"""ExploraBrain — Javier, a guide on explora.com and its booking site.

The site is Explora's, not ours. A browser extension injects the widget and a
small adapter into www.explora.com and reservations.explora.com; the adapter
turns each :class:`~voqalize.sdk.Action` below into a move on the tab in front:
a page opened, a section scrolled to and ringed, a tab or an accordion opened,
a lodge's availability checked on the booking site, an expedition's enquiry
filled in and sent. Every tab reports what it shows as a typed event
(:mod:`.app_events`), whichever of the visitor and Javier moved it.

He is built on the SendPotion guide (``demos/sendpotion``) and keeps its
shape: a guide, not a search box; every fact from the site; nothing on the page
invented; the screen following his voice through cues in his reply; English or
Latin American Spanish, as the visitor chose or speaks. What is new here is one
thing the site does and SendPotion's does not.

**Every page is a full page load.** explora.com is WordPress, and every move
between pages — the visitor's click or his cue — throws the page away and loads
the next one. The call survives it (the extension rejoins the same session on
the next page, and Voqalize holds the call and its queued audio meanwhile), but
nothing on the old page can still be ringed, and a sentence being spoken as the
page goes would be cut. So a ``{page: …}`` cue is not sent ahead with the
speech like the others: his reply is split there (:meth:`ExploraBrain._paced`).
What he said before it is spoken out; the page opens once his voice is quiet;
and the rest of the reply, with its cues, waits for the new page to report
itself — which it does only once the call has rejoined on it, so the rest is
heard on the page it is about and its cues land there.

**The booking is the visitor's, up to the button.** A lodge's availability is
checked on reservations.explora.com — the lodge, an open arrival day, the
nights — and he can take them on to the rooms and rates; he never goes past
them into the booking's payment. An expedition has an enquiry form instead: he
fills in every field from what the visitor told him, they tick "I'm not a
robot", and then he presses Send Message for them.
"""

from __future__ import annotations

import asyncio
import inspect
import math
import re
import time
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel, Field
from voqalize_demos import (
    PATIENCE,
    FallbackLine,
    GeminiBrain,
    configure_soon,
    landed,
    needs_result_now,
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
    SpeechEnd,
    SpeechStart,
    UserIdle,
    UserMessage,
)
from voqalize.sdk.voice import ToolChoice
from voqalize.sdk.wire import Config, IdleConfig, SttConfig, TtsConfig, Voice

from . import knowledge as kb
from .app_events import (
    EXPLORA_EVENTS,
    CommandFailed,
    EnquiryFields,
    EnquirySent,
    EnquiryState,
    ExploraEvent,
    LanguageRequested,
    PageChanged,
    StayState,
    TabInfo,
    TabsChanged,
)
from .cues import MAX_CUE, CueKind, CueParser, RawCue
from .knowledge import TOPIC_IDS, Knowledge, canonical_path, norm, site_path

AGENT_NAME = "Javier"

#: As SendPotion measured: at LOW, Gemini writes the answer and its cues first.
THINKING = types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)
#: SendPotion's model, measured there for first words and cue-writing.
MODEL = "gemini-3.8-flash"

# ─── Voice and timing ──────────────────────────────────────────────────────────

#: Javier's voice, SendPotion's: one man, recorded in English and in Latin
#: American Spanish.
VOICE = Voice.OMNIVOICE_JAVIER

#: A quiet visitor is someone looking at photographs of a lodge; a guide beside
#: them says something after a while, and not twice more.
_IDLE_MS = 20_000
_IDLE_NUDGES = 2
#: The idle window while a result the page produced is waiting to be talked
#: through (the calendar's open days, a filled form): a visitor who reacts
#: speaks first, one who is reading hears it from him.
_TALK_THROUGH_MS = 2_000
#: A visitor describing a trip pauses mid-sentence, as SendPotion's did.
EXPLORA_PATIENCE = PATIENCE + 2
#: A message this soon after the last one is the rest of the same thought.
_FRAGMENT_S = 4.0

#: How long the rest of a reply waits for the page a cue opened, beyond the
#: time his voice needs to finish what came before it. Voqalize holds a call
#: through a page load for ten seconds; past this the page is not coming.
_PAGE_WAIT_S = 9.0
#: His speaking pace, to tell how long the words before a page cue take to say.
_WORDS_PER_S = 2.8

# ─── Language ──────────────────────────────────────────────────────────────────

#: What he answers in, as the tag both legs of the call take. The European
#: recognizer hears either whatever it is set to and writes what it heard, so
#: the recognizer leg only follows the voice, as a pair, and the language is
#: decided here from words: the visitor's, then his own.
Lang = Literal["en", "es"]
OPENING: Lang = "en"
LANGUAGE_NAMES: dict[Lang, str] = {"en": "English", "es": "Spanish"}

#: What he says at the start of his next turn after the visitor pressed the
#: toggle: written, in the new language, read by the new voice.
TOGGLE_CONFIRM: dict[Lang, str] = {
    "en": "Sure, let's continue in English.",
    "es": "Claro, seguimos en español.",
}

# The small words of each language, which carry no topic: a sentence that uses
# several of one and none of the other is in that one, whatever its nouns are.
# Words both languages write ("a", "no", "me", "son") are in neither list.
_SPANISH_WORDS = frozenset(
    # A word list reads as words, so it stays a split string.
    """que qué de del el los las la una unas unos por para con como cómo cuánto cuanto
    cuánta cuesta cuestan puedes puede podrías quiero quisiera necesito tengo tienes
    tiene hay hola gracias sí está están estoy es eso esto esta este estos pero muy
    también hablar habla hablas hablemos español castellano usted ustedes mi mis tu tus
    su sus nosotros vale bueno claro dónde donde cuál cual cuándo cuando precio precios
    muéstrame dime explícame noches noche viaje viajar hotel hoteles desierto
    """.split()  # noqa: SIM905
)
_ENGLISH_WORDS = frozenset(
    """the is are was what how can could you your i i'm it it's this that these those do
    does show me my we our for with about and of to have has there here please want
    would like tell sure yes okay right of course let's
    """.split()  # noqa: SIM905
)
#: Enough of his reply to tell its language: its first sentence, or this many
#: characters. On SendPotion's dev call 826ccd1f the first chunk was " P".
_WRITTEN_ENOUGH = 60
_SENTENCE_END = re.compile(r"[.?!](?:\s|$)")
#: Letters and marks only Spanish writes, of the two.
_SPANISH_MARKS = re.compile(r"[¿¡ñáéíóú]", re.IGNORECASE)
_LETTERS = re.compile(r"[\wáéíóúüñ']+")
#: A cue is the site's own words, in English whatever he speaks.
_CUE_TEXT = re.compile(r"\{[^{}]*\}?")


def language_of(text: str, *, sure: bool = True) -> Lang | None:
    """The language ``text`` is plainly in, or ``None``.

    ``sure`` is for what the visitor said, where one stray word must not move
    the call: Spanish needs two of its words (or its marks and one), English
    three of its own and none of Spanish's. Unsure is for the first words of his
    own reply, which are few: one Spanish word, or two English ones, will do."""
    text = _CUE_TEXT.sub(" ", text)
    words = set(_LETTERS.findall(text.lower()))
    es = len(words & _SPANISH_WORDS) + (1 if _SPANISH_MARKS.search(text) else 0)
    en = len(words & _ENGLISH_WORDS)
    if es >= (2 if sure else 1) and es > en:
        return "es"
    if en >= (3 if sure else 2) and es == 0:
        return "en"
    return None


#: "Vídeo" is Spain's spelling, and the voice reads it with Spain's stress.
_VIDEO_ES = re.compile(r"\b([Vv])ídeo(s?)\b")


def latin_american(text: str) -> str:
    """``text`` as Latin America spells what the voice reads."""
    return _VIDEO_ES.sub(r"\1ideo\2", text)


def _chosen_note(language: Lang, how: str) -> str:
    name = LANGUAGE_NAMES[language]
    return (
        f"[The visitor chose {name} {how}. Answer in {name} from now on, whatever "
        "language they speak to you, until they ask for the other one.]"
    )


# ─── Actions (brain → page) ────────────────────────────────────────────────────


class Navigate(Action):
    """Open one of www.explora.com's pages in the tab in front, once his voice
    is quiet: a full page load. With ``heading``, ``text`` or ``faq``, that is
    shown once the page is up. The page reports ``page_changed``."""

    path: str
    after_words: int = 0
    """Words of his this turn still to be heard before the page may go: the
    page waits for them to start and then for the voice to stop."""
    heading: str | None = None
    text: str | None = None
    faq: str | None = None


class Cue(Action):
    """A move on the page in front for when the voice reaches ``at`` — the first
    words of the sentence it belongs to (see :mod:`.cues`); empty ``at`` is when
    the voice stops. A heading, an in-page tab or accordion by its label, words
    to ring, or an accordion question to open."""

    at: str
    word: int = 0
    """Words of the unit before it, for a page that times cues by the clock."""
    heading: str | None = None
    text: str | None = None
    faq: str | None = None


