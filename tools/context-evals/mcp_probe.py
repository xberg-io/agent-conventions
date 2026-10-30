#!/usr/bin/env python3
"""Analyze captured MCP catalogs and Claude startup transport without making model calls.

The inputs are controlled JSON/JSONL artifacts, not token-usage claims. Capture the real
server protocol and CLI requests first; this analyzer refuses empty or mismatched evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

from exposure import BYTES_PER_TOKEN


def _strings(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)


def _catalog(messages: list[dict]) -> tuple[list[dict], dict, str]:
    results = [message["result"] for message in messages if isinstance(message.get("result"), dict)]
    catalogs = [result["tools"] for result in results if "tools" in result]
    if not catalogs or not catalogs[0] or any(tools != catalogs[0] for tools in catalogs):
        raise ValueError("expected a nonempty stable catalog")
    tools = catalogs[0]
    if not all(
        isinstance(tool, dict) and tool.get("name") and isinstance(tool.get("inputSchema"), dict) for tool in tools
    ):
        raise ValueError("catalog tools need names and input schemas")
    if len({tool["name"] for tool in tools}) != len(tools):
        raise ValueError("catalog has duplicate tool names")
    initialized = [result for result in results if "serverInfo" in result]
    if len(initialized) != 1 or not initialized[0]["serverInfo"].get("version"):
        raise ValueError("expected initialized server metadata")
    return tools, initialized[0]["serverInfo"], initialized[0].get("instructions", "")


def _request_summary(request: dict, names: set[str]) -> dict:
    body = request.get("body", {})
    tools = body.get("tools")
    if not isinstance(tools, list) or not tools:
        raise ValueError("startup request lacks its tools array")
    eager = {tool.get("name") for tool in tools if tool.get("name") in names}
    if any(not isinstance(tool.get("input_schema"), dict) for tool in tools if tool.get("name") in eager):
        raise ValueError("advertised eager tools lack schemas")
    search = any(tool.get("name") == "ToolSearch" and isinstance(tool.get("input_schema"), dict) for tool in tools)
    context = "\n".join(_strings({key: body.get(key) for key in ("system", "messages")}))
    deferred_names = names - eager
    if deferred_names and not search:
        raise ValueError("omitted schemas without a search tool do not prove deferral")
    if any(not re.search(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", context) for name in deferred_names):
        raise ValueError("deferred names are absent from startup context")
    loading = "eager" if eager == names else "mixed" if eager else "deferred"
    return {
        "path": request["path"],
        "model": body.get("model"),
        "request_bytes": request.get("bytes"),
        "tool_count": len(tools),
        "mcp_schema_count": len(eager),
        "mcp_compact_schema_bytes": sum(
            len(json.dumps(tool, separators=(",", ":")).encode()) for tool in tools if tool.get("name") in eager
        ),
        "deferred_mcp_name_count": len(deferred_names),
        "tool_search": search,
        "deferred_placeholder": any(
            tool.get("name") == "DeferredToolPlaceholder" and tool.get("defer_loading") is True for tool in tools
        ),
        "schema_loading": loading,
    }


def analyze(
    catalog: list[dict], rpc: list[dict], startup: list[dict], requests: list[dict], server: str = "ai-rulez"
) -> dict:
    """Require actual catalog, connection and request evidence before classifying schema loading."""
    tools, info, instructions = _catalog(catalog)
    if any(row.get("direction") == "client" and row.get("message", {}).get("method") == "tools/call" for row in rpc):
        raise ValueError("tools/call occurred in a metadata-only probe")
    runtime_catalogs = []
    for row in rpc:
        result = row.get("message", {}).get("result", {})
        if row.get("direction") == "server" and isinstance(result, dict) and "tools" in result:
            runtime_catalogs.append(result["tools"])
    if not runtime_catalogs or any(runtime != tools for runtime in runtime_catalogs):
        raise ValueError("runtime catalog differs from measured server catalog")
    initialized = [row for row in startup if row.get("type") == "system" and row.get("subtype") == "init"]
    if len(initialized) != 1 or not any(
        item.get("name") == server and item.get("status") == "connected"
        for item in initialized[0].get("mcp_servers", [])
    ):
        raise ValueError("expected one connected MCP startup")
    prefix = f"mcp__{server}__"
    names = {prefix + tool["name"] for tool in tools}
    advertised = {name for name in initialized[0].get("tools", []) if name.startswith(prefix)}
    if advertised != names:
        raise ValueError("startup advertised tools differ from the server catalog")
    messages = [
        request
        for request in requests
        if request.get("path", "").startswith("/v1/messages") and "count_tokens" not in request["path"]
    ]
    if not messages:
        raise ValueError("no captured Messages request")
    canonical = b"".join(json.dumps(tool, separators=(",", ":")).encode() for tool in tools) + instructions.encode()
    return {
        "server_info": info,
        "catalog_tool_count": len(tools),
        "catalog_schema_instruction_bytes": len(canonical),
        "catalog_sha256": hashlib.sha256(canonical).hexdigest(),
        "static_estimated_tokens": round(len(canonical) / BYTES_PER_TOKEN),
        "token_scope": "static calibrated estimate; no native model input measurement",
        "startup_advertised_mcp_tools": sorted(advertised),
        "count_endpoint_requests": sum("count_tokens" in request.get("path", "") for request in requests),
        "startup_requests": [_request_summary(messages[0], names)],
        "followup_message_requests": len(messages) - 1,
    }


def _jsonl(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not rows or not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"expected nonempty JSON object rows: {path}")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("catalog", "rpc", "startup", "requests"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--server", default="ai-rulez")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = analyze(
        _jsonl(args.catalog), _jsonl(args.rpc), _jsonl(args.startup), json.loads(args.requests.read_text()), args.server
    )
    text = json.dumps(result, indent=2) + "\n"
    if args.out:
        args.out.write_text(text)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
