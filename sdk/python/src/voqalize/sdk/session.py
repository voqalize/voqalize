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
    @app.websocket("/voice")
    async def voice(ws: WebSocket, session_id: str):
        await ws.accept()
        await run_session(
            _StarletteChannel(ws),                       # send/recv bytes
            brain=MyBrain,                               # or a () -> Brain factory
            session_id=session_id,                       # from ?session_id=
            token=ws.headers.get("authorization"),       # SDK verifies it
        )

Auth is the caller's request to extract and the SDK's to verify: you pass the
``session_id`` query parameter and the ``Authorization`` header value; the SDK checks Voqalize's
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
import functools
import hashlib
import uuid
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any, Protocol

import jwt
from cryptography.hazmat.primitives import serialization
from loguru import logger

from ._identity import VerifiedIdentity, verified_identity
from ._keys import VOQALIZE_PUBLIC_KEYS
from ._logging import session_context
from .engine import (
    DEFAULT_BULK_MAXSIZE,
    RunnerHost,
    SessionFactory,
    SessionRunner,
)
from .wire import MalformedFrameError, WireSerializer

if TYPE_CHECKING:
    from .brain import Brain

# The audience every brain-connection token carries — a wire constant, not a
# per-agent one. Any brain verifies aud == this; nothing configures it.
BRAIN_AUDIENCE = "brain"

# Namespace for hashing a non-UUID session id string to 16 bytes (a session id
# Voqalize minted is already a UUID; this is only a robustness fallback).
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
    """Raised by :func:`run_session` when the connection's token fails verification.

    The caller should close the socket: close code 4000 is what Voqalize reads as a
    permanent, non-retriable rejection."""


def session_id_bytes(session_id: str) -> bytes:
    """16-byte key for the session. Raw UUID bytes when the id is a real UUID,
    else a stable uuid5 hash."""
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


@functools.lru_cache(maxsize=64)
def key_id(public_pem: str) -> str:
    """The ``kid`` Voqalize stamps on a token signed with this key's private half.

    Derived, never configured: the first 16 hex characters of the SHA-256 of the
    key's DER-encoded SubjectPublicKeyInfo. The signer computes the same value from
    its own key, so a key id cannot be set wrong on either side. Returns ``""`` for
    a PEM that does not parse; that key simply never matches a ``kid``.
    """
    try:
        key = serialization.load_pem_public_key(public_pem.encode())
    except (ValueError, TypeError):
        return ""
    der = key.public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return hashlib.sha256(der).hexdigest()[:16]


def _keys_for(token: str, public_keys: list[str]) -> list[str]:
    """``public_keys`` with the one the token's ``kid`` names first.

    The rest follow, in their own order, so a token whose ``kid`` names no key we
    hold — or that carries none, as every token signed before key ids existed
    does — is still tried against each key, as before."""
    try:
        kid = jwt.get_unverified_header(token).get("kid")
    except jwt.PyJWTError:
        return public_keys
    if not isinstance(kid, str) or not kid:
        return public_keys
    named = [pem for pem in public_keys if key_id(pem) == kid]
    return named + [pem for pem in public_keys if pem not in named]


def _expected_agents(expect_agent: str | Iterable[str] | None) -> frozenset[str] | None:
    if expect_agent is None:
        return None
    agents = frozenset([expect_agent]) if isinstance(expect_agent, str) else frozenset(expect_agent)
    if not agents or not all(agents):
        raise ValueError(
            "run_session: expect_agent must be an agent id, or a list of them; "
            "it was empty. Leave it out to accept any agent."
        )
    return agents


_warned_no_expect_agent = False


def _warn_no_expect_agent() -> None:
    """Once per process: a brain without ``expect_agent`` serves any agent."""
    global _warned_no_expect_agent
    if _warned_no_expect_agent:
        return
    _warned_no_expect_agent = True
    logger.warning(
        "run_session: expect_agent= is not set, so this brain accepts a session "
        "for any agent, including one in another workspace whose brain URL points "
        "here. Pass expect_agent=<your agent id> (it is VOQALIZE_AGENT_ID if you "
        "followed the docs). A future release will require it."
    )


