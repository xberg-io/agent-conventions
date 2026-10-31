"""The selected hook command must run the newest stable CLI, not merely lock a valid source."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shlex
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

import hook_pins
import hook_runtime

COMMIT = "96942fd51a8840bb796ed9ba117d18b5d2d011d0"
CATALOGUE = """version = 1
[[hooks]]
id = "ai-rulez-validate"
stages = ["pre-commit"]
args = ["validate", "--no-local"]
files = ["**"]
always_run = true
workspace = true
pass_filenames = false
[[hooks.paths]]
channel = "system"
check = "command -v ai-rulez"
run = "ai-rulez"
[[hooks.paths]]
channel = "npm"
check = "command -v npx"
run = "npx -y ai-rulez@latest"
"""


def configure(root: Path, channels: str = '["system"]') -> None:
    (root / "poly.toml").write_text(
        '[[hooks.sources]]\nid="ai-rulez"\ngit="https://github.com/Goldziher/ai-rulez.git"\n'
        'revision="v5"\nhooks=["ai-rulez-validate"]\n'
    )
    (root / "poly-hooks.lock").write_text(
        f'version=1\n[[sources]]\nid="ai-rulez"\nsource="https://github.com/Goldziher/ai-rulez.git"\n'
        f'revision="{COMMIT}"\npath="cache://fixture/{COMMIT}"\n'
    )
    (root / "poly.local.toml").write_text(f"[hook_preferences]\nchannels={channels}\n")


def executable(path: Path, version: str, trace: Path | None = None) -> None:
    record = f'printf "%s %s\\n" "{path.name}" "$*" >> {shlex.quote(str(trace))}\n' if trace else ""
    path.write_text(f'#!/bin/sh\n{record}printf "ai-rulez version {version}\\n"\n')
    path.chmod(0o755)


def invalid_locks(body: str) -> list[tuple[str, str]]:
    cases = [
        ("missing version", body.replace("version=1\n", "")),
        ("boolean version", body.replace("version=1", "version=true")),
        ("unsupported version", body.replace("version=1", "version=2")),
        ("missing sources", "version=1\n"),
    ]
    for key in ("id", "source", "revision", "path"):
        line = next(line for line in body.splitlines(True) if line.startswith(key + "="))
        cases.append((f"missing {key}", body.replace(line, "")))
        cases.append((f"nonstring {key}", body.replace(line, f"{key}=123\n")))
    cases.append(
        ("unused source missing path", body + '\n[[sources]]\nid="unused"\nsource="other"\nrevision="other"\n')
    )
    return cases


def network(request: str, **_kwargs: object) -> io.BytesIO:
    url = request
    if url == "https://registry.npmjs.org/ai-rulez/latest":
        return io.BytesIO(json.dumps({"name": "ai-rulez", "version": "5.9.8"}).encode())
    if url == f"https://raw.githubusercontent.com/Goldziher/ai-rulez/{COMMIT}/poly-hooks.toml":
        return io.BytesIO(CATALOGUE.encode())
    raise AssertionError(f"unexpected network boundary: {url}")


class RuntimeGateTest(unittest.TestCase):
    def test_unset_path_must_not_search_the_platform_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable(root / "ai-rulez", "5.9.8")
            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(os, "defpath", str(root)),
                self.assertRaisesRegex(ValueError, "PATH is unset"),
            ):
                hook_runtime.select(["ai-rulez-validate"], tomllib.loads(CATALOGUE), ["system"], root)

    def test_public_runtime_cli_refuses_unset_path_even_with_a_default_provider(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configure(root)
            executable(root / "ai-rulez", "5.9.8")
            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(os, "defpath", str(root)),
                patch.object(sys, "argv", ["hook_pins.py", "--consumer", str(root), "--runtime"]),
                patch("urllib.request.urlopen", side_effect=network),
                contextlib.redirect_stderr(io.StringIO()) as errors,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(hook_pins.main(), 1)
            self.assertIn("PATH is unset", errors.getvalue())

    def test_lock_extensions_and_descriptive_path_do_not_change_the_catalogue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configure(root)
            executable(root / "ai-rulez", "5.9.8")
            path = root / "poly-hooks.lock"
            body = path.read_text().replace("version=1\n", 'version=1\nfuture_header="allowed"\n')
            body = body.replace(f'path="cache://fixture/{COMMIT}"', 'path="not-an-execution-selector"')
            path.write_text(body + "future_source=123\n")
            with (
                patch.dict(os.environ, {"PATH": str(root)}, clear=True),
                patch("urllib.request.urlopen", side_effect=network),
            ):
                self.assertEqual([result.version for result in hook_runtime.verify(root)], ["5.9.8"])

    def test_rejects_stale_system_despite_current_equal_hook_definition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configure(root)
            executable(root / "ai-rulez", "5.9.6")
            arguments = ["hook_pins.py", "--consumer", str(root), "--runtime"]
            output, errors = io.StringIO(), io.StringIO()
            with (
                patch.object(sys, "argv", arguments),
                patch.dict(os.environ, {"PATH": str(root)}, clear=True),
                patch("urllib.request.urlopen", side_effect=network),
                contextlib.redirect_stdout(output),
                contextlib.redirect_stderr(errors),
            ):
                status = hook_pins.main()
            self.assertEqual(status, 1, "valid floating source and commit must not hide a stale selected CLI")
            self.assertIn("5.9.6", errors.getvalue())
            self.assertIn("5.9.8", errors.getvalue())

    def test_current_system_is_accepted_without_changing_preferences_or_cli(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configure(root)
            executable(root / "ai-rulez", "5.9.8")
            before = {path.name: path.read_bytes() for path in root.iterdir()}
            with (
                patch.dict(os.environ, {"PATH": str(root)}, clear=True),
                patch("urllib.request.urlopen", side_effect=network),
            ):
                measured = hook_runtime.verify(root)
            self.assertEqual(
                [(item.hook, item.channel, item.version) for item in measured],
                [("ai-rulez-validate", "system", "5.9.8")],
            )
            self.assertEqual({path.name: path.read_bytes() for path in root.iterdir()}, before)

    def test_stale_system_is_measured_before_any_npm_reference_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configure(root)
            trace = root / "trace"
            executable(root / "ai-rulez", "5.9.6", trace)
            executable(root / "npx", "5.9.8", trace)
            requests = []

            def reference(request: str, **kwargs: object) -> io.BytesIO:
                requests.append(request)
                if request == hook_runtime.REGISTRY:
                    self.assertEqual(trace.read_text(), "ai-rulez --version\n")
                return network(request, **kwargs)

            with (
                patch.dict(os.environ, {"PATH": str(root)}, clear=True),
                patch("urllib.request.urlopen", side_effect=reference),
                self.assertRaisesRegex(ValueError, "selected system ai-rulez 5.9.6, npm latest is 5.9.8"),
            ):
                hook_runtime.verify(root)
            self.assertEqual(len(requests), 2)
            self.assertEqual(trace.read_text(), "ai-rulez --version\n")

    def test_unknown_or_unreviewed_catalogues_are_rejected(self) -> None:
        mutations = [
            (CATALOGUE.replace("version = 1", "version = 2"), "catalog version"),
            (CATALOGUE.replace("version = 1", "version = true"), "catalog version"),
            (CATALOGUE.replace("version = 1", 'version = 1\nunknown = "field"'), "unreviewed"),
            (
                CATALOGUE.replace('stages = ["pre-commit"]', 'stages = ["pre-commit"]\nenv = {PATH="/other"}'),
                "unreviewed",
            ),
            (CATALOGUE.replace('stages = ["pre-commit"]', "stages = []"), "stages"),
            (CATALOGUE.replace('stages = ["pre-commit"]', 'stages = ["pre-commit"]\ncwd = "other"'), "unreviewed"),
            (CATALOGUE.replace('stages = ["pre-commit"]', 'stages = ["pre-commit"]\nroot = "other"'), "unreviewed"),
            (CATALOGUE.replace('channel = "system"', 'channel = "uvx"'), "unknown"),
            (CATALOGUE.replace('run = "ai-rulez"', 'run = "ai-rulez && false"'), "unreviewed"),
            (CATALOGUE.replace('check = "command -v ai-rulez"', 'check = "true"'), "unreviewed"),
            (CATALOGUE.replace('run = "ai-rulez"', 'run = "ai-rulez"\ninstall = "unexpected installer"'), "unreviewed"),
            (CATALOGUE.replace('id = "ai-rulez-validate"', 'id = "other"'), "absent"),
            (CATALOGUE + '\n[[hooks.paths]]\nchannel="system"\n', "duplicate"),
            ("version=1\n[[hooks]]\n", "catalog"),
        ]
        for content, message in mutations:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                hook_runtime.select(["ai-rulez-validate"], tomllib.loads(content), ["system"])

    def test_empty_or_unavailable_hook_selection_cannot_pass(self) -> None:
        producer = tomllib.loads(CATALOGUE)
        with self.assertRaisesRegex(ValueError, "zero hooks"):
            hook_runtime.select([], producer, ["system"])
        with patch.dict(os.environ, {"PATH": ""}, clear=True), self.assertRaisesRegex(ValueError, "no eligible"):
            hook_runtime.select(["ai-rulez-validate"], producer, ["npm", "system"])

    def test_zero_configured_hooks_are_rejected_before_network_access(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configure(root)
            path = root / "poly.toml"
            path.write_text(path.read_text().replace('["ai-rulez-validate"]', "[]"))
            with (
                patch("urllib.request.urlopen", side_effect=AssertionError("unexpected fetch")),
                self.assertRaisesRegex(ValueError, "nonempty selected hooks"),
            ):
                hook_runtime.verify(root)

    def test_missing_preferences_are_rejected_before_network_access(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configure(root)
            (root / "poly.local.toml").unlink()
            with (
                patch.dict(os.environ, {"PATH": ""}, clear=True),
                patch("urllib.request.urlopen", side_effect=AssertionError("unexpected fetch")),
                self.assertRaisesRegex(ValueError, "no provider"),
            ):
                hook_runtime.verify(root)

    def test_unknown_duplicate_or_missing_preferences_never_guess_a_channel(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for value in ('["uvx"]', '["system", "system"]', "[]", '"system"'):
                with self.subTest(channels=value):
                    configure(root, value)
                    with self.assertRaisesRegex(ValueError, "channel"):
                        hook_runtime.preferences(root)
            (root / "poly.local.toml").unlink()
            with patch.dict(os.environ, {"PATH": ""}, clear=True), self.assertRaisesRegex(ValueError, "no provider"):
                hook_runtime.preferences(root)

    def test_malformed_nonstable_or_failed_version_output_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            command = Path(directory) / "ai-rulez"
            for version in ("5.9.8-beta.1", "05.9.8", "5.9", "5.9.8 extra"):
                with self.subTest(version=version):
                    executable(command, version)
                    with self.assertRaisesRegex(ValueError, "stable version"):
                        hook_runtime.measure((str(command),))
            command.write_text("#!/bin/sh\nexit 9\n")
            with self.assertRaisesRegex(ValueError, "exited 9"):
                hook_runtime.measure((str(command),))

    def test_registry_errors_and_unstable_references_fail_closed(self) -> None:
        for body in ({"name": "other", "version": "5.9.8"}, {"name": "ai-rulez", "version": "5.9.9-rc.1"}):
            with (
                self.subTest(body=body),
                patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(body).encode())),
                self.assertRaisesRegex(ValueError, "stable ai-rulez"),
            ):
                hook_runtime.latest()
        with (
            patch("urllib.request.urlopen", side_effect=OSError("offline")),
            self.assertRaisesRegex(OSError, "offline"),
        ):
            hook_runtime.latest()

    def test_untrusted_catalogue_source_is_rejected_without_fetching_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configure(root)
            path = root / "poly-hooks.lock"
            path.write_text(path.read_text().replace("Goldziher/ai-rulez.git", "other/ai-rulez.git"))
            with (
                patch("urllib.request.urlopen", side_effect=AssertionError("unexpected fetch")),
                self.assertRaisesRegex(ValueError, "canonical Goldziher"),
            ):
                hook_runtime.verify(root)

    def test_source_only_mode_remains_explicitly_separate_from_runtime_measurement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configure(root)
            with (
                patch.object(sys, "argv", ["hook_pins.py", "--consumer", str(root)]),
                patch("urllib.request.urlopen", side_effect=AssertionError("unexpected runtime fetch")),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                self.assertEqual(hook_pins.main(), 0)
            self.assertIn("1 hook sources", output.getvalue())
            self.assertNotIn("checked AI runtime", output.getvalue())

    def test_linked_worktree_uses_main_preferences_unless_it_has_its_own(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            main = root / "main worktree"
            linked = root / "linked"
            main.mkdir()
            linked.mkdir()
            (main / "poly.local.toml").write_text('[hook_preferences]\nchannels=["npm", "system"]\n')
            git = root / "git"
            git.write_text(
                '#!/bin/sh\ncase "$*" in *"--porcelain -z") '
                f'printf "%s\\0" {shlex.quote("worktree " + str(main))} "HEAD fixture" "";; *) exit 2;; esac\n'
            )
            git.chmod(0o755)
            with patch.dict(os.environ, {"PATH": str(root)}, clear=True):
                self.assertEqual(hook_runtime.preferences(linked), ["npm", "system"])
                (linked / "poly.local.toml").write_text('[hook_preferences]\nchannels=["system"]\n')
                self.assertEqual(hook_runtime.preferences(linked), ["system"])

    def test_unknown_source_and_machine_preference_fields_fail_before_fetching(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for filename, addition in (
                ("poly.toml", 'unreviewed = "field"\n'),
                ("poly.local.toml", 'unreviewed = "field"\n'),
            ):
                with self.subTest(filename=filename):
                    configure(root)
                    executable(root / "ai-rulez", "5.9.8")
                    path = root / filename
                    path.write_text(path.read_text() + addition)
                    with (
                        patch.dict(os.environ, {"PATH": str(root)}, clear=True),
                        patch("urllib.request.urlopen", side_effect=network),
                        self.assertRaisesRegex(ValueError, "unknown .*field"),
                    ):
                        hook_runtime.verify(root)


if __name__ == "__main__":
    unittest.main()
