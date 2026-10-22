"""What the visitor's tabs report — the page→brain half of the screen contract.

The other direction is the :class:`~voqalize.sdk.Action` classes in
``brain.py``. These are sent by the extension on saintgeorge.cl, and they fire
for the visitor's own clicks as well as for Javier's moves, so his picture of
their screen is true whoever moved it.

Three of them carry what changes during the year, read in the visitor's own
browser while the call is on: the fees and the admission status off the
admission page (:class:`FeesRead`), and the coming events off the school's
public calendar (:class:`EventsRead`). The brain never fetches the site itself.

The site is the school's, not ours, and it changes without asking. So the
nested shapes are plain models that ignore a field they do not know, while the
events themselves are strict: a new field on a link is harmless, a new event is
a change we want to hear about.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk import AppEvent, AppEvents

__all__ = [
    "SAINT_GEORGE_EVENTS",
    "CalendarEvent",
    "CommandDone",
    "CommandFailed",
    "ContactUsed",
    "EventsRead",
    "Fee",
    "FeesRead",
    "LanguageRequested",
    "PageChanged",
    "PageLink",
    "SaintGeorgeEvent",
    "TabInfo",
    "TabsChanged",
]


class PageLink(BaseModel):
    """A link on the page that opens something of its own: a PDF, the
    musical's tickets, a portal."""

    label: str = ""
    url: str
    near: str = ""
    """The heading or section it sits under."""


class PageChanged(AppEvent):
    """The tab in front changed page, or came to the front: what is on it now."""

    url: str = ""
    path: str
    title: str = ""
    kind: Literal["home", "unit", "admission", "page"] = "page"
    """The home page, a unit's page (``/unidad/…``), an admission page, or any
    other page."""
    headings: list[str] = Field(default_factory=list[str])
    """The page's section headings, in order — what a ``show`` cue takes."""
    faqs: list[str] = Field(default_factory=list[str])
    """The accordions on the page, by their buttons' words — what a ``faq`` cue
    opens."""
    cards: list[str] = Field(default_factory=list[str])
    """The titles of the cards on the page: the units, the newsletters."""
    links: list[PageLink] = Field(default_factory=list[PageLink])
    """The documents and links out on the page, what ``open_link`` takes."""


class TabInfo(BaseModel):
    tab_id: str
    url: str = ""
    title: str = ""


class TabsChanged(AppEvent):
    """Every Saint George's tab the visitor has open, and the one in front: the
    whole list each time."""

    tabs: list[TabInfo] = Field(default_factory=list[TabInfo])
    active: str = ""


class CommandFailed(AppEvent):
    """A move Javier sent could not be carried out on the page."""

    command: str
    reason: str = ""


class CommandDone(AppEvent):
    """A move Javier sent was carried out: the page now shows what he asked.
    Sent for ``show_contact_card`` once the card is up."""

    command: str
    detail: str = ""


class Fee(BaseModel):
    label: str = ""
    """As the page writes it: "Cuota de Incorporación por estudiante"."""
    value: str = ""
    """As the page writes it: "UF 85"."""
    note: str = ""
    """What the page adds: "(puede variar dependiendo el nivel)"."""


class FeesRead(AppEvent):
    """The admission page in front, read just now in the visitor's browser:
    the reference fees and the admission status, as the page words them."""

    url: str = ""
    heading: str = ""
    """The fees' own heading on the page: "Valores referenciales año 2026"."""
    fees: list[Fee] = Field(default_factory=list[Fee])
    status: list[str] = Field(default_factory=list[str])
    """The admission lines: "Admisión 2027: …", "Admisión Pre Kínder 2028: …"."""


class CalendarEvent(BaseModel):
    date: str
    """ISO, in Santiago: ``2026-10-27``."""
    time: str = ""
    """``19:00`` in Santiago, or empty for an all-day event."""
    title: str = ""


class EventsRead(AppEvent):
    """The school's public calendar, fetched and read in the visitor's
    browser just now: the next events from today, soonest first."""

    today: str = ""
    events: list[CalendarEvent] = Field(default_factory=list[CalendarEvent])


class ContactUsed(AppEvent):
    """The visitor pressed a button on the contact card Javier put up: the
    email opens in their own mail app (they send it themselves), or the
    phone number in their phone app."""

    via: Literal["email", "phone", "closed"]


class LanguageRequested(AppEvent):
    """The visitor pressed the other language on the widget's toggle."""

    language: Literal["en", "es"]


type SaintGeorgeEvent = (
    PageChanged
    | TabsChanged
    | CommandFailed
    | CommandDone
    | FeesRead
    | EventsRead
    | ContactUsed
    | LanguageRequested
)

SAINT_GEORGE_EVENTS = AppEvents[SaintGeorgeEvent](
    PageChanged,
    TabsChanged,
    CommandFailed,
    CommandDone,
    FeesRead,
    EventsRead,
    ContactUsed,
    LanguageRequested,
)
