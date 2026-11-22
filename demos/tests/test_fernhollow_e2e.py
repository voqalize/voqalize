"""Fernhollow — Emily, the design adviser — end to end over the wire, no network,
no LLM key.

The real ``FernhollowBrain`` (its prompt, tools, precomputed indexes and the
authored policies) on a real ``brain_server`` socket, driven by the
conformance ``VoqalizeDriver``, with only the *model* scripted. The script walks
the demo storyline: the brief → a room set → swap the lamp (and a barge-in
that lands before the swap, which must leave the board as it was) → compare
chairs → a cheaper desk that looks alike → art that goes with the desk →
stretch the budget → add the room to the cart, confirmed → a finishing touch.

The ids the script passes and the payloads it asserts are computed from the
same engines the brain runs (``engine.py``), so the test pins the *wiring* —
what reaches the screen, in which order, and what the model reads back — while
``test_fernhollow_engine.py`` pins the engines' own outputs.

Run: ``cd demos && uv run pytest tests/test_fernhollow_e2e.py``
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import pytest
from google.genai import types
from voqalize_demos.discovery import discover
from voqalize_demos.testing import Reply, ScriptedGemini, call, reply, reply_and_call

from voqalize.sdk.gemini import _needs_result_now

from ._harness import DemoRig, check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.fernhollow import engine as eng  # noqa: E402
from voqalize_demos._loaded.fernhollow.brain import FernhollowBrain  # noqa: E402
from voqalize_demos._loaded.fernhollow.catalog import CATALOG, money  # noqa: E402
from voqalize_demos._loaded.fernhollow.persona import PERSONA  # noqa: E402
from voqalize_demos._loaded.fernhollow.policies import policy_numbers  # noqa: E402
from voqalize_demos._loaded.fernhollow.prompt import GREETING, GREETINGS  # noqa: E402

# The character lives in persona.json; the test reads it like the brain does.
LANGUAGE = PERSONA.default_language
VOICE = PERSONA.voice(LANGUAGE)

# ── The storyline's brief, and what the engines make of it ───────────────────

BRIEF = eng.Brief(
    room="home-office",
    uses=("long hours",),
    materials=eng.map_terms("materials", ["wood"]).words,
    styles=("modern",),
    budget=2500.0,
)
ROOM = eng.build_room(BRIEF)
assert isinstance(ROOM, eng.RoomSet)
DESK = ROOM.piece("desk")
CHAIR = ROOM.piece("chair")
LAMP = ROOM.piece("lamp")
assert DESK is not None and CHAIR is not None and LAMP is not None
NEW_LAMP = eng.swap_piece(ROOM, BRIEF, "lamp", seen=[LAMP.product_id])
assert isinstance(NEW_LAMP, eng.Piece)
ROOM_2 = ROOM.with_piece(NEW_LAMP)
OTHER_CHAIR = CATALOG.similar[CHAIR.product_id][0][0]
CHEAPER_DESKS, _ = eng.more_like(DESK.product_id, "cheaper")
ART = eng.goes_with(
    DESK.product_id, category="artwork", exclude=tuple(p.product_id for p in ROOM_2.pieces)
)
STRETCH = eng.stretch_budget(ROOM_2, BRIEF)


def _results(contents: list[types.Content]) -> dict[str, str]:
    """Every tool result one request carried, by tool name."""
    return {
        p.function_response.name or "": str((p.function_response.response or {})["result"])
        for c in contents
        for p in (c.parts or [])
        if p.function_response is not None
    }


def _all_results(llm: ScriptedGemini) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for contents in llm.captured_contents:
        for c in contents:
            for p in c.parts or []:
                fr = p.function_response
                if fr is not None and fr.id not in seen:
                    seen.add(fr.id or str(len(seen)))
                    out.append(str((fr.response or {}).get("result") or fr.response))
    return out


def _story() -> ScriptedGemini:
    return ScriptedGemini(
        {
            "I'm setting up a home office.": [
                reply_and_call(
                    "A home office — lovely.", "update_brief", update={"room": "home-office"}
                ),
                reply("What feel are you after?"),
            ],
            "Warm wood, modern, and I'm at the desk all day. About twenty-five hundred.": [
                reply_and_call(
                    "Wood and modern, for long days.",
                    "update_brief",
                    update={
                        "materials": ["wood"],
                        "styles": ["modern"],
                        "uses": ["all day at the desk"],
                        "budget": 2500,
                    },
                ),
                reply("That's enough to design with. Shall I put the room together?"),
            ],
            "Yes, put it together.": [
                reply_and_call("A wood-and-modern office, coming up.", "build_room", request={}),
                reply("Here's a wood-and-modern office, with most of the budget on the chair."),
            ],
            # The barge-in: the line streams, the shopper talks over it, and the
            # call never arrives — the board must not move.
            "Hmm, the lamp": Reply(
                chunks=("Another lamp ", "that keeps ", "the wood going ", "with the desk."),
                chunk_delay=0.25,
                calls=(("swap_piece", {"request": {"slot": "lamp"}}),),
            ),
            "A different lamp, please.": [
                reply_and_call("Here's another lamp.", "swap_piece", request={"slot": "lamp"}),
                reply("This one keeps the wood going."),
            ],
            "Compare the chair with something similar.": [
                reply_and_call(
                    "Side by side.",
                    "compare",
                    request={"products": ["chair", OTHER_CHAIR]},
                ),
                reply("The first is built more for long hours."),
            ],
            "Is there a cheaper desk that looks like this one?": [
                reply_and_call(
                    "A few look-alikes for less.",
                    "more_like",
                    request={"anchor": "desk", "change": "cheaper"},
                ),
                reply("The first is the closest look."),
            ],
            "What art would go with the desk?": [
                reply_and_call(
                    "Some art for that wall.",
                    "goes_with",
                    request={"anchor": "desk", "category": "artwork"},
                ),
                reply("The first shares the wood."),
            ],
            "Can we make the budget go further?": [
                reply_and_call("Sale prices first.", "stretch_budget", request={}),
                reply(
                    "The desk has an on-sale look-alike, which saves three hundred thirty-nine dollars."
                ),
            ],
            "Add the whole room to my cart.": reply_and_call(
                "All five, into your cart.",
                "add_to_cart",
                request={"what": "room"},
            ),
            "Anything to finish it off?": [
                reply_and_call("One finishing touch.", "suggest_finish"),
                reply("This would sit well with the desk."),
            ],
        }
    )


async def _drive_story(rig: DemoRig, llm: ScriptedGemini) -> None:
    await rig.driver.start_session()
    for line in (
        "I'm setting up a home office.",
        "Warm wood, modern, and I'm at the desk all day. About twenty-five hundred.",
        "Yes, put it together.",
    ):
        check_turn(rig, await rig.driver.user_says(line), units=2)

    # Barge in while the swap's line is still streaming: no call, no swap.
    cut = await rig.driver.barge_in("Hmm, the lamp", speak_delay=0.05)
    assert cut.interrupted
    assert "swap_piece" not in rig.actions(), "a swap landed from a turn the shopper cut off"
    brain = rig.brain
    assert isinstance(brain, FernhollowBrain)
    assert brain.screen.room is not None
    assert brain.screen.room.piece("lamp") == LAMP, "the board moved under a cut turn"

    for line in (
        "A different lamp, please.",
        "Compare the chair with something similar.",
        "Is there a cheaper desk that looks like this one?",
        "What art would go with the desk?",
        "Can we make the budget go further?",
    ):
        check_turn(rig, await rig.driver.user_says(line), units=2)

    # Added at once: no confirmation to answer.
    check_turn(rig, await rig.driver.user_says("Add the whole room to my cart."), units=1)
    check_turn(rig, await rig.driver.user_says("Anything to finish it off?"), units=2)


async def test_greeting_and_voice_reach_the_wire() -> None:
    """Emily greets with the fixed line, and Emily in English lands on both legs
    before the greeting audio."""
    async with demo("fernhollow", _story()) as rig:
        greeting = await rig.driver.start_session()
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text == GREETING
        check_voice_pair(rig, voice=VOICE, language=LANGUAGE)


async def test_the_storyline_drives_the_screen() -> None:
    """The whole demo, and the exact ``ui-command`` payloads the store reads."""
    llm = _story()
    async with demo("fernhollow", llm) as rig:
        await _drive_story(rig, llm)
        actions = rig.actions()
        # Once a taste is in the brief, the grid follows it before the room is built.
        assert actions[:5] == [
            "update_brief",
            "navigate",
            "update_brief",
            "apply_filters",
            "show_room_set",
        ], actions
        assert actions[5:] == [
            "swap_piece",
            "show_compare",
            "show_more_like",
            "show_goes_with",
            *(["swap_piece"] * (len(STRETCH.swaps) + (1 if STRETCH.upgrade else 0))),
            "show_savings",
            "cart_updated",
            "suggest_finish",
        ], actions

        brief = rig.command("update_brief")
        assert brief["brief"]["room"] == "home-office"
        assert brief["products_left"] == len(eng.products_left(eng.Brief(room="home-office")))

        board = rig.command("show_room_set")
        assert board["room"] == "home-office" and board["budget"] == 2500
        assert [p["product_id"] for p in board["pieces"]] == [p.product_id for p in ROOM.pieces]
        assert board["total"] == ROOM.total <= 2500
        for tile in board["pieces"]:
            product = CATALOG.products[tile["product_id"]]
            assert tile["title"] == product.title and tile["price"] == product.price
            assert tile["image"] == product.image and tile["reason"]

        swap = rig.command("swap_piece")
        assert swap["slot"] == "lamp" and swap["old_product_id"] == LAMP.product_id
        assert swap["piece"]["product_id"] == NEW_LAMP.product_id
        assert swap["total"] == ROOM_2.total

        compare = rig.command("show_compare")
        assert set(compare["product_ids"]) == {CHAIR.product_id, OTHER_CHAIR}
        assert compare["rows"][0]["label"] == "Price"

        more = rig.command("show_more_like")
        assert more["anchor_id"] == DESK.product_id
        assert [i["product_id"] for i in more["items"]] == [i.product_id for i in CHEAPER_DESKS]
        for item in more["items"]:
            assert CATALOG.products[item["product_id"]].price < DESK.product.price

        art = rig.command("show_goes_with")
        assert art["anchor_id"] == DESK.product_id
        assert [i["product_id"] for i in art["items"]] == [i.product_id for i in ART]
        assert all(
            CATALOG.products[i["product_id"]].category_slug == "artwork" for i in art["items"]
        )

        savings = rig.command("show_savings")
        assert [s["to_id"] for s in savings["swaps"]] == [s.to_id for s in STRETCH.swaps]
        assert savings["saved"] == STRETCH.saved > 0
        for s in savings["swaps"]:
            assert CATALOG.products[s["to_id"]].on_sale
            assert s["now"] < s["was"]

        cart = rig.command("cart_updated")
        assert [line["product_id"] for line in cart["lines"]] == [
            p.product_id for p in STRETCH.room.pieces
        ]
        assert {line["qty"] for line in cart["lines"]} == {1}
        assert cart["total"] == STRETCH.room.total
        assert {line["product_id"] for line in cart["lines"]} == {
            p.product_id for p in STRETCH.room.pieces
        }

        finish = rig.command("suggest_finish")
        assert finish["product_id"] not in {line["product_id"] for line in cart["lines"]}
        assert finish["reason"]

        # What Emily added reached the model as context, ahead of the next words.
        last = " ".join(
            p.text or "" for c in llm.captured_contents[-2] for p in c.parts or [] if p.text
        )
        assert f"cart (5 items, {money(STRETCH.room.total)}):" in last


async def test_the_model_reads_what_landed() -> None:
    """Each marked tool answers in the same turn: the second request of the
    turn carries the result, in prose, with catalog titles and prices."""
    llm = _story()
    async with demo("fernhollow", llm) as rig:
        await _drive_story(rig, llm)
    results: dict[str, str] = {}
    for contents in llm.captured_contents:
        results.update(_results(contents))
    assert "ask next:" in results["update_brief"]
    assert DESK.product.title in results["build_room"]
    assert "{" not in results["build_room"], "a tool result read as a dict"
    assert "winner" in results["compare"]
    assert "Savings are on the board" in results["stretch_budget"]
    assert "Added to the cart" in results["add_to_cart"]


async def test_every_number_said_comes_from_the_catalog_or_policies() -> None:
    """No invented facts: every figure in every tool result the model read is a
    catalog price or was-price, a policy number, a count of products, or a sum
    of catalog prices the board itself shows (a room total, a saving)."""
    llm = _story()
    async with demo("fernhollow", llm) as rig:
        await _drive_story(rig, llm)
        brain = rig.brain
        assert isinstance(brain, FernhollowBrain)
    allowed: set[float] = set(policy_numbers())
    for p in CATALOG.products.values():
        allowed |= {v.price for v in p.variants}
        allowed |= {v.compare_at for v in p.variants if v.compare_at is not None}
    for room in (ROOM, ROOM_2, STRETCH.room):
        allowed.add(room.total)
    allowed.add(STRETCH.saved)
    allowed.add(2500.0)  # the shopper's own budget
    counts = {float(n) for n in range(len(CATALOG.products) + 1)}
    figures = re.compile(r"\$?\d[\d,]*(?:\.\d+)?")
    said = _all_results(llm)
    assert said
    for text in said:
        # ids are slugs and may carry digits; they are never spoken
        text = re.sub(r"\[id [^\]]+\]", "", text)
        for m in figures.finditer(text):
            raw = m.group(0)
            value = float(raw.lstrip("$").replace(",", ""))
            if raw.startswith("$"):
                assert value in allowed, f"invented figure {raw!r} in: {text}"
            else:
                assert value in counts or value in allowed, f"invented number {raw!r} in: {text}"


async def test_add_to_cart_adds_at_once_and_once_per_turn() -> None:
    """Adding asks nothing (owner, 2026-11-03): the cart shows Emily added it.
    Two calls in one turn — a model repeating itself — still add once, so
    nothing lands twice; a later turn can add more."""
    llm = ScriptedGemini(
        {
            "Build me a home office around two thousand.": [
                Reply(
                    text="A home office around two thousand.",
                    calls=(
                        ("update_brief", {"update": {"room": "home-office", "budget": 2000}}),
                        ("build_room", {"request": {}}),
                    ),
                ),
                reply("Here it is."),
            ],
            "Add it all.": Reply(
                text="Adding all five.",
                calls=(
                    ("add_to_cart", {"request": {"what": "room"}}),
                    ("add_to_cart", {"request": {"what": "room"}}),
                ),
            ),
            "And the chair once more.": reply_and_call(
                "Another chair, added.", "add_to_cart", request={"product": "chair"}
            ),
        }
    )
    async with demo("fernhollow", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Build me a home office around two thousand.")
        await rig.driver.user_says("Add it all.")
        assert "confirm_add" not in rig.actions(), "asked before adding"
        assert rig.actions().count("cart_updated") == 1, "the repeat call added twice"
        brain = rig.brain
        assert isinstance(brain, FernhollowBrain)
        assert len(brain.cart) == 5 and set(brain.cart.values()) == {1}
        await rig.driver.user_says("And the chair once more.")
        assert rig.actions().count("cart_updated") == 2
        assert sorted(brain.cart.values()) == [1, 1, 1, 1, 2]


async def test_options_for_a_piece_are_a_grid_to_pick_from() -> None:
    """ "Show me a couple of other desks" is the desk grid to choose from — not a
    comparison, and not a swap made for them (dev call 551114ff). The one they
    then pick goes on the board."""
    llm = ScriptedGemini(
        {
            "Build me a home office around two thousand.": [
                Reply(
                    text="A home office around two thousand.",
                    calls=(
                        ("update_brief", {"update": {"room": "home-office", "budget": 2000}}),
                        ("build_room", {"request": {}}),
                    ),
                ),
                reply("Here it is."),
            ],
            "Show me a couple of other desks, in oak.": [
                reply_and_call(
                    "Here are some other desks.",
                    "piece_options",
                    request={"slot": "desk", "want": ["oak"]},
                ),
                reply("Which one?"),
            ],
            "The second one.": [
                reply_and_call(
                    "Putting it on the board.",
                    "swap_piece",
                    request={"slot": "desk", "product": "2"},
                ),
                reply("Done."),
            ],
        }
    )
    async with demo("fernhollow", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Build me a home office around two thousand.")
        await rig.driver.user_says("Show me a couple of other desks, in oak.")
        grid = rig.command("apply_filters")
        assert grid["filters"]["category"] == "desks"
        assert grid["count"] > 1
        assert "show_compare" not in rig.actions() and "swap_piece" not in rig.actions()
        listed = _results(llm.captured_contents[-1])["piece_options"]
        assert "1. " in listed and "2. " in listed
        await rig.driver.user_says("The second one.")
        brain = rig.brain
        assert isinstance(brain, FernhollowBrain)
        assert brain.screen.room is not None
        desk = brain.screen.room.piece("desk")
        assert desk is not None and desk.product_id == grid["product_ids"][1]


async def test_checkout_tells_what_to_type_sees_it_and_moves_on() -> None:
    """Opening checkout says, in the same turn, that the shopper types their
    email and phone (dev call 551114ff: the page opened and Emily went quiet).
    Half an email is not filled; a whole one completes the contact step, and
    "done" moves on. A complete address is not read back: Emily says it is
    on screen to check and the shopper clicks Review order (owner, 2026-11-03)."""
    llm = ScriptedGemini(
        {
            "Let's check out.": [
                reply_and_call("Here's checkout.", "checkout_step", request={"step": "contact"}),
                reply("Type your email and phone in yourself, and tell me when you're done."),
            ],
            "Done, I've typed it.": [
                reply_and_call("On to shipping.", "checkout_step", request={"step": "shipping"}),
                reply("What name and address should it go to?"),
            ],
            "Sam Rivera, 12 Elm Street, Portland, 97201, United States.": [
                reply_and_call(
                    "Filling that in.",
                    "fill_checkout",
                    fields={
                        "first_name": "Sam",
                        "last_name": "Rivera",
                        "address1": "12 Elm Street",
                        "city": "Portland",
                        "postcode": "97201",
                        "country": "United States",
                    },
                ),
                reply(
                    "I've filled in your details on screen — please check them and click Review order."
                ),
            ],
        }
    )
    async with demo("fernhollow", llm) as rig:
        await rig.driver.start_session()
        brain = rig.brain
        assert isinstance(brain, FernhollowBrain)
        await rig.driver.send_ui_event(
            "cart_changed",
            {
                "lines": [{"product_id": CHAIR_ID, "variant_id": CHAIR_VARIANT, "qty": 1}],
                "total": 289.0,
                "by": "visitor",
            },
        )
        await asyncio.sleep(0.1)

        await rig.driver.user_says("Let's check out.")
        opened = _results(llm.captured_contents[-1])["checkout_step"]
        assert "email (the shopper types it themselves" in opened, "said a turn late"

        # Half an email, then the whole one: only the whole one counts.
        await rig.driver.send_ui_event(
            "checkout_changed", {"field": "email", "complete": False, "by": "visitor"}
        )
        await asyncio.sleep(0.1)
        assert "email" not in brain.checkout_filled
        await rig.driver.send_ui_event(
            "checkout_changed", {"field": "email", "complete": True, "by": "visitor"}
        )
        await asyncio.sleep(0.1)
        assert "email" in brain.checkout_filled

        await rig.driver.user_says("Done, I've typed it.")
        heard = " ".join(
            p.text or "" for c in llm.captured_contents[-2] for p in c.parts or [] if p.text
        )
        assert "contact step is complete" in heard
        steps = [
            c["payload"]["step"]
            for c in rig.driver.ui_commands
            if c.get("command") == "checkout_step"
        ]
        assert steps == ["contact", "shipping"]

        await rig.driver.user_says("Sam Rivera, 12 Elm Street, Portland, 97201, United States.")
        steps = [
            c["payload"]["step"]
            for c in rig.driver.ui_commands
            if c.get("command") == "checkout_step"
        ]
        assert steps == ["contact", "shipping"], "moved past the address for the shopper"
        filled = _results(llm.captured_contents[-1])["fill_checkout"]
        assert "please check them and click Review order" in filled
        # Nothing they said is handed back to be read aloud.
        assert "Elm" not in filled and "9 7 2 0 1" not in filled

        # The shopper clicks Review order; the page says where it is.
        await rig.driver.send_ui_event("checkout_step_reached", {"step": "review", "by": "visitor"})
        await asyncio.sleep(0.1)
        assert brain.checkout_step_now == "review"


async def test_a_tool_name_is_never_spoken() -> None:
    """Prod call 4a18177e: "update_brief helps set up the brief for your
    space" was said aloud. A tool's name is taken out of speech."""
    llm = ScriptedGemini(
        {
            "A home office please.": [
                reply_and_call(
                    "I can help with your home office. update_brief helps set up the brief.",
                    "update_brief",
                    update={"room": "home-office"},
                ),
                reply("Shall I show you desks, or compare two chairs?"),
            ],
        }
    )
    async with demo("fernhollow", llm) as rig:
        await rig.driver.start_session()
        turn = await rig.driver.user_says("A home office please.")
        said = " ".join(u.text for u in turn.units)
        assert "update_brief" not in said, said
        assert "I can help with your home office." in said
        # A tool named with a plain word (show, compare) is still a word (round 1:
        # "Shall I show you cushions" came out "Shall I you cushions").
        assert "Shall I show you desks, or compare two chairs?" in said


