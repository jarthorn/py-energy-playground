# Overview

This folder contains scripts for analyzing extant wind and solar generation capacity in Canada.


# Source data
The data for this script comes from the COPPER data model. See [../../data/gen-capacity-can/README.md](data readme) for details on loading data.

The following files are used:

1. gridcells.csv - Metadata about grid cells across Canada

grid_cell — integer ID
ba — balancing area (Ontario.b, etc.)
pr - province

2. extant_wind_solar.csv - Metadata about nameplate capacity at existing wind and solar installations

location — `{grid_cell}.wind_ons` or `{grid_cell}.solar`
One period column (2025, 2030, …) — nameplate MW still in service that year for that location

3. windcf.csv — hourly wind capacity factors
4. solarcf.csv — hourly solar capacity factors

Both capacity-factor files have the same shape:

- Rows are hours of the year, from 1-8760.
- Columns are grid cell ids.
- Cell values are the capacity factor at that location for that hour of the year.
- Many columns are potential future sites. A column is used only when extant_wind_solar.csv has positive 2025 nameplate for that technology at that grid cell.

For a given hour of the year (h), the expected power output is NAMEPLATE_CAPACITY[location] × CF[h, location]. Wind uses windcf.csv. Solar uses solarcf.csv. A wind capacity factor outside 0–1 aborts the run. Solar factors above 1 are used as given.

Each run writes two files that share a timestamp:

- `output/wind-capacity-on_by-ba_2025_YYYYMMDD-HHMM.csv`
- `output/solar-capacity_by-ba_2025_YYYYMMDD-HHMM.csv`

Rows are hours 1–8760. Columns are balancing authorities. Each cell is that technology's generation in the authority, rounded to the nearest whole MW.

# Balancing-authority demand

`demand_by_ba.py` splits provincial hourly demand onto balancing authorities, then subtracts wind and solar.

```bash
uv run python src/gen-capacity-can/demand_by_ba.py
```

Population weights are `PROVINCE_BA_POPULATION` at the top of that script. Each province's demand in an hour is shared across the authorities listed for that province in proportion to those headcounts. `Ontario.a` also receives the Quebec population assigned to that authority (grid cell 2068).

Inputs, under `data/gen-capacity-can/`:

- `demand.csv` — hours 0–8759, blank hour-column header, provinces as columns, MW
- `solar_gen_ba.csv` and `wind_gen_ba.csv` — hours 1–8760, column `h`, balancing authorities as columns, MW

Demand hour 0 is generation hour 1. The outputs use that generation index, hours 1–8760 under column `h`. An authority with no column in a generation file contributes 0 MW. A structural problem (hour index, row width, unknown column, non-numeric cell) aborts with no output from that run.

One run writes two files that share a timestamp:

- `output/demand_ba_YYYYMMDD-HHMM.csv`
- `output/net_demand_ba_YYYYMMDD-HHMM.csv`

Both use column `h` and hours 1–8760. Columns are balancing authorities. Each cell is rounded to the nearest whole MW, with halves away from zero. A positive value below 1 MW is written as 1. Net demand is the disaggregated demand minus solar minus wind, and it may be negative.

# Dashboard

From the repository root, build the hourly files, then open the page. The page reads the newest `output/wind-capacity-on_by-ba_2025_YYYYMMDD-HHMM.csv`. It does not recompute generation from the COPPER inputs, and it does not chart the solar file.

```bash
uv run python src/gen-capacity-can/hourly_variable_generation.py
uv run streamlit run src/gen-capacity-can/dashboard.py
```

Choose a balancing authority. The chart is estimated hourly onshore wind megawatts for 2025 nameplate: each site's capacity factor times its nameplate, summed within the authority.
