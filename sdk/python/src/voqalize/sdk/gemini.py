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

**The brain owns the transcript, and the transcript is what was heard.** Each
unit of speech goes into the transcript as it streams, then
:meth:`~voqalize.sdk.Brain.on_finalize` rewrites it to the delivered prefix. A
reply that generated three sentences and was cut after one is remembered as one —
which is the only version the caller and the model can both agree on.
"""

from __future__ import annotations

import functools
import inspect
import os
from collections import deque
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from typing import Any, get_type_hints

from google import genai
from google.genai import types
from loguru import logger

from .brain import Brain, Session
from .events import Chunk, Finalize, Speech, SpeechEnd, SpeechStart, UserMessage

__all__ = ["DEFAULT_MODEL", "VOICE_THINKING", "GeminiBrain"]

# Overridable because free-tier Gemini quotas are per model — when one model's
# daily bucket is spent (an eval run, a long demo day), pointing the process at a
# sibling model is the difference between "it works" and "come back tomorrow".
DEFAULT_MODEL = os.environ.get("VOQAL_GEMINI_MODEL", "gemini-3.5-flash")

# The least thinking this model allows, for lowest voice latency: on a voice turn
# a reasoning budget is spent in silence the caller sits through, and the thought
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


@dataclass
class _Unit:
    """One model turn, held by identity while it is still being written.

    ``types.Content`` is a pydantic model, so two of them compare equal whenever
    their fields do — and two freshly opened, still-empty turns always do. The
    queue and the transcript therefore track *this*, never the content itself.
    """

    content: types.Content


class GeminiBrain(Brain):
    """Base for a Gemini-backed brain. Override the prompt, the greeting and
    :attr:`tools`; the turn shape and the transcript come from here. The tools
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

        For context the app knows and the conversation does not — typically the
        live screen state pushed to :meth:`~voqalize.sdk.Brain.on_rtvi`, which
        takes no floor and starts no turn::

            async def on_rtvi(self, session, msg):
                if msg.data.get("t") == "state_sync":
                    self.append_to_context(
                        types.Content(
                            role="user",
                            parts=[types.Part(text="ON SCREEN: " + json.dumps(msg.data["d"]))],
                        )
                    )

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

        The transcript is written from both sides of the seam and neither alone:
        the **order** comes from the stream, where every part arrives in the order
        the model produced it, and the tool **responses** come from AFC's own
        record, which is the only place they exist.

        The catch, and it is inherent: the contents are handed over once, so
        heard truth applies per *turn*, not per hop. A turn is a couple of seconds,
        and a unit's heard truth is not known until it has finished playing anyway
        — which is usually after the whole turn generated.
        """
        contents = list(self._history)
        # The head of AFC's record is what we just handed it, so folding starts
        # past our own contents.
        folded = len(contents)
        calls: list[tuple[_Unit, types.Part]] = []
        answered = 0
        unit: _Unit | None = None
        speaking = False
        try:
            async for chunk in await self._client.aio.models.generate_content_stream(
                model=self._model, contents=contents, config=self._turn_config()
            ):
                folded, taken = self._fold_results(chunk, folded)
                answered += taken
                for part in _parts(chunk):
                    if unit is None:
                        unit = self._open_unit()
                    self._extend_unit(unit, part)
                    if part.function_call:
                        calls.append((unit, part))
                    # `thought` parts carry text that is reasoning, not speech.
                    if part.text and not part.thought:
                        if not speaking:
                            yield SpeechStart()
                            self._awaiting.append(unit)
                            speaking = True
                        yield Chunk(part.text)
                if _finished(chunk):
                    if speaking:
                        yield SpeechEnd()
                    unit, speaking = None, False
            if speaking:
                # The stream ended without a finish_reason. Close the unit anyway:
                # a SpeechStart with no SpeechEnd is a wire violation.
                yield SpeechEnd()
        finally:
            # Never yield here — a barge-in closes this generator by throwing
            # GeneratorExit at the yield above, and an async generator that
            # yields while closing raises instead of tearing down.
            self._drop_unanswered(calls[answered:])

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
        depend on the caller.

        **The method is the declaration.** Its name is the name the model calls,
        its docstring is the description the model reads, and its single pydantic
        parameter is the schema. Nothing is declared twice.

        Take one model, or nothing at all. Flat parameters are not supported:
        google-genai builds a correct schema for a bare ``Literal`` and then fails
        to *execute* the call, handing the model an error it will cheerfully paper
        over. A model wraps the same field safely.

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
        """Move AFC's own function responses into the transcript as they appear.

        ``automatic_function_calling_history`` is the record google-genai keeps of
        the turn it is running: the contents we handed it, then each hop's calls
        and the responses it fed itself. It grows *between* hops, so a hop's
        responses reach us on the first chunk of the next one — which is exactly
        where they belong in history, after the unit that called them and before
        the unit that answers.

        Only the responses are taken. The calls are already in the transcript,
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
                    # will tell the caller it did the thing. This is the only
                    # place that failure is visible on our side of the seam.
                    logger.warning("tool {} failed: {}", response.name, response.response["error"])
        return len(record), taken

    def _drop_unanswered(self, calls: list[tuple[_Unit, types.Part]]) -> None:
        """Take out calls whose response never came back.

        A barge-in cuts the stream, and a hop's responses only reach us on the
        chunk after it — so a call at the cut may have no response and never will.
        A ``function_call`` with no ``function_response`` beside it is not a
        conversation Gemini will accept on the next turn, so it leaves. Whether
        the tool actually ran is not ours to know: the transcript records what
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
        true for this caller and no other — who they are, what they are calling
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
        caller actually heard.

        A unit this brain never opened is the greeting: `greet` returns a string
        the SDK speaks, so the only record of it anywhere is what comes back
        here — already heard-truth, already cut to the delivered prefix if the
        caller talked over it. Without this the model does not know it greeted,
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
        transcript, since a model turn with no parts is not a turn.
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
        transcript but was never played, so nothing will be reported for it.
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
    brain: ``self.session.dispatch`` reaching nothing, the transcript written to an
    object no one reads, the model told ``ok``, and not one thing on the wire to
    say so. Ours happens to hold a ``genai.Client``, whose lock cannot be copied at
    all, so we got a crash instead of that silence — the only luck in it. A plain
    function is atomic to ``deepcopy``, so this closure is what we hand over and
    the brain stays here.

    That is the whole job. The wrapper does not run a loop, collect a result or
    catch an exception; AFC still owns the turn.

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
    return tool


def _finished(chunk: types.GenerateContentResponse) -> bool:
    """True on the last chunk of a hop. google-genai yields every chunk of every
    hop through one iterator, so this is the only boundary between them."""
    return any(c.finish_reason is not None for c in chunk.candidates or [])
