"""The Travel Desk demo, end to end over the wire — no network, no LLM key.

The real ``TravelBrain`` — the shipping ``demos/travel/backend/brain_gemini.py``,
its real prompt, its real ten tools — hosted on a real ``brain_server`` socket and
driven by the conformance ``VoqalizeDriver``, with only the *model* scripted. See
``tests/_harness.py`` for what every demo's e2e proves.

Travel is the demo whose screen state can change **by the travel agent's own
hand**, not just by Priya's tools — the ``/travel`` UI echoes a ``state_sync``
snapshot of the active itinerary on connect and after every change, and that echo
is the only place "what's on screen" can include a hand edit. It must fold into
context **without** taking the floor, exactly like legal's ``clause_focus``, and
**without** the itinerary itself following it in: the screen is read through
``read_screen``, never remembered.

Run: ``cd demos && uv run pytest tests/test_travel_e2e.py``
"""

from __future__ import annotations

from typing import Any

from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, call, reply, reply_and_call

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


#: A snapshot of the shape ``store.tsx``'s ``snapshot()`` sends, trimmed to the
#: facts a version bump is keyed on.
_PODDAR: dict[str, Any] = {
    "name": "Poddar Vietnam",
    "screen": "flights",
    "screen_context": "blr-out",
    "destination": "Ho Chi Minh City",
    "dates": "12 Aug 2026 to 18 Aug 2026",
    "legs": [{"id": "blr-out", "label": "Bangalore → Ho Chi Minh", "selected": None}],
    "hotels": [],
    "days": [],
}


def _context_text(llm: ScriptedGemini) -> str:
    """Everything the brain appended to the context as the agent's own words.

    A hand edit on the /travel screen reaches the model exactly one way: ``on_rtvi``
    appends a line saying which decisions moved. It takes no floor, so it is
    invisible until the *next* request carries the whole context along with it."""
    return " ".join(
        part.text or ""
        for contents in llm.captured_contents
        for content in contents
        if content.role == "user"
        for part in (content.parts or [])
    )


def _tool_results(llm: ScriptedGemini) -> str:
    """Every tool result the brain put in front of the model, as one blob.

    Under automatic function calling a whole turn is one request, so the calls it
    made are first carried by the request that *follows* it. google-genai wraps a
    tool's return as ``{"result": ...}``."""
    out: list[str] = []
    for contents in llm.captured_contents:
        for content in contents:
            for part in content.parts or []:
                if part.function_response is not None:
                    out.append(str((part.function_response.response or {}).get("result", "")))
    return " ".join(out)


async def test_what_the_agent_changed_is_named_and_the_itinerary_is_never_dumped() -> None:
    """``state_sync`` is the one client message that must not speak — and, since the
    itinerary moved out of the context, the one that must not describe either.

    This used to append the whole itinerary on every change, prefixed
    *authoritative* and undated, so a long call ended with a hundred near-identical
    screens in front of the model. Now the snapshot stops at the brain: the context
    gets one line naming which decisions the agent moved and pointing at
    ``read_screen``. Both halves are asserted — a note carrying the leg id would be
    the old dump again, one fact at a time."""
    llm = _llm()
    async with demo("travel", llm) as rig:
        await rig.driver.start_session()
        before = len(rig.driver.ui_commands)

        # The first sync is the page as it loaded; the second is the agent.
        await rig.driver.send_client_message(
            "state_sync", {"itinerary": {"name": "Poddar Vietnam"}}
        )
        await rig.driver.send_client_message("state_sync", {"itinerary": _PODDAR})
        # Frames on one connection are ordered, so both syncs are ingested by the
        # time the next turn is served.
        turn = await rig.driver.user_says("What's on screen right now?")
        check_turn(rig, turn, units=1)
        assert len(rig.driver.ui_commands) == before, "state_sync drove the screen"

    context = _context_text(llm)
    assert "just changed the screen" in context
    assert "read_screen" in context
    assert "blr-out" not in context, "the change note is carrying the screen"
    assert "ON SCREEN RIGHT NOW" not in context, "the itinerary dump is back"


async def test_a_tool_aimed_at_a_leg_the_agent_moved_is_refused_until_it_is_read() -> None:
    """The version gate, which is what makes read-don't-remember enforceable.

    Prompt discipline is a request; a model that skips the read is selecting an
    option id from a search that is no longer the one on screen. So the tool refuses
    instead of acting, and the refusal is retriable: read, then act.

    The other half is that Priya's own dispatches must *not* trip it. The browser
    echoes every one of them back as a ``state_sync`` indistinguishable from the
    agent moving the screen by hand, and a change the model asked for is one it has
    already been told about — so the echo below is sent exactly as the browser sends
    it, and costs the model no hop."""
    llm = ScriptedGemini(
        {
            "Bring the outbound options back up.": [
                reply_and_call("Sure.", "show_flights", action={"leg_id": "blr-out"}),
                reply("They're up."),
            ],
            "Take the IndiGo one.": [
                # Stale — the agent has moved the screen since. Then the retry.
                call("select_flight", action={"leg_id": "blr-out", "option_id": "f1"}),
                call("read_screen"),
                reply_and_call(
                    "Locking that in.",
                    "select_flight",
                    action={"leg_id": "blr-out", "option_id": "f1"},
                ),
                reply("IndiGo is in."),
            ],
            "Thanks.": reply("Any time."),
        }
    )
    async with demo("travel", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.send_client_message(
            "state_sync", {"itinerary": {"name": "Poddar Vietnam"}}
        )

        # The screen moves, but Priya moved it — so this costs no read.
        await rig.driver.user_says("Bring the outbound options back up.")
        assert rig.actions() == ["show_flights"], rig.actions()
        assert not _select_refused(llm), "the brain's own dispatch bumped the version"
        await rig.driver.send_client_message("state_sync", {"itinerary": _PODDAR})

        # Now the agent edits the itinerary by hand.
        moved = {**_PODDAR, "days": [{"day": 1, "date": "12 Aug 2026", "title": "Arrival"}]}
        await rig.driver.send_client_message("state_sync", {"itinerary": moved})
        await rig.driver.user_says("Take the IndiGo one.")
        assert rig.actions() == ["show_flights", "select_flight"], rig.actions()

        # One more turn, so the turn above's hops are in the context being asserted.
        await rig.driver.user_says("Thanks.")

    assert _select_refused(llm)


def _select_refused(llm: ScriptedGemini) -> bool:
    return "the screen moved since you last read it" in _tool_results(llm)
