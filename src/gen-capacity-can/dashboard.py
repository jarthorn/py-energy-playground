"""Chart hourly onshore wind generation by balancing authority.

Reads the newest by-authority CSV written by hourly_wind_generation.py.
Does not recompute generation from the COPPER inputs.

Usage:
    uv run streamlit run src/gen-capacity-can/dashboard.py
"""

from __future__ import annotations

import csv
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = REPO_ROOT / "output"

# These match hourly_wind_generation.py. The dashboard only reads that script's CSV.
SCRIPT_NAME = "wind-capacity-on"
NAMEPLATE_YEAR = "2025"
HOURS_IN_YEAR = 8760
DISPLAY_YEAR = int(NAMEPLATE_YEAR)
BY_BA_NAME = re.compile(rf"^{re.escape(SCRIPT_NAME)}_by-ba_{NAMEPLATE_YEAR}_\d{{8}}-\d{{4}}\.csv$")
INTEGER_MW = re.compile(r"-?\d+")
DEFAULT_AUTHORITY = "Ontario.a"
# Fits the longest label ("Newfoundland and Labrador.a") without spanning the chart.
AUTHORITY_SELECT_WIDTH = 320
REGENERATE = "uv run python src/gen-capacity-can/hourly_wind_generation.py"


class DataError(Exception):
    """The hourly CSV broke an assumption. The page shows this instead of a chart."""


@dataclass(frozen=True)
class HourlyWind:
    path: Path
    authorities: tuple[str, ...]
    hours: tuple[int, ...]
    series: dict[str, tuple[int, ...]]
    display_times: tuple[str, ...]


def latest_by_ba_csv(output_dir: Path) -> Path:
    """Newest `wind-capacity-on_by-ba_<year>_YYYYMMDD-HHMM.csv` in `output_dir`.

    The timestamp sorts lexicographically, so the greatest filename is the latest run.
    """
    expected = f"output/{SCRIPT_NAME}_by-ba_{NAMEPLATE_YEAR}_YYYYMMDD-HHMM.csv"
    if not output_dir.is_dir():
        raise DataError(f"No output directory at {output_dir}. Regenerate the hourly file with: {REGENERATE}")
    matches = [path for path in output_dir.iterdir() if path.is_file() and BY_BA_NAME.fullmatch(path.name)]
    if not matches:
        raise DataError(f"No file matching {expected} in {output_dir}. Regenerate it with: {REGENERATE}")
    matches.sort(key=lambda path: path.name)
    return matches[-1]


def parse_mw_cell(value: str) -> int:
    """Whole megawatts. Rejects decimals, blanks, and surrounding space."""
    if INTEGER_MW.fullmatch(value) is None:
        raise ValueError(value)
    return int(value)


def hour_to_display_time(hour: int, *, year: int = DISPLAY_YEAR) -> datetime:
    """Map hour-of-year `hour` to `year-01-01 00:00` plus `hour - 1` hours.

    This is a display calendar only. 2025 is not a leap year, so hour 8760 is
    2025-12-31 23:00. The result is naive: no timezone and no daylight-saving shift.
    """
    if type(hour) is not int or hour < 1:
        raise DataError(f"Hour {hour!r} is not an hour of the year")
    return datetime(year, 1, 1) + timedelta(hours=hour - 1)


