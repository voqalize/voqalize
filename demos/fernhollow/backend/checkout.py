"""Checkout, as Emily fills it by voice: the fields, their checks, the spell-back,
and the order total with the authored delivery charge.

This is a demo with nothing real behind it (CONTRACT.md, v2): Emily may fill
every field from what the shopper says and place the order — but only after
the shopper's spoken yes. An email and a postcode are said back, character by
character where it matters, in one short line, so a mis-heard letter is caught
before the order goes.
"""

from __future__ import annotations

import re
from typing import Literal

from .policies import POLICIES

__all__ = [
    "FIELDS",
    "REQUIRED",
    "STEPS",
    "CheckoutField",
    "CheckoutStepName",
    "check",
    "delivery_fee",
    "spell_back",
]

CheckoutField = Literal[
    "email",
    "first_name",
    "last_name",
    "address1",
    "address2",
    "city",
    "region",
    "postcode",
    "country",
    "phone",
    "delivery",
]
CheckoutStepName = Literal["contact", "shipping", "review"]

FIELDS: tuple[CheckoutField, ...] = (
    "email",
    "first_name",
    "last_name",
    "address1",
    "address2",
    "city",
    "region",
    "postcode",
    "country",
    "phone",
    "delivery",
)
REQUIRED: tuple[CheckoutField, ...] = (
    "email",
    "first_name",
    "last_name",
    "address1",
    "city",
    "postcode",
    "country",
)
# Personal data the shopper types themselves: never asked for aloud, never
# filled by Emily — it would be said into a microphone and into a transcript.
PRIVATE: frozenset[CheckoutField] = frozenset({"email", "phone"})
STEPS: dict[CheckoutStepName, tuple[CheckoutField, ...]] = {
    "contact": ("email", "first_name", "last_name", "phone"),
    "shipping": ("address1", "address2", "city", "region", "postcode", "country", "delivery"),
    "review": (),
}

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_SPOKEN_EMAIL = (
    (r"\s+at\s+", "@"),
    (r"\s+dot\s+", "."),
    (r"\s+underscore\s+", "_"),
    (r"\s+(dash|hyphen)\s+", "-"),
)


def _email(value: str) -> str:
    """An email as the model passes it, with any spoken "at"/"dot" folded."""
    v = f" {value.strip().lower()} "
    for pattern, repl in _SPOKEN_EMAIL:
        v = re.sub(pattern, repl, v)
    return v.strip().replace(" ", "")


def check(field: CheckoutField, value: str) -> tuple[str, str | None]:
    """The value as the form takes it, and why it is not usable (or ``None``)."""
    v = value.strip()
    match field:
        case "email":
            v = _email(v)
            return v, None if _EMAIL.match(v) else "that is not a complete email address"
        case "postcode":
            v = re.sub(r"\s+", " ", v.upper())
            ok = re.fullmatch(r"[A-Z0-9][A-Z0-9 -]{1,9}", v) is not None
            return v, None if ok else "that does not look like a postcode"
        case "phone":
            digits = re.sub(r"[^\d+]", "", v)
            return digits, None if len(
                re.sub(r"\D", "", digits)
            ) >= 7 else "a phone number needs more digits"
        case _:
            return v, None if v else "it is empty"


_SAY = {"@": "at", ".": "dot", "-": "dash", "_": "underscore", "+": "plus"}


def spell_back(field: CheckoutField, value: str) -> str | None:
    """How Emily reads it back: an email's name part letter by letter when it
    is short, then the rest in words; a postcode character by character."""
    if field == "email":
        local, _, domain = value.partition("@")
        name = (
            " ".join(_SAY.get(c, c) for c in local)
            if len(local) <= 12
            else local.replace(".", " dot ")
        )
        return f"{name}, at {domain.replace('.', ' dot ')}"
    if field == "postcode":
        return " ".join(c for c in value if c != " ")
    return None


def delivery_fee(subtotal: float) -> float:
    """The authored delivery charge: free over the threshold, else the flat fee."""
    d = POLICIES.get("delivery", {})
    threshold = float(d.get("freeThreshold", 0))
    fee = float(d.get("flatFee", 0))
    return 0.0 if subtotal == 0 or subtotal > threshold else fee
