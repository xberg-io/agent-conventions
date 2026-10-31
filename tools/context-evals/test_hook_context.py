"""Original consumer identity comes from Poly's Git context, never a snapshot path guess."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

import hook_context
import hook_runtime
import test_hook_runtime_poly as fixtures

CAPTURE = """import json, os, sys
from pathlib import Path
sys.path.insert(0, os.environ["CONTEXT_MODULES"])
import hook_context
import hook_runtime
try:
    context = hook_context.bind(Path.cwd())
except ValueError as error:
    with open(os.environ["CONTEXT_TRACE"], "a") as trace:
        trace.write(json.dumps({"error": str(error), "execution_root": str(Path.cwd()),
                                "git_dir": os.environ.get("GIT_DIR")}) + "\\n")
    sys.exit(1)
record = {"consumer": str(context.consumer), "execution_root": str(context.execution_root),
          "git_dir": str(context.git_dir), "index_file": str(context.index_file),
          "exported": {key: os.environ.get(key) for key in
                       ["GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OPTIONAL_LOCKS"]},
          "selected": sys.argv[1:], "snapshot_config": Path("poly.toml").read_text(),
          "snapshot_probe": Path("probe.txt").read_text(),
          "preferences": hook_runtime.preferences(context.consumer)}
with open(os.environ["CONTEXT_TRACE"], "a") as trace:
    trace.write(json.dumps(record) + "\\n")
