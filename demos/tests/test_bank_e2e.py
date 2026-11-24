"""Global Bank (fictional) — the brain over the real wire, the model scripted.

One brain, four landing pages (CONTRACT.md): the banking assistant in the app,
the account-opening guide, the card advisor and the loan advisor. Each test
drives one landing's main flow and asserts what reached the page (Stage moves),
what the model was told (tool results, notes), and what was spoken.

Run: ``cd demos && uv run pytest tests/test_bank_e2e.py``
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from typing import Any

import pytest
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedOpenAI, reply, reply_and_call, tool_results_of

from voqalize.conformance import VoqalizeDriver
from voqalize.sdk.wire import ConfigureFrame

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


@pytest.fixture(autouse=True)
def _no_call_carried_between_tests() -> Iterator[None]:
    """Every test here opens the same session id, and a dropped call is held for
    a redial to rejoin (CONTRACT.md, Redial): clear the store around each test,
    so no test rejoins the one before it. Real session ids never repeat."""
    from voqalize_demos._loaded.bank.brain import REJOIN

    REJOIN.clear()
    yield
    REJOIN.clear()


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


_BANKING = {"landing": "banking", "path": "/app", "lang": "en", "signed_in": True}


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
    # The same figures frontend/src/lib/bankmath.test.ts pins for the page.
    assert profile == {
        "dining": 13700,
        "online": 44000,
        "groceries": 7300,
        "travel": 22000,
        "fuel": 5400,
        "utilities": 3500,
        "other": 100,
    }
    assert [(v.card_id, v.net_yearly) for v in m.rank_cards(profile)] == [
        ("prism", 49048), ("voyage", 38776), ("daily", 27520), ("spark", 13479), ("fuelone", 9114)
    ]  # fmt: skip
    assert m.card_emi(64990, 6).emi == 11278
    assert m.fd_quote(100000, 12, "cumulative")["maturity"] == 107291
    ranked = m.rank_cards(profile)
    assert {v.card_id for v in ranked} == set(b.CARD_IDS)
    assert ranked == sorted(ranked, key=lambda v: (-v.net_yearly, v.card_id))
    # Signed in, her income (₹1,42,500) is below Prism's ₹2,00,000: it ranks last, marked.
    income = b.CUSTOMER["profile"]["monthly_income"]
    assert [(v.card_id, v.net_yearly, v.below_income) for v in m.rank_cards(profile, income)] == [
        ("voyage", 38776, False),
        ("daily", 27520, False),
        ("spark", 13479, False),
        ("fuelone", 9114, False),
        ("prism", 49048, True),
    ]
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
            rig, answer, "applied", "done, reference GLBCB482113: Debit card ending 7712 blocked"
        )
        brain = rig.brain
        assert isinstance(brain, BankBrain)
        assert brain.cards["debit"]["controls"]["blocked"] is True
        idle = await rig.driver.user_idle()
        assert "GLBCB482113" in idle.text and "Done" in idle.text


# ─── B1: "show me my accounts" is answered with her balances, never silence ──

_SB, _CA = (b.inr(a["balance"]) for a in b.CUSTOMER["accounts"])


async def test_show_me_my_accounts_rings_them_and_reads_each_balance() -> None:
    """The owner's words on a signed-in dashboard: the accounts are ringed on
    screen and both balances come back to be read in the same turn."""
    llm = ScriptedOpenAI(
        {
            "Can you show me my accounts?": [
                reply_and_call("Of course, here are your accounts.", "my_accounts"),
                reply(f"Your savings has {_SB}, and your current account has {_CA}."),
            ],
        }
    )
    async with demo("bank", llm) as rig:
        await rig.driver.start_session(init=_BANKING)
        with tools_within_budget():
            t = await rig.driver.user_says("Can you show me my accounts?")
        check_turn(rig, t)
        assert _move(rig, "accounts.show")["args"] == {}
        said = _results(llm, "my_accounts")[-1]
        assert f"available balance {_SB}" in said and f"available balance {_CA}" in said
        assert "Read her each account's balance" in said
        # Answered in the same turn: the second request carried the balances.
        assert _SB in t.text and _CA in t.text
        assert "ending 4821 has" not in t.text, "the brain's floor spoke over a model that answered"
        await _result(rig, _move(rig, "accounts.show"), "applied", "both balances ringed")
        assert "nav.open" not in [p["move"] for p in _moves(rig)]


async def test_an_already_open_dashboard_still_gets_the_balances_said() -> None:
    """B1 as it happened: the model promised, opened the dashboard that was
    already open and said nothing more. The tool now reads back what the screen
    holds, and when the model still says nothing after it, the brain says her
    balances itself: never a promise and then silence."""
    llm = ScriptedOpenAI(
        {
            "Can you show me my accounts?": [
                reply_and_call(
                    "Of course, I'll open your accounts.", "open_screen", screen="dashboard"
                ),
                reply(""),
            ],
        }
    )
    async with demo("bank", llm) as rig:
        await rig.driver.start_session(init=_BANKING)
        t = await rig.driver.user_says("Can you show me my accounts?")
        check_turn(rig, t)
        opened = _move(rig, "nav.open")
        assert opened["args"] == {"screen": "dashboard"}
        said = _results(llm, "open_screen")[-1]
        assert _SB in said and _CA in said and "What it shows" in said
        assert len(llm.requests) == 2, "open_screen's result is read in the same turn"
        assert f"savings account ending 4821 has {_SB}" in t.text
        assert f"current account ending 6630 has {_CA}" in t.text
        # The page answers as it did on the call; nothing more is owed or said wrong.
        await _result(rig, opened, "applied", "dashboard is already open")
        brain = rig.brain
        assert isinstance(brain, BankBrain) and brain._say_next is None


async def test_a_move_the_page_refuses_is_still_answered_aloud() -> None:
    llm = ScriptedOpenAI(
        {
            "Open my statements.": [
                reply_and_call("Opening them.", "open_screen", screen="statements"),
                reply("Your statements are on screen."),
            ],
        }
    )
    async with demo("bank", llm) as rig:
        await rig.driver.start_session(init=_BANKING)
        await rig.driver.user_says("Open my statements.")
        await _result(
            rig, _move(rig, "nav.open"), "refused", "screen: the statements screen did not open"
        )
        idle = await rig.driver.user_idle()
        assert "didn't come up on your screen" in idle.text


async def test_only_my_bank_accounts_shows_savings_and_current_together() -> None:
    llm = ScriptedOpenAI(
        {
            "Remove the credit card and only show me my bank accounts.": [
                reply_and_call("Sure.", "find_transactions", account="bank", period="last_30_days"),
                reply("Here are your savings and current account transactions."),
            ],
        }
    )
    async with demo("bank", llm) as rig:
        await rig.driver.start_session(init=_BANKING)
        await rig.driver.user_says("Remove the credit card and only show me my bank accounts.")
        args = _move(rig, "txn.find")["args"]
        assert args["account"] == "bank" and args["label"].startswith("Savings and current")
        both = b.filter_txns(b.TxnFilter(account="bank", from_days_ago=29, to_days_ago=0))
        assert {t["account"] for t in both} == {"sb", "ca"}
        said = _results(llm, "find_transactions")[-1]
        assert said.startswith(f"{len(both)} transactions")
        assert "credit card," not in said and "Not done" not in said


async def test_a_language_switch_is_said_in_the_new_language() -> None:
    llm = ScriptedOpenAI(
        {"Can we talk in Hindi?": reply_and_call("Sure.", "set_language", language="hi")}
    )
    async with demo("bank", llm) as rig:
        await rig.driver.start_session(init=_BANKING)
        await rig.driver.user_says("Can we talk in Hindi?")
        await asyncio.sleep(0.2)
        check_voice_pair(rig, voice=PERSONA["voices"]["hi"], language="hi")
        idle = await rig.driver.user_idle()
        assert "हिंदी" in idle.text


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
        await _result(rig, submit, "applied", "submitted, reference GLB-SB-104233")
        idle = await rig.driver.user_idle()
        assert "GLB-SB-104233" in idle.text


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
        income = b.CUSTOMER["profile"]["monthly_income"]
        top = [v.card_id for v in m.rank_cards(profile, income)[:3]]
        assert compare["card_ids"] == top and compare["dining"] == 8000
        ranking = _results(llm, "rank_cards")[-1]
        assert ranking.splitlines()[2].startswith("1. ")  # after spend and income lines

        await rig.driver.user_says("Convert my laptop purchase to EMI.")
        plan = _move(rig, "emi.plan")["args"]
        assert plan == {"txn_id": _laptop(), "tenure_months": 6}
        row = m.card_emi(64990, 6)
        assert f"EMI {b.inr(row.emi)}" in _results(llm, "plan_emi")[-1]


async def test_her_real_spend_ranks_cards_she_qualifies_for_first() -> None:
    llm = ScriptedOpenAI(
        {
            "Which card suits how I spend?": [
                reply_and_call("Let me look at your spend.", "rank_cards", use_my_spend=True),
                reply("Voyage gives you the most of the cards you qualify for."),
            ],
        }
    )
    async with demo("bank", llm) as rig:
        await rig.driver.start_session(
            init={"landing": "cards", "path": "/cards", "lang": "en", "signed_in": True}
        )
        await rig.driver.user_says("Which card suits how I spend?")
        # Prism has the highest raw value but needs ₹2,00,000 a month; she earns ₹1,42,500.
        assert _move(rig, "cards.compare")["args"]["card_ids"] == ["voyage", "daily", "spark"]
        ranking = _results(llm, "rank_cards")[-1]
        assert "1. Global Voyage" in ranking
        prism = next(x for x in ranking.splitlines() if "Prism" in x)
        assert prism.startswith("5. ") and "Income below requirement" in prism
        assert "₹2,00,000" in prism


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
        await _result(rig, submit, "applied", "submitted, reference GLB-LD-552210: qualified lead")
        idle = await rig.driver.user_idle()
        assert (
            "GLB-LD-552210" in idle.text
            and "home loan team" in idle.text
            and "evening" in idle.text
        )


# ─── Selling on the public pages (B2): few questions, the best option, a nudge ─


async def test_home_loan_sales_asks_then_pitches_the_plan_with_its_money() -> None:
    """On the home loan page Arjun knows the product, asks only income and EMIs,
    then the property price; recommend_loan puts the eligibility check and the
    calculator on screen with her numbers and returns the plan: the amount the
    LTV allows, the EMI, the interest, eligibility and a shorter tenure's saving.
    A yes to applying fills the application with everything already said."""
    llm = ScriptedOpenAI(
        {
            "I want a home loan.": reply(
                "Happy to help. What's your monthly take-home, and do you pay any EMIs now?"
            ),
            "1.5 lakh a month, a 10,000 car EMI.": reply(
                "Got it. And roughly what does the flat cost?"
            ),
            "About 75 lakh.": [
                reply_and_call(
                    "Let me work out the best plan for you.",
                    "recommend_loan",
                    loan_type="home",
                    monthly_income=150000,
                    existing_emis=10000,
                    property_value=7500000,
                ),
                reply(
                    "We can lend sixty lakh over twenty years at 8.85%, an EMI of about fifty-three "
                    "thousand, well within your budget. Shall I start your application?"
                ),
            ],
            "Yes, I'm Kavya Iyer, 9812345678, Bengaluru, call me in the morning.": [
                reply_and_call(
                    "Putting that in.",
                    "fill_loan_application",
                    loan_type="home",
                    full_name="Kavya Iyer",
                    mobile="9812345678",
                    city="Bengaluru",
                    employment="salaried",
                    monthly_income=150000,
                    existing_emis=10000,
                    amount=6000000,
                    tenure_months=240,
                    property_value=7500000,
                    preferred_time="morning",
                ),
                reply("All filled in. Shall I submit it?"),
            ],
        }
    )
    async with demo("bank", llm) as rig:
        await rig.driver.start_session(
            init={"landing": "loans", "path": "/loans/home", "lang": "en"}
        )
        await rig.driver.user_says("I want a home loan.")
        first = json.dumps(llm.captured_inputs[-1], ensure_ascii=False)
        assert "the Home loan page" in first and "loan salesperson" in first
        await rig.driver.user_says("1.5 lakh a month, a 10,000 car EMI.")
        assert not [p for p in _moves(rig) if p["move"].startswith("loan.")]  # asks first

        await rig.driver.user_says("About 75 lakh.")
        home = b.loan_product("home") or {}
        plan = m.loan_plan(home, monthly_income=150000, existing_emis=10000, asset_value=7500000)
        assert plan.amount == 6000000 and plan.tenure_months == 240 and plan.fits  # 80% of 75 lakh
        el = _move(rig, "loan.eligibility")["args"]
        assert el["monthly_income"] == 150000 and el["existing_emis"] == 10000
        assert _move(rig, "loan.calc")["args"] == {
            "loan_type": "home", "amount": 6000000, "tenure_months": 240, "rate": home["rate_typical"]
        }  # fmt: skip
        pitch = _results(llm, "recommend_loan")[-1]
        assert f"EMI {b.inr(plan.emi)}" in pitch
        assert f"total interest {b.inr(plan.total_interest)}" in pitch
        assert f"up to {b.inr(plan.max_emi or 0)}" in pitch  # eligibility
        assert plan.shorter is not None and f"save {b.inr(plan.shorter[2])}" in pitch
        assert "their own share is" not in pitch and "own share ₹15,00,000" in pitch
        assert "offer to start the application" in pitch

        await rig.driver.user_says(
            "Yes, I'm Kavya Iyer, 9812345678, Bengaluru, call me in the morning."
        )
        assert "Everything is filled" in _results(llm, "fill_loan_application")[-1]


async def test_a_loan_pitch_asks_for_what_is_missing_before_any_number() -> None:
    """recommend_loan without the income (or the amount) refuses, naming the one
    question to ask, and puts nothing on screen: no invented numbers."""
    llm = ScriptedOpenAI(
        {
            "Car loan please.": [
                reply_and_call("Sure.", "recommend_loan", loan_type="car"),
                reply("What's your monthly take-home and any EMIs?"),
            ],
            "80,000 a month, no EMIs.": [
                reply_and_call("Thanks.", "recommend_loan", loan_type="car", monthly_income=80000),
                reply("And the car's on-road price?"),
            ],
        }
    )
    async with demo("bank", llm) as rig:
        await rig.driver.start_session(init={"landing": "loans", "path": "/loans", "lang": "en"})
        await rig.driver.user_says("Car loan please.")
        assert "monthly take-home income" in _results(llm, "recommend_loan")[-1]
        await rig.driver.user_says("80,000 a month, no EMIs.")
        assert "on-road price" in _results(llm, "recommend_loan")[-1]
        assert not [p for p in _moves(rig) if p["move"].startswith("loan.")]


async def test_card_sales_asks_income_and_spend_then_pitches_one_card() -> None:
    """On /cards Arjun asks how they spend and what they earn, then
    recommend_card shows the pick beside the runner-up, best first, and returns
    what it is worth to them a year after fees, that they qualify, how much more
    than the runner-up, and the nudge to apply. A card above their income is not
    pitched. A yes opens that card's application, prefilled."""
    llm = ScriptedOpenAI(
        {
            "I'm looking for a credit card.": reply(
                "Lovely. Roughly how much do you put on a card a month, and on what? And your "
                "monthly take-home?"
            ),
            "About 40,000, mostly online shopping. I earn 70,000.": [
                reply_and_call(
                    "Let me find the one that pays you back most.",
                    "recommend_card",
                    monthly_income=70000,
                    total_monthly=40000,
                    mostly_on="online",
                ),
                reply(
                    "Daily Cashback suits you best, worth about thirteen thousand a year with the "
                    "fee waived. Shall I start your application? It takes two minutes."
                ),
            ],
            "Yes, go on.": [
                reply_and_call("Opening it.", "open_screen", screen="cards_apply", id="daily"),
                reply_and_call(
                    "Putting in what I know.",
                    "fill_card_application",
                    card_id="daily",
                    monthly_income=70000,
                ),
                reply("Your name as on your PAN?"),
            ],
        }
    )
    async with demo("bank", llm) as rig:
        await rig.driver.start_session(init={"landing": "cards", "path": "/cards", "lang": "en"})
        await rig.driver.user_says("I'm looking for a credit card.")
        assert not [p for p in _moves(rig) if p["move"] == "cards.compare"]  # asks first

        await rig.driver.user_says("About 40,000, mostly online shopping. I earn 70,000.")
        profile = dict.fromkeys(b.CARD_CATEGORIES, 0.0) | {"online": 20000.0, "other": 20000.0}
        ranked = [v for v in m.rank_cards(profile, 70000) if not v.below_income]
        best, second = ranked[0], ranked[1]
        compare = _move(rig, "cards.compare")["args"]
        assert compare["card_ids"][0] == best.card_id and compare["online"] == 20000
        pitch = _results(llm, "recommend_card")[-1]
        name = (b.card_product(best.card_id) or {})["name"]
        assert f"RECOMMEND: {name}" in pitch
        assert f"about {b.inr(best.net_yearly)} a year" in pitch
        assert f"{b.inr(best.yearly_rewards)} in rewards" in pitch
        assert f"they earn {b.inr(70000)}" in pitch  # eligibility
        assert f"{b.inr(best.net_yearly - second.net_yearly)} more" in pitch
        assert "half on online" in pitch
        assert "Prism" not in pitch.split("Not offered")[0]  # needs ₹2,00,000 a month
        assert f"open_screen cards_apply id {best.card_id}" in pitch

        await rig.driver.user_says("Yes, go on.")
        assert _move(rig, "nav.open")["args"] == {"screen": "cards_apply", "id": "daily"}
        filled = [p["args"] for p in _moves(rig) if p["move"] == "form.fill"]
        assert {"form": "card_apply", "field": "card_id", "value": "daily"} in filled


