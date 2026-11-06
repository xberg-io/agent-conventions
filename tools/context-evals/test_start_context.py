"""Tests for start_context.py, the eval harness's static model of a Claude Code session start."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import start_context


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class StartContextTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_shim_claude_md_counts_agents_md_without_comments(self) -> None:
        write(self.repo, "CLAUDE.md", "<!-- banner -->\n@AGENTS.md\n")
        agents = "# repo\n\n## Rules\n\n### one\n\nx\n"
        write(self.repo, "AGENTS.md", agents)
        report = start_context.claude(self.repo)
        instructions = {i.path: i.bytes for i in report.items if i.kind == "instructions"}
        self.assertEqual(instructions, {"CLAUDE.md": len("\n@AGENTS.md\n"), "AGENTS.md": len(agents)})
        self.assertEqual(report.start_tokens(), round(sum(instructions.values()) / start_context.BYTES_PER_TOKEN))

    def test_standalone_claude_md_ignores_agents_md(self) -> None:
        write(self.repo, "CLAUDE.md", "# repo\n")
        write(self.repo, "AGENTS.md", "# other\n")
        report = start_context.claude(self.repo)
        self.assertEqual([i.path for i in report.items if i.kind == "instructions"], ["CLAUDE.md"])

    def test_gated_rules_and_gated_or_user_only_skills_cost_nothing_at_start(self) -> None:
        write(self.repo, "CLAUDE.md", "")
        write(self.repo, ".claude/rules/scoped.md", "---\npaths:\n  - 'x/**'\n---\nbody\n")
        write(self.repo, ".claude/skills/a/SKILL.md", "---\nname: a\ndescription: open\n---\nbody\n")
        write(self.repo, ".claude/skills/b/SKILL.md", "---\nname: b\ndescription: gated\npaths:\n  - 'x/**'\n---\n")
        write(
            self.repo,
            ".claude/skills/c/SKILL.md",
            "---\nname: c\ndescription: manual\ndisable-model-invocation: true\n---\n",
        )
        report = start_context.claude(self.repo)
        self.assertEqual([(i.name, i.gated) for i in report.items if i.kind == "rule"], [("scoped", True)])
        self.assertEqual(report.start_tokens(), round(len("- a: open\n") / start_context.BYTES_PER_TOKEN))

    def test_terms_match_whole_words_and_acceptances_scope_by_artifact_and_repo(self) -> None:
        self.assertTrue(start_context.term_pattern("alpha").search("An Alpha-based run"))
        self.assertIsNone(start_context.term_pattern("alpha").search("alphabet"))
        accept = [{"term": "alpha", "artifact": "skill:brand", "repo": "app"}]
        self.assertTrue(start_context.is_accepted(accept, "alpha", "skill:brand", "app"))
        self.assertFalse(start_context.is_accepted(accept, "alpha", "skill:brand", "other"))
        self.assertFalse(start_context.is_accepted(accept, "alpha", "CLAUDE.md", "app"))


if __name__ == "__main__":
    unittest.main()
