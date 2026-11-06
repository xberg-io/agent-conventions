"""Probe sentinels distinguish listings from bodies and each harness layout."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import probe


class ProbeTest(unittest.TestCase):
    def test_codex_uses_agents_layout_and_separate_body_sentinel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            tokens = probe.plant(root, "src/lib.rs", preset="codex")
            self.assertIn(tokens["root"], (root / "AGENTS.md").read_text())
            self.assertIn(tokens["nested"], (root / "src/AGENTS.md").read_text())
            skill = (root / ".agents/skills/probe-skill/SKILL.md").read_text()
            self.assertIn(tokens["skillbody"], skill.split("---", 2)[2])
            self.assertNotIn(tokens["skillbody"], skill.split("---", 2)[1])

    def test_claude_distinguishes_path_gating_and_manual_skills(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            tokens = probe.plant(root, "src/lib.rs", preset="claude")
            self.assertIn(tokens["scoped"], (root / ".claude/rules/probe-scoped.md").read_text())
            self.assertIn("disable-model-invocation: true", (root / ".claude/skills/probe-manual/SKILL.md").read_text())
            self.assertIn(tokens["agent"], (root / ".claude/agents/probe-agent.md").read_text())

    def test_plants_one_distinct_sentinel_per_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "crates/a/src").mkdir(parents=True)
            (root / "crates/a/src/lib.rs").write_text("")
            tokens = probe.plant(root, "crates/a/src/lib.rs")
            self.assertEqual(len(set(tokens.values())), 10)
            self.assertTrue(all(probe.SENTINEL.fullmatch(t) for t in tokens.values()))
            self.assertIn('"crates/a/src/**"', (root / ".claude/rules/probe-scoped.md").read_text())
            self.assertIn(tokens["nested"], (root / "crates/a/src/CLAUDE.md").read_text())


if __name__ == "__main__":
    unittest.main()
