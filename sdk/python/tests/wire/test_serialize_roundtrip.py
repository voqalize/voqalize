"""Per-frame serializer round-trip: serialize(deserialize) == input."""

from __future__ import annotations

import pytest

from voqalize.sdk.wire import (
    WIRE_VERSION,
    CancelFrame,
    ConfigureIdleFrame,
    ConfigureSttFrame,
    ConfigureTtsFrame,
    EndFrame,
    ErrorCode,
    ErrorFrame,
    FinalizeFrame,
    FinalizeReason,
    Frame,
    InterruptionFrame,
    ResponseFrame,
    RTVIFrame,
    RTVIType,
    SessionStartFrame,
    SpeechChunkFrame,
    SpeechEndFrame,
    SpeechStartFrame,
    UserIdleFrame,
    UserMessageFrame,
    WireSerializer,
)


def _frames() -> list[Frame]:
    return [
        SessionStartFrame(
            turn_id=1,
            session_id="sess-123",
            init={"greet": "hello", "n": 7, "deep": {"k": [1, 2, 3]}},
        ),
        UserMessageFrame(turn_id=4, text="hello there"),
        UserIdleFrame(turn_id=5, level=2, idle_ms=30000),
        InterruptionFrame(through_turn=9),
        FinalizeFrame(speech_id=3, heard_text="ok, scheduled", reason=FinalizeReason.COMPLETED),
        FinalizeFrame(speech_id=4, heard_text="partial...", reason=FinalizeReason.USER_BARGE_IN),
        SpeechStartFrame(speech_id=7, turn_id=4),
        SpeechChunkFrame(speech_id=7, text="hi"),
        SpeechChunkFrame(speech_id=7, text=" world"),
        SpeechEndFrame(speech_id=7),
        RTVIFrame(
            type=RTVIType.SERVER_MESSAGE,
            data={"type": "ui_command", "action": "open_panel", "action_id": "a1"},
            turn_id=4,
        ),
        RTVIFrame(type=RTVIType.CLIENT_MESSAGE, data={"t": "tap", "d": {"id": 3}}, id="req-1"),
        ConfigureTtsFrame(request_id=1, voice="omnivoice/gauri", language="hi", speed=1.25),
        ConfigureSttFrame(
            request_id=2,
            language_hint="hi",
            thresholds={"eot_threshold": 0.75, "eot_timeout_ms": 4000},
        ),
        ConfigureIdleFrame(request_id=3, timeout_ms=0),
        ResponseFrame(request_id=3, accepted=True),
        ResponseFrame(request_id=4, accepted=False, detail="speed must be 0.5 to 2.0"),
        EndFrame(),
        CancelFrame(reason="user_left"),
        CancelFrame(),  # reason=None → empty string on wire
        ErrorFrame(code=ErrorCode.OVERLOAD, message="upstream timeout", fatal=False),
        ErrorFrame(code=ErrorCode.WIRE_VERSION, message="bad wire", fatal=True),
    ]


_FIELDS: dict[type[Frame], tuple[str, ...]] = {
    SessionStartFrame: ("turn_id", "session_id", "init", "wire_version"),
    UserMessageFrame: ("turn_id", "text"),
    UserIdleFrame: ("turn_id", "level", "idle_ms"),
    InterruptionFrame: ("through_turn",),
    FinalizeFrame: ("speech_id", "heard_text", "reason"),
    SpeechStartFrame: ("speech_id", "turn_id"),
    SpeechChunkFrame: ("speech_id", "text"),
    SpeechEndFrame: ("speech_id",),
    RTVIFrame: ("type", "data", "id", "turn_id"),
    ConfigureTtsFrame: ("request_id", "voice", "language", "model", "speed"),
    ConfigureSttFrame: ("request_id", "language_hint", "thresholds"),
    ConfigureIdleFrame: ("request_id", "timeout_ms"),
    ResponseFrame: ("request_id", "accepted", "detail"),
    ErrorFrame: ("code", "message", "fatal"),
    # Field-less frames round-trip to their own type and nothing more.
    EndFrame: (),
}


@pytest.mark.parametrize("frame", _frames(), ids=lambda f: type(f).__name__)
async def test_roundtrip(frame: Frame) -> None:
    ser = WireSerializer()
    payload = await ser.serialize(frame)
    assert isinstance(payload, bytes)

    out = await ser.deserialize(payload)
    assert type(out) is type(frame)

    if isinstance(frame, CancelFrame):
        # CancelFrame.reason: None on input may come back as None or "" — we
        # canonicalize "" → None on decode, so this round-trips.
        assert out.reason == frame.reason
        return

    for field in _FIELDS[type(frame)]:
        assert getattr(out, field) == getattr(frame, field), (
            f"{type(frame).__name__}.{field} differs: "
            f"{getattr(out, field)!r} != {getattr(frame, field)!r}"
        )


async def test_session_start_carries_the_wire_version() -> None:
    """The version is stamped on the session's first frame and nowhere else."""
    ser = WireSerializer()
    out = await ser.deserialize(await ser.serialize(SessionStartFrame(turn_id=1, session_id="s")))
    assert isinstance(out, SessionStartFrame)
    assert out.wire_version == WIRE_VERSION


async def test_rtvi_turn_id_is_absent_when_unset() -> None:
    """``turn_id`` on the RTVI plane annotates traces. Unset means unset — it
    must not decode as turn 0, which is a turn nobody minted."""
    ser = WireSerializer()
    out = await ser.deserialize(
        await ser.serialize(RTVIFrame(type=RTVIType.SERVER_MESSAGE, data={"a": 1}))
    )
    assert isinstance(out, RTVIFrame)
    assert out.turn_id is None
    assert out.id is None


@pytest.mark.parametrize(
    "frame",
    [
        ConfigureTtsFrame(request_id=9),
        ConfigureSttFrame(request_id=9),
        ConfigureIdleFrame(request_id=9),
    ],
    ids=lambda f: type(f).__name__,
)
async def test_an_empty_delta_still_names_its_op(frame: Frame) -> None:
    """A request that changes nothing is a legal no-op the far side answers — so
    the op must survive the trip even when no field is set. Encode it as a bare
    envelope and it would arrive as an unknown operation instead."""
    ser = WireSerializer()
    out = await ser.deserialize(await ser.serialize(frame))
    assert type(out) is type(frame)


async def test_an_undeclared_threshold_is_refused_at_the_sender() -> None:
    """The thresholds dict is the schema's own field names. A name the schema does
    not declare fails here rather than travelling as a key nothing will read."""
    ser = WireSerializer()
    with pytest.raises(AttributeError):
        await ser.serialize(ConfigureSttFrame(request_id=1, thresholds={"patience": 3}))
