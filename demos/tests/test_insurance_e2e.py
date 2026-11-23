"""Chhatri Insurance, end to end over the wire — the real brain, a scripted model.

One customer, Rohan, through all three jobs: a car quote from two sentences (and
an add-on toggled by voice), "am I covered if…" answered from his own car policy
with the clause marked, and a motor claim and a health claim filled from what
he says, up to the review step he submits himself. Plus the language: the
toggle's Hindi at connect, Hindi heard mid-call, and the toggle moved mid-call.
And a call that outlives a dropped brain socket (redial, CONTRACT.md).

Run: ``cd demos && uv run pytest tests/test_insurance_e2e.py``
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedOpenAI, call, reply, reply_and_call

from voqalize.conformance import VoqalizeDriver
from voqalize.sdk.wire import Capability, ConfigureFrame

from ._harness import DemoRig, check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.insurance import persona, rating  # noqa: E402
from voqalize_demos._loaded.insurance.brain import InsuranceBrain  # noqa: E402
from voqalize_demos._loaded.insurance.store import POLICIES, clauses  # noqa: E402

VOICE = persona.LANGUAGES["en"].voice


@pytest.fixture(autouse=True)
def _no_call_carried_between_tests() -> Iterator[None]:
    """Every test here opens the same session id, and a dropped call is held for
    a redial to rejoin (CONTRACT.md, redial): clear the store around each test,
    so no test rejoins the one before it. Real session ids never repeat."""
    from voqalize_demos._loaded.insurance.brain import REJOIN

    REJOIN.clear()
    yield
    REJOIN.clear()


def _moves(rig: DemoRig) -> list[dict[str, Any]]:
    return [dict(c["payload"]) for c in rig.driver.ui_commands if c.get("command") == "stage_move"]


def _tool_outputs(llm: ScriptedOpenAI) -> list[str]:
    """Every tool result the brain filed, in order."""
    out: list[str] = []
    for items in llm.captured_inputs:
        for i in items:
            if isinstance(i, dict) and i.get("type") == "function_call_output":
                result = json.loads(i["output"])["result"]
                if result not in out:
                    out.append(result)
    return out


async def _hello(rig: DemoRig, path: str) -> None:
    await rig.driver.send_ui_event(
        "stage_hello",
        {
            "runtime": "@voqalize/stage",
            "contract": 1,
            "url": f"https://dev.example.com/demos/insurance/{path}",
        },
    )
    await asyncio.sleep(0.1)


def _brain(rig: DemoRig) -> InsuranceBrain:
    b = rig.brain
    assert isinstance(b, InsuranceBrain)
    return b


# ─── Quote ────────────────────────────────────────────────────────────────────

CAR_SAID = "I have a 2022 diesel SUV in Pune, it cost about fourteen and a half lakh, two years without a claim."
CAR = {
    "vehicle_class": "suv",
    "fuel": "diesel",
    "registration_year": "2022",
    "ex_showroom": "14.5 lakh",
    "city": "Pune",
    "claim_free_years": "2",
}


async def test_a_car_quote_from_two_sentences_fills_the_form_and_speaks_the_total() -> None:
    expected = rating.quote(
        "car",
        {**CAR, "ex_showroom": "1450000", "city": "pune"},
        ["pa_owner", "zero_dep"],
    )
    llm = ScriptedOpenAI(
        {
            CAR_SAID: [
                call(
                    "update_quote",
                    product="car",
                    answers=[{"field": k, "value": v} for k, v in CAR.items()],
                    addons_on=["zero_dep"],
                ),
                reply(f"Your SUV comes to {expected.total} rupees a year, with zero depreciation."),
            ],
            "Take engine protection too.": reply_and_call(
                "Engine protection is on.",
                "update_quote",
                product="car",
                addons_on=["engine_protect"],
            ),
        }
    )
    async with demo("insurance", llm) as rig:
        greeting = await rig.driver.start_session(init={"landing": "/quote/car", "lang": "en"})
        check_greeting(rig, greeting)
        check_voice_pair(rig, voice=VOICE, language="en")
        assert greeting is not None and "build your quote" in greeting.text
        assert _brain(rig).mode == "quote"

        t1 = await rig.driver.user_says(CAR_SAID)
        check_turn(rig, t1)
        moves = _moves(rig)
        # On /quote/car the builder is already there: no open, fields one by one, the add-on, the panel.
        assert [m["move"] for m in moves] == ["quote.fill"] * 6 + ["quote.addon", "quote.show"]
        assert {m["args"]["field"]: m["args"]["value"] for m in moves[:6]} == {
            **CAR,
            "ex_showroom": "1450000",
            "city": "pune",
        }
        result = _tool_outputs(llm)[0]
        assert f"TOTAL PAYABLE {rating.inr(expected.total)}" in result
        assert "Zero depreciation" in result
        assert str(expected.total) in t1.text

        t2 = await rig.driver.user_says("Take engine protection too.")
        check_turn(rig, t2)
        assert _moves(rig)[-2]["move"] == "quote.addon"
        assert _moves(rig)[-2]["args"] == {"addon": "engine_protect", "on": True}


async def test_a_quote_asks_only_for_what_is_missing_and_opens_the_builder() -> None:
    llm = ScriptedOpenAI(
        {
            "Health cover for me and my wife, I'm 38.": [
                call(
                    "update_quote",
                    product="health",
                    answers=[
                        {"field": "cover_type", "value": "family floater"},
                        {"field": "adults", "value": "2"},
                        {"field": "eldest_age", "value": "38"},
                    ],
                ),
                reply("How much cover would you like, and which city do you live in?"),
            ]
        }
    )
    async with demo("insurance", llm) as rig:
        await rig.driver.start_session(init={"landing": "/", "lang": "en"})
        assert _brain(rig).mode == "home"
        check_turn(rig, await rig.driver.user_says("Health cover for me and my wife, I'm 38."))
        moves = _moves(rig)
        assert moves[0] == {**moves[0], "move": "quote.open", "args": {"product": "health"}}
        assert [m["args"]["value"] for m in moves[1:]] == ["family_floater", "2", "38"]
        result = _tool_outputs(llm)[0]
        assert "Still needed" in result and "sum_insured" in result and "city" in result
        assert "quote.show" not in [m["move"] for m in moves]


# ─── Policies ─────────────────────────────────────────────────────────────────


def _engine_water_clause() -> tuple[str, str]:
    """The car policy's clause about a waterlogged engine, read from the data."""
    for s, c in clauses("car-2026"):
        words = " ".join(c.get("tags", [])) + " " + c["title"]
        if "engine" in words.lower() and any(w in words.lower() for w in ("flood", "water")):
            return s["id"], c["id"]
    raise AssertionError("car-2026 has no engine/water clause")


