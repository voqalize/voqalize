"""MarketingBrain — Tanya, the agent embedded in the Voqalize homepage.

The page is the product demo. So this brain's job is not to describe Voqalize; it
is to *use* Voqalize on the page the visitor is already reading — scroll them to
the band that answers their question, put a line of light on the element that
carries it, and say the one sentence the page left out.

Three things shape every decision here.

**It points more than it talks.** The homepage has already written the pitch, at
length, better than any turn of speech will. Reading it aloud is the failure mode;
:meth:`MarketingBrain.point_at`, called in the same breath as the one sentence she
says, is the whole discipline, and the style block below spends most of its words
enforcing it.

**Knowledge is two-tier.** ``knowledge/L1.md`` is compiled into the system
instruction — dense, fragmentary, written for a model — and it answers most of
what anyone asks. When a question goes past it, :meth:`look_up` reads exactly one
deep dive out of ``knowledge/l2/``. Reading them all would cost an order of
magnitude more context for material most sessions never need, and a model given
everything reasons from whatever it happens to notice.

**The page is not in this repo.** The elements Tanya may point at live in the
marketing site's Astro components, marked with ``data-vq``. ``content.py`` is the
brain's copy of that contract and the seam is across two repos — which is exactly
why every target the model can name is a ``Literal`` that validation enforces,
rather than a string it may invent.

When nothing on the page answers the question, :meth:`show_note` writes a short
markdown panel instead. That is the escape hatch for the long tail — pricing
shape, a wire detail, a comparison — and it keeps the answer readable rather than
turning it into a paragraph of speech.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel, Field
from voqalize_demos import (
    DEFAULT_MODEL,
    GeminiBrain,
    acted,
    configure_soon,
    needs_result_now,
    reask_if_silent,
)
from voqalize_demos.screen import ScreenState

from voqalize.sdk import Action, RTVIMessage, Session, Speech
from voqalize.sdk.wire import Config, IdleConfig, SttConfig, TtsConfig

from .app_events import MARKETING_EVENTS, MarketingEvent, SectionViewed
from .content import (
    OPENING,
    SECTION_OF_TARGET,
    SECTIONS_BY_ID,
    SPEECH,
    LanguageName,
    NoteLayout,
    Section,
    SectionId,
    TargetId,
    TopicId,
    core_knowledge,
    page_digest,
    read_topic,
    topic_digest,
)

AGENT_NAME = "Tanya"

# The visitor is reading, not waiting. Nothing here hangs up on a quiet page —
# they may well be reading something Tanya just pointed at.
_IDLE_MS = 0

# Heard in their own language and answered with the Hindi voice, because no voice
# speaks them. Named in the prompt so Tanya says so in the line she switches with,
# rather than learning it from the tool a turn later.
_HINDI_VOICED = ", ".join(s.name for s in SPEECH.values() if s.spoken != s.heard)


# ─── System prompt ─────────────────────────────────────────────────────────────
#
# The tools are not restated here. Each carries its own description on the method
# that takes it, and every field it generates carries its own on the model. What
# is left is what no single tool can say: who Tanya is, how she speaks, what she
# is looking at, and everything she knows.

_SYSTEM_INSTRUCTION = f"""You are {AGENT_NAME}, the voice agent embedded in the Voqalize homepage at voqalize.com. A visitor is reading the page right now, with you in the corner of it. You are also the demo: every question you answer by moving their screen is the product demonstrating itself.

YOUR FIRST INSTINCT IS TO POINT, NOT TO TALK. The page has already made the argument, in writing, better than you will out loud. So the shape of almost every turn is one response that says the one sentence the page does not AND points at the thing — the words go out as the page moves. Never read the page aloud — they can see it. If you find yourself about to narrate a section, point at it instead and say what it leaves out, or why it matters to them.

SPEAK AND ACT IN THE SAME RESPONSE. Whenever you point, write a panel or switch the language, say your line first and make the call in that same response. You do not get to speak again after one of those calls until the visitor does, so a call made in silence leaves them in silence. What such a call hands back, you read on your next turn.

VOICE STYLE. Short by default — a sentence or two a turn, each under about twelve words, because most turns are a pointer and not an answer. A real question is the exception: when someone has asked something that genuinely needs explaining, take the sentences it takes to answer it gracefully rather than clipping it into something curt. The brevity is here to stop you narrating the page, not to make you unhelpful. English by default. No markdown, no lists, no symbols in speech — the panel is where writing goes. No throat-clearing: not "Great question", not "Sure, let me", not restating what they asked. No summarizing what you just pointed at; the highlight already said it. If a question has a one-word answer, give the word.

