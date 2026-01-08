"""
Unit tests for ElectricityStats using the bundled Canada sample dataset.
"""
import unittest
from pathlib import Path
import json
import sys

# Add src directory to path so we can import analysis
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from analysis import ElectricityStats


def load_sample_records():
    """Load the sample Canada monthly generation data from the repo."""
    sample_path = project_root / "data" / "canada-monthly-generation.json"
    with open(sample_path, "r") as f:
        content = json.load(f)
    return content.get("data", [])


class TestElectricityStats(unittest.TestCase):
    """Test cases for ElectricityStats class."""

    def setUp(self):
        """Set up test fixtures."""
        self.stats = ElectricityStats(load_sample_records())

    def test_peak_months_share_of_generation(self):
        """Test finding peak months for share_of_generation_pct."""
        peaks = self.stats.peak_months_by_series("share_of_generation_pct")

        # Spot-check a few expected peaks from the sample file
        self.assertEqual(peaks["Hydro"], ("2021-01-01", 64.9))
        self.assertEqual(peaks["Wind"], ("2024-04-01", 10.35))
        self.assertEqual(peaks["Nuclear"], ("2020-07-01", 17.17))

    def test_peak_months_generation_twh(self):
        """Test finding peak months for generation_twh."""
        peaks = self.stats.peak_months_by_series("generation_twh")

        # Spot-check a few expected peaks from the sample file
        self.assertEqual(peaks["Hydro"], ("2022-01-01", 40.17))
        self.assertEqual(peaks["Gas"], ("2024-01-01", 9.88))
        self.assertEqual(peaks["Coal"], ("2020-01-01", 3.67))


if __name__ == "__main__":
    unittest.main()
