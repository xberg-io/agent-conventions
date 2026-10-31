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
import hashlib
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
import continuation
import exposure
import gateway
import gateway_transport
import judge
import records
import runner
import scoring
import stats
import transcript
from cases import Case, Criterion, Reference

HERE = Path(__file__).parent
HARNESS_VERSION = "6"
VERSION_KEYS = (
    "judge_prompt_version",
    "rubric_version",
    "judge_model",
    "calibration_version",
    "taxonomy_version",
    "harness_version",
    "tool_profile_version",
    "judge_tool_profile_version",
    "execution_policy",
)

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


def run_metadata(
    args: argparse.Namespace, commit: str, config: runner.RunConfig, selected: list[Case], domains: dict
) -> dict:
    name = args.repo_name or args.repo.resolve().name
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
        "tool_profile_version": runner.TOOL_PROFILE_VERSION,
        "judge_tool_profile_version": judge.TOOL_PROFILE_VERSION,
        "harness_version": HARNESS_VERSION,
        "execution_policy": execution_policy(args),
        "budget_round": budget_round(args),
        "calibration_version": exposure.CALIBRATION["calibration_version"],
        "taxonomy_version": hashlib.sha256(json.dumps(domains, sort_keys=True).encode()).hexdigest(),
        "record_version": records.RECORD_VERSION,
        "judge_prompt_version": judge.JUDGE_PROMPT_VERSION,
        "rubric_version": judge.RUBRIC_VERSION,
        "judge_model": "",
        "case_corpus_hash": cases_mod.corpus_hash(selected),
        "cases": [c.id for c in selected],
        "started_at": started,
    }
    return meta


def resume_metadata(out: Path, meta: dict) -> None:
    previous = read_json(out / "run.json")
    stable = (
        "commit",
        "model",
        "split",
        "repeats",
        "max_turns",
        "timeout",
        "case_corpus_hash",
        "harness_version",
        "allowed_tools",
        "tool_profile_version",
        "judge_tool_profile_version",
        "execution_policy",
        "budget_round",
        "continuation_manifest",
        "admission_epoch",
    )
    if any(previous.get(key) != meta.get(key) for key in stable):
        raise HarnessError("resume parameters differ from the recorded run")
    meta["started_at"], meta["run_id"] = previous["started_at"], previous["run_id"]
    meta["judge_model"] = previous.get("judge_model", "")


