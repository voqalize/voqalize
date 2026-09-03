"""The Brain surface, driven directly through its adapter.

No sockets: ``_adapter_for`` plus a recording emitter is the whole harness, which
is what makes it the right place to pin behaviour the wire tests can only reach
by accident.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import voqalize.sdk as sdk
import voqalize.sdk.brain as brain_module
from voqalize.sdk import (
    Action,
    Brain,
    Chunk,
    ErrorCode,
    RTVIMessage,
    RTVIType,
    Session,
    SpeechEnd,
    SpeechStart,
    UserIdle,
    UserMessage,
)
from voqalize.sdk.brain import _adapter_for
from voqalize.sdk.wire import (
    WIRE_VERSION,
    ErrorFrame,
    FinalizeFrame,
    Frame,
    InterruptionFrame,
    RTVIFrame,
    SessionStartFrame,
    SpeechChunkFrame,
    SpeechStartFrame,
    UserIdleFrame,
    UserMessageFrame,
)

GREETING_TURN = 1


def test_the_public_surface_is_deliberate() -> None:
    """A helper becomes API the moment ``from voqalize.sdk import *`` names it."""
    assert sdk.__all__ == [
        "Action",
        "Brain",
        "Channel",
        "Chunk",
        "Error",
        "ErrorCode",
        "Finalize",
        "RTVIMessage",
        "RTVIType",
        "RequestRejected",
        "Session",
        "SessionRejected",
        "Speech",
        "SpeechEnd",
        "SpeechStart",
        "UserIdle",
        "UserMessage",
        "WireError",
        "configure_logging",
        "run_session",
        "serve",
        "session_context",
    ]
    assert brain_module.__all__ == [
        "Brain",
        "RequestRejected",
        "Session",
        "WireError",
        "serve",
    ]


class Recorder:
    """An :class:`Emitter` that keeps what the brain put on the wire."""

    def __init__(self) -> None:
        self.frames: list[Frame] = []

    def send(self, frame: Frame) -> None:
        self.frames.append(frame)

    def names(self) -> list[str]:
        return [type(f).__name__ for f in self.frames]

    def spoken(self) -> str:
        return "".join(f.text for f in self.frames if isinstance(f, SpeechChunkFrame))


def _client_message(t: str, d: dict | None = None) -> RTVIFrame:
    return RTVIFrame(type=RTVIType.CLIENT_MESSAGE, data={"t": t, "d": d or {}})


async def _open(brain: Brain) -> tuple[object, Recorder]:
    rec = Recorder()
    adapter = _adapter_for(brain, rec)
    await adapter.handle_frame(SessionStartFrame(turn_id=GREETING_TURN, session_id="s"))
    return adapter, rec


# ─── A failed on_session_start fails the call ─────────────────────────────────


class BrokenSetup(Brain):
    async def on_session_start(self, session: Session) -> None:
        raise RuntimeError("the CRM was down")

    async def greet(self, session: Session) -> str:
        return "Hi! How can I help?"

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[object, None]:
        yield SpeechStart()
        yield Chunk("still here")
        yield SpeechEnd()


async def test_a_failed_on_session_start_never_greets() -> None:
    """A greeting promises a working agent. If setup failed, the state behind that
    promise is not there, and speaking it anyway is a worse failure than silence —
    the caller believes the agent and talks to it."""
    _adapter, rec = await _open(BrokenSetup())
    await asyncio.sleep(0.02)
    assert rec.spoken() == ""


async def test_a_failed_on_session_start_fails_the_call() -> None:
    """Fail where the failure happened: a fatal error on the wire, then the end.
    Not a live session running on state that was never built."""
    _adapter, rec = await _open(BrokenSetup())
    await asyncio.sleep(0.02)
    errors = [f for f in rec.frames if isinstance(f, ErrorFrame)]
    assert len(errors) == 1
    assert errors[0].fatal
    assert errors[0].code is ErrorCode.INTERNAL
    assert "the CRM was down" in errors[0].message
    assert rec.names()[-1] == "EndFrame"


class BrokenGreeting(Brain):
    async def greet(self, session: Session) -> str:
        raise RuntimeError("the model timed out")

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[object, None]:
        yield SpeechStart()
        yield Chunk("still here")
        yield SpeechEnd()


async def test_a_failed_greet_fails_the_call() -> None:
    """The same rule for the other way a session opens. A greeting that never
    arrives is dead air on the one turn nothing retries — the caller is listening
    to a live line that will not speak first, and no check we have can see it."""
    _adapter, rec = await _open(BrokenGreeting())
    await asyncio.sleep(0.02)
    errors = [f for f in rec.frames if isinstance(f, ErrorFrame)]
    assert len(errors) == 1
    assert errors[0].fatal
    assert errors[0].message == "greet failed: the model timed out"
    assert rec.names()[-1] == "EndFrame"


# ─── The greeting is a turn like any other ───────────────────────────────────


class Greeter(Brain):
    async def greet(self, session: Session) -> str | None:
        return "hello"

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[object, None]:
        yield SpeechStart()
        yield Chunk("hi")
        yield SpeechEnd()


async def test_the_greeting_is_bound_to_the_session_start_turn() -> None:
    """``SessionStart`` *is* turn 1, so the greeting names it like any other unit
    of speech. There is no sentinel turn and no separate greeting arm."""
    _adapter, rec = await _open(Greeter())
    await asyncio.sleep(0.02)
    starts = [f for f in rec.frames if isinstance(f, SpeechStartFrame)]
    assert [f.turn_id for f in starts] == [GREETING_TURN]


# ─── The interruption watermark ──────────────────────────────────────────────


class Chatty(Brain):
    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[object, None]:
        yield SpeechStart()
        for word in msg.text.split():
            await asyncio.sleep(0.01)
            yield Chunk(word)
        yield SpeechEnd()


async def test_the_watermark_kills_the_turn_it_names() -> None:
    adapter, rec = await _open(Chatty())
    await adapter.handle_frame(UserMessageFrame(turn_id=2, text="one two three four five"))
    await asyncio.sleep(0.015)
    await adapter.handle_frame(InterruptionFrame(through_turn=2))
    await asyncio.sleep(0.08)
    assert rec.spoken() != "onetwothreefourfive"


async def test_a_turn_above_the_watermark_keeps_the_floor() -> None:
    """The watermark is a bound, not a stop button: it names everything through a
    turn, and a turn opened after it is untouched."""
    adapter, rec = await _open(Chatty())
    await adapter.handle_frame(InterruptionFrame(through_turn=4))
    await adapter.handle_frame(UserMessageFrame(turn_id=5, text="still mine"))
    await asyncio.sleep(0.08)
    assert rec.spoken() == "stillmine"


async def test_a_turn_already_under_the_watermark_never_starts() -> None:
    """A stale turn arriving behind the watermark that killed it is not run at
    all — the brain does not spend a model call answering a question the caller
    has already talked over."""
    adapter, rec = await _open(Chatty())
    await adapter.handle_frame(InterruptionFrame(through_turn=7))
    await adapter.handle_frame(UserMessageFrame(turn_id=6, text="too late"))
    await asyncio.sleep(0.08)
    assert rec.spoken() == ""


async def test_the_watermark_is_never_echoed() -> None:
    """Voqalize set the watermark, so it already knows. An echo would be a system
    frame overtaking the very speech the drain is waiting to see land."""
    adapter, rec = await _open(Chatty())
    await adapter.handle_frame(UserMessageFrame(turn_id=2, text="one two three"))
    await adapter.handle_frame(InterruptionFrame(through_turn=2))
    await asyncio.sleep(0.05)
    assert not [f for f in rec.frames if isinstance(f, InterruptionFrame)]


# ─── on_rtvi acts, but never speaks ──────────────────────────────────────────


class Refresh(Action):
    pass


class Hangup(Brain):
    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[object, None]:
        yield SpeechEnd()

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        name = msg.data["t"] if isinstance(msg.data, dict) else None
        if name == "hang_up":
            session.end(reason="user tapped hang up")
        elif name == "refresh":
            session.dispatch(Refresh())


async def test_an_app_message_may_end_the_session() -> None:
    """Every callback is handed the session, so hanging up needs no yieldable of
    its own — ``session.end()`` is reachable from all of them, and a tap on "end
    call" is not a sentence the agent has to say first."""
    adapter, rec = await _open(Hangup())
    await adapter.handle_frame(_client_message("hang_up"))
    await asyncio.sleep(0.02)
    assert rec.names() == ["EndFrame"]


