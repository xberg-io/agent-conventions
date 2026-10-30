"""Explicit, append-only admission epochs within one unchanged financial round."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path

BOUND_FIELDS = ("version", "context_tokens", "max_output_tokens", "rates_nanos_per_token", "max_budget_usd")


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def equal_bounds(first: dict, second: dict) -> bool:
    return digest({key: first.get(key) for key in BOUND_FIELDS}) == digest(
        {key: second.get(key) for key in BOUND_FIELDS}
    )


def validate_charges(db: sqlite3.Connection, manifests: dict[int, dict], fail: type[Exception]) -> None:
    rows = db.execute(
        "SELECT r.model,r.max_tokens,r.charge,r.state,e.epoch FROM hard_requests r JOIN hard_request_epochs e ON e.request=r.id"
    )
    total = 0
    for model, maximum, charge, state, epoch in rows:
        manifest = manifests[epoch]
        if not isinstance(maximum, int) or not 0 < maximum <= manifest["max_output_tokens"]:
            raise fail("request output bound is invalid")
        price = manifest["rates_nanos_per_token"].get(model)
        if (
            price is None
            or not isinstance(charge, int)
            or charge < 0
            or state not in {"pending", "uncertain", "settled"}
        ):
            raise fail("request accounting is invalid")
        bound = (
            manifest["context_tokens"] * (price["input"] + price["write_1h"] + price["read"])
            + maximum * price["output"]
        )
        if charge > bound or (state != "settled" and charge != bound):
            raise fail("uncertain/pending reservation or settled charge changed")
        total += charge
    if total > root_identity(db)[0]["total_nanos"]:
        raise fail("all-epoch charges exceed the unchanged round ceiling")


def validate_bindings(db: sqlite3.Connection, records: list[dict], fail: type[Exception]) -> None:
    missing = db.execute(
        "SELECT COUNT(*) FROM hard_requests r LEFT JOIN hard_request_epochs e ON r.id=e.request WHERE e.request IS NULL"
    ).fetchone()[0]
    if missing or db.execute("PRAGMA foreign_key_check").fetchall():
        raise fail("request/epoch binding or foreign-key integrity failed")
    validate_charges(db, {row["epoch"]: row["manifest"] for row in records}, fail)


def root_identity(db: sqlite3.Connection) -> tuple[dict, str, str]:
    total, policy, stopped, value, path = db.execute(
        "SELECT total,policy,stopped,round_uuid,canonical_path FROM hard_round WHERE id=1"
    ).fetchone()
    return {"uuid": value, "total_nanos": total, "ledger_path": path}, policy, stopped


def create_tables(db: sqlite3.Connection) -> None:
    db.execute("CREATE TABLE hard_epochs(epoch INTEGER PRIMARY KEY,record TEXT NOT NULL,audit_hash TEXT NOT NULL)")
    db.execute(
        "CREATE TABLE hard_epoch_cursor(id INTEGER PRIMARY KEY CHECK(id=1),epoch INTEGER REFERENCES hard_epochs(epoch))"
    )
    db.execute(
        "CREATE TABLE hard_epoch_stops(epoch INTEGER PRIMARY KEY REFERENCES hard_epochs(epoch),reason TEXT NOT NULL)"
    )
    db.execute(
        "CREATE TABLE hard_request_epochs(request INTEGER PRIMARY KEY REFERENCES hard_requests(id),epoch INTEGER REFERENCES hard_epochs(epoch),actor TEXT NOT NULL)"
    )
    db.execute(
        "CREATE TRIGGER hard_requests_delete BEFORE DELETE ON hard_requests BEGIN SELECT RAISE(ABORT,'immutable request history'); END"
    )
    db.execute(
        "CREATE TRIGGER hard_requests_update BEFORE UPDATE ON hard_requests WHEN OLD.state!='pending' OR NEW.model IS NOT OLD.model OR NEW.max_tokens IS NOT OLD.max_tokens OR NEW.owner IS NOT OLD.owner OR NEW.birth IS NOT OLD.birth OR NEW.charge>OLD.charge OR NEW.charge<0 OR NEW.state NOT IN ('settled','uncertain') BEGIN SELECT RAISE(ABORT,'immutable request accounting'); END"
    )
    for table in ("hard_epochs", "hard_epoch_stops", "hard_request_epochs"):
        for operation in ("UPDATE", "DELETE"):
            db.execute(
                f"CREATE TRIGGER {table}_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'immutable epoch history'); END"
            )


def append_epoch(db: sqlite3.Connection, identity: dict, manifest: dict, previous: str, approval: dict) -> dict:
    count = db.execute("SELECT COUNT(*) FROM hard_epochs").fetchone()[0]
    record = {
        "epoch": count,
        "round": identity,
        "manifest": manifest,
        "policy_sha256": digest(manifest),
        "previous": previous,
        "approval": approval,
    }
    hashed = digest(record)
    db.execute("INSERT INTO hard_epochs VALUES(?,?,?)", (count, json.dumps(record, sort_keys=True), hashed))
    return record | {"audit_hash": hashed}


def history(db: sqlite3.Connection, identity: dict, fail: type[Exception]) -> list[dict]:
    if not db.execute("SELECT name FROM sqlite_master WHERE name='hard_epochs'").fetchone():
        raise fail("legacy round requires an explicit reviewed recovery")
    previous, records = "", []
    for index, (number, text, hashed) in enumerate(
        db.execute("SELECT epoch,record,audit_hash FROM hard_epochs ORDER BY epoch")
    ):
        record = json.loads(text)
        if number != index or record.get("epoch") != index or record.get("round") != identity:
            raise fail("epoch identity or sequence is invalid")
        if (
            record.get("previous") != previous
            or digest(record) != hashed
            or digest(record["manifest"]) != record["policy_sha256"]
        ):
            raise fail("epoch audit chain is invalid")
        if records and not equal_bounds(record["manifest"], records[0]["manifest"]):
            raise fail("epoch pricing or bounds changed")
        records.append(record | {"audit_hash": hashed})
        previous = hashed
    if not records or root_identity(db)[1] != records[0]["policy_sha256"]:
        raise fail("legacy policy does not match the immutable genesis epoch")
    cursor = db.execute("SELECT epoch FROM hard_epoch_cursor WHERE id=1").fetchone()
    if cursor != (len(records) - 1,):
        raise fail("admission cursor is missing, corrupt or rolled back")
    return records


class Epochs:
    def __init__(self, db: sqlite3.Connection, manifest: dict, fail: type[Exception], *, fresh: bool) -> None:
        import uuid

        self.identity, _, _ = root_identity(db)
        self.actor = str(uuid.uuid4())
        self.manifest, self.fail = manifest, fail
        if fresh:
            create_tables(db)
            genesis = append_epoch(db, self.identity, manifest, "", {"kind": "genesis"})
            db.execute("INSERT INTO hard_epoch_cursor VALUES(1,?)", (genesis["epoch"],))
        records = history(db, self.identity, fail)
        self.epoch, self.policy = records[-1]["epoch"], digest(manifest)
        if records[-1]["policy_sha256"] != self.policy:
            raise fail("current controller policy is not the reviewed admission epoch")
        self.validate_bindings(db)

    def validate_bindings(self, db: sqlite3.Connection) -> None:
        validate_bindings(db, history(db, self.identity, self.fail), self.fail)

    def guard(self, db: sqlite3.Connection) -> None:
        if root_identity(db)[0] != self.identity:
            raise self.fail("round UUID, canonical path or ceiling changed")
        active = history(db, self.identity, self.fail)[-1]
        if (active["epoch"], active["policy_sha256"]) != (self.epoch, self.policy):
            raise self.fail("stale admission epoch; refusing forwarding")
        self.validate_bindings(db)
        if db.execute("SELECT reason FROM hard_epoch_stops WHERE epoch=?", (self.epoch,)).fetchone():
            raise self.fail("round stopped")

    def stop(self, db: sqlite3.Connection, reason: str) -> bool:
        changed = db.execute("INSERT OR IGNORE INTO hard_epoch_stops VALUES(?,?)", (self.epoch, reason)).rowcount
        db.execute("UPDATE hard_round SET stopped=? WHERE id=1 AND stopped=''", (reason,))
        return bool(changed)

    def own(self, db: sqlite3.Connection, request: int, owner: int, birth: str) -> None:
        row = db.execute(
            "SELECT e.epoch,r.owner,r.birth,r.state,e.actor FROM hard_requests r JOIN hard_request_epochs e ON e.request=r.id WHERE r.id=?",
            (request,),
        ).fetchone()
        if row != (self.epoch, owner, birth, "pending", self.actor):
            raise self.fail("settlement is not this controller's pending epoch request")

    def describe(self, db: sqlite3.Connection) -> dict:
        records = history(db, self.identity, self.fail)
        active = records[-1]
        stop = db.execute("SELECT reason FROM hard_epoch_stops WHERE epoch=?", (active["epoch"],)).fetchone()
        return {
            "admission_epoch": {key: active[key] for key in ("epoch", "policy_sha256", "audit_hash")},
            "epoch_history": records,
            "stop_reason": stop[0] if stop else "",
            "legacy_stop_reason": root_identity(db)[2],
        }


def validate_approval(identity: dict, previous: dict, current: dict, approval: dict, fail: type[Exception]) -> None:
    required = {"reviewed_ref", "previous_policy", "next_policy", "round", "reason"}
    if (
        not isinstance(approval, dict)
        or set(approval) != required
        or not isinstance(approval.get("reviewed_ref"), str)
        or not re.fullmatch(r"[0-9a-f]{40}", approval["reviewed_ref"])
    ):
        raise fail("explicit reviewed source approval is required")
    if (
        approval["round"] != identity
        or approval["previous_policy"] != digest(previous)
        or approval["next_policy"] != digest(current)
    ):
        raise fail("approval does not bind the exact round and old/new controller policies")
    if approval["reason"] != "protocol-compatibility-recovery" or digest(previous) == digest(current):
        raise fail("replayed or unsupported recovery")
    if not equal_bounds(previous, current):
        raise fail("recovery cannot change pricing, context or output bounds")


def recover(path: Path, identity: dict, previous: dict, current: dict, approval: dict, fail: type[Exception]) -> None:
    if not path.is_file() or path.is_symlink() or str(path.resolve()) != identity["ledger_path"]:
        raise fail("recovery requires the original canonical ledger")
    validate_approval(identity, previous, current, approval, fail)
    with closing(sqlite3.connect(f"file:{path.resolve()}?mode=rw", uri=True, timeout=30)) as db, db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("BEGIN IMMEDIATE")
        actual, root_policy, legacy_stop = root_identity(db)
        if actual != identity or not 0 < actual["total_nanos"] <= 25_000_000_000:
            raise fail("recovery round UUID, canonical path or ceiling changed")
        if db.execute("SELECT id FROM hard_requests WHERE state='pending'").fetchone():
            raise fail("pending requests block recovery")
        exists = db.execute("SELECT name FROM sqlite_master WHERE name='hard_epochs'").fetchone()
        if not exists:
            if root_policy != digest(previous) or not legacy_stop:
                raise fail("legacy policy/stop does not authorize the expected recovery")
            create_tables(db)
            old = append_epoch(db, identity, previous, "", {"kind": "legacy-import"})
            db.execute("INSERT INTO hard_epoch_cursor VALUES(1,0)")
            db.execute("INSERT INTO hard_epoch_stops VALUES(0,?)", (legacy_stop,))
            db.execute("INSERT INTO hard_request_epochs SELECT id,0,'legacy' FROM hard_requests")
        else:
            old = history(db, identity, fail)[-1]
            if (
                old["policy_sha256"] != digest(previous)
                or not db.execute("SELECT reason FROM hard_epoch_stops WHERE epoch=?", (old["epoch"],)).fetchone()
            ):
                raise fail("expected stopped admission epoch is not current")
        validate_bindings(db, history(db, identity, fail), fail)
        new = append_epoch(db, identity, current, old["audit_hash"], approval)
        db.execute("UPDATE hard_epoch_cursor SET epoch=? WHERE id=1", (new["epoch"],))
        records = history(db, identity, fail)
        validate_bindings(db, records, fail)
