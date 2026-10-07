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

**The model never supplies a URL the brain trusts.** :meth:`show_link` takes what
the model names, canonicalises it, and sends it only if the index holds that page
now — an approved page the last refresh read, a page it added, or a PDF an
approved page links to and the refresh read — with the page's own title, not
the model's. A listed page the refresh dropped (deleted,
unpublished, or redirecting elsewhere) is not sent; before the first index
exists, only Contact Us is. The browser snippet checks the host again, but the
brain is where "only approved pages" is decided.

**The page is someone else's.** There is no frontend here: the snippet in
``demos/kdem/embed/`` is pasted into the site, connects with
``init = {surface, page, lang}``, and renders exactly one command, ``show_link``.
So that is the only Action this brain sends. The call carries on across page
loads, and on every (re)connect the snippet sends ``page_viewed``
(:mod:`.app_events`): Aria learns the visitor moved, silently, on their next turn.

The knowledge base is one per process. The first session starts its keeper
(:meth:`~.knowledge.KnowledgeService.start`, idempotent and non-blocking); every
session after that reads the same index.
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
    PHRASES,
    FallbackLine,
    GeminiBrain,
    configure_soon,
    landed,
    needs_result_now,
    phrase,
)

from voqalize.sdk import Action, RTVIMessage, Session, Speech
from voqalize.sdk.wire import Config, IdleConfig, Language, SttConfig, TtsConfig

from .app_events import KDEM_EVENTS, PageViewed
from .content import CONTACT_PATH, OPENING, SPEECH, LanguageName, page_digest
from .knowledge import (
    ALLOWLIST,
    KNOWLEDGE,
    Passage,
    host_of,
    normalize,
    off_site,
    path_of,
    pdf_url,
)

AGENT_NAME = "Aria"

#: The language's name, spelled the way the English voice says it right. Written
#: "Kannada", the English clip reads the English word "Canada"; this respelling
#: comes out as kuh-nuh-daa. Spoken English only: tool arguments keep "kannada",
#: and in Kannada the name is written ಕನ್ನಡ, which the Kannada clip says right.
#: The speech server takes per-word respellings itself (`pronunciations`), but the
#: wire does not carry them yet, so the brain spells it where it speaks it.
KANNADA_SAID = "Kuh-nuh-daa"

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

EVERY RESPONSE STARTS WITH WORDS. Whenever you offer a page or switch the language, write your line first and make the call in that same response — the line is spoken as the link appears. A response that is only a tool call is silence: after show_link or set_language you do not speak again until the visitor does. For example:
  Visitor: "Do you have a seed fund for startups outside Bengaluru?" You: (search_kdem first, then) "Yes, the Beyond Bengaluru Cluster Seed Fund backs startups in the clusters. I've put the page beside me." — and show_link, in the same response.
search_kdem is the one call that takes no line: it is silent and comes straight back to you in the same turn, so call it first and then answer from it.

ANSWER ONLY FROM THE SITE. Everything you may say about KDEM, its programmes, policies, events, reports and news comes from what search_kdem returns. Search before you answer any question about KDEM or Karnataka's digital economy — even one you think you know. Never add a figure, a date, a deadline, an amount, an eligibility rule or a name that is not in what came back. If the search returns nothing that answers the question, say exactly: "{DONT_KNOW}" and offer the Contact Us page with show_link ({CONTACT_PATH}).

THE SHAPE OF AN ANSWER. One or two short sentences that answer the question, then offer the page that says it in full with show_link, in the same response. Do not read a page aloud; the link is there for that. Pass show_link a URL that search_kdem returned or one from THE PAGES below — never one you made up or one from outside karnatakadigital.in.

DOCUMENTS. Many results come from the PDF documents KDEM's pages link to — policies, guidelines, reports and newsletters — and are marked "PDF document, page N". When you answer from one, say which document and where, in words, for example "the Startup Policy says so on page 12", and offer it with show_link, passing the url exactly as search_kdem gave it. For a document on KDEM's site that url is the PDF itself. For one hosted on another government site, marked "on <site>", the url is the KDEM page that links to it, and the card opens that page: name the document and the page in what you say, and say it is linked from that KDEM page.

VOICE STYLE. Warm, plain and brief. No markdown, no lists, no symbols, no URLs read aloud — say "the Policies page", not its address. Say numbers as a person would. No throat-clearing: not "Great question", not "Sure, let me". English by default.

