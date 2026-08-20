"""``Brain.voice`` / ``Brain.language`` — the brain declares how it sounds.

An agent's voice and language used to live on the agent record in the control
plane. They don't any more: the record holds one value for every caller, and the
brain is the only thing that knows *this* one. What replaces it is a pair of
class attributes the SDK applies at session start.

These pin the two properties that make the replacement trustworthy:

1. **It reaches the wire, ahead of the greeting.** A settings frame that arrives
   after the first audio is worse than useless — the caller has already heard the
   wrong voice say hello. The applied frames must precede the greeting text on
   the log, which is the same ordered lane the speech rides.
2. **It cannot be lost by a subclass.** The attributes are applied by the adapter
   on the way into ``on_session_start``, not by a base class's hook — so a brain
   that overrides that hook (every real one does) and forgets ``super()`` still
   gets its voice. ``ForgetfulBrain`` below is exactly that brain.

Why the care: a wrong voice is inaudible to automation. The transcript is
word-perfect, WER is unchanged, every check passes — and a native speaker hears
a foreigner reading their language. The only defence is a test that watches the
frames.
"""

from __future__ import annotations

from voqalize.conformance import (
    DirectConnection,
    VoiceDriver,
    generate_keypair,
    mint_pygato_token,
)
from voqalize.sdk import Brain, Chunk, DirectAgent, SpeechEnd, SpeechStart, brain_factory
from voqalize.sdk.wire import (
    LLMTextFrame,
    UpdateSTTSettingsFrame,
    UpdateTTSSettingsFrame,
)

SESSION_ID = "declared-voice-test"


class HindiBrain(Brain):
    """Declares both halves and overrides ``on_session_start`` without ``super()``."""

    language = "hi"
    voice = "omnivoice/gauri"

    async def on_session_start(self, session) -> None:
        self.started = True

    async def greet(self, session) -> str:
        return "नमस्ते!"

    async def on_user_message(self, session, msg):
        yield SpeechStart()
        yield Chunk("ठीक है।")
        yield SpeechEnd()


class VoiceOnlyBrain(HindiBrain):
    """A different voice, same (default) language — must not touch the recognizer."""

    language = None
    voice = "omnivoice/gaurav"


class PlainBrain(HindiBrain):
    """Declares nothing: the platform default must be left alone."""

    language = None
    voice = None


class OverridingBrain(HindiBrain):
    """Declares Hindi, then resolves a different language for *this* caller."""

    async def on_session_start(self, session) -> None:
        session.configure_language("ta", voice="omnivoice/gauri")
        await super().on_session_start(session)


async def _run(brain: Brain) -> list:
    keypair = generate_keypair()
    agent = DirectAgent(
        factory=brain_factory(lambda: brain),
        host="127.0.0.1",
        port=0,
        public_keys=keypair.public_pem,
    )
    port = await agent.start()
    token = mint_pygato_token(
        private_key_pem=keypair.private_pem,
        session_id=SESSION_ID,
        agent_id="declared-voice",
        tenant_id="demo",
    )
    driver = VoiceDriver(
        DirectConnection(f"ws://127.0.0.1:{port}", SESSION_ID, token=token),
        session_id=SESSION_ID,
        agent_id="declared-voice",
        default_timeout=10.0,
    )
    await driver.open()
    try:
        await driver.start_session()
        return list(driver.log)
    finally:
        await driver.aclose()
        await agent.aclose()


def _settings(log, frame_type) -> list[dict]:
    return [dict(r.frame.settings) for r in log if isinstance(r.frame, frame_type)]


def _first_index(log, frame_type) -> int | None:
    for i, r in enumerate(log):
        if isinstance(r.frame, frame_type):
            return i
    return None


async def test_declared_language_configures_both_halves_before_the_greeting() -> None:
    log = await _run(HindiBrain())

    assert _settings(log, UpdateTTSSettingsFrame) == [
        {"voice": "omnivoice/gauri", "language": "hi"}
    ]
    assert _settings(log, UpdateSTTSettingsFrame) == [{"language_hint": "hi"}]

    greeting = _first_index(log, LLMTextFrame)
    assert greeting is not None, "the brain must have greeted"
    tts_at = _first_index(log, UpdateTTSSettingsFrame)
    stt_at = _first_index(log, UpdateSTTSettingsFrame)
    assert tts_at is not None and tts_at < greeting, (
        "the declared voice landed after the greeting audio — the caller already "
        "heard the wrong voice say hello"
    )
    assert stt_at is not None and stt_at < greeting, (
        "the declared recognizer landed after the greeting — the caller's first "
        "reply would be transcribed by the wrong recognizer"
    )


async def test_voice_without_language_leaves_the_recognizer_alone() -> None:
    log = await _run(VoiceOnlyBrain())
    assert _settings(log, UpdateTTSSettingsFrame) == [{"voice": "omnivoice/gaurav"}]
    # Changing which of two English voices speaks is not a language change; sending
    # a language_hint here would re-point the recognizer for no reason.
    assert _settings(log, UpdateSTTSettingsFrame) == []


async def test_declaring_nothing_emits_nothing() -> None:
    # Guard-the-guard: without the declaration there are no settings frames at
    # all, so the assertions above are reading the attributes and not some
    # unrelated frame the runtime always sends.
    log = await _run(PlainBrain())
    assert _settings(log, UpdateTTSSettingsFrame) == []
    assert _settings(log, UpdateSTTSettingsFrame) == []


async def test_on_session_start_can_override_the_declaration() -> None:
    # The per-caller escape hatch: a brain that resolves the language from this
    # session's payload speaks last, and both still precede the greeting.
    log = await _run(OverridingBrain())
    tts = _settings(log, UpdateTTSSettingsFrame)
    assert [s["language"] for s in tts] == ["hi", "ta"], (
        "the declaration must be applied first and the per-call override second, "
        "so the override wins"
    )
    greeting = _first_index(log, LLMTextFrame)
    assert greeting is not None
    last_tts = max(i for i, r in enumerate(log) if isinstance(r.frame, UpdateTTSSettingsFrame))
    assert last_tts < greeting
