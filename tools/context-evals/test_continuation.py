"""Reviewed continuation preserves every prior trial and executes only the exact remainder."""

import copy
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing, contextmanager
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

import cases
import continuation
import gateway
import gateway_epochs
import harness
import records
import runner
import scoring
import testkit
from test_runner import git


def session(repo: str, case_id: str, repeat: int, prior: bool = False) -> dict:
    return {
        "repo": repo,
        "case_id": case_id,
        "repeat": repeat,
        "source": {"raw_sha256": "a" * 64, "meta_sha256": "b" * 64, "adjudication": None, "request_ids": [1]}
        if prior
        else None,
    }


class SessionPlanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.expected = {("xberg", "first", 0), ("xberg", "first", 1), ("sceptre", "second", 0)}
        self.prior = {("xberg", "first", 0)}
        self.plan = [session(*key, key in self.prior) for key in sorted(self.expected)]

    def test_exact_disjoint_plan_references_all_prior_trials(self) -> None:
        rows = continuation.validate_session_plan(self.plan, self.expected, self.prior)
        self.assertEqual(set(rows), self.expected)
        self.assertEqual(sum(row["source"] is not None for row in rows.values()), 1)

    def test_duplicate_missing_or_unplanned_tuple_is_rejected(self) -> None:
        for plan in [self.plan + [self.plan[0]], self.plan[:-1], self.plan + [session("xberg", "other", 0)]]:
            with self.subTest(plan=plan), self.assertRaises(continuation.ContinuationError):
                continuation.validate_session_plan(plan, self.expected, self.prior)

    def test_prior_trial_cannot_be_dropped_or_scheduled_for_rerun(self) -> None:
        changed = copy.deepcopy(self.plan)
        next(row for row in changed if row["source"] is not None)["source"] = None
        with self.assertRaises(continuation.ContinuationError):
            continuation.validate_session_plan(changed, self.expected, self.prior)

    def test_unknown_keys_boolean_repeat_and_untyped_source_are_rejected(self) -> None:
        changes = [{"repeat": True}, {"repeat": -1}, {"unknown": 1}, {"source": {}}, {"repo": 1}]
        for change in changes:
            changed = copy.deepcopy(self.plan)
            changed[0].update(change)
            with self.subTest(change=change), self.assertRaises(continuation.ContinuationError):
                continuation.validate_session_plan(changed, self.expected, self.prior)

    def test_actual_study_dimensions_keep_fourteen_prior_and_one_hundred_seventy_two_new_trials(self) -> None:
        expected = {
            (repo, f"case-{case}", repeat)
            for repo, count in [("xberg", 46), ("sceptre", 16)]
            for case in range(count)
            for repeat in range(3)
        }
        prior = set(sorted(key for key in expected if key[0] == "xberg")[:14])
        rows = continuation.validate_session_plan(
            [session(*key, key in prior) for key in sorted(expected)], expected, prior
        )
        self.assertEqual(len(rows), 186)
        self.assertEqual(sum(row["source"] is not None for row in rows.values()), 14)
        self.assertEqual(sum(key[0] == "xberg" and row["source"] is None for key, row in rows.items()), 124)
        self.assertEqual(sum(key[0] == "sceptre" and row["source"] is None for key, row in rows.items()), 48)


class FinancialAdmissionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name).resolve() / "round.sqlite3"
        self.ledger = gateway.Ledger(self.path, 25)
        request = self.ledger.reserve("claude-sonnet-5-5", 4096)
        self.ledger.settle(request, 1000)
        self.ledger.stop("known collection stop")
        snapshot = self.ledger.snapshot()
        previous = snapshot["admission_epoch"]
        self.future = gateway.manifest() | {"source_sha256": "e" * 64}
        self.plan = {
            "round": self.ledger.identity(),
            "previous_admission": previous,
            "next_admission": {"epoch": previous["epoch"] + 1, "policy_sha256": gateway_epochs.digest(self.future)},
            "previous_manifest": gateway.manifest(),
            "next_manifest": self.future,
            "prior_requests_sha256": continuation.ledger_state(self.path)["requests_sha256"],
            "reviewed_ref": "f" * 40,
        }

    def check(self, *, before: bool) -> dict:
        with patch("gateway.manifest", return_value=self.future):
            return continuation.validate_financial(self.plan, self.path, before_recovery=before)

    def migrate(self) -> None:
        approval = {
            "reviewed_ref": "f" * 40,
            "round": self.plan["round"],
            "previous_policy": gateway_epochs.digest(self.plan["previous_manifest"]),
            "next_policy": gateway_epochs.digest(self.future),
            "reason": "protocol-compatibility-recovery",
            "previous_admission": {key: self.plan["previous_admission"][key] for key in ("epoch", "audit_hash")},
        }
        gateway_epochs.recover(
            self.path, self.plan["round"], self.plan["previous_manifest"], self.future, approval, gateway.GatewayError
        )

    def test_readonly_draft_validation_requires_stopped_prior_epoch_and_preserves_bytes(self) -> None:
        before = self.path.read_bytes()
        state = self.check(before=True)
        self.assertEqual(state["round"], self.ledger.identity())
        self.assertEqual(self.path.read_bytes(), before)
        with self.assertRaises(continuation.ContinuationError):
            self.check(before=False)

    def test_execution_requires_the_exact_reviewed_next_epoch(self) -> None:
        self.migrate()
        self.check(before=False)
        with self.assertRaises(continuation.ContinuationError):
            self.check(before=True)

    def test_rehashed_but_unapproved_transition_cannot_authorize_continuation(self) -> None:
        self.migrate()
        with closing(sqlite3.connect(self.path)) as db, db:
            epoch, text = db.execute("SELECT epoch,record FROM hard_epochs ORDER BY epoch DESC LIMIT 1").fetchone()
            changed = json.loads(text)
            changed["approval"]["reason"] = "unreviewed"
            db.execute("DROP TRIGGER hard_epochs_update")
            db.execute(
                "UPDATE hard_epochs SET record=?,audit_hash=? WHERE epoch=?",
                (json.dumps(changed, sort_keys=True), gateway_epochs.digest(changed), epoch),
            )
        with self.assertRaises(continuation.ContinuationError):
            self.check(before=False)

    def test_changed_identity_epoch_hash_bounds_or_prior_rows_are_rejected(self) -> None:
        variants = [
            ("round", self.plan["round"] | {"uuid": "wrong"}),
            ("previous_admission", self.plan["previous_admission"] | {"audit_hash": "0" * 64}),
            ("next_admission", self.plan["next_admission"] | {"epoch": True}),
            ("prior_requests_sha256", "0" * 64),
            ("next_manifest", self.future | {"max_output_tokens": 8192}),
        ]
        for key, value in variants:
            original = self.plan[key]
            self.plan[key] = value
            with self.subTest(key=key), self.assertRaises(continuation.ContinuationError):
                self.check(before=True)
            self.plan[key] = original