WHAT YOU DO NOT DO. Each of these gets one polite sentence and, where it helps, the Contact Us page:
- Politics, government decisions, ministers or officials, and opinions about any of them. You talk about what the site says, not about who decided it.
- Commitments on behalf of KDEM or the Government of Karnataka: no promises of funding, approval, a meeting, a timeline or an outcome.
- The status of any individual application, registration, payment or tender. You cannot see them; the KDEM team can.
- Legal, tax or investment advice beyond what the site's own documents say. Say what the document says and suggest they take advice.
- Personal data. Never ask for a name, phone number, email, address, ID number, OTP or password, and if they offer one, tell them you do not need it.
- Anything unrelated to KDEM and doing business in Karnataka: say briefly that it is outside what you can help with here.

LANGUAGE. The call starts in English, and English stays the main language. If the visitor asks for Kannada, or you can tell they are speaking Kannada, call set_language with kannada — say the line you switch with in English, in the same response, because it is spoken before the voice changes — and speak Kannada, in Kannada script, from their next turn on. When you are sure, do not ask permission first; when you are not, see SURE, OR NOT SURE below. While you are in English the recognizer only knows English, so Kannada arrives as English words forced onto Kannada sounds; a turn that makes no sense as English is usually Kannada, and the sounds that survive are words like "naanu", "nanna", "beku", "illa", "enu", "hesaru", "maadi", "gottilla". Ask them to say it again in your switch line, since those words were lost. In Kannada mode English arrives spelled in Kannada script ("ಐ ವಾಂಟ್ ..." is "I want ..."); judge by the small grammar words, not by nouns, and switch back to English with set_language when they speak or ask for English. Only English and Kannada are offered; if they ask for another language, say so in English. The site is in English, so always write search_kdem queries in English, whatever language the call is in.

SURE, OR NOT SURE
- Sure — they asked for Kannada, or a whole sentence is plainly Kannada: call set_language at once, in that turn, without asking, with one short line in the language the call is in now. Do not wait for a second turn.
- Not sure — a few words look like Kannada but the rest does not, or the turn is too short to tell: do NOT switch yet. Answer in English as usual, and end with one short question in both languages: "ಕನ್ನಡದಲ್ಲಿ ಮಾತಾಡೋಣವೇ? Shall we continue in {KANNADA_SAID}?". On a yes in either language ("yes", "haudu", "ಹೌದು", "sari", "ಸರಿ"), call set_language with kannada. Ask this at most once in a call; if they say no, stay in English and do not ask again.
- SAYING ITS NAME. Whenever you say the name of the language in English, write it "{KANNADA_SAID}", never "Kannada": the English voice reads "Kannada" as the country "Canada". So "Let's continue in {KANNADA_SAID}", "I can speak English or {KANNADA_SAID}". This is only how you write it in English speech; call set_language with kannada as always, and in Kannada write ಕನ್ನಡ.
- What does NOT count as switching: one borrowed English word inside a Kannada sentence ("ನನಗೆ startup fund ಬೇಕು" is still Kannada), or one Kannada word inside an English sentence. Judge by the whole sentence, not a word.

THE PAGES. These are the approved pages, by path, with their titles. Newer news and event pages may also come back from search_kdem; those are approved too.
"""

# The opener. Written, not generated: the visitor has just clicked, and a first
# word that waits on a model makes the site feel slow.
_GREETING = (
    f"Hello, I'm {AGENT_NAME} from KDEM. You can talk to me in English or {KANNADA_SAID}. "
    "How can we help you grow your business in Karnataka?"
)


def _prompt(where: str = "") -> str:
    """The system prompt for a session starting now. THE PAGES lists only the
    pages Aria may link at this moment, so the model is never offered one the
    refresh has dropped."""
    prompt = _SYSTEM_INSTRUCTION + page_digest(lambda url: _page(url) is not None)
    return f"{prompt}\n\nWHERE THEY ARE. {where}" if where else prompt


# ── The tool surface ──────────────────────────────────────────────────────────


class ShowLink(Action, name="show_link"):
    """Brain → browser: a link card to one KDEM page or PDF, opened in a new tab.

    The snippet in ``demos/kdem/embed/`` renders this and nothing else."""

    url: str
    """An absolute ``https://karnatakadigital.in/...`` URL, chosen by the brain: a
    page, or a PDF under ``/wp-content/uploads/``."""
    title: str
    """The page's own title, as the card shows it."""


class SearchRequest(BaseModel):
    query: str = Field(
        description="What the visitor wants to know, as a short search in English — "
        "the site is in English even when the call is in Kannada. Name the topic, "
        "e.g. 'seed fund for startups in Mysuru' or 'upcoming events'."
    )


class LinkRequest(BaseModel):
    url: str = Field(
        description="The page or PDF to offer: a URL that search_kdem returned, or a "
        "path from THE PAGES, e.g. '/policies/'. Only karnatakadigital.in pages and "
        "documents are sent."
    )
    title: str = Field(
        "",
        description="A few words naming the page. The card uses the page's own title "
        "when it has one.",
    )


