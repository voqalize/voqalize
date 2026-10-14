"""SaatvikBrain — Tushar, a solar advisor on www.saatvikgroup.com.

The site is Saatvik Green Energy's, not ours. A browser extension injects the
widget and a small adapter into it; the adapter turns each
:class:`~voqalize.sdk.Action` below into a move on Saatvik's own page — a route,
a section scrolled to and ringed, an FAQ opened, a datasheet open at the page
that answers the question, the savings calculator run, the dealer locator
filtered, the enquiry form filled in — and reports every page, result and form
back as a typed event (:mod:`.app_events`).

Four things shape every decision here.

**A product expert first, a lead-capturer second.** Every turn answers what was
asked, in a sentence or two, and makes a move on the page. What he learns on
the way is recorded quietly with ``update_lead`` and becomes the brief Saatvik's
sales team receives (:mod:`.lead`) — shown to the visitor as it fills, so
nothing is collected behind their back.

**Every figure has a source.** A wattage, efficiency, warranty or subsidy amount
is spoken from L1 (in this prompt), an L2 topic he read, a search of the site,
or what the page itself reported. A datasheet figure is shown, not just said:
the PDF opens at its page with the figure highlighted, and the brain checks the
quote is on that page before it is sent (:meth:`.knowledge.Knowledge.find_quote`).

**Nothing on the page is invented.** A path he navigates to, a heading he
scrolls to and an FAQ he opens are checked against the crawl and against what
the page last reported; anything else is refused before it reaches the page.

**The form is the visitor's.** He fills in what they told him and rings what is
left. He never ticks consent and never submits; the visitor types their own
phone number and email, and presses Submit themselves.

How a result that arrives after his turn gets spoken — the calculator's
estimate, the dealers, a submitted form — is in :meth:`SaatvikBrain.on_user_idle`.
"""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

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
    configure_soon,
    landed,
    needs_result_now,
    phrase,
    say_line,
)

from voqalize.sdk import (
    Action,
    RequestRejected,
    RTVIMessage,
    Session,
    Speech,
    SpeechChunk,
    SpeechStart,
    UserIdle,
    UserMessage,
)
from voqalize.sdk.wire import Config, IdleConfig, Language, SttConfig, TtsConfig, Voice

from . import knowledge as kb
from .app_events import (
    SAATVIK_EVENTS,
    CalculatorInputs,
    CalculatorResult,
    CommandFailed,
    Dealer,
    DealersShown,
    DocumentClosed,
    DocumentOpened,
    EnquiryFields,
    EnquiryOpened,
    EnquirySubmitted,
    LanguageRequested,
    PageChanged,
    SaatvikEvent,
)
from .knowledge import TOPIC_IDS, Knowledge, canonical_path, norm
from .lead import (
    Estimate,
    Lead,
    LeadBrief,
    LeadFields,
    Observed,
    Ownership,
    Score,
    Segment,
    Timeline,
    post_brief,
)

AGENT_NAME = "Tushar"

# ─── Timing ────────────────────────────────────────────────────────────────────

#: A quiet visitor is someone reading a page, and an advisor beside them says
#: something after a while: the same window Qween asked for, long enough that a
#: visitor reading a datasheet is not interrupted mid-thought.
_IDLE_MS = 20_000
#: The quiet spells he speaks into before leaving them to browse. Every later
#: one is silence: a third nudge is nagging.
_IDLE_NUDGES = 2
#: The idle window while a result the page just produced is waiting to be talked
#: through. A brain has no floor outside a turn, so the calculator's estimate,
#: the dealer list and a submitted form reach Tushar as a quiet spell, not as a
#: turn. Two seconds: a visitor who reacts to the result has started speaking by
#: then (and their words win, with the result already in context), while a
#: visitor who is reading is not left with a silent screen for long.
_TALK_THROUGH_MS = 2_000

# ─── Language ──────────────────────────────────────────────────────────────────

LanguageName = Literal["english", "hindi"]


@dataclass(frozen=True)
class Speaking:
    heard: Language
    spoken: Language
    voice: Voice


SPEECH: dict[LanguageName, Speaking] = {
    "english": Speaking(Language.EN, Language.EN, Voice.OMNIVOICE_GAURAV),
    "hindi": Speaking(Language.HI, Language.HI, Voice.OMNIVOICE_GAURAV),
}
BY_TAG: dict[str, LanguageName] = {"en": "english", "hi": "hindi"}
_TAG: dict[LanguageName, Literal["en", "hi"]] = {"english": "en", "hindi": "hi"}
OPENING: LanguageName = "english"

# Tushar's own line for a silent turn is said in the language his voice speaks.
assert {s.spoken for s in SPEECH.values()} <= set(PHRASES), "a spoken language has no PHRASES row"

#: What Tushar says at the start of his next turn after the visitor switched the
#: language on the toggle: written, in the new language, read by the new voice.
TOGGLE_CONFIRM: dict[LanguageName, str] = {
    "english": "Sure, let's continue in English.",
    "hindi": "ज़रूर, अब हिंदी में बात करते हैं।",
}

