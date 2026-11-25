"""Hotel Belmonte, end to end over the wire — no network, no LLM key.

The real :class:`BelmonteBrain` on a real ``brain_server`` socket, driven by the
conformance ``VoqalizeDriver``; only the model is scripted
(:class:`~voqalize_demos.testing.ScriptedOpenAI`, flat tool arguments). One
concierge across the app, so each flow starts on the screen a guest would
start it from: check-in from Home on the arrival day (reservation, the guest's
own ID scan, preferences, early check-in, the guest's Complete check-in); in-room
dining and drinks (a menu read, required choices asked rather than chosen, the
totals, the guest's Place order); the spa (free times, a time picked, the
guest's Book); check-out on the last morning (the folio, a charge questioned,
late check-out, express check-out the guest presses); visitors, front desk
requests, meeting rooms, activities and the hotel's policies. Plus English
only, persona.json as the one place for the character, and redial.

Run: ``cd demos && uv run pytest tests/test_belmonte_e2e.py``
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
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

from voqalize_demos._loaded.belmonte import hotel as h  # noqa: E402
from voqalize_demos._loaded.belmonte.brain import BelmonteBrain  # noqa: E402
from voqalize_demos._loaded.belmonte.persona import LANGUAGES, NAME  # noqa: E402
from voqalize_demos._loaded.belmonte.spoken import (  # noqa: E402
    parse_date,
    parse_time,
    room_words,
    speak_text,
)

#: The stay the app sends on the last morning: checked in, room 1412.
DEPARTURE = {"scenario": "departure", "checked_in": True, "room": "1412"}
#: The arrival day, checked in already (a guest who did it on the app earlier).
ARRIVED = {"scenario": "arrival", "checked_in": True, "room": "1412"}


@pytest.fixture(autouse=True)
def _no_call_carried_between_tests() -> Iterator[None]:
    """Every test here opens the same session id, and a dropped call is held for
    a redial: clear the store around each test so none rejoins the one before."""
    from voqalize_demos._loaded.belmonte.brain import REJOIN

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


async def _lands(driver: VoqalizeDriver, answered: set[str]) -> None:
    """The app lands every move it was sent (so the queue moves on)."""
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


async def _guest(rig: DemoRig, name: str, data: dict[str, Any]) -> None:
    """The guest does something on screen themselves (a tap the app reports)."""
    await rig.driver.send_ui_event("stage_event", {"name": name, "by": "visitor", "data": data})
    await asyncio.sleep(0.1)


def _brain(rig: DemoRig) -> BelmonteBrain:
    assert isinstance(rig.brain, BelmonteBrain)
    return rig.brain


def _rig(llm: ScriptedOpenAI):
    return demo_from("belmonte", lambda: BelmonteBrain(client=llm))  # type: ignore[arg-type]


def _said_later(brain: BelmonteBrain) -> str:
    """The written line the brain will say in the next quiet moment."""
    assert brain._say_next is not None  # pyright: ignore[reportPrivateUsage]
    return brain._say_next()  # pyright: ignore[reportPrivateUsage]


# ─── Check-in, from Home on the arrival day ───────────────────────────────────


async def test_check_in_from_home_with_the_guest_scanning_their_own_id() -> None:
    llm = ScriptedOpenAI(
        {
            "check me in": replies(
                reply_and_call("Of course, let's get you checked in.", "start_check_in"),
            ),
            "that's mine": reply_and_call(
                "Wonderful. Now tap Scan ID and hold up your license.", "confirm_reservation"
            ),
            "high floor": replies(
                call("set_room_preferences", arrival="now", floor="high", bed="king", quiet=True),
                reply(
                    "You'll have room 1412, a quiet corner room. Early check-in is $40; would you like it?"
                ),
            ),
            "take the early": reply_and_call(
                "Done. Review it and press Complete check-in.", "set_early_check_in", want=True
            ),
            "anything else": reply("Enjoy your stay!"),
        }
    )
    answered: set[str] = set()
    async with _rig(llm) as rig:
        greeting = await rig.driver.start_session(init={"page": "home", "lang": "en"})
        check_greeting(rig, greeting)
        assert greeting is not None
        assert greeting.text == LANGUAGES["en"].greeting.format(name=NAME, guest="Maya")
        check_voice_pair(rig, voice=LANGUAGES["en"].voice, language="en")
        brain = _brain(rig)
        assert not brain.guest.checked_in and brain.guest.scenario == "arrival"

        t1 = await rig.driver.user_says("Hi, can you check me in please?")
        check_turn(rig, t1)
        assert _move(rig, "checkin.open")["args"] == {"step": "reservation"}
        heard = input_texts(llm.captured_inputs[-1])
        assert "Not checked in yet" in heard and "next step reservation" in heard
        await _lands(rig.driver, answered)

        t2 = await rig.driver.user_says("Yes, that's mine, two of us")
        check_turn(rig, t2)
        assert _move(rig, "checkin.confirm")["args"] == {}
        assert brain.guest.checkin.confirmed
        await _lands(rig.driver, answered)

        # Too early: the ID is the guest's to scan, and preferences wait for it.
        assert brain.guest.checkin.reachable(brain.stay.now)[-1] == "id"

        # The guest taps Scan ID themselves; the concierge asks the next thing.
        await _guest(rig, "checkin.id_verified", {})
        assert brain.guest.checkin.id_verified
        assert "What time will you get here" in _said_later(brain)

        t3 = await rig.driver.user_says("I'm here now, a high floor and quiet please, one king")
        check_turn(rig, t3)
        prefs = tool_results_of(llm.captured_inputs[-1], "set_room_preferences")[0]
        assert "room 1412, floor 14" in prefs
        assert "early check-in is $40.00" in prefs and "ready now" in prefs
        assert _move(rig, "checkin.prefs")["args"] == {
            "arrival": "now",
            "floor": "high",
            "bed": "king",
            "quiet": "yes",
        }
        await _lands(rig.driver, answered)

        t4 = await rig.driver.user_says("Yes, take the early check-in")
        check_turn(rig, t4)
        assert _move(rig, "checkin.early")["args"] == {"want": "yes"}
        assert brain.guest.checkin.early is True
        await _lands(rig.driver, answered)
        # Nothing the concierge did pressed Complete check-in: no such move exists.
        assert all(m["move"] != "checkin.done" for m in _moves(rig))
        assert not brain.guest.checked_in

        # The guest presses Complete check-in.
        await _guest(rig, "checkin.done", {"room": "1412", "label": "room 1412"})
        assert brain.guest.checked_in and brain.guest.room == "1412"
        line = _said_later(brain)
        assert line.startswith("You're all checked in, Maya. Room 1412, on floor 14")

        t5 = await rig.driver.user_says("Great, anything else I should know?")
        check_turn(rig, t5)
        heard = input_texts(llm.captured_inputs[-1])
        assert "The guest pressed Complete check-in" in heard
        assert "Checked in, room 1412" in heard


async def test_preferences_wait_for_the_guests_own_id_scan() -> None:
    llm = ScriptedOpenAI(
        {
            "yes": reply_and_call("Thank you.", "confirm_reservation"),
            "high floor": replies(
                call("set_room_preferences", floor="high"),
                reply("First, tap Scan ID on screen."),
            ),
        }
    )
    async with _rig(llm) as rig:
        await rig.driver.start_session(init={"page": "checkin", "lang": "en"})
        await rig.driver.user_says("yes it's mine")
        t = await rig.driver.user_says("A high floor please")
        check_turn(rig, t)
        result = tool_results_of(llm.captured_inputs[-1], "set_room_preferences")[0]
        assert result.startswith("Not done: the guest has not scanned their ID yet")
        assert "checkin.prefs" not in [m["move"] for m in _moves(rig)]


# ─── In-room dining and drinks ────────────────────────────────────────────────


async def test_breakfast_is_ordered_with_every_choice_the_guest_made() -> None:
    llm = ScriptedOpenAI(
        {
            "for breakfast": replies(
                reply_and_call(
                    "Let me pull up breakfast.", "show_menu", outlet="dining", section="breakfast"
                ),
                reply("The Belmonte breakfast is $23 with eggs your way. What would you like?"),
            ),
            "Two belmonte": reply_and_call(
                "Two Belmonte breakfasts, coming up.",
                "add_to_order",
                outlet="dining",
                item="Belmonte breakfast",
                quantity=2,
            ),
            "Scrambled": reply_and_call(
                "Perfect.",
                "add_to_order",
                outlet="dining",
                item="Belmonte breakfast",
                quantity=2,
                choices=["scrambled", "bacon", "sourdough"],
            ),
            "And a burger": reply_and_call(
                "Adding a burger.",
                "add_to_order",
                outlet="dining",
                item="Belmonte burger",
                choices=["medium", "fries"],
            ),
            "15 percent": replies(
                call("review_order", outlet="dining", tip_percent=15),
                reply("{show: total} Here's your order. Press Place order when you're ready."),
            ),
            "thanks": reply("My pleasure."),
        }
    )
    answered: set[str] = set()
    async with _rig(llm) as rig:
        await rig.driver.start_session(init={"page": "home", "lang": "en", "stay": DEPARTURE})
        brain = _brain(rig)
        assert brain.guest.checked_in and brain.stay.now == "08:15"

        t1 = await rig.driver.user_says("What's for breakfast?")
        check_turn(rig, t1)
        menu = tool_results_of(llm.captured_inputs[-1], "show_menu")[0]
        assert "In-room dining, Breakfast (6:30 to 11:00 AM, served now)" in menu
        assert "Belmonte breakfast $23.00" in menu
        assert "Eggs (choose one): Scrambled, Fried, Poached, Egg whites (+$2.00)" in menu
        assert "20% service charge and a $5.00 delivery fee" in menu
        assert _move(rig, "menu.open")["args"] == {"outlet": "dining", "section": "breakfast"}
        await _lands(rig.driver, answered)

        # No choices said: nothing is chosen for them, and they hear what to choose.
        t2 = await rig.driver.user_says("Two belmonte breakfasts please")
        check_turn(rig, t2, units=2)
        assert "For the Belmonte breakfast, needs a choice of eggs" in t2.units[-1].text
        assert "menu.item" not in [m["move"] for m in _moves(rig)]
        assert brain.guest.carts["dining"] == []

        t3 = await rig.driver.user_says("Scrambled, with bacon and sourdough")
        check_turn(rig, t3)
        assert _move(rig, "menu.item")["args"] == {
            "outlet": "dining",
            "item_id": "belmonte-breakfast",
            "qty": 2,
            "choices": ["eggs:scrambled", "breakfast_side:bacon", "toast:sourdough"],
            "add": True,
        }
        await _lands(rig.driver, answered)

        # Lunch is not served at 8:15 AM: said at once, not ordered.
        t4 = await rig.driver.user_says("And a burger")
        check_turn(rig, t4, units=2)
        assert "served 11:00 AM to 10:00 PM" in t4.units[-1].text
        assert len(brain.guest.carts["dining"]) == 1

        t5 = await rig.driver.user_says("That's it, 15 percent tip")
        check_turn(rig, t5)
        totals = h.order_totals("dining", brain.guest.carts["dining"], 15)
        review = tool_results_of(llm.captured_inputs[-1], "review_order")[0]
        assert totals.subtotal == 46.00 and totals.total == 71.13
        assert f"total {h.money(totals.total)}" in review and "tip 15% $6.90" in review
        assert "Delivery in about 25 to 35 minutes, charged to room 1412" in review
        assert "The guest presses Place order." in review
        assert _move(rig, "cart.open")["args"] == {"outlet": "dining", "tip": 15}
        await _lands(rig.driver, answered)

        # The guest presses Place order.
        await _guest(
            rig,
            "order.placed",
            {
                "outlet": "dining",
                "id": "dining-1",
                "total": totals.total,
                "time": "25 to 35 minutes",
                "label": "2 Belmonte breakfast",
            },
        )
        assert brain.guest.carts["dining"] == []
        assert _said_later(brain) == (
            "Thank you, your order is in: $71.13 on your room bill, arriving in about 25 to 35 minutes. Anything else I can get you?"
        )
        assert any(c["amount"] == totals.total for c in brain.guest.charges)


async def test_drinks_to_a_cabana_with_the_age_rule() -> None:
    llm = ScriptedOpenAI(
        {
            "spritz": reply_and_call(
                "Two Halcyon Spritz.",
                "add_to_order",
                outlet="bar",
                item="Halcyon Spritz",
                quantity=2,
            ),
            "cabana 4": replies(
                call("review_order", outlet="bar", tip_percent=20, deliver_to="cabana", cabana="4"),
                reply("To cabana 4. Please have your ID ready; press Place order."),
            ),
        }
    )
    answered: set[str] = set()
    async with _rig(llm) as rig:
        await rig.driver.start_session(init={"page": "bar", "lang": "en", "stay": ARRIVED})
        t1 = await rig.driver.user_says("Two halcyon spritz please")
        check_turn(rig, t1)
        assert _move(rig, "menu.item")["args"]["item_id"] == "halcyon-spritz"
        await _lands(rig.driver, answered)
        t2 = await rig.driver.user_says("To cabana 4, 20 percent tip")
        check_turn(rig, t2)
        assert _move(rig, "cart.open")["args"] == {
            "outlet": "bar",
            "tip": 20,
            "deliver_to": "cabana",
            "cabana": "4",
        }
        review = tool_results_of(llm.captured_inputs[-1], "review_order")[0]
        assert "21 and over" in review and "photo ID" in review
        assert "total $47.60" in review  # $32 + $6.40 service + $2.80 tax + $6.40 tip


# ─── Spa ──────────────────────────────────────────────────────────────────────


async def test_a_spa_time_is_picked_from_the_free_ones_and_the_guest_books() -> None:
    llm = ScriptedOpenAI(
        {
            "deep tissue": replies(
                reply_and_call(
                    "Let me check the times.",
                    "spa_times",
                    treatment="80 minute deep tissue",
                    date="today",
                ),
                reply("There's 5:00 PM or 6:00 PM with Owen today. Which suits you?"),
            ),
            "3 pm": reply_and_call(
                "Let me hold that.",
                "choose_spa_time",
                treatment="80 minute deep tissue",
                date="today",
                time="3 pm",
            ),
            "5 pm": reply_and_call(
                "Lovely, 5 PM with Owen.",
                "choose_spa_time",
                treatment="80 minute deep tissue",
                date="today",
                time="5 pm",
            ),
        }
    )
    answered: set[str] = set()
    async with _rig(llm) as rig:
        await rig.driver.start_session(init={"page": "spa", "lang": "en", "stay": ARRIVED})
        brain = _brain(rig)
        t1 = await rig.driver.user_says("Can I get an 80 minute deep tissue massage today?")
        check_turn(rig, t1)
        times = tool_results_of(llm.captured_inputs[-1], "spa_times")[0]
        assert (
            "Deep tissue massage, 80 min, $255.00 plus $51.00 service charge, $306.00 in all."
            in times
        )
        assert "Free on Wed, Nov 25: 5:00 PM with Owen; 6:00 PM with Owen." in times
        assert "Free cancellation up to 24 hours" in times
        assert _move(rig, "spa.treatment")["args"] == {
            "treatment_id": "deep-80",
            "date": "2026-11-25",
        }
        await _lands(rig.driver, answered)

        t2 = await rig.driver.user_says("3 pm please")
        check_turn(rig, t2, units=2)
        assert "3:00 PM isn't free on Wed, Nov 25. There's 5:00 PM, 6:00 PM." in t2.units[-1].text
        assert "spa.slot" not in [m["move"] for m in _moves(rig)]

        t3 = await rig.driver.user_says("OK, 5 pm then")
        check_turn(rig, t3)
        assert _move(rig, "spa.slot")["args"] == {
            "treatment_id": "deep-80",
            "date": "2026-11-25",
            "time": "17:00",
            "therapist_id": "owen",
        }
        await _lands(rig.driver, answered)
        await _guest(
            rig,
            "spa.booked",
            {
                "id": "deep-80",
                "total": 306.0,
                "label": "Deep tissue massage, 80 min, Wed, Nov 25 at 5:00 PM with Owen",
            },
        )
        assert brain.guest.bookings and "Lovely, you're booked" in _said_later(brain)


# ─── Check-out on the last morning ────────────────────────────────────────────


async def test_check_out_reads_the_bill_questions_a_charge_and_leaves_the_last_press_to_the_guest() -> (
    None
):
    llm = ScriptedOpenAI(
        {
            "my bill": replies(
                reply_and_call("Here's your bill.", "open_bill"),
                reply("{show: Minibar} Your balance is $1,797.72."),
            ),
            "minibar": reply_and_call(
                "I'll write that up.",
                "question_charge",
                charge="the minibar",
                reason="We didn't use the minibar",
            ),
            "send it": reply_and_call(
                "Sending it.",
                "question_charge",
                charge="minibar",
                reason="We didn't use the minibar",
                send=True,
            ),
            "4 pm": replies(
                call("late_checkout", time="4 pm"), reply("4 PM is fully booked; 2 PM is $60.")
            ),
            "1 pm": replies(
                call("late_checkout", time="1 pm"), reply("1 PM is $40. Press Request.")
            ),
            "check out": reply_and_call("Here's express check-out.", "express_checkout"),
        }
    )
    answered: set[str] = set()
    async with _rig(llm) as rig:
        await rig.driver.start_session(init={"page": "checkout", "lang": "en", "stay": DEPARTURE})
        brain = _brain(rig)
        t1 = await rig.driver.user_says("Can I see my bill?")
        check_turn(rig, t1)
        bill = tool_results_of(llm.captured_inputs[-1], "open_bill")[0]
        assert "Minibar $24.00" in bill and "Two sparkling waters" in bill
        assert "Balance due $1,797.72" in bill
        assert _move(rig, "checkout.open")["args"] == {"part": "folio"}
        await _lands(rig.driver, answered)

        t2 = await rig.driver.user_says("We never touched the minibar")
        check_turn(rig, t2)
        assert _move(rig, "folio.dispute")["args"] == {
            "line_id": "minibar-1124",
            "reason": "We didn't use the minibar",
            "send": False,
        }
        assert "minibar-1124" not in brain.guest.disputes
        await _lands(rig.driver, answered)

        t3 = await rig.driver.user_says("Yes, send it")
        check_turn(rig, t3)
        assert _move(rig, "folio.dispute")["args"]["send"] is True
        assert "minibar-1124" in brain.guest.disputes
        await _lands(rig.driver, answered)

        t4 = await rig.driver.user_says("Can I stay until 4 pm?")
        check_turn(rig, t4)
        late = tool_results_of(llm.captured_inputs[-1], "late_checkout")[0]
        assert late.startswith("4:00 PM is Fully booked for this date")
        assert "late.pick" not in [m["move"] for m in _moves(rig)]

        t5 = await rig.driver.user_says("Then 1 pm")
        check_turn(rig, t5)
        assert _move(rig, "late.pick")["args"] == {"time": "13:00"}
        await _lands(rig.driver, answered)
        await _guest(rig, "late.requested", {"value": "13:00", "label": "1:00 PM", "total": 40.0})
        assert brain.guest.late_requested == "13:00"

        t6 = await rig.driver.user_says("And check out please")
        check_turn(rig, t6)
        assert _move(rig, "checkout.open")["args"] == {"part": "express"}
        express = tool_results_of(llm.captured_inputs[-1], "express_checkout")
        assert not express  # an action: its result reaches the model next turn
        assert not brain.guest.checked_out, "only the guest's own press checks out"
        await _guest(
            rig,
            "checkout.done",
            {"total": 1813.72, "label": "balance $1,813.72 on Visa ending 4417"},
        )
        assert brain.guest.checked_out
        assert _said_later(brain).startswith("You're all checked out, Maya.")


# ─── Visitors, requests, meetings, activities, the house ──────────────────────


async def test_visitors_requests_meetings_activities_and_policies() -> None:
    llm = ScriptedOpenAI(
        {
            "Who's waiting": replies(call("visitors"), reply("Three visitors are waiting.")),
            "Let Alex": reply_and_call(
                "Opening Alex's request.", "open_visitor", visitor="Alex Rivera", meet="lobby"
            ),
            "expecting Sam": reply_and_call(
                "I'll add Sam.",
                "expect_visitor",
                name="Sam Ortiz",
                from_time="6 pm",
                to_time="7 pm",
                meet="room",
            ),
            "towels": reply_and_call(
                "Sending towels.",
                "front_desk_request",
                kind="housekeeping",
                items=["towels", "extra pillows"],
                send=True,
            ),
            "airport": reply_and_call(
                "I'll set up the sedan.",
                "front_desk_request",
                kind="transport",
                option="airport sedan",
                time="10 am",
                send=True,
            ),
            "wake": reply_and_call(
                "Setting your wake-up call.",
                "front_desk_request",
                kind="wakeup",
                date="tomorrow",
                time="6:30 am",
                send=True,
            ),
            "dog": replies(
                call("hotel_info", topic="dogs"), reply("Dogs are welcome, $75 a night.")
            ),
            "30 people": replies(
                call("meeting_rooms", headcount=30, layout="classroom", date="Nov 30"),
                reply("The Marina Room fits 36 classroom."),
            ),
            "marina": replies(
                call(
                    "quote_meeting",
                    room="Marina Room",
                    date="Nov 30",
                    block="morning",
                    headcount=30,
                    layout="classroom",
                    catering=["coffee break", "working lunch"],
                    av=["extra mics"],
                ),
                reply("That's an estimated $3,608.85."),
            ),
            "kayak": reply_and_call(
                "I'll set that up.",
                "book_activity",
                activity="kayak tour",
                date="tomorrow",
                time="10 am",
                guests=2,
            ),
        }
    )
    answered: set[str] = set()
    async with _rig(llm) as rig:
        await rig.driver.start_session(init={"page": "requests", "lang": "en", "stay": ARRIVED})
        brain = _brain(rig)

        t = await rig.driver.user_says("Who's waiting for me?")
        check_turn(rig, t)
        vis = tool_results_of(llm.captured_inputs[-1], "visitors")[0]
        assert "Alex Rivera: Business meeting" in vis and "waiting 9 minutes" in vis
        await _lands(rig.driver, answered)

        t = await rig.driver.user_says("Let Alex wait in the lobby")
        check_turn(rig, t)
        assert _move(rig, "visitor.open")["args"] == {"visitor_id": "v-rivera", "meet": "lobby"}
        assert brain.guest.visitors["v-rivera"] == "pending", "only the guest's Approve approves"
        await _lands(rig.driver, answered)
        await _guest(
            rig,
            "visitor.decided",
            {"id": "v-rivera", "value": "approved", "label": "Alex Rivera, waiting in the lobby"},
        )
        assert brain.guest.visitors["v-rivera"] == "approved"
        assert _said_later(brain) == "Done, Alex Rivera will wait for you in the lobby."

        t = await rig.driver.user_says("I'm expecting Sam Ortiz between 6 and 7 pm, send him up")
        check_turn(rig, t)
        assert _move(rig, "visitor.expect")["args"] == {
            "name": "Sam Ortiz",
            "arrive_from": "18:00",
            "arrive_to": "19:00",
            "meet": "room",
        }
        await _lands(rig.driver, answered)

        t = await rig.driver.user_says("Yes please, extra towels and pillows")
        check_turn(rig, t)
        assert _move(rig, "request.fill")["args"] == {
            "kind": "housekeeping",
            "items": ["towels", "pillows"],
            "send": True,
        }
        await _lands(rig.driver, answered)

        # A ride that costs money is filled, never sent by the concierge.
        t = await rig.driver.user_says("And the airport sedan at 10 am, yes book it")
        check_turn(rig, t)
        assert _move(rig, "request.fill")["args"] == {
            "kind": "transport",
            "option": "airport",
            "time": "10:00",
            "send": False,
        }
        await _lands(rig.driver, answered)

        t = await rig.driver.user_says("A wake-up call tomorrow at 6:30 please, yes")
        check_turn(rig, t)
        assert _move(rig, "request.fill")["args"] == {
            "kind": "wakeup",
            "date": "2026-11-26",
            "time": "06:30",
            "send": True,
        }
        await _lands(rig.driver, answered)

        t = await rig.driver.user_says("Can I bring my dog next time?")
        check_turn(rig, t)
        pets = tool_results_of(llm.captured_inputs[-1], "hotel_info")[0]
        assert pets.startswith("Pet policy (open on screen):") and "$75 a night per room" in pets
        assert _move(rig, "info.open")["args"] == {"topic": "pets"}
        await _lands(rig.driver, answered)

        t = await rig.driver.user_says("I need a room for 30 people, classroom, on Nov 30")
        check_turn(rig, t)
        rooms = tool_results_of(llm.captured_inputs[-1], "meeting_rooms")[0]
        assert (
            "Marina Room" in rooms and "Grand Halcyon Ballroom" in rooms and "Pelican" not in rooms
        )
        assert _move(rig, "meeting.filter")["args"] == {
            "headcount": 30,
            "layout": "classroom",
            "date": "2026-11-30",
        }
        await _lands(rig.driver, answered)

        t = await rig.driver.user_says(
            "The marina room, morning, with coffee, lunch and extra mics"
        )
        check_turn(rig, t)
        quote = tool_results_of(llm.captured_inputs[-1], "quote_meeting")[0]
        assert "Estimate $3,608.85" in quote and "8:00 AM to 12:00 PM" in quote
        assert _move(rig, "meeting.pick")["args"] == {
            "room_id": "marina",
            "date": "2026-11-30",
            "block": "morning",
            "headcount": 30,
            "layout": "classroom",
            "catering": ["coffee", "lunch"],
            "av": ["mics"],
        }
        await _lands(rig.driver, answered)

        t = await rig.driver.user_says("Book the kayak tour tomorrow at 10 for two")
        check_turn(rig, t)
        assert _move(rig, "activity.pick")["args"] == {
            "activity_id": "kayak-tour",
            "date": "2026-11-26",
            "time": "10:00",
            "guests": 2,
        }


async def test_allergens_policies_front_desk_and_what_the_hotel_does_not_offer() -> None:
    llm = ScriptedOpenAI(
        {
            "gluten-free": replies(
                call("show_menu", outlet="dining", search="gluten-free"),
                reply("The Cobb salad and the New York strip are gluten-free."),
            ),
            "smoke": replies(call("hotel_info", topic="smoking"), reply("It's smoke-free.")),
            "parking": replies(call("hotel_info", topic="parking"), reply("Valet is $52 a night.")),
            "casino": replies(call("hotel_info", topic="casino"), reply("We don't have a casino.")),
            "laundry": reply_and_call(
                "Let me arrange that.", "front_desk_request", kind="laundry pickup", send=True
            ),
            "my car": reply_and_call(
                "Your car, coming up.", "front_desk_request", kind="valet", time="now", send=True
            ),
            "Decline Priya": reply_and_call("Opening it.", "open_visitor", visitor="Priya Chen"),
        }
    )
    answered: set[str] = set()
    async with _rig(llm) as rig:
        await rig.driver.start_session(init={"page": "dining", "lang": "en", "stay": ARRIVED})
        brain = _brain(rig)

        t = await rig.driver.user_says("What's gluten-free for lunch?")
        check_turn(rig, t)
        menu = tool_results_of(llm.captured_inputs[-1], "show_menu")[0]
        assert "Cliffside Cobb salad $21.00" in menu and "New York strip" in menu
        assert "Belmonte burger" not in menu and "Margherita" not in menu
        assert "contains egg, dairy" in menu, "allergens are read with the item"
        await _lands(rig.driver, answered)

        t = await rig.driver.user_says("Can I smoke on the balcony?")
        check_turn(rig, t)
        info = tool_results_of(llm.captured_inputs[-1], "hotel_info")[-1]
        assert "smoke-free, including vaping" in info and "$350 cleaning fee" in info
        await _lands(rig.driver, answered)

        t = await rig.driver.user_says("And what does parking cost?")
        check_turn(rig, t)
        info = tool_results_of(llm.captured_inputs[-1], "hotel_info")[-1]
        assert "Valet parking is $52 a night; self-parking is $35 a night." in info
        assert _move(rig, "info.open")["args"] == {"topic": "parking"}
        await _lands(rig.driver, answered)

        # Not offered: said plainly, nothing invented, nothing opened.
        moves = len(_moves(rig))
        t = await rig.driver.user_says("Is there a casino?")
        check_turn(rig, t)
        assert tool_results_of(llm.captured_inputs[-1], "hotel_info")[-1].startswith(
            "No section on 'casino'"
        )
        t = await rig.driver.user_says("Can you send someone for my laundry?")
        check_turn(rig, t, units=2)
        assert t.units[-1].text.startswith("I can arrange housekeeping, maintenance")
        assert len(_moves(rig)) == moves

        t = await rig.driver.user_says("Can I have my car now please, yes")
        check_turn(rig, t)
        assert _move(rig, "request.fill")["args"] == {
            "kind": "valet",
            "time": "14:40",
            "send": True,
        }
        await _lands(rig.driver, answered)

        t = await rig.driver.user_says("Decline Priya please")
        check_turn(rig, t)
        assert _move(rig, "visitor.open")["args"] == {"visitor_id": "v-chen"}
        await _lands(rig.driver, answered)
        await _guest(
            rig, "visitor.decided", {"id": "v-chen", "value": "declined", "label": "Priya Chen"}
        )
        assert brain.guest.visitors["v-chen"] == "declined"
        assert _said_later(brain) == "Done, the front desk will let Priya Chen know."


async def test_an_allergy_reads_what_lists_none_of_it() -> None:
    llm = ScriptedOpenAI(
        {
            "shellfish": replies(
                call("show_menu", outlet="dining", search="shellfish"),
                reply("The burger and the Cobb salad list no shellfish."),
            ),
        }
    )
    async with _rig(llm) as rig:
        await rig.driver.start_session(init={"page": "dining", "lang": "en", "stay": ARRIVED})
        t = await rig.driver.user_says("What's for lunch? I'm allergic to shellfish.")
        check_turn(rig, t)
        menu = tool_results_of(llm.captured_inputs[-1], "show_menu")[0]
        assert "Belmonte burger $26.00" in menu and "Grilled king salmon" in menu
        assert "clam chowder" not in menu.lower(), "the chowder lists shellfish"


async def test_an_action_that_leaves_a_button_for_the_guest_says_which() -> None:
    """The model says the action and stops ("I'll set up the kayak tour."): the
    guest still hears what is theirs to press; when it named the button, the
    brain adds nothing."""
    llm = ScriptedOpenAI(
        {
            "kayak": reply_and_call(
                "I'll set up the kayak tour for two.",
                "book_activity",
                activity="kayak tour",
                date="tomorrow",
                time="10 am",
                guests=2,
            ),
            "tennis": reply_and_call(
                "Done, press Book to confirm the court.",
                "book_activity",
                activity="tennis",
                date="tomorrow",
                time="8 am",
                guests=2,
            ),
        }
    )
    async with _rig(llm) as rig:
        await rig.driver.start_session(init={"page": "activities", "lang": "en", "stay": ARRIVED})
        t = await rig.driver.user_says("Book the kayak tour tomorrow at 10 for two")
        check_turn(rig, t, units=2)
        assert t.units[-1].text == "It's all set up, $178.00 on your room. Press Book to confirm."
        t = await rig.driver.user_says("And tennis at 8 tomorrow for two")
        check_turn(rig, t, units=1)


async def test_switching_tabs_mid_call_by_hand_and_by_her_cue() -> None:
    llm = ScriptedOpenAI(
        {
            "what's on": reply("{go: dining} Here's the in-room dining menu."),
            "the spa": reply("Lovely, the spa is open."),
        }
    )
    async with _rig(llm) as rig:
        await rig.driver.start_session(init={"page": "home", "lang": "en", "stay": ARRIVED})
        brain = _brain(rig)
        t = await rig.driver.user_says("So what's on the menu?")
        check_turn(rig, t)
        cues = [
            dict(c.get("payload") or {})
            for c in rig.driver.ui_commands
            if c.get("command") == "stage_cue"
        ]
        assert cues and cues[-1]["move"] == "app.go" and cues[-1]["args"] == ["dining"]
        assert "{go" not in t.text, "a cue is never spoken"
        # The guest taps over to the spa themselves: the next turn knows.
        await _guest(rig, "stay.page", {"page": "spa"})
        assert brain.guest.page == "spa"
        await rig.driver.user_says("I'm looking at the spa now")
        assert "Screen: spa." in input_texts(llm.captured_inputs[-1])


async def test_the_scenario_switch_starts_the_stay_over() -> None:
    llm = ScriptedOpenAI({"hello": reply("Hello!")})
    async with _rig(llm) as rig:
        await rig.driver.start_session(init={"page": "home", "lang": "en"})
        brain = _brain(rig)
        assert brain.guest.scenario == "arrival" and not brain.guest.checked_in
        await _guest(rig, "stay.scenario", {"scenario": "departure", "label": "Check-out day"})
        assert brain.guest.scenario == "departure" and brain.guest.room == "1412"
        assert "the morning the guest checks out" in brain.system_instruction
        await rig.driver.user_says("hello")
        assert "Checked in, room 1412" in input_texts(llm.captured_inputs[-1])


# ─── Language, persona, speech ────────────────────────────────────────────────


async def test_english_only_whatever_the_page_asks() -> None:
    async with _rig(ScriptedOpenAI()) as rig:
        await rig.driver.start_session(init={"page": "home", "lang": "hi"})
        check_voice_pair(rig, voice=LANGUAGES["en"].voice, language="en")
        brain = _brain(rig)
        assert brain.lang == "en" and "You speak English only" in brain.system_instruction
        assert "set_language" not in [t.__name__ for t in brain.tools]


def test_the_character_comes_from_persona_json() -> None:
    raw = json.loads((h.ROOT / "persona.json").read_text())
    assert {t: s.voice for t, s in LANGUAGES.items()} == {
        t: v["voice"] for t, v in raw["languages"].items()
    }
    assert raw["name"] == NAME == "Kasia" and raw["character"] == "kasia"
    assert list(raw["languages"]) == ["en"]


def test_room_numbers_are_said_the_way_a_front_desk_says_them() -> None:
    assert room_words("1412") == "fourteen twelve"
    assert room_words("1108") == "eleven oh eight"
    assert room_words("0516") == "five sixteen"
    assert room_words("0921") == "nine twenty-one"
    assert (
        speak_text("Room 1412, floor 14, $18.50 at 7:30 PM.")
        == "Room fourteen twelve, floor 14, $18.50 at 7:30 PM."
    )


def test_times_and_days_as_the_guest_says_them() -> None:
    assert parse_time("7:30 pm") == "19:30"
    assert parse_time("5 PM") == "17:00"
    assert parse_time("10 am") == "10:00"
    assert parse_time("noon") == "12:00"
    assert parse_time("half past six in the evening") == "18:30"
    assert parse_time("now", "14:40") == "14:40"
    assert parse_date("tomorrow", "2026-11-25") == "2026-11-26"
    assert parse_date("Friday", "2026-11-25") == "2026-11-27"
    assert parse_date("Nov 30", "2026-11-25") == "2026-11-30"


async def test_the_umbrella_factory_builds_the_brain() -> None:
    async with demo("belmonte", ScriptedOpenAI()) as rig:
        greeting = await rig.driver.start_session()
        check_greeting(rig, greeting)
        check_voice_pair(rig, voice=LANGUAGES["en"].voice, language="en")


def test_the_rules_cases_are_current() -> None:
    """data/rules_cases.json is what the app's vitest holds its rules to."""
    path = h.ROOT / "data" / "rules_cases.json"
    before = path.read_text()
    h.write_cases()
    assert path.read_text() == before, "rules_cases.json was stale; it has been rewritten"


