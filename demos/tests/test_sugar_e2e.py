"""The Diabetes Coach demo, end to end over the wire — no network, no LLM key.

The real ``SugarBrain`` — the shipping ``demos/sugar/backend/brain.py``, its real
prompt, its real fourteen tools — hosted on a real ``brain_server`` socket and
driven by the conformance ``VoqalizeDriver``, with only the *model* scripted. See
``tests/_harness.py`` for what every demo's e2e proves.

Sugar is the demo where the **language is settled twice, by two different
layers**. The patient's LanguageToggle is answered before the call exists, so the
page sends it as connect-time ``config`` and this brain is dialled into a session
already in it — ``session.init["language"]`` then only says which language to
*write* in. Mid-call, when the patient asks to switch, the brain owns it: that is
a real runtime event and ``switch_language`` moves both legs at once.

Both are the exact manoeuvre that shipped broken — the choice reached the prompt
and not the wire, so the coach wrote Devanagari and an English reference voice
read it aloud. Nothing in a transcript shows that; these frames do.

Run: ``cd demos && uv run pytest tests/test_sugar_e2e.py``
"""

from __future__ import annotations

from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, reply, reply_and_call

from ._harness import (
    check_configured_at_connect,
    check_greeting,
    check_turn,
    check_voice_pair,
    demo,
)

discover()

VOICE = "omnivoice/gauri"

SCENARIO = {
    "patient": {"name": "Rajesh"},
    "talk_mode": "quiet",
    "joined_from_nudge": "Evening check-in",
}


def _llm() -> ScriptedGemini:
    return ScriptedGemini(
        {
            "I had two rotis and dal at eight.": [
                reply_and_call(
                    "Logging that.",
                    "log_meal",
                    # One tool, one model, one parameter — the argument is the
                    # ``LogMeal`` the browser renders, nested under the name the
                    # method gives it. That name is part of the schema Gemini
                    # reads, so a script writes what the model would write.
                    meal={
                        "meal_type": "dinner",
                        "time_label": "8:00 PM",
                        "items": [
                            {"name": "Roti", "quantity": "2", "calories": 240},
                            {"name": "Dal", "quantity": "1 bowl", "calories": 180},
                        ],
                    },
                ),
                reply("Logged — about four hundred and twenty calories."),
            ],
            "Can we talk in Hindi?": [
                reply_and_call("Sure.", "switch_language", to={"language": "Hindi"}),
                reply("ठीक है, अब हिंदी में बात करते हैं।"),
            ],
        }
    )


async def test_the_greeting_is_written_without_touching_the_wire() -> None:
    """The coach opens with its written line, by name, and configures nothing.

    The session's voice and language arrived with the connect request, so the
    greeting — the one utterance nobody gets to re-run — is already synthesized in
    the right clip with no round trip to have ordered correctly ahead of it. A
    configure here would be a second authority for the same answer.

    The greeting runs no model either: ``ScriptedGemini`` records every call it is
    asked for, and the opening turn makes none."""
    llm = _llm()
    async with demo("sugar", llm) as rig:
        greeting = await rig.driver.start_session(init={"scenario": SCENARIO})
        check_greeting(rig, greeting)
        assert greeting is not None
        assert greeting.text == "Hi Rajesh! Your evening check-in — how did today go?"
        assert llm.calls == []
        check_configured_at_connect(rig)


async def test_the_patients_chosen_language_writes_the_hello() -> None:
    """A Hindi patient is greeted in Hindi, and the brain still configures nothing.

    ``init["language"]`` is the same answer as the ``config`` the page sent
    alongside it, read by the layer that writes rather than the one that speaks.
    This asserts the writing half — the speaking half is the connect request's,
    and the two are built from one toggle in ``data.ts`` so they cannot be chosen
    apart.

    Which is the whole ordering argument: the Devanagari hello came out in an
    en-IN voice when the choice reached the prompt and not the wire, and the
    greeting is the one utterance there is no second chance at."""
    async with demo("sugar", _llm()) as rig:
        greeting = await rig.driver.start_session(init={"language": "Hindi", "scenario": SCENARIO})
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text.startswith("नमस्ते Rajesh!")
        check_configured_at_connect(rig)


async def test_logging_a_meal_drives_the_screen() -> None:
    """One tool round-trip, with the exact ``ui_command`` payload the /sugar Today
    screen renders — including the calorie total, which the brain sums rather than
    trusting the model to add up."""
    async with demo("sugar", _llm()) as rig:
        await rig.driver.start_session(init={"scenario": SCENARIO})

        turn = await rig.driver.user_says("I had two rotis and dal at eight.")
        check_turn(rig, turn, units=2)

        assert rig.actions() == ["log_meal"], rig.actions()
        meal = rig.command("log_meal")
        assert meal["meal_type"] == "dinner"
        assert [i["name"] for i in meal["items"]] == ["Roti", "Dal"]
        assert meal["total_calories"] == 420


async def test_switching_language_mid_call_moves_both_halves() -> None:
    """The patient asks to switch, and the recognizer follows the voice.

    This is the one part of sugar's language that is a runtime event, so it is the
    one part the brain owns: the page settled the opening language, and a change of
    mind mid-call is something only the conversation knows about.

    ``switch_language`` is one ``session.configure`` call precisely so it cannot
    half-apply. Moving only the TTS leg leaves the recognizer hearing Hindi as
    English — the caller is then mis-transcribed for the rest of the call, and the
    reply, generated from that wrong transcript, is merely *odd* rather than
    obviously broken. Assert the pair, on the frames."""
    async with demo("sugar", _llm()) as rig:
        await rig.driver.start_session(init={"scenario": SCENARIO})
        # Nothing yet: the session opened in the language the page asked for.
        check_configured_at_connect(rig)

        turn = await rig.driver.user_says("Can we talk in Hindi?")
        check_turn(rig, turn, units=2)

        # No ui_command: switching language is a wire change, not a screen change.
        assert rig.actions() == [], rig.actions()
        check_voice_pair(rig, voice=VOICE, language="hi")
