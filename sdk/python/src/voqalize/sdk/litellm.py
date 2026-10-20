"""A LiteLLM-backed Brain: the voice core, speaking to any model LiteLLM reaches.

    from voqalize.sdk.litellm import LiteLLMBrain

    class Concierge(LiteLLMBrain):
        def __init__(self) -> None:
            super().__init__(
                system_instruction="You are …",
                model="anthropic/claude-haiku-5-5",   # or "openai/responses/gpt-6-sol", …
                reasoning="low",
            )

        @property
        def tools(self):
            return [self.open_booking]

Install with ``pip install voqalize-agent-sdk[litellm]``. Nothing in
``voqalize.sdk`` imports this module, so the core SDK stays free of ``litellm``.
Keys come from the environment, as LiteLLM reads them (``OPENAI_API_KEY``,
``ANTHROPIC_API_KEY``, …), or from ``options={"api_key": …}``.

The turn is the voice core's (:mod:`voqalize.sdk.voice`), the same as on every
other model. This module is only LiteLLM's half: the context as chat messages,
tools as JSON schema, and the streamed deltas read back. Two things to know:

- **Reasoning is not carried between requests.** Chat messages have no place for
  a provider's reasoning items, so each request reasons afresh. A model whose
  tool calls need their reasoning handed back is better served by its own layer
  (:class:`~voqalize.sdk.openai.OpenAIBrain`,
  :class:`~voqalize.sdk.gemini.GeminiBrain`).
- **A tool call runs when its arguments are complete**, which over chat
  completions is when the response ends. The words before it have already been
  spoken by then.

OpenAI's GPT-6 models take tools together with a reasoning effort only on the
Responses API, which LiteLLM reaches as ``"openai/responses/<model>"``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from typing import Any

import litellm

from ._portable import PortableBrain, Request, Turn
from .voice import TOOL_BUDGET_MS, ModelChunk, ModelPart, ModelUsage, needs_result_now

__all__ = ["TOOL_BUDGET_MS", "LiteLLMBrain", "needs_result_now"]


class LiteLLMBrain(PortableBrain):
    """Base for a brain on any model LiteLLM reaches. Override the prompt, the
    greeting and :attr:`~voqalize.sdk.voice.VoiceBrain.tools`; the turn shape, the
    tool loop and the context come from the voice core.

    ``model`` is LiteLLM's model string. ``reasoning`` is passed as
    ``reasoning_effort``, or left out when ``None``. ``options`` are passed to
    every ``litellm.acompletion`` call as they are — an ``api_key``, an
    ``api_base``, a ``temperature``. A setting the provider does not take is
    dropped rather than refused. ``max_tool_hops`` and ``report_usage`` are the
    voice core's."""

    provider = "litellm"

    def __init__(
        self,
        *,
        system_instruction: str,
        model: str,
        reasoning: str | None = None,
        options: Mapping[str, Any] | None = None,
        max_tool_hops: int = 6,
        report_usage: bool = True,
    ) -> None:
        super().__init__(
            model=model,
            system_instruction=system_instruction,
            max_tool_hops=max_tool_hops,
            report_usage=report_usage,
        )
        self._reasoning = reasoning
        self._options = dict(options or {})

    def _arguments(self, contents: list[Turn], request: Request) -> dict[str, Any]:
        """One ``litellm.acompletion`` call's arguments."""
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": _messages(self._system_instruction, contents),
            "stream": True,
            "stream_options": {"include_usage": True},
            "drop_params": True,
            **self._options,
        }
        tools: list[dict[str, Any]] = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in request.tools
        ]
        if tools:
            choice: Any = "auto"
            if request.choice.mode == "none":
                choice = "none"
            elif request.choice.mode == "only":
                name = request.choice.name
                if "/responses/" in self._model:
                    # LiteLLM's Responses bridge passes a named tool_choice on in a
                    # shape OpenAI refuses. "Only this tool, and you must call it"
                    # is the same request.
                    tools = [t for t in tools if t["function"]["name"] == name]
                    choice = "required"
                else:
                    choice = {"type": "function", "function": {"name": name}}
            kwargs["tools"] = tools
            kwargs["tool_choice"] = choice
        if self._reasoning is not None:
            kwargs["reasoning_effort"] = self._reasoning
            # drop_params would otherwise drop it, silently, for any model LiteLLM's
            # table does not list as reasoning — every GPT-6 model, when this was
            # written — and the model would run at its own default effort instead.
            kwargs["allowed_openai_params"] = ["reasoning_effort"]
        return kwargs

    async def _model_stream(
        self, contents: list[Turn], request: Request
    ) -> AsyncIterator[ModelChunk]:
        stream = await litellm.acompletion(**self._arguments(contents, request))
        # Tool calls arrive in pieces, by index: an id and a name, then the
        # arguments a few characters at a time. They are whole once the response
        # ends.
        calls: dict[int, dict[str, str]] = {}
        usage: ModelUsage | None = None
        async for chunk in stream:  # pyright: ignore[reportGeneralTypeIssues]
            if getattr(chunk, "usage", None):
                usage = _usage(chunk.usage)
            for choice in getattr(chunk, "choices", None) or []:
                delta = choice.delta
                if delta is None:
                    continue
                if delta.content:
                    part = {"type": "text", "text": delta.content}
                    yield ModelChunk([ModelPart("text", part, text=delta.content)])
                for tc in delta.tool_calls or []:
                    slot = calls.setdefault(tc.index or 0, {"id": "", "name": "", "arguments": ""})
                    slot["id"] = tc.id or slot["id"]
                    if tc.function is not None:
                        slot["name"] = tc.function.name or slot["name"]
                        slot["arguments"] += tc.function.arguments or ""
        parts: list[ModelPart] = []
        for index in sorted(calls):
            slot = calls[index]
            call = {
                "type": "function_call",
                "call_id": slot["id"] or f"call_{index}",
                "name": slot["name"],
                "arguments": slot["arguments"] or "{}",
            }
            parts.append(ModelPart("call", call, call=call))
        if parts:
            yield ModelChunk(parts)
        yield ModelChunk(finished=True, usage=usage)


