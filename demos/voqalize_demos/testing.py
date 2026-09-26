"""``ScriptedGemini`` — a fake ``genai.Client`` driven by a dictionary, no network,
no API key.

The demo brains take the client by injection and hand it straight to
:class:`voqalize.sdk.gemini.GeminiBrain`, so the whole model is one seam wide:
``client.aio.models.generate_content_stream(model=,
contents=, config=)``. This answers on that seam, from a script::

    from voqalize_demos.testing import ScriptedGemini, reply, reply_and_call

    llm = ScriptedGemini({
        "Show me the Pixel.": reply_and_call(
            "Pulling it up.", "open_product", product_id="pixel-9"
        ),
        "How much is it?": reply("Forty-five thousand rupees."),
    })

It stands in for google-genai with automatic function calling off, which is how
:class:`~voqalize.sdk.gemini.GeminiBrain` calls it:

* **One reply per request.** Each key maps to an ordered list of replies, and
  each ``generate_content_stream`` call plays the next one. A brain asks again
  inside a turn only after a tool marked ``@needs_result_now``, so a turn that
  calls unmarked tools consumes one reply, and a reply scripted after it is
  not played in that turn. Speak and call in the same reply
  (:func:`reply_and_call`), the way the prompts ask the model to.
* **It runs no tools.** The brain runs them, from the call parts in the stream,
  so a test drives the real tool body and the real ``session.dispatch``. A
  scripted call to a tool the brain does not declare fails the test here, since
  that is a mistake in the test and not something to hand the brain.
* **It obeys a request that may not call.** The brain's last request after
  ``max_tool_hops`` switches calls off; the scripted calls in that reply are
  dropped, as the model would not make them.
* **Streaming.** ``reply(chunks=[...])`` yields one response per chunk, which is
  what real ``generate_content_stream`` does — incremental parts, never a repeated
  aggregate — so a barge-in can land mid-reply.

Keys match the **last user text** exactly; failing that, any key that is a
*substring* of it, in insertion order — so a test keys on the distinctive phrase
in a long turn rather than pasting the whole of it. Anything unmatched gets
:attr:`default`, so a mis-keyed test fails on the assertion it wrote rather than
deep in the brain.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from google.genai import interactions as gi
from google.genai import types


@dataclass
class Reply:
    """One model response — one LLM call's worth of output.

    ``text`` is the spoken answer; ``calls`` are the tool invocations to request;
    ``chunks`` (when set) stream the answer as partials *instead of* ``text``.
    ``error`` (when set) makes the call raise — the fault-injection primitive."""

    text: str = ""
    calls: tuple[tuple[str, dict[str, Any]], ...] = ()
    chunks: tuple[str, ...] = ()
    chunk_delay: float = 0.0
    error: str | None = None

    @property
    def spoken(self) -> str:
        """What the brain will actually speak for this reply."""
        return "".join(self.chunks) if self.chunks else self.text


def reply(
    text: str = "",
    *,
    chunks: tuple[str, ...] | list[str] = (),
    chunk_delay: float = 0.0,
) -> Reply:
    """A spoken model reply. Pass ``chunks=`` to stream it as partials (the
    barge-in shape); ``chunk_delay`` spaces them so an interrupt can land between
    two. With ``chunks``, the spoken text is their concatenation — ``text`` is not
    also emitted, because a real stream never repeats itself."""
    return Reply(text=text if not chunks else "", chunks=tuple(chunks), chunk_delay=chunk_delay)


def call(name: str, /, *, args: dict[str, Any] | None = None, **kwargs: Any) -> Reply:
    """A model reply that only invokes tool ``name`` (no speech).

    Tool arguments go as keywords (``call("open_order", order_id="A-1")``) or as
    one explicit dict — the escape hatch for an argument whose name collides with
    this helper's own parameters. ``name`` is positional-only, so
    ``call("switch_language", name="Tamil")`` already means *the tool's* ``name``."""
    return Reply(calls=((name, _tool_args(args, kwargs)),))


