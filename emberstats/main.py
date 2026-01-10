import sys
from pathlib import Path


from .country_codes import CountryCode
from .load import Load
from .report import ReportRunner


def main(country_code: CountryCode | str):
    """
    Main entrypoint that fetches data and generates reports.

    Args:
        country_code: Country code (CountryCode enum or string that will be validated)
    """
    # Convert string to CountryCode if needed
    if isinstance(country_code, str):
        country_code = CountryCode(country_code.upper())

    project_root = Path(__file__).parent.parent
    data_path = project_root / "data" / f"{country_code.value.lower()}-monthly-generation.json"

    # Fetch fresh data from the API and store it locally
    loader = Load(
        country_code=country_code,
        start_date="2000-01",
        is_aggregate_series=False,
    )
    print("Fetching data from API and storing to:", data_path)
    loader.fetch_and_store(data_path)

    # Read stored data, run analysis, and print to stdout
    reporter = ReportRunner(data_path, country_code)
    reporter.run()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            country_code = CountryCode(sys.argv[1].upper())
        except ValueError:
            print(f"Error: Invalid country code '{sys.argv[1]}'. Please use a valid ISO 3166-1 alpha-3 code.")
            sys.exit(1)
    else:
        country_code = CountryCode.CAN
    main(country_code)
