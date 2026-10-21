"""What a Brain receives, and what it says.

Three groups, and the split between them is the whole contract:

* **Triggers** — :class:`UserMessage`, :class:`UserIdle`, :class:`RTVIMessage`.
  Voqalize hands one to a callback; that callback is where the floor lives.
* **Speech** — :class:`SpeechStart` / :class:`SpeechChunk` / :class:`SpeechEnd`. The
  only thing a speaking callback may yield, because speech is the only thing
  whose position on the audio timeline is its meaning. Everything else — an
  action, a language switch, hanging up — is a method on the session.
* **Reports** — :class:`Finalize` and :class:`Error`. What happened, after it
  happened. :class:`TurnStep` is the one report that goes the other way: one
  piece of work the brain did for a turn, for :meth:`Session.report_step`.

Speech is bracketed because it can be cut mid-word: one ``SpeechStart`` …
``SpeechEnd`` pair is one *unit*, and a unit is the granularity at which Voqalize
reports back what the user actually heard. It is also the granularity at which a
brain can take speech back: ``session.cancel_speech`` names a unit by the
``speech_id`` the SDK writes onto its ``SpeechStart``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .wire import ErrorCode, RTVIType

__all__ = [
    "Error",
    "Finalize",
    "RTVIMessage",
    "Speech",
    "SpeechChunk",
    "SpeechEnd",
    "SpeechStart",
    "TurnStep",
    "UserIdle",
    "UserMessage",
]


# ─── Triggers ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class UserMessage:
    """The human finished an utterance and the floor is yours."""

    text: str


@dataclass(frozen=True)
class UserIdle:
    """The human has gone quiet, and the floor is yours if you want it.

    ``level`` counts consecutive escalations with no intervening speech (1 is the
    first nudge, and it resets the moment they say something), so a brain can
    escalate — "still there?" at 1, wrap up at 3. ``idle_ms`` is the silence that
    had elapsed when Voqalize noticed.
    """

    level: int
    idle_ms: int


@dataclass(frozen=True)
class RTVIMessage:
    """One RTVI message from the app — a tap, a keystroke, a state push.

    Voqalize forwards the whitelisted types verbatim and interprets nothing about
    them. Handling one cannot make the agent speak, because nothing about a click
    means the human stopped talking.

    ``id`` is RTVI's own correlation id when the message carries one; answer such
    a message with :meth:`Session.send_rtvi` quoting it back.
    """

    type: RTVIType
    data: Any = None
    id: str | None = None


# ─── Emissions ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SpeechStart:
    """Open a unit of speech.

    Keep a reference to it when you might want to stop the unit later: the SDK
    writes the id it minted onto ``speech_id`` as the unit opens, and that id is
    what :meth:`Session.cancel_speech` and :class:`Finalize` name::

        start = SpeechStart()
        yield start
        ...
        fin = await session.cancel_speech(start.speech_id)

    ``None`` until the SDK has consumed the yield. Not a constructor argument:
    ids are minted by the SDK, never chosen. It plays no part in equality, so
    every ``SpeechStart()`` still compares equal to every other.

    Yield a fresh ``SpeechStart()`` for each unit you may cancel. The id is
    written onto the instance each time it is yielded, so one instance shared
    across units or sessions names only the unit it opened last.
    """

    speech_id: int | None = field(default=None, init=False, compare=False)


@dataclass(frozen=True)
class SpeechChunk:
    """Text to speak, inside an open unit. Stream them as you produce them."""

    text: str


@dataclass(frozen=True)
class SpeechEnd:
    """Close the open unit of speech."""


#: One unit of speech, delimited.
Speech = SpeechStart | SpeechChunk | SpeechEnd

#: The name this class shipped under until 2026-09-08, kept working.
#:
#: ``SpeechChunk`` is canonical because a name you can grep is worth more than a
#: name that is two characters shorter: one search now finds the proto message,
#: the wire frame, the SDK class, every demo that yields one and every recorded
#: event, and ``Chunk`` alone found none of those. It is the same class, so
#: ``isinstance`` and ``match`` are unaffected either way.
Chunk = SpeechChunk


# ─── Reports ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Finalize:
    """What the user actually heard for one unit of speech.

    Arrives after playout, which may be long after the callback that produced the
    unit returned. ``heard`` is the delivered prefix, not what you generated —
    on a barge-in the two differ, and recording the generated version is how a
    model ends up referencing sentences it never finished saying.

    ``generated`` is the text this end put on the wire for that unit, kept by the
    SDK so you do not have to keep it yourself. ``heard`` is a verbatim prefix of
    it, which is what makes :attr:`interrupted` a comparison rather than a claim:
    equal means the unit played out, shorter means the user cut it off, and
    empty against a unit that sent text means nothing reached the ear. Voqalize
    used to send the verdict alongside the evidence; it stopped, because a copy of
    a derivable fact is one more thing that can be wrong.

    ``speech_id`` names the unit this reports on — the value the SDK minted when
    the unit opened, echoed back unchanged. It correlates and does nothing else.
    """

    speech_id: int
    heard: str
    generated: str

    @property
    def interrupted(self) -> bool:
        """``True`` when the unit was cut short — the user talked over it, or the
        brain cancelled it with :meth:`Session.cancel_speech` before it played
        out."""
        return self.heard != self.generated


@dataclass(frozen=True)
class Error:
    """A signal from Voqalize. Today: the wire dropped data under congestion."""

    code: ErrorCode
    message: str
    fatal: bool = False


# ─── What the brain reports ───────────────────────────────────────────────────


@dataclass(frozen=True)
class TurnStep:
    """One piece of work the brain did for a turn, for :meth:`Session.report_step`:
    a model request, a tool, a database query, an API or MCP call.

    ``kind`` says what sort — ``"model"`` and ``"tool"`` are the ones the voice
    brains report themselves; a brain names its own (``"database"``, ``"http"``,
    ``"mcp"``). ``name`` says which one: the model, the tool, the table.
    ``provider`` is the company whose meter the counts ran on, never a router in
    between, and empty for the brain's own work.

    ``start_ms`` is when it began, after the brain received the turn's stimulus.
    Leave it ``None`` when reporting a step the moment it ends, and the session
    places it: now, less ``duration_ms``.

    ``counts`` is how much of what, by name. For a model request:
    ``input_tokens`` (cached ones included), ``cached_input_tokens``,
    ``cache_write_tokens``, ``output_tokens`` (text and tool calls) and
    ``reasoning_tokens`` (thinking nobody hears and the provider still bills).
    Leave out a count that was not reported rather than writing 0. Counts, never
    prices, and never content: no prompt, no arguments, no result.
    """

    kind: str
    name: str
    duration_ms: int
    provider: str = ""
    start_ms: int | None = None
    first_output_ms: int | None = None
    counts: Mapping[str, int] = field(default_factory=lambda: dict[str, int]())
