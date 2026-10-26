"""Tests for decide.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import decide
from loop_fixtures import RUN_META, rec, scored

TARGET = frozenset(f"t{i}" for i in range(10))


def run(name: str, target: dict, other: dict | None = None, tokens: int = 1000, **meta: object) -> decide.Run:
    records = []
    for case, scores in target.items():
        records += scored(case, scores, domain="d", cluster=f"k-{case}", start_tokens=tokens)
    for case, scores in (other or {}).items():
        records += scored(case, scores, domain="e", cluster=f"k-{case}", must_use_hit=["s"], start_tokens=tokens)
    return decide.Run(name, {**RUN_META, **meta}, records)


def control() -> decide.Run:
    return run("control", {c: [0.25] * 3 for c in TARGET}, {f"o{i}": [1.0] * 3 for i in range(10)})


def winner(name: str = "win", tokens: int = 1000) -> decide.Run:
    other = {f"o{i}": [1.0] * 3 for i in range(10)} | {"o0": [0.75] * 3}
    return run(name, {c: [1.0] * 3 for c in TARGET}, other, tokens=tokens)


class DecideTest(unittest.TestCase):
    def test_clear_win_is_accepted_and_lists_regressed_cases(self) -> None:
        [result] = decide.decide(control(), [winner()], [TARGET])
        self.assertEqual(result.decision, "accept")
        self.assertTrue(result.holm_significant)
        target = result.metrics["primary_target"]
        self.assertEqual((target.mean, target.lo, target.hi), (0.75, 0.75, 0.75))
        self.assertAlmostEqual(result.metrics["primary_overall"].mean, 0.3625)
        self.assertEqual(result.metrics["answer_leak"].mean, 0.0)
        self.assertEqual(result.metrics["recall_other"].cases, 10)
        self.assertIsNone(result.metrics["under_ask"])
        self.assertEqual(result.regressed, [("o0", -0.25)])
        self.assertEqual(result.start_tokens, {"control": 1000, "arm": 1000, "growth": 0.0})

    def test_win_that_regresses_a_guardrail_is_rejected(self) -> None:
        arm = winner()
        for record in arm.records:
            if record.domain == "e":
                record.answer_leaks = ["other-product"]
        [result] = decide.decide(control(), [arm], [TARGET])
        self.assertEqual(result.decision, "reject")
        self.assertEqual(result.metrics["answer_leak"].mean, -0.5)
        self.assertEqual(len(result.reasons), 1)
        self.assertTrue(result.reasons[0].startswith("answer_leak: not non-inferior (lower bound -"))

    def test_placebo_with_zero_effect_is_rejected(self) -> None:
        placebo = control()
        placebo.name = "placebo"
        [result] = decide.decide(control(), [placebo], [TARGET])
        self.assertEqual(result.decision, "reject")
        self.assertEqual(result.reasons, ["primary_target: no improvement (mean +0.0000)"])
        self.assertEqual(result.regressed, [])

    def test_arm_over_the_start_token_budget_is_rejected(self) -> None:
        [result] = decide.decide(control(), [winner(tokens=1100)], [TARGET])
        self.assertEqual(result.decision, "reject")
        self.assertEqual(result.reasons, ["start tokens: +10.0% over the +5% budget"])

    def test_arm_over_the_absolute_cap_is_rejected(self) -> None:
        [result] = decide.decide(control(), [winner(tokens=1040)], [TARGET], decide.Rule(token_cap=1000))
        self.assertEqual(result.decision, "reject")
        self.assertEqual(result.reasons, ["start tokens: 1040 over the cap 1000"])

    def test_holm_turns_a_lone_marginal_win_into_reject(self) -> None:
        diffs = [0.25] * 6 + [-0.25] + [0.0] * 3
        base = run("control", {f"t{i}": [0.5] for i in range(10)})
        marginal = run("marginal", {f"t{i}": [0.5 + d] for i, d in enumerate(diffs)})
        [alone] = decide.decide(base, [marginal], [TARGET])
        self.assertEqual(alone.decision, "accept")
        self.assertEqual(alone.metrics["primary_target"].p_not_greater, 0.022)
        noops = [run(f"noop{i}", {f"t{j}": [0.5] for j in range(10)}) for i in range(2)]
        results = decide.decide(base, [marginal, *noops], [TARGET] * 3)
        self.assertEqual([r.decision for r in results], ["reject"] * 3)
        self.assertEqual(results[0].reasons, ["primary_target: not significant after Holm (p 0.0220)"])

    def test_underpowered_win_is_inconclusive_with_repeats_needed(self) -> None:
        diffs = [0.25] * 4 + [-0.25] * 2 + [0.0] * 4
        base = run("control", {f"t{i}": [0.5] for i in range(10)})
        noisy = run("noisy", {f"t{i}": [0.5 + d] for i, d in enumerate(diffs)})
        [result] = decide.decide(base, [noisy], [TARGET])
        self.assertEqual(result.decision, "inconclusive")
        self.assertEqual(result.repeats, 1.0)
        self.assertEqual(result.repeats_needed, 11)
        self.assertEqual(result.reasons[-1], "about 11 repeats needed")

    def test_refuses_runs_with_different_judge_or_rubric(self) -> None:
        arm = winner()
        arm.meta = {**arm.meta, "rubric_version": "r2"}
        with self.assertRaisesRegex(ValueError, "rubric_version"):
            decide.decide(control(), [arm], [TARGET])

    def test_primary_falls_back_to_binary_pass(self) -> None:
        self.assertEqual(decide.primary(rec("a", criteria={})), 1.0)
        self.assertEqual(decide.primary(rec("a", criteria={}, asked=True)), 0.0)
        self.assertEqual(decide.primary(rec("a", criteria={"x": True, "y": False, "z": None})), 0.5)

    def test_harness_errors_are_left_out(self) -> None:
        records = [rec("a", criteria={"x": False}, error="timeout"), rec("a", 1)]
        self.assertEqual(decide.per_case(records, decide.primary), {"a": [1.0]})

    def test_resolve_target(self) -> None:
        records = [rec("a", domain="d", cluster="k"), rec("b", domain="e", cluster="k"), rec("c", domain="e")]
        self.assertEqual(decide.resolve_target("k", records), {"a", "b"})
        self.assertEqual(decide.resolve_target("domain:e", records), {"b", "c"})
        self.assertEqual(decide.resolve_target("cases:a,c", records), {"a", "c"})
        with self.assertRaises(ValueError):
            decide.resolve_target("cluster:none", records)


class PlaceboTest(unittest.TestCase):
    def test_false_accept_rate_is_flagged_above_five_percent(self) -> None:
        report = decide.calibrate_placebo(["accept"] + ["reject"] * 9)
        self.assertEqual(report, {"placebos": 10, "accepted": 1, "rate": 0.1, "flagged": True})
        self.assertFalse(decide.calibrate_placebo(["reject"] * 19 + ["inconclusive"])["flagged"])

    def test_unknown_decision_is_an_error(self) -> None:
        with self.assertRaises(ValueError):
            decide.calibrate_placebo(["maybe"])


if __name__ == "__main__":
    unittest.main()