def cmd_run(
    args: argparse.Namespace,
    execute: runner.Execute,
    environ: Mapping[str, str],
    continuation_plan: continuation.Plan | None = None,
) -> int:
    domains = load_domains(args.domains)
    out: Path = args.out.resolve()
    if out.exists() and any(out.iterdir()) and not args.resume:
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
        jobs=args.jobs,
        resume=args.resume,
    )
    commit = runner.resolve_ref(args.repo.resolve(), args.ref)
    meta = run_metadata(args, commit, config, selected, domains)
    if continuation_plan is not None:
        meta["continuation_manifest"] = {"path": str(continuation_plan.path), "sha256": continuation_plan.sha256}
        meta["admission_epoch"] = continuation_plan.data["next_admission"]
    if args.resume:
        resume_metadata(out, meta)
    meta["jobs"] = args.jobs
    write_json(out / "run.json", meta)
    write_json(out / "cases.json", [asdict(c) for c in selected])
    inherited = continuation_plan.inherited(name) if continuation_plan else None
    guarded = continuation_plan.wrap(execute, out, name) if continuation_plan else execute
    runner.Runner(args.repo, out, config, execute=guarded, environ=environ, inherited=inherited).run(commit, selected)
    meta["finished_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_json(out / "run.json", meta)
    return score_run(out, load_domains(args.domains))


def cmd_continue(args: argparse.Namespace, execute: runner.Execute, environ: Mapping[str, str]) -> int:
    if not args.hard_budget:
        raise HarnessError("reviewed continuation requires the original hard-budget ledger")
    corpus = cases_mod.load_corpus(args.cases_dir, load_domains(args.domains))
    plan = continuation.Plan.load(args.manifest, args.manifest_sha256, corpus, args.budget_ledger)
    name = args.repo.resolve().name
    if name not in plan.selected:
        raise HarnessError("consumer is outside the reviewed continuation")
    config = plan.identities[name]["config"]
    if plan.data["version"] == 2 and str(args.out.resolve()) != plan.data["outputs"][name]:
        raise HarnessError("continuation output differs from its sealed plan")
    sealed = argparse.Namespace(
        **(
            vars(args)
            | {
                "repo_name": name,
                "ref": plan.data["repos"][name]["ref"],
                "model": config["model"],
                "cases": "*",
                "split": "tune",
                "repeats": config["repeats"],
                "max_turns": config["max_turns"],
                "timeout": config["timeout"],
                "jobs": 1,
                "resume": False,
                "skip_generate": not config["generate"],
            }
        )
    )
    return cmd_run(sealed, execute, environ, continuation_plan=plan)


def cmd_continuation_report(args: argparse.Namespace) -> int:
    data = continuation.read_bound_json(args.manifest, args.manifest_sha256)
    domains = load_domains(args.domains)
    corpus = cases_mod.load_corpus(args.cases_dir, domains)
    ledger = Path(data["round"]["ledger_path"])
    plan = continuation.Plan.load(args.manifest, args.manifest_sha256, corpus, ledger, allow_stopped=True)
    report = plan.aggregate(args.runs, domains)
    out = args.out.resolve()
    continuation.controlled_path(str(out), ledger)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(f"verified {report['expected_trials']} planned trials across {len(report['sources'])} consumers")
    return 0


def recorded_continuation(run_dir: Path, domains: dict) -> continuation.Plan | None:
    meta = read_json(run_dir / "run.json")
    item = meta.get("continuation_manifest")
    if item is None:
        return None
    corpus = cases_mod.load_corpus(HERE / "cases", domains)
    return continuation.Plan.load(
        Path(item["path"]), item["sha256"], corpus, Path(meta["budget_round"]["ledger_path"]), allow_stopped=True
    )


def certificate_fields(info: runner.SessionMeta | None, meta: dict, versions: tuple[str, ...]) -> bool:
    return (
        info is not None
        and info.bounded_failure is True
        and type(info.returncode) is int
        and info.returncode == 1
        and isinstance(info.stderr, str)
        and meta.get("harness_version") in versions
        and meta.get("allowed_tools") == list(runner.DEFAULT_TOOLS)
        and meta.get("model") in gateway.MODELS
    )


def completion_events(raw: str) -> list[dict]:
    """Project native JSON events while preserving the parser's existing text-diagnostic tolerance."""
    events = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def completion_terminal(raw: str) -> dict | None:
    events = completion_events(raw)
    if not events:
        return None
    try:
        return gateway_transport.terminal_event("\n".join(json.dumps(event, allow_nan=False) for event in events))
    except (ValueError, TypeError):
        return None


def certificate_profile(raw: str, meta: dict) -> bool:
    events = completion_events(raw)
    if not events:
        return False
    initializations = [event for event in events if event.get("type") == "system" and event.get("subtype") == "init"]
    if len(initializations) != 1:
        return False
    gate = gateway_transport.InitGate(meta["model"], runner.DEFAULT_TOOLS)
    gate.observe(json.dumps(initializations[0]))
    return gate.valid


def controller_metadata(info: runner.SessionMeta | None) -> bool:
    return (
        info is not None
        and type(info.returncode) is int
        and type(info.bounded_failure) is bool
        and isinstance(info.error, str)
        and isinstance(info.stderr, str)
    )


def ordinary_completion(info: runner.SessionMeta, terminal: dict) -> bool:
    return (
        info.returncode == 0
        and info.error == ""
        and info.bounded_failure is False
        and terminal.get("subtype") == "success"
        and terminal.get("is_error") is False
        and terminal.get("errors", []) == []
        and terminal.get("permission_denials", []) == []
        and type(terminal.get("safety_stops", 0)) is int
        and terminal.get("safety_stops", 0) == 0
    )


def completion_error(terminal: dict) -> str:
    subtype = terminal.get("subtype")
    if subtype == "success" and terminal.get("is_error") is False:
        return ""
    return subtype if isinstance(subtype, str) and subtype else "invalid native result"


def unavailable_certificate(info: runner.SessionMeta | None, raw: str, meta: dict) -> bool:
    if not certificate_fields(info, meta, (HARNESS_VERSION,)) or info.error != "tool_unavailable":
        return False
    result = runner.Completed(info.returncode, raw, info.stderr, bounded_failure=True)
    if runner.session_error(result, runner.DEFAULT_TOOLS) != "tool_unavailable":
        return False
    return certificate_profile(raw, meta)


def maximum_certificate(info: runner.SessionMeta | None, raw: str, meta: dict) -> bool:
    maximum = meta.get("max_turns")
    if (
        not certificate_fields(info, meta, ("5", HARNESS_VERSION))
        or info.error not in ("", "error_max_turns")
        or type(maximum) is not int
        or maximum <= 0
    ):
        return False
    result = runner.Completed(info.returncode, raw, info.stderr, bounded_failure=True)
    return (
        gateway_transport.maximum_turn_failure(result, maximum)
        and not runner.tool_profile_error(raw, runner.DEFAULT_TOOLS)
        and certificate_profile(raw, meta)
    )


def agent_profile_error(raw: str, meta: dict) -> str:
    if meta.get("harness_version") not in ("5", HARNESS_VERSION):
        return "unsupported execution methodology"
    if meta.get("allowed_tools") != list(runner.DEFAULT_TOOLS):
        return "invalid declared agent tool profile"
    if not isinstance(meta.get("model"), str) or not meta["model"]:
        return "invalid declared model"
    if not certificate_profile(raw, meta):
        return "tool profile mismatch"
    return runner.tool_profile_error(raw, runner.DEFAULT_TOOLS)


def trial_status(info: runner.SessionMeta | None, raw: str, meta: dict) -> tuple[str, bool]:
    profile_error = agent_profile_error(raw, meta)
    terminal = completion_terminal(raw)
    if terminal is None:
        return profile_error or "invalid native completion", False
    if not controller_metadata(info):
        return profile_error or "invalid controller metadata", False
    error = profile_error or info.error or completion_error(terminal)
    if unavailable_certificate(info, raw, meta):
        return "tool_unavailable", True
    if error == "tool_unavailable":
        return "uncertified tool-unavailable failure", False
    if error == "error_max_turns":
        if maximum_certificate(info, raw, meta):
            return error, True
        return "uncertified maximum-turn failure", False
    if not error and ordinary_completion(info, terminal):
        return "", False
    return error or "uncertified CLI execution", False


def score_trial(
    run_dir: Path, case: Case, repeat: int, meta: dict, domains: dict, plan: continuation.Plan | None
) -> records.SessionRecord | None:
    if plan is not None:
        path, info, provenance = plan.resolve(meta["repo"], case.id, repeat, run_dir)
    else:
        path = run_dir / "transcripts" / f"{runner.session_name(case.id, repeat)}.jsonl"
        info = runner.read_meta(run_dir / "transcripts", case.id, repeat)
        provenance = {}
    if path is None or not path.exists():
        return None
    raw = path.read_text()
    error, bounded = trial_status(info, raw, meta)
    return scoring.score(
        case,
        transcript.parse(raw),
        domains,
        run_dir / "context",
        run_id=meta["run_id"],
        repeat=repeat,
        run_dir=str(run_dir.resolve()),
        error=error,
        root=info.root if info else None,
        bounded_failure=bounded,
        provenance=provenance,
    )


def score_run(run_dir: Path, domains: dict) -> int:
    meta = read_json(run_dir / "run.json")
    corpus = run_cases(run_dir)
    plan = recorded_continuation(run_dir, domains)
    out = []
    for case_id in meta["cases"]:
        for repeat in range(meta["repeats"]):
            value = score_trial(run_dir, corpus[case_id], repeat, meta, domains, plan)
            if value is not None:
                out.append(value)
    expected = len(meta["cases"]) * meta["repeats"]
    if len(out) != expected:
        raise HarnessError(f"expected {expected} sessions, found {len(out)}; run is incomplete")
    if plan is not None:
        from continuation_runtime import verify_request_partition

        verify_request_partition(plan, out)
    meta["calibration_version"] = exposure.CALIBRATION["calibration_version"]
    meta["taxonomy_version"] = hashlib.sha256(json.dumps(domains, sort_keys=True).encode()).hexdigest()
    write_json(run_dir / "run.json", meta)
    apply_judge(run_dir, out)
    records.write_sessions(run_dir / "sessions.jsonl", out)
    errors = sum(1 for r in out if r.error)
    print(f"scored {len(out)} sessions ({errors} failed) into {run_dir / 'sessions.jsonl'}")
    return 0


def verdict_sources_match(rows: list[dict], sessions: list[records.SessionRecord]) -> bool:
    indexed = {(row.case_id, row.repeat): row for row in sessions}
    seen = set()
    for row in rows:
        if not isinstance(row.get("case_id"), str) or type(row.get("repeat")) is not int:
            return False
        key = row["case_id"], row["repeat"]
        if key in seen or key not in indexed or indexed[key].error:
            return False
        if row.get("session_provenance", {}) != indexed[key].provenance:
            return False
        seen.add(key)
    return True


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
        recorded_meta = read_json(run_dir / "run.json")
        recorded_policy = recorded_meta.get("execution_policy")
        recorded_round = recorded_meta.get("budget_round")
        same = (
            validity.get("execution_policy") == recorded_policy
            and validity.get("continuation_manifest_sha256")
            == recorded_meta.get("continuation_manifest", {}).get("sha256")
            and verdict_sources_match(rows, sessions)
            and validity.get("budget_round") == recorded_round
            and all(row.get("budget_round") == recorded_round for row in rows)
            and all(row.get("execution_policy") == recorded_policy for row in rows)
            and validity["judge_prompt_version"] == judge.JUDGE_PROMPT_VERSION
            and validity["rubric_version"] == judge.RUBRIC_VERSION
            and validity.get("judge_tool_profile_version") == judge.TOOL_PROFILE_VERSION
            and models <= {validity.get("models", {}).get("primary")}
            and all(
                row.get("judge_prompt_version") == judge.JUDGE_PROMPT_VERSION
                and row.get("rubric_version") == judge.RUBRIC_VERSION
                and row.get("judge_tool_profile_version") == judge.TOOL_PROFILE_VERSION
                for row in rows
            )
        )
        if same:
            valid = set(validity["valid_criteria"]) if validity.get("judge_valid") else set()
        else:
            print("warning: judge validity report is for another judge; criteria stay None", file=sys.stderr)
    judge.apply(sessions, rows, valid)


def cmd_score(args: argparse.Namespace) -> int:
    return score_run(args.run_dir, load_domains(args.domains))


def _sessions(run_dir: Path, *, current_rubric: bool = False) -> list[records.SessionRecord]:
    meta = read_json(run_dir / "run.json")
    if current_rubric and meta.get("rubric_version") != judge.RUBRIC_VERSION:
        raise HarnessError("run uses a legacy rubric; migrate the reviewed scoring corpus before paid judging")
    if current_rubric and any(
        meta.get(key) != expected
        for key, expected in (
            ("harness_version", HARNESS_VERSION),
            ("tool_profile_version", runner.TOOL_PROFILE_VERSION),
            ("judge_tool_profile_version", judge.TOOL_PROFILE_VERSION),
        )
    ):
        raise HarnessError("run uses a legacy tool profile; fresh sessions are required before paid judging")
    path = run_dir / "sessions.jsonl"
    if not path.exists():
        raise HarnessError(f"{path} does not exist; run `score` first")
    return records.read_sessions(path)


def cmd_judge(args: argparse.Namespace, factory: GraderFactory) -> int:
    require_execution_policy(args)
    sessions = _sessions(args.run_dir, current_rubric=True)
    rows = judge.judge_sessions(sessions, run_cases(args.run_dir), factory(args.model), args.model)
    identity = budget_round(args)
    provenance = {(row.case_id, row.repeat): row.provenance for row in sessions}
    for row in rows:
        row["execution_policy"] = execution_policy(args)
        row["budget_round"] = identity
        row["session_provenance"] = provenance[(row["case_id"], row["repeat"])]
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
    require_execution_policy(args)
    sessions = _sessions(args.run_dir, current_rubric=True)
    report = judge.validate(
        sessions,
        run_cases(args.run_dir),
        factory(args.model),
        factory(args.second_model),
        load_domains(args.domains),
        per_domain=args.per_domain,
    )
    report["models"] = {"primary": args.model, "secondary": args.second_model}
    report["execution_policy"] = execution_policy(args)
    report["budget_round"] = budget_round(args)
    report["continuation_manifest_sha256"] = (
        read_json(args.run_dir / "run.json").get("continuation_manifest", {}).get("sha256")
    )
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


def completion_markdown(blocks: dict, *, recorded_baseline: bool = False) -> list[str]:
    columns = list(blocks)
    output = [
        "Recorded baseline trials (technical attempts reported separately):"
        if recorded_baseline
        else "All executed trials (invalid trials prevent baseline acceptance):",
        "",
        "| Measure | " + " | ".join(columns) + " |",
        "|---|" + "---|" * len(columns),
    ]
    for name, key in (
        ("recorded baseline trials" if recorded_baseline else "executed trials", "executed_trials"),
        ("invalid trials", "invalid_trials"),
        ("execution valid", "execution_valid"),
    ):
        output.append(
            "| " + name + " | " + " | ".join(str(blocks[column]["all_trials"][key]) for column in columns) + " |"
        )
    for name in ("completion", "expect_pass", "criteria_pass"):
        cells = []
        for column in columns:
            value = blocks[column]["all_trials"][name]
            rate = f"{value['rate']:.3f}" if value["rate"] is not None else "ungraded"
            cells.append(f"{value['numerator']:g}/{value['denominator']} ({rate})")
        output.append("| " + name + " | " + " | ".join(cells) + " |")
    return output + ["", "Conditional diagnostics (failed sessions excluded):", ""]


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
    technical = meta.get("technical_attempts")
    if technical:
        out.extend(
            [
                f"Cohort agent execution attempts: {technical['cohort_agent_execution_attempts']}; recorded baseline trials: "
                f"{technical['verified_baseline_records']}; unknown technical attempt(s): {technical['unknown_technical_attempts']}. "
                "One replacement was declared before execution; no unknown answer or profile is inferred.",
                "",
            ]
        )
    out.extend(completion_markdown(blocks, recorded_baseline=technical is not None))
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
    plan = recorded_continuation(args.run_dir, load_domains(args.domains))
    sessions = plan.verify_run(args.run_dir, load_domains(args.domains)) if plan else _sessions(args.run_dir)
    summary = scoring.aggregate(sessions)
    validity = args.run_dir / "judge" / "validity.json"
    write_json(
        args.run_dir / "report.json",
        {"run": meta, "judge_validity": read_json(validity) if validity.exists() else None, "summary": summary},
    )
    if plan is not None and plan.data["version"] == 2:
        from continuation_runtime import technical_attempt_summary

        technical = technical_attempt_summary(plan, sessions, repo=meta["repo"])
        report = read_json(args.run_dir / "report.json")
        write_json(args.run_dir / "report.json", report | {"methodology": technical})
        meta = meta | {"technical_attempts": technical}
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


def require_execution_policy(args: argparse.Namespace) -> None:
    recorded = read_json(args.run_dir / "run.json").get("execution_policy")
    if recorded != execution_policy(args):
        raise HarnessError("run uses a different execution policy; fresh sessions and judging are required")
    if read_json(args.run_dir / "run.json").get("budget_round") != budget_round(args):
        raise HarnessError("run belongs to a different budget round; reuse its original shared ledger")
    plan = recorded_continuation(args.run_dir, load_domains(args.domains))
    if plan is not None:
        if args.model != "claude-sonnet-5-5" or (
            hasattr(args, "second_model") and args.second_model != "claude-sonnet-5"
        ):
            raise HarnessError("continuation requires its approved primary and secondary judge models")
        plan.verify_run(args.run_dir, load_domains(args.domains))
        if plan.data["version"] == 2:
            from continuation_runtime import verify_collection_receipts

            verify_collection_receipts(plan, complete=True)


def budget_round(args: argparse.Namespace) -> dict | None:
    if not args.hard_budget:
        return None
    if not args.budget_ledger:
        raise HarnessError("hard execution requires its original shared budget ledger")
    return gateway.Ledger(args.budget_ledger, args.budget_usd).identity()


def execution_policy(args: argparse.Namespace) -> dict:
    if args.hard_budget:
        return {"mode": "hard-gateway", "policy": gateway.manifest(), "policy_sha256": gateway.policy_hash()}
    return {"mode": "soft" if args.allow_soft_budget else "unmetered-injected-test"}


def continuation_parsers(sub) -> None:
    continued = sub.add_parser("continue", help="collect only an explicitly reviewed immutable continuation plan")
    continued.add_argument("--manifest", type=Path, required=True)
    continued.add_argument("--manifest-sha256", required=True)
    continued.add_argument("--repo", type=Path, required=True)
    continued.add_argument("--out", type=Path, required=True)

    combined = sub.add_parser("continue-report", help="verify and aggregate every immutable continuation trial")
    combined.add_argument("--manifest", type=Path, required=True)
    combined.add_argument("--manifest-sha256", required=True)
    combined.add_argument("--run", dest="runs", type=Path, action="append", required=True)
    combined.add_argument("--out", type=Path, required=True)


def result_parsers(sub) -> None:
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


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--domains", type=Path, default=HERE / "domains.toml")
    p.add_argument("--cases-dir", type=Path, default=HERE / "cases")
    p.add_argument("--budget-ledger", type=Path, help="shared SQLite spending ledger for this round")
    p.add_argument("--budget-usd", type=float, default=25.0)
    p.add_argument("--per-call-usd", type=float, default=0.2, help="prospective reservation for soft-budget mode only")
    modes = p.add_mutually_exclusive_group()
    modes.add_argument("--hard-budget", action="store_true", help="require reserved, network-confined egress")
    modes.add_argument(
        "--allow-soft-budget",
        action="store_true",
        help="explicitly accept prospective accounting, not a hard spending ceiling",
    )
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
    r.add_argument("--jobs", type=int, default=1)
    r.add_argument("--resume", action="store_true", help="reuse saved sessions with identical run parameters")
    r.add_argument("--timeout", type=float, default=600.0)
    r.add_argument("--skip-generate", action="store_true", help="the ref has its generated outputs committed")
    r.add_argument("--out", type=Path, required=True)

    continuation_parsers(sub)

    result_parsers(sub)
    return p


def dispatch(
    args: argparse.Namespace, execute: runner.Execute, environ: Mapping[str, str], factory: GraderFactory
) -> int:
    if args.command == "validate-cases":
        return cmd_validate_cases(args)
    if args.command == "run":
        return cmd_run(args, execute, environ)
    if args.command == "continue":
        return cmd_continue(args, execute, environ)
    if args.command == "score":
        return cmd_score(args)
    if args.command == "judge":
        return cmd_judge(args, factory)
    if args.command == "judge-validate":
        return cmd_judge_validate(args, factory)
    if args.command == "report":
        return cmd_report(args)
    if args.command == "continue-report":
        return cmd_continuation_report(args)
    return cmd_compare(args)


def main(
    argv: list[str] | None = None,
    *,
    execute: runner.Execute = runner.subprocess_execute,
    environ: Mapping[str, str] = os.environ,
    grader_factory: GraderFactory | None = None,
) -> int:
    args = parser().parse_args(argv)
    paid = args.command in ("run", "continue") or (
        args.command in ("judge", "judge-validate") and grader_factory is None
    )
    if paid and execute is runner.subprocess_execute and not (args.allow_soft_budget or args.hard_budget):
        print(
            "error: a hard dollar ceiling requires --hard-budget; otherwise explicit --allow-soft-budget consent is required",
            file=sys.stderr,
        )
        return 2
    if paid and (execute is runner.subprocess_execute or args.hard_budget) and not args.budget_ledger:
        print("error: paid execution requires a shared --budget-ledger", file=sys.stderr)
        return 2
    try:
        if args.hard_budget and paid:
            execute = gateway_transport.HardExecute(
                gateway.Ledger(args.budget_ledger, args.budget_usd), environ.get("ANTHROPIC_API_KEY", "")
            )
        elif args.budget_ledger and paid:
            execute = budget.BudgetedExecute(
                args.budget_ledger,
                args.budget_usd,
                args.per_call_usd,
                execute,
                allow_soft_limits=args.allow_soft_budget,
            )
        factory = grader_factory or (lambda model: judge.ClaudeGrader(model, environ=environ, execute=execute))
        return dispatch(args, execute, environ, factory)
    except (HarnessError, runner.RunnerError, cases_mod.CaseError, continuation.ContinuationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
