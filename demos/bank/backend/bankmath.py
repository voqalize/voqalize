"""The bank's arithmetic, the brain's half. ``frontend/src/lib/bankmath.ts`` is the
page's, and the two agree to the rupee (CONTRACT.md, "Maths";
``demos/tests/test_bank_e2e.py`` pins the numbers both sides show)."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any

from .bank import CARD_CATEGORIES, CUSTOMER, PRODUCTS


def emi(principal: float, rate_pa: float, months: int) -> float:
    """Reducing-balance EMI."""
    if principal <= 0 or months <= 0:
        return 0.0
    r = rate_pa / 12 / 100
    if r == 0:
        return principal / months
    f = (1 + r) ** months
    return principal * r * f / (f - 1)


def rnd(x: float) -> int:
    """JavaScript's Math.round for non-negative values: halves go up."""
    return math.floor(x + 0.5)


@dataclass(frozen=True)
class EmiRow:
    months: int
    rate: float
    emi: int
    total_interest: int
    processing_fee: int
    gst_on_fee: int
    total_cost: int


def card_emi(amount: float, months: int) -> EmiRow:
    """A card spend converted to EMI for one tenure (``products.emi``)."""
    rate = next(
        (float(t["rate"]) for t in PRODUCTS["emi"]["tenures"] if t["months"] == months), 0.0
    )
    m = rnd(emi(amount, rate, months))
    interest = rnd(m * months - amount)
    e = PRODUCTS["emi"]
    fee = rnd(max(float(e["processing_fee_min"]), amount * float(e["processing_fee_pct"]) / 100))
    gst = rnd(fee * 0.18)
    return EmiRow(months, rate, m, interest, fee, gst, interest + fee + gst)


def card_emi_table(amount: float) -> list[EmiRow]:
    return [card_emi(amount, int(t["months"])) for t in PRODUCTS["emi"]["tenures"]]


EMI_TENURES: tuple[int, ...] = tuple(int(t["months"]) for t in PRODUCTS["emi"]["tenures"])

# ─── Card value ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CardValue:
    card_id: str
    monthly_rewards: int
    yearly_rewards: int
    fuel_saving_yearly: int
    lounge_value: int
    fee: int
    fee_waived: bool
    net_yearly: int
    # True when a known monthly income is below the card's ``min_income_monthly``.
    below_income: bool = False


def card_value(card: dict[str, Any], s: dict[str, float]) -> CardValue:
    """CONTRACT.md "Card value": a card's yearly value for a monthly spend profile."""
    model = PRODUCTS["card_value_model"]
    points = card["reward_type"] == "points"
    rates: dict[str, float] = (card["earn"] if points else card["cashback_rates"]) or {}
    base = float(rates.get("base", 0))
    per = float(card.get("earn_per") or 100)
    pv = float(card["point_value"])
    caps: dict[str, float] = card.get("caps") or {}

    def unit(spend: float, r: float) -> float:
        return spend * r / per * pv if points else spend * r / 100

    fixed = 0.0
    extra = 0.0
    for c in model["categories"]:
        spend = float(s.get(c, 0))
        r = float(rates[c]) if c in rates else base
        if c in model["accelerated"]:
            fixed += unit(spend, min(r, base))
            extra += unit(spend, max(0.0, r - base))
        else:
            term = unit(spend, r)
            if c == "fuel" and caps.get("fuel_cashback_monthly") is not None:
                term = min(term, float(caps["fuel_cashback_monthly"]))
            fixed += term
    if points:
        cap = (
            float(caps["accelerated_points_monthly"]) * pv
            if caps.get("accelerated_points_monthly") is not None
            else math.inf
        )
    else:
        acc = caps.get("accelerated_cashback_monthly")
        cap = float(acc) if acc is not None else math.inf
    monthly = fixed + min(extra, cap)
    fuel_saving = (
        min(float(s.get("fuel", 0)) * 0.01, float(card["fuel"]["surcharge_waiver_cap_monthly"]))
        * 12
    )
    lv = model["lounge_value"]
    lounge = 0
    if float(s.get("travel", 0)) >= lv["travel_spend_threshold"]:
        dom_n = card["lounge"]["domestic_per_year"]
        dom = lv["domestic_used_max"] if dom_n is None else min(dom_n, lv["domestic_used_max"])
        intl = min(card["lounge"]["international_per_year"], lv["international_used_max"])
        lounge = dom * lv["domestic"] + intl * lv["international"]
    yearly_spend = 12 * sum(float(v) for v in s.values())
    waived = yearly_spend >= card["fee_waiver_spend"]
    fee = 0 if waived else int(card["annual_fee"])
    yearly = monthly * 12
    return CardValue(
        card_id=card["id"],
        monthly_rewards=rnd(monthly),
        yearly_rewards=rnd(yearly),
        fuel_saving_yearly=rnd(fuel_saving),
        lounge_value=int(lounge),
        fee=int(card["annual_fee"]),
        fee_waived=waived,
        net_yearly=rnd(yearly + fuel_saving + lounge - fee),
    )


