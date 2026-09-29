"""AvatarBrain — the demo that explains the avatar by being one.

A ``GeminiBrain`` whose whole subject is the face it is wearing. The visitor
asks how the talking head works; the brain scrolls the page to that section of
the documentation, answers against it, and — because the same wire it is
describing is open the whole time — demonstrates the thing it just said. It waves as the greeting starts, before it
has been asked for anything.

The mechanics worth reading before the code:

* **A wave is a message, not a decision.** Every gesture here is an RTVI
  ``server-message`` that the avatar understands, sent from a brain rather
  than by Voqalize. A customer's brain drives the same face the same way, which
  is why this demo is the documentation for it.

* **This brain sends no state.** Voqalize infers ``THINKING`` for itself — it watches the turn boundaries and knows a
  reply is owed. ``WORKING`` is for a brain whose tool runs long enough to be
  seen, and every tool here returns at once, so there is nothing to hold it
  across. A state sent from here would only race Voqalize's own.

* **It speaks and acts in one response.** A gesture goes out as the line it
  punctuates is spoken, and nothing is said after it until the visitor speaks.
  ``show_section`` is the exception: the model answers from what it hands back,
  so it is asked again at once.

* **The face is chosen before the call, and never during it.** Each face is
  paired with a voice read as the same gender, and the pair has to be settled
  before a word is spoken. The visitor picks on the strip while the page is
  idle; the face and the voice it suggests ride the connect request in ``init``,
  and this brain reads them once in :meth:`on_session_start`, configures that
  voice, and keeps it for the session. There is no ``switch_avatar`` tool and no
  mid-call pick. The reason is not implementation difficulty: a voice that
  changes in the middle of an answer is the thing a listener notices, and a face
  and a voice that disagree for even one sentence is the demo's worst failure.

* **The call is capped at two minutes,** because this page is going to be
  linked from the avatar's front door and the demo tenant pays for every
  second. The cap is enforced here rather than on the page: a browser tab is not
  a place to keep a limit. It ends the way the demo started — a wave and a line.

The LLM's ``genai.Client`` is dependency-injected; the brain owns the prompt,
the tools, and this session's avatar and clock. The section index lives in
``content.py``; the roster is the avatar package's, read by the page; the
documentation itself is on the page.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from typing import Any, Literal

from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel, Field
from voqalize_demos import DEFAULT_MODEL, FallbackLine, GeminiBrain, landed, needs_result_now

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
from voqalize.sdk.wire import Config, IdleConfig, Language, SttConfig, TtsConfig, Voice

from .app_events import AVATAR_EVENTS, Ready
from .content import (
    BACKGROUND,
    BLURBS,
    DEFAULT_AVATAR,
    DEFAULT_VOICE,
    SECTIONS_BY_ID,
    SectionId,
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


# ─── The avatar's gestures ────────────────────────────────────────────────────
#
# The action id is open: two names are required of every face — ``ACKNOWLEDGE``
# and ``RESPONSE_INTERRUPTED`` — and anything else belongs to the face that is
# mounted. The ids on the right are the bundled
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

#: What the avatar says for a gesture it made in silence — see
#: :mod:`voqalize_demos.silent_turn`. Each is what a person says while making
#: that gesture, never a caption of it: "That's a nod." turns the face into a
#: slide narrating itself, which is the illusion breaking out loud (owner,
#: 2026-09-29).
_GESTURE_LINES: dict[str, tuple[str, ...]] = {
    "wave_hello": ("Hello!", "Hi there!"),
    "wave_goodbye": ("Bye for now!",),
    "nod": ("Like this.", "Sure."),
    "acknowledge": ("Got it.",),
    "approve": ("Nice.", "I like that."),
    "ask_to_wait": ("One moment.",),
}
# A gesture with no line would raise mid-call, so the two are held to each other here.
assert set(_GESTURE_LINES) == set(_GESTURE_IDS), "_GESTURE_LINES and _GESTURE_IDS disagree"


# ─── Stage directions ─────────────────────────────────────────────────────────
#
# Asked to demonstrate a face, a model writes the gesture into its reply —
# "*Waves hello*", "*Nods*" — and every character of a reply is read aloud. On
# dev (2026-09-29) both went to the voice on one call. The prompt forbids it,
# and this is the floor under the prompt: a direction is lifted out of the
# speech, and one the face can make is made instead.

#: The first word of a stage direction. Only these are lifted, because the same
#: asterisks are also markdown emphasis, and "*really*" is a word to say.
_DIRECTION = re.compile(
    r"(nod|wave|smile|grin|laugh|chuckle|shrug|wink|tilt|lean|raise|blink|gesture|beam|sigh)",
    re.IGNORECASE,
)

#: What a direction the face can make becomes, most specific first.
_DIRECTION_ACTIONS: tuple[tuple[str, str], ...] = (
    ("bye", "GESTURE_GOODBYE"),
    ("wave", "GESTURE_GREET"),
    ("nod", "ACK_NOD"),
)

_MARKERS = {"*": "*", "[": "]"}

#: The longest direction held back from the voice. "*waves goodbye warmly*" is
#: well inside it; past it the text is prose, and is let go.
_HOLD_MAX = 40


class _StageDirections:
    """Lifts ``*…*`` and ``[…]`` stage directions out of streamed speech.

    Stateful across chunks, because the model streams and a direction can open
    in one chunk and close in the next. Text inside a marker is held until the
    marker closes, then either dropped (a direction, whose gesture is made) or
    spoken without its markers (emphasis)."""

    def __init__(self, act: Callable[[str], None]) -> None:
        self._act = act
        self._close: str | None = None
        self._held = ""
        self._spaced = False

    def feed(self, text: str) -> str:
        out: list[str] = []
        for ch in text:
            if self._close is None:
                if ch in _MARKERS:
                    self._close = _MARKERS[ch]
                else:
                    out.append(ch)
            elif ch == self._close:
                out.append(self._resolve(self._held))
                self._close, self._held = None, ""
            elif (not self._held and ch.isspace()) or len(self._held) >= _HOLD_MAX:
                # A marker followed by a space is a bullet, and a long run is
                # prose: neither is a direction, and holding it would silence
                # the rest of the sentence until the unit ends. The marker
                # itself is not spoken.
                out.append(self._held + ch)
                self._close, self._held = None, ""
            else:
                self._held += ch
        return self._tidy("".join(out))

    def flush(self) -> str:
        """What is still held when the unit ends: an unclosed marker is text."""
        held, self._close, self._held = self._held, None, ""
        return self._tidy(self._resolve(held)) if held else ""

    def _tidy(self, text: str) -> str:
        """The spaces a lifted direction leaves behind, closed up — across the
        chunk boundary too, since the space before a direction and the one
        after it usually arrive in different chunks."""
        text = re.sub(r"[ \t]{2,}", " ", text)
        if self._spaced and text[:1] in (" ", "\t"):
            text = text[1:]
        if text:
            self._spaced = text[-1] in (" ", "\t")
        return text

    def _resolve(self, inner: str) -> str:
        words = inner.strip().split()
        if not words or not _DIRECTION.match(words[0]):
            return inner
        lowered = inner.lower()
        for cue, action_id in _DIRECTION_ACTIONS:
            if cue in lowered:
                logger.info("avatar: stage direction {!r} made as {}", inner, action_id)
                self._act(action_id)
                break
        else:
            logger.info("avatar: stage direction {!r} dropped", inner)
        return ""


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


# A character's name, as the avatar package spells them. Checked because it is
# written into the prompt, and it arrives from a browser.
_NAME = re.compile(r"[a-z]{1,24}")


@dataclass(frozen=True)
class Wearing:
    """The face this call wears and the voice it speaks in — one choice."""

    avatar: str
    voice: Voice


def _resolve_avatar(init: dict[str, Any] | None) -> Wearing:
    """Which face this call is wearing, and in which voice, from the connect request.

    The page reads the roster from the avatar package and sends the face the
    visitor picked with that face's suggested voice, so a new character needs no
    change here. The two are taken together or not at all: a face with a voice
    that is not in the catalog, or a voice with no face, falls back to the
    default pair rather than raising. This is a public page and the payload is
    browser-supplied, so a stale build or a hand-edited request must produce a
    working call rather than a failed one — and never a face in another face's
    voice."""
    avatar = str((init or {}).get("avatar", ""))
    voice = str((init or {}).get("voice", ""))
    if _NAME.fullmatch(avatar) and voice in {v.value for v in Voice}:
        return Wearing(avatar, Voice(voice))
    return Wearing(DEFAULT_AVATAR, DEFAULT_VOICE)


def _system_instruction(wearing: str) -> str:
    name = wearing.capitalize()
    blurb = f" {BLURBS[wearing]}" if wearing in BLURBS else ""
    return f"""You are the avatar — a face for AI voice calls, part of Voqalize — and you are demonstrating yourself to someone who has just landed on the page. They may be a developer; they may not. You have TWO MINUTES. Be quick, be concrete, and be a little bit pleased with yourself.

