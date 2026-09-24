"""The Vantage Bank branch kiosk, end to end over the wire — no network, no key.

The real ``KioskBrain`` — the shipping ``demos/kiosk/backend/brain.py``, its real
prompt, its real eleven tools, its real Python rules — hosted on a real
``brain_server`` socket and driven by the conformance ``VoqalizeDriver``, with only
the *model* scripted. See ``tests/_harness.py`` for what every demo's e2e proves.

Tanvi is the demo where the **two strings per figure** rule is the whole design.
Every fact on the shelf exists twice: ``₹1,50,000`` for the totem and "one and a
half lakh rupees" for the voice, and handing the wrong one to the wrong consumer
is silent — the transcript is perfect and the customer hears "one five zero comma
zero zero zero". So the assertions here are not only conversational: every ``SAY:``
span the brain ever hands the model is swept for a digit, a rupee sign, a percent
sign and every raw enum token, because that is the only place it is visible.

The other four things this file holds:

* **A hand alone reaches the QR.** The whole journey is walked with
  ``send_ui_event`` and nothing else, asserting the action on the glass at every
  step — and, at every step, that Tanvi said nothing and no model ran. Then one
  word from the customer, and her first request already carries every gesture.

* **The arithmetic is Python.** ``assess`` and ``shortlist`` are pure functions
  with no model in them; they are called directly *and* through the wire, and the
  band, the reasons and the ranking must agree. A bank telling a walk-in customer
  the wrong thing in a branch is not a soft failure.
* **Confirmation is asked once.** A clear yes settles. An unclear reply is
  re-asked exactly one time, and a second unclear reply is taken as heard — the
  loop cannot run twice, which is what stops the kiosk sounding like a bad IVR.
* **The language moves as a pair.** ``switch_language`` is one
  ``session.configure``, so the recognizer and the reference clip cannot drift
  apart mid-call.

Run: ``cd demos && uv run pytest tests/test_kiosk_e2e.py``
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any, NamedTuple

from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, call, reply

from ._harness import DemoRig, _configs, _last, check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.kiosk.brain import (  # noqa: E402
    KIOSK_EVENTS,
    AskProfile,
    CardView,
    ConfirmValue,
    OpenConsent,
    ShowEligibility,
    ShowQr,
    ShowShortlist,
)
from voqalize_demos._loaded.kiosk.cards import (  # noqa: E402
    EMPLOYMENT_SPOKEN,
    EXISTING_CARDS_SPOKEN,
    INCOME_BAND_SPOKEN,
    PROFILE_PROMPTS,
    SPEND_SPOKEN,
    VALUE_PROMPTS,
)
from voqalize_demos._loaded.kiosk.eligibility import assess, shortlist  # noqa: E402
from voqalize_demos._loaded.kiosk.prompts import GREETING  # noqa: E402

#: One person, two languages — the clip does not change when the language does.
VOICE = "omnivoice/gayatri"

#: The profile every flow test drives: salaried, mid band, one card already,
#: fuel is where the money goes. Chosen because it lands in the *standard* band
#: with three eligible cards, so the shortlist is a real ranking rather than a
#: list of everything.
_SALARIED_FUEL = {
    "employment": "salaried",
    "income_band": "25k_60k",
    "existing_cards": "one",
    "spend_category": "fuel",
}


# ─── Reading what the brain said to the model ─────────────────────────────────
# ``dump_conversation`` does not work on a GeminiBrain demo, so everything the
# brain put in front of the model is read off the requests it made instead.


def _record(llm: ScriptedGemini) -> list[Any]:
    """The newest request's ``contents`` — the whole session, once.

    Every request carries the context that has accumulated so far, so the newest
    one is the complete record and each earlier one is a prefix of it. Walking
    *all* of them counts every tool result as many times as there were later
    turns, which turns "asked once" into "asked three times"."""
    return llm.captured_contents[-1] if llm.captured_contents else []


def _tool_results(llm: ScriptedGemini) -> list[str]:
    """Every tool result the brain handed the model, in order, once each.

    A tool's outcome never reaches the wire — the customer hears only the sentence
    the model built from it — so the model's *next* prompt is the only place it is
    visible. google-genai wraps a return as ``{"result": ...}``, so unwrap that one
    level; ``str(response)`` would read the wrapper and match on its punctuation.
    """
    return [
        str((part.function_response.response or {}).get("result", ""))
        for content in _record(llm)
        for part in content.parts or []
        if part.function_response is not None
    ]


def _user_text(contents: list[Any]) -> str:
    """One request's context, as the customer's own words — what they said out
    loud and the one-line note behind every gesture, in the order they arrived."""
    return " ".join(
        part.text or ""
        for content in contents
        if content.role == "user"
        for part in content.parts or []
    )


def _context_text(llm: ScriptedGemini) -> str:
    """Everything the brain appended to the context as the customer's own words.

    What the customer does with their hand reaches the model exactly one way:
    ``on_rtvi`` appends one line naming the gesture. It takes no floor, so it is
    invisible until the next request carries the whole context with it."""
    return _user_text(_record(llm))


def _spoken(rig: DemoRig) -> list[str]:
    """Every unit of speech Tanvi has put on the wire so far, in order.

    The hand path's central claim is a *negative* one, and a negative claim needs
    something countable to be asserted against: this list not growing across a
    gesture is what "she stayed quiet" means on the wire."""
    return [unit.text for turn in rig.driver.turns.values() for unit in turn.units]


async def _by_hand(
    rig: DemoRig, event: str, payload: dict[str, Any] | None = None
) -> list[tuple[str, dict[str, Any]]]:
    """One gesture, and everything it put on the glass, in order.

    ``send_ui_event`` returns once the frame is sent, not once ``on_rtvi`` has
    run — and ``on_rtvi`` takes no floor, so there is no bracket to wait on and
    nothing to await but the clock."""
    before = len(rig.driver.ui_commands)
    await rig.driver.send_ui_event(event, payload or {})
    await asyncio.sleep(0.1)
    return [
        (str(c.get("command")), dict(c.get("payload") or {}))
        for c in rig.driver.ui_commands[before:]
        if not str(c.get("command", "")).startswith("__")
    ]


_SAY = re.compile(r"SAY:(.*)", re.DOTALL)


def _say_lines(llm: ScriptedGemini) -> list[str]:
    """Every ``SAY:`` line the brain wrote, which is the text it told Tanvi to
    speak verbatim. This is the only place the display/spoken split is checkable
    from outside the brain."""
    return [m.group(1) for result in _tool_results(llm) if (m := _SAY.search(result))]


async def _one_more_turn(rig: DemoRig) -> None:
    """One throwaway turn, so the turn before it is readable.

    Under automatic function calling a whole user turn is *one* request, and the
    calls and responses it made are filed into the context only after it — so a
    tool result is first carried by the request that follows. A test that asserts
    on the last turn's tool results without this is asserting on an empty list."""
    await rig.driver.user_says("Thanks.")


