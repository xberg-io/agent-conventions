"""Reviewed recovery never creates another budget or releases uncertain charges."""

import copy
import os
import sqlite3
import sys
import tempfile
import unittest
import uuid
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

import gateway
import gateway_epochs

MODEL = "claude-sonnet-5-5"
HELD = 6_140_960_000
TOTAL = 25_000_000_000


# ~keep Exact v3 admission implementation from 07d086c must stay fenced after a reviewed recovery.
LEGACY_RESERVE_SOURCE = 'def reserve(self, model: str, max_tokens: int) -> int:\n        amount = Policy().reservation(model, max_tokens)\n        birth = process_identity(os.getpid())\n        if not birth:\n            raise GatewayError("cannot establish request owner identity")\n        with self.connection() as db:\n            db.execute("BEGIN IMMEDIATE")\n            if db.execute("SELECT stopped FROM hard_round WHERE id=1").fetchone()[0]:\n                raise GatewayError("round stopped")\n            spent = db.execute("SELECT COALESCE(SUM(charge), 0) FROM hard_requests").fetchone()[0]\n            if spent + amount > self.total:\n                raise GatewayError("round budget cannot reserve another complete request")\n            return db.execute(\n                "INSERT INTO hard_requests VALUES (NULL, ?, ?, ?, \'pending\', ?, ?)",\n                (model, max_tokens, amount, os.getpid(), birth),\n            ).lastrowid'


