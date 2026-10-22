"""What the visitor's tabs report — the page→brain half of the screen contract.

The other direction is the :class:`~voqalize.sdk.Action` classes in
``brain.py``. These are sent by the extension on www.santanderarena.cl, and they
fire for the visitor's own clicks as well as for Javier's moves, so his picture
of their screen is true whoever moved it.

The site is Santander Arena's, not ours, and it changes without asking. So the
nested shapes are plain models that ignore a field they do not know, while the
events themselves are strict: a new field on a card is harmless, a new event is
a change we want to hear about.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk import AppEvent, AppEvents

__all__ = [
    "SANTANDER_EVENTS",
    "CommandFailed",
    "LanguageRequested",
    "PageChanged",
    "SantanderEvent",
    "TabInfo",
    "TabsChanged",
    "TicketLink",
]


class TicketLink(BaseModel):
    """A link on the page that leaves the site to buy: tickets, parking, VIP."""

    label: str = ""
    url: str
    near: str = ""
    """The card or page it belongs to: the show's name, usually."""


class PageChanged(AppEvent):
    """The tab in front changed page, or came to the front: what is on it now."""

    url: str = ""
    path: str
    title: str = ""
    kind: Literal["home", "event", "news", "page"] = "page"
    """The home page, one show's page, one news story, or any other page."""
    headings: list[str] = Field(default_factory=list[str])
    """The page's section headings, in order — what a ``show`` cue takes."""
    faqs: list[str] = Field(default_factory=list[str])
    """The FAQ questions on the page — what a ``faq`` cue takes."""
    cards: list[str] = Field(default_factory=list[str])
    """The titles of the cards on the page, carousels included: shows, bars,
    experiences, news."""
    tickets: list[TicketLink] = Field(default_factory=list[TicketLink])
    """Every link on the page to buy tickets, parking or an experience."""


class TabInfo(BaseModel):
    tab_id: str
    url: str = ""
    title: str = ""


class TabsChanged(AppEvent):
    """Every Santander Arena tab the visitor has open, and the one in front:
    the whole list each time."""

    tabs: list[TabInfo] = Field(default_factory=list[TabInfo])
    active: str = ""


class CommandFailed(AppEvent):
    """A move Javier sent could not be carried out on the page."""

    command: str
    reason: str = ""


class LanguageRequested(AppEvent):
    """The visitor pressed the other language on the widget's toggle."""

    language: Literal["en", "es"]


type SantanderEvent = PageChanged | TabsChanged | CommandFailed | LanguageRequested

SANTANDER_EVENTS = AppEvents[SantanderEvent](
    PageChanged,
    TabsChanged,
    CommandFailed,
    LanguageRequested,
)
