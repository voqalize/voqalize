"""What the pharmacist did, named — the browser→brain half of the screen contract.

The other direction is the :class:`~voqalize.sdk.Action` classes in ``brain.py``:
each a declared shape whose wire name comes off the class name, whose payload is
validated at the call site, and whose TypeScript twin is generated rather than
written. :class:`~voqalize.sdk.AppEvent` is that, mirrored — so ``on_rtvi``
narrows on a *type* instead of reading ``msg.data["t"]`` and hoping about
``msg.data["d"]``. Both halves of ``actions.gen.ts`` come out of this one union
and that one, together.

Why it had to exist. The shape this replaced carried a whole cart, debounced, so
neither end ever *named* a change: the mirror diffed its old picture against the
new one and inferred which act produced the difference. Every inference is a place
the two pictures can part company, and the best the model could then be told is
that *something* moved. ``li3 quantity set to 5`` needs no diff, no inference, and
no round trip to interpret.

Nothing arrives behind these events. There is no snapshot and no repair channel,
so **completeness** is the property to hold: a gesture missing from this union is a
gesture the brain never learns about, which shows up as a gap in a log rather than
being quietly reconciled a beat later by a cart nobody reads. Adding one is adding
a class here and a name to :data:`DESK_EVENTS`; the browser's half regenerates.

Nothing here decides what the brain *does* with an event. Declaring is this
module's whole job — the SDK does the parsing; injecting into the model's context, moving the mirror, or
ignoring it outright is the brain's call, one event at a time.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from voqalize.sdk import AppEvent, AppEvents

__all__ = [
    "DESK_EVENTS",
    "DeskEvent",
    "FamilyChosen",
    "OrderConfirmed",
    "QuantitySet",
    "QuestionAnswered",
    "RowAdded",
    "RowRemoved",
    "SkuChosen",
]


class SkuChosen(AppEvent):
    """He pointed at one medicine for this row — off the pills, out of the variant
    strip, or out of the search panel. ``via`` is not decoration: "picked it off
    the options I offered" and "swapped the variant on a row that was already
    settled" are different things to say back to him."""

    item_id: str
    sku_code: str
    sku_name: str = ""
    via: Literal["pill", "variant", "search"] = "pill"


class RowAdded(AppEvent):
    """He added a row himself, out of the search panel — a row the mirror has
    never seen and every tool would otherwise be blind to."""

    item_id: str
    sku_code: str
    sku_name: str = ""
    query: str = ""
    quantity: int | None = None


class RowRemoved(AppEvent):
    """He deleted a row. Carries its name because after this the mirror has
    nothing left to look the name up from."""

    item_id: str
    spoken_text: str = ""


class QuestionAnswered(AppEvent):
    """He answered the question on the row by tapping a pill. ``question`` is what
    was asked, so a model about to ask it again can see that it is spent."""

    item_id: str
    question: str = ""
    answer: str = ""
    surviving_codes: list[str] = Field(default_factory=list)


class FamilyChosen(AppEvent):
    """He picked a brand card. Not the same act as answering a question — nobody
    asked — and the next thing to say differs accordingly."""

    item_id: str
    family: str
    surviving_codes: list[str] = Field(default_factory=list)


class QuantitySet(AppEvent):
    """He typed or stepped a quantity."""

    item_id: str
    quantity: int


class OrderConfirmed(AppEvent):
    """He tapped Confirm. The call is over bar the goodbye."""

    order_no: str = ""
    item_count: int = 0
    total_mrp: float = 0.0


#: One thing the pharmacist did. A union rather than a base class, so a ``match``
#: over it is checked for exhaustiveness — a gesture added here and not handled in
#: :meth:`OrderDesk.apply_event` fails pyright rather than the call.
type DeskEvent = (
    SkuChosen
    | RowAdded
    | RowRemoved
    | QuestionAnswered
    | FamilyChosen
    | QuantitySet
    | OrderConfirmed
)

#: The vocabulary this brain speaks, and the only thing that reads it. Scoped
#: rather than global because the demos umbrella runs every brain in one process,
#: and another one is entitled to its own ``RowAdded``.
DESK_EVENTS = AppEvents[DeskEvent](
    SkuChosen,
    RowAdded,
    RowRemoved,
    QuestionAnswered,
    FamilyChosen,
    QuantitySet,
    OrderConfirmed,
)
