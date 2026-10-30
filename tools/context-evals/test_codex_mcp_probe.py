"""Guards against mistaking a missing Codex MCP integration for deferred schemas."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import codex_mcp_probe


def protocol() -> list[dict]:
    tools = [{"name": name, "inputSchema": {"type": "object"}} for name in ("find_skill", "load_skill")]
    return [
        {"direction": "client", "message": {"id": 0, "method": "initialize"}},
        {"direction": "server", "message": {"id": 0, "result": {"serverInfo": {"version": "5.9.3"}}}},
        {"direction": "client", "message": {"id": 1, "method": "tools/list"}},
        {"direction": "server", "message": {"id": 1, "result": {"tools": tools}}},
    ]


def transport() -> list[dict]:
    names = ["mcp__ai_rulez__find_skill", "mcp__ai_rulez__load_skill"]
    selected = {"name": names[0], "description": f"exec tool declaration:\ndeclare const tools: {{ {names[0]}(args: {{"}
    initial = {
        "model": "gpt-6.1-sol",
        "input": [
            {
                "type": "additional_tools",
                "tools": [
                    {
                        "type": "namespace",
                        "name": "functions",
                        "tools": [
                            {"type": "custom", "name": "exec", "description": "JavaScript metadata registry"},
                        ],
                    }
                ],
            }
        ],
    }
    followup = copy.deepcopy(initial)
    followup["input"].extend(
        [
            {
                "type": "custom_tool_call",
                "call_id": "lookup",
                "namespace": "functions",
                "name": "exec",
                "input": codex_mcp_probe.METADATA_PROGRAM,
            },
            {
                "type": "custom_tool_call_output",
                "call_id": "lookup",
                "output": [
                    {"type": "input_text", "text": json.dumps({"names": names, "selected": selected})},
                ],
            },
        ]
    )
    return [{"method": "POST", "path": "/v1/responses", "body": body} for body in (initial, followup)]


class CodexMcpProbeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rpc = protocol()
        self.requests = transport()
        self.events = [
            {"type": "item.completed", "item": {"type": "agent_message", "text": "LOCAL_CODEX_MCP_OK"}},
            {"type": "turn.completed", "usage": {"input_tokens": 123456}},
        ]
        self.model = {"slug": "gpt-6.1-sol", "tool_mode": "code_mode_only", "supports_search_tool": True}

    def analyze(self) -> dict:
        return codex_mcp_probe.analyze(self.rpc, self.requests, self.events, self.model)

    def test_real_catalog_and_registry_prove_code_mode_loading_without_native_token_claims(self) -> None:
        result = self.analyze()
        self.assertEqual(result["catalog_tool_count"], 2)
        self.assertEqual(result["startup_mcp_definition_count"], 0)
        self.assertEqual(result["runtime_metadata_count"], 2)
        self.assertEqual(result["selected_definition"], "mcp__ai_rulez__find_skill")
        self.assertNotIn("input_tokens", result)

    def test_empty_catalog_is_not_a_zero_schema_pass(self) -> None:
        self.rpc[-1]["message"]["result"]["tools"] = []
        with self.assertRaisesRegex(ValueError, "catalog"):
            self.analyze()

    def test_missing_initialize_or_tools_list_response_is_rejected(self) -> None:
        for position in (1, 3):
            with self.subTest(position=position):
                self.rpc = protocol()
                del self.rpc[position]
                with self.assertRaisesRegex(ValueError, "response"):
                    self.analyze()

    def test_mcp_source_invocation_is_rejected_even_if_proxy_blocked_it(self) -> None:
        self.rpc.append({"direction": "client", "message": {"id": 3, "method": "tools/call"}})
        with self.assertRaisesRegex(ValueError, "metadata"):
            self.analyze()

    def test_unfinished_pagination_is_rejected(self) -> None:
        self.rpc[-1]["message"]["result"]["nextCursor"] = "more"
        with self.assertRaisesRegex(ValueError, "pagination"):
            self.analyze()

    def test_empty_startup_tools_are_rejected(self) -> None:
        self.requests[0]["body"]["input"] = []
        with self.assertRaisesRegex(ValueError, "exec"):
            self.analyze()

    def test_missing_followup_or_metadata_output_is_rejected(self) -> None:
        for missing in ("request", "output"):
            self.requests = transport()
            if missing == "request":
                self.requests.pop()
            else:
                self.requests[1]["body"]["input"].pop()
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                self.analyze()

    def test_truncated_or_wrong_registry_cannot_confirm_availability(self) -> None:
        output = self.requests[1]["body"]["input"][-1]["output"][0]
        output["text"] = 'Warning: truncated output {"names":[]}'
        with self.assertRaisesRegex(ValueError, "truncated"):
            self.analyze()
        output["text"] = '{"names":[],"selected":{}}'
        with self.assertRaisesRegex(ValueError, "registry"):
            self.analyze()

    def test_eager_startup_mcp_definition_is_not_misreported_as_omitted(self) -> None:
        self.requests[0]["body"]["input"][0]["tools"].append({"name": "mcp__ai_rulez__find_skill"})
        with self.assertRaisesRegex(ValueError, "startup"):
            self.analyze()

    def test_incompatible_model_metadata_is_not_treated_as_default_code_mode(self) -> None:
        self.model["tool_mode"] = "direct"
        with self.assertRaisesRegex(ValueError, "code.mode"):
            self.analyze()

    def test_failed_cli_turn_is_rejected(self) -> None:
        self.events[-1] = {"type": "turn.failed"}
        with self.assertRaisesRegex(ValueError, "completed"):
            self.analyze()

    def test_non_metadata_exec_program_is_rejected(self) -> None:
        self.requests[1]["body"]["input"][-2]["input"] = 'await tools.exec_command({cmd:"pwd"})'
        with self.assertRaisesRegex(ValueError, "metadata"):
            self.analyze()

    def test_missing_tool_call_identity_is_rejected(self) -> None:
        for item in self.requests[1]["body"]["input"][-2:]:
            item.pop("call_id")
        with self.assertRaisesRegex(ValueError, "metadata"):
            self.analyze()

    def test_absent_callable_definition_is_rejected(self) -> None:
        output = self.requests[1]["body"]["input"][-1]["output"][0]
        data = json.loads(output["text"])
        data["selected"]["description"] = "name only"
        output["text"] = json.dumps(data)
        with self.assertRaisesRegex(ValueError, "definition"):
            self.analyze()


if __name__ == "__main__":
    unittest.main()
