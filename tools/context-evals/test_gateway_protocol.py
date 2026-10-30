"""Documented provider protocol and private failure-accounting evidence."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent))

import gateway
import gateway_transport
import runner
from test_gateway import MODEL, TOOLS, payload
from test_gateway_transport import stream_body


class ProviderProtocolTest(unittest.TestCase):
    def test_updates_and_message_effort_use_only_the_documented_required_betas(self) -> None:
        request = payload() | {
            "thinking": {"type": "adaptive", "display": "updates"},
            "context_management": {"edits": [{"type": "clear_thinking_20251015", "keep": "all"}]},
        }
        request["messages"].append({"role": "system", "content": "Fixture", "output_config": {"effort": "medium"}})
        required = {
            "thinking-display-updates-2026-08-18",
            "context-management-2025-06-27",
            "mid-conversation-output-config-2026-07-01",
        }
        connection = Mock()
        response = Mock()

        def respond():
            headers = connection.request.call_args.kwargs["headers"]
            actual = set(headers.get("anthropic-beta", "").split(","))
            response.status = 200 if actual == required else 400
            response.getheader.side_effect = lambda name, default=None: {"Content-Type": "text/event-stream"}.get(
                name, default
            )
            response.read1.side_effect = [stream_body(), b""]
            return response

        connection.getresponse.side_effect = respond
        with tempfile.TemporaryDirectory() as directory, patch("http.client.HTTPSConnection", return_value=connection):
            ledger = gateway.Ledger(Path(directory) / "fixture.sqlite3", 25)
            backend = gateway_transport.Backend(ledger, gateway_transport.AnthropicProvider("OFFLINE_ONLY"))
            self.assertEqual(backend.respond(request, MODEL, TOOLS)[1], stream_body())
            self.assertEqual(ledger.spent(), 550_000)
            self.assertEqual(connection.request.call_count, 1)

    def test_provider_error_preserves_only_safe_fields_and_the_full_reservation(self) -> None:
        response, connection = Mock(status=400), Mock()
        response.getheader.side_effect = lambda name, default=None: {
            "request-id": "req_OFFLINE123",
            "Content-Type": "application/json",
        }.get(name, default)
        body = {"error": {"type": "invalid_request_error", "message": "PRIVATE_PROMPT_OR_AUTH_NEVER_LOG"}}
        response.read1.side_effect = [json.dumps(body).encode(), b""]
        connection.getresponse.return_value = response
        with tempfile.TemporaryDirectory() as directory, patch("http.client.HTTPSConnection", return_value=connection):
            ledger = gateway.Ledger(Path(directory) / "fixture.sqlite3", 25)
            backend = gateway_transport.Backend(ledger, gateway_transport.AnthropicProvider("PRIVATE_KEY_NEVER_LOG"))
            with self.assertRaises(gateway.GatewayError):
                backend.respond(payload(), MODEL, TOOLS)
            snapshot = ledger.snapshot()
            self.assertEqual(ledger.spent(), 6_140_960_000)
            self.assertEqual(
                snapshot["diagnostics"][0]["data"],
                {
                    "category": "upstream_http",
                    "status": 400,
                    "request_id": "req_OFFLINE123",
                    "error_type": "invalid_request_error",
                },
            )
            self.assertNotIn("PRIVATE_", json.dumps(snapshot))
            self.assertEqual(snapshot["requests"][0]["state"], "uncertain")
            self.assertEqual(connection.request.call_count, 1)

    def test_local_policy_failure_records_only_allowlisted_code_and_structural_shape(self) -> None:
        request = payload()
        request["messages"][0]["content"] = [{"type": "PRIVATE_CONTENT_KIND", "text": "PRIVATE_PROMPT"}]
        with tempfile.TemporaryDirectory() as directory:
            ledger = gateway.Ledger(Path(directory) / "offline.sqlite3", 25)
            provider = Mock(side_effect=AssertionError("provider must not be called"))
            backend = gateway_transport.Backend(ledger, provider)
            with self.assertRaises(gateway.GatewayError):
                backend.respond(request, MODEL, TOOLS)
            diagnostic = ledger.snapshot()["diagnostics"][0]["data"]
            self.assertEqual(diagnostic["policy_error"], "unsupported_content_or_server_feature")
            self.assertEqual(diagnostic["policy_shape"]["content_types"], ["unknown"])
            self.assertEqual(diagnostic["policy_shape"]["tool_names"], sorted(TOOLS))
            self.assertNotIn("PRIVATE_", json.dumps(ledger.snapshot()))
            self.assertEqual(ledger.snapshot()["requests"], [])
            provider.assert_not_called()

    def test_unrecognized_policy_exception_and_diagnostic_values_never_leak(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = gateway.Ledger(Path(directory) / "offline.sqlite3", 25)
            backend = gateway_transport.Backend(ledger, Mock())
            with (
                patch("gateway.Policy.prepare", side_effect=ValueError("PRIVATE_EXCEPTION")),
                self.assertRaises(gateway.GatewayError),
            ):
                backend.respond(payload(), MODEL, TOOLS)
            self.assertEqual(ledger.snapshot()["diagnostics"][0]["data"]["policy_error"], "unclassified_policy_failure")
            projected = gateway.safe_diagnostic(
                {
                    "category": "policy",
                    "policy_error": "PRIVATE_ERROR",
                    "policy_shape": {
                        "content_types": ["PRIVATE_CONTENT"],
                        "tool_names": ["PRIVATE_TOOL"],
                        "message_count": "PRIVATE_COUNT",
                        "PRIVATE_KEY": "PRIVATE_VALUE",
                    },
                }
            )
            self.assertNotIn("PRIVATE_", json.dumps(projected))
            self.assertEqual(projected["policy_error"], "unclassified_policy_failure")
            self.assertIsNone(projected["policy_shape"]["message_count"])

    def test_untrusted_policy_shape_counts_and_names_are_bounded(self) -> None:
        shape = gateway.safe_policy_shape(
            {
                "message_count": 2**200,
                "tool_count": True,
                "content_types": ["image", "PRIVATE_KIND"] * 100,
                "tool_names": ["PRIVATE_TOOL"] * 100,
                "tool_use_names": ["Write", "PRIVATE_TOOL"],
                "has_thinking": "PRIVATE_VALUE",
                "has_output_config": True,
                "PRIVATE_KEY": "PRIVATE_VALUE",
            }
        )
        self.assertEqual(shape["message_count"], 64)
        self.assertIsNone(shape["tool_count"])
        self.assertEqual(shape["content_types"], ["image", "unknown"])
        self.assertEqual(shape["tool_names"], ["unknown"])
        self.assertEqual(shape["tool_use_names"], ["Write", "unknown"])
        self.assertFalse(shape["has_thinking"])
        self.assertTrue(shape["has_output_config"])
        self.assertNotIn("PRIVATE_", json.dumps(shape))

    def test_first_stop_cause_is_immutable_and_later_rejections_are_counted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = gateway.Ledger(Path(directory) / "fixture.sqlite3", 25)
            ledger.stop("first provider failure")
            ledger.stop("later request refused")
            snapshot = ledger.snapshot()
            self.assertEqual(snapshot["stop_reason"], "first provider failure")
            self.assertEqual(snapshot["rejections"], 1)

    def test_invalid_success_stream_keeps_request_id_and_redacted_usage_shape(self) -> None:
        response, connection = Mock(status=200), Mock()
        response.getheader.side_effect = lambda name, default=None: {
            "request-id": "req_OFFLINE200",
            "Content-Type": "text/event-stream",
        }.get(name, default)
        response.read1.side_effect = [stream_body({"input_tokens": 100}), b""]
        connection.getresponse.return_value = response
        with tempfile.TemporaryDirectory() as directory, patch("http.client.HTTPSConnection", return_value=connection):
            ledger = gateway.Ledger(Path(directory) / "fixture.sqlite3", 25)
            backend = gateway_transport.Backend(ledger, gateway_transport.AnthropicProvider("OFFLINE_ONLY"))
            with self.assertRaises(gateway.GatewayError):
                backend.respond(payload(), MODEL, TOOLS)
            diagnostic = ledger.snapshot()["diagnostics"][0]["data"]
            self.assertEqual(diagnostic["status"], 200)
            self.assertEqual(diagnostic["request_id"], "req_OFFLINE200")
            self.assertEqual(diagnostic["category"], "usage")
            self.assertFalse(diagnostic["stream_shape"]["final_output_present"])
            self.assertIn("message_stop", diagnostic["stream_shape"]["events"])
            self.assertEqual(ledger.spent(), 6_140_960_000)


@unittest.skipUnless(sys.platform == "darwin", "macOS actual CLI fixture")
class NativePolicyFailureTest(unittest.TestCase):
    def test_actual_cli_forbidden_tool_followup_retains_allowlisted_policy_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mcp.json").write_text('{"mcpServers":{}}')
            ledger = gateway.Ledger(root / "OFFLINE_ONLY.sqlite3", 25)
            calls = []

            def provider(request: dict) -> tuple[str, bytes]:
                calls.append(request)
                events = [
                    json.loads(frame.split("data: ", 1)[1]) for frame in stream_body().decode().split("\n\n") if frame
                ]
                events[1]["content_block"] = {"type": "tool_use", "id": "toolu_offline", "name": "Write", "input": {}}
                events[2]["delta"] = {
                    "type": "input_json_delta",
                    "partial_json": json.dumps(
                        {"file_path": str(root / "never-written.txt"), "content": "OFFLINE_FIXTURE"}
                    ),
                }
                events[4]["delta"]["stop_reason"] = "tool_use"
                return "text/event-stream", "".join(
                    f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events
                ).encode()

            execute = gateway_transport.HardExecute(ledger, "OFFLINE_NEVER_FORWARDED", provider=provider)
            command = runner.ClaudeAdapter().command(
                runner.SessionSpec("Inspect fixture.", MODEL, 8, root / "mcp.json", TOOLS)
            )
            result = execute(command, root, {"PATH": os.environ["PATH"]}, 30)
            snapshot = ledger.snapshot()
            self.assertEqual(result.returncode, 1)
            self.assertFalse(result.timed_out)
            self.assertEqual(len(calls), 1)
            self.assertEqual(snapshot["requests"][0]["state"], "settled")
            self.assertEqual(snapshot["stop_reason"], "request policy or reservation refused")
            self.assertEqual(snapshot["diagnostics"][0]["data"]["policy_error"], "tool_profile_mismatch")
            self.assertEqual(snapshot["diagnostics"][0]["data"]["policy_shape"]["tool_use_names"], ["Write"])
            self.assertEqual(snapshot["diagnostics"][0]["data"]["policy_shape"]["tool_names"], sorted(TOOLS))
            self.assertFalse((root / "never-written.txt").exists())
