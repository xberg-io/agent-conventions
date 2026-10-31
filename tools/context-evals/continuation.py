"""Explicit immutable session plans for reviewed same-round continuation."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

UNKNOWN_ATTEMPT_REQUESTS = 5


class ContinuationError(ValueError):
    pass


def require_keys(value: object, keys: set[str]) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise ContinuationError("continuation object has missing or unknown fields")
    return value


def require_hash(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ContinuationError("continuation requires an exact SHA-256 digest")
    return value


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_bound_json(path: Path, expected: str) -> dict | list:
    if path.is_symlink() or path != path.resolve():
        raise ContinuationError("continuation artifact must be canonical")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != require_hash(expected):
        raise ContinuationError("immutable continuation artifact changed")
    return json.loads(data)


def validate_source(value: object) -> dict:
    source = require_keys(value, {"raw_sha256", "meta_sha256", "adjudication", "request_ids"})
    require_hash(source["raw_sha256"])
    require_hash(source["meta_sha256"])
    ids = source["request_ids"]
    if (
        not isinstance(ids, list)
        or not ids
        or any(type(value) is not int or value <= 0 for value in ids)
        or sorted(set(ids)) != ids
    ):
        raise ContinuationError("inherited request identities must be positive, unique and ordered")
    if source["adjudication"] not in (None, "certified-max-turns"):
        raise ContinuationError("unknown continuation adjudication")
    return source


def validate_session_plan(plan: object, expected: set[tuple], prior: set[tuple]) -> dict[tuple, dict]:
    if not isinstance(plan, list) or not expected or not prior <= expected:
        raise ContinuationError("nonempty complete session plan is required")
    output = {}
    for value in plan:
        row = require_keys(value, {"repo", "case_id", "repeat", "source"})
        if (
            not isinstance(row["repo"], str)
            or not isinstance(row["case_id"], str)
            or type(row["repeat"]) is not int
            or row["repeat"] < 0
        ):
            raise ContinuationError("session tuple has invalid types")
        key = row["repo"], row["case_id"], row["repeat"]
        if key in output or key not in expected:
            raise ContinuationError("duplicated or unplanned continuation trial")
        if (key in prior) != (row["source"] is not None):
            raise ContinuationError("every prior trial must be retained exactly once")
        if row["source"] is not None:
            validate_source(row["source"])
        output[key] = row
    if set(output) != expected:
        raise ContinuationError("continuation plan is missing expected trials")
    return output


def validate_technical_attempt(
    value: object, requests: list, order: list, prior: set, claimed: set, epoch: int
) -> dict:
    item = require_keys(
        value, {"kind", "session", "epoch", "actor", "request_ids", "charge_nanos", "replacement_executions"}
    )
    session = item["session"]
    ids = item["request_ids"]
    if (
        not isinstance(session, list)
        or len(session) != 3
        or not all(isinstance(value, str) for value in session[:2])
        or type(session[2]) is not int
        or session[2] < 0
        or not isinstance(ids, list)
        or any(type(value) is not int or value <= 0 for value in ids)
    ):
        raise ContinuationError("technical attempt requires a typed session tuple and integer request identities")
    remaining = [key for key in order if key not in prior]
    if not remaining or set(order[: len(prior)]) != prior or item["session"] != list(remaining[0]):
        raise ContinuationError("technical replacement must be the next interrupted tuple after every completed trial")
    if (
        item["kind"] != "interrupted-unknown"
        or type(item["epoch"]) is not int
        or item["epoch"] != epoch
        or type(item["replacement_executions"]) is not int
        or item["replacement_executions"] != 1
        or not isinstance(item["actor"], str)
        or not item["actor"]
    ):
        raise ContinuationError("only one explicit unknown technical attempt and replacement are supported")
    rows = [row for row in requests if row[7] == epoch]
    unassigned = [row for row in rows if row[0] not in claimed]
    ids = [row[0] for row in unassigned]
    completed = [row[0] for row in rows if row[0] in claimed]
    if (
        len(ids) != UNKNOWN_ATTEMPT_REQUESTS
        or item["request_ids"] != ids
        or not completed
        or min(ids) <= max(completed)
        or any(row[4] != "settled" or row[8] != item["actor"] for row in rows)
        or type(item["charge_nanos"]) is not int
        or item["charge_nanos"] != sum(row[3] for row in unassigned)
    ):
        raise ContinuationError("unknown technical attempt must retain the exact five trailing settled orphan charges")
    return item


def ledger_state(path: Path) -> dict:
    import sqlite3
    from contextlib import closing

    import gateway_epochs

    if not path.is_file() or path.is_symlink() or path != path.resolve():
        raise ContinuationError("continuation requires the original canonical ledger")
    with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as db:
        identity = gateway_epochs.root_identity(db)[0]
        history = gateway_epochs.history(db, identity, ContinuationError)
        gateway_epochs.validate_bindings(db, history, ContinuationError)
        rows = db.execute(
            "SELECT r.id,r.model,r.max_tokens,r.charge,r.state,r.owner,r.birth,e.epoch,e.actor FROM hard_requests r JOIN hard_request_epochs e ON e.request=r.id ORDER BY r.id"
        ).fetchall()
        stops = dict(db.execute("SELECT epoch,reason FROM hard_epoch_stops"))
    if identity["ledger_path"] != str(path):
        raise ContinuationError("ledger canonical identity changed")
    return {
        "round": identity,
        "history": history,
        "requests": rows,
        "stops": stops,
        "requests_sha256": gateway_epochs.digest(rows),
    }


def admission(value: object, *, audited: bool) -> dict:
    keys = {"epoch", "policy_sha256", "audit_hash"} if audited else {"epoch", "policy_sha256"}
    result = require_keys(value, keys)
    if type(result["epoch"]) is not int or result["epoch"] < 0:
        raise ContinuationError("admission epoch must be a nonnegative integer")
    require_hash(result["policy_sha256"])
    if audited:
        require_hash(result["audit_hash"])
    return result


def recovery_approval(data: dict) -> dict:
    import gateway_epochs

    return {
        "reviewed_ref": data["reviewed_ref"],
        "round": data["round"],
        "previous_policy": gateway_epochs.digest(data["previous_manifest"]),
        "next_policy": gateway_epochs.digest(data["next_manifest"]),
        "previous_admission": {key: data["previous_admission"][key] for key in ("epoch", "audit_hash")},
        "reason": "protocol-compatibility-recovery",
    }


def validate_financial(
    plan: dict, path: Path, *, before_recovery: bool, allow_stopped: bool = False, historical: bool = False
) -> dict:
    import gateway
    import gateway_epochs

    state = ledger_state(path)
    previous = admission(plan["previous_admission"], audited=True)
    following = admission(plan["next_admission"], audited=False)
    if plan["round"] != state["round"] or following["epoch"] != previous["epoch"] + 1:
        raise ContinuationError("continuation round or epoch sequence changed")
    if not gateway_epochs.equal_bounds(plan["previous_manifest"], plan["next_manifest"]):
        raise ContinuationError("continuation cannot change financial bounds")
    if following["policy_sha256"] != gateway_epochs.digest(plan["next_manifest"]) or (
        not historical and plan["next_manifest"] != gateway.manifest()
    ):
        raise ContinuationError("continuation requires the exact current controller policy")
    if previous["epoch"] >= len(state["history"]):
        raise ContinuationError("prior admission epoch is absent")
    original = state["history"][previous["epoch"]]
    if any(previous[key] != original[key] for key in previous) or original["manifest"] != plan["previous_manifest"]:
        raise ContinuationError("prior policy or audit hash changed")
    rows = [row for row in state["requests"] if row[7] <= previous["epoch"]]
    if gateway_epochs.digest(rows) != require_hash(plan["prior_requests_sha256"]):
        raise ContinuationError("original charges or request provenance changed")
    collected = [row for row in rows if row[7] == previous["epoch"]]
    if not collected or any(row[4] != "settled" for row in collected):
        raise ContinuationError("every prior collection request must already be settled")
    if historical and following["epoch"] >= len(state["history"]):
        raise ContinuationError("historical next admission is absent")
    active = state["history"][following["epoch"]] if historical else state["history"][-1]
    expected = previous if before_recovery else following
    if any(expected[key] != active[key] for key in expected):
        raise ContinuationError("reviewed continuation admission is not current")
    if before_recovery:
        if active["epoch"] not in state["stops"]:
            raise ContinuationError("draft recovery requires the observed stopped epoch")
    elif (active["epoch"] in state["stops"] and not (allow_stopped or historical)) or active[
        "approval"
    ] != recovery_approval(plan):
        raise ContinuationError("continuation is stopped or uses an unreviewed transition")
    return state


def prior_metadata(root: Path, hashes: dict, selected: list, ref: str, identity: dict) -> dict:
    from dataclasses import asdict

    import cases
    import gateway_epochs
    import runner

    require_keys(hashes, {"run.json", "cases.json", "context-identity.json"})
    meta = read_bound_json(root / "run.json", hashes["run.json"])
    snapshots = read_bound_json(root / "cases.json", hashes["cases.json"])
    stored = read_bound_json(root / "context-identity.json", hashes["context-identity.json"])
    if stored != identity or gateway_epochs.digest(snapshots) != gateway_epochs.digest(
        [asdict(case) for case in selected]
    ):
        raise ContinuationError("original context or case facts do not match the reviewed corpus")
    config = identity["config"]
    expected = {
        "repo": selected[0].repo,
        "commit": ref,
        "model": config["model"],
        "split": "tune",
        "repeats": config["repeats"],
        "max_turns": config["max_turns"],
        "timeout": config["timeout"],
        "allowed_tools": list(runner.DEFAULT_TOOLS),
        "tool_profile_version": runner.TOOL_PROFILE_VERSION,
        "case_corpus_hash": cases.corpus_hash(selected),
        "cases": [case.id for case in selected],
        "harness_version": "5",
        "jobs": 1,
    }
    if any(meta.get(key) != value for key, value in expected.items()):
        raise ContinuationError("original run uses different refs, prompts, model or collection settings")
    return meta


def validate_raw(raw: str, meta: dict, case, identity: dict, workspace: Path) -> str | None:
    import gateway_transport
    import runner
    import transcript

    worktree = Path(meta["root"])
    expected_parent = workspace / ".worktrees" / case.repo
    if worktree.parent != expected_parent or not re.fullmatch(r"context-eval-[A-Za-z0-9_-]+", worktree.name):
        raise ContinuationError("original worktree does not match the anchored evaluation template")
    events = [gateway_transport.decode_json(line.encode()) for line in raw.splitlines() if line.strip()]
    init = [value for value in events if value.get("type") == "system" and value.get("subtype") == "init"]
    config = identity["config"]
    gate = gateway_transport.InitGate(config["model"], runner.DEFAULT_TOOLS)
    if len(init) != 1:
        raise ContinuationError("original transcript must have exactly one initialization")
    gate.observe(json.dumps(init[0]))
    if (
        not gate.valid
        or init[0].get("cwd") != str(worktree / case.cwd)
        or runner.tool_profile_error(raw, runner.DEFAULT_TOOLS)
    ):
        raise ContinuationError("original initialization, anchored cwd or tool profile differs")
    if meta.get("error") or type(meta["returncode"]) is not int:
        raise ContinuationError("original session contains an unclassified infrastructure failure")
    parsed = transcript.parse(raw)
    if meta["returncode"] == 0 and not parsed.error:
        return None
    result = runner.Completed(meta["returncode"], raw, meta.get("stderr", ""))
    if not gateway_transport.maximum_turn_failure(result, config["max_turns"]):
        raise ContinuationError("unknown failed trial cannot receive a bounded-failure adjudication")
    return "certified-max-turns"


def validate_prior_run(root: Path, hashes: dict, selected: list, ref: str, identity: dict, *, workspace: Path) -> dict:
    import runner

    if not selected or root != root.resolve() or root.is_symlink():
        raise ContinuationError("original run root must be canonical and nonempty")
    prior_metadata(root, hashes, selected, ref, identity)
    available = {case.id: case for case in selected}
    output, raw_paths = {}, set()
    for path in sorted((root / "transcripts").glob("*.meta.json")):
        if path.is_symlink() or path != path.resolve():
            raise ContinuationError("original metadata cannot be a symlink")
        meta = json.loads(path.read_text())
        if (
            meta["case_id"] not in available
            or type(meta["repeat"]) is not int
            or not 0 <= meta["repeat"] < identity["config"]["repeats"]
        ):
            raise ContinuationError("original trial is outside the reviewed corpus")
        case = available[meta["case_id"]]
        stem = runner.session_name(case.id, meta["repeat"])
        raw_path = root / "transcripts" / f"{stem}.jsonl"
        if (
            path.name != f"{stem}.meta.json"
            or raw_path.is_symlink()
            or raw_path != raw_path.resolve()
            or not raw_path.is_file()
        ):
            raise ContinuationError("original trial file mapping is inconsistent")
        adjudication = validate_raw(raw_path.read_text(), meta, case, identity, workspace)
        key = case.repo, case.id, meta["repeat"]
        if key in output:
            raise ContinuationError("duplicated original trial")
        output[key] = {
            "root": root,
            "meta": meta,
            "raw_path": raw_path,
            "meta_path": path,
            "source": {"raw_sha256": file_hash(raw_path), "meta_sha256": file_hash(path), "adjudication": adjudication},
        }
        raw_paths.add(raw_path)
    if not output or set((root / "transcripts").glob("*.jsonl")) != raw_paths:
        raise ContinuationError("every original raw transcript and metadata pair must be retained")
    return output


def bind_prior_requests(prior: dict, selected: list, repeats: int, state: dict, epoch: int) -> None:
    order = [(case.repo, case.id, repeat) for case in selected for repeat in range(repeats)]
    if set(order[: len(prior)]) != set(prior):
        raise ContinuationError("prior trials must be the complete serialized collection prefix")
    requests = [row for row in state["requests"] if row[7] == epoch]
    if not requests or len({row[8] for row in requests}) != 1 or any(row[4] != "settled" for row in requests):
        raise ContinuationError("original collection must have one fully settled actor")
    cursor, seen = 0, set()
    for key in order[: len(prior)]:
        row = prior[key]
        events = [json.loads(line) for line in row["raw_path"].read_text().splitlines() if line.strip()]
        messages = {
            event["message"]["id"]
            for event in events
            if event.get("type") == "assistant"
            and isinstance(event.get("message"), dict)
            and isinstance(event["message"].get("id"), str)
        }
        if not messages or seen & messages:
            raise ContinuationError("original response identities are missing or reused")
        seen.update(messages)
        assigned = requests[cursor : cursor + len(messages)]
        if len(assigned) != len(messages):
            raise ContinuationError("original response has no settled accounting row")
        row["request_ids"] = [request[0] for request in assigned]
        cursor += len(messages)
    if cursor != len(requests):
        raise ContinuationError("original settled accounting contains unmatched requests")


def selected_cases(corpus: list) -> dict:
    import cases

    selected = {name: cases.select(corpus, repo=name, pattern="*", split="tune") for name in ("xberg", "sceptre")}
    if any(not values for values in selected.values()):
        raise ContinuationError("both consumer corpora must contain real tune cases")
    return selected


def fingerprints(root: Path) -> dict:
    return {name: file_hash(root / name) for name in ("run.json", "cases.json", "context-identity.json")}


def controlled_path(value: object, ledger: Path) -> Path:
    if not isinstance(value, str):
        raise ContinuationError("artifact path must be an absolute canonical string")
    path = Path(value)
    if not path.is_absolute() or path != path.resolve() or not path.is_relative_to(ledger.parent):
        raise ContinuationError("continuation artifacts must remain inside the original private round")
    return path


def context_identities(preflight: dict, base: dict, selected: dict) -> dict:
    import cases
    import runner

    expected = {
        "model": "claude-sonnet-5-5",
        "max_turns": preflight["max_turns"],
        "timeout": float(preflight["timeout_seconds"]),
        "repeats": preflight["repeats"],
        "allowed_tools": list(runner.DEFAULT_TOOLS),
        "generate": True,
    }
    if (
        base["config"] != expected
        or base["tool_profile_version"] != runner.TOOL_PROFILE_VERSION
        or preflight["jobs"] != 1
    ):
        raise ContinuationError("collection config is not the original serialized read-only profile")
    if (
        base["agent_sha256"] != preflight["tools"]["claude_sha256"]
        or base["generator_sha256"] != preflight["tools"]["ai_rulez_sha256"]
    ):
        raise ContinuationError("original CLI or context-generator fingerprint changed")
    output = {}
    for name, values in selected.items():
        check = preflight["checks"][name]
        if (
            cases.corpus_hash(values) != check["case_corpus_hash"]
            or len(values) * expected["repeats"] != check["expected_sessions"]
        ):
            raise ContinuationError("original case corpus or expected trial count changed")
        output[name] = base | {"context_sha256": require_hash(check["context_sha256"])}
    if output["xberg"] != base:
        raise ContinuationError("original Xberg context differs from its frozen preflight")
    return output


def adjudications(data: dict, prior: dict) -> list:
    import gateway_epochs

    output = []
    for key, row in sorted(prior.items()):
        if row["source"]["adjudication"] is None:
            continue
        payload = {
            "kind": "certified-max-turns",
            "session": list(key),
            "round": data["round"],
            "admission": data["previous_admission"],
            "source": row["source"] | {"request_ids": row["request_ids"]},
            "billing_sha256": data["prior_requests_sha256"],
            "case_corpus_hash": data["repos"][key[0]]["case_corpus_hash"],
        }
        output.append({"payload": payload, "sha256": gateway_epochs.digest(payload)})
    return output


def draft_header(state: dict, preflight_path: Path, reviewed_ref: str) -> dict:
    import gateway

    old = state["history"][-1]
    data = {
        "version": 1,
        "reviewed_ref": reviewed_ref,
        "round": state["round"],
        "previous_admission": {key: old[key] for key in ("epoch", "policy_sha256", "audit_hash")},
        "next_admission": {"epoch": old["epoch"] + 1, "policy_sha256": gateway.policy_hash()},
        "previous_manifest": old["manifest"],
        "next_manifest": gateway.manifest(),
        "prior_requests_sha256": state["requests_sha256"],
        "preflight": {"path": str(preflight_path), "sha256": file_hash(preflight_path)},
        "repos": {},
        "sessions": [],
    }
    return data


def make_draft(
    preflight_path: Path, sources: dict, ledger: Path, reviewed_ref: str, corpus: list, *, workspace: Path
) -> dict:
    import cases
    import continuation_compat

    state = ledger_state(ledger)
    old = state["history"][-1]
    preflight = json.loads(preflight_path.read_text())
    selected = selected_cases(corpus)
    root = sources["xberg"].resolve()
    identities = context_identities(preflight, json.loads((root / "context-identity.json").read_text()), selected)
    data = draft_header(state, preflight_path, reviewed_ref)
    prior = {}
    for name, values in selected.items():
        source = (
            {"root": str(sources[name].resolve()), "files": fingerprints(sources[name])} if name in sources else None
        )
        data["repos"][name] = {
            "ref": preflight["refs"][name],
            "case_corpus_hash": cases.corpus_hash(values),
            "context_identity": identities[name],
            "source": source,
        }
        if source:
            rows = validate_prior_run(
                Path(source["root"]),
                source["files"],
                values,
                preflight["refs"][name],
                identities[name],
                workspace=workspace,
            )
            bind_prior_requests(rows, values, identities[name]["config"]["repeats"], state, old["epoch"])
            prior.update(rows)
    for name, values in selected.items():
        for case in values:
            for repeat in range(identities[name]["config"]["repeats"]):
                key = name, case.id, repeat
                source = prior[key]["source"] | {"request_ids": prior[key]["request_ids"]} if key in prior else None
                data["sessions"].append({"repo": name, "case_id": case.id, "repeat": repeat, "source": source})
    data["compatibility"] = continuation_compat.proof(preflight["controller_commit"], reviewed_ref)
    data["adjudications"] = adjudications(data, prior)
    return data


def validate_context_sources(
    data: dict, preflight: dict, selected: dict, state: dict, ledger: Path, workspace: Path
) -> tuple:
    import cases
    import gateway_epochs

    require_keys(data["repos"], {"xberg", "sceptre"})
    original = data["repos"]["xberg"]["source"]
    require_keys(original, {"root", "files"})
    root = controlled_path(original["root"], ledger)
    base = read_bound_json(root / "context-identity.json", original["files"]["context-identity.json"])
    require_keys(base, {"tool_profile_version", "context_sha256", "config", "agent_sha256", "generator_sha256"})
    identities = context_identities(preflight, base, selected)
    prior = {}
    for name, values in selected.items():
        entry = require_keys(data["repos"][name], {"ref", "case_corpus_hash", "context_identity", "source"})
        if entry["ref"] != preflight["refs"][name] or not re.fullmatch(r"[0-9a-f]{40}", entry["ref"]):
            raise ContinuationError("original frozen consumer ref changed")
        if entry["case_corpus_hash"] != cases.corpus_hash(values) or entry["context_identity"] != identities[name]:
            raise ContinuationError("consumer corpus or generated-context identity changed")
        if entry["source"] is None:
            continue
        if name != "xberg":
            raise ContinuationError("this continuation cannot import an unreviewed second collection")
        source = require_keys(entry["source"], {"root", "files"})
        source_root = controlled_path(source["root"], ledger)
        meta = read_bound_json(source_root / "run.json", source["files"]["run.json"])
        expected_policy = {
            "mode": "hard-gateway",
            "policy": data["previous_manifest"],
            "policy_sha256": gateway_epochs.digest(data["previous_manifest"]),
        }
        if meta.get("execution_policy") != expected_policy or meta.get("budget_round") != data["round"]:
            raise ContinuationError("original sessions belong to another policy or financial round")
        rows = validate_prior_run(
            source_root, source["files"], values, entry["ref"], identities[name], workspace=workspace
        )
        bind_prior_requests(
            rows, values, identities[name]["config"]["repeats"], state, data["previous_admission"]["epoch"]
        )
        prior.update(rows)
    return identities, prior


def validate_header(data: object, ledger: Path, *, historical: bool = False) -> dict:
    import gateway

    keys = {
        "version",
        "reviewed_ref",
        "round",
        "previous_admission",
        "next_admission",
        "previous_manifest",
        "next_manifest",
        "prior_requests_sha256",
        "preflight",
        "repos",
        "sessions",
        "compatibility",
        "adjudications",
    }
    if isinstance(data, dict) and data.get("version") == 2:
        keys |= {"ancestor", "extension_source", "technical_attempt", "outputs"}
    plan = require_keys(data, keys)
    if (
        type(plan["version"]) is not int
        or plan["version"] not in (1, 2)
        or not isinstance(plan["reviewed_ref"], str)
        or not re.fullmatch(r"[0-9a-f]{40}", plan["reviewed_ref"])
    ):
        raise ContinuationError("unknown continuation protocol or reviewed source ref")
    identity = require_keys(plan["round"], {"uuid", "ledger_path", "total_nanos"})
    if type(identity["total_nanos"]) is not int or not 0 < identity["total_nanos"] <= 25_000_000_000:
        raise ContinuationError("continuation ceiling is invalid")
    if identity["ledger_path"] != str(ledger):
        raise ContinuationError("continuation must use its original canonical ledger")
    if historical:
        verify_historical_source(plan["reviewed_ref"], plan["next_manifest"])
    else:
        gateway.verify_reviewed_source(plan["reviewed_ref"])
    item = require_keys(plan["preflight"], {"path", "sha256"})
    return read_bound_json(controlled_path(item["path"], ledger), item["sha256"])


def verify_historical_source(ref: str, manifest: dict) -> None:
    import subprocess

    import gateway

    files = gateway.manifest()["source_files"]
    if manifest.get("source_files") != files or not re.fullmatch(r"[0-9a-f]{40}", ref):
        raise ContinuationError("historical controller source inventory or ref changed")
    try:
        content = b"".join(
            subprocess.check_output(
                ["git", "show", f"{ref}:tools/context-evals/{name}"],
                cwd=Path(__file__).parents[2],
                stderr=subprocess.DEVNULL,
            )
            for name in files
        )
    except subprocess.CalledProcessError as exc:
        raise ContinuationError("historical controller source is unavailable") from exc
    if hashlib.sha256(content).hexdigest() != manifest.get("source_sha256"):
        raise ContinuationError("historical policy does not match its immutable source commit")


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[3]


class Plan:
    def __init__(
        self,
        path: Path,
        sha256: str,
        data: dict,
        selected: dict,
        prior: dict,
        sessions: dict,
        identities: dict,
        ledger: Path,
        workspace: Path,
        corpus: list,
    ) -> None:
        self.path, self.sha256, self.data = path, sha256, data
        self.selected, self.prior, self.sessions, self.identities = selected, prior, sessions, identities
        self.historical = False
        self.ledger, self.workspace, self.corpus = ledger, workspace, corpus

    def inherited(self, repo: str) -> dict:
        from dataclasses import replace

        import runner

        return {
            (case_id, repeat): replace(
                runner.SessionMeta(**row["meta"]),
                bounded_failure=row["source"]["adjudication"] == "certified-max-turns",
            )
            for (name, case_id, repeat), row in self.prior.items()
            if name == repo
        }

    def verify_run(self, out: Path, domains: dict) -> list:
        from continuation_runtime import verify_run

        return verify_run(self, out, domains)

    def aggregate(self, outputs: list[Path], domains: dict) -> dict:
        from continuation_runtime import aggregate

        return aggregate(self, outputs, domains)

    def wrap(self, execute, out: Path, repo: str):
        from continuation_runtime import ContinuedExecute

        if self.historical:
            raise ContinuationError("historical plans cannot execute")

        return ContinuedExecute(self, execute, out, repo)

    def recheck(self) -> None:
        self.load(self.path, self.sha256, self.corpus, self.ledger, workspace=self.workspace)

    def resolve(self, repo: str, case_id: str, repeat: int, out: Path) -> tuple:

        if file_hash(self.path) != self.sha256:
            raise ContinuationError("reviewed continuation manifest changed")
        key = repo, case_id, repeat
        if key not in self.sessions:
            raise ContinuationError("unplanned session cannot enter continuation scores")
        if key in self.prior:
            row = self.prior[key]
            raw = row["raw_path"]
            source = self.sessions[key]["source"]
            read_bound_json(row["meta_path"], source["meta_sha256"])
            if file_hash(raw) != source["raw_sha256"]:
                raise ContinuationError("inherited raw transcript changed")
            info = self.inherited(repo)[(case_id, repeat)]
            cert = next(
                (item["sha256"] for item in self.data["adjudications"] if item["payload"]["session"] == list(key)), None
            )
            if "provenance" in row:
                return (
                    raw,
                    info,
                    row["provenance"]
                    | {"source_manifest_sha256": row["provenance"]["manifest_sha256"], "manifest_sha256": self.sha256},
                )
            return (
                raw,
                info,
                {
                    "epoch": self.data["previous_admission"]["epoch"],
                    "policy_sha256": self.data["previous_admission"]["policy_sha256"],
                    "round_uuid": self.data["round"]["uuid"],
                    "request_ids": row["request_ids"],
                    "source_run_dir": str(row["root"]),
                    "source_run_id": json.loads((row["root"] / "run.json").read_text()).get("run_id"),
                    "raw_sha256": source["raw_sha256"],
                    "meta_sha256": source["meta_sha256"],
                    "manifest_sha256": self.sha256,
                    "adjudication_sha256": cert,
                },
            )
        from continuation_runtime import resolve_local

        return resolve_local(self, repo, case_id, repeat, out)

    @classmethod
    def load(
        cls,
        path: Path,
        sha256: str,
        corpus: list,
        ledger: Path,
        *,
        before_recovery: bool = False,
        allow_stopped: bool = False,
        workspace: Path | None = None,
        historical: bool = False,
    ):
        import continuation_compat

        workspace = workspace or workspace_root()
        data = read_bound_json(path, sha256)
        if isinstance(data, dict) and data.get("version") == 2:
            if historical:
                raise ContinuationError("only the reviewed first continuation may be imported as history")
            return load_extension(
                path,
                sha256,
                data,
                corpus,
                ledger,
                before_recovery=before_recovery,
                allow_stopped=allow_stopped,
                workspace=workspace,
            )
        if historical and before_recovery:
            raise ContinuationError("historical import cannot draft or authorize recovery")
        preflight = validate_header(data, ledger, historical=historical)
        state = validate_financial(
            data, ledger, before_recovery=before_recovery, allow_stopped=allow_stopped, historical=historical
        )
        previous = state["history"][data["previous_admission"]["epoch"]]
        previous_ref = previous["approval"].get("reviewed_ref", preflight["controller_commit"])
        if preflight["policy"] != data["previous_manifest"] or preflight["controller_commit"] != previous_ref:
            raise ContinuationError("preflight does not identify the original controller")
        if data["compatibility"] != continuation_compat.proof(previous_ref, data["reviewed_ref"]):
            raise ContinuationError("model-behavior compatibility proof changed")
        selected = selected_cases(corpus)
        identities, prior = validate_context_sources(data, preflight, selected, state, ledger, workspace)
        expected = {
            (name, case.id, repeat)
            for name, values in selected.items()
            for case in values
            for repeat in range(identities[name]["config"]["repeats"])
        }
        sessions = validate_session_plan(data["sessions"], expected, set(prior))
        for key, row in prior.items():
            if sessions[key]["source"] != row["source"] | {"request_ids": row["request_ids"]}:
                raise ContinuationError("inherited transcript, metadata, adjudication or billing identity changed")
        if data["adjudications"] != adjudications(data, prior):
            raise ContinuationError("bounded-failure adjudication is absent or not hash-bound")
        plan = cls(path, sha256, data, selected, prior, sessions, identities, ledger, workspace, corpus)
        plan.historical = historical
        return plan


def extension_prior(ancestor: Plan, source: Path) -> dict:
    from dataclasses import asdict

    from continuation_runtime import resolve_local, verified_run_metadata

    verified_run_metadata(ancestor, source)
    prior = {}
    for key, row in ancestor.prior.items():
        _, _, provenance = ancestor.resolve(*key, source)
        prior[key] = row | {"provenance": provenance}
    new = validate_prior_run(
        source,
        fingerprints(source),
        ancestor.selected["xberg"],
        ancestor.data["repos"]["xberg"]["ref"],
        ancestor.identities["xberg"],
        workspace=ancestor.workspace,
    )
    for key, row in new.items():
        if key in prior or key not in ancestor.sessions or ancestor.sessions[key]["source"] is not None:
            raise ContinuationError("extension cannot rerun or replace a completed source trial")
        _, info, provenance = resolve_local(ancestor, *key, source)
        prior[key] = row | {"meta": asdict(info), "request_ids": provenance["request_ids"], "provenance": provenance}
    claimed = [value for row in prior.values() for value in row["request_ids"]]
    if len(claimed) != len(set(claimed)):
        raise ContinuationError("multi-source trials cannot share a financial request")
    return prior


def extension_outputs(value: object, ledger: Path, sources: tuple) -> dict:
    output = require_keys(value, {"xberg", "sceptre"})
    paths = [controlled_path(output[name], ledger) for name in ("xberg", "sceptre")]
    if paths[0] == paths[1] or any(
        first.is_relative_to(second) for first, second in ((paths[0], paths[1]), (paths[1], paths[0]))
    ):
        raise ContinuationError("sealed consumer output paths must be disjoint")
    if any(path.is_relative_to(source) or source.is_relative_to(path) for path in paths for source in sources):
        raise ContinuationError("extension outputs cannot overwrite or contain immutable source runs")
    return output


def extension_state(ancestor: Plan, state: dict, previous_epoch: int | None) -> dict:
    import gateway_epochs

    epoch = state["history"][-1]["epoch"] if previous_epoch is None else previous_epoch
    if type(epoch) is not int or epoch != ancestor.data["next_admission"]["epoch"]:
        raise ContinuationError("only one reviewed extension of the first continuation is supported")
    rows = [row for row in state["requests"] if row[7] <= epoch]
    before = state | {
        "history": state["history"][: epoch + 1],
        "requests": rows,
        "requests_sha256": gateway_epochs.digest(rows),
    }
    if (
        before["history"][-1]["manifest"] != ancestor.data["next_manifest"]
        or state["stops"].get(epoch) != "request policy or reservation refused"
    ):
        raise ContinuationError("extension requires the exact retained local-policy stop and source policy")
    return before


def observed_attempt(ancestor: Plan, prior: dict, before: dict, replacement: tuple) -> dict:
    epoch = before["history"][-1]["epoch"]
    claimed = {value for item in prior.values() for value in item["request_ids"]}
    orphan = [row for row in before["requests"] if row[7] == epoch and row[0] not in claimed]
    attempt = {
        "kind": "interrupted-unknown",
        "session": list(replacement),
        "epoch": epoch,
        "actor": orphan[0][8] if orphan else "",
        "request_ids": [row[0] for row in orphan],
        "charge_nanos": sum(row[3] for row in orphan),
        "replacement_executions": 1,
    }
    return validate_technical_attempt(attempt, before["requests"], list(ancestor.sessions), set(prior), claimed, epoch)


def make_extension(
    ancestor_path: Path,
    ancestor_sha: str,
    source: Path,
    ledger: Path,
    reviewed_ref: str,
    outputs: dict,
    replacement: tuple,
    corpus: list,
    *,
    workspace: Path | None = None,
    previous_epoch: int | None = None,
) -> dict:
    import continuation_compat

    workspace = workspace or workspace_root()
    ancestor_path = controlled_path(str(ancestor_path), ledger)
    source = controlled_path(str(source), ledger)
    ancestor = Plan.load(ancestor_path, ancestor_sha, corpus, ledger, historical=True, workspace=workspace)
    before = extension_state(ancestor, ledger_state(ledger), previous_epoch)
    prior = extension_prior(ancestor, source)
    attempt = observed_attempt(ancestor, prior, before, replacement)
    data = draft_header(before, Path(ancestor.data["preflight"]["path"]), reviewed_ref)
    data.update(
        version=2,
        ancestor={"path": str(ancestor_path), "sha256": ancestor_sha},
        extension_source={"root": str(source), "files": fingerprints(source)},
        technical_attempt=attempt,
        outputs=extension_outputs(outputs, ledger, (source, *(row["root"] for row in ancestor.prior.values()))),
        repos=ancestor.data["repos"],
        adjudications=ancestor.data["adjudications"],
        compatibility=continuation_compat.extension_proof(ancestor.data["reviewed_ref"], reviewed_ref),
    )
    data["sessions"] = [
        row | {"source": prior[key]["source"] | {"request_ids": prior[key]["request_ids"]} if key in prior else None}
        for key, row in ancestor.sessions.items()
    ]
    return data


def load_extension(
    path: Path,
    sha256: str,
    data: dict,
    corpus: list,
    ledger: Path,
    *,
    before_recovery: bool,
    allow_stopped: bool,
    workspace: Path,
) -> Plan:
    validate_header(data, ledger)
    validate_financial(data, ledger, before_recovery=before_recovery, allow_stopped=allow_stopped)
    from continuation_runtime import collection_schema_at

    collection_schema_at(ledger, optional=before_recovery)
    anchor = require_keys(data["ancestor"], {"path", "sha256"})
    source = require_keys(data["extension_source"], {"root", "files"})
    attempt = require_keys(
        data["technical_attempt"],
        {"kind", "session", "epoch", "actor", "request_ids", "charge_nanos", "replacement_executions"},
    )
    root = controlled_path(source["root"], ledger)
    require_keys(source["files"], {"run.json", "cases.json", "context-identity.json"})
    for name, digest in source["files"].items():
        read_bound_json(root / name, digest)
    ancestor_path = controlled_path(anchor["path"], ledger)
    expected = make_extension(
        ancestor_path,
        require_hash(anchor["sha256"]),
        root,
        ledger,
        data["reviewed_ref"],
        data["outputs"],
        tuple(attempt["session"]),
        corpus,
        workspace=workspace,
        previous_epoch=data["previous_admission"]["epoch"],
    )
    if expected != data:
        raise ContinuationError("multi-source continuation, attempt, provenance or exact session plan changed")
    ancestor = Plan.load(ancestor_path, anchor["sha256"], corpus, ledger, historical=True, workspace=workspace)
    prior = extension_prior(ancestor, root)
    sessions = validate_session_plan(data["sessions"], set(ancestor.sessions), set(prior))
    return Plan(path, sha256, data, ancestor.selected, prior, sessions, ancestor.identities, ledger, workspace, corpus)
