"""
Responsible for fetching fresh data from the Ember API and storing it to disk.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict
from dotenv import load_dotenv

import requests

from .country_codes import CountryCode

DEFAULT_START_DATE = "2015-01"


class Load:
    """
    Fetches monthly electricity generation data from the Ember API
    and persists the raw JSON response to a file.
    """

    def __init__(
        self,
        country_code: CountryCode = CountryCode.CAN,
        start_date: str = DEFAULT_START_DATE,
        base_url: str = "https://api.ember-energy.org",
        is_aggregate_series: bool = False,
    ) -> None:
        load_dotenv()
        self.api_key = os.getenv("EMBER_API_KEY")
        # Convert string to CountryCode if needed, for validation
        self.country_code = country_code
        self.start_date = start_date
        self.base_url = base_url
        self.is_aggregate_series = is_aggregate_series

    def _build_url(self) -> str:
        return (
            f"{self.base_url}/v1/electricity-generation/monthly"
            + f"?entity_code={self.country_code}"
            + f"&is_aggregate_series={'true' if self.is_aggregate_series else 'false'}"
            + "&is_aggregate_entity=false"
            + f"&start_date={self.start_date}"
            + f"&api_key={self.api_key}"
        )

    def fetch(self) -> Dict[str, Any]:
        url = self._build_url()
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json()

    def store(self, data: Dict[str, Any], output_path: Path) -> Path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w") as f:
            json.dump(data, f, indent=2)
        return output_path

    def fetch_and_store(self, output_path: Path) -> Path:
        output_path = Path(output_path)
        before_lines = _count_lines(output_path)
        data = self.fetch()
        self.store(data, output_path)
        after_lines = _count_lines(output_path)
        added = after_lines - before_lines
        if added > 0:
            print(f"{self.country_code.value}: {added} new lines")
        return output_path


def _count_lines(path: Path) -> int:
    """Return the number of lines in ``path``, or 0 if it does not exist."""
    if not path.exists():
        return 0
    with path.open("r") as f:
        return sum(1 for _ in f)


def fetch_and_store_all(start_date: str = DEFAULT_START_DATE, is_aggregate_series: bool = False) -> None:
    """
    Fetch and store data for all country codes.

    Args:
        start_date: Start date for the data query
        is_aggregate_series: Whether to include aggregate series (default: False)
    """
    print(f"Loading data for all {len(CountryCode)} countries...")
    for country_code in CountryCode:
        print(f"\nProcessing {country_code.value}...")
        try:
            load = Load(
                country_code=country_code,
                start_date=start_date,
                is_aggregate_series=is_aggregate_series,
            )
            output_path = Path(f"data/{country_code.value.lower()}-monthly-generation.json")
            load.fetch_and_store(output_path)
            print(f"✓ Successfully loaded data for {country_code.value}")
        except Exception as e:
            print(f"✗ Failed to load data for {country_code.value}: {e}")
    print("\nCompleted loading data for all countries.")


if __name__ == "__main__":
    args = sys.argv[1:]

    country_arg = None
    start_date_arg = DEFAULT_START_DATE

    for arg in args:
        if arg.startswith("--country="):
            country_arg = arg.split("=", 1)[1].upper()
        elif arg.startswith("--start_date="):
            start_date_arg = arg.split("=", 1)[1]
        else:
            print(f"Error: Unknown or malformed argument '{arg}'.")
            print("Usage: python -m emberstats.load --country=CAN --start_date=2020-01")
            print("       python -m emberstats.load --country=ALL --start_date=2015-01")
            print("Supported arguments are --country=<ISO3 code|ALL> and --start_date=YYYY-MM.")
            sys.exit(1)

    if country_arg is None:
        country_arg = CountryCode.CAN.value

    if country_arg == "ALL":
        fetch_and_store_all(start_date=start_date_arg)
        sys.exit(0)

    try:
        country_code = CountryCode(country_arg)
    except ValueError:
        print(f"Error: Invalid country code '{country_arg}'.")
        print("Please use a valid ISO 3166-1 alpha-3 country code (e.g., CAN, USA, ESP).")
        print("Use 'ALL' to load data for all countries.")
        sys.exit(1)

    load = Load(
        country_code=country_code,
        start_date=start_date_arg,
        is_aggregate_series=False,
    )
    load.fetch_and_store(Path(f"data/{country_code.value.lower()}-monthly-generation.json"))
