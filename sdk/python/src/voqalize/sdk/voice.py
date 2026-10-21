"""The voice core: how a model's stream becomes a voice turn, for any model.

    from voqalize.sdk.openai import OpenAIBrain      # or GeminiBrain, LiteLLMBrain

    class Concierge(OpenAIBrain):
        ...

:class:`VoiceCore` is the part of a model-backed brain that is about *voice*, not
about any one model: when speech opens and closes, when a tool runs against the
words around it, which tool results are worth a round trip of silence, what the
context records once the user cut a reply short, and what a turn cost. It holds no
prompt, no product rule and no model client, and it imports no vendor. Every word
it sends to speech is a word the model wrote.

A provider layer — :class:`~voqalize.sdk.gemini.GeminiBrain`,
:class:`~voqalize.sdk.openai.OpenAIBrain`, :class:`~voqalize.sdk.litellm.LiteLLMBrain`
— is the other part. It calls the model's API and hands this class its stream as
:class:`ModelChunk` values, keeps the conversation in the provider's own types,
and answers a handful of small questions about them (is this part text? a call?
add this part). Nothing else. Subclass a layer, never this class, unless you are
writing a layer.

**The model speaks first, and a tool's result waits for the next request.**
:attr:`~VoiceCore.tools` is a plain list of bound ``async def`` methods, and the
method is the declaration — its docstring is the description the model reads, its
parameter is the schema. Each call runs the moment it arrives in the stream, and
the call and its result go into the context. The model is not asked again for
that result: it reads it with the user's next message. A voice turn that waits a
whole round trip for an ``"ok"`` is dead air the user sits through, so that wait
is the exception, and a tool asks for it by name — :func:`needs_result_now`, for a
tool that reads data the model needs to say its reply. Every tool returns within
:data:`TOOL_BUDGET_MS`; a slower one is logged.

**The brain owns the context, and what it records is what was heard.** Each unit
of speech goes into the context as it streams, then
:meth:`~voqalize.sdk.Brain.on_finalize` rewrites it to the delivered prefix. A
reply that generated three sentences and was cut after one is remembered as one —
which is the only version the user and the model can both agree on.

**Every turn reports what it did.** One ``turn:`` log line per model loop, and,
when Voqalize records them, one :class:`~voqalize.sdk.TurnStep` on the wire for
every model request and every tool: what ran, when, for how long, and for a
model request its tokens by kind. Counts, never prices. Build with
``report_steps=False`` to keep them off the wire; the log line stays.
"""

from __future__ import annotations

import inspect
import re
import time
from collections import deque
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from loguru import logger

from .brain import Brain, Session
from .events import Finalize, Speech, SpeechChunk, SpeechEnd, SpeechStart, TurnStep, UserMessage

__all__ = [
    "TOOL_BUDGET_MS",
    "ModelChunk",
    "ModelPart",
    "ModelUsage",
    "ToolChoice",
    "VoiceCore",
    "needs_result_now",
]


# ─── What a provider layer hands the core ────────────────────────────────────


@dataclass
class ModelPart:
    """One piece of a model's response, as the layer read it off the stream.

    ``raw`` is the provider's own object and is what goes into the context,
    verbatim, so whatever the provider needs handed back (a thought signature, an
    encrypted reasoning item) survives. ``kind`` is the only thing the core reads:

    - ``"text"``: words for the user; ``text`` holds them.
    - ``"thought"``: reasoning, never spoken, kept in the context.
    - ``"call"``: a function call; ``call`` is what the layer's ``_run`` takes.
    - ``"other"``: anything else the provider sent, kept in the context.
    """

    kind: Literal["text", "thought", "call", "other"]
    raw: Any
    text: str = ""
    call: Any = None


@dataclass
class ModelUsage:
    """What one model request cost, as its API reported it. ``None`` is "not
    reported", never zero. ``input`` includes ``cached_input``; ``output`` is text
    and tool calls, with ``reasoning`` counted apart."""

    input: int | None = None
    cached_input: int | None = None
    cache_write: int | None = None
    output: int | None = None
    reasoning: int | None = None

    def counts(self) -> dict[str, int]:
        """The reported counts under their wire names, leaving out the rest."""
        named = {
            "input_tokens": self.input,
            "cached_input_tokens": self.cached_input,
            "cache_write_tokens": self.cache_write,
            "output_tokens": self.output,
            "reasoning_tokens": self.reasoning,
        }
        return {name: n for name, n in named.items() if n is not None}

    def __add__(self, other: ModelUsage) -> ModelUsage:
        def add(a: int | None, b: int | None) -> int | None:
            return None if a is None and b is None else (a or 0) + (b or 0)

        return ModelUsage(
            input=add(self.input, other.input),
            cached_input=add(self.cached_input, other.cached_input),
            cache_write=add(self.cache_write, other.cache_write),
            output=add(self.output, other.output),
            reasoning=add(self.reasoning, other.reasoning),
        )


@dataclass
class ModelChunk:
    """One step of a model's stream: the parts it carried, whether the response
    ended here (``finished``), whether it ended because its output did not parse
    (``malformed``), and the request's usage if it arrived on this step. Usage is
    the request's running total, so a later chunk's replaces an earlier one's."""

    parts: list[ModelPart] = field(default_factory=lambda: list[ModelPart]())
    finished: bool = False
    malformed: bool = False
    usage: ModelUsage | None = None


@dataclass(frozen=True)
class ToolChoice:
    """Which tools one :meth:`VoiceCore.respond` may call.

    ``ToolChoice.AUTO`` (the default) lets the model choose; ``ToolChoice.NONE``
    takes every tool away, so the model has to speak; ``ToolChoice.only(name)``
    makes it call that one tool. The tools stay declared either way, so the calls
    already in the context still read."""

    mode: Literal["auto", "none", "only"] = "auto"
    name: str | None = None

    AUTO: ClassVar[ToolChoice]
    NONE: ClassVar[ToolChoice]

    @classmethod
    def only(cls, name: str) -> ToolChoice:
        """The model must call ``name``, and no other tool."""
        return cls("only", name)


