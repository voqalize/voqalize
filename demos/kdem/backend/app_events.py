"""Where the visitor is on the site — the browser→brain half of the snippet's contract.

The other direction is the :class:`~voqalize.sdk.Action` classes in
``brain.py`` (``navigate``, ``point_at``, ``show_link``, ``language_changed``).
This is their mirror: a declared shape, validated where it arrives,
so ``on_rtvi`` narrows on a type instead of digging through a dict.

The snippet also has an English | ಕನ್ನಡ toggle. Pressing the other side sends
``language_requested``, and the brain switches both legs in code, not through the
model, and answers with ``language_changed``, the toggle's only source of truth.

The snippet carries a call across page loads, so the visitor can click through
the site and keep talking. On every (re)connect it sends ``page_viewed`` with
the page it is on, and that is how Aria learns the visitor moved. It carries
the path and the page's own ``<title>``; the brain names a page only by the
title on its own approved list, never by what the browser sent.

Once per call it also sends ``mic_permission``: whether the browser gave it a
live microphone. The panel says "Listening" only once it has.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from voqalize.sdk import AppEvent, AppEvents

from .content import KanField, LanguageTag

__all__ = [
    "KDEM_EVENTS",
    "KanFieldChanged",
    "KanFillFailed",
    "KdemEvent",
    "LanguageRequested",
    "MicPermission",
    "PageViewed",
    "PointMissed",
]


class PageViewed(AppEvent):
    """The page the visitor has open, sent when the call (re)connects on it."""

    path: str = Field(min_length=1, max_length=2048)
    """``location.pathname``."""
    title: str | None = Field(default=None, max_length=2048)
    """``document.title``. Logged, never quoted to the model."""


class LanguageRequested(AppEvent):
    """The visitor pressed the other side of the snippet's English | ಕನ್ನಡ toggle."""

    language: LanguageTag


class PointMissed(AppEvent):
    """A ``point_at`` the page could not show: no visible element holds the text."""

    text: str = Field(max_length=200)


class KanFieldChanged(AppEvent):
    """The visitor typed in, or changed, one field of the KAN application form
    themselves. ``value`` is what the field holds now; it is trimmed in the
    brain, and a mobile number or email is never logged or put in the context."""

    field: KanField
    value: str


class KanFillFailed(AppEvent):
    """The snippet could not carry out a ``kan_fill``: the form is not on the
    page, the field is not on the form, or the drop-down has no such option."""

    field: KanField
    reason: Literal["form_missing", "field_missing", "option_missing"]


class MicPermission(AppEvent):
    """What became of the visitor's microphone, sent once per call: ``granted``
    (a live track), ``denied`` (the browser refused it), ``unavailable`` (no
    microphone, or one in use elsewhere) or ``no_answer`` (the browser's prompt
    still unanswered after ten seconds; a later grant is sent too). Logged, so
    calls that never had a microphone can be counted; never put to the model."""

    outcome: Literal["granted", "denied", "unavailable", "no_answer"]
    waited_ms: int = Field(default=0, ge=0, le=86_400_000)
    """How long after the call started the outcome was known."""


type KdemEvent = (
    PageViewed | LanguageRequested | PointMissed | KanFieldChanged | KanFillFailed | MicPermission
)

KDEM_EVENTS = AppEvents[KdemEvent](
    PageViewed, LanguageRequested, PointMissed, KanFieldChanged, KanFillFailed, MicPermission
)
