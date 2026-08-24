"""An InterruptionFrame cancels the Brain's in-flight turn.

The Brain adapter SPAWNS the turn so the feeder stays free; a barge-in
``InterruptionFrame`` (priority lane) then raises the watermark over the turn
and cancels its generator. Verify that contract round-trips through CortexAgent
+ the multiplexed wire."""

from __future__ import annotations

import asyncio
import contextlib

from tests.cortex.conftest import wait_for
from tests.fakes.cortex import FakeCortex
from voqalize.sdk import Brain
from voqalize.sdk.brain import brain_factory
from voqalize.sdk.outbound import CortexAgent
from voqalize.sdk.wire import (
    InterruptionFrame,
    SessionStartFrame,
    UserMessageFrame,
    Wire,
    WireConfig,
    WireSerializer,
)


async def test_interruption_cancels_in_flight_turn() -> None:
    serializer = WireSerializer()
    timeline: list[str] = []
    started = asyncio.Event()

    class Blocking(Brain):
        async def on_user_message(self, session, msg):
            timeline.append(f"start:{msg.text}")
            started.set()
            try:
                await asyncio.Event().wait()  # block forever
            except asyncio.CancelledError:
                timeline.append(f"cancelled:{msg.text}")
                raise
            yield  # unreachable, but this is a speaking callback

    async with FakeCortex() as cortex:
        agent = CortexAgent(
            api_key="welcome",
            version="1.0.0",
            cortex_url=cortex.agent_url("welcome"),
            factory=brain_factory(Blocking),
        )
        run_task = asyncio.create_task(agent.run())

        pygato_wire = Wire(WireConfig(url=cortex.pygato_url("s1", "welcome")))
        await pygato_wire.start()

        await pygato_wire.send(
            await serializer.serialize(SessionStartFrame(turn_id=1, session_id="s1")),
        )
        await pygato_wire.send(
            await serializer.serialize(UserMessageFrame(turn_id=2, text="hi")),
        )
        await asyncio.wait_for(started.wait(), timeout=3.0)
        assert timeline == ["start:hi"]

        # Raise the watermark over that turn — the adapter must cancel it.
        await pygato_wire.send(
            await serializer.serialize(InterruptionFrame(through_turn=2)),
        )
        await wait_for(lambda: "cancelled:hi" in timeline, timeout=3.0)

        await pygato_wire.close()
        run_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await run_task
