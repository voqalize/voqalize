"""Ergonomic Brain SDK over the raw Cortex wire.

The low-level surface (:mod:`voqalize.sdk.cortex`) hands the customer raw
``Vql*`` frames in a pipecat ``FrameProcessor``. This layer turns that into the
``Brain``-of-callbacks surface from ``docs/voice-protocol.md`` §SDK: you write a
``Brain`` (a capability-free contract — your object holds only your state), and
SDK capability arrives as the ``Session`` / ``Interaction`` / ``Inference``
objects passed into your callbacks.

    from voqalize.sdk import Brain, serve

    class Greeter(Brain):
        async def on_session_start(self, session, start):
            async with session.inference() as inf:        # agent-initiated greeting
                await inf.speak("Hi! How can I help?")

        async def on_interaction(self, interaction):
            # interaction.conversation is the faithful (heard) transcript, already
            # incl. this user turn — build your LLM prompt from it. The SDK commits
            # the assistant's HEARD text for you; you keep no parallel history.
            history = interaction.conversation.messages
            async with interaction.inference() as inf:
                await inf.speak(f"You said: {interaction.transcript}")

    serve(Greeter, api_key="ak_...", cortex_url="wss://.../agent")

Mapping onto the *current* Vql wire (the implemented subset of the protocol):

- ``interaction``                 ← ``VqlUserTextFrame`` (transcript opens it; Voice mints ``interaction_id``)
- ``async with .inference()``     → ``VqlLLMFullResponseStart`` … ``VqlLLMFullResponseEnd`` (mints ``inference_id``)
- ``inf.speak(text)``             → ``VqlLLMTextFrame``
- ``on_inference_finalized``      ← ``VqlInferenceFinalizedFrame`` (``heard`` / ``interrupted``)
- ``session.conversation``        ← faithful transcript: SDK commits user@start + assistant ``heard``@finalize
- barge-in                        ← native ``InterruptionFrame`` → cancels the interaction coroutine + echoes the drain barrier
- ``interaction.action(...)`` /
  ``session.action(...)``         → ``RTVIServerMessageFrame`` (UI command to the browser; fire-and-forget,
                                    session-scoped — use ``session.action`` for renders outside any interaction)

Agent-initiated speech (the opening greeting) uses ``interaction_id = 0`` — the
"no user stimulus" sentinel; Voice mints user interaction ids from 1.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from loguru import logger

from .engine import Emitter, SessionAdapter, SessionFactory
from .inbound import DirectAgent
from .outbound import CortexAgent
from .wire import (
    ErrorFrame,
    Frame,
    InterruptionFrame,
    RTVIClientMessageFrame,
    RTVIServerMessageFrame,
    STTUpdateSettingsFrame,
    TTSUpdateSettingsFrame,
    VqlInferenceFinalizedFrame,
    VqlInteractionCompletedFrame,
    VqlLLMFullResponseEndFrame,
    VqlLLMFullResponseStartFrame,
    VqlLLMTextFrame,
    VqlStartFrame,
    VqlUserTextFrame,
)

# Browser→Brain message type carrying an action's result (correlated by action_id).
ACTION_OUTCOME = "action_outcome"

GREETING_INTERACTION_ID = 0


# ─── Objects passed into callbacks ────────────────────────────────────────────


@dataclass
class SessionStart:
    """Delivered to ``on_session_start``."""

    init: dict[str, Any]


@dataclass
class AppEvent:
    """Out-of-interaction UI→Brain feedback, delivered to ``on_app_event``.

    ``data`` is the message's JSON object payload (the wire always carries an
    object — matches the Go SDK's ``map[string]any``)."""

    name: str
    data: dict[str, Any]


@dataclass
class Outcome:
    """The async result of an ``interaction.action`` (the ``action.outcome`` event).

    Correlated by ``action_id`` at *session* scope, so a late outcome that lands
    in a later interaction still fires the original ``callback``.
    """

    action_id: int
    interaction_id: int
    status: str
    result: Any = None


