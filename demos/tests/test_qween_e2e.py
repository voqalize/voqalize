"""Trisha, the Qween jewellery consultant, end to end over the wire — no network,
no LLM key.

The real ``QweenBrain`` on a real ``brain_server`` socket, driven by the
conformance ``VoqalizeDriver``, with only the model scripted. The catalogue is a
small invented feed in Qween's own format, primed into the shared index, so no
test reaches www.qween.com.

What this demo earns that others do not:

**Names in, codes out.** The model says "rose bloom" and "pink sapphire"; the
page's grid takes ``mtp=ROSE_BLOOM_GOLD`` and ``stp=PINK_SAPPHIRE``. The
assertion worth making is on the params crossing the wire, since a wrong code is
an empty grid nobody hears about.

**Every figure has a source.** A price reaches the model from the feed index, or
from the dialog the page sent back — never from anywhere else, and never from an
index older than a day.

**The page is someone else's and the shopper clicks too.** The mirror is patched
from events; a route change of Trisha's own lands with the cards it produced, a
shopper's own is named and read through ``get_screen``.

Run: ``cd demos && uv run pytest tests/test_qween_e2e.py``
"""

from __future__ import annotations

import asyncio
import itertools
import time
from collections.abc import Iterator

import pytest
from google.genai import types
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, call, reply, reply_and_call

from voqalize.sdk.wire import (
    ConfigureFrame,
    RTVIFrame,
    SpeechChunkFrame,
    SpeechEndFrame,
    SpeechStartFrame,
)

from ._harness import DemoRig, _configs, check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.qween import acknowledge  # noqa: E402
from voqalize_demos._loaded.qween.brain import _GREETING, _sounds_hindi  # noqa: E402
from voqalize_demos._loaded.qween.catalog import FEED, QUOTE_LIMIT_S, Catalog  # noqa: E402


@pytest.fixture(autouse=True)
def _no_nod(monkeypatch: pytest.MonkeyPatch) -> None:
    """Her nod is random; a test that wants it asks for it."""
    monkeypatch.setattr(acknowledge, "RATE", 0.0)


def _item(
    group: str,
    slug: str,
    code: str,
    name: str,
    ptype: str,
    metal: str,
    karat: str,
    price: int,
    stone: str = "Diamond",
) -> str:
    details = {
        "Metal Colour": metal,
        "Metal Purity": karat,
        "Metal Weight": "2.10 g",
        "Diamond Quality": "SI - HI",
        "Stone Type": stone,
        "Style": "Classic",
    }
    detail_xml = "".join(
        f"<g:product_detail><g:attribute_name>{k}</g:attribute_name>"
        f"<g:attribute_value>{v}</g:attribute_value></g:product_detail>"
        for k, v in details.items()
    )
    return (
        f"<item><g:id>{code}</g:id><g:item_group_id>{group}</g:item_group_id>"
        f"<title>{name}</title><description>An invented piece for tests.</description>"
        f"<link>https://www.qween.com/product/{slug}?variantCode={code}</link>"
        f"<g:product_type>{ptype}</g:product_type><g:price>{price}.00 INR</g:price>"
        f"{detail_xml}</item>"
    )


# Invented pieces: the names and codes are ours, the shape is Qween's feed.
FEED_XML = (
    '<rss xmlns:g="http://base.google.com/ns/1.0"><channel>'
    + _item("G1", "petal-hoops", "PH-R18", "Petal Hoops", "Earrings > Hoops",
            "Rose Bloom Gold", "18 KT Gold", 64000, "Diamond, Pink Sapphire")
    + _item("G1", "petal-hoops", "PH-Y18", "Petal Hoops", "Earrings > Hoops",
            "Desert Noon Gold", "18 KT Gold", 63000, "Diamond, Pink Sapphire")
    + _item("G1", "petal-hoops", "PH-R14", "Petal Hoops", "Earrings > Hoops",
            "Rose Bloom Gold", "14 KT Gold", 52000, "Diamond, Pink Sapphire")
    + _item("G2", "dew-studs", "DS-W18", "Dew Studs", "Earrings > Studs",
            "Snowfall White Gold", "18 KT Gold", 41000)
    + _item("G3", "orbit-band", "OB-R18", "Orbit Band", "Rings > Bands",
            "Rose Bloom Gold", "18 KT Gold", 143000)
    + "</channel></rss>"
)  # fmt: skip

