"""Paynora's marketing site, end to end: the real brain on a real socket, only the model scripted.

One agent, three jobs by landing page. On ``/`` the sales rep fills the lead
card field by field and marks the modules that fit; on ``/pricing`` it sets the
calculator and states the per-employee maths from the same pricing rule the
page runs; on ``/book-demo`` it picks a free slot on the sales calendar, fills
the form and confirms only after a spoken yes. The character, voice and
languages come from ``demos/payroll_site/persona.json``.

Run: ``cd demos && uv run pytest tests/test_payroll_site_e2e.py``
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedOpenAI, call, reply, reply_and_call, tool_results_of

from ._harness import DemoRig, check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.payroll_site import calendar_rules as cal  # noqa: E402
from voqalize_demos._loaded.payroll_site import pricing  # noqa: E402
from voqalize_demos._loaded.payroll_site.brain import PaynoraSiteBrain  # noqa: E402
from voqalize_demos._loaded.payroll_site.data import inr  # noqa: E402
from voqalize_demos._loaded.payroll_site.lines import GREETING  # noqa: E402
from voqalize_demos._loaded.payroll_site.persona import PERSONA  # noqa: E402

DEMOS = Path(__file__).resolve().parents[1]
SITE = DEMOS / "payroll_site"


def _moves(rig: DemoRig, move: str | None = None) -> list[dict[str, Any]]:
    out = [
        dict(c.get("payload") or {})
        for c in rig.driver.ui_commands
        if c.get("command") == "stage_move"
    ]
    return [m for m in out if move is None or m["move"] == move]


def _cues(rig: DemoRig) -> list[dict[str, Any]]:
    return [
        dict(c.get("payload") or {})
        for c in rig.driver.ui_commands
        if c.get("command") == "stage_cue"
    ]


async def _answer_all(rig: DemoRig, rounds: int = 20) -> None:
    """The page answers every move it was sent with ``applied``, one at a time,
    as it would: each answer releases the next queued move."""
    answered: set[str] = set()
    for _ in range(rounds):
        pending = [m for m in _moves(rig) if m["call_ref"] not in answered]
        if not pending:
            return
        for m in pending:
            answered.add(m["call_ref"])
            await rig.driver.send_ui_event(
                "stage_result",
                {
                    "call_ref": m["call_ref"],
                    "move": m["move"],
                    "outcome": "applied",
                    "detail": "ok",
                },
            )
        await asyncio.sleep(0.1)


def _brain(rig: DemoRig) -> PaynoraSiteBrain:
    brain = rig.brain
    assert isinstance(brain, PaynoraSiteBrain)
    return brain


# ─── Data ─────────────────────────────────────────────────────────────────────


def test_product_json_is_the_app_s_byte_for_byte() -> None:
    """One product, two demos: the site's copy may never drift from the app's."""
    site = (SITE / "data" / "product.json").read_bytes()
    app = (DEMOS / "payroll_app" / "data" / "product.json").read_bytes()
    assert site == app


def test_the_python_pricing_matches_the_shared_cases() -> None:
    """The same fixture the page's twin (frontend/src/lib/pricing.ts) is held to."""
    cases = json.loads((SITE / "content" / "pricing_cases.json").read_text())["cases"]
    for c in cases:
        q = pricing.quote(**c["input"]).as_dict()
        assert {k: q[k] for k in c["expect"]} == c["expect"], c["input"]
        assert [line["key"] for line in q["lines"]] == c["lines"]
    q = pricing.quote(56, ["reimbursements"])
    assert q.plan == "growth" and q.monthly == 6664 and not q.minimum_applies


def test_the_python_calendar_matches_the_shared_cases() -> None:
    from datetime import date

    data = json.loads((SITE / "content" / "calendar_cases.json").read_text())
    for c in data["cases"]:
        days = cal.business_days(date.fromisoformat(c["today"]))
        assert [d.isoformat() for d in days] == c["days"]
        for day, slots in c["slots"].items():
            got = [[s.time, s.rep, s.taken] for s in cal.slots_on(date.fromisoformat(day))]
            assert got == slots
    ex = data["reference_example"]
    slot = cal.parse_slot(ex["slot"])
    assert slot is not None and cal.reference(slot) == ex["reference"]


