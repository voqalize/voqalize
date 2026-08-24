"""Drop the pygato leg with code 4001 mid-session; the pygato-side Wire
reconnects; it does **not** resend a second SessionStartFrame. (Resending would
trample the agent's session state — agents own their session lifecycle. The
agent-side session persists across a pygato-leg reconnect.)
"""

from __future__ import annotations

import asyncio
import contextlib

from tests.e2e_cortex.conftest import connect_pygato, wait_until
from tests.fakes.cortex import FakeCortex
from voqalize.sdk.engine import Emitter, SessionAdapter
from voqalize.sdk.outbound import CortexAgent
from voqalize.sdk.wire import Frame, ResponseFrame, SessionStartFrame


class StartCounter(SessionAdapter):
    starts: list[str] = []

    def __init__(self, emitter: Emitter) -> None:
        self.emitter = emitter

    async def handle_frame(self, frame: Frame) -> None:
        if isinstance(frame, SessionStartFrame):
            StartCounter.starts.append(frame.session_id or "?")

    def settle_response(self, frame: ResponseFrame) -> None:
        pass

    async def close(self) -> None:
        pass


async def test_pygato_leg_reconnect_does_not_resend_start() -> None:
    StartCounter.starts = []

    async with FakeCortex() as cortex:
        agent = CortexAgent(
            api_key="welcome",
            version="1.0.0",
            cortex_url=cortex.agent_url("welcome"),
            factory=lambda emitter: StartCounter(emitter),
        )
        run_task = asyncio.create_task(agent.run())

        client = await connect_pygato(cortex, "s1")
        try:
            await client.send(SessionStartFrame(turn_id=1, session_id="s1", init={"k": "v"}))
            await wait_until(lambda: len(StartCounter.starts) >= 1, timeout=3.0)
            assert len(StartCounter.starts) == 1

            await cortex.kill_pygato_leg("s1", code=4001)

            # Give the pygato Wire time to reconnect. It does *not* resend
            # SessionStartFrame after the reconnect — agents own session lifecycle.
            await asyncio.sleep(1.0)
            assert len(StartCounter.starts) == 1, (
                f"unexpected second SessionStartFrame: {StartCounter.starts}"
            )
        finally:
            await client.close()
            run_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await run_task
