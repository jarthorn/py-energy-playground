"""Aggregate per-station monthly EV charging stats into city-wide monthly totals.

Data source: https://open.canada.ca/data/en/dataset/4b2f9b4c-abac-4c36-997a-85c22e22bf0b/resource/6773a89d-d3ad-4e22-9348-cfb2ea65724b

All stations with usable data for a month are included. Volume metrics
(Charge Sessions, Connection time, KWH total) are reported as per-charger
averages (month total / Charger Count) so months with different reporting
coverage stay comparable.

Derived columns are recomputed from the summed totals (same formulas as the
source per-station file):

    Average Monthly Connection Time Per Charge
        = Connection time / Charge Sessions
    Average monthly connection time per day per connector
        = Connection time / days_in_month / Charger Count
    Utilization rate
        = (connection time per day per connector) / 24h
    Average daily utilization
        = Charge Sessions / Charger Count / days_in_month
          (sessions per charger per day)

Usage:
    uv run python bin/aggregate_ev_charging_monthly.py <input.csv> [--year YYYY]

Writes output/aggregate_ev_charging_monthly_YYYYMMDD-HHMM.csv
"""

from __future__ import annotations

import argparse
import calendar
import csv
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "output"
SCRIPT_NAME = "aggregate_ev_charging_monthly"

MONTH_NUMBERS = {
    "janvier": 1,
    "février": 2,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "août": 8,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "décembre": 12,
    "decembre": 12,
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

MONTH_ENGLISH = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}


@dataclass
class StationMonth:
    charger_count: int
    charge_sessions: int
    connection_seconds: int
    kwh_total: float


@dataclass
class StationInfo:
    name: str = ""
    months: dict[str, StationMonth] = field(default_factory=dict)


def parse_duration(value: str) -> int | None:
    """Parse H:MM:SS or H:MM (hours may exceed 24) into total seconds."""
    value = value.strip().strip('"')
    if not value:
        return None
    parts = value.split(":")
    if len(parts) == 2:
        parts.append("0")
    if len(parts) != 3:
        return None
    try:
        hours, minutes, seconds = (int(p) for p in parts)
    except ValueError:
        return None
    return hours * 3600 + minutes * 60 + seconds


