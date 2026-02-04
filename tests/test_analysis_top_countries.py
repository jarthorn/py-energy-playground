
import unittest
from datetime import date
from emberstats.analysis import ElectricityStats
from emberstats.models import GenerationData

def create_record(country, date_str, fuel_type, generation):
    return GenerationData(
        country=country,
        country_code=country[:3].upper(),
        is_aggregate_entity=False,
        date=date.fromisoformat(date_str),
        fuel_type=fuel_type,
        is_aggregate_series=False,
        generation_twh=generation,
        share_of_generation_pct=0.0
    )

class TestTopCountries(unittest.TestCase):
    def test_top_countries_mixed_dates(self):
        # Country A: Data up to 2023-12-01.
        # Last 12 months: 2023-01-01 to 2023-12-01.
        # Let's give it 10 TWh per month for 2023. Total 120.
        # And some older data (2022) to ensure it's filtered out.
        data_a = []
        for m in range(1, 13):
            data_a.append(create_record("Country A", f"2023-{m:02d}-01", "Solar", 10.0))
        # Add a 13th month back
        data_a.append(create_record("Country A", "2022-12-01", "Solar", 100.0)) # Should be ignored

        # Country B: Data up to 2023-10-01.
        # Last 12 months: 2022-11-01 to 2023-10-01.
        # Let's give it 20 TWh per month. Total 240.
        data_b = []
        # Nov 2022 to Oct 2023
        # 2 months in 2022: Nov, Dec
        data_b.append(create_record("Country B", "2022-11-01", "Solar", 20.0))
        data_b.append(create_record("Country B", "2022-12-01", "Solar", 20.0))
        # 10 months in 2023: Jan to Oct
        for m in range(1, 11):
            data_b.append(create_record("Country B", f"2023-{m:02d}-01", "Solar", 20.0))

        # Country C: Only 6 months of data available total.
        # 30 TWh per month. Total 180.
        # Should still sum them up. The requirement says "most recent 12 months... available".
        # Actually it says "calculated using the most recent 12 months of data available".
        # If less than 12 months, usually we just sum what is there, or maybe we treat it as is.
        # I'll assume sum of available in that 12 month window (which is all of it).
        data_c = []
        for m in range(1, 7):
            data_c.append(create_record("Country C", f"2023-{m:02d}-01", "Solar", 30.0))

        # Country D: Wrong fuel type
        data_d = [create_record("Country D", "2023-12-01", "Coal", 1000.0)]

        all_data = data_a + data_b + data_c + data_d

        stats = ElectricityStats(all_data)
        top = stats.top_countries_by_fuel_type("Solar", limit=10)

        # Expected:
        # 1. Country B: 240.0
        # 2. Country C: 180.0
        # 3. Country A: 120.0 (10*12) - the 2022-12 entry (100.0) is 13th month, so excluded?
        # Wait, for Country A, latest is 2023-12. Window is 2023-01 to 2023-12.
        # 2022-12 is indeed outside.

        self.assertEqual(len(top), 3)

        self.assertEqual(top[0].country, "Country B")
        self.assertAlmostEqual(top[0].total_twh, 240.0)

        self.assertEqual(top[1].country, "Country C")
        self.assertAlmostEqual(top[1].total_twh, 180.0)

        self.assertEqual(top[2].country, "Country A")
        self.assertAlmostEqual(top[2].total_twh, 120.0)

if __name__ == "__main__":
    unittest.main()
