"""Shipping catalog and hook-only CI must exercise the optional distributed producer."""

import tempfile
import tomllib
import unittest
from pathlib import Path

import hook_fixture_commands as commands
import hook_preflight_fixtures as fixtures
import yaml

ROOT = Path(__file__).resolve().parents[2]


class ShippingProducerTest(unittest.TestCase):
    def test_shipping_manifest_defines_both_explicit_optional_hooks(self) -> None:
        manifest = ROOT / "poly-hooks.toml"
        self.assertTrue(manifest.is_file(), "the distributed producer must exist at the repository root")
        document = tomllib.loads(manifest.read_text())
        self.assertEqual(document["version"], 1)
        hooks = document["hooks"]
        self.assertEqual([hook["id"] for hook in hooks], ["ai-runtime-freshness", "ai-runtime-freshness-worktree"])
        self.assertEqual([hook.get("args", []) for hook in hooks], [[], ["--worktree"]])
        for hook in hooks:
            self.assertEqual(hook["stages"], ["pre-commit"])
            self.assertEqual((hook["workspace"], hook["always_run"], hook["pass_filenames"]), (True, True, False))
            self.assertEqual([path["channel"] for path in hook["paths"]], ["system", "npm"])
            self.assertEqual(
                [path["run"] for path in hook["paths"]],
                [commands.producer_python("tools/context-evals/hook_preflight.py")] * 2,
            )

    def test_real_fixture_producer_contains_the_exact_shipping_catalog_and_helpers(self) -> None:
        manifest = ROOT / "poly-hooks.toml"
        self.assertTrue(manifest.is_file(), "shipping catalog is required before testing its consumed bytes")
        with tempfile.TemporaryDirectory(dir=fixtures.fixture_parent()) as directory:
            root = Path(directory)
            environment = fixtures.poly_fixtures.sandbox(root, ["system"], {})
            producer, revision = fixtures.gate_producer(root, environment)
            self.assertRegex(revision, r"^[0-9a-f]{40}$")
            self.assertEqual((producer / "poly-hooks.toml").read_bytes(), manifest.read_bytes())
            for name in ("hook_context.py", "hook_runtime.py", "hook_preflight.py"):
                self.assertEqual(
                    (producer / "tools/context-evals" / name).read_bytes(), (fixtures.MODULES / name).read_bytes()
                )

    def test_hook_qualification_has_three_managed_legs_and_shipping_path_filters(self) -> None:
        workflow = yaml.safe_load((ROOT / ".github/workflows/ai-rulez-validation.yml").read_text())
        job = workflow["jobs"].get("hook-runtime")
        self.assertIsNotNone(job, "shipping hooks require a separate focused platform qualification job")
        self.assertEqual(job["strategy"]["matrix"]["os"], ["ubuntu-latest", "macos-latest", "windows-latest"])
        self.assertEqual(job["runs-on"], "${{ matrix.os }}")
        installs = [step for step in job["steps"] if step.get("uses") == "xberg-io/actions/setup-mise@v1"]
        self.assertEqual(len(installs), 1)
        self.assertEqual(installs[0]["with"]["install-args"].split(), ["python", "uv", "node", "github:Goldziher/poly"])
        self.assertEqual([step["run"] for step in job["steps"] if "run" in step], ["mise run context:hooks"])
        triggers = workflow.get("on", workflow.get(True))
        for event in ("push", "pull_request"):
            self.assertIn("poly-hooks.toml", triggers[event]["paths"])
            self.assertIn("tools/**", triggers[event]["paths"])
        task = tomllib.loads((ROOT / "mise.toml").read_text())["tasks"]["context:hooks"]["run"]
        self.assertIn("run_hook_tests.py", task)
        self.assertNotIn("harness.py", task)
