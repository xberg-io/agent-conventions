"""A native unavailable-tool rejection ends its task without granting another provider request."""

import copy
import json
import os
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

import cases
import continuation
import gateway
import gateway_transport
import harness
import runner
import scoring
import testkit
import tool_unavailable
import transcript
from test_completion_metrics import record
from test_gateway import payload
from test_gateway_transport import stream_body

MODEL = "claude-sonnet-5-5"


def edit_stream(name: str = "Edit", inputs: dict | None = None, sequence: int = 0) -> bytes:
    events = [json.loads(frame.split("data: ", 1)[1]) for frame in stream_body().decode().split("\n\n") if frame]
    suffix = f"_{sequence}" if sequence else ""
    events[0]["message"]["id"] += suffix
    events[1]["content_block"] = {
        "type": "tool_use",
        "id": f"toolu_offline_{name.lower()}{suffix}",
        "name": name,
        "input": {},
    }
    events[2]["delta"] = {
        "type": "input_json_delta",
        "partial_json": json.dumps(inputs or {"file_path": "fixture.txt", "old_string": "old", "new_string": "new"}),
    }
    events[4]["delta"]["stop_reason"] = "tool_use"
    return "".join(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events).encode()


def refusal_request() -> dict:
    request = payload()
    request["messages"] += [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_offline_edit",
                    "name": "Edit",
                    "input": {"file_path": "fixture.txt", "old_string": "old", "new_string": "new"},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_offline_edit",
                    "is_error": True,
                    "content": "<tool_use_error>Error: No such tool available: Edit. Edit is disabled for this session, in subagents as well as here.</tool_use_error>",
                }
            ],
        },
    ]
    return request


def native_events() -> list[dict]:
    messages = refusal_request()["messages"]
    return [
        {"type": "system", "subtype": "init", "tools": list(runner.DEFAULT_TOOLS), "model": MODEL, "mcp_servers": []},
        {"type": "assistant", "message": {"id": "msg_offline", "model": MODEL, **messages[-2]}},
        {"type": "user", "message": messages[-1]},
        {
            "type": "assistant",
            "is_api_error_message": True,
            "api_error_status": 400,
            "message": {"role": "assistant", "content": [{"type": "text", "text": tool_unavailable.API_ERROR}]},
        },
        {
            "type": "result",
            "subtype": "success",
            "is_error": True,
            "terminal_reason": "api_error",
            "api_error_status": 400,
            "result": tool_unavailable.API_ERROR,
            "stop_reason": "stop_sequence",
            "permission_denials": [],
            "safety_stops": 0,
            "num_turns": 2,
        },
    ]


def maximum_events() -> list[dict]:
    events = native_events()[:3]
    events[1]["message"]["content"][0]["name"] = "Read"
    events[2]["message"]["content"][0].update(is_error=False, content="old")
    events.append(
        {
            "type": "result",
            "subtype": "error_max_turns",
            "is_error": True,
            "num_turns": 9,
            "stop_reason": "tool_use",
            "terminal_reason": "max_turns",
            "result": "",
            "errors": ["Reached maximum number of turns (8)"],
            "safety_stops": 0,
            "permission_denials": [],
        }
    )
    return events


