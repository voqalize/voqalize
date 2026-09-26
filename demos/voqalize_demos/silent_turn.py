"""A line of the brain's own for a turn that acted on screen and said nothing.

The loop runs a tool call and files its result for the *next* request, so a
response made of calls alone ends the turn in silence: the screen changes and the
user hears nothing until the runtime's watchdog apologises ten seconds later.
Every prompt here has the model say a short line and call in the same response,
and that line is the fast path — it is heard as the screen moves. On a dialled
call the model still sometimes called alone (tool-loop program, D2, 2026-09-26).
A prompt is a request; this is the floor under it.

The floor makes no model call. Beside each dispatch the user sees, the brain
records the lines that would say it landed — :func:`landed` — and when the turn
is over with nothing spoken, :meth:`FallbackLine.speak_if_silent` says one of the
last landed call's lines, straight away. Asking the model again would put a whole
request of silence between the screen moving and the first word; the line is
already written.

The line is never in the model's context. It is the brain's, not the model's, and
a model shown its own turn "saying" the canned line learns to leave the saying to
the brain. It is still a unit Voqalize will finalize, so it joins the finalize
queue after the model's own, where the heard truth that comes back for it is
taken and let go.

A demo that speaks more than one language says the line in the one its voice is
speaking. :data:`PHRASES` holds the few lines every such demo needs, per spoken
language: a demo names the phrase, and the language it is in, when the call lands.

What a brain does to use it::

    def __init__(self, ...):
        self._fallback = FallbackLine()

    def _show(self, action):
        self.session.dispatch(action)
        landed("It's open.", "Here it is.")

    async def respond(self, session):
        async for event in self._fallback.speak_if_silent(self, super().respond(session)):
            yield event
"""

from __future__ import annotations

import contextlib
import random
from collections.abc import AsyncGenerator, Mapping
from contextvars import ContextVar
from typing import Literal

from google.genai import types
from loguru import logger

from voqalize.sdk import Speech, SpeechChunk, SpeechEnd, SpeechStart
from voqalize.sdk.gemini import GeminiBrain, _Unit  # pyright: ignore[reportPrivateUsage]
from voqalize.sdk.wire import Language

#: The lines of each call that landed in the turn under way, in order. Per turn,
#: not per brain: each turn runs in its own task, and turns overlap when the user
#: speaks again before the last response has finished streaming, so a record on
#: the brain would hand one turn's dispatch to the other.
_LANDED: ContextVar[list[tuple[str, ...]] | None] = ContextVar("silent_turn_landed", default=None)

#: What a multilingual demo can say for a call, in any language it speaks:
#: ``shown`` for something put on screen, ``done`` for a change made, ``thanks``
#: for a call that ends the conversation, and ``over_to_you`` for a call that puts
#: a question in front of the user and waits for their answer. None of them names
#: the screen: the user can see it, and some demos never narrate it.
Phrase = Literal["shown", "done", "thanks", "over_to_you"]

