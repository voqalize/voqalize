"""The customer's books for one session: Banyan & Bay Foods, from ``data/company.json``.

A session starts from first principles: a fresh copy of the company as the
backend holds it, mutated only by what happens in this call (the admin's clicks,
reported as typed events, and the agent's own confirmed moves once the page says
they landed). Every number the agent says is read from here or computed by
:mod:`.payroll_engine`, with the same rules ``frontend/src/lib/engine.ts`` and the
page's store apply (``CONTRACT.md``, "Recomputation rules"), so the voice and the
screen give the same rupee.
"""

from __future__ import annotations

import copy
import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from . import payroll_engine as eng

DATA = Path(__file__).resolve().parent.parent / "data"
COMPANY: dict[str, Any] = json.loads((DATA / "company.json").read_text(encoding="utf-8"))
PRODUCT: dict[str, Any] = json.loads((DATA / "product.json").read_text(encoding="utf-8"))
IMPORT_CSV = DATA / "employees_import.csv"

FEB = eng.FEBRUARY
FEB_KEY = "2026-02"
FEB_DAYS = 28
DRAFT_ID = "PR-2026-02"
FY_KEYS = [
    "2025-04", "2025-05", "2025-06", "2025-07", "2025-08", "2025-09",
    "2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03",
]  # fmt: skip
LTA_BY_GRADE = {"G5": 3000, "G6": 5000, "G7": 5000}
RUN_KEYS: tuple[str, ...] = (
    "gross",
    "employee_pf",
    "employer_pf",
    "employee_esi",
    "employer_esi",
    "professional_tax",
    "tds",
    "reimbursements",
    "net_pay",
    "lop_days",
)
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]  # fmt: skip


# ─── Formatting ────────────────────────────────────────────────────────────────


def inr(amount: int | float) -> str:
    """₹ with Indian grouping: ₹1,26,374; a negative amount with a minus sign
    (U+2212), which reads as "minus" rather than as a dash."""
    n = round(amount)
    sign = "\u2212" if n < 0 else ""
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join([*groups, tail])
    return f"{sign}₹{s}"


def day(iso: str) -> str:
    """2026-02-16 → 16 Feb 2026."""
    y, m, d = iso[:10].split("-")
    return f"{int(d)} {MONTHS[int(m) - 1]} {y}"


def month_label(key: str) -> str:
    """2026-01 → January 2026."""
    y, m = key.split("-")
    return f"{MONTH_NAMES[int(m) - 1]} {y}"


def fold(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower().replace("-", " ")).strip()


# ─── The books ─────────────────────────────────────────────────────────────────


@dataclass
class Changed:
    """What a change did to the February draft, for the line the agent says."""

    employee_id: str
    before: dict[str, Any] | None
    after: dict[str, Any]
    lop_days: int = 0

    @property
    def net_delta(self) -> int:
        return int(self.after["net_pay"]) - int((self.before or {}).get("net_pay", 0))

    @property
    def tds_delta(self) -> int:
        return int(self.after["tds"]) - int((self.before or {}).get("tds", 0))


