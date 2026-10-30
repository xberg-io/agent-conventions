#!/usr/bin/env python3
"""Fail when a consumer's ai-rulez hook source does not follow the convention repository's floating tag (org ADR-0015).

The tag moves on every ai-rulez release, so a consumer's lock may hold any commit it resolved to; the gate checks only
that the lock holds a resolved commit, not which one.
"""

from __future__ import annotations

import argparse
import re
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


COMMIT = re.compile(r"^[0-9a-f]{40}$")


def has_hooks(consumer: Path) -> bool:
    """A consumer without poly.toml or poly-hooks.lock runs no poly hooks, so it has no hook source to pin."""
    return (consumer / "poly.toml").exists() or (consumer / "poly-hooks.lock").exists()


def check(consumer: Path, expected_revision: str) -> list[str]:
    errors = []
    if not has_hooks(consumer):
        return errors
    try:
        actual = source(consumer / "poly.toml", "hooks").get("revision")
        if actual != expected_revision:
            errors.append(f"{consumer / 'poly.toml'}: ai-rulez revision {actual!r}, expected {expected_revision!r}")
    except (OSError, ValueError) as exc:
        errors.append(str(exc))
    try:
        locked = source(consumer / "poly-hooks.lock", "sources").get("revision")
        if not isinstance(locked, str) or not COMMIT.match(locked):
            errors.append(f"{consumer / 'poly-hooks.lock'}: ai-rulez revision {locked!r} is not a resolved commit")
    except (OSError, ValueError) as exc:
        errors.append(str(exc))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consumer", type=Path, default=Path.cwd())
    parser.add_argument("--conventions", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    try:
        expected = source(args.conventions / "poly.toml", "hooks")["revision"]
        errors = check(args.consumer, expected)
    except (OSError, ValueError, KeyError) as exc:
        errors = [str(exc)]
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if not errors and not has_hooks(args.consumer):
        print("checked 0 consumers: no poly.toml or poly-hooks.lock, so no poly hooks")
    elif not errors:
        print(f"checked 1 consumer: ai-rulez {expected}")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
