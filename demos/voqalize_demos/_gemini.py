"""Shared scaffolding for Gemini-backed demo brains.

A ``GeminiBrain`` is a conversational ``voqalize.sdk.Brain`` that:

- builds each turn's working context from the framework's faithful (heard)
  transcript (``interaction.conversation``), so past turns are the heard truth;
- streams one inference per LLM call (1:1 with the wire), speaking text chunks;
- if the subclass declares ``tools``, runs the function-calling loop — speak a
  line, call a tool (which drives the browser via ``interaction.action``), feed
  the result back — up to ``max_tool_hops``.

Subclasses provide the system prompt, optional tool schemas, a
:meth:`dispatch_tool` implementation, and their opening line. This factors out
the Gemini plumbing every demo brain shares; it is **not** an LLM abstraction
(the concrete :class:`GeminiProvider` is injected) — just common brain shape.
This is the pattern a customer would follow to build one brain and share
scaffolding across several.
"""

from __future__ import annotations

import os
from typing import Any

from google.genai import types

from voqalize.sdk import Brain
from voqalize_demos.llm import GeminiProvider

# Overridable because free-tier Gemini quotas are per model — when one model's
# daily bucket is spent (an eval run, a long demo day), pointing the process at
# a sibling model is the difference between "demo works" and "come back
# tomorrow". Production sets nothing and gets the default.
DEFAULT_MODEL = os.environ.get("DEMOS_GEMINI_MODEL", "gemini-3.7-flash")

# The least thinking this model allows, for lowest voice latency: on a voice turn
# a reasoning budget is spent in silence the caller sits through, and the thought
# parts are never spoken, so the cost has no audible half at all.
#
# BOTH HALVES OF THIS LINE ARE MODEL-SPECIFIC — measure, do not assume, when you
# change DEFAULT_MODEL. Two ways it bites, each verified against the live API on
# 2026-08-14:
#
#   - The KNOB moved. `thinking_budget=0` is what the 3.1 models took; 3.5+ reject
#     it with a bare `400 INVALID_ARGUMENT` ("Request contains an invalid
#     argument") that names no field.
#   - The FLOOR moved. `thinking_level=MINIMAL` works on 3.5, and 3.7 refuses it
#     ("Thinking level MINIMAL is not supported for this model"). LOW is 3.7's
#     floor and it still spends ~275 thought tokens — there is no zero-thinking
#     setting on this model.
#
# And the floor that a model *accepts* is not automatically one it works at:
# gemini-3.5-flash-lite takes MINIMAL happily, then calls `open_itinerary` on only
# 9 of 15 identical travel-demo turns (LOW: 11/15; MEDIUM fixes it at ~1s/turn).
# It was shipped to dev on that basis and the smoke suite caught it. So when you
# move models, re-run the tool-call check — a model that answers is not the same
# as a model that acts.
VOICE_THINKING = types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)

# Appended to a hybrid greeting prompt so the model, having heard the caller's
# fixed opener already spoken, continues instead of greeting a second time.
_CONTINUE_AFTER_OPENER = (
    " You have JUST said a brief hello out loud, so do not open with another "
    "greeting or say 'hello' again — continue straight into what you have to say."
)

# A one-word hello per demo language, for the instant opener of a hybrid greeting
# (the LLM-generated remainder then follows in the caller's language). Falls back
# to English for anything unmapped.
#
# THE TRAILING "…" IS LOAD-BEARING — do not tidy it away. pipecat's
# SimpleTextAggregator holds a sentence back after terminal punctuation until a
# non-whitespace LOOKAHEAD character arrives (there is no unambiguous fast path,
# not even for the danda), so a bare "Hi!" sits in the buffer until the LLM's
# first chunk lands and the "instant" opener is not instant — measured at ~1.3 s
# on a prod call, where the first synthesis was the glued "Hi!Evening, Rajesh.".
# The ellipsis IS that lookahead char, and punkt then closes the sentence over
# the whole string, so the opener flushes on its own. Verified inaudible against
# a deployed host: same audio duration (±0.05 s) and an identical TTS→STT
# round-trip transcript, in English and Devanagari.
_HELLO_BY_LANGUAGE = {
    "english": "Hi!…",
    "hindi": "नमस्ते!…",
    "telugu": "నమస్తే!…",
    "tamil": "வணக்கம்!…",
    "kannada": "ನಮಸ್ಕಾರ!…",
    "marathi": "नमस्कार!…",
    "bengali": "নমস্কার!…",
}


def hello_for(language_name: str) -> str:
    """A short, language-appropriate opener for a hybrid greeting; English default."""
    return _HELLO_BY_LANGUAGE.get((language_name or "").strip().lower(), "Hi!…")


