"""The Contract Copilot demo, end to end over the wire — no network, no LLM key.

The real ``LegalBrain`` — the shipping ``demos/legal/backend/brain.py``, its real
prompt, its real tools, its real MSA — hosted on a real ``brain_server``
socket and driven by the conformance ``VoqalizeDriver``, with only the *model*
scripted. See ``tests/_harness.py`` for what every demo's e2e proves.

Legal is the demo that earns a **silent** browser→brain test: ``clause_focused``
carries the lawyer's reading position and must fold into context **without**
taking the floor. A copilot that answered every scroll would talk over its user,
and a copilot that ignored the message would answer "what does this mean?" about
the wrong clause — neither is visible in a transcript of the spoken turns.

Run: ``cd demos && uv run pytest tests/test_legal_e2e.py``
"""

from __future__ import annotations

from typing import Any

from google.genai import types
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, call, reply, reply_and_call

from ._harness import check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.legal.brain import _GREETING  # noqa: E402

VOICE = "kokoro/ava"
LANGUAGE = "en"

# c2 is Term & Termination in the shipped MSA. ``ClauseId`` is a Literal over the
# real contract, so a clause id that is not in the document cannot reach a tool
# body at all — this test fails at validation if the contract is re-cut.
CLAUSE = "c2"


def _llm() -> ScriptedGemini:
    return ScriptedGemini(
        {
            # Speak-first: the line said with the call is the whole reply. The
            # model reads each result with the lawyer's next message, so nothing
            # plays after these unmarked calls this turn.
            "Take me to the termination clause.": reply_and_call(
                "Section two — thirty-six months, with a twenty-five percent wind-down fee.",
                "point_to_clause",
                # One tool, one model, one parameter — the argument is the
                # ``PointToClause`` the browser renders, nested under the name
                # the method gives it. That name is part of the schema Gemini
                # reads, so a script writes what the model would write.
                target={"clause_id": CLAUSE, "reason": "Termination and wind-down fee"},
            ),
            "That wind-down fee is too rich. Push back.": reply_and_call(
                "Redlining it — twenty-five percent down to ten.",
                "propose_redline",
                redline={
                    "clause_id": CLAUSE,
                    "original_excerpt": "twenty-five percent (25%)",
                    "proposed_text": "ten percent (10%)",
                    "rationale": "Market for a 36-month term is 10%.",
                },
            ),
            "What does this mean?": reply("It caps your exposure on an early exit."),
            # The one marked tool: the answer depends on where they are, so the
            # read is followed at once by a second request carrying its result.
            "Is this one standard?": [
                reply_and_call("One sec.", "get_reading_position"),
                reply("Yes — ninety days' notice is market for a renewal."),
            ],
            "Check the cap against the playbook and model our exposure.": reply_and_call(
                "Setting both going.",
                "run_diligence",
                diligence={
                    "jobs": [
                        {
                            "label": "Check liability cap vs. playbook",
                            "kind": "finding",
                            "summary": "Fails the $2M floor.",
                            "finding_value": "$250,000 flat cap, no carve-outs",
                            "finding_flag": "risk",
                        },
                        {
                            "label": "Model breach exposure",
                            "kind": "exposure",
                            "summary": "Roughly $1.75M uncovered.",
                            "exposure_cap": "$250,000",
                            "exposure_estimate": "$2,000,000",
                        },
                    ]
                },
            ),
            "Which one is worse?": reply("The exposure gap — about one point seven five million."),
        }
    )


async def test_greeting_and_voice_reach_the_wire() -> None:
    """The copilot opens with a fixed quiet line — no model call on the start path —
    and its declared English voice lands on **both** legs before that audio."""
    async with demo("legal", _llm()) as rig:
        greeting = await rig.driver.start_session()
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text == _GREETING
        check_voice_pair(rig, voice=VOICE, language=LANGUAGE)


