"""What the visitor's page reports — the page→brain half of the screen contract.

The other direction is the :class:`~voqalize.sdk.Action` classes in ``brain.py``
and ``lead.py``. These are sent by the adapter the extension injects into
saatvikgroup.com, and they fire for the visitor's own clicks as well as for
Tushar's moves, so the brain's picture of the page is true whoever moved it.

The site is Saatvik's, not ours, and it changes without asking. So the nested
shapes are plain models that ignore a field they do not know, while the events
themselves are strict: a new field on a dealer card is harmless, a new event is a
change we want to hear about.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk import AppEvent, AppEvents

__all__ = [
    "SAATVIK_EVENTS",
    "CalculatorInputs",
    "CalculatorResult",
    "CommandFailed",
    "Dealer",
    "DealersShown",
    "DocumentClosed",
    "DocumentOpened",
    "EnquiryFields",
    "EnquiryOpened",
    "EnquirySubmitted",
    "LanguageRequested",
    "PageChanged",
    "SaatvikEvent",
]

EnquiryKind = Literal["domestic", "dealer", "export"]


class PageChanged(AppEvent):
    """The route changed, or the page first loaded: what is on it now."""

    path: str
    title: str = ""
    headings: list[str] = Field(default_factory=list[str])
    """The page's ``h1`` to ``h3`` texts, in order — what ``show_section`` takes."""
    faqs: list[str] = Field(default_factory=list[str])
    """The accordion questions on the page — what ``open_faq`` takes."""


class DocumentOpened(AppEvent):
    """The PDF viewer opened, or turned to a page."""

    url: str
    page: int = 1


class DocumentClosed(AppEvent):
    """The PDF viewer closed."""

    url: str = ""
    page: int = 1


class CalculatorInputs(BaseModel):
    units: float | None = None
    state: str | None = None
    rate: float | None = None


class CalculatorResult(AppEvent):
    """The solar calculator finished: its inputs, and its result as the page
    prints it."""

    inputs: CalculatorInputs = Field(default_factory=CalculatorInputs)
    text: str = ""


class Dealer(BaseModel):
    name: str
    type: str = ""
    city: str = ""
    phone: str = ""


class DealersShown(AppEvent):
    """The dealer locator shows these, for this state and search."""

    state: str = ""
    query: str = ""
    dealers: list[Dealer] = Field(default_factory=list[Dealer])


class EnquiryOpened(AppEvent):
    """The enquiry form is on screen, on this tab, with these required fields empty."""

    kind: EnquiryKind
    missing: list[str] = Field(default_factory=list[str])


class EnquiryFields(BaseModel):
    name: str = ""
    company: str = ""
    email: str = ""
    mobile: str = ""
    category: str = ""
    state: str = ""
    message: str = ""


class EnquirySubmitted(AppEvent):
    """The visitor pressed SUBMIT; the fields as they stood, read before the page sent."""

    kind: EnquiryKind
    fields: EnquiryFields = Field(default_factory=EnquiryFields)


class CommandFailed(AppEvent):
    """A move Tushar sent could not be carried out on the page."""

    command: str
    reason: str = ""


class LanguageRequested(AppEvent):
    """The visitor pressed the other language on the widget's toggle."""

    language: Literal["en", "hi"]


type SaatvikEvent = (
    PageChanged
    | DocumentOpened
    | DocumentClosed
    | CalculatorResult
    | DealersShown
    | EnquiryOpened
    | EnquirySubmitted
    | CommandFailed
    | LanguageRequested
)

SAATVIK_EVENTS = AppEvents[SaatvikEvent](
    PageChanged,
    DocumentOpened,
    DocumentClosed,
    CalculatorResult,
    DealersShown,
    EnquiryOpened,
    EnquirySubmitted,
    CommandFailed,
    LanguageRequested,
)
