"""Hard-budget routing is selected before either agent or judge execution."""

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

import gateway
import harness
import runner


class HardBudgetRoutingTest(unittest.TestCase):
    def test_agent_judge_and_validation_all_use_the_shared_hard_executor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "round.sqlite3"
            commands = [
                (
                    ["run", "--repo", directory, "--ref", "main", "--model", gateway.MODELS[0], "--out", directory],
                    "cmd_run",
                ),
                (["judge", directory, "--model", gateway.MODELS[0]], "cmd_judge"),
                (
                    ["judge-validate", directory, "--model", gateway.MODELS[0], "--second-model", gateway.MODELS[1]],
                    "cmd_judge_validate",
                ),
            ]
            executor = object()
            for command, handler in commands:
                with (
                    self.subTest(command=command),
                    patch("harness.gateway_transport.HardExecute", return_value=executor) as factory,
                ):
                    with patch(f"harness.{handler}", return_value=0) as dispatch:
                        result = harness.main(
                            ["--hard-budget", "--budget-ledger", str(ledger), *command],
                            environ={"ANTHROPIC_API_KEY": "offline-fixture"},
                        )
                    self.assertEqual(result, 0)
                    self.assertEqual(factory.call_args.args[1], "offline-fixture")
                    if handler == "cmd_run":
                        self.assertIs(dispatch.call_args.args[1], executor)
                    else:
                        grader_factory = dispatch.call_args.args[1]
                        with patch("harness.judge.ClaudeGrader") as grader:
                            grader_factory(gateway.MODELS[0])
                            self.assertIs(grader.call_args.kwargs["execute"], executor)

    def test_hard_mode_requires_ledger_and_cannot_mix_soft_consent(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()) as error:
            result = harness.main(
                ["--hard-budget", "judge", ".", "--model", gateway.MODELS[0]],
                environ={"ANTHROPIC_API_KEY": "offline-fixture"},
            )
        self.assertEqual(result, 2)
        self.assertIn("shared --budget-ledger", error.getvalue())
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            harness.parser().parse_args(["--hard-budget", "--allow-soft-budget", "score", "."])
        self.assertEqual(raised.exception.code, 2)

    def test_hard_initialization_refusal_returns_failure_without_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(io.StringIO()):
            with patch("harness.gateway_transport.HardExecute", side_effect=gateway.GatewayError("proof refused")):
                with patch("harness.cmd_judge") as dispatch:
                    result = harness.main(
                        [
                            "--hard-budget",
                            "--budget-ledger",
                            str(Path(directory) / "ledger"),
                            "judge",
                            ".",
                            "--model",
                            gateway.MODELS[0],
                        ],
                        environ={"ANTHROPIC_API_KEY": "offline-fixture"},
                    )
                    self.assertEqual(result, 2)
                    dispatch.assert_not_called()


class ProtocolProvenanceTest(unittest.TestCase):
    def test_budget_policy_difference_prevents_comparison(self) -> None:
        old = dict.fromkeys(harness.VERSION_KEYS, "same")
        new = {**old, "execution_policy": {"mode": "hard-gateway", "policy_sha256": "different"}}
        self.assertTrue(any("execution_policy" in reason for reason in harness.comparable(old, new)))

    def test_current_judge_rejects_an_old_execution_policy_before_grading(self) -> None:
        import argparse
        import json

        import judge

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = {
                "harness_version": harness.HARNESS_VERSION,
                "rubric_version": judge.RUBRIC_VERSION,
                "tool_profile_version": runner.TOOL_PROFILE_VERSION,
                "judge_tool_profile_version": judge.TOOL_PROFILE_VERSION,
                "execution_policy": {"mode": "old-protocol"},
            }
            (root / "run.json").write_text(json.dumps(metadata))
            (root / "sessions.jsonl").write_text("")
            args = argparse.Namespace(run_dir=root, model=gateway.MODELS[0], hard_budget=True)
            with self.assertRaises(harness.HarnessError) as raised:
                harness.cmd_judge(args, lambda _model: self.fail("must not grade mismatched protocol"))
            self.assertIn("execution policy", str(raised.exception))


