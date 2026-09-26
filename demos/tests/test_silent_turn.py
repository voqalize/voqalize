"""A turn that acted on screen and said nothing gets a line of the brain's own.

On a dialled call (tool-loop program, D2) the model called an action tool alone in
most of the demos, and the user heard nothing until the runtime's watchdog
apologised. :mod:`voqalize_demos.silent_turn` is the floor under the prompt's rule
— a written line, no second request; these pin what it does and, as much, what it
leaves alone.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncGenerator
from itertools import pairwise
from typing import Any, cast

from voqalize_demos import PHRASES, FallbackLine, GeminiBrain, landed
from voqalize_demos.testing import ScriptedGemini, call, reply

from voqalize.sdk import Speech, SpeechChunk, SpeechEnd, SpeechStart

from ._harness import check_turn, demo

_OPEN = ("It's open.", "Here it is.")


class _Brain:
    """All :class:`FallbackLine` touches of a brain: its finalize queue."""

    def __init__(self) -> None:
        self._awaiting: deque[Any] = deque()


async def _turn(
    *, lands: tuple[str, ...] = (), speaks: bool = False
) -> AsyncGenerator[Speech, None]:
    """A stand-in for ``super().respond``: lands ``lands``, speaks if asked."""
    if lands:
        landed(*lands)
    if speaks:
        yield SpeechStart()
        yield SpeechChunk("It's open.")
        yield SpeechEnd()


async def _drain(
    turn: AsyncGenerator[Speech, None], fallback: FallbackLine | None = None
) -> tuple[list[Speech], _Brain]:
    brain = _Brain()
    speak = (fallback or FallbackLine()).speak_if_silent(cast(GeminiBrain, brain), turn)
    return [e async for e in speak], brain


def _said(events: list[Speech]) -> list[str]:
    return [e.text for e in events if isinstance(e, SpeechChunk)]


async def test_a_turn_that_acted_silently_gets_one_line_of_what_landed() -> None:
    async def turn() -> AsyncGenerator[Speech, None]:
        landed("Moved.")
        landed(*_OPEN)
        return
        yield  # an async generator that yields nothing

    events, brain = await _drain(turn())
    assert [type(e) for e in events] == [SpeechStart, SpeechChunk, SpeechEnd]
    assert _said(events)[0] in _OPEN, "the line is the last landed call's"
    assert len(brain._awaiting) == 1, "the line is a unit Voqalize will finalize"  # pyright: ignore[reportPrivateUsage]


async def test_a_turn_that_spoke_or_landed_nothing_is_left_alone() -> None:
    for lands, speaks in ((_OPEN, True), ((), False), ((), True)):
        events, brain = await _drain(_turn(lands=lands, speaks=speaks))
        assert _said(events) == (["It's open."] if speaks else []), (lands, speaks)
        assert not brain._awaiting  # pyright: ignore[reportPrivateUsage]


async def test_the_line_said_last_is_not_said_again() -> None:
    fallback = FallbackLine()
    said = [_said((await _drain(_turn(lands=_OPEN), fallback))[0])[0] for _ in range(6)]
    assert all(a != b for a, b in pairwise(said)), said


async def test_landed_outside_a_turn_does_nothing() -> None:
    landed(*_OPEN)


async def test_a_barge_in_closes_the_turn_under_way() -> None:
    """The consumer closing the floor mid-speech closes the inherited turn."""
    closed: list[bool] = []

    async def turn() -> AsyncGenerator[Speech, None]:
        try:
            yield SpeechStart()
            yield SpeechChunk("It's open.")
        finally:
            closed.append(True)

    speak = FallbackLine().speak_if_silent(cast(GeminiBrain, _Brain()), turn())
    assert isinstance(await anext(speak), SpeechStart)
    await speak.aclose()
    assert closed == [True]


async def test_turns_in_flight_keep_their_own_record() -> None:
    """Each turn runs in its own task; one turn's dispatch is not the other's."""
    (quiet, _), (loud, _) = await asyncio.gather(
        _drain(_turn()), _drain(_turn(lands=_OPEN, speaks=True))
    )
    assert _said(quiet) == []
    assert _said(loud) == ["It's open."]


def test_every_language_has_every_phrase() -> None:
    kinds = {kind for row in PHRASES.values() for kind in row}
    for language, row in PHRASES.items():
        assert set(row) == kinds, language
        assert all(row.values()), language


async def test_servicing_says_the_case_is_open_when_the_call_came_alone() -> None:
    """Over the real wire: the call lands once, the brain's line is what the
    advisor hears, the turn is one request, and the line never reaches the
    context."""
    from servicing.backend.brain import _LINES, OpenCase  # pyright: ignore[reportPrivateUsage]

    llm = ScriptedGemini(
        {
            "Open Daniel Cho's case.": call("open_case", action={"ref": "MS-1042"}),
            "Thanks.": reply("Anytime."),
        }
    )
    async with demo("servicing", llm) as rig:
        await rig.driver.start_session()
        turn = await rig.driver.user_says("Open Daniel Cho's case.")
        check_turn(rig, turn, units=1)
        (line,) = (u.text for u in turn.units)
        assert line in _LINES[OpenCase], line
        assert rig.actions() == ["open_case"]
        assert len(llm.captured_contents) == 1, "a silent turn asked the model again"

        await rig.driver.user_says("Thanks.")
        spoken = " ".join(
            part.text or ""
            for content in llm.captured_contents[-1]
            if content.role == "model"
            for part in content.parts or []
        )
        assert line not in spoken, f"the brain's line {line!r} reached the context"
