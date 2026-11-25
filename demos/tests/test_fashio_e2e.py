"""Fashio, end to end: the real brain on a real socket, only the model scripted.

One agent, six jobs, one per landing page: the shopping assistant narrows the
listing (the filters as one Stage move), rings a product with a cue and adds to
the bag only on a spoken yes; the size advisor runs the shared fit rule and
offers the nearest size in stock; the gift finder asks who and the occasion, then
the budget, then shows a shortlist with reasons; order tracking says the status
from the data and never changes a placed order; returns check the 7-day window
and the fragrance rule, tick "unused with tags" only on the shopper's word and
never submit; the kiosk searches the whole catalogue and shows a QR code. The
character, voice and languages come from ``demos/fashio/persona.json``. "Today" is
fixed (Asia/Kolkata) so the order dates are stable.

Run: ``cd demos && uv run pytest tests/test_fashio_e2e.py``
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedOpenAI, call, reply, reply_and_call, tool_results_of

from voqalize.conformance import VoqalizeDriver
from voqalize.sdk.openai import _input as _openai_input  # pyright: ignore[reportPrivateUsage]
from voqalize.sdk.wire import ConfigureFrame

from ._harness import DemoRig, check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.fashio import fashio as f  # noqa: E402
from voqalize_demos._loaded.fashio.brain import REJOIN, FashioBrain  # noqa: E402
from voqalize_demos._loaded.fashio.lines import GREETING  # noqa: E402
from voqalize_demos._loaded.fashio.persona import PERSONA  # noqa: E402
from voqalize_demos._loaded.fashio.spoken import (  # noqa: E402
    amounts_note,
    implausible,
    parse_amounts,
    speak_text,
)

TODAY = date(2026, 11, 24)


@pytest.fixture(autouse=True)
def _fixed_day_and_no_call_carried() -> Iterator[None]:
    """Today is fixed, so the orders' offsets give stable dates; and every test
    opens the same session id, so the redial store is cleared around each test."""
    f.set_today(TODAY)
    REJOIN.clear()
    yield
    REJOIN.clear()
    f.set_today(None)


def _moves(rig: DemoRig | VoqalizeDriver, move: str | None = None) -> list[dict[str, Any]]:
    driver = rig if isinstance(rig, VoqalizeDriver) else rig.driver
    out = [
        dict(c.get("payload") or {}) for c in driver.ui_commands if c.get("command") == "stage_move"
    ]
    return [m for m in out if move is None or m["move"] == move]


def _cues(rig: DemoRig) -> list[dict[str, Any]]:
    return [
        dict(c.get("payload") or {})
        for c in rig.driver.ui_commands
        if c.get("command") == "stage_cue"
    ]


async def _answer(rig: DemoRig, move: str, outcome: str = "applied") -> None:
    for m in _moves(rig, move):
        await rig.driver.send_ui_event(
            "stage_result",
            {"call_ref": m["call_ref"], "move": move, "outcome": outcome, "detail": "done"},
        )
    await asyncio.sleep(0.1)


async def _event(
    rig: DemoRig | VoqalizeDriver, name: str, data: dict[str, Any], by: str = "visitor"
) -> None:
    driver = rig if isinstance(rig, VoqalizeDriver) else rig.driver
    await driver.send_ui_event("stage_event", {"name": name, "by": by, "data": data})
    await asyncio.sleep(0.1)


def _brain(rig: DemoRig) -> FashioBrain:
    brain = rig.brain
    assert isinstance(brain, FashioBrain)
    return brain


def _filed(rig: DemoRig, name: str) -> list[str]:
    return tool_results_of(_openai_input(list(_brain(rig)._history)), name)  # pyright: ignore[reportPrivateUsage]


def _inputs(llm: ScriptedOpenAI, i: int = -1) -> str:
    return json.dumps(llm.captured_inputs[i], ensure_ascii=False)


# ─── Persona, languages and the job per landing page ──────────────────────────


async def test_the_shopping_assistant_greets_in_the_persona_voice() -> None:
    async with demo("fashio", ScriptedOpenAI()) as rig:
        greeting = await rig.driver.start_session(
            init={"surface": "fashio-web", "page": "/", "lang": "en"}
        )
        check_greeting(rig, greeting)
        check_voice_pair(rig, voice=PERSONA.voices["en"], language="en")
        assert greeting is not None and PERSONA.name in greeting.text
        assert "shopping assistant" in greeting.text and "who is it for" in greeting.text
        assert _brain(rig).job == "shopping"


async def test_a_hindi_call_moves_both_legs_and_greets_in_hindi() -> None:
    async with demo("fashio", ScriptedOpenAI()) as rig:
        greeting = await rig.driver.start_session(
            init={"page": "/demos/fashio/gifts", "lang": "hi"}
        )
        check_greeting(rig, greeting)
        check_voice_pair(rig, voice=PERSONA.voices["hi"], language="hi")
        assert greeting is not None and "नमस्ते" in greeting.text and PERSONA.name in greeting.text
        assert "किसके लिए" in greeting.text and "मौका" in greeting.text
        assert _brain(rig).job == "gifts"


@pytest.mark.parametrize(
    ("page", "job", "words"),
    [
        ("/", "shopping", "shopping for"),
        ("/shop/women/kurtas", "shopping", "shopping for"),
        ("/p/7421", "fit", "usually wear"),
        ("/p/23276", "fit", "one size"),
        ("/gifts", "gifts", "Who is the gift for, and what's the occasion?"),
        ("/orders", "orders", "Hi Neha"),
        ("/returns", "returns", "return something"),
        ("/returns?order=FSH-48213", "returns", "Which item from this order"),
        ("/kiosk", "kiosk", "whole catalogue"),
        ("/p/99999999", "shopping", "shopping for"),
    ],
)
async def test_the_landing_page_picks_the_job(page: str, job: str, words: str) -> None:
    async with demo("fashio", ScriptedOpenAI()) as rig:
        greeting = await rig.driver.start_session(init={"page": page, "lang": "en"})
        assert greeting is not None and words in greeting.text
        assert _brain(rig).job == job


async def test_moving_to_a_product_page_makes_it_the_size_advisor() -> None:
    llm = ScriptedOpenAI({"Is this one true to size?": reply("Tell me your usual size.")})
    async with demo("fashio", llm) as rig:
        await rig.driver.start_session(init={"page": "/shop"})
        await _event(
            rig, "screen.viewed", {"path": "/p/6980", "page": "product", "product_id": "6980"}
        )
        assert _brain(rig).job == "fit" and _brain(rig).product_id == 6980
        await rig.driver.user_says("Is this one true to size?")
        seen = _inputs(llm)
        assert "your job here is size and fit" in seen
        assert "Product in front: 6980" in seen


async def test_hindi_asked_mid_call_moves_both_legs_and_the_toggle() -> None:
    llm = ScriptedOpenAI(
        {
            "Hindi mein baat karein?": reply_and_call(
                "ज़रूर, अब हिंदी में बात करते हैं।", "set_language", language="hindi"
            )
        }
    )
    async with demo("fashio", llm) as rig:
        await rig.driver.start_session(init={"page": "/"})
        check_turn(rig, await rig.driver.user_says("Hindi mein baat karein?"))
        await asyncio.sleep(0.1)
        check_voice_pair(rig, voice=PERSONA.voices["hi"], language="hi")
        assert rig.command("language_changed") == {"language": "hi"}


async def test_the_tile_toggle_switches_mid_call_and_the_next_lines_are_hindi() -> None:
    ask = "Kurtas for women under 1500."
    llm = ScriptedOpenAI(
        {
            ask: reply_and_call(
                "देखता हूँ।", "search_products", dept="women", types=["kurtas"], price_max=1500
            )
        }
    )
    async with demo("fashio", llm) as rig:
        await rig.driver.start_session(init={"page": "/", "lang": "en"})
        await rig.driver.send_ui_event("language_requested", {"language": "hi", "by": "visitor"})
        await asyncio.sleep(0.1)
        check_voice_pair(rig, voice=PERSONA.voices["hi"], language="hi")
        assert rig.command("language_changed") == {"language": "hi"}
        said = await rig.driver.user_idle()
        assert said.text.startswith("ज़रूर")
        turn = await rig.driver.user_says(ask)
        assert "आपके हिसाब से" in turn.text and "पीस हैं" in turn.text
        assert "pieces fit" not in turn.text
        assert "short, warm, conversational Hindi" in llm.captured_instructions[-1]


# ─── Shopping ─────────────────────────────────────────────────────────────────

_ASK = "A kurta for my sister's mehendi under 2,000, she's an M."
_ASK_ARGS: dict[str, Any] = {
    "dept": "women",
    "types": ["kurtas"],
    "sizes": ["M"],
    "price_max": 2000,
    "usage": ["Ethnic"],
}


def _best() -> list[dict[str, Any]]:
    return f.search(
        f.Search(dept="women", types=["kurtas"], sizes=["M"], price_max=2000, usage=["Ethnic"])
    )


async def test_a_whole_request_filters_names_the_best_and_adds_only_on_yes() -> None:
    found = _best()
    best = found[0]
    llm = ScriptedOpenAI(
        {
            _ASK: reply_and_call("Let me look.", "search_products", **_ASK_ARGS),
            "Add the first one in M.": call("propose_add", product_id=str(best["id"]), size="m"),
        }
    )
    async with demo("fashio", llm) as rig:
        await rig.driver.start_session(init={"page": "/", "lang": "en"})
        turn = await rig.driver.user_says(_ASK)
        check_turn(rig, turn)
        (move,) = _moves(rig, "shop.filter")
        args = move["args"]
        assert args["dept"] == "women" and args["types"] == ["kurtas"]
        assert args["sizes"] == ["M"] and args["price_max"] == 2000 and args["usage"] == ["Ethnic"]
        assert args["colours"] is None and args["price_min"] is None
        # The count and the pick are the page's rule.
        assert f"{len(found)} pieces fit" in turn.text
        assert f.short_name(best) in turn.text and f.inr(best["price"]) in turn.text
        assert len(llm.requests) == 1, "the pitch is the brain's line: one model request"
        cues = [c for c in _cues(rig) if c["move"] == "shop.show"]
        assert cues[0]["args"] == [str(best["id"])]
        assert "{" not in turn.text
        (result,) = _filed(rig, "search_products")
        assert f"The screen shows {len(found)} products" in result and str(best["id"]) in result
        await _answer(rig, "shop.filter")

        offer = await rig.driver.user_says("Add the first one in M.")
        assert "Shall I add" in offer.text and "size M" in offer.text
        assert not _moves(rig, "bag.add"), "nothing in the bag before the yes"
        requests = len(llm.requests)

        yes = await rig.driver.user_says("Yes please.")
        check_turn(rig, yes, units=1)
        assert yes.text.startswith("Adding the")
        (add,) = _moves(rig, "bag.add")
        assert add["args"] == {"product_id": str(best["id"]), "size": "M", "qty": 1}
        assert len(llm.requests) == requests, "the yes needed no model call"
        await _answer(rig, "bag.add")
        done = await rig.driver.user_idle()
        assert done.text.startswith("It's in your bag.")


async def test_no_bag_add_without_a_yes() -> None:
    llm = ScriptedOpenAI(
        {
            "Add the blue kurta in L.": call("propose_add", product_id="7421", size="L"),
            "Hmm, actually no.": reply("No problem."),
        }
    )
    async with demo("fashio", llm) as rig:
        await rig.driver.start_session(init={"page": "/shop"})
        await rig.driver.user_says("Add the blue kurta in L.")
        assert _brain(rig).pending is not None
        await rig.driver.user_says("Hmm, actually no.")
        assert not _moves(rig, "bag.add")
        assert _brain(rig).pending is None
        assert "said no to what you offered" in _inputs(llm)


async def test_an_out_of_stock_size_offers_the_nearest_in_stock() -> None:
    llm = ScriptedOpenAI(
        {"The grey check shirt in XL.": call("propose_add", product_id="6980", size="XL")}
    )
    async with demo("fashio", llm) as rig:
        await rig.driver.start_session(init={"page": "/shop"})
        turn = await rig.driver.user_says("The grey check shirt in XL.")
        assert "Size XL is out of stock" in turn.text and "XXL is in stock" in turn.text
        pending = _brain(rig).pending
        assert pending is not None and pending.size == "XXL"
        yes = await rig.driver.user_says("Okay, the XXL then.")
        assert _moves(rig, "bag.add")[0]["args"]["size"] == "XXL"
        assert "XXL" in yes.text


async def test_what_the_shopper_ticks_is_the_search_the_brain_keeps() -> None:
    llm = ScriptedOpenAI({"Anything in blue?": reply("Let me look.")})
    async with demo("fashio", llm) as rig:
        await rig.driver.start_session(init={"page": "/shop"})
        await _event(
            rig,
            "shop.changed",
            {
                "summary": "Women, Kurtas",
                "count": 400,
                "dept": "women",
                "types": ["kurtas"],
                "ids": ["7421"],
            },
        )
        assert _brain(rig).search.dept == "women" and _brain(rig).search.types == ["kurtas"]
        await rig.driver.user_says("Anything in blue?")
        seen = _inputs(llm)
        assert "The visitor changed the search: Women, Kurtas" in seen
        assert "Search: Women, Kurtas" in seen


async def test_nothing_fitting_names_the_nearest_and_keeps_the_budget() -> None:
    """Nothing under ₹250: the answer names the nearest piece and asks; the screen and
    the next search keep the budget they said."""
    assert not f.search(f.Search(types=["kurtas"], price_max=250))
    cheapest = f.sort_products(f.search(f.Search(types=["kurtas"])), "price_asc")[0]
    llm = ScriptedOpenAI(
        {
            "Kurtas under 250.": reply_and_call(
                "Let me look.", "search_products", types=["kurtas"], price_max=250
            )
        }
    )
    async with demo("fashio", llm) as rig:
        await rig.driver.start_session(init={"page": "/shop"})
        turn = await rig.driver.user_says("Kurtas under 250.")
        (move,) = _moves(rig, "shop.filter")
        assert move["args"]["price_max"] == 250, "the screen shows the budget they said"
        assert "Nothing fits under ₹250 yet." in turn.text
        assert f.short_name(cheapest) in turn.text and "raise the budget" in turn.text
        (said,) = _filed(rig, "search_products")
        assert "not on screen" in said and str(cheapest["id"]) in said
        assert _brain(rig).search.price_max == 250 and _brain(rig).results == []


async def test_opening_a_product_describes_it_and_asks_the_size() -> None:
    llm = ScriptedOpenAI(
        {
            "Show me the blue kurta.": reply_and_call(
                "Opening it.", "open_product", product_id="7421"
            )
        }
    )
    async with demo("fashio", llm) as rig:
        await rig.driver.start_session(init={"page": "/shop"})
        turn = await rig.driver.user_says("Show me the blue kurta.")
        assert _moves(rig, "site.go")[0]["args"] == {"path": "/p/7421"}
        assert "Here's the" in turn.text and "₹999" in turn.text
        assert "What size do you usually wear?" in turn.text
        assert _brain(rig).job == "fit" and _brain(rig).product_id == 7421


async def test_compare_names_the_better_buy() -> None:
    llm = ScriptedOpenAI(
        {"Compare those two.": call("compare_products", product_ids=["18894", "7421"])}
    )
    async with demo("fashio", llm) as rig:
        await rig.driver.start_session(init={"page": "/shop"})
        turn = await rig.driver.user_says("Compare those two.")
        assert _moves(rig, "compare.show")[0]["args"] == {"ids": ["18894", "7421"]}
        assert "better buy" in turn.text and "50% off" in turn.text
        assert "Which one do you like?" in turn.text


async def test_checkout_rings_sections_and_never_asks_for_details() -> None:
    llm = ScriptedOpenAI(
        {
            "Take me to checkout.": call("guide_checkout", field="contact"),
            "My number is 98765 43210.": reply("Please type it in the box."),
        }
    )
    async with demo("fashio", llm) as rig:
        await rig.driver.start_session(init={"page": "/bag"})
        await _event(rig, "bag.changed", {"count": 1, "total": 999, "lines": ["7421|M|1|0"]})
        turn = await rig.driver.user_says("Take me to checkout.")
        assert _moves(rig, "site.go")[0]["args"] == {"path": "/checkout"}
        assert _moves(rig, "checkout.focus")[0]["args"] == {"field": "contact"}
        assert "Type your name and phone number" in turn.text
        await rig.driver.user_says("My number is 98765 43210.")
        assert "They said a phone number aloud" in _inputs(llm)


async def test_the_order_the_shopper_placed_is_thanked_by_name() -> None:
    async with demo("fashio", ScriptedOpenAI()) as rig:
        await rig.driver.start_session(init={"page": "/checkout"})
        await _event(rig, "order.placed", {"order_id": "FSH-49001", "total": 999})
        said = await rig.driver.user_idle()
        assert said.text.startswith("Thank you, Neha!") and "FSH-49001" in said.text
        assert "Sunday, 29 November" in said.text  # today + 5 days, delivery days_max
        assert _brain(rig).order_status["FSH-49001"] == "placed"


# ─── Size and fit ─────────────────────────────────────────────────────────────


async def test_the_fit_rule_picks_the_size_and_says_why() -> None:
    p = f.product(3078)
    assert p is not None and f.cut_of(p) == "slim"
    llm = ScriptedOpenAI(
        {
            "I'm usually an M and I like it relaxed.": reply_and_call(
                "Got it.", "size_advice", usual_size="M", fit="relaxed"
            )
        }
    )
    async with demo("fashio", llm) as rig:
        await rig.driver.start_session(init={"page": "/p/3078"})
        turn = await rig.driver.user_says("I'm usually an M and I like it relaxed.")
        (fill,) = _moves(rig, "fit.fill")
        assert fill["args"] == {"product_id": "3078", "usual_size": "M", "fit": "relaxed"}
        (rec,) = _moves(rig, "fit.recommend")
        expected = f.recommend(p, "M", "relaxed")
        assert expected is not None and expected.size == "L" and expected.wanted is None
        assert rec["args"]["size"] == "L" and "wanted" not in rec["args"]
        assert "one size up" in rec["args"]["reason"]
        assert "Go for L." in turn.text and "Shall I add the L" in turn.text
        assert len(llm.requests) == 1


async def test_an_out_of_stock_fit_names_the_alternative_and_adds_on_yes() -> None:
    p = f.product(6980)
    assert p is not None
    llm = ScriptedOpenAI(
        {"I wear XL, regular fit.": call("size_advice", usual_size="XL", fit="regular")}
    )
    async with demo("fashio", llm) as rig:
        await rig.driver.start_session(init={"page": "/p/6980"})
        turn = await rig.driver.user_says("I wear XL, regular fit.")
        (rec,) = _moves(rig, "fit.recommend")
        expected = f.recommend(p, "XL", "regular")
        assert expected is not None and (expected.size, expected.wanted) == ("XXL", "XL")
        assert rec["args"]["size"] == "XXL" and rec["args"]["wanted"] == "XL"
        assert "Your size would be XL, but it's out of stock" in turn.text
        assert "XXL is the nearest in stock" in turn.text
        await rig.driver.user_says("Yes, add it.")
        assert _moves(rig, "bag.add")[0]["args"] == {"product_id": "6980", "size": "XXL", "qty": 1}


async def test_the_size_advisor_asks_the_usual_size_first() -> None:
    llm = ScriptedOpenAI({"Which size should I take?": call("size_advice")})
    async with demo("fashio", llm) as rig:
        await rig.driver.start_session(init={"page": "/p/7421"})
        turn = await rig.driver.user_says("Which size should I take?")
        assert not _moves(rig, "fit.recommend")
        assert "What size do you usually wear" in turn.text


async def test_the_size_chart_reads_the_row() -> None:
    llm = ScriptedOpenAI({"What are the measurements for M?": call("size_chart", size="M")})
    async with demo("fashio", llm) as rig:
        await rig.driver.start_session(init={"page": "/p/7421"})
        turn = await rig.driver.user_says("What are the measurements for M?")
        assert _moves(rig, "size_chart.open")[0]["args"] == {"product_id": "7421", "size": "M"}
        assert "bust 36, waist 30 and hip 39 inches" in turn.text


def test_the_page_and_the_brain_share_one_fit_rule() -> None:
    """CONTRACT.md, "Fit": a bare number is UK n for shoes; letter to waist by the
    gender's chart; an out-of-stock wanted size goes to the nearest, ties larger."""
    heels = f.product(14448)  # UK 4, UK 5 (0), UK 6
    jeans = f.product(11339)  # waist 28 (0) .. 40, regular fit
    assert heels is not None and jeans is not None
    a = f.recommend(heels, "5")
    assert a is not None and (a.size, a.wanted) == ("UK 6", "UK 5"), "a tie goes to the larger"
    b = f.recommend(jeans, "L")
    assert b is not None and (b.base, b.size) == ("34", "34")
    tall = f.recommend(jeans, "32", "regular", 188)
    assert tall is not None and (tall.size, tall.why) == ("34", "tall_up")
    assert f.recommend(f.product(23276) or {}, "M") is None  # one size


