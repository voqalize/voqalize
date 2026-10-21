"""Javier, Explora's guide, end to end over the wire — no network, no LLM key.

The real ``ExploraBrain`` on a real ``brain_server`` socket, driven by the
conformance ``VoqalizeDriver``, with only the model scripted. The knowledge is a
small invented site in the crawl's own shape, put in place of the committed one,
so no test depends on what the crawl found this week.

What this demo earns that SendPotion's does not:

**Every page is a full page load.** A ``{page: …}`` cue splits his reply: the
words before it are spoken, the page opens once they have been said, and the
rest waits for the new page to report itself — so it is heard, and its cues
land, on the page it is about.

**The booking is the visitor's, up to the button.** Availability is checked on
the booking site and stops at the rooms; an expedition's enquiry is filled from
what they said and sent only once they have ticked the reCAPTCHA.

Run: ``cd demos && uv run pytest tests/test_explora_e2e.py``
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from google.genai import types
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, call, reply, reply_and_call

from ._harness import _configs, check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.explora import brain as explora  # noqa: E402
from voqalize_demos._loaded.explora import knowledge as kb  # noqa: E402
from voqalize_demos._loaded.explora.brain import (  # noqa: E402
    _IDLE_MS,
    _TALK_THROUGH_MS,
    asked_page,
    best_section,
    greeting,
    language_of,
)
from voqalize_demos._loaded.explora.knowledge import (  # noqa: E402
    Faq,
    Hotel,
    Knowledge,
    Page,
    Section,
)

# An invented site in the crawl's shape: the names and figures are ours.
SITE = Knowledge(
    l1="Explora runs lodges. (Invented for tests.)",
    topics={},
    pages={
        "/": Page(
            "/",
            "Explora | Official Site",
            kind="home",
            sections=(
                Section("Our Destinations", "Patagonia, the desert, the valley."),
                Section("What's Included in Your Stay", "Meals, drinks and explorations."),
            ),
            faqs=(Faq("Patagonia [Argentina + Chile]", "Lakes and glaciers."),),
        ),
        "/patagonia-travel-argentina-chile": Page(
            "/patagonia-travel-argentina-chile",
            "Explora Patagonia Travel",
            kind="destination",
            sections=(
                Section("PATAGONIA", ""),
                Section("OUR PATAGONIA LUXURY TRAVEL LODGES", "Five lodges in Patagonia."),
                Section("EL CHALTÉN", "Hiking under Fitz Roy."),
            ),
            tabs=("Award-Winning Lodges", "Custom-Made Explorations"),
        ),
        "/lodge/atacama-lodge": Page(
            "/lodge/atacama-lodge",
            "Atacama Lodge | Explora",
            kind="lodge",
            sections=(
                Section("Welcome to Explora Atacama", "An oasis near San Pedro de Atacama."),
                Section("Included with Your Stay", "Meals, explorations, spa, transfers."),
                Section(
                    "Stargaze from Explora\u2019s Observatory",
                    "The lodge's own observatory under the clearest skies.",
                ),
            ),
        ),
        "/explora-expeditions": Page(
            "/explora-expeditions",
            "Explora Expeditions",
            kind="expedition",
            sections=(Section("Sacred Mountains Expedition", "The unknown Inca trail."),),
        ),
    },
    hotels=(
        Hotel("EATA", "Atacama, Chile", "Hotels", "booking"),
        Hotel("EPAT", "Torres del Paine, Patagonia Chile", "Hotels", "booking"),
        Hotel("XSCM", "Sacred Mountains Expedition", "Expeditions", "enquiry"),
    ),
    countries=(("MX", "Mexico"), ("US", "United States"), ("CL", "Chile")),
    redirects={"/sacred-valley-peru": "/lodge/atacama-lodge"},
)

HOME_PAGE: dict[str, Any] = {
    "site": "site",
    "url": "https://www.explora.com/",
    "path": "/",
    "title": "Explora | Official Site",
    "headings": ["Our Destinations", "What's Included in Your Stay"],
    "faqs": ["Patagonia [Argentina + Chile]"],
}
PATAGONIA_PAGE: dict[str, Any] = {
    "site": "site",
    "url": "https://www.explora.com/patagonia-travel-argentina-chile/",
    "path": "/patagonia-travel-argentina-chile/",
    "title": "Explora Patagonia Travel",
    "headings": ["PATAGONIA", "OUR PATAGONIA LUXURY TRAVEL LODGES", "EL CHALTÉN"],
    "tabs": ["Award-Winning Lodges", "Custom-Made Explorations"],
    "links": ["/lodge/torres-del-paine-lodge/", "/el-chalten-lodge/"],
}
ATACAMA_PAGE: dict[str, Any] = {
    "site": "site",
    "url": "https://www.explora.com/lodge/atacama-lodge/",
    "path": "/lodge/atacama-lodge/",
    "title": "Atacama Lodge | Explora",
    "headings": ["Welcome to Explora Atacama", "Included with Your Stay"],
}


@pytest.fixture(autouse=True)
def _site(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Every session reads the invented site, and he never nods unless a test
    asks him to: a nod is a unit of its own."""
    monkeypatch.setattr(kb, "KNOWLEDGE", SITE)
    monkeypatch.setattr(explora, "ACK_RATE", 0.0)
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
            # A page cue mid-reply: the words before it first, the rest on the page.
            "Patagonia.": reply(
                "Patagonia it is. {page: /patagonia-travel-argentina-chile/}"
                "{show: our patagonia luxury travel lodges} Explora has five lodges here. "
                "{show: El Chalten} El Chaltén is for hikers. Do you love hiking?"
            ),
            # A page cue first: nothing is said before the page is up.
            "What is Explora?": reply(
                "{page: /}{show: our destinations} Lodges at the edge of the world. "
                "{show: what's included} Everything is included."
            ),
            # Already there, and a page that does not exist: neither is opened.
            "Tell me again.": reply(
                "{page: /lodge/atacama-lodge/}{show: welcome to explora atacama} It's an oasis. "
                "{page: /moon/} Truly."
            ),
            # Show cues against the tab in front: a heading, a tab, some words.
            "Why Explora?": reply(
                "{show: custom-made explorations} Every exploration is made for you. "
                "{show: the red door} Even the doors."
            ),
            "Open Patagonia.": reply("{faq: patagonia} Lakes and glaciers in the west."),
            # He forgot to show what they asked about: their page goes first.
            "Tell me about Atacama.": reply("It's an oasis in the driest desert."),
            "Can I go in November? Five nights.": reply_and_call(
                "Let's look at the calendar.",
                "check_availability",
                request={"hotel_code": "EATA", "nights": 5},
            ),
            "booking calendar is on their screen": reply(
                "November sixth or seventh are open. Which suits you?"
            ),
            "The sixth.": reply_and_call(
                "The sixth it is.",
                "check_availability",
                request={"hotel_code": "EATA", "date": "2026-11-06", "nights": 5},
            ),
            "The fifth of November.": reply_and_call(
                "Let me pick that.",
                "check_availability",
                request={"hotel_code": "EATA", "date": "2026-11-05"},
            ),
            "Show me the rooms.": reply_and_call(
                "Here are the rooms.",
                "check_availability",
                request={
                    "hotel_code": "EATA",
                    "date": "2026-11-06",
                    "nights": 5,
                    "show_rooms": True,
                },
            ),
            "rooms and rates are on their screen": reply(
                "The suite is from twelve hundred a night. You book it from here."
            ),
            "I'd like the Sacred Mountains expedition. I'm Ana Díaz.": reply_and_call(
                "Wonderful. I've started the form.",
                "fill_enquiry",
                request={"expedition_code": "XSCM", "first_name": "Ana", "last_name": "Díaz"},
            ),
            "enquiry form is on their screen": reply("What's your email?"),
            "ana@example.com, Mexican, plus 52 55 1234 5678.": reply_and_call(
                "I have ana at example dot com.",
                "fill_enquiry",
                request={
                    "expedition_code": "XSCM",
                    "email": "ana@example.com",
                    "nationality": "Mexican",
                    "phone": "+52 55 1234 5678",
                },
            ),
            "I'm from Mexico.": reply_and_call(
                "Got it.",
                "fill_enquiry",
                request={"expedition_code": "XSCM", "nationality": "Mexico", "title": "Ms."},
            ),
            "Send it.": reply_and_call("Sending it.", "send_enquiry"),
            "ticked I'm not a robot": reply_and_call("Sending it now.", "send_enquiry"),
            "enquiry has just been sent": reply("It's sent. Explora's team will write to you."),
            # Spanish heard: the call is in Spanish before he answers.
            "¿Cuánto cuesta una noche en Atacama? Quiero ver los precios.": reply(
                "{show: included with your stay} Todo está incluido. ¿Revisamos fechas?"
            ),
            "Carry on.": reply("Sure, let's keep going."),
            "Anything in March?": reply_and_call(
                "I've opened the calendar.",
                "check_availability",
                request={"hotel_code": "EPAT", "month": "2027-03"},
            ),
            # Live run: a silent booking move, re-asked, made up a calendar and
            # read it out in brackets. Now the written line is said instead.
            "Can I go in March?": [
                call("check_availability", request={"hotel_code": "EATA"}),
                reply("[The booking calendar shows March 1 and March 2.]"),
            ],
            "What's on the screen?": reply(
                "The calendar is open. [Open arrival days: March 1.] Pick a day."
            ),
        }
    )


