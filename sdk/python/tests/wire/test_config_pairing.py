"""``Config`` refuses a half-stated language at the call site.

A language has two legs — the recognizer and the recorded speaker — and moving
one without the other is the failure with no symptom: the words stay right and
only the voice is wrong, so the transcript, the logs and every automated score
are identical to a correct call. The one place it is visible is the moment
somebody writes it down, which is why this guard is here and not one round trip
away.

It is the *only* rule enforced locally. Whether the speech tier can actually
speak a given language is its own answer and comes back as a rejected response —
a client-side copy of that roster would be one more thing to keep honest, and it
would be wrong the day a clip is recorded.
"""

from __future__ import annotations

import pytest

from voqalize.sdk.wire import Config, ConfigError, IdleConfig, Language, SttConfig, TtsConfig, Voice


def test_naming_a_language_on_one_leg_only_is_refused() -> None:
    with pytest.raises(ConfigError, match=r"tts\.language but not stt\.language"):
        Config(tts=TtsConfig(language=Language.HI))

    with pytest.raises(ConfigError, match=r"stt\.language but not tts\.language"):
        Config(stt=SttConfig(language=Language.HI))


def test_the_legs_may_differ_as_long_as_both_are_stated() -> None:
    # The guard is statedness, not equality. There are fewer languages that can
    # be spoken than understood, so a call heard in Odia and spoken with the
    # Hindi clip is a real configuration — it just has to be written down.
    config = Config(
        stt=SttConfig(language=Language.OR),
        tts=TtsConfig(language=Language.HI),
    )
    assert config.stt is not None and config.stt.language is Language.OR
    assert config.tts is not None and config.tts.language is Language.HI


def test_changing_only_the_voice_touches_no_language() -> None:
    # Which of two personas reads the text is not a language change, so the rule
    # does not apply and must not fire.
    assert Config(tts=TtsConfig(voice=Voice.OMNIVOICE_GAURAV)).stt is None


def test_a_config_that_names_no_language_at_all_is_fine() -> None:
    assert Config(idle=IdleConfig(timeout_ms=0)).tts is None
    assert Config() == Config()
