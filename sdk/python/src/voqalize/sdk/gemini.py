"""A Gemini-backed Brain: the voice core, speaking to Gemini.

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

How a turn goes — the model speaks first, a tool's result waits for the next
request unless the tool is :func:`needs_result_now`, the context records what was
heard, and every turn reports what it cost — is the voice core's, and is the same
on every model: :mod:`voqalize.sdk.voice`. This module is only Gemini's half:
the request, the stream, and the context in Gemini's own ``types.Content``.
"""

from __future__ import annotations

import functools
import inspect
import os
from collections.abc import AsyncIterator, Callable
from typing import Any, get_type_hints

from google import genai
from google.genai import _extra_utils, types  # pyright: ignore[reportPrivateUsage]
from pydantic import BaseModel

from .voice import (
    _RETRY_TEXT,  # pyright: ignore[reportPrivateUsage]
    TOOL_BUDGET_MS,
    ModelChunk,
    ModelPart,
    ModelUsage,
    ToolChoice,
    VoiceBrain,
    _needs_result_now,  # pyright: ignore[reportPrivateUsage]
    _require_async,  # pyright: ignore[reportPrivateUsage]
    needs_result_now,
)

# Lived here before the voice core did, and brains still import them from here.
# The `as` form is what makes each an explicit re-export.
from .voice import _SPOKEN_CALL_HEADS as _SPOKEN_CALL_HEADS  # pyright: ignore[reportPrivateUsage]
from .voice import _looks_like_call as _looks_like_call  # pyright: ignore[reportPrivateUsage]
from .voice import _Unit as _Unit  # pyright: ignore[reportPrivateUsage]

__all__ = ["DEFAULT_MODEL", "TOOL_BUDGET_MS", "VOICE_THINKING", "GeminiBrain", "needs_result_now"]

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

# The retry's note, as Gemini takes it. One object, so a request can be checked
# for carrying it by identity.
_RETRY_NOTE = types.Content(role="user", parts=[types.Part(text=_RETRY_TEXT)])

# The config of a turn's last request once ``max_tool_hops`` is spent, and of
# every request made with ``tools=ToolChoice.NONE``. The tools stay declared, so
# the calls already in the context still read; the model may not make another,
# so it has to answer.
_ANSWER_NOW = types.ToolConfig(
    function_calling_config=types.FunctionCallingConfig(mode=types.FunctionCallingConfigMode.NONE)
)


