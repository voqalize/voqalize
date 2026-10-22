"""What a turn did, on the wire: ``TurnStep`` from the voice core and from
``session.report_step``.

Driven through the adapter, as Voqalize drives a turn, so each step carries the
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
from voqalize.sdk import Session, TurnStep, Unsupported
from voqalize.sdk.brain import _adapter_for
from voqalize.sdk.wire import Capability, SessionStartFrame, TurnStepFrame


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


def _steps(wire: _Wire) -> list[TurnStepFrame]:
    return [f for f in wire.frames if isinstance(f, TurnStepFrame)]


async def test_a_turn_reports_each_request_and_each_tool_as_a_step() -> None:
    """``lookup`` is marked, so the turn asks twice: model, tool, model, in the
    order they ended, each with its own counts. Gemini leaves out a zero count,
    and once it reported the prompt that is a zero, not an unknown."""
    script = [
        *_costing(_calls("lookup"), prompt=100, cached=40, out=5, thoughts=2),
        *_costing(_text("It is 42."), prompt=150, out=4),
    ]
    brain, wire, _ = await _open(_Coach(_ScriptedClient(script)), Capability.TURN_STEPS)
    await _turn(brain)

    tool, first, second = _steps(wire)
    assert {s.turn_id for s in (tool, first, second)} == {2}
    assert [(s.kind, s.name) for s in (tool, first, second)] == [
        ("tool", "lookup"),
        ("model", brain.model),
        ("model", brain.model),
    ]
    assert (first.provider, tool.provider) == ("google", "")
    assert first.counts == {
        "input_tokens": 100,
        "cached_input_tokens": 40,
        "output_tokens": 5,
        "reasoning_tokens": 2,
    }
    assert second.counts == {
        "input_tokens": 150,
        "cached_input_tokens": 0,
        "output_tokens": 4,
        "reasoning_tokens": 0,
    }
    # One timeline: the tool ran inside the first request's stream, and the
    # second request began after the first ended. Each start is rounded to a whole
    # millisecond on its own, so every comparison allows 1 ms.
    assert first.start_ms <= tool.start_ms + 1
    assert tool.start_ms + tool.duration_ms <= first.start_ms + first.duration_ms + 1
    assert second.start_ms >= first.start_ms + first.duration_ms - 1
    assert first.first_output_ms is not None
    assert tool.first_output_ms is None


async def test_counts_the_api_never_reported_stay_out() -> None:
    brain, wire, _ = await _open(_Coach(_ScriptedClient(_text("Hi."))), Capability.TURN_STEPS)
    await _turn(brain)

    [step] = _steps(wire)
    assert step.kind == "model"
    assert step.counts == {}


async def test_nothing_is_sent_to_a_voqalize_that_does_not_record_them() -> None:
    brain, wire, _ = await _open(_Coach(_ScriptedClient(_calls("ping"))))
    await _turn(brain)
    assert _steps(wire) == []


async def test_report_steps_false_keeps_them_off_the_wire() -> None:
    class Quiet(_Coach):
        def __init__(self, client: Any) -> None:
            super().__init__(client)
            self._report_steps = False

    brain, wire, _ = await _open(Quiet(_ScriptedClient(_calls("ping"))), Capability.TURN_STEPS)
    await _turn(brain)
    assert _steps(wire) == []


async def test_the_constructor_takes_the_opt_out() -> None:
    from voqalize.sdk.gemini import GeminiBrain

    brain = GeminiBrain(client=_ScriptedClient([]), system_instruction="x", report_steps=False)  # pyright: ignore[reportArgumentType]
    assert brain._report_steps is False  # pyright: ignore[reportPrivateUsage]


# ─── session.report_step, for the brain's own work ───────────────────────────


async def test_report_step_needs_the_capability() -> None:
    _, _, session = await _open(_Coach(_ScriptedClient([])))
    assert session.can_report_steps is False
    with pytest.raises(Unsupported):
        session.report_step(TurnStep(kind="database", name="orders", duration_ms=5), turn_id=1)


async def test_report_step_outside_a_turn_needs_its_turn_id() -> None:
    _, wire, session = await _open(_Coach(_ScriptedClient([])), Capability.TURN_STEPS)
    with pytest.raises(ValueError, match="outside a turn"):
        session.report_step(TurnStep(kind="database", name="orders", duration_ms=5))

    session.report_step(
        TurnStep(kind="database", name="orders", duration_ms=5, counts={"rows": 14}), turn_id=1
    )
    [step] = _steps(wire)
    assert (step.turn_id, step.kind, step.name, step.counts) == (
        1,
        "database",
        "orders",
        {"rows": 14},
    )
    assert step.provider == ""


async def test_a_step_with_no_start_is_placed_as_ending_now() -> None:
    """Turn 1 began when the session opened; a 0 ms step reported now began no
    earlier than that, and one too long for the turn starts at its beginning."""
    _, wire, session = await _open(_Coach(_ScriptedClient([])), Capability.TURN_STEPS)
    session.report_step(TurnStep(kind="http", name="weather", duration_ms=0), turn_id=1)
    session.report_step(TurnStep(kind="http", name="weather", duration_ms=10**6), turn_id=1)
    session.report_step(
        TurnStep(kind="mcp", name="calendar", duration_ms=30, start_ms=250), turn_id=1
    )
    placed, clamped, given = _steps(wire)
    assert placed.start_ms >= 0
    assert clamped.start_ms == 0
    assert given.start_ms == 250


async def test_a_step_for_a_turn_the_session_never_saw_needs_its_start() -> None:
    _, _, session = await _open(_Coach(_ScriptedClient([])), Capability.TURN_STEPS)
    with pytest.raises(ValueError, match="start_ms"):
        session.report_step(TurnStep(kind="http", name="weather", duration_ms=3), turn_id=99)
