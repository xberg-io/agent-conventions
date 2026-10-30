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
