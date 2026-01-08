import os
import requests
from dotenv import load_dotenv

from analysis import ElectricityStats


def print_peak_table(peak_months, title, value_label):
    """
    Print a formatted table of peak months for each series.

    Args:
        peak_months: dict[series] -> (month, value)
        title: Table title string
        value_label: Column header label for the value column
    """
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)
    print(f"{'Series':<45} | {'Month':<12} | {value_label:>16}")
    print("-" * 70)
    for series, (month, value) in sorted(peak_months.items()):
        print(f"{series:<45} | {month:<12} | {value:>15.2f}")


def main():
    load_dotenv()
    ember_api_key = os.getenv("EMBER_API_KEY")
    base_url = "https://api.ember-energy.org"
    query_url = (
        f"{base_url}/v1/electricity-generation/monthly"
        + f"?entity_code=ESP&is_aggregate_series=false&start_date=2000-01&api_key={ember_api_key}"
    )
    print(query_url)
    response = requests.get(query_url)
    print("Response code: ", response.status_code)
    if response.status_code == 200:
        data = response.json()
        records = data.get("data", [])

        analyzer = ElectricityStats(records)

        # Analyze the API response data: share_of_generation_pct
        peak_share_months = analyzer.peak_months_by_series("share_of_generation_pct")

        print_peak_table(
            peak_share_months,
            title="Peak month for share of generation (%)",
            value_label="Peak Value (%)",
        )

        # Analyze the API response data: generation_twh
        peak_gen_months = analyzer.peak_months_by_series("generation_twh")

        print_peak_table(
            peak_gen_months,
            title="Peak month for generation (TWh)",
            value_label="Peak Value (TWh)",
        )
    else:
        print(f"Error: Failed to fetch data. Status code: {response.status_code}")


if __name__ == "__main__":
    main()
