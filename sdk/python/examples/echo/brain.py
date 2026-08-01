"""EchoBrain — the smallest possible Voqalize brain (no LLM, no external deps).

Greets on session start and echoes every turn back as ``"You said: {transcript}"``.
It exists to answer one question: *is the voice loop wired up end to end?* Speak
into the mic, hear the echo — the socket, the token, the frame vocabulary, and
your ``Brain`` callbacks are all working.

The whole customer surface is two callbacks:

- ``on_session_start`` opens an agent-initiated inference (the greeting) via
  ``session.say()`` — the ``interaction_id = 0`` "no user stimulus" bracket.
- ``on_interaction`` opens one ``interaction.say()`` bracket per turn and
  ``speak``s the echoed transcript.

No ``Vql*`` frames, no LLM credentials, no dependencies beyond the SDK itself.
Run it with ``run_direct.py``.
"""

from __future__ import annotations

from loguru import logger

from voqalize.sdk import Brain, Interaction, Session, SessionStart


class EchoBrain(Brain):
    """Greets, then echoes each user turn."""

    async def on_session_start(self, session: Session, start: SessionStart) -> None:
        logger.info("echo: session {} started", session.id)
        async with session.say() as inf:
            await inf.speak("Hi! I'm an echo bot. Say something and I'll repeat it back.")

    async def on_interaction(self, interaction: Interaction) -> None:
        logger.info("echo: heard {!r}", interaction.transcript)
        async with interaction.say() as inf:
            await inf.speak(f"You said: {interaction.transcript}")
