"""Execute and score only the reviewed continuation plan without rewriting inherited artifacts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from continuation import Plan

from continuation import ContinuationError


def actor_request_ids(ledger) -> set[int]:
    import sqlite3
    from contextlib import closing

    with closing(sqlite3.connect(f"file:{ledger.path}?mode=ro", uri=True)) as db:
        return {
            row[0]
            for row in db.execute(
                "SELECT request FROM hard_request_epochs WHERE epoch=? AND actor=?",
                (ledger.epochs.epoch, ledger.epochs.actor),
            )
        }


def verify_command(plan: Plan, repo: str, argv: list, cwd: Path, environment: dict, timeout: float) -> None:
    import tempfile

    import runner

    if argv.count("--mcp-config") != 1 or len(argv) < 3:
        raise ContinuationError("continuation CLI command differs from its reviewed template")
    mcp = Path(argv[argv.index("--mcp-config") + 1])
    home = mcp.parent
    if (
        mcp.name != "mcp.json"
        or home.parent.resolve() != Path(tempfile.gettempdir()).resolve()
        or not re.fullmatch(r"ctx-home-[A-Za-z0-9_-]+", home.name)
    ):
        raise ContinuationError("MCP path is outside the predetermined fresh-session template")
    if mcp.stat().st_size > 512 or json.loads(mcp.read_text()) != {"mcpServers": {}}:
        raise ContinuationError("continuation requires the original strict empty MCP config")
    if (
        set(environment) != {"PATH", "ANTHROPIC_API_KEY", "HOME", "CLAUDE_CONFIG_DIR"}
        or environment["HOME"] != str(home)
        or environment["CLAUDE_CONFIG_DIR"] != str(home)
    ):
        raise ContinuationError("continuation CLI environment differs from its template")
    config = plan.identities[repo]["config"]
    candidates = [case for case in plan.selected[repo] if case.prompt == argv[2]]
    expected = runner.ClaudeAdapter().command(
        runner.SessionSpec(argv[2], config["model"], config["max_turns"], mcp, runner.DEFAULT_TOOLS)
    )
    if not candidates or argv != expected or timeout != config["timeout"]:
        raise ContinuationError("model, prompt, tools or collection limits changed")
    for case in candidates:
        worktree = cwd
        for _ in Path(case.cwd).parts:
            worktree = worktree.parent
        if (
            cwd == cwd.resolve()
            and cwd == worktree / case.cwd
            and worktree.parent == plan.workspace / ".worktrees" / repo
            and re.fullmatch(r"context-eval-[A-Za-z0-9_-]+", worktree.name)
        ):
            return
    raise ContinuationError("collection cwd is outside the anchored frozen-worktree template")


def next_planned_trial(plan: Plan, repo: str, out: Path) -> tuple:
    import runner

    remaining = [key for key in plan.sessions if key[0] == repo and key not in plan.prior]
    pending = []
    for key in remaining:
        name = runner.session_name(key[1], key[2])
        meta, raw = out / "transcripts" / f"{name}.meta.json", out / "transcripts" / f"{name}.jsonl"
        if meta.exists() != raw.exists():
            raise ContinuationError("fresh trial capture is incomplete; no subsequent trial may start")
        if not meta.exists():
            pending.append(key)
        elif pending:
            raise ContinuationError("fresh trials must remain the exact serialized plan prefix")
    if not pending:
        raise ContinuationError("sealed collection is already complete")
    return pending[0]


class ContinuedExecute:
    def __init__(self, plan: Plan, inner, out: Path, repo: str) -> None:
        self.plan, self.inner, self.out, self.repo = plan, inner, out, repo

    def preflight(self, argv: list, cwd: Path, environment: dict, timeout: float) -> None:
        import runner

        self.plan.recheck()
        if self.plan.data["version"] == 2 and str(self.out.resolve()) != self.plan.data["outputs"][self.repo]:
            raise ContinuationError("collection output is outside the sealed plan")
        if not argv:
            raise ContinuationError("continuation command is empty")
        expected = self.plan.data["next_admission"]
        ledger = self.inner.ledger
        if (ledger.epochs.epoch, ledger.epochs.policy) != (expected["epoch"], expected["policy_sha256"]):
            raise ContinuationError("executor does not own the reviewed admission epoch")
        if Path(argv[0]).name != "claude":
            if argv != ["ai-rulez", "generate", "--no-local"]:
                raise ContinuationError("unreviewed command cannot run inside continuation collection")
            if (
                runner.binary_fingerprint("ai-rulez", environment)
                != self.plan.identities[self.repo]["generator_sha256"]
            ):
                raise ContinuationError("context generator identity changed before generation")
            return
        if json.loads((self.out / "context-identity.json").read_text()) != self.plan.identities[self.repo]:
            raise ContinuationError("fresh generated context identity differs from the original collection")
        verify_command(self.plan, self.repo, argv, cwd, environment, timeout)
        if self.plan.data["version"] == 2:
            key = next_planned_trial(self.plan, self.repo, self.out)
            case = next(case for case in self.plan.selected[self.repo] if case.id == key[1])
            if argv[2] != case.prompt:
                raise ContinuationError("collection command does not match the next sealed trial")

    def __call__(self, argv: list, cwd: Path, environment: dict, timeout: float):
        from dataclasses import replace

        try:
            self.preflight(argv, cwd, environment, timeout)
        except ContinuationError:
            self.inner.ledger.stop("reviewed continuation admission refused")
            raise
        if Path(argv[0]).name != "claude":
            return self.inner(argv, cwd, environment, timeout)
        ledger = self.inner.ledger
        before = actor_request_ids(ledger)
        key = next_planned_trial(self.plan, self.repo, self.out) if self.plan.data["version"] == 2 else None
        result = self.inner(argv, cwd, environment, timeout)
        if key == tuple(self.plan.data.get("technical_attempt", {}).get("session", [])) and (
            (result.returncode or result.timed_out) and not result.bounded_failure
        ):
            ledger.stop("declared technical replacement failed")
        collection = {
            "epoch": ledger.epochs.epoch,
            "policy_sha256": ledger.epochs.policy,
            "actor": ledger.epochs.actor,
            "request_ids": sorted(actor_request_ids(ledger) - before),
        }
        return replace(result, collection=collection)


def verified_collection(plan: Plan, info) -> dict:
    from continuation import ledger_state, require_keys

    collection = require_keys(info.collection, {"epoch", "policy_sha256", "actor", "request_ids"})
    expected = plan.data["next_admission"]
    if type(collection["epoch"]) is not int or any(collection[key] != expected[key] for key in expected):
        raise ContinuationError("fresh trial belongs to another collection policy or epoch")
    ids = collection["request_ids"]
    if (
        not isinstance(ids, list)
        or not ids
        or any(type(value) is not int or value <= 0 for value in ids)
        or sorted(set(ids)) != ids
    ):
        raise ContinuationError("fresh trial has invalid request identities")
    state = ledger_state(plan.ledger)
    rows = {row[0]: row for row in state["requests"]}
    if any(
        value not in rows
        or rows[value][7] != expected["epoch"]
        or rows[value][8] != collection["actor"]
        or rows[value][4] != "settled"
        for value in ids
    ):
        raise ContinuationError("fresh trial billing is not fully settled in its owning epoch")
    return collection


def resolve_local(plan: Plan, repo: str, case_id: str, repeat: int, out: Path) -> tuple:
    from dataclasses import asdict

    import runner
    from continuation import file_hash, validate_raw

    stem = runner.session_name(case_id, repeat)
    raw_path, meta_path = out / "transcripts" / f"{stem}.jsonl", out / "transcripts" / f"{stem}.meta.json"
    if not raw_path.exists():
        return None, None, {}
    info = runner.read_meta(out / "transcripts", case_id, repeat)
    if info is None or raw_path != raw_path.resolve() or meta_path != meta_path.resolve():
        raise ContinuationError("fresh trial has missing metadata or a noncanonical artifact")
    collection = verified_collection(plan, info)
    expected = plan.data["next_admission"]
    ids = collection["request_ids"]
    raw = raw_path.read_text()
    case = next(case for case in plan.selected[repo] if case.id == case_id)
    bounded = validate_raw(raw, asdict(info), case, plan.identities[repo], plan.workspace)
    if info.bounded_failure != (bounded == "certified-max-turns"):
        raise ContinuationError("fresh bounded failure lacks its controller certificate")
    messages = {
        value["message"]["id"]
        for line in raw.splitlines()
        if line.strip()
        for value in [json.loads(line)]
        if value.get("type") == "assistant"
        and isinstance(value.get("message"), dict)
        and isinstance(value["message"].get("id"), str)
    }
    if len(messages) != len(ids):
        raise ContinuationError("fresh model responses do not match their exact settled request slice")
    return (
        raw_path,
        info,
        {
            "epoch": expected["epoch"],
            "policy_sha256": expected["policy_sha256"],
            "round_uuid": plan.data["round"]["uuid"],
            "request_ids": ids,
            "actor": collection["actor"],
            "source_run_dir": str(out),
            "source_run_id": json.loads((out / "run.json").read_text())["run_id"],
            "raw_sha256": file_hash(raw_path),
            "meta_sha256": file_hash(meta_path),
            "manifest_sha256": plan.sha256,
            "adjudication_sha256": None,
        },
    )


def verified_run_metadata(plan: Plan, out: Path) -> dict:
    from dataclasses import asdict

    import cases
    import gateway_epochs
    import runner
    from continuation import controlled_path

    controlled_path(str(out), plan.ledger)
    meta = json.loads((out / "run.json").read_text())
    repo = meta["repo"]
    if repo not in plan.selected:
        raise ContinuationError("unplanned consumer run cannot enter continuation results")
    context = plan.identities[repo]
    expected = {
        "continuation_manifest": {"path": str(plan.path), "sha256": plan.sha256},
        "execution_policy": {
            "mode": "hard-gateway",
            "policy": plan.data["next_manifest"],
            "policy_sha256": plan.data["next_admission"]["policy_sha256"],
        },
        "budget_round": plan.data["round"],
        "admission_epoch": plan.data["next_admission"],
        "commit": plan.data["repos"][repo]["ref"],
        "ref": plan.data["repos"][repo]["ref"],
        "model": context["config"]["model"],
        "repeats": context["config"]["repeats"],
        "max_turns": context["config"]["max_turns"],
        "timeout": context["config"]["timeout"],
        "jobs": 1,
        "split": "tune",
        "case_corpus_hash": cases.corpus_hash(plan.selected[repo]),
        "cases": [case.id for case in plan.selected[repo]],
    }
    if any(meta.get(key) != value for key, value in expected.items()):
        raise ContinuationError("derived run metadata differs from the reviewed continuation")
    if (
        json.loads((out / "context-identity.json").read_text()) != context
        or runner.context_fingerprint(out / "context") != context["context_sha256"]
    ):
        raise ContinuationError("derived context snapshot changed")
    if gateway_epochs.digest(json.loads((out / "cases.json").read_text())) != gateway_epochs.digest(
        [asdict(case) for case in plan.selected[repo]]
    ):
        raise ContinuationError("derived run changed the frozen case or reference facts")
    return meta


def compare_scored_record(actual, expected) -> None:
    from dataclasses import asdict

    first, second = asdict(actual), asdict(expected)
    if set(actual.criteria) != set(expected.criteria) or any(
        type(value) is not bool and value is not None for value in actual.criteria.values()
    ):
        raise ContinuationError("stored criterion schema differs from the frozen scoring corpus")
    if actual.error and any(value is not None for value in actual.criteria.values()):
        raise ContinuationError("a failed nonanswer cannot acquire a judge verdict")
    first.pop("criteria")
    second.pop("criteria")
    if first != second:
        raise ContinuationError("stored session answer, failure, metrics or provenance changed")


def verify_request_partition(plan: Plan, rows: list) -> None:
    from continuation import ledger_state

    claimed = [value for row in rows for value in row.provenance["request_ids"]]
    if len(claimed) != len(set(claimed)):
        raise ContinuationError("multiple trials claim the same provider request")
    fresh = [row for row in rows if row.provenance["epoch"] == plan.data["next_admission"]["epoch"]]
    actors = {row.provenance["actor"] for row in fresh}
    if len(actors) != 1:
        raise ContinuationError("one serialized collection must have exactly one controller actor")
    state = ledger_state(plan.ledger)
    actual = {
        row[0] for row in state["requests"] if row[7] == plan.data["next_admission"]["epoch"] and row[8] in actors
    }
    assigned = {value for row in fresh for value in row.provenance["request_ids"]}
    if assigned != actual:
        raise ContinuationError("collection has unmatched financial requests")


def verify_run(plan: Plan, out: Path, domains: dict) -> list:
    import records
    import runner
    import scoring
    import transcript

    plan.load(plan.path, plan.sha256, plan.corpus, plan.ledger, allow_stopped=True, workspace=plan.workspace)
    meta = verified_run_metadata(plan, out)
    rows = records.read_sessions(out / "sessions.jsonl")
    expected = {(case.id, repeat) for case in plan.selected[meta["repo"]] for repeat in range(meta["repeats"])}
    keys = [(row.case_id, row.repeat) for row in rows]
    if len(keys) != len(set(keys)) or set(keys) != expected:
        raise ContinuationError("derived run is duplicated or incomplete")
    cases = {case.id: case for case in plan.selected[meta["repo"]]}
    for row in rows:
        path, info, provenance = plan.resolve(meta["repo"], row.case_id, row.repeat, out)
        if path is None or info is None:
            raise ContinuationError("expected continuation trial is absent")
        raw = path.read_text()
        expected_row = scoring.score(
            cases[row.case_id],
            transcript.parse(raw),
            domains,
            out / "context",
            run_id=meta["run_id"],
            repeat=row.repeat,
            run_dir=str(out.resolve()),
            error=info.error or runner.tool_profile_error(raw, runner.DEFAULT_TOOLS),
            root=info.root,
            bounded_failure=info.bounded_failure,
            provenance=provenance,
        )
        compare_scored_record(row, expected_row)
    verify_request_partition(plan, rows)
    for row in rows:
        row.criteria = dict.fromkeys(row.criteria)
    from harness import apply_judge

    apply_judge(out, rows)
    return rows


def aggregate(plan: Plan, outputs: list[Path], domains: dict) -> dict:
    import scoring
    from continuation import file_hash, ledger_state

    rows, consumers, sources, collected = [], set(), [], []
    for out in outputs:
        meta = verified_run_metadata(plan, out)
        if meta["repo"] in consumers:
            raise ContinuationError("consumer appears twice in the combined continuation")
        consumers.add(meta["repo"])
        verified = verify_run(plan, out, domains)
        rows.extend(verified)
        collected.extend((meta["repo"], row.case_id, row.repeat) for row in verified)
        sources.append(
            {
                "repo": meta["repo"],
                "path": str(out),
                "run_sha256": file_hash(out / "run.json"),
                "sessions_sha256": file_hash(out / "sessions.jsonl"),
            }
        )
    if consumers != set(plan.selected) or len(collected) != len(plan.sessions) or set(collected) != set(plan.sessions):
        raise ContinuationError("combined continuation does not cover every planned consumer trial")
    claimed = [value for row in rows for value in row.provenance["request_ids"]]
    if len(claimed) != len(set(claimed)):
        raise ContinuationError("combined consumers duplicate a financial request")
    state = ledger_state(plan.ledger)
    charges = {
        name: sum(row[3] for row in state["requests"] if row[4] == name) for name in ("settled", "uncertain", "pending")
    }
    return {
        "version": 1,
        "manifest_sha256": plan.sha256,
        "round": plan.data["round"],
        "expected_trials": len(plan.sessions),
        "collection_complete": True,
        "sources": sources,
        "compatibility": plan.data["compatibility"],
        "summary": scoring.aggregate(rows),
        **({"methodology": technical_attempt_summary(plan, rows)} if plan.data["version"] == 2 else {}),
        "financial": {
            "total_nanos": state["round"]["total_nanos"],
            "upstream_attempts": len(state["requests"]),
            "settled_requests": sum(row[4] == "settled" for row in state["requests"]),
            "uncertain_requests": sum(row[4] == "uncertain" for row in state["requests"]),
            "settled_nanos": charges["settled"],
            "uncertain_reserved_nanos": charges["uncertain"],
            "pending_reserved_nanos": charges["pending"],
            "accounted_nanos": sum(charges.values()),
            "actual_billed_cost_known": not charges["uncertain"],
        },
    }


def technical_attempt_summary(plan: Plan, rows: list, *, repo: str | None = None) -> dict:
    attempt = plan.data["technical_attempt"]
    relevant = repo is None or repo == attempt["session"][0]
    return {
        "protocol": "single-declared-technical-replacement-1",
        "scope": "reviewed baseline collection; earlier invalid protocol attempts remain in financial history",
        "collection_epochs": sorted({row.provenance["epoch"] for row in rows}),
        "verified_baseline_records": len(rows),
        "cohort_agent_execution_attempts": len(rows) + int(relevant),
        "unknown_technical_attempts": int(relevant),
        "declared_replacements": int(relevant),
        "unknown_attempt": attempt if relevant else None,
        "unknown_attempt_outcome_or_profile_known": False,
        "outcome_selection": False,
    }
