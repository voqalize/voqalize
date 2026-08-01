"""End-to-end round trip across the wire vocabulary, over a real FakeCortex.

Pygato side (simulated by a Wire client): open a session with a VqlStartFrame,
then drive a user turn + an inference-finalized frame.

Agent side: a ``Brain`` recognises the interaction and speaks a full LLM
response. The pygato client must see the LLM frames arrive back over the wire.
"""

from __future__ import annotations

import asyncio
import contextlib

from tests.e2e_cortex.conftest import connect_pygato
from tests.fakes.cortex import FakeCortex
from voqalize.sdk import Brain, make_agent
from voqalize.sdk.wire import (
    FinalizeReason,
    VqlInferenceFinalizedFrame,
    VqlLLMFullResponseEndFrame,
    VqlLLMFullResponseStartFrame,
    VqlLLMTextFrame,
    VqlStartFrame,
    VqlUserTextFrame,
)


class LLMResponder(Brain):
    """On each interaction, speak a one-chunk LLM response."""

    async def on_interaction(self, interaction) -> None:
        async with interaction.say() as inf:
            await inf.speak("hello")


async def test_round_trip_every_frame() -> None:
    async with FakeCortex() as cortex:
        agent = make_agent(
            LLMResponder,
            api_key="welcome",
            version="1.0.0",
            cortex_url=cortex.agent_url("welcome"),
        )
        run_task = asyncio.create_task(agent.run())

        client = await connect_pygato(cortex, "s1")
        try:
            # Open the session.
            await client.send(VqlStartFrame(session_id="s1", agent_id="welcome", payload={}))

            # Drive a user turn + a finalize.
            await client.send(VqlUserTextFrame(interaction_id=1, text="user said hi"))
            await client.send(
                VqlInferenceFinalizedFrame(
                    interaction_id=1,
                    inference_id=1,
                    heard_text="bot said hi",
                    interrupted=False,
                    reason=FinalizeReason.COMPLETED,
                )
            )

            # The Brain's inference bracket emits Start → Text → End.
            expected = {
                "VqlLLMFullResponseStartFrame",
                "VqlLLMTextFrame",
                "VqlLLMFullResponseEndFrame",
            }
            frames, _ = await client.collect_until(
                lambda fr, _ac: expected.issubset({type(f).__name__ for f in fr}),
                timeout=5.0,
            )
            texts = [f.text for f in frames if isinstance(f, VqlLLMTextFrame)]
            assert "hello" in texts
            assert any(isinstance(f, VqlLLMFullResponseStartFrame) for f in frames)
            assert any(isinstance(f, VqlLLMFullResponseEndFrame) for f in frames)
        finally:
            await client.close()
            run_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await run_task