class ShowSection(Action):
    """On the tab in front, scroll to the heading named ``heading`` (or open the
    tab or accordion with that label) and ring it; with ``text``, ring the
    smallest element containing that text."""

    heading: str | None = None
    text: str | None = None


class OpenFaq(Action):
    """Open the accordion whose question starts with ``question``, and ring it."""

    question: str


class CheckAvailability(Action):
    """On reservations.explora.com, choose the lodge ``hotel_code`` and, with
    them, the arrival ``date`` (``YYYY-MM-DD``) and ``nights``. With ``rooms``,
    press Continue to its rooms and rates. Never past them. The page reports
    ``stay_state``."""

    hotel_code: str
    date: str | None = None
    month: str | None = None
    """``YYYY-MM``: with no date, the month the calendar turns to, whose open
    days it reports."""
    nights: int | None = None
    rooms: bool = False
    language: Literal["EN", "ES"] = "EN"
    """The booking site's language for the pages it opens: the call's."""


class FillEnquiry(Action):
    """On reservations.explora.com, open the enquiry form of the expedition
    ``expedition_code`` and fill in the fields given. What is filled stays. The
    page reports ``enquiry_state``."""

    expedition_code: str
    title: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    country: str | None = None
    """The nationality as the form's list names it ("Mexico"): its codes
    repeat (``AL`` is both Albania and the DR Congo), its names do not."""
    message: str | None = None
    language: Literal["EN", "ES"] = "EN"
    """The booking site's language for the pages it opens: the call's."""


class SendEnquiry(Action):
    """Press Send Message on the filled enquiry form, once its reCAPTCHA is ticked."""


class FocusTab(Action):
    """Bring one of the visitor's Explora tabs to the front."""

    tab_id: str


class LanguageChanged(Action):
    """The call's language moved, by the toggle, by voice or by
    ``set_language``: the widget's toggle follows at once."""

    language: Literal["en", "es"]


# ─── Tool requests ─────────────────────────────────────────────────────────────

if TYPE_CHECKING:
    TopicId = str
    HotelCode = str
    ExpeditionCode = str
else:
    # The L2 files present at import, as the tool's enum; see knowledge.TOPIC_IDS.
    TopicId = Literal[TOPIC_IDS]
    HotelCode = Literal[
        tuple(h.code for h in kb.KNOWLEDGE.hotels if h.flow != "enquiry") or ("EATA",)
    ]
    ExpeditionCode = Literal[
        tuple(h.code for h in kb.KNOWLEDGE.hotels if h.flow == "enquiry") or ("XICE",)
    ]


class TopicRequest(BaseModel):
    topic: TopicId = Field(description="The topic to read, by its name.")


class SearchRequest(BaseModel):
    query: str = Field(
        description="A few words to look for on explora.com, e.g. 'horseback riding "
        "Atacama', 'altitude', 'airport transfer Torres del Paine', 'honeymoon'."
    )


class AvailabilityRequest(BaseModel):
    """Only what the visitor said: leave out anything they did not."""

    hotel_code: HotelCode = Field(
        description="The lodge or Travesia, by its booking code (from the lodges list)."
    )
    date: str | None = Field(
        default=None,
        description="Arrival day as YYYY-MM-DD, one the calendar lists as open; only once "
        "the visitor has picked it.",
    )
    month: str | None = Field(
        default=None,
        description="YYYY-MM, when they named a month but no day: the calendar turns to it "
        "and its open days come back to you.",
    )
    nights: int | None = Field(
        default=None, description="Nights, one the page offers; only if they said."
    )
    show_rooms: bool = Field(
        default=False,
        description="Go on to the rooms and rates for that stay. Only when the visitor "
        "agrees to see them.",
    )


class EnquiryRequest(BaseModel):
    """Only what the visitor said: leave out anything they did not."""

    expedition_code: ExpeditionCode = Field(description="The expedition, by its code.")
    title: Literal["Mr.", "Ms."] | None = Field(default=None, description="Only if clear.")
    first_name: str | None = Field(default=None)
    last_name: str | None = Field(default=None)
    email: str | None = Field(default=None, description="As they spelled it.")
    phone: str | None = Field(default=None, description="With country code, digits only.")
    nationality: str | None = Field(
        default=None, description="Their nationality, as a country name, e.g. 'Mexico'."
    )
    message: str | None = Field(
        default=None,
        description="Two or three sentences for Explora's team, from what they told you: "
        "who is travelling, when, and what they want from the expedition.",
    )


class TabRequest(BaseModel):
    tab_id: str = Field(description="The tab_id from the open tabs list.")


class LanguageRequest(BaseModel):
    language: Lang = Field(description="'en' for English, 'es' for Spanish.")


# ─── The prompt ────────────────────────────────────────────────────────────────

_SITE_MAP_CHARS = 26000
_SECTIONS_PER_PAGE = 12
#: The order pages are listed in the prompt's site map, most visited first.
_KIND_ORDER = (
    "home",
    "destination",
    "lodge",
    "expedition",
    "experience",
    "offer",
    "about",
    "post",
    "other",
)
_TITLE_SUFFIXES = (" | Explora", " - Explora Hotels", " - Explora", " | Official Site")
#: Headings that are on every page, and say nothing about it.
_EVERYWHERE = frozenset({"special offers", "unique programs", "discover our destinations"})


def _short_title(title: str) -> str:
    for suffix in _TITLE_SUFFIXES:
        title = title.removesuffix(suffix)
    return title.split(" | ")[0].strip()


def _useful_headings(page: kb.Page) -> list[str]:
    """A page's headings for the site map: short ones, not the footer's."""
    return [
        h
        for h in page.headings
        if len(h) <= 90 and norm(h) not in _EVERYWHERE and not h.startswith("[")
    ]


def _site_map(k: Knowledge) -> str:
    lines: list[str] = []
    size = 0
    order = {kind: i for i, kind in enumerate(_KIND_ORDER)}
    for p in sorted(k.pages.values(), key=lambda p: (order.get(p.kind, 99), p.path)):
        heads = "; ".join(_useful_headings(p)[:_SECTIONS_PER_PAGE])
        line = f"- {site_path(p.path)} ({p.kind}) — {_short_title(p.title)}" + (
            f" (sections: {heads})" if heads else ""
        )
        size += len(line) + 1
        if size > _SITE_MAP_CHARS:
            break
        lines.append(line)
    return "\n".join(lines) or "(The site map is not loaded: find pages with search_site.)"


def _topics(k: Knowledge) -> str:
    return "\n".join(f"- {t.id}: {t.title}" for t in k.topics.values()) or "(none loaded)"


def _hotels(k: Knowledge) -> str:
    return (
        "\n".join(
            f"- {h.code}: {h.label}"
            + (" (expedition: enquiry form)" if h.flow == "enquiry" else "")
            + (f" ({h.group})" if h.group.startswith("New") else "")
            for h in k.hotels
        )
        or "(The booking site's list is not loaded.)"
    )


