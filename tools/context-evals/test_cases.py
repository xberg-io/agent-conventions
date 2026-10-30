"""Tests for cases.py."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import cases
import testkit

GOOD = """- id: xberg-one
  domain: xberg
  repo: xberg
  cwd: crates/xberg
  prompt: "p"
  behaviour: answer
  sandbox: result
"""


class CasesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "cases"
        self.domains = testkit.domains()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write(self, rel: str, text: str) -> None:
        path = self.dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def errors(self) -> list[str]:
        with self.assertRaises(cases.CaseError) as ctx:
            cases.load_corpus(self.dir, self.domains)
        return ctx.exception.errors

    def test_fixture_corpus_loads_with_split_and_cluster(self) -> None:
        corpus = cases.load_corpus(testkit.CASES, self.domains)
        self.assertEqual(
            [(c.id, c.split, c.cluster) for c in corpus],
            [
                ("xberg-ocr-dpi", "holdout", "ocr-pipeline-and-quality"),
                ("xberg-ocr-module", "tune", "ocr-pipeline-and-quality"),
                ("xberg-fetch-location", "tune", "xberg"),
                ("xberg-dpi-ambiguous", "tune", "xberg"),
            ],
        )
        first = corpus[0]
        self.assertEqual(
            first.criteria[1], cases.Criterion("names-engine", "The answer names Tesseract as the OCR engine.")
        )
        self.assertEqual(first.reference.sources, ("crates/xberg/src/ocr/mod.rs",))

    def test_select_defaults_to_tune_and_holdout_is_explicit(self) -> None:
        corpus = cases.load_corpus(testkit.CASES, self.domains)
        self.assertEqual(len(cases.select(corpus)), 3)
        self.assertEqual([c.id for c in cases.select(corpus, split="holdout")], ["xberg-ocr-dpi"])
        self.assertEqual(
            [c.id for c in cases.select(corpus, split="all", pattern="xberg-ocr-*")],
            ["xberg-ocr-dpi", "xberg-ocr-module"],
        )
        self.assertEqual(cases.select(corpus, repo="crawlberg", split="all"), [])
        with self.assertRaises(ValueError):
            cases.select(corpus, split="everything")

    def test_schema_errors_are_all_reported(self) -> None:
        self.write(
            "xberg/xberg.yaml",
            GOOD
            + """- id: Bad_Id
  domain: xberg
  repo: xberg
  cwd: /abs
  prompt: "p"
  behaviour: maybe
  sandbox: live
  colour: blue
  expect: ["("]
  must_use: [a]
  must_not_use: [a]
  criteria:
    - {id: c-one, check: "x"}
    - {id: c-one, check: "y"}
""",
        )
        errors = [e.split(": ", 1)[1] for e in self.errors()]
        self.assertEqual(
            errors,
            [
                "unknown keys ['colour']",
                "id is not kebab-case",
                "behaviour 'maybe' not in ('answer', 'ask', 'either')",
                "sandbox 'live' not in ('result', 'procedure')",
                "cwd must be relative to the repository root",
                "duplicate criterion id 'c-one'",
                "expect pattern '(' does not compile: missing ), unterminated subpattern at position 0",
                "skills both required and forbidden: ['a']",
            ],
        )

    def test_missing_required_key_drops_the_case(self) -> None:
        self.write("xberg/xberg.yaml", "- id: xberg-x\n  domain: xberg\n")
        self.assertEqual(len(self.errors()), 1)
        self.assertIn(
            "missing or empty required keys ['repo', 'cwd', 'prompt', 'behaviour', 'sandbox']", self.errors()[0]
        )

    def test_corpus_checks_ids_taxonomy_and_layout(self) -> None:
        self.write("xberg/xberg.yaml", GOOD)
        self.write("xberg/other.yaml", GOOD.replace("domain: xberg", "domain: nowhere"))
        self.write(
            "crawlberg/crawlberg.yaml", GOOD.replace("repo: xberg", "repo: crawlberg").replace("xberg-one", "c-1")
        )
        errors = [e.split(":", 2)[2].strip() for e in self.errors()]
        self.assertEqual(
            errors,
            [
                "belongs in crawlberg/xberg.yaml",
                "domain 'nowhere' is not in domains.toml",
                "belongs in xberg/nowhere.yaml",
                "duplicate case id (also in " + str(self.dir / "xberg/other.yaml") + ")",
            ],
        )

    def test_checkout_checks_cwd_sources_and_generated_skills(self) -> None:
        repo = testkit.make_checkout(Path(self.tmp.name) / "repo")
        corpus = cases.load_corpus(testkit.CASES, self.domains)
        self.assertEqual(cases.check_checkout(corpus, repo), [])
        self.assertEqual(cases.generated_skills(repo), {"ocr-pipeline-and-quality", "crawl-tuning"})
        (repo / "crates/xberg/src/ocr/mod.rs").unlink()
        (repo / ".claude/skills/crawl-tuning/SKILL.md").unlink()
        errors = [e.split(": ", 1)[1] for e in cases.check_checkout(corpus, repo)]
        self.assertEqual(
            errors,
            [
                f"reference source 'crates/xberg/src/ocr/mod.rs' does not exist in {repo}",
                f"reference source 'crates/xberg/src/ocr/mod.rs' does not exist in {repo}",
            ],
        )

    def test_forbidden_skills_need_not_exist_in_consumer(self) -> None:
        repo = testkit.make_checkout(Path(self.tmp.name) / "repo")
        case = cases.load_corpus(testkit.CASES, self.domains)[0]
        case = cases.Case(**{**case.__dict__, "must_not_use": ("foreign-product-skill",)})
        self.assertEqual(cases.check_checkout([case], repo), [])

    def test_open_layout_skills_count_as_generated(self) -> None:
        repo = Path(self.tmp.name) / "open"
        (repo / ".agents/skills/x").mkdir(parents=True)
        (repo / ".agents/skills/x/SKILL.md").write_text("---\nname: named-x\ndescription: d\n---\n")
        self.assertEqual(cases.generated_skills(repo), {"named-x"})

    def test_corpus_hash_ignores_file_location_but_not_content(self) -> None:
        corpus = cases.load_corpus(testkit.CASES, self.domains)
        moved = [cases.Case(**{**c.__dict__, "file": "elsewhere"}) for c in reversed(corpus)]
        self.assertEqual(cases.corpus_hash(corpus), cases.corpus_hash(moved))
        changed = [cases.Case(**{**corpus[0].__dict__, "prompt": "other"}), *corpus[1:]]
        self.assertNotEqual(cases.corpus_hash(corpus), cases.corpus_hash(changed))


if __name__ == "__main__":
    unittest.main()
