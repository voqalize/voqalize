"""SaatvikBrain — Tushar, a solar advisor on www.saatvikgroup.com.

The site is Saatvik Green Energy's, not ours. A browser extension injects the
widget and a small adapter into it; the adapter turns each
:class:`~voqalize.sdk.Action` below into a move on Saatvik's own page — a route,
a section scrolled to and ringed, an FAQ opened, a datasheet open at the page
that answers the question, the savings calculator run, the dealer locator
filtered, the enquiry form filled in — and reports every page, result and form
back as a typed event (:mod:`.app_events`).

Four things shape every decision here.

**A product expert, not a lead-capturer.** Every turn answers what was asked,
in words, as a conversation: the answer, why it matters for this visitor, and
usually a question back. A move on the page goes beside the answer when it
helps, and is talked about, never just pointed at. The model keeps no lead: the brief Saatvik's sales team receives
(:mod:`.lead`) is filled by the brain from what it already sees — the
calculator's inputs, the dealer search, the enquiry form, the pages and
documents opened, the questions asked — and never costs a tool call inside a
reply. A dev call where the model was told to record the lead every turn
answered nothing at all: each reply was bookkeeping and a page move.

**Every figure has a source.** A wattage, efficiency, warranty or subsidy amount
is spoken from L1 (in this prompt), an L2 topic he read, a search of the site,
or what the page itself reported. A datasheet figure is shown, not just said:
the PDF opens at its page with the figure highlighted, and the brain checks the
quote is on that page before it is sent (:meth:`.knowledge.Knowledge.find_quote`).

**Nothing on the page is invented.** A path he navigates to, a heading he
scrolls to and an FAQ he opens are checked against the crawl and against what
the page last reported; anything else is refused before it reaches the page.

**The form is the visitor's.** He fills in what they told him, adds to it as
they tell him more — a number or email they say is filled in and read back —
and rings what is left. He never asks for a number or email, never ticks
consent and never submits; the visitor presses Submit themselves.

How a result that arrives after his turn gets spoken — the calculator's
estimate, the dealers, a submitted form — is in :meth:`SaatvikBrain.on_user_idle`.
"""

from __future__ import annotations

import inspect
import re
import time
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
from voqalize_demos.acknowledge import Acknowledger, Kind, Vocabulary, hold_the_floor

from voqalize.sdk import (
    Action,
    RequestRejected,
    RTVIMessage,
    RTVIType,
    Session,
    Speech,
    SpeechChunk,
    SpeechStart,
    UserIdle,
    UserMessage,
)
from voqalize.sdk.voice import ToolChoice
from voqalize.sdk.wire import Config, IdleConfig, Language, SttConfig, TtsConfig, Voice

from . import knowledge as kb
from .app_events import (
    SAATVIK_EVENTS,
    BookingFields,
    BookingOpened,
    BookingSubmitted,
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

#: LOW, not the SDK's MINIMAL. At MINIMAL, Gemini mostly made the page call first
#: and wrote nothing, so the visitor heard only the brain's written "ये देखिए।" or
#: "Here's our … page." (dev calls ab8f6acb and ffdcd2d2, 2026-10-14). At LOW it
#: writes the whole answer first and calls at the end, and the page moves while he
#: is still talking — the marketing site's guide measured the same switch, at
#: about 1.5 s to the first word, which his nod covers.
THINKING = types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)

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
#: How long a pause the recognizer waits out before the visitor's turn ends: a
#: little more than the other demos'. On the owner's hotspot call (1c91dcfc) the
#: uplink stalled every 10 to 20 s and, at the demos' patience, "How does this one
#: compare? … Against the mono." reached Tushar as two turns.
SAATVIK_PATIENCE = PATIENCE + 2
#: A message that arrives this soon after the last one is the rest of the same
#: thought, split by a pause: answered without a nod of its own, so the visitor
#: does not hear a nod cut off and another start.
_FRAGMENT_S = 4.0

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


class OpenTab(Action):
    """Click one of the page's spec tabs, scroll to it and ring its panel."""

    label: str


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


class BookingPrefill(BaseModel):
    name: str | None = None
    mobile: str | None = None
    email: str | None = None
    address: str | None = None
    state: str | None = None
    city: str | None = None
    pincode: str | None = None


#: The products with a BOOK NOW, by the slug /book?product= takes. Any other
#: slug silently books the TEJ PLUS G12R module, so only these are ever sent.
ProductSlug = Literal[
    "surya-connect-kit",
    "tej-plus-g12r",
    "tej-m10r",
    "n-topcon",
    "bifacial-g2tb",
    "mono-perc",
    "vega-g2wb",
    "uday-single-phase",
    "uday-three-phase",
    "uday-plus-hybrid",
]
#: The product a page's BOOK NOW books, so "book this" on it needs no name.
_BOOKABLE: dict[str, ProductSlug] = {
    "/solar-kits": "surya-connect-kit",
    "/modules/bifacial-g12r": "tej-plus-g12r",
    "/modules/bifacial-g2g-m10r": "tej-m10r",
    "/modules/n-topcon": "n-topcon",
    "/modules/bifacial-g2tb": "bifacial-g2tb",
    "/modules/mono-perc": "mono-perc",
    "/modules/mono-facial-g2wb": "vega-g2wb",
    "/inverters": "uday-single-phase",
    "/inverters/single-phase": "uday-single-phase",
    "/inverters/three-phase": "uday-three-phase",
    "/inverters/hybrid": "uday-plus-hybrid",
}