def _payloads(rig: DemoRig, action: str) -> list[dict[str, Any]]:
    """Every payload the brain fired under one command name, in order.

    ``rig.command`` returns the first, which is the wrong one for an action the
    flow fires repeatedly — ``confirm_value`` moves ``heard`` → ``confirming`` →
    ``confirmed`` and the last one is the state the customer is left looking at."""
    return [
        dict(c.get("payload") or {}) for c in rig.driver.ui_commands if c.get("command") == action
    ]


# ─── The scripted model ───────────────────────────────────────────────────────


def _discovery_script() -> dict[str, Any]:
    """The four questions and the four answers, as fourteen-turn pacing has them:
    one tool to record the answer — which puts the next question up by itself —
    and one short line that folds the acknowledgement and the question into one
    breath."""
    return {
        "Hello there.": [
            call("ask_profile", ask={"field": "employment", "question": "What do you do?"}),
            reply("Are you salaried, self employed, in government service, or studying?"),
        ],
        "I'm salaried.": [
            call("capture_value", heard={"field": "employment", "value": "salaried"}),
            reply("Got it. And roughly what comes in every month?"),
        ],
        "About forty thousand a month.": [
            call("capture_value", heard={"field": "income_band", "value": "25k_60k"}),
            reply("Thank you. Do you already hold a credit card?"),
        ],
        "Just the one.": [
            call("capture_value", heard={"field": "existing_cards", "value": "one"}),
            reply("Right. And where does most of your spending go?"),
        ],
        "Mostly fuel, I drive a lot.": [
            call("capture_value", heard={"field": "spend_category", "value": "fuel"}),
            call("check_eligibility", request={}),
            reply(
                "You are likely eligible for our main cards, and the line is about two to "
                "three times your monthly income. A banker at the desk will confirm."
            ),
        ],
    }


def _full_flow_llm() -> ScriptedGemini:
    """Discovery, then the cards, then the QR — the whole visit."""
    return ScriptedGemini(
        {
            **_discovery_script(),
            "Which one would you pick?": [
                call("show_shortlist"),
                reply("The Vantage Fuel is my pick, because you spend most on fuel."),
            ],
            "Tell me more about that one.": [
                call("open_card_detail", card={"card_id": "vantage_fuel"}),
                reply("The fuel surcharge comes off on most fills, which is where you spend."),
            ],
            "I'll take it.": [
                call("open_consent", card={"card_id": "vantage_fuel"}),
                reply(
                    "Everything you are agreeing to is on screen. Say yes out loud if you are happy."
                ),
            ],
            "Yes, go ahead.": [
                call("finish_with_qr", card={"card_id": "vantage_fuel"}),
                reply("Show that code at the desk and a banker will take it from here."),
            ],
        }
    )


async def _drive_discovery(rig: DemoRig) -> None:
    """The four questions, answered out loud. Leaves the totem on the eligibility
    screen with all four values captured."""
    await rig.driver.user_says("Hello there.")
    await rig.driver.user_says("I'm salaried.")
    await rig.driver.user_says("About forty thousand a month.")
    await rig.driver.user_says("Just the one.")
    await rig.driver.user_says("Mostly fuel, I drive a lot.")


# ─── The liveness floor ───────────────────────────────────────────────────────


async def test_the_kiosk_greets_and_both_legs_reach_the_wire() -> None:
    """A walk-in gets the English opener, and both halves of the language land
    before that audio.

    ``greet`` contains no model call — a customer standing at a totem should not
    wait on a first token to be told they are talking to an AI — so the greeting
    is asserted against the hand-written table, not against a scripted reply."""
    llm = ScriptedGemini()
    async with demo("kiosk", llm) as rig:
        greeting = await rig.driver.start_session()
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text == GREETING["English"]
        check_voice_pair(rig, voice=VOICE, language="en")
        assert llm.calls == [], "greet() called the model"


def test_the_opener_discloses_the_ai_in_its_first_sentence() -> None:
    """Tanvi says she is an AI in her first sentence, in both languages.

    It is in the fixed table rather than the prompt because it cannot wait for a
    turn the customer might never take — someone who walks up, hears one line and
    walks away has still been told."""
    for language, opener in GREETING.items():
        first = re.split(r"[.।]", opener)[0]
        assert ("AI" in first) or ("ए आई" in first), (language, first)


async def test_the_totem_language_toggle_opens_the_call_in_hindi() -> None:
    """The page carries the customer's choice from the totem's own toggle, and the
    brain resolves it — one authority, because the same choice also has to move
    the greeting's text."""
    async with demo("kiosk", ScriptedGemini()) as rig:
        greeting = await rig.driver.start_session(init={"language": "Hindi"})
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text == GREETING["Hindi"]
        check_voice_pair(rig, voice=VOICE, language="hi")


async def test_a_language_the_page_does_not_know_falls_back_rather_than_refusing() -> None:
    """A stale totem against a new brain greets in English, and greets. A kiosk
    that opens in the wrong language is recoverable in a branch; one that refuses
    to open is a screen nobody can use."""
    async with demo("kiosk", ScriptedGemini()) as rig:
        greeting = await rig.driver.start_session(init={"language": "Klingon"})
        assert greeting is not None and greeting.text == GREETING["English"]
        check_voice_pair(rig, voice=VOICE, language="en")


# ─── Discovery ────────────────────────────────────────────────────────────────


async def test_a_spoken_answer_lands_on_the_totem_as_a_confirmed_value() -> None:
    """The first discovery answer, all the way through: the model resolves what
    was said to a closed token, the brain records it, and the screen gets the
    *label* — never the token, which reads as "self underscore employed".

    A closed answer settles on the spot. There is no reading back a word the
    customer just chose off a list of four."""
    llm = ScriptedGemini(_discovery_script())
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()

        first = await rig.driver.user_says("Hello there.")
        check_turn(rig, first, units=1)
        asked = rig.command("ask_profile")
        assert asked["field"] == "employment"
        assert [o["value"] for o in asked["options"]] == [
            "salaried",
            "self_employed",
            "government",
            "student",
        ]
        assert all(o["label"] and o["label_hi"] for o in asked["options"]), asked["options"]

        second = await rig.driver.user_says("I'm salaried.")
        check_turn(rig, second, units=1)
        (value,) = _payloads(rig, "confirm_value")
        assert value == {
            "field": "employment",
            "display": "Salaried",
            "masked": "Salaried",
            "state": "heard",
        }
        assert rig.brain.answers["employment"] == "salaried"
        assert "employment" in rig.brain.confirmed


