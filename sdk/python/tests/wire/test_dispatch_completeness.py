"""CI guard: every Vql frame class must be wired into both encoder + decoder
dispatch tables. Adding a class without wiring it fails this test.
"""

from voqalize.sdk.wire.frames import VQL_FRAME_CLASSES
from voqalize.sdk.wire.serializer import _DECODERS, _ENCODERS


def test_every_vql_class_has_encoder() -> None:
    missing = [c.__name__ for c in VQL_FRAME_CLASSES if c not in _ENCODERS]
    assert not missing, (
        f"Vql frame classes missing from _ENCODERS: {missing}. Wire them in serializer.py."
    )


def test_decoder_table_covers_vql_oneofs() -> None:
    """Every vql_* oneof field declared in the proto must have a decoder."""
    from voqalize.sdk.wire import _frames_pb2 as pb

    env = pb.Envelope()
    vql_fields = {
        f.name for f in env.DESCRIPTOR.oneofs_by_name["body"].fields if f.name.startswith("vql_")
    }
    decoder_vql_keys = {k for k in _DECODERS if k.startswith("vql_")}
    assert vql_fields == decoder_vql_keys, (
        f"Vql oneof fields without decoders: {vql_fields - decoder_vql_keys}; "
        f"decoders without proto fields: {decoder_vql_keys - vql_fields}"
    )
