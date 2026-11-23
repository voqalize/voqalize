"""Calls that outlive their brain socket (SDK 0.15.0, ``Config.redial``).

With redial on, when Meera's socket drops without a hang-up (a Cortex restart,
a network blip, a deploy draining with 1012), Voqalize dials the brain again for
the same session and resends the turns it had not answered. The SDK runs that as
a new session: a fresh ``DentalBrain``, ``on_session_start``, then a greeting
the caller does not hear. Everything the call had built lives on the old brain
object: the language and page, the call's own copy of the calendar (with what
this browser booked, moved or cancelled laid over it), the verified patient,
the slot held, the change waiting for a yes, the model's history and the Stage
director.

So each live brain is held here by session id, and a brain that starts on a
session id already held adopts it. Process memory, not a shared store: a redial
that reaches this process (the usual case behind Cortex, where one process holds
the one relay socket) picks the call up where it was; one that reaches a fresh
process finds nothing and carries on as a new conversation on the same page,
which still beats a call that ends. Entries go two minutes after their socket
drops (Voqalize redials one call for 60 s at most, brain.redial.cap_secs), or
twelve hours after they were last held, whichever is first.

The same pattern as Fernhollow's ``rejoin.py`` (CONTRACT.md there, v7).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Generic, TypeVar

__all__ = ["Rejoin"]

T = TypeVar("T")

#: How long a dropped call's brain is kept for a redial to find.
KEEP_AFTER_DROP_S = 120.0
#: A brain whose socket never reported a drop (a process killed mid-call) is
#: still let go eventually.
KEEP_LIVE_S = 12 * 3600.0


class Rejoin(Generic[T]):
    """Live brains by session id, for a redial to pick up."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        # session id → (brain, when it was held, when its socket dropped or None)
        self._held: dict[str, tuple[T, float, float | None]] = {}

    def __len__(self) -> int:
        self._prune()
        return len(self._held)

    def hold(self, session_id: str, brain: T) -> None:
        """``brain`` now serves ``session_id``'s call."""
        self._prune()
        self._held[session_id] = (brain, self._clock(), None)

    def take(self, session_id: str) -> T | None:
        """The brain that served this call before, if it is still held."""
        self._prune()
        entry = self._held.pop(session_id, None)
        return None if entry is None else entry[0]

    def dropped(self, session_id: str, brain: T) -> None:
        """``brain``'s socket closed. Kept a while for a redial; a brain that is
        no longer the one held (a redial already took the call) changes nothing."""
        entry = self._held.get(session_id)
        if entry is not None and entry[0] is brain and entry[2] is None:
            self._held[session_id] = (brain, entry[1], self._clock())

    def clear(self) -> None:
        """Forget every call (tests reuse one session id)."""
        self._held.clear()

    def _prune(self) -> None:
        now = self._clock()
        for sid, (_, held_at, dropped_at) in list(self._held.items()):
            if (dropped_at is not None and now - dropped_at > KEEP_AFTER_DROP_S) or (
                now - held_at > KEEP_LIVE_S
            ):
                del self._held[sid]
