"""A Gemini-backed Brain: history, streaming, and the tools the model calls.

    from google import genai
    from voqalize.sdk.gemini import GeminiBrain

    class Concierge(GeminiBrain):
        def __init__(self) -> None:
            super().__init__(client=genai.Client(), system_instruction="You are …")

        async def greet(self, session):
            return "Hi! What can I do for you?"

        @property
        def tools(self):
            return [self.open_booking]

        async def open_booking(self, args: OpenBooking) -> str:
            "Put the booking form on screen."
            self.session.dispatch(args)
            return "ok"

Host it the same way as any other brain — :func:`voqalize.sdk.run_session` from
your own WebSocket route, or :func:`voqalize.sdk.serve` over the Cortex relay.

Install with ``pip install voqalize-agent-sdk[gemini]``. Nothing in
``voqalize.sdk`` imports this module, so the core SDK stays free of
``google-genai``.

**The model owns its tools; we own the voice.** :attr:`~GeminiBrain.tools` is a
plain list of bound ``async def`` methods, and the method is the declaration — its
docstring is the description the model reads, its single pydantic parameter is the
schema. From there google-genai is on its own: it runs the tools, feeds itself the
responses and hops again, so a turn that calls a tool and then speaks about the
result is one call from here, not a loop. We take the record it kept
(``automatic_function_calling_history``) rather than interposing to make our own.

**The brain owns the context, and what it records is what was heard.** Each
unit of speech goes into the context as it streams, then
:meth:`~voqalize.sdk.Brain.on_finalize` rewrites it to the delivered prefix. A
reply that generated three sentences and was cut after one is remembered as one —
which is the only version the user and the model can both agree on.
"""

from __future__ import annotations

import functools
import inspect
import os
import re
import time
from collections import deque
from collections.abc import AsyncGenerator, Callable, Iterator
from dataclasses import dataclass, field
from typing import Any, get_type_hints

from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel

from .brain import Brain, Session
from .events import Finalize, Speech, SpeechChunk, SpeechEnd, SpeechStart, UserMessage

__all__ = ["DEFAULT_MODEL", "VOICE_THINKING", "GeminiBrain"]

# Overridable because free-tier Gemini quotas are per model — when one model's
# daily bucket is spent (an eval run, a long demo day), pointing the process at a
# sibling model is the difference between "it works" and "come back tomorrow".
DEFAULT_MODEL = os.environ.get("VOQAL_GEMINI_MODEL", "gemini-3.5-flash")

# The least thinking this model allows, for lowest voice latency: on a voice turn
# a reasoning budget is spent in silence the user sits through, and the thought
# parts are never spoken, so the cost has no audible half at all.
#
# BOTH HALVES OF THIS LINE ARE MODEL-SPECIFIC — measure, do not assume, when you
# change DEFAULT_MODEL. Three ways it bites, each verified against the live API on
# 2026-08-14, and all three were hit in one afternoon getting to this pair:
#
#   - The KNOB moved. `thinking_budget=0` is what the 3.1 models took; 3.5+ reject
#     it with a bare `400 INVALID_ARGUMENT` ("Request contains an invalid
#     argument") that names no field.
#   - The FLOOR moved. MINIMAL works here, and `gemini-3.7-flash` refuses it
#     ("Thinking level MINIMAL is not supported for this model") — LOW is that
#     model's floor and still spends ~275 thought tokens, so it has no
#     zero-thinking setting at all, and its turns ran ~2x this one's.
#   - A LEVEL A MODEL ACCEPTS IS NOT ONE IT ACTS AT. `gemini-3.5-flash-lite` takes
#     MINIMAL happily, then calls `open_itinerary` on only 9 of 15 identical
#     travel turns — it asks "which trip?" instead of driving the screen (LOW:
#     11/15, and open_dashboard drops to 12/15; MEDIUM fixes it at ~1s/turn; a
#     prompt nudge made it worse, 1/15). Clean build, green unit tests, and a
#     Playwright voice smoke suite is what caught it.
#
# So when you move models: probe the knob, then re-run the tool-call check, then
# read the think= numbers on a real deployed call — a one-shot TTFT probe
# understates a turn that carries history and screen grounding.
VOICE_THINKING = types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL)

