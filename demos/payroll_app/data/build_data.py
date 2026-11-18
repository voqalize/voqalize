"""Build the shared sample data for the two Tankora demos, deterministically.

    cd demos && uv run python payroll_app/data/build_data.py

Writes, from ``product.json`` (hand-authored) and the engine in
``payroll_app/backend/payroll_engine.py``:

- ``payroll_app/data/company.json``   Banyan & Bay Foods: employees, structures, YTD,
  payroll runs Apr 2025 - Feb 2026 (payslips for Nov, Dec, Jan and the Feb draft),
  leave, reimbursements, declarations and proofs, tickets.
- ``payroll_app/data/employees_import.csv``  the sample CSV the onboarding wizard imports.
- ``payroll_app/data/tax_fixtures.json``  engine cases the TypeScript twin must match.
- ``payroll_site/data/product.json``  a byte-for-byte copy of product.json.
- ``payroll_site/data/tax_example.json``  the worked old-vs-new example the marketing
  site's tax page shows, computed by the same engine.

Run it again after editing product.json or this file; the e2e tests fail if the
site's copies drift from what this script writes. Every person, company and number
is invented. The demo's clock is frozen at 16 Feb 2026, inside FY 2025-26.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import json
import random
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
APP = HERE.parent
SITE = APP.parent / "payroll_site"

_spec = importlib.util.spec_from_file_location(
    "payroll_engine", APP / "backend" / "payroll_engine.py"
)
assert _spec
assert _spec.loader
eng = importlib.util.module_from_spec(_spec)
sys.modules["payroll_engine"] = eng
_spec.loader.exec_module(eng)

TODAY = "2026-02-16"
MONTH_DAYS = [30, 31, 30, 31, 31, 30, 31, 30, 31, 31, 28, 31]  # Apr 2025 .. Mar 2026
MONTH_KEYS = [
    "2025-04", "2025-05", "2025-06", "2025-07", "2025-08", "2025-09",
    "2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03",
]  # fmt: skip
MONTH_LABELS = [
    "April 2025", "May 2025", "June 2025", "July 2025", "August 2025", "September 2025",
    "October 2025", "November 2025", "December 2025", "January 2026", "February 2026", "March 2026",
]  # fmt: skip
PAY_DATES = [
    "2025-04-30", "2025-05-30", "2025-06-30", "2025-07-31", "2025-08-29", "2025-09-30",
    "2025-10-31", "2025-11-28", "2025-12-31", "2026-01-30", "2026-02-27", "2026-03-31",
]  # fmt: skip
SLIP_MONTHS = [7, 8, 9, 10]  # Nov, Dec, Jan payslips kept in full, Feb is the draft
JAN, FEB = 9, 10
PROOFS_COUNT_FROM = JAN  # proofs verified before the January run count from January

LOCATIONS = {
    "Bengaluru": {"state": "Karnataka", "office": "Head office, HSR Layout, Bengaluru"},
    "Mumbai": {"state": "Maharashtra", "office": "Sales office, Andheri East, Mumbai"},
    "Pune": {"state": "Maharashtra", "office": "Warehouse, Chakan, Pune"},
    "New Delhi": {"state": "Delhi", "office": "Sales office, Okhla, New Delhi"},
    "Hyderabad": {"state": "Telangana", "office": "Support centre, Madhapur, Hyderabad"},
}


@dataclass
class Person:
    id: str
    name: str
    gender: str
    department: str
    title: str
    city: str
    ctc: int
    joined: str
    regime: str = "new"
    lta_monthly: int = 0
    manager: str | None = None
    grade: str = "G3"
    decl: dict[str, Any] = field(default_factory=dict[str, Any])
    story: str | None = None


# --------------------------------------------------------------------- roster
# (name, gender, department, title, city, annual CTC, joined, grade)
ROSTER: list[tuple[str, str, str, str, str, int, str, str]] = [
    (
        "Aditi Bhandari",
        "F",
        "Leadership",
        "Co-founder and CEO",
        "Bengaluru",
        4200000,
        "2019-06-01",
        "G7",
    ),
    (
        "Kunal Shetty",
        "M",
        "Leadership",
        "Co-founder and COO",
        "Bengaluru",
        4080000,
        "2019-06-01",
        "G7",
    ),
    (
        "Vandana Iyer",
        "F",
        "Finance and HR",
        "Head of Finance",
        "Bengaluru",
        3000000,
        "2020-02-10",
        "G6",
    ),
    ("Meghna Rao", "F", "Finance and HR", "HR Manager", "Bengaluru", 1500000, "2021-07-05", "G5"),
    (
        "Tarun Gowda",
        "M",
        "Finance and HR",
        "Accounts Executive",
        "Bengaluru",
        660000,
        "2022-11-14",
        "G3",
    ),
    (
        "Shalini Pillai",
        "F",
        "Finance and HR",
        "HR Executive",
        "Bengaluru",
        540000,
        "2023-08-01",
        "G2",
    ),
    (
        "Kavitha Menon",
        "F",
        "Engineering",
        "Engineering Manager",
        "Bengaluru",
        3600000,
        "2020-09-01",
        "G6",
    ),
    (
        "Arvind Natarajan",
        "M",
        "Engineering",
        "Senior Software Engineer",
        "Bengaluru",
        2400000,
        "2021-03-15",
        "G5",
    ),
    (
        "Neha Kulkarni",
        "F",
        "Engineering",
        "Senior Software Engineer",
        "Bengaluru",
        2280000,
        "2021-10-04",
        "G5",
    ),
    (
        "Siddharth Rao",
        "M",
        "Engineering",
        "Software Engineer",
        "Bengaluru",
        1440000,
        "2022-06-20",
        "G4",
    ),
    (
        "Fatima Sheikh",
        "F",
        "Engineering",
        "Software Engineer",
        "Bengaluru",
        1380000,
        "2023-01-09",
        "G4",
    ),
    (
        "Rahul Hegde",
        "M",
        "Engineering",
        "Software Engineer",
        "Bengaluru",
        1320000,
        "2023-07-17",
        "G4",
    ),
    ("Divya Prakash", "F", "Engineering", "QA Engineer", "Bengaluru", 960000, "2023-04-03", "G3"),
    (
        "Manoj Kumar",
        "M",
        "Engineering",
        "DevOps Engineer",
        "Bengaluru",
        1620000,
        "2022-02-01",
        "G4",
    ),
    ("Sneha Reddy", "F", "Engineering", "Data Analyst", "Bengaluru", 1080000, "2024-01-15", "G3"),
    (
        "Abhishek Jain",
        "M",
        "Engineering",
        "Software Engineer",
        "Bengaluru",
        1260000,
        "2025-09-01",
        "G4",
    ),
    (
        "Pooja Nair",
        "F",
        "Engineering",
        "Associate Software Engineer",
        "Bengaluru",
        840000,
        "2025-11-03",
        "G3",
    ),
    (
        "Ishaan Malhotra",
        "M",
        "Product and Design",
        "Product Manager",
        "Bengaluru",
        2160000,
        "2022-05-02",
        "G5",
    ),
    (
        "Ritika Sen",
        "F",
        "Product and Design",
        "Product Designer",
        "Bengaluru",
        1500000,
        "2022-09-12",
        "G4",
    ),
    ("Varun Bhat", "M", "Product and Design", "UX Writer", "Bengaluru", 900000, "2024-03-18", "G3"),
    (
        "Lakshmi Venkatesh",
        "F",
        "Product and Design",
        "Design Lead",
        "Bengaluru",
        2040000,
        "2021-01-11",
        "G5",
    ),
    (
        "Nikita Saxena",
        "F",
        "Marketing",
        "Head of Marketing",
        "Bengaluru",
        2520000,
        "2021-04-19",
        "G6",
    ),
    (
        "Aman Chawla",
        "M",
        "Marketing",
        "Performance Marketer",
        "Bengaluru",
        1200000,
        "2022-12-05",
        "G4",
    ),
    ("Sanjana Das", "F", "Marketing", "Brand Manager", "Bengaluru", 1320000, "2023-02-13", "G4"),
    ("Yusuf Ali", "M", "Marketing", "Content Lead", "Bengaluru", 1080000, "2023-09-25", "G3"),
    (
        "Tanvi Joshi",
        "F",
        "Marketing",
        "Social Media Executive",
        "Bengaluru",
        600000,
        "2024-06-10",
        "G2",
    ),
    (
        "Harish Murthy",
        "M",
        "Leadership",
        "Head of Supply Chain",
        "Bengaluru",
        2880000,
        "2020-03-02",
        "G6",
    ),
    (
        "Deepa Raghavan",
        "F",
        "Finance and HR",
        "Payroll Specialist",
        "Bengaluru",
        780000,
        "2025-10-06",
        "G3",
    ),
    ("Gaurav Mehta", "M", "Sales", "Head of Sales", "Mumbai", 3240000, "2020-08-17", "G6"),
    ("Ravi Kumar", "M", "Sales", "Senior Sales Executive", "Mumbai", 1680000, "2021-11-22", "G4"),
    ("Swati Patil", "F", "Sales", "Key Account Manager", "Mumbai", 1920000, "2021-05-10", "G5"),
    ("Imran Qureshi", "M", "Sales", "Sales Executive", "Mumbai", 900000, "2023-03-06", "G3"),
    ("Anita D'Souza", "F", "Sales", "Sales Executive", "Mumbai", 840000, "2023-10-16", "G3"),
    ("Rohit Sawant", "M", "Sales", "Sales Executive", "Mumbai", 780000, "2024-07-01", "G2"),
    ("Mehul Shah", "M", "Sales", "Key Account Manager", "Mumbai", 1800000, "2022-01-24", "G5"),
    ("Priyanka Kadam", "F", "Sales", "Sales Coordinator", "Mumbai", 540000, "2024-09-09", "G2"),
    ("Farhan Kapadia", "M", "Sales", "Sales Executive", "Mumbai", 720000, "2025-08-18", "G2"),
    ("Kiran Jadhav", "M", "Sales", "Sales Executive", "Mumbai", 690000, "2024-11-11", "G2"),
    ("Sachin Pawar", "M", "Operations", "Warehouse Manager", "Pune", 1080000, "2021-06-14", "G4"),
    (
        "Sunita Gaikwad",
        "F",
        "Operations",
        "Inventory Controller",
        "Pune",
        480000,
        "2022-04-04",
        "G2",
    ),
    ("Mahesh Shinde", "M", "Operations", "Warehouse Associate", "Pune", 252000, "2023-01-16", "G1"),
    ("Vijay More", "M", "Operations", "Warehouse Associate", "Pune", 252000, "2023-05-22", "G1"),
    ("Rekha Salunkhe", "F", "Operations", "Packing Associate", "Pune", 240000, "2023-08-28", "G1"),
    ("Santosh Kale", "M", "Operations", "Forklift Operator", "Pune", 276000, "2022-10-03", "G1"),
    (
        "Ganesh Bhosale",
        "M",
        "Operations",
        "Warehouse Associate",
        "Pune",
        252000,
        "2024-02-12",
        "G1",
    ),
    ("Asha Chavan", "F", "Operations", "Packing Associate", "Pune", 240000, "2024-08-05", "G1"),
    ("Nilesh Wagh", "M", "Operations", "Dispatch Executive", "Pune", 330000, "2025-07-07", "G1"),
    (
        "Arjita Bose",
        "F",
        "Sales",
        "Regional Sales Manager, North",
        "New Delhi",
        2160000,
        "2021-08-02",
        "G5",
    ),
    ("Vikram Singh", "M", "Sales", "Sales Executive", "New Delhi", 900000, "2022-08-29", "G3"),
    ("Simran Kaur", "F", "Sales", "Sales Executive", "New Delhi", 840000, "2023-06-12", "G3"),
    ("Rajat Khanna", "M", "Sales", "Key Account Manager", "New Delhi", 1560000, "2022-03-21", "G4"),
    ("Neeraj Tyagi", "M", "Sales", "Sales Executive", "New Delhi", 720000, "2025-12-01", "G2"),
    (
        "Sravani Reddy",
        "F",
        "Customer Support",
        "Support Lead",
        "Hyderabad",
        960000,
        "2022-07-11",
        "G3",
    ),
    (
        "Mohammed Irfan",
        "M",
        "Customer Support",
        "Support Associate",
        "Hyderabad",
        420000,
        "2023-11-06",
        "G2",
    ),
    (
        "Keerthi Rao",
        "F",
        "Customer Support",
        "Support Associate",
        "Hyderabad",
        396000,
        "2024-05-20",
        "G2",
    ),
    (
        "Anil Goud",
        "M",
        "Customer Support",
        "Support Associate",
        "Hyderabad",
        360000,
        "2024-12-02",
        "G1",
    ),
]

MANAGERS = {
    "Leadership": "Aditi Bhandari",
    "Finance and HR": "Vandana Iyer",
    "Engineering": "Kavitha Menon",
    "Product and Design": "Ishaan Malhotra",
    "Marketing": "Nikita Saxena",
    "Sales": "Gaurav Mehta",
    "Operations": "Sachin Pawar",
    "Customer Support": "Sravani Reddy",
}
MANAGER_OVERRIDES = {
    "Aditi Bhandari": None,
    "Kunal Shetty": "Aditi Bhandari",
    "Vandana Iyer": "Kunal Shetty",
    "Kavitha Menon": "Kunal Shetty",
    "Ishaan Malhotra": "Kunal Shetty",
    "Nikita Saxena": "Aditi Bhandari",
    "Gaurav Mehta": "Aditi Bhandari",
    "Harish Murthy": "Kunal Shetty",
    "Sachin Pawar": "Harish Murthy",
    "Sravani Reddy": "Kunal Shetty",
    "Arjita Bose": "Gaurav Mehta",
    "Vikram Singh": "Arjita Bose",
    "Simran Kaur": "Arjita Bose",
    "Rajat Khanna": "Arjita Bose",
    "Neeraj Tyagi": "Arjita Bose",
}

# Old-regime employees and their declarations (April 2025) and verified proofs (Jan 2026).
# Each item: section, label, declared, proof (verified amount), proof status.
OLD_REGIME: dict[str, dict[str, Any]] = {
    "Ravi Kumar": {
        "rent_monthly": 35000,
        "landlord": "Landlord PAN on file",
        "items": [
            ("80C", "ELSS mutual fund", 60000, 0, "not_submitted"),
            ("80C", "Public Provident Fund", 40000, 40000, "verified"),
            ("80C", "Life insurance premium", 28400, 28400, "verified"),
            ("80D", "Health insurance, self and family", 25000, 25000, "verified"),
            (
                "80D_parents",
                "Health insurance, parents (senior citizens)",
                42000,
                42000,
                "verified",
            ),
            ("80CCD1B", "NPS, own contribution", 50000, 0, "not_submitted"),
        ],
        "rent_proof": "verified",
        "parents_senior": True,
        "lta_monthly": 3000,
    },
    "Gaurav Mehta": {
        "rent_monthly": 0,
        "items": [
            ("80C", "Home loan principal", 150000, 150000, "verified"),
            ("24b", "Home loan interest", 200000, 200000, "verified"),
            ("80D", "Health insurance, self and family", 25000, 25000, "verified"),
            ("80CCD1B", "NPS, own contribution", 50000, 50000, "verified"),
        ],
        "parents_senior": False,
        "lta_monthly": 5000,
        "lta_claim": 48000,
    },
    "Vandana Iyer": {
        "rent_monthly": 0,
        "items": [
            ("80C", "Public Provident Fund", 150000, 150000, "verified"),
            ("24b", "Home loan interest", 180000, 180000, "verified"),
            ("80D", "Health insurance, self and family", 22000, 22000, "verified"),
            (
                "80D_parents",
                "Health insurance, parents (senior citizens)",
                50000,
                50000,
                "verified",
            ),
            ("80CCD1B", "NPS, own contribution", 50000, 50000, "verified"),
        ],
        "parents_senior": True,
        "lta_monthly": 5000,
    },
    "Harish Murthy": {
        "rent_monthly": 0,
        "items": [
            ("80C", "Children's tuition fees", 110000, 110000, "verified"),
            ("24b", "Home loan interest", 200000, 200000, "verified"),
            ("80D", "Health insurance, self and family", 25000, 25000, "verified"),
            ("80CCD1B", "NPS, own contribution", 50000, 50000, "verified"),
        ],
        "parents_senior": False,
        "lta_monthly": 5000,
    },
    "Swati Patil": {
        "rent_monthly": 0,
        "items": [
            ("80C", "Home loan principal", 120000, 120000, "verified"),
            ("24b", "Home loan interest", 200000, 200000, "verified"),
            ("80D", "Health insurance, self and family", 18000, 18000, "verified"),
            ("80CCD1B", "NPS, own contribution", 50000, 25000, "partly_verified"),
        ],
        "parents_senior": False,
        "lta_monthly": 3000,
    },
}
# On the new regime, but with declarations on file: the regime comparison favours the old one.
NEW_WITH_DECLARATIONS: dict[str, dict[str, Any]] = {
    "Kavitha Menon": {
        "rent_monthly": 60000,
        "landlord": "Landlord PAN on file",
        "items": [
            ("80C", "Public Provident Fund", 100000, 100000, "verified"),
            ("80C", "Children's tuition fees", 28400, 28400, "verified"),
            ("80D", "Health insurance, self and family", 25000, 25000, "verified"),
            (
                "80D_parents",
                "Health insurance, parents (senior citizens)",
                50000,
                50000,
                "verified",
            ),
            ("80CCD1B", "NPS, own contribution", 50000, 50000, "verified"),
        ],
        "rent_proof": "verified",
        "parents_senior": True,
        "lta_monthly": 5000,
        "lta_claim": 40000,
    },
}
LTA_BY_GRADE = {"G5": 3000, "G6": 5000, "G7": 5000}


def to_decl(spec: dict[str, Any], use: str) -> Any:
    """use = "declared" or "verified"."""
    idx = 2 if use == "declared" else 3
    d = eng.Declarations(
        rent_monthly=spec.get("rent_monthly", 0)
        if (use == "declared" or spec.get("rent_proof", "verified") == "verified")
        else 0,
        parents_senior=bool(spec.get("parents_senior", False)),
        lta_claim=int(spec.get("lta_claim", 0)),
    )
    for item in spec["items"]:
        sec, amt = item[0], int(item[idx])
        if sec == "80C":
            d.sec80c_other += amt
        elif sec == "80D":
            d.sec80d_self += amt
        elif sec == "80D_parents":
            d.sec80d_parents += amt
        elif sec == "80CCD1B":
            d.sec80ccd1b += amt
        elif sec == "24b":
            d.home_loan_interest += amt
    return d


def first_month_idx(joined: str) -> int:
    if joined < "2025-04-01":
        return 0
    return MONTH_KEYS.index(joined[:7])


def masked_pan(rng: random.Random, name: str) -> str:
    letters = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    surname = name.split()[-1][0].upper()
    tail = rng.choice(letters)
    return (
        f"{''.join(rng.choice(letters) for _ in range(3))}P{surname}{rng.randint(1000, 9999)}{tail}"
    )


def build() -> dict[str, Any]:
    rng = random.Random(2026)
    product = eng.load_product()
    people: list[Person] = []
    for i, (name, g, dept, title, city, ctc, joined, grade) in enumerate(ROSTER):
        assert ctc % 12 == 0, name
        pid = f"BB-{1001 + i}"
        p = Person(
            id=pid,
            name=name,
            gender=g,
            department=dept,
            title=title,
            city=city,
            ctc=ctc,
            joined=joined,
            grade=grade,
        )
        p.lta_monthly = LTA_BY_GRADE.get(grade, 0)
        if name in OLD_REGIME:
            p.regime = "old"
            p.lta_monthly = OLD_REGIME[name]["lta_monthly"]
        if name in NEW_WITH_DECLARATIONS:
            p.lta_monthly = NEW_WITH_DECLARATIONS[name]["lta_monthly"]
        people.append(p)
    by_name = {p.name: p for p in people}
    for p in people:
        mgr = MANAGER_OVERRIDES.get(p.name, MANAGERS[p.department])
        p.manager = by_name[mgr].id if mgr and mgr != p.name else None

    # ------------------------------------------------------------ leave
    leave_policy = {
        "year": "Calendar year 2026 (January to December)",
        "types": [
            {"id": "EL", "name": "Earned leave", "per_year": 18, "accrual": "1.5 days a month", "carry_forward_max": 30, "encashable": True},
            {"id": "CL", "name": "Casual leave", "per_year": 8, "accrual": "Credited on 1 January", "carry_forward_max": 0, "encashable": False},
            {"id": "SL", "name": "Sick leave", "per_year": 8, "accrual": "Credited on 1 January", "carry_forward_max": 0, "encashable": False},
            {"id": "LOP", "name": "Leave without pay", "per_year": None, "accrual": "When no balance is left; deducted as loss-of-pay", "carry_forward_max": 0, "encashable": False},
        ],
        "approval": "Reporting manager approves; HR can approve on their behalf.",
        "lop_rule": "Loss-of-pay days reduce every earning in proportion: earning x (days in month - LOP days) / days in month.",
        "attendance_cutoff": "Leave approved by the 25th counts in that month's payroll; later approvals carry to the next month.",
        "sandwich_rule": False,
    }  # fmt: skip
    holidays = [
        {"date": "2026-01-01", "name": "New Year's Day", "locations": ["all"]},
        {"date": "2026-01-14", "name": "Makara Sankranti", "locations": ["Bengaluru", "Hyderabad"]},
        {"date": "2026-01-26", "name": "Republic Day", "locations": ["all"]},
        {"date": "2026-03-04", "name": "Holi", "locations": ["Mumbai", "Pune", "New Delhi"]},
        {"date": "2026-05-01", "name": "Labour Day / Maharashtra Day", "locations": ["all"]},
        {"date": "2026-08-15", "name": "Independence Day", "locations": ["all"]},
        {"date": "2026-10-02", "name": "Gandhi Jayanti", "locations": ["all"]},
        {"date": "2026-12-25", "name": "Christmas", "locations": ["all"]},
    ]
    # Calendar-year balances on 16 Feb 2026: EL accrued Jan+Feb (3) plus carry-forward.
    leave_requests: list[dict[str, Any]] = []
    balances: dict[str, dict[str, float]] = {}
    lop_by_month: dict[tuple[str, int], int] = {}
    for p in people:
        carry = float(rng.choice([2, 4, 5.5, 6, 8, 9.5, 12]))
        balances[p.id] = {"EL": carry + 3.0, "CL": 8.0, "SL": 8.0}
    # Approved leave already taken in Jan-Feb 2026, and the LOP stories.
    taken = [
        ("Ravi Kumar", "LOP", "2026-01-12", "2026-01-13", 2, "approved", "Family function in Lucknow. No earned or casual leave left after the December trip.", "2026-01-05"),
        ("Ravi Kumar", "EL", "2025-12-22", "2025-12-31", 8, "approved", "Year-end trip.", "2025-12-01"),
        ("Mahesh Shinde", "LOP", "2025-12-08", "2025-12-08", 1, "approved", "Personal work.", "2025-12-06"),
        ("Neha Kulkarni", "SL", "2026-01-19", "2026-01-20", 2, "approved", "Fever.", "2026-01-19"),
        ("Siddharth Rao", "CL", "2026-02-02", "2026-02-02", 1, "approved", "Bank work.", "2026-01-28"),
        ("Sunita Gaikwad", "EL", "2026-02-09", "2026-02-11", 3, "approved", "Village visit.", "2026-01-30"),
        ("Arjita Bose", "CL", "2026-01-30", "2026-01-30", 1, "approved", "Personal.", "2026-01-27"),
    ]  # fmt: skip
    pending = [
        ("Fatima Sheikh", "EL", "2026-02-23", "2026-02-27", 5, "pending", "Sister's wedding in Lucknow.", "2026-02-10"),
        ("Rekha Salunkhe", "CL", "2026-02-19", "2026-02-20", 2, "pending", "Child's school admission.", "2026-02-13"),
        ("Imran Qureshi", "SL", "2026-02-16", "2026-02-17", 2, "pending", "Viral fever, doctor's note attached.", "2026-02-16"),
        ("Aman Chawla", "EL", "2026-03-09", "2026-03-13", 5, "pending", "Trip to Coorg.", "2026-02-12"),
        ("Asha Chavan", "CL", "2026-02-24", "2026-02-25", 2, "pending", "Family function.", "2026-02-14"),
    ]  # fmt: skip
    for p in people:
        if p.name == "Ravi Kumar":
            balances[p.id] = {"EL": 0.0, "CL": 0.0, "SL": 6.0}
        if p.name == "Asha Chavan":
            balances[p.id]["CL"] = 1.0  # one day short: approving 2 days makes 1 day LOP
        if p.name == "Rekha Salunkhe":
            balances[p.id]["CL"] = 3.0
    for n, (name, typ, start, end, days, status, reason, applied) in enumerate(taken + pending):
        p = by_name[name]
        req = {
            "id": f"LV-{2401 + n}",
            "employee_id": p.id,
            "type": typ,
            "from": start,
            "to": end,
            "days": days,
            "status": status,
            "reason": reason,
            "applied_on": applied,
            "approver_id": p.manager,
        }
        leave_requests.append(req)
        if status == "approved" and typ in ("CL", "SL", "EL") and start >= "2026-01-01":
            balances[p.id][typ] -= days
        if status == "approved" and typ == "LOP":
            lop_by_month[(p.id, MONTH_KEYS.index(start[:7]))] = days

    # ------------------------------------------------------- reimbursements
    reimb_policy = [
        {"category": "Phone and internet", "monthly_limit": 1500, "grades": "All", "taxable": False, "bill_required": True},
        {"category": "Business travel", "monthly_limit": None, "grades": "All", "taxable": False, "bill_required": True},
        {"category": "Client meals", "monthly_limit": 3000, "grades": "Sales, G4 and above", "taxable": False, "bill_required": True},
        {"category": "Fuel for field visits", "monthly_limit": 2500, "grades": "Sales", "taxable": False, "bill_required": True},
        {"category": "Learning and books", "monthly_limit": 2000, "grades": "All", "taxable": False, "bill_required": True},
    ]  # fmt: skip
    claims_raw = [
        # Paid with the January run
        ("Ravi Kumar", "Fuel for field visits", 2340, 2340, "2026-01-08", "paid", "Fuel, client visits in Thane and Navi Mumbai", JAN, None),
        ("Ravi Kumar", "Client meals", 2860, 2860, "2026-01-14", "paid", "Lunch with buyer, Hypercity chain", JAN, None),
        ("Swati Patil", "Business travel", 6420, 6420, "2026-01-10", "paid", "Train and cab, Nashik distributor visit", JAN, None),
        ("Vikram Singh", "Fuel for field visits", 2100, 2100, "2026-01-12", "paid", "Fuel, Noida and Gurugram outlets", JAN, None),
        ("Arvind Natarajan", "Learning and books", 1899, 1899, "2026-01-06", "paid", "Book: database internals", JAN, None),
        ("Sravani Reddy", "Phone and internet", 1178, 1178, "2026-01-05", "paid", "Broadband, December", JAN, None),
        # For the February run
        ("Ravi Kumar", "Fuel for field visits", 2180, 2180, "2026-02-06", "approved", "Fuel, Bhiwandi warehouse visits", FEB, None),
        ("Imran Qureshi", "Client meals", 4850, 4580, "2026-02-09", "needs_fix", "Dinner with distributor, Dadar", FEB, "Amount claimed (₹4,850) does not match the bill (₹4,580). Looks like two digits swapped."),
        ("Rajat Khanna", "Business travel", 11240, 11240, "2026-02-04", "pending", "Flight Delhi to Jaipur and back, retailer meet", FEB, None),
        ("Simran Kaur", "Fuel for field visits", 2950, 2950, "2026-02-10", "pending", "Fuel, Faridabad route", FEB, "Over the ₹2,500 monthly limit for fuel by ₹450."),
        ("Ritika Sen", "Learning and books", 1650, 1650, "2026-02-03", "pending", "Online course: motion design basics", FEB, None),
        ("Mohammed Irfan", "Phone and internet", 799, 799, "2026-02-05", "approved", "Mobile plan, January", FEB, None),
        ("Mehul Shah", "Client meals", 2740, 2740, "2026-02-11", "pending", "Lunch with modern-trade buyer, BKC", FEB, None),
        ("Fatima Sheikh", "Phone and internet", 1499, 1499, "2026-02-02", "rejected", "Broadband, January", FEB, "Duplicate of a claim paid in January."),
    ]  # fmt: skip
    claims: list[dict[str, Any]] = []
    for n, (name, cat, amt, bill, date, status, desc, month, note) in enumerate(claims_raw):
        claims.append(
            {
                "id": f"RB-{3101 + n}",
                "employee_id": by_name[name].id,
                "category": cat,
                "amount": amt,
                "bill_amount": bill,
                "date": date,
                "status": status,
                "description": desc,
                "payroll_month": MONTH_KEYS[month],
                "note": note,
                "bill_file": f"bill-{3101 + n}.pdf",
            }
        )

    def reimb_for(pid: str, month: int, statuses: tuple[str, ...]) -> int:
        return sum(
            c["amount"]
            for c in claims
            if c["employee_id"] == pid
            and c["payroll_month"] == MONTH_KEYS[month]
            and c["status"] in statuses
        )

    # ------------------------------------------------------- simulate payroll
    employees: list[dict[str, Any]] = []
    slips: dict[str, list[dict[str, Any]]] = {}
    run_totals: list[dict[str, Any]] = [
        dict.fromkeys(("employees", "gross", "employee_pf", "employer_pf", "employee_esi", "employer_esi", "professional_tax", "tds", "reimbursements", "net_pay", "lop_days"), 0)
        for _ in range(12)
    ]  # fmt: skip
    declarations: list[dict[str, Any]] = []
    comparisons: dict[str, Any] = {}
    for p in people:
        st = eng.structure(p.ctc, p.city, p.lta_monthly)
        state = LOCATIONS[p.city]["state"]
        pay = eng.EmployeePay(
            ctc=p.ctc,
            city=p.city,
            state=state,
            gender=p.gender,
            lta_monthly=p.lta_monthly,
            regime=p.regime,  # type: ignore[arg-type]
            first_month_idx=first_month_idx(p.joined),
        )
        spec = OLD_REGIME.get(p.name) or NEW_WITH_DECLARATIONS.get(p.name)
        declared = to_decl(spec, "declared") if spec else eng.Declarations()
        verified = to_decl(spec, "verified") if spec else eng.Declarations()
        ytd = eng.Ytd()
        ytd_to_jan = eng.Ytd()
        p_slips: list[dict[str, Any]] = []
        for m in range(FEB + 1):
            if m < pay.first_month_idx:
                continue
            days = MONTH_DAYS[m]
            lop = lop_by_month.get((p.id, m), 0)
            if m == pay.first_month_idx and p.joined >= "2025-04-01":
                lop += int(p.joined[8:10]) - 1  # not yet joined counts as unpaid days
            decl = verified if m >= PROOFS_COUNT_FROM else declared
            statuses = ("paid",) if m < FEB else ("approved",)
            reimb = reimb_for(p.id, m, statuses)
            slip = eng.payslip(pay, m, days, lop, ytd, decl, reimbursements=reimb)
            t = run_totals[m]
            t["employees"] += 1
            for k in (
                "gross",
                "employee_pf",
                "employer_pf",
                "employee_esi",
                "employer_esi",
                "professional_tax",
                "tds",
                "reimbursements",
                "net_pay",
            ):
                t[k] += getattr(slip, k)
            t["lop_days"] += slip.lop_days
            if m in SLIP_MONTHS:
                d = slip.to_dict()
                d["month"] = MONTH_KEYS[m]
                d["regime"] = p.regime
                d["joining_days_unpaid"] = (
                    int(p.joined[8:10]) - 1
                    if m == pay.first_month_idx and p.joined >= "2025-04-01"
                    else 0
                )
                p_slips.append(d)
            if m < FEB:
                ytd = ytd.plus(slip)
                ytd_to_jan = ytd
        slips[p.id] = p_slips
        # Regime comparison on the same projected year, from verified amounts.
        comp = eng.regime_comparison(pay, ytd_to_jan, FEB, verified if spec else eng.Declarations())
        comparisons[p.id] = {
            "new_total": comp["new"]["total_tax"],
            "old_total": comp["old"]["total_tax"],
            "better": comp["better"],
            "saving": comp["saving"],
        }
        assert comp["new"]["taxable_income"] < 5_000_000
        assert comp["old"]["taxable_income"] < 5_000_000
        employees.append(
            {
                "id": p.id,
                "name": p.name,
                "gender": p.gender,
                "email": f"{p.name.lower().replace(' ', '.').replace(chr(39), '')}@banyanbay.example",
                "department": p.department,
                "title": p.title,
                "grade": p.grade,
                "location": p.city,
                "state": state,
                "metro_for_hra": eng.is_metro(p.city),
                "joined": p.joined,
                "manager_id": p.manager,
                "status": "active",
                "pan": masked_pan(rng, p.name),
                "uan": f"10{rng.randint(10**9, 10**10 - 1)}",
                "bank": f"{rng.choice(['HDFC Bank', 'ICICI Bank', 'State Bank of India', 'Axis Bank', 'Kotak Mahindra Bank'])} ····{rng.randint(1000, 9999)}",
                "tax_regime": p.regime,
                "regime_chosen_on": "2025-04-11" if p.regime == "old" else None,
                "annual_ctc": p.ctc,
                "structure": asdict(st),
                "lta_monthly": p.lta_monthly,
                "pf": True,
                "esi": st.esi_applicable,
                "first_fy_month": MONTH_KEYS[pay.first_month_idx],
                "ytd_to_jan": asdict(ytd_to_jan),
                "regime_comparison": comparisons[p.id],
                "leave_balance": balances[p.id],
            }
        )
        if spec:
            items: list[dict[str, Any]] = []
            for sec, label, dec, ver, status in spec["items"]:
                items.append(
                    {
                        "section": sec,
                        "label": label,
                        "declared": dec,
                        "verified": ver,
                        "proof_status": status,
                    }
                )
            if spec.get("rent_monthly"):
                items.insert(
                    0,
                    {
                        "section": "HRA",
                        "label": f"House rent, ₹{spec['rent_monthly']:,} a month ({p.city})",
                        "declared": spec["rent_monthly"] * 12,
                        "verified": spec["rent_monthly"] * 12
                        if spec.get("rent_proof") == "verified"
                        else 0,
                        "proof_status": spec.get("rent_proof", "verified"),
                        "rent_monthly": spec["rent_monthly"],
                        "landlord_pan": spec.get("landlord", ""),
                    },
                )
            if spec.get("lta_claim"):
                items.append(
                    {
                        "section": "LTA",
                        "label": "Leave travel, family trip within India",
                        "declared": spec["lta_claim"],
                        "verified": spec["lta_claim"],
                        "proof_status": "verified",
                    }
                )
            declarations.append(
                {
                    "employee_id": p.id,
                    "regime": p.regime,
                    "declared_on": "2025-04-11",
                    "proofs_submitted_on": "2026-01-16",
                    "proofs_verified_on": "2026-01-21",
                    "items": items,
                    "declared_80c_other": declared.sec80c_other,
                    "verified_80c_other": verified.sec80c_other,
                    # The engine's own inputs (payroll_engine.Declarations), so the
                    # brain and engine.ts read the same numbers instead of
                    # re-deriving them from the item labels.
                    "engine": {"declared": asdict(declared), "verified": asdict(verified)},
                }
            )

    # ---------------------------------------------------------------- runs
    runs: list[dict[str, Any]] = []
    for m in range(FEB + 1):
        t = run_totals[m]
        runs.append(
            {
                "id": f"PR-{MONTH_KEYS[m]}",
                "month": MONTH_KEYS[m],
                "label": MONTH_LABELS[m],
                "status": "draft" if m == FEB else "paid",
                "pay_date": PAY_DATES[m],
                "days": MONTH_DAYS[m],
                "approved_by": None if m == FEB else "Vandana Iyer",
                "employer_cost": t["gross"] + t["employer_pf"] + t["employer_esi"],
                **t,
            }
        )
    by_id = {e["id"]: e for e in employees}
    ravi = by_name["Ravi Kumar"].id
    rs = {s["month"]: s for s in slips[ravi]}
    dec_net, jan_net = rs["2025-12"]["net_pay"], rs["2026-01"]["net_pay"]
    assert rs["2026-01"]["lop_days"] == 2
    assert rs["2026-01"]["tds"] > rs["2025-12"]["tds"], "Ravi's TDS should rise in January"
    assert by_id[ravi]["regime_comparison"]["better"] == "new", (
        "verified proofs should make new cheaper for Ravi"
    )
    assert by_id[by_name["Kavitha Menon"].id]["regime_comparison"]["better"] == "old"
    stories = {
        "ravi_net_drop": {
            "employee_id": ravi,
            "dec_net": dec_net,
            "jan_net": jan_net,
            "drop": dec_net - jan_net,
            "lop_days": 2,
            "lop_amount": rs["2025-12"]["gross"] - rs["2026-01"]["gross"],
            "tds_dec": rs["2025-12"]["tds"],
            "tds_jan": rs["2026-01"]["tds"],
            "reimb_dec": rs["2025-12"]["reimbursements"],
            "reimb_jan": rs["2026-01"]["reimbursements"],
            "why_tds": "Proofs verified on 21 Jan 2026: ELSS (₹60,000) and NPS (₹50,000) were declared but no proof was submitted, so 80C and 80CCD(1B) now count only what was verified, and the year's tax is spread over the three months left.",
        },
        "kavitha_old_better": {
            "employee_id": by_name["Kavitha Menon"].id,
            **comparisons[by_name["Kavitha Menon"].id],
        },
    }

    company = {
        "_about": "Banyan & Bay Foods Pvt. Ltd., a fictional Tankora customer. Generated by build_data.py; do not edit by hand.",
        "today": TODAY,
        "fy": product["tax"]["fy"],
        "company": {
            "name": "Banyan & Bay Foods",
            "legal_name": "Banyan & Bay Foods Pvt. Ltd.",
            "industry": "D2C packaged foods: millet snacks, cold-pressed oils and pantry staples",
            "founded": 2019,
            "registered_office": "HSR Layout, Bengaluru, Karnataka 560102",
            "pan": "AAKCB7713Q",
            "tan": "BLRB09412E",
            "pf_code": "KN/BNG/0098765",
            "esi_code": "53000123456000999",
            "pt_registrations": {"Karnataka": "PTKA-0451123", "Maharashtra": "PTMH-27561190"},
            "plan": "growth",
            "plan_note": "Growth plan, 56 employees x ₹119 = ₹6,664 a month before GST, billed monthly.",
            "admin": {
                "employee_id": by_name["Meghna Rao"].id,
                "name": "Meghna Rao",
                "role": "HR admin",
            },
            "payroll_approver": {"employee_id": by_name["Vandana Iyer"].id, "name": "Vandana Iyer"},
            "pay_cycle": "Calendar month; salary paid on the last working day",
            "locations": [{"city": c, **v} for c, v in LOCATIONS.items()],
            "departments": sorted({p.department for p in people}),
            "regime_change_policy": "Banyan & Bay lets an employee change the regime used for TDS once a year, until the proof window closes on 28 Feb 2026. TDS for the months left is then recalculated. The final choice is made in the income-tax return.",
            "windows": {
                "declaration": {"opens": "2025-04-01", "closes": "2025-04-30"},
                "proofs": {
                    "opens": "2026-01-05",
                    "first_verification": "2026-01-21",
                    "closes": "2026-02-28",
                },
            },
        },
        "structure_rule": "Basic 40% of monthly CTC; HRA 50% of basic in Mumbai or New Delhi, 40% elsewhere; LTA by grade (₹3,000 G5, ₹5,000 G6 and up); employer PF 12% of basic up to ₹15,000; employer ESI 3.25% when gross is up to ₹21,000; special allowance is the balance.",
        "employees": employees,
        "payslips": slips,
        "payroll_runs": runs,
        "leave": {"policy": leave_policy, "holidays": holidays, "requests": leave_requests},
        "reimbursements": {"policy": reimb_policy, "claims": claims},
        "declarations": declarations,
        "form16": {
            "fy_2024_25": {
                "status": "issued",
                "issued_on": "2025-06-12",
                "note": "Form 16 for FY 2024-25 (Part A and Part B) issued to every employee who was paid in that year.",
            },
            "fy_2025_26": {
                "status": "upcoming",
                "due_by": "2026-06-15",
                "note": "Form 16 for FY 2025-26 is generated after the March 2026 run and the Q4 TDS return.",
            },
        },
        "tickets": [
            {
                "id": "TK-1182",
                "subject": "PF ECR upload failed for November",
                "status": "resolved",
                "opened": "2025-12-03",
                "summary": "UAN missing for one new joiner; added and re-uploaded.",
            },
            {
                "id": "TK-1207",
                "subject": "Bank file format for Axis Bank",
                "status": "resolved",
                "opened": "2026-01-22",
                "summary": "Switched the bank transfer file to the bank's bulk-upload layout.",
            },
        ],
        "stories": stories,
    }
    return company


def import_csv(company: dict[str, Any]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["employee_id", "name", "email", "gender", "department", "designation", "location", "state", "date_of_joining", "annual_ctc", "pan", "uan", "tax_regime", "manager_id"])  # fmt: skip
    for e in company["employees"]:
        w.writerow([e["id"], e["name"], e["email"], e["gender"], e["department"], e["title"], e["location"], e["state"], e["joined"], e["annual_ctc"], e["pan"], e["uan"], e["tax_regime"], e["manager_id"] or ""])  # fmt: skip
    return buf.getvalue()


def fixtures() -> dict[str, Any]:
    """Cases the TypeScript engine must reproduce exactly."""
    cases: list[dict[str, Any]] = []
    salaries = [
        {
            "gross": 780000,
            "basic": 312000,
            "hra": 156000,
            "lta": 0,
            "employee_pf": 21600,
            "professional_tax": 2500,
            "months": 12,
            "metro": True,
        },
        {
            "gross": 1170000,
            "basic": 480000,
            "hra": 192000,
            "lta": 0,
            "employee_pf": 21600,
            "professional_tax": 2500,
            "months": 12,
            "metro": False,
        },
        {
            "gross": 1275000,
            "basic": 500000,
            "hra": 250000,
            "lta": 36000,
            "employee_pf": 21600,
            "professional_tax": 2500,
            "months": 12,
            "metro": True,
        },
        {
            "gross": 1658400,
            "basic": 672000,
            "hra": 336000,
            "lta": 36000,
            "employee_pf": 21600,
            "professional_tax": 2500,
            "months": 12,
            "metro": True,
        },
        {
            "gross": 3578400,
            "basic": 1440000,
            "hra": 576000,
            "lta": 60000,
            "employee_pf": 21600,
            "professional_tax": 2500,
            "months": 12,
            "metro": False,
        },
        {
            "gross": 520000,
            "basic": 208000,
            "hra": 83200,
            "lta": 0,
            "employee_pf": 21600,
            "professional_tax": 2400,
            "months": 12,
            "metro": False,
        },
        {
            "gross": 1300000,
            "basic": 520000,
            "hra": 208000,
            "lta": 0,
            "employee_pf": 21600,
            "professional_tax": 0,
            "months": 7,
            "metro": True,
        },
    ]
    decls = [
        eng.Declarations(),
        eng.Declarations(
            rent_monthly=35000,
            sec80c_other=128400,
            sec80d_self=25000,
            sec80d_parents=42000,
            parents_senior=True,
            sec80ccd1b=50000,
        ),
        eng.Declarations(
            sec80c_other=150000, home_loan_interest=250000, sec80d_self=30000, lta_claim=48000
        ),
    ]
    for s in salaries:
        for d in decls:
            sal = eng.AnnualSalary(**s)  # type: ignore[arg-type]
            for regime in ("new", "old"):
                cases.append(
                    {
                        "kind": "tax",
                        "regime": regime,
                        "salary": s,
                        "decl": asdict(d),
                        "out": eng.compute_tax(regime, sal, d).to_dict(),
                    }
                )  # type: ignore[arg-type]
    pays = [
        {
            "ctc": 1680000,
            "city": "Mumbai",
            "state": "Maharashtra",
            "gender": "M",
            "lta_monthly": 3000,
            "regime": "old",
            "first_month_idx": 0,
        },
        {
            "ctc": 252000,
            "city": "Pune",
            "state": "Maharashtra",
            "gender": "F",
            "lta_monthly": 0,
            "regime": "new",
            "first_month_idx": 0,
        },
        {
            "ctc": 3600000,
            "city": "Bengaluru",
            "state": "Karnataka",
            "gender": "F",
            "lta_monthly": 5000,
            "regime": "new",
            "first_month_idx": 0,
        },
        {
            "ctc": 396000,
            "city": "Hyderabad",
            "state": "Telangana",
            "gender": "M",
            "lta_monthly": 0,
            "regime": "new",
            "first_month_idx": 5,
        },
        {
            "ctc": 900000,
            "city": "New Delhi",
            "state": "Delhi",
            "gender": "M",
            "lta_monthly": 0,
            "regime": "new",
            "first_month_idx": 0,
        },
    ]
    for pdict in pays:
        pay = eng.EmployeePay(**pdict)  # type: ignore[arg-type]
        cases.append(
            {
                "kind": "structure",
                "pay": pdict,
                "out": asdict(eng.structure(pay.ctc, pay.city, pay.lta_monthly)),
            }
        )
        ytd = eng.Ytd()
        for m in range(12):
            if m < pay.first_month_idx:
                continue
            lop = 2 if m == JAN else 0
            d = decls[1] if pay.regime == "old" else decls[0]
            slip = eng.payslip(
                pay, m, MONTH_DAYS[m], lop, ytd, d, reimbursements=1000 if m == FEB else 0
            )
            cases.append(
                {
                    "kind": "payslip",
                    "pay": pdict,
                    "month_idx": m,
                    "days": MONTH_DAYS[m],
                    "lop": lop,
                    "ytd": asdict(ytd),
                    "decl": asdict(d),
                    "reimbursements": 1000 if m == FEB else 0,
                    "out": slip.to_dict(),
                }
            )
            ytd = ytd.plus(slip)
        cases.append(
            {
                "kind": "comparison",
                "pay": pdict,
                "ytd": asdict(ytd),
                "month_idx": FEB,
                "decl": asdict(decls[1]),
                "out": eng.regime_comparison(pay, eng.Ytd(), 0, decls[1]),
            }
        )
    # The comparison case above uses an empty ytd at month 0 for a whole-year view.
    for c in cases:
        if c["kind"] == "comparison":
            c["ytd"] = asdict(eng.Ytd())
            c["month_idx"] = 0
    return {
        "_about": "Generated by build_data.py from payroll_engine.py. engine.ts must match every case.",
        "cases": cases,
    }


def tax_example(company: dict[str, Any]) -> dict[str, Any]:
    """A worked example for the marketing site: a ₹16.8 lakh CTC salesperson in
    Mumbai, both regimes, with and without proofs. Anonymised: no names."""
    pay = eng.EmployeePay(
        ctc=1680000, city="Mumbai", state="Maharashtra", gender="M", lta_monthly=3000, regime="old"
    )
    spec = OLD_REGIME["Ravi Kumar"]
    declared = to_decl(spec, "declared")
    verified = to_decl(spec, "verified")
    full_year = eng.projected_annual(pay, eng.Ytd(), None, 0)
    return {
        "_about": "Generated by build_data.py with the same engine the product demo uses.",
        "fy_label": "FY 2025-26 (AY 2026-27)",
        "profile": {
            "annual_ctc": 1680000,
            "city": "Mumbai",
            "role": "Senior sales executive",
            "rent_monthly": 35000,
        },
        "annual_salary": asdict(full_year),
        "declared": {
            "decl": asdict(declared),
            "new": eng.compute_tax("new", full_year, declared).to_dict(),
            "old": eng.compute_tax("old", full_year, declared).to_dict(),
        },
        "after_proofs": {
            "decl": asdict(verified),
            "new": eng.compute_tax("new", full_year, verified).to_dict(),
            "old": eng.compute_tax("old", full_year, verified).to_dict(),
            "missing": ["ELSS ₹60,000", "NPS ₹50,000"],
        },
    }


def dump(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    company = build()
    dump(HERE / "company.json", company)
    (HERE / "employees_import.csv").write_text(import_csv(company), encoding="utf-8")
    dump(HERE / "tax_fixtures.json", fixtures())
    (SITE / "data").mkdir(parents=True, exist_ok=True)
    (SITE / "data" / "product.json").write_bytes((HERE / "product.json").read_bytes())
    dump(SITE / "data" / "tax_example.json", tax_example(company))
    s = company["stories"]["ravi_net_drop"]
    print(f"employees={len(company['employees'])} runs={len(company['payroll_runs'])}")
    print(f"ravi: {s}")
    print(f"kavitha: {company['stories']['kavitha_old_better']}")
    feb = company["payroll_runs"][-1]
    print(
        f"feb draft: gross={feb['gross']} net={feb['net_pay']} tds={feb['tds']} employees={feb['employees']}"
    )


if __name__ == "__main__":
    main()