async def test_pointing_and_redlining_drive_the_document() -> None:
    """Two turns, each one spoken line with its tool call in the same response, and
    the exact ``ui_command`` payloads the /legal Docket UI renders — the clause ids
    resolved against the real MSA. Neither tool is marked, so each turn is one
    request and one unit: nothing is spoken after the screen moves."""
    async with demo("legal", _llm()) as rig:
        await rig.driver.start_session()

        t1 = await rig.driver.user_says("Take me to the termination clause.")
        check_turn(rig, t1, units=1)

        t2 = await rig.driver.user_says("That wind-down fee is too rich. Push back.")
        check_turn(rig, t2, units=1)

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
    """``clause_focused`` is the one app event that must **not** speak.

    The lawyer scrolling is not a question: the brain records the position and
    stays quiet, and only the next spoken turn shows it took — one line saying
    they moved, pointing at the tool that reads back *where*. Both halves are
    asserted because either alone passes for the wrong reason: a brain that
    ignored the event is also silent, and the clause is nowhere in the context as
    a blob, which is the whole point of the read tool."""
    llm = _llm()
    async with demo("legal", llm) as rig:
        await rig.driver.start_session()
        before = len(rig.driver.ui_commands)

        await rig.driver.send_ui_event("clause_focused", {"clause_id": CLAUSE})
        # The floor is untaken: no speech, no screen command. Frames on one
        # connection are ordered, so the focus is already ingested by the time the
        # next turn is served — which is what the assertion below proves.
        turn = await rig.driver.user_says("What does this mean?")
        check_turn(rig, turn, units=1)
        assert len(rig.driver.ui_commands) == before, "clause_focused drove the screen"

    grounded = "".join(
        p.text or "" for c in llm.captured_contents[-1] for p in (c.parts or []) if c.role == "user"
    )
    assert "scrolled to a different clause" in grounded
    assert "get_reading_position" in grounded
    assert "LAWYER IS CURRENTLY VIEWING" not in grounded


def _function_responses(contents: list[types.Content]) -> dict[str, Any]:
    """Every tool result in a request, by tool name."""
    return {
        p.function_response.name or "": p.function_response.response
        for c in contents
        for p in c.parts or []
        if p.function_response is not None
    }


async def test_the_reading_position_is_read_before_the_answer() -> None:
    """``get_reading_position`` is the one tool whose result the model needs to say
    its reply, so it is marked: the line before it and the answer after it are two
    units of one turn, and the second request already carries where they are."""
    llm = _llm()
    async with demo("legal", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.send_ui_event("clause_focused", {"clause_id": CLAUSE})

        requests = len(llm.calls)
        turn = await rig.driver.user_says("Is this one standard?")
        check_turn(rig, turn, units=2)

    assert len(llm.calls) == requests + 2, "the marked read did not take a second request"
    position = _function_responses(llm.captured_contents[-1])["get_reading_position"]
    assert "Term & Termination" in str(position), position


async def test_diligence_speaks_first_and_its_result_waits_a_turn() -> None:
    """The hero move: one spoken line starts the background angles and the turn
    ends there — one request, one unit, the cards on screen. The tool's result is
    read with the lawyer's next message, which is where it has to be."""
    llm = _llm()
    async with demo("legal", llm) as rig:
        await rig.driver.start_session()

        requests = len(llm.calls)
        turn = await rig.driver.user_says(
            "Check the cap against the playbook and model our exposure."
        )
        check_turn(rig, turn, units=1)
        assert len(llm.calls) == requests + 1, "an unmarked tool took a second request"
        assert rig.actions() == ["run_diligence"], rig.actions()
        assert [j["kind"] for j in rig.command("run_diligence")["jobs"]] == [
            "finding",
            "exposure",
        ]

        await rig.driver.user_says("Which one is worse?")

    assert "run_diligence" in _function_responses(llm.captured_contents[-1])


async def test_a_clause_brought_up_in_silence_is_still_said() -> None:
    """The prompt has the model speak with every call; this is the turn where it
    did not. The brain names the clause it brought up — one request, no second
    ask — and the line never reaches the model's context."""
    llm = ScriptedGemini(
        {
            "Take me to the limitation of liability clause.": call(
                "point_to_clause", target={"clause_id": "c8"}
            ),
            "Thanks.": reply("Of course."),
        }
    )
    async with demo("legal", llm) as rig:
        await rig.driver.start_session()
        turn = await rig.driver.user_says("Take me to the limitation of liability clause.")
        check_turn(rig, turn, units=1)
        assert [u.text for u in turn.units] == ["Here's Section 8, Limitation of Liability."]
        assert rig.actions() == ["point_to_clause"]
        assert len(llm.captured_contents) == 1, "a silent turn asked the model again"

        await rig.driver.user_says("Thanks.")
        spoken = " ".join(
            part.text or ""
            for content in llm.captured_contents[-1]
            if content.role == "model"
            for part in content.parts or []
        )
        assert "Here's Section 8" not in spoken, "the brain's line reached the context"
