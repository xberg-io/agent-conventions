"""A real normal commit must reject stale runtimes independently of the canonical validator."""

from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

import hook_fixture_commands as commands
import hook_preflight_fixtures as fixtures


class DistributedPreflightTest(unittest.TestCase):
    def test_stale_validator_can_pass_but_the_normal_commit_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(dir=fixtures.fixture_parent()) as directory:
            root = Path(directory)
            environment = fixtures.setup(root, stale=True)
            result, events = fixtures.commit(root, environment, "stale")
            gates, validators = fixtures.captured(events)
            self.assertEqual(len(gates), 1, result.stdout + result.stderr)
            self.assertEqual([event["status"] for event in validators], [0])
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("npm latest is 5.9.8", result.stdout + result.stderr)

    def test_current_runtime_and_valid_data_commit_with_both_real_hooks(self) -> None:
        with tempfile.TemporaryDirectory(dir=fixtures.fixture_parent()) as directory:
            root = Path(directory)
            environment = fixtures.setup(root)
            result, events = fixtures.commit(root, environment, "current")
            gates, validators = fixtures.captured(events)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(len(gates), 1)
            self.assertEqual([event["status"] for event in validators], [0])
            self.assertNotEqual(gates[0]["cwd"], str(root.resolve()))
            self.assertNotEqual(gates[0]["source_root"], str(root / "gauv producer"))
            self.assertTrue(Path(gates[0]["source_root"]).is_dir())

    def test_a_freshness_pass_does_not_hide_a_validator_failure(self) -> None:
        with tempfile.TemporaryDirectory(dir=fixtures.fixture_parent()) as directory:
            root = Path(directory)
            environment = fixtures.setup(root)
            (root / ".ai-rulez/config.toml").write_text('version="5.0"\nname=\n')
            fixtures.git(root, environment, "add", ".ai-rulez/config.toml")
            result, events = fixtures.commit(root, environment, "validator-failure")
            gates, validators = fixtures.captured(events)
            self.assertEqual(len(gates), 1)
            self.assertEqual(len(validators), 1)
            self.assertNotEqual(validators[0]["status"], 0)
            self.assertNotEqual(result.returncode, 0)
            output = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout + result.stderr)
            self.assertIn("  ✓ gauv-preflight:ai-runtime-freshness", output.splitlines())
            probes = [event for event in events if event.get("args") == ["--version"]]
            self.assertEqual([(event["provider"], event["status"]) for event in probes], [("ai-rulez", 0)])

    def test_unmeasurable_selected_runtime_rejects_the_normal_commit(self) -> None:
        with tempfile.TemporaryDirectory(dir=fixtures.fixture_parent()) as directory:
            root = Path(directory)
            environment = fixtures.setup(root)
            environment["FAIL_VERSION"] = "1"
            result, events = fixtures.commit(root, environment, "unmeasured")
            gates, validators = fixtures.captured(events)
            self.assertEqual(len(gates), 1)
            self.assertEqual([event["status"] for event in validators], [0])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--version exited 17", result.stdout + result.stderr)

    def test_linked_preferences_override_main_and_missing_preferences_fall_back(self) -> None:
        with tempfile.TemporaryDirectory(dir=fixtures.fixture_parent()) as directory:
            base = Path(directory)
            main, linked = base / "main worktree", base / "linked worktree"
            main.mkdir()
            environment = fixtures.setup(main)
            first, _ = fixtures.commit(main, environment, "linked-main")
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            fixtures.git(main, environment, "worktree", "add", "-b", "linked", str(linked))
            commands.directory(main / "bin", linked / "bin")
            environment["AI_VERSION_SYSTEM"] = fixtures.OLD
            if os.environ.get("PREFLIGHT_NATIVE_OLD"):
                environment["NATIVE_AI_SYSTEM"] = os.environ["PREFLIGHT_NATIVE_OLD"]
            for local in (False, True):
                with self.subTest(local_override=local):
                    if local:
                        (linked / "poly.local.toml").write_text('[hook_preferences]\nchannels=["npm", "system"]\n')
                    (linked / ".ai-rulez/config.toml").write_text(fixtures.VALID_CONFIG + f'description="{local}"\n')
                    fixtures.git(linked, environment, "add", ".ai-rulez/config.toml")
                    result, events = fixtures.commit(linked, environment, f"linked-{local}")
                    gates, validators = fixtures.captured(events)
                    if local:
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    else:
                        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(len(gates), 1)
                    self.assertEqual([v["provider"] for v in validators], ["npx" if local else "ai-rulez"])
                    self.assertEqual([v["status"] for v in validators], [0])
                    probes = [event for event in events if event.get("args") == ["--version"]]
                    self.assertEqual([p["provider"] for p in probes], ["npx" if local else "ai-rulez"])

    def test_partial_staging_and_alternate_index_keep_worktree_selection_and_snapshot_execution(self) -> None:
        with tempfile.TemporaryDirectory(dir=fixtures.fixture_parent()) as directory:
            root = Path(directory)
            environment = fixtures.setup(root)
            initial, _ = fixtures.commit(root, environment, "index-initial")
            self.assertEqual(initial.returncode, 0, initial.stdout + initial.stderr)
            index = root / "alternate index"
            environment["GIT_INDEX_FILE"] = str(index)
            fixtures.git(root, environment, "read-tree", "HEAD")
            working_config = (root / "poly.toml").read_text()
            (root / "poly.toml").write_text(working_config.replace('hooks=["ai-rulez-validate"]', 'hooks=["missing"]'))
            (root / "probe.txt").write_text("staged probe\n")
            (root / ".ai-rulez/config.toml").write_text(fixtures.VALID_CONFIG + 'description="staged"\n')
            fixtures.git(root, environment, "add", "poly.toml", "probe.txt", ".ai-rulez/config.toml")
            (root / "poly.toml").write_text(working_config)
            (root / "probe.txt").write_text("unstaged probe\n")
            result, events = fixtures.commit(root, environment, "alternate-index")
            gates, validators = fixtures.captured(events)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual([v["status"] for v in validators], [0])
            self.assertEqual(len(gates), 1)
            self.assertEqual(gates[0]["index"], str(index))
            self.assertEqual(gates[0]["probe"], "staged probe\n")
            self.assertIn('hooks=["missing"]', gates[0]["snapshot_config"])
            self.assertEqual((root / "poly.toml").read_text(), working_config)
            self.assertEqual((root / "probe.txt").read_text(), "unstaged probe\n")

    def test_unassociated_separate_git_dir_fails_closed_without_hiding_validator(self) -> None:
        with tempfile.TemporaryDirectory(dir=fixtures.fixture_parent()) as directory:
            base = Path(directory)
            root = base / "consumer"
            root.mkdir()
            environment = fixtures.setup(root, separate=base / "metadata.git")
            result, events = fixtures.commit(root, environment, "separate-git-dir")
            gates, validators = fixtures.captured(events)
            self.assertEqual(len(gates), 1)
            self.assertEqual([v["status"] for v in validators], [0])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exactly one registered worktree, found 0", result.stdout + result.stderr)

    def test_missing_export_refuses_the_nearest_repository_instead_of_guessing(self) -> None:
        with tempfile.TemporaryDirectory(dir=fixtures.fixture_parent()) as directory:
            root = Path(directory)
            environment = fixtures.setup(root)
            result = fixtures.poly_fixtures.run(
                [sys.executable, str(fixtures.MODULES / "hook_preflight.py")], root, environment
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("requires an exported absolute GIT_DIR directory", result.stderr)


class WorktreePreflightTest(unittest.TestCase):
    def test_explicit_worktree_mode_commits_without_an_inferred_context_export(self) -> None:
        with tempfile.TemporaryDirectory(dir=fixtures.fixture_parent()) as directory:
            root = Path(directory)
            environment = fixtures.setup(root, worktree=True)
            result, events = fixtures.commit(root, environment, "worktree-current")
            gates, validators = fixtures.captured(events)
            self.assertEqual(len(gates), 1, result.stdout + result.stderr)
            self.assertEqual([v["status"] for v in validators], [0])
            self.assertEqual(gates[0]["argv"], ["--worktree"])
            self.assertEqual(gates[0]["cwd"], str(root.resolve()))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_stale_worktree_runtime_rejects_commit_while_validator_still_passes(self) -> None:
        with tempfile.TemporaryDirectory(dir=fixtures.fixture_parent()) as directory:
            root = Path(directory)
            environment = fixtures.setup(root, worktree=True, stale=True)
            result, events = fixtures.commit(root, environment, "worktree-stale")
            gates, validators = fixtures.captured(events)
            self.assertEqual(len(gates), 1)
            self.assertEqual(gates[0]["argv"], ["--worktree"])
            self.assertEqual([v["status"] for v in validators], [0])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("npm latest is 5.9.8", result.stdout + result.stderr)

    def test_a_reported_newer_worktree_runtime_does_not_replace_official_latest(self) -> None:
        with tempfile.TemporaryDirectory(dir=fixtures.fixture_parent()) as directory:
            root = Path(directory)
            environment = fixtures.setup(root, worktree=True)
            environment.pop("NATIVE_AI_SYSTEM", None)
            environment["AI_VERSION_SYSTEM"] = "99.0.0"
            result, events = fixtures.commit(root, environment, "worktree-newer-local")
            gates, validators = fixtures.captured(events)
            self.assertEqual(len(gates), 1)
            self.assertEqual([v["status"] for v in validators], [0])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("selected system ai-rulez 99.0.0, npm latest is 5.9.8", result.stdout + result.stderr)

    def test_worktree_linked_override_and_main_fallback_measure_the_selected_provider(self) -> None:
        with tempfile.TemporaryDirectory(dir=fixtures.fixture_parent()) as directory:
            base = Path(directory)
            main, linked = base / "main worktree", base / "linked worktree"
            main.mkdir()
            environment = fixtures.setup(main, worktree=True)
            first, _ = fixtures.commit(main, environment, "worktree-linked-main")
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            fixtures.git(main, environment, "worktree", "add", "-b", "linked", str(linked))
            commands.directory(main / "bin", linked / "bin")
            environment["AI_VERSION_SYSTEM"] = fixtures.OLD
            if os.environ.get("PREFLIGHT_NATIVE_OLD"):
                environment["NATIVE_AI_SYSTEM"] = os.environ["PREFLIGHT_NATIVE_OLD"]
            for local in (False, True):
                with self.subTest(local_override=local):
                    if local:
                        (linked / "poly.local.toml").write_text('[hook_preferences]\nchannels=["npm", "system"]\n')
                    (linked / ".ai-rulez/config.toml").write_text(fixtures.VALID_CONFIG + f'description="{local}"\n')
                    fixtures.git(linked, environment, "add", ".ai-rulez/config.toml")
                    result, events = fixtures.commit(linked, environment, f"worktree-linked-{local}")
                    gates, validators = fixtures.captured(events)
                    self.assertEqual(len(gates), 1)
                    self.assertEqual(gates[0]["cwd"], str(linked.resolve()))
                    self.assertEqual([v["provider"] for v in validators], ["npx" if local else "ai-rulez"])
                    self.assertEqual([v["status"] for v in validators], [0])
                    self.assertEqual(result.returncode == 0, local, result.stdout + result.stderr)

    def test_worktree_active_index_policy_cannot_be_replaced_by_the_normal_index(self) -> None:
        with tempfile.TemporaryDirectory(dir=fixtures.fixture_parent()) as directory:
            root = Path(directory)
            environment = fixtures.setup(root, worktree=True)
            alternate = {**environment, "GIT_INDEX_FILE": str(root / "alternate index")}
            fixtures.git(root, alternate, "read-tree", "--empty")
            fixtures.git(root, alternate, "add", "poly.toml", "poly-hooks.lock", "probe.txt", ".ai-rulez/config.toml")
            fixtures.index_policy(root, alternate, isolated=True)
            self.assertIn("isolate=true", fixtures.git(root, alternate, "show", ":poly.toml"))
            self.assertIn("isolate=false", fixtures.git(root, environment, "show", ":poly.toml"))
            rejected, events = fixtures.commit(root, alternate, "worktree-alternate-reject")
            gates, validators = fixtures.captured(events)
            self.assertEqual([v["status"] for v in validators], [0])
            self.assertEqual(len(gates), 1)
            self.assertEqual(gates[0]["index"], alternate["GIT_INDEX_FILE"])
            self.assertNotEqual(rejected.returncode, 0, rejected.stdout + rejected.stderr)
            self.assertIn(
                "active-index policy requires explicit hooks.isolate=false", rejected.stdout + rejected.stderr
            )
            fixtures.index_policy(root, alternate, isolated=False)
            fixtures.index_policy(root, environment, isolated=True)
            self.assertIn("isolate=false", fixtures.git(root, alternate, "show", ":poly.toml"))
            self.assertIn("isolate=true", fixtures.git(root, environment, "show", ":poly.toml"))
            accepted, events = fixtures.commit(root, alternate, "worktree-alternate-accept")
            gates, validators = fixtures.captured(events)
            self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)
            self.assertEqual([v["status"] for v in validators], [0])
            self.assertEqual(gates[0]["cwd"], str(root.resolve()))
            self.assertIn("isolate=false", (root / "poly.toml").read_text())

    def test_worktree_entry_cannot_treat_an_isolated_snapshot_as_the_consumer(self) -> None:
        with tempfile.TemporaryDirectory(dir=fixtures.fixture_parent()) as directory:
            root = Path(directory)
            environment = fixtures.setup(root, worktree=True)
            path = root / "poly.toml"
            path.write_text(path.read_text().replace("isolate=false", "isolate=true"))
            result, events = fixtures.commit(root, environment, "worktree-wrong-snapshot")
            gates, validators = fixtures.captured(events)
            self.assertEqual(len(gates), 1)
            self.assertNotEqual(gates[0]["cwd"], str(root.resolve()))
            self.assertEqual([v["status"] for v in validators], [0])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exact Git top-level", result.stdout + result.stderr)

    def test_explicit_worktree_mode_still_refuses_an_unassociated_separate_git_dir(self) -> None:
        with tempfile.TemporaryDirectory(dir=fixtures.fixture_parent()) as directory:
            base = Path(directory)
            root = base / "consumer"
            root.mkdir()
            environment = fixtures.setup(root, separate=base / "metadata.git", worktree=True)
            result, events = fixtures.commit(root, environment, "worktree-separate-git-dir")
            gates, validators = fixtures.captured(events)
            self.assertEqual(len(gates), 1)
            self.assertEqual([v["status"] for v in validators], [0])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exactly one registered worktree, found 0", result.stdout + result.stderr)