ToolChoice.AUTO = ToolChoice("auto")
ToolChoice.NONE = ToolChoice("none")


# ─── Tools ───────────────────────────────────────────────────────────────────

#: How long a tool may take, in milliseconds, before it is logged as slow. A tool
#: runs while the user waits for the agent's next word, so it reads memory,
#: dispatches to the screen, starts background work if it has any, and returns.
#: Nothing is cancelled at the budget; the warning is the whole enforcement.
TOOL_BUDGET_MS = 20

_NEEDS_RESULT_NOW = "__voqalize_needs_result_now__"


def needs_result_now[F: Callable[..., Any]](fn: F) -> F:
    """Mark a tool whose result the model must read before it finishes its reply.

    **Add it when the tool reads data the model needs to answer correctly** — a
    balance, a cart, what is on the screen, an eligibility check — from memory.
    Leave it off everything else: actions, screen changes, sign-in prompts,
    language switches, and a tool whose result only repeats what the model
    already said. Unmarked is the default, and the right answer for most tools.

    What it changes. By default a tool runs when the model calls it, its result
    goes into the context, and the turn ends when the model stops speaking: the
    model reads the result with the user's next message. With this mark, the
    model is asked again as soon as the tool returns, with every result so far,
    and speaks about it now. That costs the user a whole model round trip of
    silence, which is why it is not the default.

    What the user hears if a tool that needs it is missing it: the agent says
    its line, calls the tool, and goes quiet until the user speaks again — then
    answers from the result, a turn late. What they hear if a tool that does not
    need it has it: a pause before every reply that calls it.

    It sets an attribute and nothing else, so it works on a method or on a free
    function, above or below other decorators that keep attributes. It does not
    make a slow tool acceptable: every tool, marked or not, returns within
    :data:`TOOL_BUDGET_MS`::

        class Desk(OpenAIBrain):
            async def show_card_controls(self) -> str:
                "Put the card controls on screen."
                self.session.dispatch(ShowCardControls())
                return "shown"

            @needs_result_now
            async def get_account_balance(self, args: Account) -> dict[str, str]:
                "The balance of one of the customer's accounts."
                return self.accounts[args.number].balance()
    """
    setattr(fn, _NEEDS_RESULT_NOW, True)
    return fn


def _needs_result_now(fn: Callable[..., Any]) -> bool:
    return getattr(fn, _NEEDS_RESULT_NOW, False) is True


def _require_async(fn: Callable[..., Any]) -> None:
    """A tool is ``async def``, or it is refused before the model ever sees it.

    A tool is awaited in the turn's own task, on the loop, which is what stamps
    its ``self.session.dispatch`` with the turn the model is answering. A
    synchronous tool would have to run either on the loop, where its first
    blocking call stalls every session in the process, or on a worker thread,
    where the first ``await`` it grows is a rewrite. So there is one kind of tool.
    """
    if not inspect.iscoroutinefunction(fn):
        raise TypeError(
            f"tool {getattr(fn, '__name__', fn)!r} must be `async def`. A tool runs in the "
            "turn's task on the event loop, and a sync one would block every session in "
            "the process while it ran. Make it `async def` — the body needs no other change."
        )


# ─── A function call written as text ─────────────────────────────────────────

# How a function call the model wrote out as TEXT begins. At low thinking a model
# occasionally emits its call as words instead of as a function call —
# `certain_tool_call\n  "name": "default_api:read_screen"` was one, on a live
# travel session — and text is speech, so the user heard it read aloud and no
# tool ran. Ordinary speech, in any language, opens with none of these; a unit
# that opens with one is held until it is known, and never spoken.
_CALL_HEADS = (
    "```",
    "tool_call",
    "tool_code",
    "tool_use",
    "certain_tool_call",
    "function_call",
    "functions.",
    "default_api",
    "print(default_api",
)

# The key that names a call once the text opens a JSON object, a list or a tag.
_CALL_KEYS = frozenset(
    {"name", "function", "tool", "call", "args", "arguments", "action", "parameters"}
)

_WRAPPERS = "{[<\"'"
_IDENTIFIER = re.compile(r"[a-z_][a-z0-9_]*")

# How a function call written as text begins *after speech has started* in the
# same unit — "Opening it now. certain_tool_call …". Narrower than the opening
# heads on purpose: a sentence already under way may say "tool call", or even
# "default_api", and cutting it there would silence real speech. These are the
# forms no sentence carries: a code fence, a call tag, the leaked-call prefix,
# `default_api` followed by the `:` or `.` that names a function, and a JSON
# object whose first key names a call.
_SPOKEN_CALL_HEADS = (
    "```",
    "<tool_call",
    "<tool_code",
    "<function_call",
    "certain_tool_call",
    "default_api:",
    "default_api.",
)
_SPOKEN_CALL_KEYS = "|".join(sorted(_CALL_KEYS))
_SPOKEN_CALL = re.compile(
    r"```|<(?:tool_call|tool_code|function_call)"
    r"|(?<!\w)(?:certain_tool_call|default_api[:.])"
    rf"|\{{\s*[\"'](?:{_SPOKEN_CALL_KEYS})[\"']\s*:",
    re.IGNORECASE,
)
# A JSON object's opening that could still grow into `{"name":` — the brace, the
# quote, and the letters of a key so far.
_JSON_OPENING = re.compile(r"""\{\s*(?:(["'])([a-z]*)(?:\1\s*)?)?""", re.IGNORECASE)
_WORD = re.compile(r"\w")
# Where a held tail can start. Nothing in Devanagari or any other script is here,
# so speech in those holds nothing at all.
_TAIL_STARTS = frozenset("`<{cCdD")
# A tail is a head's length at most, bar whitespace inside a JSON opening such as
# `{  "na`; this caps the look-back, and so the hold, even then.
_TAIL_SCAN = 64

