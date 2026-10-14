"""Tushar, Saatvik's solar advisor, end to end over the wire — no network, no LLM key.

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
arrives after Tushar's turn; it reaches the model's next request, and a quiet
visitor hears it from him in a short quiet spell.

Run: ``cd demos && uv run pytest tests/test_saatvik_e2e.py``
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from google.genai import types
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, call, reply, reply_and_call

from ._harness import _configs, check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.saatvik import brain as saatvik  # noqa: E402
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
    """Every session reads the invented site, not the committed crawl, and he
    never nods unless a test asks him to: a nod is a unit of its own."""
    monkeypatch.setattr(kb, "KNOWLEDGE", SITE)
    monkeypatch.setattr(saatvik, "ACK_RATE", 0.0)
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
            # What the call told him goes to the lead with the form, once.
            "We're a school in Pune, I'm Asha, and we'd like a quote.": reply_and_call(
                "Here's the form; add your email and mobile, tick consent and submit.",
                "open_enquiry",
                request={
                    "kind": "domestic",
                    "category": "Solar EPC - Rooftop",
                    "state": "Maharashtra",
                    "name": "Asha",
                    "segment": "institutional",
                    "city": "Pune",
                },
            ),
            "I use 500 units, about 4000 rupees, in Gujarat.": reply_and_call(
                "That's about five hundred units.",
                "run_calculator",
                request={"state": "Gujarat", "monthly_units": 500, "monthly_bill_inr": 4000},
            ),
            "So how much would I save?": reply("About three thousand a month."),
            "estimate is on their screen": reply("You'd save about three thousand rupees a month."),
            "just submitted the enquiry": reply("Thank you! When are you hoping to install?"),
            "Find me a dealer in Goa.": reply_and_call(
                "Here are the dealers.", "find_dealer", request={"state": "Goa", "city": "Panaji"}
            ),
            # Refused and silent: asked again with tools off, he asks in his own words.
            "I use 350 units in Karnataka.": [
                call("run_calculator", request={"state": "Karnataka", "monthly_units": 350}),
                reply("What rate do you pay per unit?"),
            ],
            # A state the visitor never named is not guessed: it is asked for. Silent
            # twice, so the written line asks.
            "I use 500 units at 6 rupees a unit.": [
                call("run_calculator", request={"monthly_units": 500, "rate_per_unit": 6}),
                call("run_calculator", request={"monthly_units": 500, "rate_per_unit": 6}),
            ],
            # BOOK NOW, by voice: the booking fills in as they talk.
            "Book the kit for my home.": reply_and_call(
                "I've opened the booking for a home.",
                "book_product",
                request={"installation": "residential", "name": "Ravi", "city": "Bengaluru"},
            ),
            "My pincode is 560102.": reply_and_call(
                "I've added five six zero one zero two.",
                "book_product",
                request={"installation": "residential", "pincode": "560102"},
            ),
            "Book this for my shop.": reply_and_call(
                "I've opened the booking for a business.",
                "book_product",
                request={"installation": "commercial"},
            ),
            # Gemini sometimes sends a tool's fields flat, without ``request``.
            "Show me the specs, flat.": reply_and_call(
                "Here are the specs.", "show_section", heading="mechanical"
            ),
            # The form fills in as the visitor talks: each call adds, none clears.
            "I'm Ravi, from Bengaluru, I want a quote.": reply_and_call(
                "I've put your name in.",
                "open_enquiry",
                request={"kind": "domestic", "name": "Ravi", "state": "Karnataka"},
            ),
            "My mobile is 98475 41790.": reply_and_call(
                "I've put nine eight four seven five, four one seven nine zero. Is that right?",
                "open_enquiry",
                request={"kind": "domestic", "mobile": "9847541790"},
            ),
            # A page move with no words: the model is asked once more, tools off.
            "Show me that panel.": [
                call("navigate", request={"path": "/modules/test-panel"}),
                reply("It's a bifacial panel made for rooftops. Do you get much heat there?"),
            ],
            # Silent twice: the second request may not call, so his written line speaks.
            "Open the panel page.": [
                call("navigate", request={"path": "/modules/test-panel"}),
                call("navigate", request={"path": "/modules/test-panel"}),
            ],
            "How does this one compare?": reply("TOPCon runs cooler."),
            "Against the mono.": reply("TOPCon beats Mono PERC in heat."),
            "Is TOPCon better than PERC?": reply("Yes, TOPCon. It handles heat better than PERC."),
            "Mujhe solar panel chahiye, kya aap Hindi mein baat kar sakte hain?": reply(
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
    """A written opener, and gaurav in English on both legs before it."""
    async with demo("saatvik", _llm()) as rig:
        greeting = await rig.driver.start_session(
            init={"surface": "saatvik-ext", "page": "/", "lang": "en"}
        )
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text == _GREETING
        check_voice_pair(rig, voice="omnivoice/gaurav", language="en")
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
        check_voice_pair(rig, voice="omnivoice/gaurav", language="hi")


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


async def test_the_enquiry_is_prefilled_never_submitted_and_becomes_the_brief(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A pitch, with the brief shown in the widget.
    monkeypatch.setattr(saatvik, "SHARE_BRIEF", True)
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


async def test_a_visitor_never_sees_the_brief_and_the_model_keeps_no_lead() -> None:
    """The owner's call 1c91dcfc: told to record the lead every turn, the model
    answered nothing. No tool keeps it, and the visitor's widget never shows it."""
    llm = _llm()
    async with demo("saatvik", llm) as rig:
        await rig.driver.start_session(init={"page": "/"})
        await rig.driver.user_says("We're a school in Pune, I'm Asha, and we'd like a quote.")
        await _page(
            rig,
            "enquiry_submitted",
            {"kind": "domestic", "fields": {"name": "Asha Rao", "state": "Maharashtra"}},
        )
        assert "lead_brief" not in rig.actions()
        assert not hasattr(saatvik.SaatvikBrain, "update_lead")
        assert "update_lead" not in llm.captured_system_instructions[-1]


