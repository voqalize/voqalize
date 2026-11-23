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
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedOpenAI, reply, reply_and_call, tool_results

from voqalize.sdk.stage import load_spec
from voqalize.sdk.stage.check import check_spec
from voqalize.sdk.stage.gen import render_python, render_typescript

from ._harness import DemoRig, check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.payroll_app import books as books_mod  # noqa: E402
from voqalize_demos._loaded.payroll_app.brain import PaynoraBrain  # noqa: E402

DEMOS = Path(__file__).resolve().parents[1]
APP = DEMOS / "payroll_app"
PERSONA = json.loads((APP / "persona.json").read_text())
NAME = PERSONA["display_name"]
COMPANY = json.loads((APP / "data" / "company.json").read_text())
FEB = next(r for r in COMPANY["payroll_runs"] if r["id"] == "PR-2026-02")
inr = books_mod.inr


def _moves(rig: DemoRig) -> list[dict[str, Any]]:
    return [dict(c["payload"]) for c in rig.driver.ui_commands if c.get("command") == "stage_move"]


async def _answer(rig: DemoRig, moves: list[dict[str, Any]], detail: str = "") -> None:
    for m in moves:
        await rig.driver.send_ui_event(
            "stage_result",
            {"call_ref": m["call_ref"], "move": m["move"], "outcome": "applied", "detail": detail},
        )
    await asyncio.sleep(0.1)


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
                reply_and_call("Now the pay structure.", "setup_step", step="structure"),
                reply("That's your rule. Shall I import your employees?"),
            ],
            "Go on, import them.": [
                reply_and_call("Importing your file.", "setup_step", step="import"),
                reply("All 56 rows are valid. Leave policy next?"),
            ],
            "Yes, the leave policy.": [
                reply_and_call("Here's the leave policy.", "setup_step", step="leave"),
                reply("Done. Shall I run a test payroll?"),
            ],
            "Run the test payroll.": [
                reply_and_call("Running February as a test.", "setup_step", step="test_run"),
                reply("The test matches your February draft."),
            ],
        }
    )


async def test_onboarding_fills_each_step_and_the_test_payroll_equals_the_draft() -> None:
    llm = _onboarding_llm()
    async with demo("payroll_app", llm) as rig:
        greeting = await rig.driver.start_session(init={"landing": "/welcome", "lang": "en"})
        assert greeting is not None and "setup" in greeting.text
        check_turn(rig, await rig.driver.user_says("Yes, let's begin."))
        moves = _moves(rig)
        assert moves[0] == {**moves[0], "move": "setup.step", "args": {"step": "company"}}
        fills = {m["args"]["field"]: m["args"]["value"] for m in moves if m["move"] == "setup.fill"}
        co = COMPANY["company"]
        assert fills["legal_name"] == co["legal_name"]
        assert fills["pan"] == co["pan"] and fills["tan"] == co["tan"]
        await _answer(rig, moves)

        check_turn(rig, await rig.driver.user_says("Looks right. Next."))
        fills = {
            m["args"]["field"]: m["args"]["value"] for m in _moves(rig) if m["move"] == "setup.fill"
        }
        assert fills["basic_pct"] == "40" and fills["hra_metro_pct"] == "50"

        check_turn(rig, await rig.driver.user_says("Go on, import them."))
        imported = tool_results(llm.captured_inputs[-1])["setup_step"]
        assert "56 rows, 56 valid, no errors" in imported
        assert "setup.import" in [m["move"] for m in _moves(rig)]

        check_turn(rig, await rig.driver.user_says("Yes, the leave policy."))
        fills = {
            m["args"]["field"]: m["args"]["value"] for m in _moves(rig) if m["move"] == "setup.fill"
        }
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
                reply_and_call(
                    "Let me see what that does.",
                    "decide_leave",
                    request="Asha Chavan",
                    decision="approve",
                ),
                reply("One day becomes loss of pay. Shall I approve it?"),
            ],
            "Fix Imran's claim.": [
                reply_and_call("Checking his bill.", "fix_claim", claim="Imran"),
                reply("The bill says ₹4,580. Shall I fix it?"),
            ],
            "I need someone to look at our PF upload.": reply_and_call(
                "I'll write it up for our payroll team.",
                "hand_off",
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


async def test_support_approves_asha_after_a_yes_and_the_draft_follows() -> None:
    llm = _support_llm()
    async with demo("payroll_app", llm) as rig:
        await rig.driver.start_session(init={"landing": "/", "lang": "en"})
        check_turn(rig, await rig.driver.user_says("Approve Asha's leave."))
        asked = tool_results(llm.captured_inputs[-1])["decide_leave"]
        before = COMPANY["payslips"]["BB-1046"][-1]
        assert "LV-2412" in asked and "1 day(s) become loss of pay" in asked
        assert inr(before["net_pay"]) in asked
        assert "leave.decide" not in [m["move"] for m in _moves(rig)]

        yes = await rig.driver.user_says("Yes.")
        check_turn(rig, yes, units=1)
        decide = _moves(rig)[-1]
        assert decide["move"] == "leave.decide"
        assert decide["args"] == {"request_id": "LV-2412", "decision": "approve"}
        await _answer(rig, [decide], "Asha Chavan's leave approved")
        outcome = await rig.driver.user_idle()
        brain = _brain(rig)
        feb = brain.books.slip("BB-1046", "2026-02")
        assert feb is not None and feb["lop_days"] == 1
        assert outcome.text.startswith("Done — Asha Chavan's leave is approved.")
        assert inr(feb["net_pay"]) in outcome.text
        assert brain.books.draft["net_pay"] == FEB["net_pay"] - (before["net_pay"] - feb["net_pay"])


async def test_support_fixes_imrans_claim_after_a_yes() -> None:
    llm = _support_llm()
    async with demo("payroll_app", llm) as rig:
        await rig.driver.start_session(init={"landing": "/", "lang": "en"})
        check_turn(rig, await rig.driver.user_says("Fix Imran's claim."))
        asked = tool_results(llm.captured_inputs[-1])["fix_claim"]
        assert "RB-3108" in asked and "₹4,850" in asked and "₹4,580" in asked
        check_turn(rig, await rig.driver.user_says("Yes, fix it."), units=1)
        fix = _moves(rig)[-1]
        assert fix["move"] == "claim.fix" and fix["args"] == {"claim_id": "RB-3108", "amount": 4580}
        await _answer(rig, [fix])
        await rig.driver.user_idle()
        books = _brain(rig).books
        assert books.feb_reimbursements("BB-1032") == 4580
        assert books.draft["reimbursements"] == FEB["reimbursements"] + 4580


async def test_support_hands_off_with_a_written_ticket_on_screen() -> None:
    llm = _support_llm()
    async with demo("payroll_app", llm) as rig:
        await rig.driver.start_session(init={"landing": "/help", "lang": "en"})
        check_turn(rig, await rig.driver.user_says("I need someone to look at our PF upload."))
        draft = _moves(rig)[-1]
        assert draft["move"] == "ticket.draft"
        assert draft["args"]["subject"] == "PF ECR upload for February"
        assert "PF ECR" in draft["args"]["summary"]
        check_turn(rig, await rig.driver.user_says("Yes, send it."), units=1)
        submit = _moves(rig)[-1]
        assert submit["move"] == "ticket.submit"
        await _answer(rig, [submit])
        sent = await rig.driver.user_idle()
        assert "TK-1208" in sent.text


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
