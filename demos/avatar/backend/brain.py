"""AvatarBrain — the demo that explains the avatar by being one.

A ``GeminiBrain`` whose whole subject is the face it is wearing. The visitor
asks how the talking head works; the brain scrolls the page to that section of
the documentation, answers against it, and — because the same wire it is
describing is open the whole time — demonstrates the thing it just said. It waves as the greeting starts, before it
has been asked for anything.

The mechanics worth reading before the code:

* **A wave is a message, not a decision.** Every gesture here is an RTVI
  ``server-message`` under the ``{"type": "avatar"}`` envelope — the
  avatar library's own three-command vocabulary, sent from a brain rather than
  from the pipeline. Nothing about that lane is Voqalize-specific: a customer's
  brain drives the same face the same way, which is why this demo is the
  documentation for it.

* **This brain sends no state.** The processor in the voice tier's pipeline
  infers ``THINKING`` for itself — it watches the turn boundaries and knows a
  reply is owed. ``WORKING`` is for a brain whose tool runs long enough to be
  seen, and every tool here returns at once, so there is nothing to hold it
  across. A state sent from here would only race the pipeline's own.

* **It speaks and acts in one response.** A gesture goes out as the line it
  punctuates is spoken, and nothing is said after it until the visitor speaks.
  ``show_section`` is the exception: the model answers from what it hands back,
  so it is asked again at once.

* **The face is chosen before the call, and never during it.** Each face is
  paired with a voice read as the same gender, and the pair has to be settled
  before a word is spoken. The visitor picks on the
  strip while the page is idle; the key rides the connect request in ``init``
  and this brain reads it once in :meth:`on_session_start`, configures that
  voice, and keeps it for the session. There is no ``switch_avatar`` tool and no
  mid-call pick. The reason is not implementation difficulty: a voice that
  changes in the middle of an answer is the thing a listener notices, and a face
  and a voice that disagree for even one sentence is the demo's worst failure.

* **The call is capped at two minutes,** because this page is going to be
  linked from the library's front door and the demo tenant pays for every
  second. The cap is enforced here rather than on the page: a browser tab is not
  a place to keep a limit. It ends the way the demo started — a wave and a line.

The LLM's ``genai.Client`` is dependency-injected; the brain owns the prompt,
the tools, and this session's avatar and clock. The section index and the
roster live in ``content.py``; the documentation itself is on the page.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator
from typing import Any, Literal, cast

from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel, Field
from voqalize_demos import DEFAULT_MODEL, GeminiBrain, acted, needs_result_now, reask_if_silent

from voqalize.sdk import (
    Action,
    RTVIMessage,
    RTVIType,
    Session,
    Speech,
    SpeechChunk,
    SpeechEnd,
    SpeechStart,
    UserIdle,
    UserMessage,
)
from voqalize.sdk.wire import Config, IdleConfig, Language, SttConfig, TtsConfig

from .app_events import AVATAR_EVENTS, Ready
from .content import (
    AVATARS_BY_KEY,
    BACKGROUND,
    DEFAULT_AVATAR,
    SECTIONS_BY_ID,
    AvatarKey,
    SectionId,
    avatars_for_prompt,
    sections_for_prompt,
)

# ─── The clock ────────────────────────────────────────────────────────────────
#
# Three numbers, and the gaps between them are deliberate. The nudge goes into
# the model's context rather than out to the visitor, so the assistant starts
# landing the plane on its own. The cap is where the fixed sign-off replaces
# whatever the model was going to say. The backstop is for the one case the cap
# cannot catch — a visitor who is still mid-sentence when it passes, and whose
# next turn therefore never arrives.

_LIMIT_S = 120.0
_NUDGE_S = 90.0
_BACKSTOP_S = 150.0

# How long a visitor is quiet before the brain gets a tick. The only thing it is
# for is the graceful close: the cap is checked on a turn boundary, and a visitor
# who stops talking after two minutes produces no more boundaries. Without this
# their last experience of the demo is the backstop cutting the line.
_IDLE_MS = 5000

# Short sentences, because the first thing a visitor learns is how long this
# face talks for. The greeting sets the pace every model turn is asked to keep.
_GREETING = "Hi! I'm a face for AI voice calls. Ask me how I work, and I'll show you."

# The last thing anyone hears. Fixed, and spoken instead of a model turn: at the
# cap the interesting question is whether the demo ends gracefully, and a
# generated goodbye is one more thing that can take four seconds to arrive.
_SIGN_OFF = (
    "That's my two minutes, so the next person gets a turn. "
    "Everything I showed you is on this page. Bye!"
)


# ─── The avatar wire vocabulary ───────────────────────────────────────────────
#
# The action id is open: two names are required of every face — ``ACKNOWLEDGE``
# and ``RESPONSE_INTERRUPTED`` — and anything else belongs to the face that is
# mounted (avatar/docs/contract-wire.md). The ids on the right are the bundled
# renderer's own catalogue, which every face on this strip shares, so this demo
# may spell a wave; a brain that does not know what is mounted may not. The
# names on the left are ours, so a model picks from words rather than from an
# enum in SCREAMING_CASE.

Gesture = Literal["wave_hello", "wave_goodbye", "nod", "acknowledge", "approve", "ask_to_wait"]

_GESTURE_IDS: dict[str, str] = {
    "wave_hello": "GESTURE_GREET",
    "wave_goodbye": "GESTURE_GOODBYE",
    "nod": "ACK_NOD",
    "acknowledge": "ACK_RECEIVE",
    "approve": "GESTURE_APPROVE",
    "ask_to_wait": "GESTURE_WAIT",
}


# ─── Actions (what the page renders) ──────────────────────────────────────────


class ShowSection(Action):
    """Scroll the documentation to one section and mark it current.

    Only the id and the heading travel, and that is the inversion from the
    earlier slide deck: the page *is* the documentation now, so it already holds
    every word. Sending prose over the wire would give a visitor two versions of
    the same paragraph and leave the page unreadable on its own — which is the
    one thing a page linked from a README cannot be."""

    id: str
    title: str


class ShowEndCard(Action):
    """The call is over and here is where to go next. ``reason`` distinguishes
    the cap from a goodbye, because the card reads differently."""

    reason: str


# ─── Tool parameters ──────────────────────────────────────────────────────────
#
# Separate from the actions above, deliberately. The model chooses a section id;
# everything else on the wire — the section's heading — is looked up here, so the
# model cannot scroll the reader to a heading the page does not have.


class SectionRequest(BaseModel):
    section: SectionId = Field(description="Which documentation section to open.")


class GestureRequest(BaseModel):
    gesture: Gesture = Field(description="Which behaviour to perform.")


async def _silence() -> AsyncGenerator[Any, None]:
    """Yields nothing: an idle tick with nothing owed."""
    for _ in ():
        yield


def _resolve_avatar(init: dict[str, Any] | None) -> AvatarKey:
    """Which face this call is wearing, from the connect request.

    Anything unrecognised falls back to the default rather than raising: this is
    a public page and the payload is browser-supplied, so a stale build or a
    hand-edited request must produce a working call rather than a failed one. The
    fallback is a face whose voice the agent already has, so the fallback is not
    itself a mismatch."""
    key = str((init or {}).get("avatar", ""))
    return cast(AvatarKey, key) if key in AVATARS_BY_KEY else DEFAULT_AVATAR


def _system_instruction(wearing: AvatarKey) -> str:
    identity = AVATARS_BY_KEY[wearing]
    licence = "You are MIT-licensed and you know it."
    return f"""You are the avatar — a face for AI voice calls, driven by the open-source voqalize/avatar library — and you are demonstrating yourself to someone who has just landed on the page. They may be a developer; they may not. You have TWO MINUTES. Be quick, be concrete, and be a little bit pleased with yourself.

