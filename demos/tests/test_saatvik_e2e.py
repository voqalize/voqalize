"""Tara, Saatvik's solar advisor, end to end over the wire — no network, no LLM key.

The real ``SaatvikBrain`` on a real ``brain_server`` socket, driven by the
conformance ``VoqalizeDriver``, with only the model scripted. The knowledge is a
small invented site in the crawl's own shape, put in place of the committed one,
so no test depends on what the crawl found this week.

What this demo earns that others do not:

**Nothing on the page is invented.** A path, a heading, an FAQ and a PDF quote
are checked before they reach the page; the assertion worth making is on what
crossed the wire, and on what did not.

**The form is the visitor's.** The prefill carries what they said and nothing
else — no consent, no submit — and a submitted form becomes the brief the sales
team receives, scored.

**A result the page produced is talked through.** The calculator's estimate
arrives after Tara's turn; it reaches the model's next request, and a quiet
visitor hears it from her in a short quiet spell.

Run: ``cd demos && uv run pytest tests/test_saatvik_e2e.py``
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from google.genai import types
from voqalize_demos.discovery import discover
from voqalize_demos.testing import Reply, ScriptedGemini, call, reply, reply_and_call

from ._harness import _configs, check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.saatvik import knowledge as kb  # noqa: E402
from voqalize_demos._loaded.saatvik.brain import (  # noqa: E402
    _GREETING,
    _GREETING_HI,
    _IDLE_MS,
    _TALK_THROUGH_MS,
    TOGGLE_CONFIRM,
)
from voqalize_demos._loaded.saatvik.knowledge import (  # noqa: E402
    Document,
    Faq,
    Knowledge,
    Page,
    Word,
)


def _line(text: str, y: float) -> tuple[Word, ...]:
    """One OCR line of words, laid left to right at height ``y``."""
    out: list[Word] = []
    x = 0.1
    for w in text.split():
        out.append(Word(w, x, y, x + 0.01 * len(w), y + 0.02))
        x += 0.01 * len(w) + 0.01
    return tuple(out)


# A datasheet whose text is drawn as outlines: its words come from OCR, with the
# OCR's own slips ("(y)" for a gamma), and a quote is marked by its boxes.
_PMAX = "Temperature coefficient of Pmax (y) -0.30%/\u00b0C"
_VOC = "Temperature coefficient of Voc (B) -0.26%/\u00b0C"
_OCR_WORDS = _line(_PMAX, 0.40) + _line(_VOC, 0.45)

# An invented site in the crawl's shape: the names and figures are ours.
SITE = Knowledge(
    l1="Saatvik makes solar modules. Toll-free: 1800 000 0000 (invented for tests).",
    topics={},
    pages={
        "/": Page("/", "Home"),
        "/solar-calculator": Page("/solar-calculator", "Solar Calculator"),
        "/contact": Page("/contact", "Contact Us"),
        "/modules/test-panel": Page(
            "/modules/test-panel",
            "Test Panel 600",
            headings=("Test Panel 600", "Key Features", "Mechanical & Electrical Specifications"),
            faqs=(Faq("Does it work in the heat?", "Yes, its coefficient is low."),),
            text="A bifacial module for rooftops.",
            documents=("https://example.test/docs/test-panel.pdf",),
        ),
    },
    documents={
        "test-panel-datasheet": Document(
            id="test-panel-datasheet",
            url="https://example.test/docs/test-panel.pdf",
            title="Test Panel 600 Datasheet",
            kind="datasheet",
            pages={
                1: "Test Panel 600 Bifacial. Maximum Power 600 Wp. Module Efficiency 22.4%.",
                2: "Temperature Characteristics: Temperature coefficient of Power (Pm) -0.30 %/ºC.",
            },
            linked_from=("/modules/test-panel",),
        ),
        "outlined-datasheet": Document(
            id="outlined-datasheet",
            url="https://example.test/docs/outlined.pdf",
            title="Outlined Panel Datasheet",
            kind="datasheet",
            pages={1: "Outlined Panel", 2: f"{_PMAX}\n{_VOC}"},
            words={2: _OCR_WORDS},
        ),
    },
)

PANEL_PAGE = {
    "path": "/modules/test-panel",
    "title": "Test Panel 600",
    "headings": ["Test Panel 600", "Key Features", "Mechanical & Electrical Specifications"],
    "faqs": ["Does it work in the heat?"],
}


@pytest.fixture(autouse=True)
def _site(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Every session reads the invented site, not the committed crawl."""
    monkeypatch.setattr(kb, "KNOWLEDGE", SITE)
    yield


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
            "Take me to the panel page.": reply_and_call(
                "Here's the panel.", "navigate", request={"path": "/modules/test-panel/"}
            ),
            "Take me to the moon page.": reply_and_call(
                "Here it is.", "navigate", request={"path": "/moon"}
            ),
            "Where are the specs?": reply_and_call(
                "Here are the specs.", "show_section", request={"heading": "mechanical"}
            ),
            "Show me the warranty section.": reply_and_call(
                "Here.", "show_section", request={"heading": "Warranty"}
            ),
            "Does it like the heat?": reply_and_call(
                "It does.", "open_faq", request={"question": "does it work in the heat"}
            ),
            "What is the temperature coefficient?": [
                call("search_site", request={"query": "temperature coefficient"}),
                reply_and_call(
                    "Minus zero point three percent per degree.",
                    "open_document",
                    request={
                        "document_id": "test-panel-datasheet",
                        "page": 2,
                        "quote": "temperature coefficient of power (pm)  -0.30",
                    },
                ),
            ],
            "And its efficiency?": reply_and_call(
                "Twenty-two point four percent.",
                "open_document",
                request={
                    "document_id": "test-panel-datasheet",
                    "page": 2,
                    "quote": "Efficiency 22.4%",
                },
            ),
            "And the warranty?": reply_and_call(
                "Thirty years.",
                "open_document",
                request={
                    "document_id": "test-panel-datasheet",
                    "page": 1,
                    "quote": "30 year warranty",
                },
            ),
            "And on the outlined sheet?": reply_and_call(
                "Minus zero point three.",
                "open_document",
                request={
                    "document_id": "outlined-datasheet",
                    "page": 1,
                    "quote": "Temperature coefficient of Pmax -0.30%/\u00b0C",
                },
            ),
            "And both coefficients?": reply_and_call(
                "Here are both.",
                "open_document",
                request={
                    "document_id": "outlined-datasheet",
                    "page": 2,
                    "quote": f"{_PMAX} {_VOC}",
                },
            ),
            # One response, both calls: noting the lead never costs a hop.
            "We're a school in Pune, I'm Asha, and we'd like a quote.": Reply(
                text="Here's the form; add your email and mobile, tick consent and submit.",
                calls=(
                    (
                        "update_lead",
                        {
                            "request": {
                                "segment": "institutional",
                                "state": "Maharashtra",
                                "city": "Pune",
                            }
                        },
                    ),
                    (
                        "open_enquiry",
                        {
                            "request": {
                                "kind": "domestic",
                                "category": "Solar EPC - Rooftop",
                                "state": "Maharashtra",
                                "name": "Asha",
                            }
                        },
                    ),
                ),
            ),
            "My bill is about 4000 rupees in Gujarat.": reply_and_call(
                "Let me run that.",
                "run_calculator",
                request={"state": "Gujarat", "monthly_units": 500, "monthly_bill_inr": 4000},
            ),
            "So how much would I save?": reply("About three thousand a month."),
            "estimate is on their screen": reply("You'd save about three thousand rupees a month."),
            "just submitted the enquiry": reply("Thank you! When are you hoping to install?"),
            "Find me a dealer in Goa.": reply_and_call(
                "Let me look.", "find_dealer", request={"state": "Goa", "city": "Panaji"}
            ),
            "Mujhe solar panel chahiye, kya aap Hindi mein baat kar sakti hain?": reply(
                "जी हाँ, बताइए आपको क्या चाहिए।"
            ),
        }
    )


