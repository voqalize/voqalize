"""Voqalize Python Agent SDK — **pipecat-free**.

Write a :class:`Brain` of callbacks (``on_interaction`` / ``on_inference_finalized``
/ …); SDK capability arrives as the ``Session`` / ``Interaction`` / ``Inference``
passed into them. Then host it, one Brain instance per session:

- **Inbound (primary):** ``serve_direct(MyBrain, host=..., port=...)`` — PyGato
  dials your WebSocket route per session. Cloud Run / any backend can expose it.
- **Outbound (fallback, localhost/egress-only):** ``serve(MyBrain, api_key=...,
  cortex_url=...)`` — your process dials the Cortex relay.

The same Brain runs on either transport; a config change picks which. Installing
this SDK pulls **no** ``pipecat`` dependency — the wire is plain protobuf and the
Brain surface is plain dataclasses.

See [docs/architecture.md](docs/architecture.md) for the model and
docs/voice-protocol.md §SDK for the design.
"""

from .actions import Action
from .brain import (
    Brain,
    ClientMessage,
    Conversation,
    IdleInfo,
    Inference,
    Interaction,
    InteractionSource,
    Message,
    Outcome,
    Session,
    SessionStart,
    adapter_for,
    brain_factory,
    make_agent,
    make_direct_agent,
    serve,
    serve_auto,
    serve_direct,
)
from .inbound import DirectAgent
from .outbound import CortexAgent
from .session import Channel, SessionRejected, run_session

__all__ = [
    "Action",
    "Brain",
    "Channel",
    "ClientMessage",
    "Conversation",
    "CortexAgent",
    "DirectAgent",
    "IdleInfo",
    "Inference",
    "Interaction",
    "InteractionSource",
    "Message",
    "Outcome",
    "Session",
    "SessionRejected",
    "SessionStart",
    "adapter_for",
    "brain_factory",
    "make_agent",
    "make_direct_agent",
    "run_session",
    "serve",
    "serve_auto",
    "serve_direct",
]
