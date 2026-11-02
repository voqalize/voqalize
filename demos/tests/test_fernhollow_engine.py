"""Fernhollow's engines, pinned to fixed outputs — and every tool timed.

Each engine is a pure function over the committed indexes, so its answer for a
fixed brief is a fixed list of ids. The expected values below were read off
the engines once and written down; a change to the word lists, the recipes,
the scoring or the precomputed neighbours that moves one fails here, and the
diff says exactly which answer moved.

The latency test runs every one of the 16 tool functions on a real brain
(with a recording session in place of the socket) and holds each to 10 ms —
half the SDK's tool budget.

Run: ``cd demos && uv run pytest tests/test_fernhollow_engine.py``
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, cast

import pytest
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini

from voqalize.sdk import Session

discover()

from voqalize_demos._loaded.fernhollow import brain as fb  # noqa: E402
from voqalize_demos._loaded.fernhollow import engine as eng  # noqa: E402
from voqalize_demos._loaded.fernhollow import words as w  # noqa: E402
from voqalize_demos._loaded.fernhollow.catalog import CATALOG  # noqa: E402

WOOD = eng.map_terms("materials", ["wood"]).words
BRIEF = eng.Brief(
    room="home-office", uses=("long hours",), materials=WOOD, styles=("modern",), budget=2500.0
)


def _ids(items: list[eng.Item]) -> list[str]:
    return [i.product_id for i in items]


# ─── Words ────────────────────────────────────────────────────────────────────


def test_words_take_the_longest_form_once() -> None:
    assert w.find("Cast iron skillet with an oak handle", w.MATERIALS) == ["iron", "oak"]
    assert w.find("Bouclé and wooden legs", w.MATERIALS) == ["boucle", "wood"]
    assert w.find("Ash-grey wash", w.MATERIALS) == ["ash"]


def test_a_material_around_the_product_is_not_its_material() -> None:
    """ "brings warmth to wooden or tiled floors" says nothing about a rug's material."""
    rug = CATALOG.products["large-natural-fiber-area-rug"]
    assert "wood" not in rug.materials
    taupe = CATALOG.products["warm-taupe-cotton-area-rug"]
    assert taupe.materials == ("cotton",)
    assert taupe.sources["cotton"] == "Warm Taupe cotton area rug"


def test_filter_mapping_states_its_assumption() -> None:
    wood = eng.map_terms("materials", ["wood"])
    assert wood.words[:4] == ("wood", "oak", "walnut", "ash")
    assert wood.assumptions == ("I read 'wood' as wood, oak, walnut, ash, birch and similar",)
    scandi = eng.map_terms("styles", ["Scandinavian"])
    assert scandi.words == ("minimalist",)
    assert scandi.assumptions == (
        "nothing here is described as 'Scandinavian', so I went with minimalist",
    )
    oak = eng.map_terms("materials", ["oak"])
    assert oak.words == ("oak",) and oak.assumptions == ()
    neon = eng.map_terms("colours", ["neon"])
    assert neon.words == () and neon.unmatched == ("neon",)


def test_filters_map_to_a_fixed_grid() -> None:
    f = eng.Filters(category="desks", materials=WOOD, price_max=500)
    ids = f.results()
    assert ids == EXPECTED_WOOD_DESKS_UNDER_500
    assert all(CATALOG.products[i].price <= 500 for i in ids)


# ─── The brief ────────────────────────────────────────────────────────────────


def test_brief_narrows_one_question_at_a_time() -> None:
    q = eng.next_question(eng.Brief())
    assert q.dim == "room" and q.text == "Which room are we working on?"
    office = eng.Brief(room="home-office")
    assert (
        len(eng.products_left(office)) == 145
    )  # desks, chairs, shelving, lamps, rugs after the misfiled clean-up
    q = eng.next_question(office)
    assert (q.dim, q.options) == EXPECTED_FIRST_TASTE_QUESTION
    tasted = eng.Brief(room="home-office", materials=WOOD, styles=("modern",))
    assert len(eng.products_left(tasted)) == EXPECTED_LEFT_WOOD_MODERN
    assert eng.next_question(tasted).dim == "budget"
    budgeted = eng.Brief(room="home-office", materials=WOOD, styles=("modern",), budget=2500)
    assert eng.next_question(budgeted).dim == "uses"
    assert eng.next_question(BRIEF).dim == "ready"
    skipped = eng.Brief(room="home-office", skipped=("styles", "materials", "colours"))
    assert eng.next_question(skipped).dim == "budget"


