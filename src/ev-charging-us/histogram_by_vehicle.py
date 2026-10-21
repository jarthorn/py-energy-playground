"""Per-vehicle histogram of EV Watts vehicle-linked charging sessions.

Streams the input (grouped by vehicle_id) so only one vehicle's sessions are
held in memory at a time. Vehicle attributes are joined from the vehicles
table. Rows missing energy_kwh are omitted entirely. Rows missing duration
are kept for week occupancy only (not session counts, connection time, or
energy).

Usage:
    uv run python src/ev-charging-us/histogram_by_vehicle.py

Writes:
    output/us_ev_by_vehicle_YYYYMMDD-HHMM.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = REPO_ROOT / "output"
DEFAULT_SESSIONS = REPO_ROOT / "data" / "ev-charging-us" / "evwatts.public.vehiclesessions.sorted-by-vehicle.csv"
DEFAULT_VEHICLES = REPO_ROOT / "data" / "ev-charging-us" / "evwatts.public.vehicles.csv"
SCRIPT_NAME = "us_ev_by_vehicle"

OUTPUT_COLUMNS = (
    "vehicle_id",
    "sessions",
    "total_connection_time",
    "total_energy_charged",
    "weeks_with_sessions",
    "weeks_without_sessions",
    "vehicle_type",
    "electrification_level",
    "ownership",
    "state",
)

SESSION_REQUIRED = ("id", "vehicle_id", "start_datetime", "duration", "energy_kwh")
VEHICLE_REQUIRED = ("id", "vehicle_type", "electrification_level", "ownership", "state")

VEHICLE_TYPE_MAP = {
    "PASSENGER CAR": "CAR",
    "MULTIPURPOSE PASSENGER VEHICLE (MPV)": "MPV",
    "BUS": "BUS",
}

ELECTRIFICATION_LEVEL_MAP = {
    "BEV (Battery Electric Vehicle)": "BEV",
    "PHEV (Plug-in Hybrid Electric Vehicle)": "PHEV",
}


@dataclass(frozen=True)
class Vehicle:
    vehicle_type: str
    electrification_level: str
    ownership: str
    state: str


@dataclass(frozen=True)
class Session:
    session_id: str
    plugin: datetime
    energy_kwh: float | None
    connection_time_h: float | None
    row_num: int

    @property
    def counts_toward_totals(self) -> bool:
        return self.connection_time_h is not None and self.energy_kwh is not None


@dataclass(frozen=True)
class VehicleAggregate:
    vehicle_id: str
    sessions: int
    total_connection_time: float
    total_energy_charged: float
    weeks_with_sessions: int
    weeks_without_sessions: int
    vehicle_type: str
    electrification_level: str
    ownership: str
    state: str


@dataclass
class SkipCounts:
    missing_duration: int = 0
    missing_energy: int = 0
    invalid_timestamp: int = 0
    empty_vehicle_id: int = 0


def parse_timestamp(value: str) -> datetime | None:
    value = value.strip().strip('"')
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d"):
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


def remap_label(value: str, mapping: dict[str, str], field: str, vehicle_id: str) -> str:
    if value not in mapping:
        raise SystemExit(
            f"Unexpected {field} {value!r} for vehicle_id {vehicle_id!r}; expected one of {sorted(mapping)}"
        )
    return mapping[value]


def format_number(value: float, decimals: int = 6) -> str:
    text = f"{value:.{decimals}f}".rstrip("0").rstrip(".")
    return text if text else "0"


def week_monday(d: date) -> date:
    """Return the Monday of the calendar week containing d (Mon–Sun weeks)."""
    return d - timedelta(days=d.weekday())


def count_weeks(plugin_dates: list[date]) -> tuple[int, int]:
    """Return (weeks_with_sessions, weeks_without_sessions).

    Weeks without sessions are counted only between the first and last session
    weeks inclusive (Monday–Sunday calendar weeks).
    """
    if not plugin_dates:
        raise ValueError("count_weeks requires at least one session date")

    weeks_with = {week_monday(d) for d in plugin_dates}
    first_monday = min(weeks_with)
    last_monday = max(weeks_with)
    span_weeks = ((last_monday - first_monday).days // 7) + 1
    weeks_without = span_weeks - len(weeks_with)
    if weeks_without < 0:
        raise SystemExit(f"Internal error: negative empty weeks (span={span_weeks}, with={len(weeks_with)})")
    return len(weeks_with), weeks_without


def load_vehicles(path: Path) -> dict[str, Vehicle]:
    """Load vehicle attributes keyed by vehicles.id."""
    vehicles: dict[str, Vehicle] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise SystemExit(f"Empty or unreadable CSV: {path}")

        field_map = {name.strip().strip('"'): name for name in reader.fieldnames}
        missing = set(VEHICLE_REQUIRED) - set(field_map)
        if missing:
            raise SystemExit(f"Missing required columns in {path}: {sorted(missing)}")

        for row_num, row in enumerate(reader, start=2):
            vehicle_id = row[field_map["id"]].strip().strip('"')
            if not vehicle_id:
                raise SystemExit(f"{path}:{row_num}: empty vehicle id")
            if vehicle_id in vehicles:
                raise SystemExit(f"{path}:{row_num}: duplicate vehicle id {vehicle_id!r}")
            vehicles[vehicle_id] = Vehicle(
                vehicle_type=remap_label(
                    row[field_map["vehicle_type"]].strip(),
                    VEHICLE_TYPE_MAP,
                    "vehicle_type",
                    vehicle_id,
                ),
                electrification_level=remap_label(
                    row[field_map["electrification_level"]].strip(),
                    ELECTRIFICATION_LEVEL_MAP,
                    "electrification_level",
                    vehicle_id,
                ),
                ownership=row[field_map["ownership"]].strip(),
                state=row[field_map["state"]].strip(),
            )

    if not vehicles:
        raise SystemExit(f"No data rows in {path}")
    return vehicles


def aggregate_vehicle(vehicle_id: str, sessions: list[Session], vehicle: Vehicle) -> VehicleAggregate:
    if not sessions:
        raise SystemExit(f"No sessions for vehicle_id {vehicle_id!r}")

    complete = [s for s in sessions if s.counts_toward_totals]
    weeks_with, weeks_without = count_weeks([s.plugin.date() for s in sessions])
    return VehicleAggregate(
        vehicle_id=vehicle_id,
        sessions=len(complete),
        total_connection_time=sum(s.connection_time_h or 0.0 for s in complete),
        total_energy_charged=sum(s.energy_kwh or 0.0 for s in complete),
        weeks_with_sessions=weeks_with,
        weeks_without_sessions=weeks_without,
        vehicle_type=vehicle.vehicle_type,
        electrification_level=vehicle.electrification_level,
        ownership=vehicle.ownership,
        state=vehicle.state,
    )


def aggregate_to_row(agg: VehicleAggregate) -> dict[str, str]:
    return {
        "vehicle_id": agg.vehicle_id,
        "sessions": str(agg.sessions),
        "total_connection_time": format_number(agg.total_connection_time),
        "total_energy_charged": format_number(agg.total_energy_charged),
        "weeks_with_sessions": str(agg.weeks_with_sessions),
        "weeks_without_sessions": str(agg.weeks_without_sessions),
        "vehicle_type": agg.vehicle_type,
        "electrification_level": agg.electrification_level,
        "ownership": agg.ownership,
        "state": agg.state,
    }


def parse_session(
    row: dict[str, str],
    field_map: dict[str, str],
    row_num: int,
    skips: SkipCounts,
) -> Session | None:
    session_id = row[field_map["id"]].strip().strip('"')
    plugin = parse_timestamp(row[field_map["start_datetime"]])
    duration = parse_float(row[field_map["duration"]])
    energy = parse_float(row[field_map["energy_kwh"]])

    if duration is None:
        skips.missing_duration += 1
    if energy is None:
        skips.missing_energy += 1
        return None

    if plugin is None:
        skips.invalid_timestamp += 1
        print(
            f"Row {row_num} session {session_id}: missing/invalid start_datetime",
            file=sys.stderr,
        )
        return None

    return Session(
        session_id=session_id,
        plugin=plugin,
        energy_kwh=energy if duration is not None else None,
        connection_time_h=duration,
        row_num=row_num,
    )


def iter_vehicle_groups(path: Path, vehicles: dict[str, Vehicle], skips: SkipCounts):
    """Yield (vehicle_id, sessions, vehicle) for each contiguous vehicle group.

    Hard-fails if a vehicle_id reappears after a different vehicle, since streaming
    aggregation assumes the file is grouped by vehicle_id.
    """
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise SystemExit(f"Empty or unreadable CSV: {path}")

        field_map = {name.strip().strip('"'): name for name in reader.fieldnames}
        missing = set(SESSION_REQUIRED) - set(field_map)
        if missing:
            raise SystemExit(f"Missing required columns in {path}: {sorted(missing)}")

        current_vehicle: str | None = None
        current_sessions: list[Session] = []
        finished_vehicles: set[str] = set()
        row_count = 0

        for row_num, row in enumerate(reader, start=2):
            row_count += 1
            vehicle_id = row[field_map["vehicle_id"]].strip().strip('"')
            if not vehicle_id:
                skips.empty_vehicle_id += 1
                print(f"Row {row_num}: empty vehicle_id", file=sys.stderr)
                continue
            if vehicle_id not in vehicles:
                raise SystemExit(f"Row {row_num}: vehicle_id {vehicle_id!r} not found in vehicles table")

            if current_vehicle is None:
                current_vehicle = vehicle_id
            elif vehicle_id != current_vehicle:
                if vehicle_id in finished_vehicles:
                    raise SystemExit(
                        f"Row {row_num}: vehicle_id {vehicle_id!r} reappears after other "
                        "vehicles; input must be grouped by vehicle_id for streaming aggregation"
                    )
                finished_vehicles.add(current_vehicle)
                yield current_vehicle, current_sessions, vehicles[current_vehicle]
                current_vehicle = vehicle_id
                current_sessions = []

            session = parse_session(row, field_map, row_num, skips)
            if session is None:
                continue
            current_sessions.append(session)

        if current_vehicle is not None:
            yield current_vehicle, current_sessions, vehicles[current_vehicle]

        if row_count == 0:
            raise SystemExit(f"No data rows in {path}")


def output_path(when: datetime | None = None) -> Path:
    stamp = (when or datetime.now()).strftime("%Y%m%d-%H%M")
    return OUTPUT_DIR / f"{SCRIPT_NAME}_{stamp}.csv"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_SESSIONS,
        help=f"Vehicle sessions CSV grouped by vehicle_id (default: {DEFAULT_SESSIONS})",
    )
    parser.add_argument(
        "--vehicles",
        type=Path,
        default=DEFAULT_VEHICLES,
        help=f"Vehicles lookup CSV (default: {DEFAULT_VEHICLES})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.input.is_file():
        print(f"Input file not found: {args.input}", file=sys.stderr)
        return 1
    if not args.vehicles.is_file():
        print(f"Vehicles file not found: {args.vehicles}", file=sys.stderr)
        return 1

    vehicles = load_vehicles(args.vehicles)
    path = output_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    vehicles_written = 0
    total_sessions = 0
    empty_vehicles = 0
    skips = SkipCounts()

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(OUTPUT_COLUMNS))
        writer.writeheader()

        for vehicle_id, sessions, vehicle in iter_vehicle_groups(args.input, vehicles, skips):
            if not sessions:
                empty_vehicles += 1
                print(
                    f"vehicle_id {vehicle_id!r}: no usable sessions after filtering",
                    file=sys.stderr,
                )
                continue
            agg = aggregate_vehicle(vehicle_id, sessions, vehicle)
            writer.writerow(aggregate_to_row(agg))
            vehicles_written += 1
            total_sessions += agg.sessions

    if empty_vehicles:
        raise SystemExit(f"{empty_vehicles} vehicle(s) had no usable sessions")
    if vehicles_written == 0:
        raise SystemExit("No vehicles written")

    print(f"Wrote {path}", file=sys.stderr)
    print(f"Vehicles: {vehicles_written:,}")
    print(f"Sessions: {total_sessions:,}")
    print(
        f"Missing duration (weeks only): {skips.missing_duration:,}; "
        f"omitted missing energy_kwh: {skips.missing_energy:,}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