async def test_am_i_covered_finds_the_clause_and_marks_it() -> None:
    _, clause_id = _engine_water_clause()
    question = "Am I covered if my car's engine gets damaged driving through a flooded road?"
    llm = ScriptedOpenAI(
        {
            question: [
                call(
                    "search_policy",
                    question="engine damaged driving through flooded road",
                    policy_id="car-2026",
                ),
                reply_and_call(
                    f"Yes, clause {clause_id} covers it through your engine protection add-on.",
                    "mark_clause",
                    policy_id="car-2026",
                    clause_id=clause_id,
                    verdict="covered",
                ),
            ]
        }
    )
    async with demo("insurance", llm) as rig:
        greeting = await rig.driver.start_session(init={"landing": "/my-policies", "lang": "en"})
        assert greeting is not None and "exact clause" in greeting.text
        t = await rig.driver.user_says(question)
        check_turn(rig, t)
        found = _tool_outputs(llm)[0]
        assert f"car-2026 clause {clause_id} " in found
        assert _moves(rig) == [
            {
                **_moves(rig)[0],
                "move": "policy.mark",
                "args": {"policy_id": "car-2026", "clause_id": clause_id, "verdict": "covered"},
            }
        ]


async def test_a_clause_that_does_not_exist_is_never_marked() -> None:
    llm = ScriptedOpenAI(
        {
            "Is theft covered?": reply_and_call(
                "Let me see.",
                "mark_clause",
                policy_id="car-2026",
                clause_id="99.9",
                verdict="covered",
            )
        }
    )
    async with demo("insurance", llm) as rig:
        await rig.driver.start_session(init={"landing": "/my-policies/car-2026"})
        check_turn(rig, await rig.driver.user_says("Is theft covered?"))
        assert _moves(rig) == []


