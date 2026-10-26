"""Tests for holdout.py."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import holdout
from decide import Run
from loop_fixtures import RUN_META, scored


def accepted(n: int, round_: int = 1) -> list[dict]:
    return [{"round": round_, "decision": "accept", "arm_kind": "change"} for _ in range(n)]


def holdout_run(ref: str, score: float, split: str = "holdout") -> Run:
    records = []
    for i in range(10):
        records += scored(f"h{i}", [score] * 2, cluster=f"k{i}", split=split)
    return Run(ref, {**RUN_META, "ref": ref}, records)


class HoldoutTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "holdout.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def check(self, candidate: Run, entries: list[dict] | None = None, **kw: object) -> dict:
        tip = holdout_run("tip", 0.5)
        return holdout.checkpoint(self.state, entries or accepted(3), "h1", tip, candidate, **kw)

    def test_status_is_due_every_three_accepted_changes(self) -> None:
        self.assertFalse(holdout.status(self.state, accepted(2), "h1")["due"])
        status = holdout.status(self.state, accepted(3), "h1")
        self.assertEqual(
            {k: status[k] for k in ("reads", "cap", "remaining", "accepted", "due")},
            {"reads": 0, "cap": 5, "remaining": 5, "accepted": 3, "due": True},
        )

    def test_checkpoint_that_beats_the_tip_by_the_mde_is_progress(self) -> None:
        result = self.check(holdout_run("cand", 1.0))
        self.assertEqual(result["verdict"], "progress")
        self.assertEqual(result["interval"]["mean"], 0.5)
        state = json.loads(self.state.read_text())["h1"]
        self.assertEqual((state["reads"], state["tip"], state["accepted_at_last_read"]), (1, "cand", 3))
        self.assertFalse(holdout.status(self.state, accepted(5), "h1")["due"])
        self.assertTrue(holdout.status(self.state, accepted(6), "h1")["due"])

    def test_regression_signals_revert_and_keeps_the_tip(self) -> None:
        result = self.check(holdout_run("cand", 0.25))
        self.assertEqual(result["verdict"], "revert")
        self.assertEqual(json.loads(self.state.read_text())["h1"]["tip"], "tip")

    def test_no_change_is_a_plateau(self) -> None:
        self.assertEqual(self.check(holdout_run("cand", 0.5))["verdict"], "plateau")

    def test_reads_are_capped_per_harness_version(self) -> None:
        for _ in range(2):
            self.check(holdout_run("cand", 0.5), cap=2, force=True)
        with self.assertRaises(holdout.BudgetExhausted):
            self.check(holdout_run("cand", 0.5), cap=2, force=True)
        self.assertEqual(holdout.status(self.state, accepted(3), "h1", cap=2)["reads"], 2)
        self.assertEqual(holdout.status(self.state, accepted(3), "h2", cap=2)["remaining"], 2)

    def test_checkpoint_before_it_is_due_is_refused_without_a_read(self) -> None:
        with self.assertRaises(holdout.NotDue):
            self.check(holdout_run("cand", 1.0), accepted(1))
        self.assertFalse(self.state.exists())

    def test_tune_records_are_not_a_holdout_read(self) -> None:
        with self.assertRaisesRegex(ValueError, "holdout"):
            self.check(holdout_run("cand", 1.0, split="tune"))
        self.assertFalse(self.state.exists())


class StopTest(unittest.TestCase):
    def test_two_rounds_without_an_accept_stop(self) -> None:
        rejected = [{"round": r, "decision": "reject", "arm_kind": "change"} for r in (2, 3)]
        placebo = {"round": 3, "decision": "accept", "arm_kind": "placebo"}
        self.assertEqual(
            holdout.stop_condition(accepted(1) + rejected + [placebo]),
            (True, "rounds 2 and 3 accepted nothing"),
        )
        self.assertEqual(holdout.stop_condition(accepted(1) + rejected[:1]), (False, ""))

    def test_holdout_plateau_stops(self) -> None:
        checkpoints = [{"verdict": "progress"}, {"verdict": "plateau"}]
        self.assertEqual(holdout.stop_condition(accepted(1), checkpoints), (True, "holdout plateau"))
        self.assertEqual(holdout.stop_condition(accepted(1), checkpoints[:1]), (False, ""))


if __name__ == "__main__":
    unittest.main()
