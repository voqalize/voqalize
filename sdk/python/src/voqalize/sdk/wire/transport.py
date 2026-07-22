"""Websocket transport for the cortex wire.

Two wire shapes, one connection class:

  `Wire`              — single-session connection. PyGato has its own copy at
                        `pygato/src/pygato/wire/transport.py`; this one stays
                        here for symmetry and for in-SDK single-session uses.
                        Message format: `[1-byte direction][protobuf payload]`.

  `MultiplexedWire`   — used by the agent SDK (`/agent` endpoint).
                        Message format: `[16-byte session_id][1-byte direction][protobuf payload]`.
                        The 16-byte prefix matches cortex's `protocol.SessionIDLen`
                        spec (see `cortex/internal/protocol/protocol.go`).

Both share connect/reconnect/close machinery via the `_Connection` base.

Reconnect lives here. Each leg instantiates its own wire against its cortex URL;
cortex itself is byte-opaque, so each side reconnects independently of the other.

Close code semantics (matches existing cortex contract):
  - 4000 (NoAgent)        → PermanentClose, never retry
  - 4001 (AgentGone)      → transient, reconnect with backoff
  - anything else         → transient, reconnect with backoff
  - 1000 from us (close()) → no reconnect

After each successful reconnect, the optional `on_reconnect` callback fires so
the consumer can re-establish session state (e.g. re-send VqlStartFrame).
"""

from __future__ import annotations

import asyncio
import contextlib
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import websockets
from loguru import logger
from websockets.asyncio.client import ClientConnection
from websockets.exceptions import ConnectionClosed

from .frames import FrameDirection

CLOSE_NO_AGENT = 4000  # permanent
CLOSE_AGENT_GONE = 4001  # transient

# Length of the session-id prefix on the multiplexed `/agent` leg.
SESSION_ID_LEN = 16


class PermanentClose(Exception):
    """Raised by send/recv/start when cortex returned a non-retriable close."""

    def __init__(self, code: int, reason: str = ""):
        super().__init__(f"cortex permanently closed: code={code} reason={reason!r}")
        self.code = code
        self.reason = reason


class WireClosed(Exception):
    """Raised by send/recv after the consumer called close()."""


@dataclass
class WireConfig:
    url: str
    initial_backoff_seconds: float = 0.1
    max_backoff_seconds: float = 60.0
    backoff_multiplier: float = 2.0
    backoff_jitter: float = 0.1  # ± fraction of current delay
    connect_timeout: float = 10.0
    headers: dict[str, str] | None = None
    # Called on every connect attempt so callers can rotate short-lived tokens.
    # Returns a dict merged on top of ``headers`` for that attempt only.
    headers_provider: Callable[[], dict[str, str]] | None = None


OnReconnect = Callable[[], Awaitable[None]]


