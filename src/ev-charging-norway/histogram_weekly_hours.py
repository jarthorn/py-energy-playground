"""Histogram Dataset4 hourly predictions by day-of-week and hour.

Produces 168 rows (7 days × 24 hours) with session counts and total energy
charged per bin. Day-of-week uses ISO-style numbering: 1=Monday … 7=Sunday.

Usage:
    uv run python src/ev-charging-norway/histogram_weekly_hours.py

Writes:
    output/norway_ev_weekly_hours_YYYYMMDD-HHMM.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = REPO_ROOT / "output"
DEFAULT_INPUT = REPO_ROOT / "data" / "ev-charging-norway" / "Dataset4_hourly_predictions.csv"
SCRIPT_NAME = "norway_ev_weekly_hours"

DAY_NAMES = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)

OUTPUT_COLUMNS = (
    "day_of_week",
    "hour",
    "day_name",
    "sessions",
    "total_energy_charged",
)


@dataclass
class BinStats:
    sessions: int = 0
    energy: float = 0.0


def parse_timestamp(value: str) -> datetime | None:
    value = value.strip().strip('"')
    if not value or value.upper() == "NA":
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def parse_european_number(value: str) -> float | None:
    """Parse a number that may use comma as decimal separator.

    Returns None for empty/NA values (expected in this dataset for idle hours).
    """
    value = value.strip().strip('"')
    if not value or value.upper() == "NA":
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def format_number(value: float, decimals: int = 6) -> str:
    text = f"{value:.{decimals}f}".rstrip("0").rstrip(".")
    return text if text else "0"


def aggregate(path: Path) -> dict[tuple[int, int], BinStats]:
    bins: dict[tuple[int, int], BinStats] = defaultdict(BinStats)
    bad_timestamps = 0
    bad_energy = 0
    row_count = 0

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        if reader.fieldnames is None:
            raise SystemExit(f"Empty or unreadable CSV: {path}")

        # Quoted headers may retain quote characters depending on dialect.
        field_map = {name.strip().strip('"'): name for name in reader.fieldnames}
        required = {"date_from", "energy_charged_i"}
        missing = required - set(field_map)
        if missing:
            raise SystemExit(f"Missing required columns in {path}: {sorted(missing)}")

        date_col = field_map["date_from"]
        energy_col = field_map["energy_charged_i"]

        for row_num, row in enumerate(reader, start=2):
            row_count += 1
            ts = parse_timestamp(row[date_col])
            if ts is None:
                bad_timestamps += 1
                print(
                    f"Row {row_num}: invalid date_from {row[date_col]!r}",
                    file=sys.stderr,
                )
                continue

            raw_energy = row[energy_col]
            energy = parse_european_number(raw_energy)
            stripped = raw_energy.strip().strip('"')
            if energy is None and stripped and stripped.upper() != "NA":
                bad_energy += 1
                print(
                    f"Row {row_num}: invalid energy_charged_i {raw_energy!r}",
                    file=sys.stderr,
                )
                continue

            # Monday=0 in datetime → day_of_week 1..7
            day_of_week = ts.weekday() + 1
            key = (day_of_week, ts.hour)
            stats = bins[key]
            stats.sessions += 1
            if energy is not None:
                stats.energy += energy

    if bad_timestamps:
        print(f"Skipped {bad_timestamps} row(s) with invalid timestamps", file=sys.stderr)
    if bad_energy:
        print(f"Skipped {bad_energy} row(s) with invalid energy values", file=sys.stderr)
    if row_count == 0:
        raise SystemExit(f"No data rows in {path}")

    return bins


def build_output_rows(bins: dict[tuple[int, int], BinStats]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for day_of_week in range(1, 8):
        for hour in range(24):
            stats = bins.get((day_of_week, hour), BinStats())
            rows.append(
                {
                    "day_of_week": str(day_of_week),
                    "hour": str(hour),
                    "day_name": DAY_NAMES[day_of_week - 1],
                    "sessions": str(stats.sessions),
                    "total_energy_charged": format_number(stats.energy),
                }
            )
    return rows


def output_path(when: datetime | None = None) -> Path:
    stamp = (when or datetime.now()).strftime("%Y%m%d-%H%M")
    return OUTPUT_DIR / f"{SCRIPT_NAME}_{stamp}.csv"


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(OUTPUT_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Dataset4 hourly predictions CSV (default: {DEFAULT_INPUT})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.input.is_file():
        print(f"Input file not found: {args.input}", file=sys.stderr)
        return 1

    bins = aggregate(args.input)
    rows = build_output_rows(bins)
    if len(rows) != 168:
        raise SystemExit(f"Expected 168 output rows, got {len(rows)}")

    path = output_path()
    write_csv(path, rows)
    print(f"Wrote {path}", file=sys.stderr)
    print(f"Total input rows counted: {sum(s.sessions for s in bins.values())}")
    print(f"Total energy charged: {format_number(sum(s.energy for s in bins.values()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
