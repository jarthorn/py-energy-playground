"""Tests for week spanning and connection-time inference in histogram_by_user."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "src" / "ev-charging-norway" / "histogram_by_user.py"


def load_module():
    spec = importlib.util.spec_from_file_location("histogram_by_user", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Required so dataclasses can resolve annotations under Python 3.15+.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mod = load_module()


def session(
    energy: float,
    connection: float | None,
    plugin: datetime,
    session_id: str = "s",
    row_num: int = 1,
):
    return mod.Session(
        session_id=session_id,
        plugin=plugin,
        energy_kwh=energy,
        connection_time_h=connection,
        row_num=row_num,
    )


class TestWeekCounting(unittest.TestCase):
    def test_single_session_one_week(self):
        with_count, without = mod.count_weeks([date(2020, 1, 15)])  # Wednesday
        self.assertEqual(with_count, 1)
        self.assertEqual(without, 0)

    def test_same_week_multiple_days(self):
        # Mon 13 Jan 2020 and Sun 19 Jan 2020 are the same calendar week
        with_count, without = mod.count_weeks([date(2020, 1, 13), date(2020, 1, 19)])
        self.assertEqual(with_count, 1)
        self.assertEqual(without, 0)

    def test_gap_weeks_between_first_and_last(self):
        # Week of Mon 6 Jan, then skip one week, then week of Mon 20 Jan
        with_count, without = mod.count_weeks([date(2020, 1, 8), date(2020, 1, 22)])
        self.assertEqual(with_count, 2)
        self.assertEqual(without, 1)

    def test_consecutive_weeks_no_gap(self):
        with_count, without = mod.count_weeks([date(2020, 1, 6), date(2020, 1, 13)])
        self.assertEqual(with_count, 2)
        self.assertEqual(without, 0)

    def test_year_boundary(self):
        # Mon 30 Dec 2019 week and Mon 13 Jan 2020 week → one empty week (6 Jan)
        with_count, without = mod.count_weeks([date(2019, 12, 31), date(2020, 1, 15)])
        self.assertEqual(with_count, 2)
        self.assertEqual(without, 1)


class TestConnectionInference(unittest.TestCase):
    def test_average_rate_from_known_sessions(self):
        sessions = [
            session(10.0, 2.0, datetime(2020, 1, 1, 12, 0, 0)),  # 5 kW
            session(20.0, 5.0, datetime(2020, 1, 2, 12, 0, 0)),  # 4 kW
            session(30.0, None, datetime(2020, 1, 3, 12, 0, 0)),
        ]
        rate = mod.average_charge_rate_kw(sessions)
        self.assertAlmostEqual(rate, 4.5)

    def test_infer_missing_connection_time(self):
        sessions = [
            session(10.0, 2.0, datetime(2020, 1, 1, 12, 0, 0), session_id="a"),  # 5 kW
            session(20.0, 5.0, datetime(2020, 1, 2, 12, 0, 0), session_id="b"),  # 4 kW
            session(9.0, None, datetime(2020, 1, 3, 12, 0, 0), session_id="c"),
        ]
        times, inferred = mod.resolve_connection_times(sessions)
        self.assertEqual(inferred, 1)
        self.assertAlmostEqual(times[0], 2.0)
        self.assertAlmostEqual(times[1], 5.0)
        self.assertAlmostEqual(times[2], 9.0 / 4.5)

    def test_aggregate_user_totals(self):
        sessions = [
            session(10.0, 2.0, datetime(2020, 1, 6, 12, 0, 0)),  # week 1
            session(9.0, None, datetime(2020, 1, 20, 12, 0, 0)),  # week 3; skip week 2
        ]
        # Only one known rate sample: 10/2 = 5 kW → inferred time = 9/5 = 1.8
        agg = mod.aggregate_user("U1", sessions)
        self.assertEqual(agg.sessions, 2)
        self.assertAlmostEqual(agg.total_energy_charged, 19.0)
        self.assertAlmostEqual(agg.total_connection_time, 2.0 + 1.8)
        self.assertEqual(agg.weeks_with_sessions, 2)
        self.assertEqual(agg.weeks_without_sessions, 1)
        self.assertEqual(agg.inferred_sessions, 1)

    def test_cannot_infer_without_rate_samples(self):
        sessions = [
            session(10.0, None, datetime(2020, 1, 1, 12, 0, 0)),
        ]
        with self.assertRaises(SystemExit):
            mod.resolve_connection_times(sessions)


if __name__ == "__main__":
    unittest.main()
