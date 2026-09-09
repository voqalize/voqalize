"""Where the lawyer is reading — the browser→brain half of the screen contract.

The other direction is the :class:`~voqalize.sdk.Action` classes in ``brain.py``:
a declared shape whose wire name comes off the class name, validated at the call
site, with a generated TypeScript twin. :class:`~voqalize.sdk.AppEvent` is that,
mirrored — so ``on_rtvi`` narrows on a *type* rather than being handed a dict and
left to guess at its keys.

Docket has exactly one gesture, because it has exactly one screen: the lawyer
scrolls, and whichever clause crosses the middle of the viewport is the one they
are reading. It carries the clause's id and nothing else — the contract itself is
static and compiled into the system instruction, so an id is all Ada needs to
know which of the clauses already in front of her the lawyer means by "this one".

There is no "document opened" event. The matter is the same for every session and
is in the prompt before the first word.
"""

from __future__ import annotations

from voqalize.sdk import AppEvent, AppEvents

__all__ = ["LEGAL_EVENTS", "ClauseFocused", "LegalEvent"]


class ClauseFocused(AppEvent):
    """The lawyer scrolled, and this clause is now centred in their viewport."""

    clause_id: str


type LegalEvent = ClauseFocused

LEGAL_EVENTS = AppEvents[LegalEvent](ClauseFocused)