# ─── Persona and languages ────────────────────────────────────────────────────


async def test_the_home_page_greets_as_the_sales_rep_in_the_persona_voice() -> None:
    async with demo("payroll_site", ScriptedOpenAI()) as rig:
        greeting = await rig.driver.start_session(
            init={"page": "/demos/payroll_site/", "lang": "en"}
        )
        check_greeting(rig, greeting)
        check_voice_pair(rig, voice=PERSONA.voices["en"], language="en")
        assert greeting is not None
        assert greeting.text == GREETING["sdr"]["en"].format(name=PERSONA.name)
        assert PERSONA.name in greeting.text
        assert _brain(rig).job == "sdr"


async def test_hindi_from_the_toggle_moves_both_legs_and_the_greeting() -> None:
    async with demo("payroll_site", ScriptedOpenAI()) as rig:
        greeting = await rig.driver.start_session(init={"page": "/pricing", "lang": "hi"})
        check_greeting(rig, greeting)
        check_voice_pair(rig, voice=PERSONA.voices["hi"], language="hi")
        assert greeting is not None and "नमस्ते" in greeting.text
        assert _brain(rig).job == "pricing"
        assert "[Language: Hindi]" in _brain(rig).screen_now()


async def test_hindi_asked_mid_call_moves_both_legs_and_the_toggle() -> None:
    llm = ScriptedOpenAI(
        {
            "Hindi mein baat karein?": reply_and_call(
                "ज़रूर, अब हिंदी में बात करते हैं।", "set_language", language="hindi"
            )
        }
    )
    async with demo("payroll_site", llm) as rig:
        await rig.driver.start_session(init={"page": "/"})
        check_turn(rig, await rig.driver.user_says("Hindi mein baat karein?"))
        await asyncio.sleep(0.1)
        check_voice_pair(rig, voice=PERSONA.voices["hi"], language="hi")
        assert rig.command("language_changed") == {"language": "hi"}


async def test_the_toggle_pressed_mid_call_switches_and_says_so() -> None:
    async with demo("payroll_site", ScriptedOpenAI()) as rig:
        await rig.driver.start_session(init={"page": "/", "lang": "en"})
        await rig.driver.send_ui_event("language_requested", {"language": "hi"})
        await asyncio.sleep(0.1)
        check_voice_pair(rig, voice=PERSONA.voices["hi"], language="hi")
        turn = await rig.driver.user_idle()
        assert "हिंदी" in turn.text


# ─── The sales rep on / ───────────────────────────────────────────────────────

_INTRO = "I'm Meghna from Banyan and Bay, we're 56 people in Karnataka and Maharashtra."
_PAINS = "We run it on spreadsheets and proof season kills us every February."


def _sdr() -> ScriptedOpenAI:
    return ScriptedOpenAI(
        {
            _INTRO: [
                call(
                    "update_lead",
                    name="Meghna",
                    company="Banyan & Bay Foods",
                    headcount=56,
                    states=["Karnataka", "Maharashtra"],
                ),
                reply("Thanks, Meghna. How do you run payroll today?"),
            ],
            _PAINS: [
                call("update_lead", current_tool="spreadsheets", pains=["tax_proofs"]),
                reply(
                    "{module: declarations} Proofs come in through the portal and you verify "
                    "each line. Growth fits a team your size."
                ),
            ],
            "It's meghna at banyanbay dot in.": [
                call("update_lead", email="meghna@banyanbay.in"),
                reply("That's meghna at banyanbay dot in, right?"),
            ],
            "Yes, that's right.": reply_and_call(
                "Done.", "update_lead", email="meghna@banyanbay.in", email_confirmed=True
            ),
        }
    )


