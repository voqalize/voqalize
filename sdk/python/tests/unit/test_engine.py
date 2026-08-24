"""Unit tests for the per-session engine (:class:`SessionRunner`).

Drives a runner directly through a fake :class:`RunnerHost`, pinning the lane
semantics: priority-lane ordering (both directions), drop-newest on the bulk lane
with an edge-triggered congestion ``ErrorFrame`` delivered to the adapter, and
EndFrame teardown notifying the host.

(Cross-session fair-writer round-robin is a CortexAgent concern, covered by
``tests/cortex/test_agent_session_isolation.py``; single-session runner behaviour
is pinned here.)
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from voqalize.sdk.engine import (
    DEFAULT_BULK_MAXSIZE,
    DEFAULT_PRIORITY_MAXSIZE,
    Emitter,
    RunnerHost,
    SessionAdapter,
    SessionRunner,
)
from voqalize.sdk.wire import (
    CancelFrame,
    EndFrame,
    ErrorCode,
    ErrorFrame,
    Frame,
    InterruptionFrame,
    ResponseFrame,
    SpeechChunkFrame,
    UserMessageFrame,
)

SID = b"\x00" * 15 + b"\x01"

FrameHook = Callable[[Frame, "Recorder"], Awaitable[None]]


class FakeHost(RunnerHost):
    def __init__(self) -> None:
        self.ready_signals = 0
        self.closed: list[SessionRunner] = []

    def signal_ready(self, runner: SessionRunner) -> None:
        self.ready_signals += 1

    def close_session(self, runner: SessionRunner) -> None:
        self.closed.append(runner)


class Recorder(SessionAdapter):
    def __init__(self, emitter: Emitter, on_frame: FrameHook | None = None) -> None:
        self.emitter = emitter
        self.received: list[Frame] = []
        self.closed = False
        self._on_frame = on_frame

    async def handle_frame(self, frame: Frame) -> None:
        self.received.append(frame)
        if self._on_frame is not None:
            await self._on_frame(frame, self)

    def settle_response(self, frame: ResponseFrame) -> None:
        self.received.append(frame)

    async def close(self) -> None:
        self.closed = True


def _build(
    *, bulk_max: int = DEFAULT_BULK_MAXSIZE, on_frame: FrameHook | None = None
) -> tuple[SessionRunner, Recorder, FakeHost]:
    host = FakeHost()
    holder: dict[str, Recorder] = {}

    def factory(emitter: Emitter) -> SessionAdapter:
        adapter = Recorder(emitter, on_frame)
        holder["adapter"] = adapter
        return adapter

    runner = SessionRunner(session_id=SID, factory=factory, host=host, bulk_max=bulk_max)
    return runner, holder["adapter"], host


async def _until(predicate, *, timeout: float = 2.0, interval: float = 0.005) -> None:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(interval)
    raise AssertionError(f"timeout waiting for {predicate}")


# ─── Inbound: priority lane ordering ─────────────────────────────────────────


async def test_priority_lane_dispatched_before_bulk() -> None:
    runner, adapter, _host = _build(bulk_max=64)
    # Enqueue three bulk frames, then one priority frame, all before the feeder
    # starts — so the feeder's first pop must choose the priority lane.
    runner.enqueue_inbound(UserMessageFrame(text="a"))
    runner.enqueue_inbound(UserMessageFrame(text="b"))
    runner.enqueue_inbound(UserMessageFrame(text="c"))
    runner.enqueue_inbound(InterruptionFrame(through_turn=3))  # priority lane
    runner.start()
    try:
        await _until(lambda: len(adapter.received) == 4)
        assert isinstance(adapter.received[0], InterruptionFrame), (
            f"priority lane must come first; got {type(adapter.received[0]).__name__}"
        )
        texts = [f.text for f in adapter.received[1:] if isinstance(f, UserMessageFrame)]
        assert texts == ["a", "b", "c"]
    finally:
        await runner.cancel()


# ─── Inbound: drop-newest + congestion ErrorFrame ────────────────────────────


async def test_inbound_bulk_lane_drops_newest_and_signals_error() -> None:
    runner, adapter, _host = _build(bulk_max=4)
    for i in range(8):
        runner.enqueue_inbound(SpeechChunkFrame(speech_id=1, text=f"f{i}"))
    # First 4 kept, remaining 4 dropped (drop-newest) — all before the feeder ran.
    assert runner._in.depth() == 4
    runner.start()
    try:
        # The four survivors are the FIRST four, and a single non-fatal
        # ErrorFrame is delivered to the adapter about the congestion.
        await _until(lambda: any(isinstance(f, ErrorFrame) for f in adapter.received))
        texts = [f.text for f in adapter.received if isinstance(f, SpeechChunkFrame)]
        assert texts == ["f0", "f1", "f2", "f3"]
        errs = [f for f in adapter.received if isinstance(f, ErrorFrame)]
        assert len(errs) == 1
        assert not errs[0].fatal
        assert errs[0].code is ErrorCode.OVERLOAD
        assert "inbound queue full" in errs[0].message
    finally:
        await runner.cancel()


async def test_a_full_bulk_lane_still_queues_what_it_cannot_shed() -> None:
    """Droppability is a property of the flow, not of the queue. Speech chunks
    and RTVI messages are unbounded, so a full lane sheds them; a user message is
    bounded by turns taken, so it queues however deep the backlog runs."""
    runner, _adapter, _host = _build(bulk_max=2)
    for i in range(4):
        runner.enqueue_inbound(SpeechChunkFrame(speech_id=1, text=f"c{i}"))
    assert runner._in.depth() == 2
    runner.enqueue_inbound(UserMessageFrame(turn_id=9, text="say this anyway"))
    assert runner._in.depth() == 3


# ─── Outbound: drop-newest + congestion ErrorFrame ───────────────────────────


async def test_outbound_overflow_delivers_error_frame() -> None:
    async def flood(frame: Frame, adapter: Recorder) -> None:
        if isinstance(frame, UserMessageFrame):
            # Tight synchronous burst; nobody pops the outbound lane in this
            # unit test, so it overflows past normal_max and drops newest.
            for i in range(64):
                adapter.emitter.send(SpeechChunkFrame(speech_id=1, text=f"c{i}"))

    runner, adapter, host = _build(bulk_max=4, on_frame=flood)
    runner.enqueue_inbound(UserMessageFrame(text="go"))
    runner.start()
    try:
        await _until(lambda: any(isinstance(f, ErrorFrame) for f in adapter.received))
        errs = [f for f in adapter.received if isinstance(f, ErrorFrame)]
        assert not errs[0].fatal
        assert "outbound queue full" in errs[0].message
        # The runner never kills the session on a drop.
        assert host.closed == []
    finally:
        await runner.cancel()


# ─── Outbound: a priority frame jumps ahead of queued bulk frames ────────────


async def test_outbound_priority_frame_pops_first() -> None:
    async def emit_mix(frame: Frame, adapter: Recorder) -> None:
        if isinstance(frame, UserMessageFrame):
            for i in range(3):
                adapter.emitter.send(SpeechChunkFrame(speech_id=1, text=f"n{i}"))
            adapter.emitter.send(CancelFrame())  # priority lane

    runner, _adapter, _host = _build(bulk_max=64, on_frame=emit_mix)
    runner.enqueue_inbound(UserMessageFrame(turn_id=2, text="go"))
    runner.start()
    try:
        await _until(lambda: runner._out.depth() == 4)
        first = runner.pop_out()
        assert isinstance(first, CancelFrame), f"priority lane must pop first; got {first!r}"
    finally:
        await runner.cancel()


async def test_end_drains_behind_queued_data() -> None:
    """``End`` is terminal but not priority: a session tears down only after the
    data already queued in front of it has been dispatched."""
    runner, adapter, host = _build(bulk_max=64)
    runner.enqueue_inbound(SpeechChunkFrame(speech_id=1, text="one"))
    runner.enqueue_inbound(SpeechChunkFrame(speech_id=1, text="two"))
    runner.enqueue_inbound(EndFrame())
    runner.start()
    await _until(lambda: runner in host.closed)
    assert [type(f).__name__ for f in adapter.received] == [
        "SpeechChunkFrame",
        "SpeechChunkFrame",
        "EndFrame",
    ]


# ─── EndFrame teardown notifies the host ─────────────────────────────────────


async def test_endframe_tears_down_and_notifies_host() -> None:
    runner, adapter, host = _build()
    runner.enqueue_inbound(EndFrame())
    runner.start()
    await _until(lambda: runner in host.closed)
    assert adapter.closed is True
    assert isinstance(adapter.received[-1], EndFrame)


# Module-level constants are sane.
def test_default_maxsizes_positive() -> None:
    assert DEFAULT_BULK_MAXSIZE > 0
    assert DEFAULT_PRIORITY_MAXSIZE > 0
