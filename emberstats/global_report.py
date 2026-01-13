"""
Global report analyzing all loaded country data to find new records set in the latest month.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import date
from io import StringIO
from pathlib import Path
from typing import Dict, Tuple

from .analysis import ElectricityStats, NewRecord
from .country_codes import CountryCode
from .models import GenerationRecord


class GlobalReport:
    """Analyzes all loaded country data to find new records set in the latest month."""

    def __init__(self, data_dir: Path, output_csv: bool = False) -> None:
        self.data_dir = Path(data_dir)
        self.output_csv = output_csv

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

    def _print_new_records(
        self, new_records_by_fuel: Dict[str, list[NewRecord]], title: str, unit_label: str
    ) -> None:
        if not new_records_by_fuel:
            print("No new records set in the latest month.")
            return

        # Flatten all records into a single list
        all_records = []
        for fuel_type, records in new_records_by_fuel.items():
            all_records.extend(records)

        # Sort by fuel type
        all_records.sort(key=lambda x: x.fuel_type)

        if self.output_csv:
            self._print_new_records_csv(all_records, title, unit_label)
        else:
            self._print_new_records_table(all_records, title, unit_label)

    def _print_new_records_csv(
        self, all_records: list[NewRecord], title: str, unit_label: str
    ) -> None:
        """Print new records in CSV format."""
        print(f"\n# {title}")

        # Output CSV
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow([f"Fuel Type", "Country", "Date", f"New Record {unit_label}", f"Previous Peak {unit_label}"])

        for record in all_records:
            writer.writerow(
                [
                    record.fuel_type,
                    record.country_name,
                    record.date,
                    f"{record.value:.2f}",
                    f"{record.previous_peak:.2f}",
                ]
            )

        print(output.getvalue())

    def _print_new_records_table(
        self, all_records: list[NewRecord], title: str, unit_label: str
    ) -> None:
        """Print a table of new records in a formatted table suitable for command line viewing."""
        print("\n" + "=" * 95)
        print(title)
        print("=" * 95)

        print(f"{'Fuel Type':<20} | {'Country':<15} | {'Date':<12} | {f'New Record {unit_label}':>15} | {f'Previous Peak {unit_label}':>15}")
        print("-" * 95)
        for record in all_records:
            print(
                f"{record.fuel_type:<20} | {record.country_name:<15} | {record.date:<12} | "
                f"{record.value:>15.2f} | {record.previous_peak:>18.2f}"
            )

    def run(self) -> None:
        """Generate and print the global report."""
        # Find new records for share of generation
        new_share_records = self._find_new_records("share_of_generation_pct")
        self._print_new_records(
            new_share_records,
            title="Countries Setting New Peak Share of Generation Records (Latest Month)",
            unit_label="(%)",
        )

        # Find new records for absolute generation
        new_gen_records = self._find_new_records("generation_twh")
        self._print_new_records(
            new_gen_records,
            title="Countries Setting New Peak Generation Records (Latest Month)",
            unit_label="(TWh)",
        )


def main(output_csv: bool = False) -> None:
    """
    Main entrypoint for global_report.py.

    Args:
        output_csv: If True, output in CSV format; otherwise output formatted table
    """
    project_root = Path(__file__).parent.parent
    data_dir = project_root / "data"

    if not data_dir.exists():
        print(f"Error: Data directory not found: {data_dir}")
        print("Please run the load program first to fetch data for at least one country.")
        return

    report = GlobalReport(data_dir, output_csv=output_csv)
    report.run()


if __name__ == "__main__":
    output_csv = "-csv" in sys.argv or "--csv" in sys.argv
    main(output_csv=output_csv)
