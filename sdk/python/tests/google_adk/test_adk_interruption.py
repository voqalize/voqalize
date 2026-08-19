"""End-to-end barge-in scenarios for the ADK adapter — white-box-derived from a
walkthrough across pygato, the wire protocol, and this SDK, then modelled as tests.

These pin the *heard-truth* contract at every seam a barge-in can land, driven by
the conformance harness (the exact PyGato leg). The load-bearing facts they encode,
straight from the pygato/wire trace:

* ``heard_text`` is computed by PyGato from the audio playout clock — the words that
  physically played — and shipped to the brain in ``InferenceFinalized`` keyed by
  ``(interaction_id, inference_id)``, ``interrupted=True``. The brain commits that
  prefix; it never derives heard-truth itself. In the harness the driver *is* Voice
  and dictates the prefix, which is what makes these deterministic.
* Wire order to the brain on a barge is ``Interruption`` first (cancel the
  in-flight run), ``InferenceFinalized{interrupted}`` second (commit the prefix).
* An idle / no-audio barge emits **no** finalize at all (``heard is None``).
* PyGato **mutes the user during a tool round-trip** (``FunctionCallUserMuteStrategy``),
  so a barge cannot land between a ``function_call`` and its ``function_response`` —
  it lands on the *answer* inference, after the tool already ran and ADK already
  persisted a well-formed call+result pair.

The architectural contract under test (the maturity rewrite): the ADK session is the
source of truth. Past turns are corrected to heard-truth in a ``before_model_callback``
that reads ADK's own event log — never a parallel SDK-owned transcript that overwrites
``llm_request.contents`` wholesale. The proof that the source of truth really is ADK's
session lives in ``test_adk_session_source_of_truth.py`` (out-of-band events survive).
"""

from __future__ import annotations

import pytest

pytest.importorskip("google.adk")

from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm

from voqalize.conformance import (
    DirectConnection,
    VoiceDriver,
    checks,
    generate_keypair,
    mint_pygato_token,
)
from voqalize.google_adk import adk_brain
from voqalize.google_adk.testing import ScriptedLlm, call, reply
from voqalize.sdk import DirectAgent, brain_factory

GREETING = "Travel desk, how can I help?"
INSTRUCTION = "You are a travel desk. Use tools; never read raw ids aloud."
# The un-heard tail — must never reach the user's ears nor any later prompt.
SENTINEL = "NEVER_HEARD_AFTER_BARGE_IN"

_DISPATCHED: list[str] = []


async def book_trip(city: str) -> dict:
    """Book a trip to a city (records a confirmation the answer would quote).

    Args:
        city: The destination city.
    """
    _DISPATCHED.append(city)
    return {"pnr": f"TR-{city[:3].upper()}", "status": "confirmed"}


def build_agent(model: str | BaseLlm) -> LlmAgent:
    return LlmAgent(name="desk", model=model, instruction=INSTRUCTION, tools=[book_trip])


# ─── prompt introspection helpers ────────────────────────────────────────────
#
# Every assertion reads the genai ``Content`` list the model was handed on a later
# turn (``ScriptedLlm.captured_contents[-1]``) — i.e. exactly what the corrector
# produced. Heard-truth is proven by what is, and is not, in that prompt.


def _text_of(content) -> str:
    return "".join(p.text for p in (content.parts or []) if getattr(p, "text", None))


def _flatten(contents: list) -> str:
    """All text + function-call + function-response payloads of a rendered prompt,
    flattened to one searchable string."""
    out: list[str] = []
    for c in contents:
        for p in c.parts or []:
            if getattr(p, "text", None):
                out.append(p.text)
            fc = getattr(p, "function_call", None)
            if fc is not None:
                out.append(f"call:{fc.name}:{dict(fc.args or {})}")
            fr = getattr(p, "function_response", None)
            if fr is not None:
                out.append(f"resp:{fr.name}:{dict(fr.response or {})}")
    return " ".join(out)


def _model_texts(contents: list) -> list[str]:
    """The spoken text of every model turn, in order."""
    return [_text_of(c) for c in contents if c.role == "model" and _text_of(c)]


def _user_texts(contents: list) -> list[str]:
    return [_text_of(c) for c in contents if c.role == "user" and _text_of(c)]


