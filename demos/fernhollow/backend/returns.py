"""The returns desk's engine: the demo orders checked against the returns policy.

Orders are fictional orders of real catalog products (``data/demo_orders.json``)
with dates kept as *days ago*, so whether a line can go back holds whenever the
demo runs. The window is the order file's ``return_window_days`` (30, counted
from delivery — the authored returns policy says the same). A line is:

``eligible``
    delivered, and inside the window — with the days left;
``outside_window``
    delivered longer ago than the window — with the days since delivery;
``not_delivered``
    not delivered yet, so nothing can go back yet.

The other half of the policy — unused, complete, in original condition — is the
shopper's to state on the form (``condition``), never assumed here.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from .catalog import CATALOG, DEMO

__all__ = [
    "CONDITIONS",
    "ORDERS",
    "REASONS",
    "RESOLUTIONS",
    "WINDOW_DAYS",
    "Eligibility",
    "Line",
    "Order",
    "exchange_options",
    "find_order",
    "normalise_number",
    "order_from",
]

ORDERS_PATH = DEMO / "data" / "demo_orders.json"

Eligibility = Literal["eligible", "outside_window", "not_delivered"]


@dataclass(frozen=True)
class Line:
    product_id: str
    variant_id: str
    title: str
    variant: str
    qty: int
    unit_price: float
    status: Eligibility
    days_since_delivery: int | None
    days_left: int | None


@dataclass(frozen=True)
class Order:
    number: str
    name: str
    status: str
    delivered_days_ago: int | None
    lines: tuple[Line, ...]
    total: float
    placed_days_ago: int = 0
    source: Literal["placed", "known", "demo"] = "demo"

    @property
    def eligible(self) -> tuple[Line, ...]:
        return tuple(line for line in self.lines if line.status == "eligible")


_RAW: dict[str, Any] = json.loads(ORDERS_PATH.read_text())
WINDOW_DAYS: int = int(_RAW["return_window_days"])


def _status(order: dict[str, Any]) -> tuple[Eligibility, int | None, int | None]:
    delivered = order.get("delivered_days_ago")
    if order.get("status") != "delivered" or delivered is None:
        return "not_delivered", None, None
    days = int(delivered)
    if days > WINDOW_DAYS:
        return "outside_window", days, None
    return "eligible", days, WINDOW_DAYS - days


def order_from(o: dict[str, Any], source: Literal["placed", "known", "demo"] = "demo") -> Order:
    """One order in the shared shape (demo file, the page's ``orders_known``,
    or one Emily placed), checked against the window."""
    status, since, left = _status(o)
    lines = tuple(
        Line(
            product_id=line["product_id"],
            variant_id=str(line.get("variant_id") or ""),
            title=line.get("title", ""),
            variant=line.get("variant", ""),
            qty=int(line.get("qty", 1)),
            unit_price=float(line.get("unit_price", 0)),
            status=status,
            days_since_delivery=since,
            days_left=left,
        )
        for line in o.get("lines", [])
    )
    return Order(
        number=str(o["number"]),
        name=o.get("name", ""),
        status=o.get("status", ""),
        delivered_days_ago=o.get("delivered_days_ago"),
        lines=lines,
        total=float(o.get("total", 0)),
        placed_days_ago=int(o.get("placed_days_ago") or 0),
        source=source,
    )


def _load() -> dict[str, Order]:
    return {o["number"]: order_from(o) for o in _RAW["orders"]}


ORDERS: dict[str, Order] = _load()


def normalise_number(text: str) -> str | None:
    """``FH-20418`` from "fh 20418", "20418", "F H two oh four one eight" is the
    model's job; this takes whatever digits it heard."""
    digits = re.sub(r"\D", "", text)
    return f"FH-{digits}" if digits else None


_NEWEST = re.compile(
    r"\b(last|latest|newest|recent|most recent|just placed|just made|just ordered|i placed)\b"
)


def find_order(
    text: str, *, placed: Sequence[Order] = (), known: Sequence[Order] = ()
) -> Order | None:
    """The order ``text`` names: orders placed this session first, then the
    ones the page knows, then the demo orders. "My last order" / "the one I
    just placed" is the newest of the shopper's own."""
    number = normalise_number(text)
    if number is None:
        if _NEWEST.search(text.lower()):
            if placed:
                return placed[-1]
            if known:
                return min(known, key=lambda o: o.placed_days_ago)
        return None
    for o in (*reversed(placed), *known):
        if o.number == number:
            return o
    return ORDERS.get(number)


# ─── The return form's values (the contract's names) ──────────────────────────

REASONS = ("changed_mind", "doesnt_suit_room", "arrived_damaged", "wrong_item", "not_as_expected")
CONDITIONS = ("unused_in_packaging", "unused_unpacked", "damaged_on_arrival")
RESOLUTIONS = ("refund", "exchange", "store_credit")
COLLECTIONS = ("pickup", "drop_off")
WINDOWS = ("weekday_morning", "weekday_afternoon", "saturday")


def exchange_options(product_id: str, current_variant: str | None = None) -> list[tuple[str, str]]:
    """The product's other real option values, as (variant id, value)."""
    p = CATALOG.get(product_id)
    if p is None:
        return []
    return [(v.id, v.value) for v in p.variants if v.id != current_variant]
