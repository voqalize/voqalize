"""The sales calendar on ``/book-demo``: which 30-minute slots exist, and which
are already taken.

Authored in ``content/site.json`` (``calendar``): each rep's weekly hours in
IST, the holidays, and how many business days are shown. The days are the next
``business_days`` weekdays after today (IST), skipping holidays. A slot is taken
by the rule written in ``calendar.taken_rule``; the page's twin is
``frontend/src/lib/calendar.ts`` and ``content/calendar_cases.json`` pins both.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

from .data import CALENDAR

IST = timezone(timedelta(hours=5, minutes=30))
_EPOCH = date(1970, 1, 1)
_DAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
REPS: list[dict[str, Any]] = list(CALENDAR["reps"])
REP_BY_ID: dict[str, dict[str, Any]] = {r["id"]: r for r in REPS}
HOLIDAYS = frozenset(CALENDAR["holidays"])


@dataclass(frozen=True)
class Slot:
    id: str
    day: date
    time: str  # "HH:MM", IST
    rep: str
    taken: bool

    @property
    def rep_name(self) -> str:
        return str(REP_BY_ID[self.rep]["name"])


def today_ist(now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(IST).date()


def business_days(today: date) -> list[date]:
    """The next ``business_days`` weekdays after ``today``, holidays skipped."""
    out: list[date] = []
    d = today
    while len(out) < int(CALENDAR["business_days"]):
        d += timedelta(days=1)
        if d.weekday() < 5 and d.isoformat() not in HOLIDAYS:
            out.append(d)
    return out


def minutes(time: str) -> int:
    h, m = time.split(":")
    return int(h) * 60 + int(m)


def is_taken(day: date, time: str, rep_index: int) -> bool:
    epoch_day = (day - _EPOCH).days
    return (epoch_day * 3 + (minutes(time) // 30) * 7 + rep_index * 11) % 5 == 0


def slot_id(day: date, time: str, rep: str) -> str:
    return f"{day.isoformat()}-{time.replace(':', '')}-{rep}"


def slots_on(day: date) -> list[Slot]:
    """Every slot that day, by time then rep order."""
    key = _DAY_KEYS[day.weekday()]
    out: list[Slot] = []
    for i, rep in enumerate(REPS):
        for t in rep["hours"].get(key, []):
            out.append(Slot(slot_id(day, t, rep["id"]), day, t, rep["id"], is_taken(day, t, i)))
    return sorted(out, key=lambda s: (minutes(s.time), REPS.index(REP_BY_ID[s.rep])))


def parse_slot(sid: str) -> Slot | None:
    """A slot id back into its slot, or None when it is not one the calendar has."""
    try:
        y, mo, d, hhmm, rep = sid.strip().split("-", 4)
        day = date(int(y), int(mo), int(d))
    except ValueError:
        return None
    return next((s for s in slots_on(day) if s.id == f"{day.isoformat()}-{hhmm}-{rep}"), None)


def reference(slot: Slot) -> str:
    rep = REP_BY_ID[slot.rep]
    return f"TKD-{slot.day.strftime('%d%m')}-{slot.time.replace(':', '')}-{rep['initials']}"


def day_label(d: date) -> str:
    """``Thu 19 Nov 2026``: the page's DD MMM YYYY with the weekday."""
    return d.strftime("%a %d %b %Y")


def spoken_day(d: date) -> str:
    return f"{d.strftime('%A')} {d.day} {d.strftime('%B')}"


def spoken_time(time: str) -> str:
    h, m = (int(x) for x in time.split(":"))
    suffix = "am" if h < 12 else "pm"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {suffix}" if m else f"{h12} {suffix}"


_DAYS_HI = ("सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार")
_MONTHS_HI = (
    "जनवरी",
    "फ़रवरी",
    "मार्च",
    "अप्रैल",
    "मई",
    "जून",
    "जुलाई",
    "अगस्त",
    "सितंबर",
    "अक्टूबर",
    "नवंबर",
    "दिसंबर",
)


def spoken_day_hi(d: date) -> str:
    """The day as said in Hindi: "बुधवार 25 नवंबर"."""
    return f"{_DAYS_HI[d.weekday()]} {d.day} {_MONTHS_HI[d.month - 1]}"


def spoken_time_hi(time: str) -> str:
    """The time as said in Hindi: "सुबह 9:30 बजे", "दोपहर 2 बजे"."""
    h, m = (int(x) for x in time.split(":"))
    part = "सुबह" if h < 12 else "दोपहर" if h < 16 else "शाम"
    h12 = h % 12 or 12
    return f"{part} {h12}:{m:02d} बजे" if m else f"{part} {h12} बजे"


def part_of(time: str) -> str:
    m = minutes(time)
    return "morning" if m < 12 * 60 else "afternoon" if m < 16 * 60 else "evening"