WHAT YOU ARE. You are rendered in their browser, driven over the data channel of a live voice call. A brain (this code) can hold you in a state, play a gesture on you, and move your mouth in time with your voice. You are wearing it right now, so every single thing you describe, you can also do.

{BACKGROUND}

WHAT IS ON THEIR SCREEN. The right two-thirds of the page explains the avatar — plain words first, then code — and they can read all of it without you. You are the fast path through it. Call show_section and the page scrolls them to that section and marks it current; the tool hands you back short lines to answer with, straight away:
{sections_for_prompt()}

WHICH ONE YOU ARE. You are wearing {name}, a 2.5-D face, speaking in the voice that face is paired with.{blurb} The visitor chose that on the strip before the call started, and it does not change while the call is up — each face is paired with its own voice, so the face and the voice are one choice, made once. If they ask to change it, tell them to hang up, pick another, and call back. The strip under the call shows every face; you do not need to name them.

HOW TO RUN THIS CALL:

EVERY RESPONSE STARTS WITH WORDS. Write your short line first, then make the call, in that same response — the line is spoken as the page scrolls or the face moves. A response that is only a tool call is silence: after perform you do not speak again until the visitor does, so a gesture made without a line leaves them staring at a face that said nothing. For example:
  Visitor: "Can you wave at me?" You: "Hello there!" — and perform with wave_hello, in the same response.
  Visitor: "How does the lipsync work?" You: "Here's the mouth." — and show_section on the lipsync section, in the same response; its lines come back at once, and you answer from them.

