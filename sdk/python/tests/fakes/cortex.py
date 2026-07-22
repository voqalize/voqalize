"""FakeCortex — a session-id-aware TCP relay that stands in for cortex.

Mirrors the real cortex split:
- Pygato leg: ``ws://host/s/{session_id}?agent_id={agent_id}``.
  Wire format ``[1-byte direction][payload]``. One session per connection.
- Agent leg: ``ws://host/agent?agent_id={agent_id}``.
  Wire format ``[16-byte session_id][1-byte direction][payload]``. One
  connection per agent process; many sessions multiplex over it.

FakeCortex inserts the 16-byte session_id prefix on the pygato→agent path
and strips it on the agent→pygato path. Test session ids are arbitrary
strings; we hash them to 16 bytes via uuid5.

Two-copy vendoring policy: identical file lives at
``pygato/tests/fakes/cortex.py`` and ``agent-sdk/tests/fakes/cortex.py``. If
the two drift, the shared e2e suite catches it.

Usage::

    async with FakeCortex() as cortex:
        pygato_wire = Wire(WireConfig(url=cortex.pygato_url("s1", "welcome")))
        await pygato_wire.start()

        agent = CortexAgent(
            api_key="welcome",
            version="1.0.0",
            cortex_url=cortex.agent_url("welcome"),
            factory=brain_factory(MyBrain),
        )
        await agent.run()

Failure injectors::

    await cortex.kill_pygato_leg("s1", code=4001)
    await cortex.kill_agent_leg("welcome", code=4001)
    cortex.drop_next("s1", n=2, direction="pygato_to_agent")
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse

import websockets
from loguru import logger
from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

SESSION_ID_LEN = 16

# Stable namespace for converting test session_id strings → 16 raw bytes.
_SESSION_NAMESPACE = uuid.UUID("d1e83b8d-3a3b-4ab5-9c0c-9c8d6f5d8a01")


def session_id_bytes(session_id: str) -> bytes:
    """Hash a test session_id string to 16 bytes deterministically."""
    return uuid.uuid5(_SESSION_NAMESPACE, session_id).bytes


@dataclass
class _AgentLeg:
    """One agent-side connection — a single physical socket per agent_id over
    which many sessions multiplex."""

    agent_id: str
    ws: ServerConnection | None = None
    ever_connected: bool = False
    # Frames buffered for this agent while it hasn't connected yet.
    buffered: list[bytes] = field(default_factory=list)


@dataclass
class _Session:
    """One session — one pygato leg, multiplexed onto an agent leg by id."""

    session_id: str
    agent_id: str
    pygato: ServerConnection | None = None
    pygato_ever_connected: bool = False
    pygato_buffered: list[bytes] = field(default_factory=list)
    drop_pygato_to_agent: int = 0
    drop_agent_to_pygato: int = 0


class FakeCortex:
    """Tiny localhost relay for cortex-leg tests."""

    def __init__(self, host: str = "127.0.0.1") -> None:
        self._host = host
        self._port: int | None = None
        self._server: websockets.asyncio.server.Server | None = None
        self._agents: dict[str, _AgentLeg] = {}
        self._sessions: dict[str, _Session] = {}
        self._lock = asyncio.Lock()

    # ─── Context manager ────────────────────────────────────────────────

    async def __aenter__(self) -> FakeCortex:
        self._server = await serve(self._handler, self._host, 0)
        sockets = list(self._server.sockets) if self._server.sockets else []
        if not sockets:
            raise RuntimeError("FakeCortex: server bound no sockets")
        self._port = sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        for sess in list(self._sessions.values()):
            if sess.pygato is not None:
                with suppress(Exception):
                    await sess.pygato.close(code=1000)
        for agent in list(self._agents.values()):
            if agent.ws is not None:
                with suppress(Exception):
                    await agent.ws.close(code=1000)
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    # ─── URL helpers ────────────────────────────────────────────────────

    def base_url(self) -> str:
        """Root URL — `ws://host:port`. Pygato's CortexLLMService
        appends `/s/{session_id}` itself."""
        return f"ws://{self._host}:{self._port}"

    def pygato_url(self, session_id: str, agent_id: str) -> str:
        return f"ws://{self._host}:{self._port}/s/{session_id}?agent_id={agent_id}"

    def agent_url(self, agent_id: str) -> str:
        return f"ws://{self._host}:{self._port}/agent?agent_id={agent_id}"

    # ─── Failure injectors ──────────────────────────────────────────────

    async def kill_pygato_leg(self, session_id: str, code: int = 4001) -> None:
        sess = self._sessions.get(session_id)
        if sess is None or sess.pygato is None:
            return
        ws = sess.pygato
        sess.pygato = None
        await ws.close(code=code)

    async def kill_agent_leg(self, agent_id: str, code: int = 4001) -> None:
        agent = self._agents.get(agent_id)
        if agent is None or agent.ws is None:
            return
        ws = agent.ws
        agent.ws = None
        await ws.close(code=code)

    def drop_next(
        self,
        session_id: str,
        *,
        n: int = 1,
        direction: str = "pygato_to_agent",
    ) -> None:
        sess = self._sessions.get(session_id)
        if sess is None:
            raise KeyError(f"FakeCortex: no session {session_id!r}")
        if direction == "pygato_to_agent":
            sess.drop_pygato_to_agent += n
        elif direction == "agent_to_pygato":
            sess.drop_agent_to_pygato += n
        else:
            raise ValueError(f"unknown direction: {direction!r}")

    # ─── Server handler ─────────────────────────────────────────────────

    async def _handler(self, ws: ServerConnection) -> None:
        path = self._path_of(ws)
        params = self._parse_query(ws)
        agent_id = self._agent_id_from_bearer(ws) or params.get("agent_id")

        if path.startswith("/s/"):
            session_id = path[len("/s/") :]
            if not session_id or not agent_id:
                await ws.close(code=1003, reason="missing session_id/agent_id")
                return
            await self._serve_pygato(ws, session_id=session_id, agent_id=agent_id)
        elif path == "/agent":
            if not agent_id:
                await ws.close(code=1003, reason="missing agent_id")
                return
            await self._serve_agent(ws, agent_id=agent_id)
        else:
            await ws.close(code=1003, reason=f"unknown path {path!r}")

    async def _serve_pygato(self, ws: ServerConnection, *, session_id: str, agent_id: str) -> None:
        async with self._lock:
            sess = self._sessions.get(session_id)
            if sess is None:
                sess = _Session(session_id=session_id, agent_id=agent_id)
                self._sessions[session_id] = sess
            sess.pygato = ws
            sess.pygato_ever_connected = True

        try:
            async for msg in ws:
                if not isinstance(msg, (bytes, bytearray)):
                    continue
                await self._route_pygato_to_agent(sess, bytes(msg))
        except ConnectionClosed:
            pass
        finally:
            async with self._lock:
                if sess.pygato is ws:
                    sess.pygato = None

    async def _serve_agent(self, ws: ServerConnection, *, agent_id: str) -> None:
        async with self._lock:
            agent = self._agents.get(agent_id)
            if agent is None:
                agent = _AgentLeg(agent_id=agent_id)
                self._agents[agent_id] = agent
            # Crash-only model: one live agent leg at a time. If another shows
            # up, the previous owner is replaced.
            agent.ws = ws
            agent.ever_connected = True

        # Flush any messages buffered while the agent was disconnected.
        await self._flush_agent_buffered(agent)

        try:
            async for msg in ws:
                if not isinstance(msg, (bytes, bytearray)):
                    continue
                await self._route_agent_to_pygato(agent, bytes(msg))
        except ConnectionClosed:
            pass
        finally:
            async with self._lock:
                if agent.ws is ws:
                    agent.ws = None

    # ─── Routing ───────────────────────────────────────────────────────

    async def _route_pygato_to_agent(self, sess: _Session, msg: bytes) -> None:
        """pygato sent `[direction][payload]`. Prepend the 16-byte session_id
        and forward to the agent leg."""
        if sess.drop_pygato_to_agent > 0:
            sess.drop_pygato_to_agent -= 1
            logger.debug(f"fake_cortex: drop pygato→agent ({len(msg)}B)")
            return
        prefixed = session_id_bytes(sess.session_id) + msg
        agent = self._agents.get(sess.agent_id)
        if agent is None or agent.ws is None:
            if agent is not None and not agent.ever_connected:
                # Buffer until the agent first connects (initial-connect race).
                if agent is None:
                    agent = _AgentLeg(agent_id=sess.agent_id)
                    self._agents[sess.agent_id] = agent
                agent.buffered.append(prefixed)
                return
            logger.debug(
                f"fake_cortex: agent leg gone for {sess.agent_id}, dropping "
                f"pygato→agent ({len(msg)}B)"
            )
            return
        try:
            await agent.ws.send(prefixed)
        except ConnectionClosed:
            if not agent.ever_connected:
                agent.buffered.append(prefixed)

    async def _route_agent_to_pygato(self, agent: _AgentLeg, msg: bytes) -> None:
        """Agent sent `[16B session_id][direction][payload]`. Strip the
        session_id and forward `[direction][payload]` to the corresponding
        pygato leg."""
        if len(msg) < SESSION_ID_LEN + 1:
            logger.warning(f"fake_cortex: short agent→pygato message ({len(msg)}B); dropping")
            return
        sid_bytes = msg[:SESSION_ID_LEN]
        payload = msg[SESSION_ID_LEN:]
        sess = self._find_session_by_bytes(sid_bytes)
        if sess is None:
            logger.debug(
                f"fake_cortex: agent→pygato for unknown session {sid_bytes.hex()[:8]}; dropping"
            )
            return
        if sess.drop_agent_to_pygato > 0:
            sess.drop_agent_to_pygato -= 1
            logger.debug(f"fake_cortex: drop agent→pygato ({len(payload)}B)")
            return
        if sess.pygato is None:
            if not sess.pygato_ever_connected:
                sess.pygato_buffered.append(payload)
                return
            logger.debug(
                f"fake_cortex: pygato leg gone for {sess.session_id}, dropping "
                f"agent→pygato ({len(payload)}B)"
            )
            return
        try:
            await sess.pygato.send(payload)
        except ConnectionClosed:
            if not sess.pygato_ever_connected:
                sess.pygato_buffered.append(payload)

    async def _flush_agent_buffered(self, agent: _AgentLeg) -> None:
        if agent.ws is None:
            return
        queued = agent.buffered
        agent.buffered = []
        for msg in queued:
            try:
                await agent.ws.send(msg)
            except ConnectionClosed:
                agent.buffered.append(msg)
                break

    # ─── Helpers ────────────────────────────────────────────────────────

    def _find_session_by_bytes(self, sid_bytes: bytes) -> _Session | None:
        for sess in self._sessions.values():
            if session_id_bytes(sess.session_id) == sid_bytes:
                return sess
        return None

    @staticmethod
    def _parse_query(ws: ServerConnection) -> dict[str, str]:
        request = ws.request
        target = request.path if request is not None else ""
        parsed = urlparse(target)
        qs = parse_qs(parsed.query)
        return {k: v[0] for k, v in qs.items() if v}

    @staticmethod
    def _path_of(ws: ServerConnection) -> str:
        request = ws.request
        target = request.path if request is not None else ""
        return urlparse(target).path

    @staticmethod
    def _header(ws: ServerConnection, name: str) -> str | None:
        request = ws.request
        if request is None:
            return None
        headers = getattr(request, "headers", None)
        if headers is None:
            return None
        try:
            return headers.get(name) or headers.get(name.lower())
        except Exception:
            return None

    @classmethod
    def _agent_id_from_bearer(cls, ws: ServerConnection) -> str | None:
        """Extract the routing agent_id from `Authorization: Bearer <token>`.

        Customer keys (``ak_…``) are used verbatim as the routing key — that
        matches local-dev where the customer key is also the pool key.
        Otherwise the token is decoded as a JWT *without verification*:
        FakeCortex routes on the claim, so a forged claim would only fool
        itself. Returns ``None`` if no usable bearer is present.
        """
        raw = cls._header(ws, "Authorization")
        if not raw or not raw.lower().startswith("bearer "):
            return None
        token = raw[len("Bearer ") :].strip()
        if not token:
            return None
        if token.startswith("ak_"):
            return token
        try:
            import jwt as _jwt

            claims = _jwt.decode(token, options={"verify_signature": False})
        except Exception:
            return None
        return claims.get("agent_id") or None


@asynccontextmanager
async def fake_cortex() -> asyncio.AsyncIterator[FakeCortex]:
    async with FakeCortex() as cortex:
        yield cortex
