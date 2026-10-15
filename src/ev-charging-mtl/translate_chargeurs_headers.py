"""Translate French column titles in Montreal EV charging CSVs to English.

Uses the same English titles as the manually cleaned
``chargeurs_statistiques_YYYY.csv`` files. Rewrites the given file in place
(header row only; data rows unchanged).

Usage:
    uv run python src/ev-charging-mtl/translate_chargeurs_headers.py \\
        data/ev-charging-mtl/chargeurs_statistiques.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
import tempfile
from pathlib import Path

# French source titles (trailing whitespace ignored when matching) -> English.
HEADER_TRANSLATIONS = {
    "Borne": "Station",
    "Nombre de borne": "Charger Count",
    "Arrondissement": "Neighbourhood",
    "Intersection": "Intersection",
    "Latitude": "Latitude",
    "Longitude": "Longitude",
    "Adresse": "Address",
    "": "Station Name",
    "Annee": "Year",
    "Mois": "Month",
    "NOMBRE DE RECHARGE": "Charge Sessions",
    "Temps de connexion": "Connection time",
    "KWH total": "KWH total",
    "Temps de connexion mensuel moyen par recharge (TCMMR)": ("Average Monthly Connection Time Per Charge"),
    "Temps de connexion mensuel moyen par jour par connecteur (TCMMJC)": (
        "Average monthly connection time per day per connector"
    ),
    "Taux d'utilisation": "Utilization rate",
    "MOYENNE UTILISATEUR/ JOUR": "Average daily utilization",
}

ENGLISH_HEADERS = frozenset(HEADER_TRANSLATIONS.values())


def translate_header(field: str) -> str:
    """Map one header cell to English, or leave it if already English."""
    key = field.strip()
    if key in HEADER_TRANSLATIONS:
        return HEADER_TRANSLATIONS[key]
    if field in ENGLISH_HEADERS or key in ENGLISH_HEADERS:
        return field.strip() if key in ENGLISH_HEADERS else field
    raise ValueError(f"Unrecognized column title: {field!r}")


def translate_csv_headers_in_place(path: Path) -> list[str]:
    """Rewrite ``path`` with translated headers; return the new header row."""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        try:
            old_header = next(reader)
        except StopIteration as exc:
            raise SystemExit(f"Empty CSV: {path}") from exc
        rows = list(reader)

    try:
        new_header = [translate_header(col) for col in old_header]
    except ValueError as exc:
        raise SystemExit(f"{path}: {exc}") from exc

    # Atomic replace so a failed write does not truncate the source file.
    with tempfile.NamedTemporaryFile(
        mode="w",
        newline="",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
        suffix=".tmp",
    ) as tmp:
        tmp_path = Path(tmp.name)
        writer = csv.writer(tmp)
        writer.writerow(new_header)
        writer.writerows(rows)

    tmp_path.replace(path)
    return new_header


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "csv_path",
        type=Path,
        help="CSV file to rewrite in place (French headers -> English)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    path = args.csv_path
    if not path.is_file():
        print(f"File not found: {path}", file=sys.stderr)
        return 1

    new_header = translate_csv_headers_in_place(path)
    print(f"Updated headers in {path}:", file=sys.stderr)
    for col in new_header:
        print(f"  {col}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
