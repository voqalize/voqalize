"""What the visitor's tabs report — the page→brain half of the screen contract.

The other direction is the :class:`~voqalize.sdk.Action` classes in
``brain.py``. These are sent by the extension on www.explora.com and
reservations.explora.com, and they fire for the visitor's own clicks as well as
for Javier's moves, so his picture of their screen is true whoever moved it.

Every move between pages on both hosts is a full page load. A page reports
itself once the call has rejoined on it, so ``page_changed`` is also the signal
that the next page is up and listening.

The site is Explora's, not ours, and it changes without asking. So the nested
shapes are plain models that ignore a field they do not know, while the events
themselves are strict: a new field on a booking step is harmless, a new event is
a change we want to hear about.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk import AppEvent, AppEvents

__all__ = [
    "EXPLORA_EVENTS",
    "CommandFailed",
    "EnquiryFields",
    "EnquirySent",
    "EnquiryState",
    "ExploraEvent",
    "LanguageRequested",
    "NightsOption",
    "PageChanged",
    "RoomOption",
    "StayState",
    "TabInfo",
    "TabsChanged",
    "TwinLookup",
]


class PageChanged(AppEvent):
    """The tab in front loaded a page, or came to the front: what is on it now."""

    site: Literal["site", "reservations"] = "site"
    """``site`` is www.explora.com; ``reservations`` is reservations.explora.com."""
    url: str = ""
    path: str
    title: str = ""
    headings: list[str] = Field(default_factory=list[str])
    """The page's section headings, in order — what a ``show`` cue takes."""
    faqs: list[str] = Field(default_factory=list[str])
    """The questions in the page's accordions — what a ``faq`` cue takes."""
    tabs: list[str] = Field(default_factory=list[str])
    """The labels of the in-page tabs and accordions, which ``show`` opens."""
    links: list[str] = Field(default_factory=list[str])
    """The page's own sub-menu (a lodge's or a destination's), as paths."""


class TabInfo(BaseModel):
    tab_id: str
    url: str = ""
    title: str = ""


class TabsChanged(AppEvent):
    """Every Explora tab the visitor has open, and the one in front: the whole
    list each time."""

    tabs: list[TabInfo] = Field(default_factory=list[TabInfo])
    active: str = ""


class NightsOption(BaseModel):
    nights: int
    label: str = ""


class RoomOption(BaseModel):
    name: str
    text: str = ""


class StayState(AppEvent):
    """Where an availability check on reservations.explora.com stands: the
    calendar for a lodge with its open days, the nights offered for the chosen
    day, or the rooms and rates (step two)."""

    step: Literal["dates", "rooms"]
    hotel_code: str = ""
    hotel: str = ""
    month: str = ""
    """The first month the calendar shows, as it labels it."""
    open_days: list[str] = Field(default_factory=list[str])
    """Arrival days that can be chosen, ``YYYY-MM-DD``, soonest first."""
    date: str = ""
    nights: list[NightsOption] = Field(default_factory=list[NightsOption])
    chosen_nights: int = 0
    rooms: list[RoomOption] = Field(default_factory=list[RoomOption])


class EnquiryFields(BaseModel):
    title: str = ""
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""
    country: str = ""
    message: str = ""


class EnquiryState(AppEvent):
    """The expedition enquiry form: what is filled, what is still empty, and
    whether the visitor has ticked "I'm not a robot"."""

    expedition: str = ""
    expedition_code: str = ""
    filled: EnquiryFields = Field(default_factory=EnquiryFields)
    missing: list[str] = Field(default_factory=list[str])
    captcha: bool = False


class EnquirySent(AppEvent):
    """Send Message was pressed on a complete form: the page is posting it.
    ``by`` says who pressed it."""

    expedition: str = ""
    by: Literal["javier", "visitor"] = "javier"


class CommandFailed(AppEvent):
    """A move Javier sent could not be carried out on the page."""

    command: str
    reason: str = ""


class LanguageRequested(AppEvent):
    """The visitor pressed the other language on the widget's toggle."""

    language: Literal["en", "es"]


class TwinLookup(AppEvent):
    """How the tab found the page a ``navigate`` named in the call's language,
    just before it loaded it: the brain names English paths, and a Spanish
    call loads each page's Spanish twin. Sent so a page that came up in the
    wrong language can be traced to why."""

    path: str
    """The English path the brain named."""
    language: Literal["en", "es"]
    url: str = ""
    """What was loaded."""
    source: Literal["as-is", "here", "cache", "fetch", "hub", "fallback", "timeout"] = "fallback"
    """Already in that language; the page in front's own links; this tab's
    cache; a fetch of the page's head (from the page, or the extension's hub);
    none found (the English page); or not found in time (the English page)."""
    ms: int = 0
    error: str = ""
    """Why the page's head could not be read, when it could not."""


type ExploraEvent = (
    PageChanged
    | TabsChanged
    | StayState
    | EnquiryState
    | EnquirySent
    | CommandFailed
    | LanguageRequested
    | TwinLookup
)

EXPLORA_EVENTS = AppEvents[ExploraEvent](
    PageChanged,
    TabsChanged,
    StayState,
    EnquiryState,
    EnquirySent,
    CommandFailed,
    LanguageRequested,
    TwinLookup,
)
