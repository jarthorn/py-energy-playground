# Montreal EV charging data

Raw input files for Montreal public EV charging analysis. CSV files in this
folder are gitignored; obtain them locally as described below.

## Files

| File | Description |
| --- | --- |
| `chargeurs_statistiques_YYYY.csv` | Monthly station statistics (sessions, connection time, kWh, utilization) by calendar year |

## Data source

Use of public charging stations for electric cars (Ville de Montréal / Government and
Municipalities of Québec), via the [Open Government Portal](https://open.canada.ca/data/en/dataset/4b2f9b4c-abac-4c36-997a-85c22e22bf0b)
(CC BY 4.0 – Quebec).

Place downloaded CSV files directly in this folder. Related formats on the same
record include GeoJSON and shapefile station locations.

Source CSVs use French column titles. Translate them in place before running
aggregation scripts:

```bash
uv run python src/ev-charging-mtl/translate_chargeurs_headers.py \
  data/ev-charging-mtl/chargeurs_statistiques.csv
```
