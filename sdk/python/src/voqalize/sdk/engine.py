"""Per-session runtime engine — pipecat-free.

One :class:`SessionRunner` per session. It owns the two-lane inbound buffer, the
two-lane outbound buffer, the feeder loop that dispatches frames to the session
adapter, and ack-gating. The *same* runner drives both transports (the outbound
Cortex relay and the inbound direct server), which differ only in the small
:class:`RunnerHost` seam (who signals the writer and who tears the session down).

Design (identical to the previous pipecat-pipeline version, minus pipecat):

- **Two lanes each way.** System frames (``SessionStart`` / ``Interruption`` / ``Cancel``
  — see :func:`~voqalize.sdk.wire.is_system`) ride a priority lane that bypasses
  queued data; everything else rides a bounded normal lane with **drop-newest**
  semantics. ``End`` is *not* system — it rides the normal lane so a session tears
  down only after its queued data drains.
- **Ack-gating.** For any inbound envelope carrying ``request_id > 0``, the runner
  emits an ``Ack`` envelope the moment the frame is **taken off the inbound lane**,
  before ``adapter.handle_frame`` runs. The ack answers "this frame is committed to
  the ordered lane", not "the brain finished thinking about it" — and that is
  exactly the fact PyGato's ``_send_and_await_ack`` needs, because the feeder below
  is a single sequential consumer, so ordering into the adapter is already
  guaranteed at dequeue time.

  Acking *after* the handler would make the ack mean "handled", which welds
  brain-side compute onto PyGato's pipeline: an ``on_inference_finalized`` doing a
  database write parks ``__process_queue`` for the whole write, and the *next* user
  utterance — queued behind it in the same direction-agnostic queue — goes out late
  by exactly that much. That costs a real call about two seconds a turn, and it is
  invisible, because the delay lands on PyGato's transmit lane where no timer is
  watching. A slow callback delays the *callbacks* behind it (they are one ordered
  lane by design) and nothing else.
- **Backpressure.** Normal-lane overflow drops the newest frame and delivers a
  non-fatal ``ErrorFrame`` to the adapter (edge-triggered: one per congestion
  episode per direction). The runner never kills a session.
- **Interruption** is handled in the *adapter* (cancel in-flight + echo the drain
  barrier); the runner only guarantees the ``Interruption`` is dispatched ahead of
  queued data via the system lane.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from loguru import logger

from .wire import EndFrame, ErrorFrame, Frame, FrameDirection, is_system

DEFAULT_NORMAL_MAXSIZE = 256
DEFAULT_SYSTEM_MAXSIZE = 32  # tripwire; never expected to fill
_LOW_WATERMARK_FRAC = 0.5

# Every brain→wire frame is sent DOWNSTREAM (1); PyGato flips ui_command to
# UPSTREAM on its own read.
OUT_DIRECTION = FrameDirection.DOWNSTREAM


# ─── The unit that moves ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class Envelope:
    """A frame plus the wire correlation that travels beside it.

    ``epoch`` is minted by the voice runtime and echoed back unread; the runner
    and the adapter only carry it. ``inference_id`` is minted per model call by
    whichever side opens the inference.
    """

    frame: Frame
    request_id: int = 0
    epoch: int = 0
    inference_id: int = 0


# ─── Seams ────────────────────────────────────────────────────────────────────


class Emitter(Protocol):
    """What a session adapter uses to send frames back toward the wire.

    Non-blocking: enqueues onto the runner's outbound lanes. Implemented by
    :class:`SessionRunner`.
    """

    def send(self, frame: Frame, *, epoch: int = 0, inference_id: int = 0) -> None: ...


class SessionAdapter(Protocol):
    """The brain-side of one session (implemented by ``brain._BrainAdapter``).

    ``handle_frame`` is dispatched sequentially by the feeder, system-lane first.
    It may emit frames synchronously via the :class:`Emitter` it was built with,
    and it may spawn its own tasks (e.g. ``on_interaction``). ``close`` runs
    session teardown (``on_session_end``).
    """

    async def handle_frame(self, env: Envelope) -> None: ...

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


@dataclass
class _Ack:
    """Outbound marker: emit an ``Ack(ack_id)`` envelope. Never dropped."""

    ack_id: int


OutItem = Envelope | _Ack


# ─── Lane containers ──────────────────────────────────────────────────────────


@dataclass
class _InLanes:
    """Inbound: system (priority) + normal (bounded, drop-newest), one consumer."""

    system_max: int
    normal_max: int
    system: deque[Envelope] = field(default_factory=deque)
    normal: deque[Envelope] = field(default_factory=deque)
    ready: asyncio.Event = field(default_factory=asyncio.Event)

    def put_system(self, item: Envelope) -> None:
        if len(self.system) >= self.system_max:
            raise RuntimeError(f"inbound system lane overflow at {self.system_max} — bug")
        self.system.append(item)
        self.ready.set()

    def put_normal(self, item: Envelope) -> bool:
        if len(self.normal) >= self.normal_max:
            return False
        self.normal.append(item)
        self.ready.set()
        return True

    async def get(self) -> Envelope:
        while True:
            if self.system:
                item = self.system.popleft()
            elif self.normal:
                item = self.normal.popleft()
            else:
                self.ready.clear()
                await self.ready.wait()
                continue
            if not self.system and not self.normal:
                self.ready.clear()
            return item

    def depth(self) -> int:
        return len(self.system) + len(self.normal)


@dataclass
class _OutLanes:
    """Outbound: system (Interruption echo) + normal (Envelope | _Ack)."""

    system_max: int
    normal_max: int
    system: deque[OutItem] = field(default_factory=deque)
    normal: deque[OutItem] = field(default_factory=deque)

    def put_system(self, item: OutItem) -> None:
        if len(self.system) >= self.system_max:
            raise RuntimeError(f"outbound system lane overflow at {self.system_max} — bug")
        self.system.append(item)

    def put_normal(self, item: OutItem) -> bool:
        if len(self.normal) >= self.normal_max:
            return False
        self.normal.append(item)
        return True

    def append_ack(self, item: _Ack) -> None:
        # Acks bypass the bound: a dropped ack hangs the bridge. They stay in the
        # normal lane so they FIFO with the session's own frames rather than
        # overtaking them on the system lane.
        self.normal.append(item)

    def pop(self) -> OutItem | None:
        if self.system:
            return self.system.popleft()
        if self.normal:
            return self.normal.popleft()
        return None

    def empty(self) -> bool:
        return not self.system and not self.normal

    def depth(self) -> int:
        return len(self.system) + len(self.normal)


# ─── SessionRunner ────────────────────────────────────────────────────────────


class SessionRunner:
    """One per session_id. Owns the lanes, the feeder, and outbound emission."""

    def __init__(
        self,
        *,
        session_id: bytes,
        factory: SessionFactory,
        host: RunnerHost,
        normal_max: int = DEFAULT_NORMAL_MAXSIZE,
        system_max: int = DEFAULT_SYSTEM_MAXSIZE,
    ) -> None:
        self.session_id = session_id
        self._host = host
        self._in = _InLanes(system_max=system_max, normal_max=normal_max)
        self._out = _OutLanes(system_max=system_max, normal_max=normal_max)
        self._low_watermark = max(1, int(normal_max * _LOW_WATERMARK_FRAC))

        # Build the adapter last — it captures ``self`` as its Emitter.
        self._adapter: SessionAdapter = factory(self)

        self._feeder_task: asyncio.Task[None] | None = None
        self._error_pump_task: asyncio.Task[None] | None = None
        self._error_events: asyncio.Queue[tuple[FrameDirection, str]] = asyncio.Queue()

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

    def enqueue_inbound(self, env: Envelope) -> None:
        if is_system(env.frame):
            self._in.put_system(env)
        elif not self._in.put_normal(env):
            self._notify_inbound_drop()

    # ─── Outbound (Emitter, called by the adapter) ──────────────────────

    def send(self, frame: Frame, *, epoch: int = 0, inference_id: int = 0) -> None:
        env = Envelope(frame=frame, epoch=epoch, inference_id=inference_id)
        was_empty = self._out.empty()
        if is_system(frame):
            self._out.put_system(env)
        elif not self._out.put_normal(env):
            self._notify_outbound_drop()
            return
        if was_empty:
            self._host.signal_ready(self)

    def _enqueue_ack(self, ack_id: int) -> None:
        was_empty = self._out.empty()
        self._out.append_ack(_Ack(ack_id))
        if was_empty:
            self._host.signal_ready(self)

    def pop_out(self) -> OutItem | None:
        item = self._out.pop()
        # Outbound drained: re-check the edge-triggered flag so an outbound-heavy
        # session with no inbound traffic can still clear.
        if self._outbound_congested and self._out.depth() <= self._low_watermark:
            self._outbound_congested = False
        return item

    def out_empty(self) -> bool:
        return self._out.empty()

    # ─── Feeder ─────────────────────────────────────────────────────────

    async def _feed(self) -> None:
        ended = False
        try:
            while True:
                env = await self._in.get()
                # Ack first: the frame is now committed to this single sequential
                # consumer, which is the whole of what the ack promises. Waiting
                # until `handle_frame` returns would put the customer's callback
                # on PyGato's critical path — see the module docstring.
                if env.request_id:
                    self._enqueue_ack(env.request_id)
                try:
                    await self._adapter.handle_frame(env)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception(
                        "session: adapter.handle_frame failed for {}", type(env.frame).__name__
                    )
                if self._inbound_congested and self._in.depth() <= self._low_watermark:
                    self._inbound_congested = False
                if isinstance(env.frame, EndFrame):
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
                (
                    FrameDirection.DOWNSTREAM,
                    "voqalize: inbound queue full; dropping data frames until consumer catches up",
                )
            )

    def _notify_outbound_drop(self) -> None:
        if not self._outbound_congested:
            self._outbound_congested = True
            self._error_events.put_nowait(
                (
                    FrameDirection.UPSTREAM,
                    "voqalize: outbound queue full; dropping data frames until wire catches up",
                )
            )

    async def _error_pump(self) -> None:
        while True:
            _direction, message = await self._error_events.get()
            try:
                await self._adapter.handle_frame(
                    Envelope(frame=ErrorFrame(error=message, fatal=False))
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
