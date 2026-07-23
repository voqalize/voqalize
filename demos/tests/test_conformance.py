"""Protocol-conformance tests for the demos runtime.

These are the "integration test" leg of the demos' triple duty: they drive the
**real** inbound stack — the SDK's ``run_session`` over an in-memory ``Channel``
pair, the actual demo ``Brain``, the real ``Vql*`` wire vocabulary — with a
PyGato-side driver, **no audio and no LLM**. A demo's fixed session-start greeting
rides the wire exactly as it would in production, proving the brain is wired to
the transport correctly. (Full-voice behaviour — the LLM tool loop — is a staging
smoke test, not a CI unit.)

The channel/driver harness mirrors the SDK's own
``tests/direct/test_run_session_handoff.py``.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from voqalize_demos.discovery import build_for, discover
from voqalize_demos.llm import GeminiProvider
from voqalize_demos.umbrella import create_app

from voqalize.sdk import run_session
from voqalize.sdk.wire import CortexFrameSerializer, VqlLLMTextFrame, VqlStartFrame

_TEARDOWN_ERRORS = (TimeoutError, asyncio.CancelledError, ConnectionError)


# ─── In-memory channel harness (PyGato ↔ brain, no server, no TCP) ─────────────


class _Endpoint:
    def __init__(self, out_q: asyncio.Queue, in_q: asyncio.Queue) -> None:
        self._out = out_q
        self._in = in_q

    async def send(self, data: bytes) -> None:
        await self._out.put(bytes(data))

    async def recv(self) -> bytes:
        item = await self._in.get()
        if item is None:
            raise ConnectionError("channel closed")
        return item

    async def close(self) -> None:
        await self._out.put(None)


def _pipe() -> tuple[_Endpoint, _Endpoint]:
    a2b: asyncio.Queue = asyncio.Queue()
    b2a: asyncio.Queue = asyncio.Queue()
    return _Endpoint(out_q=a2b, in_q=b2a), _Endpoint(out_q=b2a, in_q=a2b)


class _Client:
    """PyGato-side driver over the in-memory channel: bare [dir][payload] framing."""

    def __init__(self, endpoint: _Endpoint) -> None:
        self._ep = endpoint
        self._ser = CortexFrameSerializer()

    async def send(self, frame, *, request_id: int = 0) -> None:
        payload = await self._ser.serialize(frame, request_id=request_id)
        await self._ep.send(b"\x01" + payload)  # DOWNSTREAM

    async def collect_until(self, predicate, timeout: float = 3.0):
        frames: list = []
        acks: list[int] = []

        async def _pump():
            while not predicate(frames, acks):
                raw = await self._ep.recv()
                msg = await self._ser.deserialize_message(raw[1:])
                if msg.ack is not None:
                    acks.append(msg.ack)
                elif msg.frame is not None:
                    frames.append(msg.frame)

        await asyncio.wait_for(_pump(), timeout=timeout)
        return frames, acks


def _mint_token(priv_pem: bytes, session_id: str) -> str:
    return "Bearer " + jwt.encode(
        {
            "iss": "pygato",
            "aud": "brain",
            "sub": session_id,
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(seconds=60),
        },
        priv_pem,
        algorithm="RS256",
    )


def _keypair() -> tuple[bytes, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    pub = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return priv, pub


# ─── Discovery / wiring ────────────────────────────────────────────────────────


def test_discovery_finds_co_located_backends():
    """Every ``demos/<name>/backend/`` is discovered with a name, router, factory."""
    demos = discover()
    assert demos, "at least one demo backend must be discovered"
    for demo in demos:
        assert demo.name and demo.router is not None and demo.build is not None


def test_travel_is_discovered():
    names = {d.name for d in discover()}
    assert "travel" in names


def test_umbrella_app_builds():
    """The umbrella constructs and mounts a brain route per discovered demo.

    FastAPI mounts each included router lazily, so assert on the built health
    payload (which lists the mounted demos) rather than the raw route table."""
    from starlette.testclient import TestClient

    app = create_app()
    with TestClient(app) as client:
        body = client.get("/healthz").json()
    assert body["ok"] is True
    assert "travel" in body["demos"]


# ─── Inbound protocol conformance (real stack, no LLM) ─────────────────────────


async def test_travel_greeting_rides_the_wire():
    """A real travel session over the inbound path speaks its fixed greeting.

    Drives the actual ``TravelBrain`` (built through the manifest registry) with a
    valid Voqalize brain token. ``on_session_start`` speaks a fixed line — no LLM
    call — so this asserts the brain↔transport wiring end-to-end without a Gemini
    key or any audio."""
    priv, pub = _keypair()
    sid = str(uuid.uuid4())
    llm = GeminiProvider(api_key="")  # never called — the greeting is a fixed line
    build = build_for("travel")

    server_ch, client_ch = _pipe()
    task = asyncio.create_task(
        run_session(
            server_ch,
            brain_builder=lambda: build(llm),
            session_id=sid,
            token=_mint_token(priv, sid),
            public_keys=pub,
        )
    )
    client = _Client(client_ch)
    try:
        await client.send(VqlStartFrame(session_id=sid, agent_id="travel"))
        frames, _ = await client.collect_until(
            lambda fr, _ac: any(isinstance(f, VqlLLMTextFrame) and "प्रिया" in f.text for f in fr)
        )
        assert any(isinstance(f, VqlLLMTextFrame) for f in frames)
    finally:
        await client_ch.close()
        with contextlib.suppress(*_TEARDOWN_ERRORS):
            await asyncio.wait_for(task, timeout=2.0)


def test_unknown_demo_has_no_backend():
    """An unknown name has no discovered backend — ``build_for`` raises KeyError."""
    with pytest.raises(KeyError):
        build_for("does-not-exist")
