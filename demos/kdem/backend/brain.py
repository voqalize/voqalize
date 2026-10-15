"""KdemBrain — Aria, the voice agent on karnatakadigital.in.

A visitor to KDEM's site (the Karnataka Digital Economy Mission) clicks "Talk to
Aria" and asks a question about doing business in Karnataka. Aria answers from
the site's own approved pages and the PDF documents they link to (policies,
guidelines, reports, newsletters), in a sentence or two, and offers the page or
the PDF that says it in full as a link card beside her face.

Three things shape every decision here.

**She answers only from the pages KDEM approved.** :meth:`search_kdem` reads the
in-memory index ``knowledge.py`` keeps of those pages — their visible text, one
canonical URL per topic, refreshed from the sitemap about once a day — and of
the text of the PDFs they link to, page by page, so she can say where in a
document the answer is. The prompt holds her to what comes back. When nothing does, she says so in one fixed
line and offers Contact Us. A government agency's assistant that improvises a
scheme, a figure or a deadline is worse than one that says it does not know.

**The model never supplies a URL the brain trusts.** :meth:`show_document`,
:meth:`offer_page` and :meth:`go_to_page` take what
the model names, canonicalises it, and sends it only if the index holds that page
now — an approved page the last refresh read, a page it added, or a PDF an
approved page links to and the refresh read — with the page's own title, not
the model's. A listed page the refresh dropped (deleted,
unpublished, or redirecting elsewhere) is not sent; before the first index
exists, only Contact Us is. The browser snippet checks the host again, but the
brain is where "only approved pages" is decided.

**The page is someone else's.** There is no frontend here: the snippet in
``demos/kdem/embed/`` is pasted into the site, connects with
``init = {surface, page, lang}``, and renders four commands: ``show_link`` (a
card for a document, sent by the model's ``show_document``), ``navigate``,
``point_at`` and ``language_changed``. Pages are visited; cards are for documents. The call carries on across
page loads, and on every (re)connect the snippet sends ``page_viewed``
(:mod:`.app_events`): Aria learns the visitor moved, silently, on their next turn.

**She asks before she moves the page.** ``go_to_page`` opens another page in the
visitor's tab, and the brain sends it only for a page ``offer_page`` offered in
her previous turn (the visitor's next turn is the yes), or when the visitor's
own words this turn ask to be taken somewhere. ``point_at`` needs no asking: it
lights up a phrase the brain has checked is on the page they have open.

The knowledge base is one per process. The first session starts its keeper
(:meth:`~.knowledge.KnowledgeService.start`, idempotent and non-blocking); every
session after that reads the same index.
"""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator
from typing import Any

from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel, Field
from voqalize_demos import (
    DEFAULT_MODEL,
    PATIENCE,
    PHRASES,
    FallbackLine,
    GeminiBrain,
    landed,
    needs_result_now,
    phrase,
    say_line,
)

from voqalize.sdk import Action, RequestRejected, RTVIMessage, Session, Speech, UserMessage
from voqalize.sdk.wire import Config, IdleConfig, Language, SttConfig, TtsConfig

from .app_events import KDEM_EVENTS, LanguageRequested, PageViewed, PointMissed
from .content import (
    BY_CODE,
    BY_TAG,
    CONTACT_PATH,
    OPENING,
    SPEECH,
    LanguageName,
    LanguageTag,
    page_digest,
)
from .content import Speech as LanguageSpeech
from .knowledge import (
    ALLOWLIST,
    KNOWLEDGE,
    Passage,
    host_of,
    is_pdf,
    normalize,
    off_site,
    path_of,
    pdf_url,
)

AGENT_NAME = "Aria"

# The visitor is reading the site, not waiting on her. Nothing hangs up on a
# quiet page — they may be reading the link she just offered.
_IDLE_MS = 0

#: How many passages one search hands back. Three is enough to answer from and
#: few enough that a turn's context stays small.
_PASSAGES = 3

#: The line for anything the approved pages do not answer. Written once, here,
#: so the prompt and the tool results say the same words.
DONT_KNOW = "I don't have that on our website. The KDEM team can help."

# Her own line for a silent turn is said in the language her voice speaks, so
# each one needs a row in the shared phrases — held at import, not on a call.
assert {s.code for s in SPEECH.values()} <= set(PHRASES), "a spoken language has no PHRASES row"

