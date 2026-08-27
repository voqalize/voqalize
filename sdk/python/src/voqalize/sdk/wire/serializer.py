"""Protobuf serializer for the wire.

Transcodes between the plain dataclasses in :mod:`.frames` and ``Envelope``
bytes. Pipecat-free, stateless, no base class.

The envelope is the ``oneof`` and nothing else, so a frame carries everything it
needs and nothing travels beside it.

``deserialize`` is strict and raises on anything it cannot decode.
``deserialize_message`` — the entry point the read loops use — is
forward-compatible: corrupt bytes still raise, but an envelope whose body this
build does not know is logged and skipped, since a newer peer may send a frame
added after this SDK shipped.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from loguru import logger

from . import _frames_pb2 as pb
from .frames import (
    WIRE_FRAME_CLASSES,
    CancelFrame,
    Config,
    ConfigureFrame,
    EndFrame,
    ErrorCode,
    ErrorFrame,
    FinalizeFrame,
    Frame,
    IdleConfig,
    InterruptionFrame,
    Language,
    ResponseFrame,
    RTVIFrame,
    RTVIType,
    SessionStartFrame,
    SpeechChunkFrame,
    SpeechEndFrame,
    SpeechStartFrame,
    SttConfig,
    TtsConfig,
    UserIdleFrame,
    UserMessageFrame,
    Voice,
)

_CODE_TO_PB: dict[ErrorCode, int] = {
    ErrorCode.PROTOCOL: pb.ERROR_CODE_PROTOCOL,
    ErrorCode.WIRE_VERSION: pb.ERROR_CODE_WIRE_VERSION,
    ErrorCode.REJECTED: pb.ERROR_CODE_REJECTED,
    ErrorCode.OVERLOAD: pb.ERROR_CODE_OVERLOAD,
    ErrorCode.INTERNAL: pb.ERROR_CODE_INTERNAL,
}
_CODE_FROM_PB: dict[int, ErrorCode] = {v: k for k, v in _CODE_TO_PB.items()}

_RTVI_TO_PB: dict[RTVIType, int] = {
    RTVIType.SERVER_MESSAGE: pb.RTVI_TYPE_SERVER_MESSAGE,
    RTVIType.SERVER_RESPONSE: pb.RTVI_TYPE_SERVER_RESPONSE,
    RTVIType.ERROR_RESPONSE: pb.RTVI_TYPE_ERROR_RESPONSE,
    RTVIType.UI_COMMAND: pb.RTVI_TYPE_UI_COMMAND,
    RTVIType.UI_JOB_GROUP: pb.RTVI_TYPE_UI_JOB_GROUP,
    RTVIType.CLIENT_MESSAGE: pb.RTVI_TYPE_CLIENT_MESSAGE,
    RTVIType.SEND_TEXT: pb.RTVI_TYPE_SEND_TEXT,
    RTVIType.UI_EVENT: pb.RTVI_TYPE_UI_EVENT,
    RTVIType.UI_SNAPSHOT: pb.RTVI_TYPE_UI_SNAPSHOT,
    RTVIType.UI_CANCEL_JOB_GROUP: pb.RTVI_TYPE_UI_CANCEL_JOB_GROUP,
}
_RTVI_FROM_PB: dict[int, RTVIType] = {v: k for k, v in _RTVI_TO_PB.items()}

_VOICE_TO_PB: dict[Voice, int] = {
    Voice.OMNIVOICE_GAURI: pb.VOICE_OMNIVOICE_GAURI,
    Voice.OMNIVOICE_GAURAV: pb.VOICE_OMNIVOICE_GAURAV,
}
_PB_TO_VOICE: dict[int, Voice] = {v: k for k, v in _VOICE_TO_PB.items()}

# Read out of the descriptor rather than written down again. `Language`'s values
# *are* the `iso_code` option — a hand-kept table of twenty-three rows is the
# drift the option exists to prevent, and this raises at import if the two ever
# disagree rather than mistranslating one language at runtime.
_ISO_CODE = pb.DESCRIPTOR.extensions_by_name["iso_code"]
_PB_TO_LANG: dict[int, Language] = {
    value.number: Language(value.GetOptions().Extensions[_ISO_CODE])
    for value in pb.Language.DESCRIPTOR.values
    if value.number != 0
}
_LANG_TO_PB: dict[Language, int] = {v: k for k, v in _PB_TO_LANG.items()}


class UnsupportedFrameError(Exception):
    """serialize() was called with a frame type not in the dispatch table."""


class MalformedFrameError(Exception):
    """Bytes that don't parse into a known frame."""