def format_duration(total_seconds: float) -> str:
    seconds = int(round(total_seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


def parse_number(value: str) -> float | None:
    """Parse a French/English numeric cell (quotes, spaces, decimal comma)."""
    value = value.strip().strip('"').replace(" ", "").replace("%", "")
    if not value:
        return None
    value = value.replace(",", ".")
    try:
        return float(value)
    except ValueError:
        return None


def format_number(value: float, decimals: int = 5) -> str:
    text = f"{value:.{decimals}f}".rstrip("0").rstrip(".")
    return text


def format_percent(value: float) -> str:
    return f"{value:.2f}%"


def month_sort_key(month: str) -> tuple[int, str]:
    return (MONTH_NUMBERS.get(month.lower(), 99), month)


def month_number(month: str) -> int:
    num = MONTH_NUMBERS.get(month.lower())
    if num is None:
        raise ValueError(f"Unrecognized month name: {month!r}")
    return num


def english_month(month: str) -> str:
    return MONTH_ENGLISH[month_number(month)]


def days_in_month(month: str, year: int) -> int:
    return calendar.monthrange(year, month_number(month))[1]


def infer_year(path: Path, explicit: int | None) -> int:
    if explicit is not None:
        return explicit
    match = re.search(r"(?<!\d)(20\d{2})(?!\d)", path.stem)
    if match:
        return int(match.group(1))
    raise SystemExit(f"Could not infer year from filename {path.name!r}; pass --year YYYY")


def row_has_data(row: dict[str, str]) -> bool:
    station = (row.get("Station") or "").strip()
    month = (row.get("Month") or "").strip()
    sessions = (row.get("Charge Sessions") or "").strip()
    return bool(station and month and sessions)


def load_stations(path: Path) -> dict[str, StationInfo]:
    """Load per-station monthly rows that have usable charging metrics."""
    stations: dict[str, StationInfo] = {}

    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row_has_data(row):
                continue

            station_id = row["Station"].strip()
            month = row["Month"].strip()
            info = stations.setdefault(station_id, StationInfo())
            name = (row.get("Station Name") or "").strip()
            if name and not info.name:
                info.name = name

            sessions = parse_number(row["Charge Sessions"])
            connection = parse_duration(row["Connection time"])
            kwh = parse_number(row["KWH total"])
            chargers = parse_number(row.get("Charger Count", ""))
            if sessions is None or connection is None or kwh is None or chargers is None:
                print(f"Skipping row with missing data: {row}", file=sys.stderr)
                continue

            entry = StationMonth(
                charger_count=int(chargers),
                charge_sessions=int(sessions),
                connection_seconds=connection,
                kwh_total=kwh,
            )
            if month in info.months:
                print(
                    f"Duplicate station-month: station={station_id} name={info.name or name!r} month={month!r}",
                    file=sys.stderr,
                )
                continue
            info.months[month] = entry

    return stations


def aggregate(stations: dict[str, StationInfo], year: int) -> list[dict[str, str]]:
    by_month: dict[str, list[StationMonth]] = defaultdict(list)
    for info in stations.values():
        for month, entry in info.months.items():
            by_month[month].append(entry)

    rows: list[dict[str, str]] = []
    for month in sorted(by_month, key=month_sort_key):
        entries = by_month[month]
        station_count = len(entries)
        charger_count = sum(e.charger_count for e in entries)
        sessions = sum(e.charge_sessions for e in entries)
        connection = sum(e.connection_seconds for e in entries)
        kwh = sum(e.kwh_total for e in entries)
        days = days_in_month(month, year)

        sessions_per_charger = sessions / charger_count if charger_count else 0.0
        connection_per_charger = connection / charger_count if charger_count else 0.0
        kwh_per_charger = kwh / charger_count if charger_count else 0.0

        avg_per_charge = connection / sessions if sessions else 0.0
        avg_per_day_per_connector = connection / days / charger_count if charger_count else 0.0
        utilization = (avg_per_day_per_connector / 86400) * 100 if charger_count else 0.0
        daily_utilization = sessions / charger_count / days if charger_count and days else 0.0

        rows.append(
            {
                "Year": year,
                "Month": english_month(month),
                "Station count": str(station_count),
                "Charger count": str(charger_count),
                "Sessions per charger": format_number(sessions_per_charger, decimals=2),
                "Connection time per charger": format_duration(connection_per_charger),
                "Average daily sessions per charger": format_number(daily_utilization, decimals=2),
                "KWH per charger": format_number(kwh_per_charger),
                "Connection time per charge": format_duration(avg_per_charge),
                "Connection time per day per connector": format_duration(avg_per_day_per_connector),
                "Utilization rate": format_percent(utilization),
            }
        )
    return rows


def output_path(when: datetime | None = None) -> Path:
    stamp = (when or datetime.now()).strftime("%Y%m%d-%H%M")
    return OUTPUT_DIR / f"{SCRIPT_NAME}_{stamp}.csv"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", type=Path, help="Per-station monthly charging CSV")
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Calendar year for day-of-month calculations (default: infer from filename)",
    )
    args = parser.parse_args(argv)

    if not args.input_csv.is_file():
        print(f"Input file not found: {args.input_csv}", file=sys.stderr)
        return 1

    year = infer_year(args.input_csv, args.year)
    stations = load_stations(args.input_csv)
    if not stations:
        print("No station data found in input file", file=sys.stderr)
        return 1

    out_rows = aggregate(stations, year)
    if not out_rows:
        print("No monthly aggregates produced", file=sys.stderr)
        return 1

    out_path = output_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"Wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