@dataclass
class Message:
    """One committed conversation turn — part of the *faithful record*.

    For an ``"assistant"`` message ``content`` is the text the user actually
    HEARD (post-TTS, truncated on barge-in), never the generated text.
    Provider-neutral: map it onto your LLM's message type when you build a prompt.
    """

    role: str  # "user" | "assistant"
    content: str


class Conversation:
    """The session's faithful, heard-truth transcript — *framework-maintained*.

    The heard-text contract is enforced here, not left to the Brain. The SDK
    records every turn for you: the user utterance at interaction start, and one
    assistant message per inference built from its HEARD text at finalize — so
    the generated-but-never-spoken tail of a barged-in reply never lands in the
    record. Read :attr:`messages` both to build your LLM prompt (past turns are
    always the heard truth) and to persist. You cannot commit generated text by
    mistake, because you never commit at all.

    In-flight caveat: an inference is only recorded once it *finalizes* (post
    playout). Within a single ``on_interaction`` (e.g. a tool round-trip) use the
    generated text for the working context — heard isn't known yet — and let the
    next turn read it back from here as the reconciled truth.
    """

    def __init__(self) -> None:
        self._messages: list[Message] = []

    @property
    def messages(self) -> list[Message]:
        """The committed transcript so far (a copy; mutate via the SDK only)."""
        return list(self._messages)

    def _record_user(self, text: str) -> None:
        self._messages.append(Message("user", text))

    def _record_assistant_heard(self, text: str) -> None:
        # Only HEARD text is ever recorded; empty (nothing landed) is dropped.
        if text:
            self._messages.append(Message("assistant", text))


class Inference:
    """One LLM call, delivered to ``on_inference_finalized``.

    ``heard`` is the text the user actually heard for *this inference* (post-TTS,
    truncated on barge-in) — commit this, never the generated text.
    """

    def __init__(
        self,
        *,
        interaction_id: int,
        inference_id: int,
        heard: str,
        interrupted: bool,
        interaction: Interaction | None,
    ) -> None:
        self.interaction_id = interaction_id
        self.id = inference_id
        self.heard = heard
        self.interrupted = interrupted
        self.interaction = interaction


class _InferenceBracket:
    """`async with <interaction|session>.inference() as inf:` — emits the
    ``VqlLLMFullResponse{Start,End}`` pair and mints the ``inference_id``."""

    def __init__(self, proc: _BrainAdapter, interaction_id: int, inference_id: int) -> None:
        self._proc = proc
        self.interaction_id = interaction_id
        self.id = inference_id

    async def __aenter__(self) -> _InferenceBracket:
        await self._proc._emit(
            VqlLLMFullResponseStartFrame(interaction_id=self.interaction_id, inference_id=self.id)
        )
        return self

    async def speak(self, text: str) -> None:
        """Emit a chunk of bot speech (``inference.output``). May be called many
        times within one bracket; Voice TTS chunks + word-times it for playout."""
        if not text:
            return
        await self._proc._emit(
            VqlLLMTextFrame(interaction_id=self.interaction_id, inference_id=self.id, text=text)
        )

    async def __aexit__(self, *exc: object) -> bool:
        await self._proc._emit(
            VqlLLMFullResponseEndFrame(interaction_id=self.interaction_id, inference_id=self.id)
        )
        return False


