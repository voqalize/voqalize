"""Session-scoped actions reach the pygato leg over the wire.

``action`` is floor-free and session-scoped: the Brain may fire one outside any
interaction (``session.action``, e.g. a render from ``on_session_start``) as well
as within one (``interaction.action``). Both serialize to the same ``ui_command``
``RTVIServerMessageFrame`` and must arrive at the pygato-side client, with
session-monotonic ``action_id``s minted across both call sites.

``RTVIServerMessageFrame`` is encode-only, so the client reads the raw envelope
(see ``conftest.parse_ui_command``) rather than round-tripping through the
serializer.
"""

from __future__ import annotations

import asyncio
import contextlib

from pydantic import BaseModel, Field

from tests.e2e_cortex.conftest import connect_pygato
from tests.fakes.cortex import FakeCortex
from voqalize.sdk import Action, Brain, make_agent
from voqalize.sdk.wire import (
    VqlRTVIClientMessageFrame,
    VqlStartFrame,
    VqlUserTextFrame,
)


class ActionBrain(Brain):
    """Fires one out-of-interaction action at session start, then one
    interaction-scoped action per user turn."""

    async def on_session_start(self, session, start) -> None:
        session.action("render_init", {"address": "Home"})

    async def on_interaction(self, interaction) -> None:
        interaction.action("render_turn", {"text": interaction.transcript})


class Row(BaseModel):
    label: str = ""
    from_: str = Field(default="", alias="from")


class RenderInit(Action, name="render_init"):
    address: str
    rows: list[Row] = []


class TypedActionBrain(Brain):
    """Fires the SAME two commands as :class:`ActionBrain`, declared instead of
    hand-assembled — at both call sites (session- and interaction-scoped)."""

    async def on_session_start(self, session, start) -> None:
        session.action(RenderInit(address="Home", rows=[Row(label="l", **{"from": "BLR"})]))

    async def on_interaction(self, interaction) -> None:
        interaction.action(RenderTurn(text=interaction.transcript))


class RenderTurn(Action, name="render_turn"):
    text: str


async def _drive(brain: type[Brain], cortex: FakeCortex, key: str) -> list[dict]:
    """Run one brain through a full session and return the ui_commands it emitted."""
    agent = make_agent(brain, api_key=key, version="1.0.0", cortex_url=cortex.agent_url(key))
    run_task = asyncio.create_task(agent.run())
    client = await connect_pygato(cortex, f"s-{key}", key)
    try:
        await client.send(VqlStartFrame(session_id=f"s-{key}", agent_id=key, payload={}))
        await client.send(VqlUserTextFrame(interaction_id=1, text="hi there"))
        return await client.collect_ui_commands(2, timeout=5.0)
    finally:
        await client.close()
        run_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await run_task


async def test_session_action_round_trip() -> None:
    async with FakeCortex() as cortex:
        agent = make_agent(
            ActionBrain,
            api_key="welcome",
            version="1.0.0",
            cortex_url=cortex.agent_url("welcome"),
        )
        run_task = asyncio.create_task(agent.run())

        client = await connect_pygato(cortex, "s1")
        try:
            # Open the session — on_session_start fires a session.action before
            # any interaction exists.
            await client.send(VqlStartFrame(session_id="s1", agent_id="welcome", payload={}))
            # A user turn fires an interaction-scoped action.
            await client.send(VqlUserTextFrame(interaction_id=1, text="hi there"))

            cmds_list = await client.collect_ui_commands(2, timeout=5.0)
            cmds = {c["action"]: c for c in cmds_list}
            assert cmds["render_init"]["address"] == "Home"
            assert cmds["render_turn"]["text"] == "hi there"
            # action_id is session-monotonic across both call sites.
            ids = sorted(c["action_id"] for c in cmds.values())
            assert ids == [1, 2], ids
        finally:
            await client.close()
            run_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await run_task


async def test_typed_actions_ride_the_same_wire_envelope() -> None:
    """A declared :class:`Action` produces the byte-identical envelope the legacy
    ``action(name, dict)`` form produces — at both call sites, over the real socket.

    This is the compatibility guarantee the whole typed-actions surface rests on: an
    existing browser handler cannot tell which form the brain used, so a brain may be
    migrated command-by-command with no coordinated UI release.
    """
    async with FakeCortex() as cortex:
        legacy = await _drive(ActionBrain, cortex, "legacy")
        typed = await _drive(TypedActionBrain, cortex, "typed")

    by_action = ({c["action"]: c for c in legacy}, {c["action"]: c for c in typed})
    legacy_cmds, typed_cmds = by_action

    # The interaction-scoped one is a pure like-for-like: same name, same single arg.
    assert typed_cmds["render_turn"] == legacy_cmds["render_turn"]
    assert typed_cmds["render_turn"] == {
        "type": "ui_command",
        "action": "render_turn",
        "action_id": 2,
        "text": "hi there",
    }

    # The session-scoped one adds a nested aliased model — the envelope keys and the
    # arg spread are unchanged; `from_` goes out as the browser's `from`.
    assert typed_cmds["render_init"] == {
        "type": "ui_command",
        "action": "render_init",
        "action_id": 1,
        "address": "Home",
        "rows": [{"label": "l", "from": "BLR"}],
    }
    # Envelope keys and action_ids are identical to the legacy run, field-for-field.
    assert set(typed_cmds) == set(legacy_cmds)
    for name, cmd in typed_cmds.items():
        assert cmd["type"] == legacy_cmds[name]["type"] == "ui_command"
        assert cmd["action_id"] == legacy_cmds[name]["action_id"]


async def test_typed_action_callback_still_fires() -> None:
    """``callback=`` is orthogonal to which calling form was used — the outcome is
    matched by the same session-scoped ``action_id`` the typed call returned."""
    seen: list[tuple[int, str]] = []

    class CallbackBrain(Brain):
        async def on_session_start(self, session, start) -> None:
            session.action(
                RenderInit(address="Home"),
                callback=lambda outcome: seen.append((outcome.action_id, outcome.status)),
            )

    async with FakeCortex() as cortex:
        agent = make_agent(
            CallbackBrain, api_key="cb", version="1.0.0", cortex_url=cortex.agent_url("cb")
        )
        run_task = asyncio.create_task(agent.run())
        client = await connect_pygato(cortex, "s-cb", "cb")
        try:
            await client.send(VqlStartFrame(session_id="s-cb", agent_id="cb", payload={}))
            (cmd,) = await client.collect_ui_commands(1, timeout=5.0)
            # The browser's echo, on the same frame any client message rides.
            await client.send(
                VqlRTVIClientMessageFrame(
                    interaction_id=1,
                    msg_id="m1",
                    type="action_outcome",
                    data={"action_id": cmd["action_id"], "status": "done"},
                )
            )
            for _ in range(50):
                if seen:
                    break
                await asyncio.sleep(0.05)
        finally:
            await client.close()
            run_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await run_task

    assert seen == [(1, "done")]
