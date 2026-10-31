"""A declared replacement retains unknown attempts and exact multi-epoch provenance."""

import copy
import json
import sys
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

import cases
import continuation
import records
import runner
import testkit
from test_continuation import CollectionFixture, FakeCollector


def bounded_fixture_result(result: runner.Completed) -> runner.Completed:
    events = [json.loads(line) for line in result.stdout.splitlines()]
    events[-1].update(
        subtype="error_max_turns",
        is_error=True,
        result="",
        num_turns=9,
        stop_reason="tool_use",
        terminal_reason="max_turns",
        errors=["Reached maximum number of turns (8)"],
        safety_stops=0,
        permission_denials=[],
    )
    bounded = replace(result, returncode=1, stdout="\n".join(map(json.dumps, events)) + "\n", bounded_failure=True)
    return bounded


class TechnicalAttemptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.first = ("xberg", "first", 0)
        self.replacement = ("xberg", "first", 1)
        self.order = [self.first, self.replacement, ("sceptre", "other", 0)]
        self.rows = [(i, "claude-sonnet-5-5", 4096, 1000, "settled", 1, "fixture", 2, "actor") for i in range(1, 7)]
        self.attempt = {
            "kind": "interrupted-unknown",
            "session": list(self.replacement),
            "epoch": 2,
            "actor": "actor",
            "request_ids": [2, 3, 4, 5, 6],
            "charge_nanos": 5000,
            "replacement_executions": 1,
        }

    def validate(self, value=None, rows=None):
        return continuation.validate_technical_attempt(
            self.attempt if value is None else value,
            self.rows if rows is None else rows,
            self.order,
            {self.first},
            {1},
            2,
        )

    def test_unknown_attempt_is_retained_without_manufacturing_an_answer_or_profile(self) -> None:
        result = self.validate()
        self.assertEqual(result, self.attempt)
        self.assertEqual(result["replacement_executions"], 1)
        self.assertNotIn("answer", result)
        self.assertNotIn("bounded_failure", result)

    def test_unknown_attempt_cannot_hide_missing_duplicated_or_relabelled_charges(self) -> None:
        changes = [
            {"request_ids": [2, 3, 4, 5]},
            {"request_ids": [1, 3, 4, 5, 6]},
            {"request_ids": [2, 2, 4, 5, 6]},
            {"charge_nanos": 0},
            {"epoch": 1},
            {"actor": "other"},
            {"replacement_executions": 2},
            {"replacement_executions": True},
            {"session": ["xberg", "first", True]},
            {"session": None},
            {"request_ids": [True, 3, 4, 5, 6]},
            {"session": list(self.first)},
            {"answer": "invented"},
        ]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(continuation.ContinuationError):
                self.validate(self.attempt | change)

    def test_pending_uncertain_other_actor_and_nontrailing_orphans_are_rejected(self) -> None:
        for index, replacement in [(4, "pending"), (4, "uncertain"), (8, "other-actor")]:
            rows = copy.deepcopy(self.rows)
            changed = list(rows[-1])
            changed[index] = replacement
            rows[-1] = tuple(changed)
            with self.subTest(index=index, replacement=replacement), self.assertRaises(continuation.ContinuationError):
                self.validate(rows=rows)
        with self.assertRaises(continuation.ContinuationError):
            continuation.validate_technical_attempt(self.attempt, self.rows, self.order, {self.first}, {6}, 2)

    def test_completed_tuple_cannot_be_selected_for_replacement_or_later_tuple_cherry_picked(self) -> None:
        value = self.attempt | {"session": ["sceptre", "other", 0]}
        with self.assertRaises(continuation.ContinuationError):
            self.validate(value)