# Sent on the one retry, after the model's function call came out as text or
# malformed. It goes on that request only and never into the context, so the
# conversation reads as though the model answered well the first time. When the
# call came after words were spoken, those words are already in the context as
# the model's own, which is how it knows what not to say again.
_RETRY_TEXT = (
    "Your last reply tried to call a function but wrote the call as text, or "
    "wrote it malformed. No function ran, and the user heard none of that "
    "text: only the words before it, if there were any, which are above as "
    "your own. Make the call through function calling now, or answer in "
    "speech, and do not say again what was already said. Do not mention "
    "this note."
)


def _looks_like_call(text: str) -> bool | None:
    """Whether a unit that opens with ``text`` is a function call written as text.

    ``True`` and ``False`` are verdicts. ``None`` means the opening is still a
    prefix of one, and the next piece decides.

    The verdict comes from the opening only, so ordinary speech costs nothing:
    a sentence that opens with a letter, a digit or any non-Latin script is
    ``False`` on its first piece, whatever it goes on to say — "tool", braces and
    underscores mid-sentence included. Only an opening that is a strict prefix of
    a call head (``"Default"``, ``"Tool"``, ``"{"``) waits, and the piece after it
    settles it. Text that opens a JSON object, list, tag or quote waits for its
    first key and is a call only if that key names one (``{"name": …``).
    """
    s = text.lstrip().casefold()
    if not s:
        return None
    if s.startswith(_CALL_HEADS):
        return True
    if any(head.startswith(s) for head in _CALL_HEADS):
        return None
    wrapped = s[0] in _WRAPPERS
    if wrapped:
        s = s.lstrip(_WRAPPERS + " \t\r\n")
        if not s:
            return None
        if s.startswith(_CALL_HEADS):
            return True
    word = _IDENTIFIER.match(s)
    if word is None:
        return False
    if "_" in word.group():
        # `read_screen(`, `open_itinerary:` — nobody says an underscore.
        return True
    if not wrapped:
        return False
    if word.end() == len(s):
        return None
    return word.group() in _CALL_KEYS and s[word.end()] in "\"':"


def _tail_start(text: str, start: int) -> int:
    """Where the end of ``text`` could still be the start of a call written as
    text, or ``len(text)`` when it cannot — so a piece that ends on a space, a
    full stop or any Devanagari holds nothing back.

    A letter head (``certain_tool_call``, ``default_api:``) counts only where it
    starts a word; ``text[start - 1]`` is the character already spoken before
    it."""
    for i in range(max(start, len(text) - _TAIL_SCAN), len(text)):
        ch = text[i]
        if ch not in _TAIL_STARTS:
            continue
        if ch.isalpha() and i and _WORD.match(text[i - 1]):
            continue
        if _may_open_spoken_call(text[i:]):
            return i
    return len(text)


def _may_open_spoken_call(s: str) -> bool:
    """Whether ``s`` is a strict prefix of a :data:`_SPOKEN_CALL` marker: the next
    piece could complete it."""
    low = s.lower()
    if any(head.startswith(low) for head in _SPOKEN_CALL_HEADS):
        return True
    opening = _JSON_OPENING.fullmatch(s)
    if opening is None:
        return False
    key = opening.group(2)
    if key is None:
        return True
    if opening.end(2) < len(s):
        # The key's closing quote has come; only a call's key can still become one.
        return key.lower() in _CALL_KEYS
    return any(k.startswith(key.lower()) for k in _CALL_KEYS)


# ─── One unit of speech ──────────────────────────────────────────────────────


@dataclass
class _Unit:
    """One model turn, held by identity while it is still being written.

    A provider's turn type is often a pydantic model, so two of them compare equal
    whenever their fields do — and two freshly opened, still-empty turns always do.
    The queue and the context therefore track *this*, never the content itself.

    It also holds back the unit's opening while that opening could still be a
    function call the model wrote out as text — see :func:`_looks_like_call` —
    and, once it is speaking, the short tail that could still be the start of one
    — see :data:`_SPOKEN_CALL`.
    """

    #: The provider's model turn, in the context from the moment the unit opens.
    content: Any
    #: Text not yet spoken, because the opening is still undecided.
    held: list[str] = field(default_factory=lambda: list[str]())
    #: ``None`` while undecided, ``False`` once it is speech, ``True`` once it is
    #: a function call written out as text — from its opening, or from a point
    #: after speech began — and nothing more of it will be spoken.
    leaked: bool | None = None
    #: The response ended malformed: the call it tried to make never ran.
    malformed: bool = False
    #: The model made a real function call in this unit.
    called: bool = False
    #: The function responses for this unit's calls: a turn of their own, placed
    #: right after the unit in the context once the first tool returns.
    responses: Any = None
    #: A ``SpeechStart`` for this unit has gone out, and a ``SpeechEnd`` is owed.
    speaking: bool = False
    #: The end of speech under way that could still be the start of a call written
    #: as text — ``"default"``, ``'{"na'``, one backtick. Never longer than a head.
    tail: str = ""
    #: Every piece released to be spoken, in order. A call written as text after
    #: speech began cuts the unit's text in the context down to exactly this.
    said: list[str] = field(default_factory=lambda: list[str]())

    def release(self, text: str) -> list[str]:
        """Take one piece of text; return what may be spoken now.

        Until the opening is known it is held, and the whole held opening is
        released the moment one more piece settles it. After that each piece goes
        out as it arrives, less a tail that could be the start of a call."""
        if self.leaked:
            return []
        if self.leaked is None:
            self.held.append(text)
            self.leaked = _looks_like_call("".join(self.held))
            if self.leaked is not False:
                return []
            pieces, self.held = self.held, []
        else:
            pieces = [text]
        out: list[str] = []
        for piece in pieces:
            out += self._scan(piece)
        return out

    def settle(self, *, malformed: bool) -> list[str]:
        """Close the unit; return held text that turned out to be speech.

        An opening still undecided when the response ends is speech, and so is a
        held tail: the model stopped writing, and nothing it wrote is a call. A
        response that ended malformed speaks nothing more, whatever it held."""
        self.malformed = malformed
        if malformed and self.leaked is None:
            self.leaked = True
        out: list[str] = []
        if self.leaked is None:
            self.leaked = False
            held, self.held = self.held, []
            for piece in held:
                out += self._scan(piece)
        if self.tail and self.leaked is False and not malformed:
            out.append(self.tail)
            self.said.append(self.tail)
        self.tail = ""
        return out

    def _scan(self, text: str) -> list[str]:
        """Speech under way: ``text`` less anything from a call marker on, and less
        the tail that could still become one.

        The released text keeps the piece boundaries it arrived with — the old
        tail, then the new piece — so nothing is merged that was not held."""
        if self.leaked:
            return []
        # The character before the tail, so a marker must start a word.
        context = self.said[-1][-1:] if self.said else ""
        full = context + self.tail + text
        start, split = len(context), len(context) + len(self.tail)
        hit = _SPOKEN_CALL.search(full, start)
        if hit is not None:
            end, self.leaked, self.tail = hit.start(), True, ""
        else:
            end = _tail_start(full, start)
            self.tail = full[end:]
        out = [p for p in (full[start : min(end, split)], full[split:end]) if p]
        self.said += out
        return out

    @property
    def failed_call(self) -> bool:
        """The model tried to call a tool here, nothing ran, and it did not go on
        to make a real call — so the turn is still waiting on it."""
        return bool(self.leaked or self.malformed) and not self.called


