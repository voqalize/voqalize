"""The frame vocabulary carried over the cortex wire.

These are the Python representations; the protobuf encoding lives next door in
``_frames_pb2.py`` and is plumbed by ``serializer.py``. Brains deal in these
dataclasses, never in protobuf objects.

**Pipecat-free.** Every frame is a plain ``@dataclass`` rooted at the local
:class:`Frame` marker, so the SDK carries no pipecat dependency. Only protobuf
``Envelope`` bytes cross the wire; Python class identity never does.

Every frame here is payload and nothing else. Correlation — ``epoch`` and
``speech_id`` — rides the envelope and is threaded alongside a frame by
:mod:`.serializer`, never stored on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from typing import Any

# The wire version this build speaks. The runtime stamps it on the session's first
# envelope and a brain that speaks a different one refuses the session — see
# :meth:`voqalize.sdk.brain._BrainAdapter._start`. The rule for when it moves is
# in frames.proto.
PROTOCOL_VERSION = 1


class FrameDirection(IntEnum):
    """Wire direction byte. Values match pipecat's ``FrameDirection`` (the voice
    runtime is pipecat internally): ``DOWNSTREAM=1`` toward the brain / bot
    output, ``UPSTREAM=2`` back."""

    DOWNSTREAM = 1
    UPSTREAM = 2


class Frame:
    """Marker base for every wire frame."""


class FinalizeReason(StrEnum):
    """Why a speech unit was finalized."""

    COMPLETED = "completed"
    USER_BARGE_IN = "user_barge_in"


# ─── Voice → Brain ────────────────────────────────────────────────────────────


@dataclass
class SessionStartFrame(Frame):
    """First frame of a session. ``payload`` is opaque customer init data."""

    session_id: str = ""
    agent_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    protocol_version: int = PROTOCOL_VERSION


@dataclass
class UserMessageFrame(Frame):
    """A committed user stimulus. Text-only today."""

    text: str = ""


@dataclass
class UserIdleFrame(Frame):
    """The user went silent past the idle timeout and the runtime handed the
    brain the floor to re-engage. ``level`` counts consecutive escalations
    without intervening speech (1 = first nudge); ``idle_ms`` is the silence
    elapsed when it fired."""

    level: int = 1
    idle_ms: int = 0


@dataclass
class BrowserMessageFrame(Frame):
    """A browser-originated message relayed to the brain.

    ``client.sendClientMessage(type, data)`` in the browser arrives here. Every
    message is delivered — the runtime never interprets ``type``. UI-action
    outcomes ride this frame too (``type == "action_result"``); the SDK routes
    those to their pending ``action`` callback rather than the generic handler.
    """

    type: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class FinalizeFrame(Frame):
    """What the user actually heard of one speech unit — never a cross-unit
    concatenation. The unit is the envelope's ``speech_id``."""

    heard_text: str = ""
    reason: FinalizeReason = FinalizeReason.COMPLETED


# ─── Brain → Voice ────────────────────────────────────────────────────────────


@dataclass
class SpeechStartFrame(Frame):
    """Opens one speech unit."""


@dataclass
class SpeechChunkFrame(Frame):
    """One chunk of text within a speech unit."""

    text: str = ""


@dataclass
class SpeechEndFrame(Frame):
    """Closes one speech unit."""


@dataclass
class BrowserCommandFrame(Frame):
    """A brain-originated command pushed to the browser. The brain drives the
    screen; the runtime relays ``data`` unread."""

    data: Any = None


# ─── The control leg ──────────────────────────────────────────────────────────
#
# One request out, exactly one response back, on every op. ``request_id`` names
# that pair and nothing else. Every other field is optional and means "leave this
# alone" when unset, so a request carries only what the brain asked to change.


@dataclass
class ConfigureTtsFrame(Frame):
    """Retune the voice. Brain → Voice."""

    request_id: int = 0
    voice: str | None = None
    language: str | None = None
    model: str | None = None
    speed: float | None = None


@dataclass
class ConfigureSttFrame(Frame):
    """Retune the recognizer. Brain → Voice.

    ``thresholds`` keys are the schema's own field names, built from what the
    brain set; the serializer rejects a name the schema does not declare.
    """

    request_id: int = 0
    language_hint: str | None = None
    thresholds: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConfigureIdleFrame(Frame):
    """Retune idle detection. ``timeout_ms == 0`` disables it."""

    request_id: int = 0
    timeout_ms: int | None = None


@dataclass
class ResponseFrame(Frame):
    """Voice's answer to one request. ``detail`` is empty on acceptance."""

    request_id: int = 0
    accepted: bool = True
    detail: str = ""


#: Every frame that carries a request. Each has a ``request_id``, and exactly one
#: :class:`ResponseFrame` names it back.
ConfigureRequest = ConfigureTtsFrame | ConfigureSttFrame | ConfigureIdleFrame


# ─── Both directions ──────────────────────────────────────────────────────────


@dataclass
class InterruptionFrame(Frame):
    """Field-less barge-in / drain-barrier signal. System lane."""


@dataclass
class EndFrame(Frame):
    """Graceful end-of-session. Rides the normal lane, draining behind data."""


@dataclass
class CancelFrame(Frame):
    """Abrupt session cancel. System lane."""

    reason: str | None = None


@dataclass
class ErrorFrame(Frame):
    """Non-fatal or fatal error surfaced to the peer. The SDK emits this on
    normal-lane overflow as a drop-newest congestion signal."""

    error: str = ""
    fatal: bool = False


# ─── Lane routing ─────────────────────────────────────────────────────────────

# The priority lane carries session-control signals that must bypass queued
# data. ``End`` is deliberately not here — it rides the normal lane so a session
# tears down only after its queued data has drained.
_SYSTEM_FRAMES: tuple[type, ...] = (SessionStartFrame, InterruptionFrame, CancelFrame)


def is_system(frame: Frame) -> bool:
    """True for frames that ride the priority lane."""
    return isinstance(frame, _SYSTEM_FRAMES)


# ─── Registry (used by the serializer's completeness check) ───────────────────

WIRE_FRAME_CLASSES: tuple[type[Frame], ...] = (
    SessionStartFrame,
    UserMessageFrame,
    UserIdleFrame,
    BrowserMessageFrame,
    InterruptionFrame,
    SpeechStartFrame,
    SpeechChunkFrame,
    SpeechEndFrame,
    FinalizeFrame,
    BrowserCommandFrame,
    ConfigureTtsFrame,
    ConfigureSttFrame,
    ConfigureIdleFrame,
    ResponseFrame,
    EndFrame,
    CancelFrame,
    ErrorFrame,
)
