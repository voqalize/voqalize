"""The Servicing Desk demo, end to end over the wire — no network, no LLM key.

The real ``ServicingBrain`` — the shipping ``demos/servicing/backend/brain.py``,
its real prompt, its real fifteen tools — hosted on a real ``DirectAgent`` socket
and driven by the conformance ``VoiceDriver``, with only the *model* scripted. See
``tests/_harness.py`` for what every demo's e2e proves.

The desk is the demo that leans hardest on the brain **normalising the model's
output** before it reaches the console: case refs are upper-cased, and the jobs
and findings the model invents are given stable ids the browser keys its rows by.
Both are invisible in the reply and load-bearing on screen.

Run: ``cd demos && uv run pytest tests/test_servicing_e2e.py``
"""

from __future__ import annotations

from typing import Any

from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, reply, reply_and_call

from ._harness import check_greeting, check_turn, check_voice_pair, demo

discover()

VOICE = "omnivoice/gauri"
LANGUAGE = "en"

PAYLOAD: dict[str, Any] = {"advisor": {"name": "Kavita", "role": "Senior Servicing Advisor"}}

WORKSPACE = {
    "view": "case",
    "active_case": "SR-4471",
    "tab": "timeline",
    "pending_approvals": 2,
}


def _llm() -> ScriptedGemini:
    return ScriptedGemini(
        {
            # Lower-case on purpose: the model writes what it heard, the brain
            # normalises it. See the assertion below.
            "Pull up the Sharma escalation.": [
                reply_and_call("Opening it.", "open_case", ref="sr-4471"),
                reply("SR-4471 is up — the Sharma escalation."),
            ],
            "Work it up and send it to underwriting.": [
                reply_and_call(
                    "On it.",
                    "prepare_case",
                    args={
                        "ref": "sr-4471",
                        "summary": "Hardship request, income re-verification pending.",
                        "jobs": [
                            {"label": "Re-pull income docs"},
                            {"label": "Recompute DTI"},
                        ],
                        "findings": [{"label": "Payslip is three months stale"}],
                    },
                ),
                reply_and_call(
                    "Routing it.",
                    "assign_case",
                    args={
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
    """The desk greets the advisor by name from the init payload — no model call on
    the start path — and its declared voice lands on **both** legs first."""
    async with demo("servicing", _llm()) as rig:
        greeting = await rig.driver.start_session(payload=PAYLOAD)
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text.startswith("Hi Kavita — Servicing Desk here.")
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
        await rig.driver.start_session(payload=PAYLOAD)

        t1 = await rig.driver.user_says("Pull up the Sharma escalation.")
        check_turn(rig, t1, inferences=2)
        assert rig.command("open_case")["ref"] == "SR-4471"

        t2 = await rig.driver.user_says("Work it up and send it to underwriting.")
        check_turn(rig, t2, inferences=3)

        assert rig.actions() == ["open_case", "prepare_case", "assign_case"], rig.actions()

        prepared = rig.command("prepare_case")
        assert prepared["ref"] == "SR-4471"
        assert [j["id"] for j in prepared["jobs"]] == ["j1", "j2"]
        assert [f["id"] for f in prepared["findings"]] == ["f1"]

        assigned = rig.command("assign_case")
        assert assigned["ref"] == "SR-4471"
        assert assigned["assignee_kind"] == "department"
        assert assigned["assignee"] == "underwriting"


async def test_the_console_snapshot_is_ingested_silently_and_answers_where_am_i() -> None:
    """``state_sync`` takes no floor, and then backs both the turn's grounding and
    the read-only ``get_advisor_context`` tool.

    ``get_advisor_context`` is the one tool that drives no screen — it exists so the
    assistant can answer about the console without moving it — so its correctness
    is only visible in what the snapshot made available."""
    llm = _llm()
    async with demo("servicing", llm) as rig:
        await rig.driver.start_session(payload=PAYLOAD)
        before = len(rig.driver.ui_commands)

        await rig.driver.send_client_message("state_sync", {"workspace": WORKSPACE})

        turn = await rig.driver.user_says("Where am I?")
        check_turn(rig, turn, inferences=2)
        assert len(rig.driver.ui_commands) == before, "state_sync or the read-only tool drew"
        assert rig.brain.current_state == WORKSPACE

    grounded = "".join(
        p.text or ""
        for c in llm.captured_contents[-1]
        if c.role == "user"
        for p in (c.parts or [])
        if p.text
    )
    assert "CURRENT WORKSPACE STATE" in grounded
    assert "SR-4471" in grounded
