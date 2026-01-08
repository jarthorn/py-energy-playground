"""
Analysis utilities for electricity generation data.

These helpers operate on already-loaded API responses and do not handle
fetching or presentation concerns.
"""
from __future__ import annotations
from typing import Dict, Iterable, Tuple, Any


class ElectricityStats:
    """Encapsulates analysis over monthly electricity generation records."""

    def __init__(self, records: Iterable[Dict[str, Any]]):
        """
        Args:
            records: Iterable of record dictionaries (typically the API 'data' array).
        """
        self.records: Iterable[Dict[str, Any]] = records or []

    def peak_months_by_series(self, metric_key: str) -> Dict[str, Tuple[str, float]]:
        """
        Compute the month with the peak value for each series for a given metric.

        Args:
            metric_key: Key of the metric to use (e.g. 'share_of_generation_pct', 'generation_twh')

        Returns:
            Mapping: series -> (peak_month, peak_value)
        """
        peak_by_series: Dict[str, Tuple[str, float]] = {}

        for record in self.records:
            series = record.get("series")
            date = record.get("date")
            value = record.get(metric_key)

            if series is None or date is None or value is None:
                continue

            current_peak = peak_by_series.get(series)
            if current_peak is None or value > current_peak[1]:
                peak_by_series[series] = (date, value)

        return peak_by_series
