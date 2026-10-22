# Overview

This folder contains scripts for analyzing the capacity of extant wind power generation in Canada.


# Source data
The data for this script comes from the COPPER data model. See [../data/wind-capacity-on/README.md](data readme) for details on loading data.

The following files are used:

1. gridcells.csv - Metadata about grid cells across Canada

grid_cell — integer ID
ba — balancing area (Ontario.b, etc.)
pr - province

2. extant_wind_solar.csv - Metadata about nameplate capacity at existing wind and solar installations

location — {grid_cell}.wind_ons (ignore .solar rows)
One period column (2025, 2030, …) — nameplate MW still in service that year for that location

3. windcf.csv - Matrix of capacity factors for each location and hour of the year

- Rows are hours of the year, from 1-8760.
- Columns are grid cell ids.
- Cell values are the capacity factor of wind power at that location, for that hour of the year.
- We will need to filter out locations that we are not interested in tracking. There are many more location ids in this file than in extant_wind_solar.csv because they represent potential future wind generation sites, as well as solar generation sites.

For a given hour of the year (h), the expected power output is NAMEPLATE_CAPACITY[location] x CF[h, location]
