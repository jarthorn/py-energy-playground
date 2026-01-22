"""
Unit tests for ElectricityStats using the bundled Canada sample dataset.
"""

from emberstats.analysis import ElectricityStats
from emberstats.models import GenerationData
import unittest
from datetime import date
from pathlib import Path
import json
import sys

# Add project root to path so we can import emberstats as a package
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))



def load_sample_records():
    """Load the sample Canada monthly generation data from the repo."""
    sample_path = project_root / "tests/data" / "canada-monthly-generation.json"
    with open(sample_path, "r") as f:
        content = json.load(f)
    data_list = content.get("data", [])
    return [GenerationData.from_dict(record_dict) for record_dict in data_list]


class TestElectricityStats(unittest.TestCase):
    """Test cases for ElectricityStats class."""

    def setUp(self):
        """Set up test fixtures."""
        self.stats = ElectricityStats(load_sample_records())

    def test_peak_months_share_of_generation(self):
        """Test finding peak months for share_of_generation_pct."""
        peaks = self.stats.peak_months_by_series("share_of_generation_pct")

        # Spot-check a few expected peaks from the sample file
        # Verify that peaks returns GenerationData objects
        self.assertIn("Hydro", peaks)
        hydro_record = peaks["Hydro"]
        self.assertEqual(hydro_record.date, date(2021, 1, 1))
        self.assertEqual(hydro_record.share_of_generation_pct, 64.9)

        self.assertIn("Wind", peaks)
        wind_record = peaks["Wind"]
        self.assertEqual(wind_record.date, date(2024, 4, 1))
        self.assertEqual(wind_record.share_of_generation_pct, 10.35)

        self.assertIn("Nuclear", peaks)
        nuclear_record = peaks["Nuclear"]
        self.assertEqual(nuclear_record.date, date(2020, 7, 1))
        self.assertEqual(nuclear_record.share_of_generation_pct, 17.17)

    def test_peak_months_generation_twh(self):
        """Test finding peak months for generation_twh."""
        peaks = self.stats.peak_months_by_series("generation_twh")

        # Spot-check a few expected peaks from the sample file
        # Verify that peaks returns GenerationData objects
        self.assertIn("Hydro", peaks)
        hydro_record = peaks["Hydro"]
        self.assertEqual(hydro_record.date, date(2022, 1, 1))
        self.assertEqual(hydro_record.generation_twh, 40.17)

        self.assertIn("Gas", peaks)
        gas_record = peaks["Gas"]
        self.assertEqual(gas_record.date, date(2024, 1, 1))
        self.assertEqual(gas_record.generation_twh, 9.88)

        self.assertIn("Coal", peaks)
        coal_record = peaks["Coal"]
        self.assertEqual(coal_record.date, date(2020, 1, 1))
        self.assertEqual(coal_record.generation_twh, 3.67)

    def test_total_generation_last_12_months(self):
        """Test calculating total generation for the last 12 months."""
        total_twh, latest_date = self.stats.total_generation_last_12_months()

        self.assertIsNotNone(latest_date, "Latest date should not be None")
        self.assertEqual(total_twh, 612.01, "Total generation should be 612 TWh")

    def test_total_generation_previous_12_months(self):
        """Test calculating total generation for the previous 12 months."""
        total_twh = self.stats.total_generation_previous_12_months()

        self.assertEqual(total_twh, 594.03, "Total generation should be 594.03 TWh")

    def test_get_energy_mix(self):
        """Test fetching the energy mix snapshot."""
        mix = self.stats.get_energy_mix()
        self.assertTrue(len(mix) > 0)

        # Spot check Hydro
        hydro = next(r for r in mix if r.fuel_type == "Hydro")
        # Latest month in sample is Sep 2025
        # Hydro gen in Sep 2025: 22.87 TWh
        # Share: 51.46%
        self.assertEqual(hydro.gen_current_month, 22.87)
        self.assertEqual(hydro.share_current_month, 51.46)
        # Sep 2024 Hydro: 23.99 TWh. Growth = (22.87 - 23.99)/23.99 * 100 = -4.67%
        self.assertAlmostEqual(hydro.growth_current_month, -4.67, places=2)

        # Last 12 months vs Prev
        # Using totals from other tests/checks or just verify it's populated
        self.assertIsNotNone(hydro.gen_last_12_months)
        self.assertIsNotNone(hydro.growth_last_12_months)

    def test_aggregate_by_year(self):
        """Test aggregating generation by year."""
        # Canada sample data has years 2020-2025
        # 2020 should be full year (12 months)
        # 2025 has data up to September (9 months) -> Partial

        aggs = self.stats.aggregate_by_year()
        self.assertTrue(len(aggs) > 0)

        # Check 2020
        agg_2020 = next(a for a in aggs if a.year == 2020)
        self.assertFalse(agg_2020.is_partial)
        # Compare with value manually calculated from sample data
        self.assertEqual(agg_2020.generation_twh, 577.55)

        # Check 2025 (Partial)
        agg_2025 = next(a for a in aggs if a.year == 2025)
        self.assertTrue(agg_2025.is_partial)

        # Check filtering by fuel type "Hydro"
        hydro_aggs = self.stats.aggregate_by_year(fuel_type="Hydro")
        hydro_2020 = next(a for a in hydro_aggs if a.year == 2020)

        # Verify it sums correctly (Hydro 2020 total from sample check or approximation)
        # We know it should be less than total 2020
        self.assertLess(hydro_2020.generation_twh, agg_2020.generation_twh)
        self.assertFalse(hydro_2020.is_partial)


if __name__ == "__main__":
    unittest.main()
