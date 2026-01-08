import os
import json
import requests
from dotenv import load_dotenv

def find_peak_months_by_series(response_data):
    """
    Determine which month had the peak share_of_generation_pct for each series.

    Args:
        response_data: Either a dictionary (API response) or a string path to a JSON file

    Returns:
        Dictionary mapping series names to tuples of (peak_month, peak_value)
    """

    # Extract the data array
    data_records = response_data.get('data', [])

    # Group records by series and track the peak for each
    peak_by_series = {}

    for record in data_records:
        series = record.get('series')
        date = record.get('date')
        share_pct = record.get('share_of_generation_pct')

        if series is None or date is None or share_pct is None:
            continue

        # If this is the first record for this series, or if this value is higher
        if series not in peak_by_series or share_pct > peak_by_series[series][1]:
            peak_by_series[series] = (date, share_pct)

    return peak_by_series


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
        # Analyze the API response data
        peak_months = find_peak_months_by_series(data)

        print("\n" + "="*70)
        print("Peak months by series (share_of_generation_pct):")
        print("="*70)
        print(f"{'Series':<45} | {'Month':<12} | {'Peak Value':>12}")
        print("-"*70)
        for series, (month, value) in sorted(peak_months.items()):
            print(f"{series:<45} | {month:<12} | {value:>11.2f}%")
    else:
        print(f"Error: Failed to fetch data. Status code: {response.status_code}")


if __name__ == "__main__":
    main()