async def test_the_sales_rep_fills_the_lead_card_and_marks_the_modules() -> None:
    llm = _sdr()
    async with demo("payroll_site", llm) as rig:
        await rig.driver.start_session(init={"page": "/", "lang": "en"})

        check_turn(rig, await rig.driver.user_says(_INTRO))
        await _answer_all(rig)
        fills = [(m["args"]["field"], m["args"]) for m in _moves(rig, "lead.fill")]
        # Field by field, in the card's order, each its own move.
        assert [f for f, _ in fills] == [
            "company",
            "name",
            "headcount",
            "states",
            "recommended_plan",
        ]
        assert fills[2][1]["value"] == "56"
        assert fills[3][1]["items"] == ["Karnataka", "Maharashtra"]
        # 56 is above Starter's 50: the rule picks Growth.
        assert fills[4][1]["value"] == "growth"
        (said,) = tool_results_of(llm.captured_inputs[-1], "update_lead")
        assert "Suggested plan: Growth because 56 employees is above the Starter limit" in said
        assert "Still empty" in said

        turn = await rig.driver.user_says(_PAINS)
        check_turn(rig, turn)
        await _answer_all(rig)
        fills = [m["args"]["field"] for m in _moves(rig, "lead.fill")][5:]
        # Proofs need Growth too; the plan stays, so it is not filled again.
        assert fills == ["current_tool", "pains"]
        (marked,) = _moves(rig, "modules.highlight")
        assert marked["args"] == {"ids": ["tax", "declarations"]}
        said = tool_results_of(llm.captured_inputs[-1], "update_lead")[-1]
        assert "Investment declarations and proofs needs Growth" in said
        assert "Suggested plan: Growth" in said
        (cue,) = _cues(rig)
        assert cue["move"] == "modules.show" and cue["args"] == ["declarations"]
        assert "{" not in turn.text
        assert _brain(rig).lead["recommended_plan"] == "growth"

        # The email goes on the card only once read back and confirmed.
        check_turn(rig, await rig.driver.user_says("It's meghna at banyanbay dot in."))
        assert "email" not in [m["args"]["field"] for m in _moves(rig, "lead.fill")]
        said = tool_results_of(llm.captured_inputs[-1], "update_lead")[-1]
        assert "read meghna@banyanbay.in back" in said
        check_turn(rig, await rig.driver.user_says("Yes, that's right."))
        await _answer_all(rig)
        email = [m["args"] for m in _moves(rig, "lead.fill") if m["args"]["field"] == "email"]
        assert email == [{"field": "email", "value": "meghna@banyanbay.in"}]


async def test_the_visitor_s_own_card_edits_reach_the_brain_without_the_email() -> None:
    llm = ScriptedOpenAI({"What would you suggest?": reply("Growth, for proofs.")})
    async with demo("payroll_site", llm) as rig:
        await rig.driver.start_session(init={"page": "/"})
        await rig.driver.send_ui_event(
            "stage_event",
            {
                "name": "lead.changed",
                "by": "visitor",
                "data": {
                    "headcount": 120,
                    "pains": ["tax_proofs"],
                    "has_email": True,
                    "field": "pains",
                },
            },
        )
        await asyncio.sleep(0.1)
        assert _brain(rig).lead["headcount"] == 120
        check_turn(rig, await rig.driver.user_says("What would you suggest?"))
        sent = json.dumps(llm.captured_inputs[-1], ensure_ascii=False)
        assert "The visitor changed the lead card" in sent
        assert "headcount 120" in sent and "email given" in sent


# ─── The pricing explainer on /pricing ────────────────────────────────────────

_PRICE_ASK = "We're 56 people and we need reimbursements."