# ─── What a turn cost ────────────────────────────────────────────────────────


@dataclass
class _Clock:
    """When a turn's two moments happened, relative to asking for it.

    ``speak`` is the one the user experiences: everything before it is silence
    they are sitting in. It is not the same as ``open`` — a turn that calls a tool
    first starts streaming promptly and may say nothing at all, or speak only
    after a tool it waited on, which is why both are recorded.

    A moment that never came reads ``none``, not a number: a turn cut short by a
    barge-in, or one that only ran tools, genuinely has no time-to-speech, and a
    zero there would be a measurement nobody took.
    """

    started: float
    open: float | None = None
    speak: float | None = None

    def mark_open(self) -> None:
        if self.open is None:
            self.open = time.monotonic()

    def mark_speak(self) -> None:
        if self.speak is None:
            self.speak = time.monotonic()

    def ms(self, at: float | None) -> int | None:
        return None if at is None else round((at - self.started) * 1000)

    def _since(self, at: float | None) -> str:
        ms = self.ms(at)
        return "none" if ms is None else f"{ms}ms"

    def __str__(self) -> str:
        return (
            f"open={self._since(self.open)} speak={self._since(self.speak)} "
            f"total={self._since(time.monotonic())}"
        )


@dataclass
class _Tally:
    """What a turn did: requests made, tools run, how many of those the model was
    asked again for, and the tokens every request reported, summed."""

    hops: int = 0
    calls: int = 0
    awaited: int = 0
    usage: ModelUsage | None = None

    def add(self, usage: ModelUsage | None) -> None:
        if usage is not None:
            self.usage = usage if self.usage is None else self.usage + usage


def _log_turn(model: str, tally: _Tally, clock: _Clock) -> None:
    """What one turn cost, in tokens and in silence.

    A turn is one request, and one more for each response that called a tool
    marked :func:`needs_result_now` (and once more for a call the model wrote as
    text). ``hops`` is how many requests there were, and every token count is the
    **sum** over them, since each request is billed for its whole prompt. A
    context quietly filling up with screen snapshots shows as a rising prompt long
    before it shows as a slow turn, and that is a thing we have already had to
    reconstruct from a production transcript once.

    ``calls`` is the tools the turn ran and ``awaited`` how many of them were
    marked. ``speechless`` says the turn ran and said nothing: the model called a
    tool and did not speak first, so the user heard silence until they spoke
    again. That is the brain's to fix — in its prompt, or by speaking a line of its
    own — and this is where a brain owner sees how often it happens.

    The times are on the same line so that "the brain took four seconds" stops
    being an observation and becomes an attribution: ``speak`` is dead air the
    user heard, and read against ``hops`` and ``prompt`` beside it, it says
    whether the cost was one slow round trip or three fast ones re-sending a
    context that had grown too big.

    Times are always known here; counts are the API's to report, and a count we do
    not have is not a zero — the clause is dropped rather than filled with one.

    Counts and durations only. A token count is not speech, a millisecond is not
    speech, and speech is never a log field.
    """
    shape = (
        f"hops={tally.hops} calls={tally.calls} awaited={tally.awaited} "
        f"speechless={'yes' if clock.speak is None else 'no'}"
    )
    usage = tally.usage
    if usage is None:
        logger.info("turn: model={} {} {} — no usage reported", model, shape, clock)
        return
    logger.info(
        "turn: model={} {} {} prompt={} cached={} output={} thoughts={}",
        model,
        shape,
        clock,
        usage.input or 0,
        usage.cached_input or 0,
        usage.output or 0,
        usage.reasoning or 0,
    )


# ─── The core ────────────────────────────────────────────────────────────────