class GeminiBrain(VoiceBrain[types.Content, types.GenerateContentConfig]):
    """Base for a Gemini-backed brain. Override the prompt, the greeting and
    :attr:`tools`; the turn shape, the tool loop and the context come from the
    voice core (:class:`~voqalize.sdk.voice.VoiceBrain`).

    ``max_tool_hops`` caps how many times one turn asks the model again for the
    result of a tool marked :func:`needs_result_now`. The last of those times
    may not call a tool, so the model has to answer. Unmarked tools never ask
    again, so they never count.

    ``report_usage=False`` keeps each turn's token counts off the wire; they stay
    in the ``turn:`` log line either way."""

    provider = "gemini"

    def __init__(
        self,
        *,
        client: genai.Client,
        system_instruction: str,
        model: str = DEFAULT_MODEL,
        max_tool_hops: int = 6,
        report_usage: bool = True,
    ) -> None:
        super().__init__(model=model, max_tool_hops=max_tool_hops, report_usage=report_usage)
        self._client = client
        self._config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            thinking_config=VOICE_THINKING,
        )
        # The tool loop is ours: google-genai declares the tools and never runs
        # them, so a call's result reaches the model only when we ask again.
        self._afc = types.AutomaticFunctionCallingConfig(disable=True)

    # ─── Context ────────────────────────────────────────────────────────

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

        For a sentence, :meth:`~voqalize.sdk.voice.VoiceBrain.append_note` is the
        same thing on every model. This one is for what only Gemini takes: a
        ``Content`` is whatever Gemini takes, so handing the model a screenshot or
        a PDF is this same call with a different part. The role must be ``user``:
        the model's side of a conversation is written by the model.

        Append the **act**, not the screen, and know that it appends
        **immediately, once, where you call it** — the rules are
        :meth:`~voqalize.sdk.voice.VoiceBrain.append_note`'s.
        """
        if content.role != "user":
            raise ValueError(
                f"append_to_context takes user content, got role={content.role!r}. "
                "The model's side of a conversation is written by the model."
            )
        self._history.append(content)

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
        there is no decorator to learn to declare one. It is read per turn, so the
        list can depend on the user.

        **Every tool returns within** :data:`TOOL_BUDGET_MS`, and its result
        reaches the model with the next request, not this one. Mark the tools
        whose result the model needs to say this reply with
        :func:`needs_result_now`, and only those.

        **The method is the declaration.** Its name is the name the model calls,
        its docstring is the description the model reads, and its single pydantic
        parameter is the schema. Nothing is declared twice.

        Take one model, or nothing at all. Not because flatness is unsupported —
        a flat ``str``, ``int`` or ``list[str]`` runs — but because a flat
        parameter is the one google-genai's argument conversion, which this uses,
        never parses. It checks each against
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

    async def _run(self, tool: Callable[..., Any] | None, call: types.FunctionCall) -> types.Part:
        """Run one call and return its response.

        The arguments are built exactly as google-genai's own loop builds them —
        whole numbers back to ``int``, each pydantic parameter validated out of
        the JSON — so a tool behaves here as it did under it. Timing, the budget
        and turning a raise into ``{'error': …}`` are the voice core's.
        """
        name = call.name or ""
        args: dict[str, Any] = {}
        if tool is not None:
            args = _extra_utils.convert_number_values_for_dict_function_call_args(call.args or {})

        async def run() -> Any:
            assert tool is not None  # the voice core runs this only for a declared tool
            return await _extra_utils.invoke_function_from_dict_args_async(args, tool)

        response = await self._invoke_tool(tool, name, run)
        return types.Part(
            function_response=types.FunctionResponse(id=call.id, name=name, response=response)
        )

    # ─── The provider layer ─────────────────────────────────────────────

    def _new_user_turn(self, text: str) -> types.Content:
        return types.Content(role="user", parts=[types.Part(text=text)])

    def _new_model_turn(self, parts: list[Any]) -> types.Content:
        return types.Content(role="model", parts=list(parts))

    def _new_results_turn(self) -> types.Content:
        return types.Content(role="user", parts=[])

    def _retry_note_turn(self) -> types.Content:
        return _RETRY_NOTE

    def _turn_parts(self, turn: types.Content) -> list[Any]:
        return list(turn.parts or [])

    def _set_turn_parts(self, turn: types.Content, parts: list[Any]) -> None:
        turn.parts = parts

    def _new_text_part(self, text: str) -> types.Part:
        return types.Part(text=text)

    def _part_text(self, part: types.Part) -> str:
        return part.text or ""

    def _set_part_text(self, part: types.Part, text: str) -> None:
        part.text = text

    def _part_is_thought(self, part: types.Part) -> bool:
        return bool(part.thought)

    def _part_is_call(self, part: types.Part) -> bool:
        return part.function_call is not None

    def _turn_request(self, tools: ToolChoice | None) -> types.GenerateContentConfig:
        config = self._turn_config()
        if tools is None or tools.mode == "auto" or not config.tools:
            return config
        if tools.mode == "none":
            return config.model_copy(update={"tool_config": _ANSWER_NOW})
        only = types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(
                mode=types.FunctionCallingConfigMode.ANY,
                allowed_function_names=[tools.name or ""],
            )
        )
        return config.model_copy(update={"tool_config": only})

    def _answer_now_request(
        self, request: types.GenerateContentConfig
    ) -> types.GenerateContentConfig:
        return request.model_copy(update={"tool_config": _ANSWER_NOW})

    def _request_tools(self, request: types.GenerateContentConfig) -> dict[str, Callable[..., Any]]:
        return {fn.__name__: fn for fn in request.tools or [] if callable(fn)}

    def _call_name(self, call: types.FunctionCall) -> str:
        return call.name or ""

    async def _model_stream(
        self, contents: list[types.Content], request: types.GenerateContentConfig
    ) -> AsyncIterator[ModelChunk]:
        async for chunk in await self._client.aio.models.generate_content_stream(
            model=self._model, contents=contents, config=request
        ):
            yield ModelChunk(
                parts=[_model_part(p) for p in _chunk_parts(chunk)],
                finished=_finished(chunk),
                malformed=_malformed(chunk),
                usage=_usage(chunk.usage_metadata),
            )


def _model_part(part: types.Part) -> ModelPart:
    """One Gemini part, as the voice core reads it. ``thought`` parts carry text
    that is reasoning, not speech."""
    if part.function_call:
        return ModelPart("call", part, call=part.function_call)
    if part.thought:
        return ModelPart("thought", part)
    if part.text:
        return ModelPart("text", part, text=part.text)
    return ModelPart("other", part)


def _usage(meta: types.GenerateContentResponseUsageMetadata | None) -> ModelUsage | None:
    """Gemini's counts in the voice core's names. ``prompt_token_count`` already
    includes the cached part; thoughts are billed as output and counted apart.

    Gemini leaves a count out when it is zero — no cache hit, no thinking — so
    once it has reported the prompt, a missing cached or thoughts count is a
    zero, not an unknown."""
    if meta is None:
        return None
    reported = meta.prompt_token_count is not None
    return ModelUsage(
        input=meta.prompt_token_count,
        cached_input=meta.cached_content_token_count or (0 if reported else None),
        output=meta.candidates_token_count,
        reasoning=meta.thoughts_token_count or (0 if reported else None),
    )


def _chunk_parts(chunk: types.GenerateContentResponse) -> list[types.Part]:
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

    ``async def`` is required, for the reason
    :func:`~voqalize.sdk.voice._require_async` gives.

    **A bound method must not cross this line.** google-genai deep-copies the
    config it is handed, on every request, and
    ``copy.deepcopy`` of a bound method copies ``__self__`` with it, by definition
    (``copy._deepcopy_method``). The tools it then calls belong to a *clone* of the
    brain: ``self.session.dispatch`` reaching nothing, the context written to an
    object no one reads, the model told ``ok``, and not one thing on the wire to
    say so. Ours happens to hold a ``genai.Client``, whose lock cannot be copied at
    all, so we got a crash instead of that silence — the only luck in it. A plain
    function is atomic to ``deepcopy``, so this closure is what we hand over and
    the brain stays here.

    The wrapper carries the tool's :func:`needs_result_now` mark, and nothing
    else of the loop: timing, catching and asking again are the voice core's.

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
    strings, and two different things are read: ``get_type_hints`` to build the
    *declaration*, which resolves them, and ``inspect.signature`` to build the
    *call* (google-genai's own argument conversion, which we use), which does
    not. Left alone, a tool declares a perfect schema and then raises on every
    call — and the error goes to the model, which narrates
    it as success. Both go on the closure, so the method the developer wrote is
    handed over unread and comes back unchanged.
    """
    _require_async(fn)

    @functools.wraps(fn)
    async def tool(*args: Any, **kwargs: Any) -> Any:
        return await fn(*args, **kwargs)

    if _needs_result_now(fn):
        needs_result_now(tool)
    tool.__annotations__ = get_type_hints(fn)
    tool.__signature__ = inspect.signature(fn, eval_str=True)  # pyright: ignore[reportFunctionMemberAccess]
    for annotation in tool.__annotations__.values():
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            annotation.model_rebuild()
    return tool


def _finished(chunk: types.GenerateContentResponse) -> bool:
    """True on the last chunk of a response."""
    return any(c.finish_reason is not None for c in chunk.candidates or [])


#: Finish reasons that end a response with nothing to run and nothing said.
#: ``MALFORMED_RESPONSE`` is newer than some ``google-genai`` releases, which warn
#: that it is not a ``FinishReason`` and keep it anyway; so it is matched by its
#: value, not by a member that may not exist.
_MALFORMED_REASONS = frozenset({"MALFORMED_FUNCTION_CALL", "MALFORMED_RESPONSE"})


def _malformed(chunk: types.GenerateContentResponse) -> bool:
    """True when the response ended because the model's output did not parse —
    a function call, or the response as a whole: there is no call to run, and
    the stream just ends with nothing said."""
    return any(
        getattr(c.finish_reason, "value", c.finish_reason) in _MALFORMED_REASONS
        for c in chunk.candidates or []
    )