# ─── Gifts ────────────────────────────────────────────────────────────────────


async def test_the_gift_finder_asks_then_shows_a_shortlist_in_budget() -> None:
    llm = ScriptedOpenAI(
        {
            "It's for my sister, for Raksha Bandhan.": reply_and_call(
                "Lovely.", "gift_brief", recipient="sister", occasion="Raksha Bandhan"
            ),
            "Up to 2k.": call("gift_brief", budget_max=2000),
        }
    )
    async with demo("fashio", llm) as rig:
        await rig.driver.start_session(init={"page": "/gifts"})
        first = await rig.driver.user_says("It's for my sister, for Raksha Bandhan.")
        (brief,) = _moves(rig, "gifts.brief")
        assert brief["args"] == {"recipient": "Sister", "occasion": "Raksha Bandhan"}
        assert "Do you have a budget in mind, or shall I not worry about it?" in first.text
        assert not _moves(rig, "gifts.show")
        await _answer(rig, "gifts.brief")

        second = await rig.driver.user_says("Up to 2k.")
        assert "'2k' = 2000 rupees" in _inputs(llm)
        (show,) = _moves(rig, "gifts.show")
        picks = f.pick_gifts(
            f.GiftBrief(recipient="Sister", occasion="Raksha Bandhan", budget_max=2000)
        )
        assert show["args"]["ids"] == [str(p["id"]) for p in picks]
        assert len(show["args"]["reasons"]) == len(picks) >= 3
        for i in show["args"]["ids"]:
            p = f.product(i)
            assert p is not None and p["price"] <= 2000 and p["gender"] in ("women", "unisex")
        assert f"Here are {len(picks)} ideas." in second.text
        assert f.short_name(picks[0]) in second.text
        cues = [c["args"] for c in _cues(rig) if c["move"] == "shop.show"]
        assert [str(picks[0]["id"])] in cues


