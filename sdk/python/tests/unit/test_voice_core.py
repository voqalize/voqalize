"""The voice core's public hooks, the same on every layer: ``append_note``,
``say_line`` and ``respond_with``. Driven on Gemini's scripted model."""

from __future__ import annotations

from typing import Any

from google.genai import types

from tests.unit.test_gemini_turn import (
    _brain,  # pyright: ignore[reportPrivateUsage]
    _calls,  # pyright: ignore[reportPrivateUsage]
    _history,  # pyright: ignore[reportPrivateUsage]
    _shape,  # pyright: ignore[reportPrivateUsage]
    _text,  # pyright: ignore[reportPrivateUsage]
)
from voqalize.sdk import Finalize, UserMessage
from voqalize.sdk.voice import ToolChoice


async def test_a_note_is_a_user_turn_and_starts_nothing() -> None:
    brain, _ = await _brain([])
    brain.append_note("(They opened pricing.)")
    assert _history(brain) == ["user: (They opened pricing.)"]


async def test_an_own_line_takes_its_own_finalize_and_stays_out_of_the_context() -> None:
    """The model's next unit must get the next finalize. A line the brain spoke
    itself is a unit too, and without its own place in the queue it would take
    the model's."""
    brain, session = await _brain(_text("From the model."))
    said = [e async for e in brain.say_line("One moment.")]
    assert _shape(said) == ["[", "One moment.", "]"]
    _ = [e async for e in brain.on_user_message(session, UserMessage("hello"))]

    await brain.on_finalize(session, Finalize(1, "One moment.", "One moment."))
    await brain.on_finalize(session, Finalize(2, "From the", "From the model."))
    assert _history(brain) == ["user: hello", "model: From the"]


async def test_a_remembered_line_is_cut_to_what_was_heard() -> None:
    brain, session = await _brain([])
    _ = [e async for e in brain.say_line("Which city are you in?", remember=True)]
    await brain.on_finalize(session, Finalize(1, "Which city", "Which city are you in?"))
    assert _history(brain) == ["model: Which city"]


async def test_respond_with_none_takes_the_tools_away() -> None:
    brain, session = await _brain(_text("Here it is."))
    brain.append_note("hello")
    events = [e async for e in brain.respond_with(session, tools=ToolChoice.NONE)]
    assert _shape(events) == ["[", "Here it is.", "]"]
    models: Any = brain._client.models  # pyright: ignore[reportPrivateUsage]
    assert models.may_call == [False]


async def test_respond_with_only_forces_that_tool() -> None:
    brain, session = await _brain(_calls("ping"))
    brain.append_note("hello")
    _ = [e async for e in brain.respond_with(session, tools=ToolChoice.only("ping"))]
    config: types.GenerateContentConfig = brain._turn_request(ToolChoice.only("ping"))  # pyright: ignore[reportPrivateUsage]
    fc = config.tool_config.function_calling_config  # pyright: ignore[reportOptionalMemberAccess]
    assert fc is not None
    assert fc.mode == types.FunctionCallingConfigMode.ANY
    assert fc.allowed_function_names == ["ping"]
    assert brain.ran == ["ping"]
