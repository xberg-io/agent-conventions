"""Curated positive controls must satisfy their deterministic answer checks."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import cases
import harness
import judge

CURATED = {
    "sceptre-adr-reverse-decision",
    "sceptre-backend-seam-direct-ort",
    "sceptre-backend-seam-candle-architecture",
    "sceptre-code-style-config-precedence",
    "sceptre-code-style-stdout",
    "sceptre-crate-layout-flag-mapping",
    "sceptre-mcp-add-parameter",
    "sceptre-rust-checks-test-gate",
    "sceptre-neg-release",
}


class ReferenceControlsTest(unittest.TestCase):
    def test_curated_tune_references_match_every_expected_pattern(self) -> None:
        corpus = cases.load_corpus(harness.HERE / "cases", harness.load_domains(harness.HERE / "domains.toml"))
        selected = [case for case in corpus if case.id in CURATED]
        self.assertEqual(len(selected), 9)
        self.assertTrue(all(case.split == "tune" for case in selected))
        for case in selected:
            for pattern in case.expect:
                with self.subTest(case=case.id, pattern=pattern):
                    self.assertIsNotNone(re.search(pattern, judge.reference_answer(case)))


if __name__ == "__main__":
    unittest.main()
