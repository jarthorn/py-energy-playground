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
DASHBOARD_PATH = PROJECT_ROOT / "src" / "wind-capacity-on" / "dashboard.py"
AGGREGATION_PATH = PROJECT_ROOT / "src" / "wind-capacity-on" / "hourly_wind_generation.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


dash = load_module(DASHBOARD_PATH, "wind_dashboard")
aggregation = load_module(AGGREGATION_PATH, "hourly_wind_generation")


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
        table = dash.load_hourly_wind(self.path, hours_in_year=2)
        self.assertEqual(table.authorities, ("Alberta.a", "Ontario.a"))
        self.assertEqual(table.hours, (1, 2))
        self.assertEqual(table.series["Ontario.a"], (151, 187))
        self.assertEqual(table.series["Alberta.a"], (10, 0))
        self.assertEqual(table.display_times, ("2025-01-01 00:00:00", "2025-01-01 01:00:00"))

    def test_missing_hour_column_fails(self):
        write_csv(self.path, [["Ontario.a"], ["151"]])
        with self.assertRaises(dash.DataError) as caught:
            dash.load_hourly_wind(self.path, hours_in_year=1)
        self.assertIn("header must start with column 'h'", str(caught.exception))

    def test_byte_order_mark_fails(self):
        write_csv(self.path, hourly_rows(["Ontario.a"], [["151"]]))
        self.path.write_bytes(b"\xef\xbb\xbf" + self.path.read_bytes())
        with self.assertRaises(dash.DataError) as caught:
            dash.load_hourly_wind(self.path, hours_in_year=1)
        self.assertIn("header must start with column 'h'", str(caught.exception))

    def test_decimal_megawatts_fail(self):
        write_csv(self.path, hourly_rows(["Ontario.a"], [["151.133308"]]))
        with self.assertRaises(dash.DataError) as caught:
            dash.load_hourly_wind(self.path, hours_in_year=1)
        self.assertIn("not an integer MW value", str(caught.exception))
        self.assertIn("Ontario.a", str(caught.exception))

    def test_hour_gap_fails(self):
        write_csv(self.path, [["h", "Ontario.a"], ["1", "10"], ["3", "12"]])
        with self.assertRaises(dash.DataError) as caught:
            dash.load_hourly_wind(self.path, hours_in_year=2)
        self.assertIn("where 2 was expected", str(caught.exception))

    def test_short_row_fails(self):
        write_csv(self.path, [["h", "Ontario.a", "Quebec.a"], ["1", "10"]])
        with self.assertRaises(dash.DataError) as caught:
            dash.load_hourly_wind(self.path, hours_in_year=1)
        self.assertIn("has 2 columns; header has 3", str(caught.exception))

    def test_wrong_row_count_fails(self):
        write_csv(self.path, hourly_rows(["Ontario.a"], [["10"]]))
        with self.assertRaises(dash.DataError) as caught:
            dash.load_hourly_wind(self.path, hours_in_year=2)
        self.assertIn("has 1 hour rows; expected 2", str(caught.exception))

    def test_duplicate_authority_fails(self):
        write_csv(self.path, hourly_rows(["Ontario.a", "Ontario.a"], [["10", "12"]]))
        with self.assertRaises(dash.DataError) as caught:
            dash.load_hourly_wind(self.path, hours_in_year=1)
        self.assertIn("repeats balancing authority column 'Ontario.a'", str(caught.exception))

    def test_missing_file_fails(self):
        with self.assertRaises(dash.DataError) as caught:
            dash.load_hourly_wind(self.path, hours_in_year=1)
        self.assertIn("Input file not found", str(caught.exception))


class TestLatestByBaCsv(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name)

    def test_picks_the_lexicographically_latest_by_authority_file(self):
        names = [
            "wind-capacity-on_Ontario.a_2025_20261022-1800.csv",
            "wind-capacity-on_by-ba_2025_20261022-1722.csv",
            "wind-capacity-on_by-ba_2025_20261022-1728.csv",
            "wind-capacity-on_by-ba_2025_20261022-1728.csv.partial",
            "wind-capacity-on_by-ba_2030_20261022-1900.csv",
            "notes.txt",
        ]
        for name in names:
            (self.output / name).write_text("h\n", encoding="utf-8")
        chosen = dash.latest_by_ba_csv(self.output)
        self.assertEqual(chosen.name, "wind-capacity-on_by-ba_2025_20261022-1728.csv")

    def test_missing_directory_fails(self):
        with self.assertRaises(dash.DataError) as caught:
            dash.latest_by_ba_csv(self.output / "missing")
        self.assertIn("No output directory", str(caught.exception))

    def test_no_matching_file_fails(self):
        (self.output / "wind-capacity-on_Ontario.a_2025_20261022-1523.csv").write_text("h\n", encoding="utf-8")
        with self.assertRaises(dash.DataError) as caught:
            dash.latest_by_ba_csv(self.output)
        self.assertIn("No file matching", str(caught.exception))


class TestDefaultAuthority(unittest.TestCase):
    def test_prefers_ontario_a_when_present(self):
        self.assertEqual(dash.default_authority(["Alberta.a", "Ontario.a", "Quebec.a"]), "Ontario.a")

    def test_falls_back_to_the_first_column(self):
        self.assertEqual(dash.default_authority(["Alberta.a", "Quebec.a"]), "Alberta.a")


class TestAggregationContract(unittest.TestCase):
    def test_filename_pattern_matches_the_aggregation_script(self):
        name = aggregation.output_path(datetime(2026, 10, 22, 17, 28)).name
        self.assertEqual(name, "wind-capacity-on_by-ba_2025_20261022-1728.csv")
        self.assertIsNotNone(dash.BY_BA_NAME.fullmatch(name))
        self.assertEqual(dash.NAMEPLATE_YEAR, aggregation.NAMEPLATE_YEAR)
        self.assertEqual(dash.HOURS_IN_YEAR, aggregation.HOURS_IN_YEAR)


class TestBuildFigure(unittest.TestCase):
    def test_titles_the_series_and_offers_the_shorter_windows(self):
        figure = dash.build_figure("Ontario.a", ["2025-01-01 00:00:00", "2025-01-01 01:00:00"], [151, 187])
        self.assertEqual(figure.layout.title.text, "Ontario.a onshore wind generation, 2025")
        self.assertEqual(figure.layout.uirevision, "Ontario.a")
        self.assertEqual(figure.layout.yaxis.rangemode, "tozero")
        self.assertEqual(figure.layout.yaxis.title.text, "MW")
        self.assertTrue(figure.layout.xaxis.rangeslider.visible)
        labels = [button.label for button in figure.layout.xaxis.rangeselector.buttons]
        self.assertEqual(labels, ["7 days", "30 days", "Full year"])
        self.assertEqual(list(figure.data[0].x), ["2025-01-01 00:00:00", "2025-01-01 01:00:00"])
        self.assertEqual(list(figure.data[0].y), [151, 187])


if __name__ == "__main__":
    unittest.main()
