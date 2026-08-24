"""The frame vocabulary carried over the wire.

These are the Python representations; the protobuf encoding lives next door in
``_frames_pb2.py`` and is plumbed by ``serializer.py``. Brains deal in these
dataclasses, never in protobuf objects.

**Pipecat-free.** Every frame is a plain ``@dataclass`` rooted at the local
:class:`Frame` marker, so the SDK carries no pipecat dependency. Only protobuf
``Envelope`` bytes cross the wire; Python class identity never does.

The wire has two planes. The voice plane — turns, speech units, what the caller
heard, the control leg — is Voqalize's own. The RTVI plane is a tunnel:
:class:`RTVIFrame` carries one whitelisted pipecat RTVI message verbatim.

Every identifier lives on the frame that mints or names it. Nothing rides
alongside.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# The wire version this build speaks. The runtime stamps it on the session's first
# frame and a brain that speaks a different one refuses the session — see
# :meth:`voqalize.sdk.brain._BrainAdapter._start`. The rule for when it moves is
# in frames.proto.
WIRE_VERSION = 3


class Frame:
    """Marker base for every wire frame."""


class FinalizeReason(StrEnum):
    """Why a speech unit was finalized."""

    COMPLETED = "completed"
    USER_BARGE_IN = "user_barge_in"


class ErrorCode(StrEnum):
    """What kind of error an :class:`ErrorFrame` reports."""

    PROTOCOL = "protocol"
    WIRE_VERSION = "wire_version"
    REJECTED = "rejected"
    OVERLOAD = "overload"
    INTERNAL = "internal"


class RTVIType(StrEnum):
    """The RTVI message types that cross the wire, by their RTVI names.

    A type absent here does not cross in either direction. ``bot-*`` and
    ``llm-*`` are the runtime's own assertions about the media and the model,
    and a brain must not be able to forge them.
    """

    SERVER_MESSAGE = "server-message"
    SERVER_RESPONSE = "server-response"
    ERROR_RESPONSE = "error-response"
    UI_COMMAND = "ui-command"
    UI_JOB_GROUP = "ui-job-group"

    CLIENT_MESSAGE = "client-message"
    SEND_TEXT = "send-text"
    UI_EVENT = "ui-event"
    UI_SNAPSHOT = "ui-snapshot"
    UI_CANCEL_JOB_GROUP = "ui-cancel-job-group"


#: RTVI types a brain may send. The app is the only end that originates the
#: others, and the runtime rejects one arriving from a brain.
RTVI_TO_APP = frozenset(
    {
        RTVIType.SERVER_MESSAGE,
        RTVIType.SERVER_RESPONSE,
        RTVIType.ERROR_RESPONSE,
        RTVIType.UI_COMMAND,
        RTVIType.UI_JOB_GROUP,
    }
)

#: RTVI types a brain may receive.
RTVI_TO_BRAIN = frozenset(
    {
        RTVIType.CLIENT_MESSAGE,
        RTVIType.SEND_TEXT,
        RTVIType.UI_EVENT,
        RTVIType.UI_SNAPSHOT,
        RTVIType.UI_CANCEL_JOB_GROUP,
    }
)


# ─── Voqalize → Brain ────────────────────────────────────────────────────────────


@dataclass
class SessionStartFrame(Frame):
    """First frame of a session, and the session's first turn. ``init`` is
    opaque customer init data."""

    turn_id: int = 0
    session_id: str = ""
    init: dict[str, Any] = field(default_factory=dict)
    wire_version: int = WIRE_VERSION


@dataclass
class UserMessageFrame(Frame):
    """A committed user stimulus, on a turn of its own. Text-only today."""

    turn_id: int = 0
    text: str = ""


@dataclass
class UserIdleFrame(Frame):
    """The user went silent past the idle timeout and the runtime handed the
    brain the floor to re-engage. ``level`` counts consecutive escalations
    without intervening speech (1 = first nudge); ``idle_ms`` is the silence
    elapsed when it fired."""

    turn_id: int = 0
    level: int = 1
    idle_ms: int = 0


@dataclass
class InterruptionFrame(Frame):
    """The barge-in watermark: everything through ``through_turn`` is dead, so
    the brain stops generating for it. Monotone and unacknowledged — a brain
    that misses one is corrected by the next."""

    through_turn: int = 0


@dataclass
class FinalizeFrame(Frame):
    """What the user actually heard of one speech unit — never a cross-unit
    concatenation."""

    speech_id: int = 0
    heard_text: str = ""
    reason: FinalizeReason = FinalizeReason.COMPLETED


# ─── Brain → Voqalize ────────────────────────────────────────────────────────────


@dataclass
class SpeechStartFrame(Frame):
    """Opens one speech unit and binds it to the turn it answers."""

    speech_id: int = 0
    turn_id: int = 0


@dataclass
class SpeechChunkFrame(Frame):
    """One chunk of text within a speech unit."""

    speech_id: int = 0
    text: str = ""


@dataclass
class SpeechEndFrame(Frame):
    """Closes one speech unit."""

    speech_id: int = 0


# ─── The control leg ──────────────────────────────────────────────────────────
#
# One request out, exactly one response back, on every op. ``request_id`` names
# that pair and nothing else. Every other field is optional and means "leave this
# alone" when unset, so a request carries only what the brain asked to change.


@dataclass
class ConfigureTtsFrame(Frame):
    """Retune the voice. Brain → Voqalize."""

    request_id: int = 0
    voice: str | None = None
    language: str | None = None
    model: str | None = None
    speed: float | None = None


@dataclass
class ConfigureSttFrame(Frame):
    """Retune the recognizer. Brain → Voqalize.

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
    """Voqalize's answer to one request. ``detail`` is empty on acceptance."""

    request_id: int = 0
    accepted: bool = True
    detail: str = ""