class PriorFixture:
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / "reports" / "round" / "epoch1" / "xberg"
        (self.source / "transcripts").mkdir(parents=True)
        self.case = cases.select(cases.load_corpus(testkit.CASES, testkit.domains()), split="tune")[0]
        self.identity = {
            "tool_profile_version": runner.TOOL_PROFILE_VERSION,
            "context_sha256": "a" * 64,
            "agent_sha256": "b" * 64,
            "generator_sha256": "c" * 64,
            "config": {
                "model": "claude-sonnet-5-5",
                "max_turns": 8,
                "timeout": 180.0,
                "repeats": 3,
                "allowed_tools": list(runner.DEFAULT_TOOLS),
                "generate": True,
            },
        }
        self.meta = {
            "repo": "xberg",
            "commit": "d" * 40,
            "model": "claude-sonnet-5-5",
            "split": "tune",
            "repeats": 3,
            "max_turns": 8,
            "timeout": 180.0,
            "cases": [self.case.id],
            "jobs": 1,
            "case_corpus_hash": cases.corpus_hash([self.case]),
            "harness_version": "5",
            "allowed_tools": list(runner.DEFAULT_TOOLS),
            "tool_profile_version": runner.TOOL_PROFILE_VERSION,
        }
        for repeat in range(2):
            self.write_trial(repeat, failed=repeat == 1)
        self.write_json("run.json", self.meta)
        self.write_json("cases.json", [asdict(self.case)])
        self.write_json("context-identity.json", self.identity)
        self.hashes = {
            name: continuation.file_hash(self.source / name)
            for name in ("run.json", "cases.json", "context-identity.json")
        }

    def write_json(self, name, value) -> None:
        (self.source / name).write_text(json.dumps(value))

    def write_trial(self, repeat, *, failed=False) -> None:
        worktree = self.root / ".worktrees" / "xberg" / "context-eval-fixture"
        init = {
            "type": "system",
            "subtype": "init",
            "model": "claude-sonnet-5-5",
            "tools": list(runner.DEFAULT_TOOLS),
            "mcp_servers": [],
            "cwd": str(worktree / self.case.cwd),
        }
        terminal = {
            "type": "result",
            "subtype": "error_max_turns" if failed else "success",
            "is_error": failed,
            "num_turns": 9 if failed else 1,
            "stop_reason": "tool_use" if failed else "end_turn",
            "terminal_reason": "max_turns" if failed else "success",
            "result": "" if failed else "fixture",
            "errors": ["Reached maximum number of turns (8)"] if failed else [],
            "safety_stops": 0,
            "permission_denials": [],
        }
        path = self.source / "transcripts" / runner.session_name(self.case.id, repeat)
        path.with_suffix(path.suffix + ".jsonl").write_text("\n".join(map(json.dumps, [init, terminal])) + "\n")
        path.with_suffix(path.suffix + ".meta.json").write_text(
            json.dumps(
                {
                    "case_id": self.case.id,
                    "repeat": repeat,
                    "root": str(worktree),
                    "returncode": 1 if failed else 0,
                    "seconds": 1.0,
                    "error": "",
                    "stderr": "",
                }
            )
        )


class PriorSourceTest(PriorFixture, unittest.TestCase):
    def validate(self):
        return continuation.validate_prior_run(
            self.source, self.hashes, [self.case], "d" * 40, self.identity, workspace=self.root
        )

    def test_all_original_rows_are_retained_and_only_known_bounded_failure_is_adjudicated(self) -> None:
        before = {path: path.read_bytes() for path in self.source.rglob("*") if path.is_file()}
        rows = self.validate()
        self.assertEqual(len(rows), 2)
        self.assertEqual(sum(row["source"]["adjudication"] == "certified-max-turns" for row in rows.values()), 1)
        self.assertEqual({path: path.read_bytes() for path in before}, before)

    def test_original_run_or_raw_drift_and_missing_metadata_are_rejected(self) -> None:
        (self.source / "run.json").write_text("{}")
        with self.assertRaises(continuation.ContinuationError):
            self.validate()

    def test_unrecognized_failure_cannot_be_adjudicated_as_a_bounded_model_miss(self) -> None:
        path = self.source / "transcripts" / f"{runner.session_name(self.case.id, 1)}.jsonl"
        path.write_text(path.read_text().replace("error_max_turns", "unknown_failure"))
        with self.assertRaises(continuation.ContinuationError):
            self.validate()

    def test_unmapped_worktree_path_and_wrong_init_model_are_rejected(self) -> None:
        path = self.source / "transcripts" / f"{runner.session_name(self.case.id, 0)}.jsonl"
        path.write_text(path.read_text().replace("claude-sonnet-5-5", "claude-sonnet-5"))
        with self.assertRaises(continuation.ContinuationError):
            self.validate()


