"""Two UserMessageFrames sent back-to-back arrive at the session adapter in
order, and the second is not dispatched until the first ``handle_frame``
completes. This is the engine's per-session serial guarantee: the feeder awaits
each ``handle_frame`` before pulling the next inbound frame. Exercised
end-to-end through CortexAgent + MultiplexedWire."""

from __future__ import annotations

import asyncio
import contextlib

from tests.cortex.conftest import wait_for
from tests.fakes.cortex import FakeCortex
from voqalize.sdk.engine import Emitter, Envelope, SessionAdapter
from voqalize.sdk.outbound import CortexAgent
from voqalize.sdk.wire import (
    SessionStartFrame,
    UserMessageFrame,
    Wire,
    WireConfig,
    WireSerializer,
)


async def test_two_data_frames_serial_dispatch() -> None:
    serializer = WireSerializer()
    arrivals: list[str] = []
    can_finish = asyncio.Event()

    class Slow(SessionAdapter):
        def __init__(self, emitter: Emitter) -> None:
            self.emitter = emitter

        async def handle_frame(self, env: Envelope) -> None:

            frame = env.frame
            if isinstance(frame, UserMessageFrame):
                arrivals.append(f"start:{frame.text}")
                if frame.text == "first":
                    await can_finish.wait()
                arrivals.append(f"end:{frame.text}")

        async def close(self) -> None:
            pass

    async with FakeCortex() as cortex:
        agent = CortexAgent(
            api_key="welcome",
            version="1.0.0",
            cortex_url=cortex.agent_url("welcome"),
            factory=lambda emitter: Slow(emitter),
        )
        run_task = asyncio.create_task(agent.run())

        pygato_wire = Wire(WireConfig(url=cortex.pygato_url("s1", "welcome")))
        await pygato_wire.start()

        # Open the session with SessionStartFrame.
        await pygato_wire.send(
            await serializer.serialize(SessionStartFrame(session_id="s1", init={})),
        )

        # Two data frames back-to-back.
        await pygato_wire.send(
            await serializer.serialize(UserMessageFrame(text="first"), epoch=1),
        )
        await pygato_wire.send(
            await serializer.serialize(UserMessageFrame(text="second"), epoch=2),
        )

        # First handler invocation starts; second must wait.
        await wait_for(lambda: arrivals == ["start:first"], timeout=3.0)
        await asyncio.sleep(0.1)
        assert arrivals == ["start:first"], arrivals

        # Release first; second must run next, in order.
        can_finish.set()
        await wait_for(
            lambda: arrivals == ["start:first", "end:first", "start:second", "end:second"],
            timeout=3.0,
        )

        await pygato_wire.close()
        run_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await run_task
