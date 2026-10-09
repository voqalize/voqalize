"""``session.cancel_speech`` — a brain takes its own speech back.

The call names one unit by the id the SDK wrote onto its ``SpeechStart``, and
what it waits for is that unit's ``Finalize``: Voqalize sends no acknowledgement,
because the Finalize it already owes every unit is the answer. So these drive
real sessions over a real websocket, with the conformance driver honouring the
cancel the way Voqalize does, rather than poking at the plumbing.

What a guardrail needs from it, and what each test pins:

- the answer is the unit's own Finalize, and ``on_finalize`` still sees it;
- a cancel of an earlier unit that is still playing also closes the unit
  being streamed after it — the cut is the whole floor — and the generator's
  further yields for that one are dropped too, not a crash;
- a cancel that lost the race to playout, or a second cancel, answers from
  memory and sends nothing;
- what the generator yields for the unit afterwards never reaches the wire, and
  the turn stays open for a new unit;
- the three refusals happen before anything is sent — a Voqalize that did not
  advertise the capability, an id this session never minted, an id not minted
  *yet* — and the one outcome that cannot be refused up front, a Voqalize that
  never answers, is a timeout and not a hang, after which the unit is still
  the brain's to close.
"""

from __future__ import annotations

import asyncio

import pytest

from voqalize.conformance import (
    BrainServer,
    DirectConnection,
    VoqalizeDriver,
    generate_keypair,
    mint_voqalize_token,
)
from voqalize.sdk import (
    Brain,
    Finalize,
    SpeechChunk,
    SpeechEnd,
    SpeechStart,
    Unsupported,
)
from voqalize.sdk.wire import (
    Capability,
    SpeechCancelFrame,
    SpeechChunkFrame,
    SpeechEndFrame,
)

SESSION_ID = "cancel-speech-test"

OPENING = "Good question. "
FLAGGED = "The answer is 42. "
TAIL = "NEVER_ON_THE_WIRE"
CORRECTION = "Let's think about it differently."


class GuardrailBrain(Brain):
    """Cancels what it said, by script, and says what came back.

    The verb is the user's message, so one brain covers every path and each
    test reads as one exchange.
    """

    def __init__(self) -> None:
        self.starts: list[SpeechStart] = []
        self.results: list[Finalize] = []
        self.finalized: list[Finalize] = []
        self.finalize_seen = asyncio.Condition()

    async def greet(self, session) -> str:
        return "hello"

    async def on_user_message(self, session, msg):
        verb, _, arg = msg.text.partition(" ")

        if verb in ("flag", "flag-twice", "flag-unanswered"):
            start = SpeechStart()
            self.starts.append(start)
            yield start
            yield SpeechChunk(OPENING)
            yield SpeechChunk(FLAGGED)
            try:
                self.results.append(await session.cancel_speech(start.speech_id))
                if verb == "flag-twice":
                    self.results.append(await session.cancel_speech(start.speech_id))
            except TimeoutError as exc:
                # Not closed by the cancel, so closed here, as any unit is.
                yield SpeechEnd()
                yield SpeechStart()
                yield SpeechChunk(f"unanswered: {exc}")
                yield SpeechEnd()
                return
            # The model has not noticed yet; the SDK must drop all of this.
            yield SpeechChunk(TAIL)
            yield SpeechEnd()
            yield SpeechStart()
            yield SpeechChunk(CORRECTION)
            yield SpeechEnd()
            return

        if verb == "guard-unanswered":
            # The guardrail runs in a task of its own and the model finishes the
            # unit while the cancel is still waiting for its answer.
            start = SpeechStart()
            self.starts.append(start)
            yield start
            yield SpeechChunk(FLAGGED)
            guard = asyncio.create_task(session.cancel_speech(start.speech_id))
            await asyncio.sleep(0)
            yield SpeechEnd()
            try:
                await guard
            except TimeoutError as exc:
                yield SpeechStart()
                yield SpeechChunk(f"unanswered: {exc}")
                yield SpeechEnd()
            return

        if verb == "lag":
            # The guardrail is a sentence behind the model: it flags the first
            # unit while the second is already streaming.
            first = SpeechStart()
            self.starts.append(first)
            yield first
            yield SpeechChunk(OPENING)
            yield SpeechEnd()
            second = SpeechStart()
            self.starts.append(second)
            yield second
            yield SpeechChunk(FLAGGED)
            self.results.append(await session.cancel_speech(first.speech_id))
            # Wait until the cut has reached the second unit too, so what
            # follows is yielded into a unit Voqalize has already finalized.
            async with self.finalize_seen:
                await self.finalize_seen.wait_for(
                    lambda: any(f.speech_id == second.speech_id for f in self.finalized)
                )
            yield SpeechChunk(TAIL)
            yield SpeechEnd()
            yield SpeechStart()
            yield SpeechChunk(CORRECTION)
            yield SpeechEnd()
            return

        if verb == "say":
            start = SpeechStart()
            self.starts.append(start)
            yield start
            yield SpeechChunk(arg)
            yield SpeechEnd()
            return

        if verb == "late":
            self.results.append(await session.cancel_speech(int(arg)))
            yield SpeechStart()
            yield SpeechChunk("late")
            yield SpeechEnd()
            return

        try:
            if verb == "unknown":
                await session.cancel_speech(999)
            elif verb == "unminted":
                await session.cancel_speech(SpeechStart().speech_id)
            outcome = "no error"
        except Unsupported as exc:
            outcome = f"unsupported {exc.capability.value}"
        except ValueError as exc:
            outcome = f"ValueError: {exc}"
        yield SpeechStart()
        yield SpeechChunk(outcome)
        yield SpeechEnd()

    async def on_finalize(self, session, fin: Finalize) -> None:
        async with self.finalize_seen:
            self.finalized.append(fin)
            self.finalize_seen.notify_all()


