"""The account's orders page: every order of the signed-in demo account, where
it is in plain words, and what its status allows (CONTRACT.md, v6).

Every ``demo_orders.json`` order carries a ``tracking`` block (authored sample
data: a stage, a timeline of events in days ago, the booked delivery slot and
the slots it may move to). Days are relative, so the page reads right whenever
the demo runs; the weekday is worked out from today. An order placed in this
browser is packed, booked into the file's ``placed_order`` template. These are
the only delivery days in the demo.

What a status allows (the store's policy, ``content/policies.json``):

- packed: change the delivery day (to an offered slot) or cancel the order;
- on the way (``on_the_way`` or ``out_for_delivery``): ask for an earlier
  delivery — a request, never a promise; no cancelling, no new day;
- delivered: start a return, within the 30-day window.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Literal

from .catalog import DEMO

#: What a status allows, grouped: see the module docstring.
Group = Literal["packed", "on_the_way", "delivered", "cancelled"]

__all__ = [
    "PLACED_SLOTS",
    "TRACKED",
    "Group",
    "Slot",
    "Tracked",
    "day_words",
    "find_tracked",
    "group_of",
    "plain_status",
    "tracked_from_known",
]


@dataclass(frozen=True)
class Slot:
    id: str
    days_from_now: int
    window: str
    hours: str

    def words(self, today: date | None = None) -> str:
        return f"{day_words(self.days_from_now, today)} {self.window}, {self.hours}"


@dataclass(frozen=True)
class Tracked:
    number: str
    stage: str
    lines: tuple[str, ...]
    events: tuple[dict[str, Any], ...]
    slot: Slot | None
    slots: tuple[Slot, ...]
    can_reschedule: bool
    why_not: str
    stops_before: int | None
    delivered_days_ago: int | None
    total: float


def day_words(days: int, today: date | None = None) -> str:
    """ "today", "tomorrow", "yesterday", or the weekday and date."""
    if days == 0:
        return "today"
    if days == 1:
        return "tomorrow"
    if days == -1:
        return "yesterday"
    d = (today or date.today()) + timedelta(days=days)
    return f"{d.strftime('%A')} {d.day} {d.strftime('%B')}"


def _slot(raw: dict[str, Any] | None) -> Slot | None:
    if not raw or "days_from_now" not in raw:
        return None
    return Slot(
        id=str(raw.get("id") or f"d{raw['days_from_now']}-{raw['window']}"),
        days_from_now=int(raw["days_from_now"]),
        window=str(raw["window"]),
        hours=str(raw["hours"]),
    )


_RAW: dict[str, Any] = json.loads((DEMO / "data" / "demo_orders.json").read_text())


def _lines(lines: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(
        f"{line['title']} ({line['variant']})"
        + (f", {line['qty']} of them" if int(line.get("qty", 1)) > 1 else "")
        for line in lines
    )


def _load() -> dict[str, Tracked]:
    raw = _RAW
    out: dict[str, Tracked] = {}
    for o in raw["orders"]:
        t = o.get("tracking")
        if not t:
            continue
        slots = tuple(s for s in (_slot(x) for x in t.get("slots", [])) if s is not None)
        booked = t.get("delivery") or {}
        slot = next((s for s in slots if s.id == booked.get("slot")), None) or _slot(booked)
        out[o["number"]] = Tracked(
            number=o["number"],
            stage=t["stage"],
            lines=_lines(o["lines"]),
            events=tuple(t.get("events", [])),
            slot=slot,
            slots=slots,
            can_reschedule=bool(t.get("can_reschedule")),
            why_not=str(t.get("why_not") or ""),
            stops_before=booked.get("stops_before"),
            delivered_days_ago=o.get("delivered_days_ago"),
            total=float(o["total"]),
        )
    return out


TRACKED: dict[str, Tracked] = _load()

_TEMPLATE: dict[str, Any] = _RAW.get("placed_order") or {}
#: The authored slots an order placed in this browser can move to.
PLACED_SLOTS: tuple[Slot, ...] = tuple(
    s for s in (_slot(x) for x in _TEMPLATE.get("slots", [])) if s is not None
)


def tracked_from_known(
    number: str, lines: list[dict[str, Any]], total: float, placed_days_ago: int
) -> Tracked:
    """An order placed in this browser: packed, booked into the template slot."""
    booked = next((s for s in PLACED_SLOTS if s.id == _TEMPLATE.get("booked")), None)
    return Tracked(
        number=number,
        stage="packed",
        lines=_lines(lines),
        events=(
            {"stage": "ordered", "days_ago": placed_days_ago, "time": "", "text": "Order placed"},
        ),
        slot=booked,
        slots=PLACED_SLOTS,
        can_reschedule=True,
        why_not="",
        stops_before=None,
        delivered_days_ago=None,
        total=total,
    )


def group_of(t: Tracked, cancelled: bool = False) -> Group:
    if cancelled:
        return "cancelled"
    if t.stage == "packed":
        return "packed"
    if t.stage == "delivered":
        return "delivered"
    return "on_the_way"


def find_tracked(text: str, extra: dict[str, Tracked] | None = None) -> Tracked | None:
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return None
    number = f"FH-{digits}"
    return (extra or {}).get(number) or TRACKED.get(number)


def plain_status(t: Tracked, today: date | None = None) -> str:
    """Where the parcel is, in a sentence a person would say."""
    match t.stage:
        case "packed":
            when = t.slot.words(today) if t.slot else "on a day we agree with you"
            return f"It's packed at our warehouse and waiting for its van; delivery is booked for {when}."
        case "on_the_way":
            when = f"; it's due {t.slot.words(today)}" if t.slot else ""
            return f"It has left our warehouse and is on its way{when}."
        case "out_for_delivery":
            stops = f" There are {t.stops_before} stops before yours." if t.stops_before else ""
            when = f" It's due {t.slot.hours}." if t.slot else ""
            return f"It's on the van today.{when}{stops}"
        case "delivered":
            ago = t.delivered_days_ago or 0
            return f"It was delivered {ago} day{'s' if ago != 1 else ''} ago and signed for at the front door."
        case _:
            return "It's being prepared."
