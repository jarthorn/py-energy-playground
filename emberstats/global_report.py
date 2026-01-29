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
from .models import GenerationData


class GlobalReport:
    """Analyzes all loaded country data to find new records set in the latest month."""

    LINE_LENGTH = 110

    def __init__(self, data_dir: Path, output_format: str = "text") -> None:
        self.data_dir = Path(data_dir)
        self.output_format = output_format

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

    def _load_generation_data(self, file_path: Path) -> Tuple[list[GenerationData], date | None]:
        """Load data from a country data file and return (data, latest_date)."""
        with file_path.open("r") as f:
            content = json.load(f)
        data_list = content.get("data", [])

        # Load all entries (date parsing happens in GenerationData.from_dict)
        generation_data = [GenerationData.from_dict(entry_dict) for entry_dict in data_list]

        # Find the latest date from loaded data
        max_date = None
        for entry in generation_data:
            if max_date is None or entry.date > max_date:
                max_date = entry.date

        # Update entries that match the latest date
        for entry in generation_data:
            if entry.date == max_date:
                entry.is_latest_month = True

        return generation_data, max_date

    def _find_new_records(
        self, metric_attr: str
    ) -> Dict[str, list[NewRecord]]:
        new_records_by_fuel: Dict[str, list[NewRecord]] = defaultdict(list)
        country_files = self._find_country_files()

        for country_code, file_path in country_files:
            try:
                generation_data, latest_date = self._load_generation_data(file_path)
                if latest_date is None:
                    continue

                # Use ElectricityStats to find new records
                stats = ElectricityStats(generation_data)
                country_name = generation_data[0].country if generation_data else country_code.value
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

        all_records.sort(key=lambda x: (x.date, x.country_name))

        if self.output_format == "csv":
            self._print_new_records_csv(all_records, title, unit_label)
        elif self.output_format == "tweet":
            self._print_new_records_tweet(all_records, unit_label)
        else:
            self._print_new_records_table(all_records, title, unit_label)

    def _generate_tweet_text(
        self, record: NewRecord, unit_label: str
    ) -> str | None:
        """Generate tweet text for a record. Returns None if record should be skipped."""
        # Fuel types to skip
        SKIP_FUEL_TYPES = {"Other fossil", "Other renewables", "Net imports"}

        if record.fuel_type in SKIP_FUEL_TYPES:
            return None

        # Clean unit label (remove parens) and add leading space if needed
        units = unit_label.replace("(", "").replace(")", "")
        units = " " + units if units != "%" else units
        metric_name = "generation share" if "%" in unit_label else "total generation"

        date_obj = date.fromisoformat(record.date)
        date_str = date_obj.strftime("%B %Y")

        prev_date_str = "unknown date"
        if record.previous_peak_date:
            prev_date_obj = date.fromisoformat(record.previous_peak_date)
            prev_date_str = prev_date_obj.strftime("%B %Y")

        return (
            f"In {date_str}, {record.country_name} hit a new electricity record for {metric_name} "
            f"of {record.value}{units} in {record.fuel_type.lower()} power. "
            f"This exceeds the previous peak of {record.previous_peak}{units} set in {prev_date_str}."
        )

    def _print_new_records_tweet(
        self, all_records: list[NewRecord], unit_label: str
    ) -> None:
        """Print new records in tweet format."""
        for record in all_records:
            tweet_text = self._generate_tweet_text(record, unit_label)
            if tweet_text:
                print(tweet_text)

    def _print_new_records_csv(
        self, all_records: list[NewRecord], title: str, unit_label: str
    ) -> None:
        """Print new records in CSV format."""
        print(f"\n# {title}")

        # Output CSV
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Fuel Type",
            "Country",
            "Date",
            f"New Record {unit_label}",
            f"Previous Peak {unit_label}",
            "Previous Date",
            "Tweet"
        ])
        for record in all_records:
            tweet_text = self._generate_tweet_text(record, unit_label)
            writer.writerow(
                [
                    record.fuel_type,
                    record.country_name,
                    record.date,
                    f"{record.value:.2f}",
                    f"{record.previous_peak:.2f}",
                    record.previous_peak_date or "N/A",
                    tweet_text or "",
                ]
            )

        print(output.getvalue())

    def _print_new_records_table(
        self, all_records: list[NewRecord], title: str, unit_label: str
    ) -> None:
        """Print a table of new records in a formatted table suitable for command line viewing."""
        print("\n" + "=" * GlobalReport.LINE_LENGTH)
        print(title)
        print("=" * GlobalReport.LINE_LENGTH)

        print(
            f"{'Fuel Type':<20} | {'Country':<15} | {'Date':<12} | "
            f"{f'New Record {unit_label}':>15} | {f'Previous Peak {unit_label}':>15} | {'Previous Date':<12}"
        )
        print("-" * GlobalReport.LINE_LENGTH)
        for record in all_records:
            prev_date_str = record.previous_peak_date or "N/A"
            print(
                f"{record.fuel_type:<20} | {record.country_name:<15} | {record.date:<12} | "
                f"{record.value:>15.2f} | {record.previous_peak:>18.2f} | {prev_date_str:<12}"
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




def main(output_format: str = "text") -> None:
    """
    Main entrypoint for global_report.py.

    Args:
        output_format: Output format ("text", "csv", or "tweet")
    """
    project_root = Path(__file__).parent.parent
    data_dir = project_root / "data"

    if not data_dir.exists():
        print(f"Error: Data directory not found: {data_dir}")
        print("Please run the load program first to fetch data for at least one country.")
        return

    report = GlobalReport(data_dir, output_format=output_format)
    report.run()


if __name__ == "__main__":
    format_arg = "text"
    # Handle --format=X argument
    for arg in sys.argv:
        if arg.startswith("--format="):
            format_arg = arg.split("=", 1)[1].lower()
            break

    # Validate format
    if format_arg not in ["text", "csv", "tweet"]:
        print(f"Error: Invalid format '{format_arg}'. Must be 'text', 'csv', or 'tweet'.", file=sys.stderr)
        sys.exit(1)

    main(output_format=format_arg)
