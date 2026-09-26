"""The AI interviewer demo, end to end over the wire — no network, no LLM key.

The real ``InterviewBotBrain`` — the shipping ``demos/interview_bot/backend/brain.py``,
its real prompt, its real tools — hosted on a real ``brain_server`` socket and
driven by the conformance ``VoqalizeDriver``, with only the *model* scripted. See
``tests/_harness.py`` for what every demo's e2e proves.

The interviewer is the demo whose whole shape comes from ``session.init``: the
job, the candidate and the section plan arrive on the start frame, and the brain
rebuilds its system instruction from them before the first word. The greeting
itself is a fixed line, not built from any of that — so this file also pins what
the model was actually told: a greeting that never saw the résumé still sounds
fluent, and only the prompt shows the difference.

**Neither tool carries the mark.** The next section's questions are already in
the system instruction, so the interviewer moves on and asks in one response,
and the turn ends with it; the tool's result is read with the candidate's next
turn. The scripts are written in that shape, and the tests count requests where
the shape is the point.

Run: ``cd demos && uv run pytest tests/test_interview_bot_e2e.py``
"""

from __future__ import annotations

from typing import Any

from google.genai import types
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, reply_and_call

from ._harness import check_greeting, check_turn, check_voice_pair, demo

discover()

VOICE = "omnivoice/gauri"
LANGUAGE = "en"

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


def _results(contents: list[types.Content]) -> dict[str, str]:
    """Every tool result one request carried, by tool name."""
    return {
        p.function_response.name or "": str((p.function_response.response or {})["result"])
        for c in contents
        for p in (c.parts or [])
        if p.function_response is not None
    }


def _llm() -> ScriptedGemini:
    # Each move and its first question share one response: the next section is in
    # the plan the model already holds, and nothing is said after an unmarked call.
    return ScriptedGemini(
        {
            "Six years, mostly payments.": reply_and_call(
                "Thanks — let's go deeper. How did you handle idempotency on retries?",
                "advance_to_next_section",
                notes={"section_notes": "Six years, payments infrastructure."},
            ),
            "Idempotency keys on every write.": reply_and_call(
                "Good. Last stretch — anything you'd like to ask me?",
                "advance_to_next_section",
                notes={"section_notes": "Solid on idempotency."},
            ),
            # The thanks is the last thing the candidate hears: said before the
            # call, in the same response.
            "No, that's everything.": reply_and_call(
                "Thanks for your time. We'll be in touch shortly.",
                "mark_interview_completed",
                summary={"summary": "Strong payments background; clear on idempotency."},
            ),
        }
    )


async def test_greeting_and_voice_reach_the_wire() -> None:
    """The interviewer opens with a fixed line — no model call on the start
    path — and its declared female English voice lands on **both** legs before
    that audio."""
    llm = _llm()
    async with demo("interview_bot", llm) as rig:
        greeting = await rig.driver.start_session(init=PAYLOAD)
        check_greeting(rig, greeting)
        assert greeting is not None
        assert greeting.text == (
            "Hi! I'm your AI interviewer today. We'll go through a few sections "
            "together. Let's get started."
        )
        # The greeting cost no inference — the model has not been called yet.
        assert llm.calls == []
        check_voice_pair(rig, voice=VOICE, language=LANGUAGE)


async def test_the_seeded_plan_reaches_the_model() -> None:
    """The job, the résumé and the ordered plan are in the *system instruction*
    of every inference the model sees, starting with the first turn.

    Rebuilding the config in ``on_session_start`` is what makes that true — the
    greeting itself makes no model call any more, so the plan is asserted on the
    first real inference instead of the opener."""
    llm = _llm()
    async with demo("interview_bot", llm) as rig:
        await rig.driver.start_session(init=PAYLOAD)
        await rig.driver.user_says("Six years, mostly payments.")

    first = llm.captured_system_instructions[0]
    assert "Backend Engineer" in first
    assert "Six years on payments infrastructure." in first
    # Ordered introduction → technical → closing, whatever order the payload used.
    assert first.index("Introduction") < first.index("Technical Depth") < first.index("Closing")


async def test_the_sections_advance_in_order_and_close() -> None:
    """The turns walk the plan — an advance per section, then the completion —
    with the exact ``ui-command`` payloads the /interview progress rail renders.

    ``is_last`` is the one the UI cannot recompute — it drives the closing state —
    and the index is the brain's pointer, not the model's count, so a model that
    calls ``advance`` twice in one turn cannot skip a section.

    It is also the speak-first shape on every turn: one request, one unit of
    speech, and the move on the wire — neither tool is marked, so the model is not
    asked again after it."""
    llm = _llm()
    async with demo("interview_bot", llm) as rig:
        await rig.driver.start_session(init=PAYLOAD)

        for said in (
            "Six years, mostly payments.",
            "Idempotency keys on every write.",
            "No, that's everything.",
        ):
            before = len(llm.captured_contents)
            turn = await rig.driver.user_says(said)
            check_turn(rig, turn, units=1)
            assert len(llm.captured_contents) - before == 1, (
                "an unmarked tool took a second request"
            )

        assert rig.actions() == [
            "section_changed",
            "section_changed",
            "interview_completed",
        ], rig.actions()

        changes = [
            c["payload"] for c in rig.driver.ui_commands if c.get("command") == "section_changed"
        ]
        assert [(c["index"], c["key"], c["is_last"]) for c in changes] == [
            (1, "depth", False),
            (2, "wrap", True),
        ]

        done = rig.command("interview_completed")
        assert done["summary"].startswith("Strong payments background")
        assert rig.brain.ended is True


async def test_the_section_moved_to_reaches_the_next_turn() -> None:
    """``advance_to_next_section`` is not marked, so what it returns — the section
    now entered, by the brain's own pointer — reaches the model with the
    candidate's next turn, on the request that answers it."""
    llm = _llm()
    async with demo("interview_bot", llm) as rig:
        await rig.driver.start_session(init=PAYLOAD)
        await rig.driver.user_says("Six years, mostly payments.")
        await rig.driver.user_says("Idempotency keys on every write.")

    entered = _results(llm.captured_contents[-1])["advance_to_next_section"]
    assert "depth" in entered and "Technical Depth" in entered, entered
