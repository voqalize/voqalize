"""``ConformanceBrain`` — a cooperating reference brain the conformance driver
drives to exercise, and *observe*, every protocol path.

Two reasons it lives in the harness rather than the tests:

1. **Deep-semantics observability (the backchannel).** The wire lets the driver
   see the brain's *output* frames, but never what the brain *committed* to its
   session — the heard-truth ``Conversation``, the app-events it received, the
   action outcomes it correlated. Those are the MUSTs a black-box driver cannot
   assert, because the protocol has no history-request frame and we add none.
   Instead the brain echoes its committed state back over the ordinary
   application-message lane (``session.action`` → an ``RTVIServerMessage``) in
   response to the namespaced ``__voqal.conformance.dump`` client message. No
   protocol change — just cooperation on a lane the protocol already has.

   The echo is a pure function of the framework-owned ``Session`` (see
   :func:`conformance_state`), so it does *not* rely on this reference brain's
   own bookkeeping for the part that matters most — the conversation. The SDK
   could wire the same handler into ``_BrainAdapter`` behind a flag and every
   brain built on it would become conformance-testable with zero brain code.

2. **A known-good brain to self-test the driver.** Running the catalog against
   ``ConformanceBrain`` proves the driver itself is sound before it is pointed at
   a brain under test.

The brain is driven purely by the user transcript — a tiny command grammar the
scenarios speak (see the ``SAY`` / ``TWO`` / ``COUNT_SLOWLY`` / ``STORY`` / ``DO``
constants). A brain under test does *not* need this grammar; the generic
scenarios (greeting, single/multi-turn, barge-in, brackets) work against any
brain. Only the deep-semantics + action scenarios need a cooperating brain.
"""

from __future__ import annotations

import asyncio
from typing import Any

from voqalize.sdk import Brain

from .driver import CONFORMANCE_DUMP_EVENT, CONFORMANCE_STATE_ACTION

# ─── The command grammar the scenarios speak ─────────────────────────────────

GREETING_TEXT = "hello"
SAY_PREFIX = "say "  # "say banana" → one inference that speaks "banana"
TWO = "two"  # two inferences: "first" then "second"
TWO_FIRST = "first"
TWO_SECOND = "second"
COUNT_SLOWLY = "count slowly"  # slow multi-chunk inference, cuttable by barge-in
DO_PREFIX = "do "  # "do open_panel" → speak + fire an action, await its outcome

# Fault grammar — the brain deliberately misbehaves so the driver can assert the
# SDK's liveness guarantee: a raising ``on_interaction`` must NOT hang the session.
# Voice waits on VqlInteractionCompleted to unmute, so a dropped completion is dead
# air for the rest of the call — the single failure the adversarial review flagged
# as a protocol violation. These exercise the core's except-path completion.
RAISE = "raise"  # raise immediately, before speaking a word
SPEAK_RAISE_PREFIX = "speak then raise "  # "speak then raise ok" → speak "ok", then raise


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

# The reference brain's deterministic replies to the two Voice-opened,
# non-spoken triggers, so the driver can assert on a known string.
IDLE_NUDGE = "still there"  # on_user_idle → f"{IDLE_NUDGE} {level}"
APP_ACK_PREFIX = "handled "  # a responding client message → f"{APP_ACK_PREFIX}{message.type}"

# The reference convention for on_client_message: Voice delivers *every* browser
# message with a pre-minted interaction_id and never interprets it, so the brain
# decides what to do. This brain records every message as ambient state, and
# additionally takes the floor and answers messages whose type is in
# APP_RESPOND_TYPES (via message.interaction) — proving both halves of the seam.
APP_RESPOND_TYPES = frozenset({"form_submitted"})

# The tail a barge-in MUST cut off — emitted only after a long pause, so an
# interruption always lands before it. Its presence in heard text is a failure.
BARGE_SENTINEL = "NEVER_HEARD_AFTER_BARGE_IN"


def story_opening(topic: str) -> str:
    """The exact heard text a mid-story barge-in should leave committed for a
    ``tell me {topic}`` turn — deterministic, so scenarios can assert on it."""
    return f"{STORY_OPENING}{topic}. "


