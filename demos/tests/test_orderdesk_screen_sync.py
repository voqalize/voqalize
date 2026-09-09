"""The two correction paths, kept in step — thumb and voice on one row.

A misheard order is normal (DESIGN §2), so the cheap thing has to be *fixing* it,
and there are exactly two ways to: he taps the screen, or he says it again. Those
paths meet in :meth:`OrderDesk.absorb`, where the browser's narrowed row is folded
back into the mirror the model reads. Everything below is that seam — no LLM, no
network, the real catalog.

Run: ``cd demos && uv run pytest tests/test_orderdesk_screen_sync.py``
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from voqalize_demos.discovery import discover

discover()

from voqalize_demos._loaded.orderdesk.brain import (  # noqa: E402
    Choice,
    OrderDesk,
    SpokenItem,
)

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


def _snapshot(desk: OrderDesk, **narrowed: list[str]) -> dict[str, dict[str, Any]]:
    """The browser's own OrderSnapshot for what is on screen, with the named rows
    narrowed to the codes given — which is all a group-pill tap is on the wire."""
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
    desk.absorb(_snapshot(desk, **{row.id: ring}))

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
    live = _snapshot(desk, **{row.id: ring})
    desk.absorb(live)

    assert f"narrowed to {len(ring)}" in (desk.pending(live) or "")
    assert f"narrowed to {len(ring)} candidates by hand" in (desk.take_changes() or "")

    await desk.read_screen()
    split = await desk.ask_choice(
        row.id,
        "Which pack?",
        [Choice(label="small", sku_codes=ring[:1]), Choice(label="big", sku_codes=ring[1:])],
    )
    assert "no candidate set to split" in split["error"]
    assert split["options"] == ring, "the pills he can already see"


@pytest.mark.asyncio
async def test_a_narrow_the_row_never_held_changes_nothing() -> None:
    """The candidate set is the brain's fact and only ever narrows. A snapshot
    naming codes the row does not hold is a stale or confused browser, and folding
    it in would delete the answer he is looking at."""
    desk, _ = _desk()
    await desk.add_items([SpokenItem(text="guard cream")])
    (row,) = desk.items.values()
    before = [sku.code for sku in row.candidates]
    desk.absorb(_snapshot(desk, **{row.id: ["J9999999"]}))
    assert [sku.code for sku in row.candidates] == before
    assert row.status == "multi_family"
    assert desk.version == 0, "nothing changed, so the model is not sent to re-read"
