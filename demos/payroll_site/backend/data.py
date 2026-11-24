"""The facts the agent may state, loaded once: ``data/product.json`` (brand,
modules, plans, pricing rules, customers, tax), ``data/tax_example.json`` (the
worked example on the tax page) and ``content/site.json`` (page copy, the lead
card's vocabulary, the sales calendar). The page reads the same three files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _load(rel: str) -> dict[str, Any]:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


PRODUCT: dict[str, Any] = _load("data/product.json")
TAX_EXAMPLE: dict[str, Any] = _load("data/tax_example.json")
SITE: dict[str, Any] = _load("content/site.json")

BRAND: dict[str, Any] = PRODUCT["brand"]
MODULES: dict[str, dict[str, Any]] = {m["id"]: m for m in PRODUCT["modules"]}
PLANS: dict[str, dict[str, Any]] = {p["id"]: p for p in PRODUCT["plans"]}
PLAN_ORDER: list[str] = [p["id"] for p in PRODUCT["plans"]]
RULES: dict[str, Any] = PRODUCT["pricing_rules"]
CUSTOMERS: list[dict[str, Any]] = PRODUCT["customers"]
TAX: dict[str, Any] = PRODUCT["tax"]

LEAD: dict[str, Any] = SITE["lead"]
PAINS: dict[str, dict[str, Any]] = {p["id"]: p for p in LEAD["pains"]}
TOOLS: dict[str, str] = {t["id"]: t["label"] for t in LEAD["current_tools"]}
STATES: list[str] = list(LEAD["states"])
PAGES: dict[str, str] = dict(SITE["pages"])
CALENDAR: dict[str, Any] = SITE["calendar"]
TOPICS: dict[str, str] = {t["id"]: t["label"] for t in SITE["book_page"]["topics"]}


def inr(amount: int | float) -> str:
    """₹ with Indian digit grouping: 125000 → ₹1,25,000."""
    n = round(amount)
    sign = "-" if n < 0 else ""
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return f"{sign}₹{s}"
