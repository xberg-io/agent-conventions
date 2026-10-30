"""LLM grading of case criteria and validation of the grader (issue #3, section 5.2).

The grader is an injected callable `(prompt) -> text`; the real one runs `claude -p` hermetically. It must answer
with one JSON object `{"verdicts": {"<criterion id>": true | false | null}}`; null abstains, anything unparseable
abstains on every criterion.

A criterion's verdicts count only once the judge is validated for it:

- agreement: a second grader with an independently worded prompt grades the same answers (a stratified sample of
  sessions plus the reference answers and their mutants); a criterion is valid when Cohen's kappa >= 0.6 over at
  least MIN_ITEMS answers both graders decided.
- mutations: the reference answer (the case's reference facts) is perturbed: the sentence carrying the key (first) fact dropped,
  the domain's term swapped for another domain's, the answer replaced with a deflection to a tool, a path replaced
  with a wrong one. The primary grader must pass the originals (TPR) and fail the mutants (TNR).

Every verdict row and report records JUDGE_PROMPT_VERSION and RUBRIC_VERSION; results from different versions are
never compared.
"""

from __future__ import annotations

import json
import os
import random
import re
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path

import exposure
import runner
import stats
from cases import Case
from records import SessionRecord

JUDGE_PROMPT_VERSION = "judge-prompt-1"
INDEPENDENT_PROMPT_VERSION = "judge-prompt-independent-1"
RUBRIC_VERSION = "rubric-2"
KAPPA_MIN = 0.6
MIN_ITEMS = 4
TPR_MIN = 0.9
TNR_MIN = 0.8
TOOL_DEFLECTION = "Use tool X to find this out."
WRONG_PATH = "src/nonexistent/wrong_module.rs"
PATH = re.compile(r"(?<![\w/.-])[\w.-]+(?:/[\w.-]*[\w-])+")
WORD = re.compile(r"[a-z0-9_]{3,}|\d+")
STOPWORDS = {"the", "and", "for", "are", "with", "that", "this", "from", "uses", "use", "its", "has", "was", "not"}

Grader = Callable[[str], str]
Verdicts = dict[str, bool | None]

RUBRIC = """Grade each criterion independently as true (the answer clearly satisfies it), false (it does not, or \
contradicts the reference) or null (you cannot decide from the material given). Judge only the final answer; the \
reference is ground truth. Do not reward length, hedging or tool advice in place of a result."""


def _criteria_block(case: Case) -> str:
    return "\n".join(f"- {c.id}: {c.check}" for c in case.criteria)


def _reference_block(case: Case) -> str:
    facts = "\n".join(f"- {f}" for f in case.reference.facts) or "- (none)"
    sources = ", ".join(case.reference.sources) or "(none)"
    return f"Facts:\n{facts}\nSources: {sources}"


def _sandbox_note(case: Case) -> str:
    if case.sandbox == "procedure":
        return "The question concerns a live system the session could not reach: grade the procedure, not the data."
    return "Grade the result the answer gives."


def primary_prompt(case: Case, answer: str, summary: str) -> str:
    ids = ", ".join(c.id for c in case.criteria)
    return f"""You are grading an AI coding assistant's answer against binary criteria.
{RUBRIC}
{_sandbox_note(case)}

Question asked:
{case.prompt}

Reference:
{_reference_block(case)}

Session summary:
{summary or "(none)"}

Final answer:
<answer>
{answer}
</answer>

Criteria:
{_criteria_block(case)}

Reply with exactly one JSON object and nothing else:
{{"verdicts": {{<one key per criterion id: {ids}>: true | false | null}}}}"""


def independent_prompt(case: Case, answer: str, summary: str) -> str:
    """A second wording, ordered differently, so agreement is not an artefact of one prompt."""
    lines = [
        "Check a response for factual compliance. For every statement below decide whether the response satisfies it.",
        "Use the ground truth to decide; a response that only says how to find the answer does not satisfy a",
        "statement about the answer. Say null only when the statement cannot be decided.",
        _sandbox_note(case),
        "",
        "Statements:",
        _criteria_block(case),
        "",
        "Response under review:",
        "<<<",
        answer,
        ">>>",
        "",
        "Ground truth:",
        _reference_block(case),
        f"Request: {case.prompt}",
        "",
        'Output format: {"verdicts": {"<statement id>": true|false|null, ...}} as a single JSON object.',
    ]
    return "\n".join(lines)


PROMPTS = {"primary": primary_prompt, "independent": independent_prompt}


def parse_verdicts(text: str, ids: list[str]) -> Verdicts:
    """Strictly read `{"verdicts": {...}}`; a missing id or a non-boolean value abstains (None)."""
    out: Verdicts = dict.fromkeys(ids)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return out
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return out
    verdicts = data.get("verdicts") if isinstance(data, dict) else None
    if not isinstance(verdicts, dict):
        return out
    for key in ids:
        value = verdicts.get(key)
        out[key] = value if isinstance(value, bool) else None
    return out


