"""The Travel Desk demo, end to end over the wire — no network, no LLM key.

The real ``TravelBrain`` — the shipping ``demos/travel/backend/brain_gemini.py``,
its real prompt, its real eleven tools — hosted on a real ``brain_server`` socket
and driven by the conformance ``VoqalizeDriver``, with only the *model* scripted.
See ``tests/_harness.py`` for what every demo's e2e proves.

Travel is the demo whose screen can move **by the travel agent's own hand**, not
just by Priya's tools. Each of those gestures reaches the brain as one typed
``ui-event`` — ``trip_opened``, ``flights_viewed``, ``flight_selected`` — and the
two properties asserted here are the ones that make that worth having:

* the context gets **one line naming the act**, never the itinerary behind it, and
* the version gate costs a hop **only when the agent moved the screen** — Priya's
  own dispatches are not events, so they can never bill her for a re-read.

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


#: The overview a ``trip_opened`` carries — the handover, and the only event that
#: brings a whole itinerary. Everything the brain learns after this is a patch.
_PODDAR: dict[str, Any] = {
    "name": "Poddar Vietnam",
    "coordinator": "Anjali Poddar",
    "destination": "Ho Chi Minh City",
    "dates": "12 Aug 2026 to 18 Aug 2026",
    "pax": "6 adults, 2 children",
    "families": ["Poddar (4)", "Bhandari (4)"],
    "legs": [{"id": "blr-out", "label": "Bangalore \u2192 Ho Chi Minh", "date": "12 Aug 2026"}],
    "hotels": [{"city": "Ho Chi Minh City"}],
}


def _context_text(llm: ScriptedGemini) -> str:
    """Everything the brain appended to the context as the agent's own words.

    A gesture on the /travel screen reaches the model exactly one way: ``on_rtvi``
    appends a line saying what the agent just did. It takes no floor, so it is
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

    Under automatic function calling a whole turn is one request, so the results of
    the calls it made are first carried by the request that *follows* it —
    which is why the assertions below are one turn behind the act they are about.
    google-genai wraps a tool's return as ``{"result": ...}``."""
    out: list[str] = []
    for contents in llm.captured_contents:
        for content in contents:
            for part in content.parts or []:
                if part.function_response is not None:
                    out.append(str((part.function_response.response or {}).get("result", "")))
    return " ".join(out)


def _refused(llm: ScriptedGemini) -> bool:
    return "the screen moved since you last read it" in _tool_results(llm)


async def test_a_gesture_is_named_in_the_context_and_the_itinerary_never_follows_it() -> None:
    """The two halves of what a typed event bought.

    **Named**: the note says the act — "opened the flight options for the outbound
    leg" — where the diff it replaced could only ever say that *something* moved.
    **Never dumped**: the itinerary that came with ``trip_opened`` stops at the
    brain's mirror. A note carrying the dates or the coordinator would be the old
    snapshot push arriving one fact at a time, going stale in the context exactly
    the same way."""
    llm = _llm()
    async with demo("travel", llm) as rig:
        await rig.driver.start_session()
        before = len(rig.driver.ui_commands)

        await rig.driver.send_ui_event("trip_opened", _PODDAR)
        await rig.driver.send_ui_event(
            "flights_viewed", {"leg_id": "blr-out", "leg_label": "the outbound leg"}
        )
        # Frames on one connection are ordered, so both are folded in by the time
        # the next turn is served.
        turn = await rig.driver.user_says("What's on screen right now?")
        check_turn(rig, turn, units=1)
        assert len(rig.driver.ui_commands) == before, "an app event drove the screen"

    context = _context_text(llm)
    assert "The travel agent opened the Poddar Vietnam itinerary." in context
    assert "opened the flight options for the outbound leg" in context
    assert "read_screen" in context
    assert "12 Aug 2026" not in context, "the note is carrying the itinerary"
    assert "Anjali" not in context, "the note is carrying the itinerary"
    assert "ON SCREEN RIGHT NOW" not in context, "the itinerary dump is back"


async def test_only_a_gesture_costs_a_re_read_and_priyas_own_dispatch_never_does() -> None:
    """The version gate, which is what makes read-don't-remember enforceable.

    Prompt discipline is a request; a model that skips the read is selecting an
    option id from a search that is no longer the one on screen. So the tool refuses
    instead of acting, and the refusal is retriable: read, then act.

    The half that used to need a flag is now free. The browser echoed every one of
    Priya's own commands back as a snapshot indistinguishable from the agent moving
    the screen by hand, so the brain had to suppress its own echo to avoid billing
    itself a hop. Emits now live at the agent's call site, so a dispatch is simply
    not an event — ``show_flights`` below costs the ``select_flight`` after it
    nothing, and the ``overview_viewed`` after *that* costs exactly one read."""
    llm = ScriptedGemini(
        {
            "What's on screen?": [call("read_screen"), reply("The Poddar Vietnam trip.")],
            "Bring the outbound options back up.": [
                reply_and_call("Sure.", "show_flights", action={"leg_id": "blr-out"}),
                reply("They're up."),
            ],
            "Take the IndiGo one.": [
                reply_and_call(
                    "Locking that in.",
                    "select_flight",
                    action={"leg_id": "blr-out", "option_id": "f1"},
                ),
                reply("IndiGo is in."),
            ],
            "And the Rex for the hotel.": [
                # Stale — the agent has moved the screen since. Then the retry.
                call("select_hotel", action={"city": "Ho Chi Minh City", "option_id": "h1"}),
                call("read_screen"),
                reply_and_call(
                    "Done.",
                    "select_hotel",
                    action={"city": "Ho Chi Minh City", "option_id": "h1"},
                ),
                reply("The Rex it is."),
            ],
            "Thanks.": reply("Any time."),
        }
    )
    async with demo("travel", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.send_ui_event("trip_opened", _PODDAR)

        # Opening a trip is the agent's gesture, so it bills the read it should:
        # the model has never seen this itinerary.
        await rig.driver.user_says("What's on screen?")

        # Two turns Priya drives herself. Neither comes back as an event, so
        # neither can make the other stale.
        await rig.driver.user_says("Bring the outbound options back up.")
        await rig.driver.user_says("Take the IndiGo one.")
        assert rig.actions() == ["show_flights", "select_flight"], rig.actions()

        # Now the agent moves the screen by hand.
        await rig.driver.send_ui_event("overview_viewed", {})
        await rig.driver.user_says("And the Rex for the hotel.")
        assert rig.actions() == ["show_flights", "select_flight", "select_hotel"], rig.actions()
        # ``show_flights`` and ``select_flight`` have both reported back by now;
        # ``select_hotel``'s refusal has not.
        assert not _refused(llm), "the brain's own dispatch bumped the version"

        # One more turn, so the turn above's hops are in the context being asserted.
        await rig.driver.user_says("Thanks.")

    assert _refused(llm)
