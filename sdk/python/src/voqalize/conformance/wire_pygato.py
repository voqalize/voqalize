"""The pygato/Voice side of the wire — what the conformance driver needs to
impersonate PyGato against a brain.

Three pieces the driver builds on:

1. :func:`decode_upstream` — decode a brain→pygato ``Envelope`` into a plain
   :class:`~voqalize.sdk.wire.Frame` (or :class:`~voqalize.sdk.wire.Ack`).
   The SDK's own ``CortexFrameSerializer`` decoder is deliberately *asymmetric*
   — it only decodes the frames a *brain* receives, so it is missing
   ``rtvi_server_message`` and the STT/TTS settings frames, which travel
   brain→pygato (i.e. *toward* this driver). This decoder is the complete
   pygato-receive vocabulary. (Encoding pygato→brain frames reuses the SDK's
   ``CortexFrameSerializer.serialize`` unchanged — its encoder table is complete.)

2. :class:`DirectConnection` — a bare ``websockets`` client that dials
   ``{brain_url}/s/{session_id}`` exactly as PyGato does: one WS per session, an
   ``Authorization: Bearer <token>`` header, and ``[1-byte direction][protobuf]``
   framing (direction always ``DOWNSTREAM`` pygato→brain, per the wire).

3. :func:`generate_keypair` / :func:`mint_pygato_token` — the RS256 brain token
   PyGato presents, byte-for-byte the claim shape of
   ``pygato._cortex_token.CortexTokenSigner`` (``iss=pygato``, ``aud=brain``,
   ``sub=session_id``, plus ``agent_id`` / ``tenant_id``). A conformance run mints
   with an ephemeral keypair and hands the public half to the brain under test.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from websockets.asyncio.client import ClientConnection, connect

from voqalize.sdk.wire import (
    Ack,
    CancelFrame,
    EndFrame,
    ErrorFrame,
    FinalizeReason,
    Frame,
    FrameDirection,
    IdleUpdateSettingsFrame,
    InterruptionFrame,
    RTVIServerMessageFrame,
    STTUpdateSettingsFrame,
    TTSUpdateSettingsFrame,
    VqlFunctionCallInProgressFrame,
    VqlFunctionCallResultFrame,
    VqlFunctionCallsStartedFrame,
    VqlInteractionCompletedFrame,
    VqlLLMFullResponseEndFrame,
    VqlLLMFullResponseStartFrame,
    VqlLLMTextFrame,
)
from voqalize.sdk.wire import _frames_pb2 as pb

# Same protocol constant every brain verifies (voqalize.sdk.session.BRAIN_AUDIENCE
# / pygato._cortex_token.CortexTokenSigner.BRAIN_AUDIENCE). Not per-agent.
BRAIN_AUDIENCE = "brain"

# Reason enum on decode — falls back to COMPLETED defensively (mirrors the SDK).
_REASON_FROM_PB: dict[int, FinalizeReason] = {
    pb.FINALIZE_REASON_COMPLETED: FinalizeReason.COMPLETED,
    pb.FINALIZE_REASON_USER_BARGE_IN: FinalizeReason.USER_BARGE_IN,
}


class UpstreamDecodeError(Exception):
    """A brain→pygato envelope did not parse into a known frame."""


def decode_upstream(payload: bytes) -> Frame | Ack:
    """Decode one brain→pygato ``Envelope`` payload (direction byte already stripped).

    Covers the complete set of frames a brain may send toward Voice:
    ``vql_llm_*``, ``vql_fc_*``, ``vql_interaction_completed``, the
    ``vql_interruption`` drain echo, ``rtvi_server_message`` (UI commands / the
    voice-lifecycle lane), the STT/TTS/idle settings frames (``session.configure*``),
    ``error``, ``end``, ``cancel``, and bare ``ack`` envelopes.
    """
    env = pb.Envelope()
    try:
        env.ParseFromString(payload)
    except Exception as exc:
        raise UpstreamDecodeError(f"envelope parse failed: {exc}") from exc

    which = env.WhichOneof("body")
    if which is None:
        raise UpstreamDecodeError("envelope has no body set")

    if which == "ack":
        return Ack(env.ack.ack_id)
    if which == "vql_llm_start":
        m = env.vql_llm_start
        return VqlLLMFullResponseStartFrame(
            interaction_id=m.interaction_id, inference_id=m.inference_id
        )
    if which == "vql_llm_text":
        m = env.vql_llm_text
        return VqlLLMTextFrame(
            interaction_id=m.interaction_id, inference_id=m.inference_id, text=m.text
        )
    if which == "vql_llm_end":
        m = env.vql_llm_end
        return VqlLLMFullResponseEndFrame(
            interaction_id=m.interaction_id, inference_id=m.inference_id
        )
    if which == "vql_fc_started":
        m = env.vql_fc_started
        return VqlFunctionCallsStartedFrame(
            interaction_id=m.interaction_id,
            inference_id=m.inference_id,
            tool_call_id=m.tool_call_id,
            function_name=m.function_name,
            arguments=json.loads(m.arguments) if m.arguments else {},
        )
    if which == "vql_fc_in_progress":
        m = env.vql_fc_in_progress
        return VqlFunctionCallInProgressFrame(
            interaction_id=m.interaction_id,
            inference_id=m.inference_id,
            tool_call_id=m.tool_call_id,
            function_name=m.function_name,
            arguments=json.loads(m.arguments) if m.arguments else {},
        )
    if which == "vql_fc_result":
        m = env.vql_fc_result
        return VqlFunctionCallResultFrame(
            interaction_id=m.interaction_id,
            inference_id=m.inference_id,
            tool_call_id=m.tool_call_id,
            function_name=m.function_name,
            result=json.loads(m.result) if m.result else {},
        )
    if which == "vql_interaction_completed":
        return VqlInteractionCompletedFrame(
            interaction_id=env.vql_interaction_completed.interaction_id
        )
    if which == "vql_interruption":
        return InterruptionFrame()
    if which == "rtvi_server_message":
        return RTVIServerMessageFrame(data=json.loads(env.rtvi_server_message.data))
    if which == "stt_update_settings":
        return STTUpdateSettingsFrame(settings=json.loads(env.stt_update_settings.settings))
    if which == "tts_update_settings":
        return TTSUpdateSettingsFrame(settings=json.loads(env.tts_update_settings.settings))
    if which == "idle_update_settings":
        return IdleUpdateSettingsFrame(settings=json.loads(env.idle_update_settings.settings))
    if which == "error":
        return ErrorFrame(error=env.error.error, fatal=env.error.fatal)
    if which == "end":
        return EndFrame()
    if which == "cancel":
        return CancelFrame(reason=env.cancel.reason or None)

    raise UpstreamDecodeError(f"envelope body {which!r} has no pygato-side decoder")


# ─── The direct-path connection (bare websockets client) ──────────────────────


class DirectConnection:
    """A single-session PyGato→brain WebSocket, dialed the way PyGato dials it.

    URL is ``{brain_url}/s/{session_id}``; auth is an ``Authorization: Bearer``
    header; framing is ``[1-byte direction][protobuf]`` with the direction byte
    always ``DOWNSTREAM`` (1) pygato→brain. Does not own retry/backoff — the
    conformance driver wants explicit control over the socket lifecycle.
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
        await self._ws.send(bytes([FrameDirection.DOWNSTREAM.value]) + payload)

    async def recv_payload(self) -> bytes:
        """Receive one frame's protobuf payload (direction byte stripped).

        Raises ``websockets.exceptions.ConnectionClosed`` when the socket closes
        (the driver's reader treats that as end-of-connection and records the
        close code — e.g. 4000 for an auth rejection)."""
        assert self._ws is not None, "connect() first"
        msg = await self._ws.recv()
        if isinstance(msg, str):
            return b""
        return bytes(msg[1:])

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
    """Mint the short-lived RS256 token PyGato presents on a brain connection.

    Claim shape is identical to ``pygato._cortex_token.CortexTokenSigner.mint``:
    ``iss=pygato``, ``aud=brain`` (the protocol constant), ``sub=session_id``,
    ``kind=pygato``, plus ``agent_id`` / ``tenant_id`` for the recipient to decide.
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
