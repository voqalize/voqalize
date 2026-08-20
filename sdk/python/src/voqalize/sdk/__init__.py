"""Voqalize Python Agent SDK — **pipecat-free**.

Write a :class:`Brain` of callbacks; capability arrives as the :class:`Session`
passed into every one of them. Voice owns the floor and hands it to you by
calling; you spend it by yielding speech and actions::

    class Concierge(Brain):
        async def greet(self, session):
            return "Hi! What can I do for you?"

        async def on_user_message(self, session, msg):
            yield SpeechStart()
            yield Chunk(await self.answer(msg.text))
            yield SpeechEnd()

Then host it, one Brain instance per session:

- **Inbound (primary):** ``serve_direct(Concierge, host=..., port=...)`` — the
  Voqalize voice runtime dials your WebSocket route per session. Cloud Run or any
  backend can expose it.
- **Outbound (fallback, localhost / egress-only):** ``serve(Concierge,
  api_key=..., cortex_url=...)`` — your process dials the Cortex relay.

The same Brain runs on either transport; a config change picks which. Installing
this SDK pulls **no** ``pipecat`` dependency — the wire is plain protobuf and the
Brain surface is plain dataclasses. ``voqalize.sdk.gemini`` (extra: ``gemini``)
adds a Gemini-backed base class; nothing here imports it.
"""

from ._logging import configure_logging, session_context
from .actions import Action, Result
from .brain import (
    ActionHandle,
    Brain,
    ProtocolError,
    Session,
    adapter_for,
    brain_factory,
    make_agent,
    make_direct_agent,
    serve,
    serve_auto,
    serve_direct,
)
from .events import (
    AppMessage,
    Chunk,
    Error,
    Finalize,
    IdleTrigger,
    Speech,
    SpeechEnd,
    SpeechStart,
    UserMessage,
)
from .inbound import DirectAgent
from .outbound import CortexAgent
from .session import Channel, SessionRejected, run_session

__all__ = [
    "Action",
    "ActionHandle",
    "AppMessage",
    "Brain",
    "Channel",
    "Chunk",
    "CortexAgent",
    "DirectAgent",
    "Error",
    "Finalize",
    "IdleTrigger",
    "ProtocolError",
    "Result",
    "Session",
    "SessionRejected",
    "Speech",
    "SpeechEnd",
    "SpeechStart",
    "UserMessage",
    "adapter_for",
    "brain_factory",
    "configure_logging",
    "make_agent",
    "make_direct_agent",
    "run_session",
    "serve",
    "serve_auto",
    "serve_direct",
    "session_context",
]
