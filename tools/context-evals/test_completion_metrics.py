"""All valid executed trials include certified bounded failures as zeroes."""

import json
import sys
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import cases
import harness
import judge
import runner
import scoring
import testkit
from records import SessionRecord, read_sessions


def record(repeat: int, error: str = "", *, bounded: bool = False) -> SessionRecord:
    value = SessionRecord("run", "case", "domain", "cluster", repeat, "tune", "answer", False)
    value.error = error
    value.bounded_failure = bounded
    value.expect_applicable = True
    value.expect_pass = True if not error else None
    value.criteria = {"fact": True if not error else None}
    return value


def store_judge_evidence(out: Path, verdict: dict, validity: dict, source: dict, manifest: str) -> None:
    (out / "judge" / "verdicts.jsonl").write_text(json.dumps(verdict | {"session_provenance": source}) + "\n")
    harness.write_json(out / "judge" / "validity.json", validity | {"continuation_manifest_sha256": manifest})


class CompletionMetricsTest(unittest.TestCase):
    def test_one_answer_and_one_certified_failure_keep_denominator_two(self) -> None:
        rows = [record(0), record(1, "error_max_turns", bounded=True)]
        summary = scoring.summarise(rows)
        self.assertEqual(summary["metrics"]["expect_pass_rate"]["mean"], 1)
        self.assertEqual(summary["metrics"]["criteria_pass_rate"]["mean"], 1)
        all_trials = summary["all_trials"]
        self.assertTrue(all_trials["execution_valid"])
        self.assertEqual(
            (all_trials["executed_trials"], all_trials["valid_trials"], all_trials["invalid_trials"]), (2, 2, 0)
        )
        for metric in ("completion", "expect_pass", "criteria_pass"):
            self.assertEqual(all_trials[metric], {"numerator": 1, "denominator": 2, "rate": 0.5, "ungraded_trials": 0})

    def test_serialized_records_require_an_explicit_supported_integer_schema_version(self) -> None:
        value = json.loads(record(0).to_json())
        missing = value.copy()
        missing.pop("version")
        for payload in [missing, *[value | {"version": version} for version in (True, "2", 2.0, None, 99)]]:
            with self.subTest(version=payload.get("version")), self.assertRaises(ValueError):
                SessionRecord.from_dict(payload)
        self.assertEqual(SessionRecord.from_dict(value).version, 3)
        self.assertEqual(record(0).version, 3)
        legacy = SessionRecord.from_dict(value | {"version": 1})
        self.assertFalse(scoring.summarise([legacy])["all_trials"]["execution_valid"])

    def test_legacy_record_schema_cannot_claim_a_valid_primary_baseline(self) -> None:
        legacy = record(0)
        legacy.version = 1
        result = scoring.summarise([legacy])["all_trials"]
        self.assertFalse(result["execution_valid"])
        self.assertEqual(result["invalid_trials"], 1)

    def test_empty_trial_collection_cannot_be_a_valid_execution(self) -> None:
        result = scoring.summarise([])["all_trials"]
        self.assertFalse(result["execution_valid"])
        self.assertEqual(result["executed_trials"], 0)
        self.assertIsNone(result["completion"]["rate"])

    def test_unknown_failure_invalidates_execution_instead_of_becoming_a_zero(self) -> None:
        result = scoring.summarise([record(0), record(1, "timeout")])["all_trials"]
        self.assertFalse(result["execution_valid"])
        self.assertEqual((result["executed_trials"], result["valid_trials"], result["invalid_trials"]), (2, 1, 1))
        self.assertEqual(result["invalid_errors"], {"timeout": 1})

    def test_unvalidated_answers_do_not_create_a_false_zero_aware_criteria_pass(self) -> None:
        answered = record(0)
        answered.criteria = {"fact": None}
        result = scoring.summarise([answered, record(1, "error_max_turns", bounded=True)])["all_trials"]
        self.assertIsNone(result["criteria_pass"]["rate"])
        self.assertEqual(result["criteria_pass"]["denominator"], 2)
        self.assertEqual(result["criteria_pass"]["ungraded_trials"], 1)

    def test_partially_validated_answer_cannot_make_the_primary_criteria_rate_look_complete(self) -> None:
        answered = record(0)
        answered.criteria = {"known": True, "not_validated": None}
        summary = scoring.summarise([answered, record(1, "error_max_turns", bounded=True)])
        self.assertEqual(summary["metrics"]["criteria_pass_rate"]["mean"], 1)
        self.assertIsNone(summary["all_trials"]["criteria_pass"]["rate"])
        self.assertEqual(summary["all_trials"]["criteria_pass"]["ungraded_trials"], 1)

    def test_uncertified_max_turn_failure_and_falsely_certified_unknown_error_are_invalid(self) -> None:
        for failure in (record(1, "error_max_turns"), record(1, "unknown", bounded=True)):
            with self.subTest(error=failure.error):
                self.assertFalse(scoring.summarise([record(0), failure])["all_trials"]["execution_valid"])

    def test_markdown_exposes_zero_aware_counts_and_invalid_execution(self) -> None:
        meta = {
            "run_id": "run",
            "repo": "xberg",
            "ref": "frozen",
            "commit": "a" * 40,
            "model": "fixture",
            "split": "tune",
            "repeats": 2,
            "judge_prompt_version": "fixture",
            "rubric_version": "fixture",
        }
        rows = [record(0), record(1, "error_max_turns", bounded=True)]
        text = harness.report_markdown(meta, scoring.aggregate(rows))
        self.assertIn("| completion | 1/2 (0.500)", text)
        self.assertIn("Conditional diagnostics (failed sessions excluded)", text)
        text = harness.report_markdown(meta, scoring.aggregate([record(0), record(1, "timeout")]))
        self.assertIn("| execution valid | False", text)
        self.assertIn("| invalid trials | 1", text)

    def test_controller_certificate_survives_runner_metadata_and_harness_scoring(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = testkit.make_checkout(root / "checkout")
            out = root / "run"
            (out / "transcripts").mkdir(parents=True)
            testkit.make_checkout(out / "context")
            case = cases.load_corpus(testkit.CASES, testkit.domains())[0]
            raw = testkit.transcript_text("error").replace(testkit.RUN_ROOT, str(checkout))
            raw = raw.replace('"test-model"', '"claude-sonnet-5-5"')
            events = [json.loads(line) for line in raw.splitlines()]
            events[-1].update(
                stop_reason="tool_use",
                terminal_reason="max_turns",
                errors=["Reached maximum number of turns (1)"],
                safety_stops=0,
                permission_denials=[],
            )
            raw = "\n".join(map(json.dumps, events))
            worker = runner.Runner(
                checkout,
                out,
                runner.RunConfig("claude-sonnet-5-5", max_turns=1),
                execute=lambda *_: runner.Completed(1, raw, "", bounded_failure=True),
                environ={"ANTHROPIC_API_KEY": "OFFLINE_DUMMY"},
            )
            worker.session(checkout, case, 0)
            stored = runner.read_meta(out / "transcripts", case.id, 0)
            self.assertEqual(stored.returncode, 1)
            self.assertTrue(stored.bounded_failure)
            harness.write_json(out / "cases.json", [asdict(case)])
            harness.write_json(
                out / "run.json",
                {
                    "run_id": "test",
                    "cases": [case.id],
                    "repeats": 1,
                    "harness_version": harness.HARNESS_VERSION,
                    "allowed_tools": list(runner.DEFAULT_TOOLS),
                    "model": "claude-sonnet-5-5",
                    "max_turns": 1,
                },
            )
            self.assertEqual(harness.score_run(out, testkit.domains()), 0)
            scored = read_sessions(out / "sessions.jsonl")[0]
            self.assertTrue(scored.bounded_failure)
            self.assertEqual(scored.error, "error_max_turns")
            self.assertEqual(scoring.summarise([scored])["all_trials"]["completion"]["rate"], 0)

    def test_bounded_nonanswers_are_not_sent_to_a_judge(self) -> None:
        case = cases.load_corpus(testkit.CASES, testkit.domains())[0]
        self.assertGreater(len(case.criteria), 0)
        failure = record(0, "error_max_turns", bounded=True)
        failure.case_id = case.id

        def forbidden(_prompt):
            raise AssertionError("a bounded nonanswer must not generate a judge call")

        self.assertEqual(judge.judge_sessions([failure], {case.id: case}, forbidden, "fixture"), [])
        self.assertEqual(failure.error, "error_max_turns")

    def test_verdict_cache_requires_the_same_session_source_and_continuation_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "judge").mkdir()
            answered = record(0)
            answered.criteria = {"fact": None}
            answered.provenance = {"epoch": 1, "policy_sha256": "a" * 64}
            policy, identity = {"mode": "fixture"}, {"uuid": "fixture"}
            meta = {"execution_policy": policy, "budget_round": identity, "continuation_manifest": {"sha256": "b" * 64}}
            versions = {
                "judge_prompt_version": judge.JUDGE_PROMPT_VERSION,
                "rubric_version": judge.RUBRIC_VERSION,
                "judge_tool_profile_version": judge.TOOL_PROFILE_VERSION,
            }
            verdict = {
                "case_id": "case",
                "repeat": 0,
                "verdicts": {"fact": True},
                "judge_model": "fixture",
                "execution_policy": policy,
                "budget_round": identity,
                **versions,
            }
            validity = {
                "models": {"primary": "fixture"},
                "judge_valid": True,
                "valid_criteria": ["case/fact"],
                "execution_policy": policy,
                "budget_round": identity,
                "continuation_manifest_sha256": "b" * 64,
                **versions,
            }
            harness.write_json(out / "run.json", meta)
            for source, manifest, expected in [
                ({"epoch": 2}, "b" * 64, None),
                (answered.provenance, "c" * 64, None),
                (answered.provenance, "b" * 64, True),
            ]:
                store_judge_evidence(out, verdict, validity, source, manifest)
                harness.apply_judge(out, [answered])
                self.assertIs(answered.criteria["fact"], expected)
            answered.error = "error_max_turns"
            answered.bounded_failure = True
            answered.criteria = {"fact": None}
            harness.apply_judge(out, [answered])
            self.assertIsNone(answered.criteria["fact"])

    def test_per_session_original_collection_provenance_survives_serialization(self) -> None:
        failure = record(1, "error_max_turns", bounded=True)
        failure.provenance = {"epoch": 1, "policy_sha256": "a" * 64, "request_ids": [2, 3]}
        restored = SessionRecord.from_dict(json.loads(failure.to_json()))
        self.assertEqual(restored.provenance, failure.provenance)

    def test_certification_and_expectation_applicability_survive_record_serialization(self) -> None:
        failure = record(1, "error_max_turns", bounded=True)
        restored = SessionRecord.from_dict(json.loads(failure.to_json()))
        self.assertTrue(restored.bounded_failure)
        self.assertTrue(restored.expect_applicable)
        self.assertEqual(restored.error, "error_max_turns")
        self.assertEqual(restored.criteria, {"fact": None})


if __name__ == "__main__":
    unittest.main()
