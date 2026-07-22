"""Cortex wire layer — plain-dataclass frames + protobuf serializer + transport.

Pipecat-free: installing the SDK pulls no ``pipecat`` dependency. The wire only
ever moves protobuf ``Envelope`` bytes; the frame *classes* here are plain
dataclasses that never cross the socket.

Public surface:
- ``Frame`` + the ``Vql*Frame`` / lifecycle / RTVI dataclasses — the wire's frame
  vocabulary. ``FrameDirection`` — the 1-byte direction enum. ``is_system`` — the
  lane-routing predicate.
- ``CortexFrameSerializer`` — protobuf transcoder (plain class).
- ``MultiplexedWire``, ``Wire``, ``WireConfig``, ``PermanentClose`` — websocket
  transport with reconnect.
- ``UnsupportedFrameError``, ``MalformedFrameError`` — fail-loud signaling.
"""

from .frames import (
    VQL_FRAME_CLASSES,
    CancelFrame,
    EndFrame,
    ErrorFrame,
    FinalizeReason,
    Frame,
    FrameDirection,
    InterruptionFrame,
    RTVIClientMessageFrame,
    RTVIServerMessageFrame,
    STTUpdateSettingsFrame,
    TTSUpdateSettingsFrame,
    VqlFunctionCallInProgressFrame,
    VqlFunctionCallResultFrame,
    VqlFunctionCallsStartedFrame,
    VqlInferenceFinalizedFrame,
    VqlInteractionCompletedFrame,
    VqlLLMFullResponseEndFrame,
    VqlLLMFullResponseStartFrame,
    VqlLLMTextFrame,
    VqlStartFrame,
    VqlUserTextFrame,
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
from .transport import MultiplexedWire, PermanentClose, Wire, WireClosed, WireConfig

__all__ = [
    "VQL_FRAME_CLASSES",
    "Ack",
    "CancelFrame",
    "CortexFrameSerializer",
    "DecodedMessage",
    "EndFrame",
    "ErrorFrame",
    "FinalizeReason",
    "Frame",
    "FrameDirection",
    "InterruptionFrame",
    "MalformedFrameError",
    "MultiplexedWire",
    "PermanentClose",
    "RTVIClientMessageFrame",
    "RTVIServerMessageFrame",
    "STTUpdateSettingsFrame",
    "TTSUpdateSettingsFrame",
    "UnsupportedFrameError",
    "VqlFunctionCallInProgressFrame",
    "VqlFunctionCallResultFrame",
    "VqlFunctionCallsStartedFrame",
    "VqlInferenceFinalizedFrame",
    "VqlInteractionCompletedFrame",
    "VqlLLMFullResponseEndFrame",
    "VqlLLMFullResponseStartFrame",
    "VqlLLMTextFrame",
    "VqlStartFrame",
    "VqlUserTextFrame",
    "Wire",
    "WireClosed",
    "WireConfig",
    "is_system",
    "serialize_ack",
]
