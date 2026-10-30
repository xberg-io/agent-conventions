"""Offline guards for interpreting captured real MCP/Claude startup evidence."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import mcp_probe


class McpProbeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tools = [
            {"name": "find_skill", "description": "Find", "inputSchema": {"type": "object"}},
            {"name": "load_skill", "description": "Load", "inputSchema": {"type": "object"}},
        ]
        self.catalog = [
            {"id": 1, "result": {"serverInfo": {"name": "ai-rulez", "version": "5.9.3"}, "instructions": "Read only"}},
            {"id": 2, "result": {"tools": self.tools}},
        ]
        names = ["mcp__ai-rulez__" + tool["name"] for tool in self.tools]
        self.rpc = [{"direction": "server", "message": {"id": 2, "result": {"tools": self.tools}}}]
        self.startup = [
            {
                "type": "system",
                "subtype": "init",
                "tools": names,
                "mcp_servers": [{"name": "ai-rulez", "status": "connected"}],
            },
        ]
        self.requests = [
            {
                "path": "/v1/messages?beta=true",
                "body": {
                    "model": "local-fixture",
                    "messages": [{"role": "user", "content": "\n".join(names)}],
                    "tools": [
                        {"name": "ToolSearch", "input_schema": {"type": "object"}},
                        {"name": "DeferredToolPlaceholder", "defer_loading": True},
                    ],
                },
            }
        ]

    def analyze(self) -> dict:
        return mcp_probe.analyze(self.catalog, self.rpc, self.startup, self.requests)

    def test_names_only_startup_is_distinguished_from_eager_schemas(self) -> None:
        result = self.analyze()
        self.assertEqual(result["catalog_tool_count"], 2)
        self.assertGreater(result["catalog_schema_instruction_bytes"], 0)
        self.assertEqual(result["startup_requests"][0]["schema_loading"], "deferred")
        self.assertEqual(result["startup_requests"][0]["mcp_schema_count"], 0)
        self.requests[0]["body"]["tools"] = [
            {"name": "mcp__ai-rulez__" + tool["name"], "input_schema": tool["inputSchema"]} for tool in self.tools
        ]
        self.assertEqual(self.analyze()["startup_requests"][0]["schema_loading"], "eager")

    def test_an_empty_or_changed_catalog_cannot_prove_deferral(self) -> None:
        self.catalog[1]["result"]["tools"] = []
        with self.assertRaisesRegex(ValueError, "nonempty"):
            self.analyze()
        self.catalog[1]["result"]["tools"] = copy.deepcopy(self.tools)
        self.rpc[0]["message"]["result"]["tools"] = self.tools[:1]
        with self.assertRaisesRegex(ValueError, "catalog"):
            self.analyze()

    def test_a_failed_connection_or_missing_advertised_name_is_rejected(self) -> None:
        self.startup[0]["mcp_servers"][0]["status"] = "failed"
        with self.assertRaisesRegex(ValueError, "connected"):
            self.analyze()
        self.startup[0]["mcp_servers"][0]["status"] = "connected"
        self.startup[0]["tools"].pop()
        with self.assertRaisesRegex(ValueError, "advertised"):
            self.analyze()

    def test_absent_requests_or_tools_are_not_a_zero_schema_pass(self) -> None:
        self.requests[0]["body"].pop("tools")
        with self.assertRaisesRegex(ValueError, "tools"):
            self.analyze()
        self.requests.clear()
        with self.assertRaisesRegex(ValueError, "Messages"):
            self.analyze()

    def test_no_search_or_no_names_is_not_deferral_evidence(self) -> None:
        self.requests[0]["body"]["tools"] = [{"name": "Read"}]
        with self.assertRaisesRegex(ValueError, "search"):
            self.analyze()
        self.requests[0]["body"]["tools"] = [{"name": "ToolSearch", "input_schema": {"type": "object"}}]
        self.requests[0]["body"]["messages"] = []
        with self.assertRaisesRegex(ValueError, "names"):
            self.analyze()

    def test_tool_invocation_invalidates_a_metadata_only_probe(self) -> None:
        self.rpc.append({"direction": "client", "message": {"method": "tools/call"}})
        with self.assertRaisesRegex(ValueError, "tools/call"):
            self.analyze()

    def test_followup_messages_are_not_mislabelled_as_startup(self) -> None:
        followup = copy.deepcopy(self.requests[0])
        followup["body"]["tools"].append({"name": "mcp__ai-rulez__find_skill", "input_schema": {"type": "object"}})
        self.requests.append(followup)
        result = self.analyze()
        self.assertEqual(len(result["startup_requests"]), 1)
        self.assertEqual(result["followup_message_requests"], 1)
        self.assertEqual(result["startup_requests"][0]["schema_loading"], "deferred")

    def test_a_search_name_without_a_schema_is_not_sufficient(self) -> None:
        self.requests[0]["body"]["tools"] = [{"name": "ToolSearch"}]
        with self.assertRaisesRegex(ValueError, "search"):
            self.analyze()

    def test_synthetic_usage_is_never_reported_as_measured_tokens(self) -> None:
        self.requests[0]["body"]["usage"] = {"input_tokens": 123456}
        result = self.analyze()
        self.assertNotIn("input_tokens", result)
        self.assertEqual(result["token_scope"], "static calibrated estimate; no native model input measurement")


if __name__ == "__main__":
    unittest.main()
