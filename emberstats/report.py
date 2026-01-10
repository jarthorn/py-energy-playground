"""
Reads stored data from disk, runs analysis, and prints results.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, Iterable

from .analysis import ElectricityStats
from .models import GenerationRecord


class ReportRunner:
    """Loads records from a file, runs analyses, and prints to stdout."""

    def __init__(self, input_path: Path, country_code: str) -> None:
        self.country_code = country_code
        self.input_path = Path(input_path)

    def _load_records(self) -> Iterable[GenerationRecord]:
        with self.input_path.open("r") as f:
            content = json.load(f)
        data_list = content.get("data", [])
        return [GenerationRecord.from_dict(record_dict) for record_dict in data_list]

    @staticmethod
    def _print_peak_table(peak_months: Dict[str, GenerationRecord], title: str, value_label: str, metric_attr: str) -> None:
        print("\n" + "=" * 70)
        print(title)
        print("=" * 70)
        print(f"{'Fuel Type':<45} | {'Month':<12} | {value_label:>16}")
        print("-" * 70)
        for fuel_type, record in sorted(peak_months.items()):
            value = getattr(record, metric_attr, None)
            if value is not None:
                date_str = record.date.isoformat()
                print(f"{fuel_type:<45} | {date_str:<12} | {value:>15.2f}")

    def run(self) -> None:
        records = self._load_records()
        stats = ElectricityStats(records)

        # Peak share of generation
        peak_share = stats.peak_months_by_series("share_of_generation_pct")
        self._print_peak_table(
            peak_share,
            title=f"Peak month for share of generation in {self.country_code} (%)",
            value_label="Peak Value (%)",
            metric_attr="share_of_generation_pct",
        )

        # Peak generation in TWh
        peak_gen = stats.peak_months_by_series("generation_twh")
        self._print_peak_table(
            peak_gen,
            title=f"Peak month for generation in {self.country_code} (TWh)",
            value_label="Peak Value (TWh)",
            metric_attr="generation_twh",
        )


def main(country_code: str) -> None:
    """
    Main entrypoint for report.py.

    Args:
        country_code: Country code (e.g., "CAN", "ESP")
    """
    project_root = Path(__file__).parent.parent
    data_path = project_root / "data" / f"{country_code.lower()}-monthly-generation.json"

    if not data_path.exists():
        print(f"Error: Data file not found: {data_path}")
        print(f"Please run the load program first to fetch data for {country_code}:")
        print(f"  uv run python -m emberstats.load {country_code}")
        sys.exit(1)

    reporter = ReportRunner(data_path, country_code)
    reporter.run()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        country_code = sys.argv[1]
    else:
        country_code = "CAN"
    main(country_code)
