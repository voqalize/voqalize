"""The Servicing Desk demo, end to end over the wire — no network, no LLM key.

The real ``ServicingBrain`` — the shipping ``demos/servicing/backend/brain.py``,
its real prompt, its real fifteen tools — hosted on a real ``brain_server`` socket
and driven by the conformance ``VoqalizeDriver``, with only the *model* scripted. See
``tests/_harness.py`` for what every demo's e2e proves.

The desk is the demo that leans hardest on the brain **normalising the model's
output** before it reaches the console: case refs are upper-cased, and the jobs
and findings the model invents are given stable ids the browser keys its rows by.
Both are invisible in the reply and load-bearing on screen.

It is also the widest browser→brain vocabulary in the fleet, because the advisor
is a colleague with both hands on the same screen: he opens cases, routes them,
signs off drafts and submits packets while talking. Each of those arrives as a
typed ``ui-event`` naming the *act*, and the board itself rides ``session.init``
— the browser never pushes a workspace, so there is nothing to diff and nothing
to go stale in the context.

Run: ``cd demos && uv run pytest tests/test_servicing_e2e.py``
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any

from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, call, reply, reply_and_call

from ._harness import check_greeting, check_turn, check_voice_pair, demo

discover()

VOICE = "omnivoice/gauri"
LANGUAGE = "en"

#: The board as ``data.ts``'s ``boardSeed()`` sends it — the worklist the advisor
#: logged in to, handed over once in ``init`` instead of pushed on every change.
BOARD: list[dict[str, Any]] = [
    {
        "ref": "SR-4471",
        "customer": "Sharma",
        "type": "hardship",
        "title": "Hardship review",
        "stage": "in_progress",
        "priority": "high",
        "assignee": "Kavita",
        "findings": [],
        "blocker": None,
        "packet": None,
        "pending_approvals": ["Payoff release"],
        "notes": [],
    },
    {
        "ref": "SR-4482",
        "customer": "Iyer",
        "type": "rate_change",
        "title": "Rate reduction request",
        "stage": "new",
        "priority": "normal",
        "assignee": "Marcus Bell",
        "findings": [],
        "blocker": None,
        "packet": None,
        "pending_approvals": [],
        "notes": [],
    },
]


def _payload() -> dict[str, Any]:
    """A fresh init each time — the brain patches the board it is handed in place,
    exactly as it would patch the console."""
    return {
        "advisor": {"name": "Kavita", "role": "Senior Servicing Advisor"},
        "cases": deepcopy(BOARD),
    }


def _llm() -> ScriptedGemini:
    return ScriptedGemini(
        {
            # Lower-case on purpose: the model writes what it heard, the brain
            # normalises it. See the assertion below.
            "Pull up the Sharma escalation.": [
                reply_and_call(
                    "Opening it.",
                    "open_case",
                    # One tool, one model, one parameter — the argument is the
                    # ``OpenCase`` the browser renders, nested under the name
                    # the method gives it. That name is part of the schema
                    # Gemini reads, so a script writes what the model would
                    # write.
                    action={"ref": "sr-4471"},
                ),
                reply("SR-4471 is up — the Sharma escalation."),
            ],
            "Work it up and send it to underwriting.": [
                reply_and_call(
                    "On it.",
                    "prepare_case",
                    action={
                        "ref": "sr-4471",
                        "summary": "Hardship request, income re-verification pending.",
                        "jobs": [
                            {"label": "Re-pull income docs"},
                            {"label": "Recompute DTI"},
                        ],
                        "findings": [
                            {
                                "label": "Payslip is three months stale",
                                "value": "Latest payslip on file is dated three months ago",
                            }
                        ],
                    },
                ),
                reply_and_call(
                    "Routing it.",
                    "assign_case",
                    action={
                        "ref": "sr-4471",
                        "assignee_kind": "department",
                        "assignee": "underwriting",
                    },
                ),
                reply("Work-up is running and it's with underwriting."),
            ],
            "Where am I?": [
                reply_and_call("Let me look.", "get_advisor_context"),
                reply("You're on SR-4471's timeline, two approvals pending."),
            ],
        }
    )


async def test_greeting_and_voice_reach_the_wire() -> None:
    """The desk opens with a fixed line — no model call on the start path — and
    its declared voice lands on **both** legs first."""
    async with demo("servicing", _llm()) as rig:
        greeting = await rig.driver.start_session(init=_payload())
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text.startswith("Hi there — Servicing Desk here.")
        check_voice_pair(rig, voice=VOICE, language=LANGUAGE)


async def test_the_desk_normalizes_what_the_model_wrote() -> None:
    """A case ref reaches the console upper-cased, and every job and finding
    carries a stable id.

    Neither is something the model can be relied on to produce: it writes the ref
    the way it heard it, and it does not know the browser keys rows by id. A
    lower-case ref matches no case and an id-less row cannot be updated — and in
    both failures the assistant's spoken reply is perfectly correct, so only the
    ``ui_command`` shows it."""
    async with demo("servicing", _llm()) as rig:
        await rig.driver.start_session(init=_payload())

        t1 = await rig.driver.user_says("Pull up the Sharma escalation.")
        check_turn(rig, t1, units=2)
        assert rig.command("open_case")["ref"] == "SR-4471"

        t2 = await rig.driver.user_says("Work it up and send it to underwriting.")
        check_turn(rig, t2, units=3)

        assert rig.actions() == ["open_case", "prepare_case", "assign_case"], rig.actions()

        prepared = rig.command("prepare_case")
        assert prepared["ref"] == "SR-4471"
        assert [j["id"] for j in prepared["jobs"]] == ["j1", "j2"]
        assert [f["id"] for f in prepared["findings"]] == ["f1"]

        assigned = rig.command("assign_case")
        assert assigned["ref"] == "SR-4471"
        assert assigned["assignee_kind"] == "department"
        assert assigned["assignee"] == "underwriting"


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


async def test_a_gesture_is_named_in_the_context_and_the_board_never_follows_it() -> None:
    """What the advisor did with his own hand reaches the model as one line; what
    is *on* the case reaches it only through the tool.

    This used to append the whole workspace on every change, prefixed
    *authoritative*, so a session working a queue ended with a hundred
    near-identical consoles in front of the model. Now the gesture is typed, the
    line names the act, and the board — which the desk was handed once, in
    ``init`` — is read through ``get_advisor_context``, the one tool that drives
    no screen. Both halves are asserted: the customer and the draft's title must
    be in the tool's result and out of the context."""
    llm = _llm()
    async with demo("servicing", llm) as rig:
        await rig.driver.start_session(init=_payload())
        before = len(rig.driver.ui_commands)

        await rig.driver.send_ui_event("case_opened", {"ref": "sr-4471"})
        await rig.driver.send_ui_event(
            "approval_decided",
            {
                "ref": "SR-4471",
                "approval_id": "ap-1",
                "decision": "approved",
                "title": "Payoff release",
            },
        )
        # `send_ui_event` returns once the frame is sent, not once `on_rtvi` has
        # run it (it takes no floor, so there is nothing to await) — give the
        # ingestion a beat before the next turn's prompt is built, or the model
        # call can race it.
        await asyncio.sleep(0.1)

        turn = await rig.driver.user_says("Where am I?")
        check_turn(rig, turn, units=2)
        assert len(rig.driver.ui_commands) == before, "a gesture or the read-only tool drew"

        # One more turn, so the turn above's tool results are in a request.
        await rig.driver.user_says("Where am I?")

    context = _context_text(llm)
    # The ref is the handle the next tool call needs; the case behind it is not.
    assert "The advisor opened SR-4471 himself." in context, context
    assert "approved a draft on SR-4471 himself — his call, never yours" in context, context
    assert "CURRENT WORKSPACE STATE" not in context, "the workspace dump is back"
    assert "Sharma" not in context, "the board reached the context anyway"
    assert "Payoff release" not in context, "the draft's title followed the gesture in"

    results = _tool_results(llm)
    assert "Sharma" in results, results
    assert "approved: Payoff release" in results, results