# How a function call the model wrote out as TEXT begins. At MINIMAL thinking a
# Gemini model occasionally emits its call as words instead of as a
# `function_call` part — `certain_tool_call\n  "name": "default_api:read_screen"`
# was one, on a live travel session — and text is speech, so the user heard it
# read aloud and no tool ran. Ordinary speech, in any language, opens with none of
# these; a unit that opens with one is held until it is known, and never spoken.
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
_RETRY_NOTE = types.Content(
    role="user",
    parts=[
        types.Part(
            text=(
                "Your last reply tried to call a function but wrote the call as text, or "
                "wrote it malformed. No function ran, and the user heard none of that "
                "text: only the words before it, if there were any, which are above as "
                "your own. Make the call through function calling now, or answer in "
                "speech, and do not say again what was already said. Do not mention "
                "this note."
            )
        )
    ],
)


@dataclass
class _Unit:
    """One model turn, held by identity while it is still being written.

    ``types.Content`` is a pydantic model, so two of them compare equal whenever
    their fields do — and two freshly opened, still-empty turns always do. The
    queue and the context therefore track *this*, never the content itself.

    It also holds back the unit's opening while that opening could still be a
    function call the model wrote out as text — see :func:`_looks_like_call` —
    and, once it is speaking, the short tail that could still be the start of one
    — see :data:`_SPOKEN_CALL`.
    """

    content: types.Content
    #: Text not yet spoken, because the opening is still undecided.
    held: list[str] = field(default_factory=lambda: list[str]())
    #: ``None`` while undecided, ``False`` once it is speech, ``True`` once it is
    #: a function call written out as text — from its opening, or from a point
    #: after speech began — and nothing more of it will be spoken.
    leaked: bool | None = None
    #: The hop ended in ``MALFORMED_FUNCTION_CALL``: the call it tried to make
    #: never ran.
    malformed: bool = False
    #: The model made a real function call in this unit, so AFC hops again.
    called: bool = False
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

        An opening still undecided when the hop ends is speech, and so is a held
        tail: the model stopped writing, and nothing it wrote is a call. A hop
        that ended in ``MALFORMED_FUNCTION_CALL`` speaks nothing more, whatever
        it held."""
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


@dataclass
class _Clock:
    """When a turn's two moments happened, relative to asking for it.

    ``speak`` is the one the user experiences: everything before it is silence
    they are sitting in. It is not the same as ``open`` — a turn that calls a tool
    first starts streaming promptly and still says nothing for another round trip,
    which is the shape a tool-heavy turn has and the reason both are recorded.

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

    def _since(self, at: float | None) -> str:
        return "none" if at is None else f"{round((at - self.started) * 1000)}ms"

    def __str__(self) -> str:
        return (
            f"open={self._since(self.open)} speak={self._since(self.speak)} "
            f"total={self._since(time.monotonic())}"
        )


