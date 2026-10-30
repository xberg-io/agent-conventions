"""Consumer hooks must match the convention repository's hook source revision and lock."""

from __future__ import annotations

import fnmatch
import re
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))

import hook_pins


class HookPinsTest(unittest.TestCase):
    def test_hook_pin_only_changes_trigger_both_workflow_events(self) -> None:
        workflow = Path(__file__).resolve().parents[2] / ".github/workflows/ai-rulez-validation.yml"
        config = yaml.safe_load(workflow.read_text())
        events = config.get("on", config.get(True))
        for event in ("push", "pull_request"):
            patterns = events[event]["paths"]
            for filename in ("poly.toml", "poly-hooks.lock"):
                with self.subTest(event=event, filename=filename):
                    self.assertTrue(any(fnmatch.fnmatchcase(filename, pattern) for pattern in patterns))
            self.assertFalse(any(fnmatch.fnmatchcase("unrelated.txt", pattern) for pattern in patterns))

    def test_ai_rulez_is_unpinned_and_the_hook_source_floats_on_a_major_tag(self) -> None:
        root = Path(__file__).resolve().parents[2]
        self.assertNotIn("github:Goldziher/ai-rulez", tomllib.loads((root / "mise.toml").read_text())["tools"])
        config = yaml.safe_load((root / ".github/workflows/ai-rulez-validation.yml").read_text())
        steps = config["jobs"]["validate"]["steps"]
        setup = [step for step in steps if step.get("uses") == "xberg-io/actions/setup-ai-rulez@v1"]
        self.assertEqual(len(setup), 1)
        self.assertEqual((setup[0].get("with") or {}).get("ai-rulez-version", "latest"), "latest")
        revision = hook_pins.source(root / "poly.toml", "hooks")["revision"]
        self.assertRegex(revision, re.compile(r"^v[0-9]+$"))
        commit = hook_pins.source(root / "poly-hooks.lock", "sources")["revision"]
        self.assertEqual(hook_pins.check(root, revision, commit), [])

    def test_rejects_old_pin_stale_lock_and_empty_hook_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "poly.toml").write_text('[[hooks.sources]]\nid="ai-rulez"\nrevision="v5.3.0"\n')
            (repo / "poly-hooks.lock").write_text('[[sources]]\nid="ai-rulez"\nrevision="old"\n')
            errors = hook_pins.check(repo, "v5", "current")
            self.assertEqual(len(errors), 2)
            self.assertIn("v5.3.0", errors[0])
            self.assertIn("old", errors[1])
            (repo / "poly.toml").write_text("")
            self.assertIn("exactly one", hook_pins.check(repo, "v5", "current")[0])

    def test_accepts_current_pin_and_resolved_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "poly.toml").write_text('[[hooks.sources]]\nid="ai-rulez"\nrevision="v5"\n')
            (repo / "poly-hooks.lock").write_text('[[sources]]\nid="ai-rulez"\nrevision="current"\n')
            self.assertEqual(hook_pins.check(repo, "v5", "current"), [])


if __name__ == "__main__":
    unittest.main()