def reply_and_call(
    text: str, name: str, /, *, args: dict[str, Any] | None = None, **kwargs: Any
) -> Reply:
    """A model reply that speaks ``text`` *and* invokes tool ``name``. ``text`` and
    ``name`` are positional-only, so a tool argument named ``text`` or ``name``
    passes as a keyword without colliding."""
    return Reply(text=text, calls=((name, _tool_args(args, kwargs)),))


def _tool_args(args: dict[str, Any] | None, kwargs: dict[str, Any]) -> dict[str, Any]:
    """One tool-argument dict from the two accepted forms, rejecting the ambiguous
    mix (an explicit ``args=`` *and* keywords — which of the two is the call?)."""
    if args is None:
        return dict(kwargs)
    if kwargs:
        raise TypeError(
            f"pass tool arguments either as args={args!r} or as keywords "
            f"({', '.join(sorted(kwargs))}), not both"
        )
    return dict(args)


def fail(message: str = "simulated model error") -> Reply:
    """A model call that raises ``RuntimeError(message)`` — a provider outage, so a
    test can drive the no-dead-air path."""
    return Reply(error=message)


def replies(*items: Reply) -> list[Reply]:
    """The ordered replies for one key — one per model call in that turn."""
    return list(items)


def _user_contents(contents: list[types.Content]) -> list[str]:
    """Every ``role="user"`` text in a Gemini request, newest first.

    Newest first because that is what the model keys on; *every* one because the
    newest is not always the sentence. A brain that appends grounding to the
    context — orderdesk\'s "he changed the screen" note — files it as a user turn
    of its own, and it lands after the utterance it is grounding."""
    return [
        "".join(p.text for p in (content.parts or []) if p.text)
        for content in reversed(contents)
        if content.role == "user"
    ]


@dataclass
class _Cursor:
    steps: list[Reply]
    i: int = 0


@dataclass
class _Call:
    """One recorded model call — what the brain asked the model to answer."""

    model: str
    contents: list[types.Content]
    system_instruction: str


class _Models:
    """The ``client.aio.models`` half of the seam."""

    def __init__(self, owner: ScriptedGemini) -> None:
        self._owner = owner

    async def generate_content_stream(
        self,
        *,
        model: str,
        contents: Any,
        config: types.GenerateContentConfig,
    ) -> AsyncIterator[types.GenerateContentResponse]:
        """One scripted reply. Async like the real one, which awaits the call
        before iterating what it returns."""
        return self._owner.answer(model=model, contents=contents, config=config)


class _Interactions:
    """The ``client.aio.interactions`` half of the seam.

    :class:`~voqalize.sdk.gemini_interactions.GeminiInteractionsBrain` runs the
    tools *itself*, between requests, so this half only plays the model: one
    ``create()`` is one hop, and the next hop is the next ``Reply`` under the same
    key, exactly as on :class:`_Models`.
    """

    def __init__(self, owner: ScriptedGemini) -> None:
        self._owner = owner
        #: Every request this seam was handed, in call order.
        self.requests: list[dict[str, Any]] = []

    async def create(self, **request: Any) -> AsyncIterator[gi.InteractionSSEEvent]:
        """One hop's SSE stream. Async like the real one, which awaits the call
        before iterating what it returns."""
        self.requests.append(request)
        return self._owner.interact(request)


class _Aio:
    """The ``client.aio`` half of the seam."""

    def __init__(self, owner: ScriptedGemini) -> None:
        self.models = _Models(owner)
        self.interactions = _Interactions(owner)


