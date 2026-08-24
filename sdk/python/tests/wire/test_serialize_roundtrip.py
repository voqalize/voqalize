"""Per-frame serializer round-trip: serialize(deserialize) == input."""

from __future__ import annotations

import pytest

from voqalize.sdk.wire import (
    WIRE_VERSION,
    CancelFrame,
    Config,
    ConfigureFrame,
    EndFrame,
    ErrorCode,
    ErrorFrame,
    FinalizeFrame,
    FinalizeReason,
    Frame,
    IdleConfig,
    InterruptionFrame,
    Language,
    ResponseFrame,
    RTVIFrame,
    RTVIType,
    SessionStartFrame,
    SpeechChunkFrame,
    SpeechEndFrame,
    SpeechStartFrame,
    SttConfig,
    TtsConfig,
    UserIdleFrame,
    UserMessageFrame,
    Voice,
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
            type=RTVIType.UI_COMMAND,
            data={"command": "open_panel", "payload": {"panel": "orders"}},
            turn_id=4,
        ),
        RTVIFrame(type=RTVIType.CLIENT_MESSAGE, data={"t": "tap", "d": {"id": 3}}, id="req-1"),
        ConfigureFrame(
            request_id=1,
            config=Config(
                tts=TtsConfig(voice=Voice.OMNIVOICE_GAURI, language=Language.HI),
                stt=SttConfig(language=Language.HI),
                idle=IdleConfig(timeout_ms=0),
            ),
        ),
        # The legs differ on purpose: Odia is understood, and there is no Odia
        # clip to speak it with, so the call is spoken with the Hindi one.
        ConfigureFrame(
            request_id=2,
            config=Config(stt=SttConfig(language=Language.OR), tts=TtsConfig(language=Language.HI)),
        ),
        ConfigureFrame(request_id=3, config=Config(tts=TtsConfig(voice=Voice.OMNIVOICE_GAURAV))),
        ResponseFrame(request_id=3, accepted=True),
        ResponseFrame(request_id=4, accepted=False, detail="no recognizer for language 'sat'"),
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
    ConfigureFrame: ("request_id", "config"),
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


async def test_an_empty_delta_still_names_its_op() -> None:
    """A request that changes nothing is a legal no-op the far side answers — so
    the op must survive the trip even when no section is set. Encode it as a bare
    envelope and it would arrive as an unknown operation instead."""
    ser = WireSerializer()
    out = await ser.deserialize(await ser.serialize(ConfigureFrame(request_id=9)))
    assert isinstance(out, ConfigureFrame)
    assert out.config == Config()


async def test_an_unset_section_stays_unset() -> None:
    """Unset means *leave it alone*, and there is no value that says so — an
    IdleConfig that decoded as ``timeout_ms=0`` would disable idle detection on
    every request that never mentioned it."""
    ser = WireSerializer()
    out = await ser.deserialize(
        await ser.serialize(
            ConfigureFrame(request_id=9, config=Config(tts=TtsConfig(voice=Voice.OMNIVOICE_GAURI)))
        )
    )
    assert isinstance(out, ConfigureFrame)
    assert out.config.idle is None
    assert out.config.stt is None
    assert out.config.tts is not None
    assert out.config.tts.language is None