# ─── Rooms ────────────────────────────────────────────────────────────────────


def test_room_set_for_a_fixed_brief_and_budget() -> None:
    room = eng.build_room(BRIEF)
    assert isinstance(room, eng.RoomSet)
    assert [(p.slot, p.product_id) for p in room.pieces] == EXPECTED_ROOM
    assert room.total == EXPECTED_ROOM_TOTAL <= 2500
    assert [p.reason for p in room.pieces] == EXPECTED_ROOM_REASONS


def test_long_hours_weights_the_chair() -> None:
    sitting = eng.build_room(BRIEF)
    passing = eng.build_room(replace_uses(BRIEF, ()))
    assert isinstance(sitting, eng.RoomSet) and isinstance(passing, eng.RoomSet)
    chair = sitting.piece("chair")
    assert chair is not None and chair.product.comfort, (
        "the chair for long hours has no comfort words"
    )
    other = passing.piece("chair")
    assert other is not None
    assert len(chair.product.comfort) >= len(other.product.comfort)


def replace_uses(b: eng.Brief, uses: tuple[str, ...]) -> eng.Brief:
    from dataclasses import replace

    return replace(b, uses=uses)


def test_a_budget_below_the_cheapest_set_is_refused_with_the_floor() -> None:
    result = eng.build_room(eng.Brief(room="home-office", budget=100))
    assert isinstance(result, eng.RoomError)
    assert result.lowest_total == EXPECTED_OFFICE_FLOOR


def test_swap_holds_the_rest_of_the_room() -> None:
    room = eng.build_room(BRIEF)
    assert isinstance(room, eng.RoomSet)
    lamp = room.piece("lamp")
    assert lamp is not None
    new = eng.swap_piece(room, BRIEF, "lamp", seen=[lamp.product_id])
    assert isinstance(new, eng.Piece)
    assert new.product_id == EXPECTED_SWAPPED_LAMP
    swapped = room.with_piece(new)
    assert [p.product_id for p in swapped.pieces if p.slot != "lamp"] == [
        p.product_id for p in room.pieces if p.slot != "lamp"
    ]
    assert swapped.total <= 2500
    cheaper = eng.swap_piece(room, BRIEF, "desk", cheaper=True)
    assert isinstance(cheaper, eng.Piece)
    desk = room.piece("desk")
    assert desk is not None and cheaper.product.price < desk.product.price


# ─── Strips and comparisons ───────────────────────────────────────────────────


def test_goes_with_is_fixed() -> None:
    room = eng.build_room(BRIEF)
    assert isinstance(room, eng.RoomSet)
    desk = room.piece("desk")
    assert desk is not None
    art = eng.goes_with(desk.product_id, category="artwork")
    assert [(i.product_id, i.reason) for i in art] == EXPECTED_ART
    mixed = eng.goes_with(desk.product_id, exclude=[p.product_id for p in room.pieces])
    assert len({CATALOG.products[i].category_slug for i in _ids(mixed)}) == len(mixed)


def test_more_like_changes_one_thing() -> None:
    room = eng.build_room(BRIEF)
    assert isinstance(room, eng.RoomSet)
    desk = room.piece("desk")
    assert desk is not None
    cheaper, _ = eng.more_like(desk.product_id, "cheaper")
    assert _ids(cheaper) == EXPECTED_CHEAPER_DESKS
    assert all(CATALOG.products[i].price < desk.product.price for i in _ids(cheaper))
    on_sale, _ = eng.more_like(desk.product_id, "on_sale")
    assert all(CATALOG.products[i].on_sale for i in _ids(on_sale))
    walnut, own = eng.more_like(desk.product_id, "option", "Walnut")
    assert own == desk.product.variant_for("Walnut").id
    for item in walnut:
        assert item.variant_id == CATALOG.products[item.product_id].variant_for("Walnut").id


def test_compare_orders_by_fit_then_comfort_then_price() -> None:
    chairs = CATALOG.by_category["office-chairs"]
    cmp = eng.compare([chairs[0], chairs[4], chairs[14]], BRIEF)
    assert list(cmp.product_ids) == EXPECTED_COMPARE_ORDER
    labels = [r.label for r in cmp.rows]
    assert labels[0] == "Price" and "For long hours" in labels
    price = cmp.rows[0]
    prices = [CATALOG.products[i].price for i in cmp.product_ids]
    assert price.winner == prices.index(min(prices))
    assert cmp.summary == EXPECTED_COMPARE_SUMMARY


