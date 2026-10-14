# Oslo EV charging vs temperature — analysis plan

## Thesis

Temperature has a measurable impact on **grid demand from EV charging**. Grid planners should account for it when projecting demand and matching it with renewable supply. Extremely cold periods are expected to show an outsize effect (battery inefficiency, cabin heating, preconditioning), so a linear temperature slope is too blunt. While the intended research direction is to build a model that explicitly calculates EV charging behaviour using a physics model, the immediate exercise is to do some basic data collation and aggregation to get directional confirmation of the research direction.

## Goal of this analysis

Estimate how Oslo EV charging **load** varies with ambient temperature at **hourly resolution**, after controlling for calendar/time-of-day structure. Produce an intermediate table in CSV format with the following columns:

- Temperature bin (5-degree range)
- Number of sessions in this temperature range. Use the average temperature during that charging session, ignoring hours at end of session that are less than 30 minutes. (A)
- Number of calendar days with the low in this temperature range (B). Include all days from the start of the first session to the end of the last session.
- Total number of KWh from charging sessions that fall into this bin (C)
- KWh/day (C/B)
- KWh/session (C/A)
- sessions per user (A / total number of unique users in the filtered dataset)

The script should be saved in src/ev-charging-norway/ folder. Report on stderr if temperature data is missing for a given session. 

Produce three separate output files with the following calendar filters:

- All sessions
- Weekday sessions
- Weekend sessions

On stdout, include the following summary data
- Total number of sessions (after location filter)
- Total number of unique users (after location filter)

## Data sources

| Source | Path | Role |
|---|---|---|
| Session reports | `data/ev-charging-norway/Dataset1_charging_reports.csv` | Charging session data (kWh/session, sessions/day vs cold) in local time (CET or CEST) |
| Hourly temperature | `data/ev-charging-norway/SN18700_hourly_YYYY.csv` (2018–2021) | Oslo ambient temperature (station SN18700) in UTC timezone |

This is a sample of Oslo charging users, not the full city fleet. Results are about **relative temperature response** and shapes, not absolute Oslo system MW unless later scaled.

**Geography filter:** Oslo only — charging rows where location / `user_id` prefix is `OSL` (e.g. `OSL_S`, `OSL_T`, `OSL_1`, `OSL_2`). We may expand to other locations in future, but we only have temperature data for Oslo for now.

**Temperature bins:** 5°C increments, half-open intervals, e.g.

`[<−15), [−15,−10), [−10,−5), [−5,0), [0,5), [5,10), [10,15), [15,20), [≥20)`

- In the code, we will make the bin size a clearly defined variable so we can adjust bin sizes later if needed for either finer resolution or statistical significance

## Overview of approach

- Filter out non-Oslo locations
- Augment session data with mean temperature for that session, and weekday/weekend flag using session start time as discriminator
- Produce and output "all sessions" aggregate
- Produce and output "weekday" and "weekend" aggregates

## Out of scope (for now)

- Scaling sample demand to full Oslo / Norway fleet MW
- More advanced statistical analysis
- Full forecasting pipeline or renewable adequacy simulation
- Non-Oslo locations
- Causal identification beyond observational regression with calendar controls
