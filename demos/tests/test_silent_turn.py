"""A turn that acted on screen and said nothing is asked once more.

On a dialled call (tool-loop program, D2) the model called an action tool alone in
most of the demos, and the user heard nothing until the runtime's watchdog
apologised. :mod:`voqalize_demos.silent_turn` is the floor under the prompt's rule;
these pin what it does and, as much, what it leaves alone.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any, cast

from voqalize_demos import acted, reask_if_silent
from voqalize_demos.testing import ScriptedGemini, call, replies, reply

from voqalize.sdk import Session, Speech, SpeechChunk, SpeechEnd, SpeechStart

from ._harness import check_turn, demo

_SESSION = cast(Session, None)


class _Turns:
    """A stand-in for ``super().respond``: each run plays the next script."""

    def __init__(self, *scripts: tuple[bool, bool]) -> None:
        #: Per run: whether it acts on screen, and whether it speaks.
        self._scripts = list(scripts)
        self.runs = 0
        self.closed = 0

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        acts, speaks = self._scripts[self.runs]
        self.runs += 1
        try:
            if acts:
                acted("open_case")
            if speaks:
                yield SpeechStart()
                yield SpeechChunk("It's open.")
                yield SpeechEnd()
        finally:
            self.closed += 1


async def _drain(turns: _Turns) -> list[Speech]:
    return [e async for e in reask_if_silent(turns.respond, _SESSION)]


async def test_a_turn_that_acted_silently_is_asked_once_more() -> None:
    turns = _Turns((True, False), (False, True))
    events = await _drain(turns)
    assert turns.runs == 2
    assert [type(e) for e in events] == [SpeechStart, SpeechChunk, SpeechEnd]


async def test_a_turn_that_spoke_or_only_read_is_left_alone() -> None:
    for script in ((True, True), (False, False), (False, True)):
        turns = _Turns(script, (False, True))
        await _drain(turns)
        assert turns.runs == 1, script


async def test_it_asks_once_only() -> None:
    turns = _Turns((True, False), (True, False), (False, True))
    assert await _drain(turns) == []
    assert turns.runs == 2


async def test_acted_outside_a_turn_does_nothing() -> None:
    acted("open_case")


async def test_a_barge_in_closes_the_turn_under_way() -> None:
    """The consumer closing the helper mid-speech closes the inherited turn, and
    no second request goes."""
    turns = _Turns((True, True), (False, True))
    gen = reask_if_silent(turns.respond, _SESSION)
    assert isinstance(await anext(gen), SpeechStart)
    await gen.aclose()
    assert (turns.runs, turns.closed) == (1, 1)


async def test_turns_in_flight_keep_their_own_record() -> None:
    """Each turn runs in its own task; one turn's dispatch is not the other's."""
    quiet, loud = _Turns((False, False), (False, True)), _Turns((True, True), (False, True))
    await asyncio.gather(_drain(quiet), _drain(loud))
    assert (quiet.runs, loud.runs) == (1, 1)


async def test_servicing_says_what_it_opened_when_the_call_came_alone() -> None:
    """Over the real wire: the call lands once, and the second request — the
    context now ending in its result — is what the user hears."""
    opened = "Daniel Cho's case is open."
    llm = ScriptedGemini(
        {
            "Open Daniel Cho's case.": replies(
                call("open_case", action={"ref": "MS-1042"}),
                reply(opened),
            )
        }
    )
    async with demo("servicing", llm) as rig:
        await rig.driver.start_session()
        turn = await rig.driver.user_says("Open Daniel Cho's case.")
        check_turn(rig, turn, units=1)
        assert [u.text for u in turn.units] == [opened]
        assert rig.actions() == ["open_case"]
        second: list[Any] = llm.captured_contents[-1]
        assert second[-1].parts[0].function_response is not None, (
            "the second request should end in the call's result, with no note after it"
        )
