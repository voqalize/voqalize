"""The two opaque fields — ``SessionStart.init`` and ``RTVI.data`` — survive
round-trip with nested structure intact.

They are the only untyped things on the wire, and they are untyped because each
carries an application's own shape: ``init`` is the customer's, ``data`` is
RTVI's. Everything else, the control leg included, is a declared field.
"""

from voqalize.sdk.wire import (
    RTVIFrame,
    RTVIType,
    SessionStartFrame,
    WireSerializer,
)


async def test_nested_init_roundtrip() -> None:
    ser = WireSerializer()
    frame = SessionStartFrame(
        turn_id=1,
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


async def test_rtvi_data_roundtrip() -> None:
    ser = WireSerializer()
    frame = RTVIFrame(
        type=RTVIType.CLIENT_MESSAGE,
        data={"t": "form_submitted", "d": {"rows": [{"id": 1}], "meta": {"ms": 12.5}}},
        id="req-7",
    )
    out = await ser.deserialize(await ser.serialize(frame))
    assert isinstance(out, RTVIFrame)
    assert out.data == frame.data
    assert out.id == frame.id


async def test_rtvi_data_need_not_be_a_dict() -> None:
    """RTVI owns the payload's shape, and RTVI does not promise an object."""
    ser = WireSerializer()
    for payload in ([1, 2, 3], "plain", 7, True):
        out = await ser.deserialize(
            await ser.serialize(RTVIFrame(type=RTVIType.UI_EVENT, data=payload))
        )
        assert isinstance(out, RTVIFrame)
        assert out.data == payload
