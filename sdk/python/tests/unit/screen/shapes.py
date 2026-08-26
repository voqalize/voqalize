"""The nested models ``actions.py`` reaches for by a relative import."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class Urgency(StrEnum):
    LOW = "low"
    HIGH = "high"


class Row(BaseModel):
    """One line of the table."""

    label: str
    amount: float
