"""Shared helpers for cortex agent-sdk tests.

Pipecat-free. The SDK exposes no raw ``FrameProcessor`` customer path anymore, so
these tests drive the per-session engine either through a small
:class:`RecordingAdapter` (implements
:class:`~voqalize.sdk.engine.SessionAdapter`) or through a ``Brain`` subclass.
The runner dispatches each inbound frame to ``handle_frame`` serially, so a
recording adapter observes exactly the order the engine delivers.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from voqalize.sdk.engine import Emitter, SessionAdapter
from voqalize.sdk.wire import Frame, ResponseFrame

FrameHook = Callable[[Frame, "RecordingAdapter"], Awaitable[None]]


class RecordingAdapter(SessionAdapter):
    """A minimal :class:`SessionAdapter` that records every frame the runner
    dispatches. Forwards nothing (there is no downstream); it may emit its own
    frames via ``self.emitter``.

    An optional async ``on_frame(frame, self)`` hook fires for each frame after
    recording — the engine-level analogue of a pipecat ``process_frame``
    override.
    """

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
        # No request ever leaves a recording adapter, so an answer to one is
        # just another frame to record.
        self.received.append(frame)

    async def close(self) -> None:
        self.closed = True


async def wait_for(predicate, *, timeout: float = 2.0, interval: float = 0.01) -> None:
    """Poll until ``predicate()`` returns truthy or the timeout fires."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(interval)
    raise AssertionError(f"timeout waiting for {predicate}")
