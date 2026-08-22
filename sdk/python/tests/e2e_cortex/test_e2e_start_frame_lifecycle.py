"""Pygato side (Wire client): send a SessionStartFrame carrying a session_id and
opaque init data.

Agent side: a test SessionAdapter observes the SessionStartFrame verbatim — proving
the session id and its init data survive the multiplexed wire."""

from __future__ import annotations

import asyncio
import contextlib

from tests.e2e_cortex.conftest import connect_pygato, wait_until
from tests.fakes.cortex import FakeCortex
from voqalize.sdk.engine import Emitter, Envelope, SessionAdapter
from voqalize.sdk.outbound import CortexAgent
from voqalize.sdk.wire import SessionStartFrame


class StartCapture(SessionAdapter):
    seen: list[SessionStartFrame] = []

    def __init__(self, emitter: Emitter) -> None:
        self.emitter = emitter

    async def handle_frame(self, env: Envelope) -> None:

        frame = env.frame
        if isinstance(frame, SessionStartFrame):
            StartCapture.seen.append(frame)

    async def close(self) -> None:
        pass


async def test_start_frame_carries_session_id_and_init() -> None:
    StartCapture.seen = []
    async with FakeCortex() as cortex:
        agent = CortexAgent(
            api_key="welcome",
            version="1.0.0",
            cortex_url=cortex.agent_url("welcome"),
            factory=lambda emitter: StartCapture(emitter),
        )
        run_task = asyncio.create_task(agent.run())

        client = await connect_pygato(cortex, "s1")
        try:
            await client.send(SessionStartFrame(session_id="s1", init={"greeting": "hi"}))

            await wait_until(lambda: bool(StartCapture.seen), timeout=3.0)
            vql_start = StartCapture.seen[0]
            assert vql_start.session_id == "s1"
            assert vql_start.init == {"greeting": "hi"}
        finally:
            await client.close()
            run_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await run_task
