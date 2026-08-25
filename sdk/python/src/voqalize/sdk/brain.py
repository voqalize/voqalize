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

**Voqalize owns the floor; the brain spends it.** Voqalize decides when the brain may
speak, and it does that by calling one of the two speaking callbacks. There is no
``request_floor`` and no way to interrupt the user — that absence is what makes
the system predictable, and everything else here follows from it.

A speaking callback is an async generator, and **the generator is the mouth**:
``SpeechStart`` / ``Chunk`` / ``SpeechEnd`` are the only things it may yield,
because speech is the only thing whose position on the audio timeline is its
meaning. Awaiting between them is fine — that is how a tool call sits between two
things you say.

Everything else is a method on the :class:`Session` handed to every callback:
``session.dispatch(action)`` to render, ``await session.configure(...)``
to switch language, ``session.end()`` to hang up. Those are floor-free, so they
read the same from inside a turn and from the five callbacks that are not
generators at all — and, called at the same point in a generator body, they reach
the wire at exactly the same point as a yield would.

``configure`` is awaited, because Voqalize answers it. Awaiting is how a language
it has no recognizer for becomes a :class:`RequestRejected` you handle, rather
than a call that runs on sounding wrong and reports nothing. It is safe to await
from anywhere a brain runs, including from inside a turn.

The turn is over when the generator returns. **It does not wait for the audio to
finish playing**, which is the part that surprises people: what the user actually
heard arrives later, per speech unit, at :meth:`Brain.on_finalize`.

Mapping onto the wire:

- ``on_user_message``       ← ``UserMessageFrame``
- ``on_user_idle``          ← ``UserIdleFrame``
- ``on_rtvi``               ← ``RTVIFrame``
- ``SpeechStart``/``SpeechEnd`` → ``Speech{Start,End}Frame`` (mints one ``speech_id``)
- ``Chunk``                 → ``SpeechChunkFrame``
- ``on_finalize``           ← ``FinalizeFrame``
- ``session.send_rtvi``     → ``RTVIFrame``
- an ``Action``             → an RTVI ``ui-command``
- ``configure_*``           → a ``Configure*Frame``, answered by one ``ResponseFrame``
- barge-in                  ← ``InterruptionFrame`` → every turn through the watermark is cancelled

Correlation never appears in this surface. Voqalize mints a ``turn_id`` for each
stimulus and the SDK binds the speech it produces to that turn, so a barge-in can
name exactly what is dead.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextvars import ContextVar
from typing import Any

from loguru import logger

from .actions import Action
from .engine import Emitter, SessionAdapter, SessionFactory
from .events import (
    Chunk,
    Error,
    Finalize,
    RTVIMessage,
    Speech,
    SpeechEnd,
    SpeechStart,
    UserIdle,
    UserMessage,
)
from .outbound import CortexAgent
from .wire import (
    WIRE_VERSION,
    Config,
    ConfigureFrame,
    ConfigureRequest,
    EndFrame,
    ErrorCode,
    ErrorFrame,
    FinalizeFrame,
    FinalizeReason,
    Frame,
    InterruptionFrame,
    ResponseFrame,
    RTVIFrame,
    RTVIType,
    SessionStartFrame,
    SpeechChunkFrame,
    SpeechEndFrame,
    SpeechStartFrame,
    UserIdleFrame,
    UserMessageFrame,
)
from .wire.frames import RTVI_TO_APP

__all__ = [
    "Brain",
    "RequestRejected",
    "Session",
    "WireError",
    "adapter_for",
    "brain_factory",
    "serve",
]

# The turn a brain callback is running for, so floor-free calls made from inside
# one can annotate what they send without the brain threading it through.
_current_turn: ContextVar[int | None] = ContextVar("voqalize_turn", default=None)

#: How long a `session.configure_*` call waits for Voqalize's answer. Comfortably
#: past Voqalize's own wait on the recognizer, so a rejection in flight
#: arrives as a rejection rather than as a timeout.
REQUEST_TIMEOUT_S = 10.0