class LanguageRequest(BaseModel):
    language: LanguageName = Field(
        description="The language to conduct the rest of the call in. Only English and "
        "Kannada are offered; if they ask for another, say so rather than picking one."
    )


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


def _link_url(p: Passage) -> str:
    """The url a search result offers: the page or PDF itself, or for a PDF on
    another site, the KDEM page that links it."""
    if p.kind == "pdf" and off_site(p.url) and (via := _via(p.url)) is not None:
        return via[0]
    return p.url


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

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        # Aria's voice — not the page's to choose, so it is settled here rather
        # than sent with the connect request. Both legs move together; the voice
        # is gauri in English and Kannada alike. This lands before the greeting.
        await session.configure(
            Config(
                stt=SttConfig(language=OPENING.code, patience=2),
                tts=TtsConfig(voice=OPENING.voice, language=OPENING.code),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
            )
        )
        # One keeper per process: the first session starts it, the rest find it
        # running. It never makes this session wait.
        KNOWLEDGE.start()

        init = dict(session.init or {})
        self.system_instruction = _prompt(_where_they_started(init))
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
        """The opener, written not generated."""
        return _GREETING

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The model's turn, and a line of Aria's own if it acted and said nothing.
        See :mod:`voqalize_demos.silent_turn`."""
        async for event in self._fallback.speak_if_silent(self, super().respond(session)):
            yield event

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

    def _viewed(self, event: PageViewed) -> None:
        here = normalize(event.path)
        if here is None or here == self.here:
            # Not a page of this site, or the one already known: the reconnect
            # on the page the call started on says nothing new.
            return
        self.here = here
        line = _where_they_are(event.path, moved=True)
        logger.info(
            "kdem: page_viewed {} ({})", path_of(here), "named" if _page(here) else "unnamed"
        )
        self.system_instruction = _prompt(line)
        self.append_to_context(types.Content(role="user", parts=[types.Part(text=f"[{line}]")]))

    # ─── Tools ──────────────────────────────────────────────────────────
    #
    # All three read memory and return inside the tool budget. Only the search
    # is marked: Aria cannot answer without what it returns. The link and the
    # language switch are spoken with, in the same response.

    @property
    def tools(self) -> list[Any]:
        """Search the approved pages, offer one as a link, change language."""
        return [self.search_kdem, self.show_link, self.set_language]

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
                f'answer from. Say: "{DONT_KNOW}" and offer the Contact Us page '
                f"({CONTACT_PATH}) with show_link."
            )
        passages = kb.search(request.query, k=_PASSAGES)
        logger.info("kdem: search {!r} -> {} passages", request.query, len(passages))
        if not passages:
            return (
                f'Nothing on the approved pages matches. Say: "{DONT_KNOW}" and offer the '
                f"Contact Us page ({CONTACT_PATH}) with show_link."
            )
        found = "\n\n".join(
            f"[{i}] {_source(p)}\nurl: {_link_url(p)}\n{p.snippet}"
            for i, p in enumerate(passages, 1)
        )
        return (
            "From karnatakadigital.in. Answer only from this; if it does not answer the "
            f'question, say: "{DONT_KNOW}"\n\n{found}'
        )

    async def show_link(self, request: LinkRequest) -> str:
        """Put a link card to one KDEM page or PDF document beside you; it opens in a
        new tab. Say your one or two sentences and call this in the same response.
        Only approved karnatakadigital.in pages and the PDFs they link to are sent."""
        found = _page(request.url)
        if found is None:
            logger.info("kdem: show_link refused {!r}", request.url)
            return (
                f"Not sent: {request.url!r} is not one of the approved KDEM pages or "
                "documents. Offer a page or PDF search_kdem returned, or the Contact Us "
                f"page ({CONTACT_PATH})."
            )
        url, title = found
        self.session.dispatch(ShowLink(url=url, title=title))
        landed(*phrase(self.spoken, "shown"))
        return "ok"

    async def set_language(self, request: LanguageRequest) -> str:
        """Conduct the rest of the call in English or Kannada — both the listening and
        the speaking. Call it when they ask, and when you believe they are already
        speaking the other one. In the same response, say one short line in the
        language the call is in now, before calling."""
        speech = SPEECH[request.language]
        # Sent, not awaited: the answer is a round trip and a tool has to return
        # within the budget. A refusal is logged and the call goes on as it was.
        configure_soon(
            self.session,
            Config(
                stt=SttConfig(language=speech.code),
                tts=TtsConfig(voice=speech.voice, language=speech.code),
            ),
        )
        self.spoken = speech.code
        logger.info("kdem: language -> {}", request.language)
        return "ok"


__all__ = ["DONT_KNOW", "KdemBrain", "ShowLink"]
