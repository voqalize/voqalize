"""Turn-watchdog hardening for the ADK integration.

The ADK ``Runner`` owns tool execution, so there is no per-tool timeout here — the
shared ``turn_timeout`` watchdog is the backstop. A tool that hangs forever blocks
the runner's event stream; the watchdog cancels the whole run (tearing down the ADK
generator) and speaks the fallback, so the turn completes instead of stranding the
caller in silence. Asserted through the conformance :class:`VoqalizeDriver`.
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("google.adk")

from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm

from voqalize.conformance import (
    DirectConnection,
    VoqalizeDriver,
    checks,
    generate_keypair,
    mint_voqalize_token,
)
from voqalize.google_adk import adk_brain
from voqalize.google_adk.testing import ScriptedLlm, call
from voqalize.sdk import DirectAgent, brain_factory

GREETING = "Hi there!"
INSTRUCTION = "You are a helpful assistant."
FALLBACK = "SENTINEL_FALLBACK_LINE"

_tool_started: list[str] = []


async def slow_tool(reason: str) -> dict:
    """A tool that hangs well past any test timeout.

    Args:
        reason: Why the caller wants it to run.
    """
    _tool_started.append(reason)
    await asyncio.sleep(30)
    return {"never": "reached"}


def build_agent(model: str | BaseLlm) -> LlmAgent:
    return LlmAgent(name="assistant", model=model, instruction=INSTRUCTION, tools=[slow_tool])


async def _host(
    llm: ScriptedLlm, *, turn_timeout: float | None
) -> tuple[DirectAgent, VoqalizeDriver]:
    keypair = generate_keypair()
    make = adk_brain(
        lambda: build_agent(llm),
        greeting=GREETING,
        error_fallback=FALLBACK,
        turn_timeout=turn_timeout,
        answer_conformance_dump=True,
    )
    agent = DirectAgent(
        factory=brain_factory(make),
        host="127.0.0.1",
        port=0,
        public_keys=keypair.public_pem,
    )
    port = await agent.start()
    session_id = "adk-timeouts-test"
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


async def test_hung_tool_hits_turn_watchdog_and_speaks_fallback() -> None:
    """A tool that hangs forever is caught by the turn watchdog: the ADK run is torn
    down and the fallback spoken, so the turn completes instead of hanging."""
    _tool_started.clear()
    llm = ScriptedLlm({"Hang forever please.": [call("slow_tool", reason="hang")]})
    agent, driver = await _host(llm, turn_timeout=0.3)
    try:
        await driver.start_session()
        # The watchdog speaks after the torn-down run's empty bracket closes, so the
        # driver's quiet window has to outlast the 0.3s turn_timeout.
        t = await driver.user_says("Hang forever please.", quiet_for=1.0)

        checks.check_completed(t)
        assert _tool_started == ["hang"], _tool_started  # the tool really started
        assert FALLBACK in t.text, (
            f"a hung tool left the turn with no speech — watchdog didn't fire:\n{t.text!r}"
        )
    finally:
        await driver.aclose()
        await agent.aclose()
