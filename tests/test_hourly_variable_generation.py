"""Tests for summing extant wind and solar generation by balancing authority."""

from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "src" / "gen-capacity-can" / "hourly_variable_generation.py"


def load_module():
    spec = importlib.util.spec_from_file_location("hourly_variable_generation", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mod = load_module()


def write_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)


class TestFormatMw(unittest.TestCase):
    def test_rounds_half_away_from_zero(self):
        self.assertEqual(mod.format_mw(0), "0")
        self.assertEqual(mod.format_mw(0.4), "0")
        self.assertEqual(mod.format_mw(0.5), "1")
        self.assertEqual(mod.format_mw(1.5), "2")
        self.assertEqual(mod.format_mw(2), "2")


class TestSelectLocations(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.gridcells = self.root / "gridcells.csv"
        self.extant = self.root / "extant_wind_solar.csv"
        write_csv(
            self.gridcells,
            [
                ["grid_cell", "ba"],
                ["1", "Ontario.a"],
                ["2", "Ontario.a"],
                ["3", "Ontario.b"],
                ["8", "Ontario.a"],
                ["4", "Alberta.a"],
            ],
        )
        write_csv(
            self.extant,
            [
                ["location", "2025"],
                ["1.wind_ons", "10"],
                ["2.wind_ons", "0"],
                ["3.wind_ons", "5"],
                ["4.solar", "99"],
                ["5.wind_ons", "7"],
                ["9.wind_ons", "8"],
            ],
        )

    def test_keeps_positive_onshore_wind_in_every_balancing_authority(self):
        locations, mismatches = mod.select_locations(self.extant, self.gridcells)
        self.assertEqual(
            locations,
            [
                mod.Site(1, "Ontario.a", 10.0),
                mod.Site(3, "Ontario.b", 5.0),
            ],
        )
        self.assertEqual([item.grid_cell for item in mismatches], [5, 9])
        self.assertIn("not in gridcells.csv", mismatches[0].message)
        self.assertIn("skipping", mismatches[0].message)

    def test_all_zero_nameplate_fails_and_keeps_mismatches(self):
        write_csv(
            self.extant,
            [
                ["location", "2025"],
                ["1.wind_ons", "0"],
                ["3.wind_ons", "0"],
                ["5.wind_ons", "7"],
            ],
        )
        with self.assertRaises(mod.DataError) as caught:
            mod.select_locations(self.extant, self.gridcells)
        self.assertIn("No extant onshore wind", str(caught.exception))
        self.assertEqual([item.grid_cell for item in caught.exception.mismatches], [5])

    def test_duplicate_wind_location_fails(self):
        write_csv(
            self.extant,
            [
                ["location", "2025"],
                ["1.wind_ons", "10"],
                ["1.wind_ons", "4"],
            ],
        )
        with self.assertRaises(mod.DataError) as caught:
            mod.select_locations(self.extant, self.gridcells)
        self.assertIn("more than once", str(caught.exception))

    def test_utf8_bom_on_input_headers(self):
        for path in (self.gridcells, self.extant):
            path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
        locations, mismatches = mod.select_locations(self.extant, self.gridcells)
        self.assertEqual(
            locations,
            [
                mod.Site(1, "Ontario.a", 10.0),
                mod.Site(3, "Ontario.b", 5.0),
            ],
        )
        self.assertEqual([item.grid_cell for item in mismatches], [5, 9])

    def test_unexpected_location_suffix_fails(self):
        write_csv(
            self.extant,
            [
                ["location", "2025"],
                ["1.wind_ofs", "10"],
            ],
        )
        with self.assertRaises(mod.DataError) as caught:
            mod.select_locations(self.extant, self.gridcells)
        self.assertIn("neither .wind_ons nor .solar", str(caught.exception))

    def test_selects_positive_solar_and_skips_wind(self):
        locations, mismatches = mod.select_locations(self.extant, self.gridcells, technology=mod.SOLAR)
        self.assertEqual(locations, [mod.Site(4, "Alberta.a", 99.0)])
        self.assertEqual(mismatches, [])

    def test_same_grid_cell_can_be_wind_and_solar(self):
        write_csv(
            self.extant,
            [
                ["location", "2025"],
                ["1.wind_ons", "10"],
                ["1.solar", "4"],
            ],
        )
        wind, wind_mismatches = mod.select_locations(self.extant, self.gridcells, technology=mod.WIND)
        solar, solar_mismatches = mod.select_locations(self.extant, self.gridcells, technology=mod.SOLAR)
        self.assertEqual(wind, [mod.Site(1, "Ontario.a", 10.0)])
        self.assertEqual(solar, [mod.Site(1, "Ontario.a", 4.0)])
        self.assertEqual(wind_mismatches, [])
        self.assertEqual(solar_mismatches, [])

    def test_duplicate_solar_fails_while_selecting_wind(self):
        write_csv(
            self.extant,
            [
                ["location", "2025"],
                ["1.wind_ons", "10"],
                ["4.solar", "2"],
                ["4.solar", "3"],
            ],
        )
        with self.assertRaises(mod.DataError) as caught:
            mod.select_locations(self.extant, self.gridcells, technology=mod.WIND)
        self.assertIn("more than once", str(caught.exception))

    def test_bad_solar_nameplate_fails_while_selecting_wind(self):
        write_csv(
            self.extant,
            [
                ["location", "2025"],
                ["1.wind_ons", "10"],
                ["4.solar", "nope"],
            ],
        )
        with self.assertRaises(mod.DataError) as caught:
            mod.select_locations(self.extant, self.gridcells)
        self.assertIn("not a number", str(caught.exception))

    def test_all_zero_solar_fails(self):
        write_csv(
            self.extant,
            [
                ["location", "2025"],
                ["1.wind_ons", "10"],
                ["4.solar", "0"],
            ],
        )
        with self.assertRaises(mod.DataError) as caught:
            mod.select_locations(self.extant, self.gridcells, technology=mod.SOLAR)
        self.assertIn("No extant solar", str(caught.exception))


class TestWriteHourlyGeneration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.windcf = self.root / "windcf.csv"
        self.dest = self.root / "out.csv"
        write_csv(
            self.windcf,
            [
                ["h", "10", "2", "99"],
                ["1", "0.5", "0.25", "0.25"],
                ["2", "1", "0", "0.5"],
            ],
        )
        self.locations = [
            mod.Site(10, "Ontario.a", 4.0),
            mod.Site(2, "Ontario.a", 10.0),
            mod.Site(99, "Ontario.b", 8.0),
            mod.Site(50, "Alberta.a", 3.0),
        ]

    def test_sums_locations_within_each_balancing_authority(self):
        authorities, mismatches = mod.write_hourly_generation(self.windcf, self.locations, self.dest, hours_in_year=2)
        self.assertEqual(authorities, ["Ontario.a", "Ontario.b"])
        self.assertEqual([item.grid_cell for item in mismatches], [50])
        self.assertIn("no column for grid cell 50", mismatches[0].message)
        with self.dest.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(
            rows,
            [
                ["h", "Ontario.a", "Ontario.b"],
                ["1", "5", "2"],
                ["2", "4", "4"],
            ],
        )
        self.assertFalse((self.root / "out.csv.partial").exists())

    def test_hour_gap_removes_partial_output(self):
        write_csv(
            self.windcf,
            [
                ["h", "2"],
                ["1", "0.5"],
                ["3", "0.5"],
            ],
        )
        with self.assertRaises(mod.DataError) as caught:
            mod.write_hourly_generation(
                self.windcf,
                [mod.Site(2, "Ontario.a", 10.0)],
                self.dest,
                hours_in_year=2,
            )
        self.assertIn("where 2 was expected", str(caught.exception))
        self.assertFalse(self.dest.exists())
        self.assertFalse((self.root / "out.csv.partial").exists())

    def test_short_year_fails(self):
        with self.assertRaises(mod.DataError) as caught:
            mod.write_hourly_generation(
                self.windcf,
                [mod.Site(2, "Ontario.a", 10.0)],
                self.dest,
                hours_in_year=3,
            )
        self.assertIn("has 2 hour rows; expected 3", str(caught.exception))
        self.assertFalse(self.dest.exists())

    def test_capacity_factor_above_one_fails(self):
        write_csv(
            self.windcf,
            [
                ["h", "2"],
                ["1", "1.1"],
            ],
        )
        with self.assertRaises(mod.DataError) as caught:
            mod.write_hourly_generation(self.windcf, [mod.Site(2, "Ontario.a", 10.0)], self.dest, hours_in_year=1)
        self.assertIn("expected a number in [0, 1]", str(caught.exception))

    def test_capacity_factor_above_one_is_used_when_the_cap_is_open(self):
        write_csv(
            self.windcf,
            [
                ["h", "2"],
                ["1", "1.5"],
            ],
        )
        authorities, mismatches = mod.write_hourly_generation(
            self.windcf,
            [mod.Site(2, "Ontario.a", 10.0)],
            self.dest,
            hours_in_year=1,
            max_capacity_factor=None,
        )
        self.assertEqual(authorities, ["Ontario.a"])
        self.assertEqual(mismatches, [])
        with self.dest.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(rows, [["h", "Ontario.a"], ["1", "15"]])

    def test_negative_capacity_factor_fails_when_the_cap_is_open(self):
        write_csv(
            self.windcf,
            [
                ["h", "2"],
                ["1", "-0.1"],
            ],
        )
        with self.assertRaises(mod.DataError) as caught:
            mod.write_hourly_generation(
                self.windcf,
                [mod.Site(2, "Ontario.a", 10.0)],
                self.dest,
                hours_in_year=1,
                max_capacity_factor=None,
            )
        self.assertIn("expected a non-negative number", str(caught.exception))

    def test_every_selected_column_missing_fails(self):
        with self.assertRaises(mod.DataError) as caught:
            mod.write_hourly_generation(self.windcf, [mod.Site(50, "Alberta.a", 3.0)], self.dest, hours_in_year=2)
        self.assertIn("No selected locations", str(caught.exception))
        self.assertEqual([item.grid_cell for item in caught.exception.mismatches], [50])
        self.assertFalse(self.dest.exists())


class TestGenerateHourlyFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.gridcells = self.root / "gridcells.csv"
        self.extant = self.root / "extant_wind_solar.csv"
        self.windcf = self.root / "windcf.csv"
        self.solarcf = self.root / "solarcf.csv"
        self.when = datetime(2026, 10, 23, 10, 26)
        write_csv(
            self.gridcells,
            [
                ["grid_cell", "ba"],
                ["1", "Ontario.a"],
                ["2", "Ontario.a"],
                ["3", "Ontario.b"],
            ],
        )
        write_csv(
            self.extant,
            [
                ["location", "2025"],
                ["1.wind_ons", "10"],
                ["1.solar", "4"],
                ["2.wind_ons", "0"],
                ["3.solar", "0"],
            ],
        )
        write_csv(
            self.windcf,
            [
                ["h", "1", "3"],
                ["1", "0.5", "0"],
                ["2", "1", "0"],
            ],
        )
        write_csv(
            self.solarcf,
            [
                ["h", "1", "3"],
                ["1", "0.25", "0.5"],
                ["2", "0", "1"],
            ],
        )

    def test_writes_wind_and_solar_with_the_same_timestamp(self):
        results = mod.generate_hourly_files(
            self.extant,
            self.gridcells,
            [(mod.WIND, self.windcf), (mod.SOLAR, self.solarcf)],
            self.root,
            when=self.when,
            hours_in_year=2,
        )
        self.assertEqual(
            [path.name for path, _authorities in results],
            [
                "wind-capacity-on_by-ba_2025_20261023-1026.csv",
                "solar-capacity_by-ba_2025_20261023-1026.csv",
            ],
        )
        wind_path, solar_path = (path for path, _authorities in results)
        with wind_path.open(newline="", encoding="utf-8") as handle:
            wind_rows = list(csv.reader(handle))
        with solar_path.open(newline="", encoding="utf-8") as handle:
            solar_rows = list(csv.reader(handle))
        self.assertEqual(
            wind_rows,
            [
                ["h", "Ontario.a"],
                ["1", "5"],
                ["2", "10"],
            ],
        )
        self.assertEqual(
            solar_rows,
            [
                ["h", "Ontario.a"],
                ["1", "1"],
                ["2", "0"],
            ],
        )

    def test_solar_failure_removes_the_wind_file_from_this_run(self):
        write_csv(
            self.solarcf,
            [
                ["h", "1"],
                ["1", "0.25"],
                ["3", "0"],
            ],
        )
        with self.assertRaises(mod.DataError) as caught:
            mod.generate_hourly_files(
                self.extant,
                self.gridcells,
                [(mod.WIND, self.windcf), (mod.SOLAR, self.solarcf)],
                self.root,
                when=self.when,
                hours_in_year=2,
            )
        self.assertIn("where 2 was expected", str(caught.exception))
        self.assertFalse((self.root / "wind-capacity-on_by-ba_2025_20261023-1026.csv").exists())
        self.assertFalse((self.root / "solar-capacity_by-ba_2025_20261023-1026.csv").exists())
        self.assertFalse((self.root / "solar-capacity_by-ba_2025_20261023-1026.csv.partial").exists())


if __name__ == "__main__":
    unittest.main()