async def test_an_app_message_may_render() -> None:
    """A click can update the screen. That is a ``session.dispatch``, not a yield —
    an action carries no audio, so it has no position on the audio timeline to
    express."""
    adapter, rec = await _open(Hangup())
    await adapter.handle_frame(_client_message("refresh"))
    await asyncio.sleep(0.02)
    assert rec.names() == ["RTVIFrame"]
    sent = rec.frames[0]
    assert isinstance(sent, RTVIFrame)
    assert sent.type is RTVIType.UI_COMMAND
    assert sent.data["command"] == "refresh"


class Talkative(Brain):
    """Tries to speak from an app message — a generator body where the contract
    says coroutine. There is no way to write this that type-checks."""

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[object, None]:
        yield SpeechEnd()

    async def on_rtvi(  # type: ignore[override]
        self, session: Session, msg: RTVIMessage
    ) -> AsyncGenerator[object, None]:
        yield SpeechStart()
        yield Chunk("I saw you click that")
        yield SpeechEnd()


async def test_an_app_message_still_may_not_take_the_floor() -> None:
    """A click cannot talk over the person clicking.

    The callback is awaited, not driven, so a generator body cannot reach the
    wire at all — it is closed unstarted and the floor stays where it was.
    """
    adapter, rec = await _open(Talkative())
    await adapter.handle_frame(_client_message("anything"))
    await asyncio.sleep(0.02)
    assert rec.spoken() == ""
    assert rec.frames == []


