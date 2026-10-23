"""Tests for reading the by-authority hourly wind CSV and mapping hours onto 2025."""

from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_PATH = PROJECT_ROOT / "src" / "gen-capacity-can" / "dashboard.py"
AGGREGATION_PATH = PROJECT_ROOT / "src" / "gen-capacity-can" / "hourly_variable_generation.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


dash = load_module(DASHBOARD_PATH, "wind_dashboard")
aggregation = load_module(AGGREGATION_PATH, "hourly_variable_generation")


def write_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)


def hourly_rows(authorities: list[str], values: list[list[str]]) -> list[list[str]]:
    rows = [["h", *authorities]]
    for hour, line in enumerate(values, start=1):
        rows.append([str(hour), *line])
    return rows


class TestHourToDisplayTime(unittest.TestCase):
    def test_hour_one_is_midnight_on_new_years_day(self):
        self.assertEqual(dash.hour_to_display_time(1), datetime(2025, 1, 1, 0, 0))

    def test_hours_step_forward_across_midnight(self):
        self.assertEqual(dash.hour_to_display_time(2), datetime(2025, 1, 1, 1, 0))
        self.assertEqual(dash.hour_to_display_time(24), datetime(2025, 1, 1, 23, 0))
        self.assertEqual(dash.hour_to_display_time(25), datetime(2025, 1, 2, 0, 0))

    def test_last_hour_of_non_leap_year_stays_in_december(self):
        last = dash.hour_to_display_time(8760)
        self.assertEqual(last, datetime(2025, 12, 31, 23, 0))
        self.assertLess(last, datetime(2026, 1, 1))

    def test_hour_before_one_fails(self):
        with self.assertRaises(dash.DataError):
            dash.hour_to_display_time(0)
        with self.assertRaises(dash.DataError):
            dash.hour_to_display_time(-1)

    def test_display_string_has_no_timezone_suffix(self):
        self.assertEqual(dash.format_display_time(dash.hour_to_display_time(1)), "2025-01-01 00:00:00")
        self.assertEqual(dash.format_display_time(dash.hour_to_display_time(8760)), "2025-12-31 23:00:00")