async def test_an_answer_the_model_invented_is_refused_with_the_vocabulary() -> None:
    """A token outside the closed set does not reach the rules. The model is told
    what it may say instead, and the totem is not painted — a screen showing a
    value the rules will never accept is worse than no screen."""
    llm = ScriptedGemini(
        {
            "I work in a bank.": [
                call("capture_value", heard={"field": "employment", "value": "banker"}),
                reply("Salaried, self employed, government, or studying?"),
            ],
        }
    )
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        check_turn(rig, await rig.driver.user_says("I work in a bank."))
        assert _payloads(rig, "confirm_value") == []
        assert rig.brain.answers == {}
        await _one_more_turn(rig)
    refusal = " ".join(_tool_results(llm))
    assert "'banker' is not a value I can use for employment" in refusal
    assert "salaried, self_employed, government, student" in refusal
    assert "SAY:" not in refusal, "a refusal is a direction to the model, not a line to read"


# ─── The rules ────────────────────────────────────────────────────────────────


def test_the_rules_are_pure_python_and_instant() -> None:
    """``assess`` is dictionary lookups and comparisons — no I/O, no sleeps, no
    model. A thousand runs inside the budget one run is allowed says there is
    nothing hiding in it."""
    started = time.perf_counter()
    for _ in range(1000):
        assess(employment="salaried", income_band="25k_60k", existing_cards="one")
    assert time.perf_counter() - started < 0.5


def test_a_thin_file_is_routed_to_the_secured_card_and_never_to_a_score() -> None:
    """The three properties ``eligibility.py`` exists to hold, on one profile.

    A customer with no card yet and an income a lender can barely see is routed to
    the secured card whatever else clears, the band names how wide the shelf is
    rather than a decision, and nothing that leaves carries a number a bureau
    would recognise."""
    verdict = assess(employment="salaried", income_band="25k_60k", existing_cards="none")
    assert verdict.band == "secured"
    assert verdict.prefer_secured is True
    assert "vantage_rise" in verdict.eligible_card_ids
    assert verdict.line_spoken == "eighty percent of your fixed deposit"
    assert not any("score" in reason.lower() for reason in verdict.reasons), verdict.reasons
    assert not hasattr(verdict, "score")

    ranked = shortlist(verdict, "online")
    assert ranked.recommended_id == "vantage_rise"
    # Three cards even when only two clear: the customer sees where they can go
    # next, and the screen says which is which.
    assert len(ranked.rows) == 3
    assert [row.eligible for row in ranked.rows] == [True, True, False]


async def test_eligibility_and_the_shortlist_land_on_the_totem() -> None:
    """The verdict and the ranking, as the frontend store receives them.

    The shortlist payload is the demo's widest surface — nine fields on three
    cards — and every one of them is a display string. If a spoken form leaked
    into it the screen would read "eighty percent of your fixed deposit" where the
    design has ``80% of your fixed deposit``, and nothing else would notice."""
    llm = _full_flow_llm()
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        await _drive_discovery(rig)

        verdict = rig.command("show_eligibility")
        assert verdict["band"] == "standard"
        assert verdict["line_estimate"] == "2x to 3x your monthly income"
        assert "Salaried income" in verdict["reasons"]
        assert not any("score" in reason.lower() for reason in verdict["reasons"])

        picked = await rig.driver.user_says("Which one would you pick?")
        check_turn(rig, picked, units=1)
        board = rig.command("show_shortlist")
        assert [c["id"] for c in board["cards"]] == [
            "vantage_fuel",
            "vantage_everyday",
            "vantage_rise",
        ]
        assert board["recommended_id"] == "vantage_fuel"
        assert all(c["eligible"] for c in board["cards"])

        fuel = board["cards"][0]
        assert fuel["name"] == "Vantage Fuel"
        assert fuel["fee"] == "₹500 a year"
        assert fuel["waiver"] == "Waived on ₹1,00,000 spend a year"
        assert fuel["reward"] == "4% at any pump, up to ₹400 a month"
        assert fuel["line_estimate"] == "2x your monthly income"
        # Every declared field is emitted, including the ones the screen may not
        # use — the generated TypeScript narrows on the whole model.
        assert set(fuel) == set(CardView.model_fields)

    # The wire and the pure function agree, which is what "the rules are Python"
    # has to mean: the brain ran them, it did not restate them.
    expected = shortlist(assess(**_only_rules(_SALARIED_FUEL)), "fuel")
    assert [row.card.id for row in expected.rows] == [c["id"] for c in board["cards"]]
    assert expected.recommended_id == board["recommended_id"]


def _only_rules(profile: dict[str, str]) -> dict[str, Any]:
    """The three fields ``assess`` takes; spend is the shortlist's, not the gate's."""
    return {k: v for k, v in profile.items() if k != "spend_category"}


# ─── Confirmation, spoken ─────────────────────────────────────────────────────


def _mobile_script(*confirmations: tuple[str, str]) -> dict[str, Any]:
    """Capture a mobile number, then answer the read-back ``len(confirmations)``
    times. Each entry is ``(what the customer says, what Tanvi says next)``."""
    script: dict[str, Any] = {
        "My number is nine eight seven six five four three two one zero.": [
            call("capture_value", heard={"field": "mobile", "value": "98765 43210"}),
            reply("Nine eight seven six five, four three two one zero. Is that right?"),
        ],
    }
    for heard, spoken in confirmations:
        script[heard] = [
            call("confirm", check={"field": "mobile", "value": "9876543210", "heard": heard}),
            reply(spoken),
        ]
    return script


async def test_a_clear_yes_settles_a_value_read_back_aloud() -> None:
    """The cubicle is private, so the number is spoken and the yes is spoken.

    Two things are asserted on the way: the totem shows the *masked* form at rest,
    and the SAY line the brain handed the model is the number in words. A screen
    string reaching the TTS here is the demo's loudest failure and the transcript
    would be perfect."""
    llm = ScriptedGemini(_mobile_script(("Yes, that's right.", "Thank you.")))
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()

        check_turn(
            rig,
            await rig.driver.user_says(
                "My number is nine eight seven six five four three two one zero."
            ),
        )
        (heard,) = _payloads(rig, "confirm_value")
        assert heard["state"] == "confirming"
        assert heard["masked"] == "XXXXX 43210", "the totem is showing the whole number"
        assert heard["display"] == "98765 43210"

        check_turn(rig, await rig.driver.user_says("Yes, that's right."))
        states = [p["state"] for p in _payloads(rig, "confirm_value")]
        assert states == ["confirming", "confirmed"]
        assert rig.brain.confirmed == {"mobile"}
        assert rig.brain.reasked == set(), "a clear yes was re-asked"

    say = " ".join(_say_lines(llm))
    assert "nine eight seven six five, four three two one zero" in say
    assert "9876543210" not in say and "98765" not in say


