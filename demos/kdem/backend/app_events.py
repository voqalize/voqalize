"""Where the visitor is on the site — the browser→brain half of the snippet's contract.

The other direction is ``show_link``, the one :class:`~voqalize.sdk.Action` the
brain sends. This is its mirror: a declared shape, validated where it arrives,
so ``on_rtvi`` narrows on a type instead of digging through a dict.

The snippet carries a call across page loads, so the visitor can click through
the site and keep talking. On every (re)connect it sends ``page_viewed`` with
the page it is on, and that is how Aria learns the visitor moved. It carries
the path and the page's own ``<title>``; the brain names a page only by the
title on its own approved list, never by what the browser sent.
"""

from __future__ import annotations

from pydantic import Field

from voqalize.sdk import AppEvent, AppEvents

__all__ = ["KDEM_EVENTS", "KdemEvent", "PageViewed"]


class PageViewed(AppEvent):
    """The page the visitor has open, sent when the call (re)connects on it."""

    path: str = Field(min_length=1, max_length=2048)
    """``location.pathname``."""
    title: str | None = Field(default=None, max_length=2048)
    """``document.title``. Logged, never quoted to the model."""


type KdemEvent = PageViewed

KDEM_EVENTS = AppEvents[KdemEvent](PageViewed)