async def test_a_gift_with_no_limit_goes_straight_to_ideas() -> None:
    """F11: "a birthday gift for a friend, no limit" ended the Fernhollow call."""
    llm = ScriptedOpenAI(
        {
            "A birthday gift for a friend, no limit.": call(
                "gift_brief", recipient="friend", occasion="birthday", no_budget=True
            )
        }
    )
    async with demo("fashio", llm) as rig:
        await rig.driver.start_session(init={"page": "/gifts"})
        turn = await rig.driver.user_says("A birthday gift for a friend, no limit.")
        check_turn(rig, turn)
        (brief,) = _moves(rig, "gifts.brief")
        assert brief["args"]["budget_max"] == 0
        (show,) = _moves(rig, "gifts.show")
        assert len(show["args"]["ids"]) == 6
        assert "ideas" in turn.text


async def test_a_gift_note_is_read_back_once_and_set_on_yes() -> None:
    note = "Happy Rakhi, Didi!"
    llm = ScriptedOpenAI(
        {
            "Gift wrap the kurta with a note saying Happy Rakhi Didi.": call(
                "gift_wrap", product_id="7421", note=note
            )
        }
    )
    async with demo("fashio", llm) as rig:
        await rig.driver.start_session(init={"page": "/bag"})
        await _event(rig, "bag.changed", {"count": 1, "total": 999, "lines": ["7421|M|1|0"]})
        turn = await rig.driver.user_says(
            "Gift wrap the kurta with a note saying Happy Rakhi Didi."
        )
        assert f'The note will read: "{note}"' in turn.text
        assert not _moves(rig, "bag.gift")
        await rig.driver.user_says("Yes.")
        (gift,) = _moves(rig, "bag.gift")
        assert gift["args"] == {"product_id": "7421", "size": "M", "on": True, "note": note}


