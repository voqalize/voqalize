"""The shared per-demo e2e rig: one real demo brain on a real socket, driven by
the conformance ``VoiceDriver``, with only the *model* scripted.

``test_travel_adk.py`` established this shape for the one ADK demo; every other
demo is a ``GeminiBrain``, so the only difference is which fake model goes in
(:class:`voqalize_demos.testing.ScriptedGemini` instead of ADK's ``ScriptedLlm``).
Everything else — the ``brain_server`` WebSocket, the minted PyGato token, the
driver's playout/heard-truth model — is identical, which is the point: these tests
exercise the same wire a production session runs on.

What every demo's e2e must prove, and why each one is here:

* **it greets** — on interaction 0, with every bracket it opened closed. The
  liveness floor.
* **its voice and language reach the wire, as a pair** — see :func:`check_voice_pair`.
  This is the check that would have caught the OrderDesk Hindi-in-an-English-voice
  bug, and the invalid ``stt.model`` that took prod down: neither is visible in a
  transcript, so no amount of conversational assertion finds them.
* **a tool round-trip drives the screen** — two inference brackets for one user
  turn, and the exact ``ui_command`` payload the demo's frontend reads.

Demos are built through :func:`voqalize_demos.discovery.build_for`, the same
factory the umbrella app mounts, so a test never re-wires a demo by hand.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

from voqalize_demos.discovery import build_for
from voqalize_demos.testing import ScriptedGemini

from voqalize.conformance import (
    BrainServer,
    DirectConnection,
    VoiceDriver,
    checks,
    generate_keypair,
    mint_pygato_token,
)
from voqalize.sdk import Brain

# The whole TTS catalog (``docs/reference/catalog.md``). A voice outside it is
# rejected by vql-speech at connect — which is how two fossil agent records took
# production down: the values named engines deleted a release earlier, and nothing
# between the record and the wire had an opinion.
VOICES = frozenset({"omnivoice/gauri", "omnivoice/gaurav"})

# What ``vql-stt`` serves: English plus the 22 Indic languages. Anything else
# silently falls back to the English recognizer.
LANGUAGES = frozenset(
    {
        "en",
        "as",
        "bn",
        "brx",
        "doi",
        "gu",
        "hi",
        "kn",
        "kok",
        "ks",
        "mai",
        "ml",
        "mni",
        "mr",
        "ne",
        "or",
        "pa",
        "sa",
        "sat",
        "sd",
        "ta",
        "te",
        "ur",
    }
)


@dataclass
class DemoRig:
    """One hosted demo session: the brain under test, its socket, and the driver."""

    name: str
    server: BrainServer
    driver: VoiceDriver
    _built: list[Brain]

    @property
    def brain(self) -> Brain:
        """The brain serving this session.

        The server builds it on connect — *after* the rig is handed to the
        test — so a read before ``driver.start_session()`` is a test bug, and says
        so rather than returning ``None``."""
        if not self._built:
            raise AssertionError(
                f"{self.name}: the brain does not exist until the session opens — "
                "call driver.start_session() before reading rig.brain"
            )
        return self._built[-1]

    def actions(self) -> list[str]:
        """The ``ui_command`` actions the brain fired, minus the conformance
        backchannel (``__``-prefixed, used by ``dump_conversation``)."""
        return [
            str(c.get("action"))
            for c in self.driver.ui_commands
            if not str(c.get("action", "")).startswith("__")
        ]

    def command(self, action: str) -> dict[str, Any]:
        """The first ``ui_command`` for ``action`` — the payload the demo's frontend
        store receives. Raises if the brain never fired it."""
        for c in self.driver.ui_commands:
            if c.get("action") == action:
                return dict(c)
        raise AssertionError(f"{self.name}: no ui_command {action!r} — fired: {self.actions()}")


@contextlib.asynccontextmanager
async def demo(name: str, llm: ScriptedGemini) -> AsyncIterator[DemoRig]:
    """Host demo ``name``'s real brain (scripted model) on localhost and open a
    PyGato-side driver against it. Tears both down on the way out.

    The brain comes from :func:`build_for` — the same factory the umbrella mounts —
    so a test never re-wires a demo by hand. The two ADK demos (``travel``,
    ``orderdesk``) build their own model from the environment and ignore the
    injected provider; host those with :func:`demo_from` and an ADK ``ScriptedLlm``."""
    build = build_for(name)
    async with demo_from(name, lambda: build(llm)) as rig:  # type: ignore[arg-type]
        yield rig


@contextlib.asynccontextmanager
async def demo_from(name: str, build: Callable[[], Brain]) -> AsyncIterator[DemoRig]:
    """:func:`demo` with the brain construction spelled out — for a demo whose model
    is not the injected ``GeminiProvider``."""
    keypair = generate_keypair()
    built: list[Brain] = []

    def _build() -> Brain:
        brain = build()
        built.append(brain)
        return brain

    server = BrainServer(
        _build,
        host="127.0.0.1",
        port=0,
        public_keys=keypair.public_pem,
    )
    port = await server.start()
    session_id = f"{name}-e2e"
    driver = VoiceDriver(
        DirectConnection(
            f"ws://127.0.0.1:{port}",
            session_id,
            token=mint_pygato_token(
                private_key_pem=keypair.private_pem,
                session_id=session_id,
                agent_id=name,
                tenant_id="demo",
            ),
        ),
        session_id=session_id,
        agent_id=name,
        default_timeout=10.0,
    )
    await driver.open()
    try:
        yield DemoRig(name=name, server=server, driver=driver, _built=built)
    finally:
        await driver.aclose()
        await server.aclose()


# ─── The checks every demo shares ─────────────────────────────────────────────


def check_voice_pair(rig: DemoRig, *, voice: str, language: str) -> None:
    """Both halves of the language reached the wire, agreeing, before the greeting.

    ``language`` sets the recognizer **and** the voice-cloning reference clip, and
    the two are named differently on the two legs (TTS ``language``, STT
    ``language_hint``). Half-applying it is silent: the words stay right and only
    the speaker is wrong, so WER, logs and every automated score are blind to it —
    which is exactly how a demo shipped Devanagari read in an English voice for
    weeks. The only place it is visible is here, on the frames themselves."""
    driver = rig.driver
    checks.require(
        bool(driver.tts_settings),
        f"{rig.name}: no TTSUpdateSettings on the wire — the brain declared no voice "
        "and set none, so the session runs on whatever the platform default happens "
        "to be",
    )
    checks.require(
        bool(driver.stt_settings),
        f"{rig.name}: no STTUpdateSettings on the wire — the recognizer never got a "
        "language hint, so the caller is transcribed as English",
    )
    tts = driver.tts_settings[-1]
    stt = driver.stt_settings[-1]
    checks.require(
        tts.get("voice") == voice,
        f"{rig.name}: TTS voice is {tts.get('voice')!r}, expected {voice!r}",
    )
    checks.require(
        tts.get("language") == language,
        f"{rig.name}: TTS language is {tts.get('language')!r}, expected {language!r} — "
        "the reference clip, i.e. which recorded speaker reads the text",
    )
    checks.require(
        stt.get("language_hint") == language,
        f"{rig.name}: STT language_hint is {stt.get('language_hint')!r}, expected "
        f"{language!r} — the two halves have drifted apart",
    )
    check_catalog(rig)


def check_catalog(rig: DemoRig) -> None:
    """Every voice/language the brain ever put on the wire is one vql-speech serves.

    A value outside the catalog is not a soft failure: an unknown voice prefix is
    rejected at connect (``voice not found``), and an unknown ``?model=`` is an
    HTTP 403 before a single frame flows. Both have happened in production, from
    values that were valid when they were written and were never revisited."""
    for tts in rig.driver.tts_settings:
        voice = tts.get("voice")
        if voice is not None:
            checks.require(
                voice in VOICES,
                f"{rig.name}: voice {voice!r} is not in the catalog {sorted(VOICES)} — "
                "vql-speech rejects it at connect",
            )
        language = tts.get("language")
        if language is not None:
            checks.require(
                language in LANGUAGES,
                f"{rig.name}: TTS language {language!r} is not served by vql-stt",
            )
        model = tts.get("model")
        checks.require(
            model is None or model == "sonic-2",
            f"{rig.name}: TTS model {model!r} — the engine is chosen by the voice "
            "prefix; naming a deleted engine here is how prod broke",
        )
    for stt in rig.driver.stt_settings:
        hint = stt.get("language_hint")
        if hint is not None:
            checks.require(
                hint in LANGUAGES,
                f"{rig.name}: STT language_hint {hint!r} is not served by vql-stt",
            )
        model = stt.get("model")
        checks.require(
            model in (None, "vql-stt", "flux-general-en", "flux-general-multi"),
            f"{rig.name}: STT model {model!r} is rejected by vql-speech with HTTP 403",
        )


def check_greeting(rig: DemoRig, turn: Any) -> None:
    """The demo greeted, on interaction 0, with closed brackets."""
    checks.check_greeting(rig.driver, turn)
    checks.require(
        bool(turn is not None and turn.text.strip()),
        f"{rig.name}: greeted with no text — the caller hears dead air on connect",
    )


def check_turn(rig: DemoRig, turn: Any, *, inferences: int | None = None) -> None:
    """A clean user turn: it spoke, every bracket closed, ids are monotone, and the
    interaction completed (without which Voice stays muted for the rest of the call)."""
    checks.check_brackets_closed(turn)
    checks.check_inference_ids_monotonic(turn)
    checks.check_completed(turn)
    checks.check_spoke(turn)
    if inferences is not None:
        checks.require(
            len(turn.inferences) == inferences,
            f"{rig.name}: expected {inferences} inference bracket(s), got "
            f"{len(turn.inferences)}: {[i.text for i in turn.inferences]}",
        )
