"""Sunny, Saatvik's solar advisor, end to end over the wire — no network, no LLM key.

The real ``SaatvikBrain`` on a real ``brain_server`` socket, driven by the
conformance ``VoqalizeDriver``, with only the model scripted. The knowledge is a
small invented site in the crawl's own shape, put in place of the committed one,
so no test depends on what the crawl found this week.

What this demo earns that others do not:

**Nothing on the page is invented.** A path, a heading, a spec tab, an FAQ and
a PDF quote are checked before they reach the page; the assertion worth making
is on what crossed the wire, and on what did not.

**The screen follows her voice.** The page moves by the cues she writes into
her reply, never by a tool: each is taken out of the speech, checked, and sent
anchored to the first words of its sentence. A sentence about a section she
forgot to cue gets one of the brain's own.

**The form is the visitor's.** The prefill carries what they said and nothing
else — no consent, no submit — and a submitted form becomes the brief the sales
team receives, scored.

**A result the page produced is talked through.** The calculator's estimate
arrives after Sunny's turn; it reaches the model's next request, and a quiet
visitor hears it from her in a short quiet spell.

Run: ``cd demos && uv run pytest tests/test_saatvik_e2e.py``
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from voqalize_demos.discovery import discover
from voqalize_demos.testing import (
    ScriptedOpenAI,
    call,
    input_texts,
    reply,
    reply_and_call,
    tool_results,
)

from ._harness import _configs, check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.saatvik import brain as saatvik  # noqa: E402
from voqalize_demos._loaded.saatvik import knowledge as kb  # noqa: E402
from voqalize_demos._loaded.saatvik.brain import (  # noqa: E402
    _GREETING,
    _GREETING_HI,
    _IDLE_MS,
    _TALK_THROUGH_MS,
    MODEL,
    TOGGLE_CONFIRM,
)
from voqalize_demos._loaded.saatvik.knowledge import (  # noqa: E402
    CityRate,
    Datasheet,
    Document,
    Faq,
    Knowledge,
    Page,
    ProductLine,
    Section,
    Step,
    Tariff,
    Variant,
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
_PMAX = "Temperature coefficient of Pmax (y) -0.30%/°C"
_VOC = "Temperature coefficient of Voc (B) -0.26%/°C"
_OCR_WORDS = _line(_PMAX, 0.40) + _line(_VOC, 0.45)

PANEL = "/modules/test-panel"
KIT = "/test-kit"
_HEADINGS = ("Test Panel 600", "Key Features", "Mechanical & Electrical Specifications")
_TABS = ("ELECTRICAL", "MECHANICAL", "WARRANTY")

# An invented site in the crawl's shape: the names and figures are ours.
SITE = Knowledge(
    l1="Saatvik makes solar modules. Toll-free: 1800 000 0000 (invented for tests).",
    topics={},
    pages={
        "/": Page("/", "Home"),
        KIT: Page(
            KIT,
            "Test Kit",
            headings=("Test Kit", "No Battery Required", "DC & AC Cables", "Five Year Warranty"),
            sections=(
                Section("Test Kit", "A complete kit."),
                Section("No Battery Required", "Runs on the grid with no battery."),
                Section("DC & AC Cables", "Every cable in the box."),
                Section("Five Year Warranty", "Covered for five years."),
            ),
        ),
        "/solar-calculator": Page("/solar-calculator", "Solar Calculator"),
        "/contact": Page("/contact", "Contact Us"),
        "/faq": Page(
            "/faq",
            "FAQs",
            faqs=(Faq("How does net metering work?", "Your meter runs both ways."),),
        ),
        PANEL: Page(
            PANEL,
            "Test Panel 600",
            headings=_HEADINGS,
            faqs=(Faq("Does it work in the heat?", "Yes, its coefficient is low."),),
            text="A bifacial module for rooftops.",
            documents=("https://example.test/docs/test-panel.pdf",),
            sections=(
                Section("Test Panel 600", "A bifacial module for rooftops."),
                Section("Key Features", "Low temperature coefficient. Rear side gain."),
                Section("Mechanical & Electrical Specifications", "Anodised frame, glass."),
            ),
            tabs=_TABS,
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
            linked_from=(PANEL,),
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
    tariffs={
        "Karnataka": Tariff("Karnataka", 7.5, 4.5, 9.0, "BESCOM"),
        "Maharashtra": Tariff(
            "Maharashtra", 9.0, 5.0, 15.0, "MSEDCL", (CityRate("Mumbai", "Adani Electricity", 8.0),)
        ),
    },
)

PANEL_PAGE = {
    "path": PANEL,
    "title": "Test Panel 600",
    "headings": list(_HEADINGS),
    "faqs": ["Does it work in the heat?"],
    "tabs": list(_TABS),
}

#: A cue's payload with nothing set: each test names what it expects.
NONE: dict[str, Any] = {"path": None, "heading": None, "text": None, "tab": None, "faq": None}


@pytest.fixture(autouse=True)
def _site(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Every session reads the invented site, not the committed crawl."""
    monkeypatch.setattr(kb, "KNOWLEDGE", SITE)
    yield


