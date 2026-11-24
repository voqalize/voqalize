"""Paynora's price for a team: the plan and the per-employee maths, line by line.

The one pricing function on the brain's side. Its twin is
``frontend/src/lib/pricing.ts``; both are held to ``content/pricing_cases.json``
(``test_payroll_site_e2e.py`` and ``pricing.test.ts``), so the number the agent
says is the number the calculator shows.

The rule is ``pricing_rules.plan_choice`` in ``data/product.json``: the cheapest
plan that covers the headcount and every module asked for; the monthly fee is
headcount x price per employee, or the plan minimum when that is higher. The
statutory filing add-on is only on the plans it lists, so asking for it is one
more thing the plan must cover. Annual billing takes ``annual_discount_pct`` off
the monthly fee (the add-on included) and waives the setup fee; GST is added on
top of everything. Every amount is whole rupees, rounded half up.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .data import MODULES, PLAN_ORDER, PLANS, RULES, inr

Billing = Literal["monthly", "annual"]


def pct(amount: int, percent: int | float) -> int:
    """``percent`` of ``amount`` in whole rupees, half up (the TS twin does the same)."""
    return int((amount * percent * 100 + 5000) // 10000)


@dataclass
class Line:
    key: str
    label: str
    amount: int
    note: str = ""


@dataclass
class Quote:
    status: Literal["ok", "custom"]
    headcount: int
    modules: list[str]
    billing: Billing
    filing: bool
    plan: str = ""
    plan_name: str = ""
    why: list[str] = field(default_factory=list)
    rate: int = 0
    base: int = 0
    minimum: int = 0
    minimum_applies: bool = False
    subscription: int = 0
    filing_fee: int = 0
    monthly: int = 0
    discount: int = 0
    monthly_net: int = 0
    gst: int = 0
    monthly_total: int = 0
    setup_fee: int = 0
    setup_waived: bool = False
    setup_due: int = 0
    setup_gst: int = 0
    annual_net: int = 0
    annual_gst: int = 0
    annual_total: int = 0
    lines: list[Line] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _filing() -> dict[str, Any]:
    return next(a for a in RULES["addons"] if a["id"] == "filing")


def choose_plan(headcount: int, modules: list[str], filing: bool) -> tuple[str | None, list[str]]:
    """The cheapest plan covering the headcount, the modules and the add-on;
    ``None`` above the largest plan. The reasons, in words, for the agent."""
    need = 0
    why: list[str] = []
    for m in modules:
        rank = PLAN_ORDER.index(MODULES[m]["min_plan"])
        if rank > 0:
            why.append(f"{MODULES[m]['name']} needs {PLANS[PLAN_ORDER[rank]]['name']} or above")
        need = max(need, rank)
    if filing:
        first = min(PLAN_ORDER.index(p) for p in _filing()["available_on"])
        why.append(f"the filing service is on {PLANS[PLAN_ORDER[first]]['name']} and above")
        need = max(need, first)
    for plan_id in PLAN_ORDER[need:]:
        plan = PLANS[plan_id]
        if headcount <= plan["max_employees"]:
            if PLAN_ORDER.index(plan_id) > need:
                why.append(
                    f"{headcount} employees is above the {PLANS[PLAN_ORDER[need]]['name']} limit"
                )
            return plan_id, why
    return None, why


def quote(
    headcount: int,
    modules: list[str] | None = None,
    billing: Billing = "monthly",
    filing: bool = False,
) -> Quote:
    mods = [m for m in dict.fromkeys(modules or []) if m in MODULES]
    q = Quote(status="ok", headcount=headcount, modules=mods, billing=billing, filing=filing)
    plan_id, why = choose_plan(headcount, mods, filing)
    q.why = why
    if plan_id is None:
        q.status = "custom"
        return q
    plan = PLANS[plan_id]
    q.plan, q.plan_name = plan_id, plan["name"]
    q.rate = int(plan["price_per_employee_month"])
    q.base = headcount * q.rate
    q.minimum = int(plan["minimum_month"])
    q.minimum_applies = q.base < q.minimum
    q.subscription = max(q.base, q.minimum)
    addon = _filing()
    q.filing_fee = headcount * int(addon["price_per_employee_month"]) if filing else 0
    q.monthly = q.subscription + q.filing_fee
    q.discount = pct(q.monthly, RULES["annual_discount_pct"]) if billing == "annual" else 0
    q.monthly_net = q.monthly - q.discount
    q.gst = pct(q.monthly_net, RULES["gst_pct"])
    q.monthly_total = q.monthly_net + q.gst
    q.setup_fee = int(plan["setup_fee"])
    q.setup_waived = (
        billing == "annual" and bool(RULES["setup_fee_waived_on_annual"]) and q.setup_fee > 0
    )
    q.setup_due = 0 if q.setup_waived else q.setup_fee
    q.setup_gst = pct(q.setup_due, RULES["gst_pct"])
    q.annual_net = q.monthly_net * 12
    q.annual_gst = pct(q.annual_net, RULES["gst_pct"])
    q.annual_total = q.annual_net + q.annual_gst
    q.lines = _lines(q)
    return q


def _lines(q: Quote) -> list[Line]:
    gst = RULES["gst_pct"]
    out = [
        Line("base", f"{q.headcount} employees × {inr(q.rate)}", q.base, f"{q.plan_name} plan"),  # noqa: RUF001
        Line(
            "minimum",
            f"Plan minimum {inr(q.minimum)}",
            q.subscription,
            "applies: your fee is the minimum"
            if q.minimum_applies
            else "not applied: you are above it",
        ),
    ]
    if q.filing:
        rate = int(_filing()["price_per_employee_month"])
        out.append(
            Line("filing", f"Filing service, {q.headcount} × {inr(rate)}", q.filing_fee, "add-on")  # noqa: RUF001
        )
    out.append(Line("subtotal", "Monthly fee", q.monthly, "before GST"))
    if q.billing == "annual":
        out.append(
            Line(
                "discount",
                f"Annual billing, {RULES['annual_discount_pct']}% off",
                -q.discount,
                f"{inr(q.monthly_net)} a month",
            )
        )
    out.append(Line("gst", f"GST {gst}%", q.gst, "on the monthly fee"))
    out.append(Line("total", "Monthly total with GST", q.monthly_total, ""))
    if q.billing == "annual":
        out.append(Line("annual", "Billed yearly, with GST", q.annual_total, "12 months"))
    if q.setup_fee:
        out.append(
            Line(
                "setup",
                "One-time setup fee",
                q.setup_due,
                "waived on annual billing"
                if q.setup_waived
                else f"plus {inr(q.setup_gst)} GST, waived if you pay annually",
            )
        )
    else:
        out.append(Line("setup", "One-time setup fee", 0, "none on this plan"))
    return out


def spoken(q: Quote) -> str:
    """The maths as the tool hands it to the model: every line, in order."""
    if q.status == "custom":
        return f"{q.headcount} employees: {RULES['above_max_employees']}"
    why = f" ({'; '.join(q.why)})" if q.why else ""
    lines = "; ".join(
        f"{line.label} = {inr(line.amount)}" + (f" ({line.note})" if line.note else "")
        for line in q.lines
    )
    return f"Plan: {q.plan_name}{why}. {lines}. Prices exclude GST unless the line says so."