# ─── Orders ───────────────────────────────────────────────────────────────────


async def test_a_shipped_order_says_its_courier_and_date() -> None:
    llm = ScriptedOpenAI({"Where is order 48602?": call("find_order", order_id="48602")})
    async with demo("fashio", llm) as rig:
        await rig.driver.start_session(init={"page": "/orders"})
        turn = await rig.driver.user_says("Where is order 48602?")
        assert _moves(rig, "orders.open")[0]["args"] == {"order_id": "FSH-48602"}
        assert "Order FSH-48602 has shipped with BlueRoute Express" in turn.text
        assert "Thursday, 26 November" in turn.text  # today + 2, from the data
        (said,) = _filed(rig, "find_order")
        assert "AWB 7741 2096 5530" in said


async def test_with_no_number_the_orders_on_the_way_are_named() -> None:
    llm = ScriptedOpenAI({"Where's my order?": call("find_order")})
    async with demo("fashio", llm) as rig:
        await rig.driver.start_session(init={"page": "/orders"})
        turn = await rig.driver.user_says("Where's my order?")
        assert "You have 3 orders on the way" in turn.text
        assert not _moves(rig, "orders.open")


async def test_a_packed_order_opens_the_cancel_dialog_and_a_shipped_one_is_refused() -> None:
    llm = ScriptedOpenAI(
        {
            "Cancel order 48711.": call("cancel_order", order_id="FSH-48711"),
            "And cancel 48602 too.": call("cancel_order", order_id="FSH-48602"),
        }
    )
    async with demo("fashio", llm) as rig:
        await rig.driver.start_session(init={"page": "/orders"})
        turn = await rig.driver.user_says("Cancel order 48711.")
        assert _moves(rig, "orders.cancel_open")[0]["args"] == {"order_id": "FSH-48711"}
        assert "Press Cancel order to confirm" in turn.text and "UPI" in turn.text
        refused = await rig.driver.user_says("And cancel 48602 too.")
        assert len(_moves(rig, "orders.cancel_open")) == 1
        assert "already shipped, so it can't be cancelled" in refused.text
        assert "return it within 7 days" in refused.text
        await _event(rig, "order.cancelled", {"order_id": "FSH-48711"})
        done = await rig.driver.user_idle()
        assert done.text.startswith("Done, Neha, order FSH-48711 is cancelled.")