class Session:
    """Session-level handle (reachable as ``interaction.session``)."""

    def __init__(self, proc: _BrainAdapter, session_id: str, init: dict[str, Any]) -> None:
        self._proc = proc
        self.id = session_id
        self.init = init
        # Framework-maintained faithful transcript (heard-text contract).
        self.conversation = Conversation()
        # inference counter for agent-initiated speech (interaction_id = 0).
        self._greeting_inferences = 0
        # Brain-minted action ids + pending outcome callbacks, at SESSION scope so
        # a late action.outcome (even in a later interaction) still fires.
        self._action_seq = 0
        self._action_callbacks: dict[int, Callable[[Outcome], Any]] = {}

    def inference(self) -> _InferenceBracket:
        """Open an agent-initiated inference (e.g. the opening greeting),
        scoped to the ``interaction_id = 0`` sentinel."""
        self._greeting_inferences += 1
        return _InferenceBracket(self._proc, GREETING_INTERACTION_ID, self._greeting_inferences)

    def action(
        self,
        name: str,
        args: dict[str, Any] | None = None,
        *,
        callback: Callable[[Outcome], Any] | None = None,
    ) -> int:
        """Fire a UI command to the browser (a "UI tool") *outside any interaction*.

        Actions are session-scoped and floor-free (they carry no audio), so the
        Brain may emit one any time — a render from ``on_session_start``, an
        ``on_app_event`` handler, or an async-backend task that resolves after the
        triggering interaction has ended. Same fire-and-return semantics as
        :meth:`Interaction.action`, minus the originating-turn attribution: it
        emits the RTVI ``ui_command`` envelope pygato relays
        (``{"type": "ui_command", "action": name, "action_id": id, **args}``) and
        returns the Brain-minted ``action_id``. The optional ``callback(outcome)``
        fires out-of-band when the browser echoes ``action_outcome`` (matched by
        ``action_id`` at session scope). Never blocks.
        """
        action_id = self._register_action(callback)
        self._proc._emit_nowait(
            RTVIServerMessageFrame(
                data={"type": "ui_command", "action": name, "action_id": action_id, **(args or {})}
            )
        )
        return action_id

    def configure_tts(
        self,
        *,
        voice: str | None = None,
        language: str | None = None,
        model: str | None = None,
    ) -> None:
        """Change TTS voice/language/model for the **next** inference (mid-call).

        Fire-and-forget, like :meth:`action`. Not instantaneous: vql-speech
        locks voice/model/language per Cartesia context, and pygato pins one
        context per inference, so a change here only takes effect once the
        current inference (if any) finishes — never mid-utterance. Only pass
        the fields you want to change; omitted fields keep their current value.

        This is the TTS half of the voice-protocol `session.configure()` DTO
        (`docs/voice-protocol.md`) — see :meth:`configure_stt` for the STT-VAD
        half; mid-call `locale` reconfigure is not yet exposed here.
        """
        settings: dict[str, Any] = {}
        if voice is not None:
            settings["voice"] = voice
        if language is not None:
            settings["language"] = language
        if model is not None:
            settings["model"] = model
        if not settings:
            return
        self._proc._emit_nowait(TTSUpdateSettingsFrame(settings=settings))

    def configure_stt(
        self,
        *,
        language_hint: str | None = None,
        vad_confidence: float | None = None,
        vad_min_volume: float | None = None,
        vad_start_frames: int | None = None,
        vad_stop_frames_to_trigger_update: int | None = None,
        vad_eager_frames: int | None = None,
        vad_barge_in_ms: int | None = None,
        resume_frames: int | None = None,
        min_segment_speech_frames: int | None = None,
        confidence_tail_ms: int | None = None,
    ) -> None:
        """Change STT VAD/turn-detection knobs mid-call.

        Fire-and-forget, like :meth:`action`. Unlike :meth:`configure_tts`,
        these apply live with no queuing — vql-speech treats them as
        comparison bounds against self-resetting counters, safe to change
        mid-utterance. Only pass the fields you want to change; omitted
        fields keep their current value. Field names match vql-speech's Flux
        `Configure` thresholds verbatim.

        Use this to widen the pause window for a slow or stammering talker,
        tighten it for a fast-turnaround IVR flow, or adapt live to a noisy
        environment.

        This is the STT-VAD half of the voice-protocol `session.configure()`
        DTO (`docs/voice-protocol.md`). ``language_hint`` swaps the recognition
        language mid-call (e.g. ``"hi"`` / ``"te"``) — paired with a
        :meth:`configure_tts` ``language=`` change, this switches the whole voice
        to another language between turns.
        """
        settings: dict[str, Any] = {}
        if language_hint is not None:
            settings["language_hint"] = language_hint
        if vad_confidence is not None:
            settings["vad_confidence"] = vad_confidence
        if vad_min_volume is not None:
            settings["vad_min_volume"] = vad_min_volume
        if vad_start_frames is not None:
            settings["vad_start_frames"] = vad_start_frames
        if vad_stop_frames_to_trigger_update is not None:
            settings["vad_stop_frames_to_trigger_update"] = vad_stop_frames_to_trigger_update
        if vad_eager_frames is not None:
            settings["vad_eager_frames"] = vad_eager_frames
        if vad_barge_in_ms is not None:
            settings["vad_barge_in_ms"] = vad_barge_in_ms
        if resume_frames is not None:
            settings["resume_frames"] = resume_frames
        if min_segment_speech_frames is not None:
            settings["min_segment_speech_frames"] = min_segment_speech_frames
        if confidence_tail_ms is not None:
            settings["confidence_tail_ms"] = confidence_tail_ms
        if not settings:
            return
        self._proc._emit_nowait(STTUpdateSettingsFrame(settings=settings))

    def _register_action(self, callback: Callable[[Outcome], Any] | None) -> int:
        self._action_seq += 1
        if callback is not None:
            self._action_callbacks[self._action_seq] = callback
        return self._action_seq

    def _pop_action_callback(self, action_id: int) -> Callable[[Outcome], Any] | None:
        return self._action_callbacks.pop(action_id, None)


