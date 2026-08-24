"""Robust error handling for the ADK integration — the no-dead-air guarantee.

A real ADK ``Runner`` runs the loop. Asserted through the conformance
:class:`VoqalizeDriver` so it pins observable behaviour:

* **A model error speaks a fallback.** When the model raises, the turn still
  completes and the user hears a spoken apology instead of dead air.
* **A tool exception never hangs the turn.** However ADK surfaces a raising tool
  (propagated to the run, or fed back to the model as an error part), the turn MUST
  terminate and the user MUST hear *something* — never silence.
"""

from __future__ import annotations

import pytest

pytest.importorskip("google.adk")

from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm

from voqalize.conformance import (
    BrainServer,
    DirectConnection,
    VoqalizeDriver,
    checks,
    generate_keypair,
    mint_voqalize_token,
)
from voqalize.google_adk import adk_brain
from voqalize.google_adk.testing import ScriptedLlm, call, fail, finish, reply

GREETING = "Hi there!"
INSTRUCTION = "You are a helpful assistant."
FALLBACK = "SENTINEL_FALLBACK_LINE"

_tool_calls: list[str] = []


async def boom(reason: str) -> dict:
    """A tool that always fails.

    Args:
        reason: Why the caller wants it to run.
    """
    _tool_calls.append(reason)
    raise RuntimeError("tool exploded")


def build_agent(model: str | BaseLlm, *, tools: list | None = None) -> LlmAgent:
    return LlmAgent(name="assistant", model=model, instruction=INSTRUCTION, tools=tools or [])


async def _host(
    llm: ScriptedLlm, *, tools: list | None = None
) -> tuple[BrainServer, VoqalizeDriver]:
    keypair = generate_keypair()
    make = adk_brain(
        lambda: build_agent(llm, tools=tools),
        greeting=GREETING,
        error_fallback=FALLBACK,
        answer_conformance_dump=True,
    )
    agent = BrainServer(make, public_keys=keypair.public_pem)
    port = await agent.start()
    session_id = "adk-errors-test"
    token = mint_voqalize_token(
        private_key_pem=keypair.private_pem,
        session_id=session_id,
        agent_id="assistant",
        tenant_id="demo",
    )
    driver = VoqalizeDriver(
        DirectConnection(f"ws://127.0.0.1:{port}", session_id, token=token),
        session_id=session_id,
        default_timeout=10.0,
    )
    await driver.open()
    return agent, driver


async def test_model_error_speaks_fallback_and_completes() -> None:
    """A model call that raises does not hang the turn or leave dead air: the turn
    completes and the user hears the configured fallback line."""
    llm = ScriptedLlm({"Trigger an error.": [fail("boom from the model")]})
    agent, driver = await _host(llm)
    try:
        await driver.start_session()
        t = await driver.user_says("Trigger an error.")

        checks.check_completed(t)
        assert FALLBACK in t.text, (
            f"model error left the turn silent — no spoken fallback:\n{t.text!r}"
        )
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_silent_reply_speaks_fallback_and_completes() -> None:
    """A model that returns *cleanly but empty* (a safety-blocked or truncated reply —
    no text, no calls, no error) must not leave dead air: the turn completes and the
    spoke-nothing guard speaks the fallback, even though nothing raised."""
    llm = ScriptedLlm({"Say nothing at all.": [finish(reason="SAFETY")]})
    agent, driver = await _host(llm)
    try:
        await driver.start_session()
        t = await driver.user_says("Say nothing at all.")

        checks.check_completed(t)
        assert FALLBACK in t.text, (
            f"a silent (empty/safety-blocked) reply left the turn with no speech:\n{t.text!r}"
        )
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_tool_exception_never_leaves_dead_air() -> None:
    """A tool that raises never hangs the turn or leaves silence: the turn completes
    and the user hears either the model's own recovery or the turn-level fallback."""
    _tool_calls.clear()
    llm = ScriptedLlm(
        {
            "Please do the risky thing.": [
                call("boom", reason="user asked"),
                reply("Sorry, that didn't work — let me try another way."),
            ],
        }
    )
    agent, driver = await _host(llm, tools=[boom])
    try:
        await driver.start_session()
        t = await driver.user_says("Please do the risky thing.")

        checks.check_completed(t)
        assert _tool_calls == ["user asked"], _tool_calls  # the tool really ran and raised
        assert t.text.strip(), f"tool error left the turn silent — dead air:\n{t.text!r}"
    finally:
        await driver.aclose()
        await agent.aclose()
