"""What the JSON-schema layers share: a turn of plain dicts, and tools declared
and called from their own signatures with pydantic alone.

:class:`~voqalize.sdk.openai.OpenAIBrain` and
:class:`~voqalize.sdk.litellm.LiteLLMBrain` keep the conversation as
:class:`Turn` values and render it into their API's shape on every request. A
tool is declared from its signature — one pydantic model parameter, plain
parameters, or none — and its arguments are validated by the same pydantic
model before it runs. No vendor import here.
"""

from __future__ import annotations

import copy
import inspect
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, get_type_hints

from pydantic import BaseModel, create_model
from pydantic_core import to_json

from .voice import ToolChoice, VoiceCore, _require_async  # pyright: ignore[reportPrivateUsage]

__all__ = ["PortableBrain", "Request", "Tool", "Turn", "declare"]


@dataclass(eq=False)
class Turn:
    """One turn of a conversation kept as plain dicts.

    ``role`` is ``"user"`` (the user's words, and notes about them), ``"model"``
    (what the model wrote) or ``"results"`` (function responses). Each part is a
    dict with a ``type``:

    - ``{"type": "text", "text": …}`` — words.
    - ``{"type": "reasoning", …}`` — a provider's reasoning item, kept as it came.
    - ``{"type": "function_call", "call_id": …, "name": …, "arguments": "<json>"}``
    - ``{"type": "function_call_output", "call_id": …, "output": "<json>"}``

    Compared by identity, like every turn the voice core tracks.
    """

    role: Literal["user", "model", "results"]
    parts: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())

    @property
    def text(self) -> str:
        """The turn's words, joined."""
        return "".join(p.get("text", "") for p in self.parts if p.get("type") == "text")


@dataclass
class Tool:
    """One tool, declared from its signature: the name the model calls, the
    description it reads, the JSON schema of its arguments, and how to call it
    with arguments that schema allows."""

    name: str
    description: str
    parameters: dict[str, Any]
    fn: Callable[..., Any]
    _model: type[BaseModel] | None
    _wrapped: bool

    async def call(self, arguments: dict[str, Any]) -> Any:
        """Validate ``arguments`` against the schema and run the tool. A model
        that sent arguments the schema refuses gets the validation error back as
        the result, which it can read and correct."""
        if self._model is None:
            return await self.fn()
        args = self._model.model_validate(arguments)
        if self._wrapped:
            return await self.fn(args)
        return await self.fn(**{name: getattr(args, name) for name in self._model.model_fields})


def declare(fn: Callable[..., Any]) -> Tool:
    """Declare one tool from its signature.

    - **One pydantic model parameter** — the shape every voice brain uses: the
      schema is the model's own, flat, so the model fills the fields directly.
    - **Plain parameters** (``str``, ``int``, a ``Literal``…): the schema is
      built from them, and each is validated before the call.
    - **None**: an empty object.

    The docstring is the description. ``async def`` is required.
    """
    _require_async(fn)
    name = getattr(fn, "__name__", "tool")
    description = inspect.getdoc(fn) or ""
    hints = get_type_hints(fn)
    params = [
        p
        for p in inspect.signature(fn, eval_str=True).parameters.values()
        if p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
    ]
    if not params:
        empty = {"type": "object", "properties": {}, "additionalProperties": False}
        return Tool(name, description, empty, fn, None, False)
    only = hints.get(params[0].name) if len(params) == 1 else None
    if isinstance(only, type) and issubclass(only, BaseModel):
        only.model_rebuild()
        return Tool(name, description, _schema(only), fn, only, True)
    fields: dict[str, Any] = {
        p.name: (hints.get(p.name, Any), ... if p.default is p.empty else p.default) for p in params
    }
    model = create_model(f"{name}_arguments", **fields)
    return Tool(name, description, _schema(model), fn, model, False)


def _schema(model: type[BaseModel]) -> dict[str, Any]:
    """A model's JSON schema with every ``$ref`` written out in place, since not
    every provider behind a gateway resolves them."""
    schema = model.model_json_schema()
    defs: dict[str, Any] = schema.pop("$defs", {})

    def inline(node: Any) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                target = copy.deepcopy(defs[ref.removeprefix("#/$defs/")])
                rest = {k: v for k, v in node.items() if k != "$ref"}
                return inline({**target, **rest})
            return {k: inline(v) for k, v in node.items()}
        if isinstance(node, list):
            return [inline(v) for v in node]
        return node

    out = inline(schema)
    out.pop("title", None)
    out.setdefault("properties", {})
    return out