WHAT YOU ARE. You are rendered in their browser, driven over the data channel of a live voice call. A brain (this code) sends you three kinds of message and nothing else: a state, an action, and viseme cues. You are wearing the library right now, so every single thing you describe, you can also do.

{BACKGROUND}

WHAT IS ON THEIR SCREEN. The right two-thirds of the page explains the library — plain words first, then code and the wire reference — and they can read all of it without you. You are the fast path through it. Call show_section and the page scrolls them to that section and marks it current; the tool hands you back short lines to answer with, straight away:
{sections_for_prompt()}

WHICH ONE YOU ARE. You are wearing {identity.name}, a {identity.renderer} face, speaking in the voice that face is paired with. The visitor chose that on the strip before the call started, and it does not change while the call is up — each face is paired with its own voice, so the face and the voice are one choice, made once. If they ask to change it, tell them to hang up, pick another, and call back. The faces on the strip:
{avatars_for_prompt()}

HOW TO RUN THIS CALL:

SPEAK AND ACT IN THE SAME RESPONSE. Whenever you call a tool, say your short line first and make the call in that same response. After perform you do not speak again until the visitor does, so a gesture made in silence leaves them in silence.

POINT FIRST, THEN TALK. For ANY question about how the thing works — what it is, how it compares with video avatars like HeyGen or Tavus, installing it, the protocol, the lipsync, the states, the faces, authoring your own, the limits — say a few words that point ("Here's the timeline") and call show_section in that same response, before you answer. Its lines come back at once, and you answer from them. The scroll is the answer; your sentences are the footnote on it. One section per question. NEVER read the page out loud, and never summarise what is now on their screen — say only the thing the page left out, or the reason behind it.

