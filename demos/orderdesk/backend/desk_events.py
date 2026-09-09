"""What the pharmacist did, named — the browser→brain half of the screen contract.

The other direction is six :class:`~voqalize.sdk.Action` classes in ``brain.py``:
each a declared shape whose wire name comes off the class name, whose payload is
validated at the call site, and whose TypeScript twin is generated rather than
written. This is that, mirrored — so ``on_rtvi`` narrows on a *type* instead of
reading ``msg.data["t"]`` and hoping about ``msg.data["d"]``.

Why it had to exist. ``state_sync`` carries a whole cart, so neither end ever
*names* a change: the mirror diffs its old picture against the new one and infers
which act produced the difference. Every inference is a place the two pictures
can part company, and the best the model can then be told is that *something*
moved — which is why it must go and read the screen before it may act. ``li3
quantity set to 5`` needs no diff, no inference, and no round trip to interpret.

``state_sync`` has not gone anywhere; it is the repair channel now. It still
arrives debounced with the whole cart, :meth:`OrderDesk.absorb` still folds it in
— and finds the change already applied, so it reports nothing a second time. An
event dropped on the wire is therefore repaired within 250 ms instead of lost,
which is what makes this safe to try without touching the wire contract at all.

Nothing here decides what the brain *does* with an event. Parsing is this
module's whole job; injecting into the model's context, moving the mirror, or
ignoring it outright is the brain's call, one event at a time.
"""

from __future__ import annotations

import re
from typing import Any, ClassVar, Literal

from loguru import logger
from pydantic import BaseModel, ConfigDict, ValidationError

__all__ = [
    "DeskEvent",
    "FamilyChosen",
    "OrderConfirmed",
    "QuantitySet",
    "QuestionAnswered",
    "RowAdded",
    "RowRemoved",
    "SkuChosen",
    "parse_event",
]

_CAMEL_BOUNDARY = re.compile(r"(.)([A-Z][a-z]+)")
_LOWER_UPPER = re.compile(r"([a-z0-9])([A-Z])")


def _snake_case(name: str) -> str:
    return _LOWER_UPPER.sub(r"\1_\2", _CAMEL_BOUNDARY.sub(r"\1_\2", name)).lower()


_REGISTRY: dict[str, type[DeskEvent]] = {}


class DeskEvent(BaseModel):
    """One thing the pharmacist did to the screen, addressed by row id.

    ``extra="forbid"`` is deliberate on an *inbound* shape: a field this side does
    not know about is a frontend that has moved on, and that is worth a loud log
    rather than a silent read of a stale contract. It is not worth a crash — see
    :func:`parse_event`."""

    #: The wire name, from the class name. Dunder for the same reason
    #: :class:`Action` uses one — a field called ``event`` must stay payload.
    __voqal_event__: ClassVar[str] = "desk_event"

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    def __init_subclass__(cls, name: str | None = None, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.__voqal_event__ = name if name is not None else _snake_case(cls.__name__)
        _REGISTRY[cls.__voqal_event__] = cls


class SkuChosen(DeskEvent):
    """He pointed at one medicine for this row — off the pills, out of the variant
    strip, or out of the search panel. ``via`` is not decoration: "picked it off
    the options I offered" and "swapped the variant on a row that was already
    settled" are different things to say back to him."""

    item_id: str
    sku_code: str
    sku_name: str = ""
    via: Literal["pill", "variant", "search"] = "pill"


class RowAdded(DeskEvent):
    """He added a row himself, out of the search panel — a row the mirror has
    never seen and every tool would otherwise be blind to."""

    item_id: str
    sku_code: str
    sku_name: str = ""
    query: str = ""
    quantity: int | None = None


class RowRemoved(DeskEvent):
    """He deleted a row. Carries its name because after this the mirror has
    nothing left to look the name up from."""

    item_id: str
    spoken_text: str = ""


class QuestionAnswered(DeskEvent):
    """He answered the question on the row by tapping a pill. ``question`` is what
    was asked, so a model about to ask it again can see that it is spent."""

    item_id: str
    question: str = ""
    answer: str = ""
    surviving_codes: list[str] = []


class FamilyChosen(DeskEvent):
    """He picked a brand card. Not the same act as answering a question — nobody
    asked — and the next thing to say differs accordingly."""

    item_id: str
    family: str
    surviving_codes: list[str] = []


class QuantitySet(DeskEvent):
    """He typed or stepped a quantity."""

    item_id: str
    quantity: int


class OrderConfirmed(DeskEvent):
    """He tapped Confirm. The call is over bar the goodbye."""

    order_no: str = ""
    item_count: int = 0
    total_mrp: float = 0.0


def parse_event(kind: str, payload: dict[str, Any]) -> DeskEvent | None:
    """The named event, or ``None`` if this side does not know that name or the
    payload does not fit it.

    Both misses are logged and neither raises. A browser one deploy ahead of this
    brain must degrade to the ``state_sync`` it still sends, not take the call
    down — that is the whole of the backward-compatibility promise."""
    cls = _REGISTRY.get(kind)
    if cls is None:
        return None
    try:
        return cls.model_validate(payload)
    except ValidationError as exc:
        logger.warning("orderdesk: {} did not fit {}: {}", kind, cls.__name__, exc.errors())
        return None