async def _page(rig: object, event: str, payload: dict[str, object]) -> None:
    await rig.driver.send_ui_event(event, payload)  # type: ignore[attr-defined]
    # `on_rtvi` takes no floor and there is nothing to await: give it a moment.
    await asyncio.sleep(0.1)


def _idle_windows(rig: object) -> list[int | None]:
    return [c.idle.timeout_ms for c in _configs(rig) if c.idle is not None]  # type: ignore[arg-type]


async def test_greeting_and_voice_reach_the_wire() -> None:
    """A written opener, and gauri in English on both legs before it."""
    async with demo("saatvik", _llm()) as rig:
        greeting = await rig.driver.start_session(
            init={"surface": "saatvik-ext", "page": "/", "lang": "en"}
        )
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text == _GREETING
        check_voice_pair(rig, voice="omnivoice/gauri", language="en")
        assert _idle_windows(rig) == [_IDLE_MS]


async def test_the_opener_follows_the_page_and_the_language() -> None:
    async with demo("saatvik", _llm()) as rig:
        greeting = await rig.driver.start_session(
            init={"surface": "saatvik-ext", "page": "/solar-calculator", "lang": "en"}
        )
        assert greeting is not None and "calculator" in greeting.text
    async with demo("saatvik", _llm()) as rig:
        greeting = await rig.driver.start_session(
            init={"surface": "saatvik-ext", "page": "/", "lang": "hi"}
        )
        assert greeting is not None and greeting.text == _GREETING_HI
        check_voice_pair(rig, voice="omnivoice/gauri", language="hi")


