"""The ai-rulez area map is rendered from domains.toml, so the taxonomy has one source."""

from __future__ import annotations

import sys
import tomllib
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import areas

ROOT = Path(__file__).resolve().parents[2]
DOMAINS = {
    "domain": {
        "billing": {"owner": "@team/billing", "paths": ["billing/"], "terms": ["invoice", "ledger_sync"]},
        "search": {"owner": "@team/search", "terms": ["ranker"]},
    },
    "repos": {"billing": {"domains": ["billing"]}, "tooling": {"domains": []}},
}


class AreasTest(unittest.TestCase):
    def test_an_owned_domain_is_shared_and_every_other_domain_leaks(self) -> None:
        rendered = tomllib.loads(areas.render(DOMAINS, "billing"))
        self.assertEqual(
            rendered["area"],
            [
                {"name": "billing", "owner": "@team/billing", "terms": ["invoice", "ledger_sync"], "shared": True},
                {"name": "search", "owner": "@team/search", "terms": ["ranker"], "shared": False},
            ],
        )
        self.assertEqual(
            [area["shared"] for area in tomllib.loads(areas.render(DOMAINS, "tooling"))["area"]], [False, False]
        )

    def test_rejects_an_unlisted_repo_and_an_undefined_owned_domain(self) -> None:
        with self.assertRaisesRegex(ValueError, "not listed"):
            areas.render(DOMAINS, "missing")
        broken = {**DOMAINS, "repos": {"billing": {"domains": ["billing", "ghost"]}}}
        with self.assertRaisesRegex(ValueError, "ghost"):
            areas.render(broken, "billing")

    def test_an_area_excludes_the_compounds_that_contain_its_terms(self) -> None:
        domains = {
            "names": ["invoice-io", "invoicer"],
            "domain": {
                "billing": {"terms": ["invoice"]},
                "pro": {"terms": ["invoice-pro"]},
                "search": {"terms": ["ranker"]},
            },
            "repos": {"tooling": {"domains": []}},
        }
        rendered = {area["name"]: area for area in tomllib.loads(areas.render(domains, "tooling"))["area"]}
        self.assertEqual(rendered["billing"]["exclude"], ["invoice-io", "invoice-pro"])
        self.assertNotIn("exclude", rendered["pro"])
        self.assertNotIn("exclude", rendered["search"])

    def test_acceptances_are_rendered_where_they_hold(self) -> None:
        domains = {
            **DOMAINS,
            "accept": [
                {"term": "ranker", "repo": "billing", "reason": "Ours too."},
                {"term": "ranker", "repo": "tooling", "reason": "Not this repo."},
                {"term": "invoice", "artifact": "skill:brand", "harnesses": ["codex"], "reason": "Codex lists it."},
                {"term": "invoice", "artifact": "agent:rev", "reason": "The\n  reviewer."},
            ],
        }
        claude = tomllib.loads(areas.render(domains, "billing"))["accept"]
        self.assertEqual(
            claude,
            [
                {"term": "ranker", "path": "**", "reason": "Ours too."},
                {"term": "invoice", "path": ".claude/agents/rev.md", "reason": "The reviewer."},
            ],
        )
        codex = tomllib.loads(areas.render(domains, "billing", "codex"))["accept"]
        self.assertEqual(
            [entry["path"] for entry in codex], ["**", ".agents/skills/brand/SKILL.md", ".codex/agents/rev.toml"]
        )
        self.assertNotIn("accept", tomllib.loads(areas.render(DOMAINS, "billing")))

    def test_rejects_a_pattern_artifact_a_reasonless_acceptance_and_an_unknown_harness(self) -> None:
        with self.assertRaisesRegex(ValueError, "pattern"):
            areas.render({**DOMAINS, "accept": [{"term": "x", "artifact": "skill:.*", "reason": "r"}]}, "billing")
        with self.assertRaisesRegex(ValueError, "reason"):
            areas.render({**DOMAINS, "accept": [{"term": "x"}]}, "billing")
        with self.assertRaisesRegex(ValueError, "harness"):
            areas.render(DOMAINS, "billing", "cursor")

    def test_the_committed_map_matches_domains_toml(self) -> None:
        domains = tomllib.loads((ROOT / "tools/context-evals/domains.toml").read_text())
        committed = ROOT / tomllib.loads((ROOT / ".ai-rulez/config.toml").read_text())["exposure"]["areas_file"]
        self.assertEqual(committed.read_text(), areas.render(domains, "agent-conventions"))
        self.assertTrue(any(area["terms"] for area in tomllib.loads(committed.read_text())["area"]))


if __name__ == "__main__":
    unittest.main()