class RecoveryTest(unittest.TestCase):
    def setUp(self) -> None:
        verifier = patch("gateway.verify_reviewed_source")
        self.verifier = verifier.start()
        self.addCleanup(verifier.stop)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name).resolve() / "round.sqlite3"
        self.previous = copy.deepcopy(gateway.manifest())
        self.previous.update(protocol="hard-gateway-3", source_sha256="a" * 64)
        self.identity = {"uuid": str(uuid.uuid4()), "total_nanos": TOTAL, "ledger_path": str(self.path)}
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                "CREATE TABLE hard_round(id INTEGER PRIMARY KEY,total INTEGER,policy TEXT,stopped TEXT,round_uuid TEXT,canonical_path TEXT)"
            )
            db.execute(
                "INSERT INTO hard_round VALUES(1,?,?,?, ?,?)",
                (
                    TOTAL,
                    gateway_epochs.digest(self.previous),
                    "original uncertain request",
                    self.identity["uuid"],
                    str(self.path),
                ),
            )
            db.execute(
                "CREATE TABLE hard_requests(id INTEGER PRIMARY KEY,model TEXT,max_tokens INTEGER,charge INTEGER,state TEXT,owner INTEGER,birth TEXT)"
            )
            db.execute("INSERT INTO hard_requests VALUES(1,?,4096,?,'uncertain',0,'fixture')", (MODEL, HELD))
        self.approval = {
            "reviewed_ref": "f" * 40,
            "previous_policy": gateway_epochs.digest(self.previous),
            "next_policy": gateway.policy_hash(),
            "round": self.identity,
            "reason": "protocol-compatibility-recovery",
        }

    def migrate(self) -> None:
        gateway.recover_round(self.path, self.identity, self.previous, self.approval)

    def query(self, sql: str):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute(sql).fetchall()

    def test_recovery_preserves_every_legacy_row_and_binds_new_requests_to_the_epoch(self) -> None:
        legacy = self.query("SELECT * FROM hard_requests")
        root = self.query("SELECT * FROM hard_round")
        self.migrate()
        current = gateway.Ledger(self.path, 25)
        self.assertEqual(current.identity(), self.identity)
        self.assertEqual(self.query("SELECT * FROM hard_round"), root)
        self.assertEqual(self.query("SELECT * FROM hard_requests"), legacy)
        self.assertEqual(current.spent(), HELD)
        self.assertEqual(current.snapshot()["admission_epoch"]["epoch"], 1)
        request = current.reserve(MODEL, 4096)
        self.assertEqual(self.query(f"SELECT epoch FROM hard_request_epochs WHERE request={request}"), [(1,)])
        with self.assertRaises(gateway.GatewayError):
            current.settle(1, 0)
        current.settle(request, 0)
        self.assertEqual(current.spent(), HELD)
        self.assertEqual(len(current.snapshot()["epoch_history"]), 2)

    def test_cap_includes_the_original_uncertain_charge(self) -> None:
        self.migrate()
        current = gateway.Ledger(self.path, 25)
        for _ in range(3):
            current.reserve(MODEL, 4096)
        self.assertEqual(current.spent(), HELD * 4)
        with self.assertRaises(gateway.GatewayError):
            current.reserve(MODEL, 4096)

    def test_duplicate_transition_and_implicit_old_policy_acceptance_are_refused(self) -> None:
        with self.assertRaises(gateway.GatewayError):
            gateway.Ledger(self.path, 25)
        self.migrate()
        with self.assertRaises(gateway.GatewayError):
            self.migrate()
        self.assertEqual(gateway.Ledger(self.path, 25).spent(), HELD)

    def test_wrong_round_and_changed_bounds_do_not_mutate_legacy_data(self) -> None:
        before = self.query("SELECT * FROM hard_round"), self.query("SELECT * FROM hard_requests")
        for field, value in [
            ("uuid", "wrong"),
            ("total_nanos", TOTAL + 1),
            ("ledger_path", str(self.path.parent / "other")),
        ]:
            wrong = self.identity | {field: value}
            with self.subTest(field=field), self.assertRaises(gateway.GatewayError):
                gateway.recover_round(self.path, wrong, self.previous, self.approval)
        changed = copy.deepcopy(self.previous)
        changed["context_tokens"] += 1
        with self.assertRaises(gateway.GatewayError):
            gateway.recover_round(self.path, self.identity, changed, self.approval)
        self.assertEqual((self.query("SELECT * FROM hard_round"), self.query("SELECT * FROM hard_requests")), before)

    def test_pending_requests_block_transition(self) -> None:
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE hard_requests SET state='pending',owner=? WHERE id=1", (os.getpid(),))
        with self.assertRaises(gateway.GatewayError):
            self.migrate()
        self.assertEqual(self.query("SELECT charge,state FROM hard_requests"), [(HELD, "pending")])

    def next_epoch(self) -> tuple[dict, dict, dict]:
        previous = gateway.manifest()
        future = copy.deepcopy(previous)
        future.update(source_sha256="b" * 64, protocol="offline-future-controller")
        approval = self.approval | {
            "previous_policy": gateway_epochs.digest(previous),
            "next_policy": gateway_epochs.digest(future),
        }
        return previous, future, approval

    def test_stale_controller_is_fenced_after_another_explicit_epoch(self) -> None:
        self.migrate()
        stale = gateway.Ledger(self.path, 25)
        stale.stop("reviewed compatibility hold")
        previous, future, approval = self.next_epoch()
        gateway_epochs.recover(self.path, self.identity, previous, future, approval, gateway.GatewayError)
        with self.assertRaisesRegex(gateway.GatewayError, "stale admission epoch"):
            stale.reserve(MODEL, 4096)
        self.assertEqual(stale.spent(), HELD)
        with self.assertRaises(gateway.GatewayError):
            gateway.Ledger(self.path, 25)

    def test_one_controller_cannot_settle_another_controllers_pending_ticket(self) -> None:
        self.migrate()
        first, second = gateway.Ledger(self.path, 25), gateway.Ledger(self.path, 25)
        request = first.reserve(MODEL, 4096)
        with self.assertRaises(gateway.GatewayError):
            second.settle(request, 0)
        self.assertEqual(first.spent(), HELD * 2)
        first.settle(request, 0)
        self.assertEqual(first.spent(), HELD)

    def test_interrupted_transaction_rolls_back_every_appended_epoch(self) -> None:
        original = gateway_epochs.append_epoch
        before = self.query("SELECT * FROM hard_round"), self.query("SELECT * FROM hard_requests")
        calls = []

        def interrupted(*arguments):
            result = original(*arguments)
            calls.append(result)
            if len(calls) == 2:
                raise KeyboardInterrupt()
            return result

        with patch("gateway_epochs.append_epoch", side_effect=interrupted), self.assertRaises(KeyboardInterrupt):
            self.migrate()
        self.assertEqual(self.query("SELECT name FROM sqlite_master WHERE name='hard_epochs'"), [])
        self.assertEqual((self.query("SELECT * FROM hard_round"), self.query("SELECT * FROM hard_requests")), before)

    def test_recovery_cannot_change_the_bound_even_with_matching_supplied_hashes(self) -> None:
        for field, value in [
            ("context_tokens", 2_000_000),
            ("max_output_tokens", 8192),
            ("max_budget_usd", 26),
            ("max_output_tokens", 4096.0),
        ]:
            current = copy.deepcopy(gateway.manifest())
            current[field] = value
            approval = self.approval | {"next_policy": gateway_epochs.digest(current)}
            with self.subTest(field=field, value=value), self.assertRaisesRegex(gateway.GatewayError, "bounds"):
                gateway_epochs.recover(self.path, self.identity, self.previous, current, approval, gateway.GatewayError)
        self.assertEqual(self.query("SELECT charge,state FROM hard_requests"), [(HELD, "uncertain")])

    def test_immutable_history_and_bad_cursor_cannot_be_reopened(self) -> None:
        self.migrate()
        for statement in [
            "UPDATE hard_epochs SET record='{}' WHERE epoch=0",
            "DELETE FROM hard_epoch_stops WHERE epoch=0",
            "UPDATE hard_requests SET charge=0 WHERE id=1",
        ]:
            with self.subTest(statement=statement), self.assertRaises(sqlite3.IntegrityError):
                with closing(sqlite3.connect(self.path)) as db, db:
                    db.execute(statement)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE hard_epoch_cursor SET epoch=0 WHERE id=1")
        with self.assertRaises(gateway.GatewayError):
            gateway.Ledger(self.path, 25)

    def test_transition_and_reservation_race_fails_closed(self) -> None:
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier

        self.migrate()
        stale = gateway.Ledger(self.path, 25)
        stale.stop("reviewed compatibility hold")
        previous, future, approval = self.next_epoch()
        barrier = Barrier(2)

        def transition():
            barrier.wait()
            gateway_epochs.recover(self.path, self.identity, previous, future, approval, gateway.GatewayError)

        def reserve():
            barrier.wait()
            with self.assertRaises(gateway.GatewayError):
                stale.reserve(MODEL, 4096)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(transition), pool.submit(reserve)]
            for future_task in futures:
                future_task.result(timeout=10)
        self.assertEqual(self.query("SELECT charge,state FROM hard_requests"), [(HELD, "uncertain")])
        self.assertEqual(self.query("SELECT epoch FROM hard_epoch_cursor"), [(2,)])

    def test_legacy_v3_admission_stays_fenced_by_its_original_stopped_field(self) -> None:
        from types import SimpleNamespace

        self.migrate()
        current = gateway.Ledger(self.path, 25)
        namespace = {
            "Policy": gateway.Policy,
            "process_identity": gateway.process_identity,
            "os": os,
            "GatewayError": gateway.GatewayError,
        }
        exec(compile(LEGACY_RESERVE_SOURCE, "immutable-v3-reserve", "exec"), namespace)
        legacy = SimpleNamespace(path=self.path, total=TOTAL, connection=current.connection)
        with self.assertRaisesRegex(gateway.GatewayError, "round stopped"):
            namespace["reserve"](legacy, MODEL, 4096)
        self.assertEqual(self.query("SELECT stopped FROM hard_round"), [("original uncertain request",)])
        self.assertEqual(current.spent(), HELD)


class ApprovalSourceTest(unittest.TestCase):
    def test_unknown_or_stale_reviewed_source_cannot_authorize_recovery(self) -> None:
        from unittest.mock import Mock

        with patch("gateway.subprocess.run", return_value=Mock(returncode=0, stdout=b"stale")):
            with self.assertRaises(gateway.GatewayError):
                gateway.verify_reviewed_source("f" * 40)
        with patch("gateway.subprocess.run") as execute:
            with self.assertRaises(gateway.GatewayError):
                gateway.verify_reviewed_source("--output=/tmp/forbidden")
            execute.assert_not_called()

    def test_reviewed_source_verifies_every_bound_controller_file(self) -> None:
        from unittest.mock import Mock

        def source(arguments, **_options):
            name = arguments[-1].split(":tools/context-evals/", 1)[1]
            return Mock(returncode=0, stdout=(Path(__file__).parent / name).read_bytes())

        with patch("gateway.subprocess.run", side_effect=source) as execute:
            gateway.verify_reviewed_source("f" * 40)
            self.assertEqual(execute.call_count, len(gateway.manifest()["source_files"]))
