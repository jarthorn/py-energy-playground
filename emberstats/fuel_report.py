"""
Generates a report for a specific fuel type aggregated across all available country data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable

from .analysis import ElectricityStats, YearlyAggregation
from .models import GenerationData


class FuelReport:
    """Aggregates data by fuel type and prints a report."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)

    def load_all_data(self) -> Iterable[GenerationData]:
        """Load all entries from all JSON files in the data directory."""
        all_data = []
        for file_path in self.data_dir.glob("*-monthly-generation.json"):
            try:
                with file_path.open("r") as f:
                    content = json.load(f)
                data_list = content.get("data", [])

                # Check if data_list is empty, if so skip
                if not data_list:
                    continue

                # Load entries
                country_data = [
                    GenerationData.from_dict(entry_dict)
                    for entry_dict in data_list
                ]
                all_data.extend(country_data)
            except Exception as e:
                print(f"Warning: Failed to load {file_path.name}: {e}", file=sys.stderr)
                continue
        return all_data

    def print_report(self, aggs: list[YearlyAggregation], fuel_type: str) -> None:
        """Print the aggregated report table."""
        print("\n" + "=" * 60)
        print(f"Global Aggregation Report for: {fuel_type}")
        print("=" * 60)

        # Headers
        headers = ["Year", "Generation (TWh)", "Growth Rate (%)"]
        print(f"{headers[0]:<6} | {headers[1]:>18} | {headers[2]:>16}")
        print("-" * 60)

        prev_gen = 0.0

        for agg in aggs:
            growth_str = "-"
            if prev_gen > 0:
                growth_val = ((agg.generation_twh - prev_gen) / prev_gen) * 100
                growth_str = f"{growth_val:+.1f}"

            gen_str = f"{agg.generation_twh:,.2f}"
            if agg.is_partial:
                gen_str += "*"

            print(
                f"{agg.year:<6} | "
                f"{gen_str:>18} | "
                f"{growth_str:>16}"
            )

            prev_gen = agg.generation_twh

    def run(self, fuel_type: str) -> None:
        stats = ElectricityStats(self.load_all_data())

        aggregated = stats.aggregate_by_year(fuel_type)

        if not aggregated:
            print(f"No data found for fuel type: '{fuel_type}'")
            return

        self.print_report(aggregated, fuel_type)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m emberstats.fuel_report <fuel_type>")
        print("Example: python -m emberstats.fuel_report Solar")
        print('Example: python -m emberstats.fuel_report "Other fossil"')
        sys.exit(1)

    fuel_type = sys.argv[1]

    project_root = Path(__file__).parent.parent
    data_dir = project_root / "data"

    if not data_dir.exists():
        print(f"Error: Data directory not found: {data_dir}")
        sys.exit(1)

    reporter = FuelReport(data_dir)
    reporter.run(fuel_type)


if __name__ == "__main__":
    main()