# ─── Redial: a dropped brain socket does not end the call ─────────────────────


def _configs(driver: VoqalizeDriver) -> list[ConfigureFrame]:
    return [r for r in driver.requests if isinstance(r, ConfigureFrame)]


def _redials(driver: VoqalizeDriver) -> list[bool | None]:
    return [c.config.redial.enabled for c in _configs(driver) if c.config.redial is not None]


def _redial_llm() -> ScriptedOpenAI:
    return ScriptedOpenAI(
        {
            "check me in": reply_and_call("Let's check you in.", "start_check_in"),
            "that's mine": reply_and_call("Thank you.", "confirm_reservation"),
            "burger": reply_and_call(
                "A burger.",
                "add_to_order",
                outlet="dining",
                item="Belmonte burger",
                choices=["medium", "fries"],
            ),
            "my order": replies(call("review_order", outlet="dining"), reply("Here's your order.")),
        }
    )


async def _redial_rig(llm: ScriptedOpenAI, sid: str) -> tuple[Any, list[BelmonteBrain], Any]:
    from voqalize.conformance import (
        BrainServer,
        DirectConnection,
        generate_keypair,
        mint_voqalize_token,
    )

    built: list[BelmonteBrain] = []

    def _build() -> BelmonteBrain:
        brain = BelmonteBrain(client=llm)  # type: ignore[arg-type]
        built.append(brain)
        return brain

    keypair = generate_keypair()
    server = BrainServer(_build, host="127.0.0.1", port=0, public_keys=keypair.public_pem)
    port = await server.start()

    def driver() -> VoqalizeDriver:
        token = mint_voqalize_token(
            private_key_pem=keypair.private_pem,
            session_id=sid,
            agent_id="belmonte",
            tenant_id="demo",
        )
        return VoqalizeDriver(
            DirectConnection(f"ws://127.0.0.1:{port}", sid, token=token),
            session_id=sid,
            default_timeout=10.0,
        )

    return server, built, driver


