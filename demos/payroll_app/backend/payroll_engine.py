"""Paynora's payroll and income-tax engine: salary structure, monthly payslip and
TDS on salary, and the old-vs-new regime computation for one stated year.

Pure functions over integers (rupees). The rules are read from
``data/product.json`` (``tax``), the one file both demos share, and
``frontend/src/lib/engine.ts`` is this module's twin in TypeScript: both are held
to ``data/tax_fixtures.json``, which ``data/build_data.py`` writes from this file.

Rounding is half-up to the rupee everywhere; total income and the tax payable are
then rounded to the nearest ₹10 (sections 288A and 288B). Surcharge is not
modelled: every sample employee is below ₹50 lakh, and ``build_data.py`` asserts it.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any, Literal

Regime = Literal["new", "old"]

PRODUCT_PATH = Path(__file__).resolve().parent.parent / "data" / "product.json"

# Months of the financial year, April first. Index 10 is February (PT's 13th instalment).
FY_MONTHS = ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]
FEBRUARY = 10


def rnd(x: Fraction | int) -> int:
    """Half-up to the rupee (all amounts here are positive)."""
    f = Fraction(x)
    return int((f + Fraction(1, 2)) // 1)


def ceil(x: Fraction | int) -> int:
    f = Fraction(x)
    return int(-((-f) // 1))


def round10(x: int) -> int:
    """Nearest ₹10, five and above going up (sections 288A / 288B)."""
    return ((x + 5) // 10) * 10


# --------------------------------------------------------------------------- rules


@dataclass(frozen=True)
class Slab:
    lo: int
    hi: int | None
    rate: int


@dataclass(frozen=True)
class RegimeRules:
    slabs: tuple[Slab, ...]
    standard_deduction: int
    rebate_limit: int
    rebate_max: int
    marginal_relief: bool


@dataclass(frozen=True)
class PtRule:
    slabs: tuple[Slab, ...]
    slabs_women: tuple[Slab, ...] | None
    february: int | None


@dataclass(frozen=True)
class Rules:
    new: RegimeRules
    old: RegimeRules
    cess_pct: int
    limits: dict[str, int]
    metro_cities: tuple[str, ...]
    hra_metro_pct: int
    hra_non_metro_pct: int
    hra_rent_minus_basic_pct: int
    pf_ceiling: int
    pf_pct: int
    esi_ceiling: int
    esi_employee_bp: int  # basis points: 0.75% = 75
    esi_employer_bp: int  # 3.25% = 325
    pt: dict[str, PtRule]

    def regime(self, regime: Regime) -> RegimeRules:
        return self.new if regime == "new" else self.old


def _slabs(raw: list[list[int | None]]) -> tuple[Slab, ...]:
    out: list[Slab] = []
    for lo, hi, rate in raw:
        assert lo is not None
        assert rate is not None
        out.append(Slab(lo=lo, hi=hi, rate=rate))
    return tuple(out)


def _regime(raw: dict[str, Any]) -> RegimeRules:
    rebate: dict[str, Any] = raw["rebate_87a"]
    return RegimeRules(
        slabs=_slabs(raw["slabs"]),
        standard_deduction=int(raw["standard_deduction"]),
        rebate_limit=int(rebate["income_limit"]),
        rebate_max=int(rebate["max"]),
        marginal_relief=bool(rebate["marginal_relief"]),
    )


def load_rules(product: dict[str, Any]) -> Rules:
    tax: dict[str, Any] = product["tax"]
    pt: dict[str, PtRule] = {}
    for state, r in tax["professional_tax"]["states"].items():
        rule: dict[str, Any] = r
        women = rule.get("slabs_women")
        feb = rule.get("february")
        pt[str(state)] = PtRule(
            slabs=_slabs(rule["slabs"]),
            slabs_women=_slabs(women) if women else None,
            february=int(feb) if feb is not None else None,
        )
    hra: dict[str, Any] = tax["hra"]
    return Rules(
        new=_regime(tax["regimes"]["new"]),
        old=_regime(tax["regimes"]["old"]),
        cess_pct=int(tax["cess_pct"]),
        limits={str(k): int(v) for k, v in tax["limits"].items()},
        metro_cities=tuple(hra["metro_cities"]),
        hra_metro_pct=int(hra["metro_pct"]),
        hra_non_metro_pct=int(hra["non_metro_pct"]),
        hra_rent_minus_basic_pct=int(hra["rent_minus_basic_pct"]),
        pf_ceiling=int(tax["pf"]["wage_ceiling"]),
        pf_pct=int(tax["pf"]["employee_pct"]),
        esi_ceiling=int(tax["esi"]["gross_ceiling"]),
        esi_employee_bp=round(float(tax["esi"]["employee_pct"]) * 100),
        esi_employer_bp=round(float(tax["esi"]["employer_pct"]) * 100),
        pt=pt,
    )


def load_product(path: Path = PRODUCT_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


RULES = load_rules(load_product())


# ------------------------------------------------------------- salary structure


@dataclass(frozen=True)
class Structure:
    """One full month of an employee's salary, from annual CTC."""

    basic: int
    hra: int
    lta: int
    special: int
    gross: int
    employer_pf: int
    employer_esi: int
    esi_applicable: bool
    monthly_ctc: int


