"""Session-scoped actions reach the pygato leg over the wire.

An action carries no audio, so it needs no floor: the Brain dispatches one from
anywhere — ``on_session_start`` before a word has been said, or from inside a
turn — and both serialize to the same ``ui_command`` ``ServerMessageFrame``.
``action_id`` is minted session-monotonically across every call site, and it is
what the browser's answer is correlated by.
"""

from __future__ import annotations

import asyncio
import contextlib

from pydantic import BaseModel, Field

from tests.e2e_cortex.conftest import connect_pygato
from tests.fakes.cortex import FakeCortex
from voqalize.sdk import Action, Brain, Chunk, Result, SpeechEnd, SpeechStart
from voqalize.sdk.brain import brain_factory
from voqalize.sdk.outbound import CortexAgent
from voqalize.sdk.wire import (
    ClientMessageFrame,
    LLMTextFrame,
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
    """Both call sites reach the wire, in the same envelope, with monotonic ids.

    The nested aliased model is the load-bearing half: ``from_`` is the Python
    spelling and ``from`` is the browser's, at every depth — a browser handler is
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
            await client.send(SessionStartFrame(session_id="s1", agent_id="welcome", payload={}))
            # A user turn dispatches the second one.
            await client.send(UserMessageFrame(text="hi there"), epoch=1)

            cmds = {c["action"]: c for c in await client.collect_ui_commands(2, timeout=5.0)}
        finally:
            await client.close()
            run_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await run_task

    assert cmds["render_init"] == {
        "type": "ui_command",
        "action": "render_init",
        "action_id": 1,
        "address": "Home",
        "rows": [{"label": "l", "from": "BLR"}],
    }
    assert cmds["render_turn"] == {
        "type": "ui_command",
        "action": "render_turn",
        "action_id": 2,
        "text": "hi there",
    }


async def test_action_result_reaches_on_result() -> None:
    """The browser's answer rides the ordinary client-message lane and is matched
    back to the dispatching call by ``action_id`` — session-scoped, so it settles
    long after the turn that fired it would have ended."""
    seen: list[tuple[int, str]] = []

    class CallbackBrain(Brain):
        async def on_session_start(self, session) -> None:
            session.dispatch(
                RenderInit(
                    address="Home",
                    on_result=lambda result: seen.append((result.action_id, result.status)),
                )
            )

    async with FakeCortex() as cortex:
        agent = CortexAgent(
            factory=brain_factory(CallbackBrain),
            api_key="cb",
            version="1.0.0",
            cortex_url=cortex.agent_url("cb"),
        )
        run_task = asyncio.create_task(agent.run())
        client = await connect_pygato(cortex, "s-cb", "cb")
        try:
            await client.send(SessionStartFrame(session_id="s-cb", agent_id="cb", payload={}))
            (cmd,) = await client.collect_ui_commands(1, timeout=5.0)
            await client.send(
                ClientMessageFrame(
                    msg_id="m1",
                    type="action_result",
                    data={"action_id": cmd["action_id"], "status": "ok"},
                ),
                epoch=1,
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

    assert seen == [(1, "ok")]


async def test_awaiting_a_result_resolves_the_handle() -> None:
    """``dispatch`` never blocks; the handle it returns is how a brain that *does*
    need the answer waits for it — the same settle, surfaced as a future. The turn
    is a generator, so awaiting inside it simply stops producing speech until the
    browser answers."""
    resolved: list[Result] = []

    class AwaitingBrain(Brain):
        async def on_user_message(self, session, msg):
            result = await session.dispatch(RenderInit(address="Home")).result
            resolved.append(result)
            yield SpeechStart()
            yield Chunk(f"got {result.status}")
            yield SpeechEnd()

    async with FakeCortex() as cortex:
        agent = CortexAgent(
            factory=brain_factory(AwaitingBrain),
            api_key="aw",
            version="1.0.0",
            cortex_url=cortex.agent_url("aw"),
        )
        run_task = asyncio.create_task(agent.run())
        client = await connect_pygato(cortex, "s-aw", "aw")
        try:
            await client.send(SessionStartFrame(session_id="s-aw", agent_id="aw", payload={}))
            await client.send(UserMessageFrame(text="go"), epoch=1)
            (cmd,) = await client.collect_ui_commands(1, timeout=5.0)
            await client.send(
                ClientMessageFrame(
                    msg_id="m1",
                    type="action_result",
                    data={"action_id": cmd["action_id"], "status": "ok", "result": {"ok": True}},
                ),
                epoch=1,
            )
            frames, _ = await client.collect_until(
                lambda fr, _ac: any(isinstance(f, LLMTextFrame) and "got ok" in f.text for f in fr),
                timeout=5.0,
            )
        finally:
            await client.close()
            run_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await run_task

    assert [(r.action_id, r.status, r.data) for r in resolved] == [(1, "ok", {"ok": True})]
    assert any(isinstance(f, LLMTextFrame) and "got ok" in f.text for f in frames)