async def test_an_address_change_is_refused_with_the_policy() -> None:
    llm = ScriptedOpenAI(
        {
            "Can I change the delivery address for 48711?": call(
                "delivery_change", order_id="FSH-48711", what="address"
            ),
            "Can I get 48602 earlier?": call("delivery_change", order_id="FSH-48602", what="date"),
        }
    )
    async with demo("fashio", llm) as rig:
        await rig.driver.start_session(init={"page": "/orders"})
        turn = await rig.driver.user_says("Can I change the delivery address for 48711?")
        assert "its delivery address can't be changed" in turn.text
        assert "reorder with the new address" in turn.text
        (said,) = _filed(rig, "delivery_change")
        assert f.POLICY["changes"]["summary"] in said
        assert not _moves(rig, "orders.cancel_open")
        await rig.driver.user_says("Yes, do that.")
        assert _moves(rig, "orders.cancel_open")[0]["args"] == {"order_id": "FSH-48711"}
        shipped = await rig.driver.user_says("Can I get 48602 earlier?")
        assert "already shipped" in shipped.text and "Thursday, 26 November" in shipped.text


# ─── Returns ──────────────────────────────────────────────────────────────────


async def test_an_eligible_return_is_filled_and_never_submitted() -> None:
    llm = ScriptedOpenAI(
        {
            "I want to return the kurta from order 48213.": call(
                "start_return", order_id="FSH-48213", product_id="7421"
            ),
            "It's too small.": call("return_details", reason="size_small"),
        }
    )
    async with demo("fashio", llm) as rig:
        await rig.driver.start_session(init={"page": "/returns"})
        first = await rig.driver.user_says("I want to return the kurta from order 48213.")
        assert not _moves(rig, "site.go"), "already on /returns: the form opens in place"
        assert _moves(rig, "returns.fill")[0]["args"] == {
            "order_id": "FSH-48213",
            "product_id": "7421",
        }
        assert "You have 4 days left" in first.text and "reason" in first.text

        second = await rig.driver.user_says("It's too small.")
        fill = _moves(rig, "returns.fill")[-1]["args"]
        assert fill == {"order_id": "FSH-48213", "product_id": "7421", "reason": "size_small"}
        assert "unused, with its original tags still on?" in second.text
        requests = len(llm.requests)

        third = await rig.driver.user_says("Yes, it's unused and the tags are on.")
        ticked = _moves(rig, "returns.fill")[-1]["args"]
        assert ticked["unused"] is True and ticked["tags"] is True
        assert "press Submit return" in third.text
        assert len(llm.requests) == requests
        assert not [m for m in _moves(rig) if "submit" in json.dumps(m).lower()], "never submits"

        await _event(
            rig,
            "return.submitted",
            {"order_id": "FSH-48213", "reference": f.return_ref("FSH-48213", 7421)},
        )
        done = await rig.driver.user_idle()
        assert done.text.startswith("Done, Neha, your return is in.")
        assert "FSH-48213|7421" in _brain(rig).returned


