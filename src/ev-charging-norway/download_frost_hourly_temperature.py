"""Download hourly air temperature from MET Norway Frost API to yearly CSVs.

Source: https://frost.met.no/ (station SN18700 = Oslo–Blindern by default)

Each output file has one row per UTC hour in that calendar year:

    station_id,hour,temperature

Usage:
    export FROST_CLIENT_ID=<your client id>
    uv run python bin/download_frost_hourly_temperature.py
    uv run python bin/download_frost_hourly_temperature.py --years 2018 2019 2020 2021

Writes data/ev-charging-norway/SN18700_hourly_YYYY.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "ev-charging-norway"

FROST_OBSERVATIONS_URL = "https://frost.met.no/observations/v0.jsonld"
DEFAULT_STATION = "SN18700"
DEFAULT_YEARS = (2018, 2019, 2020, 2021)

CSV_COLUMNS = ("station_id", "hour", "temperature")


def hours_in_year(year: int) -> list[datetime]:
    """Return every UTC hour from Jan 1 00:00 through Dec 31 23:00."""
    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    hours: list[datetime] = []
    current = start
    while current < end:
        hours.append(current)
        current += timedelta(hours=1)
    return hours


def fetch_year(client_id: str, station: str, year: int) -> dict[datetime, float]:
    """Fetch hourly air temperatures for one calendar year (UTC)."""
    params = {
        "sources": station,
        "elements": "air_temperature",
        "referencetime": f"{year}-01-01/{year + 1}-01-01",
        "timeresolutions": "PT1H",
        "levels": "default",
        "timeoffsets": "default",
    }
    response = requests.get(
        FROST_OBSERVATIONS_URL,
        params=params,
        auth=(client_id, ""),
        timeout=120,
    )
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"Non-JSON response for {year} (HTTP {response.status_code})") from exc

    if response.status_code != 200:
        error = payload.get("error", {})
        message = error.get("message", response.reason)
        reason = error.get("reason", "")
        detail = f"{message}: {reason}" if reason else message
        raise RuntimeError(f"Frost API error for {year} (HTTP {response.status_code}): {detail}")

    by_hour: dict[datetime, float] = {}
    for item in payload.get("data", []):
        reference_time = datetime.fromisoformat(item["referenceTime"].replace("Z", "+00:00"))
        observations = item.get("observations") or []
        if not observations:
            continue
        # With levels=default / timeoffsets=default there should be one value.
        value = observations[0]["value"]
        by_hour[reference_time] = float(value)
    return by_hour


def write_year_csv(
    path: Path,
    station: str,
    year: int,
    observations: dict[datetime, float],
) -> tuple[int, int]:
    """Write one CSV row per hour. Returns (written_rows, missing_hours)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    missing = 0
    rows = 0
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for hour in hours_in_year(year):
            temperature = observations.get(hour)
            if temperature is None:
                missing += 1
                temperature_str = ""
            else:
                temperature_str = str(temperature)
            writer.writerow(
                {
                    "station_id": station,
                    "hour": hour.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "temperature": temperature_str,
                }
            )
            rows += 1
    return rows, missing


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--station",
        default=DEFAULT_STATION,
        help=f"Frost source id (default: {DEFAULT_STATION})",
    )
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=list(DEFAULT_YEARS),
        help="Calendar years to download (default: 2018-2021)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for yearly CSVs (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--client-id",
        default=None,
        help="Frost client ID (default: FROST_CLIENT_ID env / .env)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = parse_args(argv)
    client_id = args.client_id or os.getenv("FROST_CLIENT_ID")
    if not client_id:
        print(
            "Frost client ID required. Set FROST_CLIENT_ID or pass --client-id.",
            file=sys.stderr,
        )
        return 1

    station = args.station.upper()
    if not station.startswith("SN"):
        station = f"SN{station}"

    for year in args.years:
        print(f"Fetching {station} hourly temperature for {year}...", file=sys.stderr)
        observations = fetch_year(client_id, station, year)
        out_path = args.output_dir / f"{station}_hourly_{year}.csv"
        rows, missing = write_year_csv(out_path, station, year, observations)
        print(
            f"Wrote {out_path} ({rows} hours, {len(observations)} observed, {missing} missing)",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