class RequestAttributionTest(unittest.TestCase):
    def test_response_count_maps_exact_settled_request_slices_without_rewriting_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected = cases.load_corpus(testkit.CASES, testkit.domains())[:1]
            prior = {}
            before = {}
            for repeat, count in [(0, 2), (1, 1)]:
                path = root / f"trial-{repeat}.jsonl"
                path.write_text(
                    "\n".join(
                        json.dumps({"type": "assistant", "message": {"id": f"msg-{repeat}-{i}"}}) for i in range(count)
                    )
                )
                prior[(selected[0].repo, selected[0].id, repeat)] = {"raw_path": path}
                before[path] = path.read_bytes()
            rows = [(i, "claude-sonnet-5-5", 4096, 1000, "settled", 0, "fixture", 1, "same-actor") for i in range(2, 5)]
            continuation.bind_prior_requests(prior, selected, 3, {"requests": rows}, 1)
            self.assertEqual([row["request_ids"] for row in prior.values()], [[2, 3], [4]])
            self.assertEqual({path: path.read_bytes() for path in before}, before)
            with self.assertRaises(continuation.ContinuationError):
                continuation.bind_prior_requests(prior, selected, 3, {"requests": rows[:-1]}, 1)
            with self.assertRaises(continuation.ContinuationError):
                continuation.bind_prior_requests(prior, selected, 3, {"requests": rows + [rows[-1]]}, 1)


class ManifestFixture(PriorFixture):
    def setUp(self) -> None:
        super().setUp()
        self.ledger_path = self.root / "reports" / "round" / "paid-round.sqlite3"
        self.ledger = gateway.Ledger(self.ledger_path, 25)
        for repeat in range(2):
            request = self.ledger.reserve("claude-sonnet-5-5", 4096)
            self.ledger.settle(request, 1000)
            path = self.source / "transcripts" / f"{runner.session_name(self.case.id, repeat)}.jsonl"
            events = [json.loads(line) for line in path.read_text().splitlines()]
            events.insert(1, {"type": "assistant", "message": {"id": f"msg-{repeat}", "content": []}})
            path.write_text("\n".join(map(json.dumps, events)) + "\n")
        self.ledger.stop("known collection stop")
        self.previous = gateway.manifest()
        self.future = self.previous | {"source_sha256": "e" * 64}
        self.meta.update(
            execution_policy={
                "mode": "hard-gateway",
                "policy": self.previous,
                "policy_sha256": gateway_epochs.digest(self.previous),
            },
            budget_round=self.ledger.identity(),
        )
        self.write_json("run.json", self.meta)
        self.hashes["run.json"] = continuation.file_hash(self.source / "run.json")
        self.sceptre = replace(self.case, id="sceptre-fixture", repo="sceptre")
        self.corpus = [self.case, self.sceptre]
        self.preflight = self.ledger_path.parent / "preflight.json"
        self.create_preflight()
        self.mock_proof = {
            "version": 1,
            "previous_ref": "d" * 40,
            "reviewed_ref": "f" * 40,
            "symbols": {"fixture": "a" * 64},
        }
        for target, value in [
            ("gateway.manifest", self.future),
            ("gateway.verify_reviewed_source", None),
            ("continuation_compat.proof", self.mock_proof),
        ]:
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def create_preflight(self) -> None:
        preflight = {
            "controller_commit": "d" * 40,
            "policy": self.previous,
            "refs": {"xberg": "d" * 40, "sceptre": "e" * 40},
            "repeats": 3,
            "max_turns": 8,
            "timeout_seconds": 180,
            "jobs": 1,
            "models": list(gateway.MODELS),
            "tools": {"claude_sha256": "b" * 64, "ai_rulez_sha256": "c" * 64},
            "checks": {},
        }
        for case, context in [(self.case, "a" * 64), (self.sceptre, "d" * 64)]:
            preflight["checks"][case.repo] = {
                "case_corpus_hash": cases.corpus_hash([case]),
                "context_sha256": context,
                "expected_sessions": 3,
                "tune_cases": 1,
            }
        self.preflight.write_text(json.dumps(preflight))

    def draft(self):
        return continuation.make_draft(
            self.preflight, {"xberg": self.source}, self.ledger_path, "f" * 40, self.corpus, workspace=self.root
        )

    def load(self, value=None, expected_hash=None):
        value = self.draft() if value is None else value
        path = self.ledger_path.parent / "continuation.json"
        path.write_text(json.dumps(value))
        return continuation.Plan.load(
            path,
            expected_hash or continuation.file_hash(path),
            self.corpus,
            self.ledger_path,
            before_recovery=True,
            workspace=self.root,
        )


