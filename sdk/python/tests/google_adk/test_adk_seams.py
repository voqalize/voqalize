"""Overriding a Brain seam on a framework adapter works — wrapping a native ADK
agent doesn't shadow it.

``AdkBrain`` drives ADK's runner and owns two Brain seams internally:
``on_client_message`` (answers the conformance backchannel when
``answer_conformance_dump=True``) and ``on_error`` (a warning log). A customer still
wants those seams — browser client messages (``on_client_message``) and a teardown
hook (``on_session_end``) — so they **override the ordinary method** on their
``AdkBrain`` subclass. These prove the override is honoured, and that the
adapter-internal conformance answer coexists with a customer override (calling
``super().on_client_message`` keeps it).
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
    generate_keypair,
    mint_voqalize_token,
)
from voqalize.conformance.driver import CONFORMANCE_DUMP_EVENT
from voqalize.google_adk import AdkBrain
from voqalize.google_adk.testing import ScriptedLlm, reply
from voqalize.sdk import DirectAgent, brain_factory

GREETING = "Front desk, how can I help?"
INSTRUCTION = "You are a front desk agent."
SESSION_ID = "adk-seams-test"


def build_agent(model: str | BaseLlm) -> LlmAgent:
    return LlmAgent(name="desk", model=model, instruction=INSTRUCTION, tools=[])


async def _driver(make, keypair) -> tuple[VoqalizeDriver, DirectAgent]:
    agent = DirectAgent(
        factory=brain_factory(make), host="127.0.0.1", port=0, public_keys=keypair.public_pem
    )
    port = await agent.start()
    token = mint_voqalize_token(
        private_key_pem=keypair.private_pem,
        session_id=SESSION_ID,
        agent_id="desk",
        tenant_id="demo",
    )
    driver = VoqalizeDriver(
        DirectConnection(f"ws://127.0.0.1:{port}", SESSION_ID, token=token),
        session_id=SESSION_ID,
        default_timeout=10.0,
    )
    return driver, agent


async def test_on_client_message_override_receives_ui_messages() -> None:
    """A customer's ``on_client_message`` override receives a real browser client
    message — wrapping ADK's runner doesn't swallow the seam."""
    seen: list[tuple[str, dict]] = []
    llm = ScriptedLlm({"__unused__": [reply("ok")]})

    class Recording(AdkBrain):
        def __init__(self) -> None:
            super().__init__(lambda: build_agent(llm), greeting=GREETING)

        async def on_client_message(self, session, message) -> None:
            seen.append((message.type, message.data))

    keypair = generate_keypair()
    driver, agent = await _driver(Recording, keypair)
    await driver.open()
    try:
        await driver.start_session()
        await driver.send_client_message("cart_updated", {"items": 3})
        await _eventually(lambda: len(seen) >= 1)
        assert seen == [("cart_updated", {"items": 3})]
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_conformance_answer_coexists_with_override() -> None:
    """With ``answer_conformance_dump=True`` AND an ``on_client_message`` override that
    calls ``super()``, the conformance dump is answered internally while a real client
    message still reaches the override — the internal seam never shadows the customer's."""
    seen: list[str] = []
    llm = ScriptedLlm({"__unused__": [reply("ok")]})

    class Recording(AdkBrain):
        def __init__(self) -> None:
            super().__init__(
                lambda: build_agent(llm), greeting=GREETING, answer_conformance_dump=True
            )

        async def on_client_message(self, session, message) -> None:
            # super() answers the conformance dump; a real message falls through to us.
            await super().on_client_message(session, message)
            if message.type != CONFORMANCE_DUMP_EVENT:
                seen.append(message.type)

    keypair = generate_keypair()
    driver, agent = await _driver(Recording, keypair)
    await driver.open()
    try:
        await driver.start_session()
        # The conformance dump is answered internally (super()) and not recorded.
        dump = await driver.dump_conversation()
        assert dump is not None
        await driver.send_client_message("cart_updated", {"items": 1})
        await _eventually(lambda: seen == ["cart_updated"])
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_on_session_end_override_fires() -> None:
    """A customer's ``on_session_end`` teardown override fires when the session ends."""
    ended = asyncio.Event()
    llm = ScriptedLlm({"__unused__": [reply("ok")]})

    class Recording(AdkBrain):
        def __init__(self) -> None:
            super().__init__(lambda: build_agent(llm), greeting=GREETING)

        async def on_session_end(self, session) -> None:
            ended.set()

    keypair = generate_keypair()
    driver, agent = await _driver(Recording, keypair)
    await driver.open()
    try:
        await driver.start_session()
    finally:
        await driver.aclose()
        await agent.aclose()
    await asyncio.wait_for(ended.wait(), timeout=5.0)


async def _eventually(predicate, *, timeout: float = 5.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition not met within timeout")
