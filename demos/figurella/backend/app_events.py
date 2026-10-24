"""What the visitor's tabs report — the page→brain half of the screen contract.

The other direction is the :class:`~voqalize.sdk.Action` classes in
``brain.py``. These are sent by the extension on figurella.cl, and they fire for
the visitor's own clicks as well as for Javier's moves, so his picture of her
screen is true whoever moved it.

Two of them follow the forms: :class:`FormState` after every fill and after she
types or picks a branch herself, and :class:`FormResult` once she has pressed
the form's own button and the site has answered (its success message, its
thank-you page, or its error). Javier never presses that button: the extension
cannot, and the brain has no way to ask it to.

The site is Figurella's, not ours, and it changes without asking. So the
nested shapes are plain models that ignore a field they do not know, while the
events themselves are strict: a new field is harmless, a new event is a change
we want to hear about.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk import AppEvent, AppEvents

__all__ = [
    "FIGURELLA_EVENTS",
    "CommandDone",
    "CommandFailed",
    "FigurellaEvent",
    "FormResult",
    "FormState",
    "LanguageRequested",
    "PageChanged",
    "TabInfo",
    "TabsChanged",
]

PageKind = Literal[
    "home", "method", "plans", "stories", "convenios", "franchise", "faq", "blog", "post",
    "thanks", "privacy", "page",
]  # fmt: skip
FormName = Literal["booking", "franchise"]


class PageChanged(AppEvent):
    """The tab in front changed page, or came to the front: what is on it now."""

    url: str = ""
    path: str
    title: str = ""
    kind: PageKind = "page"
    anchors: list[str] = Field(default_factory=list[str])
    """The catalogue's places this page shows, by key — what a ``show`` cue takes."""
    faqs: list[str] = Field(default_factory=list[str])
    """The FAQ accordion's questions, by key, on the FAQ page."""
    form: Literal["booking", "franchise", "none"] = "none"
    """The form on this page: the booking form (in the footer of nearly every
    page), the franchise form (/franquicias/), or none."""


class TabInfo(BaseModel):
    tab_id: str
    url: str = ""
    title: str = ""


class TabsChanged(AppEvent):
    """Every Figurella tab the visitor has open, and the one in front: the whole
    list each time."""

    tabs: list[TabInfo] = Field(default_factory=list[TabInfo])
    active: str = ""


class CommandFailed(AppEvent):
    """A move Javier sent could not be carried out on the page."""

    command: str
    reason: str = ""


class CommandDone(AppEvent):
    """A move Javier sent was carried out: the page now shows what he asked.
    Sent for the form fills, with what went in and what is still empty."""

    command: str
    detail: str = ""


class FormState(AppEvent):
    """A form as it stands, after Javier filled it or after she typed in it or
    picked a branch on the page herself."""

    form: FormName = "booking"
    filled: list[str] = Field(default_factory=list[str])
    """Of nombre, telefono, email, comuna, sucursal, mensaje: the ones with a value."""
    missing: list[str] = Field(default_factory=list[str])
    """Required and still empty."""
    invalid: list[str] = Field(default_factory=list[str])
    """Filled, but the site would refuse it (a phone with spaces or letters, an
    email without its @)."""
    values: dict[str, str] = Field(default_factory=dict[str, str])
    """What each filled field holds now, as the page has it (the branch by its
    name). Hers, for reading back: never repeated beyond that."""
    consent: bool = True
    """The privacy and WhatsApp box (booking form only), which comes ticked and
    is hers alone to change."""
    ready: bool = False
    """Every required field is in and valid: the button is hers to press."""
    by: Literal["javier", "visitor"] = "javier"


class FormResult(AppEvent):
    """She pressed the form's own button and the site answered."""

    form: FormName = "booking"
    outcome: Literal["sent", "error"]
    message: str = ""
    """The site's own words, when it showed any."""
    fields: list[str] = Field(default_factory=list[str])
    """The fields the site marked wrong, on an error."""


class LanguageRequested(AppEvent):
    """The visitor pressed the other language on the widget's toggle."""

    language: Literal["en", "es"]


type FigurellaEvent = (
    PageChanged
    | TabsChanged
    | CommandFailed
    | CommandDone
    | FormState
    | FormResult
    | LanguageRequested
)

FIGURELLA_EVENTS = AppEvents[FigurellaEvent](
    PageChanged,
    TabsChanged,
    CommandFailed,
    CommandDone,
    FormState,
    FormResult,
    LanguageRequested,
)
