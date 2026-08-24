"""Per-session runtime engine — pipecat-free.

One :class:`SessionRunner` per session. It owns the two-lane inbound buffer, the
two-lane outbound buffer, the feeder loop that dispatches frames to the session
adapter. The *same* runner drives both transports (the outbound Cortex relay and
the inbound direct server), which differ only in the small :class:`RunnerHost`
seam (who signals the writer and who tears the session down).

Design:

- **Two lanes each way.** Session control — ``SessionStart`` / ``Interruption`` /
  ``Cancel``, see :func:`~voqalize.sdk.wire.frames.is_priority` — rides a priority
  lane that bypasses queued data. Nothing on it has an ordering relationship with
  what it overtakes. ``End`` is *not* priority: it rides the bulk lane so a
  session tears down only after its queued data drains.
- **Backpressure sheds only the unbounded flows.** The bulk lane is bounded, and
  a full lane drops a newly arriving speech chunk or RTVI message — see
  :func:`~voqalize.sdk.wire.frames.is_droppable`. Everything else is bounded by
  turns taken and units spoken, so it queues however deep the backlog runs. A
  drop delivers a non-fatal ``ErrorFrame`` to the adapter, edge-triggered: one
  per congestion episode per direction. The runner never kills a session.
- **One sequential consumer.** The feeder below takes frames off the inbound
  lanes one at a time and awaits ``adapter.handle_frame`` on each, so the adapter
  sees frames in wire order. A slow callback delays the *callbacks* behind it and
  nothing else — it never reaches back across the wire.
- **A ``Response`` bypasses the lanes entirely.** It is an answer, not a
  stimulus: it has exactly one consumer — the caller blocked on it — and no
  ordering against speech or user messages. Queueing it behind the feeder would
  deadlock every request made from a callback, because the feeder is inside the
  very callback that is awaiting it.
- **Interruption** is handled in the *adapter*, which holds the watermark; the
  runner only guarantees it is dispatched ahead of queued data.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from loguru import logger

from .wire import CancelFrame, EndFrame, ErrorCode, ErrorFrame, Frame, ResponseFrame
from .wire.frames import is_droppable, is_priority

DEFAULT_BULK_MAXSIZE = 256
DEFAULT_PRIORITY_MAXSIZE = 32  # tripwire; never expected to fill
_LOW_WATERMARK_FRAC = 0.5


# ─── Seams ────────────────────────────────────────────────────────────────────


class Emitter(Protocol):
    """What a session adapter uses to send frames back toward the wire.

    Non-blocking: enqueues onto the runner's outbound lanes. Implemented by
    :class:`SessionRunner`.
    """

    def send(self, frame: Frame) -> None: ...


class SessionAdapter(Protocol):
    """The brain-side of one session (implemented by ``brain._BrainAdapter``).

    ``handle_frame`` is dispatched sequentially by the feeder, priority lane
    first. It may emit frames synchronously via the :class:`Emitter` it was built
    with, and it may spawn its own tasks (e.g. ``on_user_message``).
    ``settle_response`` is called straight off the reader instead, and must not
    block. ``close`` runs session teardown (``on_session_end``).
    """

    async def handle_frame(self, frame: Frame) -> None: ...

    def settle_response(self, frame: ResponseFrame) -> None: ...

    async def close(self) -> None: ...


# A factory builds the adapter for one session, wired to the runner's Emitter.
# The session id itself arrives inside the SessionStart frame, so it isn't a
# parameter here (matches the Brain surface, where Session.id = frame.session_id).
SessionFactory = Callable[["Emitter"], SessionAdapter]


class RunnerHost(Protocol):
    """The per-transport seam. Everything else about a session is transport-neutral.

    * ``signal_ready`` — the runner's outbound lanes went empty→non-empty; the
      host's writer should drain them (direct: set a per-conn event; cortex: push
      the sid onto the shared fair-writer queue).
    * ``close_session`` — the session ended (End drained, or teardown); the host
      forgets the runner.
    """

    def signal_ready(self, runner: SessionRunner) -> None: ...

    def close_session(self, runner: SessionRunner) -> None: ...


# ─── Lane container ───────────────────────────────────────────────────────────


@dataclass
class _Lanes:
    """Priority (bypasses queued data) + bulk (bounded, sheds droppable frames)."""

    priority_max: int
    bulk_max: int
    label: str
    priority: deque[Frame] = field(default_factory=deque)
    bulk: deque[Frame] = field(default_factory=deque)

    def put(self, frame: Frame) -> bool:
        """Queue a frame. False means it was shed under backpressure."""
        if is_priority(frame):
            if len(self.priority) >= self.priority_max:
                raise RuntimeError(
                    f"{self.label} priority lane overflow at {self.priority_max} — bug"
                )
            self.priority.append(frame)
            return True
        if len(self.bulk) >= self.bulk_max and is_droppable(frame):
            return False
        self.bulk.append(frame)
        return True

    def pop(self) -> Frame | None:
        if self.priority:
            return self.priority.popleft()
        if self.bulk:
            return self.bulk.popleft()
        return None

    def empty(self) -> bool:
        return not self.priority and not self.bulk

    def depth(self) -> int:
        return len(self.priority) + len(self.bulk)


@dataclass
class _InLanes(_Lanes):
    """Inbound lanes, with the single consumer's readiness event."""

    ready: asyncio.Event = field(default_factory=asyncio.Event)

    def put(self, frame: Frame) -> bool:
        queued = super().put(frame)
        if queued:
            self.ready.set()
        return queued

    async def get(self) -> Frame:
        while True:
            frame = self.pop()
            if frame is None:
                self.ready.clear()
                await self.ready.wait()
                continue
            if self.empty():
                self.ready.clear()
            return frame