def format_display_time(moment: datetime) -> str:
    """Clock time with no timezone suffix, so a Plotly date axis shows these digits."""
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def load_hourly_wind(path: Path, *, hours_in_year: int = HOURS_IN_YEAR) -> HourlyWind:
    """Read one by-authority CSV. Raises DataError rather than returning a partial table."""
    if not path.is_file():
        raise DataError(f"Input file not found: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise DataError(f"{path.name} is empty") from exc
        if not header or header[0] != "h":
            raise DataError(f"{path.name} header must start with column 'h'")
        authorities = header[1:]
        if not authorities:
            raise DataError(f"{path.name} has no balancing authority columns")
        if any(name == "" for name in authorities):
            raise DataError(f"{path.name} has an empty column name")
        seen: set[str] = set()
        for name in authorities:
            if name in seen:
                raise DataError(f"{path.name} repeats balancing authority column {name!r}")
            seen.add(name)

        width = len(header)
        columns: list[list[int]] = [[] for _ in authorities]
        hours: list[int] = []
        expected = 1
        for row in reader:
            if len(row) != width:
                label = row[0] if row else str(expected)
                raise DataError(f"{path.name} hour {label} has {len(row)} columns; header has {width}")
            raw_hour = row[0]
            if not raw_hour.isdigit() or int(raw_hour) != expected:
                raise DataError(f"{path.name} hour column has {raw_hour!r} where {expected} was expected")
            for index, authority in enumerate(authorities):
                cell = row[index + 1]
                try:
                    megawatts = parse_mw_cell(cell)
                except ValueError:
                    raise DataError(
                        f"{path.name} hour {expected} column {authority!r} has {cell!r}, "
                        "which is not an integer MW value"
                    ) from None
                columns[index].append(megawatts)
            hours.append(expected)
            expected += 1
        written = expected - 1
        if written != hours_in_year:
            raise DataError(f"{path.name} has {written} hour rows; expected {hours_in_year}")

    display_times = tuple(format_display_time(hour_to_display_time(hour)) for hour in hours)
    series = {authority: tuple(values) for authority, values in zip(authorities, columns, strict=True)}
    return HourlyWind(
        path=path,
        authorities=tuple(authorities),
        hours=tuple(hours),
        series=series,
        display_times=display_times,
    )


def default_authority(authorities: Sequence[str]) -> str:
    if not authorities:
        raise DataError("No balancing authority columns to chart")
    if DEFAULT_AUTHORITY in authorities:
        return DEFAULT_AUTHORITY
    return authorities[0]


def build_figure(authority: str, display_times: Sequence[str], megawatts: Sequence[int]) -> go.Figure:
    """One line for `authority`. `uirevision` resets zoom when the authority changes."""
    figure = go.Figure(
        data=[
            go.Scatter(
                x=list(display_times),
                y=list(megawatts),
                mode="lines",
                line={"width": 1},
                name=authority,
                hovertemplate="%{x|%Y-%m-%d %H:%M}<br>%{y} MW<extra></extra>",
            )
        ]
    )
    figure.update_layout(
        title=f"{authority} onshore wind generation, {NAMEPLATE_YEAR}",
        uirevision=authority,
        height=640,
        margin={"l": 64, "r": 24, "t": 88, "b": 32},
        showlegend=False,
        yaxis={"title": "MW", "rangemode": "tozero"},
        xaxis={
            "type": "date",
            "rangeslider": {"visible": True},
            "rangeselector": {
                "buttons": [
                    {"count": 7, "label": "7 days", "step": "day", "stepmode": "backward"},
                    {"count": 30, "label": "30 days", "step": "day", "stepmode": "backward"},
                    {"step": "all", "label": "Full year"},
                ]
            },
        },
    )
    return figure


@st.cache_data(show_spinner="Reading hourly wind file")
def cached_hourly_wind(path_str: str) -> HourlyWind:
    return load_hourly_wind(Path(path_str))


def main() -> None:
    st.set_page_config(page_title=f"Onshore wind generation, {NAMEPLATE_YEAR}", layout="wide")
    try:
        table = cached_hourly_wind(str(latest_by_ba_csv(OUTPUT_DIR)))
    except DataError as exc:
        st.error(str(exc))
        st.stop()

    authorities = list(table.authorities)
    authority = st.selectbox(
        "Balancing authority",
        authorities,
        index=authorities.index(default_authority(authorities)),
        width=AUTHORITY_SELECT_WIDTH,
    )
    st.plotly_chart(
        build_figure(authority, table.display_times, table.series[authority]),
        width="stretch",
        config={"scrollZoom": True, "displaylogo": False},
    )
    st.caption(
        f"Estimated hourly wind generation for {authority} in {NAMEPLATE_YEAR}. "
        "Uses localized capacity factors for each wind generator location sourced from MERRA, "
        "multiplied by nameplate capacity of each plant."
    )


if __name__ == "__main__":
    main()
