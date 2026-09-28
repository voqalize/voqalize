"""The kiosk's language switching.

Two halves, because two different things can go wrong.

* **The mechanics — always run, no model.** A scripted model makes the calls,
  and these assert what the brain does with them: both legs move together in
  every direction and back again, the recognizer keeps its patience through a
  switch, English spelled in an Indian script is caught in Python before the
  model runs — and the screen never moves, because it is English.

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
from voqalize_demos.testing import ScriptedGemini, reply, reply_and_call

from ._harness import DemoRig, _configs, _last, demo
from .test_kiosk_e2e import VOICE, _legs, _spoken

_CODE = {"English": "en", "Kannada": "kn", "Hindi": "hi", "Tamil": "ta"}


def _asked(rig: DemoRig) -> list[str]:
    """The questions put on the glass, in order, by field."""
    return [
        str((c.get("payload") or {}).get("field"))
        for c in rig.driver.ui_commands
        if c.get("command") == "ask_profile"
    ]


def _patience(rig: DemoRig) -> int | None:
    return _last(_configs(rig), lambda c: c.stt.patience if c.stt else None)


async def _into(rig: DemoRig, language: str) -> None:
    """Put the call in ``language`` the way the English check does — both legs,
    awaited, and the note that tells the model — so a scenario can start there
    without a scripted turn."""
    brain = rig.brain
    brain._append_note(await brain._switch_to(language, by="the customer"))  # pyright: ignore[reportPrivateUsage]


# ─── The mechanics ────────────────────────────────────────────────────────────


async def test_every_direction_moves_both_legs_and_comes_back() -> None:
    """English → Kannada → English → Hindi → Tamil → English, each by a spoken
    request. Every hop moves the voice's language and the recognizer's together,
    and the glass does not move at all: it is English, whatever is spoken."""
    hops = ["Kannada", "English", "Hindi", "Tamil", "English"]
    # One distinct line per hop: the script answers by what was said, and two hops
    # to English would otherwise share one cursor.
    said = [f"Hop {at}: let's speak {name}." for at, name in enumerate(hops)]
    llm = ScriptedGemini(
        {
            line: reply_and_call("Okay.", "switch_language", to={"language": name})
            for line, name in zip(said, hops, strict=True)
        }
    )
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        assert _legs(rig) == (VOICE, "en", "en")
        on_the_glass = list(rig.driver.ui_commands)
        for line, name in zip(said, hops, strict=True):
            await rig.driver.user_says(line)
            code = _CODE[name]
            assert _legs(rig) == (VOICE, code, code), (name, _legs(rig))
            assert rig.brain.language == name
        assert rig.driver.ui_commands == on_the_glass, "a language switch moved the screen"


async def test_patience_is_three_and_a_switch_keeps_it() -> None:
    """The kiosk listens with patience 3 from the first word — nothing is
    dictated any more, a mobile number and a PAN are typed — and every language
    switch re-sends the recognizer's settings, so a switch must carry it too."""
    llm = ScriptedGemini(
        {"Kannada please.": reply_and_call("ಸರಿ.", "switch_language", to={"language": "Kannada"})}
    )
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        assert _patience(rig) == 3
        await rig.driver.user_says("Kannada please.")
        assert _legs(rig) == (VOICE, "kn", "kn")
        assert _patience(rig) == 3