# ─── SessionRunner ────────────────────────────────────────────────────────────


class SessionRunner:
    """One per session_id. Owns the lanes, the feeder, and outbound emission."""

    def __init__(
        self,
        *,
        session_id: bytes,
        factory: SessionFactory,
        host: RunnerHost,
        bulk_max: int = DEFAULT_BULK_MAXSIZE,
        priority_max: int = DEFAULT_PRIORITY_MAXSIZE,
    ) -> None:
        self.session_id = session_id
        self._host = host
        self._in = _InLanes(priority_max=priority_max, bulk_max=bulk_max, label="inbound")
        self._out = _Lanes(priority_max=priority_max, bulk_max=bulk_max, label="outbound")
        self._low_watermark = max(1, int(bulk_max * _LOW_WATERMARK_FRAC))

        # Build the adapter last — it captures ``self`` as its Emitter.
        self._adapter: SessionAdapter = factory(self)

        self._feeder_task: asyncio.Task[None] | None = None
        self._error_pump_task: asyncio.Task[None] | None = None
        self._error_events: asyncio.Queue[str] = asyncio.Queue()

        # Edge-triggered congestion flags (avoid ErrorFrame spam).
        self._inbound_congested = False
        self._outbound_congested = False
        self._closed = False

    # ─── Lifecycle ──────────────────────────────────────────────────────

    def start(self) -> None:
        self._feeder_task = asyncio.create_task(
            self._feed(), name=f"session-feeder-{self.session_id.hex()[:8]}"
        )
        self._error_pump_task = asyncio.create_task(
            self._error_pump(), name=f"session-errpump-{self.session_id.hex()[:8]}"
        )

    async def cancel(self) -> None:
        """Abrupt teardown (reconnect / shutdown)."""
        await self._teardown(notify_host=False)

    # ─── Inbound (called by the transport reader) ───────────────────────

    def enqueue_inbound(self, frame: Frame) -> None:
        if isinstance(frame, ResponseFrame):
            self._adapter.settle_response(frame)
            return
        if not self._in.put(frame):
            self._notify_inbound_drop()

    # ─── Outbound (Emitter, called by the adapter) ──────────────────────

    def send(self, frame: Frame) -> None:
        was_empty = self._out.empty()
        if not self._out.put(frame):
            self._notify_outbound_drop()
            return
        if was_empty:
            self._host.signal_ready(self)

    def pop_out(self) -> Frame | None:
        frame = self._out.pop()
        # Outbound drained: re-check the edge-triggered flag so an outbound-heavy
        # session with no inbound traffic can still clear.
        if self._outbound_congested and self._out.depth() <= self._low_watermark:
            self._outbound_congested = False
        return frame

    def out_empty(self) -> bool:
        return self._out.empty()

    # ─── Feeder ─────────────────────────────────────────────────────────

    async def _feed(self) -> None:
        ended = False
        try:
            while True:
                frame = await self._in.get()
                try:
                    await self._adapter.handle_frame(frame)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception(
                        "session: adapter.handle_frame failed for {}", type(frame).__name__
                    )
                if self._inbound_congested and self._in.depth() <= self._low_watermark:
                    self._inbound_congested = False
                # Both are terminal. The difference is the lane they rode in
                # on: `Cancel` bypassed whatever was queued, `End` drained
                # behind it.
                if isinstance(frame, EndFrame | CancelFrame):
                    ended = True
                    break
        except asyncio.CancelledError:
            raise
        finally:
            if ended:
                await self._teardown(notify_host=True)

    # ─── Congestion → ErrorFrame (edge-triggered) ───────────────────────

    def _notify_inbound_drop(self) -> None:
        if not self._inbound_congested:
            self._inbound_congested = True
            self._error_events.put_nowait(
                "voqalize: inbound queue full; dropping data frames until consumer catches up"
            )

    def _notify_outbound_drop(self) -> None:
        if not self._outbound_congested:
            self._outbound_congested = True
            self._error_events.put_nowait(
                "voqalize: outbound queue full; dropping data frames until wire catches up"
            )

    async def _error_pump(self) -> None:
        while True:
            message = await self._error_events.get()
            try:
                await self._adapter.handle_frame(
                    ErrorFrame(code=ErrorCode.OVERLOAD, message=message, fatal=False)
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("session: delivering congestion ErrorFrame failed")

    # ─── Teardown ───────────────────────────────────────────────────────

    async def _teardown(self, *, notify_host: bool) -> None:
        if self._closed:
            return
        self._closed = True
        for task in (self._feeder_task, self._error_pump_task):
            if task is not None and not task.done() and task is not asyncio.current_task():
                task.cancel()
        with contextlib.suppress(Exception):
            await self._adapter.close()
        for task in (self._feeder_task, self._error_pump_task):
            if task is None or task is asyncio.current_task():
                continue
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        if notify_host:
            try:
                self._host.close_session(self)
            except Exception:
                logger.exception("session: host.close_session raised")