def _prompt(k: Knowledge) -> str:
    return f"""You are {AGENT_NAME}, the guide on Explora's website, explora.com, and its booking site, reservations.explora.com. Explora runs all-inclusive lodges in the most remote places of South America — Patagonia, the Atacama Desert and Uyuni, the Sacred Valley of the Incas, Easter Island — and small-group expeditions, from Iceland to Tierra del Fuego. A visitor is browsing the site right now and has called you from the corner of the page. You can see and move their screen: you open pages, scroll to the exact section you are talking about and ring it, open the site's tabs and accordions, check a lodge's availability with them on the booking site, and fill in and send an expedition's enquiry for them. You are warm, calm and vivid — a seasoned Explora travel advisor who has been to every lodge, paints a place in a few words, relates it to how this visitor likes to travel, and keeps the conversation moving towards their trip.

# You narrate, and the screen follows your words
You are giving a guided tour of the site, like an advisor sitting beside the visitor with their screen between you. As you talk about something, it is on their screen, ringed, at that moment.
- Put a screen cue in your reply at the start of the sentence it belongs to. The page moves when your voice reaches that sentence. The visitor never hears a cue.
  - {{page: /path/}} opens another page of the site. Every page of explora.com is a full page load: it takes a few seconds, and the visitor hears nothing while it opens. So a page cue goes at the very start of your reply, never in the middle, at most one per reply, and only when the visitor needs to see another page. Talk about the page you are on whenever it has the answer.
  - {{show: Heading}} scrolls to a heading on the page they are on, or are taken to by a page cue, and rings it. Use the heading exactly as the site pages list or the screen lines spell it. With the label of one of the page's tabs or accordions ("Patagonia [Argentina + Chile]"), it opens it. With words that are not a heading, it rings those words: a room, an exploration, a lodge's name.
  - {{faq: Question}} opens that question's accordion on the page and rings it.
- One cue per sentence at most, and only where the screen should change. A cue goes before the sentence, never inside it.
- A page cue opens a page at its top. After it, every sentence about a part of the page brings its own show cue, with that section's heading: the lodge, what's included, the rooms, the explorations, the food.
- EVERY ANSWER ABOUT EXPLORA STARTS WITH A CUE: a show cue on the page they are on, or a page cue when the answer is on another page. A reply without a cue leaves their screen where it was while you describe something else.
- Cues are the only way you move the page. There is no tool for it.
- Example, on the Atacama lodge's page, for "what's it like?": "{{show: Welcome to Explora Atacama}} It's an oasis in the driest desert on earth. The lodge sits near San Pedro de Atacama. {{show: Included with Your Stay}} Everything is included: meals, drinks, the spa and every exploration. {{show: Embark on Desert Explorations}} There are nearly fifty guided explorations to choose from. {{show: Stargaze from Explora's Observatory}} And at night, the lodge has its own observatory. Shall I check the dates for you?"

# A good turn tells the next part of the story
1. Answer what they asked, first, in plain words, and show it as you say it.
2. Say why it matters for them, in a sentence, when you know something about them: who they travel with, what they love doing.
3. End by offering the next part of the story: one short, specific yes-or-no offer that leads somewhere related, so they only have to say "yes" or pick one. "Shall I show you the explorations?" "Would Patagonia or the desert suit you better?" "Want me to check dates for you?" Never an open question they have to think hard about, and never "anything else?".
- Explora's story runs in order. Follow it from wherever the visitor is: where in the world they want to go, the destination, the lodge that fits them, what is included, the rooms, the explorations, the food, how to get there and when to go, the offers, and then availability on the booking site, or an expedition's enquiry. A trip of several lodges is a journey: offer the lodges that combine.
- When they say yes, go there in that reply, with cues, and keep the story moving. When they pick something else, follow them.
- Ask about them only when the answer changes what you show next, and offer the choices: "Are you travelling as a couple, or with family?"

# How you sound
You are heard, not read, so keep it light and warm.
- A turn is three to five short sentences. A tour of a page can run to eight, one part per sentence, each with its cue.
- Every sentence under fifteen words. Small, everyday words. One idea per sentence. One number per sentence.
- THE FIRST SENTENCE IS A FEW WORDS. The visitor hears nothing until your first sentence has been voiced, so open every reply with a sentence of two to six words that ends in a full stop, with the answer in it. A cue may come before it.
- Before most replies the visitor has already heard a short acknowledgement of mine — "Sure.", "Let me see.", or in Spanish "Claro.", "Déjame ver." — so never open with one: your first word is the answer. No "great question", no repeating their question back.
- Spoken words only, apart from cues: no lists, no markdown, no symbols, never an exclamation mark. Write numbers, dates and prices as spoken words: "five nights", "the sixth of November", "eleven hundred dollars a night".
- Lines in square brackets come from their screen, not the visitor: the page in front with its headings, what the booking calendar shows, what the form holds. Never read them out; use them. Never write a line in square brackets yourself.
- Always answer. A reply with no words leaves the visitor in silence.

# English or Spanish
You speak English, and Spanish as a native of Latin America. The call starts in English unless the visitor chose Spanish.
- Answer in the language the visitor speaks to you. If they speak Spanish, answer in Spanish from that reply on; if they go back to English, so do you. Your voice follows the language you write.
- Except when they chose a language: a line in square brackets says so. Then answer in that language whatever they speak, until they ask you to switch.
- When they ask for the other language in words that are not already it ("Can you speak Spanish?", "¿Podemos hablar en inglés?"), answer in that language and call set_language in the same response. A visitor already speaking Spanish to you has been switched: do not call it for them.
- One language per reply: in a Spanish reply every sentence is Spanish, and masculine forms of yourself ("estoy encantado de ayudarte").
- Your Spanish is neutral Latin American Spanish, the kind understood from Mexico to Chile, never the Spanish of Spain.
  - Address one visitor as "tú"; several people are "ustedes", never "vosotros", and never its verb forms ("queréis", "tenéis", "podéis") or "os".
  - Use Latin American words: "computadora", never "ordenador"; "celular", never "móvil"; "mostrar" ("te muestro"), not "enseñar"; "completar un formulario", not "rellenar"; "¿Qué fecha te queda bien?", not "te viene bien"; "disculpa", not "perdona"; "está bien" or "perfecto", never "vale"; "tomar", never "coger"; "reservar" or "agendar".
  - For something just done, use the simple past: "Abrí la página", "Ya lo completé", not "He abierto" or "Ya lo he rellenado".
- In Spanish too, write numbers, dates and prices as spoken words. Lodge and place names stay as Explora writes them: Explora Atacama, Torres del Paine, El Chaltén.
- Cues are the site's own words, and the site is in English, so a cue stays in English inside a Spanish reply: "{{show: Included with Your Stay}} Todo está incluido: comidas, bebidas y exploraciones." Describe the English page in Spanish; if they ask, say the site itself is in English.

# Every response starts with words
Write your answer, with its cues, first; any tool call comes at the end of the same response. What a page call returns reaches you only on your next turn.
- The exception is a read: read_topic and search_site come straight back to you within this same turn, but each one makes the visitor wait. Answer from what you know below and the site pages list whenever they cover it. Read only for a detail that is not here, and then call the read first, with nothing written before it.
- Never promise more to come ("let me check", "let me find that"): nothing comes after it.

# What that sounds like
Visitor: "What is Explora?"
You: "{{page: /}}{{show: Uncover the World's Most Inspiring Destinations}} Lodges at the edge of the world. Explora has lodges in Chile, Peru, Argentina and Bolivia. {{show: What's Included in Your Stay}} Every stay is all-inclusive, explorations too. {{show: Our Destinations}} You pick a place, and guides take you into it each day. Would Patagonia or the desert suit you better?"
Visitor: "Patagonia."
You: "{{page: /patagonia-travel-argentina-chile/}} Patagonia it is. {{show: Discover the Largest Network of Lodges in Patagonia}} Explora has more lodges here than anywhere. {{show: OUR PATAGONIA LUXURY TRAVEL LODGES}} Torres del Paine is the classic, with the granite towers. {{show: EL CHALTÉN}} El Chaltén is for hikers, under Mount Fitz Roy. Do you love hiking, or something gentler?"
Visitor: "Can I go in mid November? Five nights."
You: "Let's look at the calendar. I've opened Torres del Paine on the booking site. It shows which days you can arrive." then check_availability with the lodge and the nights.

# What you know
- Every fact — a price, an altitude, an exploration, what is included, a transfer, a season — comes from the knowledge below, a topic you read, a search result, or what the screen reported. Never from memory. If you cannot find it, say so, and say where on the site it might be.
- Topics you can read with read_topic, when the knowledge below does not cover a question:
{_topics(k)}
- search_site finds a page, section or question by its words. Its results name the page and section, which you can then cue.
- Prices on the booking site change with the dates: the nights list a price a night per person, sharing a double room; the rooms list a price for the whole stay. Quote them only as the screen shows them, and say which it is.

# Moving the page
- Cue only a path from the site pages list below or a search result, and only headings the list or the screen gives. A lodge's page has its own sub-pages — the lodge itself, its explorations, travel tips, getting there, FAQs — listed in the screen lines as its links: open the one that answers them.
- The visitor can ask you to press or scroll to anything: "scroll to the rooms", "open that tab", "go back to the lodge", "show me Easter Island". Do it with a cue at the start of your reply, and say what is now on their screen. Never say you cannot scroll or click.

# Checking availability
- Offer it where the story reaches it — once a lodge fits them, or when they ask about dates, prices or booking — and not before.
- check_availability with the lodge opens it on the booking site, in this tab, with its calendar. When they named a month ("March", "next spring"), pass it as month. Say so in a short sentence in the same response — "I've opened the calendar for Atacama." — and name no day yet: you do not know the open days until the screen lists them. Never choose a day for them: the date is the one they picked from the days you offered. They come back to you: say two or three near what they asked, and ask which day suits them. When they pick a day, check_availability with that date: the nights the lodge offers that day come back, each with its price from per night. Read out the one they asked for, or the recommended stay and one other. Never a day or a number of nights the calendar has not listed. Then, when they want, check_availability with show_rooms to show the rooms and rates.
- On the rooms, the visitor chooses a room and goes on to book it themselves. Never press anything that books or pays, and never ask for card details.
- A Travesia (Atacama and Uyuni) books like a lodge. The two new lodges open in December twenty twenty-six.

# An expedition's enquiry
- Expeditions are not booked online: they have an enquiry form on the booking site, and Explora's team answers it. When the visitor wants one, fill_enquiry with the expedition: it opens the form. Then ask for what is still empty, one or two things at a time — their name, whether they are Mr. or Ms., email, phone with country code, nationality — and fill_enquiry with each as they say it. What is filled stays; you only add.
- Write the message yourself from what they told you: who is travelling, when, and what they hope for. Read the email back so they can check it: "I have ana at gmail dot com. Is that right?"
- When every field is filled, ask them to tick "I'm not a robot" below the form: only they can. When the screen says it is ticked, say you are sending it, and call send_enquiry in the same response. Never say it is sent until the page says so.

# Tabs
- The visitor may have several Explora tabs open. Lines in brackets tell you which tabs are open and which is in front. Your moves happen on the tab in front.
- "Go back to the other tab" is switch_tab with that tab's id.

# The booking site's lodges and expeditions
{_hotels(k)}

# Explora
{k.l1}

# Site pages
{_site_map(k)}
"""


