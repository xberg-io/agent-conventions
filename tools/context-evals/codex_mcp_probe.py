#!/usr/bin/env python3
"""Validate offline Codex code-mode MCP transport captures without running a client."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

PROBE_VERSION = "codex-mcp-1"

METADATA_PROGRAM = (
    'text({names:ALL_TOOLS.filter(x => x.name.includes("ai_rulez") || x.name.includes("ai-rulez")).map(x => x.name), '
    'selected:ALL_TOOLS.find(x => x.name === "mcp__ai_rulez__find_skill") || '
    'ALL_TOOLS.find(x => x.name.includes("ai_rulez"))})'
)

METADATA_METHODS = frozenset(
    {
        "initialize",
        "notifications/initialized",
        "tools/list",
        "resources/list",
        "prompts/list",
        "ping",
        "notifications/cancelled",
    }
)


def _reply(rpc: list[dict], method: str) -> dict:
    calls = [
        row["message"]
        for row in rpc
        if row.get("direction") == "client" and row.get("message", {}).get("method") == method
    ]
    if len(calls) != 1 or calls[0].get("id") is None:
        raise ValueError(f"expected one {method} request and response")
    replies = [
        row["message"]
        for row in rpc
        if row.get("direction") == "server" and row.get("message", {}).get("id") == calls[0].get("id")
    ]
    if len(replies) != 1 or not isinstance(replies[0].get("result"), dict):
        raise ValueError(f"missing successful {method} response")
    return replies[0]["result"]


def _catalog(rpc: list[dict]) -> tuple[list[dict], dict]:
    if any(
        row.get("direction") == "client" and row.get("message", {}).get("method") not in METADATA_METHODS for row in rpc
    ):
        raise ValueError("non-metadata MCP request occurred")
    initialized = _reply(rpc, "initialize")
    info = initialized.get("serverInfo", {})
    if not info.get("version"):
        raise ValueError("initialize response lacks server version")
    result = _reply(rpc, "tools/list")
    if result.get("nextCursor"):
        raise ValueError("unfinished catalog pagination")
    tools = result.get("tools")
    if (
        not isinstance(tools, list)
        or not tools
        or not all(
            isinstance(tool, dict)
            and isinstance(tool.get("name"), str)
            and tool["name"]
            and isinstance(tool.get("inputSchema"), dict)
            for tool in tools
        )
    ):
        raise ValueError("expected nonempty catalog with names and input schemas")
    if len({tool["name"] for tool in tools}) != len(tools):
        raise ValueError("duplicate catalog tool name")
    return tools, info


def _startup(body: dict) -> None:
    definitions = [
        tool
        for item in body.get("input", [])
        if item.get("type") == "additional_tools"
        for namespace in item.get("tools", [])
        if namespace.get("name") == "functions"
        for tool in namespace.get("tools", [])
    ]
    if not any(tool.get("name") == "exec" and tool.get("type") == "custom" for tool in definitions):
        raise ValueError("startup lacks the code-mode exec tool")
    serialized = json.dumps(body)
    if "mcp__ai_rulez" in serialized or "mcp__ai-rulez" in serialized:
        raise ValueError("startup already contains MCP names or definitions")


def _metadata(body: dict) -> dict:
    calls = [item for item in body.get("input", []) if item.get("type") == "custom_tool_call"]
    if len(calls) != 1 or calls[0].get("namespace") != "functions" or calls[0].get("name") != "exec":
        raise ValueError("expected one functions.exec metadata lookup")
    if (
        calls[0].get("input") != METADATA_PROGRAM
        or not isinstance(calls[0].get("call_id"), str)
        or not calls[0]["call_id"]
    ):
        raise ValueError("expected the controlled metadata program and call identity")
    outputs = [
        item
        for item in body.get("input", [])
        if item.get("type") == "custom_tool_call_output" and item.get("call_id") == calls[0].get("call_id")
    ]
    if len(outputs) != 1 or not isinstance(outputs[0].get("output"), list):
        raise ValueError("missing metadata lookup output")
    text = [part["text"] for part in outputs[0]["output"] if part.get("type") == "input_text"]
    if not text or any("truncated output" in part for part in text):
        raise ValueError("missing or truncated metadata output")
    try:
        value = json.loads(text[-1])
    except json.JSONDecodeError as error:
        raise ValueError("metadata output is not complete JSON") from error
    if not isinstance(value, dict):
        raise TypeError("metadata output must be an object")
    return value


def _registry(metadata: dict, expected: set[str]) -> str:
    names = metadata.get("names")
    if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
        raise ValueError("registry lacks its names")
    if len(names) != len(expected) or set(names) != expected:
        raise ValueError("runtime registry differs from connected catalog")
    selected = metadata.get("selected", {})
    name, description = selected.get("name"), selected.get("description", "")
    if name not in expected or not isinstance(description, str) or "exec tool declaration:" not in description:
        raise ValueError("selected registry entry lacks its callable definition")
    if not re.search(re.escape(name) + r"\(args:\s*\{", description):
        raise ValueError("selected definition lacks its parameter declaration")
    return name


def _completed(events: list[dict]) -> None:
    completed = [event for event in events if event.get("type") == "turn.completed"]
    answers = [
        event.get("item", {}).get("text")
        for event in events
        if event.get("type") == "item.completed" and event.get("item", {}).get("type") == "agent_message"
    ]
    if (
        len(completed) != 1
        or answers != ["LOCAL_CODEX_MCP_OK"]
        or any(event.get("type") == "turn.failed" for event in events)
    ):
        raise ValueError("expected one completed fixture turn")


def analyze(rpc: list[dict], requests: list[dict], events: list[dict], model_info: dict) -> dict:
    """Validate nonempty runtime metadata, not merely the absence of startup schemas."""
    tools, info = _catalog(rpc)
    if model_info.get("tool_mode") != "code_mode_only" or model_info.get("supports_search_tool") is not True:
        raise ValueError("expected the measured bundled code-mode model capabilities")
    posts = [request for request in requests if request.get("method") == "POST"]
    if len(posts) != 2 or any(request.get("path") != "/v1/responses" for request in posts):
        raise ValueError("expected startup and metadata followup Responses requests only")
    if any(request.get("body", {}).get("model") != model_info.get("slug") for request in posts):
        raise ValueError("request model differs from bundled model metadata")
    _startup(posts[0]["body"])
    expected = {"mcp__ai_rulez__" + re.sub(r"[^a-zA-Z0-9_]", "_", tool["name"]) for tool in tools}
    if len(expected) != len(tools):
        raise ValueError("catalog names collide after Codex normalization")
    selected = _registry(_metadata(posts[1]["body"]), expected)
    _completed(events)
    canonical = json.dumps(tools, separators=(",", ":")).encode()
    return {
        "probe_version": PROBE_VERSION,
        "server_info": info,
        "model": model_info["slug"],
        "tool_mode": model_info["tool_mode"],
        "catalog_tool_count": len(tools),
        "catalog_sha256": hashlib.sha256(canonical).hexdigest(),
        "startup_mcp_definition_count": 0,
        "runtime_metadata_count": len(expected),
        "selected_definition": selected,
        "responses_requests": len(posts),
        "mcp_source_calls": 0,
        "usage_scope": "synthetic fixture usage excluded; no native token or billing measurement",
    }


def _jsonl(path: Path) -> list[dict]:
    values = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not values or not all(isinstance(value, dict) for value in values):
        raise ValueError(f"expected nonempty JSON objects: {path}")
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("rpc", "requests", "events", "models"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    models = json.loads(args.models.read_text())["models"]
    selected = [model for model in models if model.get("slug") == args.model]
    if len(selected) != 1:
        raise ValueError("expected one bundled model entry")
    summary = analyze(_jsonl(args.rpc), json.loads(args.requests.read_text()), _jsonl(args.events), selected[0])
    text = json.dumps(summary, indent=2) + "\n"
    if args.out:
        args.out.write_text(text)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