class TestParseMwCell(unittest.TestCase):
    def test_accepts_whole_megawatts_including_zero_and_negative(self):
        self.assertEqual(dash.parse_mw_cell("0"), 0)
        self.assertEqual(dash.parse_mw_cell("151"), 151)
        self.assertEqual(dash.parse_mw_cell("-3"), -3)

    def test_rejects_values_that_are_not_integer_tokens(self):
        for value in ("151.0", "", " 151", "151 ", "1e2", "12a", "+151", "151.5"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    dash.parse_mw_cell(value)


class TestLoadHourlyWind(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "wind-capacity-on_by-ba_2025_20261022-1728.csv"

    def test_reads_authorities_in_file_order_and_maps_hours(self):
        write_csv(
            self.path,
            hourly_rows(
                ["Alberta.a", "Ontario.a"],
                [["10", "151"], ["0", "187"]],
            ),
        )
        table = dash.load_hourly_csv(self.path, hours_in_year=2)
        self.assertEqual(table.authorities, ("Alberta.a", "Ontario.a"))
        self.assertEqual(table.hours, (1, 2))
        self.assertEqual(table.series["Ontario.a"], (151, 187))
        self.assertEqual(table.series["Alberta.a"], (10, 0))
        self.assertEqual(table.display_times, ("2025-01-01 00:00:00", "2025-01-01 01:00:00"))

    def test_missing_hour_column_fails(self):
        write_csv(self.path, [["Ontario.a"], ["151"]])
        with self.assertRaises(dash.DataError) as caught:
            dash.load_hourly_csv(self.path, hours_in_year=1)
        self.assertIn("header must start with column 'h'", str(caught.exception))

    def test_byte_order_mark_fails(self):
        write_csv(self.path, hourly_rows(["Ontario.a"], [["151"]]))
        self.path.write_bytes(b"\xef\xbb\xbf" + self.path.read_bytes())
        with self.assertRaises(dash.DataError) as caught:
            dash.load_hourly_csv(self.path, hours_in_year=1)
        self.assertIn("header must start with column 'h'", str(caught.exception))

    def test_decimal_megawatts_fail(self):
        write_csv(self.path, hourly_rows(["Ontario.a"], [["151.133308"]]))
        with self.assertRaises(dash.DataError) as caught:
            dash.load_hourly_csv(self.path, hours_in_year=1)
        self.assertIn("not an integer MW value", str(caught.exception))
        self.assertIn("Ontario.a", str(caught.exception))

    def test_hour_gap_fails(self):
        write_csv(self.path, [["h", "Ontario.a"], ["1", "10"], ["3", "12"]])
        with self.assertRaises(dash.DataError) as caught:
            dash.load_hourly_csv(self.path, hours_in_year=2)
        self.assertIn("where 2 was expected", str(caught.exception))

    def test_short_row_fails(self):
        write_csv(self.path, [["h", "Ontario.a", "Quebec.a"], ["1", "10"]])
        with self.assertRaises(dash.DataError) as caught:
            dash.load_hourly_csv(self.path, hours_in_year=1)
        self.assertIn("has 2 columns; header has 3", str(caught.exception))

    def test_wrong_row_count_fails(self):
        write_csv(self.path, hourly_rows(["Ontario.a"], [["10"]]))
        with self.assertRaises(dash.DataError) as caught:
            dash.load_hourly_csv(self.path, hours_in_year=2)
        self.assertIn("has 1 hour rows; expected 2", str(caught.exception))

    def test_duplicate_authority_fails(self):
        write_csv(self.path, hourly_rows(["Ontario.a", "Ontario.a"], [["10", "12"]]))
        with self.assertRaises(dash.DataError) as caught:
            dash.load_hourly_csv(self.path, hours_in_year=1)
        self.assertIn("repeats balancing authority column 'Ontario.a'", str(caught.exception))

    def test_missing_file_fails(self):
        with self.assertRaises(dash.DataError) as caught:
            dash.load_hourly_csv(self.path, hours_in_year=1)
        self.assertIn("Input file not found", str(caught.exception))


class TestAlignSeries(unittest.TestCase):
    def test_missing_authority_is_a_zero_series(self):
        table = dash.HourlySeries(
            path=Path("solar.csv"),
            authorities=("Ontario.a",),
            hours=(1, 2),
            series={"Ontario.a": (4, 5)},
            display_times=("2025-01-01 00:00:00", "2025-01-01 01:00:00"),
        )
        self.assertEqual(dash.series_or_zeros(table, "Ontario.a"), (4, 5))
        self.assertEqual(dash.series_or_zeros(table, "Manitoba.a"), (0, 0))

    def test_authority_list_is_the_sorted_union(self):
        wind = dash.HourlySeries(
            Path("wind.csv"),
            ("Ontario.a", "Alberta.a"),
            (1,),
            {"Ontario.a": (1,), "Alberta.a": (2,)},
            ("2025-01-01 00:00:00",),
        )
        solar = dash.HourlySeries(
            Path("solar.csv"),
            ("Ontario.a",),
            (1,),
            {"Ontario.a": (3,)},
            ("2025-01-01 00:00:00",),
        )
        self.assertEqual(dash.authorities_present((wind, solar)), ("Alberta.a", "Ontario.a"))

    def test_different_hour_indexes_fail(self):
        first = dash.HourlySeries(Path("wind.csv"), ("Ontario.a",), (1, 2), {"Ontario.a": (1, 2)}, ("a", "b"))
        second = dash.HourlySeries(Path("demand.csv"), ("Ontario.a",), (1,), {"Ontario.a": (3,)}, ("a",))
        with self.assertRaises(dash.DataError) as caught:
            dash.require_same_hours((first, second))
        self.assertIn("demand.csv hours do not match wind.csv", str(caught.exception))


class TestDefaultAuthority(unittest.TestCase):
    def test_prefers_ontario_a_when_present(self):
        self.assertEqual(dash.default_authority(["Alberta.a", "Ontario.a", "Quebec.a"]), "Ontario.a")

    def test_falls_back_to_the_first_column(self):
        self.assertEqual(dash.default_authority(["Alberta.a", "Quebec.a"]), "Alberta.a")


class TestAggregationContract(unittest.TestCase):
    def test_year_length_matches_the_aggregation_script(self):
        self.assertEqual(dash.NAMEPLATE_YEAR, aggregation.NAMEPLATE_YEAR)
        self.assertEqual(dash.HOURS_IN_YEAR, aggregation.HOURS_IN_YEAR)


class TestBuildFigure(unittest.TestCase):
    def test_stacks_four_series_on_one_x_axis(self):
        times = ["2025-01-01 00:00:00", "2025-01-01 01:00:00"]
        panels = (
            ("onshore wind generation", [151, 187], True),
            ("solar generation", [0, 0], True),
            ("demand", [10, 12], True),
            ("net demand", [9, -4], True),
        )
        figure = dash.build_figure("Ontario.a", times, panels)
        self.assertEqual(figure.layout.uirevision, "Ontario.a")
        self.assertEqual(
            [annotation.text for annotation in figure.layout.annotations],
            [
                "Ontario.a onshore wind generation, 2025",
                "Ontario.a solar generation, 2025",
                "Ontario.a demand, 2025",
                "Ontario.a net demand, 2025",
            ],
        )
        self.assertEqual(figure.layout.yaxis.rangemode, "tozero")
        self.assertEqual(figure.layout.yaxis4.rangemode, "tozero")
        self.assertEqual(figure.layout.xaxis.matches, "x4")
        self.assertEqual(figure.layout.xaxis2.matches, "x4")
        self.assertEqual(figure.layout.xaxis3.matches, "x4")
        self.assertIsNone(figure.layout.xaxis4.matches)
        self.assertTrue(figure.layout.xaxis4.rangeslider.visible)
        labels = [button.label for button in figure.layout.xaxis4.rangeselector.buttons]
        self.assertEqual(labels, ["7 days", "30 days", "Full year"])
        self.assertEqual([list(trace.y) for trace in figure.data], [[151, 187], [0, 0], [10, 12], [9, -4]])
        self.assertEqual(list(figure.data[0].x), times)
        self.assertEqual(list(figure.data[3].x), times)


if __name__ == "__main__":
    unittest.main()
