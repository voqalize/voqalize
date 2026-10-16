"""What the visitor's tabs report — the page→brain half of the screen contract.

The other direction is the :class:`~voqalize.sdk.Action` classes in
``brain.py``. These are sent by the extension on sendpotion.com and
blog.sendpotion.com, and they fire for the visitor's own clicks as well as for
Tushar's moves, so his picture of their screen is true whoever moved it.

The site is SendPotion's, not ours, and it changes without asking. So the nested
shapes are plain models that ignore a field they do not know, while the events
themselves are strict: a new field on a booking step is harmless, a new event is
a change we want to hear about.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk import AppEvent, AppEvents

__all__ = [
    "SENDPOTION_EVENTS",
    "CommandFailed",
    "DemoFields",
    "DemoScheduled",
    "DemoState",
    "PageChanged",
    "SendPotionEvent",
    "TabInfo",
    "TabsChanged",
]


class PageChanged(AppEvent):
    """The tab in front changed page, or came to the front: what is on it now."""

    site: Literal["site", "blog"] = "site"
    """``site`` is sendpotion.com; ``blog`` is blog.sendpotion.com."""
    url: str = ""
    path: str
    title: str = ""
    kind: Literal["page", "post", "blog"] = "page"
    """A product page, one blog post, or a list of posts."""
    headings: list[str] = Field(default_factory=list[str])
    """The page's headings, in order — what ``show_section`` takes."""
    faqs: list[str] = Field(default_factory=list[str])
    """The FAQ questions on the page — what ``open_faq`` takes."""
    plans: list[str] = Field(default_factory=list[str])
    """The pricing plans on the page, by name."""


class TabInfo(BaseModel):
    tab_id: str
    url: str = ""
    title: str = ""


class TabsChanged(AppEvent):
    """Every SendPotion tab the visitor has open, and the one in front: the
    whole list each time."""

    tabs: list[TabInfo] = Field(default_factory=list[TabInfo])
    active: str = ""


class DemoFields(BaseModel):
    name: str = ""
    email: str = ""
    notes: str = ""


class DemoState(AppEvent):
    """Where the demo booking on /demo/ stands: the calendar with its open days
    (and the chosen day's times), or the details step with what is still empty."""

    step: Literal["calendar", "details", "scheduled"]
    month: str = ""
    days: list[str] = Field(default_factory=list[str])
    date: str = ""
    times: list[str] = Field(default_factory=list[str])
    time: str = ""
    timezone: str = ""
    filled: DemoFields = Field(default_factory=DemoFields)
    missing: list[str] = Field(default_factory=list[str])


class DemoScheduled(AppEvent):
    """The visitor pressed Schedule Event. ``blocked`` when the demo stopped it
    before it reached SendPotion's calendar."""

    date: str = ""
    time: str = ""
    filled: DemoFields = Field(default_factory=DemoFields)
    blocked: bool = False


class CommandFailed(AppEvent):
    """A move Tushar sent could not be carried out on the page."""

    command: str
    reason: str = ""


type SendPotionEvent = PageChanged | TabsChanged | DemoState | DemoScheduled | CommandFailed

SENDPOTION_EVENTS = AppEvents[SendPotionEvent](
    PageChanged,
    TabsChanged,
    DemoState,
    DemoScheduled,
    CommandFailed,
)
