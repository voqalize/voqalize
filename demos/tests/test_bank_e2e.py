"""Anvaya Bank (fictional) — the brain over the real wire, the model scripted.

One brain, four landing pages (CONTRACT.md): the banking assistant in the app,
the account-opening guide, the card advisor and the loan advisor. Each test
drives one landing's main flow and asserts what reached the page (Stage moves),
what the model was told (tool results, notes), and what was spoken.

Run: ``cd demos && uv run pytest tests/test_bank_e2e.py``
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedOpenAI, reply, reply_and_call, tool_results_of

from ._harness import (
    DemoRig,
    check_greeting,
    check_turn,
    check_voice_pair,
    demo,
    tools_within_budget,
)

discover()

from voqalize_demos._loaded.bank import bank as b  # noqa: E402
from voqalize_demos._loaded.bank import bankmath as m  # noqa: E402
from voqalize_demos._loaded.bank.brain import BankBrain, classify, mode_of, spend_txns  # noqa: E402
from voqalize_demos._loaded.bank.forms import OPEN_STEPS  # noqa: E402
from voqalize_demos._loaded.bank.prompt import greeting  # noqa: E402

PERSONA = json.loads((b.ROOT / "persona.json").read_text("utf-8"))


def _moves(rig: DemoRig) -> list[dict[str, Any]]:
    return [dict(c["payload"]) for c in rig.driver.ui_commands if c.get("command") == "stage_move"]


def _move(rig: DemoRig, move: str) -> dict[str, Any]:
    hits = [p for p in _moves(rig) if p["move"] == move]
    assert hits, f"no {move} move; sent: {[p['move'] for p in _moves(rig)]}"
    return hits[-1]


async def _result(rig: DemoRig, move: dict[str, Any], outcome: str, detail: str) -> None:
    await rig.driver.send_ui_event(
        "stage_result",
        {"call_ref": move["call_ref"], "move": move["move"], "outcome": outcome, "detail": detail},
    )
    await asyncio.sleep(0.1)


def _results(llm: ScriptedOpenAI, name: str) -> list[str]:
    return tool_results_of(llm.captured_inputs[-1], name)


# ─── The persona is one file ─────────────────────────────────────────────────


def test_the_persona_file_drives_name_voice_and_languages() -> None:
    assert b.voice_for("en") == PERSONA["voices"]["en"]
    assert b.voice_for("hi") == PERSONA["voices"]["hi"]
    assert set(b.LANGUAGES) == {"en", "hi"}
    for mode in ("banking", "account", "cards", "loans", "home"):
        assert PERSONA["name"] in greeting(mode, "en", True)
        assert PERSONA["spoken_names"]["hi"] in greeting(mode, "hi", True)


def test_modes_follow_the_screen() -> None:
    assert mode_of("credit_card") == "banking"
    assert mode_of("open_account") == "account"
    assert mode_of("cards_emi") == "cards"
    assert mode_of("loan_apply") == "loans"
    assert mode_of("home") == "home"


def test_yes_and_no_are_heard_in_both_languages() -> None:
    for said in ("Yes.", "yes please", "Go ahead", "haan", "हाँ", "हाँ जी", "kar do", "theek hai"):
        assert classify(said) == "yes", said
    for said in ("No.", "cancel it", "nahi", "नहीं", "rehne do", "wait"):
        assert classify(said) == "no", said
    for said in ("Yes but what is the fee?", "can you tell me more about it first please"):
        assert classify(said) is None, said


# ─── Maths: the numbers the page shows (frontend/src/lib/bankmath.ts) ─────────


def test_card_emi_and_ranking_numbers() -> None:
    row = m.card_emi(64990, 6)
    assert row.rate == 14.0
    assert row.emi == m.rnd(m.emi(64990, 14.0, 6))
    assert row.processing_fee == 650 and row.gst_on_fee == 117
    profile = m.customer_profile()
    assert all(v % 100 == 0 for v in profile.values())
    ranked = m.rank_cards(profile)
    assert {v.card_id for v in ranked} == set(b.CARD_IDS)
    assert ranked == sorted(ranked, key=lambda v: (-v.net_yearly, v.card_id))
    el = m.loan_eligibility(
        b.loan_product("personal") or {}, monthly_income=100000, existing_emis=10000
    )
    assert el.max_emi == 40000 and el.max_amount % 10000 == 0
    gold = m.loan_eligibility(b.loan_product("gold") or {}, gold_grams=50)
    assert gold.max_amount == 270000  # 50 g at ₹7,200 a gram, 75% of it


# ─── Banking: answers from her data, opens the screen, confirms changes ──────


def _banking_llm() -> ScriptedOpenAI:
    return ScriptedOpenAI(
        {
            "What was this 4,999 charge?": [
                reply_and_call("Let me find it.", "explain_transaction", amount=4999),
                reply("That's your StreamBox annual plan, renewed on your Spark card."),
            ],
            "How much did I spend on food last month?": [
                reply_and_call(
                    "Here's last month.", "spending", month="last_month", category="food"
                ),
                reply("You spent that on food last month."),
            ],
            "Block my debit card.": [
                reply_and_call("Sure.", "request_change", kind="card_block", card="debit"),
                reply("It's on your screen: block the debit card ending 7712. Shall I go ahead?"),
            ],
        }
    )


async def test_banking_answers_from_her_data_and_confirms_a_block() -> None:
    llm = _banking_llm()
    async with demo("bank", llm) as rig:
        greeting_turn = await rig.driver.start_session(
            init={"landing": "banking", "path": "/app", "lang": "en", "signed_in": True}
        )
        check_greeting(rig, greeting_turn)
        check_voice_pair(rig, voice=PERSONA["voices"]["en"], language="en")
        assert "Aditi" in greeting_turn.text and PERSONA["name"] in greeting_turn.text

        with tools_within_budget():
            t1 = await rig.driver.user_says("What was this 4,999 charge?")
        check_turn(rig, t1)
        assert _move(rig, "txn.open")["args"] == {"txn_id": "T0197"}
        explained = _results(llm, "explain_transaction")[-1]
        assert "StreamBox" in explained and "annual" in explained.lower()

        t2 = await rig.driver.user_says("How much did I spend on food last month?")
        check_turn(rig, t2)
        last = b.shift_month(b.month_key(b.today()), -1)
        assert _move(rig, "insights.show")["args"] == {"month": last, "category": "food"}
        food = sum(t["amount"] for t in spend_txns(last) if t["category"] == "food")
        said = _results(llm, "spending")[-1]
        assert f"Food & dining: {b.inr(food)}" in said

        t3 = await rig.driver.user_says("Block my debit card.")
        check_turn(rig, t3)
        ask = _move(rig, "confirm.ask")
        assert ask["args"]["kind"] == "card_block" and ask["args"]["card"] == "debit"
        assert ask["args"]["action_id"] == "A1"
        assert "confirm.answer" not in [p["move"] for p in _moves(rig)], "changed before a yes"

        # A plain yes: pressed by the brain itself, no model turn.
        asked = len(llm.requests)
        t4 = await rig.driver.user_says("Yes.")
        check_turn(rig, t4)
        assert len(llm.requests) == asked
        answer = _move(rig, "confirm.answer")
        assert answer["args"] == {"action_id": "A1", "yes": True}

        await _result(
            rig, answer, "applied", "done, reference ANVCB482113: Debit card ending 7712 blocked"
        )
        brain = rig.brain
        assert isinstance(brain, BankBrain)
        assert brain.cards["debit"]["controls"]["blocked"] is True
        idle = await rig.driver.user_idle()
        assert "ANVCB482113" in idle.text and "Done" in idle.text


async def test_a_change_the_page_refuses_is_never_said_done() -> None:
    llm = ScriptedOpenAI(
        {
            "Raise my debit card ATM limit to 5 lakh.": [
                reply_and_call(
                    "Let me check.",
                    "request_change",
                    kind="card_limit",
                    card="debit",
                    control="atm_daily",
                    value="500000",
                ),
                reply("The most I can set is one lakh."),
            ],
        }
    )
    async with demo("bank", llm) as rig:
        await rig.driver.start_session(init={"landing": "banking", "lang": "en", "signed_in": True})
        await rig.driver.user_says("Raise my debit card ATM limit to 5 lakh.")
        assert "confirm.ask" not in [p["move"] for p in _moves(rig)]
        assert "at most ₹1,00,000" in _results(llm, "request_change")[-1]


async def test_signed_out_visitor_data_stays_private() -> None:
    llm = ScriptedOpenAI(
        {
            "What's my balance?": [
                reply_and_call("Let me see.", "card_details", card="credit"),
                reply("Please sign in first."),
            ]
        }
    )
    async with demo("bank", llm) as rig:
        await rig.driver.start_session(init={"landing": "home", "lang": "en", "signed_in": False})
        await rig.driver.user_says("What's my balance?")
        assert _moves(rig) == []
        assert "not signed in" in _results(llm, "card_details")[-1]


# ─── Account opening: the form fills as she talks ────────────────────────────


async def test_account_opening_fills_the_form_and_submits_on_yes() -> None:
    llm = ScriptedOpenAI(
        {
            "I'm Priya Menon, born 12 March 1994, female.": [
                reply_and_call(
                    "Thanks, Priya.",
                    "fill_account_form",
                    full_name="Priya Menon",
                    date_of_birth="1994-03-12",
                    gender="female",
                    mobile="98450 12345",
                    email="priya.m@example.com",
                ),
                reply("Now your address: where do you live?"),
            ],
            "My PAN is ABCDE12F.": [
                reply_and_call(
                    "Noted.", "fill_account_form", pan="ABCDE12F", aadhaar="234567891234"
                ),
                reply("That PAN looks short; can you say it again?"),
            ],
            "Submit it.": reply("Shall I submit?"),
            "Yes.": [
                reply_and_call("Submitting.", "submit_application", form="open_account"),
                reply_and_call("Submitting.", "submit_application", form="open_account"),
            ],
        }
    )
    async with demo("bank", llm) as rig:
        g = await rig.driver.start_session(
            init={"landing": "account", "path": "/open-account", "lang": "en"}
        )
        assert "savings account" in g.text
        await rig.driver.user_says("I'm Priya Menon, born 12 March 1994, female.")
        fills = [p["args"] for p in _moves(rig) if p["move"] == "form.fill"]
        assert {"form": "open_account", "field": "mobile", "value": "9845012345"} in fills
        assert [f["field"] for f in fills] == [
            "full_name",
            "date_of_birth",
            "gender",
            "mobile",
            "email",
        ]
        assert _move(rig, "form.step")["args"] == {"form": "open_account", "step": 2}
        assert "Still needed (step 2)" in _results(llm, "fill_account_form")[-1]

        await rig.driver.user_says("My PAN is ABCDE12F.")
        said = _results(llm, "fill_account_form")[-1]
        assert "pan (a PAN like" in said and "Filled: aadhaar" in said
        assert {"form": "open_account", "field": "pan", "value": "ABCDE12F"} not in [
            p["args"] for p in _moves(rig) if p["move"] == "form.fill"
        ]

        # Submitting with fields missing is refused by the brain; nothing is pressed.
        await rig.driver.user_says("Submit it.")
        await rig.driver.user_says("Yes.")
        assert "form.submit" not in [p["move"] for p in _moves(rig)]

        # The page reports the rest filled by hand; now a yes submits.
        await rig.driver.send_ui_event(
            "form_changed",
            {
                "form": "open_account",
                "step": 6,
                "filled": [f for _, _, fs in OPEN_STEPS for f in fs],
                "missing": [],
                "by": "visitor",
            },
        )
        await asyncio.sleep(0.1)
        await rig.driver.user_says("Yes.")
        assert any("still needed" in r for r in _results(llm, "submit_application"))
        submit = _move(rig, "form.submit")
        assert submit["args"] == {"form": "open_account"}
        await _result(rig, submit, "applied", "submitted, reference ANV-SB-104233")
        idle = await rig.driver.user_idle()
        assert "ANV-SB-104233" in idle.text


# ─── Cards: ranked from spend, compare, EMI ──────────────────────────────────


async def test_card_advisor_ranks_from_spend_and_plans_an_emi() -> None:
    llm = ScriptedOpenAI(
        {
            "About 8,000 on food and 6,000 online, 2,000 on fuel.": [
                reply_and_call(
                    "Let me compare.", "rank_cards", dining=8000, online=6000, fuel=2000
                ),
                reply("Spark comes out on top for you."),
            ],
            "Convert my laptop purchase to EMI.": [
                reply_and_call(
                    "Here are the plans.", "plan_emi", txn_id=_laptop(), tenure_months=6
                ),
                reply("Six months is about eleven thousand a month."),
            ],
        }
    )
    async with demo("bank", llm) as rig:
        await rig.driver.start_session(
            init={"landing": "cards", "path": "/cards", "lang": "en", "signed_in": True}
        )
        await rig.driver.user_says("About 8,000 on food and 6,000 online, 2,000 on fuel.")
        compare = _move(rig, "cards.compare")["args"]
        profile = dict.fromkeys(b.CARD_CATEGORIES, 0.0) | {
            "dining": 8000.0,
            "online": 6000.0,
            "fuel": 2000.0,
        }
        top = [v.card_id for v in m.rank_cards(profile)[:3]]
        assert compare["card_ids"] == top and compare["dining"] == 8000
        ranking = _results(llm, "rank_cards")[-1]
        assert ranking.splitlines()[1].startswith("1. ")

        await rig.driver.user_says("Convert my laptop purchase to EMI.")
        plan = _move(rig, "emi.plan")["args"]
        assert plan == {"txn_id": _laptop(), "tenure_months": 6}
        row = m.card_emi(64990, 6)
        assert f"EMI {b.inr(row.emi)}" in _results(llm, "plan_emi")[-1]


def _laptop() -> str:
    return next(t["id"] for t in b.CUSTOMER["transactions"] if t["amount"] == 64990)


# ─── Loans: eligibility, EMI with the maths, the lead card ───────────────────


async def test_loan_advisor_works_out_eligibility_emi_and_ends_in_a_lead() -> None:
    llm = ScriptedOpenAI(
        {
            "I earn 1.2 lakh a month and pay 15,000 in EMIs.": [
                reply_and_call(
                    "Let me work it out.",
                    "loan_eligibility",
                    loan_type="home",
                    monthly_income=120000,
                    existing_emis=15000,
                ),
                reply("You could borrow up to that."),
            ],
            "What's the EMI on 50 lakh for 20 years?": [
                reply_and_call(
                    "Here's the working.",
                    "loan_emi",
                    loan_type="home",
                    amount=5000000,
                    tenure_months=240,
                ),
                reply("About forty-four thousand a month."),
            ],
            "Apply. I'm Rohan Gupta, 9876543210, Pune.": [
                reply_and_call(
                    "Putting it in.",
                    "fill_loan_application",
                    loan_type="home",
                    full_name="Rohan Gupta",
                    mobile="9876543210",
                    city="Pune",
                    employment="salaried",
                    monthly_income=120000,
                    existing_emis=15000,
                    amount=5000000,
                    tenure_months=240,
                    property_value=7000000,
                    preferred_time="evening",
                ),
                reply("All filled in. Shall I submit it?"),
            ],
            "Yes, submit.": reply_and_call("Submitting.", "submit_application", form="loan_apply"),
        }
    )
    async with demo("bank", llm) as rig:
        await rig.driver.start_session(init={"landing": "loans", "path": "/loans", "lang": "en"})
        await rig.driver.user_says("I earn 1.2 lakh a month and pay 15,000 in EMIs.")
        home = b.loan_product("home") or {}
        el = m.loan_eligibility(home, monthly_income=120000, existing_emis=15000)
        assert f"up to {b.inr(el.max_amount)}" in _results(llm, "loan_eligibility")[-1]
        assert _move(rig, "loan.eligibility")["args"]["monthly_income"] == 120000

        await rig.driver.user_says("What's the EMI on 50 lakh for 20 years?")
        emi = m.rnd(m.emi(5000000, home["rate_typical"], 240))
        assert f"EMI {b.inr(emi)}" in _results(llm, "loan_emi")[-1]
        assert _move(rig, "loan.calc")["args"] == {
            "loan_type": "home", "amount": 5000000, "tenure_months": 240, "rate": home["rate_typical"]
        }  # fmt: skip

        await rig.driver.user_says("Apply. I'm Rohan Gupta, 9876543210, Pune.")
        assert "Everything is filled" in _results(llm, "fill_loan_application")[-1]
        await rig.driver.user_says("Yes, submit.")
        submit = _move(rig, "form.submit")
        await _result(rig, submit, "applied", "submitted, reference ANV-LD-552210: qualified lead")
        idle = await rig.driver.user_idle()
        assert (
            "ANV-LD-552210" in idle.text
            and "home loan team" in idle.text
            and "evening" in idle.text
        )


# ─── Languages ───────────────────────────────────────────────────────────────


async def test_hindi_from_the_toggle_sets_both_legs_and_greets_in_hindi() -> None:
    async with demo("bank", ScriptedOpenAI()) as rig:
        g = await rig.driver.start_session(init={"landing": "loans", "lang": "hi"})
        check_voice_pair(rig, voice=PERSONA["voices"]["hi"], language="hi")
        assert PERSONA["spoken_names"]["hi"] in g.text


async def test_the_toggle_mid_call_moves_both_legs_and_the_dock() -> None:
    llm = ScriptedOpenAI()
    async with demo("bank", llm) as rig:
        await rig.driver.start_session(init={"landing": "home", "lang": "en"})
        await rig.driver.send_ui_event("language_requested", {"language": "hi", "by": "visitor"})
        await asyncio.sleep(0.2)
        check_voice_pair(rig, voice=PERSONA["voices"]["hi"], language="hi")
        assert rig.command("language_changed") == {"language": "hi"}
        idle = await rig.driver.user_idle()
        assert "हिंदी" in idle.text


async def test_page_moves_switch_the_job() -> None:
    llm = ScriptedOpenAI({"hello": reply("Hi.")})
    async with demo("bank", llm) as rig:
        await rig.driver.start_session(init={"landing": "banking", "lang": "en", "signed_in": True})
        await rig.driver.send_ui_event(
            "page_viewed", {"path": "/cards", "screen": "cards", "signed_in": True, "by": "visitor"}
        )
        await asyncio.sleep(0.1)
        await rig.driver.user_says("hello")
        text = json.dumps(llm.captured_inputs[-1], ensure_ascii=False)
        assert "the credit-card advisor" in text