# ─── Greeting ──────────────────────────────────────────────────────────────────

_INTRO: dict[Lang, str] = {
    "en": f"Hi, I'm {AGENT_NAME}, your guide to Explora.",
    "es": f"Hola, soy {AGENT_NAME}, tu guía de Explora.",
}
_GREETING: dict[Lang, str] = {
    "en": "I can show you our lodges and expeditions, or help you plan a trip. "
    "Where would you love to go?",
    "es": "Puedo mostrarte nuestros lodges y expediciones, o ayudarte a planear un viaje. "
    "¿A dónde te encantaría ir?",
}
#: The opener's second sentence for the page the call starts on, by a word in
#: its path; the first match wins, and anything else gets the plain greeting.
_OPENERS: tuple[tuple[str, dict[Lang, str]], ...] = (
    (
        "expedition",
        {
            "en": "Ask me about this expedition, or I can walk you through it.",
            "es": "Pregúntame por esta expedición, o te la muestro paso a paso.",
        },
    ),
    (
        "lodge",
        {
            "en": "I can walk you through this lodge, or check dates for you.",
            "es": "Puedo mostrarte este lodge, o revisar fechas contigo.",
        },
    ),
    (
        "destinations",
        {
            "en": "Tell me how you like to travel, and I'll show you the lodge that fits.",
            "es": "Cuéntame cómo te gusta viajar, y te muestro el lodge que encaja.",
        },
    ),
    (
        "offer",
        {
            "en": "Ask me about any of these offers, and I'll show you the details.",
            "es": "Pregúntame por cualquiera de estas ofertas, y te muestro los detalles.",
        },
    ),
)
_RESERVATIONS_GREETING: dict[Lang, str] = {
    "en": "Tell me where and when you'd like to go, and I'll check the dates with you.",
    "es": "Dime a dónde y cuándo te gustaría ir, y reviso las fechas contigo.",
}


def greeting(path: str | None, site: str | None, lang: Lang = OPENING) -> str:
    """The written opener, in ``lang``, tailored to the page the call starts on."""
    if site == "reservations":
        return f"{_INTRO[lang]} {_RESERVATIONS_GREETING[lang]}"
    here = canonical_path(path or "/")
    line = next((lines[lang] for word, lines in _OPENERS if word in here), _GREETING[lang])
    return f"{_INTRO[lang]} {line}"


# ─── Written lines for moves ───────────────────────────────────────────────────

#: His line for a silent turn, by what moved: "shown" for anything else.
_LANDED: dict[str, dict[Lang, str]] = {
    "shown": {"en": "Here it is.", "es": "Aquí lo tienes."},
    "stay": {
        "en": "Here's the booking calendar.",
        "es": "Aquí tienes el calendario de reservas.",
    },
    "rooms": {"en": "Here are the rooms and rates.", "es": "Aquí están las habitaciones."},
    "enquiry": {
        "en": "I've filled that in on the form.",
        "es": "Ya lo completé en el formulario.",
    },
    "sent": {"en": "I'm sending it now.", "es": "Lo estoy enviando."},
    "tab": {"en": "There's that tab.", "es": "Ahí tienes esa pestaña."},
}

# ─── His nod ───────────────────────────────────────────────────────────────────

_ACK_LINES: dict[Lang, dict[Kind, tuple[str, ...]]] = {
    "en": {
        "request": ("Sure.", "Okay.", "Of course.", "Certainly."),
        "question": ("Let me see.", "Hmm, let me see.", "Okay."),
        "correction": ("I see.", "Understood.", "Right."),
        "statement": ("Okay.", "Got it.", "Right."),
    },
    "es": {
        "request": ("Claro.", "Por supuesto.", "Perfecto.", "Con gusto."),
        "question": ("Déjame ver.", "A ver.", "Mmm, déjame ver."),
        "correction": ("Ya veo.", "Entendido.", "De acuerdo."),
        "statement": ("Muy bien.", "Entendido.", "Claro."),
    },
}
ACK_RATE = 0.75
ACK_HOLD_AFTER_S = 4.0
_ACK_HOLD: dict[Lang, tuple[str, ...]] = {
    "en": ("One moment.", "Just a moment."),
    "es": ("Un momento.", "Un momentito."),
}
_ACK_SORRY: dict[Lang, str] = {
    "en": "Sorry, that's taking a little longer.",
    "es": "Disculpa, está tardando un poco más.",
}
#: A visitor's ordinary words about Explora, so the reading trusts them.
_ACK_WORDS = Vocabulary(
    common=frozenset(
        # A word list reads as words, so it stays a split string.
        """explora lodge lodges hotel hotels patagonia atacama uyuni chalten calafate paine
        torres easter island rapa nui sacred valley machu picchu cusco peru chile bolivia
        argentina iceland fuego expedition expeditions exploration explorations hike hiking
        trek horseback rooms room suite nights night dates availability booking book price
        prices rates offer offers honeymoon family desert glacier stargazing spa
        """.split()  # noqa: SIM905
    ),
)


def _avatar_state(session: Session, state: Literal["WORKING"] | None) -> None:
    """The talking head's working latch: held until speech owed has played."""
    session.send_rtvi(RTVIType.SERVER_MESSAGE, {"type": "avatar", "cmd": "state", "state": state})


_HEADINGS_IN_NOTE = 40
_FAQS_IN_NOTE = 30
_TABS_IN_NOTE = 20
_LINKS_IN_NOTE = 16
_SEARCH_HITS = 6
_DAYS_IN_NOTE = 24
_ROOMS_IN_NOTE = 12


async def _silence() -> AsyncGenerator[Any, None]:
    for _ in ():
        yield


def _clip(items: list[str] | tuple[str, ...], most: int) -> str:
    more = f"; and {len(items) - most} more" if len(items) > most else ""
    return "; ".join(items[:most]) + more


def _match(want: str, options: list[str] | tuple[str, ...]) -> str | None:
    """The option ``want`` names: the same words, else the one it begins, else
    the one it is inside — how the page itself matches. Punctuation and accents
    do not count: "el chalten" is "EL CHALTÉN"."""

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


def _spoken_date(iso: str) -> str:
    """``2026-11-06`` → ``Friday, November 6, 2026``, for the model to read."""
    try:
        d = datetime.strptime(iso, "%Y-%m-%d")
    except ValueError:
        return iso
    return f"{d:%A}, {d:%B} {d.day}, {d.year}"


#: The page for what the visitor asked about, when his reply forgets to show
#: it: SendPotion's dev call 60e6c24b had him describe a page twice with the
#: screen left where it was. Matched on the visitor's own words, not on his
#: reply's. A page here costs a full page load, so it opens only when the tab is
#: not already on a page about the same place (``home``: fragments of its path).
_ASKED_PAGES: tuple[tuple[re.Pattern[str], str, tuple[str, ...]], ...] = tuple(
    (re.compile(rf"\b(?:{words})", re.IGNORECASE), path, home)
    for words, path, home in (
        (r"uyuni|travesia|salt flats?", "/lodge/atacama-uyuni-crossing/", ("uyuni",)),
        (r"atacama|san pedro|desert", "/lodge/atacama-lodge/", ("atacama", "puritama")),
        (r"easter island|rapa nui", "/lodge/easter-island-hotels/", ("easter-island",)),
        (
            r"sacred valley|machu picchu|cusco|urubamba",
            "/lodge/travel-machupicchu-and-the-sacred-valley-of-the-incas-peru-explora/",
            ("sacred-valley", "machu", "machupicchu"),
        ),
        (r"chalt[eé]n|fitz ?roy", "/el-chalten-lodge/", ("chalten",)),
        (r"calafate|perito moreno", "/lodge/el-calafate/", ("calafate",)),
        (
            r"patagonia national park|parque nacional patagonia",
            "/lodge/patagonia-national-park/",
            ("patagonia-national-park",),
        ),
        (r"torres del paine|paine", "/lodge/torres-del-paine-lodge/", ("torres-del-paine",)),
        (r"iceland", "/explora-expeditions/", ("iceland", "expedition")),
        (r"tierra del fuego", "/travel-tierra-del-fuego/", ("fuego",)),
        (r"sacred mountains?", "/sacred-mountain-expedition/", ("sacred-mountain",)),
        (r"expeditions?", "/explora-expeditions/", ("expedition", "iceland", "fuego")),
        (r"offers?|discount|deals?|promotion", "/offer/", ("offer",)),
        (r"patagonia", "/patagonia-travel-argentina-chile/", ("patagonia", "paine", "chalten")),
    )
)


