"""A held line takes its own finalize, ahead of the model's, however the two race.

:func:`voqalize_demos.acknowledge.hold_the_floor` speaks a line of the brain's
own while the model's turn keeps running in a task of its own. Voqalize
finalizes units in the order it plays them, and the held line plays first, so it
has to be queued first — including when the model starts speaking while the
held line is still going out.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any, cast

from google import genai
from voqalize_demos import GeminiBrain
from voqalize_demos.acknowledge import Acknowledger, hold_the_floor
from voqalize_demos.testing import ScriptedGemini

from voqalize.sdk import Speech, SpeechChunk, SpeechEnd, SpeechStart


def _brain() -> GeminiBrain:
    return GeminiBrain(client=cast(genai.Client, ScriptedGemini().client), system_instruction="")


def _ack() -> Acknowledger[str]:
    return Acknowledger(
        lines={},
        hold_lines={"en": ("One moment.",)},
        sorry={"en": "Sorry, that's taking a little longer."},
        hold_after_s=0.05,
        sorry_after_s=10.0,
    )


async def test_a_model_that_starts_during_the_held_line_queues_behind_it() -> None:
    brain = _brain()
    awaiting: Any = brain._awaiting  # pyright: ignore[reportPrivateUsage]
    model_unit = object()
    holding = asyncio.Event()

    async def turn() -> AsyncGenerator[Speech, None]:
        await holding.wait()
        yield SpeechStart()
        # What the voice core does once a unit's start has been taken.
        awaiting.append(model_unit)
        yield SpeechChunk("Here it is.")
        yield SpeechEnd()

    said: list[str] = []
    async for event in hold_the_floor(brain, _ack(), lambda: "en", turn()):
        if isinstance(event, SpeechStart) and not holding.is_set():
            # The held line has begun: let the model start under it.
            holding.set()
            await asyncio.sleep(0.05)
        if isinstance(event, SpeechChunk):
            said.append(event.text)

    assert said == ["One moment.", "Here it is."]
    assert len(awaiting) == 2
    assert awaiting[1] is model_unit, "the held line's finalize went to the model's unit"


async def test_a_model_that_answers_in_time_gets_no_held_line() -> None:
    brain = _brain()

    async def turn() -> AsyncGenerator[Speech, None]:
        yield SpeechStart()
        yield SpeechChunk("Here it is.")
        yield SpeechEnd()

    said = [
        e.text
        async for e in hold_the_floor(brain, _ack(), lambda: "en", turn())
        if isinstance(e, SpeechChunk)
    ]
    assert said == ["Here it is."]
    assert not brain._awaiting  # pyright: ignore[reportPrivateUsage]