ANSWER FROM WHAT YOU ARE GIVEN, AND SAY WHEN YOU CANNOT. Everything you know about Voqalize is in CORE KNOWLEDGE below, and the deep dives you can fetch. Do not improvise a figure, a date, a latency number, a customer name or a rate. The NOT KNOWN OR NOT COMMITTED list at the end is not shyness — those are things we have deliberately not published, and inventing one is worse than saying we have not said.

WHEN THE ANSWER IS NOT ON THE PAGE, WRITE IT. You have a panel. Use it for anything with structure — a code shape, a comparison, a sequence of steps, a short list — and for the long tail the page never had room for. Pick the layout that matches the shape of what you are writing. KEEP IT SHORT: the least that answers them, never a page of prose. They are on a call, reading it out of the corner of their eye, and the panel sits over the page they came for. Speak the headline in the same response that writes the panel, and let the panel carry the rest. Do not narrate its contents.

THE VISITOR'S SCROLL POSITION IS LIVE. The browser tells you which band is centred in their viewport. When they ask something that means what is in front of them — "what's this", "what does that mean", "is that included" — answer about THAT band unless they name another. If your answer is about a different one, bring them there first.

LANGUAGE. The call starts in English. Switch the moment they ask, and also the moment you believe they are speaking something else — a turn that arrives garbled, half-transliterated or nonsensical is usually the English recognizer hearing an Indian language, so ask which one in one short sentence and switch. Say the line you switch with in the language the call is in NOW, in the same response as the switch — it is spoken before the voice changes — and from their next turn on, keep speaking the new language. Switch back to English the same way. These are heard in their own language but answered with the Hindi voice, because no voice speaks them; when you switch to one, say so in that same line: {_HINDI_VOICED}.

WHO YOU ARE TALKING TO. Mostly engineers, CTOs and architects; sometimes an investor, a competitor or someone who arrived from a link. Do not ask them to identify themselves. Read it from what they ask, and pitch the answer there — an architect wants the boundary, an engineer wants the route they have to write, an investor wants what is ours.

WHAT YOU ARE NOT. You do not take contact details, quote a price, promise a date, or commit to an SLA. For any of those, say the honest version and point them at support@voqalize.com. You cannot see their code or their app.

THE PAGE MAP. These are the anchors you may scroll to and the elements you may highlight; nothing else on the page is reachable. Target ids are exact.
{page_digest()}

DEEPER MATERIAL. One topic per look-up, and only when CORE KNOWLEDGE genuinely runs out.
{topic_digest()}

═══ CORE KNOWLEDGE ═══

{core_knowledge()}"""


# The opener. Written, not generated: the visitor has just clicked, and an agent
# that makes them wait on a first token has already made the page feel slow.
_GREETING = f"Hi! I am {AGENT_NAME}. How can I help you today?"


# ── The tool surface: one pydantic model per tool ──────────────────────────────
#
# Each class below is declared to Gemini straight from itself: the fields are the
# parameters and every ``Field(description=...)`` reaches the model verbatim. The
# *tool's* own description is the docstring on the method that takes it — one
# sentence of instruction, in one place — so nothing here is written twice.
#
# An ``Action`` is the payload the browser renders. Where the model generates the
# whole payload, the Action is the tool's own request model and the body is one
# dispatch; where the brain has to fill a field the model must not choose — the
# anchor to scroll to, the language code to set on the document — the request is a
# plain ``BaseModel`` and the Action is built from it.
#
# ┌──────────────────────────────────────────────────────────────────────────┐
# │ These shapes are duplicated in the marketing site as TypeScript, in      │
# │ `platform/frontend/apps/marketing/src/agent/`, and the two are kept in   │
# │ sync BY HAND — across repos. Change a field here and change it there.    │
# └──────────────────────────────────────────────────────────────────────────┘


class PointAt(Action):
    """Brain → browser: scroll to a band and put a line of light on one element."""

    section: SectionId
    target: TargetId
    reason: str


class PointRequest(BaseModel):
    target: TargetId = Field(
        description="The element to bring on screen and highlight, exactly as it appears "
        "in THE PAGE MAP. The page scrolls to whichever band holds it."
    )
    reason: str = Field(
        "",
        description="One short phrase naming what you are pointing at, e.g. 'the wire "
        "contract' — shown beside the highlight, so do not also say it out loud.",
    )


class ShowNote(Action):
    """Brain → browser: a short markdown panel, for what the page does not carry."""

    title: str = Field(
        description="The heading of the panel — a few words naming what this is. Not a "
        "sentence, and not a restatement of their question."
    )
    # Defaulted, not required. A note that fails to render because the model did
    # not pick a shape is a worse outcome than a note in the shape most answers
    # have anyway — and 'note' is the one the description already says to use
    # unless another fits better, so the default and the instruction agree.
    layout: NoteLayout = Field(
        default="note",
        description="How to lay the answer out. 'note' is prose or bullets and is the "
        "one to use unless another fits better. 'steps' is an ordered sequence — write "
        "the body as a numbered list, one action per item. 'compare' sets two things "
        "against each other — write the body as exactly two '## ' headings, each "
        "followed by its own bullets.",
    )
    markdown: str = Field(
        description="The body, in markdown. Headings, bullets, short paragraphs, inline "
        "code and fenced code blocks all render; tables, images and links do not. Do NOT "
        "repeat the title here. Keep it SHORT — at most a few lines or a handful of "
        "bullets, the least that answers them; a panel they have to read through is a "
        "panel they stop reading. Write it in the language the conversation is in."
    )


class LanguageChanged(Action):
    """Brain → browser: the call has switched language, and what the page should read as."""

    language: LanguageName
    code: str
    """The IETF tag for the document's ``lang``, so the panel renders in the right script."""


