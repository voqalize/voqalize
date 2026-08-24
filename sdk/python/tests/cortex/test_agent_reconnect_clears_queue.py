"""On wire reconnect the SDK tears down every active session; pygato re-sends
SessionStartFrame for each live session, which builds a fresh SessionRunner + adapter
instance.
"""

from __future__ import annotations

import asyncio
import contextlib

from tests.cortex.conftest import wait_for
from tests.fakes.cortex import FakeCortex
from voqalize.sdk.engine import Emitter, SessionAdapter
from voqalize.sdk.outbound import CortexAgent
from voqalize.sdk.wire import (
    Frame,
    ResponseFrame,
    SessionStartFrame,
    UserMessageFrame,
    Wire,
    WireConfig,
    WireSerializer,
)


async def test_reconnect_drops_active_sessions_and_new_start_spins_fresh_adapter() -> None:
    serializer = WireSerializer()
    timeline: list[str] = []
    block = asyncio.Event()

    class Probe(SessionAdapter):
        instances: list[Probe] = []

        def __init__(self, emitter: Emitter) -> None:
            self.emitter = emitter
            Probe.instances.append(self)
            self._mine = len(Probe.instances)

        async def handle_frame(self, frame: Frame) -> None:
            if isinstance(frame, SessionStartFrame):
                timeline.append(f"start#{self._mine}:{frame.init.get('which', '?')}")
            elif isinstance(frame, UserMessageFrame):
                timeline.append(f"data#{self._mine}:start:{frame.turn_id}")
                try:
                    await block.wait()
                except asyncio.CancelledError:
                    timeline.append(f"data#{self._mine}:cancelled:{frame.turn_id}")
                    raise
                timeline.append(f"data#{self._mine}:end:{frame.turn_id}")

        def settle_response(self, frame: ResponseFrame) -> None:
            pass

        async def close(self) -> None:
            pass

    async with FakeCortex() as cortex:
        agent = CortexAgent(
            api_key="welcome",
            version="1.0.0",
            cortex_url=cortex.agent_url("welcome"),
            factory=lambda emitter: Probe(emitter),
        )
        run_task = asyncio.create_task(agent.run())

        pygato_wire = Wire(WireConfig(url=cortex.pygato_url("s1", "welcome")))
        await pygato_wire.start()

        await pygato_wire.send(
            await serializer.serialize(
                SessionStartFrame(turn_id=1, session_id="s1", init={"which": "first"})
            ),
        )
        await pygato_wire.send(
            await serializer.serialize(UserMessageFrame(turn_id=2, text="hi")),
        )
        await wait_for(lambda: "data#1:start:2" in timeline, timeout=3.0)

        # Kill the agent leg with a transient code; SDK reconnects.
        await cortex.kill_agent_leg("welcome", code=4001)

        # The in-flight handle_frame on the first session must be cancelled.
        await wait_for(lambda: "data#1:cancelled:2" in timeline, timeout=3.0)

        # Pygato re-sends SessionStart for the same session — fresh adapter.
        await pygato_wire.send(
            await serializer.serialize(
                SessionStartFrame(turn_id=1, session_id="s1", init={"which": "second"})
            ),
        )
        await wait_for(
            lambda: any(s.startswith("start#") and s.endswith(":second") for s in timeline),
            timeout=3.0,
        )
        assert len(Probe.instances) >= 2, (
            f"expected a fresh adapter on the second SessionStart; got {len(Probe.instances)}"
        )

        await pygato_wire.close()
        run_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await run_task
