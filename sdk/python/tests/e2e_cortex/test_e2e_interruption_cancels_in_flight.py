"""A barge-in InterruptionFrame cancels the in-flight turn on the agent side. No
further LLM frames from that unit cross the wire after the interruption, and the
agent echoes an InterruptionFrame back as pygato's drain barrier."""

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
    LLMTextFrame,
    SessionStartFrame,
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
            await client.send(SessionStartFrame(session_id="s1", agent_id="welcome", payload={}))
            await client.send(UserMessageFrame(text="say hi"), epoch=1)

            # Wait for the first chunk to arrive over the wire.
            frames, _ = await client.collect_until(
                lambda fr, _ac: any(isinstance(f, LLMTextFrame) for f in fr),
                timeout=3.0,
            )
            assert any(f.text == "chunk-1" for f in frames if isinstance(f, LLMTextFrame))

            # Barge in. The agent cancels the turn and echoes an
            # InterruptionFrame back as the drain barrier — on the outbound
            # system lane, so it jumps ahead of any queued data.
            await client.send(InterruptionFrame())
            await wait_until(lambda: "cancelled:say hi" in StreamingResponder.timeline, timeout=3.0)

            # Collect everything up to and including the InterruptionFrame echo.
            frames2, _ = await client.collect_until(
                lambda fr, _ac: any(isinstance(f, InterruptionFrame) for f in fr),
                timeout=3.0,
            )
            assert any(isinstance(f, InterruptionFrame) for f in frames2)
            # No further LLM text frames slipped through after the barge-in.
            assert not any(isinstance(f, LLMTextFrame) for f in frames2), (
                f"text frames slipped through after interruption: {frames2}"
            )
        finally:
            await client.close()
            run_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await run_task
