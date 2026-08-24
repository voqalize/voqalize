"""Voqalize Python Agent SDK — **pipecat-free**.

Write a :class:`Brain` of callbacks; capability arrives as the :class:`Session`
passed into every one of them. Voqalize owns the floor and hands it to you by
calling; you spend it by yielding speech. Everything that is not speech — an
action, a language switch, hanging up — is a method on the session::

    class Concierge(Brain):
        async def greet(self, session):
            return "Hi! What can I do for you?"

        async def on_user_message(self, session, msg):
            yield SpeechStart()
            yield Chunk(await self.answer(msg.text))
            yield SpeechEnd()

A brain lives inside a larger application, and there are exactly two ways that
application hosts it:

- **Your app owns a WebSocket route.** Accept the upgrade yourself and hand the
  connected socket to :func:`run_session` — one connection is one session, and
  Voqalize dials your ``brain_url`` with ``?session_id=`` appended. This is the
  primary path.
- **Your app cannot accept an inbound connection** (a laptop, a strict egress-only
  network). ``await serve(Concierge, api_key=..., cortex_url=...)`` dials the
  Cortex relay instead and blocks; you decide where that call runs.

The same Brain runs on either. Installing this SDK pulls **no** ``pipecat``
dependency — the wire is plain protobuf and the Brain surface is plain
dataclasses. ``voqalize.sdk.gemini`` (extra: ``gemini``) adds a Gemini-backed base
class; nothing here imports it.
"""

from ._logging import configure_logging, session_context
from .actions import Action, Result
from .brain import ActionHandle, Brain, RequestRejected, Session, WireError, serve
from .events import (
    Chunk,
    Error,
    Finalize,
    RTVIMessage,
    Speech,
    SpeechEnd,
    SpeechStart,
    UserIdle,
    UserMessage,
)
from .session import Channel, SessionRejected, run_session
from .wire import ErrorCode, RTVIType

__all__ = [
    "Action",
    "ActionHandle",
    "Brain",
    "Channel",
    "Chunk",
    "Error",
    "ErrorCode",
    "Finalize",
    "RTVIMessage",
    "RTVIType",
    "RequestRejected",
    "Result",
    "Session",
    "SessionRejected",
    "Speech",
    "SpeechEnd",
    "SpeechStart",
    "UserIdle",
    "UserMessage",
    "WireError",
    "configure_logging",
    "run_session",
    "serve",
    "session_context",
]
