"""What a turn cost, on the wire: ``TurnUsage`` from the voice core and from
``session.report_usage``.

Driven through the adapter, as Voqalize drives a turn, so the frame carries the
turn it belongs to. The model is the scripted Gemini of ``test_gemini_turn``.
"""

from __future__ import annotations

from typing import Any

import pytest
from google.genai import types

from tests.unit.test_gemini_turn import (
    _calls,  # pyright: ignore[reportPrivateUsage]
    _Coach,  # pyright: ignore[reportPrivateUsage]
    _ScriptedClient,  # pyright: ignore[reportPrivateUsage]
    _text,  # pyright: ignore[reportPrivateUsage]
    _turn,  # pyright: ignore[reportPrivateUsage]
    _Wire,  # pyright: ignore[reportPrivateUsage]
)
from voqalize.sdk import Session, TurnUsage, Unsupported
from voqalize.sdk.brain import _adapter_for
from voqalize.sdk.wire import Capability, SessionStartFrame, TurnUsageFrame


def _costing(
    hop: list[types.GenerateContentResponse],
    *,
    prompt: int,
    cached: int | None = None,
    out: int = 0,
    thoughts: int | None = None,
) -> list[types.GenerateContentResponse]:
    """One scripted request whose last chunk reports what it cost."""
    meta = types.GenerateContentResponseUsageMetadata(
        prompt_token_count=prompt,
        cached_content_token_count=cached,
        candidates_token_count=out,
        thoughts_token_count=thoughts,
    )
    return [*hop[:-1], hop[-1].model_copy(update={"usage_metadata": meta})]


async def _open(brain: Any, *capabilities: Capability) -> tuple[Any, _Wire, Session]:
    wire = _Wire()
    adapter = _adapter_for(brain, wire)
    await adapter.handle_frame(
        SessionStartFrame(turn_id=1, session_id="s", capabilities=frozenset(capabilities))
    )
    session = adapter._session  # pyright: ignore[reportPrivateUsage]
    assert session is not None
    brain._adapter = adapter
    return brain, wire, session


def _usage(wire: _Wire) -> list[TurnUsageFrame]:
    return [f for f in wire.frames if isinstance(f, TurnUsageFrame)]


async def test_a_turn_reports_its_counts_summed_over_its_requests() -> None:
    """``lookup`` is marked, so the turn makes two requests; each is billed for
    its whole prompt, so the frame carries the sum. Gemini leaves out a zero
    count, and once it reported the prompt that is a zero, not an unknown."""
    script = [
        *_costing(_calls("lookup"), prompt=100, cached=40, out=5, thoughts=2),
        *_costing(_text("It is 42."), prompt=150, out=4),
    ]
    brain, wire, _ = await _open(_Coach(_ScriptedClient(script)), Capability.TURN_USAGE)
    await _turn(brain)

    [usage] = _usage(wire)
    assert usage.turn_id == 2
    assert (usage.model, usage.provider) == (brain.model, "gemini")
    assert (usage.requests, usage.tool_calls) == (2, 1)
    assert usage.input_tokens == 250
    assert usage.cached_input_tokens == 40
    assert usage.output_tokens == 9
    assert usage.reasoning_tokens == 2
    assert usage.cache_write_tokens is None
    assert usage.first_token_ms is not None
    assert usage.first_speech_ms is not None
    assert usage.first_speech_ms >= usage.first_token_ms


async def test_a_silent_turn_has_no_time_to_speech() -> None:
    script = _costing(_calls("ping"), prompt=10, out=1)
    brain, wire, _ = await _open(_Coach(_ScriptedClient(script)), Capability.TURN_USAGE)
    await _turn(brain)

    [usage] = _usage(wire)
    assert usage.first_speech_ms is None
    assert usage.tool_calls == 1


async def test_counts_the_api_never_reported_stay_unreported() -> None:
    brain, wire, _ = await _open(_Coach(_ScriptedClient(_text("Hi."))), Capability.TURN_USAGE)
    await _turn(brain)

    [usage] = _usage(wire)
    assert usage.input_tokens is None
    assert usage.output_tokens is None


async def test_nothing_is_sent_to_a_voqalize_that_does_not_record_it() -> None:
    brain, wire, _ = await _open(_Coach(_ScriptedClient(_text("Hi."))))
    await _turn(brain)
    assert _usage(wire) == []


async def test_report_usage_false_keeps_the_numbers_off_the_wire() -> None:
    class Quiet(_Coach):
        def __init__(self, client: Any) -> None:
            super().__init__(client)
            self._report_usage = False

    brain, wire, _ = await _open(Quiet(_ScriptedClient(_text("Hi."))), Capability.TURN_USAGE)
    await _turn(brain)
    assert _usage(wire) == []


async def test_the_constructor_takes_the_opt_out() -> None:
    from voqalize.sdk.gemini import GeminiBrain

    brain = GeminiBrain(client=_ScriptedClient([]), system_instruction="x", report_usage=False)  # pyright: ignore[reportArgumentType]
    assert brain._report_usage is False  # pyright: ignore[reportPrivateUsage]


# ─── session.report_usage, for a brain with its own loop ──────────────────────


async def test_report_usage_needs_the_capability() -> None:
    _, _, session = await _open(_Coach(_ScriptedClient([])))
    assert session.can_report_usage is False
    with pytest.raises(Unsupported):
        session.report_usage(TurnUsage(model="m", provider="mine"), turn_id=3)


async def test_report_usage_outside_a_turn_needs_its_turn_id() -> None:
    _, wire, session = await _open(_Coach(_ScriptedClient([])), Capability.TURN_USAGE)
    with pytest.raises(ValueError, match="outside a turn"):
        session.report_usage(TurnUsage(model="m", provider="mine"))

    session.report_usage(TurnUsage(model="m", provider="mine", input_tokens=7), turn_id=3)
    [usage] = _usage(wire)
    assert (usage.turn_id, usage.provider, usage.input_tokens) == (3, "mine", 7)
