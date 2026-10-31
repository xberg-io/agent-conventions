"""Hermetic headless sessions per case (issue #3, section 5.2).

For a consumer repository and a git ref the runner creates a throwaway worktree, generates the AI configuration
there, and runs each case N times with a fresh HOME and config directory, project settings only, an empty strict
MCP config, read-only tools, a turn cap and a timeout. Each session's raw transcript and a small metadata file go to
`<out>/transcripts/`; the worktree is reset after every session and removed at the end. The developer's own
configuration never reaches a session: the child sees only PATH, the API key and its own temporary HOME.

The agent is an adapter (command line and environment); only Claude Code is implemented. The process call is
injectable so tests run without the agent.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path

import tool_unavailable
import transcript
from cases import Case

DEFAULT_TOOLS = ("Read", "Glob", "Grep", "Skill")
TOOL_PROFILE_VERSION = "claude-read-only-1"
CONTEXT_DIRS = (".claude/rules", ".claude/skills", ".claude/agents", ".agents/skills")
CONTEXT_FILES = (".mcp.json", ".claude/settings.json", ".claude/settings.local.json", ".codex/config.toml")
PRUNE = {".git", "node_modules", "target", ".venv", "vendor", "dist", "build"}
STDERR_TAIL = 2000


class RunnerError(RuntimeError):
    pass


@dataclass
class Completed:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    bounded_failure: bool = False
    collection: dict = field(default_factory=dict)


class Interrupted(KeyboardInterrupt):
    def __init__(self, completed: Completed) -> None:
        super().__init__("isolated CLI interrupted")
        self.completed = completed


def save_interrupted(transcripts: Path, name: str, meta: SessionMeta, completed: Completed) -> None:
    evidence = transcripts / "interrupted"
    evidence.mkdir(exist_ok=True)
    meta.returncode, meta.stderr = 130, completed.stderr[-STDERR_TAIL:]
    meta.error = "interrupted; partial evidence is not a completed trial"
    with (evidence / f"{name}.jsonl").open("x") as stream:
        stream.write(completed.stdout)
    with (evidence / f"{name}.stderr").open("x") as stream:
        stream.write(completed.stderr)
    with (evidence / f"{name}.meta.json").open("x") as stream:
        stream.write(json.dumps(asdict(meta), indent=2) + "\n")


Execute = Callable[[list[str], Path, Mapping[str, str], float], Completed]


def _text(data: bytes | str | None) -> str:
    return data.decode(errors="replace") if isinstance(data, bytes) else (data or "")


def subprocess_execute(argv: list[str], cwd: Path, env: Mapping[str, str], timeout: float) -> Completed:
    try:
        out = subprocess.run(argv, cwd=cwd, env=dict(env), capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        return Completed(-1, _text(exc.stdout), _text(exc.stderr), timed_out=True)
    return Completed(out.returncode, out.stdout, out.stderr)


@dataclass(frozen=True)
class SessionSpec:
    prompt: str
    model: str
    max_turns: int
    mcp_config: Path
    allowed_tools: tuple[str, ...]


class ClaudeAdapter:
    """Claude Code in print mode with stream-json output."""

    name = "claude"

    def command(self, spec: SessionSpec) -> list[str]:
        return [
            "claude",
            "-p",
            spec.prompt,
            "--output-format",
            "stream-json",
            "--verbose",
            "--model",
            spec.model,
            "--max-turns",
            str(spec.max_turns),
            "--setting-sources",
            "project",
            "--strict-mcp-config",
            "--mcp-config",
            str(spec.mcp_config),
            "--tools",
            ",".join(spec.allowed_tools),
            "--allowedTools",
            ",".join(spec.allowed_tools),
        ]

    def env(self, home: Path, environ: Mapping[str, str]) -> dict[str, str]:
        return {
            "PATH": environ.get("PATH", "/usr/bin:/bin"),
            "ANTHROPIC_API_KEY": environ["ANTHROPIC_API_KEY"],
            "HOME": str(home),
            "CLAUDE_CONFIG_DIR": str(home),
        }


def preflight(environ: Mapping[str, str]) -> None:
    """Refuse to run nested in another agent session (it would inherit that session) or without a key."""
    if environ.get("CLAUDECODE"):
        raise RunnerError("refusing to run inside another Claude Code session (CLAUDECODE is set)")
    if not environ.get("ANTHROPIC_API_KEY"):
        raise RunnerError("ANTHROPIC_API_KEY is not set")


def git(*args: str, cwd: Path) -> str:
    out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    if out.returncode != 0:
        raise RunnerError(f"git {' '.join(args)} failed in {cwd}: {out.stderr.strip()}")
    return out.stdout.strip()


def resolve_ref(repo: Path, ref: str) -> str:
    return git("rev-parse", "--verify", f"{ref}^{{commit}}", cwd=repo)


@contextmanager
def worktree(repo: Path, commit: str) -> Iterator[Path]:
    """A detached throwaway worktree outside the repository, removed afterwards whatever happens."""
    parent = repo.resolve().parent / ".worktrees" / repo.resolve().name
    parent.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix="context-eval-", dir=parent)).resolve()
    git("worktree", "add", "--detach", "--quiet", str(path), commit, cwd=repo)
    try:
        yield path
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(path)], cwd=repo, capture_output=True, check=False)
        shutil.rmtree(path, ignore_errors=True)


def snapshot_context(checkout: Path, dest: Path) -> None:
    """Copy the files the inventory needs (root and nested CLAUDE.md/AGENTS.md, rules, skills, agents)."""
    for root, dirs, files in os.walk(checkout):
        dirs[:] = sorted(d for d in dirs if d not in PRUNE)
        for name in files:
            if name in ("CLAUDE.md", "AGENTS.md"):
                src = Path(root) / name
                target = dest / src.relative_to(checkout)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
    for rel in CONTEXT_DIRS:
        if (checkout / rel).is_dir():
            shutil.copytree(checkout / rel, dest / rel, symlinks=False, dirs_exist_ok=True)
    for rel in CONTEXT_FILES:
        if (checkout / rel).is_file():
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(checkout / rel, target)


def context_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        data = path.read_bytes()
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(len(data).to_bytes(8, "big") + data)
    return digest.hexdigest()


def binary_fingerprint(name: str, environ: Mapping[str, str]) -> str:
    binary = shutil.which(name, path=environ.get("PATH"))
    return hashlib.sha256(Path(binary).read_bytes()).hexdigest() if binary else "unavailable"


def session_name(case_id: str, repeat: int) -> str:
    return f"{case_id}.r{repeat}"


@dataclass
class SessionMeta:
    case_id: str
    repeat: int
    root: str
    """Worktree path at run time: the parser strips it from absolute tool paths."""
    returncode: int
    seconds: float
    error: str = ""
    stderr: str = ""
    bounded_failure: bool = False
    collection: dict = field(default_factory=dict)


def tool_profile_error(stdout: str, expected: tuple[str, ...]) -> str:
    """Fail closed when the CLI's advertised or used tools differ from its command contract."""
    parsed = transcript.parse(stdout)
    tools = parsed.init.get("tools")
    if not isinstance(tools, list):
        return "missing init tool profile"
    if not all(isinstance(tool, str) for tool in tools) or len(tools) != len(expected) or set(tools) != set(expected):
        return "tool profile mismatch"
    if any(call.name not in expected for call in parsed.calls):
        return "tool profile mismatch: unexpected tool call"
    return ""