class HistoricalSourceTest(unittest.TestCase):
    def test_historical_source_requires_the_exact_source_inventory_and_commit_hash(self) -> None:
        import hashlib

        import gateway

        inventory = gateway.manifest()["source_files"]
        first = Path(gateway.__file__).read_bytes()
        manifest = gateway.manifest() | {
            "source_sha256": hashlib.sha256(first + b"offline" * (len(inventory) - 1)).hexdigest()
        }

        def source(argv: list[str], **_options: object) -> bytes:
            return first if argv[-1].endswith("/gateway.py") else b"offline"

        with patch("subprocess.check_output", side_effect=source) as git_source:
            continuation.verify_historical_source("f" * 40, manifest)
            self.assertEqual(git_source.call_count, len(inventory))
            with self.assertRaises(continuation.ContinuationError):
                continuation.verify_historical_source("f" * 40, manifest | {"source_sha256": "0" * 64})
            with self.assertRaises(continuation.ContinuationError):
                continuation.verify_historical_source("f" * 40, manifest | {"source_files": inventory[:-1]})
            with self.assertRaises(continuation.ContinuationError):
                continuation.verify_historical_source("f", manifest)


class StudyDimensionTest(unittest.TestCase):
    def test_actual_plan_retains_115_and_schedules_71_with_one_declared_replacement(self) -> None:
        order = [
            (repo, f"case-{index:02}", repeat)
            for repo, count in (("xberg", 46), ("sceptre", 16))
            for index in range(count)
            for repeat in range(3)
        ]
        prior = set(order[:115])
        sessions = [
            {
                "repo": repo,
                "case_id": case_id,
                "repeat": repeat,
                "source": {
                    "raw_sha256": "a" * 64,
                    "meta_sha256": "b" * 64,
                    "adjudication": None,
                    "request_ids": [index + 2],
                }
                if (repo, case_id, repeat) in prior
                else None,
            }
            for index, (repo, case_id, repeat) in enumerate(order)
        ]
        plan = continuation.validate_session_plan(sessions, set(order), prior)
        self.assertEqual(len(plan), 186)
        self.assertEqual(sum(row["source"] is not None for row in plan.values()), 115)
        fresh = [key for key, row in plan.items() if row["source"] is None]
        self.assertEqual(len(fresh), 71)
        self.assertEqual(sum(key[0] == "xberg" for key in fresh), 23)
        self.assertEqual(sum(key[0] == "sceptre" for key in fresh), 48)
        self.assertEqual(fresh[0], order[115])
        self.assertEqual(len(set(fresh)), 71)


class ExtensionFixture(CollectionFixture):
    def setUp(self) -> None:
        super().setUp()
        # This fixture represents protocol4 history, independent of the live harness version.
        self.enterContext(patch("harness.HARNESS_VERSION", "5"))
        self.prepare_corpus()
        self.prepare_collection()
        self.capture_lost_source()
        self.ancestor = self.plan
        self.mid_policy = self.future
        self.next_policy = self.future | {"source_sha256": "9" * 64}
        for target, value in [
            ("gateway.manifest", self.next_policy),
            ("continuation.verify_historical_source", None),
            ("continuation_compat.extension_proof", {"version": 2, "fixture": "bounded-reviewed-extension"}),
        ]:
            patcher = patch(target, return_value=value, create=True)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.outputs = {name: str(self.ledger_path.parent / "epoch3" / name) for name in ("xberg", "sceptre")}
        self.replacement = ("xberg", self.extra.id, 0)

    def prepare_corpus(self) -> None:
        self.extra = replace(self.case, id="xberg-second", prompt="Second fixture question")
        self.corpus = [self.case, self.extra, self.sceptre]
        self.meta["cases"] = [self.case.id, self.extra.id]
        self.meta["case_corpus_hash"] = cases.corpus_hash([self.case, self.extra])
        self.write_json("run.json", self.meta)
        self.write_json("cases.json", [asdict(self.case), asdict(self.extra)])
        self.hashes = continuation.fingerprints(self.source)
        preflight = json.loads(self.preflight.read_text())
        preflight["checks"]["xberg"].update(
            case_corpus_hash=self.meta["case_corpus_hash"], expected_sessions=6, tune_cases=2
        )
        self.preflight.write_text(json.dumps(preflight))

    def capture_lost_source(self) -> None:
        owner = self

        class LostCollector(FakeCollector):
            def __call__(self, argv, cwd, environment, timeout):
                if argv[0] == "claude" and len(self.calls) == 1:
                    for _ in range(5):
                        request = self.ledger.reserve("claude-sonnet-5-5", 4096)
                        self.ledger.settle(request, 1000)
                    self.ledger.stop("request policy or reservation refused")
                    raise KeyboardInterrupt()
                return super().__call__(argv, cwd, environment, timeout)

        self.source2 = self.ledger_path.parent / "epoch2" / "xberg"
        with (
            self.patched_commands(),
            patch(
                "gateway_transport.HardExecute", side_effect=lambda *_: LostCollector(owner.ledger_path, owner.calls)
            ),
            self.assertRaises(KeyboardInterrupt),
        ):
            self.invoke(
                "continue",
                "--manifest",
                str(self.plan.path),
                "--manifest-sha256",
                self.plan.sha256,
                "--repo",
                str(self.root / "xberg"),
                "--out",
                str(self.source2),
            )

    def extension(self) -> dict:
        return continuation.make_extension(
            self.ancestor.path,
            self.ancestor.sha256,
            self.source2,
            self.ledger_path,
            "9" * 40,
            self.outputs,
            self.replacement,
            self.corpus,
            workspace=self.root,
        )

    def load_extension(self, data: dict | None = None) -> continuation.Plan:
        path = self.ledger_path.parent / "extension.json"
        path.write_text(json.dumps(self.extension() if data is None else data))
        return continuation.Plan.load(
            path, continuation.file_hash(path), self.corpus, self.ledger_path, before_recovery=True, workspace=self.root
        )


