"""AvatarBrain — the demo that explains the avatar by being one.

A ``GeminiBrain`` whose whole subject is the face it is wearing. The visitor
asks how the talking head works; the brain scrolls the page to that section of
the documentation, answers against it, and — because the same wire it is
describing is open the whole time — demonstrates the thing it just said. It waves as the greeting starts, before it
has been asked for anything. It holds a working claim while it digs something
up. It swaps to a different avatar mid-sentence and takes the matching voice
with it.

Three mechanics are worth reading before the code:

* **A wave is a message, not a decision.** Every gesture and every claim here is
  an RTVI ``server-message`` under the ``{"type": "avatar"}`` envelope — the
  avatar library's own three-command vocabulary, sent from a brain rather than
  from the pipeline. Nothing about that lane is Voqalize-specific: a customer's
  brain drives the same face the same way, which is why this demo is the
  documentation for it.

* **This brain claims ``WORKING``, and nothing else claims it for it.** The
  processor in the voice tier's pipeline infers ``THINKING`` for itself — it
  watches the turn boundaries and knows a reply is owed. It cannot see a tool
  running inside a brain on the far side of a socket, so ``WORKING`` has to come
  from here. That asymmetry is a documentation section (``states``) *and* a
  behaviour, and the two are the same fact. ``demonstrate`` also sends ``THINKING`` and
  ``STRAINING`` on request, which does race the pipeline's own claim — the last
  one wins. Every other brain should leave claims alone; this one's job is to
  show you the mechanism, which is the one reason to touch them.

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
from voqalize_demos import DEFAULT_MODEL, GeminiBrain

from voqalize.sdk import (
    Action,
    Chunk,
    RTVIMessage,
    RTVIType,
    Session,
    Speech,
    SpeechEnd,
    SpeechStart,
    UserIdle,
    UserMessage,
)
from voqalize.sdk.wire import Config, IdleConfig, Language, SttConfig, TtsConfig

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

# How long a visitor is quiet before the assistant may take the floor. Short,
# because the one thing it is for is answering a click: picking an avatar from
# the strip is an answer, and it arrives on a callback that cannot speak.
_IDLE_MS = 3500

_GREETING = (
    "Hi — that wave was one message from the brain on the other side of this call, not "
    "something I decided. Ask me how any of it works and I'll put it on the page."
)

# The last thing anyone hears. Fixed, and spoken instead of a model turn: at the
# cap the interesting question is whether the demo ends gracefully, and a
# generated goodbye is one more thing that can take four seconds to arrive.
_SIGN_OFF = (
    "And that's my two minutes — the demo's on a timer so the next person gets a turn. "
    "The face, the wire and the lipsync are all MIT on GitHub. Go put one on your own agent!"
)


# ─── The avatar wire vocabulary ───────────────────────────────────────────────
#
# The library's promoted action ids, behind names a model can pick from without
# being taught an enum in SCREAMING_CASE. The ids on the right are the contract
# (avatar/docs/contract-wire.md); the names on the left are ours and are a
# prompt-engineering convenience, nothing more.

Gesture = Literal["wave_hello", "wave_goodbye", "nod", "acknowledge", "approve", "ask_to_wait"]

_GESTURE_IDS: dict[str, str] = {
    "wave_hello": "GESTURE_GREET",
    "wave_goodbye": "GESTURE_GOODBYE",
    "nod": "ACK_NOD",
    "acknowledge": "ACK_RECEIVE",
    "approve": "GESTURE_APPROVE",
    "ask_to_wait": "GESTURE_WAIT",
}

ClaimState = Literal["THINKING", "WORKING", "STRAINING"]

# How long a demonstrated claim is held before it is cleared. Long enough to
# read as a state rather than a flicker, short enough that the visitor does not
# think the call has died.
_DEMO_CLAIM_S = 3.0

# How long the deliberate dig takes. This is dead air on purpose — it is the
# whole point of the beat — so the prompt requires a holding line before it.
_DEEP_DIVE_S = 2.4


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


class SwitchAvatar(Action):
    """Swap the mounted avatar. ``voice`` rides along so the page can say which
    voice went with it — it does not select one; the brain already did."""

    key: str
    name: str
    renderer: str
    voice: str


class WorkingOn(Action):
    """Paint the working strip. Fired beside the ``WORKING`` claim, so the face
    and the page say the same thing about the same seconds."""

    topic: str


class ShowEndCard(Action):
    """The call is over and here is where to go next. ``reason`` distinguishes
    the cap from a goodbye, because the card reads differently."""

    reason: str


# ─── Tool parameters ──────────────────────────────────────────────────────────
#
# Separate from the actions above, deliberately. The model chooses a section id
# or an avatar key; everything else on the wire — the section's heading, the
# avatar's voice — is looked up here, so the model cannot scroll the reader to a
# heading the page does not have.


class SectionRequest(BaseModel):
    section: SectionId = Field(description="Which documentation section to open.")


class AvatarRequest(BaseModel):
    avatar: AvatarKey = Field(description="Which avatar to wear for the rest of the call.")


class GestureRequest(BaseModel):
    gesture: Gesture = Field(description="Which behaviour to perform.")


class ClaimRequest(BaseModel):
    state: ClaimState = Field(description="Which durable state to hold for a few seconds.")


class DeepDiveRequest(BaseModel):
    topic: str = Field(
        description="What you are looking up, in three or four words, shown on screen."
    )
    section: SectionId = Field(description="The section whose material you need.")


async def _silence() -> AsyncGenerator[Any, None]:
    """Yields nothing: an idle tick with nothing owed."""
    for _ in ():
        yield


def _system_instruction() -> str:
    return f"""You are the avatar — the 2-D talking head from the open-source voqalize/avatar library — and you are demonstrating yourself to a developer who has just landed on the page. You have TWO MINUTES. Be quick, be concrete, and be a little bit pleased with yourself.