# ─── a speaking callback that never speaks ────────────────────────────────────


class SilentIdle(Brain):
    """``on_user_idle`` written the obvious way: no ``yield`` anywhere, so Python
    makes it a coroutine rather than the generator its annotation claims."""

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[object, None]:
        yield SpeechEnd()

    async def on_user_idle(self, session: Session, idle: UserIdle) -> None:  # type: ignore[override]
        if idle.level >= 3:
            session.end(reason="idle")


async def test_a_speaking_callback_that_never_speaks_still_runs() -> None:
    """Deciding not to take the floor is a real answer, and the natural way to
    write it has no ``yield`` in it. Driving that as a generator would fail at the
    first ``async for`` — a brain that does nothing, for a reason invisible in the
    source."""
    adapter, rec = await _open(SilentIdle())
    await adapter.handle_frame(UserIdleFrame(turn_id=2, level=1, idle_ms=5000))
    await asyncio.sleep(0.02)
    assert rec.frames == []
    await adapter.handle_frame(UserIdleFrame(turn_id=3, level=3, idle_ms=15000))
    await asyncio.sleep(0.02)
    assert rec.names() == ["EndFrame"]


# ─── the wire version gate ────────────────────────────────────────────────


async def test_a_session_that_speaks_our_wire_version_starts() -> None:
    """The gate is `!=`, so the happy path has to be pinned alongside the refusal:
    a version check that refuses everything would pass the test below."""
    rec = Recorder()
    adapter = _adapter_for(Greeter(), rec)
    await adapter.handle_frame(
        SessionStartFrame(turn_id=GREETING_TURN, session_id="s", wire_version=WIRE_VERSION)
    )
    await asyncio.sleep(0.02)
    assert rec.spoken() == "hello"


async def test_a_session_that_speaks_another_wire_version_is_refused() -> None:
    """Voqalize speaks first, so this is the last moment either end can refuse before
    a call is running and the only one where refusing is free — nothing has been
    synthesized and the caller has heard nothing. The brain never greets, and the
    error is fatal so the runtime ends the call rather than sitting mute."""
    rec = Recorder()
    adapter = _adapter_for(Greeter(), rec)
    await adapter.handle_frame(
        SessionStartFrame(turn_id=GREETING_TURN, session_id="s", wire_version=WIRE_VERSION + 1)
    )
    await asyncio.sleep(0.02)
    assert rec.names() == ["ErrorFrame", "EndFrame"]
    err = rec.frames[0]
    assert isinstance(err, ErrorFrame)
    assert err.fatal
    assert err.code is ErrorCode.WIRE_VERSION


async def test_an_older_wire_version_is_refused_too() -> None:
    """A lower version is not a subset of a higher one: the arms it names may have
    been renumbered or reused underneath it. Refusing in both directions is what
    keeps that from being a guess."""
    rec = Recorder()
    adapter = _adapter_for(Greeter(), rec)
    await adapter.handle_frame(
        SessionStartFrame(turn_id=GREETING_TURN, session_id="s", wire_version=WIRE_VERSION - 1)
    )
    await asyncio.sleep(0.02)
    assert rec.names() == ["ErrorFrame", "EndFrame"]


# ─── Naming a unit ────────────────────────────────────────────────────────────


class Namer(Brain):
    """A brain that names the unit it opens, which is how it recognises its own
    work when the report comes back — a filler line it wants kept out of its
    model's context, say."""

    def __init__(self) -> None:
        self.named: list[int] = []
        self.finalized: list[int] = []

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[object, None]:
        sid = session.next_speech_id()
        self.named.append(sid)
        yield SpeechStart(id=sid)
        yield Chunk("one moment")
        yield SpeechEnd()

    async def on_finalize(self, session: Session, fin: sdk.Finalize) -> None:
        self.finalized.append(fin.speech_id)


