"""Voice and language as strings, beside the deprecated catalog enums.

The string fields sit on new field numbers, so a brain built against the enum
fields is still understood byte for byte, and a brain that names a voice the
catalog never listed reaches the speech tier unchanged. Which field a setting
travels on is decided by what the brain wrote: a catalog member on the enum
field every Voqalize reads, a plain string on the string field.
"""

from __future__ import annotations

import pytest
from google.protobuf import json_format

from voqalize.sdk.wire import (
    Capability,
    Config,
    ConfigError,
    ConfigureFrame,
    ErrorCode,
    ErrorFrame,
    Language,
    ResponseFrame,
    SessionStartFrame,
    SttConfig,
    TtsConfig,
    Voice,
    WireSerializer,
)
from voqalize.sdk.wire import _frames_pb2 as pb

ser = WireSerializer()


def _numbers(message) -> dict[str, int]:
    return {f.name: f.number for f in message.DESCRIPTOR.fields}


def test_the_field_numbers_are_the_contract() -> None:
    # The enum fields keep the names and numbers they shipped with, so an older
    # brain's bytes and an older document's JSON keys mean what they meant.
    assert _numbers(pb.TtsConfig) == {
        "voice": 1,
        "language": 2,
        "voice_id": 3,
        "language_tag": 4,
    }
    assert _numbers(pb.SttConfig) == {"language": 1, "patience": 2, "language_tag": 3}
    assert _numbers(pb.Response)["code"] == 4
    assert pb.CAPABILITY_STRING_CONFIG == 2
    assert (
        pb.ERROR_CODE_UNSUPPORTED_VOICE,
        pb.ERROR_CODE_UNSUPPORTED_LANGUAGE,
        pb.ERROR_CODE_INVALID_REQUEST,
    ) == (6, 7, 8)


def test_the_enum_fields_are_marked_deprecated() -> None:
    for message, name in (
        (pb.TtsConfig, "voice"),
        (pb.TtsConfig, "language"),
        (pb.SttConfig, "language"),
    ):
        assert message.DESCRIPTOR.fields_by_name[name].GetOptions().deprecated, name


def test_json_written_before_the_strings_still_names_the_enums() -> None:
    # A stored configuration in proto3 JSON keeps its meaning: the existing
    # keys are still the enum fields, and the strings have keys of their own.
    m = json_format.Parse(
        '{"tts": {"voice": "VOICE_OMNIVOICE_GAURI", "language": "LANGUAGE_HI"},'
        ' "stt": {"language": "LANGUAGE_HI"}}',
        pb.Config(),
    )
    assert m.tts.voice == pb.VOICE_OMNIVOICE_GAURI
    assert m.tts.language == pb.LANGUAGE_HI
    assert m.stt.language == pb.LANGUAGE_HI
    assert not m.tts.HasField("voice_id")
    m = json_format.Parse(
        '{"tts": {"voice_id": "gemini/kore", "language_tag": "en-IN"},'
        ' "stt": {"language_tag": "ta"}}',
        pb.Config(),
    )
    assert (m.tts.voice_id, m.tts.language_tag, m.stt.language_tag) == (
        "gemini/kore",
        "en-IN",
        "ta",
    )


async def _configure(config: Config) -> pb.Envelope:
    env = pb.Envelope()
    env.ParseFromString(await ser.serialize(ConfigureFrame(request_id=1, config=config)))
    return env


async def test_strings_travel_on_the_string_fields() -> None:
    env = await _configure(
        Config(
            tts=TtsConfig(voice="gemini/kore", language="en-IN"),
            stt=SttConfig(language="ta"),
        )
    )
    tts, stt = env.request.configure.tts, env.request.configure.stt
    assert (tts.voice_id, tts.language_tag, stt.language_tag) == ("gemini/kore", "en-IN", "ta")
    assert not tts.HasField("voice")
    assert not tts.HasField("language")
    assert not stt.HasField("language")


async def test_catalog_members_travel_on_the_enum_fields() -> None:
    # What a brain written before the strings sends, unchanged — so a Voqalize
    # that predates them is served exactly as before.
    env = await _configure(
        Config(
            tts=TtsConfig(voice=Voice.OMNIVOICE_GAURI, language=Language.HI),
            stt=SttConfig(language=Language.HI),
        )
    )
    tts, stt = env.request.configure.tts, env.request.configure.stt
    assert tts.voice == pb.VOICE_OMNIVOICE_GAURI
    assert tts.language == pb.LANGUAGE_HI
    assert stt.language == pb.LANGUAGE_HI
    assert not tts.HasField("voice_id")
    assert not tts.HasField("language_tag")
    assert not stt.HasField("language_tag")


