"""Resume across WebSocket sessions for the ADK integration.

Same contract as the genai adapter, exercised through the ADK ``Runner`` path: the
``on_resume`` hook returns the prior-session messages and the SDK seeds them into
ADK's own session (``_seed_adk_session``) plus ``session.conversation``. Because ADK's
session is what the model prompts from, the seeded history is what the model actually
sees — this test proves that end to end via the scripted model's captured contents.
"""

from __future__ import annotations

import pytest

pytest.importorskip("google.adk")

from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm

from voqalize._framework.heard import text_of
from voqalize.conformance import (
    BrainServer,
    DirectConnection,
    VoqalizeDriver,
    checks,
    generate_keypair,
    mint_voqalize_token,
)
from voqalize.google_adk import AdkBrain
from voqalize.google_adk.testing import ScriptedLlm, reply
from voqalize.sdk import BrainServer, Message, brain_factory

GREETING = "Hi! Which trip are we working on?"
INSTRUCTION = "You are a travel desk."
CONV_KEY = "conv-abc-123"

PRIOR = [
    Message("user", "I want to fly to Tokyo."),
    Message("assistant", "Great — when are you travelling?"),
    Message("user", "Next month."),
    Message("assistant", "Got it: Tokyo, next month."),
]


def build_agent(model: str | BaseLlm) -> LlmAgent:
    return LlmAgent(name="assistant", model=model, instruction=INSTRUCTION)


async def _host(llm: ScriptedLlm, *, on_resume) -> tuple[BrainServer, VoqalizeDriver]:
    keypair = generate_keypair()
    resume_fn = on_resume

    class ResumingBrain(AdkBrain):
        def __init__(self) -> None:
            super().__init__(
                lambda: build_agent(llm), greeting=GREETING, answer_conformance_dump=True
            )

        async def on_resume(self, session, start):
            return await resume_fn(session, start)

    agent = BrainServer(ResumingBrain, public_keys=keypair.public_pem)
    port = await agent.start()
    session_id = "adk-resume-test"
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


def _all_text(captured: list) -> str:
    return "\n".join(text_of(c) for contents in captured for c in contents)


async def test_resume_seeds_prior_history_and_skips_greeting() -> None:
    async def on_resume(session, start):
        if start.init.get("conversation_id") == CONV_KEY:
            return PRIOR
        return []

    llm = ScriptedLlm({"And what about hotels?": [reply("Sure — how many nights?")]})
    agent, driver = await _host(llm, on_resume=on_resume)
    try:
        greeting = await driver.start_session(
            init={"conversation_id": CONV_KEY}, greeting_timeout=1.0
        )
        assert greeting is None  # resumed call: the cold greeting is skipped
        t = await driver.user_says("And what about hotels?")

        checks.check_completed(t)
        assert "how many nights" in t.text
        blob = _all_text(llm.captured_contents)
        assert "fly to Tokyo" in blob and "Tokyo, next month" in blob
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_no_resume_greets_normally() -> None:
    async def on_resume(session, start):
        return []

    llm = ScriptedLlm({"Hello?": [reply("How can I help?")]})
    agent, driver = await _host(llm, on_resume=on_resume)
    try:
        greeting = await driver.start_session()
        assert greeting is not None and GREETING in greeting.text
        t = await driver.user_says("Hello?")
        checks.check_completed(t)
        blob = _all_text(llm.captured_contents)
        assert "Tokyo" not in blob
    finally:
        await driver.aclose()
        await agent.aclose()