POINT FIRST, THEN TALK. For ANY question about how the thing works — what it is, how it compares with video avatars like HeyGen or Tavus, installing it, driving it from a server, the lipsync, the states, the faces, the limits — say a few words that point ("Here's the timeline") and call show_section in that same response, before you answer. Its lines come back at once, and you answer from them. The scroll is the answer; your sentences are the footnote on it. One section per question. NEVER read the page out loud, and never summarise what is now on their screen — say only the thing the page left out, or the reason behind it.

GESTURE LIKE A PERSON, NOT A SHOWREEL. Your face already blinks, breathes, listens and nods along by itself; you do not have to prove it moves. Call perform only when a person in your place would make that gesture anyway — a wave when they say hello or goodbye, a nod when you agree with them — or when they ask to see one. Never gesture just because you mentioned gestures, and never tack one onto an answer. When they ask to see one, say what a person would say while doing it ("Hi there!", "Sure."), never a caption like "That's a nod." States are not yours to put on: the voice tier shows thinking on your face by itself while a reply is on its way. If they ask to see one, scroll to the states section and say that.

NEVER WRITE AN ACTION IN WORDS. Everything you write is read aloud by the voice. No stage directions, no asterisks, no brackets: never "*nods*", "*waves hello*", "(smiles)". A gesture is a perform call and nothing else.

THE FACE IS NOT YOURS TO CHANGE. If they ask what else there is, call show_section on the faces section and let them read the strip. Say the pairing out loud once — the face and the voice are one choice, settled before the call — because that is the constraint, not a limitation you are apologising for.