class Interaction:
    """One committed user stimulus + the handle you respond through.

    Passed into ``on_interaction``. ``transcript`` is the committed utterance;
    open one ``inference()`` bracket per LLM call.
    """

    def __init__(
        self,
        proc: _BrainAdapter,
        interaction_id: int,
        transcript: str,
        session: Session,
        brain: Brain,
    ) -> None:
        self._proc = proc
        self.id = interaction_id
        self.transcript = transcript
        self.session = session
        self.brain = brain
        self._inferences = 0

    @property
    def conversation(self) -> Conversation:
        """The session's faithful transcript (see :class:`Conversation`).

        Already includes *this* interaction's user utterance (committed before
        ``on_interaction`` runs) — build your LLM prompt straight from it."""
        return self.session.conversation

    def inference(self) -> _InferenceBracket:
        """Open one inference bracket — 1:1 with an LLM call. Never wrap a whole
        multi-inference run in a single bracket."""
        self._inferences += 1
        return _InferenceBracket(self._proc, self.id, self._inferences)

    def action(
        self,
        name: str,
        args: dict[str, Any] | None = None,
        *,
        callback: Callable[[Outcome], Any] | None = None,
    ) -> int:
        """Fire a UI command to the browser (a "UI tool") and return its ``action_id``.

        :meth:`Session.action` attributed to *this* interaction. Fire-and-return —
        never blocks. Emits the RTVI ``ui_command`` envelope pygato relays:
        ``{"type": "ui_command", "action": name, "action_id": id, **args}``. The
        browser echoes ``{"type": "action_outcome", "action_id": id, ...}`` when it
        finishes; the optional ``callback(outcome)`` fires out-of-band when that
        arrives (matched by ``action_id`` at session scope, so a late outcome in a
        later interaction still fires). ``callback`` may be sync or async.
        """
        return self.session.action(name, args, callback=callback)


# ─── The Brain contract ───────────────────────────────────────────────────────