# ─── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_INSTRUCTION = f"""You are {AGENT_NAME}, the voice assistant on the website of KDEM, the Karnataka Digital Economy Mission, at karnatakadigital.in. A visitor is on the site right now, with you in the corner of the page. They are usually a founder, an investor, a company looking at Karnataka, a student or a job seeker.

EVERY RESPONSE STARTS WITH WORDS. Whenever you offer a page, take them to one, point at something or show a document, write your line first and make the call in that same response — the line is spoken as the page moves. A response that is only a tool call is silence: after offer_page, go_to_page, point_at or show_document you do not speak again until the visitor does. For example:
  Visitor: "Do you have a seed fund for startups outside Bengaluru?" You: (search_kdem first, then) "Yes, the Beyond Bengaluru Cluster Seed Fund backs startups in the clusters. Shall I take you to its page?" — and offer_page with that page, in the same response.
search_kdem and set_language are the two calls that take no line. search_kdem is silent and comes straight back to you in the same turn, so call it first and then answer from it. set_language is answered by a line of its own, in the new voice, so call it alone and say nothing.

ANSWER ONLY FROM THE SITE. Everything you may say about KDEM, its programmes, policies, events, reports and news comes from what search_kdem returns. Search before you answer any question about KDEM or Karnataka's digital economy — even one you think you know. Never add a figure, a date, a deadline, an amount, an eligibility rule or a name that is not in what came back. If the search returns nothing that answers the question, say exactly: "{DONT_KNOW}" and offer to take them to the Contact Us page with offer_page ({CONTACT_PATH}), or point at it with point_at if they are already there.

THE SHAPE OF AN ANSWER. One or two short sentences that answer the question, then, in the same response:
- when the page that says it in full is another page, offer to take them there with offer_page: "Shall I take you to the Seed Fund page?";
- when they are already on that page, point at the part that says it with point_at;
- when the answer comes from a PDF, name the document and the page in words and show it beside you with show_document.
Do not read a page aloud; the page is there for that. Pass a URL that search_kdem returned or one from THE PAGES below.

DOCUMENTS. Many results come from the PDF documents KDEM's pages link to — policies, guidelines, reports and newsletters — and are marked "PDF document, page N". When you answer from one, say which document and where, in words, for example "the Startup Policy says so on page 12", and show it beside you with show_document, passing the url exactly as search_kdem gave it. A document hosted on another government site, marked "on <site>", opens as the KDEM page that links to it: name the document and the page in what you say, and say it is linked from that KDEM page.

TAKING THEM AROUND THE SITE. You can take the visitor to another page of the site, in this same tab; the call carries on there with them.
- Ask first, in one short line, and call offer_page with that page in the same response: "Shall I take you to the Seed Fund page?" When they say yes, in their next turn, call go_to_page with it and say one short line: "Taking you there."
- When they ask to be taken somewhere ("take me to the events page", "open the policies page"), that is their yes: call go_to_page at once, with "Taking you there."
- go_to_page goes to a page you offered in your last turn, or one they asked for in this turn. A PDF opens beside you with show_document instead, so the call stays on this page.
- POINTING. On the page they have open, point at the part that answers them with point_at, passing a short exact phrase from that page's text: a heading or a few words, under 80 characters, as they appear in what search_kdem returned for that page. No need to ask: "Eligibility is right here."
- After you take them to a page you are still in the same conversation: carry on from where you were, point at the part they need, and do not greet them again.

VOICE STYLE. Warm, plain and brief. No markdown, no lists, no symbols, no URLs read aloud — say "the Policies page", not its address. Say numbers as a person would. No throat-clearing: not "Great question", not "Sure, let me". English by default.

WHAT YOU DO NOT DO. Each of these gets one polite sentence and, where it helps, the Contact Us page:
- Politics, government decisions, ministers or officials, and opinions about any of them. You talk about what the site says, not about who decided it.
- Commitments on behalf of KDEM or the Government of Karnataka: no promises of funding, approval, a meeting, a timeline or an outcome.
- The status of any individual application, registration, payment or tender. You cannot see them; the KDEM team can.
- Legal, tax or investment advice beyond what the site's own documents say. Say what the document says and suggest they take advice.
- Personal data. Never ask for a name, phone number, email, address, ID number, OTP or password, and if they offer one, tell them you do not need it.
- Anything unrelated to KDEM and doing business in Karnataka: say briefly that it is outside what you can help with here.

