"""No-provider-spend checks of the egress boundary and reserved in-flight billing."""

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import gateway
import gateway_transport
import runner
from test_gateway import MODEL, TOOLS, payload, usage

CREDENTIAL_PATHS = (
    ".ssh/id_ed25519",
    ".aws/credentials",
    ".netrc",
    ".config/gcloud/credentials.db",
    ".claude/.credentials.json",
    "Library/Keychains/login.keychain-db",
)


PROCESS_ENV_PROBE = """import ctypes,json,os,sys
libc=ctypes.CDLL(None,use_errno=True)
def inspect(pid,marker):
    mib=(ctypes.c_int*3)(1,49,pid);size=ctypes.c_size_t()
    first=libc.sysctl(mib,3,None,ctypes.byref(size),None,0)
    code=ctypes.get_errno()
    if first!=0:return {'rc':first,'errno':code,'visible':False}
    if not 0<size.value<1048576:raise RuntimeError('invalid bounded fixture process size')
    buffer=ctypes.create_string_buffer(size.value)
    ctypes.set_errno(0)
    second=libc.sysctl(mib,3,buffer,ctypes.byref(size),None,0)
    return {'rc':second,'errno':ctypes.get_errno(),'visible':(b'ANTHROPIC_API_KEY='+marker) in buffer.raw}
print(json.dumps({'own_environment_available':os.environ.get('ANTHROPIC_API_KEY')=='OFFLINE_CHILD_ONLY',
                  'self':inspect(os.getpid(),b'OFFLINE_CHILD_ONLY'),
                  'sibling':inspect(int(sys.argv[1]),b'OFFLINE_SIBLING_ONLY')}))
"""


def stream_body(final_usage: dict | None = None) -> bytes:
    initial = usage()
    initial["output_tokens"] = 0
    events = [
        {
            "type": "message_start",
            "message": {
                "id": "msg_offline",
                "type": "message",
                "role": "assistant",
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "model": MODEL,
                "usage": initial,
            },
        },
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Fixture answer"}},
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn", "stop_sequence": None},
            "usage": {"output_tokens": 20} if final_usage is None else final_usage,
        },
        {"type": "message_stop"},
    ]
    return "".join(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events).encode()


class BackendTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "round.sqlite3"
        self.ledger = gateway.Ledger(self.path, 25)
        self.calls = []

    def provider(self, request):
        self.assertEqual(self.ledger.spent(), 6_140_960_000)
        self.calls.append(copy.deepcopy(request))
        return "text/event-stream", stream_body()

    def test_reservation_commits_before_the_only_upstream_attempt(self) -> None:
        backend = gateway_transport.Backend(self.ledger, self.provider)
        content_type, body = backend.respond(payload(), MODEL, TOOLS)
        self.assertEqual(content_type, "text/event-stream")
        self.assertEqual(body, stream_body())
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0]["max_tokens"], 4096)
        self.assertEqual(self.ledger.spent(), 550_000)

    def test_missing_terminal_output_retains_full_reservation_and_stops_another_client(self) -> None:
        def provider(request):
            self.calls.append(request)
            return "text/event-stream", stream_body({"input_tokens": 100})

        backend = gateway_transport.Backend(self.ledger, provider)
        with self.assertRaises(gateway.GatewayError):
            backend.respond(payload(), MODEL, TOOLS)
        self.assertEqual(self.ledger.spent(), 6_140_960_000)
        self.assertEqual(self.ledger.snapshot()["requests"][0]["state"], "uncertain")
        self.assertTrue(self.ledger.snapshot()["stop_reason"])
        with self.assertRaises(gateway.GatewayError):
            backend.respond(payload(), MODEL, TOOLS)
        self.assertEqual(len(self.calls), 1)

    def test_transport_timeout_is_not_retried_and_keeps_the_whole_reservation(self) -> None:
        def provider(request):
            self.calls.append(request)
            raise TimeoutError("fixture timeout")

        backend = gateway_transport.Backend(self.ledger, provider)
        with self.assertRaises(gateway.GatewayError):
            backend.respond(payload(), MODEL, TOOLS)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.ledger.spent(), 6_140_960_000)
        self.assertTrue(self.ledger.snapshot()["stop_reason"])

    def test_tool_or_model_drift_is_rejected_without_forwarding_or_reserving(self) -> None:
        backend = gateway_transport.Backend(self.ledger, self.provider)
        for request in [payload() | {"model": "claude-sonnet-5"}, payload() | {"tools": []}]:
            with self.subTest(request=request), self.assertRaises(gateway.GatewayError):
                backend.respond(request, MODEL, TOOLS)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.ledger.spent(), 0)

    def test_unterminated_unknown_and_post_terminal_streams_are_not_settled(self) -> None:
        bad_streams = [
            stream_body().rsplit(b"event: message_stop", 1)[0],
            b"event: mystery\ndata: {}\n\n",
            stream_body() + b'event: message_delta\ndata: {"type":"message_delta","usage":{"output_tokens":21}}\n\n',
        ]
        for index, body in enumerate(bad_streams):
            ledger = gateway.Ledger(Path(self.temporary.name) / f"bad-{index}.sqlite3", 25)
            backend = gateway_transport.Backend(ledger, lambda _request, body=body: ("text/event-stream", body))
            with self.subTest(index=index), self.assertRaises(gateway.GatewayError):
                backend.respond(payload(), MODEL, TOOLS)
            self.assertEqual(ledger.spent(), 6_140_960_000)
            self.assertTrue(ledger.snapshot()["stop_reason"])

    def test_nonstream_requires_terminal_message_and_the_expected_model(self) -> None:
        request = payload() | {"stream": False}
        response = {"type": "message", "model": MODEL, "stop_reason": "end_turn", "usage": usage()}
        backend = gateway_transport.Backend(
            self.ledger, lambda _request: ("application/json", json.dumps(response).encode())
        )
        backend.respond(request, MODEL, TOOLS)
        self.assertEqual(self.ledger.spent(), 550_000)
        for change in [{"model": "sonnet"}, {"stop_reason": None}, {"usage": {}}]:
            ledger = gateway.Ledger(Path(self.temporary.name) / f"bad-{next(iter(change))}.sqlite3", 25)
            backend = gateway_transport.Backend(
                ledger, lambda _request, change=change: ("application/json", json.dumps(response | change).encode())
            )
            with self.subTest(change=change), self.assertRaises(gateway.GatewayError):
                backend.respond(request, MODEL, TOOLS)
            self.assertEqual(ledger.spent(), 6_140_960_000)


class LoopbackBoundaryTest(unittest.TestCase):
    setUp = BackendTest.setUp
    provider = BackendTest.provider

    def post(self, address, token, body, path="/v1/messages", length=None):
        import http.client

        connection = http.client.HTTPConnection(*address, timeout=2)
        headers = {"x-api-key": token, "Content-Type": "application/json"}
        if length is not None:
            headers["Content-Length"] = str(length)
        connection.request("POST", path, body, headers)
        response = connection.getresponse()
        result = response.status, response.read()
        connection.close()
        return result

    def test_exact_authenticated_route_forwards_once_and_never_echoes_credentials(self) -> None:
        with gateway_transport.LocalGateway(
            gateway_transport.Backend(self.ledger, self.provider), MODEL, TOOLS
        ) as server:
            status, body = self.post(server.address, server.token, json.dumps(payload()))
            self.assertEqual(status, 200)
            self.assertEqual(body, stream_body())
            self.assertEqual(len(self.calls), 1)
            self.assertNotIn(server.token.encode(), body)
            self.assertEqual(server.address[0], "127.0.0.1")

    def test_wrong_key_route_and_oversized_body_never_reach_provider(self) -> None:
        with gateway_transport.LocalGateway(
            gateway_transport.Backend(self.ledger, self.provider), MODEL, TOOLS
        ) as server:
            cases = [
                ("wrong", "/v1/messages", b"{}"),
                (server.token, "/v1/messages?else=true", b"{}"),
                (server.token, "/v1/messages", b"oversized"),
            ]
            for token, path, body in cases:
                with self.subTest(path=path):
                    length = gateway.BODY_BYTES + 1 if body == b"oversized" else None
                    status, result = self.post(server.address, token, body, path, length)
                    self.assertGreaterEqual(status, 400)
                    self.assertNotIn(server.token.encode(), result)
            self.assertEqual(self.calls, [])
            self.assertEqual(self.ledger.spent(), 0)


