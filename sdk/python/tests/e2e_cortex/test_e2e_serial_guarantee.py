"""Burst 10 UserMessageFrames over the wire. The agent's ``handle_frame``
invocations are serialized — the engine feeder awaits each ``handle_frame``
before pulling the next inbound frame, so at most one runs at a time."""

from __future__ import annotations

import asyncio
import contextlib

from tests.e2e_cortex.conftest import connect_pygato, wait_until
from tests.fakes.cortex import FakeCortex
from voqalize.sdk.engine import Emitter, Envelope, SessionAdapter
from voqalize.sdk.outbound import CortexAgent
from voqalize.sdk.wire import SessionStartFrame, UserMessageFrame


class SerialChecker(SessionAdapter):
    timeline: list[tuple[str, int]] = []
    in_flight: int = 0
    max_in_flight: int = 0

    def __init__(self, emitter: Emitter) -> None:
        self.emitter = emitter

    async def handle_frame(self, env: Envelope) -> None:

        frame = env.frame
        if isinstance(frame, UserMessageFrame):
            SerialChecker.in_flight += 1
            SerialChecker.max_in_flight = max(SerialChecker.max_in_flight, SerialChecker.in_flight)
            SerialChecker.timeline.append(("start", env.epoch))
            await asyncio.sleep(0.01)
            SerialChecker.timeline.append(("end", env.epoch))
            SerialChecker.in_flight -= 1

    async def close(self) -> None:
        pass


async def test_serial_dispatch_under_burst() -> None:
    SerialChecker.timeline = []
    SerialChecker.in_flight = 0
    SerialChecker.max_in_flight = 0

    async with FakeCortex() as cortex:
        agent = CortexAgent(
            api_key="welcome",
            version="1.0.0",
            cortex_url=cortex.agent_url("welcome"),
            factory=lambda emitter: SerialChecker(emitter),
        )
        run_task = asyncio.create_task(agent.run())

        client = await connect_pygato(cortex, "s1")
        try:
            await client.send(SessionStartFrame(session_id="s1", init={}))
            for i in range(10):
                await client.send(UserMessageFrame(text=f"msg-{i}"), epoch=i)

            await wait_until(
                lambda: sum(1 for kind, _ in SerialChecker.timeline if kind == "end") == 10,
                timeout=10.0,
            )
            assert SerialChecker.max_in_flight == 1, (
                f"concurrency observed: max_in_flight={SerialChecker.max_in_flight}"
            )
            for i in range(10):
                start_idx = SerialChecker.timeline.index(("start", i))
                end_idx = SerialChecker.timeline.index(("end", i))
                assert end_idx == start_idx + 1, (
                    f"interaction {i} start/end not adjacent: {SerialChecker.timeline}"
                )
        finally:
            await client.close()
            run_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await run_task
