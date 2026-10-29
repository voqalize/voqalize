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

Every move is a Stage move: cues go out as ``stage_cue`` with the raw words
after them, tool moves as ``stage_move``, and the page answers each with one
``stage_result``. :func:`_explora` stands in for that page and answers every
move as made, unless a test answers one itself.

Run: ``cd demos && uv run pytest tests/test_explora_e2e.py``
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import time
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from voqalize_demos.discovery import discover
from voqalize_demos.testing import (
    Reply,
    ScriptedOpenAI,
    call,
    input_texts,
    reply,
    reply_and_call,
    tool_results,
)

from ._harness import DemoRig, _configs, check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.explora import brain as explora  # noqa: E402
from voqalize_demos._loaded.explora import knowledge as kb  # noqa: E402
from voqalize_demos._loaded.explora.brain import (  # noqa: E402
    _IDLE_MS,
    _TALK_THROUGH_MS,
    LANDING_FLOOR_MS,
    asked_page,
    asked_page_language,
    best_section,
    days_line,
    greeting,
    language_of,
    nights_line,
    spoken_day,
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
        "/atacama-explorations": Page(
            "/atacama-explorations",
            "Atacama Explorations | Explora",
            kind="lodge",
            sections=(Section("Explorations", "Nearly fifty guided explorations."),),
        ),
        # The lodges' index, in the crawl's shape: one heading, and the lodges
        # named in its text, each with an "Explore … >" link.
        "/lodge": Page(
            "/lodge",
            "Lodges Archive - Explora Hotels",
            kind="lodge",
            sections=(
                Section(
                    "OUR LODGES",
                    "Patagonia El Calafate By the glaciers. Explore El Calafate > "
                    "Torres del Paine Granite peaks. Explore Torres del Paine > "
                    "Sacred Valley Inca villages. Explore Sacred Valley > "
                    "Atacama The driest desert. Explore Atacama > "
                    "Easter Island In the Pacific. Explore Easter Island >",
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
    """Every session reads the invented site."""
    monkeypatch.setattr(kb, "KNOWLEDGE", SITE)
    yield


def _results(items: list[Any]) -> dict[str, str]:
    return tool_results(items)


def _texts(items: list[Any]) -> str:
    return input_texts(items)


def _llm() -> ScriptedOpenAI:
    return ScriptedOpenAI(
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
            # Two pages in one reply: only the first is opened (prod call 661f3df0).
            "Show me the desert.": reply(
                "{page: /lodge/atacama-lodge/}{show: welcome to explora atacama} It's an oasis. "
                "{page: /patagonia-travel-argentina-chile/} Patagonia is green."
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
                args={"hotel_code": "EATA", "nights": 5},
            ),
            "booking calendar is on their screen": reply(
                "November sixth or seventh are open. Which suits you?"
            ),
            "The sixth.": reply_and_call(
                "The sixth it is.",
                "check_availability",
                args={"hotel_code": "EATA", "date": "2026-11-06", "nights": 5},
            ),
            "The fifth of November.": reply_and_call(
                "Let me pick that.",
                "check_availability",
                args={"hotel_code": "EATA", "date": "2026-11-05"},
            ),
            "Show me the rooms.": reply_and_call(
                "Here are the rooms.",
                "check_availability",
                args={
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
                args={"expedition_code": "XSCM", "first_name": "Ana", "last_name": "Díaz"},
            ),
            "enquiry form is on their screen": reply("What's your email?"),
            "ana@example.com, Mexican, plus 52 55 1234 5678.": reply_and_call(
                "I have ana at example dot com.",
                "fill_enquiry",
                args={
                    "expedition_code": "XSCM",
                    "email": "ana@example.com",
                    "nationality": "Mexican",
                    "phone": "+52 55 1234 5678",
                },
            ),
            "I'm from Mexico.": reply_and_call(
                "Got it.",
                "fill_enquiry",
                args={"expedition_code": "XSCM", "nationality": "Mexico", "title": "Ms."},
            ),
            "Send it.": reply_and_call("Sending it.", "send_enquiry"),
            "ticked I'm not a robot": reply_and_call("Sending it now.", "send_enquiry"),
            "enquiry has just been sent": reply("It's sent. Explora's team will write to you."),
            # Spanish heard: the call is in Spanish before he answers.
            "¿Cuánto cuesta una noche en Atacama? Quiero ver los precios.": reply(
                "{show: included with your stay} Todo está incluido. ¿Revisamos fechas?"
            ),
            "Carry on.": reply("Sure, let's keep going."),
            # Dev call 1f6cd8ce: the lodge's own rooms page, linked by its tab
            # bar but crawled under another path, was dropped three times.
            "Show me the room options.": reply(
                "Just a moment. {page: /explora-lodge-easter-island-new/} Here are the rooms."
            ),
            "Bring up the pricing tab.": reply_and_call(
                "Here it is.", "switch_tab", args={"tab_id": "99"}
            ),
            # Dev call ed9846d5, turn 6: his whole reply was a promise.
            "Show me the explorations.": [
                reply("One moment."),
                reply("Nearly fifty explorations, all included. Shall I pick some?"),
            ],
            "Read me the zones.": reply(
                "First, the salt flat basin. Then the Altiplano rises above four thousand metres. "
                "Shall I check dates?"
            ),
            # Dev call 0a304d89: the zones are accordions on the page, named in
            # passing with no cue of his own.
            "Talk me through the zones.": reply(
                "There are four zones. Janca is the highest, with glaciers. "
                "Suni covers the mid altitudes and its farms. Shall I check dates?"
            ),
            # Dev call 0a304d89, turn 4: a page cue for the page in front and
            # nothing else. Now asked once more, with tools off.
            "Show me explorations.": [
                reply("{page: /lodge/atacama-lodge/}"),
                reply("{show: stargaze} Here are the nights under the stars."),
            ],
            "I'll take the suite, two of us, king bed.": reply_and_call(
                "Good choice.",
                "choose_room",
                args={"room": "suite", "travellers": 2, "bed": "King"},
            ),
            "Pick the penthouse.": reply_and_call(
                "Let me pick it.", "choose_room", args={"room": "Penthouse"}
            ),
            "Anything in March?": reply_and_call(
                "I've opened the calendar.",
                "check_availability",
                args={"hotel_code": "EPAT", "month": "2027-03"},
            ),
            # Live run: a silent booking move, re-asked, made up a calendar and
            # read it out in brackets. Now the written line is said instead.
            "Can I go in March?": [
                call("check_availability", args={"hotel_code": "EATA"}),
                reply("[The booking calendar shows March 1 and March 2.]"),
            ],
            "What's on the screen?": reply(
                "The calendar is open. [Open arrival days: March 1.] Pick a day."
            ),
            # Prod call be1f5b9a: a Spanish call, a page opened, and every
            # sentence after it about the page in Spanish.
            "Quiero ver Patagonia.": reply(
                "Claro que sí. {page: /patagonia-travel-argentina-chile/}"
                "{show: Explora en la Patagonia} Explora tiene cinco lodges aquí. "
                "¿Te gusta caminar?"
            ),
            "Me está mostrando la página en inglés. ¿Se la puedes mostrar en español?": reply(
                "Te la muestro en español."
            ),
            # Prod call be1f5b9a, turns 13 to 16: four travellers, two rooms.
            "Somos cuatro, queremos dos suites.": reply_and_call(
                "Perfecto.", "choose_room", args={"room": "suite", "count": 2, "bed": "King"}
            ),
            "Agrega otra suite.": reply_and_call(
                "Claro.", "choose_room", args={"room": "suite", "count": 2}
            ),
            "Add it twice.": Reply(
                text="Adding it.",
                calls=(
                    ("choose_room", {"room": "Yali"}),
                    ("choose_room", {"room": "Yali"}),
                ),
            ),
            "Show me the rooms again.": Reply(
                text="Here they are.",
                calls=(
                    (
                        "check_availability",
                        {
                            "hotel_code": "EATA",
                            "date": "2026-11-06",
                            "show_rooms": True,
                        },
                    ),
                    (
                        "check_availability",
                        {
                            "hotel_code": "EATA",
                            "date": "2026-11-06",
                            "show_rooms": True,
                        },
                    ),
                ),
            ),
            # Prod call 80dac4ed: a heading made up for a page not yet seen.
            "What's here?": reply(
                "{show: Our Lodges Your Home Base for Adventure} Lodges everywhere. "
                "{show: Included with Your Stay} Everything is included."
            ),
            "Slow one.": reply(chunks=["It's an oasis.", " Truly."], chunk_delay=0.6),
            # A dev test on 2026-10-28: his right cue streamed as a sliver
            # ("{show"), was read as none, and the backstop's page won.
            "Is Atacama all inclusive?": reply(
                chunks=["{show", ": what's included", " in your stay}", " Everything is included."]
            ),
            # The lodges' index: one sentence names several things on it.
            "Where are your lodges?": reply(
                "Explora has lodges in Chile, Peru and Bolivia. "
                "In Peru, the Sacred Valley lodge sits among Inca villages. Which suits you?"
            ),
            # Dev call 2f94965e: the calendar claimed, twice, and never opened.
            "Can I go to Atacama in November? Three nights.": reply(
                "November is lovely. I'm opening the Atacama calendar for three nights."
            ),
            "You said you were opening the calendar but did not do it.": reply_and_call(
                "Opening it now.",
                "check_availability",
                args={"hotel_code": "EATA", "month": "2026-11"},
            ),
            # A follow-up that still does not keep it is not asked again.
            "Check Atacama for me.": reply("I'm checking availability for Atacama."),
            "You said you were checking availability but did not do it.": reply(
                "I'm checking availability now."
            ),
            # A booking sentence is never given a show cue by the backstop.
            "What's included?": reply("Everything is included with your stay."),
            "And the calendar?": reply("The calendar lists every night included with your stay."),
            # A heading written blind, close to one the page's crawl lists.
            "What about the nights?": reply(
                "{show: Stargaze From Explora Observatory} At night, there's the observatory."
            ),
        }
    )


@contextlib.asynccontextmanager
async def _explora(
    llm: ScriptedOpenAI, *, unanswered: tuple[str, ...] = ()
) -> AsyncIterator[DemoRig]:
    """The demo, with a stand-in for the page's Stage: every ``stage_move`` is
    answered ``applied`` as soon as it arrives, as the extension answers a move
    it made, except the moves in ``unanswered``, which a test answers itself.
    Cues are never answered: their words are never heard here."""
    async with demo("explora", llm) as rig:
        answered: set[str] = set()

        async def page() -> None:
            while True:
                for c in list(rig.driver.ui_commands):
                    if c.get("command") != "stage_move":
                        continue
                    move = c["payload"]
                    if move["call_ref"] in answered or move["move"] in unanswered:
                        continue
                    answered.add(move["call_ref"])
                    await _answer(rig, move, "applied", "made")
                await asyncio.sleep(0.01)

        task = asyncio.create_task(page())
        try:
            yield rig
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


async def _answer(rig: Any, move: dict[str, Any], outcome: str, detail: str) -> None:
    """The page's one ``stage_result`` for ``move``."""
    await rig.driver.send_ui_event(
        "stage_result",
        {"call_ref": move["call_ref"], "move": move["move"], "outcome": outcome, "detail": detail},
    )


async def _until(rig: Any, name: str, count: int) -> None:
    """Until the brain has sent ``count`` ``name`` commands (a site Action, or
    a Stage move by its id)."""
    for _ in range(300):
        if len(_commands(rig, name)) >= count:
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"no {name} #{count}: {_commands(rig, name)}")


#: The page's state, as the extension sends it: a Stage state event per slice.
_STATE_EVENTS = {
    "page_changed": "page.changed",
    "stay_state": "stay.changed",
    "enquiry_state": "enquiry.changed",
}


def _state_event(event: str, payload: dict[str, Any]) -> dict[str, Any]:
    """``payload`` as the extension's ``stage_event`` for the slice it changes:
    an enquiry's fields by name only, never what they hold."""
    data = dict(payload)
    if event == "enquiry_state":
        data["filled"] = [k for k, v in (payload.get("filled") or {}).items() if v]
    return {"name": _STATE_EVENTS[event], "by": "visitor", "data": data}


async def _page(rig: Any, event: str, payload: dict[str, Any]) -> None:
    if event in _STATE_EVENTS:
        await rig.driver.send_ui_event("stage_event", _state_event(event, payload))
    else:
        await rig.driver.send_ui_event(event, payload)
    # `on_rtvi` takes no floor and there is nothing to await: give it a moment.
    await asyncio.sleep(0.1)


def _commands(rig: Any, name: str) -> list[dict[str, Any]]:
    """The payloads of the site Action ``name``, or the arguments of the Stage
    move with that id (``explora.navigate``)."""
    if name.startswith("explora."):
        return [m["args"] for m in _stage(rig, "stage_move") if m["move"] == name]
    return [c["payload"] for c in rig.driver.ui_commands if c.get("command") == name]


def _stage(rig: Any, command: str) -> list[dict[str, Any]]:
    return [c["payload"] for c in rig.driver.ui_commands if c.get("command") == command]


def _cues(rig: Any) -> list[dict[str, Any]]:
    """Every ``stage_cue`` sent."""
    return _stage(rig, "stage_cue")


def _shown(rig: Any) -> list[str]:
    """What each ``show`` cue names, resolved to the page's own spelling."""
    return [c["args"][0] for c in _cues(rig) if c["move"] == "core.show"]


NAVIGATE = "explora.navigate"
TWIN = "explora.twin"


def _idle_windows(rig: Any) -> list[int | None]:
    return [c.idle.timeout_ms for c in _configs(rig) if c.idle is not None]


async def _says_while_pages_load(rig: Any, text: str, *pages: dict[str, Any]) -> Any:
    """The visitor says ``text``; each page he opens loads and reports itself,
    as the extension's next page does once the call has rejoined on it."""
    turn = asyncio.create_task(rig.driver.user_says(text))
    for page in pages:
        opened = len(_commands(rig, NAVIGATE))
        for _ in range(200):
            await asyncio.sleep(0.02)
            if len(_commands(rig, NAVIGATE)) > opened or turn.done():
                break
        await _page(rig, "page_changed", page)
    return await turn


# ─── Greeting and voice ────────────────────────────────────────────────────────


async def test_greeting_and_voice_reach_the_wire() -> None:
    """A written opener, and javier in English on both legs before it."""
    async with _explora(_llm()) as rig:
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
    async with _explora(_llm()) as rig:
        turn = await rig.driver.start_session(init={"site": "site", "path": "/", "lang": "es"})
        assert turn is not None and turn.text.startswith("Hola, soy Javier")
        check_voice_pair(rig, voice="omnivoice/javier", language="es")


async def test_a_call_on_the_spanish_site_starts_in_spanish() -> None:
    async with _explora(_llm()) as rig:
        turn = await rig.driver.start_session(
            init={"site": "site", "path": "/es/desierto-de-atacama/", "site_lang": "es"}
        )
        assert turn is not None and turn.text.startswith("Hola, soy Javier")
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        # Prod call be1f5b9a: the tab was never told, and took the first
        # English page's language for the call's. Told at once, and the page
        # the visitor started on stays as it is.
        assert _commands(rig, "language_changed") == [{"language": "es", "site": "stay"}]


ES_PATAGONIA_PAGE: dict[str, Any] = {
    **PATAGONIA_PAGE,
    "url": "https://www.explora.com/es/patagonia/",
    "path": "/es/patagonia/",
    "headings": ["Explora en la Patagonia", "EL CHALTÉN"],
}


async def test_an_english_page_in_a_spanish_call_is_loaded_again_in_spanish() -> None:
    """Prod call be1f5b9a: every page he opened in a Spanish call came up in
    English, and his Spanish cues all missed. The tab is asked for the page's
    own twin; his Spanish cue, which only the Spanish page can judge, is sent
    as he wrote it rather than dropped against the English crawl."""
    async with _explora(_llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/es/", "site_lang": "es"})
        turn = asyncio.create_task(rig.driver.user_says("Quiero ver Patagonia.", quiet_for=1.0))
        await _until(rig, NAVIGATE, 1)
        await _page(rig, "page_changed", PATAGONIA_PAGE)
        await _until(rig, TWIN, 1)
        assert _commands(rig, TWIN) == [{"language": "es"}]
        assert [m["when"] for m in _stage(rig, "stage_move") if m["move"] == TWIN] == ["quiet"]
        await _page(rig, "page_changed", ES_PATAGONIA_PAGE)
        said = await turn
        check_turn(rig, said)
        assert "Explora tiene cinco lodges aquí." in said.text
        assert _shown(rig) == ["Explora en la Patagonia"]


async def test_a_page_with_no_spanish_twin_lets_the_reply_go_on() -> None:
    llm = _llm()
    async with _explora(llm, unanswered=(TWIN,)) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/es/", "site_lang": "es"})
        turn = asyncio.create_task(rig.driver.user_says("Quiero ver Patagonia.", quiet_for=1.0))
        await _until(rig, NAVIGATE, 1)
        await _page(rig, "page_changed", PATAGONIA_PAGE)
        await _until(rig, TWIN, 1)
        twin = next(m for m in _stage(rig, "stage_move") if m["move"] == TWIN)
        await _answer(rig, twin, "refused", "/patagonia has no Spanish version")
        said = await turn
        assert "Explora tiene cinco lodges aquí." in said.text
        await rig.driver.user_says("Carry on.")
        assert "stays as it is (/patagonia has no Spanish version)" in _texts(
            llm.captured_inputs[-1]
        )


async def test_show_me_the_page_in_spanish_loads_it() -> None:
    """Prod call be1f5b9a, turn 5: "Ya la cambié a español", and nothing was
    sent to the page. Now the page's twin is asked for in code."""
    llm = _llm()
    async with _explora(llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/es/", "site_lang": "es"})
        await _page(rig, "page_changed", PATAGONIA_PAGE)
        await rig.driver.user_says(
            "Me está mostrando la página en inglés. ¿Se la puedes mostrar en español?"
        )
        assert _commands(rig, TWIN) == [{"language": "es"}]
        assert "loading in Spanish now" in _texts(llm.captured_inputs[-1])
        assert _commands(rig, NAVIGATE) == []


@pytest.mark.parametrize(
    ("text", "spoken", "page", "want"),
    [
        ("Me está mostrando la página en inglés. ¿Me la muestras en español?", "es", "en", "es"),
        ("La página está en inglés.", "es", "en", "es"),
        ("Can you show me the page in English?", "en", "es", "en"),
        # Already in it, or no page named: nothing to do.
        ("La página está en español.", "es", "es", None),
        ("¿Hablas inglés?", "es", "en", None),
        # The other language asked for is a request about the call.
        ("Can I see the page in Spanish?", "en", "en", None),
        ("Show me the page in Spanish.", "en", None, None),
    ],
)
def test_a_request_for_the_page_in_a_language(
    text: str, spoken: str, page: str | None, want: str | None
) -> None:
    assert asked_page_language(text, spoken, page) == want  # type: ignore[arg-type]


# ─── Full page loads ───────────────────────────────────────────────────────────


async def test_a_reply_opens_one_page_and_keeps_its_words() -> None:
    """A second page cue in the same reply is dropped: the screen stays on the
    page he is describing, and the words after the cue are still said."""
    async with _explora(_llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        turn = await _says_while_pages_load(rig, "Show me the desert.", ATACAMA_PAGE)
        check_turn(rig, turn)
        assert [c["path"] for c in _commands(rig, NAVIGATE)] == ["/lodge/atacama-lodge/"]
        assert "It's an oasis." in turn.text and "Patagonia is green." in turn.text
        assert "{" not in turn.text


async def test_a_page_cue_opens_the_page_at_once_and_the_reply_streams_on() -> None:
    """The page goes the moment the cue is read (``after_words`` 0: the
    extension keeps his voice playing through the load), in the same unit of
    speech; the cues after it go out after it, checked against that page."""
    async with _explora(_llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        turn = await _says_while_pages_load(rig, "Patagonia.", PATAGONIA_PAGE)
        check_turn(rig, turn, units=1)
        assert turn.text.startswith("Patagonia it is.")
        assert "Explora has five lodges here." in turn.text
        assert "{" not in turn.text
        navigate = _commands(rig, NAVIGATE)
        assert navigate == [{"path": "/patagonia-travel-argentina-chile/", "after_words": 0}]
        order = [
            c["command"]
            for c in rig.driver.ui_commands
            if c["command"] in ("stage_move", "stage_cue")
        ]
        assert order == ["stage_move", "stage_cue", "stage_cue"]
        # The page's spelling, anchored to the raw words that follow each.
        cues = _cues(rig)
        assert [c["args"] for c in cues] == [["OUR PATAGONIA LUXURY TRAVEL LODGES"], ["EL CHALTÉN"]]
        assert cues[0]["at"].startswith("Explora has five lodges here. El Chaltén")
        assert cues[1]["at"].startswith("El Chaltén is for hikers.")


async def test_the_page_being_left_reporting_again_is_not_the_new_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The extension re-reports a page whose parts render late; that is not
    the page he opened, so the reply still finds its page late."""
    monkeypatch.setattr(explora, "_PAGE_WAIT_S", 0.6)
    async with _explora(_llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        await _page(rig, "page_changed", ATACAMA_PAGE)
        task = asyncio.create_task(rig.driver.user_says("Patagonia.", quiet_for=1.5))
        await _until(rig, NAVIGATE, 1)
        await _page(rig, "page_changed", ATACAMA_PAGE)
        turn = await task
        assert any(line in turn.text for line in explora._PAGE_LATE["en"])


async def test_a_page_cue_first_adds_no_line_of_its_own() -> None:
    """A dev test on 2026-10-28: his nod, then "Let me show you.", then the
    page — four to seven seconds from question to page. Now the reply's own
    first words are said over the load, and nothing is added."""
    async with _explora(_llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        turn = await _says_while_pages_load(rig, "What is Explora?", HOME_PAGE)
        check_turn(rig, turn, units=1)
        assert turn.text.split() == (
            ["Lodges", "at", "the", "edge", "of", "the", "world.", "Everything", "is", "included."]
        )
        assert _commands(rig, NAVIGATE) == [{"path": "/", "after_words": 0}]
        assert _shown(rig) == ["Our Destinations", "What's Included in Your Stay"]


async def test_a_page_that_never_reports_lets_him_run_ahead_only_so_far(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """His voice carries on through the load for two sentences; past them the
    rest waits for the page, and a page that never comes is said plainly
    (prod call be1f5b9a said a whole reply over a page that never came)."""
    monkeypatch.setattr(explora, "_PAGE_WAIT_S", 0.2)
    async with _explora(_llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        # The driver calls a turn done after a quarter second of quiet; this one
        # is quiet for the length of the wait.
        turn = await rig.driver.user_says("Patagonia.", quiet_for=2.5)
        check_turn(rig, turn)
        assert turn.text.startswith("Patagonia it is.")
        assert "Explora has five lodges here. El Chaltén is for hikers." in turn.text
        assert any(line in turn.text for line in explora._PAGE_LATE["en"])
        assert "Do you love hiking?" not in turn.text


async def test_the_page_in_front_and_an_unknown_page_open_nothing() -> None:
    async with _explora(_llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        await _page(rig, "page_changed", ATACAMA_PAGE)
        turn = await rig.driver.user_says("Tell me again.")
        check_turn(rig, turn, units=1)
        assert _commands(rig, NAVIGATE) == []
        assert _shown(rig)[0] == "Welcome to Explora Atacama"
        assert "Truly." in turn.text


async def test_a_redirected_path_is_the_page_it_lands_on() -> None:
    assert SITE.page("/sacred-valley-peru/") is SITE.page("/lodge/atacama-lodge")


# ─── Cues on the page in front ─────────────────────────────────────────────────


async def test_cues_are_checked_against_the_tab_in_front() -> None:
    llm = _llm()
    async with _explora(llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await _page(rig, "page_changed", PATAGONIA_PAGE)
        await rig.driver.user_says("Why Explora?")
        # A tab's label opens the tab; words that are on no heading are rung.
        assert _shown(rig) == ["Custom-Made Explorations", "the red door"]
        seen = _texts(llm.captured_inputs[-1])
        assert "Its tabs and accordions: Award-Winning Lodges; Custom-Made Explorations" in seen
        assert "Its own sub-pages: /lodge/torres-del-paine-lodge/; /el-chalten-lodge/" in seen
        await _page(rig, "page_changed", HOME_PAGE)
        await rig.driver.user_says("Open Patagonia.")
        assert _cues(rig)[-1]["move"] == "core.faq"
        assert _cues(rig)[-1]["args"] == ["Patagonia [Argentina + Chile]"]


async def test_the_page_they_asked_about_opens_when_his_reply_forgets() -> None:
    async with _explora(_llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await _says_while_pages_load(rig, "Tell me about Atacama.", ATACAMA_PAGE)
        assert _commands(rig, NAVIGATE)[0]["path"] == "/lodge/atacama-lodge/"
    # Not from a page about the same place.
    async with _explora(_llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/atacama-travel-tips/"})
        await rig.driver.user_says("Tell me about Atacama.")
        assert _commands(rig, NAVIGATE) == []


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
    async with _explora(llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        await rig.driver.user_says("Can I go in November? Five nights.")
        assert _commands(rig, "explora.check_availability")[-1] == {
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
        # It landed: his written line first, in the short window, then the days.
        assert _idle_windows(rig)[-1] == LANDING_FLOOR_MS
        turn = await rig.driver.user_idle(level=1, idle_ms=LANDING_FLOOR_MS)
        check_turn(rig, turn)
        assert turn.text.startswith("Here's the Atacama calendar for November.")
        assert "Which suits you?" in turn.text
        seen = _texts(llm.captured_inputs[-1])
        assert "Open arrival days: Friday, November 6, 2026; Saturday, November 7, 2026" in seen

        await rig.driver.user_says("The sixth.")
        assert _commands(rig, "explora.check_availability")[-1]["date"] == "2026-11-06"
        # A day the calendar does not list is refused before it reaches the page.
        await rig.driver.user_says("The fifth of November.")
        # A tool's result reaches the model with the next request.
        await rig.driver.user_says("Carry on.")
        refused = _results(llm.captured_inputs[-1])["check_availability"]
        assert "not an open arrival day" in refused
        assert len(_commands(rig, "explora.check_availability")) == 2

        await rig.driver.user_says("Show me the rooms.")
        assert _commands(rig, "explora.check_availability")[-1]["rooms"] is True
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
        turn = await rig.driver.user_idle(level=1, idle_ms=LANDING_FLOOR_MS)
        assert turn.text.startswith("Here are the rooms at Atacama.")
        assert "You book it from here." in turn.text
        assert "Suite (from US$ 1,200 per night)" in _texts(llm.captured_inputs[-1])


async def test_an_expedition_enquiry_fills_and_sends_only_once_ticked() -> None:
    llm = _llm()
    async with _explora(llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/explora-expeditions/"})
        await rig.driver.user_says("I'd like the Sacred Mountains expedition. I'm Ana Díaz.")
        assert _commands(rig, "explora.fill_enquiry")[-1] == {
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
            in _results(llm.captured_inputs[-1])["fill_enquiry"]
        )
        filled = _commands(rig, "explora.fill_enquiry")[-1]
        assert filled["first_name"] == "Ana" and filled["email"] == "ana@example.com"
        assert filled["country"] is None
        await rig.driver.user_says("I'm from Mexico.")
        assert _commands(rig, "explora.fill_enquiry")[-1]["country"] == "Mexico"
        assert _commands(rig, "explora.fill_enquiry")[-1]["title"] == "Ms."

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
        assert "not ticked" in _results(llm.captured_inputs[-1])["send_enquiry"]
        assert _commands(rig, "explora.send_enquiry") == []

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
        assert _commands(rig, "explora.send_enquiry") == [{}]
        await _page(
            rig,
            "enquiry_sent",
            {"expedition": "Sacred Mountains Expedition", "by": "javier"},
        )
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert "Explora's team will write to you." in turn.text


async def test_he_speaks_up_once_about_an_enquiry_the_visitor_fills_in_by_themselves() -> None:
    """The spec lets him speak about the enquiry form (``react: speak``): the
    visitor types part of it and pauses, and he offers help in the next short
    quiet spell; another pause soon after is not commented on; their own words
    first always win. Nothing they typed is in what he is told."""
    llm = _llm()
    partial = {
        "expedition": "Sacred Mountains Expedition",
        "expedition_code": "XSCM",
        "filled": {"first_name": "Ana"},
        "missing": ["email", "phone"],
        "captcha": False,
    }
    async with _explora(llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        # The form comes up: his own line for it (what he needs from them)
        # comes first, as it always has.
        await _page(rig, "enquiry_state", {**partial, "filled": {}, "missing": ["first_name"]})
        await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert "filling in the enquiry form by themselves" not in _texts(llm.captured_inputs[-1])

        # They fill part of it themselves and pause: he speaks up about it.
        await _page(rig, "enquiry_state", partial)
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        said = _texts(llm.captured_inputs[-1])
        assert "filling in the enquiry form by themselves" in said
        assert "Ana" not in said

        # Another pause soon after: kept for its line, not spoken about.
        await _page(rig, "enquiry_state", {**partial, "missing": ["phone"]})
        assert _idle_windows(rig)[-1] != _TALK_THROUGH_MS


async def test_a_booking_move_the_page_could_not_make_is_said_plainly() -> None:
    """A ``stage_result`` that failed reaches the model as one plain line, and
    the next move of the same class goes out: the page answered this one."""
    llm = _llm()
    async with _explora(llm, unanswered=("explora.check_availability",)) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        await rig.driver.user_says("Can I go in November? Five nights.")
        move = next(m for m in _stage(rig, "stage_move") if m["move"].endswith("availability"))
        assert move["call_ref"] and move["when"] == "now"
        await _answer(rig, move, "failed", "the booking calendar is not on the page")
        await rig.driver.user_says("Carry on.")
        seen = _texts(llm.captured_inputs[-1])
        assert (
            "That did not happen on the page (the booking site's availability: the booking "
            "calendar is not on the page)" in seen
        )


async def test_a_cue_the_visitor_talked_over_is_no_failure() -> None:
    llm = _llm()
    async with _explora(llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        await _page(rig, "page_changed", ATACAMA_PAGE)
        await rig.driver.user_says("Tell me again.")
        cue = _cues(rig)[0]
        await rig.driver.send_ui_event(
            "stage_result",
            {
                "call_ref": cue["call_ref"],
                "move": cue["move"],
                "outcome": "refused",
                "detail": "interrupted",
                "refused": [{"arg": "show", "why": "interrupted"}],
            },
        )
        await asyncio.sleep(0.1)
        await rig.driver.user_says("Carry on.")
        assert "did not land" not in _texts(llm.captured_inputs[-1])


async def test_a_silent_booking_move_says_its_line_and_no_bracket_is_spoken() -> None:
    llm = _llm()
    async with _explora(llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        turn = await rig.driver.user_says("Can I go in March?")
        # Said before the page moves: it names no calendar not yet there.
        assert turn.text.strip() == "Let me pull that up."
        assert _commands(rig, "explora.check_availability")[-1]["hotel_code"] == "EATA"
        turn = await rig.driver.user_says("What's on the screen?")
        assert "[" not in turn.text and "March 1" not in turn.text
        assert "The calendar is open." in turn.text and "Pick a day." in turn.text


ROOMS_STATE: dict[str, Any] = {
    "step": "rooms",
    "hotel_code": "EATA",
    "date": "2026-11-06",
    "chosen_nights": 5,
    "rooms": [{"name": "Suite Catur"}, {"name": "Yali"}],
}
DATES_STATE: dict[str, Any] = {
    "step": "dates",
    "hotel_code": "EATA",
    "hotel": "Atacama, Chile",
    "month": "November 2026",
    "open_days": ["2026-11-06", "2026-11-07"],
}


async def test_a_talk_through_the_model_leaves_silent_is_read_from_the_page() -> None:
    """Prod call be1f5b9a: the calendar's open days were never said."""
    llm = ScriptedOpenAI(
        {
            "Can I go in November? Five nights.": reply_and_call(
                "Let's look at the calendar.",
                "check_availability",
                args={"hotel_code": "EATA", "nights": 5},
            ),
        },
        default=reply(""),
    )
    async with _explora(llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        await rig.driver.user_says("Can I go in November? Five nights.")
        await _page(rig, "stay_state", DATES_STATE)
        turn = await rig.driver.user_idle(level=1, idle_ms=LANDING_FLOOR_MS)
        assert turn.text.strip() == (
            "Here's the Atacama calendar for November. " + days_line(DATES_STATE["open_days"], "en")
        )


def test_the_calendar_read_out() -> None:
    assert spoken_day("2026-11-06", "en") == "Friday the sixth of November"
    assert spoken_day("2026-11-21", "es") == "el sábado veintiuno de noviembre"
    assert days_line(["2026-11-02", "2026-11-03"], "es") == (
        "Puedes llegar el lunes dos de noviembre o el martes tres de noviembre. "
        "¿Qué día te queda bien?"
    )
    six = [kb_nights(6, "6 noches (desde US$ 4.260 / noche)")]
    assert nights_line(six, 6, "es").startswith("Para 6 noches, desde 4260 dólares por noche")
    assert "Shall I show you the rooms?" in nights_line([], 0, "en")


def kb_nights(nights: int, label: str) -> Any:
    return explora.NightsOption(nights=nights, label=label)


async def test_the_screen_is_kept_in_the_mirror_and_read_whole() -> None:
    """The page's state arrives as Stage state events, folded into the
    mirror; the screen lines are cut short, and read_screen gives it whole."""
    headings = [f"Section {i}" for i in range(55)]
    llm = _llm()
    async with _explora(llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        await _page(rig, "page_changed", {**ATACAMA_PAGE, "headings": headings})
        await rig.driver.user_says("What's here?")
        seen = _texts(llm.captured_inputs[-1])
        assert "Section 39" in seen and "Section 50" not in seen
        brain = rig.brain  # type: ignore[attr-defined]
        assert brain.stage.mirror.version("page") == 1
        whole = await brain.read_screen(explora.ReadRequest(slice="page"))
        assert "version 1" in whole and "  - Section 54" in whole
        assert "read_screen" in [t.__name__ for t in brain.tools]
        # The old app event carries no state any more: it is not read.
        await rig.driver.send_ui_event("page_changed", {**ATACAMA_PAGE, "path": "/elsewhere/"})
        await asyncio.sleep(0.1)
        assert brain.page.path == "/lodge/atacama-lodge/"


async def test_the_enquiry_reaches_the_brain_by_field_name_only() -> None:
    llm = _llm()
    async with _explora(llm) as rig:
        await rig.driver.start_session(init={"site": "reservations", "path": "/ibe/expeditions"})
        await _page(
            rig,
            "enquiry_state",
            {
                "expedition": "Sacred Mountains Expedition",
                "expedition_code": "XSCM",
                "filled": {"first_name": "Ana", "email": "ana@example.com"},
                "missing": ["phone"],
                "captcha": False,
            },
        )
        brain = rig.brain  # type: ignore[attr-defined]
        assert brain.stage.mirror.value("enquiry")["filled"] == ["first_name", "email"]
        await rig.driver.user_says("What's left?")
        seen = _texts(llm.captured_inputs[-1])
        assert "Filled: first_name, email" in seen
        assert "Ana" not in seen and "ana@example.com" not in seen


async def test_a_heading_made_up_for_the_page_is_dropped() -> None:
    async with _explora(_llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        await _page(rig, "page_changed", ATACAMA_PAGE)
        await rig.driver.user_says("What's here?")
        assert _shown(rig) == ["Included with Your Stay"]


async def test_a_month_they_name_turns_the_calendar_to_it() -> None:
    async with _explora(_llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/", "lang": "es"})
        await rig.driver.user_says("Anything in March?")
        sent = _commands(rig, "explora.check_availability")[-1]
        assert sent["month"] == "2027-03" and sent["date"] is None
        # The booking site opens in the call's language.
        assert sent["language"] == "ES"


ZONES_PAGE: dict[str, Any] = {
    "site": "site",
    "url": "https://www.explora.com/machu-picchu-hiking-tours/",
    "path": "/machu-picchu-hiking-tours/",
    "title": "Machu Picchu Hiking Tours",
    "headings": ["Exploration Zones"],
    "faqs": ["1. Janca", "2. Quechua", "3. Suni", "4. Puna"],
}


async def test_items_he_names_in_passing_are_shown() -> None:
    async with _explora(_llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/machu-picchu-hiking-tours/"})
        await _page(rig, "page_changed", ZONES_PAGE)
        await rig.driver.user_says("Talk me through the zones.")
        assert [(c["move"], c["args"]) for c in _cues(rig)] == [
            ("core.faq", ["1. Janca"]),
            ("core.faq", ["3. Suni"]),
        ]


async def test_a_reply_that_was_only_a_dropped_page_cue_is_asked_again() -> None:
    async with _explora(_llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        await _page(rig, "page_changed", ATACAMA_PAGE)
        turn = await rig.driver.user_says("Show me explorations.")
        assert "nights under the stars" in turn.text


async def test_a_room_is_chosen_from_the_rooms_on_screen() -> None:
    llm = _llm()
    async with _explora(llm) as rig:
        await rig.driver.start_session(init={"site": "reservations", "path": "/ibe/paso2"})
        await _page(
            rig,
            "stay_state",
            {
                "step": "rooms",
                "hotel_code": "EATA",
                "date": "2026-11-06",
                "chosen_nights": 5,
                "rooms": [{"name": "Suite Catur"}, {"name": "Yali"}],
            },
        )
        await rig.driver.user_says("I'll take the suite, two of us, king bed.")
        assert _commands(rig, "explora.choose_room") == [
            {"room": "Suite Catur", "travellers": 2, "bed": "King", "count": 1}
        ]
        await rig.driver.user_says("Pick the penthouse.")
        await rig.driver.user_says("Carry on.")
        assert "no room 'Penthouse'" in _results(llm.captured_inputs[-1])["choose_room"]
        assert len(_commands(rig, "explora.choose_room")) == 1


async def test_more_rooms_for_a_bigger_party() -> None:
    """Prod call be1f5b9a: four travellers, and the second room was refused
    as already selected; a King bed was chosen that nobody asked for."""
    llm = _llm()
    async with _explora(llm) as rig:
        await rig.driver.start_session(
            init={"site": "reservations", "path": "/ibe/paso2", "lang": "es"}
        )
        await _page(rig, "stay_state", ROOMS_STATE)
        await rig.driver.user_says("Somos cuatro, queremos dos suites.")
        assert _commands(rig, "explora.choose_room") == [
            {"room": "Suite Catur", "travellers": None, "bed": None, "count": 2}
        ]
        # The same room again, in another turn, is another room.
        await rig.driver.user_says("Agrega otra suite.")
        assert len(_commands(rig, "explora.choose_room")) == 2
        # The same press twice in one turn is one press.
        await rig.driver.user_says("Add it twice.")
        assert [c["room"] for c in _commands(rig, "explora.choose_room")] == [
            "Suite Catur",
            "Suite Catur",
            "Yali",
        ]


async def test_the_same_availability_move_twice_while_loading_is_sent_once() -> None:
    async with _explora(_llm()) as rig:
        await rig.driver.start_session(init={"site": "reservations", "path": "/ibe/paso1"})
        await _page(rig, "stay_state", {**DATES_STATE, "date": "2026-11-06"})
        await rig.driver.user_says("Show me the rooms again.")
        assert len(_commands(rig, "explora.check_availability")) == 1


ATACAMA_LODGE_PAGE: dict[str, Any] = {
    **ATACAMA_PAGE,
    "links": [
        "/lodge/atacama-lodge/",
        "/atacama-desert-explora-lodge/",
        "/atacama-explorations/",
        "/gastronomy-in-atacama/",
        "/atacama-getting-there/",
    ],
}


async def test_a_lodge_sub_page_opens_when_his_reply_only_promises() -> None:
    """Dev call ed9846d5: "Show me the explorations." got "One moment." and
    nothing moved. The lodge's own explorations page opens first, and a
    reply that only promises is asked again."""
    async with _explora(_llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        await _page(rig, "page_changed", ATACAMA_LODGE_PAGE)
        turn = await _says_while_pages_load(
            rig,
            "Show me the explorations.",
            {**ATACAMA_PAGE, "path": "/atacama-explorations/", "headings": ["Explorations"]},
        )
        assert _commands(rig, NAVIGATE)[0]["path"] == "/atacama-explorations/"
        assert "Nearly fifty explorations" in turn.text


@pytest.mark.parametrize(
    ("text", "path"),
    [
        ("Show me the explorations", "/atacama-explorations/"),
        ("What's the food like?", "/gastronomy-in-atacama/"),
        ("How do I get there from the airport?", "/atacama-getting-there/"),
        ("Show me the rooms", "/atacama-desert-explora-lodge/"),
        ("Can you speak Spanish?", None),
    ],
)
def test_the_lodge_sub_page_for_what_they_asked(text: str, path: str | None) -> None:
    assert explora.asked_sub_page(text, ATACAMA_LODGE_PAGE["links"], "/lodge/atacama-lodge") == path


def test_a_numbered_one_word_heading_is_named() -> None:
    sections = [("1. Cuenca del salar", ""), ("3. Altiplano", ""), ("4. Montaña", "")]
    assert best_section("Then the Altiplano rises above four thousand metres.", sections) == (
        "3. Altiplano"
    )


EASTER_PAGE: dict[str, Any] = {
    "site": "site",
    "url": "https://www.explora.com/explorations-lodge/easter-island/",
    "path": "/explorations-lodge/easter-island/",
    "title": "Easter Island Explorations",
    "headings": ["All Explorations"],
    "links": ["/lodge/easter-island-hotels/", "/explora-lodge-easter-island-new/"],
}


async def test_a_page_its_own_tab_bar_links_opens_though_the_crawl_lacks_it() -> None:
    async with _explora(_llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": EASTER_PAGE["path"]})
        await _page(rig, "page_changed", EASTER_PAGE)
        turn = await _says_while_pages_load(
            rig,
            "Show me the room options.",
            {**EASTER_PAGE, "path": "/explora-lodge-easter-island-new/", "headings": ["OUR ROOMS"]},
        )
        assert _commands(rig, NAVIGATE)[0]["path"] == "/explora-lodge-easter-island-new/"
        # The holding line he copied is not said, and nothing is added for the load.
        assert turn.text.split() == ["Here", "are", "the", "rooms."]


async def test_switch_tab_with_one_tab_moves_nothing() -> None:
    llm = _llm()
    async with _explora(llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await rig.driver.user_says("Bring up the pricing tab.")
        await rig.driver.user_says("Carry on.")
        assert "only this one Explora tab" in _results(llm.captured_inputs[-1])["switch_tab"]
        assert _commands(rig, "explora.focus_tab") == []


@pytest.mark.parametrize(
    ("text", "path"),
    [
        # The thing named last is the one wanted.
        (
            "I'm still seeing the explorations, I can't see the rooms here.",
            "/atacama-desert-explora-lodge/",
        ),
        ("Show me the rooms and then the explorations", "/atacama-explorations/"),
    ],
)
def test_the_sub_page_named_last_is_the_one_wanted(text: str, path: str) -> None:
    links = ATACAMA_LODGE_PAGE["links"]
    assert explora.asked_sub_page(text, links, "/atacama-explorations") == path or (
        explora.asked_sub_page(text, links, "/lodge/atacama-lodge") == path
    )


@pytest.mark.parametrize(
    ("text", "here", "path"),
    [
        ("Can you go back to the other lodges available?", "/ibe/paso2", "/destinations/"),
        ("Show me all the lodges", "/", "/destinations/"),
        ("Show me the lodges", "/destinations", None),
        # A dev test on 2026-10-28: "the lodges" asked on /lodge/ took the
        # visitor off it, and his cues for its country headings were refused.
        ("Walk me through the lodges", "/lodge/", None),
        ("Walk me through the lodges", "/lodge", None),
        ("Muéstrame los lodges", "/es/lodge/", None),
        # A place named wins over "lodges".
        ("Show me the lodges in Atacama", "/", "/lodge/atacama-lodge/"),
    ],
)
def test_all_the_lodges(text: str, here: str, path: str | None) -> None:
    assert asked_page(text, here) == path


def test_a_page_that_lists_the_lodges_keeps_them() -> None:
    assert asked_page("Show me all the lodges", "/explora-hotels", lists_lodges=True) is None
    assert explora.listed_items(SITE.page("/lodge")) == [
        "El Calafate",
        "Torres del Paine",
        "Sacred Valley",
        "Atacama",
        "Easter Island",
    ]


LODGES_PAGE: dict[str, Any] = {
    "site": "site",
    "url": "https://www.explora.com/lodge/",
    "path": "/lodge/",
    "title": "Lodges Archive - Explora Hotels",
    "headings": ["OUR LODGES", "BOLIVIA", "CHILE", "PERU"],
}


async def test_the_lodges_asked_for_on_their_own_page_stay_there() -> None:
    async with _explora(_llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/"})
        await _page(rig, "page_changed", LODGES_PAGE)
        await rig.driver.user_says("Where are your lodges?")
        assert _commands(rig, NAVIGATE) == []


async def test_a_sentence_naming_several_things_rings_each_at_its_word() -> None:
    """One-word headings the page reports (CHILE, PERU, BOLIVIA) ring, and a
    sentence that names several gets a cue for each, in spoken order, each
    anchored at the word that names it; the lodges the page lists by name
    ring as words."""
    async with _explora(_llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/"})
        await _page(rig, "page_changed", LODGES_PAGE)
        await rig.driver.user_says("Where are your lodges?")
        cues = _cues(rig)
        assert [c["args"] for c in cues] == [
            ["CHILE"],
            ["PERU"],
            ["BOLIVIA"],
            ["PERU"],
            ["Sacred Valley"],
        ]
        assert [c["at"].split()[0] for c in cues] == [
            "Chile,",
            "Peru",
            "Bolivia.",
            "Peru,",
            "Sacred",
        ]
        # Each at its own word, not all at the sentence's start.
        befores = [c["before"] for c in cues]
        assert befores == sorted(befores) and len(set(befores)) == len(befores)
        assert all(c["move"] == "core.show" for c in cues)


def test_names_in_spoken_order_longest_first() -> None:
    labels = [("TORRES DEL PAINE", True), ("Torres del Paine C. Reserve", True), ("PERU", True)]
    sentence = "Torres del Paine C. Reserve is quieter, and Peru is warm."
    assert explora.names_in(sentence, labels) == [
        (0, "Torres del Paine C. Reserve"),
        (sentence.index("Peru"), "PERU"),
    ]
    # One word of a crawled heading is not a name; a closing offer names nothing.
    assert explora.names_in("Peru is warm.", [("PERU", False)]) == []
    assert explora.names_in("Would Peru suit you?", labels) == []


async def test_his_own_cue_streamed_as_slivers_keeps_him_on_the_page() -> None:
    async with _explora(_llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await _page(rig, "page_changed", HOME_PAGE)
        turn = await rig.driver.user_says("Is Atacama all inclusive?")
        assert _commands(rig, NAVIGATE) == []
        assert _shown(rig) == ["What's Included in Your Stay"]
        assert "Everything is included." in turn.text


async def test_a_heading_written_blind_is_matched_to_the_crawl_before_it_is_dropped() -> None:
    async with _explora(_llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        await _page(rig, "page_changed", ATACAMA_PAGE)
        await rig.driver.user_says("What about the nights?")
        assert _shown(rig) == ["Stargaze from Explora\u2019s Observatory"]


def test_the_prompt_walks_a_page_of_lodges_item_by_item() -> None:
    prompt = explora._prompt(SITE)
    assert "NAME AND CUE EACH ONE" in prompt
    assert "{show: El Calafate} El Calafate" in prompt
    assert "Never make up a heading for a page you have not seen." in prompt
    assert (
        "(names it lists: El Calafate; Torres del Paine; Sacred Valley; Atacama; Easter Island)"
        in prompt
    )


def test_countries_and_hotels_are_found_by_name() -> None:
    assert SITE.country("mexico") == ("MX", "Mexico")
    assert SITE.country("US") == ("US", "United States")
    assert SITE.country("Narnia") is None
    hotel = SITE.hotel("Torres del Paine")
    assert hotel is not None and hotel.code == "EPAT"


# ─── Language ──────────────────────────────────────────────────────────────────


async def test_spanish_heard_moves_both_legs_before_he_answers() -> None:
    async with _explora(_llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        await rig.driver.user_says("¿Cuánto cuesta una noche en Atacama? Quiero ver los precios.")
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert {"language": "es", "site": "follow"} in _commands(rig, "language_changed")


async def test_the_toggle_switches_and_confirms_in_the_new_language() -> None:
    async with _explora(_llm()) as rig:
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


# ─── A slow booking site is not a failed move ──────────────────────────────────


async def test_a_slow_move_gets_one_holding_line_and_a_late_answer_corrects_the_unknown() -> None:
    llm = _llm()
    async with _explora(llm, unanswered=("explora.check_availability",)) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        # The brain's Stage clock (and only it) runs ahead of the wall clock.
        ahead = [0.0]
        rig.brain.stage._clock = lambda: time.monotonic() + ahead[0]  # type: ignore[attr-defined]
        await rig.driver.user_says("Can I go in November? Five nights.")
        move = next(m for m in _stage(rig, "stage_move") if m["move"].endswith("availability"))
        # The page says it is still at it: parsed, and the move given its time again.
        ahead[0] = 7.0
        await _page(
            rig,
            "stage_progress",
            {"call_ref": move["call_ref"], "move": move["move"], "phase": "loading", "ms": 7000},
        )
        await asyncio.sleep(0.7)  # the brain's look for slow moves
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        asked = len(llm.requests)
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert turn.text in explora._HOLDING["explora.check_availability"]["en"]
        assert not re.search(r"slow|lent[ao]", turn.text, re.IGNORECASE)
        assert len(llm.requests) == asked
        # Its time runs out on the timer, with no turn of his: unknown.
        ahead[0] = 7.0 + 21.0
        await asyncio.sleep(0.5)
        # The page answers after all: a correction for his next turn.
        await _answer(rig, move, "applied", "the calendar for Atacama is open")
        await asyncio.sleep(0.1)
        await rig.driver.user_says("Carry on.")
        seen = _texts(llm.captured_inputs[-1])
        assert "[The page did not answer the booking site's availability" in seen
        assert (
            "[Correction: the booking site's availability did happen after all "
            "(the calendar for Atacama is open)." in seen
        )


# ─── The committed crawl ───────────────────────────────────────────────────────


def test_the_committed_crawl_loads_and_every_asked_page_exists() -> None:
    real = kb.load()
    assert len(real.pages) > 50
    assert {h.code for h in real.hotels} >= {"EATA", "EPAT", "XSCM"}
    assert real.country("Mexico") == ("MX", "Mexico")
    for _, path, _ in explora._ASKED_PAGES:
        assert real.page(path) is not None, path
    assert "OUR DESTINATIONS" in real.page("/destinations/").headings  # type: ignore[union-attr]


# ─── Promises, and the nights they said ───────────────────────────────────────


async def test_a_claimed_calendar_is_called_in_one_follow_up_with_their_nights() -> None:
    """Dev call 2f94965e: "I'm opening the Atacama calendar for three nights",
    and no tool call. The turn is asked once more, with the tool forced, and
    the nights the visitor said reach the page though the model left them out."""
    llm = _llm()
    async with _explora(llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        await _page(rig, "page_changed", ATACAMA_PAGE)
        asked = len(llm.requests)
        turn = await rig.driver.user_says("Can I go to Atacama in November? Three nights.")
        assert len(llm.requests) == asked + 2
        note = "[You said you were opening the calendar but did not do it. Do it now.]"
        assert note in _texts(llm.captured_inputs[-1])
        assert llm.requests[-1]["tool_choice"] == _FORCED
        assert "Atacama calendar" in turn.text and "Opening it now." in turn.text
        assert _commands(rig, "explora.check_availability") == [
            {
                "hotel_code": "EATA",
                "date": None,
                "month": "2026-11",
                "nights": 3,
                "rooms": False,
                "language": "EN",
            }
        ]
        # The claim rang nothing: the backstop leaves a booking sentence alone.
        assert _shown(rig) == []


async def test_a_follow_up_is_asked_once_a_turn() -> None:
    llm = _llm()
    async with _explora(llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        asked = len(llm.requests)
        await rig.driver.user_says("Check Atacama for me.")
        assert len(llm.requests) == asked + 2
        assert _commands(rig, "explora.check_availability") == []


async def test_the_sites_default_nights_are_never_theirs() -> None:
    llm = _llm()
    async with _explora(llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        await _page(rig, "stay_state", {**DATES_STATE, "date": "2026-11-06", "chosen_nights": 5})
        await rig.driver.user_says("Carry on.")
        seen = _texts(llm.captured_inputs[-1])
        assert "Selected: 5 nights, the site's default, not their choice." in seen
        assert _commands(rig, "explora.check_availability") == []


async def test_the_nights_they_said_replace_the_sites_without_asking() -> None:
    llm = _llm()
    async with _explora(llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        await rig.driver.user_says("Can I go to Atacama in November? Three nights.")
        nights = [
            {"nights": 3, "label": "3 nights (from US$ 1,000 / night)"},
            {"nights": 5, "label": "5 nights (from US$ 900 / night)"},
        ]
        day = {**DATES_STATE, "date": "2026-11-06", "nights": nights}
        await _page(rig, "stay_state", {**day, "chosen_nights": 5})
        # Set at once, by the brain, with the day the page is on.
        await _until(rig, "explora.check_availability", 2)
        sent = _commands(rig, "explora.check_availability")[-1]
        assert (sent["date"], sent["nights"]) == ("2026-11-06", 3)
        await _page(rig, "stay_state", {**day, "chosen_nights": 3})
        # The nights landed: his line first, at once.
        assert _idle_windows(rig)[-1] == LANDING_FLOOR_MS
        turn = await rig.driver.user_idle(level=1, idle_ms=LANDING_FLOOR_MS)
        assert turn.text.startswith("Here are the stays arriving Friday the sixth of November.")
        seen = _texts(llm.captured_inputs[-1])
        assert "Selected: 5 nights, the site's choice, not theirs: they asked for 3." in seen
        assert "Setting the 3 nights they asked for now." in seen
        assert "Selected: 3 nights, as they asked." in seen
        assert "without asking them about the nights" in seen
        # Once a day: the page's nearest is not fought over.
        assert len(_commands(rig, "explora.check_availability")) == 2


# ─── A move that lands is said at once ─────────────────────────────────────────

#: No line of his ever blames the site for being slow.
_BLAMES = re.compile(r"slow|lent[ao]", re.IGNORECASE)


async def test_the_calendar_that_lands_is_said_at_once_and_gets_no_holding_line() -> None:
    llm = _llm()
    async with _explora(llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        ahead = [0.0]
        rig.brain.stage._clock = lambda: time.monotonic() + ahead[0]  # type: ignore[attr-defined]
        await rig.driver.user_says("Can I go in November? Five nights.")
        await _page(rig, "stay_state", DATES_STATE)
        # Within the short window, not the three-second talk-through.
        assert _idle_windows(rig)[-1] == LANDING_FLOOR_MS == 300
        # Past the holding time, its result still out: no holding line.
        ahead[0] = 7.0
        await asyncio.sleep(0.7)
        assert rig.brain._hold is None  # type: ignore[attr-defined]
        asked = len(llm.requests)
        turn = await rig.driver.user_idle(level=1, idle_ms=LANDING_FLOOR_MS)
        check_turn(rig, turn)
        # Written, said before the model was asked anything.
        assert turn.text.startswith("Here's the Atacama calendar for November.")
        assert not _BLAMES.search(turn.text)
        assert len(llm.requests) == asked + 1
        seen = _texts(llm.captured_inputs[-1])
        assert 'You have just said: "Here\'s the Atacama calendar for November."' in seen
        assert "In one more sentence at most: The booking calendar is on their screen" in seen
        await rig.driver.user_says("Carry on.")
        assert "Still working on the page" not in _texts(llm.captured_inputs[-1])


async def test_a_page_that_comes_up_after_his_reply_is_said_in_spanish_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(explora, "_PAGE_WAIT_S", 0.2)
    async with _explora(_llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        await rig.driver.user_says("Patagonia.", quiet_for=2.5)
        # The page comes up after all, his reply over: its line, at once.
        await _page(rig, "page_changed", PATAGONIA_PAGE)
        assert _idle_windows(rig)[-1] == LANDING_FLOOR_MS
        turn = await rig.driver.user_idle(level=1, idle_ms=LANDING_FLOOR_MS)
        assert turn.text.startswith("Here's Explora Patagonia Travel.")
    event = explora.StayState.model_validate({**DATES_STATE, "month": "Noviembre 2026"})
    assert explora.stay_landed_line(event, "Atacama", "es") == (
        "Aquí está el calendario de Atacama para noviembre."
    )


def test_no_written_line_blames_the_site() -> None:
    lines = [
        line for by_lang in explora._HOLDING.values() for said in by_lang.values() for line in said
    ]
    lines += [line for said in explora._PAGE_LATE.values() for line in said]
    lines += [line for by_lang in explora._LANDED.values() for line in by_lang.values()]
    assert len(lines) > 20
    assert [line for line in lines if _BLAMES.search(line)] == []
    # Two or three lines a move, in each language, so the line varies.
    assert all(2 <= len(said) <= 3 for v in explora._HOLDING.values() for said in v.values())
    prompt = explora._prompt(explora.kb.KNOWLEDGE)
    assert "can be slow" not in prompt
    assert "Never say the site, the booking site or the page is slow" in prompt


async def test_the_backstop_shows_nothing_on_a_booking_sentence() -> None:
    async with _explora(_llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/lodge/atacama-lodge/"})
        await _page(rig, "page_changed", ATACAMA_PAGE)
        await rig.driver.user_says("What's included?")
        assert _shown(rig) == ["Included with Your Stay"]
        await rig.driver.user_says("And the calendar?")
        assert _shown(rig) == ["Included with Your Stay"]


def test_the_nights_a_visitor_says() -> None:
    assert explora.nights_said("Can I go in November? Three nights.") == 3
    assert explora.nights_said("Quiero ir 4 noches, no, cinco noches") == 5
    assert explora.nights_said("A night under the stars") is None
    assert explora.nights_said("What's on tonight?") is None


# ─── Dev call 453f2e19: a promise in words, and no call ────────────────────────

#: The tool choice of a forced follow-up.
_FORCED = {"type": "function", "name": "check_availability"}


def _promising() -> ScriptedOpenAI:
    """The three responses of dev call 453f2e19 that said the move and called
    nothing, each followed by the forced call, which comes back silent."""
    return ScriptedOpenAI(
        {
            "Can I see Torres del Paine in November?": reply(
                "I'll open the calendar. I'm checking Torres del Paine for November."
            ),
            "You said \u201cI'll open the calendar.\u201d": call(
                "check_availability", args={"hotel_code": "EPAT", "month": "2026-11"}
            ),
            "We'd like three nights, please.": reply(
                "I'm selecting three nights to see the rates."
            ),
            "You said you were selecting three nights": call(
                "check_availability",
                args={"hotel_code": "EATA", "date": "2026-11-06", "nights": 3},
            ),
            "Rates for three nights from the sixth?": reply(
                "Happy to help. I'm opening the rooms and rates for your three nights."
            ),
            "You said you were opening the rooms": call(
                "check_availability",
                args={
                    "hotel_code": "EATA",
                    "date": "2026-11-06",
                    "nights": 3,
                    "show_rooms": True,
                },
            ),
            "Show me the rates.": call(
                "check_availability", args={"hotel_code": "EATA", "nights": 3}
            ),
            # On the booking site, a reply that cues the www site's sections.
            "What's included here?": reply(
                "{show: Included with Your Stay} Everything is included. "
                "{faq: Patagonia} Even the explorations."
            ),
        }
    )


@pytest.mark.parametrize(
    ("said", "note", "sent"),
    [
        (
            "Can I see Torres del Paine in November?",
            "[You said \u201cI'll open the calendar.\u201d but did not do it. Do it now.]",
            {
                "hotel_code": "EPAT",
                "date": None,
                "month": "2026-11",
                "nights": None,
                "rooms": False,
            },
        ),
        (
            "We'd like three nights, please.",
            "[You said you were selecting three nights but did not do it. Do it now.]",
            {
                "hotel_code": "EATA",
                "date": "2026-11-06",
                "month": None,
                "nights": 3,
                "rooms": False,
            },
        ),
        (
            "Rates for three nights from the sixth?",
            "[You said you were opening the rooms but did not do it. Do it now.]",
            {"hotel_code": "EATA", "date": "2026-11-06", "month": None, "nights": 3, "rooms": True},
        ),
    ],
)
async def test_a_promise_in_words_gets_one_forced_call(
    said: str, note: str, sent: dict[str, Any]
) -> None:
    llm = _promising()
    async with _explora(llm) as rig:
        await rig.driver.start_session(init={"site": "reservations", "path": "/ibe/paso1"})
        if sent["date"]:
            await _page(rig, "stay_state", {**DATES_STATE, "date": "2026-11-06"})
        asked = len(llm.requests)
        turn = await rig.driver.user_says(said)
        # One follow-up, with the tool forced and the note that says why.
        assert len(llm.requests) == asked + 2
        assert llm.requests[-1]["tool_choice"] == _FORCED
        assert note in _texts(llm.captured_inputs[-1])
        assert _commands(rig, "explora.check_availability") == [{**sent, "language": "EN"}]
        # The forced call is silent: his written line says it, naming no
        # screen that has not come up.
        line = (
            "Let me pull those up."
            if sent["rooms"]
            else "Let me pick that day."
            if sent["date"]
            else "Let me pull that up."
        )
        assert turn.text.strip().endswith(line)


async def test_rates_with_the_day_and_nights_known_go_to_the_rooms() -> None:
    """Dev call 453f2e19: "show me the rates", the day and nights known, took
    a nights step instead of the rooms."""
    llm = _promising()
    async with _explora(llm) as rig:
        await rig.driver.start_session(init={"site": "reservations", "path": "/ibe/paso1"})
        await rig.driver.user_says("We'd like three nights, please.")
        await _page(rig, "stay_state", {**DATES_STATE, "date": "2026-11-06", "chosen_nights": 3})
        await rig.driver.user_says("Show me the rates.")
        sent = _commands(rig, "explora.check_availability")[-1]
        assert (sent["date"], sent["nights"], sent["rooms"]) == ("2026-11-06", 3, True)
    assert "show_rooms at once" in explora._prompt(explora.kb.KNOWLEDGE)


async def test_no_section_is_cued_on_the_booking_site() -> None:
    """Dev call 453f2e19: every show cue on reservations.explora.com was
    refused; none is sent there, the backstop's included."""
    async with _explora(_promising()) as rig:
        await rig.driver.start_session(init={"site": "reservations", "path": "/ibe/paso1"})
        turn = await rig.driver.user_says("What's included here?")
        assert "Everything is included." in turn.text and "{" not in turn.text
        assert _cues(rig) == []


def test_a_booking_step_is_a_silent_call_in_the_prompt() -> None:
    prompt = explora._prompt(explora.kb.KNOWLEDGE)
    assert "call its tool and write NO words in that response" in prompt
    assert "in the response that announces it" not in prompt
    assert "say you are sending it, and call send_enquiry" not in prompt
