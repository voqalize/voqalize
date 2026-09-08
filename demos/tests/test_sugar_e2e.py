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

from typing import Any

from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, call, reply, reply_and_call

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
    """The coach opens with its written line and configures nothing.

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
        assert greeting.text == "Hi there! Your evening check-in — how did today go?"
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
        assert greeting is not None and greeting.text.startswith("नमस्ते!")
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


#: A snapshot of the shape ``store.tsx``'s ``snapshot()`` sends.
_TAPPED: dict[str, Any] = {
    "phase": "call",
    "meals": [{"meal": "dinner", "time": "8:00 PM", "total_kcal": 420}],
    "medications": [{"name": "Metformin", "status": "pending"}],
    "sensor_order": "ordered",
    "summary_shown": False,
}


def _context_text(llm: ScriptedGemini) -> str:
    return " ".join(
        part.text or ""
        for contents in llm.captured_contents
        for content in contents
        if content.role == "user"
        for part in (content.parts or [])
    )


def _tool_results(llm: ScriptedGemini) -> str:
    """Under automatic function calling a whole turn is one request, so what it
    called is first carried by the request that follows it."""
    return " ".join(
        str((part.function_response.response or {}).get("result", ""))
        for contents in llm.captured_contents
        for content in contents
        for part in (content.parts or [])
        if part.function_response is not None
    )


async def test_what_the_patient_tapped_is_named_and_the_screen_is_never_dumped() -> None:
    """``state_sync`` is the one client message that must not speak — and, since the
    screen moved out of the context, the one that must not describe either.

    This brain used to append the whole screen on every change, prefixed
    *authoritative*, so a call that logs a dozen things ended with a dozen
    near-identical screens in front of the model. Now the snapshot stops at the
    brain: the context gets one line naming which facts the patient moved and
    pointing at ``read_screen``. Both halves are asserted — a note carrying the
    sensor state would be the old dump again, one fact at a time."""
    llm = ScriptedGemini({"What have I got logged?": reply("It is all on your screen.")})
    async with demo("sugar", llm) as rig:
        await rig.driver.start_session(init={"scenario": SCENARIO})
        before = len(rig.driver.ui_commands)

        # The first sync is the app as it loaded; the second is the patient's tap.
        await rig.driver.send_client_message("state_sync", {"screen": {"phase": "call"}})
        await rig.driver.send_client_message("state_sync", {"screen": _TAPPED})
        turn = await rig.driver.user_says("What have I got logged?")
        check_turn(rig, turn, units=1)
        assert len(rig.driver.ui_commands) == before, "state_sync drove the screen"

    context = _context_text(llm)
    assert "just changed the screen" in context
    assert "read_screen" in context
    assert "ordered" not in context, "the change note is carrying the screen"
    assert "CURRENT SCREEN STATE" not in context, "the screen dump is back"


async def test_a_tool_aimed_at_a_screen_the_patient_moved_is_refused_until_it_is_read() -> None:
    """The version gate, which is what makes read-don't-remember enforceable.

    ``confirm_sensor_order`` is the tool this matters most for: its own description
    tells the coach not to place an order the patient already placed by hand, and
    that instruction is worth nothing if the coach is reasoning from a screen taken
    before the tap. So the tool refuses instead of ordering twice, and the refusal
    is retriable: read, then act."""
    llm = ScriptedGemini(
        {
            "Yes, order it.": [
                call("confirm_sensor_order"),  # stale — he tapped it himself
                call("read_screen"),
                reply("You have already ordered it — nothing more to do."),
            ],
            "Thanks.": reply("Any time."),
        }
    )
    async with demo("sugar", llm) as rig:
        await rig.driver.start_session(init={"scenario": SCENARIO})
        await rig.driver.send_client_message("state_sync", {"screen": {"phase": "call"}})
        await rig.driver.send_client_message("state_sync", {"screen": _TAPPED})

        await rig.driver.user_says("Yes, order it.")
        assert rig.actions() == [], "the order went through on a screen never read"

        # One more turn, so the turn above's hops are in the context being asserted.
        await rig.driver.user_says("Thanks.")

    results = _tool_results(llm)
    assert "the screen moved since you last read it" in results
    assert "sensor order: ordered" in results, "read_screen did not serve the tap"
