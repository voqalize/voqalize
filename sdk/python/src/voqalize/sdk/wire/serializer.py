"""Protobuf codec for the cortex wire.

Transcodes between the plain dataclasses in :mod:`.frames` and ``Envelope``
bytes. Pipecat-free, stateless, no base class.

Correlation is not part of a frame. ``serialize`` takes ``request_id``,
``epoch`` and ``inference_id`` as keywords and writes them onto the envelope;
``deserialize_message`` hands them back beside the decoded frame in a
:class:`DecodedMessage`. Callers thread that trio explicitly — the emitting
context (a turn, an inference) is what knows the values, not the payload.

``deserialize`` is strict and raises on anything it cannot decode.
``deserialize_message`` — the entry point the read loops use — is
forward-compatible: corrupt bytes still raise, but an envelope whose body this
build does not know is logged and skipped, since a newer peer may send a frame
added after this SDK shipped.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from loguru import logger

from . import _frames_pb2 as pb
from .frames import (
    WIRE_FRAME_CLASSES,
    CancelFrame,
    ClientMessageFrame,
    EndFrame,
    ErrorFrame,
    FinalizeReason,
    Frame,
    InferenceFinalizedFrame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    ServerMessageFrame,
    SessionStartFrame,
    UpdateIdleSettingsFrame,
    UpdateSTTSettingsFrame,
    UpdateTTSSettingsFrame,
    UserIdleFrame,
    UserMessageFrame,
)

_REASON_TO_PB: dict[FinalizeReason, int] = {
    FinalizeReason.COMPLETED: pb.FINALIZE_REASON_COMPLETED,
    FinalizeReason.USER_BARGE_IN: pb.FINALIZE_REASON_USER_BARGE_IN,
}
_REASON_FROM_PB: dict[int, FinalizeReason] = {v: k for k, v in _REASON_TO_PB.items()}


class UnsupportedFrameError(Exception):
    """serialize() was called with a frame type not in the dispatch table."""


class MalformedFrameError(Exception):
    """Bytes that don't parse into a known frame."""


@dataclass(frozen=True)
class Ack:
    """Wire-level ordering ack. Not a frame.

    Sent on taking an envelope onto the ordered inbound lane, which releases the
    peer's blocked send. Explicitly not "the brain has handled this".
    """

    ack_id: int


def serialize_ack(ack_id: int) -> bytes:
    """Encode a bare Ack envelope."""
    env = pb.Envelope()
    env.ack.ack_id = ack_id
    return env.SerializeToString()


@dataclass(frozen=True)
class DecodedMessage:
    """One envelope: its frame (or ack) plus the envelope's correlation."""

    frame: Frame | None
    ack: int | None
    request_id: int = 0
    epoch: int = 0
    inference_id: int = 0


# ─── Encoders ─────────────────────────────────────────────────────────────────


def _enc_session_start(f: SessionStartFrame, env: pb.Envelope) -> None:
    m = env.session_start
    m.session_id = f.session_id
    m.agent_id = f.agent_id
    m.payload = json.dumps(f.payload)


def _enc_user_message(f: UserMessageFrame, env: pb.Envelope) -> None:
    env.user_message.text = f.text


def _enc_user_idle(f: UserIdleFrame, env: pb.Envelope) -> None:
    m = env.user_idle
    m.level = f.level
    m.idle_ms = f.idle_ms


def _enc_client_message(f: ClientMessageFrame, env: pb.Envelope) -> None:
    m = env.client_message
    m.msg_id = f.msg_id
    m.type = f.type
    m.data = json.dumps(f.data)


def _enc_interruption(f: InterruptionFrame, env: pb.Envelope) -> None:
    env.interruption.SetInParent()


def _enc_llm_start(f: LLMFullResponseStartFrame, env: pb.Envelope) -> None:
    env.llm_start.SetInParent()


def _enc_llm_text(f: LLMTextFrame, env: pb.Envelope) -> None:
    env.llm_text.text = f.text


def _enc_llm_end(f: LLMFullResponseEndFrame, env: pb.Envelope) -> None:
    env.llm_end.SetInParent()


def _enc_inference_finalized(f: InferenceFinalizedFrame, env: pb.Envelope) -> None:
    m = env.inference_finalized
    m.heard_text = f.heard_text
    m.reason = _REASON_TO_PB[f.reason]


def _enc_server_message(f: ServerMessageFrame, env: pb.Envelope) -> None:
    env.server_message.data = json.dumps(f.data)


