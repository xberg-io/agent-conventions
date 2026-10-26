"""Tests for triage.py."""

from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import triage
from loop_fixtures import rec

FAIL = {"c1": False}


class FailureTest(unittest.TestCase):
    def test_each_failure_reason(self) -> None:
        cases = {
            "error": rec("a", error="timeout"),
            "behaviour": rec("a", asked=True),
            "must_use_missed": rec("a", must_use_missed=["s"]),
            "must_not_use_hit": rec("a", must_not_use_hit=["s"]),
            "answer_leaks": rec("a", answer_leaks=["x"]),
            "expect_failed": rec("a", expect_pass=False),
            "criteria": rec("a", criteria={"c1": True, "c2": False}),
        }
        for reason, record in cases.items():
            with self.subTest(reason=reason):
                self.assertEqual(triage.failure_reasons(record), [reason])

    def test_passing_session_has_no_reason(self) -> None:
        self.assertEqual(triage.failure_reasons(rec("a", expect_pass=True, criteria={"c1": True, "c2": None})), [])


class PreLabelTest(unittest.TestCase):
    def test_each_label(self) -> None:
        sandbox = {"proc": "procedure"}
        cases = {
            "harness": rec("a", error="crash", asked=True),
            "over_ask": rec("a", behaviour="answer", asked=True),
            "under_ask": rec("a", behaviour="ask", asked=False),
            "not_found": rec("a", must_use_missed=["s"]),
            "wrong_skill": rec("a", must_not_use_hit=["t"]),
            "answer_leak": rec("a", answer_leaks=["x"]),
            "sandbox_limit": rec("proc", expect_pass=False),
        }
        for label, record in cases.items():
            with self.subTest(label=label):
                self.assertEqual(triage.pre_labels(record, sandbox), [label])

    def test_used_skill_outside_must_use_is_wrong_skill(self) -> None:
        record = rec("a", skills_used=["s", "other"], must_use_hit=["s"])
        self.assertEqual(triage.pre_labels(record), ["wrong_skill"])
        self.assertEqual(triage.pre_labels(rec("a", skills_used=["other"])), [])

    def test_expect_failure_without_procedure_sandbox_is_unlabelled(self) -> None:
        self.assertEqual(triage.pre_labels(rec("a", expect_pass=False), {"a": "readonly"}), [])

    def test_harness_hides_other_labels(self) -> None:
        self.assertEqual(triage.pre_labels(rec("a", error="x", must_use_missed=["s"])), ["harness"])


class OchiaiTest(unittest.TestCase):
    def records(self) -> list:
        return [
            rec("s1", loaded=("skill:A", "rule:B"), criteria=FAIL),
            rec("s2", loaded=("skill:A",), criteria=FAIL),
            rec("s3", loaded=("rule:B",)),
            rec("s4", loaded=("skill:A", "rule:B")),
            rec("e1", domain="e", loaded=("rule:B",), criteria=FAIL),
            rec("h1", loaded=("rule:C",), error="timeout"),
        ]

    def test_ranking_is_per_domain(self) -> None:
        ranking = triage.suspiciousness(self.records())
        self.assertEqual(
            [(s.artifact, s.failed, s.passed) for s in ranking["d"]], [("skill:A", 2, 1), ("rule:B", 1, 2)]
        )
        self.assertAlmostEqual(ranking["d"][0].score, 2 / math.sqrt(6))
        self.assertAlmostEqual(ranking["d"][1].score, 1 / math.sqrt(6))
        self.assertEqual([(s.artifact, s.score) for s in ranking["e"]], [("rule:B", 1.0)])

    def test_harness_failures_stay_out_of_the_spectrum(self) -> None:
        ranking = triage.suspiciousness(self.records())
        self.assertNotIn("rule:C", [s.artifact for s in ranking["d"]])

    def test_clusters_key_on_cause_and_top_artifact(self) -> None:
        result = triage.triage(self.records())
        keys = {(c.cause, c.artifact): c.cases for c in result.clusters}
        self.assertEqual(
            keys,
            {
                ("unlabelled", "skill:A"): ["s1", "s2"],
                ("unlabelled", "rule:B"): ["e1"],
                ("harness", "-"): ["h1"],
            },
        )
        self.assertEqual(result.clusters[0].cause, "unlabelled")
        self.assertEqual(result.clusters[0].sessions, 2)

    def test_not_found_points_at_the_missed_skill(self) -> None:
        result = triage.triage([rec("a", loaded=("rule:B",), must_use_missed=["wanted"])])
        self.assertEqual((result.clusters[0].cause, result.clusters[0].artifact), ("not_found", "skill:wanted"))


class CoderTest(unittest.TestCase):
    def test_coder_codes_only_unlabelled_sessions(self) -> None:
        prompts: list[str] = []

        def coder(prompt: str) -> str:
            prompts.append(prompt)
            return "Wrong: the rule names a removed flag."

        records = [rec("a", criteria=FAIL, answer="uses --old"), rec("b", asked=True)]
        result = triage.triage(records, coder=coder)
        self.assertEqual(len(prompts), 1)
        self.assertIn("uses --old", prompts[0])
        self.assertIn("missing", prompts[0])
        self.assertEqual([s.cause for s in result.sessions], ["wrong", "over_ask"])
        self.assertEqual(result.sessions[0].coder_raw, "Wrong: the rule names a removed flag.")
        self.assertEqual(result.taxonomy_version, triage.TAXONOMY_VERSION)

    def test_unknown_code_stays_unlabelled(self) -> None:
        result = triage.triage([rec("a", criteria=FAIL)], coder=lambda _: "no idea")
        self.assertEqual(result.sessions[0].cause, "unlabelled")
        self.assertEqual(result.sessions[0].coder_raw, "no idea")

    def test_json_and_markdown(self) -> None:
        result = triage.triage([rec("a", criteria=FAIL, loaded=("skill:A",)), rec("b")])
        data = json.loads(result.to_json())
        self.assertEqual(data["taxonomy_version"], triage.TAXONOMY_VERSION)
        self.assertEqual(data["failing"], 1)
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["clusters"][0]["artifact"], "skill:A")
        self.assertIn("| unlabelled | skill:A | 1 | a |", result.to_markdown())


if __name__ == "__main__":
    unittest.main()
