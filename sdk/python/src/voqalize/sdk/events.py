"""What a Brain receives, and what it says.

Three groups, and the split between them is the whole contract:

* **Triggers** — :class:`UserMessage`, :class:`UserIdle`, :class:`BrowserMessage`.
  Voice hands one to a callback; that callback is where the floor lives.
* **Speech** — :class:`SpeechStart` / :class:`Chunk` / :class:`SpeechEnd`. The
  only thing a speaking callback may yield, because speech is the only thing
  whose position on the audio timeline is its meaning. Everything else — an
  action, a language switch, hanging up — is a method on the session.
* **Reports** — :class:`Finalize` and :class:`Error`. What happened, after it
  happened.

Speech is bracketed because it can be cut mid-word: one ``SpeechStart`` …
``SpeechEnd`` pair is one *unit*, and a unit is the granularity at which Voice
reports back what the user actually heard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "BrowserMessage",
    "Chunk",
    "Error",
    "Finalize",
    "SpeechEnd",
    "SpeechStart",
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
    had elapsed when Voice noticed.
    """

    level: int
    idle_ms: int


@dataclass(frozen=True)
class BrowserMessage:
    """The browser said something — a tap, a keystroke, a state push.

    Delivered unconditionally: Voice never interprets ``type`` and never decides
    whether it deserves a reply. Handling it cannot make the agent speak, because
    nothing about a click means the human stopped talking.
    """

    type: str
    data: dict[str, Any] = field(default_factory=dict)


# ─── Emissions ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SpeechStart:
    """Open a unit of speech."""


@dataclass(frozen=True)
class Chunk:
    """Text to speak, inside an open unit. Stream them as you produce them."""

    text: str


@dataclass(frozen=True)
class SpeechEnd:
    """Close the open unit of speech."""


#: One unit of speech, delimited.
Speech = SpeechStart | Chunk | SpeechEnd


# ─── Reports ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Finalize:
    """What the user actually heard for one unit of speech.

    Arrives after playout, which may be long after the callback that produced the
    unit returned. ``heard`` is the delivered prefix, not what you generated —
    on a barge-in the two differ, and recording the generated version is how a
    model ends up referencing sentences it never finished saying.

    ``speech_id`` names the unit this reports on — the value the SDK minted when
    the unit opened, echoed back unchanged. It correlates and does nothing else.
    """

    speech_id: int
    heard: str
    interrupted: bool


@dataclass(frozen=True)
class Error:
    """A runtime signal. Today: the wire dropped data under congestion."""

    message: str
    fatal: bool = False
