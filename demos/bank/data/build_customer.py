"""Write ``customer.json``: the one signed-in customer of the Anvaya Bank demo.

Everything is fictional and deterministic (a fixed seed), so the brain and the
page read exactly the same accounts, cards and transactions. Dates are kept as
``days_ago`` (and ``days_from_now`` for what is due), so the data is fresh
whenever the demo runs: both sides turn them into dates against today.

Run: ``uv run python demos/bank/data/build_customer.py``
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
SEED = 4821
DAYS = 120

#: (merchant shown on the statement, readable merchant, category, low, high)
FOOD = [
    ("ZESTRO*ORDER BLR", "Zestro food delivery", "food", 280, 1150),
    ("TIFFIN TALES KORAMANGALA", "Tiffin Tales", "food", 180, 520),
    ("BREW AND BLOOM CAFE", "Brew & Bloom Cafe", "food", 240, 890),
    ("MASALA JUNCTION INDIRANAGAR", "Masala Junction restaurant", "food", 900, 3400),
    ("DOSA POINT HSR", "Dosa Point", "food", 120, 380),
]
GROCERY = [
    ("FRESHBASKET BLR", "FreshBasket groceries", "groceries", 650, 3200),
    ("KIRANA QUICK 10MIN", "Kirana Quick delivery", "groceries", 210, 1400),
    ("NATURES CART HSR", "Nature's Cart", "groceries", 400, 2100),
]
CABS = [("URBAN RIDES TRIP", "Urban Rides cab", "travel", 140, 720)]
FUEL = [("CITY FUELS KORAMANGALA", "City Fuels petrol pump", "fuel", 1500, 3600)]
SHOP = [
    ("TRENDZY FASHION ONLINE", "Trendzy Fashion", "shopping", 1200, 4800),
    ("BOOKHAVEN BLR", "Bookhaven books", "shopping", 350, 1600),
    ("HOMELY DECOR ONLINE", "Homely Decor", "shopping", 800, 3900),
]
FUN = [("CINEPLEX FORUM MALL", "CinePlex Forum Mall", "entertainment", 450, 1400)]
HEALTH = [
    ("WELLNESS PHARMACY", "Wellness Pharmacy", "health", 220, 1800),
    ("CAREFIRST CLINIC", "CareFirst Clinic", "health", 600, 1500),
]


def money(x: float) -> float:
    return round(x, 2)


def build() -> dict[str, Any]:
    rng = random.Random(SEED)
    txns: list[dict[str, Any]] = []

    def add(
        account: str,
        days_ago: int,
        statement: str,
        merchant: str,
        category: str,
        amount: float,
        direction: str,
        mode: str,
        note: str | None = None,
    ) -> None:
        txns.append(
            {
                "account": account,
                "days_ago": days_ago,
                "description": statement,
                "merchant": merchant,
                "category": category,
                "amount": money(amount),
                "direction": direction,
                "mode": mode,
                **({"note": note} if note else {}),
            }
        )

    # ── Savings: salary, rent, SIP, EMI, bills, family, cash ────────────────
    for cycle, d in enumerate((107, 77, 47, 17)):
        add(
            "sb",
            d,
            "NEFT CR LUMEN SOFTWARE PVT LTD SALARY",
            "Lumen Software Pvt Ltd (salary)",
            "income",
            142500,
            "credit",
            "NEFT",
        )
        add(
            "sb",
            d - 1,
            "NEFT DR PRAKASH RAO RENT",
            "Prakash Rao (rent)",
            "rent",
            32000,
            "debit",
            "NEFT",
        )
        add(
            "sb",
            d - 2,
            "ANVAYA MF SIP 0042",
            "Anvaya Mutual Fund SIP",
            "investments",
            15000,
            "debit",
            "auto-debit",
        )
        add(
            "sb",
            d - 3,
            "LOAN EMI ANVAYA AUTO 7731",
            "Anvaya car loan EMI",
            "emi",
            14200,
            "debit",
            "auto-debit",
        )
        add(
            "sb",
            d - 4,
            "UPI SUNITA SHARMA",
            "Sunita Sharma (mother)",
            "transfers",
            10000,
            "debit",
            "UPI",
        )
        add(
            "sb",
            d - 6,
            "BILLPAY METRO POWER DISTRIBUTION",
            "Metro Power Distribution (electricity)",
            "bills",
            [2140, 1985, 1760, 1690][cycle],
            "debit",
            "bill pay",
        )
        add(
            "sb",
            d - 7,
            "BILLPAY SKYLINE FIBERNET",
            "Skyline Fibernet (broadband)",
            "bills",
            999,
            "debit",
            "bill pay",
        )
        add(
            "sb",
            d - 8,
            "BILLPAY NIMBUS MOBILE POSTPAID",
            "Nimbus Mobile postpaid",
            "bills",
            649,
            "debit",
            "bill pay",
        )
        if d - 12 >= 0:
            add(
                "sb",
                d - 12,
                "ATM WDL ANVAYA ATM KORAMANGALA",
                "Cash withdrawal, Anvaya ATM Koramangala",
                "cash",
                rng.choice([3000, 5000, 4000]),
                "debit",
                "ATM",
            )
    add(
        "sb",
        90,
        "INT CREDIT QTR",
        "Savings interest for the quarter",
        "income",
        2846.0,
        "credit",
        "interest",
    )
    add(
        "sb",
        63,
        "UPI RAHUL VERMA",
        "Rahul Verma",
        "transfers",
        2400,
        "debit",
        "UPI",
        "Split for a weekend trip",
    )
    add("sb", 41, "UPI CR RAHUL VERMA", "Rahul Verma", "transfers", 1200, "credit", "UPI")
    add(
        "sb",
        28,
        "REFUND TRENDZY FASHION",
        "Trendzy Fashion (refund)",
        "refunds",
        1899,
        "credit",
        "UPI",
    )
    add(
        "sb",
        9,
        "IMPS DR MEERA NAIR",
        "Meera Nair",
        "transfers",
        6500,
        "debit",
        "IMPS",
        "Birthday gift contribution",
    )
    # UPI from savings: small food, groceries, cabs
    for d in range(DAYS - 1, -1, -1):
        if rng.random() < 0.28:
            m = rng.choice(FOOD[:2] + FOOD[4:] + CABS + GROCERY[1:2])
            add("sb", d, "UPI " + m[0], m[1], m[2], rng.randint(m[3], m[4]), "debit", "UPI")

    # ── Credit card: most card spend ────────────────────────────────────────
    for d in range(DAYS - 1, -1, -1):
        if rng.random() < 0.42:
            m = rng.choice(FOOD)
            add("cc", d, m[0], m[1], m[2], rng.randint(m[3], m[4]), "debit", "card")
        if rng.random() < 0.18:
            m = rng.choice(GROCERY)
            add("cc", d, m[0], m[1], m[2], rng.randint(m[3], m[4]), "debit", "card")
        if rng.random() < 0.07:
            m = FUEL[0]
            add("cc", d, m[0], m[1], m[2], rng.randint(m[3], m[4]), "debit", "card")
        if rng.random() < 0.06:
            m = rng.choice(SHOP)
            add("cc", d, m[0], m[1], m[2], rng.randint(m[3], m[4]), "debit", "card")
        if rng.random() < 0.04:
            m = rng.choice(FUN + HEALTH)
            add("cc", d, m[0], m[1], m[2], rng.randint(m[3], m[4]), "debit", "card")
    # The ones the demo is built around.
    add(
        "cc",
        6,
        "SBX*ANNUAL PLAN MUMBAI IN",
        "StreamBox Media, annual streaming plan",
        "entertainment",
        4999,
        "debit",
        "card",
        "Annual renewal of your StreamBox plan, billed once a year. Auto-renew is on with this card.",
    )
    add(
        "cc",
        12,
        "VOLTMART ELECTRONICS BLR",
        "VoltMart Electronics, Koramangala",
        "shopping",
        64990,
        "debit",
        "card",
        "Laptop purchase. Eligible to convert to EMI.",
    )
    add(
        "cc",
        34,
        "SKYWINGS AIR BLR-GOI",
        "SkyWings Air, Bengaluru to Goa return",
        "travel",
        18450,
        "debit",
        "card",
    )
    add(
        "cc",
        32,
        "HOTEL SAFFRON STAY GOA",
        "Saffron Stay hotel, Goa",
        "travel",
        22800,
        "debit",
        "card",
    )
    add("cc", 31, "GOA COASTAL KITCHEN", "Goa Coastal Kitchen", "food", 3480, "debit", "card")
    add(
        "cc",
        71,
        "ROOPA JEWELLERS JAYANAGAR",
        "Roopa Jewellers, Jayanagar",
        "shopping",
        38500,
        "debit",
        "card",
    )
    add(
        "cc",
        88,
        "SKYWINGS AIR BLR-DEL",
        "SkyWings Air, Bengaluru to Delhi",
        "travel",
        9650,
        "debit",
        "card",
    )
    add(
        "cc",
        86,
        "HOTEL MERIDIAN COURT DELHI",
        "Meridian Court hotel, New Delhi",
        "travel",
        14200,
        "debit",
        "card",
    )
    add(
        "cc",
        21,
        "FEE ANNUAL MEMBERSHIP SPARK",
        "Annual fee, Anvaya Spark card",
        "fees",
        499,
        "debit",
        "fee",
    )
    add("cc", 20, "GST ON ANNUAL FEE", "GST on the annual fee", "fees", 89.82, "debit", "fee")
    add(
        "cc",
        19,
        "REVERSAL ANNUAL FEE SPARK",
        "Annual fee reversed (spend above ₹1.5 lakh)",
        "refunds",
        588.82,
        "credit",
        "fee",
    )

    # Statements every 30 days; each older one is paid from savings 15 days later.
    statement_days = (104, 74, 44, 14)
    statements: list[dict[str, Any]] = []
    for i, gen in enumerate(statement_days):
        start = gen + 30
        spent = sum(
            t["amount"]
            for t in txns
            if t["account"] == "cc" and gen <= t["days_ago"] < start and t["direction"] == "debit"
        )
        back = sum(
            t["amount"]
            for t in txns
            if t["account"] == "cc" and gen <= t["days_ago"] < start and t["direction"] == "credit"
        )
        total = money(spent - back)
        stmt = {
            "id": f"CCST-{i + 1}",
            "generated_days_ago": gen,
            "from_days_ago": start - 1,
            "to_days_ago": gen,
            "total_due": total,
            "min_due": money(max(200.0, round(total * 0.05))),
        }
        if gen - 15 >= 0 and i < len(statement_days) - 1:
            stmt["paid_days_ago"] = gen - 15
            add(
                "sb",
                gen - 15,
                "BILLPAY ANVAYA CREDIT CARD 3094",
                "Anvaya Spark credit card bill",
                "transfers",
                total,
                "debit",
                "bill pay",
            )
            add(
                "cc",
                gen - 15,
                "PAYMENT RECEIVED THANK YOU",
                "Payment received from savings",
                "transfers",
                total,
                "credit",
                "payment",
            )
        else:
            stmt["due_days_from_now"] = 6
        statements.append(stmt)

    # ── Current account: the design studio ──────────────────────────────────
    clients = [
        ("IMPS CR KESTREL FOODS PVT LTD", "Kestrel Foods Pvt Ltd", 85000),
        ("NEFT CR BLUEPEAK INTERIORS LLP", "Bluepeak Interiors LLP", 62000),
        ("NEFT CR ORCHID LEARNING", "Orchid Learning Pvt Ltd", 48000),
    ]
    for k, d in enumerate((112, 95, 81, 66, 52, 38, 24, 10)):
        c = clients[k % len(clients)]
        add(
            "ca",
            d,
            c[0],
            c[1] + " (client payment)",
            "income",
            c[2],
            "credit",
            "NEFT" if "NEFT" in c[0] else "IMPS",
        )
    for d in (110, 80, 50, 20):
        add(
            "ca",
            d,
            "NEFT DR HIVE COWORK SPACES",
            "Hive Cowork Spaces (desk rent)",
            "rent",
            12500,
            "debit",
            "NEFT",
        )
        add(
            "ca",
            d - 2,
            "FIGBOARD DESIGN SUITE SUBSCR",
            "Figboard design suite subscription",
            "bills",
            2360,
            "debit",
            "card",
        )
        add("ca", d - 5, "GST PAYMENT CHALLAN", "GST payment", "fees", 18900, "debit", "NEFT")
        add(
            "ca",
            d - 7,
            "IMPS DR ANIL KUMAR FREELANCE",
            "Anil Kumar (freelance illustrator)",
            "transfers",
            15000,
            "debit",
            "IMPS",
        )
    add(
        "ca",
        60,
        "TRF TO SELF SAVINGS 4821",
        "Transfer to your savings account",
        "transfers",
        40000,
        "debit",
        "internal",
    )
    add(
        "sb",
        60,
        "TRF FROM CURRENT 6630",
        "Transfer from your current account",
        "transfers",
        40000,
        "credit",
        "internal",
    )

    # Order newest first within each day; ids are stable.
    txns.sort(key=lambda t: (t["days_ago"], t["account"], t["description"]))
    balances = {"sb": 342815.40, "ca": 418240.00}
    for t in txns:  # newest first: walk balances back in time
        acc = t["account"]
        if acc in balances:
            t["balance_after"] = money(balances[acc])
            balances[acc] += -t["amount"] if t["direction"] == "credit" else t["amount"]
    lowest = {a: min(t["balance_after"] for t in txns if t["account"] == a) for a in balances}
    assert all(v > 0 for v in lowest.values()), lowest
    for n, t in enumerate(
        sorted(txns, key=lambda t: (-t["days_ago"], t["account"], t["description"]))
    ):
        t["id"] = f"T{n + 1:04d}"
        t["ref"] = f"{rng.randint(100000000000, 999999999999)}"
        t["emi_eligible"] = (
            t["account"] == "cc"
            and t["direction"] == "debit"
            and t["amount"] >= 2500
            and t["category"] in ("shopping", "travel", "health")
        )

    unbilled = sum(
        t["amount"] if t["direction"] == "debit" else -t["amount"]
        for t in txns
        if t["account"] == "cc" and t["days_ago"] < 14
    )
    last = statements[-1]
    outstanding = money(last["total_due"] + unbilled)
    limit = 250000.0

    return {
        "_note": "Fictional customer of the fictional Anvaya Bank. Generated by build_customer.py; do not edit by hand.",
        "profile": {
            "name": "Aditi Sharma",
            "first_name": "Aditi",
            "customer_id": "AN48213907",
            "mobile_masked": "+91 98XXX XX214",
            "email_masked": "ad•••@example.com",
            "city": "Bengaluru",
            "segment": "Privilege",
            "since_year": 2019,
            "relationship_manager": "Vikram Desai",
            "monthly_income": 142500,
            "employer": "Lumen Software Pvt Ltd",
            "age": 34,
        },
        "accounts": [
            {
                "id": "sb",
                "type": "savings",
                "name": "Privilege Savings",
                "product": "Anvaya Privilege Savings",
                "number_masked": "XXXX XXXX 4821",
                "last4": "4821",
                "ifsc": "ANVB0001207",
                "branch": "Koramangala, Bengaluru",
                "balance": 342815.40,
                "available": 342815.40,
                "rate": 3.75,
                "holder": "Aditi Sharma",
            },
            {
                "id": "ca",
                "type": "current",
                "name": "Business Current",
                "product": "Anvaya Business Current Account",
                "number_masked": "XXXX XXXX 6630",
                "last4": "6630",
                "ifsc": "ANVB0001207",
                "branch": "Koramangala, Bengaluru",
                "balance": 418240.00,
                "available": 418240.00,
                "rate": 0,
                "holder": "Sharma Design Studio (proprietor Aditi Sharma)",
            },
        ],
        "cards": [
            {
                "id": "debit",
                "kind": "debit",
                "name": "Privilege Visa Signature Debit",
                "network": "Visa",
                "last4": "7712",
                "linked_account": "sb",
                "expiry": "08/29",
                "limits": {"atm_daily": 50000, "pos_daily": 200000, "online_daily": 100000},
                "limits_max": {"atm_daily": 100000, "pos_daily": 500000, "online_daily": 300000},
                "controls": {
                    "blocked": False,
                    "international": False,
                    "online": True,
                    "contactless": True,
                    "atm": True,
                },
            },
            {
                "id": "credit",
                "kind": "credit",
                "name": "Anvaya Spark",
                "product_id": "spark",
                "network": "Visa",
                "last4": "3094",
                "expiry": "11/28",
                "credit_limit": limit,
                "outstanding": outstanding,
                "available": money(limit - outstanding),
                "cash_limit": 50000,
                "reward_points": 18420,
                "points_expiring": {"points": 1200, "days_from_now": 42},
                "limits": {"online_daily": 150000, "pos_daily": 250000, "atm_daily": 20000},
                "limits_max": {"online_daily": 250000, "pos_daily": 250000, "atm_daily": 50000},
                "controls": {
                    "blocked": False,
                    "international": True,
                    "online": True,
                    "contactless": True,
                    "atm": False,
                },
                "statement": {
                    "total_due": last["total_due"],
                    "min_due": last["min_due"],
                    "due_days_from_now": 6,
                    "generated_days_ago": last["generated_days_ago"],
                },
                "unbilled": money(unbilled),
            },
        ],
        "statements": statements,
        "beneficiaries": [
            {
                "id": "b-prakash",
                "name": "Prakash Rao",
                "nickname": "Landlord",
                "bank": "Kaveri Co-operative Bank",
                "account_masked": "XXXX 3318",
                "ifsc": "KCOB0000412",
                "limit": 100000,
            },
            {
                "id": "b-sunita",
                "name": "Sunita Sharma",
                "nickname": "Mum",
                "bank": "Anvaya Bank",
                "account_masked": "XXXX 9046",
                "ifsc": "ANVB0000318",
                "limit": 200000,
            },
            {
                "id": "b-rahul",
                "name": "Rahul Verma",
                "nickname": "Rahul",
                "bank": "Deccan Gramin Bank",
                "account_masked": "XXXX 5521",
                "ifsc": "DGBK0001190",
                "limit": 50000,
            },
            {
                "id": "b-meera",
                "name": "Meera Nair",
                "nickname": "Meera",
                "bank": "Anvaya Bank",
                "account_masked": "XXXX 7710",
                "ifsc": "ANVB0000655",
                "limit": 50000,
            },
            {
                "id": "b-anil",
                "name": "Anil Kumar",
                "nickname": "Illustrator",
                "bank": "Coastal Federal Bank",
                "account_masked": "XXXX 2087",
                "ifsc": "CFBL0002231",
                "limit": 100000,
            },
        ],
        "registered_billers": [
            {
                "biller_id": "metro-power",
                "consumer_masked": "XXXX 7781",
                "due": 1840.0,
                "due_days_from_now": 9,
                "autopay": False,
            },
            {
                "biller_id": "skyline-fibernet",
                "consumer_masked": "XXXX 0942",
                "due": 999.0,
                "due_days_from_now": 12,
                "autopay": True,
            },
            {
                "biller_id": "nimbus-mobile",
                "consumer_masked": "98XXX XX214",
                "due": 649.0,
                "due_days_from_now": 14,
                "autopay": False,
            },
            {
                "biller_id": "anvaya-card",
                "consumer_masked": "XXXX 3094",
                "due": last["total_due"],
                "due_days_from_now": 6,
                "autopay": False,
            },
        ],
        "deposits": [
            {
                "id": "fd-1",
                "kind": "fd",
                "amount": 200000,
                "rate": 7.1,
                "tenure_months": 12,
                "opened_days_ago": 140,
                "matures_days_from_now": 225,
                "payout": "cumulative",
                "maturity_amount": 214659.0,
            },
            {
                "id": "fd-2",
                "kind": "fd",
                "amount": 100000,
                "rate": 7.4,
                "tenure_months": 24,
                "opened_days_ago": 300,
                "matures_days_from_now": 430,
                "payout": "quarterly",
                "maturity_amount": 100000.0,
            },
        ],
        "loans": [
            {
                "id": "car-7731",
                "kind": "car",
                "name": "Anvaya Car Loan",
                "outstanding": 412000,
                "emi": 14200,
                "months_left": 34,
                "rate": 9.1,
                "next_emi_days_from_now": 13,
            },
        ],
        "offers": [
            {
                "id": "pl-preapproved",
                "kind": "loan",
                "loan_type": "personal",
                "title": "Pre-approved personal loan",
                "amount": 600000,
                "rate": 10.99,
                "tenure_max_months": 60,
                "valid_days_from_now": 21,
                "line": "Up to ₹6,00,000 at 10.99%, in your account in minutes.",
            },
            {
                "id": "card-upgrade-voyage",
                "kind": "card",
                "card_id": "voyage",
                "title": "Upgrade to Anvaya Voyage",
                "line": "You spent on travel in two of the last three months. Voyage earns 10 points per ₹100 on flights and hotels, with lounge access. Joining fee waived for you.",
            },
        ],
        "transactions": txns,
    }


def main() -> None:
    data = build()
    out = HERE / "customer.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    n = len(data["transactions"])
    print(f"wrote {out.name}: {n} transactions")


if __name__ == "__main__":
    main()