def arguments(raw: str | None) -> dict[str, Any]:
    """A call's arguments, parsed. Raises ``ValueError`` on text that is not a
    JSON object, which the voice core returns to the model as the call's error."""
    parsed = json.loads(raw or "{}")
    if not isinstance(parsed, dict):
        raise ValueError(f"arguments must be a JSON object, got {raw!r}")
    return parsed


def output(response: dict[str, Any]) -> str:
    """A function response as the JSON text the model reads."""
    return to_json(response, fallback=str).decode()


@dataclass
class Request:
    """One turn's request settings for a JSON-schema layer: the tools declared,
    and which of them the model may call."""

    tools: list[Tool]
    choice: ToolChoice


class PortableBrain(VoiceCore[Turn, Request]):
    """The half that :class:`~voqalize.sdk.openai.OpenAIBrain` and
    :class:`~voqalize.sdk.litellm.LiteLLMBrain` share: the context as
    :class:`Turn` values, tools declared from their signatures, and calls run
    against those declarations. A layer adds the one call to its API."""

    def __init__(
        self,
        *,
        model: str,
        system_instruction: str,
        max_tool_hops: int = 6,
        report_usage: bool = True,
    ) -> None:
        super().__init__(model=model, max_tool_hops=max_tool_hops, report_usage=report_usage)
        self._system_instruction = system_instruction
        # The declarations the turn under way was asked with, by name, so a call
        # is validated against exactly the schema the model was shown.
        self._declared: dict[str, Tool] = {}

    @property
    def system_instruction(self) -> str:
        """The prompt every request carries. Settable from
        :meth:`~voqalize.sdk.Brain.on_session_start`, where the facts that are
        true for this user and no other are finally in hand. Setting it replaces
        the prompt for the rest of the session."""
        return self._system_instruction

    @system_instruction.setter
    def system_instruction(self, text: str) -> None:
        self._system_instruction = text

    # ─── Tools ──────────────────────────────────────────────────────────

    async def _run(self, tool: Callable[..., Any] | None, call: dict[str, Any]) -> dict[str, Any]:
        name = str(call.get("name", ""))
        declared = self._declared.get(name)

        async def run() -> Any:
            assert declared is not None
            return await declared.call(arguments(call.get("arguments")))

        response = await self._invoke_tool(tool if declared is not None else None, name, run)
        return {
            "type": "function_call_output",
            "call_id": call.get("call_id", ""),
            "output": output(response),
        }

    def _turn_request(self, tools: ToolChoice | None) -> Request:
        declared = [declare(fn) for fn in self.tools]
        self._declared = {t.name: t for t in declared}
        return Request(tools=declared, choice=tools or ToolChoice.AUTO)

    def _answer_now_request(self, request: Request) -> Request:
        return Request(tools=request.tools, choice=ToolChoice.NONE)

    def _request_tools(self, request: Request) -> dict[str, Callable[..., Any]]:
        return {t.name: t.fn for t in request.tools}

    def _call_name(self, call: dict[str, Any]) -> str:
        return str(call.get("name", ""))

    # ─── The context ────────────────────────────────────────────────────

    def _new_user_turn(self, text: str) -> Turn:
        return Turn("user", [{"type": "text", "text": text}])

    def _new_model_turn(self, parts: list[Any]) -> Turn:
        return Turn("model", list(parts))

    def _new_results_turn(self) -> Turn:
        return Turn("results")

    def _turn_parts(self, turn: Turn) -> list[Any]:
        return list(turn.parts)

    def _set_turn_parts(self, turn: Turn, parts: list[Any]) -> None:
        turn.parts = parts

    def _new_text_part(self, text: str) -> dict[str, Any]:
        return {"type": "text", "text": text}

    def _part_text(self, part: dict[str, Any]) -> str:
        return str(part.get("text", "")) if part.get("type") == "text" else ""

    def _set_part_text(self, part: dict[str, Any], text: str) -> None:
        part["text"] = text

    def _part_is_thought(self, part: dict[str, Any]) -> bool:
        return part.get("type") == "reasoning"

    def _part_is_call(self, part: dict[str, Any]) -> bool:
        return part.get("type") == "function_call"