# ─── Encoders ─────────────────────────────────────────────────────────────────


def _enc_session_start(f: SessionStartFrame, env: pb.Envelope) -> None:
    m = env.session_start
    m.turn_id = f.turn_id
    m.session_id = f.session_id
    m.init = json.dumps(f.init)
    m.wire_version = f.wire_version


def _enc_user_message(f: UserMessageFrame, env: pb.Envelope) -> None:
    m = env.user_message
    m.turn_id = f.turn_id
    m.text = f.text


def _enc_user_idle(f: UserIdleFrame, env: pb.Envelope) -> None:
    m = env.user_idle
    m.turn_id = f.turn_id
    m.level = f.level
    m.idle_ms = f.idle_ms


def _enc_interruption(f: InterruptionFrame, env: pb.Envelope) -> None:
    env.interruption.through_turn = f.through_turn


def _enc_finalize(f: FinalizeFrame, env: pb.Envelope) -> None:
    m = env.finalize
    m.speech_id = f.speech_id
    m.heard_text = f.heard_text


def _enc_speech_start(f: SpeechStartFrame, env: pb.Envelope) -> None:
    m = env.speech_start
    m.speech_id = f.speech_id
    m.turn_id = f.turn_id


def _enc_speech_chunk(f: SpeechChunkFrame, env: pb.Envelope) -> None:
    m = env.speech_chunk
    m.speech_id = f.speech_id
    m.text = f.text


def _enc_speech_end(f: SpeechEndFrame, env: pb.Envelope) -> None:
    env.speech_end.speech_id = f.speech_id


# The op arm is set explicitly, so a request carrying no delta at all still names
# the op it is — an empty delta is a legal no-op the runtime answers, not a body
# the far side cannot identify.
def _enc_configure(f: ConfigureFrame, env: pb.Envelope) -> None:
    env.request.request_id = f.request_id
    m = env.request.configure
    m.SetInParent()
    c = f.config
    if c.tts is not None:
        m.tts.SetInParent()
        if c.tts.voice is not None:
            m.tts.voice = _VOICE_TO_PB[c.tts.voice]
        if c.tts.language is not None:
            m.tts.language = _LANG_TO_PB[c.tts.language]
    if c.stt is not None:
        m.stt.SetInParent()
        if c.stt.language is not None:
            m.stt.language = _LANG_TO_PB[c.stt.language]
    if c.idle is not None:
        m.idle.SetInParent()
        if c.idle.timeout_ms is not None:
            m.idle.timeout_ms = c.idle.timeout_ms


def _enc_response(f: ResponseFrame, env: pb.Envelope) -> None:
    m = env.response
    m.request_id = f.request_id
    m.status = pb.STATUS_ACCEPTED if f.accepted else pb.STATUS_REJECTED
    m.detail = f.detail


def _enc_rtvi(f: RTVIFrame, env: pb.Envelope) -> None:
    m = env.rtvi
    m.type = _RTVI_TO_PB[f.type]
    m.data = json.dumps(f.data)
    if f.id is not None:
        m.id = f.id
    if f.turn_id is not None:
        m.turn_id = f.turn_id


def _enc_end(f: EndFrame, env: pb.Envelope) -> None:
    env.end.SetInParent()


def _enc_cancel(f: CancelFrame, env: pb.Envelope) -> None:
    env.cancel.reason = "" if f.reason is None else str(f.reason)


def _enc_error(f: ErrorFrame, env: pb.Envelope) -> None:
    m = env.error
    m.code = _CODE_TO_PB[f.code]
    m.message = f.message
    m.fatal = f.fatal


