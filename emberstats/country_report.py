"""
Reads stored data from disk, runs analysis, and prints results.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, Iterable, Optional
from datetime import date

from .analysis import ElectricityStats, CurrentFuelData
from .country_codes import CountryCode
from .models import GenerationRecord


class CountryReport:
    """Loads records from a file, runs analyses, and prints to stdout."""

    def __init__(self, input_path: Path, country_code: CountryCode | str) -> None:
        # Convert string to CountryCode if needed
        if isinstance(country_code, str):
            self.country_code = CountryCode(country_code.upper())
        else:
            self.country_code = country_code
        self.input_path = Path(input_path)

    def _load_records(self) -> Iterable[GenerationRecord]:
        with self.input_path.open("r") as f:
            content = json.load(f)
        data_list = content.get("data", [])

        # Load all records first (date parsing happens in GenerationRecord.from_dict)
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

        return records

    @staticmethod
    def _calculate_global_rank(
        country_code: CountryCode, total_twh: float, data_dir: Path
    ) -> Optional[int]:
        """
        Calculate global rank for a country based on total generation in last 12 months.

        Args:
            country_code: Country code to rank
            total_twh: Total TWh for the country in last 12 months
            data_dir: Directory containing country data files

        Returns:
            Global rank (1-based) or None if insufficient data.
        """
        country_totals: list[tuple[CountryCode, float]] = []

        # Load all country files and calculate totals
        for file_path in data_dir.glob("*-monthly-generation.json"):
            try:
                country_code_str = file_path.stem.replace("-monthly-generation", "").upper()
                file_country_code = CountryCode(country_code_str)

                with file_path.open("r") as f:
                    content = json.load(f)
                data_list = content.get("data", [])
                records = [
                    GenerationRecord.from_dict(record_dict) for record_dict in data_list
                ]

                stats = ElectricityStats(records)
                country_total, _ = stats.total_generation_last_12_months()
                if country_total > 0:
                    country_totals.append((file_country_code, country_total))
            except Exception:
                # Skip files that fail to load
                continue

        if not country_totals:
            return None

        # Sort by total descending
        country_totals.sort(key=lambda x: x[1], reverse=True)

        # Find rank
        for rank, (code, total) in enumerate(country_totals, start=1):
            if code == country_code:
                return rank

        return None

    def _generate_opening_paragraph(self, stats: ElectricityStats) -> str:
        """Generate the opening paragraph with country statistics."""
        # Calculate statistics
        total_twh, latest_date = stats.total_generation_last_12_months()
        if latest_date is None:
            return f"{self.country_code.value}: No data available."

        # Get country name from first record if available
        records_list = list(stats.records)
        country_name = (
            records_list[0].country if records_list else self.country_code.value
        )

        # Global rank
        project_root = Path(__file__).parent.parent
        data_dir = project_root / "data"
        global_rank = self._calculate_global_rank(self.country_code, total_twh, data_dir)
        rank_text = f"ranked {global_rank}" if global_rank else "not ranked"

        # Growth rate
        growth_rate = stats.growth_rate_total()
        if growth_rate is not None:
            if growth_rate >= 0:
                change_text = f"increase of {growth_rate:.1f}%"
            else:
                change_text = f"decrease of {abs(growth_rate):.1f}%"
        else:
            change_text = "no change data available"

        # Fuel types above 10%
        major_fuel_types = stats.fuel_types_above_threshold(10.0)
        if major_fuel_types:
            # Format as comma-separated list with "and" before last item
            if len(major_fuel_types) == 1:
                fuel_types_text = major_fuel_types[0]
            elif len(major_fuel_types) == 2:
                fuel_types_text = f"{major_fuel_types[0]} and {major_fuel_types[1]}"
            else:
                fuel_types_text = (
                    ", ".join(major_fuel_types[:-1]) + f", and {major_fuel_types[-1]}"
                )
        else:
            fuel_types_text = "none (all below 10%)"

        # Fastest growing
        fastest_fuel_type, fastest_growth_rate = stats.fastest_growing_fuel_type()
        if fastest_fuel_type:
            fastest_text = f"{fastest_fuel_type} with a {fastest_growth_rate:.1f}%"
        else:
            fastest_text = "none (insufficient data)"

        # Slowest growing
        slowest_fuel_type, slowest_growth_rate = stats.fastest_shrinking_fuel_type()
        if slowest_fuel_type:
            slowest_text = f"{slowest_fuel_type} with a {slowest_growth_rate:.1f}%"
        else:
            slowest_text = "none (insufficient data)"

        # Build paragraph
        paragraph = (
            f"{country_name} produced {total_twh:.1f} TWh of power in the last 12 months, "
            f"meaning it is {rank_text} among major power producing countries. "
            f"This is an {change_text} from the previous 12 month period. "
            f"Its biggest sources of power are: {fuel_types_text}. "
            f"Its fastest growing source of power is {fastest_text} growth rate. "
            f"Its slowest growing source of power is {slowest_text} growth rate. "
            f"The following tables show the peak share and absolute generation for each fuel type."
        )

        return paragraph

    @staticmethod
    def _print_peak_table(
        peak_months: Dict[str, GenerationRecord], title: str, value_label: str, metric_attr: str
    ) -> None:
        print("\n" + "=" * 70)
        print(title)
        print("=" * 70)
        print(f"{'Fuel Type':<45} | {'Month':<12} | {value_label:>16}")
        print("-" * 70)
        for fuel_type, record in sorted(peak_months.items()):
            value = getattr(record, metric_attr, None)
            if value is not None:
                date_str = record.date.isoformat()
                if record.is_latest_month:
                    date_str += "*"
                print(f"{fuel_type:<45} | {date_str:<12} | {value:>15.2f}")

    @staticmethod
    def _print_energy_mix_table(
        mix_records: list["CurrentFuelData"], latest_date: Optional[date]
    ) -> None:
        if not mix_records:
            return

        date_str = latest_date.strftime("%b %Y") if latest_date else "Latest Month"

        print("\n" + "=" * 105)
        print(f"Energy Mix Snapshot: {date_str}")
        print("=" * 105)

        # Headers
        headers = [
            "Fuel Type",
            "Mth Gen (TWh)",
            "Share (%)",
            "Mth Growth (%)",
            "12M Gen (TWh)",
            "12M Growth (%)"
        ]

        print(
            f"{headers[0]:<20} | {headers[1]:>14} | {headers[2]:>10} | "
            f"{headers[3]:>14} | {headers[4]:>14} | {headers[5]:>14}"
        )
        print("-" * 105)

        for rec in mix_records:
            mth_growth_str = f"{rec.growth_current_month:+.1f}" if rec.growth_current_month is not None else "-"
            gen_12m_growth_str = f"{rec.growth_last_12_months:+.1f}" if rec.growth_last_12_months is not None else "-"

            print(
                f"{rec.fuel_type:<20} | "
                f"{rec.gen_current_month:>14.2f} | "
                f"{rec.share_current_month:>10.1f} | "
                f"{mth_growth_str:>14} | "
                f"{rec.gen_last_12_months:>14.2f} | "
                f"{gen_12m_growth_str:>14}"
            )

    def run(self) -> None:
        records = self._load_records()
        stats = ElectricityStats(records)

        # Print opening paragraph
        opening_paragraph = self._generate_opening_paragraph(stats)
        print(opening_paragraph)
        print()

        # Energy Mix Snapshot
        mix_records = stats.get_energy_mix()
        self._print_energy_mix_table(mix_records, stats._get_latest_date())

        # Peak share of generation
        peak_share = stats.peak_months_by_series("share_of_generation_pct")
        self._print_peak_table(
            peak_share,
            title=f"Peak month for share of generation in {self.country_code.value} (%)",
            value_label="Peak Value (%)",
            metric_attr="share_of_generation_pct",
        )

        # Peak generation in TWh
        peak_gen = stats.peak_months_by_series("generation_twh")
        self._print_peak_table(
            peak_gen,
            title=f"Peak month for generation in {self.country_code.value} (TWh)",
            value_label="Peak Value (TWh)",
            metric_attr="generation_twh",
        )

def main(country_code: CountryCode) -> None:
    project_root = Path(__file__).parent.parent
    data_path = project_root / "data" / f"{country_code.value.lower()}-monthly-generation.json"

    if not data_path.exists():
        print(f"Error: Data file not found: {data_path}")
        print(f"Please run the load program first to fetch data for {country_code.value}:")
        print(f"  uv run python -m emberstats.load {country_code.value}")
        sys.exit(1)

    reporter = CountryReport(data_path, country_code)
    reporter.run()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            country_code = CountryCode(sys.argv[1].upper())
        except ValueError:
            print(f"Error: Invalid country code '{sys.argv[1]}'. Please use a valid ISO 3166-1 alpha-3 code.")
            sys.exit(1)
    else:
        country_code = CountryCode.CAN
    main(country_code)