LISTING = {
    "path": "/catalog?cat=Earrings&mtp=ROSE_BLOOM_GOLD",
    "kind": "catalog",
    "params": {"cat": ["Earrings"], "mtp": ["ROSE_BLOOM_GOLD"]},
    "dialog_open": False,
    "cards": [
        {"n": 1, "slug": "petal-hoops", "text": "Petal Hoops ₹64,000"},
        {"n": 2, "slug": "dew-studs", "text": "Dew Studs ₹41,000"},
    ],
}
PIECE_PAGE = {
    "path": "/product/petal-hoops?variantCode=PH-R18",
    "kind": "product",
    "params": {"variantCode": ["PH-R18"]},
    "dialog_open": False,
    "slug": "petal-hoops",
    "variant_code": "PH-R18",
    "name": "Petal Hoops",
}


@pytest.fixture(autouse=True)
def _feed() -> Iterator[None]:
    """Every test starts from the invented feed, fetched just now."""
    FEED.prime(Catalog.parse(FEED_XML.encode()))
    yield
    FEED.prime(Catalog.parse(FEED_XML.encode()))


def _results(contents: list[types.Content]) -> dict[str, str]:
    return {
        p.function_response.name or "": str((p.function_response.response or {})["result"])
        for c in contents
        for p in (c.parts or [])
        if p.function_response is not None
    }


def _texts(contents: list[types.Content]) -> str:
    return "\n".join(p.text or "" for c in contents for p in (c.parts or []))


def _llm() -> ScriptedGemini:
    return ScriptedGemini(
        {
            # One line and one move, in one response: find_jewellery is not a read.
            "Show me rose gold earrings with pink sapphire under a lakh.": [
                reply_and_call(
                    "Here are rose gold earrings with pink sapphire.",
                    "find_jewellery",
                    request={
                        "category": "earrings",
                        "metals": ["rose bloom"],
                        "stones": ["pink sapphire"],
                        "price_max": 100000,
                    },
                ),
            ],
            # A purity is not a facet the listing has: the search goes out
            # without it, and the result says which pieces come in it.
            "Show me earrings in 14 karat.": [
                reply_and_call(
                    "Here are our earrings.",
                    "find_jewellery",
                    request={"category": "earrings", "karat": "14"},
                ),
            ],
            "Just hoops please.": [
                reply_and_call("Only the hoops.", "find_jewellery", request={"kind": "hoops"}),
            ],
            "Open the first one.": [
                reply_and_call("The Petal Hoops.", "show_piece", request={"card": 1}),
            ],
            "Can I see it in yellow gold?": [
                reply_and_call("In yellow gold.", "change_metal", request={"metal": "desert noon"}),
            ],
            # Asked, not told: change_metal is still the call, and it says so
            # when the piece is not made in that gold.
            "Do you have it in white gold?": [
                reply_and_call(
                    "Let me show you.", "change_metal", request={"metal": "snowfall white"}
                ),
            ],
            "And in 14 karat?": [
                reply_and_call("In fourteen karat.", "change_metal", request={"karat": "14"}),
            ],
            "Why is it priced like that?": [
                reply_and_call("Here is the breakup.", "show_price_breakup"),
            ],
            "So what does the gold cost?": reply("Forty thousand of it is the gold."),
            # The shopper's own click is read into this message: one request.
            "What's this one?": reply("That's the Orbit Band."),
            "How much is the Orbit Band?": [
                call("lookup_piece", request={"piece": "orbit band"}),
                reply("About one lakh forty-three thousand rupees."),
            ],
            "I'd rather talk to someone.": [
                reply_and_call(
                    "Of course, here is our concierge.",
                    "connect_to_person",
                    request={"how": "concierge"},
                ),
            ],
            "मुझे हिंदी में बात करनी है": [
                reply_and_call(
                    "ज़रूर, हिंदी में बात करते हैं।", "set_language", request={"language": "hindi"}
                ),
            ],
            # Hindi through the English recognizer: no word list catches it,
            # the model does, and writes Devanagari.
            "Apindimene bolti?": reply("हाँ, मैं हिंदी में बात कर सकती हूँ।"),
            # Hinglish with a request in it: the model only searches; the
            # switch is the brain's, made before the model runs.
            "Hindi mein baat karo, mujhe rings dikhao.": [
                reply_and_call(
                    "ज़रूर, ये रहीं हमारी रिंग्स।", "find_jewellery", request={"category": "rings"}
                ),
            ],
        }
    )


