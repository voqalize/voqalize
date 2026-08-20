"""``ConformanceBrain`` — a cooperating reference brain the conformance driver
drives to exercise, and *observe*, every protocol path.

Two reasons it lives in the harness rather than the tests:

1. **Deep-semantics observability (the backchannel).** The wire lets the driver
   see the brain's *output* frames, but never what the brain *committed* — the
   heard transcript, the app messages it received, the action results it
   correlated. Those are the MUSTs a black-box driver cannot assert, because the
   protocol has no history-request frame and we add none. Instead the brain
   echoes its committed state back over the ordinary application-message lane
   (a ``ui_command``) in response to the namespaced
   ``__voqal.conformance.dump`` client message. No protocol change — just
   cooperation on a lane the protocol already has.

   The echo is brain-side bookkeeping, and it has to be: **history belongs to the
   brain.** The SDK maintains no transcript, so what this brain records from
   ``on_finalize`` — the delivered prefix, never the generated text — *is* the
   property under test. A brain that recorded what it generated would fail the
   barge-in scenarios, which is exactly the bug those scenarios exist to catch.

2. **A known-good brain to self-test the driver.** Running the catalog against
   ``ConformanceBrain`` proves the driver itself is sound before it is pointed at
   a brain under test.

The brain is driven purely by the user transcript — a tiny command grammar the
scenarios speak (see the ``SAY`` / ``TWO`` / ``COUNT_SLOWLY`` / ``DO`` constants).
A brain under test does *not* need this grammar: the wire-level tier (greeting,
single/multi-turn, bracket integrity, auth) works against any brain, and the suite
**probes** for the grammar and skips the rest rather than failing a brain for not
knowing a vocabulary it was never supposed to know (see :mod:`.report`).

Everything that needs the grammar is marked ``requires_reference`` in the catalog,
barge-in included — cutting a reply mid-flight needs a reply long enough to still
be playing, which is exactly what ``count slowly`` is for. Against an ordinary
brain the cut lands after generation finished, which is legal and proves nothing.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from voqalize.sdk import (
    Action,
    AppMessage,
    Brain,
    Chunk,
    Emission,
    Finalize,
    IdleTrigger,
    Result,
    Session,
    SpeechEnd,
    SpeechStart,
    UserMessage,
)

from .driver import CONFORMANCE_DUMP_EVENT, CONFORMANCE_STATE_ACTION

# ─── The command grammar the scenarios speak ─────────────────────────────────

GREETING_TEXT = "hello"
SAY_PREFIX = "say "  # "say banana" → one unit of speech that says "banana"
TWO = "two"  # two units: "first" then "second"
TWO_FIRST = "first"
TWO_SECOND = "second"
COUNT_SLOWLY = "count slowly"  # slow multi-chunk unit, cuttable by barge-in
DO_PREFIX = "do "  # "do open_panel" → speak + fire an action, correlate its result

# Fault grammar — the brain deliberately misbehaves so the driver can assert the
# SDK's liveness guarantee: a raising turn must NOT hang the session. A turn left
# with an open bracket is dead air for the rest of the call — TTS never flushes
# the tail and the user waits on a reply that will not come.
RAISE = "raise"  # raise immediately, before speaking a word
SPEAK_RAISE_PREFIX = "speak then raise "  # "speak then raise ok" → say "ok", then raise


class ReferenceBrainFault(RuntimeError):
    """The reference brain's deliberate fault (see the fault grammar above)."""


# A long, cuttable "story" response, used by the multi-interruption heard-truth
# stress test. It plays one deterministic heard chunk, pauses long enough for a
# barge-in to land, then would speak a tail carrying BARGE_SENTINEL. The heard
# chunk is a pure function of the topic (see ``story_opening``), so the driver
# knows exactly what a mid-story barge-in should have committed.
STORY_PREFIX = "tell me "  # "tell me beanstalk" → a long story about "beanstalk"
STORY_OPENING = "Once upon a time, the story of "  # heard-before-a-barge chunk
STORY_TAIL = "unfolds to its conclusion. "  # the un-heard tail (+ BARGE_SENTINEL)

# A response that stays silent before speaking, so a barge-in can land *before
# any audio plays* (heard-truth empty ⇒ no assistant message committed).
SILENT_PREFIX = "wait then "

# The reference brain's deterministic reply to the one Voice-opened, non-spoken
# trigger that may still take the floor, so the driver can assert on a known
# string.
IDLE_NUDGE = "still there"  # on_user_idle → f"{IDLE_NUDGE} {level}"

# The tail a barge-in MUST cut off — emitted only after a long pause, so an
# interruption always lands before it. Its presence in heard text is a failure.
BARGE_SENTINEL = "NEVER_HEARD_AFTER_BARGE_IN"


class OpenPanel(Action, name="open_panel"):
    """The one action the ``do `` grammar knows, for the action round-trip."""

    foo: str = "bar"


