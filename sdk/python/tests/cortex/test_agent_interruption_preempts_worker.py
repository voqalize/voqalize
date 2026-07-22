"""An InterruptionFrame cancels the Brain's in-flight interaction task.

In the pipecat-free engine, the Brain adapter SPAWNS ``on_interaction`` so the
inbound frame acks promptly; a barge-in ``InterruptionFrame`` (system lane) then
cancels the in-flight interaction coroutine. Verify that contract round-trips
through CortexAgent + the multiplexed wire."""

from __future__ import annotations

import asyncio
import contextlib

from tests.cortex.conftest import wait_for
from tests.fakes.cortex import FakeCortex
from voqalize.sdk import Brain, brain_factory
from voqalize.sdk.outbound import CortexAgent
from voqalize.sdk.wire import (
    CortexFrameSerializer,
    FrameDirection,
    InterruptionFrame,
    VqlStartFrame,
    VqlUserTextFrame,
    Wire,
    WireConfig,
)


async def test_interruption_cancels_in_flight_interaction() -> None:
    serializer = CortexFrameSerializer()
    timeline: list[str] = []
    started = asyncio.Event()

    class Blocking(Brain):
        async def on_interaction(self, interaction) -> None:
            timeline.append(f"start:{interaction.id}")
            started.set()
            try:
                await asyncio.Event().wait()  # block forever
            except asyncio.CancelledError:
                timeline.append(f"cancelled:{interaction.id}")
                raise

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
            FrameDirection.DOWNSTREAM,
            await serializer.serialize(
                VqlStartFrame(session_id="s1", agent_id="welcome", payload={})
            ),
        )
        await pygato_wire.send(
            FrameDirection.DOWNSTREAM,
            await serializer.serialize(VqlUserTextFrame(interaction_id=1, text="hi")),
        )
        await asyncio.wait_for(started.wait(), timeout=3.0)
        assert timeline == ["start:1"]

        # Send interruption — the Brain adapter must cancel the in-flight
        # interaction task.
        await pygato_wire.send(
            FrameDirection.DOWNSTREAM,
            await serializer.serialize(InterruptionFrame()),
        )
        await wait_for(lambda: "cancelled:1" in timeline, timeout=3.0)

        await pygato_wire.close()
        run_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await run_task