def summary(record: SessionRecord) -> str:
    files = [i.name for i in record.loaded if i.kind == "file"]
    return "\n".join(
        [
            f"skills used: {', '.join(record.skills_used) or 'none'}",
            f"files read: {', '.join(files[:20]) or 'none'}" + (" ..." if len(files) > 20 else ""),
            f"turns: {record.turns}",
        ]
    )


def grade(case: Case, answer: str, grader: Grader, *, style: str = "primary", context: str = "") -> Verdicts:
    ids = [c.id for c in case.criteria]
    if not ids:
        return {}
    return parse_verdicts(grader(PROMPTS[style](case, answer, context)), ids)


def judge_sessions(records: list[SessionRecord], cases: dict[str, Case], grader: Grader, model: str) -> list[dict]:
    """Raw verdict rows for every session that ran and has criteria."""
    rows = []
    for r in records:
        case = cases.get(r.case_id)
        if r.error or case is None or not case.criteria:
            continue
        rows.append(
            {
                "case_id": r.case_id,
                "repeat": r.repeat,
                "verdicts": grade(case, r.answer, grader, context=summary(r)),
                "judge_model": model,
                "judge_prompt_version": JUDGE_PROMPT_VERSION,
                "rubric_version": RUBRIC_VERSION,
            }
        )
    return rows


def apply(records: list[SessionRecord], rows: list[dict], valid: set[str]) -> None:
    """Write verdicts into the records, keeping None for every criterion not in `valid` (`case/criterion`)."""
    by_session = {(row["case_id"], row["repeat"]): row["verdicts"] for row in rows}
    for r in records:
        verdicts = by_session.get((r.case_id, r.repeat), {})
        r.criteria = {cid: (verdicts.get(cid) if f"{r.case_id}/{cid}" in valid else None) for cid in r.criteria}


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+|\n+", text.strip()) if s.strip()]


def _words(text: str) -> set[str]:
    return set(WORD.findall(text.lower())) - STOPWORDS


def drop_fact(answer: str, facts: tuple[str, ...]) -> str | None:
    """Remove the sentence sharing most content words with the first (key) reference fact."""
    if not facts:
        return None
    sentences = _sentences(answer)
    overlap, index = max(((len(_words(s) & _words(facts[0])), -i) for i, s in enumerate(sentences)), default=(0, 0))
    if overlap == 0:
        return None
    return " ".join(s for i, s in enumerate(sentences) if i != -index)


def swap_domain(answer: str, case: Case, domains: dict) -> str | None:
    """Replace the case domain's terms with the first term of a domain the case's repo does not own."""
    owned = {case.domain, *domains.get("repos", {}).get(case.repo, {}).get("domains", [])}
    foreign = next((spec["terms"][0] for name, spec in sorted(domains.get("domain", {}).items())
                    if name not in owned and spec.get("terms")), None)  # fmt: skip
    if foreign is None:
        return None
    swapped = answer
    for term in domains.get("domain", {}).get(case.domain, {}).get("terms", []):
        swapped = exposure.term_pattern(term).sub(foreign, swapped)
    return swapped if swapped != answer else None


def wrong_path(answer: str) -> str | None:
    match = PATH.search(answer)
    if match is None:
        return None
    return answer[: match.start()] + WRONG_PATH + answer[match.end() :]


def mutants(answer: str, case: Case, domains: dict) -> dict[str, str]:
    candidates = {
        "drop-fact": drop_fact(answer, case.reference.facts),
        "swap-domain": swap_domain(answer, case, domains),
        "tool-deflection": TOOL_DEFLECTION,
        "wrong-path": wrong_path(answer),
    }
    return {kind: text for kind, text in candidates.items() if text is not None and text != answer}


def reference_answer(case: Case) -> str:
    return " ".join(case.reference.facts)


def stratified_sample(records: list[SessionRecord], per_domain: int, seed: int = 0) -> list[SessionRecord]:
    """Up to `per_domain` sessions per domain, spread over cases first, deterministic for a seed."""
    rng = random.Random(seed)
    out = []
    for domain in sorted({r.domain for r in records}):
        pool = sorted((r for r in records if r.domain == domain), key=lambda r: (r.case_id, r.repeat))
        rng.shuffle(pool)
        pool.sort(key=lambda r: r.repeat)
        out += pool[:per_domain]
    return out


def _both(case: Case, text: str, a: Grader, b: Grader, context: str = "") -> tuple[Verdicts, Verdicts]:
    return grade(case, text, a, context=context), grade(case, text, b, style="independent", context=context)


