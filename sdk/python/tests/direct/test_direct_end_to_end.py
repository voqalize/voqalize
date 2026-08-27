"""End-to-end tests for the direct (Cortex-less) brain path.

Exercises the real server stack — ``BrainServer`` → ``_ServerChannel`` →
``SessionBuffer`` → ``_SessionRunner`` → the ergonomic ``Brain`` adapter — over
a real TCP WebSocket, driven by the actual PyGato-leg ``Wire`` client speaking
the same one-envelope-per-message framing and frame vocabulary PyGato uses
against Cortex today. No Cortex relay is involved.

This is the proof that "PyGato dials the customer's brain directly, one socket
per session" works with the existing per-session machinery unchanged.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from voqalize.conformance import BrainServer
from voqalize.sdk import Brain, Chunk, SpeechEnd, SpeechStart
from voqalize.sdk.wire import (
    InterruptionFrame,
    PermanentClose,
    SessionStartFrame,
    SpeechChunkFrame,
    SpeechStartFrame,
    UserMessageFrame,
    Wire,
    WireConfig,
    WireSerializer,
)

# ─── A tiny brain ────────────────────────────────────────────────────────────


class EchoBrain(Brain):
    """Greets on session start; echoes each user turn back as one unit."""

    async def greet(self, session) -> str:
        return "hi there"

    async def on_user_message(self, session, msg):
        yield SpeechStart()
        yield Chunk(f"echo: {msg.text}")
        yield SpeechEnd()


class SlowBrain(Brain):
    """Speaks after a delay — long enough to be barged in on."""

    async def on_user_message(self, session, msg):
        yield SpeechStart()
        await asyncio.sleep(5.0)  # cancelled by the interruption before this
        yield Chunk("you should never hear this")
        yield SpeechEnd()


# ─── Harness ─────────────────────────────────────────────────────────────────


class _Client:
    """PyGato-side driver: a single-session ``Wire`` + the shared serializer."""

    def __init__(self, wire: Wire) -> None:
        self._wire = wire
        self._ser = WireSerializer()

    async def send(self, frame) -> None:
        await self._wire.send(await self._ser.serialize(frame))

    async def collect_until(self, predicate, timeout: float = 3.0) -> list:
        """Drain inbound messages until ``predicate(frames)`` is true."""
        frames: list = []

        async def _pump():
            while not predicate(frames):
                frame = await self._ser.deserialize_message(await self._wire.recv())
                if frame is not None:
                    frames.append(frame)

        await asyncio.wait_for(_pump(), timeout=timeout)
        return frames


async def _serve(brain_cls, **kwargs) -> tuple[BrainServer, int]:
    server = BrainServer(
        brain_cls,
        host="127.0.0.1",
        port=0,
        **kwargs,
    )
    port = await server.start()
    return server, port


async def _connect(port: int, session_id: str, *, headers: dict | None = None) -> Wire:
    wire = Wire(WireConfig(url=f"ws://127.0.0.1:{port}?session_id={session_id}", headers=headers))
    await wire.start()
    return wire


def _has_text(substr: str):
    def _pred(frames) -> bool:
        return any(isinstance(f, SpeechChunkFrame) and substr in f.text for f in frames)

    return _pred


# ─── Tests ───────────────────────────────────────────────────────────────────


async def test_direct_round_trip_greeting_and_echo():
    """Full loop with no Cortex: start → greeting → user turn → echo."""
    server, port = await _serve(EchoBrain, allow_unverified=True)
    session_id = str(uuid.uuid4())
    wire = await _connect(port, session_id)
    client = _Client(wire)
    try:
        # Session start is turn 1 → the brain greets on it.
        await client.send(SessionStartFrame(turn_id=1, session_id=session_id))
        frames = await client.collect_until(_has_text("hi there"))
        assert any(isinstance(f, SpeechChunkFrame) and "hi there" in f.text for f in frames)

        # A user turn → the brain echoes.
        await client.send(UserMessageFrame(turn_id=2, text="ping"))
        frames = await client.collect_until(_has_text("echo: ping"))
        assert any(isinstance(f, SpeechChunkFrame) and "echo: ping" in f.text for f in frames)
    finally:
        await wire.close()
        await server.aclose()


async def test_direct_interruption_cancels_the_turn_it_names():
    """A barge-in raises the watermark, and the turn under it stops generating."""
    server, port = await _serve(SlowBrain, allow_unverified=True)
    session_id = str(uuid.uuid4())
    wire = await _connect(port, session_id)
    client = _Client(wire)
    try:
        await client.send(SessionStartFrame(turn_id=1, session_id=session_id))
        # Kick off the slow turn, then barge in before it can speak.
        await client.send(UserMessageFrame(turn_id=2, text="hello"))
        frames = await client.collect_until(
            lambda fr: any(isinstance(f, SpeechStartFrame) for f in fr)
        )
        await client.send(InterruptionFrame(through_turn=2))

        # Nothing comes back: the watermark is Voqalize's own, so there is no
        # acknowledgement to wait for — only the silence that proves the turn died.
        with pytest.raises(TimeoutError):
            await client.collect_until(
                lambda fr: any(isinstance(f, SpeechChunkFrame) for f in fr), timeout=1.0
            )
        assert not any(isinstance(f, InterruptionFrame) for f in frames), (
            "the watermark is V→B only; a brain that echoes it overtakes its own speech"
        )
    finally:
        await wire.close()
        await server.aclose()


async def test_direct_idle_interruption_leaves_the_session_live():
    """An ``InterruptionFrame`` arriving with **no turn in flight** — the user
    speaks while the agent is silent, just after the greeting settles — raises the
    watermark over nothing and the session serves the next turn normally.

    The other interruption test barges a *running* turn; this pins the empty case,
    which a regression could plausibly crash on or leave wedged."""
    server, port = await _serve(EchoBrain, allow_unverified=True)
    session_id = str(uuid.uuid4())
    wire = await _connect(port, session_id)
    client = _Client(wire)
    try:
        await client.send(SessionStartFrame(turn_id=1, session_id=session_id))
        await client.collect_until(_has_text("hi there"))

        await client.send(InterruptionFrame(through_turn=1))

        # The session survived: a subsequent user turn is served normally.
        await client.send(UserMessageFrame(turn_id=2, text="ping"))
        frames = await client.collect_until(_has_text("echo: ping"))
        assert any(isinstance(f, SpeechChunkFrame) and "echo: ping" in f.text for f in frames)
    finally:
        await wire.close()
        await server.aclose()


async def test_direct_auth_accepts_valid_token_rejects_bad():
    """With a public key configured, a valid PyGato token connects; a forged
    token is closed permanently (4000, mirroring Cortex's NoAgent)."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    pub_pem = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )

    def mint(session_id: str, *, priv=priv_pem) -> str:
        now = datetime.now(UTC)
        return jwt.encode(
            {
                "iss": "pygato",
                "aud": "brain",
                "sub": session_id,
                "kind": "voqal-voice",
                "agent_id": "echo",
                "tenant_id": "t1",
                "iat": now,
                "exp": now + timedelta(seconds=300),
            },
            priv,
            algorithm="RS256",
        )

    server, port = await _serve(EchoBrain, public_keys=pub_pem)
    try:
        # Valid token → connects and works.
        good_sid = str(uuid.uuid4())
        wire = await _connect(port, good_sid, headers={"Authorization": f"Bearer {mint(good_sid)}"})
        client = _Client(wire)
        await client.send(SessionStartFrame(turn_id=1, session_id=good_sid))
        frames = await client.collect_until(_has_text("hi there"))
        assert frames
        await wire.close()

        # Forged token (wrong signing key) → permanent 4000 close.
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        other_pem = other.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        bad_sid = str(uuid.uuid4())
        with pytest.raises(PermanentClose):
            bad_wire = Wire(
                WireConfig(
                    url=f"ws://127.0.0.1:{port}?session_id={bad_sid}",
                    headers={"Authorization": f"Bearer {mint(bad_sid, priv=other_pem)}"},
                )
            )
            # The server accepts the upgrade then closes 4000, so the permanent
            # close may surface on start() OR on the first recv() — cover both.
            await bad_wire.start()
            await bad_wire.recv()
    finally:
        await server.aclose()


async def test_embedded_voqalize_keys_present_and_valid():
    """The shipped SDK must carry at least one parseable Voqalize public key, or
    the zero-config default silently has nothing to verify against."""
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    from voqalize.sdk._keys import VOQALIZE_PUBLIC_KEYS

    assert VOQALIZE_PUBLIC_KEYS, "no embedded Voqalize keys"
    for pem in VOQALIZE_PUBLIC_KEYS:
        load_pem_public_key(pem.encode())  # raises if malformed


async def test_brain_server_demands_an_explicit_verification_choice():
    """No keys and no ``allow_unverified`` fails at construction.

    ``BrainServer`` deliberately has no fallback to the embedded Voqalize keys
    (``run_session`` does): a test server trusting the *production* signer can only
    ever reject every token a test mints, and that takes a while to see.
    """
    for kwargs in ({}, {"public_keys": []}):
        with pytest.raises(ValueError, match="public_keys="):
            BrainServer(EchoBrain, host="127.0.0.1", port=0, **kwargs)
    # allow_unverified is the explicit escape hatch — no raise even with no keys.
    server = BrainServer(EchoBrain, host="127.0.0.1", port=0, allow_unverified=True)
    await server.aclose()
