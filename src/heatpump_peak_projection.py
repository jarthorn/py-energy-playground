"""Winter PEAK (capacity) impact of converting all Ontario residential gas
space + water heating to cold-climate heat pumps by 2050.

Companion to bin/heatpump_projection.py (which estimates annual ENERGY). This
script estimates the incremental WINTER PEAK electricity demand (GW).

Per the request, this analysis fixes two parameters:
  * 2050 household scaling = 1.26x (population growth to ~2050)
  * heat-pump seasonal COP  = 3.5
and instead spreads the result over a TEMPERATURE / weather basis, using the
10-year average, minimum, and maximum of Ontario residential gas consumption.

Peak method (degree-day / design-temperature, space heating only is weather-driven):

    Annual space-heat energy  E_space = U_agg * HDD18 * 24      (U_agg = GW/degC)
    => U_agg = E_space / (HDD18 * 24)
    Peak space-heat power      P_space = U_agg * (T_indoor - T_design)
    => P_space = E_space[GWh] * (T_indoor - T_design) / (HDD18 * 24)

Water heating is treated as (roughly) weather-independent, contributing close to
its average power at the system peak (water_peak_factor).

Electricity peak = thermal peak / COP. (See the big caveat in the companion .txt:
using the SEASONAL COP of 3.5 at the coldest hour UNDERSTATES the true peak,
because real heat-pump COP at the design temperature is far lower and resistance
backup often engages. This is retained only because the request fixed COP = 3.5.)

Usage:
    uv run python bin/heatpump_peak_projection.py
"""

import csv
import statistics
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "ieso" / "heatpump-forecast"
GAS_CSV = DATA_DIR / "ontario-residential-natgas-by-year.csv"

# --- Fixed assumptions (per request) --------------------------------------------
HOUSEHOLD_GROWTH_2050 = 1.26     # scale today's load to projected 2050 households

# Heat-pump COP variants used for the peak.
#   3.5 = seasonal average COP (optimistic for the coldest hour).
#   2.0 = assumed 2050 COLD-DAY COP at the winter design temperature. This
#         reflects efficiency progress over current-generation cold-climate units
#         (which are nearer ~1.5 on the coldest days).
COP_VARIANTS = {
    "seasonal_cop_3.5": 3.5,
    "cold_day_cop_2.0": 2.0,
}

# --- Shared heating assumptions (same as the energy model) ----------------------
SHARE_SPACE = 0.70
SHARE_WATER = 0.30
AFUE_SPACE = 0.85
EF_WATER = 0.63
BASELINE_HP_SHARE = 0.063        # IESO 2050 baseline heat-pump household share

# --- Climate / peak assumptions (Ontario, population-weighted) ------------------
# Heating degree-days, base 18 degC (Env. Canada climate normals: Toronto 3434,
# Ottawa 4477) -> population-weighted ~3700.
HDD18 = 3700.0
T_INDOOR = 18.0                  # consistent with the HDD base temperature
# Winter design temperature (Ontario Building Code SB-1, January 2.5%):
# Toronto -18, Ottawa -24 -> population-weighted ~ -19 degC.
T_DESIGN = -19.0
WATER_PEAK_FACTOR = 1.0          # water heating contribution at system peak (~average)

# --- Context ---------------------------------------------------------------------
IESO_REF_WINTER_PEAK_2050_GW = 35.1   # IESO reference-scenario 2050 winter peak

HOURS_PER_YEAR = 8760.0


def load_gas_basis() -> dict[str, float]:
    with open(GAS_CSV, newline="", encoding="utf-8") as f:
        vals = [float(r["energy_twh_thermal"]) for r in csv.DictReader(f)]
    return {
        "10yr_average": statistics.mean(vals),
        "10yr_minimum": min(vals),
        "10yr_maximum": max(vals),
    }


def peak_for_basis(gas_basis_twh: float, cop: float) -> dict:
    gas_2050 = gas_basis_twh * HOUSEHOLD_GROWTH_2050

    useful_space_twh = gas_2050 * SHARE_SPACE * AFUE_SPACE
    useful_water_twh = gas_2050 * SHARE_WATER * EF_WATER

    # Space heating peak (weather-driven).
    delta_t = T_INDOOR - T_DESIGN
    space_peak_thermal_gw = (useful_space_twh * 1000.0) * delta_t / (HDD18 * 24.0)
    space_peak_elec_gw = space_peak_thermal_gw / cop

    # Water heating peak (~constant; based on average electric power).
    water_elec_annual_gwh = (useful_water_twh * 1000.0) / cop
    water_peak_elec_gw = (water_elec_annual_gwh / HOURS_PER_YEAR) * WATER_PEAK_FACTOR

    total_full = space_peak_elec_gw + water_peak_elec_gw
    total_incremental = total_full * (1 - BASELINE_HP_SHARE)

    return {
        "gas_basis_twh": round(gas_basis_twh, 2),
        "gas_2050_twh": round(gas_2050, 2),
        "peak_cop": cop,
        "space_peak_thermal_gw": round(space_peak_thermal_gw, 2),
        "space_peak_elec_gw": round(space_peak_elec_gw, 2),
        "water_peak_elec_gw": round(water_peak_elec_gw, 2),
        "total_peak_elec_full_gw": round(total_full, 2),
        "total_peak_elec_incremental_gw": round(total_incremental, 2),
        "pct_of_ieso_ref_winter_peak": round(100 * total_incremental / IESO_REF_WINTER_PEAK_2050_GW, 1),
    }


def main() -> None:
    bases = load_gas_basis()

    rows = []
    for cop_label, cop in COP_VARIANTS.items():
        for name, gas in bases.items():
            r = peak_for_basis(gas, cop)
            rows.append({"cop_variant": cop_label, "basis": name, **r})

    out_csv = DATA_DIR / "heatpump-2050-winter-peak.csv"
    fields = list(rows[0].keys())
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"Winter peak impact (2050 households x{HOUSEHOLD_GROWTH_2050}, "
          f"HDD18 {HDD18:.0f}, T_design {T_DESIGN} degC):\n")
    print(f"{'cop_variant':<18}{'basis':<14}{'gas2050':>9}{'space th':>10}{'space el':>10}"
          f"{'water el':>10}{'TOTAL el':>10}{'incr el':>9}{'% IESO wpk':>11}")
    for r in rows:
        print(f"{r['cop_variant']:<18}{r['basis']:<14}{r['gas_2050_twh']:>9}"
              f"{r['space_peak_thermal_gw']:>10}{r['space_peak_elec_gw']:>10}"
              f"{r['water_peak_elec_gw']:>10}{r['total_peak_elec_full_gw']:>10}"
              f"{r['total_peak_elec_incremental_gw']:>9}{r['pct_of_ieso_ref_winter_peak']:>10}%")
    print(f"\nContext: IESO 2050 reference winter peak = {IESO_REF_WINTER_PEAK_2050_GW} GW.")
    print(f"Wrote -> {out_csv}")


if __name__ == "__main__":
    main()
