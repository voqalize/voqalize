"""Cues in a reply: the page moves when the voice says the sentence.

A tool call moves the page once, when the model has finished writing — and a
model writes a whole reply in about a second, which the voice then takes
fifteen to say. A reply that walks through three steps would have the page at
the first and the voice at the third. So the model writes its moves *into* the
reply, right before the first word of the sentence they belong to::

    It's an oasis in the desert. {show: Included with Your Stay} Everything
    is included. {show: Explorations} There are nearly fifty to choose from.

:class:`CueParser` takes one unit of speech as it streams, chunk by chunk, and
hands back the text with the cues taken out — the voice never reads one — and
each cue as a :class:`RawCue`, with the spoken text that follows it (``at``)
and how many characters were said before it (``before``). The page segments
``at`` into words the same way it segments what it hears, so the brain never
splits words itself and anchors work in any script.

The grammar::

    cue  := "{" verb [ ":" arg ( "|" arg ){0,3} ] "}"
    verb := [a-z]{2,12}      one of the brain's registered verbs
    arg  := at most 80 characters, no braces or newline; trimmed

Anything else in braces is not spoken either, and a cue whose verb is not
registered is dropped. A brace the model opens and never closes is given up
once it runs past :data:`MAX_CUE`, and what followed it is spoken.

The model does not always write cues. Each sentence, once complete, is handed
to an optional ``auto`` backstop with the cues the model placed in it, and
whatever cues that returns are anchored to the sentence's start like the
model's own.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Collection
from dataclasses import dataclass

from loguru import logger

from .moves import MAX_ARGS

__all__ = [
    "AT_CHARS",
    "MAX_ARG",
    "MAX_CUE",
    "RELEASE_CHARS",
    "RELEASE_TOKENS",
    "AutoCues",
    "CueParser",
    "RawCue",
]

#: The longest a cue may run, braces included, before it is given up as text.
MAX_CUE = 220
#: The longest one argument may be.
MAX_ARG = 80
#: How much of the following spoken text a cue carries as ``at``.
AT_CHARS = 48
#: A cue is released once this many whitespace-separated tokens follow it...
RELEASE_TOKENS = 3
#: ...or this many characters, in a script written without spaces.
RELEASE_CHARS = 12

_CUE = re.compile(r"\{\s*([A-Za-z]+)\s*(?::(.*))?\}", re.DOTALL)
_VERB = re.compile(r"[a-z]{2,12}")
#: A sentence ends at a full stop, question or exclamation mark, ellipsis or
#: danda with whitespace after it — so "$39.99" and a stop still at the end of
#: a chunk do not end one — or at a full-width stop, which never needs a space.
_END = re.compile(r"[.!?\u2026\u0964\u0965](?=\s)|[\u3002\uff01\uff1f]")
#: Scripts written without spaces between words: Thai, Lao, Myanmar, Khmer,
#: kana, CJK ideographs, half-width katakana.
_SPACELESS = re.compile(
    r"[\u0e00-\u0eff\u1000-\u109f\u1780-\u17ff\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff66-\uff9f]"
)

#: ``(sentence, index in the unit, the model's own cues in it as (verb, args))``
#: → cues to add at its start, in order, as ``(verb, args)``.
AutoCues = Callable[
    [str, int, tuple[tuple[str, tuple[str, ...]], ...]], list[tuple[str, list[str]]]
]


@dataclass(frozen=True, slots=True)
class RawCue:
    """A cue taken out of the speech, not yet resolved against the page."""

    verb: str
    args: tuple[str, ...]
    at: str
    """The spoken text that follows the cue, whitespace collapsed, up to
    :data:`AT_CHARS` characters cut on a space where one falls; empty when
    nothing was said after it."""
    before: int
    """How many characters of the unit's spoken text come before it: the
    page's clock when it hears no spoken text to follow."""
    unit: int = 0
    """Which unit of speech of the turn it belongs to."""
    auto: bool = False
    """Whether the backstop added it, rather than the model."""


@dataclass(slots=True)
class _Waiting:
    verb: str
    args: tuple[str, ...]
    pos: int
    """Where in the unit's spoken text the words after it begin."""
    seq: int
    auto: bool


def _clip(text: str) -> str:
    """``text`` cut to :data:`AT_CHARS`, on a space when one falls inside."""
    if len(text) <= AT_CHARS:
        return text
    if text[AT_CHARS] == " ":
        return text[:AT_CHARS]
    cut = text[:AT_CHARS]
    space = cut.rfind(" ")
    return cut[:space] if space > 0 else cut


