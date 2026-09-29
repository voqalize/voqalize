"""What the shopper is looking at — the page→brain half of the screen contract.

The other direction is the :class:`~voqalize.sdk.Action` classes in ``brain.py``.
These are sent by the site adapter the extension injects into Qween's page, and
they fire for the shopper's own clicks as well as for the agent's moves, so the
brain's mirror of the page is true whoever moved it.

Qween's page is theirs, not ours, and it changes without asking us. So the nested
shapes here are plain models that ignore a field they do not know, while the
events themselves are strict: a new field on a card is harmless, a new event is a
change we want to hear about.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk import AppEvent, AppEvents

__all__ = [
    "QWEEN_EVENTS",
    "Card",
    "CommandFailed",
    "DialogClosed",
    "DialogOpened",
    "PageChanged",
    "QweenEvent",
]

PageKind = Literal["home", "catalog", "category", "collection", "product", "page"]


class Card(BaseModel):
    """One product card in a listing, in the order the page shows them."""

    n: int
    """1-based position on the page — what ``highlight_card`` takes."""
    slug: str | None = None
    text: str = ""
    """The card's own words, clipped: its name and price as the page prints them."""


class PageChanged(AppEvent):
    """The route changed — the shopper's click or the agent's move."""

    path: str
    kind: PageKind
    params: dict[str, list[str]] = Field(default_factory=dict)
    dialog_open: bool = False
    slug: str | None = None
    """On a product page, the piece."""
    variant_code: str | None = None
    """On a product page, the variant the URL names, if it names one."""
    name: str | None = None
    """On a product page, the piece's heading."""
    cards: list[Card] = Field(default_factory=list)
    """On any other page, the product cards it has rendered so far."""


class DialogOpened(AppEvent):
    """A dialog opened on Qween's page, whoever opened it, with its own words."""

    title: str | None = None
    text: str = ""


class DialogClosed(AppEvent):
    """The open dialog closed."""


class CommandFailed(AppEvent):
    """A command the agent sent could not be carried out on the page."""

    command: str
    error: str


type QweenEvent = PageChanged | DialogOpened | DialogClosed | CommandFailed

QWEEN_EVENTS = AppEvents[QweenEvent](PageChanged, DialogOpened, DialogClosed, CommandFailed)
