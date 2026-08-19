"""Ergonomic Brain SDK over the raw Cortex wire.

The wire surface (:mod:`voqalize.sdk.wire`) deals in payload frames plus the
envelope correlation beside them. This layer turns that into the
``Brain``-of-callbacks surface from ``docs/voice-protocol.md`` §SDK: you write a
``Brain`` (a capability-free contract — your object holds only your state), and
SDK capability arrives as the ``Session`` / ``Interaction`` / ``Inference``
objects passed into your callbacks.

    from voqalize.sdk import Brain, serve

    class Greeter(Brain):
        async def on_session_start(self, session, start):
            async with session.say() as speech:      # the opening line the agent speaks
                await speech.speak("Hi! How can I help?")

        async def on_interaction(self, interaction):
            # interaction.conversation is the faithful (heard) transcript, already
            # incl. this user turn — build your LLM prompt from it. The SDK commits
            # the assistant's HEARD text for you; you keep no parallel history.
            history = interaction.conversation.messages
            async with interaction.say() as speech:
                await speech.speak(f"You said: {interaction.transcript}")

    serve(Greeter, api_key="sk_...", cortex_url="wss://.../agent")

``say()`` is the raw-speech bracket: *you* supply the words and the SDK streams
them to Voice for TTS. (A framework integration's ``run_inference()`` is the
sibling verb where the *model* supplies the words — see ``voqalize.google_adk``
et al.; under the hood it opens the same ``say()`` bracket per model call.)

Mapping onto the wire:

- ``interaction``                 ← ``UserMessageFrame`` (its text opens the turn)
- ``on_user_idle``                ← ``UserIdleFrame``
- ``on_client_message``           ← ``ClientMessageFrame`` (every browser message; respond by touching ``message.interaction``)
- ``async with .say()``           → ``LLMFullResponseStartFrame`` … ``LLMFullResponseEndFrame`` (mints ``inference_id``)
- ``speech.speak(text)``          → ``LLMTextFrame``
- ``on_inference_finalized``      ← ``InferenceFinalizedFrame`` (``heard`` / ``interrupted``)
- ``session.conversation``        ← faithful transcript: SDK commits user@start + assistant ``heard``@finalize
- barge-in                        ← ``InterruptionFrame`` → cancels the interaction coroutine + echoes the drain barrier
- ``interaction.action(...)`` /
  ``session.action(...)``         → ``ServerMessageFrame`` (UI command to the browser; fire-and-forget,
                                    session-scoped — use ``session.action`` for renders outside any interaction)

Correlation never appears in this surface. The runtime stamps each stimulus with
an ``epoch``; the SDK echoes it, unread, on everything the Brain emits while
handling that stimulus, so the runtime's drain barrier can place a frame.
Agent-initiated speech (the opening greeting) answers no stimulus and rides
epoch 0.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, ClassVar, overload

from loguru import logger

from .actions import Action, action_envelope
from .engine import Emitter, Envelope, SessionAdapter, SessionFactory
from .inbound import DirectAgent
from .outbound import CortexAgent
from .wire import (
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

# Browser→Brain message type carrying an action's result (correlated by action_id).
ACTION_OUTCOME = "action_outcome"

# Agent-initiated speech answers no stimulus, so it echoes no epoch.
NO_EPOCH = 0


# ─── Objects passed into callbacks ────────────────────────────────────────────


@dataclass
class SessionStart:
    """Delivered to ``on_session_start``."""

    init: dict[str, Any]


@dataclass
class IdleInfo:
    """Why an idle interaction opened, reachable as ``interaction.idle`` inside
    ``on_user_idle``.

    ``level`` counts consecutive idle escalations without intervening user speech
    (1 = first nudge; resets when the user speaks), so the Brain can escalate —
    a gentle "still there?" at level 1, a wrap-up at level 3. ``idle_ms`` is the
    silence elapsed when Voice opened the interaction."""

    level: int
    idle_ms: int


class InteractionSource(StrEnum):
    """What made Voice open an interaction (``interaction.source``).

    Voice is the sole interaction initiator; this says *which* of the triggers
    fired. ``USER`` carries a ``transcript``; ``IDLE`` carries ``idle``;
    ``CLIENT_MESSAGE`` carries ``client_message`` (both with an empty
    ``transcript`` — no words were spoken)."""

    USER = "user"
    IDLE = "idle"
    CLIENT_MESSAGE = "client_message"


@dataclass
class Outcome:
    """The async result of an ``interaction.action`` (the ``action.outcome`` event).

    Correlated by ``action_id`` at *session* scope, so a late outcome that lands
    in a later interaction still fires the original ``callback``.
    """

    action_id: int
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

    def seed(self, messages: Iterable[Message]) -> None:
        """Prepend prior-session turns so a logical conversation resumes (RESUME).

        A voice session is one WebSocket, but a *logical* conversation may span
        several — a dropped call reconnects, or a caller phones back. When it does,
        the new session boots with an empty record, so the model would start cold.
        Hand the SDK the :attr:`messages` you persisted from the previous session
        (keyed by your own stable identifier, which you read from
        ``session.init`` / ``SessionStart.init``) and they become the heard-truth
        prefix: the faithful record spans sessions and the very first prompt of the
        new session already carries prior context.

        Seed **once, at session start, before any live interaction** — it is the
        opening state, not a mid-call edit. A framework integration
        (``adk_brain`` / ``genai_brain`` / ``agents_brain``) wires this to its
        ``on_resume`` hook and also seeds its own tool-aware transcript from the
        same messages; a hand-written :class:`Brain` calls it directly from
        ``on_session_start``. No-op on an empty iterable; raises if the record
        already holds a turn (seed before the first one)."""
        seeded = list(messages)
        if not seeded:
            return
        if self._messages:
            raise RuntimeError(
                "Conversation.seed() must run before any turn is recorded "
                "(seed prior-session history at session start, not mid-conversation)"
            )
        self._messages.extend(Message(m.role, m.content) for m in seeded)

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
        inference_id: int,
        heard: str,
        interrupted: bool,
        interaction: Interaction | None,
    ) -> None:
        self.id = inference_id
        self.heard = heard
        self.interrupted = interrupted
        self.interaction = interaction


class _SpeechBracket:
    """`async with <interaction|session>.say() as speech:` — one unit of bot
    speech. Emits the ``LLMFullResponse{Start,End}`` pair, mints the
    ``inference_id``, and streams whatever text you ``speak()`` to Voice for TTS."""

    def __init__(
        self,
        proc: _BrainAdapter,
        epoch: int,
        inference_id: int,
        interaction: Interaction | None = None,
    ) -> None:
        self._proc = proc
        self._epoch = epoch
        self.id = inference_id
        # The owning interaction (None for agent-initiated/greeting speech), so a
        # non-empty speak() can record that the turn produced audio — the signal the
        # no-dead-air guard reads.
        self._interaction = interaction

    async def __aenter__(self) -> _SpeechBracket:
        await self._emit(LLMFullResponseStartFrame())
        return self

    async def speak(self, text: str) -> None:
        """Emit a chunk of bot speech (``inference.output``). May be called many
        times within one bracket; Voice TTS chunks + word-times it for playout."""
        if not text:
            return
        if self._interaction is not None:
            self._interaction._spoke = True
        await self._emit(LLMTextFrame(text=text))

    async def __aexit__(self, *exc: object) -> bool:
        await self._emit(LLMFullResponseEndFrame())
        return False

    async def _emit(self, frame: Frame) -> None:
        await self._proc._emit(frame, epoch=self._epoch, inference_id=self.id)


class Session:
    """Session-level handle (reachable as ``interaction.session``)."""

    def __init__(self, proc: _BrainAdapter, session_id: str, init: dict[str, Any]) -> None:
        self._proc = proc
        self.id = session_id
        self.init = init
        # Framework-maintained faithful transcript (heard-text contract).
        self.conversation = Conversation()
        # Session-monotonic inference counter — one id per say() bracket, shared
        # by every interaction and by agent-initiated speech.
        self._inference_seq = 0
        # Brain-minted action ids + pending outcome callbacks, at SESSION scope so
        # a late action.outcome (even in a later interaction) still fires.
        self._action_seq = 0
        self._action_callbacks: dict[int, Callable[[Outcome], Any]] = {}
        # Set once the Brain asks to end the session, so end() is idempotent.
        self._ended = False

    def end(self, reason: str = "agent_ended") -> None:
        """End the session from the Brain side (e.g. after a goodbye).

        Emits a bare ``End`` frame on the normal lane, so it drains behind any
        speech you queued first (say your goodbye, *then* ``session.end()``).
        Voice tears the call down in response and closes the socket; the Brain's
        :meth:`Brain.on_session_end` fires on that close. Idempotent — a second
        call is a no-op.

        ``reason`` is logged locally for your own diagnostics; it does **not**
        cross the wire (the ``End`` frame carries no reason field — Voice never
        needs the Brain's rationale to hang up).
        """
        if self._ended:
            return
        self._ended = True
        logger.info("session {}: ending (reason={})", self.id, reason)
        self._proc._emit_nowait(EndFrame())

    def say(self) -> _SpeechBracket:
        """Open a session-scoped speech bracket — *you* supply the words (e.g. the
        opening greeting). Agent-initiated: it answers no user stimulus. ``async
        with session.say() as speech: await speech.speak(...)``."""
        return _SpeechBracket(self._proc, NO_EPOCH, self._next_inference())

    def _next_inference(self) -> int:
        self._inference_seq += 1
        return self._inference_seq

    @overload
    def action(
        self, action: Action, /, *, callback: Callable[[Outcome], Any] | None = None
    ) -> int: ...

    @overload
    def action(
        self,
        name: str,
        args: dict[str, Any] | None = None,
        *,
        callback: Callable[[Outcome], Any] | None = None,
    ) -> int: ...

    def action(
        self,
        name: str | Action,
        args: dict[str, Any] | None = None,
        *,
        callback: Callable[[Outcome], Any] | None = None,
    ) -> int:
        """Fire a UI command to the browser (a "UI tool") *outside any interaction*.

        Two calling forms, one wire shape:

        - **typed** — ``session.action(OpenItinerary(name="Poddar Vietnam"))``, where
          ``OpenItinerary`` is a :class:`~voqalize.sdk.Action` subclass. The wire
          name comes from the class, the args from its fields
          (``model_dump(by_alias=True, mode="json")``).
        - **legacy** — ``session.action("open_itinerary", {"name": "Poddar Vietnam"})``.
          Unchanged, and staying: the general form for brains that don't use pydantic.

        Both emit the identical RTVI ``ui_command`` envelope pygato relays
        (``{"type": "ui_command", "action": name, "action_id": id, **args}``) and
        return the Brain-minted ``action_id``.

        Actions are session-scoped and floor-free (they carry no audio), so the
        Brain may emit one any time — a render from ``on_session_start``, an
        ``on_client_message`` handler, or an async-backend task that resolves after the
        triggering interaction has ended. Same fire-and-return semantics as
        :meth:`Interaction.action`, minus the originating-turn attribution. The
        optional ``callback(outcome)`` fires out-of-band when the browser echoes
        ``action_outcome`` (matched by ``action_id`` at session scope). Never blocks.
        """
        wire_name, payload = action_envelope(name, args)
        action_id = self._register_action(callback)
        self._proc._emit_nowait(
            ServerMessageFrame(
                data={
                    "type": "ui_command",
                    "action": wire_name,
                    "action_id": action_id,
                    **payload,
                }
            )
        )
        return action_id

    def configure_language(self, language: str, *, voice: str | None = None) -> None:
        """Switch the whole call to another language — **the only way to do this.**

        One call moves both halves. Do not reach for :meth:`configure_tts` and
        :meth:`configure_stt` to change a language: the two sides name the field
        differently (TTS ``language``, STT ``language_hint``), so doing it by hand
        is two calls that can drift, and half-applying it is silent. A session
        that speaks Hindi through the English recognizer transcribes badly with no
        error; one that recognises Hindi in an English voice sounds like a
        non-native speaker and passes every automated check we have — accent is
        invisible to WER.

        ``language`` is an ISO code (``"hi"``, ``"ta"``, ``"en"``). Pass ``voice``
        too when the target language needs a different catalog voice. To open a
        session in a language, set ``pipeline.stt.language`` and
        ``pipeline.tts.language`` at connect instead — same field, same value.

        Fire-and-forget, and inherits each half's timing: STT applies at the next
        turn boundary, TTS at the next inference (never mid-utterance).
        """
        self.configure_tts(voice=voice, language=language)
        self.configure_stt(language_hint=language)

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
        self._proc._emit_nowait(UpdateTTSSettingsFrame(settings=settings))

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
        self._proc._emit_nowait(UpdateSTTSettingsFrame(settings=settings))

    def configure_idle(self, *, timeout_ms: int | None = None) -> None:
        """(Re)configure idle detection mid-call — the idle half of the
        voice-protocol ``session.configure()`` DTO (mirrors :meth:`configure_tts`
        / :meth:`configure_stt`).

        Fire-and-forget. ``timeout_ms`` is the silence after Voice stops speaking
        before it opens an idle interaction (``on_user_idle``). Pass ``0`` to
        disable idle detection entirely (no idle interactions until you re-enable
        it). Only pass the fields you want to change; omitted fields keep their
        current value.
        """
        settings: dict[str, Any] = {}
        if timeout_ms is not None:
            settings["timeout_ms"] = timeout_ms
        if not settings:
            return
        self._proc._emit_nowait(UpdateIdleSettingsFrame(settings=settings))

    def _register_action(self, callback: Callable[[Outcome], Any] | None) -> int:
        self._action_seq += 1
        if callback is not None:
            self._action_callbacks[self._action_seq] = callback
        return self._action_seq

    def _pop_action_callback(self, action_id: int) -> Callable[[Outcome], Any] | None:
        return self._action_callbacks.pop(action_id, None)


class Interaction:
    """One Voice-opened interaction + the handle you respond through.

    Reached one of two ways: passed into a floor-owning callback the trigger
    routed to (``on_interaction`` / ``on_user_idle``), or materialized on demand
    from ``on_client_message`` via ``message.interaction`` when the Brain chooses
    to respond. ``source`` says which trigger opened it; open one ``say()`` bracket
    per LLM call.

    - ``source == USER`` — ``transcript`` is the committed utterance.
    - ``source == IDLE`` — ``idle`` carries the escalation; ``transcript`` empty.
    - ``source == CLIENT_MESSAGE`` — ``client_message`` carries the browser
      message; ``transcript`` empty.
    """

    def __init__(
        self,
        proc: _BrainAdapter,
        epoch: int,
        transcript: str,
        session: Session,
        brain: Brain,
        *,
        source: InteractionSource = InteractionSource.USER,
        idle: IdleInfo | None = None,
        client_message: ClientMessage | None = None,
    ) -> None:
        self._proc = proc
        # The stimulus this turn answers. Opaque to the Brain — useful only to
        # correlate logs; the SDK echoes it on everything the turn emits.
        self.id = epoch
        self.transcript = transcript
        self.session = session
        self.brain = brain
        # Which trigger opened this interaction, plus the trigger-specific payload
        # (exactly one of idle/client_message is set for the non-USER sources).
        self.source = source
        self.idle = idle
        self.client_message = client_message
        # Flipped by a bracket's first non-empty speak(); read by the no-dead-air
        # guard to tell a silent turn (empty/safety-blocked model reply) from a
        # spoken one.
        self._spoke = False

    @property
    def conversation(self) -> Conversation:
        """The session's faithful transcript (see :class:`Conversation`).

        Already includes *this* interaction's user utterance (committed before
        ``on_interaction`` runs) — build your LLM prompt straight from it."""
        return self.session.conversation

    @property
    def spoke(self) -> bool:
        """Whether this interaction has emitted any non-empty bot speech yet. The
        no-dead-air guard speaks a fallback for a turn that ends having said
        nothing (an empty or safety-blocked model reply that raised no error)."""
        return self._spoke

    def say(self) -> _SpeechBracket:
        """Open one speech bracket for this interaction — 1:1 with an LLM call
        (mints one ``inference_id``). Never wrap a whole multi-inference run in a
        single bracket; open one per model call."""
        return _SpeechBracket(self._proc, self.id, self.session._next_inference(), interaction=self)

    @overload
    def action(
        self, action: Action, /, *, callback: Callable[[Outcome], Any] | None = None
    ) -> int: ...

    @overload
    def action(
        self,
        name: str,
        args: dict[str, Any] | None = None,
        *,
        callback: Callable[[Outcome], Any] | None = None,
    ) -> int: ...

    def action(
        self,
        name: str | Action,
        args: dict[str, Any] | None = None,
        *,
        callback: Callable[[Outcome], Any] | None = None,
    ) -> int:
        """Fire a UI command to the browser (a "UI tool") and return its ``action_id``.

        :meth:`Session.action` attributed to *this* interaction — same two calling
        forms (typed ``action(MyAction(...))`` or legacy ``action(name, args)``), same
        wire shape. Fire-and-return — never blocks. Emits the RTVI ``ui_command``
        envelope pygato relays: ``{"type": "ui_command", "action": name, "action_id":
        id, **args}``. The browser echoes ``{"type": "action_outcome", "action_id":
        id, ...}`` when it finishes; the optional ``callback(outcome)`` fires
        out-of-band when that arrives (matched by ``action_id`` at session scope, so a
        late outcome in a later interaction still fires). ``callback`` may be sync or
        async.
        """
        if isinstance(name, Action):
            return self.session.action(name, callback=callback)
        return self.session.action(name, args, callback=callback)


class ClientMessage:
    """A browser→Brain client message, delivered to ``on_client_message``.

    ``client.sendClientMessage(type, data)`` in the browser → Voice → here. Voice
    delivers **every** client message unconditionally — it does not interpret the
    message or decide whether it warrants a reply. That is the Brain's call:

    - **update internal state** (a tool reads it later) — just read ``data`` and
      return; nothing is spoken;
    - **append to your model history without responding** — your own concern
      (e.g. add an event to your framework session), then return;
    - **respond right away** — touch :attr:`interaction` to take the floor and
      ``say()`` / ``run_inference`` on it. No coordination with Voice is needed.

    ``type`` is the message name, ``data`` its JSON object payload, ``id`` the
    browser-supplied message id (may be empty).
    """

    def __init__(
        self,
        proc: _BrainAdapter,
        session: Session,
        brain: Brain,
        *,
        epoch: int,
        msg_id: str,
        msg_type: str,
        data: dict[str, Any],
    ) -> None:
        self._proc = proc
        self._session = session
        self._brain = brain
        self._epoch = epoch
        self.id = msg_id
        self.type = msg_type
        self.data = data
        # Materialized lazily by `interaction`.
        self._interaction: Interaction | None = None

    @property
    def interaction(self) -> Interaction:
        """Take the floor for this message and get the interaction to respond on.

        Lazily materializes the interaction for this message (``source ==
        CLIENT_MESSAGE``) and registers it, so a barge-in cancels your response.
        Idempotent — repeated reads return the same interaction. If you never read
        it, no interaction is driven (responding is opt-in)."""
        if self._interaction is None:
            self._interaction = self._proc._materialize_client_interaction(self)
        return self._interaction


# ─── The Brain contract ───────────────────────────────────────────────────────


class Brain:
    """Capability-free contract. Subclass and implement what you need; your
    object holds only your state. SDK capability arrives via the ``session`` /
    ``interaction`` / ``inference`` passed into the callbacks below.

    Only ``on_interaction`` is required. ``on_inference_finalized`` is the core
    companion (commit the heard text). The rest are optional.

    **Floor management (guidance, not enforced).** Voice is the sole interaction
    initiator: it opens every turn and hands the brain the floor via
    a callback. Respond — invoke the LLM, ``say()`` — only when you hold the floor.
    There are four triggers that open (or can open) an interaction, all opened by
    Voice:

    1. ``on_session_start`` — session start, the opening greeting.
    2. ``on_interaction`` — the user stopped speaking.
    3. ``on_user_idle`` — the user went silent past the idle timeout.
    4. ``on_client_message`` — a browser client message.

    The first three are floor-owning: the runtime opens the interaction and hands
    it to you. ``on_client_message`` is different — Voice delivers **every** client
    message but does not decide whether it deserves a reply. You do: update state
    and return, or take the floor by
    touching ``message.interaction`` and responding. Speaking or invoking the model
    outside a floor you hold is bad practice — the SDK won't stop you (it logs a
    warning), but you're talking out of turn.

    **Voice and language are declared here, not configured elsewhere.** Set
    :attr:`voice` (and :attr:`language` if the agent doesn't speak English) as
    class attributes; the SDK applies them at session start, before
    :meth:`on_session_start` runs::

        class ConciergeBrain(Brain):
            voice = "omnivoice/gauri"
            language = "hi"

    They live in the brain because the brain is the only thing that knows the
    caller — an agent record can hold one language for everyone, which is wrong
    the moment a customer speaks a different one. Declaring them here means they
    are version-controlled and reviewed with the rest of the agent. When the
    language depends on *this* call (the caller's state, their profile, what they
    just said), leave the attribute unset and call
    :meth:`Session.configure_language` from ``on_session_start`` instead — it
    lands before the greeting is spoken.
    """

    #: TTS voice for every session this brain serves, e.g. ``"omnivoice/gauri"``.
    #: ``None`` ⇒ leave the platform default in place.
    voice: ClassVar[str | None] = None

    #: ISO language code for both halves of the call — the recognizer *and* the
    #: voice-cloning reference clip, applied via :meth:`Session.configure_language`
    #: so the two can never half-apply. ``None`` ⇒ platform default (English).
    language: ClassVar[str | None] = None

    async def on_session_start(self, session: Session, start: SessionStart) -> None:
        """Setup, and the floor-owning callback for the opening greeting. The
        runtime opens a session-start interaction before any user turn; speak the
        greeting via ``session.say()``."""

    async def on_session_end(self, session: Session) -> None:
        """Teardown. Called once when the session ends (any reason). Best-effort:
        exceptions are swallowed and it never blocks the socket from closing."""

    async def on_interaction(self, interaction: Interaction) -> None:
        """The core callback — the user stopped speaking, so you hold the floor.
        Input is complete; invoke the LLM and respond via ``interaction.say()``.
        Return ⇒ the interaction is complete."""
        raise NotImplementedError("Brain.on_interaction must be implemented")

    async def on_user_idle(self, interaction: Interaction) -> None:
        """The user went silent past the idle timeout — you hold the floor to
        re-engage. ``interaction.idle`` (``IdleInfo``) carries the escalation
        ``level`` (1 = first nudge; escalates while silence persists) and elapsed
        ``idle_ms``; ``interaction.transcript`` is empty (nothing was said).
        Respond via ``interaction.say()`` (a nudge like "Are you still there?"),
        or return without speaking to let the silence ride. Default: no-op (the
        interaction completes silently and Voice keeps listening).

        Configure the timeout with ``session.configure_idle(timeout_ms=…)``."""

    async def on_client_message(self, session: Session, message: ClientMessage) -> None:
        """A browser client message arrived (``client.sendClientMessage``). Voice
        delivers **every** one and lets you
        decide: read ``message.type`` / ``message.data`` and update state (return
        without speaking), or take the floor by touching ``message.interaction`` and
        responding via ``interaction.say()`` / ``run_inference``. Default: no-op
        (state the browser pushes is ignored unless you handle it).

        UI-action outcomes (``type == "action_outcome"``) never reach here — they
        are routed to the pending ``action`` callback that fired them."""

    async def on_inference_finalized(self, inference: Inference) -> None:
        """Per-inference side-effect hook (logging, durable store, metrics).

        The faithful record is committed for you: the SDK has already appended
        ``inference.heard`` to ``session.conversation`` (the heard-text contract,
        framework-enforced) before this fires. You no longer need to maintain a
        parallel committed-history; read ``interaction.conversation`` instead."""

    async def on_error(self, session: Session, error: ErrorFrame) -> None:
        """Non-fatal runtime signal (e.g. backpressure drop). Default: ignore.

        The runtime delivers an ``ErrorFrame`` here when it has to drop data under
        congestion (drop-newest). Override to log or shed load; the session is
        never killed by the runtime."""


# ─── The adapter: wire frames ↔ Brain callbacks ───────────────────────────────


@dataclass
class _Pending:
    interaction: Interaction
    task: asyncio.Task[None]


class _BrainAdapter:
    """One per session. Implements :class:`~voqalize.sdk.engine.SessionAdapter`:
    translates inbound envelopes into ``Brain`` callbacks and the Brain's responses
    back onto the wire via the runner's :class:`Emitter`.

    Pipecat-free — no ``FrameProcessor``, no ``push_frame``. The runner dispatches
    each inbound envelope to :meth:`handle_frame` (system-lane first) and emits the
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
    async def _emit(self, frame: Frame, *, epoch: int = 0, inference_id: int = 0) -> None:
        self._emitter.send(frame, epoch=epoch, inference_id=inference_id)

    def _emit_nowait(self, frame: Frame) -> None:
        self._emitter.send(frame)

    def _apply_declared_voice(self, session: Session) -> None:
        """Apply the brain's declared :attr:`Brain.voice` / :attr:`Brain.language`.

        Runs here — in the adapter, on the way into the session — rather than in a
        base class's ``on_session_start``, because a subclass that overrides that
        hook and forgets ``super()`` would silently lose its voice, and a wrong
        voice is inaudible to every automated check we have (accent and speaker
        identity do not show up in a transcript).

        Emitted *before* the brain's own hook, so a brain that resolves the
        language per caller can still override it there with
        :meth:`Session.configure_language` — later frame on the same ordered lane
        wins, and both land before the greeting audio.
        """
        language, voice = self._brain.language, self._brain.voice
        if language is not None:
            # Both halves in one call: the recognizer and the reference clip.
            session.configure_language(language, voice=voice)
        elif voice is not None:
            session.configure_tts(voice=voice)

    async def handle_frame(self, env: Envelope) -> None:
        frame = env.frame

        if isinstance(frame, SessionStartFrame):
            self._session = Session(self, frame.session_id, dict(frame.payload))
            self._apply_declared_voice(self._session)
            await self._brain.on_session_start(
                self._session, SessionStart(init=dict(frame.payload))
            )
            return

        if isinstance(frame, UserMessageFrame):
            assert self._session is not None
            # Commit the user utterance to the faithful transcript at interaction
            # start, before on_interaction runs (framework-enforced record).
            self._session.conversation._record_user(frame.text)
            self._open_interaction(
                Interaction(self, env.epoch, frame.text, self._session, self._brain)
            )
            return

        if isinstance(frame, UserIdleFrame):
            # Voice opened an idle interaction (user silent past the timeout). No
            # user utterance to record — nothing was said — so the faithful
            # transcript stays clean; only the brain's response inferences land.
            assert self._session is not None
            self._open_interaction(
                Interaction(
                    self,
                    env.epoch,
                    "",
                    self._session,
                    self._brain,
                    source=InteractionSource.IDLE,
                    idle=IdleInfo(level=frame.level, idle_ms=frame.idle_ms),
                )
            )
            return

        if isinstance(frame, InterruptionFrame):
            # Barge-in: cancel in-flight interaction coroutines (CancelledError
            # unwinds their open inference brackets), then echo the
            # InterruptionFrame onward — pygato's drain barrier. The echo rides
            # the outbound system lane, so it jumps ahead of queued data.
            await self._cancel_pending()
            self._emitter.send(InterruptionFrame())
            return

        if isinstance(frame, InferenceFinalizedFrame):
            inference = Inference(
                inference_id=env.inference_id,
                heard=frame.heard_text,
                interrupted=frame.reason is FinalizeReason.USER_BARGE_IN,
                interaction=self._interactions.get(env.epoch),
            )
            # Framework-enforced heard-text commit: one assistant message per
            # inference, built from HEARD text (never generated). Done before the
            # hook so on_inference_finalized observes the committed transcript.
            if self._session is not None:
                self._session.conversation._record_assistant_heard(frame.heard_text)
            await self._brain.on_inference_finalized(inference)
            return

        if isinstance(frame, ClientMessageFrame) and self._session is not None:
            # action.outcome (App→Brain): correlated by action_id, routed to the
            # pending callback — never surfaced as a generic client message.
            if frame.type == ACTION_OUTCOME:
                self._dispatch_action_outcome(frame.data)
                return
            # Every other browser→Brain message goes to on_client_message. `type`
            # is the message name; `data` its JSON object payload (the wire
            # dataclass always carries an object). Spawned so an ambient
            # high-frequency message never blocks the ordered conversation lane,
            # and a response the Brain chooses to run streams out of that task.
            self._spawn_client_message(
                ClientMessage(
                    self,
                    self._session,
                    self._brain,
                    epoch=env.epoch,
                    msg_id=frame.msg_id,
                    msg_type=frame.type,
                    data=frame.data,
                )
            )
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
            status=str(data.get("status", "")),
            result=data.get("result"),
        )
        result = callback(outcome)
        if inspect.isawaitable(result):
            task = asyncio.ensure_future(result)
            self._bg_tasks.add(task)
            task.add_done_callback(self._bg_tasks.discard)

    def _open_interaction(self, interaction: Interaction) -> None:
        """Register a Voice-opened interaction and SPAWN its floor-owning callback.

        Shared by the two Voice-opened triggers (user text / idle). Spawn (don't
        await): handle_frame must return promptly so the runner acks the opening
        frame and PyGato's flow control keeps moving; the response streams out of
        the spawned task via emitter.send. (Client messages take their own spawn
        path — see :meth:`_spawn_client_message`.)
        """
        self._interactions[interaction.id] = interaction
        task = asyncio.create_task(
            self._run_interaction(interaction), name=f"interaction-{interaction.id}"
        )
        self._pending[interaction.id] = _Pending(interaction, task)

    def _spawn_client_message(self, message: ClientMessage) -> None:
        """Deliver a client message to ``on_client_message`` without blocking inbound
        dispatch.

        Spawned (not awaited) for the same reason interactions are: handle_frame
        must return promptly. Unlike an interaction this does **not** open one up
        front — whether the message drives one is the Brain's call, made by
        touching ``message.interaction``."""
        task = asyncio.create_task(
            self._run_client_message(message),
            name=f"client-message-{message.id or message.type}",
        )
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    def _materialize_client_interaction(self, message: ClientMessage) -> Interaction:
        """Open + register the interaction a Brain takes the floor with from
        ``on_client_message`` (via ``message.interaction``).

        Bound to the message's stimulus, registered in ``_interactions`` (so its
        inference finalize resolves) and ``_pending`` against the running
        ``on_client_message`` task (so a barge-in cancels the response and teardown
        tears it down), exactly like a Voice-opened interaction — the only
        difference is who opened it."""
        assert self._session is not None
        interaction = Interaction(
            self,
            message._epoch,
            "",
            self._session,
            self._brain,
            source=InteractionSource.CLIENT_MESSAGE,
            client_message=message,
        )
        self._interactions[interaction.id] = interaction
        task = asyncio.current_task()
        if task is not None:
            self._pending[interaction.id] = _Pending(interaction, task)
        return interaction

    async def _run_client_message(self, message: ClientMessage) -> None:
        try:
            await self._brain.on_client_message(message._session, message)
        except asyncio.CancelledError:
            raise  # barge-in cut a response mid-flight (Voice finalizes the cut inference)
        except Exception:
            # The turn failed; the session stays live.
            logger.exception("brain: on_client_message failed for message type {}", message.type)
        finally:
            if message._interaction is not None:
                self._pending.pop(message._interaction.id, None)

    async def _dispatch_interaction(self, interaction: Interaction) -> None:
        """Route an interaction to its floor-owning callback by ``source``.

        Only the two Voice-opened triggers reach here (``USER`` / ``IDLE``); a
        ``CLIENT_MESSAGE`` interaction is materialized and driven from within
        ``on_client_message`` (see :meth:`_run_client_message`), not spawned here."""
        if interaction.source is InteractionSource.IDLE:
            await self._brain.on_user_idle(interaction)
        else:
            await self._brain.on_interaction(interaction)

    async def _run_interaction(self, interaction: Interaction) -> None:
        try:
            await self._dispatch_interaction(interaction)
        except asyncio.CancelledError:
            raise  # barge-in cut the turn (Voice finalizes the cut inference)
        except Exception:
            # The brain failed this turn; the session stays live. Adapters layer a
            # spoken fallback on top of this.
            logger.exception("brain: on_interaction failed for interaction {}", interaction.id)
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
