"""Holdout read budget, checkpoints and the stop rule of the improvement loop (issue #3, section 6, step 9).

The holdout split is read only at checkpoints, every `CHECKPOINT_EVERY` accepted changes (counted from the ledger),
and at most `DEFAULT_CAP` times per harness version; every read is recorded in a small JSON state file. A checkpoint
compares a candidate's holdout sessions with the last verified tip: progress only when the improvement is at least the
minimum detectable effect, revert when it is a regression, plateau otherwise.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import stats
from decide import Run, check_versions, per_case, primary
from ledger import accepted_changes

DEFAULT_CAP = 5
CHECKPOINT_EVERY = 3
DEFAULT_STATE = Path(__file__).parent / "holdout-state.json"


class BudgetExhausted(RuntimeError):
    pass


class NotDue(RuntimeError):
    pass


def _load(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def _version_state(state: dict, harness_version: str) -> dict:
    return state.get(harness_version, {"reads": 0, "accepted_at_last_read": 0, "tip": "", "checkpoints": []})


def status(
    path: Path, entries: list[dict], harness_version: str, *, cap: int = DEFAULT_CAP, every: int = CHECKPOINT_EVERY
) -> dict:
    current = _version_state(_load(path), harness_version)
    accepted = accepted_changes(entries)
    remaining = max(cap - current["reads"], 0)
    return {
        "harness_version": harness_version,
        "reads": current["reads"],
        "cap": cap,
        "remaining": remaining,
        "accepted": accepted,
        "accepted_at_last_read": current["accepted_at_last_read"],
        "due": remaining > 0 and accepted - current["accepted_at_last_read"] >= every,
        "tip": current["tip"],
        "checkpoints": current["checkpoints"],
    }


def verdict(interval: stats.Interval, alpha: float) -> str:
    if interval.hi < 0:
        return "revert"
    if interval.mean > 0 and interval.mean >= interval.mde(alpha):
        return "progress"
    return "plateau"


def checkpoint(
    path: Path,
    entries: list[dict],
    harness_version: str,
    tip: Run,
    candidate: Run,
    *,
    cap: int = DEFAULT_CAP,
    every: int = CHECKPOINT_EVERY,
    force: bool = False,
    alpha: float = 0.05,
    seed: int = 0,
) -> dict:
    """Compare `candidate` with the last verified `tip` on the holdout split and record the read.

    `force` skips the every-N-accepts schedule, never the cap.
    """
    current = status(path, entries, harness_version, cap=cap, every=every)
    if current["remaining"] == 0:
        raise BudgetExhausted(f"holdout read budget for harness {harness_version} is spent ({current['reads']}/{cap})")
    if not current["due"] and not force:
        since = current["accepted"] - current["accepted_at_last_read"]
        raise NotDue(f"{since} accepted changes since the last holdout read; a checkpoint is due every {every}")
    check_versions([tip, candidate])
    base = per_case((r for r in tip.records if r.split == "holdout"), primary)
    arm = per_case((r for r in candidate.records if r.split == "holdout"), primary)
    if not base or not arm:
        raise ValueError("tip and candidate both need scored holdout sessions")
    clusters = {r.case_id: r.cluster for r in tip.records + candidate.records}
    interval = stats.paired_cluster_bootstrap(base, arm, clusters, alpha=alpha, seed=seed)
    result = {
        "verdict": verdict(interval, alpha),
        "interval": asdict(interval),
        "mde": interval.mde(alpha),
        "tip_ref": tip.meta.get("ref", tip.name),
        "candidate_ref": candidate.meta.get("ref", candidate.name),
        "accepted": current["accepted"],
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    state = _load(path)
    version = _version_state(state, harness_version)
    version["reads"] += 1
    version["accepted_at_last_read"] = current["accepted"]
    version["tip"] = (
        result["candidate_ref"] if result["verdict"] == "progress" else (version["tip"] or result["tip_ref"])
    )
    version["checkpoints"].append(result)
    state[harness_version] = version
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    return result


def stop_condition(entries: list[dict], checkpoints: list[dict] | None = None) -> tuple[bool, str]:
    """Stop after the last two rounds accepted nothing, or when the last holdout checkpoint was a plateau."""
    rounds = sorted({e["round"] for e in entries})
    if len(rounds) >= 2:
        last = rounds[-2:]
        if not accepted_changes([e for e in entries if e["round"] in last]):
            return True, f"rounds {last[0]} and {last[1]} accepted nothing"
    if checkpoints and checkpoints[-1]["verdict"] == "plateau":
        return True, "holdout plateau"
    return False, ""
