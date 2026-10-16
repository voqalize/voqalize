"""SendPotionBrain — Tushar, a guide on sendpotion.com and its blog.

The site is SendPotion's, not ours. A browser extension injects the widget and a
small adapter into sendpotion.com and blog.sendpotion.com; the adapter turns
each :class:`~voqalize.sdk.Action` below into a move on the tab in front — a
page, a section scrolled to and ringed, an FAQ opened, the demo calendar on
/demo/ with a day, a time and the visitor's details filled in — and the call
itself opens the blog posts he recommends in new tabs. Every tab reports what it
shows as a typed event (:mod:`.app_events`), whichever of the visitor and
Tushar moved it.

Four things shape every decision here.

**A guide, not a search box.** Every turn answers what was asked, in words, as
a conversation: the answer, why it matters for this visitor, and a question
back that moves them on. A move on the page goes beside the answer and is
talked about, never just pointed at. Asked to walk them through, he gives a
tour, one stop per turn, and asks before the next one.

**Every fact has a source.** A price, a limit, a feature or an integration is
spoken from L1 (in this prompt), an L2 topic he read, a search of the site, or
what the page itself reported. Never from memory.

**Nothing on the page is invented.** A path he navigates to, a heading he
scrolls to, an FAQ he opens and a blog post he recommends are checked against
the crawl and against what the tab last reported; anything else is refused
before it reaches the page.

**The booking is the visitor's.** He picks the day and time they asked for and
fills in what they told him; he never asks for an email, and never presses
Schedule Event.

How a result that arrives after his turn gets spoken — the demo calendar's open
days, a submitted booking — is in :meth:`SendPotionBrain.on_user_idle`.
"""

from __future__ import annotations

import inspect
import re
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any, Literal

from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel, Field
from voqalize_demos import (
    DEFAULT_MODEL,
    PATIENCE,
    FallbackLine,
    GeminiBrain,
    configure_soon,
    landed,
    needs_result_now,
    phrase,
    say_line,
)
from voqalize_demos.acknowledge import Acknowledger, Kind, Vocabulary, hold_the_floor

from voqalize.sdk import Action, RTVIMessage, RTVIType, Session, Speech, UserIdle, UserMessage
from voqalize.sdk.wire import Config, IdleConfig, Language, SttConfig, TtsConfig, Voice

from . import knowledge as kb
from .app_events import (
    SENDPOTION_EVENTS,
    CommandFailed,
    DemoScheduled,
    DemoState,
    PageChanged,
    SendPotionEvent,
    TabInfo,
    TabsChanged,
)
from .knowledge import TOPIC_IDS, Knowledge, canonical_path, norm

AGENT_NAME = "Tushar"

#: LOW, as Saatvik measured: at MINIMAL, Gemini mostly made the page call first
#: and wrote nothing; at LOW it writes the answer first and calls at the end, so
#: the page moves while he is still talking.
THINKING = types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)
#: The one extra request a silent page move gets: tools declared, none callable.
_TALK_NOW = types.ToolConfig(
    function_calling_config=types.FunctionCallingConfig(mode=types.FunctionCallingConfigMode.NONE)
)

# ─── Voice and timing ──────────────────────────────────────────────────────────

#: Tushar's voice, in English: the speech tier's Indian-English male persona,
#: the one Saatvik's Tushar speaks with.
VOICE = Voice.OMNIVOICE_GAURAV
LANGUAGE = Language.EN

#: A quiet visitor is someone reading a page or a post; a guide beside them says
#: something after a while, and not twice more.
_IDLE_MS = 20_000
_IDLE_NUDGES = 2
#: The idle window while a result the page produced is waiting to be talked
#: through (the demo calendar's open days): a visitor who reacts speaks first,
#: one who is reading hears it from him.
_TALK_THROUGH_MS = 2_000
#: A little more patience than the demos' default, as Saatvik's: a visitor
#: thinking aloud about their use case pauses mid-sentence.
SENDPOTION_PATIENCE = PATIENCE + 2
#: A message this soon after the last one is the rest of the same thought.
_FRAGMENT_S = 4.0

# ─── Actions (brain → page) ────────────────────────────────────────────────────


class Navigate(Action):
    """Go to one of sendpotion.com's pages and, with ``heading`` or ``text``,
    scroll to that section and ring it. The page reports ``page_changed``."""

    path: str
    heading: str | None = None
    text: str | None = None


class ShowSection(Action):
    """On the tab in front, scroll to the heading named ``heading`` and ring its
    section; with ``text``, ring the smallest element containing that text (a
    plan card, a feature, a line of a post)."""

    heading: str | None = None
    text: str | None = None


class OpenFaq(Action):
    """Open the FAQ that starts with ``question`` on the page in front, and ring it."""

    question: str


class ReadingItem(BaseModel):
    url: str
    title: str
    why: str | None = None


class OpenPosts(Action):
    """Show ``posts`` in the widget's reading list, on every tab, under
    ``heading``; and open ``open`` (one of them) in a new tab."""

    heading: str
    posts: list[ReadingItem]
    open: str | None = None


class OpenPost(Action):
    """Open one blog post — in the tab that already shows it, or a new one —
    and, with ``heading``, scroll to that section of it."""

    url: str
    heading: str | None = None


