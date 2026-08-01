"""Cross-version wire compatibility for the browser→Brain client message.

PyGato and the Brains that talk to it promote at different times (pygato
dev-first; the demo brains to both envs at once), so all four old/new pairings
happen in production. The client message is the frame that changed: it gained a
Voice-minted ``interaction_id``, added as field 4 on the EXISTING envelope field
37 rather than as a new frame, precisely so none of the pairings break.

Covered here:

======================  ==================================================
pairing                 test
======================  ==================================================
old pygato → new SDK    ``test_unstamped_message_decodes_as_unstamped``
                        ``test_unstamped_message_reaches_on_client_message``
new pygato → new SDK    ``test_stamped_message_round_trips``
                        ``test_stamped_message_reaches_on_client_message``
new pygato → old SDK    ``test_old_three_field_parser_reads_stamped_message``
old pygato ← new SDK    ``test_unstamped_encoding_is_byte_identical_to_legacy``
any → either            ``test_unknown_envelope_body_is_skipped_not_raised``
======================  ==================================================
"""

from __future__ import annotations

import asyncio
import json
import uuid

from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

from voqalize.sdk.wire import (
    CortexFrameSerializer,
    FrameDirection,
    VqlLLMFullResponseStartFrame,
    VqlRTVIClientMessageFrame,
    VqlStartFrame,
    Wire,
    WireConfig,
)
from voqalize.sdk.wire import _frames_pb2 as pb

MSG_TYPE = "state_sync"
MSG_DATA = {"screen": "cart", "items": [1, 2, 3]}


def _legacy_envelope_bytes(*, msg_id: str, msg_type: str, data: dict) -> bytes:
    """The bytes an *old* pygato puts on the wire: envelope field 37 with only
    the original three fields — no ``interaction_id`` anywhere."""
    env = pb.Envelope()
    m = env.rtvi_client_message
    m.msg_id = msg_id
    m.type = msg_type
    m.data = json.dumps(data)
    return env.SerializeToString()


def _old_three_field_message_class():
    """The pre-stamp ``RTVIClientMessage`` (msg_id/type/data only), rebuilt at
    runtime — a stand-in for an SDK released before field 4 existed."""
    fdp = descriptor_pb2.FileDescriptorProto()
    fdp.name = "legacy_rtvi_client_message.proto"
    fdp.package = "legacy"
    fdp.syntax = "proto3"
    msg = fdp.message_type.add()
    msg.name = "RTVIClientMessage"
    for name, number in (("msg_id", 1), ("type", 2), ("data", 3)):
        field = msg.field.add()
        field.name = name
        field.number = number
        field.type = descriptor_pb2.FieldDescriptorProto.TYPE_STRING
        field.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    pool = descriptor_pool.DescriptorPool()
    return message_factory.GetMessageClass(pool.Add(fdp).message_types_by_name["RTVIClientMessage"])


# ─── Encode / decode ─────────────────────────────────────────────────────────


async def test_stamped_message_round_trips() -> None:
    """new pygato → new SDK: the Voice-minted stamp survives the round trip."""
    ser = CortexFrameSerializer()
    sent = VqlRTVIClientMessageFrame(interaction_id=42, msg_id="m-1", type=MSG_TYPE, data=MSG_DATA)

    got = await ser.deserialize(await ser.serialize(sent))

    assert isinstance(got, VqlRTVIClientMessageFrame)
    assert (got.interaction_id, got.msg_id, got.type, got.data) == (42, "m-1", MSG_TYPE, MSG_DATA)


async def test_unstamped_message_decodes_as_unstamped() -> None:
    """old pygato → new SDK: a three-field encoding still decodes.

    ``interaction_id`` is 0 — absent on the wire. Voice mints real ids from 1, so
    0 cannot collide with a live interaction and unambiguously means "unstamped".
    """
    payload = _legacy_envelope_bytes(msg_id="m-1", msg_type=MSG_TYPE, data=MSG_DATA)

    frame = await CortexFrameSerializer().deserialize(payload)

    assert isinstance(frame, VqlRTVIClientMessageFrame)
    assert (frame.msg_id, frame.type, frame.data) == ("m-1", MSG_TYPE, MSG_DATA)
    assert frame.interaction_id == 0


async def test_unstamped_encoding_is_byte_identical_to_legacy() -> None:
    """A frame with no stamp encodes to exactly the pre-stamp bytes.

    proto3 omits zero-valued scalars, so field 4 costs nothing when unset: a new
    sender that has no id to stamp is indistinguishable on the wire from an old
    one. That is what makes the change additive rather than a new frame.
    """
    encoded = await CortexFrameSerializer().serialize(
        VqlRTVIClientMessageFrame(interaction_id=0, msg_id="m-1", type=MSG_TYPE, data=MSG_DATA)
    )

    assert encoded == _legacy_envelope_bytes(msg_id="m-1", msg_type=MSG_TYPE, data=MSG_DATA)


