"""Documented provider protocol and private failure-accounting evidence."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent))

import gateway
import gateway_transport
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
