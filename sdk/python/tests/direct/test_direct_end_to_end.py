"""End-to-end tests for the direct (Cortex-less) brain path.

Exercises the real server stack — ``DirectAgent`` → ``_ServerWire`` →
``SessionBuffer`` → ``_SessionRunner`` → the ergonomic ``Brain`` adapter — over
a real TCP WebSocket, driven by the actual PyGato-leg ``Wire`` client speaking
the same bare ``[direction][payload]`` framing and ``Vql*`` vocabulary PyGato
uses against Cortex today. No Cortex relay is involved.

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

from voqalize.sdk import Brain, DirectAgent, brain_factory
from voqalize.sdk.wire import (
    CortexFrameSerializer,
    FrameDirection,
    InterruptionFrame,
    PermanentClose,
    VqlLLMTextFrame,
    VqlStartFrame,
    VqlUserTextFrame,
    Wire,
    WireConfig,
)

# ─── A tiny brain ────────────────────────────────────────────────────────────


class EchoBrain(Brain):
    """Greets on session start; echoes each user turn back as one inference."""

    async def on_session_start(self, session, start) -> None:
        async with session.say() as inf:
            await inf.speak("hi there")

    async def on_interaction(self, interaction) -> None:
        async with interaction.say() as inf:
            await inf.speak(f"echo: {interaction.transcript}")


class SlowBrain(Brain):
    """Speaks after a delay — long enough to be barged in on."""

    async def on_interaction(self, interaction) -> None:
        async with interaction.say() as inf:
            await asyncio.sleep(5.0)  # cancelled by the interruption before this
            await inf.speak("you should never hear this")


# ─── Harness ─────────────────────────────────────────────────────────────────


class _Client:
    """PyGato-side driver: a single-session ``Wire`` + the shared serializer."""

    def __init__(self, wire: Wire) -> None:
        self._wire = wire
        self._ser = CortexFrameSerializer()

    async def send(self, frame, *, request_id: int = 0) -> None:
        payload = await self._ser.serialize(frame, request_id=request_id)
        await self._wire.send(FrameDirection.DOWNSTREAM, payload)

    async def collect_until(self, predicate, timeout: float = 3.0):
        """Drain inbound messages until ``predicate(frames, acks)`` is true.

        Returns ``(frames, acks)`` where ``frames`` is the list of decoded
        Frames and ``acks`` the list of ack ids seen."""
        frames: list = []
        acks: list[int] = []

        async def _pump():
            while not predicate(frames, acks):
                _direction, payload = await self._wire.recv()
                msg = await self._ser.deserialize_message(payload)
                if msg.ack is not None:
                    acks.append(msg.ack)
                elif msg.frame is not None:
                    frames.append(msg.frame)

        await asyncio.wait_for(_pump(), timeout=timeout)
        return frames, acks


async def _serve(brain_cls, **kwargs) -> tuple[DirectAgent, int]:
    agent = DirectAgent(
        factory=brain_factory(brain_cls),
        host="127.0.0.1",
        port=0,
        **kwargs,
    )
    port = await agent.start()
    return agent, port


async def _connect(port: int, session_id: str, *, headers: dict | None = None) -> Wire:
    wire = Wire(WireConfig(url=f"ws://127.0.0.1:{port}/s/{session_id}", headers=headers))
    await wire.start()
    return wire


def _has_text(substr: str):
    def _pred(frames, _acks) -> bool:
        return any(isinstance(f, VqlLLMTextFrame) and substr in f.text for f in frames)

    return _pred


# ─── Tests ───────────────────────────────────────────────────────────────────


async def test_direct_round_trip_greeting_and_echo():
    """Full loop with no Cortex: start → greeting → user turn → echo + ack."""
    agent, port = await _serve(EchoBrain, allow_unverified=True)
    session_id = str(uuid.uuid4())
    wire = await _connect(port, session_id)
    client = _Client(wire)
    try:
        # Session start → the brain greets (agent-initiated inference 0).
        await client.send(VqlStartFrame(session_id=session_id, agent_id="echo"))
        frames, _ = await client.collect_until(_has_text("hi there"))
        assert any(isinstance(f, VqlLLMTextFrame) and "hi there" in f.text for f in frames)

        # A user turn → the brain echoes, and the frame is acked after dispatch.
        await client.send(VqlUserTextFrame(interaction_id=1, text="ping"), request_id=42)
        frames, acks = await client.collect_until(
            lambda fr, ac: _has_text("echo: ping")(fr, ac) and 42 in ac
        )
        assert any(isinstance(f, VqlLLMTextFrame) and "echo: ping" in f.text for f in frames)
        assert 42 in acks, "the data frame must be acked after the brain consumes it"
    finally:
        await wire.close()
        await agent.aclose()


async def test_direct_interruption_echoes_drain_barrier():
    """A barge-in cancels the in-flight interaction and echoes the barrier."""
    agent, port = await _serve(SlowBrain, allow_unverified=True)
    session_id = str(uuid.uuid4())
    wire = await _connect(port, session_id)
    client = _Client(wire)
    try:
        await client.send(VqlStartFrame(session_id=session_id, agent_id="slow"))
        # Kick off the slow interaction, then barge in before it can speak.
        await client.send(VqlUserTextFrame(interaction_id=1, text="hello"), request_id=1)
        await asyncio.sleep(0.1)
        await client.send(InterruptionFrame())

        # The brain echoes an InterruptionFrame back — PyGato's drain barrier.
        frames, _ = await client.collect_until(
            lambda fr, _ac: any(isinstance(f, InterruptionFrame) for f in fr)
        )
        assert any(isinstance(f, InterruptionFrame) for f in frames)
        # The cancelled inference never produced its (post-sleep) text.
        assert not any(isinstance(f, VqlLLMTextFrame) and "never hear" in f.text for f in frames)
    finally:
        await wire.close()
        await agent.aclose()


async def test_direct_idle_interruption_is_handled_and_session_survives():
    """An ``InterruptionFrame`` arriving with **no turn in flight** (an idle
    barge-in — the user speaks while the agent is silent, e.g. just after the
    greeting settles) is handled gracefully: the brain cancels nothing, still echoes
    the drain barrier, and the session stays live for the next turn.

    The other interruption test barges a *running* turn; this pins the empty-pending
    path (``_cancel_pending`` over zero interactions), which a regression could
    plausibly crash on or leave wedged so the next turn never answers."""
    agent, port = await _serve(EchoBrain, allow_unverified=True)
    session_id = str(uuid.uuid4())
    wire = await _connect(port, session_id)
    client = _Client(wire)
    try:
        await client.send(VqlStartFrame(session_id=session_id, agent_id="echo"))
        # Drain the greeting first, so the InterruptionFrame we look for next can
        # only be the idle barge-in's drain echo.
        await client.collect_until(_has_text("hi there"))

        # Idle barge-in: interrupt with no interaction in flight.
        await client.send(InterruptionFrame())
        frames, _ = await client.collect_until(
            lambda fr, _ac: any(isinstance(f, InterruptionFrame) for f in fr)
        )
        assert any(isinstance(f, InterruptionFrame) for f in frames), (
            "an idle interruption must still echo the drain barrier"
        )

        # The session survived: a subsequent user turn is served normally + acked.
        await client.send(VqlUserTextFrame(interaction_id=1, text="ping"), request_id=7)
        frames, acks = await client.collect_until(
            lambda fr, ac: _has_text("echo: ping")(fr, ac) and 7 in ac
        )
        assert any(isinstance(f, VqlLLMTextFrame) and "echo: ping" in f.text for f in frames)
        assert 7 in acks, "the post-interruption turn must still be acked"
    finally:
        await wire.close()
        await agent.aclose()


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

    agent, port = await _serve(EchoBrain, public_keys=pub_pem)
    try:
        # Valid token → connects and works.
        good_sid = str(uuid.uuid4())
        wire = await _connect(port, good_sid, headers={"Authorization": f"Bearer {mint(good_sid)}"})
        client = _Client(wire)
        await client.send(VqlStartFrame(session_id=good_sid, agent_id="echo"))
        frames, _ = await client.collect_until(_has_text("hi there"))
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
                    url=f"ws://127.0.0.1:{port}/s/{bad_sid}",
                    headers={"Authorization": f"Bearer {mint(bad_sid, priv=other_pem)}"},
                )
            )
            # The server accepts the upgrade then closes 4000, so the permanent
            # close may surface on start() OR on the first recv() — cover both.
            await bad_wire.start()
            await bad_wire.recv()
    finally:
        await agent.aclose()


async def test_embedded_platform_keys_present_and_valid():
    """The shipped SDK must carry at least one parseable Voqalize public key, or
    the zero-config default silently has nothing to verify against."""
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    from voqalize.sdk._platform_keys import VOQAL_PLATFORM_PUBLIC_KEYS

    assert VOQAL_PLATFORM_PUBLIC_KEYS, "no embedded platform keys"
    for pem in VOQAL_PLATFORM_PUBLIC_KEYS:
        load_pem_public_key(pem.encode())  # raises if malformed


async def test_direct_default_verifies_with_embedded_keys():
    """Zero config: no ``public_keys`` and no ``allow_unverified`` ⇒ the embedded
    Voqalize keys are used, so an unauthenticated peer is rejected (4000). Proves
    verification is the default, not opt-in."""
    agent, port = await _serve(EchoBrain)  # no keys, no allow_unverified
    try:
        sid = str(uuid.uuid4())
        with pytest.raises(PermanentClose):
            wire = Wire(WireConfig(url=f"ws://127.0.0.1:{port}/s/{sid}"))  # no bearer
            await wire.start()
            await wire.recv()
    finally:
        await agent.aclose()


async def test_direct_empty_keys_raises_without_allow_unverified():
    """An explicitly empty key set with no ``allow_unverified`` must fail loudly at
    construction rather than silently accept everything."""
    with pytest.raises(ValueError, match="no verification keys"):
        DirectAgent(
            factory=brain_factory(EchoBrain),
            host="127.0.0.1",
            port=0,
            public_keys=[],
        )
    # allow_unverified is the explicit escape hatch — no raise even with no keys.
    agent = DirectAgent(
        factory=brain_factory(EchoBrain),
        host="127.0.0.1",
        port=0,
        public_keys=[],
        allow_unverified=True,
    )
    await agent.aclose()
