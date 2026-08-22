"""The three opaque dict fields — ``SessionStart.init``, ``ClientMessage.data``
and ``ServerMessage.data`` — survive round-trip with nested structure intact.

They are the only untyped things on the wire, and they are untyped because each
carries an application's own shape. Everything else, the control leg included, is
a declared field.
"""

from voqalize.sdk.wire import (
    BrowserCommandFrame,
    BrowserMessageFrame,
    CortexFrameSerializer,
    SessionStartFrame,
)


async def test_nested_init_roundtrip() -> None:
    ser = CortexFrameSerializer()
    frame = SessionStartFrame(
        session_id="s",
        init={
            "k1": "v1",
            "n": 42,
            "flag": True,
            "nested": {"deeper": {"list": [1, "two", {"three": 3.5}]}},
        },
    )
    out = await ser.deserialize(await ser.serialize(frame))
    assert isinstance(out, SessionStartFrame)
    assert out.init == frame.init


async def test_browser_message_data_roundtrip() -> None:
    ser = CortexFrameSerializer()
    frame = BrowserMessageFrame(
        type="form_submitted",
        data={"rows": [{"id": 1}, {"id": 2}], "total": 2, "meta": {"ms": 12.5}},
    )
    out = await ser.deserialize(await ser.serialize(frame))
    assert isinstance(out, BrowserMessageFrame)
    assert out.data == frame.data


async def test_browser_command_data_roundtrip() -> None:
    ser = CortexFrameSerializer()
    frame = BrowserCommandFrame(data={"ui": "open_panel", "args": [1, {"deep": True}]})
    out = await ser.deserialize(await ser.serialize(frame))
    assert isinstance(out, BrowserCommandFrame)
    assert out.data == frame.data
