"""
Data models for electricity generation records.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class GenerationRecord:
    """Represents a single monthly electricity generation record from the API."""

    country: str
    country_code: str
    is_aggregate_entity: bool
    date: date
    fuel_type: str
    is_aggregate_series: bool
    generation_twh: Optional[float]
    share_of_generation_pct: Optional[float]
    is_latest_month: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> GenerationRecord:
        """
        Create a GenerationRecord from a dictionary (typically from JSON).

        Raises:
            ValueError: If date is missing or has an invalid format
        """
        date_str = data.get("date", "")
        if not date_str:
            raise ValueError(f"Missing required 'date' field in record: {data}")
        try:
            parsed_date = date.fromisoformat(date_str)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid date format '{date_str}' in record: {data}") from e

        return cls(
            country=data.get("entity", ""),
            country_code=data.get("entity_code", ""),
            is_aggregate_entity=data.get("is_aggregate_entity", False),
            date=parsed_date,
            fuel_type=data.get("series", ""),
            is_aggregate_series=data.get("is_aggregate_series", False),
            generation_twh=data.get("generation_twh"),
            share_of_generation_pct=data.get("share_of_generation_pct"),
            is_latest_month=False,
        )
