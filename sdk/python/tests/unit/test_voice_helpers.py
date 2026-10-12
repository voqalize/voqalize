"""A turn that acted on screen and said nothing gets a line of the brain's own.

On real calls the model sometimes calls an action tool alone, and the user
hears nothing until the runtime's watchdog apologises. :mod:`voqalize.sdk.voice_helpers` is the floor under the prompt's rule
— a written line, no second request; these pin what it does and, as much, what it
leaves alone.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncGenerator
from itertools import pairwise
from typing import Any, cast

from voqalize.sdk import Speech, SpeechChunk, SpeechEnd, SpeechStart
from voqalize.sdk.gemini import GeminiBrain
from voqalize.sdk.voice_helpers import PHRASES, FallbackLine, landed

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
