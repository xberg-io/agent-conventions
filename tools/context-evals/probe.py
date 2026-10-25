#!/usr/bin/env python3
"""Probe what Claude Code loads at start and on demand (issue #3, section 4.1).

Copies a consumer checkout to a throwaway directory, plants a unique sentinel in each candidate artifact (the root
CLAUDE.md, an unscoped and a glob-scoped rule, a skill description, a nested CLAUDE.md), and runs headless sessions
with a fresh config directory:

- start: a trivial prompt; reports usage (input + cache tokens) and which sentinels the model can see.
- on-demand: the same after reading a file the glob-scoped rule and the nested CLAUDE.md cover.

Needs `claude` on PATH and ANTHROPIC_API_KEY in the environment; nothing from the user's own configuration is used.
Run it on a machine you control, not inside another agent session (the child would inherit that session).

Usage:
    probe.py REPO --scoped-file crates/foo/src/lib.rs [--repeats 3] [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SENTINEL = re.compile(r"PROBE-[A-Z]+-[0-9a-f]{8}")
ASK = (
    "List every string matching PROBE-<WORD>-<8 hex> that appears anywhere in your instructions, rules, "
    "skill listings or context, one per line, and nothing else. Print NONE if there are none."
)


def plant(root: Path, scoped_file: str) -> dict[str, str]:
    """Write one sentinel per artifact; return {artifact: sentinel}."""
    tokens = {
        name: f"PROBE-{name.upper().replace('-', '')}-{secrets.token_hex(4)}"
        for name in ("root", "rule", "scoped", "skill", "nested")
    }
    claude_md = root / "CLAUDE.md"
    claude_md.write_text(
        claude_md.read_text() + f"\n\nProbe marker: {tokens['root']}\n"
        if claude_md.exists()
        else f"Probe marker: {tokens['root']}\n"
    )
    rules = root / ".claude" / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    (rules / "probe-unscoped.md").write_text(f"Probe marker: {tokens['rule']}\n")
    scoped_dir = str(Path(scoped_file).parent)
    (rules / "probe-scoped.md").write_text(
        f'---\npaths:\n  - "{scoped_dir}/**"\n---\nProbe marker: {tokens["scoped"]}\n'
    )
    skill = root / ".claude" / "skills" / "probe-skill"
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text(
        f"---\nname: probe-skill\ndescription: Probe marker {tokens['skill']}.\n---\nbody\n"
    )
    (root / scoped_dir / "CLAUDE.md").write_text(f"Probe marker: {tokens['nested']}\n")
    return tokens


def run(root: Path, prompt: str, config_dir: Path) -> dict:
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(config_dir),
        "CLAUDE_CONFIG_DIR": str(config_dir),
        "ANTHROPIC_API_KEY": os.environ["ANTHROPIC_API_KEY"],
    }
    out = subprocess.run(
        [
            "claude",
            "-p",
            prompt,
            "--output-format",
            "json",
            "--allowedTools",
            "Read",
            "--strict-mcp-config",
            "--setting-sources",
            "project",
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    data = json.loads(out.stdout or "{}")
    usage = data.get("usage", {})
    start = sum(usage.get(k, 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    return {"tokens": start, "seen": sorted(set(SENTINEL.findall(data.get("result", "")))), "error": out.stderr[-500:]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repo", type=Path)
    parser.add_argument("--scoped-file", required=True, help="a tracked file under the directory to scope")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    if "ANTHROPIC_API_KEY" not in os.environ or shutil.which("claude") is None:
        sys.exit("needs `claude` on PATH and ANTHROPIC_API_KEY")
    if os.environ.get("CLAUDECODE"):
        sys.exit("refusing to run inside another Claude Code session")

    results = []
    with tempfile.TemporaryDirectory(prefix="ctx-probe-") as tmp:
        root = Path(tmp) / "repo"
        shutil.copytree(args.repo, root, symlinks=True, ignore=shutil.ignore_patterns(".git", "target", "node_modules"))
        tokens = plant(root, args.scoped_file)
        for _ in range(args.repeats):
            for phase, prompt in (("start", ASK), ("on-demand", f"Read {args.scoped_file}, then: {ASK}")):
                config = Path(tempfile.mkdtemp(prefix="cfg-", dir=tmp))
                result = run(root, prompt, config)
                loaded = {name: tok in result["seen"] for name, tok in tokens.items()}
                results.append({"phase": phase, **result, "loaded": loaded})
                print(
                    f"{phase:9} tokens={result['tokens']:>7}  "
                    + "  ".join(f"{k}={'y' if v else '-'}" for k, v in loaded.items())
                )
    if args.json:
        args.json.write_text(json.dumps(results, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
