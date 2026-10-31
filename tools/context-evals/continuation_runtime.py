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
        if self.plan.data["version"] == 2:
            bind_collection(self.plan, ledger, self.out, self.repo)
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
        if self.plan.data["version"] == 2:
            try:
                key, _ = claim_collection_slot(self.plan, ledger, self.repo, argv, cwd)
            except ContinuationError:
                ledger.stop("reviewed continuation admission refused")
                raise
            try:
                result = self.inner(argv, cwd, environment, timeout)
                return record_collection_completion(self.plan, ledger, key, cwd, result)
            except BaseException:
                ledger.stop("collection execution has no durable completion")
                raise
        before = actor_request_ids(ledger)
        result = self.inner(argv, cwd, environment, timeout)
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
    bounded = validate_raw(raw, asdict(info), case, plan.identities[repo], plan.workspace, allow_tool_unavailable=True)
    if info.bounded_failure != (bounded in ("certified-max-turns", "certified-tool-unavailable")):
        raise ContinuationError("fresh bounded failure lacks its controller certificate")
    messages = model_response_ids(raw)
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


def verified_run_metadata(plan: Plan, out: Path, *, check_context: bool = True) -> dict:
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
    if check_context and (
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

    if plan.data["version"] == 2:
        verify_collection_receipts(plan)

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
    receipts = verify_collection_receipts(plan)
    return {
        "collection_receipt_protocol": "sqlite-append-only-1",
        "collection_actors": {name: owner["actor"] for name, owner in receipts["owners"].items()},
        "durably_completed_collection_slots": len(receipts["completed"]),
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


COLLECTION_TABLES = {
    "context_collection_owners": """CREATE TABLE context_collection_owners (
        epoch INTEGER NOT NULL, repo TEXT NOT NULL CHECK(repo IN ('xberg','sceptre')),
        manifest TEXT NOT NULL, actor TEXT NOT NULL UNIQUE, output TEXT NOT NULL UNIQUE,
        header_sha256 TEXT NOT NULL, PRIMARY KEY(epoch,repo))""",
    "context_collection_receipts": """CREATE TABLE context_collection_receipts (
        seq INTEGER PRIMARY KEY, epoch INTEGER NOT NULL, repo TEXT NOT NULL,
        case_id TEXT NOT NULL, repeat INTEGER NOT NULL CHECK(repeat>=0),
        kind TEXT NOT NULL CHECK(kind IN ('intent','completion')), payload TEXT NOT NULL,
        UNIQUE(epoch,repo,case_id,repeat,kind),
        FOREIGN KEY(epoch,repo) REFERENCES context_collection_owners(epoch,repo))""",
}
COLLECTION_TRIGGERS = {
    f"{table}_no_{operation.lower()}": f"CREATE TRIGGER {table}_no_{operation.lower()} BEFORE {operation} ON {table} "
    "BEGIN SELECT RAISE(ABORT,'immutable operational receipt'); END"
    for table in COLLECTION_TABLES
    for operation in ("UPDATE", "DELETE")
}


def collection_schema(db, *, optional: bool = False) -> bool:
    expected = COLLECTION_TABLES | COLLECTION_TRIGGERS
    actual = dict(
        db.execute(
            "SELECT name,sql FROM sqlite_master WHERE type IN ('table','trigger') AND (tbl_name IN (?,?) OR name LIKE 'context_collection_%')",
            tuple(COLLECTION_TABLES),
        )
    )
    if not actual and optional:
        return False
    if any(not isinstance(sql, str) for sql in actual.values()):
        raise ContinuationError("operational receipt schema contains invalid definitions")
    if {name: " ".join(sql.split()) for name, sql in actual.items()} != {
        name: " ".join(sql.split()) for name, sql in expected.items()
    }:
        raise ContinuationError("operational receipt schema is missing or malformed")
    indexes = {
        "context_collection_owners": {("actor",), ("output",), ("epoch", "repo")},
        "context_collection_receipts": {("epoch", "repo", "case_id", "repeat", "kind")},
    }
    for table, columns in indexes.items():
        rows = db.execute(f'PRAGMA index_list("{table}")').fetchall()
        if any(not re.fullmatch(rf"sqlite_autoindex_{table}_[0-9]+", row[1]) for row in rows):
            raise ContinuationError("unexpected operational receipt index")
        found = {tuple(item[2] for item in db.execute(f'PRAGMA index_info("{row[1]}")')) for row in rows}
        if found != columns or len(rows) != len(columns) or any(row[2] != 1 or row[4] != 0 for row in rows):
            raise ContinuationError("operational receipt uniqueness constraints changed")
    return True


def collection_schema_at(path: Path, *, optional: bool = False) -> bool:
    import sqlite3
    from contextlib import closing

    try:
        with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as db:
            return collection_schema(db, optional=optional)
    except sqlite3.Error as exc:
        raise ContinuationError("operational receipt schema cannot be read") from exc


def initialize_collection_receipts(plan: Plan) -> None:
    import sqlite3
    from contextlib import closing

    from continuation import read_bound_json, validate_financial, validate_header

    data = read_bound_json(plan.path, plan.sha256)
    if data["version"] != 2:
        raise ContinuationError("operational receipts require the exact reviewed extension")
    validate_header(data, plan.ledger)
    validate_financial(data, plan.ledger, before_recovery=False)
    with closing(sqlite3.connect(f"file:{plan.ledger}?mode=rw", uri=True)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        if collection_schema(db, optional=True):
            reconcile_collection(db, plan)
            return
        epoch = data["next_admission"]["epoch"]
        if db.execute("SELECT COUNT(*) FROM hard_request_epochs WHERE epoch=?", (epoch,)).fetchone()[0]:
            raise ContinuationError("receipt initialization cannot hide already executed admission requests")
        for sql in (COLLECTION_TABLES | COLLECTION_TRIGGERS).values():
            db.execute(sql)
        collection_schema(db)


def receipt_json(value: str) -> dict:
    try:
        parsed = json.loads(value)
    except (ValueError, TypeError) as exc:
        raise ContinuationError("operational receipt payload is malformed") from exc
    if not isinstance(parsed, dict):
        raise ContinuationError("operational receipt payload must be an object")
    return parsed


def collection_header(plan: Plan, output: Path, *, context: bool) -> str:
    import gateway_epochs

    try:
        meta = verified_run_metadata(plan, output, check_context=context)
    except (OSError, ValueError, KeyError) as exc:
        raise ContinuationError("collection header or context is missing or changed") from exc
    return gateway_epochs.digest(
        {key: value for key, value in meta.items() if key not in ("judge_model", "finished_at")}
    )


def metadata_digest(meta: dict) -> str:
    import math
    from dataclasses import asdict

    import gateway_epochs
    import runner

    expected = set(asdict(runner.SessionMeta("", 0, "", 0, 0.0)))
    if (
        set(meta) != expected
        or type(meta["seconds"]) not in (int, float)
        or not math.isfinite(meta["seconds"])
        or meta["seconds"] < 0
    ):
        raise ContinuationError("completed trial metadata shape changed")
    return gateway_epochs.digest({key: value for key, value in meta.items() if key != "seconds"})


def completion_artifacts(owner: dict, key: tuple, payload: dict) -> None:
    import runner
    from continuation import file_hash

    name = runner.session_name(key[1], key[2])
    raw = Path(owner["output"]) / "transcripts" / f"{name}.jsonl"
    meta = raw.with_name(f"{name}.meta.json")
    if any(not path.is_file() or path != path.resolve() or path.is_symlink() for path in (raw, meta)):
        raise ContinuationError("consumed trial artifacts are missing or noncanonical")
    try:
        unchanged = (
            file_hash(raw) == payload["stdout_sha256"]
            and metadata_digest(receipt_json(meta.read_text())) == payload["metadata_sha256"]
        )
    except (OSError, ValueError, KeyError) as exc:
        raise ContinuationError("consumed trial evidence is unavailable or malformed") from exc
    if not unchanged:
        raise ContinuationError("consumed trial artifacts changed after execution")


def receipt_ids(value: object) -> list[int]:
    if (
        not isinstance(value, list)
        or any(type(item) is not int or item <= 0 for item in value)
        or value != sorted(set(value))
    ):
        raise ContinuationError("operational receipt request identities changed")
    return value


def receipt_payload(kind: str, value: str) -> dict:
    from continuation import require_hash, require_keys

    item = receipt_json(value)
    if kind == "intent":
        require_keys(item, {"before_request_ids", "cwd", "argv_sha256"})
        receipt_ids(item["before_request_ids"])
        require_hash(item["argv_sha256"])
        if not isinstance(item["cwd"], str) or not Path(item["cwd"]).is_absolute():
            raise ContinuationError("operational intent cwd changed")
    elif kind == "completion":
        require_keys(
            item,
            {
                "request_ids",
                "stdout_sha256",
                "stderr_sha256",
                "metadata_sha256",
                "returncode",
                "timed_out",
                "bounded_failure",
                "certified",
            },
        )
        receipt_ids(item["request_ids"])
        for name in ("stdout_sha256", "stderr_sha256", "metadata_sha256"):
            require_hash(item[name])
        if type(item["returncode"]) is not int or any(
            type(item[name]) is not bool for name in ("timed_out", "bounded_failure", "certified")
        ):
            raise ContinuationError("operational completion semantics changed")
    else:
        raise ContinuationError("unknown operational receipt event")
    return item


def receipt_owners(db, plan: Plan, receipts: list) -> dict:
    from continuation import require_hash

    owners = {}
    for row in db.execute("SELECT epoch,repo,manifest,actor,output,header_sha256 FROM context_collection_owners"):
        epoch, repo, manifest, actor, output, header = row
        if (
            epoch != plan.data["next_admission"]["epoch"]
            or repo not in plan.selected
            or manifest != plan.sha256
            or output != plan.data["outputs"][repo]
        ):
            raise ContinuationError("collection epoch or consumer is already owned by another sealed plan")
        if not isinstance(actor, str) or not actor or repo in owners:
            raise ContinuationError("collection actor ownership changed")
        context = any(item[2] == repo for item in receipts)
        if require_hash(header) != collection_header(plan, Path(output), context=context):
            raise ContinuationError("collection header changed after actor admission")
        owners[repo] = {"actor": actor, "output": output}
    return owners


def financial_collection_rows(db, plan: Plan) -> dict:
    epoch = plan.data["next_admission"]["epoch"]
    return {
        row[0]: (row[1], row[2])
        for row in db.execute(
            "SELECT r.id,r.state,e.actor FROM hard_requests r JOIN hard_request_epochs e ON e.request=r.id WHERE e.epoch=?",
            (epoch,),
        )
    }


def validate_receipt_event(row: tuple, index: int, plan: Plan, owners: dict) -> tuple:
    seq, epoch, repo, case_id, repeat, kind, text = row
    if (
        seq != index + 1
        or epoch != plan.data["next_admission"]["epoch"]
        or repo not in owners
        or type(repeat) is not int
    ):
        raise ContinuationError("operational receipt sequence or ownership changed")
    return (repo, case_id, repeat), owners[repo]["actor"], kind, receipt_payload(kind, text)


def reconcile_collection(db, plan: Plan, *, pending_for: tuple | None = None) -> dict:
    collection_schema(db)
    events = db.execute(
        "SELECT seq,epoch,repo,case_id,repeat,kind,payload FROM context_collection_receipts ORDER BY seq"
    ).fetchall()
    owners = receipt_owners(db, plan, events)
    financial = financial_collection_rows(db, plan)
    order = [key for key in plan.sessions if key not in plan.prior]
    completed, claimed, pending = [], {item["actor"]: set() for item in owners.values()}, None
    for index, row in enumerate(events):
        key, actor, kind, payload = validate_receipt_event(row, index, plan, owners)
        repo = key[0]
        if kind == "intent":
            if (
                pending is not None
                or len(completed) >= len(order)
                or key != order[len(completed)]
                or payload["before_request_ids"] != sorted(claimed[actor])
            ):
                raise ContinuationError("collection intents are not the exact durable plan prefix")
            pending = key, payload, actor
        else:
            if pending is None or key != pending[0] or not payload["certified"] or not payload["request_ids"]:
                raise ContinuationError("collection completion is missing or uncertified")
            if any(
                value in claimed[actor] or financial.get(value) != ("settled", actor)
                for value in payload["request_ids"]
            ):
                raise ContinuationError("completed collection receipt does not own its settled requests")
            completion_artifacts(owners[repo], key, payload)
            claimed[actor].update(payload["request_ids"])
            completed.append(key)
            pending = None
    state = {
        "owners": owners,
        "completed": completed,
        "pending": pending,
        "claimed": claimed,
        "next": order[len(completed)] if len(completed) < len(order) else None,
        "financial": financial,
    }
    validate_receipt_financial(state, pending_for)
    return state


def validate_receipt_financial(state: dict, pending_for: tuple | None) -> None:
    pending, claimed, financial = state["pending"], state["claimed"], state["financial"]
    if pending is not None and pending_for != (pending[0], pending[2]):
        raise ContinuationError("an admitted collection slot has not durably completed")
    for actor, ids in claimed.items():
        actual = {value for value, (_, owner) in financial.items() if owner == actor}
        if pending is None or actor != pending[2]:
            if actual != ids:
                raise ContinuationError("collection actor has unreceipted financial requests")
        elif not ids <= actual:
            raise ContinuationError("prior completed requests disappeared")
    if state["next"] is not None and any(actor not in claimed for _, actor in financial.values()):
        raise ContinuationError("unowned admission requests precede completion of the collection")


def collection_transaction(plan: Plan):
    import sqlite3
    from contextlib import closing, contextmanager

    @contextmanager
    def transaction():
        with closing(sqlite3.connect(f"file:{plan.ledger}?mode=rw", uri=True)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            try:
                db.execute("BEGIN IMMEDIATE")
                yield db
                db.commit()
            except sqlite3.Error as exc:
                db.rollback()
                raise ContinuationError("operational receipt transaction refused") from exc
            except BaseException:
                db.rollback()
                raise

    return transaction()


def bind_collection(plan: Plan, ledger, output: Path, repo: str) -> dict:
    with collection_transaction(plan) as db:
        state = reconcile_collection(db, plan)
        owner = state["owners"].get(repo)
        if owner is not None:
            if owner["actor"] != ledger.epochs.actor:
                raise ContinuationError("consumer collection is already owned by another actor")
            return state
        if (
            state["next"] is None
            or state["next"][0] != repo
            or any(item["actor"] == ledger.epochs.actor for item in state["owners"].values())
        ):
            raise ContinuationError("collection actor or consumer order is already bound")
        if str(output.resolve()) != plan.data["outputs"][repo]:
            raise ContinuationError("collection output differs from its durable binding")
        db.execute(
            "INSERT INTO context_collection_owners VALUES(?,?,?,?,?,?)",
            (
                ledger.epochs.epoch,
                repo,
                plan.sha256,
                ledger.epochs.actor,
                str(output),
                collection_header(plan, output, context=False),
            ),
        )
        return reconcile_collection(db, plan)


def claim_collection_slot(plan: Plan, ledger, repo: str, argv: list, cwd: Path) -> tuple:
    import gateway_epochs

    with collection_transaction(plan) as db:
        state = reconcile_collection(db, plan)
        key = state["next"]
        if key is None or key[0] != repo or state["owners"].get(repo, {}).get("actor") != ledger.epochs.actor:
            raise ContinuationError("collection slot is consumed or owned by another actor")
        case = next(case for case in plan.selected[repo] if case.id == key[1])
        if argv[2] != case.prompt:
            raise ContinuationError("paid command differs from the next durable collection slot")
        before = sorted(state["claimed"][ledger.epochs.actor])
        payload = {"before_request_ids": before, "cwd": str(cwd), "argv_sha256": gateway_epochs.digest(argv)}
        db.execute(
            "INSERT INTO context_collection_receipts(epoch,repo,case_id,repeat,kind,payload) VALUES(?,?,?,?,?,?)",
            (ledger.epochs.epoch, *key, "intent", json.dumps(payload, sort_keys=True)),
        )
        return key, before


def model_response_ids(raw: str) -> set[str]:
    import tool_unavailable

    return set(tool_unavailable.native_response_ids(raw))


def completion_payload(plan: Plan, key: tuple, cwd: Path, result) -> dict:
    import hashlib
    from dataclasses import asdict

    import runner
    from continuation import validate_raw

    case = next(case for case in plan.selected[key[0]] if case.id == key[1])
    parent = plan.workspace / ".worktrees" / key[0]
    root = next((path for path in (cwd, *cwd.parents) if path.parent == parent), None)
    if root is None:
        raise ContinuationError("completion root is outside its frozen worktree template")
    error = runner.session_error(result, runner.DEFAULT_TOOLS)
    meta = runner.SessionMeta(
        key[1],
        key[2],
        str(root),
        result.returncode,
        0.0,
        error,
        result.stderr[-runner.STDERR_TAIL :],
        result.bounded_failure,
        result.collection,
    )
    valid = True
    try:
        bounded = validate_raw(
            result.stdout, asdict(meta), case, plan.identities[key[0]], plan.workspace, allow_tool_unavailable=True
        )
        valid = (
            result.bounded_failure == (bounded in ("certified-max-turns", "certified-tool-unavailable"))
            and not result.timed_out
            and len(model_response_ids(result.stdout)) == len(result.collection["request_ids"])
        )
    except (ContinuationError, runner.RunnerError, ValueError, KeyError, TypeError):
        valid = False
    return {
        "request_ids": result.collection["request_ids"],
        "stdout_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
        "stderr_sha256": hashlib.sha256(result.stderr.encode()).hexdigest(),
        "metadata_sha256": metadata_digest(asdict(meta)),
        "returncode": result.returncode,
        "timed_out": result.timed_out,
        "bounded_failure": result.bounded_failure,
        "certified": valid,
    }


def record_collection_completion(plan: Plan, ledger, key: tuple, cwd: Path, result):
    from dataclasses import replace

    with collection_transaction(plan) as db:
        state = reconcile_collection(db, plan, pending_for=(key, ledger.epochs.actor))
        if state["pending"] is None or state["pending"][0] != key:
            raise ContinuationError("completion has no durable admitted slot")
        before = set(state["pending"][1]["before_request_ids"])
        ids = sorted(
            value
            for value, (_, actor) in state["financial"].items()
            if actor == ledger.epochs.actor and value not in before
        )
        collection = {
            "epoch": ledger.epochs.epoch,
            "policy_sha256": ledger.epochs.policy,
            "actor": ledger.epochs.actor,
            "request_ids": ids,
        }
        completed = replace(result, collection=collection)
        payload = completion_payload(plan, key, cwd, completed)
        payload["certified"] = (
            payload["certified"]
            and bool(ids)
            and all(state["financial"][value] == ("settled", ledger.epochs.actor) for value in ids)
        )
        encoded = json.dumps(payload, sort_keys=True)
        receipt_payload("completion", encoded)
        db.execute(
            "INSERT INTO context_collection_receipts(epoch,repo,case_id,repeat,kind,payload) VALUES(?,?,?,?,?,?)",
            (ledger.epochs.epoch, *key, "completion", encoded),
        )
    if not payload["certified"]:
        ledger.stop("collection result could not be certified by its durable receipt")
    return completed


def verify_collection_receipts(plan: Plan, *, complete: bool = False) -> dict:
    import sqlite3
    from contextlib import closing

    with closing(sqlite3.connect(f"file:{plan.ledger}?mode=ro", uri=True)) as db:
        state = reconcile_collection(db, plan)
    if complete and state["next"] is not None:
        raise ContinuationError("all sealed collection slots must complete before paid judging")
    return state