def _messages(system: str, contents: list[Turn]) -> list[dict[str, Any]]:
    """The context as chat messages: one assistant message per model turn, its
    words and its calls together, and one tool message per result."""
    messages: list[dict[str, Any]] = [{"role": "system", "content": system}] if system else []
    for turn in contents:
        if turn.role == "user":
            messages.append({"role": "user", "content": turn.text})
        elif turn.role == "results":
            messages.extend(
                {"role": "tool", "tool_call_id": p["call_id"], "content": p["output"]}
                for p in turn.parts
            )
        else:
            calls = [
                {
                    "id": p["call_id"],
                    "type": "function",
                    "function": {"name": p["name"], "arguments": p["arguments"]},
                }
                for p in turn.parts
                if p.get("type") == "function_call"
            ]
            message: dict[str, Any] = {"role": "assistant", "content": turn.text or None}
            if calls:
                message["tool_calls"] = calls
            if turn.text or calls:
                messages.append(message)
    return messages


def _usage(usage: Any) -> ModelUsage:
    """LiteLLM's counts in the voice core's names. ``completion_tokens`` includes
    the reasoning, which is counted apart here; a cache write is reported only by
    the providers that bill it."""
    prompt_details = getattr(usage, "prompt_tokens_details", None)
    reasoning = getattr(getattr(usage, "completion_tokens_details", None), "reasoning_tokens", None)
    completion = getattr(usage, "completion_tokens", None)
    write = getattr(usage, "cache_creation_input_tokens", None)
    if write is None:
        write = getattr(prompt_details, "cache_creation_tokens", None)
    return ModelUsage(
        input=getattr(usage, "prompt_tokens", None),
        cached_input=getattr(prompt_details, "cached_tokens", None),
        cache_write=write,
        output=None if completion is None else completion - (reasoning or 0),
        reasoning=reasoning,
    )
