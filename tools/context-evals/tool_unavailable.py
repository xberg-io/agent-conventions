"""Match a source-bound native unavailable-tool refusal without allowing that tool or forwarding its history."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass

API_ERROR = "API Error: 400 round stopped or request refused"
TERMINAL_FIELDS = {
    "type",
    "subtype",
    "is_error",
    "terminal_reason",
    "api_error_status",
    "result",
    "stop_reason",
    "permission_denials",
    "safety_stops",
    "num_turns",
    "errors",
    "duration_api_ms",
    "session_id",
    "total_cost_usd",
    "usage",
    "modelUsage",
    "fast_mode_state",
    "fast_mode_disabled_reason",
    "subagent_stats",
    "duration_ms",
    "uuid",
    "queued_turn_count",
    "result_index",
    "model_usage_since_last_result",
}


def provider_events(data: bytes) -> list[dict]:
    frames = data.decode().replace("\r\n", "\n").split("\n\n")
    return [
        json.loads("\n".join(line[5:].lstrip() for line in frame.splitlines() if line.startswith("data:")))
        for frame in frames
        if any(line.startswith("data:") for line in frame.splitlines())
    ]


def response_message_id(content_type: str, data: bytes) -> str:
    try:
        if content_type.split(";", 1)[0].strip() == "application/json":
            value = json.loads(data).get("id")
        else:
            starts = [event for event in provider_events(data) if event.get("type") == "message_start"]
            value = starts[0].get("message", {}).get("id") if len(starts) == 1 else None
        return value if isinstance(value, str) else ""
    except (ValueError, TypeError, KeyError, UnicodeError, AttributeError):
        return ""


def native_response_ids(stdout: str) -> list[str]:
    try:
        events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
        return response_ids(events)
    except (ValueError, TypeError, KeyError, AttributeError):
        return []


def response_ids(events: list[dict]) -> list[str]:
    values = []
    for event in events:
        if event.get("type") == "assistant" and event.get("is_api_error_message") is not True:
            value = event.get("message", {}).get("id")
            if not isinstance(value, str) or not value:
                return []
            if value not in values:
                values.append(value)
    return values


def unavailable_message(name: str) -> str:
    return (
        f"<tool_use_error>Error: No such tool available: {name}. "
        f"{name} is disabled for this session, in subagents as well as here.</tool_use_error>"
    )


def call_hash(block: dict) -> str:
    fields = {key: block[key] for key in ("type", "id", "name", "input")}
    return hashlib.sha256(
        json.dumps(fields, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


@dataclass(frozen=True)
class Evidence:
    message_id: str
    tool_id: str
    name: str
    call_sha256: str


def evidence(message_id: object, block: object) -> Evidence | None:
    if not isinstance(block, dict) or set(block) - {"type", "id", "name", "input", "cache_control"}:
        return None
    if (
        block.get("type") != "tool_use"
        or not isinstance(message_id, str)
        or not message_id
        or not isinstance(block.get("id"), str)
        or not block["id"]
        or not isinstance(block.get("name"), str)
        or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", block["name"])
        or not isinstance(block.get("input"), dict)
    ):
        return None
    return Evidence(message_id, block["id"], block["name"], call_hash(block))


def response_sources(content_type: str, data: bytes) -> list[Evidence]:
    """Read only already usage-validated provider output; malformed tool metadata cannot certify a task failure."""
    try:
        if content_type.split(";", 1)[0].strip() == "application/json":
            message = json.loads(data)
            return [item for block in message.get("content", []) if (item := evidence(message.get("id"), block))]
        return stream_sources(provider_events(data))
    except (ValueError, TypeError, KeyError, UnicodeError, AttributeError):
        return []


def stream_sources(events: list[dict]) -> list[Evidence]:
    message_id, blocks, fragments, output = None, {}, {}, []
    for event in events:
        kind, index = event.get("type"), event.get("index")
        if kind == "message_start":
            message_id = event.get("message", {}).get("id")
        elif kind == "content_block_start":
            blocks[index], fragments[index] = copy.deepcopy(event.get("content_block")), []
        elif kind == "content_block_delta" and event.get("delta", {}).get("type") == "input_json_delta":
            fragments[index].append(event["delta"]["partial_json"])
        elif kind == "content_block_stop":
            block = blocks.pop(index, None)
            if isinstance(block, dict) and block.get("type") == "tool_use":
                text = "".join(fragments.pop(index, []))
                if text:
                    block["input"] = json.loads(text)
                if item := evidence(message_id, block):
                    output.append(item)
    return output


def result_matches(block: object, item: Evidence) -> bool:
    return (
        isinstance(block, dict)
        and not set(block) - {"type", "tool_use_id", "is_error", "content", "cache_control"}
        and block.get("type") == "tool_result"
        and block.get("tool_use_id") == item.tool_id
        and block.get("is_error") is True
        and block.get("content") == unavailable_message(item.name)
    )


def unexpected(block: object, tools: tuple[str, ...]) -> bool:
    return isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") not in tools


def request_calls(messages: list[dict], tools: tuple[str, ...], sources: list[Evidence]) -> list[tuple] | None:
    found = []
    for position, message in enumerate(messages):
        if not isinstance(message, dict) or not isinstance(message.get("content"), list):
            continue
        for offset, block in enumerate(message["content"]):
            if unexpected(block, tools):
                if evidence("candidate", block) is None:
                    return None
                matching = [item for item in sources if item.call_sha256 == call_hash(block)]
                if message.get("role") != "assistant" or len(matching) != 1:
                    return None
                found.append((position, offset, matching[0]))
    return found


def request_refusal(payload: dict, tools: tuple[str, ...], sources: list[Evidence]) -> tuple[Evidence, dict] | None:
    """Return a validation-only copy. The caller must never forward this modified request."""
    messages = payload.get("messages")
    if not tools or not isinstance(messages, list):
        return None
    found = request_calls(messages, tools, sources)
    if found is None or len(found) != 1:
        return None
    position, offset, item = found[0]
    if position + 1 >= len(messages) or messages[position + 1].get("role") != "user":
        return None
    results = messages[position + 1].get("content")
    if not isinstance(results, list) or sum(result_matches(block, item) for block in results) != 1:
        return None
    clean = copy.deepcopy(payload)
    clean["messages"][position]["content"][offset] = neutral(messages[position]["content"][offset])
    clean["messages"][position + 1]["content"] = [
        neutral(block) if result_matches(block, item) else block for block in results
    ]
    return item, clean


def neutral(block: dict) -> dict:
    return {"type": "text", "text": ""} | (
        {"cache_control": block["cache_control"]} if "cache_control" in block else {}
    )


def native_terminal(event: dict) -> bool:
    expected = {
        "type": "result",
        "subtype": "success",
        "is_error": True,
        "terminal_reason": "api_error",
        "api_error_status": 400,
        "result": API_ERROR,
        "stop_reason": "stop_sequence",
        "permission_denials": [],
        "safety_stops": 0,
    }
    return (
        not set(event) - TERMINAL_FIELDS
        and all(type(event.get(key)) is type(value) and event.get(key) == value for key, value in expected.items())
        and type(event.get("num_turns")) is int
        and event["num_turns"] >= 2
        and event.get("errors", []) == []
    )


def native_evidence(stdout: str, tools: tuple[str, ...]) -> Evidence | None:
    try:
        events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
        if not events or not all(isinstance(event, dict) for event in events):
            return None
        if sum(event.get("type") == "result" for event in events) != 1 or not native_terminal(events[-1]):
            return None
        inits = [event for event in events if event.get("type") == "system" and event.get("subtype") == "init"]
        if len(inits) != 1 or inits[0] != events[0] or sorted(inits[0].get("tools", [])) != sorted(tools):
            return None
        model = inits[0].get("model")
        if not isinstance(model, str) or not model:
            return None
        return native_calls(events, tools, model)
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


def native_sources(events: list[dict], tools: tuple[str, ...], model: str) -> list[tuple] | None:
    found = []
    for position, event in enumerate(events[:-1]):
        if event.get("type") != "assistant":
            continue
        message = event.get("message", {})
        for block in message.get("content", []):
            if unexpected(block, tools):
                item = evidence(message.get("id"), block)
                if item is None or message.get("role") != "assistant" or message.get("model") != model:
                    return None
                found.append((position, item))
    return found


def native_calls(events: list[dict], tools: tuple[str, ...], model: str) -> Evidence | None:
    found = native_sources(events, tools, model)
    if found is None or len(found) != 1:
        return None
    position, item = found[0]
    if position + 2 >= len(events):
        return None
    reply = events[position + 1]
    if reply.get("type") != "user" or reply.get("message", {}).get("role") != "user":
        return None
    results = [
        block
        for event in events
        if event.get("type") == "user"
        for block in event.get("message", {}).get("content", [])
        if isinstance(block, dict) and block.get("tool_use_id") == item.tool_id
    ]
    if len(results) != 1 or not result_matches(results[0], item):
        return None
    if results[0] not in reply.get("message", {}).get("content", []):
        return None
    return item if local_api_error(events[-2]) else None


def local_api_error(error: dict) -> bool:
    return not (
        error.get("type") != "assistant"
        or error.get("is_api_error_message") is not True
        or type(error.get("api_error_status")) is not int
        or error["api_error_status"] != 400
        or error.get("message", {}).get("content") != [{"type": "text", "text": API_ERROR}]
    )