class WireError(RuntimeError):
    """A brain broke one of its four obligations:

    1. **Balanced brackets.** Every ``SpeechStart`` is followed by a
       ``SpeechEnd``; a ``Chunk`` outside a unit is a wire error.
    2. **You don't block.** A callback that stalls holds the floor open and the
       caller hears nothing.
    3. **You don't speak outside a speaking callback.**
    4. **``greet`` is fast.** It runs before the caller has heard anything.

    Almost always the first: an unbalanced bracket, or speech yielded from a
    callback that holds no floor.
    """


class RequestRejected(RuntimeError):
    """Voqalize refused a ``session.configure`` call and applied none of it.

    A request is accepted or rejected whole, so on this exception the previous
    setting is still in force and the call is still coherent — an unsupported
    language leaves both legs where they were rather than moving one of them.
    ``detail`` is Voqalize's own reason, written to be shown.
    """

    def __init__(self, op: str, detail: str) -> None:
        super().__init__(f"{op} rejected: {detail}")
        self.op = op
        self.detail = detail


# ─── The session ──────────────────────────────────────────────────────────────


class Session:
    """The capability handle: it emits to the wire, and it owns the in-flight
    machinery whose lifetime is exactly the socket.

    That rule is what keeps it thin. In-flight request ids die when the socket
    dies, so they live here. Conversation history, model context and domain state
    have a different lifetime — they may outlive the session — and belong to the
    brain.
    """

    def __init__(self, adapter: _BrainAdapter, session_id: str, init: dict[str, Any]) -> None:
        self._adapter = adapter
        #: The session id Voqalize assigned.
        self.id = session_id
        #: The opaque init data Voqalize was handed at connect. Read your own keys
        #: out of it — the SDK never interprets it.
        self.init = init
        # One id per speech unit, session-monotonic. Voqalize never reads it — it
        # comes back on the Finalize naming the unit it belongs to, and nothing
        # on that side compares, orders or formats it.
        self._speech_seq = 0
        # One id per configure request, session-monotonic. Its whole job is to
        # name the answer that comes back.
        self._request_seq = 0
        self._awaiting: dict[int, asyncio.Future[ResponseFrame]] = {}
        self._ended = False

    # ─── The app ────────────────────────────────────────────────────────

    def send_rtvi(self, type: RTVIType, data: Any = None, *, id: str | None = None) -> None:
        """Send one RTVI message to the app. Never blocks.

        Callable from anywhere — inside a turn, from work that finished long
        after the turn that started it — because a message carries no audio and so
        needs no floor. Inside a turn it hits the wire in
        the order it runs, so it cannot jump ahead of speech you already yielded,
        and it is annotated with that turn for traces.

        Quote ``id`` back from the message you are answering when RTVI gave it
        one. Only the five types in
        :data:`~voqalize.sdk.wire.frames.RTVI_TO_APP` may be sent; the app
        originates the rest, and Voqalize refuses one arriving from a brain.
        """
        if type not in RTVI_TO_APP:
            raise WireError(
                f"a brain may not send RTVI {type.value!r}: the app originates it. "
                f"Sendable types are {sorted(t.value for t in RTVI_TO_APP)}."
            )
        self._adapter.emit(RTVIFrame(type=type, data=data, id=id, turn_id=_current_turn.get()))

    def dispatch(self, action: Action) -> None:
        """Send an action to the app. Never blocks, and nothing comes back.

        Sugar over :meth:`send_rtvi`: it rides RTVI's own ``ui-command``, which a
        pipecat client reads with ``useUICommandHandler`` and no adapter of ours.
        An answer is an ordinary ``client-message`` arriving at
        :meth:`Brain.on_rtvi`, correlated by whatever your app puts in it.
        """
        self.send_rtvi(
            RTVIType.UI_COMMAND,
            {"command": type(action).__voqal_action__, "payload": action.to_payload()},
        )

    def _discard_pending(self) -> None:
        for future in self._awaiting.values():
            future.cancel()
        self._awaiting.clear()

    # ─── Ending the call ────────────────────────────────────────────────

    def end(self, reason: str = "agent_ended") -> None:
        """Hang up. Callable from anywhere — every callback is handed the session.

        To say goodbye first, speak it and then call this: the generator body
        resumes only after the SDK has consumed everything you yielded, so
        writing it in that order *is* the ordering, and the goodbye is heard.
        Voqalize ends on a *control* frame — delivered in order, TTS finishing the
        contexts already open and the transport playing out its audio queue
        before either stops — so nothing already spoken is cut off. To abandon a
        call instead, call this without speaking first. Idempotent. ``reason`` is
        logged locally; Voqalize never needs the brain's rationale to hang up, so it
        does not cross the wire.
        """
        if self._ended:
            return
        self._ended = True
        logger.info("session {}: ending (reason={})", self.id, reason)
        self._adapter.emit(EndFrame())

    # ─── Configuration ──────────────────────────────────────────────────
    #
    # Every one of these is a request, and every request is answered. Awaiting
    # the answer is how a setting Voqalize cannot honour becomes an exception here
    # instead of a call that sounds wrong and reports nothing.
    #
    # Accepted means Voqalize took the change, not that you can hear it yet: each
    # method says below where its boundary is.

    async def configure(self, config: Config) -> None:
        """Override the session's configuration. Brain → Voqalize.

        The session already opened on the agent record's defaults, so this is for
        a condition that changed *during* the call — the caller switched
        language, the line got noisy, this one needs longer to think. It is not
        how a session is initialized; by the time a brain runs, the pipeline is
        built and speaking::

            await session.configure(
                Config(
                    stt=SttConfig(language=Language.TA),
                    tts=TtsConfig(language=Language.TA, voice=Voice.OMNIVOICE_GAURI),
                )
            )

        Both language legs, always — :class:`Config` refuses to be built with one
        and not the other, because half a language change is silent. They may
        differ: ten of the twenty-three languages can be spoken, so a call heard
        in Odia is spoken with the Hindi clip, said out loud rather than
        substituted behind your back.

        Where each section lands, since none of them is instant:

        - **tts** — the next speech unit. The synthesizer locks the voice for one
          synthesis context and Voqalize pins one context per unit, so the
          sentence being spoken finishes in the old voice.
        - **stt** — once the open turn commits. The recognizer carries per-turn
          decoder state, so the turn being spoken still transcribes as spoken.
        - **idle** — immediately. Voqalize owns that timer, and one already
          running restarts on the new duration before the answer comes back.

        Accepted means Voqalize took the change, not that you can hear it yet.
        Rejection is all-or-nothing and raises :class:`RequestRejected` with the
        reason: nothing in the request applied, and the call is still wholly in
        the state it was in.
        """
        await self._request("configure", ConfigureFrame(config=config))

    async def _request(self, op: str, frame: ConfigureRequest) -> None:
        """Send one request and block on its answer.

        Safe from anywhere a brain runs — Voqalize's answer bypasses the frame lanes
        entirely, so awaiting one inside a callback cannot stall the delivery of
        the answer it is waiting for.
        """
        self._request_seq += 1
        frame.request_id = self._request_seq
        future: asyncio.Future[ResponseFrame] = asyncio.get_running_loop().create_future()
        self._awaiting[frame.request_id] = future
        self._adapter.emit(frame)
        try:
            response = await asyncio.wait_for(future, REQUEST_TIMEOUT_S)
        except TimeoutError:
            raise TimeoutError(
                f"{op}: Voqalize did not answer within {REQUEST_TIMEOUT_S:g}s, so whether "
                f"it applied is unknown"
            ) from None
        finally:
            self._awaiting.pop(frame.request_id, None)
        if not response.accepted:
            raise RequestRejected(op, response.detail)

    def _settle_request(self, frame: ResponseFrame) -> None:
        future = self._awaiting.pop(frame.request_id, None)
        if future is None:
            logger.warning(
                "session {}: answer to request {} arrived with nobody waiting",
                self.id,
                frame.request_id,
            )
            return
        if not future.done():
            future.set_result(frame)

    # ─── Internal ───────────────────────────────────────────────────────

    def _next_speech_id(self) -> int:
        self._speech_seq += 1
        return self._speech_seq


