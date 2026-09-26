"""The Forge workflow-studio demo, end to end over the wire — no network, no key.

The real ``ForgeBrain`` — the shipping ``demos/forge/backend/brain.py``, its real
prompt, its real tools — hosted on a real ``brain_server`` socket and
driven by the conformance ``VoqalizeDriver``, with only the *model* scripted. See
``tests/_harness.py`` for what every demo's e2e proves.

Worth pinning here, in order. A tool call has to reach the studio with its
arguments intact — each tool's parameter *is* the ``Action`` dispatched, so a
rename in either repo silently drops the edit. What the admin does by hand has to
reach the context as the *act* and nowhere near it as a value. And forge's own
case: what the studio's interpreter works out for itself — a test run's
verdicts — has to come back **carrying its result**, because Ada has no other way
to learn it.

Run: ``cd demos && uv run pytest tests/test_forge_e2e.py``
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any

from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, reply, reply_and_call

from voqalize.sdk.gemini import _needs_result_now

from ._harness import check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.forge.brain import ForgeBrain  # noqa: E402

VOICE = "omnivoice/gauri"
LANGUAGE = "en"

#: The catalog as ``data.ts``'s ``studioSeed()`` hands it over — the studio
#: already has it, so it rides ``init`` rather than being pushed back.
CATALOG: list[dict[str, Any]] = [
    {
        "id": "guest-wifi",
        "name": "Guest Wi-Fi",
        "category": "ITSM",
        "status": "draft",
        "version": 1,
        "trigger": "A sponsor requests guest access",
        "the request context": [],
        "the blocks": [
            {"id": "s1", "kind": "form", "label": "Request details", "next": "s2"},
            {"id": "s2", "kind": "end", "label": "Done", "outcome": "Complete"},
        ],
        "the tests": [
            {"name": "Sponsor submits", "given": "s1", "event": "submit", "expect": "s2"},
        ],
        "the open gaps": [],
    },
]


def _payload() -> dict[str, Any]:
    """A fresh catalog per test — the brain patches the workflows it is handed."""
    return {"admin": {"name": "Nadia"}, "workflows": deepcopy(CATALOG)}


def _llm() -> ScriptedGemini:
    return ScriptedGemini(
        {
            # One tool, one model, one parameter — the argument is the
            # ``Action`` the studio applies, nested under the name the method
            # gives it (``action``), just as the model would send it. Neither edit
            # is marked: the line goes with the call and the turn ends with it.
            "Open the guest wifi workflow.": reply_and_call(
                "Opening Guest Wi-Fi.", "open_workflow", action={"id": "guest-wifi"}
            ),
            "Add a manager approval after the form.": reply_and_call(
                "Adding a manager approval.",
                "add_state",
                action={
                    "after": "s1",
                    "kind": "approval",
                    "label": "Manager approval",
                    "approver": "Reporting manager",
                    "sla_hours": 24,
                },
            ),
            "What's on screen?": reply("The guest Wi-Fi flow."),
        }
    )


async def test_greeting_and_voice_reach_the_wire() -> None:
    """Ada opens with a fixed line — no model call on the start path — and her
    declared voice lands on **both** legs before that audio."""
    async with demo("forge", _llm()) as rig:
        greeting = await rig.driver.start_session(init=_payload())
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text.startswith("Hi there — Ada here.")
        check_voice_pair(rig, voice=VOICE, language=LANGUAGE)


async def test_edits_reach_the_studio_with_their_arguments_intact() -> None:
    """Forge dispatches each tool's own parameter **verbatim**: the pydantic model
    the model filled in *is* the ``ui-command`` payload the studio store reads.

    That is the whole contract, and it is one rename away from breaking silently —
    the model still calls the tool, Ada still says "added", and the block never
    appears. So assert the payload key by key rather than just the action. The one
    field the model did not fill is ``id``: Ada mints it before dispatch, because a
    block the studio named is a block only the studio can name again.

    Each turn is one unit: the short line said with the call. Nothing an edit
    returns changes what the admin hears, so the model is not asked again."""
    async with demo("forge", _llm()) as rig:
        await rig.driver.start_session(init=_payload())

        t1 = await rig.driver.user_says("Open the guest wifi workflow.")
        check_turn(rig, t1, units=1)
        t2 = await rig.driver.user_says("Add a manager approval after the form.")
        check_turn(rig, t2, units=1)

        assert rig.actions() == ["open_workflow", "add_state"], rig.actions()
        assert rig.command("open_workflow")["id"] == "guest-wifi"

        added = rig.command("add_state")
        assert added["after"] == "s1"
        assert added["kind"] == "approval"
        assert added["label"] == "Manager approval"
        assert added["approver"] == "Reporting manager"
        assert added["sla_hours"] == 24
        assert added["id"].startswith("s_a"), added["id"]


async def test_a_gesture_is_named_in_the_context_and_the_workflow_is_read_instead() -> None:
    """What the admin did reaches the context; what the screen says does not.

    This used to append the whole workspace on every change, prefixed
    *authoritative*, so a session that edits twenty blocks ended with twenty
    near-identical workspaces in front of the model. Now the gesture arrives typed,
    the context gets one line naming it, and ``read_screen`` is the only way to the
    blocks — which are what every edit has to name."""
    llm = ScriptedGemini(
        {
            "What's on screen?": [
                reply_and_call("Let me look.", "read_screen"),
                reply("Guest Wi-Fi is open — a form block and an end."),
            ],
        }
    )
    async with demo("forge", llm) as rig:
        await rig.driver.start_session(init=_payload())
        before = len(rig.driver.ui_commands)

        await rig.driver.send_ui_event("workflow_opened", {"id": "guest-wifi"})
        await rig.driver.send_ui_event("block_focused", {"id": "s1"})
        await asyncio.sleep(0.1)

        # Two units: `read_screen` is marked, so the model is asked again with
        # the screen and answers from it in the same turn. That second request
        # carries the result, so no flush turn is needed to assert on it.
        turn = await rig.driver.user_says("What's on screen?")
        check_turn(rig, turn, units=2)
        assert len(rig.driver.ui_commands) == before, "a gesture or read_screen drew"

    results = _tool_results(llm)
    assert "s1" in results, "read_screen did not serve the block ids"
    assert "Request details" in results

    context = _user_text([c for cs in llm.captured_contents for c in cs])
    assert "The admin opened a workflow themselves." in context
    assert "The admin selected a block themselves." in context
    assert "read_screen" in context
    assert "Request details" not in context, "the workflow reached the context anyway"
    assert "guest-wifi" not in context, "the gesture carried its value"


async def test_the_studio_s_own_answer_carries_its_result() -> None:
    """A test run is not somebody's gesture, and it is the one thing that has to
    arrive valued.

    Nobody decided the verdicts — the studio's interpreter computed them, on its
    own clock, and the browser is the only place they exist. So unlike a gesture
    this line carries what it found. It still bumps the screen version, so the next
    edit reads before it acts."""
    llm = ScriptedGemini({"Thanks.": reply("Any time."), "And?": reply("All good.")})
    async with demo("forge", llm) as rig:
        await rig.driver.start_session(init=_payload())
        await rig.driver.send_ui_event("workflow_opened", {"id": "guest-wifi"})
        await rig.driver.send_ui_event(
            "tests_finished",
            {
                "tests": [
                    {"name": "Sponsor submits", "passed": False, "rested_at": "s1"},
                ]
            },
        )
        await asyncio.sleep(0.1)
        await rig.driver.user_says("Thanks.")
        await rig.driver.user_says("And?")

    context = _user_text([c for cs in llm.captured_contents for c in cs])
    assert "The test run finished: 0 of 1 passing." in context
    assert "'Sponsor submits' rested at s1." in context


async def test_an_edit_against_a_workflow_the_admin_moved_is_refused_until_it_is_read() -> None:
    """The version gate, which is what makes read-don't-remember enforceable.

    Forge is where this matters most: every edit names a block by an id Ada read
    off the screen, and the admin is editing the same canvas with their own hands.
    An ``add_state`` after ``s1`` issued against a workflow two edits old rewires
    whatever now sits at ``s1``. So it refuses, and the refusal is retriable: read,
    then act. The scripted model here does exactly the wrong thing first.

    ``add_state`` is not marked, so the refusal reaches the model with the admin's
    next words, not in the turn that made the edit. The retry is then the shape
    the prompt asks for: a short line with ``read_screen``, which is marked, and
    the edit in the reply after it answers."""
    edit: dict[str, Any] = {
        "after": "s1",
        "kind": "approval",
        "label": "Manager approval",
        "approver": "Reporting manager",
    }
    llm = ScriptedGemini(
        {
            # Stale — the admin has moved the screen since anything was read.
            "Add a manager approval after the form.": reply_and_call(
                "Adding a manager approval.", "add_state", action=edit
            ),
            "Is it there?": [
                reply_and_call("Let me look.", "read_screen"),
                reply_and_call("Adding it now.", "add_state", action=edit),
            ],
        }
    )
    async with demo("forge", llm) as rig:
        await rig.driver.start_session(init=_payload())
        await rig.driver.send_ui_event("workflow_opened", {"id": "guest-wifi"})
        await asyncio.sleep(0.1)

        await rig.driver.user_says("Add a manager approval after the form.")
        assert rig.actions() == [], "the stale edit rewired the studio"

        retry = await rig.driver.user_says("Is it there?")
        check_turn(rig, retry, units=2)
        # Exactly one block was added: the stale call rewired nothing.
        assert rig.actions() == ["add_state"], rig.actions()

    assert "not applied: the screen moved since you last read it" in _tool_results(llm)


def _tool_results(llm: ScriptedGemini) -> str:
    """Every tool result any request carried. An unmarked tool's result is first
    carried by the request that follows its turn; a marked one's, by the next
    request of the same turn."""
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


def test_only_the_screen_read_holds_the_turn() -> None:
    """The mark, pinned tool by tool, so a change to it is a decision someone makes.

    Held: ``read_screen``, the one tool whose answer the model needs before it can
    reply — the block ids every edit names. Every edit applies exactly what the
    model specified, and what the studio computes for itself arrives later as an
    event, so those tools say their line with the call and are read with the
    admin's next words."""
    brain = ForgeBrain(client=ScriptedGemini({}))  # pyright: ignore[reportArgumentType]
    held = {tool.__name__ for tool in brain.tools if _needs_result_now(tool)}
    assert held == {"read_screen"}
