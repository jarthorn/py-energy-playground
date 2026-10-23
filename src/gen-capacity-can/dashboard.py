"""Chart hourly wind, solar, demand, and net demand by balancing authority.

Reads the four by-authority CSVs in data/gen-capacity-can/. Does not recompute
them from the COPPER inputs. The charts share one time axis.

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
from plotly.subplots import make_subplots

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "data" / "gen-capacity-can"

NAMEPLATE_YEAR = "2025"
HOURS_IN_YEAR = 8760
DISPLAY_YEAR = int(NAMEPLATE_YEAR)
INTEGER_MW = re.compile(r"-?\d+")
DEFAULT_AUTHORITY = "Ontario.a"
# Fits the longest label ("Newfoundland and Labrador.b") without spanning the chart.
AUTHORITY_SELECT_WIDTH = 340


@dataclass(frozen=True)
class SeriesSpec:
    filename: str
    title: str
    pin_zero: bool


# Top to bottom: the original wind chart, then solar, demand, and net demand.
SERIES = (
    SeriesSpec("wind_gen_ba.csv", "Estimated onshore wind generation", True),
    SeriesSpec("solar_gen_ba.csv", "Estimated solar generation", True),
    SeriesSpec("demand_ba.csv", "Demand", True),
    SeriesSpec("net_demand_ba.csv", "Net demand", True),
)

RANGE_BUTTONS = (
    {"count": 7, "label": "7 days", "step": "day", "stepmode": "backward"},
    {"count": 30, "label": "30 days", "step": "day", "stepmode": "backward"},
    {"step": "all", "label": "Full year"},
)


class DataError(Exception):
    """An hourly CSV broke an assumption. The page shows this instead of a chart."""


@dataclass(frozen=True)
class HourlySeries:
    path: Path
    authorities: tuple[str, ...]
    hours: tuple[int, ...]
    series: dict[str, tuple[int, ...]]
    display_times: tuple[str, ...]


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


def load_hourly_csv(path: Path, *, hours_in_year: int = HOURS_IN_YEAR) -> HourlySeries:
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
    return HourlySeries(
        path=path,
        authorities=tuple(authorities),
        hours=tuple(hours),
        series=series,
        display_times=display_times,
    )


def require_same_hours(tables: Sequence[HourlySeries]) -> None:
    """The four charts share one x-axis, so the hour indexes have to be identical."""
    if not tables:
        raise DataError("No hourly files to chart")
    expected = tables[0].hours
    for table in tables[1:]:
        if table.hours != expected:
            raise DataError(f"{table.path.name} hours do not match {tables[0].path.name}")


def authorities_present(tables: Sequence[HourlySeries]) -> tuple[str, ...]:
    """Alphabetical union of authority columns. A later chart may lack a column."""
    names = {name for table in tables for name in table.authorities}
    if not names:
        raise DataError("No balancing authority columns to chart")
    return tuple(sorted(names))


def series_or_zeros(table: HourlySeries, authority: str) -> tuple[int, ...]:
    """Missing balancing authorities are regions with zero generation of that type."""
    found = table.series.get(authority)
    if found is not None:
        return found
    return tuple(0 for _ in table.hours)


def default_authority(authorities: Sequence[str]) -> str:
    if not authorities:
        raise DataError("No balancing authority columns to chart")
    if DEFAULT_AUTHORITY in authorities:
        return DEFAULT_AUTHORITY
    return authorities[0]


def build_figure(
    authority: str,
    display_times: Sequence[str],
    panels: Sequence[tuple[str, Sequence[int], bool]],
) -> go.Figure:
    """Four stacked lines sharing one x-axis.

    `panels` is `(title, megawatts, pin_y_at_zero)` from top to bottom.
    `uirevision` resets the shared zoom when the authority changes.
    The week, month, and year buttons and the range slider sit on that shared axis.
    """
    figure = make_subplots(
        rows=len(panels),
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        subplot_titles=tuple(f"{title}, {NAMEPLATE_YEAR}" for title, _, _ in panels),
    )
    x_values = list(display_times)
    for index, (title, megawatts, pin_zero) in enumerate(panels, start=1):
        figure.add_trace(
            go.Scatter(
                x=x_values,
                y=list(megawatts),
                mode="lines",
                line={"width": 1},
                name=title,
                hovertemplate="%{x|%Y-%m-%d %H:%M}<br>%{y} MW<extra></extra>",
            ),
            row=index,
            col=1,
        )
        yaxis: dict[str, str] = {"title": "MW"}
        if pin_zero:
            yaxis["rangemode"] = "tozero"
        figure.update_yaxes(**yaxis, row=index, col=1)

    figure.update_xaxes(type="date")
    # The bottom axis owns the shared range. Paper coordinates keep the buttons
    # at the top of the stack, where they apply to every chart.
    figure.update_xaxes(
        rangeslider={"visible": True},
        rangeselector={
            "buttons": list(RANGE_BUTTONS),
            "x": 0,
            "xanchor": "left",
            "y": 1.02,
            "yanchor": "bottom",
        },
        row=len(panels),
        col=1,
    )
    figure.update_layout(
        height=260 * len(panels) + 120,
        uirevision=authority,
        showlegend=False,
        margin={"l": 64, "r": 24, "t": 72, "b": 24},
    )
    return figure


def panels_for(authority: str, tables: Sequence[HourlySeries]) -> tuple[tuple[str, tuple[int, ...], bool], ...]:
    if len(tables) != len(SERIES):
        raise DataError(f"Expected {len(SERIES)} hourly files, got {len(tables)}")
    return tuple(
        (spec.title, series_or_zeros(table, authority), spec.pin_zero)
        for spec, table in zip(SERIES, tables, strict=True)
    )


@st.cache_data(show_spinner="Reading hourly files")
def cached_hourly_csv(path_str: str) -> HourlySeries:
    return load_hourly_csv(Path(path_str))


def load_dashboard_tables() -> tuple[HourlySeries, ...]:
    tables = tuple(cached_hourly_csv(str(DATA_DIR / spec.filename)) for spec in SERIES)
    require_same_hours(tables)
    return tables


def main() -> None:
    st.set_page_config(page_title=f"Generation and demand, {NAMEPLATE_YEAR}", layout="wide")
    try:
        tables = load_dashboard_tables()
    except DataError as exc:
        st.error(str(exc))
        st.stop()

    authorities = list(authorities_present(tables))
    authority = st.selectbox(
        "Balancing authority",
        authorities,
        index=authorities.index(default_authority(authorities)),
        width=AUTHORITY_SELECT_WIDTH,
    )
    st.plotly_chart(
        build_figure(authority, tables[0].display_times, panels_for(authority, tables)),
        width="stretch",
        config={"scrollZoom": True, "displaylogo": False},
    )
    st.caption(
        f"Estimated hourly wind generation for {authority} in {NAMEPLATE_YEAR}. "
        "Uses localized capacity factors for each wind generator location sourced from MERRA, "
        "multiplied by nameplate capacity of each plant."
    )
    st.caption(
        f"Estimated hourly solar generation for {authority} in {NAMEPLATE_YEAR}. "
        "Uses localized capacity factors for each solar generator location, "
        "multiplied by nameplate capacity of each plant."
    )
    st.caption(
        f"Estimated hourly demand for {authority} in {NAMEPLATE_YEAR}. "
        "Provincial demand is shared across balancing authorities by population."
    )
    st.caption(
        f"Estimated hourly net demand for {authority} in {NAMEPLATE_YEAR}. Demand minus wind and solar generation."
    )


if __name__ == "__main__":
    main()