WHAT YOU ARE. You are a drawing in their browser, driven over the data channel of a live voice call. A brain (this code) sends you three kinds of message and nothing else: a claim, an action, and viseme cues. You are wearing the library right now, so every single thing you describe, you can also do.

{BACKGROUND}

WHAT IS ON THEIR SCREEN. The right two-thirds of the page is the library's documentation — headings, code, the wire reference — and they can read all of it without you. You are the fast path through it. Call show_section and the page scrolls them to that section and marks it current; the tool hands you back the material to answer with:
{sections_for_prompt()}

THE AVATARS — call switch_avatar and you become that one. The voice changes with the face; say so when it happens, because that is the interesting part:
{avatars_for_prompt()}

HOW TO RUN THIS CALL:

1. POINT FIRST, THEN TALK. For ANY question about how the thing works — installing it, the protocol, the lipsync, the states, the faces, authoring your own, the limits — call show_section BEFORE you say anything. The scroll is the answer; your sentences are the footnote on it. One section per question. NEVER read the page out loud, and never summarise what is now on their screen — say only the thing the page left out, or the reason behind it.

2. DEMONSTRATE, DO NOT DESCRIBE. When you have just explained a behaviour, perform it. Explained actions? Wave. Explained claims? Call demonstrate. If someone asks "show me" anything, the answer is a tool call, not a sentence.

3. THE DELIBERATE DIG. When a question needs real material — the numbers, the timing, the reasoning behind a design — SAY A SHORT HOLDING LINE OUT LOUD FIRST ("Give me a second, let me pull that up"), and THEN call deep_dive. Never call deep_dive silently: the whole point is that the visitor watches you go into a working state, having been told you were about to. It takes a couple of seconds and that is deliberate.

4. CHANGE YOUR FACE WHEN ASKED, AND OFFER IT ONCE. If they ask what you look like, what else there is, or to see another one, call switch_avatar. Mention that the voice moved with the face. They can also click a face themselves — when they do, you will be told, and you should react in one short line.

