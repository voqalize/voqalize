"""The Vantage Bank branch kiosk, end to end over the wire — no network, no key.

The real ``KioskBrain`` — the shipping ``demos/kiosk/backend/brain.py``, its real
prompt, its real gestures, its real Python rules — hosted on a real
``brain_server`` socket and driven by the conformance ``VoqalizeDriver``, with only
the *model* scripted. See ``tests/_harness.py`` for what every demo's e2e proves.

**The screen runs the form; Tanvi helps.** So the claims here are mostly about
what she *cannot* do, because those are the ones a prompt cannot hold:

* **Her tools are gestures.** Every one builds the event a tap would and goes
  through ``apply_event``; none dispatches to the glass itself, none takes a
  string that could end up on it, and none reaches the mobile number, the PAN or
  the consent.
* **The screen is English.** A language switch moves her voice and her ears and
  never the glass.
* **She is quiet while the form is filled.** A hand walks from the first question
  to the QR without a word from her; a spoken answer gets a word or two; the line
  about the top card is said once per shortlist, whichever way it went up.
* **The screen reaches her read-only, every turn** — in front of the customer's
  words, and gone from the context when the turn is over.

And two older ones: the arithmetic is Python, and every figure the voice is handed
is in words.

Run: ``cd demos && uv run pytest tests/test_kiosk_e2e.py``
"""

from __future__ import annotations

import asyncio
import inspect
import re
import time
import typing
from typing import Any, NamedTuple, get_args

import pytest
from voqalize_demos import PHRASES
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, call, reply, reply_and_call

from voqalize.sdk.gemini import _needs_result_now
from voqalize.sdk.wire import Language

from ._harness import DemoRig, _configs, _last, check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.kiosk import brain as kiosk  # noqa: E402
from voqalize_demos._loaded.kiosk.brain import (  # noqa: E402
    HAND_ONLY,
    KIOSK_EVENTS,
    TANVI_GESTURES,
    AskProfile,
    ConfirmValue,
    ConsentGiven,
    ShowEligibility,
    ShowQr,
    ShowShortlist,
)
from voqalize_demos._loaded.kiosk.cards import (  # noqa: E402
    CARDS,
    EMPLOYMENT_SPOKEN,
    EXISTING_CARDS_SPOKEN,
    INCOME_BAND_SPOKEN,
    PROFILE_PROMPTS,
    SPEND_SPOKEN,
    VALUE_PROMPTS,
)
from voqalize_demos._loaded.kiosk.eligibility import assess, shortlist  # noqa: E402
from voqalize_demos._loaded.kiosk.pitch import pitch_line  # noqa: E402
from voqalize_demos._loaded.kiosk.prompts import GREETING, SYSTEM_INSTRUCTION  # noqa: E402

#: One person, every language — the clip does not change when the language does.
VOICE = "omnivoice/gayatri"

#: The profile every flow test drives: salaried, mid band, one card already,
#: fuel is where the money goes. It lands in the *standard* band with three
#: eligible cards, so the shortlist is a real ranking rather than everything.
_SALARIED_FUEL = {
    "employment": "salaried",
    "income_band": "25k_60k",
    "existing_cards": "one",
    "spend_category": "fuel",
}

#: What the glass's own copy says, which no model wrote.
_SNAPSHOT = "What the kiosk screen shows right now:"


# ─── Reading what the brain said to the model ─────────────────────────────────
# ``dump_conversation`` does not work on a GeminiBrain demo, so everything the
# brain put in front of the model is read off the requests it made instead.


def _record(llm: ScriptedGemini) -> list[Any]:
    """The newest request's ``contents`` — the whole session, once."""
    return llm.captured_contents[-1] if llm.captured_contents else []


def _texts(contents: list[Any], role: str = "user") -> list[str]:
    """Every text part of one role in one request, in order."""
    return [
        part.text or ""
        for content in contents
        if content.role == role
        for part in content.parts or []
        if part.text
    ]


def _tool_results(llm: ScriptedGemini) -> list[str]:
    """Every tool result the brain handed the model, in order, once each. A
    return is wrapped as ``{"result": ...}``, so unwrap that one level."""
    return [
        str((part.function_response.response or {}).get("result", ""))
        for content in _record(llm)
        for part in content.parts or []
        if part.function_response is not None
    ]


