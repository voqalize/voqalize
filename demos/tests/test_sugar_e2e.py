"""The Diabetes Coach demo, end to end over the wire — no network, no LLM key.

The real ``SugarBrain`` — the shipping ``demos/sugar/backend/brain.py``, its real
prompt, its real tools — hosted on a real ``brain_server`` socket and
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

**Only ``read_screen`` carries the mark.** It returns what the coach needs to
answer, so a turn that calls it is asked again at once; every other tool moves
the phone or the call, so the line and the call share one response and the turn
ends with it. The scripts are written in that shape, and the tests count requests
where the shape is the point.

Run: ``cd demos && uv run pytest tests/test_sugar_e2e.py``
"""

from __future__ import annotations

from google.genai import types
from voqalize_demos import PHRASES
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, call, reply, reply_and_call

from voqalize.sdk.wire import Language

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
            # The line and the log in one response: `log_meal` is not marked, so
            # nothing follows it this turn.
            "I had two rotis and dal at eight.": [
                reply_and_call(
                    "Got it — dinner's on your screen.",
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
            ],
            "That's all I ate.": reply("Nice, honest day."),
            # The switch line is said in the language the call is in *now*: it is
            # spoken before the new voice is configured. Hindi starts with the
            # patient's next turn.
            "Can we talk in Hindi?": [
                reply_and_call(
                    "Sure, switching to Hindi.", "switch_language", to={"language": "Hindi"}
                ),
            ],
            "ठीक है।": reply("ठीक है, अब हिंदी में बात करते हैं।"),
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
    """One tool call, with the exact ``ui_command`` payload the /sugar Today
    screen renders — including the calorie total, which the brain sums rather than
    trusting the model to add up.

    It is also the speak-first shape in one turn: one request, one unit of speech,
    and the meal on the wire — ``log_meal`` only echoes the model's own estimate,
    so it is not marked and the model is not asked again after it. Its result
    reaches the model with the patient's next turn."""
    llm = _llm()
    async with demo("sugar", llm) as rig:
        await rig.driver.start_session(init={"scenario": SCENARIO})

        before = len(llm.captured_contents)
        turn = await rig.driver.user_says("I had two rotis and dal at eight.")
        check_turn(rig, turn, units=1)
        assert len(llm.captured_contents) - before == 1, "an unmarked tool took a second request"

        assert rig.actions() == ["log_meal"], rig.actions()
        meal = rig.command("log_meal")
        assert meal["meal_type"] == "dinner"
        assert [i["name"] for i in meal["items"]] == ["Roti", "Dal"]
        assert meal["total_calories"] == 420

        await rig.driver.user_says("That's all I ate.")
        assert "ok, 420 calories" in _results(llm.captured_contents[-1])["log_meal"]


async def test_switching_language_mid_call_moves_both_halves() -> None:
    """The patient asks to switch, and the recognizer follows the voice.

    This is the one part of sugar's language that is a runtime event, so it is the
    one part the brain owns: the page settled the opening language, and a change of
    mind mid-call is something only the conversation knows about.

    ``switch_language`` is one ``session.configure`` call precisely so it cannot
    half-apply. Moving only the TTS leg leaves the recognizer hearing Hindi as
    English — the user is then mis-transcribed for the rest of the call, and the
    reply, generated from that wrong transcript, is merely *odd* rather than
    obviously broken. Assert the pair, on the frames.

    The switch is sent and not awaited, so the turn is one request and one unit —
    the line said in English, before the voice changes — and the next turn is the
    first one written in Hindi."""
    llm = _llm()
    async with demo("sugar", llm) as rig:
        await rig.driver.start_session(init={"scenario": SCENARIO})
        # Nothing yet: the session opened in the language the page asked for.
        check_configured_at_connect(rig)

        before = len(llm.captured_contents)
        turn = await rig.driver.user_says("Can we talk in Hindi?")
        check_turn(rig, turn, units=1)
        assert len(llm.captured_contents) - before == 1, "an unmarked tool took a second request"

        # No ui_command: switching language is a wire change, not a screen change.
        assert rig.actions() == [], rig.actions()
        check_voice_pair(rig, voice=VOICE, language="hi")

        turn = await rig.driver.user_says("ठीक है।")
        check_turn(rig, turn, units=1)


#: A snapshot of the shape ``store.tsx``'s ``snapshot()`` sends.
def _context_text(llm: ScriptedGemini) -> str:
    return " ".join(
        part.text or ""
        for contents in llm.captured_contents
        for content in contents
        if content.role == "user"
        for part in (content.parts or [])
    )


def _results(contents: list[types.Content]) -> dict[str, str]:
    """Every tool result one request carried, by tool name."""
    return {
        p.function_response.name or "": str((p.function_response.response or {})["result"])
        for c in contents
        for p in (c.parts or [])
        if p.function_response is not None
    }


async def test_what_the_patient_tapped_is_named_and_the_screen_never_follows_it() -> None:
    """The gesture arrives typed, and the screen behind it stays where it is.

    This brain used to be sent the whole screen on every change and append it to
    the context, prefixed *authoritative*, so a call that logs a dozen things ended
    with a dozen near-identical screens in front of the model. Now the browser
    sends one ``ui-event`` naming the act — ``sensor_order_confirmed`` — the brain
    patches a picture it owns, and the context gets one line. Both halves are
    asserted: a note carrying the order state would be the old dump again, one fact
    at a time."""
    llm = ScriptedGemini({"What have I got logged?": reply("It is all on your screen.")})
    async with demo("sugar", llm) as rig:
        await rig.driver.start_session(init={"scenario": SCENARIO})
        before = len(rig.driver.ui_commands)

        await rig.driver.send_ui_event("sensor_order_confirmed")
        turn = await rig.driver.user_says("What have I got logged?")
        check_turn(rig, turn, units=1)
        assert len(rig.driver.ui_commands) == before, "an app event drove the screen"

    context = _context_text(llm)
    assert "The patient confirmed the sensor order by tapping the card." in context
    assert "read_screen" in context
    assert "ordered" not in context, "the note is carrying the screen"
    assert "CURRENT SCREEN STATE" not in context, "the screen dump is back"


async def test_a_tool_aimed_at_a_screen_the_patient_moved_is_refused_until_it_is_read() -> None:
    """The version gate, which is what makes read-don't-remember enforceable.

    ``confirm_sensor_order`` is the tool this matters most for: its own description
    tells the coach not to place an order the patient already placed by hand, and
    that instruction is worth nothing if the coach is reasoning from a screen taken
    before the tap. So the tool refuses instead of ordering twice, and the refusal
    is retriable: read, then act.

    ``confirm_sensor_order`` is not marked, so its refusal reaches the coach with
    the patient's next turn, and that is where she reads. ``read_screen`` is
    marked, so the answer after it is grounded in the tap within that same turn."""
    llm = ScriptedGemini(
        {
            "Yes, order it.": reply_and_call(
                "Ordering it.",
                "confirm_sensor_order",  # stale — he tapped it himself
            ),
            "Did it go through?": [
                call("read_screen"),
                reply("You'd already ordered it — nothing more to do."),
            ],
        }
    )
    async with demo("sugar", llm) as rig:
        await rig.driver.start_session(init={"scenario": SCENARIO})
        await rig.driver.send_ui_event("sensor_order_confirmed")

        await rig.driver.user_says("Yes, order it.")
        assert rig.actions() == [], "the order went through on a screen never read"

        before = len(llm.captured_contents)
        turn = await rig.driver.user_says("Did it go through?")
        check_turn(rig, turn, units=1)
        assert len(llm.captured_contents) - before == 2, "read_screen was not answered at once"
        assert rig.actions() == [], "the order went through twice"

    refused = _results(llm.captured_contents[-2])["confirm_sensor_order"]
    assert "the screen moved since you last read it" in refused
    read = _results(llm.captured_contents[-1])["read_screen"]
    assert "the sensor order: ordered" in read, "read_screen did not serve the tap"


async def test_a_log_made_in_silence_gets_the_coachs_line_in_the_calls_language() -> None:
    """The prompt has the coach speak first; this is the turn where it did not.

    A response of ``log_meal`` alone would leave a Hindi patient in silence, so
    the brain says one written line — Hindi's "done" phrase, since the call is in
    Hindi — in the same single request. The line never reaches the context, which
    holds only the model's own words."""
    meal = {
        "meal_type": "dinner",
        "time_label": "8:00 PM",
        "items": [{"name": "Roti", "quantity": "2", "calories": 240}],
    }
    llm = ScriptedGemini(
        {
            "रात को दो रोटी खाई।": call("log_meal", meal=meal),
            "बस इतना ही।": reply("बहुत बढ़िया।"),
        }
    )
    async with demo("sugar", llm) as rig:
        await rig.driver.start_session(init={"language": "Hindi", "scenario": SCENARIO})

        turn = await rig.driver.user_says("रात को दो रोटी खाई।")
        check_turn(rig, turn, units=1)
        (line,) = (u.text for u in turn.units)
        assert line in PHRASES[Language.HI]["done"], line
        assert rig.actions() == ["log_meal"]
        assert len(llm.captured_contents) == 1, "a silent turn asked the model again"

        await rig.driver.user_says("बस इतना ही।")
        spoken = " ".join(
            part.text or ""
            for content in llm.captured_contents[-1]
            if content.role == "model"
            for part in content.parts or []
        )
        assert line not in spoken, f"the coach's line {line!r} reached the context"
