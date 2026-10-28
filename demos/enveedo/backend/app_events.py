"""What the visitor's tabs report — the page→brain half of the screen contract.

The other direction is the :class:`~voqalize.sdk.Action` classes in
``brain.py``. These are sent by the extension on enveedo.com (and, for the
demo scheduler, from inside its meetings.hubspot.com frame), and they fire for
the visitor's own clicks as well as for Javier's moves, so his picture of the
screen is true whoever moved it.

Two follow the demo scheduler on /book-a-demo: :class:`DemoState` after every
change in it, and :class:`DemoScheduled` when the visitor presses its final
button (stopped by the demo before it reaches Enveedo's calendar). Two follow
the site's HubSpot forms: :class:`FormState` after every fill and after the
visitor types in one, and :class:`FormResult` once they have pressed its own
Submit and the site has answered. Javier never presses either button, never
ticks a consent box and never touches the reCAPTCHA: the extension cannot,
and the brain has no way to ask it to.

The site is Enveedo's, not ours, and it changes without asking. So the nested
shapes are plain models that ignore a field they do not know, and a page's
kind is the catalogue's word for it, whatever that is, while the events
themselves are strict: a new field is harmless, a new event is a change we want
to hear about.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk import AppEvent, AppEvents

__all__ = [
    "ENVEEDO_EVENTS",
    "CommandDone",
    "CommandFailed",
    "DemoFields",
    "DemoScheduled",
    "DemoState",
    "EnveedoEvent",
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
    """As the browser has it: /es/… on a Spanish page."""
    lang: Literal["en", "es"] = "en"
    """The language the page is in (``<html lang>``)."""
    title: str = ""
    kind: str = "page"
    """The catalogue's kind: home, platform, enterprise, frameworks, partners,
    demo, contact, about, resources, insurance, faq, trust, library, legal, …
    or page."""
    anchors: list[str] = Field(default_factory=list[str])
    """The catalogue's places this page shows, by key — what a ``show`` cue takes."""
    form: Literal["contact", "soc2", "demo", "none"] = "none"
    """The form or scheduler this page holds."""


class TabInfo(BaseModel):
    tab_id: str
    url: str = ""
    title: str = ""


class TabsChanged(AppEvent):
    """Every Enveedo tab the visitor has open, and the one in front: the whole
    list each time."""

    tabs: list[TabInfo] = Field(default_factory=list[TabInfo])
    active: str = ""


class CommandFailed(AppEvent):
    """A move Javier sent could not be carried out on the page."""

    command: str
    reason: str = ""


class CommandDone(AppEvent):
    """A move Javier sent was carried out: the page now shows what he asked.
    Sent for the form fills and the reveals, with what was done."""

    command: str
    detail: str = ""


class DemoFields(BaseModel):
    """What the scheduler's details step holds now."""

    first_name: str = ""
    last_name: str = ""
    email: str = ""


class DemoState(AppEvent):
    """Where the demo scheduler on /book-a-demo stands: still loading, the
    calendar with its open days (and the chosen day's times), or the details
    step with what is still empty."""

    step: Literal["loading", "calendar", "details", "scheduled"]
    duration: str = ""
    """The meeting length chosen: "15 mins", "30 mins" or "1 hour"."""
    durations: list[str] = Field(default_factory=list[str])
    month: str = ""
    """The month the calendar shows, as it labels it ("November 2026")."""
    days: list[str] = Field(default_factory=list[str])
    """The open days the calendar shows, ISO ("2026-11-04")."""
    date: str = ""
    """The day chosen, ISO."""
    times: list[str] = Field(default_factory=list[str])
    """The chosen day's open times, as "10:30am"."""
    time: str = ""
    timezone: str = ""
    """The timezone the scheduler shows its times in (the visitor's)."""
    filled: DemoFields = Field(default_factory=DemoFields)
    missing: list[str] = Field(default_factory=list[str])
    """Required details still empty, of first_name, last_name, email."""


class DemoScheduled(AppEvent):
    """The visitor pressed the scheduler's final button. ``blocked`` when the
    demo stopped it before it reached Enveedo's calendar."""

    date: str = ""
    time: str = ""
    filled: DemoFields = Field(default_factory=DemoFields)
    blocked: bool = False


class FormState(AppEvent):
    """One of the site's forms as it stands, after Javier filled it or after
    the visitor typed in it."""

    form: Literal["contact", "soc2"] = "contact"
    filled: list[str] = Field(default_factory=list[str])
    """The fields with a value, by the brain's names (firstname, email, …)."""
    missing: list[str] = Field(default_factory=list[str])
    """Required and still empty, the consent box included (``consent``)."""
    invalid: list[str] = Field(default_factory=list[str])
    """Filled, but the site would refuse it (an email without its @)."""
    values: dict[str, str] = Field(default_factory=dict[str, str])
    """What each filled field holds now, as the page has it. The visitor's, for
    reading back: never repeated beyond that."""
    ready: bool = False
    """Every required field is in and valid and the consent box is ticked:
    Submit is theirs to press."""
    by: Literal["javier", "visitor"] = "javier"


class FormResult(AppEvent):
    """The visitor pressed Submit on one of the site's forms and the site
    answered."""

    form: Literal["contact", "soc2"] = "contact"
    outcome: Literal["sent", "invalid", "failed"]
    """``sent``: HubSpot's thank-you message replaced the form; ``invalid``: a
    field refused; ``failed``: the site could not send it (the reCAPTCHA did
    not pass, or the request failed)."""
    message: str = ""
    """The site's own words, when it showed any."""
    fields: list[str] = Field(default_factory=list[str])
    """The fields the site marked wrong, on ``invalid``."""


class LanguageRequested(AppEvent):
    """The visitor pressed the other language on the widget's toggle."""

    language: Literal["en", "es"]


type EnveedoEvent = (
    PageChanged
    | TabsChanged
    | CommandFailed
    | CommandDone
    | DemoState
    | DemoScheduled
    | FormState
    | FormResult
    | LanguageRequested
)

ENVEEDO_EVENTS = AppEvents[EnveedoEvent](
    PageChanged,
    TabsChanged,
    CommandFailed,
    CommandDone,
    DemoState,
    DemoScheduled,
    FormState,
    FormResult,
    LanguageRequested,
)
