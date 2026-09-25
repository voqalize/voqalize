"""The kiosk's language switching, and the spoken answers that move it on.

Two halves, because two different things can go wrong.

* **The mechanics — always run, no model.** A scripted model makes the calls,
  and these assert what the brain does with them: both legs move together in
  every direction and back again, a spoken answer puts the next question up by
  itself instead of leaving Tanvi to wait, and a settled answer never paints a
  confirm screen. These are the parts a live Kannada session got wrong: the
  customer answered, Tanvi acknowledged, and nothing moved until they spoke again.

* **The judgement — opt-in, real model.** Whether Tanvi *notices* a language
  change is a property of the prompt and the model, and only a model can test
  it. Each scenario hands the real brain a turn exactly as the recognizer writes
  it — English spoken to the Kannada recognizer arrives as English words spelled
  in Kannada script — and asserts on what she does. Skipped without
  ``GEMINI_API_KEY``; run it after any change to ``prompts.py``::

      GEMINI_API_KEY=... uv run pytest tests/test_kiosk_language.py -q
"""

from __future__ import annotations

import os
import re
from typing import Any

import pytest
from voqalize_demos.testing import ScriptedGemini, call, reply

from ._harness import DemoRig, _configs, _last, demo
from .test_kiosk_e2e import (
    _BY_HAND,
    VOICE,
    _by_hand,
    _legs,
    _one_more_turn,
    _spoken,
    _tool_results,
)

_CODE = {"English": "en", "Kannada": "kn", "Hindi": "hi", "Tamil": "ta"}


def _asked(rig: DemoRig) -> list[str]:
    """The questions put on the glass, in order, by field."""
    return [
        str((c.get("payload") or {}).get("field"))
        for c in rig.driver.ui_commands
        if c.get("command") == "ask_profile"
    ]


def _states(rig: DemoRig) -> list[str]:
    """Every read-back state the glass was sent, in order."""
    return [
        str((c.get("payload") or {}).get("state"))
        for c in rig.driver.ui_commands
        if c.get("command") == "confirm_value"
    ]


# ─── The mechanics ────────────────────────────────────────────────────────────


async def test_every_direction_moves_both_legs_and_comes_back() -> None:
    """English → Kannada → English → Hindi → Tamil → English, each by a spoken
    request. Every hop moves the voice's language and the recognizer's together,
    and the screen follows: Hindi copy for Hindi, English copy for the rest."""
    hops = ["Kannada", "English", "Hindi", "Tamil", "English"]
    # One distinct line per hop: the script answers by what was said, and two hops
    # to English would otherwise share one cursor.
    said = [f"Hop {at}: let's speak {name}." for at, name in enumerate(hops)]
    llm = ScriptedGemini(
        {
            line: [call("switch_language", to={"language": name}), reply("Okay.")]
            for line, name in zip(said, hops, strict=True)
        }
    )
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        assert _legs(rig) == (VOICE, "en", "en")
        for line, name in zip(said, hops, strict=True):
            await rig.driver.user_says(line)
            code = _CODE[name]
            assert _legs(rig) == (VOICE, code, code), (name, _legs(rig))
            assert rig.brain.language == name
            changed = rig.driver.ui_commands[-1]
            assert changed["command"] == "language_changed", changed
            assert changed["payload"] == {
                "language": name,
                "screen_language": "hi" if name == "Hindi" else "en",
            }


async def test_patience_is_three_and_a_switch_keeps_it() -> None:
    """The kiosk listens with patience 3 from the first word, and every language
    switch re-sends the recognizer's settings — so a switch must carry it too,
    or the kiosk quietly falls back to the deployment's 7 in Kannada."""
    llm = ScriptedGemini()
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        assert _last(_configs(rig), lambda c: c.stt.patience if c.stt else None) == 3
        await _by_hand(rig, "language_picked", {"language": "Kannada"})
        assert _last(_configs(rig), lambda c: c.stt.patience if c.stt else None) == 3


def _patience(rig: DemoRig) -> int | None:
    return _last(_configs(rig), lambda c: c.stt.patience if c.stt else None)


async def test_dictation_waits_longer_and_the_questions_do_not() -> None:
    """Quick for the four questions, patient while a mobile or PAN is read out in
    groups — a partial one is rejected outright, so cutting it at a pause makes
    the customer start again. Start over brings the quick pace back."""
    async with demo("kiosk", ScriptedGemini()) as rig:
        await rig.driver.start_session()
        assert _patience(rig) == 3
        for step in _BY_HAND:
            await _by_hand(rig, step.event, step.payload)
            if step.event == "consent_given":
                break
        assert rig.brain.view["screen"] == "value"
        assert _patience(rig) == 8, "the mobile number is asked for at the quick pace"
        await _by_hand(rig, "restart_pressed")
        assert _patience(rig) == 3