async def test_a_used_item_is_not_ticked() -> None:
    llm = ScriptedOpenAI(
        {
            "Return the kurta from 48213, it's too big.": call(
                "return_details", order_id="FSH-48213", product_id="7421", reason="size_large"
            )
        }
    )
    async with demo("fashio", llm) as rig:
        await rig.driver.start_session(init={"page": "/returns"})
        await rig.driver.user_says("Return the kurta from 48213, it's too big.")
        turn = await rig.driver.user_says("Well, I wore it once and washed it.")
        assert "only unused items" in turn.text
        assert not any(m["args"].get("unused") for m in _moves(rig, "returns.fill"))


async def test_a_return_after_eleven_days_is_refused_with_the_dates() -> None:
    llm = ScriptedOpenAI(
        {"Return the shoes from 47920.": call("start_return", order_id="FSH-47920")}
    )
    async with demo("fashio", llm) as rig:
        await rig.driver.start_session(init={"page": "/returns"})
        turn = await rig.driver.user_says("Return the shoes from 47920.")
        assert "delivered on Friday, 13 November" in turn.text
        assert "closed on Friday, 20 November" in turn.text
        assert not _moves(rig, "returns.fill")


async def test_a_fragrance_is_refused_and_the_other_item_offered() -> None:
    llm = ScriptedOpenAI(
        {
            "Return the perfume from 48090.": call(
                "start_return", order_id="FSH-48090", product_id="36940"
            )
        }
    )
    async with demo("fashio", llm) as rig:
        await rig.driver.start_session(init={"page": "/returns"})
        turn = await rig.driver.user_says("Return the perfume from 48090.")
        assert "fragrances can't be returned" in turn.text
        assert "can go back, though" in turn.text
        assert all("product_id" not in m["args"] for m in _moves(rig, "returns.fill"))


def test_the_page_and_the_brain_share_the_order_rules() -> None:
    orders = {o["id"]: o for o in f.resolve_orders()}
    assert orders["FSH-48213"]["delivered"] == date(2026, 11, 21)
    assert f.return_check(orders["FSH-48213"], 7421, set()).days_left == 4
    assert f.return_check(orders["FSH-47920"], None, set()).why == "window"
    assert f.return_check(orders["FSH-48090"], 36940, set()).why == "fragrance"
    assert f.return_check(orders["FSH-48711"], None, set()).why == "not_delivered"
    assert f.can_cancel("packed") and not f.can_cancel("shipped")
    assert f.return_ref("FSH-48213", 7421) == "RTN-48213-7421"
    assert f.fmt_date(date(2026, 11, 27)) == "27 Nov 2026"
    assert f.spoken_day(date(2026, 11, 27)) == "Friday, 27 November"
    small = f.bag_totals([(1889, "L", 1, False)])  # ₹699: under ₹799, delivery ₹79
    assert (small.subtotal, small.delivery, small.total) == (699, 79, 778)
    wrapped = f.bag_totals([(7421, "M", 1, True)])
    assert (wrapped.delivery, wrapped.wrap, wrapped.total) == (0, 49, 1048)
    assert f.inr(125999) == "₹1,25,999" and f.discount_pct(f.product(18894) or {}) == 50


# ─── Kiosk ────────────────────────────────────────────────────────────────────


async def test_the_kiosk_searches_the_catalogue_and_shows_a_qr() -> None:
    s = f.Search(types=["watches"], colours=["Black"], price_max=3000)
    found = [p for p in f.search(s) if p["gender"] == "men"]
    best = found[0]
    llm = ScriptedOpenAI(
        {
            "Black watches for men under 3000.": call(
                "kiosk_search",
                genders=["men"],
                types=["watches"],
                colours=["black"],
                price_max=3000,
            ),
            "Show me the first one.": call("kiosk_show", product_id=str(best["id"])),
            "Give me the QR code.": call("kiosk_qr", product_id=str(best["id"])),
            "Can someone help me?": call("call_floor_assistant"),
        }
    )
    async with demo("fashio", llm) as rig:
        await rig.driver.start_session(init={"page": "/kiosk"})
        turn = await rig.driver.user_says("Black watches for men under 3000.")
        (search,) = _moves(rig, "kiosk.search")
        assert search["args"]["types"] == ["watches"] and search["args"]["colours"] == ["Black"]
        assert search["args"]["genders"] == ["men"] and search["args"]["price_max"] == 3000
        assert f"{len(found)} pieces match" in turn.text and f.short_name(best) in turn.text
        shown = await rig.driver.user_says("Show me the first one.")
        assert _moves(rig, "kiosk.show")[0]["args"] == {"product_id": str(best["id"])}
        assert "Scan the QR code" in shown.text
        await rig.driver.user_says("Give me the QR code.")
        assert _moves(rig, "kiosk.qr")[0]["args"] == {"product_id": str(best["id"])}
        helped = await rig.driver.user_says("Can someone help me?")
        assert len(_moves(rig, "kiosk.assist")) == 1
        assert "floor assistant is on the way" in helped.text


