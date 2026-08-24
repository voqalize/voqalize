"""A barge-in InterruptionFrame cancels the in-flight turn on the agent side. No
further speech frames from that unit cross the wire after the watermark, and
nothing is echoed back — Voqalize set the watermark, so it already knows."""

from __future__ import annotations

import asyncio
import contextlib

from tests.e2e_cortex.conftest import connect_pygato, wait_until
from tests.fakes.cortex import FakeCortex
from voqalize.sdk import Brain, Chunk, SpeechEnd, SpeechStart
from voqalize.sdk.brain import brain_factory
from voqalize.sdk.outbound import CortexAgent
from voqalize.sdk.wire import (
    InterruptionFrame,
    SessionStartFrame,
    SpeechChunkFrame,
    UserMessageFrame,
)


class StreamingResponder(Brain):
    """Speaks one chunk then blocks forever; gets cancelled by the barge-in."""

    timeline: list[str] = []

    async def on_user_message(self, session, msg):
        StreamingResponder.timeline.append(f"start:{msg.text}")
        yield SpeechStart()
        yield Chunk("chunk-1")
        try:
            await asyncio.Event().wait()  # block until cancelled
        except asyncio.CancelledError:
            StreamingResponder.timeline.append(f"cancelled:{msg.text}")
            raise
        yield SpeechEnd()


async def test_interruption_cancels_in_flight() -> None:
    StreamingResponder.timeline = []

    async with FakeCortex() as cortex:
        agent = CortexAgent(
            factory=brain_factory(StreamingResponder),
            api_key="welcome",
            version="1.0.0",
            cortex_url=cortex.agent_url("welcome"),
        )
        run_task = asyncio.create_task(agent.run())

        client = await connect_pygato(cortex, "s1")
        try:
            await client.send(SessionStartFrame(turn_id=1, session_id="s1"))
            await client.send(UserMessageFrame(turn_id=2, text="say hi"))

            # Wait for the first chunk to arrive over the wire.
            frames = await client.collect_until(
                lambda fr: any(isinstance(f, SpeechChunkFrame) for f in fr),
                timeout=3.0,
            )
            assert any(f.text == "chunk-1" for f in frames if isinstance(f, SpeechChunkFrame))

            # Barge in: raise the watermark over that turn.
            await client.send(InterruptionFrame(through_turn=2))
            await wait_until(lambda: "cancelled:say hi" in StreamingResponder.timeline, timeout=3.0)

            # Nothing more crosses the wire — no further speech, and no echo of
            # the watermark. An echo would be a priority frame overtaking the
            # very speech Voqalize is still waiting to see land.
            with contextlib.suppress(TimeoutError):
                await client.collect_until(lambda fr: bool(fr), timeout=1.0)
                raise AssertionError("the brain kept talking after the watermark")
        finally:
            await client.close()
            run_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await run_task
