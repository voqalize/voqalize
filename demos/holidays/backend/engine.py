"""The holiday engine: prices, days and recommended picks, from the inventory.

The rules are written once in ``CONTRACT.md`` ("The engine") and implemented
twice — here, for the brain, and in ``frontend/src/engine.ts``, for the page —
because a visitor building a trip by hand never touches the brain. Both are held
to ``data/engine_cases.json``, which :func:`write_cases` writes from this file:
the page's vitest runs every case, and ``tests/test_holidays_engine.py`` fails
when the file is stale.

Everything is a dict read or a small loop over one destination, so every tool
answers in well under a millisecond.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any, Literal

DATA = Path(__file__).resolve().parent.parent / "data"
INVENTORY: dict[str, Any] = json.loads((DATA / "inventory.json").read_text())
RULES: dict[str, Any] = INVENTORY["rules"]
CASES = DATA / "engine_cases.json"

Style = Literal["relaxed", "adventure", "honeymoon", "family"]
STYLES: tuple[Style, ...] = ("relaxed", "adventure", "honeymoon", "family")
DayKind = Literal["arrival", "transfer", "full", "departure"]
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

DESTINATIONS: dict[str, dict[str, Any]] = {d["id"]: d for d in INVENTORY["destinations"]}
ORIGINS: dict[str, str] = {o["id"]: o["city"] for o in INVENTORY["origins"]}
FLIGHTS: dict[str, dict[str, Any]] = {f["id"]: f for f in INVENTORY["flights"]}
CITIES: dict[str, dict[str, Any]] = {
    c["id"]: {**c, "destination": d["id"]} for d in INVENTORY["destinations"] for c in d["cities"]
}
HOTELS: dict[str, dict[str, Any]] = {
    h["id"]: {**h, "city": c["id"]} for c in CITIES.values() for h in c["hotels"]
}
ACTIVITIES: dict[str, dict[str, Any]] = {
    a["id"]: {**a, "city": c["id"]} for c in CITIES.values() for a in c["activities"]
}


def money(n: int | float) -> str:
    """₹ in Indian grouping: ₹1,25,000."""
    n = round(n)
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


def day_label(d: date) -> str:
    """DD MMM YYYY, with the weekday: Fri 12 Dec 2026."""
    return f"{WEEKDAYS[d.weekday()]} {d.day:02d} {d.strftime('%b')} {d.year}"


def round10(x: float) -> int:
    return math.floor(x / 10 + 0.5) * 10


def half_up(x: float) -> int:
    return math.floor(x + 0.5)


# ─── The trip ─────────────────────────────────────────────────────────────────


@dataclass
class Trip:
    """One trip, the same shape the page keeps (CONTRACT.md, "The trip")."""

    from_city: str | None = None
    destination: str | None = None
    start_date: str | None = None
    nights: int | None = None
    adults: int = 2
    kids: list[int] = field(default_factory=lambda: list[int]())
    budget: int = 0
    style: Style | None = None
    split: list[int] = field(default_factory=lambda: list[int]())
    flight_id: str | None = None
    hotels: dict[str, tuple[str, str]] = field(default_factory=lambda: dict[str, tuple[str, str]]())
    activities: list[tuple[int, str]] = field(default_factory=lambda: list[tuple[int, str]]())

    @property
    def dest(self) -> dict[str, Any] | None:
        return DESTINATIONS.get(self.destination or "")

    @property
    def pax(self) -> int:
        return self.adults + len(self.kids)

    @property
    def paying_kids(self) -> int:
        return sum(1 for a in self.kids if a > RULES["infant_max_age"])

    @property
    def infants(self) -> int:
        return sum(1 for a in self.kids if a <= RULES["infant_max_age"])

    def missing(self) -> list[str]:
        """What the brief still needs before flights can be shown."""
        need = []
        if not self.from_city:
            need.append("from_city")
        if not self.destination:
            need.append("destination")
        if not self.start_date:
            need.append("start_date")
        if not self.nights:
            need.append("nights")
        return need

    def to_json(self) -> dict[str, Any]:
        return {
            "from_city": self.from_city,
            "destination": self.destination,
            "start_date": self.start_date,
            "nights": self.nights,
            "adults": self.adults,
            "kids": list(self.kids),
            "budget": self.budget,
            "style": self.style,
            "split": list(self.split),
            "flight_id": self.flight_id,
            "hotels": {c: {"hotel_id": h, "room_id": r} for c, (h, r) in self.hotels.items()},
            "activities": [{"day": d, "activity_id": a} for d, a in self.activities],
        }

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> Trip:
        """The page's trip (``init.trip``), keeping only what the inventory knows."""
        t = cls()
        if (o := str(raw.get("from_city") or "")) in ORIGINS:
            t.from_city = o
        if (d := str(raw.get("destination") or "")) in DESTINATIONS:
            t.destination = d
        if isinstance(sd := raw.get("start_date"), str) and _parse_date(sd):
            t.start_date = sd
        if isinstance(n := raw.get("nights"), int) and t.dest and _nights_ok(t.dest, n):
            t.nights = n
        if isinstance(a := raw.get("adults"), int) and 1 <= a <= RULES["max_travellers"]:
            t.adults = a
        kids = raw.get("kids")
        if isinstance(kids, list):
            t.kids = [
                int(k) for k in kids if isinstance(k, int) and 0 <= k <= RULES["child_max_age"]
            ]  # pyright: ignore[reportUnknownVariableType]
        if isinstance(b := raw.get("budget"), int) and b >= 0:
            t.budget = b
        if raw.get("style") in STYLES:
            t.style = raw["style"]
        if t.dest and t.nights:
            split = raw.get("split")
            if isinstance(split, list) and valid_split(
                t, [int(x) for x in split if isinstance(x, int)]
            ):  # pyright: ignore[reportUnknownVariableType]
                t.split = [int(x) for x in split]  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
            else:
                t.split = default_split(t.dest, t.nights)
        f = FLIGHTS.get(str(raw.get("flight_id") or ""))
        if f and f["origin"] == t.from_city and f["destination"] == t.destination:
            t.flight_id = f["id"]
        hotels = raw.get("hotels")
        if isinstance(hotels, dict):
            for city, pick in hotels.items():  # pyright: ignore[reportUnknownVariableType]
                if not isinstance(pick, dict):
                    continue
                h = HOTELS.get(str(pick.get("hotel_id") or ""))  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
                room = str(pick.get("room_id") or "")  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
                if h and h["city"] == city and any(r["id"] == room for r in h["rooms"]):
                    t.hotels[str(city)] = (h["id"], room)  # pyright: ignore[reportUnknownArgumentType]
        acts = raw.get("activities")
        if isinstance(acts, list):
            for a in acts:  # pyright: ignore[reportUnknownVariableType]
                if isinstance(a, dict) and isinstance(a.get("day"), int):  # pyright: ignore[reportUnknownMemberType]
                    aid = str(a.get("activity_id") or "")  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
                    day = int(a["day"])  # pyright: ignore[reportUnknownArgumentType]
                    if aid in ACTIVITIES and can_add(t, aid, day) is None:
                        t.activities.append((day, aid))
        return t


