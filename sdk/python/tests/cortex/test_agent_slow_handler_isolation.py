"""A slow ``handle_frame`` on one session must not block other sessions sharing
the same agent process.

This pins the engine's core promise: each session has its own SessionRunner with
its own pair of in/out lanes, the wire reader doesn't await the adapter's
coroutine, and a talkative-but-slow session that overflows its inbound normal
lane gets a non-fatal ``ErrorFrame`` (drop-newest) without affecting peers. The
congestion ErrorFrame is delivered on a separate error-pump task, so it reaches
the wedged adapter even while its feeder is parked in ``handle_frame``."""

from __future__ import annotations

import asyncio
import contextlib

from tests.cortex.conftest import wait_for
from tests.fakes.cortex import FakeCortex
from voqalize.sdk.engine import Emitter, Envelope, SessionAdapter
from voqalize.sdk.outbound import CortexAgent
from voqalize.sdk.wire import (
    CortexFrameSerializer,
    ErrorFrame,
    Frame,
    SessionStartFrame,
    UserMessageFrame,
    Wire,
    WireConfig,
)

_INBOUND_MAX = 4  # tiny so it's easy to overflow


class Recorder(SessionAdapter):
    """Per-session adapter. Session A parks on its gate while processing
    contexts (creating the head-of-line pile-up). Session B is fast.

    We disambiguate sessions by the ``A:`` / ``B:`` prefix on the first
    UserMessageFrame's text — the adapter isn't told its session id directly for
    data frames."""

    instances: list[Recorder] = []

    def __init__(self, emitter: Emitter) -> None:
        self.emitter = emitter
        Recorder.instances.append(self)
        self.session_tag: str | None = None
        self.contexts_processed: list[str] = []
        self.errors: list[ErrorFrame] = []
        self.gate = asyncio.Event()

    async def handle_frame(self, env: Envelope) -> None:

        frame = env.frame
        if isinstance(frame, UserMessageFrame):
            if self.session_tag is None:
                self.session_tag = frame.text.split(":", 1)[0]
            if self.session_tag == "A":
                # Slow handler on session A — block until released. Short
                # timeout keeps a hung test failing in seconds, not minutes.
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self.gate.wait(), timeout=8.0)
            self.contexts_processed.append(frame.text)
            return
        if isinstance(frame, ErrorFrame):
            self.errors.append(frame)
            return

    async def close(self) -> None:
        pass


async def _send(
    wire: Wire, serializer: CortexFrameSerializer, frame: Frame, *, epoch: int = 0
) -> None:
    await wire.send(await serializer.serialize(frame, epoch=epoch))


async def test_slow_handler_does_not_block_other_sessions() -> None:
    Recorder.instances.clear()
    serializer = CortexFrameSerializer()

    async with FakeCortex() as cortex:
        agent = CortexAgent(
            api_key="welcome",
            version="1.0.0",
            cortex_url=cortex.agent_url("welcome"),
            factory=lambda emitter: Recorder(emitter),
            inbound_queue_maxsize=_INBOUND_MAX,
        )
        run_task = asyncio.create_task(agent.run())

        wire_a = Wire(WireConfig(url=cortex.pygato_url("sA", "welcome")))
        wire_b = Wire(WireConfig(url=cortex.pygato_url("sB", "welcome")))
        try:
            await wire_a.start()
            await wire_b.start()
            await _run_assertions(wire_a, wire_b, serializer)
        finally:
            with contextlib.suppress(Exception):
                await wire_a.close()
            with contextlib.suppress(Exception):
                await wire_b.close()
            run_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await run_task


async def _run_assertions(wire_a: Wire, wire_b: Wire, serializer: CortexFrameSerializer) -> None:
    # Open both sessions and wait for both Recorder instances.
    await _send(
        wire_a,
        serializer,
        SessionStartFrame(session_id="sA", init={}),
    )
    await _send(
        wire_b,
        serializer,
        SessionStartFrame(session_id="sB", init={}),
    )
    await wait_for(lambda: len(Recorder.instances) == 2, timeout=3.0)

    # Send one context to A so the slow handler is already in flight.
    await _send(
        wire_a,
        serializer,
        UserMessageFrame(text="A:t0"),
        epoch=0,
    )

    # `session_tag` is set the moment the first context enters handle_frame; the
    # gate is still closed so the slow handler is parked, but the tag is visible.
    await wait_for(
        lambda: any(r.session_tag == "A" for r in Recorder.instances),
        timeout=3.0,
    )

    # Overflow the inbound queue on A. One context is in flight (blocked),
    # _INBOUND_MAX more fit, anything beyond drops.
    FLOOD = _INBOUND_MAX + 8
    for i in range(1, FLOOD + 1):
        await _send(
            wire_a,
            serializer,
            UserMessageFrame(text=f"A:t{i}"),
            epoch=i,
        )

    # B keeps flowing while A is wedged.
    await _send(
        wire_b,
        serializer,
        UserMessageFrame(text="B:t0"),
        epoch=0,
    )

    rec_a = next(r for r in Recorder.instances if r.session_tag == "A")
    rec_b = next(r for r in Recorder.instances if r is not rec_a)

    # B's context must complete even though A is wedged.
    await wait_for(lambda: "B:t0" in rec_b.contexts_processed, timeout=5.0)

    # A should have received at least one non-fatal ErrorFrame about the inbound
    # drop episode (edge-triggered: exactly one per episode).
    await wait_for(lambda: len(rec_a.errors) >= 1, timeout=5.0)
    assert all(not e.fatal for e in rec_a.errors), (
        "drop ErrorFrames must be non-fatal — the runner never kills a session"
    )
    assert any("inbound queue full" in (e.error or "") for e in rec_a.errors), (
        f"expected inbound-drop ErrorFrame, got {[e.error for e in rec_a.errors]}"
    )

    # Releasing A's gate lets the surviving frames drain. Importantly: A is NOT
    # killed by the drop — it keeps processing remaining frames.
    rec_a.gate.set()
    await wait_for(lambda: len(rec_a.contexts_processed) >= 2, timeout=5.0)
