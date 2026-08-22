"""Outbound congestion: when the adapter emits frames faster than the wire
drains, the normal-lane bound kicks in. The runner drops newest and delivers a
single non-fatal ``ErrorFrame`` back to the adapter (via ``handle_frame``) —
edge-triggered, so the adapter isn't spammed with one ErrorFrame per drop.

The session is NOT killed by the runner — once the lane drains below the
low-watermark the congestion flag clears.
"""

from __future__ import annotations

import asyncio
import contextlib

from tests.cortex.conftest import wait_for
from tests.fakes.cortex import FakeCortex
from voqalize.sdk.engine import Emitter, Envelope, SessionAdapter
from voqalize.sdk.outbound import CortexAgent
from voqalize.sdk.wire import (
    ErrorFrame,
    Frame,
    SessionStartFrame,
    SpeechChunkFrame,
    UserMessageFrame,
    Wire,
    WireConfig,
    WireSerializer,
)

_QUEUE_MAX = 4
_FLOOD = 64  # well above _QUEUE_MAX so drops are guaranteed


class Flooder(SessionAdapter):
    """On the first UserMessageFrame, emit ``_FLOOD`` SpeechChunkFrames in a tight
    synchronous loop (no await → the outbound lane can't drain between sends, so
    it overflows). Records any ErrorFrame the runner delivers back."""

    instances: list[Flooder] = []

    def __init__(self, emitter: Emitter) -> None:
        self.emitter = emitter
        Flooder.instances.append(self)
        self.errors: list[ErrorFrame] = []
        self._fired = False

    async def handle_frame(self, env: Envelope) -> None:

        frame = env.frame
        if isinstance(frame, ErrorFrame):
            self.errors.append(frame)
            return
        if isinstance(frame, UserMessageFrame) and not self._fired:
            self._fired = True
            for i in range(_FLOOD):
                self.emitter.send(SpeechChunkFrame(text=f"chunk-{i}"), epoch=env.epoch, speech_id=1)

    async def close(self) -> None:
        pass


async def _send(wire: Wire, serializer: WireSerializer, frame: Frame, *, epoch: int = 0) -> None:
    await wire.send(await serializer.serialize(frame, epoch=epoch))


async def test_outbound_overflow_delivers_error_frame() -> None:
    """The adapter flushes far more frames than the outbound lane can hold. The
    runner must drop newest and deliver at most a small handful of non-fatal
    ErrorFrames per congestion episode."""

    Flooder.instances.clear()
    serializer = WireSerializer()

    async with FakeCortex() as cortex:
        agent = CortexAgent(
            api_key="welcome",
            version="1.0.0",
            cortex_url=cortex.agent_url("welcome"),
            factory=lambda emitter: Flooder(emitter),
            # Both inbound and outbound lanes share this bound; a tiny value
            # makes outbound overflow easy to trigger when the adapter pushes
            # faster than the single writer task drains.
            inbound_queue_maxsize=_QUEUE_MAX,
        )
        run_task = asyncio.create_task(agent.run())

        wire = Wire(WireConfig(url=cortex.pygato_url("s1", "welcome")))
        try:
            await wire.start()

            await _send(
                wire,
                serializer,
                SessionStartFrame(session_id="s1", init={}),
            )
            await _send(
                wire,
                serializer,
                UserMessageFrame(text="go"),
                epoch=1,
            )

            await wait_for(lambda: len(Flooder.instances) == 1, timeout=3.0)
            flooder = Flooder.instances[0]

            # Eventually an ErrorFrame should arrive describing the outbound
            # congestion.
            await wait_for(lambda: len(flooder.errors) >= 1, timeout=5.0)

            # All congestion ErrorFrames are non-fatal — the runner never kills.
            assert all(not e.fatal for e in flooder.errors), (
                "outbound drops must be non-fatal — the runner never kills a session"
            )
            assert any("outbound queue full" in (e.error or "") for e in flooder.errors), (
                f"expected an outbound-drop ErrorFrame; got {[e.error for e in flooder.errors]}"
            )

            # Edge-triggered: a single congestion episode produces one ErrorFrame
            # (tolerate up to 2 in case the writer drains and re-congests).
            assert len(flooder.errors) <= 2, (
                f"expected edge-triggered ErrorFrame (≤2), got {len(flooder.errors)}"
            )
        finally:
            with contextlib.suppress(Exception):
                await wire.close()
            run_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await run_task
