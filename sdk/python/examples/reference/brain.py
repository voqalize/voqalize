"""ReferenceBrain — every part of the protocol, driven by voice.

``examples/echo`` answers *is the loop wired up?* in twelve lines. This one
answers the next question: **does each lane of the protocol actually work on a
real call?** Every capability is bound to a spoken phrase, so one call exercises
the whole surface without a test harness in sight.

Say                     | What it proves
------------------------|--------------------------------------------------
(anything)              | ``on_user_message`` streams — the reply arrives word
                        | by word, one ``Chunk`` each, inside one speech unit
"look it up"            | Two units in one turn: a filler, a pause, an answer
"open the dashboard"    | ``session.dispatch`` — a ui-command on the RTVI lane
"ask me something"      | An action that asks; the app's reply arrives at
                        | ``on_rtvi`` and is voiced on the next turn
"what did you hear"     | Heard-text reconciliation: what the caller actually
                        | received, which is not what was generated if you barged in
"speak hindi"           | ``session.configure`` — both legs, TTS and STT
"speak english"         | back again
"goodbye"               | Speak, then ``session.end()`` — the goodbye is heard

Barge in at any point: cut the bot off mid-sentence, then ask "what did you
hear". The answer is the truncated prefix, because ``on_finalize`` is where the
brain learns what was delivered and rewrites its own transcript to match. That
reconciliation is the brain's job — the SDK keeps no history for you.

**Walk the language lane last.** These triggers are English substring matches —
a harness, not a design. A real brain routes on intent, and ends a call because
its model called a tool, not because a string matched. The moment the recognizer
moves to Hindi it returns Devanagari, and every English trigger here stops
matching; ``_EXITS`` and ``_GOODBYE`` carry the surface forms of the two lanes
that have to survive that, and nothing else does.

Only ``on_user_message`` is required; everything else here is opt-in.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

from loguru import logger

from voqalize.sdk import (
    Action,
    Brain,
    Chunk,
    Error,
    Finalize,
    RTVIMessage,
    Session,
    Speech,
    SpeechEnd,
    SpeechStart,
    UserIdle,
    UserMessage,
)
from voqalize.sdk.wire import Config, IdleConfig, Language, SttConfig, TtsConfig, Voice

# ─── Actions: a class per app command, fields are the payload ────────────────


class OpenDashboard(Action):
    """→ an RTVI ``ui-command``: {"command":"open_dashboard","payload":{"panel":…}}"""

    panel: str


class AskQuestion(Action):
    """Puts a question on the screen. The app answers whenever it likes, as an
    ordinary client message — see ``on_rtvi``."""

    prompt: str
    choices: list[str]


# ─── The brain ────────────────────────────────────────────────────────────────

#: Language → the voice that language should be read in. Moving one without the
#: other is the silent bug ``Config`` refuses to let you write.
_VOICES = {
    Language.HI: Voice.OMNIVOICE_GAURI,
    Language.TA: Voice.OMNIVOICE_GAURI,
    Language.EN: Voice.OMNIVOICE_GAURI,
}

#: Language → the phrases that switch to it, in every language the suite can
#: already be speaking; the first is also what we call it out loud. A one-way door
#: is an unwalkable lane: on 2026-08-21 a walk switched to Hindi, and "speak
#: english" came back as ``इंग्लिश में बात करो``.
_EXITS = {
    Language.EN: ("english", "इंग्लिश", "अंग्रेज़ी", "ஆங்கிலம்"),
    Language.HI: ("hindi", "हिंदी", "हिन्दी", "இந்தி"),
    Language.TA: ("tamil", "तमिल", "தமிழ்"),
}

#: Same reason: the hang-up has to be reachable from whatever the call switched to.
_GOODBYE = ("goodbye", "hang up", "गुड बाय", "गुडबाय", "अलविदा", "பை", "விடைபெறுகிறேன்")


class ReferenceBrain(Brain):
    """Holds only its own state. Capability arrives on the ``session``."""

    voice = Voice.OMNIVOICE_GAURI

    def __init__(self) -> None:
        #: speech_id → what the caller actually heard. Written in on_finalize.
        self.heard: dict[int, str] = {}
        #: speech_id → what this brain generated for that unit. The SDK hands
        #: it back on the finalize, so pairing the two is not the brain's job.
        self.generated: dict[int, str] = {}
        #: What the app last answered, spoken on the next turn — an app message
        #: holds no floor, so it cannot speak for itself.
        self._pending_answer: str | None = None

    # ─── Lifecycle ───────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        logger.info("reference: session {} init={}", session.id, session.init)
        # Nudge after 20 s of silence rather than the record's default.
        await session.configure(Config(idle=IdleConfig(timeout_ms=20_000)))

    async def greet(self, session: Session) -> str:
        line = (
            "Hello. I am the reference brain. Say anything and I will echo it, "
            "or ask me to open the dashboard."
        )
        return line

    async def on_session_end(self, session: Session) -> None:
        logger.info("reference: session {} ended; heard={}", session.id, self.heard)

    async def on_error(self, session: Session, error: Error) -> None:
        logger.error("reference: error fatal={} {}", error.fatal, error.message)

    # ─── The one required callback ───────────────────────────────────────

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[Speech, None]:
        said = msg.text.lower().strip()
        logger.info("reference: heard {!r}", msg.text)

        # An answer that arrived between turns gets voiced now.
        if self._pending_answer is not None:
            answer, self._pending_answer = self._pending_answer, None
            async for speech in self._say(f"By the way, you picked {answer}."):
                yield speech

        if any(word in said for word in _GOODBYE):
            async for speech in self._say("Goodbye. Ending the call now."):
                yield speech
            # The generator body resumes only once the SDK has consumed
            # everything yielded, so writing it in this order IS the ordering:
            # the goodbye is spoken before the hang-up frame goes out.
            session.end("caller said goodbye")
            return

        if "dashboard" in said:
            session.dispatch(OpenDashboard(panel="overview"))
            async for speech in self._say("Opening the dashboard now."):
                yield speech
            return

        if "ask me" in said:
            session.dispatch(AskQuestion(prompt="Which one?", choices=["first", "second"]))
            async for speech in self._say(
                "I put a question on your screen. Tap an answer and I will "
                "mention it on your next turn."
            ):
                yield speech
            return

        if "what did you hear" in said or "what did i hear" in said:
            if not self.heard:
                async for speech in self._say("Nothing has finished playing yet."):
                    yield speech
                return
            last = max(self.heard)
            gen, got = self.generated.get(last, ""), self.heard[last]
            cut = "" if gen.strip() == got.strip() else " You cut me off, so that is shorter."
            async for speech in self._say(f"You heard: {got}.{cut}"):
                yield speech
            return

        if "look it up" in said or "slowly" in said:
            # Two speech units in one turn — the tool-hop shape. The first closes
            # before the second opens; each gets its own speech id.
            async for speech in self._say("Let me look that up."):
                yield speech
            await asyncio.sleep(2.0)
            async for speech in self._say("I checked, and the answer is forty two."):
                yield speech
            return

        for lang, phrases in _EXITS.items():
            if any(phrase in said for phrase in phrases):
                async for speech in self._say(f"Switching to {phrases[0]}."):
                    yield speech
                # One request moves BOTH legs — the recognizer and the voice —
                # so there is no moment where the call is half in each.
                await session.configure(
                    Config(
                        stt=SttConfig(language=lang),
                        tts=TtsConfig(language=lang, voice=_VOICES[lang]),
                    )
                )
                return

        async for speech in self._say(f"You said: {msg.text}"):
            yield speech

    # ─── Optional callbacks ──────────────────────────────────────────────

    async def on_user_idle(self, session: Session, idle: UserIdle) -> AsyncGenerator[Speech, None]:
        logger.info("reference: idle level={} after {}ms", idle.level, idle.idle_ms)
        async for speech in self._say("Still here whenever you are ready."):
            yield speech

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        # Not a generator: an app message never takes the floor. An action's
        # answer arrives here like any other tap — the dispatch that asked the
        # question is over, so correlate on whatever your app puts in the reply.
        logger.info("reference: rtvi {} id={} {}", msg.type.value, msg.id, msg.data)
        if not isinstance(msg.data, dict) or msg.data.get("t") != "answer":
            return
        choice = (msg.data.get("d") or {}).get("choice")
        if isinstance(choice, str):
            self._pending_answer = choice

    async def on_finalize(self, session: Session, fin: Finalize) -> None:
        """What the caller actually heard — the only place the brain learns it.

        On a clean unit this equals what was generated. On a barge-in it is the
        played prefix, and *that* is what belongs in history: a model that is told
        it said three sentences the caller never heard will answer the next turn
        as if they landed.
        """
        self.heard[fin.speech_id] = fin.heard
        self.generated[fin.speech_id] = fin.generated
        logger.info(
            "reference: finalized #{} interrupted={} heard={!r} (generated {!r})",
            fin.speech_id,
            fin.interrupted,
            fin.heard,
            fin.generated,
        )

    # ─── Helpers ─────────────────────────────────────────────────────────

    async def _say(self, text: str) -> AsyncGenerator[Speech, None]:
        """One speech unit, streamed word by word so the chunking is audible on
        the wire (a real brain yields whatever its model streams)."""
        yield SpeechStart()
        for word in text.split(" "):
            yield Chunk(word + " ")
        yield SpeechEnd()
