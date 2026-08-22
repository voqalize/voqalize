"""``session.configure_*`` — one request out, exactly one answer back.

The four methods are awaitable, and what they wait for is Voice's *validation*:
accepted means Voice took the change whole, rejected means it applied none of it.
That is only useful if it holds from the place a brain actually retunes — inside
a turn, inside the hook that is itself being fed by the same socket the answer
arrives on. So these drive real sessions over a real websocket rather than
poking at the plumbing.

Three outcomes, and a brain has to survive all three: accepted, refused, and the
one the protocol cannot promise away — a Voice that stopped answering.
"""

from __future__ import annotations

import pytest

from voqalize.conformance import (
    BrainServer,
    DirectConnection,
    VoiceDriver,
    generate_keypair,
    mint_pygato_token,
)
from voqalize.sdk import Brain, Chunk, RequestRejected, SpeechEnd, SpeechStart
from voqalize.sdk.wire import ConfigureIdleFrame, ConfigureSttFrame, ConfigureTtsFrame

SESSION_ID = "configure-test"


class TuningBrain(Brain):
    """Retunes from inside the turn, and says what came back.

    Awaiting an answer here is the demanding case: the hook runs on the frame the
    feeder is delivering, so an answer queued behind that feeder would never
    arrive and this turn would never end.
    """

    async def greet(self, session) -> str:
        return "hello"

    async def on_user_message(self, session, msg):
        try:
            await session.configure_stt(eot_threshold=0.75, eot_timeout_ms=4000)
            outcome = "accepted"
        except RequestRejected as exc:
            outcome = f"rejected {exc.op}: {exc.detail}"
        except TimeoutError as exc:
            outcome = f"unanswered: {exc}"
        yield SpeechStart()
        yield Chunk(outcome)
        yield SpeechEnd()


class ThreeWayBrain(TuningBrain):
    """Makes one of each request before the greeting."""

    async def on_session_start(self, session) -> None:
        await session.configure_tts(speed=1.1)
        await session.configure_stt(vad_confidence=0.6)
        await session.configure_idle(timeout_ms=0)


async def _open(brain: Brain) -> tuple[VoiceDriver, BrainServer]:
    keypair = generate_keypair()
    server = BrainServer(lambda: brain, host="127.0.0.1", port=0, public_keys=keypair.public_pem)
    port = await server.start()
    token = mint_pygato_token(
        private_key_pem=keypair.private_pem,
        session_id=SESSION_ID,
        agent_id="configure",
        tenant_id="demo",
    )
    driver = VoiceDriver(
        DirectConnection(f"ws://127.0.0.1:{port}", SESSION_ID, token=token),
        session_id=SESSION_ID,
        default_timeout=10.0,
    )
    await driver.open()
    return driver, server


def _spoken(turn) -> str:
    return "".join(text for unit in turn.units for text in unit.texts)


async def test_an_accepted_request_returns_and_the_turn_completes() -> None:
    driver, server = await _open(TuningBrain())
    try:
        await driver.start_session()
        turn = await driver.user_says("slow down a little")
    finally:
        await driver.aclose()
        await server.aclose()

    assert _spoken(turn) == "accepted"
    assert [f.thresholds for f in driver.requests if isinstance(f, ConfigureSttFrame)] == [
        {"eot_threshold": 0.75, "eot_timeout_ms": 4000}
    ]


async def test_a_refusal_raises_and_names_what_voice_said() -> None:
    driver, server = await _open(TuningBrain())
    driver.reject["configure_stt"] = "eot_threshold must be 0.0 to 1.0"
    try:
        await driver.start_session()
        turn = await driver.user_says("slow down a little")
    finally:
        await driver.aclose()
        await server.aclose()

    # Voice's own reason reaches the brain verbatim, and the turn still finishes:
    # a refused request is an answer, not a broken session.
    assert _spoken(turn) == "rejected configure_stt: eot_threshold must be 0.0 to 1.0"


async def test_an_unanswered_request_times_out_and_the_session_lives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("voqalize.sdk.brain.REQUEST_TIMEOUT_S", 0.3)
    driver, server = await _open(TuningBrain())
    driver.withhold.add("configure_stt")
    try:
        await driver.start_session()
        turn = await driver.user_says("slow down a little")
    finally:
        await driver.aclose()
        await server.aclose()

    # The state is genuinely unknown here, and the message says so rather than
    # implying the change was dropped.
    assert _spoken(turn).startswith("unanswered: configure_stt: Voice did not answer")
    assert "unknown" in _spoken(turn)


async def test_every_request_carries_its_own_id() -> None:
    driver, server = await _open(ThreeWayBrain())
    try:
        await driver.start_session()
        await driver.user_says("hi")
    finally:
        await driver.aclose()
        await server.aclose()

    assert [type(f) for f in driver.requests] == [
        ConfigureTtsFrame,
        ConfigureSttFrame,
        ConfigureIdleFrame,
        ConfigureSttFrame,
    ]
    # The id's whole job is to name the answer, so it is per session and never
    # reused — including across the greeting and the turn that follows it.
    assert [f.request_id for f in driver.requests] == [1, 2, 3, 4]
