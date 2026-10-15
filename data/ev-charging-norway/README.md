# Norway EV charging data

Raw input files for the Oslo EV charging / temperature analysis scripts in
`src/ev-charging-norway/`. CSV files in this folder are gitignored; obtain them
locally as described below.

## Files

| File | Description | How to obtain |
| --- | --- | --- |
| `Dataset1_charging_reports.csv` | Residential EV charging sessions (plug-in/out times, energy charged, locations) | [Zenodo record 12730566](https://zenodo.org/records/12730566) |
| `Dataset4_hourly_predictions.csv` | Hourly predictions (energy charged, connected capacity per session) | Same Zenodo record |
| `SN18700_hourly_YYYY.csv` | Hourly air temperature at Oslo–Blindern (Frost station SN18700), one file per year | See below |
| `location-histogram.txt` | Rough notes on session counts by location code | Checked into git |

Other files from the Zenodo dataset (`Dataset2_user_predictions.csv`,
`Dataset3_session_predictions.csv`) may also be placed here if needed; they are
not required by the current scripts.

## EV charging datasets (Zenodo)

Download from:

https://zenodo.org/records/12730566

Dataset: *Electric vehicle charging dataset with 35,000 charging sessions from
12 residential locations in Norway* (Sørensen et al., CC BY 4.0). Place the CSV
files directly in this folder.

## Temperature data (MET Norway Frost)

Requires a Frost API client ID (`FROST_CLIENT_ID` in the environment or `.env`).
See https://frost.met.no/.

```bash
export FROST_CLIENT_ID=<your client id>
uv run python src/ev-charging-norway/download_frost_hourly_temperature.py
# optional: uv run python src/ev-charging-norway/download_frost_hourly_temperature.py --years 2018 2019 2020 2021
```

Writes `SN18700_hourly_YYYY.csv` into this folder (default years 2018–2021).
