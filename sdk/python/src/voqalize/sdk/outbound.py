"""CortexAgent — the multiplexed agent SDK runtime (optional Cortex-relay path).

One agent process holds one **outbound** WebSocket to Cortex's ``/agent``
endpoint. Many sessions ride that single connection, demuxed by a 16-byte raw
UUID prefix on every message, which the relay inserts and strips.
This is the path for brains that cannot accept an inbound connection (serverless,
laptops, strict egress-only networks); when the application owns a WebSocket route
it uses :func:`voqalize.sdk.run_session` there instead.

The customer writes a :class:`~voqalize.sdk.brain.Brain`; the same Brain runs
unchanged on either transport. Both hand a
:data:`~voqalize.sdk.engine.SessionFactory` to the runtime; the only difference
is who dials whom.

Per-session guarantees, by construction:

1. **Session isolation.** Each session_id gets its own
   :class:`~voqalize.sdk.engine.SessionRunner`; the Brain adapter has no path
   to any other session's runner. Cross-session writes are unreachable.
2. **Fresh state per session.** ``factory`` is invoked anew for every session.
3. **Fairness.** A slow session's inbound backlog can't stall the wire reader
   (per-session lanes); a talkative session can't starve quiet ones outbound
   (the shared writer round-robins via the ready queue). On overflow: drop newest
   + a non-fatal ``ErrorFrame`` to the affected session — never a kill.
4. **Interruption** rides the wire as an ``InterruptionFrame`` naming the turn it
   condemns (system lane), dispatched ahead of queued data; the adapter raises
   the session's watermark and cancels in-flight work. Nothing goes back.
5. **Reconnect** (via ``MultiplexedWire``): on reconnect all sessions are torn
   down; Voqalize re-sends each ``SessionStartFrame``, creating fresh runners.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import Callable

from loguru import logger

from ._logging import session_context
from .engine import (
    DEFAULT_BULK_MAXSIZE,
    RunnerHost,
    SessionFactory,
    SessionRunner,
)
from .wire import (
    MalformedFrameError,
    MultiplexedWire,
    PermanentClose,
    SessionStartFrame,
    WireClosed,
    WireConfig,
    WireSerializer,
)


class CortexAgent(RunnerHost):
    """Connects to Cortex ``/agent``, demuxes per-session frames into one
    :class:`SessionRunner` each, and drains all sessions over one fair writer."""

    def __init__(
        self,
        *,
        version: str,
        cortex_url: str,
        factory: SessionFactory,
        api_key: str | None = None,
        authorization_provider: Callable[[], str] | None = None,
        inbound_queue_maxsize: int | None = None,
    ) -> None:
        # Exactly one auth source: a static sk_… (customer agents) OR a callable
        # that mints a fresh ``"Bearer <jwt>"`` per connect (our own agents).
        if (api_key is None) == (authorization_provider is None):
            raise ValueError("CortexAgent: pass exactly one of api_key= or authorization_provider=")
        self._api_key = api_key
        self._authorization_provider = authorization_provider
        self._version = version
        self._cortex_url = cortex_url
        self._factory = factory
        self._serializer = WireSerializer()
        self._bulk_maxsize = inbound_queue_maxsize or DEFAULT_BULK_MAXSIZE

        self._wire: MultiplexedWire | None = None
        self._sessions: dict[bytes, SessionRunner] = {}
        # Sessions with outbound work pending. Each sid appears at most once by
        # construction (SessionRunner signals ready only on empty→non-empty).
        self._ready: asyncio.Queue[bytes] = asyncio.Queue()
        self._reader_task: asyncio.Task[None] | None = None
        self._writer_task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()
        self._permanent: PermanentClose | None = None

    @property
    def version(self) -> str:
        return self._version

    async def run(self) -> None:
        """Connect, dispatch, return when the wire closes permanently."""
        static_headers = {"X-Agent-Version": self._version}
        headers_provider = None
        if self._api_key is not None:
            static_headers["Authorization"] = f"Bearer {self._api_key}"
        else:
            provider = self._authorization_provider
            assert provider is not None
            headers_provider = lambda: {"Authorization": provider()}  # noqa: E731

        self._wire = MultiplexedWire(
            WireConfig(
                url=self._cortex_url,
                headers=static_headers,
                headers_provider=headers_provider,
            ),
            on_reconnect=self._on_reconnect,
        )
        await self._wire.start()

        self._reader_task = asyncio.create_task(self._reader_loop(), name="cortex-reader")
        self._writer_task = asyncio.create_task(self._writer_loop(), name="cortex-writer")
        try:
            stopped = asyncio.create_task(self._stopped.wait())
            reader = self._reader_task
            _done, pending = await asyncio.wait(
                {stopped, reader}, return_when=asyncio.FIRST_COMPLETED
            )
            for t in pending:
                if t is not reader:
                    t.cancel()
        finally:
            await self._stop()

        if self._permanent is not None:
            raise self._permanent
        # A reader that DIED (factory raised, framing bug, …) must surface, not
        # vanish as a clean exit-0 — the silent version cost a live debugging
        # session to even notice. CancelledError means _stop cancelled it: normal.
        if reader.done() and not reader.cancelled():
            exc = reader.exception()
            if exc is not None:
                raise exc

    # ─── RunnerHost seam ────────────────────────────────────────────────

    def signal_ready(self, runner: SessionRunner) -> None:
        self._ready.put_nowait(runner.session_id)

    def close_session(self, runner: SessionRunner) -> None:
        self._sessions.pop(runner.session_id, None)
        logger.info("cortex: closed session {}", _sid_str(runner.session_id))

    # ─── Reader / writer ────────────────────────────────────────────────

    async def _reader_loop(self) -> None:
        assert self._wire is not None
        while not self._stopped.is_set():
            try:
                sid, payload = await self._wire.recv()
            except PermanentClose as exc:
                self._permanent = exc
                return
            except WireClosed:
                return
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("cortex: wire.recv failed; stopping")
                return

            try:
                frame = await self._serializer.deserialize_message(payload)
            except MalformedFrameError:
                logger.exception("cortex: malformed payload, skipping")
                continue
            if frame is None:
                # A body this build does not know.
                continue

            runner = self._sessions.get(sid)
            if runner is None:
                if not isinstance(frame, SessionStartFrame):
                    logger.warning(
                        "cortex: dropping {} for unknown session {}",
                        type(frame).__name__,
                        _sid_str(sid),
                    )
                    continue
                runner = SessionRunner(
                    session_id=sid,
                    factory=self._factory,
                    host=self,
                    bulk_max=self._bulk_maxsize,
                )
                # `start()` inside the context, not merely the log line: the
                # tasks it creates copy the ambient context, so the brain's own
                # coroutines — which run in the feeder task — inherit the
                # session id without anything being threaded through. The relay
                # leg carries no per-session token, so the id is all there is.
                with session_context(_sid_str(sid)):
                    runner.start()
                    logger.info("cortex: opened session {}", _sid_str(sid))
                self._sessions[sid] = runner
            runner.enqueue_inbound(frame)

    async def _writer_loop(self) -> None:
        assert self._wire is not None
        while not self._stopped.is_set():
            sid = await self._ready.get()
            runner = self._sessions.get(sid)
            if runner is None:
                continue  # closed between signal and now
            out = runner.pop_out()
            if out is None:
                continue
            try:
                payload = await self._serializer.serialize(out)
            except Exception:
                logger.exception("cortex: serialize failed for session {}", _sid_str(sid))
                if not runner.out_empty():
                    self._ready.put_nowait(sid)
                continue
            try:
                await self._wire.send(sid, payload)
            except (WireClosed, PermanentClose):
                return
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("cortex: wire.send failed for session {}", _sid_str(sid))
                continue
            if not runner.out_empty():
                self._ready.put_nowait(sid)  # fair re-queue at the tail

    # ─── Reconnect / shutdown ───────────────────────────────────────────

    async def _on_reconnect(self) -> None:
        if not self._sessions:
            return
        logger.info("cortex: reconnected, tearing down {} sessions", len(self._sessions))
        runners = list(self._sessions.values())
        self._sessions.clear()
        await asyncio.gather(*(r.cancel() for r in runners), return_exceptions=True)

    async def _stop(self) -> None:
        self._stopped.set()
        for task in (self._reader_task, self._writer_task):
            if task is not None and not task.done():
                task.cancel()
        for task in (self._reader_task, self._writer_task):
            if task is None:
                continue
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        runners = list(self._sessions.values())
        self._sessions.clear()
        await asyncio.gather(*(r.cancel() for r in runners), return_exceptions=True)
        if self._wire is not None:
            with contextlib.suppress(Exception):
                await self._wire.close()
            self._wire = None

    def request_stop(self) -> None:
        """Signal the run loop to unwind. Used by tests; not the customer API."""
        self._stopped.set()


def _sid_str(session_id: bytes) -> str:
    """Render a 16-byte raw UUID as the hyphenated string for logs."""
    try:
        return str(uuid.UUID(bytes=session_id))
    except ValueError:
        return session_id.hex()
