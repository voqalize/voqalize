"""A Gemini-backed Brain on the **interactions** API, where we run the tool loop.

    from google import genai
    from voqalize.sdk.gemini_interactions import GeminiInteractionsBrain

    class Concierge(GeminiInteractionsBrain):
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

That is the same brain :class:`~voqalize.sdk.gemini.GeminiBrain` takes, and the
same way you host it. What differs is underneath.

**There is no automatic function calling here.** ``interactions`` declares tools
and nothing else — ``tools`` is a list of *declarations*, no field anywhere takes
a callable, and the API returns a ``function_call`` step and stops. So this class
runs the loop: declare, stream, call, answer, stream again, up to
``max_tool_hops``. :class:`~voqalize.sdk.gemini.GeminiBrain` hands that job to
google-genai and takes the record it kept; this one keeps its own.

Three things are better for having done it ourselves:

* **A turn's boundaries are told to us, not inferred.** A hop on
  ``generate_content`` is delimited by a ``finish_reason`` on some chunk, and a
  unit of speech is whatever falls between two of them. Here every step arrives
  bracketed — ``step.start``, its deltas, ``step.stop`` — and a ``model_output``
  step *is* a unit of speech.
* **A call and its result are linked by id**, not by position: ``function_call``
  carries an ``id`` and the ``function_result`` quotes it as ``call_id``. When a
  barge-in cuts a turn between the two, the pair that is missing is the one
  named, rather than the one counted.
* **The context is re-read per hop.** The whole context goes over on every call,
  so something :meth:`GeminiInteractionsBrain.append_to_context` added while a
  tool was running is in front of the model for the sentence that follows it. On
  ``generate_content`` the contents are handed over once per turn, so the same
  append waits for the turn after.

**The brain owns the context, and what it records is what was heard.** Each
``model_output`` step goes into the context as it streams, then :meth:`~voqalize.sdk.Brain.on_finalize` rewrites it to the
delivered prefix — same rule, same reason, as every other brain here.

Install with ``pip install voqalize-agent-sdk[gemini]``.
"""

from __future__ import annotations

import inspect
import json
from collections import deque
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from typing import Any, cast, get_type_hints

from google import genai
from google.genai import interactions as gi
from google.genai import types
from loguru import logger
from pydantic import BaseModel

from .brain import Brain, Session
from .events import Chunk, Finalize, Speech, SpeechEnd, SpeechStart, UserMessage
from .gemini import DEFAULT_MODEL

__all__ = ["VOICE_THINKING", "GeminiInteractionsBrain"]

# The same bet as :data:`voqalize.sdk.gemini.VOICE_THINKING`, in this API's units:
# on a voice turn a reasoning budget is spent in silence the caller sits through,
# and thought steps are never spoken. Read that constant's comment before moving
# models — both the floor and the model's willingness to *act* at a level it
# accepts are model-specific, and were measured, not assumed. Here the knob is a
# level rather than a token budget: minimal, low, medium, high.
VOICE_THINKING = gi.GenerationConfig(thinking_level="minimal")


