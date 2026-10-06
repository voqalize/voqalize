"""The Petwell Appointment Desk demo, end to end over the wire — no network, no LLM key.

The real ``PetwellBrain`` — the shipping ``demos/petwell/backend/brain.py``, its
real prompt, its real tools, its real branch catalog — hosted on a real
``brain_server`` socket and driven by the conformance ``VoqalizeDriver``, with only
the *model* scripted. See ``tests/_harness.py`` for what every demo's e2e proves.

**Only ``show_slots`` carries ``@needs_result_now``** — which times are still
free is something only the slot book knows, so that turn is two requests: the
call, then the times offered. Every other tool shows what the model named from
its prompt and says its line with the call, one request per turn.

The browser→brain leg is the caller's own taps and the final Send Request: each
folds into the context without taking the floor, and the next idle tick answers.

Run: ``cd demos && uv run pytest tests/test_petwell_e2e.py``
"""

from __future__ import annotations

import asyncio
import datetime as dt

from google.genai import types
from voqalize_demos.discovery import discover
from voqalize_demos.testing import Reply, ScriptedGemini, call, reply, reply_and_call

from ._harness import check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.petwell.brain import (  # noqa: E402
    _GREETING,
    _IDLE_MS,
    ChooseBranch,
    PetwellBrain,
)
from voqalize_demos._loaded.petwell.catalog import slots_for  # noqa: E402

VOICE = "omnivoice/gaurav"
LANGUAGE = "en"

# Always a bookable day that is not today, so "past times today" never trims it.
TOMORROW = (dt.datetime.now(dt.UTC) + dt.timedelta(hours=5, minutes=30)).date() + dt.timedelta(
    days=1
)
DAY = TOMORROW.isoformat()
FREE = slots_for("mum-powai", DAY, "clinic")


def _results(contents: list[types.Content]) -> dict[str, str]:
    """Every tool result one request carried, by tool name."""
    return {
        p.function_response.name or "": str((p.function_response.response or {})["result"])
        for c in contents
        for p in (c.parts or [])
        if p.function_response is not None
    }


def _llm() -> ScriptedGemini:
    return ScriptedGemini(
        {
            # One sentence answers four steps: four calls under one line.
            "I want to get my dog vaccinated at your Powai branch.": Reply(
                text="Happy to help — a vaccination at Petwell Powai. Which day suits you?",
                calls=(
                    ("start_booking", {"action": {"visit_type": "clinic"}}),
                    ("choose_city", {"action": {"city": "Mumbai"}}),
                    ("choose_branch", {"action": {"branch_id": "mum-powai"}}),
                    ("choose_service", {"action": {"service_id": "vaccination"}}),
                ),
            ),
            # The one read: the call, then — with the free times in hand — the offer.
            "Tomorrow please.": [
                reply_and_call("Let me check tomorrow.", "show_slots", query={"date": DAY}),
                reply(f"Tomorrow I have {FREE[0]} or {FREE[1]} free. Which works?"),
            ],
            "The first one.": reply_and_call(
                "Done. May I have your name and your pet's name?",
                "choose_slot",
                action={"date": DAY, "time": FREE[0]},
            ),
            "I'm Riya and he's Bruno, a beagle. 98200 12345.": Reply(
                text="Thanks Riya. Please check the summary and tap Send Request.",
                calls=(
                    (
                        "fill_details",
                        {
                            "action": {
                                "owner_name": "Riya",
                                "pet_name": "Bruno",
                                "pet_type": "dog",
                                "phone": "9820012345",
                            }
                        },
                    ),
                    ("show_review", {}),
                ),
            ),
            # The idle tick after Send Request: the note's own phrase is the key.
            "tapped Send Request": reply(
                "Your reference is PW-123456. Powai will call you shortly."
            ),
            "My dog ate rat poison!": reply_and_call(
                "Please come in now — the helpline is on your screen.",
                "show_emergency",
                query={"city": "Mumbai"},
            ),
            "Book me in Kolkata.": reply_and_call(
                "Our Kolkata hospital opens soon — could another city work?",
                "choose_city",
                action={"city": "Kolkata"},
            ),
        }
    )


async def test_greeting_and_voice_reach_the_wire() -> None:
    """The desk greets, and its declared English voice lands on **both** legs
    before the greeting audio does."""
    async with demo("petwell", _llm()) as rig:
        greeting = await rig.driver.start_session()
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text == _GREETING
        check_voice_pair(rig, voice=VOICE, language=LANGUAGE)


