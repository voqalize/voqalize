"""Paynora app (payroll_app): the brain over the real wire, model scripted.

One brain, three jobs by landing: the onboarding guide on ``/welcome`` fills the
setup wizard and runs a test payroll equal to the February draft; in-app support
on ``/`` explains Ravi Kumar's lower January pay with the data's numbers,
approves Asha Chavan's leave and fixes Imran Qureshi's claim after a spoken yes,
and hands off with a written ticket; the feature coach compares Kavitha Menon's
regimes slab by slab and switches her after a yes. Plus the Hindi init path,
the mid-call toggle, the Stage spec being current, and the data files being what
``build_data.py`` writes now.

The character's name, voice and languages are read from ``persona.json``, as
the brain reads them.

Run: ``cd demos && uv run pytest tests/test_payroll_app_e2e.py``
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import json
import re
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from voqalize_demos.discovery import build_for, discover
from voqalize_demos.testing import ScriptedOpenAI, reply, reply_and_call, tool_results

from voqalize.conformance import (
    BrainServer,
    DirectConnection,
    VoqalizeDriver,
    generate_keypair,
    mint_voqalize_token,
)
from voqalize.sdk import Brain
from voqalize.sdk.stage import load_spec
from voqalize.sdk.stage.check import check_spec
from voqalize.sdk.stage.gen import render_python, render_typescript
from voqalize.sdk.wire import Capability, ConfigureFrame

from ._harness import DemoRig, check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.payroll_app import books as books_mod  # noqa: E402
from voqalize_demos._loaded.payroll_app import brain as brain_mod  # noqa: E402
from voqalize_demos._loaded.payroll_app.brain import REJOIN, PaynoraBrain  # noqa: E402
from voqalize_demos._loaded.payroll_app.prompt import JOB_NOTE  # noqa: E402
from voqalize_demos._loaded.payroll_app.rejoin import KEEP_AFTER_DROP_S, Rejoin  # noqa: E402

DEMOS = Path(__file__).resolve().parents[1]
APP = DEMOS / "payroll_app"
PERSONA = json.loads((APP / "persona.json").read_text())
NAME = PERSONA["display_name"]
COMPANY = json.loads((APP / "data" / "company.json").read_text())
FEB = next(r for r in COMPANY["payroll_runs"] if r["id"] == "PR-2026-02")
inr = books_mod.inr


@pytest.fixture(autouse=True)
def _no_call_carried_between_tests() -> Iterator[None]:
    """Every test here opens the same session id, and a dropped call is held for
    a redial to rejoin (CONTRACT.md, redial): clear the store around each test,
    so no test rejoins the one before it. Real session ids never repeat."""
    REJOIN.clear()
    yield
    REJOIN.clear()


def _moves(rig: DemoRig) -> list[dict[str, Any]]:
    return [dict(c["payload"]) for c in rig.driver.ui_commands if c.get("command") == "stage_move"]


async def _answer(rig: DemoRig, moves: list[dict[str, Any]], detail: str = "") -> None:
    for m in moves:
        await rig.driver.send_ui_event(
            "stage_result",
            {"call_ref": m["call_ref"], "move": m["move"], "outcome": "applied", "detail": detail},
        )
    await asyncio.sleep(0.1)


async def _yes(rig: DemoRig, text: str, move: str, detail: str = "") -> Any:
    """Say a yes and play the page: answer the confirmed move the moment it is
    sent, as the page does about a second later, so the turn's one line is the
    outcome (round 1, A3)."""

    async def page() -> None:
        for _ in range(200):
            sent = [m for m in _moves(rig) if m["move"] == move]
            if sent:
                await _answer(rig, sent[-1:], detail)
                return
            await asyncio.sleep(0.01)

    task = asyncio.create_task(page())
    turn = await rig.driver.user_says(text)
    await task
    return turn


def _brain(rig: DemoRig) -> PaynoraBrain:
    brain = rig.brain
    assert isinstance(brain, PaynoraBrain)
    return brain


# ─── Greeting, voice, language ────────────────────────────────────────────────


async def test_each_landing_greets_for_its_job_with_the_persona_voice() -> None:
    for landing, word in (
        ("/welcome", "setup"),
        ("/", "payslip"),
        ("/help", "payslip"),
        ("/tax", "screen"),
    ):
        REJOIN.clear()  # one session id for each landing: none rejoins the last
        async with demo("payroll_app", ScriptedOpenAI()) as rig:
            greeting = await rig.driver.start_session(init={"landing": landing, "lang": "en"})
            check_greeting(rig, greeting)
            assert greeting is not None and NAME in greeting.text and word in greeting.text
            check_voice_pair(rig, voice=PERSONA["voices"]["en"], language="en")


async def test_hindi_from_the_toggle_configures_both_legs_and_greets_in_hindi() -> None:
    async with demo("payroll_app", ScriptedOpenAI()) as rig:
        greeting = await rig.driver.start_session(init={"landing": "/", "lang": "hi"})
        check_greeting(rig, greeting)
        assert greeting is not None and "नमस्ते" in greeting.text and NAME in greeting.text
        check_voice_pair(rig, voice=PERSONA["voices"]["hi"], language="hi")


async def test_the_toggle_switches_mid_call_and_says_so() -> None:
    async with demo("payroll_app", ScriptedOpenAI()) as rig:
        await rig.driver.start_session(init={"landing": "/", "lang": "en"})
        await rig.driver.send_ui_event("language_requested", {"language": "hi", "by": "visitor"})
        await asyncio.sleep(0.1)
        check_voice_pair(rig, voice=PERSONA["voices"]["hi"], language="hi")
        assert rig.command("language_changed") == {"language": "hi"}
        said = await rig.driver.user_idle()
        assert said.text.startswith("ज़रूर")


async def test_hindi_heard_mid_call_moves_both_legs() -> None:
    llm = ScriptedOpenAI({"Hindi mein baat karein?": reply("जी, अब हिंदी में बात करते हैं।")})
    async with demo("payroll_app", llm) as rig:
        await rig.driver.start_session(init={"landing": "/", "lang": "en"})
        check_turn(rig, await rig.driver.user_says("Hindi mein baat karein?"))
        check_voice_pair(rig, voice=PERSONA["voices"]["hi"], language="hi")
        assert rig.command("language_changed") == {"language": "hi"}


# ─── Onboarding guide ─────────────────────────────────────────────────────────


def _onboarding_llm() -> ScriptedOpenAI:
    return ScriptedOpenAI(
        {
            "Yes, let's begin.": [
                reply_and_call(
                    "Filling in your company details now.", "setup_step", step="company"
                ),
                reply("Those are in from your signup. Shall we do the pay structure next?"),
            ],
            "Looks right. Next.": [
                reply_and_call("Here's the pay structure.", "setup_step", step="structure"),
                reply(
                    "How would you like basic and HRA set, or shall I put in what most "
                    "companies use?"
                ),
            ],
            "Use what most companies use.": [
                reply_and_call(
                    "Putting those in.", "setup_fill", step="structure", rest="defaults"
                ),
                reply("They're in, and you can change any of them. Import employees next?"),
            ],
            "Make basic 45 percent.": [
                reply_and_call(
                    "Changing basic.",
                    "setup_fill",
                    step="structure",
                    values=[{"field": "basic_pct", "value": "45"}],
                ),
                reply("Basic is now 45% of CTC."),
            ],
            "Go on, import them.": [
                reply_and_call("Here's the import step.", "setup_step", step="import"),
                reply(
                    "{show: Download sample file} You can download the sample file, then "
                    "{show: Import file} click Import file and choose it."
                ),
            ],
            "[She imported her employee file herself": reply(
                "{show: Validation summary} All 56 rows came in clean. Leave policy next?"
            ),
            "Yes, the leave policy.": [
                reply_and_call("Here's the leave policy.", "setup_step", step="leave"),
                reply("What would you like, or shall I use the common policy?"),
            ],
            "The common one is fine.": [
                reply_and_call("Putting it in.", "setup_fill", step="leave", rest="defaults"),
                reply("That's in. Shall I run a test payroll?"),
            ],
            "Run the test payroll.": [
                reply_and_call("Running February as a test.", "setup_step", step="test_run"),
                reply("The test matches your February draft."),
            ],
        }
    )


def _fills(rig: DemoRig, since: int = 0) -> dict[str, str]:
    return {
        m["args"]["field"]: m["args"]["value"]
        for m in _moves(rig)[since:]
        if m["move"] == "setup.fill"
    }


async def test_onboarding_asks_each_step_and_only_the_admin_imports() -> None:
    """Round 1, A1: only the company details come from signup; the structure
    and leave policy are asked or taken from the common defaults on her word;
    she imports the file herself; the test payroll equals the draft."""
    llm = _onboarding_llm()
    async with demo("payroll_app", llm) as rig:
        greeting = await rig.driver.start_session(init={"landing": "/welcome", "lang": "en"})
        assert greeting is not None and "setup" in greeting.text
        check_turn(rig, await rig.driver.user_says("Yes, let's begin."))
        moves = _moves(rig)
        assert moves[0] == {**moves[0], "move": "setup.step", "args": {"step": "company"}}
        fills = _fills(rig)
        co = COMPANY["company"]
        assert fills["legal_name"] == co["legal_name"]
        assert fills["pan"] == co["pan"] and fills["tan"] == co["tan"]
        await _answer(rig, moves)

        # The pay structure opens empty: nothing is filled until she says.
        seen = len(_moves(rig))
        check_turn(rig, await rig.driver.user_says("Looks right. Next."))
        assert _fills(rig, seen) == {}
        offer = tool_results(llm.captured_inputs[-1])["setup_step"]
        assert "nothing came from signup" in offer and "basic 40% of CTC" in offer

        seen = len(_moves(rig))
        check_turn(rig, await rig.driver.user_says("Use what most companies use."))
        fills = _fills(rig, seen)
        assert fills["basic_pct"] == "40" and fills["hra_metro_pct"] == "50"

        seen = len(_moves(rig))
        check_turn(rig, await rig.driver.user_says("Make basic 45 percent."))
        assert _fills(rig, seen) == {"basic_pct": "45"}

        # The import is hers: Priya points at the sample and the button.
        seen = len(_moves(rig))
        check_turn(rig, await rig.driver.user_says("Go on, import them."))
        told = tool_results(llm.captured_inputs[-1])["setup_step"]
        assert "You cannot import" in told
        assert [m["move"] for m in _moves(rig)[seen:]] == ["setup.step"]
        shown = [
            c["payload"]["args"]
            for c in rig.driver.ui_commands
            if c.get("command") == "stage_cue" and c["payload"]["move"] == "app.show"
        ]
        assert ["Download sample file"] in shown and ["Import file"] in shown

        await rig.driver.send_ui_event(
            "stage_event",
            {
                "name": "setup.changed",
                "by": "visitor",
                "data": {"step": "import", "filled": [], "imported": 56, "test_run": False},
            },
        )
        await asyncio.sleep(0.1)
        said = await rig.driver.user_idle()
        assert "56 rows" in said.text

        seen = len(_moves(rig))
        check_turn(rig, await rig.driver.user_says("Yes, the leave policy."))
        assert _fills(rig, seen) == {}
        check_turn(rig, await rig.driver.user_says("The common one is fine."))
        fills = _fills(rig, seen)
        assert fills["el_per_year"] == "18" and fills["cl_per_year"] == "8"

        check_turn(rig, await rig.driver.user_says("Run the test payroll."))
        result = tool_results(llm.captured_inputs[-1])["setup_step"]
        assert f"{FEB['employees']} employees" in result
        assert f"gross {inr(FEB['gross'])}" in result
        assert f"TDS {inr(FEB['tds'])}" in result
        assert f"net pay {inr(FEB['net_pay'])}" in result
        assert "matches the February draft exactly" in result
        assert _moves(rig)[-1]["move"] == "setup.test_run"


# ─── In-app support ───────────────────────────────────────────────────────────


def _support_llm() -> ScriptedOpenAI:
    return ScriptedOpenAI(
        {
            "Why is Ravi's net pay lower this month?": [
                reply_and_call(
                    "Here's Ravi's January payslip beside December.",
                    "explain_net_pay",
                    employee="Ravi",
                ),
                reply(
                    "{show: Loss of pay} Two days of leave without pay cut his gross. "
                    "{show: TDS} And his tax went up after his proofs were checked."
                ),
            ],
            "Approve Asha's leave.": [
                reply_and_call("", "decide_leave", request="Asha Chavan", decision="approve"),
                reply("Asha asked for 2 days of casual leave. Shall I approve it?"),
            ],
            "Reject Asha's leave.": [
                reply_and_call("", "decide_leave", request="Asha Chavan", decision="reject"),
                reply("Asha asked for 2 days of casual leave. Shall I reject it?"),
            ],
            "Fix Imran's claim.": [
                reply_and_call("", "fix_claim", claim="Imran"),
                reply("The bill says ₹4,580. Shall I correct it?"),
            ],
            "Show me RB-3109.": [
                reply_and_call("Here's that claim.", "open_claim", claim="RB-3109"),
                reply("{show: Bill amount} Rajat's travel claim matches its bill."),
            ],
            "Show me last month's payroll. Who earned the most?": [
                reply_and_call("Here's January's run.", "payroll_register", month="2026-01"),
                reply("{show: Payroll register} January's run is open."),
            ],
            "Can you email this register to my CA?": [
                reply_and_call(
                    "", "hand_off", kind="feature", subject="Email the register", summary="x"
                ),
                reply_and_call("", "offer_request", topic="email the register to her CA"),
                reply(
                    "I can't send email from here. Shall I file it as a support request or a "
                    "feature request?"
                ),
            ],
            "A feature request.": [
                reply_and_call(
                    "I'll write it up beside your screen.",
                    "hand_off",
                    kind="feature",
                    subject="Email the payroll register to an outside accountant",
                    summary="Meghna wants to email a month's payroll register to her CA from "
                    "Paynora. Today she can only view it on screen.",
                ),
                reply("It's written up beside your screen. Shall I send it?"),
            ],
            "I need someone to look at our PF upload.": [
                reply_and_call("", "offer_request", topic="checking the PF ECR upload"),
                reply("I can't check that here. Support request or feature request?"),
            ],
            "Support, please.": reply_and_call(
                "I'll write it up for our payroll team.",
                "hand_off",
                kind="support",
                subject="PF ECR upload for February",
                summary="Meghna wants help uploading the February PF ECR. Nothing in the app is wrong; "
                "she needs the payroll team to check the file before the 15 March due date.",
            ),
        }
    )


async def test_support_explains_ravi_with_the_datas_numbers() -> None:
    llm = _support_llm()
    async with demo("payroll_app", llm) as rig:
        await rig.driver.start_session(init={"landing": "/", "lang": "en"})
        check_turn(rig, await rig.driver.user_says("Why is Ravi's net pay lower this month?"))
        move = _moves(rig)[0]
        assert move["move"] == "payslip.compare"
        assert move["args"] == {"employee_id": "BB-1030", "month": "2026-01", "against": "2025-12"}
        result = tool_results(llm.captured_inputs[-1])["explain_net_pay"]
        s = COMPANY["stories"]["ravi_net_drop"]
        for amount in (s["dec_net"], s["jan_net"], s["tds_dec"], s["tds_jan"], s["reimb_jan"]):
            assert inr(amount) in result, amount
        assert f"gross fell by {inr(s['lop_amount'])}" in result
        assert "2 day(s) unpaid" in result and "LV-2401" in result
        assert "ELSS" in result and "NPS" in result and "21 Jan 2026" in result
        assert "28 Feb 2026" in result
        # The cues in the explanation ring the lines as the voice reaches them.
        shown = [
            c["payload"]["args"]
            for c in rig.driver.ui_commands
            if c.get("command") == "stage_cue" and c["payload"]["move"] == "app.show"
        ]
        assert ["Loss of pay"] in shown and ["TDS"] in shown


async def test_support_approves_asha_with_one_question_and_one_outcome() -> None:
    """Round 1, A3: one natural question, then one line on yes: the outcome
    itself, with the page's answer in it (no "On it." then "Done")."""
    llm = _support_llm()
    async with demo("payroll_app", llm) as rig:
        await rig.driver.start_session(init={"landing": "/", "lang": "en"})
        check_turn(rig, await rig.driver.user_says("Approve Asha's leave."))
        asked = tool_results(llm.captured_inputs[-1])["decide_leave"]
        before = COMPANY["payslips"]["BB-1046"][-1]
        assert "Asha Chavan asked for 2 days of casual leave" in asked
        assert "1 day becomes loss of pay" in asked and asked.rstrip().endswith(
            "Shall I approve it?"
        )
        assert inr(before["net_pay"]) in asked
        assert "leave.decide" not in [m["move"] for m in _moves(rig)]

        yes = await _yes(rig, "Yes.", "leave.decide", "Asha Chavan's leave approved")
        check_turn(rig, yes, units=1)
        decide = _moves(rig)[-1]
        assert decide["args"] == {"request_id": "LV-2412", "decision": "approve"}
        brain = _brain(rig)
        feb = brain.books.slip("BB-1046", "2026-02")
        assert feb is not None and feb["lop_days"] == 1
        assert yes.text.startswith("Approved. 1 day becomes loss of pay")
        assert inr(feb["net_pay"]) in yes.text
        assert "On it" not in yes.text and "Done" not in yes.text
        assert brain.books.draft["net_pay"] == FEB["net_pay"] - (before["net_pay"] - feb["net_pay"])


