"""Protobuf serializer for the cortex wire.

Converts between the SDK's plain-dataclass ``Frame`` types (Vql frames +
lifecycle/RTVI twins, all defined in :mod:`.frames`) and ``Envelope`` protobuf
bytes. Pipecat-free — a pure transcoder with no base class.

Serializing an unsupported frame is a programmer error and raises
`UnsupportedFrameError`. On decode, `deserialize()` is strict (raises
`MalformedFrameError` on a malformed / unknown envelope), while
`deserialize_message()` — the entry point the wire read loops use — is
forward-compatible: corrupt bytes still raise, but an envelope whose body this
build does not know is logged and skipped, since a newer PyGato may legitimately
send a frame added after this SDK shipped.

In addition to pipecat frames, the wire carries `Ack` envelopes — ordering
acks the SDK emits after the customer's `process_frame` returns for a given
data frame. Acks are wire-level (not pipecat Frames), exposed via
`serialize_ack` / `deserialize_message`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from loguru import logger

from . import _frames_pb2 as pb
from .frames import (
    VQL_FRAME_CLASSES,
    CancelFrame,
    EndFrame,
    ErrorFrame,
    FinalizeReason,
    Frame,
    IdleUpdateSettingsFrame,
    InterruptionFrame,
    RTVIServerMessageFrame,
    STTUpdateSettingsFrame,
    TTSUpdateSettingsFrame,
    VqlFunctionCallInProgressFrame,
    VqlFunctionCallResultFrame,
    VqlFunctionCallsStartedFrame,
    VqlInferenceFinalizedFrame,
    VqlInteractionCompletedFrame,
    VqlLLMFullResponseEndFrame,
    VqlLLMFullResponseStartFrame,
    VqlLLMTextFrame,
    VqlRTVIClientMessageFrame,
    VqlStartFrame,
    VqlUserIdleFrame,
    VqlUserTextFrame,
)

# FinalizeReason ↔ protobuf enum. UNSPECIFIED never appears on the wire (the
# sender always sets a reason); decode falls back to COMPLETED defensively.
_REASON_TO_PB: dict[FinalizeReason, int] = {
    FinalizeReason.COMPLETED: pb.FINALIZE_REASON_COMPLETED,
    FinalizeReason.USER_BARGE_IN: pb.FINALIZE_REASON_USER_BARGE_IN,
}
_REASON_FROM_PB: dict[int, FinalizeReason] = {v: k for k, v in _REASON_TO_PB.items()}


class UnsupportedFrameError(Exception):
    """Raised when serialize() is called with a frame type not in the dispatch table."""


class MalformedFrameError(Exception):
    """Raised when deserialize() receives bytes that don't parse into a known frame."""


@dataclass(frozen=True)
class Ack:
    """Wire-level ordering ack. Not a pipecat Frame.

    Emitted by this SDK after the customer's `process_frame` returns for a
    data frame the bridge sent. The bridge resolves a pending future keyed
    by `ack_id` to unblock its own `process_frame`, releasing the next
    buffered frame in arrival order.
    """

    ack_id: int


def serialize_ack(ack_id: int) -> bytes:
    """Encode a wire-level Ack envelope. Bridge/SDK-internal — not a Frame."""
    env = pb.Envelope()
    env.ack.ack_id = ack_id
    return env.SerializeToString()


@dataclass(frozen=True)
class DecodedMessage:
    """One envelope's worth of decoded wire data.

    `frame` is the pipecat Frame (or None for pure-ack envelopes).
    `ack` is the ack_id of an Ack envelope (or None).
    `request_id` is non-zero on frames that expect an ack back when
    `process_frame` has finished consuming them.
    """

    frame: Frame | None
    ack: int | None
    request_id: int


# ─── Encoders (Frame → Envelope) ──────────────────────────────────────────────


def _encode_vql_start(f: VqlStartFrame, env: pb.Envelope) -> None:
    m = env.vql_start
    m.session_id = f.session_id
    m.agent_id = f.agent_id
    m.payload = json.dumps(f.payload)
    m.audio_in_sample_rate = f.audio_in_sample_rate
    m.audio_out_sample_rate = f.audio_out_sample_rate
    m.enable_metrics = f.enable_metrics
    m.enable_tracing = f.enable_tracing
    m.enable_usage_metrics = f.enable_usage_metrics
    m.report_only_initial_ttfb = f.report_only_initial_ttfb


