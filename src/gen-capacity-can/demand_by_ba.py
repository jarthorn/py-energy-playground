"""Disaggregate provincial demand to balancing authorities, then subtract wind and solar.

Provincial hourly demand is split with the population weights below. Net demand
is that split minus onshore wind and solar in the same hour. Net demand may be
negative, and is not clamped.

demand.csv labels the first hour 0 and leaves the hour-column header blank.
solar_gen_ba.csv and wind_gen_ba.csv label that same hour 1, under column `h`.
The script pairs them by row order and checks both labels. An authority with no
column in a generation file contributes 0 MW. A column that is not a configured
authority, a broken hour index, or a non-numeric cell aborts the run.

Usage:
    uv run python src/gen-capacity-can/demand_by_ba.py

Writes:
    output/demand_ba_YYYYMMDD-HHMM.csv
    output/net_demand_ba_YYYYMMDD-HHMM.csv

Both outputs label hours 1–8760 under column `h`, the same index as the generation
files. demand.csv hour 0 is output hour 1. Columns are balancing authorities,
alphabetical. Cells are whole megawatts: nearest MW, halves away from zero, and
any positive value below 1 MW is written as 1.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = REPO_ROOT / "output"
DATA_DIR = REPO_ROOT / "data" / "gen-capacity-can"
DEFAULT_DEMAND = DATA_DIR / "demand.csv"
DEFAULT_SOLAR = DATA_DIR / "solar_gen_ba.csv"
DEFAULT_WIND = DATA_DIR / "wind_gen_ba.csv"

HOURS_IN_YEAR = 8760
# demand.csv's first data row is hour 0. The generation files call that hour 1.
DEMAND_HOUR_ORIGIN = 0
GENERATION_HOUR_ORIGIN = 1

# Headcount of grid cells in each province assigned to each balancing authority.
# A province's demand in an hour is shared across these authorities in proportion
# to the weights. Replace this table to use a different split. Every weight must
# be a positive integer.
#
# Counts are the sum of gridcells.csv column `population`, grouped by province (`pr`)
# and balancing authority (`ba`). Two cells sit in one province and are served by
# another province's authority: grid cell 2068 (Quebec, population 15187) is Ontario.a,
# and grid cell 2870 (Quebec, population 0) is Newfoundland and Labrador.a. The
# zero-population cell is omitted, so Ontario.a receives a share of Quebec demand
# as well as its share of Ontario demand.
PROVINCE_BA_POPULATION: dict[str, dict[str, int]] = {
    "Alberta": {"Alberta.a": 4_269_532},
    "British Columbia": {"British Columbia.a": 4_993_982},
    "Manitoba": {"Manitoba.a": 1_341_217},
    "New Brunswick": {"New Brunswick.a": 785_275},
    "Newfoundland and Labrador": {
        "Newfoundland and Labrador.a": 485_613,
        "Newfoundland and Labrador.b": 18_294,
    },
    "Nova Scotia": {"Nova Scotia.a": 973_541},
    "Ontario": {
        "Ontario.a": 13_435_314,
        "Ontario.b": 765_558,
    },
    "Prince Edward Island": {"Prince Edward Island.a": 129_267},
    "Quebec": {
        "Ontario.a": 15_187,
        "Quebec.a": 7_867_232,
        "Quebec.b": 653_080,
    },
    "Saskatchewan": {"Saskatchewan.a": 1_134_115},
}


class DataError(Exception):
    """Input data broke an assumption. The script exits rather than write a bad file."""


def format_mw(value: float) -> str:
    """Nearest whole MW. Halves round away from zero, so 1.5 becomes 2 and -1.5 becomes -2.

    A positive value below 1 MW is written as 1, so it is not rounded down to 0.
    Zero stays 0. Negative values use the same nearest-MW rule.
    """
    if not math.isfinite(value):
        raise DataError(f"computed megawatts {value!r} is not a finite number")
    if 0 < value < 1:
        return "1"
    rounded = Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    text = format(rounded, "f")
    if text == "-0":
        return "0"
    return text


def validate_weights(weights: dict[str, dict[str, int]]) -> None:
    """Reject a split that cannot conserve provincial demand."""
    if not weights:
        raise DataError("Population weights are empty")
    for province, shares in weights.items():
        if not isinstance(province, str) or not province.strip() or province != province.strip():
            raise DataError(f"Population weights have an invalid province name: {province!r}")
        if not shares:
            raise DataError(f"{province} has no balancing authorities")
        for ba, population in shares.items():
            if not isinstance(ba, str) or not ba.strip() or ba != ba.strip():
                raise DataError(f"{province} has an invalid balancing authority name: {ba!r}")
            if isinstance(population, bool) or not isinstance(population, int) or population <= 0:
                raise DataError(f"{province} / {ba} population weight {population!r} must be a positive integer")


def balancing_authorities(weights: dict[str, dict[str, int]]) -> list[str]:
    return sorted({ba for shares in weights.values() for ba in shares})


def disaggregate_hour(demand_mw: dict[str, float], weights: dict[str, dict[str, int]]) -> dict[str, float]:
    """Split one hour of provincial demand across balancing authorities.

    An authority served from more than one province receives the sum of its shares.
    The shares of a province sum to that province's demand.
    """
    if set(demand_mw) != set(weights):
        missing = sorted(set(weights) - set(demand_mw))
        extra = sorted(set(demand_mw) - set(weights))
        detail = []
        if missing:
            detail.append(f"missing {', '.join(missing)}")
        if extra:
            detail.append(f"unexpected {', '.join(extra)}")
        raise DataError(f"Demand provinces do not match the population weights ({'; '.join(detail)})")
    totals: dict[str, float] = {}
    for province, shares in weights.items():
        mw = demand_mw[province]
        total_population = sum(shares.values())
        for ba, population in shares.items():
            totals[ba] = totals.get(ba, 0.0) + mw * population / total_population
    return totals


def net_demand_hour(
    demand_mw: dict[str, float],
    solar_mw: dict[str, float],
    wind_mw: dict[str, float],
) -> dict[str, float]:
    """Demand minus solar minus wind. Missing generation is 0. The result may be negative."""
    extras = (set(solar_mw) | set(wind_mw)) - set(demand_mw)
    if extras:
        names = ", ".join(sorted(extras))
        raise DataError(f"Generation includes balancing authorities with no demand: {names}")
    for source, values in (("solar", solar_mw), ("wind", wind_mw)):
        for ba, mw in values.items():
            if mw < 0:
                raise DataError(f"{source} generation for {ba} is negative ({mw})")
    return {ba: demand_mw[ba] - solar_mw.get(ba, 0.0) - wind_mw.get(ba, 0.0) for ba in demand_mw}


def location_columns(
    header: list[str],
    source: str,
    *,
    hour_header: str,
    allowed: set[str],
    required: set[str] | None = None,
) -> list[str]:
    if not header:
        raise DataError(f"{source} is empty")
    if header[0] != hour_header:
        expected = "blank" if hour_header == "" else repr(hour_header)
        raise DataError(f"{source} hour column header must be {expected}, found {header[0]!r}")
    names = header[1:]
    if not names:
        raise DataError(f"{source} has no location columns")
    seen: set[str] = set()
    for name in names:
        if not name:
            raise DataError(f"{source} has an empty column header")
        if name in seen:
            raise DataError(f"{source} repeats column {name!r}")
        seen.add(name)
        if name not in allowed:
            raise DataError(f"{source} has unexpected column {name!r}")
    if required is not None:
        missing = required - seen
        if missing:
            raise DataError(f"{source} is missing columns: {', '.join(sorted(missing))}")
    return names


def read_header(reader: csv.reader, source: str) -> list[str]:
    try:
        header = next(reader)
    except StopIteration as exc:
        raise DataError(f"{source} is empty") from exc
    return [cell.strip() for cell in header]


def parse_hour(value: str, *, source: str, expected: int) -> int:
    text = value.strip()
    if not text.isdigit():
        raise DataError(f"{source} hour column has {value!r} where {expected} was expected")
    hour = int(text)
    if hour != expected:
        raise DataError(f"{source} hour column is {hour} where {expected} was expected")
    return hour


def parse_mw(value: str, *, source: str, hour: int, column: str) -> float:
    text = value.strip()
    try:
        mw = float(text)
    except ValueError:
        raise DataError(f"{source} hour {hour} column {column} has {value!r}, which is not a number") from None
    if not math.isfinite(mw) or mw < 0:
        raise DataError(f"{source} hour {hour} column {column} has {value!r}; expected a non-negative number of MW")
    return mw


def read_hour(
    reader: csv.reader,
    source: str,
    columns: list[str],
    *,
    expected_hour: int,
    width: int,
    rows_read: int,
    hours_in_year: int,
) -> dict[str, float]:
    try:
        row = next(reader)
    except StopIteration as exc:
        raise DataError(f"{source} has {rows_read} hour rows; expected {hours_in_year}") from exc
    if not row:
        raise DataError(f"{source} hour column has '' where {expected_hour} was expected")
    hour = parse_hour(row[0], source=source, expected=expected_hour)
    if len(row) != width:
        raise DataError(f"{source} hour {hour} has {len(row)} columns; header has {width}")
    values = {}
    for index, column in enumerate(columns, start=1):
        values[column] = parse_mw(row[index], source=source, hour=hour, column=column)
    return values


def reject_extra_row(reader: csv.reader, source: str, hours_in_year: int) -> None:
    try:
        next(reader)
    except StopIteration:
        return
    raise DataError(f"{source} has more than {hours_in_year} hour rows")


def output_paths(output_dir: Path, when: datetime) -> tuple[Path, Path]:
    stamp = when.strftime("%Y%m%d-%H%M")
    return (output_dir / f"demand_ba_{stamp}.csv", output_dir / f"net_demand_ba_{stamp}.csv")


def write_ba_demand_files(
    demand_path: Path,
    solar_path: Path,
    wind_path: Path,
    output_dir: Path,
    *,
    weights: dict[str, dict[str, int]] | None = None,
    when: datetime | None = None,
    hours_in_year: int = HOURS_IN_YEAR,
) -> tuple[Path, Path, list[str]]:
    """Write disaggregated demand and net demand. A failure leaves neither file from this run."""
    shares = PROVINCE_BA_POPULATION if weights is None else weights
    validate_weights(shares)
    if GENERATION_HOUR_ORIGIN != DEMAND_HOUR_ORIGIN + 1:
        raise DataError("Generation hours must be the demand hour plus one")
    for path in (demand_path, solar_path, wind_path):
        if not path.is_file():
            raise DataError(f"Input file not found: {path}")

    authorities = balancing_authorities(shares)
    provinces = set(shares)
    allowed_authorities = set(authorities)
    dest_demand, dest_net = output_paths(output_dir, when or datetime.now())
    partials = [dest_demand.with_name(dest_demand.name + ".partial"), dest_net.with_name(dest_net.name + ".partial")]
    committed: list[Path] = []

    with (
        demand_path.open(newline="", encoding="utf-8-sig") as demand_handle,
        solar_path.open(newline="", encoding="utf-8-sig") as solar_handle,
        wind_path.open(newline="", encoding="utf-8-sig") as wind_handle,
    ):
        demand_reader = csv.reader(demand_handle)
        solar_reader = csv.reader(solar_handle)
        wind_reader = csv.reader(wind_handle)
        demand_header = read_header(demand_reader, demand_path.name)
        solar_header = read_header(solar_reader, solar_path.name)
        wind_header = read_header(wind_reader, wind_path.name)
        demand_columns = location_columns(
            demand_header,
            demand_path.name,
            hour_header="",
            allowed=provinces,
            required=provinces,
        )
        solar_columns = location_columns(
            solar_header,
            solar_path.name,
            hour_header="h",
            allowed=allowed_authorities,
        )
        wind_columns = location_columns(
            wind_header,
            wind_path.name,
            hour_header="h",
            allowed=allowed_authorities,
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            with (
                partials[0].open("w", newline="", encoding="utf-8") as demand_out,
                partials[1].open("w", newline="", encoding="utf-8") as net_out,
            ):
                demand_writer = csv.writer(demand_out)
                net_writer = csv.writer(net_out)
                demand_writer.writerow(["h", *authorities])
                net_writer.writerow(["h", *authorities])
                for index in range(hours_in_year):
                    demand_hour = DEMAND_HOUR_ORIGIN + index
                    generation_hour = GENERATION_HOUR_ORIGIN + index
                    demand_mw = read_hour(
                        demand_reader,
                        demand_path.name,
                        demand_columns,
                        expected_hour=demand_hour,
                        width=len(demand_header),
                        rows_read=index,
                        hours_in_year=hours_in_year,
                    )
                    solar_mw = read_hour(
                        solar_reader,
                        solar_path.name,
                        solar_columns,
                        expected_hour=generation_hour,
                        width=len(solar_header),
                        rows_read=index,
                        hours_in_year=hours_in_year,
                    )
                    wind_mw = read_hour(
                        wind_reader,
                        wind_path.name,
                        wind_columns,
                        expected_hour=generation_hour,
                        width=len(wind_header),
                        rows_read=index,
                        hours_in_year=hours_in_year,
                    )
                    by_authority = disaggregate_hour(demand_mw, shares)
                    net = net_demand_hour(by_authority, solar_mw, wind_mw)
                    demand_writer.writerow([str(generation_hour), *(format_mw(by_authority[ba]) for ba in authorities)])
                    net_writer.writerow([str(generation_hour), *(format_mw(net[ba]) for ba in authorities)])
                reject_extra_row(demand_reader, demand_path.name, hours_in_year)
                reject_extra_row(solar_reader, solar_path.name, hours_in_year)
                reject_extra_row(wind_reader, wind_path.name, hours_in_year)
            partials[0].replace(dest_demand)
            committed.append(dest_demand)
            partials[1].replace(dest_net)
            committed.append(dest_net)
        except Exception:
            for path in partials:
                path.unlink(missing_ok=True)
            for path in committed:
                path.unlink(missing_ok=True)
            raise
    return dest_demand, dest_net, authorities


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    parse_args(argv)
    try:
        dest_demand, dest_net, authorities = write_ba_demand_files(
            DEFAULT_DEMAND,
            DEFAULT_SOLAR,
            DEFAULT_WIND,
            OUTPUT_DIR,
        )
    except DataError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        f"Wrote {dest_demand} and {dest_net} ({HOURS_IN_YEAR} hours, {len(authorities)} balancing authorities)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
