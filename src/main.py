import os
import json
import requests
from dotenv import load_dotenv


def find_peak_months_by_series(response_data, value_key):
    """
    Determine which month had the peak value of a given metric for each series.

    Args:
        response_data: Dictionary (API response JSON)
        value_key: Key of the metric to use (e.g. 'share_of_generation_pct', 'generation_twh')

    Returns:
        Dictionary mapping series names to tuples of (peak_month, peak_value)
    """

    # Extract the data array
    data_records = response_data.get("data", [])

    # Group records by series and track the peak for each
    peak_by_series = {}

    for record in data_records:
        series = record.get("series")
        date = record.get("date")
        value = record.get(value_key)

        if series is None or date is None or value is None:
            continue

        # If this is the first record for this series, or if this value is higher
        if series not in peak_by_series or value > peak_by_series[series][1]:
            peak_by_series[series] = (date, value)

    return peak_by_series


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
        + f"?entity_code=CAN&is_aggregate_series=false&start_date=2000-01&api_key={ember_api_key}"
    )
    print(query_url)
    response = requests.get(query_url)
    print("Response code: ", response.status_code)
    if response.status_code == 200:
        data = response.json()

        # Analyze the API response data: share_of_generation_pct
        peak_share_months = find_peak_months_by_series(data, "share_of_generation_pct")

        print_peak_table(
            peak_share_months,
            title="Peak month for share of generation (%)",
            value_label="Peak Value (%)",
        )

        # Analyze the API response data: generation_twh
        peak_gen_months = find_peak_months_by_series(data, "generation_twh")

        print_peak_table(
            peak_gen_months,
            title="Peak month for generation (TWh)",
            value_label="Peak Value (TWh)",
        )
    else:
        print(f"Error: Failed to fetch data. Status code: {response.status_code}")


if __name__ == "__main__":
    main()