class ManifestTest(ManifestFixture, unittest.TestCase):
    def test_manifest_keeps_every_original_and_only_schedules_the_exact_remainder(self) -> None:
        plan = self.load()
        self.assertEqual(len(plan.sessions), 6)
        self.assertEqual(len(plan.prior), 2)
        self.assertEqual(len(plan.data["adjudications"]), 1)
        self.assertEqual(sum(row["source"] is None for row in plan.sessions.values()), 4)
        self.assertEqual([row["request_ids"] for row in plan.prior.values()], [[1], [2]])

    def test_manifest_hash_unknown_keys_and_missing_coverage_fail_closed(self) -> None:
        with self.assertRaises(continuation.ContinuationError):
            self.load(expected_hash="0" * 64)
        for transform in [lambda p: p.update(unknown=True), lambda p: p["sessions"].pop()]:
            value = self.draft()
            transform(value)
            with self.assertRaises(continuation.ContinuationError):
                self.load(value)

    def test_raw_drift_cannot_be_reapproved_by_rehashing_only_the_outer_manifest(self) -> None:
        value = self.draft()
        path = self.source / "transcripts" / f"{runner.session_name(self.case.id, 0)}.jsonl"
        events = [json.loads(line) for line in path.read_text().splitlines()]
        events[-1]["result"] = "different answer"
        path.write_text("\n".join(map(json.dumps, events)) + "\n")
        with self.assertRaises(continuation.ContinuationError):
            self.load(value)

    def test_adjudication_or_context_compatibility_claim_cannot_be_forged(self) -> None:
        for key in ["adjudications", "compatibility"]:
            value = self.draft()
            value[key] = [] if key == "adjudications" else {}
            with self.subTest(key=key), self.assertRaises(continuation.ContinuationError):
                self.load(value)


