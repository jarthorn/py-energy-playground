"""
Analysis utilities for electricity generation data.

These helpers operate on already-loaded API responses and do not handle
fetching or presentation concerns.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Dict, Iterable, Optional, Tuple

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


@dataclass
class CurrentFuelData:
    """Statistics for a fuel type in the energy mix table."""

    fuel_type: str
    gen_current_month: float
    share_current_month: float
    growth_current_month: Optional[float]  # vs same month last year
    gen_last_12_months: float
    growth_last_12_months: Optional[float]  # vs previous 12 months


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

    def _get_latest_date(self) -> Optional[date]:
        """Get the most recent date from records."""
        if not self.records:
            return None
        return max(record.date for record in self.records)

    @staticmethod
    def _subtract_months(from_date: date, months: int) -> date:
        """
        Subtract a number of months from a date.

        Args:
            from_date: Starting date (assumed to be first day of month)
            months: Number of months to subtract

        Returns:
            New date with months subtracted, on the first day of the month
        """
        year = from_date.year
        month = from_date.month
        month -= months
        while month <= 0:
            month += 12
            year -= 1
        return date(year, month, 1)

    def _get_records_in_date_range(
        self, start_date: date, end_date: date
    ) -> list[GenerationRecord]:
        """Get records within a date range (inclusive)."""
        return [
            record
            for record in self.records
            if start_date <= record.date <= end_date
        ]

    def total_generation_last_12_months(self) -> Tuple[float, Optional[date]]:
        """
        Calculate total generation in TWh for the last 12 months.

        Returns:
            Tuple of (total_twh, latest_date). Returns (0.0, None) if no data.
        """
        latest_date = self._get_latest_date()
        if latest_date is None:
            return (0.0, None)

        start_date = self._subtract_months(latest_date, 11)

        records_12_months = self._get_records_in_date_range(start_date, latest_date)
        total = sum(
            record.generation_twh
            for record in records_12_months
            if record.generation_twh is not None
        )

        return (total, latest_date)

    def total_generation_previous_12_months(self) -> float:
        """
        Calculate total generation in TWh for the 12 months before the last 12 months.

        Returns:
            Total TWh. Returns 0.0 if no data.
        """
        latest_date = self._get_latest_date()
        if latest_date is None:
            return 0.0

        start_date = self._subtract_months(latest_date, 23)
        end_date = self._subtract_months(latest_date, 11)

        # Get records from start_date (inclusive) to end_date (exclusive)
        # Since records are on the 1st, we want end_date to be exclusive
        records_previous = [
            record
            for record in self.records
            if start_date <= record.date < end_date
        ]
        total = sum(
            record.generation_twh
            for record in records_previous
            if record.generation_twh is not None
        )

        return total

    def growth_rate_total(self) -> Optional[float]:
        """
        Calculate growth rate from previous 12 months to last 12 months.

        Returns:
            Growth rate as percentage (e.g., 5.2 for 5.2% growth). Returns None if insufficient data.
        """
        current_total, _ = self.total_generation_last_12_months()
        previous_total = self.total_generation_previous_12_months()

        if previous_total == 0:
            return None

        growth_rate = ((current_total - previous_total) / previous_total) * 100
        return growth_rate

    def fuel_types_above_threshold(self, threshold_pct: float = 10.0) -> list[str]:
        """
        Find fuel types that generate more than threshold_pct of total production in the most recent month.

        Args:
            threshold_pct: Threshold percentage (default: 10.0)

        Returns:
            List of fuel type names sorted by share (descending).
        """
        latest_date = self._get_latest_date()
        if latest_date is None:
            return []

        # Get all records from the most recent month
        latest_records = [r for r in self.records if r.date == latest_date]

        # Calculate total generation for the month
        total_generation = sum(
            record.generation_twh
            for record in latest_records
            if record.generation_twh is not None
        )

        if total_generation == 0:
            return []

        # Find fuel types above threshold
        above_threshold = []
        for record in latest_records:
            if record.generation_twh is not None and record.generation_twh > 0:
                share = (record.generation_twh / total_generation) * 100
                if share > threshold_pct:
                    above_threshold.append((record.fuel_type, share))

        # Sort by share descending
        above_threshold.sort(key=lambda x: x[1], reverse=True)
        return [fuel_type for fuel_type, _ in above_threshold]

    def _calculate_totals_by_fuel_type(self, records: list[GenerationRecord]) -> Dict[str, float]:
        """Aggregate generation TWh by fuel type for a list of records."""
        totals: Dict[str, float] = {}
        for record in records:
            if record.generation_twh is not None:
                totals[record.fuel_type] = totals.get(record.fuel_type, 0.0) + record.generation_twh
        return totals

    def fuel_type_growth_rates(self) -> Dict[str, float]:
        """
        Calculate growth rate for each fuel type from previous 12 months to last 12 months.

        Returns:
            Dictionary mapping fuel_type -> growth_rate (percentage).
            Only includes fuel types with data in both periods.
        """
        latest_date = self._get_latest_date()
        if latest_date is None:
            return {}

        # Last 12 months
        start_last = self._subtract_months(latest_date, 11)
        records_last = self._get_records_in_date_range(start_last, latest_date)

        # Previous 12 months (end_date exclusive logic simulation)
        end_previous = self._subtract_months(latest_date, 11)
        start_previous = self._subtract_months(latest_date, 23)
        records_previous = [
            record
            for record in self.records
            if start_previous <= record.date < end_previous
        ]

        last_by_fuel = self._calculate_totals_by_fuel_type(records_last)
        previous_by_fuel = self._calculate_totals_by_fuel_type(records_previous)

        # Calculate growth rates
        growth_rates: Dict[str, float] = {}
        all_fuel_types = set(last_by_fuel.keys()) | set(previous_by_fuel.keys())

        for fuel_type in all_fuel_types:
            last_total = last_by_fuel.get(fuel_type, 0.0)
            previous_total = previous_by_fuel.get(fuel_type, 0.0)

            if previous_total > 0:
                growth_rate = ((last_total - previous_total) / previous_total) * 100
                growth_rates[fuel_type] = growth_rate
            elif last_total > 0:
                # New fuel type (no previous data) - treat as infinite growth
                # We'll skip these for fastest growing/shrinking
                pass

        return growth_rates

    def fastest_growing_fuel_type(self) -> Optional[Tuple[str, float]]:
        """
        Find the fastest growing fuel type.

        Returns:
            Tuple of (fuel_type, growth_rate) or None if no data.
        """
        growth_rates = self.fuel_type_growth_rates()
        if not growth_rates:
            return None

        fastest = max(growth_rates.items(), key=lambda x: x[1])
        return fastest

    def fastest_shrinking_fuel_type(self) -> Optional[Tuple[str, float]]:
        """
        Find the fastest shrinking (or slowest growing) fuel type.

        Returns:
            Tuple of (fuel_type, growth_rate) or None if no data.
        """
        growth_rates = self.fuel_type_growth_rates()
        if not growth_rates:
            return None

        slowest = min(growth_rates.items(), key=lambda x: x[1])
        return slowest

    def get_energy_mix(self) -> list[CurrentFuelData]:
        """
        Get a snapshot of the energy mix including current month and rolling 12-month stats.

        Returns:
            List of CurrentFuelData objects, one per fuel type.
        """
        latest_date = self._get_latest_date()
        if latest_date is None:
            return []

        # Current month data
        latest_records = [r for r in self.records if r.date == latest_date]
        latest_by_fuel = {r.fuel_type: r for r in latest_records}

        # Date 1 year ago for monthly growth
        one_year_ago_date = self._subtract_months(latest_date, 12)
        one_year_ago_records = [r for r in self.records if r.date == one_year_ago_date]
        one_year_ago_by_fuel = {r.fuel_type: r for r in one_year_ago_records}

        # Rolling 12 month data
        start_last_12 = self._subtract_months(latest_date, 11)
        records_last_12 = self._get_records_in_date_range(start_last_12, latest_date)

        start_prev_12 = self._subtract_months(latest_date, 23)
        end_prev_12 = self._subtract_months(latest_date, 11)
        records_prev_12 = [
            record
            for record in self.records
            if start_prev_12 <= record.date < end_prev_12
        ]

        total_last_12_by_fuel = self._calculate_totals_by_fuel_type(records_last_12)
        total_prev_12_by_fuel = self._calculate_totals_by_fuel_type(records_prev_12)

        mix_records = []
        all_fuel_types = set(latest_by_fuel.keys()) | set(total_last_12_by_fuel.keys())

        for fuel_type in all_fuel_types:
            # Current Month Stats
            current_rec = latest_by_fuel.get(fuel_type)
            gen_current = current_rec.generation_twh if current_rec and current_rec.generation_twh is not None else 0.0
            share_current = current_rec.share_of_generation_pct if current_rec and current_rec.share_of_generation_pct is not None else 0.0

            # Monthly Growth
            prev_year_rec = one_year_ago_by_fuel.get(fuel_type)
            gen_prev_year = prev_year_rec.generation_twh if prev_year_rec and prev_year_rec.generation_twh is not None else 0.0

            growth_current = None
            if gen_prev_year > 0:
                growth_current = ((gen_current - gen_prev_year) / gen_prev_year) * 100

            # 12 Month Stats
            gen_last_12 = total_last_12_by_fuel.get(fuel_type, 0.0)
            gen_prev_12 = total_prev_12_by_fuel.get(fuel_type, 0.0)

            growth_last_12 = None
            if gen_prev_12 > 0:
                growth_last_12 = ((gen_last_12 - gen_prev_12) / gen_prev_12) * 100

            mix_records.append(CurrentFuelData(
                fuel_type=fuel_type,
                gen_current_month=gen_current,
                share_current_month=share_current,
                growth_current_month=growth_current,
                gen_last_12_months=gen_last_12,
                growth_last_12_months=growth_last_12
            ))

        # Sort by share descending
        mix_records.sort(key=lambda x: x.share_current_month, reverse=True)
        return mix_records
