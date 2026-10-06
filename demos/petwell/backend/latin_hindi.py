# Copied from demos/kiosk/backend (kiosk-screen-leads): demos are self-contained.
"""Hindi, spoken to a recognizer listening for English.

The English recognizer cannot write Devanagari, so a customer who answers in
Hindi arrives as Hindi in English letters: "Main student hoon", "mera naam
Abhishek hai". The model reads that without trouble — and that is the problem:
on a local call it understood "main student hoon", tapped the answer, said "Got
it" in English and never switched, so the customer's next sentence was mangled
again by a recognizer that does not know Hindi.

So this is checked in Python, before the model runs, the same way
:mod:`.script_english` checks the other direction, and just as narrowly. It
counts Hindi **grammar** words — hai, hoon, mera, mujhe, kya, nahi, karta —
because nouns prove nothing: "student", "salary" and "card" are the same word in
both languages. "main" and "mai" count only beside another Hindi word, since
"the main thing" is English.

A turn is Hindi when at least two of its words are on the list and they make up
at least a third of it. Anything less — a single "theek hai" in an English
sentence, or speech the recognizer garbled past recognition — is left to the
model, whose prompt covers it.
"""

from __future__ import annotations

import re

__all__ = ["reads_as_latin_hindi"]

#: Hindi grammar words as an English recognizer spells them, variants beside
#: each other. Deliberately no English homographs: not "to", "me", "se", "par".
_HINDI: frozenset[str] = frozenset(
    [
        # to be
        "hai", "hain", "hoon", "hun", "hu", "tha", "thi",
        # me, you, mine
        "mera", "meri", "mere", "mujhe", "mujhko", "hum", "humein", "aap", "aapka",
        "aapki", "aapko", "tum", "tumhara",
        # asking, refusing, agreeing
        "kya", "kyaa", "kyun", "kaise", "kitna", "kitne", "kitni", "nahi", "nahin",
        "haan", "ji", "theek", "thik",
        # doing, wanting
        "karta", "karti", "karte", "karna", "karo", "kariye", "chahiye", "chahta",
        "chahti", "sakta", "sakti", "sakte", "raha", "rahi", "rahe", "bolo", "boliye",
        # in, of, and
        "mein", "ka", "ki", "ke", "ko", "aur", "bhi", "abhi", "wala", "wali", "baat",
        # the words a profile answer is made of
        "naam", "naukri", "padhai", "kaam", "kharcha", "mahina", "mahine",
    ]
)  # fmt: skip
#: English words that are also Hindi ones, counted only beside a word above.
_WEAK: frozenset[str] = frozenset(["main", "mai"])

_TOKEN = re.compile(r"[A-Za-z]+")


def reads_as_latin_hindi(text: str) -> bool:
    """Whether a turn the English recognizer wrote is really Hindi."""
    tokens = [t.lower() for t in _TOKEN.findall(text)]
    if not tokens:
        return False
    strong = sum(1 for t in tokens if t in _HINDI and t not in _WEAK)
    if strong == 0:
        return False
    hits = strong + sum(1 for t in tokens if t in _WEAK)
    return hits >= 2 and hits * 3 >= len(tokens)