# The small grammar words of Hindi, as the English recognizer spells them and as
# the Hindi one writes them. A visitor who uses them is speaking Hindi or
# Hinglish, whatever the nouns are. Qween's list, which calls proved out.
_HINDI_GRAMMAR = (
    "hai hain hoon hun kya kyaa mein mujhe muje muja mujhko chahiye chahie chahi "
    "karo kariye karna dikhao dikhaiye dikha dikhana aap baat nahi nahin sakti sakte sakta "
    "sabse bolti bolo batao bataiye theek thik hazar hazaar "
    "wala wali kitna kitne kitni liye bhi aur yeh woh accha acha haan ka ki ke ko se ek "
    "है हैं हूँ हूं क्या में मुझे चाहिए करो करिए करना दिखाओ दिखाइए दिखा आप बात नहीं "
    "सकती सकते सकता वाला वाली कितना कितने कितनी लिए भी और यह ये वह वो अच्छा हाँ हां "
    "का की के को से एक"
)
_HINDI_WORDS = frozenset(_HINDI_GRAMMAR.split())
#: Hindi's script: a reply written in it is a reply in Hindi.
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def _sounds_hindi(text: str) -> bool:
    """Two different Hindi grammar words: one is a coincidence ("se", "ki"),
    two is a sentence."""
    words = set(re.findall(r"[\wऀ-ॿ]+", text.lower()))
    return len(words & _HINDI_WORDS) >= 2


# ─── What the site's own forms take ────────────────────────────────────────────

#: The savings calculator's state options, by their labels.
CalculatorState = Literal[
    "Andaman & Nicobar", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar",
    "Chandigarh", "Chhattisgarh", "Dadra & Nagar Haveli and Daman & Diu", "Delhi (NCT)",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jammu & Kashmir", "Jharkhand",
    "Karnataka", "Kerala", "Ladakh", "Lakshadweep", "Madhya Pradesh", "Maharashtra",
    "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Puducherry", "Punjab",
    "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh",
    "Uttarakhand", "West Bengal",
]  # fmt: skip

#: The dealer locator's state options. A state not here has no listed dealer.
DEALER_STATES: tuple[str, ...] = (
    "Assam", "Chhattisgarh", "Delhi & NCR", "Gujarat", "Haryana", "Karnataka", "Kerala",
    "Madhya Pradesh", "Maharashtra", "Odisha", "Punjab", "Rajasthan", "Tamil Nadu",
    "Telangana", "Uttar Pradesh", "Uttarakhand", "West Bengal",
)  # fmt: skip
_DELHI = ("delhi", "new delhi", "ncr", "delhi ncr", "delhi (nct)", "gurgaon", "gurugram", "noida")

#: The enquiry form's categories, by their labels.
Category = Literal[
    "Module - requirement above 200 KW",
    "Module - requirement below 199 KW",
    "Solar EPC - Rooftop",
    "Solar EPC - Utility Ground Mount",
    "Solar Inverter",
    "Transformer",
    "Solar Kit",
    "Service Support",
    "Others",
]
EnquiryKind = Literal["domestic", "dealer", "export"]

if TYPE_CHECKING:
    TopicId = str
else:
    # The L2 files present at import, as the tool's enum; see knowledge.TOPIC_IDS.
    TopicId = Literal[TOPIC_IDS]


def _dealer_state(state: str | None) -> str | None:
    """The locator's own label for ``state``, or ``None`` when it lists no dealer there."""
    if not state:
        return None
    want = norm(state)
    if want in _DELHI:
        return "Delhi & NCR"
    return next((s for s in DEALER_STATES if norm(s) == want), None)


# ─── Actions (brain → page) ────────────────────────────────────────────────────


class Navigate(Action):
    """Go to one of the site's pages; the page reports ``page_changed``."""

    path: str


class ShowSection(Action):
    """Scroll to the ``h1`` to ``h3`` named ``heading`` and ring its section; with
    ``text``, ring the smallest element in it that contains that text."""

    heading: str
    text: str | None = None


class OpenFaq(Action):
    """Open the accordion question that starts with ``question`` and ring it."""

    question: str


class QuoteBox(BaseModel):
    """A rectangle to mark on a PDF page, in fractions of the page from its top
    left corner."""

    x: float
    y: float
    w: float
    h: float


class OpenDocument(Action):
    """Open the in-page PDF viewer at ``page``, highlighting ``quote`` when given.

    ``boxes`` is set on a page whose text is drawn as outlines (Saatvik's module
    datasheets), where the viewer's text layer has nothing to find: the quote's
    words were read off the page image at build time, and the page marks these
    rectangles instead."""

    url: str
    title: str
    page: int
    quote: str | None = None
    boxes: list[QuoteBox] | None = None


class CloseDocument(Action):
    """Close the PDF viewer."""


class LanguageChanged(Action):
    """The call's language moved, by the toggle, by voice or by ``set_language``:
    the widget's toggle follows at once."""

    language: Literal["en", "hi"]


class EnquiryPrefill(BaseModel):
    name: str | None = None
    company: str | None = None
    email: str | None = None
    mobile: str | None = None
    category: str | None = None
    state: str | None = None
    message: str | None = None


class OpenEnquiry(Action):
    """Open the enquiry form's ``kind`` tab and fill in ``prefill``. The page
    rings the required fields still empty and the SUBMIT button; it never ticks
    consent and never submits."""

    kind: EnquiryKind
    prefill: EnquiryPrefill


class RunCalculator(Action):
    """Fill in and run the savings calculator; the page reports ``calculator_result``."""

    units: float
    state: str
    rate: float


class FindDealer(Action):
    """Filter the dealer locator; the page reports ``dealers_shown``."""

    state: str | None = None
    query: str | None = None


# ─── Tool requests ─────────────────────────────────────────────────────────────


class TopicRequest(BaseModel):
    topic: TopicId = Field(description="The topic to read, by its name.")


class SearchRequest(BaseModel):
    query: str = Field(
        description="A few words to look for on the site and in its datasheets and "
        "manuals, e.g. 'temperature coefficient', 'bifacial 580 W', 'warranty'."
    )


class NavigateRequest(BaseModel):
    path: str = Field(
        description="A page path from the site pages list or a search result, e.g. "
        "'/solar-calculator'. Never a path you made up."
    )


