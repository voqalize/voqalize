"""Per-frame serializer round-trip: serialize(deserialize) == input."""

from __future__ import annotations

import pytest

from voqalize.sdk.wire import (
    BrowserCommandFrame,
    BrowserMessageFrame,
    CancelFrame,
    ConfigureIdleFrame,
    ConfigureSttFrame,
    ConfigureTtsFrame,
    CortexFrameSerializer,
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


def _frames() -> list[Frame]:
    return [
        SessionStartFrame(
            session_id="sess-123",
            agent_id="welcome",
            payload={"greet": "hello", "n": 7, "deep": {"k": [1, 2, 3]}},
        ),
        UserMessageFrame(text="hello there"),
        UserIdleFrame(level=2, idle_ms=30000),
        BrowserMessageFrame(type="form_submitted", data={"field": "email"}),
        InterruptionFrame(),
        FinalizeFrame(heard_text="ok, scheduled", reason=FinalizeReason.COMPLETED),
        FinalizeFrame(heard_text="partial...", reason=FinalizeReason.USER_BARGE_IN),
        SpeechStartFrame(),
        SpeechChunkFrame(text="hi"),
        SpeechChunkFrame(text=" world"),
        SpeechEndFrame(),
        BrowserCommandFrame(data={"ui": "open_panel", "args": {"id": 3}}),
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
        ErrorFrame(error="upstream timeout", fatal=False),
        ErrorFrame(error="bad config", fatal=True),
    ]


_FIELDS: dict[type[Frame], tuple[str, ...]] = {
    SessionStartFrame: ("session_id", "agent_id", "payload"),
    UserMessageFrame: ("text",),
    UserIdleFrame: ("level", "idle_ms"),
    BrowserMessageFrame: ("type", "data"),
    FinalizeFrame: ("heard_text", "reason"),
    SpeechChunkFrame: ("text",),
    BrowserCommandFrame: ("data",),
    ConfigureTtsFrame: ("request_id", "voice", "language", "model", "speed"),
    ConfigureSttFrame: ("request_id", "language_hint", "thresholds"),
    ConfigureIdleFrame: ("request_id", "timeout_ms"),
    ResponseFrame: ("request_id", "accepted", "detail"),
    ErrorFrame: ("error", "fatal"),
    # Field-less frames round-trip to their own type and nothing more.
    InterruptionFrame: (),
    SpeechStartFrame: (),
    SpeechEndFrame: (),
    EndFrame: (),
}


@pytest.mark.parametrize("frame", _frames(), ids=lambda f: type(f).__name__)
async def test_roundtrip(frame: Frame) -> None:
    ser = CortexFrameSerializer()
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


@pytest.mark.parametrize("frame", _frames(), ids=lambda f: type(f).__name__)
async def test_correlation_rides_the_envelope(frame: Frame) -> None:
    """Correlation is the envelope's, not the body's: any frame carries any
    pair, and it comes back beside the decoded frame."""
    ser = CortexFrameSerializer()
    payload = await ser.serialize(frame, epoch=22, speech_id=33)

    msg = await ser.deserialize_message(payload)
    assert type(msg.frame) is type(frame)
    assert (msg.epoch, msg.speech_id) == (22, 33)


async def test_correlation_defaults_to_zero() -> None:
    ser = CortexFrameSerializer()
    msg = await ser.deserialize_message(await ser.serialize(UserMessageFrame(text="hi")))
    assert (msg.epoch, msg.speech_id) == (0, 0)


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
    ser = CortexFrameSerializer()
    out = await ser.deserialize(await ser.serialize(frame))
    assert type(out) is type(frame)


async def test_an_undeclared_threshold_is_refused_at_the_sender() -> None:
    """The thresholds dict is the schema's own field names. A name the schema does
    not declare fails here rather than travelling as a key nothing will read."""
    ser = CortexFrameSerializer()
    with pytest.raises(AttributeError):
        await ser.serialize(ConfigureSttFrame(request_id=1, thresholds={"patience": 3}))
