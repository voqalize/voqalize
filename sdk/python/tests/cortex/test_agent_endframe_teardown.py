"""Natural session teardown via EndFrame.

When pygato sends EndFrame for a session, the SDK must:
  1. Dispatch the EndFrame to the session adapter so the customer sees it.
  2. Tear down the session's internal tasks (feeder, error pump) without leaks.
  3. Remove the session from CortexAgent's session map.

A second VqlStartFrame for the same session_id after teardown must build a
fresh adapter instance — proving the slot was freed.
"""

from __future__ import annotations

import asyncio
import contextlib

from tests.cortex.conftest import wait_for
from tests.fakes.cortex import FakeCortex
from voqalize.sdk.engine import Emitter, SessionAdapter
from voqalize.sdk.outbound import CortexAgent
from voqalize.sdk.wire import (
    CortexFrameSerializer,
    EndFrame,
    Frame,
    FrameDirection,
    VqlStartFrame,
    VqlUserTextFrame,
    Wire,
    WireConfig,
)


class Recorder(SessionAdapter):
    instances: list[Recorder] = []

    def __init__(self, emitter: Emitter) -> None:
        self.emitter = emitter
        Recorder.instances.append(self)
        self.saw_context = False
        self.saw_end = False

    async def handle_frame(self, frame: Frame) -> None:
        if isinstance(frame, VqlUserTextFrame):
            self.saw_context = True
        if isinstance(frame, EndFrame):
            self.saw_end = True

    async def close(self) -> None:
        pass


async def _send(wire: Wire, serializer: CortexFrameSerializer, frame: Frame) -> None:
    await wire.send(FrameDirection.DOWNSTREAM, await serializer.serialize(frame))


async def test_endframe_tears_down_session_cleanly() -> None:
    Recorder.instances.clear()
    serializer = CortexFrameSerializer()

    async with FakeCortex() as cortex:
        agent = CortexAgent(
            api_key="welcome",
            version="1.0.0",
            cortex_url=cortex.agent_url("welcome"),
            factory=lambda emitter: Recorder(emitter),
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
            await _send(wire, serializer, VqlUserTextFrame(interaction_id=1, text="hi"))

            await wait_for(lambda: len(Recorder.instances) == 1, timeout=3.0)
            rec = Recorder.instances[0]
            await wait_for(lambda: rec.saw_context, timeout=3.0)

            # End the session over the wire.
            await _send(wire, serializer, EndFrame())

            # Customer sees the EndFrame.
            await wait_for(lambda: rec.saw_end, timeout=3.0)

            # And the SDK reaps the session — the internal map empties and the
            # adapter's close() ran (teardown of feeder + error pump).
            await wait_for(lambda: len(agent._sessions) == 0, timeout=3.0)

            # A re-Start for the same session_id should produce a fresh adapter
            # instance — proving the slot was actually freed.
            await _send(
                wire,
                serializer,
                VqlStartFrame(session_id="s1", agent_id="welcome", payload={}),
            )
            await wait_for(lambda: len(Recorder.instances) == 2, timeout=3.0)
            assert Recorder.instances[1] is not Recorder.instances[0]
        finally:
            with contextlib.suppress(Exception):
                await wire.close()
            agent.request_stop()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.wait_for(run_task, timeout=3.0)
            if not run_task.done():
                run_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await run_task