def _parse(body: str) -> tuple[str, tuple[str, ...]] | None:
    """A cue's verb and arguments, or ``None`` when ``body`` is not one."""
    m = _CUE.fullmatch(body)
    if m is None:
        return None
    verb = m.group(1).lower()
    if _VERB.fullmatch(verb) is None:
        return None
    raw = m.group(2)
    if raw is None:
        return verb, ()
    if "\n" in raw or "\r" in raw:
        return None
    args = tuple(" ".join(a.split()) for a in raw.split("|"))
    if len(args) > MAX_ARGS or any(not a or len(a) > MAX_ARG for a in args):
        return None
    return verb, args


class CueParser:
    """One unit of speech: feed it chunks, get spoken text and cues back.

    A cue comes back once :data:`RELEASE_TOKENS` whitespace-separated tokens
    (or :data:`RELEASE_CHARS` characters of a script written without spaces)
    have followed it, or at :meth:`flush`, in the order of where it sits in the
    speech. With a backstop, a cue also waits for its sentence to finish, so
    that a cue the backstop adds at that sentence's start is sent before it.
    """

    def __init__(
        self, verbs: Collection[str], auto: AutoCues | None = None, *, unit: int = 0
    ) -> None:
        self._verbs = frozenset(verbs)
        self._auto = auto
        self._unit = unit
        #: Everything the unit has said so far, as text: a word split across
        #: two chunks is still one word here.
        self._said = ""
        self._pending = ""
        self._waiting: list[_Waiting] = []
        self._seq = 0
        #: Where each of the model's cues sat in the spoken text.
        self._marks: list[tuple[int, str, tuple[str, ...]]] = []
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
            body = text[start : end + 1]
            parsed = _parse(body)
            if parsed is not None and parsed[0] in self._verbs:
                verb, args = parsed
                pos = len(self._said) + len(out)
                self._wait(verb, args, pos, auto=False)
                self._marks.append((pos, verb, args))
            elif parsed is not None:
                logger.info("stage: {!r} is not a move of this brain; dropped", body)
            # Anything else in braces is not for the voice either.
            i = end + 1
        self._said += out
        self._complete(final=False)
        return out, self._release(final=False)

    def flush(self) -> tuple[str, list[RawCue]]:
        """The end of the unit: an unclosed brace is text, and every cue still
        waiting comes back with what followed it."""
        rest = self._pending.lstrip("{")
        self._pending = ""
        self._said += rest
        self._complete(final=True)
        return rest, self._release(final=True)

    def _wait(self, verb: str, args: tuple[str, ...], pos: int, *, auto: bool) -> None:
        self._waiting.append(_Waiting(verb, args, pos, self._seq, auto))
        self._seq += 1

    def _complete(self, *, final: bool) -> None:
        """Offer each sentence finished since the last call to ``auto``, with
        the model's cues inside it, and queue what it adds at its start."""
        while True:
            m = _END.search(self._said, self._sentence_from)
            if m is not None:
                end = m.end()
            elif final and self._said[self._sentence_from :].strip():
                end = len(self._said)
            else:
                return
            start, self._sentence_from = self._sentence_from, end
            body = self._said[start:end]
            if self._auto is not None and body.strip():
                first = start + len(body) - len(body.lstrip())
                placed = tuple((v, a) for p, v, a in self._marks if start <= p < end)
                for verb, args in self._auto(body.strip(), self._sentences, placed):
                    if verb not in self._verbs:
                        logger.info("stage: backstop cue {!r} is not a move; dropped", verb)
                        continue
                    self._wait(verb, tuple(args), first, auto=True)
            self._sentences += 1

    def _ready(self, pos: int) -> bool:
        if self._auto is not None and pos >= self._sentence_from:
            # Its sentence is not finished, so the backstop has not yet had
            # its say: a cue it adds at the sentence's start must go first.
            return False
        after = self._said[pos:]
        tokens = after.split()
        complete = len(tokens) if after[-1:].isspace() else len(tokens) - 1
        if complete >= RELEASE_TOKENS:
            return True
        return _SPACELESS.search(after) is not None and len("".join(tokens)) >= RELEASE_CHARS

    def _at(self, pos: int, *, final: bool) -> str:
        after = self._said[pos:]
        if not final and _SPACELESS.search(after) is None and not after[-1:].isspace():
            # The last token may still be growing in the next chunk.
            after = after[: max(after.rfind(" "), after.rfind("\t"), after.rfind("\n"), 0)]
        return _clip(" ".join(after.split()))

    def _release(self, *, final: bool) -> list[RawCue]:
        self._waiting.sort(key=lambda w: (w.pos, w.seq))
        done: list[RawCue] = []
        while self._waiting and (final or self._ready(self._waiting[0].pos)):
            w = self._waiting.pop(0)
            at = self._at(w.pos, final=final)
            done.append(RawCue(w.verb, w.args, at, w.pos, self._unit, w.auto))
        return done