LANGUAGE. The call starts in English, and English stays the main language. Besides English you speak Kannada, the language of Karnataka, in a Kannada voice.
- NEVER SAY ITS NAME IN ENGLISH. In English speech, never say the name of the Kannada language: the English voice cannot say it. If you must refer to it, say "Karnataka's own language"; usually, simply switch. If they ask which languages you speak, or whether you speak it, say: "I speak English, and Karnataka's own language too. Just speak to me in it, or tap ಕನ್ನಡ at the top of my panel."
- SWITCHING TO KANNADA. If the visitor asks for Kannada, or a turn looks like Kannada, call set_language with kannada at once, in that turn, and say NOTHING yourself: no line before the call and none after. The voice changes first, and then a written Kannada line is said for you, asking them to say it again. From their next turn on, speak Kannada, in Kannada script. While you are in English the recognizer only knows English, so Kannada arrives as English words forced onto Kannada sounds; a turn that makes no sense as English is usually Kannada, and the sounds that survive are words like "naanu", "nanna", "beku", "illa", "enu", "hesaru", "maadi", "gottilla". Do not ask whether to switch: switch. If you were wrong, the visitor speaks English and you switch back, or they tap English on the page.
- SWITCHING BACK. In Kannada mode English arrives spelled in Kannada script ("ಐ ವಾಂಟ್ ..." is "I want ..."); judge by the small grammar words, not by nouns. When they speak English or ask for it, call set_language with english, again saying nothing yourself: a written English line is said for you in the English voice.
- What does NOT count as switching: one borrowed English word inside a Kannada sentence ("ನನಗೆ startup fund ಬೇಕು" is still Kannada), or one Kannada word inside an English sentence. Judge by the whole sentence, not a word.
- Only English and Kannada are offered; if they ask for another language, say so in English. The site is in English, so always write search_kdem queries in English, whatever language the call is in.

THE PAGES. These are the approved pages, by path, with their titles. Newer news and event pages may also come back from search_kdem; those are approved too.
"""

# The opener. Written, not generated: the visitor has just clicked, and a first
# word that waits on a model makes the site feel slow.
_GREETING = (
    f"Hello, I'm {AGENT_NAME} from KDEM. How can we help you grow your business in Karnataka?"
)


#: The opener when the visitor picked ಕನ್ನಡ on the toggle before the call.
#: Written, like the English one. To be checked by a native speaker.
_GREETING_KN = "ನಮಸ್ಕಾರ, ನಾನು KDEM ನ ಆರಿಯಾ. ಕರ್ನಾಟಕದಲ್ಲಿ ನಿಮ್ಮ ವ್ಯವಹಾರ ಬೆಳೆಸಲು ನಾವು ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಹುದು?"

#: What Aria says, at the start of her next turn, after the visitor switched the
#: language on the toggle. Written, in the new language, read by the new voice.
#: The Kannada line is to be checked by a native speaker.
TOGGLE_CONFIRM: dict[LanguageTag, str] = {
    "en": "Sure, let's continue in English.",
    "kn": "ಸರಿ, ಈಗ ಕನ್ನಡದಲ್ಲಿ ಮಾತಾಡೋಣ.",
}

#: What Aria says when she switches by voice, after both legs have moved, so the
#: new voice reads it, at the end of the turn that asked for it. The visitor's
#: Kannada was heard by the English recognizer and lost, so the Kannada line asks
#: them to say it again. Never the language's English name: the English voice
#: cannot say it. The Kannada line is to be checked by a native speaker.
SWITCH_LINE: dict[LanguageTag, str] = {
    "en": "Sure, let's continue in English.",
    "kn": "ಸರಿ, ಈಗ ಕನ್ನಡದಲ್ಲಿ ಮಾತಾಡೋಣ. ದಯವಿಟ್ಟು ನಿಮ್ಮ ಪ್ರಶ್ನೆಯನ್ನು ಮತ್ತೊಮ್ಮೆ ಹೇಳಿ.",
}


def _prompt(where: str = "", spoken: Language = OPENING.code) -> str:
    """The system prompt as things stand: THE PAGES lists only the pages Aria
    may link at this moment, so the model is never offered one the refresh has
    dropped; the call's language now, when it is not English; and where the
    visitor is."""
    prompt = _SYSTEM_INSTRUCTION + page_digest(lambda url: _page(url) is not None)
    if spoken == Language.KN:
        prompt += (
            "\n\nTHE CALL IS IN KANNADA NOW. Speak Kannada, in Kannada script, until the "
            "visitor asks for English, speaks it, or switches it on the page."
        )
    return f"{prompt}\n\nWHERE THEY ARE. {where}" if where else prompt


# ── The tool surface ──────────────────────────────────────────────────────────


class ShowLink(Action, name="show_link"):
    """Brain → browser: a link card to one KDEM document, opened in a new tab.

    The model's tool for it is ``show_document``, and it is for PDFs only: pages
    are visited, with ``offer_page`` / ``go_to_page``. The command keeps the wire
    name ``show_link`` and its ``{url, title}`` payload so the snippet already on
    the site renders it unchanged."""

    url: str
    """An absolute ``https://karnatakadigital.in/...`` URL, chosen by the brain: a
    PDF under ``/wp-content/uploads/``, or, for a PDF on another site, the
    approved KDEM page that links it."""
    title: str
    """The document's own title, as the card shows it."""


