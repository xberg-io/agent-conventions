"""Score parsed sessions into SessionRecords and aggregate them per domain (issue #3, section 5.2).

A loaded artifact leaks when it belongs to a domain the case's repo (and the case's own domain) does not own:
by path (domains.toml `paths`) for every artifact, and by text (domain `terms`) for context artifacts, i.e.
instructions, rules, skills and agents. Files the session read are judged by path only: source code legitimately
mentions neighbouring products, while a rule or skill that does is routing knowledge into the wrong session.
The domains.toml accept list applies, with the artifact named as exposure.py names it.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import exposure
import stats
import tool_unavailable
import transcript
from cases import Case
from records import RECORD_VERSION, Loaded, SessionRecord, Usage
from transcript import Transcript

CONTEXT_KINDS = ("instructions", "rule", "skill", "agent")


@dataclass(frozen=True)
class Metric:
    name: str
    value: Callable[[SessionRecord], float | None]
    higher_is_better: bool


def owned_domains(case: Case, domains: dict) -> set[str]:
    return {case.domain, *domains.get("repos", {}).get(case.repo, {}).get("domains", [])}


def path_domains(path: str, domains: dict) -> set[str]:
    """Domains whose `paths` cover a repo-relative path (a trailing `/` covers the whole directory)."""
    out = set()
    for name, spec in domains.get("domain", {}).items():
        for pattern in spec.get("paths", []):
            glob = pattern + "**" if pattern.endswith("/") else pattern
            if transcript.glob_regex(glob).match(path):
                out.add(name)
    return out


def foreign_terms(text: str, owned: set[str], domains: dict, accept: list[dict], artifact: str, repo: str) -> list[str]:
    """`domain:term` for every foreign domain term in `text` that the accept list does not cover."""
    hits = []
    for name, spec in domains.get("domain", {}).items():
        if name in owned:
            continue
        for term in spec.get("terms", []):
            if exposure.term_pattern(term).search(text) and not exposure.is_accepted(accept, term, artifact, repo):
                hits.append(f"{name}:{term}")
    return hits


def artifact_name(item: Loaded) -> str:
    return f"{item.kind}:{item.name}" if item.kind in ("skill", "agent") else item.name


def artifact_text(item: Loaded, context: Path) -> str:
    if item.kind == "skill":
        file = transcript.skill_file(context, item.name)
        return exposure.read(file) if file else item.name
    if item.kind in ("instructions", "rule"):
        path = context / item.name
        return exposure.read(path) if path.is_file() else ""
    return ""


def leaked_artifacts(loaded: list[Loaded], case: Case, domains: dict, context: Path) -> list[str]:
    owned = owned_domains(case, domains)
    accept = domains.get("accept", [])
    leaked: list[str] = []
    for item in loaded:
        name = artifact_name(item)
        foreign_path = item.kind not in ("skill", "agent") and path_domains(item.name, domains) - owned
        text = artifact_text(item, context) if item.kind in CONTEXT_KINDS else ""
        foreign_text = text and foreign_terms(text, owned, domains, accept, name, case.repo)
        if (foreign_path or foreign_text) and name not in leaked:
            leaked.append(name)
    return leaked


def answer_leaks(answer: str, case: Case, domains: dict) -> list[str]:
    hits = [p for p in case.must_not_mention if re.search(p, answer)]
    return hits + foreign_terms(
        answer, owned_domains(case, domains), domains, domains.get("accept", []), "answer", case.repo
    )


def start_tokens(t: Transcript, context: Path) -> int:
    """Context tokens of the first model call; the static estimate when the transcript has no usage."""
    if t.first_usage is not None and t.first_usage.context_tokens:
        return t.first_usage.context_tokens
    return int(exposure.claude(context).summary()["start_tokens"])


def classified_outcome(t: Transcript, error: str, certified: bool, contaminated: list) -> tuple[str, str, bool]:
    error = error or t.error or ("contaminated" if contaminated else "")
    unavailable = certified is True and error == "tool_unavailable" and t.answer == tool_unavailable.API_ERROR
    answer = "" if unavailable else t.answer
    bounded = certified is True and error in ("error_max_turns", "tool_unavailable") and not contaminated and not answer
    return error, answer, bounded


def score(
    case: Case,
    t: Transcript,
    domains: dict,
    context: Path,
    *,
    run_id: str,
    repeat: int,
    run_dir: str = "",
    error: str = "",
    root: str | None = None,
    bounded_failure: bool = False,
    provenance: dict | None = None,
) -> SessionRecord:
    """Score one transcript; only a controller certificate can mark a bounded task failure."""
    root = transcript.session_root(t, case.cwd) if root is None else root
    loaded = transcript.inventory(t, context, case.cwd, root)
    used = list(dict.fromkeys(name for name, _ in t.skills_used()))
    contaminated = transcript.contaminated(t, root, run_dir)
    error, answer, bounded = classified_outcome(t, error, bounded_failure, contaminated)
    return SessionRecord(
        run_id=run_id,
        case_id=case.id,
        domain=case.domain,
        cluster=case.cluster,
        repeat=repeat,
        split=case.split,
        behaviour=case.behaviour,
        asked=transcript.asked(answer),
        loaded=loaded,
        skills_used=used,
        must_use_hit=[s for s in case.must_use if s in used],
        must_use_missed=[s for s in case.must_use if s not in used],
        must_not_use_hit=[s for s in case.must_not_use if s in used],
        leaked_artifacts=leaked_artifacts(loaded, case, domains, context),
        answer_leaks=answer_leaks(answer, case, domains),
        expect_pass=all(re.search(p, answer) for p in case.expect) if case.expect and not error else None,
        criteria={c.id: None for c in case.criteria},
        answer=answer,
        start_tokens=start_tokens(t, context),
        usage=t.usage if t.usage != Usage() else (t.first_usage or Usage()),
        cost_usd=t.cost_usd,
        turns=t.turns or t.assistant_turns,
        error=error,
        contaminated=contaminated,
        bounded_failure=bounded,
        expect_applicable=bool(case.expect),
        provenance=provenance or {},
    )


def _recall(r: SessionRecord) -> float | None:
    wanted = len(r.must_use_hit) + len(r.must_use_missed)
    return len(r.must_use_hit) / wanted if wanted else None


def _precision(r: SessionRecord) -> float | None:
    if not r.skills_used:
        return None
    good = [s for s in r.skills_used if s not in r.must_not_use_hit and f"skill:{s}" not in r.leaked_artifacts]
    return len(good) / len(r.skills_used)


METRICS = (
    Metric("skill_recall", _recall, True),
    Metric("skill_precision", _precision, True),
    Metric("leak_rate", lambda r: float(bool(r.leaked_artifacts)), False),
    Metric("answer_leak_rate", lambda r: float(bool(r.answer_leaks)), False),
    Metric("over_ask_rate", lambda r: float(r.asked) if r.behaviour == "answer" else None, False),
    Metric("under_ask_rate", lambda r: float(not r.asked) if r.behaviour == "ask" else None, False),
    Metric("expect_pass_rate", lambda r: None if r.expect_pass is None else float(r.expect_pass), True),
    Metric("criteria_pass_rate", lambda r: r.criteria_pass_rate, True),
    Metric("start_tokens", lambda r: float(r.start_tokens), False),
    Metric("cost_usd", lambda r: r.cost_usd, False),
)
METRIC_BY_NAME = {m.name: m for m in METRICS}


def per_case(records: list[SessionRecord], metric: Metric) -> dict[str, list[float]]:
    """Scores per case over its repeats; failed sessions and inapplicable metrics are left out."""
    out: dict[str, list[float]] = {}
    for r in records:
        if r.error:
            continue
        value = metric.value(r)
        if value is not None:
            out.setdefault(r.case_id, []).append(value)
    return out


def valid_trial(record: SessionRecord) -> bool:
    if type(record.version) is not int or record.version != RECORD_VERSION:
        return False
    if record.contaminated:
        return False
    if not record.error:
        return not record.bounded_failure
    return (
        record.error in ("error_max_turns", "tool_unavailable") and record.bounded_failure is True and not record.answer
    )


def trial_rate(rows: list[SessionRecord], value: Callable[[SessionRecord], float | None]) -> dict:
    values = [0.0 if row.bounded_failure else value(row) for row in rows]
    missing = sum(item is None for item in values)
    numerator = sum(item for item in values if item is not None)
    return {
        "numerator": numerator,
        "denominator": len(rows),
        "rate": numerator / len(rows) if rows and not missing else None,
        "ungraded_trials": missing,
    }


def all_trials(records: list[SessionRecord]) -> dict:
    valid = [row for row in records if valid_trial(row)]
    invalid = [row for row in records if not valid_trial(row)]
    expectations = [row for row in valid if row.expect_applicable or row.expect_pass is not None]
    criteria = [row for row in valid if row.criteria]
    return {
        "version": 1,
        "executed_trials": len(records),
        "valid_trials": len(valid),
        "invalid_trials": len(invalid),
        "execution_valid": bool(records) and not invalid,
        "invalid_errors": dict(Counter(row.error or "invalid completion classification" for row in invalid)),
        "completion": trial_rate(valid, lambda _row: 1.0),
        "expect_pass": trial_rate(
            expectations, lambda row: float(row.expect_pass) if row.expect_pass is not None else None
        ),
        "criteria_pass": trial_rate(
            criteria,
            lambda row: row.criteria_pass_rate if all(value is not None for value in row.criteria.values()) else None,
        ),
    }


def summarise(records: list[SessionRecord], *, seed: int = 0) -> dict:
    clusters = {r.case_id: r.cluster for r in records}
    out: dict = {
        "sessions": len(records),
        "errors": sum(1 for r in records if r.error),
        "metrics": {},
        "all_trials": all_trials(records),
    }
    for metric in METRICS:
        values = per_case(records, metric)
        if not values:
            out["metrics"][metric.name] = None
            continue
        iv = stats.cluster_bootstrap(values, clusters, seed=seed)
        out["metrics"][metric.name] = {
            "mean": iv.mean,
            "lo": iv.lo,
            "hi": iv.hi,
            "cases": iv.cases,
            "clusters": iv.clusters,
            "sessions": sum(len(v) for v in values.values()),
        }
    return out


def aggregate(records: list[SessionRecord], *, seed: int = 0) -> dict:
    """Overall and per-domain summaries with clustered 95% intervals."""
    domains = sorted({r.domain for r in records})
    return {
        "overall": summarise(records, seed=seed),
        "domains": {d: summarise([r for r in records if r.domain == d], seed=seed) for d in domains},
    }
