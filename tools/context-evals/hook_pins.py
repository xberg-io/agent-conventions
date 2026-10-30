#!/usr/bin/env python3
"""Fail when a consumer's local ai-rulez hooks differ from the convention pin."""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path


def source(path: Path, table: str) -> dict:
    data = tomllib.loads(path.read_text())
    sources = data.get("hooks", {}).get("sources", []) if table == "hooks" else data.get("sources", [])
    found = [s for s in sources if s.get("id") == "ai-rulez"]
    if len(found) != 1:
        raise ValueError(f"{path}: expected exactly one ai-rulez hook source, found {len(found)}")
    return found[0]


def check(consumer: Path, expected_version: str, expected_commit: str) -> list[str]:
    errors = []
    for filename, table, expected in (
        ("poly.toml", "hooks", f"v{expected_version}"),
        ("poly-hooks.lock", "sources", expected_commit),
    ):
        try:
            actual = source(consumer / filename, table).get("revision")
            if actual != expected:
                errors.append(f"{consumer / filename}: ai-rulez revision {actual!r}, expected {expected!r}")
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consumer", type=Path, default=Path.cwd())
    parser.add_argument("--conventions", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    try:
        tools = tomllib.loads((args.conventions / "mise.toml").read_text())["tools"]
        expected = tools["github:Goldziher/ai-rulez"]
        commit = source(args.conventions / "poly-hooks.lock", "sources")["revision"]
        errors = check(args.consumer, expected, commit)
    except (OSError, ValueError, KeyError) as exc:
        errors = [str(exc)]
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if not errors:
        print(f"checked 1 consumer: ai-rulez v{expected}, lock {commit}")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
