"""A short acknowledgement of Trisha's own, said the moment the shopper stops.

The model's first words take about 1.4 s to arrive and then a sentence's worth
of synthesis to be heard. A person answering a question nods first — "Sure.",
"Right.", "अच्छा।" — and the nod is what tells you they heard. This is that nod:
chosen by the brain from a light reading of what the shopper said, spoken as a
unit of its own before the model is asked, so it is heard while the model is
still thinking. The model is told it has been said and opens with the answer;
the prompt keeps its own fillers to the middle of a reply.

The reading is a word list, not a model: a request ("show me", "दिखाओ") gets a
yes, a question gets a thinking nod, a correction gets an "I see". A message it
cannot read gets nothing — a transcript the English recognizer made of Hindi
("Apindimene bolti?") would otherwise be nodded at in the wrong voice before
the model answers it in Hindi. Nor are thanks, goodbyes, greetings or the
shopper's own backchannels answered with one.

Not every turn: a nod on every reply is a tic. The line is picked at random,
never the one said last, and the rate is :data:`RATE`.

The English lines are all in gayatri's phrase cache on speech.dev, so each is
heard about one network round trip after the turn ends. "Hmm." and every Hindi
line are not, and cost a synthesis of ~300 ms — still well ahead of the model.
Like :class:`~voqalize_demos.FallbackLine`'s line, it never enters the model's
context: it is the brain's, not the model's.
"""

from __future__ import annotations

import random
import re
from collections.abc import Mapping
from typing import Literal

from voqalize.sdk.wire import Language

Kind = Literal["request", "question", "correction", "statement"]

#: The share of readable turns that get a nod. The rest open with the model.
RATE = 0.75

LINES: Mapping[Language, Mapping[Kind, tuple[str, ...]]] = {
    Language.EN: {
        "request": ("Sure.", "Okay.", "Of course.", "Certainly."),
        "question": ("Right.", "I see.", "Hmm."),
        "correction": ("I see.", "Understood.", "Right."),
        "statement": ("Okay.", "Got it.", "Right."),
    },
    Language.HI: {
        "request": ("जी।", "ज़रूर।", "ठीक है।", "अच्छा।"),
        "question": ("अच्छा।", "हम्म।", "जी।"),
        "correction": ("अच्छा।", "समझ गई।", "जी।"),
        "statement": ("जी।", "अच्छा।", "ठीक है।"),
    },
}

#: A nod speaks for the turn, so the runtime's own "taking longer" line — armed
#: until the turn's first words — never fires after one. These are the floor in
#: its place: a holding line once the model has been quiet :data:`HOLD_AFTER_S`
#: past the nod, and an apology once it has been quiet :data:`SORRY_AFTER_S`.
HOLD_AFTER_S = 4.0
SORRY_AFTER_S = 12.0
HOLD: Mapping[Language, tuple[str, ...]] = {
    Language.EN: ("One moment.", "Just a moment."),
    Language.HI: ("एक पल।", "बस एक पल।"),
}
SORRY: Mapping[Language, str] = {
    Language.EN: "Sorry, that's taking a little longer.",
    Language.HI: "माफ़ कीजिए, थोड़ा समय लग रहा है।",
}

#: Words, in either script; the danda (।) ends a sentence and is not a letter.
_WORDS = re.compile("[\\w\u0900-\u0963\u0966-\u097f']+")

#: Nothing to nod at: the shopper's own backchannel, thanks, goodbye, hello.
_SKIP = frozenset(
    [
        "ok",
        "okay",
        "yes",
        "yeah",
        "yep",
        "no",
        "nope",
        "hmm",
        "hm",
        "mm",
        "uh",
        "um",
        "thanks",
        "thank",
        "bye",
        "goodbye",
        "hi",
        "hello",
        "hey",
        "haan",
        "han",
        "haa",
        "ji",
        "achha",
        "acha",
        "theek",
        "thik",
        "shukriya",
        "dhanyavaad",
        "namaste",
        "हाँ",
        "हां",
        "जी",
        "अच्छा",
        "ठीक",
        "धन्यवाद",
        "शुक्रिया",
        "नमस्ते",
        "हम्म",
    ]
)
_THANKS_OR_BYE = frozenset(
    ["thanks", "thank", "bye", "goodbye", "shukriya", "dhanyavaad", "धन्यवाद", "शुक्रिया", "अलविदा"]
)

