# Ember electricity generation data

Raw monthly electricity generation JSON files used by the `emberstats` package.
JSON files in this folder are gitignored; generate them locally as described below.

## Files

| File | Description |
| --- | --- |
| `{iso3}-monthly-generation.json` | Ember API monthly generation response for one country (ISO 3166-1 alpha-3, lowercase), e.g. `can-monthly-generation.json` |

## How to generate

Requires an Ember API key (`EMBER_API_KEY` in the environment or `.env`).
See https://ember-energy.org/.

Fetch one country (default start date `2015-01`):

```bash
uv run python -m emberstats.load --country=CAN
uv run python -m emberstats.load --country=CAN --start_date=2020-01
```

Fetch all supported countries:

```bash
uv run python -m emberstats.load --country=ALL
```

Files are written under this directory by `emberstats/load.py`.