async def test_a_clinic_booking_drives_the_screen_to_send_request() -> None:
    """The whole clinic flow, by voice: the screen moves under every line, the
    slot read takes the one extra request, and Send Request is answered on the
    next idle tick with the reference the browser minted."""
    llm = _llm()
    async with demo("petwell", llm) as rig:
        await rig.driver.start_session()

        before = len(llm.captured_contents)
        t1 = await rig.driver.user_says("I want to get my dog vaccinated at your Powai branch.")
        check_turn(rig, t1, units=1)
        assert len(llm.captured_contents) - before == 1, "an unmarked tool took a second request"

        before = len(llm.captured_contents)
        t2 = await rig.driver.user_says("Tomorrow please.")
        check_turn(rig, t2)
        assert len(llm.captured_contents) - before == 2, "the slot read did not hold the turn"
        assert FREE[0] in _results(llm.captured_contents[-1])["show_slots"]

        await rig.driver.user_says("The first one.")
        await rig.driver.user_says("I'm Riya and he's Bruno, a beagle. 98200 12345.")

        assert rig.actions() == [
            "start_booking",
            "choose_city",
            "choose_branch",
            "choose_service",
            "show_slots",
            "choose_slot",
            "fill_details",
            "show_review",
        ], rig.actions()
        slots = rig.command("show_slots")
        assert slots["branch_id"] == "mum-powai" and slots["date"] == DAY
        assert slots["times"] == FREE
        assert rig.command("choose_slot") == {"date": DAY, "time": FREE[0]}
        details = rig.command("fill_details")
        assert details["pet_name"] == "Bruno" and details["phone"] == "9820012345"

        sent = len(rig.driver.ui_commands)
        await rig.driver.send_ui_event(
            "appointment_requested",
            {"ref": "PW-123456", "owner_name": "Riya", "pet_name": "Bruno", "phone": "9820012345"},
        )
        await asyncio.sleep(0.1)
        assert len(rig.driver.ui_commands) == sent, "Send Request drove the screen"
        turn = await rig.driver.user_idle(level=1, idle_ms=_IDLE_MS)
        check_turn(rig, turn, units=1)
        note = "".join(p.text or "" for p in (llm.captured_contents[-1][-1].parts or []))
        assert "PW-123456" in note and "Petwell Powai" in note, note


async def test_a_time_that_is_not_free_is_refused() -> None:
    """``choose_slot`` checks the slot book: a taken time is an error the model
    reads, and the screen does not move."""
    taken = next(
        f"{h:02d}:{m:02d}" for h in range(9, 20) for m in (0, 30) if f"{h:02d}:{m:02d}" not in FREE
    )
    llm = ScriptedGemini(
        {
            "Powai, vaccination.": Reply(
                text="Sure.",
                calls=(
                    ("start_booking", {"action": {"visit_type": "clinic"}}),
                    ("choose_branch", {"action": {"branch_id": "mum-powai"}}),
                ),
            ),
            "Book the taken one.": reply_and_call(
                "Booking that.", "choose_slot", action={"date": DAY, "time": taken}
            ),
            "Okay.": reply("Sorry, that one's gone."),
        }
    )
    async with demo("petwell", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Powai, vaccination.")
        await rig.driver.user_says("Book the taken one.")
        assert "choose_slot" not in rig.actions()
        await rig.driver.user_says("Okay.")
        assert "not free" in _results(llm.captured_contents[-1])["choose_slot"]


async def test_an_emergency_opens_the_helpline_instead_of_booking() -> None:
    """A pet in danger is not booked: the emergency panel opens with the
    region's helpline and that city's 24x7 branches."""
    async with demo("petwell", _llm()) as rig:
        await rig.driver.start_session()
        turn = await rig.driver.user_says("My dog ate rat poison!")
        check_turn(rig, turn, units=1)
        sos = rig.command("show_emergency")
        assert sos["city"] == "Mumbai"
        assert sos["helpline"] == "+91 90000 02222"
        assert sos["branch_ids"] == ["mum-mahalaxmi"]


async def test_an_opening_soon_city_shows_but_cannot_be_booked() -> None:
    """Kolkata is on screen, flagged opening soon; its branch refuses a booking."""
    async with demo("petwell", _llm()) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Book me in Kolkata.")
        assert rig.command("choose_city") == {"city": "Kolkata"}
        brain = rig.brain
        assert isinstance(brain, PetwellBrain)
        refused = await brain.choose_branch(ChooseBranch(branch_id="kol-ballygunge"))
        assert refused.startswith("error:"), refused


async def test_a_tap_is_answered_on_the_next_idle_and_silence_otherwise() -> None:
    """A branch tapped on screen folds in silently and the next idle tick carries
    on from it; with nothing tapped, idle ticks stay silent."""
    llm = ScriptedGemini(
        {
            "Clinic visit in Mumbai.": Reply(
                text="Which branch is closest?",
                calls=(
                    ("start_booking", {"action": {"visit_type": "clinic"}}),
                    ("choose_city", {"action": {"city": "Mumbai"}}),
                ),
            ),
            "tapped the Petwell Churchgate branch": reply(
                "Churchgate it is. What's the visit for?"
            ),
        }
    )
    async with demo("petwell", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Clinic visit in Mumbai.")

        quiet = await rig.driver.user_idle(level=1, idle_ms=_IDLE_MS, timeout=1.0)
        assert quiet.units == [], [u.text for u in quiet.units]

        await rig.driver.send_ui_event("branch_picked", {"branch_id": "mum-churchgate"})
        await asyncio.sleep(0.1)
        turn = await rig.driver.user_idle(level=1, idle_ms=_IDLE_MS)
        check_turn(rig, turn, units=1)
        brain = rig.brain
        assert isinstance(brain, PetwellBrain) and brain.branch_id == "mum-churchgate"


async def test_a_branch_chosen_in_silence_is_still_said() -> None:
    """The model picks the branch and says nothing: the brain says the branch's
    own line, with no second request."""
    llm = ScriptedGemini(
        {
            "Powai.": call("choose_branch", action={"branch_id": "mum-powai"}),
        }
    )
    async with demo("petwell", llm) as rig:
        await rig.driver.start_session()
        before = len(llm.captured_contents)
        turn = await rig.driver.user_says("Powai.")
        check_turn(rig, turn, units=1)
        (line,) = (u.text for u in turn.units)
        assert line == "Petwell Powai it is. What's the visit for?", line
        assert len(llm.captured_contents) - before == 1, "a silent turn asked the model again"