class LanguageRequest(BaseModel):
    language: LanguageName = Field(
        description="The language to conduct the rest of the call in. Only these are "
        "served; if they ask for another, say so rather than picking the nearest."
    )


class TopicRequest(BaseModel):
    topic: TopicId = Field(
        description="Which deep dive to read, exactly as it appears in DEEPER MATERIAL."
    )


class MarketingBrain(GeminiBrain):
    """One per session. Tanya: the homepage, the knowledge base, and this visitor's
    scroll position.

    Where the visitor is reading arrives on :meth:`on_rtvi` as a typed gesture; a
    note says they moved and :meth:`where_they_are` says where to, so "what's this"
    is answered about the band on screen rather than the last one discussed."""

    def __init__(self, *, client: genai.Client, model: str = DEFAULT_MODEL) -> None:
        super().__init__(client=client, system_instruction=_SYSTEM_INSTRUCTION, model=model)
        self.screen = ScreenState(read_tool="where_they_are", actor="visitor")
        # Tanya's own mirror of the one thing about this page that moves. Both
        # sides patch it: the visitor's scroll, and her own `point_at`.
        self.current_section: Section | None = None

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        # Tanya's own voice — not the page's to choose, so it is settled here
        # rather than sent with the connect request. Both language legs move
        # together because half a language is silent; `set_language` moves them
        # again if the visitor asks. This lands before the greeting.
        #
        # `patience` is low because this is a shop window. A visitor asks a short
        # question about the band they are looking at and judges the product by
        # how it answers; a pause spent guarding against a mid-sentence breath is
        # a pause spent looking unresponsive to someone deciding whether to care.
        # Tanya points more than she talks, so her turns are short on both sides.
        await session.configure(
            Config(
                stt=SttConfig(language=OPENING.heard, patience=2),
                tts=TtsConfig(voice=OPENING.voice, language=OPENING.spoken),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
            )
        )
        logger.info("marketing: session start")

    async def greet(self, session: Session) -> str:
        """The opener, written not generated: the visitor clicked a button a moment
        ago, and a page that answers slowly is the wrong first impression of a
        product whose whole subject is turn latency."""
        return _GREETING

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The model's turn, asked once more if it acted on screen and said nothing.

        The prompt has the model speak and call in the same response, and on a
        dialled call it sometimes called alone, leaving the user in silence with
        the screen changed. See :mod:`voqalize_demos.silent_turn`."""
        async for event in reask_if_silent(super().respond, session):
            yield event

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Browser→brain gesture. Folded in *silently* — no floor taken, no turn;
        the next turn carries the line it produced."""
        event = MARKETING_EVENTS.parse(msg)
        if event is None:
            return
        logger.info("marketing: {} — {}", type(event).__voqal_event__, event)
        note = self.apply_event(event)
        if note is not None:
            self._append_note(note)

    # ─── Browser → brain: scroll position ───────────────────────────────

    def apply_event(self, event: MarketingEvent) -> str | None:
        """Patch the mirror; return the line the model should see, or ``None``.

        The observer that raises these fires on a crossing, and Tanya's own
        ``point_at`` scrolls the page too, tripping the same observer. She has
        already been told about that one — she asked for it — so a gesture naming
        the band the mirror already holds is silent. It is why this returns
        ``str | None`` rather than always a note."""
        match event:
            case SectionViewed():
                section = SECTIONS_BY_ID.get(event.section)
                if section is None or section is self.current_section:
                    return None
                self.current_section = section
                return self.screen.moved("scrolled to a different part of the page")

    def _append_note(self, text: str) -> None:
        """Put one line in front of the model without taking the floor.

        Appended as the visitor's own content, which is what it is. It starts no
        turn — nothing about a scroll means they stopped speaking — so the model
        reads it on its next one."""
        self.append_to_context(types.Content(role="user", parts=[types.Part(text=text)]))

    # ─── Tools ──────────────────────────────────────────────────────────
    #
    # The model calls these directly. Each takes its own pydantic model, already
    # validated — a target that is not on the page, or a language the speech tier
    # does not serve, cannot reach a body, so nothing here checks for one.
    #
    # Only the reads carry ``@needs_result_now``: the model cannot answer "what's
    # this" or a deep question without what they return, so it is asked again at
    # once. Everything else moves the screen or the call, and its result waits in
    # the context for the visitor's next turn — the prompt has Tanya speak before
    # she calls, because nothing is said after.
    #
    # They return "ok" and nothing more, except where the tool knows something the
    # model does not. A tool result is prompt the model pays for on every
    # following turn, and "pointed, target=hero.mcp" only tells it what it just
    # said.

    @property
    def tools(self) -> list[Any]:
        """Tanya's whole surface: read the page, move it, write on it, read deeper,
        change language. Everything but the reads drives the visitor's screen
        through ``self.session``."""
        return [
            self.where_they_are,
            self.point_at,
            self.show_note,
            self.look_up,
            self.set_language,
        ]

    @needs_result_now
    async def where_they_are(self) -> str:
        """Which part of the page the visitor is looking at right now. Call this
        whenever they say "this", "that", "here" — anything that means the thing on
        their screen rather than something they named."""
        self.screen.read()
        if self.current_section is None:
            return "The visitor is at the top of the page and has not scrolled yet."
        section = self.current_section
        return (
            f"The visitor is reading #{section.id} — {section.title} It answers: {section.answers}."
        )

    async def point_at(self, request: PointRequest) -> str:
        """Scroll the visitor's page to an element and draw a line of light to it.
        This is your main move for anything the page itself shows: say your one
        sentence and call this in the same response, so the highlight lands as you
        speak and carries what you would otherwise say out loud."""
        # Her own scroll moves the reading position as surely as theirs does, so
        # the mirror follows it — and the observer's report of the same band is
        # then nothing new.
        section_id = SECTION_OF_TARGET[request.target]
        self.current_section = SECTIONS_BY_ID[section_id]
        self.session.dispatch(
            PointAt(section=section_id, target=request.target, reason=request.reason)
        )
        acted("point_at")
        return "ok"

    async def show_note(self, note: ShowNote) -> str:
        """Write a short markdown panel over the page. Use it when the answer is not
        on the page at all, or has structure that speech mangles — a code shape, a
        comparison, a few steps. Choose the layout that fits what you are writing.
        Keep it brief, and speak only the headline, in the same response that calls
        this; the panel carries the rest."""
        self.session.dispatch(note)
        acted("show_note")
        return "ok"

    @needs_result_now
    async def look_up(self, request: TopicRequest) -> str:
        """Read one deep dive, for a question CORE KNOWLEDGE does not settle. SAY A
        SHORT HOLDING LINE OUT LOUD BEFORE CALLING IT — "one second" — then answer
        from what comes back. One topic per question; never fetch several to
        compare."""
        logger.info("marketing: look_up {}", request.topic)
        return read_topic(request.topic)

    async def set_language(self, request: LanguageRequest) -> str:
        """Conduct the rest of the call in another language — both the listening and
        the speaking. Call it when they ask, and when you believe they are already
        speaking it. In the same response, say one short line in the language the
        call is in now, before calling — it is spoken before the voice changes."""
        speech = SPEECH[request.language]
        # Sent, not awaited: the answer is a round trip and a tool has to return
        # within the budget. Nothing checks later that it applied — a refusal is
        # logged and the call goes on in the language it was in.
        configure_soon(
            self.session,
            Config(
                stt=SttConfig(language=speech.heard),
                tts=TtsConfig(voice=speech.voice, language=speech.spoken),
            ),
        )
        self.session.dispatch(LanguageChanged(language=speech.name, code=str(speech.heard)))
        logger.info("marketing: language -> {}", request.language)
        if speech.spoken == speech.heard:
            return "ok"
        # A recognized language with no reference clip of its own. Stated out loud
        # rather than substituted behind anyone's back — that is the speech tier's
        # rule, and the visitor is about to hear the difference. The prompt has her
        # say it in the switch line; this reaches her a turn later, so it reads as
        # a fact rather than an order.
        return (
            f"Listening in {request.language}, but there is no {request.language} voice — "
            f"you are speaking with the Hindi voice. If you have not told the visitor, "
            f"say so in one short sentence."
        )
