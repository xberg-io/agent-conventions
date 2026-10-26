"""The pre-registered accept rule of the improvement loop (issue #3, section 6, step 7).

`decide` compares N arm runs with one shared control run. An arm is accepted iff
- the primary metric (per-session criteria pass rate, or a binary session pass where no criterion was graded)
  improves on its target cases: lower bound > 0 and significant after Holm across all arms (p_not_greater);
- the primary metric over all cases is non-inferior: lower bound > -margin;
- every guardrail is non-inferior (lower bound of the improvement > -margin, higher is better): no leaked
  artifact, no answer leak, skill recall in other domains, no over-ask, no under-ask;
- mean start tokens grow by at most `token_budget` and stay under the optional absolute cap.
A check whose point estimate already fails (no target improvement, a guardrail mean at or below -margin, a Holm
miss, the token budget) rejects. When only bounds fail (positive target mean with lower bound <= 0, a guardrail mean
above -margin with lower bound below it) the arm is inconclusive and reports the repeats needed. Sessions with a harness error are left out of every
metric: they are not a model miss.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Callable, Collection, Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from statistics import fmean

import stats
from records import SessionRecord, read_sessions
from triage import is_failure

VERSION_KEYS = ("judge_version", "rubric_version")
DECISIONS = ("accept", "reject", "inconclusive")
PLACEBO_FALSE_ACCEPT_LIMIT = 0.05


@dataclass
class Run:
    name: str
    meta: dict
    records: list[SessionRecord]

    @classmethod
    def load(cls, path: Path) -> Run:
        meta = json.loads((path / "run.json").read_text())
        return cls(path.name, meta, read_sessions(path / "sessions.jsonl"))


@dataclass(frozen=True)
class Rule:
    alpha: float = 0.05
    margin: float = 0.02
    token_budget: float = 0.05
    """Largest allowed relative growth of mean start tokens per change."""
    token_cap: float | None = None
    """Optional absolute ceiling on the arm's mean start tokens."""
    resamples: int = stats.DEFAULT_RESAMPLES
    seed: int = 0


Score = Callable[[SessionRecord], float | None]


def primary(record: SessionRecord) -> float:
    rate = record.criteria_pass_rate
    return rate if rate is not None else float(not is_failure(record))


def _absent(values: list[str]) -> float:
    return 0.0 if values else 1.0


def guardrails(target_domains: set[str]) -> dict[str, Score]:
    def recall_other(r: SessionRecord) -> float | None:
        wanted = len(r.must_use_hit) + len(r.must_use_missed)
        if r.domain in target_domains or not wanted:
            return None
        return len(r.must_use_hit) / wanted

    return {
        "leak": lambda r: _absent(r.leaked_artifacts),
        "answer_leak": lambda r: _absent(r.answer_leaks),
        "recall_other": recall_other,
        "over_ask": lambda r: float(not r.asked) if r.behaviour == "answer" else None,
        "under_ask": lambda r: float(r.asked) if r.behaviour == "ask" else None,
    }


def per_case(
    records: Iterable[SessionRecord], score: Score, cases: Collection[str] | None = None
) -> dict[str, list[float]]:
    out: dict[str, list[float]] = defaultdict(list)
    for record in records:
        if record.error or (cases is not None and record.case_id not in cases):
            continue
        value = score(record)
        if value is not None:
            out[record.case_id].append(value)
    return dict(out)


def mean_start_tokens(records: Iterable[SessionRecord]) -> float:
    values = [r.start_tokens for r in records if not r.error]
    return fmean(values) if values else 0.0


def resolve_target(spec: str, records: Iterable[SessionRecord]) -> frozenset[str]:
    """`cases:a,b` names case ids, `domain:x` a domain, `cluster:x` or a bare name a statistics cluster."""
    kind, _, value = spec.partition(":") if ":" in spec else ("cluster", "", spec)
    if kind == "cases":
        found = frozenset(v for v in value.split(",") if v)
    elif kind in ("cluster", "domain"):
        found = frozenset(r.case_id for r in records if getattr(r, kind) == value)
    else:
        raise ValueError(f"target {spec!r}: kind must be cases, domain or cluster")
    if not found:
        raise ValueError(f"target {spec!r} matches no case")
    return found


