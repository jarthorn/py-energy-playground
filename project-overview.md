# Objective

This is a simple set of command line tools for analyzing electricity data. Data is scraped from external sources into local files in the data directory. Other commands create various summaries and reports based on this data.

# Tech stack

- Python 3.15
- Ruff for python formatting. Please run ruff check and ruff format before committing.
- Raw input data should be stored in the "data" folder, in a sub-folder appropriate for that script
- Output files should be stored in the "output" folder. Output filenames should have a scenario or script name, and a timestamp in the format YYYYMMDD-HHMM from when the output was produced