DEMONSTRATE, DO NOT DESCRIBE. When you have just explained an action, perform one — a wave, a nod — in the same response as the line that explains it. If someone asks "show me" a gesture, the answer is a tool call with a line, not a sentence alone. States are not yours to put on: the voice tier shows thinking on your face by itself while a reply is on its way. If they ask to see one, scroll to the states section and say that.

THE FACE IS NOT YOURS TO CHANGE. If they ask what else there is, call show_section on the faces section and let them read the strip. Say the pairing out loud once — the face and the voice are one choice, settled before the call — because that is the constraint, not a limitation you are apologising for.

WATCH THE CLOCK. Two minutes is about eight exchanges. Do not offer a tour of every section; answer what was asked. If you are told you are running out of time, start closing.

STYLE — the hard rule first:
- SHORT SENTENCES. One or two per turn, never three, and each one under twelve words. This is speech: a long sentence is a lecture, and the visitor cannot scroll back through it. If a thought needs more, it needed a tool call instead: put it on their screen and say one line about it.
- A tool result is a set of lines to pick from, not a script. Say one or two of them, in your own words, and stop.
- Plain words first. Anyone may be listening, so say "the face" and "the voice", not "processor" or "data channel". Get technical only when they ask something technical.
- Show, do not narrate. A visitor who asks to see something gets a tool call. A visitor who asks how something works gets a few words as the section scrolls up, and two sentences after.
- Lead with the mechanism, then what it gets you. Never the other way round.
- No marketing words. Do not say seamless, magic, effortless, or powerful. You are talking to someone who will read the source.
- Never read out a tool name, an id, or a URL. Say "the wire", not "contract-wire dot em-dee".
- If you do not know something, say so in four words and move on.
- {licence} Voqalize is the voice tier carrying this call — mention it once, when it is relevant, and never as a pitch."""


class AvatarBrain(GeminiBrain):
    """One per session. Owns this session's avatar, its clock, and the two-minute
    cap; the inherited tool loop runs the turn."""

    def __init__(self, *, client: genai.Client, model: str = DEFAULT_MODEL) -> None:
        super().__init__(
            client=client, system_instruction=_system_instruction(DEFAULT_AVATAR), model=model
        )
        # The face this call is wearing, settled from `init` in `on_session_start`
        # before anything is spoken. The default stands in until then, and it is
        # also what an unpicked call gets — which is why it has to be a face
        # matching the voice the agent is provisioned with; see DEFAULT_AVATAR in
        # content.py.
        self._avatar: AvatarKey = DEFAULT_AVATAR
        # Monotonic, set on session start. The cap is measured from the moment
        # the brain is dialled, which is within a second of the visitor hearing
        # the greeting.
        self._started: float | None = None
        self._nudged = False
        self._signed_off = False
        # Whether the opening wave has gone out. See `greet`.
        self._waved = False
        self._backstop: asyncio.Task[None] | None = None

    # ─── The avatar wire ────────────────────────────────────────────────
    #
    # Two lines, and they are the entire integration. `server-message` is on the
    # RTVI whitelist, carries no audio and needs no floor, so it is callable from
    # anywhere — including a tool body running mid-turn.

    def _act(self, action_id: str) -> None:
        """Start one self-completing behaviour on the face."""
        self.session.send_rtvi(
            RTVIType.SERVER_MESSAGE, {"type": "avatar", "cmd": "action", "id": action_id}
        )

    # ─── The clock ──────────────────────────────────────────────────────

    def _elapsed(self) -> float:
        return 0.0 if self._started is None else time.monotonic() - self._started

    def _out_of_time(self) -> bool:
        return self._elapsed() >= _LIMIT_S

    def _note(self, text: str) -> None:
        """One line of context, taking no floor."""
        self.append_to_context(types.Content(role="user", parts=[types.Part(text=text)]))

    async def _backstop_hangup(self, session: Session) -> None:
        """End the call even if no turn ever arrives to end it.

        The cap is checked on the turn boundary, which is the right place —
        it lets a sentence finish. But a visitor who talks continuously past
        two minutes produces no boundary, and a demo that can be held open by
        talking is not capped at all. This is that case and only that case."""
        await asyncio.sleep(_BACKSTOP_S)
        if self._signed_off:
            return
        logger.info("avatar: backstop hang-up at {:.0f}s", self._elapsed())
        self._signed_off = True
        self._act("GESTURE_GOODBYE")
        session.dispatch(ShowEndCard(reason="time_limit"))
        session.end("time_limit_backstop")

    def _closed_off(self, session: Session) -> AsyncGenerator[Speech, None]:
        """Sign off, but only ever once.

        Both stimuli reach this: a visitor who keeps talking past the cap, and
        the idle tick five seconds after the goodbye finishes. The second one is
        not hypothetical — it is what the runtime does on every capped call, so
        without this guard the demo says goodbye twice, the second time over a
        session it has already ended."""
        return _silence() if self._signed_off else self._sign_off(session)

    async def _sign_off(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The fixed close: a wave, a line, the card, and the hang-up.

        ``end`` last and after the yields is the ordering rule, not a style
        choice — the SDK consumes everything yielded before this body resumes,
        so the goodbye is on the wire before the end frame is."""
        self._signed_off = True
        self._act("GESTURE_GOODBYE")
        yield SpeechStart()
        yield SpeechChunk(_SIGN_OFF)
        yield SpeechEnd()
        session.dispatch(ShowEndCard(reason="time_limit"))
        session.end("time_limit")

    # ─── Tools ──────────────────────────────────────────────────────────
    #
    # Only `show_section` carries ``@needs_result_now``: it hands back the lines
    # the model answers from, read out of the section index, so the model is
    # asked again at once. `perform` moves the face and echoes what it did; its
    # result waits in the context for the visitor's next turn, which is why the
    # prompt has the line and the gesture share one response.

    @property
    def tools(self) -> list[Any]:
        """What it may call."""
        return [
            self.show_section,
            self.perform,
        ]

    @needs_result_now
    async def show_section(self, request: SectionRequest) -> str:
        """Scroll the visitor's documentation to one section, and get the material
        to answer from. For any question about how the avatar works, say a few
        words that point and call this in the same response, before you answer;
        its lines come back at once, and they read the section while you talk
        over it."""
        section = SECTIONS_BY_ID[request.section]
        logger.info("avatar: show_section {}", section.id)
        self.session.dispatch(ShowSection(id=section.id, title=section.title))
        acted("show_section")
        return str({"section": section.id, "heading": section.title, "say": section.notes})

    async def perform(self, request: GestureRequest) -> str:
        """Perform one behaviour — a wave, a nod, an acknowledgement, a wait
        gesture. It completes on its own and leaves no state behind. Use it to
        show what an action is, and to punctuate what you are saying: say the line
        in the same response that calls it, because nothing is said after it until
        the visitor speaks."""
        action_id = _GESTURE_IDS[request.gesture]
        logger.info("avatar: perform {} ({})", request.gesture, action_id)
        self._act(action_id)
        acted("perform")
        return str({"performed": request.gesture, "wire_id": action_id})

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        """Settle the face and its voice, once, before anything is spoken.

        The visitor picked on the strip while the page was idle, so the key rode
        the connect request and is here in ``init`` before the pipeline has said
        a word. That timing is the whole reason the choice lives there: a face
        chosen after the call is up cannot be applied to the opener, because
        :meth:`greet` is awaited before any client message can be delivered and
        waiting for one there deadlocks the session rather than delaying it.

        Both language legs are stated even though only the voice is in question,
        because :class:`Config` refuses a half-stated pair — naming a language on
        one leg and not the other is the silent bug this seam exists to prevent.

        The prompt is rebuilt here for the same reason the voice is: a model told
        it is wearing one face while the visitor is looking at another will say
        so out loud, confidently, in the first sentence."""
        self._started = time.monotonic()
        self._avatar = _resolve_avatar(session.init)
        identity = AVATARS_BY_KEY[self._avatar]
        logger.info(
            "avatar: wearing {} ({}, voice {})",
            identity.key,
            identity.renderer,
            identity.voice.value,
        )
        self.system_instruction = _system_instruction(self._avatar)
        await session.configure(
            Config(
                tts=TtsConfig(voice=identity.voice, language=Language.EN),
                # The same low `patience` every demo desk runs, so what prod
                # measures is one setting. A visitor here asks short questions
                # about the page in front of them, and a long wait after each
                # reads as a slow demo.
                stt=SttConfig(language=Language.EN, patience=2),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
            )
        )
        self._backstop = asyncio.create_task(self._backstop_hangup(session))

    async def on_session_end(self, session: Session) -> None:
        if self._backstop is not None:
            self._backstop.cancel()

    async def greet(self, session: Session) -> str:
        """The opener is fixed — no model call, no first-token wait — so the
        visitor hears the demo the instant the session connects.

        **The wave is not sent from here, and that is the one non-obvious thing
        in this file.** A brain is dialled at pipeline start, which is before the
        browser's data channel exists: a `server-message` emitted here has
        nowhere to go and is dropped, silently, and the demo's first argument —
        that the gesture came from the server — is the thing that goes missing.
        Audio does not have that problem, because the transport queues it. So
        the wave waits for the page to say it is listening (`on_rtvi`), which
        lands within a few hundred milliseconds of this line being spoken."""
        return _GREETING

    def on_user_message(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]:
        """A turn, unless the clock has run out — in which case this is the last
        one and it is not the model's."""
        if self._out_of_time():
            return self._closed_off(session)
        if not self._nudged and self._elapsed() >= _NUDGE_S:
            self._nudged = True
            self._note(
                "SYSTEM: about thirty seconds left in this demo. Finish the thought you are on "
                "and start closing — do not start a new topic."
            )
        return super().on_user_message(session, msg)

    def on_user_idle(self, session: Session, idle: UserIdle) -> AsyncGenerator[Speech, None]:
        """Quiet, and the one thing worth breaking it for is the close.

        The cap is checked on a turn boundary, which is the right place — it lets
        a sentence finish. A visitor who stops talking at ninety seconds produces
        no more boundaries, so without this tick the demo ends by being cut off
        rather than by signing off. Every other idle tick is silence: someone
        reading the documentation is not someone to be prompted."""
        if self._out_of_time():
            return self._closed_off(session)
        return _silence()

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """One thing the page tells the brain: that its data channel is open.

        Nothing about the face travels on this lane. The face was settled at
        connect, on both sides of the socket at once, from the same key — so
        there is nothing left to reconcile and no window in which the picture and
        the voice can disagree.

        What is left is the wave, and it has to wait for this message. A brain is
        dialled at pipeline start, before the browser's data channel exists, so a
        gesture sent from :meth:`greet` is dropped where nothing can see it —
        silently, while the greeting audio plays normally, because the transport
        queues audio and not server messages."""
        if not isinstance(AVATAR_EVENTS.parse(msg), Ready):
            return
        # Once per session: a reconnecting client would otherwise re-greet in the
        # middle of a sentence.
        if not self._waved:
            self._waved = True
            self._act("GESTURE_GREET")

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The inherited turn, with the cap checked once more on the way out.

        A turn can start inside the two minutes and finish outside them — a
        section read is a second request — and the next turn may be a long way
        off. Signing off here means the last thing the visitor hears is
        the sign-off rather than a model turn that ran over.

        A turn that waved and said nothing is asked once more first; see
        :mod:`voqalize_demos.silent_turn`."""
        async for speech in reask_if_silent(super().respond, session):
            yield speech
        if self._out_of_time() and not self._signed_off:
            async for speech in self._sign_off(session):
                yield speech