def session_error(result: Completed, tools: tuple[str, ...]) -> str:
    if result.timed_out:
        return "timeout"
    if result.returncode != 0 and not result.stdout.strip():
        return f"exit {result.returncode}"
    if result.bounded_failure and result.returncode == 1 and tool_unavailable.native_evidence(result.stdout, tools):
        return "tool_unavailable"
    return tool_profile_error(result.stdout, tools)


@dataclass
class RunConfig:
    model: str
    max_turns: int = 20
    timeout: float = 600.0
    repeats: int = 1
    allowed_tools: tuple[str, ...] = DEFAULT_TOOLS
    generate: bool = True
    jobs: int = 1
    resume: bool = False

    def __post_init__(self) -> None:
        if not self.model:
            raise RunnerError("a model is required")
        if self.repeats < 1 or self.max_turns < 1 or self.timeout <= 0 or self.jobs < 1:
            raise RunnerError("repeats, max turns and timeout must be positive")


class Runner:
    def __init__(
        self,
        repo: Path,
        out: Path,
        config: RunConfig,
        *,
        adapter: ClaudeAdapter | None = None,
        execute: Execute = subprocess_execute,
        environ: Mapping[str, str] = os.environ,
        inherited: Mapping[tuple[str, int], SessionMeta] | None = None,
    ) -> None:
        self.inherited = inherited or {}
        self.repo = repo.resolve()
        self.out = out.resolve()
        self.config = config
        self.adapter = adapter or ClaudeAdapter()
        self.execute = execute
        self.environ = environ
        self.context_lock = threading.Lock()

    def prepare_context(self, checkout: Path) -> None:
        with self.context_lock, tempfile.TemporaryDirectory(prefix="ctx-context-check-") as tmp:
            candidate = Path(tmp)
            snapshot_context(checkout, candidate)
            config = asdict(self.config)
            for key in ("jobs", "resume"):
                config.pop(key)
            identity = {
                "tool_profile_version": TOOL_PROFILE_VERSION,
                "context_sha256": context_fingerprint(candidate),
                "config": config,
                "agent_sha256": binary_fingerprint(self.adapter.name, self.environ),
                "generator_sha256": binary_fingerprint("ai-rulez", self.environ)
                if self.config.generate
                else "committed",
            }
            identity = json.loads(json.dumps(identity))
            path = self.out / "context-identity.json"
            context = self.out / "context"
            if path.exists():
                stored = json.loads(path.read_text())
                if stored != identity or context_fingerprint(context) != stored["context_sha256"]:
                    raise RunnerError("context identity changed; refusing to reuse transcripts")
                return
            if self.config.resume or context.exists():
                raise RunnerError("missing context identity; legacy runs require review before resumption")
            shutil.copytree(candidate, context)
            path.write_text(json.dumps(identity, indent=2) + "\n")

    def generate(self, checkout: Path) -> None:
        if not self.config.generate:
            return
        env = {"PATH": self.environ.get("PATH", "/usr/bin:/bin"), "HOME": self.environ.get("HOME", str(checkout))}
        done = self.execute(["ai-rulez", "generate", "--no-local"], checkout, env, self.config.timeout)
        if done.returncode != 0 or done.timed_out:
            raise RunnerError(f"ai-rulez generate failed: {done.stderr[-STDERR_TAIL:]}")

    def reset(self, checkout: Path) -> None:
        if checkout.resolve() == self.repo:
            raise RunnerError("refusing to reset the source checkout")
        git("checkout", "--", ".", cwd=checkout)
        git("clean", "-fdq", cwd=checkout)
        self.generate(checkout)
        self.prepare_context(checkout)

    def session(self, checkout: Path, case: Case, repeat: int) -> SessionMeta:
        transcripts = self.out / "transcripts"
        name = session_name(case.id, repeat)
        cwd = checkout / case.cwd
        meta = SessionMeta(case.id, repeat, str(checkout), 0, 0.0)
        if not cwd.is_dir():
            meta.error = f"cwd {case.cwd!r} does not exist at this ref"
            (transcripts / f"{name}.jsonl").write_text("")
        else:
            with tempfile.TemporaryDirectory(prefix="ctx-home-") as home:
                mcp = Path(home) / "mcp.json"
                mcp.write_text(json.dumps({"mcpServers": {}}))
                spec = SessionSpec(
                    case.prompt, self.config.model, self.config.max_turns, mcp, self.config.allowed_tools
                )
                started = time.monotonic()
                try:
                    done = self.execute(
                        self.adapter.command(spec), cwd, self.adapter.env(Path(home), self.environ), self.config.timeout
                    )
                except Interrupted as exc:
                    meta.seconds = round(time.monotonic() - started, 3)
                    save_interrupted(transcripts, name, meta, exc.completed)
                    raise
                meta.seconds = round(time.monotonic() - started, 3)
            meta.returncode, meta.stderr = done.returncode, done.stderr[-STDERR_TAIL:]
            meta.bounded_failure = done.bounded_failure
            meta.collection = done.collection
            meta.error = session_error(done, self.config.allowed_tools)
            (transcripts / f"{name}.jsonl").write_text(done.stdout)
        (transcripts / f"{name}.meta.json").write_text(json.dumps(asdict(meta), indent=2) + "\n")
        return meta

    def run_worker(self, commit: str, cases: list[Case]) -> list[SessionMeta]:
        metas = []
        with worktree(self.repo, commit) as checkout:
            self.generate(checkout)
            self.prepare_context(checkout)
            for case in cases:
                for repeat in range(self.config.repeats):
                    inherited = self.inherited.get((case.id, repeat))
                    if inherited is not None:
                        metas.append(inherited)
                        continue
                    previous = read_meta(self.out / "transcripts", case.id, repeat) if self.config.resume else None
                    raw = self.out / "transcripts" / f"{session_name(case.id, repeat)}.jsonl"
                    if previous is not None and raw.is_file():
                        if not previous.error:
                            previous.error = tool_profile_error(raw.read_text(), self.config.allowed_tools)
                        metas.append(previous)
                        continue
                    metas.append(self.session(checkout, case, repeat))
                    self.reset(checkout)
        return metas

    def run(self, commit: str, cases: list[Case]) -> list[SessionMeta]:
        preflight(self.environ)
        if shutil.which("git") is None:
            raise RunnerError("git is not on PATH")
        (self.out / "transcripts").mkdir(parents=True, exist_ok=True)
        jobs = min(self.config.jobs, len(cases))
        if jobs <= 1:
            return self.run_worker(commit, cases)
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            pending = [pool.submit(self.run_worker, commit, cases[i::jobs]) for i in range(jobs)]
            return [meta for future in pending for meta in future.result()]


def read_meta(transcripts: Path, case_id: str, repeat: int) -> SessionMeta | None:
    path = transcripts / f"{session_name(case_id, repeat)}.meta.json"
    return SessionMeta(**json.loads(path.read_text())) if path.exists() else None