class BookProduct(Action):
    """Open ``product``'s booking page (its BOOK NOW), choose ``installation`` on
    its first step, press Continue, and fill in ``details`` on the second. The
    page rings the fields still empty, the consent box and CONFIRM BOOKING; it
    never ticks consent and never confirms."""

    product: ProductSlug
    installation: Literal["residential", "commercial"]
    details: BookingPrefill


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
    """Only what the visitor said, in their words' numbers: leave out anything
    they did not say rather than guess it."""

    state: CalculatorState | None = Field(
        default=None, description="The visitor's state, only if they named it."
    )
    monthly_units: float | None = Field(
        default=None, description="Units (kWh) the visitor uses a month, only if they said."
    )
    monthly_bill_inr: float | None = Field(
        default=None,
        description="The visitor's monthly electricity bill in rupees, only if they said.",
    )
    rate_per_unit: float | None = Field(
        default=None, description="Rupees per unit, only if they said."
    )


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
        description="One or two sentences for the sales team: what they need, in their terms.",
    )
    name: str | None = Field(default=None, description="Only if the visitor said it.")
    company: str | None = Field(default=None, description="Only if the visitor said it.")
    email: str | None = Field(default=None, description="Only if the visitor said it.")
    mobile: str | None = Field(default=None, description="Only if the visitor said it.")
    # What the call has told you that the sales team needs, all optional and
    # only as the visitor said it. Gathered here, once, when the form opens —
    # never as bookkeeping inside an ordinary reply.
    segment: Segment | None = Field(default=None, description="Who they are, if clear.")
    need: str | None = Field(default=None, description="What they want, in a few words.")
    city: str | None = Field(default=None, description="City or district, if they said.")
    system_size_kw: float | None = None
    monthly_units: float | None = None
    monthly_bill_inr: float | None = None
    roof_type: str | None = Field(default=None, description="e.g. RCC flat, tin sheet, tiled.")
    roof_area: str | None = Field(default=None, description="As they said it, e.g. '800 sq ft'.")
    ownership: Ownership | None = Field(default=None, description="Of the roof or site.")
    timeline: Timeline | None = None
    callback_requested: bool | None = Field(default=None, description="They want a person to call.")
    preferred_time: str | None = Field(default=None, description="Best time to call them.")


class BookingRequest(BaseModel):
    product: ProductSlug | None = Field(
        default=None,
        description="Which product to book; leave empty to book the product on their page.",
    )
    installation: Literal["residential", "commercial"] = Field(
        description="residential for a home, commercial for a shop, office or factory."
    )
    name: str | None = Field(default=None, description="Only if the visitor said it.")
    mobile: str | None = Field(default=None, description="Ten digits, only if the visitor said it.")
    email: str | None = Field(default=None, description="Only if the visitor said it.")
    address: str | None = Field(
        default=None, description="House or flat, street, area; only if they said it."
    )
    state: str | None = Field(default=None, description="Full state name, if known.")
    city: str | None = Field(default=None, description="If they said it.")
    pincode: str | None = Field(default=None, description="Six digits, if they said it.")