def _spoken(rig: DemoRig) -> list[str]:
    """Every unit of speech Tanvi has put on the wire so far, in order. This list
    not growing across a gesture is what "she stayed quiet" means on the wire."""
    return [unit.text for turn in rig.driver.turns.values() for unit in turn.units]


async def _by_hand(
    rig: DemoRig, event: str, payload: dict[str, Any] | None = None
) -> list[tuple[str, dict[str, Any]]]:
    """One gesture, and everything it put on the glass, in order.

    ``on_rtvi`` takes no floor, so there is no bracket to wait on and nothing to
    await but the clock."""
    before = len(rig.driver.ui_commands)
    await rig.driver.send_ui_event(event, payload or {})
    await asyncio.sleep(0.1)
    return [
        (str(c.get("command")), dict(c.get("payload") or {}))
        for c in rig.driver.ui_commands[before:]
        if not str(c.get("command", "")).startswith("__")
    ]


def _payloads(rig: DemoRig, action: str) -> list[dict[str, Any]]:
    """Every payload the brain fired under one command name, in order."""
    return [
        dict(c.get("payload") or {}) for c in rig.driver.ui_commands if c.get("command") == action
    ]


def _idle_ms(rig: DemoRig) -> int | None:
    """The idle clock as the brain last set it."""
    return _last(_configs(rig), lambda c: c.idle.timeout_ms if c.idle else None)


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


def _only_rules(profile: dict[str, str]) -> dict[str, Any]:
    """The three fields ``assess`` takes; spend is the shortlist's, not the gate's."""
    return {k: v for k, v in profile.items() if k != "spend_category"}


def _english_pitch(profile: dict[str, str] = _SALARIED_FUEL) -> str:
    ranked = shortlist(assess(**_only_rules(profile)), profile["spend_category"])  # type: ignore[arg-type]
    line = pitch_line(ranked, profile["spend_category"], Language.EN)  # type: ignore[arg-type]
    assert line is not None
    return line


# ─── The journey, driven by a hand alone ──────────────────────────────────────


class Step(NamedTuple):
    """One thing a customer does with their hand, and what the glass does next.

    ``lands`` is the command names, in order — the row of the brain's own
    transition table, written here from the outside so the two have to agree."""

    event: str
    payload: dict[str, Any]
    lands: tuple[str, ...]


#: The whole visit, gesture by gesture, with nothing said out loud — every
#: gesture the totem can send, in the order a customer meets them. The values are
#: sent as a keypad sends them, spacing and case and all.
_BY_HAND: tuple[Step, ...] = (
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
    Step("value_entered", {"field": "pan", "value": "abcde1234f"}, ("confirm_value", "show_qr")),
    Step("value_edited", {"field": "mobile", "value": "91234 56789"}, ("confirm_value",)),
    Step("restart_pressed", {}, ("started_over", "ask_profile")),
)

_UPTO_THE_CARDS = 1 + next(
    i for i, step in enumerate(_BY_HAND) if step.event == "eligibility_acknowledged"
)


async def _walk(rig: DemoRig, upto: int = len(_BY_HAND)) -> None:
    for step in _BY_HAND[:upto]:
        await _by_hand(rig, step.event, step.payload)


async def test_the_kiosk_greets_puts_the_form_up_and_both_legs_reach_the_wire() -> None:
    """A walk-in gets the English opener, the first question is on the glass as
    it is said, and both halves of the language land before that audio. ``greet``
    makes no model call."""
    llm = ScriptedGemini()
    async with demo("kiosk", llm) as rig:
        greeting = await rig.driver.start_session()
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text == GREETING["English"]
        check_voice_pair(rig, voice=VOICE, language="en")
        assert rig.actions() == ["ask_profile"]
        assert rig.command("ask_profile")["field"] == "employment"
        assert llm.calls == [], "greet() called the model"