def test_stretch_budget_uses_real_sale_prices() -> None:
    room = eng.build_room(BRIEF)
    assert isinstance(room, eng.RoomSet)
    s = eng.stretch_budget(room, BRIEF)
    assert [(x.slot, x.from_id, x.to_id) for x in s.swaps] == EXPECTED_STRETCH_SWAPS
    for x in s.swaps:
        to = CATALOG.products[x.to_id]
        assert to.on_sale and to.compare_at is not None and to.price < x.was
    assert s.saved == round(sum(x.was - x.now for x in s.swaps), 2) == EXPECTED_SAVED
    assert s.moved_to == EXPECTED_MOVED_TO
    assert s.room.total <= room.total + 1e-6


# ─── The returns desk ─────────────────────────────────────────────────────────


def test_order_eligibility_per_line() -> None:
    from voqalize_demos._loaded.fernhollow import returns as rt

    assert rt.WINDOW_DAYS == 30
    assert rt.normalise_number("fh 20418") == "FH-20418"
    inside = rt.find_order("FH-20418")
    assert inside is not None
    assert [(x.status, x.days_since_delivery, x.days_left) for x in inside.lines] == [
        ("eligible", 6, 24)
    ] * 3
    late = rt.find_order("20155")
    assert late is not None
    assert [(x.status, x.days_since_delivery) for x in late.lines] == [("outside_window", 41)]
    coming = rt.find_order("FH-20502")
    assert coming is not None and {x.status for x in coming.lines} == {"not_delivered"}
    assert rt.find_order("FH-99999") is None
    assert rt.exchange_options("desk-chair-with-aluminum-frame", "31094") == [("31095", "Walnut")]


# ─── Every tool under 10 ms ───────────────────────────────────────────────────


class _Screen:
    def __init__(self) -> None:
        self.sent: list[Any] = []

    def dispatch(self, action: Any) -> None:
        self.sent.append(action)


def _brain() -> tuple[fb.FernhollowBrain, _Screen]:
    brain = fb.FernhollowBrain(client=ScriptedGemini({}))  # pyright: ignore[reportArgumentType]
    screen = _Screen()
    brain._session = cast(Session, screen)  # pyright: ignore[reportPrivateUsage]
    return brain, screen


def _calls(brain: fb.FernhollowBrain) -> list[tuple[str, Any]]:
    chairs = CATALOG.by_category["office-chairs"]
    return [
        ("update_brief", fb.BriefUpdate(room="home-office")),
        (
            "update_brief",
            fb.BriefUpdate(materials=["wood"], styles=["modern"], uses=["all day"], budget=2500),
        ),
        ("build_room", fb.BuildRoom()),
        ("swap_piece", fb.SwapRequest(slot="lamp")),
        ("compare", fb.CompareRequest(products=["chair", chairs[4]])),
        ("edit_compare", fb.EditCompare(add=[chairs[5]])),
        ("more_like", fb.MoreLikeRequest(anchor="desk", change="cheaper")),
        ("more_like", fb.MoreLikeRequest(anchor="desk", change="material", value="walnut")),
        ("goes_with", fb.GoesWithRequest(anchor="desk", category="artwork")),
        ("goes_with", fb.GoesWithRequest(anchor="desk")),
        ("stretch_budget", fb.StretchRequest()),
        ("set_filters", fb.FilterRequest(room="living", colours=["neutral"], styles=["scandi"])),
        ("remove_filter", fb.RemoveFilterRequest(key="colours")),
        ("undo", None),
        ("show", fb.ShowRequest(product="desk", option="Walnut")),
        ("show", fb.ShowRequest(query="oak shelf")),
        ("show", fb.ShowRequest(page="journal")),
        ("shortlist", fb.ShortlistRequest(add=["this"])),
        ("add_to_cart", fb.AddToCartRequest(what="room")),
        ("suggest_finish", None),
        ("store_policy", fb.PolicyRequest(topic="delivery")),
        ("find_order", fb.OrderRequest(order_number="fh 20418")),
        ("start_return", fb.OrderRequest(order_number="FH-20418")),
        ("check_exchange", fb.ExchangeRequest(product="desk chair")),
    ]