@dataclass
class Books:
    """One session's mutable copy of the company."""

    data: dict[str, Any] = field(default_factory=lambda: copy.deepcopy(COMPANY))
    next_employee: int = 1057
    next_ticket: int = 1208

    # ── reads ──

    @property
    def employees(self) -> list[dict[str, Any]]:
        return self.data["employees"]

    def employee(self, ref: str | None) -> dict[str, Any] | None:
        """An employee by id (BB-1030), full name, or a first or last name
        that names exactly one person."""
        if not ref:
            return None
        want = fold(ref)
        for e in self.employees:
            if e["id"].lower() == ref.strip().lower() or fold(e["name"]) == want:
                return e
        words = set(want.split())
        hits = [e for e in self.employees if words & set(fold(e["name"]).split())]
        if len(hits) == 1:
            return hits[0]
        full = [e for e in hits if words >= set(fold(e["name"]).split())]
        return full[0] if len(full) == 1 else None

    def matches(self, ref: str) -> list[dict[str, Any]]:
        words = set(fold(ref).split())
        return [e for e in self.employees if words & set(fold(e["name"]).split())]

    def name(self, employee_id: str) -> str:
        e = self.employee(employee_id)
        return e["name"] if e else employee_id

    def slips(self, employee_id: str) -> list[dict[str, Any]]:
        return self.data["payslips"].get(employee_id, [])

    def slip(self, employee_id: str, month: str) -> dict[str, Any] | None:
        return next((s for s in self.slips(employee_id) if s["month"] == month), None)

    def run(self, run_id: str = DRAFT_ID) -> dict[str, Any] | None:
        return next((r for r in self.data["payroll_runs"] if r["id"] == run_id), None)

    @property
    def draft(self) -> dict[str, Any]:
        run = self.run(DRAFT_ID)
        assert run is not None
        return run

    @property
    def requests(self) -> list[dict[str, Any]]:
        return self.data["leave"]["requests"]

    def request(self, ref: str) -> dict[str, Any] | None:
        """A leave request by id, or the one pending request of a named employee."""
        for r in self.requests:
            if r["id"].lower() == ref.strip().lower():
                return r
        e = self.employee(ref)
        if e is None:
            return None
        mine = [r for r in self.requests if r["employee_id"] == e["id"]]
        pending = [r for r in mine if r["status"] == "pending"]
        return (pending or mine or [None])[0]

    @property
    def claims(self) -> list[dict[str, Any]]:
        return self.data["reimbursements"]["claims"]

    def claim(self, ref: str) -> dict[str, Any] | None:
        for c in self.claims:
            if c["id"].lower() == ref.strip().lower():
                return c
        e = self.employee(ref)
        if e is None:
            return None
        open_ = [
            c
            for c in self.claims
            if c["employee_id"] == e["id"] and c["status"] in ("needs_fix", "pending")
        ]
        return open_[0] if open_ else None

    def declaration(self, employee_id: str) -> dict[str, Any] | None:
        return next((d for d in self.data["declarations"] if d["employee_id"] == employee_id), None)

    def verified(self, employee_id: str) -> eng.Declarations:
        d = self.declaration(employee_id)
        if d is None:
            return eng.Declarations()
        return eng.Declarations(**d["engine"]["verified"])

    def pay(self, e: dict[str, Any]) -> eng.EmployeePay:
        first = e.get("first_fy_month", "2025-04")
        return eng.EmployeePay(
            ctc=int(e["annual_ctc"]),
            city=e["location"],
            state=e["state"],
            gender=e["gender"],
            lta_monthly=int(e["lta_monthly"]),
            regime=e["tax_regime"],
            first_month_idx=FY_KEYS.index(first) if first in FY_KEYS else 0,
        )

    def ytd(self, e: dict[str, Any]) -> eng.Ytd:
        return eng.Ytd(**e["ytd_to_jan"])

    def feb_reimbursements(self, employee_id: str) -> int:
        return sum(
            int(c["amount"])
            for c in self.claims
            if c["employee_id"] == employee_id
            and c["payroll_month"] == FEB_KEY
            and c["status"] == "approved"
        )

    def comparison(self, employee_id: str) -> dict[str, Any]:
        e = self.employee(employee_id)
        assert e is not None
        return eng.regime_comparison(self.pay(e), self.ytd(e), FEB, self.verified(e["id"]))

    # ── the February draft ──

    def feb_slip(
        self,
        e: dict[str, Any],
        *,
        lop_days: int | None = None,
        regime: eng.Regime | None = None,
        reimbursements: int | None = None,
    ) -> dict[str, Any]:
        """The employee's February payslip recomputed by the engine, with the
        LOP, regime and reimbursements as they stand unless given."""
        now = self.slip(e["id"], FEB_KEY) or {}
        lop = int(now.get("lop_days", 0)) if lop_days is None else lop_days
        reimb = self.feb_reimbursements(e["id"]) if reimbursements is None else reimbursements
        slip = eng.payslip(
            self.pay(e),
            FEB,
            FEB_DAYS,
            lop,
            self.ytd(e),
            self.verified(e["id"]),
            reimbursements=reimb,
            regime=regime,
        ).to_dict()
        slip["month"] = FEB_KEY
        slip["regime"] = regime or e["tax_regime"]
        slip["joining_days_unpaid"] = int(now.get("joining_days_unpaid", 0))
        return slip

    def _replace_feb(self, employee_id: str, slip: dict[str, Any]) -> dict[str, Any] | None:
        slips = self.data["payslips"].setdefault(employee_id, [])
        before = next((s for s in slips if s["month"] == FEB_KEY), None)
        if before is not None:
            slips[slips.index(before)] = slip
        else:
            slips.append(slip)
        self.retotal()
        return before

    def retotal(self) -> None:
        """The draft run's totals, summed again from every February payslip."""
        run = self.draft
        totals: dict[str, int] = dict.fromkeys(RUN_KEYS, 0)
        count = 0
        for slips in self.data["payslips"].values():
            for s in slips:
                if s["month"] == FEB_KEY:
                    count += 1
                    for k in RUN_KEYS:
                        totals[k] += int(s[k])
        run.update(totals)
        run["employees"] = count
        run["employer_cost"] = totals["gross"] + totals["employer_pf"] + totals["employer_esi"]

    # ── leave ──

    def leave_impact(self, req: dict[str, Any]) -> tuple[int, int]:
        """(days covered by the balance, days that become LOP) if approved now."""
        days = int(req["days"])
        if req["type"] == "LOP":
            return 0, days
        e = self.employee(req["employee_id"])
        bal = float((e or {}).get("leave_balance", {}).get(req["type"], 0))
        covered = int(min(days, max(0.0, bal)))
        return covered, days - covered

    def preview_leave(self, req: dict[str, Any]) -> Changed | None:
        """What approving would do to the February draft, without doing it."""
        _, lop = self.leave_impact(req)
        if lop == 0 or not req["from"].startswith(FEB_KEY):
            return None
        e = self.employee(req["employee_id"])
        assert e is not None
        before = self.slip(e["id"], FEB_KEY)
        now_lop = int((before or {}).get("lop_days", 0))
        return Changed(e["id"], before, self.feb_slip(e, lop_days=now_lop + lop), lop)

    def decide_leave(
        self, request_id: str, decision: Literal["approve", "reject"]
    ) -> Changed | None:
        req = self.request(request_id)
        if req is None or req["status"] != "pending":
            return None
        if decision == "reject":
            req["status"] = "rejected"
            return None
        covered, lop = self.leave_impact(req)
        changed = self.preview_leave(req)
        req["status"] = "approved"
        e = self.employee(req["employee_id"])
        if e is not None and req["type"] != "LOP":
            bal = e["leave_balance"]
            bal[req["type"]] = float(bal.get(req["type"], 0)) - covered
        if lop:
            req["lop_days"] = lop
        if changed is not None:
            self._replace_feb(changed.employee_id, changed.after)
        return changed

    # ── claims ──

    def _claim_into_feb(self, c: dict[str, Any]) -> Changed | None:
        if c["payroll_month"] != FEB_KEY:
            return None
        e = self.employee(c["employee_id"])
        if e is None:
            return None
        before = self.slip(e["id"], FEB_KEY)
        after = self.feb_slip(e)
        self._replace_feb(e["id"], after)
        return Changed(e["id"], before, after)

    def fix_claim(self, claim_id: str, amount: int | None = None) -> Changed | None:
        c = self.claim(claim_id)
        if c is None:
            return None
        c["amount"] = int(c["bill_amount"] if amount is None else amount)
        c["status"] = "approved"
        c["note"] = None
        return self._claim_into_feb(c)

    def decide_claim(self, claim_id: str, decision: Literal["approve", "reject"]) -> Changed | None:
        c = self.claim(claim_id)
        if c is None:
            return None
        c["status"] = "approved" if decision == "approve" else "rejected"
        return self._claim_into_feb(c) if decision == "approve" else None

    # ── regime ──

    def preview_regime(self, employee_id: str, regime: eng.Regime) -> Changed:
        e = self.employee(employee_id)
        assert e is not None
        return Changed(e["id"], self.slip(e["id"], FEB_KEY), self.feb_slip(e, regime=regime))

    def switch_regime(self, employee_id: str, regime: eng.Regime) -> Changed | None:
        e = self.employee(employee_id)
        if e is None:
            return None
        changed = self.preview_regime(e["id"], regime)
        e["tax_regime"] = regime
        e["regime_chosen_on"] = self.data["today"]
        self._replace_feb(e["id"], changed.after)
        return changed

    # ── new joiner ──

    def new_employee(self, fields: dict[str, Any]) -> dict[str, Any]:
        """The record a new joiner gets, before it is saved."""
        city = str(fields["location"])
        state = next(
            (loc["state"] for loc in self.data["company"]["locations"] if loc["city"] == city),
            "",
        )
        grade = str(fields.get("grade") or "G2")
        lta = LTA_BY_GRADE.get(grade, 0)
        ctc = int(fields["annual_ctc"])
        joined = str(fields["joined"])
        return {
            "id": f"BB-{self.next_employee}",
            "name": str(fields["name"]),
            "gender": str(fields.get("gender") or "F"),
            "email": str(fields.get("email") or ""),
            "department": str(fields.get("department") or ""),
            "title": str(fields.get("title") or ""),
            "grade": grade,
            "location": city,
            "state": state,
            "metro_for_hra": eng.is_metro(city),
            "joined": joined,
            "manager_id": fields.get("manager_id"),
            "status": "active",
            "tax_regime": str(fields.get("tax_regime") or "new"),
            "regime_chosen_on": None,
            "annual_ctc": ctc,
            "lta_monthly": lta,
            "first_fy_month": joined[:7],
            "ytd_to_jan": {
                "gross": 0,
                "basic": 0,
                "hra": 0,
                "lta": 0,
                "employee_pf": 0,
                "professional_tax": 0,
                "tds": 0,
                "months": 0,
            },
            "leave_balance": {"EL": 0.0, "CL": 0.0, "SL": 0.0},
        }

    def joiner_slip(self, e: dict[str, Any]) -> dict[str, Any]:
        unpaid = int(e["joined"][8:10]) - 1 if e["joined"].startswith(FEB_KEY) else 0
        slip = eng.payslip(
            self.pay(e), FEB, FEB_DAYS, unpaid, eng.Ytd(), eng.Declarations()
        ).to_dict()
        slip.update(month=FEB_KEY, regime=e["tax_regime"], joining_days_unpaid=unpaid)
        return slip

    def add_employee(self, fields: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        e = self.new_employee(fields)
        if fields.get("id"):
            e["id"] = str(fields["id"])
        self.next_employee = max(self.next_employee, int(e["id"].split("-")[1])) + 1
        slip = self.joiner_slip(e)
        self.employees.append(e)
        self.data["payslips"][e["id"]] = [slip]
        self.retotal()
        return e, slip

    # ── tickets ──

    def add_ticket(self, subject: str, summary: str, ticket_id: str | None = None) -> str:
        tid = ticket_id or f"TK-{self.next_ticket}"
        self.next_ticket = max(self.next_ticket, int(tid.split("-")[1])) + 1
        self.data["tickets"].append(
            {
                "id": tid,
                "subject": subject,
                "status": "open",
                "opened": self.data["today"],
                "summary": summary,
            }
        )
        return tid


# ─── The onboarding import ─────────────────────────────────────────────────────

_PAN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
_REQUIRED = (
    "employee_id",
    "name",
    "email",
    "gender",
    "department",
    "designation",
    "location",
    "state",
    "date_of_joining",
    "annual_ctc",
    "tax_regime",
)


def import_summary(path: Path = IMPORT_CSV) -> dict[str, Any]:
    """The import file as the setup wizard's validation reads it: rows, valid,
    errors with reasons, and the split by location and regime."""
    rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
    ids = [r["employee_id"] for r in rows]
    errors: list[str] = []
    for i, r in enumerate(rows, start=2):
        missing = [k for k in _REQUIRED if not (r.get(k) or "").strip()]
        if missing:
            errors.append(f"row {i}: missing {', '.join(missing)}")
        if r.get("pan") and not _PAN.match(r["pan"]):
            errors.append(f"row {i}: PAN {r['pan']} is not in the PAN format")
        if ids.count(r["employee_id"]) > 1:
            errors.append(f"row {i}: duplicate employee id {r['employee_id']}")
        if r.get("manager_id") and r["manager_id"] not in ids:
            errors.append(f"row {i}: manager {r['manager_id']} is not in the file")
        if not (r.get("annual_ctc") or "").isdigit():
            errors.append(f"row {i}: annual CTC is not a number")
    by_location: dict[str, int] = {}
    regimes: dict[str, int] = {}
    for r in rows:
        by_location[r["location"]] = by_location.get(r["location"], 0) + 1
        regimes[r["tax_regime"]] = regimes.get(r["tax_regime"], 0) + 1
    bad_rows = {e.split(":")[0] for e in errors}
    return {
        "rows": len(rows),
        "valid": len(rows) - len(bad_rows),
        "errors": errors,
        "by_location": by_location,
        "regimes": regimes,
        "annual_ctc": sum(int(r["annual_ctc"]) for r in rows if r["annual_ctc"].isdigit()),
    }


def test_payroll(books: Books) -> dict[str, int]:
    """The February 2026 test payroll the wizard runs: every employee's Feb
    payslip recomputed by the engine from scratch, summed."""
    totals: dict[str, int] = dict.fromkeys(RUN_KEYS, 0)
    count = 0
    for e in books.employees:
        if e["joined"] > "2026-02-28":
            continue
        slip = books.feb_slip(e)
        count += 1
        for k in RUN_KEYS:
            totals[k] += int(slip[k])
    totals["employees"] = count
    totals["employer_cost"] = totals["gross"] + totals["employer_pf"] + totals["employer_esi"]
    return totals