# ─── Dates ────────────────────────────────────────────────────────────────────


def _parse_date(s: str) -> date | None:
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def earliest(today: date) -> date:
    return today + timedelta(days=RULES["min_days_ahead"])


def month_start(month: int, today: date, year: int | None = None) -> date:
    """The default departure for a month: the first Friday on or after the 10th,
    in the next occurrence of that month at least a week away."""
    years = [year] if year else [today.year, today.year + 1, today.year + 2]
    for y in years:
        d = date(y, month, 10)
        d += timedelta(days=(4 - d.weekday()) % 7)
        if d >= earliest(today) or year:
            return d
    raise ValueError("no such month")


def day1(t: Trip) -> date | None:
    """The holiday's first day: the day the outbound flight lands."""
    if not t.start_date:
        return None
    start = date.fromisoformat(t.start_date)
    f = FLIGHTS.get(t.flight_id or "")
    return start + timedelta(days=int(f["out"]["arrive_day"]) if f else 0)


# ─── Days and cities ──────────────────────────────────────────────────────────


def _nights_ok(dest: Mapping[str, Any], n: int) -> bool:
    lo, hi = dest["nights"]
    return lo <= n <= hi


def default_split(dest: Mapping[str, Any], nights: int) -> list[int]:
    return list(dest["splits"][str(nights)])


