"""
Unit tests for ElectricityStats using the bundled Canada sample dataset.
"""
import unittest
from datetime import date
from pathlib import Path
import json
import sys

# Add project root to path so we can import emberstats as a package
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from emberstats.analysis import ElectricityStats
from emberstats.models import GenerationRecord


def load_sample_records():
    """Load the sample Canada monthly generation data from the repo."""
    sample_path = project_root / "data" / "canada-monthly-generation.json"
    with open(sample_path, "r") as f:
        content = json.load(f)
    data_list = content.get("data", [])
    return [GenerationRecord.from_dict(record_dict) for record_dict in data_list]


class TestElectricityStats(unittest.TestCase):
    """Test cases for ElectricityStats class."""

    def setUp(self):
        """Set up test fixtures."""
        self.stats = ElectricityStats(load_sample_records())

    def test_peak_months_share_of_generation(self):
        """Test finding peak months for share_of_generation_pct."""
        peaks = self.stats.peak_months_by_series("share_of_generation_pct")

        # Spot-check a few expected peaks from the sample file
        # Verify that peaks returns GenerationRecord objects
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
        # Verify that peaks returns GenerationRecord objects
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


if __name__ == "__main__":
    unittest.main()
