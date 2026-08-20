"""End-to-end round trip across the wire vocabulary, over a real FakeCortex.

Pygato side (simulated by a Wire client): open a session with a SessionStartFrame,
then drive a user turn + an inference-finalized frame.

Agent side: a ``Brain`` takes the turn and speaks a full unit of speech. The
pygato client must see the LLM frames arrive back over the wire.
"""

from __future__ import annotations

import asyncio
import contextlib

from tests.e2e_cortex.conftest import connect_pygato
from tests.fakes.cortex import FakeCortex
from voqalize.sdk import Brain, Chunk, SpeechEnd, SpeechStart
from voqalize.sdk.brain import brain_factory
from voqalize.sdk.outbound import CortexAgent
from voqalize.sdk.wire import (
    FinalizeReason,
    InferenceFinalizedFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    SessionStartFrame,
    UserMessageFrame,
)


class LLMResponder(Brain):
    """On each turn, speak a one-chunk response."""

    async def on_user_message(self, session, msg):
        yield SpeechStart()
        yield Chunk("hello")
        yield SpeechEnd()


async def test_round_trip_every_frame() -> None:
    async with FakeCortex() as cortex:
        agent = CortexAgent(
            factory=brain_factory(LLMResponder),
            api_key="welcome",
            version="1.0.0",
            cortex_url=cortex.agent_url("welcome"),
        )
        run_task = asyncio.create_task(agent.run())

        client = await connect_pygato(cortex, "s1")
        try:
            # Open the session.
            await client.send(SessionStartFrame(session_id="s1", agent_id="welcome", payload={}))

            # Drive a user turn + a finalize.
            await client.send(UserMessageFrame(text="user said hi"), epoch=1)
            await client.send(
                InferenceFinalizedFrame(heard_text="bot said hi", reason=FinalizeReason.COMPLETED),
                epoch=1,
                inference_id=1,
            )

            # The Brain's unit of speech emits Start → Text → End.
            expected = {
                "LLMFullResponseStartFrame",
                "LLMTextFrame",
                "LLMFullResponseEndFrame",
            }
            frames, _ = await client.collect_until(
                lambda fr, _ac: expected.issubset({type(f).__name__ for f in fr}),
                timeout=5.0,
            )
            texts = [f.text for f in frames if isinstance(f, LLMTextFrame)]
            assert "hello" in texts
            assert any(isinstance(f, LLMFullResponseStartFrame) for f in frames)
            assert any(isinstance(f, LLMFullResponseEndFrame) for f in frames)
        finally:
            await client.close()
            run_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await run_task