async def test_support_rejects_with_the_past_tense_right() -> None:
    llm = _support_llm()
    async with demo("payroll_app", llm) as rig:
        await rig.driver.start_session(init={"landing": "/", "lang": "en"})
        check_turn(rig, await rig.driver.user_says("Reject Asha's leave."))
        yes = await _yes(rig, "Yes, reject it.", "leave.decide")
        check_turn(rig, yes, units=1)
        assert (
            yes.text
            == "Rejected. Asha Chavan's leave request LV-2412 is closed, and Asha can see it."
        )


async def test_a_yes_with_a_new_request_is_not_a_yes() -> None:
    """Round 1: "Okay, can you show me the last one" sent a waiting ticket."""
    llm = _support_llm()
    async with demo("payroll_app", llm) as rig:
        await rig.driver.start_session(init={"landing": "/", "lang": "en"})
        check_turn(rig, await rig.driver.user_says("Approve Asha's leave."))
        await rig.driver.user_says("Okay, can you show me last month's payroll?")
        assert "leave.decide" not in [m["move"] for m in _moves(rig)]


async def test_support_fixes_imrans_claim_after_a_yes() -> None:
    llm = _support_llm()
    async with demo("payroll_app", llm) as rig:
        await rig.driver.start_session(init={"landing": "/", "lang": "en"})
        check_turn(rig, await rig.driver.user_says("Fix Imran's claim."))
        asked = tool_results(llm.captured_inputs[-1])["fix_claim"]
        assert "₹4,850" in asked and "₹4,580" in asked
        assert {"move": "claim.open", "args": {"claim_id": "RB-3108"}}.items() <= _moves(rig)[
            -1
        ].items()
        yes = await _yes(rig, "Yes, fix it.", "claim.fix")
        check_turn(rig, yes, units=1)
        fix = _moves(rig)[-1]
        assert fix["move"] == "claim.fix" and fix["args"] == {"claim_id": "RB-3108", "amount": 4580}
        assert yes.text.startswith("Fixed. RB-3108 is now ₹4,580")
        books = _brain(rig).books
        assert books.feb_reimbursements("BB-1032") == 4580
        assert books.draft["reimbursements"] == FEB["reimbursements"] + 4580