class TabRequest(BaseModel):
    label: str = Field(description="The tab's label as the page shows it, e.g. MECHANICAL.")


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
        if p.path.count("/") > _SITE_MAP_DEPTH or p.path in kb.REDIRECTS:
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
    return f"""You are {AGENT_NAME}, the solar advisor on Saatvik Green Energy's website, www.saatvikgroup.com. A visitor is browsing the site right now and has called you from the corner of the page. You can see and move their screen: you open Saatvik's pages, scroll to sections, open FAQs, open datasheets at the right page with the figure highlighted, run the savings calculator, find dealers and fill in the enquiry form with them. You are warm, expert and conversational — the advisor in a showroom who knows the panels inside out, explains them in plain words, relates them to the visitor's own home, and keeps the conversation going. Going solar should feel simple and personal after talking to you.

# A good turn has three parts
1. Answer what they asked, first, in plain words: which panel, which inverter, what size, and why it suits them.
2. Show it, and talk about it. If a page, section, FAQ or datasheet fits, move the page in the same response, and name one concrete thing on it that matters for them: "See the thirty-year warranty in the comparison? That's five years more than Mono PERC." In Hindi: "तुलना में तीस साल की वारंटी देखिए, जो Mono PERC से पाँच साल ज़्यादा है।" Never read the page out. Never say only "here it is", "here's the page", "ये देखिए।" or "यह रहा।": the screen moving already says that. A reply that only points at the screen is a failed turn.
3. Hand it back. End with one short question or offer that moves the conversation on. Make it about them: their roof, their monthly units or bill, power cuts where they live, when they want it. Or offer the next natural step ("Want me to run the savings calculator with you?"). Vary it. Never end with "anything else?" or "let me know if you have questions".

# How you sound
You are heard, not read, so keep it light and warm, like a helpful advisor in a showroom.
- A turn is three or four short sentences, about forty words: the answer, one thing on the screen or one reason, the question. Stop there.
- Every sentence under fifteen words. Small, everyday words. One idea per sentence. One number per sentence.
- THE FIRST SENTENCE IS A FEW WORDS. The visitor hears nothing until your whole first sentence has been voiced, so open every reply, in English or Hindi, with a sentence of two to six words that ends in a full stop, with the answer in it.
- Go longer only when they ask you to explain, tell them more, or just talk about something ("tell me more", "explain this", "कुछ बताइए", "इसके बारे में बात करो"). Then talk properly: five to eight short sentences about what they asked or what is on their screen, picking what matters for a home buyer, and end with a question.
- Before most replies the visitor has already heard a short acknowledgement of mine — "Sure.", "Let me see.", "जी।" — the moment they stopped speaking. So never open with one: your first word is the answer. No "great question", no repeating their question back.
- Spoken words only: no lists, no markdown, no symbols, never an exclamation mark. Write every number and unit as spoken words, never digits or symbols: "three kilowatts", never "3 kW"; "five hundred and eighty watts", never "580 Wp"; "about seventy-eight thousand rupees", never "₹78,000". In Hindi too: "तीन किलोवाट", never "३ किलोवाट" or "3 kW".
- English by default. A visitor who speaks Hindi or Hinglish is answered in Hindi, written in Devanagari; you are a man, so use masculine forms of yourself ("मैं दिखाता हूँ", "मैंने खोल दिया है"). Product names and model numbers stay as Saatvik writes them. One language per reply: in a Hindi reply every sentence is Hindi, with no English sentence in it. That includes the line about their screen: in Hindi it is "स्क्रीन पर किट के सारे पार्ट्स देखिए।" or "डेटाशीट के पेज तीन पर पाँच किलोवाट की किट देखिए।", never "See … on your screen?". Before you finish a Hindi reply, check that no sentence in it is English.
- Lines in square brackets come from the page, not the visitor: what they opened, what a form or the calculator shows. Never read them out; use them.

# Every response starts with words
Write your whole answer first, then make the page calls at the end of the same response. The page moves while you are still talking. A response that is only tool calls is silence: after it you do not speak again until the visitor does, and what a page call returns reaches you only on your next turn.
- The one exception is a read. read_topic and search_site come straight back to you within this same turn. When you need one, call it first, with nothing written before it, then give your one reply, the answer and the move, once it is back.
- Never promise more to come ("let me check", "let me find that", "let me open"): nothing comes after it. Talk about what they see, as already there.

# What that sounds like
Match this rhythm: short sentences, one idea each, words before calls.
Visitor: "Can I put solar on my house?"
You: "Yes, most homes can. You need a roof you control, with some shade-free space. About a hundred square feet gives you one kilowatt. See the five steps, from site survey to first unit? Roughly how many units do you use a month?" then navigate(path="/epc-solutions/rooftop/residential").
Visitor: "Can you recommend a kit for a three kilowatt system?"
You: "SuryaConnect is the simple choice. It comes as one kit: panels, inverter, wiring and mounting. There's a three kilowatt size, so it fits you exactly. See every component listed on the page? Do you get power cuts where you live?" then navigate(path="/solar-kits").
Visitor: "Which panel should I buy?"
You: "For a home, I'd pick N-TOPCon. It makes more power in heat and low light. It also carries a thirty-year performance warranty. See the N-TOPCon versus Mono PERC comparison? Is your roof space tight, or is budget the bigger concern?" then navigate(path="/modules/n-topcon").
Visitor: "Is this suitable for a home?"
You: "Yes, it suits a home well. TEJ panels get the most out of a small roof. And they lose less power on hot days. Saatvik's home kits use N-TOPCon too. How big is your roof, roughly?"
Visitor: "Tell me about this."
You: "This is SuryaConnect, Saatvik's complete home kit. Everything comes together: panels, inverter, distribution boxes, cables and mounting. The panels are made-in-India N-TOPCon, which PM Surya Ghar asks for. It connects to the grid and cuts your bill. It has no battery, so it pauses in a power cut. There are three and five kilowatt kits. Shall I work out which size fits your bill?"
Visitor: "Is there a dealer near me in Jaipur?"
You: "Yes, Saatvik has dealers across Rajasthan. A local dealer does the site survey and the installation. The Jaipur list is coming up on your screen. Is this for your home?" then find_dealer(state="Rajasthan", city="Jaipur").
Visitor: "I use about four hundred units a month in Gujarat, at seven rupees a unit."
You: "That's a good size for solar. I'm putting those numbers into Saatvik's calculator. It works out the system size, the subsidy and your yearly savings. Is your roof flat concrete?" then run_calculator(state="Gujarat", monthly_units=400, rate_per_unit=7).
Visitor: "मैं घर पर सोलर लगा सकता हूँ क्या?"
You: "जी, बिल्कुल लगा सकते हैं। बस छत आपकी हो और उस पर धूप आती हो। एक किलोवाट के लिए करीब सौ वर्ग फुट जगह चाहिए। आपका महीने का बिल लगभग कितने यूनिट का आता है?" then navigate(path="/epc-solutions/rooftop/residential").
Visitor: "इसके बारे में कुछ बात करो।"
You: "यह सूर्याकनेक्ट किट है। इसमें पैनल, इन्वर्टर, तार और माउंटिंग सब साथ आता है। पैनल भारत में बने N-TOPCon हैं, तो PM Surya Ghar की सब्सिडी मिल सकती है। यह ग्रिड से जुड़कर आपका बिल घटाती है। तीन और पाँच किलोवाट की किट आती है। क्या मैं आपके बिल से सही साइज़ निकालूँ?"

# Keep threads
Remember what they tell you about themselves and use it: their city, their bill or units, their roof, power cuts, what they asked earlier. "For three kilowatts in Bengaluru, …". Never ask again for something they already said. If they mentioned power cuts, bring up the hybrid inverter and battery when it fits.

# What you know
- Every figure — a wattage, efficiency, warranty, price, subsidy amount, timeline — comes from the knowledge below, a topic you read, a search result, or what the page reported. Never from memory. If you cannot find it, say so plainly, and say where on Saatvik's site it might be.
- Read a topic with read_topic before answering anything it covers beyond what is below. Topics:
{_topics(k)}
- For a specific figure, model or document, search_site. When the answer is on a datasheet or manual page, open it with open_document at that page and highlight the figure with a quote copied from the search result.
- PRICES. Saatvik publishes no price for any product, kit or size. For a cost or savings question, take them to the calculator (below). Never give a price, a cost range or a saving from memory, and never estimate, scale or round one.
- Subsidies and policy: give the national scheme as Saatvik's pages describe it. State top-ups, DISCOM rules and net metering vary by state and change often: say so, and point them to the official national portal. Never promise an amount for their state.
- Investors, the company, news and careers are answered from the topics (company, investors, newsroom). Never steer an investor or a job seeker to the sales enquiry form; open the right page for them instead.

# Never push a call back
- NEVER offer a call back, a call from the team, an expert, sales, a site survey, the enquiry form or a booking unless the visitor asks for it themselves ("connect me", "I want to talk to someone", "call me", "show me the form", "book it"). You are here to guide them yourself, as far as they want to go. The question that ends your turn is always about their need, never "shall I arrange a call back?".

# Cost and savings go to the calculator
- When they ask what it will cost, what they will pay, or how much they will save, take them to Saatvik's calculator in the same response: navigate(path="/solar-calculator"), and say it works out Saatvik's estimate for their state: the system size, the cost after subsidy, the yearly savings and the payback. Then ask for the first input it needs that they have not given.
- Never quote a saving, a payback or a cost range yourself, and never invent one: those come only from the calculator's result.
- The calculator needs their state, their monthly units and their rate per unit. Never assume or estimate any of them, not even an "average rate" for their state. If they do not know their rate, say it is printed on their electricity bill, or that with their monthly bill and their monthly units you can work it out. Once you have all three, run_calculator, and talk them through the result on their screen.

# Moving the page
- navigate only to a path from the site pages list below or from a search result. show_section and open_faq take a heading or question on the page the visitor has open.
- To size a system or show savings you can answer from the rules of thumb below first, in words. run_calculator is for when they want Saatvik's estimate: it needs their state, and two of their monthly units, their monthly bill and their rate per unit — every one exactly as the visitor said it. Never guess, assume or default any of them: no state they did not name, no rate they did not give. A bill in rupees on its own is not units. Ask for what is missing, one thing at a time, before calling it. The estimate appears on the page and comes back to you: talk them through it from the page's figures.
- find_dealer for a dealer near them. The dealer list comes back to you from the page.

# Buttons, forms and choices, by voice
The visitor can ask you to press anything on their screen or fill any form on it: "click Book now", "open the datasheet", "fill this form", "choose residential". Do it with your tools, in the same response as your words, and say what is now on their screen. Never say you cannot click.
- BOOK NOW, on the kit page, any module page and any Uday inverter page, is book_product: leave product empty to book the one on their page, or name it. On the kit page (/solar-kits), DOWNLOAD DATASHEET is open_document with the kit datasheet (document_id saatvik-solar-kit-on-grid-n-topcon-datasheet; page one is the three kilowatt features, page two its kit list, page three the five kilowatt features, page four its kit list). DOWNLOAD BROCHURE is open_document with saatvik-solar-kit-brochure at page two (page one is only artwork). CONTACT US is open_enquiry, domestic, category Solar Kit. ESTIMATE MY SAVINGS is run_calculator when you have their state, units and rate; otherwise navigate to /solar-calculator and ask for what is missing.
- Spec tabs on a product page (ELECTRICAL, MECHANICAL, WARRANTY on a module; the battery, pumps and BESS have their own): open_tab with the label, when they ask about what is on one, or say "click mechanical". Only the open tab's rows are on screen.
- On the booking page: the residential or commercial choice, Continue, and the details step are all book_product. On the calculator: Calculate is run_calculator. On the contact page: the enquiry tabs and fields are open_enquiry; Find a dealer is find_dealer.
- "Fill this form" means the form on their screen: the booking page is book_product, the contact form is open_enquiry, the calculator is run_calculator. Fill what they have told you, and ask for what is missing, one thing at a time, except their mobile number and email: those they say if they want to, or type.
- What stays theirs, always: the consent box, Submit, Confirm booking, and the calculator's "Unlock my report" form. If they ask you to press one of those, say kindly that it is theirs to press, and point to it.
- A button with no tool here: say what it does, and offer what you can do instead.
- When there is a choice, say the options: the kit comes in three and five kilowatts; booking asks residential or commercial; the contact page has domestic, export and dealer enquiries.
- To buy, book or order the kit, a module or an Uday inverter, use book_product: it is the product page's own path, with no payment now. The battery, pumps, BESS, transformers, film and EPC have no booking: a quote, a call back or a question for sales is open_enquiry.

# The visitor's enquiry
- You are a product expert. The question that ends your turn is about their need when the answer changes your advice — their kind of building, their bill, power cuts, their roof — one question per turn, and never to fill in a form. Nothing is recorded during the conversation; there is no bookkeeping for you to do.
- When they want a quote, a call back or to talk to sales, open_enquiry with what they told you, including what the sales team needs from the call so far (their need, city, bill or units, roof, timeline) as far as they said it. Then tell them, in a sentence or two, which fields are left, and that they tick the consent box and press Submit themselves. Never say it is submitted until the page tells you.
- FILLING THE FORM IS YOUR JOB, the enquiry form and the booking page alike (book_product works the same way: call it again to add, and what is filled stays). Whenever they tell you their name, company, email, mobile number, city or what to write in the message, or ask you to fill or type something in, call open_enquiry again with it, in the same response as your words. What is already filled stays; you only add. Never refuse, never tell them they must type it themselves, and never give a reason such as privacy or security: there is none. The only things that stay theirs are the consent box and Submit.
- Never ask them to read out a phone number or email. But when they say one, fill it in, then read it back so they can check it, because a number heard over a call is easily misheard: "I've put nine eight four seven five, four one seven nine zero. Is that right?" If they correct it, fill it again.
- You know only what they said in this call. If they say "you know my name" or "you have my email", say kindly that you don't have it yet, and ask them to say it or type it in.
- A question while the form is open is a question: answer it, as in any other turn. Call open_enquiry only when they give you something for the form.
- A visitor who wants a person: give Saatvik's toll-free number or WhatsApp from the knowledge below, or open the enquiry form with callback_requested, and say a person will call.
- When the page tells you the form was submitted, thank them in one sentence, say Saatvik's team will be in touch, and go back to answering their questions.

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
    "booking": {
        Language.EN: ("Here's the booking page, with what you told me filled in.",),
        Language.HI: ("यह रहा बुकिंग पेज, आपकी बताई बातें भरी हुई हैं।",),
    },
}
assert all({s.spoken for s in SPEECH.values()} <= set(v) for v in _LANDED_LINES.values()), (
    "a spoken language has no written line for a move"
)

# ─── His nod ───────────────────────────────────────────────────────────────────

#: Said the moment the visitor stops, while the model thinks. See
#: :mod:`voqalize_demos.acknowledge`; the Hindi lines are his, so masculine.
_ACK_LINES: dict[Language, dict[Kind, tuple[str, ...]]] = {
    Language.EN: {
        "request": ("Sure.", "Okay.", "Of course.", "Certainly."),
        "question": ("Let me see.", "Hmm, let me see.", "Okay."),
        "correction": ("I see.", "Understood.", "Right."),
        "statement": ("Okay.", "Got it.", "Right."),
    },
    Language.HI: {
        "request": ("जी।", "ज़रूर।", "ठीक है।", "अच्छा।"),
        "question": ("जी, बताता हूँ।", "जी।", "हम्म, देखता हूँ।"),
        "correction": ("अच्छा।", "समझ गया।", "जी।"),
        "statement": ("जी।", "अच्छा।", "ठीक है।"),
    },
}
#: Whether the widget shows the brief to the visitor (see ``share_brief``).
#: Module-level so a test can pin it.
SHARE_BRIEF = False

#: The share of readable turns he nods on, and how long the model may stay
#: quiet after a nod before he holds the floor. Module-level so a test can pin them.
ACK_RATE = 0.75
ACK_HOLD_AFTER_S = 4.0
_ACK_HOLD = {
    Language.EN: ("One moment.", "Just a moment."),
    Language.HI: ("एक पल।", "बस एक पल।"),
}
_ACK_SORRY = {
    Language.EN: "Sorry, that's taking a little longer.",
    Language.HI: "माफ़ कीजिए, थोड़ा समय लग रहा है।",
}
#: A visitor's ordinary words about going solar, so the reading trusts them.
_ACK_WORDS = Vocabulary(
    common=frozenset(
        [
            "solar",
            "panel",
            "panels",
            "module",
            "modules",
            "roof",
            "rooftop",
            "house",
            "home",
            "bill",
            "units",
            "unit",
            "subsidy",
            "inverter",
            "battery",
            "batteries",
            "kw",
            "kilowatt",
            "price",
            "cost",
            "dealer",
            "installation",
            "system",
            "electricity",
            "monthly",
            "topcon",
            "perc",
            "bifacial",
            "pump",
            "warranty",
            "company",
            "सोलर",
            "पैनल",
            "छत",
            "घर",
            "बिल",
            "यूनिट",
            "सब्सिडी",
            "बिजली",
        ]
    ),
)


def _avatar_state(session: Session, state: Literal["WORKING"] | None) -> None:
    """The talking head's working latch, as qween sends it: held until speech
    owed has played, ended by the reply's own playout."""
    session.send_rtvi(RTVIType.SERVER_MESSAGE, {"type": "avatar", "cmd": "state", "state": state})


