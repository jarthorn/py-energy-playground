"""Project the incremental Ontario electricity demand from converting residential
natural-gas space + water heating to cold-climate heat pumps by 2050.

Method (delivered/useful-energy basis):
    useful_heat   = gas_energy_thermal * gas_efficiency        (per end use)
    hp_electricity = useful_heat / heat_pump_seasonal_COP      (per end use)

The IESO 2025/2026 APO baseline already assumes ~6.3% of households use heat
pumps in 2050. The "incremental over baseline" figure scales the full-conversion
electricity by (1 - baseline_share), treating that share as already electrified.

All energy values are in TWh (thermal for gas/useful heat; electric for output).
Natural-gas energy is taken directly from Statistics Canada deliveries in GJ,
which are on a higher-heating-value (HHV) basis -- consistent with how furnace
AFUE / water-heater efficiency are defined -- so no heating-value assumption is
needed.

Usage:
    uv run python bin/heatpump_projection.py
"""

import csv
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "ieso" / "heatpump-forecast"

# --- Base-case assumptions (documented in the companion .txt) --------------------

# Residential natural gas energy, TWh thermal/yr.
# 10-year (2016-2025) average of StatCan Table 25-10-0059 Ontario residential
# deliveries -> weather-normalized "typical year". Recent annual range: 79-96 TWh.
GAS_ENERGY_TWH = 87.72

# Split of residential gas between space and water heating (assumption: 100% of
# residential gas is space or water heating, per the request).
SHARE_SPACE = 0.70
SHARE_WATER = 0.30

# Average (stock-blended) efficiency of existing gas appliances.
AFUE_SPACE = 0.85    # furnaces: mix of mid- and high-efficiency/condensing
EF_WATER = 0.63      # storage gas water heaters (energy factor)

# Cold-climate heat-pump seasonal COP assumed for 2050.
# Present best-in-class field/seasonal COP in a cold climate is ~3.0; per the
# request, the 2050 average is assumed to EXCEED today's max. Base case 3.5.
COP_2050 = 3.5
COP_SENSITIVITY = [2.5, 3.0, 3.5, 4.0, 4.5]

# IESO baseline heat-pump adoption in 2050 (share of households).
BASELINE_HP_SHARE = 0.063

# Optional: scale today's gas-heating load to projected 2050 household growth.
# Ontario population ~16.1M (2024) -> ~20.3M (2050, interpolated from MOF 2051);
# households assumed to grow proportionally.
HOUSEHOLD_GROWTH_2050 = 20.3 / 16.1  # ~1.26


def hp_electricity(gas_twh: float, cop: float,
                   afue_space: float = AFUE_SPACE, ef_water: float = EF_WATER,
                   share_space: float = SHARE_SPACE, share_water: float = SHARE_WATER):
    """Electricity (TWh) to serve `gas_twh` of gas heating via heat pumps at `cop`."""
    gas_space = gas_twh * share_space
    gas_water = gas_twh * share_water
    useful_space = gas_space * afue_space
    useful_water = gas_water * ef_water
    useful_total = useful_space + useful_water
    elec = useful_total / cop
    return {
        "useful_heat_twh": useful_total,
        "elec_full_twh": elec,
        "elec_incremental_twh": elec * (1 - BASELINE_HP_SHARE),
        "gas_displaced_twh": gas_twh,
    }


def main() -> None:
    rows = []

    for basis, gas in (("current_gas_load", GAS_ENERGY_TWH),
                       ("scaled_to_2050_households", GAS_ENERGY_TWH * HOUSEHOLD_GROWTH_2050)):
        for cop in COP_SENSITIVITY:
            r = hp_electricity(gas, cop)
            rows.append({
                "basis": basis,
                "gas_energy_twh_thermal": round(gas, 2),
                "seasonal_cop": cop,
                "useful_heat_twh": round(r["useful_heat_twh"], 2),
                "elec_full_conversion_twh": round(r["elec_full_twh"], 2),
                "elec_incremental_over_6.3pct_baseline_twh": round(r["elec_incremental_twh"], 2),
            })

    out_csv = DATA_DIR / "heatpump-2050-projection.csv"
    fields = ["basis", "gas_energy_twh_thermal", "seasonal_cop", "useful_heat_twh",
              "elec_full_conversion_twh", "elec_incremental_over_6.3pct_baseline_twh"]
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    base = hp_electricity(GAS_ENERGY_TWH, COP_2050)
    print(f"Base case (current gas load = {GAS_ENERGY_TWH} TWh thermal, COP = {COP_2050}):")
    print(f"  Useful heat delivered:                 {base['useful_heat_twh']:.1f} TWh")
    print(f"  Electricity, full (100%) conversion:   {base['elec_full_twh']:.1f} TWh")
    print(f"  Electricity, incremental over 6.3%:    {base['elec_incremental_twh']:.1f} TWh")
    print(f"\nWrote sensitivity table -> {out_csv}")
    for r in rows:
        print(f"  {r['basis']:<26} COP {r['seasonal_cop']}: "
              f"full {r['elec_full_conversion_twh']:.1f} TWh, "
              f"incremental {r['elec_incremental_over_6.3pct_baseline_twh']:.1f} TWh")


if __name__ == "__main__":
    main()
