"""Restricted Anthropic egress and isolated Claude subprocesses for hard-budget runs."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Self

import gateway
import runner

RESPONSE_BYTES = 16 * 1024 * 1024
CHUNK_BYTES = 64 * 1024
ERROR_BYTES = CHUNK_BYTES


def decode_json(data: bytes) -> dict:
    def reject_constant(_value: str) -> None:
        raise gateway.GatewayError("nonfinite provider JSON")

    value = json.loads(data, parse_constant=reject_constant)
    if not isinstance(value, dict):
        raise gateway.GatewayError("provider response must be an object")
    return value


def response_cost(content_type: str, data: bytes, model: str, maximum: int, streamed: bool) -> int:
    if len(data) > RESPONSE_BYTES:
        raise gateway.GatewayError("provider response exceeds bounded buffer")
    kind = content_type.split(";", 1)[0].strip()
    if not streamed and kind == "application/json":
        message = decode_json(data)
        if message.get("type") != "message" or message.get("model") != model or not message.get("stop_reason"):
            raise gateway.GatewayError("nonterminal response or model drift")
        return gateway.Policy().cost(message.get("usage"), model, maximum)
    if not streamed or kind != "text/event-stream":
        raise gateway.GatewayError("unexpected response encoding")
    stream = gateway.StreamUsage(model, maximum)
    text = data.decode("utf-8").replace("\r\n", "\n")
    for frame in text.split("\n\n"):
        if not frame.strip():
            continue
        fields = [line for line in frame.splitlines() if not line.startswith(":")]
        names = [line.removeprefix("event:").strip() for line in fields if line.startswith("event:")]
        values = [line.removeprefix("data:").lstrip() for line in fields if line.startswith("data:")]
        if len(names) != 1 or not values or len(fields) != len(names) + len(values):
            raise gateway.GatewayError("malformed provider stream")
        event = decode_json("\n".join(values).encode())
        if event.get("type") != names[0]:
            raise gateway.GatewayError("stream event identity mismatch")
        stream.feed(event)
    return stream.cost()


@dataclass(frozen=True)
class ProviderResponse:
    content_type: str
    data: bytes
    diagnostic: dict

    def __iter__(self) -> Iterator[str | bytes]:
        yield self.content_type
        yield self.data


Provider = Callable[[dict], tuple[str, bytes] | ProviderResponse]


def stream_shape(data: bytes) -> dict:
    shape = {"events": [], "initial_usage_present": {}, "final_output_present": False, "parseable": True}
    try:
        for frame in data.decode("utf-8").replace("\r\n", "\n").split("\n\n"):
            lines = [line[5:].lstrip() for line in frame.splitlines() if line.startswith("data:")]
            if not lines:
                continue
            event = decode_json("\n".join(lines).encode())
            kind = event.get("type")
            if kind not in shape["events"]:
                shape["events"].append(kind)
            if kind == "message_start":
                usage = event.get("message", {}).get("usage", {})
                shape["initial_usage_present"] = {key: key in usage for key in gateway.TOKEN_KEYS}
            if kind == "message_delta":
                shape["final_output_present"] = "output_tokens" in event.get("usage", {})
    except (ValueError, UnicodeError, TypeError, AttributeError, gateway.GatewayError):
        shape["parseable"] = False
    return gateway.safe_stream_shape(shape)


class Backend:
    def __init__(self, ledger: gateway.Ledger, provider: Provider) -> None:
        self.ledger, self.provider = ledger, provider

    def respond(self, payload: dict, model: str, tools: tuple[str, ...]) -> tuple[str, bytes]:
        reservation, stage, metadata = None, "policy", {}
        try:
            request = gateway.Policy().prepare(payload, tools)
            if request["model"] != model:
                raise gateway.GatewayError("CLI/request model mismatch")
            stage = "reservation"
            reservation = self.ledger.reserve(model, request["max_tokens"])
            stage = "transport"
            response = self.provider(request)
            content_type, data = response
            metadata = getattr(response, "diagnostic", {})
            stage = "usage"
            if request.get("stream", False):
                metadata = metadata | {"stream_shape": stream_shape(data)}
            cost = response_cost(content_type, data, model, request["max_tokens"], request.get("stream", False))
            stage = "settlement"
            self.ledger.settle(reservation, cost)
            return content_type, data
        except Exception as exc:
            diagnostic = exc.diagnostic if isinstance(exc, ProviderFailure) else metadata | {"category": stage}
            if reservation is None:
                self.ledger.stop("request policy or reservation refused", diagnostic)
            else:
                self.ledger.uncertain(reservation, "provider request could not be safely settled", diagnostic)
            raise gateway.GatewayError("provider request refused or billing uncertain; round stopped") from exc


class LocalGateway:
    def __init__(self, backend: Backend, model: str, tools: tuple[str, ...]) -> None:
        import secrets
        from http.server import ThreadingHTTPServer

        self.backend, self.model, self.tools = backend, model, tools
        self.token = secrets.token_urlsafe(32)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self.handler())
        self.server.daemon_threads = False
        self.address = self.server.server_address

    def handler(self) -> type:
        import hmac
        from http.server import BaseHTTPRequestHandler

        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format: str, *_arguments: object) -> None:
                return

            def do_POST(self) -> None:
                self.connection.settimeout(10)
                try:
                    if self.path not in ("/v1/messages", "/v1/messages?beta=true"):
                        raise gateway.GatewayError("unsupported API route")
                    if not hmac.compare_digest(self.headers.get("x-api-key", ""), owner.token):
                        raise gateway.GatewayError("unauthorized local request")
                    lengths = self.headers.get_all("Content-Length", [])
                    if len(lengths) != 1 or self.headers.get("Transfer-Encoding"):
                        raise gateway.GatewayError("request framing refused")
                    size = int(lengths[0])
                    if not 0 < size <= gateway.BODY_BYTES:
                        raise gateway.GatewayError("request body exceeds bound")
                    data = self.rfile.read(size)
                    if len(data) != size:
                        raise gateway.GatewayError("incomplete request body")
                    kind, body = owner.backend.respond(decode_json(data), owner.model, owner.tools)
                    self.send_response(200)
                except Exception:
                    kind, body = (
                        "application/json",
                        b'{"error":{"type":"gateway_refused","message":"round stopped or request refused"}}',
                    )
                    self.send_response(400)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)

        return Handler

    def __enter__(self) -> Self:
        import threading

        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_error: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


def sandbox_command(
    port: int,
    command: list[str],
    *,
    workspace: Path | None = None,
    home: Path | str | None = None,
    original_home: Path | None = None,
) -> list[str]:
    import sys

    if sys.platform != "darwin" or not 0 < port < 65536:
        raise gateway.GatewayError("hard-budget OS network confinement is unavailable")
    # ~keep KERN_PROCARGS2 needs a sysctl-read denial; process-info alone does not protect sibling environments.
    profile = (
        "(version 1)(allow default)(deny file-write*)(deny file-link)"
        "(deny mach-lookup)(deny appleevent-send)(deny mach-priv-task-port)"
        "(deny process-info*)(allow process-info* (target self))"
        '(deny sysctl-read (sysctl-name-prefix "kern.proc"))(deny network*)'
        f'(allow network-outbound (remote tcp4 "localhost:{port}"))'
    )
    if workspace is not None:
        profile += file_profile(workspace, home, original_home)
    return ["/usr/bin/sandbox-exec", "-p", profile, *command]


def child_environment(home: Path, token: str, port: int, model: str) -> dict[str, str]:
    import os

    if model not in gateway.MODELS:
        raise gateway.GatewayError("unknown child model")
    temporary = home / "tmp"
    temporary.mkdir(mode=0o700)
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "TMPDIR": str(temporary),
        "TMP": str(temporary),
        "TEMP": str(temporary),
        "XDG_CACHE_HOME": str(home / "cache"),
        "CLAUDE_CONFIG_DIR": str(home / "claude"),
        "ANTHROPIC_API_KEY": token,
        "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{port}",
        "NO_PROXY": "127.0.0.1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "DISABLE_TELEMETRY": "1",
        "DISABLE_ERROR_REPORTING": "1",
        "DISABLE_AUTOUPDATER": "1",
        "ENABLE_TOOL_SEARCH": "false",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": model,
        "CLAUDE_CODE_SUBAGENT_MODEL": model,
    }


def verify_sandbox() -> dict[str, bool]:
    import socket
    import subprocess
    import sys
    from contextlib import ExitStack

    with ExitStack() as stack:
        listeners = []
        for family, host in [(socket.AF_INET, "127.0.0.1"), (socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")]:
            listener = stack.enter_context(socket.socket(family))
            if family == socket.AF_INET6:
                listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            listener.bind((host, listeners[0] if family == socket.AF_INET6 else 0))
            listener.listen()
            listeners.append(listener.getsockname()[1])
        probe = """import errno,json,socket,sys