def _results(items: list[Any]) -> dict[str, str]:
    return tool_results(items)


def _texts(items: list[Any]) -> str:
    return input_texts(items)


def _names(request: dict[str, Any]) -> list[str]:
    """The tools a request declared, by name."""
    return [str(t.get("name")) for t in request.get("tools") or []]


def _cues(rig: object) -> list[dict[str, Any]]:
    return [c["payload"] for c in rig.driver.ui_commands if c.get("command") == "cue"]  # type: ignore[attr-defined]


def _llm() -> ScriptedOpenAI:
    return ScriptedOpenAI(
        {
            # Cues: out of the speech, checked against the site, sent to the page.
            "Show me the panel.": reply(
                f"{{page: {PANEL}}}{{show: Key Features}} It stays cool in the heat. "
                "{show: mechanical} The frame is strong aluminium. Want the warranty next?"
            ),
            "Take me to the moon page.": reply("{page: /moon} That page is not on the site."),
            "What's the warranty?": reply(
                "{tab: warranty} It carries thirty years of cover. Shall I open the datasheet?"
            ),
            "What about shipping?": reply("{tab: shipping} It ships from the factory."),
            "Show me the warranty section.": reply("{show: Warranty} Thirty years, in writing."),
            "Does it like the heat?": reply("{faq: does it work in the heat} It does."),
            "How does net metering work?": reply(
                "{faq: how does net metering work} Your meter runs both ways."
            ),
            "मुझे पैनल दिखाइए।": reply(
                f"{{page: {PANEL}}} जी, यह पैनल गर्मी में ठंडा रहता है। "
                "{show: Key Features} इसकी खूबियाँ यहाँ हैं।"
            ),
            # No cue: the sentence that names a section of the page gets one.
            "What makes it good?": reply(
                "It is a bifacial module. Its key features suit hot roofs. Want the specs?"
            ),
            "What is the temperature coefficient?": [
                call("search_site", query="temperature coefficient"),
                reply_and_call(
                    "Minus zero point three percent per degree.",
                    "open_document",
                    document_id="test-panel-datasheet",
                    page=2,
                    quote="temperature coefficient of power (pm)  -0.30",
                ),
            ],
            "And its efficiency?": reply_and_call(
                "Twenty-two point four percent.",
                "open_document",
                document_id="test-panel-datasheet",
                page=2,
                quote="Efficiency 22.4%",
            ),
            "And the warranty?": reply_and_call(
                "Thirty years.",
                "open_document",
                document_id="test-panel-datasheet",
                page=1,
                quote="30 year warranty",
            ),
            "And on the outlined sheet?": reply_and_call(
                "Minus zero point three.",
                "open_document",
                document_id="outlined-datasheet",
                page=1,
                quote="Temperature coefficient of Pmax -0.30%/°C",
            ),
            "And both coefficients?": reply_and_call(
                "Here are both.",
                "open_document",
                document_id="outlined-datasheet",
                page=2,
                quote=f"{_PMAX} {_VOC}",
            ),
            # What the call told her goes to the lead with the form, once.
            "We're a school in Pune, I'm Asha, and we'd like a quote.": reply_and_call(
                "Here's the form; add your email and mobile, tick consent and submit.",
                "open_enquiry",
                kind="domestic",
                category="Solar EPC - Rooftop",
                state="Maharashtra",
                name="Asha",
                segment="institutional",
                city="Pune",
            ),
            "I use 500 units, about 4000 rupees, in Gujarat.": reply_and_call(
                "That's about five hundred units.",
                "run_calculator",
                site="home",
                state="Gujarat",
                monthly_units=500,
                monthly_bill_inr=4000,
            ),
            "So how much would I save?": reply("About three thousand a month."),
            "estimate is on their screen": reply("You'd save about three thousand rupees a month."),
            "just submitted the enquiry": reply("Thank you. When are you hoping to install?"),
            "Find me a dealer in Goa.": reply_and_call(
                "Here are the dealers.", "find_dealer", state="Goa", city="Panaji"
            ),
            # Refused and silent: asked again with tools off, she asks in her own words.
            # A state with no typical rate: refused and silent, so asked again
            # with tools off, she asks in her own words.
            "I use 350 units in Ladakh.": [
                call("run_calculator", site="home", state="Ladakh", monthly_units=350),
                reply("What rate do you pay per unit?"),
            ],
            # No rate: the state's typical rate, and the units from the bill.
            "My bill is about 4500 in Bengaluru, Karnataka. I don't know the rate.": reply_and_call(
                "I'm putting your bill into the calculator.",
                "run_calculator",
                site="home",
                state="Karnataka",
                city="Bengaluru",
                monthly_bill_inr=4500,
            ),
            # A city with its own power company has its own rate.
            "I use 400 units in Mumbai.": reply_and_call(
                "I'm putting four hundred units into the calculator.",
                "run_calculator",
                site="home",
                state="Maharashtra",
                city="Mumbai",
                monthly_units=400,
            ),
            "इस किट में क्या है?": reply(
                "जी, यह पूरी किट है। इसमें बैटरी नहीं है, तो रखरखाव कम है। किट में केबल भी शामिल हैं।"
            ),
            "What's special about this kit?": reply(
                "It's a complete kit. No battery is required, so upkeep is low. "
                "Both the DC and AC cables come in the box."
            ),
            # A state the visitor never named is not guessed: it is asked for. Silent
            # twice, so the written line asks.
            "I use 500 units at 6 rupees a unit.": [
                call("run_calculator", site="home", monthly_units=500, rate_per_unit=6),
                call("run_calculator", site="home", monthly_units=500, rate_per_unit=6),
            ],
            # BOOK NOW, by voice: the booking fills in as they talk.
            "Book the kit for my home.": reply_and_call(
                "I've opened the booking for a home.",
                "book_product",
                installation="residential",
                name="Ravi",
                city="Bengaluru",
            ),
            "My pincode is 560102.": reply_and_call(
                "I've added five six zero one zero two.",
                "book_product",
                installation="residential",
                pincode="560102",
            ),
            "Book this for my shop.": reply_and_call(
                "I've opened the booking for a business.",
                "book_product",
                installation="commercial",
            ),
            # The form fills in as the visitor talks: each call adds, none clears.
            "I'm Ravi, from Bengaluru, I want a quote.": reply_and_call(
                "I've put your name in.",
                "open_enquiry",
                kind="domestic",
                name="Ravi",
                state="Karnataka",
            ),
            "My mobile is 98475 41790.": reply_and_call(
                "I've put nine eight four seven five, four one seven nine zero. Is that right?",
                "open_enquiry",
                kind="domestic",
                mobile="9847541790",
            ),
            # A move with no words: the model is asked once more, tools off.
            "Open the datasheet.": [
                call("open_document", document_id="test-panel-datasheet", page=1),
                reply("It's the panel's datasheet. Its maximum power is six hundred watts."),
            ],
            # Silent twice: the second request may not call, so her written line speaks.
            "Show me the datasheet.": [
                call("open_document", document_id="test-panel-datasheet", page=1),
                call("open_document", document_id="test-panel-datasheet", page=1),
            ],
            # Only a cue, no words: the page moves and she is asked again to speak.
            "Just the panel page.": [
                reply("{page: /modules/test-panel}"),
                reply("This is the Test Panel. It stays cool in the heat."),
            ],
            "What about warranty?": reply("Thirty years on performance."),
            # A business is not sized by the home calculator.
            "What would rooftop solar cost my factory in Gujarat, on CAPEX?": reply_and_call(
                "I'm putting your numbers into the calculator.",
                "run_calculator",
                site="business",
                state="Gujarat",
                monthly_bill_inr=200000,
            ),
            "What would it cost on our roof here?": reply_and_call(
                "I'm putting your numbers into the calculator.",
                "run_calculator",
                site="home",
                state="Gujarat",
                monthly_bill_inr=200000,
            ),
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
    """A written opener, and ananya in English on both legs before it."""
    async with demo("saatvik", _llm()) as rig:
        greeting = await rig.driver.start_session(
            init={"surface": "saatvik-ext", "page": "/", "lang": "en"}
        )
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text == _GREETING
        assert greeting.text.startswith("Hi, I'm Sunny")
        check_voice_pair(rig, voice="omnivoice/ananya", language="en")
        assert _idle_windows(rig) == [_IDLE_MS]


async def test_the_opener_follows_the_page_and_the_language() -> None:
    async with demo("saatvik", _llm()) as rig:
        greeting = await rig.driver.start_session(
            init={"surface": "saatvik-ext", "page": "/solar-calculator", "lang": "en"}
        )
        assert greeting is not None and "calculator" in greeting.text
        assert greeting.text.startswith("Hi, I'm Sunny")
    async with demo("saatvik", _llm()) as rig:
        greeting = await rig.driver.start_session(
            init={"surface": "saatvik-ext", "page": "/", "lang": "hi"}
        )
        assert greeting is not None and greeting.text == _GREETING_HI
        # Her name, and a woman's Hindi: "सात्विक की सलाहकार", not "का".
        assert "सनी" in greeting.text and "सात्विक की सोलर सलाहकार" in greeting.text
        check_voice_pair(rig, voice="omnivoice/ananya", language="hi")


async def test_the_page_moves_only_by_cues() -> None:
    """No tool moves the page: navigate, show_section, open_faq and open_tab are
    gone, and the model is never told of them."""
    llm = _llm()
    async with demo("saatvik", llm) as rig:
        await rig.driver.start_session(init={"page": "/"})
        tools = {t.__name__ for t in rig.brain.tools}  # type: ignore[attr-defined]
        assert not tools & {"navigate", "show_section", "open_faq", "open_tab"}
        await rig.driver.user_says("So how much would I save?")
        declared = set(_names(llm.requests[-1]))
        assert declared == {
            "read_topic",
            "search_site",
            "open_document",
            "close_document",
            "run_calculator",
            "find_dealer",
            "open_enquiry",
            "book_product",
            "set_language",
        }


async def test_cues_leave_the_speech_and_move_the_page_with_it() -> None:
    async with demo("saatvik", _llm()) as rig:
        await rig.driver.start_session(init={"page": "/"})
        turn = await rig.driver.user_says("Show me the panel.")
        check_turn(rig, turn)
        assert "{" not in turn.text and "}" not in turn.text
        assert "page:" not in turn.text and "show:" not in turn.text
        assert "It stays cool in the heat. The frame is strong aluminium." in turn.text
        # The page, then its heading as the site spells it, both at the first
        # sentence; a heading named by its first word, at the second. No cue is
        # added to the closing offer.
        assert _cues(rig) == [
            {**NONE, "at": "it stays cool", "word": 0, "path": PANEL},
            {**NONE, "at": "it stays cool", "word": 0, "path": PANEL, "heading": "Key Features"},
            {
                **NONE,
                "at": "the frame is",
                "word": 6,
                "path": PANEL,
                "heading": "Mechanical & Electrical Specifications",
            },
        ]
        assert "navigate" not in rig.actions()


async def test_a_cue_to_a_page_not_on_the_site_is_dropped() -> None:
    async with demo("saatvik", _llm()) as rig:
        await rig.driver.start_session(init={"page": "/"})
        turn = await rig.driver.user_says("Take me to the moon page.")
        check_turn(rig, turn)
        assert "{" not in turn.text and "moon}" not in turn.text
        assert turn.text.strip() == "That page is not on the site."
        assert _cues(rig) == []


async def test_tab_and_faq_cues_are_checked_against_the_page() -> None:
    llm = _llm()
    async with demo("saatvik", llm) as rig:
        await rig.driver.start_session(init={"page": PANEL})
        await _page(rig, "page_changed", PANEL_PAGE)
        await rig.driver.user_says("What's the warranty?")
        # The page's own label, from the visitor's lower case.
        assert _cues(rig) == [{**NONE, "at": "it carries thirty", "word": 0, "tab": "WARRANTY"}]
        # The page the visitor opened was read in with what they said.
        seen = _texts(llm.captured_inputs[-1])
        assert "Its sections: Test Panel 600" in seen
        assert "Its spec tabs: ELECTRICAL, MECHANICAL, WARRANTY" in seen
        # A tab the page does not have is dropped.
        await rig.driver.user_says("What about shipping?")
        assert len(_cues(rig)) == 1
        # A heading the page does not have rings the words instead.
        await rig.driver.user_says("Show me the warranty section.")
        assert _cues(rig)[-1] == {**NONE, "at": "thirty years in", "word": 0, "text": "Warranty"}
        # An FAQ on the page in front, in the page's own words.
        await rig.driver.user_says("Does it like the heat?")
        assert _cues(rig)[-1] == {
            **NONE,
            "at": "it does",
            "word": 0,
            "faq": "Does it work in the heat?",
        }


async def test_an_faq_on_another_page_carries_that_page() -> None:
    async with demo("saatvik", _llm()) as rig:
        await rig.driver.start_session(init={"page": PANEL})
        turn = await rig.driver.user_says("How does net metering work?")
        check_turn(rig, turn)
        assert _cues(rig) == [
            {
                **NONE,
                "at": "your meter runs",
                "word": 0,
                "path": "/faq",
                "faq": "How does net metering work?",
            }
        ]


async def test_a_hindi_reply_anchors_its_cues_to_devanagari_words() -> None:
    async with demo("saatvik", _llm()) as rig:
        await rig.driver.start_session(init={"page": "/"})
        turn = await rig.driver.user_says("मुझे पैनल दिखाइए।")
        check_turn(rig, turn)
        assert "{" not in turn.text and "Key Features" not in turn.text
        check_voice_pair(rig, voice="omnivoice/ananya", language="hi")
        # The cue stays in the site's English; the anchor is what the voice says.
        assert _cues(rig) == [
            {**NONE, "at": "जी यह पैनल", "word": 0, "path": PANEL},
            {
                **NONE,
                "at": "इसकी खूबियाँ यहाँ",
                "word": 8,
                "path": PANEL,
                "heading": "Key Features",
            },
        ]


async def test_a_sentence_about_a_section_she_did_not_cue_gets_one() -> None:
    async with demo("saatvik", _llm()) as rig:
        await rig.driver.start_session(init={"page": PANEL})
        turn = await rig.driver.user_says("What makes it good?")
        check_turn(rig, turn)
        # Only the sentence that names a heading: not the opener, not the offer.
        assert _cues(rig) == [
            {**NONE, "at": "its key features", "word": 5, "heading": "Key Features"}
        ]


async def test_a_pdf_quote_is_verified_moved_or_dropped() -> None:
    llm = _llm()
    async with demo("saatvik", llm) as rig:
        await rig.driver.start_session(init={"page": PANEL})
        await rig.driver.user_says("What is the temperature coefficient?")
        found = _results(llm.captured_inputs[-1])["search_site"]
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
        await rig.driver.start_session(init={"page": PANEL})
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
        assert "update_lead" not in llm.captured_instructions[-1]


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
        assert "Monthly savings ₹3,100" in _texts(llm.captured_inputs[-1])
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
        check_voice_pair(rig, voice="omnivoice/ananya", language="hi")
        # The widget's toggle is told at once, not left to guess from her voice.
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
        check_voice_pair(rig, voice="omnivoice/ananya", language="hi")
        assert rig.command("language_changed") == {"language": "hi"}


async def test_a_calculator_with_no_rate_asks_for_it_aloud() -> None:
    """A speechless call the calculator refused is not a silent turn: asked
    again, she asks for what it lacked, and nothing runs on the page."""
    async with demo("saatvik", _llm()) as rig:
        await rig.driver.start_session(init={"page": "/"})
        turn = await rig.driver.user_says("I use 350 units in Ladakh.")
        check_turn(rig, turn)
        assert turn.text == "What rate do you pay per unit?"
        assert "run_calculator" not in rig.actions()


async def test_no_rate_runs_on_the_states_typical_rate() -> None:
    """A visitor who does not know their rate is not sent to find their bill:
    the calculator runs on their state's typical rate, units from their bill,
    and she is told to say the rate is typical."""
    llm = _llm()
    async with demo("saatvik", llm) as rig:
        await rig.driver.start_session(init={"page": "/"})
        await rig.driver.user_says(
            "My bill is about 4500 in Bengaluru, Karnataka. I don't know the rate."
        )
        run = next(c for c in rig.driver.ui_commands if c.get("command") == "run_calculator")
        assert run["payload"] == {"units": 600, "state": "Karnataka", "rate": 7.5}
        await rig.driver.user_says("So how much would I save?")
        result = _results(llm.captured_inputs[-1])["run_calculator"]
        assert "typical residential rate" in result and "₹7.5" in result


async def test_a_business_is_never_sized_by_the_home_calculator() -> None:
    """The calculator is Saatvik's home rooftop estimate: for a factory she is
    told to say the cost depends on the site and to offer the enquiry form."""
    llm = _llm()
    async with demo("saatvik", llm) as rig:
        await rig.driver.start_session(init={"page": "/"})
        await rig.driver.user_says("What would rooftop solar cost my factory in Gujarat, on CAPEX?")
        assert "run_calculator" not in rig.actions()
        await rig.driver.user_says("So how much would I save?")
        result = _results(llm.captured_inputs[-1])["run_calculator"]
        assert result.startswith("Not run") and "enquiry form" in result


async def test_a_business_products_page_never_runs_the_home_calculator() -> None:
    async with demo("saatvik", _llm()) as rig:
        await rig.driver.start_session(init={"page": "/epc-solutions/rooftop/commercial"})
        await rig.driver.user_says("What would it cost on our roof here?")
        assert "run_calculator" not in rig.actions()


async def test_a_city_with_its_own_power_company_has_its_own_rate() -> None:
    async with demo("saatvik", _llm()) as rig:
        await rig.driver.start_session(init={"page": "/"})
        await rig.driver.user_says("I use 400 units in Mumbai.")
        run = next(c for c in rig.driver.ui_commands if c.get("command") == "run_calculator")
        assert run["payload"] == {"units": 400, "state": "Maharashtra", "rate": 8.0}


async def test_a_hindi_sentence_rings_the_card_it_names() -> None:
    """A Hindi reply has no English words to score: its solar words, read
    through the glossary, ring the one card each names (the owner's Hindi dev
    call rang nothing on the kit page)."""
    async with demo("saatvik", _llm()) as rig:
        await rig.driver.start_session(init={"page": KIT})
        await rig.driver.user_says("इस किट में क्या है?")
        assert [c["heading"] for c in _cues(rig)] == [
            "Test Kit",
            "No Battery Required",
            "DC & AC Cables",
        ]


async def test_a_heading_said_in_other_words_order_is_rung() -> None:
    async with demo("saatvik", _llm()) as rig:
        await rig.driver.start_session(init={"page": KIT})
        await rig.driver.user_says("What's special about this kit?")
        assert [c["heading"] for c in _cues(rig)] == ["No Battery Required", "DC & AC Cables"]


def test_a_playbook_reads_as_the_products_story_to_its_call_to_action() -> None:
    k = Knowledge(
        l1="",
        topics={},
        pages={},
        documents={},
        products=(
            ProductLine(
                id="kit",
                name="Test Kit",
                path=KIT,
                pitch="A complete home kit.",
                story=(Step("Test Kit", "what it is"), Step("No Battery Required")),
                variants=(Variant("3 kW kit", "for about 400 units", "3 kW"),),
                datasheets=(Datasheet("kit-datasheet", "Kit", "p1: 3 kW"),),
                cta="BOOK NOW → book_product(product=surya-connect-kit)",
                qualify=("home or business", "monthly bill"),
                next=("batteries",),
                calculator=True,
            ),
        ),
    )
    text = saatvik._playbooks(k)
    assert "## Test Kit (kit) — /test-kit" in text
    assert "Story: Test Kit (what it is) → No Battery Required" in text
    assert "3 kW kit: for about 400 units [show: 3 kW]" in text
    assert "Call to action: BOOK NOW → book_product(product=surya-connect-kit)" in text
    assert "Ask: home or business; monthly bill" in text


async def test_a_silent_move_asks_the_model_to_talk_about_it() -> None:
    """A move with no words gets one more request, tools off, with the call and
    its result in the context: she talks about what opened, not "Here it is."."""
    llm = _llm()
    async with demo("saatvik", llm) as rig:
        await rig.driver.start_session(init={"page": PANEL})
        turn = await rig.driver.user_says("Open the datasheet.")
        check_turn(rig, turn, units=1)
        assert turn.text.startswith("It's the panel's datasheet.")
        assert rig.actions().count("open_document") == 1
        retry = llm.captured_inputs[-1]
        assert "Opened Test Panel 600 Datasheet" in _results(retry)["open_document"]


async def test_the_silent_move_retry_declares_the_tools_and_may_call_none() -> None:
    """The retry is tool choice "none" over the same declared tools, where the
    turn's own request leaves the choice to the model."""
    llm = _llm()
    async with demo("saatvik", llm) as rig:
        await rig.driver.start_session(init={"page": PANEL})
        before = len(llm.requests)
        await rig.driver.user_says("Open the datasheet.")
        first, again = llm.requests[before:]
        assert first.get("tool_choice") == "auto"
        assert again.get("tool_choice") == "none"
        assert again.get("tools")
        assert _names(again) == _names(first)
        assert again.get("reasoning") == first.get("reasoning")
        assert again.get("instructions") == first.get("instructions")


async def test_a_reply_that_is_only_a_cue_is_asked_to_speak() -> None:
    """A cue is no speech: a reply of nothing but a cue moves the page, and the
    model is asked once more, tools off, so she talks about what opened."""
    llm = _llm()
    async with demo("saatvik", llm) as rig:
        await rig.driver.start_session(init={"page": "/"})
        before = len(llm.requests)
        turn = await rig.driver.user_says("Just the panel page.")
        check_turn(rig, turn, units=1)
        assert turn.text.startswith("This is the Test Panel.")
        assert _cues(rig)[0]["path"] == PANEL
        _, again = llm.requests[before:]
        assert again.get("tool_choice") == "none"


async def test_a_missed_cue_is_noted_quietly() -> None:
    """A cue the page could not make (perhaps one of the brain's own) is told to
    the model as a quiet fact, never as something to apologise for aloud."""
    llm = _llm()
    async with demo("saatvik", llm) as rig:
        await rig.driver.start_session(init={"page": PANEL})
        await _page(
            rig, "command_failed", {"command": "cue", "reason": "no heading Warranty Terms"}
        )
        await rig.driver.user_says("What about warranty?")
        notes = _texts(llm.captured_inputs[-1])
        assert "screen cue of yours did not land" in notes
        assert "Tell the visitor plainly" not in notes


async def test_twice_silent_falls_back_to_her_written_line() -> None:
    """The retry may not call a tool, so a model silent again gets the written
    line, and the document opened once."""
    async with demo("saatvik", _llm()) as rig:
        await rig.driver.start_session(init={"page": PANEL})
        turn = await rig.driver.user_says("Show me the datasheet.")
        check_turn(rig, turn)
        assert turn.text == "Here's the Test Panel 600 Datasheet."
        assert rig.actions().count("open_document") == 1


async def test_she_thinks_at_low_on_terra_so_the_words_come_before_the_calls() -> None:
    llm = _llm()
    async with demo("saatvik", llm) as rig:
        await rig.driver.start_session(init={"page": "/"})
        await rig.driver.user_says("So how much would I save?")
        request = llm.requests[-1]
        assert request.get("model") == MODEL == "gpt-6.1-terra"
        assert request.get("reasoning") == {"effort": "low"}


async def test_a_calculator_with_no_state_asks_for_it_rather_than_guess() -> None:
    async with demo("saatvik", _llm()) as rig:
        await rig.driver.start_session(init={"page": "/"})
        turn = await rig.driver.user_says("I use 500 units at 6 rupees a unit.")
        check_turn(rig, turn)
        assert turn.text == saatvik._ASK_STATE[saatvik.Language.EN][0]
        assert "run_calculator" not in rig.actions()


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


async def test_book_now_fills_the_booking_and_adds_to_it() -> None:
    """The kit's BOOK NOW by voice: residential chosen, details filled, a second
    call adds the pincode and keeps the rest; a confirmed booking reaches her."""
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
        assert "confirmed the booking of surya-connect-kit" in _texts(llm.captured_inputs[-1])


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
        assert _results(llm.captured_inputs[-1])["book_product"].startswith("Not opened")