class ScriptedGemini:
    """A ``genai.Client``-shaped fake answering from ``{user_text: [Reply, ...]}``.

    Structural, not nominal: a brain calls
    ``client.aio.models.generate_content_stream(...)``, so this answers on both
    halves of that shape and never constructs a real ``genai.Client``."""

    def __init__(
        self,
        script: dict[str, list[Reply] | Reply] | None = None,
        *,
        default: Reply | None = None,
    ) -> None:
        self._cursors: dict[str, _Cursor] = {}
        for key, value in (script or {}).items():
            self._cursors[key] = _Cursor(value if isinstance(value, list) else [value])
        self._default = default if default is not None else reply("Right.")
        self.calls: list[_Call] = []
        self.aio = _Aio(self)

    @property
    def client(self) -> ScriptedGemini:
        """What a brain is handed. This object is its own client."""
        return self

    # ─── What the brain asked ────────────────────────────────────────────

    @property
    def captured_contents(self) -> list[list[types.Content]]:
        """Every request's ``contents``, in call order — for asserting the brain
        prompted the model with heard truth."""
        return [c.contents for c in self.calls]

    @property
    def captured_system_instructions(self) -> list[str]:
        """Every request's system instruction as text, in call order — for
        asserting what a brain folded into the prompt (payload context, grounding)."""
        return [c.system_instruction for c in self.calls]

    # ─── The seam ────────────────────────────────────────────────────────

    def answer(
        self,
        *,
        model: str,
        contents: Any,
        config: types.GenerateContentConfig,
    ) -> AsyncIterator[types.GenerateContentResponse]:
        """Record the request and return its reply as a chunk stream."""
        items = list(contents)
        self.calls.append(
            _Call(
                model=model,
                contents=items,
                system_instruction=_system_text(config),
            )
        )
        return self._reply(self._key(_user_contents(items)), config)

    async def _reply(
        self, key: str, config: types.GenerateContentConfig
    ) -> AsyncIterator[types.GenerateContentResponse]:
        """The next reply under ``key``, ending on the ``finish_reason`` that
        closes it."""
        # Deep-copied first, because google-genai does, on every request. A bound
        # method copied this way brings ``__self__`` with it, and the tool then
        # runs on a clone of the brain. Copying here is what makes a fake that
        # would notice.
        config = config.model_copy(deep=True)
        declared = {fn.__name__ for fn in (config.tools or []) if callable(fn)}
        if declared:
            afc = config.automatic_function_calling
            if afc is None or not afc.disable:
                raise AssertionError("automatic function calling must be off")
        fc = config.tool_config and config.tool_config.function_calling_config
        may_call = not (fc and fc.mode == types.FunctionCallingConfigMode.NONE)
        step = self._next(key)
        if step.error is not None:
            raise RuntimeError(step.error)
        for name, _ in step.calls:
            if name not in declared:
                raise AssertionError(
                    f"scripted call to {name!r}, which this brain does not declare"
                )
        calls = step.calls if may_call else ()
        async for chunk in _emit(step, calls):
            yield chunk

    # ─── The interactions seam ───────────────────────────────────────────

    def interact(self, request: dict[str, Any]) -> AsyncIterator[gi.InteractionSSEEvent]:
        """One hop of the script, as the event stream the interactions API sends.

        Keyed on the last user step the brain would key on — but scanning *every*
        user step, newest first, for one the script knows. A brain that appends
        grounding as a ``UserInputStep`` (aura's screen snapshot does) otherwise
        buries the sentence the test is keyed on behind a JSON blob."""
        return _interaction_events(
            self._next(self._key(_user_texts(list(request.get("input") or []))))
        )

    def _key(self, texts: list[str]) -> str:
        """The script key for a request, given its user texts newest first: the
        newest one the script knows, else the newest."""
        return next((t for t in texts if self._cursor(t) is not None), texts[0] if texts else "")

    def _cursor(self, key: str) -> _Cursor | None:
        """The script this user text is keyed on: exact first, then any key that is
        a substring of it, in insertion order."""
        cursor = self._cursors.get(key)
        if cursor is None:
            cursor = next(
                (c for k, c in self._cursors.items() if k and k in key),
                None,
            )
        return cursor

    def _next(self, key: str) -> Reply:
        cursor = self._cursor(key)
        if cursor is None or cursor.i >= len(cursor.steps):
            return self._default
        step = cursor.steps[cursor.i]
        cursor.i += 1
        return step


