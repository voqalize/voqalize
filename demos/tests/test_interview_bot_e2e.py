"""The AI interviewer demo, end to end over the wire — no network, no LLM key.

The real ``InterviewBrain`` — the shipping ``demos/interview_bot/backend/brain.py``,
its real prompt, its real two tools — hosted on a real ``DirectAgent`` socket and
driven by the conformance ``VoiceDriver``, with only the *model* scripted. See
``tests/_harness.py`` for what every demo's e2e proves.

The interviewer is the demo whose whole shape comes from ``init_payload``: the
job, the candidate and the section plan arrive on the start frame, and the brain
rebuilds its system instruction from them before the first word. So this file also
pins what the model was actually told — a greeting that never saw the resume is
still a fluent greeting, and only the prompt shows the difference.

Run: ``cd demos && uv run pytest tests/test_interview_bot_e2e.py``
"""

from __future__ import annotations

from typing import Any

from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, reply, reply_and_call

from ._harness import check_greeting, check_turn, check_voice_pair, demo

discover()

VOICE = "omnivoice/gauri"
LANGUAGE = "en"

# The distinctive phrase in `_greeting_prompt()`.
GREETING_PROMPT = "warmly by name"

# Section order is the brain's, not the payload's: introduction first, closing
# last, everything else stable in between. Seeded here out of order on purpose.
PAYLOAD: dict[str, Any] = {
    "job": {"title": "Backend Engineer", "description": "Python services at scale."},
    "candidate": {"name": "Priya Nair", "resume_text": "Six years on payments infrastructure."},
    "plan": {
        "sections": {
            "depth": {"type": "technical", "title": "Technical Depth"},
            "wrap": {"type": "closing", "title": "Closing"},
            "intro": {"type": "introduction", "title": "Introduction"},
        }
    },
}


def _llm() -> ScriptedGemini:
    return ScriptedGemini(
        {
            GREETING_PROMPT: reply(
                "Priya, good to meet you — I'm your AI interviewer for the Backend "
                "Engineer role. Tell me about yourself."
            ),
            "Six years, mostly payments.": [
                reply_and_call(
                    "Thanks — let's go deeper.",
                    "advance_to_next_section",
                    section_notes="Six years, payments infrastructure.",
                ),
                reply("How did you handle idempotency on retries?"),
            ],
            "Idempotency keys on every write.": [
                reply_and_call(
                    "Good. Last stretch.",
                    "advance_to_next_section",
                    section_notes="Solid on idempotency.",
                ),
                reply("Anything you'd like to ask me?"),
            ],
            "No, that's everything.": [
                reply_and_call(
                    "Thanks for your time.",
                    "mark_interview_completed",
                    summary="Strong payments background; clear on idempotency.",
                ),
                reply("We'll be in touch shortly."),
            ],
        }
    )


async def test_greeting_and_voice_reach_the_wire() -> None:
    """The interviewer opens with the instant "Hi!" plus the model's personalised
    remainder, and its declared female English voice lands on **both** legs first."""
    async with demo("interview_bot", _llm()) as rig:
        greeting = await rig.driver.start_session(payload=PAYLOAD)
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text.startswith("Hi!")
        assert "Priya" in greeting.text
        check_voice_pair(rig, voice=VOICE, language=LANGUAGE)


async def test_the_seeded_plan_reaches_the_model() -> None:
    """The job, the resume and the ordered plan are in the *system instruction* of
    the very first inference — the greeting's own.

    Rebuilding the config in ``on_session_start`` is what makes that true; before
    it, the greeting was generated from the base prompt and only later turns saw
    the candidate. Both greetings sound fine, which is why this is asserted on the
    prompt and not on the words."""
    llm = _llm()
    async with demo("interview_bot", llm) as rig:
        await rig.driver.start_session(payload=PAYLOAD)

    first = llm.captured_system_instructions[0]
    assert "Backend Engineer" in first
    assert "Six years on payments infrastructure." in first
    # Ordered introduction → technical → closing, whatever order the payload used.
    assert first.index("Introduction") < first.index("Technical Depth") < first.index("Closing")


async def test_the_sections_advance_in_order_and_close() -> None:
    """Three turns walk the plan: two advances and a completion, with the exact
    ``ui_command`` payloads the /interview progress rail renders.

    ``is_last`` is the one the UI cannot recompute — it drives the closing state —
    and the index is the brain's pointer, not the model's count, so a model that
    calls ``advance`` twice in one turn cannot skip a section."""
    async with demo("interview_bot", _llm()) as rig:
        await rig.driver.start_session(payload=PAYLOAD)

        t1 = await rig.driver.user_says("Six years, mostly payments.")
        check_turn(rig, t1, inferences=2)
        t2 = await rig.driver.user_says("Idempotency keys on every write.")
        check_turn(rig, t2, inferences=2)
        t3 = await rig.driver.user_says("No, that's everything.")
        check_turn(rig, t3, inferences=2)

        assert rig.actions() == [
            "section_changed",
            "section_changed",
            "interview_completed",
        ], rig.actions()

        changes = [c for c in rig.driver.ui_commands if c.get("action") == "section_changed"]
        assert [(c["index"], c["key"], c["is_last"]) for c in changes] == [
            (1, "depth", False),
            (2, "wrap", True),
        ]

        done = rig.command("interview_completed")
        assert done["summary"].startswith("Strong payments background")
        assert rig.brain.ended is True
