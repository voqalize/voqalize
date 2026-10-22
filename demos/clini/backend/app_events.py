"""What the visitor's tabs report — the page→brain half of the screen contract.

The other direction is the :class:`~voqalize.sdk.Action` classes in
``brain.py``. These are sent by the extension on www.clini.cl and
agenda-web.clini.cl, and they fire for the visitor's own clicks as well as for
Javier's moves, so his picture of their screen is true whoever moved it.

The site is Clini's, not ours, and it changes without asking. So the nested
shapes are plain models that ignore a field they do not know, while the events
themselves are strict: a new field on a page report is harmless, a new event is
a change we want to hear about.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk import AppEvent, AppEvents

__all__ = [
    "CLINI_EVENTS",
    "AgendaState",
    "CliniEvent",
    "CommandDone",
    "CommandFailed",
    "LanguageRequested",
    "LasikFormState",
    "PageChanged",
    "TabInfo",
    "TabsChanged",
]


class PageChanged(AppEvent):
    """The tab in front changed page, or came to the front: what is on it now."""

    site: Literal["site", "agenda"] = "site"
    """``site`` is www.clini.cl; ``agenda`` is agenda-web.clini.cl, the booking."""
    url: str = ""
    path: str
    title: str = ""
    kind: Literal["page", "post", "agenda"] = "page"
    """``page`` is any www.clini.cl page, ``post`` a blog post (``/blog/…`` and
    ``/blog-mujer/…``), ``agenda`` the booking on agenda-web.clini.cl."""
    headings: list[str] = Field(default_factory=list[str])
    """The page's headings, in order — what ``show_section`` takes."""
    faqs: list[str] = Field(default_factory=list[str])
    """The FAQ questions on the page — what ``open_faq`` takes."""
    plans: list[str] = Field(default_factory=list[str])
    """Named plans or offers on the page (kept for the brain's matcher)."""


class TabInfo(BaseModel):
    tab_id: str
    url: str = ""
    title: str = ""


class TabsChanged(AppEvent):
    """Every Clini tab the visitor has open, and the one in front: the
    whole list each time."""

    tabs: list[TabInfo] = Field(default_factory=list[TabInfo])
    active: str = ""


class CommandFailed(AppEvent):
    """A move Javier sent could not be carried out on the page."""

    command: str
    reason: str = ""


class CommandDone(AppEvent):
    """A move Javier sent was carried out: the page now shows what he asked.

    Sent for ``open_agenda`` (once the requested step is on screen),
    ``agenda_pick`` (after the day or hour is selected),
    ``fill_agenda_patient`` (after the fields are set) and ``fill_lasik_form``.
    The booking tools wait for this or :class:`CommandFailed` before they
    answer the model, so Javier only claims what actually happened."""

    command: str
    detail: str = ""
    """What is on screen now, in a few English words, e.g. ``selected Tue
    2026-10-27 10:00 at QUINTA VERGARA`` or ``filled name, email; phone
    refused: …``."""


class LanguageRequested(AppEvent):
    """The visitor pressed the other language on the widget's toggle."""

    language: Literal["en", "es"]


class AgendaState(AppEvent):
    """What the booking on agenda-web.clini.cl shows: on load, and after each
    step, whoever took it (debounced by the page).

    ``search`` is the service and prestación picker; ``results`` the calendar
    and a day's hours; ``booking`` the patient form; ``done`` the success
    overlay. Names are the booking's own words, as it shows them."""

    step: Literal["search", "results", "booking", "done"]
    servicio: int | None = None
    servicio_name: str = ""
    prestacion: int | None = None
    prestacion_name: str = ""
    region: int | None = None
    month: str = ""
    """The month the calendar shows, YYYY-MM (empty if it is not on screen)."""
    days: list[str] = Field(default_factory=list[str])
    """Every open day of the month on screen (at most 31), YYYY-MM-DD."""
    centres: list[str] = Field(default_factory=list[str])
    """The centres listed for the day, as titled ("TM | BUIN")."""
    day: str = ""
    """The day selected or in view, YYYY-MM-DD: the one ``times`` belong to."""
    centre: str = ""
    """The centre whose ``times`` are listed, as titled ("TM | BUIN")."""
    times: list[str] = Field(default_factory=list[str])
    """The hours of ``centre`` (at most 24), HH:MM; empty once an hour is
    picked."""
    selected: str = ""
    """The selection summary, as the booking writes it."""
    indications: str = ""
    """The service's alert and the centre's indications (at most 600 chars)."""
    invalid: list[str] = Field(default_factory=list[str])
    """The patient fields still empty or invalid, e.g. ``rut``, ``phone``, ``consent``."""
    document: Literal["rut", "passport"] = "rut"
    """Which identity document the patient form asks for: the RUT, or a
    passport for a visitor without one."""
    ready: bool = False
    """Whether AGENDAR is enabled: everything is valid, and it is theirs to press."""


class LasikFormState(AppEvent):
    """The free LASIK evaluation form on /cirugia-lasik, after a fill."""

    filled: list[str] = Field(default_factory=list[str])
    missing: list[str] = Field(default_factory=list[str])
    valid: bool = False
    """Whether the form passes its own checks: "¡Agendar evaluación!" is theirs to press."""


type CliniEvent = (
    PageChanged
    | TabsChanged
    | CommandDone
    | CommandFailed
    | LanguageRequested
    | AgendaState
    | LasikFormState
)

CLINI_EVENTS = AppEvents[CliniEvent](
    PageChanged,
    TabsChanged,
    CommandDone,
    CommandFailed,
    LanguageRequested,
    AgendaState,
    LasikFormState,
)
