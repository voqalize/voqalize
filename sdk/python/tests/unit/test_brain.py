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
    EndSession,
    Session,
    SpeechEnd,
    SpeechStart,
    UserMessage,
    adapter_for,
)
from voqalize.sdk.engine import Envelope
from voqalize.sdk.wire import (
    ClientMessageFrame,
    ErrorFrame,
    Frame,
    LLMTextFrame,
    SessionStartFrame,
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


# ─── on_app_message may hang up, but still may not speak ──────────────────────


class Hangup(Brain):
    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[object, None]:
        yield SpeechEnd()

    async def on_app_message(
        self, session: Session, msg: AppMessage
    ) -> AsyncGenerator[Action | EndSession, None]:
        yield EndSession(reason="user tapped hang up")


async def test_an_app_message_may_end_the_session() -> None:
    """A tap on "hang up" is the browser's, not a sentence the agent has to say
    first — so ``EndSession`` is on the app-message channel too, and typed."""
    adapter, rec = await _open(Hangup())
    await adapter.handle_frame(_env(ClientMessageFrame(msg_id="m1", type="hang_up", data={})))
    await asyncio.sleep(0.02)
    assert "EndFrame" in rec.names()


class Talkative(Brain):
    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[object, None]:
        yield SpeechEnd()

    async def on_app_message(
        self, session: Session, msg: AppMessage
    ) -> AsyncGenerator[object, None]:
        yield SpeechStart()
        yield Chunk("I saw you click that")
        yield SpeechEnd()


async def test_an_app_message_still_may_not_take_the_floor() -> None:
    """Widening the channel to ``EndSession`` must not widen it to speech: a click
    can end the call or update the screen, never talk over the person clicking."""
    adapter, rec = await _open(Talkative())
    await adapter.handle_frame(_env(ClientMessageFrame(msg_id="m1", type="anything", data={})))
    await asyncio.sleep(0.02)
    assert rec.spoken() == ""