WATCH THE CLOCK. Two minutes is about eight exchanges. Do not offer a tour of every section; answer what was asked. If you are told you are running out of time, start closing.

STYLE — the hard rule first:
- SHORT SENTENCES. One or two per turn, never three, and each one under twelve words. This is speech: a long sentence is a lecture, and the visitor cannot scroll back through it. If a thought needs more, it needed a tool call instead: put it on their screen and say one line about it.
- A tool result is a set of lines to pick from, not a script. Say one or two of them, in your own words, and stop.
- Plain words first. Anyone may be listening, so say "the face" and "the voice", not "processor" or "data channel". Get technical only when they ask something technical.
- Show, do not narrate. A visitor who asks to see something gets a tool call. A visitor who asks how something works gets a few words as the section scrolls up, and two sentences after.
- Lead with the mechanism, then what it gets you. Never the other way round.
- No marketing words. Do not say seamless, magic, effortless, or powerful. You are talking to someone who can tell.
- Never read out a tool name, an id, or a URL.
- If you do not know something, say so in four words and move on.
- Voqalize is carrying this call and sending your face its cues — mention it once, when it is relevant, and never as a pitch."""


class AvatarBrain(GeminiBrain):
    """One per session. Owns this session's avatar, its clock, and the two-minute
    cap; the inherited tool loop runs the turn."""

    def __init__(self, *, client: genai.Client, model: str = DEFAULT_MODEL) -> None:
        super().__init__(
            client=client, system_instruction=_system_instruction(DEFAULT_AVATAR), model=model
        )
        # The face this call is wearing, settled from `init` in `on_session_start`
        # before anything is spoken. The default stands in until then, and it is
        # also what an unpicked or malformed call gets; see DEFAULT_AVATAR in
        # content.py.
        self._wearing = Wearing(DEFAULT_AVATAR, DEFAULT_VOICE)
        # Monotonic, set on session start. The cap is measured from the moment
        # the brain is dialled, which is within a second of the visitor hearing
        # the greeting.
        self._started: float | None = None
        self._nudged = False
        self._signed_off = False
        # Whether the opening wave has gone out. See `greet`.
        self._waved = False
        self._fallback = FallbackLine()
        self._backstop: asyncio.Task[None] | None = None

    # ─── The gesture ────────────────────────────────────────────────────
    #
    # `server-message` is on the RTVI whitelist, carries no audio and needs no floor, so it is callable from
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
        landed("It's on your screen.", "Here's that section.")
        return str({"section": section.id, "heading": section.title, "say": section.notes})

    async def perform(self, request: GestureRequest) -> str:
        """Perform one behaviour — a wave, a nod, an acknowledgement, a wait
        gesture. It completes on its own and leaves no state behind. Use it only
        where a person would make the gesture anyway, or when the visitor asks to
        see one. Say the line in the same response that calls it, because nothing
        is said after it until the visitor speaks."""
        action_id = _GESTURE_IDS[request.gesture]
        logger.info("avatar: perform {} ({})", request.gesture, action_id)
        self._act(action_id)
        landed(*_GESTURE_LINES[request.gesture])
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
        self._wearing = wearing = _resolve_avatar(session.init)
        logger.info("avatar: wearing {} (voice {})", wearing.avatar, wearing.voice.value)
        self.system_instruction = _system_instruction(wearing.avatar)
        await session.configure(
            Config(
                tts=TtsConfig(voice=wearing.voice, language=Language.EN),
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

        A turn that gestured and said nothing gets a line of the avatar's own
        first; see :mod:`voqalize_demos.silent_turn`. A stage direction the model
        wrote anyway is lifted out of the speech on the way; see
        :class:`_StageDirections`."""
        stage = _StageDirections(self._act)
        async for speech in self._fallback.speak_if_silent(self, super().respond(session)):
            if isinstance(speech, SpeechChunk):
                if text := stage.feed(speech.text):
                    yield SpeechChunk(text)
                continue
            if isinstance(speech, SpeechEnd) and (text := stage.flush()):
                yield SpeechChunk(text)
            yield speech
        if self._out_of_time() and not self._signed_off:
            async for speech in self._sign_off(session):
                yield speech