async def test_a_kannada_answer_is_tapped_and_the_next_question_comes_up() -> None:
    """The live Kannada report, with the new shape: the customer answers in
    Kannada, Tanvi taps the answer and says a word in Kannada, and the next
    question is on the glass — in English — without anyone waiting on anyone."""
    llm = ScriptedGemini(
        {
            "ನಾನು ಸಂಬಳದ ಕೆಲಸ ಮಾಡ್ತೀನಿ": reply_and_call(
                "ಸರಿ.", "answer_on_screen", answer={"employment": "salaried"}
            ),
        }
    )
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        await _into(rig, "Kannada")
        turn = await rig.driver.user_says("ನಾನು ಸಂಬಳದ ಕೆಲಸ ಮಾಡ್ತೀನಿ")
        assert [u.text for u in turn.units] == ["ಸರಿ."]
        assert rig.brain.answers == {"employment": "salaried"}
        assert _asked(rig) == ["employment", "income_band"]
        assert rig.brain.language == "Kannada"


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
    llm = ScriptedGemini({heard: reply("Sure, English it is.")})
    async with demo("kiosk", llm) as rig:
        await rig.driver.start_session()
        await _into(rig, "Kannada")
        assert _legs(rig) == (VOICE, "kn", "kn")
        await rig.driver.user_says(heard)
        assert rig.brain.language == "English"
        assert _legs(rig) == (VOICE, "en", "en")
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
        await _into(rig, "Kannada")
        await rig.driver.user_says("ನಾನು ಸ್ಯಾಲರೀಡ್ ಎಂಪ್ಲಾಯಿ")
        assert rig.brain.language == "Kannada"
        assert _legs(rig) == (VOICE, "kn", "kn")


def test_the_prompt_teaches_both_directions_and_the_unsure_middle() -> None:
    """The judgement lives in the prompt, so its three rules are pinned here: how
    garbled English means an Indian language, how English arrives spelled in an
    Indian script, and what to do when it is not clear — ask, in both languages,
    rather than switch or stay silent. And the screen stays English."""
    from voqalize_demos._loaded.kiosk.prompts import SYSTEM_INSTRUCTION

    prompt = SYSTEM_INSTRUCTION
    assert "HOW TO TELL THEY ARE NOT SPEAKING ENGLISH" in prompt
    assert "HOW TO TELL THEY HAVE GONE BACK TO ENGLISH" in prompt
    for sample in ("ಐ ವಾಂಟ್ ಟು ಸ್ಪೀಕ್ ಇನ್ ಇಂಗ್ಲಿಷ್", "आई वांट टू टॉक इन इंग्लिश", "வாட் இஸ் தி ஃபீ"):
        assert sample in prompt, sample
    assert "SURE, OR NOT SURE" in prompt
    assert "Shall we continue in English?" in prompt
    assert "The screen is in English, whatever language you are speaking." in prompt


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
    """Open the session — greeted, with the first question on the glass — and
    move it into ``start_in`` if asked, so every scenario starts where a real one
    does."""
    await rig.driver.start_session()
    if start_in:
        await _into(rig, start_in)


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
async def test_live_a_kannada_answer_is_tapped_and_the_next_question_comes_up() -> None:
    """The second report: in Kannada the right option was chosen and then nothing
    happened. The answer must be tapped, the next question must be on the glass,
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


@live
async def test_live_a_question_is_answered_from_the_shelf_and_moves_nothing() -> None:
    """A question is not an answer: Tanvi answers it in a line, from the cards in
    her prompt, and the screen stays where it is."""
    async with demo("kiosk", _client()) as rig:
        await _live(rig)
        on_the_glass = list(rig.driver.ui_commands)
        before = len(_spoken(rig))
        await rig.driver.user_says("What is a secured card?", timeout=_TURN)
        said = " ".join(_spoken(rig)[before:])
        assert said.strip(), "Tanvi did not answer"
        assert "deposit" in said.lower(), said
        assert rig.driver.ui_commands == on_the_glass, "a question moved the screen"


@live
async def test_live_a_pan_read_aloud_is_turned_to_the_keypad() -> None:
    """The privacy rule: a customer who starts reading a PAN out is asked to type
    it in, and none of it is repeated back."""
    async with demo("kiosk", _client()) as rig:
        await _live(rig)
        before = len(_spoken(rig))
        await rig.driver.user_says("My PAN is A B C D E one two three four F.", timeout=_TURN)
        said = " ".join(_spoken(rig)[before:])
        assert re.search(r"\btyp", said.lower()), f"not sent to the keypad: {said!r}"
        assert "ABCDE" not in said.replace(" ", "").upper(), said
        assert "pan" not in rig.brain.answers
