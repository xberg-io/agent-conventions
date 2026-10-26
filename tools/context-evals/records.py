"""The scored-session record: the contract between the dynamic harness and the improvement loop (issue #3).

One record per (case, repeat) session. The harness writes them as JSON lines (`sessions.jsonl` in a run directory,
next to `run.json` with the run's metadata); triage, decide and the ledger read them. Fields are only ever added,
never renamed; bump RECORD_VERSION on any change of meaning.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

RECORD_VERSION = 1
BEHAVIOURS = ("answer", "ask", "either")


@dataclass
class Usage:
    input_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0

    @property
    def context_tokens(self) -> int:
        return self.input_tokens + self.cache_creation_tokens + self.cache_read_tokens


@dataclass
class Loaded:
    """One artifact that entered the session's context, in order."""

    kind: str
    """instructions | rule | skill | agent | file | mcp-tool"""
    name: str
    """Path relative to the checkout for files, rules and instructions; the name for skills, agents and tools."""
    turn: int
    """0 for what was present at start, else the assistant turn that loaded it."""
    tokens: int = 0


@dataclass
class SessionRecord:
    run_id: str
    case_id: str
    domain: str
    cluster: str
    """The unit cases are clustered by for statistics: the target skill if the case has one, else the domain."""
    repeat: int
    split: str
    """tune | holdout (stats.is_holdout)"""
    behaviour: str
    """The case's label: answer | ask | either."""
    asked: bool
    """The session ended asking the user for clarification instead of answering."""
    loaded: list[Loaded] = field(default_factory=list)
    skills_used: list[str] = field(default_factory=list)
    must_use_hit: list[str] = field(default_factory=list)
    must_use_missed: list[str] = field(default_factory=list)
    must_not_use_hit: list[str] = field(default_factory=list)
    leaked_artifacts: list[str] = field(default_factory=list)
    """Loaded artifacts owned by another domain (domains.toml)."""
    answer_leaks: list[str] = field(default_factory=list)
    """must_not_mention patterns or other domains' terms found in the answer."""
    expect_pass: bool | None = None
    criteria: dict[str, bool | None] = field(default_factory=dict)
    """Judge verdict per criterion id; None when the judge abstained or the criterion is not validated."""
    answer: str = ""
    start_tokens: int = 0
    usage: Usage = field(default_factory=Usage)
    cost_usd: float = 0.0
    turns: int = 0
    error: str = ""
    """Non-empty when the session itself failed (timeout, crash): a `harness` failure, never scored as a model miss."""
    contaminated: list[str] = field(default_factory=list)
    """Paths under the harness directory or the run directory that the session looked at; such a session is void."""
    version: int = RECORD_VERSION

    @property
    def criteria_pass_rate(self) -> float | None:
        graded = [v for v in self.criteria.values() if v is not None]
        return sum(graded) / len(graded) if graded else None

    @property
    def behaviour_ok(self) -> bool:
        return self.behaviour == "either" or (self.behaviour == "ask") == self.asked

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict) -> SessionRecord:
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"unknown session record fields: {sorted(unknown)}")
        data = dict(data)
        data["usage"] = Usage(**data.get("usage", {}))
        data["loaded"] = [Loaded(**item) for item in data.get("loaded", [])]
        record = cls(**data)
        if record.behaviour not in BEHAVIOURS:
            raise ValueError(f"{record.case_id}: behaviour {record.behaviour!r} not in {BEHAVIOURS}")
        if record.split not in ("tune", "holdout"):
            raise ValueError(f"{record.case_id}: split {record.split!r} is not tune or holdout")
        return record


def read_sessions(path: Path) -> list[SessionRecord]:
    return [SessionRecord.from_dict(json.loads(line)) for line in path.read_text().splitlines() if line.strip()]


def write_sessions(path: Path, records: list[SessionRecord]) -> None:
    path.write_text("".join(r.to_json() + "\n" for r in records))