async def _open(brain: Brain) -> tuple[VoqalizeDriver, BrainServer]:
    keypair = generate_keypair()
    server = BrainServer(lambda: brain, host="127.0.0.1", port=0, public_keys=keypair.public_pem)
    port = await server.start()
    token = mint_voqalize_token(
        private_key_pem=keypair.private_pem,
        session_id=SESSION_ID,
        agent_id="cancel",
        tenant_id="demo",
    )
    driver = VoqalizeDriver(
        DirectConnection(f"ws://127.0.0.1:{port}", SESSION_ID, token=token),
        session_id=SESSION_ID,
        default_timeout=5.0,
    )
    # A cut mid-playout: the user heard the opening and not the flagged text.
    driver.heard_on_cancel = lambda unit: unit.texts[0] if unit.texts else ""
    await driver.open()
    return driver, server


def _spoken(turn) -> str:
    return "".join(text for unit in turn.units for text in unit.texts)


def _frames_for(driver: VoqalizeDriver, speech_id: int, frame_type) -> list:
    return [
        r.frame
        for r in driver.log
        if isinstance(r.frame, frame_type) and r.frame.speech_id == speech_id
    ]


async def test_cancel_returns_the_units_finalize_and_on_finalize_still_fires() -> None:
    brain = GuardrailBrain()
    driver, server = await _open(brain)
    try:
        await driver.start_session()
        turn = await driver.user_says("flag")
    finally:
        await driver.aclose()
        await server.aclose()

    speech_id = brain.starts[0].speech_id
    assert speech_id is not None, "the SDK writes the minted id onto the SpeechStart"
    expected = Finalize(speech_id=speech_id, heard=OPENING, generated=OPENING + FLAGGED)
    assert brain.results == [expected]
    assert expected.interrupted
    # One Finalize per unit, and the hook sees the same one the call returned.
    assert [f for f in brain.finalized if f.speech_id == speech_id] == [expected]
    # The turn stayed open: the correction went out on it and was heard in full.
    assert [unit.text for unit in turn.units] == [OPENING + FLAGGED, CORRECTION]
    assert turn.completed


async def test_nothing_the_generator_yields_after_the_cancel_reaches_the_wire() -> None:
    brain = GuardrailBrain()
    driver, server = await _open(brain)
    try:
        await driver.start_session()
        await driver.user_says("flag")
    finally:
        await driver.aclose()
        await server.aclose()

    speech_id = brain.starts[0].speech_id
    assert speech_id is not None
    assert [f.speech_id for f in driver.cancels] == [speech_id]
    # The cancel closed the unit, so its SpeechEnd is not sent, and neither is
    # anything chunked after it.
    assert _frames_for(driver, speech_id, SpeechEndFrame) == []
    assert TAIL not in "".join(f.text for f in _frames_for(driver, speech_id, SpeechChunkFrame))


async def test_cancelling_an_earlier_unit_also_closes_the_one_still_streaming() -> None:
    brain = GuardrailBrain()
    driver, server = await _open(brain)
    try:
        await driver.start_session()
        turn = await driver.user_says("lag")
    finally:
        await driver.aclose()
        await server.aclose()

    first, second = (start.speech_id for start in brain.starts)
    assert first is not None and second is not None
    assert brain.results == [Finalize(speech_id=first, heard=OPENING, generated=OPENING)]
    # The second unit was inside the cut: finalized unheard, with what had gone
    # out for it, and nothing the generator yielded afterwards reached the wire.
    assert [f for f in brain.finalized if f.speech_id == second] == [
        Finalize(speech_id=second, heard="", generated=FLAGGED)
    ]
    assert _frames_for(driver, second, SpeechEndFrame) == []
    assert TAIL not in "".join(f.text for f in _frames_for(driver, second, SpeechChunkFrame))
    # And the turn went on: the correction is a unit of its own, heard in full.
    assert [unit.text for unit in turn.units] == [OPENING, FLAGGED, CORRECTION]
    assert turn.completed