class SandboxBoundaryTest(unittest.TestCase):
    def test_unsupported_platform_refuses_before_starting_a_session(self) -> None:
        from unittest.mock import patch

        with patch("sys.platform", "linux"), self.assertRaises(gateway.GatewayError):
            gateway_transport.verify_sandbox()

    @unittest.skipUnless(sys.platform == "darwin", "macOS sandbox proof")
    def test_real_sandbox_allows_only_the_designated_ipv4_loopback_port(self) -> None:
        proof = gateway_transport.verify_sandbox()
        self.assertEqual(
            proof, {"allowed_ipv4": True, "denied_other_port": True, "denied_ipv6": True, "denied_external": True}
        )

    def test_child_environment_has_dummy_credentials_and_isolated_auth_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            environment = gateway_transport.child_environment(Path(directory), "dummy-local", 12345, MODEL)
            self.assertEqual(environment["ANTHROPIC_API_KEY"], "dummy-local")
            self.assertEqual(environment["ANTHROPIC_BASE_URL"], "http://127.0.0.1:12345")
            self.assertEqual(environment["HOME"], directory)
            self.assertEqual(
                set(name for name in environment if "KEY" in name or "TOKEN" in name), {"ANTHROPIC_API_KEY"}
            )
            self.assertNotIn("CLAUDE_CODE_OAUTH_TOKEN", environment)
            self.assertEqual(environment["ANTHROPIC_DEFAULT_HAIKU_MODEL"], MODEL)


class ProviderBoundaryTest(unittest.TestCase):
    def test_deadline_shuts_down_the_owned_socket_even_during_a_stalled_response(self) -> None:
        import time
        from unittest.mock import Mock, patch

        connection = Mock()

        def stalled_response():
            time.sleep(0.1)
            return Mock(status=200)

        connection.getresponse.side_effect = stalled_response
        with patch("http.client.HTTPSConnection", return_value=connection), self.assertRaises(gateway.GatewayError):
            gateway_transport.AnthropicProvider("fixture-private-key", timeout=0.02)(payload())
        connection.sock.shutdown.assert_called_once()
        self.assertTrue(connection.close.called)

    def test_fixed_tls_endpoint_single_attempt_and_private_auth_replacement(self) -> None:
        from unittest.mock import Mock, patch

        response = Mock()
        response.status = 200
        response.getheader.side_effect = lambda name, default=None: {
            "Content-Type": "text/event-stream",
            "Content-Encoding": None,
        }.get(name)
        response.read1.side_effect = [stream_body(), b""]
        connection = Mock()
        connection.getresponse.return_value = response
        with patch("http.client.HTTPSConnection", return_value=connection) as factory:
            provider = gateway_transport.AnthropicProvider("fixture-private-key")
            content_type, body = provider(payload())
        self.assertEqual(content_type, "text/event-stream")
        self.assertEqual(body, stream_body())
        self.assertEqual(factory.call_args.args, ("api.anthropic.com", 443))
        self.assertEqual(connection.request.call_count, 1)
        args, kwargs = connection.request.call_args
        self.assertEqual(args[:2], ("POST", "/v1/messages"))
        self.assertEqual(kwargs["headers"]["x-api-key"], "fixture-private-key")
        self.assertNotIn("fixture-private-key", args[2])
        self.assertTrue(connection.close.called)

    def test_failed_status_is_never_followed_or_retried(self) -> None:
        from unittest.mock import Mock, patch

        response = Mock(status=307)
        connection = Mock()
        connection.getresponse.return_value = response
        with patch("http.client.HTTPSConnection", return_value=connection), self.assertRaises(gateway.GatewayError):
            gateway_transport.AnthropicProvider("fixture-private-key")(payload())
        self.assertEqual(connection.request.call_count, 1)
        self.assertTrue(connection.close.called)


