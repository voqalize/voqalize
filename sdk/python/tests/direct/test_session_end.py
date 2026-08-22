"""``session.end()`` — the Brain ends the call from its side (e.g. after a goodbye).

Emits a bare ``End`` frame on the normal lane, so it drains behind any speech the
Brain queued first. In production PyGato receives it and closes the socket; here the
conformance driver just records the frame it received. These pin: (1) a goodbye
followed by ``session.end()`` puts an ``End`` on the wire, ordered after the speech;
(2) ``end()`` is idempotent — a second call emits nothing.
"""

from __future__ import annotations

from voqalize.conformance import (
    BrainServer,
    DirectConnection,
    VoiceDriver,
    generate_keypair,
    mint_pygato_token,
)
from voqalize.sdk import (
    Brain,
    Chunk,
    SpeechEnd,
    SpeechStart,
)
from voqalize.sdk.wire import EndFrame

SESSION_ID = "session-end-test"


class GoodbyeBrain(Brain):
    """Greets, then on the first user turn says goodbye and ends the session."""

    def __init__(self, *, double_end: bool = False) -> None:
        self._double_end = double_end

    async def greet(self, session) -> str:
        return "Hello!"

    async def on_user_message(self, session, msg):
        yield SpeechStart()
        yield Chunk("Goodbye!")
        yield SpeechEnd()
        session.end(reason="user_said_bye")
        if self._double_end:
            session.end(reason="user_said_bye")


async def _run(brain: Brain) -> list:
    keypair = generate_keypair()
    server = BrainServer(
        lambda: brain,
        host="127.0.0.1",
        port=0,
        public_keys=keypair.public_pem,
    )
    port = await server.start()
    token = mint_pygato_token(
        private_key_pem=keypair.private_pem,
        session_id=SESSION_ID,
        agent_id="bye",
        tenant_id="demo",
    )
    driver = VoiceDriver(
        DirectConnection(f"ws://127.0.0.1:{port}", SESSION_ID, token=token),
        session_id=SESSION_ID,
        default_timeout=10.0,
    )
    await driver.open()
    try:
        g = await driver.start_session()
        assert g is not None and "Hello" in g.text
        t = await driver.user_says("bye")
        assert "Goodbye" in t.text
        return list(driver.log)
    finally:
        await driver.aclose()
        await server.aclose()


async def test_end_emits_end_frame_after_speech() -> None:
    log = await _run(GoodbyeBrain())
    end_positions = [i for i, r in enumerate(log) if isinstance(r.frame, EndFrame)]
    assert len(end_positions) == 1, "session.end() must emit exactly one End frame"

    # The End rides the normal lane, so it drains *after* the goodbye speech.
    from voqalize.sdk.wire import SpeechChunkFrame

    goodbye_positions = [
        i
        for i, r in enumerate(log)
        if isinstance(r.frame, SpeechChunkFrame) and "Goodbye" in r.frame.text
    ]
    assert goodbye_positions, "the goodbye must have been spoken"
    assert end_positions[0] > goodbye_positions[-1], "End must come after the goodbye speech"


async def test_end_is_idempotent() -> None:
    log = await _run(GoodbyeBrain(double_end=True))
    ends = [r for r in log if isinstance(r.frame, EndFrame)]
    assert len(ends) == 1, "a second end() must be a no-op"