def valid_split(t: Trip, split: Sequence[int]) -> bool:
    """A split the inventory can serve: one number per city, summing to the
    nights, a transfer between each pair of cities with nights, and the first
    city kept when the arrival transfer goes to it by name."""
    d = t.dest
    if not d or not t.nights or len(split) != len(d["cities"]):
        return False
    if any(n < 0 for n in split) or sum(split) != t.nights:
        return False
    ids = [c["id"] for c, n in zip(d["cities"], split, strict=True) if n > 0]
    legs = {(x["from"], x["to"]) for x in d["transfers"]}
    if any((a, b) not in legs for a, b in pairwise(ids)):
        return False
    arrive = next(x for x in d["transfers"] if x["id"].endswith("-arrive"))
    return arrive["to"] in ("first", ids[0])


def stops(t: Trip) -> list[tuple[str, int]]:
    """(city id, nights) for each city with nights, in route order."""
    d = t.dest
    if not d or not t.split:
        return []
    return [(c["id"], n) for c, n in zip(d["cities"], t.split, strict=True) if n > 0]


@dataclass(frozen=True)
class Day:
    n: int
    city: str
    kind: DayKind
    date: date | None

    @property
    def slots(self) -> tuple[str, ...]:
        if self.kind == "full":
            return ("morning", "afternoon", "evening")
        if self.kind in ("arrival", "transfer"):
            return ("evening",)
        return ()


def days(t: Trip) -> list[Day]:
    if not t.nights:
        return []
    first = day1(t)
    out: list[Day] = []
    n = 1
    for i, (city, nights) in enumerate(stops(t)):
        for k in range(nights):
            kind: DayKind = "full"
            if k == 0:
                kind = "arrival" if i == 0 else "transfer"
            out.append(Day(n, city, kind, first + timedelta(days=n - 1) if first else None))
            n += 1
    if out:
        last = out[-1].city
        out.append(Day(n, last, "departure", first + timedelta(days=n - 1) if first else None))
    return out


def _slots_of(activity: Mapping[str, Any]) -> tuple[str, ...]:
    return ("morning", "afternoon") if activity["slot"] == "full_day" else (activity["slot"],)


def can_add(
    t: Trip, activity_id: str, day: int, *, ignore: tuple[int, str] | None = None
) -> str | None:
    """Why ``activity_id`` cannot go on ``day``, or None when it can."""
    a = ACTIVITIES.get(activity_id)
    if a is None:
        return "there is no such activity"
    ds = {d.n: d for d in days(t)}
    d = ds.get(day)
    if d is None:
        return f"the trip has days 1 to {len(ds)}" if ds else "the trip has no days yet"
    if d.city != a["city"]:
        return f"day {day} is in {CITIES[d.city]['name']}, and {a['name']} is in {CITIES[a['city']]['name']}"
    if d.kind == "departure":
        return f"day {day} is the day you fly home"
    need = _slots_of(a)
    if any(s not in d.slots for s in need):
        if d.kind in ("arrival", "transfer"):
            return f"day {day} is a travel day, with only the evening free"
        return f"{a['name']} does not fit day {day}"
    taken = {
        s
        for dn, aid in t.activities
        if dn == day and (dn, aid) != ignore
        for s in _slots_of(ACTIVITIES[aid])
    }
    if taken & set(need):
        return f"the {', '.join(sorted(set(need) & taken))} of day {day} is already taken"
    if any(age < a["min_age"] for age in t.kids):
        return f"{a['name']} is for ages {a['min_age']} and up"
    if a["min_age"] >= 18 and t.kids:
        return f"{a['name']} is for adults only"
    if d.date and WEEKDAYS[d.date.weekday()] in a["closed"]:
        return f"{a['name']} does not run on {WEEKDAYS[d.date.weekday()]}days"
    if (day, activity_id) in t.activities:
        return f"{a['name']} is already on day {day}"
    return None


