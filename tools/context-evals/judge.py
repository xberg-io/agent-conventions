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
  with a wrong one. The primary grader must pass the originals (TPR) and fail the mutants (TNR). A swap or a path
  replacement is made only where a criterion's check names that term or path: a change no criterion inspects is
  not a wrong answer under any criterion, so a judge that passes it is not lenient.

Every verdict row and report records JUDGE_PROMPT_VERSION and RUBRIC_VERSION, and the report MUTATION_VERSION;
results from different versions are never compared.
"""

from __future__ import annotations

import json
import os
import random
import re
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path

import runner
import start_context
import stats
import transcript
from cases import Case
from records import SessionRecord

JUDGE_PROMPT_VERSION = "judge-prompt-3"
INDEPENDENT_PROMPT_VERSION = "judge-prompt-independent-3"
TOOL_PROFILE_VERSION = "claude-judge-no-tools-1"
RUBRIC_VERSION = "rubric-3"
MUTATION_VERSION = "mutation-2"
KAPPA_MIN = 0.6
MIN_ITEMS = 4
TPR_MIN = 0.9
TNR_MIN = 0.8
TOOL_DEFLECTION = "Use tool X to find this out."
WRONG_PATH = "src/nonexistent/wrong_module.rs"
PATH = re.compile(r"(?<![\w/.-])[\w.-]+(?:/[\w.-]*[\w-])+")
FILE_NAME = re.compile(r"[\w-]+\.[A-Za-z][\w]*$")
WORD = re.compile(r"[a-z0-9_]{3,}|\d+")
STOPWORDS = {"the", "and", "for", "are", "with", "that", "this", "from", "uses", "use", "its", "has", "was", "not"}

Grader = Callable[[str], str]
Verdicts = dict[str, bool | None]

RUBRIC = """Grade each criterion independently as true (the answer clearly satisfies it), false (it does not, or \
contradicts the reference) or null (you cannot decide from the material given). Judge only the final answer; the \
reference is ground truth. Do not reward length, hedging or tool advice in place of a result.
Before deciding, compare every concrete name the answer gives (file and directory paths, crates, repositories, \
tools, commands, configuration files and keys, products) with the name the reference gives for the same thing. A \
different name is a contradiction, not a paraphrase, even when the rest of the sentence matches: a path is right \
only when every segment the answer gives matches the reference, and a product, tool or repository named in place of \
the reference's is wrong. A criterion whose subject is a contradicted statement is false, even if other wording in \
the answer would satisfy it."""


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
Protocol: {JUDGE_PROMPT_VERSION}; {TOOL_PROFILE_VERSION}. Use only the supplied material; tools are unavailable.
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
        f"Protocol: {INDEPENDENT_PROMPT_VERSION}; {TOOL_PROFILE_VERSION}. Tools are unavailable.",
        "Check a response for factual compliance. For every statement below decide whether the response satisfies it.",
        "Use the ground truth to decide; a response that only says how to find the answer does not satisfy a",
        "statement about the answer. Say null only when the statement cannot be decided.",
        "Check each name in the response (paths, crates, repositories, tools, commands, config files and keys,",
        "products) against the ground truth. Where the response names something other than what the ground truth",
        "names for the same role, the response is wrong on that point: every statement about that point is",
        "unsatisfied, however close the surrounding wording. A path must match the ground truth segment by segment.",
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
                "judge_tool_profile_version": TOOL_PROFILE_VERSION,
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


def _checks(case: Case | None) -> list[str]:
    return [c.check for c in case.criteria] if case is not None else []


def swap_domain(answer: str, case: Case, domains: dict) -> str | None:
    """Replace the case domain's terms that a criterion names with the first term of a domain the repo does not own."""
    owned = {case.domain, *domains.get("repos", {}).get(case.repo, {}).get("domains", [])}
    foreign = next((spec["terms"][0] for name, spec in sorted(domains.get("domain", {}).items())
                    if name not in owned and spec.get("terms")), None)  # fmt: skip
    if foreign is None:
        return None
    swapped = answer
    for term in domains.get("domain", {}).get(case.domain, {}).get("terms", []):
        pattern = start_context.term_pattern(term)
        if any(pattern.search(check) for check in _checks(case)):
            swapped = pattern.sub(foreign, swapped)
    return swapped if swapped != answer else None


