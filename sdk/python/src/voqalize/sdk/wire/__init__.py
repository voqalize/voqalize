"""Cortex wire layer — plain-dataclass frames, protobuf codec, transport.

Pipecat-free: installing the SDK pulls no ``pipecat`` dependency. Only protobuf
``Envelope`` bytes cross the socket; the frame classes here never do.

Public surface:
- The frame dataclasses plus ``Frame``, ``FrameDirection`` (the 1-byte direction
  enum) and ``is_system`` (the lane-routing predicate).
- ``CortexFrameSerializer`` — the protobuf codec; ``DecodedMessage`` carries a
  decoded frame beside the envelope's ``request_id`` / ``epoch`` /
  ``inference_id``.
- ``MultiplexedWire``, ``Wire``, ``WireConfig``, ``PermanentClose`` — websocket
  transport with reconnect. ``AuthRejected`` (a ``PermanentClose``) is the
  handshake-refused case: a credential cortex answers 401/403 to is never
  retried.
- ``UnsupportedFrameError``, ``MalformedFrameError`` — fail-loud signaling.
"""

from .frames import (
    WIRE_FRAME_CLASSES,
    CancelFrame,
    ClientMessageFrame,
    EndFrame,
    ErrorFrame,
    FinalizeReason,
    Frame,
    FrameDirection,
    InferenceFinalizedFrame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    ServerMessageFrame,
    SessionStartFrame,
    UpdateIdleSettingsFrame,
    UpdateSTTSettingsFrame,
    UpdateTTSSettingsFrame,
    UserIdleFrame,
    UserMessageFrame,
    is_system,
)
from .serializer import (
    Ack,
    CortexFrameSerializer,
    DecodedMessage,
    MalformedFrameError,
    UnsupportedFrameError,
    serialize_ack,
)
from .transport import (
    AuthRejected,
    MultiplexedWire,
    PermanentClose,
    Wire,
    WireClosed,
    WireConfig,
)

__all__ = [
    "WIRE_FRAME_CLASSES",
    "Ack",
    "AuthRejected",
    "CancelFrame",
    "ClientMessageFrame",
    "CortexFrameSerializer",
    "DecodedMessage",
    "EndFrame",
    "ErrorFrame",
    "FinalizeReason",
    "Frame",
    "FrameDirection",
    "InferenceFinalizedFrame",
    "InterruptionFrame",
    "LLMFullResponseEndFrame",
    "LLMFullResponseStartFrame",
    "LLMTextFrame",
    "MalformedFrameError",
    "MultiplexedWire",
    "PermanentClose",
    "ServerMessageFrame",
    "SessionStartFrame",
    "UnsupportedFrameError",
    "UpdateIdleSettingsFrame",
    "UpdateSTTSettingsFrame",
    "UpdateTTSSettingsFrame",
    "UserIdleFrame",
    "UserMessageFrame",
    "Wire",
    "WireClosed",
    "WireConfig",
    "is_system",
    "serialize_ack",
]
