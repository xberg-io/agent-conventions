"""A verified maximum-turn task failure must not erase its result or poison billing."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

import gateway
import gateway_transport
import runner
import transcript

MODEL = "claude-sonnet-5-5"


class BoundedTaskFailureTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.ledger = gateway.Ledger(self.root / "round.sqlite3", 25)
        self.init = {
            "type": "system",
            "subtype": "init",
            "model": MODEL,
            "tools": list(runner.DEFAULT_TOOLS),
            "mcp_servers": [],
        }
        self.terminal = {
            "type": "result",
            "subtype": "error_max_turns",
            "is_error": True,
            "num_turns": 9,
            "stop_reason": "tool_use",
            "terminal_reason": "max_turns",
            "errors": ["Reached maximum number of turns (8)"],
            "safety_stops": 0,
            "permission_denials": [],
        }
        self.state = "settled"
        self.timeout = False
        self.returncode = 1

    def execute(self) -> runner.Completed:
        def isolated(_argv, _cwd, _environment, _timeout, gate):
            request = self.ledger.reserve(MODEL, 4096)
            if self.state != "pending":
                self.ledger.settle(request, 1000) if self.state != "uncertain" else self.ledger.uncertain(
                    request, "fixture"
                )
            if self.state == "stopped":
                self.ledger.stop("existing first stop")
            gate.observe(json.dumps(self.init))
            text = "\n".join(json.dumps(value) for value in (self.init, self.terminal)) + "\n"
            return runner.Completed(self.returncode, text, "", timed_out=self.timeout)

        with (
            patch("gateway_transport.verify_sandbox", return_value={}),
            patch("shutil.which", return_value=sys.executable),
            patch("gateway_transport.isolated_process", side_effect=isolated),
        ):
            execute = gateway_transport.HardExecute(self.ledger, "OFFLINE_UNUSED", provider=lambda _: None)
            command = runner.ClaudeAdapter().command(
                runner.SessionSpec("Fixture task", MODEL, 8, self.root / "mcp.json", runner.DEFAULT_TOOLS)
            )
            return execute(command, self.root, {"PATH": os.environ.get("PATH", "")}, 30)

    def test_known_maximum_turn_failure_is_retained_without_stopping_the_financial_round(self) -> None:
        result = self.execute()
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.bounded_failure)
        self.assertEqual(transcript.parse(result.stdout).error, "error_max_turns")
        self.assertEqual(transcript.parse(result.stdout).answer, "")
        self.assertEqual(self.ledger.snapshot()["stop_reason"], "")
        self.assertEqual(self.ledger.spent(), 1000)
        self.ledger.reserve(MODEL, 4096)

    def test_wrong_tool_or_model_profile_still_stops(self) -> None:
        self.init["tools"] = ["Bash"]
        result = self.execute()
        self.assertFalse(result.bounded_failure)
        self.assertTrue(self.ledger.snapshot()["stop_reason"])

    def test_unsettled_request_still_stops(self) -> None:
        self.state = "pending"
        result = self.execute()
        self.assertFalse(result.bounded_failure)
        self.assertTrue(self.ledger.snapshot()["stop_reason"])
        self.assertEqual(self.ledger.spent(), 6_140_960_000)

    def test_wrong_model_still_stops(self) -> None:
        self.init["model"] = "claude-sonnet-5"
        result = self.execute()
        self.assertFalse(result.bounded_failure)
        self.assertTrue(self.ledger.snapshot()["stop_reason"])

    def test_malformed_or_additional_failure_conditions_still_stop(self) -> None:
        for index, change in enumerate(
            [
                {"num_turns": True},
                {"num_turns": 8},
                {"is_error": False},
                {"errors": ["unknown failure"]},
                {"permission_denials": ["Read"]},
                {"safety_stops": 1},
                {"terminal_reason": "unknown"},
                {"result": "partial answer"},
            ]
        ):
            self.ledger = gateway.Ledger(self.root / f"bad-{index}.sqlite3", 25)
            original = self.terminal.copy()
            self.terminal.update(change)
            with self.subTest(change=change):
                self.execute()
                self.assertTrue(self.ledger.snapshot()["stop_reason"])
            self.terminal = original

    def test_another_actors_settled_request_is_not_this_actors_completion(self) -> None:
        other = gateway.Ledger(self.ledger.path, 25)
        request = other.reserve(MODEL, 4096)
        other.settle(request, 1000)
        self.assertFalse(self.ledger.actor_requests_settled())
        self.assertTrue(other.actor_requests_settled())

    def test_unknown_error_subtype_still_stops(self) -> None:
        self.terminal["subtype"] = "error_unknown"
        result = self.execute()
        self.assertFalse(result.bounded_failure)
        self.assertTrue(self.ledger.snapshot()["stop_reason"])

    def test_prior_stop_cannot_be_cleared_by_a_known_failure(self) -> None:
        self.state = "stopped"
        self.execute()
        self.assertEqual(self.ledger.snapshot()["stop_reason"], "existing first stop")

    def test_new_uncertainty_still_stops_and_retains_full_charge(self) -> None:
        self.state = "uncertain"
        result = self.execute()
        self.assertFalse(result.bounded_failure)
        self.assertTrue(self.ledger.snapshot()["stop_reason"])
        self.assertEqual(self.ledger.spent(), 6_140_960_000)

    def test_zero_exit_with_an_error_terminal_still_stops(self) -> None:
        self.returncode = 0
        self.terminal["subtype"] = "unknown_failure"
        result = self.execute()
        self.assertFalse(result.bounded_failure)
        self.assertTrue(self.ledger.snapshot()["stop_reason"])

    def test_zero_exit_with_the_success_terminal_keeps_the_round_open(self) -> None:
        self.returncode = 0
        self.terminal.update(
            subtype="success",
            is_error=False,
            result="fixture answer",
            terminal_reason="completed",
            errors=[],
            num_turns=1,
            stop_reason="end_turn",
        )
        result = self.execute()
        self.assertEqual(result.returncode, 0)
        self.assertFalse(result.bounded_failure)
        self.assertEqual(self.ledger.snapshot()["stop_reason"], "")

    def test_timeout_still_stops(self) -> None:
        self.timeout = True
        result = self.execute()
        self.assertFalse(result.bounded_failure)
        self.assertTrue(self.ledger.snapshot()["stop_reason"])


@unittest.skipUnless(sys.platform == "darwin", "macOS actual CLI fixture")
class ActualBoundedFailureTest(unittest.TestCase):
    def test_actual_cli_max_turn_failure_retains_return_one_without_stopping_settled_billing(self) -> None:
        from test_gateway_transport import stream_body

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "fixture.txt").write_text("OFFLINE_PUBLIC_FIXTURE")
            (root / "mcp.json").write_text('{"mcpServers":{}}')
            ledger = gateway.Ledger(root / "offline.sqlite3", 25)

            def provider(_request):
                events = [
                    json.loads(frame.split("data: ", 1)[1]) for frame in stream_body().decode().split("\n\n") if frame
                ]
                events[1]["content_block"] = {"type": "tool_use", "id": "toolu_offline", "name": "Read", "input": {}}
                events[2]["delta"] = {
                    "type": "input_json_delta",
                    "partial_json": json.dumps({"file_path": str(root / "fixture.txt")}),
                }
                events[4]["delta"]["stop_reason"] = "tool_use"
                return "text/event-stream", "".join(
                    f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events
                ).encode()

            execute = gateway_transport.HardExecute(ledger, "OFFLINE_NEVER_FORWARDED", provider=provider)
            argv = runner.ClaudeAdapter().command(
                runner.SessionSpec("Read fixture.", MODEL, 1, root / "mcp.json", runner.DEFAULT_TOOLS)
            )
            result = execute(argv, root, {"PATH": os.environ["PATH"]}, 30)
            self.assertEqual(result.returncode, 1)
            self.assertTrue(result.bounded_failure)
            self.assertEqual(transcript.parse(result.stdout).error, "error_max_turns")
            self.assertEqual(ledger.snapshot()["stop_reason"], "")
            self.assertEqual(ledger.snapshot()["requests"][0]["state"], "settled")


if __name__ == "__main__":
    unittest.main()
