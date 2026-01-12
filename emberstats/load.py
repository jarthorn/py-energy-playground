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


class Load:
    """
    Fetches monthly electricity generation data from the Ember API
    and persists the raw JSON response to a file.
    """

    def __init__(
        self,
        country_code: CountryCode | str = CountryCode.CAN,
        start_date: str = "2000-01",
        base_url: str = "https://api.ember-energy.org",
        is_aggregate_series: bool = False,
    ) -> None:
        load_dotenv()
        self.api_key = os.getenv("EMBER_API_KEY")
        # Convert string to CountryCode if needed, for validation
        if isinstance(country_code, str):
            self.country_code = CountryCode(country_code.upper())
        else:
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
        print("Fetching data from:", url)
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
        data = self.fetch()
        return self.store(data, output_path)


def fetch_and_store_all(start_date: str = "2000-01", is_aggregate_series: bool = False) -> None:
    """
    Fetch and store data for all country codes.

    Args:
        start_date: Start date for the data query (default: "2000-01")
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
    if len(sys.argv) > 1:
        arg = sys.argv[1].upper()
        if arg == "ALL":
            fetch_and_store_all()
        else:
            try:
                country_code = CountryCode(arg)
            except ValueError:
                print(f"Error: Invalid country code '{sys.argv[1]}'.")
                print("Please use a valid ISO 3166-1 alpha-3 country code (e.g., CAN, USA, ESP).")
                print("Use 'ALL' to load data for all countries.")
                sys.exit(1)
            load = Load(
                country_code=country_code,
                start_date="2000-01",
                is_aggregate_series=False,
            )
            load.fetch_and_store(Path(f"data/{country_code.value.lower()}-monthly-generation.json"))
    else:
        country_code = CountryCode.CAN
        load = Load(
            country_code=country_code,
            start_date="2000-01",
            is_aggregate_series=False,
        )
        load.fetch_and_store(Path(f"data/{country_code.value.lower()}-monthly-generation.json"))
