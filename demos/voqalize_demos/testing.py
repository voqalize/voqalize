"""``ScriptedGemini`` — a fake :class:`~voqalize_demos.llm.GeminiProvider` driven by
a dictionary, no network, no API key.

The demo brains take the provider by injection (see :mod:`voqalize_demos.llm`)
and hand its ``client`` to :class:`voqalize.sdk.gemini.GeminiBrain`, so the whole
model is one seam wide: ``client.aio.models.generate_content_stream(model=,
contents=, config=)``. This answers on that seam, from a script::

    from voqalize_demos.testing import ScriptedGemini, reply, reply_and_call

    llm = ScriptedGemini({
        "Show me the Pixel.": [
            reply_and_call("Pulling it up.", "open_product", product_id="pixel-9"),
            reply("That's the Pixel 9, forty-five thousand rupees."),
        ],
    })

This is the ``GeminiBrain`` twin of the deleted ADK adapter's
``ScriptedLlm`` (``travel`` and ``orderdesk`` were its last two demos, both now
ported), and it stands in for the whole of google-genai —
including the automatic function calling the brain now leans on:

* **Multi-hop per call.** One user turn is ONE ``generate_content_stream`` call,
  however many tools it takes. google-genai runs the tool, appends the response,
  and calls the model again, all inside that one stream; so does this. Each key
  maps to an ordered list of replies, one per hop, played until a hop asks for no
  tools. A hop ends with a ``finish_reason``, which is the only boundary the
  brain can see and therefore the only thing that closes a unit of speech.
* **It runs the tools, and keeps AFC's record.** A scripted ``call("log_meal",
  ...)`` invokes the brain's own bound method — building the declared pydantic
  model out of the JSON on the way in, exactly as google-genai does — so a test
  drives the real tool body and the real ``session.dispatch``. What the tool
  returned goes into ``automatic_function_calling_history``, never into the
  stream, because that is the only place the real one puts it: the brain reads
  its context off that record.
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
import inspect
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, get_args, get_origin

from google.genai import types
from pydantic import BaseModel


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


def _last_user_text(contents: list[types.Content]) -> str:
    """The most recent ``role="user"`` text in a Gemini request (``""`` if none).

    Mirrors what the model itself keys on. Read once per turn now that the hops
    happen inside one call, so one key holds every step of it."""
    for content in reversed(contents):
        if content.role != "user":
            continue
        return "".join(p.text for p in (content.parts or []) if p.text)
    return ""


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
        """One scripted turn, however many hops it takes. Async like the real one,
        which awaits the call before iterating what it returns."""
        return self._owner.answer(model=model, contents=contents, config=config)


class _Aio:
    """The ``client.aio`` half of the seam."""

    def __init__(self, owner: ScriptedGemini) -> None:
        self.models = _Models(owner)


class ScriptedGemini:
    """A ``GeminiProvider``-shaped fake answering from ``{user_text: [Reply, ...]}``.

    Structural, not nominal: a brain reads ``llm.client`` and calls
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
        """Record the request and return the whole turn as one chunk stream."""
        items = list(contents)
        self.calls.append(
            _Call(
                model=model,
                contents=items,
                system_instruction=_system_text(config),
            )
        )
        return self._turn(_last_user_text(items), config, items)

    async def _turn(
        self,
        key: str,
        config: types.GenerateContentConfig,
        contents: list[types.Content],
    ) -> AsyncIterator[types.GenerateContentResponse]:
        """Play hops until one asks for no tools, running each tool as it goes.

        ``automatic_function_calling_history`` is stamped on every chunk and grows
        the way the real one does, which is what decides where the brain files a
        tool response. It opens as the contents it was handed, verbatim, and a
        hop's calls and responses are appended only once that hop is over — so
        they are first visible on the *next* hop's first chunk.
        """
        # Deep-copied first, because google-genai does — on entry and again on
        # every hop. A bound method copied this way brings ``__self__`` with it,
        # and the tool then runs on a clone of the brain. Copying here is what
        # makes a fake that would notice.
        config = config.model_copy(deep=True)
        tools = {fn.__name__: fn for fn in (config.tools or [])}
        afc = config.automatic_function_calling
        record = list(contents)
        for _ in range((afc.maximum_remote_calls if afc else None) or 10):
            step = self._next(key)
            if step.error is not None:
                raise RuntimeError(step.error)
            async for chunk in _emit(step, tools, record):
                yield chunk
            if not step.calls:
                return

    def _next(self, key: str) -> Reply:
        cursor = self._cursors.get(key)
        if cursor is None:
            cursor = next(
                (c for k, c in self._cursors.items() if k and k in key),
                None,
            )
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
    step: Reply, tools: dict[str, Any], record: list[types.Content]
) -> AsyncIterator[types.GenerateContentResponse]:
    """One hop as the chunk sequence a real stream would produce, ending on the
    ``finish_reason`` that closes it.

    The tools run before that last chunk, which is where google-genai runs them
    too. Their responses go into ``record`` and never into the stream — one
    ``role="user"`` content holding the lot, behind a model content per chunk,
    which is the shape the live API returns.
    """
    call_parts = [
        types.Part(function_call=types.FunctionCall(name=n, args=dict(a))) for n, a in step.calls
    ]
    # What this hop's chunks carry: the record as it stood before this hop.
    seen = list(record)
    emitted: list[list[types.Part]] = []

    def out(parts: list[types.Part], *, finish: bool = False) -> types.GenerateContentResponse:
        emitted.append(parts)
        return _response(parts, finish=finish, record=seen)

    if step.chunks:
        for chunk in step.chunks:
            if step.chunk_delay:
                await asyncio.sleep(step.chunk_delay)
            yield out([types.Part(text=chunk)])
        if call_parts:
            yield out(call_parts)
    else:
        parts: list[types.Part] = []
        if step.text:
            parts.append(types.Part(text=step.text))
        parts.extend(call_parts)
        if parts:
            yield out(parts)
    responses: list[types.Part] = []
    for name, args in step.calls:
        fn = tools.get(name)
        if fn is None:
            raise AssertionError(f"scripted call to {name!r}, which this brain does not declare")
        try:
            result = await fn(**_coerce(fn, args))
        except Exception as exc:  # what google-genai does with a raising tool
            response: dict[str, Any] = {"error": str(exc)}
        else:
            response = {"result": result}
        responses.append(types.Part.from_function_response(name=name, response=response))
    yield out([], finish=True)
    if responses:
        record.extend(types.Content(role="model", parts=parts) for parts in emitted)
        record.append(types.Content(role="user", parts=responses))


