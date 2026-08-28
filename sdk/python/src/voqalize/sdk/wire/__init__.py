"""The wire — plain-dataclass frames, protobuf serializer, transport.

Pipecat-free: installing the SDK pulls no ``pipecat`` dependency. Only protobuf
``Envelope`` bytes cross the socket; the frame classes here never do.

Public surface:
- The frame dataclasses plus ``Frame``, and the enums they carry —
  ``ErrorCode`` and ``RTVIType``.
- ``Config`` and its three sections, the ``Voice`` and ``Language`` catalogs,
  and ``ConfigError`` — one configuration type used at session creation and for
  changes made by the brain while the call is running.
- ``WireSerializer`` — the protobuf serializer.
- ``WIRE_VERSION`` — the wire version this build speaks.
- ``MultiplexedWire``, ``WireConfig``, ``PermanentClose`` — websocket transport
  with reconnect. ``AuthRejected`` (a ``PermanentClose``) is the
  handshake-refused case: a credential Cortex answers 401/403 to is never
  retried.
- ``UnsupportedFrameError``, ``MalformedFrameError`` — fail-loud signaling.
"""

from .frames import (
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
