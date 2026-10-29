"""The name a model wrote, matched against what the page offers."""

from __future__ import annotations

from voqalize.sdk.stage import fold, match_label
from voqalize.sdk.stage.labels import tokens


def test_fold_strips_latin_accents_and_keeps_other_marks() -> None:
    assert fold("EL CHALTÉN") == "el chalten"
    assert fold("Ñuñoa\u2019s") == "nunoa's"
    # A Devanagari vowel sign is part of the word, not an accent.
    assert fold("हिंदी") == "हिंदी"
    # NFKC: full-width Latin is Latin.
    assert fold("\uff32\uff2f\uff2f\uff2d\uff33") == "rooms"


def test_tokens_keep_combining_marks_inside_words() -> None:
    assert tokens("यह हमारा, कमरा।") == ["यह", "हमारा", "कमरा"]
    assert tokens("Está en la sección Música, ¿sí?") == [
        "esta",
        "en",
        "la",
        "seccion",
        "musica",
        "si",
    ]


def test_exact_ignores_case_accents_and_punctuation() -> None:
    assert match_label("el chalten", ["Rooms", "EL CHALTÉN"]) == "EL CHALTÉN"
    assert match_label("Rooms!", ["rooms", "Room service"]) == "rooms"


def test_a_unique_prefix() -> None:
    assert match_label("Pricing", ["Pricing plans", "FAQ"]) == "Pricing plans"


def test_an_ambiguous_prefix_is_none() -> None:
    assert match_label("Suite", ["Suite Deluxe", "Suite Standard"]) is None


def test_best_token_overlap() -> None:
    options = ["Deluxe Room with View", "Garden Suite", "Family Room"]
    assert match_label("the deluxe room view", options) == "Deluxe Room with View"
    assert match_label("rooftop bar", options) is None


def test_two_options_that_fold_alike_are_ambiguous() -> None:
    assert match_label("rooms", ["Rooms", "ROOMS"]) is None
    assert match_label("rooms", ["Rooms", "Rooms"]) == "Rooms"


def test_empty_want_is_none() -> None:
    assert match_label("  ...", ["Rooms"]) is None