async def test_an_unclear_reply_is_asked_again_once_and_only_once() -> None:
    """The loop that defines a bad voice bot, bounded in Python.

    "I think so" is a hedge, not a yes, so it is asked once more. The *second*
    unclear reply is taken as heard and the call moves on — there is no tap gate
    behind this and no third attempt, because repeated "sorry, I didn't catch
    that" is the sound the whole demo is built to avoid."""
    llm = ScriptedGemini(
        _mobile_script(
            ("I think so.", "Let me put it another way — is that the number you use?"),
            ("Umm, hang on.", "I'll take that as right. Moving on."),
        )
    )
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says(
            "My number is nine eight seven six five four three two one zero."
        )

        check_turn(rig, await rig.driver.user_says("I think so."))
        assert rig.brain.reasked == {"mobile"}
        assert "mobile" not in rig.brain.confirmed
        assert [p["state"] for p in _payloads(rig, "confirm_value")] == [
            "confirming",
            "confirming",
        ]

        check_turn(rig, await rig.driver.user_says("Umm, hang on."))
        assert rig.brain.confirmed == {"mobile"}
        assert [p["state"] for p in _payloads(rig, "confirm_value")] == [
            "confirming",
            "confirming",
            "confirmed",
        ]
        await _one_more_turn(rig)

    verdicts = [r for r in _tool_results(llm) if "clear yes" in r or "asked once already" in r]
    assert len(verdicts) == 2, verdicts
    assert "Not a clear yes" in verdicts[0]
    assert "do not ask a third time" in verdicts[0]
    assert "Taking it as heard" in verdicts[1]


async def test_a_correction_embedded_in_the_answer_is_not_a_yes() -> None:
    """The fourth way a confirmation goes wrong, and the only one a yes-token
    check alone would miss: they said yes *and* gave a different number in the
    same breath."""
    llm = ScriptedGemini(
        _mobile_script(("Yes — well, no, it's 9876543211.", "Let me read that back again."))
    )
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says(
            "My number is nine eight seven six five four three two one zero."
        )
        await rig.driver.user_says("Yes — well, no, it's 9876543211.")
        assert rig.brain.reasked == {"mobile"}
        assert "mobile" not in rig.brain.confirmed


# ─── Language ─────────────────────────────────────────────────────────────────


