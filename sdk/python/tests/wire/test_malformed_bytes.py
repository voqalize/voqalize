"""Deserializing garbage / unset-oneof envelopes must raise MalformedFrameError."""

import pytest

from voqalize.sdk.wire import MalformedFrameError, WireSerializer


async def test_text_input_rejected() -> None:
    ser = WireSerializer()
    with pytest.raises(MalformedFrameError):
        await ser.deserialize("not bytes")  # type: ignore[arg-type]


async def test_garbage_bytes_rejected() -> None:
    ser = WireSerializer()
    with pytest.raises(MalformedFrameError):
        # Random bytes that don't form a valid protobuf message.
        await ser.deserialize(b"\xff\xff\xff\xff\xff\xff\xff\xff")


async def test_empty_envelope_rejected() -> None:
    """A valid but empty Envelope (no oneof body set) is malformed."""
    ser = WireSerializer()
    with pytest.raises(MalformedFrameError, match="no body"):
        await ser.deserialize(b"")
