"""Pygato side (Wire client): send a VqlStartFrame carrying session_id,
agent_id, and an init payload.

Agent side: a test SessionAdapter observes the VqlStartFrame verbatim — proving
the session identity and init payload survive the multiplexed wire."""

from __future__ import annotations

import asyncio
import contextlib

from tests.e2e_cortex.conftest import connect_pygato, wait_until
from tests.fakes.cortex import FakeCortex
from voqalize.sdk.engine import Emitter, SessionAdapter
from voqalize.sdk.outbound import CortexAgent
from voqalize.sdk.wire import Frame, VqlStartFrame


class StartCapture(SessionAdapter):
    seen: list[VqlStartFrame] = []

    def __init__(self, emitter: Emitter) -> None:
        self.emitter = emitter

    async def handle_frame(self, frame: Frame) -> None:
        if isinstance(frame, VqlStartFrame):
            StartCapture.seen.append(frame)

    async def close(self) -> None:
        pass


async def test_start_frame_carries_identity_and_payload() -> None:
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
            await client.send(
                VqlStartFrame(session_id="s1", agent_id="welcome", payload={"greeting": "hi"})
            )

            await wait_until(lambda: bool(StartCapture.seen), timeout=3.0)
            vql_start = StartCapture.seen[0]
            assert vql_start.session_id == "s1"
            assert vql_start.agent_id == "welcome"
            assert vql_start.payload == {"greeting": "hi"}
        finally:
            await client.close()
            run_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await run_task
