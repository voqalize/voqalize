"""Multiple tool calls in a SINGLE model response for the ADK adapter.

Here the ADK ``Runner`` owns dispatch, not the SDK, so *ordering* across the two
calls is the framework's concern (it may run them concurrently) — what the SDK must
still get right is that **both** round-trips survive the correction into the next
prompt as well-formed ``function_call`` / ``function_response`` pairs. A regression
in how the corrector preserves paired tool parts (dropping the second exchange, or
losing a call's response) fails here.
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
from voqalize.google_adk.testing import Reply, ScriptedLlm, reply
from voqalize.sdk import DirectAgent, brain_factory

GREETING = "Travel desk, how can I help?"
INSTRUCTION = "You are a travel desk. Use tools; never read raw ids aloud."

DISPATCHED: list[str] = []


async def book_flight(city: str) -> dict:
    """Book a flight to a city.

    Args:
        city: The destination city.
    """
    DISPATCHED.append("book_flight")
    return {"pnr": f"FL-{city[:3].upper()}"}


async def book_hotel(city: str) -> dict:
    """Book a hotel in a city.

    Args:
        city: The city to book a hotel in.
    """
    DISPATCHED.append("book_hotel")
    return {"conf": f"HT-{city[:3].upper()}"}


def build_agent(model: str | BaseLlm) -> LlmAgent:
    return LlmAgent(
        name="desk", model=model, instruction=INSTRUCTION, tools=[book_flight, book_hotel]
    )


def _script() -> dict:
    return {
        "Book my Tokyo flight and hotel.": [
            Reply(calls=(("book_flight", {"city": "Tokyo"}), ("book_hotel", {"city": "Tokyo"}))),
            reply("All set — your flight and hotel are booked."),
        ],
    }


async def _host(llm: ScriptedLlm) -> tuple[DirectAgent, VoiceDriver]:
    keypair = generate_keypair()
    make = adk_brain(
        lambda: build_agent(llm),
        greeting=GREETING,
        streaming=True,
        answer_conformance_dump=True,
    )
    agent = DirectAgent(
        factory=brain_factory(make),
        host="127.0.0.1",
        port=0,
        public_keys=keypair.public_pem,
    )
    port = await agent.start()
    session_id = "adk-multitool-test"
    token = mint_pygato_token(
        private_key_pem=keypair.private_pem,
        session_id=session_id,
        agent_id="travel",
        tenant_id="demo",
    )
    driver = VoiceDriver(
        DirectConnection(f"ws://127.0.0.1:{port}", session_id, token=token),
        session_id=session_id,
        agent_id="travel",
        default_timeout=10.0,
    )
    await driver.open()
    return agent, driver


async def test_all_calls_in_one_response_are_dispatched() -> None:
    """Both tool calls in a single model response run (order is the Runner's to
    choose) and the turn completes with the follow-up answer."""
    DISPATCHED.clear()
    llm = ScriptedLlm(_script())
    agent, driver = await _host(llm)
    try:
        await driver.start_session()
        t = await driver.user_says("Book my Tokyo flight and hotel.")

        checks.check_completed(t)
        assert "booked" in t.text
        assert sorted(DISPATCHED) == ["book_flight", "book_hotel"], DISPATCHED
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_both_round_trips_carried_forward_paired() -> None:
    """Both round-trips survive the correction into the follow-up prompt as matched
    call/response pairs — neither dropped, neither orphaned."""
    DISPATCHED.clear()
    llm = ScriptedLlm(_script())
    agent, driver = await _host(llm)
    try:
        await driver.start_session()
        await driver.user_says("Book my Tokyo flight and hotel.")

        follow_up = llm.captured_contents[-1]
        call_names: list[str] = []
        resp_names: list[str] = []
        for c in follow_up:
            for p in c.parts or []:
                fc = getattr(p, "function_call", None)
                if fc is not None:
                    call_names.append(fc.name or "")
                fr = getattr(p, "function_response", None)
                if fr is not None:
                    resp_names.append(fr.name or "")
        assert sorted(call_names) == ["book_flight", "book_hotel"], call_names
        assert sorted(resp_names) == ["book_flight", "book_hotel"], (
            f"carried calls {call_names} not fully matched by responses {resp_names}"
        )
    finally:
        await driver.aclose()
        await agent.aclose()
