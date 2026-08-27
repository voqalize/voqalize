"""``session.configure`` — one request out, exactly one answer back.

The method is awaitable, and what it waits for is Voqalize's *validation*:
accepted means Voqalize took the change whole, rejected means it applied none of
it. That is only useful if it holds from the place a brain actually retunes —
inside a turn, inside the hook that is itself being fed by the same socket the
answer arrives on. So these drive real sessions over a real websocket rather than
poking at the plumbing.

Three outcomes, and a brain has to survive all three: accepted, refused, and the
one the protocol cannot promise away — a Voqalize that stopped answering.

And one ordering, which is the whole reason a brain may configure at all from
:meth:`Brain.on_session_start`: the request reaches the wire *before* the first
word of the greeting. A configure that lands after the audio is worse than
useless — the caller has already heard the wrong voice say hello, in the wrong
recognizer's language. That is inaudible to automation: the transcript is
word-perfect, WER is unchanged, every other check passes, and only a native
speaker hears a foreigner reading their language. The frames are the only place
it shows.
"""

from __future__ import annotations

import pytest

from voqalize.conformance import (
    BrainServer,
    DirectConnection,
    VoqalizeDriver,
    generate_keypair,
    mint_voqalize_token,
)
from voqalize.sdk import Brain, Chunk, RequestRejected, SpeechEnd, SpeechStart
from voqalize.sdk.wire import (
    Config,
    ConfigureFrame,
    IdleConfig,
    Language,
    SpeechChunkFrame,
    SttConfig,
    TtsConfig,
    Voice,
)

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
            await session.configure(
                Config(
                    stt=SttConfig(language=Language.TA),
                    tts=TtsConfig(language=Language.TA),
                )
            )
            outcome = "accepted"
        except RequestRejected as exc:
            outcome = f"rejected {exc.op}: {exc.detail}"
        except TimeoutError as exc:
            outcome = f"unanswered: {exc}"
        yield SpeechStart()
        yield Chunk(outcome)
        yield SpeechEnd()


class TwiceBrain(TuningBrain):
    """Configures once before the greeting, and once more inside the turn."""

    async def on_session_start(self, session) -> None:
        await session.configure(
            Config(tts=TtsConfig(voice=Voice.OMNIVOICE_GAURAV), idle=IdleConfig(timeout_ms=0))
        )


async def _open(brain: Brain) -> tuple[VoqalizeDriver, BrainServer]:
    keypair = generate_keypair()
    server = BrainServer(lambda: brain, host="127.0.0.1", port=0, public_keys=keypair.public_pem)
    port = await server.start()
    token = mint_voqalize_token(
        private_key_pem=keypair.private_pem,
        session_id=SESSION_ID,
        agent_id="configure",
        tenant_id="demo",
    )
    driver = VoqalizeDriver(
        DirectConnection(f"ws://127.0.0.1:{port}", SESSION_ID, token=token),
        session_id=SESSION_ID,
        default_timeout=10.0,
    )
    await driver.open()
    return driver, server


def _spoken(turn) -> str:
    return "".join(text for unit in turn.units for text in unit.texts)


def _first_index(driver: VoqalizeDriver, frame_type) -> int | None:
    """Where a frame type first appears in the driver's own ordered log.

    Requests and speech ride the same lane, so their positions here are the
    positions the caller experienced.
    """
    for i, r in enumerate(driver.log):
        if isinstance(r.frame, frame_type):
            return i
    return None


async def test_an_accepted_request_returns_and_the_turn_completes() -> None:
    driver, server = await _open(TuningBrain())
    try:
        await driver.start_session()
        turn = await driver.user_says("switch to tamil")
    finally:
        await driver.aclose()
        await server.aclose()

    assert _spoken(turn) == "accepted"
    assert [f.config for f in driver.requests] == [
        Config(stt=SttConfig(language=Language.TA), tts=TtsConfig(language=Language.TA))
    ]