async def test_an_answer_before_any_question_moves_on_and_is_not_asked_again() -> None:
    """The greeting asks for a name and the customer answers more: "I'm Ravi, I'm
    salaried". The answer lands on the welcome screen, and the next question comes
    up at once — so the first quiet moment does not put employment up again."""
    llm = ScriptedGemini(
        {
            "I'm Ravi, I'm salaried.": [
                call("capture_value", heard={"field": "employment", "value": "salaried"}),
                reply("Nice to meet you, Ravi. Roughly what comes in every month?"),
            ]
        }
    )
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("I'm Ravi, I'm salaried.")
        await rig.driver.user_idle(timeout=0.5)
        await _one_more_turn(rig)

        assert _asked(rig) == ["income_band"], _asked(rig)
        captured = next(r for r in _tool_results(llm) if r.startswith("Recorded"))
        assert "income band question is already up" in captured, captured


async def test_a_confirmed_mobile_stays_on_the_glass_as_confirmed() -> None:
    """A read-back that settles keeps its panel, marked confirmed, so Tanvi reading
    the screen sees what the customer sees — not a confirm screen with nothing on
    it."""
    llm = ScriptedGemini(
        {
            "It's 98765 43210.": [
                call("capture_value", heard={"field": "mobile", "value": "9876543210"})
            ],
            "Yes, that's right.": [
                call("confirm", check={"field": "mobile", "value": "9876543210", "heard": "yes"})
            ],
        }
    )
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("It's 98765 43210.")
        assert rig.brain.view["the value being confirmed"]["state"] == "confirming"
        await rig.driver.user_says("Yes, that's right.")
        assert rig.brain.view["screen"] == "confirm"
        assert rig.brain.view["the value being confirmed"]["state"] == "confirmed"


async def test_the_picker_and_the_voice_can_hand_the_language_back_and_forth() -> None:
    """The customer picks Kannada on the screen, then asks for English out loud,
    then picks Kannada again. Neither path is special: the last one wins, and the
    legs always match it."""
    llm = ScriptedGemini(
        {"I want to speak in English.": [call("switch_language", to={"language": "English"})]}
    )
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        await _by_hand(rig, "language_picked", {"language": "Kannada"})
        assert _legs(rig) == (VOICE, "kn", "kn")
        await rig.driver.user_says("I want to speak in English.")
        assert _legs(rig) == (VOICE, "en", "en")
        await _by_hand(rig, "language_picked", {"language": "Kannada"})
        assert _legs(rig) == (VOICE, "kn", "kn")
        assert rig.brain.language == "Kannada"


async def test_a_spoken_answer_in_kannada_puts_the_next_question_up_itself() -> None:
    """The bug from the Kannada session: an answer was recorded, the screen asked
    for a confirmation nobody needed, and Tanvi waited. Now the answer settles, the
    next question is on the glass in the same breath, and the tool tells her to
    ask it in this turn — so the turn cannot end in silence."""
    llm = ScriptedGemini(
        {
            "ನಮಸ್ಕಾರ": [
                call("ask_profile", ask={"field": "employment", "question": "ನೀವು ಏನು ಮಾಡುತ್ತೀರಿ?"}),
                reply("ನೀವು ಸಂಬಳದ ಕೆಲಸದಲ್ಲಿದ್ದೀರಾ?"),
            ],
            "ನಾನು ಸಂಬಳದ ಕೆಲಸ ಮಾಡ್ತೀನಿ": [
                call("capture_value", heard={"field": "employment", "value": "salaried"}),
                reply("ಸರಿ. ತಿಂಗಳಿಗೆ ಎಷ್ಟು ಬರುತ್ತದೆ?"),
            ],
        }
    )
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        await _by_hand(rig, "language_picked", {"language": "Kannada"})
        await rig.driver.user_says("ನಮಸ್ಕಾರ")
        await rig.driver.user_says("ನಾನು ಸಂಬಳದ ಕೆಲಸ ಮಾಡ್ತೀನಿ")
        await _one_more_turn(rig)

        assert _asked(rig) == ["employment", "income_band"], _asked(rig)
        assert "confirming" not in _states(rig), "a chip answer was read back for a yes"
        assert rig.brain.view["screen"] == "question"
        assert rig.brain.view["the value being confirmed"] is None
        assert rig.brain.answers["employment"] == "salaried"

        captured = next(r for r in _tool_results(llm) if r.startswith("Recorded"))
        assert "income band question is already up" in captured, captured
        assert "same turn" in captured and "ask it once" in captured, captured