# ─── Claims ───────────────────────────────────────────────────────────────────

# Yesterday in India, as the model would write it from the date note.
YESTERDAY = (
    (datetime.now(timezone(timedelta(hours=5, minutes=30))) - timedelta(days=1)).date().isoformat()
)
MOTOR_SAID = "Someone rear-ended my car yesterday at about 7 pm on Baner Road in Pune."
MOTOR_MORE = "I was driving, licence MH12 2015 0012345. The other car was MH 14 XY 2210, nobody was hurt, and I filed an FIR, number 412 of 2026 at Baner police station."
MOTOR_LAST = "It's at the network garage in Baner and it still drives. Use my account on file."


async def test_a_motor_claim_fills_from_what_he_says_and_reaches_review() -> None:
    garage = next(
        g["id"] for g in json.loads((rating.DATA / "network.json").read_text())["garages"]
    )
    bank = json.loads((rating.DATA / "customer.json").read_text())["bank_on_file"]
    llm = ScriptedOpenAI(
        {
            MOTOR_SAID: [
                call("start_claim", claim_type="motor", policy_id="car-2026"),
                call(
                    "fill_claim",
                    answers=[
                        {"field": "incident_kind", "value": "accident"},
                        {"field": "incident_date", "value": YESTERDAY},
                        {"field": "incident_time", "value": "19:00"},
                        {"field": "incident_city", "value": "Pune"},
                        {"field": "incident_location", "value": "Baner Road"},
                        {"field": "description", "value": "Another car hit mine from behind."},
                    ],
                ),
                reply("I'm sorry. Were you driving, and was anyone else involved?"),
            ],
            MOTOR_MORE: [
                call(
                    "fill_claim",
                    answers=[
                        {"field": "driver_is_policyholder", "value": "yes"},
                        {"field": "driver_licence", "value": "MH12 2015 0012345"},
                        {"field": "other_party_involved", "value": "yes"},
                        {"field": "other_vehicle_number", "value": "MH 14 XY 2210"},
                        {"field": "injuries", "value": "none"},
                        {"field": "police_reported", "value": "yes"},
                        {"field": "fir_number", "value": "412/2026"},
                        {"field": "police_station", "value": "Baner"},
                    ],
                ),
                reply("Got it. Where is the car now, and can it be driven?"),
            ],
            MOTOR_LAST: [
                call(
                    "fill_claim",
                    answers=[
                        {"field": "garage_id", "value": garage},
                        {"field": "vehicle_location", "value": "at_garage"},
                        {"field": "vehicle_drivable", "value": "yes"},
                        {"field": "account_holder", "value": bank["account_holder"]},
                        {"field": "bank_name", "value": bank["bank_name"]},
                        {"field": "account_number", "value": bank["account_number"]},
                        {"field": "ifsc", "value": bank["ifsc"]},
                    ],
                ),
                reply_and_call("That's everything. Here's the review.", "review_claim"),
            ],
            "submitted claim CLM-M-260418": reply(
                "Thank you, your claim reference is CLM-M-260418."
            ),
        }
    )
    async with demo("insurance", llm) as rig:
        greeting = await rig.driver.start_session(init={"landing": "/claim", "lang": "en"})
        assert greeting is not None and "fill in the form" in greeting.text
        assert _brain(rig).today.isoformat() > YESTERDAY

        check_turn(rig, await rig.driver.user_says(MOTOR_SAID))
        moves = _moves(rig)
        assert moves[0]["move"] == "claim.start"
        assert moves[0]["args"] == {"claim_type": "motor", "policy_id": "car-2026"}
        assert [m["args"]["field"] for m in moves[1:]] == [
            "incident_kind",
            "incident_date",
            "incident_time",
            "incident_city",
            "incident_location",
            "description",
        ]
        first = _tool_outputs(llm)[-1]
        assert "vehicle_drivable" in first and "driver_is_policyholder" in first
        assert "contact_phone" not in first.split("Still missing")[1]

        check_turn(rig, await rig.driver.user_says(MOTOR_MORE))
        check_turn(rig, await rig.driver.user_says(MOTOR_LAST))
        last = _tool_outputs(llm)
        assert any("Every required field is filled" in r for r in last)
        assert _moves(rig)[-1]["move"] == "claim.review"
        # The documents he still uploads himself: the FIR copy because he reported it.
        assert "Copy of the FIR" in last[-1]
        assert "claim.submit" not in {m["move"] for m in _moves(rig)}

        # The customer uploads and submits; she thanks him with the guide's next step.
        await rig.driver.send_ui_event(
            "stage_event",
            {
                "name": "claim.submitted",
                "by": "visitor",
                "data": {"reference": "CLM-M-260418", "filled": [], "documents": []},
            },
        )
        await asyncio.sleep(0.1)
        thanks = await rig.driver.user_idle()
        check_turn(rig, thanks)
        assert "CLM-M-260418" in thanks.text


