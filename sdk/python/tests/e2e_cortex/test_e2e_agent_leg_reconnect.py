"""The agent SDK survives a transient close on the `/agent` leg. The wire
reconnects with backoff; CortexAgent.run() does not raise.
"""

from __future__ import annotations

import asyncio
import contextlib

from tests.e2e_cortex.conftest import connect_pygato, wait_until
from tests.fakes.cortex import FakeCortex
from voqalize.sdk.engine import Emitter, SessionAdapter
from voqalize.sdk.outbound import CortexAgent
from voqalize.sdk.wire import Frame, VqlStartFrame


class StartRecorder(SessionAdapter):
    starts: int = 0

    def __init__(self, emitter: Emitter) -> None:
        self.emitter = emitter

    async def handle_frame(self, frame: Frame) -> None:
        if isinstance(frame, VqlStartFrame):
            StartRecorder.starts += 1

    async def close(self) -> None:
        pass


async def test_agent_leg_transient_close_does_not_kill_run() -> None:
    StartRecorder.starts = 0
    async with FakeCortex() as cortex:
        agent = CortexAgent(
            api_key="welcome",
            version="1.0.0",
            cortex_url=cortex.agent_url("welcome"),
            factory=lambda emitter: StartRecorder(emitter),
        )
        run_task = asyncio.create_task(agent.run())

        client = await connect_pygato(cortex, "s1")
        try:
            await client.send(VqlStartFrame(session_id="s1", agent_id="welcome", payload={}))
            await wait_until(lambda: StartRecorder.starts >= 1, timeout=3.0)

            await cortex.kill_agent_leg("welcome", code=4001)

            # The run task must not raise — wire reconnects, agent stays alive.
            await asyncio.sleep(0.3)
            assert not run_task.done(), f"agent.run() exited unexpectedly: {run_task.exception()!r}"
        finally:
            await client.close()
            run_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await run_task
