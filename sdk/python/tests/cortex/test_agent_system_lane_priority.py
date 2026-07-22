"""A barge-in InterruptionFrame rides the system lane and preempts in-flight
work even under a normal-lane backlog.

In the pipecat-free engine, the Brain adapter spawns each ``on_interaction`` (so
inbound data frames ack promptly and the feeder never blocks), and the runner
dispatches the system-lane ``InterruptionFrame`` ahead of any queued normal
frames. The net observable: after piling up many user turns whose responses are
slow, a single interruption cancels the in-flight interaction(s) promptly —
without first grinding through the whole backlog.

(The pure lane-ordering guarantee — system frame popped before queued normal
frames — is pinned deterministically in ``tests/unit/test_engine.py``.)"""

from __future__ import annotations

import asyncio
import contextlib

from tests.cortex.conftest import wait_for
from tests.fakes.cortex import FakeCortex
from voqalize.sdk import Brain, brain_factory
from voqalize.sdk.outbound import CortexAgent
from voqalize.sdk.wire import (
    CortexFrameSerializer,
    Frame,
    FrameDirection,
    InterruptionFrame,
    VqlStartFrame,
    VqlUserTextFrame,
    Wire,
    WireConfig,
)


async def _send(wire: Wire, serializer: CortexFrameSerializer, frame: Frame) -> None:
    await wire.send(FrameDirection.DOWNSTREAM, await serializer.serialize(frame))


async def test_interruption_preempts_backlog() -> None:
    serializer = CortexFrameSerializer()
    timeline: list[str] = []
    first_in_flight = asyncio.Event()

    class Slow(Brain):
        async def on_interaction(self, interaction) -> None:
            timeline.append(f"start:{interaction.id}")
            if interaction.id == 0:
                first_in_flight.set()
            try:
                # Each response takes 30s — without interruption, draining 16 of
                # them serially would take minutes.
                await asyncio.sleep(30.0)
                timeline.append(f"done:{interaction.id}")
            except asyncio.CancelledError:
                timeline.append(f"cancelled:{interaction.id}")
                raise

    async with FakeCortex() as cortex:
        agent = CortexAgent(
            api_key="welcome",
            version="1.0.0",
            cortex_url=cortex.agent_url("welcome"),
            factory=brain_factory(Slow),
        )
        run_task = asyncio.create_task(agent.run())

        wire = Wire(WireConfig(url=cortex.pygato_url("s1", "welcome")))
        try:
            await wire.start()

            await _send(
                wire,
                serializer,
                VqlStartFrame(session_id="s1", agent_id="welcome", payload={}),
            )

            # Pile up 16 user turns. Each spawns a slow interaction task.
            for i in range(16):
                await _send(
                    wire,
                    serializer,
                    VqlUserTextFrame(interaction_id=i, text=f"hi-{i}"),
                )

            # Wait until the first interaction is actually running.
            await asyncio.wait_for(first_in_flight.wait(), timeout=3.0)
            assert timeline[0] == "start:0", timeline

            # Now interrupt. The interruption rides the system lane and must
            # cancel in-flight work well before the 30s/response backlog would.
            t0 = asyncio.get_event_loop().time()
            await _send(wire, serializer, InterruptionFrame())
            await wait_for(lambda: "cancelled:0" in timeline, timeout=5.0)
            elapsed = asyncio.get_event_loop().time() - t0
            assert elapsed < 5.0, f"interruption took {elapsed:.2f}s — system lane bypass failed"

            # Sanity: no interaction completed before the cancellation arrived.
            done_count = sum(1 for e in timeline if e.startswith("done:"))
            assert done_count == 0, (
                f"expected interruption to fire before any response completed; timeline={timeline}"
            )
        finally:
            with contextlib.suppress(Exception):
                await wire.close()
            run_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await run_task
