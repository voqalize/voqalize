"""What Tanvi does when a turn moved the page and said nothing.

The SDK's tool loop files a call's result for the next request, so a response made
of tool calls alone ends the turn in silence: the section opens and the visitor
hears nothing until the voice runtime's watchdog says "Sorry, that's taking longer
than I expected." At the low thinking a voice turn runs at, Gemini answers that way
often, whatever the prompt says (the evals in ``brain/evals`` caught it on most
page moves).

So a silent turn gets one more request, with the calls and their results now in
the context and tools switched off: the model has to talk, and what it talks about
is the section it just opened. The page has already moved, so the visitor watches
the screen change while she starts speaking. Only if that request is silent too does
she say a written line, recorded by the tool that moved the page (:func:`landed`);
that line makes no model call.

The written-line half is adapted from the public demos' ``voqalize_demos/silent_turn.py``
(Apache-2.0, github.com/voqalize/voqalize), trimmed to English.
"""

from __future__ import annotations

import contextlib
import random
from collections.abc import AsyncGenerator, Callable
from contextvars import ContextVar

from google.genai import types
from loguru import logger

from voqalize.sdk import Speech, SpeechChunk, SpeechEnd, SpeechStart
from voqalize.sdk.gemini import GeminiBrain, _Unit  # pyright: ignore[reportPrivateUsage]

_LANDED: ContextVar[list[tuple[str, ...]] | None] = ContextVar("tanvi_landed", default=None)


def landed(*lines: str) -> None:
    """Beside a dispatch the visitor sees, record the lines that say it landed."""
    if lines and (record := _LANDED.get()) is not None:
        record.append(lines)


async def say_line(brain: GeminiBrain, line: str) -> AsyncGenerator[Speech, None]:
    """One written line, spoken as the brain's own unit. Never in the model's context."""
    yield SpeechStart()
    brain._awaiting.append(_Unit(types.Content(role="model", parts=[])))  # pyright: ignore[reportPrivateUsage]
    yield SpeechChunk(line)
    yield SpeechEnd()


class FallbackLine:
    """Makes a silent page move speak: the model again, then a written line. One per brain."""

    def __init__(self) -> None:
        self._last = ""

    async def speak_if_silent(
        self,
        brain: GeminiBrain,
        turn: AsyncGenerator[Speech, None],
        again: Callable[[], AsyncGenerator[Speech, None]] | None = None,
    ) -> AsyncGenerator[Speech, None]:
        record: list[tuple[str, ...]] = []
        token = _LANDED.set(record)
        spoke = False
        try:
            async for event in turn:
                spoke = spoke or isinstance(event, SpeechStart)
                yield event
            if spoke or not record:
                return
            if again is not None:
                logger.info("tanvi: moved the page and said nothing; asking the model to speak")
                follow = again()
                try:
                    async for event in follow:
                        spoke = spoke or isinstance(event, SpeechStart)
                        yield event
                finally:
                    await follow.aclose()
                if spoke:
                    return
            choices = [line for line in record[-1] if line != self._last] or list(record[-1])
            self._last = random.choice(choices)
            logger.warning("tanvi: moved the page and said nothing, twice; saying {!r}", self._last)
            async for event in say_line(brain, self._last):
                yield event
        finally:
            await turn.aclose()
            with contextlib.suppress(ValueError):
                _LANDED.reset(token)