class RuntimePlanTest(ManifestFixture, unittest.TestCase):
    def advance(self, plan) -> None:
        approval = {
            "reviewed_ref": plan.data["reviewed_ref"],
            "round": plan.data["round"],
            "previous_policy": gateway_epochs.digest(plan.data["previous_manifest"]),
            "next_policy": gateway_epochs.digest(plan.data["next_manifest"]),
            "previous_admission": {key: plan.data["previous_admission"][key] for key in ("epoch", "audit_hash")},
            "reason": "protocol-compatibility-recovery",
        }
        gateway_epochs.recover(
            self.ledger_path,
            plan.data["round"],
            plan.data["previous_manifest"],
            plan.data["next_manifest"],
            approval,
            gateway.GatewayError,
        )

    def test_inherited_resolution_preserves_raw_and_metadata_and_adds_only_derived_provenance(self) -> None:
        plan = self.load()
        before = {path: path.read_bytes() for path in self.source.rglob("*") if path.is_file()}
        inherited = plan.inherited("xberg")
        self.assertEqual(len(inherited), 2)
        self.assertTrue(inherited[(self.case.id, 1)].bounded_failure)
        path, info, provenance = plan.resolve("xberg", self.case.id, 1, self.source.parent / "new")
        self.assertTrue(path.is_relative_to(self.source))
        self.assertEqual(info.returncode, 1)
        self.assertTrue(info.bounded_failure)
        self.assertEqual(provenance["epoch"], plan.data["previous_admission"]["epoch"])
        self.assertEqual(provenance["policy_sha256"], plan.data["previous_admission"]["policy_sha256"])
        self.assertEqual(provenance["request_ids"], [2])
        self.assertEqual(len(provenance["adjudication_sha256"]), 64)
        self.assertEqual({path: path.read_bytes() for path in before}, before)

    def test_fresh_context_mismatch_refuses_before_the_inner_executor(self) -> None:
        from types import SimpleNamespace

        plan = self.load()
        self.advance(plan)
        out = self.ledger_path.parent / "epoch2" / "xberg"
        out.mkdir(parents=True)
        (out / "context-identity.json").write_text("{}")
        calls = []
        inner = SimpleNamespace(ledger=gateway.Ledger(self.ledger_path, 25))
        wrapped = plan.wrap(inner, out, "xberg")
        with self.assertRaisesRegex(continuation.ContinuationError, "context identity"):
            wrapped(["claude"], self.root, {}, 180)
        self.assertEqual(inner.ledger.spent(), 2000)
        self.assertTrue(inner.ledger.snapshot()["stop_reason"])
        self.assertEqual(calls, [])

    def test_reviewed_command_forwards_unchanged_and_captures_only_its_owned_requests(self) -> None:
        plan = self.load()
        self.advance(plan)
        out = self.ledger_path.parent / "epoch2" / "xberg"
        out.mkdir(parents=True)
        (out / "context-identity.json").write_text(json.dumps(self.identity))
        calls = []

        class Inner:
            ledger = gateway.Ledger(self.ledger_path, 25)

            def __call__(self, argv, cwd, environment, timeout):
                calls.append((argv, cwd, environment, timeout))
                request = self.ledger.reserve("claude-sonnet-5-5", 4096)
                self.ledger.settle(request, 1000)
                return runner.Completed(0, "offline fixture", "")

        inner = Inner()
        wrapped = plan.wrap(inner, out, "xberg")
        cwd = self.root / ".worktrees" / "xberg" / "context-eval-fresh" / self.case.cwd
        cwd.mkdir(parents=True)
        with tempfile.TemporaryDirectory(prefix="ctx-home-") as directory:
            home = Path(directory)
            mcp = home / "mcp.json"
            mcp.write_text('{"mcpServers":{}}')
            argv = runner.ClaudeAdapter().command(
                runner.SessionSpec(self.case.prompt, "claude-sonnet-5-5", 8, mcp, runner.DEFAULT_TOOLS)
            )
            env = runner.ClaudeAdapter().env(home, {"ANTHROPIC_API_KEY": "OFFLINE_UNUSED"})
            result = wrapped(argv, cwd, env, 180)
            changed = argv.copy()
            changed[changed.index("--model") + 1] = "claude-sonnet-5"
            with self.assertRaisesRegex(continuation.ContinuationError, "model, prompt"):
                wrapped(changed, cwd, env, 180)
            self.assertEqual(len(calls), 1)
            self.assertTrue(inner.ledger.snapshot()["stop_reason"])
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0][0], argv)
        self.assertIs(calls[0][2], env)
        self.assertEqual(result.collection["request_ids"], [3])
        self.assertEqual(result.collection["epoch"], plan.data["next_admission"]["epoch"])
        self.assertEqual(inner.ledger.spent(), 3000)