class VoiceCore[M, R](Brain):
    """The voice half of a model-backed brain, for any model. A provider layer
    subclasses it; a brain subclasses the layer.

    ``M`` is the provider's turn type (what the context is a list of) and ``R`` is
    the provider's request settings for one turn. The layer implements the
    methods under *The provider layer* below and nothing else.

    ``max_tool_hops`` caps how many times one turn asks the model again for the
    result of a tool marked :func:`needs_result_now`. The last of those times
    may not call a tool, so the model has to answer. Unmarked tools never ask
    again, so they never count.

    ``report_steps`` sends a :class:`~voqalize.sdk.TurnStep` to Voqalize for every
    model request and every tool, which it keeps in the call record. On by
    default; ``False`` keeps the numbers in your logs only.
    """

    #: The company whose meter a model step's counts ran on, as its
    #: :class:`~voqalize.sdk.TurnStep` names it. Set by each layer.
    provider: str = ""

    def __init__(self, *, model: str, max_tool_hops: int = 6, report_steps: bool = True) -> None:
        self._model = model
        self._max_tool_hops = max_tool_hops
        self._report_steps = report_steps
        # The conversation, in the provider's own type, on purpose. What a brain
        # owes Voqalize is provider-neutral; what a brain says to a model is the
        # provider's, and a wrapper type in between is one more thing that has to
        # keep up with every provider.
        self._history: list[M] = []
        # Units still awaiting their heard truth, in the order Voqalize will
        # report them. Only units that opened a *speech* unit are here: Voqalize
        # finalizes what it played, and a response that only called a tool played
        # nothing.
        self._awaiting: deque[_Unit] = deque()

    @property
    def model(self) -> str:
        """The model every request names."""
        return self._model

    # ─── Context the conversation does not carry ───────────────────────

    def append_note(self, text: str) -> None:
        """Add one sentence to the context, on the user's side, without starting a
        turn — typically what the person just did on screen, arriving at
        :meth:`~voqalize.sdk.Brain.on_rtvi`::

            async def on_rtvi(self, session, msg):
                match EVENTS.parse(msg):
                    case QuantitySet() as e:
                        self.append_note(f"(They set {e.item_id} to {e.quantity}.)")

        Append the **act**, not the screen. One named sentence is what a model can
        act on; a whole-state blob appended on a debounce is a context full of
        near-identical copies, none of them dated, and a model reasoning from
        whichever it noticed.

        It appends **immediately, once, where you call it**. Nothing here
        debounces, diffs or re-renders. Every request is the previous one plus
        what happened since, which is what makes it cacheable and what stops the
        context changing under a turn already in flight.

        Calling it mid-turn is safe, including from inside a tool. A call's result
        is filed directly after the call, so a note made while the tool runs lands
        after both and never between them. A note is not a speech unit, so heard
        truth never rewrites it and it is never dropped as an unanswered call.
        """
        self._history.append(self._new_user_turn(text))

    async def say_line(self, line: str, *, remember: bool = False) -> AsyncGenerator[Speech, None]:
        """Speak a line the brain wrote itself, as a unit of its own, from inside a
        speaking callback::

            async for event in self.say_line("One moment, opening it."):
                yield event

        The model did not write it, so by default it stays out of the context:
        the model never reads words it did not choose as its own. With
        ``remember=True`` it goes in as the model's words, cut to what the user
        heard like any other unit — right for a line the model needs to know was
        said, such as a question the brain asked.

        Use this rather than yielding the unit yourself: every unit Voqalize plays
        gets a finalize, and a unit this class did not open would take the
        finalize meant for the model's next one.
        """
        unit = _Unit(self._new_model_turn([self._new_text_part(line)] if remember else []))
        yield SpeechStart()
        # Only once the start has been taken: a barge-in that lands on it leaves
        # nothing awaiting a finalize that will never come.
        if remember:
            self._history.append(unit.content)
        self._awaiting.append(unit)
        yield SpeechChunk(line)
        yield SpeechEnd()

    # ─── The turn ───────────────────────────────────────────────────────

    def on_user_message(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]:
        self._history.append(self._new_user_turn(msg.text))
        return self.respond(session)

    def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """Stream one turn: speech, and the tools the model calls along the way.
        The model may call any tool; :meth:`respond_with` limits it. The rules of
        the turn are :meth:`respond_with`'s."""
        return self._respond_turn(session, None)

    def respond_with(self, session: Session, *, tools: ToolChoice) -> AsyncGenerator[Speech, None]:
        """One more model loop on the turn under way, with ``tools`` limiting what
        every request of it may do: ``ToolChoice.NONE`` makes the model speak,
        ``ToolChoice.only(name)`` makes it call ``name``, ``ToolChoice.AUTO`` is
        :meth:`respond`.

        For a brain that checks what a turn did and asks again — a turn that moved
        the screen and said nothing, a reply that promised a link and put none up::

            async def respond(self, session):
                spoke = False
                async for event in super().respond(session):
                    spoke = spoke or isinstance(event, SpeechStart)
                    yield event
                if not spoke:
                    async for event in self.respond_with(session, tools=ToolChoice.NONE):
                        yield event

        It goes straight to the voice core, not through an override of
        :meth:`respond`, so whatever that override adds runs once per turn.

        Stream one turn: speech, and the tools the model calls along the way.

        **One request, and the turn ends when its stream does.** Each function
        call runs the moment it arrives, in stream order, after the speech before
        it has gone out — so "Opening it now." is heard as the screen changes, not
        after. Its result is filed in the context right after the call, and the
        model reads it with the next request. That next request is normally the
        user's next message: a result the model does not need to say *this* reply
        costs no silence. A response that called a tool marked
        :func:`needs_result_now` is the exception — the model is asked again at
        once, with every result that response produced, up to ``max_tool_hops``
        times; the last of those may not call a tool, so the model has to
        answer.

        So a model that calls a tool without speaking first leaves the user in
        silence until they speak again. That is the prompt's to fix — tell the
        model to say a short line, then call, in the same response — or the
        brain's, by asking again with ``tools=ToolChoice.NONE``, or by speaking a
        line of its own with :meth:`say_line`.

        A unit of speech is one response. It **opens** on the first spoken text,
        lazily, so a response that only calls a tool never opens one; it
        **closes** when the response finishes or the stream ends.

        **A function call written as text is never spoken.** At low thinking a
        model sometimes writes its call out as words (``default_api:read_screen``,
        ``{"name": …}``) instead of making it. That text would be read aloud and
        nothing would run. So a unit's opening is held only while it could still
        be one: a sentence that opens with a letter, a digit or Devanagari
        passes on its first piece, and an ambiguous opening waits one more piece,
        or until the response ends. A unit that is a call written as text, or a
        response that ends malformed, speaks nothing and leaves the context, and
        the request goes once more, with a note that is not kept in the context.

        **A call written after speech began is cut where it begins.** A speaking
        unit's text is watched for the forms no sentence carries
        (:data:`_SPOKEN_CALL`: a fence, a call tag, ``certain_tool_call``,
        ``default_api:``, ``{"name":``), including one split across chunks. The
        only text held is a tail that could still be the start of one —
        ``"default"`` at the end of a chunk, one backtick — never a sentence, and
        speech in Devanagari holds nothing. From the marker on, nothing is
        spoken; the speech ends there, and the unit keeps in the context exactly
        the words that went out.

        The turn then asks once more, as it does for a leaked opening. That is a
        choice. The words before such a call are nearly always the model
        announcing it ("Opening it now."), so a turn that ends there has told the
        user something is happening and then done nothing. The retry needs no
        extra bookkeeping to avoid repeating itself: the words the user heard are
        already in the context as the model's own, and the note asks it not to
        say them again. Once only: a model that leaks twice in a row is not
        converging, and a third request is more silence for the user to sit in.

        Each model request and each tool is reported as a
        :class:`~voqalize.sdk.TurnStep` when it ends, unless built with
        ``report_steps=False``, and when the turn ends — finished, cut by a
        barge-in, or failed — it logs one ``turn:`` line.
        """
        return self._respond_turn(session, tools)

    async def _respond_turn(
        self, session: Session, tools: ToolChoice | None
    ) -> AsyncGenerator[Speech, None]:
        """The turn :meth:`respond` and :meth:`respond_with` describe."""
        config = self._turn_request(tools)
        tool_map = self._request_tools(config)
        unit: _Unit | None = None
        # A call in the context whose tool has not returned. A barge-in can land
        # on the speech yielded before it, or cancel the tool itself.
        running: tuple[_Unit, Any] | None = None
        tally = _Tally()
        clock = _Clock(started=time.monotonic())
        retried = note = False
        followups = 0
        try:
            while True:
                contents = list(self._history)
                if note:
                    # On the retry's request only, and never into the context.
                    contents.append(self._retry_note_turn())
                    note = False
                tally.hops += 1
                request = config
                if followups == self._max_tool_hops:
                    # The budget is spent: this request may not call a tool, so
                    # the turn still ends in something the user hears.
                    logger.warning(
                        "turn: model={} reached max_tool_hops={}; the last request "
                        "may not call a tool",
                        self._model,
                        self._max_tool_hops,
                    )
                    request = self._answer_now_request(config)
                # The response called a tool the model needs the result of now.
                awaited = False
                # The response tried to call a tool, nothing ran, and nothing
                # real was called after it.
                stranded = False
                # This request's usage, as reported so far: a running total.
                hop_usage: ModelUsage | None = None
                hop_started = time.monotonic()
                hop_first: float | None = None
                try:
                    async for chunk in self._model_stream(contents, request):
                        clock.mark_open()
                        if hop_first is None:
                            hop_first = time.monotonic()
                        if chunk.usage is not None:
                            hop_usage = chunk.usage
                        speak: list[str] = []
                        for part in chunk.parts:
                            if unit is None:
                                unit = self._open_unit()
                            if part.kind == "call":
                                # Speech before a call goes out before its tool runs.
                                if speak:
                                    clock.mark_speak()
                                    for event in self._speak(unit, speak):
                                        yield event
                                    speak = []
                                self._extend_unit(unit, part.raw)
                                unit.called = True
                                running = (unit, part.raw)
                                name = self._call_name(part.call)
                                tool = tool_map.get(name)
                                tool_started = time.monotonic()
                                self._file(unit, await self._run(tool, part.call))
                                self._report(session, "tool", name, "", tool_started)
                                running = None
                                tally.calls += 1
                                if tool is not None and _needs_result_now(tool):
                                    tally.awaited += 1
                                    awaited = True
                                continue
                            self._extend_unit(unit, part.raw)
                            # Reasoning carries text that is not speech.
                            if part.kind == "text":
                                speak += unit.release(part.text)
                        finished, malformed = chunk.finished, chunk.malformed
                        if finished and unit is not None:
                            speak += unit.settle(malformed=malformed)
                        if speak and unit is not None:
                            clock.mark_speak()
                            for event in self._speak(unit, speak):
                                yield event
                        if unit is not None and unit.leaked and unit.speaking:
                            # The model began writing a call as text mid-speech.
                            # What went out stays said; nothing after it will be,
                            # so the speech ends now rather than when the
                            # response does.
                            logger.warning(
                                "turn: model={} wrote a function call as text after "
                                "speech began; the words before it were spoken and "
                                "none of the call was",
                                self._model,
                            )
                            yield SpeechEnd()
                            unit.speaking = False
                        if finished:
                            if unit is not None:
                                if unit.speaking:
                                    yield SpeechEnd()
                                stranded = self._close(unit) or stranded
                            elif malformed:
                                # A malformed call usually arrives with no parts
                                # at all, so it never opened a unit.
                                stranded = True
                            unit = None
                finally:
                    tally.add(hop_usage)
                    self._report(
                        session,
                        "model",
                        self._model,
                        self.provider,
                        hop_started,
                        first=hop_first,
                        counts=(hop_usage or ModelUsage()).counts(),
                    )
                if unit is not None:
                    # The stream ended without finishing. Close the unit anyway: a
                    # SpeechStart with no SpeechEnd is a wire violation.
                    speak = unit.settle(malformed=False)
                    if speak:
                        clock.mark_speak()
                        for event in self._speak(unit, speak):
                            yield event
                    if unit.speaking:
                        yield SpeechEnd()
                    stranded = self._close(unit) or stranded
                    unit = None
                if stranded and not retried:
                    logger.warning(
                        "turn: model={} wrote a function call as text or malformed; none "
                        "of the call was spoken and nothing ran — asking once more",
                        self._model,
                    )
                    retried = note = True
                    continue
                if stranded:
                    logger.warning(
                        "turn: model={} wrote a function call as text or malformed again; "
                        "the turn ends without it",
                        self._model,
                    )
                    break
                if not awaited or followups == self._max_tool_hops:
                    break
                followups += 1
        finally:
            # Never yield here — a barge-in closes this generator by throwing
            # GeneratorExit at a yield above, and an async generator that
            # yields while closing raises instead of tearing down.
            if running is not None:
                self._drop_unanswered([running])
            if unit is not None and unit.leaked is not False:
                # Cut while an opening was held, or while a leaked call was still
                # streaming: none of the call was heard.
                self._strip(unit)
            _log_turn(self._model, tally, clock)

    def _report(
        self,
        session: Session,
        kind: str,
        name: str,
        provider: str,
        started: float,
        *,
        first: float | None = None,
        counts: dict[str, int] | None = None,
    ) -> None:
        """Send one step that started at ``started`` and ends now, if Voqalize
        records them and this brain has not opted out. Never raises: the step is
        a record, not the call."""
        if not self._report_steps or not getattr(session, "can_report_steps", False):
            return
        now = time.monotonic()
        try:
            session.report_step(
                TurnStep(
                    kind=kind,
                    name=name,
                    provider=provider,
                    duration_ms=round((now - started) * 1000),
                    first_output_ms=None if first is None else round((first - started) * 1000),
                    counts=counts or {},
                )
            )
        except Exception:
            logger.exception("turn: model={} could not report a {} step", self._model, kind)

    def _speak(self, unit: _Unit, pieces: list[str]) -> Iterator[Speech]:
        """Released text as speech, opening the unit on its first piece.

        A plain generator, so the unit is enqueued for its finalize only once the
        consumer has taken the ``SpeechStart``: a barge-in that lands on that
        yield leaves nothing awaiting a finalize that will never come."""
        if not unit.speaking:
            yield SpeechStart()
            self._awaiting.append(unit)
            unit.speaking = True
        for piece in pieces:
            yield SpeechChunk(piece)

    def _close(self, unit: _Unit) -> bool:
        """Finish a unit; return whether the turn is stranded on a call that
        never ran.

        A leaked unit leaves the context. The user heard none of it, and a model
        that reads its own call-as-text back as something it said writes the
        next one the same way."""
        if unit.leaked:
            self._strip(unit)
        return unit.failed_call

    def _strip(self, unit: _Unit) -> None:
        """Take a call written as text out of the context, and keep what the unit
        said before it. A unit that said nothing leaves entirely."""
        if not unit.said:
            self._unsay(unit)
            return
        # The speech is in the context as the model's own, cut to what went out;
        # heard truth cuts it further when Voqalize reports what played. Calls,
        # thoughts and signatures keep their identity and their order.
        said = "".join(unit.said)
        kept: list[Any] = []
        placed = False
        for part in self._turn_parts(unit.content):
            if not self._part_text(part) or self._part_is_thought(part):
                kept.append(part)
            elif not placed:
                self._set_part_text(part, said)
                kept.append(part)
                placed = True
        self._set_turn_parts(unit.content, kept)

    def _unsay(self, unit: _Unit) -> None:
        """Take out everything a unit wrote except its real function calls, which
        ran and are answered. Its text, its thoughts and its signature-only parts
        go with it: none of it was heard, and a model turn with nothing left in
        it is not a turn."""
        kept = [p for p in self._turn_parts(unit.content) if self._part_is_call(p)]
        self._set_turn_parts(unit.content, kept)
        if not kept:
            self._history = [c for c in self._history if c is not unit.content]

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Callable[..., Any]]:
        """The tools the model may call, read once per turn.

        Bound ``async def`` methods, listed by hand::

            @property
            def tools(self):
                return [self.log_meal, self.show_glucose]

        A plain list of callables is what every model SDK and every agentic
        framework takes, so a brain's tools go where the brain goes and there is
        no decorator to learn to declare one. It is read per turn, so the list can
        depend on the user.

        **Every tool returns within** :data:`TOOL_BUDGET_MS`, and its result
        reaches the model with the next request, not this one. Mark the tools
        whose result the model needs to say this reply with
        :func:`needs_result_now`, and only those.

        **The method is the declaration.** Its name is the name the model calls,
        its docstring is the description the model reads, and its parameter is
        the schema. Nothing is declared twice. Take one pydantic model, or
        nothing; each layer says what else it accepts.

        The session is not a parameter, because the signature is the schema and
        the model would try to fill it. Read
        :attr:`~voqalize.sdk.Brain.session` instead.
        """
        return []

    async def _invoke_tool(
        self, tool: Callable[..., Any] | None, name: str, run: Callable[[], Awaitable[Any]]
    ) -> dict[str, Any]:
        """Run one call and return its response, timed against the budget.

        ``run`` calls ``tool`` with the arguments the layer built for it. A tool
        that raises answers ``{'error': …}``, which the model reads like any other
        result; a call to a tool that is not declared this turn answers the same
        way.
        """
        started = time.monotonic()
        response: dict[str, Any]
        if tool is None:
            response = {"error": f"there is no tool named {name!r}"}
        else:
            try:
                response = {"result": await run()}
            except Exception as exc:
                response = {"error": str(exc)}
        took = (time.monotonic() - started) * 1000
        if "error" in response:
            # The model will read this and may well tell the user it did the
            # thing. This line is the only place the failure shows on our side.
            logger.warning("tool {} failed: {}", name, response["error"])
        if took > TOOL_BUDGET_MS:
            logger.warning(
                "tool {}.{} took {}ms, over the {}ms budget; the user waited for it",
                type(self).__name__,
                name,
                round(took),
                TOOL_BUDGET_MS,
            )
        return response

    def _file(self, unit: _Unit, reply: Any) -> None:
        """Put a function response in the context, in the turn directly after the
        model turn that made the call.

        Directly after, by identity: content appended while the tool ran — from
        inside it, or from :meth:`append_note` on a screen event — lands after the
        responses, never between a call and its answer. The responses are a turn
        of their own, never merged with the user's words: a merged one once made
        the model answer *as* the user."""
        if unit.responses is None:
            unit.responses = self._new_results_turn()
            at = next(i for i, c in enumerate(self._history) if c is unit.content)
            self._history.insert(at + 1, unit.responses)
        self._set_turn_parts(unit.responses, [*self._turn_parts(unit.responses), reply])

    def _drop_unanswered(self, calls: list[tuple[_Unit, Any]]) -> None:
        """Take out calls whose response never came back.

        A barge-in can land after a call is in the context and before its tool
        returns — on the speech yielded ahead of it, or in the tool itself. A call
        with no response beside it is not a conversation a model API will accept
        on the next turn, so it leaves. Whatever the tool did before it was cut
        stands; the context records what completed.
        """
        for unit, part in calls:
            kept = [p for p in self._turn_parts(unit.content) if p is not part]
            self._set_turn_parts(unit.content, kept)
            if not kept:
                self._history = [c for c in self._history if c is not unit.content]

    # ─── Heard truth ────────────────────────────────────────────────────

    async def on_finalize(self, session: Session, fin: Finalize) -> None:
        """Rewrite the unit Voqalize just finished playing down to what the
        user actually heard.

        A unit this brain never opened is the greeting: `greet` returns a string
        the SDK speaks, so the only record of it anywhere is what comes back
        here — already heard-truth, already cut to the delivered prefix if the
        user talked over it. Without this the model does not know it greeted,
        and asks its opening question a second time.
        """
        if not self._awaiting:
            if fin.heard:
                self._history.append(self._new_model_turn([self._new_text_part(fin.heard)]))
            return
        self._reconcile(self._awaiting.popleft(), fin.heard)

    def _reconcile(self, unit: _Unit, heard: str) -> None:
        """Collapse a unit's text down to ``heard``, in place.

        Non-text parts — function calls, thoughts, the signatures and reasoning
        items a provider wants handed back — keep their identity and their order;
        only spoken text is replaced, by the first text part, and later text parts
        go because they were generated and never delivered. A unit left with
        nothing leaves the context, since a model turn with no parts is not a turn.
        """
        kept: list[Any] = []
        placed = False
        for part in self._turn_parts(unit.content):
            if not self._part_text(part):
                kept.append(part)
            elif heard and not placed:
                self._set_part_text(part, heard)
                kept.append(part)
                placed = True
        self._set_turn_parts(unit.content, kept)
        if not kept:
            self._history = [c for c in self._history if c is not unit.content]

    # ─── Plumbing ───────────────────────────────────────────────────────

    def _open_unit(self) -> _Unit:
        """A model turn appended to history now, filled as the stream arrives —
        so an interruption leaves behind exactly what had been generated when it
        landed, ready to be cut down to what was heard.

        Not yet awaiting a finalize: a response that only calls a tool belongs in
        the context but was never played, so nothing will be reported for it.
        :meth:`respond` enqueues the unit when it opens speech.
        """
        unit = _Unit(self._new_model_turn([]))
        self._history.append(unit.content)
        return unit

    def _extend_unit(self, unit: _Unit, part: Any) -> None:
        self._set_turn_parts(unit.content, [*self._turn_parts(unit.content), part])

    # ─── The provider layer ─────────────────────────────────────────────
    #
    # Everything below is the layer's. Each is one small question about the
    # provider's own types, or the one call to its API.

    def _new_user_turn(self, text: str) -> M:
        """A user turn holding ``text``."""
        raise NotImplementedError

    def _new_model_turn(self, parts: list[Any]) -> M:
        """A model turn holding ``parts``."""
        raise NotImplementedError

    def _new_results_turn(self) -> M:
        """An empty turn to hold function responses."""
        raise NotImplementedError

    def _retry_note_turn(self) -> M:
        """The note the one retry carries, on that request only."""
        return self._new_user_turn(_RETRY_TEXT)

    def _turn_parts(self, turn: M) -> list[Any]:
        """The parts of ``turn``, in order."""
        raise NotImplementedError

    def _set_turn_parts(self, turn: M, parts: list[Any]) -> None:
        """Replace the parts of ``turn``, in place."""
        raise NotImplementedError

    def _new_text_part(self, text: str) -> Any:
        """A text part holding ``text``."""
        raise NotImplementedError

    def _part_text(self, part: Any) -> str:
        """The text ``part`` carries, or ``""``."""
        raise NotImplementedError

    def _set_part_text(self, part: Any, text: str) -> None:
        """Replace the text of a text part, in place."""
        raise NotImplementedError

    def _part_is_thought(self, part: Any) -> bool:
        """Whether ``part`` is reasoning."""
        raise NotImplementedError

    def _part_is_call(self, part: Any) -> bool:
        """Whether ``part`` is a function call."""
        raise NotImplementedError

    def _turn_request(self, tools: ToolChoice | None) -> R:
        """This turn's request settings: the tools, limited by ``tools``."""
        raise NotImplementedError

    def _answer_now_request(self, request: R) -> R:
        """``request`` with every tool still declared and none callable."""
        raise NotImplementedError

    def _request_tools(self, request: R) -> dict[str, Callable[..., Any]]:
        """The tools ``request`` declares, by the name the model calls."""
        raise NotImplementedError

    def _call_name(self, call: Any) -> str:
        """The name a function call asks for."""
        raise NotImplementedError

    async def _run(self, tool: Callable[..., Any] | None, call: Any) -> Any:
        """Run one call — through :meth:`_invoke_tool` — and return its response part."""
        raise NotImplementedError

    def _model_stream(self, contents: list[M], request: R) -> AsyncIterator[ModelChunk]:
        """One request to the model, as :class:`ModelChunk` values."""
        raise NotImplementedError
