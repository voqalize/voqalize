"""The Kosha Homes data and the rules the page shares with the brain.

``data/homes.json`` is the only source of facts. The search, EMI and visit-slot
rules here are the ones written in ``CONTRACT.md`` and implemented again in the
page (``frontend/src/data/``), so a count, an EMI or a free slot the agent says
is the one on screen. Everything is in memory and answers in microseconds.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

DATA = Path(__file__).resolve().parents[1] / "data" / "homes.json"
HOMES: dict[str, Any] = json.loads(DATA.read_text(encoding="utf-8"))

IST = ZoneInfo("Asia/Kolkata")
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
Part = Literal["morning", "afternoon", "evening", "any"]

LISTINGS: dict[str, dict[str, Any]] = {x["id"]: x for x in HOMES["listings"]}
PROJECTS: dict[str, dict[str, Any]] = {p["id"]: p for p in HOMES["projects"]}
CITIES: dict[str, dict[str, Any]] = {c["id"]: c for c in HOMES["cities"]}
LENDERS: dict[str, dict[str, Any]] = {x["id"]: x for x in HOMES["lenders"]}
EMI_DEFAULTS: dict[str, Any] = HOMES["emi"]
BRAND: dict[str, Any] = HOMES["brand"]


# ─── Money ──────────────────────────────────────────────────────────────────


def inr(n: float) -> str:
    """₹ in Indian grouping: 11400000 → ₹1,14,00,000."""
    s = str(round(n))
    if len(s) <= 3:
        return f"₹{s}"
    head, tail = s[:-3], s[-3:]
    groups: list[str] = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return "₹" + ",".join(groups) + "," + tail


def short(n: float) -> str:
    """The way a buyer says it: ₹1.14 crore, ₹92 lakh, ₹42,000."""
    if n >= 1_00_00_000:
        return f"₹{n / 1_00_00_000:.2f}".rstrip("0").rstrip(".") + " crore"
    if n >= 1_00_000:
        return f"₹{n / 1_00_000:.1f}".rstrip("0").rstrip(".") + " lakh"
    return inr(n)


def price_line(x: dict[str, Any]) -> str:
    if x["deal"] == "rent":
        return f"{inr(x['rent'])} a month, deposit {short(x['deposit'])}"
    return short(x["price"])


# ─── Search ─────────────────────────────────────────────────────────────────


@dataclass
class Search:
    """The listings page's search; unset fields do not filter (CONTRACT.md)."""

    city: str | None = None
    deal: str | None = None
    bhk: list[int] = field(default_factory=lambda: list[int]())
    budget_min: int | None = None
    budget_max: int | None = None
    possession: str | None = None
    localities: list[str] = field(default_factory=lambda: list[str]())
    office: str | None = None
    max_km: float | None = None
    school_km: float | None = None
    metro_km: float | None = None
    amenities: list[str] = field(default_factory=lambda: list[str]())

    def args(self) -> dict[str, Any]:
        """As the ``listings.filter`` move takes it: every field, unset ones null."""
        return {
            "city": self.city,
            "deal": self.deal,
            "bhk": [str(b) for b in self.bhk] or None,  # a move's array carries strings
            "budget_min": self.budget_min,
            "budget_max": self.budget_max,
            "possession": self.possession,
            "localities": list(self.localities) or None,
            "office": self.office,
            "max_km": self.max_km,
            "school_km": self.school_km,
            "metro_km": self.metro_km,
            "amenities": list(self.amenities) or None,
        }

    @classmethod
    def of(cls, data: dict[str, Any]) -> Search:
        def ints(v: Any) -> list[int]:
            return [int(i) for i in v or []]

        def strs(v: Any) -> list[str]:
            return [str(i) for i in v or []]

        return cls(
            city=data.get("city") or None,
            deal=data.get("deal") or None,
            bhk=ints(data.get("bhk")),
            budget_min=data.get("budget_min"),
            budget_max=data.get("budget_max"),
            possession=data.get("possession") or None,
            localities=strs(data.get("localities")),
            office=data.get("office") or None,
            max_km=data.get("max_km"),
            school_km=data.get("school_km"),
            metro_km=data.get("metro_km"),
            amenities=strs(data.get("amenities")),
        )

    def summary(self) -> str:
        parts: list[str] = []
        if self.city:
            parts.append(CITIES[self.city]["name"])
        if self.deal:
            parts.append("to rent" if self.deal == "rent" else "to buy")
        if self.bhk:
            parts.append("/".join(str(b) for b in sorted(self.bhk)) + " BHK")
        if self.budget_min is not None:
            parts.append(f"from {short(self.budget_min)}")
        if self.budget_max is not None:
            parts.append(f"up to {short(self.budget_max)}")
        if self.possession:
            parts.append("ready to move" if self.possession == "ready" else "under construction")
        if self.localities:
            parts.append("in " + ", ".join(self.localities))
        if self.office:
            name = place_name(self.office)
            parts.append(f"within {self.max_km:g} km of {name}" if self.max_km else f"near {name}")
        if self.school_km is not None:
            parts.append(f"a school within {self.school_km:g} km")
        if self.metro_km is not None:
            parts.append(f"metro within {self.metro_km:g} km")
        if self.amenities:
            parts.append("with " + ", ".join(self.amenities))
        return ", ".join(parts) or "every home"