def _log_turn(
    model: str,
    hops: int,
    usage: types.GenerateContentResponseUsageMetadata | None,
    clock: _Clock,
) -> None:
    """What one turn cost, in tokens and in silence.

    Under automatic function calling a turn is several requests, each re-sending
    the whole context plus the hop before it, so ``prompt`` here is the **last and
    largest** of them and ``hops`` says how many there were. A context quietly
    filling up with screen snapshots shows as a rising prompt long before it shows
    as a slow turn, and that is a thing we have already had to reconstruct from a
    production transcript once.

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
    if usage is None:
        logger.info("turn: model={} hops={} {} — no usage reported", model, hops, clock)
        return
    logger.info(
        "turn: model={} hops={} {} prompt={} cached={} output={} thoughts={}",
        model,
        hops,
        clock,
        usage.prompt_token_count or 0,
        usage.cached_content_token_count or 0,
        usage.candidates_token_count or 0,
        usage.thoughts_token_count or 0,
    )


class GeminiBrain(Brain):
    """Base for a Gemini-backed brain. Override the prompt, the greeting and
    :attr:`tools`; the turn shape and the context come from here. The tools
    themselves are run by google-genai, not by us."""

    def __init__(
        self,
        *,
        client: genai.Client,
        system_instruction: str,
        model: str = DEFAULT_MODEL,
        max_tool_hops: int = 6,
    ) -> None:
        self._client = client
        self._model = model
        self._config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            thinking_config=VOICE_THINKING,
        )
        # `ignore_call_history` is left at its default, off: that history is the
        # record of what the model called and what it was told back, and taking it
        # is what lets us stay out of the tool loop entirely.
        self._afc = types.AutomaticFunctionCallingConfig(maximum_remote_calls=max_tool_hops)

        # The conversation, in Gemini's own type, on purpose. What a brain owes
        # Voqalize is provider-neutral; what a brain says to a model is the
        # provider's, and a wrapper type in between is one more thing that has to
        # keep up with Gemini. :meth:`append_to_context` is the way in.
        self._history: list[types.Content] = []
        # Units still awaiting their heard truth, in the order Voqalize will
        # report them. Only units that opened a *speech* unit are here: Voqalize
        # finalizes what it played, and a hop that only called a tool played
        # nothing.
        self._awaiting: deque[_Unit] = deque()

    # ─── The turn ───────────────────────────────────────────────────────

    def append_to_context(self, content: types.Content) -> None:
        """Add to the conversation the model sees, in Gemini's own type.

        For context the app knows and the conversation does not — typically what
        the person just did on screen, arriving at
        :meth:`~voqalize.sdk.Brain.on_rtvi` as a typed
        :class:`~voqalize.sdk.app_events.AppEvent`, which takes no floor and
        starts no turn::

            async def on_rtvi(self, session, msg):
                match EVENTS.parse(msg):
                    case QuantitySet() as e:
                        self.append_to_context(
                            types.Content(
                                role="user",
                                parts=[types.Part(text=f"HE SET {e.item_id} TO {e.quantity}")],
                            )
                        )

        Append the **act**, not the screen. One named sentence is what a model can
        act on; a whole-state blob appended on a debounce is a context full of
        near-identical copies, none of them dated, and a model reasoning from
        whichever it noticed.

        A ``Content`` is whatever Gemini takes, so handing the model a screenshot
        or a PDF is this same call with a different part. The role must be
        ``user``: the model's side of a conversation is written by the model.

        It appends **immediately, once, where you call it**. Nothing here
        debounces, diffs or re-renders — what to append and when is yours, and
        this method will not guess which of ten identical screens you meant. Every
        request is the previous one plus what happened since, which is what makes
        it cacheable and what stops the context changing under a turn already in
        flight.

        Calling it mid-turn is safe. The append can land between a tool call and
        its result; Gemini accepts that, and the model finishes the call before it
        attends to what arrived. Reconciliation is untouched — appended content is
        not a speech unit, so it is never rewritten with heard text and never
        dropped as an unanswered call.
        """
        if content.role != "user":
            raise ValueError(
                f"append_to_context takes user content, got role={content.role!r}. "
                "The model's side of a conversation is written by the model."
            )
        self._history.append(content)

    def on_user_message(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]:
        self._history.append(types.Content(role="user", parts=[types.Part(text=msg.text)]))
        return self.respond(session)

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """Stream one turn, however many tool hops it takes.

        google-genai runs the tools and loops for us, so this is a single call
        whose stream spans every hop. Two rules turn that stream into speech:

        * a unit **closes** on ``finish_reason``, which arrives on the last chunk
          of every hop, and on the stream ending;
        * a unit **opens** on the first spoken text after a close — lazily, so a
          hop that only calls a tool never opens one at all. Opening a unit
          eagerly per hop is what used to emit an empty ``SpeechStart`` /
          ``SpeechEnd`` pair around a silent tool call.

        The context is written from both sides of the seam and neither alone:
        the **order** comes from the stream, where every part arrives in the order
        the model produced it, and the tool **responses** come from AFC's own
        record, which is the only place they exist.

        The catch, and it is inherent: the contents are handed over once, so
        heard truth applies per *turn*, not per hop. A turn is a couple of seconds,
        and a unit's heard truth is not known until it has finished playing anyway
        — which is usually after the whole turn generated.

        **A function call written as text is never spoken.** At low thinking a
        model sometimes writes its call out as words (``default_api:read_screen``,
        ``{"name": …}``) instead of making it. That text would be read aloud and
        nothing would run. So a unit's opening is held only while it could still
        be one: a sentence that opens with a letter, a digit or Devanagari
        passes on its first piece, and an ambiguous opening waits one more piece,
        or until its hop ends. A unit that is a call written as text, or a hop
        that ends in ``MALFORMED_FUNCTION_CALL``, speaks nothing and leaves the
        context. If the turn ends waiting on it, the request goes once more, with
        a note that is not kept in the context.

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
        """
        config = self._turn_config()
        calls: list[tuple[_Unit, types.Part]] = []
        answered = 0
        unit: _Unit | None = None
        usage: types.GenerateContentResponseUsageMetadata | None = None
        hops = 0
        clock = _Clock(started=time.monotonic())
        try:
            for attempt in range(2):
                contents = list(self._history)
                if attempt:
                    contents.append(_RETRY_NOTE)
                # The head of AFC's record is what we just handed it, so folding
                # starts past our own contents.
                folded = len(contents)
                # The turn is waiting on a call that never ran, and nothing since
                # has spoken or called.
                stranded = False
                async for chunk in await self._client.aio.models.generate_content_stream(
                    model=self._model, contents=contents, config=config
                ):
                    clock.mark_open()
                    folded, taken = self._fold_results(chunk, folded)
                    answered += taken
                    if chunk.usage_metadata is not None:
                        usage = chunk.usage_metadata
                    speak: list[str] = []
                    for part in _parts(chunk):
                        if unit is None:
                            unit = self._open_unit()
                        self._extend_unit(unit, part)
                        if part.function_call:
                            calls.append((unit, part))
                            unit.called, stranded = True, False
                        # `thought` parts carry text that is reasoning, not speech.
                        if part.text and not part.thought:
                            speak += unit.release(part.text)
                    finished, malformed = _finished(chunk), _malformed(chunk)
                    if finished and unit is not None:
                        speak += unit.settle(malformed=malformed)
                    if speak and unit is not None:
                        clock.mark_speak()
                        stranded = False
                        for event in self._speak(unit, speak):
                            yield event
                    if unit is not None and unit.leaked and unit.speaking:
                        # The model began writing a call as text mid-speech. What
                        # went out stays said; nothing after it will be, so the
                        # speech ends now rather than when the hop does.
                        logger.warning(
                            "turn: model={} wrote a function call as text after speech "
                            "began; the words before it were spoken and none of the call was",
                            self._model,
                        )
                        yield SpeechEnd()
                        unit.speaking = False
                    if finished:
                        hops += 1
                        if unit is not None:
                            if unit.speaking:
                                yield SpeechEnd()
                            stranded = self._close(unit) or stranded
                        elif malformed:
                            # A malformed call usually arrives with no parts at
                            # all, so it never opened a unit.
                            stranded = True
                        unit = None
                if unit is not None:
                    # The stream ended without a finish_reason. Close the unit
                    # anyway: a SpeechStart with no SpeechEnd is a wire violation.
                    speak = unit.settle(malformed=False)
                    if speak:
                        clock.mark_speak()
                        stranded = False
                        for event in self._speak(unit, speak):
                            yield event
                    if unit.speaking:
                        yield SpeechEnd()
                    stranded = self._close(unit) or stranded
                    unit = None
                self._drop_unanswered(calls[answered:])
                calls, answered = [], 0
                if not stranded:
                    break
                logger.warning(
                    "turn: model={} wrote a function call as text or malformed; none of the "
                    "call was spoken and nothing ran — {}",
                    self._model,
                    "asking once more" if attempt == 0 else "the turn ends without it",
                )
        finally:
            # Never yield here — a barge-in closes this generator by throwing
            # GeneratorExit at the yield above, and an async generator that
            # yields while closing raises instead of tearing down.
            self._drop_unanswered(calls[answered:])
            if unit is not None and unit.leaked is not False:
                # Cut while an opening was held, or while a leaked call was still
                # streaming: none of the call was heard.
                self._strip(unit)
            _log_turn(self._model, hops, usage, clock)

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
        kept: list[types.Part] = []
        placed = False
        for part in unit.content.parts or []:
            if not part.text or part.thought:
                kept.append(part)
            elif not placed:
                part.text = said
                kept.append(part)
                placed = True
        unit.content.parts = kept

    def _unsay(self, unit: _Unit) -> None:
        """Take out everything a unit wrote except its real function calls, which
        AFC ran and answers. Its text, its thoughts and its signature-only parts
        go with it: none of it was heard, and a model turn with nothing left in
        it is not a turn."""
        unit.content.parts = [p for p in unit.content.parts or [] if p.function_call]
        if not unit.content.parts:
            self._history = [c for c in self._history if c is not unit.content]

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Callable[..., Any]]:
        """The tools the model may call, read once per turn.

        Bound ``async def`` methods, listed by hand::

            @property
            def tools(self):
                return [self.log_meal, self.show_glucose]

        A plain list of callables is what google-genai takes — and ADK, and every
        other agentic framework — so a brain's tools go where the brain goes and
        there is no decorator to learn. It is read per turn, so the list can
        depend on the user.

        **The method is the declaration.** Its name is the name the model calls,
        its docstring is the description the model reads, and its single pydantic
        parameter is the schema. Nothing is declared twice.

        Take one model, or nothing at all. Not because flatness is unsupported —
        a flat ``str``, ``int`` or ``list[str]`` runs — but because a flat
        parameter is the one google-genai never parses. It checks each against
        ``isinstance`` and coerces nothing, so a bare ``Literal`` raises outright
        (``isinstance`` refuses a subscripted generic) and a bare ``Enum``,
        ``date``, ``Decimal`` or ``UUID`` is rejected as the JSON string it still
        is. Both land as an ``{'error': …}`` the model cheerfully papers over. A
        model parameter is the only annotation that gets validated, which is why
        the same ``Literal`` is safe inside one — see
        ``tests/unit/test_flat_parameters.py``, which pins all of it upstream.

        The session is not a parameter, because the signature is the schema and
        the model would try to fill it. Read
        :attr:`~voqalize.sdk.Brain.session` instead.
        """
        return []

    def _turn_config(self) -> types.GenerateContentConfig:
        """This turn's config, carrying this turn's tools."""
        tools = self.tools
        if not tools:
            return self._config
        return self._config.model_copy(
            update={
                "tools": [_ready(fn) for fn in tools],
                "automatic_function_calling": self._afc,
            }
        )

    def _fold_results(self, chunk: types.GenerateContentResponse, folded: int) -> tuple[int, int]:
        """Move AFC's own function responses into the context as they appear.

        ``automatic_function_calling_history`` is the record google-genai keeps of
        the turn it is running: the contents we handed it, then each hop's calls
        and the responses it fed itself. It grows *between* hops, so a hop's
        responses reach us on the first chunk of the next one — which is exactly
        where they belong in history, after the unit that called them and before
        the unit that answers.

        Only the responses are taken. The calls are already in the context,
        verbatim from the stream, thought signatures and all.
        """
        record = chunk.automatic_function_calling_history or []
        if len(record) <= folded:
            return folded, 0
        taken = 0
        for content in record[folded:]:
            parts = [p for p in (content.parts or []) if p.function_response]
            if not parts:
                continue
            self._history.append(types.Content(role="user", parts=parts))
            taken += len(parts)
            for part in parts:
                response = part.function_response
                if (
                    response
                    and isinstance(response.response, dict)
                    and "error" in response.response
                ):
                    # google-genai hands the model `{'error': ...}` and the model
                    # will tell the user it did the thing. This is the only
                    # place that failure is visible on our side of the seam.
                    logger.warning("tool {} failed: {}", response.name, response.response["error"])
        return len(record), taken

    def _drop_unanswered(self, calls: list[tuple[_Unit, types.Part]]) -> None:
        """Take out calls whose response never came back.

        A barge-in cuts the stream, and a hop's responses only reach us on the
        chunk after it — so a call at the cut may have no response and never will.
        A ``function_call`` with no ``function_response`` beside it is not a
        conversation Gemini will accept on the next turn, so it leaves. Whether
        the tool actually ran is not ours to know: the context records what
        completed, and the side effect stands either way.
        """
        for unit, part in calls:
            kept = [p for p in (unit.content.parts or []) if p is not part]
            unit.content.parts = kept
            if not kept:
                self._history = [c for c in self._history if c is not unit.content]

    # ─── Context ────────────────────────────────────────────────────────

    @property
    def system_instruction(self) -> str:
        """The prompt every call carries. Settable from
        :meth:`~voqalize.sdk.Brain.on_session_start`, where the facts that are
        true for this user and no other — who they are, what they are calling
        about, what your system already knows — are finally in hand. Setting it
        replaces the prompt for the rest of the session; the tools and the model
        stay as constructed.
        """
        return str(self._config.system_instruction or "")

    @system_instruction.setter
    def system_instruction(self, text: str) -> None:
        self._config = self._config.model_copy(update={"system_instruction": text})

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
                self._history.append(
                    types.Content(role="model", parts=[types.Part(text=fin.heard)])
                )
            return
        self._reconcile(self._awaiting.popleft(), fin.heard)

    def _reconcile(self, unit: _Unit, heard: str) -> None:
        """Collapse a unit's text down to ``heard``, in place.

        Non-text parts — function calls, thoughts, the signatures Gemini 3 wants
        handed back — keep their identity and their order; only spoken text is
        replaced, by the first text part, and later text parts go because they
        were generated and never delivered. A unit left with nothing leaves the
        context, since a model turn with no parts is not a turn.
        """
        kept: list[types.Part] = []
        placed = False
        for part in unit.content.parts or []:
            if not part.text:
                kept.append(part)
            elif heard and not placed:
                part.text = heard
                kept.append(part)
                placed = True
        unit.content.parts = kept
        if not kept:
            self._history = [c for c in self._history if c is not unit.content]

    # ─── Plumbing ───────────────────────────────────────────────────────

    def _open_unit(self) -> _Unit:
        """A model turn appended to history now, filled as the stream arrives —
        so an interruption leaves behind exactly what had been generated when it
        landed, ready to be cut down to what was heard.

        Not yet awaiting a finalize: a hop that only calls a tool belongs in the
        context but was never played, so nothing will be reported for it.
        :meth:`respond` enqueues the unit when it opens speech.
        """
        unit = _Unit(types.Content(role="model", parts=[]))
        self._history.append(unit.content)
        return unit

    def _extend_unit(self, unit: _Unit, part: types.Part) -> None:
        if unit.content.parts is None:
            unit.content.parts = []
        unit.content.parts.append(part)


def _parts(chunk: types.GenerateContentResponse) -> list[types.Part]:
    """Every part of one chunk, verbatim so thought signatures survive the
    round-trip into history."""
    out: list[types.Part] = []
    for candidate in chunk.candidates or []:
        content = candidate.content
        out.extend((content.parts or []) if content else [])
    return out


def _ready(fn: Callable[..., Any]) -> Callable[..., Any]:
    """One tool, as google-genai needs to receive it: a plain function, with its
    annotations resolved.

    ``async def`` is required. AFC runs a synchronous tool on a worker thread, off
    the loop, where the first ``await`` a tool grows is a rewrite.

    **A bound method must not cross this line.** google-genai deep-copies the
    config it is handed — once on entry and again on every AFC hop — and
    ``copy.deepcopy`` of a bound method copies ``__self__`` with it, by definition
    (``copy._deepcopy_method``). The tools it then calls belong to a *clone* of the
    brain: ``self.session.dispatch`` reaching nothing, the context written to an
    object no one reads, the model told ``ok``, and not one thing on the wire to
    say so. Ours happens to hold a ``genai.Client``, whose lock cannot be copied at
    all, so we got a crash instead of that silence — the only luck in it. A plain
    function is atomic to ``deepcopy``, so this closure is what we hand over and
    the brain stays here.

    That is the whole job. The wrapper does not run a loop, collect a result or
    catch an exception; AFC still owns the turn.

    The model parameter is rebuilt for the same reason, one level in. Postponed
    annotations leave a model's *fields* as ``ForwardRef`` too, and pydantic
    resolves them lazily — on the first validation, which is long after the
    declaration is built. google-genai reads the fields directly, so a model
    naming a class defined further down the brain module fails to declare with a
    ``ValueError`` naming the parameter, and the tool the developer wrote never
    reaches the turn. ``model_rebuild`` is a no-op on a model that is already
    complete.

    Resolving the annotations onto the wrapper is the second half. Brain modules
    use ``from __future__ import annotations``, so a method's annotations are
    strings, and google-genai reads two different things: ``get_type_hints`` to
    build the *declaration*, which resolves them, and ``inspect.signature`` to
    build the *call*, which does not. Left alone, a tool declares a perfect schema
    and then raises on every call — and the error goes to the model, which narrates
    it as success. Both go on the closure, so the method the developer wrote is
    handed over unread and comes back unchanged.
    """
    if not inspect.iscoroutinefunction(fn):
        raise TypeError(
            f"tool {getattr(fn, '__name__', fn)!r} must be `async def`. A sync tool runs on a "
            "worker thread, off the loop, so the first self.session.dispatch(...) it grows "
            "reaches a loop that is not running. Make it `async def` — the body needs "
            "no other change."
        )

    @functools.wraps(fn)
    async def tool(*args: Any, **kwargs: Any) -> Any:
        return await fn(*args, **kwargs)

    tool.__annotations__ = get_type_hints(fn)
    tool.__signature__ = inspect.signature(fn, eval_str=True)  # pyright: ignore[reportFunctionMemberAccess]
    for annotation in tool.__annotations__.values():
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            annotation.model_rebuild()
    return tool


def _finished(chunk: types.GenerateContentResponse) -> bool:
    """True on the last chunk of a hop. google-genai yields every chunk of every
    hop through one iterator, so this is the only boundary between them."""
    return any(c.finish_reason is not None for c in chunk.candidates or [])


def _malformed(chunk: types.GenerateContentResponse) -> bool:
    """True when the hop ended because the model's function call did not parse.
    AFC finds no call to run, so the stream just ends — with nothing said."""
    return any(
        c.finish_reason == types.FinishReason.MALFORMED_FUNCTION_CALL
        for c in chunk.candidates or []
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