class FakeCollector:
    def __init__(self, ledger_path: Path, calls: list) -> None:
        self.ledger = gateway.Ledger(ledger_path, 25)
        self.calls = calls

    def __call__(self, argv, cwd, environment, timeout):
        if argv[0] != "claude":
            return runner.Completed(0, "", "")
        self.calls.append(argv[2])
        request = self.ledger.reserve("claude-sonnet-5-5", 4096)
        self.ledger.settle(request, 1000)
        init = {
            "type": "system",
            "subtype": "init",
            "model": "claude-sonnet-5-5",
            "tools": list(runner.DEFAULT_TOOLS),
            "mcp_servers": [],
            "cwd": str(cwd),
        }
        answer = {"type": "assistant", "message": {"id": f"msg-new-{len(self.calls)}", "content": []}}
        result = {"type": "result", "subtype": "success", "is_error": False, "result": "fixture answer", "num_turns": 1}
        return runner.Completed(0, "\n".join(map(json.dumps, [init, answer, result])) + "\n", "")


class CollectionFixture(ManifestFixture):
    def prepare_collection(self) -> None:
        self.checkouts = {}
        for name in ("xberg", "sceptre"):
            checkout = testkit.make_checkout(self.root / ".worktrees" / name / "context-eval-fresh")
            git(checkout, "init", "-q", "-b", "main")
            git(checkout, "add", "-A")
            git(checkout, "commit", "-q", "-m", "fixture")
            self.checkouts[name] = checkout
        snapshot = self.root / "snapshot"
        runner.snapshot_context(self.checkouts["xberg"], snapshot)
        self.identity["context_sha256"] = runner.context_fingerprint(snapshot)
        self.write_json("context-identity.json", self.identity)
        self.preflight_data = json.loads(self.preflight.read_text())
        for check in self.preflight_data["checks"].values():
            check["context_sha256"] = self.identity["context_sha256"]
        self.preflight.write_text(json.dumps(self.preflight_data))
        self.plan = self.load()
        RuntimePlanTest.advance(self, self.plan)
        self.original_bytes = {path: path.read_bytes() for path in self.source.rglob("*") if path.is_file()}
        self.calls = []

    @contextmanager
    def patched_commands(self):
        @contextmanager
        def checkout(repo, ref):
            self.assertEqual(ref, self.preflight_data["refs"][repo.name])
            yield self.checkouts[repo.name]

        with (
            patch("runner.worktree", side_effect=checkout),
            patch("runner.resolve_ref", side_effect=lambda repo, _: self.preflight_data["refs"][repo.name]),
            patch("runner.binary_fingerprint", side_effect=lambda name, _: "b" * 64 if name == "claude" else "c" * 64),
            patch("harness.cases_mod.load_corpus", return_value=self.corpus),
            patch("continuation.workspace_root", return_value=self.root),
            patch("gateway_transport.HardExecute", side_effect=lambda *_: FakeCollector(self.ledger_path, self.calls)),
        ):
            yield

    def invoke(self, *command, **extra):
        return harness.main(
            ["--hard-budget", "--budget-ledger", str(self.ledger_path), "--budget-usd", "25", *command],
            environ={"ANTHROPIC_API_KEY": "OFFLINE_UNUSED", "PATH": os.environ["PATH"]},
            **extra,
        )

    def collect(self) -> dict:
        self.prepare_collection()
        outputs = {}
        with self.patched_commands():
            for name in ("xberg", "sceptre"):
                out = self.ledger_path.parent / "epoch2" / name
                code = self.invoke(
                    "continue",
                    "--manifest",
                    str(self.plan.path),
                    "--manifest-sha256",
                    self.plan.sha256,
                    "--repo",
                    str(self.root / name),
                    "--out",
                    str(out),
                )
                self.assertEqual(code, 0)
                outputs[name] = out
        return outputs