async def test_a_taste_filters_the_listing_then_offers_the_room() -> None:
    """A named taste filters the room's own listing (not a page of its own),
    then Emily offers the whole room; with a yes and a budget she is told to
    build it (owner, 2026-11-03)."""
    llm = ScriptedGemini(
        {
            "A home office please.": [
                reply_and_call("A home office.", "update_brief", update={"room": "home-office"}),
                reply("Which colours?"),
            ],
            "Neutral.": [
                reply_and_call(
                    "Let me narrow these to neutral.",
                    "update_brief",
                    update={"colours": ["neutral"]},
                ),
                reply("Would you like me to help set up the entire room?"),
            ],
            "Yes, about two thousand.": [
                reply_and_call("Two thousand it is.", "update_brief", update={"budget": 2000}),
                reply("Building it now."),
            ],
        }
    )
    async with demo("fernhollow", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("A home office please.")
        await rig.driver.user_says("Neutral.")
        brain = rig.brain
        assert isinstance(brain, FernhollowBrain)
        assert brain.screen.page == "room/home-office", "filtered on a page of its own"
        # "neutral" reads as several catalog colours; all are sent, ticked together.
        assert "neutral" in rig.command("apply_filters")["filters"]["colours"]
        offered = _results(llm.captured_contents[-1])["update_brief"]
        assert "Would you like me to help set up the entire room?" in offered
        await rig.driver.user_says("Yes, about two thousand.")
        assert "call build_room now" in _results(llm.captured_contents[-1])["update_brief"]


async def test_the_grid_follows_the_brief_and_shows_the_question() -> None:
    """The brief asks about a taste and says which options, so the page can
    show them; once the shopper names one, the grid is filtered to it without
    the model calling set_filters or sending them to the sidebar."""
    llm = ScriptedGemini(
        {
            "A home office please.": [
                reply_and_call("A home office.", "update_brief", update={"room": "home-office"}),
                reply("Which colours?"),
            ],
            "Taupe.": [
                reply_and_call("Taupe it is.", "update_brief", update={"colours": ["taupe"]}),
                reply("Here they are."),
            ],
        }
    )
    async with demo("fernhollow", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("A home office please.")
        asking = rig.command("update_brief")["asking"]
        assert asking is not None and asking["dim"] in ("styles", "materials", "colours")
        assert asking["options"], "a question with nothing to show"
        assert "apply_filters" not in rig.actions(), "filtered before any taste was known"
        await rig.driver.user_says("Taupe.")
        sent = rig.command("apply_filters")
        assert sent["filters"]["room"] == "home-office"
        assert sent["filters"]["colours"] == ["taupe"]
        assert sent["count"] > 0


async def test_pieces_come_off_the_board_when_not_needed() -> None:
    """ "Drop the rug and the lamp" takes those tiles off the room board — the
    rest held still, the total recomputed — rather than touching the shortlist
    and saying it did."""
    llm = ScriptedGemini(
        {
            "Build me a home office around two thousand.": [
                Reply(
                    text="A home office around two thousand.",
                    calls=(
                        ("update_brief", {"update": {"room": "home-office", "budget": 2000}}),
                        ("build_room", {"request": {}}),
                    ),
                ),
                reply("Here it is."),
            ],
            "Drop the rug and the lamp, I don't need them.": [
                reply_and_call(
                    "Taking those off.", "remove_pieces", request={"pieces": ["rug", "lamp"]}
                ),
                reply("Done."),
            ],
        }
    )
    async with demo("fernhollow", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Build me a home office around two thousand.")
        await rig.driver.user_says("Drop the rug and the lamp, I don't need them.")
        brain = rig.brain
        assert isinstance(brain, FernhollowBrain)
        assert brain.screen.room is not None
        assert [p.slot for p in brain.screen.room.pieces] == ["desk", "chair", "shelving"]
        sent = rig.command("remove_pieces")
        assert sent["slots"] == ["rug", "lamp"]
        assert sent["total"] == brain.screen.room.total
        assert "update_shortlist" not in rig.actions()


async def test_this_one_means_what_is_on_screen() -> None:
    """A tap on the page moves the mirror, so "the second one" and "this" name
    what the shopper sees now — not what the brain last showed."""
    desks = CATALOG.by_category["desks"]
    llm = ScriptedGemini(
        {
            "Open the second one.": [
                reply_and_call("Here it is.", "show", request={"product": "2"}),
                reply("It comes in ash or walnut."),
            ],
            "Show me this in walnut.": [
                reply_and_call(
                    "In walnut.", "show", request={"product": "this", "option": "Walnut"}
                ),
                reply("Here it is in walnut."),
            ],
        }
    )
    async with demo("fernhollow", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.send_ui_event(
            "visible_products", {"product_ids": desks[:4], "by": "visitor"}
        )
        await asyncio.sleep(0.1)
        await rig.driver.user_says("Open the second one.")
        opened = rig.command("open_product")
        assert opened["product_id"] == desks[1]
        await rig.driver.user_says("Show me this in walnut.")
        walnut = [c for c in rig.driver.ui_commands if c.get("command") == "open_product"][-1]
        product = CATALOG.products[desks[1]]
        assert walnut["payload"]["variant_id"] == product.variant_for("Walnut").id
        # The facts the model answers from are the catalog's own.
        facts = _results(llm.captured_contents[-1])["show"]
        assert product.intro in facts and "sizes, stock and delivery dates" in facts


async def test_filters_say_their_assumption() -> None:
    """A broad word is mapped to the catalog's own words, and the result says
    how — the model says that aloud."""
    llm = ScriptedGemini(
        {
            "Show me wood desks under five hundred.": [
                reply_and_call(
                    "Wood desks under five hundred.",
                    "set_filters",
                    request={"category": "desks", "materials": ["wood"], "price_max": 500},
                ),
                reply("I read wood as oak, walnut, ash and the like."),
            ],
            "Drop the price limit.": reply_and_call(
                "Price limit off.", "remove_filter", request={"key": "price_max"}
            ),
            "Go back.": reply_and_call("Back as it was.", "undo"),
        }
    )
    async with demo("fernhollow", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Show me wood desks under five hundred.")
        applied = rig.command("apply_filters")
        assert applied["filters"]["category"] == "desks"
        assert "oak" in applied["filters"]["materials"] and applied["filters"]["price_max"] == 500
        assert applied["assumption"] and "wood" in applied["assumption"]
        assert all(CATALOG.products[i].price <= 500 for i in applied["product_ids"])
        await rig.driver.user_says("Drop the price limit.")
        removed = rig.command("remove_filter")
        assert removed["key"] == "price_max" and removed["count"] > applied["count"]
        await rig.driver.user_says("Go back.")
        assert rig.actions()[-1] == "undo"
        brain = rig.brain
        assert isinstance(brain, FernhollowBrain)
        assert brain.screen.filters.price_max == 500


async def test_a_silent_call_is_still_said() -> None:
    """The prompt has Emily speak with every call; when the model calls alone it
    is asked once more with tools off (round 1), and when that is silent too the
    brain says the landed line."""
    llm = ScriptedGemini(
        {
            "Show me the returns policy.": [
                call("store_policy", request={"topic": "returns"}),
                reply(""),
            ]
        }
    )
    async with demo("fernhollow", llm) as rig:
        await rig.driver.start_session()
        turn = await rig.driver.user_says("Show me the returns policy.")
        check_turn(rig, turn, units=1)
        assert turn.units[0].text in ("The policy is on screen.", "Here's the policy.")
        assert rig.command("open_policy")["topic"] == "returns"
        assert len(llm.captured_contents) == 2


def test_marks_are_reads() -> None:
    """The mark, pinned tool by tool: the tools whose answer only the engine
    knows hold the turn; the rest say their line with the call."""
    brain = FernhollowBrain(client=ScriptedGemini({}))  # pyright: ignore[reportArgumentType]
    held = {tool.__name__ for tool in brain.tools if _needs_result_now(tool)}
    assert held == {
        "update_brief",
        "build_room",
        "swap_piece",
        "piece_options",
        "goes_with",
        "more_like",
        "compare",
        "edit_compare",
        "set_filters",
        "stretch_budget",
        "show",
        "suggest_finish",
        "check_exchange",
        "resolve_product",
        "fill_checkout",
        # What to say on opening a step depends on it: the shopper types their
        # own email and phone, said as the page opens, not a turn later.
        "checkout_step",
        # The front of house (CONTRACT v5): the gift edit's next question or
        # picks, where a parcel is and the kiosk's picks are said from the result.
        "gift_edit",
        "track_order",
        "kiosk_answer",
        # v6 (owner, round 1): she leads. Saving a pick returns the next piece
        # on the shopper's list to offer; the saved view says how the picks go
        # together; the day picker's days, the return form's items and its next
        # question are said from the result, in the same turn.
        "shortlist",
        "show_saved",
        "change_delivery",
        "start_return",
        "fill_return",
        # Whether an order can be cancelled or brought forward is the status's
        # to say (often no): the answer, or the cancel question, is said now.
        "cancel_order",
        "request_earlier",
    }
    assert len(brain.tools) == 35


def test_prompt_names_only_what_exists() -> None:
    """The catalog section is generated: every style the products use, and
    none they do not."""
    from voqalize_demos._loaded.fernhollow.prompt import system_instruction

    prompt = system_instruction()
    styles = [w for w, _ in CATALOG.vocab["styles"]]
    assert set(styles) == {
        "minimalist",
        "modern",
        "organic",
        "classic",
        "contemporary",
        "sculptural",
        "rustic",
        "luxury",
        "vintage",
        "modular",
    }
    assert f"Styles named: {', '.join(styles)}." in prompt
    assert "scandinavian" not in prompt.lower()
    assert "don't sell" not in prompt.lower() and "do not sell" not in prompt.lower()


# ─── One acknowledgement, upstream ────────────────────────────────────────────


def test_emily_never_opens_on_an_acknowledgement() -> None:
    """One acknowledgement, upstream: Voqalize's own ack covers the wait, so no
    line Emily says — the greeting, every scripted reply here, and every landed
    line the brain can speak in a silent turn — opens on one of her own."""
    import inspect

    from voqalize_demos._loaded.fernhollow import brain as fb
    from voqalize_demos._loaded.fernhollow.prompt import ACK_OPENER

    lines = [GREETING]
    for script in (
        _story(),
        _circle_llm(),
        _brief_llm(),
        _orders_llm(),
        _return_llm(),
        _gifts_llm(),
    ):
        for cursor in script._cursors.values():  # pyright: ignore[reportPrivateUsage]
            lines += [step.spoken for step in cursor.steps if step.spoken]
    source = inspect.getsource(fb)
    landed = re.findall(r'landed\(\s*((?:f?"[^"]*",?\s*)+)\)', source)
    assert len(landed) >= 15, landed
    for group in landed:
        lines += re.findall(r'f?"([^"]*)"', group)
    for line in lines:
        first = re.split(r"(?<=[.!?—])\s", line.strip(), maxsplit=1)[0]
        assert not ACK_OPENER.match(first), f"opens on an acknowledgement: {line!r}"
    assert ACK_OPENER.match("Let me check that.") and ACK_OPENER.match("Sure! Here it is.")


DESK_LINE = "modern-home-office-desk-with-chestnut-brown-finish"


async def test_emilys_own_changes_are_followed_but_not_told() -> None:
    """The page reports Emily's own moves with ``by: "emily"`` (or ``"mira"``,
    from a page a release behind): the mirror follows them, and the model hears
    nothing it already knows. The shopper's own act is told."""
    desks = CATALOG.by_category["desks"]
    async with demo("fernhollow", ScriptedGemini()) as rig:
        await rig.driver.start_session()
        brain = rig.brain
        assert isinstance(brain, FernhollowBrain)

        def told() -> list[str]:
            return [
                p.text or ""
                for c in brain._history  # pyright: ignore[reportPrivateUsage]
                if c.role == "user"
                for p in c.parts or []
                if "The shopper opened" in (p.text or "")
            ]

        for by, pid in (("emily", desks[0]), ("mira", desks[1])):
            await rig.driver.send_ui_event(
                "product_viewed", {"product_id": pid, "variant_id": None, "by": by}
            )
            await asyncio.sleep(0.1)
            assert brain.screen.product == pid
        assert told() == [], "an agent-made change reached the context"
        await rig.driver.send_ui_event(
            "product_viewed", {"product_id": desks[2], "variant_id": None, "by": "visitor"}
        )
        await asyncio.sleep(0.1)
        assert brain.screen.product == desks[2]
        assert len(told()) == 1 and desks[2] in told()[0]


# ─── v2: references, and checkout by voice ────────────────────────────────────

OAK_SOFAS = [p for p in CATALOG.by_category["sofas"] if "oak" in p]
GRID = [{"product_id": p, "row": i // 3, "col": i % 3} for i, p in enumerate(OAK_SOFAS)]
DEEP = ("modular-oak-sofa-with-deep-seating", "modular-oak-sofa-with-deep-seats")


async def _show_grid(rig: DemoRig) -> None:
    await rig.driver.send_ui_event(
        "visible_products", {"product_ids": OAK_SOFAS, "layout": GRID, "by": "visitor"}
    )
    await asyncio.sleep(0.1)


async def test_a_garbled_name_between_look_alikes_is_asked_not_guessed() -> None:
    """A sofa listing, and a name the recognizer garbled that fits two of them:
    both are numbered on screen and Emily asks one question naming the
    difference; "the second one" then resolves to the second, and the badges go."""
    llm = ScriptedGemini(
        {
            "the moduler oak sofa with deep seat": [
                reply_and_call(
                    "Two of these fit that.",
                    "resolve_product",
                    request={"spoken": "the moduler oak sofa with deep seat"},
                ),
                reply("Which one: one, top right, or two, in the middle?"),
            ],
            "The second one.": [
                reply_and_call(
                    "The second.", "resolve_product", request={"spoken": "the second one"}
                ),
                reply("Good choice — the deep-seat modular in oak."),
            ],
        }
    )
    async with demo("fernhollow", llm) as rig:
        await rig.driver.start_session()
        await _show_grid(rig)
        await rig.driver.user_says("I like the moduler oak sofa with deep seat")
        choices = rig.command("show_choices")
        assert tuple(choices["product_ids"]) == DEEP
        assert choices["label"].startswith("Which one:")
        asked = _results(llm.captured_contents[-1])["resolve_product"]
        assert "Ask exactly this" in asked and choices["label"] in asked
        assert "open_product" not in rig.actions(), "it guessed between close candidates"

        await rig.driver.user_says("The second one.")
        said = _results(llm.captured_contents[-1])["resolve_product"]
        assert f"[id {DEEP[1]}]" in said
        assert rig.actions()[-1] == "clear_choices"


async def test_a_clear_reference_is_not_questioned() -> None:
    """One sofa clearly meant — by name, or by its place on screen — is used
    at once, with no choices and no question."""
    llm = ScriptedGemini(
        {
            "the oak sectional": [
                reply_and_call(
                    "The sectional.", "resolve_product", request={"spoken": "the oak sectional"}
                ),
                reply("The modular oak sectional, here."),
            ],
            "the bottom left one": [
                reply_and_call(
                    "That one.", "resolve_product", request={"spoken": "the bottom left one"}
                ),
                reply("That's it."),
            ],
        }
    )
    async with demo("fernhollow", llm) as rig:
        await rig.driver.start_session()
        await _show_grid(rig)
        await rig.driver.user_says("Tell me about the oak sectional")
        assert (
            "[id modular-oak-sectional-sofa]"
            in _results(llm.captured_contents[-1])["resolve_product"]
        )
        await rig.driver.user_says("And the bottom left one")
        bottom_left = next(g["product_id"] for g in GRID if g["row"] == 2 and g["col"] == 0)
        assert f"[id {bottom_left}]" in _results(llm.captured_contents[-1])["resolve_product"]
        assert "show_choices" not in rig.actions()


async def test_pointing_is_this_one() -> None:
    """What the shopper points at (fresh) is "this", silently."""
    llm = ScriptedGemini(
        {
            "Add this one.": reply_and_call(
                "Shall I add it?", "add_to_cart", request={"what": "product", "product": "this"}
            )
        }
    )
    async with demo("fernhollow", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.send_ui_event(
            "pointing", {"product_id": OAK_SOFAS[0], "how": "hover", "by": "visitor"}
        )
        await asyncio.sleep(0.1)
        brain = rig.brain
        assert isinstance(brain, FernhollowBrain)
        assert not any(
            "pointing" in (p.text or "").lower()
            for c in brain._history  # pyright: ignore[reportPrivateUsage]
            for p in c.parts or []
        ), "a pointing was spoken about"
        await rig.driver.user_says("Add this one.")
        assert rig.command("cart_updated")["lines"][0]["product_id"] == OAK_SOFAS[0]


DESK_ID = "modern-home-office-desk-with-chestnut-brown-finish"


async def test_checkout_fully_by_voice_with_the_yes() -> None:
    """Emily opens checkout first, leaves email and phone to the shopper's own
    typing (personal data is never filled, so never said), fills the name and
    address from what they say, reads the postcode back, asks before placing
    the order, and places it only on the shopper's yes in a later turn — with
    the authored delivery charge."""
    llm = ScriptedGemini(
        {
            "Let's check out.": [
                reply_and_call(
                    "Here's checkout. Type your email and phone in yourself, and I'll do the rest.",
                    "checkout_step",
                    request={"step": "contact"},
                ),
                reply("What name should the order go under?"),
            ],
            "I'm Sam Rivera.": [
                Reply(
                    text="Sam Rivera, noted.",
                    calls=(
                        # A model that tries anyway: the field is not even in its schema.
                        (
                            "fill_checkout",
                            {
                                "fields": {
                                    "email": "sam dot rivera at example dot com",
                                    "first_name": "Sam",
                                    "last_name": "Rivera",
                                }
                            },
                        ),
                    ),
                ),
                reply("And the address?"),
            ],
            "12 Elm Street, Portland, 97201, United States.": [
                Reply(
                    text="Twelve Elm Street, Portland.",
                    calls=(
                        (
                            "fill_checkout",
                            {
                                "fields": {
                                    "address1": "12 Elm Street",
                                    "city": "Portland",
                                    "postcode": "97201",
                                    "country": "United States",
                                }
                            },
                        ),
                        ("place_order", {"request": {"confirmed_by_voice": True}}),
                    ),
                ),
                reply("Postcode nine seven two zero one."),
            ],
            "Looks right.": [
                reply_and_call("The total is up.", "place_order", request={}),
                reply("Shall I place the order?"),
            ],
            "Yes, place it.": reply_and_call(
                "Placing it now.", "place_order", request={"confirmed_by_voice": True}
            ),
        }
    )
    async with demo("fernhollow", llm) as rig:
        await rig.driver.start_session()
        brain = rig.brain
        assert isinstance(brain, FernhollowBrain)
        await rig.driver.send_ui_event(
            "cart_changed",
            {
                "lines": [{"product_id": DESK_ID, "variant_id": "27504", "qty": 1}],
                "total": 499.99,
                "by": "visitor",
            },
        )
        await asyncio.sleep(0.1)

        await rig.driver.user_says("Let's check out.")
        assert rig.command("checkout_step")["step"] == "contact", "asked before checkout was open"

        await rig.driver.user_says("I'm Sam Rivera.")
        # checkout_step is an action, so its result rides this next request.
        results = _results(llm.captured_contents[-1])
        assert "email (the shopper types it themselves" in results["checkout_step"]
        first = results["fill_checkout"]
        fills = [
            c["payload"] for c in rig.driver.ui_commands if c.get("command") == "checkout_fill"
        ]
        assert [f["field"] for f in fills] == ["first_name", "last_name"], "email was filled"
        assert "email (the shopper types it themselves" in first

        # The shopper types their email on the page: the brain hears the field, not the value.
        await _type_email(rig)
        await rig.driver.user_says("12 Elm Street, Portland, 97201, United States.")
        second = _results(llm.captured_contents[-1])
        assert "9 7 2 0 1" not in second["fill_checkout"], "the postcode is read back"
        assert "please check them and click Review order" in second["fill_checkout"]
        assert "NOT DONE" in second["place_order"], "a yes it was never asked for placed an order"
        assert "order_placed" not in rig.actions()

        await rig.driver.user_says("Looks right.")
        confirm = rig.command("confirm_place_order")
        assert confirm["total"] == 548.99  # $499.99 is not over $500: the flat $49 applies
        assert "order_placed" not in rig.actions()

        await rig.driver.user_says("Yes, place it.")
        placed = rig.command("order_placed")
        assert placed["order_number"] == "FH-30001" and placed["total"] == 548.99
        assert brain.cart == {} and brain.confirms.pending is None


# ─── v3: circle to ask ────────────────────────────────────────────────────────

SOFAS = CATALOG.by_category["sofas"]


async def _circle(rig: DemoRig, things: list[dict[str, str]], page: str = "home") -> None:
    await rig.driver.send_ui_event(
        "selection", {"things": things, "gesture": "circle", "page": page, "by": "visitor"}
    )
    await asyncio.sleep(0.1)


def _circle_llm() -> ScriptedGemini:
    return ScriptedGemini(
        {
            "Compare these.": [
                reply_and_call("Side by side.", "compare", request={"products": ["these"]}),
                reply("The first is the cheapest."),
            ],
            "Show me this.": reply_and_call("Here it is.", "show", request={"page": "this"}),
            "Compare them.": [
                reply_and_call("Six are circled.", "compare", request={"products": ["them"]}),
                reply("You've circled six sofas — which two to four shall I compare?"),
            ],
        }
    )


async def test_circling_three_sofas_then_compare_these() -> None:
    """Three sofas circled on the home page: nothing happens until the shopper
    speaks; the selection survives a page change; "compare these" compares
    exactly those three."""
    llm = _circle_llm()
    async with demo("fernhollow", llm) as rig:
        await rig.driver.start_session()
        picked = SOFAS[:3]
        await _circle(rig, [{"kind": "product", "id": i} for i in picked])
        assert rig.actions() == [], "acted on a selection the shopper did not speak about"
        await rig.driver.send_ui_event("page_viewed", {"path": "category/sofas", "by": "visitor"})
        await asyncio.sleep(0.1)
        check_turn(rig, await rig.driver.user_says("Compare these."), units=2)
        assert set(rig.command("show_compare")["product_ids"]) == set(picked)
        note = " ".join(
            p.text or "" for c in llm.captured_contents[0] for p in c.parts or [] if p.text
        )
        assert "circled 3 things" in note and "do nothing yet" in note


async def test_a_circled_room_tile_and_show_me_this() -> None:
    llm = _circle_llm()
    async with demo("fernhollow", llm) as rig:
        await rig.driver.start_session()
        await _circle(rig, [{"kind": "room", "id": "home-office"}])
        await rig.driver.user_says("Show me this.")
        assert rig.command("navigate")["page"] == "room/home-office"


async def test_six_circled_for_a_compare_is_asked_about() -> None:
    llm = _circle_llm()
    async with demo("fernhollow", llm) as rig:
        await rig.driver.start_session()
        await _circle(rig, [{"kind": "product", "id": i} for i in SOFAS[:6]], page="category/sofas")
        check_turn(rig, await rig.driver.user_says("Compare them."), units=2)
        assert "show_compare" not in rig.actions()
        said = _results(llm.captured_contents[-1])["compare"]
        assert "6 products are circled" in said and "ask which to compare" in said
        assert CATALOG.products[SOFAS[5]].title in said


async def test_a_cleared_selection_is_not_these() -> None:
    llm = ScriptedGemini(
        {
            "Compare these.": [
                reply_and_call("Side by side.", "compare", request={"products": ["these"]}),
                reply("Which ones?"),
            ]
        }
    )
    async with demo("fernhollow", llm) as rig:
        await rig.driver.start_session()
        await _circle(rig, [{"kind": "product", "id": i} for i in SOFAS[:2]])
        await rig.driver.send_ui_event("selection_cleared", {"by": "visitor"})
        await asyncio.sleep(0.1)
        await rig.driver.user_says("Compare these.")
        assert "show_compare" not in rig.actions()


# ─── Returns by voice: the yes, and the page's answer ───────────────────────────────────────────

CHAIR_ID = "desk-chair-with-aluminum-frame"
CHAIR_VARIANT = CATALOG.products[CHAIR_ID].variants[0].id


def _return_calls(**answers: Any) -> tuple[tuple[str, dict[str, Any]], ...]:
    """Start the return of the chair on FH-20418 and give every answer at once
    (a shopper who says it all in one breath): the form fills to the review."""
    full = {
        "items": [{"product": CHAIR_ID, "qty": 1}],
        "reason": "changed_mind",
        "condition": "unused_unpacked",
        "resolution": "refund",
        "collection": "drop_off",
        **answers,
    }
    return (
        ("start_return", {"order_number": "FH-20418"}),
        ("fill_return", {"answers": full}),
    )


def _stage_moves(rig: DemoRig) -> list[dict[str, Any]]:
    return [dict(c["payload"]) for c in rig.driver.ui_commands if c.get("command") == "stage_move"]


async def _answer(rig: DemoRig, moves: list[dict[str, Any]], outcome: str = "applied") -> None:
    for m in moves:
        await rig.driver.send_ui_event(
            "stage_result", {"call_ref": m["call_ref"], "move": m["move"], "outcome": outcome}
        )
    await asyncio.sleep(0.1)


async def test_this_never_means_i_cannot_see() -> None:
    """A circled product is "this", ahead of a pointing."""
    llm = ScriptedGemini(
        {
            "Can you tell me about this?": [
                reply_and_call("This one's a good pick.", "show", request={"product": "this"}),
                reply("It's the cream linen sofa."),
            ]
        }
    )
    async with demo("fernhollow", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.send_ui_event(
            "pointing", {"product_id": SOFAS[4], "how": "hover", "by": "visitor"}
        )
        await _circle(rig, [{"kind": "product", "id": SOFAS[1]}])
        await rig.driver.user_says("Can you tell me about this?")
        assert rig.command("open_product")["product_id"] == SOFAS[1]


async def test_yes_to_submit_speaks_once_and_never_runs_a_silent_turn() -> None:
    """The live failure, replayed: "Yes" to "Shall I submit the return?" →
    returns.submit applied with the reference → return_submitted → the page
    opens the confirmation. Emily says "Submitting it now." herself, with no
    model request, then exactly one outcome line with the reference — never
    the page's "thank them" a second time — and no turn is speechless."""
    from loguru import logger

    turns: list[str] = []
    sink = logger.add(
        lambda m: turns.append(m.record["message"]),
        level="INFO",
        filter=lambda r: r["message"].startswith("turn:") or "said nothing" in r["message"],
    )
    llm = ScriptedGemini(
        {
            "Return the chair from FH-20418: doesn't suit, boxed, refund, pickup Saturday.": [
                Reply(
                    text="Putting that on your return now.",
                    calls=_return_calls(
                        reason="doesnt_suit_room",
                        condition="unused_in_packaging",
                        collection="pickup",
                        pickup_window="saturday",
                    ),
                ),
                reply("Everything is filled in. Shall I submit the return?"),
            ],
            # Were the model asked after the yes, this is the silent duplicate
            # submit from the live call. It must never be asked.
            "Yes.": call("submit_return", request={"confirmed_by_voice": True}),
        }
    )
    try:
        async with demo("fernhollow", llm) as rig:
            await rig.driver.start_session()
            await rig.driver.user_says(
                "Return the chair from FH-20418: doesn't suit, boxed, refund, pickup Saturday."
            )
            await _answer(rig, _stage_moves(rig))
            asked = len(llm.captured_contents)

            yes = await rig.driver.user_says("Yes.")
            check_turn(rig, yes, units=1)
            assert [u.text for u in yes.units] == ["Submitting it now."]
            assert len(llm.captured_contents) == asked, "the model ran after a handled yes"
            submit = _stage_moves(rig)[-1]
            assert submit["move"] == "returns.submit"

            await rig.driver.send_ui_event(
                "stage_result",
                {
                    "call_ref": submit["call_ref"],
                    "move": "returns.submit",
                    "outcome": "applied",
                    "detail": "return submitted, reference RT-923348-1",
                },
            )
            await rig.driver.send_ui_event(
                "stage_event",
                {
                    "name": "returns.return_submitted",
                    "by": "agent",
                    "data": {"reference": "RT-923348-1", "filled": ["order_number", "email"]},
                },
            )
            await rig.driver.send_ui_event(
                "page_viewed", {"path": "returns/confirmation", "by": "emily"}
            )
            await asyncio.sleep(0.1)
            outcome = await rig.driver.user_idle()
            check_turn(rig, outcome, units=1)
            assert [u.text for u in outcome.units] == [
                "Done — your return is in, reference RT-923348-1. We'll be in touch about the pickup."
            ]
            again = await rig.driver.user_idle()
            assert again.units == [], "the outcome was said twice"
            assert len(llm.captured_contents) == asked, "a model turn ran for the outcome"
    finally:
        logger.remove(sink)
    assert not [t for t in turns if "speechless=yes" in t or "said nothing" in t], turns


async def test_a_silent_refused_call_still_says_something() -> None:
    """A tool call refused, with nothing spoken: the floor speaks, honestly."""
    llm = ScriptedGemini(
        {"Submit it.": call("submit_return", request={"confirmed_by_voice": True})}
    )
    async with demo("fernhollow", llm) as rig:
        await rig.driver.start_session()
        turn = await rig.driver.user_says("Submit it.")
        check_turn(rig, turn, units=1)
        assert [u.text for u in turn.units] == ["That didn't go through yet."]


@pytest.mark.parametrize(
    "said", ["Can you please submit it?", "Yes please.", "Go ahead and submit it."]
)
async def test_any_plain_yes_submits_once(said: str) -> None:
    llm = ScriptedGemini(
        {
            "Return the chair from FH-20418": [
                Reply(text="Putting that on your return now.", calls=_return_calls()),
                reply("Everything is filled in. Shall I submit the return?"),
            ],
            "Did it go?": call("submit_return", request={"confirmed_by_voice": True}),
        }
    )
    async with demo("fernhollow", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Return the chair from FH-20418")
        await _answer(rig, _stage_moves(rig))
        yes = await rig.driver.user_says(said)
        assert [u.text for u in yes.units] == ["Submitting it now."]
        submit = _stage_moves(rig)[-1]
        await rig.driver.send_ui_event(
            "stage_result",
            {
                "call_ref": submit["call_ref"],
                "move": "returns.submit",
                "outcome": "applied",
                "detail": "return submitted, reference RT-20418-1",
            },
        )
        await asyncio.sleep(0.1)
        done = await rig.driver.user_idle()
        assert [u.text for u in done.units] == [
            "Done — your return is in, reference RT-20418-1. We'll be in touch about the drop-off."
        ]
        # The model, asked later, calls submit again: blocked, and still spoken.
        dup = await rig.driver.user_says("Did it go?")
        check_turn(rig, dup, units=1)
        assert [u.text for u in dup.units] == [
            "That's already done — your return is in, reference RT-20418-1. "
            "We'll be in touch about the drop-off."
        ]
        assert [m["move"] for m in _stage_moves(rig)].count("returns.submit") == 1


# ─── Every confirmation, one mechanism (parametrized across the acts) ─────────

#: What Emily fills at checkout. Email and phone are not hers: the shopper types
#: them, which reaches the brain as ``checkout_changed`` with the field name only.
_FIELDS = {
    "first_name": "Sam",
    "last_name": "Rivera",
    "address1": "12 Elm Street",
    "city": "Portland",
    "postcode": "97201",
    "country": "United States",
}

#: kind → (the line that asks, the calls that ask, the line on a yes, what reaches the page).
#: Adding to the cart is not here: it asks nothing (owner, 2026-11-03).
ASKS: dict[str, tuple[str, tuple[tuple[str, dict[str, Any]], ...], str, str]] = {
    "place_order": (
        "That's everything — shall I place the order?",
        (("fill_checkout", {"fields": _FIELDS}), ("place_order", {"request": {}})),
        "It's placed — your order number is FH-30001.",
        "order_placed",
    ),
    "submit_return": (
        "Putting that on your return now. Shall I submit it?",
        _return_calls(),
        "Submitting it now.",
        "returns.submit",
    ),
    # Cancelling a packed order (owner, round 1, F8): the same ask, yes, act, outcome.
    "cancel_order": (
        "It's still packed, so it can be cancelled. Shall I cancel order FH-31207?",
        (("cancel_order", {"order_number": "FH-31207"}),),
        "Cancelling it now.",
        "orders.cancel",
    ),
}
_CONFIRMED_CALL = {
    "place_order": ("place_order", {"request": {"confirmed_by_voice": True}}),
    "submit_return": ("submit_return", {"request": {"confirmed_by_voice": True}}),
    "cancel_order": ("cancel_order", {"order_number": "FH-31207", "confirmed_by_voice": True}),
}


async def _type_email(rig: DemoRig) -> None:
    """The shopper types their email at checkout: the page sends the field's
    name, never its value."""
    await rig.driver.send_ui_event("checkout_changed", {"field": "email", "by": "visitor"})
    await asyncio.sleep(0.1)


def _sent(rig: DemoRig, what: str) -> int:
    if what.startswith(("returns.", "orders.")):
        return [m["move"] for m in _stage_moves(rig)].count(what)
    return rig.actions().count(what)


async def _asked(rig: DemoRig, kind: str) -> None:
    await rig.driver.start_session()
    if kind == "place_order":
        await rig.driver.send_ui_event(
            "cart_changed",
            {
                "lines": [{"product_id": CHAIR_ID, "variant_id": CHAIR_VARIANT, "qty": 1}],
                "total": 289.0,
                "by": "visitor",
            },
        )
        await _type_email(rig)
    check_turn(rig, await rig.driver.user_says(f"Let's do the {kind}."))
    if kind in ("submit_return", "cancel_order"):
        await _answer(rig, _stage_moves(rig))


def _conf_llm(kind: str) -> ScriptedGemini:
    ask, calls, _, _ = ASKS[kind]
    name, args = _CONFIRMED_CALL[kind]
    return ScriptedGemini(
        {
            f"Let's do the {kind}.": Reply(text=ask, calls=calls),
            # A marked tool (cancel_order) gets a second hop: silent here, so
            # the duplicate's exact line is the floor.
            "Do it again.": [Reply(calls=((name, args),)), reply("")],
        }
    )


def _turn_sink() -> tuple[list[str], int]:
    from loguru import logger

    seen: list[str] = []
    sink = logger.add(
        lambda m: seen.append(m.record["message"]),
        level="INFO",
        filter=lambda r: r["message"].startswith("turn:") or "said nothing" in r["message"],
    )
    return seen, sink


@pytest.mark.parametrize("kind", sorted(ASKS))
async def test_a_yes_acts_once_and_a_duplicate_still_speaks(kind: str) -> None:
    from loguru import logger

    seen, sink = _turn_sink()
    llm = _conf_llm(kind)
    _, _, said, what = ASKS[kind]
    try:
        async with demo("fernhollow", llm) as rig:
            await _asked(rig, kind)
            asked = len(llm.captured_contents)
            yes = await rig.driver.user_says("Yes, please.")
            check_turn(rig, yes, units=1)
            assert [u.text for u in yes.units] == [said]
            assert len(llm.captured_contents) == asked, "the model ran after a handled yes"
            assert _sent(rig, what) == 1
            dup = await rig.driver.user_says("Do it again.")
            check_turn(rig, dup, units=1)
            assert dup.units[0].text.startswith("That's already"), dup.units[0].text
            assert _sent(rig, what) == 1, "a confirmed act was sent twice"
    finally:
        logger.remove(sink)
    # Every turn the model left silent was covered by the floor: no silent turn.
    silent = [t for t in seen if "speechless=yes" in t]
    # The model is asked once more (it may say nothing); then the written floor.
    floored = [t for t in seen if "the brain says" in t]
    assert len(silent) == len(floored), seen


@pytest.mark.parametrize("kind", sorted(ASKS))
@pytest.mark.parametrize("said", ["No, wait.", "Yes but change it", "What's the total?"])
async def test_anything_but_a_plain_yes_acts_nothing(kind: str, said: str) -> None:
    llm = _conf_llm(kind)
    _, _, _, what = ASKS[kind]
    async with demo("fernhollow", llm) as rig:
        await _asked(rig, kind)
        turn = await rig.driver.user_says(said)
        check_turn(rig, turn)
        assert _sent(rig, what) == 0
        brain = rig.brain
        assert isinstance(brain, FernhollowBrain)
        if said.startswith("No"):
            assert brain.confirms.pending is None, "a no left the question open"
        else:
            assert brain.confirms.pending is not None


@pytest.mark.parametrize(
    ("outcome", "detail", "line"),
    [
        (
            "applied",
            "return submitted, reference RT-20418-1",
            "Done — your return is in, reference RT-20418-1. We'll be in touch about the drop-off.",
        ),
        (
            "refused",
            "step 1: Enter the email",
            "That didn't go through — the page says: step 1: Enter the email.",
        ),
        (
            "unknown",
            None,
            "I can't confirm that went through — the page didn't answer. Please check it on screen.",
        ),
    ],
)
async def test_the_page_answer_is_said_once(outcome: str, detail: str | None, line: str) -> None:
    llm = _conf_llm("submit_return")
    async with demo("fernhollow", llm) as rig:
        await _asked(rig, "submit_return")
        await rig.driver.user_says("Yes.")
        submit = _stage_moves(rig)[-1]
        payload: dict[str, Any] = {
            "call_ref": submit["call_ref"],
            "move": "returns.submit",
            "outcome": outcome,
        }
        if detail:
            payload["detail"] = detail
        await rig.driver.send_ui_event("stage_result", payload)
        if outcome == "applied":
            await rig.driver.send_ui_event(
                "stage_event",
                {
                    "name": "returns.return_submitted",
                    "by": "visitor",
                    "data": {"reference": "RT-20418-1", "filled": []},
                },
            )
        await asyncio.sleep(0.1)
        said = await rig.driver.user_idle()
        assert [u.text for u in said.units] == [line]
        again = await rig.driver.user_idle()
        assert again.units == [], "the outcome was said twice"


# ─── The front of house: a job per landing page (CONTRACT.md, v5) ─────────────

from voqalize_demos._loaded.fernhollow.edits import stored as stored_edits  # noqa: E402

KIOSK_PICKS = [x["product_id"] for x in stored_edits()["kiosk"]["living|warm_wood|400"]]
SHEETS = "organic-cotton-sheet-set-oat-milk"
SHEETS_KING = CATALOG.products[SHEETS].variant_for("King").id


def _last_result(llm: ScriptedGemini, tool: str) -> str:
    for contents in reversed(llm.captured_contents):
        found = _results(contents).get(tool)
        if found is not None:
            return found
    raise AssertionError(f"no result for {tool}")


def _notes(rig: DemoRig) -> str:
    brain = rig.brain
    assert isinstance(brain, FernhollowBrain)
    return " ".join(
        p.text or ""
        for c in brain._history  # pyright: ignore[reportPrivateUsage]
        for p in c.parts or []
        if p.text
    )


@pytest.mark.parametrize(
    ("landing", "job"),
    [
        ("/", "shop"),
        ("/returns", "orders"),
        ("/orders/return?order=FH-20377", "returns"),
        ("/gifts", "gifts"),
        ("/orders", "orders"),
        ("/kiosk", "kiosk"),
    ],
)
async def test_each_landing_page_starts_its_own_job(landing: str, job: str) -> None:
    """One brain, one character: the page the call starts on picks the job and
    its greeting; the persona's voice and language land on both legs."""
    async with demo("fernhollow", ScriptedGemini({})) as rig:
        greeting = await rig.driver.start_session(
            init={"surface": "fernhollow-web", "landing": landing, "lang": "en"}
        )
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text == GREETINGS[job]  # type: ignore[index]
        assert PERSONA.name in greeting.text
        check_voice_pair(rig, voice=VOICE, language=LANGUAGE)
        brain = rig.brain
        assert isinstance(brain, FernhollowBrain) and brain.job == job


async def test_landing_on_another_jobs_page_switches_the_job() -> None:
    async with demo("fernhollow", ScriptedGemini({})) as rig:
        await rig.driver.start_session(init={"landing": "/"})
        brain = rig.brain
        assert isinstance(brain, FernhollowBrain)
        await rig.driver.send_ui_event(
            "page_viewed", {"path": "/product/" + SHEETS, "by": "visitor"}
        )
        await asyncio.sleep(0.1)
        assert brain.job == "shop", "a product page belongs to no job: the job holds"
        await rig.driver.send_ui_event("page_viewed", {"path": "/gifts", "by": "visitor"})
        await asyncio.sleep(0.1)
        assert brain.job == "gifts"
        assert "Your job is now: gifts" in _notes(rig)


async def test_kiosk_three_questions_three_picks_and_start_over() -> None:
    llm = ScriptedGemini(
        {
            "The living room.": [
                reply_and_call("Living room.", "kiosk_answer", request={"room": "living"}),
                reply("What feel?"),
            ],
            "Warm wood, up to four hundred.": [
                reply_and_call(
                    "Warm wood, up to four hundred.",
                    "kiosk_answer",
                    request={"room": "living", "feel": "warm_wood", "budget": "400"},
                ),
                reply("Three picks, and a QR code to take them home."),
            ],
            "Start over.": reply_and_call("Starting over.", "kiosk_restart"),
        }
    )
    async with demo("fernhollow", llm) as rig:
        greeting = await rig.driver.start_session(init={"landing": "/kiosk"})
        # The call starting is the start (owner, round 1, F9): question 1 is on
        # screen as she asks which room.
        assert greeting is not None and "Which room" in greeting.text  # type: ignore[union-attr]
        assert [m["move"] for m in _stage_moves(rig)] == ["kiosk.start"]
        check_turn(rig, await rig.driver.user_says("The living room."), units=2)
        assert [(m["move"], m["args"]) for m in _stage_moves(rig)] == [
            ("kiosk.start", {}),
            ("kiosk.answer", {"question": "room", "value": "living"}),
        ]
        assert "What feel?" in _last_result(llm, "kiosk_answer")

        check_turn(rig, await rig.driver.user_says("Warm wood, up to four hundred."), units=2)
        assert [(m["move"], m["args"]) for m in _stage_moves(rig)[2:]] == [
            ("kiosk.answer", {"question": "feel", "value": "warm_wood"}),
            ("kiosk.answer", {"question": "budget", "value": "400"}),
        ], "the room already chosen is not sent again"
        picks = _last_result(llm, "kiosk_answer")
        assert len(KIOSK_PICKS) == 3 and "QR code" in picks
        for pid in KIOSK_PICKS:
            assert CATALOG.products[pid].title in picks and CATALOG.products[pid].price <= 400

        check_turn(rig, await rig.driver.user_says("Start over."), units=1)
        assert _stage_moves(rig)[-1]["move"] == "kiosk.restart"
        brain = rig.brain
        assert isinstance(brain, FernhollowBrain) and brain.kiosk == {}

        # Tapped by hand: the third tap hands the model the picks to talk about.
        for q, v in (("room", "living"), ("feel", "warm_wood"), ("budget", "400")):
            await rig.driver.send_ui_event(
                "stage_event",
                {"name": "kiosk.answered", "by": "visitor", "data": {"question": q, "value": v}},
            )
        await asyncio.sleep(0.1)
        notes = _notes(rig)
        assert all(CATALOG.products[pid].title in notes for pid in KIOSK_PICKS)


# ─── Round 1 (owner, 19 Nov 2026): she leads, remembers, and finishes the job ─

SAND = eng.map_terms("colours", ["sand"]).words
SAND_SOFAS = eng.Filters(category="sofas", colours=SAND).results()
SAND_RUGS = eng.Filters(category="rugs", colours=SAND).results()
SOFA_ID = SAND_SOFAS[0]
RUG_ID = SAND_RUGS[0]
CUSHIONS = [i.product_id for i in eng.goes_with(SOFA_ID, category="throw-pillows")]
CUSHION_ID = CUSHIONS[0]


def _brief_llm() -> ScriptedGemini:
    """The owner's call, replayed the way it should go: a sofa, a rug and
    cushions in sand, chosen one by one, seen together, added together."""
    return ScriptedGemini(
        {
            "I'm doing up my living room. I want a sofa, a rug and a few cushions, in sand.": [
                reply_and_call(
                    "A sofa, a rug and cushions, in sand.",
                    "update_brief",
                    update={
                        "room": "living",
                        "colours": ["sand"],
                        "pieces": ["sofa", "rug", "cushions"],
                    },
                ),
                reply("Here are the sand sofas first. Which one do you like?"),
            ],
            "I like the first one.": [
                reply_and_call("Good choice.", "shortlist", request={"add": ["the first one"]}),
                reply(
                    "It's saved. Shall we move on to the rug now, or see cushions that go with the sofa?"
                ),
            ],
            "The rug now.": [
                reply_and_call(
                    "Sand rugs, then.",
                    "set_filters",
                    request={"category": "rugs", "colours": ["sand"]},
                ),
                reply("Two sand rugs. Which one suits the sofa?"),
            ],
            "That first rug.": [
                reply_and_call("Saving it.", "shortlist", request={"add": ["the first one"]}),
                reply("Saved. Shall I show you cushions that go with the sofa?"),
            ],
            "Yes, cushions.": [
                reply_and_call(
                    "Cushions for the sofa.",
                    "goes_with",
                    request={"anchor": SOFA_ID, "category": "cushions"},
                ),
                reply("These pick up the sofa's tone. Which one?"),
            ],
            "The first cushion.": [
                reply_and_call("Saved.", "shortlist", request={"add": ["the first one"]}),
                reply("All three are saved. Shall I show them together?"),
            ],
            # The live mistake: a compare of a sofa, a rug and a cushion. Refused;
            # the model then shows the saved picks together instead.
            "Show me what I've selected.": [
                reply_and_call(
                    "Here they are.",
                    "compare",
                    request={"products": [SOFA_ID, RUG_ID, CUSHION_ID]},
                ),
                reply_and_call("Your picks, together.", "show_saved"),
                reply("They share sand. Shall I add all three to your cart?"),
            ],
            "Add them to the cart.": reply_and_call(
                "Adding all three.", "add_to_cart", request={"what": "saved"}
            ),
        }
    )


async def test_the_brief_is_remembered_and_walked_in_order() -> None:
    """F1: "a sofa, a rug and cushions" is the brief for the whole call. The
    first piece opens in their taste; each saved pick hands the model the next
    piece to offer, as a choice of two; "show me what I've selected" is the
    saved picks together (never a cross-category compare); "add them" adds
    every saved pick in one go, and the reply is only what the cart holds."""
    llm = _brief_llm()
    async with demo("fernhollow", llm) as rig:
        await rig.driver.start_session()
        brain = rig.brain
        assert isinstance(brain, FernhollowBrain)

        check_turn(
            rig,
            await rig.driver.user_says(
                "I'm doing up my living room. I want a sofa, a rug and a few cushions, in sand."
            ),
            units=2,
        )
        assert brain.wants == ["sofas", "rugs", "throw-pillows"]
        grid = rig.command("apply_filters")
        assert grid["filters"]["category"] == "sofas" and grid["filters"]["colours"] == list(SAND)
        brief = _last_result(llm, "update_brief")
        assert "sofa — not chosen yet; rug — not chosen yet; cushions — not chosen yet" in brief
        assert "entire room" not in brief, "they named their pieces: no whole-room offer"

        check_turn(rig, await rig.driver.user_says("I like the first one."), units=2)
        assert brain.shortlisted == [SOFA_ID]
        saved = _last_result(llm, "shortlist")
        assert "Shall we move on to the rug now, or see cushions that go with the sofa?" in saved

        check_turn(rig, await rig.driver.user_says("The rug now."), units=2)
        check_turn(rig, await rig.driver.user_says("That first rug."), units=2)
        assert brain.shortlisted == [SOFA_ID, RUG_ID]
        assert "Shall I show you cushions that go with the sofa?" in _last_result(llm, "shortlist")

        check_turn(rig, await rig.driver.user_says("Yes, cushions."), units=2)
        assert rig.command("show_goes_with")["anchor_id"] == SOFA_ID
        check_turn(rig, await rig.driver.user_says("The first cushion."), units=2)
        assert brain.shortlisted == [SOFA_ID, RUG_ID, CUSHION_ID]
        assert "every piece on their list is saved" in _last_result(llm, "shortlist")
        # The screen note carries the list with what is saved for each, every turn.
        assert f"sofa — saved: {CATALOG.products[SOFA_ID].title}" in _notes(rig)

        compares = rig.actions().count("show_compare")
        check_turn(rig, await rig.driver.user_says("Show me what I've selected."), units=3)
        assert rig.actions().count("show_compare") == compares, (
            "a sofa, a rug and a cushion compare nothing"
        )
        assert "different kinds of piece" in _last_result(llm, "compare")
        shown = rig.command("show_saved")
        assert shown["product_ids"] == [SOFA_ID, RUG_ID, CUSHION_ID]
        assert shown["title"] == "Your picks for the living room"

        check_turn(rig, await rig.driver.user_says("Add them to the cart."))
        cart = rig.command("cart_updated")
        assert sorted(line["product_id"] for line in cart["lines"]) == sorted(
            [SOFA_ID, RUG_ID, CUSHION_ID]
        ), "every saved pick goes in, in one call"
        assert sorted(pid for pid, _ in brain.cart) == sorted([SOFA_ID, RUG_ID, CUSHION_ID])


async def test_a_silent_action_is_followed_by_a_real_sentence() -> None:
    """F1/X4: a turn that only acted is not answered by a written two-word line
    ("Filtered.", "It's on the shortlist."): the model is asked once more, with
    tools off, and its sentence is what is heard."""
    from loguru import logger

    floor: list[str] = []
    sink = logger.add(
        lambda m: floor.append(m.record["message"]),
        level="WARNING",
        filter=lambda r: "the brain says" in r["message"],
    )
    llm = ScriptedGemini(
        {
            "Put it in my cart.": [
                call("add_to_cart", request={"product": SOFA_ID}),
                reply("I've added the sandstone sofa to your cart. Shall we look at rugs next?"),
            ]
        }
    )
    try:
        async with demo("fernhollow", llm) as rig:
            await rig.driver.start_session()
            turn = await rig.driver.user_says("Put it in my cart.")
            check_turn(rig, turn, units=1)
            assert turn.units[0].text.startswith("I've added the sandstone sofa")
            assert rig.command("cart_updated")["lines"][0]["product_id"] == SOFA_ID
    finally:
        logger.remove(sink)
    assert floor == [], f"the written floor spoke instead of the model: {floor}"


def _orders_llm() -> ScriptedGemini:
    return ScriptedGemini(
        {
            "Where's my bed frame?": [
                reply_and_call("Your bed frame order.", "track_order", order_number="FH-31207"),
                reply("It's packed and booked for its van. You can change the day or cancel it."),
            ],
            "Show me the available options.": [
                reply_and_call("Here are the days.", "change_delivery", order_number="FH-31207"),
                reply("Those are the days it can move to. Which suits you?"),
            ],
            "The evening one, the day after tomorrow... no wait, the Sunday evening.": [
                reply_and_call(
                    "Moving it.",
                    "change_delivery",
                    order_number="FH-31207",
                    slot="d3-evening",
                ),
                reply("Done."),
            ],
            "And the chair order, can I cancel that?": [
                reply_and_call("The chair order.", "cancel_order", order_number="FH-31188"),
                reply("It's already on the van, so it can't be cancelled now."),
            ],
            "Can it come earlier then?": [
                reply_and_call("I'll ask the driver.", "request_earlier", order_number="FH-31188"),
                reply("I've asked; it's a request, not a promise."),
            ],
            "Return the chairs from my old order.": [
                reply_and_call("That order.", "start_return", order_number="FH-20155"),
                reply("That one was delivered forty-one days ago, outside the thirty-day window."),
            ],
        }
    )


async def test_orders_act_by_status() -> None:
    """F8: one orders page; what an order allows depends on its status.
    Packed: the day picker opens with the days ("show me the options" opens
    it, the live bug) and a day is saved. On the way: no cancel, an earlier
    delivery is a request. Delivered outside the window: no return, honestly."""
    llm = _orders_llm()
    async with demo("fernhollow", llm) as rig:
        greeting = await rig.driver.start_session(init={"landing": "/orders"})
        assert greeting is not None and greeting.text == GREETINGS["orders"]  # type: ignore[union-attr]

        check_turn(rig, await rig.driver.user_says("Where's my bed frame?"), units=2)
        assert _stage_moves(rig)[-1]["move"] == "orders.open"
        where = _last_result(llm, "track_order")
        assert "packed" in where and "change the delivery day" in where and "cancel" in where

        check_turn(rig, await rig.driver.user_says("Show me the available options."), units=2)
        shown = _stage_moves(rig)[-1]
        assert (shown["move"], shown["args"]) == ("orders.show_slots", {"order_number": "FH-31207"})
        days = _last_result(llm, "change_delivery")
        assert "d3-evening" in days and "picker" in days

        check_turn(
            rig,
            await rig.driver.user_says(
                "The evening one, the day after tomorrow... no wait, the Sunday evening."
            ),
            units=2,
        )
        moved = _stage_moves(rig)[-1]
        assert (moved["move"], moved["args"]) == (
            "orders.reschedule",
            {"order_number": "FH-31207", "slot": "d3-evening"},
        )

        check_turn(
            rig, await rig.driver.user_says("And the chair order, can I cancel that?"), units=2
        )
        assert "orders.cancel" not in [m["move"] for m in _stage_moves(rig)]
        assert "cannot be cancelled" in _last_result(llm, "cancel_order")

        check_turn(rig, await rig.driver.user_says("Can it come earlier then?"))
        earlier = _stage_moves(rig)[-1]
        assert (earlier["move"], earlier["args"]) == (
            "orders.request_earlier",
            {"order_number": "FH-31188"},
        )
        assert "not a promise" in _last_result(llm, "request_earlier")

        check_turn(rig, await rig.driver.user_says("Return the chairs from my old order."), units=2)
        assert "orders.start_return" not in [m["move"] for m in _stage_moves(rig)]
        assert "outside the 30-day return window" in _last_result(llm, "start_return")


def _return_llm() -> ScriptedGemini:
    return ScriptedGemini(
        {
            "I'd like to return something from my living room order.": [
                reply_and_call("That order.", "start_return", order_number="FH-20377"),
                reply("Which items are going back: the runner or the cushions?"),
            ],
            "The cushions.": [
                reply_and_call(
                    "The cushions.", "fill_return", answers={"items": [{"product": "the cushions"}]}
                ),
                reply("How many of the two are going back?"),
            ],
            "Both of them.": [
                reply_and_call(
                    "Both.",
                    "fill_return",
                    answers={"items": [{"product": "cushion", "qty": 2}]},
                ),
                reply("Why are they going back?"),
            ],
            "It's unused and still in its packaging.": [
                reply_and_call(
                    "Unused, in its packaging.",
                    "fill_return",
                    answers={"condition": "unused_in_packaging"},
                ),
                reply("Would you like a refund, an exchange, or store credit?"),
            ],
            "A refund, and I'll drop it off.": [
                reply_and_call(
                    "A refund, dropped off.",
                    "fill_return",
                    answers={"resolution": "refund", "collection": "drop_off"},
                ),
                reply("Everything is filled in. Shall I submit the return?"),
            ],
        }
    )


async def test_a_return_is_filled_two_ways_one_answer_at_a_time() -> None:
    """F5/F8: a delivered order's return form opens on its items with nothing
    chosen; each answer is ticked the moment it is said (the item and its
    quantity included — the live bug); what the shopper taps by hand the brain
    hears with its value and carries on from; the form moves on by itself; the
    yes submits it. No order number typed, no email anywhere."""
    llm = _return_llm()
    async with demo("fernhollow", llm) as rig:
        await rig.driver.start_session(init={"landing": "/orders"})
        brain = rig.brain
        assert isinstance(brain, FernhollowBrain)

        check_turn(
            rig,
            await rig.driver.user_says("I'd like to return something from my living room order."),
            units=2,
        )
        opened = _stage_moves(rig)[-1]
        assert (opened["move"], opened["args"]) == (
            "orders.start_return",
            {"order_number": "FH-20377"},
        )
        started = _last_result(llm, "start_return")
        assert "nothing is chosen" in started and "email" not in started.lower()
        assert "Which items are going back" in started

        check_turn(rig, await rig.driver.user_says("The cushions."), units=2)
        assert [m["move"] for m in _stage_moves(rig)][-1] == "orders.start_return", (
            "two cushions were ordered: how many is asked before anything is ticked"
        )
        assert "How many of the 2" in _last_result(llm, "fill_return")

        check_turn(rig, await rig.driver.user_says("Both of them."), units=2)
        moves = _stage_moves(rig)
        assert [(m["move"], m["args"]) for m in moves[-2:]] == [
            (
                "returns.select_item",
                {"product_id": "textured-wool-cushion-in-pebble-grey", "qty": 2},
            ),
            ("returns.next_step", {}),
        ]
        assert "Why is it going back" in _last_result(llm, "fill_return")

        # The shopper taps the reason by hand: the brain hears it, with its value.
        await rig.driver.send_ui_event(
            "stage_event",
            {
                "name": "returns.field_filled",
                "by": "visitor",
                "data": {
                    "order_number": "FH-20377",
                    "field": "reason",
                    "value": "wrong_item",
                    "filled": ["items", "reason"],
                },
            },
        )
        await asyncio.sleep(0.1)
        assert brain.form["reason"] == "wrong_item"
        assert "set reason to received the wrong item by hand" in _notes(rig)
        assert "Is it unused and still in its packaging" in _notes(rig)

        check_turn(
            rig, await rig.driver.user_says("It's unused and still in its packaging."), units=2
        )
        check_turn(rig, await rig.driver.user_says("A refund, and I'll drop it off."), units=2)
        fills = [
            (m["args"].get("field"), m["args"].get("value"))
            for m in _stage_moves(rig)
            if m["move"] == "returns.fill"
        ]
        assert fills == [
            ("condition", "unused_in_packaging"),
            ("resolution", "refund"),
            ("collection", "drop_off"),
        ], "nothing is filled that was not said, and the reason they tapped is not sent again"
        assert "Shall I submit the return?" in _last_result(llm, "fill_return")
        assert [m["move"] for m in _stage_moves(rig)].count("returns.next_step") == 3
        await _answer(rig, _stage_moves(rig))

        yes = await rig.driver.user_says("Yes.")
        assert [u.text for u in yes.units] == ["Submitting it now."]
        submit = _stage_moves(rig)[-1]
        assert submit["move"] == "returns.submit"


def _gifts_llm() -> ScriptedGemini:
    return ScriptedGemini(
        {
            "It's for a colleague, a thank-you.": [
                reply_and_call(
                    "A thank-you for a colleague.",
                    "gift_edit",
                    request={"recipient": "colleague", "occasion": "thank_you"},
                ),
                reply("Do you have a budget in mind, or shall I not worry about it?"),
            ],
            "Don't worry about the budget.": [
                reply_and_call("No limit, then.", "gift_edit", request={"no_budget": True}),
                reply("Here's a short list."),
            ],
            "Add the second one.": reply_and_call(
                "Adding it.", "add_to_cart", request={"product": "the second one"}
            ),
        }
    )


async def test_gifts_ask_who_and_why_together_then_the_budget() -> None:
    """F7: nothing is set before she starts; one question for who and the
    occasion, then the budget question, which can be skipped — only then the
    short list."""
    llm = _gifts_llm()
    async with demo("fernhollow", llm) as rig:
        greeting = await rig.driver.start_session(init={"landing": "/gifts"})
        assert greeting is not None and "Who is it for, and what's the occasion?" in greeting.text  # type: ignore[union-attr]
        assert _stage_moves(rig) == [], "nothing is chosen before she starts"

        check_turn(rig, await rig.driver.user_says("It's for a colleague, a thank-you."), units=2)
        first = _stage_moves(rig)[-1]
        assert (first["move"], first["args"]) == (
            "gifts.set",
            {"recipient": "colleague", "occasion": "thank_you"},
        )
        assert "Do you have a budget in mind, or shall I not worry about it?" in _last_result(
            llm, "gift_edit"
        )

        check_turn(rig, await rig.driver.user_says("Don't worry about the budget."), units=2)
        budget = _stage_moves(rig)[-1]
        assert (budget["move"], budget["args"]) == ("gifts.set", {"budget": 0})
        picks = [x["product_id"] for x in stored_edits()["gifts"]["colleague|thank_you|0"]]
        listed = _last_result(llm, "gift_edit")
        assert "no budget limit" in listed
        for pid in picks:
            assert CATALOG.products[pid].title in listed

        check_turn(rig, await rig.driver.user_says("Add the second one."))
        assert rig.command("cart_updated")["lines"][0]["product_id"] == picks[1]
