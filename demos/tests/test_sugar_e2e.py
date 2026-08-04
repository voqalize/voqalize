"""The Diabetes Coach demo, end to end over the wire — no network, no LLM key.

The real ``SugarBrain`` — the shipping ``demos/sugar/backend/brain.py``, its real
prompt, its real fourteen tools — hosted on a real ``DirectAgent`` socket and
driven by the conformance ``VoiceDriver``, with only the *model* scripted. See
``tests/_harness.py`` for what every demo's e2e proves.

Sugar is the demo where the **language moves twice**: once from the patient's
LanguageToggle in the init payload, and again mid-call when they ask to switch.
Both are the exact manoeuvre that shipped broken — the choice reached the prompt
and not the wire, so the coach wrote Devanagari and an English reference voice
read it aloud. Nothing in a transcript shows that; these frames do.

Run: ``cd demos && uv run pytest tests/test_sugar_e2e.py``
"""

from __future__ import annotations

from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, reply, reply_and_call

from ._harness import check_greeting, check_turn, check_voice_pair, demo

discover()

VOICE = "omnivoice/gauri"

# The distinctive phrase in `_greeting_instruction()` — the hybrid greeting sends
# a whole paragraph of instruction as the user turn, so key on a fragment.
GREETING_PROMPT = "just tapped Join"

SCENARIO = {
    "patient": {"name": "Rajesh"},
    "talk_mode": "quiet",
    "joined_from_nudge": "Evening check-in",
}


def _llm() -> ScriptedGemini:
    return ScriptedGemini(
        {
            GREETING_PROMPT: reply("Evening, Rajesh — go on, I'm listening."),
            "I had two rotis and dal at eight.": [
                reply_and_call(
                    "Logging that.",
                    "log_meal",
                    meal_type="dinner",
                    time_label="8:00 PM",
                    items=[
                        {"name": "Roti", "quantity": "2", "calories": 240},
                        {"name": "Dal", "quantity": "1 bowl", "calories": 180},
                    ],
                ),
                reply("Logged — about four hundred and twenty calories."),
            ],
            "Can we talk in Hindi?": [
                reply_and_call("Sure.", "switch_language", args={"language": "Hindi"}),
                reply("ठीक है, अब हिंदी में बात करते हैं।"),
            ],
        }
    )


async def test_greeting_and_voice_reach_the_wire() -> None:
    """The coach opens with the instant hello plus the model's grounded remainder,
    and its default English voice lands on **both** legs before that audio."""
    async with demo("sugar", _llm()) as rig:
        greeting = await rig.driver.start_session(payload={"scenario": SCENARIO})
        check_greeting(rig, greeting)
        assert greeting is not None
        # Hybrid greeting: the fixed hello is spoken instantly, the model's line
        # streams in behind it — so both are in one interaction's text.
        assert greeting.text.startswith("Hi!")
        assert "Evening, Rajesh" in greeting.text
        check_voice_pair(rig, voice=VOICE, language="en")


async def test_the_patients_chosen_language_is_on_the_wire_before_the_hello() -> None:
    """A Hindi patient hears a Hindi hello **in a Hindi voice**.

    The ordering is the point: ``configure_language`` runs before the greeting, so
    the first audio of the call is already in the right reference clip. When it ran
    after — or only reached the prompt — the Devanagari hello came out in an en-IN
    voice, which is right on paper and foreign in the ear."""
    async with demo("sugar", _llm()) as rig:
        greeting = await rig.driver.start_session(
            payload={"language": "Hindi", "scenario": SCENARIO}
        )
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text.startswith("नमस्ते!")
        check_voice_pair(rig, voice=VOICE, language="hi")


async def test_logging_a_meal_drives_the_screen() -> None:
    """One tool round-trip, with the exact ``ui_command`` payload the /sugar Today
    screen renders — including the calorie total, which the brain sums rather than
    trusting the model to add up."""
    async with demo("sugar", _llm()) as rig:
        await rig.driver.start_session(payload={"scenario": SCENARIO})

        turn = await rig.driver.user_says("I had two rotis and dal at eight.")
        check_turn(rig, turn, inferences=2)

        assert rig.actions() == ["log_meal"], rig.actions()
        meal = rig.command("log_meal")
        assert meal["meal_type"] == "dinner"
        assert [i["name"] for i in meal["items"]] == ["Roti", "Dal"]
        assert meal["total_calories"] == 420


async def test_switching_language_mid_call_moves_both_halves() -> None:
    """The patient asks to switch, and the recognizer follows the voice.

    ``switch_language`` is one ``configure_language`` call precisely so it cannot
    half-apply. Moving only the TTS leg leaves the recognizer hearing Hindi as
    English — the caller is then mis-transcribed for the rest of the call, and the
    reply, generated from that wrong transcript, is merely *odd* rather than
    obviously broken. Assert the pair, on the frames."""
    async with demo("sugar", _llm()) as rig:
        await rig.driver.start_session(payload={"scenario": SCENARIO})
        check_voice_pair(rig, voice=VOICE, language="en")

        turn = await rig.driver.user_says("Can we talk in Hindi?")
        check_turn(rig, turn, inferences=2)

        # No ui_command: switching language is a wire change, not a screen change.
        assert rig.actions() == [], rig.actions()
        check_voice_pair(rig, voice=VOICE, language="hi")
