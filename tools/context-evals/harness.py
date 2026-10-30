#!/usr/bin/env python3
"""Dynamic context-evaluation harness (issue #3, section 5.2).

Commands:
    validate-cases [--repo-root PATH [--repo NAME]]
    run --repo PATH --ref REF --model M --out DIR [--cases GLOB] [--split tune|holdout|all] [--repeats N]
    score RUN_DIR
    judge RUN_DIR --model M
    judge-validate RUN_DIR --model M --second-model M2
    report RUN_DIR
    compare BASE_RUN ARM_RUN

A run directory holds run.json (repo, ref, model, versions, case corpus hash, start time), cases.json (the cases
as run), context/ (the checkout's context files), transcripts/, sessions.jsonl, and after judging judge/ and
report.{json,md}. The holdout split runs only when asked for (`--split holdout`). Never run this in per-commit CI:
each session calls a model.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import budget
import cases as cases_mod
import judge
import records
import runner
import scoring
import stats
import transcript
from cases import Case, Criterion, Reference

HERE = Path(__file__).parent
HARNESS_VERSION = "2"
VERSION_KEYS = ("judge_prompt_version", "rubric_version", "judge_model")

GraderFactory = Callable[[str], judge.Grader]


class HarnessError(RuntimeError):
    pass


def load_domains(path: Path) -> dict:
    return tomllib.loads(path.read_text())


def case_from_dict(data: dict) -> Case:
    data = dict(data)
    for key in ("must_use", "must_not_use", "must_not_mention", "expect"):
        data[key] = tuple(data.get(key, ()))
    data["criteria"] = tuple(Criterion(**c) for c in data.get("criteria", ()))
    ref = data.get("reference") or {}
    data["reference"] = Reference(tuple(ref.get("facts", ())), tuple(ref.get("sources", ())))
    return Case(**data)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def run_cases(run_dir: Path) -> dict[str, Case]:
    return {c["id"]: case_from_dict(c) for c in read_json(run_dir / "cases.json")}


def cmd_validate_cases(args: argparse.Namespace) -> int:
    domains = load_domains(args.domains)
    try:
        corpus = cases_mod.load_corpus(args.cases_dir, domains)
    except cases_mod.CaseError as exc:
        for error in exc.errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    if not corpus:
        print(f"error: no cases under {args.cases_dir}", file=sys.stderr)
        return 1
    errors = []
    if args.repo_root:
        name = args.repo or args.repo_root.resolve().name
        errors = cases_mod.check_checkout([c for c in corpus if c.repo == name], args.repo_root.resolve())
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    holdout = sum(1 for c in corpus if c.split == "holdout")
    print(f"{len(corpus)} cases ({len(corpus) - holdout} tune, {holdout} holdout), {len(errors)} checkout errors")
    return 1 if errors else 0


def cmd_run(args: argparse.Namespace, execute: runner.Execute, environ: Mapping[str, str]) -> int:
    domains = load_domains(args.domains)
    out: Path = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise HarnessError(f"{out} is not empty; every run gets a fresh directory")
    corpus = cases_mod.load_corpus(args.cases_dir, domains)
    name = args.repo_name or args.repo.resolve().name
    selected = cases_mod.select(corpus, repo=name, pattern=args.cases, split=args.split)
    if not selected:
        raise HarnessError(f"no {args.split} case matches repo {name!r} and {args.cases!r}")
    runner.preflight(environ)
    config = runner.RunConfig(
        model=args.model,
        max_turns=args.max_turns,
        timeout=args.timeout,
        repeats=args.repeats,
        generate=not args.skip_generate,
    )
    commit = runner.resolve_ref(args.repo.resolve(), args.ref)
    started = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta = {
        "run_id": f"{name}@{commit[:12]}@{started}",
        "repo": name,
        "ref": args.ref,
        "commit": commit,
        "model": args.model,
        "agent": runner.ClaudeAdapter.name,
        "split": args.split,
        "repeats": args.repeats,
        "max_turns": args.max_turns,
        "timeout": args.timeout,
        "allowed_tools": list(config.allowed_tools),
        "harness_version": HARNESS_VERSION,
        "record_version": records.RECORD_VERSION,
        "judge_prompt_version": judge.JUDGE_PROMPT_VERSION,
        "rubric_version": judge.RUBRIC_VERSION,
        "judge_model": "",
        "case_corpus_hash": cases_mod.corpus_hash(selected),
        "cases": [c.id for c in selected],
        "started_at": started,
    }
    write_json(out / "run.json", meta)
    write_json(out / "cases.json", [asdict(c) for c in selected])
    runner.Runner(args.repo, out, config, execute=execute, environ=environ).run(commit, selected)
    meta["finished_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_json(out / "run.json", meta)
    return score_run(out, load_domains(args.domains))


def score_run(run_dir: Path, domains: dict) -> int:
    meta = read_json(run_dir / "run.json")
    corpus = run_cases(run_dir)
    out = []
    for case_id in meta["cases"]:
        for repeat in range(meta["repeats"]):
            path = run_dir / "transcripts" / f"{runner.session_name(case_id, repeat)}.jsonl"
            if not path.exists():
                continue
            info = runner.read_meta(run_dir / "transcripts", case_id, repeat)
            t = transcript.parse_file(path)
            out.append(
                scoring.score(
                    corpus[case_id],
                    t,
                    domains,
                    run_dir / "context",
                    run_id=meta["run_id"],
                    repeat=repeat,
                    run_dir=str(run_dir.resolve()),
                    error=info.error if info else "",
                    root=info.root if info else None,
                )
            )
    apply_judge(run_dir, out)
    records.write_sessions(run_dir / "sessions.jsonl", out)
    errors = sum(1 for r in out if r.error)
    print(f"scored {len(out)} sessions ({errors} failed) into {run_dir / 'sessions.jsonl'}")
    return 0


def apply_judge(run_dir: Path, sessions: list[records.SessionRecord]) -> None:
    """Apply stored verdicts, masked to the criteria the stored validity report validated for the same judge."""
    verdicts_path, validity_path = run_dir / "judge" / "verdicts.jsonl", run_dir / "judge" / "validity.json"
    if not verdicts_path.exists():
        return
    rows = [json.loads(line) for line in verdicts_path.read_text().splitlines() if line.strip()]
    valid: set[str] = set()
    if validity_path.exists():
        validity = read_json(validity_path)
        models = {row["judge_model"] for row in rows}
        same = (
            validity["judge_prompt_version"] == judge.JUDGE_PROMPT_VERSION
            and validity["rubric_version"] == judge.RUBRIC_VERSION
            and models <= {validity.get("models", {}).get("primary")}
        )
        if same:
            valid = set(validity["valid_criteria"])
        else:
            print("warning: judge validity report is for another judge; criteria stay None", file=sys.stderr)
    judge.apply(sessions, rows, valid)


def cmd_score(args: argparse.Namespace) -> int:
    return score_run(args.run_dir, load_domains(args.domains))


def _sessions(run_dir: Path) -> list[records.SessionRecord]:
    path = run_dir / "sessions.jsonl"
    if not path.exists():
        raise HarnessError(f"{path} does not exist; run `score` first")
    return records.read_sessions(path)


def cmd_judge(args: argparse.Namespace, factory: GraderFactory) -> int:
    sessions = _sessions(args.run_dir)
    rows = judge.judge_sessions(sessions, run_cases(args.run_dir), factory(args.model), args.model)
    path = args.run_dir / "judge" / "verdicts.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    meta = read_json(args.run_dir / "run.json")
    write_json(args.run_dir / "run.json", {**meta, "judge_model": args.model})
    apply_judge(args.run_dir, sessions)
    records.write_sessions(args.run_dir / "sessions.jsonl", sessions)
    if not (args.run_dir / "judge" / "validity.json").exists():
        print("judge not validated yet: criteria stay None until `judge-validate` runs", file=sys.stderr)
    print(f"graded {len(rows)} sessions")
    return 0


def cmd_judge_validate(args: argparse.Namespace, factory: GraderFactory) -> int:
    sessions = _sessions(args.run_dir)
    report = judge.validate(
        sessions,
        run_cases(args.run_dir),
        factory(args.model),
        factory(args.second_model),
        load_domains(args.domains),
        per_domain=args.per_domain,
    )
    report["models"] = {"primary": args.model, "secondary": args.second_model}
    write_json(args.run_dir / "judge" / "validity.json", report)
    (args.run_dir / "judge" / "validity.md").write_text(judge.validity_markdown(report))
    apply_judge(args.run_dir, sessions)
    records.write_sessions(args.run_dir / "sessions.jsonl", sessions)
    print(
        f"{len(report['valid_criteria'])}/{len(report['criteria'])} criteria valid; "
        f"judge valid: {'yes' if report['judge_valid'] else 'no'}"
    )
    return 0


def _cell(m: dict | None, digits: int = 3) -> str:
    if m is None:
        return "n/a"
    return f"{m['mean']:.{digits}f} [{m['lo']:.{digits}f}, {m['hi']:.{digits}f}] ({m['cases']})"


def report_markdown(meta: dict, summary: dict) -> str:
    out = [
        f"# Context run {meta['run_id']}",
        "",
        (
            f"Repo `{meta['repo']}` at `{meta['ref']}` ({meta['commit'][:12]}), model `{meta['model']}`, "
            f"split {meta['split']}, {meta['repeats']} repeat(s). Judge `{meta.get('judge_model') or 'none'}`, "
            f"prompt `{meta['judge_prompt_version']}`, rubric `{meta['rubric_version']}`."
        ),
        "",
        "Cells: mean [95% cluster-bootstrap interval] (cases).",
        "",
    ]
    columns = ["overall", *summary["domains"]]
    blocks = {"overall": summary["overall"], **summary["domains"]}
    out.append("| Metric | " + " | ".join(columns) + " |")
    out.append("|---|" + "---|" * len(columns))
    for metric in scoring.METRICS:
        cells = [_cell(blocks[c]["metrics"][metric.name]) for c in columns]
        out.append(f"| {metric.name} | " + " | ".join(cells) + " |")
    out.append(
        "| sessions (failed) | "
        + " | ".join(f"{blocks[c]['sessions']} ({blocks[c]['errors']})" for c in columns)
        + " |"
    )
    return "\n".join(out) + "\n"


def cmd_report(args: argparse.Namespace) -> int:
    meta = read_json(args.run_dir / "run.json")
    summary = scoring.aggregate(_sessions(args.run_dir))
    validity = args.run_dir / "judge" / "validity.json"
    write_json(
        args.run_dir / "report.json",
        {"run": meta, "judge_validity": read_json(validity) if validity.exists() else None, "summary": summary},
    )
    text = report_markdown(meta, summary)
    (args.run_dir / "report.md").write_text(text)
    print(text)
    return 0


def comparable(base: dict, arm: dict) -> list[str]:
    """Reasons two runs must not be compared: different judge or rubric versions or judge models."""
    return [
        f"{key}: {base.get(key)!r} != {arm.get(key)!r}" for key in VERSION_KEYS if base.get(key, "") != arm.get(key, "")
    ]


def _verdict(iv: stats.Interval, higher_is_better: bool) -> str:
    if iv.verdict == "inconclusive":
        return "inconclusive"
    return "improved" if (iv.verdict == "better") == higher_is_better else "regressed"


def compare(base: list[records.SessionRecord], arm: list[records.SessionRecord], *, seed: int = 0) -> list[dict]:
    clusters = {r.case_id: r.cluster for r in [*base, *arm]}
    domains = sorted({r.domain for r in [*base, *arm]})
    rows = []
    for metric in scoring.METRICS:
        for scope in ["overall", *domains]:
            pick = (lambda rs: rs) if scope == "overall" else (lambda rs, d=scope: [r for r in rs if r.domain == d])
            b, a = scoring.per_case(pick(base), metric), scoring.per_case(pick(arm), metric)
            if not set(b) & set(a):
                continue
            iv = stats.paired_cluster_bootstrap(b, a, clusters, seed=seed)
            rows.append(
                {
                    "metric": metric.name,
                    "scope": scope,
                    "diff": iv.mean,
                    "lo": iv.lo,
                    "hi": iv.hi,
                    "mde": iv.mde(),
                    "cases": iv.cases,
                    "clusters": iv.clusters,
                    "verdict": _verdict(iv, metric.higher_is_better),
                }
            )
    return rows


def compare_markdown(base: dict, arm: dict, rows: list[dict]) -> str:
    out = [
        f"# Compare {base['run_id']} -> {arm['run_id']}",
        "",
        (
            "Difference arm - base, paired cluster bootstrap 95% interval; MDE at 80% power. "
            "`inconclusive` when the interval spans zero."
        ),
        "",
        "| Metric | Scope | Diff | Interval | MDE | Cases (clusters) | Verdict |",
        "|---|---|---:|---|---:|---:|---|",
    ]
    for r in rows:
        out.append(
            f"| {r['metric']} | {r['scope']} | {r['diff']:+.3f} | [{r['lo']:+.3f}, {r['hi']:+.3f}] "
            f"| {r['mde']:.3f} | {r['cases']} ({r['clusters']}) | {r['verdict']} |"
        )
    return "\n".join(out) + "\n"


def cmd_compare(args: argparse.Namespace) -> int:
    base_meta, arm_meta = read_json(args.base / "run.json"), read_json(args.arm / "run.json")
    reasons = comparable(base_meta, arm_meta)
    if reasons:
        raise HarnessError("refusing to compare runs graded differently: " + "; ".join(reasons))
    if base_meta["case_corpus_hash"] != arm_meta["case_corpus_hash"]:
        print("warning: the runs used different case corpora; only shared cases are paired", file=sys.stderr)
    rows = compare(_sessions(args.base), _sessions(args.arm))
    if args.json:
        write_json(args.json, {"base": base_meta, "arm": arm_meta, "rows": rows})
    print(compare_markdown(base_meta, arm_meta, rows))
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--domains", type=Path, default=HERE / "domains.toml")
    p.add_argument("--cases-dir", type=Path, default=HERE / "cases")
    p.add_argument("--budget-ledger", type=Path, help="shared SQLite spending ledger for this round")
    p.add_argument("--budget-usd", type=float, default=25.0)
    p.add_argument("--per-call-usd", type=float, default=0.2)
    sub = p.add_subparsers(dest="command", required=True)

    v = sub.add_parser("validate-cases", help="validate the case corpus (and against a checkout)")
    v.add_argument("--repo-root", type=Path)
    v.add_argument("--repo", help="repo name in domains.toml (default: the checkout directory name)")

    r = sub.add_parser("run", help="run hermetic sessions for one repo at one ref")
    r.add_argument("--repo", type=Path, required=True)
    r.add_argument("--repo-name", help="repo name in domains.toml (default: the directory name)")
    r.add_argument("--ref", required=True)
    r.add_argument("--model", required=True)
    r.add_argument("--cases", default="*", help="glob over case ids")
    r.add_argument("--split", choices=("tune", "holdout", "all"), default="tune")
    r.add_argument("--repeats", type=int, default=3)
    r.add_argument("--max-turns", type=int, default=20)
    r.add_argument("--timeout", type=float, default=600.0)
    r.add_argument("--skip-generate", action="store_true", help="the ref has its generated outputs committed")
    r.add_argument("--out", type=Path, required=True)

    for name in ("score", "report"):
        sub.add_parser(name).add_argument("run_dir", type=Path)
    j = sub.add_parser("judge", help="grade every session's criteria")
    j.add_argument("run_dir", type=Path)
    j.add_argument("--model", required=True)
    jv = sub.add_parser("judge-validate", help="agreement and mutation tests for the judge")
    jv.add_argument("run_dir", type=Path)
    jv.add_argument("--model", required=True)
    jv.add_argument("--second-model", required=True)
    jv.add_argument("--per-domain", type=int, default=20)
    c = sub.add_parser("compare", help="paired comparison of two runs")
    c.add_argument("base", type=Path)
    c.add_argument("arm", type=Path)
    c.add_argument("--json", type=Path)
    return p


def main(
    argv: list[str] | None = None,
    *,
    execute: runner.Execute = runner.subprocess_execute,
    environ: Mapping[str, str] = os.environ,
    grader_factory: GraderFactory | None = None,
) -> int:
    args = parser().parse_args(argv)
    if args.budget_ledger:
        execute = budget.BoundedExecute(args.budget_ledger, args.budget_usd, args.per_call_usd, execute)
    factory = grader_factory or (lambda model: judge.ClaudeGrader(model, environ=environ, execute=execute))
    try:
        if args.command == "validate-cases":
            return cmd_validate_cases(args)
        if args.command == "run":
            return cmd_run(args, execute, environ)
        if args.command == "score":
            return cmd_score(args)
        if args.command == "judge":
            return cmd_judge(args, factory)
        if args.command == "judge-validate":
            return cmd_judge_validate(args, factory)
        if args.command == "report":
            return cmd_report(args)
        return cmd_compare(args)
    except (HarnessError, runner.RunnerError, cases_mod.CaseError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