def test_the_opener_is_an_ai_that_asks_for_nothing() -> None:
    """Tanvi says she is an AI in her first sentence, in both languages, and asks
    no question: the form is up, so the next move is the customer's hand. Not
    their name either — the form never uses it."""
    for language, opener in GREETING.items():
        first = re.split(r"[.।]", opener)[0]
        assert ("AI" in first) or ("ए आई" in first), (language, first)
        assert "?" not in opener, (language, opener)
        assert "name" not in opener.lower() and "नाम" not in opener, (language, opener)


async def test_the_page_can_open_the_call_in_hindi_and_nothing_else() -> None:
    """The greeting is written in English and Hindi, so those are the languages
    a session may open in. Anything else greets in English — a kiosk that opens in
    the wrong language is recoverable; one that refuses to open is not."""
    async with demo("kiosk", ScriptedGemini()) as rig:
        greeting = await rig.driver.start_session(init={"language": "Hindi"})
        assert greeting is not None and greeting.text == GREETING["Hindi"]
        check_voice_pair(rig, voice=VOICE, language="hi")
        # The screen does not follow: the first question is the bank's English.
        assert rig.command("ask_profile")["question"] == PROFILE_PROMPTS["employment"]
    async with demo("kiosk", ScriptedGemini()) as rig:
        greeting = await rig.driver.start_session(init={"language": "Klingon"})
        assert greeting is not None and greeting.text == GREETING["English"]
        check_voice_pair(rig, voice=VOICE, language="en")


async def test_a_customer_who_never_speaks_walks_from_the_first_question_to_the_qr() -> None:
    """The hand path, end to end, with the microphone live and Tanvi silent.

    Asserted at every step, because both are properties of each gesture: the
    exact action on the glass, and that Tanvi said nothing and no model ran."""
    llm = ScriptedGemini()
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        after_the_greeting = _spoken(rig)

        for step in _BY_HAND:
            landed = await _by_hand(rig, step.event, step.payload)
            assert [name for name, _ in landed] == list(step.lands), (step.event, landed)
            assert _spoken(rig) == after_the_greeting, f"{step.event}: Tanvi took the floor"
            assert llm.calls == [], f"{step.event}: a gesture reached the model"

        # The walk is the vocabulary: a gesture cannot be added to the brain
        # without a row here saying what it does to the screen.
        assert {step.event for step in _BY_HAND} == {e.__voqal_event__ for e in KIOSK_EVENTS}

        # The questions, in order, in the bank's own English, and Start over puts
        # the first one back.
        first, *asked, again = _payloads(rig, "ask_profile")
        assert [q["field"] for q in [first, *asked]] == list(_SALARIED_FUEL)
        assert again["field"] == "employment"
        assert [q["question"] for q in [first, *asked]] == [
            PROFILE_PROMPTS[f] for f in _SALARIED_FUEL
        ]
        assert all(set(o) == {"value", "label"} for q in asked for o in q["options"]), asked

        # The rules ran, they were not restated: the wire and the pure function.
        verdict = assess(**_only_rules(_SALARIED_FUEL))
        assert rig.command("show_eligibility") == {
            "band": verdict.band,
            "reasons": list(verdict.reasons),
            "line_estimate": verdict.line_display,
        }
        ranked = shortlist(verdict, "fuel")
        boards = _payloads(rig, "show_shortlist")
        assert [c["id"] for c in boards[0]["cards"]] == [r.card.id for r in ranked.rows]
        assert boards[0]["recommended_id"] == ranked.recommended_id
        assert len(boards) == 2 and boards[0] == boards[1], boards

        consent = rig.command("open_consent")
        assert consent["card_id"] == "vantage_fuel"
        assert consent["bullets"][-1] == (
            "Vantage Bank runs its own checks. Nothing is approved at this kiosk."
        )
        keypads = _payloads(rig, "ask_value")
        assert [(k["field"], k["label"], k["kind"]) for k in keypads] == [
            ("mobile", *VALUE_PROMPTS["mobile"]),
            ("pan", *VALUE_PROMPTS["pan"]),
        ]
        settled = _payloads(rig, "confirm_value")
        assert [(v["field"], v["state"]) for v in settled] == [
            ("mobile", "confirmed"),
            ("pan", "confirmed"),
            ("mobile", "confirmed"),
        ]
        assert (settled[0]["display"], settled[0]["masked"]) == ("98765 43210", "XXXXX 43210")
        assert (settled[1]["display"], settled[1]["masked"]) == ("ABCDE1234F", "ABCDEXXXXF")
        assert rig.command("show_qr")["caption"] == "Vantage Fuel. Show this at the desk."
        assert rig.brain.answers == {} and rig.brain.assessment is None

    assert llm.calls == [], "a hand-driven journey called the model"