#: How much of a page's own text reaches the model in a note.
_CALC_CHARS = 1200
_HEADINGS_IN_NOTE = 20
_FAQS_IN_NOTE = 12
_DEALERS_IN_NOTE = 8
_SEARCH_HITS = 6


#: Said when the calculator could not run and the turn said nothing: the
#: question that gets it run.
_ASK_UNITS = {
    Language.EN: ("Roughly how many units do you use a month? It's on your bill.",),
    Language.HI: ("आप महीने में लगभग कितने यूनिट इस्तेमाल करते हैं? यह आपके बिल पर होता है।",),
}
_ASK_RATE = {
    Language.EN: ("And roughly what do you pay per unit? It's on your bill.",),
    Language.HI: ("और आप एक यूनिट का लगभग कितना देते हैं? यह आपके बिल पर होता है।",),
}
_ASK_STATE = {
    Language.EN: ("And which state are you in?",),
    Language.HI: ("और आप किस राज्य में हैं?",),
}


def _short_title(title: str) -> str:
    """A page or document title as said aloud: the part before the site's name."""
    return title.split(" — ")[0].split(" | ")[0].strip()


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
        share_brief: bool | None = None,
    ) -> None:
        self.kb = knowledge if knowledge is not None else kb.KNOWLEDGE
        super().__init__(client=client, system_instruction=_prompt(self.kb), model=model)
        self._config = self._config.model_copy(update={"thinking_config": THINKING})
        #: Show the brief in the widget. Off for a visitor, who came to ask
        #: about solar; on for a pitch that shows Saatvik what sales receives.
        self._share_brief = SHARE_BRIEF if share_brief is None else share_brief
        #: When the visitor's last message arrived, to tell a fragment from a question.
        self._heard_at = float("-inf")
        self.spoken: Language = SPEECH[OPENING].spoken
        self._fallback = FallbackLine()
        self._ack = Acknowledger(
            _ACK_LINES, _ACK_HOLD, _ACK_SORRY, _ACK_WORDS, ACK_RATE, ACK_HOLD_AFTER_S
        )
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
        #: What the enquiry form has been filled with this call, so each
        #: open_enquiry adds to it.
        self._prefill: EnquiryPrefill | None = None
        #: The same for the booking page, and the product it books.
        self._booking: BookingPrefill | None = None
        self._booked_product: ProductSlug | None = None

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        init = session.init or {}
        self._path = canonical_path(str(init.get("page") or "/"))
        lang = BY_TAG.get(str(init.get("lang") or ""), OPENING)
        # His own voice, settled here and not by the page. Both language legs
        # move together; the toggle and `set_language` move them again.
        await session.configure(
            Config(
                stt=SttConfig(language=SPEECH[lang].heard, patience=SAATVIK_PATIENCE),
                tts=TtsConfig(voice=SPEECH[lang].voice, language=SPEECH[lang].spoken),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
            )
        )
        self.spoken = SPEECH[lang].spoken
        self.lead.update(language=lang)
        self.lead.saw_page(self._path)
        logger.info("saatvik: session start on {} in {}", self._path, lang)

    async def on_session_end(self, session: Session) -> None:
        """A submitted lead goes to the webhook once more at the end, with
        every page and question that came after the form."""
        if self.lead.submitted:
            post_brief(self.lead.brief())

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
        now = time.monotonic()
        fragment, self._heard_at = now - self._heard_at < _FRAGMENT_S, now
        # His nod while the model thinks, in the voice now speaking: a unit of
        # his own, never in the model's context. Once it has played the face
        # looks away and works until the answer starts. The rest of a split
        # question gets none: the first half's nod was its nod.
        if not fragment and (nod := self._ack.line(msg.text, self.spoken)) is not None:
            logger.info("saatvik: ack {!r}", nod)
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
                    self, self._ack, lambda: self.spoken, turn, answered
                ):
                    yield event
            finally:
                answered()
            return
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
                "could show them, or the savings estimate. Then let them "
                "browse."
            )
        self._note(f"{quiet} {ask}")
        return self.respond(session)

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The model's turn. If it moved the page and said nothing, the model is
        asked once more with tools off, so he talks about what he just showed;
        only if that is silent too does he say a written line of his own
        (:mod:`voqalize_demos.silent_turn`).

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
        turn = self._fallback.speak_if_silent(
            self, super().respond(session), again=lambda: self._talk_now(session)
        )
        async for event in turn:
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

    def _talk_now(self, session: Session) -> AsyncGenerator[Speech, None]:
        """One more model request with tools off: the page has moved, and what he
        says now is about what is on it. The tools stay declared, so the calls
        already in the context still read, but none may be made."""
        return self.respond_with(session, tools=ToolChoice.NONE)

    async def _run(self, tool: Any, call: types.FunctionCall) -> types.Part:
        """Every tool takes one model, ``request``. Gemini sometimes sends that
        model's fields flat (``{"heading": …}`` for ``{"request": {"heading": …}}``),
        which the SDK refuses: nothing moves, nothing lands, and the turn ends in
        silence (an eval call sat 90 s on one). Wrap them before the call runs."""
        args = dict(call.args or {})
        if (
            tool is not None
            and args
            and "request" not in args
            and "request" in inspect.signature(tool).parameters
        ):
            logger.info("saatvik: {} called with flat arguments; wrapping them", call.name)
            call = call.model_copy(update={"args": {"request": args}})
        return await super()._run(tool, call)

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
            case BookingOpened():
                missing = ", ".join(event.missing) or "none"
                return (
                    f"[The booking page for {event.product or 'the product'} is at step two of "
                    f"two, for a {event.installation} "
                    f"installation. Fields still empty: {missing}. The visitor ticks consent and "
                    "presses Confirm booking themselves.]"
                )
            case BookingSubmitted():
                return self._booked(event.product, event.installation, event.fields)
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
                "Say so in one sentence and offer to look in a nearby city instead."
            )
            return f"[The dealer locator shows no dealers for '{event.state} {event.query}'.]"
        self._talk_through(
            "The dealers are on their screen and they have not spoken. Name the nearest one "
            "or two in a sentence, and ask one question about their need."
        )
        listed = _clip([_dealer_line(d) for d in event.dealers], _DEALERS_IN_NOTE)
        return f"[The dealer locator shows, for '{event.state} {event.query}': {listed}]"

    def _submitted(self, kind: str, fields: EnquiryFields) -> str:
        self.lead.update(
            enquiry_kind=kind,
            **{k: v for k, v in fields.model_dump().items() if v},
        )
        self.lead.submitted = True
        self._brief_changed()
        self._talk_through(
            "They have just submitted the enquiry. Thank them in one sentence, say "
            "Saatvik's team will be in touch, and offer to keep answering their questions."
        )
        return f"[The visitor submitted the {kind} enquiry form. It reached Saatvik's sales team.]"

    def _booked(self, product: str, installation: str, fields: BookingFields) -> str:
        self.lead.update(
            name=fields.name or None,
            city=fields.city or None,
            state=fields.state or None,
            enquiry_kind="domestic",
        )
        self.lead.submitted = True
        self._brief_changed()
        self._talk_through(
            "They have just confirmed the booking. Thank them in one sentence, say a "
            "Saatvik specialist will call to size the system and share a quote, with no "
            "payment now, and offer to keep answering their questions."
        )
        return f"[The visitor confirmed the booking of {product or 'the product'}, {installation}.]"

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
        if p.tabs:
            note += f" Its spec tabs: {', '.join(p.tabs)}."
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
        """Post the brief to the webhook once submitted, and show it in the
        widget when sharing is on."""
        brief = self.lead.brief()
        if self.lead.submitted:
            post_brief(brief)
        if self._share_brief:
            self.session.dispatch(brief)

    def _move(self, action: Action, lines: str | None = None, english: str | None = None) -> None:
        """Dispatch ``action``, with the written line for it should the turn say
        nothing: ``english`` when the call is in English and the move has
        something of its own to say, else its own under ``lines``, else the
        plain "shown"."""
        self.session.dispatch(action)
        if english and self.spoken == Language.EN:
            landed(english)
            return
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

    def _faq_answer(self, question: str) -> str | None:
        """The first sentence of a FAQ's own answer on the page the visitor has open."""
        page = self.kb.page(self._path)
        answer = next((f.a for f in page.faqs if f.q == question), "") if page else ""
        first = re.split(r"(?<=[.!?])\s", answer.strip(), maxsplit=1)[0]
        return first if 0 < len(first) <= 240 else None

    def _document_by_url(self, url: str) -> kb.Document | None:
        return next((d for d in self.kb.documents.values() if d.url == url), None)

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        """Read and search Saatvik's knowledge, move the visitor's page, run the
        calculator and the dealer locator, fill the enquiry, change language.
        Nothing here keeps the lead: the brain does that from what it sees."""
        return [
            self.read_topic,
            self.search_site,
            self.navigate,
            self.show_section,
            self.open_faq,
            self.open_tab,
            self.open_document,
            self.close_document,
            self.run_calculator,
            self.find_dealer,
            self.open_enquiry,
            self.book_product,
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
        """Open one of Saatvik's pages on the visitor's screen. In the same
        response, before the call, tell them what the page shows that answers
        them and why it matters for their home, then ask what you need next."""
        page = self.kb.page(request.path)
        if page is None:
            near = ", ".join(self.kb.near_paths(request.path)) or "none"
            return (
                f"Not opened: {request.path} is not a page on Saatvik's site. Closest: {near}. "
                "Tell the visitor if you said it was open."
            )
        self._move(Navigate(path=page.path), english=f"Here's our {_short_title(page.title)} page.")
        return f"Opened {page.title} ({page.path})."

    async def show_section(self, request: SectionRequest) -> str:
        """Scroll the visitor's page to a section and ring it — or, with text, one
        row or line inside it. In the same response, say what that section or row
        tells them and why it matters."""
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
        """Open one of the FAQs on the visitor's page and ring it. In the same
        response, give the answer in your own words."""
        faqs = self._faqs()
        question = _match(request.question, faqs)
        if question is None:
            return (
                f"Not opened: this page has no FAQ '{request.question}'. "
                f"Its FAQs: {_clip(faqs, _FAQS_IN_NOTE) or 'none'}."
            )
        self._move(OpenFaq(question=question), english=self._faq_answer(question))
        return f"Opened the FAQ '{question}'."

    async def open_tab(self, request: TabRequest) -> str:
        """Click one of the spec tabs on the visitor's page (ELECTRICAL,
        MECHANICAL, WARRANTY on a module; the battery's, a pump's or BESS's own),
        so its rows are on screen. In the same response, say the one figure on it
        that answers them."""
        tabs = self.page.tabs if self.page is not None else []
        label = _match(request.label, tabs)
        if label is None:
            return (
                f"Not opened: this page has no tab '{request.label}'. "
                f"Its tabs: {', '.join(tabs) or 'none'}."
            )
        self._move(OpenTab(label=label))
        return f"Opened the '{label}' tab."

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
        self._move(
            OpenDocument(url=doc.url, title=doc.title, page=page, quote=quote, boxes=boxes),
            english=f"Here's the {_short_title(doc.title)}"
            + (", with that line highlighted." if quote else "."),
        )
        return result

    async def close_document(self) -> str:
        """Close the PDF viewer."""
        self.session.dispatch(CloseDocument())
        landed(*phrase(self.spoken, "done"))
        return "Closed."

    async def run_calculator(self, request: CalculatorRequest) -> str:
        """Run Saatvik's solar savings calculator on the visitor's screen. Needs
        their state and two of monthly units, monthly bill and rate per unit,
        every one as the visitor said it: never a guess. The estimate comes back
        from the page. In the same response, say what you are working out for
        them."""
        units, bill, rate = request.monthly_units, request.monthly_bill_inr, request.rate_per_unit
        if units is None and bill is not None and rate:
            units = round(bill / rate)
        if rate is None and bill is not None and units:
            rate = round(bill / units, 2)
        if units is None:
            landed(*_ASK_UNITS[self.spoken])
            return "Not run: ask for their monthly units, or their bill and rate per unit."
        if rate is None:
            landed(*_ASK_RATE[self.spoken])
            return "Not run: ask for their rate per unit, or their monthly bill."
        if request.state is None:
            landed(*_ASK_STATE[self.spoken])
            return "Not run: ask which state they are in."
        self.lead.update(monthly_units=units, monthly_bill_inr=bill, state=request.state)
        self._move(RunCalculator(units=units, state=request.state, rate=rate), "calculator")
        return (
            f"Running the calculator for {units:g} units a month in {request.state} at ₹{rate:g}."
        )

    async def find_dealer(self, request: DealerRequest) -> str:
        """Show Saatvik's dealers near the visitor in the dealer locator. The list
        comes back from the page. In the same response, say what you are looking
        for and what a local dealer will do for them."""
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
        you filled in, or fill more into the open form: call it again whenever
        they give you their name, email, mobile, city or message. What is already
        filled stays. It never submits. Say which fields are left for them, and
        that they tick consent and press Submit."""
        self.lead.update(
            **request.model_dump(exclude={"kind", "message", "email", "mobile"}),
            enquiry_kind=request.kind,
        )
        message = request.message or (
            self.lead.brief().summary if self.lead.fields != LeadFields() else None
        )
        asked = EnquiryPrefill(
            name=request.name,
            company=request.company,
            email=request.email,
            mobile=request.mobile,
            category=request.category,
            state=request.state or self.lead.fields.state,
            message=message,
        )
        # A second call adds to the form rather than starting it again: the model
        # sends what the visitor just said, and the rest is what is already there.
        before = self._prefill.model_dump() if self._prefill is not None else {}
        prefill = EnquiryPrefill(
            **{k: v if v is not None else before.get(k) for k, v in asked.model_dump().items()}
        )
        self._prefill = prefill
        self._move(OpenEnquiry(kind=request.kind, prefill=prefill), "enquiry")
        self._brief_changed()
        filled = [k for k, v in prefill.model_dump().items() if v]
        left = [k for k in ("name", "email", "mobile", "state", "category") if k not in filled]
        return (
            f"The {request.kind} form is open with {', '.join(filled) or 'nothing'} filled in. "
            f"Left for the visitor: {', '.join(left) or 'nothing required'}, the consent box and "
            "Submit."
        )

    async def book_product(self, request: BookingRequest) -> str:
        """Book a product: its page's BOOK NOW (the SuryaConnect kit, a module or
        an Uday inverter). Opens its booking page, picks residential or
        commercial, presses Continue, and fills in what they told you. Call it
        again to add their name, mobile, email, address, city or pincode as they
        say them; what is filled stays. It never confirms. Say which fields are
        left, and that they tick consent and press Confirm booking."""
        product = request.product or _BOOKABLE.get(self._path) or self._booked_product
        if product is None:
            return (
                "Not opened: say which product to book. Bookable: the SuryaConnect kit, "
                "the six modules and the three Uday inverters."
            )
        if product != self._booked_product:
            self._booking = None
        self._booked_product = product
        asked = BookingPrefill(
            name=request.name,
            mobile=request.mobile,
            email=request.email,
            address=request.address,
            state=request.state or self.lead.fields.state,
            city=request.city or self.lead.fields.city,
            pincode=request.pincode,
        )
        before = self._booking.model_dump() if self._booking is not None else {}
        details = BookingPrefill(
            **{k: v if v is not None else before.get(k) for k, v in asked.model_dump().items()}
        )
        self._booking = details
        self.lead.update(name=request.name, city=request.city, state=request.state)
        self._move(
            BookProduct(product=product, installation=request.installation, details=details),
            "booking",
        )
        filled = [k for k, v in details.model_dump().items() if v]
        left = [k for k in BookingPrefill.model_fields if k not in filled]
        return (
            f"The {request.installation} booking for {product} is at step two with "
            f"{', '.join(filled) or 'nothing'} filled in. Left for the visitor: "
            f"{', '.join(left) or 'nothing'}, the consent box and Confirm booking."
        )

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
            stt=SttConfig(language=speech.heard, patience=SAATVIK_PATIENCE),
            tts=TtsConfig(voice=speech.voice, language=speech.spoken),
        )


def _dealer_line(d: Dealer) -> str:
    return ", ".join(x for x in (d.name, d.type, d.city, d.phone) if x)


__all__ = [
    "BookProduct",
    "CloseDocument",
    "FindDealer",
    "LanguageChanged",
    "LeadBrief",
    "Navigate",
    "Observed",
    "OpenDocument",
    "OpenEnquiry",
    "OpenFaq",
    "OpenTab",
    "QuoteBox",
    "RunCalculator",
    "SaatvikBrain",
    "Score",
    "ShowSection",
]
