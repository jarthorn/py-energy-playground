"""
Reads stored data from disk, runs analysis, and prints results.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, Iterable, Tuple, Any

from analysis import ElectricityStats


class ReportRunner:
    """Loads records from a file, runs analyses, and prints to stdout."""

    def __init__(self, input_path: Path) -> None:
        self.input_path = Path(input_path)

    def _load_records(self) -> Iterable[Dict[str, Any]]:
        with self.input_path.open("r") as f:
            content = json.load(f)
        return content.get("data", [])

    @staticmethod
    def _print_peak_table(peak_months: Dict[str, Tuple[str, float]], title: str, value_label: str) -> None:
        print("\n" + "=" * 70)
        print(title)
        print("=" * 70)
        print(f"{'Series':<45} | {'Month':<12} | {value_label:>16}")
        print("-" * 70)
        for series, (month, value) in sorted(peak_months.items()):
            print(f"{series:<45} | {month:<12} | {value:>15.2f}")

    def run(self) -> None:
        records = self._load_records()
        stats = ElectricityStats(records)

        # Peak share of generation
        peak_share = stats.peak_months_by_series("share_of_generation_pct")
        self._print_peak_table(
            peak_share,
            title="Peak month for share of generation (%)",
            value_label="Peak Value (%)",
        )

        # Peak generation in TWh
        peak_gen = stats.peak_months_by_series("generation_twh")
        self._print_peak_table(
            peak_gen,
            title="Peak month for generation (TWh)",
            value_label="Peak Value (TWh)",
        )


def main(entity_code: str) -> None:
    """
    Main entrypoint for report.py.

    Args:
        entity_code: Country code (e.g., "CAN", "ESP")
    """
    project_root = Path(__file__).parent.parent
    data_path = project_root / "data" / f"{entity_code.lower()}-monthly-generation.json"

    if not data_path.exists():
        print(f"Error: Data file not found: {data_path}")
        print(f"Please run the load program first to fetch data for {entity_code}:")
        print(f"  uv run src/load.py {entity_code}")
        sys.exit(1)

    reporter = ReportRunner(data_path)
    reporter.run()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        entity_code = sys.argv[1]
    else:
        entity_code = "CAN"
    main(entity_code)