async def test_support_opens_a_claim_it_is_asked_about() -> None:
    llm = _support_llm()
    async with demo("payroll_app", llm) as rig:
        await rig.driver.start_session(init={"landing": "/reimbursements", "lang": "en"})
        check_turn(rig, await rig.driver.user_says("Show me RB-3109."))
        assert _moves(rig)[-1]["move"] == "claim.open"
        assert "the bill matches" in tool_results(llm.captured_inputs[-1])["open_claim"]


async def test_support_opens_last_months_payroll_instead_of_a_ticket() -> None:
    """Round 1, A4: previous month's payroll is a move she makes, and the
    highest earner is answered from the data."""
    llm = _support_llm()
    async with demo("payroll_app", llm) as rig:
        await rig.driver.start_session(init={"landing": "/payroll/PR-2026-02", "lang": "en"})
        check_turn(
            rig, await rig.driver.user_says("Show me last month's payroll. Who earned the most?")
        )
        opened = _moves(rig)[-1]
        assert opened["move"] == "app.open" and opened["args"] == {"path": "/payroll/PR-2026-01"}
        result = tool_results(llm.captured_inputs[-1])["payroll_register"]
        jan = next(r for r in COMPANY["payroll_runs"] if r["id"] == "PR-2026-01")
        assert f"net pay {inr(jan['net_pay'])}" in result
        top = max(
            COMPANY["employees"],
            key=lambda e: next(
                (p["gross"] for p in COMPANY["payslips"][e["id"]] if p["month"] == "2026-01"), 0
            ),
        )
        assert top["name"] in result
        assert "ticket.draft" not in [m["move"] for m in _moves(rig)]


