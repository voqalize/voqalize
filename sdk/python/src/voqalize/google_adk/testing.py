"""``ScriptedLlm`` — a fake ADK model driven by a dictionary, no network, no keys.

Google ADK models are ``BaseLlm`` subclasses; a fake one just yields canned
``LlmResponse``s. This one is keyed by the **last user text** in the request, so a
scripted conversation reads like a script::

    from voqalize.google_adk.testing import ScriptedLlm, reply, call, replies

    llm = ScriptedLlm({
        "book me a flight to hanoi": replies(
            call("search_flights", destination="Hanoi"),   # 1st model call: tool
            reply("I found three options — the cheapest is $412."),  # 2nd call: answer
        ),
        "the cheapest one": replies(
            call("select_flight", flight_id="VN-412"),
            reply("Booked. You're on VN-412."),
        ),
    })

Two things make it match how the real loop calls a model:

* **Multi-step per key.** A tool round-trip calls the model *twice* for the same
  user turn (once to emit the ``function_call``, once to answer given the tool
  result). Each key maps to an ordered list of replies consumed across those
  calls; the cursor advances per call, keyed by the user text, which is stable
  across the round-trip (a function-response request carries no new user text).
* **Streaming.** With ``stream=True`` a :func:`reply` with ``chunks=`` yields
  partial responses (with an optional inter-chunk delay) then an aggregated one —
  the exact shape ADK's SSE path produces — so a barge-in can land mid-reply.

It also records every request's ``contents`` in :attr:`captured_contents`, so a
test can assert the SDK corrected the prompt to heard-truth.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import PrivateAttr

from voqalize._framework.heard import last_user_text


@dataclass
class Reply:
    """One model response (one LLM call's worth of output).

    ``text`` is the spoken answer; ``calls`` are tool invocations to request;
    ``chunks`` (when set) stream that text as partials before the aggregate.
    ``error`` (when set) makes this model call *raise* instead of responding — the
    fault-injection primitive for the no-dead-air path (see :func:`fail`)."""

    text: str = ""
    calls: tuple[tuple[str, dict[str, Any]], ...] = ()
    chunks: tuple[str, ...] = ()
    chunk_delay: float = 0.0
    error: str | None = None
    thought: str = ""
    finish_reason: str = ""


def reply(
    text: str = "",
    *,
    chunks: tuple[str, ...] | list[str] = (),
    chunk_delay: float = 0.0,
    thought: str = "",
) -> Reply:
    """A spoken model reply. Pass ``chunks=`` to stream it as partials (barge-in
    test); ``chunk_delay`` spaces them so an interrupt can land between chunks. Pass
    ``thought=`` to prepend a thinking part (``thought=True``) — the model's private
    reasoning, which the SDK must gate out of speech."""
    return Reply(text=text, chunks=tuple(chunks), chunk_delay=chunk_delay, thought=thought)


def call(name: str, /, *, args: dict[str, Any] | None = None, **kwargs: Any) -> Reply:
    """A model reply that only invokes tool ``name`` (no speech).

    Tool arguments go either as keywords (``call("book", city="Hanoi")``) or as one
    explicit dict (``call("book", args={"name": "Poddar"})``). The dict form is the
    escape hatch for an argument whose name collides with this helper's own parameters —
    ``name`` and ``args`` themselves. ``name`` is positional-only, so
    ``call("book", name="Poddar")`` already means *the tool's* ``name``."""
    return Reply(calls=((name, _tool_args(args, kwargs)),))


def reply_and_call(
    text: str, name: str, /, *, args: dict[str, Any] | None = None, **kwargs: Any
) -> Reply:
    """A model reply that speaks ``text`` *and* invokes tool ``name``.

    Same argument forms as :func:`call`. ``text`` and ``name`` are **positional-only**,
    so tool arguments actually named ``text`` or ``name`` pass as keywords without
    colliding: ``reply_and_call("Opening it.", "open_itinerary", name="Poddar Vietnam")``
    calls the tool with ``{"name": "Poddar Vietnam"}``. For an argument literally named
    ``args``, use the dict form."""
    return Reply(text=text, calls=((name, _tool_args(args, kwargs)),))


def _tool_args(args: dict[str, Any] | None, kwargs: dict[str, Any]) -> dict[str, Any]:
    """One tool-argument dict from the two accepted forms, rejecting the ambiguous mix
    (an explicit ``args=`` *and* keywords — which of the two is the tool call?)."""
    if args is None:
        return dict(kwargs)
    if kwargs:
        raise TypeError(
            f"pass tool arguments either as args={args!r} or as keywords "
            f"({', '.join(sorted(kwargs))}), not both"
        )
    return dict(args)


def fail(message: str = "simulated model error") -> Reply:
    """A model call that raises ``RuntimeError(message)`` — models a provider error
    so a test can drive the no-dead-air path."""
    return Reply(error=message)


def finish(reason: str = "STOP") -> Reply:
    """A model call that returns **cleanly but empty** — no text, no calls (a
    safety-blocked or truncated reply). Drives the *silent* no-dead-air path: the turn
    completes without error, so only the spoke-nothing guard saves it from dead air."""
    return Reply(finish_reason=reason)


def replies(*items: Reply) -> list[Reply]:
    """The ordered replies for one user-text key (one per model call in the turn)."""
    return list(items)


def _system_text(llm_request: Any) -> str:
    """The request's system instruction as plain text (``""`` when unset). ADK keeps it
    on ``config.system_instruction``, as a string or a ``Content``."""
    si = getattr(getattr(llm_request, "config", None), "system_instruction", None)
    if si is None:
        return ""
    if isinstance(si, str):
        return si
    parts = getattr(si, "parts", None) or []
    return "".join(p.text for p in parts if getattr(p, "text", None))


@dataclass
class _Cursor:
    steps: list[Reply]
    i: int = 0


class ScriptedLlm(BaseLlm):
    """A ``BaseLlm`` that answers from a ``{user_text: [Reply, ...]}`` script.

    ``BaseLlm`` is a pydantic model, so the mutable per-run bookkeeping (cursors,
    captured requests) lives in ``PrivateAttr`` fields, populated in ``__init__``.
    """

    model: str = "scripted-llm"
    _cursors: dict[str, _Cursor] = PrivateAttr(default_factory=dict)
    _captured: list[list[Any]] = PrivateAttr(default_factory=list)
    _captured_system: list[str] = PrivateAttr(default_factory=list)

    def __init__(self, script: dict[str, list[Reply] | Reply]) -> None:
        super().__init__(model="scripted-llm")
        # Normalize a bare Reply value to a one-element list for convenience.
        for key, value in script.items():
            steps = value if isinstance(value, list) else [value]
            self._cursors[key] = _Cursor(steps)

    @property
    def captured_contents(self) -> list[list[Any]]:
        """Every request's ``contents`` (a copy per call), in call order — for
        asserting the SDK corrected the prompt to heard-truth."""
        return self._captured

    @property
    def captured_system_instructions(self) -> list[str]:
        """Every request's fully-assembled system instruction as text, in call order —
        for asserting what the SDK grounded each call in (the client's instruction plus
        whatever ``grounding()`` appended)."""
        return self._captured_system

    async def generate_content_async(  # type: ignore[override]
        self, llm_request: Any, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        self._captured.append(list(llm_request.contents))
        self._captured_system.append(_system_text(llm_request))
        key = last_user_text(llm_request.contents)
        cursor = self._cursors.get(key)
        if cursor is None or cursor.i >= len(cursor.steps):
            # Unscripted input: answer with a benign nudge instead of raising, so
            # a mis-keyed test fails on a clear assertion, not deep in ADK.
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[types.Part(text=f"[unscripted: {key!r}]")],
                )
            )
            return

        step = cursor.steps[cursor.i]
        cursor.i += 1

        if step.error is not None:
            raise RuntimeError(step.error)

        call_parts = [
            types.Part(function_call=types.FunctionCall(name=n, args=dict(a)))
            for n, a in step.calls
        ]
        # A thinking part (the model's private reasoning) rides the aggregated event
        # ahead of the answer text; the SDK must gate it out of speech.
        thought_parts = [types.Part(text=step.thought, thought=True)] if step.thought else []

        if stream and step.chunks:
            for chunk in step.chunks:
                if step.chunk_delay:
                    await asyncio.sleep(step.chunk_delay)
                yield LlmResponse(
                    content=types.Content(role="model", parts=[types.Part(text=chunk)]),
                    partial=True,
                )
            yield LlmResponse(
                content=types.Content(
                    role="model", parts=[*thought_parts, types.Part(text=step.text), *call_parts]
                ),
                turn_complete=True,
            )
            return

        parts: list[types.Part] = [*thought_parts]
        if step.text:
            parts.append(types.Part(text=step.text))
        parts.extend(call_parts)
        yield LlmResponse(content=types.Content(role="model", parts=parts))
