"""Credentials never reach the model (FEEDBACK X9).

The visitor types the mobile number they sign in with and the one-time code
themselves; Meera never asks for, fills, reads back or hears them. A visitor may
still say them aloud. :func:`withhold` takes them out of what the patient said
before it goes into the model's context, and names what it took, so the brain
can leave a note ("they said a code aloud; ask them to type it") without the
digits themselves.

What counts, in a heard sentence:

- a **mobile number**: a run of digits (in figures, or as spoken digit words in
  English or Hindi, in groups or not) that makes ten digits, or twelve starting
  91, or eleven starting 0. Always withheld, whatever the call is doing.
- a **code**: a run of four to six digits, when the call is waiting for a code
  (``expecting_code``) or the sentence says code / OTP, and nothing in it
  sounds like money (₹, rupees, hazaar, lakh, "k"), so "under 5000 rupees" is
  left alone.

The model is told the number or code was not kept, so it cannot quote it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Kind = Literal["phone", "code"]

#: One digit said as a word: English, roman Hindi and Devanagari.
_DIGIT_WORDS: dict[str, str] = {
    "zero": "0",
    "oh": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "shunya": "0",
    "ek": "1",
    "teen": "3",
    "chaar": "4",
    "char": "4",
    "paanch": "5",
    "panch": "5",
    "chhe": "6",
    "chhah": "6",
    "saat": "7",
    "aath": "8",
    "nau": "9",
    "शून्य": "0",
    "एक": "1",
    "दो": "2",
    "तीन": "3",
    "चार": "4",
    "पांच": "5",
    "पाँच": "5",
    "छह": "6",
    "छः": "6",
    "सात": "7",
    "आठ": "8",
    "नौ": "9",
}
#: "do" (two) is also an everyday Hindi/English word; it counts only inside a
#: run that already has other digits.
_WEAK = {"do": "2"}

_TOKEN = re.compile(r"\+?[0-9\u0966-\u096f]+|[-.,+]|[^\s0-9\u0966-\u096f.,+-]+")
_SEPARATORS = {"-", ".", ",", "+"}
_MONEY = re.compile(
    r"₹|\brs\.?\b|\brupee|\brupay|\bhazaa?r|\blakh|\blac\b|\bcrore|\b\d+\s?k\b|रुपय|रुपए|हज़ार|हजार|लाख|करोड़",
    re.IGNORECASE,
)
_CODE_WORDS = re.compile(r"\b(code|otp|pin)\b|कोड|ओटीपी", re.IGNORECASE)
_DEVANAGARI_DIGITS = str.maketrans({chr(0x0966 + i): str(i) for i in range(10)})

PHONE_MARK = "[a mobile number, not kept]"
CODE_MARK = "[a sign-in code, not kept]"


@dataclass(frozen=True)
class Withheld:
    """What the model may read of a heard sentence, and what was taken out."""

    text: str
    kinds: tuple[Kind, ...] = ()


def _digits_of(token: str) -> str | None:
    t = token.casefold().strip("?!:;\"'()।")
    if not t:
        return None
    if t[0] == "+":
        t = t[1:]
    if t.translate(_DEVANAGARI_DIGITS).isdigit():
        return t.translate(_DEVANAGARI_DIGITS)
    if t in _DIGIT_WORDS:
        return _DIGIT_WORDS[t]
    return None


def _is_phone(digits: str) -> bool:
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return len(digits) == 10 and digits[0] in "6789"


def withhold(text: str, *, expecting_code: bool = False) -> Withheld:
    """``text`` with any mobile number, and any code where one is expected,
    replaced by a mark that names it."""
    spans: list[tuple[int, int, str]] = []  # start, end, digits
    run: list[tuple[int, int, str]] = []

    def close() -> None:
        if run:
            digits = "".join(d for _, _, d in run)
            # A run of digit words alone ("one", "do") is not a number.
            if len(digits) >= 4:
                spans.append((run[0][0], run[-1][1], digits))
            run.clear()

    for m in _TOKEN.finditer(text):
        token = m.group(0)
        digits = _digits_of(token)
        if digits is None and run and token.casefold() in _WEAK:
            digits = _WEAK[token.casefold()]
        if digits is not None:
            run.append((m.start(), m.end(), digits))
        elif token in _SEPARATORS and run:
            continue
        else:
            close()
    close()

    money = bool(_MONEY.search(text))
    wants_code = expecting_code or bool(_CODE_WORDS.search(text))
    out = text
    kinds: list[Kind] = []
    for start, end, digits in reversed(spans):
        if _is_phone(digits):
            mark, kind = PHONE_MARK, "phone"
        elif 4 <= len(digits) <= 6 and wants_code and not money:
            mark, kind = CODE_MARK, "code"
        else:
            continue
        out = out[:start] + mark + out[end:]
        kinds.append(kind)
    return Withheld(out, tuple(dict.fromkeys(reversed(kinds))))