def check_versions(runs: Iterable[Run]) -> None:
    runs = list(runs)
    for key in VERSION_KEYS:
        values = {run.meta.get(key) for run in runs}
        if None in values or len(values) != 1:
            names = {run.name: run.meta.get(key) for run in runs}
            raise ValueError(f"runs disagree on {key} or lack it, refusing to compare: {names}")


@dataclass
class ArmDecision:
    arm: str
    target: list[str]
    decision: str
    reasons: list[str]
    metrics: dict[str, stats.Interval | None]
    holm_significant: bool
    start_tokens: dict[str, float]
    regressed: list[tuple[str, float]] = field(default_factory=list)
    """Per-case Pareto check: (case, change of its mean primary score) for every case that got worse."""
    repeats: float = 0.0
    repeats_needed: int | None = None

    def to_dict(self, alpha: float = 0.05) -> dict:
        data = asdict(self)
        for name, interval in self.metrics.items():
            if interval is not None:
                data["metrics"][name]["mde"] = interval.mde(alpha)
        return data


def _interval(control: dict, arm: dict, clusters: dict[str, str], rule: Rule) -> stats.Interval | None:
    try:
        return stats.paired_cluster_bootstrap(
            control, arm, clusters, alpha=rule.alpha, resamples=rule.resamples, seed=rule.seed
        )
    except ValueError:
        return None


def _regressed(control: dict[str, list[float]], arm: dict[str, list[float]]) -> list[tuple[str, float]]:
    out = []
    for case in sorted(set(control) & set(arm)):
        delta = fmean(arm[case]) - fmean(control[case])
        if delta < 0:
            out.append((case, delta))
    return out


def _mean_repeats(*runs: dict[str, list[float]]) -> float:
    counts = [len(v) for run in runs for v in run.values()]
    return fmean(counts) if counts else 0.0


def _evaluate(control: Run, arm: Run, target: frozenset[str], rule: Rule) -> ArmDecision:
    clusters = {r.case_id: r.cluster for r in control.records + arm.records}
    target_domains = {r.domain for r in control.records if r.case_id in target}
    base_target, arm_target = per_case(control.records, primary, target), per_case(arm.records, primary, target)
    base_all, arm_all = per_case(control.records, primary), per_case(arm.records, primary)
    metrics = {
        "primary_target": _interval(base_target, arm_target, clusters, rule),
        "primary_overall": _interval(base_all, arm_all, clusters, rule),
    }
    for name, score in guardrails(target_domains).items():
        metrics[name] = _interval(per_case(control.records, score), per_case(arm.records, score), clusters, rule)
    base_tokens, arm_tokens = mean_start_tokens(control.records), mean_start_tokens(arm.records)
    growth = arm_tokens / base_tokens - 1 if base_tokens else 0.0
    return ArmDecision(
        arm=arm.name,
        target=sorted(target),
        decision="",
        reasons=[],
        metrics=metrics,
        holm_significant=False,
        start_tokens={"control": base_tokens, "arm": arm_tokens, "growth": growth},
        regressed=_regressed(base_all, arm_all),
        repeats=_mean_repeats(base_target, arm_target),
    )


def _repeats_for(result: ArmDecision, interval: stats.Interval, effect: float, rule: Rule) -> int:
    # The standard error shrinks roughly with the square root of the repeats.
    return math.ceil(result.repeats * (interval.mde(rule.alpha) / effect) ** 2)


