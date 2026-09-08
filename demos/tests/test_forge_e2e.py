"""The Forge workflow-studio demo, end to end over the wire — no network, no key.

The real ``ForgeBrain`` — the shipping ``demos/forge/backend/brain.py``, its real
prompt, its real twenty-one tools — hosted on a real ``brain_server`` socket and
driven by the conformance ``VoqalizeDriver``, with only the *model* scripted. See
``tests/_harness.py`` for what every demo's e2e proves.

Forge inverts the usual ownership: the **studio** owns the workflow and Ada only
relays edits, grounded on the ``state_sync`` snapshot it pushes. So the two things
worth pinning are that a tool call reaches the studio with its arguments intact
(each tool's parameter *is* the ``Action`` dispatched — a rename in either repo
silently drops the edit), and that the snapshot lands **on the brain and not in
the prompt**: it is read through ``read_screen``, and an edit against a workspace
the admin moved since is refused rather than applied to the wrong block.

Run: ``cd demos && uv run pytest tests/test_forge_e2e.py``
"""

from __future__ import annotations

from typing import Any

from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, call, reply, reply_and_call

from ._harness import check_greeting, check_turn, check_voice_pair, demo

discover()

VOICE = "omnivoice/gauri"
LANGUAGE = "en"

PAYLOAD: dict[str, Any] = {"admin": {"name": "Nadia"}}

#: A snapshot of the shape ``store.tsx``'s ``snapshot()`` sends.
WORKSPACE: dict[str, Any] = {
    "view": "editor",
    "panel": "blocks",
    "active": {
        "id": "guest-wifi",
        "name": "Guest Wi-Fi",
        "status": "draft",
        "states": [
            {"id": "s1", "kind": "form", "label": "Request details"},
            {"id": "s2", "kind": "end", "label": "Done"},
        ],
    },
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


async def test_the_workspace_is_read_on_request_and_never_dumped() -> None:
    """``state_sync`` takes no floor — and, since the workspace moved out of the
    context, it puts nothing there either.

    This used to append the whole workspace on every change, prefixed
    *authoritative*, so a session that edits twenty blocks ended with twenty
    near-identical workspaces in front of the model. Now the snapshot stops at the
    brain and ``read_screen`` is the only way to it — including the block ids,
    which are what every edit has to name."""
    llm = ScriptedGemini(
        {
            "What's on screen?": [
                reply_and_call("Let me look.", "read_screen"),
                reply("Guest Wi-Fi is open — a form block and an end."),
            ],
            "Thanks.": reply("Any time."),
        }
    )
    async with demo("forge", llm) as rig:
        await rig.driver.start_session(init=PAYLOAD)
        before = len(rig.driver.ui_commands)

        # The first sync is the studio as it loaded; the second is the admin.
        await rig.driver.send_client_message("state_sync", {"workspace": {"view": "list"}})
        await rig.driver.send_client_message("state_sync", {"workspace": WORKSPACE})

        turn = await rig.driver.user_says("What's on screen?")
        check_turn(rig, turn, units=2)
        assert len(rig.driver.ui_commands) == before, "state_sync or read_screen drew"

        # One more turn, so the turn above's tool results are in a request.
        await rig.driver.user_says("Thanks.")

    results = _tool_results(llm)
    assert "s1" in results, "read_screen did not serve the block ids"
    context = _user_text([c for cs in llm.captured_contents for c in cs])
    assert "just changed the screen" in context
    assert "read_screen" in context
    assert "CURRENT WORKSPACE STATE" not in context, "the workspace dump is back"
    assert "Request details" not in context, "the workspace reached the context anyway"


async def test_an_edit_against_a_workspace_the_admin_moved_is_refused_until_it_is_read() -> None:
    """The version gate, which is what makes read-don't-remember enforceable.

    Forge is where this matters most: every edit names a block by an id Ada read
    off the screen, and the admin is editing the same canvas with their own hands.
    An ``add_state`` after ``s1`` issued against a workspace two edits old rewires
    whatever now sits at ``s1``. So it refuses, and the refusal is retriable: read,
    then act. The scripted model here does exactly the wrong thing first."""
    edit: dict[str, Any] = {
        "after": "s1",
        "kind": "approval",
        "label": "Manager approval",
        "approver": "Reporting manager",
    }
    llm = ScriptedGemini(
        {
            "Add a manager approval after the form.": [
                call("add_state", action=edit),  # stale — the admin has moved it
                call("read_screen"),
                reply_and_call("Adding it.", "add_state", action=edit),
                reply("It's in."),
            ],
            "Thanks.": reply("Any time."),
        }
    )
    async with demo("forge", llm) as rig:
        await rig.driver.start_session(init=PAYLOAD)
        await rig.driver.send_client_message("state_sync", {"workspace": {"view": "list"}})
        await rig.driver.send_client_message("state_sync", {"workspace": WORKSPACE})

        await rig.driver.user_says("Add a manager approval after the form.")
        # Exactly one block was added: the stale call rewired nothing.
        assert rig.actions() == ["add_state"], rig.actions()

        # One more turn, so the turn above's hops are in the context being asserted.
        await rig.driver.user_says("Thanks.")

    assert "the screen moved since you last read it" in _tool_results(llm)


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


def _user_text(contents: list[Any]) -> str:
    return "".join(
        p.text or "" for c in contents if c.role == "user" for p in (c.parts or []) if p.text
    )