async def test_a_refusal_raises_and_names_what_voice_said() -> None:
    driver, server = await _open(TuningBrain())
    driver.reject["configure"] = "no recognizer for language 'ta'"
    try:
        await driver.start_session()
        turn = await driver.user_says("switch to tamil")
    finally:
        await driver.aclose()
        await server.aclose()

    # Voqalize's own reason reaches the brain verbatim, and the turn still finishes:
    # a refused request is an answer, not a broken session.
    assert _spoken(turn) == "rejected configure: no recognizer for language 'ta'"


async def test_an_unanswered_request_times_out_and_the_session_lives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("voqalize.sdk.brain.REQUEST_TIMEOUT_S", 0.3)
    driver, server = await _open(TuningBrain())
    driver.withhold.add("configure")
    try:
        await driver.start_session()
        turn = await driver.user_says("switch to tamil")
    finally:
        await driver.aclose()
        await server.aclose()

    # The state is genuinely unknown here, and the message says so rather than
    # implying the change was dropped.
    assert _spoken(turn).startswith("unanswered: configure: Voqalize did not answer")
    assert "unknown" in _spoken(turn)


async def test_every_request_carries_its_own_id() -> None:
    driver, server = await _open(TwiceBrain())
    try:
        await driver.start_session()
        await driver.user_says("switch to tamil")
    finally:
        await driver.aclose()
        await server.aclose()

    assert [type(f) for f in driver.requests] == [ConfigureFrame, ConfigureFrame]
    # The id's whole job is to name the answer, so it is per session and never
    # reused — including across the greeting and the turn that follows it.
    assert [f.request_id for f in driver.requests] == [1, 2]


async def test_a_session_start_request_lands_before_the_greeting() -> None:
    # `on_session_start` runs before `greet` — that ordering is the contract, and
    # since the voice a brain wants is now a configure call in that hook and
    # nothing else, this is the only thing standing between a brain and a
    # greeting spoken in the voice it was replacing.
    driver, server = await _open(TwiceBrain())
    try:
        await driver.start_session()
    finally:
        await driver.aclose()
        await server.aclose()

    greeting = _first_index(driver, SpeechChunkFrame)
    assert greeting is not None, "the brain must have greeted"
    configured = _first_index(driver, ConfigureFrame)
    assert configured is not None and configured < greeting, (
        "the request landed after the greeting audio — the caller already heard "
        "the wrong voice say hello"
    )


async def test_a_refusal_at_session_start_fails_the_session() -> None:
    # Voqalize has no engine for what this brain asked for, and the brain did not
    # catch it. It has stated what the call is; running it in some other voice is
    # a call nobody asked for — so there is no greeting and the session ends
    # fatally, rather than running to its end sounding wrong.
    driver, server = await _open(TwiceBrain())
    driver.reject["configure"] = "no voice 'omnivoice/gaurav'"
    try:
        await driver.start_session()
    finally:
        await driver.aclose()
        await server.aclose()

    assert _first_index(driver, SpeechChunkFrame) is None, "it must not have greeted"
    assert [(e.fatal, e.message) for e in driver.errors] == [
        (
            True,
            "on_session_start failed: configure rejected: no voice 'omnivoice/gaurav'",
        )
    ]


async def test_the_three_sections_travel_as_one_request() -> None:
    # The point of one op over three: a language change has to touch both legs,
    # and two requests would put a turn boundary — and a refusal — between the
    # halves, leaving the call heard in one language and spoken in another.
    driver, server = await _open(TwiceBrain())
    try:
        await driver.start_session()
        await driver.user_says("switch to tamil")
    finally:
        await driver.aclose()
        await server.aclose()

    assert driver.requests[0].config == Config(
        tts=TtsConfig(voice=Voice.OMNIVOICE_GAURAV), idle=IdleConfig(timeout_ms=0)
    )
    assert driver.requests[1].config == Config(
        stt=SttConfig(language=Language.TA), tts=TtsConfig(language=Language.TA)
    )
