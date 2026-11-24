"""Turning what the customer said into the quote form's values, by
``data/products.json``: an option value for a select, digits for an amount
(``14 lakh`` → ``1400000``), a whole number in range for a count."""

from __future__ import annotations

import re
from typing import Any

from voqalize.sdk.stage import match_label

from .amounts import parse
from .rating import CITIES, PRODUCTS

Json = dict[str, Any]


def field_spec(product: str, field_id: str) -> Json | None:
    return next((f for f in PRODUCTS[product]["fields"] if f["id"] == field_id), None)


def field_options(f: Json) -> list[tuple[str, str]]:
    if f.get("options_from") == "cities":
        return [(c["value"], c["label"]) for c in CITIES.values()]
    return [(o["value"], o["label"]) for o in f.get("options", [])]


def money(text: str) -> int | None:
    """Rupees from "14 lakh", "fourteen and a half lakh", "1.5 crore", "₹14,50,000"
    (:func:`.amounts.parse`, the same reading the claim form uses)."""
    heard = parse(text)
    return heard.rupees if heard is not None else None


def normalise(product: str, field_id: str, raw: str) -> tuple[str | None, str]:
    """The stored value, or None and why it was not taken."""
    f = field_spec(product, field_id)
    if f is None:
        ids = ", ".join(x["id"] for x in PRODUCTS[product]["fields"])
        return None, f"not a {product} quote field (fields: {ids})"
    value = str(raw).strip()
    if not value:
        return None, "empty"
    kind = f["type"]
    if kind == "select":
        opts = field_options(f)
        by_value = {v.lower(): v for v, _ in opts}
        if value.lower() in by_value:
            return by_value[value.lower()], ""
        if (amount := money(value)) is not None and str(amount) in by_value:
            return str(amount), ""
        label = match_label(value, [lbl for _, lbl in opts])
        if label is not None:
            return next(v for v, lbl in opts if lbl == label), ""
        if f.get("options_from") == "cities":
            return "other", ""
        return None, "options: " + ", ".join(v for v, _ in opts)
    if kind == "text":
        return value, ""
    n = (
        money(value)
        if kind == "money"
        else (int(m.group()) if (m := re.search(r"\d+", value)) else None)
    )
    if n is None:
        return None, "a number"
    lo, hi = f.get("min"), f.get("max")
    if field_id == "claim_free_years" and n > 5:
        n = 5
    if lo is not None and n < lo:
        return None, f"at least {lo}"
    if hi is not None and n > hi:
        return None, f"at most {hi}"
    return str(n), ""