#: The phrases, by the language the voice speaks — which, for a language no voice
#: speaks, is Hindi: those calls are answered in Hindi, and so is this. Each line
#: says the thing is done, not that it is being done: by the time it is spoken the
#: call has run.
PHRASES: Mapping[Language, Mapping[Phrase, tuple[str, ...]]] = {
    Language.EN: {
        "shown": ("Here it is.", "There you go."),
        "done": ("Done.", "That's done."),
        "thanks": ("Thank you. Goodbye.",),
        "over_to_you": ("Go ahead.", "Please, go ahead."),
    },
    Language.HI: {
        "shown": ("यह रहा।", "ये देखिए।"),
        "done": ("हो गया।", "ठीक है, हो गया।"),
        "thanks": ("धन्यवाद।",),
        "over_to_you": ("बताइए।", "जी, बताइए।"),
    },
    Language.BN: {
        "shown": ("এই যে।", "এই দেখুন।"),
        "done": ("হয়ে গেছে।",),
        "thanks": ("ধন্যবাদ।",),
        "over_to_you": ("বলুন।",),
    },
    Language.GU: {
        "shown": ("આ રહ્યું.", "આ જુઓ."),
        "done": ("થઈ ગયું.",),
        "thanks": ("આભાર.",),
        "over_to_you": ("જણાવો.",),
    },
    Language.KN: {
        "shown": ("ಇಲ್ಲಿದೆ.", "ಇದನ್ನು ನೋಡಿ."),
        "done": ("ಆಯ್ತು.",),
        "thanks": ("ಧನ್ಯವಾದಗಳು.",),
        "over_to_you": ("ಹೇಳಿ.",),
    },
    Language.ML: {
        "shown": ("ഇതാ.", "ഇത് നോക്കൂ."),
        "done": ("ശരി, ചെയ്തു.",),
        "thanks": ("നന്ദി.",),
        "over_to_you": ("പറയൂ.",),
    },
    Language.MR: {
        "shown": ("हे पाहा.", "हे बघा."),
        "done": ("झालं.",),
        "thanks": ("धन्यवाद.",),
        "over_to_you": ("सांगा.",),
    },
    Language.PA: {
        "shown": ("ਇਹ ਰਿਹਾ।", "ਇਹ ਦੇਖੋ।"),
        "done": ("ਹੋ ਗਿਆ।",),
        "thanks": ("ਧੰਨਵਾਦ।",),
        "over_to_you": ("ਦੱਸੋ।",),
    },
    Language.TA: {
        "shown": ("இதோ.", "இதைப் பாருங்கள்."),
        "done": ("முடிந்தது.",),
        "thanks": ("நன்றி.",),
        "over_to_you": ("சொல்லுங்கள்.",),
    },
    Language.TE: {
        "shown": ("ఇదిగో.", "ఇది చూడండి."),
        "done": ("అయిపోయింది.",),
        "thanks": ("ధన్యవాదాలు.",),
        "over_to_you": ("చెప్పండి.",),
    },
}


def phrase(language: Language, what: Phrase) -> tuple[str, ...]:
    """The lines for ``what`` in the spoken ``language``.

    A language with no row raises: a multilingual demo holds its spoken languages
    to :data:`PHRASES` at import, so this is found in CI, not on a call."""
    return PHRASES[language][what]


def landed(*lines: str) -> None:
    """Record, beside a dispatch, the lines that say it landed.

    Call it for anything the user sees move as an answer. A read, a refused call,
    and a dispatch that is not an answer — a language switch — record nothing.
    Outside a turn it does nothing."""
    if lines and (record := _LANDED.get()) is not None:
        record.append(lines)


class FallbackLine:
    """Speaks a landed call's line when the model's turn said nothing. One per brain."""

    def __init__(self) -> None:
        self._last = ""

    async def speak_if_silent(
        self, brain: GeminiBrain, turn: AsyncGenerator[Speech, None]
    ) -> AsyncGenerator[Speech, None]:
        """``turn`` — the inherited ``super().respond(session)`` — and then, if it
        spoke nothing and something landed, one line from the last call that did."""
        record: list[tuple[str, ...]] = []
        token = _LANDED.set(record)
        spoke = False
        try:
            async for event in turn:
                spoke = spoke or isinstance(event, SpeechStart)
                yield event
            if spoke or not record:
                return
            line = self._pick(record[-1])
            logger.warning("turn: acted on screen and said nothing; the brain says {!r}", line)
            yield SpeechStart()
            brain._awaiting.append(_Unit(types.Content(role="model", parts=[])))  # pyright: ignore[reportPrivateUsage]
            yield SpeechChunk(line)
            yield SpeechEnd()
        finally:
            await turn.aclose()
            # Closed from another context, the token cannot be reset — and there
            # is nothing to reset: the value went with the task that set it.
            with contextlib.suppress(ValueError):
                _LANDED.reset(token)

    def _pick(self, lines: tuple[str, ...]) -> str:
        """One of ``lines``, never the one said last."""
        choices = [line for line in lines if line != self._last] or list(lines)
        self._last = random.choice(choices)
        return self._last
