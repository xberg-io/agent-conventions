#!/usr/bin/env python3
"""Measure Claude Code and Codex context loading in disposable consumer worktrees."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path

import budget
import runner
import transcript

PROBE_VERSION = "2"
SENTINEL = re.compile(r"PROBE-[A-Z]+-[0-9a-f]{8}")
ASK = (
    "List every string matching PROBE-<WORD>-<8 hex> visible in your current instructions, rules, "
    "skill listings or context, one per line. Print NONE if none. Do not search or read files to find markers."
)


def write(path: Path, text: str, *, append: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text((path.read_text() if append and path.exists() else "") + text)


def plant(root: Path, scoped_file: str, *, preset: str = "claude") -> dict[str, str]:
    names = ("root", "agentsroot", "rule", "scoped", "skill", "skillbody", "gated", "manual", "agent", "nested")
    tokens = {name: f"PROBE-{name.upper()}-{secrets.token_hex(4)}" for name in names}
    instruction = "CLAUDE.md" if preset == "claude" else "AGENTS.md"
    write(root / instruction, f"\nProbe marker: {tokens['root']}\n", append=True)
    if preset == "claude":
        write(root / "AGENTS.md", f"\nProbe marker: {tokens['agentsroot']}\n", append=True)
    scoped_dir = str(Path(scoped_file).parent)
    rules = root / ".claude/rules"
    write(rules / "probe-unscoped.md", f"Probe marker: {tokens['rule']}\n")
    write(rules / "probe-scoped.md", f'---\npaths: ["{scoped_dir}/**"]\n---\n{tokens["scoped"]}\n')
    skills = root / (".claude/skills" if preset == "claude" else ".agents/skills")
    for name, marker, extra, body in (
        ("probe-skill", "skill", "", tokens["skillbody"]),
        ("probe-gated", "gated", f'paths: ["{scoped_dir}/**"]\n', "body"),
        ("probe-manual", "manual", "disable-model-invocation: true\n", "body"),
    ):
        write(
            skills / name / "SKILL.md", f"---\nname: {name}\ndescription: Probe {tokens[marker]}.\n{extra}---\n{body}\n"
        )
    write(root / scoped_dir / instruction, f"Probe marker: {tokens['nested']}\n")
    if preset == "claude":
        write(
            root / ".claude/agents/probe-agent.md",
            f"---\nname: probe-agent\ndescription: Probe {tokens['agent']}.\n---\nbody\n",
        )
    else:
        write(
            root / ".codex/agents/probe-agent.toml", f'name = "probe-agent"\ndescription = "Probe {tokens["agent"]}"\n'
        )
    return tokens


def codex_result(text: str) -> dict:
    answer, usage, model = "", {}, ""
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("type") == "turn.completed":
            usage = row.get("usage", {})
        item = row.get("item", {})
        if item.get("type") == "agent_message":
            answer = item.get("text", "")
        model = row.get("model", model)
    return {"answer": answer, "tokens": usage.get("input_tokens", 0), "usage": usage, "model": model}


def run_codex(
    root: Path, prompt: str, config: Path, model: str, execute: runner.Execute
) -> tuple[dict, runner.Completed]:
    environ = os.environ
    original = Path(environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "auth.json"
    if not original.is_file() or json.loads(original.read_text()).get("auth_mode") != "chatgpt":
        raise runner.RunnerError("Codex probe needs existing CLI subscription auth")
    if original.is_file():
        shutil.copy2(original, config / "auth.json")
    env = {"PATH": environ["PATH"], "HOME": str(config), "CODEX_HOME": str(config)}
    argv = [
        "codex",
        "exec",
        "--ignore-user-config",
        "--ignore-rules",
        "--ephemeral",
        "--json",
        "--sandbox",
        "read-only",
        "--model",
        model,
        "-c",
        'approval_policy="never"',
        "-c",
        "features.multi_agent=false",
        prompt,
    ]
    done = execute(argv, root, env, 180)
    result = codex_result(done.stdout)
    result["model"] = result["model"] or model
    return result, done


def run(root: Path, prompt: str, config: Path, *, preset: str, model: str, execute: runner.Execute) -> dict:
    environ = os.environ
    if preset == "claude":
        mcp = config / "mcp.json"
        mcp.write_text('{"mcpServers": {}}')
        spec = runner.SessionSpec(prompt, model, 4, mcp, runner.DEFAULT_TOOLS)
        done = execute(runner.ClaudeAdapter().command(spec), root, runner.ClaudeAdapter().env(config, environ), 180)
        parsed = transcript.parse(done.stdout)
        usage = parsed.first_usage
        result = {
            "answer": parsed.answer,
            "tokens": sum((usage.input_tokens, usage.cache_read_tokens, usage.cache_creation_tokens)) if usage else 0,
            "model": parsed.model,
            "cost_usd": parsed.cost_usd,
        }
    else:
        result, done = run_codex(root, prompt, config, model, execute)
    result.update(
        {
            "seen": sorted(set(SENTINEL.findall(result["answer"]))),
            "error": done.stderr[-1000:] if done.returncode else "",
            "returncode": done.returncode,
            "raw": done.stdout,
            "stderr": done.stderr,
        }
    )
    return result


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("--scoped-file", required=True)
    parser.add_argument("--preset", choices=("claude", "codex"), default="claude")
    parser.add_argument("--model", required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--budget-ledger", type=Path, required=True)
    parser.add_argument(
        "--allow-soft-budget",
        action="store_true",
        help="accept prospective accounting; the CLI cannot enforce a hard dollar ceiling",
    )
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--phases", nargs="+", choices=("start", "search", "read", "skill", "nested-start"))
    return parser.parse_args()


def measure_phases(args: argparse.Namespace, root: Path, tokens: dict, paid: runner.Execute, info: dict) -> None:
    results = []
    phases = (
        ("start", ASK),
        ("search", f"Search {args.scoped_file} for __probe_no_match__, without reading it. Then: {ASK}"),
        ("read", f"Read {args.scoped_file}. Then: {ASK}"),
        ("skill", f"Invoke probe-skill. Then: {ASK}"),
        ("nested-start", ASK),
    )
    for repeat in range(args.repeats):
        for phase, prompt in phases:
            if args.phases and phase not in args.phases:
                continue
            cwd = root / Path(args.scoped_file).parent if phase == "nested-start" else root
            with tempfile.TemporaryDirectory(prefix="ctx-probe-home-") as home:
                result = run(cwd, prompt, Path(home), preset=args.preset, model=args.model, execute=paid)
            loaded = {name: value in result["seen"] for name, value in tokens.items()}
            results.append({"phase": phase, "repeat": repeat, **result, "loaded": loaded})
            args.json.write_text(json.dumps({**info, "results": results}, indent=2) + "\n")
            print(f"{args.preset} {phase} repeat={repeat} tokens={result['tokens']} loaded={loaded}", flush=True)
            if result["returncode"]:
                raise runner.RunnerError("probe subprocess failed; see local JSON stderr")


def main() -> int:
    args = arguments()
    if args.preset == "claude":
        runner.preflight(os.environ)
        if not args.allow_soft_budget:
            raise runner.RunnerError(
                "Claude CLI cannot enforce a hard dollar ceiling; explicit --allow-soft-budget consent is required"
            )
    paid = budget.BudgetedExecute(
        args.budget_ledger, 25, 0.2, runner.subprocess_execute, allow_soft_limits=args.allow_soft_budget
    )
    commit = runner.resolve_ref(args.repo, "main")
    version = subprocess.check_output([args.preset, "--version"], text=True).strip()
    with runner.worktree(args.repo, commit) as root:
        runner.Runner(args.repo, args.json.parent, runner.RunConfig(model=args.model)).generate(root)
        tokens = plant(root, args.scoped_file, preset=args.preset)
        info = {"probe_version": PROBE_VERSION, "harness_version": version, "preset": args.preset, "commit": commit}
        measure_phases(args, root, tokens, paid, info)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
