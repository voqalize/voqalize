"""When cortex closes the agent leg with code 4000 (NoAgent), `agent.run()`
raises `PermanentClose` instead of looping reconnect.
"""

from __future__ import annotations

import asyncio

import pytest

from tests.cortex.conftest import RecordingAdapter
from tests.fakes.cortex import FakeCortex
from voqalize.sdk.outbound import CortexAgent
from voqalize.sdk.wire import PermanentClose


async def test_close_4000_raises_permanent() -> None:
    async with FakeCortex() as cortex:
        agent = CortexAgent(
            api_key="welcome",
            version="1.0.0",
            cortex_url=cortex.agent_url("welcome"),
            factory=lambda emitter: RecordingAdapter(emitter),
        )
        run_task = asyncio.create_task(agent.run())

        # Give the wire a beat to connect, then close with 4000.
        await asyncio.sleep(0.1)
        await cortex.kill_agent_leg("welcome", code=4000)

        with pytest.raises(PermanentClose):
            await asyncio.wait_for(run_task, timeout=3.0)
