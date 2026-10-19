"""Tests for minute-level allocation in US weekly-hours histogram."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from collections import defaultdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "src" / "ev-charging-us" / "histogram_weekly_hours.py"


def load_module():
    spec = importlib.util.spec_from_file_location("us_histogram_weekly_hours", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mod = load_module()


class TestAllocateSession(unittest.TestCase):
    def test_single_hour_full_energy(self):
        bins: dict[tuple[int, int], mod.BinStats] = defaultdict(mod.BinStats)
        # Monday 2020-03-02 10:00, 1 hour, 6 kWh
        ok = mod.allocate_session(bins, datetime(2020, 3, 2, 10, 0, 44), 1.0, 6.0)
        self.assertTrue(ok)
        self.assertEqual(bins[(1, 10)].sessions, 1)
        self.assertAlmostEqual(bins[(1, 10)].energy, 6.0)
        self.assertEqual(len(bins), 1)

    def test_spans_two_hours(self):
        bins: dict[tuple[int, int], mod.BinStats] = defaultdict(mod.BinStats)
        # 90 minutes starting at 10:30 → 30 min in hour 10, 60 in hour 11
        ok = mod.allocate_session(bins, datetime(2020, 3, 2, 10, 30, 0), 1.5, 9.0)
        self.assertTrue(ok)
        self.assertEqual(bins[(1, 10)].sessions, 1)
        self.assertEqual(bins[(1, 11)].sessions, 1)
        self.assertAlmostEqual(bins[(1, 10)].energy, 3.0)  # 30/90 * 9
        self.assertAlmostEqual(bins[(1, 11)].energy, 6.0)  # 60/90 * 9

    def test_crosses_midnight_and_weekday(self):
        bins: dict[tuple[int, int], mod.BinStats] = defaultdict(mod.BinStats)
        # Monday 23:45, 30 minutes → Mon 23 (15 min) + Tue 0 (15 min)
        ok = mod.allocate_session(bins, datetime(2020, 3, 2, 23, 45, 0), 0.5, 4.0)
        self.assertTrue(ok)
        self.assertEqual(bins[(1, 23)].sessions, 1)
        self.assertEqual(bins[(2, 0)].sessions, 1)
        self.assertAlmostEqual(bins[(1, 23)].energy, 2.0)
        self.assertAlmostEqual(bins[(2, 0)].energy, 2.0)

    def test_floors_start_to_minute(self):
        bins: dict[tuple[int, int], mod.BinStats] = defaultdict(mod.BinStats)
        ok = mod.allocate_session(bins, datetime(2020, 3, 2, 10, 0, 59), 1 / 60, 1.0)
        self.assertTrue(ok)
        self.assertEqual(bins[(1, 10)].sessions, 1)
        self.assertAlmostEqual(bins[(1, 10)].energy, 1.0)

    def test_zero_duration_rejected(self):
        bins: dict[tuple[int, int], mod.BinStats] = defaultdict(mod.BinStats)
        self.assertFalse(mod.allocate_session(bins, datetime(2020, 3, 2, 10, 0, 0), 0.0, 5.0))
        self.assertEqual(len(bins), 0)

    def test_rounds_sub_minute_duration_to_zero(self):
        bins: dict[tuple[int, int], mod.BinStats] = defaultdict(mod.BinStats)
        # 0.1 seconds in hours ≈ 2.8e-5 h → rounds to 0 minutes
        self.assertFalse(mod.allocate_session(bins, datetime(2020, 3, 2, 10, 0, 0), 0.1 / 3600, 1.0))
        self.assertEqual(len(bins), 0)

    def test_zero_energy_still_counts_session(self):
        bins: dict[tuple[int, int], mod.BinStats] = defaultdict(mod.BinStats)
        ok = mod.allocate_session(bins, datetime(2020, 3, 2, 10, 0, 0), 1.0, 0.0)
        self.assertTrue(ok)
        self.assertEqual(bins[(1, 10)].sessions, 1)
        self.assertEqual(bins[(1, 10)].energy, 0.0)


if __name__ == "__main__":
    unittest.main()
