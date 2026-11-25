"""Hotel Belmonte's data and rules, for the brain: ``data/hotel.json`` and what
follows from it (prices with their charges, the spa's free times, which room a
guest's preferences get, a meeting quote). The app implements the same rules in
``frontend/src/lib/rules.ts``; ``data/rules_cases.json`` (written by
:func:`write_cases`) holds both to one answer.

Money is US dollars, rounded half up to the cent the same way on both sides
(:func:`cents`). Times are ``HH:MM`` on a 24 hour clock, dates ``YYYY-MM-DD``.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA: dict[str, Any] = json.loads((ROOT / "data" / "hotel.json").read_text())

HOTEL: dict[str, Any] = DATA["hotel"]
GUEST: dict[str, Any] = DATA["guest"]
SCENARIOS: dict[str, Any] = DATA["scenarios"]
CHECKIN: dict[str, Any] = DATA["checkin"]
LATE: dict[str, Any] = DATA["late_checkout"]
GROUPS: dict[str, Any] = DATA["option_groups"]
DINING: dict[str, Any] = DATA["dining"]
BAR: dict[str, Any] = DATA["bar"]
SPA: dict[str, Any] = DATA["spa"]
PLACES: dict[str, Any] = {p["id"]: p for p in DATA["places"]}
ACTIVITIES: dict[str, Any] = {a["id"]: a for a in DATA["activities"]}
MEETINGS: dict[str, Any] = DATA["meetings"]
ROOMS: dict[str, Any] = {r["id"]: r for r in MEETINGS["rooms"]}
VISITORS: dict[str, Any] = DATA["visitors"]
REQUESTS: dict[str, Any] = DATA["requests"]
INFO: dict[str, Any] = {s["id"]: s for s in DATA["info"]}
TREATMENTS: dict[str, Any] = {t["id"]: t for t in SPA["treatments"]}
THERAPISTS: dict[str, Any] = {t["id"]: t for t in SPA["therapists"]}

#: Every menu item by outlet, with the section it is in.
ITEMS: dict[str, dict[str, dict[str, Any]]] = {
    "dining": {i["id"]: {**i, "section": p["id"]} for p in DINING["periods"] for i in p["items"]},
    "bar": {i["id"]: {**i, "section": s["id"]} for s in BAR["sections"] for i in s["items"]},
}
SECTIONS: dict[str, dict[str, Any]] = {
    "dining": {p["id"]: p for p in DINING["periods"]},
    "bar": {s["id"]: s for s in BAR["sections"]},
}

SPA_CLOSE = "20:00"


# ─── Formats ─────────────────────────────────────────────────────────────────


def cents(x: float) -> float:
    """Round half up to the cent (the app's ``cents`` does the same)."""
    return math.floor(x * 100 + 0.5 + 1e-9) / 100


def money(x: float) -> str:
    """$1,234.50; a credit as -$389.00."""
    sign = "-" if x < 0 else ""
    return f"{sign}${abs(cents(x)):,.2f}"


def minutes(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def hhmm(n: int) -> str:
    return f"{n // 60:02d}:{n % 60:02d}"


def clock(t: str) -> str:
    """14:40 -> 2:40 PM; 12:00 -> 12:00 PM; 24:00 -> midnight."""
    n = minutes(t)
    if n % (24 * 60) == 0 and n:
        return "midnight"
    h, m = divmod(n % (24 * 60), 60)
    suffix = "AM" if h < 12 else "PM"
    return f"{(h % 12) or 12}:{m:02d} {suffix}"


_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def day(d: str) -> str:
    """2026-11-25 -> Wed, Nov 25."""
    x = date.fromisoformat(d)
    return f"{_DAYS[x.weekday()]}, {_MONTHS[x.month - 1]} {x.day}"


def dates_between(a: str, b: str) -> list[str]:
    """Each date from a to b, both included."""
    x, y = date.fromisoformat(a), date.fromisoformat(b)
    return [date.fromordinal(n).isoformat() for n in range(x.toordinal(), y.toordinal() + 1)]


# ─── The stay ────────────────────────────────────────────────────────────────


@dataclass
class Stay:
    """One scenario's clock and reservation."""

    scenario: str
    today: str
    now: str
    arrive: str
    depart: str

    @classmethod
    def of(cls, scenario: str) -> Stay:
        s = SCENARIOS.get(scenario) or SCENARIOS["arrival"]
        return cls(
            scenario=scenario if scenario in SCENARIOS else "arrival",
            today=s["today"],
            now=s["now"],
            arrive=s["arrive"],
            depart=s["depart"],
        )

    @property
    def nights(self) -> int:
        return (
            date.fromisoformat(self.depart).toordinal()
            - date.fromisoformat(self.arrive).toordinal()
        )

    def bookable_dates(self) -> list[str]:
        """Today through the departure day."""
        return dates_between(self.today, self.depart)

    def later(self, d: str, t: str, lead_min: int = 30) -> bool:
        """Is ``t`` on ``d`` far enough ahead to book."""
        if d > self.today:
            return True
        return d == self.today and minutes(t) >= minutes(self.now) + lead_min


# ─── Check-in ────────────────────────────────────────────────────────────────


def assign_room(floor: str | None, bed: str | None, quiet: bool | None) -> dict[str, Any]:
    """The first room of the reserved type that fits the preferences; when none
    does, quiet is let go, then the floor."""
    rooms: list[dict[str, Any]] = CHECKIN["rooms"]

    def fits(r: dict[str, Any], f: str | None, q: bool | None) -> bool:
        if (bed or "king") != r["bed"]:
            return False
        if f == "high" and r["floor"] < 10:
            return False
        if f == "low" and r["floor"] > 6:
            return False
        return not (q and not r["quiet"])

    for f, q in ((floor, quiet), (floor, None), (None, None)):
        hit = next((r for r in rooms if fits(r, f, q)), None)
        if hit is not None:
            return hit
    return rooms[0]


def arrival_minutes(arrival: str, now: str) -> int:
    return minutes(now) if arrival == "now" else minutes(arrival)


def early_offered(arrival: str | None, now: str) -> bool:
    """Arriving before standard check-in."""
    return arrival is not None and arrival_minutes(arrival, now) < minutes(
        CHECKIN["early"]["before"]
    )


def ready_by(room: dict[str, Any], now: str) -> int:
    return minutes(now) if room["ready"] == "now" else minutes(room["ready"])


def early_available(room: dict[str, Any], arrival: str, now: str) -> bool:
    """The room is clean by the time they arrive."""
    return ready_by(room, now) <= arrival_minutes(arrival, now)


# ─── Menus and orders ────────────────────────────────────────────────────────


def groups_of(item: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """An item's option groups, with a size group for a wine sold by the glass."""
    out = [(g, GROUPS[g]) for g in item.get("options", [])]
    if "bottle" in item:
        out.insert(
            0,
            (
                "size",
                {
                    "label": "Size",
                    "pick": True,
                    "choices": [["glass", "Glass", 0], ["bottle", "Bottle", 0]],
                },
            ),
        )
    return out


@dataclass
class Line:
    """One order line."""

    item_id: str
    qty: int
    choices: list[str] = field(default_factory=list)
    note: str = ""


def unit_price(outlet: str, line: Line) -> float:
    item = ITEMS[outlet][line.item_id]
    base = item["bottle"] if "size:bottle" in line.choices else item["price"]
    extra = 0.0
    for gid, g in groups_of(item):
        for cid, _, add in g["choices"]:
            if f"{gid}:{cid}" in line.choices:
                extra += add
    return cents(base + extra)


def choice_labels(outlet: str, line: Line) -> list[str]:
    item = ITEMS[outlet][line.item_id]
    out: list[str] = []
    for gid, g in groups_of(item):
        for cid, label, _ in g["choices"]:
            if f"{gid}:{cid}" in line.choices:
                out.append(label)
    return out


def check_choices(outlet: str, item_id: str, choices: list[str]) -> tuple[list[str], list[str]]:
    """(the choices as group:choice ids, what is wrong or missing). A choice may
    be given by its id or its label; a pick group with none is missing."""
    item = ITEMS[outlet][item_id]
    got: list[str] = []
    problems: list[str] = []
    for raw in choices:
        want = raw.strip().lower()
        if ":" in want:
            g, _, c = want.partition(":")
        else:
            g, c = "", want
        hit = None
        for gid, grp in groups_of(item):
            if g and g != gid:
                continue
            for cid, label, _ in grp["choices"]:
                if c in (cid, label.lower()) or c.replace(" ", "_") == cid:
                    hit = f"{gid}:{cid}"
                    break
            if hit:
                break
        if hit is None:
            problems.append(f"'{raw}' is not an option for {item['name']}")
        elif hit not in got:
            got.append(hit)
    for gid, grp in groups_of(item):
        mine = [x for x in got if x.startswith(gid + ":")]
        if grp["pick"] and not mine:
            names = ", ".join(lbl for _, lbl, _ in grp["choices"])
            problems.append(f"needs a choice of {grp['label'].lower()}: {names}")
        if grp["pick"] and len(mine) > 1:
            problems.append(f"only one {grp['label'].lower()}")
    return got, problems


@dataclass
class Totals:
    subtotal: float
    service: float
    delivery: float
    tax: float
    tip: float
    total: float


def order_totals(outlet: str, lines: list[Line], tip_pct: int) -> Totals:
    """Subtotal, the 20% service charge, delivery, 8.75% tax on the food and
    drink, the guest's tip (a share of the subtotal), and the total."""
    policy = DINING if outlet == "dining" else BAR
    subtotal = cents(sum(unit_price(outlet, ln) * ln.qty for ln in lines))
    service = cents(subtotal * policy["service_charge_pct"] / 100)
    delivery = cents(policy["delivery_fee"]) if lines else 0.0
    tax = cents(subtotal * HOTEL["sales_tax_pct"] / 100)
    tip = cents(subtotal * tip_pct / 100)
    return Totals(
        subtotal, service, delivery, tax, tip, cents(subtotal + service + delivery + tax + tip)
    )


def period_open(period: dict[str, Any], now: str) -> bool:
    a, b, n = minutes(period["from"]), minutes(period["to"]), minutes(now)
    return a <= n < b if a < b else (n >= a or n < b)


def open_period(now: str) -> str:
    return next(p["id"] for p in DINING["periods"] if period_open(p, now))


def alcohol_served(now: str) -> bool:
    """California: no alcohol sold from 2:00 to 6:00 AM."""
    return not (minutes("02:00") <= minutes(now) < minutes("06:00"))


def cabana_open(now: str) -> bool:
    pool = next(b for b in BAR["bars"] if b["id"] == "pool")
    return minutes(pool["from"]) <= minutes(now) < minutes(pool["to"])


# ─── Spa ─────────────────────────────────────────────────────────────────────


def therapists_for(treatment: dict[str, Any], pref: str | None) -> list[str]:
    ids: list[str] = list(treatment["therapists"])
    p = (pref or "any").lower()
    if p in ("female", "woman", "women"):
        return [t for t in ids if THERAPISTS[t]["gender"] == "female"]
    if p in ("male", "man", "men"):
        return [t for t in ids if THERAPISTS[t]["gender"] == "male"]
    if p in THERAPISTS:
        return [t for t in ids if t == p]
    return ids


def _free(th: str, d: str, t: str, mins: int) -> bool:
    sched: list[str] = SPA["schedule"].get(d, {}).get(th, [])
    if t not in sched:
        return False
    if mins > 60 and hhmm(minutes(t) + 60) not in sched:
        return False
    return minutes(t) + mins <= minutes(SPA_CLOSE)


def spa_slots(stay: Stay, treatment_id: str, d: str, pref: str | None) -> list[tuple[str, str]]:
    """(time, therapist id) for each free start, by time then therapist. A
    treatment for two needs two of its therapists free; the first is named."""
    t = TREATMENTS[treatment_id]
    who = therapists_for(t, pref)
    times = sorted({x for th in who for x in SPA["schedule"].get(d, {}).get(th, [])})
    out: list[tuple[str, str]] = []
    for x in times:
        if not stay.later(d, x):
            continue
        free = [th for th in who if _free(th, d, x, t["minutes"])]
        if t.get("for_two"):
            if len(free) >= 2:
                out.append((x, free[0]))
        else:
            out.extend((x, th) for th in free)
    return out


def spa_total(treatment_id: str) -> tuple[float, float, float]:
    """(price, service charge, total)."""
    price = TREATMENTS[treatment_id]["price"]
    service = cents(price * SPA["service_charge_pct"] / 100)
    return price, service, cents(price + service)


def treatment_label(t: dict[str, Any]) -> str:
    return f"{t['name']}, {t['minutes']} min"


# ─── Activities ──────────────────────────────────────────────────────────────


def activity_total(activity_id: str, guests: int) -> float:
    return cents(ACTIVITIES[activity_id]["price"] * guests)


def activity_times(stay: Stay, activity_id: str, d: str) -> list[str]:
    return [t for t in ACTIVITIES[activity_id]["times"] if stay.later(d, t)]


# ─── Meetings ────────────────────────────────────────────────────────────────


def block_span(block: str, start: str | None, hours: int | None) -> tuple[str, str] | None:
    b = next((x for x in MEETINGS["blocks"] if x["id"] == block), None)
    if b is None:
        return None
    if block == "hours":
        if not start or not hours:
            return None
        return start, hhmm(minutes(start) + hours * 60)
    return b["from"], b["to"]


def room_free(room_id: str, d: str, span: tuple[str, str]) -> bool:
    a, b = minutes(span[0]), minutes(span[1])
    if a < minutes(MEETINGS["hours_from"]) or b > minutes(MEETINGS["hours_to"]):
        return False
    taken: list[list[str]] = MEETINGS["taken"].get(room_id, {}).get(d, [])
    return all(b <= minutes(x) or a >= minutes(y) for x, y in taken)


def rooms_for(headcount: int | None, layout: str | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in MEETINGS["rooms"]:
        caps: dict[str, int] = r["layouts"]
        if layout and layout not in caps:
            continue
        cap = caps[layout] if layout else max(caps.values())
        if headcount and cap < headcount:
            continue
        out.append(r)
    return out


@dataclass
class Quote:
    room: float
    catering: float
    fb_service: float
    tax: float
    av: float
    total: float
    hours: int


def meeting_quote(
    room_id: str,
    block: str,
    hours: int | None,
    headcount: int,
    catering: list[str],
    av: list[str],
) -> Quote:
    r = ROOMS[room_id]
    span_hours = {"morning": 4, "afternoon": 4, "full": 9}.get(block, hours or 0)
    rates: dict[str, float] = r["rates"]
    room = (
        rates["half"]
        if block in ("morning", "afternoon")
        else rates["full"]
        if block == "full"
        else rates["hour"] * span_hours
    )
    cat = cents(
        sum(c["per_person"] for c in MEETINGS["catering"] if c["id"] in catering) * headcount
    )
    fb = cents(cat * MEETINGS["fb_service_pct"] / 100)
    tax = cents(cat * HOTEL["sales_tax_pct"] / 100)
    av_total = cents(
        sum(
            a["price"] * (span_hours if a.get("per_hour") else 1)
            for a in MEETINGS["av_addons"]
            if a["id"] in av
        )
    )
    return Quote(room, cat, fb, tax, av_total, cents(room + cat + fb + tax + av_total), span_hours)


# ─── Folio ───────────────────────────────────────────────────────────────────


def balance(lines: list[dict[str, Any]], disputed: set[str]) -> float:
    return cents(sum(ln["amount"] for ln in lines if ln["id"] not in disputed))


# ─── The page's twin ─────────────────────────────────────────────────────────


def write_cases() -> Path:
    """Answers the app's rules must give too (frontend vitest reads this)."""
    stay_a, stay_d = Stay.of("arrival"), Stay.of("departure")
    lines = [
        Line(
            "belmonte-burger",
            2,
            ["burger_cook:medium", "side:sweet_fries", "burger_mods:no_onions"],
        ),
        Line("kale-caesar", 1, ["salad_protein:salmon"]),
        Line("chocolate-cake", 1),
    ]
    drinks = [
        Line("pinot-noir", 1, ["size:bottle"]),
        Line("halcyon-spritz", 2, ["cocktail_mods:double"]),
    ]
    cases: dict[str, Any] = {
        "orders": [
            {
                "outlet": "dining",
                "tip": 15,
                "lines": [ln.__dict__ for ln in lines],
                "totals": order_totals("dining", lines, 15).__dict__,
            },
            {
                "outlet": "bar",
                "tip": 0,
                "lines": [ln.__dict__ for ln in drinks],
                "totals": order_totals("bar", drinks, 0).__dict__,
            },
        ],
        "spa": [
            {
                "scenario": "arrival",
                "treatment": "deep-80",
                "date": stay_a.today,
                "pref": "any",
                "slots": spa_slots(stay_a, "deep-80", stay_a.today, "any"),
            },
            {
                "scenario": "departure",
                "treatment": "couples-80",
                "date": stay_d.today,
                "pref": "any",
                "slots": spa_slots(stay_d, "couples-80", stay_d.today, "any"),
            },
            {
                "scenario": "arrival",
                "treatment": "swedish-50",
                "date": "2026-11-26",
                "pref": "male",
                "slots": spa_slots(stay_a, "swedish-50", "2026-11-26", "male"),
            },
        ],
        "rooms": [
            {"floor": f, "bed": b, "quiet": q, "room": assign_room(f, b, q)["room"]}
            for f, b, q in [
                ("high", "king", True),
                ("low", "king", False),
                ("high", "queens", True),
                (None, None, None),
                ("low", "queens", True),
            ]
        ],
        "quotes": [
            {
                "room": "marina",
                "block": "morning",
                "hours": None,
                "headcount": 30,
                "catering": ["coffee", "lunch"],
                "av": ["mics"],
                "quote": meeting_quote(
                    "marina", "morning", None, 30, ["coffee", "lunch"], ["mics"]
                ).__dict__,
            },
            {
                "room": "cypress",
                "block": "hours",
                "hours": 3,
                "headcount": 10,
                "catering": [],
                "av": ["tech"],
                "quote": meeting_quote("cypress", "hours", 3, 10, [], ["tech"]).__dict__,
            },
        ],
    }
    out = ROOT / "data" / "rules_cases.json"
    out.write_text(json.dumps(cases, indent=1) + "\n")
    return out