def _encode_vql_user_text(f: VqlUserTextFrame, env: pb.Envelope) -> None:
    env.vql_user_text.interaction_id = f.interaction_id
    env.vql_user_text.text = f.text


def _encode_vql_interruption(f: InterruptionFrame, env: pb.Envelope) -> None:
    # Field-less signal; maps to pipecat's native InterruptionFrame on decode.
    env.vql_interruption.SetInParent()


def _encode_vql_inference_finalized(f: VqlInferenceFinalizedFrame, env: pb.Envelope) -> None:
    m = env.vql_inference_finalized
    m.interaction_id = f.interaction_id
    m.inference_id = f.inference_id
    m.heard_text = f.heard_text
    m.interrupted = f.interrupted
    m.reason = _REASON_TO_PB[f.reason]


def _encode_vql_llm_start(f: VqlLLMFullResponseStartFrame, env: pb.Envelope) -> None:
    env.vql_llm_start.interaction_id = f.interaction_id
    env.vql_llm_start.inference_id = f.inference_id


def _encode_vql_llm_text(f: VqlLLMTextFrame, env: pb.Envelope) -> None:
    env.vql_llm_text.interaction_id = f.interaction_id
    env.vql_llm_text.inference_id = f.inference_id
    env.vql_llm_text.text = f.text


def _encode_vql_llm_end(f: VqlLLMFullResponseEndFrame, env: pb.Envelope) -> None:
    env.vql_llm_end.interaction_id = f.interaction_id
    env.vql_llm_end.inference_id = f.inference_id


def _encode_vql_fc_started(f: VqlFunctionCallsStartedFrame, env: pb.Envelope) -> None:
    m = env.vql_fc_started
    m.interaction_id = f.interaction_id
    m.inference_id = f.inference_id
    m.tool_call_id = f.tool_call_id
    m.function_name = f.function_name
    m.arguments = json.dumps(f.arguments)


def _encode_vql_fc_in_progress(f: VqlFunctionCallInProgressFrame, env: pb.Envelope) -> None:
    m = env.vql_fc_in_progress
    m.interaction_id = f.interaction_id
    m.inference_id = f.inference_id
    m.tool_call_id = f.tool_call_id
    m.function_name = f.function_name
    m.arguments = json.dumps(f.arguments)


def _encode_vql_fc_result(f: VqlFunctionCallResultFrame, env: pb.Envelope) -> None:
    m = env.vql_fc_result
    m.interaction_id = f.interaction_id
    m.inference_id = f.inference_id
    m.tool_call_id = f.tool_call_id
    m.function_name = f.function_name
    m.result = json.dumps(f.result)


def _encode_vql_interaction_completed(f: VqlInteractionCompletedFrame, env: pb.Envelope) -> None:
    env.vql_interaction_completed.interaction_id = f.interaction_id


def _encode_end(f: EndFrame, env: pb.Envelope) -> None:
    env.end.SetInParent()


def _encode_cancel(f: CancelFrame, env: pb.Envelope) -> None:
    # Pipecat CancelFrame.reason is `Any | None`; coerce to str on the wire.
    env.cancel.reason = "" if f.reason is None else str(f.reason)


def _encode_error(f: ErrorFrame, env: pb.Envelope) -> None:
    env.error.error = f.error
    env.error.fatal = f.fatal


def _encode_rtvi_server_message(f: RTVIServerMessageFrame, env: pb.Envelope) -> None:
    env.rtvi_server_message.data = json.dumps(f.data)


def _encode_rtvi_client_message(f: VqlRTVIClientMessageFrame, env: pb.Envelope) -> None:
    # Envelope field 37 — the same key older pygato/SDKs already speak. The
    # Voice-minted stamp is an appended optional field, so a peer that predates
    # it still decodes msg_id/type/data and simply sees no interaction_id.
    m = env.rtvi_client_message
    m.interaction_id = f.interaction_id
    m.msg_id = f.msg_id
    m.type = f.type
    m.data = json.dumps(f.data)