rows={}
for name,family,host,port,allowed in json.loads(sys.argv[1]):
    sock=socket.socket(family);sock.settimeout(1)
    try:
        sock.connect((host,port));rows[name]=allowed
    except OSError as error:
        rows[name]=not allowed and error.errno in (errno.EPERM,errno.EACCES)
    finally:
        sock.close()
print(json.dumps(rows))
"""
        cases = [
            ("allowed_ipv4", socket.AF_INET, "127.0.0.1", listeners[0], True),
            ("denied_other_port", socket.AF_INET, "127.0.0.1", listeners[1], False),
            ("denied_ipv6", socket.AF_INET6, "::1", listeners[2], False),
            ("denied_external", socket.AF_INET, "1.1.1.1", 443, False),
        ]
        command = sandbox_command(listeners[0], [sys.executable, "-I", "-c", probe, json.dumps(cases)])
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10,
            env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"},
            check=True,
        )
        proof = json.loads(result.stdout)
        if len(proof) != 4 or not all(value is True for value in proof.values()):
            raise gateway.GatewayError("OS network confinement negative control failed")
        return proof


def shutdown_socket(sock) -> None:
    import socket

    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


def provider_headers(payload: dict, api_key: str) -> dict[str, str]:
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
        "accept-encoding": "identity",
    }
    betas = []
    if "context_management" in payload:
        betas.append("context-management-2025-06-27")
    if payload.get("thinking", {}).get("display") == "updates":
        betas.append("thinking-display-updates-2026-08-18")
    if any("output_config" in message for message in payload["messages"]):
        betas.append("mid-conversation-output-config-2026-07-01")
    if betas:
        headers["anthropic-beta"] = ",".join(betas)
    return headers


class ProviderFailure(gateway.GatewayError):
    def __init__(self, response) -> None:
        self.diagnostic = gateway.safe_diagnostic(
            {
                "category": "upstream_http",
                "status": response.status,
                "request_id": response.getheader("request-id"),
                "error_type": provider_error_type(response),
            }
        )
        super().__init__("provider rejected the request; billing remains uncertain")


def provider_error_type(response) -> str | None:
    chunks, size = [], 0
    try:
        while chunk := response.read1(min(CHUNK_BYTES, ERROR_BYTES + 1 - size)):
            size += len(chunk)
            if size > ERROR_BYTES:
                return None
            chunks.append(chunk)
        value = decode_json(b"".join(chunks)).get("error", {})
        return value.get("type") if isinstance(value, dict) else None
    except (OSError, ValueError, TypeError, gateway.GatewayError):
        return None


class AnthropicProvider:
    def __init__(self, api_key: str, timeout: float = 120) -> None:
        if not api_key or not 0 < timeout <= 180:
            raise gateway.GatewayError("provider credential and bounded timeout are required")
        self._key, self.timeout = api_key, timeout

    def __call__(self, payload: dict) -> ProviderResponse:
        import http.client
        import ssl
        import time

        connection = http.client.HTTPSConnection(
            "api.anthropic.com", 443, context=ssl.create_default_context(), timeout=self.timeout
        )
        deadline = time.monotonic() + self.timeout
        timer = None
        try:
            connection.connect()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise gateway.GatewayError("provider connection exceeded deadline")
            timer = threading.Timer(remaining, shutdown_socket, args=(connection.sock,))
            timer.daemon = True
            timer.start()
            headers = provider_headers(payload, self._key)
            connection.request("POST", "/v1/messages", json.dumps(payload, allow_nan=False), headers=headers)
            response = connection.getresponse()
            if response.status != 200:
                raise ProviderFailure(response)
            if response.getheader("Content-Encoding") not in (None, "identity"):
                raise gateway.GatewayError("upstream response encoding refused")
            chunks, size = [], 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise gateway.GatewayError("provider deadline exhausted")
                if connection.sock is not None:
                    connection.sock.settimeout(remaining)
                chunk = response.read1(min(CHUNK_BYTES, RESPONSE_BYTES + 1 - size))
                if not chunk:
                    break
                size += len(chunk)
                if size > RESPONSE_BYTES:
                    raise gateway.GatewayError("provider body exceeds bound")
                chunks.append(chunk)
            return ProviderResponse(
                response.getheader("Content-Type", ""),
                b"".join(chunks),
                gateway.safe_diagnostic(
                    {"category": "upstream_http", "status": 200, "request_id": response.getheader("request-id")}
                ),
            )
        finally:
            if timer is not None:
                timer.cancel()
            connection.close()


def validate_writable_home(home: Path, workspace: Path, original: Path) -> None:
    import stat

    if home == original or home in original.parents or home.is_relative_to(workspace) or workspace.is_relative_to(home):
        raise gateway.GatewayError("writable home must be isolated from the case worktree and original home")
    for path in home.rglob("*"):
        info = path.lstat()
        if stat.S_ISREG(info.st_mode) and info.st_nlink > 1:
            raise gateway.GatewayError("writable home contains a preexisting hardlink")


def file_profile(workspace: Path, home: Path | str, original_home: Path | None = None) -> str:
    import pathlib
    import shutil
    import sys

    original = pathlib.Path(original_home or pathlib.Path.home()).resolve()
    writable = pathlib.Path(home).resolve() if home is not None else None
    if home is None or not pathlib.Path(home).is_dir() or not pathlib.Path(workspace).is_dir():
        raise gateway.GatewayError("isolated session paths are required")
    validate_writable_home(writable, pathlib.Path(workspace).resolve(), original)

    def quoted(value: Path | str) -> str:
        return json.dumps(str(pathlib.Path(value).resolve()))

    profile = f"(deny file-read* (subpath {quoted(original)}))"
    runtime = {pathlib.Path(sys.base_prefix)}
    if binary := shutil.which("claude"):
        runtime.add(pathlib.Path(binary).resolve().parent)
    allowed = {pathlib.Path(workspace), pathlib.Path(home), *runtime}
    for path in allowed:
        if path.resolve() == original or path.resolve() in original.parents:
            raise gateway.GatewayError("read exception would expose original home")
        profile += f"(allow file-read* (subpath {quoted(path)}))"
    pattern = (
        r"(^|/)([.][eE][nN][vV]($|[.])|[.]netrc$|[.]npmrc$|[^/]*[.]([pP][eE][mM]|[kK][eE][yY]|p12|pfx|keychain-db)$)"
    )
    profile += f"(deny file-read* (regex #{json.dumps(pattern)}))"
    profile += f'(allow file-write* (subpath {quoted(writable)}) (literal "/dev/null"))(deny file-link)'
    return profile


class InitGate:
    def __init__(self, model: str, tools: tuple[str, ...]) -> None:
        import threading

        self.model, self.tools = model, tools
        self.event, self.valid = threading.Event(), False

    def observe(self, line: str) -> None:
        try:
            value = json.loads(line)
        except ValueError:
            return
        if value.get("type") == "system" and value.get("subtype") == "init":
            actual = value.get("tools")
            self.valid = (
                isinstance(actual, list)
                and all(isinstance(name, str) for name in actual)
                and len(actual) == len(self.tools)
                and set(actual) == set(self.tools)
                and value.get("model") == self.model
                and value.get("mcp_servers") == []
            )
            self.event.set()

    def require(self) -> None:
        if not self.event.wait(10) or not self.valid:
            raise gateway.GatewayError("CLI initialization did not prove the restricted profile")


def capture_pipe(pipe: BinaryIO, output: bytearray, observe: Callable[[str], None], failed: threading.Event) -> None:
    try:
        while line := pipe.readline(RESPONSE_BYTES + 1):
            if len(output) + len(line) > RESPONSE_BYTES:
                failed.set()
                return
            output.extend(line)
            observe(line.decode("utf-8", errors="strict"))
    except Exception:
        failed.set()
    finally:
        pipe.close()


def isolated_process(
    argv: list[str], cwd: Path, environment: dict[str, str], timeout: float, gate: InitGate
) -> runner.Completed:
    workspace = next((path for path in (cwd, *cwd.parents) if (path / ".git").exists()), cwd)
    command = sandbox_command(
        int(environment["ANTHROPIC_BASE_URL"].rsplit(":", 1)[1]), argv, workspace=workspace, home=environment["HOME"]
    )
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    output, errors, failed = bytearray(), bytearray(), threading.Event()
    readers = [
        threading.Thread(target=capture_pipe, args=(process.stdout, output, gate.observe, failed)),
        threading.Thread(target=capture_pipe, args=(process.stderr, errors, lambda _line: None, failed)),
    ]
    for reader in readers:
        reader.start()
    deadline, timed_out = time.monotonic() + timeout, False
    try:
        while process.poll() is None:
            if failed.is_set() or time.monotonic() >= deadline:
                timed_out = not failed.is_set()
                break
            time.sleep(0.02)
    finally:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait()
    for reader in readers:
        reader.join(timeout=2)
    if any(reader.is_alive() for reader in readers) or failed.is_set():
        raise gateway.GatewayError("CLI output failed its bounded capture contract")
    return runner.Completed(
        process.returncode,
        output.decode("utf-8", errors="replace"),
        errors.decode("utf-8", errors="replace"),
        timed_out=timed_out,
    )


def bounded_task_failure(result: runner.Completed, argv: list[str], ledger: gateway.Ledger) -> bool:
    if result.returncode != 1 or result.timed_out or argv.count("--max-turns") != 1:
        return False
    try:
        maximum = int(argv[argv.index("--max-turns") + 1])
        events = [decode_json(line.encode()) for line in result.stdout.splitlines() if line.strip()]
    except (ValueError, IndexError, gateway.GatewayError):
        return False
    if maximum <= 0 or not events or sum(event.get("type") == "result" for event in events) != 1:
        return False
    terminal = events[-1]
    expected = {
        "type": "result",
        "subtype": "error_max_turns",
        "is_error": True,
        "num_turns": maximum + 1,
        "stop_reason": "tool_use",
        "terminal_reason": "max_turns",
        "errors": [f"Reached maximum number of turns ({maximum})"],
        "safety_stops": 0,
        "permission_denials": [],
    }
    if any(type(terminal.get(key)) is not type(value) or terminal.get(key) != value for key, value in expected.items()):
        return False
    if terminal.get("result") not in (None, ""):
        return False
    return ledger.actor_requests_settled()


class HardExecute:
    def __init__(self, ledger: gateway.Ledger, api_key: str, provider: Provider | None = None) -> None:
        self.ledger = ledger
        self.proof = verify_sandbox()
        self.provider = provider or AnthropicProvider(api_key)

    def __call__(self, argv: list[str], cwd: Path, env: Mapping[str, str], timeout: float) -> runner.Completed:
        import pathlib
        import shutil
        import tempfile

        import runner

        if pathlib.Path(argv[0]).name != "claude":
            clean = {
                key: value
                for key, value in env.items()
                if not any(word in key.upper() for word in ("KEY", "TOKEN", "SECRET", "PASSWORD"))
            }
            return runner.subprocess_execute(argv, cwd, clean, timeout)
        model, tools = self.profile(argv)
        gate = InitGate(model, tools)
        backend = Backend(self.ledger, self.provider)
        original = backend.respond

        def checked(payload: dict, expected_model: str, expected_tools: tuple[str, ...]) -> tuple[str, bytes]:
            try:
                gate.require()
            except gateway.GatewayError:
                self.ledger.stop("CLI initialization profile was not validated")
                raise
            return original(payload, expected_model, expected_tools)

        backend.respond = checked
        with tempfile.TemporaryDirectory(prefix="context-hard-budget-") as directory:
            home = pathlib.Path(directory)
            with LocalGateway(backend, model, tools) as server:
                environment = child_environment(home, server.token, server.address[1], model)
                binary = shutil.which(argv[0], path=env.get("PATH"))
                if binary is None:
                    raise gateway.GatewayError("Claude executable not found")
                try:
                    result = isolated_process(
                        [str(pathlib.Path(binary).resolve()), *argv[1:]], cwd, environment, timeout, gate
                    )
                except BaseException:
                    self.ledger.stop("isolated CLI interrupted or failed")
                    raise
            if (
                result.timed_out
                or not gate.valid
                or runner.tool_profile_error(result.stdout, tools)
                or (result.returncode and not bounded_task_failure(result, argv, self.ledger))
            ):
                self.ledger.stop("CLI execution did not complete with the verified tool profile")
            return result

    @staticmethod
    def profile(argv: list[str]) -> tuple[str, tuple[str, ...]]:
        import runner

        if argv.count("--model") != 1 or argv.count("--tools") != 1:
            raise gateway.GatewayError("explicit CLI model and tool profile are required")
        model = argv[argv.index("--model") + 1]
        tools = tuple(filter(None, argv[argv.index("--tools") + 1].split(",")))
        if model not in gateway.MODELS or tools not in ((), runner.DEFAULT_TOOLS):
            raise gateway.GatewayError("unsupported CLI model or tool profile")
        if "--strict-mcp-config" not in argv or "--mcp-config" not in argv:
            raise gateway.GatewayError("strict empty MCP configuration is required")
        return model, tools