def rank_cards(s: dict[str, float], monthly_income: float | None = None) -> list[CardValue]:
    """Every card by yearly net value, best first. With a known monthly income, the cards
    it qualifies for come first and the rest follow, marked ``below_income``."""
    values = [
        replace(
            card_value(c, s),
            below_income=monthly_income is not None
            and monthly_income < float(c["min_income_monthly"]),
        )
        for c in PRODUCTS["credit_cards"]
    ]
    return sorted(values, key=lambda v: (v.below_income, -v.net_yearly, v.card_id))


def customer_profile() -> dict[str, float]:
    """The customer's own monthly spend: debits of the last 90 days from savings and
    the card, by card category, divided by 3, rounded to ₹100."""
    p = dict.fromkeys(CARD_CATEGORIES, 0.0)
    cat = {c["id"]: c["card_category"] for c in PRODUCTS["spend_categories"]}
    for t in CUSTOMER["transactions"]:
        if t["direction"] != "debit" or t["days_ago"] >= 90 or t["account"] == "ca":
            continue
        k = cat.get(t["category"])
        if k:
            p[k] += float(t["amount"])
    return {k: float(rnd(v / 3 / 100) * 100) for k, v in p.items()}


# ─── Loans ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Eligibility:
    loan_type: str
    rate: float
    tenure_months: int
    max_emi: int | None
    max_amount: int


def loan_eligibility(
    loan: dict[str, Any],
    *,
    monthly_income: float | None = None,
    existing_emis: float | None = None,
    tenure_months: int | None = None,
    gold_grams: float | None = None,
) -> Eligibility:
    rate = float(loan["rate_typical"])
    n = tenure_months or int(loan["tenure_default_months"])
    if loan["id"] == "gold":
        grams = gold_grams or 0.0
        per = float(loan["gold_rate_per_gram_22k"])
        ltv = float(loan.get("ltv_pct") or 75)
        top = min(float(loan["amount_max"]), math.floor(grams * per * ltv / 100 / 1000) * 1000)
        return Eligibility("gold", rate, n, None, int(top))
    income = monthly_income or 0.0
    existing = existing_emis or 0.0
    foir = float(loan["foir"] or 0.5)
    max_emi = max(0.0, income * foir - existing)
    r = rate / 12 / 100
    f = (1 + r) ** n
    raw = max_emi * (f - 1) / (r * f)
    top = min(float(loan["amount_max"]), math.floor(raw / 10000) * 10000)
    return Eligibility(loan["id"], rate, n, rnd(max_emi), int(max(0.0, top)))


# ─── Fixed deposits ───────────────────────────────────────────────────────────


def fd_rate(months: int) -> float | None:
    for r in PRODUCTS["fd"]["rates"]:
        if r["min_months"] <= months <= r["max_months"]:
            return float(r["rate"])
    return None


def fd_quote(amount: float, months: int, payout: str) -> dict[str, float]:
    rate = fd_rate(months) or 0.0
    if payout == "cumulative":
        maturity = rnd(amount * (1 + rate / 400) ** (4 * months / 12))
        return {"rate": rate, "maturity": maturity, "interest": maturity - amount, "payout_each": 0}
    each = rnd(amount * rate / 100 / (12 if payout == "monthly" else 4))
    return {
        "rate": rate,
        "maturity": amount,
        "interest": rnd(amount * rate * months / 1200),
        "payout_each": each,
    }