class Brain:
    """Capability-free contract. Subclass and implement what you need; your
    object holds only your state. SDK capability arrives via the ``session`` /
    ``interaction`` / ``inference`` passed into the callbacks below.

    Only ``on_interaction`` is required. ``on_inference_finalized`` is the core
    companion (commit the heard text). The rest are optional.
    """

    async def on_session_start(self, session: Session, start: SessionStart) -> None:
        """Setup; may open agent-initiated speech via ``session.inference()``."""

    async def on_session_end(self, session: Session) -> None:
        """Teardown."""

    async def on_interaction(self, interaction: Interaction) -> None:
        """The core callback. Input is complete; invoke the LLM and respond via
        ``interaction.inference()``. Return ⇒ the interaction is complete."""
        raise NotImplementedError("Brain.on_interaction must be implemented")

    async def on_inference_finalized(self, inference: Inference) -> None:
        """Per-inference side-effect hook (logging, durable store, metrics).

        The faithful record is committed for you: the SDK has already appended
        ``inference.heard`` to ``session.conversation`` (the heard-text contract,
        framework-enforced) before this fires. You no longer need to maintain a
        parallel committed-history; read ``interaction.conversation`` instead."""

    async def on_app_event(self, session: Session, event: AppEvent) -> None:
        """Out-of-interaction UI→Brain feedback (e.g. ``state_sync``)."""

    async def on_error(self, session: Session, error: ErrorFrame) -> None:
        """Non-fatal runtime signal (e.g. backpressure drop). Default: ignore.

        The runtime delivers an ``ErrorFrame`` here when it has to drop data under
        congestion (drop-newest). Override to log or shed load; the session is
        never killed by the runtime."""


# ─── The adapter: Vql frames ↔ Brain callbacks ────────────────────────────────


@dataclass
class _Pending:
    interaction: Interaction
    task: asyncio.Task[None]


