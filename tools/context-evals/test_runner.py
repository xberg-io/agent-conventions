"""Tests for runner.py with a real throwaway git repository and a fake agent process."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Mapping
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

import cases
import runner
import testkit

ENV = {"PATH": "/usr/bin:/bin", "ANTHROPIC_API_KEY": "test-key", "HOME": "/home/dev", "SECRET_TOKEN": "x"}


def git(repo: Path, *args: str) -> str:
    cmd = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args]
    return subprocess.run(cmd, cwd=repo, capture_output=True, text=True, check=True).stdout.strip()


class FakeAgent:
    """Records each call; the agent call dirties the tree so the reset is observable."""

    def __init__(self, timeout_case: str = "") -> None:
        self.calls: list[dict] = []
        self.timeout_case = timeout_case

    def __call__(self, argv: list[str], cwd: Path, env: Mapping[str, str], timeout: float) -> runner.Completed:
        root = Path(env.get("CLAUDE_CONFIG_DIR", cwd))
        self.calls.append(
            {
                "argv": argv,
                "cwd": cwd,
                "env": dict(env),
                "timeout": timeout,
                "stray_before": any(p.name == "stray.txt" for p in cwd.rglob("stray.txt")),
                "mod_before": (cwd / "src/ocr/mod.rs").read_text() if (cwd / "src/ocr/mod.rs").exists() else "",
                "home_exists": root.is_dir(),
                "mcp": (root / "mcp.json").read_text() if (root / "mcp.json").exists() else "",
            }
        )
        if argv[0] == "ai-rulez":
            return runner.Completed(0, "", "")
        (cwd / "stray.txt").write_text("x")
        if (cwd / "src/ocr/mod.rs").exists():
            (cwd / "src/ocr/mod.rs").write_text("changed\n")
        if argv[2] == self.timeout_case:
            return runner.Completed(-1, '{"type":"system"}\n', "slow", timed_out=True)
        return runner.Completed(0, testkit.transcript_text("skill_used"), "warn\n")


class RunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.repo = testkit.make_checkout(base / "xberg")
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "init")
        self.commit = git(self.repo, "rev-parse", "HEAD")
        self.out = base / "run"
        corpus = {c.id: c for c in cases.load_corpus(testkit.CASES, testkit.domains())}
        self.cases = [corpus["xberg-ocr-dpi"], corpus["xberg-dpi-ambiguous"]]

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def make(self, fake: FakeAgent, generate: bool = True, environ: Mapping[str, str] = ENV) -> runner.Runner:
        config = runner.RunConfig(model="m-1", max_turns=7, timeout=30, repeats=2, generate=generate)
        return runner.Runner(self.repo, self.out, config, execute=fake, environ=environ)

    def test_interrupted_session_preserves_partial_evidence_without_a_completed_trial(self) -> None:
        partial = '{"type":"system","subtype":"init"}\n'

        def interrupted(_argv: list[str], _cwd: Path, _env: Mapping[str, str], _timeout: float) -> runner.Completed:
            raise runner.Interrupted(runner.Completed(130, partial, "offline interrupted stderr"))

        instance = self.make(interrupted, generate=False)
        self.out.mkdir()
        (self.out / "transcripts").mkdir()
        with self.assertRaises(KeyboardInterrupt):
            instance.session(self.repo, self.cases[0], 0)
        name = runner.session_name(self.cases[0].id, 0)
        evidence = self.out / "transcripts" / "interrupted"
        self.assertEqual((evidence / f"{name}.jsonl").read_text(), partial)
        self.assertEqual((evidence / f"{name}.stderr").read_text(), "offline interrupted stderr")
        meta = json.loads((evidence / f"{name}.meta.json").read_text())
        self.assertEqual(meta["returncode"], 130)
        self.assertEqual(meta["error"], "interrupted; partial evidence is not a completed trial")
        self.assertFalse(meta["bounded_failure"])
        self.assertFalse((self.out / "transcripts" / f"{name}.meta.json").exists())

    def test_sessions_are_hermetic_reset_and_cleaned_up(self) -> None:
        fake = FakeAgent()
        metas = self.make(fake).run(runner.resolve_ref(self.repo, "main"), self.cases)
        agent = [c for c in fake.calls if c["argv"][0] == "claude"]
        generate = [c for c in fake.calls if c["argv"][0] == "ai-rulez"]
        self.assertEqual((len(agent), len(generate)), (4, 5))
        self.assertEqual(generate[0]["argv"], ["ai-rulez", "generate", "--no-local"])
        self.assertEqual(set(generate[0]["env"]), {"PATH", "HOME"})
        first = agent[0]
        mcp_path = first["argv"][first["argv"].index("--mcp-config") + 1]
        self.assertEqual(
            first["argv"],
            [
                "claude", "-p", "What DPI does OCR render pages at by default?", "--output-format", "stream-json",
                "--verbose", "--model", "m-1", "--max-turns", "7", "--setting-sources", "project",
                "--strict-mcp-config", "--mcp-config", mcp_path, "--tools", "Read,Glob,Grep,Skill",
                "--allowedTools", "Read,Glob,Grep,Skill",
            ],
        )  # fmt: skip
        self.assertEqual(json.loads(first["mcp"]), {"mcpServers": {}})
        self.assertEqual(set(first["env"]), {"PATH", "ANTHROPIC_API_KEY", "HOME", "CLAUDE_CONFIG_DIR"})
        self.assertEqual(first["env"]["HOME"], first["env"]["CLAUDE_CONFIG_DIR"])
        self.assertEqual(len({c["env"]["HOME"] for c in agent}), 4)
        self.assertFalse(any(Path(c["env"]["HOME"]).exists() for c in agent))
        self.assertEqual(first["timeout"], 30)
        self.assertEqual(first["cwd"].name, "xberg")
        self.assertEqual(first["cwd"].parent.name, "crates")
        self.assertEqual(agent[2]["cwd"], first["cwd"].parent.parent)
        self.assertEqual([c["stray_before"] for c in agent], [False, False, False, False])
        self.assertEqual([c["mod_before"] for c in agent[:2]], [testkit.FILES["crates/xberg/src/ocr/mod.rs"]] * 2)
        checkout = first["cwd"].parent.parent
        self.assertEqual(checkout.parent.parent.name, ".worktrees")
        self.assertFalse(checkout.exists())
        self.assertEqual(len(git(self.repo, "worktree", "list").splitlines()), 1)
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")
        self.assertEqual([(m.case_id, m.repeat, m.error, m.returncode) for m in metas], [
            ("xberg-ocr-dpi", 0, "", 0), ("xberg-ocr-dpi", 1, "", 0),
            ("xberg-dpi-ambiguous", 0, "", 0), ("xberg-dpi-ambiguous", 1, "", 0),
        ])  # fmt: skip
        self.assertEqual(metas[0].root, str(checkout))
        saved = self.out / "transcripts" / "xberg-ocr-dpi.r1.jsonl"
        self.assertEqual(saved.read_text(), testkit.transcript_text("skill_used"))
        self.assertEqual(runner.read_meta(self.out / "transcripts", "xberg-ocr-dpi", 1), metas[1])
        self.assertEqual(
            sorted(str(p.relative_to(self.out / "context")) for p in (self.out / "context").rglob("*") if p.is_file()),
            sorted(k for k in testkit.FILES if k.endswith(".md")),
        )

    def test_skip_generate_timeout_and_missing_cwd(self) -> None:
        fake = FakeAgent(timeout_case="Which DPI should I use?")
        missing = cases.Case(**{**self.cases[0].__dict__, "id": "xberg-gone", "cwd": "crates/gone"})
        metas = self.make(fake, generate=False).run(self.commit, [*self.cases, missing])
        self.assertEqual([c["argv"][0] for c in fake.calls], ["claude"] * 4)
        self.assertEqual(
            [(m.case_id, m.error) for m in metas],
            [
                ("xberg-ocr-dpi", ""),
                ("xberg-ocr-dpi", ""),
                ("xberg-dpi-ambiguous", "timeout"),
                ("xberg-dpi-ambiguous", "timeout"),
                ("xberg-gone", "cwd 'crates/gone' does not exist at this ref"),
                ("xberg-gone", "cwd 'crates/gone' does not exist at this ref"),
            ],
        )
        self.assertEqual(metas[2].stderr, "slow")
        self.assertEqual((self.out / "transcripts" / "xberg-gone.r0.jsonl").read_text(), "")

    def test_rejects_advertised_tools_outside_the_read_only_profile(self) -> None:
        fake = FakeAgent()

        def drift(argv: list[str], cwd: Path, env: Mapping[str, str], timeout: float) -> runner.Completed:
            done = fake(argv, cwd, env, timeout)
            if argv[0] == "claude":
                done.stdout = done.stdout.replace('"Read", "Glob", "Grep", "Skill"', '"Read", "Bash"')
            return done

        metas = self.make(drift).run(self.commit, self.cases[:1])
        self.assertEqual(len(metas), 2)
        self.assertTrue(all("tool profile mismatch" in meta.error for meta in metas))

    def test_rejects_a_missing_init_tool_profile(self) -> None:
        fake = FakeAgent()

        def no_init(argv: list[str], cwd: Path, env: Mapping[str, str], timeout: float) -> runner.Completed:
            done = fake(argv, cwd, env, timeout)
            if argv[0] == "claude":
                done.stdout = "\n".join(done.stdout.splitlines()[1:])
            return done

        metas = self.make(no_init).run(self.commit, self.cases[:1])
        self.assertTrue(all("missing init tool profile" in meta.error for meta in metas))

    def test_refuses_nested_session_missing_key_and_missing_model(self) -> None:
        fake = FakeAgent()
        with self.assertRaisesRegex(runner.RunnerError, "CLAUDECODE"):
            self.make(fake, environ={**ENV, "CLAUDECODE": "1"}).run(self.commit, self.cases)
        with self.assertRaisesRegex(runner.RunnerError, "ANTHROPIC_API_KEY"):
            self.make(fake, environ={"PATH": "/bin"}).run(self.commit, self.cases)
        self.assertEqual(fake.calls, [])
        with self.assertRaisesRegex(runner.RunnerError, "model is required"):
            runner.RunConfig(model="")

    def test_failed_generate_aborts_and_still_removes_the_worktree(self) -> None:
        def failing(argv: list[str], cwd: Path, env: Mapping[str, str], timeout: float) -> runner.Completed:
            return runner.Completed(2, "", "boom")

        config = runner.RunConfig(model="m")
        with self.assertRaisesRegex(runner.RunnerError, "ai-rulez generate failed: boom"):
            runner.Runner(self.repo, self.out, config, execute=failing, environ=ENV).run(self.commit, self.cases)
        self.assertEqual(len(git(self.repo, "worktree", "list").splitlines()), 1)

    def test_resume_reuses_saved_sessions_without_new_model_calls(self) -> None:
        fake = FakeAgent()
        configured = self.make(fake)
        configured.run(self.commit, self.cases)
        again = FakeAgent()
        resumed = self.make(again)
        resumed.config.resume = True
        metas = resumed.run(self.commit, self.cases)
        self.assertEqual(len(metas), 4)
        self.assertEqual([c for c in again.calls if c["argv"][0] == "claude"], [])

    def test_parallel_workers_keep_separate_checkouts(self) -> None:
        fake = FakeAgent()
        configured = self.make(fake)
        configured.config.jobs = 2
        metas = configured.run(self.commit, self.cases)
        calls = [c for c in fake.calls if c["argv"][0] == "claude"]
        self.assertEqual(len(metas), 4)
        self.assertEqual(len({c["cwd"].parents[1] if c["cwd"].name == "xberg" else c["cwd"] for c in calls}), 2)

    def test_resume_rejects_changed_context_without_overwriting_original(self) -> None:
        self.make(FakeAgent()).run(self.commit, self.cases)
        original = (self.out / "context/CLAUDE.md").read_text()
        fake = FakeAgent()

        def changing(argv, cwd, env, timeout):
            if argv[0] == "ai-rulez":
                (cwd / "CLAUDE.md").write_text("changed generated instructions")
            return fake(argv, cwd, env, timeout)

        resumed = self.make(changing)
        resumed.config.resume = True
        with self.assertRaisesRegex(runner.RunnerError, "identity"):
            resumed.run(self.commit, self.cases)
        self.assertEqual((self.out / "context/CLAUDE.md").read_text(), original)
        self.assertEqual([c for c in fake.calls if c["argv"][0] == "claude"], [])

    def test_resume_rejects_changed_generation_mode_and_binary(self) -> None:
        self.make(FakeAgent()).run(self.commit, self.cases)
        resumed = self.make(FakeAgent(), generate=False)
        resumed.config.resume = True
        with self.assertRaisesRegex(runner.RunnerError, "identity"):
            resumed.run(self.commit, self.cases)
        binary = Path(self.tmp.name) / "different-ai-rulez"
        binary.write_text("different binary")
        original_which = runner.shutil.which

        def different_binary(name, *args, **kwargs):
            return str(binary) if name == "ai-rulez" else original_which(name, *args, **kwargs)

        resumed = self.make(FakeAgent())
        resumed.config.resume = True
        with patch.object(runner.shutil, "which", different_binary):
            with self.assertRaisesRegex(runner.RunnerError, "identity"):
                resumed.run(self.commit, self.cases)

    def test_legacy_resume_without_identity_is_refused(self) -> None:
        self.make(FakeAgent()).run(self.commit, self.cases)
        (self.out / "context-identity.json").unlink(missing_ok=True)
        resumed = self.make(FakeAgent())
        resumed.config.resume = True
        with self.assertRaisesRegex(runner.RunnerError, "identity"):
            resumed.run(self.commit, self.cases)

    def test_unknown_ref_is_an_error(self) -> None:
        with self.assertRaises(runner.RunnerError):
            runner.resolve_ref(self.repo, "no-such-ref")


class FrozenRoundTest(unittest.TestCase):
    """The binaries and include cache a round starts with are the ones every one of its sessions uses."""

    setUp = RunnerTest.setUp
    tearDown = RunnerTest.tearDown
    make = RunnerTest.make

    def install(self, name: str, data: bytes) -> Path:
        installed = Path(self.tmp.name) / "installed"
        installed.mkdir(exist_ok=True)
        binary = installed / name
        binary.write_bytes(data)
        binary.chmod(0o755)
        return binary

    def installed_env(self) -> dict[str, str]:
        return {**ENV, "PATH": f"{Path(self.tmp.name) / 'installed'}:/usr/bin:/bin"}

    def test_an_agent_update_mid_run_does_not_change_the_binary_sessions_run(self) -> None:
        installed = self.install("claude", b"\x7fELF claude 2.1.318")
        self.install("ai-rulez", b"\x7fELF ai-rulez 5.10.0")
        fake = FakeAgent()

        def updating(argv: list[str], cwd: Path, env: Mapping[str, str], timeout: float) -> runner.Completed:
            if argv[0] == "claude":
                installed.write_bytes(b"\x7fELF claude 2.1.319")
            return fake(argv, cwd, env, timeout)

        metas = self.make(updating, environ=self.installed_env()).run(self.commit, self.cases)
        frozen = self.out / "bin"
        self.assertEqual([m.error for m in metas], ["", "", "", ""])
        self.assertEqual((frozen / "claude").read_bytes(), b"\x7fELF claude 2.1.318")
        self.assertEqual({c["env"]["PATH"].split(":")[0] for c in fake.calls}, {str(frozen.resolve())})
        identity = json.loads((self.out / "context-identity.json").read_text())
        self.assertEqual(identity["agent_sha256"], hashlib.sha256(b"\x7fELF claude 2.1.318").hexdigest())
        record = json.loads((self.out / runner.FROZEN_RECORD).read_text())
        self.assertEqual(sorted(record["binaries"]), ["ai-rulez", "claude"])
        self.assertEqual(record["binaries"]["claude"]["source"], str(installed.resolve()))

    def test_resume_after_an_agent_update_reuses_the_frozen_copy(self) -> None:
        installed = self.install("claude", b"\x7fELF claude 2.1.318")
        self.make(FakeAgent(), generate=False, environ=self.installed_env()).run(self.commit, self.cases[:1])
        installed.write_bytes(b"\x7fELF claude 2.1.319")
        again = FakeAgent()
        resumed = self.make(again, generate=False, environ=self.installed_env())
        resumed.config.resume = True
        (self.out / "transcripts" / "xberg-ocr-dpi.r1.jsonl").unlink()
        metas = resumed.run(self.commit, self.cases[:1])
        self.assertEqual([m.error for m in metas], ["", ""])
        self.assertEqual(len([c for c in again.calls if c["argv"][0] == "claude"]), 1)
        self.assertEqual((self.out / "bin" / "claude").read_bytes(), b"\x7fELF claude 2.1.318")

    def test_a_changed_frozen_copy_is_still_refused(self) -> None:
        self.install("claude", b"\x7fELF claude 2.1.318")
        self.make(FakeAgent(), generate=False, environ=self.installed_env()).run(self.commit, self.cases[:1])
        frozen = self.out / "bin" / "claude"
        frozen.chmod(0o755)
        frozen.write_bytes(b"\x7fELF tampered")
        resumed = self.make(FakeAgent(), generate=False, environ=self.installed_env())
        resumed.config.resume = True
        with self.assertRaisesRegex(runner.RunnerError, "identity"):
            resumed.run(self.commit, self.cases[:1])

    def test_a_script_launcher_cannot_be_frozen(self) -> None:
        self.install("claude", b"#!/bin/sh\nexec node cli.js\n")
        fake = FakeAgent()
        with self.assertRaisesRegex(runner.RunnerError, "script launcher"):
            self.make(fake, generate=False, environ=self.installed_env()).run(self.commit, self.cases)
        self.assertEqual(fake.calls, [])

    def test_judging_runs_the_frozen_copy(self) -> None:
        self.install("claude", b"\x7fELF claude 2.1.318")
        self.make(FakeAgent(), generate=False, environ=self.installed_env()).run(self.commit, self.cases[:1])
        environ = runner.frozen_environ(self.out, ENV)
        self.assertEqual(environ["PATH"], f"{(self.out / 'bin').resolve()}:/usr/bin:/bin")
        self.assertEqual(runner.frozen_environ(Path(self.tmp.name) / "no-run", ENV), ENV)

    def test_generation_uses_a_private_cache_home(self) -> None:
        real = Path(self.tmp.name) / "real-home"
        (real / ".cache" / "ai-rulez").mkdir(parents=True)
        (real / ".cache" / "ai-rulez" / "stale-include").write_text("stale")
        (real / ".ssh").mkdir()
        (real / ".gitconfig").write_text("[user]\n")
        fake = FakeAgent()
        self.make(fake, environ={**ENV, "HOME": str(real)}).run(self.commit, self.cases[:1])
        generate = [c for c in fake.calls if c["argv"][0] == "ai-rulez"]
        home = (self.out / runner.GENERATOR_HOME).resolve()
        self.assertEqual({c["env"]["HOME"] for c in generate}, {str(home)})
        self.assertEqual(set(generate[0]["env"]), {"PATH", "HOME"})
        self.assertEqual((home / ".gitconfig").readlink(), real / ".gitconfig")
        self.assertEqual((home / ".ssh").readlink(), real / ".ssh")
        self.assertFalse((home / ".config" / "git").exists())
        self.assertEqual(list((home / ".cache").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