async def test_switching_to_hindi_moves_both_legs_together() -> None:
    """One ``session.configure``, so the pair cannot half-apply.

    Moving only the voice leaves the recognizer hearing Devanagari as English for
    the rest of the call, and every later reply is generated from that wrong
    transcript. Tanvi is one person in two languages, so the *voice* must not
    move with the language."""
    llm = ScriptedGemini(
        {
            "क्या हम हिंदी में बात कर सकते हैं?": [
                call("switch_language", to={"language": "Hindi"}),
                reply("ज़रूर, हिंदी में बात करते हैं।"),
            ],
        }
    )
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        check_voice_pair(rig, voice=VOICE, language="en")

        turn = await rig.driver.user_says("क्या हम हिंदी में बात कर सकते हैं?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice=VOICE, language="hi")
        assert rig.brain.language == "Hindi"


def _legs(rig: DemoRig) -> tuple[str, str, str]:
    """The voice, the spoken language and the heard language now on the wire.

    Read separately rather than through ``check_voice_pair``, which takes one
    language for both legs: a language with no clip of its own is *meant* to be
    heard in one language and spoken in another."""
    configs = _configs(rig)
    return (
        _last(configs, lambda c: c.tts.voice if c.tts else None),
        _last(configs, lambda c: c.tts.language if c.tts else None),
        _last(configs, lambda c: c.stt.language if c.stt else None),
    )


async def test_a_customer_already_speaking_tamil_moves_the_kiosk_without_asking() -> None:
    """Auto-detection: nobody asked for Tamil. The customer simply answered in it,
    the model heard it, and both legs moved — with the page told, so the chip can
    show the customer what the kiosk decided it heard."""
    llm = ScriptedGemini(
        {
            "நான் ஒரு கிரெடிட் கார்டு பார்க்கிறேன்": [
                call("switch_language", to={"language": "Tamil"}),
                reply("சரி, தமிழில் பேசலாம்."),
            ],
        }
    )
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        check_voice_pair(rig, voice=VOICE, language="en")

        await rig.driver.user_says("நான் ஒரு கிரெடிட் கார்டு பார்க்கிறேன்")
        check_voice_pair(rig, voice=VOICE, language="ta")
        assert rig.brain.language == "Tamil"
        changed = rig.command("language_changed")
        assert changed == {"language": "Tamil", "screen_language": "en"}, (
            "no Tamil screen exists, so the screen keeps its English copy"
        )


async def test_a_language_with_no_clip_is_heard_in_it_and_answered_in_hindi() -> None:
    """Odia: the recognizer understands it and no voice speaks it. The honest
    configuration is split on purpose — heard in Odia, answered in Hindi — and the
    model is told to say so rather than let the customer discover it."""
    llm = ScriptedGemini(
        {
            "ମୁଁ ଗୋଟିଏ କ୍ରେଡିଟ୍ କାର୍ଡ ଚାହୁଁଛି": [
                call("switch_language", to={"language": "Odia"}),
                reply("मैं आपकी बात समझता हूँ और हिंदी में जवाब दूँगा।"),
            ],
            # A tool's result reaches the model on the *next* request, so one more
            # turn is what puts it in the record to read.
            "ଠିକ ଅଛି": [reply("ठीक है।")],
        }
    )
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("ମୁଁ ଗୋଟିଏ କ୍ରେଡିଟ୍ କାର୍ଡ ଚାହୁଁଛି")
        voice, spoken, heard = _legs(rig)
        assert (voice, spoken, heard) == (VOICE, "hi", "or"), (voice, spoken, heard)
        await rig.driver.user_says("ଠିକ ଅଛି")
        told = next(r for r in _tool_results(llm) if "Odia" in r)
        assert "answering in Hindi" in told and "SAY:" in told


async def test_the_language_can_go_back_and_forth_and_back_to_english() -> None:
    """A switch is not one-way. English is a row in the table like any other, so a
    customer who tried Hindi and wants English back gets both legs back — and the
    page is told every time, so the chip never shows a language the call has left."""
    llm = ScriptedGemini(
        {
            "हिंदी में बात करो": [call("switch_language", to={"language": "Hindi"}), reply("ठीक है।")],
            "Can we go back to English please": [
                call("switch_language", to={"language": "English"}),
                reply("Sure."),
            ],
            "தமிழ்ல பேசலாமா": [call("switch_language", to={"language": "Tamil"}), reply("சரி.")],
            "English again": [
                call("switch_language", to={"language": "English"}),
                reply("Of course."),
            ],
        }
    )
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        for said, language, code in [
            ("हिंदी में बात करो", "Hindi", "hi"),
            ("Can we go back to English please", "English", "en"),
            ("தமிழ்ல பேசலாமா", "Tamil", "ta"),
            ("English again", "English", "en"),
        ]:
            await rig.driver.user_says(said)
            check_voice_pair(rig, voice=VOICE, language=code)
            assert rig.brain.language == language, (said, rig.brain.language)
        told = [
            c["payload"]["language"]
            for c in rig.driver.ui_commands
            if c.get("command") == "language_changed"
        ]
        assert told == ["Hindi", "English", "Tamil", "English"]


async def test_the_language_chip_moves_the_voice_too_and_says_nothing() -> None:
    """The chip used to change the screen's copy and leave Tanvi speaking English.
    Now it moves both legs — and, like every other gesture, it never takes the
    floor."""
    async with demo("kiosk", ScriptedGemini({})) as rig:
        await rig.driver.start_session()
        said = _spoken(rig)

        await _by_hand(rig, "language_picked", {"language": "Hindi"})
        check_voice_pair(rig, voice=VOICE, language="hi")
        assert rig.brain.language == "Hindi"
        assert rig.command("language_changed")["screen_language"] == "hi"
        assert _spoken(rig) == said, "the chip took the floor"


async def test_the_picker_reaches_any_language_not_just_hindi() -> None:
    """The picker lists every language the brain declares, so it can reach one the
    old two-way toggle never could. Kannada has a clip of its own, so both legs
    land on Kannada and the screen keeps its English copy."""
    async with demo("kiosk", ScriptedGemini({})) as rig:
        await rig.driver.start_session()
        said = _spoken(rig)

        await _by_hand(rig, "language_picked", {"language": "Kannada"})
        check_voice_pair(rig, voice=VOICE, language="kn")
        assert rig.brain.language == "Kannada"
        assert rig.command("language_changed") == {"language": "Kannada", "screen_language": "en"}
        assert _spoken(rig) == said, "the picker took the floor"

        # And back, which is how a customer undoes a switch they did not want.
        await _by_hand(rig, "language_picked", {"language": "English"})
        check_voice_pair(rig, voice=VOICE, language="en")


async def test_picking_the_current_language_again_configures_nothing() -> None:
    """A second tap on the language already in use is not a second request."""
    async with demo("kiosk", ScriptedGemini({})) as rig:
        await rig.driver.start_session()
        before = len(_configs(rig))
        await _by_hand(rig, "language_picked", {"language": "English"})
        assert len(_configs(rig)) == before


async def test_a_hindi_yes_reads_as_a_yes() -> None:
    """The recognizer returns what was said, so a Hindi confirmation comes back in
    Devanagari and a romanised "haan" never appears in it. A yes-set with only the
    Latin half reads every Hindi yes as unclear — which is the one failure this
    whole confirmation step exists to avoid."""
    llm = ScriptedGemini(_mobile_script(("हाँ, बिल्कुल सही।", "धन्यवाद।")))
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session(init={"language": "Hindi"})
        await rig.driver.user_says(
            "My number is nine eight seven six five four three two one zero."
        )
        await rig.driver.user_says("हाँ, बिल्कुल सही।")
        assert rig.brain.confirmed == {"mobile"}
        assert rig.brain.reasked == set()
        assert [p["state"] for p in _payloads(rig, "confirm_value")][-1] == "confirmed"


# ─── The screen the customer touches ──────────────────────────────────────────


async def test_a_tap_moves_the_screen_without_taking_the_floor() -> None:
    """A hand on the glass is an answer, and it must never put Tanvi's voice over
    the hand that is still moving.

    So ``on_rtvi`` moves the screen and says nothing: it folds the gesture into
    the mirror, puts one line in front of the model *naming* what they did and
    never what the screen now says, and dispatches the next row of the journey.
    The screen is read back through ``get_screen_context``, which is the only copy
    that cannot go stale."""
    llm = ScriptedGemini(
        {
            "Hello there.": [
                call("ask_profile", ask={"field": "employment", "question": "What do you do?"}),
                reply("Are you salaried, self employed, in government service, or studying?"),
            ],
            "What's next?": [
                call("get_screen_context"),
                call("ask_profile", ask={"field": "income_band", "question": "What do you earn?"}),
                reply("And roughly what comes in every month?"),
            ],
        }
    )
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Hello there.")
        said = _spoken(rig)

        moved = await _by_hand(
            rig, "profile_answered", {"field": "employment", "value": "salaried"}
        )
        assert [(name, body["field"]) for name, body in moved] == [
            ("ask_profile", "income_band")
        ], moved
        assert _spoken(rig) == said, "the gesture took the floor"
        assert rig.brain.answers["employment"] == "salaried"
        # Theirs wins: a value they chose with their own hand is not read back.
        assert "employment" in rig.brain.confirmed

        check_turn(rig, await rig.driver.user_says("What's next?"))
        await _one_more_turn(rig)

    context = _context_text(llm)
    assert "tapped their answer to the employment" in context
    assert "get_screen_context" in context
    assert "salaried" not in context, "the change note is carrying the value"

    screen = " ".join(r for r in _tool_results(llm) if "is on the" in r)
    assert "The customer is on the question screen." in screen
    assert "employment: salaried" in screen


def test_every_gesture_the_totem_can_send_is_in_the_vocabulary() -> None:
    """:data:`KIOSK_EVENTS` is what ``on_rtvi`` reads and what ``actions.gen.ts``
    is generated from, so a class declared and left out of it is a gesture the
    screen can send and the brain silently drops."""
    assert [event.__voqal_event__ for event in KIOSK_EVENTS] == [
        "journey_started",
        "profile_answered",
        "eligibility_acknowledged",
        "card_tapped",
        "card_detail_closed",
        "card_compared",
        "card_chosen",
        "consent_given",
        "value_entered",
        "value_confirmed",
        "value_edited",
        "restart_pressed",
        "language_picked",
    ]


async def test_start_over_is_the_only_way_back_and_it_keeps_the_language() -> None:
    """There is no idle timeout in this demo and nothing resets itself. Start over
    clears the answers, the verdict and the shortlist — and keeps the language,
    because the person who pressed it is the person still standing there."""
    llm = ScriptedGemini(
        {
            **_discovery_script(),
            "Actually, start again.": [
                call("start_over"),
                reply("Of course. Are you salaried, self employed, or studying?"),
            ],
        }
    )
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session(init={"language": "Hindi"})
        await _drive_discovery(rig)
        assert len(rig.brain.answers) == 4

        check_turn(rig, await rig.driver.user_says("Actually, start again."))
        assert rig.brain.answers == {}
        assert rig.brain.assessment is None
        assert rig.brain.shortlist_ids == ()
        assert rig.actions()[-1] == "ask_profile"
        assert rig.driver.ui_commands[-1]["payload"]["field"] == "employment"
        assert rig.brain.language == "Hindi"
        check_voice_pair(rig, voice=VOICE, language="hi")


# ─── The journey, driven by a hand alone ──────────────────────────────────────


class Step(NamedTuple):
    """One thing a customer does with their hand, and what the glass does next.

    ``lands`` is the command names, in order — the row of the brain's own
    transition table, written here from the outside so the two have to agree."""

    event: str
    payload: dict[str, Any]
    lands: tuple[str, ...]


#: The whole visit, gesture by gesture, with nothing said out loud. It is every
#: one of the twelve the totem can send, in the order a customer meets them, and
#: the walk asserts that: a gesture added to the vocabulary and not walked here
#: is one nothing proves a hand can reach.
#:
#: The two values are sent the way a keypad sends them — a mobile with the space
#: the customer typed, a PAN in the case they left it in — because normalising
#: what was pressed is the typed path's job and a half-typed value must never be
#: painted as settled.
_BY_HAND: tuple[Step, ...] = (
    Step("journey_started", {}, ("ask_profile",)),
    Step("profile_answered", {"field": "employment", "value": "salaried"}, ("ask_profile",)),
    Step("profile_answered", {"field": "income_band", "value": "25k_60k"}, ("ask_profile",)),
    Step("profile_answered", {"field": "existing_cards", "value": "one"}, ("ask_profile",)),
    Step("profile_answered", {"field": "spend_category", "value": "fuel"}, ("show_eligibility",)),
    Step("eligibility_acknowledged", {}, ("show_shortlist",)),
    Step("card_tapped", {"card_id": "vantage_fuel"}, ("open_card_detail",)),
    Step("card_detail_closed", {}, ("show_shortlist",)),
    Step("card_compared", {}, ()),
    Step("card_chosen", {"card_id": "vantage_fuel"}, ("open_consent",)),
    Step("consent_given", {"card_id": "vantage_fuel"}, ("ask_value",)),
    Step(
        "value_entered",
        {"field": "mobile", "value": "98765 43210"},
        ("confirm_value", "ask_value"),
    ),
    Step("value_confirmed", {"field": "mobile"}, ()),
    Step(
        "value_entered",
        {"field": "pan", "value": "abcde1234f"},
        ("confirm_value", "show_qr"),
    ),
    Step("value_edited", {"field": "mobile", "value": "91234 56789"}, ("confirm_value",)),
    # After the questions, so the copy asserted below is all English; before Start
    # over, so the walk also proves a restart keeps the language. The chip is not a
    # step in the journey, but it is a gesture, so it walks here with the rest.
    Step("language_picked", {"language": "Hindi"}, ("language_changed",)),
    Step("restart_pressed", {}, ("started_over", "ask_profile")),
)

#: Where the walk above stops for the takeover test: the customer has read the
#: shortlist, closed a card and come back to it, and has still said nothing.
_UPTO_THE_SHORTLIST = 1 + next(
    i for i, step in enumerate(_BY_HAND) if step.event == "card_detail_closed"
)


async def test_a_customer_who_never_speaks_walks_from_the_attract_loop_to_the_qr() -> None:
    """The hand path, end to end, with the microphone live and Tanvi silent.

    This is the demo's other half and it is asserted the way the spoken half is:
    the exact action on the glass at every step, the band and the ranking equal to
    a direct call of the pure functions, and the fees on the screen and nowhere
    else. Two things are asserted at *every* step rather than at the end, because
    both are properties of each gesture and not of the walk:

    * **Tanvi says nothing.** She greeted, once, and the wire carries no unit of
      speech after it. This is the requirement most likely to regress — the brain
      used to answer an idle tick after every tap — so the count is taken before
      the walk and compared after every gesture, not once at the finish.
    * **No model ran.** ``llm.calls`` stays empty for the whole journey. A
      transition that reached the model would be a screen that waits on a token,
      which is the thing an action exists not to be.
    """
    llm = ScriptedGemini()
    async with demo("kiosk", llm) as rig:
        greeting = await rig.driver.start_session()
        check_greeting(rig, greeting)
        after_the_greeting = _spoken(rig)
        assert len(after_the_greeting) == 1, after_the_greeting

        for step in _BY_HAND:
            landed = await _by_hand(rig, step.event, step.payload)
            assert [name for name, _ in landed] == list(step.lands), (step.event, landed)
            assert _spoken(rig) == after_the_greeting, f"{step.event}: Tanvi took the floor"
            assert llm.calls == [], f"{step.event}: a gesture reached the model"

        # The walk is the vocabulary, so a thirteenth gesture cannot be added to
        # the brain without a row here saying what it does to the screen.
        assert {step.event for step in _BY_HAND} == {e.__voqal_event__ for e in KIOSK_EVENTS}
        # And it is the same customer the spoken tests drive, so the two paths
        # cannot drift into asserting different arithmetic.
        assert {
            step.payload["field"]: step.payload["value"]
            for step in _BY_HAND
            if step.event == "profile_answered"
        } == _SALARIED_FUEL

        # The four questions, in order, in the bank's own words — a hand-driven
        # question still has copy, and no model authored a word of it.
        # The fifth is Start over, which puts the first question back.
        *asked, again = _payloads(rig, "ask_profile")
        assert [q["field"] for q in asked] == list(_SALARIED_FUEL)
        assert again["field"] == "employment"
        assert [q["question"] for q in asked] == [PROFILE_PROMPTS[q["field"]][0] for q in asked]
        assert all(q["options"] for q in asked), asked

        # The rules ran, they were not restated: the wire and the pure function.
        verdict = assess(**_only_rules(_SALARIED_FUEL))
        assert rig.command("show_eligibility") == {
            "band": verdict.band,
            "reasons": list(verdict.reasons),
            "line_estimate": verdict.line_display,
        }
        ranked = shortlist(verdict, _SALARIED_FUEL["spend_category"])
        boards = _payloads(rig, "show_shortlist")
        assert [c["id"] for c in boards[0]["cards"]] == [r.card.id for r in ranked.rows]
        assert boards[0]["recommended_id"] == ranked.recommended_id
        # An action carries the whole row, so opening a card and closing it again
        # puts back exactly what was there — the row the customer tapped does not
        # move out from under the finger still on it.
        assert len(boards) == 2 and boards[0] == boards[1], boards

        assert rig.command("open_card_detail")["card_id"] == "vantage_fuel"
        consent = rig.command("open_consent")
        assert consent["card_id"] == "vantage_fuel"
        assert consent["bullets"][-1] == (
            "Vantage Bank runs its own checks. Nothing is approved at this kiosk."
        )

        # Two keypads, in order, each labelled in this session's language.
        keypads = _payloads(rig, "ask_value")
        assert [(k["field"], k["kind"]) for k in keypads] == [("mobile", "tel"), ("pan", "text")]
        assert [k["label"] for k in keypads] == [
            VALUE_PROMPTS["mobile"][0],
            VALUE_PROMPTS["pan"][0],
        ]

        # A value the customer typed is theirs and settles on the spot — it is
        # never read back, because asking them to confirm their own keystrokes is
        # the kiosk redoing work the human has already done. What the keypad sent
        # is normalised on the way in, so the masked form cannot slice a string
        # that still has the customer's spacing in it.
        settled = _payloads(rig, "confirm_value")
        assert [(v["field"], v["state"]) for v in settled] == [
            ("mobile", "confirmed"),
            ("pan", "confirmed"),
            ("mobile", "confirmed"),
        ]
        assert (settled[0]["display"], settled[0]["masked"]) == ("98765 43210", "XXXXX 43210")
        assert (settled[1]["display"], settled[1]["masked"]) == ("ABCDE1234F", "ABCDEXXXXF")
        assert (settled[2]["display"], settled[2]["masked"]) == ("91234 56789", "XXXXX 56789")

        assert rig.command("show_qr")["caption"] == "Vantage Fuel. Show this at the desk."
        # Start over is the only way back, and it is the last thing the walk does:
        # the first question again, in the language picked just before it.
        assert rig.actions()[-1] == "ask_profile"
        assert rig.driver.ui_commands[-1]["payload"]["field"] == "employment"
        assert rig.brain.language == "Hindi"
        assert rig.brain.answers == {} and rig.brain.assessment is None

    assert llm.calls == [], "a hand-driven journey called the model"


async def test_an_idle_kiosk_is_a_silent_one_however_long_the_customer_takes() -> None:
    """The one Tanvi used to get wrong, and the only place it is visible.

    ``on_rtvi`` cannot speak — it is not a generator — so a gesture could never
    take the floor directly. What it *could* do, and used to, was leave a reply
    owed and have the next idle tick pay it: a customer filling the kiosk in with
    their hands was commented at, tap by tap, a beat behind their own finger.
    The idle turn is therefore the only frame that can catch this, and it is
    driven here at the three moments that mattered — before a gesture, after one,
    and with the shortlist on the glass."""
    llm = ScriptedGemini()
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        said = _spoken(rig)

        walked = 0
        for upto in (0, 1, _UPTO_THE_SHORTLIST):
            for step in _BY_HAND[walked:upto]:
                await _by_hand(rig, step.event, step.payload)
            walked = upto
            idle = await rig.driver.user_idle(timeout=0.5)
            assert idle.units == [], f"Tanvi answered the silence after {walked} gesture(s)"

        assert _spoken(rig) == said, "Tanvi spoke without being spoken to"
        assert llm.calls == [], "an idle tick reached the model"


async def test_a_quiet_customer_gets_the_first_question_without_a_word() -> None:
    """Start is the only way in, and nothing after it asks for a tap. The greeting
    asks for a name; a customer who does not give one gets the first question's
    answers on the glass at the first quiet moment — silently, with no model
    call — and only once, however long the quiet lasts."""
    llm = ScriptedGemini()
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        said = _spoken(rig)
        assert "ask_profile" not in rig.actions()

        await rig.driver.user_idle(timeout=0.5)
        await rig.driver.user_idle(timeout=0.5)

        asked = _payloads(rig, "ask_profile")
        assert [q["field"] for q in asked] == ["employment"], asked
        assert _spoken(rig) == said, "Tanvi spoke into the quiet"
        assert llm.calls == [], "the quiet reached the model"


async def test_a_word_after_a_silent_run_reaches_tanvi_with_the_whole_visit_behind_it() -> None:
    """The customer fills the kiosk in themselves, then says "hey Tanvi" — and she
    answers with the visit already in front of her.

    This is what the per-gesture note buys. Each one costs tokens rather than a
    turn, so a customer who never needed her paid nothing for them; the moment
    they do, her first request already carries every gesture, in order, in the
    customer's own voice. The notes *name* what they did and carry no value — the
    screen itself is read back through ``get_screen_context``, which is the only
    copy that cannot go stale."""
    llm = ScriptedGemini(
        {
            "Hey Tanvi, which of these is cheapest?": [
                call("get_screen_context"),
                reply("The Vantage Everyday asks no fee at all, and it is on your screen."),
            ],
        }
    )
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        for step in _BY_HAND[:_UPTO_THE_SHORTLIST]:
            await _by_hand(rig, step.event, step.payload)
        assert llm.calls == [], "the silent run reached the model"
        assert len(_spoken(rig)) == 1, "Tanvi spoke before she was spoken to"

        spoken_to = await rig.driver.user_says("Hey Tanvi, which of these is cheapest?")
        check_turn(rig, spoken_to, units=1)
        await _one_more_turn(rig)

    # Her first request of the session is the turn they finally gave her, and the
    # eight gestures before it are already in it.
    opening = _user_text(llm.captured_contents[0])
    for note in (
        "touched the screen to begin",
        "tapped their answer to the employment",
        "tapped their answer to the income band",
        "tapped their answer to the existing cards",
        "tapped their answer to the spend category",
        "read what they are likely eligible for and moved on",
        "opened one of the cards themselves",
        "closed the card and went back to the three",
    ):
        assert note in opening, note
    assert "Hey Tanvi" in opening
    for value in ("salaried", "25k_60k", "vantage_fuel"):
        assert value not in opening, f"a change note is carrying {value!r}"

    # And she reads the glass rather than remembering it — what a hand put there
    # is what she is looking at.
    screen = " ".join(r for r in _tool_results(llm) if "is on the" in r)
    assert "The customer is on the shortlist screen." in screen
    assert "vantage_fuel" in screen


# ─── The end of the visit ─────────────────────────────────────────────────────


async def test_a_card_that_is_not_on_the_shortlist_is_refused() -> None:
    """The guard that stops an invented id, or one left over from a shortlist
    since replaced, reaching the consent panel. Retriable, and it names the way
    out."""
    llm = ScriptedGemini(
        {
            **_discovery_script(),
            "What about the Crest?": [
                call("show_shortlist"),
                call("open_consent", card={"card_id": "vantage_crest"}),
                reply("The Crest is not one of the three on your screen."),
            ],
        }
    )
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        await _drive_discovery(rig)
        check_turn(rig, await rig.driver.user_says("What about the Crest?"))
        assert "open_consent" not in rig.actions()
        await _one_more_turn(rig)
    refusal = " ".join(_tool_results(llm))
    assert "'vantage_crest' is not on the shortlist" in refusal
    assert "vantage_fuel, vantage_everyday, vantage_rise" in refusal


async def test_the_qr_ends_the_flow_after_a_spoken_yes() -> None:
    """The whole visit, ending where it is supposed to end.

    The consent bullets are written in Python so a model cannot soften a fee or
    invent a waiver, and the last one is the sentence this kiosk exists to keep
    saying. Then the QR, and nothing after it — the kiosk has no tool that can
    submit anything."""
    llm = _full_flow_llm()
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        await _drive_discovery(rig)
        await rig.driver.user_says("Which one would you pick?")
        await rig.driver.user_says("Tell me more about that one.")

        check_turn(rig, await rig.driver.user_says("I'll take it."))
        consent = rig.command("open_consent")
        assert consent["card_id"] == "vantage_fuel"
        assert consent["bullets"][0] == "Annual fee: ₹500 a year"
        assert consent["bullets"][-1] == (
            "Vantage Bank runs its own checks. Nothing is approved at this kiosk."
        )
        assert set(consent) == set(OpenConsent.model_fields)

        check_turn(rig, await rig.driver.user_says("Yes, go ahead."))
        qr = rig.command("show_qr")
        assert qr["caption"] == "Vantage Fuel. Show this at the desk."
        assert rig.brain.consented_card_id == "vantage_fuel"

        assert rig.actions() == [
            "ask_profile",
            "confirm_value",
            "ask_profile",
            "confirm_value",
            "ask_profile",
            "confirm_value",
            "ask_profile",
            "confirm_value",
            "show_eligibility",
            "show_shortlist",
            "open_card_detail",
            "open_consent",
            "show_qr",
        ], rig.actions()

        # Nothing was submitted, because there is nothing that could submit it:
        # the eleven tools are the whole of what this kiosk can do, and the last
        # one of them draws a QR code.
        assert [tool.__name__ for tool in rig.brain.tools] == [
            "start_over",
            "ask_profile",
            "capture_value",
            "confirm",
            "check_eligibility",
            "show_shortlist",
            "open_card_detail",
            "open_consent",
            "finish_with_qr",
            "get_screen_context",
            "switch_language",
        ]


# ─── The rule the whole demo rests on ─────────────────────────────────────────

#: A digit, a rupee sign, a percent sign, a multiplication ex or an em-dash, read
#: aloud, is gibberish — "five percent sign", "two minus three ex", "one five
#: zero comma zero zero zero". Every one of them is a display form, and the shelf
#: carries a spoken twin for each.
#: ``\u00d7`` is the multiplication sign, spelled as an escape because it is the
#: character a linter cannot tell apart from a letter x — which is the point.
_DISPLAY_ONLY = re.compile(r"[₹%\u00d7—]|\d")

#: The wire tokens of the four closed vocabularies that would read as a phrase
#: with the word "underscore" in the middle of it. Every one is mapped to a
#: spoken phrase in ``cards.py`` before anything interpolates it into a sentence.
_WIRE_TOKENS = tuple(
    token
    for tokens in (EMPLOYMENT_SPOKEN, INCOME_BAND_SPOKEN, EXISTING_CARDS_SPOKEN, SPEND_SPOKEN)
    for token in tokens
    if "_" in token
)

#: Words this kiosk does not use. It never approves anything and it says so.
_BANNED = ("instant", "guaranteed", "approved", "magic", "effortless")


#: Tool results that told Tanvi to (re)state a question. Each one made her say a
#: question twice: she had already asked it before calling the tool that said so.
_ASKS_AGAIN = re.compile(
    r"SAY:\s*your question|then your next question|then carry on|"
    r"move straight to the next step|and ask the first question",
    re.IGNORECASE,
)


async def test_no_tool_tells_tanvi_to_ask_a_question_again() -> None:
    """The repeat bug, pinned at its cause. A live session had Tanvi ask one
    question two and three times in a row: the prompt said to ask it before
    calling ``ask_profile``, and the tool's result said to ask it again. A question
    now has exactly one home — ``ask_profile`` — and its result lets her say
    nothing more if she already asked."""
    llm = _full_flow_llm()
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        await _drive_discovery(rig)
        await rig.driver.user_says("Which one would you pick?")
        await _one_more_turn(rig)

    results = _tool_results(llm)
    assert results, "the walk reached no tools"
    for result in results:
        assert not _ASKS_AGAIN.search(result), f"a tool asked for a question again: {result!r}"
    asked = [r for r in results if r.startswith("Shown.")]
    assert asked and all("say nothing more" in r for r in asked), asked


async def test_nothing_the_brain_tells_tanvi_to_say_is_a_display_string() -> None:
    """The sweep. Every ``SAY:`` span the brain writes across a whole visit, swept
    for the figures and the raw tokens that belong only on the glass.

    ``SAY:`` now introduces only text Tanvi is to *speak*: the eligibility verdict,
    the recommendation, the card's perk, the card being agreed to and the QR line
    — the five tools this walk reaches that quote the card shelf. The generic
    directions ("a three-word acknowledgement", "your question") lost their
    ``SAY:`` because they were what made Tanvi ask the same question twice: a
    tool told her to say something she had already said before calling it.

    This is the check that cannot be written per call site: the failure is one
    interpolation in one branch of one tool, and it is heard exactly once, in
    front of a customer."""
    llm = _full_flow_llm()
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        await _drive_discovery(rig)
        await rig.driver.user_says("Which one would you pick?")
        await rig.driver.user_says("Tell me more about that one.")
        await rig.driver.user_says("I'll take it.")
        await rig.driver.user_says("Yes, go ahead.")
        await _one_more_turn(rig)

    lines = _say_lines(llm)
    # One per content tool the walk reaches, so the sweep cannot pass empty.
    assert len(lines) >= 5, lines
    for line in lines:
        assert not _DISPLAY_ONLY.search(line), f"a display string reached a SAY line: {line!r}"
        for token in _WIRE_TOKENS:
            assert token not in line, f"the wire token {token!r} reached a SAY line: {line!r}"
        for word in _BANNED:
            assert word not in line.lower(), f"{word!r} in a SAY line: {line!r}"


def test_the_sweep_can_fail() -> None:
    """The negative control: a green sweep would read as proof, so assert the probe
    rejects each shape it exists to catch, and passes the spoken twin of it."""
    for bad in ("₹500 a year", "5% online", "2x your income", "up to 400 a month"):
        assert _DISPLAY_ONLY.search(bad), bad
    assert "self_employed" in _WIRE_TOKENS and "25k_60k" in _WIRE_TOKENS
    assert not _DISPLAY_ONLY.search(
        " the Vantage Fuel is your best fit, because you spend most on fuel."
    )


# ─── The typed contract ───────────────────────────────────────────────────────


def test_an_action_wire_name_is_the_snake_case_of_its_class() -> None:
    """Declared once: the class name *is* the command name, so nothing about the
    contract is written down twice and the generated TypeScript narrows on the
    same union this brain defines."""
    assert AskProfile.__voqal_action__ == "ask_profile"
    assert ConfirmValue.__voqal_action__ == "confirm_value"
    assert ShowEligibility.__voqal_action__ == "show_eligibility"
    assert ShowShortlist.__voqal_action__ == "show_shortlist"
    assert ShowQr.__voqal_action__ == "show_qr"
