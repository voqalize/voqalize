"""The framework-agnostic connection-handoff entrypoint (:func:`run_session`).

Unlike ``tests/direct/test_direct_end_to_end.py`` (which drives the ``DirectAgent``
*server* over real TCP), this exercises ``run_session`` with **no server at all**:
the "socket" is an in-memory :class:`Channel` pair. That is exactly the shape a
customer's FastAPI/Django route hands the SDK — the SDK owns neither the listener
nor the upgrade, only the connected byte channel. Also pins token verification
(the caller passes ``session_id`` + ``token``; the SDK verifies).
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

from voqalize.sdk import Brain, SessionRejected, run_session
from voqalize.sdk.wire import (
    CortexFrameSerializer,
    LLMTextFrame,
    SessionStartFrame,
    UserMessageFrame,
)

_TEARDOWN_ERRORS = (TimeoutError, asyncio.CancelledError, ConnectionError)


class EchoBrain(Brain):
    async def on_session_start(self, session, start) -> None:
        async with session.say() as inf:
            await inf.speak("hi there")

    async def on_interaction(self, interaction) -> None:
        async with interaction.say() as inf:
            await inf.speak(f"echo: {interaction.transcript}")


class _Endpoint:
    """One end of an in-memory duplex byte channel (send/recv bytes)."""

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
    server = _Endpoint(out_q=a2b, in_q=b2a)  # handed to run_session
    client = _Endpoint(out_q=b2a, in_q=a2b)  # the PyGato-side driver
    return server, client


class _Client:
    """PyGato-side driver over the in-memory channel: bare [dir][payload] framing."""

    def __init__(self, endpoint: _Endpoint) -> None:
        self._ep = endpoint
        self._ser = CortexFrameSerializer()

    async def send(
        self, frame, *, request_id: int = 0, epoch: int = 0, inference_id: int = 0
    ) -> None:
        payload = await self._ser.serialize(
            frame, request_id=request_id, epoch=epoch, inference_id=inference_id
        )
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


def _has_text(substr: str):
    return lambda frames, _acks: any(
        isinstance(f, LLMTextFrame) and substr in f.text for f in frames
    )


async def test_run_session_handoff_greeting_echo_and_ack():
    """No server: run_session over an in-memory channel does the full loop."""
    server_ch, client_ch = _pipe()
    sid = str(uuid.uuid4())
    task = asyncio.create_task(
        run_session(server_ch, brain=EchoBrain, session_id=sid, allow_unverified=True)
    )
    client = _Client(client_ch)
    try:
        await client.send(SessionStartFrame(session_id=sid, agent_id="echo"))
        frames, _ = await client.collect_until(_has_text("hi there"))
        assert any(isinstance(f, LLMTextFrame) and "hi there" in f.text for f in frames)

        await client.send(UserMessageFrame(text="ping"), epoch=1, request_id=7)
        frames, acks = await client.collect_until(
            lambda fr, ac: _has_text("echo: ping")(fr, ac) and 7 in ac
        )
        assert any(isinstance(f, LLMTextFrame) and "echo: ping" in f.text for f in frames)
        assert 7 in acks, "the data frame must be acked after dispatch"
    finally:
        await client_ch.close()  # closes the server side's recv → run_session returns
        with contextlib.suppress(*_TEARDOWN_ERRORS):
            await asyncio.wait_for(task, timeout=2.0)


async def test_run_session_rejects_bad_token_before_running():
    """A forged token raises SessionRejected — the caller then closes the socket."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub_pem = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_pem = other.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    sid = str(uuid.uuid4())
    forged = jwt.encode(
        {
            "iss": "pygato",
            "aud": "brain",
            "sub": sid,
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(seconds=60),
        },
        other_pem,
        algorithm="RS256",
    )
    server_ch, _client_ch = _pipe()
    with pytest.raises(SessionRejected):
        await run_session(
            server_ch,
            brain=EchoBrain,
            session_id=sid,
            token=f"Bearer {forged}",
            public_keys=pub_pem,
        )


async def test_run_session_accepts_valid_token():
    """A token signed by the configured key, with sub == session_id, runs."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    pub_pem = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    sid = str(uuid.uuid4())
    good = jwt.encode(
        {
            "iss": "pygato",
            "aud": "brain",
            "sub": sid,
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(seconds=60),
        },
        priv_pem,
        algorithm="RS256",
    )
    server_ch, client_ch = _pipe()
    task = asyncio.create_task(
        run_session(
            server_ch, brain=EchoBrain, session_id=sid, token=f"Bearer {good}", public_keys=pub_pem
        )
    )
    client = _Client(client_ch)
    try:
        await client.send(SessionStartFrame(session_id=sid, agent_id="echo"))
        frames, _ = await client.collect_until(_has_text("hi there"))
        assert frames
    finally:
        await client_ch.close()
        with contextlib.suppress(*_TEARDOWN_ERRORS):
            await asyncio.wait_for(task, timeout=2.0)
