"""
Analysis utilities for electricity generation data.

These helpers operate on already-loaded API responses and do not handle
fetching or presentation concerns.
"""
from __future__ import annotations
from typing import Dict, Iterable

from .models import GenerationRecord


class ElectricityStats:
    """Encapsulates analysis over monthly electricity generation records."""

    def __init__(self, records: Iterable[GenerationRecord]):
        """
        Args:
            records: Iterable of GenerationRecord objects (typically the API 'data' array).
        """
        self.records: Iterable[GenerationRecord] = records or []

    def peak_months_by_series(self, metric_attr: str) -> Dict[str, GenerationRecord]:
        """
        Compute the month with the peak value for each fuel type for a given metric.

        Args:
            metric_attr: Attribute name of the metric to use (e.g. 'share_of_generation_pct', 'generation_twh')

        Returns:
            Mapping: fuel_type -> GenerationRecord (the record with the peak value for that fuel type)
        """
        peak_by_series: Dict[str, GenerationRecord] = {}

        for record in self.records:
            if not record.fuel_type:
                continue

            value = getattr(record, metric_attr, None)
            if value is None:
                continue

            current_peak = peak_by_series.get(record.fuel_type)
            if current_peak is None:
                peak_by_series[record.fuel_type] = record
            else:
                current_value = getattr(current_peak, metric_attr, None)
                if current_value is not None and value > current_value:
                    peak_by_series[record.fuel_type] = record

        return peak_by_series
