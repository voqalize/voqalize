"""Multi-agent (root → sub-agent hand-off) — the corrector must reach sub-agents.

A real ADK app is often a tree: a root triage ``LlmAgent`` that ``transfer_to_agent``s
to specialist sub-agents, each making its **own** model calls. Two things must hold
for voice, and installing the corrector on the root alone breaks both:

1. **Every agent prompts from heard-truth.** The sub-agent's model call must see ADK's
   session corrected to what the user actually heard, not ADK's raw event log. We
   install the ``before_model_callback`` corrector on every ``LlmAgent`` in the
   sub-agent tree, so the sub-agent's contents are corrected to — here — just the user
   turn, not ADK's raw ``user → transfer_call → transfer_response`` log.
2. **The hand-off itself is invisible to history.** ADK's internal ``transfer_to_agent``
   call is routing bookkeeping, not a client tool; the corrector strips its
   ``function_call`` / ``function_response`` parts **and** ADK's ``_convert_foreign_event``
   "For context:" hand-off turn, or it would replay into every later prompt. We assert
   the corrected prompt carries only the client's real tool (``book_table``), not the
   transfer.
"""

from __future__ import annotations

import pytest

pytest.importorskip("google.adk")

from google.adk.agents import LlmAgent

from voqalize._framework.heard import text_of
from voqalize.conformance import (
    DirectConnection,
    VoqalizeDriver,
    checks,
    generate_keypair,
    mint_voqalize_token,
)
from voqalize.google_adk import adk_brain
from voqalize.google_adk.testing import ScriptedLlm, call, reply
from voqalize.sdk import DirectAgent, brain_factory

GREETING = "Front desk, how can I help?"
SESSION_ID = "adk-subagents-test"
UTTERANCE = "Book me a table for two at seven."


def book_table(time: str, party_size: int) -> dict:
    """Book a table (the sub-agent's real client tool)."""
    return {"status": "booked", "time": time, "party_size": party_size}


def _tool_names(contents: list) -> list[str]:
    """Every function-call / function-response name across a rendered prompt's
    contents — used to prove which tool round-trips reached heard-truth."""
    names: list[str] = []
    for c in contents:
        for p in c.parts or []:
            if getattr(p, "function_call", None):
                names.append(p.function_call.name)
            if getattr(p, "function_response", None):
                names.append(p.function_response.name)
    return names


async def test_handoff_corrects_the_subagent_and_hides_the_transfer() -> None:
    """A root agent transfers to a booking sub-agent. The sub-agent's model prompts
    from heard-truth (the corrector reached it), and ADK's internal ``transfer_to_agent``
    never lands in the corrected tool history — only the real ``book_table`` does."""
    # Distinct models per agent so we can prove the SUB-agent was corrected: its
    # captured contents must be corrected to the user turn, not ADK's raw event log.
    root_model = ScriptedLlm({UTTERANCE: [call("transfer_to_agent", agent_name="booking")]})
    booking_model = ScriptedLlm(
        {
            UTTERANCE: [
                call("book_table", time="19:00", party_size=2),
                reply("Booked — a table for two at seven."),
            ]
        }
    )

    def build_agent() -> LlmAgent:
        booking = LlmAgent(
            name="booking",
            model=booking_model,
            instruction="You book tables. Use book_table.",
            tools=[book_table],
        )
        return LlmAgent(
            name="triage",
            model=root_model,
            instruction="Route booking requests to the booking agent.",
            sub_agents=[booking],
        )

    keypair = generate_keypair()
    make = adk_brain(build_agent, greeting=GREETING, streaming=True, answer_conformance_dump=True)
    agent = DirectAgent(
        factory=brain_factory(make), host="127.0.0.1", port=0, public_keys=keypair.public_pem
    )
    port = await agent.start()
    token = mint_voqalize_token(
        private_key_pem=keypair.private_pem,
        session_id=SESSION_ID,
        agent_id="triage",
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

        t = await driver.user_says(UTTERANCE)
        checks.check_completed(t)
        # The whole hand-off resolved to the sub-agent's spoken answer.
        assert "Booked" in t.text, t.text

        # 1. The sub-agent was corrected: its first model call saw the corrected
        #    history — exactly the user turn — not ADK's raw
        #    user → transfer_call → transfer_response event log (which would be >1 item
        #    and carry a function_call/response part). Installing the corrector on the
        #    root alone leaves this at ADK's event log and the assertion fails.
        assert booking_model.captured_contents, "the booking sub-agent never ran"
        first = booking_model.captured_contents[0]
        assert len(first) == 1, [text_of(c) for c in first]
        assert first[0].role == "user"
        assert UTTERANCE in text_of(first[0])

        # 2. The transfer is invisible to heard-truth: across every prompt the
        #    sub-agent saw, the client's real book_table round-trip is rendered but
        #    ADK's internal transfer_to_agent never is — so it can't replay into a
        #    later turn. (The sub-agent's *answer* call, [1], renders the tool step.)
        seen = [n for cc in booking_model.captured_contents for n in _tool_names(cc)]
        assert "book_table" in seen, seen
        assert "transfer_to_agent" not in seen, seen

        # 3. The pure hand-off opened no inference bracket: exactly the sub-agent's two
        #    model calls (book_table, then the spoken answer) — not a third empty one.
        assert len(t.inferences) == 2, [inf.text for inf in t.inferences]
    finally:
        await driver.aclose()
        await agent.aclose()
