"""The framework-agnostic connection-handoff entrypoint (:func:`run_session`).

Unlike ``tests/direct/test_direct_end_to_end.py`` (which drives the ``BrainServer``
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

from voqalize.sdk import Brain, SessionRejected, SpeechChunk, SpeechEnd, SpeechStart, run_session
from voqalize.sdk.wire import (
    SessionStartFrame,
    SpeechChunkFrame,
    UserMessageFrame,
    WireSerializer,
)

_TEARDOWN_ERRORS = (TimeoutError, asyncio.CancelledError, ConnectionError)


class EchoBrain(Brain):
    async def greet(self, session) -> str:
        return "hi there"

    async def on_user_message(self, session, msg):
        yield SpeechStart()
        yield SpeechChunk(f"echo: {msg.text}")
        yield SpeechEnd()


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
    """PyGato-side driver over the in-memory channel: one envelope per message."""

    def __init__(self, endpoint: _Endpoint) -> None:
        self._ep = endpoint
        self._ser = WireSerializer()

    async def send(self, frame) -> None:
        payload = await self._ser.serialize(frame)
        await self._ep.send(payload)

    async def collect_until(self, predicate, timeout: float = 3.0) -> list:
        frames: list = []

        async def _pump():
            while not predicate(frames):
                raw = await self._ep.recv()
                msg = await self._ser.deserialize_message(raw)
                if msg is not None:
                    frames.append(msg)

        await asyncio.wait_for(_pump(), timeout=timeout)
        return frames


def _has_text(substr: str):
    return lambda frames: any(isinstance(f, SpeechChunkFrame) and substr in f.text for f in frames)


async def test_run_session_handoff_greeting_and_echo():
    """No server: run_session over an in-memory channel does the full loop."""
    server_ch, client_ch = _pipe()
    sid = str(uuid.uuid4())
    task = asyncio.create_task(
        run_session(server_ch, brain=EchoBrain, session_id=sid, allow_unverified=True)
    )
    client = _Client(client_ch)
    try:
        await client.send(SessionStartFrame(turn_id=1, session_id=sid))
        frames = await client.collect_until(_has_text("hi there"))
        assert any(isinstance(f, SpeechChunkFrame) and "hi there" in f.text for f in frames)

        await client.send(UserMessageFrame(turn_id=2, text="ping"))
        frames = await client.collect_until(_has_text("echo: ping"))
        assert any(isinstance(f, SpeechChunkFrame) and "echo: ping" in f.text for f in frames)
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
        await client.send(SessionStartFrame(turn_id=1, session_id=sid))
        frames = await client.collect_until(_has_text("hi there"))
        assert frames
    finally:
        await client_ch.close()
        with contextlib.suppress(*_TEARDOWN_ERRORS):
            await asyncio.wait_for(task, timeout=2.0)


async def test_run_session_defaults_to_the_embedded_voqalize_keys():
    """No ``public_keys`` and no ``allow_unverified`` ⇒ the embedded Voqalize keys
    verify the token, so an unauthenticated peer is rejected. Verification is the
    default on the production surface, not opt-in."""
    server_ch, _client_ch = _pipe()
    with pytest.raises(SessionRejected):
        await run_session(server_ch, brain=EchoBrain, session_id=str(uuid.uuid4()))


# ─── expect_agent: a brain serves its own agent and refuses the rest ─────────


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


def _token(priv: bytes, sid: str, *, agent_id: str, tenant_id: str = "t-1", **headers) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "iss": "pygato",
            "aud": "brain",
            "sub": sid,
            "kind": "pygato",
            "agent_id": agent_id,
            "tenant_id": tenant_id,
            "iat": now,
            "exp": now + timedelta(seconds=60),
        },
        priv,
        algorithm="RS256",
        headers=headers or None,
    )


class _IdentityBrain(Brain):
    """Greets with what its session says it was signed for."""

    async def greet(self, session) -> str:
        return f"for {session.tenant_id}/{session.agent_id}"

    async def on_user_message(self, session, msg):
        yield SpeechStart()
        yield SpeechChunk("ok")
        yield SpeechEnd()


async def _greeting(**kwargs) -> str:
    """Run one session to its greeting and return the greeting's text."""
    server_ch, client_ch = _pipe()
    sid = kwargs.pop("session_id")
    task = asyncio.create_task(
        run_session(server_ch, brain=_IdentityBrain, session_id=sid, **kwargs)
    )
    client = _Client(client_ch)
    try:
        await client.send(SessionStartFrame(turn_id=1, session_id=sid))
        frames = await client.collect_until(_has_text("for "))
        return next(f.text for f in frames if isinstance(f, SpeechChunkFrame))
    finally:
        await client_ch.close()
        with contextlib.suppress(*_TEARDOWN_ERRORS):
            await asyncio.wait_for(task, timeout=2.0)


