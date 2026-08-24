"""The wire — plain-dataclass frames, protobuf serializer, transport.

Pipecat-free: installing the SDK pulls no ``pipecat`` dependency. Only protobuf
``Envelope`` bytes cross the socket; the frame classes here never do.

Public surface:
- The frame dataclasses plus ``Frame``, and the enums they carry —
  ``FinalizeReason``, ``ErrorCode``, ``RTVIType``.
- ``Config`` and its three sections, the ``Voice`` and ``Language`` catalogs,
  ``SPEAKABLE``, and ``ConfigError`` — one configuration type, shared with the
  agent record that stores a session's defaults.
- ``WireSerializer`` — the protobuf serializer.
- ``WIRE_VERSION`` — the wire version this build speaks.
- ``MultiplexedWire``, ``WireConfig``, ``PermanentClose`` — websocket transport
  with reconnect. ``AuthRejected`` (a ``PermanentClose``) is the
  handshake-refused case: a credential Cortex answers 401/403 to is never
  retried.
- ``UnsupportedFrameError``, ``MalformedFrameError`` — fail-loud signaling.
"""

from .frames import (
    SPEAKABLE,
    WIRE_VERSION,
    CancelFrame,
    Config,
    ConfigError,
    ConfigureFrame,
    ConfigureRequest,
    EndFrame,
    ErrorCode,
    ErrorFrame,
    FinalizeFrame,
    FinalizeReason,
    Frame,
    IdleConfig,
    InterruptionFrame,
    Language,
    ResponseFrame,
    RTVIFrame,
    RTVIType,
    SessionStartFrame,
    SpeechChunkFrame,
    SpeechEndFrame,
    SpeechStartFrame,
    SttConfig,
    TtsConfig,
    UserIdleFrame,
    UserMessageFrame,
    Voice,
)
from .serializer import (
    MalformedFrameError,
    UnsupportedFrameError,
    WireSerializer,
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
    "SPEAKABLE",
    "WIRE_VERSION",
    "AuthRejected",
    "CancelFrame",
    "Config",
    "ConfigError",
    "ConfigureFrame",
    "ConfigureRequest",
    "EndFrame",
    "ErrorCode",
    "ErrorFrame",
    "FinalizeFrame",
    "FinalizeReason",
    "Frame",
    "IdleConfig",
    "InterruptionFrame",
    "Language",
    "MalformedFrameError",
    "MultiplexedWire",
    "PermanentClose",
    "RTVIFrame",
    "RTVIType",
    "ResponseFrame",
    "SessionStartFrame",
    "SpeechChunkFrame",
    "SpeechEndFrame",
    "SpeechStartFrame",
    "SttConfig",
    "TtsConfig",
    "UnsupportedFrameError",
    "UserIdleFrame",
    "UserMessageFrame",
    "Voice",
    "Wire",
    "WireClosed",
    "WireConfig",
    "WireSerializer",
]
