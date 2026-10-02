"""What the customer types or taps, and the two ways the screen shows it.

``normalise`` decides whether what arrived is yet a value — a mobile number, a
PAN, one of the closed answers — and ``display_form`` and ``masked_form`` are the
two ways the glass shows it: in full, and as a totem standing in a branch shows
it at rest. None of it is ever spoken: the mobile number and the PAN are typed,
and Tanvi never reads either back.
"""

from __future__ import annotations

import re

from .cards import (
    EMPLOYMENT_SPOKEN,
    EXISTING_CARDS_SPOKEN,
    INCOME_BAND_SPOKEN,
    PROFILE_CHOICES,
    SPEND_SPOKEN,
    CapturedField,
)

__all__ = ["display_form", "masked_form", "normalise"]


# ─── Values the customer gives ─────────────────────────────────────────────────

_MOBILE = re.compile(r"^[6-9]\d{9}$")
_PAN = re.compile(r"^[A-Z]{5}\d{4}[A-Z]$")

#: The four closed vocabularies in one place, keyed by field. The maps in
#: ``cards.py`` are keyed by their own Literal so a missing token is caught
#: there; here they are read by a field name that is only known at runtime.
_SPOKEN_BY_FIELD: dict[str, dict[str, str]] = {
    "employment": {**EMPLOYMENT_SPOKEN},
    "income_band": {**INCOME_BAND_SPOKEN},
    "existing_cards": {**EXISTING_CARDS_SPOKEN},
    "spend_category": {**SPEND_SPOKEN},
}


def normalise(field: CapturedField, value: str) -> str | None:
    """The value as this demo stores it, or ``None`` if it is not one.

    A mobile number arrives with whatever spacing the keypad let through and a
    PAN in whatever case; a closed answer arrives as one of its own tokens or not at
    all. Everything downstream can then assume the shape.
    """
    if field == "mobile":
        digits = re.sub(r"\D", "", value)
        return digits if _MOBILE.match(digits) else None
    if field == "pan":
        pan = re.sub(r"[^A-Za-z0-9]", "", value).upper()
        return pan if _PAN.match(pan) else None
    token = value.strip().lower()
    return token if token in _SPOKEN_BY_FIELD[field] else None


def display_form(field: CapturedField, value: str) -> str:
    """The value for the screen: numerals and labels, never spoken."""
    if field == "mobile":
        return f"{value[:5]} {value[5:]}"
    if field == "pan":
        return value
    labels = {choice[0]: choice[1] for choice in PROFILE_CHOICES[field]}
    return labels[value]


def masked_form(field: CapturedField, value: str) -> str:
    """The value as a totem in a branch should show it at rest."""
    if field == "mobile":
        return f"XXXXX {value[5:]}"
    if field == "pan":
        return f"{value[:5]}XXXX{value[9]}"
    return display_form(field, value)