def conformance_state(
    session: Any,
    *,
    app_events: list[dict[str, Any]] | None = None,
    outcomes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the backchannel state payload from a framework-owned ``Session``.

    The ``messages`` block — the heard-truth history the brain would send to the
    LLM — is read straight off ``session.conversation``, which the SDK owns and
    the brain cannot corrupt. That is the whole point: this function depends only
    on framework state, so the SDK could publish it for *any* brain. The
    ``app_events`` / ``outcomes`` blocks are optional brain-side bookkeeping the
    reference brain happens to keep for the action/app-event scenarios."""
    return {
        "messages": [{"role": m.role, "content": m.content} for m in session.conversation.messages],
        "app_events": list(app_events or []),
        "outcomes": list(outcomes or []),
    }


class ConformanceBrain(Brain):
    """A deterministic reference brain that also echoes its committed state."""

    def __init__(self) -> None:
        self.app_events: list[dict[str, Any]] = []
        self.outcomes: list[dict[str, Any]] = []

    async def on_session_start(self, session, start) -> None:
        async with session.say() as inf:
            await inf.speak(GREETING_TEXT)

    async def on_interaction(self, interaction) -> None:
        text = interaction.transcript

        if text.startswith(SAY_PREFIX):
            async with interaction.say() as inf:
                await inf.speak(text[len(SAY_PREFIX) :])
            return

        if text == TWO:
            async with interaction.say() as inf:
                await inf.speak(TWO_FIRST)
            async with interaction.say() as inf:
                await inf.speak(TWO_SECOND)
            return

        if text == COUNT_SLOWLY:
            async with interaction.say() as inf:
                await inf.speak("one. ")
                await asyncio.sleep(0.05)
                await inf.speak("two. ")
                await asyncio.sleep(0.05)
                await inf.speak("three. ")
                # A long pause, then a tail: a barge-in during the pause must cut
                # this off, so BARGE_SENTINEL must never reach heard text.
                await asyncio.sleep(0.5)
                await inf.speak(BARGE_SENTINEL)
            return

        if text.startswith(STORY_PREFIX):
            topic = text[len(STORY_PREFIX) :]
            async with interaction.say() as inf:
                # One heard chunk, a long pause (a barge-in lands here), then the
                # un-heard tail. If the turn is *not* interrupted, the whole story
                # — sentinel included — is heard and committed.
                await inf.speak(story_opening(topic))
                await asyncio.sleep(0.5)
                await inf.speak(f"{STORY_TAIL}{BARGE_SENTINEL}")
            return

        if text.startswith(SILENT_PREFIX):
            async with interaction.say() as inf:
                # Open the bracket, then stay silent long enough for a barge-in to
                # land before any audio: heard-truth is empty ⇒ nothing committed.
                await asyncio.sleep(0.5)
                await inf.speak(f"delayed {text[len(SILENT_PREFIX) :]}")
            return

        if text == RAISE:
            # Raise before speaking: no bracket, no text — the core must still
            # complete the interaction so Voice unmutes for the next turn.
            raise ReferenceBrainFault("deliberate fault before any speech")

        if text.startswith(SPEAK_RAISE_PREFIX):
            # Speak a chunk (heard-truth must survive), then raise: the bracket
            # closes, the heard text commits, and the interaction still completes.
            async with interaction.say() as inf:
                await inf.speak(text[len(SPEAK_RAISE_PREFIX) :])
            raise ReferenceBrainFault("deliberate fault after speaking")

        if text.startswith(DO_PREFIX):
            action_name = text[len(DO_PREFIX) :]

            def _record(outcome) -> None:
                self.outcomes.append(
                    {
                        "action_id": outcome.action_id,
                        "status": outcome.status,
                        "result": outcome.result,
                    }
                )

            async with interaction.say() as inf:
                await inf.speak("on it")
                interaction.action(action_name, {"foo": "bar"}, callback=_record)
            return

        async with interaction.say() as inf:
            await inf.speak(f"you said {text}")

    async def on_user_idle(self, interaction) -> None:
        # Voice opened an idle interaction; re-engage with a level-tagged nudge so
        # the driver can assert both the heard text and the escalation level.
        assert interaction.idle is not None  # always set for an idle interaction
        async with interaction.say() as inf:
            await inf.speak(f"{IDLE_NUDGE} {interaction.idle.level}")

    async def on_client_message(self, session, message) -> None:
        # Voice delivers every browser message here with a pre-minted interaction_id
        # and never interprets it — the brain decides what to do with each.
        if message.type == CONFORMANCE_DUMP_EVENT:
            # The conformance backchannel: echo committed state, don't spend the floor.
            session.action(
                CONFORMANCE_STATE_ACTION,
                conformance_state(session, app_events=self.app_events, outcomes=self.outcomes),
            )
            return
        # Record every message as ambient state (the update-internal-state path).
        self.app_events.append({"name": message.type, "data": message.data})
        # Answer the types this brain chooses to respond to, by taking the floor via
        # message.interaction (source == CLIENT_MESSAGE). No user turn is recorded —
        # a client message is not speech — so the committed conversation holds only
        # the assistant's answer.
        if message.type in APP_RESPOND_TYPES:
            async with message.interaction.say() as inf:
                await inf.speak(f"{APP_ACK_PREFIX}{message.type}")
