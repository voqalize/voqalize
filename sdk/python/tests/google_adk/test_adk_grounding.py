"""``grounding()`` + the ``state_sync`` browser-snapshot convention.

A screen-driving agent must never answer "what's on screen?" from a stale turn. Two
SDK seams make that structural, and this file pins both — plus the one that matters
most, their composition:

* ``AdkBrain.grounding() -> str | None`` is appended to the system instruction on
  **every model call**, *after* whatever ADK assembled — so it composes with a plain
  string instruction (ADK's ``{state}`` templating still applies to it) and with the
  client's own ``InstructionProvider`` alike, and never clobbers either. Returning
  ``None`` appends nothing at all, turn by turn.
* ``state_sync`` client messages are ingested by default onto ``self.browser_state``,
  replacing the previous snapshot and **taking no floor** — a screen change must not
  make the agent talk.

The combined test is the real contract: a snapshot the browser pushed between turns is
in the *next* prompt's system instruction, with no tool call and no round-trip.
"""

from __future__ import annotations

import asyncio
import json

import pytest

pytest.importorskip("google.adk")

from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.models.base_llm import BaseLlm

from voqalize.conformance import (
    DirectConnection,
    VoqalizeDriver,
    checks,
    generate_keypair,
    mint_voqalize_token,
)
from voqalize.google_adk import AdkBrain
from voqalize.google_adk.testing import ScriptedLlm, reply
from voqalize.sdk import DirectAgent, brain_factory

GREETING = "Travel desk, how can I help?"
INSTRUCTION = "You are a travel desk. Speak in short sentences."
SESSION_ID = "adk-grounding-test"


def build_agent(model: str | BaseLlm, *, instruction=INSTRUCTION) -> LlmAgent:
    return LlmAgent(name="desk", model=model, instruction=instruction, tools=[])


async def _host(make) -> tuple[DirectAgent, VoqalizeDriver]:
    keypair = generate_keypair()
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
    await driver.open()
    return agent, driver