"""


def fixture_parent() -> Path:
    parent = Path(__file__).resolve().parents[3] / "reports/conventions-hook-context-2026-10-31/fixtures"
    parent.mkdir(parents=True, exist_ok=True)
    return parent


def git(root: Path, environment: dict[str, str], *arguments: str) -> str:
    result = fixtures.run([str(root / "bin/git"), *arguments], root, environment)
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout.strip()


def catalogues() -> str:
    return "version=1\n" + "\n".join(
        f'''
[[hooks]]
id="capture-{name}"
stages=["pre-commit"]
args=["{name}-source"]
files=["**"]
workspace=true
always_run=true
pass_filenames=false
[[hooks.paths]]
channel="system"
check="command -v python3"
run='python3 "$POLY_HOOK_SOURCE_ROOT/capture.py" system'
[[hooks.paths]]
channel="npm"
check="command -v python3"
run='python3 "$POLY_HOOK_SOURCE_ROOT/capture.py" npm'
'''
        for name in ("context", "index")
    )


def setup(root: Path) -> dict[str, str]:
    environment = fixtures.sandbox(root, ["system"], {})
    (root / "bin/python3").symlink_to(sys.executable)
    (root / "producer/capture.py").write_text(CAPTURE)
    (root / "producer/poly-hooks.toml").write_text(catalogues())
    path = root / "poly.toml"
    path.write_text(path.read_text().replace('hooks=["ai-rulez-validate"]', 'hooks=["capture-context"]'))
    environment["CONTEXT_MODULES"] = str(Path(__file__).parent)
    environment["CONTEXT_TRACE"] = str(root / "context.jsonl")
    return environment


def commit(poly: str, root: Path, environment: dict[str, str]) -> dict:
    trace = Path(environment["CONTEXT_TRACE"])
    trace.unlink(missing_ok=True)
    result = fixtures.execute_hook(poly, root, environment, commit=True)
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    records = [json.loads(line) for line in trace.read_text().splitlines()]
    if len(records) != 1:
        raise AssertionError(f"expected exactly one physical context hook, got {len(records)}")
    return records[0]


class HookContextTest(unittest.TestCase):
    def test_missing_relative_or_non_directory_exports_are_refused(self) -> None:
        reports = fixture_parent()
        with tempfile.TemporaryDirectory(dir=reports) as directory:
            root = Path(directory)
            for value in (None, "", ".git", str(root / "missing")):
                with self.subTest(export=value), self.assertRaisesRegex(ValueError, "exported absolute GIT_DIR"):
                    environment = {} if value is None else {"GIT_DIR": value}
                    hook_context.bind(root, environment)

    def test_ambiguous_registered_identity_is_refused(self) -> None:
        reports = fixture_parent()
        with tempfile.TemporaryDirectory(dir=reports) as directory:
            root = Path(directory)
            environment = setup(root)
            fixtures.initialize(root, environment)
            environment["GIT_DIR"] = str(root / ".git")
            real_run = subprocess.run
            duplicates = []

            def duplicated(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
                result = real_run(arguments, **kwargs)
                if "worktree" in arguments:
                    self.assertEqual(result.returncode, 0)
                    duplicates.append(True)
                    result.stdout *= 2
                return result

            with (
                patch("hook_context.subprocess.run", side_effect=duplicated),
                self.assertRaisesRegex(ValueError, "exactly one registered worktree, found 2"),
            ):
                hook_context.bind(root, environment)
            self.assertEqual(duplicates, [True])

    def test_an_execution_directory_in_another_repo_does_not_select_its_consumer(self) -> None:
        reports = fixture_parent()
        with tempfile.TemporaryDirectory(dir=reports) as directory:
            base = Path(directory)
            root, decoy = base / "consumer", base / "unrelated repository"
            root.mkdir()
            decoy.mkdir()
            environment = setup(root)
            fixtures.initialize(root, environment)
            git(root, environment, "-C", str(decoy), "init", "-q")
            environment["GIT_DIR"] = str(root / ".git")
            context = hook_context.bind(decoy, environment)
            self.assertEqual(context.consumer, root.resolve())
            self.assertEqual(context.execution_root, decoy.resolve())
            environment["GIT_DIR"] = str(base / "bare.git")
            git(root, environment, "init", "--bare", "-q", environment["GIT_DIR"])
            with self.assertRaisesRegex(ValueError, "found 0"):
                hook_context.bind(decoy, environment)

    def test_linked_worktree_keeps_local_overrides_and_main_fallback(self) -> None:
        poly = shutil.which("poly")
        self.assertIsNotNone(poly)
        reports = fixture_parent()
        with tempfile.TemporaryDirectory(prefix="hook-context-", dir=reports) as directory:
            base = Path(directory)
            main, linked = base / "main worktree", base / "linked worktree"
            main.mkdir()
            environment = setup(main)
            fixtures.initialize(main, environment)
            commit(poly, main, environment)
            git(main, environment, "worktree", "add", "-b", "fixture-linked", str(linked))
            (linked / "producer").symlink_to(main / "producer", target_is_directory=True)
            (linked / "bin").symlink_to(main / "bin", target_is_directory=True)
            for local in (False, True):
                with self.subTest(local_override=local):
                    if local:
                        (linked / "poly.local.toml").write_text('[hook_preferences]\nchannels=["npm", "system"]\n')
                    (linked / "probe.txt").write_text(f"linked content {local}\n")
                    git(main, environment, "-C", str(linked), "add", "probe.txt")
                    context = commit(poly, linked, environment)
                    self.assertEqual(context["consumer"], str(linked.resolve()))
                    self.assertEqual(context["preferences"], ["npm", "system"] if local else ["system"])
                    self.assertEqual(context["selected"][0], "npm" if local else "system")
                    self.assertNotEqual(context["execution_root"], str(linked.resolve()))
            self.reject_nearest_preferences(linked, environment, context)

    def reject_nearest_preferences(self, linked: Path, environment: dict[str, str], context: dict) -> None:
        for index, body in enumerate(
            (
                "[hook_preferences]\nchannels=[]\n",
                '[hook_preferences]\nchannels=["system"]\nunreviewed=true\n',
                "[hook_preferences\n",
            )
        ):
            with self.subTest(invalid_preferences=index):
                (linked / "poly.local.toml").write_text(body)
                Path(environment["CONTEXT_TRACE"]).unlink(missing_ok=True)
                (linked / "probe.txt").write_text(f"invalid nearest preferences {index}\n")
                git(linked, environment, "add", "probe.txt")
                result = fixtures.run(
                    [
                        str(linked / "bin/git"),
                        "-c",
                        "user.name=Fixture",
                        "-c",
                        "user.email=fixture@example.invalid",
                        "commit",
                        "-m",
                        "test: reject invalid nearest preferences",
                    ],
                    linked,
                    environment,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("poly.local.toml", result.stdout + result.stderr)
                self.assertFalse(Path(environment["CONTEXT_TRACE"]).exists())
                with self.assertRaises(ValueError):
                    hook_runtime.preferences(Path(context["consumer"]))

    def test_separate_git_directory_without_registered_top_level_fails_closed(self) -> None:
        poly = shutil.which("poly")
        self.assertIsNotNone(poly)
        reports = fixture_parent()
        for configured in (False, True):
            with self.subTest(core_worktree=configured), tempfile.TemporaryDirectory(dir=reports) as directory:
                base = Path(directory)
                root = base / "consumer space"
                root.mkdir()
                metadata = base / "metadata.git"
                environment = setup(root)
                git(root, environment, "init", "-q", "--separate-git-dir", str(metadata))
                if configured:
                    git(root, environment, "config", "core.worktree", str(root))
                git(root, environment, "add", "poly.toml", "probe.txt")
                result = fixtures.execute_hook(poly, root, environment, commit=True)
                self.assertNotEqual(result.returncode, 0)
                records = [json.loads(line) for line in Path(environment["CONTEXT_TRACE"]).read_text().splitlines()]
                self.assertEqual(len(records), 1)
                self.assertEqual(records[0]["git_dir"], str(metadata.resolve()))
                self.assertIn("exactly one registered worktree, found 0", records[0]["error"])

    def test_child_git_identity_queries_strip_inherited_snapshot_context(self) -> None:
        reports = fixture_parent()
        with tempfile.TemporaryDirectory(dir=reports) as directory:
            root = Path(directory)
            environment = setup(root)
            fixtures.initialize(root, environment)
            execution = root / "arbitrary execution"
            execution.mkdir()
            environment.update(
                {
                    "GIT_DIR": str(root / ".git"),
                    "GIT_WORK_TREE": str(execution),
                    "GIT_INDEX_FILE": str(root / "alternate.index"),
                    "GIT_COMMON_DIR": "invalid",
                }
            )
            original = dict(environment)
            calls = []
            real_run = subprocess.run

            def observed(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
                calls.append((arguments, kwargs["env"]))
                return real_run(arguments, **kwargs)

            with patch("hook_context.subprocess.run", side_effect=observed):
                context = hook_context.bind(execution, environment)
            self.assertEqual(context.consumer, root.resolve())
            self.assertEqual(context.execution_root, execution.resolve())
            self.assertEqual(context.index_file, root / "alternate.index")
            self.assertEqual(environment, original)
            self.assertGreaterEqual(len(calls), 2)
            for arguments, child in calls:
                self.assertTrue(hook_context.GIT_CONTEXT.isdisjoint(child))
                if "worktree" in arguments:
                    self.assertEqual(arguments[1:3], ["--git-dir", str((root / ".git").resolve())])
                else:
                    self.assertNotIn("--git-dir", arguments, "candidate must resolve its own Git identity")

    def test_partial_staging_retains_alternate_index_and_worktree_selection(self) -> None:
        poly = shutil.which("poly")
        self.assertIsNotNone(poly)
        reports = fixture_parent()
        with tempfile.TemporaryDirectory(prefix="hook-context-", dir=reports) as directory:
            root = Path(directory)
            environment = setup(root)
            fixtures.initialize(root, environment)
            commit(poly, root, environment)
            alternate = root / "alternate.index"
            shutil.copyfile(root / ".git/index", alternate)
            environment["GIT_INDEX_FILE"] = str(alternate)
            config = root / "poly.toml"
            original = config.read_text()
            config.write_text(original.replace('hooks=["capture-context"]', 'hooks=["capture-index"]'))
            (root / "probe.txt").write_text("staged content\n")
            git(root, environment, "add", "poly.toml", "probe.txt")
            config.write_text(original)
            (root / "probe.txt").write_text("unstaged content\n")
            context = commit(poly, root, environment)
            self.assertEqual(context["consumer"], str(root.resolve()))
            self.assertEqual(context["index_file"], str(alternate.resolve()))
            self.assertEqual(context["selected"], ["system", "context-source"])
            self.assertIn('hooks=["capture-index"]', context["snapshot_config"])
            self.assertEqual(context["snapshot_probe"], "staged content\n")
            self.assertEqual((root / "probe.txt").read_text(), "unstaged content\n")

    def test_default_isolated_normal_hook_binds_original_consumer_not_snapshot(self) -> None:
        poly = shutil.which("poly")
        self.assertIsNotNone(poly)
        reports = fixture_parent()
        with tempfile.TemporaryDirectory(prefix="hook-context-", dir=reports) as directory:
            root = Path(directory)
            environment = setup(root)
            fixtures.initialize(root, environment)
            result = fixtures.execute_hook(poly, root, environment, commit=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            records = [json.loads(line) for line in (root / "context.jsonl").read_text().splitlines()]
            self.assertEqual(len(records), 1)
            context = records[0]
            self.assertNotEqual(context["execution_root"], str(root.resolve()), "actual staged hook required")
            self.assertEqual(context["consumer"], str(root.resolve()))
            self.assertEqual(context["git_dir"], str((root / ".git").resolve()))
            self.assertEqual(context["exported"]["GIT_WORK_TREE"], None)
            self.assertEqual(context["exported"]["GIT_OPTIONAL_LOCKS"], "0")


if __name__ == "__main__":
    unittest.main()