async def test_the_fourth_answer_goes_straight_to_the_eligibility_check() -> None:
    """After the last of the four there is no next question to put up, so the
    tool hands Tanvi the next step by name instead of leaving the turn open."""
    llm = ScriptedGemini(
        {
            "Start.": [call("ask_profile", ask={"field": "employment", "question": "?"})],
            "Salaried.": [
                call("capture_value", heard={"field": "employment", "value": "salaried"})
            ],
            "Forty thousand.": [
                call("capture_value", heard={"field": "income_band", "value": "25k_60k"})
            ],
            "One card.": [call("capture_value", heard={"field": "existing_cards", "value": "one"})],
            "Fuel.": [call("capture_value", heard={"field": "spend_category", "value": "fuel"})],
        }
    )
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        for line in ("Start.", "Salaried.", "Forty thousand.", "One card.", "Fuel."):
            await rig.driver.user_says(line)
        await _one_more_turn(rig)

        assert _asked(rig) == ["employment", "income_band", "existing_cards", "spend_category"]
        last = [r for r in _tool_results(llm) if r.startswith("Recorded")][-1]
        assert "check_eligibility" in last and "same turn" in last, last


async def test_correcting_an_earlier_answer_does_not_jump_the_screen() -> None:
    """A customer on the income question who says "actually I'm self-employed"
    is correcting, not answering. The answer changes; the screen stays where
    they are."""
    llm = ScriptedGemini(
        {
            "Start.": [call("ask_profile", ask={"field": "employment", "question": "?"})],
            "Salaried.": [
                call("capture_value", heard={"field": "employment", "value": "salaried"})
            ],
            "Actually, I'm self-employed.": [
                call("capture_value", heard={"field": "employment", "value": "self_employed"})
            ],
        }
    )
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        for line in ("Start.", "Salaried.", "Actually, I'm self-employed."):
            await rig.driver.user_says(line)
        await _one_more_turn(rig)

        assert _asked(rig) == ["employment", "income_band"], _asked(rig)
        assert rig.brain.answers["employment"] == "self_employed"
        assert rig.brain.view["the question on screen"] == "income band"
        last = [r for r in _tool_results(llm) if r.startswith("Recorded")][-1]
        assert "carry on where they were" in last, last


#: English as each recognizer spells it, and the sentences that must NOT count.
_ENGLISH_SPELLED = [
    "ಐ ವಾಂಟ್ ಟು ಸ್ಪೀಕ್ ಇನ್ ಇಂಗ್ಲಿಷ್",  # I want to speak in English
    "ಕ್ಯಾನ್ ವಿ ಸ್ವಿಚ್ ಟು ಇಂಗ್ಲಿಷ್ ಪ್ಲೀಸ್",  # Can we switch to English please
    "ಐ ಆಮ್ ಎ ಸ್ಯಾಲರೀಡ್ ಎಂಪ್ಲಾಯಿ ವರ್ಕಿಂಗ್ ಇನ್ ಎ ಪ್ರೈವೇಟ್ ಕಂಪನಿ",  # English, with loan nouns
    "आई वांट टू टॉक इन इंग्लिश",  # I want to talk in English
    "वाट इज़ द फी?",  # What is the fee?
    "வாட் இஸ் தி ஃபீ",  # What is the fee? (Tamil script)
]
_NOT_ENGLISH = [
    "ನಾನು ಸ್ಯಾಲರೀಡ್ ಎಂಪ್ಲಾಯಿ",  # Kannada, with English nouns
    "ನಾನು ಸಂಬಳದ ಕೆಲಸ ಮಾಡ್ತೀನಿ",  # Kannada
    "मैं salaried हूँ, प्राइवेट कंपनी में काम करता हूँ",  # Hindi, one English word
    "हाँ ठीक है, ओके",  # Hindi with "okay"
    "ಯೆಸ್",  # "yes", borrowed everywhere
    "ನನ್ನ ಮೈ ನೋವು ಇದೆ",  # Kannada ಮೈ is "body", not "my"
    "ஆம், சம்பளம் வாங்குகிறேன்",  # Tamil ஆம் is "yes", not "am"
]


@pytest.mark.parametrize("text", _ENGLISH_SPELLED)
def test_english_spelled_in_an_indian_script_reads_as_english(text: str) -> None:
    from voqalize_demos._loaded.kiosk.script_english import reads_as_english

    assert reads_as_english(text), text


@pytest.mark.parametrize("text", _NOT_ENGLISH)
def test_an_indian_language_with_loan_words_does_not(text: str) -> None:
    from voqalize_demos._loaded.kiosk.script_english import reads_as_english

    assert not reads_as_english(text), text


