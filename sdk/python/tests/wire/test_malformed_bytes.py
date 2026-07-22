"""Deserializing garbage / unset-oneof envelopes must raise MalformedFrameError."""

import pytest

from voqalize.sdk.wire import CortexFrameSerializer, MalformedFrameError


async def test_text_input_rejected() -> None:
    ser = CortexFrameSerializer()
    with pytest.raises(MalformedFrameError):
        await ser.deserialize("not bytes")  # type: ignore[arg-type]


async def test_garbage_bytes_rejected() -> None:
    ser = CortexFrameSerializer()
    with pytest.raises(MalformedFrameError):
        # Random bytes that don't form a valid protobuf message.
        await ser.deserialize(b"\xff\xff\xff\xff\xff\xff\xff\xff")


async def test_empty_envelope_rejected() -> None:
    """A valid but empty Envelope (no oneof body set) is malformed."""
    ser = CortexFrameSerializer()
    with pytest.raises(MalformedFrameError, match="no body"):
        await ser.deserialize(b"")