async def test_a_packet_edit_on_a_console_the_advisor_moved_is_refused_until_it_is_read() -> None:
    """The version gate, which is what makes read-don't-remember enforceable.

    The advisor works the console with their own hands while talking, so a packet
    field the desk sets from a workspace it read two turns ago can land on a
    different case entirely. Prompt discipline is a request; this refuses instead,
    and the refusal is retriable: read, then act."""
    llm = ScriptedGemini(
        {
            "Set the payoff date to month-end.": [
                # Stale — the advisor moved the console since. Then the retry.
                call(
                    "update_packet_field",
                    action={
                        "ref": "sr-4471",
                        "section": "Payoff",
                        "field": "Payoff date",
                        "value": "30 Sep",
                    },
                ),
                call("get_advisor_context"),
                reply_and_call(
                    "Setting it.",
                    "update_packet_field",
                    action={
                        "ref": "sr-4471",
                        "section": "Payoff",
                        "field": "Payoff date",
                        "value": "30 Sep",
                    },
                ),
                reply("Payoff date is month-end."),
            ],
            "Thanks.": reply("Any time."),
        }
    )
    async with demo("servicing", llm) as rig:
        await rig.driver.start_session(init=_payload())
        await rig.driver.send_ui_event("case_opened", {"ref": "SR-4471"})
        await asyncio.sleep(0.1)

        await rig.driver.user_says("Set the payoff date to month-end.")
        # Exactly one edit reached the console: the stale call drew nothing.
        assert rig.actions() == ["update_packet_field"], rig.actions()

        # One more turn, so the turn above's hops are in the context being asserted.
        await rig.driver.user_says("Thanks.")

    assert "the screen moved since you last read it" in _tool_results(llm)
