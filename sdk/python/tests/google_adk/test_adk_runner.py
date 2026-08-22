"""Bring-your-own ``Runner`` — the escape hatch from the hard-wired ``InMemoryRunner``.

A developer who already runs ADK with their **own** services (a
``DatabaseSessionService`` / ``VertexAiSessionService`` for durable state, a
``MemoryService``, an ``ArtifactService``) must be able to keep them when they add
voice — not have them silently swapped for the in-memory defaults. ``adk_brain``
takes an optional ``runner_factory(agent) -> Runner``; this proves the SDK drives
*that* runner (its session_service sees the session, its ``app_name`` is honored)
while the heard-truth corrector still holds (the driven turn is spoken).
"""

from __future__ import annotations

import pytest

pytest.importorskip("google.adk")

from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from voqalize.conformance import (
    DirectConnection,
    VoiceDriver,
    checks,
    generate_keypair,
    mint_pygato_token,
)
from voqalize.google_adk import adk_brain
from voqalize.google_adk.testing import ScriptedLlm, reply
from voqalize.sdk import DirectAgent, brain_factory

GREETING = "Front desk, how can I help?"
INSTRUCTION = "You are a front desk agent."
APP_NAME = "my-own-app"
SESSION_ID = "adk-runner-test"


def build_agent(model: str | BaseLlm) -> LlmAgent:
    return LlmAgent(name="desk", model=model, instruction=INSTRUCTION, tools=[])


async def test_custom_runner_factory_is_driven_and_keeps_its_session_service() -> None:
    """The SDK drives the client-supplied ``Runner``: its own ``session_service`` holds
    the session (so durable state/artifacts survive) and its ``app_name`` is used —
    while the driven turn is still spoken (corrector intact)."""
    # The client's own service instance — the thing that would be a DatabaseSessionService
    # in production. We hold the reference to prove the SDK used *this* one.
    my_service = InMemorySessionService()

    def runner_factory(agent: LlmAgent) -> Runner:
        return Runner(app_name=APP_NAME, agent=agent, session_service=my_service)

    llm = ScriptedLlm({"Book me a table.": [reply("Done — your table is booked.")]})
    keypair = generate_keypair()
    make = adk_brain(
        lambda: build_agent(llm),
        greeting=GREETING,
        streaming=True,
        runner_factory=runner_factory,
        answer_conformance_dump=True,
    )
    agent = DirectAgent(
        factory=brain_factory(make), host="127.0.0.1", port=0, public_keys=keypair.public_pem
    )
    port = await agent.start()
    token = mint_pygato_token(
        private_key_pem=keypair.private_pem,
        session_id=SESSION_ID,
        agent_id="desk",
        tenant_id="demo",
    )
    driver = VoiceDriver(
        DirectConnection(f"ws://127.0.0.1:{port}", SESSION_ID, token=token),
        session_id=SESSION_ID,
        default_timeout=10.0,
    )
    await driver.open()
    try:
        g = await driver.start_session()
        assert g is not None and GREETING in g.text

        # The SDK created the ADK session on OUR service, under OUR app_name.
        found = await my_service.get_session(
            app_name=APP_NAME, user_id=SESSION_ID, session_id=SESSION_ID
        )
        assert found is not None, "the SDK must drive the client's own runner/session_service"

        # And the custom runner actually drives the turn — corrector intact.
        t = await driver.user_says("Book me a table.")
        checks.check_completed(t)
        assert "booked" in t.text
    finally:
        await driver.aclose()
        await agent.aclose()
