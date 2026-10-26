"""Tests for stats.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import stats


class StatsTest(unittest.TestCase):
    def test_holdout_split_is_deterministic_and_about_one_fifth(self) -> None:
        ids = [f"case-{i}" for i in range(2000)]
        share = sum(map(stats.is_holdout, ids)) / len(ids)
        self.assertAlmostEqual(share, 0.2, delta=0.03)
        self.assertEqual([stats.is_holdout(i) for i in ids[:50]], [stats.is_holdout(i) for i in ids[:50]])

    def test_clear_improvement_is_better(self) -> None:
        base = {f"c{i}": [0.0, 0.0, 0.0] for i in range(30)}
        arm = {f"c{i}": [1.0, 1.0, 0.0] for i in range(30)}
        clusters = {f"c{i}": f"k{i % 6}" for i in range(30)}
        iv = stats.paired_cluster_bootstrap(base, arm, clusters)
        self.assertAlmostEqual(iv.mean, 2 / 3)
        self.assertEqual(iv.verdict, "better")
        self.assertEqual((iv.clusters, iv.cases), (6, 30))
        self.assertEqual(iv.p_not_greater, 0.0)

    def test_noise_is_inconclusive_and_mirrors(self) -> None:
        base = {f"c{i}": [float(i % 2)] for i in range(20)}
        arm = {f"c{i}": [float((i + 1) % 2)] for i in range(20)}
        clusters = {f"c{i}": f"k{i}" for i in range(20)}
        iv = stats.paired_cluster_bootstrap(base, arm, clusters)
        self.assertEqual(iv.verdict, "inconclusive")
        self.assertGreater(iv.mde(), 0)
        worse = stats.paired_cluster_bootstrap(arm, {k: [0.0] for k in arm}, clusters)
        self.assertEqual(worse.verdict, "worse")

    def test_one_cluster_carries_its_whole_weight(self) -> None:
        # Ten improved cases in one cluster are one draw, so the interval stays wide.
        base = {f"c{i}": [0.0] for i in range(12)}
        arm = {**{f"c{i}": [1.0] for i in range(10)}, "c10": [0.0], "c11": [0.0]}
        clusters = {**{f"c{i}": "big" for i in range(10)}, "c10": "a", "c11": "b"}
        iv = stats.paired_cluster_bootstrap(base, arm, clusters)
        self.assertEqual(iv.verdict, "inconclusive")
        self.assertEqual(iv.lo, 0.0)

    def test_no_shared_case_is_an_error(self) -> None:
        with self.assertRaises(ValueError):
            stats.paired_cluster_bootstrap({"a": [1.0]}, {"b": [1.0]}, {})

    def test_holm_steps_down(self) -> None:
        self.assertEqual(stats.holm({"a": 0.01, "b": 0.02, "c": 0.04}), {"a": True, "b": True, "c": True})
        self.assertEqual(stats.holm({"a": 0.01, "b": 0.03, "c": 0.04}), {"a": True, "b": False, "c": False})
        self.assertEqual(stats.holm({"a": 0.03, "b": 0.5}), {"a": False, "b": False})

    def test_kappa_known_values(self) -> None:
        self.assertEqual(stats.cohen_kappa([True, False, True, False], [True, False, True, False]), 1.0)
        self.assertAlmostEqual(stats.cohen_kappa([True, True, False, False], [True, False, True, False]), 0.0)
        # 20 items: both yes 8, both no 7, disagree 5 -> po 0.75, pe 0.5 -> 0.5
        a = [True] * 8 + [False] * 7 + [True] * 2 + [False] * 3
        b = [True] * 8 + [False] * 7 + [False] * 2 + [True] * 3
        self.assertAlmostEqual(stats.cohen_kappa(a, b), 0.5)


if __name__ == "__main__":
    unittest.main()
