"""End-to-end round trip across the wire vocabulary, over a real FakeCortex.

Pygato side (simulated by a Wire client): open a session with a SessionStartFrame,
then drive a user turn + a finalize frame.

Agent side: a ``Brain`` takes the turn and speaks a full unit of speech. The
pygato client must see the speech frames arrive back over the wire.
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
    FinalizeFrame,
    FinalizeReason,
    SessionStartFrame,
    SpeechChunkFrame,
    SpeechEndFrame,
    SpeechStartFrame,
    UserMessageFrame,
)


class SpeechResponder(Brain):
    """On each turn, speak a one-chunk response."""

    async def on_user_message(self, session, msg):
        yield SpeechStart()
        yield Chunk("hello")
        yield SpeechEnd()


async def test_round_trip_every_frame() -> None:
    async with FakeCortex() as cortex:
        agent = CortexAgent(
            factory=brain_factory(SpeechResponder),
            api_key="welcome",
            version="1.0.0",
            cortex_url=cortex.agent_url("welcome"),
        )
        run_task = asyncio.create_task(agent.run())

        client = await connect_pygato(cortex, "s1")
        try:
            # Open the session.
            await client.send(SessionStartFrame(turn_id=1, session_id="s1"))

            # Drive a user turn + a finalize.
            await client.send(UserMessageFrame(turn_id=2, text="user said hi"))
            await client.send(
                FinalizeFrame(
                    speech_id=1, heard_text="bot said hi", reason=FinalizeReason.COMPLETED
                ),
            )

            # The Brain's unit of speech emits Start → Text → End.
            expected = {
                "SpeechStartFrame",
                "SpeechChunkFrame",
                "SpeechEndFrame",
            }
            frames = await client.collect_until(
                lambda fr: expected.issubset({type(f).__name__ for f in fr}),
                timeout=5.0,
            )
            texts = [f.text for f in frames if isinstance(f, SpeechChunkFrame)]
            assert "hello" in texts
            assert any(isinstance(f, SpeechStartFrame) for f in frames)
            assert any(isinstance(f, SpeechEndFrame) for f in frames)
        finally:
            await client.close()
            run_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await run_task