class GeminiInteractionsBrain(Brain):
    """Base for a Gemini brain on the interactions API. Override the prompt, the
    greeting and :attr:`tools`; the turn shape, the tool loop and the context
    come from here."""

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
        self._system_instruction = system_instruction
        self._max_tool_hops = max_tool_hops

        # The conversation, as interaction steps — typed by what each one is
        # (``user_input``, ``thought``, ``model_output``, ``function_call``,
        # ``function_result``) rather than by a role shared between a person and a
        # tool's answer. In the provider's own types, on purpose; see the same
        # note on :class:`~voqalize.sdk.gemini.GeminiBrain`. This is where the two
        # adapters differ, and where they should.
        self._history: list[gi.Step] = []
        # Steps still awaiting their heard truth, in the order Voqalize will
        # report them. Only steps that opened speech are here: Voqalize finalizes
        # what it played, and a hop that only called a tool played nothing.
        #
        # Tracked by identity throughout — two freshly opened, still-empty steps
        # are equal as pydantic models, so `remove`, `index` and `in` are all
        # wrong on this queue and on the context.
        self._awaiting: deque[gi.ModelOutputStep] = deque()

    # ─── The turn ───────────────────────────────────────────────────────

    def append_to_context(self, step: gi.UserInputStep) -> None:
        """Add to the conversation the model sees, in the interactions API's own type.

        For context the app knows and the conversation does not — typically the
        live screen state pushed to :meth:`~voqalize.sdk.Brain.on_rtvi`, which
        takes no floor and starts no turn::

            async def on_rtvi(self, session, msg):
                if msg.data.get("t") == "state_sync":
                    self.append_to_context(
                        gi.UserInputStep(
                            content=[
                                gi.TextContent(text="ON SCREEN: " + json.dumps(msg.data["d"]))
                            ]
                        )
                    )

        A ``UserInputStep`` holds whatever the API takes, so handing the model a
        screenshot or a PDF is this same call with different content. It is the
        only step you may append: every other kind is the model's to write, or a
        tool result this class writes itself. That is the same rule
        :meth:`~voqalize.sdk.gemini.GeminiBrain.append_to_context` spells as
        ``role == "user"``, said in the vocabulary this API uses instead.

        It appends **immediately, once, where you call it**. Nothing here
        debounces, diffs or re-renders — what to append and when is yours, and
        this method will not guess which of ten identical screens you meant. Every
        hop is the previous one plus what happened since, which is what makes it
        cacheable and what stops the context changing under a turn already in
        flight.

        Calling it mid-turn is safe. The append can land between a function call
        and its result; the API accepts that, and the model finishes the call
        before it attends to what arrived. Reconciliation is untouched — an
        appended step is not a speech step, so it is never rewritten with heard
        text and never dropped as an unanswered call.
        """
        if type(step) is not gi.UserInputStep:
            raise ValueError(
                f"append_to_context takes a UserInputStep, got {type(step).__name__}. "
                "The model's side of a conversation is written by the model."
            )
        self._history.append(step)

    def on_user_message(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]:
        self._history.append(gi.UserInputStep(content=[gi.TextContent(text=msg.text)]))
        return self.respond(session)

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """Stream one turn, however many tool hops it takes.

        One hop is one interaction: the whole context goes over, the model
        answers with a series of steps, and if any of them is a ``function_call``
        we run it, write the result into the context and go round again.
        The loop ends when a hop asks for no tools. If it goes round
        ``max_tool_hops`` times without one, the last hop is run with
        ``tool_choice="none"``: the declarations stay in place, so the context
        still reads, and the model has to answer. A turn that spends its whole
        budget still ends in something the caller hears.

        Speech comes off the stream as it arrives. A ``model_output`` step opens
        a unit on its first text and closes it at ``step.stop``; every other kind
        of step is silent, so a hop that only calls a tool never opens one.
        """
        tools = self.tools  # read once per turn, so a hop cannot change the offer
        declarations = [_declare(fn) for fn in tools]
        table = {fn.__name__: fn for fn in tools}
        try:
            for hop in range(self._max_tool_hops + 1):
                spent = hop == self._max_tool_hops
                produced: list[gi.Step] = []
                async for speech in self._hop(declarations, produced, answer_now=spent):
                    yield speech
                if spent:
                    logger.warning("tool budget of {} hops spent", self._max_tool_hops)
                    return
                calls = [s for s in produced if isinstance(s, gi.FunctionCallStep)]
                if not calls:
                    return
                await self._run(table, calls)
        finally:
            # Never yield here — a barge-in closes this generator by throwing
            # GeneratorExit at the yield above, and an async generator that
            # yields while closing raises instead of tearing down.
            self._drop_unanswered()

    async def _hop(
        self, declarations: list[gi.Function], produced: list[gi.Step], *, answer_now: bool
    ) -> AsyncGenerator[Speech, None]:
        """One interaction, streamed: speech out, steps into ``produced``.

        Steps arrive in pieces and are assembled here. ``step.start`` carries the
        skeleton — for a function call that is its ``id`` and ``name``, with the
        arguments still empty — and the rest lands as deltas: text, fragments of
        the arguments JSON, the thought signature. ``step.stop`` closes it.

        Each step joins the context the moment it opens, so an interruption
        leaves behind exactly what had been generated when it landed.

        Deltas name the step they belong to by ``index``, so nothing here assumes
        one step finishes before the next begins.
        """
        steps: dict[int, gi.Step] = {}
        buffered: dict[int, str] = {}
        speaking: int | None = None

        async for event in await self._stream(declarations, answer_now):
            if isinstance(event, gi.StepStart):
                steps[event.index] = event.step
                buffered[event.index] = ""
                produced.append(event.step)
                self._history.append(event.step)
            elif isinstance(event, gi.StepDelta):
                step, delta = steps.get(event.index), event.delta
                if isinstance(delta, gi.TextDelta):
                    buffered[event.index] += delta.text
                    if isinstance(step, gi.ModelOutputStep):
                        if speaking is None:
                            yield SpeechStart()
                            self._awaiting.append(step)
                            speaking = event.index
                        yield Chunk(delta.text)
                elif isinstance(delta, gi.ArgumentsDelta):
                    buffered[event.index] += delta.arguments or ""
                elif isinstance(delta, gi.ThoughtSignatureDelta) and isinstance(
                    step, gi.ThoughtStep
                ):
                    # Gemini 3 wants its own thought handed back, signed. This is
                    # the only place the signature exists.
                    step.signature = delta.signature
            elif isinstance(event, gi.StepStop):
                _close(steps.get(event.index), buffered.get(event.index, ""))
                if speaking == event.index:
                    yield SpeechEnd()
                    speaking = None
            elif isinstance(event, gi.ErrorEvent):
                # The stream's own failure channel: an HTTP 200 whose body says no.
                detail = (event.error and event.error.message) or "no detail"
                raise RuntimeError(f"interaction failed: {detail}")

        if speaking is not None:
            # The stream ended without closing the step. Close the unit anyway: a
            # SpeechStart with no SpeechEnd is a wire violation.
            yield SpeechEnd()

    async def _stream(
        self, declarations: list[gi.Function], answer_now: bool
    ) -> AsyncIterator[gi.InteractionSSEEvent]:
        """One streamed, stateless interaction carrying the whole context.

        ``store=False`` and no ``previous_interaction_id``: the conversation lives
        here, in the brain, and never on Google's side. That is the same
        bargain every other brain in this SDK makes, and it is what lets
        :meth:`~voqalize.sdk.Brain.on_finalize` rewrite a turn after the fact —
        server-side state cannot be told that the caller only heard half of it.
        """
        request: dict[str, Any] = {
            "model": self._model,
            "input": list(self._history),
            "system_instruction": self._system_instruction,
            "generation_config": VOICE_THINKING.model_copy(update={"tool_choice": "none"})
            if answer_now
            else VOICE_THINKING,
            "stream": True,
            "store": False,
        }
        if declarations:
            request["tools"] = declarations
        stream = await self._client.aio.interactions.create(**request)
        return cast(AsyncIterator[gi.InteractionSSEEvent], stream)

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Callable[..., Any]]:
        """The tools the model may call, read once per turn.

        Bound ``async def`` methods, listed by hand::

            @property
            def tools(self):
                return [self.log_meal, self.show_glucose]

        **The method is the declaration.** Its name is the name the model calls,
        its docstring is the description the model reads, and its single pydantic
        parameter is the schema. Nothing is declared twice, and this is the same
        list :class:`~voqalize.sdk.gemini.GeminiBrain` takes — a brain moves
        between the two classes without touching its tools.

        Take one model, or nothing at all. Nested models are fine; the schema goes
        over as JSON Schema with its ``$defs`` intact. The rule is the same here
        as on the automatic path and the reason is the opposite one: this path
        parses the model parameter and passes every other argument through
        untouched, so a flat ``date`` reaches the tool as the ``str`` it arrived
        as instead of failing loudly (``tests/unit/test_flat_parameters.py``).

        The session is not a parameter, because the signature is the schema and
        the model would try to fill it. Read
        :attr:`~voqalize.sdk.Brain.session` instead.
        """
        return []

    async def _run(
        self, table: dict[str, Callable[..., Any]], calls: list[gi.FunctionCallStep]
    ) -> None:
        """Run this hop's calls and write each result into the context.

        In the order the model produced them, one at a time. Tools drive the
        screen, and two of them racing would put the caller's display in an order
        the model never asked for.

        A tool that raises is reported as one — ``is_error`` on the step, and a
        line in the log. On the automatic path a failure reaches the model as an
        ``{'error': …}`` payload it will cheerfully narrate as success, and this
        API at least lets us say which it was.
        """
        for call in calls:
            fn = table.get(call.name)
            if fn is None:
                self._history.append(_failed(call, f"no tool named {call.name!r}"))
                logger.warning("model called unknown tool {}", call.name)
                continue
            try:
                result = await fn(**_coerce(fn, call.arguments))
            except Exception as exc:
                self._history.append(_failed(call, str(exc)))
                logger.warning("tool {} failed: {}", call.name, exc)
            else:
                self._history.append(
                    gi.FunctionResultStep(
                        call_id=call.id,
                        name=call.name,
                        result=json.dumps({"result": result}, default=str),
                    )
                )

    def _drop_unanswered(self) -> None:
        """Take out calls whose result never came back.

        A barge-in cuts a turn wherever it lands, which may be between a call and
        the result we were about to write. A ``function_call`` with no
        ``function_result`` quoting its id is not a conversation Gemini will
        accept on the next turn, so it leaves. Whether the tool actually ran is
        not ours to know: the context records what completed, and the side
        effect stands either way.
        """
        answered = {
            s.call_id for s in self._history if isinstance(s, gi.FunctionResultStep) and s.call_id
        }
        self._history = [
            s
            for s in self._history
            if not (isinstance(s, gi.FunctionCallStep) and s.id not in answered)
        ]

    # ─── Context ────────────────────────────────────────────────────────

    @property
    def system_instruction(self) -> str:
        """The prompt every hop carries. Settable from
        :meth:`~voqalize.sdk.Brain.on_session_start`, where the facts that are
        true for this caller and no other — who they are, what they are calling
        about, what your system already knows — are finally in hand. Setting it
        replaces the prompt for the rest of the session; the tools and the model
        stay as constructed.
        """
        return self._system_instruction

    @system_instruction.setter
    def system_instruction(self, text: str) -> None:
        self._system_instruction = text

    # ─── Heard truth ────────────────────────────────────────────────────

    async def on_finalize(self, session: Session, fin: Finalize) -> None:
        """Rewrite the step Voqalize just finished playing down to what the
        caller actually heard.

        A unit this brain never opened is the greeting: `greet` returns a string
        the SDK speaks, so the only record of it anywhere is what comes back
        here — already heard-truth, already cut to the delivered prefix if the
        caller talked over it. Without this the model does not know it greeted,
        and asks its opening question a second time.
        """
        if not self._awaiting:
            if fin.heard:
                self._history.append(gi.ModelOutputStep(content=[gi.TextContent(text=fin.heard)]))
            return
        self._reconcile(self._awaiting.popleft(), fin.heard)

    def _reconcile(self, step: gi.ModelOutputStep, heard: str) -> None:
        """Collapse a step's text down to ``heard``, in place.

        Anything that is not text keeps its identity and its order; only spoken
        text is replaced, by the first text item, and later ones go because they
        were generated and never delivered. A step left with nothing leaves the
        context, since a model turn with no content is not a turn.
        """
        kept: list[gi.Content] = []
        placed = False
        for item in step.content or []:
            if not isinstance(item, gi.TextContent):
                kept.append(item)
            elif heard and not placed:
                item.text = heard
                kept.append(item)
                placed = True
        step.content = kept
        if not kept:
            self._history = [s for s in self._history if s is not step]


