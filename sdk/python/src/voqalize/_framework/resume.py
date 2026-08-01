"""Greeting resolution for a framework integration's session start.

A voice session is one WebSocket, but a *logical* conversation may span several: a
dropped call reconnects, or a caller phones back an hour later. Each of those is a
fresh ``session_id`` with an empty history. Resuming that prior context is the
adapter's job (ADK seeds it back into the framework-owned session); the only shared
concern that lives here is resolving the **greeting** — the line the agent opens
with when the call is *not* a resume.

The client keys resume off its **own** stable identifier — read from
``session.init`` / ``start.init`` (the opaque payload the control plane puts on
``VqlStart``) — loads that conversation from its **own** store, and hands the
messages back. The SDK persists nothing and interprets no identifier. This keeps
the moat intact: the transcript never leaves the client's environment.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from voqalize.sdk.brain import Session, SessionStart

    # A greeting is either a fixed line, or a callback that computes the opener from
    # the session context (e.g. a name read from ``start.init``) — returning ``None``
    # to open silently. The callback is the escape hatch from a hard-coded default.
    GreetingHook = Callable[[Session, SessionStart], Awaitable[str | None]]


async def resolve_greeting(
    greeting: str | GreetingHook | None,
    session: Session,
    start: SessionStart,
) -> str | None:
    """Resolve a greeting to the line to speak (or ``None`` for silence).

    A plain string (or ``None``) is returned as-is; a callable is awaited with the
    session context so the opener can be computed from ``start.init`` (a caller's
    name, locale, account tier) instead of being frozen at wiring time."""
    if greeting is None or isinstance(greeting, str):
        return greeting
    return await greeting(session, start)
