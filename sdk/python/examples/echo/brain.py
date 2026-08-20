"""EchoBrain — the smallest possible Voqalize brain (no LLM, no external deps).

Greets, then echoes every turn back as ``"You said: {text}"``. It exists to answer
one question: *is the voice loop wired up end to end?* Speak into the mic, hear the
echo — the socket, the token, the frame vocabulary and your ``Brain`` callbacks are
all working.

The whole customer surface is two callbacks:

- ``greet`` returns the opening line. It answers no user stimulus, so it is the
  one thing the brain says without being asked.
- ``on_user_message`` is an async generator, and the generator is the mouth:
  ``SpeechStart`` opens a unit, ``Chunk`` streams text into it, ``SpeechEnd``
  closes it.

No ``Vql*`` frames, no LLM credentials, no dependencies beyond the SDK itself.
Host it with :func:`voqalize.sdk.run_session` — see ``examples/fastapi_inbound``.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from loguru import logger

from voqalize.sdk import Brain, Chunk, Session, Speech, SpeechEnd, SpeechStart, UserMessage


class EchoBrain(Brain):
    """Greets, then echoes each user turn."""

    async def greet(self, session: Session) -> str:
        logger.info("echo: session {} started", session.id)
        return "Hi! I'm an echo bot. Say something and I'll repeat it back."

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[Speech, None]:
        logger.info("echo: heard {!r}", msg.text)
        yield SpeechStart()
        yield Chunk(f"You said: {msg.text}")
        yield SpeechEnd()
