"""Offline controls for whole-request reservations, untrusted usage and shared stop state."""

import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

sys.path.insert(0, str(Path(__file__).parent))

import gateway

MODEL = "claude-sonnet-5-5"
TOOLS = ("Read", "Glob", "Grep", "Skill")


def payload() -> dict:
    return {
        "model": MODEL,
        "max_tokens": 32000,
        "messages": [{"role": "user", "content": "Fixture question"}],
        "tools": [{"name": name, "input_schema": {"type": "object"}} for name in TOOLS],
        "stream": True,
    }


def usage() -> dict:
    return {
        "input_tokens": 100,
        "output_tokens": 20,
        "cache_creation_input_tokens": 40,
        "cache_read_input_tokens": 50,
        "cache_creation": {"ephemeral_5m_input_tokens": 10, "ephemeral_1h_input_tokens": 30},
        "service_tier": "standard",
        "speed": "standard",
        "inference_geo": "global",
    }


class PolicyTest(unittest.TestCase):
    def test_all_thinking_retention_is_allowed_but_server_compaction_is_refused(self) -> None:
        request = payload() | {"context_management": {"edits": [{"type": "clear_thinking_20251015", "keep": "all"}]}}
        self.assertEqual(gateway.Policy().prepare(request, TOOLS)["context_management"], request["context_management"])
        request["context_management"]["edits"][0]["type"] = "compact_20260112"
        with self.assertRaises(gateway.GatewayError):
            gateway.Policy().prepare(request, TOOLS)

    def test_reserves_full_context_for_each_input_category_plus_clamped_output(self) -> None:
        policy = gateway.Policy()
        self.assertEqual(policy.reservation(MODEL, 4096), 6_140_960_000)
        self.assertEqual(policy.reservation("claude-sonnet-5", 4096), 6_240_960_000)

    def test_normalizes_output_limit_and_standard_global_routing_without_mutating_input(self) -> None:
        request = payload()
        result = gateway.Policy().prepare(request, TOOLS)
        self.assertEqual(result["max_tokens"], 4096)
        self.assertEqual(result["service_tier"], "standard_only")
        self.assertEqual(result["inference_geo"], "global")
        self.assertEqual(request["max_tokens"], 32000)

    def test_refuses_unknown_model_pricing_tiers_and_server_features(self) -> None:
        changes = [
            {"model": "sonnet"},
            {"model": "claude-opus-5-5"},
            {"service_tier": "priority"},
            {"inference_geo": "us"},
            {"speed": "fast"},
            {"max_tokens": True},
            {"max_tokens": 128001},
            {"max_tokens": -1},
            {"context_management": {}},
            {"container": "server"},
            {"mcp_servers": []},
        ]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(gateway.GatewayError):
                gateway.Policy().prepare(payload() | change, TOOLS)

    def test_refuses_tool_profile_drift_and_remote_images_before_a_request_can_be_reserved(self) -> None:
        request = payload()
        for tools in [[], request["tools"] + [{"name": "Bash"}], [{"type": "web_search_20250305", "name": "Read"}]]:
            with self.subTest(tools=tools), self.assertRaises(gateway.GatewayError):
                gateway.Policy().prepare(request | {"tools": tools}, TOOLS)
        request["messages"][0]["content"] = [{"type": "image", "source": {"type": "url", "url": "https://example.org"}}]
        with self.assertRaises(gateway.GatewayError):
            gateway.Policy().prepare(request, TOOLS)

    def test_judge_profile_accepts_only_an_actual_empty_tool_set(self) -> None:
        request = payload() | {"tools": []}
        self.assertEqual(gateway.Policy().prepare(request, ())["tools"], [])
        with self.assertRaises(gateway.GatewayError):
            gateway.Policy().prepare(payload(), ())

    def test_settles_every_cache_category_using_integer_nano_dollars(self) -> None:
        self.assertEqual(gateway.Policy().cost(usage(), MODEL, 4096), 550_000)
        self.assertEqual(gateway.Policy().cost(usage(), "claude-sonnet-5", 4096), 555_000)

    def test_unknown_cache_split_is_conservatively_charged_at_one_hour_rate(self) -> None:
        value = usage()
        del value["cache_creation"]
        self.assertEqual(gateway.Policy().cost(value, MODEL, 4096), 565_000)

    def test_usage_is_untrusted_and_rejects_missing_invalid_and_unpriced_categories(self) -> None:
        invalid = [
            {"input_tokens": -1},
            {"input_tokens": True},
            {"input_tokens": 1.5},
            {"input_tokens": 1_000_001},
            {"output_tokens": 4097},
            {"output_tokens": 2**63},
            {"service_tier": "priority"},
            {"speed": "fast"},
            {"inference_geo": "us"},
            {"unknown_billable_tokens": 3},
            {"server_tool_use": {"web_search_requests": 1}},
            {"cache_creation": {"ephemeral_5m_input_tokens": 1, "ephemeral_1h_input_tokens": 1}},
        ]
        for change in invalid:
            with self.subTest(change=change), self.assertRaises(gateway.GatewayError):
                gateway.Policy().cost(usage() | change, MODEL, 4096)
        missing = usage()
        del missing["input_tokens"]
        with self.assertRaises(gateway.GatewayError):
            gateway.Policy().cost(missing, MODEL, 4096)


