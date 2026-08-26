"""The Forge workflow-studio demo, end to end over the wire — no network, no key.

The real ``ForgeBrain`` — the shipping ``demos/forge/backend/brain.py``, its real
prompt, its real twenty-one tools — hosted on a real ``brain_server`` socket and
driven by the conformance ``VoqalizeDriver``, with only the *model* scripted. See
``tests/_harness.py`` for what every demo's e2e proves.

Forge inverts the usual ownership: the **studio** owns the workflow and Ada only
relays edits, grounded on the ``state_sync`` snapshot it pushes. So the two things
worth pinning are that a tool call reaches the studio with its arguments intact
(each tool's parameter *is* the ``Action`` dispatched — a rename in either repo
silently drops the edit), and that the snapshot lands in the prompt without
taking the floor.

Run: ``cd demos && uv run pytest tests/test_forge_e2e.py``
"""

from __future__ import annotations

from typing import Any

from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, reply, reply_and_call

from ._harness import check_greeting, check_turn, check_voice_pair, demo

discover()

VOICE = "omnivoice/gauri"
LANGUAGE = "en"

PAYLOAD: dict[str, Any] = {"admin": {"name": "Nadia"}}

WORKSPACE = {
    "workflowId": "guest-wifi",
    "states": [
        {"id": "s1", "kind": "form", "label": "Request details"},
        {"id": "s2", "kind": "end", "label": "Done"},
    ],
}


def _llm() -> ScriptedGemini:
    return ScriptedGemini(
        {
            "Open the guest wifi workflow.": [
                # One tool, one model, one parameter — the argument is the
                # ``Action`` the studio applies, nested under the name the
                # method gives it (``action``), just as the model would send it.
                reply_and_call("Opening it.", "open_workflow", action={"id": "guest-wifi"}),
                reply("Guest Wi-Fi is open — a form block and an end."),
            ],
            "Add a manager approval after the form.": [
                reply_and_call(
                    "Adding it.",
                    "add_state",
                    action={
                        "after": "s1",
                        "kind": "approval",
                        "label": "Manager approval",
                        "approver": "Reporting manager",
                        "sla_hours": 24,
                    },
                ),
                reply("Approval added after the request form."),
            ],
            "What's on screen?": reply("The guest Wi-Fi flow."),
        }
    )


async def test_greeting_and_voice_reach_the_wire() -> None:
    """Ada opens with a fixed line — no model call on the start path — and her
    declared voice lands on **both** legs before that audio."""
    async with demo("forge", _llm()) as rig:
        greeting = await rig.driver.start_session(init=PAYLOAD)
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text.startswith("Hi there — Ada here.")
        check_voice_pair(rig, voice=VOICE, language=LANGUAGE)


async def test_edits_reach_the_studio_with_their_arguments_intact() -> None:
    """Forge dispatches each tool's own parameter **verbatim**: the pydantic model
    the model filled in *is* the ``ui-command`` payload the studio store reads.

    That is the whole contract, and it is one rename away from breaking silently —
    the model still calls the tool, Ada still says "added", and the block never
    appears. So assert the payload key by key rather than just the action."""
    async with demo("forge", _llm()) as rig:
        await rig.driver.start_session(init=PAYLOAD)

        t1 = await rig.driver.user_says("Open the guest wifi workflow.")
        check_turn(rig, t1, units=2)
        t2 = await rig.driver.user_says("Add a manager approval after the form.")
        check_turn(rig, t2, units=2)

        assert rig.actions() == ["open_workflow", "add_state"], rig.actions()
        assert rig.command("open_workflow")["id"] == "guest-wifi"

        added = rig.command("add_state")
        assert added["after"] == "s1"
        assert added["kind"] == "approval"
        assert added["label"] == "Manager approval"
        assert added["approver"] == "Reporting manager"
        assert added["sla_hours"] == 24


async def test_the_workspace_snapshot_grounds_the_next_turn_silently() -> None:
    """``state_sync`` is ingested without taking the floor, and shows up in the next
    turn's prompt as the authoritative block ids Ada must edit against.

    Before any snapshot arrives there is deliberately **no** workspace grounding —
    an empty state and an unknown state are different things, and asserting the
    absence is what stops the brain inventing block ids on the first turn."""
    llm = _llm()
    async with demo("forge", llm) as rig:
        await rig.driver.start_session(init=PAYLOAD)

        first = await rig.driver.user_says("What's on screen?")
        check_turn(rig, first, units=1)
        assert "CURRENT WORKSPACE STATE" not in _user_text(llm.captured_contents[-1])

        before = len(rig.driver.ui_commands)
        await rig.driver.send_client_message("state_sync", {"workspace": WORKSPACE})

        second = await rig.driver.user_says("What's on screen?")
        check_turn(rig, second, units=1)
        assert len(rig.driver.ui_commands) == before, "state_sync drove the screen"

    grounded = _user_text(llm.captured_contents[-1])
    assert "CURRENT WORKSPACE STATE" in grounded
    # The block ids specifically: they are what the next edit has to name.
    assert '"id": "s1"' in grounded


def _user_text(contents: list[Any]) -> str:
    return "".join(
        p.text or "" for c in contents if c.role == "user" for p in (c.parts or []) if p.text
    )