async def test_navigate_goes_to_a_real_page_and_refuses_an_invented_one() -> None:
    llm = _llm()
    async with demo("saatvik", llm) as rig:
        await rig.driver.start_session(init={"page": "/"})
        check_turn(rig, await rig.driver.user_says("Take me to the panel page."))
        assert rig.command("navigate") == {"path": "/modules/test-panel"}
        await rig.driver.user_says("Take me to the moon page.")
        assert rig.actions().count("navigate") == 1
        await rig.driver.user_says("So how much would I save?")
        refused = _results(llm.captured_contents[-1])["navigate"]
        assert refused.startswith("Not opened: /moon is not a page")


async def test_sections_and_faqs_are_checked_against_the_page() -> None:
    llm = _llm()
    async with demo("saatvik", llm) as rig:
        await rig.driver.start_session(init={"page": "/"})
        await _page(rig, "page_changed", PANEL_PAGE)
        await rig.driver.user_says("Where are the specs?")
        assert rig.command("show_section") == {
            "heading": "Mechanical & Electrical Specifications",
            "text": None,
        }
        # The page the visitor opened was read in with what they said.
        assert "Its sections: Test Panel 600" in _texts(llm.captured_contents[-1])
        await rig.driver.user_says("Show me the warranty section.")
        assert rig.actions().count("show_section") == 1
        await rig.driver.user_says("Does it like the heat?")
        assert rig.command("open_faq") == {"question": "Does it work in the heat?"}


async def test_a_pdf_quote_is_verified_moved_or_dropped() -> None:
    llm = _llm()
    async with demo("saatvik", llm) as rig:
        await rig.driver.start_session(init={"page": "/modules/test-panel"})
        await rig.driver.user_says("What is the temperature coefficient?")
        found = _results(llm.captured_contents[-1])["search_site"]
        assert "document_id: test-panel-datasheet, page 2" in found
        opened = [
            c["payload"] for c in rig.driver.ui_commands if c.get("command") == "open_document"
        ]
        # The model's spacing and case, the page's own words.
        assert opened[0] == {
            "url": "https://example.test/docs/test-panel.pdf",
            "title": "Test Panel 600 Datasheet",
            "page": 2,
            "quote": "Temperature coefficient of Power (Pm) -0.30",
            "boxes": None,
        }
        # On another page of the same PDF: opened where the quote is.
        await rig.driver.user_says("And its efficiency?")
        # Nowhere in it: the page opens, nothing is highlighted.
        await rig.driver.user_says("And the warranty?")
        opened = [
            c["payload"] for c in rig.driver.ui_commands if c.get("command") == "open_document"
        ]
        assert (opened[1]["page"], opened[1]["quote"]) == (1, "Efficiency 22.4%")
        assert (opened[2]["page"], opened[2]["quote"]) == (1, None)


async def test_an_outlined_pdf_quote_is_marked_by_its_ocr_boxes() -> None:
    async with demo("saatvik", _llm()) as rig:
        await rig.driver.start_session(init={"page": "/modules/test-panel"})
        # The model drops the OCR's "(y)" and asks the wrong page: the quote is
        # still found, on page 2, and its words become one box on their line.
        await rig.driver.user_says("And on the outlined sheet?")
        opened = rig.command("open_document")
        assert (opened["page"], opened["quote"]) == (2, _PMAX)
        first, last = _OCR_WORDS[0], _OCR_WORDS[len(_PMAX.split()) - 1]
        [box] = opened["boxes"]
        assert box["x"] < first.x0 and box["x"] + box["w"] > last.x1
        assert box["y"] < 0.40 and box["y"] + box["h"] > 0.42
        # A quote over two lines is two boxes, one per line.
        await rig.driver.user_says("And both coefficients?")
        both = [c for c in rig.driver.ui_commands if c.get("command") == "open_document"]
        top, bottom = both[-1]["payload"]["boxes"]
        assert top["y"] < 0.40 < bottom["y"] - 0.04


