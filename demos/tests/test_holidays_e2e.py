"""Wanderloom Holidays, end to end over the wire — no network, no LLM key.

The real :class:`HolidaysBrain` on a real ``brain_server`` socket, driven by the
conformance ``VoqalizeDriver``; only the model is scripted
(:class:`~voqalize_demos.testing.ScriptedOpenAI`, flat tool arguments). Each
landing page's main flow: the home page helps choose a destination and starts
the brief; the trip builder takes a brief in one sentence, builds a priced
package, edits it item by item ("swap the hotel in Ubud for something by the
beach"), takes the visitor's own clicks, and ends at checkout with the visitor
paying. Plus the language: English or Hindi from the page, and a switch mid-call;
and redial: a call whose brain socket drops picks up where it was.

Run: ``cd demos && uv run pytest tests/test_holidays_e2e.py``
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from voqalize_demos.discovery import discover
from voqalize_demos.testing import (
    ScriptedOpenAI,
    call,
    input_texts,
    replies,
    reply,
    reply_and_call,
    tool_results_of,
)

from voqalize.conformance import VoqalizeDriver
from voqalize.sdk.wire import ConfigureFrame

from ._harness import DemoRig, check_greeting, check_turn, check_voice_pair, demo, demo_from

discover()

from voqalize_demos._loaded.holidays import engine as eng  # noqa: E402
from voqalize_demos._loaded.holidays.brain import HolidaysBrain  # noqa: E402
from voqalize_demos._loaded.holidays.persona import LANGUAGES  # noqa: E402

TODAY = date(2026, 11, 18)


@pytest.fixture(autouse=True)
def _no_call_carried_between_tests() -> Iterator[None]:
    """Every test here opens the same session id, and a dropped call is held for
    a redial to rejoin (CONTRACT.md, Redial): clear the store around each test,
    so no test rejoins the one before it. Real session ids never repeat."""
    from voqalize_demos._loaded.holidays.brain import REJOIN

    REJOIN.clear()
    yield
    REJOIN.clear()


def _moves(rig: DemoRig) -> list[dict[str, Any]]:
    return [
        dict(c.get("payload") or {})
        for c in rig.driver.ui_commands
        if c.get("command") == "stage_move"
    ]


def _move(rig: DemoRig, move: str) -> dict[str, Any]:
    found = [m for m in _moves(rig) if m["move"] == move]
    assert found, f"no {move} move; sent: {[m['move'] for m in _moves(rig)]}"
    return found[-1]


async def _page_answers(rig: DemoRig, answered: set[str]) -> None:
    """The page lands every move it was sent (so the queue moves on)."""
    await _lands(rig.driver, answered)


async def _lands(driver: VoqalizeDriver, answered: set[str]) -> None:
    for _ in range(4):
        new = [
            dict(c.get("payload") or {})
            for c in driver.ui_commands
            if c.get("command") == "stage_move"
        ]
        new = [m for m in new if m["call_ref"] not in answered]
        if not new:
            return
        for m in new:
            answered.add(m["call_ref"])
            await driver.send_ui_event(
                "stage_result",
                {
                    "call_ref": m["call_ref"],
                    "move": m["move"],
                    "outcome": "applied",
                    "detail": "done",
                },
            )
        await asyncio.sleep(0.05)


def _brain(rig: DemoRig) -> HolidaysBrain:
    assert isinstance(rig.brain, HolidaysBrain)
    return rig.brain


def _rig(llm: ScriptedOpenAI):
    return demo_from("holidays", lambda: HolidaysBrain(client=llm, today=TODAY))  # type: ignore[arg-type]


async def test_the_trip_builder_takes_a_brief_builds_edits_and_checks_out() -> None:
    llm = ScriptedOpenAI(
        {
            "Delhi to Bali": replies(
                call(
                    "set_trip",
                    from_city="Delhi",
                    destination="Bali",
                    month="February",
                    nights=6,
                    adults=2,
                    style="honeymoon",
                ),
                reply("Lovely. Shall I build the whole package, or go step by step?"),
            ),
            "build the whole thing": replies(
                call("build_package"),
                reply("{show: total} Here it is, all in, with two nights' worth of plans in Ubud."),
            ),
            "by the beach": replies(
                call("show_hotels", city="Ubud", want="beach"),
                reply(
                    "Ubud is inland, so the beach hotels are in Seminyak. Want another night there?"
                ),
            ),
            "move a night": reply_and_call(
                "Moving a night to Seminyak.", "set_nights", city="Seminyak", nights=4
            ),
            "the flights": replies(
                call("show_flights"),
                reply("{show: flight 1} The first is the nonstop-free best value."),
            ),
            "second one": reply_and_call("Done.", "choose_flight", choice="2"),
            "sunrise trek": reply_and_call(
                "Adding it.", "add_activity", activity="Mount Batur sunrise trek", day=2
            ),
            "let's book": reply_and_call("Opening the review page.", "go_to_checkout"),
        }
    )
    answered: set[str] = set()
    async with _rig(llm) as rig:
        greeting = await rig.driver.start_session(init={"page": "plan", "lang": "en"})
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text == LANGUAGES["en"].greeting_plan
        check_voice_pair(rig, voice=LANGUAGES["en"].voice, language="en")
        brain = _brain(rig)

        # The brief, in one sentence.
        t1 = await rig.driver.user_says(
            "Delhi to Bali in February for six nights, my wife and I, it's our honeymoon"
        )
        check_turn(rig, t1)
        brief = _move(rig, "trip.brief")["args"]
        assert brief == {
            "from_city": "DEL",
            "destination": "bali",
            "start_date": "2027-02-12",
            "nights": 6,
            "style": "honeymoon",
        }, brief
        result = tool_results_of(llm.captured_inputs[-1], "set_trip")[0]
        assert "The brief is complete" in result
        assert "Fri 12 Feb 2027" in result
        assert brain.trip.split == [3, 3]
        await _page_answers(rig, answered)

        # The whole package, priced by the engine the page uses too.
        t2 = await rig.driver.user_says("Just build the whole thing for us")
        check_turn(rig, t2)
        built = _move(rig, "trip.build")["args"]
        expected = eng.build_package(brain.trip)
        assert built["flight_id"] == expected.flight_id == "DEL-bali-2"
        assert built["hotels"] == ["ubud:sayan-ridge:pool-villa", "seminyak:seminyak-shore:ocean"]
        assert built["activities"][0] == "1:ubud-kecak"
        package = tool_results_of(llm.captured_inputs[-1], "build_package")[0]
        total = eng.price(brain.trip).total
        assert eng.money(total) in package and "GST" in package
        assert "Day 7" in package and "fly home" in package
        await _page_answers(rig, answered)

        # "Swap the hotel in Ubud for something by the beach": Ubud is inland.
        t3 = await rig.driver.user_says(
            "Can you swap the hotel in Ubud for something by the beach?"
        )
        check_turn(rig, t3)
        hotels = tool_results_of(llm.captured_inputs[-1], "show_hotels")[0]
        assert "No hotel in Ubud fits 'beach'. It is inland." in hotels
        assert "Seminyak Shore Resort" in hotels
        assert _move(rig, "trip.hotels")["args"] == {"city": "ubud"}
        await _page_answers(rig, answered)

        # Move a night to the beach; the itinerary follows.
        t4 = await rig.driver.user_says("Then move a night to Seminyak")
        check_turn(rig, t4)
        assert _move(rig, "trip.nights")["args"] == {"split": ["2", "4"]}
        assert brain.trip.split == [2, 4]
        assert all(eng.can_add(brain.trip, a, d) is not None for d, a in brain.trip.activities)
        await _page_answers(rig, answered)

        # The visitor picks a room by hand: the brain's trip follows, and the
        # model hears it, with the new total.
        await rig.driver.send_ui_event(
            "stage_event",
            {
                "name": "trip.hotel_picked",
                "by": "visitor",
                "data": {
                    "city": "seminyak",
                    "hotel_id": "petitenget-villas",
                    "room_id": "one-bed",
                    "label": "Petitenget Pool Villas, One-bedroom Pool Villa, in Seminyak",
                },
            },
        )
        await asyncio.sleep(0.1)
        assert brain.trip.hotels["seminyak"] == ("petitenget-villas", "one-bed")

        t5 = await rig.driver.user_says("And what are the flights?")
        check_turn(rig, t5)
        heard = input_texts(llm.captured_inputs[-2])
        assert "The visitor picked Petitenget Pool Villas" in heard
        assert eng.money(eng.price(brain.trip).total) in heard
        flights = tool_results_of(llm.captured_inputs[-1], "show_flights")[0]
        assert flights.startswith("2 options from Delhi")
        assert "1. Lagoon Air" in flights and "(suggested" in flights
        assert "18% " not in flights  # no invented numbers: season is said in words
        await _page_answers(rig, answered)

        t6 = await rig.driver.user_says("Take the second one")
        check_turn(rig, t6)
        assert brain.trip.flight_id == "DEL-bali-1"
        assert _move(rig, "trip.flight")["args"] == {"flight_id": "DEL-bali-1"}
        await _page_answers(rig, answered)

        # A full-day trek on a day whose morning is taken is refused, with the days it fits.
        t7 = await rig.driver.user_says("Add the sunrise trek on day 2")
        check_turn(rig, t7)
        await _page_answers(rig, answered)

        t8 = await rig.driver.user_says("Looks great, let's book")
        check_turn(rig, t8)
        trek = tool_results_of(llm.captured_inputs[-1], "add_activity")[0]
        assert trek == "Not added: the morning of day 2 is already taken.", trek
        assert ("2", "ubud-batur-trek") not in [(str(d), a) for d, a in brain.trip.activities]
        assert _move(rig, "trip.go")["args"] == {"page": "checkout"}
        await _page_answers(rig, answered)

        # The visitor pays by hand; the planner says the reference in the next quiet spell.
        await rig.driver.send_ui_event(
            "stage_event",
            {"name": "trip.paid", "by": "visitor", "data": {"reference": "WL-482913", "total": 1}},
        )
        await asyncio.sleep(0.1)
        assert brain.booked == "WL-482913"
        assert brain._say_next is not None  # pyright: ignore[reportPrivateUsage]
        assert "W L - 4 8 2 9 1 3" in brain._say_next()  # pyright: ignore[reportPrivateUsage]

    # Every move the brain sent is one the page declares, and nothing else went to the page.
    assert all(c.get("command") in ("stage_move", "stage_cue") for c in rig.driver.ui_commands)
    assert llm.requests[0]["reasoning"] == {"effort": "medium"}


async def test_the_home_page_helps_choose_and_starts_the_brief() -> None:
    llm = ScriptedOpenAI(
        {
            "warm in December": replies(
                call("list_destinations", month="December", style="family"),
                reply("Goa and Dubai are both lovely in December. Which sounds better?"),
            ),
            "Goa sounds good": replies(
                call(
                    "set_trip",
                    from_city="Bombay",
                    destination="Goa",
                    month="December",
                    nights=4,
                    adults=2,
                    kids_ages=[6, 9],
                    style="family",
                ),
                reply("{go: plan} I've put it all in. Shall I build it?"),
            ),
        }
    )
    async with _rig(llm) as rig:
        greeting = await rig.driver.start_session(init={"page": "home", "lang": "en"})
        assert greeting is not None and greeting.text == LANGUAGES["en"].greeting_home
        assert "home page" in llm.captured_instructions[0] if llm.captured_instructions else True

        t1 = await rig.driver.user_says("Somewhere warm in December with our two kids")
        check_turn(rig, t1)
        listed = tool_results_of(llm.captured_inputs[-1], "list_destinations")[0]
        assert f"From {eng.money(eng.from_price('goa'))} per person from Delhi" in listed
        assert "Goa (India)" in listed and "In season then." in listed
        assert "The call started on the home page" in llm.captured_instructions[0]

        t2 = await rig.driver.user_says("Goa sounds good, from Mumbai, four nights")
        check_turn(rig, t2)
        args = _move(rig, "trip.brief")["args"]
        assert args["from_city"] == "BOM" and args["destination"] == "goa"
        assert args["kids"] == ["6", "9"] and args["start_date"] == "2026-12-11"
        cues = [
            dict(c.get("payload") or {})
            for c in rig.driver.ui_commands
            if c.get("command") == "stage_cue"
        ]
        assert [(c["move"], c["args"]) for c in cues] == [("trip.go", ["plan"])]
        assert "I've put it all in" in t2.text and "{" not in t2.text


async def test_what_is_not_sold_is_said_and_not_invented() -> None:
    llm = ScriptedOpenAI(
        {
            "Patna": replies(
                call("set_trip", from_city="Patna", destination="Iceland", nights=5),
                reply("We don't fly from Patna or sell Iceland. Where else could you leave from?"),
            )
        }
    )
    async with _rig(llm) as rig:
        await rig.driver.start_session(init={"page": "plan"})
        t1 = await rig.driver.user_says("From Patna to Iceland for five nights")
        check_turn(rig, t1)
        result = tool_results_of(llm.captured_inputs[-1], "set_trip")[0]
        assert "Wanderloom does not fly from Patna" in result
        assert "Wanderloom does not sell Iceland" in result
        assert "Still need: where they fly from, where to, when" in result
        # Only what the inventory can serve reaches the screen.
        assert [m["args"] for m in _moves(rig) if m["move"] == "trip.brief"] == [{"nights": 5}]


async def test_hindi_from_the_page_and_english_from_the_toggle() -> None:
    llm = ScriptedOpenAI({"हिंदी": reply("ज़रूर।")})
    async with _rig(llm) as rig:
        greeting = await rig.driver.start_session(init={"page": "home", "lang": "hi"})
        assert greeting is not None and greeting.text == LANGUAGES["hi"].greeting_home
        check_voice_pair(rig, voice=LANGUAGES["hi"].voice, language="hi")
        assert "This call is in Hindi" in llm.captured_instructions[0] if llm.requests else True

        await rig.driver.send_ui_event("language_chosen", {"language": "en"})
        await asyncio.sleep(0.1)
        check_voice_pair(rig, voice=LANGUAGES["en"].voice, language="en")
        brain = _brain(rig)
        assert brain.lang == "en"
        assert "This call is in English" in brain.system_instruction
        # The toggle only asked; the brain's language_changed is what moves it.
        assert rig.command("language_changed") == {"language": "en"}


async def test_a_switch_asked_by_voice_moves_the_page_toggle() -> None:
    """The visitor asks for Hindi out loud: both legs move, and the page's
    toggle follows (language_changed), so the next call starts in Hindi too."""
    llm = ScriptedOpenAI(
        {"Hindi mein": reply_and_call("ज़रूर, अब हिंदी में।", "set_language", language="hi")}
    )
    async with _rig(llm) as rig:
        await rig.driver.start_session(init={"page": "plan", "lang": "en"})
        assert "language_changed" not in rig.actions()
        check_turn(rig, await rig.driver.user_says("Hindi mein baat karein?"))
        await asyncio.sleep(0.1)
        check_voice_pair(rig, voice=LANGUAGES["hi"].voice, language="hi")
        assert rig.command("language_changed") == {"language": "hi"}


async def test_a_trip_built_by_hand_before_the_call_is_where_the_call_starts() -> None:
    trip = {
        "from_city": "BLR",
        "destination": "kerala",
        "start_date": "2026-12-18",
        "nights": 5,
        "adults": 2,
        "kids": [6],
        "split": [2, 2, 1],
        "flight_id": "BLR-kerala-1",
        "hotels": {"munnar": {"hotel_id": "cardamom-hills", "room_id": "family"}},
        "activities": [{"day": 2, "activity_id": "munnar-tea-museum"}],
    }
    llm = ScriptedOpenAI({"total": replies(call("trip_summary"), reply("Here's where it stands."))})
    async with _rig(llm) as rig:
        await rig.driver.start_session(init={"page": "plan", "lang": "en", "trip": trip})
        brain = _brain(rig)
        assert brain.trip.flight_id == "BLR-kerala-1"
        assert brain.trip.hotels == {"munnar": ("cardamom-hills", "family")}
        t1 = await rig.driver.user_says("What's the total so far?")
        check_turn(rig, t1)
        summary = tool_results_of(llm.captured_inputs[-1], "trip_summary")[0]
        assert "Cardamom Hills Inn" in summary and "Tea factory and museum tour" in summary
        assert eng.money(eng.price(brain.trip).total) in summary


def test_the_voice_and_languages_come_from_persona_json() -> None:
    raw = json.loads((eng.DATA.parent / "persona.json").read_text())
    assert {t: s.voice for t, s in LANGUAGES.items()} == {
        t: v["voice"] for t, v in raw["languages"].items()
    }
    assert raw["name"] in LANGUAGES["en"].greeting_plan


async def test_the_umbrella_factory_builds_the_brain() -> None:
    async with demo("holidays", ScriptedOpenAI()) as rig:
        greeting = await rig.driver.start_session()
        check_greeting(rig, greeting)
        check_voice_pair(rig, voice=LANGUAGES["en"].voice, language="en")


# ── Redial: a dropped brain socket does not end the call ─────────────────────


def _configs(driver: VoqalizeDriver) -> list[ConfigureFrame]:
    return [r for r in driver.requests if isinstance(r, ConfigureFrame)]


def _redials(driver: VoqalizeDriver) -> list[bool | None]:
    return [c.config.redial.enabled for c in _configs(driver) if c.config.redial is not None]


def _redial_llm() -> ScriptedOpenAI:
    return ScriptedOpenAI(
        {
            "Delhi to Bali": replies(
                call(
                    "set_trip",
                    from_city="Delhi",
                    destination="Bali",
                    month="February",
                    nights=6,
                    adults=2,
                    style="honeymoon",
                ),
                reply("Lovely. Shall I build the whole package?"),
            ),
            "build the whole thing": replies(
                call("build_package"), reply("{show: total} Here it is, all in.")
            ),
            "the flights": replies(call("show_flights"), reply("दो विकल्प हैं।")),
        }
    )


async def _redial_rig(llm: ScriptedOpenAI, sid: str) -> tuple[Any, list[HolidaysBrain], Any]:
    """A real brain server two drivers can dial on one session id, as Voqalize
    does when it redials; and every brain it built, in order."""
    from voqalize.conformance import (
        BrainServer,
        DirectConnection,
        generate_keypair,
        mint_voqalize_token,
    )

    built: list[HolidaysBrain] = []

    def _build() -> HolidaysBrain:
        brain = HolidaysBrain(client=llm, today=TODAY)  # type: ignore[arg-type]
        built.append(brain)
        return brain

    keypair = generate_keypair()
    server = BrainServer(_build, host="127.0.0.1", port=0, public_keys=keypair.public_pem)
    port = await server.start()

    def driver() -> VoqalizeDriver:
        token = mint_voqalize_token(
            private_key_pem=keypair.private_pem,
            session_id=sid,
            agent_id="holidays",
            tenant_id="demo",
        )
        return VoqalizeDriver(
            DirectConnection(f"ws://127.0.0.1:{port}", sid, token=token),
            session_id=sid,
            default_timeout=10.0,
        )

    return server, built, driver


async def _drop(driver: VoqalizeDriver, brain: HolidaysBrain) -> None:
    """The socket drops: no End, no close code a hang-up would send. Returns once
    the brain's ``on_session_end`` has marked the call dropped."""
    from voqalize_demos._loaded.holidays.brain import REJOIN

    await driver.aclose()
    for _ in range(50):
        entry = REJOIN._held.get(driver.session_id)  # pyright: ignore[reportPrivateUsage]
        if entry is not None and entry[0] is brain and entry[2] is not None:
            return
        await asyncio.sleep(0.02)
    raise AssertionError("the dropped socket never reached on_session_end")