def test_the_rules_are_pure_python_and_instant() -> None:
    """``assess`` is dictionary lookups and comparisons — no I/O, no model."""
    started = time.perf_counter()
    for _ in range(1000):
        assess(employment="salaried", income_band="25k_60k", existing_cards="one")
    assert time.perf_counter() - started < 0.5


def test_a_thin_file_is_routed_to_the_secured_card_and_never_to_a_score() -> None:
    verdict = assess(employment="salaried", income_band="25k_60k", existing_cards="none")
    assert verdict.band == "secured"
    assert "vantage_rise" in verdict.eligible_card_ids
    assert not any("score" in reason.lower() for reason in verdict.reasons), verdict.reasons
    ranked = shortlist(verdict, "online")
    assert ranked.recommended_id == "vantage_rise" and ranked.why == "secured"
    assert [row.eligible for row in ranked.rows] == [True, True, False]


# ─── Tanvi's tools are gestures ───────────────────────────────────────────────


def _tool_methods() -> list[Any]:
    return [getattr(kiosk.KioskBrain, fn.__name__) for fn in _tools_of_a_brain()]


def _tools_of_a_brain() -> list[Any]:
    brain = kiosk.KioskBrain.__new__(kiosk.KioskBrain)
    return list(kiosk.KioskBrain.tools.fget(brain))  # type: ignore[attr-defined]


def test_no_tool_touches_the_glass_or_the_hand_only_fields() -> None:
    """The model's only way to affect the screen is a customer gesture, so no
    tool body dispatches, paints, or names a gesture only a hand may make."""
    hand_only = {event.__name__ for event in HAND_ONLY}
    for tool in _tool_methods():
        source = inspect.getsource(tool)
        assert "_show(" not in source and "dispatch(" not in source, tool.__name__
        assert not any(name in source for name in hand_only), tool.__name__
        assert not _needs_result_now(tool), f"{tool.__name__} is an action, not a read"


def test_no_tool_takes_a_string_that_could_reach_the_screen() -> None:
    """Every argument of every tool is a closed vocabulary. A free string is how
    model-authored text reaches a bank's glass, so there is none to fill."""

    def closed(annotation: Any) -> bool:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if typing.get_origin(annotation) is typing.Literal:
            return True
        return bool(args) and all(closed(a) for a in args)

    for tool in _tool_methods():
        hints = typing.get_type_hints(tool)
        hints.pop("return", None)
        for model in hints.values():
            for name, field in model.model_fields.items():
                assert closed(field.annotation), f"{tool.__name__}.{name} is {field.annotation}"


def test_the_privacy_line_is_a_type_not_a_prompt() -> None:
    """Mobile, PAN and consent have no model path: the gestures split into the
    ones Tanvi may make and the ones only a hand may, and the brain refuses the
    second kind even if a future tool tried to build one."""
    assert {e.__name__ for e in HAND_ONLY} == {
        "ConsentGiven",
        "ValueEntered",
        "ValueConfirmed",
        "ValueEdited",
    }
    brain = kiosk.KioskBrain.__new__(kiosk.KioskBrain)
    with pytest.raises(TypeError, match="hand only"):
        brain._perform(ConsentGiven(card_id="vantage_fuel"))  # pyright: ignore[reportPrivateUsage]
    assert TANVI_GESTURES.isdisjoint(HAND_ONLY)