class SectionRequest(BaseModel):
    heading: str = Field(description="A section heading on the page the visitor has open.")
    text: str | None = Field(
        default=None,
        description="Optional: a few words inside that section to ring, e.g. one spec row.",
    )


class FaqRequest(BaseModel):
    question: str = Field(description="An FAQ question on the page the visitor has open.")


class DocumentRequest(BaseModel):
    document_id: str = Field(description="The document_id from a search result.")
    page: int = Field(default=1, description="The page of the PDF to open at.")
    quote: str | None = Field(
        default=None,
        description="Optional: a few words copied exactly from that page of the search "
        "result to highlight — the figure you are about to say.",
    )


class CalculatorRequest(BaseModel):
    state: CalculatorState = Field(description="The visitor's state.")
    monthly_units: float | None = Field(
        default=None, description="Units (kWh) the visitor uses a month, if they said."
    )
    monthly_bill_inr: float | None = Field(
        default=None, description="The visitor's monthly electricity bill in rupees, if they said."
    )
    rate_per_unit: float | None = Field(default=None, description="Rupees per unit, if they said.")


class DealerRequest(BaseModel):
    state: str | None = Field(default=None, description="The visitor's state, if known.")
    city: str | None = Field(default=None, description="The visitor's city or district, if known.")


class EnquiryRequest(BaseModel):
    kind: EnquiryKind = Field(
        description="domestic: a buyer in India; dealer: wants to become a dealer or "
        "distributor; export: a buyer outside India."
    )
    category: Category | None = Field(default=None, description="What the enquiry is about.")
    state: str | None = Field(default=None, description="The visitor's state, if known.")
    message: str | None = Field(
        default=None,
        description="One or two sentences for the sales team: what they need, in "
        "their terms. Leave empty to have it written from what you recorded.",
    )
    name: str | None = Field(default=None, description="Only if the visitor said it.")
    company: str | None = Field(default=None, description="Only if the visitor said it.")
    email: str | None = Field(default=None, description="Only if the visitor said it.")
    mobile: str | None = Field(default=None, description="Only if the visitor said it.")


class LeadUpdate(BaseModel):
    """What the visitor just told you about their need. Set only what they said."""

    segment: Segment | None = Field(default=None, description="Who they are.")
    need: str | None = Field(default=None, description="What they want, in a few words.")
    system_size_kw: float | None = None
    monthly_units: float | None = None
    monthly_bill_inr: float | None = None
    state: str | None = None
    city: str | None = Field(default=None, description="City or district.")
    roof_type: str | None = Field(default=None, description="e.g. RCC flat, tin sheet, tiled.")
    roof_area: str | None = Field(default=None, description="As they said it, e.g. '800 sq ft'.")
    ownership: Ownership | None = Field(default=None, description="Of the roof or site.")
    timeline: Timeline | None = None
    budget: str | None = None
    financing_interest: bool | None = None
    subsidy_interest: bool | None = None
    products_interested: list[str] | None = None
    decision_maker: bool | None = Field(default=None, description="Do they decide the purchase?")
    callback_requested: bool | None = None
    preferred_time: str | None = Field(default=None, description="Best time to call them.")
    objections: list[str] | None = Field(default=None, description="Doubts they raised.")
    name: str | None = Field(default=None, description="Only if they said it.")
    company: str | None = Field(default=None, description="Only if they said it.")


class LanguageRequest(BaseModel):
    language: LanguageName


# ─── The prompt ────────────────────────────────────────────────────────────────

#: The site map in the prompt: top-level and second-level pages, as many as fit
#: here. Deeper pages are reached through search.
_SITE_MAP_CHARS = 5000
_SITE_MAP_DEPTH = 2
#: The site's own suffix on every page title: the same words on every line.
_TITLE_SUFFIX = " — Saatvik Green Energy"


def _site_map(k: Knowledge) -> str:
    lines: list[str] = []
    size = 0
    for p in sorted(k.pages.values(), key=lambda p: (p.path.count("/"), p.path)):
        if p.path.count("/") > _SITE_MAP_DEPTH:
            continue
        line = f"- {p.path} — {p.title.removesuffix(_TITLE_SUFFIX)}"
        size += len(line) + 1
        if size > _SITE_MAP_CHARS:
            break
        lines.append(line)
    return "\n".join(lines) or "(The site map is not loaded: find pages with search_site.)"


def _topics(k: Knowledge) -> str:
    return "\n".join(f"- {t.id}: {t.title}" for t in k.topics.values()) or "(none loaded)"