class BookDemo(Action):
    """Open /demo/ and, in its Calendly calendar, choose ``day`` and ``time`` and
    fill in the details given. The page reports ``demo_state``; it never
    presses Schedule Event."""

    day: str | None = None
    time: str | None = None
    name: str | None = None
    email: str | None = None
    notes: str | None = None


class OpenSignup(Action):
    """Open the Potion app's sign-up (app.sendpotion.com) in a new tab."""


class FocusTab(Action):
    """Bring one of the visitor's SendPotion tabs to the front."""

    tab_id: str


# ─── Tool requests ─────────────────────────────────────────────────────────────

if TYPE_CHECKING:
    TopicId = str
else:
    # The L2 files present at import, as the tool's enum; see knowledge.TOPIC_IDS.
    TopicId = Literal[TOPIC_IDS]


class TopicRequest(BaseModel):
    topic: TopicId = Field(description="The topic to read, by its name.")


class SearchRequest(BaseModel):
    query: str = Field(
        description="A few words to look for on sendpotion.com, e.g. 'HubSpot integration', "
        "'video length limit', 'real estate'."
    )


class PostSearchRequest(BaseModel):
    use_case: str = Field(
        description="What the visitor wants to do or learn, in a few words, e.g. 'cold "
        "outreach for agencies', 'video sales letter mistakes', 'real estate follow-ups'."
    )


class NavigateRequest(BaseModel):
    path: str = Field(
        description="A page path from the site pages list or a search result, e.g. "
        "'/pricing'. Never a path you made up."
    )
    heading: str | None = Field(
        default=None,
        description="Optional: a section heading on that page to scroll to, from the site "
        "pages list or a search result.",
    )
    text: str | None = Field(
        default=None,
        description="Optional: a few words on that page to scroll to and ring instead, e.g. "
        "a plan name like 'Professional'.",
    )


class SectionRequest(BaseModel):
    heading: str | None = Field(
        default=None, description="A heading on the page the visitor has in front."
    )
    text: str | None = Field(
        default=None,
        description="Optional: a few words on that page to ring, e.g. a plan name or a "
        "feature, inside the heading's section when both are given.",
    )


class FaqRequest(BaseModel):
    question: str = Field(description="An FAQ question on the page the visitor has in front.")


class PickedPost(BaseModel):
    url: str = Field(description="The post's url, from find_blog_posts.")
    why: str = Field(
        description="Why it fits this visitor, in under ten words, e.g. 'Ten VSL mistakes to skip'."
    )


class RecommendRequest(BaseModel):
    heading: str = Field(
        description="A short title for the reading list, e.g. 'For agency outreach'."
    )
    posts: list[PickedPost] = Field(description="Two to four posts, best first.")
    open_first: bool = Field(
        default=True, description="Open the first post in a new tab for them now."
    )


class OpenPostRequest(BaseModel):
    url: str = Field(description="The post's url, from find_blog_posts.")
    heading: str | None = Field(
        default=None, description="Optional: a heading inside that post to scroll to."
    )


class DemoRequest(BaseModel):
    """Only what the visitor said: leave out anything they did not."""

    day: str | None = Field(
        default=None,
        description="An open day as the calendar lists it, e.g. 'Tuesday, October 20', or "
        "as the visitor said it ('next Tuesday' resolved to a listed day).",
    )
    time: str | None = Field(default=None, description="e.g. '3:00pm', only if they said.")
    name: str | None = Field(default=None, description="Only if the visitor said it.")
    email: str | None = Field(default=None, description="Only if the visitor said it.")
    notes: str | None = Field(
        default=None,
        description="One or two sentences for SendPotion's team: who they are and what "
        "they want videos for, in their terms.",
    )


class TabRequest(BaseModel):
    tab_id: str = Field(description="The tab_id from the open tabs list.")


# ─── The prompt ────────────────────────────────────────────────────────────────

_SITE_MAP_CHARS = 7000
_SECTIONS_PER_PAGE = 8
_TITLE_SUFFIXES = (" | Potion", " — Potion", " - Potion")


def _short_title(title: str) -> str:
    for suffix in _TITLE_SUFFIXES:
        title = title.removesuffix(suffix)
    return title.split(" | ")[0].strip()


def _site_map(k: Knowledge) -> str:
    lines: list[str] = []
    size = 0
    for p in sorted(k.pages.values(), key=lambda p: (p.path.count("/"), p.path)):
        heads = "; ".join(p.headings[:_SECTIONS_PER_PAGE])
        line = f"- {p.path} — {_short_title(p.title)}" + (f" (sections: {heads})" if heads else "")
        size += len(line) + 1
        if size > _SITE_MAP_CHARS:
            break
        lines.append(line)
    return "\n".join(lines) or "(The site map is not loaded: find pages with search_site.)"


def _topics(k: Knowledge) -> str:
    return "\n".join(f"- {t.id}: {t.title}" for t in k.topics.values()) or "(none loaded)"