async def test_grounding_is_appended_to_a_static_instruction() -> None:
    """A ``grounding()`` override lands in the system instruction of the model call —
    *after* the client's plain-string instruction, which survives intact."""
    llm = ScriptedLlm({"What's up?": [reply("Nothing yet.")]})

    class Grounded(AdkBrain):
        def __init__(self) -> None:
            super().__init__(lambda: build_agent(llm), greeting=GREETING)

        def grounding(self) -> str | None:
            return "ON SCREEN: the dashboard."

    agent, driver = await _host(Grounded)
    try:
        await driver.start_session()
        await driver.user_says("What's up?")
        system = llm.captured_system_instructions[-1]
        assert INSTRUCTION in system, system
        assert "ON SCREEN: the dashboard." in system, system
        assert system.index(INSTRUCTION) < system.index("ON SCREEN"), system
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_grounding_composes_with_a_client_instruction_provider() -> None:
    """A client who already passes their own ADK ``InstructionProvider`` keeps it — the
    SDK composes with the provider's output, it does not replace the callable."""
    llm = ScriptedLlm({"What's up?": [reply("Nothing yet.")]})

    def provider(_ctx: ReadonlyContext) -> str:
        return "PROVIDER-INSTRUCTION for desk"

    class Grounded(AdkBrain):
        def __init__(self) -> None:
            super().__init__(lambda: build_agent(llm, instruction=provider), greeting=GREETING)

        def grounding(self) -> str | None:
            return "ON SCREEN: the dashboard."

    agent, driver = await _host(Grounded)
    try:
        await driver.start_session()
        await driver.user_says("What's up?")
        system = llm.captured_system_instructions[-1]
        assert "PROVIDER-INSTRUCTION for desk" in system, system
        assert "ON SCREEN: the dashboard." in system, system
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_grounding_none_omits_the_block_entirely() -> None:
    """Conditional grounding: a turn where ``grounding()`` returns ``None`` appends
    nothing — no header, no empty block — while a later turn that returns text does.
    (The legal demo grounds only once a document is open.)"""
    llm = ScriptedLlm(
        {
            "Anything open?": [reply("Nothing open.")],
            "Now?": [reply("The Poddar file.")],
        }
    )

    class Grounded(AdkBrain):
        def __init__(self) -> None:
            super().__init__(lambda: build_agent(llm), greeting=GREETING)
            self.open_file: str | None = None

        def grounding(self) -> str | None:
            if self.open_file is None:
                return None
            return f"OPEN FILE: {self.open_file}"

    brains: list[Grounded] = []

    def make() -> Grounded:
        brain = Grounded()
        brains.append(brain)
        return brain

    agent, driver = await _host(make)
    try:
        await driver.start_session()
        await driver.user_says("Anything open?")
        # Nothing appended: the ungrounded prompt is exactly what ADK assembled.
        ungrounded = llm.captured_system_instructions[-1]
        assert "OPEN FILE" not in ungrounded, ungrounded

        brains[0].open_file = "Poddar Vietnam"
        await driver.user_says("Now?")
        grounded = llm.captured_system_instructions[-1]
        # …and the grounded prompt is that same text plus the block, appended.
        assert grounded == f"{ungrounded}\n\nOPEN FILE: Poddar Vietnam", grounded
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_state_sync_snapshot_lands_in_the_next_prompt() -> None:
    """The whole convention end-to-end: the browser pushes ``state_sync`` between
    turns, the SDK keeps it on ``browser_state`` **without taking the floor** (no model
    call, nothing spoken), and the next prompt's system instruction carries it."""
    llm = ScriptedLlm({"Which flights are up?": [reply("The Bangalore leg.")]})
    snapshot = {"itinerary": {"name": "Poddar Vietnam", "legs": [{"id": "blr-out"}]}}

    class Screen(AdkBrain):
        def __init__(self) -> None:
            super().__init__(lambda: build_agent(llm), greeting=GREETING)

        def grounding(self) -> str | None:
            if not self.browser_state:
                return None
            return "ON SCREEN NOW: " + json.dumps(self.browser_state, sort_keys=True)

    brains: list[Screen] = []

    def make() -> Screen:
        brain = Screen()
        brains.append(brain)
        return brain

    agent, driver = await _host(make)
    try:
        await driver.start_session()
        await driver.send_client_message("state_sync", snapshot)
        await _eventually(lambda: brains[0].browser_state == snapshot)

        # No floor was taken: the snapshot drove no model call and no speech.
        assert llm.captured_contents == []

        t = await driver.user_says("Which flights are up?")
        checks.check_completed(t)
        system = llm.captured_system_instructions[-1]
        assert "ON SCREEN NOW:" in system, system
        assert "Poddar Vietnam" in system and "blr-out" in system, system
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_state_sync_replaces_rather_than_merges() -> None:
    """Each snapshot is complete: the second replaces the first, so a row the user
    deleted in the browser cannot be resurrected by a merge."""
    llm = ScriptedLlm({"__unused__": [reply("ok")]})

    brains: list[AdkBrain] = []

    def make() -> AdkBrain:
        brain = AdkBrain(lambda: build_agent(llm), greeting=GREETING)
        brains.append(brain)
        return brain

    agent, driver = await _host(make)
    try:
        await driver.start_session()
        await driver.send_client_message("state_sync", {"legs": ["a", "b"], "stale": 1})
        await _eventually(lambda: brains[0].browser_state is not None)
        await driver.send_client_message("state_sync", {"legs": ["a"]})
        await _eventually(lambda: brains[0].browser_state == {"legs": ["a"]})
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_state_sync_survives_a_client_override_calling_super() -> None:
    """A subclass with its own ``on_client_message`` keeps the default snapshot
    handling by calling ``super()`` — and still sees the message itself."""
    llm = ScriptedLlm({"__unused__": [reply("ok")]})
    seen: list[str] = []

    class Screen(AdkBrain):
        def __init__(self) -> None:
            super().__init__(lambda: build_agent(llm), greeting=GREETING)

        async def on_client_message(self, session, message) -> None:
            seen.append(message.type)
            await super().on_client_message(session, message)

    brains: list[Screen] = []

    def make() -> Screen:
        brain = Screen()
        brains.append(brain)
        return brain

    agent, driver = await _host(make)
    try:
        await driver.start_session()
        await driver.send_client_message("state_sync", {"cart": 3})
        await _eventually(lambda: brains[0].browser_state == {"cart": 3})
        assert seen == ["state_sync"]
    finally:
        await driver.aclose()
        await agent.aclose()


async def _eventually(predicate, *, timeout: float = 5.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition not met within timeout")
