"""Moves are checked where they are declared, not in the middle of a call."""

from __future__ import annotations

import pytest

from voqalize.sdk.stage import Move, MoveClass, MoveSet


def test_a_cueable_move_with_a_verb() -> None:
    m = Move(id="core.show", verb="show", cls=MoveClass.LOOK, args=("target",))
    assert (m.verb, m.args, m.say) == ("show", ("target",), "")


@pytest.mark.parametrize(
    "verb",
    ["Show", "s", "show_it", "show2", "core.show", "averyveryverylongverb", ""],
)
def test_a_verb_is_one_short_lowercase_word(verb: str) -> None:
    with pytest.raises(ValueError, match="lowercase word"):
        Move(id="x", verb=verb, cls=MoveClass.LOOK)


@pytest.mark.parametrize("verb", ["name", "function", "tool", "call", "args", "action"])
def test_a_verb_that_names_a_function_call_is_refused(verb: str) -> None:
    with pytest.raises(ValueError, match="function call"):
        Move(id="x", verb=verb, cls=MoveClass.LOOK)


def test_a_confirmed_move_has_no_verb() -> None:
    with pytest.raises(ValueError, match="only ever made by a tool"):
        Move(id="cart.add", verb="add", cls=MoveClass.CONFIRMED)
    assert Move(id="cart.add", verb=None, cls=MoveClass.CONFIRMED).verb is None


def test_a_cue_takes_at_most_four_args_and_a_tool_move_twelve() -> None:
    with pytest.raises(ValueError, match="at most 4, since a cue carries them"):
        Move(id="x", verb="show", cls=MoveClass.LOOK, args=("a", "b", "c", "d", "e"))
    assert len(Move(id="x", verb=None, cls=MoveClass.LOOK, args=tuple("abcde")).args) == 5
    with pytest.raises(ValueError, match="at most 12"):
        Move(id="x", verb=None, cls=MoveClass.LOOK, args=tuple("abcdefghijklm"))


def test_a_move_set_refuses_duplicates() -> None:
    show = Move(id="core.show", verb="show", cls=MoveClass.LOOK)
    with pytest.raises(ValueError, match="id"):
        MoveSet([show, Move(id="core.show", verb="ring", cls=MoveClass.LOOK)])
    with pytest.raises(ValueError, match="share the verb"):
        MoveSet([show, Move(id="core.other", verb="show", cls=MoveClass.LOOK)])
    moves = MoveSet([show, Move(id="cart.add", verb=None, cls=MoveClass.CONFIRMED)])
    assert moves.by_verb("show") is show and moves["core.show"] is show
    assert moves.verbs == {"show"} and len(moves) == 2 and "cart.add" in moves
