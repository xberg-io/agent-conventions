"""Compare the runtime resolver with the actual pinned Poly runner in isolated local-catalog repositories."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).parent))

import hook_runtime
import test_hook_runtime as fixtures

PROBE = """import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
import hook_runtime
import test_hook_runtime as fixtures
with patch("urllib.request.urlopen", side_effect=fixtures.network):
    import hook_pins
    arguments = ["hook_pins.py", "--consumer", sys.argv[2], "--runtime"]
    if len(sys.argv) > 3:
        arguments.extend(["--execution-root", sys.argv[3]])
    sys.argv = arguments
    sys.exit(hook_pins.main())
"""


def run(arguments: list[str], root: Path, environment: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(arguments, cwd=root, env=environment, capture_output=True, text=True, timeout=30, check=False)


def sandbox(root: Path, channels: list[str], versions: dict[str, str]) -> dict[str, str]:
    binary = root / "bin"
    binary.mkdir()
    for name in ("git", "sh", "poly", "dirname"):
        target = shutil.which(name)
        if target is None:
            raise AssertionError(f"Poly integration requires {name}")
        (binary / name).symlink_to(target)
    for name, version in versions.items():
        command = binary / name
        command.write_text(
            f'#!/bin/sh\nprintf "%s|%s\\n" "{name}" "$*" >> "$PROVIDER_TRACE"\nprintf "ai-rulez version {version}\\n"\n'
        )
        command.chmod(0o755)
    producer = root / "producer"
    producer.mkdir()
    (producer / "poly-hooks.toml").write_text(fixtures.CATALOGUE)
    (root / "poly.toml").write_text(
        '[hooks]\nstages=["pre-commit"]\n[hooks.builtin]\nlint=false\nfmt=false\n'
        '[[hooks.sources]]\nid="ai-rulez"\npath="producer"\nhooks=["ai-rulez-validate"]\n'
    )
    (root / "poly.local.toml").write_text(f"[hook_preferences]\nchannels={json.dumps(channels)}\n")
    (root / "probe.txt").write_text("real tracked fixture\n")
    return {
        "PATH": str(binary),
        "HOME": str(root / "home"),
        "XDG_CACHE_HOME": str(root / "cache"),
        "XDG_CONFIG_HOME": str(root / "config"),
        "PROVIDER_TRACE": str(root / "trace"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
    }


def execute_hook(poly: str, root: Path, environment: dict[str, str], *, commit: bool) -> subprocess.CompletedProcess:
    if not commit:
        return run([poly, "hooks", "run", "--all-files", "--no-cache", "--jobs", "1"], root, environment)
    installation = run([poly, "hooks", "install"], root, environment)
    if installation.returncode != 0:
        raise AssertionError(installation.stdout + installation.stderr)
    return run(
        [
            str(root / "bin/git"),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-m",
            "test: verify hook provider",
        ],
        root,
        environment,
    )


def initialize(root: Path, environment: dict[str, str]) -> None:
    for arguments in (["init", "-q"], ["add", "poly.toml", "probe.txt"]):
        result = run([str(root / "bin/git"), *arguments], root, environment)
        if result.returncode != 0:
            raise AssertionError(result.stdout + result.stderr)


def git_producer(root: Path, environment: dict[str, str]) -> str:
    producer = root / "producer"
    commands = [
        ["init", "-q"],
        ["add", "poly-hooks.toml"],
        [
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "test: define catalog",
        ],
    ]
    for arguments in commands:
        result = run([str(root / "bin/git"), "-C", str(producer), *arguments], root, environment)
        if result.returncode != 0:
            raise AssertionError(result.stdout + result.stderr)
    return run([str(root / "bin/git"), "-C", str(producer), "rev-parse", "HEAD"], root, environment).stdout.strip()


class RealPolyProviderTest(unittest.TestCase):
    def test_actual_poly_reaches_no_provider_with_git_available_but_no_ai_cli(self) -> None:
        poly = shutil.which("poly")
        self.assertIsNotNone(poly)
        reports = Path(__file__).resolve().parents[3] / "reports"
        with tempfile.TemporaryDirectory(dir=reports) as directory:
            root = Path(directory)
            environment = sandbox(root, ["system"], {})
            initialize(root, environment)
            actual = execute_hook(poly, root, environment, commit=False)
            self.assertNotEqual(actual.returncode, 0)
            self.assertIn("no eligible execution path", actual.stdout + actual.stderr)
            self.assertFalse((root / "trace").exists())

    def test_empty_path_preserves_current_directory_provider_selection(self) -> None:
        poly = shutil.which("poly")
        self.assertIsNotNone(poly)
        reports = Path(__file__).resolve().parents[3] / "reports"
        with tempfile.TemporaryDirectory(dir=reports) as directory:
            root = Path(directory)
            environment = sandbox(root, ["system"], {"ai-rulez": "5.9.8"})
            initialize(root, environment)
            for name in ("git", "sh", "ai-rulez"):
                (root / name).symlink_to(root / "bin" / name)
            environment["PATH"] = ""
            actual = execute_hook(poly, root, environment, commit=False)
            self.assertEqual(actual.returncode, 0, actual.stdout + actual.stderr)
            self.assertEqual((root / "trace").read_text().splitlines(), ["ai-rulez|validate --no-local"])
            with patch.dict(os.environ, environment, clear=True):
                selected = hook_runtime.select(
                    ["ai-rulez-validate"], tomllib.loads(fixtures.CATALOGUE), ["system"], root
                )
                self.assertEqual(hook_runtime.measure(selected[0][2], root), "5.9.8")

    def test_git_lock_path_is_descriptive_and_unknown_lock_fields_are_accepted(self) -> None:
        poly = shutil.which("poly")
        self.assertIsNotNone(poly)
        reports = Path(__file__).resolve().parents[3] / "reports"
        with tempfile.TemporaryDirectory(dir=reports) as directory:
            root = Path(directory)
            environment = sandbox(root, ["system"], {"ai-rulez": "5.9.8"})
            initialize(root, environment)
            revision = git_producer(root, environment)
            config = root / "poly.toml"
            config.write_text(
                config.read_text().replace(
                    'path="producer"', f'git={json.dumps((root / "producer").as_uri())}\nrevision="{revision}"'
                )
            )
            updated = run([poly, "hooks", "update"], root, environment)
            self.assertEqual(updated.returncode, 0, updated.stdout + updated.stderr)
            path = root / "poly-hooks.lock"
            body = path.read_text()
            locked = tomllib.loads(body)["sources"][0]
            self.assertEqual(locked["revision"], revision)
            decoy = root / "decoy"
            decoy.mkdir()
            (decoy / "poly-hooks.toml").write_text(fixtures.CATALOGUE.replace('run = "ai-rulez"', 'run = "false"'))
            body = body.replace(json.dumps(locked["path"]), json.dumps(str(decoy)))
            body = body.replace("version = 1\n", "version = 1\nfuture_header=123\n")
            path.write_text(body + '\nfuture_source="accepted"\n')
            actual = execute_hook(poly, root, environment, commit=False)
            self.assertEqual(actual.returncode, 0, actual.stdout + actual.stderr)
            self.assertEqual((root / "trace").read_text().splitlines(), ["ai-rulez|validate --no-local"])

    def test_malformed_locks_fail_in_actual_poly_and_the_public_runtime_cli(self) -> None:
        poly = shutil.which("poly")
        self.assertIsNotNone(poly)
        reports = Path(__file__).resolve().parents[3] / "reports"
        with tempfile.TemporaryDirectory(dir=reports) as directory:
            root = Path(directory)
            environment = sandbox(root, ["system"], {"ai-rulez": "5.9.8"})
            original_config = (root / "poly.toml").read_text()
            initialize(root, environment)
            fixtures.configure(root)
            cases = fixtures.invalid_locks((root / "poly-hooks.lock").read_text())
            for name, body in cases:
                with self.subTest(boundary=name):
                    (root / "trace").unlink(missing_ok=True)
                    (root / "poly.toml").write_text(original_config)
                    (root / "poly-hooks.lock").write_text(body)
                    actual = execute_hook(poly, root, environment, commit=False)
                    self.assertNotEqual(actual.returncode, 0, f"Poly accepted {name}")
                    self.assertIn("poly-hooks.lock", actual.stdout + actual.stderr)
                    self.assertFalse((root / "trace").exists(), "invalid lock must not execute a hook")
                    fixtures.configure(root)
                    (root / "poly-hooks.lock").write_text(body)
                    checked = run(
                        [sys.executable, "-c", PROBE, str(Path(__file__).parent), str(root)], root, environment
                    )
                    self.assertEqual(checked.returncode, 1, f"public runtime CLI accepted {name}")
                    self.assertIn("error:", checked.stderr)

    def test_malformed_metadata_is_rejected_by_poly_and_the_probe(self) -> None:
        poly = shutil.which("poly")
        self.assertIsNotNone(poly)
        reports = Path(__file__).resolve().parents[3] / "reports"
        for kind in ("bool-version", "source-field", "preference-field"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory(dir=reports) as directory:
                root = Path(directory)
                environment = sandbox(root, ["system"], {"ai-rulez": "5.9.8"})
                if kind == "bool-version":
                    path = root / "producer/poly-hooks.toml"
                    path.write_text(path.read_text().replace("version = 1", "version = true"))
                else:
                    path = root / ("poly.toml" if kind == "source-field" else "poly.local.toml")
                    path.write_text(path.read_text() + 'unreviewed = "field"\n')
                initialize(root, environment)
                actual = execute_hook(poly, root, environment, commit=False)
                self.assertNotEqual(actual.returncode, 0)
                diagnostic = actual.stdout + actual.stderr
                self.assertIn("boolean" if kind == "bool-version" else "unknown field", diagnostic)
                self.assertFalse((root / "trace").exists(), "invalid metadata must fail before running the AI hook")
                if kind == "bool-version":
                    with self.assertRaisesRegex(ValueError, "catalog version"):
                        hook_runtime.select(["ai-rulez-validate"], tomllib.loads(path.read_text()), ["system"], root)
                elif kind == "preference-field":
                    with self.assertRaisesRegex(ValueError, "unknown hook_preferences field"):
                        hook_runtime.preferences(root)
                else:
                    fixtures.configure(root)
                    path.write_text(path.read_text() + 'unreviewed = "field"\n')
                    with self.assertRaisesRegex(ValueError, "unknown configured hook source field"):
                        hook_runtime.catalogue(root)

    def test_default_isolated_normal_hook_uses_its_observed_snapshot_root(self) -> None:
        poly = shutil.which("poly")
        self.assertIsNotNone(poly)
        reports = Path(__file__).resolve().parents[3] / "reports"
        with tempfile.TemporaryDirectory(dir=reports) as directory:
            root = Path(directory)
            consumer, reviewer = root / "consumer", root / "reviewer"
            consumer.mkdir()
            reviewer.mkdir()
            environment = sandbox(consumer, ["system"], {"ai-rulez": "5.9.8"})
            (consumer / "bin/ai-rulez").write_text(
                "#!/bin/sh\nversion=5.9.8\nif [ -f probe.txt ]; then version=5.9.6; fi\n"
                'printf "%s|%s|%s\\n" "$PWD" "$*" "$version" >> "$PROVIDER_TRACE"\n'
                'printf "ai-rulez version %s\\n" "$version"\n'
            )
            initialize(consumer, environment)
            actual = execute_hook(poly, consumer, environment, commit=True)
            self.assertEqual(actual.returncode, 0, actual.stdout + actual.stderr)
            trace = Path(environment["PROVIDER_TRACE"])
            records = trace.read_text().splitlines()
            self.assertEqual(len(records), 1)
            observed_root = Path(records[0].split("|", 1)[0])
            self.assertNotEqual(observed_root, consumer.resolve())
            self.assertEqual((observed_root / "probe.txt").read_text(), "real tracked fixture\n")
            self.assertEqual(records[0], f"{observed_root}|validate --no-local|5.9.6")
            fixtures.configure(consumer)
            arguments = [sys.executable, "-c", PROBE, str(Path(__file__).parent), str(consumer), str(observed_root)]
            checked = run(arguments, reviewer, environment)
            self.assertEqual(checked.returncode, 1, checked.stdout + checked.stderr)
            self.assertIn("selected system ai-rulez 5.9.6, npm latest is 5.9.8", checked.stderr)
            self.assertEqual(trace.read_text().splitlines(), [records[0], f"{observed_root}|--version|5.9.6"])

    def test_normal_hook_and_probe_share_cwd_and_relative_path_resolution(self) -> None:
        poly = shutil.which("poly")
        self.assertIsNotNone(poly)
        reports = Path(__file__).resolve().parents[3] / "reports"
        for relative in (False, True):
            with self.subTest(relative_path=relative), tempfile.TemporaryDirectory(dir=reports) as directory:
                root = Path(directory)
                consumer, reviewer = root / "consumer", root / "reviewer"
                consumer.mkdir()
                reviewer.mkdir()
                environment = sandbox(consumer, ["system"], {"ai-rulez": "5.9.8"})
                config = consumer / "poly.toml"
                config.write_text(config.read_text().replace("[hooks]\n", "[hooks]\nisolate=false\n"))
                (reviewer / "bin").mkdir()
                command = consumer / "bin/ai-rulez"
                command.write_text(
                    "#!/bin/sh\nversion=5.9.8\n"
                    f'if [ "$PWD" = {shlex.quote(str(consumer.resolve()))} ]; then version=5.9.6; fi\n'
                    'printf "%s|%s|%s\\n" "$PWD" "$*" "$version" >> "$PROVIDER_TRACE"\n'
                    'printf "ai-rulez version %s\\n" "$version"\n'
                )
                if relative:
                    environment["PATH"] = "bin"
                initialize(consumer, environment)
                actual = execute_hook(poly, consumer, environment, commit=True)
                self.assertEqual(actual.returncode, 0, actual.stdout + actual.stderr)
                trace = Path(environment["PROVIDER_TRACE"])
                self.assertEqual(trace.read_text().splitlines(), [f"{consumer.resolve()}|validate --no-local|5.9.6"])
                fixtures.configure(consumer)
                arguments = [sys.executable, "-c", PROBE, str(Path(__file__).parent), str(consumer)]
                checked = run(arguments, reviewer, environment)
                self.assertEqual(checked.returncode, 1, "probe must reject the stale consumer-root runtime")
                self.assertIn("selected system ai-rulez 5.9.6, npm latest is 5.9.8", checked.stderr)
                self.assertEqual(
                    trace.read_text().splitlines(),
                    [f"{consumer.resolve()}|validate --no-local|5.9.6", f"{consumer.resolve()}|--version|5.9.6"],
                )

    def test_ci_installs_committed_poly_for_the_integration_tests(self) -> None:
        root = Path(__file__).resolve().parents[2]
        config = yaml.safe_load((root / ".github/workflows/ai-rulez-validation.yml").read_text())
        steps = config["jobs"]["context-harness"]["steps"]
        setup = [step for step in steps if step.get("uses") == "xberg-io/actions/setup-mise@v1"]
        self.assertEqual(len(setup), 1)
        self.assertIn("github:Goldziher/poly", shlex.split(setup[0]["with"]["install-args"]))

    def compare(
        self, channels: list[str], versions: dict[str, str], channel: str, version: str, *, commit: bool = False
    ) -> None:
        poly = shutil.which("poly")
        self.assertIsNotNone(poly, "install the committed mise Poly tool before running integration tests")
        reports = Path(__file__).resolve().parents[3] / "reports"
        reports.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="hook-runtime-poly-", dir=reports) as directory:
            root = Path(directory)
            environment = sandbox(root, channels, versions)
            expected = tomllib.loads((Path(__file__).resolve().parents[2] / "mise.toml").read_text())["tools"][
                "github:Goldziher/poly"
            ]
            identity = run([poly, "--version"], root, environment)
            self.assertEqual(identity.returncode, 0, identity.stderr)
            self.assertEqual(identity.stdout.split()[:2], ["poly", expected])
            initialize(root, environment)
            result = execute_hook(poly, root, environment, commit=commit)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            expected = "npx" if channel == "npm" else "ai-rulez"
            prefix = "-y ai-rulez@latest " if channel == "npm" else ""
            self.assertEqual((root / "trace").read_text().splitlines(), [f"{expected}|{prefix}validate --no-local"])
            with patch.dict(os.environ, environment, clear=True):
                selected = hook_runtime.select(
                    ["ai-rulez-validate"], tomllib.loads(fixtures.CATALOGUE), hook_runtime.preferences(root)
                )
                measured = hook_runtime.measure(selected[0][2])
            self.assertEqual([(item[0], item[1]) for item in selected], [("ai-rulez-validate", channel)])
            self.assertEqual(measured, version)
            self.assertEqual(
                (root / "trace").read_text().splitlines(),
                [f"{expected}|{prefix}validate --no-local", f"{expected}|{prefix}--version"],
            )

    def test_npm_first_selects_npm_even_when_system_is_stale(self) -> None:
        self.compare(["npm", "system"], {"ai-rulez": "5.9.6", "npx": "5.9.8"}, "npm", "5.9.8")

    def test_system_first_does_not_silently_upgrade_through_npm(self) -> None:
        self.compare(["system", "npm"], {"ai-rulez": "5.9.6", "npx": "5.9.8"}, "system", "5.9.6")

    def test_missing_npm_falls_back_to_the_current_system_cli(self) -> None:
        self.compare(["npm", "system"], {"ai-rulez": "5.9.8"}, "system", "5.9.8")

    def test_system_only_uses_the_current_system_cli(self) -> None:
        self.compare(["system"], {"ai-rulez": "5.9.8", "npx": "5.9.8"}, "system", "5.9.8", commit=True)


if __name__ == "__main__":
    unittest.main()
