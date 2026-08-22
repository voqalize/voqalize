"""A factory (or anything else that kills the reader) must surface out of
``CortexAgent.run()`` — not vanish as a clean return.

Regression: a Brain factory with the wrong signature crashed SessionRunner
construction on the first inbound frame; the reader task died holding the
exception, ``run()`` returned 0, and the process exited with zero output.
"""

from __future__ import annotations

import asyncio

import pytest

from tests.fakes.cortex import FakeCortex
from voqalize.sdk.outbound import CortexAgent
from voqalize.sdk.wire import (
    CortexFrameSerializer,
    SessionStartFrame,
    Wire,
    WireConfig,
)


class _Boom(Exception):
    pass


def _broken_factory(_host):
    raise _Boom("factory blew up")


async def test_factory_crash_raises_out_of_run() -> None:
    serializer = CortexFrameSerializer()

    async with FakeCortex() as cortex:
        agent = CortexAgent(
            api_key="welcome",
            version="1.0.0",
            cortex_url=cortex.agent_url("welcome"),
            factory=_broken_factory,
        )
        run_task = asyncio.create_task(agent.run())

        wire = Wire(WireConfig(url=cortex.pygato_url("s1", "welcome")))
        await wire.start()
        await wire.send(
            await serializer.serialize(
                SessionStartFrame(session_id="s1", agent_id="welcome", payload={})
            ),
        )

        with pytest.raises(_Boom):
            await asyncio.wait_for(run_task, timeout=3.0)

        await wire.close()