HEALTH_SAID = "My son Aarav was admitted to hospital for dengue on the 10th of this month, I paid and want reimbursement."


async def test_a_health_claim_takes_the_member_and_refuses_what_the_form_does_not_take() -> None:
    llm = ScriptedOpenAI(
        {
            HEALTH_SAID: [
                call("start_claim", claim_type="health"),
                call(
                    "fill_claim",
                    answers=[
                        {"field": "patient_member", "value": "Aarav"},
                        {"field": "claim_mode", "value": "reimbursement"},
                        {"field": "ailment", "value": "Dengue fever"},
                        {"field": "fir_number", "value": "123"},
                        {"field": "admission_date", "value": "2099-01-10"},
                    ],
                ),
                reply("Which hospital was it?"),
            ]
        }
    )
    async with demo("insurance", llm) as rig:
        await rig.driver.start_session(init={"landing": "/claim"})
        check_turn(rig, await rig.driver.user_says(HEALTH_SAID))
        moves = _moves(rig)
        assert moves[0]["args"] == {"claim_type": "health", "policy_id": "health-2026"}
        filled = {m["args"]["field"]: m["args"]["value"] for m in moves[1:]}
        assert filled == {
            "patient_member": "aarav",
            "claim_mode": "reimbursement",
            "ailment": "Dengue fever",
        }
        result = _tool_outputs(llm)[-1]
        assert "fir_number = '123' not taken" in result
        assert "admission_date = '2099-01-10' not taken: a date in the future" in result
        assert "hospital_id" in result


# ─── Language ─────────────────────────────────────────────────────────────────


async def test_hindi_from_the_toggle_configures_both_legs_and_greets_in_hindi() -> None:
    async with demo("insurance", ScriptedOpenAI()) as rig:
        greeting = await rig.driver.start_session(init={"landing": "/claim", "lang": "hi"})
        check_voice_pair(rig, voice=persona.LANGUAGES["hi"].voice, language="hi")
        assert greeting is not None and persona.name_in("hi") in greeting.text


async def test_hindi_heard_moves_both_legs_and_the_toggle() -> None:
    llm = ScriptedOpenAI({"मुझे कार का क्वोट चाहिए": reply("ज़रूर, कार किस साल की है?")})
    async with demo("insurance", llm) as rig:
        await rig.driver.start_session(init={"landing": "/quote", "lang": "en"})
        check_voice_pair(rig, voice=VOICE, language="en")
        check_turn(rig, await rig.driver.user_says("मुझे कार का क्वोट चाहिए"))
        check_voice_pair(rig, voice=persona.LANGUAGES["hi"].voice, language="hi")
        assert _moves(rig)[0]["move"] == "site.language"
        assert _moves(rig)[0]["args"] == {"language": "hi"}


async def test_the_toggle_mid_call_switches_and_says_so() -> None:
    async with demo("insurance", ScriptedOpenAI()) as rig:
        await rig.driver.start_session(init={"landing": "/"})
        await rig.driver.send_ui_event(
            "stage_event",
            {"name": "site.language_chosen", "by": "visitor", "data": {"language": "hi"}},
        )
        await asyncio.sleep(0.2)
        check_voice_pair(rig, voice=persona.LANGUAGES["hi"].voice, language="hi")
        said = await rig.driver.user_idle()
        assert said.text == persona.SWITCHED["hi"]


# ─── Following the visitor ────────────────────────────────────────────────────


