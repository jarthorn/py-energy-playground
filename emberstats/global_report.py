"""
Global report analyzing all loaded country data to find new records set in the latest month.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Dict, Tuple

from .analysis import ElectricityStats, NewRecord
from .country_codes import CountryCode
from .models import GenerationRecord


class GlobalReport:
    """Analyzes all loaded country data to find new records set in the latest month."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)

    def _find_country_files(self) -> list[tuple[CountryCode, Path]]:
        """Find all country data files and return tuples of (CountryCode, file_path)."""
        country_files = []
        for file_path in self.data_dir.glob("*-monthly-generation.json"):
            # Extract country code from filename (e.g., "can-monthly-generation.json" -> "CAN")
            country_code_str = file_path.stem.replace("-monthly-generation", "").upper()
            try:
                country_code = CountryCode(country_code_str)
                country_files.append((country_code, file_path))
            except ValueError:
                # Skip files that don't match a valid country code
                continue
        return country_files

    def _load_records(self, file_path: Path) -> Tuple[list[GenerationRecord], date | None]:
        """Load records from a country data file and return (records, latest_date)."""
        with file_path.open("r") as f:
            content = json.load(f)
        data_list = content.get("data", [])

        # Load all records (date parsing happens in GenerationRecord.from_dict)
        records = [GenerationRecord.from_dict(record_dict) for record_dict in data_list]

        # Find the latest date from loaded records
        max_date = None
        for record in records:
            if max_date is None or record.date > max_date:
                max_date = record.date

        # Update records that match the latest date
        for record in records:
            if record.date == max_date:
                record.is_latest_month = True

        return records, max_date

    def _find_new_records(
        self, metric_attr: str
    ) -> Dict[str, list[NewRecord]]:
        """
        Find countries that set new records in the latest month, grouped by fuel_type.

        Args:
            metric_attr: The metric to analyze ('share_of_generation_pct' or 'generation_twh')

        Returns:
            Dictionary mapping fuel_type -> list of NewRecord objects
        """
        new_records_by_fuel: Dict[str, list[NewRecord]] = defaultdict(list)
        country_files = self._find_country_files()

        for country_code, file_path in country_files:
            try:
                records, latest_date = self._load_records(file_path)
                if latest_date is None:
                    continue

                # Use ElectricityStats to find new records
                stats = ElectricityStats(records)
                country_name = records[0].country if records else country_code.value
                new_records = stats.find_new_records_in_latest_month(
                    latest_date=latest_date,
                    metric_attr=metric_attr,
                    country_code=country_code,
                    country_name=country_name,
                )

                # Group by fuel type
                for new_record in new_records:
                    new_records_by_fuel[new_record.fuel_type].append(new_record)
            except Exception as e:
                # Skip countries that fail to load
                print(f"Warning: Failed to process {country_code.value}: {e}", file=sys.stderr)
                continue

        return dict(new_records_by_fuel)

    def _print_new_records_table(
        self, new_records_by_fuel: Dict[str, list[NewRecord]], title: str, value_label: str
    ) -> None:
        """Print a table of new records grouped by fuel type."""
        print("\n" + "=" * 90)
        print(title)
        print("=" * 90)

        if not new_records_by_fuel:
            print("No new records set in the latest month.")
            return

        for fuel_type in sorted(new_records_by_fuel.keys()):
            records = new_records_by_fuel[fuel_type]
            print(f"\n{fuel_type}:")
            print(f"{'Country':<15} | {'Date':<12} | {'New Record':>15} | {'Previous Peak':>15}")
            print("-" * 90)
            for record in sorted(records, key=lambda x: x.value, reverse=True):
                print(
                    f"{record.country_code.value:<15} | {record.date:<12} | "
                    f"{record.value:>15.2f} | {record.previous_peak:>15.2f}"
                )

    def run(self) -> None:
        """Generate and print the global report."""
        # Find new records for share of generation
        new_share_records = self._find_new_records("share_of_generation_pct")
        self._print_new_records_table(
            new_share_records,
            title="Countries Setting New Peak Share of Generation Records (Latest Month)",
            value_label="Share (%)",
        )

        # Find new records for absolute generation
        new_gen_records = self._find_new_records("generation_twh")
        self._print_new_records_table(
            new_gen_records,
            title="Countries Setting New Peak Generation Records (Latest Month)",
            value_label="Generation (TWh)",
        )


def main() -> None:
    """Main entrypoint for global_report.py."""
    project_root = Path(__file__).parent.parent
    data_dir = project_root / "data"

    if not data_dir.exists():
        print(f"Error: Data directory not found: {data_dir}")
        print("Please run the load program first to fetch data for at least one country.")
        return

    report = GlobalReport(data_dir)
    report.run()


if __name__ == "__main__":
    main()
