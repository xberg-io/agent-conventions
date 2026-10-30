"""Calibration is byte-weighted and refuses zero-work inputs."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import calibrate


class CalibrationTest(unittest.TestCase):
    def test_weights_native_counts_by_sample_size(self) -> None:
        self.assertEqual(calibrate.estimate([{"bytes": 20, "tokens": 10}, {"bytes": 100, "tokens": 20}]), 4)

    def test_refuses_empty_or_zero_token_calibration(self) -> None:
        for samples in ([], [{"bytes": 20, "tokens": 0}]):
            with self.assertRaises(ValueError):
                calibrate.estimate(samples)


if __name__ == "__main__":
    unittest.main()