class ConformanceState(Action, name=CONFORMANCE_STATE_ACTION):
    """The backchannel echo: committed state over the ordinary action lane."""

    messages: list[dict[str, Any]]
    app_events: list[dict[str, Any]]
    outcomes: list[dict[str, Any]]


def story_opening(topic: str) -> str:
    """The exact heard text a mid-story barge-in should leave committed for a
    ``tell me {topic}`` turn — deterministic, so scenarios can assert on it."""
    return f"{STORY_OPENING}{topic}. "


def conformance_state(brain: ConformanceBrain) -> dict[str, Any]:
    """The backchannel state payload: heard transcript, app messages, results."""
    return {
        "messages": list(brain.messages),
        "app_events": list(brain.app_events),
        "outcomes": list(brain.outcomes),
    }


class ConformanceBrain(Brain):
    """A deterministic reference brain that also echoes its committed state."""

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.app_events: list[dict[str, Any]] = []
        self.outcomes: list[dict[str, Any]] = []

    async def greet(self, session: Session) -> str:
        return GREETING_TEXT

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[Emission, None]:
        text = msg.text
        self.messages.append({"role": "user", "content": text})

        if text.startswith(SAY_PREFIX):
            yield SpeechStart()
            yield Chunk(text[len(SAY_PREFIX) :])
            yield SpeechEnd()
            return

        if text == TWO:
            yield SpeechStart()
            yield Chunk(TWO_FIRST)
            yield SpeechEnd()
            yield SpeechStart()
            yield Chunk(TWO_SECOND)
            yield SpeechEnd()
            return

        if text == COUNT_SLOWLY:
            yield SpeechStart()
            yield Chunk("one. ")
            await asyncio.sleep(0.05)
            yield Chunk("two. ")
            await asyncio.sleep(0.05)
            yield Chunk("three. ")
            # A long pause, then a tail: a barge-in during the pause must cut
            # this off, so BARGE_SENTINEL must never reach heard text.
            await asyncio.sleep(0.5)
            yield Chunk(BARGE_SENTINEL)
            yield SpeechEnd()
            return

        if text.startswith(STORY_PREFIX):
            # One heard chunk, a long pause (a barge-in lands here), then the
            # un-heard tail. If the turn is *not* interrupted, the whole story —
            # sentinel included — is heard and committed.
            yield SpeechStart()
            yield Chunk(story_opening(text[len(STORY_PREFIX) :]))
            await asyncio.sleep(0.5)
            yield Chunk(f"{STORY_TAIL}{BARGE_SENTINEL}")
            yield SpeechEnd()
            return

        if text.startswith(SILENT_PREFIX):
            # Open the bracket, then stay silent long enough for a barge-in to
            # land before any audio: heard-truth is empty ⇒ nothing committed.
            yield SpeechStart()
            await asyncio.sleep(0.5)
            yield Chunk(f"delayed {text[len(SILENT_PREFIX) :]}")
            yield SpeechEnd()
            return

        if text == RAISE:
            # Raise before speaking: no bracket, no text — the session must stay
            # live so Voice unmutes for the next turn.
            raise ReferenceBrainFault("deliberate fault before any speech")

        if text.startswith(SPEAK_RAISE_PREFIX):
            # Speak a chunk (heard-truth must survive), then raise: the bracket
            # closes and the session stays live.
            yield SpeechStart()
            yield Chunk(text[len(SPEAK_RAISE_PREFIX) :])
            yield SpeechEnd()
            raise ReferenceBrainFault("deliberate fault after speaking")

        if text.startswith(DO_PREFIX):
            yield SpeechStart()
            yield Chunk("on it")
            yield SpeechEnd()
            yield OpenPanel(on_result=self._record)
            return

        yield SpeechStart()
        yield Chunk(f"you said {text}")
        yield SpeechEnd()

    async def on_user_idle(
        self, session: Session, idle: IdleTrigger
    ) -> AsyncGenerator[Emission, None]:
        # Voice handed over the floor because the user went quiet; re-engage with
        # a level-tagged nudge so the driver can assert both the heard text and
        # the escalation level. No user turn is recorded — nothing was said.
        yield SpeechStart()
        yield Chunk(f"{IDLE_NUDGE} {idle.level}")
        yield SpeechEnd()

    async def on_app_message(
        self, session: Session, msg: AppMessage
    ) -> AsyncGenerator[Action, None]:
        # Voice delivers every browser message here and never interprets it — the
        # brain decides what to do with each. It may render; it may not speak.
        if msg.type == CONFORMANCE_DUMP_EVENT:
            yield ConformanceState(**conformance_state(self), timeout_s=None)
            return
        self.app_events.append({"name": msg.type, "data": msg.data})

    async def on_finalize(self, session: Session, fin: Finalize) -> None:
        # The heard prefix, not what was generated. An interrupted unit that
        # delivered nothing commits nothing.
        if fin.heard:
            self.messages.append({"role": "assistant", "content": fin.heard})

    def _record(self, result: Result) -> None:
        self.outcomes.append(
            {
                "action_id": result.action_id,
                "status": result.status,
                "result": result.data,
            }
        )