class RefusalLatchTest(unittest.TestCase):
    def test_validation_only_replacement_cannot_hide_an_oversized_original_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = gateway.Ledger(Path(directory) / "round.sqlite3", 25)
            backend = gateway_transport.Backend(ledger, lambda _: ("text/event-stream", edit_stream()))
            backend.respond(payload(), MODEL, runner.DEFAULT_TOOLS)
            request = refusal_request()
            size = len(json.dumps(request).encode())
            request["messages"][0]["content"] += "x" * (gateway.BODY_BYTES + 1 - size)
            self.assertEqual(len(json.dumps(request).encode()), gateway.BODY_BYTES + 1)
            with self.assertRaises(gateway.GatewayError):
                backend.respond(request, MODEL, runner.DEFAULT_TOOLS)
            self.assertTrue(ledger.snapshot()["stop_reason"])

    def test_missing_paid_response_in_native_history_cannot_certify_the_request_slice(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = gateway.Ledger(Path(directory) / "round.sqlite3", 25)
            responses = iter([stream_body().replace(b"msg_offline", b"msg_prior"), edit_stream()])
            backend = gateway_transport.Backend(ledger, lambda _: ("text/event-stream", next(responses)))
            backend.respond(payload(), MODEL, runner.DEFAULT_TOOLS)
            backend.respond(payload(), MODEL, runner.DEFAULT_TOOLS)
            with self.assertRaises(gateway.GatewayError):
                backend.respond(refusal_request(), MODEL, runner.DEFAULT_TOOLS)
            result = runner.Completed(1, "\n".join(map(json.dumps, native_events())), "")
            self.assertFalse(backend.certifies_tool_failure(result, runner.DEFAULT_TOOLS))

    def test_a_refused_session_cannot_forward_concurrent_or_later_requests(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = gateway.Ledger(Path(directory) / "round.sqlite3", 25)
            calls = []

            def provider(request: dict) -> tuple[str, bytes]:
                calls.append(request)
                return "text/event-stream", edit_stream()

            backend = gateway_transport.Backend(ledger, provider)
            backend.respond(payload(), MODEL, runner.DEFAULT_TOOLS)
            with self.assertRaises(gateway.GatewayError):
                backend.respond(refusal_request(), MODEL, runner.DEFAULT_TOOLS)

            def refused(_index: int) -> None:
                with self.assertRaises(gateway.GatewayError):
                    backend.respond(payload(), MODEL, runner.DEFAULT_TOOLS)

            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(refused, range(16)))
            self.assertEqual(len(calls), 1)
            self.assertEqual(ledger.snapshot()["stop_reason"], "")

    def test_other_invalid_policy_fields_still_stop_after_a_local_tool_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            changes = [
                {"service_tier": "priority"},
                {"speed": "fast"},
                {"model": "claude-sonnet-5"},
                {"max_tokens": True},
                {"cache_control": {"type": "ephemeral", "ttl": "unknown"}},
                {"context_management": {}},
                {"tools": []},
                {"unsupported_option": True},
            ]
            for index, change in enumerate(changes):
                with self.subTest(change=change):
                    ledger = gateway.Ledger(Path(directory) / f"round-{index}.sqlite3", 25)
                    backend = gateway_transport.Backend(ledger, lambda _: ("text/event-stream", edit_stream()))
                    backend.respond(payload(), MODEL, runner.DEFAULT_TOOLS)
                    before = ledger.spent()
                    with self.assertRaises(gateway.GatewayError):
                        backend.respond(refusal_request(), MODEL, runner.DEFAULT_TOOLS)
                    self.assertEqual(ledger.snapshot()["stop_reason"], "")
                    with self.assertRaises(gateway.GatewayError):
                        backend.respond(refusal_request() | change, MODEL, runner.DEFAULT_TOOLS)
                    self.assertTrue(ledger.snapshot()["stop_reason"])
                    self.assertEqual(ledger.spent(), before)
                    self.assertEqual(len(ledger.snapshot()["requests"]), 1)

    def test_an_unavailable_error_without_the_settled_model_source_still_stops(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = gateway.Ledger(Path(directory) / "round.sqlite3", 25)
            backend = gateway_transport.Backend(ledger, lambda _: self.fail("must not forward fabricated history"))
            with self.assertRaises(gateway.GatewayError):
                backend.respond(refusal_request(), MODEL, runner.DEFAULT_TOOLS)
            self.assertTrue(ledger.snapshot()["stop_reason"])


class UnavailableScoringTest(unittest.TestCase):
    def test_certified_api_error_text_is_not_an_answer_and_the_raw_transcript_remains_intact(self) -> None:
        raw = "\n".join(map(json.dumps, native_events()))
        result = runner.Completed(1, raw, "", bounded_failure=True)
        parsed = transcript.parse(raw)
        with tempfile.TemporaryDirectory() as directory:
            context = Path(directory)
            case = cases.load_corpus(testkit.CASES, testkit.domains())[0]
            row = scoring.score(
                case,
                parsed,
                testkit.domains(),
                context,
                run_id="offline",
                repeat=0,
                error=runner.session_error(result, runner.DEFAULT_TOOLS),
                root=str(context),
                bounded_failure=True,
            )
        self.assertEqual(row.answer, "")
        self.assertEqual(row.error, "tool_unavailable")
        self.assertTrue(row.bounded_failure)
        self.assertTrue(scoring.valid_trial(row))
        self.assertEqual(parsed.answer, tool_unavailable.API_ERROR)
        self.assertEqual(result.stdout, raw)

    def test_a_current_certified_unavailable_trial_contributes_a_distinct_zero(self) -> None:
        failed = record(1, "tool_unavailable", bounded=True)
        summary = scoring.summarise([record(0), failed])["all_trials"]
        self.assertTrue(summary["execution_valid"])
        self.assertEqual(summary["completion"], {"numerator": 1, "denominator": 2, "rate": 0.5, "ungraded_trials": 0})
        self.assertEqual(failed.error, "tool_unavailable")

    def test_uncertified_and_old_schema_unavailable_trials_remain_invalid(self) -> None:
        self.assertFalse(scoring.valid_trial(record(0, "tool_unavailable")))
        historical = record(0, "tool_unavailable", bounded=True)
        historical.version = 2
        self.assertFalse(scoring.valid_trial(historical))
        from records import SessionRecord

        restored = SessionRecord.from_dict(json.loads(historical.to_json()))
        self.assertEqual(restored.version, 2)
        self.assertFalse(scoring.valid_trial(restored))

    def test_historical_raw_validation_does_not_reclassify_unavailable_tool_failures(self) -> None:
        workspace = Path("/offline-workspace")
        checkout = workspace / ".worktrees" / "xberg" / "context-eval-offline"
        events = native_events()
        events[0]["cwd"] = str(checkout)
        raw = "\n".join(map(json.dumps, events))
        meta = {"root": str(checkout), "returncode": 1, "error": "tool_unavailable", "bounded_failure": True}
        case = SimpleNamespace(repo="xberg", cwd=".")
        identity = {"config": {"model": MODEL, "max_turns": 8}}
        with self.assertRaises(continuation.ContinuationError):
            continuation.validate_raw(raw, meta, case, identity, workspace)
        self.assertEqual(
            continuation.validate_raw(raw, meta, case, identity, workspace, allow_tool_unavailable=True),
            "certified-tool-unavailable",
        )
        with self.assertRaises(continuation.ContinuationError):
            continuation.validate_raw(
                raw, meta | {"bounded_failure": False}, case, identity, workspace, allow_tool_unavailable=True
            )


class RescoreProofTest(unittest.TestCase):
    def test_ordinary_success_binds_the_requested_model_empty_mcp_and_canonical_agent_tools(self) -> None:
        metadata = {"error": "", "returncode": 0, "bounded_failure": False}
        for version in ("5", harness.HARNESS_VERSION):
            success = maximum_events()
            success[-1] = {"type": "result", "subtype": "success", "is_error": False, "result": "fixture answer"}
            run = {"harness_version": version}
            self.assertTrue(scoring.valid_trial(self.score(success, stored=metadata, run=run)))
            generic = copy.deepcopy(success)
            generic[0]["model"] = generic[1]["message"]["model"] = "offline-generic-model"
            self.assertTrue(
                scoring.valid_trial(self.score(generic, stored=metadata, run=run | {"model": "offline-generic-model"}))
            )
            wrong_model = copy.deepcopy(success)
            wrong_model[0]["model"] = "claude-sonnet-5"
            wrong_mcp = copy.deepcopy(success)
            wrong_mcp[0]["mcp_servers"] = [{"name": "unexpected"}]
            wrong_tools = copy.deepcopy(success)
            wrong_tools[0]["tools"] = ["Bash"]
            wrong_tools[1]["message"]["content"][0]["name"] = "Bash"
            for broken, declaration in (
                (wrong_model, run),
                (wrong_mcp, run),
                (wrong_tools, run | {"allowed_tools": ["Bash"]}),
                ([success[0], *success], run),
            ):
                with self.subTest(version=version, declaration=declaration):
                    self.assertFalse(scoring.valid_trial(self.score(broken, stored=metadata, run=declaration)))

    def test_known_historical_profiles_preserve_genuine_maximum_failures_and_reject_drift(self) -> None:
        for version in ("5", harness.HARNESS_VERSION):
            for error in ("", "error_max_turns"):
                self.assertTrue(
                    scoring.valid_trial(
                        self.score(
                            maximum_events(), stored={"error": error}, run={"max_turns": 8, "harness_version": version}
                        )
                    )
                )
            success = maximum_events()
            success[-1] = {"type": "result", "subtype": "success", "is_error": False, "result": "fixture answer"}
            metadata = {"error": "", "returncode": 0, "bounded_failure": False}
            self.assertTrue(scoring.valid_trial(self.score(success, stored=metadata, run={"harness_version": version})))
            success[0]["tools"] = ["Bash"]
            success[1]["message"]["content"][0]["name"] = "Bash"
            self.assertFalse(
                scoring.valid_trial(self.score(success, stored=metadata, run={"harness_version": version}))
            )

    def test_maximum_turn_zero_requires_typed_metadata_and_the_declared_turn_budget(self) -> None:
        for change in (
            {"returncode": True},
            {"returncode": 0},
            {"bounded_failure": 1},
            {"bounded_failure": False},
            {"stderr": []},
            {"error": "timeout"},
        ):
            with self.subTest(stored=change):
                self.assertFalse(
                    scoring.valid_trial(
                        self.score(maximum_events(), stored={"error": "error_max_turns"} | change, run={"max_turns": 8})
                    )
                )
        for change in (
            {},
            {"max_turns": None},
            {"max_turns": 0},
            {"max_turns": True},
            {"max_turns": 7},
            {"max_turns": 9},
            {"max_turns": "8"},
            {"max_turns": 8, "harness_version": "unknown"},
        ):
            with self.subTest(run=change):
                self.assertFalse(
                    scoring.valid_trial(self.score(maximum_events(), stored={"error": "error_max_turns"}, run=change))
                )

    def test_maximum_turn_zero_rejects_unknown_terminals_permissions_and_tool_profiles(self) -> None:
        for terminal in (
            {"subtype": "unknown-error"},
            {"num_turns": 8},
            {"permission_denials": ["Read"]},
            {"errors": ["unknown error"]},
            {"terminal_reason": "unknown"},
        ):
            broken = maximum_events()
            broken[-1].update(terminal)
            self.assertFalse(
                scoring.valid_trial(self.score(broken, stored={"error": "error_max_turns"}, run={"max_turns": 8}))
            )
        broken = maximum_events()
        broken[1]["message"]["content"][0]["name"] = "Bash"
        broken[-1]["subtype"] = "unknown-error"
        for version in ("5", harness.HARNESS_VERSION):
            self.assertFalse(
                scoring.valid_trial(
                    self.score(
                        broken, stored={"error": "error_max_turns"}, run={"max_turns": 8, "harness_version": version}
                    )
                )
            )

    @staticmethod
    def native_mutants() -> list[list[dict]]:
        mutants = [native_events()[:-1], native_events() + [native_events()[-1]]]
        for location, key, value in ((1, "name", "Bash"), (2, "content", "permission denied")):
            broken = native_events()
            broken[location]["message"]["content"][0][key] = value
            mutants.append(broken)
        broken = native_events()
        broken[0]["model"] = broken[1]["message"]["model"] = "claude-sonnet-5"
        mutants.append(broken)
        broken = native_events()
        broken[0]["mcp_servers"] = [{"name": "unexpected"}]
        mutants.append(broken)
        broken = native_events()
        broken[1]["message"]["content"] = [{"type": "text", "text": json.dumps(broken[1]["message"]["content"])}]
        mutants.append(broken)
        return mutants

    def score(self, events: list[dict], stored: dict | None = None, run: dict | None = None):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            testkit.make_checkout(out / "context")
            (out / "transcripts").mkdir()
            case = cases.load_corpus(testkit.CASES, testkit.domains())[0]
            name = runner.session_name(case.id, 0)
            (out / "transcripts" / f"{name}.jsonl").write_text("\n".join(map(json.dumps, events)))
            info = runner.SessionMeta(
                case.id, 0, str(out / "context"), 1, 0, error="tool_unavailable", bounded_failure=True
            )
            (out / "transcripts" / f"{name}.meta.json").write_text(json.dumps(asdict(info) | (stored or {})))
            meta = {
                "run_id": "offline",
                "repo": case.repo,
                "model": MODEL,
                "allowed_tools": list(runner.DEFAULT_TOOLS),
                "harness_version": harness.HARNESS_VERSION,
            } | (run or {})
            return harness.score_trial(out, case, 0, meta, testkit.domains(), None)

    def test_rescoring_revalidates_the_native_certificate_instead_of_trusting_stored_error(self) -> None:
        self.assertTrue(scoring.valid_trial(self.score(native_events())))
        for change in (
            {"returncode": True},
            {"returncode": 0},
            {"returncode": -1},
            {"bounded_failure": 1},
            {"bounded_failure": "true"},
            {"bounded_failure": False},
            {"stderr": []},
            {"error": "timeout"},
        ):
            with self.subTest(stored=change):
                self.assertFalse(scoring.valid_trial(self.score(native_events(), stored=change)))
        for change in (
            {"harness_version": "5"},
            {"harness_version": "unknown"},
            {"harness_version": None},
            {"allowed_tools": ["Read", "Bash"]},
            {"model": "claude-sonnet-5"},
        ):
            with self.subTest(run=change):
                self.assertFalse(scoring.valid_trial(self.score(native_events(), run=change)))
        for broken in self.native_mutants():
            self.assertFalse(scoring.valid_trial(self.score(broken)))
        with self.assertRaises(TypeError):
            self.score(native_events(), stored={"timed_out": True})


class EvidenceTest(unittest.TestCase):
    def test_native_failure_requires_every_exact_boundary_and_not_permission_or_unknown_errors(self) -> None:
        valid = native_events()

        def render(value: list[dict]) -> str:
            return "\n".join(map(json.dumps, value))

        self.assertIsNotNone(tool_unavailable.native_evidence(render(valid), runner.DEFAULT_TOOLS))
        changes = [
            (0, {"tools": ["Bash"]}),
            (4, {"permission_denials": ["Edit"]}),
            (4, {"safety_stops": 1}),
            (4, {"api_error_status": True}),
            (4, {"terminal_reason": "unknown"}),
            (4, {"result": "permission denied"}),
            (4, {"errors": ["unknown condition"]}),
            (4, {"unexpected_failure": True}),
            (4, {"num_turns": True}),
            (3, {"is_api_error_message": False}),
        ]
        for index, fields in changes:
            broken = copy.deepcopy(valid)
            broken[index].update(fields)
            with self.subTest(index=index, fields=fields):
                self.assertIsNone(tool_unavailable.native_evidence(render(broken), runner.DEFAULT_TOOLS))
        for mutation in (valid[:-1], [*valid, valid[-1]], [*valid[:3], valid[2], *valid[3:]]):
            self.assertIsNone(tool_unavailable.native_evidence(render(mutation), runner.DEFAULT_TOOLS))
        wrong_model = copy.deepcopy(valid)
        wrong_model[1]["message"]["model"] = "unknown-model"
        self.assertIsNone(tool_unavailable.native_evidence(render(wrong_model), runner.DEFAULT_TOOLS))

    def test_only_the_matched_settled_response_can_explain_rejected_history(self) -> None:
        sources = tool_unavailable.response_sources("text/event-stream", edit_stream())
        self.assertEqual(len(sources), 1)
        result = tool_unavailable.request_refusal(refusal_request(), runner.DEFAULT_TOOLS, sources)
        self.assertIsNotNone(result)
        item, clean = result
        self.assertEqual(item.message_id, "msg_offline")
        gateway.Policy().prepare(clean, runner.DEFAULT_TOOLS)
        self.assertIsNone(tool_unavailable.request_refusal(refusal_request(), runner.DEFAULT_TOOLS, []))
        for change in ("tool_use_id", "is_error", "content"):
            broken = copy.deepcopy(refusal_request())
            broken["messages"][-1]["content"][0][change] = "not the native result"
            with self.subTest(field=change):
                self.assertIsNone(tool_unavailable.request_refusal(broken, runner.DEFAULT_TOOLS, sources))

    def test_tool_json_inside_model_text_is_not_native_evidence(self) -> None:
        events = native_events()
        self.assertIsNotNone(tool_unavailable.native_evidence("\n".join(map(json.dumps, events)), runner.DEFAULT_TOOLS))
        text = json.dumps(events[1]["message"]["content"])
        events[1]["message"]["content"] = [{"type": "text", "text": text}]
        self.assertIsNone(tool_unavailable.native_evidence("\n".join(map(json.dumps, events)), runner.DEFAULT_TOOLS))


class HistoricalInventoryTest(unittest.TestCase):
    def test_a_new_controller_cannot_claim_an_old_inventory_that_omits_its_new_dependency(self) -> None:
        import hashlib

        source = Path(gateway.__file__).read_bytes()
        inventory = gateway.manifest()["source_files"][:-1]
        forged = gateway.manifest() | {
            "protocol": "hard-gateway-4",
            "source_files": inventory,
            "source_sha256": hashlib.sha256(source + b"offline" * (len(inventory) - 1)).hexdigest(),
        }

        def git_source(argv: list[str], **_options: object) -> bytes:
            return source if argv[-1].endswith("/gateway.py") else b"offline"

        with (
            patch("subprocess.check_output", side_effect=git_source),
            self.assertRaises(continuation.ContinuationError),
        ):
            continuation.verify_historical_source("f" * 40, forged)


@unittest.skipUnless(sys.platform == "darwin", "macOS native CLI boundary")
class ActualUnavailableToolTest(unittest.TestCase):
    def test_native_edit_rejection_is_a_finite_task_failure_without_another_upstream_call(self) -> None:
        self.run_native_case(0)

    def test_four_prior_settled_native_reads_and_edit_rejection_retain_the_exact_five_call_slice(self) -> None:
        self.run_native_case(4)

    def run_native_case(self, prior_reads: int) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "fixture.txt").write_text("old")
            (root / "mcp.json").write_text('{"mcpServers":{}}')
            ledger = gateway.Ledger(root / "offline.sqlite3", 25)
            calls = []

            def provider(request: dict) -> tuple[str, bytes]:
                calls.append(request)
                if len(calls) <= prior_reads:
                    return "text/event-stream", edit_stream(
                        "Read", {"file_path": str(root / "fixture.txt")}, len(calls)
                    )
                return "text/event-stream", edit_stream(sequence=len(calls) if prior_reads else 0)

            execute = gateway_transport.HardExecute(ledger, "OFFLINE_NEVER_FORWARDED", provider=provider)
            argv = runner.ClaudeAdapter().command(
                runner.SessionSpec(
                    "Read fixture.txt; do not modify it.", MODEL, 8, root / "mcp.json", runner.DEFAULT_TOOLS
                )
            )
            result = execute(argv, root, {"PATH": os.environ["PATH"]}, 30)
            artifact = os.environ.get("CONTEXT_EVAL_OFFLINE_ARTIFACT_DIR")
            if artifact:
                target = Path(artifact)
                target.mkdir(parents=True, exist_ok=True)
                (target / f"native-edit-{prior_reads}.jsonl").write_text(result.stdout)
                (target / f"native-edit-{prior_reads}.stderr").write_text(result.stderr)
            self.assertEqual(len(calls), prior_reads + 1)
            self.assertEqual((root / "fixture.txt").read_text(), "old")
            self.assertEqual(ledger.snapshot()["stop_reason"], "")
            self.assertEqual(result.returncode, 1)
            self.assertTrue(result.bounded_failure)
            self.assertEqual(runner.session_error(result, runner.DEFAULT_TOOLS), "tool_unavailable")
            self.assertEqual(len(ledger.snapshot()["requests"]), prior_reads + 1)
            self.assertTrue(all(row["state"] == "settled" for row in ledger.snapshot()["requests"]))


if __name__ == "__main__":
    unittest.main()