# ─── Amounts heard and said (X8) ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("heard", "rupees"),
    [
        ("under 2k", [(2000, None)]),
        ("two thousand", [(2000, None)]),
        ("dedh hazaar", [(1500, None)]),
        ("dhai hazaar tak", [(2500, None)]),
        ("1,500", [(1500, None)]),
        ("15 सौ", [(1500, None)]),
        ("pandrah sau", [(1500, None)]),
        ("around 3000", [(3000, None)]),
        ("between 1000 and 2000", [(2000, 1000)]),
        ("1000 to 2000", [(2000, 1000)]),
        ("डेढ़ हज़ार तक", [(1500, None)]),
        ("a 32 or a 34", [(32, None), (34, None)]),
    ],
)
def test_spoken_budgets_parse_to_rupees(
    heard: str, rupees: list[tuple[float, float | None]]
) -> None:
    assert [(a.value, a.low) for a in parse_amounts(heard)] == rupees


def test_an_implausible_budget_is_confirmed_back_never_used() -> None:
    why = implausible({"price_max": 2}, ["under 2k"])
    assert why is not None and why.startswith("Not done") and "₹2,000, right?" in why
    assert implausible({"price_max": 15}, ["pandrah sau"]) is not None
    assert implausible({"price_max": 10_00_000}, []) is not None
    assert implausible({"price_max": 1500}, []) is None
    assert implausible({"price_max": 0}, []) is None, "zero is no limit"
    assert (
        amounts_note("around dedh hazaar")
        == "[Amounts they said, in rupees: 'dedh hazaar' = about 1500 rupees.]"
    )
    assert amounts_note("yes please") is None
    assert speak_text("It's ₹1,999, down from ₹2,499.", "en") == "It's ₹1,999, down from ₹2,499."
    assert speak_text("यह ₹1,999 का है।", "hi") == "यह ₹1,999 का है।"


async def test_a_spoken_budget_reaches_the_model_in_rupees_and_a_wrong_one_is_confirmed() -> None:
    llm = ScriptedOpenAI(
        {
            "Kurtas under dedh hazaar.": reply_and_call(
                "Let me look.", "search_products", types=["kurtas"], price_max=1500
            ),
            "Actually make it under 2k.": call("search_products", price_max=2),
        }
    )
    async with demo("fashio", llm) as rig:
        await rig.driver.start_session(init={"page": "/shop"})
        await rig.driver.user_says("Kurtas under dedh hazaar.")
        assert "'dedh hazaar' = 1500 rupees" in _inputs(llm)
        assert _moves(rig, "shop.filter")[0]["args"]["price_max"] == 1500
        await _answer(rig, "shop.filter")
        turn = await rig.driver.user_says("Actually make it under 2k.")
        result = _filed(rig, "search_products")[-1]
        assert result.startswith("Not done") and "₹2,000" in result
        assert len(_moves(rig, "shop.filter")) == 1, "the wrong budget never reached the screen"
        assert "₹2,000, right?" in turn.text
        assert _brain(rig).search.price_max == 1500


# ─── Redial: a call outlives a dropped brain socket ───────────────────────────


def _redials(driver: VoqalizeDriver) -> list[bool | None]:
    return [
        r.config.redial.enabled
        for r in driver.requests
        if isinstance(r, ConfigureFrame) and r.config.redial is not None
    ]