async def test_pricing_sets_the_calculator_and_states_the_maths() -> None:
    llm = ScriptedOpenAI(
        {
            _PRICE_ASK: [
                call("price_plan", headcount=56, modules=["reimbursements"]),
                reply(
                    "{line: base} That's Growth: 56 times 119 is 6,664 rupees a month. "
                    "{line: minimum} You're above the 5,999 minimum, so it doesn't apply. "
                    "{line: gst} GST takes it to 7,864."
                ),
            ],
            "And if we pay annually, with the filing service?": [
                call(
                    "price_plan",
                    headcount=56,
                    modules=["reimbursements"],
                    billing="annual",
                    filing=True,
                ),
                reply("{line: discount} Annual takes fifteen percent off and waives setup."),
            ],
        }
    )
    async with demo("payroll_site", llm) as rig:
        await rig.driver.start_session(init={"page": "/pricing", "lang": "en"})
        assert _brain(rig).job == "pricing"
        turn = await rig.driver.user_says(_PRICE_ASK)
        check_turn(rig, turn)
        (move,) = _moves(rig, "pricing.set")
        assert move["args"] == {
            "headcount": 56,
            "modules": ["reimbursements"],
            "billing": "monthly",
            "filing": False,
        }
        (said,) = tool_results_of(llm.captured_inputs[-1], "price_plan")
        assert said.startswith("Plan: Growth (Reimbursements needs Growth or above)")
        assert f"56 employees × {inr(119)} = {inr(6664)}" in said  # noqa: RUF001
        assert "not applied" in said
        assert f"GST 18% = {inr(1200)}" in said and f"= {inr(7864)}" in said
        assert f"One-time setup fee = {inr(15000)}" in said
        assert [c["args"] for c in _cues(rig)] == [["base"], ["minimum"], ["gst"]]
        assert "{" not in turn.text
        await _answer_all(rig)

        check_turn(
            rig, await rig.driver.user_says("And if we pay annually, with the filing service?")
        )
        move = _moves(rig, "pricing.set")[-1]
        assert move["args"]["billing"] == "annual" and move["args"]["filing"] is True
        q = pricing.quote(56, ["reimbursements"], "annual", True)
        said = tool_results_of(llm.captured_inputs[-1], "price_plan")[-1]
        assert f"Filing service, 56 × {inr(20)} = {inr(1120)}" in said  # noqa: RUF001
        assert f"Annual billing, 15% off = {inr(-q.discount)}" in said
        assert "waived on annual billing" in said
        assert f"Billed yearly, with GST = {inr(q.annual_total)}" in said


async def test_pricing_above_the_largest_plan_is_a_custom_quote() -> None:
    llm = ScriptedOpenAI({"We have 1,200 people.": call("price_plan", headcount=1200)})
    async with demo("payroll_site", llm) as rig:
        await rig.driver.start_session(init={"page": "/pricing"})
        check_turn(rig, await rig.driver.user_says("We have 1,200 people."))
        said = tool_results_of(llm.captured_inputs[-1], "price_plan")[-1]
        assert "custom price" in said


# ─── The demo booker on /book-demo ────────────────────────────────────────────


def _a_free_slot() -> cal.Slot:
    for d in cal.business_days(cal.today_ist()):
        free = [s for s in cal.slots_on(d) if not s.taken]
        if free:
            return free[0]
    raise AssertionError("the calendar has no free slot")


async def test_the_booker_picks_a_slot_and_confirms_only_after_yes() -> None:
    slot = _a_free_slot()
    day = slot.day.isoformat()
    llm = ScriptedOpenAI(
        {
            f"Can we do {day}?": [
                call("demo_slots", day=day),
                reply("There's a slot then."),
            ],
            "That one please. I'm Ravi from Kestrel, ravi@kestrel.example, yes that's right.": [
                call(
                    "hold_slot",
                    slot_id=slot.id,
                    name="Ravi",
                    company="Kestrel Health Labs",
                    email="ravi@kestrel.example",
                    email_confirmed=True,
                    headcount=410,
                ),
                reply("Shall I confirm it?"),
            ],
        }
    )
    async with demo("payroll_site", llm) as rig:
        greeting = await rig.driver.start_session(init={"page": "/book-demo", "lang": "en"})
        assert greeting is not None and "30-minute demo" in greeting.text
        assert _brain(rig).job == "booker"

        check_turn(rig, await rig.driver.user_says(f"Can we do {day}?"))
        (shown,) = _moves(rig, "calendar.show")
        assert shown["args"] == {"day": day}
        (said,) = tool_results_of(llm.captured_inputs[-1], "demo_slots")
        assert slot.id in said and slot.rep_name in said
        taken = [s.id for s in cal.slots_on(slot.day) if s.taken]
        assert not any(t in said for t in taken), "a taken slot was offered"
        await _answer_all(rig)

        check_turn(
            rig,
            await rig.driver.user_says(
                "That one please. I'm Ravi from Kestrel, ravi@kestrel.example, yes that's right."
            ),
        )
        await _answer_all(rig)
        (pick,) = _moves(rig, "booking.pick")
        assert pick["args"] == {"slot_id": slot.id}
        fills = [(m["args"]["field"], m["args"]["value"]) for m in _moves(rig, "booking.fill")]
        assert fills == [
            ("name", "Ravi"),
            ("company", "Kestrel Health Labs"),
            ("headcount", "410"),
            ("topic", "walkthrough"),
            ("email", "ravi@kestrel.example"),
        ]
        # Held, not booked: nothing confirmed until the visitor's yes.
        assert _moves(rig, "booking.confirm") == []
        assert _brain(rig).held is not None

        turn = await rig.driver.user_says("Yes, go ahead.")
        check_turn(rig, turn)
        assert "Confirming it now" in turn.text
        (confirm,) = _moves(rig, "booking.confirm")
        await rig.driver.send_ui_event(
            "stage_result",
            {"call_ref": confirm["call_ref"], "move": "booking.confirm", "outcome": "applied"},
        )
        await asyncio.sleep(0.1)
        said = await rig.driver.user_idle()
        assert cal.reference(slot) in said.text
        assert slot.rep_name.split()[0] in said.text
        assert slot.id in _brain(rig).booked


