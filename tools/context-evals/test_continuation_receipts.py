"""Durable collection receipts refuse artifact loss, replay and actor reuse before forwarding."""

import json
import shutil
import sqlite3
import sys
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

import continuation
import continuation_runtime
import runner
import test_continuation
from test_continuation import FakeCollector
from test_continuation_extension import ExtensionFixture


class ReceiptFixture(ExtensionFixture):
    def admit(self, initialize=True):
        self.plan = self.load_extension()
        test_continuation.RuntimePlanTest.advance(self, self.plan)
        if initialize:
            continuation_runtime.initialize_collection_receipts(self.plan)
        return self.plan

    def command(self, repo="xberg", out=None, plan=None):
        plan = plan or self.plan
        return [
            "continue",
            "--manifest",
            str(plan.path),
            "--manifest-sha256",
            plan.sha256,
            "--repo",
            str(self.root / repo),
            "--out",
            str(out or self.outputs[repo]),
        ]

    def invoke_collection(self, repo="xberg", out=None, plan=None):
        with self.patched_commands():
            return self.invoke(*self.command(repo, out, plan))


class DurableReceiptTest(ReceiptFixture, unittest.TestCase):
    def test_exact_whole_output_loss_replay_refuses_new_actor_before_forwarding(self) -> None:
        self.admit()
        before = len(self.calls)
        self.assertEqual(self.invoke_collection(), 0)
        self.assertEqual(len(self.calls) - before, 3)
        output = Path(self.outputs["xberg"])
        self.assertTrue(output.is_relative_to(self.root))
        shutil.rmtree(output)
        before = len(self.calls)
        self.assertEqual(self.invoke_collection(), 2)
        self.assertEqual(len(self.calls), before)

    def test_deleted_or_rewritten_pair_stops_before_the_next_forwarding(self) -> None:
        self.admit()
        before = len(self.calls)
        original_reset = runner.Runner.reset
        output = Path(self.outputs["xberg"])

        def lose_pair(instance, checkout):
            path = output / "transcripts" / f"{self.extra.id}.r0"
            raw = Path(str(path) + ".jsonl")
            meta = Path(str(path) + ".meta.json")
            if raw.exists():
                raw.unlink()
                meta.unlink()
            return original_reset(instance, checkout)

        with patch("runner.Runner.reset", lose_pair):
            self.assertEqual(self.invoke_collection(), 2)
        self.assertEqual(len(self.calls) - before, 1)

    def test_answer_rewrite_before_first_score_refuses_next_paid_call(self) -> None:
        self.admit()
        before = len(self.calls)
        original_reset = runner.Runner.reset
        output = Path(self.outputs["xberg"])

        def rewrite(instance, checkout):
            raw = output / "transcripts" / f"{self.extra.id}.r0.jsonl"
            if raw.exists():
                raw.write_text(raw.read_text().replace("fixture answer", "rewritten answer"))
            return original_reset(instance, checkout)

        with patch("runner.Runner.reset", rewrite):
            self.assertEqual(self.invoke_collection(), 2)
        self.assertEqual(len(self.calls) - before, 1)

    def test_explicit_receipt_initialization_preserves_every_financial_row_and_schema(self) -> None:
        self.admit(initialize=False)

        def financial_snapshot():
            with closing(sqlite3.connect(self.ledger_path)) as db:
                names = [
                    row[0]
                    for row in db.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'hard_%' ORDER BY name"
                    )
                ]
                schema = db.execute(
                    "SELECT name,sql FROM sqlite_master WHERE tbl_name LIKE 'hard_%' ORDER BY name"
                ).fetchall()
                return schema, {name: db.execute(f"SELECT * FROM {name} ORDER BY rowid").fetchall() for name in names}

        before = financial_snapshot()
        self.assertEqual(len(before[1]), 8)
        continuation_runtime.initialize_collection_receipts(self.plan)
        self.assertEqual(financial_snapshot(), before)

    def test_missing_schema_after_admission_is_not_silently_initialized(self) -> None:
        self.admit(initialize=False)
        before = len(self.calls)
        self.assertEqual(self.invoke_collection(), 2)
        self.assertEqual(len(self.calls), before)
        with closing(sqlite3.connect(self.ledger_path)) as db:
            names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn("context_collection_owners", names)

    def test_malformed_schema_cannot_be_reinitialized_or_used(self) -> None:
        self.admit()
        with closing(sqlite3.connect(self.ledger_path)) as db, db:
            db.execute("DROP TRIGGER context_collection_owners_no_update")
        with self.assertRaises(continuation.ContinuationError):
            continuation_runtime.initialize_collection_receipts(self.plan)
        before = len(self.calls)
        self.assertEqual(self.invoke_collection(), 2)
        self.assertEqual(len(self.calls), before)

    def test_different_manifest_and_outputs_cannot_reseal_an_already_consumed_epoch(self) -> None:
        self.admit()
        self.assertEqual(self.invoke_collection(), 0)
        changed = json.loads(self.plan.path.read_text())
        changed["outputs"] = {name: str(self.ledger_path.parent / "resealed" / name) for name in ("xberg", "sceptre")}
        path = self.ledger_path.parent / "resealed.json"
        path.write_text(json.dumps(changed))
        other = continuation.Plan.load(
            path, continuation.file_hash(path), self.corpus, self.ledger_path, workspace=self.root
        )
        before = len(self.calls)
        self.assertEqual(self.invoke_collection(out=changed["outputs"]["xberg"], plan=other), 2)
        self.assertEqual(len(self.calls), before)

    def test_shared_collection_actor_cannot_forward_for_the_second_consumer(self) -> None:
        self.admit()
        shared = FakeCollector(self.ledger_path, self.calls)
        with self.patched_commands(), patch("gateway_transport.HardExecute", return_value=shared):
            self.assertEqual(self.invoke(*self.command()), 0)
            before = len(self.calls)
            self.assertEqual(self.invoke(*self.command("sceptre")), 2)
        self.assertEqual(len(self.calls), before)

    def test_direct_api_cannot_repeat_a_returned_slot_before_artifacts_are_persisted(self) -> None:
        import tempfile

        self.admit()
        output = Path(self.outputs["xberg"])
        output.mkdir(parents=True)
        for name in ("cases.json", "context-identity.json"):
            shutil.copy2(self.source2 / name, output / name)
        shutil.copytree(self.source2 / "context", output / "context")
        meta = json.loads((self.source2 / "run.json").read_text())
        meta.update(
            run_id="direct-fixture",
            execution_policy={
                "mode": "hard-gateway",
                "policy": self.plan.data["next_manifest"],
                "policy_sha256": self.plan.data["next_admission"]["policy_sha256"],
            },
            admission_epoch=self.plan.data["next_admission"],
            continuation_manifest={"path": str(self.plan.path), "sha256": self.plan.sha256},
        )
        (output / "run.json").write_text(json.dumps(meta))
        (output / "transcripts").mkdir()
        inner = FakeCollector(self.ledger_path, self.calls)
        wrapped = self.plan.wrap(inner, output, "xberg")
        cwd = self.checkouts["xberg"] / self.extra.cwd
        with tempfile.TemporaryDirectory(prefix="ctx-home-") as directory, self.patched_commands():
            home = Path(directory)
            mcp = home / "mcp.json"
            mcp.write_text('{"mcpServers":{}}')
            argv = runner.ClaudeAdapter().command(
                runner.SessionSpec(self.extra.prompt, "claude-sonnet-5-5", 8, mcp, runner.DEFAULT_TOOLS)
            )
            env = runner.ClaudeAdapter().env(home, {"ANTHROPIC_API_KEY": "OFFLINE_UNUSED"})
            before = len(self.calls)
            wrapped(argv, cwd, env, 180)
            self.assertEqual(len(self.calls) - before, 1)
            with self.assertRaises(continuation.ContinuationError):
                wrapped(argv, cwd, env, 180)
            self.assertEqual(len(self.calls) - before, 1)

    def test_operational_rows_are_append_only_and_schema_loss_cannot_hide_paid_requests(self) -> None:
        self.admit()
        self.assertEqual(self.invoke_collection(), 0)
        with closing(sqlite3.connect(self.ledger_path)) as db, db:
            for table in ("context_collection_owners", "context_collection_receipts"):
                for operation in ("UPDATE", "DELETE"):
                    sql = f"UPDATE {table} SET epoch=epoch" if operation == "UPDATE" else f"DELETE FROM {table}"
                    with self.assertRaises(sqlite3.IntegrityError):
                        db.execute(sql)
            db.execute("DROP TABLE context_collection_receipts")
            db.execute("DROP TABLE context_collection_owners")
        with self.assertRaises(continuation.ContinuationError):
            continuation_runtime.initialize_collection_receipts(self.plan)

    def test_substantive_metadata_rewrite_refuses_next_forwarding(self) -> None:
        self.admit()
        before = len(self.calls)
        original_reset = runner.Runner.reset
        output = Path(self.outputs["xberg"])

        def rewrite(instance, checkout):
            meta = output / "transcripts" / f"{self.extra.id}.r0.meta.json"
            if meta.exists():
                value = json.loads(meta.read_text())
                value["stderr"] = "changed evidence"
                meta.write_text(json.dumps(value))
            return original_reset(instance, checkout)

        with patch("runner.Runner.reset", rewrite):
            self.assertEqual(self.invoke_collection(), 2)
        self.assertEqual(len(self.calls) - before, 1)

    def test_pending_intent_after_interruption_blocks_other_consumers(self) -> None:
        from test_continuation import FakeCollector

        self.admit()
        owner = self

        class InterruptedCollector(FakeCollector):
            def __call__(self, argv, cwd, environment, timeout):
                result = super().__call__(argv, cwd, environment, timeout)
                if argv[0] == "claude":
                    raise KeyboardInterrupt()
                return result

        before = len(self.calls)
        with (
            self.patched_commands(),
            patch(
                "gateway_transport.HardExecute",
                side_effect=lambda *_: InterruptedCollector(owner.ledger_path, owner.calls),
            ),
            self.assertRaises(KeyboardInterrupt),
        ):
            self.invoke(*self.command())
        self.assertEqual(len(self.calls) - before, 1)
        before = len(self.calls)
        self.assertEqual(self.invoke_collection("sceptre"), 2)
        self.assertEqual(len(self.calls), before)
        with closing(sqlite3.connect(self.ledger_path)) as db:
            self.assertEqual(db.execute("SELECT kind FROM context_collection_receipts").fetchall(), [("intent",)])

    def test_initialization_cannot_hold_a_writer_transaction_across_forwarding(self) -> None:
        self.admit()
        owner = self

        class WriterProbe(FakeCollector):
            def __call__(self, argv, cwd, environment, timeout):
                with closing(sqlite3.connect(owner.ledger_path, timeout=0.1)) as db:
                    db.execute("BEGIN IMMEDIATE")
                    db.rollback()
                return super().__call__(argv, cwd, environment, timeout)

        with (
            self.patched_commands(),
            patch("gateway_transport.HardExecute", side_effect=lambda *_: WriterProbe(owner.ledger_path, owner.calls)),
        ):
            self.assertEqual(self.invoke(*self.command()), 0)

    def test_extra_operational_schema_object_is_rejected(self) -> None:
        self.admit()
        with closing(sqlite3.connect(self.ledger_path)) as db, db:
            db.execute("CREATE TABLE context_collection_unknown(value TEXT)")
        before = len(self.calls)
        self.assertEqual(self.invoke_collection(), 2)
        self.assertEqual(len(self.calls), before)

    def test_invalid_timing_metadata_refuses_before_another_request(self) -> None:
        self.admit()
        before = len(self.calls)
        original_reset = runner.Runner.reset
        output = Path(self.outputs["xberg"])

        def rewrite(instance, checkout):
            meta = output / "transcripts" / f"{self.extra.id}.r0.meta.json"
            if meta.exists():
                value = json.loads(meta.read_text())
                value["seconds"] = -1
                meta.write_text(json.dumps(value))
            return original_reset(instance, checkout)

        with patch("runner.Runner.reset", rewrite):
            self.assertEqual(self.invoke_collection(), 2)
        self.assertEqual(len(self.calls) - before, 1)

    def test_pending_guard_fires_while_financial_round_is_still_active(self) -> None:
        self.admit()
        owner = self

        class PendingProbe(FakeCollector):
            def __call__(self, argv, cwd, environment, timeout):
                if argv[0] == "claude":
                    owner.assertNotIn(self.ledger.epochs.epoch, continuation.ledger_state(owner.ledger_path)["stops"])
                    with owner.assertRaisesRegex(continuation.ContinuationError, "has not durably completed"):
                        continuation_runtime.verify_collection_receipts(owner.plan)
                return super().__call__(argv, cwd, environment, timeout)

        with (
            self.patched_commands(),
            patch("gateway_transport.HardExecute", side_effect=lambda *_: PendingProbe(owner.ledger_path, owner.calls)),
        ):
            self.assertEqual(self.invoke(*self.command()), 0)

    def test_missing_model_response_evidence_cannot_certify_consumed_requests(self) -> None:
        self.admit()
        owner = self
        before = len(self.calls)

        class MissingResponse(FakeCollector):
            def __call__(self, argv, cwd, environment, timeout):
                from dataclasses import replace

                result = super().__call__(argv, cwd, environment, timeout)
                if argv[0] != "claude":
                    return result
                events = [json.loads(line) for line in result.stdout.splitlines()]
                return replace(
                    result, stdout="\n".join(json.dumps(row) for row in events if row.get("type") != "assistant") + "\n"
                )

        with (
            self.patched_commands(),
            patch(
                "gateway_transport.HardExecute", side_effect=lambda *_: MissingResponse(owner.ledger_path, owner.calls)
            ),
        ):
            self.assertEqual(self.invoke(*self.command()), 2)
        self.assertEqual(len(self.calls) - before, 1)


class ReceiptTimingTest(unittest.TestCase):
    def test_only_finite_nonnegative_diagnostic_timing_is_excluded_from_semantic_hash(self) -> None:
        from dataclasses import asdict

        meta = asdict(runner.SessionMeta("fixture", 0, "/fixture", 0, 1.0))
        digest = continuation_runtime.metadata_digest(meta)
        self.assertEqual(continuation_runtime.metadata_digest(meta | {"seconds": 2.0}), digest)
        for value in (float("nan"), float("inf"), -1.0, True):
            with self.subTest(value=value), self.assertRaises(continuation.ContinuationError):
                continuation_runtime.metadata_digest(meta | {"seconds": value})
        for field, value in (
            ("stderr", "changed"),
            ("root", "/other"),
            ("returncode", 1),
            ("bounded_failure", True),
            ("collection", {"actor": "other"}),
        ):
            self.assertNotEqual(continuation_runtime.metadata_digest(meta | {field: value}), digest)