async def test_old_three_field_parser_reads_stamped_message() -> None:
    """new pygato → old SDK: an SDK that predates field 4 still reads the message.

    Protobuf files the unknown field aside and leaves the original three intact,
    so an un-upgraded brain keeps working — it simply never sees a stamp.
    """
    env = pb.Envelope()
    env.ParseFromString(
        await CortexFrameSerializer().serialize(
            VqlRTVIClientMessageFrame(interaction_id=7, msg_id="m-1", type=MSG_TYPE, data=MSG_DATA)
        )
    )

    old = _old_three_field_message_class()()
    old.ParseFromString(env.rtvi_client_message.SerializeToString())

    assert (old.msg_id, old.type, json.loads(old.data)) == ("m-1", MSG_TYPE, MSG_DATA)


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


# ─── End to end, through the real stack ──────────────────────────────────────


class _Recorder:
    """A DirectAgent hosting a Brain that records client messages."""

    def __init__(self) -> None:
        self.seen: list[tuple[str, dict, int]] = []
        self.got = asyncio.Event()


async def _run_client_message(payload: bytes, *, respond: bool) -> tuple[_Recorder, list]:
    """Deliver one already-encoded client-message envelope to a live Brain.

    Returns the recorder plus every frame the Brain emitted back.
    """
    from voqalize.sdk import Brain, DirectAgent, brain_factory

    rec = _Recorder()

    class Recording(Brain):
        async def on_interaction(self, interaction) -> None:  # pragma: no cover - unused
            pass

        async def on_client_message(self, session, message) -> None:
            rec.seen.append((message.type, message.data, message.interaction_id))
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
    try:
        await wire.send(
            FrameDirection.DOWNSTREAM,
            await ser.serialize(VqlStartFrame(session_id=session_id, agent_id="compat")),
        )
        await wire.send(FrameDirection.DOWNSTREAM, payload)
        await asyncio.wait_for(rec.got.wait(), timeout=3.0)

        # Drain whatever the brain emitted; the socket goes quiet once it is done.
        async def _drain() -> None:
            while True:
                _direction, data = await wire.recv()
                msg = await ser.deserialize_message(data)
                if msg.frame is not None:
                    emitted.append(msg.frame)

        with __import__("contextlib").suppress(TimeoutError):
            await asyncio.wait_for(_drain(), timeout=0.6)
    finally:
        await wire.close()
        await agent.aclose()
    return rec, emitted


async def test_stamped_message_reaches_on_client_message() -> None:
    """new pygato → new SDK, full stack: the seam fires carrying the stamp."""
    payload = await CortexFrameSerializer().serialize(
        VqlRTVIClientMessageFrame(interaction_id=9, msg_id="m-7", type=MSG_TYPE, data=MSG_DATA)
    )

    rec, _ = await _run_client_message(payload, respond=False)

    assert rec.seen == [(MSG_TYPE, MSG_DATA, 9)]


async def test_unstamped_message_reaches_on_client_message() -> None:
    """old pygato → new SDK, full stack: the seam still fires, marked unstamped.

    This is the regression the additive design exists to prevent — a renumbered
    frame would have been dropped silently and this seam would never run.
    """
    payload = _legacy_envelope_bytes(msg_id="m-7", msg_type=MSG_TYPE, data=MSG_DATA)

    rec, _ = await _run_client_message(payload, respond=False)

    assert rec.seen == [(MSG_TYPE, MSG_DATA, 0)]


async def test_unstamped_response_degrades_to_an_agent_initiated_turn() -> None:
    """A Brain may still respond to an unstamped message; it just cannot spend
    the id, so the reply rides the agent-initiated sentinel exactly as it did
    before the stamp existed — and no ``VqlInteractionCompleted`` is invented for
    an interaction the old pygato never opened.
    """
    from voqalize.sdk.wire import VqlInteractionCompletedFrame

    payload = _legacy_envelope_bytes(msg_id="m-7", msg_type=MSG_TYPE, data=MSG_DATA)

    rec, emitted = await _run_client_message(payload, respond=True)

    assert rec.seen == [(MSG_TYPE, MSG_DATA, 0)]
    starts = [f for f in emitted if isinstance(f, VqlLLMFullResponseStartFrame)]
    assert starts, "the brain's reply must still go out"
    assert all(f.interaction_id == 0 for f in starts), "unstamped speech is agent-initiated"
    assert not [f for f in emitted if isinstance(f, VqlInteractionCompletedFrame)], (
        "nothing is waiting on a completion for an interaction that was never opened"
    )
