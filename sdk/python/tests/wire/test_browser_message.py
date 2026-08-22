"""The browser→brain message, over the real stack.

Voqalize delivers every one of them unconditionally and never interprets the type.
Handling one cannot make the server speak — nothing about a click means the human
stopped talking — so ``on_browser_message`` is a coroutine, not a generator, and a
brain that writes one anyway is contained rather than obeyed.

Also covered here: an envelope body this build has never heard of must be skipped,
not raised — a newer peer adding a frame cannot kill the read loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid

from voqalize.sdk.wire import (
    SessionStartFrame,
    SpeechStartFrame,
    Wire,
    WireConfig,
    WireSerializer,
)

MSG_TYPE = "state_sync"
MSG_DATA = {"screen": "cart", "items": [1, 2, 3]}


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

    decoded = await WireSerializer().deserialize_message(unknown)

    assert decoded.frame is None


class _Recorder:
    def __init__(self) -> None:
        self.seen: list[tuple[str, dict]] = []
        self.got = asyncio.Event()


async def _run_browser_message(*, speak: bool) -> tuple[_Recorder, list]:
    """Deliver one application message to a live Brain over a real socket.

    Returns the recorder and every frame the Brain emitted back.
    """
    from voqalize.conformance import BrainServer
    from voqalize.sdk import Brain, Chunk, SpeechEnd, SpeechStart
    from voqalize.sdk.wire import BrowserMessageFrame

    rec = _Recorder()

    class Recording(Brain):
        async def on_browser_message(self, session, msg):
            rec.seen.append((msg.type, msg.data))
            rec.got.set()

    class Speaking(Brain):
        """The contract violation, written out: a generator body on the one
        callback that is awaited rather than driven."""

        async def on_browser_message(self, session, msg):  # type: ignore[override]
            rec.seen.append((msg.type, msg.data))
            rec.got.set()
            yield SpeechStart()
            yield Chunk("noted")
            yield SpeechEnd()

    server = BrainServer(
        Speaking if speak else Recording,
        host="127.0.0.1",
        port=0,
        allow_unverified=True,
    )
    port = await server.start()
    session_id = str(uuid.uuid4())
    wire = Wire(WireConfig(url=f"ws://127.0.0.1:{port}/s/{session_id}"))
    await wire.start()
    ser = WireSerializer()
    emitted: list = []
    try:
        await wire.send(
            await ser.serialize(SessionStartFrame(session_id=session_id)),
        )
        await wire.send(
            await ser.serialize(BrowserMessageFrame(type=MSG_TYPE, data=MSG_DATA)),
        )
        # A violating brain never reaches its own body, so there is nothing to
        # wait for — give it a short beat and let the assertions speak.
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(rec.got.wait(), timeout=0.3 if speak else 3.0)

        # Drain whatever the brain emitted; the socket goes quiet once it is done.
        async def _drain() -> None:
            while True:
                data = await wire.recv()
                msg = await ser.deserialize_message(data)
                if msg.frame is not None:
                    emitted.append(msg.frame)

        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(_drain(), timeout=0.6)
    finally:
        await wire.close()
        await server.aclose()
    return rec, emitted


async def test_browser_message_reaches_the_seam() -> None:
    """The seam fires with the message exactly as sent, and the session stays silent."""
    rec, emitted = await _run_browser_message(speak=False)

    assert rec.seen == [(MSG_TYPE, MSG_DATA)]
    assert not [f for f in emitted if isinstance(f, SpeechStartFrame)]


async def test_speaking_from_a_browser_message_puts_nothing_on_the_wire() -> None:
    """The signature says coroutine; the runtime enforces it rather than trusting it.

    A tap that made the server start talking would cut across whatever the human was
    saying. The generator is closed unstarted, so not a byte of speech reaches
    Voqalize — and because it never runs, the body's own bookkeeping does not happen
    either. A contract violation is refused whole, not half-honoured.
    """
    rec, emitted = await _run_browser_message(speak=True)

    assert rec.seen == []
    assert not [f for f in emitted if isinstance(f, SpeechStartFrame)]
