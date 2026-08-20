"""Drive the ADK travel agent end-to-end over the real wire, with real Gemini.

Hosts ``build_travel_agent`` wrapped by ``adk_brain`` on a ``brain_server`` (a real
localhost WebSocket), then drives it with the conformance ``VoiceDriver`` —
exactly the PyGato-side leg, over real TCP, minting a real pygato token. This is
the shape check: prove the SDK drives ADK, speaks per model call, fires the UI
actions, and commits heard-truth history — before we swap Gemini for a scripted
fake.

Run (needs GEMINI_API_KEY, from the repo-root .env):

    cd sdk/python
    set -a && . ../../.env && set +a
    GOOGLE_API_KEY="$GEMINI_API_KEY" uv run python -m examples.travel_adk.run_conformance
"""

from __future__ import annotations

import asyncio
import json
import os

from voqalize.conformance import (
    DirectConnection,
    VoiceDriver,
    brain_server,
    generate_keypair,
    mint_pygato_token,
)
from voqalize.google_adk import adk_brain

from .agent import GREETING, build_travel_agent

MODEL = os.environ.get("ADK_MODEL", "gemini-3.1-flash-lite")


def _print_turn(label: str, turn) -> None:
    print(f"\n### {label}")
    if turn is None:
        print("  (no turn)")
        return
    print(f"  interaction {turn.interaction_id}  completed={turn.completed}")
    for inf in turn.inferences:
        print(f"    inference {inf.inference_id}: heard={inf.text!r}")


async def main() -> None:
    keypair = generate_keypair()
    make_brain = adk_brain(
        lambda: build_travel_agent(MODEL),
        greeting=GREETING,
        streaming=True,
        answer_conformance_dump=True,
    )
    session_id = "travel-adk-demo"
    token = mint_pygato_token(
        private_key_pem=keypair.private_pem,
        session_id=session_id,
        agent_id="travel",
        tenant_id="demo",
    )
    async with brain_server(make_brain, public_keys=keypair.public_pem) as server:
        print(f"hosting ADK travel brain (model={MODEL}) on {server.url}")
        driver = VoiceDriver(
            DirectConnection(server.url, session_id, token=token),
            session_id=session_id,
            agent_id="travel",
            default_timeout=30.0,
        )
        try:
            await driver.open()
            greeting = await driver.start_session(greeting_timeout=30.0)
            _print_turn("greeting (interaction 0)", greeting)

            t1 = await driver.user_says(
                "Start a new trip: Poddar family to Hanoi, 12th to 18th August 2026.",
                timeout=45.0,
            )
            _print_turn("user: start trip", t1)

            t2 = await driver.user_says(
                "Now show me flights from Bangalore to Hanoi.", timeout=45.0
            )
            _print_turn("user: show flights", t2)

            t3 = await driver.user_says("Pick the cheapest one.", timeout=45.0)
            _print_turn("user: pick cheapest", t3)

            print("\n### UI commands the brain fired (ui_command lane)")
            for cmd in driver.ui_commands:
                action = cmd.get("action")
                keys = [k for k in cmd if k not in ("type", "action", "action_id")]
                print(f"  {action}  fields={keys}")

            print("\n### committed conversation (heard-truth backchannel)")
            state = await driver.dump_conversation(timeout=10.0)
            for m in state["messages"]:
                print(f"  {m['role']:>9}: {m['content']!r}")

            await driver.end_session()
        finally:
            await driver.aclose()

    print("\nraw ui_commands:")
    print(json.dumps(driver.ui_commands, indent=2)[:2000])


if __name__ == "__main__":
    asyncio.run(main())