def asked_page(text: str, here: str) -> str | None:
    """The site page for what ``text`` asks about, or ``None`` — never one about
    the place the tab at ``here`` already shows."""
    if asks_call_language(text):
        return None
    named = [(m.start(), path, home) for rx, path, home in _ASKED_PAGES if (m := rx.search(text))]
    if not named:
        return None
    _, path, home = min(named)
    return None if any(h in here for h in home) else path


# A request about the call's own language: a verb of speaking, addressed to him
# or said by him, and the language. SendPotion's dev call 1ff72fee: "Hey, can
# you speak in Spanish?" opened a page about languages while he switched.
_CALL_LANGUAGE = re.compile(
    r"\b(?:speak|talk|switch|change|continue|carry on|answer|reply|respond|go back|"
    r"habl\w*|cambi\w*|sig\w*|continu\w*|respond\w*|contest\w*|pas\w*|volv\w*)\b"
    r"[^.?!]{0,25}?\b(?:spanish|english|español|espanol|castellano|inglés|ingles)\b",
    re.IGNORECASE,
)
_TO_HIM = re.compile(
    r"^\W*(?:(?:hey|ok|okay|please|so|now|vale|oye|bueno|por favor)\W+)*"
    r"(?:speak|talk|switch|change|continue|carry|answer|reply|respond|go|habla|háblame|"
    r"hábleme|cambia|sigue|continúa|responde|contesta|pasa|vuelve)\b"
    r"|\b(?:you|we|us|let'?s|let us|i|i'?ll|puedes|podemos|podrías|podríamos|hablemos|"
    r"sigamos|cambiemos|continuemos|pasemos|volvamos|me|nos|hablamos|seguimos|cambiamos|"
    r"continuamos|pasamos|volvemos|puedo)\b",
    re.IGNORECASE,
)


def asks_call_language(text: str) -> bool:
    """Whether ``text`` asks him to speak another language."""
    return bool(_CALL_LANGUAGE.search(text) and _TO_HIM.search(text))


# ─── The section a sentence describes ──────────────────────────────────────────
#
# What he says, sentence by sentence, matched against the sections of the one
# page in front — never the whole site. A heading word counts for more than a
# word of the section's text, a word every section shares for little, and a
# sentence that is not clearly about one section moves nothing.

_STOP = frozenset(
    # A word list reads as words, so it stays a split string.
    """a an the and or but of to in on for with by at from as is are was were be been
    it its this that these those you your yours we our us they their them he she his
    her i me my can will just also so then than too very here there what which who how
    when where why all any each every more most some such no not only own same into out
    up down over under again once about after before both few other per via do does did
    have has had get gets got make makes made use uses used using explora lodge lodges
    like let lets want would shall could should see show shows one two three section
    page stay stays guest guests our also day days
    """.split()  # noqa: SIM905
)
#: How sure a match must be: its score, and its lead over the runner-up, as
#: SendPotion tuned them on its dev calls.
_SECTION_MIN = 6.0
_SECTION_LEAD = 1.5
_SECTION_MIN_WORDS = 4


def _stem(w: str) -> str:
    for suffix in ("ing", "ers", "er", "ed", "es", "s"):
        if len(w) > 4 and w.endswith(suffix):
            return w[: -len(suffix)]
    return w


def _terms(text: str) -> list[str]:
    return [
        _stem(w) for w in re.findall(r"[a-z0-9']+", norm(text)) if len(w) > 2 and w not in _STOP
    ]


def best_section(sentence: str, sections: list[tuple[str, str]]) -> str | None:
    """The heading of the one section ``sentence`` is about, of ``sections``
    (heading, text) on one page; ``None`` unless it is clearly one."""
    if sentence.rstrip().endswith("?"):
        return None  # The closing offer: about what comes next, not this page.
    said = " ".join(re.findall(r"[a-z0-9']+", norm(sentence)))
    quoted = [
        h
        for h, _ in sections
        if h
        and len(phrase := re.findall(r"[a-z0-9']+", norm(h))) >= 2
        and re.search(rf"\b{re.escape(' '.join(phrase))}\b", said)
    ]
    if quoted:
        return max(quoted, key=len)
    if len(sentence.split()) < _SECTION_MIN_WORDS:
        return None
    docs = [(h, set(_terms(h)), set(_terms(t))) for h, t in sections if h]
    if not docs:
        return None
    df: dict[str, int] = {}
    for _, head, text in docs:
        for w in head | text:
            df[w] = df.get(w, 0) + 1
    want = set(_terms(sentence))
    scored: list[tuple[float, str]] = []
    for heading, head, text in docs:
        score = 0.0
        for w in want:
            idf = math.log(1 + len(docs) / (1 + df.get(w, 0)))
            score += 2 * idf if w in head else 0.6 * idf if w in text else 0.0
        scored.append((score, heading))
    scored.sort(key=lambda s: -s[0])
    top, heading = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    return heading if top >= _SECTION_MIN and top - second >= _SECTION_LEAD else None


#: A ``{page: …}`` cue, as the model writes it, anywhere in a chunk.
_PAGE_CUE = re.compile(r"\{\s*page\s*:\s*([^{}]*?)\s*\}", re.IGNORECASE)


def _words_in(text: str) -> int:
    return len(re.findall(r"[\w']+", _CUE_TEXT.sub(" ", text)))


# ─── The brain ─────────────────────────────────────────────────────────────────


