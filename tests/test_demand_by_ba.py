"""Tests for splitting provincial demand onto balancing authorities and subtracting generation."""

from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "src" / "gen-capacity-can" / "demand_by_ba.py"


def load_module():
    spec = importlib.util.spec_from_file_location("demand_by_ba", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mod = load_module()

WEIGHTS = {
    "Ontario": {"Ontario.a": 2, "Ontario.b": 2},
    "Quebec": {"Ontario.a": 1, "Quebec.a": 3},
}


def write_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)


def read_csv(path: Path) -> list[list[str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.reader(handle))


class TestFormatMw(unittest.TestCase):
    def test_rounds_to_nearest_mw_with_halves_away_from_zero(self):
        self.assertEqual(mod.format_mw(11614), "11614")
        self.assertEqual(mod.format_mw(1.4), "1")
        self.assertEqual(mod.format_mw(1.5), "2")
        self.assertEqual(mod.format_mw(2.5), "3")
        self.assertEqual(mod.format_mw(-6.5), "-7")
        self.assertEqual(mod.format_mw(-1.5), "-2")
        self.assertEqual(mod.format_mw(-0.4), "0")
        self.assertEqual(mod.format_mw(-0.5), "-1")
        self.assertEqual(mod.format_mw(0.0), "0")

    def test_positive_values_below_one_mw_round_up_to_one(self):
        self.assertEqual(mod.format_mw(0.1), "1")
        self.assertEqual(mod.format_mw(1 / 3), "1")
        self.assertEqual(mod.format_mw(0.5), "1")
        self.assertEqual(mod.format_mw(0.9), "1")


class TestDisaggregateHour(unittest.TestCase):
    def test_single_authority_province_is_copied(self):
        result = mod.disaggregate_hour({"Alberta": 11614.0}, {"Alberta": {"Alberta.a": 4_269_532}})
        self.assertEqual(result, {"Alberta.a": 11614.0})

    def test_cross_border_authority_receives_both_provinces(self):
        result = mod.disaggregate_hour({"Ontario": 40.0, "Quebec": 40.0}, WEIGHTS)
        # Ontario.a = 40 * 2/4 + 40 * 1/4. Ontario.b = 40 * 2/4. Quebec.a = 40 * 3/4.
        self.assertEqual(result["Ontario.a"], 30.0)
        self.assertEqual(result["Ontario.b"], 20.0)
        self.assertEqual(result["Quebec.a"], 30.0)
        self.assertEqual(sum(result.values()), 80.0)

    def test_province_set_must_match_the_weights(self):
        with self.assertRaises(mod.DataError) as caught:
            mod.disaggregate_hour({"Ontario": 1.0}, WEIGHTS)
        self.assertIn("missing Quebec", str(caught.exception))


class TestNetDemandHour(unittest.TestCase):
    def test_subtracts_generation_and_treats_a_missing_authority_as_zero(self):
        net = mod.net_demand_hour(
            {"Alberta.a": 10.0, "Manitoba.a": 4.0},
            {"Alberta.a": 12.0},
            {"Alberta.a": 3.0, "Manitoba.a": 1.0},
        )
        self.assertEqual(net["Alberta.a"], -5.0)
        self.assertEqual(net["Manitoba.a"], 3.0)

    def test_generation_for_an_unknown_authority_fails(self):
        with self.assertRaises(mod.DataError) as caught:
            mod.net_demand_hour({"Alberta.a": 1.0}, {"Quebec.a": 1.0}, {})
        self.assertIn("Quebec.a", str(caught.exception))

    def test_negative_generation_fails(self):
        with self.assertRaises(mod.DataError) as caught:
            mod.net_demand_hour({"Alberta.a": 5.0}, {}, {"Alberta.a": -1.0})
        self.assertIn("wind generation for Alberta.a is negative", str(caught.exception))


class TestValidateWeights(unittest.TestCase):
    def test_zero_population_fails(self):
        with self.assertRaises(mod.DataError) as caught:
            mod.validate_weights({"Quebec": {"Quebec.a": 0}})
        self.assertIn("positive integer", str(caught.exception))

    def test_configured_weights_are_usable(self):
        mod.validate_weights(mod.PROVINCE_BA_POPULATION)
        authorities = mod.balancing_authorities(mod.PROVINCE_BA_POPULATION)
        self.assertIn("Newfoundland and Labrador.b", authorities)
        self.assertEqual(authorities, sorted(authorities))
        self.assertIn("Ontario.a", mod.PROVINCE_BA_POPULATION["Ontario"])
        self.assertIn("Ontario.a", mod.PROVINCE_BA_POPULATION["Quebec"])


class TestWriteBaDemandFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.demand = self.root / "demand.csv"
        self.solar = self.root / "solar_gen_ba.csv"
        self.wind = self.root / "wind_gen_ba.csv"
        self.when = datetime(2026, 10, 23, 10, 44)
        write_csv(
            self.demand,
            [
                ["", "Quebec", "Ontario"],
                ["0", "40", "40"],
                ["1", "0", "5"],
            ],
        )
        write_csv(
            self.solar,
            [
                ["h", "Ontario.a"],
                ["1", "12"],
                ["2", "9"],
            ],
        )
        write_csv(
            self.wind,
            [
                ["h", "Quebec.a", "Ontario.b"],
                ["1", "4", "1"],
                ["2", "0", "0"],
            ],
        )

    def write(self, **kwargs):
        return mod.write_ba_demand_files(
            self.demand,
            self.solar,
            self.wind,
            self.root,
            weights=WEIGHTS,
            when=self.when,
            hours_in_year=2,
            **kwargs,
        )

    def test_writes_both_files_on_the_generation_hour_index(self):
        demand_path, net_path, authorities = self.write()
        self.assertEqual(demand_path.name, "demand_ba_20261023-1044.csv")
        self.assertEqual(net_path.name, "net_demand_ba_20261023-1044.csv")
        self.assertEqual(authorities, ["Ontario.a", "Ontario.b", "Quebec.a"])
        # demand.csv hours 0 and 1 are written as hours 1 and 2.
        self.assertEqual(
            read_csv(demand_path),
            [
                ["h", "Ontario.a", "Ontario.b", "Quebec.a"],
                ["1", "30", "20", "30"],
                ["2", "3", "3", "0"],
            ],
        )
        # Hour 1: Ontario.a 30 - solar 12. Ontario.b 20 - wind 1. Quebec.a 30 - wind 4.
        # Hour 2: Ontario.a is 2.5 before rounding, then minus solar 9, so -6.5, which rounds to -7.
        self.assertEqual(
            read_csv(net_path),
            [
                ["h", "Ontario.a", "Ontario.b", "Quebec.a"],
                ["1", "18", "19", "26"],
                ["2", "-7", "3", "0"],
            ],
        )
        self.assertFalse((self.root / "demand_ba_20261023-1044.csv.partial").exists())

    def test_negative_demand_fails_and_removes_partial_output(self):
        write_csv(
            self.demand,
            [
                ["", "Ontario", "Quebec"],
                ["0", "-1", "40"],
                ["1", "5", "0"],
            ],
        )
        prior = self.root / "demand_ba_20261023-1044.csv"
        prior.write_text("keep\n", encoding="utf-8")
        with self.assertRaises(mod.DataError) as caught:
            self.write()
        self.assertIn("expected a non-negative number of MW", str(caught.exception))
        self.assertEqual(prior.read_text(encoding="utf-8"), "keep\n")
        self.assertFalse((self.root / "net_demand_ba_20261023-1044.csv").exists())
        self.assertFalse((self.root / "demand_ba_20261023-1044.csv.partial").exists())

    def test_wind_hour_index_must_match_the_demand_row(self):
        write_csv(
            self.wind,
            [
                ["h", "Ontario.b", "Quebec.a"],
                ["1", "1", "4"],
                ["3", "0", "0"],
            ],
        )
        with self.assertRaises(mod.DataError) as caught:
            self.write()
        self.assertIn("wind_gen_ba.csv hour column is 3 where 2 was expected", str(caught.exception))
        self.assertFalse((self.root / "demand_ba_20261023-1044.csv").exists())
        self.assertFalse((self.root / "net_demand_ba_20261023-1044.csv").exists())

    def test_short_solar_file_fails(self):
        write_csv(
            self.solar,
            [
                ["h", "Ontario.a"],
                ["1", "12"],
            ],
        )
        with self.assertRaises(mod.DataError) as caught:
            self.write()
        self.assertIn("solar_gen_ba.csv has 1 hour rows; expected 2", str(caught.exception))

    def test_extra_demand_row_fails(self):
        write_csv(
            self.demand,
            [
                ["", "Ontario", "Quebec"],
                ["0", "40", "40"],
                ["1", "5", "0"],
                ["2", "1", "1"],
            ],
        )
        with self.assertRaises(mod.DataError) as caught:
            self.write()
        self.assertIn("demand.csv has more than 2 hour rows", str(caught.exception))
        self.assertFalse((self.root / "net_demand_ba_20261023-1044.csv").exists())

    def test_unexpected_generation_column_fails(self):
        write_csv(
            self.solar,
            [
                ["h", "Ontario.a", "Atlantis.a"],
                ["1", "12", "0"],
                ["2", "9", "0"],
            ],
        )
        with self.assertRaises(mod.DataError) as caught:
            self.write()
        self.assertIn("unexpected column 'Atlantis.a'", str(caught.exception))

    def test_missing_province_fails(self):
        write_csv(
            self.demand,
            [
                ["", "Ontario"],
                ["0", "40"],
                ["1", "5"],
            ],
        )
        with self.assertRaises(mod.DataError) as caught:
            self.write()
        self.assertIn("missing columns: Quebec", str(caught.exception))

    def test_demand_hour_header_must_be_blank(self):
        write_csv(
            self.demand,
            [
                ["h", "Ontario", "Quebec"],
                ["0", "40", "40"],
                ["1", "5", "0"],
            ],
        )
        with self.assertRaises(mod.DataError) as caught:
            self.write()
        self.assertIn("hour column header must be blank", str(caught.exception))

    def test_row_width_mismatch_fails(self):
        write_csv(
            self.wind,
            [
                ["h", "Ontario.b", "Quebec.a"],
                ["1", "1"],
                ["2", "0", "0"],
            ],
        )
        with self.assertRaises(mod.DataError) as caught:
            self.write()
        self.assertIn("hour 1 has 2 columns; header has 3", str(caught.exception))

    def test_non_numeric_generation_fails(self):
        write_csv(
            self.solar,
            [
                ["h", "Ontario.a"],
                ["1", "n/a"],
                ["2", "9"],
            ],
        )
        with self.assertRaises(mod.DataError) as caught:
            self.write()
        self.assertIn("not a number", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
