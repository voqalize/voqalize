"""The screen naming what he did, instead of the brain inferring it from a cart.

``state_sync`` carries a whole ``OrderSnapshot``, so neither end ever names a
change: :meth:`OrderDesk.absorb` diffs its old picture against the new one and
infers which act produced the difference. A :mod:`desk_events` message says it
outright — ``li3 quantity set to 5``, addressed by row id.

The property that lets both live at once, and the one most of this file is about:
an event and the snapshot behind it must not report the same thumb twice. The
snapshot still arrives 250 ms later with everything in it; by then the change is
applied, its diff finds nothing, and the model is told once. That is what makes
this safe to add without touching the wire — and it is also the repair path, so
an event dropped on the way is recovered rather than lost.

Run: ``cd demos && uv run pytest tests/test_orderdesk_desk_events.py``
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from voqalize_demos.discovery import discover

discover()

from voqalize_demos._loaded.orderdesk.brain import OrderDesk, SpokenItem  # noqa: E402
from voqalize_demos._loaded.orderdesk.desk_events import (  # noqa: E402
    FamilyChosen,
    OrderConfirmed,
    QuantitySet,
    QuestionAnswered,
    RowAdded,
    RowRemoved,
    SkuChosen,
    parse_event,
)

from voqalize.sdk import Action, Session  # noqa: E402


class _Screen:
    def __init__(self) -> None:
        self.drawn: list[Action] = []

    def dispatch(self, action: Action) -> None:
        self.drawn.append(action)


def _desk() -> OrderDesk:
    desk = OrderDesk()
    desk.session = cast(Session, _Screen())
    return desk


def _snapshot(desk: OrderDesk, **narrowed: list[str]) -> dict[str, dict[str, Any]]:
    """The browser's own snapshot of what is on screen — the debounced repair
    channel, exactly as ``state_sync`` sends it after the event has landed."""
    return {
        row.id: {
            "id": row.id,
            "status": row.status,
            "spoken_text": row.spoken_text,
            "sku_code": row.sku.code if row.sku else None,
            "quantity": row.quantity,
            "candidate_codes": narrowed.get(
                row.id, [sku.code for sku in (row.candidates or row.variants)]
            ),
        }
        for row in desk.items.values()
    }


# ─── the vocabulary ────────────────────────────────────────────────────────────


def test_the_wire_name_of_an_event_is_its_class_name() -> None:
    """The same contract ``Action`` has in the other direction: the class name *is*
    the wire name, so nothing about it is written down twice."""
    assert SkuChosen.__voqal_event__ == "sku_chosen"
    assert QuestionAnswered.__voqal_event__ == "question_answered"
    assert OrderConfirmed.__voqal_event__ == "order_confirmed"
    assert parse_event("quantity_set", {"item_id": "li1", "quantity": 5}) == QuantitySet(
        item_id="li1", quantity=5
    )


def test_a_message_this_brain_cannot_read_is_not_a_crash() -> None:
    """A browser one deploy ahead has to degrade to the ``state_sync`` it still
    sends. An unknown name and a payload that does not fit are both a ``None`` and
    a log line — never an exception on a live call."""
    assert parse_event("teleport_row", {"item_id": "li1"}) is None
    assert parse_event("quantity_set", {"item_id": "li1"}) is None  # no quantity
    assert parse_event("quantity_set", {"item_id": "li1", "quantity": 5, "colour": "red"}) is None


# ─── the mirror, told rather than inferred ─────────────────────────────────────


@pytest.mark.asyncio
async def test_a_quantity_he_typed_arrives_named_and_the_snapshot_does_not_repeat_it() -> None:
    """The event names the row and the number. The snapshot that follows carries
    the same number, finds the mirror already holding it, and says nothing — so one
    thumb is one line in the model's context, not two."""
    desk = _desk()
    await desk.add_items([SpokenItem(text="telma 40", quantity=10)])
    (row,) = desk.items.values()

    desk.apply_event(QuantitySet(item_id=row.id, quantity=5))
    assert row.quantity == 5
    note = desk.take_changes() or ""
    assert f"{row.id} ({row.spoken_text}) quantity set to 5" in note

    desk.absorb(_snapshot(desk))
    assert desk.take_changes() is None, "the repair channel repeated the news"


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

    desk.absorb(_snapshot(desk))
    assert desk.take_changes() is None


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

    desk.absorb(_snapshot(desk, **{row.id: ring}))
    assert desk.take_changes() is None


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
async def test_a_narrow_the_row_never_held_changes_nothing_by_event_either() -> None:
    """The candidate set is still the brain's fact and still only ever narrows.
    Being *told* a set does not make it authoritative — the ownership rule is one
    rule, and both paths go through it."""
    desk = _desk()
    await desk.add_items([SpokenItem(text="guard cream")])
    (row,) = desk.items.values()
    before = [sku.code for sku in row.candidates]

    desk.apply_event(FamilyChosen(item_id=row.id, family="RING", surviving_codes=["J9999999"]))
    assert [sku.code for sku in row.candidates] == before
    assert desk.version == 0, "nothing changed, so the model is not sent to re-read"


@pytest.mark.asyncio
async def test_a_row_he_added_from_search_is_a_row_the_tools_can_see() -> None:
    """A hand-added row the mirror never adopted is on screen and invisible to every
    tool. The event adopts it the instant he taps, rather than a debounce later."""
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

    desk.absorb(_snapshot(desk))
    assert desk.take_changes() is None


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

    desk.absorb(_snapshot(desk))
    assert desk.take_changes() is None


@pytest.mark.asyncio
async def test_confirm_is_the_one_event_that_is_not_about_a_row() -> None:
    desk = _desk()
    await desk.add_items([SpokenItem(text="telma 40", quantity=10)])

    desk.apply_event(OrderConfirmed(order_no="MS-0930-1", item_count=1, total_mrp=1234.5))
    assert "he tapped Confirm — order MS-0930-1, 1 rows" in (desk.take_changes() or "")


@pytest.mark.asyncio
async def test_an_event_for_a_row_that_is_not_there_is_ignored() -> None:
    """Events race the snapshot both ways. One aimed at a row the mirror does not
    hold is dropped, not invented — the snapshot behind it is what adopts rows."""
    desk = _desk()
    desk.apply_event(QuantitySet(item_id="li99", quantity=3))
    desk.apply_event(SkuChosen(item_id="li99", sku_code="J0000001", via="pill"))
    desk.apply_event(RowRemoved(item_id="li99"))
    assert desk.version == 0
    assert desk.take_changes() is None