class ExploraBrain(GeminiBrain):
    """One per session. Javier: Explora's knowledge, its pages, its booking
    site, and a mirror of the visitor's tabs, in English or Spanish."""

    def __init__(
        self,
        *,
        client: genai.Client,
        model: str = MODEL,
        knowledge: Knowledge | None = None,
    ) -> None:
        self.kb = knowledge if knowledge is not None else kb.KNOWLEDGE
        super().__init__(client=client, system_instruction=_prompt(self.kb), model=model)
        self._config = self._config.model_copy(update={"thinking_config": THINKING})
        self._heard_at = float("-inf")
        #: The language he speaks now, whether the visitor chose it, and the
        #: toggle's written confirmation of a switch, said in his next turn.
        self.spoken: Lang = OPENING
        self._chosen = False
        self._confirm: str | None = None
        self._fallback = FallbackLine()
        self._ack = Acknowledger(
            _ACK_LINES, _ACK_HOLD, _ACK_SORRY, _ACK_WORDS, ACK_RATE, ACK_HOLD_AFTER_S
        )
        #: The tab in front as it last reported itself.
        self.page: PageChanged | None = None
        self._path = "/"
        self._site = "site"
        self._page_unseen = False
        #: Counts every page the tab in front reports, so a reply waiting on a
        #: page it opened knows when the next one is up.
        self._pages_seen = 0
        self._page_arrived = asyncio.Event()
        #: Every open Explora tab, and which is in front.
        self.tabs: list[TabInfo] = []
        self._active = ""
        self._tabs_unseen = False
        #: The booking site as it last reported itself.
        self.stay: StayState | None = None
        self.enquiry: EnquiryState | None = None
        self._enquiry_fields: dict[str, str] = {}
        self._enquiry_code: str | None = None
        self._talk: str | None = None
        #: The page this turn's cues are on: the one in front, then wherever a
        #: page cue took it. ``None`` on the booking site.
        self._cue_path: str | None = None
        self._idle_short = False
        self._nudges = 0
        #: The page for what the visitor last asked about, opened at the start
        #: of his reply if it has no cue of its own; see :func:`asked_page`.
        self._backstop: str | None = None
        #: This reply's moves so far: what was last rung, so a sentence on the
        #: same section does not ring it again.
        self._shown: str | None = None
        #: Whether this turn made a booking move (availability, the enquiry).
        self._booked = False

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        init = session.init or {}
        self._path = canonical_path(str(init.get("path") or "/"))
        self._site = "reservations" if init.get("site") == "reservations" else "site"
        # The page sends `lang` only once the visitor has pressed the toggle.
        chosen = init.get("lang")
        self._chosen = chosen in LANGUAGE_NAMES
        self.spoken = "es" if chosen == "es" else OPENING
        await session.configure(
            Config(
                stt=SttConfig(language=self.spoken, patience=EXPLORA_PATIENCE),
                tts=TtsConfig(voice=VOICE, language=self.spoken),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
            )
        )
        logger.info(
            "explora: session start on {} {} in {}{}",
            self._site,
            self._path,
            self.spoken,
            " (chosen)" if self._chosen else "",
        )
        today = datetime.now(UTC)
        self._note(f"[Today is {today:%A}, {today:%B} {today.day}, {today.year}.]")
        if self._chosen:
            self._note(_chosen_note(self.spoken, "before the call"))

    async def greet(self, session: Session) -> str:
        """The opener, written not generated."""
        return greeting(self._path, self._site, self.spoken)

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[Speech, None]:
        """A visitor who speaks the other language is answered in it from the
        first word, unless they chose the language they are in; the tab they
        moved to is read in with what they said; his nod covers the model's
        thinking."""
        heard = None if self._chosen else language_of(msg.text)
        if heard is not None and heard != self.spoken:
            await session.configure(self._speaking(heard))
            logger.info("explora: language -> {} (heard)", heard)
        self._talk = None
        self._nudges = 0
        # A reply cut off before it said a word keeps its page for the next one.
        self._backstop = (
            None
            if asks_call_language(msg.text)
            else asked_page(msg.text, self._path) or self._backstop
        )
        self._restore_idle()
        self._read_in_screen()
        now = time.monotonic()
        fragment, self._heard_at = now - self._heard_at < _FRAGMENT_S, now
        if not fragment and (nod := self._ack.line(msg.text, self.spoken)) is not None:
            logger.info("explora: ack {!r}", nod)
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
        """A quiet spell — the only floor he gets without the visitor speaking.

        A result the page produced after his turn (the calendar's open days, a
        ticked reCAPTCHA) is put in the context at once and the idle window
        shortened, so a quiet visitor hears it from him here. Otherwise an
        ordinary quiet spell: a nudge, twice, then silence."""
        self._restore_idle()
        self._backstop = None
        if self._talk is not None:
            ask, self._talk = self._talk, None
            self._note(ask)
            return self.respond(session)
        if self._confirm is not None:
            line, self._confirm = self._confirm, None
            return say_line(self, line)
        if self._nudges >= _IDLE_NUDGES:
            return _silence()
        self._nudges += 1
        self._read_in_screen()
        quiet = f"The visitor has said nothing for about {round(idle.idle_ms / 1000)} seconds."
        if self._nudges == 1:
            ask = (
                "Speak into the quiet, briefly, as the advisor beside them would: one vivid "
                "thing about what is on their screen, or one question that helps you plan "
                "their trip. Never ask whether they are still there, and never repeat your "
                "last line."
            )
        else:
            ask = (
                "Still quiet. One last, light offer, different from your last: something you "
                "could show them next, or checking dates for them. Then let them browse."
            )
        self._note(f"{quiet} {ask}")
        return self.respond(session)

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The model's turn, with its page moves paced to the page loads and its
        other cues taken out of the speech and sent to the page (:mod:`.cues`).

        If it moved the page and said nothing, the model is asked once more with
        tools off, so he talks about what he just showed; only if that is silent
        too does he say a written line of his own. A turn that came back with
        nothing at all is asked once more the same way.

        Except after a booking move: a model asked to talk about a calendar it
        has not seen yet made one up, open days and all, and read it out as a
        line in brackets. There the written line ("Here's the booking
        calendar.") is said instead, and the real days follow from the page."""
        if (line := self._confirm) is not None:
            self._confirm = None
            async for event in say_line(self, line):
                yield event
        self._cue_path = self._path if self._site == "site" else None
        self._shown = None
        self._booked = False
        spoke = False
        turn = self._unbracketed(
            self._fallback.speak_if_silent(
                self, super().respond(session), again=lambda: self._talk_again(session)
            )
        )
        async for event in self._spelled(self._written(session, self._cued(self._paced(turn)))):
            spoke = spoke or isinstance(event, SpeechStart)
            yield event
        if not spoke:
            logger.warning("explora: the model returned nothing; asking once more")
            again = self._written(session, self._cued(self._paced(self._talk_now(session))))
            async for event in self._spelled(again):
                yield event

    async def _paced(self, turn: AsyncGenerator[Speech, None]) -> AsyncGenerator[Speech, None]:
        """``turn``, split at each ``{page: …}`` cue, which costs a full page load.

        The words before the cue are spoken and their unit closed; the page is
        opened, once his voice is quiet (:class:`Navigate`); and the rest waits
        for the new page to report itself, so it is heard on it and its cues
        land there. A page that never comes holds the rest no longer than
        :data:`_PAGE_WAIT_S` past the words still being said."""
        buf = ""
        said = 0
        opened = False
        first = True
        try:
            async for event in turn:
                if isinstance(event, SpeechStart):
                    opened = True
                    yield event
                    continue
                if isinstance(event, SpeechEnd):
                    if buf:
                        yield SpeechChunk(buf)
                        said += _words_in(buf)
                        buf = ""
                    opened = False
                    yield event
                    continue
                if not isinstance(event, SpeechChunk):
                    yield event
                    continue
                text = event.text
                if first and text.strip():
                    first = False
                    text = self._with_backstop(text)
                buf += text
                while (m := _PAGE_CUE.search(buf)) is not None:
                    before, value, buf = buf[: m.start()], m.group(1), buf[m.end() :]
                    if before.strip():
                        yield SpeechChunk(before)
                        said += _words_in(before)
                    page = self.kb.page(value)
                    if page is None:
                        logger.info("explora: page cue {!r} names no page; dropped", value)
                        continue
                    if self._site == "site" and page.path == self._path:
                        continue  # Already there: a show cue after it does the rest.
                    # The words so far play out in their own unit, then the page goes.
                    if opened and said:
                        yield SpeechEnd()
                        opened = False
                    await self._open_page(page.path, said)
                    said = 0
                    if not opened:
                        yield SpeechStart()
                        opened = True
                # A cue may still be arriving: hold back an open brace's tail.
                cut = buf.rfind("{")
                if cut >= 0 and "}" not in buf[cut:] and len(buf) - cut <= MAX_CUE:
                    head, buf = buf[:cut], buf[cut:]
                else:
                    head, buf = buf, ""
                if head:
                    yield SpeechChunk(head)
                    said += _words_in(head)
            if buf:
                yield SpeechChunk(buf)
        finally:
            await turn.aclose()

    async def _open_page(self, path: str, words_before: int) -> None:
        """Open ``path`` on the tab in front and wait for it to report itself."""
        seen = self._pages_seen
        # The page being left may report itself again (late-rendering parts):
        # only a report of another page is the new one.
        leaving = self._path if self._site == "site" else None
        self._page_arrived.clear()
        logger.info("explora: opening {} after {} words", path, words_before)
        self.session.dispatch(Navigate(path=site_path(path), after_words=words_before))
        self._cue_path = path
        self._shown = None
        deadline = time.monotonic() + _PAGE_WAIT_S + words_before / _WORDS_PER_S
        while self._pages_seen == seen or (leaving is not None and self._path == leaving):
            left = deadline - time.monotonic()
            if left <= 0:
                logger.warning("explora: {} did not report itself in time", path)
                return
            try:
                await asyncio.wait_for(self._page_arrived.wait(), left)
            except TimeoutError:
                continue
            self._page_arrived.clear()
        self._cue_path = self._path if self._site == "site" else None
        logger.info("explora: {} is up", self._path)

    async def _written(
        self, session: Session, turn: AsyncGenerator[Speech, None]
    ) -> AsyncGenerator[Speech, None]:
        """``turn``, with each unit held back until its first sentence is in,
        and both legs moved to the language it is in when it is not the call's.
        A chunk can be a sliver (" P"), so one is never enough to tell."""
        held: list[Speech] = []
        text = ""

        async def release() -> AsyncGenerator[Speech, None]:
            nonlocal held, text
            written = language_of(text, sure=False)
            if written is not None and written != self.spoken:
                await session.configure(self._speaking(written))
                logger.info("explora: language -> {} (written)", written)
            out, held, text = held, [], ""
            for event in out:
                yield event

        async for event in turn:
            if isinstance(event, SpeechStart):
                held.append(event)
                continue
            if not held:
                yield event
                continue
            held.append(event)
            if isinstance(event, SpeechChunk):
                text += event.text
                if len(text) < _WRITTEN_ENOUGH and not _SENTENCE_END.search(text):
                    continue
            async for out in release():
                yield out
        if held:
            async for out in release():
                yield out

    def _spelled(self, turn: AsyncGenerator[Speech, None]) -> AsyncGenerator[Speech, None]:
        """``turn``, with Spanish speech spelled as Latin America says it."""

        async def spelled() -> AsyncGenerator[Speech, None]:
            async for event in turn:
                if isinstance(event, SpeechChunk) and self.spoken == "es":
                    event = SpeechChunk(latin_american(event.text))
                yield event

        return spelled()

    async def _cued(self, turn: AsyncGenerator[Speech, None]) -> AsyncGenerator[Speech, None]:
        """``turn`` with every ``{show|faq: …}`` taken out of its text and sent
        to the page as a :class:`Cue`, anchored to the words before it. Page
        cues were taken out before it, by :meth:`_paced`."""
        parser = CueParser(self._auto_cues)
        try:
            async for event in turn:
                if isinstance(event, SpeechStart):
                    parser = CueParser(self._auto_cues)
                elif isinstance(event, SpeechChunk):
                    text, raw = parser.feed(event.text)
                    for cue in raw:
                        self._send_cue(cue)
                    if text:
                        yield SpeechChunk(text)
                    continue
                else:  # SpeechEnd
                    rest, raw = parser.flush()
                    for cue in raw:
                        self._send_cue(cue)
                    if rest:
                        yield SpeechChunk(rest)
                yield event
        finally:
            await turn.aclose()

    def _with_backstop(self, chunk: str) -> str:
        """The reply's first words, with the page the visitor asked about cued
        in front of them when the reply brings no cue of its own."""
        if self._backstop is None or not chunk.strip():
            return chunk
        path, self._backstop = self._backstop, None
        if "{" in chunk or self._site != "site" or canonical_path(path) == self._path:
            return chunk
        logger.info("explora: the reply has no cue; showing {} first", path)
        return f"{{page: {path}}}{chunk}"

    def _send_cue(self, raw: RawCue) -> None:
        """Check a cue against the page, as the tools do, and send it; one that
        names nothing real is dropped and logged rather than reaching the page."""
        cue = self._resolve_cue(raw)
        logger.info("explora: cue {} {!r} at {!r} -> {}", raw.kind, raw.value, raw.at, cue)
        if cue is not None:
            if raw.kind == "show":
                self._shown = cue.heading or cue.text
            self.session.dispatch(cue)

    def _auto_cues(
        self, sentence: str, index: int, placed: tuple[tuple[CueKind, str], ...]
    ) -> list[tuple[CueKind, str]]:
        """The section a sentence of his describes and did not cue (see
        :mod:`.cues`): SendPotion's dev call 56e87ed1 had him describe four
        sections of a page with no cue at all."""
        if {k for k, _ in placed} & {"show", "faq", "page"}:
            return []
        shown = self._section_for(sentence)
        return [("show", shown)] if shown is not None and shown != self._shown else []

    def _section_for(self, sentence: str) -> str | None:
        """The heading on the page in front that ``sentence`` is about."""
        if self._cue_path is None:
            return None
        page = self.kb.page(self._cue_path)
        live = self._headings()
        sections = [(s.heading, s.text) for s in page.sections] if page else []
        if live:
            known = {h for h, _ in sections}
            sections += [(h, "") for h in live if h not in known]
        return best_section(sentence, sections)

    def _resolve_cue(self, raw: RawCue) -> Cue | None:
        if raw.kind == "page":
            return None  # Paced by _paced, never sent ahead.
        if raw.kind == "faq":
            question = _match(raw.value, self._faqs())
            if question is None:
                return None
            return Cue(at=raw.at, word=raw.word, faq=question)
        # show: a heading of the page in front, else a tab's label, else words.
        heading = _match(raw.value, self._headings()) or _match(raw.value, self._tab_labels())
        text = None if heading else raw.value[:120]
        return Cue(at=raw.at, word=raw.word, heading=heading, text=text)

    def _talk_now(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The one extra request a silent page move gets: tools declared, none callable."""
        return self.respond_with(session, tools=ToolChoice.NONE)

    def _talk_again(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The extra request, unless the silent move was a booking one: then
        nothing, and the written line for it is said."""
        return _silence() if self._booked else self._talk_now(session)

    async def _unbracketed(
        self, turn: AsyncGenerator[Speech, None]
    ) -> AsyncGenerator[Speech, None]:
        """``turn`` without anything in square brackets: those are the screen's
        lines to him, never his to say, and one he writes himself is made up."""
        inside = False
        try:
            async for event in turn:
                if isinstance(event, SpeechStart):
                    inside = False
                if not isinstance(event, SpeechChunk):
                    yield event
                    continue
                out = ""
                for ch in event.text:
                    if ch == "[":
                        inside = True
                    elif ch == "]" and inside:
                        inside = False
                    elif not inside:
                        out += ch
                if out:
                    yield SpeechChunk(out)
        finally:
            await turn.aclose()

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
            logger.info("explora: {} called with flat arguments; wrapping them", call.name)
            call = call.model_copy(update={"args": {"request": args}})
        return await super()._run(tool, call)

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Page→brain events, folded in silently: no floor taken, no turn."""
        event = EXPLORA_EVENTS.parse(msg)
        if event is None:
            return
        logger.info("explora: {} — {}", type(event).__voqal_event__, event)
        if isinstance(event, LanguageRequested):
            await self._requested(session, event)
            return
        if (note := self.apply_event(event)) is not None:
            self._note(note)

    async def _requested(self, session: Session, event: LanguageRequested) -> None:
        """The visitor pressed the other language on the toggle. Switched in
        code, not through the model: both legs move in one awaited request, and
        the written confirmation is said in his next turn."""
        if event.language == self.spoken:
            return
        was = self.spoken
        try:
            await session.configure(self._speaking(event.language))
        except RequestRejected as rejected:
            logger.warning("explora: switch to {} refused: {}", event.language, rejected)
            self.spoken = was
            session.dispatch(LanguageChanged(language=was))
            return
        logger.info("explora: language -> {} (toggle)", event.language)
        self._chosen = True
        self._confirm = TOGGLE_CONFIRM[event.language]
        if not self._idle_short:
            self._idle_short = True
            configure_soon(session, Config(idle=IdleConfig(timeout_ms=_TALK_THROUGH_MS)))
        self._note(_chosen_note(event.language, "on the toggle"))

    def _speaking(self, language: Lang) -> Config:
        """Both legs of ``language``, recorded as the one he speaks now, and the
        widget's toggle moved to it."""
        if language != self.spoken:
            self.session.dispatch(LanguageChanged(language=language))
        self.spoken = language
        return Config(
            stt=SttConfig(language=language, patience=EXPLORA_PATIENCE),
            tts=TtsConfig(voice=VOICE, language=language),
        )

    # ─── Page → brain ───────────────────────────────────────────────────

    def apply_event(self, event: ExploraEvent) -> str | None:
        """Patch the mirror; return the line the model should see."""
        match event:
            case PageChanged():
                self.page = event
                self._path = canonical_path(event.path)
                self._site = event.site
                self._page_unseen = True
                self._pages_seen += 1
                self._page_arrived.set()
                # Read in with their next message or quiet spell: they may click
                # on before they speak, and only the last page matters.
                return None
            case TabsChanged():
                self.tabs = event.tabs
                self._active = event.active
                self._tabs_unseen = True
                return None
            case StayState():
                return self._stay_changed(event)
            case EnquiryState():
                return self._enquiry_changed(event)
            case EnquirySent():
                who = "You pressed" if event.by == "javier" else "The visitor pressed"
                self._talk_through(
                    "The enquiry has just been sent. Thank them in one sentence, say Explora's "
                    "expedition team will write to them, and offer to keep answering questions."
                )
                return f"[{who} Send Message on the {event.expedition or 'expedition'} enquiry.]"
            case LanguageRequested():
                return None  # Switched by on_rtvi before it gets here.
            case CommandFailed() if event.command == "cue":
                return (
                    f"[A screen cue of yours did not land ({event.reason}). If the visitor "
                    "asks where it is, show it again; otherwise carry on.]"
                )
            case CommandFailed():
                if event.command in ("check_availability", "fill_enquiry", "send_enquiry"):
                    self._talk = None
                    self._restore_idle()
                return (
                    f"[That did not happen on the page ({event.command}: {event.reason}). "
                    "Tell the visitor plainly and offer what you can do instead; never say it "
                    "worked.]"
                )

    def _stay_changed(self, event: StayState) -> str | None:
        before = self.stay
        self.stay = event
        lodge = event.hotel or event.hotel_code
        if event.step == "rooms":
            rooms = _clip([f"{r.name} ({r.text})" if r.text else r.name for r in event.rooms], 12)
            if before is None or before.step != "rooms":
                self._talk_through(
                    "The rooms and rates are on their screen and they have not spoken. Name "
                    "two of the rooms with their price in one sentence each, and say they choose "
                    "a room and book it themselves from here."
                )
            return (
                f"[The booking site shows the rooms for {lodge}, arriving "
                f"{_spoken_date(event.date)} for {event.chosen_nights} nights: "
                f"{rooms or 'none listed'}. The visitor chooses and books a room themselves.]"
            )
        days = [_spoken_date(d) for d in event.open_days[:_DAYS_IN_NOTE]]
        note = f"[The booking calendar for {lodge} is open"
        note += f", showing {event.month}." if event.month else "."
        note += f" Open arrival days: {_clip(days, _DAYS_IN_NOTE)}." if days else " No open days."
        if event.date:
            nights = "; ".join(n.label or f"{n.nights} nights" for n in event.nights)
            note += f" Chosen arrival: {_spoken_date(event.date)}."
            note += f" Nights offered: {nights}." if nights else " No stay available that day."
            if event.chosen_nights:
                note += f" Selected: {event.chosen_nights} nights."
        note += "]"
        if before is None or before.hotel_code != event.hotel_code:
            self._talk_through(
                "The booking calendar is on their screen and they have not spoken. Name two "
                "or three open arrival days near what they asked, in one sentence, and ask which "
                "suits them."
            )
        elif event.date and (
            before.date != event.date or before.chosen_nights != event.chosen_nights
        ):
            self._talk_through(
                "The nights for their arrival day are on their screen. Say the price from per "
                "night for the stay they asked for, or the recommended one, and offer to show "
                "the rooms."
            )
        return note

    def _enquiry_changed(self, event: EnquiryState) -> str | None:
        before = self.enquiry
        self.enquiry = event
        filled = [k for k, v in event.filled.model_dump().items() if v]
        note = (
            f"[The {event.expedition or 'expedition'} enquiry form is on their screen. "
            f"Filled: {', '.join(filled) or 'nothing'}. Still empty: "
            f"{', '.join(event.missing) or 'nothing'}. "
            + (
                "They have ticked I'm not a robot.]"
                if event.captcha
                else "I'm not a robot is not ticked yet.]"
            )
        )
        if event.captcha and not event.missing and (before is None or not before.captcha):
            self._talk_through(
                "They have just ticked I'm not a robot, and the form is complete. Say in one "
                "sentence that you are sending it, and call send_enquiry."
            )
        elif before is None:
            self._talk_through(
                "The enquiry form is on their screen and they have not spoken. Say in one "
                "sentence what you need from them for it, starting with their name."
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
            self._note(f"[The visitor's open Explora tabs — {listed}.]")
        self._tabs_unseen = False
        if not self._page_unseen or self.page is None:
            return
        self._page_unseen = False
        p = self.page
        where = "the booking site" if p.site == "reservations" else "the site"
        note = f"[The tab in front shows {where}: “{p.title or p.path}” ({p.url or p.path})."
        if p.headings:
            note += f" Its headings: {_clip(p.headings, _HEADINGS_IN_NOTE)}."
        if p.tabs:
            note += f" Its tabs and accordions: {_clip(p.tabs, _TABS_IN_NOTE)}."
        if p.faqs:
            note += f" Its questions: {_clip(p.faqs, _FAQS_IN_NOTE)}."
        if p.links:
            note += f" Its own sub-pages: {_clip(p.links, _LINKS_IN_NOTE)}."
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

    def _move(self, action: Action, line: str = "shown") -> None:
        """Dispatch ``action``, with the written line for it (one of
        :data:`_LANDED`, in the language he speaks) should the turn say nothing."""
        self.session.dispatch(action)
        landed(_LANDED[line][self.spoken])

    def _site_language(self) -> Literal["EN", "ES"]:
        return "ES" if self.spoken == "es" else "EN"

    def _headings(self) -> tuple[str, ...]:
        if self.page is not None and canonical_path(self.page.path) == self._cue_path:
            return tuple(self.page.headings)
        page = self.kb.page(self._cue_path) if self._cue_path else None
        return page.headings if page else ()

    def _faqs(self) -> tuple[str, ...]:
        if self.page is not None and canonical_path(self.page.path) == self._cue_path:
            return tuple(self.page.faqs)
        page = self.kb.page(self._cue_path) if self._cue_path else None
        return tuple(f.q for f in page.faqs) if page else ()

    def _tab_labels(self) -> tuple[str, ...]:
        if self.page is not None and canonical_path(self.page.path) == self._cue_path:
            return tuple(self.page.tabs)
        page = self.kb.page(self._cue_path) if self._cue_path else None
        return page.tabs if page else ()

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        """Read and search Explora's knowledge, check availability, fill and
        send an expedition's enquiry, move between the visitor's tabs."""
        return [
            self.read_topic,
            self.search_site,
            self.check_availability,
            self.fill_enquiry,
            self.send_enquiry,
            self.switch_tab,
            self.set_language,
        ]

    @needs_result_now
    async def read_topic(self, request: TopicRequest) -> str:
        """Read one of Explora's knowledge topics before answering from it."""
        topic = self.kb.topics.get(request.topic)
        if topic is None:
            return f"No topic '{request.topic}' is written yet: use search_site."
        return topic.text

    @needs_result_now
    async def search_site(self, request: SearchRequest) -> str:
        """Search explora.com's pages, sections and questions. Each result names
        the page path and the section heading to take them to."""
        hits = self.kb.search(request.query, _SEARCH_HITS)
        if not hits:
            return f"Nothing on explora.com matches '{request.query}'."
        out: list[str] = []
        for h in hits:
            path = site_path(h.path) if h.path else ""
            if h.kind == "faq":
                out.append(f"[question on {path}] {h.title}\n  {h.snippet}")
            else:
                where = f", heading: {h.section}" if h.section else ""
                out.append(f"[page] {h.title} — path: {path}{where}\n  {h.snippet}")
        return "\n".join(out)

    async def check_availability(self, request: AvailabilityRequest) -> str:
        """Open a lodge's availability on reservations.explora.com, in this tab,
        or add to it: the arrival day they chose, the nights, and the rooms
        when they want them. The calendar's open days and the nights it offers
        come back to you from the page. It never books or pays."""
        hotel = self.kb.hotel(request.hotel_code)
        if hotel is None or hotel.flow == "enquiry":
            return (
                f"Not opened: '{request.hotel_code}' is not a lodge on the booking site. "
                "An expedition has an enquiry form: use fill_enquiry."
            )
        date = request.date
        stay = self.stay
        if (
            date
            and stay
            and stay.hotel_code == hotel.code
            and stay.open_days
            and date not in stay.open_days
            # The page lists the soonest days only: past them, the page judges.
            and date <= max(stay.open_days)
        ):
            near = _clip([_spoken_date(d) for d in stay.open_days[:6]], 6)
            return f"Not chosen: {date} is not an open arrival day. Open days include: {near}."
        rooms = request.show_rooms and bool(date or (self.stay and self.stay.date))
        self._booked = True
        self._move(
            CheckAvailability(
                hotel_code=hotel.code,
                date=date,
                month=request.month[:7] if request.month and not date else None,
                nights=request.nights,
                rooms=rooms,
                language=self._site_language(),
            ),
            "rooms" if rooms else "stay",
        )
        what = ", ".join(
            x
            for x in (
                f"arriving {_spoken_date(date)}" if date else "",
                f"{request.nights} nights" if request.nights else "",
                "going on to the rooms" if rooms else "",
            )
            if x
        )
        return f"The booking site is opening {hotel.label}" + (f", {what}" if what else "") + "."

    async def fill_enquiry(self, request: EnquiryRequest) -> str:
        """Open an expedition's enquiry form on reservations.explora.com, or add
        to it: the fields the visitor gave, and your message for Explora's
        team. What is filled stays. It never presses Send Message."""
        hotel = self.kb.hotel(request.expedition_code)
        if hotel is None or hotel.flow != "enquiry":
            return f"Not opened: '{request.expedition_code}' is not an expedition."
        if self._enquiry_code != hotel.code:
            self._enquiry_fields = {}
            self._enquiry_code = hotel.code
        unknown = ""
        given = request.model_dump(exclude={"expedition_code"})
        if nationality := given.pop("nationality", None):
            found = self.kb.country(nationality)
            if found is None:
                unknown = f" '{nationality}' is not on the form's nationality list: ask again."
            else:
                given["country"] = found[1]
        for key, value in given.items():
            if value:
                self._enquiry_fields[key] = str(value)
        fields = dict(self._enquiry_fields)
        self._booked = True
        self._move(
            FillEnquiry(expedition_code=hotel.code, language=self._site_language(), **fields),
            "enquiry",
        )
        listed = ", ".join(k for k in fields) or "nothing yet"
        return f"The {hotel.label} enquiry form is open; filled: {listed}.{unknown}"

    async def send_enquiry(self) -> str:
        """Press Send Message on the expedition's enquiry form. Only once every
        field is filled and the screen says the visitor ticked I'm not a robot."""
        state = self.enquiry
        if state is None:
            return "Not sent: no enquiry form is open. Use fill_enquiry first."
        if state.missing:
            return f"Not sent: still empty: {', '.join(state.missing)}."
        if not state.captcha:
            return "Not sent: I'm not a robot is not ticked yet. Ask the visitor to tick it."
        self._booked = True
        self._move(SendEnquiry(), "sent")
        return "Pressed Send Message; the page will say when it has gone."

    async def switch_tab(self, request: TabRequest) -> str:
        """Bring another of the visitor's Explora tabs to the front."""
        tab = next((t for t in self.tabs if t.tab_id == request.tab_id), None)
        if tab is None:
            listed = ", ".join(f"{t.tab_id} ({t.title})" for t in self.tabs) or "none"
            return f"Not switched: no tab '{request.tab_id}'. Open tabs: {listed}."
        self._move(FocusTab(tab_id=tab.tab_id), "tab")
        return f"Brought '{tab.title or tab.url}' to the front."

    async def set_language(self, request: LanguageRequest) -> str:
        """Conduct the rest of the call in English ('en') or Spanish ('es'),
        listening and speaking. Call it when they ask for the other language in
        words that are not already it — "Can you speak Spanish?" — and to go
        back. Say one short line in the language you are switching to, in the
        same response. A visitor already speaking Spanish has been switched: do
        not call it for them."""
        self._chosen = True
        configure_soon(self.session, self._speaking(request.language))
        logger.info("explora: language -> {} (asked)", request.language)
        return "ok"


__all__ = [
    "CheckAvailability",
    "Cue",
    "EnquiryFields",
    "ExploraBrain",
    "FillEnquiry",
    "FocusTab",
    "LanguageChanged",
    "Navigate",
    "OpenFaq",
    "SendEnquiry",
    "ShowSection",
]
