"""End-to-end conformance of the Google ADK integration, no network, no real LLM.

Hosts the **client-authored** travel agent (``examples/travel_adk/agent.py``)
wrapped by the SDK's :func:`voqalize.google_adk.adk_brain`, backed by a
:class:`ScriptedLlm` fake model, over a real ``BrainServer`` WebSocket. Drives it
with the conformance :class:`VoqalizeDriver` — the exact PyGato-side leg — and
asserts the wire MUSTs from ``docs/reference/wire`` via the shared
``conformance.checks`` library.

Two things are proven here that the live-Gemini shape check could not assert
deterministically:

* **A tool round-trip is faithful multi-inference.** One user turn drives two
  model calls (emit the ``function_call``, then answer given the tool result) →
  two inference brackets, the tools fire their ``ui_command``s, and the committed
  conversation is heard-truth.
* **Barge-in corrects the next prompt to heard text.** A reply is cut mid-stream;
  the un-heard tail (``SENTINEL``) is never committed *and* never appears in the
  contents the model sees on the following turn — the SDK corrected ADK's own
  assembled history to heard-truth (dropping the generated tail), not left it at
  ADK's raw event log.
"""

from __future__ import annotations

import pytest

pytest.importorskip("google.adk")

from examples.travel_adk.agent import GREETING, build_travel_agent

from voqalize.conformance import (
    BrainServer,
    DirectConnection,
    VoqalizeDriver,
    checks,
    generate_keypair,
    mint_voqalize_token,
)
from voqalize.google_adk import adk_brain
from voqalize.google_adk.testing import ScriptedLlm, reply, reply_and_call

SENTINEL = "NEVER_HEARD_AFTER_BARGE_IN"

_FLIGHTS = [
    {"airline": "IndiGo", "flight_no": "6E-123", "price": 28000},
    {"airline": "Vietnam Airlines", "flight_no": "VN-567", "price": 35000},
]


def _script() -> dict:
    """The scripted dialogue: keyed by the exact user utterance, one Reply per
    model call (a tool round-trip keys two Replies under the same utterance)."""
    return {
        "Show me flights to Hanoi.": [
            reply_and_call(
                "Sure, pulling up flights.",
                "search_flights",
                leg="Bangalore to Hanoi",
                options=_FLIGHTS,
            ),
            reply("I found two options. The cheapest is IndiGo at 28000 rupees."),
        ],
        # A single streamed reply whose sentinel tail arrives only after a pause,
        # so a barge-in lands after the first chunk and cuts the rest.
        "What about the cheapest?": [
            reply(chunks=["The cheapest is IndiGo, ", SENTINEL], chunk_delay=0.4),
        ],
        "Book it.": [
            reply_and_call(
                "Great choice.",
                "select_flight",
                leg="Bangalore to Hanoi",
                flight_no="6E-123",
            ),
            reply("Done. The Poddar family is booked on IndiGo 6E-123."),
        ],
    }


async def _host(llm: ScriptedLlm) -> tuple[BrainServer, VoqalizeDriver]:
    keypair = generate_keypair()
    make = adk_brain(
        lambda: build_travel_agent(llm),
        greeting=GREETING,
        streaming=True,
        answer_conformance_dump=True,
    )
    agent = BrainServer(make, public_keys=keypair.public_pem)
    port = await agent.start()
    session_id = "adk-travel-test"
    token = mint_voqalize_token(
        private_key_pem=keypair.private_pem,
        session_id=session_id,
        agent_id="travel",
        tenant_id="demo",
    )
    driver = VoqalizeDriver(
        DirectConnection(f"ws://127.0.0.1:{port}", session_id, token=token),
        session_id=session_id,
        default_timeout=10.0,
    )
    await driver.open()
    return agent, driver


async def test_scripted_multi_turn_with_tool_calls() -> None:
    """A greeting + two user turns (one spanning a tool round-trip) satisfy the
    bracket / completion / greeting MUSTs, fire the UI actions, and commit a
    heard-truth conversation."""
    agent, driver = await _host(ScriptedLlm(_script()))
    try:
        greeting = await driver.start_session()
        checks.check_greeting(driver, greeting)

        t1 = await driver.user_says("Show me flights to Hanoi.")
        # Tool round-trip ⇒ two model calls ⇒ two inference brackets.
        assert len(t1.inferences) == 2, [i.text for i in t1.inferences]
        checks.check_brackets_closed(t1)
        checks.check_inference_ids_monotonic(t1)
        checks.check_completed(t1)
        checks.check_spoke(t1)

        t2 = await driver.user_says("Book it.")
        assert len(t2.inferences) == 2
        checks.check_brackets_closed(t2)
        checks.check_completed(t2)

        # The tools drove the screen: search on turn 1, select on turn 2.
        actions = [
            c.get("action")
            for c in driver.ui_commands
            if not str(c.get("action", "")).startswith("__")
        ]
        assert actions == ["search_flights", "select_flight"], actions
        # The model's invented options rode the ui_command payload unchanged.
        search = next(c for c in driver.ui_commands if c.get("action") == "search_flights")
        assert search["options"] == _FLIGHTS

        # No proactive speech, and heard-truth is the exact committed sequence.
        checks.check_no_unsolicited_epochs(driver, opened={t1.epoch, t2.epoch})
        state = await driver.dump_conversation()
        checks.check_conversation_sequence(
            state,
            expected=[
                {"role": "assistant", "content": GREETING},
                {"role": "user", "content": "Show me flights to Hanoi."},
                {"role": "assistant", "content": "Sure, pulling up flights."},
                {
                    "role": "assistant",
                    "content": "I found two options. The cheapest is IndiGo at 28000 rupees.",
                },
                {"role": "user", "content": "Book it."},
                {"role": "assistant", "content": "Great choice."},
                {
                    "role": "assistant",
                    "content": "Done. The Poddar family is booked on IndiGo 6E-123.",
                },
            ],
        )
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_barge_in_commits_heard_and_corrects_next_prompt() -> None:
    """A barge-in mid-reply: the drain barrier is echoed,
    the un-heard tail is neither spoken nor committed, and — the load-bearing
    assertion — the *next* model call sees the HEARD partial, not the tail."""
    llm = ScriptedLlm(_script())
    agent, driver = await _host(llm)
    try:
        await driver.start_session()
        await driver.user_says("Show me flights to Hanoi.")

        t2 = await driver.barge_in("What about the cheapest?", speak_delay=0.15)
        assert t2.interrupted
        # Heard the first chunk, never the sentinel tail.
        assert t2.heard == "The cheapest is IndiGo, ", repr(t2.heard)
        checks.check_interruption_echoed(driver)
        checks.check_no_speech_after_barge_in(driver, t2, forbidden=SENTINEL)

        # The committed conversation records the heard partial, not the tail.
        state = await driver.dump_conversation()
        checks.check_conversation_heard(
            state,
            expected_tail=[
                {"role": "user", "content": "What about the cheapest?"},
                {"role": "assistant", "content": "The cheapest is IndiGo, "},
            ],
        )

        # The correction: drive one more turn and inspect what the model was asked.
        await driver.user_says("Book it.")
        last_contents = llm.captured_contents[-1]
        flat = " ".join(
            "".join(p.text for p in (c.parts or []) if getattr(p, "text", None))
            for c in last_contents
        )
        assert SENTINEL not in flat, f"generated tail leaked into the prompt: {flat!r}"
        assert "The cheapest is IndiGo," in flat, f"heard partial missing from prompt: {flat!r}"
    finally:
        await driver.aclose()
        await agent.aclose()