def _prompt(k: Knowledge) -> str:
    return f"""You are {AGENT_NAME}, the guide on SendPotion's website, sendpotion.com, and its blog, blog.sendpotion.com. SendPotion's product is called Potion. A visitor is browsing the site right now and has called you from the corner of the page. You can see and move their screen: you open pages, scroll to the exact section that answers them and ring it, open FAQs, book a demo with them on the calendar, and open the blog posts that fit their use case in a new tab. You are warm, sharp and conversational — the product specialist who knows Potion inside out, explains it in plain words, relates it to the visitor's own work, and keeps the conversation going. Understanding Potion should feel easy and personal after talking to you.

# A good turn has three parts
1. Answer what they asked, first, in plain words, and say why it matters for them.
2. Show it, and talk about it. When a page or a section fits, move the page in the same response, to the exact section — navigate with a heading, or show_section on the page they are on — and name one concrete thing there that matters for them: "See the bulk generation part? That's how one video becomes five hundred personal ones." Never read the page out. Never say only "here it is" or "here's the page": the screen moving already says that. A reply that only points at the screen is a failed turn.
3. Hand it back. End with one short question that moves the conversation on: about their work (who they sell to, how they reach prospects now, how many videos they'd send), or the natural next step ("Want to see how it plugs into your CRM?"). Vary it. Never end with "anything else?" or "let me know if you have questions".

# Be a guide, not a search box
- Clarify before you guess. When a question could mean two things, or the right answer depends on who they are, ask one short question first — and still give the most likely answer in a sentence. "For sales teams it's mostly cold outreach. Are you selling, or marketing?"
- Learn who they are as you go: their role, their team size, what they sell, who they reach, what they use now. Use it in every later answer. Never ask again for something they already said.
- When they ask you to walk them through, show them around, or give a tour: take them through it one stop per turn, each stop a page and a section, in this order unless what they told you suggests better: what Potion does on the home page, how it works, the features, the use case closest to theirs, integrations, pricing, and booking a demo. At each stop, two or three sentences on what matters for them, then ask whether to go on or dig in. Never do two stops in one turn.
- When they ask how to do something, or how something works, explain it step by step, one short step per sentence, while you show the section.
- If something isn't on SendPotion's site, say so plainly and offer what is.

# How you sound
You are heard, not read, so keep it light and warm.
- A turn is three or four short sentences, about forty words. Go longer, five to eight short sentences, only when they ask you to explain, tell them more, or walk them through.
- Every sentence under fifteen words. Small, everyday words. One idea per sentence. One number per sentence.
- THE FIRST SENTENCE IS A FEW WORDS. The visitor hears nothing until your first sentence has been voiced, so open every reply with a sentence of two to six words that ends in a full stop, with the answer in it.
- Before most replies the visitor has already heard a short acknowledgement of mine — "Sure.", "Let me see." — so never open with one: your first word is the answer. No "great question", no repeating their question back.
- Spoken words only: no lists, no markdown, no symbols, never an exclamation mark. Write numbers and prices as spoken words: "forty-nine dollars a month", never "$49/mo".
- Lines in square brackets come from their screen, not the visitor: what they opened, what the calendar shows. Never read them out; use them.

# Every response starts with words
Write your whole answer first, then make the page calls at the end of the same response. The page moves while you are still talking. A response that is only tool calls is silence. What a page call returns reaches you only on your next turn.
- The exception is a read: read_topic, search_site and find_blog_posts come straight back to you within this same turn. When you need one, call it first, with nothing written before it, then give your one reply, the answer and the move, once it is back.
- Never promise more to come ("let me check", "let me find that"): nothing comes after it. Talk about what they see as already there.

# What that sounds like
Visitor: "What does Potion actually do?"
You: "It makes videos of you, without filming each one. Potion learns your face, voice and gestures. Then it makes personal videos for each prospect, by name. See how it works, in three steps? Who would you send videos like that to?" then navigate(path="/", heading="How Potion works").
Visitor: "How much does it cost?"
You: "Plans start at thirty-nine dollars a month. That's two hundred and fifty videos. Professional, at two ninety-nine, is unlimited. Every plan has a seven-day free trial. How many videos would you send a month?" then navigate(path="/pricing", heading="Pricing plans").
Visitor: "Does it work with HubSpot?"
You: "Yes, it does. Potion connects to HubSpot, so your contacts flow into your videos. You'll see it in the integrations list. Which tool do you run your outreach from today?" then navigate(path="/integrations", text="HubSpot").
Visitor: "I run a small agency and want more clients."
You: "Then outreach is your use case. Agencies use Potion to send a personal video to each prospect. It gets far more replies than a plain email. I've put a few posts on agency growth beside me, and opened the best one for you. How do you reach prospects today?" then find_blog_posts first, then recommend_posts with what it returned.
Visitor: "Walk me through it."
You: "Happy to. We'll start with the big idea. Potion clones you, so one recording becomes many personal videos. See "Clone yourself" on screen? Next I'd show you how it works. Shall we go on?" then navigate(path="/", heading="Clone yourself").

# What you know
- Every fact — a price, a limit, a feature, an integration, a language, a security claim — comes from the knowledge below, a topic you read, a search result, or what the page reported. Never from memory. If you cannot find it, say so, and say where on SendPotion's site it might be.
- Read a topic with read_topic before answering anything it covers beyond what is below. Topics:
{_topics(k)}
- For a specific feature, page or question, search_site. Its results name the page and section to take them to.

# Moving the page
- navigate only to a path from the site pages list below or a search result. Always pass the heading of the section that answers them, or text to ring, so their screen lands on the answer, not the top of a page. show_section and open_faq take a heading, text or question on the page in front.
- To go to the top of a page they are already on, navigate to it with no heading.
- The visitor can also ask you to press things: "scroll to pricing", "open that FAQ", "go back to features", "show me the Starter plan". Do it with your tools, in the same response as your words, and say what is now on their screen. Never say you cannot scroll or click.
- "Try for free", "sign up" or "log in" is open_signup, which opens Potion's app in a new tab. Only when they ask for it.

# The blog
- SendPotion's blog has posts on outreach, sales, marketing, agencies, video sales letters, case studies and more. When the visitor describes a use case, a problem or an industry, find_blog_posts for it, then recommend_posts with the two to four that fit best: they appear in a reading list beside you on every tab, and the first opens in a new tab. Say in a sentence what the opened post covers and why it fits them.
- Recommend only posts find_blog_posts returned, by their url. Never invent a title.
- On a post, talk about what the post says: show_section takes its headings. To take them to one part of another post, open_post with its heading.
- When they ask for case studies or proof, look for case study posts.

# Tabs
- The visitor may have several SendPotion tabs open, on the site and the blog. Lines in brackets tell you which tabs are open and which is in front. Your moves happen on the tab in front; a move to a site page from a blog tab goes to their site tab.
- "Go back to the pricing tab" or "show me the other tab" is switch_tab with that tab's id.

# Booking a demo
- Offer a demo only when they ask for one, ask to talk to someone, or ask about Enterprise or a custom plan. You are here to guide them yourself, as far as they want to go.
- When they want one, book_demo with whatever they have already said: it opens /demo/ and its calendar. The open days come back to you: say two or three of them, and ask which day and time suits them. Then book_demo again with their day and time, and any name, email or notes they gave, and it fills the calendar. What is filled stays; you only add.
- Never ask them to read out their email. When they say a name or email, fill it in with book_demo, then read the email back so they can check it: "I've put jane at acme dot com. Is that right?"
- The notes are for SendPotion's team: one or two sentences on who they are and what they want videos for, from what they told you. Fill them in when the details step opens.
- Schedule Event stays theirs to press, always. When the details are filled, tell them what's left and that they press Schedule Event themselves. Never say it is booked until the page tells you.

# SendPotion
{k.l1}

# Site pages
{_site_map(k)}
"""


