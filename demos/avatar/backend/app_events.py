"""The one thing the page tells the brain — the browser→brain half of the contract.

The other direction is the :class:`~voqalize.sdk.Action` classes in ``brain.py``:
a declared shape whose wire name comes off the class name, validated at the call
site, with a generated TypeScript twin. :class:`~voqalize.sdk.AppEvent` is that,
mirrored — so ``on_rtvi`` narrows on a *type* rather than reaching into a dict
whose shape nothing checks.

There is exactly one event, and it carries nothing. Nothing about the face
travels this lane: the face was settled at connect, on both sides of the socket
at once, from the same key. What is left is a timing fact — the data channel is
open now — and a fact has no payload.
"""

from __future__ import annotations

from voqalize.sdk import AppEvent, AppEvents

__all__ = ["AVATAR_EVENTS", "AvatarEvent", "Ready"]


class Ready(AppEvent):
    """The page's data channel is open, so a server message will now arrive."""


type AvatarEvent = Ready

AVATAR_EVENTS = AppEvents[AvatarEvent](Ready)