class GeminiBrain(Brain):
    """Base for a Gemini-backed demo brain. Override the prompt/tools/greeting."""

    def __init__(
        self,
        *,
        llm: GeminiProvider,
        system_instruction: str,
        tools: types.ToolListUnion | None = None,
        model: str = DEFAULT_MODEL,
        max_tool_hops: int = 6,
    ) -> None:
        self._llm = llm
        self._model = model
        self._max_tool_hops = max_tool_hops
        cfg: dict[str, Any] = {
            "system_instruction": system_instruction,
            "thinking_config": VOICE_THINKING,
        }
        if tools is not None:
            cfg["tools"] = tools
            # We drive the tool loop ourselves (one inference per LLM call).
            cfg["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(disable=True)
        self._config = types.GenerateContentConfig(**cfg)

    # ─── Default interaction handler ────────────────────────────────────

    async def on_interaction(self, interaction) -> None:
        await self.respond(interaction)

    async def respond(self, interaction) -> None:
        """Standard turn: stream the model over the heard transcript; if it calls
        tools, dispatch them and feed the results back, up to ``max_tool_hops``.
        Each LLM call is one ``interaction.say()`` bracket (1:1 with the wire)."""
        contents = self.working_context(interaction)
        for _ in range(self._max_tool_hops):
            async with interaction.say() as inf:
                fcalls, model_parts = await self.stream(inf, contents)
            if model_parts:
                contents.append(types.Content(role="model", parts=model_parts))
            if not fcalls:
                return
            for fc in fcalls:
                result = self.dispatch_tool(interaction, fc.name, dict(fc.args or {}))
                contents.append(
                    types.Content(
                        role="tool",
                        parts=[
                            types.Part.from_function_response(
                                name=fc.name, response={"result": result}
                            )
                        ],
                    )
                )

    def dispatch_tool(self, interaction, name: str, args: dict[str, Any]) -> str:
        """Run one tool call: mutate state + drive the browser via
        ``interaction.action(...)``; return a short string result fed back to the
        model. Override in any brain that declares ``tools``."""
        raise NotImplementedError(
            f"{type(self).__name__} declared no tools but the model called {name!r}"
        )

    # ─── Gemini plumbing (shared) ───────────────────────────────────────

    def grounding(self, interaction) -> str | None:
        """Optional authoritative context folded into every turn — typically the
        live on-screen state a browser pushes via ``on_client_message`` (``state_sync``).
        Override to return a text note; the base inserts it **just before the
        latest user turn** so an ambiguous question is grounded in what's on screen.
        Default: no grounding."""
        return None

    def working_context(self, interaction) -> list[types.Content]:
        """Gemini contents from the heard transcript (already incl. this user
        utterance), with any :meth:`grounding` note inserted just before the latest
        user turn. Skips assistant turns before the first user turn (e.g. an opening
        greeting) so contents always start with a user turn."""
        out: list[types.Content] = []
        seen_user = False
        for m in interaction.conversation.messages:
            if m.role == "user":
                seen_user = True
                out.append(types.Content(role="user", parts=[types.Part(text=m.content)]))
            elif seen_user:
                out.append(types.Content(role="model", parts=[types.Part(text=m.content)]))
        note = self.grounding(interaction)
        if note:
            # Insert before the latest user turn (the current question) so the
            # model reads the on-screen state as context, then the question.
            insert_at = len(out)
            for i in range(len(out) - 1, -1, -1):
                if out[i].role == "user":
                    insert_at = i
                    break
            out.insert(insert_at, types.Content(role="user", parts=[types.Part(text=note)]))
        return out

    async def stream(
        self, inf, contents: list[types.Content]
    ) -> tuple[list[Any], list[types.Part]]:
        """Stream one inference into ``inf``: speak text chunks, collect any
        function calls and the raw model parts (kept verbatim so Gemini-3
        thought signatures survive the round-trip). Returns ``(fcalls, parts)``."""
        fcalls: list[Any] = []
        model_parts: list[types.Part] = []
        gen = await self._llm.stream(model=self._model, contents=contents, config=self._config)
        async for chunk in gen:
            for cand in chunk.candidates or []:
                for part in (cand.content.parts or []) if cand.content else []:
                    model_parts.append(part)
                    if part.text:
                        await inf.speak(part.text)
                    if part.function_call:
                        fcalls.append(part.function_call)
        return fcalls, model_parts

    # ─── Agent-initiated speech helpers (greetings) ─────────────────────

    async def say(self, session, text: str) -> None:
        """Speak a fixed line as an agent-initiated inference (no LLM call)."""
        async with session.say() as inf:
            await inf.speak(text)

    async def generate(self, session, prompt: str) -> None:
        """Speak an LLM-generated opening from a one-shot prompt (interaction 0)."""
        async with session.say() as inf:
            await self.stream(inf, [types.Content(role="user", parts=[types.Part(text=prompt)])])

    async def say_then_generate(self, session, opener: str, prompt: str) -> None:
        """Hybrid greeting for brains whose opener must stay dynamic (language,
        per-session facts, a first question): speak a fixed ``opener`` **first**
        (instant audio, no LLM), then stream the LLM-generated remainder in the
        **same** inference so the model's ~1s first-token latency is hidden behind
        the opener the caller already heard. A standing guard is appended so the
        model doesn't greet a second time."""
        async with session.say() as inf:
            await inf.speak(opener)
            await self.stream(
                inf,
                [
                    types.Content(
                        role="user", parts=[types.Part(text=prompt + _CONTINUE_AFTER_OPENER)]
                    )
                ],
            )
