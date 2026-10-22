"""Screen cues in Javier's speech: the page moves when he says the sentence.

A tool call moves the page once, when the model has finished writing — and the model writes a whole
reply in about a second, which the voice then takes fifteen to say. A reply that
walked through three steps had the page at the first and the voice at the third.
So the model writes its moves *into* the reply, at the start of the sentence
they belong to::

    {page: /especialidades} Tenemos varias especialidades. {show: Pediatría}
    Pediatría atiende a niños y adolescentes. {show: Dermatología} Y
    dermatología ve la piel.

:class:`CueParser` takes the reply as it streams, chunk by chunk, and hands back
the text with the cues taken out — the voice never reads one — and each cue
with the first words of the sentence it belongs to (``at``). The page fires a
cue when the voice reaches those words, following the call's own spoken-text
events, which are released as the audio plays. Anchoring to the sentence's own
opening words is right whether those events come a word at a time or a sentence
at a time. A cue with no words after it (the end of the reply) has an empty
``at`` and fires when the voice stops.

Cues are written ``{kind: value}``, one of ``page``, ``show`` and ``faq``. A
brace the model opens and never closes is dropped once it runs past
:data:`MAX_CUE`, so a stray ``{`` can hold back at most that much speech.

The model does not always write them: on an earlier site demo it described
four sections of a page, twice, with no cue at all. So each sentence,
once it is complete, is handed to an ``auto`` callback with the cue kinds the
model put on it, and whatever cues that returns are anchored to the sentence
like the model's own.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

CueKind = Literal["page", "show", "faq"]

#: The longest a cue may run, braces included, before it is given up as text.
MAX_CUE = 220
#: How many of the sentence's opening words the page waits to hear.
AT_WORDS = 3

_CUE = re.compile(r"^\{\s*(page|show|faq)\s*:\s*(.+?)\s*\}$", re.IGNORECASE | re.DOTALL)
_WORD = re.compile(r"[a-z0-9']+")
#: A sentence ends at a full stop, question or exclamation mark with a space
#: after it — so "$39.99" and a stop still at the end of a chunk do not end one.
_END = re.compile(r"[.!?](?=\s)")

#: ``(sentence, index in the unit, the model's own cues on it as (kind, value))``
#: → cues to add at its start, in order.
AutoCues = Callable[[str, int, tuple[tuple["CueKind", str], ...]], list[tuple["CueKind", str]]]


def words(text: str) -> list[str]:
    """Lower-cased words without their accents, as the page compares what it
    hears: the site and half his replies are Spanish, and "está" must stay one
    word on both sides."""
    folded = unicodedata.normalize("NFKD", text.lower().replace(chr(0x2019), "'"))
    return _WORD.findall("".join(c for c in folded if not unicodedata.combining(c)))


@dataclass(frozen=True)
class RawCue:
    kind: CueKind
    value: str
    at: str
    """The first words of the sentence it belongs to, lower-cased and
    space-joined; empty when nothing was said after it."""
    word: int
    """How many words of the unit come before it: the page's clock when the
    voice sends no spoken-text events to follow."""


@dataclass
class _Waiting:
    kind: CueKind
    value: str
    said_from: int
    """Where in the unit's spoken text the words after it begin."""


class CueParser:
    """One unit of speech: feed it chunks, get spoken text and cues back. A cue
    comes back once :data:`AT_WORDS` words have followed it, or at :meth:`flush`."""

    def __init__(self, auto: AutoCues | None = None) -> None:
        #: Everything the unit has said so far, as text: a word split across
        #: two chunks is still one word here.
        self._said = ""
        self._pending = ""
        self._waiting: list[_Waiting] = []
        self._auto = auto
        #: Where each of the model's cues sat in the spoken text, and its kind.
        self._marks: list[tuple[int, CueKind, str]] = []
        #: Where the next sentence starts, and how many came before it.
        self._sentence_from = 0
        self._sentences = 0

    def feed(self, chunk: str) -> tuple[str, list[RawCue]]:
        """The speakable part of ``chunk`` and the cues now anchored."""
        out = ""
        text = self._pending + chunk
        self._pending = ""
        i = 0
        while i < len(text):
            # A space already said, then a cue taken out: the space after the
            # cue would be a second one. Skipped here rather than tidied after,
            # so every recorded position stays true.
            if (out or self._said).endswith((" ", "\t")):
                while i < len(text) and text[i] in " \t":
                    i += 1
            start = text.find("{", i)
            if start < 0:
                out += text[i:]
                break
            out += text[i:start]
            end = text.find("}", start)
            if end < 0:
                if len(text) - start > MAX_CUE:
                    # Never closed: not a cue. Drop the brace, speak the rest.
                    out += text[start + 1 :]
                else:
                    self._pending = text[start:]
                break
            if (m := _CUE.match(text[start : end + 1])) is not None:
                kind: CueKind = m.group(1).lower()  # type: ignore[assignment]
                value = " ".join(m.group(2).split())
                at = len(self._said) + len(out)
                self._waiting.append(_Waiting(kind, value, at))
                self._marks.append((at, kind, value))
            # Anything else in braces is not for the voice either.
            i = end + 1
        self._said += out
        done = self._complete(final=False)
        return out, done + self._ready(final=False)

    def flush(self) -> tuple[str, list[RawCue]]:
        """The end of the unit: an unclosed brace is text, and every cue still
        waiting comes back with what followed it."""
        rest = self._pending.lstrip("{")
        self._pending = ""
        self._said += rest
        done = self._complete(final=True)
        return rest, done + self._ready(final=True)

    def _complete(self, *, final: bool) -> list[RawCue]:
        """Each sentence finished since the last call: the model's cues inside
        it, anchored to its own words, then whatever ``auto`` adds at its start."""
        done: list[RawCue] = []
        while True:
            m = _END.search(self._said, self._sentence_from)
            if m is not None:
                end = m.end()
            elif final and self._said[self._sentence_from :].strip():
                end = len(self._said)
            else:
                return done
            start, self._sentence_from = self._sentence_from, end
            body = self._said[start:end]
            first = start + len(body) - len(body.lstrip())
            keep: list[_Waiting] = []
            for w in self._waiting:
                if w.said_from < end:
                    at = " ".join(words(self._said[w.said_from : end])[:AT_WORDS])
                    done.append(RawCue(w.kind, w.value, at, len(words(self._said[: w.said_from]))))
                else:
                    keep.append(w)
            self._waiting = keep
            if self._auto is not None and body.strip():
                placed: tuple[tuple[CueKind, str], ...] = tuple(
                    (k, v) for p, k, v in self._marks if start <= p < end
                )
                at = " ".join(words(body)[:AT_WORDS])
                word = len(words(self._said[:first]))
                for kind, value in self._auto(body.strip(), self._sentences, placed):
                    done.append(RawCue(kind, value, at, word))
            self._sentences += 1

    def _ready(self, *, final: bool) -> list[RawCue]:
        done: list[RawCue] = []
        keep: list[_Waiting] = []
        for w in self._waiting:
            after = words(self._said[w.said_from :])
            # Wait for a word more than needed: the last one may still be
            # growing in the next chunk.
            if final or len(after) > AT_WORDS:
                at = " ".join(after[:AT_WORDS])
                done.append(RawCue(w.kind, w.value, at, len(words(self._said[: w.said_from]))))
            else:
                keep.append(w)
        self._waiting = keep
        return done


__all__ = ["AT_WORDS", "MAX_CUE", "AutoCues", "CueKind", "CueParser", "RawCue", "words"]