def _is_path(match: re.Match[str], text: str) -> bool:
    """A file (the last segment has an extension), a directory written with its trailing slash, or lowercase segments.

    Capitalised slash-joined words (`FFI/native`, `Office/ODF`) are not paths: replacing one is not a wrong path.
    """
    token = match.group()
    return bool(FILE_NAME.search(token)) or text[match.end() : match.end() + 1] == "/" or token == token.lower()


def _bare_name(name: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![\w/.-]){re.escape(name)}(?![\w-])")


def _named_by(path: str, checks: list[str]) -> str:
    """How a criterion names `path`: "path" (in full or by a path sharing its tail), "file" (by file name) or ""."""
    name = path.rsplit("/", 1)[-1]
    for check in checks:
        if path in check or any(path.endswith(named) or named.endswith(path) for named in PATH.findall(check)):
            return "path"
    if FILE_NAME.fullmatch(name) and any(_bare_name(name).search(check) for check in checks):
        return "file"
    return ""


def wrong_path(answer: str, case: Case | None = None) -> str | None:
    """Replace the first path a criterion names; with no case, the first path.

    A path a criterion names only by its file name counts only when the answer names that file nowhere else, so the
    mutant no longer satisfies the criterion by the bare name.
    """
    checks = _checks(case)
    for match in PATH.finditer(answer):
        if not _is_path(match, answer):
            continue
        named = "path" if case is None else _named_by(match.group(), checks)
        mutant = answer[: match.start()] + WRONG_PATH + answer[match.end() :]
        if named == "path" or (named == "file" and not _bare_name(match.group().rsplit("/", 1)[-1]).search(mutant)):
            return mutant
    return None


def mutants(answer: str, case: Case, domains: dict) -> dict[str, str]:
    candidates = {
        "drop-fact": drop_fact(answer, case.reference.facts),
        "swap-domain": swap_domain(answer, case, domains),
        "tool-deflection": TOOL_DEFLECTION,
        "wrong-path": wrong_path(answer, case),
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


def planned_items(case: Case, domains: dict) -> int:
    """Answers validation grades for a case before any session: its reference answer and that answer's mutants."""
    if not case.reference.facts:
        return 0
    return 1 + len(mutants(reference_answer(case), case, domains))


def validation_sample(
    records: list[SessionRecord], cases: dict[str, Case], domains: dict, per_domain: int, seed: int = 0
) -> list[SessionRecord]:
    """The stratified sample, topped up with a case's further sessions (first repeats first) until each of its
    criteria has at least MIN_ITEMS graded answers; a criterion with fewer can never be valid."""
    sample = stratified_sample(records, per_domain, seed)
    chosen = {(r.case_id, r.repeat) for r in sample}
    for case_id in sorted({r.case_id for r in records}):
        have = planned_items(cases[case_id], domains) + sum(r.case_id == case_id for r in sample)
        spare = sorted((r for r in records if r.case_id == case_id and (r.case_id, r.repeat) not in chosen),
                       key=lambda r: r.repeat)  # fmt: skip
        sample += spare[: max(0, MIN_ITEMS - have)]
    return sample


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
    sample = validation_sample(ran, cases, domains, per_domain, seed)
    for r in sample:
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
        "mutation_version": MUTATION_VERSION,
        "judge_tool_profile_version": TOOL_PROFILE_VERSION,
        "validation_sessions": len(sample),
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
            f"rubric `{report['rubric_version']}`, mutations `{report.get('mutation_version', 'mutation-1')}`. "
            f"Models: {report.get('models', {})}."
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
                "claude", "-p", prompt, "--output-format", "stream-json", "--verbose", "--model", self.model,
                "--max-turns", "1",
                "--setting-sources", "project", "--strict-mcp-config", "--mcp-config", str(mcp),
                "--tools", "",
            ]  # fmt: skip
            env = runner.ClaudeAdapter().env(Path(home), self.environ)
            done = self.execute(argv, Path(home), env, self.timeout)
        if done.returncode or done.timed_out:
            return ""
        if error := runner.tool_profile_error(done.stdout, ()):
            raise runner.RunnerError(f"judge {error}")
        parsed = transcript.parse(done.stdout)
        return "" if parsed.error else parsed.answer