async def _page(rig: object, event: str, payload: dict[str, object]) -> None:
    await rig.driver.send_ui_event(event, payload)  # type: ignore[attr-defined]
    # `on_rtvi` takes no floor and there is nothing to await: give it a moment.
    await asyncio.sleep(0.1)


async def test_greeting_and_voice_reach_the_wire() -> None:
    """A written opener, and gayatri in English on both legs before it."""
    async with demo("qween", _llm()) as rig:
        greeting = await rig.driver.start_session()
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text == _GREETING
        check_voice_pair(rig, voice="omnivoice/gayatri", language="en")


async def test_a_rejoin_after_a_reload_says_so() -> None:
    """A full page load drops the call and the widget dials again with `rejoin`;
    the new session has no memory of the old one and her opener admits it."""
    async with demo("qween", _llm()) as rig:
        greeting = await rig.driver.start_session(init={"rejoin": True, "path": "/catalog"})
        check_greeting(rig, greeting)
        assert greeting is not None and "reloaded" in greeting.text
        check_voice_pair(rig, voice="omnivoice/gayatri", language="en")


async def test_find_resolves_names_to_the_grids_codes() -> None:
    """The model names a gold and a stone; the page is sent Qween's facet codes,
    and the model is told what the index matched — one request, since finding is
    a move and not a read."""
    llm = _llm()
    async with demo("qween", llm) as rig:
        await rig.driver.start_session()
        before = len(llm.captured_contents)
        turn = await rig.driver.user_says(
            "Show me rose gold earrings with pink sapphire under a lakh."
        )
        check_turn(rig, turn, units=1)
        assert len(llm.captured_contents) - before == 1, "an unmarked tool took a second request"

        assert rig.actions() == ["open_catalog"]
        assert rig.command("open_catalog")["params"] == {
            "cat": ["Earrings"],
            "mtp": ["ROSE_BLOOM_GOLD"],
            "stp": ["PINK_SAPPHIRE"],
            "fpc": ["0-100000"],
        }

        # The result waits for the next request, and carries the index's figures.
        await rig.driver.user_says("So what does the gold cost?")
        found = _results(llm.captured_contents[-1])["find_jewellery"]
        assert "1 pieces match" in found and "₹52,000 to ₹64,000" in found


async def test_a_kind_is_a_word_the_grid_searches() -> None:
    """Hoops have no facet of their own: the category and the site's text search."""
    async with demo("qween", _llm()) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Just hoops please.")
        assert rig.command("open_catalog")["params"] == {"cat": ["Earrings"], "q": ["hoop"]}


