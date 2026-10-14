"""Aggregate Oslo EV charging sessions by ambient temperature bin.

Joins Dataset1 charging sessions (Europe/Oslo local time) with SN18700 hourly
temperature (UTC). Sessions are binned by mean temperature over the session;
calendar days are binned by daily minimum temperature.

Usage:
    uv run python src/ev-charging-norway/aggregate_oslo_ev_temp.py

Writes:
    output/oslo_ev_temp_all_YYYYMMDD-HHMM.csv
    output/oslo_ev_temp_weekday_YYYYMMDD-HHMM.csv
    output/oslo_ev_temp_weekend_YYYYMMDD-HHMM.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = REPO_ROOT / "output"
DEFAULT_SESSIONS = REPO_ROOT / "data" / "ev-charging-norway" / "Dataset1_charging_reports.csv"
DEFAULT_TEMP_DIR = REPO_ROOT / "data" / "ev-charging-norway"
SCRIPT_NAME = "oslo_ev_temp"

OSLO = ZoneInfo("Europe/Oslo")
UTC = timezone.utc

# Half-open interior bins of this width (°C), with open ends below TEMP_BIN_FLOOR
# and at/above TEMP_BIN_CEILING. Example with size 5, floor -15, ceiling 20:
#   <-15, [-15,-10), [-10,-5), ..., [15,20), >=20
TEMP_BIN_SIZE_C = 5
TEMP_BIN_FLOOR_C = -15
TEMP_BIN_CEILING_C = 20

MIN_HOUR_OVERLAP = timedelta(minutes=30)

OUTPUT_COLUMNS = (
    "temperature_bin",
    "sessions",
    "days_with_daily_low_in_bin",
    "total_kwh",
    "kwh_per_day",
    "kwh_per_session",
    "sessions_per_user",
)


@dataclass(frozen=True)
class Session:
    user_id: str
    session_id: str
    plugin: datetime
    plugout: datetime
    energy_kwh: float
    mean_temp_c: float

    @property
    def is_weekend(self) -> bool:
        # Monday=0 ... Sunday=6; weekend = Saturday/Sunday
        return self.plugin.weekday() >= 5


def parse_local_timestamp(value: str) -> datetime | None:
    value = value.strip()
    if not value or value.upper() == "NA":
        return None
    try:
        naive = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return naive.replace(tzinfo=OSLO)


def parse_number(value: str) -> float | None:
    value = value.strip().replace(",", ".")
    if not value or value.upper() == "NA":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def format_number(value: float, decimals: int = 4) -> str:
    text = f"{value:.{decimals}f}".rstrip("0").rstrip(".")
    return text if text else "0"


def temperature_bin_label(temp_c: float) -> str:
    if temp_c < TEMP_BIN_FLOOR_C:
        return f"<{TEMP_BIN_FLOOR_C}"
    if temp_c >= TEMP_BIN_CEILING_C:
        return f">={TEMP_BIN_CEILING_C}"
    # Floor toward -inf into bin_size steps, clamped to [floor, ceiling).
    offset = temp_c - TEMP_BIN_FLOOR_C
    bin_index = int(offset // TEMP_BIN_SIZE_C)
    lo = TEMP_BIN_FLOOR_C + bin_index * TEMP_BIN_SIZE_C
    hi = lo + TEMP_BIN_SIZE_C
    return f"[{lo},{hi})"


def all_temperature_bin_labels() -> list[str]:
    labels = [f"<{TEMP_BIN_FLOOR_C}"]
    lo = TEMP_BIN_FLOOR_C
    while lo < TEMP_BIN_CEILING_C:
        hi = lo + TEMP_BIN_SIZE_C
        labels.append(f"[{lo},{hi})")
        lo = hi
    labels.append(f">={TEMP_BIN_CEILING_C}")
    return labels


def load_hourly_temperatures(temp_dir: Path) -> dict[datetime, float]:
    """Load SN18700 hourly temps keyed by aware UTC hour (minute=second=0)."""
    paths = sorted(temp_dir.glob("SN18700_hourly_*.csv"))
    if not paths:
        raise SystemExit(f"No SN18700_hourly_*.csv files found in {temp_dir}")

    temps: dict[datetime, float] = {}
    for path in paths:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or "hour" not in reader.fieldnames:
                raise SystemExit(f"Unexpected temperature CSV header in {path}")
            for row_num, row in enumerate(reader, start=2):
                hour_raw = (row.get("hour") or "").strip()
                temp_raw = (row.get("temperature") or "").strip()
                if not hour_raw:
                    raise SystemExit(f"Missing hour in {path} line {row_num}")
                if not temp_raw:
                    raise SystemExit(f"Missing temperature in {path} line {row_num} ({hour_raw})")
                hour = datetime.fromisoformat(hour_raw.replace("Z", "+00:00"))
                if hour.tzinfo is None:
                    hour = hour.replace(tzinfo=UTC)
                else:
                    hour = hour.astimezone(UTC)
                hour = hour.replace(minute=0, second=0, microsecond=0)
                temps[hour] = float(temp_raw)
    return temps


def overlapping_hours(plugin: datetime, plugout: datetime) -> list[tuple[datetime, timedelta]]:
    """Return (UTC hour start, overlap duration) for each hour overlapping the session."""
    if plugout <= plugin:
        return []

    start_utc = plugin.astimezone(UTC)
    end_utc = plugout.astimezone(UTC)
    hour = start_utc.replace(minute=0, second=0, microsecond=0)
    overlaps: list[tuple[datetime, timedelta]] = []
    while hour < end_utc:
        hour_end = hour + timedelta(hours=1)
        overlap_start = max(start_utc, hour)
        overlap_end = min(end_utc, hour_end)
        if overlap_end > overlap_start:
            overlaps.append((hour, overlap_end - overlap_start))
        hour = hour_end
    return overlaps


def session_mean_temperature(
    plugin: datetime,
    plugout: datetime,
    temps: dict[datetime, float],
    session_id: str,
) -> float | None:
    """Mean of hourly temps over the session; drop trailing hour if overlap < 30 minutes."""
    overlaps = overlapping_hours(plugin, plugout)
    if not overlaps:
        print(
            f"No overlapping hours for session {session_id} ({plugin.isoformat()} -> {plugout.isoformat()})",
            file=sys.stderr,
        )
        return None

    selected: list[float] = []
    for index, (hour, overlap) in enumerate(overlaps):
        is_last = index == len(overlaps) - 1
        # Drop only a trailing stub of a multi-hour session; keep sole short hours.
        if is_last and len(overlaps) > 1 and overlap < MIN_HOUR_OVERLAP:
            continue
        if hour not in temps:
            print(
                f"Missing temperature for session {session_id} at UTC hour {hour.isoformat()}",
                file=sys.stderr,
            )
            return None
        selected.append(temps[hour])

    if not selected:
        print(
            f"No usable temperature hours for session {session_id}",
            file=sys.stderr,
        )
        return None
    return sum(selected) / len(selected)


@dataclass(frozen=True)
class LoadedSessions:
    sessions: list[Session]
    location_filtered_sessions: int
    location_filtered_users: int


def load_oslo_sessions(path: Path, temps: dict[datetime, float]) -> LoadedSessions:
    sessions: list[Session] = []
    location_filtered_sessions = 0
    location_filtered_users: set[str] = set()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        required = {
            "location",
            "user_id",
            "session_id",
            "plugin_time",
            "plugout_time",
            "energy_session",
        }
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise SystemExit(f"Unexpected sessions CSV header in {path}")

        for row_num, row in enumerate(reader, start=2):
            location = (row.get("location") or "").strip()
            if not location.startswith("OSL"):
                continue

            location_filtered_sessions += 1
            session_id = (row.get("session_id") or "").strip()
            user_id = (row.get("user_id") or "").strip()
            if user_id:
                location_filtered_users.add(user_id)

            plugin = parse_local_timestamp(row.get("plugin_time") or "")
            plugout = parse_local_timestamp(row.get("plugout_time") or "")
            energy = parse_number(row.get("energy_session") or "")

            if plugin is None or plugout is None:
                print(
                    f"Skipping session {session_id or f'row {row_num}'}: invalid plugin/plugout timestamp",
                    file=sys.stderr,
                )
                continue
            if energy is None:
                print(
                    f"Skipping session {session_id}: invalid energy_session",
                    file=sys.stderr,
                )
                continue
            if plugout <= plugin:
                print(
                    f"Skipping session {session_id}: plugout is not after plugin",
                    file=sys.stderr,
                )
                continue

            mean_temp = session_mean_temperature(plugin, plugout, temps, session_id)
            if mean_temp is None:
                continue

            sessions.append(
                Session(
                    user_id=user_id,
                    session_id=session_id,
                    plugin=plugin,
                    plugout=plugout,
                    energy_kwh=energy,
                    mean_temp_c=mean_temp,
                )
            )
    return LoadedSessions(
        sessions=sessions,
        location_filtered_sessions=location_filtered_sessions,
        location_filtered_users=len(location_filtered_users),
    )


def daily_lows(
    temps: dict[datetime, float],
    start_day: date,
    end_day: date,
) -> dict[date, float]:
    """Daily minimum temperature for each Europe/Oslo calendar day in [start_day, end_day]."""
    if end_day < start_day:
        raise SystemExit("Invalid day range: end before start")

    by_day: dict[date, list[float]] = defaultdict(list)
    for hour_utc, temp in temps.items():
        local_day = hour_utc.astimezone(OSLO).date()
        if start_day <= local_day <= end_day:
            by_day[local_day].append(temp)

    lows: dict[date, float] = {}
    day = start_day
    while day <= end_day:
        values = by_day.get(day)
        if not values:
            raise SystemExit(f"No temperature observations for Oslo calendar day {day.isoformat()}")
        # A complete civil day should have 23, 24, or 25 hourly samples (DST).
        if len(values) < 23:
            raise SystemExit(f"Incomplete temperature coverage for {day.isoformat()}: {len(values)} hourly values")
        lows[day] = min(values)
        day += timedelta(days=1)
    return lows


def aggregate(
    sessions: list[Session],
    day_lows: dict[date, float],
    unique_users: int,
    calendar_filter: str,
) -> list[dict[str, str]]:
    if calendar_filter == "all":
        selected = sessions
        days = list(day_lows.items())
    elif calendar_filter == "weekday":
        selected = [s for s in sessions if not s.is_weekend]
        days = [(d, t) for d, t in day_lows.items() if d.weekday() < 5]
    elif calendar_filter == "weekend":
        selected = [s for s in sessions if s.is_weekend]
        days = [(d, t) for d, t in day_lows.items() if d.weekday() >= 5]
    else:
        raise SystemExit(f"Unknown calendar filter: {calendar_filter}")

    sessions_by_bin: dict[str, int] = defaultdict(int)
    kwh_by_bin: dict[str, float] = defaultdict(float)
    for session in selected:
        label = temperature_bin_label(session.mean_temp_c)
        sessions_by_bin[label] += 1
        kwh_by_bin[label] += session.energy_kwh

    days_by_bin: dict[str, int] = defaultdict(int)
    for _, low in days:
        days_by_bin[temperature_bin_label(low)] += 1

    if unique_users <= 0:
        raise SystemExit("No unique users available for sessions_per_user")

    rows: list[dict[str, str]] = []
    for label in all_temperature_bin_labels():
        a = sessions_by_bin.get(label, 0)
        b = days_by_bin.get(label, 0)
        c = kwh_by_bin.get(label, 0.0)

        kwh_per_day = format_number(c / b) if b else ""
        kwh_per_session = format_number(c / a) if a else ""
        sessions_per_user = format_number(a / unique_users)

        rows.append(
            {
                "temperature_bin": label,
                "sessions": str(a),
                "days_with_daily_low_in_bin": str(b),
                "total_kwh": format_number(c),
                "kwh_per_day": kwh_per_day,
                "kwh_per_session": kwh_per_session,
                "sessions_per_user": sessions_per_user,
            }
        )
    return rows


def output_path(calendar_filter: str, when: datetime | None = None) -> Path:
    stamp = (when or datetime.now()).strftime("%Y%m%d-%H%M")
    return OUTPUT_DIR / f"{SCRIPT_NAME}_{calendar_filter}_{stamp}.csv"


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(OUTPUT_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sessions",
        type=Path,
        default=DEFAULT_SESSIONS,
        help=f"Charging sessions CSV (default: {DEFAULT_SESSIONS})",
    )
    parser.add_argument(
        "--temp-dir",
        type=Path,
        default=DEFAULT_TEMP_DIR,
        help=f"Directory with SN18700_hourly_YYYY.csv (default: {DEFAULT_TEMP_DIR})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if TEMP_BIN_SIZE_C <= 0:
        raise SystemExit("TEMP_BIN_SIZE_C must be positive")
    if (TEMP_BIN_CEILING_C - TEMP_BIN_FLOOR_C) % TEMP_BIN_SIZE_C != 0:
        raise SystemExit("TEMP_BIN_CEILING_C - TEMP_BIN_FLOOR_C must be divisible by TEMP_BIN_SIZE_C")

    args = parse_args(argv)
    if not args.sessions.is_file():
        print(f"Sessions file not found: {args.sessions}", file=sys.stderr)
        return 1
    if not args.temp_dir.is_dir():
        print(f"Temperature directory not found: {args.temp_dir}", file=sys.stderr)
        return 1

    temps = load_hourly_temperatures(args.temp_dir)
    loaded = load_oslo_sessions(args.sessions, temps)
    if not loaded.sessions:
        print("No usable Oslo sessions after filtering", file=sys.stderr)
        return 1

    unique_users = loaded.location_filtered_users
    start_day = min(s.plugin.date() for s in loaded.sessions)
    end_day = max(s.plugout.date() for s in loaded.sessions)
    day_lows = daily_lows(temps, start_day, end_day)

    stamp = datetime.now()
    for calendar_filter in ("all", "weekday", "weekend"):
        rows = aggregate(loaded.sessions, day_lows, unique_users, calendar_filter)
        path = output_path(calendar_filter, when=stamp)
        write_csv(path, rows)
        print(f"Wrote {path}", file=sys.stderr)

    print(f"Total sessions (after location filter): {loaded.location_filtered_sessions}")
    print(f"Total unique users (after location filter): {loaded.location_filtered_users}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