def office_km(x: dict[str, Any], office: str) -> float | None:
    return next((o["km"] for o in x["nearby"]["offices"] if o["id"] == office), None)


def amount(x: dict[str, Any]) -> int:
    return int(x["rent"] if x["deal"] == "rent" else x["price"])


def matches(x: dict[str, Any], s: Search) -> bool:
    if s.city and x["city"] != s.city:
        return False
    if s.deal and x["deal"] != s.deal:
        return False
    if s.bhk and x["bhk"] not in s.bhk:
        return False
    if s.budget_min is not None and amount(x) < s.budget_min:
        return False
    if s.budget_max is not None and amount(x) > s.budget_max:
        return False
    if s.possession and x["possession"] != s.possession:
        return False
    if s.localities and x["locality"] not in s.localities:
        return False
    if s.office and s.max_km is not None:
        km = office_km(x, s.office)
        if km is None or km > s.max_km:
            return False
    if s.school_km is not None and x["nearby"]["schools"][0]["km"] > s.school_km:
        return False
    if s.metro_km is not None and x["nearby"]["metro"][0]["km"] > s.metro_km:
        return False
    return all(a in x["amenities"] for a in s.amenities)


def search(s: Search) -> list[dict[str, Any]]:
    """The matching listings, in the page's order (CONTRACT.md)."""
    found = [x for x in HOMES["listings"] if matches(x, s)]
    if s.office:
        office = s.office
        return sorted(found, key=lambda x: (office_km(x, office) or 99.0, amount(x), x["id"]))
    return sorted(found, key=lambda x: (x["deal"] == "rent", amount(x), x["id"]))


# ─── Places ─────────────────────────────────────────────────────────────────


