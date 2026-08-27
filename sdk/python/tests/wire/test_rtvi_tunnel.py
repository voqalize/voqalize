"""The app→brain leg of the RTVI tunnel, over the real stack.

Voqalize forwards every whitelisted message and interprets none of them.
Handling one cannot make the brain speak — nothing about a tap means the human
stopped talking — so ``on_rtvi`` is a coroutine, not a generator, and a brain
that writes one anyway is contained rather than obeyed.

Also covered here: an envelope body this build has never heard of must be
skipped, not raised — a newer peer adding a frame cannot kill the read loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid

from voqalize.sdk.wire import (
    RTVIFrame,
    RTVIType,
    SessionStartFrame,
    SpeechStartFrame,
    Wire,
    WireConfig,
    WireSerializer,
)

MSG_DATA = {"t": "state_sync", "d": {"screen": "cart", "items": [1, 2, 3]}}


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

    assert await WireSerializer().deserialize_message(unknown) is None


class _Recorder:
    def __init__(self) -> None:
        self.seen: list[tuple[RTVIType, object]] = []
        self.got = asyncio.Event()


async def _run_rtvi(*, speak: bool) -> tuple[_Recorder, list]:
    """Deliver one app message to a live Brain over a real socket.

    Returns the recorder and every frame the Brain emitted back.
    """
    from voqalize.conformance import BrainServer
    from voqalize.sdk import Brain, Chunk, SpeechEnd, SpeechStart

    rec = _Recorder()

    class Recording(Brain):
        async def on_rtvi(self, session, msg):
            rec.seen.append((msg.type, msg.data))
            rec.got.set()

    class Speaking(Brain):
        """The contract violation, written out: a generator body on the one
        callback that is awaited rather than driven."""

        async def on_rtvi(self, session, msg):  # type: ignore[override]
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
    wire = Wire(WireConfig(url=f"ws://127.0.0.1:{port}?session_id={session_id}"))
    await wire.start()
    ser = WireSerializer()
    emitted: list = []
    try:
        await wire.send(
            await ser.serialize(SessionStartFrame(turn_id=1, session_id=session_id)),
        )
        await wire.send(
            await ser.serialize(RTVIFrame(type=RTVIType.CLIENT_MESSAGE, data=MSG_DATA)),
        )
        # A violating brain never reaches its own body, so there is nothing to
        # wait for — give it a short beat and let the assertions speak.
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(rec.got.wait(), timeout=0.3 if speak else 3.0)

        # Drain whatever the brain emitted; the socket goes quiet once it is done.
        async def _drain() -> None:
            while True:
                frame = await ser.deserialize_message(await wire.recv())
                if frame is not None:
                    emitted.append(frame)

        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(_drain(), timeout=0.6)
    finally:
        await wire.close()
        await server.aclose()
    return rec, emitted


async def test_an_app_message_reaches_the_seam() -> None:
    """The seam fires with the message exactly as sent, and the session stays silent."""
    rec, emitted = await _run_rtvi(speak=False)

    assert rec.seen == [(RTVIType.CLIENT_MESSAGE, MSG_DATA)]
    assert not [f for f in emitted if isinstance(f, SpeechStartFrame)]


async def test_speaking_from_an_app_message_puts_nothing_on_the_wire() -> None:
    """The signature says coroutine; the runtime enforces it rather than trusting it.

    A tap that made the brain start talking would cut across whatever the human was
    saying. The generator is closed unstarted, so not a byte of speech reaches
    Voqalize — and because it never runs, the body's own bookkeeping does not happen
    either. A contract violation is refused whole, not half-honoured.
    """
    rec, emitted = await _run_rtvi(speak=True)

    assert rec.seen == []
    assert not [f for f in emitted if isinstance(f, SpeechStartFrame)]
