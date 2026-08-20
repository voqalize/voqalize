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
    Frame,
    LLMTextFrame,
    SessionStartFrame,
    UserMessageFrame,
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


# ─── A failed on_session_start must not cost the greeting ─────────────────────


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


async def test_a_failed_on_session_start_still_greets() -> None:
    """The call is already live and the caller is already listening. Setup that
    failed is the brain's to notice; permanent dead air on the opening line is
    not a way to report it — and it is the failure mode no monitor catches."""
    _adapter, rec = await _open(BrokenSetup())
    await asyncio.sleep(0)
    assert rec.spoken() == "Hi! How can I help?"


async def test_the_session_survives_a_failed_on_session_start() -> None:
    adapter, rec = await _open(BrokenSetup())
    await adapter.handle_frame(_env(UserMessageFrame(text="hello")))
    await asyncio.sleep(0.02)
    assert "still here" in rec.spoken()


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
