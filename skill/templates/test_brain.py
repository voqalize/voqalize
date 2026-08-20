"""Test your brain with no voice runtime, no audio, and no human.

`voqalize.conformance` ships a `VoiceDriver` — a protocol-compliant *fake
Voqalize*. It hosts your real `Brain` on a real localhost WebSocket, mints a real
PyGato token, speaks the real `Vql*` wire, and models playout/heard-truth the way
the runtime does. You drive it in **text mode**: `user_says("…")` in, a `Turn` with
`.text` out. That makes a voice agent testable exactly like any other service.

Keep one of these files per use case in your repo and run it in CI. This is the
eval primitive: a scenario is a conversation script plus assertions.

    uv pip install -e path/to/voqalize/sdk/python   # ships voqalize.conformance
    pytest -q test_brain.py
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from voqalize.conformance import (
    DirectConnection,
    VoiceDriver,
    generate_keypair,
    mint_pygato_token,
)
from voqalize.sdk import DirectAgent, brain_factory

from brain import MyBrain  # your Brain subclass

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def driver():
    """Host MyBrain on an ephemeral port and hand back a connected VoiceDriver.

    `port=0` binds anything free, so tests never collide. The keypair is minted
    per test run: the brain verifies against `keypair.public_pem`, the driver signs
    with `keypair.private_pem` — so token verification is exercised for real
    instead of being switched off.
    """
    keypair = generate_keypair()
    agent = DirectAgent(
        factory=brain_factory(MyBrain),
        host="127.0.0.1",
        port=0,
        public_keys=keypair.public_pem,
    )
    port = await agent.start()

    session_id = "test-session"
    token = mint_pygato_token(
        private_key_pem=keypair.private_pem,
        session_id=session_id,
        agent_id="agent_test",
        tenant_id="tenant_test",
    )
    drv = VoiceDriver(
        DirectConnection(f"ws://127.0.0.1:{port}", session_id, token=token),
        session_id=session_id,
        agent_id="agent_test",
        default_timeout=10.0,  # raise this when a real LLM is in the loop
    )
    await drv.open()
    try:
        yield drv
    finally:
        await drv.aclose()
        await agent.aclose()


async def test_greets_on_connect(driver: VoiceDriver) -> None:
    """The agent speaks first. `start_session` sends VqlStart and plays out
    interaction 0; `payload=` is what the browser passes as `payload` at connect,
    and lands brain-side as `start.init`."""
    greeting = await driver.start_session(payload={"user": {"name": "Ada"}})
    assert greeting is not None, "brain did not greet"
    assert "Ada" in greeting.text


async def test_answers_a_question(driver: VoiceDriver) -> None:
    await driver.start_session()
    turn = await driver.user_says("Add two oat milks to my cart.")
    assert turn.completed, "interaction never completed — the brain may have hung"
    assert "oat milk" in turn.text.lower()


async def test_drives_the_screen(driver: VoiceDriver) -> None:
    """Every `interaction.action(name, args)` the brain fires arrives on the
    driver's `ui_commands` lane, in the exact envelope the browser sees."""
    await driver.start_session()
    await driver.user_says("Add two oat milks to my cart.")

    cmds = await driver.collect_ui_commands(min_count=1)
    add = next(c for c in cmds if c["action"] == "add_to_cart")
    assert add["sku"] == "oat-milk"
    assert add["qty"] == 2

    # Report back what the UI did with it — the brain's `callback=` fires on this.
    await driver.send_action_result(add["action_id"], status="ok", result={"lines": 1})


async def test_client_message_is_ingested_silently(driver: VoiceDriver) -> None:
    """The user edited the cart by hand. The brain should absorb it, not talk."""
    await driver.start_session()
    await driver.send_client_message("cart_edited", {"removed": "oat-milk"})
    turn = await driver.user_says("What's in my cart?")
    assert "oat milk" not in turn.text.lower()


async def test_client_message_can_take_the_floor(driver: VoiceDriver) -> None:
    """`client_message` (vs `send_client_message`) waits for a spoken reply — use
    it for the messages your brain answers via `message.interaction`."""
    await driver.start_session()
    turn = await driver.client_message("help_tapped", {})
    assert turn.text, "brain did not take the floor on help_tapped"


async def test_barge_in_truncates_the_record(driver: VoiceDriver) -> None:
    """Interrupt mid-sentence. `turn.heard` is the partial the user actually heard
    — that, not the generated tail, is what belongs in conversation history."""
    await driver.start_session()
    turn = await driver.barge_in("Actually, stop.")
    assert turn.interrupted
    assert turn.heard is not None


async def test_idle_nudge(driver: VoiceDriver) -> None:
    """Silence past the idle timeout opens an interaction; the brain may re-engage
    (or stay quiet — then `turn.text` is empty, which is also a valid design)."""
    await driver.start_session()
    turn = await driver.user_idle(level=1, idle_ms=30_000)
    assert "still there" in turn.text.lower()
