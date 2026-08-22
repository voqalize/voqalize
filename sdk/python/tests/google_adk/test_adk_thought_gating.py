"""Output gating for the ADK integration — the model's private reasoning (a
``thought=True`` part, emitted when ADK runs with thinking on) must never be spoken.

Runs against a real ADK ``Runner``. Asserted through the conformance
:class:`VoqalizeDriver`: the user hears only the answer, and heard-truth records only
the answer.
"""

from __future__ import annotations

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
from voqalize.google_adk.testing import ScriptedLlm, reply
from voqalize.sdk import DirectAgent, brain_factory

GREETING = "Hi there!"
INSTRUCTION = "You are a helpful assistant."
THOUGHT = "PRIVATE_REASONING_6x7_IS_42"
ANSWER = "It's forty-two."


async def _host(llm: BaseLlm) -> tuple[DirectAgent, VoqalizeDriver]:
    keypair = generate_keypair()
    make = adk_brain(
        lambda: LlmAgent(name="assistant", model=llm, instruction=INSTRUCTION),
        greeting=GREETING,
        answer_conformance_dump=True,
    )
    agent = DirectAgent(
        factory=brain_factory(make),
        host="127.0.0.1",
        port=0,
        public_keys=keypair.public_pem,
    )
    port = await agent.start()
    session_id = "adk-thought-test"
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


async def test_thinking_part_is_never_spoken_or_committed() -> None:
    """A reply carrying a thinking part speaks only the answer; the thought reaches
    neither the user's ears nor the committed conversation."""
    llm = ScriptedLlm({"What is six times seven?": [reply(ANSWER, thought=THOUGHT)]})
    agent, driver = await _host(llm)
    try:
        await driver.start_session()
        t = await driver.user_says("What is six times seven?")

        checks.check_completed(t)
        checks.check_spoke(t)
        assert ANSWER in t.text, t.text
        assert THOUGHT not in t.text, f"model's private reasoning was spoken:\n{t.text!r}"

        state = await driver.dump_conversation()
        checks.check_conversation_sequence(
            state,
            expected=[
                {"role": "assistant", "content": GREETING},
                {"role": "user", "content": "What is six times seven?"},
                {"role": "assistant", "content": ANSWER},
            ],
        )
    finally:
        await driver.aclose()
        await agent.aclose()
