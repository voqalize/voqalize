"""Unit tests for the per-session engine (:class:`SessionRunner`).

Drives a runner directly through a fake :class:`RunnerHost`, pinning the lane
semantics that used to live in ``SessionBuffer``: system-lane priority (both
directions), drop-newest on the normal lane with an edge-triggered congestion
``ErrorFrame`` delivered to the adapter, ack emission after ``handle_frame``
returns, and EndFrame teardown notifying the host.

(Cross-session fair-writer round-robin is now a CortexAgent concern and is
covered by ``tests/cortex/test_agent_session_isolation.py``; single-session
runner behavior is pinned here.)
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from voqalize.sdk.engine import (
    DEFAULT_NORMAL_MAXSIZE,
    DEFAULT_SYSTEM_MAXSIZE,
    Emitter,
    RunnerHost,
    SessionAdapter,
    SessionRunner,
    _Ack,
)
from voqalize.sdk.wire import (
    CancelFrame,
    EndFrame,
    ErrorFrame,
    Frame,
    InterruptionFrame,
    VqlLLMTextFrame,
    VqlUserTextFrame,
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

    async def close(self) -> None:
        self.closed = True


def _build(
    *, normal_max: int = DEFAULT_NORMAL_MAXSIZE, on_frame: FrameHook | None = None
) -> tuple[SessionRunner, Recorder, FakeHost]:
    host = FakeHost()
    holder: dict[str, Recorder] = {}

    def factory(emitter: Emitter) -> SessionAdapter:
        adapter = Recorder(emitter, on_frame)
        holder["adapter"] = adapter
        return adapter

    runner = SessionRunner(session_id=SID, factory=factory, host=host, normal_max=normal_max)
    return runner, holder["adapter"], host


async def _until(predicate, *, timeout: float = 2.0, interval: float = 0.005) -> None:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(interval)
    raise AssertionError(f"timeout waiting for {predicate}")


# ─── Inbound: system lane priority ───────────────────────────────────────────


async def test_system_lane_dispatched_before_normal() -> None:
    runner, adapter, _host = _build(normal_max=64)
    # Enqueue three normal frames, then one system frame, all before the feeder
    # starts — so the feeder's first pop must choose the system lane.
    runner.enqueue_inbound(VqlUserTextFrame(interaction_id=1, text="a"))
    runner.enqueue_inbound(VqlUserTextFrame(interaction_id=1, text="b"))
    runner.enqueue_inbound(VqlUserTextFrame(interaction_id=1, text="c"))
    runner.enqueue_inbound(InterruptionFrame())  # system lane
    runner.start()
    try:
        await _until(lambda: len(adapter.received) == 4)
        assert isinstance(adapter.received[0], InterruptionFrame), (
            f"system lane must come first; got {type(adapter.received[0]).__name__}"
        )
        texts = [f.text for f in adapter.received[1:] if isinstance(f, VqlUserTextFrame)]
        assert texts == ["a", "b", "c"]
    finally:
        await runner.cancel()


# ─── Inbound: drop-newest + congestion ErrorFrame ────────────────────────────


async def test_inbound_normal_lane_drops_newest_and_signals_error() -> None:
    runner, adapter, _host = _build(normal_max=4)
    for i in range(8):
        runner.enqueue_inbound(VqlUserTextFrame(interaction_id=i, text=f"f{i}"))
    # First 4 kept, remaining 4 dropped (drop-newest) — all before the feeder ran.
    assert runner._in.depth() == 4
    runner.start()
    try:
        # The four survivors are the FIRST four, and a single non-fatal
        # ErrorFrame is delivered to the adapter about the congestion.
        await _until(lambda: any(isinstance(f, ErrorFrame) for f in adapter.received))
        texts = [f.text for f in adapter.received if isinstance(f, VqlUserTextFrame)]
        assert texts == ["f0", "f1", "f2", "f3"]
        errs = [f for f in adapter.received if isinstance(f, ErrorFrame)]
        assert len(errs) == 1
        assert not errs[0].fatal
        assert "inbound queue full" in errs[0].error
    finally:
        await runner.cancel()


# ─── Ack emitted after handle_frame returns ──────────────────────────────────


async def test_ack_enqueued_after_handle_frame() -> None:
    runner, adapter, host = _build()
    runner.enqueue_inbound(VqlUserTextFrame(interaction_id=1, text="x"), request_id=42)
    runner.start()
    try:
        await _until(lambda: adapter.received and not runner.out_empty())
        item = runner.pop_out()
        assert isinstance(item, _Ack)
        assert item.ack_id == 42
        assert host.ready_signals >= 1
    finally:
        await runner.cancel()


# ─── Outbound: drop-newest + congestion ErrorFrame ───────────────────────────


async def test_outbound_overflow_delivers_error_frame() -> None:
    async def flood(frame: Frame, adapter: Recorder) -> None:
        if isinstance(frame, VqlUserTextFrame):
            # Tight synchronous burst; nobody pops the outbound lane in this
            # unit test, so it overflows past normal_max and drops newest.
            for i in range(64):
                adapter.emitter.send(
                    VqlLLMTextFrame(interaction_id=1, inference_id=1, text=f"c{i}")
                )

    runner, adapter, host = _build(normal_max=4, on_frame=flood)
    runner.enqueue_inbound(VqlUserTextFrame(interaction_id=1, text="go"))
    runner.start()
    try:
        await _until(lambda: any(isinstance(f, ErrorFrame) for f in adapter.received))
        errs = [f for f in adapter.received if isinstance(f, ErrorFrame)]
        assert not errs[0].fatal
        assert "outbound queue full" in errs[0].error
        # The runner never kills the session on a drop.
        assert host.closed == []
    finally:
        await runner.cancel()


# ─── Outbound: system frame jumps ahead of queued normal frames ──────────────


async def test_outbound_system_frame_pops_first() -> None:
    async def emit_mix(frame: Frame, adapter: Recorder) -> None:
        if isinstance(frame, VqlUserTextFrame):
            for i in range(3):
                adapter.emitter.send(
                    VqlLLMTextFrame(interaction_id=1, inference_id=1, text=f"n{i}")
                )
            adapter.emitter.send(CancelFrame())  # system lane

    runner, _adapter, _host = _build(normal_max=64, on_frame=emit_mix)
    runner.enqueue_inbound(VqlUserTextFrame(interaction_id=1, text="go"))
    runner.start()
    try:
        await _until(lambda: runner._out.depth() == 4)
        first = runner.pop_out()
        assert isinstance(first, CancelFrame), (
            f"system lane must pop first; got {type(first).__name__}"
        )
    finally:
        await runner.cancel()


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
    assert DEFAULT_NORMAL_MAXSIZE > 0
    assert DEFAULT_SYSTEM_MAXSIZE > 0