class MultiSourceTest(ExtensionFixture, unittest.TestCase):
    def test_extension_retains_both_epochs_and_seals_one_replacement_without_source_rewrites(self) -> None:
        before = {p: p.read_bytes() for root in (self.source, self.source2) for p in root.rglob("*") if p.is_file()}
        plan = self.load_extension()
        self.assertEqual(len(plan.sessions), 9)
        self.assertEqual(len(plan.prior), 3)
        self.assertEqual(sum(row["source"] is None for row in plan.sessions.values()), 6)
        self.assertEqual(plan.data["technical_attempt"]["request_ids"], [4, 5, 6, 7, 8])
        self.assertEqual(plan.data["technical_attempt"]["charge_nanos"], 5000)
        self.assertEqual(plan.data["technical_attempt"]["session"], list(self.replacement))
        origins = [plan.resolve("xberg", self.case.id, repeat, Path(self.outputs["xberg"]))[2] for repeat in range(3)]
        self.assertEqual([row["epoch"] for row in origins], [0, 0, 1])
        self.assertEqual([row["request_ids"] for row in origins], [[1], [2], [3]])
        self.assertEqual(origins[2]["source_run_dir"], str(self.source2))
        self.assertEqual({p: p.read_bytes() for p in before}, before)

    def test_missing_or_changed_second_source_attempt_or_output_is_rejected(self) -> None:
        original = self.extension()
        variants = []
        for key in ("ancestor", "extension_source", "technical_attempt", "outputs"):
            value = copy.deepcopy(original)
            value[key] = {}
            variants.append(value)
        value = copy.deepcopy(original)
        value["sessions"][0]["source"] = None
        variants.append(value)
        value = copy.deepcopy(original)
        value["technical_attempt"]["replacement_executions"] = 2
        variants.append(value)
        for value in variants:
            with self.subTest(keys=list(value)), self.assertRaises(continuation.ContinuationError):
                self.load_extension(value)

    def test_historical_import_cannot_execute_or_import_a_second_extension(self) -> None:
        anchor = continuation.Plan.load(
            self.ancestor.path,
            self.ancestor.sha256,
            self.corpus,
            self.ledger_path,
            historical=True,
            workspace=self.root,
        )
        self.assertTrue(anchor.historical)
        with self.assertRaises(continuation.ContinuationError):
            anchor.wrap(None, self.source2, "xberg")
        plan = self.load_extension()
        with self.assertRaises(continuation.ContinuationError):
            continuation.Plan.load(
                plan.path, plan.sha256, self.corpus, self.ledger_path, historical=True, workspace=self.root
            )

    def test_changed_import_receipt_actor_epoch_and_raw_are_rejected_read_only(self) -> None:
        data = self.extension()
        meta_path = next((self.source2 / "transcripts").glob("*.meta.json"))
        original = meta_path.read_bytes()
        before = self.ledger_path.read_bytes()
        for change in ({"actor": "other"}, {"epoch": 0}, {"request_ids": [4]}):
            changed = json.loads(original)
            changed["collection"].update(change)
            meta_path.write_text(json.dumps(changed))
            try:
                with self.subTest(change=change), self.assertRaises(continuation.ContinuationError):
                    self.load_extension(data)
                self.assertEqual(self.ledger_path.read_bytes(), before)
            finally:
                meta_path.write_bytes(original)
        raw_path = next((self.source2 / "transcripts").glob("*.jsonl"))
        original_raw = raw_path.read_bytes()
        raw_path.write_bytes(original_raw.replace(b"fixture answer", b"changed answer"))
        try:
            with self.assertRaises(continuation.ContinuationError):
                self.load_extension(data)
        finally:
            raw_path.write_bytes(original_raw)


