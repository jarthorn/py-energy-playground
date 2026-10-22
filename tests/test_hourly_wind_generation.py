"""Tests for joining extant onshore wind sites and scaling hourly capacity factors."""

from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "src" / "wind-capacity-on" / "hourly_wind_generation.py"


def load_module():
    spec = importlib.util.spec_from_file_location("hourly_wind_generation", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mod = load_module()


def write_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)


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

    def test_keeps_positive_onshore_wind_in_the_balancing_authority(self):
        locations, mismatches = mod.select_locations(self.extant, self.gridcells, "Ontario.a")
        self.assertEqual(locations, [mod.WindLocation(1, 10.0)])
        self.assertEqual([item.grid_cell for item in mismatches], [5, 9])
        self.assertIn("not in gridcells.csv", mismatches[0].message)
        self.assertIn("skipping", mismatches[0].message)

    def test_unknown_balancing_authority_fails_and_keeps_mismatches(self):
        with self.assertRaises(mod.DataError) as caught:
            mod.select_locations(self.extant, self.gridcells, "Ontario.c")
        self.assertIn("Unknown balancing authority", str(caught.exception))
        self.assertEqual([item.grid_cell for item in caught.exception.mismatches], [5, 9])

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
            mod.select_locations(self.extant, self.gridcells, "Ontario.a")
        self.assertIn("more than once", str(caught.exception))

    def test_utf8_bom_on_input_headers(self):
        for path in (self.gridcells, self.extant):
            path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
        locations, mismatches = mod.select_locations(self.extant, self.gridcells, "Ontario.a")
        self.assertEqual(locations, [mod.WindLocation(1, 10.0)])
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
            mod.select_locations(self.extant, self.gridcells, "Ontario.a")
        self.assertIn("neither .wind_ons nor .solar", str(caught.exception))


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
                ["1", "0.5", "0.25", "0.1"],
                ["2", "1", "0", "0.2"],
            ],
        )
        self.locations = [
            mod.WindLocation(10, 4.0),
            mod.WindLocation(2, 10.0),
            mod.WindLocation(50, 3.0),
        ]

    def test_scales_capacity_factors_and_sorts_columns(self):
        kept, mismatches = mod.write_hourly_generation(self.windcf, self.locations, self.dest, hours_in_year=2)
        self.assertEqual([item.grid_cell for item in kept], [2, 10])
        self.assertEqual([item.grid_cell for item in mismatches], [50])
        self.assertIn("no column for grid cell 50", mismatches[0].message)
        with self.dest.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(rows, [["h", "2", "10"], ["1", "2.5", "2"], ["2", "0", "4"]])
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
                [mod.WindLocation(2, 10.0)],
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
                [mod.WindLocation(2, 10.0)],
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
            mod.write_hourly_generation(self.windcf, [mod.WindLocation(2, 10.0)], self.dest, hours_in_year=1)
        self.assertIn("expected a number in [0, 1]", str(caught.exception))

    def test_every_selected_column_missing_fails(self):
        with self.assertRaises(mod.DataError) as caught:
            mod.write_hourly_generation(self.windcf, [mod.WindLocation(50, 3.0)], self.dest, hours_in_year=2)
        self.assertIn("No selected locations", str(caught.exception))
        self.assertEqual([item.grid_cell for item in caught.exception.mismatches], [50])
        self.assertFalse(self.dest.exists())


if __name__ == "__main__":
    unittest.main()
