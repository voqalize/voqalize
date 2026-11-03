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


# ─── Which product is meant ───────────────────────────────────────────────────


def _oak_grid() -> tuple[list[str], list[Any]]:
    from voqalize_demos._loaded.fernhollow import resolve as rs

    sofas = [p for p in CATALOG.by_category["sofas"] if "oak" in p]
    return sofas, [rs.Layout(p, i // 3, i % 3) for i, p in enumerate(sofas)]


def test_thresholds_are_the_pinned_ones() -> None:
    from voqalize_demos._loaded.fernhollow import resolve as rs

    assert (rs.MIN_SCORE, rs.CLEAR_MARGIN, rs.ELSEWHERE_MARGIN, rs.POINTING_S) == (
        0.45,
        0.08,
        0.15,
        5.0,
    )


@pytest.mark.parametrize(
    ("spoken", "kind", "expected"),
    [
        # garbled, and two look-alikes on screen fit it: ask
        (
            "the moduler oak sofa with deep seat",
            "choose",
            ("modular-oak-sofa-with-deep-seating", "modular-oak-sofa-with-deep-seats"),
        ),
        # one clearly meant, by name or by place: no question
        ("the oak sectional", "one", "modular-oak-sectional-sofa"),
        ("kanso sofa", "one", "kanso-modular-oak-sofa"),
        ("modular oak sofa with linen", "one", "modular-oak-sofa-with-linen"),
        ("the second one", "one", "oak-modular-sofa-with-removable-covers"),
        ("the top left one", "one", "kanso-modular-oak-sofa"),
        ("the bottom right one", "one", "modular-oak-sectional-sofa"),
        ("number two", "one", "oak-modular-sofa-with-removable-covers"),
        # said of something that is not on screen: the catalog's, not a near miss
        ("cream linen sofa", "one", "cream-linen-sofa"),
        ("bowclay loveseat", "one", "honey-oat-boucle-loveseat"),
        (
            "teak modular sofa",
            "choose",
            ("teak-modular-sofa-with-deep-cushions", "teak-modular-sofa-with-olive-green-cushions"),
        ),
        # too little said to offer anything
        ("the walnut one", "none", None),
        ("the ninth one", "none", None),
    ],
)
def test_references_on_a_sofa_listing(spoken: str, kind: str, expected: Any) -> None:
    from voqalize_demos._loaded.fernhollow import resolve as rs

    sofas, grid = _oak_grid()
    start = time.perf_counter()
    r = rs.resolve(spoken, visible=sofas, layout=grid)
    assert (time.perf_counter() - start) * 1000 < 10
    assert r.kind == kind, (spoken, r)
    if kind == "one":
        assert r.product_id == expected
    elif kind == "choose":
        assert r.candidates == expected
        assert r.question.startswith("Which one: one, ")


def test_choices_then_pointing() -> None:
    from voqalize_demos._loaded.fernhollow import resolve as rs

    sofas, grid = _oak_grid()
    deep = ("modular-oak-sofa-with-deep-seating", "modular-oak-sofa-with-deep-seats")
    asked = rs.resolve("the moduler oak sofa with deep seat", visible=sofas, layout=grid)
    assert asked.question == (
        "Which one: one, the one on the top right at $2,950, or two, the one in the middle at $3,290?"
    )
    for answer, pid in (("the second one", deep[1]), ("two", deep[1]), ("the first", deep[0])):
        r = rs.resolve(answer, choices=deep, visible=sofas, layout=grid)
        assert (r.kind, r.product_id, r.source) == ("one", pid, "choices")
    fresh = rs.resolve("this one", pointing=sofas[3], pointing_age_s=2.0, visible=sofas)
    assert (fresh.kind, fresh.product_id) == ("one", sofas[3])
    stale = rs.resolve("this one", pointing=sofas[3], pointing_age_s=8.0, open_product=sofas[5])
    assert stale.product_id == sofas[5]


def test_the_circled_selection_outranks_pointing() -> None:
    from voqalize_demos._loaded.fernhollow import resolve as rs

    sofas, grid = _oak_grid()
    picked = sofas[:3]
    many = rs.resolve(
        "these", selection=picked, pointing=sofas[5], pointing_age_s=1.0, visible=sofas
    )
    assert (many.kind, many.candidates, many.source) == ("many", tuple(picked), "selection")
    for said in ("those", "all of them", "the circled ones", "both"):
        assert rs.resolve(said, selection=picked).kind == "many", said
    one = rs.resolve("this one", selection=picked[:1], open_product=sofas[4])
    assert (one.kind, one.product_id) == ("one", picked[0])
    # what they circled comes before what they point at (CONTRACT v4 findings, a)
    circled = rs.resolve("this one", selection=picked[:1], pointing=sofas[5], pointing_age_s=1.0)
    assert circled.product_id == picked[0]
    pointed = rs.resolve("this one", pointing=sofas[5], pointing_age_s=1.0, open_product=sofas[4])
    assert pointed.product_id == sofas[5]
    several = rs.resolve("this", selection=picked)
    assert (several.kind, several.candidates) == ("choose", tuple(picked))
    assert rs.resolve("these", visible=sofas, layout=grid).kind != "many"


def test_checkout_checks_and_spells_back() -> None:
    from voqalize_demos._loaded.fernhollow import checkout as co

    assert co.check("email", "Sam dot Rivera at Example dot com") == (
        "sam.rivera@example.com",
        None,
    )
    assert co.check("email", "sam at example")[1] is not None
    assert co.spell_back("email", "sam.rivera@example.com") == (
        "s a m dot r i v e r a, at example dot com"
    )
    assert co.check("postcode", " sw1a 1aa ") == ("SW1A 1AA", None)
    assert co.spell_back("postcode", "SW1A 1AA") == "S W 1 A 1 A A"
    assert (co.delivery_fee(499.99), co.delivery_fee(500), co.delivery_fee(500.01)) == (49, 49, 0)


# ─── Every tool under 10 ms ───────────────────────────────────────────────────


class _Screen:
    def __init__(self) -> None:
        self.sent: list[Any] = []

    def dispatch(self, action: Any) -> None:
        self.sent.append(action)

    async def configure(self, config: Any) -> None:
        self.sent.append(config)


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
        ("remove_pieces", fb.RemoveRequest(pieces=["rug"])),
        ("piece_options", fb.PieceOptionsRequest(slot="desk", want=["oak"])),
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
        ("resolve_product", fb.ResolveRequest(spoken="the moduler oak sofa with deep seat")),
        ("resolve_product", fb.ResolveRequest(spoken="cream linen sofa")),
        (
            "fill_checkout",
            fb.CheckoutFields(
                first_name="Sam",
                last_name="Rivera",
                address1="12 Elm Street",
                city="Portland",
                postcode="97201",
                country="United States",
            ),
        ),
        ("checkout_step", fb.CheckoutStepRequest(step="review")),
        ("place_order", fb.PlaceOrderRequest()),
        ("submit_return", fb.SubmitReturnRequest()),
        ("clear_selection", None),
        (
            "prepare_return",
            fb.PrepareReturn(
                order_number="FH-20418",
                items=[fb.ReturnItem(product_id="desk-chair-with-aluminum-frame", qty=1)],
                reason="doesnt_suit_room",
                condition="unused_in_packaging",
                resolution="refund",
                collection="pickup",
                pickup_window="weekday_morning",
            ),
        ),
    ]


def test_every_tool_answers_inside_ten_milliseconds() -> None:
    """Each tool, run cold (no look-ahead cache), on the storyline's state."""
    brain, screen = _brain()
    took: dict[str, float] = {}

    async def run() -> None:
        for name, arg in _calls(brain):
            if name == "fill_checkout":
                # the shopper types their own email, as the page reports it
                brain.checkout_filled.add("email")
            fn = getattr(brain, name)
            start = time.perf_counter()
            result = await (fn() if arg is None else fn(arg))
            ms = (time.perf_counter() - start) * 1000
            took[name] = max(took.get(name, 0.0), ms)
            # submit_return needs the page's returns.submit move; until the
            # scene declares it, the tool says so honestly.
            needs = {"submit_return": "returns.submit", "prepare_return": "returns.next_step"}
            honest = name in needs and brain.stage.moves.get(needs[name]) is None
            assert isinstance(result, str) and (honest or not result.startswith("NOT DONE")), (
                name,
                result,
            )

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


# ─── Model ────────────────────────────────────────────────────────────────────


def test_emily_runs_on_gemini_36_flash_at_low_thinking() -> None:
    from fernhollow.backend.brain import MODEL, THINKING, FernhollowBrain
    from google.genai import types
    from voqalize_demos.testing import ScriptedGemini

    brain = FernhollowBrain(client=ScriptedGemini([]))  # pyright: ignore[reportArgumentType]
    assert MODEL == "gemini-3.6-flash"
    assert brain._config.thinking_config is THINKING  # pyright: ignore[reportPrivateUsage]
    assert THINKING.thinking_level == types.ThinkingLevel.LOW


# ─── v4: returns that work by voice ───────────────────────────────────────────

CHAIR = "desk-chair-with-aluminum-frame"


def test_the_return_plan_is_one_fixed_sequence() -> None:
    from voqalize_demos._loaded.fernhollow import returns as rt

    order = rt.find_order("FH-20418")
    assert order is not None
    plan = rt.plan_return(
        order,
        [(CHAIR, 1)],
        reason="doesnt_suit_room",
        condition="unused_in_packaging",
        resolution="refund",
        collection="pickup",
        pickup_window="weekday_morning",
    )
    assert plan == [
        (
            "returns.find",
            {"order_number": "FH-20418", "email": "sam.rivera@example.com"},
            "1 find your order",
        ),
        ("returns.select_item", {"product_id": CHAIR, "qty": 1}, "2 items"),
        ("returns.next_step", {}, "2 items"),
        ("returns.fill", {"field": "reason", "value": "doesnt_suit_room"}, "3 reason"),
        ("returns.fill", {"field": "condition", "value": "unused_in_packaging"}, "3 reason"),
        ("returns.next_step", {}, "3 reason"),
        ("returns.fill", {"field": "resolution", "value": "refund"}, "4 resolution"),
        ("returns.next_step", {}, "4 resolution"),
        ("returns.fill", {"field": "collection", "value": "pickup"}, "5 collection"),
        ("returns.fill", {"field": "pickup_window", "value": "weekday_morning"}, "5 collection"),
        ("returns.next_step", {}, "5 collection"),
    ]
    assert isinstance(plan[1][1]["qty"], int)  # the number, never the string "1"


@pytest.mark.parametrize(
    ("kwargs", "why"),
    [
        ({"items": [(CHAIR, 2)]}, "between 1 and 1"),
        ({"items": [("oak-desk", 1)]}, "not on order"),
        ({"pickup_window": None}, "a pickup needs a window"),
        ({"resolution": "exchange"}, "exchange needs one of the item's other option values"),
        ({"reason": "broken"}, "reason must be one of"),
    ],
)
def test_the_return_plan_refuses_what_the_page_would(kwargs: dict[str, Any], why: str) -> None:
    from voqalize_demos._loaded.fernhollow import returns as rt

    order = rt.find_order("FH-20418")
    assert order is not None
    answers: dict[str, Any] = {
        "items": [(CHAIR, 1)],
        "reason": "doesnt_suit_room",
        "condition": "unused_in_packaging",
        "resolution": "refund",
        "collection": "pickup",
        "pickup_window": "weekday_morning",
    }
    answers.update(kwargs)
    items = answers.pop("items")
    result = rt.plan_return(order, items, **answers)
    assert isinstance(result, str) and why in result, result
    late = rt.find_order("FH-20155")
    assert late is not None
    refused = rt.plan_return(
        late, [(late.lines[0].product_id, 1)], **{**answers, "pickup_window": "saturday"}
    )
    assert refused == "Aged Ash Side Chair cannot be returned (outside window)"


def test_find_order_reads_placed_then_known_then_demo() -> None:
    from voqalize_demos._loaded.fernhollow import returns as rt

    mine = rt.order_from(
        {
            "number": "FH-30001",
            "email": "a@example.com",
            "status": "delivered",
            "delivered_days_ago": 0,
            "lines": [{"product_id": CHAIR, "qty": 1}],
            "total": 289,
        },
        "placed",
    )
    page = rt.order_from(
        {
            "number": "FH-879106",
            "email": "b@example.com",
            "status": "delivered",
            "placed_days_ago": 1,
            "delivered_days_ago": 1,
            "lines": [{"product_id": CHAIR, "qty": 1}],
            "total": 289,
        },
        "known",
    )
    assert rt.find_order("the order I just placed", placed=[mine], known=[page]) is mine
    assert rt.find_order("my last order", known=[page]) is page
    assert rt.find_order("FH 879106", placed=[mine], known=[page]) is page
    found = rt.find_order("FH-20418", placed=[mine], known=[page])
    assert found is not None and found.source == "demo"
    assert mine.lines[0].status == "eligible" and mine.lines[0].days_left == 30


def _v4_brain() -> tuple[fb.FernhollowBrain, _Screen]:
    from voqalize_demos._loaded.fernhollow.stage_gen import MOVES

    from voqalize.sdk.stage import Move, MoveClass, MoveSet, Stage

    brain, screen = _brain()
    extra = [
        Move(id=i, verb=None, cls=MoveClass.REVERSIBLE, args=a)
        for i, a in (("returns.find", ("order_number", "email")), ("returns.next_step", ()))
        if MOVES.get(i) is None
    ]
    brain.stage = Stage(dispatch=screen.dispatch, moves=MoveSet([*MOVES, *extra]))
    return brain, screen


def _moves(screen: _Screen) -> list[tuple[str, dict[str, Any]]]:
    return [(a.move, dict(a.args)) for a in screen.sent if type(a).__name__ == "StageMove"]


async def test_prepare_return_sends_the_sequence_and_tells_a_refusal_exactly() -> None:
    from voqalize.sdk.stage.wire import Refusal, StageResult

    brain, screen = _v4_brain()
    request = fb.PrepareReturn(
        order_number="FH-20418",
        items=[fb.ReturnItem(product_id=CHAIR, qty=1)],
        reason="doesnt_suit_room",
        condition="unused_in_packaging",
        resolution="refund",
        collection="drop_off",
    )
    result = await brain.prepare_return(request)
    assert "being filled" in result and "sam" not in result.lower()
    sent = _moves(screen)
    assert [m for m, _ in sent] == [
        "returns.find",
        "returns.select_item",
        "returns.next_step",
        "returns.fill",
        "returns.fill",
        "returns.next_step",
        "returns.fill",
        "returns.next_step",
        "returns.fill",
        "returns.next_step",
    ]
    assert sent[0][1] == {"order_number": "FH-20418", "email": "sam.rivera@example.com"}
    refs = [a.call_ref for a in screen.sent if type(a).__name__ == "StageMove"]
    assert (
        brain._staged(StageResult(call_ref=refs[0], move="returns.find", outcome="applied")) is None
    )  # pyright: ignore[reportPrivateUsage]
    note = brain._staged(  # pyright: ignore[reportPrivateUsage]
        StageResult(
            call_ref=refs[2],
            move="returns.next_step",
            outcome="refused",
            detail="step 2 needs an item",
            refused=[Refusal(arg="items", why="choose at least one item")],
        )
    )
    assert note is not None
    assert (
        "stopped at step 2 items" in note
        and "step 2 needs an item" in note
        and "choose at least one item" in note
    )
    # The run is over: later answers from it say nothing more.
    assert (
        brain._staged(StageResult(call_ref=refs[3], move="returns.fill", outcome="applied")) is None
    )  # pyright: ignore[reportPrivateUsage]


async def test_prepare_return_reaching_review_is_said() -> None:
    from voqalize.sdk.stage.wire import StageResult

    brain, screen = _v4_brain()
    (
        await brain.prepare_return(
            fb.PrepareReturn(
                order_number="FH-20418",
                items=[fb.ReturnItem(product_id=CHAIR)],
                reason="changed_mind",
                condition="unused_unpacked",
                resolution="store_credit",
                collection="drop_off",
            )
        )
    )
    notes = [
        brain._staged(StageResult(call_ref=a.call_ref, move=a.move, outcome="applied"))  # pyright: ignore[reportPrivateUsage]
        for a in screen.sent
        if type(a).__name__ == "StageMove"
    ]
    assert [n for n in notes if n] == [
        "[The returns form reached the review step. Nothing is submitted until the shopper says yes.]"
    ]


# ─── Confirmations: one mechanism for every confirmed act ─────────────────────


def test_the_yes_classifier() -> None:
    from voqalize_demos._loaded.fernhollow.confirm import classify

    for said in (
        "Yes, please.",
        "yeah",
        "Go ahead.",
        "Place it.",
        "Yep, do it",
        "Can you please submit it?",
        "Go ahead and submit it.",
        "Sure",
        "OK",
    ):
        assert classify(said) == "yes", said
    for said in ("No, wait.", "Not yet.", "Cancel that", "Hold on"):
        assert classify(said) == "no", said
    for said in ("Yes but change the address", "What's the total?", "Hmm"):
        assert classify(said) is None, said


def test_a_new_confirmed_act_needs_no_new_yes_code() -> None:
    from voqalize_demos._loaded.fernhollow.confirm import Acted, Confirmations

    done: list[str] = []
    c = Confirmations()
    c.register(
        "water_plants",
        lambda p: (done.append(p.label), Acted("Watering them now.", "[watered]"))[1],
    )
    assert c.ask("water_plants", ("water_plants", "fern"), "Water the fern", 1) is None
    assert c.due(1) is None, "a yes on the asking turn is not an answer"
    pending = c.due(2)
    assert pending is not None
    assert c.act(pending).line == "Watering them now."
    assert c.act(pending).line.startswith("That's already done"), "acted twice"
    assert done == ["Water the fern"]
    assert c.ask("water_plants", ("water_plants", "fern"), "Water the fern", 3) is not None


@pytest.mark.parametrize(
    ("outcome", "detail", "line"),
    [
        (
            "applied",
            "return submitted, reference RT-9-1",
            "Done — your return is in, reference RT-9-1. We'll be in touch about the drop-off.",
        ),
        (
            "refused",
            "step 1: Enter the email",
            "That didn't go through — the page says: step 1: Enter the email.",
        ),
        ("failed", None, "That didn't go through — the page says: failed."),
        (
            "unknown",
            None,
            "I can't confirm that went through — the page didn't answer. Please check it on screen.",
        ),
    ],
)
async def test_a_page_answered_act_says_its_outcome_once(
    outcome: str, detail: str | None, line: str
) -> None:
    from voqalize.sdk.stage.wire import StageResult

    brain, screen = _v4_brain()
    await brain.prepare_return(
        fb.PrepareReturn(
            order_number="FH-20418",
            items=[fb.ReturnItem(product_id=CHAIR)],
            reason="changed_mind",
            condition="unused_unpacked",
            resolution="refund",
            collection="drop_off",
        )
    )
    brain._say_next = None  # pyright: ignore[reportPrivateUsage]
    brain.turns += 1
    pending = brain.confirms.due(brain.turns)
    assert pending is not None and pending.kind == "submit_return"
    acted = brain.confirms.act(pending)
    assert acted.line == "Submitting it now." and acted.ref is not None
    brain._staged(
        StageResult(call_ref=acted.ref, move="returns.submit", outcome=outcome, detail=detail)
    )  # pyright: ignore[reportPrivateUsage]
    say = brain._say_next  # pyright: ignore[reportPrivateUsage]
    assert say is not None and say() == line
    assert [a.move for a in screen.sent if type(a).__name__ == "StageMove"].count(
        "returns.submit"
    ) == 1