def _verdict(result: ArmDecision, rule: Rule) -> None:
    """Reject on a failed check whose point estimate already fails; inconclusive when only the bounds do."""
    target = result.metrics["primary_target"]
    blocking, underpowered, needed = [], [], []
    if target is None:
        blocking.append("no target case was run by both control and arm")
    elif target.mean <= 0:
        blocking.append(f"primary_target: no improvement (mean {target.mean:+.4f})")
    elif target.lo > 0 and not result.holm_significant:
        blocking.append(f"primary_target: not significant after Holm (p {target.p_not_greater:.4f})")
    elif target.lo <= 0:
        underpowered.append(f"primary_target: lower bound {target.lo:+.4f} <= 0 (mean {target.mean:+.4f})")
        needed.append(_repeats_for(result, target, target.mean, rule))
    for name, iv in result.metrics.items():
        if name == "primary_target" or iv is None or iv.lo > -rule.margin:
            continue
        message = f"{name}: not non-inferior (lower bound {iv.lo:+.4f} <= -{rule.margin}, mean {iv.mean:+.4f})"
        if iv.mean <= -rule.margin:
            blocking.append(message)
        else:
            underpowered.append(message)
            needed.append(_repeats_for(result, iv, iv.mean + rule.margin, rule))
    tokens = result.start_tokens
    if tokens["growth"] > rule.token_budget:
        blocking.append(f"start tokens: +{tokens['growth']:.1%} over the +{rule.token_budget:.0%} budget")
    if rule.token_cap is not None and tokens["arm"] > rule.token_cap:
        blocking.append(f"start tokens: {tokens['arm']:.0f} over the cap {rule.token_cap:.0f}")
    if blocking:
        result.decision, result.reasons = "reject", blocking
    elif underpowered:
        result.repeats_needed = max(needed)
        result.decision = "inconclusive"
        result.reasons = [*underpowered, f"about {result.repeats_needed} repeats needed"]
    else:
        result.decision, result.reasons = "accept", ["all checks passed"]


def decide(
    control: Run, arms: list[Run], targets: list[Collection[str]], rule: Rule | None = None
) -> list[ArmDecision]:
    """Decide every arm against the shared control; `targets[i]` holds the target case ids of `arms[i]`."""
    rule = rule or Rule()
    if len(arms) != len(targets):
        raise ValueError(f"{len(arms)} arms but {len(targets)} targets")
    if len({arm.name for arm in arms}) != len(arms):
        raise ValueError("arm names must be distinct")
    check_versions([control, *arms])
    results = [_evaluate(control, arm, frozenset(t), rule) for arm, t in zip(arms, targets, strict=True)]
    pvalues = {r.arm: r.metrics["primary_target"].p_not_greater for r in results if r.metrics["primary_target"]}
    significant = stats.holm(pvalues, rule.alpha)
    for result in results:
        result.holm_significant = significant.get(result.arm, False)
        _verdict(result, rule)
    return results


def calibrate_placebo(decisions: Iterable[str], limit: float = PLACEBO_FALSE_ACCEPT_LIMIT) -> dict[str, object]:
    """False-accept rate of past placebo arms; `flagged` when it exceeds `limit`."""
    decisions = list(decisions)
    unknown = set(decisions) - set(DECISIONS)
    if unknown:
        raise ValueError(f"unknown decisions: {sorted(unknown)}")
    accepted = decisions.count("accept")
    rate = accepted / len(decisions) if decisions else 0.0
    return {"placebos": len(decisions), "accepted": accepted, "rate": rate, "flagged": rate > limit}


def to_markdown(results: list[ArmDecision]) -> str:
    lines = ["# Decision", ""]
    for result in results:
        lines += [f"## {result.arm}: {result.decision}", ""]
        lines += [f"- {reason}" for reason in result.reasons]
        lines += ["", "| metric | mean | lo | hi | p |", "| --- | --- | --- | --- | --- |"]
        for name, iv in result.metrics.items():
            row = (
                "no data | | | |"
                if iv is None
                else f"{iv.mean:+.4f} | {iv.lo:+.4f} | {iv.hi:+.4f} | {iv.p_not_greater:.4f} |"
            )
            lines.append(f"| {name} | {row}")
        tokens = result.start_tokens
        lines += ["", f"Start tokens: {tokens['control']:.0f} -> {tokens['arm']:.0f} ({tokens['growth']:+.1%})"]
        if result.regressed:
            lines.append("Regressed cases: " + ", ".join(f"{case} ({delta:+.3f})" for case, delta in result.regressed))
        lines.append("")
    return "\n".join(lines)