async def test_the_calculator_result_reaches_the_next_request() -> None:
    llm = _llm()
    async with demo("saatvik", llm) as rig:
        await rig.driver.start_session(init={"page": "/"})
        await rig.driver.user_says("I use 500 units, about 4000 rupees, in Gujarat.")
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
        await rig.driver.user_says("I use 500 units, about 4000 rupees, in Gujarat.")
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
        check_voice_pair(rig, voice="omnivoice/gaurav", language="hi")
        # The widget's toggle is told at once, not left to guess from his voice.
        assert rig.command("language_changed") == {"language": "hi"}
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert turn.text == TOGGLE_CONFIRM["hindi"]


async def test_hinglish_switches_before_the_model_answers() -> None:
    async with demo("saatvik", _llm()) as rig:
        await rig.driver.start_session(init={"page": "/"})
        turn = await rig.driver.user_says(
            "Mujhe solar panel chahiye, kya aap Hindi mein baat kar sakte hain?"
        )
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/gaurav", language="hi")
        assert rig.command("language_changed") == {"language": "hi"}


async def test_a_calculator_with_no_rate_asks_for_it_aloud() -> None:
    """A speechless call the calculator refused is not a silent turn: asked
    again, he asks for what it lacked, and nothing runs on the page."""
    async with demo("saatvik", _llm()) as rig:
        await rig.driver.start_session(init={"page": "/"})
        turn = await rig.driver.user_says("I use 350 units in Karnataka.")
        check_turn(rig, turn)
        assert turn.text == "What rate do you pay per unit?"
        assert "run_calculator" not in rig.actions()


