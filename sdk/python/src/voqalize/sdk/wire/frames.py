"""The frame vocabulary carried over the cortex wire.

These are the Python representations; the protobuf encoding lives next door in
``_frames_pb2.py`` and is plumbed by ``serializer.py``. Brains deal in these
dataclasses, never in protobuf objects.

**Pipecat-free.** Every frame is a plain ``@dataclass`` rooted at the local
:class:`Frame` marker, so the SDK carries no pipecat dependency. Only protobuf
``Envelope`` bytes cross the wire; Python class identity never does.

Every frame here is payload and nothing else. Correlation — ``request_id``,
``epoch``, ``inference_id`` — rides the envelope and is threaded alongside a
frame by :mod:`.serializer`, never stored on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from typing import Any


class FrameDirection(IntEnum):
    """Wire direction byte. Values match pipecat's ``FrameDirection`` (the voice
    runtime is pipecat internally): ``DOWNSTREAM=1`` toward the brain / bot
    output, ``UPSTREAM=2`` back."""

    DOWNSTREAM = 1
    UPSTREAM = 2


class Frame:
    """Marker base for every wire frame."""


class FinalizeReason(StrEnum):
    """Why an inference was finalized."""

    COMPLETED = "completed"
    USER_BARGE_IN = "user_barge_in"


# ─── Voice → Brain ────────────────────────────────────────────────────────────


@dataclass
class SessionStartFrame(Frame):
    """First frame of a session. ``payload`` is opaque customer init data."""

    session_id: str = ""
    agent_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


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
class ClientMessageFrame(Frame):
    """A browser-originated message relayed to the brain.

    ``client.sendClientMessage(type, data)`` in the browser arrives here. Every
    message is delivered — the runtime never interprets ``type``. UI-action
    outcomes ride this frame too (``type == "action_outcome"``); the SDK routes
    those to their pending ``action`` callback rather than the generic handler.
    """

    msg_id: str = ""
    type: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class InferenceFinalizedFrame(Frame):
    """What the user actually heard of one inference — never a cross-inference
    concatenation. The inference is the envelope's ``inference_id``."""

    heard_text: str = ""
    reason: FinalizeReason = FinalizeReason.COMPLETED


# ─── Brain → Voice ────────────────────────────────────────────────────────────


@dataclass
class LLMFullResponseStartFrame(Frame):
    """Opens one inference."""


@dataclass
class LLMTextFrame(Frame):
    """One chunk of text within an inference."""

    text: str = ""


@dataclass
class LLMFullResponseEndFrame(Frame):
    """Closes one inference."""


@dataclass
class ServerMessageFrame(Frame):
    """A brain-originated message pushed to the browser (a "UI command")."""

    data: Any = None


@dataclass
class UpdateTTSSettingsFrame(Frame):
    """Mid-session TTS reconfigure (voice / language / model)."""

    settings: dict[str, Any] = field(default_factory=dict)


@dataclass
class UpdateSTTSettingsFrame(Frame):
    """Mid-session STT reconfigure (VAD / turn-detection / model)."""

    settings: dict[str, Any] = field(default_factory=dict)


@dataclass
class UpdateIdleSettingsFrame(Frame):
    """Mid-session idle-detection reconfigure. ``timeout_ms == 0`` disables it."""

    settings: dict[str, Any] = field(default_factory=dict)


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
    ClientMessageFrame,
    InterruptionFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    LLMFullResponseEndFrame,
    InferenceFinalizedFrame,
    ServerMessageFrame,
    UpdateTTSSettingsFrame,
    UpdateSTTSettingsFrame,
    UpdateIdleSettingsFrame,
    EndFrame,
    CancelFrame,
    ErrorFrame,
)
