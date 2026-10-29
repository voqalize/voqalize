"""Matching the name a model wrote against the names a page offers.

The model writes "el chalten"; the page says "EL CHALTÉN". Both are folded the
same way — NFKC, case folded, Latin accents removed for the comparison only —
and compared as words. Marks that carry meaning in other scripts (a Devanagari
vowel sign, a Japanese voicing mark) are kept: removing them changes the word.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable

__all__ = ["OVERLAP", "fold", "match_label", "tokens"]

#: The least word overlap (Dice coefficient) that names an option on its own.
OVERLAP = 0.6


def _latin_mark(c: str) -> bool:
    return "\u0300" <= c <= "\u036f"


def fold(text: str) -> str:
    """``text`` as it is compared: NFKC, case folded, U+2019 as an apostrophe, and the Latin
    combining accents (U+0300 to U+036F) removed. The same fold the page runs on
    what it hears."""
    text = unicodedata.normalize("NFKC", text).casefold().replace("\u2019", "'")
    text = "".join(c for c in unicodedata.normalize("NFD", text) if not _latin_mark(c))
    return unicodedata.normalize("NFC", text)


def tokens(text: str) -> list[str]:
    """The words of ``text``, folded: runs of letters, marks, digits and '."""
    out: list[str] = []
    word: list[str] = []
    for c in fold(text):
        if c == "'" or unicodedata.category(c)[0] in "LMN":
            word.append(c)
        elif word:
            out.append("".join(word))
            word = []
    if word:
        out.append("".join(word))
    return out


def _dice(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return 2 * len(a & b) / (len(a) + len(b))


def _one(hits: Iterable[str]) -> str | None:
    unique = list(dict.fromkeys(hits))
    return unique[0] if len(unique) == 1 else None


def match_label(want: str, options: Iterable[str]) -> str | None:
    """The option ``want`` names, as the page offers it; ``None`` when it
    names none, or more than one equally well.

    Tried in order: the same words; the one option the words begin; the option
    sharing the most words, when the overlap is at least :data:`OVERLAP` and
    no other option shares as many.
    """
    w = tokens(want)
    if not w:
        return None
    key = " ".join(w)
    keyed = [(" ".join(tokens(o)), o) for o in dict.fromkeys(options)]
    keyed = [(k, o) for k, o in keyed if k]
    exact = [o for k, o in keyed if k == key]
    if exact:
        return _one(exact)
    prefix = [o for k, o in keyed if k.startswith(key)]
    if len(prefix) == 1:
        return prefix[0]
    want_set = set(w)
    scored = [(_dice(want_set, set(k.split())), o) for k, o in keyed]
    best = max((s for s, _ in scored), default=0.0)
    if best < OVERLAP:
        return None
    return _one(o for s, o in scored if s == best)