def places(kind: str | None = None, city: str | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in HOMES["cities"]:
        if city and c["id"] != city:
            continue
        out.extend({**p, "city": c["id"]} for p in c["places"] if kind is None or p["kind"] == kind)
    return out


def place_name(place_id: str) -> str:
    return next((p["name"] for p in places() if p["id"] == place_id), place_id)


def localities(city: str | None = None) -> list[str]:
    return [
        loc["name"]
        for c in HOMES["cities"]
        if not city or c["id"] == city
        for loc in c["localities"]
    ]


# ─── EMI ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Emi:
    price: int
    down_pct: float
    tenure_years: int
    lender: dict[str, Any]
    principal: int
    emi: int
    total_interest: int


def emi(price: int, down_pct: float, tenure_years: int, lender_id: str) -> Emi:
    lender = LENDERS[lender_id]
    principal = price * (1 - down_pct / 100)
    r = float(lender["rate"]) / 1200
    n = tenure_years * 12
    grow = (1 + r) ** n
    monthly = round(principal * r * grow / (grow - 1))
    return Emi(
        price=price,
        down_pct=down_pct,
        tenure_years=tenure_years,
        lender=lender,
        principal=round(principal),
        emi=monthly,
        total_interest=round(monthly * n - principal),
    )


# ─── Site visits ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Host:
    """Who shows a listing: a project's sales team or the city's Exchange desk."""

    contact: str
    phone: str
    address: str
    team: dict[str, Any]
    bring: tuple[str, ...]


def host(x: dict[str, Any]) -> Host:
    if x["kind"] == "new":
        p = PROJECTS[x["project_id"]]
        team = p["team"]
        bring = HOMES["bring"]["new" if p["status"] == "under_construction" else "ready"]
        return Host(team["contact"], team["phone"], p["address"], team, tuple(bring))
    desk = CITIES[x["city"]]["exchange"]
    bring = HOMES["bring"]["rent" if x["deal"] == "rent" else "resale"]
    return Host(desk["contact"], desk["phone"], desk["office"], desk, tuple(bring))


def today_ist(now: datetime | None = None) -> date:
    return (now or datetime.now(IST)).astimezone(IST).date()


def visit_days(now: datetime | None = None) -> list[date]:
    """The seven dates after today, in IST."""
    start = today_ist(now)
    return [start + timedelta(days=i) for i in range(1, 8)]


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def part_of(hhmm: str) -> Part:
    m = _minutes(hhmm)
    if m < 12 * 60:
        return "morning"
    if m < 16 * 60:
        return "afternoon"
    return "evening"


@dataclass(frozen=True)
class Slot:
    id: str  # YYYY-MM-DDTHH:MM
    day: date
    time: str
    free: bool


def day_slots(x: dict[str, Any], day: date, taken: Iterable[str] = ()) -> list[Slot] | None:
    """Every slot of ``day`` for listing ``x``; None when the host is closed."""
    team = host(x).team
    key = WEEKDAYS[day.weekday()]
    hours = team["hours"].get(key)
    if not hours:
        return None
    step = int(team["slot_minutes"])
    booked = set(team["booked"].get(key, []))
    held = set(taken)
    out: list[Slot] = []
    t, close = _minutes(hours[0]), _minutes(hours[1])
    while t + step <= close:
        hhmm = _hhmm(t)
        sid = f"{day.isoformat()}T{hhmm}"
        out.append(Slot(sid, day, hhmm, hhmm not in booked and sid not in held))
        t += step
    return out


def free_slots(
    x: dict[str, Any], day: date, part: Part = "any", taken: Iterable[str] = ()
) -> list[Slot]:
    slots = day_slots(x, day, taken) or []
    return [s for s in slots if s.free and (part == "any" or part_of(s.time) == part)]


def reference(listing_id: str, slot_id: str) -> str:
    """``KV-<listing number>-<DD><HHMM>``: BLR-104 on the 22nd at 10:30 → KV-104-221030."""
    number = listing_id.split("-")[-1]
    day = slot_id[8:10]
    hhmm = slot_id[11:16].replace(":", "")
    return f"KV-{number}-{day}{hhmm}"


def spoken_day(d: date) -> str:
    return f"{d.strftime('%A')} {d.day} {d.strftime('%b')}"


def spoken_time(hhmm: str) -> str:
    h, m = (int(v) for v in hhmm.split(":"))
    suffix = "am" if h < 12 else "pm"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {suffix}" if m else f"{h12} {suffix}"


def compare_rows(ids: Sequence[str]) -> list[tuple[str, list[str], int | None]]:
    """(label, values, index of the better one or None) for each row of a comparison."""
    xs = [LISTINGS[i] for i in ids]
    rows: list[tuple[str, list[str], int | None]] = []

    def best(values: list[float], low: bool) -> int | None:
        if len(set(values)) < 2:
            return None
        pick = min(values) if low else max(values)
        return values.index(pick)

    if all(x["deal"] == "buy" for x in xs):
        prices = [float(x["price"]) for x in xs]
        rows.append(("Price", [short(p) for p in prices], best(prices, True)))
        per = [float(x["price_per_sqft"]) for x in xs]
        rows.append(("Price per sq ft", [inr(p) for p in per], best(per, True)))
    else:
        rows.append(("Rent or price", [price_line(x) for x in xs], None))
    carpets = [float(x["carpet_sqft"]) for x in xs]
    rows.append(("Carpet area", [f"{int(c)} sq ft" for c in carpets], best(carpets, False)))
    rows.append(("Configuration", [f"{x['bhk']} BHK" for x in xs], None))
    rows.append(("Possession", [x["possession_date"] for x in xs], None))
    rows.append(("Floor", [f"{x['floor']} of {x['total_floors']}" for x in xs], None))
    rows.append(("Facing", [x["facing"] for x in xs], None))
    metro = [float(x["nearby"]["metro"][0]["km"]) for x in xs]
    rows.append(
        (
            "Nearest metro",
            [f"{x['nearby']['metro'][0]['name']}, {x['nearby']['metro'][0]['km']} km" for x in xs],
            best(metro, True),
        )
    )
    school = [float(x["nearby"]["schools"][0]["km"]) for x in xs]
    rows.append(
        (
            "Nearest school",
            [
                f"{x['nearby']['schools'][0]['name']}, {x['nearby']['schools'][0]['km']} km"
                for x in xs
            ],
            best(school, True),
        )
    )
    amen = [float(len(x["amenities"])) for x in xs]
    rows.append(("Amenities", [str(len(x["amenities"])) for x in xs], best(amen, False)))
    return rows


def facts(x: dict[str, Any]) -> str:
    """One listing, in plain lines the model can speak from."""
    n = x["nearby"]
    offices = "; ".join(f"{o['name']} {o['km']} km" for o in n["offices"][:3])
    schools = "; ".join(f"{s['name']} {s['km']} km" for s in n["schools"][:2])
    metro = n["metro"][0]
    lines = [
        f"{x['id']}: {x['title']}, {x['locality']}, {CITIES[x['city']]['name']}.",
        f"{price_line(x)}"
        + (f" ({inr(x['price_per_sqft'])} per sq ft)" if x["deal"] == "buy" else "")
        + ".",
        f"{x['bhk']} BHK, {x['carpet_sqft']} sq ft carpet, floor {x['floor']} of "
        f"{x['total_floors']}, {x['facing']} facing, {x['bathrooms']} bathrooms, "
        f"{x['balconies']} balconies, {x['parking']} parking, {x['furnishing']}.",
        f"Possession: {x['possession_date']}."
        + (f" Building age {x['age_years']} years." if x.get("age_years") else ""),
        f"Registration (demo): {x['rera']}.",
        f"Amenities: {', '.join(x['amenities'])}.",
        f"Nearest metro {metro['name']} {metro['km']} km. Schools: {schools}. Offices: {offices}.",
    ]
    return " ".join(lines)
