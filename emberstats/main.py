import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .load import Load
from .report import ReportRunner


def main(country_code: str):
    project_root = Path(__file__).parent.parent
    data_path = project_root / "data" / f"{country_code.lower()}-monthly-generation.json"

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
        country_code = sys.argv[1]
    else:
        country_code = "CAN"
    main(country_code)