_CORRECTION = frozenset(
    [
        "not",
        "wrong",
        "didn't",
        "don't",
        "isn't",
        "no",
        "actually",
        "instead",
        "rather",
        "nahi",
        "nahin",
        "galat",
        "नहीं",
        "गलत",
        "ग़लत",
        "बल्कि",
    ]
)
_QUESTION = frozenset(
    [
        "what",
        "which",
        "why",
        "how",
        "who",
        "where",
        "when",
        "whats",
        "what's",
        "is",
        "are",
        "does",
        "do",
        "can",
        "could",
        "will",
        "would",
        "should",
        "kya",
        "kaun",
        "kaise",
        "kaisa",
        "kitna",
        "kitne",
        "kitni",
        "kyun",
        "kyon",
        "kahan",
        "क्या",
        "कौन",
        "कौनसा",
        "कैसे",
        "कैसा",
        "कितना",
        "कितने",
        "कितनी",
        "क्यों",
        "कहाँ",
    ]
)
_REQUEST = frozenset(
    [
        "show",
        "find",
        "open",
        "want",
        "need",
        "looking",
        "look",
        "give",
        "take",
        "compare",
        "switch",
        "change",
        "get",
        "send",
        "please",
        "dikhao",
        "dikhaiye",
        "dikha",
        "chahiye",
        "kholo",
        "batao",
        "दिखाओ",
        "दिखाइए",
        "दिखा",
        "चाहिए",
        "खोलो",
        "खोलिए",
        "बताओ",
        "बताइए",
    ]
)


def classify(text: str) -> Kind | None:
    """What the shopper's message asks of her, or ``None`` if it asks for no nod."""
    words = [w.lower().removesuffix("'s") for w in _WORDS.findall(text)]
    if not words or all(w in _SKIP for w in words) or _THANKS_OR_BYE & set(words):
        return None
    said = set(words)
    if words[0] in {"no", "nahi", "nahin", "नहीं"} or said & {"wrong", "galat", "गलत", "ग़लत"}:
        return "correction"
    if said & _REQUEST and not (words[0] in _QUESTION and words[0] not in {"can", "could"}):
        return "request"
    if said & _QUESTION or text.rstrip().endswith("?"):
        return "question" if said & (_QUESTION | _REQUEST | _CORRECTION) else None
    if said & _CORRECTION:
        return "correction"
    return "statement" if len(words) >= 3 and _readable(words) else None


def _readable(words: list[str]) -> bool:
    """Enough ordinary words to trust the transcript is English or Hindi as heard."""
    known = _SKIP | _CORRECTION | _QUESTION | _REQUEST | _COMMON
    return sum(w in known for w in words) * 2 >= len(words)


_COMMON = frozenset(
    [
        "i",
        "i'm",
        "im",
        "me",
        "my",
        "a",
        "an",
        "the",
        "it",
        "this",
        "that",
        "these",
        "those",
        "for",
        "to",
        "of",
        "in",
        "on",
        "with",
        "and",
        "or",
        "she",
        "her",
        "he",
        "his",
        "you",
        "your",
        "we",
        "our",
        "gold",
        "ring",
        "rings",
        "earrings",
        "necklace",
        "chain",
        "bangle",
        "diamond",
        "piece",
        "one",
        "like",
        "love",
        "buy",
        "gift",
        "wife",
        "mother",
        "sister",
        "daughter",
        "wedding",
        "birthday",
        "anniversary",
        "office",
        "daily",
        "everyday",
        "mujhe",
        "mera",
        "meri",
        "ke",
        "ki",
        "ka",
        "hai",
        "hain",
        "ye",
        "yeh",
        "woh",
        "wo",
        "aur",
        "मुझे",
        "मेरा",
        "मेरी",
        "के",
        "की",
        "का",
        "है",
        "हैं",
        "ये",
        "यह",
        "वो",
        "और",
    ]
)


class Acknowledger:
    """Picks the nod for a turn. One per brain, so it never repeats itself."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()
        self._last = ""

    def line(self, text: str, spoken: Language) -> str | None:
        """The line to say before the model runs, or ``None`` for none this turn."""
        kind = classify(text)
        lines = LINES.get(spoken, {}).get(kind) if kind else None
        if not lines or self._rng.random() >= RATE:
            return None
        choices = [line for line in lines if line != self._last] or list(lines)
        self._last = self._rng.choice(choices)
        return self._last

    def hold(self, spoken: Language) -> str:
        """A line that keeps the floor while the model is slow, never the last one said."""
        lines = HOLD.get(spoken, HOLD[Language.EN])
        self._last = self._rng.choice([line for line in lines if line != self._last] or list(lines))
        return self._last