async def test_every_tool_routes_through_apply_event() -> None:
    """Each gesture tool, called by the model, reaches the glass the way a tap
    does — and the brain says it did, in the same row a tap writes."""
    llm = ScriptedGemini(
        {
            "Salaried.": reply_and_call(
                "Got it.", "answer_on_screen", answer={"employment": "salaried"}
            ),
            "About forty thousand.": reply_and_call(
                "Okay.", "answer_on_screen", answer={"income_band": "25k_60k"}
            ),
            "Just one.": reply_and_call(
                "Right.", "answer_on_screen", answer={"existing_cards": "one"}
            ),
            "Mostly fuel.": reply_and_call(
                "Thanks.", "answer_on_screen", answer={"spend_category": "fuel"}
            ),
            "Show me the cards.": reply_and_call("Here they are.", "continue_to_cards"),
            "Open the fuel one.": reply_and_call(
                "Sure.", "open_card", card={"card_id": "vantage_fuel"}
            ),
            "Go back.": reply_and_call("Okay.", "close_card"),
            "Compare them.": reply_and_call("Side by side.", "compare_cards"),
            "I'll take the fuel card.": reply_and_call(
                "Good choice.", "choose_card", card={"card_id": "vantage_fuel"}
            ),
            "Start again.": reply_and_call("Starting over.", "start_over"),
        }
    )
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        seen: list[str] = []
        real = rig.brain.apply_event

        def spy(event: Any) -> str:
            seen.append(type(event).__voqal_event__)
            return real(event)

        rig.brain.apply_event = spy  # type: ignore[method-assign]
        for line in llm_lines(llm):
            check_turn(rig, await rig.driver.user_says(line))

        assert seen == [
            "profile_answered",
            "profile_answered",
            "profile_answered",
            "profile_answered",
            "eligibility_acknowledged",
            "card_tapped",
            "card_detail_closed",
            "card_compared",
            "card_chosen",
            "restart_pressed",
        ]
        assert rig.actions()[-2:] == ["started_over", "ask_profile"]


def llm_lines(llm: ScriptedGemini) -> list[str]:
    """The script's keys, in the order they were written."""
    return list(llm._cursors)  # pyright: ignore[reportPrivateUsage]


async def test_a_gesture_a_hand_could_not_make_is_refused_and_moves_nothing() -> None:
    """Tanvi can only do what the customer's hand could do right now: answer the
    question that is up, open a card that is on the glass."""
    llm = ScriptedGemini(
        {
            "I spend on fuel.": reply_and_call(
                "Got it.", "answer_on_screen", answer={"spend_category": "fuel"}
            ),
            "Open the fuel card.": reply_and_call(
                "One moment.", "open_card", card={"card_id": "vantage_fuel"}
            ),
            "Thanks.": reply("Sure."),
        }
    )
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        before = list(rig.driver.ui_commands)
        await rig.driver.user_says("I spend on fuel.")
        await rig.driver.user_says("Open the fuel card.")
        await rig.driver.user_says("Thanks.")
        assert rig.driver.ui_commands == before, "a refused gesture moved the screen"
        assert rig.brain.answers == {}
        refused = [r for r in _tool_results(llm) if r.startswith("Not done")]
        assert len(refused) == 2, _tool_results(llm)
        assert "spend category question is not the one on the screen" in refused[0]
        assert "cards are not on the screen" in refused[1]


# ─── A spoken answer ──────────────────────────────────────────────────────────


async def test_a_spoken_answer_is_tapped_and_acknowledged_in_a_word() -> None:
    """The customer says it instead of tapping it: Tanvi taps it for them, says a
    word, and the next question comes up by itself — one request, one unit."""
    llm = ScriptedGemini(
        {
            "I'm salaried.": reply_and_call(
                "Got it.", "answer_on_screen", answer={"employment": "salaried"}
            ),
        }
    )
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        turn = await rig.driver.user_says("I'm salaried.")
        check_turn(rig, turn, units=1)
        assert [u.text for u in turn.units] == ["Got it."]
        assert len(llm.calls) == 1, "an answer asked the model twice"
        assert rig.brain.answers == {"employment": "salaried"}
        asked = _payloads(rig, "ask_profile")
        assert [q["field"] for q in asked] == ["employment", "income_band"]