async def test_a_dropped_socket_rejoins_the_call_where_it_was() -> None:
    """Mid-flow: the call started on /shop in English, searched, opened a product
    (the size advisor), switched to Hindi, saved to the wishlist and held a size
    for a yes; the socket drops. The redialled brain adopts the call — job,
    product, language, search, wishlist, fit inputs, the held add, the history —
    says no second hello, and the shopper's yes adds what was held."""
    from voqalize_demos.discovery import build_for

    from voqalize.conformance import (
        BrainServer,
        DirectConnection,
        generate_keypair,
        mint_voqalize_token,
    )

    llm = ScriptedOpenAI(
        {
            _ASK: reply_and_call("Let me look.", "search_products", **_ASK_ARGS),
            "Open the grey check shirt.": reply_and_call(
                "Opening it.", "open_product", product_id="6980"
            ),
            "Hindi mein baat karein?": reply_and_call("ज़रूर।", "set_language", language="hindi"),
            "Save it.": reply_and_call("Saved.", "save_to_wishlist", product_id="6980"),
            "Main L pehanta hoon, regular fit.": call("size_advice", usual_size="L", fit="regular"),
            "What did I ask for first?": reply("एक कुर्ता।"),
        }
    )
    build = build_for("fashio")
    built: list[FashioBrain] = []

    def _build() -> Any:
        brain = build(llm)  # type: ignore[arg-type]
        built.append(brain)  # type: ignore[arg-type]
        return brain

    keypair = generate_keypair()
    server = BrainServer(_build, host="127.0.0.1", port=0, public_keys=keypair.public_pem)
    port = await server.start()
    sid = "fashio-redial-e2e"
    init = {"surface": "fashio-web", "page": "/shop", "lang": "en"}

    def driver() -> VoqalizeDriver:
        token = mint_voqalize_token(
            private_key_pem=keypair.private_pem, session_id=sid, agent_id="fashio", tenant_id="demo"
        )
        return VoqalizeDriver(
            DirectConnection(f"ws://127.0.0.1:{port}", sid, token=token),
            session_id=sid,
            default_timeout=10.0,
        )

    first, second = driver(), driver()
    try:
        await first.open()
        greeting = await first.start_session(init=init)
        assert greeting is not None and PERSONA.name in greeting.text
        assert _redials(first) == [True]
        await first.user_says(_ASK)
        await first.user_says("Open the grey check shirt.")
        await _event(
            first, "screen.viewed", {"path": "/p/6980", "page": "product", "product_id": "6980"}
        )
        await first.user_says("Hindi mein baat karein?")
        await asyncio.sleep(0.1)
        await first.user_says("Save it.")
        await _event(first, "wishlist.changed", {"count": 1, "ids": ["6980"]}, by="agent")
        await first.user_says("Main L pehanta hoon, regular fit.")
        before = built[-1]
        assert before.job == "fit" and before.product_id == 6980 and before.lang == "hi"
        assert before.wishlist == [6980] and before.search.types == ["kurtas"]
        assert before.pending is not None and (before.pending.kind, before.pending.size) == (
            "add",
            "L",
        )
        assert not _moves(first, "bag.add")

        await first.aclose()
        for _ in range(50):
            if len(REJOIN):
                break
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.1)
        assert len(REJOIN) == 1, "the dropped call is held for a redial"

        await second.open()
        again = await second.start_session(init=init, greeting_timeout=0.5)
        assert again is None, "no second greeting on a rejoined call"
        after = built[-1]
        assert after is not before
        assert after.job == "fit" and after.product_id == 6980, "the page it moved to"
        assert after.lang == "hi" and after.wishlist == [6980]
        assert after.search.price_max == 2000 and after.fit_inputs[6980]["usual_size"] == "L"
        assert after.pending is not None and after.pending.size == "L", "the held add"
        check_voice_pair(
            DemoRig(name="fashio", server=server, driver=second, _built=[]),
            voice=PERSONA.voices["hi"],
            language="hi",
        )

        requests = len(llm.requests)
        yes = await second.user_says("हाँ, डाल दो।")
        assert yes.units, "the call carried on after the drop"
        assert _moves(second, "bag.add")[0]["args"] == {"product_id": "6980", "size": "L", "qty": 1}
        assert len(llm.requests) == requests, "the yes to the held add needed no model call"

        await second.user_says("What did I ask for first?")
        last = json.dumps(llm.captured_inputs[-1], ensure_ascii=False)
        assert _ASK in last and "Save it." in last, "the history came across"
        for lang in ("en", "hi"):
            rehello = GREETING["fit"][lang].format(name=PERSONA.name, first="Neha")
            assert rehello not in last, "no second hello reached the model's history"
    finally:
        await second.aclose()
        await server.aclose()


async def test_a_redial_that_finds_nothing_starts_fresh_and_a_hang_up_is_let_go() -> None:
    from voqalize_demos._loaded.fashio.rejoin import KEEP_AFTER_DROP_S, KEEP_LIVE_S, Rejoin

    now = [0.0]
    store: Rejoin[object] = Rejoin(clock=lambda: now[0])
    a, b = object(), object()
    store.hold("s1", a)
    store.dropped("s1", b)
    now[0] = KEEP_AFTER_DROP_S + 1
    assert store.take("s1") is a, "a live call is kept however long it runs"
    store.hold("s1", a)
    store.dropped("s1", a)
    now[0] += KEEP_AFTER_DROP_S - 1
    assert len(store) == 1
    now[0] += 2
    assert store.take("s1") is None and len(store) == 0, "expired two minutes after the drop"
    store.hold("s2", a)
    now[0] += KEEP_LIVE_S + 1
    assert len(store) == 0


async def test_a_redial_after_expiry_starts_a_new_conversation() -> None:
    from voqalize_demos._loaded.fashio import rejoin

    llm = ScriptedOpenAI(
        {"Save it.": reply_and_call("Saved.", "save_to_wishlist", product_id="7421")}
    )
    async with demo("fashio", llm) as rig:
        await rig.driver.start_session(init={"page": "/p/7421", "lang": "en"})
        await rig.driver.user_says("Save it.")
        held = _brain(rig)
        assert held.wishlist == [7421]
    real = REJOIN._clock  # pyright: ignore[reportPrivateUsage]
    try:
        REJOIN._clock = lambda: real() + rejoin.KEEP_AFTER_DROP_S + 1  # pyright: ignore[reportPrivateUsage]
        assert len(REJOIN) == 0
    finally:
        REJOIN._clock = real  # pyright: ignore[reportPrivateUsage]
    async with demo("fashio", ScriptedOpenAI()) as rig:
        greeting = await rig.driver.start_session(init={"page": "/p/7421", "lang": "en"})
        check_greeting(rig, greeting)
        fresh = _brain(rig)
        assert fresh is not held and fresh.wishlist == [] and fresh.pending is None


async def test_no_redial_is_asked_of_a_voqalize_that_does_not_offer_it() -> None:
    from voqalize.sdk.wire import Capability

    async with demo("fashio", ScriptedOpenAI()) as rig:
        rig.driver.capabilities.discard(Capability.REDIAL)
        greeting = await rig.driver.start_session(init={"page": "/", "lang": "en"})
        check_greeting(rig, greeting)
        assert _redials(rig.driver) == []
        check_voice_pair(rig, voice=PERSONA.voices["en"], language="en")