async def test_a_silent_move_asks_the_model_to_talk_about_it() -> None:
    """A page move with no words gets one more request, tools off, with the call
    and its result in the context: he talks about the page, not "Here it is."."""
    llm = _llm()
    async with demo("saatvik", llm) as rig:
        await rig.driver.start_session(init={"page": "/"})
        turn = await rig.driver.user_says("Show me that panel.")
        check_turn(rig, turn, units=1)
        assert turn.text.startswith("It's a bifacial panel made for rooftops.")
        assert rig.actions().count("navigate") == 1
        retry = llm.captured_contents[-1]
        # Gemini takes no request ending on the model's turn.
        assert retry[-1].role == "user"
        assert "Opened Test Panel 600" in _results(retry)["navigate"]


async def test_twice_silent_falls_back_to_his_written_line() -> None:
    """The retry may not call a tool, so a model silent again gets the written
    line, and the page moved once."""
    async with demo("saatvik", _llm()) as rig:
        await rig.driver.start_session(init={"page": "/"})
        turn = await rig.driver.user_says("Open the panel page.")
        check_turn(rig, turn)
        assert turn.text == "Here's our Test Panel 600 page."
        assert rig.actions().count("navigate") == 1


async def test_he_thinks_at_low_so_the_words_come_before_the_calls() -> None:
    async with demo("saatvik", _llm()) as rig:
        await rig.driver.start_session(init={"page": "/"})
        config = rig.brain._config  # type: ignore[attr-defined]
        assert config.thinking_config.thinking_level == types.ThinkingLevel.LOW


async def test_a_calculator_with_no_state_asks_for_it_rather_than_guess() -> None:
    async with demo("saatvik", _llm()) as rig:
        await rig.driver.start_session(init={"page": "/"})
        turn = await rig.driver.user_says("I use 500 units at 6 rupees a unit.")
        check_turn(rig, turn)
        assert turn.text == saatvik._ASK_STATE[saatvik.Language.EN][0]
        assert "run_calculator" not in rig.actions()