async def test_the_booker_does_not_confirm_on_a_no() -> None:
    slot = _a_free_slot()
    llm = ScriptedOpenAI(
        {
            "Book it for me.": call(
                "hold_slot",
                slot_id=slot.id,
                name="Asha",
                company="Inkwell Learning",
                email="asha@inkwell.example",
                email_confirmed=True,
            ),
            "No, wait.": reply("No problem, nothing is booked."),
            "Just confirm it.": call("confirm_booking", visitor_said_yes=False),
        }
    )
    async with demo("payroll_site", llm) as rig:
        await rig.driver.start_session(init={"page": "/book-demo"})
        check_turn(rig, await rig.driver.user_says("Book it for me."))
        check_turn(rig, await rig.driver.user_says("No, wait."))
        assert _moves(rig, "booking.confirm") == []
        assert _brain(rig).held is None


async def test_a_taken_slot_is_refused() -> None:
    taken = next(s for d in cal.business_days(cal.today_ist()) for s in cal.slots_on(d) if s.taken)
    llm = ScriptedOpenAI(
        {"Hold that.": call("hold_slot", slot_id=taken.id, name="Asha", company="Inkwell Learning")}
    )
    async with demo("payroll_site", llm) as rig:
        await rig.driver.start_session(init={"page": "/book-demo"})
        check_turn(rig, await rig.driver.user_says("Hold that."))
        said = tool_results_of(llm.captured_inputs[-1], "hold_slot")[-1]
        assert "is taken" in said
        assert _moves(rig, "booking.pick") == []


# ─── Following the visitor ────────────────────────────────────────────────────


async def test_the_brain_switches_job_when_the_visitor_moves() -> None:
    llm = ScriptedOpenAI({"How much would it be?": reply("Tell me your headcount.")})
    async with demo("payroll_site", llm) as rig:
        await rig.driver.start_session(init={"page": "/"})
        assert _brain(rig).job == "sdr"
        await rig.driver.send_ui_event(
            "stage_event",
            {
                "name": "screen.viewed",
                "by": "visitor",
                "data": {"path": "/demos/payroll_site/pricing", "title": "Pricing"},
            },
        )
        await asyncio.sleep(0.1)
        assert _brain(rig).job == "pricing"
        check_turn(rig, await rig.driver.user_says("How much would it be?"))
        sent = json.dumps(llm.captured_inputs[-1], ensure_ascii=False)
        assert "They are now on the pricing page" in sent
        assert "Your job: pricing" in sent


async def test_open_page_sends_the_navigate_move() -> None:
    llm = ScriptedOpenAI(
        {"Show me the pricing.": reply_and_call("Here's pricing.", "open_page", page="/pricing")}
    )
    async with demo("payroll_site", llm) as rig:
        await rig.driver.start_session(init={"page": "/"})
        check_turn(rig, await rig.driver.user_says("Show me the pricing."))
        assert _moves(rig, "site.go")[0]["args"] == {"path": "/pricing"}
