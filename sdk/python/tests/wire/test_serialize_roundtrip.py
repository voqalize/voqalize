"""Per-frame serializer round-trip: serialize(deserialize) == input."""

from __future__ import annotations

import pytest

from voqalize.sdk.wire import (
    CancelFrame,
    CortexFrameSerializer,
    EndFrame,
    ErrorFrame,
    FinalizeReason,
    Frame,
    InterruptionFrame,
    VqlFunctionCallInProgressFrame,
    VqlFunctionCallResultFrame,
    VqlFunctionCallsStartedFrame,
    VqlInferenceFinalizedFrame,
    VqlLLMFullResponseEndFrame,
    VqlLLMFullResponseStartFrame,
    VqlLLMTextFrame,
    VqlStartFrame,
    VqlUserTextFrame,
)


def _frames() -> list[Frame]:
    return [
        VqlStartFrame(
            session_id="sess-123",
            agent_id="welcome",
            payload={"greet": "hello", "n": 7, "deep": {"k": [1, 2, 3]}},
            audio_in_sample_rate=8000,
            audio_out_sample_rate=22050,
            enable_metrics=True,
            enable_tracing=False,
            enable_usage_metrics=True,
            report_only_initial_ttfb=True,
        ),
        VqlUserTextFrame(interaction_id=1, text="hello there"),
        # Interruption rides the wire as the field-less InterruptionFrame.
        InterruptionFrame(),
        VqlInferenceFinalizedFrame(
            interaction_id=3,
            inference_id=1,
            heard_text="ok, scheduled",
            interrupted=False,
            reason=FinalizeReason.COMPLETED,
        ),
        VqlInferenceFinalizedFrame(
            interaction_id=4,
            inference_id=2,
            heard_text="partial...",
            interrupted=True,
            reason=FinalizeReason.USER_BARGE_IN,
        ),
        VqlLLMFullResponseStartFrame(interaction_id=5, inference_id=1),
        VqlLLMTextFrame(interaction_id=5, inference_id=1, text="hi"),
        VqlLLMTextFrame(interaction_id=5, inference_id=1, text=" world"),
        VqlLLMFullResponseEndFrame(interaction_id=5, inference_id=1),
        VqlFunctionCallsStartedFrame(
            interaction_id=6,
            inference_id=1,
            tool_call_id="tc-1",
            function_name="get_weather",
            arguments={"city": "BLR", "unit": "C"},
        ),
        VqlFunctionCallInProgressFrame(
            interaction_id=6,
            inference_id=1,
            tool_call_id="tc-1",
            function_name="get_weather",
            arguments={"city": "BLR", "unit": "C"},
        ),
        VqlFunctionCallResultFrame(
            interaction_id=6,
            inference_id=1,
            tool_call_id="tc-1",
            function_name="get_weather",
            result={"temp_c": 28, "summary": "warm"},
        ),
        EndFrame(),
        CancelFrame(reason="user_left"),
        CancelFrame(),  # reason=None → empty string on wire
        ErrorFrame(error="upstream timeout", fatal=False),
        ErrorFrame(error="bad config", fatal=True),
    ]


_VQL_FIELDS = {
    VqlStartFrame: (
        "session_id",
        "agent_id",
        "payload",
        "audio_in_sample_rate",
        "audio_out_sample_rate",
        "enable_metrics",
        "enable_tracing",
        "enable_usage_metrics",
        "report_only_initial_ttfb",
    ),
    VqlUserTextFrame: ("interaction_id", "text"),
    VqlInferenceFinalizedFrame: (
        "interaction_id",
        "inference_id",
        "heard_text",
        "interrupted",
        "reason",
    ),
    VqlLLMFullResponseStartFrame: ("interaction_id", "inference_id"),
    VqlLLMTextFrame: ("interaction_id", "inference_id", "text"),
    VqlLLMFullResponseEndFrame: ("interaction_id", "inference_id"),
    VqlFunctionCallsStartedFrame: (
        "interaction_id",
        "inference_id",
        "tool_call_id",
        "function_name",
        "arguments",
    ),
    VqlFunctionCallInProgressFrame: (
        "interaction_id",
        "inference_id",
        "tool_call_id",
        "function_name",
        "arguments",
    ),
    VqlFunctionCallResultFrame: (
        "interaction_id",
        "inference_id",
        "tool_call_id",
        "function_name",
        "result",
    ),
    # InterruptionFrame is field-less — round-trips to an InterruptionFrame.
    InterruptionFrame: (),
    EndFrame: (),
    ErrorFrame: ("error", "fatal"),
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

    for field in _VQL_FIELDS.get(type(frame), ()):
        assert getattr(out, field) == getattr(frame, field), (
            f"{type(frame).__name__}.{field} differs: "
            f"{getattr(out, field)!r} != {getattr(frame, field)!r}"
        )