def _tool_pairs(contents: list) -> tuple[list[str], list[str]]:
    """(function_call names, function_response names) across a rendered prompt."""
    calls: list[str] = []
    resps: list[str] = []
    for c in contents:
        for p in c.parts or []:
            if getattr(p, "function_call", None):
                calls.append(p.function_call.name or "")
            if getattr(p, "function_response", None):
                resps.append(p.function_response.name or "")
    return calls, resps


async def _host(llm: ScriptedLlm, *, session_id: str) -> tuple[DirectAgent, VoiceDriver]:
    keypair = generate_keypair()
    make = adk_brain(
        lambda: build_agent(llm),
        greeting=GREETING,
        streaming=True,
        answer_conformance_dump=True,
    )
    agent = DirectAgent(
        factory=brain_factory(make), host="127.0.0.1", port=0, public_keys=keypair.public_pem
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
        agent_id="desk",
        default_timeout=10.0,
    )
    await driver.open()
    return agent, driver


# ─── 1. barge before any audio played (zero-heard) ───────────────────────────


async def test_barge_in_before_any_audio_leaves_no_assistant_turn() -> None:
    """A reply cut *before a single word is heard* vanishes entirely: no finalize is
    sent (``heard is None``), nothing is committed to heard-truth, and — the
    load-bearing assertion — the next prompt carries no assistant turn for it at all,
    so the model never believes it said something the user never heard.

    ADK never persisted a model event either (the barge landed during the pre-chunk
    pause, before the aggregate), so the source-of-truth session simply has two
    adjacent user turns — exactly what a corrector reading ADK's own log yields."""
    llm = ScriptedLlm(
        {
            # One delayed chunk: the barge lands during the pre-chunk pause, so no
            # audio ever plays. The chunk IS the sentinel tail.
            "Tell me about Kyoto.": [reply(chunks=[SENTINEL], chunk_delay=0.5)],
            "What about Osaka?": [reply("Osaka is a lively food city.")],
        }
    )
    agent, driver = await _host(llm, session_id="adk-bargein-zero-heard")
    try:
        await driver.start_session()

        t = await driver.barge_in("Tell me about Kyoto.", wait_for_speech=False, speak_delay=0.1)
        assert t.interrupted
        # Nothing was heard → the driver (as Voice) finalized no inference.
        assert t.heard is None, t.heard
        checks.check_interruption_echoed(driver)

        # Heard-truth records the user utterance but NO assistant reply for it.
        state = await driver.dump_conversation()
        msgs = [{"role": m["role"], "content": m["content"]} for m in state["messages"]]
        assert {"role": "user", "content": "Tell me about Kyoto."} in msgs, msgs
        assert not [
            m
            for m in msgs
            if m["role"] == "assistant" and (SENTINEL in m["content"] or not m["content"])
        ], f"a barged-before-speech reply was committed: {msgs}"

        # Drive one more turn and inspect exactly what the model was asked.
        await driver.user_says("What about Osaka?")
        prompt = llm.captured_contents[-1]
        flat = _flatten(prompt)
        assert SENTINEL not in flat, f"generated tail leaked into the prompt: {flat!r}"

        # The two user turns are adjacent — no assistant turn wedged between them.
        assert "Tell me about Kyoto." in _user_texts(prompt)
        assert "What about Osaka?" in _user_texts(prompt)
        for c in prompt:
            if c.role == "model":
                assert SENTINEL not in _text_of(c)
    finally:
        await driver.aclose()
        await agent.aclose()


# ─── 2. barge mid-partial text (ADK persisted nothing) ───────────────────────


