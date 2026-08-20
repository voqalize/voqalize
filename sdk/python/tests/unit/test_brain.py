"""The Brain surface, driven directly through its adapter.

No sockets: ``adapter_for`` plus a recording emitter is the whole harness, which
is what makes it the right place to pin behaviour the wire tests can only reach
by accident.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

from voqalize.sdk import (
    Action,
    AppMessage,
    Brain,
    Chunk,
    IdleTrigger,
    Session,
    SpeechEnd,
    SpeechStart,
    UserMessage,
)
from voqalize.sdk.brain import adapter_for
from voqalize.sdk.engine import Envelope
from voqalize.sdk.wire import (
    ClientMessageFrame,
    ErrorFrame,
    Frame,
    LLMTextFrame,
    SessionStartFrame,
    UserIdleFrame,
)


class Recorder:
    """An :class:`Emitter` that keeps what the brain put on the wire."""

    def __init__(self) -> None:
        self.frames: list[Frame] = []

    def send(self, frame: Frame, *, epoch: int = 0, inference_id: int = 0) -> None:
        self.frames.append(frame)

    def names(self) -> list[str]:
        return [type(f).__name__ for f in self.frames]

    def spoken(self) -> str:
        return "".join(f.text for f in self.frames if isinstance(f, LLMTextFrame))


def _env(frame: Frame) -> Envelope:
    return Envelope(frame=frame, epoch=0, inference_id=0, request_id=0)


async def _open(brain: Brain) -> tuple[object, Recorder]:
    rec = Recorder()
    adapter = adapter_for(brain, rec)
    await adapter.handle_frame(_env(SessionStartFrame(session_id="s", agent_id="a")))
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
    await asyncio.sleep(0)
    assert rec.spoken() == ""


async def test_a_failed_on_session_start_fails_the_call() -> None:
    """Fail where the failure happened: a fatal error on the wire, then the end.
    Not a live session running on state that was never built."""
    _adapter, rec = await _open(BrokenSetup())
    await asyncio.sleep(0)
    errors = [f for f in rec.frames if isinstance(f, ErrorFrame)]
    assert len(errors) == 1
    assert errors[0].fatal
    assert "the CRM was down" in errors[0].error
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
    await asyncio.sleep(0)
    errors = [f for f in rec.frames if isinstance(f, ErrorFrame)]
    assert len(errors) == 1
    assert errors[0].fatal
    assert errors[0].error == "greet failed: the model timed out"
    assert rec.names()[-1] == "EndFrame"


class HalfGreeting(Brain):
    async def greet(self, session: Session):
        async def opener():
            yield "Hi there, one moment"
            raise RuntimeError("the model died mid-sentence")

        return opener()

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[object, None]:
        yield SpeechEnd()


async def test_a_greeting_that_dies_mid_stream_closes_its_unit_then_fails() -> None:
    """A streamed greeting can fail after audio is already going out. The open
    unit still closes — an unclosed bracket is dead air for the rest of the call —
    and only then does the session fail."""
    _adapter, rec = await _open(HalfGreeting())
    await asyncio.sleep(0)
    assert rec.spoken() == "Hi there, one moment"
    assert rec.names() == [
        "LLMFullResponseStartFrame",
        "LLMTextFrame",
        "LLMFullResponseEndFrame",
        "ErrorFrame",
        "EndFrame",
    ]


# ─── on_app_message acts, but never speaks ────────────────────────────────────


class Refresh(Action):
    pass


class Hangup(Brain):
    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[object, None]:
        yield SpeechEnd()

    async def on_app_message(self, session: Session, msg: AppMessage) -> None:
        if msg.type == "hang_up":
            session.end(reason="user tapped hang up")
        elif msg.type == "refresh":
            session.dispatch(Refresh())


async def test_an_app_message_may_end_the_session() -> None:
    """Every callback is handed the session, so hanging up needs no yieldable of
    its own — ``session.end()`` is reachable from all of them, and a tap on "end
    call" is not a sentence the agent has to say first."""
    adapter, rec = await _open(Hangup())
    await adapter.handle_frame(_env(ClientMessageFrame(msg_id="m1", type="hang_up", data={})))
    await asyncio.sleep(0.02)
    assert rec.names() == ["EndFrame"]


async def test_an_app_message_may_render() -> None:
    """A click can update the screen. That is a ``session.dispatch``, not a yield —
    an action carries no audio, so it has no position on the audio timeline to
    express."""
    adapter, rec = await _open(Hangup())
    await adapter.handle_frame(_env(ClientMessageFrame(msg_id="m1", type="refresh", data={})))
    await asyncio.sleep(0.02)
    assert rec.names() == ["ServerMessageFrame"]


class Talkative(Brain):
    """Tries to speak from an app message — a generator body where the contract
    says coroutine. There is no way to write this that type-checks."""

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[object, None]:
        yield SpeechEnd()

    async def on_app_message(  # type: ignore[override]
        self, session: Session, msg: AppMessage
    ) -> AsyncGenerator[object, None]:
        yield SpeechStart()
        yield Chunk("I saw you click that")
        yield SpeechEnd()


async def test_an_app_message_still_may_not_take_the_floor() -> None:
    """A click cannot talk over the person clicking.

    The callback is awaited, not driven, so a generator body cannot reach the
    wire at all — it fails on the await and the floor stays where it was. No
    runtime check on what was yielded is needed, or possible.
    """
    adapter, rec = await _open(Talkative())
    await adapter.handle_frame(_env(ClientMessageFrame(msg_id="m1", type="anything", data={})))
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

    async def on_user_idle(self, session: Session, idle: IdleTrigger) -> None:  # type: ignore[override]
        if idle.level >= 3:
            session.end(reason="idle")


async def test_a_speaking_callback_that_never_speaks_still_runs() -> None:
    """Deciding not to take the floor is a real answer, and the natural way to
    write it has no ``yield`` in it. Driving that as a generator would fail at the
    first ``async for`` — a brain that does nothing, for a reason invisible in the
    source."""
    adapter, rec = await _open(SilentIdle())
    await adapter.handle_frame(_env(UserIdleFrame(level=1, idle_ms=5000)))
    await asyncio.sleep(0.02)
    assert rec.frames == []
    await adapter.handle_frame(_env(UserIdleFrame(level=3, idle_ms=15000)))
    await asyncio.sleep(0.02)
    assert rec.names() == ["EndFrame"]