async def test_an_answer_the_model_tapped_in_silence_still_gets_a_word() -> None:
    """The shared floor under every demo: a turn that acted on screen and said
    nothing speaks one written line of the brain's own, in the voice's language,
    without a second request — and the line never enters the context."""
    llm = ScriptedGemini(
        {
            "Salaried.": call("answer_on_screen", answer={"employment": "salaried"}),
            "Okay.": reply("Sure."),
        }
    )
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        turn = await rig.driver.user_says("Salaried.")
        check_turn(rig, turn, units=1)
        (line,) = (u.text for u in turn.units)
        assert line in PHRASES[Language.EN]["over_to_you"], line
        assert len(llm.calls) == 1

        await rig.driver.user_says("Okay.")
        assert line not in " ".join(_texts(_record(llm), "model"))


# ─── The screen, read-only, every turn ────────────────────────────────────────


async def test_every_turn_sees_the_screen_as_it_is_now_and_only_once() -> None:
    """The snapshot sits right in front of the customer's words and is gone from
    the context once the turn is over, so no request carries a stale copy."""
    llm = ScriptedGemini(
        {
            "What's this?": reply("A short form to find you a card."),
            "Fine.": reply("Sure."),
        }
    )
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("What's this?")
        await _by_hand(rig, "profile_answered", {"field": "employment", "value": "salaried"})
        await rig.driver.user_says("Fine.")

        for request, question in zip(
            llm.captured_contents, ("employment", "income band"), strict=True
        ):
            notes = [t for t in _texts(request) if t.startswith(_SNAPSHOT)]
            assert len(notes) == 1, notes
            assert f"the question on screen: {question}" in notes[0], notes[0]
            texts = _texts(request)
            assert texts.index(notes[0]) == len(texts) - 2, "the note is not just before the words"
        second = "\n".join(_texts(llm.captured_contents[1]))
        assert "salaried" in second  # what they have told us, as it is said
        assert "The customer answered the employment: salaried." in second
        assert all(_SNAPSHOT not in t for t in _texts(rig.brain._history))  # pyright: ignore[reportPrivateUsage]


async def test_the_snapshot_never_carries_a_mobile_number_or_a_pan() -> None:
    """Typed values are the customer's. The model learns they were typed in and
    never what they are."""
    llm = ScriptedGemini({"Is that all?": reply("Nearly done.")})
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        await _walk(rig, upto=len(_BY_HAND) - 1)
        await rig.driver.user_says("Is that all?")
        note = next(t for t in _texts(_record(llm)) if t.startswith(_SNAPSHOT))
        assert "typed in" in note
        for digits in ("98765", "43210", "91234", "56789", "ABCDE", "1234"):
            assert digits not in note, note


# ─── The line about the top card ──────────────────────────────────────────────


async def test_cards_tapped_up_get_their_line_on_the_next_quiet_moment_once() -> None:
    """A tap cannot speak, so the cards going up under a hand shorten the idle
    clock, and the first quiet moment says why the top card — written, no model
    call — then puts the clock back. Closing a card and coming back owes nothing."""
    llm = ScriptedGemini()
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        await _walk(rig, upto=_UPTO_THE_CARDS)
        await asyncio.sleep(0.05)
        assert _idle_ms(rig) == kiosk._IDLE_PITCH_MS  # pyright: ignore[reportPrivateUsage]

        idle = await rig.driver.user_idle(timeout=1.0)
        assert [u.text for u in idle.units] == [_english_pitch()]
        await asyncio.sleep(0.05)
        assert _idle_ms(rig) == kiosk._IDLE_MS  # pyright: ignore[reportPrivateUsage]

        await _by_hand(rig, "card_tapped", {"card_id": "vantage_fuel"})
        await _by_hand(rig, "card_detail_closed")
        assert (await rig.driver.user_idle(timeout=0.5)).units == []
        assert llm.calls == [], "the line about the cards called the model"
        # Tanvi knows she said it: the line is hers in the context.
        assert _english_pitch() in " ".join(_texts(rig.brain._history, "model"))  # pyright: ignore[reportPrivateUsage]