class SearchRequest(BaseModel):
    query: str = Field(
        description="What the visitor wants to know, as a short search in English — "
        "the site is in English even when the call is in Kannada. Name the topic, "
        "e.g. 'seed fund for startups in Mysuru' or 'upcoming events'."
    )


class LanguageChanged(Action, name="language_changed"):
    """Brain → browser: the language the call is in now. The snippet's
    English | ಕನ್ನಡ toggle shows this and nothing else, so it follows a switch
    made by voice as well as one made on the toggle."""

    language: LanguageTag


class Navigate(Action, name="navigate"):
    """Brain → browser: open this KDEM page in the same tab. The call carries on
    across the page load. Sent only for a page the visitor said yes to, or asked
    for themselves."""

    url: str
    """An absolute ``https://karnatakadigital.in/...`` page URL, chosen by the brain."""


class PointAt(Action, name="point_at"):
    """Brain → browser: scroll to, and briefly highlight, the first visible part
    of the page holding this text. The brain checked it is on the page."""

    text: str


class PageRequest(BaseModel):
    url: str = Field(
        description="The page: a URL that search_kdem returned, or a path from THE PAGES, "
        "e.g. '/policies/'."
    )


class PointRequest(BaseModel):
    text: str = Field(
        description="A short exact phrase from the page the visitor has open, under 80 "
        "characters: a heading or a few words, as they appear in its text."
    )


class DocumentRequest(BaseModel):
    url: str = Field(
        description="The PDF document to show: its url exactly as search_kdem returned it."
    )
    title: str = Field(
        "",
        description="A few words naming the document. The card uses its own title.",
    )


class LanguageRequest(BaseModel):
    language: LanguageName = Field(
        description="The language to conduct the rest of the call in. Only English and "
        "Kannada are offered; if they ask for another, say so rather than picking one."
    )


_POINT_CHARS = 80
"""The longest phrase ``point_at`` takes: a heading or a few words, not a passage."""

_ASKS_TO_GO = re.compile(
    r"\b(?:take|bring|walk)\s+(?:me|us)\b|\b(?:go|navigate|jump|head|move)\s+to\b"
    r"|\bopen\b|\bvisit\b|\blet'?s\s+go\b"
    r"|ಕರೆದುಕೊಂಡು\s*ಹೋಗಿ|ಕರ್ಕೊಂಡು\s*ಹೋಗಿ|ತೆರೆಯಿರಿ|ತೆಗೆಯಿರಿ|ಹೋಗೋಣ",
    re.IGNORECASE,
)
"""Words with which a visitor asks to be taken to a page, in English and Kannada.
Their own request is the yes that ``go_to_page`` otherwise waits for."""


def _squash(text: str) -> str:
    """Text as compared for pointing: whitespace collapsed, case folded."""
    return re.sub(r"\s+", " ", text).strip().casefold()


def _page(url: str) -> tuple[str, str] | None:
    """The canonical URL and title of the page ``url`` names, if Aria may link it.

    A page the index holds now (aliases fold into it): an approved page the last
    refresh read, under the list's title, a news or event page it added, or a
    PDF an approved page links to, under its link text. A PDF on another site is
    sent as the approved page that links it. A
    page on the list that the refresh dropped (gone from the sitemap, a 404, or a
    redirect elsewhere) is ``None``. Until the first index exists the one page
    sent is Contact Us, so the don't-know answer still has its link. Anything
    else, including every URL off the site, is ``None``."""
    if (theirs := pdf_url(url)) is not None and off_site(theirs):
        # A PDF on another site: the snippet shows only karnatakadigital.in, so
        # the card is the approved page that links it, if the index holds it.
        return _via(theirs)
    canonical = ALLOWLIST.canonical(url)
    if canonical is None or ALLOWLIST.is_excluded(canonical):
        return None
    approved = ALLOWLIST.approved(canonical)
    if not (KNOWLEDGE.snapshot.built_at or len(KNOWLEDGE.kb)):
        if approved is not None and approved.url == ALLOWLIST.contact_url:
            return approved.url, approved.title
        return None
    if (indexed := KNOWLEDGE.kb.page(canonical)) is None:
        return None
    if approved is not None:
        return approved.url, approved.title
    return indexed.url, indexed.title or path_of(indexed.url)


