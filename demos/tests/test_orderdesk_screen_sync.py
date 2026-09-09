"""The two correction paths, kept in step — thumb and voice on one row.

A misheard order is normal (DESIGN §2), so the cheap thing has to be *fixing* it,
and there are exactly two ways to: he taps the screen, or he says it again. Those
paths meet in :meth:`OrderDesk.apply_event`, where the gesture he made — named,
not diffed out of a cart — moves the mirror the model reads. Everything below is
that seam: no LLM, no network, the real catalog.

Run: ``cd demos && uv run pytest tests/test_orderdesk_screen_sync.py``
"""

from __future__ import annotations

from typing import cast

import pytest
from voqalize_demos.discovery import discover

discover()

from voqalize_demos._loaded.orderdesk.brain import (  # noqa: E402
    Choice,
    OrderDesk,
    SpokenItem,
)
from voqalize_demos._loaded.orderdesk.desk_events import FamilyChosen  # noqa: E402

from voqalize.sdk import Action, Session  # noqa: E402


class _Screen:
    """Stands in for the RTVI channel: a tool's dispatch is a draw, and this keeps
    them so a test can assert the screen was told, not just the mirror."""

    def __init__(self) -> None:
        self.drawn: list[Action] = []

    def dispatch(self, action: Action) -> None:
        self.drawn.append(action)


def _desk() -> tuple[OrderDesk, _Screen]:
    desk = OrderDesk()
    screen = _Screen()
    desk.session = cast(Session, screen)
    return desk, screen


@pytest.mark.asyncio
async def test_a_brand_picked_by_thumb_is_a_brand_the_voice_path_can_use() -> None:
    """He taps the RING card; the next thing he *says* has to land on RING.

    Before ``_resettle`` the mirror narrowed its candidate list and stopped there:
    the row still read ``multi_family`` with no family on it, so ``change_variant``
    answered a question about a pack size with "no brand settled yet" — on a row
    whose brand he had just settled with his thumb. That is the two paths at odds,
    and it is the whole defect this file exists to pin."""
    desk, _ = _desk()
    await desk.add_items([SpokenItem(text="guard cream")])
    (row,) = desk.items.values()
    assert row.status == "multi_family"
    assert {family.family for family in row.families} == {"RING", "ITCH"}

    ring = [sku.code for sku in row.candidates if sku.family == "RING"]
    assert len(ring) >= 2, "need a family with variants left to ask about"
    desk.apply_event(FamilyChosen(item_id=row.id, family="RING", surviving_codes=ring))

    assert row.status == "multi_variant"
    assert row.family == "RING"
    assert row.families == []
    assert [sku.code for sku in (row.variants or row.candidates)] == ring
    assert "variant_label" not in row.differing_axes, "asking about what they agree on"

    await desk.read_screen()
    settled = await desk.change_variant(row.id, "5 gm")
    assert "error" not in settled, settled
    assert row.status == "matched"
    assert row.sku is not None and row.sku.family == "RING"


@pytest.mark.asyncio
async def test_the_narrowed_row_is_reported_as_narrowed_not_as_empty() -> None:
    """Two counters read the row after a hand-narrow, and both used to read
    ``candidates`` alone — which ``_resettle`` empties when the survivors fit under
    the pill floor. "Narrowed to 0" is what the model was told about a row showing
    three choices, and a candidate table is what it was told to split when the
    browser had already turned those three into pills."""
    desk, _ = _desk()
    await desk.add_items([SpokenItem(text="guard cream")])
    (row,) = desk.items.values()
    ring = [sku.code for sku in row.candidates if sku.family == "RING"]
    desk.apply_event(FamilyChosen(item_id=row.id, family="RING", surviving_codes=ring))

    assert f"narrowed to {len(ring)}" in (desk.pending() or "")
    assert f"narrowed to RING by hand — {len(ring)} left" in (desk.take_changes() or "")

    await desk.read_screen()
    split = await desk.ask_choice(
        row.id,
        "Which pack?",
        [Choice(label="small", sku_codes=ring[:1]), Choice(label="big", sku_codes=ring[1:])],
    )
    assert "no candidate set to split" in split["error"]
    assert split["options"] == ring, "the pills he can already see"


@pytest.mark.asyncio
async def test_a_group_pill_that_rules_out_brands_rules_them_off_the_briefing() -> None:
    """A wide ``multi_family`` row gets a candidate table and a splitting question, so
    the group he taps can leave several brands standing rather than one. The cards on
    his screen shrink to those; the model was still being handed all five to ask
    about, three of them brands he had just ruled out."""
    desk, _ = _desk()
    await desk.add_items([SpokenItem(text="kof")])
    (row,) = desk.items.values()
    offered = [fam.family for fam in row.families]
    assert len(offered) >= 4, offered

    keeping = set(offered[:2])
    desk.apply_event(
        FamilyChosen(
            item_id=row.id,
            family=offered[0],
            surviving_codes=[s.code for s in row.candidates if s.family in keeping],
        )
    )

    assert row.status == "multi_family", "two brands left is still a brand question"
    assert [fam.family for fam in row.families] == offered[:2]


@pytest.mark.asyncio
async def test_a_spoken_correction_finds_the_row_by_what_he_called_it() -> None:
    """ "Abevia nahi, abiways" — he names the product, not the row id. Every other
    row-editing tool already took either; ``refine_item``, the one a spoken
    correction actually reaches for, used to cost a turn looking the id up."""
    desk, _ = _desk()
    await desk.add_items([SpokenItem(text="abevia")])
    (row,) = desk.items.values()

    fixed = await desk.refine_item("abevia", "abiways")
    assert "error" not in fixed, fixed
    assert fixed["id"] == row.id
    assert row.query == "abiways"


@pytest.mark.asyncio
async def test_a_row_already_waiting_on_an_answer_is_not_handed_its_table_again() -> None:
    """He says the same medicine twice while a question about it is still on screen.

    The second ``add_items`` lands on the row he already has (the dedupe), and used to
    answer with the whole twenty-four-line candidate table a second time — a kilobyte
    the model had already been given, folded into the history verbatim, for a row whose
    only news is that nobody has answered yet. It is also how a third question gets
    phrased with no record of the two before it."""
    desk, _ = _desk()
    (brief,) = (await desk.add_items([SpokenItem(text="telma")]))["items"]
    (row,) = desk.items.values()
    assert brief["candidate_count"] >= 5, "need a row wide enough for a table"
    assert brief["candidates"], "the first briefing is the table"

    codes = [sku.code for sku in row.candidates]
    await desk.read_screen()
    asked = await desk.ask_choice(
        row.id,
        "Which Telma line?",
        [
            Choice(label="plain", sku_codes=codes[: len(codes) // 2]),
            Choice(label="combination", sku_codes=codes[len(codes) // 2 :]),
        ],
    )
    assert "error" not in asked, asked

    again = (await desk.add_items([SpokenItem(text="telma")]))["items"][0]
    assert "candidates" not in again, "the table was handed over a second time"
    assert again["asked"] == "Which Telma line?"
    assert [group["label"] for group in again["groups"]] == ["plain", "combination"]
    assert sorted(code for group in again["groups"] for code in group["codes"]) == sorted(codes)
    assert len(desk.items) == 1, "and it is still one row"