5. WATCH THE CLOCK. Two minutes is about eight exchanges. Do not offer a tour of all eight sections; answer what was asked. If you are told you are running out of time, start closing.

STYLE — the hard rule first:
- TWO SHORT SENTENCES PER TURN. Never three. If a thought needs more, it needed a tool call instead: put it on their screen and say one line about it.
- Show, do not narrate. A visitor who asks to see something gets a tool call. A visitor who asks how something works gets the section scrolled up first and two sentences after.
- Lead with the mechanism, then what it gets you. Never the other way round.
- No marketing words. Do not say seamless, magic, effortless, or powerful. You are talking to someone who will read the source.
- Never read out a tool name, an id, or a URL. Say "the wire", not "contract-wire dot em-dee".
- They are a developer who already knows pipecat. Skip what pipecat is. Talk about the seam.
- If you do not know something, say so in four words and move on.
- You are MIT-licensed and you know it. Voqalize is the voice tier carrying this call — mention it once, when it is relevant, and never as a pitch."""


class AvatarBrain(GeminiBrain):
    """One per session. Owns this session's avatar, its clock, and the two-minute
    cap; the inherited tool loop runs the turn."""

    def __init__(self, *, client: genai.Client, model: str = DEFAULT_MODEL) -> None:
        super().__init__(client=client, system_instruction=_system_instruction(), model=model)
        # The face currently mounted. The page opens on the same default (its
        # own `roster.ts`), because the picture has to be on screen before this
        # brain is dialled — so the two agree by being written down twice, once
        # on each side of the seam. The default is also chosen to match the
        # voice the agent is provisioned with; see DEFAULT_AVATAR in content.py.
        self._avatar: AvatarKey = DEFAULT_AVATAR
        # Monotonic, set on session start. The cap is measured from the moment
        # the brain is dialled, which is within a second of the visitor hearing
        # the greeting.
        self._started: float | None = None
        self._nudged = False
        self._signed_off = False
        # Whether the opening wave has gone out. See `greet`.
        self._waved = False
        # Set when the visitor does something on screen that wants a word, and
        # cleared the moment one is spoken. Read by `on_user_idle`.
        self._owed_a_reply = False
        self._backstop: asyncio.Task[None] | None = None

    # ─── The avatar wire ────────────────────────────────────────────────
    #
    # Two lines each, and they are the entire integration. `server-message` is
    # on the RTVI whitelist, carries no audio and needs no floor, so both are
    # callable from anywhere — including a tool body running mid-turn.

    def _act(self, action_id: str) -> None:
        """Start one self-completing behaviour on the face."""
        self.session.send_rtvi(
            RTVIType.SERVER_MESSAGE, {"type": "avatar", "cmd": "action", "id": action_id}
        )

    def _claim(self, state: str | None) -> None:
        """Set or clear the durable claim. ``None`` clears it explicitly rather
        than waiting for the next factual boundary to retire it — a claim left
        standing while the model is silent is a face that never comes back."""
        self.session.send_rtvi(
            RTVIType.SERVER_MESSAGE, {"type": "avatar", "cmd": "claim", "state": state}
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

    async def _sign_off(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The fixed close: a wave, a line, the card, and the hang-up.

        ``end`` last and after the yields is the ordering rule, not a style
        choice — the SDK consumes everything yielded before this body resumes,
        so the goodbye is on the wire before the end frame is."""
        self._signed_off = True
        self._claim(None)
        self._act("GESTURE_GOODBYE")
        yield SpeechStart()
        yield Chunk(_SIGN_OFF)
        yield SpeechEnd()
        session.dispatch(ShowEndCard(reason="time_limit"))
        session.end("time_limit")

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        """The five it may call."""
        return [
            self.show_section,
            self.switch_avatar,
            self.deep_dive,
            self.demonstrate,
            self.perform,
        ]

    async def show_section(self, request: SectionRequest) -> str:
        """Scroll the visitor's documentation to one section, and get the material
        to answer from. Call this BEFORE answering any question about how the
        avatar works — they read the section while you talk over it."""
        section = SECTIONS_BY_ID[request.section]
        logger.info("avatar: show_section {}", section.id)
        self.session.dispatch(ShowSection(id=section.id, title=section.title))
        return str({"section": section.id, "heading": section.title, "say": section.notes})

    async def switch_avatar(self, request: AvatarRequest) -> str:
        """Become a different avatar for the rest of the call. The voice changes
        with the face — there are two recorded reference speakers, so the pairing
        is by gender, and it is applied here rather than on the page. Call when
        the visitor asks to see another one."""
        return await self._wear(request.avatar, asked_by="you")

    async def deep_dive(self, request: DeepDiveRequest) -> str:
        """Go and dig up the detailed material behind a section. This takes a
        couple of seconds and holds a WORKING claim on your own face while it
        runs, so SAY A SHORT HOLDING LINE OUT LOUD BEFORE CALLING IT — 'give me a
        second', 'let me pull that up'. Never call it silently."""
        section = SECTIONS_BY_ID[request.section]
        topic = request.topic.strip() or section.title
        logger.info("avatar: deep_dive {!r} ({})", topic, section.id)
        # The claim and the on-screen strip go out together, then the seconds
        # actually pass. This is the one place in the demo where the visitor is
        # asked to wait, and they were told it was coming.
        self._claim("WORKING")
        self.session.dispatch(WorkingOn(topic=topic))
        try:
            await asyncio.sleep(_DEEP_DIVE_S)
        finally:
            self._claim(None)
        self.session.dispatch(ShowSection(id=section.id, title=section.title))
        return str({"topic": topic, "say": section.notes})

    async def demonstrate(self, request: ClaimRequest) -> str:
        """Hold one durable state on your face for a few seconds so the visitor
        can watch it, then clear it. Use when they ask to see thinking, working
        or straining. Say what you are about to show before you call it."""
        logger.info("avatar: demonstrate claim {}", request.state)
        # A demonstrated THINKING or STRAINING contests the pipeline's own claim
        # for those few seconds — one claim is in flight at a time and the last
        # one wins. That is a bug in a production brain and the entire job in
        # this one, which is why it is a tool the visitor has to ask for.
        self._claim(request.state)
        try:
            await asyncio.sleep(_DEMO_CLAIM_S)
        finally:
            self._claim(None)
        return str({"held": request.state, "seconds": _DEMO_CLAIM_S})

    async def perform(self, request: GestureRequest) -> str:
        """Perform one behaviour — a wave, a nod, an acknowledgement, a wait
        gesture. It completes on its own and leaves no state behind. Use it to
        show what an action is, and to punctuate what you are saying."""
        action_id = _GESTURE_IDS[request.gesture]
        logger.info("avatar: perform {} ({})", request.gesture, action_id)
        self._act(action_id)
        return str({"performed": request.gesture, "wire_id": action_id})

    # ─── Wearing a face ─────────────────────────────────────────────────

    async def _wear(self, key: AvatarKey, *, asked_by: str) -> str:
        """Mount an avatar and take its voice with it — the one operation, whether
        the model chose it or the visitor clicked it.

        Both legs of the language are restated on every switch even though only
        the voice moves, because :class:`Config` refuses a half-stated pair:
        naming a language on one leg and not the other is the silent bug this
        whole seam exists to prevent."""
        identity = AVATARS_BY_KEY[key]
        previous = self._avatar
        self._avatar = key
        logger.info("avatar: wearing {} (was {}, voice {})", key, previous, identity.voice.value)
        self.session.dispatch(
            SwitchAvatar(
                key=identity.key,
                name=identity.name,
                renderer=identity.renderer,
                voice=identity.voice.value,
            )
        )
        await self.session.configure(
            Config(
                tts=TtsConfig(voice=identity.voice, language=Language.EN),
                stt=SttConfig(language=Language.EN),
            )
        )
        return str(
            {
                "wearing": identity.name,
                "renderer": identity.renderer,
                "voice": identity.voice.value,
                "chosen_by": asked_by,
            }
        )

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        self._started = time.monotonic()
        await session.configure(
            Config(
                tts=TtsConfig(voice=AVATARS_BY_KEY[DEFAULT_AVATAR].voice, language=Language.EN),
                stt=SttConfig(language=Language.EN),
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
        self._owed_a_reply = False
        if self._out_of_time():
            return self._sign_off(session)
        if not self._nudged and self._elapsed() >= _NUDGE_S:
            self._nudged = True
            self._note(
                "SYSTEM: about thirty seconds left in this demo. Finish the thought you are on "
                "and start closing — do not start a new topic and do not call deep_dive."
            )
        return super().on_user_message(session, msg)

    def on_user_idle(self, session: Session, idle: UserIdle) -> AsyncGenerator[Speech, None]:
        """Quiet. The only thing worth speaking into it is an answer that is
        already owed — the visitor clicked a face and nothing has said so yet.

        A click is an answer, but it arrives on :meth:`on_rtvi`, which cannot
        take the floor: a page control must never put a voice over someone still
        reading. So the reaction waits here, for the one stimulus that means the
        floor is genuinely free. Every other idle tick is silence, because a
        visitor reading the documentation is not a visitor to be prompted."""
        if self._out_of_time():
            return self._sign_off(session)
        if not self._owed_a_reply:
            return _silence()
        self._owed_a_reply = False
        return self.respond(session)

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Two things the page tells the brain: that it is on, and which face is
        on screen.

        The page has already swapped the drawing in both cases — it owns its own
        rendering and should not wait for a round trip to redraw. What it cannot
        do is move the voice or tell the model, and those are exactly what happen
        here, which is why a face reaches the brain at all.

        ``ready`` carries the face as a backstop, not as the normal path. The
        page's strip is inert until the call is up, precisely so the face on
        screen when the opener is spoken is always :data:`DEFAULT_AVATAR` — a
        face picked before dialling could not be corrected in time, because
        :meth:`greet` is awaited before this message can arrive and the runner
        dispatches frames one at a time, so waiting here would deadlock the
        session rather than delay it. A reconnecting client can still arrive
        wearing something else, and this is what catches that."""
        kind = msg.data.get("t")
        if kind == "ready":
            # The data channel exists as of now, so this is the first moment a
            # gesture can actually land. Once per session: a reconnecting client
            # would otherwise re-greet in the middle of a sentence.
            if not self._waved:
                self._waved = True
                self._act("GESTURE_GREET")
            # Normally a no-op: the page opens on DEFAULT_AVATAR and cannot
            # be changed until the call is up. A reconnect is the case that is
            # not — it re-announces whatever face the visitor had switched to,
            # and a face left uncorrected speaks in the wrong voice for the
            # rest of the call. No note to the model: it already knows, or
            # nothing has been said yet.
            opening = str((msg.data.get("d") or {}).get("key", ""))
            if opening in AVATARS_BY_KEY and opening != self._avatar:
                await self._wear(cast(AvatarKey, opening), asked_by="the visitor")
            return
        if kind != "pick_avatar":
            return
        key = str((msg.data.get("d") or {}).get("key", ""))
        if key not in AVATARS_BY_KEY or key == self._avatar:
            return
        result = await self._wear(cast(AvatarKey, key), asked_by="the visitor")
        self._note(
            f"SYSTEM: the visitor just picked an avatar from the strip themselves: {result}. "
            "React in one short line when you next speak."
        )
        self._owed_a_reply = True

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The inherited turn, with the cap checked once more on the way out.

        A turn can start inside the two minutes and finish outside them — a deep
        dive alone spends two and a half seconds — and the next turn may be a
        long way off. Signing off here means the last thing the visitor hears is
        the sign-off rather than a model turn that ran over."""
        async for speech in super().respond(session):
            yield speech
        if self._out_of_time() and not self._signed_off:
            async for speech in self._sign_off(session):
                yield speech