# ─── Prices ───────────────────────────────────────────────────────────────────


def season_pct(t: Trip) -> int:
    if not t.start_date:
        return 100
    return int(RULES["season"].get(str(date.fromisoformat(t.start_date).month), 100))


def flight_price(t: Trip, flight: Mapping[str, Any]) -> tuple[int, int]:
    """(per adult, total) for this trip's travellers."""
    adult = round10(flight["fare_adult"] * season_pct(t) / 100)
    child = round10(adult * RULES["child_fare_pct"] / 100)
    return adult, adult * t.adults + child * t.paying_kids + RULES["infant_fare"] * t.infants


def rooms(t: Trip) -> int:
    return math.ceil(t.adults / RULES["adults_per_room"])


def hotel_price(t: Trip, city: str, hotel_id: str, room_id: str) -> int:
    nights = dict(stops(t)).get(city, 0)
    room = next(r for r in HOTELS[hotel_id]["rooms"] if r["id"] == room_id)
    return int(room["price"]) * nights * rooms(t)


def vehicle(t: Trip) -> str:
    for name, cap in RULES["vehicles"]:
        if t.pax <= cap:
            return str(name)
    return str(RULES["vehicles"][-1][0])


@dataclass(frozen=True)
class Leg:
    id: str
    label: str
    mode: str
    duration: str
    price: int


def transfer_legs(t: Trip) -> list[Leg]:
    d = t.dest
    st = [c for c, _ in stops(t)]
    if not d or not st:
        return []
    by_id = {x["id"]: x for x in d["transfers"]}
    arrive = next(x for x in d["transfers"] if x["id"].endswith("-arrive"))
    depart = next(x for x in d["transfers"] if x["id"].endswith("-depart"))
    chosen = [(arrive, f"{arrive['from']} → {CITIES[st[0]]['name']}", st[0])]
    for a, b in pairwise(st):
        x = next(v for v in by_id.values() if v["from"] == a and v["to"] == b)
        chosen.append((x, f"{CITIES[a]['name']} → {CITIES[b]['name']}", b))
    chosen.append((depart, f"{CITIES[st[-1]]['name']} → {depart['to']}", st[-1]))
    legs: list[Leg] = []
    for x, label, city in chosen:
        mode = str(x["mode"])
        if x["pricing"] == "per_vehicle":
            v = vehicle(t)
            price = int(x["prices"][v])
            mode = f"private {'car' if v == 'sedan' else v.upper() if v == 'suv' else 'van'}"
        else:
            prices = x["prices"]
            if "by_hotel" in x:
                pick = t.hotels.get(city)
                entry = x["by_hotel"].get(pick[0]) if pick else None
                prices = entry or {"adult": 0, "child": 0}
                mode = str(entry["mode"]) if entry else "boat or seaplane, set by the resort"
            price = int(prices["adult"]) * t.adults + int(prices["child"]) * t.paying_kids
        legs.append(Leg(x["id"], label, mode, str(x["duration"]), price))
    return legs


def activity_price(t: Trip, activity_id: str) -> int:
    a = ACTIVITIES[activity_id]
    return int(a["price_adult"]) * t.adults + int(a["price_child"]) * t.paying_kids