def _prompt(k: Knowledge) -> str:
    return f"""You are {AGENT_NAME}, the solar advisor on Saatvik Green Energy's website, www.saatvikgroup.com. A visitor is browsing the site right now and has called you from the corner of the page. You can see and move their screen: you open Saatvik's pages, scroll to sections, open FAQs, open datasheets at the right page with the figure highlighted, run the savings calculator, find dealers and fill in the enquiry form with them. You are warm, expert and brief — the advisor who knows the panels inside out and makes going solar feel simple.

# How you speak
- One or two short sentences, then a move on the page. The page carries the detail; you say what matters.
- Spoken words only: no lists, no markdown, no symbols. Say numbers the way a person would ("five hundred and eighty watts", "about seventy-eight thousand rupees").
- Speak the move and the answer in the same response as the tool call: once the turn ends you cannot speak until the visitor does.
- English by default. A visitor who speaks Hindi or Hinglish is answered in Hindi, written in Devanagari; you are a man, so use masculine forms of yourself ("मैं दिखाता हूँ", "मैं ढूँढ रहा हूँ"). Product names, model numbers and units stay as Saatvik writes them.
- Lines in square brackets come from the page, not the visitor: what they opened, what a form or the calculator shows. Never read them out; use them.

# What you know
- Every figure — a wattage, efficiency, warranty, price, subsidy amount, timeline — comes from the knowledge below, a topic you read, a search result, or what the page reported. Never from memory. If you cannot find it, say so plainly and offer to note it for Saatvik's sales team.
- Read a topic with read_topic before answering anything it covers beyond what is below. Topics:
{_topics(k)}
- For a specific figure, model or document, search_site. When the answer is on a datasheet or manual page, open it with open_document at that page and highlight the figure with a quote copied from the search result.
- Subsidies and policy: give the national scheme as Saatvik's pages describe it. State top-ups, DISCOM rules and net metering vary by state and change often: say so, offer to note their question for the sales team, or point them to the official national portal. Never promise an amount for their state.
- Investors, the company, news and careers are answered from the topics (company, investors, newsroom). Never steer an investor or a job seeker to the sales enquiry form; open the right page for them instead.

# Moving the page
- navigate only to a path from the site pages list below or from a search result. show_section and open_faq take a heading or question on the page the visitor has open.
- To size a system or show savings, run_calculator: you need their state and either their monthly units or their monthly bill (and the rate if they know it). Ask for what is missing, one thing at a time. The estimate appears on the page and comes back to you: talk them through it from the page's figures.
- find_dealer for a dealer near them. The dealer list comes back to you from the page.

# The visitor's enquiry
- You are a product expert first. Learn about their need only as it helps you answer: their kind of building, state, bill, roof, timeline. Never interrogate; at most one question per turn.
- Every time they tell you something about their need, call update_lead with it, in the same response. It is silent bookkeeping: never mention it.
- When they want a quote, a call back or to talk to sales, open_enquiry with what they told you. Fill in name, company, email or mobile only if they said them; never ask them to read out a phone number or email for you to type. Then tell them which fields are left for them to fill in, that they tick the consent box and press Submit themselves. Never say it is submitted until the page tells you.
- A visitor who wants a person: give Saatvik's toll-free number or WhatsApp from the knowledge below if it is there, or open the enquiry form with a call back noted (update_lead callback_requested), and say a person will call.
- When the page tells you the form was submitted, thank them in one sentence, then ask the one sales question still unknown that matters most: timeline, whether they own the roof and what kind it is, who decides, financing, or the best time for the call. Record each answer with update_lead.

# Saatvik
{k.l1}

# Site pages
{_site_map(k)}
"""


# ─── Greeting ──────────────────────────────────────────────────────────────────

_GREETING = f"Hi, I'm {AGENT_NAME}, Saatvik's solar advisor. Ask me anything about going solar."
_GREETING_HI = "नमस्ते, मैं तुषार हूँ, सात्विक का सोलर सलाहकार। सोलर के बारे में कुछ भी पूछिए।"
_INTRO = f"Hi, I'm {AGENT_NAME}, Saatvik's solar advisor."
#: The opener's second sentence for the page the call starts on, by a word in
#: its path; the first match wins, and anything else gets the plain greeting.
_OPENERS: tuple[tuple[str, str], ...] = (
    ("calculator", "I can run this calculator with you, or answer anything about going solar."),
    ("dealer", "I can find a dealer near you, or answer anything about going solar."),
    ("contact", "Tell me what you need and I'll help you with this form."),
    ("investor", "Ask me anything about Saatvik, or about going solar."),
    ("product", "Ask me anything about these panels, or about going solar."),
    ("module", "Ask me anything about these panels, or about going solar."),
)


def greeting(path: str | None, spoken: Language) -> str:
    """The written opener, tailored to the page the call starts on."""
    if spoken == Language.HI:
        return _GREETING_HI
    here = canonical_path(path or "/")
    return next((f"{_INTRO} {line}" for word, line in _OPENERS if word in here), _GREETING)


# ─── Written lines for moves ───────────────────────────────────────────────────

#: His line for a silent turn whose move is not "here it is": the calculator and
#: the dealer list are still loading when the turn ends, and the form waits on them.
_LANDED_LINES: dict[str, dict[Language, tuple[str, ...]]] = {
    "calculator": {
        Language.EN: ("I'm running the estimate now.",),
        Language.HI: ("मैं अभी अनुमान निकाल रहा हूँ।",),
    },
    "dealers": {
        Language.EN: ("Let me find dealers near you.",),
        Language.HI: ("मैं आपके पास के डीलर ढूँढता हूँ।",),
    },
    "enquiry": {
        Language.EN: ("Here's the form, with what you told me filled in.",),
        Language.HI: ("यह रहा फ़ॉर्म, आपकी बताई बातें भरी हुई हैं।",),
    },
}
assert all({s.spoken for s in SPEECH.values()} <= set(v) for v in _LANDED_LINES.values()), (
    "a spoken language has no written line for a move"
)

#: How much of a page's own text reaches the model in a note.
_CALC_CHARS = 1200
_HEADINGS_IN_NOTE = 20
_FAQS_IN_NOTE = 12
_DEALERS_IN_NOTE = 8
_SEARCH_HITS = 6


async def _silence() -> AsyncGenerator[Any, None]:
    """Yields nothing: a quiet spell he lets ride."""
    for _ in ():
        yield


def _clip(items: list[str], most: int) -> str:
    more = f"; and {len(items) - most} more" if len(items) > most else ""
    return "; ".join(items[:most]) + more


def _match(want: str, options: list[str]) -> str | None:
    """The option ``want`` names: the same words, else the one it begins, else
    the one it is inside — how the page itself matches."""
    w = norm(want)
    if not w:
        return None
    folded = [(norm(o), o) for o in options]
    for test in (
        lambda o: o == w,
        lambda o: o.startswith(w),
        lambda o: w.startswith(o) and len(o) > len(w) // 2,
        lambda o: w in o,
    ):
        if (hit := next((o for f, o in folded if test(f)), None)) is not None:
            return hit
    return None


