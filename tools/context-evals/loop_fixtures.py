"""Synthetic session records and run directories for the improvement-loop tests."""

from __future__ import annotations

import json
from pathlib import Path

from records import Loaded, SessionRecord, write_sessions

RUN_META = {"repo": "repo", "ref": "base", "model": "m", "judge_version": "j1", "rubric_version": "r1"}


def rec(
    case: str,
    repeat: int = 0,
    *,
    domain: str = "d",
    cluster: str | None = None,
    behaviour: str = "answer",
    asked: bool = False,
    loaded: tuple[str, ...] = (),
    criteria: dict[str, bool | None] | None = None,
    split: str = "tune",
    **fields: object,
) -> SessionRecord:
    """A record; `loaded` items are `kind:name` strings."""
    items = [Loaded(kind=k, name=n, turn=0) for k, n in (item.split(":", 1) for item in loaded)]
    return SessionRecord(
        run_id="run",
        case_id=case,
        domain=domain,
        cluster=cluster or domain,
        repeat=repeat,
        split=split,
        behaviour=behaviour,
        asked=asked,
        loaded=items,
        criteria=criteria if criteria is not None else {"c1": True},
        **fields,
    )


def scored(case: str, scores: list[float], **kw: object) -> list[SessionRecord]:
    """One record per repeat whose criteria pass rate is the given score (quarters: 4 criteria)."""
    out = []
    for i, score in enumerate(scores):
        passed = round(score * 4)
        criteria = {f"c{j}": j < passed for j in range(4)}
        out.append(rec(case, i, criteria=criteria, **kw))
    return out


def write_run(root: Path, name: str, records: list[SessionRecord], **meta: object) -> Path:
    run = root / name
    run.mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({**RUN_META, **meta}))
    write_sessions(run / "sessions.jsonl", records)
    return run
