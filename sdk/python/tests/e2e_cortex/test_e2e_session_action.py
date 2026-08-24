"""Session-scoped actions reach the pygato leg over the wire.

An action carries no audio, so it needs no floor: the Brain dispatches one from
anywhere — ``on_session_start`` before a word has been said, or from inside a
turn — and both ride RTVI's own ``ui-command``, naming the action and nesting its
fields under ``payload``. Nothing comes back: an answer is an ordinary
``client-message`` the app sends whenever it likes, and it lands at ``on_rtvi``.
"""

from __future__ import annotations

import asyncio
import contextlib

from pydantic import BaseModel, Field

from tests.e2e_cortex.conftest import connect_pygato
from tests.fakes.cortex import FakeCortex
from voqalize.sdk import Action, Brain
from voqalize.sdk.brain import brain_factory
from voqalize.sdk.outbound import CortexAgent
from voqalize.sdk.wire import (
    RTVIFrame,
    RTVIType,
    SessionStartFrame,
    UserMessageFrame,
)


class Row(BaseModel):
    label: str = ""
    from_: str = Field(default="", alias="from")


class RenderInit(Action, name="render_init"):
    address: str
    rows: list[Row] = []


class RenderTurn(Action, name="render_turn"):
    text: str


class ActionBrain(Brain):
    """Dispatches one floor-free action at session start, then one per user turn."""

    async def on_session_start(self, session) -> None:
        session.dispatch(RenderInit(address="Home", rows=[Row(label="l", **{"from": "BLR"})]))

    async def on_user_message(self, session, msg):
        session.dispatch(RenderTurn(text=msg.text))


async def test_session_action_round_trip() -> None:
    """Both call sites reach the wire, in the same envelope.

    The nested aliased model is the load-bearing half: ``from_`` is the Python
    spelling and ``from`` is the app's, at every depth — an app handler is
    written against the second and never sees the first.
    """
    async with FakeCortex() as cortex:
        agent = CortexAgent(
            factory=brain_factory(ActionBrain),
            api_key="welcome",
            version="1.0.0",
            cortex_url=cortex.agent_url("welcome"),
        )
        run_task = asyncio.create_task(agent.run())

        client = await connect_pygato(cortex, "s1")
        try:
            # Open the session — on_session_start dispatches before any turn exists.
            await client.send(SessionStartFrame(turn_id=1, session_id="s1"))
            # A user turn dispatches the second one.
            await client.send(UserMessageFrame(turn_id=2, text="hi there"))

            cmds = {c["command"]: c for c in await client.collect_ui_commands(2, timeout=5.0)}
        finally:
            await client.close()
            run_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await run_task

    assert cmds["render_init"] == {
        "command": "render_init",
        "payload": {"address": "Home", "rows": [{"label": "l", "from": "BLR"}]},
    }
    assert cmds["render_turn"] == {
        "command": "render_turn",
        "payload": {"text": "hi there"},
    }


async def test_the_app_answers_on_the_ordinary_client_message_lane() -> None:
    """An action asks; the app answers when it likes, on the lane every other tap
    uses. The dispatch that asked is long over, so the correlation is whatever the
    app puts in the reply — here the command name it is answering."""
    answers: list[dict] = []

    class AskingBrain(Brain):
        async def on_session_start(self, session) -> None:
            session.dispatch(RenderInit(address="Home"))

        async def on_rtvi(self, session, msg) -> None:
            if msg.type is RTVIType.CLIENT_MESSAGE and isinstance(msg.data, dict):
                answers.append(msg.data)

    async with FakeCortex() as cortex:
        agent = CortexAgent(
            factory=brain_factory(AskingBrain),
            api_key="cb",
            version="1.0.0",
            cortex_url=cortex.agent_url("cb"),
        )
        run_task = asyncio.create_task(agent.run())
        client = await connect_pygato(cortex, "s-cb", "cb")
        try:
            await client.send(SessionStartFrame(turn_id=1, session_id="s-cb"))
            (cmd,) = await client.collect_ui_commands(1, timeout=5.0)
            await client.send(
                RTVIFrame(
                    type=RTVIType.CLIENT_MESSAGE,
                    data={"t": "answered", "d": {"command": cmd["command"], "picked": "first"}},
                )
            )
            for _ in range(50):
                if answers:
                    break
                await asyncio.sleep(0.05)
        finally:
            await client.close()
            run_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await run_task

    assert answers == [{"t": "answered", "d": {"command": "render_init", "picked": "first"}}]
