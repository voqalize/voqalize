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

    session_id: str = ""
    turn_id: int = 0
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
    concatenation.

    ``heard_text`` is a verbatim prefix of the text this unit generated, which is
    why the frame carries nothing else: equal means it played out, shorter means
    it was cut off, and the brain is the end that holds the other half of the
    comparison. :class:`voqalize.sdk.Finalize` makes it for you.
    """

    speech_id: int = 0
    heard_text: str = ""


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
# One request out, exactly one response back. ``request_id`` names that pair and
# nothing else.
#
# The surface is deliberately narrow — voice and language, and nothing else. The
# recognizer's thresholds are not settable from here; they keep the runtime's own
# defaults. A knob is far easier to add than to take back.


class Voice(StrEnum):
    """The voices a session can speak in.

    The value is the voice id the speech tier knows. The engine is chosen by the
    voice, not by a separate model field.
    """

    OMNIVOICE_GAURI = "omnivoice/gauri"
    OMNIVOICE_GAURAV = "omnivoice/gaurav"


class Language(StrEnum):
    """The languages a session can be conducted in.

    The value is the code the speech tier wants. It is ISO 639-1 where a
    two-letter code exists and 639-3 where none does — six of these have no
    two-letter code, so the set is not uniform and the *name* is the language,
    not the code.

    Enumerated rather than free strings so a language we do not serve cannot be
    named at all. It used to be nameable, and an unserved one fell back to the
    English recognizer instead of failing.
    """

    EN = "en"
    AS = "as"
    BN = "bn"
    BRX = "brx"
    DOI = "doi"
    GU = "gu"
    HI = "hi"
    KN = "kn"
    KOK = "kok"
    KS = "ks"
    MAI = "mai"
    ML = "ml"
    MNI = "mni"
    MR = "mr"
    NE = "ne"
    OR = "or"
    PA = "pa"
    SA = "sa"
    SAT = "sat"
    SD = "sd"
    TA = "ta"
    TE = "te"
    UR = "ur"


@dataclass(frozen=True)
class TtsConfig:
    """How the session speaks. Applies to the next speech unit, never
    mid-utterance.

    ``language`` names a recorded speaker, not a text tag. The speech tier has
    reference clips for some of these languages and not others; which is which
    is its business and it changes as clips are recorded, so a language it
    cannot speak comes back as a rejected :class:`ResponseFrame` saying so
    rather than being refused here from a stale copy of the roster.
    """

    voice: Voice | None = None
    language: Language | None = None


@dataclass(frozen=True)
class SttConfig:
    """How the session listens. Applies once the open turn commits, never
    mid-utterance."""

    language: Language | None = None


@dataclass(frozen=True)
class IdleConfig:
    """When the brain gets the floor back. ``timeout_ms == 0`` disables idle
    detection."""

    timeout_ms: int | None = None


class ConfigError(ValueError):
    """A configuration the runtime would refuse, refused here instead.

    Raised where the brain wrote it rather than one round trip later, because a
    rejected request costs a turn to find out about.
    """


@dataclass(frozen=True)
class Config:
    """One configuration, three sections.

    The same shape the agent record stores as the session's defaults, which is
    why there is one type rather than two — a record cannot drift from the wire
    if there is only one definition of what a configuration is.

    "Unset" means *leave it alone* here, and *take Voqalize's default* in the
    record. A section left ``None`` is untouched; a field left ``None`` inside a
    section it is present in is untouched too.

    Both legs carry their own language, and that is not duplication. Fewer
    languages can be spoken than understood, so understanding Odia while
    speaking with the Hindi clip is a real configuration and needs two fields to
    say. The guard is therefore not that they agree, it is that you **stated
    both**::

        Config(
            stt=SttConfig(language=Language.OR),   # listen in Odia
            tts=TtsConfig(language=Language.HI),   # speak with the Hindi clip
        )

    Naming a language on one leg and not the other raises :class:`ConfigError`.
    Changing only the voice touches no language field and is unaffected.
    """

    tts: TtsConfig | None = None
    stt: SttConfig | None = None
    idle: IdleConfig | None = None

    def __post_init__(self) -> None:
        spoken = self.tts.language if self.tts is not None else None
        heard = self.stt.language if self.stt is not None else None
        if (spoken is None) != (heard is None):
            named, missing = ("tts", "stt") if spoken is not None else ("stt", "tts")
            raise ConfigError(
                f"This configuration sets {named}.language but not {missing}.language. "
                f"A language has two legs — the recognizer and the recorded speaker — "
                f"and moving one without the other is silent: the words stay right and "
                f"only the voice is wrong. Set both, even when they differ."
            )


@dataclass
class ConfigureFrame(Frame):
    """Override the session's configuration mid-call. Brain → Voqalize.

    The session already starts from the agent record's defaults, so this is for
    a condition that changed during the call — not for initialization.
    """

    request_id: int = 0
    config: Config = field(default_factory=Config)


@dataclass
class ResponseFrame(Frame):
    """Voqalize's answer to one request. ``detail`` is empty on acceptance."""

    request_id: int = 0
    accepted: bool = True
    detail: str = ""


#: Every frame that carries a request. Each has a ``request_id``, and exactly one
#: :class:`ResponseFrame` names it back.
ConfigureRequest = ConfigureFrame


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
    ConfigureFrame,
    ResponseFrame,
    RTVIFrame,
    EndFrame,
    CancelFrame,
    ErrorFrame,
)
