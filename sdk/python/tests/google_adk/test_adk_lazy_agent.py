"""The ADK agent is built lazily — so a subclass's own state is visible to its factory.

The natural way to write a voice agent is a brain that *owns* one session's state and
hands its tools to the agent::

    class TravelBrain(AdkBrain):
        def __init__(self) -> None:
            super().__init__(lambda: build_agent(self.desk))
            self.desk = TravelDesk()

Building the agent inside ``super().__init__`` would break exactly that: the factory
would run against a half-initialized ``self`` and raise ``AttributeError``, and the
developer would have to learn the ordering trap (assign first, call super last) — which
no other Brain seam imposes. The agent is therefore built on first need (session start,
or an explicit ``brain.agent``), never in the constructor.
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
from voqalize.google_adk import AdkBrain
from voqalize.google_adk.testing import ScriptedLlm, call, reply
from voqalize.sdk import DirectAgent, brain_factory

GREETING = "Front desk, how can I help?"
SESSION_ID = "adk-lazy-test"


class Desk:
    """One session's state, plus the tool bound to it."""

    def __init__(self) -> None:
        self.opened: list[str] = []

    async def open_file(self, name: str) -> dict:
        """Open a file by name.

        Args:
            name: The file's name.
        """
        self.opened.append(name)
        return {"status": "open", "name": name}


def test_the_factory_is_not_called_during_construction() -> None:
    """Constructing the brain touches nothing — no model, no runner, no agent."""
    calls: list[int] = []

    def factory() -> LlmAgent:
        calls.append(1)
        return LlmAgent(name="desk", model=ScriptedLlm({}), tools=[])

    brain = AdkBrain(factory)
    assert calls == []
    _ = brain.agent
    assert calls == [1]
    # …and built exactly once, however often it's needed.
    _ = brain.agent
    assert calls == [1]


def test_state_assigned_after_super_init_is_visible_to_the_factory() -> None:
    """The ordering trap is gone: state set *after* ``super().__init__`` is there when
    the factory runs."""

    class Brain(AdkBrain):
        def __init__(self, model: str | BaseLlm) -> None:
            super().__init__(lambda: LlmAgent(name="desk", model=model, tools=self.desk_tools()))
            self.desk = Desk()

        def desk_tools(self) -> list:
            return [self.desk.open_file]

    brain = Brain(ScriptedLlm({}))
    assert [t.__name__ for t in brain.agent.tools] == ["open_file"]


async def test_the_lazily_built_agent_drives_a_real_turn() -> None:
    """End to end: the tool the late-bound state owns runs, and mutates that state."""
    llm = ScriptedLlm(
        {
            "Open the Poddar file.": [
                call("open_file", name="Poddar Vietnam"),
                reply("Opened the Poddar file."),
            ]
        }
    )

    class Brain(AdkBrain):
        def __init__(self) -> None:
            super().__init__(
                lambda: LlmAgent(name="desk", model=llm, tools=[self.desk.open_file]),
                greeting=GREETING,
            )
            self.desk = Desk()

    brains: list[Brain] = []

    def make() -> Brain:
        brain = Brain()
        brains.append(brain)
        return brain

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
    try:
        g = await driver.start_session()
        assert g is not None and GREETING in g.text
        t = await driver.user_says("Open the Poddar file.")
        checks.check_completed(t)
        assert brains[0].desk.opened == ["Poddar Vietnam"]
    finally:
        await driver.aclose()
        await agent.aclose()
