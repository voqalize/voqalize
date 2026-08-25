"""The Travel Desk demo, end to end over the wire — no network, no LLM key.

The real ``TravelBrain`` — the shipping ``demos/travel/backend/brain_gemini.py``,
its real prompt, its real ten tools — hosted on a real ``brain_server`` socket and
driven by the conformance ``VoqalizeDriver``, with only the *model* scripted. See
``tests/_harness.py`` for what every demo's e2e proves.

Travel is the demo whose screen state can change **by the travel agent's own
hand**, not just by Priya's tools — the ``/travel`` UI echoes a ``state_sync``
snapshot of the active itinerary on connect and after every change, and that echo
is the only place "what's on screen" can include a hand edit. It must fold into
context **without** taking the floor, exactly like legal's ``clause_focus``.

Run: ``cd demos && uv run pytest tests/test_travel_e2e.py``
"""

from __future__ import annotations

from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, reply, reply_and_call

from ._harness import check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.travel.brain_gemini import _GREETING  # noqa: E402

VOICE = "omnivoice/gauri"
LANGUAGE = "hi"


def _llm() -> ScriptedGemini:
    return ScriptedGemini(
        {
            "Let's start a new trip for the Poddar family to Vietnam.": [
                reply_and_call(
                    "Sure, opening that up.",
                    "create_itinerary",
                    # One tool, one model, one parameter — the argument is the
                    # ``CreateItinerary`` the browser renders, nested under the
                    # name the method gives it.
                    action={
                        "itinerary": {
                            "name": "Poddar Vietnam",
                            "destination": "Ho Chi Minh City",
                            "start_date": "12 Aug 2026",
                            "end_date": "18 Aug 2026",
                        }
                    },
                ),
                reply("It's open — who's travelling and what are the flight legs?"),
            ],
            "Search flights for the outbound leg.": [
                reply_and_call(
                    "Pulling up some options.",
                    "search_flights",
                    action={
                        "leg_id": "blr-out",
                        "options": [
                            {
                                "airline": "IndiGo",
                                "depart": "BLR 02:15",
                                "arrive": "SGN 09:40",
                                "price": 21000,
                            },
                            {
                                "airline": "Vietnam Airlines",
                                "depart": "BLR 05:00",
                                "arrive": "SGN 13:10",
                                "price": 24500,
                            },
                        ],
                    },
                ),
                reply("Two options are up — IndiGo non-stop or Vietnam Airlines."),
            ],
            "What's on screen right now?": reply(
                "You've got the Poddar Vietnam trip open, twelve to eighteen August."
            ),
        }
    )


async def test_greeting_and_voice_reach_the_wire() -> None:
    """The travel desk opens with a fixed Hindi line — no model call on the start
    path — and its declared female Hindi voice lands on **both** legs before that
    audio."""
    async with demo("travel", _llm()) as rig:
        greeting = await rig.driver.start_session()
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text == _GREETING
        check_voice_pair(rig, voice=VOICE, language=LANGUAGE)


async def test_creating_a_trip_and_searching_flights_drive_the_screen() -> None:
    """Two turns, each a tool round-trip, with the exact ``ui-command`` payloads
    the /travel UI renders — and a leg's flight options each carry a stable id
    even though the script never gave one."""
    async with demo("travel", _llm()) as rig:
        await rig.driver.start_session()

        t1 = await rig.driver.user_says("Let's start a new trip for the Poddar family to Vietnam.")
        check_turn(rig, t1, units=2)

        t2 = await rig.driver.user_says("Search flights for the outbound leg.")
        check_turn(rig, t2, units=2)

        assert rig.actions() == ["create_itinerary", "search_flights"], rig.actions()

        created = rig.command("create_itinerary")
        assert created["itinerary"]["name"] == "Poddar Vietnam"
        assert created["itinerary"]["destination"] == "Ho Chi Minh City"

        searched = rig.command("search_flights")
        assert searched["leg_id"] == "blr-out"
        assert [o["id"] for o in searched["options"]] == ["f1", "f2"]
        assert searched["options"][0]["airline"] == "IndiGo"


async def test_the_browsers_screen_lands_silently_and_grounds_the_next_answer() -> None:
    """``state_sync`` is the one client message that must **not** speak.

    The travel agent's own hand edits only reach Priya through this echo, so it
    has to fold into context without taking the floor — a brain that answered
    every re-send would talk over the agent typing, and one that ignored it would
    answer "what's on screen?" from a stale or absent turn. Both halves are
    asserted here because either one alone passes for the wrong reason."""
    llm = _llm()
    async with demo("travel", llm) as rig:
        await rig.driver.start_session()
        before = len(rig.driver.ui_commands)

        await rig.driver.send_client_message(
            "state_sync",
            {
                "itinerary": {
                    "name": "Poddar Vietnam",
                    "start_date": "12 Aug 2026",
                    "end_date": "18 Aug 2026",
                }
            },
        )
        # The floor is untaken: no speech, no screen command. Frames on one
        # connection are ordered, so the sync is already ingested by the time the
        # next turn is served — which is what the assertion below proves.
        turn = await rig.driver.user_says("What's on screen right now?")
        check_turn(rig, turn, units=1)
        assert len(rig.driver.ui_commands) == before, "state_sync drove the screen"

    grounded = "".join(
        p.text or "" for c in llm.captured_contents[-1] for p in (c.parts or []) if c.role == "user"
    )
    assert "ON SCREEN RIGHT NOW" in grounded
    assert "Poddar Vietnam" in grounded


async def test_a_repeated_screen_snapshot_does_not_flood_the_context() -> None:
    """The browser re-sends the same snapshot on every scroll and tap; only a
    changed one is worth a context append, or a long call fills the prompt with
    near-identical screens."""
    llm = _llm()
    snapshot = {"itinerary": {"name": "Poddar Vietnam", "start_date": "12 Aug 2026"}}
    async with demo("travel", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.send_client_message("state_sync", snapshot)
        await rig.driver.send_client_message("state_sync", snapshot)
        await rig.driver.user_says("What's on screen right now?")

    grounded = sum(
        1
        for c in llm.captured_contents[-1]
        for p in (c.parts or [])
        if c.role == "user" and p.text and "ON SCREEN" in p.text
    )
    assert grounded == 1, "the duplicate snapshot was appended again"
