"""Dantika Dental's front desk, end to end over the wire: no network, no LLM key.

The real ``DentalBrain`` (its prompt, tools, the clinic's authored data and the
slot engine) on a real ``brain_server`` socket, driven by the conformance
``VoqalizeDriver``, with only the model scripted (``ScriptedOpenAI``, flat tool
arguments). The clock is fixed to a Wednesday morning in Bengaluru, so the slots
the script holds are the ones the engine computes.

One storyline per landing page:

- ``/book``: a root canal, from the slots on the calendar to a held slot, the
  sign-in box rung for the patient to type into, the typed sign-in answered with
  a welcome by name that reads the held slot back, a refused confirm (no yes
  yet) and the booking with its two later sittings pencilled in.
- ``/my-appointments``: Rohan signs in by typing, hears his appointments, moves
  his cleaning to a free slot and says yes; the change goes to the page.

Sign-in is typed, never spoken (FEEDBACK X9): Meera has no tool that fills a
number or a code; a number or code said aloud is withheld from the model and she
asks for it to be typed; a typed sign-in reaches the brain as an event with the
patient's id and first name, and she welcomes them and carries on with what they
asked; a wrong code is said without the code; no request to the model ever holds
the phone number or the code.
- ``/`` in Hindi: the greeting and both legs in Hindi, a parking question rung
  on the page, and a clinical question routed to a dentist's callback.

Plus the rules that are code, not prompt: a CBCT without a referral or a
consultation is refused; the language toggle moves both legs mid-call; a move the
page refused is undone and said; a call whose socket drops mid-change is redialled
and carries on where it was (CONTRACT.md, "Redial").

Run: ``cd demos && uv run pytest tests/test_dental_e2e.py``
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from voqalize_demos.discovery import build_for, discover
from voqalize_demos.testing import (
    ScriptedOpenAI,
    call,
    input_texts,
    reply,
    reply_and_call,
    tool_results_of,
)

from voqalize.conformance import (
    BrainServer,
    DirectConnection,
    VoqalizeDriver,
    generate_keypair,
    mint_voqalize_token,
)
from voqalize.sdk.stage import load_spec
from voqalize.sdk.stage.gen import render_python, render_typescript
from voqalize.sdk.wire import Capability, ConfigureFrame

from ._harness import DemoRig, _configs, check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.dental import clinic as cl  # noqa: E402
from voqalize_demos._loaded.dental.brain import (  # noqa: E402
    REJOIN,
    DentalBrain,
    affirmed,
    clinical,
)
from voqalize_demos._loaded.dental.credentials import CODE_MARK, PHONE_MARK, withhold  # noqa: E402
from voqalize_demos._loaded.dental.persona import PERSONA  # noqa: E402
from voqalize_demos._loaded.dental.prompt import LINES, greeting  # noqa: E402
from voqalize_demos._loaded.dental.rejoin import KEEP_AFTER_DROP_S, Rejoin  # noqa: E402

NOW = datetime(2026, 11, 18, 10, 7, tzinfo=cl.IST)  # a Wednesday morning
CAL = cl.Calendar.build(NOW)
RCT = cl.service("rct")
assert RCT is not None
RCT_DAYS = CAL.next_days(RCT, dentist_id="dr-kavitha", start=NOW.date() + timedelta(days=5), days=1)
RCT_SLOT = RCT_DAYS[0][1][0]
RCT_PLAN = CAL.plan_sittings(RCT, RCT_SLOT)


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(cl, "now_ist", lambda: NOW)
    yield


@pytest.fixture(autouse=True)
def _no_call_carried_between_tests() -> Iterator[None]:
    """Every test here opens the same session id, and a dropped call is held for
    a redial to rejoin (CONTRACT.md, "Redial"): clear the store around each
    test, so no test rejoins the one before it. Real session ids never repeat."""
    REJOIN.clear()
    yield
    REJOIN.clear()


def _moves(rig: DemoRig, move: str | None = None) -> list[dict[str, Any]]:
    out = [
        dict(c.get("payload") or {})
        for c in rig.driver.ui_commands
        if c.get("command") == "stage_move"
    ]
    return [m for m in out if move is None or m.get("move") == move]


async def _until(rig: DemoRig, move: str, count: int = 1) -> dict[str, Any]:
    for _ in range(200):
        got = _moves(rig, move)
        if len(got) >= count:
            return got[count - 1]
        await asyncio.sleep(0.02)
    raise AssertionError(f"no {move} #{count}: {[m['move'] for m in _moves(rig)]}")


async def _answer(
    rig: DemoRig, move: dict[str, Any], outcome: str = "applied", detail: str = ""
) -> None:
    await rig.driver.send_ui_event(
        "stage_result",
        {"call_ref": move["call_ref"], "move": move["move"], "outcome": outcome, "detail": detail},
    )
    await asyncio.sleep(0.05)


def _results(llm: ScriptedOpenAI, name: str) -> list[str]:
    out: list[str] = []
    for items in llm.captured_inputs:
        for r in tool_results_of(items, name):
            if r not in out:
                out.append(r)
    return out


#: What must never reach the model: Rohan's number (as typed and as spoken) and
#: the demo code.
_SECRETS = ("9845031726", "98450 31726", "98450", cl.DATA_.otp.demo_code)


def _no_secrets(llm: ScriptedOpenAI) -> None:
    """No request the model was sent holds a phone number or the code."""
    sent = json.dumps(llm.requests, ensure_ascii=False)
    for secret in _SECRETS:
        assert secret not in sent, f"{secret!r} reached the model"


async def _typed_sign_in(
    driver: VoqalizeDriver, patient_id: str, name: str, *, is_new: bool = False
) -> None:
    """The visitor types their number, then the code, and the page signs them in:
    the two events the page sends, with no number or code in either."""
    await driver.send_ui_event("sign_in_step", {"step": "code_sent", "by": "visitor"})
    await driver.send_ui_event(
        "patient_signed_in",
        {
            "patient_id": patient_id,
            "name": name,
            "first_name": name.split()[0],
            "is_new": is_new,
            "by": "visitor",
        },
    )
    await asyncio.sleep(0.1)


# ─── /book ────────────────────────────────────────────────────────────────────


def _book_script() -> ScriptedOpenAI:
    s = RCT_SLOT
    return ScriptedOpenAI(
        {
            "I need a root canal": [
                reply_and_call(
                    "Let me pull up Dr Kavitha's calendar.", "find_slots", service="root canal"
                ),
                reply("The earliest is next week. Which suits you?"),
            ],
            "The first one please": [
                reply_and_call(
                    "I'll hold that one.",
                    "hold_slot",
                    service="rct",
                    date=s.on.isoformat(),
                    time=s.time,
                    dentist="dr-kavitha",
                    branch=s.branch,
                ),
                reply(
                    "It's held. {signin: phone} Please type your mobile number in the box on screen."
                ),
            ],
            "just signed in on screen": [
                reply(
                    "Hi Rohan, you're signed in. Your root canal with Dr Kavitha is held: shall I confirm it?"
                ),
            ],
            "Hmm, what does it cost?": [
                reply_and_call("Confirming now.", "confirm_booking"),
            ],
            "Yes, go ahead": [
                reply_and_call("Booking it now.", "confirm_booking"),
            ],
        }
    )


async def test_book_a_root_canal_with_its_sittings() -> None:
    llm = _book_script()
    async with demo("dental", llm) as rig:
        greeting_turn = await rig.driver.start_session(
            init={"surface": "dental-web", "landing": "book", "path": "/book", "lang": "en"}
        )
        check_greeting(rig, greeting_turn)
        assert greeting_turn is not None
        assert greeting_turn.text == greeting("en", "book")
        check_voice_pair(rig, voice=PERSONA.voice("en"), language="en")
        brain = rig.brain
        assert isinstance(brain, DentalBrain)

        await rig.driver.user_says("I need a root canal")
        slots = await _until(rig, "book.slots")
        assert slots["args"]["service_id"] == "rct"
        assert slots["args"]["dentist_id"] == "dr-kavitha"
        found = _results(llm, "find_slots")[0]
        first_day, first_slots = CAL.next_days(RCT)[0]
        assert first_day.isoformat() in found
        assert first_slots[0].time in found
        assert "₹6,500 to ₹12,000" in found
        await _answer(rig, slots)

        await rig.driver.user_says("The first one please")
        hold = await _until(rig, "book.hold")
        assert hold["args"]["date"] == RCT_SLOT.on.isoformat()
        assert hold["args"]["time"] == RCT_SLOT.time
        assert hold["args"]["chair_id"] == RCT_SLOT.chair
        assert hold["args"]["sittings"] == [
            f"{p.on.isoformat()} {p.time} {p.branch} {p.chair}" for p in RCT_PLAN
        ]
        held = _results(llm, "hold_slot")[0]
        assert "Not signed in yet" in held and "type their mobile number" in held
        # The sign-in box is rung for the patient to type into; nothing is filled.
        ask = await _until(rig, "patient.ask")
        assert ask["args"] == {"field": "phone"}
        await _answer(rig, hold)
        await _answer(rig, ask)

        # Rohan types his number and the code; the page tells the brain.
        await _typed_sign_in(rig.driver, "P-1001", "Rohan Mehta")
        assert brain.patient is not None and brain.patient.id == "P-1001"
        welcome = await rig.driver.user_idle()
        check_turn(rig, welcome)
        said = " ".join(u.text for u in welcome.units)
        assert said.startswith("Hi Rohan, you're signed in.")
        told = input_texts(llm.captured_inputs[-1])
        assert "Rohan just signed in on screen" in told
        assert "The held slot (Root canal" in told, "the welcome carries on with the held slot"

        # No yes yet: the confirm is refused in code, whatever the model did.
        await rig.driver.user_says("Hmm, what does it cost?")
        await asyncio.sleep(0.1)
        assert _moves(rig, "book.confirm") == []
        await rig.driver.user_says("Yes, go ahead")
        confirm = await _until(rig, "book.confirm")
        assert "not said yes" in _results(llm, "confirm_booking")[0]
        args = confirm["args"]
        assert args["booking_id"] == "DT-24117"
        assert args["patient_id"] == "P-1001"
        assert args["sitting_ids"] == ["DT-24118", "DT-24119"]
        # The calendar the brain answers from now holds all three sittings.
        mine = [
            a
            for a in brain.cal.upcoming("P-1001")
            if a.service == "rct" and a.id.startswith("DT-241")
        ]
        assert [a.sitting for a in mine] == [1, 2, 3]
        assert brain.cal.slot_at(RCT, RCT_SLOT.on, RCT_SLOT.time, dentist_id="dr-kavitha") is None
        await _answer(rig, confirm, detail="booked DT-24117")
        assert not [m for m in _moves(rig) if m["move"] in ("patient.phone", "patient.otp")]
        _no_secrets(llm)


async def test_a_refused_confirm_is_undone_and_said() -> None:
    llm = _book_script()
    async with demo("dental", llm) as rig:
        await rig.driver.start_session(init={"landing": "book", "lang": "en"})
        brain = rig.brain
        assert isinstance(brain, DentalBrain)
        for text in ("I need a root canal", "The first one please"):
            await rig.driver.user_says(text)
        await _typed_sign_in(rig.driver, "P-1001", "Rohan Mehta")
        await rig.driver.user_idle()
        await rig.driver.user_says("Yes, go ahead")
        confirm = await _until(rig, "book.confirm")
        assert "DT-24117" in brain.cal.appts
        await _answer(rig, confirm, outcome="refused", detail="that slot was just taken on screen")
        assert "DT-24117" not in brain.cal.appts
        assert brain._say_next is not None and "just taken" in brain._say_next


async def test_a_cbct_without_referral_or_consult_is_refused() -> None:
    llm = ScriptedOpenAI(
        {
            "I want a CBCT scan": [
                reply_and_call("Checking.", "find_slots", service="cbct", branch="indiranagar"),
                reply("A CBCT needs a consultation first."),
            ],
        }
    )
    async with demo("dental", llm) as rig:
        await rig.driver.start_session(init={"landing": "book", "lang": "en"})
        await _typed_sign_in(rig.driver, "P-1002", "Ishita Banerjee")
        await rig.driver.user_says("I want a CBCT scan")
        found = _results(llm, "find_slots")[0]
        assert "Not bookable for Ishita Banerjee" in found
        assert "consult" in found
        assert _moves(rig, "book.slots") == []


# ─── /my-appointments ─────────────────────────────────────────────────────────


async def test_reschedule_a_cleaning_after_a_yes() -> None:
    scaling = cl.service("scaling")
    assert scaling is not None
    a = CAL.appts["DT-24063"]
    target_day, targets = CAL.next_days(
        scaling, dentist_id=a.dentist, start=a.on + timedelta(days=1), ignore=a.id
    )[0]
    target = targets[0]
    llm = ScriptedOpenAI(
        {
            "What do I have coming up": [
                call("my_appointments"),
                reply("A root canal sitting and a cleaning."),
            ],
            "Move the cleaning": [
                reply_and_call(
                    "Let me put that on screen.",
                    "propose_change",
                    appointment_id="DT-24063",
                    action="reschedule",
                    date=target_day.isoformat(),
                    time=target.time,
                ),
                reply("It's free to move. Shall I go ahead?"),
            ],
            "Yes please": [reply_and_call("Moving it now.", "confirm_change")],
        }
    )
    async with demo("dental", llm) as rig:
        greeting_turn = await rig.driver.start_session(
            init={"landing": "my-appointments", "lang": "en"}
        )
        assert greeting_turn is not None and greeting_turn.text == greeting("en", "my-appointments")
        brain = rig.brain
        assert isinstance(brain, DentalBrain)
        await _typed_sign_in(rig.driver, "P-1001", "Rohan Mehta")
        await rig.driver.user_says("What do I have coming up")
        listed = _results(llm, "my_appointments")[0]
        assert "DT-24051" in listed and "DT-24063" in listed
        assert "sitting 2 of 3" in listed

        await rig.driver.user_says("Move the cleaning")
        propose = await _until(rig, "appt.propose")
        assert propose["args"]["appointment_id"] == "DT-24063"
        assert propose["args"]["date"] == target_day.isoformat()
        assert propose["args"]["time"] == target.time
        assert propose["args"]["fee"] == 0
        await _answer(rig, propose)

        await rig.driver.user_says("Yes please")
        apply = await _until(rig, "appt.apply")
        assert apply["args"]["action"] == "reschedule"
        moved = brain.cal.appts["DT-24063"]
        assert moved.on == target_day and cl.hhmm(moved.start) == target.time and moved.changes == 1


async def test_a_root_canal_sitting_stays_in_its_window() -> None:
    llm = ScriptedOpenAI(
        {
            "Move my root canal to three weeks later": [
                call(
                    "propose_change",
                    appointment_id="DT-24051",
                    action="reschedule",
                    date=(CAL.appts["DT-24051"].on + timedelta(days=21)).isoformat(),
                    time="11:00",
                ),
                reply("That's too late for a sitting."),
            ],
        }
    )
    async with demo("dental", llm) as rig:
        await rig.driver.start_session(init={"landing": "my-appointments", "lang": "en"})
        await _typed_sign_in(rig.driver, "P-1001", "Rohan Mehta")
        await rig.driver.user_says("Move my root canal to three weeks later")
        assert "can only move to between" in _results(llm, "propose_change")[0]
        assert _moves(rig, "appt.propose") == []


# ─── Sign-in: typed, never spoken (FEEDBACK X9) ───────────────────────────────


async def test_sign_in_is_typed_and_the_welcome_carries_on() -> None:
    """On /my-appointments Rohan asks to move his cleaning before signing in.
    Meera rings the sign-in box; he says his number aloud anyway and then the
    code: neither reaches the model, nothing is filled, and the box is rung
    again. He types a wrong code: the page shows it and Meera says it didn't go
    through, without the code. He types the right one: the page sends his id and
    first name, and in the next quiet moment Meera welcomes him by name and
    carries on with the move he asked for."""
    scaling = cl.service("scaling")
    assert scaling is not None
    llm = ScriptedOpenAI(
        {
            "I'd like to move my cleaning": [
                call("my_appointments"),
                reply("{signin: phone} Please type your mobile number in the box on screen."),
            ],
            "My number is": reply("For your privacy, please type it in the box on screen."),
            "the code is": reply("Please type the code in the box on screen."),
            "just signed in on screen": [
                reply_and_call(
                    "Hi Rohan, you're signed in. Let's move your cleaning.",
                    "propose_change",
                    appointment_id="DT-24063",
                    action="reschedule",
                ),
                reply("Which of these times suits you?"),
            ],
        }
    )
    async with demo("dental", llm) as rig:
        greeted = await rig.driver.start_session(init={"landing": "my-appointments", "lang": "en"})
        assert greeted is not None and greeted.text == greeting("en", "my-appointments")
        assert "type your mobile number" in greeted.text
        brain = rig.brain
        assert isinstance(brain, DentalBrain)

        await rig.driver.user_says("I'd like to move my cleaning")
        listed = _results(llm, "my_appointments")[0]
        assert "Not signed in yet" in listed and "Never ask them to say" in listed
        ask = await _until(rig, "patient.ask")
        assert ask["args"] == {"field": "phone"}
        await _answer(rig, ask)

        # Said aloud anyway: withheld from the model, the box rung again.
        await rig.driver.user_says("My number is 98450 31726")
        told = input_texts(llm.captured_inputs[-1])
        assert f"My number is {PHONE_MARK}" in told
        assert "They said their mobile number aloud. It was not kept" in told
        again = await _until(rig, "patient.ask", 2)
        assert again["args"] == {"field": "phone"}
        await _answer(rig, again)
        assert brain.patient is None

        # He types the number; then says the code aloud: withheld too.
        await rig.driver.send_ui_event("sign_in_step", {"step": "code_sent", "by": "visitor"})
        await asyncio.sleep(0.05)
        await rig.driver.user_says("OK the code is 4821")
        told = input_texts(llm.captured_inputs[-1])
        assert f"the code is {CODE_MARK}" in told
        code_ask = await _until(rig, "patient.ask", 3)
        assert code_ask["args"] == {"field": "code"}
        await _answer(rig, code_ask)

        # A wrong code typed: said, without the code; nobody signed in.
        await rig.driver.send_ui_event("sign_in_step", {"step": "wrong_code", "by": "visitor"})
        await asyncio.sleep(0.05)
        failed = await rig.driver.user_idle()
        said = " ".join(u.text for u in failed.units)
        assert said == LINES["en"]["code_failed"]
        assert brain.patient is None and brain.signin == "code_sent"

        # The right code typed: the welcome by name, and on with the move.
        await rig.driver.send_ui_event(
            "patient_signed_in",
            {
                "patient_id": "P-1001",
                "name": "Rohan Mehta",
                "first_name": "Rohan",
                "is_new": False,
                "by": "visitor",
            },
        )
        await asyncio.sleep(0.05)
        assert brain.patient is not None and brain.patient.id == "P-1001"
        welcome = await rig.driver.user_idle()
        said = " ".join(u.text for u in welcome.units)
        assert said.startswith("Hi Rohan, you're signed in.")
        told = input_texts(llm.captured_inputs[-1])
        assert "Rohan just signed in on screen" in told and "DT-24063" in told
        assert "Free times for DT-24063" in _results(llm, "propose_change")[0]
        await _until(rig, "cal.view")

        # Meera never filled a number or a code, and the model never held one.
        assert not [m for m in _moves(rig) if m["move"] in ("patient.phone", "patient.otp")]
        _no_secrets(llm)


async def test_a_returning_patient_is_greeted_by_name() -> None:
    """Signed in on this browser before the call: the page names him by id in
    init, the greeting uses his first name, and the restored sign-in event the
    page sends on connect is not welcomed a second time."""
    llm = ScriptedOpenAI({"hello": reply("Hi!")})
    async with demo("dental", llm) as rig:
        greeted = await rig.driver.start_session(
            init={"landing": "my-appointments", "lang": "en", "patient_id": "P-1001"}
        )
        assert greeted is not None
        assert greeted.text == greeting("en", "my-appointments", "Rohan")
        assert greeted.text.startswith("Hi Rohan,")
        brain = rig.brain
        assert isinstance(brain, DentalBrain)
        assert brain.patient is not None and brain.patient.id == "P-1001"
        await rig.driver.send_ui_event(
            "patient_signed_in",
            {
                "patient_id": "P-1001",
                "name": "Rohan Mehta",
                "first_name": "Rohan",
                "restored": True,
                "by": "visitor",
            },
        )
        await asyncio.sleep(0.05)
        assert brain._talk_next is None
        quiet = await rig.driver.user_idle(timeout=0.5)
        assert not quiet.units


async def test_a_new_patient_types_their_number_too() -> None:
    """A new patient booking: the number is typed and verified on the page, the
    page asks for a name, Meera asks for it and registers it (a name is not a
    credential), and the booking goes to the new patient id."""
    s = RCT_SLOT
    llm = ScriptedOpenAI(
        {
            "I need a root canal": [
                call("find_slots", service="root canal"),
                reply("The earliest is next week."),
            ],
            "The first one please": [
                call(
                    "hold_slot",
                    service="rct",
                    date=s.on.isoformat(),
                    time=s.time,
                    dentist="dr-kavitha",
                    branch=s.branch,
                ),
                reply("{signin: phone} Please type your mobile number in the box on screen."),
            ],
            "Asha Rao": [reply_and_call("Registering you.", "register_patient", name="Asha Rao")],
            "Yes, book it": [reply_and_call("Booking it now.", "confirm_booking")],
        }
    )
    async with demo("dental", llm) as rig:
        await rig.driver.start_session(init={"landing": "book", "lang": "hi"})
        brain = rig.brain
        assert isinstance(brain, DentalBrain)
        for text in ("I need a root canal", "The first one please"):
            await rig.driver.user_says(text)
        await _until(rig, "patient.ask")
        await rig.driver.send_ui_event("sign_in_step", {"step": "code_sent", "by": "visitor"})
        await rig.driver.send_ui_event("sign_in_step", {"step": "name_needed", "by": "visitor"})
        await asyncio.sleep(0.05)
        asked = await rig.driver.user_idle()
        assert " ".join(u.text for u in asked.units) == LINES["hi"]["name_needed"]

        await rig.driver.user_says("Asha Rao")
        name = await _until(rig, "patient.name")
        assert name["args"] == {"name": "Asha Rao"}
        await _answer(rig, name, detail="registered Asha Rao as new patient P-2001")
        # The page reports the registration it made for the agent: no welcome owed.
        await rig.driver.send_ui_event(
            "patient_signed_in",
            {
                "patient_id": "P-2001",
                "name": "Asha Rao",
                "first_name": "Asha",
                "is_new": True,
                "by": "agent",
            },
        )
        await asyncio.sleep(0.05)
        assert brain.patient is not None and brain.patient.id == "P-2001"
        assert brain._talk_next is None
        await rig.driver.user_says("Yes, book it")
        confirm = await _until(rig, "book.confirm")
        assert confirm["args"]["patient_id"] == "P-2001"


def test_spoken_numbers_and_codes_are_withheld() -> None:
    assert withhold("98450 31726").kinds == ("phone",)
    assert withhold("plus nine one nine eight four five zero three one seven two six").kinds == (
        "phone",
    )
    assert withhold("मेरा नंबर नौ आठ चार पाँच शून्य तीन एक सात दो छह है").kinds == ("phone",)
    assert withhold("It's 4821", expecting_code=True).text == f"It's {CODE_MARK}"
    assert withhold("the OTP is four eight two one").kinds == ("code",)
    # Not a code: no code expected or named, or it is money.
    assert withhold("It's 4821").kinds == ()
    assert withhold("Is it under 5000 rupees?", expecting_code=True).kinds == ()
    assert withhold("Is a filling under dedh hazaar?", expecting_code=True).kinds == ()
    assert withhold("The first one please").text == "The first one please"


# ─── / in Hindi ───────────────────────────────────────────────────────────────


async def test_home_in_hindi_parking_and_a_clinical_callback() -> None:
    llm = ScriptedOpenAI(
        {
            "पार्किंग कहाँ है": [
                reply_and_call(
                    "{show: parking} बताती हूँ।", "clinic_info", topic="parking", branch="indiranagar"
                ),
                reply("Basement में चार visitor bays हैं।"),
            ],
            "दाँत निकलवाने के बाद खून आ रहा है": [
                reply_and_call(
                    "ये dentist को बताना होगा, मैं call back करवाती हूँ।",
                    "request_callback",
                    reason="Bleeding after an extraction",
                    urgency="urgent",
                ),
            ],
        }
    )
    async with demo("dental", llm) as rig:
        # Suresh signed in on this browser before the call: the page names him by id.
        greeting_turn = await rig.driver.start_session(
            init={"landing": "home", "lang": "hi", "patient_id": "P-1003"}
        )
        check_greeting(rig, greeting_turn)
        assert greeting_turn is not None and greeting_turn.text == greeting("hi", "home")
        assert PERSONA.name("hi") in greeting_turn.text
        check_voice_pair(rig, voice=PERSONA.voice("hi"), language="hi")

        await rig.driver.user_says("पार्किंग कहाँ है")
        show = await _until(rig, "site.show")
        assert show["args"] == {"thing": "parking"}
        info = _results(llm, "clinic_info")[0]
        assert "basement" in info.lower()

        await rig.driver.user_says("दाँत निकलवाने के बाद खून आ रहा है")
        cb = await _until(rig, "callback.request")
        assert cb["args"]["callback_id"] == "CB-3107"
        assert cb["args"]["urgency"] == "urgent"
        assert cb["args"]["window"] == "within 30 minutes"
        assert "phone" not in cb["args"], "the page calls the number on record"
        assert "9886055102" not in json.dumps(llm.requests, ensure_ascii=False)
        # The clinical note reached the model before its answer.
        assert "This sounds clinical" in input_texts(llm.captured_inputs[-1])


async def test_amounts_are_said_the_way_the_voice_reads_them() -> None:
    """X8 over the wire: the model writes the screen's figures (a dashed range,
    "₹4.5k", "₹1.25 lakh") and the voice is given forms its text stage reads right
    (no ₹ with two decimals, no dash between amounts); a patient's "dedh hazaar"
    reaches the model in rupees. In Hindi a lakh amount is said the Hindi way."""
    llm = ScriptedOpenAI(
        {
            "Is a root canal with a crown under dedh hazaar?": reply(
                "No: a root canal is ₹6,500 to ₹12,000, and the crown is ₹8,000\u2013₹18,000. "
                "A take-home whitening kit is ₹4.5k; a full plan can reach ₹1.25 lakh."
            ),
            "पूरा कितना होगा?": reply("पूरा plan ₹1.25 लाख तक जा सकता है।"),
        }
    )
    async with demo("dental", llm) as rig:
        await rig.driver.start_session(init={"landing": "home", "lang": "en"})
        turn = await rig.driver.user_says("Is a root canal with a crown under dedh hazaar?")
        check_turn(rig, turn)
        said = " ".join(u.text for u in turn.units)
        assert "₹6,500 to ₹12,000" in said
        assert "₹8,000 to ₹18,000" in said and "\u2013" not in said
        assert "₹4,500" in said and "₹4.5k" not in said
        assert "one point two five lakh rupees" in said
        told = input_texts(llm.captured_inputs[-1])
        assert "'dedh hazaar' = 1500 rupees" in told

        await rig.driver.send_ui_event("language_requested", {"language": "hi", "by": "visitor"})
        await asyncio.sleep(0.2)
        turn = await rig.driver.user_says("पूरा कितना होगा?")
        said = " ".join(u.text for u in turn.units)
        assert "सवा लाख रुपये" in said and "₹1.25" not in said


async def test_the_toggle_moves_both_legs_mid_call() -> None:
    llm = ScriptedOpenAI({"hello": reply("नमस्ते!")})
    async with demo("dental", llm) as rig:
        await rig.driver.start_session(init={"landing": "home", "lang": "en"})
        await rig.driver.send_ui_event("language_requested", {"language": "hi", "by": "visitor"})
        await asyncio.sleep(0.2)
        last = _configs(rig)[-1]
        assert last.tts is not None and last.stt is not None
        assert last.tts.language == "hi" and last.stt.language == "hi"
        assert last.tts.voice == PERSONA.voice("hi")
        assert any(c.get("command") == "language_changed" for c in rig.driver.ui_commands)


async def test_the_page_schedule_is_laid_over_the_calendar() -> None:
    llm = ScriptedOpenAI({"hello": reply("Hi!")})
    async with demo("dental", llm) as rig:
        await rig.driver.start_session(init={"landing": "book", "lang": "en"})
        brain = rig.brain
        assert isinstance(brain, DentalBrain)
        await rig.driver.send_ui_event(
            "schedule_changed",
            {
                "appointments": [
                    {
                        "id": "DT-26001",
                        "patient_id": "P-1002",
                        "service": "rct",
                        "branch": RCT_SLOT.branch,
                        "date": RCT_SLOT.on.isoformat(),
                        "time": RCT_SLOT.time,
                        "duration_min": 60,
                        "dentist": "dr-kavitha",
                        "chair": RCT_SLOT.chair,
                    }
                ],
                "by": "visitor",
            },
        )
        await asyncio.sleep(0.1)
        assert brain.cal.slot_at(RCT, RCT_SLOT.on, RCT_SLOT.time, dentist_id="dr-kavitha") is None


# ─── Redial: a call outlives its socket ───────────────────────────────────────


def _redials(driver: VoqalizeDriver) -> list[bool | None]:
    return [
        r.config.redial.enabled
        for r in driver.requests
        if isinstance(r, ConfigureFrame) and r.config.redial is not None
    ]


def _driver_moves(driver: VoqalizeDriver, move: str) -> list[dict[str, Any]]:
    return [
        dict(c.get("payload") or {})
        for c in driver.ui_commands
        if c.get("command") == "stage_move" and (c.get("payload") or {}).get("move") == move
    ]


async def test_a_dropped_socket_rejoins_the_call_where_it_was() -> None:
    """Rohan verifies on /my-appointments, switches to Hindi, and a move of his
    cleaning is on screen waiting for his yes; then the brain's socket drops
    without a hang-up. Meera turns redial on; Voqalize dials again for the same
    session; the new socket's brain adopts the call (language, page, patient,
    the pending change, the call's calendar, the model's history), says no
    second greeting, and the yes on the new socket moves the cleaning."""
    scaling = cl.service("scaling")
    assert scaling is not None
    a = CAL.appts["DT-24063"]
    target_day, targets = CAL.next_days(
        scaling, dentist_id=a.dentist, start=a.on + timedelta(days=1), ignore=a.id
    )[0]
    target = targets[0]
    llm = ScriptedOpenAI(
        {
            "Move the cleaning": [
                reply_and_call(
                    "Let me put that on screen.",
                    "propose_change",
                    appointment_id="DT-24063",
                    action="reschedule",
                    date=target_day.isoformat(),
                    time=target.time,
                ),
                reply("It's free to move. Shall I go ahead?"),
            ],
            "Yes please": [reply_and_call("Moving it now.", "confirm_change")],
        }
    )
    build = build_for("dental")
    built: list[DentalBrain] = []

    def _build() -> Any:
        brain = build(llm)  # type: ignore[arg-type]
        built.append(brain)
        return brain

    keypair = generate_keypair()
    server = BrainServer(_build, host="127.0.0.1", port=0, public_keys=keypair.public_pem)
    port = await server.start()
    sid = "dental-redial-e2e"
    init = {"landing": "my-appointments", "lang": "en"}

    def driver() -> VoqalizeDriver:
        token = mint_voqalize_token(
            private_key_pem=keypair.private_pem,
            session_id=sid,
            agent_id="dental",
        )
        return VoqalizeDriver(
            DirectConnection(f"ws://127.0.0.1:{port}", sid, token=token),
            session_id=sid,
            default_timeout=10.0,
        )

    first, second = driver(), driver()
    try:
        await first.open()
        greeted = await first.start_session(init=init)
        assert greeted is not None and greeted.text == greeting("en", "my-appointments")
        assert _redials(first) == [True], "redial is turned on with the voice, before the greeting"
        await _typed_sign_in(first, "P-1001", "Rohan Mehta")
        await first.send_ui_event("language_requested", {"language": "hi", "by": "visitor"})
        await asyncio.sleep(0.1)
        await first.user_says("Move the cleaning")
        for _ in range(200):
            if _driver_moves(first, "appt.propose"):
                break
            await asyncio.sleep(0.02)
        propose = _driver_moves(first, "appt.propose")[0]
        await first.send_ui_event(
            "stage_result",
            {"call_ref": propose["call_ref"], "move": "appt.propose", "outcome": "applied"},
        )
        await asyncio.sleep(0.05)
        before = built[-1]
        assert before.pending is not None and before.pending.appt.id == "DT-24063"
        assert before.lang == "hi" and before.patient is not None
        cal = before.cal

        # The socket drops: no End, no close code a hang-up would send.
        await first.aclose()
        await asyncio.sleep(0.2)
        assert len(REJOIN) == 1, "the dropped call is held for a redial"

        # Voqalize redials: the same session id, the same init.
        await second.open()
        again = await second.start_session(init=init, greeting_timeout=0.5)
        after = built[-1]
        assert after is not before
        assert again is None, "a rejoined call is not greeted a second time"
        assert after.lang == "hi" and after.page == "my-appointments"
        assert after.patient is not None and after.patient.id == "P-1001"
        assert after.pending is not None and after.pending.appt.id == "DT-24063"
        assert after.cal is cal, "the call's own calendar came across"
        assert _redials(second) == [True]
        configs = [r.config for r in second.requests if isinstance(r, ConfigureFrame)]
        assert configs[0].tts is not None and configs[0].tts.language == "hi"
        assert configs[0].tts.voice == PERSONA.voice("hi"), "the Hindi voice, as the call had"

        await second.user_says("Yes please")
        for _ in range(200):
            if _driver_moves(second, "appt.apply"):
                break
            await asyncio.sleep(0.02)
        apply = _driver_moves(second, "appt.apply")
        assert apply and apply[0]["args"]["action"] == "reschedule", (
            "the yes landed on the new socket"
        )
        moved = after.cal.appts["DT-24063"]
        assert moved.on == target_day and cl.hhmm(moved.start) == target.time
        seen = input_texts(llm.captured_inputs[-1])
        assert "Move the cleaning" in seen, "the model's history came across"
        greetings = (greeting("en", "my-appointments"), greeting("hi", "my-appointments"))
        assert sum(seen.count(g) for g in greetings) == 1, "one greeting in the history"
    finally:
        await second.aclose()
        await server.aclose()


async def test_no_redial_is_asked_of_a_voqalize_that_does_not_offer_it() -> None:
    """``configure`` raises for redial without the capability: Meera asks only
    where it is offered, and the call starts and runs the same either way."""
    llm = ScriptedOpenAI({"hello": reply("Hi!")})
    async with demo("dental", llm) as rig:
        rig.driver.capabilities.discard(Capability.REDIAL)
        greeted = await rig.driver.start_session(init={"landing": "home", "lang": "en"})
        check_greeting(rig, greeted)
        assert _redials(rig.driver) == []
        check_voice_pair(rig, voice=PERSONA.voice("en"), language="en")
        turn = await rig.driver.user_says("hello")
        assert turn.units


def test_a_held_call_expires_and_a_fresh_process_starts_over() -> None:
    """A redial reaching a process that never held the call (a deploy) finds
    nothing and starts fresh; a live call is held however long it runs; a
    dropped one (a hang-up looks the same to the brain) is let go two minutes
    after its socket closed."""
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


# ─── Pure rules ───────────────────────────────────────────────────────────────


def test_yes_and_clinical_words() -> None:
    assert affirmed("Yes, go ahead")
    assert affirmed("हाँ, कर दीजिए")
    assert affirmed("haan theek hai")
    assert not affirmed("no, wait")
    assert not affirmed("What does it cost?")
    assert clinical("Which painkiller should I take?")
    assert clinical("मुझे बुखार और सूजन है")
    assert not clinical("Where do I park?")


def test_slot_fixtures_and_stage_files_are_current(tmp_path: Path) -> None:
    """The page's slot fixtures and the generated Stage files match their sources."""
    root = Path(cl.__file__).resolve().parent.parent
    out = tmp_path / "fixtures.json"
    cl.write_fixtures(out)
    assert out.read_text() == (root / "data" / "slot_fixtures.json").read_text(), (
        "data/slot_fixtures.json is stale: run `uv run python dental/backend/clinic.py` from demos/"
    )
    source = "dental/frontend/src/stage/scene.json"
    py, ts = "dental/backend/stage_gen.py", "dental/frontend/src/stage/scene.gen.ts"
    command = f"voqalize stage gen {source} --py {py} --ts {ts}"
    spec = load_spec(root / "frontend/src/stage/scene.json")
    demos = root.parent
    assert (demos / py).read_text() == render_python(spec, source=source, command=command)
    assert (demos / ts).read_text() == render_typescript(spec, source=source, command=command)


def test_every_offered_language_has_a_voice_greeting_and_lines() -> None:
    from voqalize_demos._loaded.dental.prompt import GREETINGS, LINES

    for code in PERSONA.codes:
        assert PERSONA.voice(code)
        assert set(GREETINGS[code]) == {
            "home",
            "book",
            "my-appointments",
            "my-appointments-signed-in",
        }
        assert set(LINES[code]) == set(LINES["en"])