# ─── Plumbing ───────────────────────────────────────────────────────────


def _close(step: gi.Step | None, buffered: str) -> None:
    """Fold a step's buffered deltas into the step itself, at ``step.stop``."""
    if isinstance(step, gi.FunctionCallStep):
        step.arguments = json.loads(buffered) if buffered else {}
    elif isinstance(step, gi.ModelOutputStep):
        step.content = [gi.TextContent(text=buffered)] if buffered else []


def _declare(fn: Callable[..., Any]) -> gi.Function:
    """One tool, as a declaration. The callable stays here.

    ``async def`` is required. We run tools inside the turn's task — a synchronous
    tool would hold the event loop for the length of whatever it does, and the
    first ``await`` it grows is a rewrite.

    Nothing callable crosses this line, so nothing about the brain does either.
    That is worth saying because the automatic path has the opposite problem:
    there the config carries the functions themselves, google-genai deep-copies
    it, and a bound method would take a clone of the brain along with it.
    """
    if not inspect.iscoroutinefunction(fn):
        raise TypeError(
            f"tool {getattr(fn, '__name__', fn)!r} must be `async def`: a sync tool would hold "
            "the event loop for as long as it runs"
        )
    declaration = types.FunctionDeclaration.from_callable_with_api_option(
        callable=fn, use_json_schema=True
    )
    return gi.Function(
        name=declaration.name,
        description=declaration.description,
        parameters=declaration.parameters_json_schema,
    )


def _coerce(fn: Callable[..., Any], arguments: dict[str, Any]) -> dict[str, Any]:
    """Build a call's arguments out of the JSON the model sent.

    ``get_type_hints`` rather than ``inspect.signature``, because brain modules
    use ``from __future__ import annotations`` and a method's own annotations are
    therefore strings. Declaring and calling from the same resolved hints is what
    keeps a tool that declares a perfect schema from raising on every call.
    """
    hints = get_type_hints(fn)
    out: dict[str, Any] = {}
    for name, value in arguments.items():
        model = hints.get(name)
        if isinstance(model, type) and issubclass(model, BaseModel) and isinstance(value, dict):
            out[name] = model.model_validate(value)
        else:
            out[name] = value
    return out


def _failed(call: gi.FunctionCallStep, detail: str) -> gi.FunctionResultStep:
    """A result the model can read and we can see. ``is_error`` is the half the
    automatic path has no room for: there a failure reaches the model as an
    ordinary payload, and the model narrates it as success."""
    return gi.FunctionResultStep(
        call_id=call.id,
        name=call.name,
        result=json.dumps({"error": detail}),
        is_error=True,
    )
