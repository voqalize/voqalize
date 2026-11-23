"""Anvaya Bank's data as the brain reads it: the same JSON the page reads
(``demos/bank/data``), the persona (``demos/bank/persona.json``), dates made from
``days_ago`` against today, and the transaction filter both sides apply.

Everything here is fictional sample data (CONTRACT.md)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]

PRODUCTS: dict[str, Any] = json.loads((ROOT / "data" / "products.json").read_text("utf-8"))
CUSTOMER: dict[str, Any] = json.loads((ROOT / "data" / "customer.json").read_text("utf-8"))
PERSONA: dict[str, Any] = json.loads((ROOT / "persona.json").read_text("utf-8"))

Lang = Literal["en", "hi"]
LANGUAGES: tuple[str, ...] = tuple(PERSONA["languages"])
DEFAULT_LANGUAGE: str = PERSONA["default_language"]

CARD_CATEGORIES: tuple[str, ...] = tuple(PRODUCTS["card_value_model"]["categories"])
CATEGORY_IDS: tuple[str, ...] = tuple(c["id"] for c in PRODUCTS["spend_categories"])
CATEGORY_NAMES: dict[str, str] = {c["id"]: c["name"] for c in PRODUCTS["spend_categories"]}
CARD_IDS: tuple[str, ...] = tuple(c["id"] for c in PRODUCTS["credit_cards"])
LOAN_IDS: tuple[str, ...] = tuple(loan["id"] for loan in PRODUCTS["loans"])
BRAND: dict[str, Any] = PRODUCTS["brand"]
IST = ZoneInfo("Asia/Kolkata")

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_MONTHS_LONG = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)  # fmt: skip


def voice_for(lang: str) -> str:
    """The persona's voice for ``lang`` (persona.json)."""
    voices: dict[str, str] = PERSONA["voices"]
    return voices.get(lang) or voices[DEFAULT_LANGUAGE]


def today() -> date:
    """Today in India, where the bank and its customer are."""
    from datetime import datetime

    return datetime.now(IST).date()


def days_ago(n: int, now: date | None = None) -> date:
    return (now or today()) - timedelta(days=n)


def fmt_date(d: date) -> str:
    """07 Nov 2026"""
    return f"{d.day:02d} {_MONTHS[d.month - 1]} {d.year}"


def month_key(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def month_name(key: str) -> str:
    y, m = (int(x) for x in key.split("-"))
    return f"{_MONTHS_LONG[m - 1]} {y}"


def month_bounds(key: str, now: date | None = None) -> tuple[int, int]:
    """(from_days_ago, to_days_ago) of a calendar month, clipped to today."""
    t = now or today()
    y, m = (int(x) for x in key.split("-"))
    first = date(y, m, 1)
    last = (date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)) - timedelta(days=1)
    return (t - first).days, max(0, (t - last).days)


def shift_month(key: str, by: int) -> str:
    y, m = (int(x) for x in key.split("-"))
    n = y * 12 + (m - 1) + by
    return f"{n // 12}-{n % 12 + 1:02d}"


def inr(n: float, *, paise: bool | None = None) -> str:
    """Indian grouping: ₹1,25,000 (₹4,999; ₹3,42,815.40)."""
    whole = abs(n)
    show_paise = paise if paise is not None else round(whole * 100) % 100 != 0
    rupees = int(whole)
    frac = round((whole - rupees) * 100)
    if frac == 100:
        rupees, frac = rupees + 1, 0
    s = str(rupees)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join([*groups, tail])
    out = f"₹{s}" + (f".{frac:02d}" if show_paise else "")
    return f"-{out}" if n < 0 else out


# ─── Lookups ──────────────────────────────────────────────────────────────────


def txn(txn_id: str) -> dict[str, Any] | None:
    return next((t for t in CUSTOMER["transactions"] if t["id"] == txn_id), None)


def card_product(card_id: str) -> dict[str, Any] | None:
    return next((c for c in PRODUCTS["credit_cards"] if c["id"] == card_id), None)


def loan_product(loan_id: str) -> dict[str, Any] | None:
    return next((loan for loan in PRODUCTS["loans"] if loan["id"] == loan_id), None)


def biller(biller_id: str) -> dict[str, Any] | None:
    return next((b for b in PRODUCTS["billers"] if b["id"] == biller_id), None)


def beneficiary(ben_id: str) -> dict[str, Any] | None:
    return next((b for b in CUSTOMER["beneficiaries"] if b["id"] == ben_id), None)


def offer(offer_id: str) -> dict[str, Any] | None:
    return next((o for o in CUSTOMER["offers"] if o["id"] == offer_id), None)


ACCOUNT_NAMES = {"sb": "savings", "ca": "current account", "cc": "credit card"}

#: The ``account`` values the transaction filter takes: one account, both bank
#: accounts together (``bank``: savings and current, no credit card), or all.
ACCOUNT_SCOPES = {"sb": ("sb",), "ca": ("ca",), "cc": ("cc",), "bank": ("sb", "ca")}


@dataclass(frozen=True)
class TxnFilter:
    """The transaction filter (CONTRACT.md, ``txn.find``); ``filterTxns`` on the page."""

    account: str | None = None
    category: str | None = None
    query: str | None = None
    from_days_ago: int | None = None
    to_days_ago: int | None = None
    min_amount: float | None = None
    max_amount: float | None = None
    direction: str | None = None


def filter_txns(f: TxnFilter, txns: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    q = (f.query or "").strip().lower()
    out = [
        t
        for t in (txns if txns is not None else CUSTOMER["transactions"])
        if (
            not f.account or f.account == "all" or t["account"] in ACCOUNT_SCOPES.get(f.account, ())
        )
        and (not f.category or t["category"] == f.category)
        and (not q or q in f"{t['merchant']} {t['description']}".lower())
        and (f.from_days_ago is None or t["days_ago"] <= f.from_days_ago)
        and (f.to_days_ago is None or t["days_ago"] >= f.to_days_ago)
        and (f.min_amount is None or t["amount"] >= f.min_amount)
        and (f.max_amount is None or t["amount"] <= f.max_amount)
        and (not f.direction or f.direction == "any" or t["direction"] == f.direction)
    ]
    return sorted(out, key=lambda t: (t["days_ago"], _neg(t["id"])))


def _neg(s: str) -> tuple[int, ...]:
    return tuple(-ord(c) for c in s)
