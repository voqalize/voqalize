"""The Brain — callbacks in, speech and actions out.

    from voqalize.sdk import Brain, Chunk, SpeechEnd, SpeechStart

    class Greeter(Brain):
        async def greet(self, session):
            return "Hi! How can I help?"

        async def on_user_message(self, session, msg):
            yield SpeechStart()
            yield Chunk(f"You said: {msg.text}")
            yield SpeechEnd()

Host it from your own WebSocket route with :func:`voqalize.sdk.run_session`, or
over the Cortex relay with :func:`serve` when your process cannot accept one.

**Voice owns the floor; the brain spends it.** Voice decides when the brain may
speak, and it does that by calling one of the two speaking callbacks. There is no
``request_floor`` and no way to interrupt the user — that absence is what makes
the system predictable, and everything else here follows from it.

A speaking callback is an async generator, and **the generator is the mouth**:
``SpeechStart`` / ``Chunk`` / ``SpeechEnd`` are the only things it may yield,
because speech is the only thing whose position on the audio timeline is its
meaning. Awaiting between them is fine — that is how a tool call sits between two
things you say.

Everything else is a method on the :class:`Session` handed to every callback:
``session.dispatch(action)`` to render, ``session.configure_language(...)`` to
switch language, ``session.end()`` to hang up. Those are floor-free, so they read
the same from inside a turn and from the five callbacks that are not generators
at all — and, called at the same point in a generator body, they reach the wire
at exactly the same point as a yield would.

The turn is over when the generator returns. **It does not wait for the audio to
finish playing**, which is the part that surprises people: what the user actually
heard arrives later, per speech unit, at :meth:`Brain.on_finalize`.

Mapping onto the wire:

- ``on_user_message``       ← ``UserMessageFrame``
- ``on_user_idle``          ← ``UserIdleFrame``
- ``on_app_message``        ← ``ClientMessageFrame``
- ``SpeechStart``/``SpeechEnd`` → ``Speech{Start,End}Frame`` (mints one ``speech_id``)
- ``Chunk``                 → ``SpeechChunkFrame``
- ``on_finalize``           ← ``FinalizeFrame``
- an ``Action``             → ``ServerMessageFrame`` (a ``ui_command`` to the browser)
- barge-in                  ← ``InterruptionFrame`` → the turn is cancelled, then echoed back as the drain barrier

Correlation never appears in this surface. Voice stamps each stimulus with an
``epoch`` and the SDK echoes it, unread, on everything the brain emits while
handling that stimulus, so Voice's drain barrier can place a frame after an
interruption. Agent-initiated speech — the opening line — answers no stimulus and
rides epoch 0.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any, ClassVar

from loguru import logger

from .actions import Action, Result
from .engine import Emitter, Envelope, SessionAdapter, SessionFactory
from .events import (
    AppMessage,
    Chunk,
    Error,
    Finalize,
    IdleTrigger,
    Speech,
    SpeechEnd,
    SpeechStart,
    UserMessage,
)
from .outbound import CortexAgent
from .wire import (
    ClientMessageFrame,
    EndFrame,
    ErrorFrame,
    FinalizeFrame,
    FinalizeReason,
    Frame,
    InterruptionFrame,
    ServerMessageFrame,
    SessionStartFrame,
    SpeechChunkFrame,
    SpeechEndFrame,
    SpeechStartFrame,
    UpdateIdleSettingsFrame,
    UpdateSTTSettingsFrame,
    UpdateTTSSettingsFrame,
    UserIdleFrame,
    UserMessageFrame,
)

__all__ = [
    "ActionHandle",
    "Brain",
    "ProtocolError",
    "Session",
    "adapter_for",
    "brain_factory",
    "serve",
]

# The browser echoes an action's answer as a client message of this type.
ACTION_RESULT = "action_result"

# Agent-initiated speech answers no stimulus, so it echoes no epoch.
NO_EPOCH = 0


class ProtocolError(RuntimeError):
    """A brain broke one of its four obligations:

    1. **Balanced brackets.** Every ``SpeechStart`` is followed by a
       ``SpeechEnd``; a ``Chunk`` outside a unit is a protocol error.
    2. **You don't block.** A callback that stalls holds the floor open and the
       caller hears nothing.
    3. **You don't speak outside a speaking callback.**
    4. **``greet`` is fast.** It runs before the caller has heard anything.

    Almost always the first: an unbalanced bracket, or speech yielded from a
    callback that holds no floor.
    """


# ─── The session ──────────────────────────────────────────────────────────────


class ActionHandle:
    """What :meth:`Session.dispatch` hands back. ``await handle.result`` to block
    the turn on the browser's answer — but say something first, because you are
    holding the floor and an ``await`` with no preceding speech is dead air."""

    def __init__(self, action_id: int) -> None:
        self.action_id = action_id
        self._future: asyncio.Future[Result] = asyncio.get_running_loop().create_future()

    @property
    def result(self) -> asyncio.Future[Result]:
        """The browser's :class:`~voqalize.sdk.actions.Result`, once it answers or
        the action expires. Cancelled along with the turn on a barge-in."""
        return self._future


@dataclass
class _PendingAction:
    handle: ActionHandle
    on_result: Callable[[Result], Any] | None
    expiry: asyncio.Task[None] | None = None


class Session:
    """The capability handle: it emits to the wire, and it owns the in-flight
    machinery whose lifetime is exactly the socket.

    That rule is what keeps it thin. Action ids and pending result handlers die
    when the socket dies, so they live here. Conversation history, model context
    and domain state have a different lifetime — they may outlive the session —
    and belong to the brain.
    """

    def __init__(self, adapter: _BrainAdapter, session_id: str, init: dict[str, Any]) -> None:
        self._adapter = adapter
        #: The session id Voice assigned.
        self.id = session_id
        #: The opaque payload Voice was handed at connect. Read your own keys out
        #: of it — the SDK never interprets it.
        self.init = init
        # One id per speech unit, session-monotonic. Voice never reads it — it
        # comes back on the Finalize naming the unit it belongs to, and nothing
        # on that side compares, orders or formats it.
        self._speech_seq = 0
        self._action_seq = 0
        self._pending: dict[int, _PendingAction] = {}
        self._ended = False

    # ─── Actions ────────────────────────────────────────────────────────

    def dispatch(self, action: Action) -> ActionHandle:
        """Send an action to the browser. Never blocks.

        Callable from anywhere — inside a turn, from an ``on_result`` callback,
        from work that finished after the turn that started it — because an action
        carries no audio and so needs no floor. Inside a turn it hits the wire in
        the order it runs, so it cannot jump ahead of speech you already yielded.
        """
        self._action_seq += 1
        action_id = self._action_seq
        handle = ActionHandle(action_id)
        pending = _PendingAction(handle, action.on_result)
        self._pending[action_id] = pending
        if action.timeout_s is not None:
            pending.expiry = self._adapter.spawn(self._expire(action_id, action.timeout_s))
        self._adapter.emit(
            ServerMessageFrame(
                data={
                    "type": "ui_command",
                    "action": type(action).__voqal_action__,
                    "action_id": action_id,
                    **action.to_payload(),
                }
            )
        )
        return handle

    async def _expire(self, action_id: int, timeout_s: float) -> None:
        await asyncio.sleep(timeout_s)
        self._settle(Result(action_id=action_id, status="timeout"))

    def _settle(self, result: Result) -> None:
        pending = self._pending.pop(result.action_id, None)
        if pending is None:
            return
        if pending.expiry is not None and pending.expiry is not asyncio.current_task():
            pending.expiry.cancel()
        if not pending.handle.result.done():
            pending.handle.result.set_result(result)
        if pending.on_result is None:
            return
        outcome = pending.on_result(result)
        if inspect.isawaitable(outcome):
            self._adapter.spawn(outcome)

    def _discard_pending(self) -> None:
        for pending in self._pending.values():
            if pending.expiry is not None:
                pending.expiry.cancel()
        self._pending.clear()

    # ─── Ending the call ────────────────────────────────────────────────

    def end(self, reason: str = "agent_ended") -> None:
        """Hang up. Callable from anywhere — every callback is handed the session.

        To say goodbye first, speak it and then call this: the generator body
        resumes only after the SDK has consumed everything you yielded, so
        writing it in that order *is* the ordering, and the goodbye is heard.
        Voice ends on a *control* frame — delivered in order, TTS finishing the
        contexts already open and the transport playing out its audio queue
        before either stops — so nothing already spoken is cut off. To abandon a
        call instead, call this without speaking first. Idempotent. ``reason`` is
        logged locally; Voice never needs the brain's rationale to hang up, so it
        does not cross the wire.
        """
        if self._ended:
            return
        self._ended = True
        logger.info("session {}: ending (reason={})", self.id, reason)
        self._adapter.emit(EndFrame())

    # ─── Configuration ──────────────────────────────────────────────────

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
        turn boundary, TTS at the next speech unit (never mid-utterance).
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
        """Change TTS voice/language/model for the **next** speech unit.

        Not instantaneous: vql-speech locks voice/model/language per synthesis
        context and Voice pins one context per unit, so a change here takes effect
        once the current unit (if any) finishes — never mid-utterance. Only pass
        what you want to change.
        """
        settings: dict[str, Any] = {}
        if voice is not None:
            settings["voice"] = voice
        if language is not None:
            settings["language"] = language
        if model is not None:
            settings["model"] = model
        if settings:
            self._adapter.emit(UpdateTTSSettingsFrame(settings=settings))

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
        """Change STT VAD / turn-detection knobs mid-call.

        Unlike :meth:`configure_tts` these apply live with no queuing — vql-speech
        treats them as comparison bounds against self-resetting counters, safe to
        change mid-utterance. Field names match its ``Configure`` thresholds
        verbatim. Use it to widen the pause window for a slow or stammering
        talker, tighten it for a fast-turnaround flow, or adapt to a noisy line.
        """
        settings: dict[str, Any] = {}
        for key, value in (
            ("language_hint", language_hint),
            ("vad_confidence", vad_confidence),
            ("vad_min_volume", vad_min_volume),
            ("vad_start_frames", vad_start_frames),
            ("vad_stop_frames_to_trigger_update", vad_stop_frames_to_trigger_update),
            ("vad_eager_frames", vad_eager_frames),
            ("vad_barge_in_ms", vad_barge_in_ms),
            ("resume_frames", resume_frames),
            ("min_segment_speech_frames", min_segment_speech_frames),
            ("confidence_tail_ms", confidence_tail_ms),
        ):
            if value is not None:
                settings[key] = value
        if settings:
            self._adapter.emit(UpdateSTTSettingsFrame(settings=settings))

    def configure_idle(self, *, timeout_ms: int | None = None) -> None:
        """(Re)configure idle detection. ``timeout_ms`` is the silence after Voice
        stops speaking before it calls :meth:`Brain.on_user_idle`; ``0`` disables
        idle detection until you re-enable it."""
        if timeout_ms is not None:
            self._adapter.emit(UpdateIdleSettingsFrame(settings={"timeout_ms": timeout_ms}))

    # ─── Internal ───────────────────────────────────────────────────────

    def _next_speech_id(self) -> int:
        self._speech_seq += 1
        return self._speech_seq


# ─── The Brain contract ───────────────────────────────────────────────────────


class Brain:
    """Subclass this. Your object holds only your state; capability arrives as the
    ``session`` passed into every callback.

    Only :meth:`on_user_message` is required.

    **Voice and language are declared here, not configured elsewhere.** Set
    :attr:`voice` (and :attr:`language` if the agent doesn't speak English) as
    class attributes; the SDK applies them at session start, before
    :meth:`on_session_start` runs::

        class ConciergeBrain(Brain):
            voice = "omnivoice/gauri"
            language = "hi"

    They live on the brain because the brain is the only thing that knows the
    caller — an agent record holds one language for everyone, which is wrong the
    moment a customer speaks a different one. When the language depends on *this*
    call, leave the attribute unset and call :meth:`Session.configure_language`
    from :meth:`on_session_start` instead; it lands before the first word.
    """

    #: TTS voice for every session this brain serves, e.g. ``"omnivoice/gauri"``.
    #: ``None`` leaves the platform default in place.
    voice: ClassVar[str | None] = None

    #: ISO language code for both halves of the call — the recognizer *and* the
    #: voice — applied through :meth:`Session.configure_language` so the two can
    #: never half-apply. ``None`` leaves the platform default (English).
    language: ClassVar[str | None] = None

    # ─── Lifecycle ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        """Setup. Runs before :meth:`greet`, which is what makes a
        :meth:`Session.configure_language` call here land before the first word is
        spoken — that ordering is the contract, not an accident.

        This is also where a logical conversation spanning several sockets picks
        up: read your own identifier out of ``session.init`` and load your own
        history. The SDK persists nothing and interprets no identifier, so the
        transcript never leaves your environment.
        """

    async def on_session_end(self, session: Session) -> None:
        """Teardown, once, for any reason. Best-effort: exceptions are swallowed
        and it never blocks the socket from closing."""

    async def on_error(self, session: Session, error: Error) -> None:
        """A runtime signal — today, that the wire dropped data under congestion.
        The session is never killed by the runtime. Default: ignore."""

    # ─── The opening line ───────────────────────────────────────────────

    async def greet(self, session: Session) -> str | None:
        """The first thing the agent says, as one line. Return ``None`` (the
        default) to open silently, which is right for an agent that waits to be
        addressed.

        **No model call belongs here.** A fixed line, or at most a template over
        ``session.init`` — ``f"Hi {name}, how can I help?"`` — and nothing else.
        It is ``async`` so you can look up that name, not so you can generate the
        sentence: this is the one moment where the caller is sitting on a
        connected session hearing nothing, and a round-trip here is the single
        most expensive latency in the product.
        """
        return None

    # ─── The three triggers ─────────────────────────────────────────────

    def on_user_message(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]:
        """The human finished speaking, so the floor is yours. Yield speech;
        return when you are done::

            async def on_user_message(self, session, msg):
                yield SpeechStart()
                yield Chunk("Let me check that")
                yield SpeechEnd()

                rows = await self.catalog.search(msg.text)
                session.dispatch(ShowResults(rows=rows))

                yield SpeechStart()
                yield Chunk(f"I found {len(rows)}.")
                yield SpeechEnd()

        **The generator is the mouth.** Only speech is yieldable, because only
        speech has a position on the audio timeline. Everything else — an action,
        a language switch, hanging up — is a method on ``session``, callable from
        here and from the five callbacks that are not generators at all.
        """
        raise NotImplementedError("Brain.on_user_message must be implemented")

    def on_user_idle(self, session: Session, idle: IdleTrigger) -> AsyncGenerator[Speech, None]:
        """The human went quiet past the idle timeout and the floor is yours if
        you want it. ``idle.level`` counts escalations, so you can nudge gently at
        1 and wrap up at 3. Default: say nothing and let the silence ride."""
        return _nothing()

    async def on_app_message(self, session: Session, msg: AppMessage) -> None:
        """The application said something — a tap, a keystroke, a state push::

            async def on_app_message(self, session, msg):
                if msg.type == "state_sync":
                    self.screen = msg.data
                elif msg.type == "catalog_search":
                    session.dispatch(ShowSearchResults(rows=self.search(msg.data["query"])))
                elif msg.type == "hang_up":
                    session.end(reason="user tapped hang up")

        Not a generator, which is the whole point: a click can update the screen
        or end the call, but it cannot make the agent start talking over the
        person clicking. There is nothing to yield here, so that rule needs no
        runtime check and cannot be broken.
        """

    # ─── What landed ────────────────────────────────────────────────────

    async def on_finalize(self, session: Session, fin: Finalize) -> None:
        """One speech unit finished playing, and this is what the user *heard* —
        the delivered prefix, not what you generated.

        Fires once per unit that produced audio, after the callback that produced
        it has long returned. Record ``fin.heard``: a barged-in reply that
        generated three sentences and delivered one must go into history as one,
        or the model will reference things it never finished saying — a failure
        that is silent, cumulative, and invisible in every metric.
        """


# ─── The adapter: wire frames ↔ Brain callbacks ───────────────────────────────


class _BrainAdapter:
    """One per session. Translates inbound envelopes into ``Brain`` callbacks and
    drives what the brain yields back onto the wire."""

    def __init__(self, brain: Brain, emitter: Emitter) -> None:
        self._brain = brain
        self._emitter = emitter
        self._session: Session | None = None
        # Speech-capable work, cancelled by a barge-in.
        self._turns: set[asyncio.Task[None]] = set()
        # Floor-free work — app messages, result callbacks — which a barge-in has
        # no reason to touch. Cancelled only at teardown.
        self._ambient: set[asyncio.Task[Any]] = set()

    # ─── Adapter services used by Session ───────────────────────────────

    def emit(self, frame: Frame, *, epoch: int = 0, speech_id: int = 0) -> None:
        self._emitter.send(frame, epoch=epoch, speech_id=speech_id)

    def spawn(self, coro: Any) -> asyncio.Task[Any]:
        task = asyncio.ensure_future(coro)
        self._ambient.add(task)
        task.add_done_callback(self._ambient.discard)
        return task

    # ─── Inbound ────────────────────────────────────────────────────────

    async def handle_frame(self, env: Envelope) -> None:
        frame = env.frame

        if isinstance(frame, SessionStartFrame):
            await self._start(frame)
            return

        session = self._session
        if session is None:
            return

        if isinstance(frame, UserMessageFrame):
            self._spawn_turn(
                session,
                env.epoch,
                _speech(self._brain.on_user_message(session, UserMessage(frame.text))),
            )
        elif isinstance(frame, UserIdleFrame):
            self._spawn_turn(
                session,
                env.epoch,
                _speech(self._brain.on_user_idle(session, IdleTrigger(frame.level, frame.idle_ms))),
            )
        elif isinstance(frame, InterruptionFrame):
            # Cancel in flight first, then echo: the echo is Voice's drain
            # barrier, and it must not arrive before the frames it fences off
            # have stopped being produced.
            await self._cancel_turns()
            self.emit(InterruptionFrame())
        elif isinstance(frame, FinalizeFrame):
            await self._brain.on_finalize(
                session,
                Finalize(
                    speech_id=env.speech_id,
                    heard=frame.heard_text,
                    interrupted=frame.reason is FinalizeReason.USER_BARGE_IN,
                ),
            )
        elif isinstance(frame, ClientMessageFrame):
            self._deliver_app_message(session, frame)
        elif isinstance(frame, ErrorFrame):
            await self._brain.on_error(session, Error(message=frame.error, fatal=frame.fatal))

        # Anything else (End / Cancel / …) is a lifecycle frame the runner acts
        # on; the brain has no handler for it.

    async def close(self) -> None:
        await self._cancel_turns()
        for task in list(self._ambient):
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        if self._session is not None:
            self._session._discard_pending()
            with contextlib.suppress(Exception):
                await self._brain.on_session_end(self._session)

    # ─── Session start, then the opening line ───────────────────────────

    async def _start(self, frame: SessionStartFrame) -> None:
        session = Session(self, frame.session_id, dict(frame.payload))
        self._session = session
        self._apply_declared_voice(session)
        try:
            await self._brain.on_session_start(session)
        except Exception as exc:
            self._abort(session, "on_session_start", exc)
            return
        try:
            opening = await self._brain.greet(session)
            if not opening:
                return
            await self._drive(session, NO_EPOCH, _one_unit(opening))
        except Exception as exc:
            self._abort(session, "greet", exc)

    def _abort(self, session: Session, hook: str, exc: Exception) -> None:
        """Fail a session that could not be opened, rather than run it broken.

        The two ways to open a session fail differently and both end here. A
        greeting spoken over state that was never built promises a working agent
        the caller then talks to; a session whose greeting never arrives is dead
        air on the one turn nothing will retry. Neither is a state to keep a call
        alive in, and both are invisible to every check we have — the transcript
        is empty and no error surfaces. So the failure goes on the wire, fatal,
        naming the hook that raised.
        """
        logger.exception("brain: {} failed for session {}", hook, session.id)
        self.emit(ErrorFrame(error=f"{hook} failed: {exc}", fatal=True))
        session.end(reason=f"{hook}_failed")

    def _apply_declared_voice(self, session: Session) -> None:
        """Apply the brain's declared :attr:`Brain.voice` / :attr:`Brain.language`.

        Here, on the way into the session, rather than in a base class's
        ``on_session_start`` — a subclass that overrides that hook and forgets
        ``super()`` would silently lose its voice, and a wrong voice is inaudible
        to every automated check we have (accent and speaker identity do not show
        up in a transcript). Emitted before the brain's own hook, so a brain that
        resolves the language per caller can still override it there: later frame
        on the same ordered lane wins, and both land before the greeting audio.
        """
        language, voice = self._brain.language, self._brain.voice
        if language is not None:
            session.configure_language(language, voice=voice)
        elif voice is not None:
            session.configure_tts(voice=voice)

    # ─── Driving what the brain yields ──────────────────────────────────

    async def _drive(self, session: Session, epoch: int, gen: AsyncGenerator[Any, None]) -> None:
        """Pull one generator to exhaustion, putting each unit of speech on the wire.

        On a barge-in the driving task is cancelled: the generator is *closed*,
        not abandoned, so the brain's ``finally`` blocks run, and any unit still
        open is closed on the wire before we unwind.
        """
        speech_id: int | None = None
        try:
            async for event in gen:
                if isinstance(event, SpeechStart):
                    if speech_id is not None:
                        raise ProtocolError("SpeechStart inside an open speech unit")
                    speech_id = session._next_speech_id()
                    self.emit(SpeechStartFrame(), epoch=epoch, speech_id=speech_id)
                elif isinstance(event, Chunk):
                    if speech_id is None:
                        raise ProtocolError("Chunk outside a speech unit")
                    if event.text:
                        self.emit(
                            SpeechChunkFrame(text=event.text), epoch=epoch, speech_id=speech_id
                        )
                elif isinstance(event, SpeechEnd):
                    if speech_id is None:
                        raise ProtocolError("SpeechEnd with no open speech unit")
                    self.emit(SpeechEndFrame(), epoch=epoch, speech_id=speech_id)
                    speech_id = None
                else:
                    raise ProtocolError(f"a brain may not yield {type(event).__name__}")
        finally:
            if speech_id is not None:
                self.emit(SpeechEndFrame(), epoch=epoch, speech_id=speech_id)
            await gen.aclose()

    def _spawn_turn(self, session: Session, epoch: int, gen: AsyncGenerator[Speech, None]) -> None:
        """Spawn, never await: ``handle_frame`` must return promptly so the runner
        keeps dispatching, and the response streams out of the spawned task."""
        task = asyncio.create_task(
            self._run_turn(session, epoch, gen), name=f"turn-{session.id}-{epoch}"
        )
        self._turns.add(task)
        task.add_done_callback(self._turns.discard)

    async def _run_turn(
        self, session: Session, epoch: int, gen: AsyncGenerator[Speech, None]
    ) -> None:
        try:
            await self._drive(session, epoch, gen)
        except asyncio.CancelledError:
            raise  # a barge-in cut the turn; Voice finalizes the unit it cut
        except Exception:
            logger.exception("brain: turn failed (session {}, epoch {})", session.id, epoch)

    async def _cancel_turns(self) -> None:
        for task in list(self._turns):
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        self._turns.clear()

    # ─── App messages ───────────────────────────────────────────────────

    def _deliver_app_message(self, session: Session, frame: ClientMessageFrame) -> None:
        if frame.type == ACTION_RESULT:
            self._settle_action(session, frame.data)
            return
        msg = AppMessage(type=frame.type, data=frame.data, id=frame.msg_id)
        self.spawn(self._run_app_message(session, msg))

    async def _run_app_message(self, session: Session, msg: AppMessage) -> None:
        try:
            handled: Any = self._brain.on_app_message(session, msg)
            if isinstance(handled, AsyncGenerator):
                # A `yield` anywhere in the body makes it a generator. Say so,
                # rather than let it surface as "object async_generator can't be
                # used in 'await' expression".
                await handled.aclose()
                raise ProtocolError(
                    "on_app_message must not be a generator: an application "
                    "message never takes the floor. Use session.dispatch(...) to "
                    "render and session.end() to hang up."
                )
            await handled
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("brain: on_app_message failed for {!r}", msg.type)

    def _settle_action(self, session: Session, data: dict[str, Any]) -> None:
        action_id = data.get("action_id")
        if not isinstance(action_id, int):
            return
        status = data.get("status")
        session._settle(
            Result(
                action_id=action_id,
                status=status if status in ("ok", "error", "timeout") else "error",
                data=data.get("result"),
                error=data.get("error"),
            )
        )


async def _nothing() -> AsyncGenerator[Any, None]:
    """Yields nothing — the default for a callback that declines the floor."""
    for _ in ():
        yield


async def _just_run(coro: Awaitable[None]) -> AsyncGenerator[Any, None]:
    """Run a speaking callback that turned out not to be a generator.

    A callback body with no ``yield`` anywhere is an ordinary coroutine, not an
    async generator, and Python decides that from the source rather than the
    annotation — so a turn that only ends the call or only updates the screen is
    silently the wrong kind of object::

        async def on_user_idle(self, session, idle):
            if idle.level >= 3:
                session.end(reason="idle")

    That is the obvious way to write it and it never speaks. Running it is the
    only reading that is not a silent no-op.
    """
    await coro
    for _ in ():
        yield


def _speech(result: Any) -> AsyncGenerator[Any, None]:
    """Whatever a speaking callback returned, as something to drive."""
    if isinstance(result, AsyncGenerator):
        return result
    return _just_run(result)


async def _one_unit(opening: str) -> AsyncGenerator[Speech, None]:
    """The opening line as one speech unit."""
    yield SpeechStart()
    yield Chunk(opening)
    yield SpeechEnd()


# ─── Entry points ─────────────────────────────────────────────────────────────


def adapter_for(brain: Brain, emitter: Emitter) -> SessionAdapter:
    """Host an already-constructed ``Brain`` as a session adapter, with no socket
    anywhere — the seam tests drive the brain through. Hosting uses
    :func:`brain_factory`, which builds one per session."""
    return _BrainAdapter(brain, emitter)


def brain_factory(build: type[Brain] | Callable[[], Brain]) -> SessionFactory:
    """A ``SessionFactory`` that builds a fresh brain per session.

    ``build`` is a zero-arg callable returning a ``Brain`` — a subclass, or a
    closure capturing injected dependencies (``lambda: OrderBrain(catalog)``)."""

    def _factory(emitter: Emitter) -> SessionAdapter:
        return _BrainAdapter(build(), emitter)

    return _factory


async def serve(brain_cls: type[Brain] | Callable[[], Brain], **cortex_kwargs: Any) -> None:
    """Host ``brain_cls`` over the Cortex relay until the connection closes
    permanently — for a process that cannot accept an inbound WebSocket.

    ``await serve(MyBrain, api_key=..., version=..., cortex_url=...)``. Blocking by
    design: it runs every session on this one connection, and the caller decides
    where that call lives. When your application owns a WebSocket route, use
    :func:`voqalize.sdk.run_session` there instead.
    """
    await CortexAgent(factory=brain_factory(brain_cls), **cortex_kwargs).run()
