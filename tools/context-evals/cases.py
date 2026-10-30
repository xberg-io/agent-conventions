"""Case corpus for the dynamic harness (issue #3, section 5.2): schema, loader and validator.

Cases live in `cases/<repo>/<domain>.yaml`, each file a YAML list of cases. A case names a prompt, where the
session starts, how it should behave (answer or ask), which skills it must and must not use, what the answer must
not mention or must contain, binary criteria for the judge and the reference the criteria are checked against.

Validation runs without a checkout (schema, enums, ids, regexes, taxonomy) and, given a checkout, also checks that
`cwd` and every `reference.sources` path exist and that every named skill is generated there.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import exposure
import stats
import yaml

BEHAVIOURS = ("answer", "ask", "either")
SANDBOXES = ("result", "procedure")
REQUIRED = ("id", "domain", "repo", "cwd", "prompt", "behaviour", "sandbox")
OPTIONAL = ("persona", "must_use", "must_not_use", "must_not_mention", "expect", "criteria", "reference")
KEBAB = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


@dataclass(frozen=True)
class Criterion:
    id: str
    check: str


@dataclass(frozen=True)
class Reference:
    facts: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class Case:
    id: str
    domain: str
    repo: str
    cwd: str
    prompt: str
    behaviour: str
    sandbox: str
    persona: str = ""
    must_use: tuple[str, ...] = ()
    must_not_use: tuple[str, ...] = ()
    must_not_mention: tuple[str, ...] = ()
    expect: tuple[str, ...] = ()
    criteria: tuple[Criterion, ...] = ()
    reference: Reference = field(default_factory=Reference)
    file: str = ""

    @property
    def split(self) -> str:
        return "holdout" if stats.is_holdout(self.id) else "tune"

    @property
    def cluster(self) -> str:
        return self.must_use[0] if self.must_use else self.domain


class CaseError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("\n".join(errors))
        self.errors = errors


def _strings(value: object, key: str, where: str, errors: list[str]) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        errors.append(f"{where}: {key} must be a list of strings")
        return ()
    return tuple(value)


def _regexes(patterns: tuple[str, ...], key: str, where: str, errors: list[str]) -> None:
    for pattern in patterns:
        try:
            re.compile(pattern)
        except re.error as exc:
            errors.append(f"{where}: {key} pattern {pattern!r} does not compile: {exc}")


def _criteria(value: object, where: str, errors: list[str]) -> tuple[Criterion, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        errors.append(f"{where}: criteria must be a list")
        return ()
    out: list[Criterion] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"id", "check"}:
            errors.append(f"{where}: each criterion needs exactly the keys id and check")
            continue
        if not isinstance(item["id"], str) or not KEBAB.fullmatch(item["id"]):
            errors.append(f"{where}: criterion id {item['id']!r} is not kebab-case")
        elif any(c.id == item["id"] for c in out):
            errors.append(f"{where}: duplicate criterion id {item['id']!r}")
        if not isinstance(item["check"], str) or not item["check"].strip():
            errors.append(f"{where}: criterion {item['id']!r} has an empty check")
        out.append(Criterion(str(item["id"]), str(item["check"])))
    return tuple(out)


def _reference(value: object, where: str, errors: list[str]) -> Reference:
    if value is None:
        return Reference()
    if not isinstance(value, dict) or not set(value) <= {"facts", "sources"}:
        errors.append(f"{where}: reference takes only facts and sources")
        return Reference()
    return Reference(
        _strings(value.get("facts"), "reference.facts", where, errors),
        _strings(value.get("sources"), "reference.sources", where, errors),
    )


def parse_case(data: object, file: str, errors: list[str]) -> Case | None:
    """Build one case, appending every schema problem to `errors`; None when the case is unusable."""
    if not isinstance(data, dict):
        errors.append(f"{file}: every entry must be a mapping")
        return None
    where = f"{file}:{data.get('id', '?')}"
    unknown = sorted(set(data) - set(REQUIRED) - set(OPTIONAL))
    if unknown:
        errors.append(f"{where}: unknown keys {unknown}")
    missing = [k for k in REQUIRED if not isinstance(data.get(k), str) or not data[k].strip()]
    if missing:
        errors.append(f"{where}: missing or empty required keys {missing}")
        return None
    if not KEBAB.fullmatch(data["id"]):
        errors.append(f"{where}: id is not kebab-case")
    if data["behaviour"] not in BEHAVIOURS:
        errors.append(f"{where}: behaviour {data['behaviour']!r} not in {BEHAVIOURS}")
    if data["sandbox"] not in SANDBOXES:
        errors.append(f"{where}: sandbox {data['sandbox']!r} not in {SANDBOXES}")
    if Path(data["cwd"]).is_absolute() or ".." in Path(data["cwd"]).parts:
        errors.append(f"{where}: cwd must be relative to the repository root")
    persona = data.get("persona") or ""
    if not isinstance(persona, str):
        errors.append(f"{where}: persona must be a string")
        persona = ""
    case = Case(
        id=data["id"],
        domain=data["domain"],
        repo=data["repo"],
        cwd=data["cwd"],
        prompt=data["prompt"],
        behaviour=data["behaviour"],
        sandbox=data["sandbox"],
        persona=persona,
        must_use=_strings(data.get("must_use"), "must_use", where, errors),
        must_not_use=_strings(data.get("must_not_use"), "must_not_use", where, errors),
        must_not_mention=_strings(data.get("must_not_mention"), "must_not_mention", where, errors),
        expect=_strings(data.get("expect"), "expect", where, errors),
        criteria=_criteria(data.get("criteria"), where, errors),
        reference=_reference(data.get("reference"), where, errors),
        file=file,
    )
    _regexes(case.must_not_mention, "must_not_mention", where, errors)
    _regexes(case.expect, "expect", where, errors)
    overlap = sorted(set(case.must_use) & set(case.must_not_use))
    if overlap:
        errors.append(f"{where}: skills both required and forbidden: {overlap}")
    return case


def load_file(path: Path, errors: list[str]) -> list[Case]:
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        errors.append(f"{path}: invalid YAML: {exc}")
        return []
    if data is None:
        return []
    if not isinstance(data, list):
        errors.append(f"{path}: a case file is a YAML list of cases")
        return []
    cases = [parse_case(item, str(path), errors) for item in data]
    return [c for c in cases if c is not None]


def case_files(cases_dir: Path) -> list[Path]:
    return sorted([*cases_dir.glob("*/*.yaml"), *cases_dir.glob("*/*.yml")])


def check_corpus(cases: list[Case], domains: dict) -> list[str]:
    """Cross-case checks: unique ids, taxonomy membership, file layout `<repo>/<domain>.yaml`."""
    errors: list[str] = []
    seen: dict[str, str] = {}
    known_domains = domains.get("domain", {})
    known_repos = domains.get("repos", {})
    for case in cases:
        where = f"{case.file}:{case.id}"
        if case.id in seen:
            errors.append(f"{where}: duplicate case id (also in {seen[case.id]})")
        seen.setdefault(case.id, case.file)
        if case.domain not in known_domains:
            errors.append(f"{where}: domain {case.domain!r} is not in domains.toml")
        if case.repo not in known_repos:
            errors.append(f"{where}: repo {case.repo!r} is not under [repos] in domains.toml")
        file = Path(case.file)
        if case.file and (file.parent.name, file.stem) != (case.repo, case.domain):
            errors.append(f"{where}: belongs in {case.repo}/{case.domain}.yaml")
    return errors


def generated_skills(repo_root: Path) -> set[str]:
    """Skill names generated in a checkout, for Claude Code (.claude/skills) and the open layout (.agents/skills)."""
    names: set[str] = set()
    for base in (repo_root / ".claude" / "skills", repo_root / ".agents" / "skills"):
        for file in sorted(base.glob("*/SKILL.md")) if base.exists() else []:
            names.add(exposure.metadata(file).get("name") or file.parent.name)
    return names


def check_checkout(cases: list[Case], repo_root: Path) -> list[str]:
    errors: list[str] = []
    skills = generated_skills(repo_root)
    for case in cases:
        where = f"{case.file}:{case.id}"
        if not (repo_root / case.cwd).is_dir():
            errors.append(f"{where}: cwd {case.cwd!r} does not exist in {repo_root}")
        for source in case.reference.sources:
            if not (repo_root / source).exists():
                errors.append(f"{where}: reference source {source!r} does not exist in {repo_root}")
        for skill in case.must_use:
            if skill not in skills:
                errors.append(f"{where}: skill {skill!r} is not generated in {repo_root}")
    return errors


def load_corpus(cases_dir: Path, domains: dict) -> list[Case]:
    """Load and validate every case file; raise CaseError listing every problem."""
    errors: list[str] = []
    cases = [c for f in case_files(cases_dir) for c in load_file(f, errors)]
    errors += check_corpus(cases, domains)
    if errors:
        raise CaseError(errors)
    return cases


def select(cases: list[Case], *, repo: str | None = None, pattern: str = "*", split: str = "tune") -> list[Case]:
    """Filter by repo, id glob and split (tune | holdout | all)."""
    if split not in ("tune", "holdout", "all"):
        raise ValueError(f"split {split!r} is not tune, holdout or all")
    return [
        c
        for c in cases
        if (repo is None or c.repo == repo)
        and fnmatch.fnmatchcase(c.id, pattern)
        and (split == "all" or c.split == split)
    ]


def corpus_hash(cases: list[Case]) -> str:
    """Hash of the cases' content (not their file paths), so a run records exactly what it was asked."""
    payload = [{k: v for k, v in asdict(c).items() if k != "file"} for c in sorted(cases, key=lambda c: c.id)]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
