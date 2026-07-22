"""Vql frame vocabulary carried over the cortex wire.

These are the *Python* representations. The protobuf encoding lives next door
in ``_frames_pb2.py`` and is plumbed by ``serializer.py``. Customer agents and
the pygato pipeline both deal in these dataclasses — never in protobuf objects.

**Pipecat-free.** Every frame here is a plain ``@dataclass`` rooted at the local
:class:`Frame` marker — the SDK carries no ``pipecat`` dependency. The wire only
ever moves protobuf ``Envelope`` bytes, so the Python class identity never
crosses the wire; pipecat's own frame hierarchy lives entirely inside PyGato, on
the far side of the socket, and is irrelevant here. (This mirrors the Go SDK's
``wire/codec.go``, where the same frames are plain Go structs.)

Two keys identify everything (see ``docs/voice-protocol.md``):

- ``interaction_id`` — Voice-minted, session-monotonic. One committed user
  stimulus (utterance or action) + the brain's full response.
- ``inference_id`` — Brain-minted, per-interaction. One LLM call (pipecat's
  "assistant turn"). One interaction → N inferences.

``(interaction_id, inference_id)`` is the unique composite key. Both are
``uint64`` typed fields — never a dotted string on the wire.

Interruption rides the wire as a field-less :class:`InterruptionFrame` (both
directions), so barge-in's cancel+reset is symmetric on both sides. Correlation
lives on the data frames (``inference_id``), not on the interrupt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from typing import Any


class FrameDirection(IntEnum):
    """Wire direction byte. Values MUST match pipecat's ``FrameDirection`` enum
    (PyGato is still pipecat internally) and the Go SDK's ``wire.Direction``:
    ``DOWNSTREAM=1`` (toward the brain / bot output), ``UPSTREAM=2`` (back)."""

    DOWNSTREAM = 1
    UPSTREAM = 2


class Frame:
    """Marker base for every wire frame. Not a pipecat type."""


class FinalizeReason(StrEnum):
    """Why an inference was finalized.

    ``interrupted == True`` iff ``reason == USER_BARGE_IN``; both are carried
    because consumers key off either the bool (cheap) or the reason (extensible).
    """

    COMPLETED = "completed"
    USER_BARGE_IN = "user_barge_in"


# ─── Lifecycle / control frames (pipecat-free twins) ──────────────────────────
#
# These used to be imported from pipecat (``StartFrame``, ``EndFrame``,
# ``CancelFrame``, ``ErrorFrame``, ``InterruptionFrame``, the RTVI pair, and the
# STT/TTS update-settings frames). The SDK now owns plain-dataclass equivalents;
# the protobuf codec transcodes them the same way. Field names/semantics are
# preserved so PyGato (still pipecat) and the SDK agree on the wire.


@dataclass
class VqlStartFrame(Frame):
    """First frame on the wire for a session.

    Carries the session/agent identity and an opaque ``payload`` dict the brain
    reads on session boot, plus the media/metrics flags PyGato's ``StartFrame``
    used to carry (kept for wire parity — the SDK itself ignores most of them).
    """

    session_id: str = ""
    agent_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    audio_in_sample_rate: int = 0
    audio_out_sample_rate: int = 0
    enable_metrics: bool = False
    enable_tracing: bool = False
    enable_usage_metrics: bool = False
    report_only_initial_ttfb: bool = False


@dataclass
class EndFrame(Frame):
    """Graceful end-of-session. Rides the NORMAL lane (drains behind data)."""


@dataclass
class CancelFrame(Frame):
    """Abrupt session cancel. System lane."""

    reason: str | None = None


@dataclass
class InterruptionFrame(Frame):
    """Field-less barge-in / drain-barrier signal, both directions. System lane."""


@dataclass
class ErrorFrame(Frame):
    """Non-fatal (``fatal=False``) or fatal error surfaced to the peer.

    The SDK emits this on normal-lane overflow (drop-newest congestion signal),
    matching the Go SDK's ``DeliverError``.
    """

    error: str = ""
    fatal: bool = False


@dataclass
class STTUpdateSettingsFrame(Frame):
    """Mid-session STT reconfigure (VAD / turn-detection / model). Brain → Voice."""

    settings: dict[str, Any] = field(default_factory=dict)


@dataclass
class TTSUpdateSettingsFrame(Frame):
    """Mid-session TTS reconfigure (voice / language / model). Brain → Voice."""

    settings: dict[str, Any] = field(default_factory=dict)


@dataclass
class RTVIClientMessageFrame(Frame):
    """A browser-originated RTVI client message relayed to the brain.

    ``client.sendClientMessage(type, data)`` in the browser → PyGato → here.
    Also carries UI-action outcomes (``type == "action_outcome"``).
    """

    msg_id: str = ""
    type: str = ""
    data: Any = None


@dataclass
class RTVIServerMessageFrame(Frame):
    """A brain-originated message pushed to the browser (a "UI command")."""

    data: Any = None


# ─── User stimulus ────────────────────────────────────────────────────────────


@dataclass
class VqlUserTextFrame(Frame):
    """Committed user utterance opening an interaction.

    Emitted DOWNSTREAM by ``UserContextAggregator``, which mints the
    session-monotonic ``interaction_id``. The brain stamps its responses with
    this ``interaction_id`` plus its own per-interaction ``inference_id``.
    """

    interaction_id: int = 0
    text: str = ""


@dataclass
class VqlInferenceFinalizedFrame(Frame):
    """Per-inference finalize: the text the user actually heard for ONE inference.

    Never a cross-inference concatenation. ``heard_text`` is the playout-gated
    accumulation of the inference identified by ``(interaction_id, inference_id)``.
    Emitted UPSTREAM by ``AssistantContextAggregator`` on ``BotStoppedSpeaking``
    (clean) or barge-in (``interrupted=True``).
    """

    interaction_id: int = 0
    inference_id: int = 0
    heard_text: str = ""
    interrupted: bool = False
    reason: FinalizeReason = FinalizeReason.COMPLETED


# ─── LLM response ─────────────────────────────────────────────────────────────


@dataclass
class VqlLLMFullResponseStartFrame(Frame):
    """Start of one bot LLM inference."""

    interaction_id: int = 0
    inference_id: int = 0


@dataclass
class VqlLLMTextFrame(Frame):
    """One chunk of LLM text within an inference. Many of these per inference."""

    interaction_id: int = 0
    inference_id: int = 0
    text: str = ""


@dataclass
class VqlLLMFullResponseEndFrame(Frame):
    """End of one bot LLM inference."""

    interaction_id: int = 0
    inference_id: int = 0


# ─── Function calls ───────────────────────────────────────────────────────────


@dataclass
class VqlFunctionCallsStartedFrame(Frame):
    """The model has decided to call a tool. Arguments are JSON-encoded on the wire."""

    interaction_id: int = 0
    inference_id: int = 0
    tool_call_id: str = ""
    function_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class VqlFunctionCallInProgressFrame(Frame):
    """Mid-flight tool call announcement (used by the UI to render a spinner)."""

    interaction_id: int = 0
    inference_id: int = 0
    tool_call_id: str = ""
    function_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class VqlFunctionCallResultFrame(Frame):
    """Result of a tool call. ``result`` is JSON-encoded on the wire."""

    interaction_id: int = 0
    inference_id: int = 0
    tool_call_id: str = ""
    function_name: str = ""
    result: dict[str, Any] = field(default_factory=dict)


# ─── Interaction completion ───────────────────────────────────────────────────


@dataclass
class VqlInteractionCompletedFrame(Frame):
    """Brain → Voice: the brain is done responding to the whole interaction.

    Emitted when ``on_interaction`` returns cleanly. Barge-in **skips** this —
    Voice finalizes the cut inference directly. Idempotent per ``interaction_id``.
    """

    interaction_id: int = 0


# ─── Lane routing ─────────────────────────────────────────────────────────────

# The priority (system) lane carries session-control signals that must bypass
# queued data. Matches the Go SDK's ``wire.IsSystem``: ``End`` is deliberately
# NOT system — it rides the normal lane so a session tears down only after its
# queued data has drained.
_SYSTEM_FRAMES: tuple[type, ...] = (VqlStartFrame, InterruptionFrame, CancelFrame)


def is_system(frame: Frame) -> bool:
    """True for frames that ride the priority lane (VqlStart / Interruption / Cancel)."""
    return isinstance(frame, _SYSTEM_FRAMES)


# ─── Registry of Vql frame classes (used by serializer + completeness test) ───

VQL_FRAME_CLASSES: tuple[type, ...] = (
    VqlStartFrame,
    VqlUserTextFrame,
    VqlInferenceFinalizedFrame,
    VqlLLMFullResponseStartFrame,
    VqlLLMTextFrame,
    VqlLLMFullResponseEndFrame,
    VqlFunctionCallsStartedFrame,
    VqlFunctionCallInProgressFrame,
    VqlFunctionCallResultFrame,
    VqlInteractionCompletedFrame,
)
