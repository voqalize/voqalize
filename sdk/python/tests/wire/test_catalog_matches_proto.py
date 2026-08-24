"""The catalog has one definition, and it is the proto.

``Voice`` and ``Language`` exist twice by necessity — once as proto enums the
runtime and the control plane both compile, once as Python enums a brain author
writes. Two spellings of one list is exactly the shape that drifts: a language
added to the speech tier reaches the runtime and never reaches the SDK, and the
symptom is a call that connects and is refused.

So the Python side is checked against the descriptor rather than against a copy
of the list. Regenerate with ``make proto`` and this test says what moved.

Which languages can be *spoken* is deliberately not here. Reference clips are a
capability of the speech tier and move when it does; the runtime answers that
question when it is asked, and a copy of today's roster in a wire contract would
be a third spelling to keep honest.
"""

from __future__ import annotations

from voqalize.sdk.wire import Language, Voice
from voqalize.sdk.wire import _frames_pb2 as pb

_ISO_CODE = pb.DESCRIPTOR.extensions_by_name["iso_code"]


def _values(enum):
    """Every value of a proto enum except the zero one, which is 'unspecified'
    and is the absence of a choice rather than a member of the catalog."""
    return [v for v in enum.DESCRIPTOR.values if v.number != 0]


def test_every_proto_language_is_a_python_language() -> None:
    iso = {v.GetOptions().Extensions[_ISO_CODE] for v in _values(pb.Language)}
    assert iso == {lang.value for lang in Language}


def test_every_proto_language_carries_an_iso_code() -> None:
    # The Python value *is* the iso_code option, so a value missing it would
    # decode as the empty string and pass the set comparison above once.
    missing = [v.name for v in _values(pb.Language) if not v.GetOptions().Extensions[_ISO_CODE]]
    assert missing == []


def test_every_proto_voice_is_a_python_voice() -> None:
    # The voice enum has no iso_code twin — the name is derived, so pin the
    # derivation rather than the list: VOICE_OMNIVOICE_GAURI → "omnivoice/gauri".
    derived = {v.name.removeprefix("VOICE_").lower().replace("_", "/") for v in _values(pb.Voice)}
    assert derived == {voice.value for voice in Voice}
