"""A short acknowledgement of the brain's own, said the moment the user stops.

The model's first words take about 1.4 s to arrive and then a sentence's worth
of synthesis to be heard. A person answering a question nods first — "Sure.",
"Let me see.", "जी।" — and the nod is what tells you they heard. This is that nod:
chosen by the brain from a light reading of what the user said, spoken as a unit
of its own before the model is asked, so it is heard while the model is still
thinking. The prompt tells the model it has been said and to open with the
answer.

The reading is a word list, not a model: a request ("show me", "दिखाओ") gets a
yes, a question gets a thinking nod, a correction gets an "I see". A message it
cannot read gets nothing — a transcript the English recognizer made of Hindi
would otherwise be nodded at in the wrong voice before the model answers it in
Hindi. Nor are thanks, goodbyes, greetings or the user's own backchannels
answered with one, nor the questions a demo names as reading wrong after a nod
(``no_nod``).

Not every turn: a nod on every reply is a tic. The line is picked at random,
never the one said last, at a demo's own ``rate``.

A nod speaks for the turn, so the runtime's "taking longer" line — armed until
the turn's first words — never fires after one. :func:`hold_the_floor` is the
floor in its place: a holding line once the model has been quiet ``hold_after_s``
past the nod, and an apology once it has been quiet ``sorry_after_s``.

Like :class:`~voqalize_demos.FallbackLine`'s line, a nod never enters the
model's context: it is the brain's, not the model's.

This began as qween's (``qween/backend/acknowledge.py``, which still carries its
own copy). The word lists read English, Hindi and Kannada; the lines, and a
demo's own vocabulary, are per demo.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
import re
from collections.abc import AsyncGenerator, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Literal, cast

from google.genai import types
from loguru import logger

from voqalize.sdk import Speech, SpeechChunk, SpeechEnd, SpeechStart
from voqalize.sdk.gemini import GeminiBrain, _Unit  # pyright: ignore[reportPrivateUsage]

Kind = Literal["request", "question", "correction", "statement"]

#: Words, in Latin, Devanagari or Kannada script; the danda (।) ends a
#: sentence and is not a letter. Kannada's vowel signs are not ``\\w``, so
#: its block is named whole.
_WORDS = re.compile("[\\wऀ-ॣ०-ॿ\u0c80-\u0cff']+")

#: Nothing to nod at: the user's own backchannel, thanks, goodbye, hello.
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
        "ಹೌದು",
        "ಸರಿ",
        "ಓಕೆ",
        "ಹಾ",
        "ಹಾಂ",
        "ಇಲ್ಲ",
        "ಬೇಡ",
        "ಆಯ್ತು",
        "ಧನ್ಯವಾದ",
        "ಧನ್ಯವಾದಗಳು",
        "ಥ್ಯಾಂಕ್ಸ್",
        "ನಮಸ್ಕಾರ",
        "ಹಲೋ",
    ]
)
_THANKS_OR_BYE = frozenset(
    [
        "thanks",
        "thank",
        "bye",
        "goodbye",
        "shukriya",
        "dhanyavaad",
        "धन्यवाद",
        "शुक्रिया",
        "अलविदा",
        "ಧನ್ಯವಾದ",
        "ಧನ್ಯವಾದಗಳು",
        "ಥ್ಯಾಂಕ್ಸ್",
        "ಬೈ",
    ]
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
        "ಇಲ್ಲ",
        "ಅಲ್ಲ",
        "ತಪ್ಪು",
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
        "ಏನು",
        "ಏನಿದೆ",
        "ಯಾವ",
        "ಯಾವುದು",
        "ಯಾಕೆ",
        "ಏಕೆ",
        "ಹೇಗೆ",
        "ಯಾರು",
        "ಎಲ್ಲಿ",
        "ಎಲ್ಲಿದೆ",
        "ಯಾವಾಗ",
        "ಎಷ್ಟು",
    ]
)
#: A mic check wants "yes, I can hear you" at once, not a nod.
_NO_NOD = frozenset(["hear", "hearing", "audible", "mic", "sunai", "सुनाई"])
_TOO_MUCH = frozenset(
    ["too", "so", "itna", "itni", "itne", "इतना", "इतनी", "इतने", "ज़्यादा", "zyada", "jyada"]
)
_REQUEST = frozenset(
    [
        "show",
        "scroll",
        "zoom",
        "close",
        "select",
        "add",
        "remove",
        "sort",
        "filter",
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
        "tell",
        "explain",
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
        "ತೋರಿಸಿ",
        "ಬೇಕು",
        "ತೆರೆಯಿರಿ",
        "ಹೇಳಿ",
        "ತಿಳಿಸಿ",
        "ಹುಡುಕಿ",
        "ಕರೆದುಕೊಂಡು",
        "ನೋಡಬೇಕು",
    ]
)
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
        "one",
        "like",
        "buy",
        "about",
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
        "ನಾನು",
        "ನನಗೆ",
        "ನನ್ನ",
        "ನಮ್ಮ",
        "ನೀವು",
        "ನಿಮ್ಮ",
        "ಈ",
        "ಆ",
        "ಇದು",
        "ಅದು",
        "ಇದೆ",
        "ಮತ್ತು",
        "ಬಗ್ಗೆ",
    ]
)


def words_of(text: str) -> list[str]:
    return [w.lower().removesuffix("'s") for w in _WORDS.findall(text)]


@dataclass(frozen=True)
class Vocabulary:
    """What a demo's users say: its own ordinary words, so a transcript about its
    domain reads as English or Hindi, and the words after which no nod reads
    right."""

    common: frozenset[str] = frozenset()
    no_nod: frozenset[str] = frozenset()


_NO_VOCABULARY = Vocabulary()


def classify(text: str, vocabulary: Vocabulary = _NO_VOCABULARY) -> Kind | None:
    """What the user's message asks of the brain, or ``None`` for no nod."""
    words = words_of(text)
    if not words or all(w in _SKIP for w in words) or _THANKS_OR_BYE & set(words):
        return None
    said = set(words)
    if said & (_NO_NOD | vocabulary.no_nod) or (
        said & {"why", "kyun", "kyon", "क्यों"} and said & _TOO_MUCH
    ):
        return None
    if words[0] in {"no", "nahi", "nahin", "नहीं", "ಇಲ್ಲ", "ಅಲ್ಲ"} or said & {
        "wrong",
        "galat",
        "गलत",
        "ग़लत",
        "ತಪ್ಪು",
    }:
        return "correction"
    if said & _REQUEST and not (words[0] in _QUESTION and words[0] not in {"can", "could"}):
        return "request"
    if said & _QUESTION or text.rstrip().endswith("?"):
        return "question" if said & (_QUESTION | _REQUEST | _CORRECTION) else None
    if said & _CORRECTION:
        return "correction"
    known = _SKIP | _CORRECTION | _QUESTION | _REQUEST | _COMMON | vocabulary.common
    readable = sum(w in known for w in words) * 2 >= len(words)
    return "statement" if len(words) >= 3 and readable else None