# The wire carries the legacy `settings` dict only. A typed delta is an
# in-process object and does not travel; the receiver rebuilds the dict form.
def _enc_update_tts(f: UpdateTTSSettingsFrame, env: pb.Envelope) -> None:
    env.update_tts_settings.settings = json.dumps(dict(f.settings))


def _enc_update_stt(f: UpdateSTTSettingsFrame, env: pb.Envelope) -> None:
    env.update_stt_settings.settings = json.dumps(dict(f.settings))


def _enc_update_idle(f: UpdateIdleSettingsFrame, env: pb.Envelope) -> None:
    env.update_idle_settings.settings = json.dumps(dict(f.settings))


def _enc_end(f: EndFrame, env: pb.Envelope) -> None:
    env.end.SetInParent()


def _enc_cancel(f: CancelFrame, env: pb.Envelope) -> None:
    env.cancel.reason = "" if f.reason is None else str(f.reason)


def _enc_error(f: ErrorFrame, env: pb.Envelope) -> None:
    env.error.error = f.error
    env.error.fatal = f.fatal


_ENCODERS: dict[type[Frame], Callable[[Any, pb.Envelope], None]] = {
    SessionStartFrame: _enc_session_start,
    UserMessageFrame: _enc_user_message,
    UserIdleFrame: _enc_user_idle,
    ClientMessageFrame: _enc_client_message,
    InterruptionFrame: _enc_interruption,
    LLMFullResponseStartFrame: _enc_llm_start,
    LLMTextFrame: _enc_llm_text,
    LLMFullResponseEndFrame: _enc_llm_end,
    InferenceFinalizedFrame: _enc_inference_finalized,
    ServerMessageFrame: _enc_server_message,
    UpdateTTSSettingsFrame: _enc_update_tts,
    UpdateSTTSettingsFrame: _enc_update_stt,
    UpdateIdleSettingsFrame: _enc_update_idle,
    EndFrame: _enc_end,
    CancelFrame: _enc_cancel,
    ErrorFrame: _enc_error,
}


# ─── Decoders ─────────────────────────────────────────────────────────────────


def _dec_session_start(env: pb.Envelope) -> SessionStartFrame:
    m = env.session_start
    return SessionStartFrame(
        session_id=m.session_id,
        agent_id=m.agent_id,
        payload=json.loads(m.payload) if m.payload else {},
    )


def _dec_user_message(env: pb.Envelope) -> UserMessageFrame:
    return UserMessageFrame(text=env.user_message.text)


def _dec_user_idle(env: pb.Envelope) -> UserIdleFrame:
    m = env.user_idle
    return UserIdleFrame(level=m.level, idle_ms=m.idle_ms)


def _dec_client_message(env: pb.Envelope) -> ClientMessageFrame:
    m = env.client_message
    return ClientMessageFrame(
        msg_id=m.msg_id,
        type=m.type,
        data=json.loads(m.data) if m.data else {},
    )


def _dec_interruption(env: pb.Envelope) -> InterruptionFrame:
    return InterruptionFrame()


def _dec_llm_start(env: pb.Envelope) -> LLMFullResponseStartFrame:
    return LLMFullResponseStartFrame()


def _dec_llm_text(env: pb.Envelope) -> LLMTextFrame:
    return LLMTextFrame(text=env.llm_text.text)


def _dec_llm_end(env: pb.Envelope) -> LLMFullResponseEndFrame:
    return LLMFullResponseEndFrame()


def _dec_inference_finalized(env: pb.Envelope) -> InferenceFinalizedFrame:
    m = env.inference_finalized
    return InferenceFinalizedFrame(
        heard_text=m.heard_text,
        reason=_REASON_FROM_PB.get(m.reason, FinalizeReason.COMPLETED),
    )


def _dec_server_message(env: pb.Envelope) -> ServerMessageFrame:
    d = env.server_message.data
    return ServerMessageFrame(data=json.loads(d) if d else None)


def _dec_update_tts(env: pb.Envelope) -> UpdateTTSSettingsFrame:
    s = env.update_tts_settings.settings
    return UpdateTTSSettingsFrame(settings=json.loads(s) if s else {})


def _dec_update_stt(env: pb.Envelope) -> UpdateSTTSettingsFrame:
    s = env.update_stt_settings.settings
    return UpdateSTTSettingsFrame(settings=json.loads(s) if s else {})


def _dec_update_idle(env: pb.Envelope) -> UpdateIdleSettingsFrame:
    s = env.update_idle_settings.settings
    return UpdateIdleSettingsFrame(settings=json.loads(s) if s else {})


