"""Stand a brain on a real localhost WebSocket, for a test that wants the wire.

The production hosting surface is :func:`voqalize.sdk.run_session` in your own
web framework's route — the SDK owns no server. A *test*, though, needs a socket
to dial, and writing the accept-verify-adapt boilerplate in every test file is how
the boilerplate drifts. :func:`brain_server` is that socket and nothing more::

    async with brain_server(MyBrain, public_keys=keypair.public_pem) as server:
        driver = VoqalizeDriver(
            DirectConnection(server.url, session_id, token=...),
            session_id=session_id,
        )
        await driver.open()

It speaks the exact leg Voqalize dials — ``{url}/s/{session_id}``, a bearer token in
``Authorization``, one protobuf envelope per binary message — so a brain
that passes here has been exercised on the wire it will actually run on, not on a
stand-in.

Verification is not optional and has no default: pass ``public_keys=`` (from
:func:`~voqalize.conformance.wire_voqalize.generate_keypair`) or
``allow_unverified=True``. There is deliberately no fallback to the embedded
Voqalize keys — a test server that trusts the *production* signer can only ever
reject every token a test mints, and it would take a while to see why.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator, Callable

import websockets
from loguru import logger
from websockets.asyncio.server import ServerConnection
from websockets.asyncio.server import serve as ws_serve

from voqalize.sdk import Brain
from voqalize.sdk.brain import brain_factory
from voqalize.sdk.session import normalize_keys, serve_channel, verify_token
from voqalize.sdk.wire.transport import CLOSE_NO_AGENT

__all__ = ["BrainServer", "brain_server"]


class BrainServer:
    """A localhost WebSocket server running one brain per connection.

    ``build`` is a ``Brain`` subclass or a zero-arg callable returning one, and it
    runs once per connection — so state on the built brain is session-scoped, the
    same guarantee production hosting gives.
    """

    def __init__(
        self,
        build: type[Brain] | Callable[[], Brain],
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        public_keys: str | list[str] | None = None,
        allow_unverified: bool = False,
    ) -> None:
        self._factory = brain_factory(build)
        self._host = host
        self._port = port
        self._allow_unverified = allow_unverified
        self._public_keys = normalize_keys(public_keys)
        if not self._public_keys and not allow_unverified:
            raise ValueError(
                "brain_server: pass public_keys= (see generate_keypair) or allow_unverified=True"
            )
        self._server: websockets.asyncio.server.Server | None = None
        self._bound_port: int | None = None

    async def start(self) -> int:
        """Bind an ephemeral port and begin accepting; returns the bound port."""
        server = await ws_serve(self._handle, self._host, self._port)
        self._server = server
        sockets = list(server.sockets) if server.sockets else []
        bound = int(sockets[0].getsockname()[1]) if sockets else self._port
        self._bound_port = bound
        return bound

    @property
    def port(self) -> int:
        if self._bound_port is None:
            raise RuntimeError("brain_server: not started")
        return self._bound_port

    @property
    def url(self) -> str:
        """The base a driver dials — it appends ``/s/{session_id}``."""
        return f"ws://{self._host}:{self.port}"

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
        claims = verify_token(
            _bearer(ws),
            session_id,
            public_keys=self._public_keys,
            allow_unverified=self._allow_unverified,
        )
        if claims is None:
            # 4000 mirrors Cortex's permanent "no agent / rejected" close.
            await ws.close(code=CLOSE_NO_AGENT, reason="unauthorized")
            return
        try:
            await serve_channel(_ServerChannel(ws), factory=self._factory, session_id=session_id)
        except Exception:
            logger.exception("brain_server: session {} errored", session_id)
        finally:
            with contextlib.suppress(Exception):
                await ws.close(code=1000)


@contextlib.asynccontextmanager
async def brain_server(
    build: type[Brain] | Callable[[], Brain],
    *,
    host: str = "127.0.0.1",
    public_keys: str | list[str] | None = None,
    allow_unverified: bool = False,
) -> AsyncGenerator[BrainServer]:
    """Host ``build`` on an ephemeral localhost port for the life of the block.

    ``build`` is a ``Brain`` subclass or a zero-arg callable returning one; it runs
    per connection. Closes the server on the way out, whatever the test did.
    """
    server = BrainServer(
        build,
        host=host,
        public_keys=public_keys,
        allow_unverified=allow_unverified,
    )
    await server.start()
    try:
        yield server
    finally:
        await server.aclose()


class _ServerChannel:
    """A ``websockets`` ``ServerConnection`` as a :class:`~voqalize.sdk.Channel`
    (send/recv *bytes*). A text frame decodes to ``b""`` and is skipped by the
    session loop; a closed socket surfaces as ``ConnectionClosed``."""

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
    path = urlparse(request.path if request is not None else "").path
    idx = path.rfind("/s/")
    if idx < 0:
        return None
    return path[idx + 3 :].strip("/") or None


def _bearer(ws: ServerConnection) -> str | None:
    request = ws.request
    headers = getattr(request, "headers", None) if request is not None else None
    if headers is None:
        return None
    return headers.get("Authorization") or headers.get("authorization") or None