async def _page(rig: Any, event: str, payload: dict[str, Any]) -> None:
    await rig.driver.send_ui_event(event, payload)
    # `on_rtvi` takes no floor and there is nothing to await: give it a moment.
    await asyncio.sleep(0.1)


def _commands(rig: Any, name: str) -> list[dict[str, Any]]:
    return [c["payload"] for c in rig.driver.ui_commands if c.get("command") == name]


def _cues(rig: Any) -> list[dict[str, Any]]:
    return _commands(rig, "cue")


def _idle_windows(rig: Any) -> list[int | None]:
    return [c.idle.timeout_ms for c in _configs(rig) if c.idle is not None]


async def _says_while_pages_load(rig: Any, text: str, *pages: dict[str, Any]) -> Any:
    """The visitor says ``text``; each page he opens loads and reports itself,
    as the extension's next page does once the call has rejoined on it."""
    turn = asyncio.create_task(rig.driver.user_says(text))
    for page in pages:
        opened = len(_commands(rig, "navigate"))
        for _ in range(200):
            await asyncio.sleep(0.02)
            if len(_commands(rig, "navigate")) > opened or turn.done():
                break
        await _page(rig, "page_changed", page)
    return await turn


# ─── Greeting and voice ────────────────────────────────────────────────────────


async def test_greeting_and_voice_reach_the_wire() -> None:
    """A written opener, and javier in English on both legs before it."""
    async with demo("explora", _llm()) as rig:
        greeting_turn = await rig.driver.start_session(
            init={"surface": "explora-ext", "site": "site", "path": "/"}
        )
        check_greeting(rig, greeting_turn)
        assert greeting_turn is not None and greeting_turn.text == greeting("/", "site")
        assert greeting_turn.text.startswith("Hi, I'm Javier")
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        assert _idle_windows(rig) == [_IDLE_MS]