class LedgerTest(unittest.TestCase):
    def test_uncertain_request_keeps_its_entire_reservation_and_stops_all_callers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "round.sqlite3"
            ledger = gateway.Ledger(path, 25)
            reservation = ledger.reserve(MODEL, 4096)
            ledger.uncertain(reservation, "provider transport interrupted")
            self.assertEqual(ledger.spent(), 6_140_960_000)
            with self.assertRaisesRegex(gateway.GatewayError, "stopped"):
                gateway.Ledger(path, 25).reserve(MODEL, 4096)

    def test_settlement_releases_only_the_verified_unused_reservation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            ledger = gateway.Ledger(Path(temporary) / "round.sqlite3", 25)
            reservation = ledger.reserve(MODEL, 4096)
            ledger.settle(reservation, 550_000)
            self.assertEqual(ledger.spent(), 550_000)
            with self.assertRaises(gateway.GatewayError):
                ledger.settle(reservation, 0)

    def test_atomic_reservations_include_pending_calls_across_independent_connections(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "round.sqlite3"
            ledgers = [gateway.Ledger(path, 25) for _ in range(8)]
            barrier = Barrier(8)

            def reserve(ledger):
                barrier.wait()
                try:
                    ledger.reserve(MODEL, 4096)
                    return True
                except gateway.GatewayError:
                    return False

            with ThreadPoolExecutor(max_workers=8) as workers:
                self.assertEqual(sum(workers.map(reserve, ledgers)), 4)
            self.assertEqual(ledgers[0].spent(), 24_563_840_000)

    def test_round_limit_and_pricing_identity_cannot_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "round.sqlite3"
            gateway.Ledger(path, 25)
            with self.assertRaises(gateway.GatewayError):
                gateway.Ledger(path, 24)
            for value in [0, -1, 25.01, float("nan"), True]:
                with self.subTest(value=value), self.assertRaises(gateway.GatewayError):
                    gateway.Ledger(Path(temporary) / "invalid.sqlite3", value)


class StreamTest(unittest.TestCase):
    def test_stop_without_terminal_delta_is_not_complete_billing(self) -> None:
        stream = gateway.StreamUsage(MODEL, 4096)
        stream.feed(self.start())
        stream.feed({"type": "message_delta", "usage": {"output_tokens": 20}})
        with self.assertRaises(gateway.GatewayError):
            stream.feed({"type": "message_stop"})

    def start(self):
        value = usage()
        value["output_tokens"] = 0
        return {"type": "message_start", "message": {"model": MODEL, "usage": value}}

    def test_terminal_stream_reconciles_cumulative_usage_once(self) -> None:
        stream = gateway.StreamUsage(MODEL, 4096)
        stream.feed(self.start())
        stream.feed({"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 20}})
        stream.feed({"type": "message_stop"})
        self.assertEqual(stream.cost(), 550_000)

    def test_incomplete_or_decreasing_stream_is_not_valid_billing_evidence(self) -> None:
        stream = gateway.StreamUsage(MODEL, 4096)
        stream.feed(self.start())
        with self.assertRaises(gateway.GatewayError):
            stream.cost()
        stream.feed({"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 20}})
        with self.assertRaises(gateway.GatewayError):
            stream.feed({"type": "message_delta", "usage": {"output_tokens": 19}})

    def test_final_usage_cannot_inherit_the_initial_output_counter(self) -> None:
        for value in [{"input_tokens": 100}, {"cache_creation_input_tokens": 40}]:
            stream = gateway.StreamUsage(MODEL, 4096)
            stream.feed(self.start())
            stream.feed({"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Output"}})
            with self.subTest(usage=value), self.assertRaises(gateway.GatewayError):
                stream.feed({"type": "message_delta", "usage": value})

    def test_stream_refuses_model_drift_unknown_events_and_usage_after_terminal(self) -> None:
        mutations = [
            {"type": "message_start", "message": {"model": "sonnet", "usage": usage()}},
            {"type": "billing_extension", "usage": usage()},
            {"type": "message_delta", "usage": {"output_tokens": -1}},
        ]
        for event in mutations:
            stream = gateway.StreamUsage(MODEL, 4096)
            with self.subTest(event=event), self.assertRaises(gateway.GatewayError):
                stream.feed(event)
        stream = gateway.StreamUsage(MODEL, 4096)
        stream.feed(self.start())
        stream.feed({"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 20}})
        stream.feed({"type": "message_stop"})
        with self.assertRaises(gateway.GatewayError):
            stream.feed({"type": "message_delta", "usage": {"output_tokens": 21}})