@dataclass(frozen=True)
class Price:
    flights: int
    hotels: int
    transfers: int
    activities: int
    gst: int
    total: int
    per_person: int

    @property
    def land(self) -> int:
        return self.hotels + self.transfers + self.activities

    def to_json(self) -> dict[str, int]:
        return {
            "flights": self.flights,
            "hotels": self.hotels,
            "transfers": self.transfers,
            "activities": self.activities,
            "gst": self.gst,
            "total": self.total,
            "per_person": self.per_person,
        }


def price(t: Trip) -> Price:
    f = FLIGHTS.get(t.flight_id or "")
    flights = flight_price(t, f)[1] if f else 0
    hotels = sum(hotel_price(t, c, h, r) for c, (h, r) in t.hotels.items() if c in dict(stops(t)))
    transfers = sum(leg.price for leg in transfer_legs(t))
    acts = sum(activity_price(t, a) for _, a in t.activities)
    land = hotels + transfers + acts
    gst = half_up(land * RULES["gst_pct"] / 100)
    total = flights + land + gst
    return Price(flights, hotels, transfers, acts, gst, total, half_up(total / max(t.pax, 1)))


# ─── Recommended picks ────────────────────────────────────────────────────────


def flights_for(t: Trip) -> list[dict[str, Any]]:
    return [
        f
        for f in INVENTORY["flights"]
        if f["origin"] == t.from_city and f["destination"] == t.destination
    ]


def recommended_flight(t: Trip) -> dict[str, Any] | None:
    options = flights_for(t)
    nonstop = [f for f in options if f["stops"] == 0]
    pool = nonstop or options
    return min(pool, key=lambda f: f["fare_adult"]) if pool else None


def _style_of(t: Trip) -> str:
    return t.style or ("family" if t.kids else "relaxed")


def recommended_hotel(t: Trip, city: str) -> tuple[str, str]:
    hotels = CITIES[city]["hotels"]
    style = _style_of(t)
    fitting = [h for h in hotels if style in h["tags"]]
    h = fitting[0] if fitting else hotels[0]
    return h["id"], h["rooms"][0]["id"]


def _cheapest_hotel(t: Trip, city: str) -> tuple[str, str]:
    hotels = CITIES[city]["hotels"]
    style = _style_of(t)
    fitting = [h for h in hotels if style in h["tags"]] or hotels
    h = min(fitting, key=lambda h: h["rooms"][0]["price"])
    return h["id"], h["rooms"][0]["id"]


def recommended_activities(t: Trip) -> list[tuple[int, str]]:
    style = _style_of(t)
    trial = replace(t, activities=[])
    for d in days(t):
        if d.kind == "arrival":
            wanted = [("evening",)]
        elif d.kind == "full":
            wanted = [("morning", "full_day"), ("afternoon",)]
        else:
            continue
        for slots in wanted:
            pick = next(
                (
                    a["id"]
                    for a in CITIES[d.city]["activities"]
                    if a["slot"] in slots
                    and style in a["tags"]
                    and all(a["id"] != x for _, x in trial.activities)
                    and can_add(trial, a["id"], d.n) is None
                ),
                None,
            )
            if pick:
                trial.activities.append((d.n, pick))
                break
    return trial.activities


def build_package(t: Trip) -> Trip:
    """The whole package for a complete brief (CONTRACT.md, "Recommended picks")."""
    out = replace(t, hotels={}, activities=[])
    f = recommended_flight(out)
    out.flight_id = f["id"] if f else None
    for city, _ in stops(out):
        out.hotels[city] = recommended_hotel(out, city)
    out.activities = recommended_activities(out)
    if out.budget and price(out).total > out.budget:
        for city, _ in stops(out):
            out.hotels[city] = _cheapest_hotel(out, city)
    return out