async def test_a_dropped_socket_rejoins_the_call_where_it_was() -> None:
    """Mid-flow — a brief, a built package, a switch to Hindi on the toggle and a
    room the visitor picked by hand — the brain's socket drops without a hang-up.
    The planner turned redial on; Voqalize dials again for the same session with
    the same (now stale) init; the new socket's brain adopts the call — trip,
    page, language and voice, the model's history — greets no one, and the next
    turn carries on from it."""
    llm = _redial_llm()
    sid = "holidays-redial-e2e"
    server, built, driver = await _redial_rig(llm, sid)
    first, second = driver(), driver()
    init = {"page": "plan", "lang": "en"}
    try:
        await first.open()
        greeting = await first.start_session(init=init)
        assert greeting is not None and greeting.text == LANGUAGES["en"].greeting_plan
        assert _redials(first) == [True], "redial is turned on with the voice, before the greeting"
        answered: set[str] = set()
        await first.user_says(
            "Delhi to Bali in February for six nights, my wife and I, it's our honeymoon"
        )
        await _lands(first, answered)
        await first.user_says("Just build the whole thing for us")
        await _lands(first, answered)
        await first.send_ui_event("language_chosen", {"language": "hi"})
        await first.send_ui_event(
            "stage_event",
            {
                "name": "trip.hotel_picked",
                "by": "visitor",
                "data": {
                    "city": "seminyak",
                    "hotel_id": "petitenget-villas",
                    "room_id": "one-bed",
                    "label": "Petitenget Pool Villas, One-bedroom Pool Villa, in Seminyak",
                },
            },
        )
        await asyncio.sleep(0.1)
        before = built[-1]
        assert before.lang == "hi"
        assert before.trip.hotels["seminyak"] == ("petitenget-villas", "one-bed")
        trip_before = before.trip.to_json()
        history_before = len(before._history)  # pyright: ignore[reportPrivateUsage]

        await _drop(first, before)

        # Voqalize redials: the same session id, the same init it started with.
        await second.open()
        regreeting = await second.start_session(init=init, greeting_timeout=0.5)
        after = built[-1]
        assert after is not before
        assert regreeting is None, "a rejoined call is not greeted again"
        assert after.trip.to_json() == trip_before, "the trip on screen is kept"
        assert after.lang == "hi" and after.page == "plan"
        assert "This call is in Hindi" in after.system_instruction
        assert after._history and len(after._history) >= history_before  # pyright: ignore[reportPrivateUsage]
        last = _configs(second)[-1].config
        assert last.tts is not None and last.tts.voice == LANGUAGES["hi"].voice
        assert last.tts.language == "hi" and last.stt is not None and last.stt.language == "hi"
        assert _redials(second) == [True]

        turn = await second.user_says("And what are the flights?")
        assert turn.units, "the call carried on after the drop"
        flights = tool_results_of(llm.captured_inputs[-1], "show_flights")[0]
        assert flights.startswith("2 options from Delhi"), "the brief came across"
        heard = json.dumps(llm.captured_inputs[-1], ensure_ascii=False)
        assert "Delhi to Bali in February" in heard, "the model's history came across"
        assert heard.count(LANGUAGES["en"].greeting_plan) <= 1, "no second greeting"
        # The Stage director now dispatches on the new socket.
        moved = [
            c["payload"]["move"] for c in second.ui_commands if c.get("command") == "stage_move"
        ]
        assert moved == ["trip.flights"], moved
    finally:
        await second.aclose()
        await server.aclose()


