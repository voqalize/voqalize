"""The pygato/Voice side of the wire — what the conformance driver needs to
impersonate PyGato against a brain.

Two pieces the driver builds on:

1. :class:`DirectConnection` — a bare ``websockets`` client that dials
   ``{brain_url}/s/{session_id}`` exactly as PyGato does: one WS per session, an
   ``Authorization: Bearer <token>`` header, and one protobuf envelope per
   binary message.

2. :func:`generate_keypair` / :func:`mint_pygato_token` — the RS256 brain token
   PyGato presents, byte-for-byte the claim shape of
   ``pygato._cortex_token.CortexTokenSigner`` (``iss=pygato``, ``aud=brain``,
   ``sub=session_id``, plus ``agent_id`` / ``tenant_id``). A conformance run mints
   with an ephemeral keypair and hands the public half to the brain under test.

Decoding is not one of them: ``CortexFrameSerializer`` decodes every body in the
schema, both ways, so the driver uses it directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from websockets.asyncio.client import ClientConnection, connect

# Same protocol constant every brain verifies (voqalize.sdk.session.BRAIN_AUDIENCE
# / pygato._cortex_token.CortexTokenSigner.BRAIN_AUDIENCE). Not per-agent.
BRAIN_AUDIENCE = "brain"

# ─── The direct-path connection (bare websockets client) ──────────────────────


class DirectConnection:
    """A single-session PyGato→brain WebSocket, dialed the way PyGato dials it.

    URL is ``{brain_url}/s/{session_id}``; auth is an ``Authorization: Bearer``
    header; framing is one protobuf envelope per binary message. Does not own
    retry/backoff — the conformance driver wants explicit control over the
    socket lifecycle.
    """

    def __init__(self, brain_url: str, session_id: str, *, token: str | None) -> None:
        self._url = f"{brain_url.rstrip('/')}/s/{session_id}"
        self._token = token
        self._ws: ClientConnection | None = None

    @property
    def url(self) -> str:
        return self._url

    async def connect(self) -> None:
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else None
        self._ws = await connect(self._url, additional_headers=headers)

    async def send_payload(self, payload: bytes) -> None:
        assert self._ws is not None, "connect() first"
        await self._ws.send(payload)

    async def recv_payload(self) -> bytes:
        """Receive one frame's protobuf payload.

        Raises ``websockets.exceptions.ConnectionClosed`` when the socket closes
        (the driver's reader treats that as end-of-connection and records the
        close code — e.g. 4000 for an auth rejection)."""
        assert self._ws is not None, "connect() first"
        msg = await self._ws.recv()
        if isinstance(msg, str):
            return b""
        return bytes(msg)

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()

    @property
    def close_code(self) -> int | None:
        return self._ws.close_code if self._ws is not None else None


# ─── The RS256 brain token PyGato presents ────────────────────────────────────


@dataclass(frozen=True)
class Keypair:
    """An RSA keypair for a conformance run: sign with ``private_pem``, configure
    the brain under test to verify against ``public_pem``."""

    private_pem: bytes
    public_pem: str


def generate_keypair() -> Keypair:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return Keypair(private_pem=private_pem, public_pem=public_pem)


def mint_pygato_token(
    *,
    private_key_pem: bytes,
    session_id: str,
    agent_id: str,
    tenant_id: str,
    ttl_seconds: int = 60,
) -> str:
    """Mint the short-lived RS256 token the voice runtime presents on a brain
    connection.

    ``pygato`` is Voqalize's internal name for that runtime — the process that holds
    the call. It survives here because it is a **literal claim value** your brain
    verifies against, not because you have to know what it stands for.

    Claims: ``iss=pygato``, ``aud=brain`` (the protocol constant),
    ``sub=session_id``, ``kind=pygato``, plus ``agent_id`` / ``tenant_id`` for the
    recipient to decide. Byte-identical to what the real runtime signs, so a brain
    that accepts this one accepts production.
    """
    now = datetime.now(UTC)
    claims = {
        "iss": "pygato",
        "aud": BRAIN_AUDIENCE,
        "sub": session_id,
        "kind": "pygato",
        "agent_id": agent_id,
        "tenant_id": tenant_id,
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
    }
    return jwt.encode(claims, private_key_pem, algorithm="RS256")