def _system_text(config: types.GenerateContentConfig) -> str:
    """The request's system instruction as plain text (``""`` when unset)."""
    si = config.system_instruction
    if si is None:
        return ""
    if isinstance(si, str):
        return si
    parts = getattr(si, "parts", None) or []
    return "".join(p.text for p in parts if getattr(p, "text", None))


async def _emit(
    step: Reply, calls: tuple[tuple[str, dict[str, Any]], ...]
) -> AsyncIterator[types.GenerateContentResponse]:
    """One reply as the chunk sequence a real stream produces: the speech, then
    the calls, then an empty chunk carrying the ``finish_reason``."""
    call_parts = [
        types.Part(function_call=types.FunctionCall(id=f"call_{i}_{n}", name=n, args=dict(a)))
        for i, (n, a) in enumerate(calls)
    ]
    if step.chunks:
        for chunk in step.chunks:
            if step.chunk_delay:
                await asyncio.sleep(step.chunk_delay)
            yield _response([types.Part(text=chunk)])
        if call_parts:
            yield _response(call_parts)
    else:
        parts: list[types.Part] = []
        if step.text:
            parts.append(types.Part(text=step.text))
        parts.extend(call_parts)
        if parts:
            yield _response(parts)
    yield _response([], finish=True)


def _user_texts(steps: list[Any]) -> list[str]:
    """Every ``UserInputStep``'s text in one request's input, newest first."""
    return [
        "".join(c.text for c in (step.content or []) if isinstance(c, gi.TextContent))
        for step in reversed(steps)
        if isinstance(step, gi.UserInputStep)
    ]


async def _interaction_events(step: Reply) -> AsyncIterator[gi.InteractionSSEEvent]:
    """One hop as the SSE sequence a real interaction would produce.

    Speech first, then this hop's calls — each step opening on a ``StepStart``
    skeleton, filling from deltas and closing on ``StepStop``. A function call's
    skeleton really is argument-less on the wire and its JSON really does arrive
    fragmented mid-token, so it goes over in two pieces here too: a brain that
    read the arguments off the skeleton would otherwise pass."""
    if step.error is not None:
        raise RuntimeError(step.error)
    resource = gi.InteractionSseEventInteraction(id="int_1", status="completed")
    yield gi.InteractionCreatedEvent(interaction=resource)
    index = 0
    chunks = step.chunks or ((step.text,) if step.text else ())
    if chunks:
        yield gi.StepStart(index=index, step=gi.ModelOutputStep())
        for chunk in chunks:
            if step.chunk_delay:
                await asyncio.sleep(step.chunk_delay)
            yield gi.StepDelta(index=index, delta=gi.TextDelta(text=chunk))
        yield gi.StepStop(index=index)
        index += 1
    for name, args in step.calls:
        payload = json.dumps(args)
        cut = len(payload) // 2
        yield gi.StepStart(
            index=index, step=gi.FunctionCallStep(id=f"call_{name}", name=name, arguments={})
        )
        yield gi.StepDelta(index=index, delta=gi.ArgumentsDelta(arguments=payload[:cut]))
        yield gi.StepDelta(index=index, delta=gi.ArgumentsDelta(arguments=payload[cut:]))
        yield gi.StepStop(index=index)
        index += 1
    # No steps on it: a streamed lifecycle payload omits what only a
    # non-streaming Interaction carries.
    yield gi.InteractionCompletedEvent(interaction=resource)


def _response(parts: list[types.Part], *, finish: bool = False) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=parts),
                finish_reason=types.FinishReason.STOP if finish else None,
            )
        ]
    )


__all__ = [
    "Reply",
    "ScriptedGemini",
    "call",
    "fail",
    "replies",
    "reply",
    "reply_and_call",
]