_ENCODERS: dict[type[Frame], Callable[[Any, pb.Envelope], None]] = {
    SessionStartFrame: _enc_session_start,
    UserMessageFrame: _enc_user_message,
    UserIdleFrame: _enc_user_idle,
    InterruptionFrame: _enc_interruption,
    FinalizeFrame: _enc_finalize,
    SpeechStartFrame: _enc_speech_start,
    SpeechChunkFrame: _enc_speech_chunk,
    SpeechEndFrame: _enc_speech_end,
    ConfigureFrame: _enc_configure,
    ResponseFrame: _enc_response,
    RTVIFrame: _enc_rtvi,
    EndFrame: _enc_end,
    CancelFrame: _enc_cancel,
    ErrorFrame: _enc_error,
}


# ─── Decoders ─────────────────────────────────────────────────────────────────


def _dec_session_start(env: pb.Envelope) -> SessionStartFrame:
    m = env.session_start
    return SessionStartFrame(
        session_id=m.session_id,
        turn_id=m.turn_id,
        init=json.loads(m.init) if m.init else {},
        wire_version=m.wire_version,
    )


def _dec_user_message(env: pb.Envelope) -> UserMessageFrame:
    m = env.user_message
    return UserMessageFrame(turn_id=m.turn_id, text=m.text)


def _dec_user_idle(env: pb.Envelope) -> UserIdleFrame:
    m = env.user_idle
    return UserIdleFrame(turn_id=m.turn_id, level=m.level, idle_ms=m.idle_ms)


def _dec_interruption(env: pb.Envelope) -> InterruptionFrame:
    return InterruptionFrame(through_turn=env.interruption.through_turn)


def _dec_finalize(env: pb.Envelope) -> FinalizeFrame:
    m = env.finalize
    return FinalizeFrame(
        speech_id=m.speech_id,
        heard_text=m.heard_text,
    )


def _dec_speech_start(env: pb.Envelope) -> SpeechStartFrame:
    m = env.speech_start
    return SpeechStartFrame(speech_id=m.speech_id, turn_id=m.turn_id)


def _dec_speech_chunk(env: pb.Envelope) -> SpeechChunkFrame:
    m = env.speech_chunk
    return SpeechChunkFrame(speech_id=m.speech_id, text=m.text)


def _dec_speech_end(env: pb.Envelope) -> SpeechEndFrame:
    return SpeechEndFrame(speech_id=env.speech_end.speech_id)


def _dec_configure(req: pb.Request) -> ConfigureFrame:
    m = req.configure
    tts = stt = idle = None
    if m.HasField("tts"):
        tts = TtsConfig(
            voice=_PB_TO_VOICE[m.tts.voice] if m.tts.HasField("voice") else None,
            language=_PB_TO_LANG[m.tts.language] if m.tts.HasField("language") else None,
        )
    if m.HasField("stt"):
        stt = SttConfig(
            language=_PB_TO_LANG[m.stt.language] if m.stt.HasField("language") else None,
        )
    if m.HasField("idle"):
        idle = IdleConfig(
            timeout_ms=m.idle.timeout_ms if m.idle.HasField("timeout_ms") else None,
        )
    return ConfigureFrame(request_id=req.request_id, config=Config(tts=tts, stt=stt, idle=idle))


_OP_DECODERS: dict[str, Callable[[pb.Request], Frame]] = {
    "configure": _dec_configure,
}


def _dec_request(env: pb.Envelope) -> Frame:
    op = env.request.WhichOneof("op")
    decoder = _OP_DECODERS.get(op or "")
    if decoder is None:
        raise MalformedFrameError(f"Request names op {op!r}, which this build has no decoder for.")
    return decoder(env.request)


def _dec_response(env: pb.Envelope) -> ResponseFrame:
    m = env.response
    return ResponseFrame(
        request_id=m.request_id,
        accepted=m.status == pb.STATUS_ACCEPTED,
        detail=m.detail,
    )


