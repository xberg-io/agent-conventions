"""Fail-closed, integer accounting for bounded Anthropic evaluation rounds."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import sqlite3
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path

import runner

POLICY_VERSION = "anthropic-standard-sonnet-2026-10-30-1"
CONTEXT_TOKENS = 1_000_000
MODEL_OUTPUT_TOKENS = 128_000
OUTPUT_TOKENS = 4096
NANOS_PER_DOLLAR = 1_000_000_000
MAX_BUDGET_USD = 25
BODY_BYTES = 4 * 1024 * 1024
MODELS = ("claude-sonnet-5-5", "claude-sonnet-5")
TOKEN_KEYS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


class GatewayError(runner.RunnerError):
    pass


def integer(value: object, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise GatewayError("invalid or overflowing token/cost counter")
    return value


def usd_nanos(value: object) -> int:
    if isinstance(value, bool):
        raise GatewayError("invalid round budget")
    try:
        amount = Decimal(str(value))
        scaled = amount * NANOS_PER_DOLLAR
        if not amount.is_finite() or not 0 < amount <= MAX_BUDGET_USD or scaled != scaled.to_integral_value():
            raise GatewayError("invalid round budget")
        return int(scaled)
    except (InvalidOperation, ValueError) as exc:
        raise GatewayError("invalid round budget") from exc


def rates(model: str) -> dict[str, int]:
    if model not in MODELS:
        raise GatewayError("unpriced model")
    return {
        "input": 2000,
        "output": 10000,
        "write_5m": 2500,
        "write_1h": 4000,
        "read": 100 if model == MODELS[0] else 200,
    }


def manifest() -> dict:
    files = ("gateway.py", "gateway_transport.py", "harness.py", "runner.py", "judge.py")
    source = b"".join((Path(__file__).parent / name).read_bytes() for name in files)
    return {
        "version": POLICY_VERSION,
        "protocol": "hard-gateway-3",
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "source_files": list(files),
        "context_tokens": CONTEXT_TOKENS,
        "max_output_tokens": OUTPUT_TOKENS,
        "rates_nanos_per_token": {model: rates(model) for model in MODELS},
        "max_budget_usd": MAX_BUDGET_USD,
    }


def policy_hash() -> str:
    return hashlib.sha256(json.dumps(manifest(), sort_keys=True).encode()).hexdigest()


def check_cache(block: dict) -> None:
    if "cache_control" not in block:
        return
    cache = block["cache_control"]
    if not isinstance(cache, dict) or set(cache) - {"type", "ttl"} or cache.get("type") != "ephemeral":
        raise GatewayError("unknown cache policy")
    if cache.get("ttl", "5m") not in ("5m", "1h"):
        raise GatewayError("unpriced cache duration")


def check_content(content: object, tools: tuple[str, ...]) -> None:
    if isinstance(content, str):
        return
    if not isinstance(content, list):
        raise GatewayError("invalid message content")
    for block in content:
        if not isinstance(block, dict):
            raise GatewayError("invalid content block")
        kind = block.get("type")
        if kind not in ("text", "tool_use", "tool_result", "thinking", "redacted_thinking"):
            raise GatewayError("unsupported content or server feature")
        if kind == "tool_use" and block.get("name") not in tools:
            raise GatewayError("tool profile mismatch")
        if kind == "tool_result":
            check_content(block.get("content", ""), tools)
        check_cache(block)


class Policy:
    def prepare(self, payload: dict, tools: tuple[str, ...]) -> dict:
        allowed = {
            "model",
            "max_tokens",
            "messages",
            "system",
            "tools",
            "metadata",
            "temperature",
            "top_p",
            "top_k",
            "stop_sequences",
            "stream",
            "thinking",
            "output_config",
            "service_tier",
            "inference_geo",
            "speed",
            "cache_control",
            "context_management",
        }
        if not isinstance(payload, dict) or set(payload) - allowed:
            raise GatewayError("unsupported request option")
        rates(payload.get("model", ""))
        maximum = integer(payload.get("max_tokens"), MODEL_OUTPUT_TOKENS)
        if not maximum:
            raise GatewayError("output limit must be positive")
        self.check_routing(payload)
        if "context_management" in payload and payload["context_management"] != {
            "edits": [{"type": "clear_thinking_20251015", "keep": "all"}]
        }:
            raise GatewayError("server compaction and unknown context editing are unavailable")
        actual_tools = payload.get("tools", [])
        self.check_tools(actual_tools, tools)
        check_content(payload.get("system", ""), tools)
        self.check_messages(payload.get("messages"), tools)
        check_cache(payload)
        result = copy.deepcopy(payload)
        result.update(max_tokens=min(maximum, OUTPUT_TOKENS), service_tier="standard_only", inference_geo="global")
        self.check_thinking(result)
        try:
            if len(json.dumps(result, allow_nan=False).encode()) > BODY_BYTES:
                raise GatewayError("request body too large")
        except (ValueError, TypeError) as exc:
            raise GatewayError("invalid request JSON") from exc
        return result

    @staticmethod
    def check_messages(messages: object, tools: tuple[str, ...]) -> None:
        if not isinstance(messages, list) or not messages:
            raise GatewayError("messages missing")
        for message in messages:
            if not isinstance(message, dict) or message.get("role") not in ("user", "assistant", "system"):
                raise GatewayError("invalid message")
            if set(message) - {"role", "content", "output_config"}:
                raise GatewayError("unknown per-message option")
            if "output_config" in message:
                Policy.check_thinking({"output_config": message["output_config"]})
            check_content(message.get("content"), tools)

    @staticmethod
    def check_routing(payload: dict) -> None:
        if payload.get("service_tier", "auto") not in ("auto", "standard_only"):
            raise GatewayError("unpriced service tier")
        if payload.get("inference_geo", "global") != "global" or payload.get("speed", "standard") != "standard":
            raise GatewayError("unpriced routing or speed")

    @staticmethod
    def check_tools(actual: object, expected: tuple[str, ...]) -> None:
        if not isinstance(actual, list) or any(not isinstance(tool, dict) for tool in actual):
            raise GatewayError("invalid tool schema")
        names = [tool.get("name") for tool in actual]
        if (
            any(not isinstance(name, str) for name in names)
            or len(names) != len(expected)
            or set(names) != set(expected)
        ):
            raise GatewayError("tool profile mismatch")
        for tool in actual:
            if tool.get("type", "custom") != "custom" or tool.get("defer_loading", False):
                raise GatewayError("server or deferred tools are unavailable")
            check_cache(tool)

    @staticmethod
    def check_thinking(payload: dict) -> None:
        thinking = payload.get("thinking", {"type": "disabled"})
        if not isinstance(thinking, dict) or thinking.get("type") not in ("disabled", "adaptive", "enabled"):
            raise GatewayError("unknown thinking policy")
        if set(thinking) - {"type", "budget_tokens", "display"}:
            raise GatewayError("unknown thinking option")
        if "budget_tokens" in thinking and integer(thinking["budget_tokens"], OUTPUT_TOKENS) >= payload["max_tokens"]:
            raise GatewayError("thinking budget exceeds output cap")
        output = payload.get("output_config", {})
        if (
            not isinstance(output, dict)
            or set(output) - {"effort"}
            or output.get("effort", "high") not in ("low", "medium", "high", "max")
        ):
            raise GatewayError("unknown output policy")

    def reservation(self, model: str, max_tokens: int) -> int:
        price = rates(model)
        maximum = integer(max_tokens, OUTPUT_TOKENS)
        # ~keep Token counting is only an estimate. Independently reserve the documented entire
        # context ceiling for each input counter, charging all cache writes at the 1h maximum.
        return CONTEXT_TOKENS * (price["input"] + price["write_1h"] + price["read"]) + maximum * price["output"]

    def cost(self, usage: dict, model: str, max_tokens: int) -> int:
        price = rates(model)
        self.check_usage(usage, max_tokens)
        cache = usage.get("cache_creation")
        write = usage["cache_creation_input_tokens"] * price["write_1h"]
        if cache is not None:
            write = cache["ephemeral_5m_input_tokens"] * price["write_5m"]
            write += cache["ephemeral_1h_input_tokens"] * price["write_1h"]
        return (
            usage["input_tokens"] * price["input"]
            + usage["output_tokens"] * price["output"]
            + usage["cache_read_input_tokens"] * price["read"]
            + write
        )

    @staticmethod
    def check_usage(usage: dict, max_tokens: int) -> None:
        allowed = {
            *TOKEN_KEYS,
            "cache_creation",
            "service_tier",
            "speed",
            "inference_geo",
            "server_tool_use",
            "output_tokens_details",
        }
        if not isinstance(usage, dict) or set(usage) - allowed or not set(TOKEN_KEYS) <= usage.keys():
            raise GatewayError("missing or unpriced usage category")
        for key in TOKEN_KEYS:
            integer(usage[key], max_tokens if key == "output_tokens" else CONTEXT_TOKENS)
        if usage.get("service_tier", "standard") != "standard" or usage.get("speed", "standard") != "standard":
            raise GatewayError("unpriced response tier or speed")
        if usage.get("inference_geo", "global") != "global":
            raise GatewayError("unpriced response geography")
        cache = usage.get("cache_creation")
        if cache is not None:
            expected = {"ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens"}
            if not isinstance(cache, dict) or set(cache) != expected:
                raise GatewayError("unknown cache usage")
            if sum(integer(value, CONTEXT_TOKENS) for value in cache.values()) != usage["cache_creation_input_tokens"]:
                raise GatewayError("inconsistent cache usage")
        for name, allowed_keys in [
            ("server_tool_use", {"web_search_requests", "web_fetch_requests"}),
            ("output_tokens_details", {"thinking_tokens"}),
        ]:
            details = usage.get(name, {})
            if not isinstance(details, dict) or set(details) - allowed_keys:
                raise GatewayError("unpriced usage detail")
            for value in details.values():
                integer(value, usage["output_tokens"] if name == "output_tokens_details" else 0)


def process_identity(pid: int) -> str:
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "lstart="],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
    )
    return result.stdout.strip() if result.returncode == 0 else ""


class Ledger:
    def __init__(self, path: Path, total: object) -> None:
        self.total = usd_nanos(total)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            raise GatewayError("budget ledger must not be a symlink")
        self.path = path.resolve()
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(descriptor)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            legacy = db.execute("SELECT name FROM sqlite_master WHERE name = 'calls'").fetchone()
            if legacy and db.execute("SELECT COUNT(*) FROM calls").fetchone()[0]:
                raise GatewayError("hard rounds cannot reuse a historical soft-budget ledger")
            self.initialize_round(db)
            db.execute(
                "CREATE TABLE IF NOT EXISTS hard_requests (id INTEGER PRIMARY KEY, model TEXT, max_tokens INTEGER, charge INTEGER, state TEXT, owner INTEGER, birth TEXT)"
            )
            owners = db.execute("SELECT DISTINCT owner, birth FROM hard_requests WHERE state='pending'").fetchall()
            if any(process_identity(pid) != birth for pid, birth in owners):
                db.execute("UPDATE hard_round SET stopped='orphaned in-flight request' WHERE id=1")

    def initialize_round(self, db: sqlite3.Connection) -> None:
        import uuid

        db.execute(
            "CREATE TABLE IF NOT EXISTS hard_round (id INTEGER PRIMARY KEY CHECK(id=1), total INTEGER, "
            "policy TEXT, stopped TEXT, round_uuid TEXT NOT NULL, canonical_path TEXT NOT NULL)"
        )
        columns = {row[1] for row in db.execute("PRAGMA table_info(hard_round)")}
        if not {"round_uuid", "canonical_path"} <= columns:
            raise GatewayError("legacy hard round lacks immutable identity; use a fresh approved round")
        db.execute(
            "INSERT OR IGNORE INTO hard_round VALUES (1, ?, ?, '', ?, ?)",
            (self.total, policy_hash(), str(uuid.uuid4()), str(self.path)),
        )
        actual = db.execute("SELECT total, policy, canonical_path FROM hard_round WHERE id=1").fetchone()
        if actual != (self.total, policy_hash(), str(self.path)):
            raise GatewayError("round budget, pricing or canonical ledger identity changed")

    def identity(self) -> dict:
        with self.connection() as db:
            value, total, path = db.execute(
                "SELECT round_uuid, total, canonical_path FROM hard_round WHERE id=1"
            ).fetchone()
        return {"uuid": value, "total_nanos": total, "ledger_path": path}

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    def spent(self) -> int:
        with self.connection() as db:
            return db.execute("SELECT COALESCE(SUM(charge), 0) FROM hard_requests").fetchone()[0]

    def reserve(self, model: str, max_tokens: int) -> int:
        amount = Policy().reservation(model, max_tokens)
        birth = process_identity(os.getpid())
        if not birth:
            raise GatewayError("cannot establish request owner identity")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT stopped FROM hard_round WHERE id=1").fetchone()[0]:
                raise GatewayError("round stopped")
            spent = db.execute("SELECT COALESCE(SUM(charge), 0) FROM hard_requests").fetchone()[0]
            if spent + amount > self.total:
                raise GatewayError("round budget cannot reserve another complete request")
            return db.execute(
                "INSERT INTO hard_requests VALUES (NULL, ?, ?, ?, 'pending', ?, ?)",
                (model, max_tokens, amount, os.getpid(), birth),
            ).lastrowid

    def settle(self, reservation: int, cost: int) -> None:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT charge, state FROM hard_requests WHERE id=?", (reservation,)).fetchone()
            if row is None or row[1] != "pending":
                raise GatewayError("request is absent or already settled")
            integer(cost, row[0])
            db.execute("UPDATE hard_requests SET charge=?, state='settled' WHERE id=?", (cost, reservation))

    def uncertain(self, reservation: int, reason: str) -> None:
        with self.connection() as db:
            db.execute("UPDATE hard_requests SET state='uncertain' WHERE id=? AND state='pending'", (reservation,))
            db.execute("UPDATE hard_round SET stopped=? WHERE id=1", (reason,))

    def stop(self, reason: str) -> None:
        with self.connection() as db:
            db.execute("UPDATE hard_round SET stopped=? WHERE id=1", (reason,))

    def snapshot(self) -> dict:
        with self.connection() as db:
            stop = db.execute("SELECT stopped FROM hard_round WHERE id=1").fetchone()[0]
            rows = db.execute("SELECT id, model, max_tokens, charge, state FROM hard_requests ORDER BY id").fetchall()
        return {
            "policy": manifest(),
            "policy_sha256": policy_hash(),
            "total_nanos": self.total,
            "round": self.identity(),
            "reserved_or_spent_nanos": sum(row[3] for row in rows),
            "stop_reason": stop,
            "requests": [
                dict(zip(("id", "model", "max_tokens", "charge_nanos", "state"), row, strict=True)) for row in rows
            ],
        }


class StreamUsage:
    def __init__(self, model: str, max_tokens: int) -> None:
        self.model, self.max_tokens = model, max_tokens
        self.usage: dict = {}
        self.started = self.stopped = self.delta = False

    def feed(self, event: dict) -> None:
        if self.stopped:
            raise GatewayError("event after terminal stream marker")
        kind = event.get("type")
        if kind == "message_start":
            message = event.get("message", {})
            if self.started or message.get("model") != self.model:
                raise GatewayError("duplicate start or response model drift")
            self.started = True
            self.update(message.get("usage", {}))
        elif not self.started:
            raise GatewayError("stream has no message start")
        elif kind == "message_delta":
            usage = event.get("usage")
            if not isinstance(usage, dict) or "output_tokens" not in usage:
                raise GatewayError("missing final output usage")
            self.update(usage)
            delta = event.get("delta", {})
            if not isinstance(delta, dict):
                raise GatewayError("invalid terminal delta")
            self.delta = delta.get("stop_reason") in (
                "end_turn",
                "max_tokens",
                "stop_sequence",
                "tool_use",
                "pause_turn",
                "refusal",
                "model_context_window_exceeded",
            )
        elif kind == "message_stop":
            if not self.delta:
                raise GatewayError("stream has no final usage")
            self.stopped = True
        elif kind not in ("content_block_start", "content_block_delta", "content_block_stop", "ping"):
            raise GatewayError("unknown or failed stream event")

    def update(self, usage: dict) -> None:
        if not isinstance(usage, dict) or not usage:
            raise GatewayError("missing stream usage")
        merged = self.usage | usage
        Policy.check_usage(merged, self.max_tokens)
        for key in TOKEN_KEYS:
            if key in self.usage and merged[key] < self.usage[key]:
                raise GatewayError("nonmonotonic cumulative usage")
        old_cache, cache = self.usage.get("cache_creation", {}), merged.get("cache_creation", {})
        if any(cache.get(key, -1) < value for key, value in old_cache.items()):
            raise GatewayError("nonmonotonic cache usage")
        self.usage = merged

    def cost(self) -> int:
        if not self.started or not self.stopped:
            raise GatewayError("incomplete provider stream")
        return Policy().cost(self.usage, self.model, self.max_tokens)
