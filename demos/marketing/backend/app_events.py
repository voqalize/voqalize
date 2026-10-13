"""Where the visitor is on the page — the browser→brain half of the screen contract.

The other direction is the :class:`~voqalize.sdk.Action` classes in ``brain.py``.
This is that, mirrored: a declared shape, validated at the call site, with a
generated TypeScript twin, so ``on_rtvi`` narrows on a *type* rather than being
handed a dict and left to guess at its keys.

The marketing page has one gesture, because the visitor can do one thing to it
that matters: scroll. Whichever band crosses the middle of the viewport is the
one they are looking at, and that is what makes "what's this?" answerable at all.
It carries the section's id and nothing else — the page itself is fixed and its
map is compiled into the system instruction, so an id is all Tanya needs.

There is no event for the agent's own scrolling. A brain's dispatch is not the
visitor's gesture, and the mirror is patched at the dispatch instead — see
``brain.py``. There is none for the markdown panel either: the agent writes that
panel, so its contents are already in the model's own context, and a dismissal is
not something the agent should act on.
"""

from __future__ import annotations

from voqalize.sdk import AppEvent, AppEvents

from .content import SectionId

__all__ = ["MARKETING_EVENTS", "MarketingEvent", "SectionViewed"]


class SectionViewed(AppEvent):
    """The visitor scrolled, and this section is now centred in their viewport."""

    section: SectionId


type MarketingEvent = SectionViewed

MARKETING_EVENTS = AppEvents[MarketingEvent](SectionViewed)