async def test_a_second_cancel_answers_from_memory_and_sends_nothing() -> None:
    brain = GuardrailBrain()
    driver, server = await _open(brain)
    try:
        await driver.start_session()
        await driver.user_says("flag-twice")
    finally:
        await driver.aclose()
        await server.aclose()

    assert len(brain.results) == 2 and brain.results[0] == brain.results[1]
    assert len([r for r in driver.log if isinstance(r.frame, SpeechCancelFrame)]) == 1


async def test_a_cancel_after_playout_returns_the_finalize_already_sent() -> None:
    brain = GuardrailBrain()
    driver, server = await _open(brain)
    try:
        await driver.start_session()
        await driver.user_says("say all of it")
        played = brain.starts[0].speech_id
        turn = await driver.user_says(f"late {played}")
    finally:
        await driver.aclose()
        await server.aclose()

    assert played is not None
    # Too late to cut anything: the answer is what it already finalized with, in
    # full, and no SpeechCancel was spent finding that out.
    assert brain.results == [Finalize(speech_id=played, heard="all of it", generated="all of it")]
    assert not brain.results[0].interrupted
    assert driver.cancels == []
    assert _spoken(turn) == "late"


async def test_an_id_this_session_never_opened_is_refused_locally() -> None:
    driver, server = await _open(GuardrailBrain())
    try:
        await driver.start_session()
        turn = await driver.user_says("unknown")
    finally:
        await driver.aclose()
        await server.aclose()

    assert _spoken(turn) == "ValueError: cancel_speech: speech 999 was never opened by this session"
    assert driver.cancels == []


async def test_a_speech_start_not_yet_yielded_has_no_id() -> None:
    driver, server = await _open(GuardrailBrain())
    try:
        await driver.start_session()
        turn = await driver.user_says("unminted")
    finally:
        await driver.aclose()
        await server.aclose()

    assert _spoken(turn).startswith("ValueError: cancel_speech: this SpeechStart has no speech_id")
    assert driver.cancels == []


async def test_a_voqalize_without_the_capability_is_refused_before_sending() -> None:
    driver, server = await _open(GuardrailBrain())
    driver.capabilities.clear()
    try:
        await driver.start_session()
        turn = await driver.user_says("unknown")
    finally:
        await driver.aclose()
        await server.aclose()

    # Refused before the id is even looked at: the capability is the first gate,
    # because a frame this Voqalize does not know would be skipped, not refused.
    assert _spoken(turn) == f"unsupported {Capability.SPEECH_CANCEL.value}"
    assert driver.cancels == []


async def test_an_unanswered_cancel_times_out_and_the_turn_goes_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("voqalize.sdk.brain.REQUEST_TIMEOUT_S", 0.3)
    driver, server = await _open(GuardrailBrain())
    try:
        await driver.start_session()
        # Advertised at SessionStart, then not honoured: the cancel is skipped
        # and no Finalize comes back for it.
        driver.capabilities.clear()
        turn = await driver.user_says("flag-unanswered", timeout=1.5)
    finally:
        await driver.aclose()
        await server.aclose()

    assert len(driver.cancels) == 1
    # Unanswered means not closed, so the generator's SpeechEnd for the unit
    # went out and the bracket closed on the wire, not just in the SDK.
    cut = turn.units[0]
    assert cut.ended and not cut.cancelled
    assert len(_frames_for(driver, cut.speech_id, SpeechEndFrame)) == 1
    assert turn.units[-1].text.startswith("unanswered: cancel_speech: Voqalize did not finalize")
    assert turn.completed


async def test_an_end_held_back_for_an_unanswered_cancel_is_sent_after_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The generator's SpeechEnd arrived while the cancel was pending, so it was
    # held back as the cancel's to close. Unanswered, the cancel closed nothing,
    # and that SpeechEnd is now the only thing that can close the bracket.
    monkeypatch.setattr("voqalize.sdk.brain.REQUEST_TIMEOUT_S", 0.3)
    driver, server = await _open(GuardrailBrain())
    try:
        await driver.start_session()
        driver.capabilities.clear()
        turn = await driver.user_says("guard-unanswered", timeout=1.5)
    finally:
        await driver.aclose()
        await server.aclose()

    cut = turn.units[0]
    assert cut.ended and not cut.cancelled
    assert len(_frames_for(driver, cut.speech_id, SpeechEndFrame)) == 1
    assert turn.units[-1].text.startswith("unanswered: cancel_speech: Voqalize did not finalize")
    assert turn.completed


def test_speech_start_equality_ignores_the_minted_id() -> None:
    # The id is written onto the object the brain yielded; it must not change
    # what a SpeechStart *is*, or `==` and hashing would turn on an SDK detail.
    minted = SpeechStart()
    object.__setattr__(minted, "speech_id", 7)
    assert minted == SpeechStart()
    assert hash(minted) == hash(SpeechStart())
    with pytest.raises(TypeError):
        SpeechStart(speech_id=7)  # type: ignore[call-arg]
