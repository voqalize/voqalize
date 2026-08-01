"""The ADK session is the source of truth — not a parallel SDK-owned transcript.

A customer picks Google ADK precisely because its ``SessionService`` is the
DB-backed history *they* control: their tool/thought log, their resumability, and
any events they add **out of band** (a retrieved document, a CRM note, a policy
reminder injected between turns). The mature adapter must let ADK's own session be
what the model prompts from — correcting past turns to heard-truth in place — rather
than overwriting ``llm_request.contents`` wholesale from a side transcript that knows
nothing the customer added.

These two tests pin exactly that, and fail against any wholesale-replace design:

1. **Out-of-band events survive into the next prompt.** The customer appends an event
   to the ADK session between turns; it must appear in the following model call. A
   reanchor that rebuilds contents from an SDK-owned transcript obliterates it.
2. **Heard-truth is persisted in the ADK session after a barge.** The correction the
   user actually heard is written back into ADK's session (the accountant event), so
   a ``SessionService`` the customer resumes from carries the truth — heard-truth is
   not stranded in a store that dies with the socket.
"""

from __future__ import annotations

import pytest

pytest.importorskip("google.adk")

from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

from voqalize.conformance import (
    DirectConnection,
    VoiceDriver,
    generate_keypair,
    mint_pygato_token,
)
from voqalize.google_adk import adk_brain
from voqalize.google_adk.testing import ScriptedLlm, reply
from voqalize.sdk import DirectAgent, brain_factory

APP_NAME = "voqalize"
INSTRUCTION = "You are a travel desk."
OOB_MARKER = "OUT_OF_BAND_CONTEXT_VIP_12345"
SENTINEL = "NEVER_HEARD_AFTER_BARGE_IN"


def build_agent(model: str | BaseLlm) -> LlmAgent:
    return LlmAgent(name="desk", model=model, instruction=INSTRUCTION)


def _flatten(contents: list) -> str:
    out: list[str] = []
    for c in contents:
        for p in c.parts or []:
            if getattr(p, "text", None):
                out.append(p.text)
    return " ".join(out)


class _RunnerHolder:
    """Captures the ADK ``Runner`` the adapter built via ``runner_factory``, so the
    test can reach into the *same* session service the customer would."""

    runner: InMemoryRunner | None = None

    def factory(self, agent: LlmAgent) -> InMemoryRunner:
        self.runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
        return self.runner


async def _host(
    llm: ScriptedLlm, *, session_id: str, holder: _RunnerHolder
) -> tuple[DirectAgent, VoiceDriver]:
    keypair = generate_keypair()
    make = adk_brain(
        lambda: build_agent(llm),
        greeting="Travel desk, how can I help?",
        streaming=True,
        answer_conformance_dump=True,
        runner_factory=holder.factory,
    )
    agent = DirectAgent(
        factory=brain_factory(make), host="127.0.0.1", port=0, public_keys=keypair.public_pem
    )
    port = await agent.start()
    token = mint_pygato_token(
        private_key_pem=keypair.private_pem,
        session_id=session_id,
        agent_id="desk",
        tenant_id="demo",
    )
    driver = VoiceDriver(
        DirectConnection(f"ws://127.0.0.1:{port}", session_id, token=token),
        session_id=session_id,
        agent_id="desk",
        default_timeout=10.0,
    )
    await driver.open()
    return agent, driver


async def test_out_of_band_session_event_reaches_the_next_prompt() -> None:
    """The customer appends an event to ADK's session between turns; the model sees it
    on the following call. Under a wholesale ``llm_request.contents`` replace from a
    side transcript, this event is obliterated and the assertion fails."""
    sid = "adk-oob-survives"
    holder = _RunnerHolder()
    llm = ScriptedLlm(
        {
            "Hello.": [reply("Hi there!")],
            "Any advice?": [reply("Sure — pack light.")],
        }
    )
    agent, driver = await _host(llm, session_id=sid, holder=holder)
    try:
        await driver.start_session()
        await driver.user_says("Hello.")

        # The customer injects out-of-band context into ADK's own session — exactly
        # the thing they chose ADK's SessionService to be able to do.
        assert holder.runner is not None
        svc = holder.runner.session_service
        session = await svc.get_session(app_name=APP_NAME, user_id=sid, session_id=sid)
        assert session is not None
        from google.adk.events.event import Event

        await svc.append_event(
            session,
            Event(
                invocation_id="oob-1",
                author="user",
                content=types.Content(role="user", parts=[types.Part(text=OOB_MARKER)]),
            ),
        )

        await driver.user_says("Any advice?")
        prompt = llm.captured_contents[-1]
        assert OOB_MARKER in _flatten(prompt), (
            "an event the customer added to ADK's session out-of-band never reached "
            f"the model — the adapter is not sourcing history from ADK's session: {_flatten(prompt)!r}"
        )
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_barge_heard_truth_is_written_back_into_the_adk_session() -> None:
    """After a barge, the heard prefix is recorded in ADK's own session (the accountant
    event), so a ``SessionService`` the customer persists/resumes from carries the
    truth. The un-heard generated tail must not be the session's effective history."""
    sid = "adk-heard-persisted"
    holder = _RunnerHolder()
    llm = ScriptedLlm(
        {"Tell me about Kyoto.": [reply(chunks=["Kyoto is ", SENTINEL], chunk_delay=0.3)]}
    )
    agent, driver = await _host(llm, session_id=sid, holder=holder)
    try:
        await driver.start_session()
        t = await driver.barge_in(
            "Tell me about Kyoto.", speak_delay=0.12, heard_prefix="Kyoto is "
        )
        assert t.heard == "Kyoto is "

        # Give the finalize a beat to be applied to the ADK session.
        await driver.dump_conversation()

        assert holder.runner is not None
        svc = holder.runner.session_service
        session = await svc.get_session(app_name=APP_NAME, user_id=sid, session_id=sid)
        assert session is not None
        texts = [
            "".join(p.text for p in (e.content.parts or []) if getattr(p, "text", None))
            for e in session.events
            if e.content is not None
        ]
        joined = " ".join(texts)
        # The heard prefix is recorded in ADK's session; the un-heard tail is not the
        # effective heard-truth there.
        assert any("Kyoto is " in x for x in texts), (
            f"heard-truth was not written back into the ADK session: {texts}"
        )
        assert SENTINEL not in joined, (
            f"the un-heard generated tail is present in the ADK session as truth: {joined!r}"
        )
    finally:
        await driver.aclose()
        await agent.aclose()