class _BrainAdapter:
    """One per session. Implements :class:`~voqalize.sdk.engine.SessionAdapter`:
    translates inbound ``Vql*`` frames into ``Brain`` callbacks and the Brain's
    responses back onto the wire via the runner's :class:`Emitter`.

    Pipecat-free — no ``FrameProcessor``, no ``push_frame``. The runner dispatches
    each inbound frame to :meth:`handle_frame` (system-lane first) and emits the
    ack after it returns; the Brain's frames go out through ``emitter.send``.
    """

    def __init__(self, brain: Brain, emitter: Emitter) -> None:
        self._brain = brain
        self._emitter = emitter
        self._session: Session | None = None
        self._interactions: dict[int, Interaction] = {}
        self._pending: dict[int, _Pending] = {}
        self._bg_tasks: set[asyncio.Task[None]] = set()

    # Brain-facing emit helpers. ``emitter.send`` is a non-blocking enqueue onto
    # the runner's outbound lanes, so both are trivial; ``_emit`` stays ``async``
    # only to keep the Brain-facing bracket API (``await inf.speak(...)``) intact.
    async def _emit(self, frame: Frame) -> None:
        self._emitter.send(frame)

    def _emit_nowait(self, frame: Frame) -> None:
        self._emitter.send(frame)

    async def handle_frame(self, frame: Frame) -> None:
        if isinstance(frame, VqlStartFrame):
            self._session = Session(self, frame.session_id, dict(frame.payload))
            await self._brain.on_session_start(
                self._session, SessionStart(init=dict(frame.payload))
            )
            return

        if isinstance(frame, VqlUserTextFrame):
            assert self._session is not None
            # Commit the user utterance to the faithful transcript at interaction
            # start, before on_interaction runs (framework-enforced record).
            self._session.conversation._record_user(frame.text)
            interaction = Interaction(
                self, frame.interaction_id, frame.text, self._session, self._brain
            )
            self._interactions[frame.interaction_id] = interaction
            # SPAWN (don't await): handle_frame must return promptly so the runner
            # acks this frame and PyGato's flow control keeps moving; the response
            # streams out of the spawned task via emitter.send.
            task = asyncio.create_task(
                self._run_interaction(interaction), name=f"interaction-{frame.interaction_id}"
            )
            self._pending[frame.interaction_id] = _Pending(interaction, task)
            return

        if isinstance(frame, InterruptionFrame):
            # Barge-in: cancel in-flight interaction coroutines (CancelledError
            # unwinds their open inference brackets), then echo the
            # InterruptionFrame onward — pygato's drain barrier. The echo rides
            # the outbound system lane, so it jumps ahead of queued data.
            await self._cancel_pending()
            self._emitter.send(InterruptionFrame())
            return

        if isinstance(frame, VqlInferenceFinalizedFrame):
            interaction = self._interactions.get(frame.interaction_id)
            inference = Inference(
                interaction_id=frame.interaction_id,
                inference_id=frame.inference_id,
                heard=frame.heard_text,
                interrupted=frame.interrupted,
                interaction=interaction,
            )
            # Framework-enforced heard-text commit: one assistant message per
            # inference, built from HEARD text (never generated). Done before the
            # hook so on_inference_finalized observes the committed transcript.
            if self._session is not None:
                self._session.conversation._record_assistant_heard(frame.heard_text)
            await self._brain.on_inference_finalized(inference)
            return

        if isinstance(frame, RTVIClientMessageFrame) and self._session is not None:
            # action.outcome (App→Brain): correlated by action_id, routed to the
            # pending callback — never surfaced as a generic app event.
            if frame.type == ACTION_OUTCOME:
                self._dispatch_action_outcome(frame.data)
                return
            # Other browser→Brain custom messages (out-of-interaction UI feedback,
            # e.g. state_sync). `type` is the message name; `data` its payload (the
            # wire always carries an object; coerce a missing payload to ``{}``).
            data = frame.data if isinstance(frame.data, dict) else {}
            await self._brain.on_app_event(self._session, AppEvent(name=frame.type, data=data))
            return

        if isinstance(frame, ErrorFrame) and self._session is not None:
            # Non-fatal runtime signal (congestion drop). Default hook ignores it.
            await self._brain.on_error(self._session, frame)
            return

        # Anything else (End/Cancel/…) is a lifecycle frame the runner acts on;
        # the Brain has no handler for it, so drop it silently.

    async def close(self) -> None:
        """Session teardown — cancel in-flight work and run on_session_end."""
        await self._cancel_pending()
        for task in list(self._bg_tasks):
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        if self._session is not None:
            with contextlib.suppress(Exception):
                await self._brain.on_session_end(self._session)

    def _dispatch_action_outcome(self, data: Any) -> None:
        """Route an inbound action.outcome to its pending callback (by action_id)."""
        if not isinstance(data, dict):
            return
        action_id = data.get("action_id")
        if not isinstance(action_id, int):
            return
        assert self._session is not None
        callback = self._session._pop_action_callback(action_id)
        if callback is None:
            return
        outcome = Outcome(
            action_id=action_id,
            interaction_id=int(data.get("interaction_id", 0) or 0),
            status=str(data.get("status", "")),
            result=data.get("result"),
        )
        result = callback(outcome)
        if inspect.isawaitable(result):
            task = asyncio.ensure_future(result)
            self._bg_tasks.add(task)
            task.add_done_callback(self._bg_tasks.discard)

    async def _run_interaction(self, interaction: Interaction) -> None:
        try:
            await self._brain.on_interaction(interaction)
        except asyncio.CancelledError:
            raise  # barge-in: skip interaction.completed (Voice finalizes the cut inference)
        except Exception:
            logger.exception("brain: on_interaction failed for interaction {}", interaction.id)
        else:
            # Clean return ⇒ the brain is done responding to the whole interaction.
            await self._emit(VqlInteractionCompletedFrame(interaction_id=interaction.id))
        finally:
            self._pending.pop(interaction.id, None)

    async def _cancel_pending(self) -> None:
        for pending in list(self._pending.values()):
            if not pending.task.done():
                pending.task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await pending.task
        self._pending.clear()


# ─── Entry points ─────────────────────────────────────────────────────────────


