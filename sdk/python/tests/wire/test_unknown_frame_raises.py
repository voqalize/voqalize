"""Serializing a frame the dispatch table doesn't know must raise."""

from dataclasses import dataclass

import pytest

from voqalize.sdk.wire import CortexFrameSerializer, Frame, UnsupportedFrameError


@dataclass
class NotInDispatchFrame(Frame):
    blah: str = ""


async def test_unsupported_frame_raises() -> None:
    ser = CortexFrameSerializer()
    with pytest.raises(UnsupportedFrameError):
        await ser.serialize(NotInDispatchFrame(blah="x"))
