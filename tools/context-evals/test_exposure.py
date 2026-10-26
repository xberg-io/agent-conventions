"""Tests for exposure.py. Run with `python3 -m unittest discover tools/context-evals`."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import exposure
import probe

DOMAINS = {
    "domain": {"alpha": {"terms": ["alpha-corpus"]}, "beta": {"terms": ["beta"]}},
    "repos": {"repo": {"domains": ["beta"]}},
}


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class ExposureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_shim_claude_md_counts_agents_md_and_its_rules(self) -> None:
        write(self.repo, "CLAUDE.md", "<!-- banner -->\n@AGENTS.md\n")
        write(self.repo, "AGENTS.md", "# repo\n\n## Rules\n\n### one\n\nx\n\n### two\n\ny\n\n## Context\n")
        report = exposure.claude(self.repo)
        self.assertEqual(report.summary()["inlined_rules"], 2)
        self.assertIn("AGENTS.md", [i.path for i in report.items if i.kind == "instructions"])
        root_bytes = sum(i.bytes for i in report.items if i.kind == "instructions")
        self.assertEqual(report.start_bytes(), root_bytes)

    def test_codex_agents_are_read_from_toml(self) -> None:
        write(self.repo, ".codex/agents/rev.toml", 'name = "rev"\ndescription = "Reviews diffs"\n')
        agents = [i for i in exposure.codex(self.repo).items if i.kind == "agent"]
        self.assertEqual([(a.name, a.description) for a in agents], [("rev", "Reviews diffs")])

    def test_codex_lists_path_gated_skills(self) -> None:
        write(self.repo, ".agents/skills/b/SKILL.md", "---\nname: b\ndescription: gated\npaths:\n  - 'x/**'\n---\n")
        summary = exposure.codex(self.repo).summary()
        self.assertEqual((summary["skills_gated"], summary["listing_bytes"]), (0, len("- b: gated\n")))

    def test_standalone_claude_md_ignores_agents_md(self) -> None:
        write(self.repo, "CLAUDE.md", "# repo\n\n## Rules\n\n### one\n\nx\n")
        write(self.repo, "AGENTS.md", "# repo\n\n## Rules\n\n### one\n\nx\n\n### scoped\n\ny\n")
        report = exposure.claude(self.repo)
        self.assertEqual(report.summary()["inlined_rules"], 1)

    def test_gated_and_user_only_skills_cost_nothing_at_start(self) -> None:
        write(self.repo, "CLAUDE.md", "")
        write(self.repo, ".claude/skills/a/SKILL.md", "---\nname: a\ndescription: open\n---\nbody\n")
        write(self.repo, ".claude/skills/b/SKILL.md", "---\nname: b\ndescription: gated\npaths:\n  - 'x/**'\n---\n")
        write(
            self.repo,
            ".claude/skills/c/SKILL.md",
            "---\nname: c\ndescription: manual\ndisable-model-invocation: true\n---\n",
        )
        summary = exposure.claude(self.repo).summary()
        self.assertEqual((summary["skills"], summary["skills_gated"], summary["skills_user_only"]), (3, 1, 1))
        self.assertEqual(summary["listing_bytes"], len("- a: open\n"))

    def test_leak_reports_foreign_terms_and_honours_accept_list(self) -> None:
        write(self.repo, "CLAUDE.md", "Use the alpha-corpus fixtures. beta is ours.\n")
        report = exposure.claude(self.repo)
        exposure.check_leaks(self.repo, report, DOMAINS, [])
        self.assertEqual([(leak.domain, leak.term) for leak in report.leaks], [("alpha", "alpha-corpus")])

        accepted = exposure.claude(self.repo)
        exposure.check_leaks(self.repo, accepted, DOMAINS, [{"term": "alpha-corpus", "reason": "test"}])
        self.assertEqual((len(accepted.leaks), len(accepted.accepted)), (0, 1))

    def test_term_inside_a_longer_name_is_not_a_leak(self) -> None:
        write(self.repo, "CLAUDE.md", "See alpha-corpus-tools and betamax.\n")
        report = exposure.claude(self.repo)
        exposure.check_leaks(self.repo, report, {**DOMAINS, "repos": {}}, [])
        self.assertEqual(report.leaks, [])

    def test_probe_plants_one_distinct_sentinel_per_artifact(self) -> None:
        write(self.repo, "crates/a/src/lib.rs", "")
        tokens = probe.plant(self.repo, "crates/a/src/lib.rs")
        self.assertEqual(len(set(tokens.values())), 5)
        self.assertTrue(all(probe.SENTINEL.fullmatch(t) for t in tokens.values()))
        scoped = (self.repo / ".claude/rules/probe-scoped.md").read_text()
        self.assertIn('"crates/a/src/**"', scoped)
        self.assertIn(tokens["nested"], (self.repo / "crates/a/src/CLAUDE.md").read_text())


if __name__ == "__main__":
    unittest.main()
