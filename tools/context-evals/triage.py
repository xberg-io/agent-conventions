"""Failure triage for one run of the dynamic harness (issue #3, section 6, step 2).

Every failing session gets deterministic pre-labels from its scores; the rest can be coded by an LLM against a
versioned taxonomy through an injected `coder(prompt) -> str`. Artifacts are ranked per domain by spectrum-based fault
localisation (Ochiai over the artifacts loaded in failing versus passing sessions of that domain), and failures are
clustered by (cause, most suspicious artifact) so one cluster becomes one hypothesis.
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field

from records import SessionRecord

TAXONOMY_VERSION = "1"
TAXONOMY = {
    "missing": "missing knowledge: no loaded artifact carries what the answer needed",
    "wrong": "wrong or stale content: a loaded artifact states something false or outdated",
    "ignored": "ignored instruction: the right instruction was loaded but not followed",
    "noise": "noise or distractor: an irrelevant loaded artifact pulled the answer off course",
    "case": "case defect: the case, its criteria or its expected behaviour is wrong",
}
PRE_LABELS = ("harness", "sandbox_limit", "answer_leak", "wrong_skill", "not_found", "over_ask", "under_ask")
"""In precedence order: the first label a session carries is its cause."""
UNLABELLED = "unlabelled"
NO_ARTIFACT = "-"


def failure_reasons(record: SessionRecord) -> list[str]:
    reasons = []
    if record.error:
        reasons.append("error")
    if not record.behaviour_ok:
        reasons.append("behaviour")
    if record.must_use_missed:
        reasons.append("must_use_missed")
    if record.must_not_use_hit:
        reasons.append("must_not_use_hit")
    if record.answer_leaks:
        reasons.append("answer_leaks")
    if record.expect_pass is False:
        reasons.append("expect_failed")
    rate = record.criteria_pass_rate
    if rate is not None and rate < 1:
        reasons.append("criteria")
    return reasons


def is_failure(record: SessionRecord) -> bool:
    return bool(failure_reasons(record))


def pre_labels(record: SessionRecord, sandbox: Mapping[str, str] | None = None) -> list[str]:
    """Deterministic labels in PRE_LABELS order; `sandbox` maps case id to the case's sandbox kind."""
    if record.error:
        return ["harness"]
    labels = []
    if record.expect_pass is False and (sandbox or {}).get(record.case_id) == "procedure":
        labels.append("sandbox_limit")
    if record.answer_leaks:
        labels.append("answer_leak")
    must_use = set(record.must_use_hit) | set(record.must_use_missed)
    if record.must_not_use_hit or (must_use and set(record.skills_used) - must_use):
        labels.append("wrong_skill")
    if record.must_use_missed:
        labels.append("not_found")
    if record.behaviour == "answer" and record.asked:
        labels.append("over_ask")
    if record.behaviour == "ask" and not record.asked:
        labels.append("under_ask")
    return labels


@dataclass
class Suspicion:
    artifact: str
    score: float
    failed: int
    passed: int


def artifacts(record: SessionRecord) -> set[str]:
    return {f"{item.kind}:{item.name}" for item in record.loaded}


def suspiciousness(records: list[SessionRecord]) -> dict[str, list[Suspicion]]:
    """Ochiai per domain: failed(a) / sqrt(total_failed * (failed(a) + passed(a))), highest first.

    Harness failures are left out: they say nothing about the context.
    """
    by_domain: dict[str, list[SessionRecord]] = defaultdict(list)
    for record in records:
        if not record.error:
            by_domain[record.domain].append(record)
    ranking = {}
    for domain, sessions in sorted(by_domain.items()):
        failed: dict[str, int] = defaultdict(int)
        passed: dict[str, int] = defaultdict(int)
        total_failed = 0
        for record in sessions:
            fails = is_failure(record)
            total_failed += fails
            for artifact in artifacts(record):
                (failed if fails else passed)[artifact] += 1
        rows = []
        for artifact in set(failed) | set(passed):
            denominator = math.sqrt(total_failed * (failed[artifact] + passed[artifact]))
            score = failed[artifact] / denominator if denominator else 0.0
            rows.append(Suspicion(artifact, score, failed[artifact], passed[artifact]))
        rows.sort(key=lambda s: (-s.score, -s.failed, s.artifact))
        ranking[domain] = rows
    return ranking


