# Objective

This is a simple set of command line tools for analyzing energy data. Data is scraped from external sources into local files in the data directory. Other commands create various summaries and reports based on this data.

# Tech stack

- Python 3.15
- Ruff for python formatting. Please run ruff check and ruff format before committing.

# Conventions

- Raw input data should be stored in the "data" folder, in a sub-folder appropriate for that script
- Output files should be stored in the "output" folder. Output filenames should have a scenario or script name, and a timestamp in the format YYYYMMDD-HHMM from when the output was produced
- One-off scripts go in "src" folder, unless it's a full module such as "emberstats"
- Batch scripts go in "bin" folder
- Follow the coding conventions of an experienced programmer:
  - Minimize code duplication. Use helper functions within a script to avoid duplication, and propose refactorings where duplication is emerging across scripts.
  - Write test cases for complex logic, and regression tests when fixing bugs. I am not concerned with complete code coverage, but focus testing effort on areas with the potential for subtle bugs.
  - Malformed or missing input data should not be ignored. Flag data errors to stderr so that we can follow up and validate input data quality.
  - It is better for a script to fail than produce an incorrect output. Hard fail and exit when an important assumption is invalidated by the code path.