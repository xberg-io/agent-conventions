"""The append-only experiment ledger of the improvement loop (issue #3, section 6, step 8).

One JSON line per arm and round. Every entry is validated on write and carries `prev`, the sha256 of the line before
it, so an edited or deleted line breaks the chain and every later append is refused. Proposers read
`history(artifact)` so an idea that was rejected for an artifact is not retried.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_PATH = Path(__file__).parent / "ledger.jsonl"
ARM_KINDS = ("change", "placebo", "deletion")
DECISIONS = ("accept", "reject", "inconclusive", "stopped")
"""`stopped`: the arm was dropped at the screen stage (paired mean difference <= 0)."""
STAGES = ("screen", "test")
TEXT_FIELDS = (
    "cluster",
    "hypothesis",
    "patch_ref",
    "base_ref",
    "model",
    "harness_version",
    "judge_version",
    "rubric_version",
    "taxonomy_version",
    "timestamp",
)
FIELDS = (*TEXT_FIELDS, "round", "arm_kind", "artifacts", "stages", "decision", "cost_usd", "prev")


def digest(line: str) -> str:
    return hashlib.sha256(line.encode()).hexdigest()


def validate(entry: dict) -> None:
    missing = sorted(set(FIELDS) - set(entry))
    unknown = sorted(set(entry) - set(FIELDS))
    if missing or unknown:
        raise ValueError(f"ledger entry: missing {missing}, unknown {unknown}")
    for name in TEXT_FIELDS:
        if not isinstance(entry[name], str) or not entry[name]:
            raise ValueError(f"ledger entry: {name} must be a non-empty string")
    if type(entry["round"]) is not int or entry["round"] < 1:
        raise ValueError("ledger entry: round must be an integer >= 1")
    if entry["arm_kind"] not in ARM_KINDS:
        raise ValueError(f"ledger entry: arm_kind {entry['arm_kind']!r} not in {ARM_KINDS}")
    if entry["decision"] not in DECISIONS:
        raise ValueError(f"ledger entry: decision {entry['decision']!r} not in {DECISIONS}")
    if not isinstance(entry["artifacts"], list) or not all(isinstance(a, str) and a for a in entry["artifacts"]):
        raise ValueError("ledger entry: artifacts must be a list of non-empty strings")
    stages = entry["stages"]
    if (
        not isinstance(stages, dict)
        or set(stages) - set(STAGES)
        or not all(isinstance(v, dict) for v in stages.values())
    ):
        raise ValueError(f"ledger entry: stages must map a subset of {STAGES} to objects")
    cost = entry["cost_usd"]
    if isinstance(cost, bool) or not isinstance(cost, int | float) or cost < 0:
        raise ValueError("ledger entry: cost_usd must be a number >= 0")
    if not isinstance(entry["prev"], str) or len(entry["prev"]) not in (0, 64):
        raise ValueError("ledger entry: prev must be empty or a sha256 hex digest")


def accepted_changes(entries: list[dict]) -> int:
    """Accepted change and deletion arms; an accepted placebo is a false accept, not a change."""
    return sum(1 for e in entries if e["decision"] == "accept" and e["arm_kind"] != "placebo")


class Ledger:
    def __init__(self, path: Path = DEFAULT_PATH) -> None:
        self.path = path

    def _lines(self) -> list[str]:
        return self.path.read_text().splitlines() if self.path.exists() else []

    def entries(self) -> list[dict]:
        """Every entry, after checking each line parses, validates and chains to the one before."""
        out = []
        prev = ""
        for number, line in enumerate(self._lines(), start=1):
            try:
                entry = json.loads(line)
                validate(entry)
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"{self.path} line {number}: {exc}") from exc
            if entry["prev"] != prev:
                raise ValueError(
                    f"{self.path} line {number}: prev does not match line {number - 1}, history was rewritten"
                )
            out.append(entry)
            prev = digest(line)
        return out

    def append(self, entry: dict) -> dict:
        if "prev" in entry:
            raise ValueError("ledger entry: prev is set by the ledger, not the caller")
        existing = self.entries()
        lines = self._lines()
        if lines and not self.path.read_text().endswith("\n"):
            raise ValueError(f"{self.path}: last line is not terminated, refusing to append to a partial write")
        entry = dict(entry)
        entry.setdefault("timestamp", datetime.now(UTC).isoformat(timespec="seconds"))
        entry["prev"] = digest(lines[-1]) if lines else ""
        validate(entry)
        if existing and entry["round"] < existing[-1]["round"]:
            raise ValueError(f"ledger entry: round {entry['round']} is before the last round {existing[-1]['round']}")
        line = json.dumps(entry, sort_keys=True)
        with self.path.open("a") as handle:
            handle.write(line + "\n")
        return entry

    def history(self, artifact: str) -> list[dict]:
        return [e for e in self.entries() if artifact in e["artifacts"]]
