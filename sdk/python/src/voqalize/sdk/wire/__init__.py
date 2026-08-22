"""Cortex wire layer — plain-dataclass frames, protobuf codec, transport.

Pipecat-free: installing the SDK pulls no ``pipecat`` dependency. Only protobuf
``Envelope`` bytes cross the socket; the frame classes here never do.

Public surface:
- The frame dataclasses plus ``Frame``, ``FrameDirection`` (the 1-byte direction
  enum) and ``is_system`` (the lane-routing predicate).
- ``CortexFrameSerializer`` — the protobuf codec; ``DecodedMessage`` carries a
  decoded frame beside the envelope's ``epoch`` / ``speech_id``.
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
    FinalizeFrame,
    FinalizeReason,
    Frame,
    FrameDirection,
    InterruptionFrame,
    ServerMessageFrame,
    SessionStartFrame,
    SpeechChunkFrame,
    SpeechEndFrame,
    SpeechStartFrame,
    UpdateIdleSettingsFrame,
    UpdateSTTSettingsFrame,
    UpdateTTSSettingsFrame,
    UserIdleFrame,
    UserMessageFrame,
    is_system,
)
from .serializer import (
    CortexFrameSerializer,
    DecodedMessage,
    MalformedFrameError,
    UnsupportedFrameError,
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
    "AuthRejected",
    "CancelFrame",
    "ClientMessageFrame",
    "CortexFrameSerializer",
    "DecodedMessage",
    "EndFrame",
    "ErrorFrame",
    "FinalizeFrame",
    "FinalizeReason",
    "Frame",
    "FrameDirection",
    "InterruptionFrame",
    "MalformedFrameError",
    "MultiplexedWire",
    "PermanentClose",
    "ServerMessageFrame",
    "SessionStartFrame",
    "SpeechChunkFrame",
    "SpeechEndFrame",
    "SpeechStartFrame",
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
]