def _dec_end(env: pb.Envelope) -> EndFrame:
    return EndFrame()


def _dec_cancel(env: pb.Envelope) -> CancelFrame:
    r = env.cancel.reason
    return CancelFrame(reason=r or None)


def _dec_error(env: pb.Envelope) -> ErrorFrame:
    return ErrorFrame(error=env.error.error, fatal=env.error.fatal)


_DECODERS: dict[str, Callable[[pb.Envelope], Frame]] = {
    "session_start": _dec_session_start,
    "user_message": _dec_user_message,
    "user_idle": _dec_user_idle,
    "client_message": _dec_client_message,
    "interruption": _dec_interruption,
    "llm_start": _dec_llm_start,
    "llm_text": _dec_llm_text,
    "llm_end": _dec_llm_end,
    "inference_finalized": _dec_inference_finalized,
    "server_message": _dec_server_message,
    "update_tts_settings": _dec_update_tts,
    "update_stt_settings": _dec_update_stt,
    "update_idle_settings": _dec_update_idle,
    "end": _dec_end,
    "cancel": _dec_cancel,
    "error": _dec_error,
}


# ─── Serializer ───────────────────────────────────────────────────────────────


class CortexFrameSerializer:
    """Binary protobuf codec for the cortex wire.

    Stateless. ``serialize`` / ``deserialize`` stay ``async`` for call-site
    symmetry, though nothing awaits.
    """

    async def serialize(
        self,
        frame: Frame,
        *,
        request_id: int = 0,
        epoch: int = 0,
        inference_id: int = 0,
    ) -> bytes:
        encoder = _ENCODERS.get(type(frame))
        if encoder is None:
            raise UnsupportedFrameError(
                f"No encoder registered for frame type {type(frame).__name__!r}. "
                "Add it to _ENCODERS in serializer.py and to the proto schema."
            )
        env = pb.Envelope()
        encoder(frame, env)
        if request_id:
            env.request_id = request_id
        if epoch:
            env.epoch = epoch
        if inference_id:
            env.inference_id = inference_id
        return env.SerializeToString()

    async def deserialize(self, data: str | bytes) -> Frame:
        decoded = self._decode_envelope(data)
        if decoded.frame is None:
            raise MalformedFrameError(
                "Received Ack-only envelope via deserialize(); call deserialize_message() instead."
            )
        return decoded.frame

    async def deserialize_message(self, data: str | bytes) -> DecodedMessage:
        """Decode an envelope, skipping a body this build does not know."""
        return self._decode_envelope(data, strict=False)

    def _decode_envelope(self, data: str | bytes, *, strict: bool = True) -> DecodedMessage:
        if isinstance(data, str):
            raise MalformedFrameError("CortexFrameSerializer is binary; got str input.")
        env = pb.Envelope()
        try:
            env.ParseFromString(data)
        except Exception as exc:
            raise MalformedFrameError(f"Envelope parse failed: {exc}") from exc

        corr: dict[str, int] = {
            "request_id": env.request_id,
            "epoch": env.epoch,
            "inference_id": env.inference_id,
        }

        which = env.WhichOneof("body")
        if which is None:
            # Either a truly empty envelope or a body a newer peer added after
            # this build shipped: protobuf parks the unknown field aside and
            # reports no body.
            if strict:
                raise MalformedFrameError("Envelope has no body set.")
            logger.warning("wire: envelope with no known body (newer peer?); skipping")
            return DecodedMessage(frame=None, ack=None, **corr)

        if which == "ack":
            return DecodedMessage(frame=None, ack=env.ack.ack_id, **corr)

        decoder = _DECODERS.get(which)
        if decoder is None:
            if strict:
                raise MalformedFrameError(
                    f"Envelope body {which!r} has no decoder. Schema and serializer drift?"
                )
            logger.warning("wire: envelope body {!r} has no decoder; skipping", which)
            return DecodedMessage(frame=None, ack=None, **corr)
        try:
            return DecodedMessage(frame=decoder(env), ack=None, **corr)
        except Exception as exc:
            raise MalformedFrameError(f"Decoder for {which!r} failed: {exc}") from exc


# Import-time check that every frame class has an encoder, so "added a frame but
# forgot to wire it" fails before the tests run.
_missing = [c.__name__ for c in WIRE_FRAME_CLASSES if c not in _ENCODERS]
if _missing:  # pragma: no cover — asserted by test_dispatch_completeness
    raise RuntimeError(
        f"Frame classes without encoder: {_missing}. Update _ENCODERS in serializer.py."
    )