async def test_expect_agent_refuses_a_token_for_another_agent():
    """The attack this exists for: a genuine token, for someone else's agent."""
    priv, pub = _keypair()
    sid = str(uuid.uuid4())
    stranger = _token(priv, sid, agent_id="agent-stranger", tenant_id="t-other")
    server_ch, _client_ch = _pipe()
    with pytest.raises(SessionRejected, match="another agent"):
        await run_session(
            server_ch,
            brain=_IdentityBrain,
            session_id=sid,
            token=f"Bearer {stranger}",
            public_keys=pub,
            expect_agent="agent-mine",
        )


async def test_expect_agent_accepts_its_own_agent_and_says_who_on_the_session():
    priv, pub = _keypair()
    sid = str(uuid.uuid4())
    text = await _greeting(
        session_id=sid,
        token=f"Bearer {_token(priv, sid, agent_id='agent-mine')}",
        public_keys=pub,
        expect_agent="agent-mine",
    )
    assert text == "for t-1/agent-mine"


async def test_expect_agent_takes_a_list():
    priv, pub = _keypair()
    sid = str(uuid.uuid4())
    text = await _greeting(
        session_id=sid,
        token=f"Bearer {_token(priv, sid, agent_id='agent-b')}",
        public_keys=pub,
        expect_agent=["agent-a", "agent-b"],
    )
    assert text == "for t-1/agent-b"


async def test_an_empty_expect_agent_is_a_mistake_not_accept_all():
    server_ch, _ = _pipe()
    with pytest.raises(ValueError, match="expect_agent"):
        await run_session(
            server_ch, brain=_IdentityBrain, session_id="s", allow_unverified=True, expect_agent=[]
        )


async def test_without_expect_agent_any_agent_still_runs(monkeypatch):
    """Optional for now: an existing brain keeps working, and is told once."""
    import voqalize.sdk.session as session_mod

    monkeypatch.setattr(session_mod, "_warned_no_expect_agent", False)
    warned: list[str] = []
    monkeypatch.setattr(session_mod.logger, "warning", lambda msg, *a, **k: warned.append(str(msg)))
    priv, pub = _keypair()
    for _ in range(2):
        sid = str(uuid.uuid4())
        text = await _greeting(
            session_id=sid,
            token=f"Bearer {_token(priv, sid, agent_id='anyone')}",
            public_keys=pub,
        )
        assert text == "for t-1/anyone"
    assert sum("expect_agent" in w for w in warned) == 1


async def test_unverified_sessions_carry_no_identity():
    text = await _greeting(session_id=str(uuid.uuid4()), allow_unverified=True)
    assert text == "for None/None"


# ─── kid: the token names its key; old tokens without one still verify ──────


async def test_kid_picks_the_named_key_and_a_missing_or_unknown_kid_falls_back():
    from voqalize.sdk.session import key_id, verify_token

    _, pub_a = _keypair()
    priv_b, pub_b = _keypair()
    keys = [pub_a, pub_b]
    sid = str(uuid.uuid4())
    assert key_id(pub_a) != key_id(pub_b) and len(key_id(pub_a)) == 16
    for tok in (
        _token(priv_b, sid, agent_id="x", kid=key_id(pub_b)),  # named
        _token(priv_b, sid, agent_id="x"),  # signed before key ids existed
        _token(priv_b, sid, agent_id="x", kid="0000000000000000"),  # unknown
    ):
        assert verify_token(tok, sid, public_keys=keys, allow_unverified=False) is not None
    # A kid cannot vouch for a key: naming A on a token signed by an unknown key fails.
    priv_c, _ = _keypair()
    forged = _token(priv_c, sid, agent_id="x", kid=key_id(pub_a))
    assert verify_token(forged, sid, public_keys=keys, allow_unverified=False) is None


def test_key_id_of_the_embedded_production_key_is_stable():
    """The signer derives the same id from its private key; pin it so a change to
    the derivation on either side is caught, not discovered in a failed call."""
    from voqalize.sdk._keys import VOQALIZE_PUBLIC_KEYS
    from voqalize.sdk.session import key_id

    assert key_id(VOQALIZE_PUBLIC_KEYS[0]) == "5bdf529e75df87c3"
