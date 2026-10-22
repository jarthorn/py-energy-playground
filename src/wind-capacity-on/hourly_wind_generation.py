"""Hourly onshore wind generation for one balancing authority.

Joins extant onshore wind nameplate capacity with grid-cell balancing
authorities, then multiplies each site's nameplate by its hourly capacity
factor. The result is one CSV: rows are hours 1–8760, columns are grid cells
in the balancing authority.

Usage:
    uv run python src/wind-capacity-on/hourly_wind_generation.py
    uv run python src/wind-capacity-on/hourly_wind_generation.py --ba Ontario.b

Writes:
    output/wind-capacity-on_<ba>_<year>_YYYYMMDD-HHMM.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = REPO_ROOT / "output"
DATA_DIR = REPO_ROOT / "data" / "wind-capacity-on"
DEFAULT_EXTANT = DATA_DIR / "extant_wind_solar.csv"
DEFAULT_GRIDCELLS = DATA_DIR / "gridcells.csv"
DEFAULT_WINDCF = DATA_DIR / "windcf.csv"
SCRIPT_NAME = "wind-capacity-on"

# Period column in extant_wind_solar.csv. Hard-coded to the 2025 fleet;
# set this to a later column (2030, 2035, 2040, 2045, 2050) to revisit
# nameplate still in service in that year.
NAMEPLATE_YEAR = "2025"

DEFAULT_BA = "Ontario.a"
HOURS_IN_YEAR = 8760
WIND_ONS_SUFFIX = ".wind_ons"
SOLAR_SUFFIX = ".solar"
# COPPER exports gridcells.csv and extant_wind_solar.csv with a UTF-8 BOM.
INPUT_ENCODING = "utf-8-sig"


class DataError(Exception):
    """Input data broke an assumption. The script exits rather than write a bad file."""

    def __init__(self, message: str, mismatches: list[LocationMismatch] | None = None) -> None:
        super().__init__(message)
        self.mismatches = list(mismatches or [])


@dataclass(frozen=True)
class WindLocation:
    grid_cell: int
    nameplate_mw: float


@dataclass(frozen=True)
class LocationMismatch:
    grid_cell: int
    message: str


def format_mw(value: float) -> str:
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text if text else "0"


def load_grid_cells(path: Path) -> dict[int, str]:
    """Map grid cell id to balancing authority."""
    cells: dict[int, str] = {}
    with path.open(newline="", encoding=INPUT_ENCODING) as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        if "grid_cell" not in fieldnames or "ba" not in fieldnames:
            raise DataError(f"{path.name} must have grid_cell and ba columns")
        for row_num, row in enumerate(reader, start=2):
            raw_id = (row.get("grid_cell") or "").strip()
            if not raw_id.isdigit():
                raise DataError(f"{path.name} row {row_num} has grid cell {raw_id!r}, which is not an integer id")
            grid_cell = int(raw_id)
            ba = (row.get("ba") or "").strip()
            if not ba:
                raise DataError(f"{path.name} row {row_num} grid cell {grid_cell} has an empty balancing authority")
            if grid_cell in cells:
                raise DataError(f"{path.name} lists grid cell {grid_cell} more than once")
            cells[grid_cell] = ba
    if not cells:
        raise DataError(f"{path.name} has no grid cells")
    return cells


def parse_nameplate(value: str, location: str, year: str) -> float:
    text = value.strip()
    try:
        mw = float(text)
    except ValueError:
        raise DataError(
            f"extant_wind_solar.csv location {location} has {year} nameplate {value!r}, which is not a number"
        ) from None
    if not math.isfinite(mw) or mw < 0:
        raise DataError(
            f"extant_wind_solar.csv location {location} has {year} nameplate {value!r}, "
            "which is not a non-negative MW value"
        )
    return mw


def select_locations(
    extant_path: Path,
    gridcells_path: Path,
    ba: str,
    year: str = NAMEPLATE_YEAR,
) -> tuple[list[WindLocation], list[LocationMismatch]]:
    """Onshore wind sites in `ba` with positive nameplate in `year`.

    A wind_ons grid cell missing from gridcells.csv is reported and skipped.
    Sites in other balancing authorities, solar rows, and zero nameplate are omitted.
    """
    cells = load_grid_cells(gridcells_path)
    known_bas = set(cells.values())
    mismatches: list[LocationMismatch] = []
    seen: dict[int, str] = {}
    chosen: list[WindLocation] = []

    with extant_path.open(newline="", encoding=INPUT_ENCODING) as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        if "location" not in fieldnames:
            raise DataError(f"{extant_path.name} must have a location column")
        if year not in fieldnames:
            raise DataError(f"{extant_path.name} has no {year} nameplate column")
        for row_num, row in enumerate(reader, start=2):
            location = (row.get("location") or "").strip()
            if location.endswith(SOLAR_SUFFIX):
                continue
            if not location.endswith(WIND_ONS_SUFFIX):
                raise DataError(
                    f"{extant_path.name} row {row_num} location {location!r} "
                    f"is neither {WIND_ONS_SUFFIX} nor {SOLAR_SUFFIX}"
                )
            raw_id = location[: -len(WIND_ONS_SUFFIX)]
            if not raw_id.isdigit():
                raise DataError(f"{extant_path.name} row {row_num} location {location!r} has no integer grid cell id")
            grid_cell = int(raw_id)
            if grid_cell in seen:
                raise DataError(
                    f"{extant_path.name} lists grid cell {grid_cell} more than once ({seen[grid_cell]} and {location})"
                )
            seen[grid_cell] = location
            nameplate = parse_nameplate(row.get(year) or "", location, year)
            if grid_cell not in cells:
                mismatches.append(
                    LocationMismatch(
                        grid_cell,
                        (
                            f"{extant_path.name} location {location} refers to grid cell {grid_cell}, "
                            f"which is not in {gridcells_path.name}; skipping"
                        ),
                    )
                )
                continue
            if cells[grid_cell] != ba or nameplate == 0:
                continue
            chosen.append(WindLocation(grid_cell, nameplate))

    mismatches.sort(key=lambda item: item.grid_cell)
    chosen.sort(key=lambda item: item.grid_cell)

    if ba not in known_bas:
        known = ", ".join(sorted(known_bas))
        raise DataError(f"Unknown balancing authority {ba!r}. Known values: {known}", mismatches)
    if not chosen:
        raise DataError(
            f"No extant onshore wind with positive {year} nameplate capacity in {ba!r}.",
            mismatches,
        )
    return chosen, mismatches


def windcf_column_index(header: list[str], source: str) -> dict[int, int]:
    if not header or header[0].strip() != "h":
        raise DataError(f"{source} header must start with column 'h'")
    index: dict[int, int] = {}
    for position, name in enumerate(header[1:], start=1):
        raw_id = name.strip()
        if not raw_id.isdigit():
            raise DataError(f"{source} column {raw_id!r} is not a grid cell id")
        grid_cell = int(raw_id)
        if grid_cell in index:
            raise DataError(f"{source} has a duplicate column for grid cell {grid_cell}")
        index[grid_cell] = position
    return index


def parse_capacity_factor(value: str, *, source: str, hour: int, grid_cell: int) -> float:
    try:
        factor = float(value.strip())
    except ValueError:
        raise DataError(
            f"{source} hour {hour} grid cell {grid_cell} has capacity factor {value!r}, which is not a number"
        ) from None
    if not math.isfinite(factor) or factor < 0 or factor > 1:
        raise DataError(
            f"{source} hour {hour} grid cell {grid_cell} has capacity factor {value!r}; expected a number in [0, 1]"
        )
    return factor


def write_hourly_generation(
    windcf_path: Path,
    locations: list[WindLocation],
    dest: Path,
    *,
    hours_in_year: int = HOURS_IN_YEAR,
) -> tuple[list[WindLocation], list[LocationMismatch]]:
    """Stream windcf.csv and write MW output for the given locations.

    Locations with no windcf column are reported and omitted. A structural problem
    in windcf.csv (hour index, row width, non-numeric factor) aborts with no output file.
    """
    if not locations:
        raise DataError("No wind locations to write")

    source = windcf_path.name
    with windcf_path.open(newline="", encoding=INPUT_ENCODING) as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise DataError(f"{source} is empty") from exc
        columns = windcf_column_index(header, source)
        header_width = len(header)

        mismatches: list[LocationMismatch] = []
        kept: list[WindLocation] = []
        for location in locations:
            if location.grid_cell not in columns:
                mismatches.append(
                    LocationMismatch(
                        location.grid_cell,
                        f"{source} has no column for grid cell {location.grid_cell}; skipping",
                    )
                )
                continue
            kept.append(location)
        mismatches.sort(key=lambda item: item.grid_cell)
        kept.sort(key=lambda item: item.grid_cell)
        if not kept:
            raise DataError("No selected locations are present in windcf.csv.", mismatches)

        partial = dest.with_name(dest.name + ".partial")
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            with partial.open("w", newline="", encoding="utf-8") as out_handle:
                writer = csv.writer(out_handle)
                writer.writerow(["h", *(str(location.grid_cell) for location in kept)])
                expected_hour = 1
                for row in reader:
                    raw_hour = row[0].strip() if row else ""
                    if not raw_hour.isdigit():
                        raise DataError(
                            f"{source} hour column has {raw_hour!r} where {expected_hour} was expected",
                            mismatches,
                        )
                    hour = int(raw_hour)
                    if hour != expected_hour:
                        raise DataError(
                            f"{source} hour column is {hour} where {expected_hour} was expected",
                            mismatches,
                        )
                    if len(row) != header_width:
                        raise DataError(
                            f"{source} hour {hour} has {len(row)} columns; header has {header_width}",
                            mismatches,
                        )
                    mw_values = []
                    for location in kept:
                        factor = parse_capacity_factor(
                            row[columns[location.grid_cell]],
                            source=source,
                            hour=hour,
                            grid_cell=location.grid_cell,
                        )
                        mw_values.append(format_mw(factor * location.nameplate_mw))
                    writer.writerow([str(hour), *mw_values])
                    expected_hour += 1
                written = expected_hour - 1
                if written != hours_in_year:
                    raise DataError(f"{source} has {written} hour rows; expected {hours_in_year}", mismatches)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
        partial.replace(dest)
    return kept, mismatches


def output_path(ba: str, when: datetime | None = None) -> Path:
    stamp = (when or datetime.now()).strftime("%Y%m%d-%H%M")
    slug = ba.replace(" ", "_")
    return OUTPUT_DIR / f"{SCRIPT_NAME}_{slug}_{NAMEPLATE_YEAR}_{stamp}.csv"


def print_mismatches(mismatches: list[LocationMismatch]) -> None:
    for mismatch in mismatches:
        print(mismatch.message, file=sys.stderr)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ba",
        default=DEFAULT_BA,
        help=f"Balancing authority to include (default: {DEFAULT_BA})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    ba = args.ba.strip()
    if not ba:
        print("Balancing authority must not be empty", file=sys.stderr)
        return 1
    try:
        for path in (DEFAULT_EXTANT, DEFAULT_GRIDCELLS, DEFAULT_WINDCF):
            if not path.is_file():
                raise DataError(f"Input file not found: {path}")
        locations, mismatches = select_locations(DEFAULT_EXTANT, DEFAULT_GRIDCELLS, ba, NAMEPLATE_YEAR)
        print_mismatches(mismatches)
        dest = output_path(ba)
        kept, cf_mismatches = write_hourly_generation(DEFAULT_WINDCF, locations, dest)
        print_mismatches(cf_mismatches)
    except DataError as exc:
        print_mismatches(exc.mismatches)
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Wrote {dest} ({HOURS_IN_YEAR} hours, {len(kept)} locations)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