async def test_a_card_pitch_needs_the_income_first() -> None:
    llm = ScriptedOpenAI(
        {
            "I spend 15,000 on fuel a month.": [
                reply_and_call("Nice.", "recommend_card", fuel=15000),
                reply("And your monthly take-home?"),
            ],
        }
    )
    async with demo("bank", llm) as rig:
        await rig.driver.start_session(init={"landing": "cards", "path": "/cards", "lang": "en"})
        await rig.driver.user_says("I spend 15,000 on fuel a month.")
        assert "monthly take-home income" in _results(llm, "recommend_card")[-1]
        assert not [p for p in _moves(rig) if p["move"] == "cards.compare"]


def test_the_signed_in_app_job_is_untouched_by_selling() -> None:
    """B2 changed the public pages only: the banking job's note is the one it was."""
    brain = BankBrain.__new__(BankBrain)
    brain.screen, brain.signed_in, brain.mode, brain.path = "dashboard", True, "banking", "/app"
    assert brain._screen_note() == (
        "[On screen: dashboard. Signed in: yes. You are the banking assistant, answering from "
        "her own accounts and cards.]"
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
        assert "the card salesperson" in text


# ─── Redial: a call outlives a dropped socket ────────────────────────────────


def _redials(driver: VoqalizeDriver) -> list[bool | None]:
    return [
        r.config.redial.enabled
        for r in driver.requests
        if isinstance(r, ConfigureFrame) and r.config.redial is not None
    ]


def _driver_moves(driver: VoqalizeDriver) -> list[dict[str, Any]]:
    return [dict(c["payload"]) for c in driver.ui_commands if c.get("command") == "stage_move"]


class _Redial:
    """One brain server and two sockets on the same session id: the first call,
    and Voqalize dialling the brain again after that socket dropped."""

    def __init__(self, llm: ScriptedOpenAI) -> None:
        from voqalize_demos.discovery import build_for

        from voqalize.conformance import BrainServer, generate_keypair

        build = build_for("bank")
        self.built: list[BankBrain] = []

        def _build() -> Any:
            brain = build(llm)  # type: ignore[arg-type]
            self.built.append(brain)
            return brain

        self.keypair = generate_keypair()
        self.server = BrainServer(
            _build, host="127.0.0.1", port=0, public_keys=self.keypair.public_pem
        )
        self.sid = "bank-redial-e2e"
        self.port = 0

    async def start(self) -> None:
        self.port = await self.server.start()

    def driver(self) -> VoqalizeDriver:
        from voqalize.conformance import DirectConnection, mint_voqalize_token

        token = mint_voqalize_token(
            private_key_pem=self.keypair.private_pem,
            session_id=self.sid,
            agent_id="bank",
            tenant_id="demo",
        )
        return VoqalizeDriver(
            DirectConnection(f"ws://127.0.0.1:{self.port}", self.sid, token=token),
            session_id=self.sid,
            default_timeout=10.0,
        )


async def _drop(driver: VoqalizeDriver) -> None:
    """The socket drops: no End, no close code a hang-up would send."""
    from voqalize_demos._loaded.bank.brain import REJOIN

    await driver.aclose()
    for _ in range(50):
        if len(REJOIN):
            break
        await asyncio.sleep(0.02)
    await asyncio.sleep(0.1)


async def test_a_dropped_socket_rejoins_the_call_where_it_was() -> None:
    """Mid-flow on the app: she switched to Hindi, opened her credit card, and
    asked to block her debit card, so the sheet awaits a yes. The brain's socket
    drops without a hang-up; Voqalize dials again for the same session with the
    same init. The new socket's brain adopts the call (language, screen, the
    sheet, the model's history, her cards) and does not greet again; her yes
    presses the sheet that was asked on the first socket."""
    llm = ScriptedOpenAI(
        {
            "Block my debit card.": [
                reply_and_call("ठीक है।", "request_change", kind="card_block", card="debit"),
                reply("स्क्रीन पर है: डेबिट कार्ड 7712 ब्लॉक करना है। आगे बढ़ूँ?"),
            ],
            "How much did I spend on food last month?": [
                reply_and_call("देखती हूँ।", "spending", month="last_month", category="food"),
                reply("पिछले महीने खाने पर इतना खर्च हुआ।"),
            ],
        }
    )
    rig = _Redial(llm)
    await rig.start()
    first, second = rig.driver(), rig.driver()
    try:
        await first.open()
        greeted = await first.start_session(init=_BANKING)
        assert greeted is not None and "Aditi" in greeted.text
        assert _redials(first) == [True], "redial is turned on with the voice, before the greeting"
        await first.send_ui_event("language_requested", {"language": "hi", "by": "visitor"})
        await first.send_ui_event(
            "page_viewed",
            {
                "path": "/app/cards/credit",
                "screen": "credit_card",
                "signed_in": True,
                "by": "visitor",
            },
        )
        await asyncio.sleep(0.2)
        await first.user_says("Block my debit card.")
        before = rig.built[-1]
        assert before.awaiting == "A1" and before.lang == "hi" and before.screen == "credit_card"
        assert "confirm.answer" not in [p["move"] for p in _driver_moves(first)]

        await _drop(first)

        # Voqalize redials: the same session id, the same init (English, the dashboard).
        await second.open()
        again = await second.start_session(init=_BANKING, greeting_timeout=0.5)
        after = rig.built[-1]
        assert after is not before
        assert again is None, "a rejoined call is not greeted a second time"
        assert after.lang == "hi" and after.screen == "credit_card" and after.mode == "banking"
        assert after.awaiting == "A1" and "A1" in after.asked, "the sheet still awaits her yes"
        assert after.turns == 1
        assert _redials(second) == [True]
        tts = [
            r.config.tts
            for r in second.requests
            if isinstance(r, ConfigureFrame) and r.config.tts is not None
        ]
        assert tts and tts[-1].voice == PERSONA["voices"]["hi"], "the language it moved to, kept"

        # Her yes answers the sheet asked on the first socket: no model turn.
        asked = len(llm.requests)
        yes = await second.user_says("हाँ")
        assert yes.units, "the call carried on after the drop"
        assert len(llm.requests) == asked
        answer = [p for p in _driver_moves(second) if p["move"] == "confirm.answer"][-1]
        assert answer["args"] == {"action_id": "A1", "yes": True}
        await second.send_ui_event(
            "stage_result",
            {
                "call_ref": answer["call_ref"],
                "move": "confirm.answer",
                "outcome": "applied",
                "detail": "done, reference GLBCB482113: Debit card ending 7712 blocked",
            },
        )
        await asyncio.sleep(0.1)
        assert after.cards["debit"]["controls"]["blocked"] is True
        idle = await second.user_idle()
        assert "GLBCB482113" in idle.text

        # The model's history came across: the next model turn still holds it.
        await second.user_says("How much did I spend on food last month?")
        last = json.dumps(llm.captured_inputs[-1], ensure_ascii=False)
        assert "Block my debit card." in last
        assert last.count("[On screen: dashboard.") == 1, "the rejoin added no second opening note"
    finally:
        await second.aclose()
        await rig.server.aclose()


async def test_a_redial_after_expiry_starts_fresh_and_the_store_lets_go(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dropped call is held two minutes, then let go: a redial after that (or
    one reaching a process that never held the call) is a new conversation on
    the same page, greeted, with none of the old call's state."""
    from voqalize_demos._loaded.bank.brain import REJOIN
    from voqalize_demos._loaded.bank.rejoin import KEEP_AFTER_DROP_S, Rejoin

    now = [0.0]
    store: Rejoin[object] = Rejoin(clock=lambda: now[0])
    a, other = object(), object()
    store.hold("s1", a)
    store.dropped("s1", other)  # not the brain held: nothing changes
    now[0] = KEEP_AFTER_DROP_S + 1
    assert store.take("s1") is a, "a live call is kept however long it runs"
    store.hold("s1", a)
    store.dropped("s1", a)
    store.dropped("s1", a)  # on_session_end runs at least once: a second run changes nothing
    now[0] += KEEP_AFTER_DROP_S - 1
    assert len(store) == 1
    now[0] += 2
    assert store.take("s1") is None and len(store) == 0
    assert store.take("never-held") is None

    # Over the wire: the same drop, then a redial after the window.
    clock = [1000.0]
    monkeypatch.setattr(REJOIN, "_clock", lambda: clock[0])
    llm = ScriptedOpenAI(
        {
            "Block my debit card.": reply_and_call(
                "Sure.", "request_change", kind="card_block", card="debit"
            )
        }
    )
    rig = _Redial(llm)
    await rig.start()
    first, second = rig.driver(), rig.driver()
    try:
        await first.open()
        await first.start_session(init=_BANKING)
        await first.user_says("Block my debit card.")
        before = rig.built[-1]
        assert before.awaiting == "A1"
        await _drop(first)
        clock[0] += KEEP_AFTER_DROP_S + 1

        await second.open()
        greeted = await second.start_session(init=_BANKING)
        after = rig.built[-1]
        assert greeted is not None and "Aditi" in greeted.text, "a new call is greeted"
        assert after.awaiting is None and after.turns == 0 and not after.asked
        assert len(REJOIN) == 1, "only the new call is held"
    finally:
        await second.aclose()
        await rig.server.aclose()


async def test_no_redial_is_asked_of_a_voqalize_that_does_not_offer_it() -> None:
    """``configure`` raises for redial without the capability: the assistant asks
    only where it is offered, and the call starts the same either way."""
    from voqalize.sdk.wire import Capability

    async with demo("bank", ScriptedOpenAI()) as rig:
        rig.driver.capabilities.discard(Capability.REDIAL)
        greeting_turn = await rig.driver.start_session(init=_BANKING)
        check_greeting(rig, greeting_turn)
        assert _redials(rig.driver) == []
        check_voice_pair(rig, voice=PERSONA["voices"]["en"], language="en")


# ─── Amounts in speech, both ways (B6, X8) ────────────────────────────────────

from voqalize_demos._loaded.bank.spoken import (  # noqa: E402
    SpokenAmounts,
    amounts_note,
    implausible,
    parse_amounts,
    speak_text,
)


@pytest.mark.parametrize(
    ("written", "lang", "spoken"),
    [
        # The owner's call (24 Nov): Voqalize's TTS read this "one rupee and twenty five
        # paisa crore". Spelled out, it passes the TTS's text chain untouched.
        (
            "Certainly, ₹1.25 crore is within our home loan range.",
            "en",
            "Certainly, one point two five crore rupees is within our home loan range.",
        ),
        (
            "Your estimated eligibility is up to ₹1.85 crore, so ₹1.25 crore is within that.",
            "en",
            "Your estimated eligibility is up to one point eight five crore rupees, so one point "
            "two five crore rupees is within that.",
        ),
        ("You can borrow ₹1.25 Cr.", "en", "You can borrow one point two five crore rupees."),
        ("Up to ₹2.25 lakh.", "en", "Up to two point two five lakh rupees."),
        ("Two FDs: ₹2 lakh and ₹1 lakh.", "en", "Two FDs: two lakh rupees and one lakh rupees."),
        ("Loans of ₹8\u201312 lakh.", "en", "Loans of eight to twelve lakh rupees."),
        ("₹8 lakh\u2013₹12 lakh.", "en", "eight lakh rupees to twelve lakh rupees."),
        ("Rates of 8.65\u20139.4% a year.", "en", "Rates of 8.65% to 9.4% a year."),
        # Plain amounts are left to the TTS, which reads them in lakh and thousand.
        ("An EMI of ₹1,57,332 a month, ₹15,000 cap.", "en", None),
        ("A 5L pressure cooker.", "en", None),
        ("A well-known bank.", "en", None),
        # Hindi: the scale in Devanagari, with the ₹ mark, so the TTS says सवा / डेढ़.
        ("जी हाँ, ₹1.25 crore तक।", "hi", "जी हाँ, ₹1.25 करोड़ तक।"),
        ("आप ₹1.5 Cr तक ले सकते हैं।", "hi", "आप ₹1.5 करोड़ तक ले सकते हैं।"),
        # Any other decimal is whole rupees: एक करोड़ पचासी लाख, not एक दशमलव आठ पाँच करोड़.
        ("eligibility ₹1.85 करोड़ तक है।", "hi", "eligibility ₹1,85,00,000 तक है।"),
        ("Loan ₹1.25\u20131.5 करोड़ तक।", "hi", "Loan ₹1.25 करोड़ से ₹1.5 करोड़ तक।"),
        ("आप 1.25 करोड़ रुपये ले सकते हैं।", "hi", "आप ₹1.25 करोड़ ले सकते हैं।"),
        ("Rate 8.65\u20139.4% सालाना है।", "hi", "Rate 8.65% से 9.4% सालाना है।"),
        # An amount that ends a Hindi sentence: the danda (।, ॥) is a stop, not a letter.
        ("आपका लोन ₹13.6 लाख।", "hi", "आपका लोन ₹13,60,000।"),
        ("आप ₹1.25 करोड़।", "hi", "आप ₹1.25 करोड़।"),
        ("आप ₹1.85 करोड़।", "hi", "आप ₹1,85,00,000।"),
        ("आप ₹1.85 करोड़॥", "hi", "आप ₹1,85,00,000॥"),
        ("आप ₹1.25 crore।", "hi", "आप ₹1.25 करोड़।"),
        ("आपका लोन ₹13.6 लाख।", "en", "आपका लोन thirteen point six lakh rupees।"),
        ("Your loan is ₹13.6 lakh.", "en", "Your loan is thirteen point six lakh rupees."),
        ("You can borrow ₹1.25 crore।", "en", "You can borrow one point two five crore rupees।"),
    ],
)
def test_amounts_are_written_the_way_the_voice_reads_them(
    written: str, lang: str, spoken: str | None
) -> None:
    assert speak_text(written, lang) == (written if spoken is None else spoken)


@pytest.mark.parametrize(
    ("heard", "values"),
    [
        # As the recogniser wrote the owner's own words (23 and 24 Nov calls).
        ("I'm looking to borrow uh 1.25 Cr.", [12500000]),
        ("I get a net salary of uh three lakhs rupees and no existing EMI.", [300000]),
        ("for dining I usually spend like ten thousand.", [10000]),
        (
            "Fuel would be ten thousand, uh bills would be Around two thousand and eighty.",
            [10000, 2080],
        ),
        ("around 1 and half lakhs", [150000]),
        ("one and a half lakh", [150000]),
        ("half a lakh", [50000]),
        ("1 crore 25 lakh", [12500000]),
        ("one point two five crore", [12500000]),
        ("15k a month", [15000]),
        ("15 hazaar", [15000]),
        ("dedh lakh", [150000]),
        ("dhai lakh", [250000]),
        ("sava do lakh", [225000]),
        ("डेढ़ लाख", [150000]),
        ("सवा करोड़", [12500000]),
        ("साढ़े तीन लाख", [350000]),
        ("पौने दो लाख", [175000]),
        ("एक लाख पचास हज़ार", [150000]),
        ("पंद्रह हज़ार", [15000]),
        ("लगभग ₹\u0967,\u0968\u096b,\u0966\u0966\u0966 का", [125000]),
        ("in 2025 15000 a month", [2025, 15000]),
    ],
)
def test_spoken_amounts_parse_to_rupees(heard: str, values: list[float]) -> None:
    assert [h.value for h in parse_amounts(heard)] == values


@pytest.mark.parametrize(
    ("heard", "low", "high"),
    [
        # A range is one amount with both ends, never the two added (₹3 lakh).
        ("my income is between 1 and 2 lakh", 100000, 200000),
        ("between one and two lakh", 100000, 200000),
        ("1-2 lakh", 100000, 200000),
        ("1 to 2 lakh", 100000, 200000),
        ("a car around 8 to 12 lakh", 800000, 1200000),
        ("1.5 to 2 crore", 15000000, 20000000),
        ("₹50,000 to ₹1 lakh", 50000, 100000),
        ("एक से दो लाख", 100000, 200000),
    ],
)
def test_a_spoken_range_parses_as_one_range(heard: str, low: float, high: float) -> None:
    (h,) = parse_amounts(heard)
    assert (h.low, h.value) == (low, high)


def test_the_amounts_note_gives_a_range_as_a_range() -> None:
    assert amounts_note("my income is between 1 and 2 lakh") == (
        "[Amounts they said, in rupees: '1 and 2 lakh' = 100000 to 200000 rupees.]"
    )
    assert amounts_note("around 8 to 12 lakh") == (
        "[Amounts they said, in rupees: '8 to 12 lakh' = about 800000 to 1200000 rupees.]"
    )


async def test_an_amount_split_across_streamed_chunks_is_still_said_whole() -> None:
    """A model streams tokens: "₹1." then "25 cr" then "ore". The rewrite waits for the
    amount to finish, and the unit's start and end pass through as they came."""
    from voqalize.sdk import SpeechChunk, SpeechEnd, SpeechStart

    async def stream() -> Any:
        yield SpeechStart()
        for piece in [
            "Certainly, ₹1.",
            "25 cr",
            "ore is within",
            " range; ₹8",
            "\u201312 lakh too.",
        ]:
            yield SpeechChunk(piece)
        yield SpeechEnd()

    out = [e async for e in SpokenAmounts(lambda: "en").wrap(stream())]
    assert isinstance(out[0], SpeechStart) and isinstance(out[-1], SpeechEnd)
    text = "".join(e.text for e in out if isinstance(e, SpeechChunk))
    assert text == (
        "Certainly, one point two five crore rupees is within range; eight to twelve lakh rupees too."
    )


def test_an_implausible_amount_is_confirmed_back_never_used() -> None:
    """I2's case on a bank field: "around 1 and half lakhs" reached a tool as ₹15."""
    why = implausible({"amount": 15}, ["around 1 and half lakhs"])
    assert why is not None and why.startswith("Not done")
    assert "₹1,50,000" in why and "₹1.5 lakh, right?" in why
    assert implausible({"amount": 150000, "existing_emis": 0}, ["1.5 lakh"]) is None
    assert implausible({"monthly_income": 300000}, ["three lakhs"]) is None
    note = amounts_note("around 1 and half lakhs")
    assert note == "[Amounts they said, in rupees: '1 and half lakhs' = about 150000 rupees.]"
    assert amounts_note("yes please") is None


async def test_amounts_are_spoken_as_words_and_a_wrong_one_is_confirmed() -> None:
    """The owner's B6 call over the wire: "1.25 Cr" heard, "₹1.25 crore" written, and the
    voice is given "one point two five crore rupees"; the model is told what the amount
    he said is in rupees. A mis-heard ₹15 for "around 1 and half lakhs" never reaches
    the calculator: the tool asks the model to confirm "₹1.5 lakh" back first."""
    llm = ScriptedOpenAI(
        {
            "I'm looking to borrow uh 1.25 Cr.": reply(
                "Certainly, ₹1.25 crore is within our home loan range. What is your monthly income?"
            ),
            "A personal loan of around 1 and half lakhs, over two years.": [
                reply_and_call(
                    "Let me work that out.",
                    "loan_emi",
                    loan_type="personal",
                    amount=15,
                    tenure_months=24,
                ),
                reply("Just to check, ₹1.5 lakh, right?"),
            ],
        }
    )
    async with demo("bank", llm) as rig:
        await rig.driver.start_session(
            init={"landing": "loans", "path": "/loans/home", "lang": "en"}
        )
        turn = await rig.driver.user_says("I'm looking to borrow uh 1.25 Cr.")
        check_turn(rig, turn)
        said = " ".join(u.text for u in turn.units)
        assert "one point two five crore rupees" in said and "₹" not in said
        told = json.dumps(llm.captured_inputs[-1], ensure_ascii=False)
        assert "'1.25 Cr' = 12500000 rupees" in told

        turn = await rig.driver.user_says(
            "A personal loan of around 1 and half lakhs, over two years."
        )
        result = _results(llm, "loan_emi")[-1]
        assert result.startswith("Not done") and "₹1,50,000" in result
        assert not [p for p in _moves(rig) if p["move"] == "loan.calc"]
        said = " ".join(u.text for u in turn.units)
        assert "one point five lakh rupees, right?" in said
