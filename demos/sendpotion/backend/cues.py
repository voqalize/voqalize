"""Screen cues in Tushar's speech: the page moves when he says the sentence.

A tool call moves the page once, when the model has finished writing — and the
model writes a whole reply in about a second, which the voice then takes fifteen
to say. A reply that walks through three steps had the page at the first and
the voice at the third (dev call e1596465). So the model writes its moves *into*
the reply, at the start of the sentence they belong to::

    Potion works in three steps. {show: Train video AI} First, you train it on
    you, in about four minutes. {show: Type video script or record a video
    template} Then you type a script.

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
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

CueKind = Literal["page", "show", "faq"]

#: The longest a cue may run, braces included, before it is given up as text.
MAX_CUE = 220
#: How many of the sentence's opening words the page waits to hear.
AT_WORDS = 3

_CUE = re.compile(r"^\{\s*(page|show|faq)\s*:\s*(.+?)\s*\}$", re.IGNORECASE | re.DOTALL)
_WORD = re.compile(r"[a-z0-9']+")


def words(text: str) -> list[str]:
    """Lower-cased words, as the page compares what it hears."""
    return _WORD.findall(text.lower().replace(chr(0x2019), "'"))


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

    def __init__(self) -> None:
        #: Everything the unit has said so far, as text: a word split across
        #: two chunks is still one word here.
        self._said = ""
        self._pending = ""
        self._waiting: list[_Waiting] = []

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
                self._waiting.append(_Waiting(kind, value, len(self._said) + len(out)))
            # Anything else in braces is not for the voice either.
            i = end + 1
        self._said += out
        return out, self._ready(final=False)

    def flush(self) -> tuple[str, list[RawCue]]:
        """The end of the unit: an unclosed brace is text, and every cue still
        waiting comes back with what followed it."""
        rest = self._pending.lstrip("{")
        self._pending = ""
        self._said += rest
        return rest, self._ready(final=True)

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


__all__ = ["AT_WORDS", "MAX_CUE", "CueKind", "CueParser", "RawCue", "words"]
