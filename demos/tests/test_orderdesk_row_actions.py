"""The brain naming what it did — the brain→app half of the contract.

The old shape was one ``upsert_items`` carrying whole rows, and it failed the way
every whole-state push fails: an action sent for one reason arrived carrying every
*other* field too, so a message that was merely late could undo something it was
never about. The browser grew ``pinned``, ``keepChoice`` and ``offersPin`` to
defend itself, and those guards then had semantics of their own to get wrong.

Fine granularity retires the guards by making them unnecessary (CLAUDE.md). Each
action below names one row and carries only what moved on it, so the blast radius
of a stale message is the field it names and nothing else — a :class:`RowQuestion`
puts a question back and *cannot* un-match a row, because it has no SKU to un-match
it with. That is a property of the shapes, so it is asserted on the shapes; the
rest of the file is the dispatch itself, tool by tool.

Run: ``cd demos && uv run pytest tests/test_orderdesk_row_actions.py``
"""

from __future__ import annotations

from typing import cast

import pytest
from voqalize_demos.discovery import discover

discover()

from voqalize_demos._loaded.orderdesk.brain import (  # noqa: E402
    Choice,
    OrderDesk,
    RowFamilies,
    RowMatched,
    RowNotFound,
    RowOpened,
    RowQuantity,
    RowQuestion,
    RowVariants,
    SpokenItem,
)

from voqalize.sdk import Action, Session  # noqa: E402

_ROW_ACTIONS = [
    RowOpened,
    RowMatched,
    RowFamilies,
    RowVariants,
    RowNotFound,
    RowQuestion,
    RowQuantity,
]


class _Screen:
    def __init__(self) -> None:
        self.drawn: list[Action] = []

    def dispatch(self, action: Action) -> None:
        self.drawn.append(action)


def _desk() -> tuple[OrderDesk, _Screen]:
    desk = OrderDesk()
    screen = _Screen()
    desk.session = cast(Session, screen)
    return desk, screen


def _commands(screen: _Screen) -> list[str]:
    return [type(action).__voqal_action__ for action in screen.drawn]


# ─── the shapes ────────────────────────────────────────────────────────────────


def test_every_row_action_names_exactly_one_row() -> None:
    """``id`` and no plural. There is no action that moves two rows at once, which
    is what lets the browser apply each one by a single lookup and lets a test read
    a dispatch log as a sentence."""
    for action in _ROW_ACTIONS:
        assert "id" in action.model_fields, action.__name__
        assert "items" not in action.model_fields, action.__name__


def test_only_the_match_carries_a_sku() -> None:
    """The whole defence, stated as a fact about the types. A late ``row_question``
    or ``row_quantity`` has no field with which to move the row off the medicine he
    settled it on — so the browser needs nothing pinned against one."""
    carrying = {a.__name__ for a in _ROW_ACTIONS if "sku" in a.model_fields}
    assert carrying == {"RowMatched"}
    assert set(RowQuestion.model_fields) == {"id", "question"}
    assert set(RowQuantity.model_fields) == {"id", "quantity"}


# ─── the dispatch ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_row_is_on_screen_before_the_catalog_is_asked() -> None:
    """He says it, it appears — greyed — and the outcome lands behind it. Two
    actions in that order is the screen keeping up with his voice rather than with
    the resolver, and ``row_opened`` carries no outcome because there is none yet."""
    desk, screen = _desk()
    await desk.add_items([SpokenItem(text="telma 40", quantity=2)])

    assert _commands(screen) == ["row_opened", "row_matched"]
    opened, matched = screen.drawn
    assert isinstance(opened, RowOpened) and isinstance(matched, RowMatched)
    assert opened.spoken_text == "telma 40" and opened.quantity == 2
    assert matched.id == opened.id and matched.sku.code


@pytest.mark.asyncio
async def test_each_outcome_is_its_own_action() -> None:
    """One action per way a row can land, so the browser renders by *which* message
    arrived and never by reading a status field off a row it was handed."""
    desk, screen = _desk()
    await desk.add_items([SpokenItem(text="guard cream")])  # several brands
    await desk.add_items([SpokenItem(text="qwertyuiop")])  # in no catalog

    assert _commands(screen) == ["row_opened", "row_families", "row_opened", "row_not_found"]
    families = screen.drawn[1]
    assert isinstance(families, RowFamilies) and len(families.families) >= 2


@pytest.mark.asyncio
async def test_a_question_put_on_a_row_says_only_that() -> None:
    """``ask_choice`` is the tool most likely to arrive late — it runs while he is
    already tapping. It sends a question and nothing else, so the worst a late one
    can do is show a question he has answered, which his next tap clears."""
    desk, screen = _desk()
    (brief,) = (await desk.add_items([SpokenItem(text="telma")]))["items"]
    (row,) = desk.items.values()
    codes = [sku.code for sku in row.candidates]
    assert brief["candidate_count"] >= 5, "need a row wide enough for a table"

    screen.drawn.clear()
    asked = await desk.ask_choice(
        row.id,
        "Which Telma line?",
        [
            Choice(label="plain", sku_codes=codes[: len(codes) // 2]),
            Choice(label="combination", sku_codes=codes[len(codes) // 2 :]),
        ],
    )
    assert "error" not in asked, asked

    (drawn,) = screen.drawn
    assert isinstance(drawn, RowQuestion)
    assert drawn.id == row.id
    assert drawn.question.text == "Which Telma line?"


@pytest.mark.asyncio
async def test_a_quantity_change_moves_the_quantity_and_leaves_the_row_alone() -> None:
    """The one row action that leaves a note standing, and the one whose whole
    payload is a number. A matched row stays matched across it because nothing in
    the message could say otherwise."""
    desk, screen = _desk()
    await desk.add_items([SpokenItem(text="telma 40", quantity=2)])
    (row,) = desk.items.values()
    screen.drawn.clear()

    await desk.set_quantity(row.id, 7)
    await desk.adjust_quantity(row.id, -2)

    assert _commands(screen) == ["row_quantity", "row_quantity"]
    assert all(isinstance(action, RowQuantity) for action in screen.drawn)
    assert [cast(RowQuantity, action).quantity for action in screen.drawn] == [7, 5]
    assert row.status == "matched" and row.sku is not None


@pytest.mark.asyncio
async def test_a_re_resolve_settles_the_row_and_says_nothing_before_that() -> None:
    """A spoken correction is one beat, not two. `_resolve_into` is synchronous, so an
    action announcing the attempt would blank the row for a fraction of a frame and then
    overwrite itself — the row goes straight from the rejected medicine to the new
    outcome, and the screen never shows an empty one in between."""
    desk, screen = _desk()
    await desk.add_items([SpokenItem(text="abevia")])
    (row,) = desk.items.values()
    screen.drawn.clear()

    fixed = await desk.refine_item(row.id, "abiways")
    assert "error" not in fixed, fixed
    commands = _commands(screen)
    assert len(commands) == 1, f"a correction should be one action, got {commands}"
    assert commands[0].startswith("row_")
    assert commands[0] != "row_opened", "the row already exists; this is a verdict"
