"""Real-model smoke tests — the ADK adapter driving a **live Gemini** end-to-end.

Everywhere else the model is faked (``ScriptedLlm``) so the suite is hermetic and
fast; Runner + SessionService + ``before_model_callback`` are always real ADK. These
tests close the one gap the fake can't: that ADK's *real* contents-assembly and a
*real* model's streaming shape match the assumptions the corrector rides on. If real
ADK ever assembles ``llm_request.contents`` differently, or a real streamed reply's
partial/aggregate shape diverges from the fake's, the correction would silently
mis-fire in production but pass the hermetic suite — this catches that.

Gated on a Gemini API key (``GOOGLE_API_KEY`` / ``GEMINI_API_KEY``); skipped in CI.
Run manually::

    export GOOGLE_API_KEY=...            # or GEMINI_API_KEY
    uv run pytest tests/google_adk/test_adk_real_model.py -q

There is no scripted model here, so a spy ``before_model_callback`` appended **after**
the corrector captures exactly the (corrected) contents the live model is handed — the
same introspection point ``ScriptedLlm.captured_contents`` gives the hermetic tests.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("google.adk")

from google.adk.agents import LlmAgent

from voqalize.conformance import (
    DirectConnection,
    VoiceDriver,
    generate_keypair,
    mint_pygato_token,
)
from voqalize.google_adk.brain import AdkBrain
from voqalize.sdk import DirectAgent, brain_factory

_HAS_KEY = bool(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"))
pytestmark = pytest.mark.skipif(_HAS_KEY is False, reason="no Gemini API key in env")

MODEL = os.environ.get("VOQAL_ADK_TEST_MODEL", "gemini-2.5-flash")
GREETING = "Travel desk, how can I help?"
# Pin the reply's opening so a barge can cut a *known* real prefix off a *longer*
# real generation — heard-truth is then a genuine prefix of what the model produced,
# not a fabricated string. The model still generates the tail itself.
LEAD = "Here is what I found."
INSTRUCTION = (
    "You are a terse travel desk. When you answer a question, begin your reply with "
    f"the exact sentence '{LEAD}' and then add one or two more sentences of detail. "
    "When asked to book, call the book_trip tool, then confirm in one short sentence. "
    "Never read raw ids or codes aloud."
)

_DISPATCHED: list[str] = []


async def book_trip(city: str) -> dict:
    """Book a trip to a city.

    Args:
        city: The destination city.
    """
    _DISPATCHED.append(city)
    return {"pnr": f"TR-{city[:3].upper()}", "status": "confirmed"}


# ─── prompt introspection (over genai ``types.Content``) ──────────────────────


def _text_of(content) -> str:
    return "".join(p.text for p in (content.parts or []) if getattr(p, "text", None))


def _model_texts(contents: list) -> list[str]:
    return [_text_of(c) for c in contents if c.role == "model" and _text_of(c)]


def _user_texts(contents: list) -> list[str]:
    return [_text_of(c) for c in contents if c.role == "user" and _text_of(c)]


def _tool_names(contents: list) -> list[str]:
    names: list[str] = []
    for c in contents:
        for p in c.parts or []:
            if getattr(p, "function_call", None):
                names.append(p.function_call.name or "")
            if getattr(p, "function_response", None):
                names.append(p.function_response.name or "")
    return names


class _SpyAdkBrain(AdkBrain):
    """An ``AdkBrain`` on the live model that also records every corrected prompt.

    The spy is appended to the agent's ``before_model_callback`` chain, which ADK runs
    *after* the corrector plugin (plugins run before agent callbacks), so it observes
    the contents **post-correction** — the exact list the live model receives.
    ``captured`` is the real-model analogue of ``ScriptedLlm.captured_contents``."""

    def __init__(self) -> None:
        self.captured: list[list] = []
        super().__init__(
            lambda: LlmAgent(name="desk", model=MODEL, instruction=INSTRUCTION, tools=[book_trip]),
            greeting=GREETING,
            streaming=True,
            answer_conformance_dump=True,
        )

        def _spy(callback_context, llm_request) -> None:
            self.captured.append(list(llm_request.contents))

        # Runs after the corrector plugin (plugins precede agent callbacks) → sees the
        # corrected view. The agent has no callback yet, so start the chain as a list.
        self._agent.before_model_callback = [_spy]


async def _host(session_id: str) -> tuple[DirectAgent, VoiceDriver, _SpyAdkBrain]:
    keypair = generate_keypair()
    brain = _SpyAdkBrain()
    agent = DirectAgent(
        factory=brain_factory(lambda: brain),
        host="127.0.0.1",
        port=0,
        public_keys=keypair.public_pem,
    )
    port = await agent.start()
    token = mint_pygato_token(
        private_key_pem=keypair.private_pem,
        session_id=session_id,
        agent_id="desk",
        tenant_id="demo",
    )
    driver = VoiceDriver(
        DirectConnection(f"ws://127.0.0.1:{port}", session_id, token=token),
        session_id=session_id,
        default_timeout=45.0,  # a live model call is slower than the fake
    )
    await driver.open()
    return agent, driver, brain


# ─── 1. the SDK drives real ADK's loop: real tool round-trip, multi-inference ──


async def test_real_model_tool_round_trip() -> None:
    """A live model decides to call ``book_trip``, ADK runs it, and the model answers
    from the tool result — proving the SDK drives real ADK's run loop end-to-end (not
    just a scripted stand-in): the tool actually fires, and the follow-up prompt
    carries a well-formed real call+response pair the corrector left intact."""
    _DISPATCHED.clear()
    agent, driver, brain = await _host("adk-real-tools")
    try:
        g = await driver.start_session()
        assert g is not None and GREETING in g.text

        t = await driver.user_says("Book me a trip to Kyoto.")
        assert not t.interrupted
        assert _DISPATCHED == ["Kyoto"], f"the real tool never fired: {_DISPATCHED}"
        # The spoken confirmation came from the model reasoning over the tool result.
        assert t.text.strip(), "no spoken confirmation"

        # A tool round-trip is >1 model call (emit the call, then answer the result).
        assert len(t.inferences) >= 1
        # The last corrected prompt the model saw carries the real tool round-trip.
        names = _tool_names(brain.captured[-1])
        assert "book_trip" in names, names
    finally:
        await driver.aclose()
        await agent.aclose()


# ─── 2. mid-partial barge on a live stream: only the heard prefix is supplied ──


async def test_real_model_mid_partial_barge_supplies_heard_prefix() -> None:
    """Cut a *live streamed* reply mid-flight. ADK never persists partials, so the next
    real prompt must carry exactly the heard prefix (what actually streamed before the
    cut) as the sole model turn for that reply — never an un-heard generated tail."""
    agent, driver, brain = await _host("adk-real-mid-partial")
    try:
        assert await driver.start_session() is not None

        # Default heard = what really streamed before the cut → a genuine real prefix.
        t = await driver.barge_in("Tell me about Kyoto.", speak_delay=0.2)
        assert t.interrupted
        heard = t.heard or ""
        assert heard.strip(), f"nothing streamed before the cut: {heard!r}"

        await driver.user_says("What about Osaka?")
        prompt = brain.captured[-1]

        # The heard prefix was supplied as a model turn, in position between its user
        # turn and the follow-up: user(Kyoto), model(heard), user(Osaka).
        models = _model_texts(prompt)
        assert models == [heard], f"expected only the heard prefix, got {models!r}"
        roles = [c.role for c in prompt if _text_of(c)]
        assert roles == ["user", "model", "user"], roles
        assert "Osaka" in " ".join(_user_texts(prompt))
    finally:
        await driver.aclose()
        await agent.aclose()


# ─── 3. barge during playout of a COMPLETE live reply: the tail is dropped ─────


async def test_real_model_barge_during_playout_drops_persisted_tail() -> None:
    """The live reply fully generates and ADK **persists** it; the user barges during
    playout having heard only ``LEAD``. The corrector must drop the persisted full
    event and leave exactly the heard prefix — so the generated tail (a real,
    model-authored continuation past ``LEAD``) never survives into the next prompt."""
    agent, driver, brain = await _host("adk-real-playout")
    try:
        assert await driver.start_session() is not None

        # Wait for the whole reply to generate + persist, then barge its playout with a
        # heard prefix that is a genuine opening of the (longer) real generation.
        t = await driver.barge_in("Tell me about Kyoto.", wait_for_complete=True, heard_prefix=LEAD)
        assert t.interrupted and t.heard == LEAD

        await driver.user_says("What about Osaka?")
        prompt = brain.captured[-1]

        kyoto_turns = [m for m in _model_texts(prompt) if m.startswith(LEAD[:12])]
        # Exactly one model turn for that reply, and it is the heard prefix — not the
        # longer persisted generation. If the tail leaked, the text would be longer.
        assert kyoto_turns == [LEAD], f"tail not dropped / heard not supplied: {kyoto_turns!r}"
    finally:
        await driver.aclose()
        await agent.aclose()