def _source(p: Passage) -> str:
    """How a search result names where it came from: a page by its title, a PDF
    as a document, with the page the passage is on and, for a PDF on another
    site, that site and the KDEM page that links it."""
    if p.kind != "pdf":
        return p.title
    where = "PDF document"
    if off_site(p.url):
        where += f" on {host_of(p.url)}"
    if p.page:
        where += f", page {p.page}"
    source = f"{p.title} ({where})"
    if off_site(p.url) and (via := _via(p.url)) is not None:
        source += f', linked from the KDEM page "{via[1]}"'
    return source


def _via(url: str) -> tuple[str, str] | None:
    """For a PDF on another site that the index holds: the approved KDEM page
    that links it, which is what the snippet can show."""
    indexed = KNOWLEDGE.kb.page(url)
    if indexed is None or indexed.kind != "pdf" or not off_site(indexed.url):
        return None
    return _page(indexed.via) if indexed.via else None


def _where_they_are(path: str, *, moved: bool) -> str:
    """One line on the page the visitor has open: by its own title and path when
    it is a page Aria may link now, else only "a page of the site". Nothing the
    browser sent is quoted."""
    known = _page(path)
    if known is None:
        return "The visitor is now on a page of the site." if moved else ""
    url, title = known
    if moved:
        return f'The visitor is now on the page "{title}" ({path_of(url)}).'
    return f'The visitor opened you on the page "{title}" ({path_of(url)}).'


def _where_they_started(init: dict[str, Any]) -> str:
    """One line on the page the visitor opened Aria from, for the prompt.

    ``page`` comes from the visitor's browser, so it is named only when it is a
    page Aria may link now, and then by that page's own title and path. Anything
    else is left out: the prompt never quotes what the browser sent."""
    raw = init.get("page")
    if not isinstance(raw, str) or not raw:
        return ""
    return _where_they_are(raw, moved=False)


