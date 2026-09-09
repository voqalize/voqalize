"""The screen naming what he did — the browser→brain half of the contract.

A :mod:`desk_events` message says the act outright: ``li3 quantity set to 5``,
addressed by row id. Nothing is inferred because nothing is diffed — there is no
snapshot behind these events, and no repair channel behind that.

So the property this file holds is **completeness**, not idempotence. An act the
screen does not send is an act the brain never learns about, which makes the
inventory below the contract itself: one test per gesture, each asserting that the
mirror moved and that the sentence handed to the model is the one he would use.

Run: ``cd demos && uv run pytest tests/test_orderdesk_desk_events.py``
"""

from __future__ import annotations

from typing import cast

import pytest
from voqalize_demos.discovery import discover

discover()

from voqalize_demos._loaded.orderdesk.brain import OrderDesk, SpokenItem  # noqa: E402
from voqalize_demos._loaded.orderdesk.desk_events import (  # noqa: E402
    DESK_EVENTS,
    CatalogSearched,
    FamilyChosen,
    OrderConfirmed,
    QuantitySet,
    QuestionAnswered,
    RowAdded,
    RowRemoved,
    SkuChosen,
    VariantsOpened,
)

from voqalize.sdk import Action, RTVIMessage, RTVIType, Session  # noqa: E402


class _Screen:
    def __init__(self) -> None:
        self.drawn: list[Action] = []

    def dispatch(self, action: Action) -> None:
        self.drawn.append(action)


def _desk() -> OrderDesk:
    desk = OrderDesk()
    desk.session = cast(Session, _Screen())
    return desk


# ─── the vocabulary ────────────────────────────────────────────────────────────


def _ui_event(name: str, payload: dict[str, object]) -> RTVIMessage:
    """What ``client.sendUIEvent(name, payload)`` puts on the wire."""
    return RTVIMessage(type=RTVIType.UI_EVENT, data={"event": name, "payload": payload})


def test_the_wire_name_of_an_event_is_its_class_name() -> None:
    """The same contract ``Action`` has in the other direction: the class name *is*
    the wire name, so nothing about it is written down twice."""
    assert SkuChosen.__voqal_event__ == "sku_chosen"
    assert QuestionAnswered.__voqal_event__ == "question_answered"
    assert OrderConfirmed.__voqal_event__ == "order_confirmed"


def test_every_gesture_this_desk_knows_is_in_the_vocabulary() -> None:
    """:data:`DESK_EVENTS` is what ``on_rtvi`` reads and what ``actions.gen.ts`` is
    generated from, so a class declared and left out of it is a gesture the screen
    can send and the brain silently drops."""
    assert {e.__voqal_event__ for e in DESK_EVENTS} == {
        "sku_chosen",
        "row_added",
        "row_removed",
        "question_answered",
        "family_chosen",
        "quantity_set",
        "order_confirmed",
        "catalog_searched",
        "variants_opened",
    }


def test_a_gesture_arrives_typed_off_the_wire() -> None:
    parsed = DESK_EVENTS.parse(_ui_event("quantity_set", {"item_id": "li1", "quantity": 5}))
    assert parsed == QuantitySet(item_id="li1", quantity=5)


def test_a_message_this_brain_cannot_read_is_not_a_crash() -> None:
    """A browser one deploy ahead names an act this brain has never heard of. That
    is a gap in the mirror — a real one, since nothing arrives later to close it —
    but a gap is a log line, never an exception on a live call."""
    assert DESK_EVENTS.parse(_ui_event("teleport_row", {"item_id": "li1"})) is None
    assert DESK_EVENTS.parse(_ui_event("quantity_set", {"item_id": "li1"})) is None  # no quantity
    assert (
        DESK_EVENTS.parse(_ui_event("quantity_set", {"item_id": "li1", "quantity": 5, "c": "red"}))
        is None
    )


# ─── the mirror, told rather than inferred ─────────────────────────────────────


@pytest.mark.asyncio
async def test_a_quantity_he_typed_arrives_named() -> None:
    """The event names the row and the number, so one thumb is one line in the
    model's context — no diff to run and nothing to infer it from."""
    desk = _desk()
    await desk.add_items([SpokenItem(text="telma 40", quantity=10)])
    (row,) = desk.items.values()

    desk.apply_event(QuantitySet(item_id=row.id, quantity=5))
    assert row.quantity == 5
    note = desk.take_changes() or ""
    assert f"{row.id} ({row.spoken_text}) quantity set to 5" in note
    assert desk.take_changes() is None, "the same news twice"


@pytest.mark.asyncio
async def test_the_gesture_that_chose_a_sku_is_part_of_what_the_model_is_told() -> None:
    """Three gestures put one medicine on one row, and they are not the same thing
    to say back to him: picking off the options offered, swapping the variant on a
    row already settled, and finding it in search himself."""
    desk = _desk()
    await desk.add_items([SpokenItem(text="guard cream")])
    (row,) = desk.items.values()
    first, second = row.candidates[0], row.candidates[1]

    desk.apply_event(
        SkuChosen(item_id=row.id, sku_code=first.code, sku_name=first.name, via="pill")
    )
    assert row.status == "matched"
    assert row.sku is not None and row.sku.code == first.code
    assert f"picked {first.name}" in (desk.take_changes() or "")

    desk.apply_event(
        SkuChosen(item_id=row.id, sku_code=second.code, sku_name=second.name, via="variant")
    )
    assert row.sku is not None and row.sku.code == second.code
    assert f"switched to {second.name}" in (desk.take_changes() or "")


