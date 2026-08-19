"""The browser→Brain client message, over the real stack.

Voice delivers every client message unconditionally, stamped with the epoch it
minted for it. The Brain decides whether to answer: reading ``message.interaction``
takes the floor, ignoring it leaves the session silent.

Also covered here: an envelope body this build has never heard of must be skipped,
not raised — a newer peer adding a frame cannot kill the read loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid

from voqalize.sdk.wire import (
    CortexFrameSerializer,
    FrameDirection,
    LLMFullResponseStartFrame,
    SessionStartFrame,
    Wire,
    WireConfig,
)

MSG_TYPE = "state_sync"
MSG_DATA = {"screen": "cart", "items": [1, 2, 3]}
EPOCH = 9


async def test_unknown_envelope_body_is_skipped_not_raised() -> None:
    """A frame added after this SDK shipped must not kill the read loop.

    Protobuf parks the unknown envelope field aside, so ``WhichOneof`` reports no
    body. ``deserialize_message`` — what the read loops call — logs and skips;
    every caller already treats a ``None`` frame as "nothing to dispatch". New
    frames are default-off, so ignoring one leaves the Brain behaving as before.
    """
    # Envelope carrying only field 99 (length-delimited, empty) — a body number
    # this build has never heard of.
    unknown = b"\x9a\x06\x00"

    decoded = await CortexFrameSerializer().deserialize_message(unknown)

    assert decoded.frame is None
    assert decoded.ack is None


class _Recorder:
    def __init__(self) -> None:
        self.seen: list[tuple[str, dict]] = []
        self.got = asyncio.Event()


async def _run_client_message(*, respond: bool) -> tuple[_Recorder, list, list[int]]:
    """Deliver one client message to a live Brain over a real socket.

    Returns the recorder, every frame the Brain emitted back, and the epoch each
    of those frames was stamped with.
    """
    from voqalize.sdk import Brain, DirectAgent, brain_factory
    from voqalize.sdk.wire import ClientMessageFrame

    rec = _Recorder()

    class Recording(Brain):
        async def on_interaction(self, interaction) -> None:  # pragma: no cover - unused
            pass

        async def on_client_message(self, session, message) -> None:
            rec.seen.append((message.type, message.data))
            if respond:
                async with message.interaction.say() as speech:
                    await speech.speak("noted")
            rec.got.set()

    agent = DirectAgent(
        factory=brain_factory(Recording), host="127.0.0.1", port=0, allow_unverified=True
    )
    port = await agent.start()
    session_id = str(uuid.uuid4())
    wire = Wire(WireConfig(url=f"ws://127.0.0.1:{port}/s/{session_id}"))
    await wire.start()
    ser = CortexFrameSerializer()
    emitted: list = []
    epochs: list[int] = []
    try:
        await wire.send(
            FrameDirection.DOWNSTREAM,
            await ser.serialize(SessionStartFrame(session_id=session_id, agent_id="compat")),
        )
        await wire.send(
            FrameDirection.DOWNSTREAM,
            await ser.serialize(
                ClientMessageFrame(msg_id="m-7", type=MSG_TYPE, data=MSG_DATA), epoch=EPOCH
            ),
        )
        await asyncio.wait_for(rec.got.wait(), timeout=3.0)

        # Drain whatever the brain emitted; the socket goes quiet once it is done.
        async def _drain() -> None:
            while True:
                _direction, data = await wire.recv()
                msg = await ser.deserialize_message(data)
                if msg.frame is not None:
                    emitted.append(msg.frame)
                    epochs.append(msg.epoch)

        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(_drain(), timeout=0.6)
    finally:
        await wire.close()
        await agent.aclose()
    return rec, emitted, epochs


async def test_client_message_reaches_on_client_message() -> None:
    """The seam fires with the message as sent, and a Brain that ignores the
    interaction says nothing."""
    rec, emitted, _ = await _run_client_message(respond=False)

    assert rec.seen == [(MSG_TYPE, MSG_DATA)]
    assert not [f for f in emitted if isinstance(f, LLMFullResponseStartFrame)]


async def test_response_echoes_the_epoch_voice_minted() -> None:
    """Answering means taking the floor on the interaction Voice opened — so the
    reply rides that epoch, unread and echoed exactly."""
    rec, emitted, epochs = await _run_client_message(respond=True)

    assert rec.seen == [(MSG_TYPE, MSG_DATA)]
    stamps = [
        e for f, e in zip(emitted, epochs, strict=True) if isinstance(f, LLMFullResponseStartFrame)
    ]
    assert stamps == [EPOCH]
