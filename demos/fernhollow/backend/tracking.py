"""The account's orders page: where each sample order is, in plain words, and
the delivery days it can still move to.

The orders are the ``demo_orders.json`` entries that carry a ``tracking``
block (authored sample data: a stage, a timeline of events in days ago, the
booked delivery slot and the slots it may move to). Days are relative, so the
page reads right whenever the demo runs; the weekday is worked out from today.
These are the only delivery days in the demo — nothing here is promised for
any other order.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from .catalog import DEMO

__all__ = [
    "TRACKED",
    "Slot",
    "Tracked",
    "day_words",
    "find_tracked",
    "plain_status",
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


def _load() -> dict[str, Tracked]:
    raw = json.loads((DEMO / "data" / "demo_orders.json").read_text())
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
            lines=tuple(
                f"{line['title']} ({line['variant']})"
                + (f", {line['qty']} of them" if line["qty"] > 1 else "")
                for line in o["lines"]
            ),
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


def find_tracked(text: str) -> Tracked | None:
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits and (t := TRACKED.get(f"FH-{digits}")) is not None:
        return t
    return None


def plain_status(t: Tracked, today: date | None = None) -> str:
    """Where the parcel is, in a sentence a person would say."""
    match t.stage:
        case "packed":
            when = t.slot.words(today) if t.slot else "on a day we agree with you"
            return f"It's packed at our warehouse and waiting for its van; delivery is booked for {when}."
        case "out_for_delivery":
            stops = f" There are {t.stops_before} stops before yours." if t.stops_before else ""
            when = f" It's due {t.slot.hours}." if t.slot else ""
            return f"It's on the van today.{when}{stops}"
        case "delivered":
            ago = t.delivered_days_ago or 0
            return f"It was delivered {ago} day{'s' if ago != 1 else ''} ago and signed for at the front door."
        case _:
            return "It's being prepared."