async def test_the_job_follows_the_page() -> None:
    llm = ScriptedOpenAI(
        {"I need to make a claim": reply_and_call("Let's do that.", "go_to", page="claim")}
    )
    async with demo("insurance", llm) as rig:
        await rig.driver.start_session(init={"landing": "/"})
        await _hello(rig, "my-policies/health-2026")
        assert _brain(rig).mode == "policies"
        check_turn(rig, await rig.driver.user_says("I need to make a claim"))
        assert _moves(rig)[-1]["args"] == {"page": "claim"}
        assert _brain(rig).mode == "claim"
        notes = [
            i for i in llm.captured_inputs[-1] if isinstance(i, dict) and i.get("role") == "user"
        ]
        assert any("[PAGE]" in str(n.get("content")) for n in notes)


def test_every_policy_the_customer_holds_has_a_document() -> None:
    assert set(POLICIES) == {
        "car-2026",
        "bike-2026",
        "health-2026",
        "home-2026",
        "term-2025",
        "travel-2026",
    }
    for pid, doc in POLICIES.items():
        ids = [c["id"] for _, c in clauses(pid)]
        assert len(ids) == len(set(ids)), f"{pid}: clause ids repeat"
        assert all(c.get("plain") and c.get("text") for _, c in clauses(pid)), pid
        assert doc["id"] == pid


def test_the_golden_quotes_are_current() -> None:
    golden = json.loads((rating.DATA / "quote_cases.json").read_text())["cases"]
    assert golden == rating.golden(), "run: uv run python insurance/backend/rating.py --cases"


# ─── A call outlives a dropped brain socket (redial) ──────────────────────────


def _redials(driver: VoqalizeDriver) -> list[bool | None]:
    return [
        r.config.redial.enabled
        for r in driver.requests
        if isinstance(r, ConfigureFrame) and r.config.redial is not None
    ]


def _spoken(driver: VoqalizeDriver) -> list[tuple[str | None, str | None]]:
    return [
        (r.config.tts.voice, r.config.tts.language)
        for r in driver.requests
        if isinstance(r, ConfigureFrame) and r.config.tts is not None
    ]


async def test_a_dropped_socket_rejoins_the_claim_where_it_was() -> None:
    """Mid-claim (the incident filled, the call switched to Hindi by the
    toggle), the brain's socket drops without a hang-up. Ananya turned redial
    on; Voqalize dials again for the same session with the same init; the new
    socket's brain adopts the call — job, language, claim, the model's history —
    greets no one, and the next turn fills the claim on from where it was."""
    from voqalize_demos._loaded.insurance.brain import REJOIN
    from voqalize_demos.discovery import build_for

    from voqalize.conformance import (
        BrainServer,
        DirectConnection,
        generate_keypair,
        mint_voqalize_token,
    )

    llm = ScriptedOpenAI(
        {
            MOTOR_SAID: [
                call("start_claim", claim_type="motor", policy_id="car-2026"),
                call(
                    "fill_claim",
                    answers=[
                        {"field": "incident_kind", "value": "accident"},
                        {"field": "incident_date", "value": YESTERDAY},
                        {"field": "incident_city", "value": "Pune"},
                    ],
                ),
                reply("I'm sorry. Were you driving?"),
            ],
            MOTOR_MORE: [
                call(
                    "fill_claim",
                    answers=[
                        {"field": "driver_is_policyholder", "value": "yes"},
                        {"field": "injuries", "value": "none"},
                    ],
                ),
                reply("ठीक है। गाड़ी अभी कहाँ है?"),
            ],
        }
    )
    build = build_for("insurance")
    built: list[InsuranceBrain] = []

    def _build() -> Any:
        brain = build(llm)  # type: ignore[arg-type]
        built.append(brain)
        return brain

    keypair = generate_keypair()
    server = BrainServer(_build, host="127.0.0.1", port=0, public_keys=keypair.public_pem)
    port = await server.start()
    sid = "insurance-redial-e2e"
    init = {"landing": "/claim", "lang": "en"}

    def driver() -> VoqalizeDriver:
        token = mint_voqalize_token(
            private_key_pem=keypair.private_pem,
            session_id=sid,
            agent_id="insurance",
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
        greeting = await first.start_session(init=init)
        assert greeting is not None and "fill in the form" in greeting.text
        assert _redials(first) == [True], "redial is turned on with the voice, before the greeting"
        await first.user_says(MOTOR_SAID)
        await first.send_ui_event(
            "stage_event",
            {"name": "site.language_chosen", "by": "visitor", "data": {"language": "hi"}},
        )
        await asyncio.sleep(0.2)
        before = built[-1]
        assert before.lang == "hi" and before.mode == "claim"
        claim_before = dict(before.claim.values)
        assert claim_before["incident_city"] == "Pune"

        # The socket drops: no End, no close code a hang-up would send.
        await first.aclose()
        for _ in range(50):
            if len(REJOIN):
                break
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.1)

        # Voqalize redials: the same session id, the same init (still "en").
        await second.open()
        again = await second.start_session(init=init, greeting_timeout=0.5)
        assert again is None, "no second greeting"
        after = built[-1]
        assert after is not before
        assert after.mode == "claim" and after.route == "claim"
        assert after.lang == "hi", "the language it had moved to, not the init's"
        assert after.claim.claim_type == "motor" and after.claim.values == claim_before
        assert _redials(second) == [True]
        assert _spoken(second)[-1] == (persona.LANGUAGES["hi"].voice, "hi")

        turn = await second.user_says(MOTOR_MORE)
        assert turn.units, "the call carried on after the drop"
        fills = [
            c["payload"]["args"]["field"]
            for c in second.ui_commands
            if c.get("command") == "stage_move" and c["payload"]["move"] == "claim.fill"
        ]
        assert fills == ["driver_is_policyholder", "injuries"]
        assert after.claim.values["incident_city"] == "Pune"
        assert after.claim.values["driver_is_policyholder"] == "yes"
        sent = json.dumps(llm.captured_inputs[-1], ensure_ascii=False)
        assert MOTOR_SAID in sent, "the model's history came across"
        assert sent.count("[Today is") == 1, "no second start note"
    finally:
        await second.aclose()
        await server.aclose()


