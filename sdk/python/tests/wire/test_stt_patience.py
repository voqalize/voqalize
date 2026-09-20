"""``SttConfig.patience`` — the turn-end pace, refused here when it is off scale.

Held at the call site for the same reason as the pairing rule next door: the
brain wrote a number, and a round trip later is a turn later. Unlike the pairing
rule, what makes this one worth refusing locally is that the failure is *silent
in the other direction* — the runtime's own control frame carries a bounded
field, so an out-of-range value does not come back as a rejection at all. It is
dropped, and the request that carried it is never answered.

What patience is worth in milliseconds is deliberately not knowable here. The
scale is the contract; the speech tier owns the mapping and re-tunes it without
a wire release.
"""

from __future__ import annotations

import pytest

from voqalize.sdk.wire import Config, ConfigError, Language, SttConfig, TtsConfig
from voqalize.sdk.wire.frames import PATIENCE_MAX, PATIENCE_MIN


def test_the_endpoints_are_both_legal() -> None:
    assert SttConfig(patience=PATIENCE_MIN).patience == PATIENCE_MIN
    assert SttConfig(patience=PATIENCE_MAX).patience == PATIENCE_MAX


def test_unset_is_not_zero() -> None:
    """Unset means *take the deployment's calibration* and zero means *answer as
    fast as you can* — the two ends of the range this field has, not one value
    written two ways."""
    assert SttConfig().patience is None
    assert SttConfig(patience=0).patience == 0


@pytest.mark.parametrize("patience", [-1, PATIENCE_MAX + 1, 100, 500])
def test_off_scale_is_refused_where_it_is_written(patience: int) -> None:
    with pytest.raises(ConfigError, match=r"stt\.patience is"):
        SttConfig(patience=patience)


def test_the_message_says_it_is_a_scale_and_not_a_duration() -> None:
    """The error a brain author will actually hit is someone typing the number of
    milliseconds they had in mind, so it has to answer that mistake by name."""
    with pytest.raises(ConfigError) as ei:
        SttConfig(patience=500)
    assert "scale, not a duration" in str(ei.value)


def test_patience_is_not_a_language_and_the_pairing_rule_ignores_it() -> None:
    """A brain slowing the recognizer down for one caller states nothing about
    language, so the two-legged guard must stay silent."""
    config = Config(stt=SttConfig(patience=9))
    assert config.stt is not None and config.stt.patience == 9
    assert config.tts is None


def test_patience_rides_alongside_a_stated_language_pair() -> None:
    config = Config(
        stt=SttConfig(language=Language.TA, patience=9),
        tts=TtsConfig(language=Language.TA),
    )
    assert config.stt is not None and config.stt.patience == 9