def validate(
    records: list[SessionRecord],
    cases: dict[str, Case],
    primary: Grader,
    secondary: Grader,
    domains: dict,
    *,
    per_domain: int = 20,
    seed: int = 0,
) -> dict:
    """Agreement (kappa per criterion) and mutation (TPR/TNR) report; `valid_criteria` lists `case/criterion`."""
    labels: dict[str, list[tuple[bool | None, bool | None]]] = {}
    originals: list[bool] = []
    detected: dict[str, list[bool]] = {}

    def record_pair(case: Case, va: Verdicts, vb: Verdicts) -> None:
        for cid in va:
            labels.setdefault(f"{case.id}/{cid}", []).append((va[cid], vb.get(cid)))

    ran = [r for r in records if not r.error and r.case_id in cases and cases[r.case_id].criteria]
    for r in stratified_sample(ran, per_domain, seed):
        case = cases[r.case_id]
        record_pair(case, *_both(case, r.answer, primary, secondary, summary(r)))
    for case in sorted(cases.values(), key=lambda c: c.id):
        if not case.criteria or not case.reference.facts:
            continue
        original = reference_answer(case)
        va, vb = _both(case, original, primary, secondary)
        record_pair(case, va, vb)
        originals.append(all(v is True for v in va.values()))
        for kind, text in mutants(original, case, domains).items():
            va, vb = _both(case, text, primary, secondary)
            record_pair(case, va, vb)
            detected.setdefault(kind, []).append(any(v is False for v in va.values()))

    criteria = {}
    for key, pairs in sorted(labels.items()):
        decided = [(x, y) for x, y in pairs if x is not None and y is not None]
        kappa = stats.cohen_kappa([x for x, _ in decided], [y for _, y in decided]) if decided else None
        valid = kappa is not None and len(decided) >= MIN_ITEMS and kappa >= KAPPA_MIN
        criteria[key] = {"kappa": kappa, "items": len(pairs), "decided": len(decided), "valid": valid}
    all_detected = [d for kind in detected.values() for d in kind]
    tpr = sum(originals) / len(originals) if originals else None
    tnr = sum(all_detected) / len(all_detected) if all_detected else None
    return {
        "judge_prompt_version": JUDGE_PROMPT_VERSION,
        "independent_prompt_version": INDEPENDENT_PROMPT_VERSION,
        "rubric_version": RUBRIC_VERSION,
        "kappa_min": KAPPA_MIN,
        "min_items": MIN_ITEMS,
        "criteria": criteria,
        "valid_criteria": sorted(k for k, v in criteria.items() if v["valid"]),
        "mutation": {
            "tpr": tpr,
            "tnr": tnr,
            "originals": len(originals),
            "mutants": len(all_detected),
            "by_kind": {k: {"tnr": sum(v) / len(v), "mutants": len(v)} for k, v in sorted(detected.items())},
        },
        "judge_valid": tpr is not None and tnr is not None and tpr >= TPR_MIN and tnr >= TNR_MIN,
    }


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def validity_markdown(report: dict) -> str:
    m = report["mutation"]
    out = [
        "# Judge validity",
        "",
        (
            f"Prompt `{report['judge_prompt_version']}` / `{report['independent_prompt_version']}`, "
            f"rubric `{report['rubric_version']}`. Models: {report.get('models', {})}."
        ),
        "",
        (
            f"Mutation tests: TPR {_fmt(m['tpr'])} over {m['originals']} originals (min {TPR_MIN}), "
            f"TNR {_fmt(m['tnr'])} over {m['mutants']} mutants (min {TNR_MIN}). "
            f"Judge valid: {'yes' if report['judge_valid'] else 'no'}."
        ),
        "",
        "| Mutation | TNR | Mutants |",
        "|---|---:|---:|",
        *[f"| {k} | {_fmt(v['tnr'])} | {v['mutants']} |" for k, v in m["by_kind"].items()],
        "",
        f"## Agreement (kappa >= {report['kappa_min']}, at least {report['min_items']} decided items)",
        "",
        "| Criterion | Kappa | Decided / items | Valid |",
        "|---|---:|---:|---|",
        *[
            f"| `{k}` | {_fmt(v['kappa'])} | {v['decided']} / {v['items']} | {'yes' if v['valid'] else 'no'} |"
            for k, v in report["criteria"].items()
        ],
    ]
    return "\n".join(out) + "\n"


class ClaudeGrader:
    """Grades through `claude -p` in an empty directory with a fresh config, no tools and one turn."""

    def __init__(
        self,
        model: str,
        *,
        execute: runner.Execute = runner.subprocess_execute,
        environ: Mapping[str, str] = os.environ,
        timeout: float = 300.0,
    ) -> None:
        if not model:
            raise runner.RunnerError("a judge model is required")
        runner.preflight(environ)
        self.model, self.execute, self.environ, self.timeout = model, execute, environ, timeout

    def __call__(self, prompt: str) -> str:
        with tempfile.TemporaryDirectory(prefix="ctx-judge-") as home:
            mcp = Path(home) / "mcp.json"
            mcp.write_text(json.dumps({"mcpServers": {}}))
            argv = [
                "claude", "-p", prompt, "--output-format", "json", "--model", self.model, "--max-turns", "1",
                "--setting-sources", "project", "--strict-mcp-config", "--mcp-config", str(mcp),
            ]  # fmt: skip
            env = runner.ClaudeAdapter().env(Path(home), self.environ)
            done = self.execute(argv, Path(home), env, self.timeout)
        try:
            return str(json.loads(done.stdout).get("result", ""))
        except (json.JSONDecodeError, AttributeError):
            return ""