async def test_redial_held_calls_are_let_go_two_minutes_after_a_drop() -> None:
    """A live call is kept however long it runs; a dropped one two minutes; a
    redial reaching a process that never held the call finds nothing."""
    from voqalize_demos._loaded.insurance.rejoin import KEEP_AFTER_DROP_S, Rejoin

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


async def test_a_redial_after_expiry_starts_fresh_and_greets() -> None:
    """Past the two minutes, a redial on the same session id is a new call: it
    greets again from the init's page and language, none of the old call's."""
    from voqalize_demos._loaded.insurance import brain as ib
    from voqalize_demos._loaded.insurance.rejoin import KEEP_AFTER_DROP_S, Rejoin
    from voqalize_demos.discovery import build_for

    llm = ScriptedOpenAI()
    stale = build_for("insurance")(llm)  # type: ignore[arg-type]
    assert isinstance(stale, InsuranceBrain)
    stale.mode, stale.route, stale.lang = "claim", "claim", "hi"
    stale.claim.start("motor", "car-2026")
    now = [0.0]
    held: Rejoin[InsuranceBrain] = Rejoin(clock=lambda: now[0])
    old, ib.REJOIN = ib.REJOIN, held
    try:
        async with demo("insurance", llm) as rig:
            held.hold(rig.driver.session_id, stale)
            held.dropped(rig.driver.session_id, stale)
            now[0] = KEEP_AFTER_DROP_S + 1
            greeting = await rig.driver.start_session(init={"landing": "/quote", "lang": "en"})
            fresh = _brain(rig)
            assert fresh is not stale
            assert greeting is not None and persona.name_in("en") in greeting.text
            assert fresh.mode == "quote" and fresh.lang == "en"
            assert fresh.claim.claim_type is None
    finally:
        ib.REJOIN = old


async def test_no_redial_is_asked_of_a_voqalize_that_does_not_offer_it() -> None:
    """``configure`` raises for redial without the capability: Ananya asks only
    where it is offered, and the call starts the same either way."""
    async with demo("insurance", ScriptedOpenAI()) as rig:
        rig.driver.capabilities.discard(Capability.REDIAL)
        greeting = await rig.driver.start_session(init={"landing": "/claim", "lang": "en"})
        assert greeting is not None and "fill in the form" in greeting.text
        assert _redials(rig.driver) == []
        check_voice_pair(rig, voice=VOICE, language="en")
