"""Tests for scoring.py."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import cases
import scoring
import testkit
import transcript
from records import SessionRecord, Usage

SKILL_CALL = (
    '{"type":"system","subtype":"init","cwd":"/work/xberg/crates/xberg"}\n'
    '{"type":"assistant","message":{"id":"m1","content":[{"type":"tool_use","id":"t","name":"Skill",'
    '"input":{"skill":"crawl-tuning"}}]}}\n'
    '{"type":"assistant","message":{"id":"m2","content":[{"type":"tool_use","id":"u","name":"Skill",'
    '"input":{"skill":"ocr-pipeline-and-quality"}}]}}\n'
    '{"type":"result","subtype":"success","result":"Tesseract at 300.","num_turns":3,"total_cost_usd":0.5}\n'
)


class ScoringTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.context = testkit.make_checkout(Path(self.tmp.name))
        self.domains = testkit.domains()
        self.cases = {c.id: c for c in cases.load_corpus(testkit.CASES, self.domains)}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def score(self, case_id: str, text: str, repeat: int = 0, **kw: object) -> SessionRecord:
        t = transcript.parse(text)
        return scoring.score(
            self.cases[case_id], t, kw.pop("domains", self.domains), self.context, run_id="r", repeat=repeat, **kw
        )

    def fixture(self, case_id: str, name: str, **kw: object) -> SessionRecord:
        return self.score(case_id, testkit.transcript_text(name), **kw)

    def test_clean_skill_session(self) -> None:
        r = self.fixture("xberg-ocr-dpi", "skill_used")
        self.assertEqual(
            (r.split, r.cluster, r.behaviour, r.asked), ("holdout", "ocr-pipeline-and-quality", "answer", False)
        )
        self.assertEqual(
            (r.skills_used, r.must_use_hit, r.must_use_missed, r.must_not_use_hit),
            (["ocr-pipeline-and-quality"], ["ocr-pipeline-and-quality"], [], []),
        )
        self.assertEqual((r.leaked_artifacts, r.answer_leaks, r.expect_pass), ([], [], True))
        self.assertEqual(r.criteria, {"names-dpi-default": None, "names-engine": None})
        self.assertEqual(
            (r.start_tokens, r.usage, r.cost_usd, r.turns, r.error), (12012, Usage(30, 3500, 21000, 220), 0.0421, 3, "")
        )
        self.assertEqual(len(r.loaded), 5)

    def test_foreign_scoped_rule_and_answer_terms_leak(self) -> None:
        r = self.fixture("xberg-fetch-location", "scoped_rule")
        self.assertEqual(r.leaked_artifacts, [".claude/rules/web-scoped.md"])
        self.assertEqual(r.answer_leaks, ["(?i)\\bcrawler\\b", "crawlberg:crawler"])
        self.assertEqual(r.expect_pass, True)

    def test_accept_list_covers_artifacts_and_answers(self) -> None:
        accept = [
            {"term": "crawler", "artifact": r"\.claude/rules/web-scoped\.md", "reason": "test"},
            {"term": "crawler", "artifact": "answer", "repo": "xberg", "reason": "test"},
        ]
        r = self.fixture("xberg-fetch-location", "scoped_rule", domains={**self.domains, "accept": accept})
        self.assertEqual((r.leaked_artifacts, r.answer_leaks), ([], ["(?i)\\bcrawler\\b"]))

    def test_forbidden_foreign_skill_hurts_precision(self) -> None:
        r = self.score("xberg-ocr-dpi", SKILL_CALL)
        self.assertEqual(r.skills_used, ["crawl-tuning", "ocr-pipeline-and-quality"])
        self.assertEqual((r.must_not_use_hit, r.leaked_artifacts), (["crawl-tuning"], ["skill:crawl-tuning"]))
        self.assertEqual(scoring.METRIC_BY_NAME["skill_precision"].value(r), 0.5)
        self.assertEqual(r.expect_pass, True)

    def test_no_usage_falls_back_to_the_static_estimate(self) -> None:
        r = self.score("xberg-ocr-dpi", SKILL_CALL)
        # root files 89 B + two skill listings 105 B = 194 B at the recorded calibration. ~keep
        self.assertEqual(r.start_tokens, 73)
        self.assertEqual((r.usage, r.turns, r.cost_usd), (Usage(), 3, 0.5))

    def test_asking_error_and_contamination(self) -> None:
        ask = self.fixture("xberg-dpi-ambiguous", "asking")
        self.assertEqual((ask.asked, ask.behaviour_ok, ask.expect_pass), (True, True, None))
        err = self.fixture("xberg-ocr-module", "error")
        self.assertEqual(
            (err.error, err.expect_pass, err.must_use_missed), ("error_max_turns", None, ["ocr-pipeline-and-quality"])
        )
        dirty = self.fixture("xberg-ocr-dpi", "contamination", run_dir="/runs/r1")
        self.assertEqual(dirty.error, "contaminated")
        self.assertEqual(dirty.contaminated, ["tools/context-evals/cases/xberg/xberg.yaml", "/runs/r1/transcripts"])
        timed_out = self.fixture("xberg-ocr-dpi", "skill_used", error="timeout")
        self.assertEqual((timed_out.error, timed_out.expect_pass), ("timeout", None))

    def test_record_round_trips_with_contamination(self) -> None:
        r = self.fixture("xberg-ocr-dpi", "contamination", run_dir="/runs/r1")
        self.assertEqual(SessionRecord.from_dict(json.loads(r.to_json())), r)

    def test_path_domains(self) -> None:
        self.assertEqual(scoring.path_domains("packages/python/x.py", self.domains), {"bindings"})
        self.assertEqual(scoring.path_domains("crates/foo-ffi/src/lib.rs", self.domains), {"bindings"})
        self.assertEqual(scoring.path_domains("Dockerfile", self.domains), {"infrastructure"})
        self.assertEqual(scoring.path_domains("tools/e2e-generator/a.py", self.domains), {"e2e-generator"})
        self.assertEqual(scoring.path_domains("crates/xberg/src/lib.rs", self.domains), set())

    def test_foreign_path_read_leaks_for_a_repo_that_does_not_own_it(self) -> None:
        text = (
            '{"type":"system","subtype":"init","cwd":"/work/xberg/crates/xberg"}\n'
            '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t","name":"Read",'
            '"input":{"file_path":"/work/xberg/charts/x/values.yaml"}}]}}\n'
            '{"type":"result","subtype":"success","result":"ok"}\n'
        )
        self.assertEqual(self.score("xberg-ocr-dpi", text).leaked_artifacts, [])
        sceptre = {**self.domains, "repos": {**self.domains["repos"], "xberg": {"domains": ["xberg"]}}}
        self.assertEqual(self.score("xberg-ocr-dpi", text, domains=sceptre).leaked_artifacts, ["charts/x/values.yaml"])

    def test_aggregate_metrics_per_domain_and_overall(self) -> None:
        records = [
            self.fixture("xberg-ocr-dpi", "skill_used"),
            self.fixture("xberg-ocr-dpi", "skill_used", repeat=1),
            self.fixture("xberg-ocr-module", "nested_claude_md"),
            self.fixture("xberg-ocr-module", "error", repeat=1),
            self.fixture("xberg-fetch-location", "scoped_rule"),
            self.fixture("xberg-dpi-ambiguous", "asking"),
        ]
        records[0].criteria = {"names-dpi-default": True, "names-engine": False}
        summary = scoring.aggregate(records)
        overall = summary["overall"]
        self.assertEqual((overall["sessions"], overall["errors"]), (6, 1))
        m = overall["metrics"]
        # recall: ocr-dpi 1.0, ocr-module 0.0 (error repeat dropped) -> mean 0.5 over two cases in one cluster
        self.assertEqual(
            (m["skill_recall"]["mean"], m["skill_recall"]["cases"], m["skill_recall"]["clusters"]), (0.5, 2, 1)
        )
        self.assertEqual(m["skill_precision"]["mean"], 1.0)
        # leak: fetch-location leaks; three clean cases -> 1/4
        self.assertEqual(m["leak_rate"]["mean"], 0.25)
        self.assertEqual(m["answer_leak_rate"]["mean"], 0.25)
        self.assertEqual((m["over_ask_rate"]["mean"], m["under_ask_rate"]["mean"]), (0.0, 0.0))
        self.assertEqual((m["criteria_pass_rate"]["mean"], m["criteria_pass_rate"]["sessions"]), (0.5, 1))
        self.assertEqual(m["expect_pass_rate"]["mean"], 1.0)
        self.assertEqual(list(summary["domains"]), ["xberg"])
        self.assertEqual(summary["domains"]["xberg"], overall)

    def test_metric_without_values_is_none(self) -> None:
        r = self.fixture("xberg-dpi-ambiguous", "asking")
        self.assertIsNone(scoring.summarise([r])["metrics"]["skill_recall"])


if __name__ == "__main__":
    unittest.main()