async def test_the_rest_of_a_split_question_gets_no_second_nod(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(saatvik, "ACK_RATE", 1.0)
    async with demo("saatvik", _llm()) as rig:
        await rig.driver.start_session(init={"page": "/modules"})
        first = await rig.driver.user_says("How does this one compare?")
        rest = await rig.driver.user_says("Against the mono.")
        nods = {
            line for lines in saatvik._ACK_LINES[saatvik.Language.EN].values() for line in lines
        }
        assert any(first.text.startswith(n) for n in nods)
        assert rest.text == "TOPCon beats Mono PERC in heat."


async def test_a_question_gets_his_nod_then_the_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    """The nod is a unit of his own ahead of the model's, and never in its context."""
    monkeypatch.setattr(saatvik, "ACK_RATE", 1.0)
    llm = _llm()
    async with demo("saatvik", llm) as rig:
        await rig.driver.start_session(init={"page": "/"})
        turn = await rig.driver.user_says("Is TOPCon better than PERC?")
        nod = turn.units[0].text
        assert nod in saatvik._ACK_LINES[saatvik.Language.EN]["question"]
        assert turn.text.endswith("It handles heat better than PERC.")
        await rig.driver.user_says("Is TOPCon better than PERC?")
        said = _texts([c for c in llm.captured_contents[-1] if c.role == "model"])
        assert nod not in said


async def test_a_slow_model_after_the_nod_is_held(monkeypatch: pytest.MonkeyPatch) -> None:
    """The nod disarms the runtime's "taking longer" line, so he holds the floor."""
    monkeypatch.setattr(saatvik, "ACK_RATE", 1.0)
    monkeypatch.setattr(saatvik, "ACK_HOLD_AFTER_S", 0.2)
    llm = ScriptedGemini(
        {"Is TOPCon better than PERC?": [reply(chunks=["Yes, TOPCon."], chunk_delay=0.6)]}
    )
    async with demo("saatvik", llm) as rig:
        await rig.driver.start_session(init={"page": "/"})
        turn = await rig.driver.user_says("Is TOPCon better than PERC?", quiet_for=1.0)
        check_turn(rig, turn, units=3)
        nod, hold, answer = (u.text for u in turn.units)
        assert nod in saatvik._ACK_LINES[saatvik.Language.EN]["question"]
        assert hold in saatvik._ACK_HOLD[saatvik.Language.EN]
        assert answer == "Yes, TOPCon."


async def test_a_second_fill_adds_to_the_form_and_keeps_what_is_there() -> None:
    async with demo("saatvik", _llm()) as rig:
        await rig.driver.start_session(init={"page": "/"})
        await rig.driver.user_says("I'm Ravi, from Bengaluru, I want a quote.")
        turn = await rig.driver.user_says("My mobile is 98475 41790.")
        check_turn(rig, turn)
        fills = [
            c["payload"]["prefill"]
            for c in rig.driver.ui_commands
            if c.get("command") == "open_enquiry"
        ]
        assert len(fills) == 2
        assert fills[0]["mobile"] is None
        assert fills[1]["name"] == "Ravi"
        assert fills[1]["mobile"] == "9847541790"
        assert fills[1]["state"] == "Karnataka"


async def test_flat_arguments_still_move_the_page() -> None:
    """Fields sent without ``request`` are wrapped, not refused into silence."""
    async with demo("saatvik", _llm()) as rig:
        await rig.driver.start_session(init={"page": "/modules/test-panel"})
        await _page(rig, "page_changed", PANEL_PAGE)
        turn = await rig.driver.user_says("Show me the specs, flat.")
        check_turn(rig, turn)
        assert rig.command("show_section")["heading"] == "Mechanical & Electrical Specifications"


async def test_book_now_fills_the_booking_and_adds_to_it() -> None:
    """The kit's BOOK NOW by voice: residential chosen, details filled, a second
    call adds the pincode and keeps the rest; a confirmed booking reaches him."""
    llm = _llm()
    async with demo("saatvik", llm) as rig:
        await rig.driver.start_session(init={"page": "/solar-kits"})
        await rig.driver.user_says("Book the kit for my home.")
        turn = await rig.driver.user_says("My pincode is 560102.")
        check_turn(rig, turn)
        books = [c["payload"] for c in rig.driver.ui_commands if c.get("command") == "book_product"]
        assert [b["installation"] for b in books] == ["residential", "residential"]
        # Booked from the kit page with no product named: the kit's own BOOK NOW.
        assert {b["product"] for b in books} == {"surya-connect-kit"}
        assert books[1]["details"]["name"] == "Ravi"
        assert books[1]["details"]["city"] == "Bengaluru"
        assert books[1]["details"]["pincode"] == "560102"
        await _page(
            rig,
            "booking_submitted",
            {
                "product": "surya-connect-kit",
                "installation": "residential",
                "fields": {"name": "Ravi"},
            },
        )
        await rig.driver.user_says("So how much would I save?")
        assert "confirmed the booking of surya-connect-kit" in _texts(llm.captured_contents[-1])


async def test_book_now_books_the_product_on_their_page_and_nothing_else() -> None:
    """On an inverter page, "book this" books that inverter; on a page with no
    BOOK NOW and no product named, nothing is opened and the model is told so."""
    llm = _llm()
    async with demo("saatvik", llm) as rig:
        await rig.driver.start_session(init={"page": "/inverters/hybrid"})
        await rig.driver.user_says("Book this for my shop.")
        assert rig.command("book_product")["product"] == "uday-plus-hybrid"
    llm = _llm()
    async with demo("saatvik", llm) as rig:
        await rig.driver.start_session(init={"page": "/"})
        await rig.driver.user_says("Book this for my shop.")
        assert "book_product" not in rig.actions()
        await rig.driver.user_says("So how much would I save?")
        assert _results(llm.captured_contents[-1])["book_product"].startswith("Not opened")
