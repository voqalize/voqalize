"""The connection-handoff entrypoint: run ONE session over an already-connected
socket the SDK did not create.

This is the framework-agnostic surface. The SDK does **not** own a WebSocket
server — your framework (FastAPI/Starlette, Django Channels, Flask+websockets,
aiohttp, …) accepts the upgrade and hands the connected socket to
:func:`run_session`. The only assumption is that the socket can move bytes:

    class Channel(Protocol):
        async def send(self, data: bytes) -> None: ...
        async def recv(self) -> bytes: ...

which is the natural shape of every WebSocket object (the ``websockets`` library,
Starlette's ``WebSocket.send_bytes``/``receive_bytes`` via a 2-line shim, etc.).

    # FastAPI — your route, your upgrade; the SDK just runs the session.
    @app.websocket("/s/{session_id}")
    async def voice(ws: WebSocket, session_id: str):
        await ws.accept()
        await run_session(
            _StarletteChannel(ws),                       # send/recv bytes
            brain=MyBrain,                               # or a () -> Brain factory
            session_id=session_id,                       # from your route param
            token=ws.headers.get("authorization"),       # SDK verifies it
        )

Auth is the caller's request to extract and the SDK's to verify: you pass the URL
``session_id`` and the ``Authorization`` header value; the SDK checks PyGato's
RS256 token (signature + expiry + ``sub == session_id``) against the embedded
Voqalize keys by default. Framework-specific wrappers that do the extraction for
you can be layered on later — this primitive stays assumption-free.

``run_session`` runs until the session ends (``End`` drains) or the socket errors,
then returns. It never closes the channel — the caller owns the socket's
lifecycle. When your process cannot accept an inbound connection at all, dial the
Cortex relay instead with :func:`voqalize.sdk.serve`.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

import jwt
from loguru import logger

from ._logging import session_context
from ._platform_keys import VOQAL_PLATFORM_PUBLIC_KEYS
from .engine import (
    DEFAULT_NORMAL_MAXSIZE,
    OUT_DIRECTION,
    Envelope,
    RunnerHost,
    SessionFactory,
    SessionRunner,
    _Ack,
)
from .wire import CortexFrameSerializer, MalformedFrameError

if TYPE_CHECKING:
    from .brain import Brain

# The audience every PyGato brain-connection token carries — a protocol constant
# (not per-agent). Any brain verifies aud == this; nothing configures it.
BRAIN_AUDIENCE = "brain"

# Namespace for hashing a non-UUID session id string to 16 bytes (a real PyGato
# session_id is already a UUID; this is only a robustness fallback).
_SESSION_NAMESPACE = uuid.UUID("d1e83b8d-3a3b-4ab5-9c0c-9c8d6f5d8a01")


class Channel(Protocol):
    """A connected bidirectional byte channel — the SDK's entrypoint.

    Satisfied by any WebSocket object that can send/receive binary messages.
    ``recv`` raises (any exception) when the socket closes; the session loop
    treats that as end-of-connection.
    """

    async def send(self, data: bytes) -> None: ...

    async def recv(self) -> bytes: ...


class SessionRejected(Exception):
    """Raised by :func:`run_session` when the PyGato token fails verification.

    The caller should close the socket (PyGato treats close code 4000 as a
    permanent, non-retriable rejection — mirroring Cortex's ``NoAgent``)."""


def session_id_bytes(session_id: str) -> bytes:
    """16-byte key for the session. Raw UUID bytes when the id is a real UUID
    (the PyGato case), else a stable uuid5 hash."""
    try:
        return uuid.UUID(session_id).bytes
    except ValueError:
        return uuid.uuid5(_SESSION_NAMESPACE, session_id).bytes


def normalize_keys(public_keys: str | list[str] | None) -> list[str]:
    if public_keys is None:
        return []
    if isinstance(public_keys, str):
        return [public_keys] if public_keys.strip() else []
    return [k for k in public_keys if k and k.strip()]


def verify_token(
    token: str | None,
    session_id: str,
    *,
    public_keys: list[str],
    allow_unverified: bool,
) -> dict[str, Any] | None:
    """Verify PyGato's RS256 brain-connection token against ``public_keys``.

    Returns the verified claims on success and ``None`` on rejection — so it is
    still usable as a boolean guard, but the caller can also read the identity
    the token asserts. That matters because ``tenant_id`` / ``agent_id`` /
    ``meeting_id`` are what tag the session's log lines (`_logging`), and the
    only trustworthy source for them is the signature that was just checked.
    An unverified session yields ``{}``, which is truthy-negative in the same
    way: verified-with-no-claims and not-verified stay distinguishable.

    Every brain — a customer's WebSocket, a Cortex relay, or one of Voqalize's own
    hosted demo brains — verifies the *same* token the *same* way: signature, plus
    ``iss="pygato"``, ``aud="brain"`` (a protocol constant — all brain connections
    share it), and ``sub == session_id`` (scoped to exactly one session). The
    recipient then decides from the token's ``tenant_id`` / ``agent_id`` whether it
    serves that agent. ``token`` may be a bare JWT or an
    ``"Authorization: Bearer <jwt>"`` header value; ``allow_unverified`` skips the
    check entirely (local dev only)."""
    if allow_unverified:
        return {}
    if not token:
        return None
    if token.lower().startswith("bearer "):
        token = token[len("bearer ") :].strip()
    for pem in public_keys:
        try:
            claims = jwt.decode(
                token,
                pem,
                algorithms=["RS256"],
                audience=BRAIN_AUDIENCE,
                issuer="pygato",
                options={"require": ["exp", "aud", "iss"]},
            )
        except Exception:
            continue
        if claims.get("sub") == session_id:
            return claims
        logger.warning("session: token sub != session id for {}", session_id)
        return None
    return None


class _ChannelSession(RunnerHost):
    """Drives one session over one :class:`Channel`: a :class:`SessionRunner`
    plus a dedicated writer. Implements :class:`RunnerHost`.

    Does **not** close the channel — the caller owns the socket's lifecycle.
    """

    def __init__(
        self,
        channel: Channel,
        *,
        session_id_raw: bytes,
        factory: SessionFactory,
        serializer: CortexFrameSerializer,
        normal_max: int,
    ) -> None:
        self._channel = channel
        self._sid = session_id_raw
        self._factory = factory
        self._serializer = serializer
        self._normal_max = normal_max
        self._runner: SessionRunner | None = None
        self._writer_task: asyncio.Task[None] | None = None
        self._ready = asyncio.Event()
        self._done = asyncio.Event()

    async def run(self) -> None:
        runner = SessionRunner(
            session_id=self._sid, factory=self._factory, host=self, normal_max=self._normal_max
        )
        self._runner = runner
        runner.start()
        self._writer_task = asyncio.create_task(self._writer_loop(), name="session-writer")
        try:
            await self._reader_loop()
        finally:
            await self._teardown()

    # ─── RunnerHost seam ────────────────────────────────────────────────

    def signal_ready(self, runner: SessionRunner) -> None:
        self._ready.set()

    def close_session(self, runner: SessionRunner) -> None:
        self._done.set()

    # ─── Reader / writer ────────────────────────────────────────────────

    async def _reader_loop(self) -> None:
        assert self._runner is not None
        while not self._done.is_set():
            try:
                msg = await self._channel.recv()
            except asyncio.CancelledError:
                raise
            except Exception:
                return  # socket closed / errored — end of connection
            if isinstance(msg, str):
                logger.warning("session: received TEXT frame; ignoring")
                continue
            if len(msg) < 1:
                continue
            payload = bytes(msg[1:])  # drop the 1-byte direction; inbound is DOWNSTREAM
            try:
                decoded = await self._serializer.deserialize_message(payload)
            except MalformedFrameError:
                logger.exception("session: malformed payload; skipping")
                continue
            if decoded.frame is None:
                continue  # SDK is the ack sender, never the receiver
            self._runner.enqueue_inbound(
                Envelope(
                    frame=decoded.frame,
                    request_id=decoded.request_id,
                    epoch=decoded.epoch,
                    inference_id=decoded.inference_id,
                )
            )

    async def _writer_loop(self) -> None:
        assert self._runner is not None
        runner = self._runner
        while True:
            await self._ready.wait()
            while True:
                item = runner.pop_out()
                if item is None:
                    break
                try:
                    if isinstance(item, _Ack):
                        out = serialize_ack_bytes(item.ack_id)
                    else:
                        out = await self._serializer.serialize(
                            item.frame, epoch=item.epoch, inference_id=item.inference_id
                        )
                except Exception:
                    logger.exception("session: serialize failed")
                    continue
                try:
                    await self._channel.send(bytes([OUT_DIRECTION.value]) + out)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    return  # socket gone
            self._ready.clear()
            if not runner.out_empty():
                self._ready.set()  # re-arm: a frame landed between pop and clear

    async def _teardown(self) -> None:
        if self._writer_task is not None and not self._writer_task.done():
            self._writer_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._writer_task
        if self._runner is not None:
            with contextlib.suppress(Exception):
                await self._runner.cancel()
            self._runner = None


def serialize_ack_bytes(ack_id: int) -> bytes:
    # Local re-export so _ChannelSession doesn't reach into wire.serializer.
    from .wire.serializer import serialize_ack

    return serialize_ack(ack_id)


async def serve_channel(
    channel: Channel,
    *,
    factory: SessionFactory,
    session_id: str,
    inbound_queue_maxsize: int | None = None,
) -> None:
    """Transport-neutral session loop over a connected channel — **no auth**.

    Used by :func:`run_session` after it verifies the token, and by the test host
    :func:`voqalize.conformance.brain_server`, which verifies its own way. Runs
    until the session ends or the socket errors; never closes the channel.
    """
    conn = _ChannelSession(
        channel,
        session_id_raw=session_id_bytes(session_id),
        factory=factory,
        serializer=CortexFrameSerializer(),
        normal_max=inbound_queue_maxsize or DEFAULT_NORMAL_MAXSIZE,
    )
    await conn.run()


async def run_session(
    channel: Channel,
    *,
    brain: type[Brain] | Callable[[], Brain],
    session_id: str,
    token: str | None = None,
    public_keys: str | list[str] | None = None,
    allow_unverified: bool = False,
    inbound_queue_maxsize: int | None = None,
) -> None:
    """Run one voice session over an already-connected socket.

    The framework-agnostic entrypoint: your web framework accepts the WebSocket
    upgrade and hands the connected ``channel`` (anything with ``send(bytes)`` /
    ``recv() -> bytes``) here, along with the URL ``session_id`` and the
    ``Authorization`` header ``token``. A fresh brain runs this one session; the
    call returns when the session ends or the socket closes.

    ``brain`` is a ``Brain`` subclass, or any zero-arg callable returning one when
    the brain needs injected dependencies (``brain=lambda: TravelBrain(llm=provider)``).
    Either way it runs once per session, so no state leaks between calls.

    Verification is on by default against the embedded Voqalize keys — PyGato's
    token must be ``iss=pygato``, ``aud=brain``, and ``sub == session_id`` (see
    :func:`verify_token`). Override the keys with ``public_keys=`` (e.g. a
    self-hosted deployment), or ``allow_unverified=True`` for local dev. Raises
    :class:`SessionRejected` if the token fails — the caller should close 4000.
    """
    from .brain import brain_factory  # local import breaks the brain↔transport cycle

    keys = (
        normalize_keys(public_keys) if public_keys is not None else list(VOQAL_PLATFORM_PUBLIC_KEYS)
    )
    if not allow_unverified and not keys:
        raise ValueError(
            "run_session: no verification keys (embedded platform keys empty and "
            "public_keys= not passed). Pass public_keys= or allow_unverified=True."
        )
    claims = verify_token(token, session_id, public_keys=keys, allow_unverified=allow_unverified)
    if claims is None:
        raise SessionRejected(f"unauthorized session {session_id}")
    # Tag every line this session writes — including the brain's own — with the
    # identity the signature just vouched for, never with anything the caller
    # supplied. See `_logging`.
    with session_context(
        session_id,
        tenant_id=str(claims.get("tenant_id", "")),
        agent_id=str(claims.get("agent_id", "")),
        meeting_id=str(claims.get("meeting_id", "")),
    ):
        await serve_channel(
            channel,
            factory=brain_factory(brain),
            session_id=session_id,
            inbound_queue_maxsize=inbound_queue_maxsize,
        )
