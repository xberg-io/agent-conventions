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

    def test_the_committed_map_matches_domains_toml(self) -> None:
        domains = tomllib.loads((ROOT / "tools/context-evals/domains.toml").read_text())
        committed = ROOT / tomllib.loads((ROOT / ".ai-rulez/config.toml").read_text())["exposure"]["areas_file"]
        self.assertEqual(committed.read_text(), areas.render(domains, "agent-conventions"))
        self.assertEqual(len(tomllib.loads(committed.read_text())["area"]), len(domains["domain"]))


if __name__ == "__main__":
    unittest.main()
