"""An OpenAI-backed Brain: the voice core, speaking to OpenAI's Responses API.

    from openai import AsyncOpenAI
    from voqalize.sdk.openai import OpenAIBrain

    class Concierge(OpenAIBrain):
        def __init__(self) -> None:
            super().__init__(
                client=AsyncOpenAI(),
                system_instruction="You are …",
                model="gpt-6-sol",
                reasoning="low",
            )

        async def greet(self, session):
            return "Hi! What can I do for you?"

        @property
        def tools(self):
            return [self.open_booking]

        async def open_booking(self, args: OpenBooking) -> str:
            "Put the booking form on screen."
            self.session.dispatch(args)
            return "ok"

Install with ``pip install voqalize-agent-sdk[openai]``. Nothing in
``voqalize.sdk`` imports this module, so the core SDK stays free of ``openai``.

The turn — speech first, tools mid-sentence, results filed for the next request
unless :func:`~voqalize.sdk.voice.needs_result_now`, history cut to what was
heard, a :class:`~voqalize.sdk.TurnUsage` per turn — is the voice core's
(:mod:`voqalize.sdk.voice`) and is the same on every model. This module is only
OpenAI's half:

- **The conversation stays in this process.** Every request sends the whole
  context with ``store=False`` and no ``previous_response_id``: a conversation
  kept on OpenAI's side cannot be told that the user heard only half of the last
  sentence. Reasoning items come back encrypted and go back in as they came, so a
  reasoning model keeps its thread across a tool call.
- **Tools are declared from their signatures.** One pydantic model parameter is
  declared flat — the model fills its fields directly — and validated by that
  model before the tool runs; plain parameters work too.
- **Reasoning** is ``reasoning="none" | "low" | "medium" | "high"``, as the model
  takes it. On a voice turn every reasoning token is silence the user sits
  through, so start low and measure.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from typing import Any

from openai import AsyncOpenAI

from ._portable import PortableBrain, Request, Turn
from .voice import TOOL_BUDGET_MS, ModelChunk, ModelPart, ModelUsage, ToolChoice, needs_result_now

__all__ = ["TOOL_BUDGET_MS", "OpenAIBrain", "needs_result_now"]


class OpenAIBrain(PortableBrain):
    """Base for an OpenAI-backed brain. Override the prompt, the greeting and
    :attr:`~voqalize.sdk.voice.VoiceBrain.tools`; the turn shape, the tool loop and
    the context come from the voice core.

    ``reasoning`` is the model's reasoning effort, or ``None`` for its default.
    ``options`` are passed to every ``responses.create`` call as they are — a
    ``prompt_cache_key``, a ``service_tier``, a ``max_output_tokens`` — for what
    this class does not name. ``max_tool_hops`` and ``report_usage`` are the voice
    core's."""

    provider = "openai"

    def __init__(
        self,
        *,
        client: AsyncOpenAI,
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
        self._client = client
        self._reasoning = reasoning
        self._options = dict(options or {})

    def _arguments(self, contents: list[Turn], request: Request) -> dict[str, Any]:
        """One ``responses.create`` call's arguments."""
        kwargs: dict[str, Any] = {
            "model": self._model,
            "instructions": self._system_instruction,
            "input": _input(contents),
            "stream": True,
            "store": False,
            **self._options,
        }
        if request.tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                    "strict": False,
                }
                for t in request.tools
            ]
            kwargs["tool_choice"] = _choice(request.choice)
        if self._reasoning is not None:
            kwargs["reasoning"] = {"effort": self._reasoning}
            # Kept out of OpenAI's storage, the reasoning has to travel with the
            # context, and this is how it comes back to us to send.
            kwargs["include"] = ["reasoning.encrypted_content"]
        return kwargs

    async def _model_stream(
        self, contents: list[Turn], request: Request
    ) -> AsyncIterator[ModelChunk]:
        stream = await self._client.responses.create(**self._arguments(contents, request))
        async for event in stream:
            match event.type:
                case "response.output_text.delta" | "response.refusal.delta":
                    delta: str = event.delta  # pyright: ignore[reportAttributeAccessIssue]
                    if delta:
                        part = {"type": "text", "text": delta}
                        yield ModelChunk([ModelPart("text", part, text=delta)])
                case "response.output_item.done":
                    item = event.item  # pyright: ignore[reportAttributeAccessIssue]
                    if item.type == "function_call":
                        call = {
                            "type": "function_call",
                            "call_id": item.call_id,
                            "name": item.name,
                            "arguments": item.arguments,
                        }
                        yield ModelChunk([ModelPart("call", call, call=call)])
                    elif item.type == "reasoning":
                        raw: dict[str, Any] = item.model_dump(exclude_none=True, mode="json")
                        raw.pop("status", None)
                        yield ModelChunk([ModelPart("thought", raw)])
                case "response.completed" | "response.incomplete":
                    response = event.response  # pyright: ignore[reportAttributeAccessIssue]
                    yield ModelChunk(finished=True, usage=_usage(response.usage))
                case "response.failed":
                    error = event.response.error  # pyright: ignore[reportAttributeAccessIssue]
                    raise RuntimeError(f"OpenAI response failed: {error}")
                case "error":
                    raise RuntimeError(f"OpenAI stream error: {event.message}")  # pyright: ignore[reportAttributeAccessIssue]
                case _:
                    pass


def _choice(choice: ToolChoice) -> Any:
    match choice.mode:
        case "none":
            return "none"
        case "only":
            return {"type": "function", "name": choice.name}
        case _:
            return "auto"


def _input(contents: list[Turn]) -> list[dict[str, Any]]:
    """The context as Responses API input items.

    A model turn's text pieces become one assistant message per run of text, in
    place among its calls. A reasoning item goes back only ahead of something it
    produced: one whose words were all cut by a barge-in has nothing after it, and
    the API refuses reasoning that precedes nothing."""
    items: list[dict[str, Any]] = []
    for turn in contents:
        if turn.role == "user":
            items.append({"role": "user", "content": turn.text})
            continue
        if turn.role == "results":
            items.extend(
                {"type": "function_call_output", "call_id": p["call_id"], "output": p["output"]}
                for p in turn.parts
            )
            continue
        words: list[str] = []
        for i, part in enumerate(turn.parts):
            kind = part.get("type")
            if kind == "text":
                words.append(part["text"])
                continue
            if words:
                items.append({"role": "assistant", "content": "".join(words)})
                words = []
            if kind == "reasoning":
                if any(p.get("type") != "reasoning" for p in turn.parts[i + 1 :]):
                    items.append(part)
            elif kind == "function_call":
                items.append(
                    {
                        "type": "function_call",
                        "call_id": part["call_id"],
                        "name": part["name"],
                        "arguments": part["arguments"],
                    }
                )
        if words:
            items.append({"role": "assistant", "content": "".join(words)})
    return items


def _usage(usage: Any) -> ModelUsage | None:
    """OpenAI's counts in the voice core's names. ``output_tokens`` includes the
    reasoning, which is counted apart here."""
    if usage is None:
        return None
    reasoning = getattr(usage.output_tokens_details, "reasoning_tokens", None)
    details = usage.input_tokens_details
    return ModelUsage(
        input=usage.input_tokens,
        cached_input=getattr(details, "cached_tokens", None),
        cache_write=getattr(details, "cache_write_tokens", None),
        output=None if usage.output_tokens is None else usage.output_tokens - (reasoning or 0),
        reasoning=reasoning,
    )