class KdemBrain(GeminiBrain):
    """One per session. Aria: KDEM's approved pages, and this visitor's call."""

    def __init__(self, *, client: genai.Client, model: str = DEFAULT_MODEL) -> None:
        super().__init__(client=client, system_instruction=_prompt(), model=model)
        #: The language the voice is speaking, for the line the brain says when
        #: the model's turn acted and said nothing.
        self.spoken: Language = OPENING.code
        self._fallback = FallbackLine()
        #: The page the visitor has open, as a site URL; ``None`` until known.
        self.here: str | None = None
        #: The WHERE THEY ARE line the prompt carries now.
        self._where = ""
        #: A toggle switch's written confirmation, said when Aria next has the floor.
        self._confirm: str | None = None
        #: A switch the model asked for with ``set_language``, made when its
        #: response has streamed, still inside the turn.
        self._pending: LanguageSpeech | None = None
        #: The visitor's turns so far, and what they said in the latest.
        self._turn = 0
        self._heard = ""
        #: The page Aria offered to take them to, and in which turn.
        self._offered: tuple[str, int] | None = None
        #: The page she took them to, until they arrive there.
        self._took_to: str | None = None
        #: The phrase she last pointed at, for a page that could not show it.
        self._pointed: str | None = None

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        # Aria's voice — not the page's to choose, so it is settled here rather
        # than sent with the connect request. Both legs move together; the voice
        # is gauri in English and Kannada alike. This lands before the greeting.
        # The one thing the page may ask for is the language the visitor picked
        # on the toggle before the call: "kn" opens in Kannada, anything else in
        # English.
        init = dict(session.init or {})
        opening = BY_TAG["kn"] if init.get("lang") == "kn" else OPENING
        await session.configure(
            Config(
                stt=SttConfig(language=opening.code, patience=PATIENCE),
                tts=TtsConfig(voice=opening.voice, language=opening.code),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
            )
        )
        self.spoken = opening.code
        # One keeper per process: the first session starts it, the rest find it
        # running. It never makes this session wait.
        KNOWLEDGE.start()

        self._where = _where_they_started(init)
        self.system_instruction = _prompt(self._where, self.spoken)
        if isinstance(page := init.get("page"), str):
            self.here = normalize(page)
        logger.info(
            "kdem: session start (surface={}, page={}, lang={}, pages indexed={})",
            init.get("surface"),
            init.get("page"),
            init.get("lang"),
            len(KNOWLEDGE.kb),
        )

    async def greet(self, session: Session) -> str:
        """The opener, written not generated, in the language the call opens in."""
        return _GREETING_KN if self.spoken == Language.KN else _GREETING

    def on_user_message(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]:
        """Count the turn and keep what was said, for ``go_to_page``'s rule; then
        the model's turn as usual."""
        self._turn += 1
        self._heard = msg.text
        return super().on_user_message(session, msg)

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The model's turn, and a line of Aria's own if it acted and said nothing.
        See :mod:`voqalize_demos.silent_turn`.

        A language switched on the toggle is confirmed first, in the new language,
        with its written line: a brain has no floor outside a turn, so this is the
        first moment Aria may speak, and it never talks over anyone.

        A language the model switched with ``set_language`` is switched last:
        once its response has streamed (it says nothing with the call), both legs
        move in one awaited request, and only then is the written line said, so
        the new voice reads it. It is the end of the same turn, so there is no
        dead air, and the visitor speaks next."""
        if (left := self._pending) is not None:
            # A switch asked for in a turn the visitor cut short: made now, quietly.
            self._pending = None
            await self._move(session, left, by="you, on what the visitor said")
        if (line := self._confirm) is not None:
            self._confirm = None
            async for event in say_line(self, line):
                yield event
        async for event in self._fallback.speak_if_silent(self, super().respond(session)):
            yield event
        if (speech := self._pending) is not None:
            self._pending = None
            if await self._move(session, speech, by="you, on what the visitor said"):
                async for event in say_line(self, SWITCH_LINE[speech.tag]):
                    yield event

    async def _move(self, session: Session, speech: LanguageSpeech, *, by: str) -> bool:
        """Move both legs to ``speech`` in one awaited request, and record it.
        ``False`` when Voqalize refused it: the page is told the language that
        still holds, and nothing else changes."""
        try:
            await session.configure(
                Config(
                    stt=SttConfig(language=speech.code, patience=PATIENCE),
                    tts=TtsConfig(voice=speech.voice, language=speech.code),
                )
            )
        except RequestRejected as rejected:
            logger.warning("kdem: switch to {} refused: {}", speech.name, rejected)
            session.dispatch(LanguageChanged(language=BY_CODE[self.spoken].tag))
            return False
        self._switched(speech, by=by, note=by.startswith("the visitor"))
        return True

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Browser→brain: the page the visitor has open. Folded in silently: no
        floor taken and no turn, so a page load never makes Aria speak; the
        model reads where they are with the visitor's next turn. Unknown events
        and payloads that do not fit are dropped by the parser."""
        event = KDEM_EVENTS.parse(msg)
        if event is None:
            return
        match event:
            case PageViewed():
                self._viewed(event)
            case LanguageRequested():
                await self._requested(session, event)
            case PointMissed():
                # Only for the phrase she pointed at: never a line the page made up.
                if event.text == self._pointed:
                    note = (
                        f'[The page could not show "{event.text}": no part of it on screen '
                        "holds that text. Say where it is in words instead.]"
                    )
                    self.append_to_context(
                        types.Content(role="user", parts=[types.Part(text=note)])
                    )

    async def _requested(self, session: Session, event: LanguageRequested) -> None:
        """The visitor pressed the other language on the toggle. Switched in code,
        not through the model: both legs move in one awaited request, the page
        is told, and the written confirmation waits for Aria's next turn. Asking
        for the language the call is already in does nothing."""
        speech = BY_TAG[event.language]
        if speech.code == self.spoken:
            return
        # A refusal puts the toggle back to the language that holds.
        if await self._move(session, speech, by="the visitor, on the page's toggle"):
            self._confirm = TOGGLE_CONFIRM[speech.tag]

    def _switched(self, speech: LanguageSpeech, *, by: str, note: bool = True) -> None:
        """Record a switch that has been sent, tell the page, and (from a
        callback) leave the model one line about it. Shared by the toggle and
        ``set_language``, so the two cannot disagree about what a switch does.
        A tool leaves no note: its own result is the model's record, and a line
        filed mid-turn would land between a call and its result."""
        logger.info("kdem: language {} -> {} (by {})", BY_CODE[self.spoken].name, speech.name, by)
        self.spoken = speech.code
        self._confirm = None
        self.session.dispatch(LanguageChanged(language=speech.tag))
        self.system_instruction = _prompt(self._where, self.spoken)
        if note:
            line = f"[The call is now in {speech.name.capitalize()}, switched by {by}.]"
            self.append_to_context(types.Content(role="user", parts=[types.Part(text=line)]))

    def _viewed(self, event: PageViewed) -> None:
        here = normalize(event.path)
        if here is None or here == self.here:
            # Not a page of this site, or the one already known: the reconnect
            # on the page the call started on says nothing new.
            return
        self.here = here
        line = self._where = _where_they_are(event.path, moved=True)
        if self._took_to is not None and ALLOWLIST.canonical(here) == self._took_to:
            self._took_to = None
            line += (
                " You took them here: carry on the conversation where it was, pointing at "
                "the part they need, and do not greet them again."
            )
        logger.info(
            "kdem: page_viewed {} ({})", path_of(here), "named" if _page(here) else "unnamed"
        )
        self.system_instruction = _prompt(line, self.spoken)
        self.append_to_context(types.Content(role="user", parts=[types.Part(text=f"[{line}]")]))

    # ─── Tools ──────────────────────────────────────────────────────────
    #
    # All read memory and return inside the tool budget. Only the search is
    # marked: Aria cannot answer without what it returns. The rest are spoken
    # with, in the same response; set_language's line is the brain's.

    @property
    def tools(self) -> list[Any]:
        """Search the approved pages, offer one as a link, take the visitor to one
        (asking first), point at part of the page they are on, change language."""
        return [
            self.search_kdem,
            self.show_document,
            self.offer_page,
            self.go_to_page,
            self.point_at,
            self.set_language,
        ]

    def _destination(self, url: str) -> tuple[str, str] | str:
        """The page ``url`` would take the visitor to, as ``(url, title)``, or the
        sentence that says why not: the same rules as ``show_document``, a PDF on
        another site going to the KDEM page that links it, and only pages, since a
        PDF in this tab would leave the call behind."""
        found = _page(url)
        if found is None:
            return (
                f"Not sent: {url!r} is not one of the approved KDEM pages. Offer a page "
                f"search_kdem returned, or the Contact Us page ({CONTACT_PATH})."
            )
        dest, title = found
        if is_pdf(dest):
            return "Not sent: a PDF opens beside you with show_document; go_to_page is for pages."
        here = ALLOWLIST.canonical(self.here) if self.here else None
        if dest == here:
            return f'They are already on "{title}". Point at the part they need with point_at.'
        return dest, title

    async def offer_page(self, request: PageRequest) -> str:
        """Offer to take the visitor to another page of the site. Say your one short
        question ("Shall I take you to the Seed Fund page?") and call this in the
        same response; nothing moves until they say yes."""
        found = self._destination(request.url)
        if isinstance(found, str):
            return found
        self._offered = (found[0], self._turn)
        logger.info("kdem: offer_page {}", path_of(found[0]))
        return "Offered. When they say yes, call go_to_page with this page."

    async def go_to_page(self, request: PageRequest) -> str:
        """Take the visitor to another page of the site, in this tab; the call
        carries on there. Only a page you offered in your last turn and they said
        yes to, or one they asked to be taken to in this turn. Say one short line
        ("Taking you there.") and call this in the same response."""
        found = self._destination(request.url)
        if isinstance(found, str):
            return found
        dest, title = found
        offered = self._offered
        said_yes = offered is not None and offered[0] == dest and offered[1] == self._turn - 1
        if not (said_yes or _ASKS_TO_GO.search(self._heard)):
            logger.info("kdem: go_to_page {} refused: not offered or asked for", path_of(dest))
            return (
                f'Not sent: ask first. Say "Shall I take you to the {title} page?" and call '
                "offer_page with it; go when they say yes."
            )
        self._offered = None
        self._took_to = dest
        self.session.dispatch(Navigate(url=dest))
        logger.info(
            "kdem: go_to_page {} ({})", path_of(dest), "a yes" if said_yes else "they asked"
        )
        landed(*phrase(self.spoken, "shown"))
        return "ok: the page opens, and the call carries on there."

    async def point_at(self, request: PointRequest) -> str:
        """Point at part of the page the visitor has open: it scrolls into view and
        lights up. Pass a short exact phrase from that page. No need to ask; say
        one short line ("Eligibility is right here.") and call this with it."""
        text = re.sub(r"\s+", " ", request.text).strip()
        if not text:
            return "Not shown: pass a short phrase from the page they are on."
        if len(text) > _POINT_CHARS:
            return f"Not shown: pass a shorter phrase, under {_POINT_CHARS} characters."
        page = KNOWLEDGE.kb.page(self.here) if self.here else None
        if page is None:
            return "Not shown: I do not have the text of the page they are on."
        if _squash(text) not in _squash(f"{page.title}\n{page.text}"):
            return (
                f"Not shown: {text!r} is not on the page they are on now ({page.title}). "
                "Pass a phrase from that page, or offer to take them to the page that has it."
            )
        self._pointed = text
        self.session.dispatch(PointAt(text=text))
        logger.info("kdem: point_at {!r} on {}", text, path_of(page.url))
        landed(*phrase(self.spoken, "shown"))
        return "ok"

    @needs_result_now
    async def search_kdem(self, request: SearchRequest) -> str:
        """Search KDEM's approved website pages and the PDF documents they link to.
        Call it before answering any question about KDEM, its programmes, policies,
        events, reports or news, and answer only from what it returns."""
        kb = KNOWLEDGE.kb
        if len(kb) == 0:
            logger.warning("kdem: search with an empty knowledge base")
            return (
                "The website's pages are not available right now, so there is nothing to "
                f'answer from. Say: "{DONT_KNOW}" and offer to take them to the Contact '
                f"Us page ({CONTACT_PATH}) with offer_page, or point at it with point_at if "
                "they are already there."
            )
        passages = kb.search(request.query, k=_PASSAGES)
        logger.info("kdem: search {!r} -> {} passages", request.query, len(passages))
        if not passages:
            return (
                f'Nothing on the approved pages matches. Say: "{DONT_KNOW}" and offer to '
                f"take them to the Contact Us page ({CONTACT_PATH}) with offer_page, or "
                "point at it with point_at if they are already there."
            )
        found = "\n\n".join(
            f"[{i}] {_source(p)}\nurl: {p.url}\n{p.snippet}" for i, p in enumerate(passages, 1)
        )
        return (
            "From karnatakadigital.in. Answer only from this; if it does not answer the "
            f'question, say: "{DONT_KNOW}"\n\n{found}'
        )

    async def show_document(self, request: DocumentRequest) -> str:
        """Show a PDF document beside you as a card; it opens in a new tab. Name the
        document and the page in your one or two sentences and call this in the
        same response. For PDFs that search_kdem returned; pages are visited."""
        found = _page(request.url) if pdf_url(request.url) is not None else None
        if found is None:
            if _page(request.url) is not None:
                logger.info("kdem: show_document refused a page {!r}", request.url)
                return (
                    "Not sent: pages are visited with offer_page / go_to_page; "
                    "show_document is for PDFs."
                )
            logger.info("kdem: show_document refused {!r}", request.url)
            return (
                f"Not sent: {request.url!r} is not one of the approved KDEM documents. "
                "Show a PDF search_kdem returned."
            )
        url, title = found
        # Sent as the snippet's "show_link" card: the wire name it already renders.
        self.session.dispatch(ShowLink(url=url, title=title))
        logger.info("kdem: show_document {}", path_of(url))
        landed(*phrase(self.spoken, "shown"))
        return "ok"

    async def set_language(self, request: LanguageRequest) -> str:
        """Conduct the rest of the call in English or Kannada — both the listening and
        the speaking. Call it when they ask, and when a turn looks like the other
        one. Call it alone and say nothing: the voice changes when your response
        ends, and then a written line is said for you in the new voice."""
        speech = SPEECH[request.language]
        if speech.code == self.spoken:
            self._pending = None
            return f"Already in {speech.name}. Carry on."
        # Not sent here: a tool returns within its budget, and the switch has to
        # land before the line the new voice says. respond() makes it, awaited,
        # once this response has streamed.
        self._pending = speech
        logger.info("kdem: set_language {} (made when the response ends)", speech.name)
        return (
            f"Switching to {speech.name}. A written line is said for you in the new voice; "
            f"say nothing more. Speak {speech.name} from the visitor's next turn."
        )


__all__ = [
    "DONT_KNOW",
    "SWITCH_LINE",
    "TOGGLE_CONFIRM",
    "KdemBrain",
    "LanguageChanged",
    "Navigate",
    "PointAt",
    "ShowLink",
]
