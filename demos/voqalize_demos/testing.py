"""``ScriptedGemini`` — a fake :class:`~voqalize_demos.llm.GeminiProvider` driven by
a dictionary, no network, no API key.

The demo brains take the concrete provider by injection (see
:mod:`voqalize_demos.llm`), so the whole model is one seam wide: ``stream(model=,
contents=, config=)`` returning an async iterator of
``types.GenerateContentResponse``. This is that seam, answering from a script::

    from voqalize_demos.testing import ScriptedGemini, reply, reply_and_call

    llm = ScriptedGemini({
        "Show me the Pixel.": [
            reply_and_call("Pulling it up.", "open_product", product_id="pixel-9"),
            reply("That's the Pixel 9, forty-five thousand rupees."),
        ],
    })

This is the ``GeminiBrain`` twin of
:class:`voqalize.google_adk.testing.ScriptedLlm` (which serves the two ADK demos,
``travel`` and ``orderdesk``) and follows the same two rules, because
:meth:`GeminiBrain.respond` calls a model the same way ADK does:

* **Multi-step per key.** One tool round-trip is *two* model calls for one user
  turn — emit the ``function_call``, then answer given the tool result. Each key
  maps to an ordered list consumed across those calls. The cursor is keyed by the
  user text, which is stable across the round-trip: the tool result is appended as
  a ``role="tool"`` content, so the *last user text* does not move.
* **Streaming.** ``reply(chunks=[...])`` yields one response per chunk, which is
  what real ``generate_content_stream`` does — incremental parts, never a repeated
  aggregate — so a barge-in can land mid-reply.

Keys match the **last user text** exactly; failing that, any key that is a
*substring* of it, in insertion order. The substring form is for greeting prompts:
a brain that opens with ``say_then_generate`` passes a whole paragraph of
instruction as the user turn, and a test should key on the distinctive phrase in
it, not paste the paragraph. Anything unmatched gets :attr:`default`, so a
mis-keyed test fails on the assertion it wrote rather than deep in the brain.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

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


def _last_user_text(contents: list[types.Content]) -> str:
    """The most recent ``role="user"`` text in a Gemini request (``""`` if none).

    Mirrors what the model itself keys on. Tool results ride ``role="tool"``, so
    this stays put across a round-trip — which is what makes one key hold both
    steps of it."""
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


class ScriptedGemini:
    """A ``GeminiProvider``-shaped fake answering from ``{user_text: [Reply, ...]}``.

    Structural, not nominal: the brains only ever call :meth:`stream`, so this does
    not subclass ``GeminiProvider`` (which would drag in a real ``genai.Client``)."""

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

    async def stream(
        self,
        *,
        model: str,
        contents: Any,
        config: types.GenerateContentConfig,
    ) -> AsyncIterator[types.GenerateContentResponse]:
        """One scripted inference. Async like the real one (which awaits the
        client's ``generate_content_stream`` before iterating it)."""
        items = list(contents)
        self.calls.append(
            _Call(
                model=model,
                contents=items,
                system_instruction=_system_text(config),
            )
        )
        step = self._next(_last_user_text(items))
        if step.error is not None:
            raise RuntimeError(step.error)
        return _emit(step)

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


async def _emit(step: Reply) -> AsyncIterator[types.GenerateContentResponse]:
    """The scripted reply as the chunk sequence a real stream would produce."""
    call_parts = [
        types.Part(function_call=types.FunctionCall(name=n, args=dict(a))) for n, a in step.calls
    ]
    if step.chunks:
        for chunk in step.chunks:
            if step.chunk_delay:
                await asyncio.sleep(step.chunk_delay)
            yield _response([types.Part(text=chunk)])
        if call_parts:
            yield _response(call_parts)
        return
    parts: list[types.Part] = []
    if step.text:
        parts.append(types.Part(text=step.text))
    parts.extend(call_parts)
    if parts:
        yield _response(parts)


def _response(parts: list[types.Part]) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=parts))]
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
