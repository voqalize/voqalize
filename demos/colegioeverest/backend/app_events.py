"""What the visitor's tabs report — the page→brain half of the screen contract.

The other direction is the :class:`~voqalize.sdk.Action` classes in
``brain.py``. These are sent by the extension on www.colegioeverest.cl, and
they fire for the visitor's own clicks as well as for Javier's moves, so his
picture of the screen is true whoever moved it.

Two of them follow the contact form on /contacto/: :class:`FormState` after
every fill and after the visitor types in it, and :class:`FormResult` once they
have pressed its own "Enviar" button and the site has answered (Contact Form
7's own events: sent, invalid, spam, failed). Javier never presses that button
and never touches the Cloudflare check beside it: the extension cannot, and
the brain has no way to ask it to.

The site is the school's, not ours, and it changes without asking. So the
nested shapes are plain models that ignore a field they do not know, and a
page's kind is the catalogue's word for it, whatever that is, while the events
themselves are strict: a new field is harmless, a new event is a change we want
to hear about.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk import AppEvent, AppEvents

__all__ = [
    "EVEREST_EVENTS",
    "CommandDone",
    "CommandFailed",
    "EverestEvent",
    "FormResult",
    "FormState",
    "LanguageRequested",
    "PageChanged",
    "TabInfo",
    "TabsChanged",
]


class PageChanged(AppEvent):
    """The tab in front changed page, or came to the front: what is on it now."""

    url: str = ""
    path: str
    title: str = ""
    kind: str = "page"
    """The catalogue's kind: home, admission, contact, school, education, cycle,
    info, community, safeguarding, documents, tour, news, post, … or page."""
    anchors: list[str] = Field(default_factory=list[str])
    """The catalogue's places this page shows, by key — what a ``show`` cue takes."""
    form: Literal["contact", "none"] = "none"
    """The contact form, on /contacto/ only."""


class TabInfo(BaseModel):
    tab_id: str
    url: str = ""
    title: str = ""


class TabsChanged(AppEvent):
    """Every Colegio Everest tab the visitor has open, and the one in front: the
    whole list each time."""

    tabs: list[TabInfo] = Field(default_factory=list[TabInfo])
    active: str = ""


class CommandFailed(AppEvent):
    """A move Javier sent could not be carried out on the page."""

    command: str
    reason: str = ""


class CommandDone(AppEvent):
    """A move Javier sent was carried out: the page now shows what he asked.
    Sent for the form fill and the sliders, with what was done."""

    command: str
    detail: str = ""


class FormState(AppEvent):
    """The contact form as it stands, after Javier filled it or after the
    visitor typed in it."""

    form: Literal["contact"] = "contact"
    filled: list[str] = Field(default_factory=list[str])
    """Of nombre, email, asunto, mensaje: the ones with a value."""
    missing: list[str] = Field(default_factory=list[str])
    """Required and still empty."""
    invalid: list[str] = Field(default_factory=list[str])
    """Filled, but the site would refuse it (an email without its @)."""
    values: dict[str, str] = Field(default_factory=dict[str, str])
    """What each filled field holds now, as the page has it. The visitor's, for
    reading back: never repeated beyond that."""
    ready: bool = False
    """Every required field is in and valid: "Enviar" is theirs to press."""
    by: Literal["javier", "visitor"] = "javier"


class FormResult(AppEvent):
    """The visitor pressed "Enviar" and the site answered."""

    form: Literal["contact"] = "contact"
    outcome: Literal["sent", "invalid", "spam", "failed"]
    """Contact Form 7's answer: ``sent`` (``wpcf7mailsent``), ``invalid`` (a
    field refused), ``spam`` (the Cloudflare check did not pass), ``failed``
    (the site could not send it)."""
    message: str = ""
    """The site's own words, when it showed any."""
    fields: list[str] = Field(default_factory=list[str])
    """The fields the site marked wrong, on ``invalid``."""


class LanguageRequested(AppEvent):
    """The visitor pressed the other language on the widget's toggle."""

    language: Literal["en", "es"]


type EverestEvent = (
    PageChanged
    | TabsChanged
    | CommandFailed
    | CommandDone
    | FormState
    | FormResult
    | LanguageRequested
)

EVEREST_EVENTS = AppEvents[EverestEvent](
    PageChanged,
    TabsChanged,
    CommandFailed,
    CommandDone,
    FormState,
    FormResult,
    LanguageRequested,
)