async def test_a_request_is_offered_first_and_filed_beside_the_screen() -> None:
    """Round 1, A4: hand_off is refused until she was offered support or
    feature and answered; the draft never navigates."""
    llm = _support_llm()
    async with demo("payroll_app", llm) as rig:
        await rig.driver.start_session(init={"landing": "/payroll/PR-2026-01", "lang": "en"})
        check_turn(rig, await rig.driver.user_says("Can you email this register to my CA?"))
        assert "ticket.draft" not in [m["move"] for m in _moves(rig)]
        check_turn(rig, await rig.driver.user_says("A feature request."))
        draft = _moves(rig)[-1]
        assert draft["move"] == "ticket.draft" and draft["args"]["kind"] == "feature"
        assert "app.open" not in [m["move"] for m in _moves(rig)]


async def test_support_hands_off_with_a_written_request_on_screen() -> None:
    llm = _support_llm()
    async with demo("payroll_app", llm) as rig:
        await rig.driver.start_session(init={"landing": "/help", "lang": "en"})
        check_turn(rig, await rig.driver.user_says("I need someone to look at our PF upload."))
        check_turn(rig, await rig.driver.user_says("Support, please."))
        draft = _moves(rig)[-1]
        assert draft["move"] == "ticket.draft"
        assert draft["args"]["kind"] == "support"
        assert draft["args"]["subject"] == "PF ECR upload for February"
        assert "PF ECR" in draft["args"]["summary"]
        sent = await _yes(rig, "Yes, send it.", "ticket.submit")
        check_turn(rig, sent, units=1)
        assert _moves(rig)[-1]["move"] == "ticket.submit"
        assert "TK-1208" in sent.text and "support request" in sent.text


async def test_a_change_made_by_click_reaches_the_books_and_the_model() -> None:
    llm = ScriptedOpenAI({"What changed?": reply("You approved Asha's leave.")})
    async with demo("payroll_app", llm) as rig:
        await rig.driver.start_session(init={"landing": "/", "lang": "en"})
        await rig.driver.send_ui_event(
            "stage_event",
            {
                "name": "leave.decided",
                "by": "visitor",
                "data": {
                    "request_id": "LV-2412",
                    "decision": "approve",
                    "employee_id": "BB-1046",
                    "lop_days": 1,
                },
            },
        )
        await asyncio.sleep(0.1)
        await rig.driver.user_says("What changed?")
        feb = _brain(rig).books.slip("BB-1046", "2026-02")
        assert feb is not None and feb["lop_days"] == 1
        notes = "\n".join(
            str(i.get("content")) for i in llm.captured_inputs[-1] if isinstance(i, dict)
        )
        assert "She approved LV-2412 by hand" in notes and inr(feb["net_pay"]) in notes


# ─── Feature coach ────────────────────────────────────────────────────────────


def _coach_llm() -> ScriptedOpenAI:
    return ScriptedOpenAI(
        {
            "How do I switch Kavitha to the old regime?": [
                reply_and_call(
                    "This is her regime screen.",
                    "open_feature",
                    feature="regime_switch",
                    employee="Kavitha Menon",
                ),
                reply_and_call(
                    "Here are both regimes.", "compare_regimes", employee="Kavitha Menon"
                ),
                reply(
                    "{show: New regime} On the new regime her tax is ₹6,56,260. "
                    "{show: Old regime slabs} On the old one it's ₹6,27,090."
                ),
            ],
            "Switch her.": [
                reply_and_call(
                    "Here's what changes.", "switch_regime", employee="Kavitha Menon", regime="old"
                ),
                reply("Her February TDS drops. Shall I switch her?"),
            ],
        }
    )


async def test_coach_compares_kavitha_slab_by_slab_and_switches_after_a_yes() -> None:
    llm = _coach_llm()
    async with demo("payroll_app", llm) as rig:
        greeting = await rig.driver.start_session(init={"landing": "/tax", "lang": "en"})
        assert greeting is not None
        check_turn(rig, await rig.driver.user_says("How do I switch Kavitha to the old regime?"))
        results = tool_results(llm.captured_inputs[-1])
        guide = results["open_feature"]
        assert "Switch regime" in guide and "Old regime slabs" in guide
        comp = results["compare_regimes"]
        k = COMPANY["stories"]["kavitha_old_better"]
        assert f"total {inr(k['new_total'])}" in comp and f"total {inr(k['old_total'])}" in comp
        assert f"lower by {inr(k['saving'])}" in comp and "at 30%" in comp
        assert [m["move"] for m in _moves(rig)] == ["regime.compare", "regime.compare"]
        assert _moves(rig)[0]["args"] == {"employee_id": "BB-1007"}

        check_turn(rig, await rig.driver.user_says("Switch her."))
        asked = tool_results(llm.captured_inputs[-1])["switch_regime"]
        feb = COMPANY["payslips"]["BB-1007"][-1]
        assert inr(feb["tds"]) in asked
        check_turn(rig, await rig.driver.user_says("Yes."), units=1)
        switch = _moves(rig)[-1]
        assert switch["move"] == "regime.switch"
        assert switch["args"] == {"employee_id": "BB-1007", "regime": "old"}
        await _answer(rig, [switch])
        outcome = await rig.driver.user_idle()
        books = _brain(rig).books
        after = books.slip("BB-1007", "2026-02")
        assert after is not None and after["regime"] == "old" and after["tds"] < feb["tds"]
        assert inr(after["tds"]) in outcome.text
        # (₹6,27,090 minus TDS to January) over February and March.
        ytd = next(e for e in COMPANY["employees"] if e["id"] == "BB-1007")["ytd_to_jan"]["tds"]
        assert after["tds"] == round((k["old_total"] - ytd) / 2)