async def test_a_purity_is_named_from_the_index_not_claimed_of_the_page() -> None:
    """Qween's listing cannot be narrowed by purity. The page is sent no purity,
    and the result says the page shows every purity and names the pieces that
    come in the one asked for, so she never says it is showing 14 karat."""
    llm = _llm()
    async with demo("qween", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Show me earrings in 14 karat.")
        assert rig.command("open_catalog")["params"] == {"cat": ["Earrings"]}

        await rig.driver.user_says("So what does the gold cost?")
        found = _results(llm.captured_contents[-1])["find_jewellery"]
        assert "shows every purity" in found
        assert "come in 14 KT Gold: Petal Hoops." in found, found


async def test_her_own_listing_lands_with_its_cards_and_a_card_opens_its_piece() -> None:
    """The cards the page rendered for her search reach the model in the page's
    order, and "the first one" opens that card's piece at a real variant."""
    llm = _llm()
    async with demo("qween", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Show me rose gold earrings with pink sapphire under a lakh.")
        await _page(rig, "page_changed", LISTING)

        await rig.driver.user_says("Open the first one.")
        assert "1. Petal Hoops ₹64,000; 2. Dew Studs ₹41,000" in _texts(llm.captured_contents[-1])
        assert rig.command("open_product") == {"slug": "petal-hoops", "variant_code": "PH-R18"}


async def test_metal_is_a_swatch_and_purity_is_a_variant() -> None:
    """A gold colour is one click on the page's swatch; a purity has none, so it
    is the variant's own URL — and each result carries the variant's price."""
    llm = _llm()
    async with demo("qween", llm) as rig:
        await rig.driver.start_session()
        await _page(rig, "page_changed", PIECE_PAGE)

        await rig.driver.user_says("Can I see it in yellow gold?")
        assert rig.command("select_metal") == {"name": "Desert Noon Gold"}

        await rig.driver.user_says("And in 14 karat?")
        assert "₹63,000" in _results(llm.captured_contents[-1])["change_metal"]
        assert rig.command("open_product") == {"slug": "petal-hoops", "variant_code": "PH-R14"}


async def test_a_gold_the_piece_is_not_made_in_leaves_the_page() -> None:
    """ "Do you have it in white?" for a piece that has no white: the swatch is
    not clicked, and the result tells her to say so."""
    llm = _llm()
    async with demo("qween", llm) as rig:
        await rig.driver.start_session()
        await _page(rig, "page_changed", PIECE_PAGE)
        await rig.driver.user_says("Do you have it in white gold?")
        await rig.driver.user_says("And in 14 karat?")
        assert "select_metal" not in rig.actions()
        assert (
            "does not come in Snowfall White Gold"
            in _results(llm.captured_contents[-1])["change_metal"]
        )


async def test_the_price_breakup_is_read_from_the_dialog() -> None:
    """The breakup's figures reach the model as the page's own words."""
    llm = _llm()
    async with demo("qween", llm) as rig:
        await rig.driver.start_session()
        await _page(rig, "page_changed", PIECE_PAGE)
        await rig.driver.user_says("Why is it priced like that?")
        assert rig.command("open_modal") == {"modal": "price_breakup", "which": None}

        breakup = "PRICE BREAKUP\nGold ₹40,112\nDiamond ₹18,300\nMaking ₹3,700\nGST ₹1,888"
        await _page(rig, "dialog_opened", {"title": "PRICE BREAKUP", "text": breakup})
        await rig.driver.user_says("So what does the gold cost?")
        assert "Gold ₹40,112" in _texts(llm.captured_contents[-1])


async def test_the_diamonds_count_and_carat_come_from_the_page() -> None:
    """The feed has no stone counts or carats; since Qween's 2026-10 refresh the
    page prints them only in its composition block, and VIEW MORE is the
    gemstones alone. The adapter reports the block with the page, so "how big
    are the diamonds?" on the piece the shopper is on needs no dialog at all."""
    composition = "DIAMOND: 22 ROUND, SI - HI, 0.2640 ct in all."
    llm = _llm()
    async with demo("qween", llm) as rig:
        await rig.driver.start_session()
        await _page(rig, "page_changed", PIECE_PAGE | {"composition": composition})
        await rig.driver.user_says("How big is each diamond?")
        assert composition in _texts(llm.captured_contents[-1])


async def test_the_shoppers_own_move_is_read_into_their_next_message() -> None:
    """A route change she did not make is read by the brain into the shopper's
    next message, so "this one" is answered in one model request, not a
    get_screen and then an answer. Only the last page is read, and only once."""
    llm = _llm()
    async with demo("qween", llm) as rig:
        await rig.driver.start_session()
        await _page(
            rig,
            "page_changed",
            PIECE_PAGE | {"slug": "orbit-band", "variant_code": "OB-R18", "name": "Orbit Band"},
        )
        before = len(llm.captured_contents)
        turn = await rig.driver.user_says("What's this one?")
        check_turn(rig, turn, units=1)
        assert len(llm.captured_contents) - before == 1
        texts = _texts(llm.captured_contents[-1])
        assert "The shopper moved the page themselves. Now: On a piece, Orbit Band." in texts
        assert "₹1,43,000" in texts

        # Nothing moved since: the next message carries no read.
        await rig.driver.user_says("How much is the Orbit Band?")
        assert _texts(llm.captured_contents[-1]).count("moved the page themselves") == 1


async def test_a_failed_command_is_never_claimed() -> None:
    """The page could not do it; the model is told so, in words."""
    llm = _llm()
    async with demo("qween", llm) as rig:
        await rig.driver.start_session()
        await _page(
            rig,
            "command_failed",
            {"command": "select_metal", "error": "no Clover Green Gold swatch on this piece"},
        )
        await rig.driver.user_says("So what does the gold cost?")
        assert "no Clover Green Gold swatch" in _texts(llm.captured_contents[-1])


async def test_no_price_from_an_index_a_day_old() -> None:
    """Past the quote limit the index is not read at all."""
    llm = _llm()
    FEED.prime(Catalog.parse(FEED_XML.encode(), fetched_at=time.time() - QUOTE_LIMIT_S - 1))
    FEED.warm = lambda: None  # type: ignore[method-assign]  # no refresh, no network
    try:
        async with demo("qween", llm) as rig:
            await rig.driver.start_session()
            await rig.driver.user_says("How much is the Orbit Band?")
            result = _results(llm.captured_contents[-1])["lookup_piece"]
            assert "₹" not in result and "loading" in result
    finally:
        del FEED.warm  # type: ignore[attr-defined]


async def test_a_person_is_one_step_away() -> None:
    """Qween's own concierge dialog, on any page."""
    async with demo("qween", _llm()) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("I'd rather talk to someone.")
        assert rig.command("open_modal") == {"modal": "concierge", "which": None}


async def test_switching_to_hindi_moves_both_legs() -> None:
    """Hinglish is Hindi mode: both legs move, and the voice stays hers."""
    async with demo("qween", _llm()) as rig:
        await rig.driver.start_session()
        turn = await rig.driver.user_says("मुझे हिंदी में बात करनी है")
        check_turn(rig, turn, units=1)
        check_voice_pair(rig, voice="omnivoice/gayatri", language="hi")


async def test_hinglish_is_answered_in_hindi_from_the_first_word() -> None:
    """A shopper speaking Hinglish is switched by the brain before the model
    runs, so her reply opens in the Hindi voice and the model makes one call,
    the search, rather than two it reliably makes only one of."""
    async with demo("qween", _llm()) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Hindi mein baat karo, mujhe rings dikhao.")
        check_voice_pair(rig, voice="omnivoice/gayatri", language="hi")
        assert rig.command("open_catalog")["params"]["cat"] == ["Rings"]


async def test_a_reply_written_in_hindi_opens_in_the_hindi_voice() -> None:
    """The English recognizer spells Hindi as noise no word list catches; the
    model understands it and writes Devanagari. The brain switches both legs
    before the unit opens, so the English voice never reads Devanagari."""
    async with demo("qween", _llm()) as rig:
        await rig.driver.start_session()
        assert not _sounds_hindi("Apindimene bolti?")
        turn = await rig.driver.user_says("Apindimene bolti?")
        check_turn(rig, turn, units=1)
        check_voice_pair(rig, voice="omnivoice/gayatri", language="hi")
        frames = [r.frame for r in rig.driver.log]
        switch = max(
            i
            for i, f in enumerate(frames)
            if isinstance(f, ConfigureFrame) and f.config.tts and f.config.tts.language == "hi"
        )
        opened = next(
            i
            for i, f in enumerate(frames)
            if isinstance(f, SpeechStartFrame) and f.speech_id == turn.units[0].speech_id
        )
        assert switch < opened


async def test_patience_stays_at_the_floor_through_a_language_switch() -> None:
    """Every request that states the recognizer states patience 0 with it: one
    that left it out would drop the call back to the deployment's 7 at the
    first Hindi word."""
    async with demo("qween", _llm()) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Hindi mein baat karo, mujhe rings dikhao.")
        stated = [c.stt for c in _configs(rig) if c.stt is not None]
        assert len(stated) >= 2, "expected the opening configure and the switch"
        assert all(stt.patience == 0 for stt in stated), stated


@pytest.mark.parametrize(
    "said",
    [
        "Show me rose gold earrings with pink sapphire under a lakh.",
        "Can I talk to someone at your store?",
        "Do you have it in yellow gold?",
    ],
)
def test_english_is_not_heard_as_hindi(said: str) -> None:
    assert not _sounds_hindi(said)


async def test_a_nod_is_heard_before_the_model_and_kept_out_of_its_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A request gets a yes of hers as its own unit, ahead of the model's reply;
    the model is never shown it, so it cannot learn to leave the nodding to her
    or repeat it."""
    monkeypatch.setattr(acknowledge, "RATE", 1.0)
    llm = _llm()
    async with demo("qween", llm) as rig:
        await rig.driver.start_session()
        turn = await rig.driver.user_says(
            "Show me rose gold earrings with pink sapphire under a lakh."
        )
        check_turn(rig, turn, units=2)
        nod, answer = (u.text for u in turn.units)
        assert nod in acknowledge.LINES[acknowledge.Language.EN]["request"]
        assert answer != nod
        said = [
            p.text
            for c in llm.captured_contents[-1]
            if c.role == "model"
            for p in (c.parts or [])
            if p.text
        ]
        assert nod not in said


async def test_a_nod_is_in_the_voice_now_speaking(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hinglish switches both legs before the nod, so it is a Hindi one."""
    monkeypatch.setattr(acknowledge, "RATE", 1.0)
    async with demo("qween", _llm()) as rig:
        await rig.driver.start_session()
        turn = await rig.driver.user_says("Hindi mein baat karo, mujhe rings dikhao.")
        check_turn(rig, turn, units=2)
        assert turn.units[0].text in acknowledge.LINES[acknowledge.Language.HI]["request"]


async def test_a_slow_model_after_the_nod_is_held_not_left_silent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The nod disarms the runtime's "taking longer" line, so the brain holds
    the floor itself: a holding line while the model is quiet, heard between
    the nod and the answer, and like the nod never in the model's context."""
    monkeypatch.setattr(acknowledge, "RATE", 1.0)
    monkeypatch.setattr(acknowledge, "HOLD_AFTER_S", 0.2)
    llm = ScriptedGemini(
        {
            "How long does delivery take?": [
                reply(chunks=["About five working days."], chunk_delay=0.6)
            ]
        }
    )
    async with demo("qween", llm) as rig:
        await rig.driver.start_session()
        turn = await rig.driver.user_says("How long does delivery take?", quiet_for=1.0)
        check_turn(rig, turn, units=3)
        nod, hold, answer = (u.text for u in turn.units)
        assert nod in acknowledge.LINES[acknowledge.Language.EN]["question"]
        assert hold in acknowledge.HOLD[acknowledge.Language.EN]
        assert answer == "About five working days."
        await rig.driver.user_says("How long does delivery take?")
        said = [
            p.text
            for c in llm.captured_contents[-1]
            if c.role == "model"
            for p in (c.parts or [])
            if p.text
        ]
        assert answer in said
        assert nod not in said
        assert hold not in said


def _story(rig: DemoRig) -> list[str]:
    """Her speech and her avatar states, in wire order: a unit is its text,
    a state is ``state:<value>``."""
    story: list[str] = []
    texts: dict[str, list[str]] = {}
    for rec in rig.driver.log:
        frame = rec.frame
        if isinstance(frame, SpeechChunkFrame):
            texts.setdefault(frame.speech_id, []).append(frame.text)
        elif isinstance(frame, SpeechEndFrame):
            story.append("".join(texts.pop(frame.speech_id, [])))
        elif (
            isinstance(frame, RTVIFrame)
            and isinstance(frame.data, dict)
            and frame.data.get("type") == "avatar"
        ):
            assert set(frame.data) == {"type", "cmd", "state"}
            story.append(f"state:{frame.data['state']}")
    return story


async def test_after_the_nod_she_works_until_the_model_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Heard, working, answering: WORKING follows the nod, her holding line is
    said from inside it, and the model's first words end it — sent before
    those words, so the runtime can end the look as they start playing."""
    monkeypatch.setattr(acknowledge, "RATE", 1.0)
    monkeypatch.setattr(acknowledge, "HOLD_AFTER_S", 0.2)
    llm = ScriptedGemini(
        {
            "How long does delivery take?": [
                reply(chunks=["About five working days."], chunk_delay=0.6)
            ]
        }
    )
    async with demo("qween", llm) as rig:
        await rig.driver.start_session()
        turn = await rig.driver.user_says("How long does delivery take?", quiet_for=1.0)
        nod, hold, answer = (u.text for u in turn.units)
        assert _story(rig)[-5:] == [nod, "state:WORKING", hold, "state:None", answer]


async def test_without_a_nod_there_is_no_working_look() -> None:
    """The negative control: a turn she did not acknowledge leaves the face to
    the runtime's own reading of the wait."""
    async with demo("qween", _llm()) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Show me rose gold earrings with pink sapphire under a lakh.")
        assert not [s for s in _story(rig) if s.startswith("state:")]


async def test_a_quick_model_after_the_nod_is_not_held(monkeypatch: pytest.MonkeyPatch) -> None:
    """The negative control: an answer inside the window gets no holding line."""
    monkeypatch.setattr(acknowledge, "RATE", 1.0)
    monkeypatch.setattr(acknowledge, "HOLD_AFTER_S", 0.5)
    llm = ScriptedGemini(
        {
            "How long does delivery take?": [
                reply(chunks=["About five working days."], chunk_delay=0.05)
            ]
        }
    )
    async with demo("qween", llm) as rig:
        await rig.driver.start_session()
        turn = await rig.driver.user_says("How long does delivery take?")
        check_turn(rig, turn, units=2)


@pytest.mark.parametrize(
    ("said", "kind"),
    [
        ("Show me rose gold earrings.", "request"),
        ("Can you show me something lighter?", "request"),
        ("मुझे अपनी बहन की शादी के लिए कुछ चाहिए।", "request"),
        ("Is it hallmarked?", None),
        ("How long does delivery take?", "question"),
        ("What's the difference between VS and SI?", "question"),
        ("रोज़ पहनने के लिए कौन सा गोल्ड अच्छा है?", "question"),
        ("No, the yellow one.", "correction"),
        ("I don't like this one.", "correction"),
        ("It's for my wife's birthday.", "statement"),
        # Nothing to nod at.
        ("Okay.", None),
        ("Thank you so much, bye.", None),
        ("Hello?", None),
        # A mic check, a doubt about the stock, and a complaint dressed as a
        # question: "Let me see." before any of them reads wrong.
        ("can you hear me am trying to search", None),
        ("why making charges are so high for this simple design", None),
        ("इतना महंगा क्यों है?", None),
        ("can you scroll down a bit", "request"),
        # The English recognizer's spelling of Hindi: nodding at it in English
        # would come before a reply the model writes in Hindi.
        ("Apindimene bolti?", None),
        ("Thika Muja lightweight dikhana", None),
    ],
)
def test_the_nod_reads_what_was_asked(said: str, kind: str | None) -> None:
    assert acknowledge.classify(said) == kind


def test_the_nod_never_repeats_itself(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(acknowledge, "RATE", 1.0)
    ack = acknowledge.Acknowledger()
    said = [ack.line("Show me rings.", acknowledge.Language.EN) for _ in range(50)]
    assert all(a != b for a, b in itertools.pairwise(said))
