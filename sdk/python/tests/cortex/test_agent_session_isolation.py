"""Two concurrent sessions on the same agent process don't leak frames into
each other's engines. Each session_id arriving on the multiplexed wire gets its
own SessionRunner + Brain instance; cross-session emits go to the right pygato
leg, not the other.
"""

from __future__ import annotations

import asyncio
import contextlib

from tests.cortex.conftest import wait_for
from tests.fakes.cortex import FakeCortex
from voqalize.sdk import Brain, Chunk, SpeechEnd, SpeechStart
from voqalize.sdk.brain import brain_factory
from voqalize.sdk.outbound import CortexAgent
from voqalize.sdk.wire import (
    CortexFrameSerializer,
    Frame,
    FrameDirection,
    LLMTextFrame,
    SessionStartFrame,
    UserMessageFrame,
    Wire,
    WireConfig,
)


class Echo(Brain):
    """On each turn, speak a single echo of the input. Records the transcripts it
    saw for the isolation assertions."""

    instances: list[Echo] = []

    def __init__(self) -> None:
        Echo.instances.append(self)
        self.seen_contexts: list[str] = []

    async def on_user_message(self, session, msg):
        self.seen_contexts.append(msg.text)
        yield SpeechStart()
        yield Chunk(f"echo:{msg.text}")
        yield SpeechEnd()


async def _drain_until(wire: Wire, serializer, predicate, timeout: float = 3.0):
    """Read frames from a pygato wire into a list until the predicate holds."""
    received: list[Frame] = []

    async def loop() -> None:
        while True:
            _direction, payload = await wire.recv()
            frame = await serializer.deserialize(payload)
            received.append(frame)
            if predicate(received):
                return

    await asyncio.wait_for(loop(), timeout=timeout)
    return received


async def test_two_sessions_are_isolated() -> None:
    Echo.instances.clear()
    serializer = CortexFrameSerializer()

    async with FakeCortex() as cortex:
        agent = CortexAgent(
            api_key="welcome",
            version="1.0.0",
            cortex_url=cortex.agent_url("welcome"),
            factory=brain_factory(Echo),
        )
        run_task = asyncio.create_task(agent.run())

        wire_a = Wire(WireConfig(url=cortex.pygato_url("sA", "welcome")))
        wire_b = Wire(WireConfig(url=cortex.pygato_url("sB", "welcome")))
        await wire_a.start()
        await wire_b.start()

        # Open both sessions.
        for session_id, wire in (("sA", wire_a), ("sB", wire_b)):
            await wire.send(
                FrameDirection.DOWNSTREAM,
                await serializer.serialize(
                    SessionStartFrame(session_id=session_id, agent_id="welcome", payload={})
                ),
            )

        # Send a context frame on each leg.
        await wire_a.send(
            FrameDirection.DOWNSTREAM,
            await serializer.serialize(UserMessageFrame(text="hello-A"), epoch=1),
        )
        await wire_b.send(
            FrameDirection.DOWNSTREAM,
            await serializer.serialize(UserMessageFrame(text="hello-B"), epoch=1),
        )

        # Each pygato wire must receive only its own session's response.
        recv_a = await _drain_until(
            wire_a,
            serializer,
            lambda r: any(isinstance(f, LLMTextFrame) for f in r),
        )
        recv_b = await _drain_until(
            wire_b,
            serializer,
            lambda r: any(isinstance(f, LLMTextFrame) for f in r),
        )

        text_a = next(f for f in recv_a if isinstance(f, LLMTextFrame))
        text_b = next(f for f in recv_b if isinstance(f, LLMTextFrame))
        assert text_a.text == "echo:hello-A"
        assert text_b.text == "echo:hello-B"

        # The two engines must be distinct Echo instances and only see their
        # own context.
        await wait_for(lambda: len(Echo.instances) == 2, timeout=2.0)
        assert len(Echo.instances) == 2
        per_instance_texts = sorted(t for inst in Echo.instances for t in inst.seen_contexts)
        assert per_instance_texts == ["hello-A", "hello-B"]
        for inst in Echo.instances:
            assert len(inst.seen_contexts) == 1, (
                "each session's Brain should only see its own context"
            )

        await wire_a.close()
        await wire_b.close()
        run_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await run_task
