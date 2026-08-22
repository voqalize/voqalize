"""Websocket transport for the wire.

Two wire shapes, one connection class:

  `Wire`              — one session per connection. Message format:
                        `[protobuf payload]`; the session is implicit in the
                        URL, so nothing wraps the payload.

  `MultiplexedWire`   — every session of one agent over a single connection to
                        the relay's `/agent` endpoint. Message format:
                        `[16-byte session_id][protobuf payload]`.

Both share connect/reconnect/close machinery via the `_Connection` base.

Reconnect lives here. Each leg holds its own wire and a relay in the path is
byte-opaque, so each side reconnects independently of the other.

Close codes:
  - 4000 (NoAgent)        → PermanentClose, never retry
  - 4001 (AgentGone)      → transient, reconnect with backoff
  - anything else         → transient, reconnect with backoff
  - 1000 from us (close()) → no reconnect

A rejection at the *HTTP handshake* is not a close code at all — the relay
answers `401`/`403` before the upgrade, so there is no websocket to carry a
code. Those are terminal too (`AuthRejected`): a credential it refuses will not
start working on attempt 12, and retrying only buries the real cause under a
backoff loop that logs "retrying" forever.

After each successful reconnect the optional `on_reconnect` callback fires, and
what it is for is teardown: the far side has lost the sessions this connection
was carrying. A session is never resumed by replaying its `SessionStartFrame` —
that would trample the state the brain still holds.
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

CLOSE_NO_AGENT = 4000  # permanent
CLOSE_AGENT_GONE = 4001  # transient

# HTTP statuses Cortex answers the upgrade with when the credential itself is
# the problem. Retrying these is pointless — the key is missing, revoked, or
# not an `sk_` for this agent, and no amount of backoff changes that.
FATAL_HTTP_STATUSES = frozenset({401, 403})

# Length of the session-id prefix on the multiplexed `/agent` leg.
SESSION_ID_LEN = 16


class PermanentClose(Exception):
    """Raised by send/recv/start when the far side returned a non-retriable close."""

    def __init__(self, code: int, reason: str = "", message: str | None = None):
        super().__init__(message or f"wire permanently closed: code={code} reason={reason!r}")
        self.code = code
        self.reason = reason


class AuthRejected(PermanentClose):
    """Cortex refused the handshake itself (HTTP 401/403), before any upgrade.

    A subclass of `PermanentClose` so every existing caller that already treats
    a permanent close as fatal keeps working unchanged; catch this specifically
    to tell "your credential is wrong" apart from "there is no agent here".
    """

    def __init__(self, status: int, reason: str = ""):
        super().__init__(
            status,
            reason,
            message=(
                f"Cortex refused the connection: HTTP {status}. The API key is "
                "missing, revoked, or is not an sk_ secret key for this agent — "
                "check VOQAL_API_KEY against the key shown in the console."
            ),
        )
        self.status = status


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
        # A first connect that failed terminally raises here rather than
        # returning a wire that only explodes on the caller's first recv().
        self._raise_if_terminal()

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
                terminal = self._terminal_error(exc)
                if terminal is not None:
                    self._permanent_error = terminal
                    logger.error(
                        f"wire: connect attempt {attempt} refused; not retrying: {terminal}"
                    )
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

    @classmethod
    def _terminal_error(cls, exc: Exception) -> PermanentClose | None:
        """Classify a failed connect attempt: terminal, or worth retrying?"""
        if cls._extract_close_code(exc) == CLOSE_NO_AGENT:
            return PermanentClose(CLOSE_NO_AGENT)
        status = cls._extract_http_status(exc)
        if status is not None and status in FATAL_HTTP_STATUSES:
            return AuthRejected(status)
        return None

    @staticmethod
    def _extract_close_code(exc: Exception) -> int | None:
        rcvd = getattr(exc, "rcvd", None)
        return rcvd.code if rcvd is not None else None

    @staticmethod
    def _extract_http_status(exc: Exception) -> int | None:
        """The status of a handshake rejection (`websockets.InvalidStatus`).

        Read defensively rather than by isinstance: the exception's shape is
        websockets' to change, and a missing attribute must degrade to "retry",
        never to a crash inside the reconnect loop.
        """
        status = getattr(getattr(exc, "response", None), "status_code", None)
        return status if isinstance(status, int) else None


class Wire(_Connection):
    """The voice leg of the wire: one session per connection.

    Message format: `[payload bytes]`. No session prefix — Voice dials
    `/s/{session_id}`, so the session is implicit in the URL. A brain never dials
    this leg: `run_session` is handed a socket its framework already accepted.
    It is here because the SDK's own tests play the voice side with it.
    """

    async def send(self, payload: bytes) -> None:
        """Send one binary message."""
        await self._raw_send(payload)

    async def recv(self) -> bytes:
        """Receive one binary message."""
        msg = await self._raw_recv()
        if not msg:
            raise ValueError("wire received empty websocket message")
        return bytes(msg)


class MultiplexedWire(_Connection):
    """The agent leg of the wire: every session over one connection.

    Message format: `[16-byte session_id][payload bytes]`. The relay inserts the
    session-id prefix on this leg.
    """

    async def send(self, session_id: bytes, payload: bytes) -> None:
        """Send `[session_id 16B][payload]`."""
        if len(session_id) != SESSION_ID_LEN:
            raise ValueError(
                f"session_id must be exactly {SESSION_ID_LEN} bytes, got {len(session_id)}"
            )
        await self._raw_send(session_id + payload)

    async def recv(self) -> tuple[bytes, bytes]:
        """Receive `[session_id 16B][payload]`."""
        msg = await self._raw_recv()
        if len(msg) < SESSION_ID_LEN:
            raise ValueError(
                f"multiplexed wire received short message ({len(msg)} bytes); "
                f"need at least {SESSION_ID_LEN}"
            )
        return bytes(msg[:SESSION_ID_LEN]), bytes(msg[SESSION_ID_LEN:])