def test_the_opener_follows_the_page() -> None:
    assert "this lodge" in greeting("/lodge/atacama-lodge/", "site")
    assert "expedition" in greeting("/explora-expeditions/", "site")
    assert "check the dates" in greeting("/ibe/paso1", "reservations")
    assert greeting("/", "site", "es").startswith("Hola, soy Javier")


async def test_a_chosen_spanish_starts_in_spanish() -> None:
    async with demo("explora", _llm()) as rig:
        turn = await rig.driver.start_session(init={"site": "site", "path": "/", "lang": "es"})
        assert turn is not None and turn.text.startswith("Hola, soy Javier")
        check_voice_pair(rig, voice="omnivoice/javier", language="es")


# ─── Full page loads ───────────────────────────────────────────────────────────


async def test_a_page_cue_splits_the_reply_at_the_page_load() -> None:
    """The words before the cue are a unit of their own; the page is opened once
    they are said; the rest, and its cues, come after the new page reports."""
    async with demo("explora", _llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        turn = await _says_while_pages_load(rig, "Patagonia.", PATAGONIA_PAGE)
        check_turn(rig, turn, units=2)
        assert turn.text.startswith("Patagonia it is.")
        assert "Explora has five lodges here." in turn.text
        assert "{" not in turn.text
        navigate = _commands(rig, "navigate")
        assert navigate == [
            {
                "path": "/patagonia-travel-argentina-chile/",
                "after_words": 3,
                "heading": None,
                "text": None,
                "faq": None,
            }
        ]
        # Every cue after the page cue went out after the page was opened.
        order = [
            c["command"] for c in rig.driver.ui_commands if c["command"] in ("navigate", "cue")
        ]
        assert order == ["navigate", "cue", "cue"]
        # Checked against the page that reported itself: the page's spelling.
        assert [c["heading"] for c in _cues(rig)] == [
            "OUR PATAGONIA LUXURY TRAVEL LODGES",
            "EL CHALTÉN",
        ]


async def test_the_page_being_left_reporting_again_is_not_the_new_one() -> None:
    """The extension re-reports a page whose parts render late; that is not
    the page he opened."""
    async with demo("explora", _llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        await _page(rig, "page_changed", ATACAMA_PAGE)
        task = asyncio.create_task(rig.driver.user_says("Patagonia.", quiet_for=1.5))
        for _ in range(200):
            await asyncio.sleep(0.02)
            if _commands(rig, "navigate"):
                break
        await _page(rig, "page_changed", ATACAMA_PAGE)
        await asyncio.sleep(0.3)
        assert _cues(rig) == []
        await _page(rig, "page_changed", PATAGONIA_PAGE)
        turn = await task
        check_turn(rig, turn, units=2)
        assert [c["heading"] for c in _cues(rig)] == [
            "OUR PATAGONIA LUXURY TRAVEL LODGES",
            "EL CHALTÉN",
        ]


async def test_a_page_cue_first_opens_the_page_before_any_word() -> None:
    async with demo("explora", _llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        turn = await _says_while_pages_load(rig, "What is Explora?", HOME_PAGE)
        check_turn(rig, turn, units=1)
        assert _commands(rig, "navigate")[0]["path"] == "/"
        assert _commands(rig, "navigate")[0]["after_words"] == 0
        assert [c["heading"] for c in _cues(rig)] == [
            "Our Destinations",
            "What's Included in Your Stay",
        ]


async def test_a_page_that_never_reports_holds_the_rest_only_so_long(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(explora, "_PAGE_WAIT_S", 0.2)
    async with demo("explora", _llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        # The driver calls a turn done after a quarter second of quiet; this one
        # is quiet for the length of the wait.
        turn = await rig.driver.user_says("Patagonia.", quiet_for=2.5)
        check_turn(rig, turn)
        assert "El Chaltén is for hikers." in turn.text


async def test_the_page_in_front_and_an_unknown_page_open_nothing() -> None:
    async with demo("explora", _llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        await _page(rig, "page_changed", ATACAMA_PAGE)
        turn = await rig.driver.user_says("Tell me again.")
        check_turn(rig, turn, units=1)
        assert _commands(rig, "navigate") == []
        assert _cues(rig)[0]["heading"] == "Welcome to Explora Atacama"
        assert "Truly." in turn.text


async def test_a_redirected_path_is_the_page_it_lands_on() -> None:
    assert SITE.page("/sacred-valley-peru/") is SITE.page("/lodge/atacama-lodge")


# ─── Cues on the page in front ─────────────────────────────────────────────────


async def test_cues_are_checked_against_the_tab_in_front() -> None:
    llm = _llm()
    async with demo("explora", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await _page(rig, "page_changed", PATAGONIA_PAGE)
        await rig.driver.user_says("Why Explora?")
        cues = _cues(rig)
        # A tab's label opens the tab; words that are on no heading are rung.
        assert cues[0]["heading"] == "Custom-Made Explorations"
        assert cues[1]["heading"] is None and cues[1]["text"] == "the red door"
        seen = _texts(llm.captured_contents[-1])
        assert "Its tabs and accordions: Award-Winning Lodges; Custom-Made Explorations" in seen
        assert "Its own sub-pages: /lodge/torres-del-paine-lodge/; /el-chalten-lodge/" in seen
        await _page(rig, "page_changed", HOME_PAGE)
        await rig.driver.user_says("Open Patagonia.")
        assert _cues(rig)[-1]["faq"] == "Patagonia [Argentina + Chile]"


async def test_the_page_they_asked_about_opens_when_his_reply_forgets() -> None:
    async with demo("explora", _llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await _says_while_pages_load(rig, "Tell me about Atacama.", ATACAMA_PAGE)
        assert _commands(rig, "navigate")[0]["path"] == "/lodge/atacama-lodge/"
    # Not from a page about the same place.
    async with demo("explora", _llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/atacama-travel-tips/"})
        await rig.driver.user_says("Tell me about Atacama.")
        assert _commands(rig, "navigate") == []


@pytest.mark.parametrize(
    ("text", "here", "path"),
    [
        ("Tell me about Torres del Paine", "/", "/lodge/torres-del-paine-lodge/"),
        ("And the salt flats in Uyuni?", "/", "/lodge/atacama-uyuni-crossing/"),
        ("What about Easter Island?", "/lodge/atacama-lodge", "/lodge/easter-island-hotels/"),
        ("Is the Chaltén lodge good for hiking?", "/", "/el-chalten-lodge/"),
        ("Tell me about Patagonia", "/", "/patagonia-travel-argentina-chile/"),
        # Already on a page about the place.
        ("Tell me about Patagonia", "/lodge/torres-del-paine-lodge", None),
        # A request about the call's language opens nothing.
        ("Can you speak Spanish?", "/", None),
        ("How many rooms are there?", "/", None),
    ],
)
def test_the_page_for_what_they_asked_about(text: str, here: str, path: str | None) -> None:
    assert asked_page(text, here) == path


def test_a_sentence_names_its_section() -> None:
    sections = [(s.heading, s.text) for s in SITE.pages["/lodge/atacama-lodge"].sections]
    assert (
        best_section("At night you can stargaze from Explora's observatory.", sections)
        == "Stargaze from Explora\u2019s Observatory"
    )
    assert best_section("Shall I check the dates?", sections) is None


# ─── The booking site ──────────────────────────────────────────────────────────


async def test_availability_is_checked_on_the_booking_site_and_stops_at_rooms() -> None:
    llm = _llm()
    async with demo("explora", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        await rig.driver.user_says("Can I go in November? Five nights.")
        assert _commands(rig, "check_availability")[-1] == {
            "hotel_code": "EATA",
            "date": None,
            "month": None,
            "nights": 5,
            "rooms": False,
            "language": "EN",
        }
        # The calendar's open days arrive after his turn: a quiet visitor hears
        # them in the short quiet spell.
        await _page(
            rig,
            "stay_state",
            {
                "step": "dates",
                "hotel_code": "EATA",
                "hotel": "Atacama, Chile",
                "month": "November 2026",
                "open_days": ["2026-11-06", "2026-11-07"],
            },
        )
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert "Which suits you?" in turn.text
        seen = _texts(llm.captured_contents[-1])
        assert "Open arrival days: Friday, November 6, 2026; Saturday, November 7, 2026" in seen

        await rig.driver.user_says("The sixth.")
        assert _commands(rig, "check_availability")[-1]["date"] == "2026-11-06"
        # A day the calendar does not list is refused before it reaches the page.
        await rig.driver.user_says("The fifth of November.")
        # A tool's result reaches the model with the next request.
        await rig.driver.user_says("Carry on.")
        refused = _results(llm.captured_contents[-1])["check_availability"]
        assert "not an open arrival day" in refused
        assert len(_commands(rig, "check_availability")) == 2

        await rig.driver.user_says("Show me the rooms.")
        assert _commands(rig, "check_availability")[-1]["rooms"] is True
        await _page(
            rig,
            "stay_state",
            {
                "step": "rooms",
                "hotel_code": "EATA",
                "hotel": "Atacama, Chile",
                "date": "2026-11-06",
                "chosen_nights": 5,
                "rooms": [{"name": "Suite", "text": "from US$ 1,200 per night"}],
            },
        )
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert "You book it from here." in turn.text
        assert "Suite (from US$ 1,200 per night)" in _texts(llm.captured_contents[-1])


async def test_an_expedition_enquiry_fills_and_sends_only_once_ticked() -> None:
    llm = _llm()
    async with demo("explora", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/explora-expeditions/"})
        await rig.driver.user_says("I'd like the Sacred Mountains expedition. I'm Ana Díaz.")
        assert _commands(rig, "fill_enquiry")[-1] == {
            "expedition_code": "XSCM",
            "title": None,
            "first_name": "Ana",
            "last_name": "Díaz",
            "email": None,
            "phone": None,
            "country": None,
            "message": None,
            "language": "EN",
        }
        # A nationality the form does not list is not guessed at.
        await rig.driver.user_says("ana@example.com, Mexican, plus 52 55 1234 5678.")
        await rig.driver.user_says("Carry on.")
        assert (
            "not on the form's nationality list"
            in _results(llm.captured_contents[-1])["fill_enquiry"]
        )
        filled = _commands(rig, "fill_enquiry")[-1]
        assert filled["first_name"] == "Ana" and filled["email"] == "ana@example.com"
        assert filled["country"] is None
        await rig.driver.user_says("I'm from Mexico.")
        assert _commands(rig, "fill_enquiry")[-1]["country"] == "Mexico"
        assert _commands(rig, "fill_enquiry")[-1]["title"] == "Ms."

        # Not sent while the reCAPTCHA is not ticked.
        await _page(
            rig,
            "enquiry_state",
            {
                "expedition": "Sacred Mountains Expedition",
                "expedition_code": "XSCM",
                "filled": {"first_name": "Ana", "email": "ana@example.com"},
                "missing": [],
                "captcha": False,
            },
        )
        await rig.driver.user_says("Send it.")
        await rig.driver.user_says("Carry on.")
        assert "not ticked" in _results(llm.captured_contents[-1])["send_enquiry"]
        assert _commands(rig, "send_enquiry") == []

        # Ticked: he says so and sends it, in the short quiet spell.
        await _page(
            rig,
            "enquiry_state",
            {
                "expedition": "Sacred Mountains Expedition",
                "expedition_code": "XSCM",
                "filled": {"first_name": "Ana", "email": "ana@example.com"},
                "missing": [],
                "captcha": True,
            },
        )
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert _commands(rig, "send_enquiry") == [{}]
        await _page(
            rig,
            "enquiry_sent",
            {"expedition": "Sacred Mountains Expedition", "by": "javier"},
        )
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert "Explora's team will write to you." in turn.text


async def test_a_silent_booking_move_says_its_line_and_no_bracket_is_spoken() -> None:
    llm = _llm()
    async with demo("explora", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        turn = await rig.driver.user_says("Can I go in March?")
        assert turn.text.strip() == "Here's the booking calendar."
        assert _commands(rig, "check_availability")[-1]["hotel_code"] == "EATA"
        turn = await rig.driver.user_says("What's on the screen?")
        assert "[" not in turn.text and "March 1" not in turn.text
        assert "The calendar is open." in turn.text and "Pick a day." in turn.text


async def test_a_month_they_name_turns_the_calendar_to_it() -> None:
    async with demo("explora", _llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/", "lang": "es"})
        await rig.driver.user_says("Anything in March?")
        sent = _commands(rig, "check_availability")[-1]
        assert sent["month"] == "2027-03" and sent["date"] is None
        # The booking site opens in the call's language.
        assert sent["language"] == "ES"


def test_countries_and_hotels_are_found_by_name() -> None:
    assert SITE.country("mexico") == ("MX", "Mexico")
    assert SITE.country("US") == ("US", "United States")
    assert SITE.country("Narnia") is None
    hotel = SITE.hotel("Torres del Paine")
    assert hotel is not None and hotel.code == "EPAT"


# ─── Language ──────────────────────────────────────────────────────────────────


async def test_spanish_heard_moves_both_legs_before_he_answers() -> None:
    async with demo("explora", _llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        await rig.driver.user_says("¿Cuánto cuesta una noche en Atacama? Quiero ver los precios.")
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert {"language": "es"} in _commands(rig, "language_changed")


async def test_the_toggle_switches_and_confirms_in_the_new_language() -> None:
    async with demo("explora", _llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await _page(rig, "language_requested", {"language": "es"})
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert turn.text == explora.TOGGLE_CONFIRM["es"]


@pytest.mark.parametrize(
    ("text", "sure", "lang"),
    [
        ("¿Qué incluye la estadía en el desierto?", True, "es"),
        ("What does the stay include?", True, "en"),
        ("Atacama", True, None),
        ("Claro.", False, "es"),
        ("{show: Included with Your Stay} Todo está incluido.", False, "es"),
    ],
)
def test_the_language_a_line_is_in(text: str, sure: bool, lang: str | None) -> None:
    assert language_of(text, sure=sure) == lang


# ─── The committed crawl ───────────────────────────────────────────────────────


def test_the_committed_crawl_loads_and_every_asked_page_exists() -> None:
    real = kb.load()
    assert len(real.pages) > 50
    assert {h.code for h in real.hotels} >= {"EATA", "EPAT", "XSCM"}
    assert real.country("Mexico") == ("MX", "Mexico")
    for _, path, _ in explora._ASKED_PAGES:
        assert real.page(path) is not None, path
    assert "OUR DESTINATIONS" in real.page("/destinations/").headings  # type: ignore[union-attr]
