"""Opaque dict fields (SessionStart.payload, ClientMessage.data,
ServerMessage.data, the *Settings frames) survive round-trip with nested
structure intact.
"""

from voqalize.sdk.wire import (
    ClientMessageFrame,
    CortexFrameSerializer,
    ServerMessageFrame,
    SessionStartFrame,
    UpdateTTSSettingsFrame,
)


async def test_nested_payload_roundtrip() -> None:
    ser = CortexFrameSerializer()
    frame = SessionStartFrame(
        session_id="s",
        agent_id="a",
        payload={
            "k1": "v1",
            "n": 42,
            "flag": True,
            "nested": {"deeper": {"list": [1, "two", {"three": 3.5}]}},
        },
    )
    out = await ser.deserialize(await ser.serialize(frame))
    assert isinstance(out, SessionStartFrame)
    assert out.payload == frame.payload


async def test_client_message_data_roundtrip() -> None:
    ser = CortexFrameSerializer()
    frame = ClientMessageFrame(
        msg_id="m-1",
        type="form_submitted",
        data={"rows": [{"id": 1}, {"id": 2}], "total": 2, "meta": {"ms": 12.5}},
    )
    out = await ser.deserialize(await ser.serialize(frame))
    assert isinstance(out, ClientMessageFrame)
    assert out.data == frame.data


async def test_server_message_data_roundtrip() -> None:
    ser = CortexFrameSerializer()
    frame = ServerMessageFrame(data={"ui": "open_panel", "args": [1, {"deep": True}]})
    out = await ser.deserialize(await ser.serialize(frame))
    assert isinstance(out, ServerMessageFrame)
    assert out.data == frame.data


async def test_settings_roundtrip() -> None:
    ser = CortexFrameSerializer()
    frame = UpdateTTSSettingsFrame(settings={"voice": "omnivoice/gauri", "speed": 1.05})
    out = await ser.deserialize(await ser.serialize(frame))
    assert isinstance(out, UpdateTTSSettingsFrame)
    assert out.settings == frame.settings