class ExtensionRuntimeTest(ExtensionFixture, unittest.TestCase):
    def advance_extension(self) -> continuation.Plan:
        import test_continuation

        self.plan = self.load_extension()
        test_continuation.RuntimePlanTest.advance(self, self.plan)
        import continuation_runtime

        continuation_runtime.initialize_collection_receipts(self.plan)
        return self.plan

    def test_complete_extension_collects_only_sealed_remainder_and_reports_every_attempt(self) -> None:
        plan = self.advance_extension()
        before_calls = len(self.calls)
        before_sources = {
            p: p.read_bytes() for root in (self.source, self.source2) for p in root.rglob("*") if p.is_file()
        }
        outputs = []
        with self.patched_commands():
            for name in ("xberg", "sceptre"):
                out = Path(self.outputs[name])
                self.assertEqual(
                    self.invoke(
                        "continue",
                        "--manifest",
                        str(plan.path),
                        "--manifest-sha256",
                        plan.sha256,
                        "--repo",
                        str(self.root / name),
                        "--out",
                        str(out),
                    ),
                    0,
                )
                outputs.append(out)
        self.assertEqual(len(self.calls) - before_calls, 6)
        self.assert_repeat_refused(plan, outputs[0], len(self.calls))
        rows = records.read_sessions(outputs[0] / "sessions.jsonl")
        self.assertEqual({row.provenance["epoch"] for row in rows}, {0, 1, 2})
        combined = plan.aggregate(outputs, testkit.domains())
        self.assertEqual(combined["expected_trials"], 9)
        self.assertEqual(combined["methodology"]["verified_baseline_records"], 9)
        self.assertEqual(combined["methodology"]["cohort_agent_execution_attempts"], 10)
        self.assertEqual(combined["methodology"]["unknown_technical_attempts"], 1)
        self.assertEqual(combined["methodology"]["declared_replacements"], 1)
        self.assertEqual(set(combined["methodology"]["collection_actors"]), {"xberg", "sceptre"})
        self.assertEqual(len(set(combined["methodology"]["collection_actors"].values())), 2)
        self.assertEqual(combined["methodology"]["durably_completed_collection_slots"], 6)
        self.assertEqual(combined["methodology"]["unknown_attempt"]["request_ids"], [4, 5, 6, 7, 8])
        self.assertTrue(combined["summary"]["overall"]["all_trials"]["execution_valid"])
        self.assertEqual({p: p.read_bytes() for p in before_sources}, before_sources)
        self.assertEqual(self.ledger.spent(), 14000)
        self.assert_judge_and_report(outputs[0])

    def assert_repeat_refused(self, plan: continuation.Plan, output: Path, expected_calls: int) -> None:
        with self.patched_commands():
            self.assertEqual(
                self.invoke(
                    "continue",
                    "--manifest",
                    str(plan.path),
                    "--manifest-sha256",
                    plan.sha256,
                    "--repo",
                    str(self.root / "xberg"),
                    "--out",
                    str(output),
                ),
                2,
            )
        self.assertEqual(len(self.calls), expected_calls)

    def assert_judge_and_report(self, output: Path) -> None:
        verdict = {criterion.id: True for criterion in self.case.criteria}
        with self.patched_commands():
            self.assertEqual(
                self.invoke(
                    "judge",
                    str(output),
                    "--model",
                    "claude-sonnet-5-5",
                    grader_factory=lambda _: lambda _prompt: json.dumps({"verdicts": verdict}),
                ),
                0,
            )
            self.assertEqual(self.invoke("report", str(output)), 0)
        judged = [json.loads(line) for line in (output / "judge/verdicts.jsonl").read_text().splitlines()]
        self.assertEqual({row["session_provenance"]["epoch"] for row in judged}, {0, 1, 2})
        self.assertFalse(any(row["case_id"] == self.case.id and row["repeat"] == 1 for row in judged))
        text = (output / "report.md").read_text()
        self.assertIn("Recorded baseline trials", text)
        self.assertIn("unknown technical attempt", text)

    def test_unsealed_output_refuses_before_any_collection_or_provider_call(self) -> None:
        plan = self.advance_extension()
        before = len(self.calls)
        with self.patched_commands():
            result = self.invoke(
                "continue",
                "--manifest",
                str(plan.path),
                "--manifest-sha256",
                plan.sha256,
                "--repo",
                str(self.root / "xberg"),
                "--out",
                str(self.ledger_path.parent / "wrong-output"),
            )
        self.assertEqual(result, 2)
        self.assertEqual(len(self.calls), before)

    def test_failed_declared_replacement_stops_before_next_case_and_preserves_failure(self) -> None:
        plan = self.advance_extension()
        owner = self
        before = len(self.calls)

        class FailedReplacement(FakeCollector):
            def __call__(self, argv, cwd, environment, timeout):
                result = super().__call__(argv, cwd, environment, timeout)
                return replace(result, returncode=1) if argv[0] == "claude" else result

        with (
            self.patched_commands(),
            patch(
                "gateway_transport.HardExecute",
                side_effect=lambda *_: FailedReplacement(owner.ledger_path, owner.calls),
            ),
        ):
            result = self.invoke(
                "continue",
                "--manifest",
                str(plan.path),
                "--manifest-sha256",
                plan.sha256,
                "--repo",
                str(self.root / "xberg"),
                "--out",
                self.outputs["xberg"],
            )
        self.assertEqual(result, 2)
        self.assertEqual(len(self.calls) - before, 1)
        state = continuation.ledger_state(self.ledger_path)
        self.assertEqual(state["stops"][2], "collection result could not be certified by its durable receipt")
        meta = json.loads((Path(self.outputs["xberg"]) / "transcripts" / f"{self.extra.id}.r0.meta.json").read_text())
        self.assertEqual(meta["returncode"], 1)
        self.assertFalse(meta["bounded_failure"])

    def test_certified_max_turn_replacement_remains_a_valid_zero_without_stopping(self) -> None:
        import gateway_transport

        plan = self.advance_extension()
        owner = self
        before = len(self.calls)

        class BoundedReplacement(FakeCollector):
            def __call__(self, argv, cwd, environment, timeout):
                result = super().__call__(argv, cwd, environment, timeout)
                if argv[0] != "claude" or len(self.calls) - before != 1:
                    return result
                bounded = bounded_fixture_result(result)
                owner.assertTrue(gateway_transport.maximum_turn_failure(bounded, 8))
                return bounded

        with (
            self.patched_commands(),
            patch(
                "gateway_transport.HardExecute",
                side_effect=lambda *_: BoundedReplacement(owner.ledger_path, owner.calls),
            ),
        ):
            code = self.invoke(
                "continue",
                "--manifest",
                str(plan.path),
                "--manifest-sha256",
                plan.sha256,
                "--repo",
                str(self.root / "xberg"),
                "--out",
                self.outputs["xberg"],
            )
        self.assertEqual(code, 0)
        rows = records.read_sessions(Path(self.outputs["xberg"]) / "sessions.jsonl")
        self.assertEqual(sum(row.bounded_failure for row in rows), 2)
        self.assertNotIn(2, continuation.ledger_state(self.ledger_path)["stops"])