def adapter_for(brain: Brain, emitter: Emitter) -> SessionAdapter:
    """Host an already-constructed ``Brain`` instance as a session adapter.

    Useful for single-session hosting/tests where you need a handle to the Brain
    (to inspect its state). Production multi-session hosting uses
    :func:`brain_factory`, which builds a fresh Brain per session."""
    return _BrainAdapter(brain, emitter)


def brain_factory(build: type[Brain] | Callable[[], Brain]) -> SessionFactory:
    """A ``SessionFactory`` for the runtime that builds a fresh ``Brain`` +
    adapter per session, wired to the runner's :class:`Emitter`.

    ``build`` is a zero-arg callable returning a ``Brain`` — a ``Brain`` subclass,
    or a closure capturing injected dependencies (``lambda: TravelBrain(llm=...)``)."""

    def _factory(emitter: Emitter) -> SessionAdapter:
        return _BrainAdapter(build(), emitter)

    return _factory


def make_agent(brain_cls: type[Brain], **cortex_kwargs: Any) -> CortexAgent:
    """Build a :class:`CortexAgent` that hosts ``brain_cls`` (one per session)."""
    return CortexAgent(factory=brain_factory(brain_cls), **cortex_kwargs)


async def serve(brain_cls: type[Brain], **cortex_kwargs: Any) -> None:
    """Host ``brain_cls`` over the **Cortex relay** (optional fallback path) until
    cancelled — for brains that cannot accept an inbound connection.

    ``serve(MyBrain, api_key=..., version=..., cortex_url=...)``.

    The **primary** path is :func:`serve_direct`, where PyGato dials your brain
    directly and you run an inbound WebSocket route.
    """
    await make_agent(brain_cls, **cortex_kwargs).run()


def make_direct_agent(brain_cls: type[Brain], **direct_kwargs: Any) -> DirectAgent:
    """Build a :class:`DirectAgent` (inbound server) hosting ``brain_cls`` (one
    per session)."""
    return DirectAgent(factory=brain_factory(brain_cls), **direct_kwargs)


async def serve_direct(brain_cls: type[Brain], **direct_kwargs: Any) -> None:
    """Host ``brain_cls`` on a self-owned inbound WebSocket server (localhost/dev).

    PyGato dials ``{brain_url}/s/{session_id}`` per session.
    ``serve_direct(MyBrain, host="0.0.0.0", port=8787, public_keys=VOQAL_PUBKEY)``.
    For production, mount :func:`voqalize.sdk.run_session` in your own web
    framework instead of owning a server here.
    """
    await make_direct_agent(brain_cls, **direct_kwargs).run()


async def serve_auto(brain_cls: type[Brain], *, mode: str | None = None, **kwargs: Any) -> None:
    """Pick the transport from config, run the SAME ``brain_cls`` — no brain code
    change between modes, just a config flip + the kwargs that mode needs.

    ``mode`` defaults to ``$VOQAL_AGENT_MODE`` (else ``"outbound"``):

    * ``"outbound"`` / ``"cortex"`` → dial the Cortex relay (localhost/egress-only).
      Pass ``cortex_url=``, ``api_key=`` (or ``authorization_provider=``), ``version=``.
    * ``"inbound"`` / ``"direct"`` → own a localhost WS server. Pass ``host=``,
      ``port=``, and optional ``public_keys=`` / ``allow_unverified=``.

    (Production inbound mounts :func:`voqalize.sdk.run_session` in your own
    framework, which owns the socket — that can't be auto-started here.)
    """
    import os

    mode = (mode or os.environ.get("VOQAL_AGENT_MODE") or "outbound").lower()
    if mode in ("inbound", "direct"):
        await serve_direct(brain_cls, **kwargs)
    elif mode in ("outbound", "cortex"):
        await serve(brain_cls, **kwargs)
    else:
        raise ValueError(f"unknown agent mode {mode!r}; expected inbound|outbound")