class _Connection:
    """Connect/reconnect/close machinery shared by both wire shapes.

    Subclasses add framing (`send` / `recv`) on top of `_raw_send` / `_raw_recv`.
    """

    def __init__(
        self,
        config: WireConfig,
        on_reconnect: OnReconnect | None = None,
    ) -> None:
        self._config = config
        self._on_reconnect = on_reconnect
        self._ws: ClientConnection | None = None
        self._connected = asyncio.Event()
        self._closed_by_user = False
        self._permanent_error: PermanentClose | None = None
        self._send_lock = asyncio.Lock()

    async def start(self) -> None:
        """Establish the first connection. Blocks until success or PermanentClose."""
        await self._reconnect_loop(is_first=True)

    async def close(self, code: int = 1000) -> None:
        """Close gracefully. No further reconnect attempts."""
        self._closed_by_user = True
        self._connected.clear()
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.close(code=code)
            self._ws = None

    async def _raw_send(self, payload: bytes) -> None:
        async with self._send_lock:
            while True:
                self._raise_if_terminal()
                await self._connected.wait()
                ws = self._ws
                if ws is None:
                    continue
                try:
                    await ws.send(payload)
                    return
                except ConnectionClosed as exc:
                    await self._handle_disconnect(exc)

    async def _raw_recv(self) -> bytes:
        while True:
            self._raise_if_terminal()
            await self._connected.wait()
            ws = self._ws
            if ws is None:
                continue
            try:
                msg = await ws.recv()
            except ConnectionClosed as exc:
                await self._handle_disconnect(exc)
                continue

            if isinstance(msg, str):
                raise ValueError("wire received TEXT websocket frame; expected BINARY")
            return msg

    # ─── Internals ─────────────────────────────────────────────────────

    def _raise_if_terminal(self) -> None:
        if self._permanent_error is not None:
            raise self._permanent_error
        if self._closed_by_user:
            raise WireClosed("Wire was closed by caller")

    async def _handle_disconnect(self, exc: ConnectionClosed) -> None:
        """React to a closed socket. Sets permanent error or kicks off reconnect."""
        self._connected.clear()
        self._ws = None

        code = exc.rcvd.code if exc.rcvd else None
        reason = exc.rcvd.reason if exc.rcvd else ""
        logger.info(f"wire: connection closed code={code} reason={reason!r}")

        if self._closed_by_user:
            return

        if code == CLOSE_NO_AGENT:
            self._permanent_error = PermanentClose(code, reason)
            return

        await self._reconnect_loop(is_first=False)

    async def _reconnect_loop(self, *, is_first: bool) -> None:
        """Run until we either connect, fail permanently, or are closed."""
        delay = self._config.initial_backoff_seconds
        attempt = 0
        while True:
            if self._closed_by_user:
                return
            if self._permanent_error is not None:
                return

            attempt += 1
            headers = dict(self._config.headers or {})
            if self._config.headers_provider is not None:
                headers.update(self._config.headers_provider())
            try:
                ws = await asyncio.wait_for(
                    websockets.connect(
                        self._config.url,
                        additional_headers=headers or None,
                    ),
                    timeout=self._config.connect_timeout,
                )
            except Exception as exc:
                code = self._extract_close_code(exc)
                if code == CLOSE_NO_AGENT:
                    self._permanent_error = PermanentClose(code)
                    return
                logger.warning(
                    f"wire: connect attempt {attempt} failed ({exc!r}); retrying in {delay:.2f}s"
                )
                await asyncio.sleep(self._jitter(delay))
                delay = min(
                    delay * self._config.backoff_multiplier,
                    self._config.max_backoff_seconds,
                )
                continue

            self._ws = ws
            self._connected.set()
            logger.info(
                f"wire: connected to {self._config.url} (attempt {attempt}, first={is_first})"
            )

            if not is_first and self._on_reconnect is not None:
                try:
                    await self._on_reconnect()
                except Exception:
                    logger.exception("wire: on_reconnect callback raised")
            return

    def _jitter(self, delay: float) -> float:
        jit = self._config.backoff_jitter
        if jit <= 0:
            return delay
        return delay * (1.0 + random.uniform(-jit, jit))

    @staticmethod
    def _extract_close_code(exc: Exception) -> int | None:
        rcvd = getattr(exc, "rcvd", None)
        return rcvd.code if rcvd is not None else None


class Wire(_Connection):
    """Pygato leg of the cortex wire.

    Message format: `[1-byte direction][payload bytes]`. No session prefix —
    pygato connects to `/s/{session_id}` so the session is implicit in the URL.
    """

    async def send(self, direction: FrameDirection, payload: bytes) -> None:
        """Send one binary message: [direction_byte] + payload."""
        await self._raw_send(bytes([direction.value]) + payload)

    async def recv(self) -> tuple[FrameDirection, bytes]:
        """Receive one binary message; return (direction, payload)."""
        msg = await self._raw_recv()
        if len(msg) < 1:
            raise ValueError("wire received empty websocket message")
        return FrameDirection(int(msg[0])), bytes(msg[1:])


class MultiplexedWire(_Connection):
    """Agent leg of the cortex wire.

    Message format: `[16-byte session_id][1-byte direction][payload bytes]`.
    Mirrors `protocol.SessionIDLen` in cortex/internal/protocol — cortex itself
    inserts the session-id prefix on this leg.
    """

    async def send(self, session_id: bytes, direction: FrameDirection, payload: bytes) -> None:
        """Send `[session_id 16B][direction 1B][payload]`."""
        if len(session_id) != SESSION_ID_LEN:
            raise ValueError(
                f"session_id must be exactly {SESSION_ID_LEN} bytes, got {len(session_id)}"
            )
        await self._raw_send(session_id + bytes([direction.value]) + payload)

    async def recv(self) -> tuple[bytes, FrameDirection, bytes]:
        """Receive `[session_id 16B][direction 1B][payload]`."""
        msg = await self._raw_recv()
        if len(msg) < SESSION_ID_LEN + 1:
            raise ValueError(
                f"multiplexed wire received short message ({len(msg)} bytes); "
                f"need at least {SESSION_ID_LEN + 1}"
            )
        sid = bytes(msg[:SESSION_ID_LEN])
        direction = FrameDirection(int(msg[SESSION_ID_LEN]))
        payload = bytes(msg[SESSION_ID_LEN + 1 :])
        return sid, direction, payload
