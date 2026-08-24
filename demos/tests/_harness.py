"""The shared per-demo e2e rig: one real demo brain on a real socket, driven by
the conformance ``VoqalizeDriver``, with only the *model* scripted.

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
    VoqalizeDriver,
    checks,
    generate_keypair,
    mint_voqalize_token,
)
from voqalize.sdk import Brain
from voqalize.sdk.wire import SPEAKABLE, Config, ConfigureFrame, Language

# There is no catalog constant here any more. ``Voice`` and ``Language`` are
# protobuf enums, so a value vql-speech does not serve cannot be constructed,
# let alone put on the wire — which is what used to take production down, from
# fossil agent records naming engines deleted a release earlier. What is left
# to check is that the demo configured at all, and configured the pair it meant
# to.


@dataclass
class DemoRig:
    """One hosted demo session: the brain under test, its socket, and the driver."""

    name: str
    server: BrainServer
    driver: VoqalizeDriver
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
        """The ``ui-command`` names the brain fired, minus the conformance
        backchannel (``__``-prefixed, used by ``dump_conversation``)."""
        return [
            str(c.get("command"))
            for c in self.driver.ui_commands
            if not str(c.get("command", "")).startswith("__")
        ]

    def command(self, action: str) -> dict[str, Any]:
        """The payload of the first ``ui-command`` named ``action`` — what the
        demo's frontend store receives. Raises if the brain never fired it."""
        for c in self.driver.ui_commands:
            if c.get("command") == action:
                return dict(c.get("payload") or {})
        raise AssertionError(f"{self.name}: no ui-command {action!r} — fired: {self.actions()}")


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
    driver = VoqalizeDriver(
        DirectConnection(
            f"ws://127.0.0.1:{port}",
            session_id,
            token=mint_voqalize_token(
                private_key_pem=keypair.private_pem,
                session_id=session_id,
                agent_id=name,
                tenant_id="demo",
            ),
        ),
        session_id=session_id,
        default_timeout=10.0,
    )
    await driver.open()
    try:
        yield DemoRig(name=name, server=server, driver=driver, _built=built)
    finally:
        await driver.aclose()
        await server.aclose()


# ─── The checks every demo shares ─────────────────────────────────────────────


def _configs(rig: DemoRig) -> list[Config]:
    """Every configuration the brain put on the wire, in order."""
    return [r.config for r in rig.driver.requests if isinstance(r, ConfigureFrame)]


def _last(configs: list[Config], read: Callable[[Config], Any]) -> Any:
    """The last value any request actually set for one field.

    Requests are deltas, so the session's state is the newest *stated* value —
    a later request that left a section out did not reset it."""
    for config in reversed(configs):
        value = read(config)
        if value is not None:
            return value
    return None


def check_voice_pair(rig: DemoRig, *, voice: str, language: str) -> None:
    """Both halves of the language reached the wire, as one request, before the
    greeting.

    ``language`` sets the recognizer **and** the voice-cloning reference clip.
    Half-applying it is silent: the words stay right and only the speaker is
    wrong, so WER, logs and every automated score are blind to it — which is
    exactly how a demo shipped Devanagari read in an English voice for weeks. The
    only place it is visible is here, on the frames themselves.

    The SDK now refuses to build a half-stated ``Config`` at all, so this is no
    longer the last line of defence. It is still the only check that the pair the
    demo chose is the pair it meant."""
    configs = _configs(rig)
    checks.require(
        bool(configs),
        f"{rig.name}: nothing configured on the wire — the brain declared no voice "
        "and set none, so the session runs on whatever the record's default happens "
        "to be",
    )
    got_voice = _last(configs, lambda c: c.tts.voice if c.tts else None)
    got_spoken = _last(configs, lambda c: c.tts.language if c.tts else None)
    got_heard = _last(configs, lambda c: c.stt.language if c.stt else None)
    checks.require(
        got_voice == voice,
        f"{rig.name}: TTS voice is {got_voice!r}, expected {voice!r}",
    )
    checks.require(
        got_spoken == language,
        f"{rig.name}: TTS language is {got_spoken!r}, expected {language!r} — "
        "the reference clip, i.e. which recorded speaker reads the text",
    )
    checks.require(
        got_heard == language,
        f"{rig.name}: STT language is {got_heard!r}, expected {language!r} — "
        "the two halves have drifted apart",
    )


def check_catalog(rig: DemoRig) -> None:
    """Every language the brain named on the speaking leg has a recorded clip.

    Both this and the catalog itself are now unrepresentable failures — ``Voice``
    and ``Language`` are enums and ``Config`` rejects a clip-less ``tts.language``
    on construction — so this asserts the guard is still wired rather than
    re-deriving it. It stays because the failures it names both happened: an
    unknown voice prefix is rejected at connect (``voice not found``), and a
    clip-less language was quietly served by the Hindi clip."""
    for config in _configs(rig):
        if config.tts is not None and config.tts.language is not None:
            checks.require(
                config.tts.language in SPEAKABLE,
                f"{rig.name}: TTS language {config.tts.language!r} has no recorded "
                "clip, so it would be read by the Hindi speaker",
            )
        if config.stt is not None and config.stt.language is not None:
            checks.require(
                config.stt.language in Language,
                f"{rig.name}: STT language {config.stt.language!r} is not served by vql-stt",
            )


def check_greeting(rig: DemoRig, turn: Any) -> None:
    """The demo greeted, on interaction 0, with closed brackets."""
    checks.check_greeting(rig.driver, turn)
    checks.require(
        bool(turn is not None and turn.text.strip()),
        f"{rig.name}: greeted with no text — the caller hears dead air on connect",
    )


def check_turn(rig: DemoRig, turn: Any, *, units: int | None = None) -> None:
    """A clean user turn: it spoke, every bracket closed, ids are monotone, and the
    turn completed (without which Voqalize stays muted for the rest of the call)."""
    checks.check_brackets_closed(turn)
    checks.check_speech_ids_monotonic(turn)
    checks.check_completed(turn)
    checks.check_spoke(turn)
    if units is not None:
        checks.require(
            len(turn.units) == units,
            f"{rig.name}: expected {units} unit(s) of speech, got "
            f"{len(turn.units)}: {[u.text for u in turn.units]}",
        )