def is_metro(city: str, rules: Rules = RULES) -> bool:
    return city in rules.metro_cities


def structure(ctc: int, city: str, lta_monthly: int = 0, rules: Rules = RULES) -> Structure:
    """Basic 40% of monthly CTC; HRA 50% of basic in a metro, 40% elsewhere; LTA as
    given; employer PF 12% of basic up to the wage ceiling; employer ESI 3.25% when
    gross is within the ESI ceiling; special allowance is the balance."""
    monthly = rnd(Fraction(ctc, 12))
    basic = rnd(Fraction(monthly * 40, 100))
    hra_pct = rules.hra_metro_pct if is_metro(city, rules) else rules.hra_non_metro_pct
    hra = rnd(Fraction(basic * hra_pct, 100))
    er_pf = rnd(Fraction(min(basic, rules.pf_ceiling) * rules.pf_pct, 100))
    gross = monthly - er_pf
    er_esi = 0
    esi = False
    # Gross with ESI is what is left after employer ESI on that same gross.
    candidate = int(Fraction((monthly - er_pf) * 10000, 10000 + rules.esi_employer_bp) // 1)
    if candidate <= rules.esi_ceiling:
        esi = True
        er_esi = ceil(Fraction(candidate * rules.esi_employer_bp, 10000))
        gross = monthly - er_pf - er_esi
    special = gross - basic - hra - lta_monthly
    assert special >= 0, f"special allowance negative for ctc {ctc}"
    return Structure(
        basic=basic,
        hra=hra,
        lta=lta_monthly,
        special=special,
        gross=gross,
        employer_pf=er_pf,
        employer_esi=er_esi,
        esi_applicable=esi,
        monthly_ctc=monthly,
    )


def professional_tax(
    state: str, gender: str, gross: int, month_idx: int, rules: Rules = RULES
) -> int:
    rule = rules.pt.get(state)
    if rule is None:
        return 0
    slabs = rule.slabs_women if (gender == "F" and rule.slabs_women) else rule.slabs
    amount = 0
    for s in slabs:
        if gross >= s.lo and (s.hi is None or gross <= s.hi):
            amount = s.rate
    if amount == 200 and month_idx == FEBRUARY and rule.february is not None:
        return rule.february
    return amount


def employee_pf(earned_basic: int, rules: Rules = RULES) -> int:
    return rnd(Fraction(min(earned_basic, rules.pf_ceiling) * rules.pf_pct, 100))


def employee_esi(earned_gross: int, applicable: bool, rules: Rules = RULES) -> int:
    return ceil(Fraction(earned_gross * rules.esi_employee_bp, 10000)) if applicable else 0


# ------------------------------------------------------------------ income tax


@dataclass
class Declarations:
    """What an employee claims for the year (declared, or verified from proofs).
    Rent is per month; it counts only for the months the employee is paid."""

    rent_monthly: int = 0
    sec80c_other: int = 0  # 80C items other than EPF (EPF is added from payroll)
    sec80d_self: int = 0
    sec80d_parents: int = 0
    parents_senior: bool = False
    sec80ccd1b: int = 0
    home_loan_interest: int = 0
    lta_claim: int = 0


@dataclass
class AnnualSalary:
    """The year's salary as the tax computation sees it (actual plus projected)."""

    gross: int
    basic: int
    hra: int
    lta: int
    employee_pf: int
    professional_tax: int
    months: int  # months paid in the year, for rent
    metro: bool


@dataclass
class SlabLine:
    lo: int
    hi: int | None
    rate: int
    taxable: int
    tax: int


@dataclass
class TaxBreakdown:
    regime: Regime
    gross_salary: int
    exempt_hra: int
    exempt_lta: int
    standard_deduction: int
    professional_tax: int
    income_from_salary: int
    house_property: int  # negative: home-loan interest
    gross_total_income: int
    ded_80c: int
    ded_80ccd1b: int
    ded_80d: int
    total_deductions: int
    taxable_income: int
    slabs: list[SlabLine] = field(default_factory=list[SlabLine])
    tax_on_income: int = 0
    rebate_87a: int = 0
    marginal_relief: int = 0
    tax_after_rebate: int = 0
    cess: int = 0
    total_tax: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def hra_exemption(sal: AnnualSalary, rent_annual: int, rules: Rules = RULES) -> int:
    if rent_annual <= 0 or sal.hra <= 0:
        return 0
    pct = rules.hra_metro_pct if sal.metro else rules.hra_non_metro_pct
    rent_less = rent_annual - rnd(Fraction(sal.basic * rules.hra_rent_minus_basic_pct, 100))
    return max(0, min(sal.hra, rent_less, rnd(Fraction(sal.basic * pct, 100))))


def slab_tax(income: int, slabs: tuple[Slab, ...]) -> tuple[int, list[SlabLine]]:
    total = 0
    lines: list[SlabLine] = []
    for s in slabs:
        top = income if s.hi is None else min(income, s.hi)
        part = max(0, top - s.lo)
        tax = rnd(Fraction(part * s.rate, 100))
        lines.append(SlabLine(lo=s.lo, hi=s.hi, rate=s.rate, taxable=part, tax=tax))
        total += tax
    return total, lines


def compute_tax(
    regime: Regime, sal: AnnualSalary, decl: Declarations, rules: Rules = RULES
) -> TaxBreakdown:
    r = rules.regime(regime)
    lim = rules.limits
    old = regime == "old"
    exempt_hra = hra_exemption(sal, decl.rent_monthly * sal.months, rules) if old else 0
    exempt_lta = min(decl.lta_claim, sal.lta) if old else 0
    pt = min(sal.professional_tax, lim["professional_tax"]) if old else 0
    sd = min(r.standard_deduction, sal.gross - exempt_hra - exempt_lta)
    salary_income = max(0, sal.gross - exempt_hra - exempt_lta - sd - pt)
    house = -min(decl.home_loan_interest, lim["24b"]) if old else 0
    gti = max(0, salary_income + house)
    d80c = min(lim["80C"], sal.employee_pf + decl.sec80c_other) if old else 0
    d80ccd = min(lim["80CCD1B"], decl.sec80ccd1b) if old else 0
    parents_cap = lim["80D_parents_senior"] if decl.parents_senior else lim["80D_parents"]
    d80d = (
        (min(decl.sec80d_self, lim["80D_self"]) + min(decl.sec80d_parents, parents_cap))
        if old
        else 0
    )
    total_ded = min(gti, d80c + d80ccd + d80d)
    taxable = round10(gti - total_ded)
    tax, lines = slab_tax(taxable, r.slabs)
    rebate = 0
    relief = 0
    if taxable <= r.rebate_limit:
        rebate = min(tax, r.rebate_max)
    elif r.marginal_relief and tax > taxable - r.rebate_limit:
        relief = tax - (taxable - r.rebate_limit)
    after = tax - rebate - relief
    cess = rnd(Fraction(after * rules.cess_pct, 100))
    return TaxBreakdown(
        regime=regime,
        gross_salary=sal.gross,
        exempt_hra=exempt_hra,
        exempt_lta=exempt_lta,
        standard_deduction=sd,
        professional_tax=pt,
        income_from_salary=salary_income,
        house_property=house,
        gross_total_income=gti,
        ded_80c=d80c,
        ded_80ccd1b=d80ccd,
        ded_80d=d80d,
        total_deductions=total_ded,
        taxable_income=taxable,
        slabs=lines,
        tax_on_income=tax,
        rebate_87a=rebate,
        marginal_relief=relief,
        tax_after_rebate=after,
        cess=cess,
        total_tax=round10(after + cess),
    )


# ------------------------------------------------------------------- payslip


@dataclass
class Ytd:
    """Year to date, through the month before the one being run."""

    gross: int = 0
    basic: int = 0
    hra: int = 0
    lta: int = 0
    employee_pf: int = 0
    professional_tax: int = 0
    tds: int = 0
    months: int = 0

    def plus(self, slip: Payslip) -> Ytd:
        return Ytd(
            gross=self.gross + slip.gross,
            basic=self.basic + slip.basic,
            hra=self.hra + slip.hra,
            lta=self.lta + slip.lta,
            employee_pf=self.employee_pf + slip.employee_pf,
            professional_tax=self.professional_tax + slip.professional_tax,
            tds=self.tds + slip.tds,
            months=self.months + 1,
        )


@dataclass
class Payslip:
    month_idx: int
    days: int
    lop_days: int
    paid_days: int
    basic: int
    hra: int
    lta: int
    special: int
    gross: int
    employee_pf: int
    employee_esi: int
    professional_tax: int
    tds: int
    reimbursements: int
    total_deductions: int
    net_pay: int
    employer_pf: int
    employer_esi: int
    annual_tax: int  # the projected annual tax this month's TDS was spread from

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EmployeePay:
    """What the engine needs to know about one employee."""

    ctc: int
    city: str
    state: str
    gender: str
    lta_monthly: int
    regime: Regime
    first_month_idx: int = 0  # the FY month they joined (0 = April or earlier)


def projected_annual(
    emp: EmployeePay, ytd: Ytd, this: Payslip | None, month_idx: int, rules: Rules = RULES
) -> AnnualSalary:
    """Year-to-date actuals, this month as computed, and full months after it."""
    st = structure(emp.ctc, emp.city, emp.lta_monthly, rules)
    gross, basic, hra, lta, pf, pt = (
        ytd.gross,
        ytd.basic,
        ytd.hra,
        ytd.lta,
        ytd.employee_pf,
        ytd.professional_tax,
    )
    months = ytd.months
    start = month_idx
    if this is not None:
        gross += this.gross
        basic += this.basic
        hra += this.hra
        lta += this.lta
        pf += this.employee_pf
        pt += this.professional_tax
        months += 1
        start = month_idx + 1
    for m in range(max(start, emp.first_month_idx), 12):
        gross += st.gross
        basic += st.basic
        hra += st.hra
        lta += st.lta
        pf += employee_pf(st.basic, rules)
        pt += professional_tax(emp.state, emp.gender, st.gross, m, rules)
        months += 1
    return AnnualSalary(
        gross=gross,
        basic=basic,
        hra=hra,
        lta=lta,
        employee_pf=pf,
        professional_tax=pt,
        months=months,
        metro=is_metro(emp.city, rules),
    )


def payslip(
    emp: EmployeePay,
    month_idx: int,
    days: int,
    lop_days: int,
    ytd: Ytd,
    decl: Declarations,
    reimbursements: int = 0,
    regime: Regime | None = None,
    rules: Rules = RULES,
) -> Payslip:
    """One month's payslip, TDS included: the year's projected tax less TDS so far,
    spread evenly over this month and the months left."""
    st = structure(emp.ctc, emp.city, emp.lta_monthly, rules)
    paid = days - lop_days

    def earned(x: int) -> int:
        return rnd(Fraction(x * paid, days))

    basic, hra, lta, special = earned(st.basic), earned(st.hra), earned(st.lta), earned(st.special)
    gross = basic + hra + lta + special
    pf = employee_pf(basic, rules)
    esi = employee_esi(gross, st.esi_applicable, rules)
    pt = professional_tax(emp.state, emp.gender, gross, month_idx, rules)
    er_pf = employee_pf(basic, rules)
    er_esi = ceil(Fraction(gross * rules.esi_employer_bp, 10000)) if st.esi_applicable else 0
    slip = Payslip(
        month_idx=month_idx,
        days=days,
        lop_days=lop_days,
        paid_days=paid,
        basic=basic,
        hra=hra,
        lta=lta,
        special=special,
        gross=gross,
        employee_pf=pf,
        employee_esi=esi,
        professional_tax=pt,
        tds=0,
        reimbursements=reimbursements,
        total_deductions=0,
        net_pay=0,
        employer_pf=er_pf,
        employer_esi=er_esi,
        annual_tax=0,
    )
    annual = projected_annual(emp, ytd, slip, month_idx, rules)
    tax = compute_tax(regime or emp.regime, annual, decl, rules).total_tax
    left = 12 - month_idx
    slip.tds = max(0, rnd(Fraction(tax - ytd.tds, left)))
    slip.annual_tax = tax
    slip.total_deductions = pf + esi + pt + slip.tds
    slip.net_pay = gross - slip.total_deductions + reimbursements
    return slip


def regime_comparison(
    emp: EmployeePay, ytd: Ytd, month_idx: int, decl: Declarations, rules: Rules = RULES
) -> dict[str, Any]:
    """Both regimes on the same projected year (actuals to date, full months after),
    as the employee would see before choosing."""
    annual = projected_annual(emp, ytd, None, month_idx, rules)
    new = compute_tax("new", annual, decl, rules)
    old = compute_tax("old", annual, decl, rules)
    better: Regime = "new" if new.total_tax <= old.total_tax else "old"
    return {
        "annual_salary": asdict(annual),
        "new": new.to_dict(),
        "old": old.to_dict(),
        "better": better,
        "saving": abs(new.total_tax - old.total_tax),
    }
