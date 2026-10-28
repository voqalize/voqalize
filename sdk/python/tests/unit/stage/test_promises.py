"""The promise guard: a turn that says a move is happening and never sends it
is reported once, at the end of the turn."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest

from voqalize.sdk import Action
from voqalize.sdk.events import Speech, SpeechChunk, SpeechEnd, SpeechStart
from voqalize.sdk.stage import Move, MoveClass, Stage, StageResult, Unkept

CHECK = Move(
    id="site.check",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=("lodge",),
    claims=(
        "opening the * calendar",
        "checking availability",
        "abro el calendario",
        "reviso la disponibilidad",
    ),
)
SHOW = Move(id="core.show", verb="show", cls=MoveClass.LOOK, args=("target",))
PAGE = Move(
    id="core.page", verb="page", cls=MoveClass.NAVIGATE, args=("path",), claims=("opening it",)
)


class Clock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


def _stage() -> tuple[Stage, list[tuple[str, str, str]], Clock]:
    told: list[tuple[str, str, str]] = []
    sent: list[Action] = []
    clock = Clock()
    stage = Stage(
        dispatch=sent.append,
        moves=(CHECK, SHOW, PAGE),
        clock=clock,
        on_unkept=lambda move, phrase, sentence: told.append((move.id, phrase, sentence)),
    )
    return stage, told, clock


async def _say(stage: Stage, *chunks: str) -> str:
    async def turn() -> AsyncGenerator[Speech, None]:
        yield SpeechStart()
        for c in chunks:
            yield SpeechChunk(c)
        yield SpeechEnd()

    out = [e async for e in stage.cued(turn())]
    return "".join(e.text for e in out if isinstance(e, SpeechChunk))


async def test_a_claim_with_its_move_sent_is_kept() -> None:
    stage, told, _ = _stage()
    await _say(stage, "Let's look. I'm opening the ", "calendar for you.")
    # The tool call comes at the end of the response, after the words.
    stage.send("site.check", {"lodge": "EATA"})
    assert stage.end_turn() == []
    assert told == []


async def test_a_claim_without_its_move_is_reported_once() -> None:
    stage, told, _ = _stage()
    await _say(
        stage,
        "November is lovely. I'm opening the Atacama calendar for three nights. ",
        "I'm opening the calendar now.",
    )
    got = stage.end_turn()
    assert got == [
        Unkept(
            CHECK,
            "opening the * calendar",
            "I'm opening the Atacama calendar for three nights.",
        )
    ]
    assert told == [
        (
            "site.check",
            "opening the * calendar",
            "I'm opening the Atacama calendar for three nights.",
        )
    ]
    # The next turn starts clean: nothing said, nothing reported.
    assert stage.end_turn() == []
    assert len(told) == 1


async def test_a_spanish_claim_matches_without_its_accents() -> None:
    stage, told, _ = _stage()
    await _say(stage, "Perfecto. Ahora REVISO la disponibilidad para noviembre.")
    assert [u.phrase for u in stage.end_turn()] == ["reviso la disponibilidad"]
    # Written with the accent the claim leaves out, it is the same words.
    await _say(stage, "Ya. Ábro el calendario de Atacama.")
    assert [u.phrase for u in stage.end_turn()] == ["abro el calendario"]
    assert len(told) == 2


async def test_a_claim_inside_a_longer_word_is_not_one() -> None:
    stage, _, _ = _stage()
    await _say(stage, "We were rechecking availability last week, and reopening it later.")
    assert stage.end_turn() == []


async def test_a_running_or_cued_move_keeps_its_claim() -> None:
    stage, _, clock = _stage()
    ref = stage.send("site.check", {"lodge": "EATA"})
    assert ref is not None
    stage.end_turn()
    # Sent last turn and still on its way: the claim is true.
    await _say(stage, "I'm checking availability, the site is slow.")
    assert stage.end_turn() == []
    # Answered during this turn: still true of this turn.
    await _say(stage, "I'm checking availability.")
    clock.t += 1
    stage.handle(StageResult(call_ref=ref, move="site.check", outcome="applied"))
    assert stage.end_turn() == []
    # Answered in an earlier turn: a fresh claim is a fresh promise.
    clock.t += 1
    await _say(stage, "I'm checking availability again.")
    assert [u.move.id for u in stage.end_turn()] == ["site.check"]
    # A cue counts as sent.
    await _say(stage, "{page: /rooms} Opening it now.")
    assert stage.end_turn() == []


async def test_an_offer_is_not_a_claim() -> None:
    stage, _, _ = _stage()
    await _say(stage, "Shall I go on checking availability? ¿Abro el calendario?")
    assert stage.end_turn() == []


async def test_begin_turn_forgets_a_turn_cut_off() -> None:
    stage, _, _ = _stage()
    await _say(stage, "I'm opening the calendar.")
    stage.begin_turn()
    assert stage.end_turn() == []


def test_a_claim_needs_words_on_both_sides_of_a_gap() -> None:
    with pytest.raises(ValueError, match="claim"):
        Move(id="x.y", verb=None, cls=MoveClass.LOOK, claims=("* calendar",))
    with pytest.raises(ValueError, match="claim"):
        Move(id="x.y", verb=None, cls=MoveClass.LOOK, claims=("...",))