def _dec_rtvi(env: pb.Envelope) -> RTVIFrame:
    m = env.rtvi
    rtvi_type = _RTVI_FROM_PB.get(m.type)
    if rtvi_type is None:
        raise MalformedFrameError(f"RTVI type {m.type} is not one this build carries.")
    return RTVIFrame(
        type=rtvi_type,
        data=json.loads(m.data) if m.data else None,
        id=m.id if m.HasField("id") else None,
        turn_id=m.turn_id if m.HasField("turn_id") else None,
    )


def _dec_end(env: pb.Envelope) -> EndFrame:
    return EndFrame()


def _dec_cancel(env: pb.Envelope) -> CancelFrame:
    r = env.cancel.reason
    return CancelFrame(reason=r or None)


def _dec_error(env: pb.Envelope) -> ErrorFrame:
    m = env.error
    return ErrorFrame(
        code=_CODE_FROM_PB.get(m.code, ErrorCode.INTERNAL),
        message=m.message,
        fatal=m.fatal,
    )


_DECODERS: dict[str, Callable[[pb.Envelope], Frame]] = {
    "session_start": _dec_session_start,
    "user_message": _dec_user_message,
    "user_idle": _dec_user_idle,
    "interruption": _dec_interruption,
    "finalize": _dec_finalize,
    "speech_start": _dec_speech_start,
    "speech_chunk": _dec_speech_chunk,
    "speech_end": _dec_speech_end,
    "request": _dec_request,
    "response": _dec_response,
    "rtvi": _dec_rtvi,
    "end": _dec_end,
    "cancel": _dec_cancel,
    "error": _dec_error,
}


# ─── Serializer ───────────────────────────────────────────────────────────────


class WireSerializer:
    """Binary protobuf serializer for the wire.

    Stateless. ``serialize`` / ``deserialize`` stay ``async`` for call-site
    symmetry, though nothing awaits.
    """

    async def serialize(self, frame: Frame) -> bytes:
        encoder = _ENCODERS.get(type(frame))
        if encoder is None:
            raise UnsupportedFrameError(
                f"No encoder registered for frame type {type(frame).__name__!r}. "
                "Add it to _ENCODERS in serializer.py and to the proto schema."
            )
        env = pb.Envelope()
        encoder(frame, env)
        return env.SerializeToString()

    async def deserialize(self, data: str | bytes) -> Frame:
        frame = self._decode(data)
        if frame is None:  # unreachable: strict decoding raises on a bodyless envelope
            raise MalformedFrameError("Envelope has no body set.")
        return frame

    async def deserialize_message(self, data: str | bytes) -> Frame | None:
        """Decode an envelope, skipping a body this build does not know."""
        return self._decode(data, strict=False)

    def _decode(self, data: str | bytes, *, strict: bool = True) -> Frame | None:
        if isinstance(data, str):
            raise MalformedFrameError("WireSerializer is binary; got str input.")
        env = pb.Envelope()
        try:
            env.ParseFromString(data)
        except Exception as exc:
            raise MalformedFrameError(f"Envelope parse failed: {exc}") from exc

        which = env.WhichOneof("body")
        if which is None:
            # Either a truly empty envelope or a body a newer peer added after
            # this build shipped: protobuf parks the unknown field aside and
            # reports no body.
            if strict:
                raise MalformedFrameError("Envelope has no body set.")
            logger.warning("wire: envelope with no known body (newer peer?); skipping")
            return None

        decoder = _DECODERS.get(which)
        if decoder is None:
            if strict:
                raise MalformedFrameError(
                    f"Envelope body {which!r} has no decoder. Schema and serializer drift?"
                )
            logger.warning("wire: envelope body {!r} has no decoder; skipping", which)
            return None
        try:
            return decoder(env)
        except Exception as exc:
            raise MalformedFrameError(f"Decoder for {which!r} failed: {exc}") from exc


# Import-time check that every frame class has an encoder, so "added a frame but
# forgot to wire it" fails before the tests run.
_missing = [c.__name__ for c in WIRE_FRAME_CLASSES if c not in _ENCODERS]
if _missing:  # pragma: no cover — asserted by test_dispatch_completeness
    raise RuntimeError(
        f"Frame classes without encoder: {_missing}. Update _ENCODERS in serializer.py."
    )