@unittest.skipUnless(sys.platform == "darwin", "macOS sandbox proof")
class FileBoundaryTest(unittest.TestCase):
    def test_secret_files_globs_and_symlink_targets_are_unreadable_but_context_is_readable(self) -> None:
        import os
        import subprocess

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            original_home = base / "original-home"
            workspace = original_home / "workspace"
            session_home = base / "session-home"
            workspace.mkdir(parents=True)
            session_home.mkdir()
            secrets = [original_home / name for name in CREDENTIAL_PATHS]
            secrets += [workspace / ".env", workspace / "downloaded.pem"]
            for path in secrets:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("OFFLINE_FIXTURE_SECRET")
            (workspace / "AGENTS.md").write_text("Permitted context")
            (workspace / "leak-link").symlink_to(secrets[0])
            probe = """import glob,json,pathlib,sys
root=pathlib.Path(sys.argv[1]); paths=json.loads(sys.argv[2]); result={}
for name in paths+['leak-link']:
    path=pathlib.Path(name) if name!='leak-link' else root/name
    try: path.read_bytes();result[str(path)]=False
    except PermissionError: result[str(path)]=True
result['glob_hidden']=not glob.glob(str(root/'.env'))
result['context']=(root/'AGENTS.md').read_text()=='Permitted context'
print(json.dumps(result))
"""
            command = gateway_transport.sandbox_command(
                12345,
                [sys.executable, "-I", "-c", probe, str(workspace), json.dumps([str(path) for path in secrets])],
                workspace=workspace,
                home=session_home,
                original_home=original_home,
            )
            result = subprocess.run(
                command, capture_output=True, text=True, env={"PATH": os.environ["PATH"]}, timeout=10
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            rows = json.loads(result.stdout)
            self.assertEqual(len(rows), len(secrets) + 3)
            self.assertTrue(all(rows.values()), rows)


class InitializationGateTest(unittest.TestCase):
    def test_only_exact_init_tools_model_and_empty_mcp_release_the_gate(self) -> None:
        for change in [{"tools": ["Bash"]}, {"model": "unpriced"}, {"mcp_servers": [{"name": "unexpected"}]}]:
            gate = gateway_transport.InitGate(MODEL, TOOLS)
            gate.observe(
                json.dumps(
                    {"type": "system", "subtype": "init", "model": MODEL, "tools": list(TOOLS), "mcp_servers": []}
                    | change
                )
            )
            with self.subTest(change=change), self.assertRaises(gateway.GatewayError):
                gate.require()
        gate = gateway_transport.InitGate(MODEL, TOOLS)
        gate.observe(
            json.dumps({"type": "system", "subtype": "init", "model": MODEL, "tools": list(TOOLS), "mcp_servers": []})
        )
        gate.require()
        self.assertTrue(gate.valid)


@unittest.skipUnless(sys.platform == "darwin", "macOS sandbox proof")
class ActualCliTest(unittest.TestCase):
    def test_real_cli_agent_and_judge_profiles_route_only_to_the_mocked_provider(self) -> None:
        import os
        import shutil

        import runner

        self.assertIsNotNone(shutil.which("claude"), "real Claude CLI required for this local contract")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mcp.json").write_text('{"mcpServers":{}}')
            for index, tools in enumerate([TOOLS, ()]):
                ledger = gateway.Ledger(root / f"round-{index}.sqlite3", 25)
                calls = []

                def provider(request: dict, calls: list = calls, ledger: gateway.Ledger = ledger) -> tuple[str, bytes]:
                    calls.append(request)
                    self.assertEqual(ledger.spent(), 6_140_960_000)
                    return "text/event-stream", stream_body()

                execute = gateway_transport.HardExecute(ledger, "never-forwarded-fixture", provider=provider)
                spec = runner.SessionSpec("Reply with one short sentence.", MODEL, 1, root / "mcp.json", tools)
                result = execute(runner.ClaudeAdapter().command(spec), root, {"PATH": os.environ["PATH"]}, 30)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                self.assertFalse(result.timed_out)
                self.assertEqual(runner.tool_profile_error(result.stdout, tools), "")
                self.assertEqual(len(calls), 1)
                self.assertEqual(ledger.spent(), 550_000)
                self.assertIn("Fixture answer", result.stdout)
                self.assertNotIn("never-forwarded-fixture", result.stdout + result.stderr)

    def test_real_read_tool_cannot_send_a_fixture_secret_but_can_read_project_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("OFFLINE_FIXTURE_SECRET_NEVER_SEND")
            (root / "AGENTS.md").write_text("Permitted offline context")
            mcp = root / "mcp.json"
            mcp.write_text('{"mcpServers":{}}')
            ledger, requests = gateway.Ledger(root / "round.sqlite3", 25), []

            def provider(request: dict) -> tuple[str, bytes]:
                requests.append(request)
                self.assertNotIn("OFFLINE_FIXTURE_SECRET_NEVER_SEND", json.dumps(request))
                if len(requests) > 2:
                    return "text/event-stream", stream_body()
                target = ".env" if len(requests) == 1 else "AGENTS.md"
                frames = stream_body().decode().split("\n\n")
                events = [json.loads(frame.split("data: ", 1)[1]) for frame in frames if frame]
                events[1]["content_block"] = {
                    "type": "tool_use",
                    "id": f"toolu_{len(requests)}",
                    "name": "Read",
                    "input": {},
                }
                events[2]["delta"] = {
                    "type": "input_json_delta",
                    "partial_json": json.dumps({"file_path": str(root / target)}),
                }
                events[4]["delta"]["stop_reason"] = "tool_use"
                body = "".join(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events).encode()
                return "text/event-stream", body

            execute = gateway_transport.HardExecute(ledger, "unused-fixture", provider=provider)
            command = runner.ClaudeAdapter().command(
                runner.SessionSpec("Read the requested fixture files.", MODEL, 3, mcp, TOOLS)
            )
            result = execute(command, root, {"PATH": os.environ["PATH"]}, 30)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(len(requests), 3)
            self.assertIn("Permitted offline context", json.dumps(requests[-1]))
            self.assertNotIn("OFFLINE_FIXTURE_SECRET_NEVER_SEND", result.stdout + result.stderr)
            results = [
                block
                for message in requests[1]["messages"]
                for block in message.get("content", [])
                if isinstance(block, dict) and block.get("type") == "tool_result"
            ]
            self.assertTrue(any(block.get("is_error") for block in results), "secret read must fail")


@unittest.skipUnless(sys.platform == "darwin", "macOS sandbox proof")
class DriftBeforeForwardingTest(unittest.TestCase):
    def test_advertised_bash_is_refused_before_any_provider_reservation(self) -> None:
        import os

        import runner

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root / "claude"
            fixture.write_text(
                f"#!{Path(sys.executable).resolve()}\n"
                + """import http.client,json,os,urllib.parse
print(json.dumps({"type":"system","subtype":"init","model":"claude-sonnet-5-5","tools":["Bash"],"mcp_servers":[]}),flush=True)
url=urllib.parse.urlsplit(os.environ['ANTHROPIC_BASE_URL'])
connection=http.client.HTTPConnection(url.hostname,url.port,timeout=5)
connection.request('POST','/v1/messages',json.dumps({"model":"claude-sonnet-5-5"}),{'x-api-key':os.environ['ANTHROPIC_API_KEY']})
response=connection.getresponse();response.read()
raise SystemExit(1 if response.status==400 else 0)
"""
            )
            fixture.chmod(0o700)
            mcp = root / "mcp.json"
            mcp.write_text('{"mcpServers":{}}')
            ledger = gateway.Ledger(root / "round.sqlite3", 25)
            calls = []
            execute = gateway_transport.HardExecute(ledger, "fixture", provider=lambda request: calls.append(request))
            command = runner.ClaudeAdapter().command(runner.SessionSpec("Fixture", MODEL, 1, mcp, TOOLS))
            result = execute(command, root, {"PATH": str(root) + os.pathsep + os.environ["PATH"]}, 10)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn('"tools": ["Bash"]', result.stdout)
            self.assertEqual(calls, [])
            self.assertEqual(ledger.spent(), 0)
            self.assertTrue(ledger.snapshot()["stop_reason"])


@unittest.skipUnless(sys.platform == "darwin", "macOS sandbox proof")
class WriteBoundaryTest(unittest.TestCase):
    def test_ledger_controller_source_and_worktree_reject_direct_symlink_and_hardlink_writes(self) -> None:
        import subprocess

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            original, home = base / "original", base / "session"
            workspace, controller = original / "worktree", original / "controller"
            for path in (home, workspace, controller):
                path.mkdir(parents=True)
            protected = [controller / "round.sqlite3", controller / "gateway.py", workspace / "AGENTS.md"]
            for index, path in enumerate(protected):
                path.write_bytes(b"UNCHANGED")
                (home / f"symlink-{index}").symlink_to(path)
            probe = """import json,os,pathlib,sys
home=pathlib.Path(sys.argv[1]);paths=json.loads(sys.argv[2]);rows={}
for index,name in enumerate(paths):
    for mode,path in [('direct',pathlib.Path(name)),('symlink',home/f'symlink-{index}')]:
        try:path.write_bytes(b'CORRUPTED');rows[f'{index}-{mode}']=False
        except PermissionError:rows[f'{index}-{mode}']=True
    try:os.link(name,home/f'hardlink-{index}');rows[f'{index}-hardlink']=False
    except PermissionError:rows[f'{index}-hardlink']=True
(home/'config').write_text('permitted session state');rows['home_write']=True
with open('/dev/null','w') as sink:sink.write('fixture')
rows['null_write']=True
print(json.dumps(rows))
"""
            command = gateway_transport.sandbox_command(
                12345,
                [
                    str(Path(sys.executable).resolve()),
                    "-I",
                    "-c",
                    probe,
                    str(home),
                    json.dumps([str(path) for path in protected]),
                ],
                workspace=workspace,
                home=home,
                original_home=original,
            )
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            rows = json.loads(result.stdout)
            self.assertEqual(len(rows), 11)
            self.assertTrue(all(rows.values()), rows)
            self.assertEqual([path.read_bytes() for path in protected], [b"UNCHANGED"] * 3)

    def test_preexisting_hardlinks_in_a_writable_home_are_refused(self) -> None:
        import os

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            workspace, home = base / "worktree", base / "session"
            workspace.mkdir()
            home.mkdir()
            source = workspace / "source.py"
            source.write_text("unchanged")
            os.link(source, home / "alias")
            with self.assertRaises(gateway.GatewayError):
                gateway_transport.file_profile(workspace, home)


@unittest.skipUnless(sys.platform == "darwin", "macOS process boundary")
class ProcessBoundaryTest(unittest.TestCase):
    def test_sysctl_can_read_self_but_cannot_recover_a_controlled_siblings_dummy_key(self) -> None:
        import errno
        import subprocess

        probe = PROCESS_ENV_PROBE
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace, home = root / "case", root / "home"
            workspace.mkdir()
            home.mkdir()
            executable = str(Path(sys.executable).resolve())
            sibling = subprocess.Popen(
                [executable, "-I", "-c", "import time;time.sleep(30)"],
                env={"PATH": "/usr/bin:/bin", "ANTHROPIC_API_KEY": "OFFLINE_SIBLING_ONLY"},
            )
            try:
                self.assertIsNone(sibling.poll())
                command = gateway_transport.sandbox_command(
                    12345, [executable, "-I", "-c", probe, str(sibling.pid)], workspace=workspace, home=home
                )
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    env={"PATH": "/usr/bin:/bin", "ANTHROPIC_API_KEY": "OFFLINE_CHILD_ONLY"},
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                rows = json.loads(result.stdout)
                self.assertTrue(rows["own_environment_available"])
                self.assertEqual(rows["self"]["rc"], 0, rows)
                self.assertTrue(rows["self"]["visible"])
                self.assertEqual(rows["sibling"]["rc"], -1, rows)
                self.assertIn(rows["sibling"]["errno"], (errno.EACCES, errno.EPERM))
                self.assertFalse(rows["sibling"]["visible"])
                self.assertIsNone(sibling.poll())
            finally:
                sibling.terminate()
                sibling.wait(timeout=5)