async def test_the_enquiry_is_prefilled_never_submitted_and_becomes_the_brief() -> None:
    llm = _llm()
    async with demo("saatvik", llm) as rig:
        await rig.driver.start_session(init={"page": "/"})
        await rig.driver.user_says("We're a school in Pune, I'm Asha, and we'd like a quote.")
        enquiry = rig.command("open_enquiry")
        assert enquiry["kind"] == "domestic"
        prefill = enquiry["prefill"]
        assert set(prefill) == {
            "name",
            "company",
            "email",
            "mobile",
            "category",
            "state",
            "message",
        }
        assert prefill["name"] == "Asha"
        assert prefill["email"] is None and prefill["mobile"] is None
        assert prefill["category"] == "Solar EPC - Rooftop"
        assert "institutional" in prefill["message"]
        assert "submit" not in rig.actions()

        # The brief is shown as it fills, not yet submitted.
        briefs = [c["payload"] for c in rig.driver.ui_commands if c.get("command") == "lead_brief"]
        assert briefs and briefs[-1]["submitted"] is False
        assert briefs[-1]["fields"]["segment"] == "institutional"

        await _page(
            rig,
            "enquiry_submitted",
            {
                "kind": "domestic",
                "fields": {
                    "name": "Asha Rao",
                    "company": "Sunrise School",
                    "email": "asha@example.test",
                    "mobile": "9800000000",
                    "category": "Solar EPC - Rooftop",
                    "state": "Maharashtra",
                    "message": "Rooftop for our school.",
                },
            },
        )
        briefs = [c["payload"] for c in rig.driver.ui_commands if c.get("command") == "lead_brief"]
        brief = briefs[-1]
        assert brief["submitted"] is True
        assert brief["fields"]["name"] == "Asha Rao"
        assert brief["fields"]["company"] == "Sunrise School"
        assert brief["fields"]["segment"] == "institutional"
        assert brief["fields"]["city"] == "Pune"
        assert brief["score"]["grade"] in ("hot", "warm")
        assert "submitted the enquiry form" in brief["score"]["reasons"]
        assert brief["routing"].startswith("Route to the Maharashtra distributors")

        # A quiet visitor is thanked in the short quiet spell.
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert "When are you hoping to install?" in turn.text
        assert _idle_windows(rig)[-1] == _IDLE_MS


async def test_the_calculator_result_reaches_the_next_request() -> None:
    llm = _llm()
    async with demo("saatvik", llm) as rig:
        await rig.driver.start_session(init={"page": "/"})
        await rig.driver.user_says("My bill is about 4000 rupees in Gujarat.")
        assert rig.command("run_calculator") == {"units": 500, "state": "Gujarat", "rate": 8}
        await _page(
            rig,
            "calculator_result",
            {
                "inputs": {"units": 500, "state": "Gujarat", "rate": 8},
                "text": "Recommended system 4 kW. Monthly savings ₹3,100.",
            },
        )
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        await rig.driver.user_says("So how much would I save?")
        assert "Monthly savings ₹3,100" in _texts(llm.captured_contents[-1])
        # They spoke first: the window is back to the ordinary one.
        assert _idle_windows(rig)[-1] == _IDLE_MS


async def test_a_quiet_visitor_hears_the_estimate_talked_through() -> None:
    llm = _llm()
    async with demo("saatvik", llm) as rig:
        await rig.driver.start_session(init={"page": "/"})
        await rig.driver.user_says("My bill is about 4000 rupees in Gujarat.")
        await _page(
            rig,
            "calculator_result",
            {"inputs": {"units": 500, "state": "Gujarat", "rate": 8}, "text": "Savings ₹3,100."},
        )
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert "three thousand" in turn.text


async def test_a_state_with_no_listed_dealer_searches_every_state() -> None:
    llm = _llm()
    async with demo("saatvik", llm) as rig:
        await rig.driver.start_session(init={"page": "/"})
        await rig.driver.user_says("Find me a dealer in Goa.")
        assert rig.command("find_dealer") == {"state": None, "query": "Panaji"}


async def test_the_toggle_switches_both_legs_and_confirms_in_hindi() -> None:
    async with demo("saatvik", _llm()) as rig:
        await rig.driver.start_session(init={"page": "/"})
        await _page(rig, "language_requested", {"language": "hi"})
        check_voice_pair(rig, voice="omnivoice/gauri", language="hi")
        # The widget's toggle is told at once, not left to guess from her voice.
        assert rig.command("language_changed") == {"language": "hi"}
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert turn.text == TOGGLE_CONFIRM["hindi"]


async def test_hinglish_switches_before_the_model_answers() -> None:
    async with demo("saatvik", _llm()) as rig:
        await rig.driver.start_session(init={"page": "/"})
        turn = await rig.driver.user_says(
            "Mujhe solar panel chahiye, kya aap Hindi mein baat kar sakti hain?"
        )
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/gauri", language="hi")
        assert rig.command("language_changed") == {"language": "hi"}
