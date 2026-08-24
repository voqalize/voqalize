"""A Gemini-backed Brain: history, streaming, and the tool loop.

    from google import genai
    from voqalize.sdk.gemini import GeminiBrain

    class Concierge(GeminiBrain):
        def __init__(self) -> None:
            super().__init__(client=genai.Client(), system_instruction="You are …")

        async def greet(self, session):
            return "Hi! What can I do for you?"

Host it the same way as any other brain — :func:`voqalize.sdk.run_session` from
your own WebSocket route, or :func:`voqalize.sdk.serve` over the Cortex relay.

Install with ``pip install voqalize-agent-sdk[gemini]``. Nothing in
``voqalize.sdk`` imports this module, so the core SDK stays free of
``google-genai``.

**The brain owns the transcript, and the transcript is what was heard.** Each
unit of speech goes into :attr:`GeminiBrain.history` as it streams, then
:meth:`~voqalize.sdk.Brain.on_finalize` rewrites it to the delivered prefix. A
reply that generated three sentences and was cut after one is remembered as one —
which is the only version the caller and the model can both agree on.
"""

from __future__ import annotations

import os
from collections import deque
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass
from typing import Any

from google import genai
from google.genai import types

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
    """Base for a Gemini-backed brain. Override the prompt, the tools and the
    greeting; the turn shape, the history and the tool loop come from here."""

    def __init__(
        self,
        *,
        client: genai.Client,
        system_instruction: str,
        tools: types.ToolListUnion | None = None,
        model: str = DEFAULT_MODEL,
        max_tool_hops: int = 6,
    ) -> None:
        self._client = client
        self._model = model
        self._max_tool_hops = max_tool_hops
        config: dict[str, Any] = {
            "system_instruction": system_instruction,
            "thinking_config": VOICE_THINKING,
        }
        if tools is not None:
            config["tools"] = tools
            # We drive the tool loop ourselves, one unit of speech per LLM call.
            config["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(
                disable=True
            )
        self._config = types.GenerateContentConfig(**config)

        #: The conversation, as Gemini contents. Yours to read, seed and persist.
        self.history: list[types.Content] = []
        # Units still awaiting their heard truth, in the order Voqalize will
        # report them. Every unit is here: Voqalize finalizes each unit
        # exactly once whether or not a word of it reached the caller, so a
        # silent one — a bare function call — is reported as heard-nothing and
        # leaves the transcript rather than never being mentioned.
        self._awaiting: deque[_Unit] = deque()

    # ─── The turn ───────────────────────────────────────────────────────

    def on_user_message(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]:
        self.history.append(types.Content(role="user", parts=[types.Part(text=msg.text)]))
        return self.respond(session)

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """Stream the model over the transcript; if it calls tools, dispatch them
        and feed the results back, up to ``max_tool_hops``. One LLM call is one
        unit of speech, so an interruption cuts exactly one of them."""
        for _ in range(self._max_tool_hops):
            calls: list[types.FunctionCall] = []
            yield SpeechStart()
            unit = self._open_unit()
            async for part in self._stream(self.working_context()):
                self._extend_unit(unit, part)
                if part.text:
                    yield Chunk(part.text)
                if part.function_call:
                    calls.append(part.function_call)
            yield SpeechEnd()

            if not calls:
                return
            for call in calls:
                result = self.dispatch_tool(session, call.name or "", dict(call.args or {}))
                self.history.append(
                    types.Content(
                        role="tool",
                        parts=[
                            types.Part.from_function_response(
                                name=call.name or "", response={"result": result}
                            )
                        ],
                    )
                )

    def dispatch_tool(self, session: Session, name: str, args: dict[str, Any]) -> str:
        """Run one tool call: mutate your state, drive the app with
        ``session.dispatch(...)``, and return a short string fed back to the model.
        Override in any brain that declares ``tools``."""
        raise NotImplementedError(
            f"{type(self).__name__} declared no tools but the model called {name!r}"
        )

    # ─── Context ────────────────────────────────────────────────────────

    def grounding(self) -> str | None:
        """Authoritative context folded into every turn — typically the live
        on-screen state the app pushes to
        :meth:`~voqalize.sdk.Brain.on_rtvi`. Return a text note and it is
        inserted **just before the latest user turn**, so an ambiguous question is
        grounded in what the caller is looking at. Default: none."""
        return None

    def working_context(self) -> list[types.Content]:
        """:attr:`history` as the contents for one call, with :meth:`grounding`
        inserted before the latest user turn.

        A leading model turn — the greeting, which answers nothing — is kept.
        Gemini accepts contents that open on `role="model"` and resolves the
        first user turn against it, which is the whole point: "yes please" is
        an answer to the question the agent opened with.
        """
        out = list(self.history)
        note = self.grounding()
        if not note:
            return out
        at = len(out)
        for i in range(len(out) - 1, -1, -1):
            if out[i].role == "user":
                at = i
                break
        out.insert(at, types.Content(role="user", parts=[types.Part(text=note)]))
        return out

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
                self.history.append(types.Content(role="model", parts=[types.Part(text=fin.heard)]))
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
            self.history = [c for c in self.history if c is not unit.content]

    # ─── Plumbing ───────────────────────────────────────────────────────

    def _open_unit(self) -> _Unit:
        """A model turn appended to history now, filled as the stream arrives —
        so an interruption leaves behind exactly what had been generated when it
        landed, ready to be cut down to what was heard."""
        unit = _Unit(types.Content(role="model", parts=[]))
        self.history.append(unit.content)
        self._awaiting.append(unit)
        return unit

    def _extend_unit(self, unit: _Unit, part: types.Part) -> None:
        if unit.content.parts is None:
            unit.content.parts = []
        unit.content.parts.append(part)

    async def _stream(self, contents: list[types.Content]) -> AsyncIterator[types.Part]:
        """One streaming call, flattened to parts. Parts are yielded verbatim so
        thought signatures survive the round-trip into history."""
        stream = await self._client.aio.models.generate_content_stream(
            model=self._model, contents=contents, config=self._config
        )
        async for chunk in stream:
            for candidate in chunk.candidates or []:
                content = candidate.content
                for part in (content.parts or []) if content else []:
                    yield part