async def test_barge_in_mid_partial_supplies_heard_turn() -> None:
    """The commonest barge: cut mid-stream, after some words played. ADK persisted
    **no** model event (partials are never appended; the aggregate never arrived), so
    the heard turn must be *supplied* into the next prompt — attached to the right
    place (between its user turn and the follow-up), carrying only the heard prefix,
    never the un-heard tail."""
    llm = ScriptedLlm(
        {
            "Tell me about Kyoto.": [reply(chunks=["Kyoto is ", SENTINEL], chunk_delay=0.3)],
            "What about Osaka?": [reply("Osaka is a lively food city.")],
        }
    )
    agent, driver = await _host(llm, session_id="adk-bargein-mid-partial")
    try:
        await driver.start_session()

        t = await driver.barge_in(
            "Tell me about Kyoto.", speak_delay=0.12, heard_prefix="Kyoto is "
        )
        assert t.interrupted
        assert t.heard == "Kyoto is ", repr(t.heard)
        checks.check_interruption_echoed(driver)
        checks.check_no_speech_after_barge_in(driver, t, forbidden=SENTINEL)

        # Heard-truth committed: the heard prefix, never the tail.
        state = await driver.dump_conversation()
        checks.check_conversation_heard(
            state,
            expected_tail=[
                {"role": "user", "content": "Tell me about Kyoto."},
                {"role": "assistant", "content": "Kyoto is "},
            ],
        )

        await driver.user_says("What about Osaka?")
        prompt = llm.captured_contents[-1]
        flat = _flatten(prompt)
        assert SENTINEL not in flat, f"un-heard tail leaked into the prompt: {flat!r}"
        # The heard turn was supplied as a model turn between the two user turns.
        assert "Kyoto is " in _model_texts(prompt), _model_texts(prompt)
        roles = [c.role for c in prompt if _text_of(c)]
        # ... user(Kyoto), model(Kyoto is), user(Osaka) — heard turn in position.
        assert roles == ["user", "model", "user"], roles
    finally:
        await driver.aclose()
        await agent.aclose()


# ─── 3. barge during playout of an already-complete reply ────────────────────


async def test_barge_in_during_playout_corrects_persisted_full_reply() -> None:
    """The reply fully generated and ADK **persisted the whole model event**, but the
    user barged during playout and heard only a prefix. The next prompt must show the
    heard prefix and *exactly one* model turn for it — the corrector drops the
    superseded full event ADK kept, so the un-heard tail never survives, and the
    prompt is not doubled (full + prefix)."""
    llm = ScriptedLlm(
        {
            "Tell me about Kyoto.": [reply(f"Kyoto is old and {SENTINEL}")],
            "What about Osaka?": [reply("Osaka is a lively food city.")],
        }
    )
    agent, driver = await _host(llm, session_id="adk-bargein-playout")
    try:
        await driver.start_session()

        # Let the reply fully generate + close its bracket, then barge its playout.
        t = await driver.barge_in(
            "Tell me about Kyoto.", wait_for_complete=True, heard_prefix="Kyoto is old and "
        )
        assert t.interrupted
        assert t.heard == "Kyoto is old and ", repr(t.heard)
        checks.check_interruption_echoed(driver)

        await driver.user_says("What about Osaka?")
        prompt = llm.captured_contents[-1]
        flat = _flatten(prompt)
        # Un-heard tail gone; heard prefix present.
        assert SENTINEL not in flat, f"un-heard tail survived into the prompt: {flat!r}"
        assert "Kyoto is old and " in _model_texts(prompt), _model_texts(prompt)
        # Exactly one model turn for Kyoto — the full event was dropped, not left
        # alongside the heard correction.
        kyoto_turns = [t_ for t_ in _model_texts(prompt) if "Kyoto is old" in t_]
        assert kyoto_turns == ["Kyoto is old and "], kyoto_turns
    finally:
        await driver.aclose()
        await agent.aclose()


# ─── 4. barge mid tool round-trip (tool already ran) ─────────────────────────


async def test_barge_in_mid_tool_round_trip_keeps_the_tool_but_drops_the_tail() -> None:
    """The user cuts the *answer* of a tool round-trip after the tool ran. The tool
    call+result survive into the next prompt **carried by ADK's own session** (memory
    intact) while the answer's un-heard tail is dropped — tool-memory and barge-in
    interacting correctly."""
    _DISPATCHED.clear()
    llm = ScriptedLlm(
        {
            # inf 1: pure tool call (no speech) → the first audio is inf 2's opener,
            # so the barge lands cleanly inside the answer inference.
            "Book my Kyoto trip.": [
                call("book_trip", city="Kyoto"),
                reply(chunks=["You're all set, ", SENTINEL], chunk_delay=0.4),
            ],
            "What's my confirmation?": [reply("Your booking is confirmed under TR-KYO.")],
        }
    )
    agent, driver = await _host(llm, session_id="adk-bargein-mid-tool")
    try:
        await driver.start_session()

        t = await driver.barge_in(
            "Book my Kyoto trip.", speak_delay=0.15, heard_prefix="You're all set, "
        )
        assert t.interrupted
        assert _DISPATCHED == ["Kyoto"], _DISPATCHED  # the tool really ran before the cut
        assert t.heard == "You're all set, ", repr(t.heard)
        checks.check_interruption_echoed(driver)
        checks.check_no_speech_after_barge_in(driver, t, forbidden=SENTINEL)

        state = await driver.dump_conversation()
        checks.check_conversation_heard(
            state,
            expected_tail=[
                {"role": "user", "content": "Book my Kyoto trip."},
                {"role": "assistant", "content": "You're all set, "},
            ],
        )

        await driver.user_says("What's my confirmation?")
        prompt = llm.captured_contents[-1]
        flat = _flatten(prompt)

        # The tool round-trip survived the barge as a well-formed call+response pair.
        calls, resps = _tool_pairs(prompt)
        assert calls == ["book_trip"], calls
        assert resps == ["book_trip"], (
            f"tool call {calls} carried forward with no matching response {resps} — "
            "orphaned call, Gemini would 400"
        )
        assert "TR-KYO" in flat, f"tool result lost across the barge: {flat!r}"
        assert "You're all set," in flat, flat
        assert SENTINEL not in flat, f"un-heard tail leaked into the prompt: {flat!r}"
    finally:
        await driver.aclose()
        await agent.aclose()


