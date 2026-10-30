"""Spending caps cover every paid runner and judge subprocess."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING

sys.path.insert(0, str(Path(__file__).parent))

import budget
import runner

if TYPE_CHECKING:
    from collections.abc import Mapping


class BudgetTest(unittest.TestCase):
    def test_actual_spend_is_shared_and_next_reservation_is_refused(self) -> None:
        calls = []

        def execute(argv: list[str], _cwd: Path, _env: Mapping[str, str], _timeout: float) -> runner.Completed:
            calls.append(argv)
            return runner.Completed(0, json.dumps({"total_cost_usd": 0.15}), "")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "budget.sqlite3"
            paid = budget.BoundedExecute(path, 0.3, 0.2, execute)
            paid(["claude", "-p", "test"], Path(tmp), {}, 1)
            self.assertEqual(calls[0][-2:], ["--max-budget-usd", "0.2"])
            resumed = budget.BoundedExecute(path, 0.3, 0.2, execute)
            with self.assertRaisesRegex(runner.RunnerError, "budget"):
                resumed(["claude", "-p", "test"], Path(tmp), {}, 1)
            self.assertEqual(len(calls), 1)
            self.assertAlmostEqual(resumed.spent(), 0.15)

    def test_missing_cost_keeps_reservation_and_aborts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paid = budget.BoundedExecute(
                Path(tmp) / "budget.sqlite3",
                1,
                0.2,
                lambda *_args: runner.Completed(1, "", "auth failed"),
            )
            with self.assertRaisesRegex(runner.RunnerError, "cost"):
                paid(["claude", "-p", "test"], Path(tmp), {}, 1)
            self.assertAlmostEqual(paid.spent(), 0.2)

    def test_turn_limit_failure_is_returned_for_case_scoring(self) -> None:
        result = runner.Completed(
            1, json.dumps({"total_cost_usd": 0.05, "is_error": True, "subtype": "error_max_turns"}), ""
        )
        with tempfile.TemporaryDirectory() as tmp:
            paid = budget.BoundedExecute(Path(tmp) / "budget.sqlite3", 1, 0.2, lambda *_args: result)
            self.assertEqual(paid(["claude", "-p", "test"], Path(tmp), {}, 1), result)
            self.assertAlmostEqual(paid.spent(), 0.05)

    def test_non_model_commands_are_not_charged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paid = budget.BoundedExecute(
                Path(tmp) / "budget.sqlite3",
                1,
                0.2,
                lambda *_args: runner.Completed(0, "generated", ""),
            )
            self.assertEqual(paid(["ai-rulez", "generate"], Path(tmp), {}, 1).stdout, "generated")
            self.assertEqual(paid.spent(), 0)


if __name__ == "__main__":
    unittest.main()
