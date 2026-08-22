"""The wire — plain-dataclass frames, protobuf codec, transport.

Pipecat-free: installing the SDK pulls no ``pipecat`` dependency. Only protobuf
``Envelope`` bytes cross the socket; the frame classes here never do.

Public surface:
- The frame dataclasses plus ``Frame``.
- ``CortexFrameSerializer`` — the protobuf codec; ``DecodedMessage`` carries a
  decoded frame beside the envelope's ``epoch`` / ``speech_id``.
- ``WIRE_VERSION`` — the wire version this build speaks.
- ``MultiplexedWire``, ``WireConfig``, ``PermanentClose`` — websocket transport
  with reconnect. ``AuthRejected`` (a ``PermanentClose``) is the
  handshake-refused case: a credential Cortex answers 401/403 to is never
  retried.
- ``UnsupportedFrameError``, ``MalformedFrameError`` — fail-loud signaling.
"""

from .frames import (
    WIRE_VERSION,
    BrowserCommandFrame,
    BrowserMessageFrame,
    CancelFrame,
    ConfigureIdleFrame,
    ConfigureRequest,
    ConfigureSttFrame,
    ConfigureTtsFrame,
    EndFrame,
    ErrorFrame,
    FinalizeFrame,
    FinalizeReason,
    Frame,
    InterruptionFrame,
    ResponseFrame,
    SessionStartFrame,
    SpeechChunkFrame,
    SpeechEndFrame,
    SpeechStartFrame,
    UserIdleFrame,
    UserMessageFrame,
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
    "WIRE_VERSION",
    "AuthRejected",
    "BrowserCommandFrame",
    "BrowserMessageFrame",
    "CancelFrame",
    "ConfigureIdleFrame",
    "ConfigureRequest",
    "ConfigureSttFrame",
    "ConfigureTtsFrame",
    "CortexFrameSerializer",
    "DecodedMessage",
    "EndFrame",
    "ErrorFrame",
    "FinalizeFrame",
    "FinalizeReason",
    "Frame",
    "InterruptionFrame",
    "MalformedFrameError",
    "MultiplexedWire",
    "PermanentClose",
    "ResponseFrame",
    "SessionStartFrame",
    "SpeechChunkFrame",
    "SpeechEndFrame",
    "SpeechStartFrame",
    "UnsupportedFrameError",
    "UserIdleFrame",
    "UserMessageFrame",
    "Wire",
    "WireClosed",
    "WireConfig",
]
