"""
Analysis utilities for electricity generation data.

These helpers operate on already-loaded API responses and do not handle
fetching or presentation concerns.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Dict, Iterable

from .country_codes import CountryCode
from .models import GenerationRecord


@dataclass
class NewRecord:
    """Represents a new record set by a country in the latest month."""

    country_code: CountryCode
    country_name: str
    fuel_type: str
    date: str
    value: float
    previous_peak: float


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

    def find_new_records_in_latest_month(
        self,
        latest_date: date,
        metric_attr: str,
        country_code: CountryCode,
        country_name: str,
    ) -> list[NewRecord]:
        """
        Find fuel types that set new records in the latest month compared to all previous months.

        Args:
            latest_date: The date of the latest month to analyze
            metric_attr: Attribute name of the metric to use (e.g. 'share_of_generation_pct', 'generation_twh')
            country_code: Country code for the records
            country_name: Country name for the records

        Returns:
            List of NewRecord objects for fuel types that set new records in the latest month
        """
        # Get all records from before the latest month
        records_before_latest = [r for r in self.records if r.date < latest_date]
        latest_records = [r for r in self.records if r.date == latest_date]

        # For each fuel type, find the peak before latest month
        stats_before = ElectricityStats(records_before_latest)
        peaks_before = stats_before.peak_months_by_series(metric_attr)

        new_records = []
        # Check each latest month record to see if it's a new peak
        for latest_record in latest_records:
            if not latest_record.fuel_type:
                continue

            value = getattr(latest_record, metric_attr, None)
            if value is None:
                continue

            previous_peak_record = peaks_before.get(latest_record.fuel_type)
            previous_peak_value = (
                getattr(previous_peak_record, metric_attr, None) if previous_peak_record else None
            )

            # If no previous peak or latest value exceeds previous peak
            if previous_peak_value is None or value > previous_peak_value:
                new_records.append(
                    NewRecord(
                        country_code=country_code,
                        country_name=country_name,
                        fuel_type=latest_record.fuel_type,
                        date=latest_date.isoformat(),
                        value=value,
                        previous_peak=previous_peak_value if previous_peak_value is not None else 0.0,
                    )
                )

        return new_records