@pytest.mark.asyncio
async def test_an_answered_question_says_what_was_asked_and_what_survived() -> None:
    """The inferred version of this could only ever report arithmetic — "narrowed to
    3 candidates". The event carries the question he answered and the words he
    answered it with, and the row lands in the same place either way."""
    desk = _desk()
    await desk.add_items([SpokenItem(text="guard cream")])
    (row,) = desk.items.values()
    ring = [sku.code for sku in row.candidates if sku.family == "RING"]
    assert len(ring) >= 2

    desk.apply_event(
        QuestionAnswered(
            item_id=row.id, question="Which brand?", answer="RING", surviving_codes=ring
        )
    )
    assert row.status == "multi_variant"
    assert row.family == "RING"
    note = desk.take_changes() or ""
    assert "'RING'" in note and "'Which brand?'" in note


@pytest.mark.asyncio
async def test_a_brand_he_picked_unasked_is_not_reported_as_an_answer() -> None:
    """Nobody asked. A family card is a brand he volunteered, and the next thing to
    say about it differs from the next thing to say about an answered question —
    which is the whole reason these are two events and not one."""
    desk = _desk()
    await desk.add_items([SpokenItem(text="guard cream")])
    (row,) = desk.items.values()
    ring = [sku.code for sku in row.candidates if sku.family == "RING"]

    desk.apply_event(FamilyChosen(item_id=row.id, family="RING", surviving_codes=ring))
    note = desk.take_changes() or ""
    assert "narrowed to RING by hand" in note
    assert "answered" not in note
    assert row.family == "RING"


@pytest.mark.asyncio
async def test_a_narrow_the_row_never_held_changes_nothing() -> None:
    """The candidate set is the brain's fact and only ever narrows. Being *told* a
    set does not make it authoritative: a code the row does not hold is a stale or
    confused browser, and folding it in would delete the answer he is looking at."""
    desk = _desk()
    await desk.add_items([SpokenItem(text="guard cream")])
    (row,) = desk.items.values()
    before = [sku.code for sku in row.candidates]

    desk.apply_event(FamilyChosen(item_id=row.id, family="RING", surviving_codes=["J9999999"]))
    assert [sku.code for sku in row.candidates] == before
    assert row.status == "multi_family"
    assert desk.version == 0, "nothing changed, so the model is not sent to re-read"


@pytest.mark.asyncio
async def test_a_row_he_added_from_search_is_a_row_the_tools_can_see() -> None:
    """A hand-added row the mirror never adopted is on screen and invisible to every
    tool. The event adopts it the instant he taps, and it is the only thing that
    will — nothing arrives behind it to notice the row later."""
    desk = _desk()
    await desk.add_items([SpokenItem(text="telma 40", quantity=10)])
    sku = desk.search_rows("volini")[0]

    desk.apply_event(
        RowAdded(item_id="m1", sku_code=sku.code, sku_name=sku.name, query="volini", quantity=2)
    )
    added = desk.items["m1"]
    assert added.status == "matched"
    assert added.sku is not None and added.sku.code == sku.code
    assert added.quantity == 2
    assert "added by hand from search" in (desk.take_changes() or "")


@pytest.mark.asyncio
async def test_a_deleted_row_is_named_after_it_is_gone() -> None:
    """The event carries the row's name because once it is out of the mirror there
    is nothing left to look the name up from — and "li2 removed" tells the model
    nothing it can say out loud."""
    desk = _desk()
    await desk.add_items([SpokenItem(text="telma 40", quantity=10)])
    (row,) = desk.items.values()

    desk.apply_event(RowRemoved(item_id=row.id, spoken_text=row.spoken_text))
    assert row.id not in desk.items
    assert f"({row.spoken_text}) removed by hand" in (desk.take_changes() or "")


@pytest.mark.asyncio
async def test_confirm_is_the_one_event_that_is_not_about_a_row() -> None:
    desk = _desk()
    await desk.add_items([SpokenItem(text="telma 40", quantity=10)])

    desk.apply_event(OrderConfirmed(order_no="MS-0930-1", item_count=1, total_mrp=1234.5))
    assert "he tapped Confirm — order MS-0930-1, 1 rows" in (desk.take_changes() or "")


@pytest.mark.asyncio
async def test_looking_is_not_editing() -> None:
    """The search bar and Change variant ride the same envelope as everything else,
    but they *ask* rather than edit: the brain answers each with a screen action, so
    the order has not moved and there is nothing to tell the model on the next turn.
    A change note here would report a keystroke as an edit he made."""
    desk = _desk()
    await desk.add_items([SpokenItem(text="telma 40", quantity=10)])
    (row,) = desk.items.values()
    desk.take_changes()

    desk.apply_event(CatalogSearched(query="cetaphil"))
    desk.apply_event(VariantsOpened(item_id=row.id, family="TELMA"))
    assert desk.take_changes() is None
    assert desk.version == 0


@pytest.mark.asyncio
async def test_an_event_for_a_row_that_is_not_there_is_ignored() -> None:
    """A row id this mirror does not hold is a browser and a brain that have parted
    company. Dropped, not invented — there is nothing to invent it *from*, and a row
    conjured out of an id would be a row no tool could ever resolve."""
    desk = _desk()
    desk.apply_event(QuantitySet(item_id="li99", quantity=3))
    desk.apply_event(SkuChosen(item_id="li99", sku_code="J0000001", via="pill"))
    desk.apply_event(RowRemoved(item_id="li99"))
    assert desk.version == 0
    assert desk.take_changes() is None
