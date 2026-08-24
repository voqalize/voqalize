"""``Brain.voice`` / ``Brain.language`` — the brain declares how it sounds.

The agent record carries the default; the brain overrides it for *this* caller.
They are a pair of class attributes the SDK applies at session start, ahead of
everything the brain itself runs.

These pin the three properties that make that trustworthy:

1. **It reaches the wire, ahead of the greeting.** A request that arrives after
   the first audio is worse than useless — the caller has already heard the wrong
   voice say hello. The request must precede the greeting text on the log, which
   is the same ordered lane the speech rides.
2. **It cannot be lost by a subclass.** The attributes are applied by the adapter
   on the way into ``on_session_start``, not by a base class's hook — so a brain
   that overrides that hook (every real one does) and forgets ``super()`` still
   gets its voice. ``HindiBrain`` below is exactly that brain.
3. **A refusal fails the session.** A brain that declared a language Voqalize will
   not serve has stated what the call is; running it in another one is a call
   nobody asked for.

Why the care: a wrong voice is inaudible to automation. The transcript is
word-perfect, WER is unchanged, every check passes — and a native speaker hears
a foreigner reading their language. The only defence is a test that watches the
frames.
"""

from __future__ import annotations

from voqalize.conformance import (
    BrainServer,
    DirectConnection,
    VoqalizeDriver,
    generate_keypair,
    mint_voqalize_token,
)
from voqalize.sdk import Brain, Chunk, SpeechEnd, SpeechStart
from voqalize.sdk.wire import (
    Config,
    ConfigureFrame,
    Language,
    SpeechChunkFrame,
    SttConfig,
    TtsConfig,
    Voice,
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
    """Declares nothing: the record's configuration must be left alone."""

    language = None
    voice = None


class OverridingBrain(HindiBrain):
    """Declares Hindi, then resolves a different language for *this* caller."""

    async def on_session_start(self, session) -> None:
        await session.configure(
            Config(
                stt=SttConfig(language=Language.TA),
                tts=TtsConfig(voice=Voice.OMNIVOICE_GAURI, language=Language.TA),
            )
        )
        await super().on_session_start(session)


async def _run(brain: Brain, *, reject: dict[str, str] | None = None) -> VoqalizeDriver:
    keypair = generate_keypair()
    server = BrainServer(
        lambda: brain,
        host="127.0.0.1",
        port=0,
        public_keys=keypair.public_pem,
    )
    port = await server.start()
    token = mint_voqalize_token(
        private_key_pem=keypair.private_pem,
        session_id=SESSION_ID,
        agent_id="declared-voice",
        tenant_id="demo",
    )
    driver = VoqalizeDriver(
        DirectConnection(f"ws://127.0.0.1:{port}", SESSION_ID, token=token),
        session_id=SESSION_ID,
        default_timeout=10.0,
    )
    driver.reject.update(reject or {})
    await driver.open()
    try:
        await driver.start_session()
        return driver
    finally:
        await driver.aclose()
        await server.aclose()


def _configs(driver: VoqalizeDriver) -> list[Config]:
    return [f.config for f in driver.requests if isinstance(f, ConfigureFrame)]


def _first_index(driver: VoqalizeDriver, frame_type) -> int | None:
    for i, r in enumerate(driver.log):
        if isinstance(r.frame, frame_type):
            return i
    return None


async def test_declared_language_configures_both_halves_before_the_greeting() -> None:
    driver = await _run(HindiBrain())

    # One request, both legs. The two-request version had a turn boundary and a
    # possible refusal between the halves; this one cannot land half-applied.
    assert _configs(driver) == [
        Config(
            stt=SttConfig(language=Language.HI),
            tts=TtsConfig(voice=Voice.OMNIVOICE_GAURI, language=Language.HI),
        )
    ]

    greeting = _first_index(driver, SpeechChunkFrame)
    assert greeting is not None, "the brain must have greeted"
    configured = _first_index(driver, ConfigureFrame)
    assert configured is not None and configured < greeting, (
        "the declaration landed after the greeting audio — the caller already "
        "heard the wrong voice say hello, in the wrong recognizer's language"
    )


async def test_voice_without_language_leaves_the_recognizer_alone() -> None:
    driver = await _run(VoiceOnlyBrain())
    # Changing which of two voices speaks is not a language change; naming a
    # language here would re-point the recognizer for no reason.
    assert _configs(driver) == [Config(tts=TtsConfig(voice=Voice.OMNIVOICE_GAURAV))]


async def test_declaring_nothing_emits_nothing() -> None:
    # Guard-the-guard: without the declaration there are no requests at all, so
    # the assertions above are reading the attributes and not some unrelated frame
    # the runtime always sends.
    driver = await _run(PlainBrain())
    assert driver.requests == []


async def test_on_session_start_can_override_the_declaration() -> None:
    # The per-caller escape hatch: a brain that resolves the language from this
    # session's init data speaks last, and both still precede the greeting.
    driver = await _run(OverridingBrain())
    assert [c.tts.language for c in _configs(driver)] == [Language.HI, Language.TA], (
        "the declaration must be applied first and the per-call override second, "
        "so the override wins"
    )
    greeting = _first_index(driver, SpeechChunkFrame)
    assert greeting is not None
    last = max(i for i, r in enumerate(driver.log) if isinstance(r.frame, ConfigureFrame))
    assert last < greeting


async def test_a_refused_declaration_fails_the_session() -> None:
    # Voqalize has no engine for the declared language. The brain asked for a call it
    # cannot have, so there is no greeting and the session ends fatally — rather
    # than a call that runs to its end in a language nobody chose.
    driver = await _run(HindiBrain(), reject={"configure": "no recognizer for language 'hi'"})

    assert len(_configs(driver)) == 1
    assert _first_index(driver, SpeechChunkFrame) is None, "it must not have greeted"
    assert [(e.fatal, e.message) for e in driver.errors] == [
        (True, "voice failed: configure rejected: no recognizer for language 'hi'")
    ]
