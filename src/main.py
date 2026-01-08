import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from load import Load
from report import ReportRunner


def main(entity_code: str):
    project_root = Path(__file__).parent.parent
    data_path = project_root / "data" / f"{entity_code.lower()}-monthly-generation.json"

    # Fetch fresh data from the API and store it locally
    loader = Load(
        entity_code=entity_code,
        start_date="2000-01",
        is_aggregate_series=False,
    )
    print("Fetching data from API and storing to:", data_path)
    loader.fetch_and_store(data_path)

    # Read stored data, run analysis, and print to stdout
    reporter = ReportRunner(data_path)
    reporter.run()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        entity_code = sys.argv[1]
    else:
        entity_code = "CAN"
    main(entity_code)
