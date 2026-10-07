"""Reshape the per-sheet IESO demand-forecast CSVs into one tidy long-format CSV.

The IESO "Demand Forecast Module Data" sheets all share the same layout:
a title row, a units row (the "Data" header), a row of calendar years, then
one row per data series (a series number in col B, a label in col C, and one
value per year from col E onward).

This script parses every '<stem>__<sheet>.csv' file in the input directory
(skipping the Menu) and emits a single tidy CSV with one row per
(sheet, scenario, series, year, value).

Usage:
    uv run python bin/tidy_demand_forecast.py <per_sheet_csv_dir> <output.csv>
"""

import csv
import re
import sys
from pathlib import Path


def to_float(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def is_year(v) -> bool:
    f = to_float(v)
    return f is not None and 2000 <= f <= 2100 and float(f).is_integer()


def detect_scenario(*texts: str) -> str:
    """Return a normalized scenario name found in any of the given strings."""
    blob = " ".join(t for t in texts if t).lower()
    if "high" in blob and "demand" in blob:
        return "High-Demand"
    if "low" in blob and "demand" in blob:
        return "Low-Demand"
    if "reference" in blob:
        return "Reference"
    return ""


def detect_breakdown(title: str) -> str:
    t = title.lower()
    if "by sector" in t:
        return "sector"
    if "by component" in t:
        return "component"
    if "growth margin component" in t:
        return "growth_margin_component"
    return "other"


def parse_sheet(rows: list[list[str]]):
    """Yield dict records for a single sheet's rows."""
    title = ""
    unit = ""
    year_cols: dict[int, int] = {}  # column index -> calendar year

    for row in rows:
        col_b = row[1] if len(row) > 1 else ""
        col_c = row[2] if len(row) > 2 else ""

        # Title row: "Figure N: ..." or "Table N: ..."
        if not title and isinstance(col_c, str) and re.match(r"^(Figure|Table)\s*\d", col_c.strip()):
            title = re.sub(r"\s+", " ", col_c.strip())
            continue

        # Units row: the "Data" header carries the unit string in col E.
        if isinstance(col_c, str) and col_c.strip() == "Data":
            unit_cell = row[4] if len(row) > 4 else ""
            if unit_cell:
                unit = str(unit_cell).strip()
            continue

        # Year row: detect the row whose col-E onward are calendar years.
        if not year_cols:
            candidate = {i: int(to_float(v)) for i, v in enumerate(row) if i >= 4 and is_year(v)}
            if candidate:
                year_cols = candidate
                continue

        # Data rows: a series number in col B, a non-empty label in col C.
        if year_cols and to_float(col_b) is not None and isinstance(col_c, str) and col_c.strip():
            series = re.sub(r"\s+", " ", col_c.strip())
            scenario = detect_scenario(series, title)
            breakdown = detect_breakdown(title)
            for col_idx, year in year_cols.items():
                value = to_float(row[col_idx]) if col_idx < len(row) else None
                if value is None:
                    continue
                yield {
                    "sheet_title": title,
                    "breakdown": breakdown,
                    "scenario": scenario,
                    "series": series,
                    "unit": unit,
                    "year": year,
                    "value": value,
                }


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    in_dir = Path(sys.argv[1])
    out_path = Path(sys.argv[2])

    sheet_files = sorted(p for p in in_dir.glob("*.csv") if "__Menu" not in p.name and p != out_path)
    if not sheet_files:
        print(f"No per-sheet CSVs found in {in_dir}")
        sys.exit(1)

    records = []
    for path in sheet_files:
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        sheet_records = list(parse_sheet(rows))
        records.extend(sheet_records)
        print(f"  {path.name}: {len(sheet_records)} tidy rows")

    fieldnames = ["sheet_title", "breakdown", "scenario", "series", "unit", "year", "value"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    print(f"Wrote {len(records)} rows -> {out_path}")


if __name__ == "__main__":
    main()