def _coerce(fn: Any, args: dict[str, Any]) -> dict[str, Any]:
    """The JSON as the declared pydantic models, which is what a tool body is
    written against — google-genai builds them on the way in and so does this.

    Read off ``inspect.signature``, which is where AFC reads them, and not off
    ``__annotations__``: a tool whose signature still carries the *string*
    ``"LogMeal"`` declares a perfect schema and then fails to be called at all."""
    params = inspect.signature(fn).parameters
    return {k: _build(params[k].annotation, v) if k in params else v for k, v in args.items()}


def _build(hint: Any, value: Any) -> Any:
    """One argument, built against its declared type — a bare model from a dict,
    or a list of them from a list of dicts (``add_items(items: list[SpokenItem])``
    is one parameter whose *type* is the list, and google-genai's real AFC
    validates it the same way)."""
    if isinstance(value, dict) and _is_model(hint):
        return hint(**value)
    if isinstance(value, list) and get_origin(hint) is list:
        (item_hint,) = get_args(hint) or (Any,)
        return [_build(item_hint, item) for item in value]
    return value


def _is_model(hint: Any) -> bool:
    return isinstance(hint, type) and issubclass(hint, BaseModel)


def _response(
    parts: list[types.Part],
    *,
    finish: bool = False,
    record: list[types.Content] | None = None,
) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=parts),
                finish_reason=types.FinishReason.STOP if finish else None,
            )
        ],
        automatic_function_calling_history=record,
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
