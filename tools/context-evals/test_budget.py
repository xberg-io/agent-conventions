"""Spending caps cover every paid runner and judge subprocess."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
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
            paid = budget.BudgetedExecute(path, 0.3, 0.2, execute, allow_soft_limits=True)
            paid(["claude", "-p", "test"], Path(tmp), {}, 1)
            self.assertEqual(calls[0][-2:], ["--max-budget-usd", "0.2"])
            resumed = budget.BudgetedExecute(path, 0.3, 0.2, execute, allow_soft_limits=True)
            with self.assertRaisesRegex(runner.RunnerError, "budget"):
                resumed(["claude", "-p", "test"], Path(tmp), {}, 1)
            self.assertEqual(len(calls), 1)
            self.assertAlmostEqual(resumed.spent(), 0.15)

    def test_missing_cost_keeps_reservation_and_aborts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paid = budget.BudgetedExecute(
                Path(tmp) / "budget.sqlite3",
                1,
                0.2,
                lambda *_args: runner.Completed(1, "", "auth failed"),
                allow_soft_limits=True,
            )
            with self.assertRaisesRegex(runner.RunnerError, "cost"):
                paid(["claude", "-p", "test"], Path(tmp), {}, 1)
            self.assertAlmostEqual(paid.spent(), 0.2)

    def test_turn_limit_failure_is_returned_for_case_scoring(self) -> None:
        result = runner.Completed(
            1, json.dumps({"total_cost_usd": 0.05, "is_error": True, "subtype": "error_max_turns"}), ""
        )
        with tempfile.TemporaryDirectory() as tmp:
            paid = budget.BudgetedExecute(
                Path(tmp) / "budget.sqlite3", 1, 0.2, lambda *_args: result, allow_soft_limits=True
            )
            self.assertEqual(paid(["claude", "-p", "test"], Path(tmp), {}, 1), result)
            self.assertAlmostEqual(paid.spent(), 0.05)

    def test_hard_ceiling_mode_refuses_unverified_cli_before_execution(self) -> None:
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            paid = budget.BudgetedExecute(Path(tmp) / "budget.sqlite3", 1, 0.2, lambda *args: calls.append(args))
            with self.assertRaisesRegex(runner.RunnerError, "soft"):
                paid(["claude", "-p", "test"], Path(tmp), {}, 1)
            self.assertEqual(calls, [])
            self.assertEqual(paid.spent(), 0)

    def test_soft_overrun_records_actual_cost_and_stops_the_whole_round(self) -> None:
        calls = []

        def execute(*_args):
            calls.append(1)
            return runner.Completed(
                1, json.dumps({"total_cost_usd": 0.0735, "is_error": True, "subtype": "error_max_budget_usd"}), ""
            )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "budget.sqlite3"
            paid = budget.BudgetedExecute(path, 1, 0.05, execute, allow_soft_limits=True)
            with self.assertRaises(runner.RunnerError):
                paid(["claude", "-p", "test"], Path(tmp), {}, 1)
            another = budget.BudgetedExecute(path, 1, 0.05, execute, allow_soft_limits=True)
            with self.assertRaisesRegex(runner.RunnerError, "stopped"):
                another(["claude", "-p", "test"], Path(tmp), {}, 1)
            self.assertEqual(calls, [1])
            self.assertAlmostEqual(another.spent(), 0.0735)

    def test_concurrent_initialization_has_one_immutable_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "budget.sqlite3"
            barrier = Barrier(2)

            def initialize(total):
                barrier.wait()
                try:
                    budget.BudgetedExecute(path, total, 0.05, lambda *_args: None)
                    return True
                except runner.RunnerError:
                    return False

            with ThreadPoolExecutor(max_workers=2) as pool:
                result = list(pool.map(initialize, [1, 2]))
            self.assertEqual(sorted(result), [False, True])
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM round_limits").fetchone()[0], 1)

    def test_non_model_commands_are_not_charged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paid = budget.BudgetedExecute(
                Path(tmp) / "budget.sqlite3",
                1,
                0.2,
                lambda *_args: runner.Completed(0, "generated", ""),
            )
            self.assertEqual(paid(["ai-rulez", "generate"], Path(tmp), {}, 1).stdout, "generated")
            self.assertEqual(paid.spent(), 0)


if __name__ == "__main__":
    unittest.main()
