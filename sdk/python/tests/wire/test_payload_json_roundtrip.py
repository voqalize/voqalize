"""Opaque dict fields (VqlStart.payload, fc.arguments, fc.result) survive
round-trip with nested structure intact.
"""

from voqalize.sdk.wire import (
    CortexFrameSerializer,
    VqlFunctionCallResultFrame,
    VqlInteractionCompletedFrame,
    VqlStartFrame,
)


async def test_interaction_completed_roundtrip() -> None:
    ser = CortexFrameSerializer()
    out = await ser.deserialize(await ser.serialize(VqlInteractionCompletedFrame(interaction_id=7)))
    assert isinstance(out, VqlInteractionCompletedFrame)
    assert out.interaction_id == 7


async def test_nested_payload_roundtrip() -> None:
    ser = CortexFrameSerializer()
    frame = VqlStartFrame(
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
    assert isinstance(out, VqlStartFrame)
    assert out.payload == frame.payload


async def test_function_call_result_dict_roundtrip() -> None:
    ser = CortexFrameSerializer()
    frame = VqlFunctionCallResultFrame(
        interaction_id=1,
        inference_id=1,
        tool_call_id="tc",
        function_name="lookup",
        result={
            "rows": [{"id": 1}, {"id": 2}],
            "total": 2,
            "meta": {"ms": 12.5},
        },
    )
    out = await ser.deserialize(await ser.serialize(frame))
    assert isinstance(out, VqlFunctionCallResultFrame)
    assert out.result == frame.result
