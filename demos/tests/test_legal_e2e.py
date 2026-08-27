"""The Contract Copilot demo, end to end over the wire — no network, no LLM key.

The real ``LegalBrain`` — the shipping ``demos/legal/backend/brain.py``, its real
prompt, its real eight tools, its real MSA — hosted on a real ``brain_server``
socket and driven by the conformance ``VoqalizeDriver``, with only the *model*
scripted. See ``tests/_harness.py`` for what every demo's e2e proves.

Legal is the demo that earns a **silent** browser→brain test: ``clause_focus``
carries the lawyer's reading position and must fold into context **without**
taking the floor. A copilot that answered every scroll would talk over its user,
and a copilot that ignored the message would answer "what does this mean?" about
the wrong clause — neither is visible in a transcript of the spoken turns.

Run: ``cd demos && uv run pytest tests/test_legal_e2e.py``
"""

from __future__ import annotations

from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, reply, reply_and_call

from ._harness import check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.legal.brain import _GREETING  # noqa: E402

VOICE = "omnivoice/gauri"
LANGUAGE = "en"

# c2 is Term & Termination in the shipped MSA. ``ClauseId`` is a Literal over the
# real contract, so a clause id that is not in the document cannot reach a tool
# body at all — this test fails at validation if the contract is re-cut.
CLAUSE = "c2"


def _llm() -> ScriptedGemini:
    return ScriptedGemini(
        {
            "Take me to the termination clause.": [
                reply_and_call(
                    "Here it is.",
                    "point_to_clause",
                    # One tool, one model, one parameter — the argument is the
                    # ``PointToClause`` the browser renders, nested under the name
                    # the method gives it. That name is part of the schema Gemini
                    # reads, so a script writes what the model would write.
                    target={"clause_id": CLAUSE, "reason": "Termination and wind-down fee"},
                ),
                reply("Clause two — thirty-six months, with a twenty-five percent wind-down fee."),
            ],
            "That wind-down fee is too rich. Push back.": [
                reply_and_call(
                    "Drafting the redline.",
                    "propose_redline",
                    redline={
                        "clause_id": CLAUSE,
                        "original_excerpt": "twenty-five percent (25%)",
                        "proposed_text": "ten percent (10%)",
                        "rationale": "Market for a 36-month term is 10%.",
                    },
                ),
                reply("Redline is in — twenty-five percent down to ten."),
            ],
            "What does this mean?": reply("It caps your exposure on an early exit."),
        }
    )


async def test_greeting_and_voice_reach_the_wire() -> None:
    """The copilot opens with a fixed quiet line — no model call on the start path —
    and its declared female English voice lands on **both** legs before that audio."""
    async with demo("legal", _llm()) as rig:
        greeting = await rig.driver.start_session()
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text == _GREETING
        check_voice_pair(rig, voice=VOICE, language=LANGUAGE)


async def test_pointing_and_redlining_drive_the_document() -> None:
    """Two turns, each a tool round-trip, with the exact ``ui_command`` payloads the
    /legal Docket UI renders — the clause ids resolved against the real MSA."""
    async with demo("legal", _llm()) as rig:
        await rig.driver.start_session()

        t1 = await rig.driver.user_says("Take me to the termination clause.")
        check_turn(rig, t1, units=2)

        t2 = await rig.driver.user_says("That wind-down fee is too rich. Push back.")
        check_turn(rig, t2, units=2)

        assert rig.actions() == ["point_to_clause", "propose_redline"], rig.actions()
        assert rig.command("point_to_clause")["clause_id"] == CLAUSE

        redline = rig.command("propose_redline")
        assert redline["clause_id"] == CLAUSE
        assert redline["original_excerpt"] == "twenty-five percent (25%)"
        assert redline["proposed_text"] == "ten percent (10%)"
        # Every declared field crosses, including the rationale the card prints
        # under the diff — the payload is the validated call, not a subset of it.
        assert redline["rationale"] == "Market for a 36-month term is 10%."


async def test_the_reading_position_lands_silently_and_grounds_the_next_answer() -> None:
    """``clause_focus`` is the one client message that must **not** speak.

    The lawyer scrolling is not a question: the brain records the position and
    stays quiet, and only the next spoken turn shows it took — the clause on
    screen is in the prompt, so "what does this mean?" has a referent. Both halves
    are asserted here because either one alone passes for the wrong reason: a
    brain that ignored the message is also silent."""
    llm = _llm()
    async with demo("legal", llm) as rig:
        await rig.driver.start_session()
        before = len(rig.driver.ui_commands)

        await rig.driver.send_client_message(
            "clause_focus",
            {"clause_id": CLAUSE, "heading": "Term & Termination"},
        )
        # The floor is untaken: no speech, no screen command. Frames on one
        # connection are ordered, so the focus is already ingested by the time the
        # next turn is served — which is what the assertion below proves.
        turn = await rig.driver.user_says("What does this mean?")
        check_turn(rig, turn, units=1)
        assert len(rig.driver.ui_commands) == before, "clause_focus drove the screen"

    grounded = "".join(
        p.text or "" for c in llm.captured_contents[-1] for p in (c.parts or []) if c.role == "user"
    )
    assert "LAWYER IS CURRENTLY VIEWING" in grounded
    assert CLAUSE in grounded
