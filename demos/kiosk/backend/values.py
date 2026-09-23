"""What the customer speaks, and the three ways it is written back.

One value, three renderings, and mixing them up is the demo's loudest failure
mode. ``display_form`` is numerals for the screen, ``masked_form`` is what a
totem standing in a branch shows at rest, and ``spoken_form`` is words for the
voice — a mobile number read as digits, a closed token read as a phrase. Nothing
here is interchangeable with anything else here.

``reads_as_yes`` is the other half: whether the reply to a read-back was a clear
yes. It is Python rather than a model call because "did they agree" decides
whether a PAN gets stored, and because the answer has to be the same one twice.
"""

from __future__ import annotations

import re

from .cards import (
    EMPLOYMENT_SPOKEN,
    EXISTING_CARDS_SPOKEN,
    INCOME_BAND_SPOKEN,
    PROFILE_CHOICES,
    SPEND_SPOKEN,
    CapturedField,
    spoken_characters,
    spoken_digits,
)

__all__ = [
    "allowed_values",
    "display_form",
    "masked_form",
    "normalise",
    "reads_as_yes",
    "spoken_form",
]


# ─── Values the customer speaks ────────────────────────────────────────────────

_MOBILE = re.compile(r"^[6-9]\d{9}$")
_PAN = re.compile(r"^[A-Z]{5}\d{4}[A-Z]$")

#: The four closed vocabularies in one place, keyed by field. The maps in
#: ``cards.py`` are keyed by their own Literal so a missing token is caught
#: there; here they are read by a field name that is only known at runtime.
_SPOKEN_BY_FIELD: dict[str, dict[str, str]] = {
    "employment": {**EMPLOYMENT_SPOKEN},
    "income_band": {**INCOME_BAND_SPOKEN},
    "existing_cards": {**EXISTING_CARDS_SPOKEN},
    "spend_category": {**SPEND_SPOKEN},
}


def normalise(field: CapturedField, value: str) -> str | None:
    """The value as this demo stores it, or ``None`` if it is not one.

    A mobile number arrives with whatever spacing the transcriber chose and a PAN
    in whatever case; a closed answer arrives as one of its own tokens or not at
    all. Everything downstream can then assume the shape.
    """
    if field == "mobile":
        digits = re.sub(r"\D", "", value)
        return digits if _MOBILE.match(digits) else None
    if field == "pan":
        pan = re.sub(r"[^A-Za-z0-9]", "", value).upper()
        return pan if _PAN.match(pan) else None
    token = value.strip().lower()
    return token if token in _SPOKEN_BY_FIELD[field] else None


def display_form(field: CapturedField, value: str) -> str:
    """The value for the screen: numerals and labels, never spoken."""
    if field == "mobile":
        return f"{value[:5]} {value[5:]}"
    if field == "pan":
        return value
    labels = {choice[0]: choice[1] for choice in PROFILE_CHOICES[field]}
    return labels[value]


def masked_form(field: CapturedField, value: str) -> str:
    """The value as a totem in a branch should show it at rest."""
    if field == "mobile":
        return f"XXXXX {value[5:]}"
    if field == "pan":
        return f"{value[:5]}XXXX{value[9]}"
    return display_form(field, value)


def spoken_form(field: CapturedField, value: str) -> str:
    """The value as the voice says it. Digits become words, tokens become
    phrases — nothing is ever interpolated into a sentence raw."""
    if field == "mobile":
        return spoken_digits(value)
    if field == "pan":
        return spoken_characters(value)
    return _SPOKEN_BY_FIELD[field][value]


def allowed_values(field: CapturedField) -> str:
    """What a model that invented a value is told back."""
    if field == "mobile":
        return "ten digits starting with 6, 7, 8 or 9"
    if field == "pan":
        return "five letters, four digits, one letter"
    return ", ".join(choice[0] for choice in PROFILE_CHOICES[field])


# ─── Was that a yes? ───────────────────────────────────────────────────────────
# Both scripts, because the recognizer returns what was said: a Hindi turn comes
# back in Devanagari and a romanised "haan" never appears in it. A set with only
# the Latin half reads every Hindi yes as unclear, which is the one failure this
# whole confirmation step exists to avoid.

_YES = frozenset(
    ["yes", "yeah", "yep", "yup", "ya", "right", "correct", "perfect", "exactly", "ok", "okay",
     "sure", "done", "haan", "han", "ha", "ji", "sahi", "bilkul", "theek", "thik",
     "हाँ", "हां", "हा", "जी", "सही", "बिल्कुल", "ठीक", "सच", "बराबर"]
)  # fmt: skip
_NO = frozenset(
    ["no", "nope", "nah", "nahi", "galat", "wrong", "incorrect", "not", "isn't", "isnt",
     "नहीं", "नही", "ना", "गलत"]
)  # fmt: skip
_HEDGE = frozenset(
    ["maybe", "think", "almost", "roughly", "about", "nearly", "sort", "kind", "guess",
     "probably", "shayad", "lagta", "umm", "um", "hmm", "hm", "wait", "actually", "sorry",
     "शायद", "लगता", "रुको", "रुकिए", "मतलब"]
)  # fmt: skip
_WORDS = re.compile(r"[a-zऀ-ॿ]+")


def reads_as_yes(heard: str) -> bool:
    """Whether that reply was a clear yes, and nothing else.

    Not-yes covers all four ways a confirmation goes wrong: no yes token at all,
    a hedge ("I think so"), a refusal, and a correction the customer embedded in
    the answer, which shows up as digits in a turn that was supposed to be one
    word. A turn too short to carry signal has no token either, so it lands here
    too.
    """
    if any(char.isdigit() for char in heard):
        return False
    tokens = set(_WORDS.findall(heard.lower()))
    if tokens & _NO or tokens & _HEDGE:
        return False
    return bool(tokens & _YES)