async def test_cards_asked_for_out_loud_get_their_line_in_the_same_turn() -> None:
    """The customer asks to see the cards: Tanvi says a word and taps it, and the
    line about the top card follows in that same turn, once."""
    llm = ScriptedGemini(
        {"Show me the cards.": reply_and_call("Here they are.", "continue_to_cards")}
    )
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        await _walk(rig, upto=_UPTO_THE_CARDS - 1)
        turn = await rig.driver.user_says("Show me the cards.")
        check_turn(rig, turn, units=2)
        assert [u.text for u in turn.units] == ["Here they are.", _english_pitch()]
        assert (await rig.driver.user_idle(timeout=0.5)).units == []
        assert len(llm.calls) == 1


async def test_the_line_is_written_in_hindi_for_a_hindi_voice() -> None:
    async with demo("kiosk", ScriptedGemini()) as rig:
        await rig.driver.start_session(init={"language": "Hindi"})
        await _walk(rig, upto=_UPTO_THE_CARDS)
        idle = await rig.driver.user_idle(timeout=1.0)
        (line,) = (u.text for u in idle.units)
        assert "वैंटेज फ़्यूल" in line and "पेट्रोल" in line, line
        assert not re.search(r"[A-Za-z]", line), f"Latin in a Hindi line: {line!r}"


async def test_in_a_language_with_no_written_line_the_model_says_it_on_the_quiet() -> None:
    """Kannada has a voice and no written line, so the quiet moment asks the model
    to say the English line in Kannada — the one model call the line costs."""
    llm = ScriptedGemini({"The cards are up.": reply("ಇದು ನಿಮಗೆ ಉತ್ತಮ ಕಾರ್ಡ್.")})
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        brain = rig.brain
        brain._append_note(await brain._switch_to("Kannada", by="the customer"))  # pyright: ignore[reportPrivateUsage]
        await _walk(rig, upto=_UPTO_THE_CARDS)
        idle = await rig.driver.user_idle(timeout=1.0)
        assert [u.text for u in idle.units] == ["ಇದು ನಿಮಗೆ ಉತ್ತಮ ಕಾರ್ಡ್."]
        asked = " ".join(_texts(_record(llm)))
        assert "in Kannada" in asked and _english_pitch() in asked
        assert (await rig.driver.user_idle(timeout=0.5)).units == []


def test_every_line_about_a_card_is_in_words() -> None:
    """The pitch goes to the voice, so no digit, rupee sign or percent sign, and
    no wire token, for any profile the rules can produce."""
    tokens = [
        token
        for spoken in (EMPLOYMENT_SPOKEN, INCOME_BAND_SPOKEN, EXISTING_CARDS_SPOKEN, SPEND_SPOKEN)
        for token in spoken
        if "_" in token
    ]
    for employment in EMPLOYMENT_SPOKEN:
        for income in INCOME_BAND_SPOKEN:
            for cards in EXISTING_CARDS_SPOKEN:
                verdict = assess(employment=employment, income_band=income, existing_cards=cards)
                for spend in SPEND_SPOKEN:
                    ranked = shortlist(verdict, spend)
                    for language in (Language.EN, Language.HI):
                        line = pitch_line(ranked, spend, language)
                        assert line and not _DISPLAY_ONLY.search(line), line
                        assert not any(token in line for token in tokens), line


# ─── The screen is English ────────────────────────────────────────────────────


async def test_a_switch_moves_the_voice_and_the_ears_and_never_the_glass() -> None:
    llm = ScriptedGemini(
        {
            "Can we speak Hindi?": reply_and_call(
                "Sure, Hindi.", "switch_language", to={"language": "Hindi"}
            ),
            "मैं नौकरी करता हूँ।": reply_and_call(
                "ठीक है।", "answer_on_screen", answer={"employment": "salaried"}
            ),
        }
    )
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Can we speak Hindi?")
        check_voice_pair(rig, voice=VOICE, language="hi")
        await rig.driver.user_says("मैं नौकरी करता हूँ।")
        asked = _payloads(rig, "ask_profile")[-1]
        assert asked["question"] == PROFILE_PROMPTS["income_band"]
        assert all(re.fullmatch(r"[ -~]+", o["label"]) for o in asked["options"]), asked
        assert "language_changed" not in rig.actions()