class CollectionIntegrationTest(CollectionFixture, unittest.TestCase):
    def test_both_consumers_retain_original_trials_and_collect_only_the_exact_remainder(self) -> None:
        outputs = self.collect()
        self.assertEqual(len(self.calls), 4)
        self.assertEqual(len(list((outputs["xberg"] / "transcripts").glob("*.jsonl"))), 1)
        self.assertEqual(len(list((outputs["sceptre"] / "transcripts").glob("*.jsonl"))), 3)
        rows = records.read_sessions(outputs["xberg"] / "sessions.jsonl")
        self.assertEqual(len(rows), 3)
        self.assertEqual(scoring.summarise(rows)["all_trials"]["completion"]["rate"], 2 / 3)
        self.assertEqual(sum(row.bounded_failure for row in rows), 1)
        self.assertEqual({row.provenance["epoch"] for row in rows}, {0, 1})
        self.assertEqual({path: path.read_bytes() for path in self.original_bytes}, self.original_bytes)
        self.assertEqual(self.ledger.spent(), 6000)
        with self.assertRaises(continuation.ContinuationError):
            self.plan.aggregate([outputs["xberg"]], testkit.domains())
        combined = self.plan.aggregate([outputs["xberg"], outputs["sceptre"]], testkit.domains())
        self.assertEqual(combined["expected_trials"], 6)
        self.assertEqual(combined["summary"]["overall"]["all_trials"]["executed_trials"], 6)
        self.assertEqual(combined["financial"]["settled_nanos"], 6000)
        before = self.ledger_path.read_bytes()
        report = self.ledger_path.parent / "combined-report.json"
        with self.patched_commands():
            code = self.invoke(
                "continue-report",
                "--manifest",
                str(self.plan.path),
                "--manifest-sha256",
                self.plan.sha256,
                "--run",
                str(outputs["xberg"]),
                "--run",
                str(outputs["sceptre"]),
                "--out",
                str(report),
            )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(report.read_text())["expected_trials"], 6)
        self.assertEqual(self.ledger_path.read_bytes(), before)
        self.assertEqual(len(self.calls), 4)

    def test_report_verification_masks_unvalidated_saved_criteria_without_rewriting_files(self) -> None:
        outputs = self.collect()
        path = outputs["xberg"] / "sessions.jsonl"
        rows = records.read_sessions(path)
        rows[0].criteria = dict.fromkeys(rows[0].criteria, True)
        records.write_sessions(path, rows)
        before = path.read_bytes()
        checked = self.plan.verify_run(outputs["xberg"], testkit.domains())
        self.assertTrue(all(value is None for value in checked[0].criteria.values()))
        self.assertEqual(path.read_bytes(), before)

    def test_plain_resume_cannot_drop_the_manifest_and_rerun_inherited_trials(self) -> None:
        outputs = self.collect()
        path = outputs["xberg"] / "run.json"
        before = path.read_bytes()
        calls = len(self.calls)
        with self.patched_commands():
            code = self.invoke(
                "run",
                "--repo",
                str(self.root / "xberg"),
                "--ref",
                self.preflight_data["refs"]["xberg"],
                "--model",
                "claude-sonnet-5-5",
                "--repeats",
                "3",
                "--max-turns",
                "8",
                "--timeout",
                "180",
                "--jobs",
                "1",
                "--resume",
                "--out",
                str(outputs["xberg"]),
            )
        self.assertEqual(code, 2)
        self.assertEqual(len(self.calls), calls)
        self.assertEqual(path.read_bytes(), before)

    def test_judging_rejects_altered_session_provenance_before_any_grader_call(self) -> None:
        from unittest.mock import Mock

        outputs = self.collect()
        path = outputs["xberg"] / "sessions.jsonl"
        rows = records.read_sessions(path)
        rows[0].provenance["epoch"] = 99
        records.write_sessions(path, rows)
        forbidden = Mock(side_effect=AssertionError("unreviewed data reached a grader"))
        with self.patched_commands():
            code = self.invoke(
                "judge", str(outputs["xberg"]), "--model", "claude-sonnet-5-5", grader_factory=lambda _: forbidden
            )
        self.assertEqual(code, 2)
        forbidden.assert_not_called()


if __name__ == "__main__":
    unittest.main()
