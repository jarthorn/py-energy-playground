"""Per-user histogram of Dataset1 charging sessions.

Streams the input (grouped by user_id) so only one user's sessions are held in
memory at a time. Missing connection_time values are inferred from that user's
average charge rate (kWh / hour) on sessions that do report connection_time.

Usage:
    uv run python src/ev-charging-norway/histogram_by_user.py

Writes:
    output/norway_ev_by_user_YYYYMMDD-HHMM.csv
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
DEFAULT_INPUT = REPO_ROOT / "data" / "ev-charging-norway" / "Dataset1_charging_reports.csv"
SCRIPT_NAME = "norway_ev_by_user"

OUTPUT_COLUMNS = (
    "user_id",
    "sessions",
    "total_connection_time",
    "total_energy_charged",
    "weeks_with_sessions",
    "weeks_without_sessions",
)


@dataclass(frozen=True)
class Session:
    session_id: str
    plugin: datetime
    energy_kwh: float
    connection_time_h: float | None
    row_num: int


@dataclass(frozen=True)
class UserAggregate:
    user_id: str
    sessions: int
    total_connection_time: float
    total_energy_charged: float
    weeks_with_sessions: int
    weeks_without_sessions: int
    inferred_sessions: int


def parse_timestamp(value: str) -> datetime | None:
    value = value.strip().strip('"')
    if not value or value.upper() == "NA":
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def parse_european_number(value: str) -> float | None:
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


def average_charge_rate_kw(sessions: list[Session]) -> float | None:
    """Mean charge rate (kWh/h == kW) from sessions with known connection time.

    Sessions with non-positive connection_time are excluded from the average.
    Returns None if no usable rate samples exist.
    """
    rates: list[float] = []
    for session in sessions:
        if session.connection_time_h is None:
            continue
        if session.connection_time_h <= 0:
            continue
        rates.append(session.energy_kwh / session.connection_time_h)
    if not rates:
        return None
    return sum(rates) / len(rates)


def resolve_connection_times(sessions: list[Session]) -> tuple[list[float], int]:
    """Return per-session connection times (hours) and count of inferred values."""
    missing = [s for s in sessions if s.connection_time_h is None]
    rate: float | None = None
    if missing:
        rate = average_charge_rate_kw(sessions)
        if rate is None:
            ids = ", ".join(s.session_id or f"row {s.row_num}" for s in missing[:5])
            raise SystemExit(
                "Cannot infer connection_time: user has sessions with missing "
                f"connection_time but no sessions with positive connection_time "
                f"to estimate a charge rate (e.g. {ids})"
            )
        if rate <= 0:
            raise SystemExit(f"Cannot infer connection_time: non-positive average charge rate {rate}")

    times: list[float] = []
    inferred = 0
    for session in sessions:
        if session.connection_time_h is not None:
            times.append(session.connection_time_h)
            continue
        assert rate is not None  # guaranteed when any connection_time is missing
        # energy_kwh / (kWh/h) → hours
        times.append(session.energy_kwh / rate)
        inferred += 1
    return times, inferred


def aggregate_user(user_id: str, sessions: list[Session]) -> UserAggregate:
    if not sessions:
        raise SystemExit(f"No sessions for user_id {user_id!r}")

    connection_times, inferred = resolve_connection_times(sessions)
    weeks_with, weeks_without = count_weeks([s.plugin.date() for s in sessions])

    return UserAggregate(
        user_id=user_id,
        sessions=len(sessions),
        total_connection_time=sum(connection_times),
        total_energy_charged=sum(s.energy_kwh for s in sessions),
        weeks_with_sessions=weeks_with,
        weeks_without_sessions=weeks_without,
        inferred_sessions=inferred,
    )


def aggregate_to_row(agg: UserAggregate) -> dict[str, str]:
    return {
        "user_id": agg.user_id,
        "sessions": str(agg.sessions),
        "total_connection_time": format_number(agg.total_connection_time),
        "total_energy_charged": format_number(agg.total_energy_charged),
        "weeks_with_sessions": str(agg.weeks_with_sessions),
        "weeks_without_sessions": str(agg.weeks_without_sessions),
    }


def parse_session(row: dict[str, str], field_map: dict[str, str], row_num: int) -> Session | None:
    session_id = row[field_map["session_id"]].strip().strip('"')
    plugin = parse_timestamp(row[field_map["plugin_time"]])
    energy = parse_european_number(row[field_map["energy_session"]])
    connection = parse_european_number(row[field_map["connection_time"]])

    raw_ct = row[field_map["connection_time"]].strip().strip('"')
    if connection is None and raw_ct and raw_ct.upper() != "NA":
        print(
            f"Row {row_num} session {session_id}: invalid connection_time {raw_ct!r}",
            file=sys.stderr,
        )
        return None

    if plugin is None:
        print(
            f"Row {row_num} session {session_id}: missing/invalid plugin_time",
            file=sys.stderr,
        )
        return None
    if energy is None:
        print(
            f"Row {row_num} session {session_id}: missing/invalid energy_session",
            file=sys.stderr,
        )
        return None

    return Session(
        session_id=session_id,
        plugin=plugin,
        energy_kwh=energy,
        connection_time_h=connection,
        row_num=row_num,
    )


def iter_user_groups(path: Path):
    """Yield (user_id, sessions) for each contiguous user group in the CSV.

    Hard-fails if a user_id reappears after a different user, since streaming
    aggregation assumes the file is grouped by user_id.
    """
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        if reader.fieldnames is None:
            raise SystemExit(f"Empty or unreadable CSV: {path}")

        field_map = {name.strip().strip('"'): name for name in reader.fieldnames}
        required = {
            "user_id",
            "session_id",
            "plugin_time",
            "connection_time",
            "energy_session",
        }
        missing = required - set(field_map)
        if missing:
            raise SystemExit(f"Missing required columns in {path}: {sorted(missing)}")

        current_user: str | None = None
        current_sessions: list[Session] = []
        finished_users: set[str] = set()
        skipped = 0
        row_count = 0

        for row_num, row in enumerate(reader, start=2):
            row_count += 1
            user_id = row[field_map["user_id"]].strip().strip('"')
            if not user_id:
                print(f"Row {row_num}: empty user_id", file=sys.stderr)
                skipped += 1
                continue

            if current_user is None:
                current_user = user_id
            elif user_id != current_user:
                if user_id in finished_users:
                    raise SystemExit(
                        f"Row {row_num}: user_id {user_id!r} reappears after other users; "
                        "input must be grouped by user_id for streaming aggregation"
                    )
                finished_users.add(current_user)
                yield current_user, current_sessions
                current_user = user_id
                current_sessions = []

            session = parse_session(row, field_map, row_num)
            if session is None:
                skipped += 1
                continue
            current_sessions.append(session)

        if current_user is not None:
            yield current_user, current_sessions

        if row_count == 0:
            raise SystemExit(f"No data rows in {path}")
        if skipped:
            print(f"Skipped {skipped} unusable row(s)", file=sys.stderr)


def output_path(when: datetime | None = None) -> Path:
    stamp = (when or datetime.now()).strftime("%Y%m%d-%H%M")
    return OUTPUT_DIR / f"{SCRIPT_NAME}_{stamp}.csv"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Dataset1 charging reports CSV (default: {DEFAULT_INPUT})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.input.is_file():
        print(f"Input file not found: {args.input}", file=sys.stderr)
        return 1

    path = output_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    users_written = 0
    total_sessions = 0
    total_inferred = 0
    empty_users = 0

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(OUTPUT_COLUMNS))
        writer.writeheader()

        for user_id, sessions in iter_user_groups(args.input):
            if not sessions:
                empty_users += 1
                print(
                    f"user_id {user_id!r}: no usable sessions after filtering",
                    file=sys.stderr,
                )
                continue
            agg = aggregate_user(user_id, sessions)
            writer.writerow(aggregate_to_row(agg))
            users_written += 1
            total_sessions += agg.sessions
            total_inferred += agg.inferred_sessions
            if agg.inferred_sessions:
                print(
                    f"user_id {user_id}: inferred connection_time for {agg.inferred_sessions} session(s)",
                    file=sys.stderr,
                )

    if empty_users:
        raise SystemExit(f"{empty_users} user(s) had no usable sessions")
    if users_written == 0:
        raise SystemExit("No users written")

    print(f"Wrote {path}", file=sys.stderr)
    print(f"Users: {users_written}")
    print(f"Sessions: {total_sessions}")
    print(f"Inferred connection times: {total_inferred}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