# ─── 5. rapid double barge-in ────────────────────────────────────────────────


async def test_rapid_double_barge_cancels_cleanly() -> None:
    """Two ``InterruptionFrame``s land back-to-back before the brain can echo the
    first. The cancel path must survive it: the open bracket still closes (its
    ``LLMFullResponseEnd`` lands — the double-``CancelledError`` teardown bug does
    not swallow it), no un-heard tail is emitted, and the session is not hung — a
    later turn still works.

    (The wire-level double-echo barrier is PyGato's concern; here we pin that the
    brain does not deadlock or drop the bracket close under a rapid multi-barge.)"""
    llm = ScriptedLlm(
        {
            "Tell me about Kyoto.": [
                reply(chunks=["Kyoto is ", "very ", SENTINEL], chunk_delay=0.25)
            ],
            "What about Osaka?": [reply("Osaka is a lively food city.")],
        }
    )
    agent, driver = await _host(llm, session_id="adk-bargein-double")
    try:
        await driver.start_session()

        t = await driver.barge_in(
            "Tell me about Kyoto.", speak_delay=0.1, interrupts=2, heard_prefix="Kyoto is "
        )
        assert t.interrupted
        checks.check_interruption_echoed(driver)
        checks.check_no_speech_after_barge_in(driver, t, forbidden=SENTINEL)
        # Every opened bracket for the cut turn closed — the teardown landed its End.
        checks.check_brackets_closed(t)

        # The session is alive: a clean follow-up completes normally.
        t2 = await driver.user_says("What about Osaka?")
        checks.check_completed(t2)
        assert "Osaka" in t2.text, t2.text
    finally:
        await driver.aclose()
        await agent.aclose()


# ─── 7. identical reply text, only the second barged (identity correlation) ──


async def test_repeated_reply_text_drops_the_barged_turn_not_the_earlier_one() -> None:
    """Two turns generate the **exact same** reply text; only the *second* is barged.

    The corrector must drop the barged (second) reply and keep the earlier, fully-heard
    one — correlating by *identity* (session order + adjacency to the accountant heard
    turn), not by a global text match that would drop whichever identical text it hit
    first. A text-keyed corrector drops the wrong (un-barged) turn, leaving the two user
    turns adjacent with no reply between them; the identity-correct corrector keeps every
    user turn paired with its own reply.

    The tell is the *role sequence* of the next prompt — with the wrong turn dropped it
    collapses to ``user, user, model, …``; correct it stays strictly interleaved."""
    common = "Right away, booking that now."
    llm = ScriptedLlm(
        {
            "Book flight one.": [reply(common)],  # fully heard, never barged
            "Book flight two.": [reply(common)],  # identical text, barged on playout
            "Anything else?": [reply("All done.")],
        }
    )
    agent, driver = await _host(llm, session_id="adk-bargein-repeat-text")
    try:
        await driver.start_session()

        # Turn A completes cleanly — its identical reply is legitimately, fully heard.
        await driver.user_says("Book flight one.")
        # Turn B: same reply text, but barged during playout after a prefix.
        t = await driver.barge_in(
            "Book flight two.", wait_for_complete=True, heard_prefix="Right away, "
        )
        assert t.interrupted
        assert t.heard == "Right away, ", repr(t.heard)

        await driver.user_says("Anything else?")
        prompt = llm.captured_contents[-1]

        # The earlier, fully-heard reply survives exactly once; the barged copy is gone
        # and replaced by its heard prefix.
        full_copies = [m for m in _model_texts(prompt) if m == common]
        assert full_copies == [common], (
            f"expected the one fully-heard copy of {common!r} to survive, got "
            f"{_model_texts(prompt)}"
        )
        assert "Right away, " in _model_texts(prompt), _model_texts(prompt)

        # Every user turn keeps its own reply — no two user turns collapse adjacent
        # (which is what dropping the wrong identical turn would produce).
        roles = [c.role for c in prompt if _text_of(c)]
        assert roles == ["user", "model", "user", "model", "user"], roles
    finally:
        await driver.aclose()
        await agent.aclose()


