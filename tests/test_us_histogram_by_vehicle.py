"""Tests for week spanning and vehicle aggregation in histogram_by_vehicle."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "src" / "ev-charging-us" / "histogram_by_vehicle.py"


def load_module():
    spec = importlib.util.spec_from_file_location("us_histogram_by_vehicle", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mod = load_module()


def session(
    energy: float | None,
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


def vehicle(**overrides):
    defaults = dict(
        electrification_level="BEV (Battery Electric Vehicle)",
        ownership="Fleet",
        state="Colorado",
    )
    defaults.update(overrides)
    return mod.Vehicle(**defaults)


class TestWeekCounting(unittest.TestCase):
    def test_single_session_one_week(self):
        with_count, without = mod.count_weeks([date(2020, 1, 15)])  # Wednesday
        self.assertEqual(with_count, 1)
        self.assertEqual(without, 0)

    def test_same_week_multiple_days(self):
        with_count, without = mod.count_weeks([date(2020, 1, 13), date(2020, 1, 19)])
        self.assertEqual(with_count, 1)
        self.assertEqual(without, 0)

    def test_gap_weeks_between_first_and_last(self):
        with_count, without = mod.count_weeks([date(2020, 1, 8), date(2020, 1, 22)])
        self.assertEqual(with_count, 2)
        self.assertEqual(without, 1)

    def test_consecutive_weeks_no_gap(self):
        with_count, without = mod.count_weeks([date(2020, 1, 6), date(2020, 1, 13)])
        self.assertEqual(with_count, 2)
        self.assertEqual(without, 0)

    def test_year_boundary(self):
        with_count, without = mod.count_weeks([date(2019, 12, 31), date(2020, 1, 15)])
        self.assertEqual(with_count, 2)
        self.assertEqual(without, 1)


class TestAggregateVehicle(unittest.TestCase):
    def test_totals_and_joined_attributes(self):
        sessions = [
            session(10.0, 2.0, datetime(2020, 1, 6, 12, 0, 0)),
            session(9.0, 1.5, datetime(2020, 1, 20, 12, 0, 0)),
        ]
        agg = mod.aggregate_vehicle("100", sessions, vehicle(state="Oregon"))
        self.assertEqual(agg.vehicle_id, "100")
        self.assertEqual(agg.sessions, 2)
        self.assertAlmostEqual(agg.total_energy_charged, 19.0)
        self.assertAlmostEqual(agg.total_connection_time, 3.5)
        self.assertEqual(agg.weeks_with_sessions, 2)
        self.assertEqual(agg.weeks_without_sessions, 1)
        self.assertEqual(agg.state, "Oregon")
        self.assertEqual(agg.ownership, "Fleet")

    def test_missing_duration_counts_for_weeks_only(self):
        sessions = [
            session(10.0, 2.0, datetime(2020, 1, 6, 12, 0, 0)),
            session(None, None, datetime(2020, 1, 20, 12, 0, 0)),
        ]
        agg = mod.aggregate_vehicle("100", sessions, vehicle())
        self.assertEqual(agg.sessions, 1)
        self.assertAlmostEqual(agg.total_energy_charged, 10.0)
        self.assertAlmostEqual(agg.total_connection_time, 2.0)
        self.assertEqual(agg.weeks_with_sessions, 2)
        self.assertEqual(agg.weeks_without_sessions, 1)

    def test_parse_session_skips_missing_duration_and_energy(self):
        field_map = {
            "id": "id",
            "start_datetime": "start_datetime",
            "duration": "duration",
            "energy_kwh": "energy_kwh",
        }
        skips = mod.SkipCounts()
        both_missing = mod.parse_session(
            {
                "id": "1",
                "start_datetime": "2020-01-01 12:00:00",
                "duration": "",
                "energy_kwh": "",
            },
            field_map,
            2,
            skips,
        )
        self.assertIsNone(both_missing)
        self.assertEqual(skips.missing_duration, 1)
        self.assertEqual(skips.missing_energy, 1)

        duration_only_missing = mod.parse_session(
            {
                "id": "1b",
                "start_datetime": "2020-01-01 12:00:00",
                "duration": "",
                "energy_kwh": "4.2",
            },
            field_map,
            3,
            skips,
        )
        self.assertIsNotNone(duration_only_missing)
        assert duration_only_missing is not None
        self.assertIsNone(duration_only_missing.connection_time_h)
        self.assertIsNone(duration_only_missing.energy_kwh)
        self.assertFalse(duration_only_missing.counts_toward_totals)
        self.assertEqual(skips.missing_duration, 2)
        self.assertEqual(skips.missing_energy, 1)

        ok = mod.parse_session(
            {
                "id": "2",
                "start_datetime": "2020-01-01 12:00:00",
                "duration": "1.5",
                "energy_kwh": "4.2",
            },
            field_map,
            3,
            skips,
        )
        self.assertIsNotNone(ok)
        assert ok is not None
        self.assertAlmostEqual(ok.connection_time_h, 1.5)
        self.assertAlmostEqual(ok.energy_kwh, 4.2)

        date_only = mod.parse_session(
            {
                "id": "3",
                "start_datetime": "2022-04-01",
                "duration": "0.5",
                "energy_kwh": "1.0",
            },
            field_map,
            4,
            skips,
        )
        self.assertIsNotNone(date_only)
        assert date_only is not None
        self.assertEqual(date_only.plugin, datetime(2022, 4, 1, 0, 0, 0))


if __name__ == "__main__":
    unittest.main()