async def test_a_named_unit_carries_that_id_on_the_wire() -> None:
    """The id the brain took is the id the frames carry. Nothing renumbers it —
    Voqalize quotes it back exactly as it arrived."""
    brain = Namer()
    _adapter, rec = await _open(brain)
    await _adapter.handle_frame(UserMessageFrame(turn_id=2, text="hi"))  # type: ignore[attr-defined]
    await asyncio.sleep(0.02)

    starts = [f for f in rec.frames if isinstance(f, SpeechStartFrame) and f.turn_id == 2]
    assert [f.speech_id for f in starts] == brain.named


async def test_a_named_unit_comes_back_under_its_own_name() -> None:
    """The whole point: a brain can recognise the unit it opened without counting
    finalizes, which is what it needs to keep one line out of its model's
    context."""
    brain = Namer()
    adapter, _rec = await _open(brain)
    await adapter.handle_frame(UserMessageFrame(turn_id=2, text="hi"))  # type: ignore[attr-defined]
    await asyncio.sleep(0.02)
    sid = brain.named[0]

    await adapter.handle_frame(FinalizeFrame(speech_id=sid, heard_text="one moment"))  # type: ignore[attr-defined]

    assert brain.finalized == [sid]


async def test_an_unnamed_unit_still_gets_an_id() -> None:
    """Naming is optional. A brain with nothing to recognise writes what it always
    wrote, and the SDK takes the next id itself."""
    _adapter, rec = await _open(Greeter())
    await asyncio.sleep(0.02)
    starts = [f for f in rec.frames if isinstance(f, SpeechStartFrame)]
    assert [f.speech_id for f in starts] == [1]


class Abandoner(Brain):
    """Takes an id for a unit it then decides not to open — a tool answered, so
    the filler is no longer worth saying."""

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[object, None]:
        session.next_speech_id()  # taken, never used
        yield SpeechStart()
        yield Chunk("here they are")
        yield SpeechEnd()


async def test_taking_an_id_and_not_using_it_leaves_a_gap() -> None:
    """Ids are opaque and gaps mean nothing — Voqalize never orders or compares
    one — so allocating ahead of a unit that then goes unspoken costs nothing."""
    adapter, rec = await _open(Abandoner())
    await asyncio.sleep(0.02)
    await adapter.handle_frame(UserMessageFrame(turn_id=2, text="hi"))  # type: ignore[attr-defined]
    await asyncio.sleep(0.02)

    starts = [f for f in rec.frames if isinstance(f, SpeechStartFrame) and f.turn_id == 2]
    assert [f.speech_id for f in starts] == [2]  # 1 was taken and dropped


class Reuser(Brain):
    """A brain whose counter reset — per model call, per tool loop. This is the
    mistake a speech-id scheme invites, and it is the one Voqalize fails the
    session over: one finalize would arrive for two pieces of text with no way to
    tell which it describes."""

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[object, None]:
        yield SpeechStart(id=7)
        yield Chunk("first")
        yield SpeechEnd()
        yield SpeechStart(id=7)
        yield Chunk("second")
        yield SpeechEnd()


class Descender(Brain):
    """Two ids taken ahead of time and spoken in the other order. Unique, so a
    uniqueness rule would let it through — and Voqalize would still fail the
    session, because the rule there is that ids ascend."""

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[object, None]:
        first, second = session.next_speech_id(), session.next_speech_id()
        yield SpeechStart(id=second)
        yield Chunk("second")
        yield SpeechEnd()
        yield SpeechStart(id=first)
        yield Chunk("first")
        yield SpeechEnd()


async def test_a_reused_id_is_refused_at_the_call_site() -> None:
    """Refused here, where the brain author can see it, rather than on the wire —
    where Voqalize ends the session and the author reads it as a dropped call."""
    adapter, rec = await _open(Reuser())
    await adapter.handle_frame(UserMessageFrame(turn_id=2, text="hi"))  # type: ignore[attr-defined]
    await asyncio.sleep(0.02)

    assert rec.spoken() == "first"


async def test_an_id_that_does_not_ascend_is_refused_at_the_call_site() -> None:
    """The SDK holds the same rule the wire does. Holding only uniqueness here
    would let a brain send a descending id, and the session would die on the far
    end for something this end could see."""
    adapter, rec = await _open(Descender())
    await adapter.handle_frame(UserMessageFrame(turn_id=2, text="hi"))  # type: ignore[attr-defined]
    await asyncio.sleep(0.02)

    assert rec.spoken() == "second"