# ─── Greeting ──────────────────────────────────────────────────────────────────

_INTRO = f"Hi, I'm {AGENT_NAME}, your guide to Potion."
_GREETING = f"{_INTRO} I can walk you through it, or take you straight to what you need. What brings you here today?"
#: The opener's second sentence for the page the call starts on, by a word in
#: its path; the first match wins, and anything else gets the plain greeting.
_OPENERS: tuple[tuple[str, str], ...] = (
    ("pricing", "I can help you pick a plan. How many people would be making videos?"),
    ("demo", "I can book this demo with you. Which day suits you?"),
    ("integrations", "Tell me which tools you use, and I'll show you how Potion fits in."),
    ("features", "Ask me about anything here, or I can walk you through it."),
    ("use-cases", "Tell me what you do, and I'll show you the use case that fits."),
    ("faq", "Ask me anything, and I'll open the answer for you."),
)
_BLOG_GREETING = f"{_INTRO} Tell me what you're working on, and I'll find the posts that fit it."


def greeting(path: str | None, site: str | None) -> str:
    """The written opener, tailored to the page the call starts on."""
    if site == "blog":
        return _BLOG_GREETING
    here = canonical_path(path or "/")
    return next((f"{_INTRO} {line}" for word, line in _OPENERS if word in here), _GREETING)


# ─── Written lines for moves ───────────────────────────────────────────────────

#: His line for a silent turn whose move is not "here it is".
_LANDED: dict[str, tuple[str, ...]] = {
    "demo": ("Here's the demo calendar.",),
    "demo_filled": ("I've filled that in on the calendar.",),
    "posts": ("I've opened the best fit in a new tab.",),
    "signup": ("I've opened the sign-up in a new tab.",),
    "tab": ("There's that tab.",),
}

# ─── His nod ───────────────────────────────────────────────────────────────────

_ACK_LINES: dict[Language, dict[Kind, tuple[str, ...]]] = {
    Language.EN: {
        "request": ("Sure.", "Okay.", "Of course.", "Certainly."),
        "question": ("Let me see.", "Hmm, let me see.", "Okay."),
        "correction": ("I see.", "Understood.", "Right."),
        "statement": ("Okay.", "Got it.", "Right."),
    },
}
ACK_RATE = 0.75
ACK_HOLD_AFTER_S = 4.0
_ACK_HOLD = {Language.EN: ("One moment.", "Just a moment.")}
_ACK_SORRY = {Language.EN: "Sorry, that's taking a little longer."}
#: A visitor's ordinary words about Potion, so the reading trusts them.
_ACK_WORDS = Vocabulary(
    common=frozenset(
        # A word list reads as words, so it stays a split string.
        """potion sendpotion video videos ai personalized personalised outreach prospect
        prospects prospecting sales marketing email emails crm hubspot salesforce linkedin
        pricing price plan plans cost demo agency agencies campaign campaigns blog post
        posts avatar avatars voice clone integration integrations reply replies leads
        """.split()  # noqa: SIM905
    ),
)


def _avatar_state(session: Session, state: Literal["WORKING"] | None) -> None:
    """The talking head's working latch: held until speech owed has played."""
    session.send_rtvi(RTVIType.SERVER_MESSAGE, {"type": "avatar", "cmd": "state", "state": state})


_HEADINGS_IN_NOTE = 24
_FAQS_IN_NOTE = 12
_SEARCH_HITS = 6
_POST_HITS = 6
_DAYS_IN_NOTE = 10
_TIMES_IN_NOTE = 16