# ─── The Brain contract ───────────────────────────────────────────────────────


class Brain:
    """Subclass this. Your object holds only your state; capability arrives as the
    ``session`` passed into every callback.

    Only :meth:`on_user_message` is required.

    **Voice and language are a call to :meth:`Session.configure` from
    :meth:`on_session_start`**, which runs before the greeting::

        from voqalize.sdk.wire import Config, Language, SttConfig, TtsConfig, Voice

        class ConciergeBrain(Brain):
            async def on_session_start(self, session: Session) -> None:
                await session.configure(
                    Config(
                        stt=SttConfig(language=Language.HI),
                        tts=TtsConfig(language=Language.HI, voice=Voice.OMNIVOICE_GAURI),
                    )
                )

    A hook, not a class attribute, because the language is often *this* call's:
    the caller's own, or the connecting page's, neither of which a value fixed at
    import time can name. A brain that has no such choice to make writes the
    constant here and pays nothing for it.

    A page that settles the language before the call exists sends it with the
    connect request instead, and this brain configures nothing — one answer, one
    authority.
    """

    # Set by the adapter the moment the session exists — before
    # `on_session_start`, before anything a subclass can override. A class-level
    # default so a subclass that defines `__init__` without calling super still
    # has it.
    _session: Session | None = None

    @property
    def session(self) -> Session:
        """The session this brain serves, reachable from anywhere on the instance.

        Every hook is also *handed* the session, and inside a hook that parameter
        is the one to use — it is the same object, and it cannot be unset. This
        property exists for the code that cannot be handed anything: a tool's
        signature is the schema Gemini is given, so a `session` parameter would be
        something the model tries to fill. Tools read `self.session`; hooks take
        the parameter. The line between them is whether we call it or the model does.
        """
        if self._session is None:
            raise RuntimeError(
                f"{type(self).__name__}.session was read before the session started. "
                "It is set by the SDK when Voqalize opens the call, so it is available "
                "in every hook and every tool — but not in __init__."
            )
        return self._session

    # ─── Lifecycle ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        """Setup. Runs before :meth:`greet`, which is what makes a
        :meth:`Session.configure` call here land before the first word is
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
        """A signal from Voqalize — today, that the wire dropped data under
        congestion. The session is never killed by it. Default: ignore."""

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

    def on_user_idle(self, session: Session, idle: UserIdle) -> AsyncGenerator[Speech, None]:
        """The human went quiet past the idle timeout and the floor is yours if
        you want it. ``idle.level`` counts escalations, so you can nudge gently at
        1 and wrap up at 3. Default: say nothing and let the silence ride."""
        return _nothing()

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """The app said something — a tap, a keystroke, a state push::

            async def on_rtvi(self, session, msg):
                if msg.type is not RTVIType.CLIENT_MESSAGE:
                    return
                kind, payload = msg.data["t"], msg.data.get("d") or {}
                if kind == "state_sync":
                    self.screen = payload
                elif kind == "catalog_search":
                    session.dispatch(ShowSearchResults(rows=self.search(payload["query"])))
                elif kind == "hang_up":
                    session.end(reason="user tapped hang up")

        Not a generator, which is the whole point: a click can update the screen
        or end the call, but it cannot make the agent start talking over the
        person clicking. There is nothing to yield here, so that rule needs no
        runtime check and cannot be broken. To speak to the app, call
        :meth:`Session.send_rtvi`.
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
        # Speech-capable work, by the turn it answers; a barge-in cancels every
        # turn through the watermark.
        self._turns: dict[asyncio.Task[None], int] = {}
        self._watermark = 0
        # Floor-free work — app messages, result callbacks — which a barge-in has
        # no reason to touch. Cancelled only at teardown.
        self._ambient: set[asyncio.Task[Any]] = set()

    # ─── Adapter services used by Session ───────────────────────────────

    def emit(self, frame: Frame) -> None:
        self._emitter.send(frame)

    def settle_response(self, frame: ResponseFrame) -> None:
        """Hand Voqalize's answer to whoever is blocked on it.

        Called straight off the reader rather than through the feeder, so it must
        stay synchronous and never block — see :mod:`.engine`.
        """
        if self._session is not None:
            self._session._settle_request(frame)

    def spawn(self, coro: Any) -> asyncio.Task[Any]:
        task = asyncio.ensure_future(coro)
        self._ambient.add(task)
        task.add_done_callback(self._ambient.discard)
        return task

    # ─── Inbound ────────────────────────────────────────────────────────

    async def handle_frame(self, frame: Frame) -> None:
        if isinstance(frame, SessionStartFrame):
            await self._start(frame)
            return

        session = self._session
        if session is None:
            return

        if isinstance(frame, UserMessageFrame):
            self._spawn_turn(
                session,
                frame.turn_id,
                _speech(self._brain.on_user_message(session, UserMessage(frame.text))),
            )
        elif isinstance(frame, UserIdleFrame):
            self._spawn_turn(
                session,
                frame.turn_id,
                _speech(self._brain.on_user_idle(session, UserIdle(frame.level, frame.idle_ms))),
            )
        elif isinstance(frame, InterruptionFrame):
            await self._raise_watermark(frame.through_turn)
        elif isinstance(frame, FinalizeFrame):
            await self._brain.on_finalize(
                session,
                Finalize(
                    speech_id=frame.speech_id,
                    heard=frame.heard_text,
                    interrupted=frame.reason is FinalizeReason.USER_BARGE_IN,
                ),
            )
        elif isinstance(frame, RTVIFrame):
            self._deliver_rtvi(session, frame)
        elif isinstance(frame, ErrorFrame):
            await self._brain.on_error(
                session, Error(code=frame.code, message=frame.message, fatal=frame.fatal)
            )

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
        session = Session(self, frame.session_id, dict(frame.init))
        self._session = session
        self._brain._session = session
        if frame.wire_version != WIRE_VERSION:
            self._refuse_version(session, frame.wire_version)
            return
        try:
            await self._brain.on_session_start(session)
        except Exception as exc:
            self._abort(session, "on_session_start", exc)
            return
        try:
            opening = await self._brain.greet(session)
        except Exception as exc:
            self._abort(session, "greet", exc)
            return
        if opening:
            # A turn like any other: `SessionStart` is turn 1, and a caller who
            # talks over the greeting interrupts it through that turn.
            self._spawn_turn(session, frame.turn_id, _one_unit(opening))

    def _refuse_version(self, session: Session, spoken: int) -> None:
        """Refuse a session whose wire version is not this SDK's.

        Voqalize speaks first, so this is the last moment either end can refuse
        before a call is running, and it is the only one where refusing costs
        nothing: no audio has been synthesized and the caller has heard nothing.
        A version that differs in either direction means the two ends do not
        agree on what the bytes mean, and guessing is the thing a version exists
        to prevent.
        """
        logger.error(
            "brain: refusing session {} — Voqalize speaks wire {}, this SDK speaks {}",
            session.id,
            spoken,
            WIRE_VERSION,
        )
        self.emit(
            ErrorFrame(
                code=ErrorCode.WIRE_VERSION,
                message=(
                    f"wire version mismatch: Voqalize speaks {spoken}, this SDK speaks {WIRE_VERSION}"
                ),
                fatal=True,
            )
        )
        session.end(reason="wire_version_mismatch")

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
        self.emit(ErrorFrame(code=ErrorCode.INTERNAL, message=f"{hook} failed: {exc}", fatal=True))
        session.end(reason=f"{hook}_failed")

    # ─── Driving what the brain yields ──────────────────────────────────

    async def _drive(self, session: Session, turn_id: int, gen: AsyncGenerator[Any, None]) -> None:
        """Pull one generator to exhaustion, putting each unit of speech on the wire.

        On a barge-in the driving task is cancelled: the generator is *closed*,
        not abandoned, so the brain's ``finally`` blocks run. A unit left open by
        anything *else* is closed on the wire, so a brain that crashes mid-speech
        does not leave the runtime waiting for a chunk that will never come.
        """
        speech_id: int | None = None
        cut = False
        try:
            async for event in gen:
                if isinstance(event, SpeechStart):
                    if speech_id is not None:
                        raise WireError("SpeechStart inside an open speech unit")
                    speech_id = session._next_speech_id()
                    self.emit(SpeechStartFrame(speech_id=speech_id, turn_id=turn_id))
                elif isinstance(event, Chunk):
                    if speech_id is None:
                        raise WireError("Chunk outside a speech unit")
                    if event.text:
                        self.emit(SpeechChunkFrame(speech_id=speech_id, text=event.text))
                elif isinstance(event, SpeechEnd):
                    if speech_id is None:
                        raise WireError("SpeechEnd with no open speech unit")
                    self.emit(SpeechEndFrame(speech_id=speech_id))
                    speech_id = None
                else:
                    raise WireError(f"a brain may not yield {type(event).__name__}")
        except asyncio.CancelledError:
            cut = True
            raise
        finally:
            if speech_id is not None and not cut:
                self.emit(SpeechEndFrame(speech_id=speech_id))
            await gen.aclose()

    def _spawn_turn(
        self, session: Session, turn_id: int, gen: AsyncGenerator[Speech, None]
    ) -> None:
        """Spawn, never await: ``handle_frame`` must return promptly so the runner
        keeps dispatching, and the response streams out of the spawned task."""
        if turn_id <= self._watermark:
            # Already interrupted before it started. Close the generator so the
            # brain's `finally` blocks still run.
            self.spawn(gen.aclose())
            return
        task = asyncio.create_task(
            self._run_turn(session, turn_id, gen), name=f"turn-{session.id}-{turn_id}"
        )
        self._turns[task] = turn_id
        task.add_done_callback(lambda t: self._turns.pop(t, None))

    async def _run_turn(
        self, session: Session, turn_id: int, gen: AsyncGenerator[Speech, None]
    ) -> None:
        token = _current_turn.set(turn_id)
        try:
            await self._drive(session, turn_id, gen)
        except asyncio.CancelledError:
            raise  # a barge-in cut the turn; Voqalize finalizes the unit it cut
        except Exception:
            logger.exception("brain: turn failed (session {}, turn {})", session.id, turn_id)
        finally:
            _current_turn.reset(token)

    async def _raise_watermark(self, through_turn: int) -> None:
        """Every turn at or through ``through_turn`` is dead.

        Nothing goes back on the wire: Voqalize set the watermark, so it already
        knows. A turn opened above it keeps the floor.
        """
        self._watermark = max(self._watermark, through_turn)
        for task, turn_id in list(self._turns.items()):
            if turn_id <= self._watermark:
                await _cancel(task)

    async def _cancel_turns(self) -> None:
        for task in list(self._turns):
            await _cancel(task)
        self._turns.clear()

    # ─── The app ────────────────────────────────────────────────────────

    def _deliver_rtvi(self, session: Session, frame: RTVIFrame) -> None:
        self.spawn(
            self._run_rtvi(session, RTVIMessage(type=frame.type, data=frame.data, id=frame.id))
        )

    async def _run_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        try:
            handled: Any = self._brain.on_rtvi(session, msg)
            if isinstance(handled, AsyncGenerator):
                # A `yield` anywhere in the body makes it a generator. Say so,
                # rather than let it surface as "object async_generator can't be
                # used in 'await' expression".
                await handled.aclose()
                raise WireError(
                    "on_rtvi must not be a generator: an app message never takes "
                    "the floor. Use session.dispatch(...) to render, "
                    "session.send_rtvi(...) to answer and session.end() to hang up."
                )
            await handled
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("brain: on_rtvi failed for {!r}", msg.type)


async def _cancel(task: asyncio.Task[Any]) -> None:
    if task.done():
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await task


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
