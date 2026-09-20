"""The catalog has one definition, and it is the proto.

``Voice`` and ``Language`` exist twice by necessity — once as proto enums the
runtime and the control plane both compile, once as Python enums a brain author
writes. Two spellings of one list is exactly the shape that drifts: a language
added to the speech tier reaches the runtime and never reaches the SDK, and the
symptom is a call that connects and is refused.

So the Python side is checked against the descriptor rather than against a copy
of the list. Regenerate with ``make proto`` and this test says what moved.

Which languages a voice can *speak* is deliberately not here. That is a
capability of the speech tier, which publishes it per voice and moves it when it
adds one; a copy of today's pairings in a wire contract would be one more
spelling to keep honest. The check that the proto's roster still matches the
speech tier's runs against the deployed catalog, not in this suite.
"""

from __future__ import annotations

from voqalize.sdk.wire import Language, Voice
from voqalize.sdk.wire import _frames_pb2 as pb

_ISO_CODE = pb.DESCRIPTOR.extensions_by_name["iso_code"]
_VOICE_ID = pb.DESCRIPTOR.extensions_by_name["voice_id"]


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
    ids = {v.GetOptions().Extensions[_VOICE_ID] for v in _values(pb.Voice)}
    assert ids == {voice.value for voice in Voice}


def test_every_proto_voice_carries_a_voice_id() -> None:
    # Same trap as the languages: a value missing the option decodes as the
    # empty string and slips through the set comparison above exactly once.
    missing = [v.name for v in _values(pb.Voice) if not v.GetOptions().Extensions[_VOICE_ID]]
    assert missing == []


def test_a_voice_id_names_the_engine_that_serves_it() -> None:
    # The prefix is the engine selector — the only one there is — so a voice id
    # without one routes nowhere. This is what makes the id worth carrying on
    # the wire instead of deriving it from the enum name.
    for v in _values(pb.Voice):
        engine, slash, name = v.GetOptions().Extensions[_VOICE_ID].partition("/")
        assert slash == "/", v.name
        assert engine and name, v.name