async def test_english_in_kannada_script_moves_both_legs_before_the_model_speaks() -> None:
    """The live failure, reproduced with a model that does exactly what the real
    one did a third of the time: answers in English and never calls
    switch_language. The brain has already moved both legs, so the English reply
    is spoken by the English voice and the next sentence is heard in English."""
    heard = "ಐ ವಾಂಟ್ ಟು ಸ್ಪೀಕ್ ಇನ್ ಇಂಗ್ಲಿಷ್"
    llm = ScriptedGemini({heard: reply("Sure. Are you salaried or self-employed?")})
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        await _by_hand(rig, "language_picked", {"language": "Kannada"})
        assert _legs(rig) == (VOICE, "kn", "kn")
        await rig.driver.user_says(heard)
        assert rig.brain.language == "English"
        assert _legs(rig) == (VOICE, "en", "en")
        assert rig.driver.ui_commands[-1]["payload"]["language"] == "English"
        # The model is told, in the same request as the words, why it is in English.
        told = [
            part.text or "" for content in llm.calls[-1].contents for part in content.parts or []
        ]
        assert any("heard English" in line for line in told), told


async def test_kannada_with_loan_words_stays_in_kannada() -> None:
    """The guard's other half: Kannada full of English nouns is still Kannada."""
    llm = ScriptedGemini({"ನಾನು ಸ್ಯಾಲರೀಡ್ ಎಂಪ್ಲಾಯಿ": reply("ಸರಿ.")})
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        await _by_hand(rig, "language_picked", {"language": "Kannada"})
        await rig.driver.user_says("ನಾನು ಸ್ಯಾಲರೀಡ್ ಎಂಪ್ಲಾಯಿ")
        assert rig.brain.language == "Kannada"
        assert _legs(rig) == (VOICE, "kn", "kn")


def test_the_prompt_teaches_both_directions_and_the_unsure_middle() -> None:
    """The judgement lives in the prompt, so its three rules are pinned here: how
    garbled English means an Indian language, how English arrives spelled in an
    Indian script, and what to do when it is not clear — ask, in both languages,
    rather than switch or stay silent."""
    # Imported here: the kiosk package is only importable once discovery has
    # loaded it, which importing test_kiosk_e2e above does.
    from voqalize_demos._loaded.kiosk.prompts import SYSTEM_INSTRUCTION

    prompt = SYSTEM_INSTRUCTION
    assert "HOW TO TELL THEY ARE NOT SPEAKING ENGLISH" in prompt
    assert "HOW TO TELL THEY HAVE GONE BACK TO ENGLISH" in prompt
    # English in Kannada, Devanagari and Tamil script, each with its meaning.
    for sample in ("ಐ ವಾಂಟ್ ಟು ಸ್ಪೀಕ್ ಇನ್ ಇಂಗ್ಲಿಷ್", "आई वांट टू टॉक इन इंग्लिश", "வாட் இஸ் தி ஃபீ"):
        assert sample in prompt, sample
    assert "SURE, OR NOT SURE" in prompt
    assert "Shall we continue in English?" in prompt
    assert "Never go quiet after an answer" in prompt


# ─── The judgement: the real model ────────────────────────────────────────────

_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
live = pytest.mark.skipif(not _KEY, reason="no GEMINI_API_KEY — the live language eval is opt-in")

#: How long one real turn may take, tools included.
_TURN = 45.0

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_KANNADA = re.compile(r"[ಀ-೿]")


def _client() -> Any:
    from google import genai

    return genai.Client(api_key=_KEY)


async def _live(rig: DemoRig, *, start_in: str | None = None) -> None:
    """Open the session, move it into ``start_in`` by the picker if asked, and put
    the first question up by staying quiet — so every scenario starts where a real
    one does: greeted, and asked what they do."""
    await rig.driver.start_session()
    if start_in:
        await _by_hand(rig, "language_picked", {"language": start_in})
    await rig.driver.user_idle(timeout=5.0)


#: English spoken while the kiosk is in Kannada, as the Kannada recognizer writes
#: it — English words in Kannada script. Each one must bring English back.
_ENGLISH_IN_KANNADA_SCRIPT = [
    "ಐ ವಾಂಟ್ ಟು ಸ್ಪೀಕ್ ಇನ್ ಇಂಗ್ಲಿಷ್",  # I want to speak in English
    "ಕ್ಯಾನ್ ವಿ ಸ್ವಿಚ್ ಟು ಇಂಗ್ಲಿಷ್ ಪ್ಲೀಸ್",  # Can we switch to English please
    "ಐ ಆಮ್ ಎ ಸ್ಯಾಲರೀಡ್ ಎಂಪ್ಲಾಯಿ ವರ್ಕಿಂಗ್ ಇನ್ ಎ ಪ್ರೈವೇಟ್ ಕಂಪನಿ",  # I am a salaried employee…
]