async def _drop(driver: VoqalizeDriver, brain: BelmonteBrain) -> None:
    from voqalize_demos._loaded.belmonte.brain import REJOIN

    await driver.aclose()
    for _ in range(50):
        entry = REJOIN._held.get(driver.session_id)  # pyright: ignore[reportPrivateUsage]
        if entry is not None and entry[0] is brain and entry[2] is not None:
            return
        await asyncio.sleep(0.02)
    raise AssertionError("the dropped socket never reached on_session_end")


async def test_a_dropped_socket_rejoins_the_call_where_it_was() -> None:
    """Mid check-in with an order started, the socket drops without a hang-up;
    the redialled brain adopts the call (check-in progress, the order, the
    model's history), greets no one, and the next turn carries on."""
    llm = _redial_llm()
    sid = "belmonte-redial-e2e"
    server, built, driver = await _redial_rig(llm, sid)
    first, second = driver(), driver()
    init = {"page": "home", "lang": "en", "stay": {"scenario": "arrival"}}
    try:
        await first.open()
        greeting = await first.start_session(init=init)
        assert greeting is not None
        assert _redials(first) == [True]
        answered: set[str] = set()
        await first.user_says("Please check me in")
        await _lands(first, answered)
        await first.user_says("Yes that's mine")
        await _lands(first, answered)
        before = built[-1]
        before.guest.checked_in, before.guest.room = True, "1412"  # checked in on screen meanwhile
        await first.user_says("And a burger, medium with fries")
        await _lands(first, answered)
        assert before.guest.checkin.confirmed and len(before.guest.carts["dining"]) == 1
        history_before = len(before._history)  # pyright: ignore[reportPrivateUsage]

        await _drop(first, before)

        await second.open()
        regreeting = await second.start_session(init=init, greeting_timeout=0.5)
        after = built[-1]
        assert after is not before and regreeting is None
        assert after.guest.checkin.confirmed and after.guest.room == "1412"
        assert [ln.item_id for ln in after.guest.carts["dining"]] == ["belmonte-burger"]
        assert len(after._history) >= history_before  # pyright: ignore[reportPrivateUsage]
        assert _redials(second) == [True]

        turn = await second.user_says("Show me my order")
        assert turn.units
        review = tool_results_of(llm.captured_inputs[-1], "review_order")[0]
        assert "1 Belmonte burger (Medium, Fries)" in review
        heard = json.dumps(llm.captured_inputs[-1], ensure_ascii=False)
        assert "Please check me in" in heard, "the model's history came across"
        moved = [
            c["payload"]["move"] for c in second.ui_commands if c.get("command") == "stage_move"
        ]
        assert moved == ["cart.open"], moved
    finally:
        await second.aclose()
        await server.aclose()


