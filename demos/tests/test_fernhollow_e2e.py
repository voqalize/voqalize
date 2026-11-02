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

from google.genai import types
from voqalize_demos.discovery import discover
from voqalize_demos.testing import Reply, ScriptedGemini, call, reply, reply_and_call

from voqalize.sdk.gemini import _needs_result_now

from ._harness import DemoRig, check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.fernhollow import engine as eng  # noqa: E402
from voqalize_demos._loaded.fernhollow.brain import FernhollowBrain  # noqa: E402
from voqalize_demos._loaded.fernhollow.catalog import CATALOG  # noqa: E402
from voqalize_demos._loaded.fernhollow.policies import policy_numbers  # noqa: E402
from voqalize_demos._loaded.fernhollow.prompt import GREETING  # noqa: E402

VOICE = "omnivoice/emily"
LANGUAGE = "en"

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
                "Shall I add all five? Just say yes or tap Add.",
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

    check_turn(rig, await rig.driver.user_says("Add the whole room to my cart."), units=1)
    # The shopper taps yes on the Add button; nothing blocks on it.
    await rig.driver.send_ui_event("confirm_result", {"confirmed": True, "by": "visitor"})
    await asyncio.sleep(0.1)
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
        assert actions[:4] == ["update_brief", "navigate", "update_brief", "show_room_set"], actions
        assert actions[4:] == [
            "swap_piece",
            "show_compare",
            "show_more_like",
            "show_goes_with",
            *(["swap_piece"] * (len(STRETCH.swaps) + (1 if STRETCH.upgrade else 0))),
            "show_savings",
            "confirm_add",
            "highlight",
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

        confirm = rig.command("confirm_add")
        assert [line["product_id"] for line in confirm["lines"]] == [
            p.product_id for p in STRETCH.room.pieces
        ]
        cart = rig.command("cart_updated")
        assert cart["total"] == STRETCH.room.total
        assert {line["product_id"] for line in cart["lines"]} == {
            p.product_id for p in STRETCH.room.pieces
        }

        finish = rig.command("suggest_finish")
        assert finish["product_id"] not in {line["product_id"] for line in cart["lines"]}
        assert finish["reason"]

        # The tap reached the model as context, ahead of the next words.
        last = " ".join(
            p.text or "" for c in llm.captured_contents[-2] for p in c.parts or [] if p.text
        )
        assert "tapped yes" in last


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
    assert "Nothing is in the cart until they say yes" in results["add_to_cart"]


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


async def test_a_spoken_yes_adds_after_the_confirmation() -> None:
    """The yes can be said instead of tapped — but only on a later turn than the
    confirmation, so the model cannot confirm on the shopper's behalf."""
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
                text="Shall I add all five?",
                calls=(
                    ("add_to_cart", {"request": {"what": "room"}}),
                    ("add_to_cart", {"request": {"what": "room", "confirmed_by_voice": True}}),
                ),
            ),
            "Yes please.": reply_and_call(
                "Done, they're in your cart.",
                "add_to_cart",
                request={"what": "room", "confirmed_by_voice": True},
            ),
        }
    )
    async with demo("fernhollow", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Build me a home office around two thousand.")
        await rig.driver.user_says("Add it all.")
        assert "cart_updated" not in rig.actions(), "confirmed in the same turn it asked"
        await rig.driver.user_says("Yes please.")
        assert rig.actions().count("cart_updated") == 1
        brain = rig.brain
        assert isinstance(brain, FernhollowBrain)
        assert brain.pending is None and len(brain.cart) == 5


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
    """The prompt has Emily speak with every call; when the model calls alone the
    brain says the landed line, with no second request."""
    llm = ScriptedGemini(
        {"Show me the returns policy.": call("store_policy", request={"topic": "returns"})}
    )
    async with demo("fernhollow", llm) as rig:
        await rig.driver.start_session()
        turn = await rig.driver.user_says("Show me the returns policy.")
        check_turn(rig, turn, units=1)
        assert rig.command("open_policy")["topic"] == "returns"
        assert len(llm.captured_contents) == 1


def test_marks_are_reads() -> None:
    """The mark, pinned tool by tool: the tools whose answer only the engine
    knows hold the turn; the rest say their line with the call."""
    brain = FernhollowBrain(client=ScriptedGemini({}))  # pyright: ignore[reportArgumentType]
    held = {tool.__name__ for tool in brain.tools if _needs_result_now(tool)}
    assert held == {
        "update_brief",
        "build_room",
        "swap_piece",
        "goes_with",
        "more_like",
        "compare",
        "edit_compare",
        "set_filters",
        "stretch_budget",
        "show",
        "suggest_finish",
        "find_order",
        "check_exchange",
        "resolve_product",
        "fill_checkout",
    }
    assert len(brain.tools) == 24


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


# ─── The returns desk ─────────────────────────────────────────────────────────


def _returns() -> ScriptedGemini:
    return ScriptedGemini(
        {
            "I'd like to return something from FH-20418.": [
                reply_and_call(
                    "Order FH-20418, coming up.",
                    "find_order",
                    request={"order_number": "FH-20418"},
                ),
                reply_and_call(
                    "All three pieces can go back — you're well inside the thirty days.",
                    "start_return",
                    request={"order_number": "FH-20418"},
                ),
            ],
            "Could I swap the chair for another finish?": [
                reply_and_call(
                    "The chair's other finish is below.",
                    "check_exchange",
                    request={"product": "desk chair"},
                ),
                reply("It also comes in walnut."),
            ],
            "And order FH-20155?": [
                reply_and_call(
                    "Order FH-20155, checking the dates.",
                    "find_order",
                    request={"order_number": "FH-20155"},
                ),
                reply(
                    "That one arrived forty-one days ago, so it's past our thirty-day window. "
                    "The care guide may help, and the team can talk it through."
                ),
            ],
        }
    )


async def test_the_returns_desk_answers_honestly() -> None:
    """FH-20418 is inside the window: every line eligible, and the form opens with
    the order in. FH-20155 is past it: the result says so with the days, gives
    the policy and no form opens."""
    llm = _returns()
    async with demo("fernhollow", llm) as rig:
        await rig.driver.start_session()
        check_turn(
            rig, await rig.driver.user_says("I'd like to return something from FH-20418."), units=2
        )
        found = _results(llm.captured_contents[-1])["find_order"]
        assert "3 of 3 lines can be returned" in found
        assert "24 days left in the 30-day window" in found
        assert "sam" not in found.lower() and "@" not in found, "personal data in a tool result"
        assert rig.command("navigate")["page"] == "returns/start?order=FH-20418"

        check_turn(
            rig, await rig.driver.user_says("Could I swap the chair for another finish?"), units=2
        )
        assert "Walnut" in _results(llm.captured_contents[-1])["check_exchange"]

        pages = len([c for c in rig.driver.ui_commands if c.get("command") == "navigate"])
        check_turn(rig, await rig.driver.user_says("And order FH-20155?"), units=2)
        late = _results(llm.captured_contents[-1])["find_order"]
        assert "0 of 1 lines can be returned" in late
        assert "delivered 41 days ago" in late and "30 days from delivery" in late
        assert "never promise an exception" in late
        assert len([c for c in rig.driver.ui_commands if c.get("command") == "navigate"]) == pages


def test_emily_never_opens_on_an_acknowledgement() -> None:
    """One acknowledgement, upstream: Voqalize's own ack covers the wait, so no
    line Emily says — the greeting, every scripted reply here, and every landed
    line the brain can speak in a silent turn — opens on one of her own."""
    import inspect

    from voqalize_demos._loaded.fernhollow import brain as fb
    from voqalize_demos._loaded.fernhollow.prompt import ACK_OPENER

    lines = [GREETING]
    for script in (_story(), _returns(), _form()):
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


def _form() -> ScriptedGemini:
    return ScriptedGemini(
        {
            "I need to return the desk from FH-20418.": [
                reply_and_call(
                    "Order FH-20418, coming up.",
                    "find_order",
                    request={"order_number": "FH-20418"},
                ),
                reply_and_call(
                    "The desk can go back — you're well inside the thirty days. What's the reason?",
                    "start_return",
                    request={"order_number": "FH-20418"},
                ),
            ],
            "It just doesn't suit the room, and it's still boxed.": reply(
                f"{{item: {DESK_LINE} | 1}} The desk goes on the return. "
                "{fill: reason | doesnt_suit_room} I'm putting down that it doesn't suit the room. "
                "{fill: condition | unused_in_packaging} And it's unused, in its packaging. "
                "{fill: email | sam@example.com} Refund or store credit?"
            ),
            "A refund, and pick it up on a weekday morning.": reply(
                "{fill: resolution | refund} A refund it is. "
                "{fill: collection | pickup} We'll collect it. "
                "{fill: pickup_window | weekday_morning} On a weekday morning. "
                "Check the review and press Submit return when you're happy."
            ),
            "submitted the return": reply(
                "Thanks — the refund goes to your original payment once the desk is back and checked."
            ),
        }
    )


def _cues(rig: DemoRig) -> list[dict[str, Any]]:
    return [
        dict(c.get("payload") or {})
        for c in rig.driver.ui_commands
        if c.get("command") == "stage_cue"
    ]


async def test_the_returns_form_fills_by_cue_and_the_shopper_submits() -> None:
    """FH-20418: the order is found eligible and the form opens with it; Emily's
    cues select the item and fill reason, condition, resolution and collection
    as she says them, the email too (a demo, CONTRACT v2). The shopper presses
    Submit return themselves; that act reaches Emily, and in the next quiet spell
    she thanks them in one line."""
    llm = _form()
    async with demo("fernhollow", llm) as rig:
        await rig.driver.start_session()
        check_turn(
            rig, await rig.driver.user_says("I need to return the desk from FH-20418."), units=2
        )
        assert rig.command("navigate")["page"] == "returns/start?order=FH-20418"

        turn = await rig.driver.user_says("It just doesn't suit the room, and it's still boxed.")
        check_turn(rig, turn, units=1)
        spoken = turn.units[0].text
        assert "{" not in spoken
        turn = await rig.driver.user_says("A refund, and pick it up on a weekday morning.")
        check_turn(rig, turn, units=1)

        cues = [(c["move"], c["args"]) for c in _cues(rig)]
        assert cues == [
            ("returns.select_item", [DESK_LINE, "1"]),
            ("returns.fill", ["reason", "doesnt_suit_room"]),
            ("returns.fill", ["condition", "unused_in_packaging"]),
            ("returns.fill", ["email", "sam@example.com"]),
            ("returns.fill", ["resolution", "refund"]),
            ("returns.fill", ["collection", "pickup"]),
            ("returns.fill", ["pickup_window", "weekday_morning"]),
        ], cues
        assert all(c["at"] for c in _cues(rig)), "a cue with no words to fire at"

        # The page answers every cue; a refused one would be told to the model.
        for c in _cues(rig):
            await rig.driver.send_ui_event(
                "stage_result",
                {
                    "call_ref": c["call_ref"],
                    "move": c["move"],
                    "outcome": "applied",
                    "detail": "set",
                },
            )
        # The shopper types their email and presses Submit return themselves.
        await rig.driver.send_ui_event(
            "stage_event",
            {
                "name": "returns.field_filled",
                "by": "visitor",
                "data": {"field": "email", "filled": ["order_number", "email"]},
            },
        )
        await rig.driver.send_ui_event(
            "stage_event",
            {
                "name": "returns.return_submitted",
                "by": "visitor",
                "data": {"reference": "RT-20418-1", "filled": ["order_number", "email"]},
            },
        )
        await asyncio.sleep(0.1)
        brain = rig.brain
        assert isinstance(brain, FernhollowBrain)
        assert brain._talk is not None  # pyright: ignore[reportPrivateUsage]
        idle = [
            r.config.idle for r in rig.driver.requests if getattr(r, "config", None) is not None
        ]
        assert any(i is not None and i.timeout_ms == 1500 for i in idle), (
            "the quiet spell was not shortened"
        )

        thanks = await rig.driver.user_idle()
        check_turn(rig, thanks, units=1)
        assert thanks.units[0].text.startswith("Thanks — the refund")
        last = " ".join(
            p.text or "" for c in llm.captured_contents[-1] for p in c.parts or [] if p.text
        )
        assert "submitted the return" in last and "thank them" in last


async def test_a_refused_cue_is_told_to_the_model() -> None:
    """A value the form does not take comes back refused with its options, and
    the model hears that — so it never says the field was set."""
    llm = ScriptedGemini(
        {
            "It's broken.": reply("{fill: reason | broken} I'm putting down that it's broken."),
            "So?": reply("The reason is set to arrived damaged."),
        }
    )
    async with demo("fernhollow", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("It's broken.")
        (cue,) = _cues(rig)
        await rig.driver.send_ui_event(
            "stage_result",
            {
                "call_ref": cue["call_ref"],
                "move": cue["move"],
                "outcome": "refused",
                "refused": [
                    {
                        "arg": "value",
                        "why": "not a reason",
                        "options": ["arrived_damaged", "changed_mind"],
                    }
                ],
            },
        )
        await asyncio.sleep(0.1)
        await rig.driver.user_says("So?")
        notes = " ".join(
            p.text or "" for c in llm.captured_contents[-1] for p in c.parts or [] if p.text
        )
        assert "did not land" in notes and "arrived_damaged" in notes


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
        assert rig.command("confirm_add")["lines"][0]["product_id"] == OAK_SOFAS[0]


DESK_ID = "modern-home-office-desk-with-chestnut-brown-finish"


async def test_checkout_fully_by_voice_with_the_yes() -> None:
    """Emily fills checkout from what the shopper says, reads the email and
    postcode back, asks before placing the order, and places it only on the
    shopper's yes in a later turn — with the authored delivery charge."""
    llm = ScriptedGemini(
        {
            "Email's sam dot rivera at example dot com, I'm Sam Rivera.": [
                reply_and_call(
                    "Sam Rivera, noted.",
                    "fill_checkout",
                    fields={
                        "email": "sam dot rivera at example dot com",
                        "first_name": "Sam",
                        "last_name": "Rivera",
                    },
                ),
                reply("That's s a m dot r i v e r a, at example dot com. And the address?"),
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

        await rig.driver.user_says("Email's sam dot rivera at example dot com, I'm Sam Rivera.")
        first = _results(llm.captured_contents[-1])["fill_checkout"]
        assert "s a m dot r i v e r a, at example dot com" in first
        fills = [
            c["payload"] for c in rig.driver.ui_commands if c.get("command") == "checkout_fill"
        ]
        assert {"field": "email", "value": "sam.rivera@example.com"} in fills

        await rig.driver.user_says("12 Elm Street, Portland, 97201, United States.")
        second = _results(llm.captured_contents[-1])
        assert "9 7 2 0 1" in second["fill_checkout"]
        assert "nothing — offer the review step" in second["fill_checkout"]
        assert "NOT DONE" in second["place_order"], "a yes it was never asked for placed an order"
        assert "order_placed" not in rig.actions()

        await rig.driver.user_says("Looks right.")
        confirm = rig.command("confirm_place_order")
        assert confirm["total"] == 548.99  # $499.99 is not over $500: the flat $49 applies
        assert "order_placed" not in rig.actions()

        await rig.driver.user_says("Yes, place it.")
        placed = rig.command("order_placed")
        assert placed["order_number"] == "FH-30001" and placed["total"] == 548.99
        assert brain.cart == {} and brain.pending_order is None