@dataclass
class Acknowledger[L: str]:
    """Picks the nod for a turn. One per brain, so it never repeats itself.

    ``L`` is how the demo names the language its voice speaks: the frozen
    :class:`~voqalize.sdk.wire.Language` for English and the Indic languages,
    or a plain tag (``"es"``) for a language the enum will never have."""

    lines: Mapping[L, Mapping[Kind, tuple[str, ...]]]
    hold_lines: Mapping[L, tuple[str, ...]]
    sorry: Mapping[L, str]
    vocabulary: Vocabulary = _NO_VOCABULARY
    #: The share of readable turns that get a nod. The rest open with the model.
    rate: float = 0.75
    hold_after_s: float = 4.0
    sorry_after_s: float = 12.0
    rng: random.Random = field(default_factory=random.Random)
    _last: str = ""

    def line(self, text: str, spoken: L) -> str | None:
        """The line to say before the model runs, or ``None`` for none this turn."""
        kind = classify(text, self.vocabulary)
        lines = self.lines.get(spoken, {}).get(kind) if kind else None
        if not lines or self.rng.random() >= self.rate:
            return None
        return self._pick(lines)

    def hold(self, spoken: L) -> str:
        """A line that keeps the floor while the model is slow: in ``spoken``,
        else in the first language the demo wrote lines for."""
        return self._pick(self.hold_lines.get(spoken) or next(iter(self.hold_lines.values())))

    def _pick(self, lines: Iterable[str]) -> str:
        options = list(lines)
        self._last = self.rng.choice([x for x in options if x != self._last] or options)
        return self._last


async def own_line(
    brain: GeminiBrain, line: str, at: int | None = None
) -> AsyncGenerator[Speech, None]:
    """One unit of the brain's own, queued for its finalize at ``at`` (the end by
    default) and never in the model's context."""
    yield SpeechStart()
    awaiting = brain._awaiting  # pyright: ignore[reportPrivateUsage]
    unit = _Unit(types.Content(role="model", parts=[]))
    awaiting.insert(len(awaiting) if at is None else at, unit)
    yield SpeechChunk(line)
    yield SpeechEnd()


async def hold_the_floor[L: str](
    brain: GeminiBrain,
    ack: Acknowledger[L],
    spoken: Callable[[], L],
    turn: AsyncGenerator[Speech, None],
    answered: Callable[[], None] = lambda: None,
) -> AsyncGenerator[Speech, None]:
    """The model's turn after a nod, with a line of the brain's own if it stays quiet.

    The turn runs in a task of its own that feeds a queue, so its context — the
    turn's calls that :class:`~voqalize_demos.FallbackLine` reads — stays in one
    task, and the wait for its next event can time out without disturbing it. A
    held line goes out only while the model has yielded nothing, and is queued
    for its finalize ahead of any unit the model has opened. ``answered`` is
    called before each of the model's own events."""
    done = object()
    events: asyncio.Queue[object] = asyncio.Queue()

    async def pump() -> None:
        try:
            async for event in turn:
                await events.put(event)
        finally:
            await events.put(done)

    awaiting = brain._awaiting  # pyright: ignore[reportPrivateUsage]
    before = {id(unit) for unit in awaiting}
    task = asyncio.create_task(pump())
    floor = [ack.hold_after_s, ack.sorry_after_s - ack.hold_after_s]
    try:
        while True:
            try:
                event = await asyncio.wait_for(events.get(), floor[0] if floor else None)
            except TimeoutError:
                line = ack.hold(spoken()) if len(floor) == 2 else ack.sorry[spoken()]
                floor.pop(0)
                logger.warning("acknowledge: the model is quiet after the nod; saying {!r}", line)
                at = next(
                    (i for i, unit in enumerate(awaiting) if id(unit) not in before),
                    len(awaiting),
                )
                async for e in own_line(brain, line, at):
                    yield e
                continue
            if event is done:
                break
            floor = []
            answered()
            yield cast(Speech, event)
        task.result()
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