async def test_a_redial_after_two_minutes_starts_fresh_from_init() -> None:
    """Expiry: a call held longer than two minutes after its drop is let go, so a
    redial then starts a new conversation on the page, greeted, from init."""
    from voqalize_demos._loaded.holidays.brain import REJOIN
    from voqalize_demos._loaded.holidays.rejoin import KEEP_AFTER_DROP_S

    llm = _redial_llm()
    sid = "holidays-redial-expired-e2e"
    server, built, driver = await _redial_rig(llm, sid)
    now = [1000.0]
    REJOIN._clock = lambda: now[0]  # pyright: ignore[reportPrivateUsage]
    first, second = driver(), driver()
    try:
        await first.open()
        await first.start_session(init={"page": "plan", "lang": "en"})
        await first.user_says(
            "Delhi to Bali in February for six nights, my wife and I, it's our honeymoon"
        )
        before = built[-1]
        assert before.trip.destination == "bali"
        await _drop(first, before)
        now[0] += KEEP_AFTER_DROP_S + 1
        assert len(REJOIN) == 0, "let go two minutes after the drop"

        await second.open()
        greeting = await second.start_session(init={"page": "plan", "lang": "en"})
        after = built[-1]
        assert greeting is not None and greeting.text == LANGUAGES["en"].greeting_plan
        assert not after.trip.destination and not after._history[1:]  # pyright: ignore[reportPrivateUsage]
    finally:
        REJOIN._clock = __import__("time").monotonic  # pyright: ignore[reportPrivateUsage]
        await second.aclose()
        await server.aclose()