# ─── The brain ─────────────────────────────────────────────────────────────────


class SaatvikBrain(GeminiBrain):
    """One per session. Tushar: Saatvik's knowledge, Saatvik's pages, and a mirror
    of what this visitor's screen shows."""

    def __init__(
        self,
        *,
        client: genai.Client,
        model: str = DEFAULT_MODEL,
        knowledge: Knowledge | None = None,
        share_brief: bool = True,
    ) -> None:
        self.kb = knowledge if knowledge is not None else kb.KNOWLEDGE
        super().__init__(client=client, system_instruction=_prompt(self.kb), model=model)
        #: Send the brief to the widget as it fills, not only once submitted.
        self._share_brief = share_brief
        self.spoken: Language = SPEECH[OPENING].spoken
        self._fallback = FallbackLine()
        self.lead = Lead()
        #: The page as the adapter last reported it, and whether the model has
        #: seen it since it changed.
        self.page: PageChanged | None = None
        self._path = "/"
        self._page_unseen = False
        self.document: DocumentOpened | None = None
        #: The document ids search has shown the model this call.
        self._found_docs: list[str] = []
        #: A result the page produced, waiting for the quiet spell that lets him
        #: talk it through; and the toggle's written confirmation.
        self._talk: str | None = None
        self._confirm: str | None = None
        self._idle_short = False
        self._nudges = 0

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        init = session.init or {}
        self._path = canonical_path(str(init.get("page") or "/"))
        lang = BY_TAG.get(str(init.get("lang") or ""), OPENING)
        # His own voice, settled here and not by the page. Both language legs
        # move together; the toggle and `set_language` move them again.
        await session.configure(
            Config(
                stt=SttConfig(language=SPEECH[lang].heard, patience=PATIENCE),
                tts=TtsConfig(voice=SPEECH[lang].voice, language=SPEECH[lang].spoken),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
            )
        )
        self.spoken = SPEECH[lang].spoken
        self.lead.update(language=lang)
        self.lead.saw_page(self._path)
        logger.info("saatvik: session start on {} in {}", self._path, lang)

    async def greet(self, session: Session) -> str:
        """The opener, written not generated."""
        return greeting(self._path, self.spoken)

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[Speech, None]:
        """A visitor who speaks Hindi is answered in Hindi from the first word;
        the page they moved to is read in with what they said."""
        if self.spoken != SPEECH["hindi"].spoken and _sounds_hindi(msg.text):
            await session.configure(self._speaking("hindi"))
            logger.info("saatvik: language -> hindi (heard)")
        # They spoke first: a result waiting to be talked through is already in
        # the context, and their words are what to answer.
        self._talk = None
        self._nudges = 0
        self._restore_idle()
        self.lead.asked(msg.text)
        self._read_in_page()
        async for event in super().on_user_message(session, msg):
            yield event

    def on_user_idle(self, session: Session, idle: UserIdle) -> AsyncGenerator[Speech, None]:
        """A quiet spell — and the only floor he gets without the visitor speaking.

        Events never speak: ``on_rtvi`` has no floor. So a result the page
        produced after his turn (the estimate, the dealers, a submitted form)
        is put in the context at once, and the idle window is shortened to
        :data:`_TALK_THROUGH_MS`. A visitor who reacts speaks first and is
        answered with the result in hand; one who is reading gets the quiet
        spell, and he talks the result through in it. The window goes back to
        :data:`_IDLE_MS` as soon as he has, or as soon as they speak.

        Otherwise it is an ordinary quiet spell: a nudge as qween's consultant
        gives one, twice, then silence."""
        self._restore_idle()
        if self._talk is not None:
            ask, self._talk = self._talk, None
            logger.info("saatvik: talking a result through")
            self._note(ask)
            return self.respond(session)
        if self._confirm is not None:
            line, self._confirm = self._confirm, None
            return say_line(self, line)
        if self._nudges >= _IDLE_NUDGES:
            return _silence()
        self._nudges += 1
        self._read_in_page()
        quiet = f"The visitor has said nothing for about {round(idle.idle_ms / 1000)} seconds."
        if self._nudges == 1:
            ask = (
                "Speak into the quiet, briefly, as the advisor beside them would: one useful "
                "thing about what is on their screen, or one question that helps you help "
                "them. Never ask whether they are still there, and never repeat your last line."
            )
        else:
            ask = (
                "Still quiet. One last, light offer, different from your last: something you "
                "could show them, the savings estimate, or a person at Saatvik. Then let them "
                "browse."
            )
        self._note(f"{quiet} {ask}")
        return self.respond(session)

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The model's turn, and a line of Tushar's own if it acted and said
        nothing (:mod:`voqalize_demos.silent_turn`).

        A language switched on the toggle is confirmed first, in the new
        language, with its written line. A unit is opened only once its first
        words are known, so the voice follows the model's own choice of
        language: Hindi heard through the English recognizer is noise no word
        list catches, but the model understands it and writes Devanagari."""
        if (line := self._confirm) is not None:
            self._confirm = None
            async for event in say_line(self, line):
                yield event
        opening: SpeechStart | None = None
        async for event in self._fallback.speak_if_silent(self, super().respond(session)):
            if isinstance(event, SpeechStart):
                opening = event
                continue
            if opening is not None:
                if isinstance(event, SpeechChunk):
                    await self._follow_script(session, event.text)
                yield opening
                opening = None
            yield event
        if opening is not None:
            yield opening

    async def _follow_script(self, session: Session, text: str) -> None:
        """Move both legs to Hindi when the model writes it and the call is not."""
        if self.spoken != SPEECH["hindi"].spoken and _DEVANAGARI.search(text):
            await session.configure(self._speaking("hindi"))
            logger.info("saatvik: language -> hindi (written)")

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Page→brain events, folded in silently: no floor taken, no turn."""
        event = SAATVIK_EVENTS.parse(msg)
        if event is None:
            return
        logger.info("saatvik: {} — {}", type(event).__voqal_event__, event)
        if isinstance(event, LanguageRequested):
            await self._requested(session, event)
            return
        if (note := self.apply_event(event)) is not None:
            self._note(note)

    # ─── Page → brain ───────────────────────────────────────────────────

    def apply_event(self, event: SaatvikEvent) -> str | None:
        """Patch the mirror and the lead; return the line the model should see."""
        match event:
            case PageChanged():
                self.page = event
                self._path = canonical_path(event.path)
                self._page_unseen = True
                self.lead.saw_page(self._path)
                # Read in with their next message or quiet spell, not now: they
                # may click on before they speak, and only the last page matters.
                return None
            case DocumentOpened():
                self.document = event
                doc = self._document_by_url(event.url)
                title = doc.title if doc else event.url
                self.lead.saw_document(title)
                return f"[The document viewer shows {title}, page {event.page}.]"
            case DocumentClosed():
                self.document = None
                return "[The document viewer is closed.]"
            case CalculatorResult():
                return self._estimated(event.inputs, event.text)
            case DealersShown():
                return self._dealers(event)
            case EnquiryOpened():
                missing = ", ".join(event.missing) or "none"
                return (
                    f"[The {event.kind} enquiry form is open. Required fields still empty: "
                    f"{missing}. The visitor fills these in, ticks consent and presses Submit "
                    "themselves.]"
                )
            case EnquirySubmitted():
                return self._submitted(event.kind, event.fields)
            case CommandFailed():
                if event.command in ("run_calculator", "find_dealer"):
                    self._talk = None
                    self._restore_idle()
                return (
                    f"[That did not happen on the page ({event.command}: {event.reason}). "
                    "Tell the visitor plainly and offer what you can do instead; never say it "
                    "worked.]"
                )
            case LanguageRequested():
                return None

    def _estimated(self, inputs: CalculatorInputs, text: str) -> str:
        result = " ".join(text.split())[:_CALC_CHARS]
        if inputs.units is not None and inputs.state and inputs.rate is not None:
            self.lead.observed.estimate = Estimate(
                units=inputs.units, state=inputs.state, rate=inputs.rate, result=result
            )
            self.lead.update(monthly_units=inputs.units, state=inputs.state)
        self._brief_changed()
        self._talk_through(
            "The estimate is on their screen and they have not spoken. Talk them through "
            "it now, in one or two sentences, from the page's figures only, then ask one "
            "question that moves them on, such as their roof or when they want it."
        )
        return (
            f"[The solar calculator shows, for {inputs.units} units a month in {inputs.state} "
            f"at ₹{inputs.rate} a unit: {result}]"
        )

    def _dealers(self, event: DealersShown) -> str:
        names = [d.name for d in event.dealers]
        self.lead.observed.dealers_shown = names
        self._brief_changed()
        if not event.dealers:
            self._talk_through(
                "The dealer locator found nobody for that search and they have not spoken. "
                "Say so in one sentence and offer the enquiry form, so Saatvik can connect them."
            )
            return f"[The dealer locator shows no dealers for '{event.state} {event.query}'.]"
        self._talk_through(
            "The dealers are on their screen and they have not spoken. Name the nearest one "
            "or two in a sentence, and offer to open the enquiry form for a call back."
        )
        listed = _clip([_dealer_line(d) for d in event.dealers], _DEALERS_IN_NOTE)
        return f"[The dealer locator shows, for '{event.state} {event.query}': {listed}]"

    def _submitted(self, kind: str, fields: EnquiryFields) -> str:
        self.lead.update(
            enquiry_kind=kind,
            **{k: v for k, v in fields.model_dump().items() if v},
        )
        self.lead.submitted = True
        brief = self.lead.brief()
        self.session.dispatch(brief)
        post_brief(brief)
        self._talk_through(
            "They have just submitted the enquiry. Thank them in one sentence and say "
            "Saatvik's team will call, then ask the one sales question still unknown that "
            "matters most: timeline, roof ownership and type, who decides, financing, or the "
            "best time for the call."
        )
        return f"[The visitor submitted the {kind} enquiry form. It reached Saatvik's sales team.]"

    async def _requested(self, session: Session, event: LanguageRequested) -> None:
        """The visitor pressed the other language on the toggle. Switched in
        code, not through the model: both legs move in one awaited request, and
        the written confirmation is said in his next turn — which, if they stay
        quiet, is the short quiet spell :meth:`on_user_idle` turns into it."""
        name = BY_TAG[event.language]
        if SPEECH[name].spoken == self.spoken:
            return
        was = self.spoken
        try:
            await session.configure(self._speaking(name))
        except RequestRejected as rejected:
            logger.warning("saatvik: switch to {} refused: {}", name, rejected)
            self.spoken = was
            self.session.dispatch(LanguageChanged(language="hi" if was == Language.HI else "en"))
            return
        logger.info("saatvik: language -> {} (toggle)", name)
        self.lead.update(language=name)
        self._confirm = TOGGLE_CONFIRM[name]
        self._shorten_idle()
        self._note(
            f"[The call is now in {name.capitalize()}, switched by the visitor on the toggle.]"
        )

    def _read_in_page(self) -> None:
        """The page they are on, once per change, ahead of what they say."""
        if not self._page_unseen or self.page is None:
            return
        self._page_unseen = False
        p = self.page
        note = f"[The visitor is on “{p.title or p.path}” ({self._path})."
        if p.headings:
            note += f" Its sections: {_clip(p.headings, _HEADINGS_IN_NOTE)}."
        if p.faqs:
            note += f" Its FAQs: {_clip(p.faqs, _FAQS_IN_NOTE)}."
        self._note(note + "]")

    def _note(self, text: str) -> None:
        self.append_to_context(types.Content(role="user", parts=[types.Part(text=text)]))

    def _talk_through(self, ask: str) -> None:
        self._talk = ask
        self._shorten_idle()

    def _shorten_idle(self) -> None:
        if not self._idle_short:
            self._idle_short = True
            configure_soon(self.session, Config(idle=IdleConfig(timeout_ms=_TALK_THROUGH_MS)))

    def _restore_idle(self) -> None:
        if self._idle_short:
            self._idle_short = False
            configure_soon(self.session, Config(idle=IdleConfig(timeout_ms=_IDLE_MS)))

    def _brief_changed(self) -> None:
        """Send the brief to the widget — as it fills when sharing is on, and
        always once submitted, when it also goes to the webhook."""
        if self.lead.submitted:
            brief = self.lead.brief()
            self.session.dispatch(brief)
            post_brief(brief)
        elif self._share_brief:
            self.session.dispatch(self.lead.brief())

    def _move(self, action: Action, lines: str | None = None) -> None:
        """Dispatch ``action``, with the written line for it should the turn say
        nothing: its own, under ``lines``, or the plain "shown"."""
        self.session.dispatch(action)
        own = _LANDED_LINES[lines][self.spoken] if lines is not None else None
        landed(*(own or phrase(self.spoken, "shown")))

    def _headings(self) -> list[str]:
        if self.page is not None:
            return self.page.headings
        page = self.kb.page(self._path)
        return list(page.headings) if page else []

    def _faqs(self) -> list[str]:
        if self.page is not None:
            return self.page.faqs
        page = self.kb.page(self._path)
        return [f.q for f in page.faqs] if page else []

    def _document_by_url(self, url: str) -> kb.Document | None:
        return next((d for d in self.kb.documents.values() if d.url == url), None)

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        """Read and search Saatvik's knowledge, move the visitor's page, run the
        calculator and the dealer locator, fill the enquiry, keep the lead,
        change language."""
        return [
            self.read_topic,
            self.search_site,
            self.navigate,
            self.show_section,
            self.open_faq,
            self.open_document,
            self.close_document,
            self.run_calculator,
            self.find_dealer,
            self.open_enquiry,
            self.update_lead,
            self.set_language,
        ]

    @needs_result_now
    async def read_topic(self, request: TopicRequest) -> str:
        """Read one of Saatvik's knowledge topics before answering from it. Its
        sources are listed at the top."""
        topic = self.kb.topics.get(request.topic)
        if topic is None:
            return f"No topic '{request.topic}' is written yet: use search_site."
        return topic.text

    @needs_result_now
    async def search_site(self, request: SearchRequest) -> str:
        """Search Saatvik's pages, FAQs, datasheets and manuals. Each result says
        how to show it: a page by its path, a PDF by its document_id and page."""
        hits = self.kb.search(request.query, _SEARCH_HITS)
        if not hits:
            return f"Nothing on the site matches '{request.query}'."
        out: list[str] = []
        for h in hits:
            if h.kind == "document" and h.document_id is not None:
                if h.document_id not in self._found_docs:
                    self._found_docs.append(h.document_id)
                out.append(
                    f"[document] {h.title} — document_id: {h.document_id}, page {h.page}\n"
                    f"  {h.snippet}"
                )
            elif h.kind == "faq":
                out.append(f"[FAQ on {h.path}] {h.title}\n  {h.snippet}")
            else:
                out.append(f"[page] {h.title} — path: {h.path}\n  {h.snippet}")
        return "\n".join(out)

    async def navigate(self, request: NavigateRequest) -> str:
        """Open one of Saatvik's pages on the visitor's screen. Say one short line
        with it, in the same response."""
        page = self.kb.page(request.path)
        if page is None:
            near = ", ".join(self.kb.near_paths(request.path)) or "none"
            return (
                f"Not opened: {request.path} is not a page on Saatvik's site. Closest: {near}. "
                "Tell the visitor if you said it was open."
            )
        self._move(Navigate(path=page.path))
        return f"Opened {page.title} ({page.path})."

    async def show_section(self, request: SectionRequest) -> str:
        """Scroll the visitor's page to a section and ring it — or, with text, one
        row or line inside it. Say one short line with it."""
        headings = self._headings()
        heading = _match(request.heading, headings)
        if heading is None:
            return (
                f"Not shown: this page has no section '{request.heading}'. "
                f"Its sections: {_clip(headings, _HEADINGS_IN_NOTE) or 'unknown'}."
            )
        text = request.text.strip()[:200] if request.text else None
        self._move(ShowSection(heading=heading, text=text or None))
        return f"Showing '{heading}'."

    async def open_faq(self, request: FaqRequest) -> str:
        """Open one of the FAQs on the visitor's page and ring it. Say one short
        line with it."""
        faqs = self._faqs()
        question = _match(request.question, faqs)
        if question is None:
            return (
                f"Not opened: this page has no FAQ '{request.question}'. "
                f"Its FAQs: {_clip(faqs, _FAQS_IN_NOTE) or 'none'}."
            )
        self._move(OpenFaq(question=question))
        return f"Opened the FAQ '{question}'."

    async def open_document(self, request: DocumentRequest) -> str:
        """Open a datasheet, manual or other Saatvik PDF on the visitor's screen at
        a page, highlighting a quote. Say the figure with it."""
        doc = self.kb.documents.get(request.document_id) or self._document_by_url(
            request.document_id
        )
        if doc is None:
            return f"Not opened: no document '{request.document_id}'. Search first."
        page = request.page if request.page in doc.pages or not doc.pages else min(doc.pages)
        quote: str | None = None
        boxes: list[QuoteBox] | None = None
        result = f"Opened {doc.title} at page {page}."
        if request.quote:
            found = self.kb.find_quote(doc.id, page, request.quote)
            if found is None:
                result += " The quote is not in this document, so nothing is highlighted."
            else:
                if found.page != page:
                    result = f"Opened {doc.title} at page {found.page}, where the quote is."
                page, quote = found.page, found.text
                boxes = [QuoteBox(x=b.x, y=b.y, w=b.w, h=b.h) for b in found.boxes] or None
        self._move(OpenDocument(url=doc.url, title=doc.title, page=page, quote=quote, boxes=boxes))
        return result

    async def close_document(self) -> str:
        """Close the PDF viewer."""
        self.session.dispatch(CloseDocument())
        landed(*phrase(self.spoken, "done"))
        return "Closed."

    async def run_calculator(self, request: CalculatorRequest) -> str:
        """Run Saatvik's solar savings calculator on the visitor's screen. Needs
        their state and either monthly units or monthly bill. The estimate comes
        back from the page. Say one short line with it."""
        units, bill, rate = request.monthly_units, request.monthly_bill_inr, request.rate_per_unit
        if units is None and bill is not None and rate:
            units = round(bill / rate)
        if rate is None and bill is not None and units:
            rate = round(bill / units, 2)
        if units is None:
            return "Not run: ask for their monthly units, or their bill and rate per unit."
        if rate is None:
            return "Not run: ask for their rate per unit, or their monthly bill."
        self.lead.update(monthly_units=units, monthly_bill_inr=bill, state=request.state)
        self._move(RunCalculator(units=units, state=request.state, rate=rate), "calculator")
        return (
            f"Running the calculator for {units:g} units a month in {request.state} at ₹{rate:g}."
        )

    async def find_dealer(self, request: DealerRequest) -> str:
        """Show Saatvik's dealers near the visitor in the dealer locator. The list
        comes back from the page. Say one short line with it."""
        state = _dealer_state(request.state)
        unlisted = bool(request.state) and state is None
        query = request.city or (request.state if unlisted else None)
        self.lead.update(state=request.state, city=request.city)
        self._move(FindDealer(state=state, query=query), "dealers")
        if unlisted:
            return (
                f"The locator lists no dealers by state in {request.state}; searched every "
                f"state for '{query}'. Say so."
            )
        return (
            f"Finding dealers{f' in {state}' if state else ''}{f' near {query}' if query else ''}."
        )

    async def open_enquiry(self, request: EnquiryRequest) -> str:
        """Open Saatvik's enquiry form on the visitor's screen with what they told
        you filled in. It never submits. Then tell them which fields are left for
        them, and that they tick consent and press Submit."""
        message = request.message or (
            self.lead.brief().summary if self.lead.fields != LeadFields() else None
        )
        prefill = EnquiryPrefill(
            name=request.name,
            company=request.company,
            email=request.email,
            mobile=request.mobile,
            category=request.category,
            state=request.state or self.lead.fields.state,
            message=message,
        )
        self.lead.update(
            enquiry_kind=request.kind,
            category=request.category,
            name=request.name,
            company=request.company,
        )
        self._move(OpenEnquiry(kind=request.kind, prefill=prefill), "enquiry")
        self._brief_changed()
        filled = [k for k, v in prefill.model_dump().items() if v]
        left = [k for k in ("name", "email", "mobile", "state", "category") if k not in filled]
        return (
            f"The {request.kind} form is open with {', '.join(filled) or 'nothing'} filled in. "
            f"Left for the visitor: {', '.join(left) or 'nothing required'}, the consent box and "
            "Submit."
        )

    async def update_lead(self, request: LeadUpdate) -> str:
        """Record what the visitor just told you about their need, for Saatvik's
        sales team. Silent: call it alongside your reply, never mention it."""
        changed = self.lead.update(**request.model_dump())
        if changed:
            self._brief_changed()
        return "noted"

    async def set_language(self, request: LanguageRequest) -> str:
        """Conduct the rest of the call in another language, listening and
        speaking. Call it when they ask for a language in words that are not
        already it — "Can you speak Hindi?" — and to go back to English. Say one
        short line in the language the call is in now, in the same response. A
        visitor already speaking Hindi has been switched: do not call it for them."""
        configure_soon(self.session, self._speaking(request.language))
        self.lead.update(language=request.language)
        logger.info("saatvik: language -> {}", request.language)
        return "ok"

    def _speaking(self, language: LanguageName) -> Config:
        """Both legs of ``language``, recorded as the one he speaks now, and
        the widget's toggle moved to it."""
        speech = SPEECH[language]
        if speech.spoken != self.spoken:
            self.session.dispatch(LanguageChanged(language=_TAG[language]))
        self.spoken = speech.spoken
        return Config(
            # Carried on every switch: unset, it drops back to the deployment's 7.
            stt=SttConfig(language=speech.heard, patience=PATIENCE),
            tts=TtsConfig(voice=speech.voice, language=speech.spoken),
        )


def _dealer_line(d: Dealer) -> str:
    return ", ".join(x for x in (d.name, d.type, d.city, d.phone) if x)


__all__ = [
    "CloseDocument",
    "FindDealer",
    "LanguageChanged",
    "LeadBrief",
    "Navigate",
    "Observed",
    "OpenDocument",
    "OpenEnquiry",
    "OpenFaq",
    "QuoteBox",
    "RunCalculator",
    "SaatvikBrain",
    "Score",
    "ShowSection",
]