def _encode_stt_update_settings(f: STTUpdateSettingsFrame, env: pb.Envelope) -> None:
    # Wire carries the legacy `settings` dict only. `delta` is a typed
    # in-process object (not portable); `service` is an in-process reference
    # (never portable). The receiver reconstructs an STTUpdateSettingsFrame
    # from the dict; pipecat converts to a typed delta with a deprecation
    # warning at apply time.
    env.stt_update_settings.settings = json.dumps(dict(f.settings))


def _encode_tts_update_settings(f: TTSUpdateSettingsFrame, env: pb.Envelope) -> None:
    env.tts_update_settings.settings = json.dumps(dict(f.settings))


def _encode_idle_update_settings(f: IdleUpdateSettingsFrame, env: pb.Envelope) -> None:
    env.idle_update_settings.settings = json.dumps(dict(f.settings))


def _encode_vql_user_idle(f: VqlUserIdleFrame, env: pb.Envelope) -> None:
    m = env.vql_user_idle
    m.interaction_id = f.interaction_id
    m.level = f.level
    m.idle_ms = f.idle_ms


# Class-keyed dispatch. VqlStartFrame is checked before StartFrame because the
# subclass must win (otherwise StartFrame's encoder would fire and miss the
# Vql fields).
_ENCODERS: dict[type[Frame], Callable[[Any, pb.Envelope], None]] = {
    VqlStartFrame: _encode_vql_start,
    VqlUserTextFrame: _encode_vql_user_text,
    VqlUserIdleFrame: _encode_vql_user_idle,
    VqlRTVIClientMessageFrame: _encode_rtvi_client_message,
    InterruptionFrame: _encode_vql_interruption,
    VqlInferenceFinalizedFrame: _encode_vql_inference_finalized,
    VqlLLMFullResponseStartFrame: _encode_vql_llm_start,
    VqlLLMTextFrame: _encode_vql_llm_text,
    VqlLLMFullResponseEndFrame: _encode_vql_llm_end,
    VqlInteractionCompletedFrame: _encode_vql_interaction_completed,
    VqlFunctionCallsStartedFrame: _encode_vql_fc_started,
    VqlFunctionCallInProgressFrame: _encode_vql_fc_in_progress,
    VqlFunctionCallResultFrame: _encode_vql_fc_result,
    EndFrame: _encode_end,
    CancelFrame: _encode_cancel,
    ErrorFrame: _encode_error,
    RTVIServerMessageFrame: _encode_rtvi_server_message,
    STTUpdateSettingsFrame: _encode_stt_update_settings,
    TTSUpdateSettingsFrame: _encode_tts_update_settings,
    IdleUpdateSettingsFrame: _encode_idle_update_settings,
}


# ─── Decoders (Envelope → Frame) ──────────────────────────────────────────────


def _decode_vql_start(env: pb.Envelope) -> VqlStartFrame:
    m = env.vql_start
    return VqlStartFrame(
        session_id=m.session_id,
        agent_id=m.agent_id,
        payload=json.loads(m.payload),
        audio_in_sample_rate=m.audio_in_sample_rate,
        audio_out_sample_rate=m.audio_out_sample_rate,
        enable_metrics=m.enable_metrics,
        enable_tracing=m.enable_tracing,
        enable_usage_metrics=m.enable_usage_metrics,
        report_only_initial_ttfb=m.report_only_initial_ttfb,
    )


def _decode_vql_user_text(env: pb.Envelope) -> VqlUserTextFrame:
    m = env.vql_user_text
    return VqlUserTextFrame(interaction_id=m.interaction_id, text=m.text)


def _decode_vql_interruption(env: pb.Envelope) -> InterruptionFrame:
    # Field-less; reconstruct pipecat's native InterruptionFrame so the receiving
    # pipeline runs its own broadcast_interruption cancel+reset.
    return InterruptionFrame()


def _decode_vql_inference_finalized(env: pb.Envelope) -> VqlInferenceFinalizedFrame:
    m = env.vql_inference_finalized
    return VqlInferenceFinalizedFrame(
        interaction_id=m.interaction_id,
        inference_id=m.inference_id,
        heard_text=m.heard_text,
        interrupted=m.interrupted,
        reason=_REASON_FROM_PB.get(m.reason, FinalizeReason.COMPLETED),
    )


def _decode_vql_llm_start(env: pb.Envelope) -> VqlLLMFullResponseStartFrame:
    m = env.vql_llm_start
    return VqlLLMFullResponseStartFrame(
        interaction_id=m.interaction_id, inference_id=m.inference_id
    )