def test_every_tool_answers_inside_ten_milliseconds() -> None:
    """Each tool, run cold (no look-ahead cache), on the storyline's state."""
    brain, screen = _brain()
    took: dict[str, float] = {}

    async def run() -> None:
        for name, arg in _calls(brain):
            if name == "suggest_finish":
                # the cart is filled by the shopper's tap; fold it in as the page would
                assert brain.pending is not None
                brain._commit_cart()  # pyright: ignore[reportPrivateUsage]
            fn = getattr(brain, name)
            start = time.perf_counter()
            result = await (fn() if arg is None else fn(arg))
            ms = (time.perf_counter() - start) * 1000
            took[name] = max(took.get(name, 0.0), ms)
            assert isinstance(result, str) and not result.startswith("NOT DONE"), (name, result)

    asyncio.run(run())
    assert set(took) == {t.__name__ for t in brain.tools}
    slow = {k: round(v, 2) for k, v in took.items() if v >= 10}
    assert not slow, f"over 10 ms: {slow}"
    assert screen.sent, "nothing reached the screen"


def test_look_ahead_makes_the_next_answer_a_cache_hit() -> None:
    brain, _ = _brain()

    async def run() -> None:
        await brain.update_brief(
            fb.BriefUpdate(
                room="home-office",
                materials=["wood"],
                styles=["modern"],
                uses=["all day"],
                budget=2500,
            )
        )
        await brain.build_room(fb.BuildRoom())
        brain.look_ahead()
        before = brain.hits
        await brain.more_like(fb.MoreLikeRequest(anchor="desk", change="cheaper"))
        await brain.stretch_budget(fb.StretchRequest())
        assert brain.hits == before + 2

    asyncio.run(run())


@pytest.mark.parametrize("room", ["living", "dining", "bedroom", "bath", "kitchen", "decor"])
def test_every_room_recipe_builds_inside_budget(room: str) -> None:
    brief = eng.Brief(room=room, budget=3000)
    start = time.perf_counter()
    result = eng.build_room(brief)
    assert (time.perf_counter() - start) * 1000 < 10
    assert isinstance(result, eng.RoomSet), result
    assert result.total <= 3000


# ─── Fixed expectations (read off the engines once; see the module docstring) ─

EXPECTED_WOOD_DESKS_UNDER_500 = [
    "compact-laptop-desk-with-integrated-shelf",
    "children-s-space-saving-wooden-desk",
    "foldable-desk-in-engineered-wood",
    "children-s-birch-writing-desk-with-gold-accents",
    "minimalist-wooden-desk",
    "ash-maple-compact-desk",
]
EXPECTED_FIRST_TASTE_QUESTION = ("colours", ("neutral", "taupe", "brown"))
EXPECTED_LEFT_WOOD_MODERN = 8  # was 9 with a glass carafe misfiled under Table Lamps
EXPECTED_ROOM = [
    ("desk", "modular-oak-desk-with-matte-metal-legs"),
    ("chair", "adjustable-golden-oak-task-chair"),
    ("lamp", "walnut-wood-floor-lamp"),
    ("shelving", "compact-laminated-wood-shelf"),
    ("rug", "misted-linen-area-rug"),
]
EXPECTED_ROOM_TOTAL = 1704.99
EXPECTED_ROOM_REASONS = [
    "Oak, as you asked",
    "Adjustable, for long hours",
    "Walnut, as you asked",
    "Wood, as you asked",
    "Neutral, like the shelving",
]
EXPECTED_OFFICE_FLOOR = 412.0
EXPECTED_SWAPPED_LAMP = "birch-wood-table-lamp"
EXPECTED_ART = [
    ("silence-driftwood-light-oak-frame", "Shares the oak"),
    ("canvas-artwork-with-pewter-horizon", "Same modern feel"),
    ("archival-canvas-artwork-with-brushed-bronze-frame", "Picked to sit with the desk"),
    ("ceramic-sculpture-with-matte-glaze", "Picked to sit with the desk"),
]
EXPECTED_CHEAPER_DESKS = [
    "minimalist-wooden-desk",
    "children-s-birch-writing-desk-with-gold-accents",
    "foldable-desk-in-engineered-wood",
    "ash-maple-compact-desk",
]
EXPECTED_COMPARE_ORDER = [
    "brushed-steel-ergonomic-chair-with-lumbar-support",
    "height-adjustable-teen-office-chair",
    "ergonomic-leather-office-chair",
]
EXPECTED_COMPARE_SUMMARY = "Brushed Steel Ergonomic Chair With Lumbar Support is built more for long hours; Height-adjustable teen office chair costs less."
EXPECTED_STRETCH_SWAPS = [
    ("desk", "modular-oak-desk-with-matte-metal-legs", "minimalist-wooden-desk")
]
EXPECTED_SAVED = 339.01
EXPECTED_MOVED_TO = None