def from_price(destination: str, origin: str = "DEL") -> int:
    """The "from ₹X per person" a destination card shows: two adults, the
    default nights, the cheapest flight from ``origin``, the cheapest room in each
    city, transfers and GST, no activities, no season."""
    d = DESTINATIONS[destination]
    t = Trip(from_city=origin, destination=destination, nights=d["default_nights"], adults=2)
    t.split = default_split(d, d["default_nights"])
    options = flights_for(t)
    if options:
        t.flight_id = min(options, key=lambda f: f["fare_adult"])["id"]
    for city, _ in stops(t):
        h = min(CITIES[city]["hotels"], key=lambda h: min(r["price"] for r in h["rooms"]))
        r = min(h["rooms"], key=lambda r: r["price"])
        t.hotels[city] = (h["id"], r["id"])
    return price(t).per_person


# ─── The cross-check with the page ────────────────────────────────────────────

_CASE_BRIEFS: list[dict[str, Any]] = [
    {
        "from_city": "DEL",
        "destination": "bali",
        "start_date": "2027-02-12",
        "nights": 6,
        "adults": 2,
        "kids": [],
        "budget": 0,
        "style": "honeymoon",
    },
    {
        "from_city": "BOM",
        "destination": "kerala",
        "start_date": "2026-12-18",
        "nights": 5,
        "adults": 2,
        "kids": [6, 1],
        "budget": 150000,
        "style": "family",
    },
    {
        "from_city": "BLR",
        "destination": "thailand",
        "start_date": "2027-01-15",
        "nights": 7,
        "adults": 3,
        "kids": [10],
        "budget": 0,
        "style": "adventure",
    },
    {
        "from_city": "AMD",
        "destination": "rajasthan",
        "start_date": "2027-03-05",
        "nights": 6,
        "adults": 4,
        "kids": [],
        "budget": 0,
        "style": "relaxed",
    },
    {
        "from_city": "CCU",
        "destination": "maldives",
        "start_date": "2027-04-09",
        "nights": 4,
        "adults": 2,
        "kids": [],
        "budget": 0,
        "style": "honeymoon",
    },
    {
        "from_city": "PNQ",
        "destination": "switzerland",
        "start_date": "2027-06-11",
        "nights": 7,
        "adults": 2,
        "kids": [8, 11],
        "budget": 0,
        "style": "family",
    },
    {
        "from_city": "HYD",
        "destination": "dubai",
        "start_date": "2026-12-11",
        "nights": 4,
        "adults": 5,
        "kids": [3, 0],
        "budget": 300000,
        "style": "family",
    },
    {
        "from_city": "MAA",
        "destination": "singapore",
        "start_date": "2027-05-14",
        "nights": 5,
        "adults": 1,
        "kids": [],
        "budget": 0,
        "style": "adventure",
    },
    {
        "from_city": "DEL",
        "destination": "goa",
        "start_date": "2027-01-08",
        "nights": 6,
        "adults": 2,
        "kids": [],
        "budget": 0,
        "style": "relaxed",
    },
]


def _case(brief: dict[str, Any]) -> dict[str, Any]:
    t = Trip.from_json(brief)
    t.split = default_split(DESTINATIONS[brief["destination"]], brief["nights"])
    built = build_package(t)
    return {
        "brief": brief,
        "package": built.to_json(),
        "price": price(built).to_json(),
        "transfers": [{"id": leg.id, "price": leg.price} for leg in transfer_legs(built)],
        "days": [
            {
                "n": d.n,
                "city": d.city,
                "kind": d.kind,
                "date": d.date.isoformat() if d.date else None,
            }
            for d in days(built)
        ],
        "month_start": {
            m: month_start(int(m), date(2026, 11, 18)).isoformat() for m in ("1", "6", "11", "12")
        },
    }


def cases() -> dict[str, Any]:
    return {
        "note": "Written by backend/engine.py write_cases(); month_start is computed for today = 2026-11-18.",
        "cases": [_case(b) for b in _CASE_BRIEFS],
        "from_prices": {
            o: {d: from_price(d, o) for d in DESTINATIONS} for o in ("DEL", "BOM", "BLR")
        },
    }


def write_cases() -> None:
    CASES.write_text(json.dumps(cases(), ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    write_cases()