#: Every frame that carries a request. Each has a ``request_id``, and exactly one
#: :class:`ResponseFrame` names it back.
ConfigureRequest = ConfigureTtsFrame | ConfigureSttFrame | ConfigureIdleFrame


# ─── The RTVI plane ───────────────────────────────────────────────────────────


@dataclass
class RTVIFrame(Frame):
    """One RTVI message, tunnelled. ``data`` is the RTVI payload and travels
    opaque; ``id`` is RTVI's own correlation id, present on requests and the
    responses that name them.

    ``turn_id`` annotates traces only. The brain may set it on what it sends;
    the runtime never sets it inbound and never passes it on to the app.
    """

    type: RTVIType = RTVIType.SERVER_MESSAGE
    data: Any = None
    id: str | None = None
    turn_id: int | None = None


# ─── Lifecycle ────────────────────────────────────────────────────────────────


@dataclass
class EndFrame(Frame):
    """Graceful end-of-session. Rides the bulk lane, draining behind data."""


@dataclass
class CancelFrame(Frame):
    """Abrupt session cancel."""

    reason: str | None = None


@dataclass
class ErrorFrame(Frame):
    """Non-fatal or fatal error surfaced to the peer. The SDK emits this on
    bulk-lane overflow as a drop-newest congestion signal."""

    code: ErrorCode = ErrorCode.INTERNAL
    message: str = ""
    fatal: bool = False


# ─── Lane routing ─────────────────────────────────────────────────────────────
#
# Two orthogonal questions. **Priority** is about ordering: the priority lane
# carries session control that must bypass queued data, and nothing on it has an
# ordering relationship with what it overtakes. **Droppability** is about
# backpressure: only the two unbounded flows — speech chunks and the RTVI
# tunnel — are shed when a lane fills. Everything else is bounded by turns taken
# and units spoken, so it is queued however deep the backlog runs.
#
# ``End`` is on neither list: it rides the bulk lane in order, so a session tears
# down only after its queued data drains.

_PRIORITY_FRAMES: tuple[type, ...] = (SessionStartFrame, InterruptionFrame, CancelFrame)

_DROPPABLE_FRAMES: tuple[type, ...] = (SpeechChunkFrame, RTVIFrame)


def is_priority(frame: Frame) -> bool:
    """True for frames that ride the priority lane, ahead of queued data."""
    return isinstance(frame, _PRIORITY_FRAMES)


def is_droppable(frame: Frame) -> bool:
    """True for frames a full bulk lane may shed."""
    return isinstance(frame, _DROPPABLE_FRAMES)


# ─── Registry (used by the serializer's completeness check) ───────────────────

WIRE_FRAME_CLASSES: tuple[type[Frame], ...] = (
    SessionStartFrame,
    UserMessageFrame,
    UserIdleFrame,
    InterruptionFrame,
    FinalizeFrame,
    SpeechStartFrame,
    SpeechChunkFrame,
    SpeechEndFrame,
    ConfigureTtsFrame,
    ConfigureSttFrame,
    ConfigureIdleFrame,
    ResponseFrame,
    RTVIFrame,
    EndFrame,
    CancelFrame,
    ErrorFrame,
)
