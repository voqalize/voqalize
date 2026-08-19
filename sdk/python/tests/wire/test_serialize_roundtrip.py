"""Per-frame serializer round-trip: serialize(deserialize) == input."""

from __future__ import annotations

import pytest

from voqalize.sdk.wire import (
    CancelFrame,
    ClientMessageFrame,
    CortexFrameSerializer,
    EndFrame,
    ErrorFrame,
    FinalizeReason,
    Frame,
    InferenceFinalizedFrame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    ServerMessageFrame,
    SessionStartFrame,
    UpdateIdleSettingsFrame,
    UpdateSTTSettingsFrame,
    UpdateTTSSettingsFrame,
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
        ClientMessageFrame(msg_id="m-1", type="form_submitted", data={"field": "email"}),
        InterruptionFrame(),
        InferenceFinalizedFrame(heard_text="ok, scheduled", reason=FinalizeReason.COMPLETED),
        InferenceFinalizedFrame(heard_text="partial...", reason=FinalizeReason.USER_BARGE_IN),
        LLMFullResponseStartFrame(),
        LLMTextFrame(text="hi"),
        LLMTextFrame(text=" world"),
        LLMFullResponseEndFrame(),
        ServerMessageFrame(data={"ui": "open_panel", "args": {"id": 3}}),
        UpdateTTSSettingsFrame(settings={"voice": "omnivoice/gauri", "language": "hi"}),
        UpdateSTTSettingsFrame(settings={"language_hint": "hi"}),
        UpdateIdleSettingsFrame(settings={"timeout_ms": 0}),
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
    ClientMessageFrame: ("msg_id", "type", "data"),
    InferenceFinalizedFrame: ("heard_text", "reason"),
    LLMTextFrame: ("text",),
    ServerMessageFrame: ("data",),
    UpdateTTSSettingsFrame: ("settings",),
    UpdateSTTSettingsFrame: ("settings",),
    UpdateIdleSettingsFrame: ("settings",),
    ErrorFrame: ("error", "fatal"),
    # Field-less frames round-trip to their own type and nothing more.
    InterruptionFrame: (),
    LLMFullResponseStartFrame: (),
    LLMFullResponseEndFrame: (),
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
    triple, and it comes back beside the decoded frame."""
    ser = CortexFrameSerializer()
    payload = await ser.serialize(frame, request_id=11, epoch=22, inference_id=33)

    msg = await ser.deserialize_message(payload)
    assert type(msg.frame) is type(frame)
    assert (msg.request_id, msg.epoch, msg.inference_id) == (11, 22, 33)


async def test_correlation_defaults_to_zero() -> None:
    ser = CortexFrameSerializer()
    msg = await ser.deserialize_message(await ser.serialize(UserMessageFrame(text="hi")))
    assert (msg.request_id, msg.epoch, msg.inference_id) == (0, 0, 0)