class RoundBindingTest(unittest.TestCase):
    def arguments(self, root: Path, ledger: Path):
        return harness.parser().parse_args(
            ["--hard-budget", "--budget-ledger", str(ledger), "judge", str(root), "--model", gateway.MODELS[0]]
        )

    def test_same_round_can_be_shared_but_judging_cannot_switch_to_a_fresh_ledger(self) -> None:
        import json

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self.arguments(root, root / "round-a.sqlite3")
            second = self.arguments(root, root / "round-b.sqlite3")
            gateway.Ledger(first.budget_ledger, 25)
            gateway.Ledger(second.budget_ledger, 25)
            (root / "run.json").write_text(
                json.dumps(
                    {"execution_policy": harness.execution_policy(first), "budget_round": harness.budget_round(first)}
                )
            )
            harness.require_execution_policy(first)
            shared = self.arguments(root, first.budget_ledger)
            self.assertEqual(harness.budget_round(first), harness.budget_round(shared))
            with self.assertRaises(harness.HarnessError) as raised:
                harness.require_execution_policy(second)
            self.assertIn("budget round", str(raised.exception))

    def test_round_identity_is_persistent_and_independent_of_comparison_protocol(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self.arguments(root, root / "round-a.sqlite3")
            second = self.arguments(root, root / "round-b.sqlite3")
            identity = harness.budget_round(first)
            self.assertEqual(identity, harness.budget_round(first))
            self.assertEqual(identity["total_nanos"], 25_000_000_000)
            self.assertEqual(identity["ledger_path"], str(first.budget_ledger.resolve()))
            self.assertNotEqual(identity["uuid"], harness.budget_round(second)["uuid"])
            self.assertEqual(harness.execution_policy(first), harness.execution_policy(second))
            same = dict.fromkeys(harness.VERSION_KEYS, "same")
            self.assertEqual(
                harness.comparable(
                    same | {"budget_round": identity}, same | {"budget_round": harness.budget_round(second)}
                ),
                [],
            )


class RoundResumeTest(unittest.TestCase):
    def test_resume_cannot_move_a_recorded_run_to_another_ledger(self) -> None:
        import test_harness

        fixture = test_harness.HarnessTest()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        first, second = fixture.base / "first.sqlite3", fixture.base / "second.sqlite3"
        output = fixture.base / "run"
        command = [
            "run",
            "--repo",
            str(fixture.repo),
            "--ref",
            "main",
            "--model",
            gateway.MODELS[0],
            "--repeats",
            "2",
            "--skip-generate",
            "--out",
            str(output),
        ]
        with patch("harness.gateway_transport.HardExecute", return_value=test_harness.agent(test_harness.BASE)):
            code, _, error = fixture.main("--hard-budget", "--budget-ledger", str(first), *command)
        self.assertEqual((code, error), (0, ""))

        def forbidden(*_arguments):
            self.fail("resume mismatch must be rejected before executing an agent")

        with patch("harness.gateway_transport.HardExecute", return_value=forbidden):
            code, _, error = fixture.main("--hard-budget", "--budget-ledger", str(second), *command, "--resume")
        self.assertEqual(code, 2)
        self.assertIn("resume parameters differ", error)

    def test_verdicts_and_validity_from_another_round_cannot_validate_answers(self) -> None:
        import json

        import records
        import test_harness

        fixture = test_harness.HarnessTest()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        output = fixture.run_harness("round-validity")
        self.assertEqual(fixture.main("judge", str(output), "--model", "judge-m")[0], 0)
        self.assertEqual(
            fixture.main(
                "judge-validate", str(output), "--model", "judge-m", "--second-model", "judge-n", "--per-domain", "2"
            )[0],
            0,
        )
        sessions = records.read_sessions(output / "sessions.jsonl")
        self.assertTrue(any(value is not None for session in sessions for value in session.criteria.values()))
        metadata = output / "run.json"
        metadata.write_text(json.dumps(json.loads(metadata.read_text()) | {"budget_round": {"uuid": "another-round"}}))
        with contextlib.redirect_stderr(io.StringIO()):
            harness.apply_judge(output, sessions)
        self.assertTrue(all(value is None for session in sessions for value in session.criteria.values()))