@dataclass
class SessionTriage:
    case_id: str
    repeat: int
    domain: str
    reasons: list[str]
    labels: list[str]
    cause: str
    artifact: str
    coder_raw: str = ""


@dataclass
class Cluster:
    cause: str
    artifact: str
    sessions: int
    cases: list[str]


@dataclass
class Triage:
    taxonomy_version: str
    total: int
    failing: int
    sessions: list[SessionTriage] = field(default_factory=list)
    suspiciousness: dict[str, list[Suspicion]] = field(default_factory=dict)
    clusters: list[Cluster] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    def to_markdown(self) -> str:
        lines = [
            f"# Triage ({self.failing} of {self.total} sessions failing, taxonomy v{self.taxonomy_version})",
            "",
            "## Clusters",
            "",
            "| cause | artifact | sessions | cases |",
            "| --- | --- | --- | --- |",
        ]
        lines += [f"| {c.cause} | {c.artifact} | {c.sessions} | {', '.join(c.cases)} |" for c in self.clusters]
        lines += ["", "## Suspicious artifacts", "", "| domain | artifact | ochiai | failed | passed |"]
        lines.append("| --- | --- | --- | --- | --- |")
        for domain, rows in self.suspiciousness.items():
            lines += [f"| {domain} | {s.artifact} | {s.score:.3f} | {s.failed} | {s.passed} |" for s in rows]
        return "\n".join(lines) + "\n"


def coding_prompt(record: SessionRecord, reasons: list[str]) -> str:
    failed = sorted(k for k, v in record.criteria.items() if v is False)
    loaded = ", ".join(f"{i.kind}:{i.name}" for i in record.loaded) or "none"
    codes = "\n".join(f"- {code}: {meaning}" for code, meaning in TAXONOMY.items())
    return (
        f"Classify why this agent session failed (taxonomy v{TAXONOMY_VERSION}). Reply with one code first.\n"
        f"{codes}\n\n"
        f"Case: {record.case_id} (domain {record.domain}, expected behaviour {record.behaviour})\n"
        f"Failure reasons: {', '.join(reasons)}\n"
        f"Failed criteria: {', '.join(failed) or 'none'}\n"
        f"Loaded artifacts: {loaded}\n"
        f"Answer:\n{record.answer}\n"
    )


def parse_code(reply: str) -> str:
    match = re.match(r"\W*([a-z]+)", reply.lower())
    return match.group(1) if match and match.group(1) in TAXONOMY else UNLABELLED


def top_artifact(record: SessionRecord, ranking: dict[str, list[Suspicion]]) -> str:
    loaded = artifacts(record)
    for row in ranking.get(record.domain, []):
        if row.artifact in loaded:
            return row.artifact
    return NO_ARTIFACT


def triage(
    records: list[SessionRecord],
    *,
    sandbox: Mapping[str, str] | None = None,
    coder: Callable[[str], str] | None = None,
) -> Triage:
    ranking = suspiciousness(records)
    result = Triage(TAXONOMY_VERSION, total=len(records), failing=0, suspiciousness=ranking)
    for record in records:
        reasons = failure_reasons(record)
        if not reasons:
            continue
        labels = pre_labels(record, sandbox)
        cause = labels[0] if labels else UNLABELLED
        raw = ""
        if cause == UNLABELLED and coder is not None:
            raw = coder(coding_prompt(record, reasons))
            cause = parse_code(raw)
        if cause == "harness":
            artifact = NO_ARTIFACT
        elif cause == "not_found":
            # The defect is in the description of the skill that never loaded, not in what did load.
            artifact = f"skill:{record.must_use_missed[0]}"
        else:
            artifact = top_artifact(record, ranking)
        result.sessions.append(
            SessionTriage(record.case_id, record.repeat, record.domain, reasons, labels, cause, artifact, raw)
        )
    result.failing = len(result.sessions)
    grouped: dict[tuple[str, str], list[SessionTriage]] = defaultdict(list)
    for session in result.sessions:
        grouped[(session.cause, session.artifact)].append(session)
    result.clusters = sorted(
        (
            Cluster(cause, artifact, len(group), sorted({s.case_id for s in group}))
            for (cause, artifact), group in grouped.items()
        ),
        key=lambda c: (-c.sessions, c.cause, c.artifact),
    )
    return result
