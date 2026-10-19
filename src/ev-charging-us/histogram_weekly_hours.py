"""Histogram EV Watts sessions by day-of-week and hour.

Streams session rows and allocates each session's energy evenly across
charge_duration minutes (start_datetime floored to the minute). Produces 168
rows (7 days × 24 hours) with active-session counts and total energy per bin.
Day-of-week uses ISO-style numbering: 1=Monday … 7=Sunday.

A session contributes +1 to `sessions` for every calendar hour it overlaps.

Usage:
    uv run python src/ev-charging-us/histogram_weekly_hours.py

Writes:
    output/us_ev_weekly_hours_YYYYMMDD-HHMM.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = REPO_ROOT / "output"
DEFAULT_INPUT = REPO_ROOT / "data" / "ev-charging-us" / "evwatts.public.session.csv"
SCRIPT_NAME = "us_ev_weekly_hours"

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

REQUIRED_COLUMNS = ("start_datetime", "charge_duration", "energy_kwh")


@dataclass
class BinStats:
    sessions: int = 0
    energy: float = 0.0


def parse_timestamp(value: str) -> datetime | None:
    value = value.strip().strip('"')
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def parse_float(value: str) -> float | None:
    value = value.strip().strip('"')
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def format_number(value: float, decimals: int = 6) -> str:
    text = f"{value:.{decimals}f}".rstrip("0").rstrip(".")
    return text if text else "0"


def allocate_session(
    bins: dict[tuple[int, int], BinStats],
    start: datetime,
    charge_duration_h: float,
    energy_kwh: float,
) -> bool:
    """Allocate one session into weekly hour bins.

    Returns False if duration rounds to zero or fewer minutes (caller should skip).
    """
    if charge_duration_h <= 0:
        return False

    n_minutes = round(charge_duration_h * 60)
    if n_minutes <= 0:
        return False

    start = start.replace(second=0, microsecond=0)
    energy_per_minute = energy_kwh / n_minutes

    remaining = n_minutes
    current = start
    while remaining > 0:
        minutes_left_in_hour = 60 - current.minute
        chunk = min(remaining, minutes_left_in_hour)
        day_of_week = current.weekday() + 1
        key = (day_of_week, current.hour)
        stats = bins[key]
        stats.sessions += 1
        stats.energy += energy_per_minute * chunk
        remaining -= chunk
        current += timedelta(minutes=chunk)

    return True


def build_weekly_hour_histogram(path: Path) -> dict[tuple[int, int], BinStats]:
    """Stream session rows and fill day-of-week × hour bins with overlaps and energy."""
    bins: dict[tuple[int, int], BinStats] = defaultdict(BinStats)
    bad_timestamps = 0
    bad_duration = 0
    bad_energy = 0
    skipped_zero_duration = 0
    allocated = 0
    row_count = 0

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise SystemExit(f"Empty or unreadable CSV: {path}")

        field_map = {name.strip().strip('"'): name for name in reader.fieldnames}
        missing = set(REQUIRED_COLUMNS) - set(field_map)
        if missing:
            raise SystemExit(f"Missing required columns in {path}: {sorted(missing)}")

        start_col = field_map["start_datetime"]
        duration_col = field_map["charge_duration"]
        energy_col = field_map["energy_kwh"]

        for row_num, row in enumerate(reader, start=2):
            row_count += 1

            ts = parse_timestamp(row[start_col])
            if ts is None:
                bad_timestamps += 1
                print(
                    f"Row {row_num}: invalid start_datetime {row[start_col]!r}",
                    file=sys.stderr,
                )
                continue

            duration = parse_float(row[duration_col])
            if duration is None:
                bad_duration += 1
                print(
                    f"Row {row_num}: invalid charge_duration {row[duration_col]!r}",
                    file=sys.stderr,
                )
                continue

            energy = parse_float(row[energy_col])
            if energy is None:
                bad_energy += 1
                print(
                    f"Row {row_num}: invalid energy_kwh {row[energy_col]!r}",
                    file=sys.stderr,
                )
                continue

            if not allocate_session(bins, ts, duration, energy):
                skipped_zero_duration += 1
                continue

            allocated += 1

    if bad_timestamps:
        print(f"Skipped {bad_timestamps} row(s) with invalid timestamps", file=sys.stderr)
    if bad_duration:
        print(f"Skipped {bad_duration} row(s) with invalid charge_duration", file=sys.stderr)
    if bad_energy:
        print(f"Skipped {bad_energy} row(s) with invalid energy_kwh", file=sys.stderr)
    if skipped_zero_duration:
        print(
            f"Skipped {skipped_zero_duration} row(s) with zero/negative charge_duration",
            file=sys.stderr,
        )
    if row_count == 0:
        raise SystemExit(f"No data rows in {path}")
    if allocated == 0:
        raise SystemExit(f"No usable sessions in {path}")

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
        help=f"EV Watts session CSV (default: {DEFAULT_INPUT})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.input.is_file():
        print(f"Input file not found: {args.input}", file=sys.stderr)
        return 1

    bins = build_weekly_hour_histogram(args.input)
    rows = build_output_rows(bins)
    if len(rows) != 168:
        raise SystemExit(f"Expected 168 output rows, got {len(rows)}")

    path = output_path()
    write_csv(path, rows)
    print(f"Wrote {path}", file=sys.stderr)
    session_hour_bins = sum(s.sessions for s in bins.values())
    total_energy = sum(s.energy for s in bins.values())
    print(f"Total session-hour bins counted: {session_hour_bins:,}")
    energy_text = f"{total_energy:,.0f}".rstrip("0").rstrip(".")
    print(f"Total energy charged: {energy_text if energy_text else '0'} kWh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
