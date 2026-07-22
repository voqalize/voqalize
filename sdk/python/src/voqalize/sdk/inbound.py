"""DirectAgent — a localhost convenience that OWNS a WebSocket server.

The framework-agnostic, production surface is :func:`voqalize.sdk.run_session`
(see :mod:`.session`): your own web framework accepts the upgrade and hands the
connected socket to the SDK. ``DirectAgent`` is the opposite convenience — for
local dev and quick scripts it owns a ``websockets`` server, extracts the
``session_id`` from the URL path and the bearer from the ``Authorization`` header,
verifies, and runs each connection through the *same* transport-neutral loop
(:func:`.session.serve_channel`).

    from voqalize.sdk import Brain, serve_direct

    class MyBrain(Brain):
        async def on_interaction(self, interaction):
            async with interaction.inference() as inf:
                await inf.speak(f"You said: {interaction.transcript}")

    asyncio.run(serve_direct(MyBrain, host="0.0.0.0", port=8787))

PyGato dials ``{brain_url}/s/{session_id}`` per session with a short-lived RS256
JWT (``iss=pygato``, ``aud=brain``, ``sub=session_id``). **Verification is on by
default** against the embedded Voqalize public keys (see :mod:`._platform_keys`);
``public_keys=`` overrides them, and ``allow_unverified=True`` skips it (local dev
only, logged loudly). Wire framing is ``[1-byte direction][protobuf payload]``,
session implicit in the URL path.
"""

from __future__ import annotations

import contextlib

import websockets
from loguru import logger
from websockets.asyncio.server import ServerConnection
from websockets.asyncio.server import serve as ws_serve

from ._platform_keys import VOQAL_PLATFORM_PUBLIC_KEYS
from .engine import DEFAULT_NORMAL_MAXSIZE, SessionFactory
from .session import normalize_keys, serve_channel, verify_token
from .wire.transport import CLOSE_NO_AGENT


class DirectAgent:
    """Owns a WebSocket server that runs one brain session per connection.

    ``factory`` runs once per connection/session, so state on the built adapter
    (and its Brain) is session-scoped. This is a localhost/dev convenience; the
    production surface is :func:`voqalize.sdk.run_session`.
    """

    def __init__(
        self,
        *,
        factory: SessionFactory,
        host: str = "0.0.0.0",
        port: int = 8787,
        public_keys: str | list[str] | None = None,
        allow_unverified: bool = False,
        inbound_queue_maxsize: int | None = None,
    ) -> None:
        self._factory = factory
        self._host = host
        self._port = port
        self._allow_unverified = allow_unverified
        self._normal_maxsize = inbound_queue_maxsize or DEFAULT_NORMAL_MAXSIZE
        # Verify against the customer's keys if any, else the embedded platform keys.
        self._public_keys = (
            normalize_keys(public_keys)
            if public_keys is not None
            else list(VOQAL_PLATFORM_PUBLIC_KEYS)
        )
        if allow_unverified:
            logger.warning(
                "direct: allow_unverified=True — brain connections are NOT "
                "authenticated. Local dev only; never run this in production."
            )
        elif not self._public_keys:
            raise ValueError(
                "direct: no verification keys available (embedded platform keys "
                "are empty and public_keys= not passed). Pass public_keys=, or "
                "allow_unverified=True for local dev."
            )
        self._server: websockets.asyncio.server.Server | None = None
        self._bound_port: int | None = None

    async def start(self) -> int:
        """Bind and begin accepting connections; returns the bound port.

        ``port=0`` binds an ephemeral port — read it back here (used in tests)."""
        server = await ws_serve(self._handle, self._host, self._port)
        self._server = server
        sockets = list(server.sockets) if server.sockets else []
        bound_port: int = sockets[0].getsockname()[1] if sockets else self._port
        self._bound_port = bound_port
        logger.info("direct: serving on ws://{}:{}/s/{{session_id}}", self._host, bound_port)
        return bound_port

    @property
    def port(self) -> int | None:
        """The bound port (set after :meth:`start`)."""
        return self._bound_port

    async def run(self) -> None:
        """Serve until cancelled."""
        if self._server is None:
            await self.start()
        server = self._server
        assert server is not None
        try:
            await server.wait_closed()
        finally:
            await self.aclose()

    async def serve_forever(self) -> None:
        await self.run()

    async def aclose(self) -> None:
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(Exception):
                await self._server.wait_closed()
            self._server = None

    async def _handle(self, ws: ServerConnection) -> None:
        session_id = _session_id_from_path(ws)
        if not session_id:
            await ws.close(code=1008, reason="expected /s/{session_id}")
            return
        if not verify_token(
            _bearer(ws),
            session_id,
            public_keys=self._public_keys,
            allow_unverified=self._allow_unverified,
        ):
            # 4000 mirrors Cortex's permanent "no agent / rejected" close.
            await ws.close(code=CLOSE_NO_AGENT, reason="unauthorized")
            logger.warning("direct: rejected session {} (auth)", session_id)
            return

        logger.info("direct: opened session {}", session_id)
        try:
            await serve_channel(
                _ServerChannel(ws),
                factory=self._factory,
                session_id=session_id,
                inbound_queue_maxsize=self._normal_maxsize,
            )
        except Exception:
            logger.exception("direct: session {} errored", session_id)
        finally:
            with contextlib.suppress(Exception):
                await ws.close(code=1000)
            logger.info("direct: closed session {}", session_id)


# ─── Helpers ─────────────────────────────────────────────────────────────────


class _ServerChannel:
    """Presents a ``websockets`` ``ServerConnection`` as a :class:`.session.Channel`
    (send/recv *bytes*). A str frame decodes to ``b""`` (skipped by the loop);
    a closed socket surfaces as the underlying ``ConnectionClosed`` (which the
    session loop treats as end-of-connection)."""

    def __init__(self, ws: ServerConnection) -> None:
        self._ws = ws

    async def send(self, data: bytes) -> None:
        await self._ws.send(data)

    async def recv(self) -> bytes:
        msg = await self._ws.recv()
        return msg if isinstance(msg, bytes) else b""


def _session_id_from_path(ws: ServerConnection) -> str | None:
    from urllib.parse import urlparse

    request = ws.request
    target = request.path if request is not None else ""
    path = urlparse(target).path
    prefix = "/s/"
    idx = path.rfind(prefix)
    if idx < 0:
        return None
    sid = path[idx + len(prefix) :].strip("/")
    return sid or None


def _bearer(ws: ServerConnection) -> str | None:
    request = ws.request
    if request is None:
        return None
    headers = getattr(request, "headers", None)
    if headers is None:
        return None
    raw = headers.get("Authorization") or headers.get("authorization")
    return raw or None