def _decode_vql_llm_text(env: pb.Envelope) -> VqlLLMTextFrame:
    m = env.vql_llm_text
    return VqlLLMTextFrame(
        interaction_id=m.interaction_id, inference_id=m.inference_id, text=m.text
    )


def _decode_vql_llm_end(env: pb.Envelope) -> VqlLLMFullResponseEndFrame:
    m = env.vql_llm_end
    return VqlLLMFullResponseEndFrame(interaction_id=m.interaction_id, inference_id=m.inference_id)


def _decode_vql_fc_started(env: pb.Envelope) -> VqlFunctionCallsStartedFrame:
    m = env.vql_fc_started
    return VqlFunctionCallsStartedFrame(
        interaction_id=m.interaction_id,
        inference_id=m.inference_id,
        tool_call_id=m.tool_call_id,
        function_name=m.function_name,
        arguments=json.loads(m.arguments),
    )


def _decode_vql_fc_in_progress(env: pb.Envelope) -> VqlFunctionCallInProgressFrame:
    m = env.vql_fc_in_progress
    return VqlFunctionCallInProgressFrame(
        interaction_id=m.interaction_id,
        inference_id=m.inference_id,
        tool_call_id=m.tool_call_id,
        function_name=m.function_name,
        arguments=json.loads(m.arguments),
    )


def _decode_vql_fc_result(env: pb.Envelope) -> VqlFunctionCallResultFrame:
    m = env.vql_fc_result
    return VqlFunctionCallResultFrame(
        interaction_id=m.interaction_id,
        inference_id=m.inference_id,
        tool_call_id=m.tool_call_id,
        function_name=m.function_name,
        result=json.loads(m.result),
    )


def _decode_vql_interaction_completed(env: pb.Envelope) -> VqlInteractionCompletedFrame:
    return VqlInteractionCompletedFrame(interaction_id=env.vql_interaction_completed.interaction_id)


def _decode_end(env: pb.Envelope) -> EndFrame:
    return EndFrame()


def _decode_cancel(env: pb.Envelope) -> CancelFrame:
    return CancelFrame(reason=env.cancel.reason or None)


def _decode_error(env: pb.Envelope) -> ErrorFrame:
    return ErrorFrame(error=env.error.error, fatal=env.error.fatal)


def _decode_rtvi_server_message(env: pb.Envelope) -> RTVIServerMessageFrame:
    return RTVIServerMessageFrame(data=json.loads(env.rtvi_server_message.data))


def _decode_rtvi_client_message(env: pb.Envelope) -> VqlRTVIClientMessageFrame:
    m = env.rtvi_client_message
    return VqlRTVIClientMessageFrame(
        # 0 when the sender predates the stamp (an older pygato that only sets
        # msg_id/type/data). Voice mints real ids from 1, so 0 can never collide
        # with a live interaction — it reads as "unstamped".
        interaction_id=m.interaction_id,
        msg_id=m.msg_id,
        type=m.type,
        data=json.loads(m.data),
    )


def _decode_stt_update_settings(env: pb.Envelope) -> STTUpdateSettingsFrame:
    return STTUpdateSettingsFrame(settings=json.loads(env.stt_update_settings.settings))


def _decode_tts_update_settings(env: pb.Envelope) -> TTSUpdateSettingsFrame:
    return TTSUpdateSettingsFrame(settings=json.loads(env.tts_update_settings.settings))


def _decode_idle_update_settings(env: pb.Envelope) -> IdleUpdateSettingsFrame:
    return IdleUpdateSettingsFrame(settings=json.loads(env.idle_update_settings.settings))


def _decode_vql_user_idle(env: pb.Envelope) -> VqlUserIdleFrame:
    m = env.vql_user_idle
    return VqlUserIdleFrame(interaction_id=m.interaction_id, level=m.level, idle_ms=m.idle_ms)


