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
    IdleUpdateSettingsFrame,
    InterruptionFrame,
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
    VqlRTVIClientMessageFrame,
    VqlStartFrame,
    VqlUserIdleFrame,
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
    "IdleUpdateSettingsFrame",
    "InterruptionFrame",
    "MalformedFrameError",
    "MultiplexedWire",
    "PermanentClose",
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
    "VqlRTVIClientMessageFrame",
    "VqlStartFrame",
    "VqlUserIdleFrame",
    "VqlUserTextFrame",
    "Wire",
    "WireClosed",
    "WireConfig",
    "is_system",
    "serialize_ack",
]
