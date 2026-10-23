"""Hourly wind and solar generation summed by balancing authority.

Joins extant nameplate capacity with grid-cell balancing authorities, multiplies
each site's nameplate by its hourly capacity factor, and sums those MW values
within each balancing authority. One run writes two CSVs. In each file, rows
are hours 1–8760 and columns are balancing authority labels.

Usage:
    uv run python src/gen-capacity-can/hourly_variable_generation.py

Writes:
    output/wind-capacity-on_by-ba_<year>_YYYYMMDD-HHMM.csv
    output/solar-capacity_by-ba_<year>_YYYYMMDD-HHMM.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = REPO_ROOT / "output"
DATA_DIR = REPO_ROOT / "data" / "gen-capacity-can"
DEFAULT_EXTANT = DATA_DIR / "extant_wind_solar.csv"
DEFAULT_GRIDCELLS = DATA_DIR / "gridcells.csv"
DEFAULT_WINDCF = DATA_DIR / "windcf.csv"
DEFAULT_SOLARCF = DATA_DIR / "solarcf.csv"

# Period column in extant_wind_solar.csv. Hard-coded to the 2025 fleet;
# set this to a later column (2030, 2035, 2040, 2045, 2050) to revisit
# nameplate still in service in that year.
NAMEPLATE_YEAR = "2025"

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
class Technology:
    """One fleet: the extant location suffix, output name, and capacity-factor ceiling.

    `max_capacity_factor` is None when factors above 1 are real data and should be used.
    """

    name: str
    suffix: str
    output_prefix: str
    max_capacity_factor: float | None


WIND = Technology("onshore wind", WIND_ONS_SUFFIX, "wind-capacity-on", 1)
SOLAR = Technology("solar", SOLAR_SUFFIX, "solar-capacity", None)
TECHNOLOGIES = (
    (WIND, DEFAULT_WINDCF),
    (SOLAR, DEFAULT_SOLARCF),
)
KNOWN_SUFFIXES = (WIND_ONS_SUFFIX, SOLAR_SUFFIX)


@dataclass(frozen=True)
class Site:
    grid_cell: int
    ba: str
    nameplate_mw: float


@dataclass(frozen=True)
class LocationMismatch:
    grid_cell: int
    message: str


def format_mw(value: float) -> str:
    """Nearest whole MW. Halves round away from zero, so 0.5 becomes 1."""
    rounded = Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return format(rounded, "f")


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


def location_suffix(location: str) -> str | None:
    for suffix in KNOWN_SUFFIXES:
        if location.endswith(suffix):
            return suffix
    return None


def select_locations(
    extant_path: Path,
    gridcells_path: Path,
    year: str = NAMEPLATE_YEAR,
    *,
    technology: Technology = WIND,
) -> tuple[list[Site], list[LocationMismatch]]:
    """Sites of `technology` with positive nameplate in `year`, tagged with their balancing authority.

    A selected grid cell missing from gridcells.csv is reported and skipped.
    Rows for the other technology are validated and then omitted. Zero nameplate is omitted.
    """
    cells = load_grid_cells(gridcells_path)
    mismatches: list[LocationMismatch] = []
    seen: dict[tuple[str, int], str] = {}
    chosen: list[Site] = []

    with extant_path.open(newline="", encoding=INPUT_ENCODING) as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        if "location" not in fieldnames:
            raise DataError(f"{extant_path.name} must have a location column")
        if year not in fieldnames:
            raise DataError(f"{extant_path.name} has no {year} nameplate column")
        for row_num, row in enumerate(reader, start=2):
            location = (row.get("location") or "").strip()
            suffix = location_suffix(location)
            if suffix is None:
                raise DataError(
                    f"{extant_path.name} row {row_num} location {location!r} "
                    f"is neither {WIND_ONS_SUFFIX} nor {SOLAR_SUFFIX}"
                )
            raw_id = location[: -len(suffix)]
            if not raw_id.isdigit():
                raise DataError(f"{extant_path.name} row {row_num} location {location!r} has no integer grid cell id")
            grid_cell = int(raw_id)
            key = (suffix, grid_cell)
            if key in seen:
                raise DataError(
                    f"{extant_path.name} lists grid cell {grid_cell} more than once ({seen[key]} and {location})"
                )
            seen[key] = location
            nameplate = parse_nameplate(row.get(year) or "", location, year)
            if suffix != technology.suffix:
                continue
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
            if nameplate == 0:
                continue
            chosen.append(Site(grid_cell, cells[grid_cell], nameplate))

    mismatches.sort(key=lambda item: item.grid_cell)
    chosen.sort(key=lambda item: item.grid_cell)

    if not chosen:
        raise DataError(
            f"No extant {technology.name} with positive {year} nameplate capacity.",
            mismatches,
        )
    return chosen, mismatches


def capacity_factor_column_index(header: list[str], source: str) -> dict[int, int]:
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


def parse_capacity_factor(
    value: str,
    *,
    source: str,
    hour: int,
    grid_cell: int,
    max_factor: float | None,
) -> float:
    try:
        factor = float(value.strip())
    except ValueError:
        raise DataError(
            f"{source} hour {hour} grid cell {grid_cell} has capacity factor {value!r}, which is not a number"
        ) from None
    if not math.isfinite(factor) or factor < 0 or (max_factor is not None and factor > max_factor):
        if max_factor is None:
            expected = "a non-negative number"
        else:
            expected = f"a number in [0, {format(max_factor, 'g')}]"
        raise DataError(
            f"{source} hour {hour} grid cell {grid_cell} has capacity factor {value!r}; expected {expected}"
        )
    return factor


def write_hourly_generation(
    cf_path: Path,
    locations: list[Site],
    dest: Path,
    *,
    hours_in_year: int = HOURS_IN_YEAR,
    max_capacity_factor: float | None = 1,
) -> tuple[list[str], list[LocationMismatch]]:
    """Stream a capacity-factor CSV and write each hour's MW total for each balancing authority.

    Locations with no capacity-factor column are reported and omitted. A balancing
    authority is included only when at least one of its locations remains. A structural
    problem in the capacity-factor file aborts with no output file. Factors above 1 are
    used when `max_capacity_factor` is None.
    """
    if not locations:
        raise DataError("No locations to write")

    source = cf_path.name
    with cf_path.open(newline="", encoding=INPUT_ENCODING) as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise DataError(f"{source} is empty") from exc
        columns = capacity_factor_column_index(header, source)
        header_width = len(header)

        mismatches: list[LocationMismatch] = []
        kept: list[Site] = []
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
            raise DataError(f"No selected locations are present in {source}.", mismatches)
        authorities = sorted({location.ba for location in kept})

        partial = dest.with_name(dest.name + ".partial")
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            with partial.open("w", newline="", encoding="utf-8") as out_handle:
                writer = csv.writer(out_handle)
                writer.writerow(["h", *authorities])
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
                    totals = dict.fromkeys(authorities, 0.0)
                    for location in kept:
                        factor = parse_capacity_factor(
                            row[columns[location.grid_cell]],
                            source=source,
                            hour=hour,
                            grid_cell=location.grid_cell,
                            max_factor=max_capacity_factor,
                        )
                        totals[location.ba] += factor * location.nameplate_mw
                    writer.writerow([str(hour), *(format_mw(totals[ba]) for ba in authorities)])
                    expected_hour += 1
                written = expected_hour - 1
                if written != hours_in_year:
                    raise DataError(f"{source} has {written} hour rows; expected {hours_in_year}", mismatches)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
        partial.replace(dest)
    return authorities, mismatches


def output_filename(technology: Technology, when: datetime, year: str = NAMEPLATE_YEAR) -> str:
    stamp = when.strftime("%Y%m%d-%H%M")
    return f"{technology.output_prefix}_by-ba_{year}_{stamp}.csv"


def output_path(when: datetime | None = None, technology: Technology = WIND) -> Path:
    return OUTPUT_DIR / output_filename(technology, when or datetime.now())


def generate_hourly_files(
    extant_path: Path,
    gridcells_path: Path,
    capacity_factors: list[tuple[Technology, Path]],
    output_dir: Path,
    *,
    year: str = NAMEPLATE_YEAR,
    when: datetime | None = None,
    hours_in_year: int = HOURS_IN_YEAR,
) -> list[tuple[Path, list[str]]]:
    """Write one by-authority CSV per technology, sharing `when` as the filename timestamp.

    A failure deletes files this call already wrote, so a run does not leave wind without solar.
    """
    stamp = when or datetime.now()
    written: list[Path] = []
    results: list[tuple[Path, list[str]]] = []
    try:
        for technology, cf_path in capacity_factors:
            if not cf_path.is_file():
                raise DataError(f"Input file not found: {cf_path}")
            locations, mismatches = select_locations(extant_path, gridcells_path, year, technology=technology)
            print_mismatches(mismatches)
            dest = output_dir / output_filename(technology, stamp, year)
            authorities, cf_mismatches = write_hourly_generation(
                cf_path,
                locations,
                dest,
                hours_in_year=hours_in_year,
                max_capacity_factor=technology.max_capacity_factor,
            )
            print_mismatches(cf_mismatches)
            written.append(dest)
            results.append((dest, authorities))
    except BaseException:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    return results


def print_mismatches(mismatches: list[LocationMismatch]) -> None:
    for mismatch in mismatches:
        print(mismatch.message, file=sys.stderr)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    parse_args(argv)
    try:
        for path in (DEFAULT_EXTANT, DEFAULT_GRIDCELLS, DEFAULT_WINDCF, DEFAULT_SOLARCF):
            if not path.is_file():
                raise DataError(f"Input file not found: {path}")
        results = generate_hourly_files(
            DEFAULT_EXTANT,
            DEFAULT_GRIDCELLS,
            list(TECHNOLOGIES),
            OUTPUT_DIR,
        )
    except DataError as exc:
        print_mismatches(exc.mismatches)
        print(str(exc), file=sys.stderr)
        return 1
    for dest, authorities in results:
        print(
            f"Wrote {dest} ({HOURS_IN_YEAR} hours, {len(authorities)} balancing authorities)",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