# ─── 8. full reply heard, interrupted flag set (no duplicate turn) ────────────


async def test_full_reply_heard_but_interrupted_writes_no_duplicate() -> None:
    """A barge can land on a reply's *trailing silence* — the whole reply already
    played, yet the finalize still arrives ``interrupted=True`` with ``heard`` equal to
    the full generated text. Nothing was cut, so ADK's own persisted model event is
    already heard-truth; the adapter must **not** append an accountant event, or the
    reply would appear twice in the next prompt (the full event plus the identical
    accountant turn — the corrector drops neither, since heard == generated supersedes
    nothing)."""
    reply_text = "Kyoto is a former capital."
    llm = ScriptedLlm(
        {
            "Tell me about Kyoto.": [reply(reply_text)],
            "What about Osaka?": [reply("Osaka is a lively food city.")],
        }
    )
    agent, driver = await _host(llm, session_id="adk-bargein-full-heard")
    try:
        await driver.start_session()

        # Full reply played (wait_for_complete) and the driver reports the *entire* text
        # as heard, but still flags the finalize interrupted (barge on trailing silence).
        t = await driver.barge_in(
            "Tell me about Kyoto.", wait_for_complete=True, heard_prefix=reply_text
        )
        assert t.interrupted
        assert t.heard == reply_text, repr(t.heard)

        await driver.user_says("What about Osaka?")
        prompt = llm.captured_contents[-1]
        copies = [m for m in _model_texts(prompt) if m == reply_text]
        assert copies == [reply_text], (
            f"the fully-heard reply must appear exactly once, got {_model_texts(prompt)}"
        )
    finally:
        await driver.aclose()
        await agent.aclose()


# ─── 6. slow model, barge before the first token ─────────────────────────────


async def test_barge_before_first_token_of_slow_model() -> None:
    """The model was invoked but is slow — the user barges before a single token
    arrives. No audio played, so no finalize is sent (``heard is None``) and no
    assistant turn is committed; yet the model *was* invoked (its request was
    captured), so this is distinct from a barge before invocation. The follow-up
    prompt carries the two user turns and no phantom assistant turn."""
    llm = ScriptedLlm(
        {
            # A long pre-first-token pause; the barge lands inside it.
            "Tell me about Kyoto.": [reply(chunks=["Kyoto ", SENTINEL], chunk_delay=0.6)],
            "What about Osaka?": [reply("Osaka is a lively food city.")],
        }
    )
    agent, driver = await _host(llm, session_id="adk-bargein-slow")
    try:
        await driver.start_session()

        # The first model call was captured before the barge — the model was invoked.
        t = await driver.barge_in("Tell me about Kyoto.", wait_for_speech=False, speak_delay=0.15)
        assert t.interrupted
        assert t.heard is None, t.heard
        checks.check_interruption_echoed(driver)
        assert any("Tell me about Kyoto." in _flatten(c) for c in llm.captured_contents), (
            "the model was never invoked for the barged turn"
        )

        state = await driver.dump_conversation()
        msgs = [{"role": m["role"], "content": m["content"]} for m in state["messages"]]
        assert not [m for m in msgs if m["role"] == "assistant" and SENTINEL in m["content"]], msgs

        await driver.user_says("What about Osaka?")
        prompt = llm.captured_contents[-1]
        assert SENTINEL not in _flatten(prompt)
        assert "Tell me about Kyoto." in _user_texts(prompt)
        assert "What about Osaka?" in _user_texts(prompt)
    finally:
        await driver.aclose()
        await agent.aclose()
