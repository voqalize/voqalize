"""Dantika Dental's front desk, end to end over the wire: no network, no LLM key.

The real ``DentalBrain`` (its prompt, tools, the clinic's authored data and the
slot engine) on a real ``brain_server`` socket, driven by the conformance
``VoqalizeDriver``, with only the model scripted (``ScriptedOpenAI``, flat tool
arguments). The clock is fixed to a Wednesday morning in Bengaluru, so the slots
the script holds are the ones the engine computes.

One storyline per landing page:

- ``/book``: a root canal, from the slots on the calendar to a held slot, the
  phone and its code, a refused confirm (no yes yet) and the booking with its
  two later sittings pencilled in.
- ``/my-appointments``: Rohan verifies, hears his appointments, moves his
  cleaning to a free slot and says yes; the change goes to the page.
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

from ._harness import DemoRig, _configs, check_greeting, check_voice_pair, demo

discover()

from voqalize_demos._loaded.dental import clinic as cl  # noqa: E402
from voqalize_demos._loaded.dental.brain import (  # noqa: E402
    REJOIN,
    DentalBrain,
    affirmed,
    clinical,
)
from voqalize_demos._loaded.dental.persona import PERSONA  # noqa: E402
from voqalize_demos._loaded.dental.prompt import greeting  # noqa: E402
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
                reply("It's held. What's your mobile number?"),
            ],
            "98450 31726": [
                reply_and_call("Sending a code.", "send_code", phone="98450 31726"),
                reply("Please read me the code."),
            ],
            "It's 4821": [
                reply_and_call("Checking.", "verify_code", code="4821"),
                reply("Thanks Rohan. Shall I confirm it?"),
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
        assert "not verified" in _results(llm, "hold_slot")[0]
        await _answer(rig, hold)

        await rig.driver.user_says("98450 31726")
        phone = await _until(rig, "patient.phone")
        assert phone["args"] == {"phone": "9845031726"}
        await _answer(rig, phone)

        await rig.driver.user_says("It's 4821")
        otp = await _until(rig, "patient.otp")
        assert otp["args"] == {"code": "4821"}
        verified = _results(llm, "verify_code")[0]
        assert "Rohan Mehta" in verified and "DT-24051" in verified
        await _answer(rig, otp)

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


async def test_a_refused_confirm_is_undone_and_said() -> None:
    llm = _book_script()
    async with demo("dental", llm) as rig:
        await rig.driver.start_session(init={"landing": "book", "lang": "en"})
        brain = rig.brain
        assert isinstance(brain, DentalBrain)
        for text in ("I need a root canal", "The first one please", "98450 31726", "It's 4821"):
            await rig.driver.user_says(text)
        await rig.driver.user_says("Yes, go ahead")
        confirm = await _until(rig, "book.confirm")
        assert "DT-24117" in brain.cal.appts
        await _answer(rig, confirm, outcome="refused", detail="that slot was just taken on screen")
        assert "DT-24117" not in brain.cal.appts
        assert brain._say_next is not None and "just taken" in brain._say_next


async def test_a_cbct_without_referral_or_consult_is_refused() -> None:
    llm = ScriptedOpenAI(
        {
            "99000 48213": [call("send_code", phone="9900048213"), reply("Code?")],
            "4821": [call("verify_code", code="4821"), reply("Thanks Ishita.")],
            "I want a CBCT scan": [
                reply_and_call("Checking.", "find_slots", service="cbct", branch="indiranagar"),
                reply("A CBCT needs a consultation first."),
            ],
        }
    )
    async with demo("dental", llm) as rig:
        await rig.driver.start_session(init={"landing": "book", "lang": "en"})
        for text in ("99000 48213", "4821", "I want a CBCT scan"):
            await rig.driver.user_says(text)
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
            "98450 31726": [call("send_code", phone="9845031726"), reply("Code please.")],
            "4821": [call("verify_code", code="4821"), reply("Thanks Rohan.")],
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
        for text in ("98450 31726", "4821", "What do I have coming up"):
            await rig.driver.user_says(text)
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
            "98450 31726": [call("send_code", phone="9845031726"), reply("Code please.")],
            "4821": [call("verify_code", code="4821"), reply("Thanks Rohan.")],
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
        for text in ("98450 31726", "4821", "Move my root canal to three weeks later"):
            await rig.driver.user_says(text)
        assert "can only move to between" in _results(llm, "propose_change")[0]
        assert _moves(rig, "appt.propose") == []


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
                    phone="9886055102",
                ),
            ],
        }
    )
    async with demo("dental", llm) as rig:
        greeting_turn = await rig.driver.start_session(init={"landing": "home", "lang": "hi"})
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
        # The clinical note reached the model before its answer.
        assert "This sounds clinical" in input_texts(llm.captured_inputs[-1])


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
            "98450 31726": [call("send_code", phone="9845031726"), reply("Code please.")],
            "4821": [call("verify_code", code="4821"), reply("Thanks Rohan.")],
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
            tenant_id="demo",
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
        for text in ("98450 31726", "4821"):
            await first.user_says(text)
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
        assert set(GREETINGS[code]) == {"home", "book", "my-appointments"}
        assert set(LINES[code]) == set(LINES["en"])