# Oneof-name-keyed decoder dispatch. Names match the proto field names.
_DECODERS: dict[str, Callable[[pb.Envelope], Frame]] = {
    "vql_start": _decode_vql_start,
    "vql_user_text": _decode_vql_user_text,
    "vql_user_idle": _decode_vql_user_idle,
    "rtvi_client_message": _decode_rtvi_client_message,
    "vql_interruption": _decode_vql_interruption,
    "vql_inference_finalized": _decode_vql_inference_finalized,
    "vql_llm_start": _decode_vql_llm_start,
    "vql_llm_text": _decode_vql_llm_text,
    "vql_llm_end": _decode_vql_llm_end,
    "vql_interaction_completed": _decode_vql_interaction_completed,
    "vql_fc_started": _decode_vql_fc_started,
    "vql_fc_in_progress": _decode_vql_fc_in_progress,
    "vql_fc_result": _decode_vql_fc_result,
    "idle_update_settings": _decode_idle_update_settings,
    "end": _decode_end,
    "cancel": _decode_cancel,
    "error": _decode_error,
}


# ─── Serializer ───────────────────────────────────────────────────────────────


class CortexFrameSerializer:
    """Binary protobuf serializer for the cortex wire.

    Pure transcoder — no internal state, no base class. ``serialize`` /
    ``deserialize`` stay ``async`` for call-site symmetry, though nothing awaits.
    """

    async def serialize(self, frame: Frame, *, request_id: int = 0) -> bytes:
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
        return env.SerializeToString()

    async def deserialize(self, data: str | bytes) -> Frame:
        decoded = self._decode_envelope(data)
        if decoded.frame is None:
            raise MalformedFrameError(
                "Received Ack-only envelope via deserialize(); call deserialize_message() instead."
            )
        return decoded.frame

    async def deserialize_message(self, data: str | bytes) -> DecodedMessage:
        """Decode an envelope. Returns the frame (or ack) plus any request_id.

        Forward-compatible: an envelope carrying a body this build does not know
        (a newer peer sent a frame added after this SDK was released — protobuf
        files it away as an unknown field, so ``WhichOneof`` reports nothing) is
        **skipped with a warning**, not raised on. Envelope fields are add-only
        and new frames are default-off, so ignoring one leaves the Brain behaving
        exactly as before. Genuinely corrupt bytes still raise.
        """
        return self._decode_envelope(data, strict=False)

    def _decode_envelope(self, data: str | bytes, *, strict: bool = True) -> DecodedMessage:
        if isinstance(data, str):
            raise MalformedFrameError("CortexFrameSerializer is binary; got str input.")
        env = pb.Envelope()
        try:
            env.ParseFromString(data)
        except Exception as exc:
            raise MalformedFrameError(f"Envelope parse failed: {exc}") from exc

        request_id = env.request_id

        which = env.WhichOneof("body")
        if which is None:
            # Either a truly empty envelope or — the case that matters — a frame
            # a NEWER peer added after this SDK shipped: protobuf parks the
            # unknown field aside and reports no body. Skip it.
            if strict:
                raise MalformedFrameError("Envelope has no body set.")
            logger.warning(
                "wire: envelope with no known body (unknown/newer frame?); skipping. "
                "Envelope fields are add-only and new frames are default-off, so this is safe."
            )
            return DecodedMessage(frame=None, ack=None, request_id=request_id)

        if which == "ack":
            return DecodedMessage(frame=None, ack=env.ack.ack_id, request_id=request_id)

        decoder = _DECODERS.get(which)
        if decoder is None:
            # In our schema but nothing maps it — a frame this side deliberately
            # does not consume, or genuine schema/serializer drift.
            if strict:
                raise MalformedFrameError(
                    f"Envelope body {which!r} has no decoder. Schema and serializer drift?"
                )
            logger.warning("wire: envelope body {!r} has no decoder; skipping", which)
            return DecodedMessage(frame=None, ack=None, request_id=request_id)
        try:
            return DecodedMessage(frame=decoder(env), ack=None, request_id=request_id)
        except Exception as exc:
            raise MalformedFrameError(f"Decoder for {which!r} failed: {exc}") from exc


# Sanity check at import time: every Vql frame class has an encoder. Catches
# the "added a frame class but forgot to wire it" mistake before tests run.
_missing = [c.__name__ for c in VQL_FRAME_CLASSES if c not in _ENCODERS]
if _missing:  # pragma: no cover — caught by test_dispatch_completeness
    raise RuntimeError(
        f"Vql frame classes without encoder: {_missing}. Update _ENCODERS in serializer.py."
    )
