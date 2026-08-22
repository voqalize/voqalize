"""Cross-turn tool memory for the ADK adapter.

If turn 1 looks up a booking reference the
model deliberately does *not* read aloud, turn 2 ("what's my reference?") can only
answer from the tool *result* carried forward. The ADK adapter prompts from ADK's
own ``SessionService``; the heard-truth corrector reconciles spoken text but must
leave an earlier turn's tool round-trip intact into a later prompt — not just the
heard spoken text.

Both probes assert on ``ScriptedLlm.captured_contents`` — the exact contents ADK's
model was handed — so they are decisive regardless of what the model would have
said.
"""

from __future__ import annotations

import pytest

pytest.importorskip("google.adk")

from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm

from voqalize.conformance import (
    DirectConnection,
    VoiceDriver,
    generate_keypair,
    mint_voice_token,
)
from voqalize.google_adk import adk_brain
from voqalize.google_adk.testing import ScriptedLlm, call, reply
from voqalize.sdk import DirectAgent, brain_factory

SECRET_REF = "XZ9-BOOKING-SECRET"

GREETING = "Travel desk, how can I help?"
INSTRUCTION = "You are a travel desk. Use tools; never read raw ids aloud."


async def get_booking(passenger: str) -> dict:
    """Look up the caller's booking. Returns a reference the agent must NOT speak.

    Args:
        passenger: The caller's surname.
    """
    return {"ref": SECRET_REF, "status": "confirmed"}


def build_agent(model: str | BaseLlm) -> LlmAgent:
    return LlmAgent(name="desk", model=model, instruction=INSTRUCTION, tools=[get_booking])


def _script() -> dict:
    return {
        # Turn 1: call the tool, then acknowledge WITHOUT reading the ref aloud.
        "Look up the Poddar booking.": [
            call("get_booking", passenger="Poddar"),
            reply("Found your booking — it's confirmed."),
        ],
        # Turn 2: the model answers from the carried-forward tool result.
        "What's my booking reference?": [
            reply(f"Your reference is {SECRET_REF}."),
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
    session_id = "adk-memory-test"
    token = mint_voice_token(
        private_key_pem=keypair.private_pem,
        session_id=session_id,
        agent_id="travel",
        tenant_id="demo",
    )
    driver = VoiceDriver(
        DirectConnection(f"ws://127.0.0.1:{port}", session_id, token=token),
        session_id=session_id,
        default_timeout=10.0,
    )
    await driver.open()
    return agent, driver


def _flatten(contents: list) -> str:
    """All text + function-call + function-response payloads flattened to one
    searchable string."""
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


async def test_tool_result_survives_to_next_turn() -> None:
    """The secret a turn-1 tool returned (never spoken) is present in the contents
    ADK's model sees on turn 2 — the core cross-turn-memory guarantee."""
    llm = ScriptedLlm(_script())
    agent, driver = await _host(llm)
    try:
        await driver.start_session()
        await driver.user_says("Look up the Poddar booking.")
        await driver.user_says("What's my booking reference?")

        turn2_prompt = _flatten(llm.captured_contents[-1])
        assert SECRET_REF in turn2_prompt, (
            f"turn-1 tool result did not survive to turn 2 — cross-turn amnesia:\n{turn2_prompt!r}"
        )
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_carried_tool_calls_are_paired() -> None:
    """Every function_call carried into a later prompt has its matching
    function_response — real Gemini rejects an orphaned call, so a reconstructed
    history must be well-formed, not merely present."""
    llm = ScriptedLlm(_script())
    agent, driver = await _host(llm)
    try:
        await driver.start_session()
        await driver.user_says("Look up the Poddar booking.")
        await driver.user_says("What's my booking reference?")

        turn2 = llm.captured_contents[-1]
        call_names: list[str] = []
        resp_names: list[str] = []
        for c in turn2:
            for p in c.parts or []:
                fc = getattr(p, "function_call", None)
                if fc is not None:
                    call_names.append(fc.name or "")
                fr = getattr(p, "function_response", None)
                if fr is not None:
                    resp_names.append(fr.name or "")
        assert call_names == ["get_booking"], call_names
        assert resp_names == ["get_booking"], (
            f"function_call {call_names} carried forward with no matching "
            f"function_response {resp_names} — orphaned call, Gemini would 400"
        )
    finally:
        await driver.aclose()
        await agent.aclose()