@pytest.mark.parametrize(
    "config",
    [
        Config(tts=TtsConfig(voice="gemini/kore", language="en-IN"), stt=SttConfig(language="ta")),
        Config(tts=TtsConfig(voice=Voice.KOKORO_AVA, language="en"), stt=SttConfig(language="en")),
        Config(tts=TtsConfig(voice="omnivoice/gauri")),
    ],
)
async def test_a_string_config_round_trips_as_written(config: Config) -> None:
    out = await ser.deserialize(await ser.serialize(ConfigureFrame(request_id=1, config=config)))
    assert isinstance(out, ConfigureFrame)
    assert out.config == config
    # A string stays a plain string, a member stays a member.
    assert type(out.config.tts.voice) is type(config.tts.voice)  # type: ignore[union-attr]


async def test_bytes_from_an_enum_only_brain_still_decode() -> None:
    # Only the enum fields set, as an SDK that predates the strings writes them.
    env = pb.Envelope()
    env.request.request_id = 1
    env.request.configure.tts.voice = pb.VOICE_OMNIVOICE_GAURAV
    env.request.configure.tts.language = pb.LANGUAGE_TA
    env.request.configure.stt.language = pb.LANGUAGE_TA
    out = await ser.deserialize(env.SerializeToString())
    assert isinstance(out, ConfigureFrame)
    assert out.config.tts == TtsConfig(voice=Voice.OMNIVOICE_GAURAV, language=Language.TA)
    assert out.config.stt == SttConfig(language=Language.TA)


@pytest.mark.parametrize(
    "build",
    [
        lambda: TtsConfig(voice=""),
        lambda: TtsConfig(language="  "),
        lambda: SttConfig(language=""),
    ],
)
def test_an_empty_name_is_refused_where_it_is_written(build) -> None:
    with pytest.raises(ConfigError, match="empty string"):
        build()


def test_the_pairing_rule_holds_for_strings() -> None:
    with pytest.raises(ConfigError, match=r"tts\.language but not stt\.language"):
        Config(tts=TtsConfig(language="hi"))
    # Both legs stated, differing, is a real configuration.
    Config(tts=TtsConfig(language="hi"), stt=SttConfig(language="or"))


async def test_the_string_capability_decodes() -> None:
    env = pb.Envelope()
    env.session_start.capabilities.extend(
        [pb.CAPABILITY_SPEECH_CANCEL, pb.CAPABILITY_STRING_CONFIG]
    )
    out = await ser.deserialize(env.SerializeToString())
    assert isinstance(out, SessionStartFrame)
    assert out.capabilities == {Capability.SPEECH_CANCEL, Capability.STRING_CONFIG}


@pytest.mark.parametrize(
    "code",
    [ErrorCode.UNSUPPORTED_VOICE, ErrorCode.UNSUPPORTED_LANGUAGE, ErrorCode.INVALID_REQUEST],
)
async def test_a_rejection_carries_its_code(code: ErrorCode) -> None:
    frame = ResponseFrame(request_id=7, accepted=False, detail="no such voice", code=code)
    assert await ser.deserialize(await ser.serialize(frame)) == frame


async def test_a_response_without_a_code_reads_as_none() -> None:
    # What a Voqalize that predates `Response.code` sends.
    frame = ResponseFrame(request_id=7, accepted=False, detail="refused")
    out = await ser.deserialize(await ser.serialize(frame))
    assert isinstance(out, ResponseFrame)
    assert out.code is None


async def test_an_unknown_response_code_reads_as_unknown() -> None:
    env = pb.Envelope()
    env.response.request_id = 7
    env.response.status = pb.STATUS_REJECTED
    # A number this build has no name for, as a newer Voqalize sends.
    env.response.code = 99  # type: ignore[assignment]
    out = await ser.deserialize(env.SerializeToString())
    assert isinstance(out, ResponseFrame)
    assert out.code is ErrorCode.UNKNOWN


@pytest.mark.parametrize("number", [0, 99])
async def test_an_unknown_error_code_reads_as_unknown_not_internal(number: int) -> None:
    env = pb.Envelope()
    env.error.code = number  # type: ignore[assignment]
    env.error.message = "something new"
    out = await ser.deserialize(env.SerializeToString())
    assert isinstance(out, ErrorFrame)
    assert out.code is ErrorCode.UNKNOWN


@pytest.mark.parametrize(
    "code",
    [ErrorCode.UNSUPPORTED_VOICE, ErrorCode.UNSUPPORTED_LANGUAGE, ErrorCode.INVALID_REQUEST],
)
async def test_a_caller_error_round_trips_on_the_error_frame(code: ErrorCode) -> None:
    frame = ErrorFrame(code=code, message="voice not found", fatal=False)
    assert await ser.deserialize(await ser.serialize(frame)) == frame
