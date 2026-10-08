"""CI guard: every frame class must be wired into both encoder + decoder
dispatch tables. Adding a class without wiring it fails this test.
"""

from voqalize.sdk.wire.frames import WIRE_FRAME_CLASSES
from voqalize.sdk.wire.serializer import _DECODERS, _ENCODERS


def test_every_frame_class_has_encoder() -> None:
    missing = [c.__name__ for c in WIRE_FRAME_CLASSES if c not in _ENCODERS]
    assert not missing, (
        f"Frame classes missing from _ENCODERS: {missing}. Wire them in serializer.py."
    )


def test_decoder_table_covers_every_body() -> None:
    """Every oneof body in the proto has a decoder."""
    from voqalize.sdk.wire import _frames_pb2 as pb

    env = pb.Envelope()
    bodies = {f.name for f in env.DESCRIPTOR.oneofs_by_name["body"].fields}
    assert bodies == set(_DECODERS), (
        f"proto bodies without decoders: {bodies - set(_DECODERS)}; "
        f"decoders without proto bodies: {set(_DECODERS) - bodies}"
    )


def test_every_capability_has_a_name() -> None:
    """Every capability the proto declares maps to a ``Capability`` member. One
    left out would be dropped on decode, so a brain would refuse a frame Voqalize
    said it honours."""
    from voqalize.sdk.wire import _frames_pb2 as pb
    from voqalize.sdk.wire.serializer import _CAPABILITY_FROM_PB

    declared = {v.number for v in pb.Capability.DESCRIPTOR.values if v.number != 0}
    assert declared == set(_CAPABILITY_FROM_PB)
