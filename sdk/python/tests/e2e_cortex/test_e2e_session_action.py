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

from tests.e2e_cortex.conftest import connect_pygato
from tests.fakes.cortex import FakeCortex
from voqalize.sdk import Brain, make_agent
from voqalize.sdk.wire import VqlStartFrame, VqlUserTextFrame


class ActionBrain(Brain):
    """Fires one out-of-interaction action at session start, then one
    interaction-scoped action per user turn."""

    async def on_session_start(self, session, start) -> None:
        session.action("render_init", {"address": "Home"})

    async def on_interaction(self, interaction) -> None:
        interaction.action("render_turn", {"text": interaction.transcript})


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