async def test_moving_to_the_wizard_switches_the_job() -> None:
    async with demo("payroll_app", ScriptedOpenAI()) as rig:
        await rig.driver.start_session(init={"landing": "/", "lang": "en"})
        await rig.driver.send_ui_event(
            "stage_event",
            {
                "name": "screen.viewed",
                "by": "visitor",
                "data": {"path": "/welcome", "title": "Setup"},
            },
        )
        await asyncio.sleep(0.1)
        assert _brain(rig).mode == "onboarding"


# ─── The files the brain and the page share ──────────────────────────────────


def test_the_stage_spec_is_current_and_clean() -> None:
    source = "payroll_app/frontend/src/stage/scene.json"
    py, ts = "payroll_app/backend/stage_gen.py", "payroll_app/frontend/src/stage/scene.gen.ts"
    spec = load_spec(DEMOS / source)
    assert [f for f in check_spec(spec) if f.level == "error"] == []
    command = f"voqalize stage gen {source} --py {py} --ts {ts}"
    assert (DEMOS / py).read_text() == render_python(spec, source=source, command=command)
    assert (DEMOS / ts).read_text() == render_typescript(spec, source=source, command=command)


def test_the_data_is_what_build_data_writes_now() -> None:
    """company.json and tax_fixtures.json are build_data.py's output today: the
    engine, the generator and the committed data have not drifted apart."""
    spec = importlib.util.spec_from_file_location(
        "payroll_build_data", APP / "data" / "build_data.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # its dataclasses look their module up by name
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    written = json.loads((APP / "data" / "company.json").read_text())
    assert json.loads(json.dumps(module.build(), ensure_ascii=False)) == written
    fixtures = json.loads((APP / "data" / "tax_fixtures.json").read_text())
    assert json.loads(json.dumps(module.fixtures(), ensure_ascii=False)) == fixtures
    assert (APP / "data" / "employees_import.csv").read_text() == module.import_csv(written)


def test_the_persona_is_the_only_place_the_character_lives() -> None:
    backend = "\n".join(p.read_text() for p in (APP / "backend").glob("*.py"))
    assert NAME not in backend
    assert PERSONA["voices"]["en"] not in backend


# ─── A call outlives a dropped brain socket (SDK 0.15.0, Config.redial) ──────


def _redials(driver: VoqalizeDriver) -> list[bool | None]:
    return [
        r.config.redial.enabled
        for r in driver.requests
        if isinstance(r, ConfigureFrame) and r.config.redial is not None
    ]


@contextlib.asynccontextmanager
async def _redial_rig(
    llm: ScriptedOpenAI, sid: str = "payroll_app-redial-e2e"
) -> AsyncIterator[tuple[DemoRig, DemoRig]]:
    """One brain server and two sockets for one session id, as Voqalize opens
    them: the first for the call, the second for the redial after it drops."""
    build = build_for("payroll_app")
    built: list[Brain] = []

    def _build() -> Brain:
        brain = build(llm)  # type: ignore[arg-type]
        built.append(brain)
        return brain

    keypair = generate_keypair()
    server = BrainServer(_build, host="127.0.0.1", port=0, public_keys=keypair.public_pem)
    port = await server.start()

    def rig() -> DemoRig:
        token = mint_voqalize_token(
            private_key_pem=keypair.private_pem,
            session_id=sid,
            agent_id="payroll_app",
            organization_id="demo",
        )
        driver = VoqalizeDriver(
            DirectConnection(f"ws://127.0.0.1:{port}", sid, token=token),
            session_id=sid,
            default_timeout=10.0,
        )
        return DemoRig(name="payroll_app", server=server, driver=driver, _built=built)

    first, second = rig(), rig()
    try:
        yield first, second
    finally:
        await first.driver.aclose()
        await second.driver.aclose()
        await server.aclose()


def _dropped(store: Rejoin[PaynoraBrain], sid: str) -> bool:
    entry = store._held.get(sid)
    return entry is not None and entry[2] is not None


async def _drop(rig: DemoRig, store: Rejoin[PaynoraBrain] = REJOIN) -> None:
    """The socket drops: no End, no close code a hang-up would send. Waits for
    the brain's ``on_session_end`` to mark the call dropped."""
    await rig.driver.aclose()
    for _ in range(100):
        if _dropped(store, rig.driver.session_id):
            return
        await asyncio.sleep(0.02)
    raise AssertionError("the dropped call was not held for a redial")


async def test_a_dropped_socket_rejoins_the_call_with_its_books_and_pending_yes() -> None:
    """Support on ``/``: Asha's leave approved (the books change), then Imran's
    claim fix asked and not yet answered; the brain's socket drops without a
    hang-up. Voqalize dials again for the same session with the same init; the
    new brain adopts the call — this session's copy of the books with Asha's
    loss of pay in it, the fix waiting for a yes, the model's history — says no
    second greeting, and the yes on the new socket fixes the claim."""
    llm = _support_llm()
    async with _redial_rig(llm) as (first, second):
        await first.driver.open()
        greeting = await first.driver.start_session(init={"landing": "/", "lang": "en"})
        check_greeting(first, greeting)
        assert _redials(first.driver) == [True], "redial is on with the voice, before the greeting"
        check_turn(first, await first.driver.user_says("Approve Asha's leave."))
        await _yes(first, "Yes.", "leave.decide", "Asha Chavan's leave approved")
        check_turn(first, await first.driver.user_says("Fix Imran's claim."))
        before = _brain(first)
        books, path = before.books, before.path
        asha = books.slip("BB-1046", "2026-02")
        assert asha is not None and asha["lop_days"] == 1
        pending = before.confirms.pending
        assert pending is not None and pending.kind == "fix_claim", "the fix waits for a yes"

        await _drop(first)

        # Voqalize redials: the same session id, the same init.
        await second.driver.open()
        again = await second.driver.start_session(
            init={"landing": "/", "lang": "en"}, greeting_timeout=0.5
        )
        assert again is None, "no second greeting on a rejoined call"
        after = _brain(second)
        assert after is not before and after.rejoined
        assert after.books is books, "the session's own copy of the books came across"
        assert after.mode == "support" and after.lang == "en"
        assert after.path == path and path != "/", "the page it moved to, not init's landing"
        assert _redials(second.driver) == [True]
        check_voice_pair(second, voice=PERSONA["voices"]["en"], language="en")

        yes = await _yes(second, "Yes, fix it.", "claim.fix")
        check_turn(second, yes, units=1)
        fix = _moves(second)[-1]
        assert fix["move"] == "claim.fix" and fix["args"] == {"claim_id": "RB-3108", "amount": 4580}
        assert yes.text.startswith("Fixed. RB-3108 is now ₹4,580")
        assert after.books.feb_reimbursements("BB-1032") == 4580
        asha = after.books.slip("BB-1046", "2026-02")
        assert asha is not None and asha["lop_days"] == 1, "the change before the drop stands"

        check_turn(second, await second.driver.user_says("Show me RB-3109."))
        sent = json.dumps(llm.captured_inputs[-1], ensure_ascii=False)
        assert "Approve Asha's leave." in sent, "the model's history came across"
        assert sent.count(JOB_NOTE["support"]) == 1, "the job is not told twice"


async def test_a_redial_after_the_hold_expires_starts_fresh() -> None:
    """Held calls go two minutes after their socket drops: a redial later than
    that starts a new conversation from a fresh copy of the books, and greets."""
    now = [0.0]
    store: Rejoin[PaynoraBrain] = Rejoin(clock=lambda: now[0])
    saved = brain_mod.REJOIN
    brain_mod.REJOIN = store
    try:
        async with _redial_rig(_support_llm(), sid="payroll_app-expiry-e2e") as (first, second):
            await first.driver.open()
            await first.driver.start_session(init={"landing": "/", "lang": "en"})
            check_turn(first, await first.driver.user_says("Approve Asha's leave."))
            await _yes(first, "Yes.", "leave.decide", "Asha Chavan's leave approved")
            before = _brain(first)
            await _drop(first, store)
            assert len(store) == 1, "held for a redial"
            now[0] += KEEP_AFTER_DROP_S + 1
            assert len(store) == 0, "let go after two minutes"

            await second.driver.open()
            greeting = await second.driver.start_session(init={"landing": "/", "lang": "en"})
            check_greeting(second, greeting)
            after = _brain(second)
            assert after is not before and not after.rejoined
            asha = after.books.slip("BB-1046", "2026-02")
            assert asha is not None and asha["lop_days"] == 0, "fresh books"
    finally:
        brain_mod.REJOIN = saved


def test_the_rejoin_store_keeps_a_live_call_and_lets_a_dropped_one_go() -> None:
    now = [0.0]
    store: Rejoin[object] = Rejoin(clock=lambda: now[0])
    a, b = object(), object()
    store.hold("s1", a)
    store.dropped("s1", b)  # not the brain held: nothing changes
    now[0] = KEEP_AFTER_DROP_S + 1
    assert store.take("s1") is a, "a live call is kept however long it runs"
    store.hold("s1", a)
    store.dropped("s1", a)
    store.dropped("s1", a)  # on_session_end runs at least once: idempotent
    now[0] += KEEP_AFTER_DROP_S - 1
    assert len(store) == 1
    now[0] += 2
    assert store.take("s1") is None and len(store) == 0
    assert store.take("never-held") is None


async def test_no_redial_is_asked_of_a_voqalize_that_does_not_offer_it() -> None:
    """``configure`` raises for redial without the capability: the guide asks
    only where it is offered, and the call starts the same either way."""
    async with demo("payroll_app", ScriptedOpenAI()) as rig:
        rig.driver.capabilities.discard(Capability.REDIAL)
        greeting = await rig.driver.start_session(init={"landing": "/", "lang": "en"})
        check_greeting(rig, greeting)
        assert _redials(rig.driver) == []
        check_voice_pair(rig, voice=PERSONA["voices"]["en"], language="en")


# ─── Round 2 (23 Nov) ─────────────────────────────────────────────────────────


def _r1_llm() -> ScriptedOpenAI:
    """The owner's own words from his 23 Nov call, as the model hears them."""
    return ScriptedOpenAI(
        {
            "Yes please, the pay structure.": [
                reply_and_call("Here's the pay structure.", "setup_step", step="structure"),
                reply("Your own values, or what most companies use?"),
            ],
            "Basic keep it 50% and HRA at 50%": [
                reply_and_call(
                    "Putting those in.",
                    "setup_fill",
                    step="structure",
                    values=[
                        {"field": "basic_pct", "value": "50"},
                        {"field": "hra_metro_pct", "value": "50"},
                        {"field": "hra_non_metro_pct", "value": "40"},
                    ],
                    rest="defaults",
                ),
                reply("Basic is 50%, HRA 50% and 40%, the rest the common values."),
            ],
            "Now the leave policy.": [
                reply_and_call("Here's the leave policy.", "setup_step", step="leave"),
                reply("What would you like?"),
            ],
            "Earned leave 18 and sick leave 8": [
                reply_and_call(
                    "Putting those in.",
                    "setup_fill",
                    step="leave",
                    values=[
                        {"field": "el_per_year", "value": "18"},
                        {"field": "sl_per_year", "value": "8"},
                        {"field": "el_carry_forward", "value": "10"},
                    ],
                ),
                reply("18 earned, 8 sick, 10 carried forward. Casual leave?"),
            ],
            "Casual leave, use the common default.": [
                reply_and_call("Putting it in.", "setup_fill", step="leave", rest="defaults"),
                reply("Casual leave is in, with the cut-off and loss-of-pay rules."),
            ],
            "Just fill it.": [
                reply_and_call("", "setup_fill", step="structure"),
                reply("What would you like in it?"),
            ],
        }
    )


async def test_onboarding_fills_her_values_directly_and_defaults_only_the_rest() -> None:
    """Round 2, R1: "Basic 50%, HRA 50% and 40% elsewhere, the rest as common"
    put the common defaults in first and then changed three of them. Now each
    field goes in once: her values as she said them, then the defaults only
    for the fields she did not give, and only when she said so."""
    llm = _r1_llm()
    async with demo("payroll_app", llm) as rig:
        await rig.driver.start_session(init={"landing": "/welcome", "lang": "en"})
        check_turn(rig, await rig.driver.user_says("Yes please, the pay structure."))
        seen = len(_moves(rig))
        check_turn(
            rig,
            await rig.driver.user_says(
                "Basic keep it 50% and HRA at 50% and for everywhere else it can be 40%. "
                "The rest you can fill as per the common."
            ),
        )
        fills = [m["args"] for m in _moves(rig)[seen:] if m["move"] == "setup.fill"]
        names = [f["field"] for f in fills]
        assert len(names) == len(set(names)), f"a field was filled twice: {names}"
        assert fills[:3] == [
            {"field": "basic_pct", "value": "50"},
            {"field": "hra_metro_pct", "value": "50"},
            {"field": "hra_non_metro_pct", "value": "40"},
        ]
        assert set(names) == {
            "basic_pct",
            "hra_metro_pct",
            "hra_non_metro_pct",
            "lta_g5",
            "lta_g6_up",
            "pf_rule",
            "esi_rule",
        }
        assert "setup.step" not in [m["move"] for m in _moves(rig)[seen:]]
        told = tool_results(llm.captured_inputs[-1])["setup_fill"]
        assert "Her values" in told and "basic 50% of CTC" in told
        assert "basic 40%" not in told

        # Leave: her three values only; nothing else until she says so.
        check_turn(rig, await rig.driver.user_says("Now the leave policy."))
        seen = len(_moves(rig))
        check_turn(
            rig,
            await rig.driver.user_says(
                "Earned leave 18 and sick leave 8, carry forward at most 10 days."
            ),
        )
        assert _fills(rig, seen) == {
            "el_per_year": "18",
            "sl_per_year": "8",
            "el_carry_forward": "10",
        }
        assert "Still empty: cl_per_year" in tool_results(llm.captured_inputs[-1])["setup_fill"]

        # The defaults for the rest never overwrite what she gave, or what she typed.
        await rig.driver.send_ui_event(
            "stage_event",
            {
                "name": "setup.changed",
                "by": "visitor",
                "data": {"step": "leave", "filled": ["lop_rule"], "test_run": False},
            },
        )
        await asyncio.sleep(0.1)
        seen = len(_moves(rig))
        check_turn(rig, await rig.driver.user_says("Casual leave, use the common default."))
        policy = {t["id"]: t for t in COMPANY["leave"]["policy"]["types"]}
        assert _fills(rig, seen) == {
            "cl_per_year": str(policy["CL"]["per_year"]),
            "attendance_cutoff": COMPANY["leave"]["policy"]["attendance_cutoff"],
        }


async def test_a_fill_with_nothing_said_fills_nothing() -> None:
    llm = _r1_llm()
    async with demo("payroll_app", llm) as rig:
        await rig.driver.start_session(init={"landing": "/welcome", "lang": "en"})
        check_turn(rig, await rig.driver.user_says("Just fill it."))
        assert _fills(rig) == {}
        assert "NOT DONE" in tool_results(llm.captured_inputs[-1])["setup_fill"]


def _view_llm() -> ScriptedOpenAI:
    return ScriptedOpenAI(
        {
            "View this as Aditi Bhandari.": [
                reply_and_call("", "view_as_employee", employee="Aditi Bhandari"),
                reply("This is Paynora as Aditi sees it."),
            ],
            "Show me November 2025 payslip.": [
                reply_and_call(
                    "Here's November.", "explain_net_pay", employee="Aditi", month="2025-11"
                ),
                reply("{show: Net pay} Her November net pay is on screen."),
            ],
            "Show me Ravi's payslip.": [
                reply_and_call("", "explain_net_pay", employee="Ravi Kumar"),
                reply("Aditi can only see her own payslips. Shall I switch back to admin?"),
            ],
            "Approve Asha's leave.": [
                reply_and_call("", "decide_leave", request="Asha Chavan", decision="approve"),
                reply("An employee can't approve leave. Shall I switch back to admin?"),
            ],
            "Compare my regimes.": [
                reply_and_call("", "compare_regimes", employee="Aditi Bhandari"),
                reply("Both regimes are on your tax tab."),
            ],
            "Switch to admin.": [
                reply_and_call("", "view_as_admin"),
                reply("Back in the admin view."),
            ],
            "Show me Aditi's November payslip now.": [
                reply_and_call("", "explain_net_pay", employee="Aditi", month="2025-11"),
                reply("Here it is."),
            ],
        }
    )


async def test_the_employee_view_stays_until_she_asks_to_leave_it() -> None:
    """Round 2, R3: in Aditi's view, "payslip number 125" (November 2025, as
    the recognizer heard it) opened the ADMIN payslip and left her view. Now
    the view is sticky: her payslip opens in her view, admin work and other
    employees are refused, and only "switch to admin" leaves it."""
    llm = _view_llm()
    async with demo("payroll_app", llm) as rig:
        await rig.driver.start_session(init={"landing": "/", "lang": "en"})
        check_turn(rig, await rig.driver.user_says("View this as Aditi Bhandari."))
        assert _moves(rig)[-1]["move"] == "me.view"
        brain = _brain(rig)
        assert brain.view_as == "BB-1001"

        check_turn(rig, await rig.driver.user_says("Show me November 2025 payslip."))
        last = _moves(rig)[-1]
        assert last["move"] == "me.view"
        assert {"employee_id": "BB-1001", "tab": "payslips", "month": "2025-11"}.items() <= last[
            "args"
        ].items()
        assert "payslip.compare" not in [m["move"] for m in _moves(rig)]
        assert brain.view_as == "BB-1001"
        # Every turn in the view tells the model whose side it is answering from.
        assert any("Employee view" in str(i) for i in llm.captured_inputs[-1])

        for ask, tool in (
            ("Show me Ravi's payslip.", "explain_net_pay"),
            ("Approve Asha's leave.", "decide_leave"),
        ):
            seen = len(_moves(rig))
            check_turn(rig, await rig.driver.user_says(ask))
            assert tool_results(llm.captured_inputs[-1])[tool].startswith("NOT DONE")
            assert _moves(rig)[seen:] == []
            assert brain.view_as == "BB-1001"
        assert brain.confirms.pending is None

        check_turn(rig, await rig.driver.user_says("Compare my regimes."))
        assert _moves(rig)[-1]["move"] == "me.view" and _moves(rig)[-1]["args"]["tab"] == "tax"

        check_turn(rig, await rig.driver.user_says("Switch to admin."))
        assert brain.view_as is None
        assert _moves(rig)[-1] == {
            **_moves(rig)[-1],
            "move": "app.open",
            "args": {"path": "/employees/BB-1001"},
        }
        check_turn(rig, await rig.driver.user_says("Show me Aditi's November payslip now."))
        assert _moves(rig)[-1]["move"] == "payslip.compare"


async def test_leaving_the_employee_view_by_hand_ends_it() -> None:
    async with demo("payroll_app", _view_llm()) as rig:
        await rig.driver.start_session(init={"landing": "/", "lang": "en"})
        check_turn(rig, await rig.driver.user_says("View this as Aditi Bhandari."))
        brain = _brain(rig)
        assert brain.view_as == "BB-1001"
        await rig.driver.send_ui_event(
            "stage_event",
            {
                "name": "screen.viewed",
                "by": "visitor",
                "data": {"path": "/employees/BB-1001", "title": "Aditi Bhandari"},
            },
        )
        await asyncio.sleep(0.1)
        assert brain.view_as is None


_DEVANAGARI_LINE = re.compile(r"[ऀ-ॿ]")


def _hindi(text: str) -> bool:
    """A Hindi sentence: Devanagari, with product words in English allowed."""
    return bool(_DEVANAGARI_LINE.search(text)) and not re.search(
        r"\b(Approved|Rejected|Fixed|Switched|Saved|Sent|Shall I|is closed|won't be)\b", text
    )


def _hindi_llm() -> ScriptedOpenAI:
    return ScriptedOpenAI(
        {
            "Asha ki leave reject karo.": [
                reply_and_call("", "decide_leave", request="Asha Chavan", decision="reject"),
                reply("Asha ने छुट्टी माँगी है। क्या मैं इसे reject कर दूँ?"),
            ],
            "Asha ki leave approve karo.": [
                reply_and_call("", "decide_leave", request="Asha Chavan", decision="approve"),
                reply("क्या मैं इसे approve कर दूँ?"),
            ],
            "Imran ka claim fix karo.": [
                reply_and_call("", "fix_claim", claim="Imran"),
                reply("क्या मैं इसे ठीक कर दूँ?"),
            ],
            "Simran ka claim reject karo.": [
                reply_and_call("", "decide_claim", claim="Simran", decision="reject"),
                reply("क्या मैं इसे reject कर दूँ?"),
            ],
            "Kavitha ko old regime par daalo.": [
                reply_and_call("", "switch_regime", employee="Kavitha Menon", regime="old"),
                reply("क्या मैं switch कर दूँ?"),
            ],
            "Aditi ke roop mein dikhao.": [
                reply_and_call("", "view_as_employee", employee="Aditi Bhandari"),
            ],
        }
    )


async def test_a_hindi_call_hears_every_ask_and_outcome_in_hindi() -> None:
    """Round 2, R8: in a Hindi call, "Rejected. Asha Chavan's leave request
    LV-2412 is closed…" and "Asha Chavan asked for 2 days…" came out as whole
    English sentences. Every line the brain writes itself is now in the call's
    language; approve, reject, payslip and the like stay as they are."""
    llm = _hindi_llm()
    async with demo("payroll_app", llm) as rig:
        await rig.driver.start_session(init={"landing": "/", "lang": "hi"})

        check_turn(rig, await rig.driver.user_says("Asha ki leave approve karo."))
        asked = tool_results(llm.captured_inputs[-1])["decide_leave"]
        assert "क्या मैं इसे approve कर दूँ?" in asked and "loss of pay बनेगा" in asked
        assert "Shall I" not in asked and "asked for" not in asked
        await rig.driver.user_says("नहीं।")

        check_turn(rig, await rig.driver.user_says("Asha ki leave reject karo."))
        yes = await _yes(rig, "हाँ।", "leave.decide")
        check_turn(rig, yes, units=1)
        assert _hindi(yes.text), yes.text
        assert yes.text.startswith("Reject हो गई।") and "LV-2412" in yes.text

        check_turn(rig, await rig.driver.user_says("Imran ka claim fix karo."))
        asked = tool_results(llm.captured_inputs[-1])["fix_claim"]
        assert "₹4,580" in asked and "approve कर दूँ?" in asked
        yes = await _yes(rig, "हाँ।", "claim.fix")
        assert _hindi(yes.text) and yes.text.startswith("Fix हो गया।"), yes.text

        check_turn(rig, await rig.driver.user_says("Simran ka claim reject karo."))
        asked = tool_results(llm.captured_inputs[-1])["decide_claim"]
        assert "क्या मैं इसे reject कर दूँ?" in asked
        yes = await _yes(rig, "हाँ।", "claim.decide")
        assert _hindi(yes.text) and "pay नहीं होगा" in yes.text, yes.text

        # Asked again after it is done: the duplicate line is Hindi too.
        brain = _brain(rig)
        assert brain.confirms.already(("claim", "RB-3110", "reject")) is not None
        assert _hindi(brain.confirms.already(("claim", "RB-3110", "reject")) or "")

        check_turn(rig, await rig.driver.user_says("Kavitha ko old regime par daalo."))
        asked = tool_results(llm.captured_inputs[-1])["switch_regime"]
        assert "क्या मैं switch कर दूँ?" in asked
        yes = await _yes(rig, "हाँ।", "regime.switch")
        assert _hindi(yes.text) and yes.text.startswith("Switch हो गया।"), yes.text

        # A turn that moved the screen and said nothing: the floor line is Hindi.
        said = await rig.driver.user_says("Aditi ke roop mein dikhao.")
        assert _hindi(said.text) and "Aditi Bhandari" in said.text, said.text


async def test_a_hindi_call_hears_a_refused_or_unanswered_change_in_hindi() -> None:
    llm = _hindi_llm()
    async with demo("payroll_app", llm) as rig:
        await rig.driver.start_session(init={"landing": "/", "lang": "hi"})
        check_turn(rig, await rig.driver.user_says("Asha ki leave reject karo."))

        async def page() -> None:
            for _ in range(200):
                sent = [m for m in _moves(rig) if m["move"] == "leave.decide"]
                if sent:
                    await rig.driver.send_ui_event(
                        "stage_result",
                        {
                            "call_ref": sent[-1]["call_ref"],
                            "move": "leave.decide",
                            "outcome": "refused",
                            "detail": "the February run is locked",
                        },
                    )
                    return
                await asyncio.sleep(0.01)

        task = asyncio.create_task(page())
        turn = await rig.driver.user_says("हाँ।")
        await task
        assert _hindi(turn.text) and "नहीं हो पाया" in turn.text, turn.text


# ─── Amounts in speech, both ways (X8) ───────────────────────────────────────

_ADD = "Add Meera Iyer, an engineer in Pune, joining 16 February, CTC 7.2 lakh."


async def test_amounts_are_spoken_as_words_and_a_wrong_ctc_is_confirmed() -> None:
    """X8 over the wire: "7.2 lakh" heard is noted to the model as 720000 rupees; a CTC
    that lost its scale on the way (72) never reaches the form, the tool asks for it
    to be confirmed back, and the voice says the amount in words. In Hindi a scaled
    amount reaches the voice as whole rupees with the ₹ mark."""
    llm = ScriptedOpenAI(
        {
            _ADD: [
                reply_and_call(
                    "Filling it in.",
                    "fill_new_employee",
                    name="Meera Iyer",
                    title="Software Engineer",
                    department="Engineering",
                    location="Pune",
                    joined="2026-02-16",
                    annual_ctc=72,
                    gender="F",
                ),
                reply("Just to check, ₹7.2 lakh, right?"),
            ],
            "उसका CTC कितना है?": reply("उनका CTC ₹16.8 lakh है।"),
        }
    )
    async with demo("payroll_app", llm) as rig:
        await rig.driver.start_session(init={"landing": "/", "lang": "en"})
        turn = await rig.driver.user_says(_ADD)
        told = json.dumps(llm.captured_inputs[-1], ensure_ascii=False)
        assert "'7.2 lakh' = 720000" in told
        result = tool_results(llm.captured_inputs[-1])["fill_new_employee"]
        assert result.startswith("Not done") and "₹7,20,000" in result
        assert not [m for m in _moves(rig) if m["move"] == "employee.fill"]
        assert "seven point two lakh rupees, right?" in turn.text and "₹" not in turn.text

    async with demo("payroll_app", llm) as rig:
        await rig.driver.start_session(init={"landing": "/", "lang": "hi"})
        turn = await rig.driver.user_says("उसका CTC कितना है?")
        assert "₹16,80,000" in turn.text and "lakh" not in turn.text
