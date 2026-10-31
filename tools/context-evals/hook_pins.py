#!/usr/bin/env python3
"""Fail when a consumer's poly hook sources do not follow the convention repository's pin policy (hook-pins.toml).

A floating source (`vN`, org ADR-0015) must name the bare major; its tag moves on every release, so the lock may hold
any commit it resolved to and the gate checks only that the lock holds a resolved commit. An exact source (`vN.N.N`)
must name that tag. A required source must be declared; the others are checked where a consumer declares them.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

COMMIT = re.compile(r"^[0-9a-f]{40}$")
FLOATING = re.compile(r"^v[0-9]+$")
EXACT = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+$")
POLICY = Path("tools/context-evals/hook-pins.toml")


@dataclass(frozen=True)
class Pin:
    id: str
    revision: str
    required: bool = False

    @property
    def floating(self) -> bool:
        return bool(FLOATING.match(self.revision))


def sources(path: Path, table: str) -> list[dict]:
    data = tomllib.loads(path.read_text())
    return data.get("hooks", {}).get("sources", []) if table == "hooks" else data.get("sources", [])


def source(path: Path, table: str, source_id: str = "ai-rulez") -> dict:
    found = [s for s in sources(path, table) if s.get("id") == source_id]
    if len(found) != 1:
        raise ValueError(f"{path}: expected exactly one {source_id} hook source, found {len(found)}")
    return found[0]


def load_policy(path: Path) -> dict[str, Pin]:
    policy: dict[str, Pin] = {}
    for entry in tomllib.loads(path.read_text()).get("sources", []):
        pin = Pin(entry.get("id", ""), entry.get("revision", ""), bool(entry.get("required", False)))
        if not pin.id or pin.id in policy:
            raise ValueError(f"{path}: hook source ids must be present and unique, got {pin.id!r}")
        if not (FLOATING.match(pin.revision) or EXACT.match(pin.revision)):
            raise ValueError(f"{path}: {pin.id} revision {pin.revision!r} is neither a bare major nor a full tag")
        policy[pin.id] = pin
    if not any(pin.required for pin in policy.values()):
        raise ValueError(f"{path}: no required hook source, so the gate would check nothing")
    return policy


def has_hooks(consumer: Path) -> bool:
    """A consumer without poly.toml or poly-hooks.lock runs no poly hooks, so it has no hook source to pin."""
    return (consumer / "poly.toml").exists() or (consumer / "poly-hooks.lock").exists()


def declared(path: Path, table: str, errors: list[str]) -> list[dict] | None:
    try:
        return sources(path, table)
    except (OSError, ValueError) as exc:
        errors.append(str(exc))
        return None


def check_revision(path: Path, pin: Pin, actual: object) -> list[str]:
    if actual == pin.revision:
        return []
    kind = "a floating source names its bare major" if pin.floating else "an exact source names its full tag"
    return [f"{path}: {pin.id} revision {actual!r}, expected {pin.revision!r} ({kind})"]


def in_use(policy: dict[str, Pin], *declarations: list[dict] | None) -> list[Pin]:
    present = {s.get("id") for found in declarations for s in found or []}
    return [pin for pin in policy.values() if pin.required or pin.id in present]


def check(consumer: Path, policy: dict[str, Pin]) -> list[str]:
    if not consumer.is_dir():
        return [f"{consumer}: consumer must be an existing directory"]
    errors: list[str] = []
    if not has_hooks(consumer):
        return errors
    config_path, lock_path = consumer / "poly.toml", consumer / "poly-hooks.lock"
    config = declared(config_path, "hooks", errors)
    lock = declared(lock_path, "sources", errors)
    for pin in in_use(policy, config, lock):
        if config is not None:
            try:
                errors += check_revision(config_path, pin, source(config_path, "hooks", pin.id).get("revision"))
            except ValueError as exc:
                errors.append(str(exc))
        if lock is not None:
            try:
                locked = source(lock_path, "sources", pin.id).get("revision")
                if not isinstance(locked, str) or not COMMIT.match(locked):
                    errors.append(f"{lock_path}: {pin.id} revision {locked!r} is not a resolved commit")
            except ValueError as exc:
                errors.append(str(exc))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consumer", type=Path, default=Path.cwd())
    parser.add_argument("--conventions", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    policy: dict[str, Pin] = {}
    try:
        policy = load_policy(args.conventions / POLICY)
        errors = check(args.consumer, policy)
    except (OSError, ValueError) as exc:
        errors = [str(exc)]
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if not errors and not has_hooks(args.consumer):
        print("checked 0 consumers: no poly.toml or poly-hooks.lock, so no poly hooks")
    elif not errors:
        checked = in_use(policy, sources(args.consumer / "poly.toml", "hooks"))
        print(f"checked 1 consumer, {len(checked)} hook sources: " + ", ".join(f"{p.id} {p.revision}" for p in checked))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
