"""A Spanish call stays Spanish until the visitor plainly speaks English.

The turns are what speech recognition actually returned on Spanish calls
(prod, 2026-10-22 to 10-27), read with one Chilean-site brain's own
``language_of``; every Spanish-and-English site brain shares the rule in ``language_hold``."""

from __future__ import annotations

import pytest
from voqalize_demos.discovery import discover

discover()

from voqalize_demos._loaded.cannonhome.brain import language_of  # noqa: E402
from voqalize_demos.language_hold import (  # noqa: E402
    heard_language,
    holds_spanish,
    may_write_english,
)

MISHEARD = [
    "And lower net here.",
    "No, it is.",
    "Yes, I hear you clearly.",
    "See what for.",
    "Recording in progress.",
    "Okay.",
]


@pytest.mark.parametrize("text", MISHEARD)
def test_a_spanish_call_holds_on_misheard_english(text: str) -> None:
    assert heard_language(text, "es", language_of) is None
    assert not may_write_english(text, "es", language_of)


def test_two_full_english_sentences_move_it() -> None:
    text = "I want to see the sheets. Can you show me the price?"
    assert heard_language(text, "es", language_of) == "en"
    assert may_write_english(text, "es", language_of)
    assert not holds_spanish(text, "es", language_of)


def test_one_english_sentence_is_held_and_the_model_told() -> None:
    text = "Can you show me the sheets?"
    assert heard_language(text, "es", language_of) is None
    assert holds_spanish(text, "es", language_of)


def test_asking_for_english_lets_the_reply_move_the_voice() -> None:
    assert may_write_english("¿Puedes hablar en inglés?", "es", language_of)
    assert not holds_spanish("Can you speak English?", "es", language_of)


def test_an_english_call_still_follows_spanish() -> None:
    assert heard_language("Hola, quiero ver las sábanas", "en", language_of) == "es"
    assert heard_language("Can you show me the sheets?", "en", language_of) == "en"
    assert may_write_english("Okay.", "en", language_of)


def test_short_plain_questions_count_as_full_sentences() -> None:
    assert (
        heard_language(
            "How much is shipping? I would like to know more, please.", "es", language_of
        )
        == "en"
    )
    assert heard_language("How much is shipping?", "es", language_of) is None