def test_no_copy_on_the_glass_is_in_another_script() -> None:
    """Every string the brain can put on the screen is ASCII-and-rupee English."""
    english = re.compile("[ -~\u20b9\u2019]+")
    for question in PROFILE_PROMPTS.values():
        assert english.fullmatch(question), question
    for label, _ in VALUE_PROMPTS.values():
        assert english.fullmatch(label), label
    for card in CARDS:
        for text in (card.name, card.fee_display, card.reward_display, card.perk_display):
            assert english.fullmatch(text), text


# ─── The language moves as a pair ─────────────────────────────────────────────


async def test_a_customer_already_speaking_tamil_moves_the_kiosk_without_asking() -> None:
    heard = "நான் சம்பளம் வாங்குகிறேன்"
    llm = ScriptedGemini(
        {heard: reply_and_call("Okay, Tamil.", "switch_language", to={"language": "Tamil"})}
    )
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says(heard)
        assert _legs(rig) == (VOICE, "ta", "ta")
        assert rig.brain.language == "Tamil"


async def test_a_language_with_no_clip_is_heard_in_it_and_answered_in_hindi() -> None:
    llm = ScriptedGemini(
        {"Odia please.": reply_and_call("ठीक है।", "switch_language", to={"language": "Odia"})}
    )
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Odia please.")
        assert _legs(rig) == (VOICE, "hi", "or")


async def test_start_over_clears_the_form_and_keeps_the_language() -> None:
    llm = ScriptedGemini({"Start again.": reply_and_call("Starting over.", "start_over")})
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session(init={"language": "Hindi"})
        await _walk(rig, upto=_UPTO_THE_CARDS)
        check_turn(rig, await rig.driver.user_says("Start again."))
        assert rig.brain.answers == {} and rig.brain.shortlist_ids == ()
        assert rig.actions()[-2:] == ["started_over", "ask_profile"]
        assert rig.brain.language == "Hindi"
        check_voice_pair(rig, voice=VOICE, language="hi")


# ─── The prompt ───────────────────────────────────────────────────────────────


def test_the_prompt_is_a_helper_not_a_form() -> None:
    """What the prompt must say, and what it must no longer say."""
    prompt = SYSTEM_INSTRUCTION
    for rule in (
        "The screen runs the form. You help.",
        "EVERY RESPONSE STARTS WITH WORDS",
        "Never ask for their mobile number, their PAN or their consent out loud",
        "type it in on the screen instead, for their privacy",
        "Never read out what is on the screen",
        "Never invent a fee, a rate, a limit or a rule",
        "likely eligible",
    ):
        assert rule in prompt, rule
    for gone in ("capture_value", "ask_profile", "check_eligibility", "SAY:", "say yes out loud"):
        assert gone not in prompt, gone
    # The shelf is in the cached prefix, in words.
    for card in CARDS:
        assert card.name in prompt and card.perk_spoken in prompt, card.id
    catalogue = prompt[prompt.index("THE CARDS") : prompt.index("LANGUAGE\n")]
    assert not _DISPLAY_ONLY.search(catalogue), "a display figure in the prompt"


# ─── The typed contract ───────────────────────────────────────────────────────

#: A figure in display form — a digit, a rupee sign, a percent sign, a
#: multiplication sign — which the voice reads as noise.
_DISPLAY_ONLY = re.compile("[\u20b9%\u00d7]|\\d")


def test_the_sweep_can_fail() -> None:
    for bad in ("₹500 a year", "5% online", "2x your income", "up to 400 a month"):
        assert _DISPLAY_ONLY.search(bad), bad
    assert not _DISPLAY_ONLY.search("four percent at any pump")


def test_every_gesture_the_totem_can_send_is_in_the_vocabulary() -> None:
    assert [event.__voqal_event__ for event in KIOSK_EVENTS] == [
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
    ]


def test_an_action_wire_name_is_the_snake_case_of_its_class() -> None:
    assert AskProfile.__voqal_action__ == "ask_profile"
    assert ConfirmValue.__voqal_action__ == "confirm_value"
    assert ShowEligibility.__voqal_action__ == "show_eligibility"
    assert ShowShortlist.__voqal_action__ == "show_shortlist"
    assert ShowQr.__voqal_action__ == "show_qr"