def test_the_rejoin_store_keeps_live_calls_and_lets_dropped_ones_go() -> None:
    from voqalize_demos._loaded.holidays.rejoin import KEEP_AFTER_DROP_S, Rejoin

    now = [0.0]
    store: Rejoin[object] = Rejoin(clock=lambda: now[0])
    a, b = object(), object()
    store.hold("s1", a)
    store.dropped("s1", b)  # not the brain held: nothing changes
    now[0] = KEEP_AFTER_DROP_S + 1
    assert store.take("s1") is a, "a live call is kept however long it runs"
    store.hold("s1", a)
    store.dropped("s1", a)
    now[0] += KEEP_AFTER_DROP_S - 1
    assert len(store) == 1
    now[0] += 2
    assert store.take("s1") is None and len(store) == 0
    assert store.take("never-held") is None


async def test_no_redial_is_asked_of_a_voqalize_that_does_not_offer_it() -> None:
    """``configure`` raises for redial without the capability: the planner asks
    only where it is offered, and the call starts the same either way."""
    from voqalize.sdk.wire import Capability

    async with _rig(ScriptedOpenAI()) as rig:
        rig.driver.capabilities.discard(Capability.REDIAL)
        greeting = await rig.driver.start_session(init={"page": "plan", "lang": "en"})
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text == LANGUAGES["en"].greeting_plan
        assert _redials(rig.driver) == []
        check_voice_pair(rig, voice=LANGUAGES["en"].voice, language="en")
