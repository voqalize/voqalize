"""The travel demo's ADK brain, end-to-end over the wire — no network, no LLM key.

The sibling ``test_conformance.py`` proves the demos are *wired* to the transport
(a fixed greeting rides the wire). This file goes one layer further for the one
demo that runs on the Google ADK adapter: it hosts the **real**
``TravelBrain`` — the shipping ``demos/travel/backend/brain.py``, its real prompt,
its real ten tools — on a real ``DirectAgent`` WebSocket, swaps only the *model*
for a :class:`ScriptedLlm`, and drives it with the conformance ``VoiceDriver``
(the exact PyGato-side leg).

Swapping just the model is what makes this deterministic: a scripted tool call
carries the exact arguments we assert the browser receives, so the demo's
``ui_command`` contract is a test, not a hope.

Three properties are covered:

* **the greeting + a tool round-trip.** One user turn drives two model calls (emit
  the ``function_call``, then answer given the tool result) → two inference
  brackets, and the tools fire the ``ui_command``s the ``/travel`` UI renders,
  with the ids the brain assigns.
* **barge-in re-anchors the next prompt.** A reply is cut mid-stream; the un-heard
  tail is never committed and never reaches the model's next prompt — the SDK
  corrected ADK's own history to heard-truth.
* **``state_sync`` grounds every prompt.** The browser's screen snapshot lands in
  the *system instruction* of the next model call, which is the ADK-native
  replacement for the old ``get_active_itinerary`` tool.

Run: ``cd demos && uv run pytest tests/test_travel_adk.py``
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import pytest

pytest.importorskip("google.adk")

from google.adk.models.llm_response import LlmResponse
from pydantic import PrivateAttr
from voqalize_demos.discovery import discover

# The demo backends are loaded from source, in place (see ``discovery``) — running
# discovery is what makes ``demos/travel/backend/`` importable, under the synthetic
# package name it mounts them at. Importing the brain class through that same path
# is the test asserting on the module the umbrella will actually serve.
discover()

from voqalize_demos._loaded.travel.brain import TravelBrain  # noqa: E402

from voqalize.conformance import (  # noqa: E402
    DirectConnection,
    VoiceDriver,
    checks,
    generate_keypair,
    mint_pygato_token,
)
from voqalize.google_adk.testing import (  # noqa: E402
    Reply,
    ScriptedLlm,
    reply,
    reply_and_call,
)
from voqalize.sdk import DirectAgent, brain_factory  # noqa: E402

GREETING = "नमस्ते, मैं प्रिया हूँ ट्रैवल डेस्क से। हम किस ट्रिप पर काम करें?"
SENTINEL = "NEVER_HEARD_AFTER_BARGE_IN"

# Deliberately id-less: the brain assigns f1/f2 (the UI keys selection off `id`).
_FLIGHTS = [
    {"airline": "IndiGo", "flight_no": "6E-123", "depart": "BLR 02:15", "price": 28000},
    {"airline": "Vietnam Airlines", "flight_no": "VN-567", "depart": "BLR 06:40", "price": 35000},
]


class _CapturingLlm(ScriptedLlm):
    """A ``ScriptedLlm`` that also records each request's *system instruction* —
    where ADK puts an ``InstructionProvider``'s output, and therefore where the
    travel brain's screen grounding lands."""

    _instructions: list[str] = PrivateAttr(default_factory=list)

    @property
    def captured_instructions(self) -> list[str]:
        return self._instructions

    async def generate_content_async(  # type: ignore[override]
        self, llm_request: Any, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        config = getattr(llm_request, "config", None)
        self._instructions.append(str(getattr(config, "system_instruction", "") or ""))
        async for response in super().generate_content_async(llm_request, stream=stream):
            yield response


def _script() -> dict[str, Any]:
    """The scripted dialogue: keyed by the exact user utterance, one Reply per
    model call (a tool round-trip keys two Replies under the same utterance)."""
    return {
        "Start the Poddar Vietnam trip, 12th to 18th August 2026.": [
            # Not ``reply_and_call``: this tool takes a ``name`` argument, which
            # collides with that helper's own ``name`` parameter (it forwards tool
            # args as **kwargs). Build the Reply directly instead.
            Reply(
                text="Sure, opening that up.",
                calls=(
                    (
                        "create_itinerary",
                        {
                            "name": "Poddar Vietnam",
                            "destination": "Ho Chi Minh and Phu Quoc",
                            "start_date": "12 Aug 2026",
                            "end_date": "18 Aug 2026",
                        },
                    ),
                ),
            ),
            reply("Poddar Vietnam is open. Shall we do the outbound flight?"),
        ],
        "Show me the outbound flights.": [
            reply_and_call(
                "Pulling up flights.",
                "search_flights",
                leg_id="blr-out",
                options=_FLIGHTS,
            ),
            reply("Two options are up. IndiGo is cheapest at 28000 rupees."),
        ],
        # A single streamed reply whose sentinel tail arrives only after a pause,
        # so a barge-in lands after the first chunk and cuts the rest.
        "What about the cheapest?": [
            reply(chunks=["The cheapest is IndiGo, ", SENTINEL], chunk_delay=0.4),
        ],
        "Book it.": [
            reply_and_call("Great choice.", "select_flight", leg_id="blr-out", option_id="f1"),
            reply("Done. IndiGo 6E-123 is pinned to the outbound leg."),
        ],
        "Which hotels are showing?": [
            reply("You're on the Phu Quoc hotels screen with three options up."),
        ],
    }


async def _host(llm: ScriptedLlm) -> tuple[DirectAgent, VoiceDriver]:
    """Host the real TravelBrain (scripted model) on a real localhost socket and
    open a PyGato-side driver against it."""
    keypair = generate_keypair()
    agent = DirectAgent(
        factory=brain_factory(lambda: TravelBrain(model=llm, answer_conformance_dump=True)),
        host="127.0.0.1",
        port=0,
        public_keys=keypair.public_pem,
    )
    port = await agent.start()
    session_id = "travel-adk-test"
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


def _actions(driver: VoiceDriver) -> list[str]:
    """The ui_command actions the brain fired, minus the conformance backchannel."""
    return [
        str(c.get("action"))
        for c in driver.ui_commands
        if not str(c.get("action", "")).startswith("__")
    ]


async def test_greeting_and_tool_roundtrip_drive_the_screen() -> None:
    """The fixed Hindi greeting, then two turns each spanning a tool round-trip:
    two inference brackets per turn, the exact ``ui_command`` payloads the
    ``/travel`` UI consumes, and a heard-truth conversation."""
    agent, driver = await _host(_CapturingLlm(_script()))
    try:
        greeting = await driver.start_session()
        checks.check_greeting(driver, greeting)
        assert greeting is not None and greeting.text == GREETING

        t1 = await driver.user_says("Start the Poddar Vietnam trip, 12th to 18th August 2026.")
        # Tool round-trip ⇒ two model calls ⇒ two inference brackets.
        assert len(t1.inferences) == 2, [i.text for i in t1.inferences]
        checks.check_brackets_closed(t1)
        checks.check_inference_ids_monotonic(t1)
        checks.check_completed(t1)
        checks.check_spoke(t1)

        t2 = await driver.user_says("Show me the outbound flights.")
        assert len(t2.inferences) == 2
        checks.check_brackets_closed(t2)
        checks.check_completed(t2)

        assert _actions(driver) == ["create_itinerary", "search_flights"], _actions(driver)

        # create_itinerary wraps the whole shell under `itinerary` — the shape
        # `buildItinerary()` in the UI store reads.
        created = next(c for c in driver.ui_commands if c.get("action") == "create_itinerary")
        assert created["itinerary"] == {
            "name": "Poddar Vietnam",
            "coordinator": "",
            "destination": "Ho Chi Minh and Phu Quoc",
            "start_date": "12 Aug 2026",
            "end_date": "18 Aug 2026",
            "summary": "",
            "families": [],
            "legs": [],
            "hotel_cities": [],
        }

        # search_flights passes the model's invented options through, with the
        # stable ids the brain assigns when the model omits them.
        search = next(c for c in driver.ui_commands if c.get("action") == "search_flights")
        assert search["leg_id"] == "blr-out"
        assert search["options"] == [
            {**_FLIGHTS[0], "id": "f1"},
            {**_FLIGHTS[1], "id": "f2"},
        ]

        checks.check_no_unsolicited_interactions(
            driver, opened={t1.interaction_id, t2.interaction_id}
        )
        state = await driver.dump_conversation()
        checks.check_conversation_sequence(
            state,
            expected=[
                {"role": "assistant", "content": GREETING},
                {
                    "role": "user",
                    "content": "Start the Poddar Vietnam trip, 12th to 18th August 2026.",
                },
                {"role": "assistant", "content": "Sure, opening that up."},
                {
                    "role": "assistant",
                    "content": "Poddar Vietnam is open. Shall we do the outbound flight?",
                },
                {"role": "user", "content": "Show me the outbound flights."},
                {"role": "assistant", "content": "Pulling up flights."},
                {
                    "role": "assistant",
                    "content": "Two options are up. IndiGo is cheapest at 28000 rupees.",
                },
            ],
        )
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_barge_in_commits_heard_and_corrects_next_prompt() -> None:
    """A barge-in mid-reply: the drain barrier is echoed, completion is skipped,
    the un-heard tail is neither spoken nor committed, and — the load-bearing
    assertion — the *next* model call sees the HEARD partial, not the tail."""
    llm = _CapturingLlm(_script())
    agent, driver = await _host(llm)
    try:
        await driver.start_session()
        await driver.user_says("Show me the outbound flights.")

        t2 = await driver.barge_in("What about the cheapest?", speak_delay=0.15)
        assert t2.interrupted
        assert t2.heard == "The cheapest is IndiGo, ", repr(t2.heard)
        checks.check_interruption_echoed(driver)
        checks.check_barge_in_skips_completion(driver, t2)
        checks.check_no_speech_after_barge_in(driver, t2, forbidden=SENTINEL)

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
        flat = " ".join(
            "".join(p.text for p in (c.parts or []) if getattr(p, "text", None))
            for c in llm.captured_contents[-1]
        )
        assert SENTINEL not in flat, f"generated tail leaked into the prompt: {flat!r}"
        assert "The cheapest is IndiGo," in flat, f"heard partial missing from prompt: {flat!r}"
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_state_sync_grounds_the_next_prompt() -> None:
    """The browser's ``state_sync`` snapshot reaches the model as *system
    instruction* on the next call — the ADK ``InstructionProvider`` grounding that
    replaced the old ``get_active_itinerary`` tool. It is ingested silently: no
    interaction is opened, so the agent never speaks because a screen changed."""
    llm = _CapturingLlm(_script())
    agent, driver = await _host(llm)
    try:
        await driver.start_session()
        # Before any snapshot, the prompt says the dashboard is showing.
        first = await driver.user_says("Show me the outbound flights.")
        assert "No itinerary is open yet" in llm.captured_instructions[0]

        await driver.send_client_message(
            "state_sync",
            {
                "itinerary": {
                    "name": "Poddar Vietnam",
                    "screen": "hotels",
                    "screen_context": "Phu Quoc",
                    "hotels": [{"city": "Phu Quoc", "options_shown": 3, "selected": None}],
                }
            },
        )
        # Same socket, ordered delivery — a beat so the brain has ingested it
        # before the next turn's model call assembles its instruction.
        await asyncio.sleep(0.1)

        turn = await driver.user_says("Which hotels are showing?")
        checks.check_completed(turn)
        grounded = llm.captured_instructions[-1]
        assert "ON SCREEN RIGHT NOW" in grounded
        assert '"screen": "hotels"' in grounded, grounded[-500:]
        assert '"screen_context": "Phu Quoc"' in grounded, grounded[-500:]
        assert "No itinerary is open yet" not in grounded

        # A client message the brain only records must not open an interaction.
        checks.check_no_unsolicited_interactions(
            driver, opened={first.interaction_id, turn.interaction_id}
        )
    finally:
        await driver.aclose()
        await agent.aclose()
