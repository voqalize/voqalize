"""A Spanish call stays in Spanish until the visitor plainly speaks English.

Speech recognition hears a short Chilean reply or a place name as English —
"See" for "sí", "And lower net here" for "Lo Barnechea" — and a brain that
followed what it heard moved both legs to English mid-call. The agent answered
in English, and the English recognizer then garbled the Spanish that came next:
a demo video on unosalud.cl had to be re-recorded for it (prod,
2026-10-27). So a Spanish call moves to English only when one turn holds two
full English sentences, or when the visitor asks for English; until then a reply
the model writes in English does not move the voice either. The page's toggle
and a brain's ``set_language`` tool are untouched: those are the visitor asking.

The rule is one way on purpose. A call that opens in English (an English site)
still follows a visitor who speaks Spanish, as before.
"""

from __future__ import annotations

import re
from typing import Protocol

#: Full English sentences one turn must hold before a Spanish call moves to English.
ENGLISH_SENTENCES = 2

_SENTENCE = re.compile(r"(?<=[.?!])\s+")
_WORD = re.compile(r"[^\W\d_]+")
_SENTENCE_WORDS = 3
_ASKS_ENGLISH = re.compile(r"\b(?:ingl[eé]s|english)\b", re.IGNORECASE)

#: The context line for a turn that reads as English in a Spanish call.
HELD_NOTE = (
    "[The words heard look English, but the visitor is speaking Spanish: speech "
    "recognition often hears a short Spanish reply or a Chilean name as English. "
    "Answer in Spanish.]"
)


class LanguageOf[L: str](Protocol):
    """A demo's own ``language_of``: the language ``text`` is plainly in, or ``None``."""

    def __call__(self, text: str, *, sure: bool = True) -> L | None: ...


def english_sentences(text: str, language_of: LanguageOf[str]) -> int:
    """How many of ``text``'s sentences are full English ones: three words or
    more, reading as English on their own. A turn of one such sentence is what
    a misheard Spanish reply looks like ("Yes, I hear you clearly.")."""
    return sum(
        len(_WORD.findall(s)) >= _SENTENCE_WORDS and language_of(s, sure=False) == "en"
        for s in _SENTENCE.split(text)
    )


def asks_for_english(text: str) -> bool:
    """Whether ``text`` names English at all, so a reply in English may follow."""
    return bool(_ASKS_ENGLISH.search(text))


def plainly_english(text: str, language_of: LanguageOf[str]) -> bool:
    """Whether ``text`` is enough English to move a Spanish call to English:
    plainly English as a whole, in :data:`ENGLISH_SENTENCES` full sentences."""
    return language_of(text) == "en" and english_sentences(text, language_of) >= ENGLISH_SENTENCES


def heard_language[L: str](text: str, spoken: str, language_of: LanguageOf[L]) -> L | None:
    """The language the call should move to for what the visitor said, or ``None``.

    ``language_of(text)`` as before, except that a Spanish call does not move to
    English on less than :data:`ENGLISH_SENTENCES` full English sentences."""
    heard = language_of(text)
    if spoken == "es" and heard == "en" and not plainly_english(text, language_of):
        return None
    return heard


def holds_spanish(text: str, spoken: str, language_of: LanguageOf[str]) -> bool:
    """Whether this turn reads as English in a Spanish call and is held in
    Spanish, so the model should be told (:data:`HELD_NOTE`)."""
    if spoken != "es" or plainly_english(text, language_of) or asks_for_english(text):
        return False
    return language_of(text, sure=False) == "en"


def may_write_english(text: str, spoken: str, language_of: LanguageOf[str]) -> bool:
    """Whether a reply written in English may move the call to English after
    the visitor said ``text``: always outside Spanish, else only when they spoke
    plain English or asked for it."""
    return spoken != "es" or plainly_english(text, language_of) or asks_for_english(text)


__all__ = [
    "ENGLISH_SENTENCES",
    "HELD_NOTE",
    "LanguageOf",
    "asks_for_english",
    "english_sentences",
    "heard_language",
    "holds_spanish",
    "may_write_english",
    "plainly_english",
]