async def _silence() -> AsyncGenerator[Any, None]:
    for _ in ():
        yield


def _clip(items: list[str] | tuple[str, ...], most: int) -> str:
    more = f"; and {len(items) - most} more" if len(items) > most else ""
    return "; ".join(items[:most]) + more


def _match(want: str, options: list[str] | tuple[str, ...]) -> str | None:
    """The option ``want`` names: the same words, else the one it begins, else
    the one it is inside — how the page itself matches. Punctuation does not
    count: "tuesday october 20" is "Tuesday, October 20"."""

    def fold(s: str) -> str:
        return " ".join(re.sub(r"[^\w\s]", " ", norm(s)).split())

    w = fold(want)
    if not w:
        return None
    folded = [(fold(o), o) for o in options]
    for test in (
        lambda o: o == w,
        lambda o: o.startswith(w),
        lambda o: w.startswith(o) and len(o) > len(w) // 2,
        lambda o: w in o,
    ):
        if (hit := next((o for f, o in folded if test(f)), None)) is not None:
            return hit
    return None


def _site_path(path: str) -> str:
    """The path as the site links it: with its trailing slash."""
    return "/" if path == "/" else f"{path}/"


# ─── The brain ─────────────────────────────────────────────────────────────────


class SendPotionBrain(GeminiBrain):
    """One per session. Tushar: SendPotion's knowledge, its pages and posts, and
    a mirror of the visitor's tabs."""

    def __init__(
        self,
        *,
        client: genai.Client,
        model: str = DEFAULT_MODEL,
        knowledge: Knowledge | None = None,
    ) -> None:
        self.kb = knowledge if knowledge is not None else kb.KNOWLEDGE
        super().__init__(client=client, system_instruction=_prompt(self.kb), model=model)
        self._config = self._config.model_copy(update={"thinking_config": THINKING})
        self._forced: types.ToolConfig | None = None
        self._heard_at = float("-inf")
        self._fallback = FallbackLine()
        self._ack = Acknowledger(
            _ACK_LINES, _ACK_HOLD, _ACK_SORRY, _ACK_WORDS, ACK_RATE, ACK_HOLD_AFTER_S
        )
        #: The tab in front as it last reported itself, and whether the model
        #: has seen it since it changed.
        self.page: PageChanged | None = None
        self._path = "/"
        self._site = "site"
        self._page_unseen = False
        #: Every open SendPotion tab, and which is in front.
        self.tabs: list[TabInfo] = []
        self._active = ""
        self._tabs_unseen = False
        #: The demo booking as the calendar last reported it.
        self.demo: DemoState | None = None
        self._demo_fields: dict[str, str] = {}
        #: Post urls find_blog_posts has shown the model this call.
        self._found_posts: list[str] = []
        self._talk: str | None = None
        self._idle_short = False
        self._nudges = 0

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        init = session.init or {}
        self._path = canonical_path(str(init.get("path") or "/"))
        self._site = "blog" if init.get("site") == "blog" else "site"
        await session.configure(
            Config(
                stt=SttConfig(language=LANGUAGE, patience=SENDPOTION_PATIENCE),
                tts=TtsConfig(voice=VOICE, language=LANGUAGE),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
            )
        )
        logger.info("sendpotion: session start on {} {}", self._site, self._path)

    async def greet(self, session: Session) -> str:
        """The opener, written not generated."""
        return greeting(self._path, self._site)

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[Speech, None]:
        """The tab they moved to is read in with what they said; his nod covers
        the model's thinking."""
        self._talk = None
        self._nudges = 0
        self._restore_idle()
        self._read_in_screen()
        now = time.monotonic()
        fragment, self._heard_at = now - self._heard_at < _FRAGMENT_S, now
        if not fragment and (nod := self._ack.line(msg.text, LANGUAGE)) is not None:
            logger.info("sendpotion: ack {!r}", nod)
            async for event in say_line(self, nod):
                yield event
            working = True

            def answered() -> None:
                nonlocal working
                if working:
                    working = False
                    _avatar_state(session, None)

            _avatar_state(session, "WORKING")
            try:
                turn = super().on_user_message(session, msg)
                async for event in hold_the_floor(
                    self, self._ack, lambda: LANGUAGE, turn, answered
                ):
                    yield event
            finally:
                answered()
            return
        async for event in super().on_user_message(session, msg):
            yield event

    def on_user_idle(self, session: Session, idle: UserIdle) -> AsyncGenerator[Speech, None]:
        """A quiet spell — the only floor he gets without the visitor speaking.

        A result the page produced after his turn (the calendar's open days, a
        press of Schedule Event) is put in the context at once and the idle
        window shortened, so a reading visitor hears it from him here. Otherwise
        an ordinary quiet spell: a nudge, twice, then silence."""
        self._restore_idle()
        if self._talk is not None:
            ask, self._talk = self._talk, None
            self._note(ask)
            return self.respond(session)
        if self._nudges >= _IDLE_NUDGES:
            return _silence()
        self._nudges += 1
        self._read_in_screen()
        quiet = f"The visitor has said nothing for about {round(idle.idle_ms / 1000)} seconds."
        if self._nudges == 1:
            ask = (
                "Speak into the quiet, briefly, as the guide beside them would: one useful thing "
                "about what is on their screen, or one question that helps you help them. Never "
                "ask whether they are still there, and never repeat your last line."
            )
        else:
            ask = (
                "Still quiet. One last, light offer, different from your last: something you "
                "could show them next, or posts that fit their use case. Then let them browse."
            )
        self._note(f"{quiet} {ask}")
        return self.respond(session)

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The model's turn. If it moved the page and said nothing, the model is
        asked once more with tools off, so he talks about what he just showed;
        only if that is silent too does he say a written line of his own."""
        turn = self._fallback.speak_if_silent(
            self, super().respond(session), again=lambda: self._talk_now(session)
        )
        async for event in turn:
            yield event

    async def _talk_now(self, session: Session) -> AsyncGenerator[Speech, None]:
        self._forced = _TALK_NOW
        try:
            async for event in super().respond(session):
                yield event
        finally:
            self._forced = None

    def _turn_config(self) -> types.GenerateContentConfig:
        config = super()._turn_config()
        if self._forced is None:
            return config
        return config.model_copy(update={"tool_config": self._forced})

    async def _run(self, tool: Any, call: types.FunctionCall) -> types.Part:
        """Every tool takes one model, ``request``; Gemini sometimes sends its
        fields flat, which the SDK refuses. Wrap them before the call runs."""
        args = dict(call.args or {})
        if (
            tool is not None
            and args
            and "request" not in args
            and "request" in inspect.signature(tool).parameters
        ):
            logger.info("sendpotion: {} called with flat arguments; wrapping them", call.name)
            call = call.model_copy(update={"args": {"request": args}})
        return await super()._run(tool, call)

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Page→brain events, folded in silently: no floor taken, no turn."""
        event = SENDPOTION_EVENTS.parse(msg)
        if event is None:
            return
        logger.info("sendpotion: {} — {}", type(event).__voqal_event__, event)
        if (note := self.apply_event(event)) is not None:
            self._note(note)

    # ─── Page → brain ───────────────────────────────────────────────────

    def apply_event(self, event: SendPotionEvent) -> str | None:
        """Patch the mirror; return the line the model should see."""
        match event:
            case PageChanged():
                self.page = event
                self._path = canonical_path(event.path)
                self._site = event.site
                self._page_unseen = True
                # Read in with their next message or quiet spell: they may click
                # on before they speak, and only the last page matters.
                return None
            case TabsChanged():
                self.tabs = event.tabs
                self._active = event.active
                self._tabs_unseen = True
                return None
            case DemoState():
                return self._demo_changed(event)
            case DemoScheduled():
                self._talk_through(
                    "They have just pressed Schedule Event. Thank them in one sentence, say "
                    "SendPotion's team will see them then, and offer to keep answering questions."
                    if not event.blocked
                    else "They have just pressed Schedule Event on the demo calendar. This is a "
                    "preview, so the page held it back: say so in one sentence, thank them, and "
                    "offer to keep answering questions."
                )
                when = " ".join(x for x in (event.date, event.time) if x)
                held = (
                    " This preview held it back from SendPotion's calendar."
                    if event.blocked
                    else ""
                )
                return (
                    f"[The visitor pressed Schedule Event for {when or 'the chosen slot'}.{held}]"
                )
            case CommandFailed():
                if event.command == "book_demo":
                    self._talk = None
                    self._restore_idle()
                return (
                    f"[That did not happen on the page ({event.command}: {event.reason}). "
                    "Tell the visitor plainly and offer what you can do instead; never say it "
                    "worked.]"
                )

    def _demo_changed(self, event: DemoState) -> str | None:
        before = self.demo
        self.demo = event
        if event.step == "details":
            filled = [k for k, v in event.filled.model_dump().items() if v]
            note = (
                f"[The demo calendar is at its details step for {event.date} at {event.time} "
                f"({event.timezone or 'their time zone'}). Filled: {', '.join(filled) or 'nothing'}. "
                f"Still empty: {', '.join(event.missing) or 'nothing required'}. The visitor "
                "presses Schedule Event themselves.]"
            )
            if before is None or before.step != "details":
                self._talk_through(
                    "The calendar's details step is on their screen and they have not spoken. "
                    "Say the day and time back to them in one sentence, say what is still empty, "
                    "and that Schedule Event is theirs to press."
                )
            return note
        if event.step == "scheduled":
            return "[The demo calendar shows the meeting as scheduled.]"
        days = _clip(event.days, _DAYS_IN_NOTE) or "none this month"
        note = f"[The demo calendar shows {event.month or 'this month'}. Open days: {days}."
        if event.date and event.times:
            note += f" Times on {event.date}: {_clip(event.times, _TIMES_IN_NOTE)}."
        if event.timezone:
            note += f" Times are in {event.timezone}."
        note += "]"
        if before is None or (before.days != event.days and not before.date):
            self._talk_through(
                "The demo calendar is on their screen and they have not spoken. Name two or three "
                "of its open days in one sentence, and ask which day and time suit them."
            )
        return note

    def _read_in_screen(self) -> None:
        """The tabs and the page in front, once per change, ahead of what they say."""
        if self._tabs_unseen and len(self.tabs) > 1:
            listed = "; ".join(
                f"{t.tab_id}: {t.title or t.url}"
                + (" (in front)" if t.tab_id == self._active else "")
                for t in self.tabs
            )
            self._note(f"[The visitor's open SendPotion tabs — {listed}.]")
        self._tabs_unseen = False
        if not self._page_unseen or self.page is None:
            return
        self._page_unseen = False
        p = self.page
        where = (
            "a blog post" if p.kind == "post" else "the blog" if p.site == "blog" else "the site"
        )
        note = f"[The tab in front shows {where}: “{p.title or p.path}” ({p.url or p.path})."
        if p.headings:
            note += f" Its headings: {_clip(p.headings, _HEADINGS_IN_NOTE)}."
        if p.faqs:
            note += f" Its FAQs: {_clip(p.faqs, _FAQS_IN_NOTE)}."
        if p.plans:
            note += f" Its plans: {', '.join(p.plans)}."
        self._note(note + "]")

    def _note(self, text: str) -> None:
        self.append_to_context(types.Content(role="user", parts=[types.Part(text=text)]))

    def _talk_through(self, ask: str) -> None:
        self._talk = ask
        if not self._idle_short:
            self._idle_short = True
            configure_soon(self.session, Config(idle=IdleConfig(timeout_ms=_TALK_THROUGH_MS)))

    def _restore_idle(self) -> None:
        if self._idle_short:
            self._idle_short = False
            configure_soon(self.session, Config(idle=IdleConfig(timeout_ms=_IDLE_MS)))

    def _move(self, action: Action, line: str | None = None) -> None:
        """Dispatch ``action``, with the written line for it should the turn say
        nothing."""
        self.session.dispatch(action)
        if line is not None:
            landed(line)
        else:
            landed(*phrase(LANGUAGE, "shown"))

    def _headings(self) -> tuple[str, ...]:
        if self.page is not None:
            return tuple(self.page.headings)
        page = self.kb.page(self._path)
        return page.headings if page and self._site == "site" else ()

    def _faqs(self) -> tuple[str, ...]:
        if self.page is not None:
            return tuple(self.page.faqs)
        page = self.kb.page(self._path)
        return tuple(f.q for f in page.faqs) if page and self._site == "site" else ()

    def _faq_answer(self, question: str) -> str | None:
        page = self.kb.page(self._path) if self._site == "site" else None
        answer = next((f.a for f in page.faqs if f.q == question), "") if page else ""
        first = answer.strip().split(". ")[0].rstrip(".")
        return f"{first}." if 0 < len(first) <= 200 else None

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        """Read and search SendPotion's knowledge and blog, move the visitor's
        tabs, book the demo, open the sign-up."""
        return [
            self.read_topic,
            self.search_site,
            self.find_blog_posts,
            self.navigate,
            self.show_section,
            self.open_faq,
            self.recommend_posts,
            self.open_post,
            self.book_demo,
            self.open_signup,
            self.switch_tab,
        ]

    @needs_result_now
    async def read_topic(self, request: TopicRequest) -> str:
        """Read one of SendPotion's knowledge topics before answering from it."""
        topic = self.kb.topics.get(request.topic)
        if topic is None:
            return f"No topic '{request.topic}' is written yet: use search_site."
        return topic.text

    @needs_result_now
    async def search_site(self, request: SearchRequest) -> str:
        """Search sendpotion.com's pages, sections and FAQs. Each result names the
        page path and the section heading to take them to."""
        hits = self.kb.search(request.query, _SEARCH_HITS)
        if not hits:
            return f"Nothing on sendpotion.com matches '{request.query}'. Try find_blog_posts."
        out: list[str] = []
        for h in hits:
            if h.kind == "faq":
                out.append(f"[FAQ on {h.path}] {h.title}\n  {h.snippet}")
            else:
                where = f", heading: {h.section}" if h.section else ""
                out.append(f"[page] {h.title} — path: {h.path}{where}\n  {h.snippet}")
        return "\n".join(out)

    @needs_result_now
    async def find_blog_posts(self, request: PostSearchRequest) -> str:
        """Find SendPotion blog posts for the visitor's use case. Then
        recommend_posts with the ones that fit."""
        hits = self.kb.find_posts(request.use_case, _POST_HITS)
        if not hits:
            return f"No blog post matches '{request.use_case}'. Say so, and offer site pages."
        out: list[str] = []
        for h in hits:
            post = self.kb.post(h.url or "")
            if post is None:
                continue
            if post.url not in self._found_posts:
                self._found_posts.append(post.url)
            about = post.summary or post.subtitle or h.snippet
            heads = f"\n  headings: {_clip(post.headings, 8)}" if post.headings else ""
            out.append(f"- {post.title} — url: {post.url}\n  {about}{heads}")
        return "\n".join(out)

    async def navigate(self, request: NavigateRequest) -> str:
        """Open one of sendpotion.com's pages on the visitor's screen, scrolled to
        the section that answers them. In the same response, before the call,
        tell them what that section shows and why it matters for them."""
        page = self.kb.page(request.path)
        if page is None:
            near = ", ".join(self.kb.near_paths(request.path)) or "none"
            return (
                f"Not opened: {request.path} is not a page on sendpotion.com. Closest: {near}. "
                "Tell the visitor if you said it was open."
            )
        heading = _match(request.heading, page.headings) if request.heading else None
        text = request.text.strip()[:120] if request.text else None
        if request.heading and heading is None and not text:
            # A heading the page does not have: go anyway, and ring the words.
            text = request.heading.strip()[:120]
        self._move(Navigate(path=_site_path(page.path), heading=heading, text=text))
        to = f", at '{heading or text}'" if heading or text else ""
        return f"Opened {_short_title(page.title)} ({page.path}){to}."

    async def show_section(self, request: SectionRequest) -> str:
        """Scroll the tab in front to a heading and ring its section — or, with
        text, ring those words (a plan, a feature, a line of a post). In the same
        response, say what it tells them and why it matters."""
        headings = self._headings()
        heading = _match(request.heading, headings) if request.heading else None
        text = request.text.strip()[:120] if request.text else None
        if request.heading and heading is None:
            if headings and not text:
                return (
                    f"Not shown: this page has no heading '{request.heading}'. "
                    f"Its headings: {_clip(headings, _HEADINGS_IN_NOTE)}."
                )
            text = text or request.heading.strip()[:120]
        if heading is None and text is None:
            return "Not shown: say which heading or words to show."
        self._move(ShowSection(heading=heading, text=text))
        return f"Showing '{heading or text}'."

    async def open_faq(self, request: FaqRequest) -> str:
        """Open one of the FAQs on the page in front and ring it. In the same
        response, give the answer in your own words."""
        faqs = self._faqs()
        question = _match(request.question, faqs)
        if question is None:
            hits = [h for h in self.kb.search(request.question, 4) if h.kind == "faq"]
            elsewhere = f" The FAQ is on {hits[0].path}: navigate there first." if hits else ""
            return (
                f"Not opened: this page has no FAQ '{request.question}'. "
                f"Its FAQs: {_clip(faqs, _FAQS_IN_NOTE) or 'none'}.{elsewhere}"
            )
        self._move(OpenFaq(question=question), self._faq_answer(question))
        return f"Opened the FAQ '{question}'."

    async def recommend_posts(self, request: RecommendRequest) -> str:
        """Put blog posts that fit the visitor in the reading list beside you, on
        every tab, and open the first in a new tab. Only posts find_blog_posts
        returned. In the same response, say what the opened post covers."""
        items: list[ReadingItem] = []
        unknown: list[str] = []
        for picked in request.posts[:4]:
            post = self.kb.post(picked.url)
            if post is None:
                unknown.append(picked.url)
                continue
            if all(i.url != post.url for i in items):
                items.append(ReadingItem(url=post.url, title=post.title, why=picked.why or None))
        if not items:
            return "Not shown: none of those is a SendPotion blog post. Use find_blog_posts first."
        first = items[0].url if request.open_first else None
        self._move(OpenPosts(heading=request.heading, posts=items, open=first), _LANDED["posts"][0])
        result = f"Listed {len(items)} posts beside you" + (
            f"; opened '{items[0].title}' in a new tab." if first else "."
        )
        if unknown:
            result += f" Not posts, so left out: {', '.join(unknown)}."
        return result

    async def open_post(self, request: OpenPostRequest) -> str:
        """Open one blog post for the visitor, in its own tab, scrolled to a
        heading when given. In the same response, say what that part covers."""
        post = self.kb.post(request.url)
        if post is None:
            return "Not opened: that is not a SendPotion blog post. Use find_blog_posts first."
        heading = _match(request.heading, post.headings) if request.heading else None
        self._move(OpenPost(url=post.url, heading=heading or request.heading))
        return f"Opened '{post.title}'" + (f" at '{heading}'." if heading else ".")

    async def book_demo(self, request: DemoRequest) -> str:
        """Open SendPotion's demo booking on /demo/, or add to it: the day and
        time they chose, and any name, email or notes they gave. What is filled
        stays. It never presses Schedule Event. The calendar's open days and its
        details step come back to you from the page."""
        for key in ("name", "email", "notes"):
            if value := getattr(request, key):
                self._demo_fields[key] = value
        day, when = request.day, request.time
        if day and self.demo is not None and self.demo.days:
            day = _match(day, self.demo.days) or day
        fields = self._demo_fields
        self._move(
            BookDemo(
                day=day,
                time=when,
                name=fields.get("name"),
                email=fields.get("email"),
                notes=fields.get("notes"),
            ),
            _LANDED["demo_filled" if day or when or self._demo_fields else "demo"][0],
        )
        parts = [x for x in (day, when) if x]
        filled = ", ".join(self._demo_fields) or "nothing"
        return (
            f"The demo calendar is open{(' at ' + ' '.join(parts)) if parts else ''}; "
            f"details given: {filled}. The visitor presses Schedule Event themselves."
        )

    async def open_signup(self) -> str:
        """Open Potion's sign-up and log-in (app.sendpotion.com) in a new tab.
        Only when they ask to sign up, try it free or log in."""
        self._move(OpenSignup(), _LANDED["signup"][0])
        return "Opened app.sendpotion.com in a new tab."

    async def switch_tab(self, request: TabRequest) -> str:
        """Bring another of the visitor's SendPotion tabs to the front."""
        tab = next((t for t in self.tabs if t.tab_id == request.tab_id), None)
        if tab is None:
            listed = ", ".join(f"{t.tab_id} ({t.title})" for t in self.tabs) or "none"
            return f"Not switched: no tab '{request.tab_id}'. Open tabs: {listed}."
        self._move(FocusTab(tab_id=tab.tab_id), _LANDED["tab"][0])
        return f"Brought '{tab.title or tab.url}' to the front."


__all__ = [
    "BookDemo",
    "FocusTab",
    "Navigate",
    "OpenFaq",
    "OpenPost",
    "OpenPosts",
    "OpenSignup",
    "ReadingItem",
    "SendPotionBrain",
    "ShowSection",
]