async def test_a_redial_after_two_minutes_starts_fresh_from_init() -> None:
    from voqalize_demos._loaded.belmonte.brain import REJOIN
    from voqalize_demos._loaded.belmonte.rejoin import KEEP_AFTER_DROP_S

    llm = _redial_llm()
    sid = "belmonte-redial-expired-e2e"
    server, built, driver = await _redial_rig(llm, sid)
    now = [1000.0]
    REJOIN._clock = lambda: now[0]  # pyright: ignore[reportPrivateUsage]
    first, second = driver(), driver()
    try:
        await first.open()
        await first.start_session(init={"page": "home", "lang": "en"})
        await first.user_says("Please check me in")
        await first.user_says("Yes that's mine")
        before = built[-1]
        assert before.guest.checkin.confirmed
        await _drop(first, before)
        now[0] += KEEP_AFTER_DROP_S + 1
        assert len(REJOIN) == 0

        await second.open()
        greeting = await second.start_session(init={"page": "home", "lang": "en"})
        after = built[-1]
        assert greeting is not None
        assert not after.guest.checkin.confirmed and not after._history[1:]  # pyright: ignore[reportPrivateUsage]
    finally:
        REJOIN._clock = __import__("time").monotonic  # pyright: ignore[reportPrivateUsage]
        await second.aclose()
        await server.aclose()


async def test_no_redial_is_asked_of_a_voqalize_that_does_not_offer_it() -> None:
    from voqalize.sdk.wire import Capability

    async with _rig(ScriptedOpenAI()) as rig:
        rig.driver.capabilities.discard(Capability.REDIAL)
        greeting = await rig.driver.start_session(init={"page": "home", "lang": "en"})
        check_greeting(rig, greeting)
        assert _redials(rig.driver) == []
        check_voice_pair(rig, voice=LANGUAGES["en"].voice, language="en")
