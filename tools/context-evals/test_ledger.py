"""Tests for ledger.py."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import ledger


def entry(**overrides: object) -> dict:
    base = {
        "round": 1,
        "cluster": "not_found/skill:poly-lint-format",
        "hypothesis": "name the trigger words in the description",
        "arm_kind": "change",
        "artifacts": ["skill:poly-lint-format"],
        "patch_ref": "abc123",
        "base_ref": "def456",
        "stages": {"screen": {"primary_target": {"mean": 0.2, "lo": 0.1, "hi": 0.3}}},
        "decision": "accept",
        "cost_usd": 1.25,
        "model": "agent-model",
        "harness_version": "h1",
        "judge_version": "j1",
        "rubric_version": "r1",
        "taxonomy_version": "1",
        "timestamp": "2026-10-26T12:00:00+00:00",
    }
    return base | overrides


class LedgerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "ledger.jsonl"
        self.ledger = ledger.Ledger(self.path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_append_chains_entries(self) -> None:
        first = self.ledger.append(entry())
        second = self.ledger.append(entry(round=2, arm_kind="placebo", artifacts=[], decision="reject"))
        self.assertEqual(first["prev"], "")
        lines = self.path.read_text().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(second["prev"], ledger.digest(lines[0]))
        self.assertEqual([e["round"] for e in self.ledger.entries()], [1, 2])

    def test_timestamp_is_filled_in(self) -> None:
        data = entry()
        del data["timestamp"]
        self.assertRegex(self.ledger.append(data)["timestamp"], r"^\d{4}-\d\d-\d\dT")

    def test_history_returns_entries_for_one_artifact(self) -> None:
        self.ledger.append(entry(decision="reject"))
        self.ledger.append(entry(round=2, artifacts=["rule:other"]))
        history = self.ledger.history("skill:poly-lint-format")
        self.assertEqual([(e["round"], e["decision"]) for e in history], [(1, "reject")])

    def test_invalid_entries_are_refused_and_nothing_is_written(self) -> None:
        bad = {
            "missing field": {k: v for k, v in entry().items() if k != "hypothesis"},
            "unknown field": entry(note="x"),
            "arm kind": entry(arm_kind="tweak"),
            "decision": entry(decision="maybe"),
            "stage": entry(stages={"holdout": {}}),
            "round": entry(round=0),
            "boolean round": entry(round=True),
            "cost": entry(cost_usd=-1),
            "empty version": entry(judge_version=""),
            "artifacts": entry(artifacts="skill:x"),
            "caller prev": entry(prev=""),
        }
        for name, data in bad.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.ledger.append(data)
        self.assertFalse(self.path.exists())

    def test_round_cannot_go_back(self) -> None:
        self.ledger.append(entry(round=2))
        with self.assertRaisesRegex(ValueError, "round"):
            self.ledger.append(entry(round=1))

    def test_rewritten_history_is_refused(self) -> None:
        self.ledger.append(entry(decision="reject"))
        self.ledger.append(entry(round=2))
        lines = self.path.read_text().splitlines()
        first = json.loads(lines[0])
        first["decision"] = "accept"
        lines[0] = json.dumps(first, sort_keys=True)
        self.path.write_text("\n".join(lines) + "\n")
        before = self.path.read_text()
        with self.assertRaisesRegex(ValueError, "line 2"):
            self.ledger.append(entry(round=3))
        self.assertEqual(self.path.read_text(), before)

    def test_unparseable_line_is_refused(self) -> None:
        self.path.write_text("{not json\n")
        with self.assertRaisesRegex(ValueError, "line 1"):
            self.ledger.append(entry())

    def test_accepted_changes_skip_placebos(self) -> None:
        self.ledger.append(entry())
        self.ledger.append(entry(arm_kind="placebo", artifacts=[]))
        self.ledger.append(entry(arm_kind="deletion"))
        self.ledger.append(entry(decision="reject"))
        self.assertEqual(ledger.accepted_changes(self.ledger.entries()), 2)


if __name__ == "__main__":
    unittest.main()
