# Wind generation dashboard plan

Handoff for a new session. Build a small local web page that charts the aggregated hourly wind file. Do not re-derive generation from the COPPER inputs.

## Tech choice

Streamlit plus Plotly is the right stack for this first view.

The page is one control and one time series: pick a balancing authority, see its 8,760 hourly megawatts, and zoom inside the year. Streamlit supplies the selector and the local page. Plotly supplies drag-zoom, scroll-zoom, and a range slider on the chart, so a custom time-range widget is unnecessary for v1. The series is about 8,760 points, which both libraries handle without extra infrastructure.

This stays in the repo’s Python toolchain (`uv`, Ruff). Add `streamlit` and `plotly` with uv. A dataframe library is unnecessary; read the CSV with the standard library and pass lists to `plotly.graph_objects`.

Revisit the stack only if the page later needs accounts, a public URL, or a layout Streamlit fights. Do not start with Dash or a separate frontend.

## What the chart is showing

The dashboard reads the aggregation script’s output, not the COPPER source files.

`src/gen-capacity-can/hourly_wind_generation.py` builds that file:

```bash
uv run python src/gen-capacity-can/hourly_wind_generation.py
```

For each onshore wind site (`location` ending in `.wind_ons`) with positive 2025 nameplate, hourly megawatts are nameplate times the capacity factor in `windcf.csv`. Sites in the same balancing authority are summed. Each sum is rounded to the nearest whole MW, with halves away from zero (0.5 becomes 1). The nameplate year is the `NAMEPLATE_YEAR` constant (`"2025"`). Solar rows and zero nameplate are excluded. A `wind_ons` grid cell missing from `gridcells.csv`, or a selected cell missing from `windcf.csv`, is reported on stderr and skipped.

`output/` is gitignored. The COPPER inputs under `data/gen-capacity-can/` are also not in git. See `data/gen-capacity-can/README.md` if those inputs are missing. Regenerate the CSV with the command above before opening the dashboard.

## Input the dashboard should load

Use the newest file matching:

```text
output/wind-capacity-on_by-ba_2025_YYYYMMDD-HHMM.csv
```

The timestamp sorts lexicographically, so the latest path is the latest run. Ignore other files in `output/`, including the earlier per-location file `wind-capacity-on_Ontario.a_2025_20261022-1523.csv` and the unrounded by-authority file `wind-capacity-on_by-ba_2025_20261022-1722.csv`.

Current file, from the run at 2026-10-22 17:28:

`output/wind-capacity-on_by-ba_2025_20261022-1728.csv`

### Shape

- CSV, UTF-8, no byte-order mark, comma-separated.
- Header row, then exactly 8,760 data rows. 8,760 is a non-leap year. There is no date column.
- First column is `h`, the hour of the year, integers `1` through `8760` in order, one row each.
- Every other column is a balancing-authority label copied from `gridcells.csv` column `ba`. Labels contain letters, spaces, and dots. They do not contain commas.
- A cell is that authority’s total onshore wind generation for that hour, in MW, as an integer. Zero is a real value.
- Column order is alphabetical by label.
- One row per hour. Wide format: authorities are columns, not a `ba` field on each row.

Authorities in the current file:

`Alberta.a`, `British Columbia.a`, `Manitoba.a`, `New Brunswick.a`, `Newfoundland and Labrador.a`, `Nova Scotia.a`, `Ontario.a`, `Ontario.b`, `Prince Edward Island.a`, `Quebec.a`, `Quebec.b`, `Saskatchewan.a`

`Newfoundland and Labrador.b` is a real authority in `gridcells.csv` and is absent here because it has no positive 2025 onshore nameplate. The dashboard should chart the columns that are present, not a hard-coded list of 13 authorities.

First hours of the current file:

```text
h,Alberta.a,British Columbia.a,Manitoba.a,New Brunswick.a,Newfoundland and Labrador.a,Nova Scotia.a,Ontario.a,Ontario.b,Prince Edward Island.a,Quebec.a,Quebec.b,Saskatchewan.a
1,1839,307,88,403,54,281,151,143,79,2599,435,21
2,2454,324,55,372,54,288,187,178,69,2508,365,17
```

Hour 1 for `Ontario.a` is 151 MW. That was 151.133308 before rounding.

### Checks

Fail visibly if the file is missing, `h` is missing, a data cell is not an integer, the hour index is not `1`…`8760` in order, or a row’s width does not match the header. An empty chart is the wrong outcome. Print the problem in the page.

## Page behavior

One Streamlit page, suggested path `src/gen-capacity-can/dashboard.py`.

Run it with uv, for example `uv run streamlit run src/gen-capacity-can/dashboard.py`.

- A select box lists the authority columns. Default the selection to `Ontario.a` when that column exists; otherwise the first column.
- One Plotly line chart of the selected authority. Y axis is MW. X axis is time within the year, so zooming lands on days and weeks rather than hour numbers.
- The CSV has no timestamps. For display only, map hour `h` to `2025-01-01 00:00` plus `h - 1` hours. 2025 is not a leap year, so hour 8760 is the last hour of 31 December. Say in the chart title or caption that this calendar is a display mapping of hour-of-year, and that the series is 2025 nameplate. Do not write dates back into the CSV.
- Zoom is the Plotly interaction: drag to zoom, double-click to reset, and a range slider under the chart. Add range buttons for 7 days, 30 days, and the full year. Those buttons are the “smaller timeframe” control. Do not build a second chart or a custom date parser for v1.
- Changing the authority replaces the series and resets to the full year.
- Cache the CSV read across selector changes. The file is a few hundred kilobytes.

Title the chart with the selected authority and the year, for example `Ontario.a onshore wind generation, 2025`.

## Out of scope for v1

- Comparing several authorities on one chart.
- Returning to per-location series. The per-location CSV was the wrong grain and should not be plotted.
- Editing `NAMEPLATE_YEAR` or re-running the aggregation from the page.
- Offshore wind, solar, or years other than 2025.
- Maps, capacity-factor charts, and download buttons.

## Project constraints

From `project-overview.md`: Python, Ruff (`uv run ruff check` and `uv run ruff format` on Python changes), uv for every Python command. Test logic that can silently mis-handle the file: hour index, integer parsing, and the hour-to-datetime mapping. A bad input should surface an error rather than a partial chart.

Read `src/gen-capacity-can/hourly_wind_generation.py` and `src/gen-capacity-can/README.md` before changing how the CSV is interpreted. The aggregation script is the source of the file format above.