@live
@pytest.mark.parametrize("heard", _ENGLISH_IN_KANNADA_SCRIPT)
async def test_live_english_in_kannada_script_switches_back_to_english(heard: str) -> None:
    """The reported bug: Kannada worked, English did not come back."""
    async with demo("kiosk", _client()) as rig:
        await _live(rig, start_in="Kannada")
        assert rig.brain.language == "Kannada"
        before = len(_spoken(rig))
        await rig.driver.user_says(heard, timeout=_TURN)
        said = " ".join(_spoken(rig)[before:])
        assert rig.brain.language == "English", (
            f"stayed in {rig.brain.language} on {heard!r}; said {said!r}; "
            f"answers {rig.brain.answers}"
        )
        assert _legs(rig) == (VOICE, "en", "en")


#: The same English, written in Devanagari by the Hindi recognizer.
@live
async def test_live_english_in_devanagari_switches_back_from_hindi() -> None:
    async with demo("kiosk", _client()) as rig:
        await _live(rig, start_in="Hindi")
        before = len(_spoken(rig))
        await rig.driver.user_says("आई वांट टू टॉक इन इंग्लिश", timeout=_TURN)
        said = " ".join(_spoken(rig)[before:])
        assert rig.brain.language == "English", f"stayed in {rig.brain.language}; said {said!r}"


#: Kannada spoken while the kiosk is in English, as the English recognizer
#: mangles it. Must move to Kannada on the one turn.
@live
async def test_live_mangled_kannada_moves_english_to_kannada() -> None:
    async with demo("kiosk", _client()) as rig:
        await _live(rig)
        await rig.driver.user_says(
            "Naanu salary kelsa maadtini, private company alli.", timeout=_TURN
        )
        assert rig.brain.language == "Kannada", rig.brain.language
        assert _legs(rig) == (VOICE, "kn", "kn")


@live
async def test_live_a_kannada_answer_is_captured_and_the_next_question_asked() -> None:
    """The second report: in Kannada the right option was chosen and then nothing
    happened. The answer must be recorded, the next question must be on the glass,
    and Tanvi must have said something in Kannada — not gone quiet."""
    async with demo("kiosk", _client()) as rig:
        await _live(rig, start_in="Kannada")
        before = len(_spoken(rig))
        await rig.driver.user_says("ನಾನು ಸಂಬಳದ ಕೆಲಸ ಮಾಡ್ತೀನಿ", timeout=_TURN)  # I work a salaried job

        assert rig.brain.answers.get("employment") == "salaried", rig.brain.answers
        assert _asked(rig)[-1] == "income_band", _asked(rig)
        said = " ".join(_spoken(rig)[before:])
        assert said.strip(), "Tanvi went quiet after the answer"
        assert _KANNADA.search(said), f"answered outside Kannada: {said!r}"
        assert rig.brain.language == "Kannada"


@live
async def test_live_a_borrowed_word_is_not_a_switch() -> None:
    """One English word inside a Hindi sentence is Hindi. The kiosk stays put."""
    async with demo("kiosk", _client()) as rig:
        await _live(rig, start_in="Hindi")
        await rig.driver.user_says("मैं salaried हूँ, प्राइवेट कंपनी में काम करता हूँ", timeout=_TURN)
        assert rig.brain.language == "Hindi", rig.brain.language
        assert rig.brain.answers.get("employment") == "salaried", rig.brain.answers


@live
async def test_live_an_unclear_turn_asks_in_both_languages_instead_of_guessing() -> None:
    """Half Hindi, half English, too short to be sure: Tanvi neither switches nor
    goes quiet, and asks — in both languages — whether to change."""
    async with demo("kiosk", _client()) as rig:
        await _live(rig)
        before = len(_spoken(rig))
        await rig.driver.user_says("Haan theek hai, okay.", timeout=_TURN)
        said = " ".join(_spoken(rig)[before:])
        assert said.strip(), "Tanvi went quiet"
        if rig.brain.language == "English":
            assert _DEVANAGARI.search(said) and re.search(r"[A-Za-z]{3}", said), (
                f"stayed in English without offering Hindi: {said!r}"
            )
        else:
            # Switching on this is allowed — it is Hindi — but only to Hindi.
            assert rig.brain.language == "Hindi", rig.brain.language