def verify_token(
    token: str | None,
    session_id: str,
    *,
    public_keys: list[str],
    allow_unverified: bool,
) -> dict[str, Any] | None:
    """Verify Voqalize's RS256 brain-connection token against ``public_keys``.

    Returns the verified claims on success and ``None`` on rejection — test
    ``is None``, not truthiness, because a verified token with no claims and an
    ``allow_unverified`` session both yield ``{}``. The claims matter because
    ``tenant_id`` and ``agent_id`` are what tag the session's log lines
    (`_logging`), and the only trustworthy source for them is the signature that
    was just checked.

    Every brain — a customer's WebSocket, a Cortex relay, or one of Voqalize's own
    hosted demo brains — verifies the *same* token the *same* way: signature, plus
    ``iss="pygato"``, ``aud="brain"`` (a wire constant — all brain connections
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
    for pem in _keys_for(token, public_keys):
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
        serializer: WireSerializer,
        bulk_max: int,
    ) -> None:
        self._channel = channel
        self._sid = session_id_raw
        self._factory = factory
        self._serializer = serializer
        self._bulk_max = bulk_max
        self._runner: SessionRunner | None = None
        self._writer_task: asyncio.Task[None] | None = None
        self._ready = asyncio.Event()
        self._done = asyncio.Event()

    async def run(self) -> None:
        runner = SessionRunner(
            session_id=self._sid, factory=self._factory, host=self, bulk_max=self._bulk_max
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
            if not msg:
                continue
            payload = bytes(msg)
            try:
                frame = await self._serializer.deserialize_message(payload)
            except MalformedFrameError:
                logger.exception("session: malformed payload; skipping")
                continue
            if frame is None:
                continue  # a body this build does not know
            self._runner.enqueue_inbound(frame)

    async def _writer_loop(self) -> None:
        assert self._runner is not None
        runner = self._runner
        while True:
            await self._ready.wait()
            while True:
                frame = runner.pop_out()
                if frame is None:
                    break
                try:
                    out = await self._serializer.serialize(frame)
                except Exception:
                    logger.exception("session: serialize failed")
                    continue
                try:
                    await self._channel.send(out)
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
        serializer=WireSerializer(),
        bulk_max=inbound_queue_maxsize or DEFAULT_BULK_MAXSIZE,
    )
    await conn.run()


async def run_session(
    channel: Channel,
    *,
    brain: type[Brain] | Callable[[], Brain],
    session_id: str,
    token: str | None = None,
    expect_agent: str | Iterable[str] | None = None,
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

    Verification is on by default against the embedded Voqalize keys — the
    token must be ``iss=pygato``, ``aud=brain``, and ``sub == session_id`` (see
    :func:`verify_token`). Override the keys with ``public_keys=`` (e.g. a
    self-hosted deployment), or ``allow_unverified=True`` for local dev. Raises
    :class:`SessionRejected` if the token fails — the caller should close 4000.

    ``expect_agent`` is the agent this brain serves, or a list of them: a token
    signed for any other agent is rejected like a forged one. Pass it. Voqalize
    signs a genuine token for every agent it calls, so without it a brain at a
    public URL also answers an agent in someone else's workspace that was pointed
    at that URL. It is optional for now and logs a warning once per process when
    it is missing; a future release will require it. ``allow_unverified=True``
    checks nothing, ``expect_agent`` included.

    The verified workspace and agent are on the brain's session as
    :attr:`Session.tenant_id <voqalize.sdk.Session.tenant_id>` and
    :attr:`Session.agent_id <voqalize.sdk.Session.agent_id>`.
    """
    from .brain import _brain_factory  # local import breaks the brain↔transport cycle

    expected = _expected_agents(expect_agent)

    keys = normalize_keys(public_keys) if public_keys is not None else list(VOQALIZE_PUBLIC_KEYS)
    if not allow_unverified and not keys:
        raise ValueError(
            "run_session: no verification keys (the embedded Voqalize keys are "
            "empty and public_keys= was not passed). Pass public_keys= or "
            "allow_unverified=True."
        )
    claims = verify_token(token, session_id, public_keys=keys, allow_unverified=allow_unverified)
    if claims is None:
        raise SessionRejected(f"unauthorized session {session_id}")
    if not allow_unverified:
        agent_id = str(claims.get("agent_id", ""))
        if expected is None:
            _warn_no_expect_agent()
        elif agent_id not in expected:
            logger.warning(
                "session: token is for agent {!r}, not one this brain serves; rejected {}",
                agent_id,
                session_id,
            )
            raise SessionRejected(f"session {session_id} is for another agent")
        identity = VerifiedIdentity(tenant_id=str(claims.get("tenant_id", "")), agent_id=agent_id)
    else:
        identity = None
    # Tag every line this session writes — including the brain's own — with the
    # identity the signature just vouched for, never with anything the caller
    # supplied. See `_logging`.
    identity_token = verified_identity.set(identity)
    try:
        with session_context(
            session_id,
            tenant_id=str(claims.get("tenant_id", "")),
            agent_id=str(claims.get("agent_id", "")),
        ):
            await serve_channel(
                channel,
                factory=_brain_factory(brain),
                session_id=session_id,
                inbound_queue_maxsize=inbound_queue_maxsize,
            )
    finally:
        verified_identity.reset(identity_token)
