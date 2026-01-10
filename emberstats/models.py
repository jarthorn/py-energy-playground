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

    @classmethod
    def from_dict(cls, data: dict) -> GenerationRecord:
        """Create a GenerationRecord from a dictionary (typically from JSON)."""
        date_str = data.get("date", "")
        parsed_date = date.fromisoformat(date_str) if date_str else date.today()

        return cls(
            country=data.get("entity", ""),
            country_code=data.get("entity_code", ""),
            is_aggregate_entity=data.get("is_aggregate_entity", False),
            date=parsed_date,
            fuel_type=data.get("series", ""),
            is_aggregate_series=data.get("is_aggregate_series", False),
            generation_twh=data.get("generation_twh"),
            share_of_generation_pct=data.get("share_of_generation_pct"),
        )
