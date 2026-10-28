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
import math
import random
import re
import time
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal, cast

from loguru import logger
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from voqalize_demos import (
    PATIENCE,
    FallbackLine,
    configure_soon,
    landed,
    needs_result_now,
    say_line,
)
from voqalize_demos.language_hold import HELD_NOTE, heard_language, holds_spanish, may_write_english

from voqalize.sdk import (
    Action,
    RequestRejected,
    RTVIMessage,
    Session,
    Speech,
    SpeechChunk,
    SpeechEnd,
    SpeechStart,
    UserIdle,
    UserMessage,
)
from voqalize.sdk.openai import OpenAIBrain
from voqalize.sdk.stage import (
    LANDING_FLOOR_MS,
    MAX_CUE,
    ArgValue,
    Landing,
    Move,
    MoveClass,
    Refused,
    Stage,
    StagePageEvents,
    landed_ask,
    match_label,
)
from voqalize.sdk.stage import wire as stage_wire
from voqalize.sdk.stage.cues import AutoCue
from voqalize.sdk.voice import ToolChoice
from voqalize.sdk.wire import Config, IdleConfig, SttConfig, TtsConfig, Voice

from . import knowledge as kb
from .app_events import (
    EXPLORA_EVENTS,
    EnquiryFields,
    EnquirySent,
    EnquiryState,
    ExploraEvent,
    LanguageRequested,
    NightsOption,
    PageChanged,
    StayState,
    TabInfo,
    TabsChanged,
    TwinLookup,
)
from .knowledge import TOPIC_IDS, Knowledge, canonical_path, norm, site_path
from .stage_gen import (
    CHECK_AVAILABILITY,
    CHOOSE_ROOM,
    FAQ,
    FILL_ENQUIRY,
    FOCUS_TAB,
    MOVES,
    NAVIGATE,
    PROMPT_LINES,
    SEND_ENQUIRY,
    TWIN,
)

AGENT_NAME = "Javier"

#: GPT-6.1 Terra at low reasoning, for cost: OpenAI caches every prompt over
#: 1,024 tokens, where Gemini 3.8 Flash cached nothing under about 16k, so most
#: of each turn's input is read from the cache.
MODEL = "gpt-6.1-terra"
REASONING = "low"

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
#: speaks first, one who is reading hears it from him. Three seconds, not
#: two: on prod call be1f5b9a, at a caller round trip of 400 ms, the visitor
#: spoke before any of three talk-throughs at two seconds had said a word.
_TALK_THROUGH_MS = 3_000
#: A visitor describing a trip pauses mid-sentence, as SendPotion's did.
EXPLORA_PATIENCE = PATIENCE + 2
#: How long the rest of a reply waits for the page a cue opened. Voqalize
#: holds a call through a page load for ten seconds; past this the page is not
#: coming.
_PAGE_WAIT_S = 9.0
#: How many sentences of a reply may stream after a page cue before the page
#: has reported itself: his voice carries on through the load, but never
#: describes much more than the page in front can show.
_AHEAD_SENTENCES = 2
#: How much of a reply's opening is read before the backstop decides whether
#: it brought a cue of its own: a chunk may be a sliver ("{show"), so the
#: first is never enough. A cue still open at this point is read to its end.
_LEAD_CHARS = 40
#: How long the rest of a reply waits for a page's Spanish twin, once the page
#: a cue opened came up in English in a Spanish call.
_TWIN_WAIT_S = 6.0

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
    lo le te ya ahora aquí ahí
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
#: A sentence about booking — the calendar, availability, dates, nights — is
#: never given a show cue by the backstop: on dev call 2f94965e it rang the
#: lodge's name under "I'm opening the Atacama calendar", a move never made,
#: and the ring made the claim look true.
_BOOKING_TALK = re.compile(
    r"\b(?:calendars?|availability|dates|nights|booking|book|calendario|disponibilidad"
    r"|fechas|noches|reserva|reservas|reservar)\b"
)
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


# ─── Moves (brain → page) ──────────────────────────────────────────────────────
#
# Everything he does on the screen is a Stage move (``voqalize.sdk.stage``): the
# page rings its target, makes it, and answers each one with a ``stage_result``.
# Show and faq are cues, written in his reply and made as the voice reaches
# them. A page cue is not a cue on Explora: every page is a full page load, so
# the brain splits his reply there and sends ``explora.navigate`` itself, once
# the words before it are said (:meth:`ExploraBrain._paced`). The rest are made
# by tools. Each move is declared once, in ``explora/scene.json``, and
# generated into ``stage_gen`` for the brain and ``scene.gen.ts`` for the page.

#: What each move did, for the line the model hears about it.
_ACTS: dict[str, str] = {
    NAVIGATE.id: "opening a page",
    TWIN.id: "loading the page in the call's language",
    CHECK_AVAILABILITY.id: "the booking site's availability",
    CHOOSE_ROOM.id: "choosing a room",
    FILL_ENQUIRY.id: "filling in the enquiry form",
    SEND_ENQUIRY.id: "sending the enquiry",
    FOCUS_TAB.id: "bringing a tab to the front",
}
#: The tool that makes each move a reply can claim, for the note that asks
#: him to keep the claim (:meth:`ExploraBrain.respond`).
_TOOL_OF: dict[str, str] = {
    CHECK_AVAILABILITY.id: "check_availability",
    CHOOSE_ROOM.id: "choose_room",
    FILL_ENQUIRY.id: "fill_enquiry",
}


def _said_it(phrase: str, sentence: str, lang: Lang) -> str:
    """What he said that he did not do, for the follow-up's note: "you were
    opening the calendar" for an English claim in the present participle, and
    otherwise the sentence itself, quoted ("I'll open the calendar.")."""
    claim = " ".join(phrase.replace("*", " ").split())
    if lang == "en" and claim.split()[0].endswith("ing"):
        return f"you were {claim}"
    return f"“{sentence}”"


#: The enquiry form's fields, as ``explora.fill_enquiry`` sends them.
_ENQUIRY_KEYS = ("title", "first_name", "last_name", "email", "phone", "country", "message")
#: The moves of the booking site: one that failed ends the talk-through.
_BOOKING_MOVES = frozenset({CHECK_AVAILABILITY.id, FILL_ENQUIRY.id, SEND_ENQUIRY.id})


class LanguageChanged(Action):
    """The call's language moved, by the toggle, by voice or by
    ``set_language``: the widget's toggle follows at once, and the tab keeps
    it for the rest of the call, on every page and both hosts."""

    language: Literal["en", "es"]
    site: Literal["follow", "stay"] = "follow"
    """What the page in front does: ``follow`` loads it in that language (its
    twin, else that language's home page); ``stay`` leaves it as it is (the
    call's start, on the page the visitor opened it on). Loading only the
    page's own twin is the ``explora.twin`` move."""


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
        default=None,
        description="The nights they said; the page picks the nearest it offers.",
    )
    show_rooms: bool = Field(
        default=False,
        description="Go on to the rooms and rates for that stay. Pass it, with the date and "
        "the nights, whenever the visitor asks for the rates, the prices or the rooms and "
        "the arrival day and the nights are known, or they give both in that same ask: "
        "never a nights step first. Otherwise only when the visitor agrees to see them.",
    )


class RoomRequest(BaseModel):
    room: str = Field(description="The room's name as the screen lists it, e.g. 'Suite'.")
    travellers: int | None = Field(
        default=None, description="How many people in this room (one or two), if they said."
    )
    bed: Literal["King", "Twin"] | None = Field(
        default=None,
        description="Bed type, only if the visitor said it in words and the room offers it. "
        "Never a guess.",
    )
    count: int = Field(
        default=1,
        description="How many rooms of this type to add, e.g. 2 for four travellers who want "
        "the same room. A room sleeps two.",
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
#: An index page (the home page, a destination, the lodges) lists more: its
#: real headings are what a reply that opens it cues, unseen.
_INDEX_SECTIONS = 30
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


def _opened(landing: Landing, event: PageChanged) -> bool:
    """Whether the page up is the one ``landing``'s navigate opened (its
    Spanish twin counts)."""
    want = (landing.args or {}).get("path")
    if not isinstance(want, str) or event.site != "site":
        return False

    def bare(path: str) -> str:
        return canonical_path(path).removeprefix("/es") or "/"

    return bare(event.path) == bare(want)


def _stay_fits(landing: Landing, event: StayState) -> bool:
    """Whether the booking site shows what ``landing``'s check asked for: its
    lodge, and the rooms when it asked for them, or its day."""
    args = landing.args or {}
    if args.get("hotel_code") not in (None, event.hotel_code):
        return False
    if args.get("rooms"):
        return event.step == "rooms"
    date = args.get("date")
    if isinstance(date, str) and date:
        return event.date == date and event.step == "dates"
    return event.step == "dates"


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
        items = listed_items(p)
        index = p.kind in ("home", "destination") or len(items) >= _LODGES_LISTED
        heads = "; ".join(_useful_headings(p)[: _INDEX_SECTIONS if index else _SECTIONS_PER_PAGE])
        line = (
            f"- {site_path(p.path)} ({p.kind}) — {_short_title(p.title)}"
            + (f" (sections: {heads})" if heads else "")
            + (f" (names it lists: {'; '.join(items)})" if items else "")
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


#: The show and faq cues, as the spec teaches them.
_CUE_LINES = "\n".join(f"  - {line}" for line in PROMPT_LINES)


def _prompt(k: Knowledge) -> str:
    return f"""You are {AGENT_NAME}, the guide on Explora's website, explora.com, and its booking site, reservations.explora.com. Explora runs all-inclusive lodges in the most remote places of South America — Patagonia, the Atacama Desert and Uyuni, the Sacred Valley of the Incas, Easter Island — and small-group expeditions, from Iceland to Tierra del Fuego. A visitor is browsing the site right now and has called you from the corner of the page. You can see and move their screen: you open pages, scroll to the exact section you are talking about and ring it, open the site's tabs and accordions, check a lodge's availability with them on the booking site, and fill in and send an expedition's enquiry for them. You are warm, calm and vivid — a seasoned Explora travel advisor who has been to every lodge, paints a place in a few words, relates it to how this visitor likes to travel, and keeps the conversation moving towards their trip.

# You narrate, and the screen follows your words
You are giving a guided tour of the site, like an advisor sitting beside the visitor with their screen between you. As you talk about something, it is on their screen, ringed, at that moment.
- Put a screen cue in your reply at the start of the sentence it belongs to. The page moves when your voice reaches that sentence. The visitor never hears a cue.
  - {{page: /path/}} opens another page of the site. Every page of explora.com is a full page load: it takes a few seconds, and your voice carries on while it opens. So a page cue goes at the very start of your reply, never in the middle, at most one per reply, and only when the visitor needs to see another page. Talk about the page you are on whenever it has the answer.
{_CUE_LINES}
- One cue per sentence at most, and only where the screen should change. A cue goes before the sentence, never inside it.
- A page cue opens a page at its top. After it, every sentence about a part of the page brings its own show cue, with that section's heading: the lodge, what's included, the rooms, the explorations, the food.
- After a page cue you have not seen the new page yet. Show only a heading the site pages list gives for that page under "sections", or a plain name the page shows as text — a lodge's name, a destination, a room — which it rings as words ("names it lists" gives them for a page of lodges). Never make up a heading for a page you have not seen.
- WHEN THE PAGE LISTS SEVERAL ITEMS — lodges, destinations, rooms, explorations, zones — NAME AND CUE EACH ONE: one short sentence per item, each with its own show cue. Never sum them up in one sentence ("These are Explora's lodges. They span four countries.") with the screen standing still.
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
- Your first word is the answer: no filler, no "great question", no repeating their question back.
- Spoken words only, apart from cues: no lists, no markdown, no symbols, never an exclamation mark. Write numbers, dates and prices as spoken words: "five nights", "the sixth of November", "eleven hundred dollars a night".
- Lines in square brackets come from their screen, not the visitor: the page in front with its headings, what the booking calendar shows, what the form holds. Never read them out; use them. Never write a line in square brackets yourself.
- Always answer, except with a booking step's call, which speaks for you. Any other reply with no words leaves the visitor in silence.

# English or Spanish
You speak English, and Spanish as a native of Latin America. The call starts in English unless the visitor chose Spanish.
- Answer in the language the visitor speaks to you. If they speak Spanish, answer in Spanish from that reply on. Once you speak Spanish, stay in Spanish until they say at least two full sentences in English in one turn, or ask for English: speech recognition often hears a short Spanish reply or a Chilean name as English ("See" for "sí", "And lower net here" for "Lo Barnechea"), and that visitor is still speaking Spanish. If they go back to English, so do you. Your voice follows the language you write.
- Except when they chose a language: a line in square brackets says so. Then answer in that language whatever they speak, until they ask you to switch.
- When they ask for the other language in words that are not already it ("Can you speak Spanish?", "¿Podemos hablar en inglés?"), answer in that language and call set_language in the same response. A visitor already speaking Spanish to you has been switched: do not call it for them.
- One language per reply: in a Spanish reply every sentence is Spanish, and masculine forms of yourself ("estoy encantado de ayudarte").
- Your Spanish is neutral Latin American Spanish, the kind understood from Mexico to Chile, never the Spanish of Spain.
  - Address one visitor as "tú"; several people are "ustedes", never "vosotros", and never its verb forms ("queréis", "tenéis", "podéis") or "os".
  - Use Latin American words: "computadora", never "ordenador"; "celular", never "móvil"; "mostrar" ("te muestro"), not "enseñar"; "completar un formulario", not "rellenar"; "¿Qué fecha te queda bien?", not "te viene bien"; "disculpa", not "perdona"; "está bien" or "perfecto", never "vale"; "tomar", never "coger"; "reservar" or "agendar".
  - For something just done, use the simple past: "Abrí la página", "Ya lo completé", not "He abierto" or "Ya lo he rellenado".
- In Spanish too, write numbers, dates and prices as spoken words. Lodge and place names stay as Explora writes them: Explora Atacama, Torres del Paine, El Chaltén.
- Cues are the site's own words. The site follows the call's language: in a Spanish call it shows Explora's Spanish pages (their paths start with /es/), and the screen lines give their Spanish headings. So a show cue names the heading exactly as the screen lines spell it, in whatever language the page is in: "{{show: Incluido en su estadía}} Todo está incluido." A page cue always names the path from the site pages list below, which is the English site: the page opens in the visitor's language by itself. If the screen lines show an English page in a Spanish call, it is being loaded in Spanish or has no Spanish version: never say you changed it.
- When the visitor says the page is in the wrong language, or asks to see it in Spanish or English, it reloads in the call's language by itself: say so in a few words ("Te la muestro en español.") and nothing more about it until the screen lines show it.

# Every response starts with words, except a booking step
Write your answer, with its cues, first; any other tool call comes at the end of the same response. A booking step is the exception: check_availability, choose_room, fill_enquiry and send_enquiry. For one, call its tool and write NO words in that response. The screen and a line of yours say what is happening; words written beside the call are heard before the screen moves, and words written without it are a promise the screen does not keep. So never say you are doing a booking step ("I'm opening the calendar", "I'm selecting three nights"): do it, with the call alone. What a page call returns reaches you only on your next turn.
- The exception is a read: read_topic and search_site come straight back to you within this same turn, but each one makes the visitor wait. Answer from what you know below and the site pages list whenever they cover it. Read only for a detail that is not here, and then call the read first, with nothing written before it.
- Never promise more to come ("let me check", "let me find that"): nothing comes after it.

# What that sounds like
Visitor: "What is Explora?"
You: "{{page: /}}{{show: Uncover the World's Most Inspiring Destinations}} Lodges at the edge of the world. Explora has lodges in Chile, Peru, Argentina and Bolivia. {{show: What's Included in Your Stay}} Every stay is all-inclusive, explorations too. {{show: Our Destinations}} You pick a place, and guides take you into it each day. Would Patagonia or the desert suit you better?"
Visitor: "Patagonia."
You: "{{page: /patagonia-travel-argentina-chile/}} Patagonia it is. {{show: Discover the Largest Network of Lodges in Patagonia}} Explora has more lodges here than anywhere. {{show: OUR PATAGONIA LUXURY TRAVEL LODGES}} Torres del Paine is the classic, with the granite towers. {{show: EL CHALTÉN}} El Chaltén is for hikers, under Mount Fitz Roy. Do you love hiking, or something gentler?"
Visitor, on the lodges page /lodge/: "Walk me through the lodges."
You: "{{show: El Calafate}} El Calafate sits on a quiet estancia, near the glaciers. {{show: El Chaltén}} El Chaltén is for hikers and trekkers. {{show: Torres del Paine}} Torres del Paine faces the granite peaks. {{show: Sacred Valley}} In Peru, the Sacred Valley lodge is among Inca villages. {{show: Atacama}} Atacama is an oasis in the driest desert. {{show: Easter Island}} And Easter Island is far out in the Pacific. Which one calls to you?"
Visitor: "Can I go in mid November? Five nights."
You: no words, only check_availability with the lodge, the month and the five nights. The screen opens the calendar and a line of yours says so; on your next turn you read out the open days it lists.

# What you know
- Every fact — a price, an altitude, an exploration, what is included, a transfer, a season — comes from the knowledge below, a topic you read, a search result, or what the screen reported. Never from memory. If you cannot find it, say so, and say where on the site it might be.
- Never state a rule, limit or restriction of the site or of booking — "one room per booking", "only by phone", a minimum stay — that is not in the knowledge below or on the screen. When a move of yours did not work, say plainly that it did not, then offer to try again, or the reservations contact from the knowledge.
- Name each exploration as the knowledge grades it: a hike is a hike, and only what it calls an ascent is an ascent.
- Topics you can read with read_topic, when the knowledge below does not cover a question:
{_topics(k)}
- search_site finds a page, section or question by its words. Its results name the page and section, which you can then cue.
- Prices on the booking site change with the dates: the nights list a price a night per person, sharing a double room; the rooms list a price for the whole stay. Quote them only as the screen shows them, and say which it is.

# Moving the page
- Cue only a path from the site pages list below or a search result, and only headings the list or the screen gives. A lodge's page has its own sub-pages — the lodge itself, its explorations, travel tips, getting there, FAQs — listed in the screen lines as its links: open the one that answers them.
- When you talk through several items on a page — zones, rooms, lodges, explorations, steps — cue each one as you name it, by the label the screen lines give it: a heading, a tab or a question. When the visitor asks you to scroll to each one as you talk, that is what they mean.
- The visitor can ask you to press or scroll to anything: "scroll to the rooms", "open that tab", "go back to the lodge", "show me Easter Island". Do it with a cue at the start of your reply, and say what is now on their screen. Never say you cannot scroll or click.
- Never say a page opened, changed or switched language, or that a room was added or a field filled, unless a screen line in square brackets or a tool's result says so. Saying you are doing a booking step ("I'm opening the calendar", "I'm filling in the form") is never yours to write: call its tool, with no words. A line saying a move did not happen means it did not: say so plainly.
- Some moves take a few seconds. While a move is still running (a line in square brackets says it is still working), never say you could not confirm it or that it failed: say you are still on it. Never say the site, the booking site or the page is slow: that blames Explora, whose site this is. If a line later says it happened after all, correct yourself in a few words.

# Checking availability
- Offer it where the story reaches it — once a lodge fits them, or when they ask about dates, prices or booking — and not before.
- check_availability with the lodge opens it on the booking site, in this tab, with its calendar. When they named a month ("March", "next spring"), pass it as month. When they said how many nights, pass them as nights, every time you call it: the page picks the nearest it offers. Never ask them to confirm the nights they already said, and never offer another number. Call it with no words in that response, and name no day yet: you do not know the open days until the screen lists them. Never choose a day for them: the date is the one they picked from the days you offered. They come back to you: say two or three near what they asked, and ask which day suits them. When they pick a day, check_availability with that date: the nights the lodge offers that day come back, each with its price from per night. Read out the nights they asked for; only when they said none, the recommended stay and one other. Nights the site selected by itself are the site's default, not their choice: never call them theirs. Never a day or a number of nights the calendar has not listed. Then, when they want, check_availability with show_rooms to show the rooms and rates.
- When they ask for the rates, the prices or the rooms and the arrival day and the nights are both known — or they give the day and the nights in that same ask — call check_availability with that date, those nights and show_rooms at once. Never a nights step first: the rooms list the prices for the whole stay.
- On the rooms, talk through two or three with their prices, cueing each as you name it. When they pick one, choose_room selects it, with their travellers if they said: the page shows its summary and the check-out button. Check-out, booking and payment are theirs to press: never press them, and never ask for card details.
- A room sleeps two. For three or more travellers they need one room per two travellers: say so, and when they pick, call choose_room once per room type they want, with count for how many rooms of that type (four travellers in the same type: count two). The site adds each room in turn.
- Pass bed only when the visitor said King or Twin in words. When a room needs a bed type, the page says so: ask them which.
- A Travesia (Atacama and Uyuni) books like a lodge. The two new lodges open in December twenty twenty-six.

# An expedition's enquiry
- Expeditions are not booked online: they have an enquiry form on the booking site, and Explora's team answers it. When the visitor wants one, fill_enquiry with the expedition: it opens the form. Then ask for what is still empty, one or two things at a time — their name, whether they are Mr. or Ms., email, phone with country code, nationality — and fill_enquiry with each as they say it. What is filled stays; you only add.
- Write the message yourself from what they told you: who is travelling, when, and what they hope for. Once the form shows the email, read it back so they can check it: "I have ana at gmail dot com. Is that right?"
- When every field is filled, ask them to tick "I'm not a robot" below the form: only they can. When the screen says it is ticked, call send_enquiry, with no words. Never say it is sent until the page says so.

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

#: His line for a silent turn, by what moved: "shown" for anything else. A
#: booking move's line is said as its call comes back, before the page has
#: done anything: it names nothing the page has not shown yet ("Here's the
#: booking calendar." was said over the old page), and the landing line says
#: what came up once it does.
_LANDED: dict[str, dict[Lang, str]] = {
    "shown": {"en": "Here it is.", "es": "Aquí lo tienes."},
    "stay": {"en": "Let me pull that up.", "es": "Te lo busco."},
    "stay_date": {"en": "Let me pick that day.", "es": "Elijo ese día."},
    "stay_nights": {"en": "Let me set that up.", "es": "Te lo ajusto."},
    "rooms": {"en": "Let me pull those up.", "es": "Te las busco."},
    "room": {"en": "Selecting that one now.", "es": "La selecciono ahora."},
    "enquiry": {"en": "Filling that in now.", "es": "Lo completo ahora."},
    "sent": {"en": "I'm sending it now.", "es": "Lo estoy enviando."},
    "tab": {"en": "There's that tab.", "es": "Ahí tienes esa pestaña."},
}

#: His line for a move still running after Stage's ``HOLDING_LINE_S``, by
#: move, said once in a quiet spell with no model request before it, so a move
#: still under way is not heard as a failed one; ``""`` is any other move. A
#: line says he is still on it and never blames the site ("the page is slow"
#: is heard as a fault of Explora's, whose site this is); one of a move's
#: lines is picked at random, so two in a call are not word for word alike.
_HOLDING: dict[str, dict[Lang, tuple[str, ...]]] = {
    CHECK_AVAILABILITY.id: {
        "en": (
            "Still opening the calendar for you, one moment.",
            "Almost there with the calendar.",
            "I'm still bringing up the dates.",
        ),
        "es": (
            "Sigo abriendo el calendario, un momento.",
            "Ya casi tengo el calendario.",
            "Sigo trayendo las fechas.",
        ),
    },
    CHOOSE_ROOM.id: {
        "en": ("Still choosing that room, one moment.", "Almost done with the room."),
        "es": ("Sigo eligiendo la habitación, un momento.", "Ya casi está la habitación."),
    },
    FILL_ENQUIRY.id: {
        "en": ("Still filling in the form, one moment.", "Almost done with the form."),
        "es": ("Sigo completando el formulario, un momento.", "Ya casi termino el formulario."),
    },
    SEND_ENQUIRY.id: {
        "en": ("Still sending it, one moment.", "Almost there, sending it now."),
        "es": ("Lo sigo enviando, un momento.", "Ya casi, lo estoy enviando."),
    },
    "": {
        "en": ("I'm still on it, one moment.", "Still working on it.", "Almost there."),
        "es": ("Sigo en eso, un momento.", "Sigo trabajando en eso.", "Ya casi."),
    },
}
#: How often the brain looks for a move slow enough for its holding line.
_HOLD_POLL_S = 0.5

#: His line when the page confirms, after all, a confirmed move he was told
#: was not confirmed: said in the next quiet spell, before the model.
_DONE_AFTER_ALL: dict[str, dict[Lang, str]] = {
    SEND_ENQUIRY.id: {
        "en": "Done after all, your enquiry is sent.",
        "es": "Al final sí, tu consulta quedó enviada.",
    },
}


def holding_line(move: str, lang: Lang, rng: random.Random | None = None) -> str:
    """His one line for a move still under way, picked at random among the
    move's lines."""
    return (rng or random).choice((_HOLDING.get(move) or _HOLDING[""])[lang])


#: What he says when a page he opened never came up, instead of the rest of a
#: reply about it: on prod call be1f5b9a he said "Here's the direct contact"
#: over the booking site, which had not moved. He is still on it; the page is
#: never blamed.
_PAGE_LATE: dict[Lang, tuple[str, ...]] = {
    "en": (
        "I haven't got that page up yet. Shall I try it again?",
        "That page isn't on your screen yet. Shall I open it again?",
    ),
    "es": (
        "Todavía no tengo esa página en pantalla. ¿La abro de nuevo?",
        "Esa página aún no aparece. ¿La intento abrir otra vez?",
    ),
}


def page_late_line(lang: Lang, rng: random.Random | None = None) -> str:
    return (rng or random).choice(_PAGE_LATE[lang])


def _month_said(label: str) -> str:
    """The calendar's month label without its year: "November 2026" → "November"."""
    return re.sub(r"[\s,]*\d{4}\s*$", "", label).strip()


def stay_landed_line(event: StayState, lodge: str, lang: Lang) -> str:
    """His line the moment the booking site shows what check_availability
    asked for: the calendar, the nights for a day, or the rooms. Said with no
    model request before it."""
    if event.step == "rooms":
        return (
            f"Here are the rooms at {lodge}."
            if lang == "en"
            else f"Aquí están las habitaciones de {lodge}."
        )
    if event.date:
        day = spoken_day(event.date, lang)
        return (
            f"Here are the stays arriving {day}."
            if lang == "en"
            else f"Aquí están las estadías llegando {day}."
        )
    month = _month_said(event.month)
    if lang == "en":
        return f"Here's the {lodge} calendar" + (f" for {month}." if month else ".")
    return f"Aquí está el calendario de {lodge}" + (f" para {month.lower()}." if month else ".")


def page_landed_line(event: PageChanged, lang: Lang) -> str:
    """His line the moment a page he opened, after his reply was over, is up."""
    title = _short_title(event.title) or ("the page" if lang == "en" else "la página")
    return f"Here's {title}." if lang == "en" else f"Aquí está {title}."


#: Spoken day numbers, for the written lines that read the calendar out. A
#: word list reads as words, so each stays a split string.
_ORDINALS_EN = """first second third fourth fifth sixth seventh eighth ninth tenth eleventh
twelfth thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth twentieth
twenty-first twenty-second twenty-third twenty-fourth twenty-fifth twenty-sixth twenty-seventh
twenty-eighth twenty-ninth thirtieth thirty-first""".split()  # noqa: SIM905
_DAYS_ES = """uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce
quince dieciséis diecisiete dieciocho diecinueve veinte veintiuno veintidós veintitrés
veinticuatro veinticinco veintiséis veintisiete veintiocho veintinueve treinta
treinta_y_uno""".split()  # noqa: SIM905
_MONTHS_ES = """enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre
diciembre""".split()  # noqa: SIM905
_WEEKDAYS_ES = "lunes martes miércoles jueves viernes sábado domingo".split()  # noqa: SIM905


def spoken_day(iso: str, lang: Lang) -> str:
    """``2026-11-06`` as he says it: "Friday the sixth of November", "el
    viernes seis de noviembre"."""
    try:
        d = datetime.strptime(iso, "%Y-%m-%d")
    except ValueError:
        return iso
    if lang == "es":
        day = _DAYS_ES[d.day - 1].replace("_", " ")
        return f"el {_WEEKDAYS_ES[d.weekday()]} {day} de {_MONTHS_ES[d.month - 1]}"
    return f"{d:%A} the {_ORDINALS_EN[d.day - 1]} of {d:%B}"


#: Nights said in words, English and Spanish.
_NIGHTS_EN = """one two three four five six seven eight nine ten eleven twelve thirteen
fourteen""".split()  # noqa: SIM905
_NIGHTS_ES = """una dos tres cuatro cinco seis siete ocho nueve diez once doce trece
catorce""".split()  # noqa: SIM905
_NIGHT_NUMBERS: dict[str, int] = {
    **{w: i for i, w in enumerate(_NIGHTS_EN, 1)},
    **{w: i for i, w in enumerate(_NIGHTS_ES, 1)},
    "un": 1,
    "uno": 1,
}
_NIGHTS_SAID = re.compile(r"\b(\d{1,2}|[a-z]+)\s+(?:nights?|noches?)\b")


def nights_said(text: str) -> int | None:
    """How many nights the visitor said they want ("three nights", "3 noches"),
    the last they said; ``None`` when they named none."""
    found = None
    for m in _NIGHTS_SAID.finditer(_fold(text)):
        word = m.group(1)
        n = int(word) if word.isdigit() else _NIGHT_NUMBERS.get(word)
        if n is not None and 0 < n <= 30:
            found = n
    return found


def days_line(days: list[str], lang: Lang) -> str:
    """The calendar's first open days, read out, and the question that follows."""
    said = [spoken_day(d, lang) for d in days[:3]]
    if not said:
        return (
            "No arrival days are open in that month. Shall I look at another?"
            if lang == "en"
            else "No hay días de llegada disponibles ese mes. ¿Busco en otro?"
        )
    if lang == "es":
        listed = said[0] if len(said) == 1 else f"{', '.join(said[:-1])} o {said[-1]}"
        return f"Puedes llegar {listed}. ¿Qué día te queda bien?"
    listed = said[0] if len(said) == 1 else f"{', '.join(said[:-1])} or {said[-1]}"
    return f"You can arrive on {listed}. Which day suits you?"


_PER_NIGHT = re.compile(r"([A-Z]{0,3}\$)\s*([\d.,]+)")


def nights_line(nights: list[NightsOption], chosen: int, lang: Lang) -> str:
    """The price from per night for the stay chosen, read out, and the offer of
    the rooms. The site writes "6 nights (from US$ 4,260 / night)"."""
    option = next((n for n in nights if n.nights == chosen), nights[0] if nights else None)
    m = _PER_NIGHT.search(option.label) if option else None
    price = int(re.sub(r"[^\d]", "", m.group(2)) or 0) if m else 0
    if option is None or not price:
        return (
            "The nights for that day are on your screen. Shall I show you the rooms?"
            if lang == "en"
            else "Ya tienes las noches para ese día en pantalla. ¿Te muestro las habitaciones?"
        )
    if lang == "es":
        return (
            f"Para {option.nights} noches, desde {price} dólares por noche y por persona. "
            "¿Te muestro las habitaciones?"
        )
    return (
        f"For {option.nights} nights, it's from {price} dollars a night per person. "
        "Shall I show you the rooms?"
    )


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


def _fold(s: str) -> str:
    """``s`` for matching: lower case, no accents, no punctuation."""
    return " ".join(re.sub(r"[^\w\s]", " ", norm(s)).split())


def _match(want: str, options: list[str] | tuple[str, ...]) -> str | None:
    """The option ``want`` names: the same words, else the one it begins, else
    the one it is inside — how the page itself matches. Punctuation and accents
    do not count: "el chalten" is "EL CHALTÉN"."""
    w = _fold(want)
    if not w:
        return None
    folded = [(_fold(o), o) for o in options]
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


#: A lodge's own sub-pages, by what the visitor asks for and the words their
#: paths use (they differ per lodge: /atacama-explorations/, /uyuni-tours/,
#: /gastronomy-in-atacama/, /how-to-get-el-chalten/). Found among the links
#: the page in front reports, so they open that lodge's page, not another's.
_SUB_PAGES: tuple[tuple[re.Pattern[str], re.Pattern[str]], ...] = tuple(
    (re.compile(rf"\b(?:{asked})", re.IGNORECASE), re.compile(path, re.IGNORECASE))
    for asked, path in (
        (
            r"explorations?|excursions?|tours?|activit|hik|exploraciones|excursiones",
            r"explorations|tours|excursion|hiking",
        ),
        (
            r"dining|food|cuisine|restaurant|wine|gastronom|comida|cocina",
            r"dining|cuisine|gastronom|cuisine",
        ),
        (
            r"getting there|get there|getting here|airport|transfers?|how to get|cómo llegar|como llegar",
            r"getting|how-to-get|get-there",
        ),
        (r"travel tips|tips|what to pack|packing|weather|climate|clima|consejos", r"tips|guied"),
        (r"rooms?|suites?|habitaci", r"lodge|hotel|where-to-stay"),
    )
)


def asked_sub_page(text: str, links: list[str], here: str) -> str | None:
    """The page in front's own sub-page for what ``text`` asks about ("show me
    the explorations" on a lodge page), or ``None``. On dev call ed9846d5 his
    whole reply to that was "One moment.", and nothing moved."""
    if asks_call_language(text):
        return None
    # The thing named last is the one wanted: "I'm still seeing the
    # explorations, not the rooms" asks for the rooms (dev call 1f6cd8ce).
    asked = sorted(
        ((m.start(), path) for rx, path in _SUB_PAGES for m in rx.finditer(text)),
        key=lambda hit: -hit[0],
    )
    for _, path in asked:
        # Not the page in front, nor the lodge's overview (every lodge
        # page links its own, and its path says "lodge" too).
        hit = next(
            (
                link
                for link in links
                if path.search(link)
                and canonical_path(link) != here
                and not canonical_path(link).startswith("/lodge/")
            ),
            None,
        )
        if hit is not None:
            return hit
    return None


#: All the lodges, when the visitor names no one place: "go back to the other
#: lodges" from the booking site did nothing on dev call 1f6cd8ce.
_ALL_LODGES = re.compile(
    r"\b(?:lodges|hotels|destinations|all (?:the |your )?(?:lodges|places)|"
    r"alojamientos|hoteles|destinos)\b",
    re.IGNORECASE,
)


#: The pages that list every lodge: "the lodges" asked for on one of them is
#: answered there. In a dev test on 2026-10-28 "the lodges" asked on /lodge/
#: sent the visitor to /destinations/, off the page whose country headings his
#: own cues named, and his {show: PERU} was refused.
_LODGE_INDEXES = frozenset({"/lodge", "/destinations", "/es/lodge", "/es/destinos"})


def asked_page(text: str, here: str, *, lists_lodges: bool = False) -> str | None:
    """The site page for what ``text`` asks about, or ``None`` — never one about
    the place the tab at ``here`` already shows, and never the lodges' index
    from a page that lists them all already (``lists_lodges``)."""
    if asks_call_language(text):
        return None
    named = [(m.start(), path, home) for rx, path, home in _ASKED_PAGES if (m := rx.search(text))]
    if not named:
        on_index = (
            lists_lodges
            or canonical_path(here) in _LODGE_INDEXES
            or "destinations" in here
            or "destinos" in here
        )
        if _ALL_LODGES.search(text) and not on_index:
            return "/destinations/"
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


# A remark about the page's own language: prod call be1f5b9a, "Me está
# mostrando la página en inglés. ¿Se la puedes mostrar en español, por favor?",
# which he answered "Ya la cambié a español." with nothing sent to the page.
_PAGE_WORDS = re.compile(
    r"\b(?:p[aá]gina|sitio|web|pantalla|page|site|website|screen)\b", re.IGNORECASE
)
_LANGUAGE_WORDS: dict[Lang, re.Pattern[str]] = {
    "es": re.compile(r"\b(?:espa[nñ]ol|castellano|spanish)\b", re.IGNORECASE),
    "en": re.compile(r"\b(?:ingl[eé]s|english)\b", re.IGNORECASE),
}


def asked_page_language(text: str, spoken: Lang, page: Lang | None) -> Lang | None:
    """The language ``text`` asks the page to be shown in, when that is the
    call's language and the page in front (in ``page``) is not in it: "show
    me the page in Spanish", "the page is in English". Asking for the page in
    the *other* language is a request about the call, and is the model's."""
    if page is None or page == spoken or not _PAGE_WORDS.search(text):
        return None
    named = {lang for lang, rx in _LANGUAGE_WORDS.items() if rx.search(text)}
    # The call's language named, or only the page's: a complaint about it.
    return spoken if spoken in named or named == {page} else None


#: The visitor asking for the rates, the prices or the rooms, in either language.
_RATES_ASK = re.compile(
    r"\b(?:rates?|prices?|pricing|rooms?|cost|tarifas?|precios?|habitaci[oó]n(?:es)?|"
    r"cu[aá]nto cuesta)\b",
    re.IGNORECASE,
)

#: A bed type said in words, in either language: the only way one is passed.
_BED_WORDS = re.compile(
    r"\b(?:king|queen|twins?|double|single|matrimonial|dos camas|camas? separadas|"
    r"cama grande|una cama|individual(?:es)?)\b",
    re.IGNORECASE,
)


def rooms_line(rooms: list[str], lang: Lang) -> str:
    """Two of the rooms on screen, named, and the question that follows."""
    named = rooms[:2]
    if lang == "es":
        listed = " y ".join(named) or "Las habitaciones"
        return f"{listed} están en tu pantalla, con sus precios. ¿Cuál te gusta?"
    listed = " and ".join(named) or "The rooms"
    return f"{listed} are on your screen, with their prices. Which one do you like?"


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


def _unnumbered(words: list[str]) -> list[str]:
    """A heading's words without its item number: "3. Altiplano" → "altiplano"."""
    return words[1:] if len(words) > 1 and words[0].isdigit() else words


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
        and (
            len(phrase := re.findall(r"[a-z0-9']+", norm(h))) >= 2
            # A numbered item's one word ("3. Altiplano") is a name too: on
            # dev call ed9846d5 he read zones three to five with no cue.
            or (len(phrase) == 2 and phrase[0].isdigit() and len(phrase[1]) >= 4)
        )
        and re.search(rf"\b{re.escape(' '.join(_unnumbered(phrase)))}\b", said)
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


def _name_words(label: str) -> list[str]:
    """A label's words as a sentence says them: no "[Argentina + Chile]", no
    item number ("3. Suni" → "suni")."""
    core = re.sub(r"\[[^\]]*\]|^\s*\d+\s*[.)]\s*", " ", label)
    return re.findall(r"[a-z0-9']+", norm(core))


def names_in(sentence: str, labels: list[tuple[str, bool]]) -> list[tuple[int, str]]:
    """Each label of ``labels`` (label, whether one word of it is a name)
    that ``sentence`` says outright, with the character it starts at, in
    spoken order. Where two overlap ("Torres del Paine" in "Torres del Paine
    C. Reserve") the longer wins; the first label given wins a tie, so put
    the page's own headings first. A question names nothing: it is the
    closing offer, about what comes next."""
    if sentence.rstrip().endswith("?"):
        return []
    # ``norm`` keeps every word where it was, one for one with the sentence's.
    said = re.findall(r"[a-z0-9']+", norm(sentence))
    starts = [m.start() for m in re.finditer(r"[^\W_]+(?:['\u2019][^\W_]+)*", sentence)]
    if len(starts) != len(said):
        starts = [0] * len(said)  # Words that do not line up: anchor at the start.
    hits: list[tuple[int, int, int, str]] = []  # (first word, -length, rank, label)
    seen: set[str] = set()
    for rank, (label, single) in enumerate(labels):
        words = _name_words(label)
        key = " ".join(words)
        if not words or key in seen or len(words) > 6:
            continue
        if len(words) == 1 and (not single or len(key) < 4 or key in _STOP):
            continue
        seen.add(key)
        for i in range(len(said) - len(words) + 1):
            if said[i : i + len(words)] == words:
                hits.append((i, -len(words), rank, label))
    taken: set[int] = set()
    out: list[tuple[int, str]] = []
    for i, neg, _, label in sorted(hits, key=lambda h: (h[1], h[0], h[2])):
        span = set(range(i, i - neg))
        if span & taken:
            continue
        taken |= span
        out.append((i, label))
    return [(starts[i] if i < len(starts) else 0, label) for i, label in sorted(out)]


#: The lodges a page of lodges names, from the crawl's own "Explore El
#: Chaltén >" links: names, not headings, which a show cue rings as words.
_EXPLORE_LINK = re.compile(r"Explore ([^>;]{3,60}?) >")


#: How many lodges a page names for it to be a page of the lodges.
_LODGES_LISTED = 5


def listed_items(page: kb.Page | None) -> list[str]:
    """The lodges and places ``page`` lists by name (its "Explore … >" links),
    in the page's order."""
    if page is None:
        return []
    found = (m.group(1).strip() for s in page.sections for m in _EXPLORE_LINK.finditer(s.text))
    return list(dict.fromkeys(found))


#: A ``{page: …}`` cue, as the model writes it, anywhere in a chunk.
_PAGE_CUE = re.compile(r"\{\s*page\s*:\s*([^{}]*?)\s*\}", re.IGNORECASE)


#: A holding line the model writes at the start of its own reply.
_HOLD_OPENER = re.compile(
    r"^\s*(?:just a moment|one moment(?: please)?|un momento|dame un momento)[.,]\s*",
    re.IGNORECASE,
)

#: What a reply that only promises more says: nothing comes after it.
_PROMISE = re.compile(
    r"\b(?:just |one |un )?(?:moment|momento|momentito|second|segundo)\b"
    r"|\blet me (?:see|check|look)(?: (?:that|into it|at that))?\b|\bdéjame ver\b|\ba ver\b",
    re.IGNORECASE,
)


#: What ends a sentence, for how far a reply has run ahead of its page.
_STOPS = (".", "?", "!", "…")


def _sentence_runs(text: str) -> list[str]:
    """``text`` cut after each sentence end outside a cue ("{show: Torres del
    Paine C. Reserve}" is not two sentences); the space after one goes with
    the next."""
    out: list[str] = []
    start = depth = 0
    for i, ch in enumerate(text):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
        elif depth == 0 and ch in ".?!…" and text[i + 1 : i + 2].isspace():
            out.append(text[start : i + 1])
            start = i + 1
    if start < len(text):
        out.append(text[start:])
    return out


# ─── The brain ─────────────────────────────────────────────────────────────────


class ExploraBrain(OpenAIBrain):
    """One per session. Javier: Explora's knowledge, its pages, its booking
    site, and a mirror of the visitor's tabs, in English or Spanish."""

    def __init__(
        self,
        *,
        client: AsyncOpenAI,
        model: str = MODEL,
        knowledge: Knowledge | None = None,
    ) -> None:
        self.kb = knowledge if knowledge is not None else kb.KNOWLEDGE
        super().__init__(
            client=client,
            system_instruction=_prompt(self.kb),
            model=model,
            reasoning=REASONING,
        )
        #: The language he speaks now, whether the visitor chose it, and the
        #: toggle's written confirmation of a switch, said in his next turn.
        self.spoken: Lang = OPENING
        self._chosen = False
        self._last_heard = ""
        self._confirm: str | None = None
        self._fallback = FallbackLine()
        #: The tab in front as it last reported itself.
        self.page: PageChanged | None = None
        self._path = "/"
        self._site = "site"
        self._page_unseen = False
        #: Counts every page the tab in front reports, so a reply waiting on a
        #: page it opened knows when the next one is up.
        self._pages_seen = 0
        self._page_arrived = asyncio.Event()
        #: Pages opened by replies that ended before the page was up.
        self._arrivals: set[asyncio.Task[bool]] = set()
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
        #: The short idle window set now (ms; 0: the long one).
        self._idle_short = 0
        self._nudges = 0
        #: The page for what the visitor last asked about, opened at the start
        #: of his reply if it has no cue of its own; see :func:`asked_page`.
        self._backstop: str | None = None
        #: This reply's moves so far: what was last rung, so a sentence on the
        #: same section does not ring it again.
        self._shown: str | None = None
        #: Whether this turn made a booking move (availability, the enquiry).
        self._booked = False
        #: The nights the visitor said they want, the last time they said it,
        #: filled in when the model leaves them out (dev call 2f94965e); and
        #: the arrival day they were last set for, so that is done once a day.
        self.stay_wanted: int | None = None
        self._nights_set_for: str | None = None
        #: The room last chosen, with its travellers, bed and count, and the
        #: model turn it was chosen in: only a repeat in the same turn is the
        #: same press. Rooms added on this stay's rooms, all told.
        self._room: tuple[str, int | None, str | None, int] | None = None
        self._room_turn = -1
        self._rooms_added = 0
        #: Counts model turns (each ``respond``).
        self._turn = 0
        #: What the visitor said lately, for what a tool may take as said.
        self._heard: list[str] = []
        #: The page in front said it has no twin in the call's language.
        self._twin_refused = False
        #: The page a reply opened answered that it did not open.
        self._page_failed = False
        #: A talk-through's written line, said if the model's turn says nothing.
        self._talk_fallback: str | None = None
        self._talk_line: str | None = None
        self._warming: asyncio.Task[None] | None = None
        #: Every move on the page goes through this director, which answers
        #: each with one result (:meth:`_staged`).
        self.stage = Stage(
            dispatch=lambda action: self.session.dispatch(action),
            moves=MOVES,
            resolve=self._resolve,
            backstop=self._auto_cues,
            on_landed=self._landing_line,
        )
        #: Replies under way: a page one of them opened is described by it,
        #: not by a landing line.
        self._replying = 0
        #: The move the site is slow on and his one line for it, said in the
        #: next quiet spell if it is still running then.
        self._hold: tuple[str, str] | None = None
        #: His written line for a confirmed move the page did after all.
        self._late_done: str | None = None
        #: Expiry on a timer, and the look for slow moves: one task a call.
        self._watching: asyncio.Task[None] | None = None

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        init = session.init or {}
        self._path = canonical_path(str(init.get("path") or "/"))
        self._site = "reservations" if init.get("site") == "reservations" else "site"
        # The page sends `lang` only once the visitor has pressed the toggle.
        chosen = init.get("lang")
        self._chosen = chosen in LANGUAGE_NAMES
        # A visitor reading the Spanish site is answered in Spanish, though
        # not held to it: what they speak still moves the call.
        site_es = init.get("site_lang") == "es" or self._path.startswith("/es/")
        self.spoken = "es" if chosen == "es" or (chosen is None and site_es) else OPENING
        await session.configure(
            Config(
                stt=SttConfig(language=self.spoken, patience=EXPLORA_PATIENCE),
                tts=TtsConfig(voice=VOICE, language=self.spoken),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
            )
        )
        # The tab keeps the call's language for the whole call, on every page
        # and both hosts. On prod call be1f5b9a a call that started on /es/
        # was never told, so the first English page made the tab think the
        # call was English, and every page after it opened in English.
        session.dispatch(LanguageChanged(language=self.spoken, site="stay"))
        logger.info(
            "explora: session start on {} {} in {}{}",
            self._site,
            self._path,
            self.spoken,
            " (chosen)" if self._chosen else "",
        )
        self._warm_cache()
        today = datetime.now(UTC)
        self._note(f"[Today is {today:%A}, {today:%B} {today.day}, {today.year}.]")
        if self._chosen:
            self._note(_chosen_note(self.spoken, "before the call"))
        self._watching = asyncio.create_task(self._watch_stage())

    async def on_session_end(self, session: Session) -> None:
        if self._watching is not None:
            self._watching.cancel()
            self._watching = None
        await super().on_session_end(session)

    async def _watch_stage(self) -> None:
        """For the whole call: a move the page never answered is said as
        unknown when its time is up, not at his next turn; and a confirmed or
        reversible move the site is slow on gets his one holding line."""

        async def slow() -> None:
            while True:
                await asyncio.sleep(_HOLD_POLL_S)
                self._hold_slow()

        await asyncio.gather(self.stage.watch(self._expired), slow())

    def _expired(self, result: stage_wire.StageResult) -> None:
        if (note := self._result_note(result)) is not None:
            self._note(note)

    def _hold_slow(self) -> None:
        """A move running past Stage's holding time: his written line for it,
        said in the next quiet spell — which only comes once neither he nor
        the visitor is speaking — if the move is still running then."""
        for run in self.stage.holding():
            line = holding_line(run.move.id, self.spoken)
            logger.info(
                "explora: {} {} still running at {:.1f} s ({}); holding line {!r}",
                run.call_ref,
                run.move.id,
                run.seconds,
                run.phase or "no phase",
                line,
            )
            self._hold = (run.call_ref, line)
            self._shorten_idle()

    def _take_hold(self) -> str | None:
        """The holding line waiting, if its move is still running."""
        hold, self._hold = self._hold, None
        if hold is None or all(r.call_ref != hold[0] for r in self.stage.running()):
            return None
        return hold[1]

    def _shorten_idle(self, ms: int = _TALK_THROUGH_MS) -> None:
        """The short quiet spell: the shortest asked for since the last one wins."""
        if not self._idle_short or ms < self._idle_short:
            self._idle_short = ms
            configure_soon(self.session, Config(idle=IdleConfig(timeout_ms=ms)))

    async def greet(self, session: Session) -> str:
        """The opener, written not generated."""
        return greeting(self._path, self._site, self.spoken)

    def _warm_cache(self) -> None:
        """Send the prompt once while the greeting plays, so the first answer
        finds it in the prompt cache. On prod call be1f5b9a the first answers
        read about seventeen thousand tokens with none cached, and took eight
        to ten seconds to a first word. The request is the turn's own — same
        instructions, same tools — so its cached prefix is the one the first
        answer opens with. Nothing waits on it, and a failure only costs the
        warm-up."""
        request = self._arguments(
            [self._new_user_turn("[The call is starting.]")], self._turn_request(None)
        )
        request.update(stream=False, max_output_tokens=16)

        async def warm() -> None:
            t0 = time.monotonic()
            try:
                got = await self._client.responses.create(**request)
            except Exception as error:  # The warm-up is best effort.
                logger.info("explora: the prompt cache warm-up failed: {}", error)
                return
            usage = getattr(got, "usage", None)
            details = getattr(usage, "input_tokens_details", None)
            logger.info(
                "explora: prompt sent ahead in {:.1f} s ({} tokens, {} cached)",
                time.monotonic() - t0,
                getattr(usage, "input_tokens", None),
                getattr(details, "cached_tokens", None),
            )

        self._warming = asyncio.create_task(warm())

    def _page_language(self) -> Lang | None:
        """The language of the www.explora.com page in front, by its path."""
        if self._site != "site":
            return None
        return "es" if self._path == "/es" or self._path.startswith("/es/") else "en"

    def _show_in(self, language: Lang) -> None:
        """Load the page in front's own twin in ``language``, once his voice is quiet."""
        logger.info("explora: the page in front is asked for in {}", language)
        self._send_move(TWIN.id, {"language": language}, when="quiet")
        name = LANGUAGE_NAMES[language]
        self._note(
            f"[The page in front is loading in {name} now. Say so in a few words, and never "
            f"say it has changed until the screen lines show the {name} page.]"
        )

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[Speech, None]:
        """A visitor who speaks the other language is answered in it from the
        first word, unless they chose the language they are in; the tab they
        moved to is read in with what they said. The runtime acknowledges them
        while the model thinks (``Config.ack``, on by default)."""
        self._last_heard = msg.text
        heard = None if self._chosen else heard_language(msg.text, self.spoken, language_of)
        if heard is not None and heard != self.spoken:
            await session.configure(self._speaking(heard))
            logger.info("explora: language -> {} (heard)", heard)
        if holds_spanish(msg.text, self.spoken, language_of):
            logger.info("explora: held in Spanish: {!r}", msg.text)
            self._note(HELD_NOTE)
        self._talk = None
        self._talk_fallback = None
        # They spoke first: what the page did is in the context as notes.
        self.stage.take_lines()
        self._hold = None
        self._late_done = None
        self._nudges = 0
        self._heard = [*self._heard[-7:], msg.text]
        if (nights := nights_said(msg.text)) is not None:
            self.stay_wanted = nights
        # "Show me the page in Spanish" is done in code, not left to a model
        # that said it was done and did nothing (prod call be1f5b9a).
        page_language = asked_page_language(msg.text, self.spoken, self._page_language())
        # A reply cut off before it said a word keeps its page for the next one.
        self._backstop = (
            None
            if asks_call_language(msg.text) or page_language is not None
            else asked_page(msg.text, self._path, lists_lodges=self._lists_lodges())
            or asked_sub_page(msg.text, self.page.links if self.page else [], self._path)
            or self._backstop
        )
        self._restore_idle()
        self._read_in_screen()
        if page_language is not None:
            self._show_in(page_language)
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
        done, self._late_done = self._late_done, None
        hold = self._take_hold()
        # What landed on screen: said first, written, the latest of it.
        landing = self.stage.take_lines()[-1:]
        first = " ".join(x for x in (done, *landing) if x) or None
        if self._talk is not None:
            ask, self._talk = self._talk, None
            self._talk_line, self._talk_fallback = self._talk_fallback, None
            if landing:
                ask = (
                    f'You have just said: "{landing[0]}". Never say that again. In one more '
                    f"sentence at most: {ask}"
                )
            self._note(ask)
            return self._line_then(first, self.respond(session))
        if landing:
            self._note(f"[{landed_ask(landing[0])}]")
            return self._line_then(first, self.respond(session))
        if done is not None:
            # A confirmed move he was told was not confirmed, done after all.
            return say_line(self, done)
        if self._confirm is not None:
            line, self._confirm = self._confirm, None
            return say_line(self, line)
        if hold is not None:
            # A move still under way: he is still on it, written, never asked
            # of the model, and no nudge counted.
            return say_line(self, hold)
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

    async def _line_then(
        self, line: str | None, turn: AsyncGenerator[Speech, None]
    ) -> AsyncGenerator[Speech, None]:
        """``line``, written, when there is one, then ``turn``."""
        try:
            if line is not None:
                async for event in say_line(self, line):
                    yield event
            async for event in turn:
                yield event
        finally:
            await turn.aclose()

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """:meth:`_respond`, counted while it runs (:attr:`_replying`)."""
        self._replying += 1
        turn = self._respond(session)
        try:
            async for event in turn:
                yield event
        finally:
            await turn.aclose()
            self._replying -= 1

    async def _respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The model's turn, with its page moves paced to the page loads and its
        other cues taken out of the speech and sent to the page (:mod:`.cues`).

        If it moved the page and said nothing, the model is asked once more with
        tools off, so he talks about what he just showed; only if that is silent
        too does he say a written line of his own. A turn that came back with
        nothing at all is asked once more the same way.

        Except after a booking move: a model asked to talk about a calendar it
        has not seen yet made one up, open days and all, and read it out as a
        line in brackets. There the written line ("Let me pull that up.") is
        said instead, and the real days follow from the page.

        A turn that said a move was happening ("I'm opening the calendar",
        "I'm selecting three nights") and never made it is asked once more,
        with that move's tool forced (:meth:`Stage.end_turn`; dev calls
        2f94965e and 453f2e19). The forced call comes back silent, so the
        silent-turn line says it, and the landing line follows the page."""
        if (line := self._confirm) is not None:
            self._confirm = None
            async for event in say_line(self, line):
                yield event
        self._turn += 1
        for expired in self.stage.expire():
            if (note := self._result_note(expired)) is not None:
                self._note(note)
        self._cue_path = self._path if self._site == "site" else None
        self._shown = None
        self._booked = False
        self.stage.begin_turn()
        talk_line, self._talk_line = self._talk_line, None
        said = ""
        turn = self._unbracketed(
            self._fallback.speak_if_silent(
                self, super().respond(session), again=lambda: self._talk_again(session)
            )
        )
        async for event in self._spelled(
            self._written(session, self.stage.cued(self._paced(turn)))
        ):
            # Words, not a unit: a reply that was only a dropped page cue
            # opened a unit and said nothing (dev call 0a304d89, turn 4).
            if isinstance(event, SpeechChunk):
                said += event.text
            yield event
        # After the turn's tool calls, which come at the end of its response.
        unkept = self.stage.end_turn()
        # Words, and not only a promise: on dev call ed9846d5 his whole reply
        # was "One moment.", and the visitor sat in silence.
        spoke = bool(_PROMISE.sub("", said).strip(" .,!?¡¿…"))
        if not spoke and talk_line is not None:
            # What the page put on screen, read out from it: on prod call
            # be1f5b9a the calendar's open days and prices were never said.
            logger.warning("explora: the talk-through said nothing; saying {!r}", talk_line)
            async for event in say_line(self, talk_line):
                yield event
        elif not spoke:
            logger.warning("explora: the model returned nothing; asking once more")
            again = self._written(session, self.stage.cued(self._paced(self._talk_now(session))))
            async for event in self._spelled(again):
                yield event
        elif unkept:
            # Once a turn: what the follow-up claims is only logged. The tool
            # is forced, not offered: on dev call 453f2e19 the model never
            # spoke and called in one response, so a follow-up that may
            # answer in words answers in words. Forced, it calls silently,
            # and the silent-turn line and the landing line speak for it.
            first = unkept[0]
            tool = _TOOL_OF.get(first.move.id)
            note = f"[You said {_said_it(first.phrase, first.sentence, self.spoken)} but did not do it. Do it now.]"
            self._note(note)
            choice = ToolChoice.only(tool) if tool is not None else ToolChoice.AUTO
            logger.info("explora: unkept {}; asking once more with {}", first.move.id, choice)
            forced = self._unbracketed(
                self._fallback.speak_if_silent(
                    self,
                    self.respond_with(session, tools=choice),
                    again=lambda: self._talk_again(session),
                )
            )
            again = self._written(session, self.stage.cued(self._paced(forced)))
            async for event in self._spelled(again):
                yield event
            self.stage.end_turn()

    async def _paced(self, turn: AsyncGenerator[Speech, None]) -> AsyncGenerator[Speech, None]:
        """``turn``, with its ``{page: …}`` cue taken out and the page opened.

        Every page is a full page load, and the extension keeps his voice
        playing across it, so the page goes at once (``after_words`` 0) and the
        reply streams on while it loads: the cues after it wait for the new page
        on the page's side. Only past :data:`_AHEAD_SENTENCES` sentences does
        the rest wait for the page to report itself, so he never describes more
        than a sentence or two ahead of the screen. A page that never comes
        holds the rest no longer than :data:`_PAGE_WAIT_S`, and is said plainly.

        Nothing is added for the load: in a dev test on 2026-10-28 a reply that
        opened with a page had his nod, then "Let me show you.", and only then
        the page, four to seven seconds from question to page."""
        buf = ""
        #: The reply's opening, read until the backstop can tell whether it
        #: brought a cue of its own (:meth:`_decided`); ``None`` once decided.
        lead = cast("str | None", "")
        #: The page this reply opened, on its way: whether it came up.
        arrival: asyncio.Task[bool] | None = None
        #: What has been said since the page cue, while the page is not up.
        ahead = 0
        #: A page this reply opened never came up: the rest of it, which is
        #: about that page, is not said, and its cues are not sent.
        late = False
        #: The page this reply has opened. One page a reply: on prod call
        #: 661f3df0 a reply opened the Atacama lodge and then, at once, the
        #: Atacama desert page, so the screen jumped past the page he was
        #: describing. A second page cue is dropped; its words are still said.
        moved: str | None = None

        def runs_of(chunk: str, *, final: bool) -> list[tuple[str, bool]]:
            """``chunk``'s speakable runs, its page cue taken out and the page
            sent, each with whether it comes after a page still on its way; an
            open brace's tail is held for the next chunk."""
            nonlocal buf, moved, arrival, ahead
            buf += chunk
            out: list[tuple[str, bool]] = []
            while (m := _PAGE_CUE.search(buf)) is not None:
                before, value, buf = buf[: m.start()], m.group(1), buf[m.end() :]
                if before:
                    out.append((before, arrival is not None))
                target = self._page_target(value)
                if target is None:
                    logger.info("explora: page cue {!r} names no page; dropped", value)
                    self._note(
                        f"[Your page cue {value} named no page of the site, so the "
                        "screen did not move. Never say it is on their screen: find the "
                        "page with search_site, or the page's own sub-pages, and cue it.]"
                    )
                    continue
                if self._site == "site" and target == self._path:
                    continue  # Already there: a show cue after it does the rest.
                if moved is not None:
                    logger.info(
                        "explora: second page cue {!r} in one reply, after {}; dropped",
                        value,
                        moved,
                    )
                    continue
                moved = target
                arrival = self._open_page(target)
                # Kept until done: a reply over before its page is up leaves
                # the page to come up (and its Spanish twin to load) by itself.
                self._arrivals.add(arrival)
                arrival.add_done_callback(self._arrivals.discard)
                ahead = 0
            cut = buf.rfind("{")
            if not final and cut >= 0 and "}" not in buf[cut:] and len(buf) - cut <= MAX_CUE:
                head, buf = buf[:cut], buf[cut:]
            else:
                head, buf = buf, ""
            if head:
                out.append((head, arrival is not None))
            return out

        async def said(runs: list[tuple[str, bool]]) -> AsyncGenerator[Speech, None]:
            """``runs``, each held for the page once the reply is far enough
            ahead of it; the honest line instead, once the page is late."""
            nonlocal late, ahead, arrival
            # Sentence by sentence while a page is on its way: a model may
            # stream a whole reply in one chunk.
            pieces = [
                (piece, after)
                for run, after in runs
                for piece in (_sentence_runs(run) if after else [run])
            ]
            for piece, after in pieces:
                if arrival is not None and (arrival.done() or ahead >= _AHEAD_SENTENCES):
                    up = await arrival
                    arrival = None
                    if not up:
                        late = True
                        yield SpeechChunk(f" {page_late_line(self.spoken)}")
                        return
                if arrival is not None and after and piece.rstrip().endswith(_STOPS):
                    ahead += 1
                yield SpeechChunk(piece)

        def opening(text: str, *, final: bool) -> str | None:
            """The reply's opening, once there is enough of it to decide on."""
            nonlocal lead
            whole = (lead or "") + text
            if not final and not self._decided(whole):
                lead = whole
                return None
            lead = None
            if not whole.strip():
                return whole
            # A holding line is mine to say, not his: he copied it on dev call
            # 1f6cd8ce ("Just a moment. Here are the rooms").
            return self._with_backstop(_HOLD_OPENER.sub("", whole, count=1))

        try:
            async for event in turn:
                if late:
                    if not isinstance(event, SpeechChunk):
                        yield event
                    continue
                if isinstance(event, SpeechChunk):
                    text = event.text
                    if lead is not None and (text := opening(text, final=False)) is None:
                        continue
                    async for out in said(runs_of(text, final=False)):
                        yield out
                    continue
                if isinstance(event, SpeechEnd):
                    rest = opening("", final=True) or "" if lead is not None else ""
                    async for out in said(runs_of(rest, final=True)):
                        yield out
                yield event
            if not late:
                rest = opening("", final=True) or "" if lead is not None else ""
                async for out in said(runs_of(rest, final=True)):
                    yield out
        finally:
            await turn.aclose()

    @staticmethod
    def _decided(lead: str) -> bool:
        """Whether a reply's opening is enough to tell if it brought a cue of
        its own: its first cue closed, or :data:`_LEAD_CHARS` of words with no
        cue still open. On a dev test on 2026-10-28 the first chunk was the
        sliver "{show", read as no cue, and his right one was overridden."""
        body = lead.lstrip()
        if not body:
            return False
        if body.rfind("{") > body.rfind("}"):
            return len(body) - body.rfind("{") > MAX_CUE
        return "}" in body or len(body) >= _LEAD_CHARS

    def _cue_is_here(self, lead: str) -> bool:
        """Whether a reply's opening ``lead`` brings a show or faq cue that
        names something on the page in front."""
        here = (*self._headings(), *self._tab_labels(), *self._faqs(), *self._known_labels())
        return any(
            _match(m.group(2), here) is not None or match_label(m.group(2), here) is not None
            for m in re.finditer(r"\{\s*(show|faq)\s*:\s*([^{}]*?)\s*\}", lead, re.IGNORECASE)
        )

    def _page_target(self, value: str) -> str | None:
        """The path a page cue opens: a page of the crawl, or one of the page
        in front's own links (a lodge's sub-pages, the Spanish site's pages),
        which the crawl may hold under another path. On dev call 1f6cd8ce the
        Easter Island lodge's /easter-island-excursions/ was dropped three
        times as unknown, though its own tab bar linked it."""
        page = self.kb.page(value)
        if page is not None:
            return page.path
        want = canonical_path(value)
        links = self.page.links if self.page is not None else []
        return want if any(canonical_path(link) == want for link in links) else None

    def _open_page(self, path: str) -> asyncio.Task[bool]:
        """Open ``path`` on the tab in front at once, his voice playing on, and
        from now check cues against it; the wait for it to report itself."""
        seen = self._pages_seen
        # The page being left may report itself again (late-rendering parts):
        # only a report of another page is the new one.
        leaving = self._path if self._site == "site" else None
        self._page_arrived.clear()
        self._page_failed = False
        logger.info("explora: opening {}", path)
        self._send_move(NAVIGATE.id, {"path": site_path(path), "after_words": 0})
        self._cue_path = path
        self._shown = None
        # On the Spanish site an English path may be the page in front: the
        # page re-reports itself rather than reload, and that is the arrival.
        if leaving is not None and leaving.startswith("/es/"):
            leaving = None
        return asyncio.ensure_future(self._page_up(path, seen, leaving))

    async def _page_up(self, path: str, seen: int, leaving: str | None) -> bool:
        """Whether ``path``, opened when ``seen`` pages had reported, came up
        in time. In a Spanish call, an English page that comes up is loaded
        again as its Spanish twin."""
        deadline = time.monotonic() + _PAGE_WAIT_S
        while self._pages_seen == seen or (leaving is not None and self._path == leaving):
            left = deadline - time.monotonic()
            if left <= 0 or self._page_failed:
                logger.warning("explora: {} did not come up", path)
                self._cue_path = self._path if self._site == "site" else None
                where = "the booking site" if self._site == "reservations" else self._path
                self._note(
                    f"[The page you opened, {site_path(path)}, did not come up: the screen "
                    f"still shows {where}. Never say it is on their screen; offer to open "
                    "it again.]"
                )
                return False
            try:
                await asyncio.wait_for(self._page_arrived.wait(), left)
            except TimeoutError:
                continue
            self._page_arrived.clear()
        if self.spoken == "es" and self._page_language() == "en":
            await self._load_twin()
        self._cue_path = self._path if self._site == "site" else None
        logger.info("explora: {} is up", self._path)
        return True

    async def _load_twin(self) -> None:
        """The page in front came up in English in a Spanish call: ask the tab
        to load its own Spanish twin, which its ``<head>`` names, and wait for
        it. On prod call be1f5b9a every page he opened came up in English."""
        english, seen = self._path, self._pages_seen
        self._twin_refused = False
        self._page_arrived.clear()
        logger.warning("explora: {} came up in English; loading its Spanish twin", english)
        self._send_move(TWIN.id, {"language": "es"}, when="quiet")
        deadline = time.monotonic() + _TWIN_WAIT_S
        while (self._pages_seen == seen or self._path == english) and not self._twin_refused:
            left = deadline - time.monotonic()
            if left <= 0:
                break
            try:
                await asyncio.wait_for(self._page_arrived.wait(), left)
            except TimeoutError:
                continue
            self._page_arrived.clear()
        if self._page_language() == "en":
            logger.warning("explora: {} stays in English", self._path)
            self._note(
                "[The page in front is in English: it has no Spanish version, or it did not "
                "load. Cue the English headings the screen lines give.]"
            )

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
            if written == "en" and not may_write_english(
                self._last_heard, self.spoken, language_of
            ):
                written = None
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

    def _with_backstop(self, chunk: str) -> str:
        """The reply's opening (up to its first cue, or :data:`_LEAD_CHARS` of
        words; :meth:`_decided`), with the page the visitor asked about cued in
        front of it when the reply brings no cue of its own."""
        if self._backstop is None or not chunk.strip():
            return chunk
        path, self._backstop = self._backstop, None
        # His own cue wins when it opens a page, or shows something the page
        # in front has; a section cue that names nothing here does not keep
        # the visitor on the wrong page.
        if (
            _PAGE_CUE.search(chunk)
            or self._cue_is_here(chunk)
            or canonical_path(path) == self._path
        ):
            return chunk
        logger.info("explora: the reply has no cue; showing {} first", path)
        return f"{{page: {path}}}{chunk}"

    def _auto_cues(
        self, sentence: str, index: int, placed: tuple[tuple[str, tuple[str, ...]], ...]
    ) -> list[AutoCue]:
        """Stage's backstop: what a sentence of his names or describes on the
        page and did not cue. SendPotion's dev call 56e87ed1 had him describe
        four sections of a page with no cue at all.

        A sentence that names several things the page has ("Patagonia, the
        Atacama Desert and Easter Island") gets one cue per name, each anchored
        at the word he names it with, so the ring follows his voice along."""
        if {verb for verb, _ in placed} & {"show", "faq"}:
            return []
        if self._booking_in_front():
            return []
        if _BOOKING_TALK.search(_fold(sentence)):
            logger.info("explora: backstop: none on a booking sentence {!r}", sentence[:120])
            return []
        cues: list[AutoCue] = []
        last = self._shown
        for at, verb, label in self._names(sentence):
            if label != last:
                cues.append((verb, [label], at))
                last = label
        if not cues and (shown := self._section_for(sentence)) is not None and shown != last:
            cues.append(("show", [shown]))
            last = shown
        self._shown = last
        return cues

    def _names(self, sentence: str) -> list[tuple[int, Literal["show", "faq"], str]]:
        """Everything on the page in front that ``sentence`` names outright, in
        the order he says it, as (offset, verb, label): its questions and tabs
        ("Suni covers the mid altitudes" names "3. Suni" — on dev call 0a304d89
        he talked through four zones listed only as accordions, and the screen
        stayed put), its headings (one word too, when the page in front reports
        it: BOLIVIA, CHILE, PERU on /lodge/), and the lodges a page of lodges
        lists by name."""
        if self._cue_path is None:
            return []
        live = self._live()
        page = self.kb.page(self._cue_path)
        kinds: dict[str, Literal["show", "faq"]] = {}
        labels: list[tuple[str, bool]] = []

        def add(
            items: tuple[str, ...] | list[str], single: bool, verb: Literal["show", "faq"]
        ) -> None:
            for label in items:
                if label not in kinds:
                    kinds[label] = verb
                    labels.append((label, single or bool(re.match(r"\s*\d+\s*[.)]", label))))

        add(self._faqs(), True, "faq")
        add(self._headings(), live, "show")
        add(self._tab_labels(), True, "show")
        if page is not None:
            add(_useful_headings(page), False, "show")
            add(listed_items(page), True, "show")
        return [(at, kinds[label], label) for at, label in names_in(sentence, labels)]

    def _lists_lodges(self) -> bool:
        """Whether the page in front lists the lodges by name, as /lodge/ and
        /destinations/ do: "the lodges" asked for there are answered there."""
        if self._site != "site":
            return False
        return len(listed_items(self.kb.page(self._path))) >= _LODGES_LISTED

    def _booking_in_front(self) -> bool:
        """Whether this turn's cues would land on reservations.explora.com:
        the tab in front is on it, and no page cue this turn has taken it to
        www.explora.com. A show or faq cue has nothing to ring there."""
        return self._site == "reservations" and self._cue_path is None

    def _live(self) -> bool:
        """Whether the page in front is the one this turn's cues are on, so its
        own report is what they are checked against."""
        return self.page is not None and canonical_path(self.page.path) == self._cue_path

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

    def _resolve(self, move: Move, args: list[str]) -> list[str] | None:
        """Stage's resolver: a cue checked against the page, as the tools are,
        and rewritten to the page's own spelling; one that names nothing real
        is dropped and logged rather than reaching the page."""
        if not args:
            return None
        value = args[0]
        if self._booking_in_front():
            # Dev call 453f2e19: every {show: …} on reservations.explora.com
            # was refused by the page, which shows www.explora.com's sections.
            logger.debug("explora: {} {!r} dropped: the booking site is in front", move.id, value)
            return None
        if move.id == FAQ.id:
            question = _match(value, self._faqs())
            return None if question is None else [question]
        # show: a heading of the page in front, else a tab's label, else words.
        heading = _match(value, self._headings()) or _match(value, self._tab_labels())
        if heading is None and self.spoken == "es" and not self._live():
            # A Spanish heading for a page still loading, and loading again as
            # its Spanish twin: only the crawl's English is here to judge it
            # by, so the page judges it when it comes up.
            self._shown = value
            return [value]
        if heading is None and self._invented(value):
            # Written blind for a page not yet seen: the nearest heading the
            # page reports or its crawl lists, by its words, before giving up.
            heading = match_label(value, self._known_labels())
            if heading is None:
                logger.info(
                    "explora: {!r} is on neither {} nor its crawl; dropped", value, self._cue_path
                )
                return None
            logger.info("explora: {!r} taken as {!r}", value, heading)
        self._shown = heading or value
        return [heading or value]

    def _known_labels(self) -> list[str]:
        """The headings and tabs of the page this turn's cues are on, as it
        reports them and as its crawl lists them."""
        page = self.kb.page(self._cue_path) if self._cue_path else None
        crawled = [*page.headings, *page.tabs] if page is not None else []
        return list(dict.fromkeys([*self._headings(), *self._tab_labels(), *crawled]))

    def _invented(self, value: str) -> bool:
        """Whether a show cue's words read as a heading ("Our Lodges: Your Home
        Base for Adventure") that neither the page in front nor its crawl has.
        Written blind for a page not yet seen, one always failed on the page
        (prod calls 80dac4ed and be1f5b9a): it is dropped, not rung. Plain
        words ("the red door") and a name the page's text has are rung."""
        if self._cue_path is None:
            return False
        words = re.findall(r"[^\W\d_]+", value)
        long = [w for w in words if len(w) > 3]
        if len(long) < 2 or sum(w[0].isupper() for w in long) < 0.75 * len(long):
            return False
        page = self.kb.page(self._cue_path)
        known = [*self._headings(), *self._tab_labels(), *self._faqs()]
        if page is not None:
            known += [*page.headings, *page.tabs, *(f.q for f in page.faqs)]
            known += [s.text for s in page.sections]
        elif len(words) < 3:
            return False  # A page the crawl lacks: only a long heading is judged.
        want = _fold(value)
        return not any(want in _fold(k) for k in known)

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

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Page→brain events, folded in silently: no floor taken, no turn."""
        # Results, hello and progress: a slow move's progress keeps it alive.
        staged = StagePageEvents.parse(msg)
        if staged is not None:
            if (note := self._staged(staged)) is not None:
                self._note(note)
            return
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
        self._shorten_idle()
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
                self.stage.landed(
                    NAVIGATE.id, event=event, fits=lambda landing: _opened(landing, event)
                )
                # Read in with their next message or quiet spell: they may click
                # on before they speak, and only the last page matters.
                return None
            case TabsChanged():
                self.tabs = event.tabs
                self._active = event.active
                self._tabs_unseen = True
                return None
            case StayState():
                note = self._stay_changed(event)
                self.stage.landed(
                    CHECK_AVAILABILITY.id,
                    event=event,
                    fits=lambda landing: _stay_fits(landing, event),
                )
                return note
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
            case TwinLookup():
                if event.source in ("fallback", "timeout"):
                    logger.warning(
                        "explora: no {} twin found for {} ({}, {} ms{})",
                        event.language,
                        event.path,
                        event.source,
                        event.ms,
                        f": {event.error}" if event.error else "",
                    )
                return None

    def _stay_changed(self, event: StayState) -> str | None:
        before = self.stay
        self.stay = event
        lodge = event.hotel or event.hotel_code
        if event.step == "rooms":
            rooms = _clip([f"{r.name} ({r.text})" if r.text else r.name for r in event.rooms], 12)
            if before is None or before.step != "rooms" or before.date != event.date:
                self._rooms_added = 0
                self._talk_through(
                    "The rooms and rates are on their screen and they have not spoken. Name "
                    "two of the rooms with their price in one sentence each, and say they choose "
                    "a room and book it themselves from here.",
                    rooms_line([r.name for r in event.rooms], self.spoken),
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
            note += self._selected(event)
        note += "]"
        wanted = self.stay_wanted
        if (
            event.date
            and wanted
            and event.chosen_nights != wanted
            and self._nights_set_for != event.date
        ):
            # They said how many nights; the site picked its own. Set theirs,
            # without asking them again: the talk-through follows the page.
            self._nights_set_for = event.date
            logger.info(
                "explora: the site selected {} nights; setting the {} they asked for",
                event.chosen_nights,
                wanted,
            )
            self._send_move(
                CHECK_AVAILABILITY.id,
                {
                    "hotel_code": event.hotel_code,
                    "date": event.date,
                    "month": None,
                    "nights": wanted,
                    "rooms": False,
                    "language": self._site_language(),
                },
            )
            return note[:-1] + f" Setting the {wanted} nights they asked for now.]"
        if before is None or before.hotel_code != event.hotel_code:
            self._talk_through(
                "The booking calendar is on their screen and they have not spoken. Name two "
                "or three open arrival days near what they asked, in one sentence, and ask which "
                "suits them.",
                days_line(event.open_days, self.spoken),
            )
        elif event.date and (
            before.date != event.date or before.chosen_nights != event.chosen_nights
        ):
            ask = (
                f"The nights for their arrival day are on their screen. They asked for {wanted} "
                "nights: say the price from per night for the stay selected, which is the "
                "nearest the site offers to theirs, without asking them about the nights, and "
                "offer to show the rooms."
                if wanted
                else "The nights for their arrival day are on their screen. Say the price from "
                "per night for the recommended stay, and offer to show the rooms."
            )
            self._talk_through(ask, nights_line(event.nights, event.chosen_nights, self.spoken))
        return note

    def _selected(self, event: StayState) -> str:
        """The nights the site has selected, for the stay note: theirs, or the
        site's own default, never passed off as their choice."""
        chosen, wanted = event.chosen_nights, self.stay_wanted
        if not chosen:
            return ""
        if wanted == chosen:
            return f" Selected: {chosen} nights, as they asked."
        if wanted:
            return (
                f" Selected: {chosen} nights, the site's choice, not theirs: they asked for "
                f"{wanted}."
            )
        return f" Selected: {chosen} nights, the site's default, not their choice."

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
        running = "; ".join(
            f"{_ACTS.get(r.move.id, r.move.id)} ({r.phase or 'sent'}, {r.seconds:.0f} s so far)"
            for r in self.stage.running()
            if r.move.verb is None
            and r.move.cls is not MoveClass.LOOK
            and r.seconds >= 2
            and not r.shown
        )
        if running:
            self._note(
                f"[Still working on the page: {running}. Not done yet, and not failed: if it "
                "comes up, say it is still working on it.]"
            )
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
        self.append_note(text)

    def _talk_through(self, ask: str, line: str | None = None) -> None:
        """Have him talk through what the page just showed, in the next quiet
        spell: ``ask`` for the model, and ``line`` if its turn says nothing."""
        self._talk = ask
        self._talk_fallback = line
        self._shorten_idle()

    def _restore_idle(self) -> None:
        if self._idle_short:
            self._idle_short = 0
            configure_soon(self.session, Config(idle=IdleConfig(timeout_ms=_IDLE_MS)))

    def _landing_line(self, landing: Landing) -> str | None:
        """His written line the moment a move shows on screen: the calendar,
        the nights or the rooms check_availability asked for, or a page a
        reply opened after that reply was over (one still under way describes
        it itself). Said in the next quiet spell, made short now."""
        event = landing.event
        if isinstance(event, StayState):
            hotel = self.kb.hotel(event.hotel_code)
            # "Atacama, Chile" is said "Atacama".
            label = hotel.label if hotel is not None else (event.hotel or event.hotel_code)
            line = stay_landed_line(event, label.split(",")[0].strip(), self.spoken)
        elif isinstance(event, PageChanged) and not self._replying:
            line = page_landed_line(event, self.spoken)
        else:
            return None
        if self._hold is not None and self._hold[0] == landing.call_ref:
            self._hold = None
        logger.info(
            "explora: {} {} on screen at {:.1f} s; landing line {!r}",
            landing.call_ref,
            landing.move.id,
            landing.seconds,
            line,
        )
        self._shorten_idle(LANDING_FLOOR_MS)
        return line

    def _send_move(
        self,
        move: str,
        args: dict[str, ArgValue],
        *,
        line: str | None = None,
        when: Literal["now", "quiet"] = "now",
    ) -> Literal["sent", "queued", "running"]:
        """Send a move through Stage, with the written line for it (one of
        :data:`_LANDED`, in the language he speaks) should the turn say
        nothing. ``running`` when exactly this move is already on its way,
        which is not sent twice."""
        try:
            ref = self.stage.send(move, args, when=when)
        except Refused:
            return "running"
        if line is not None:
            landed(_LANDED[line][self.spoken])
        return "sent" if ref is not None else "queued"

    # ─── Stage's answers ────────────────────────────────────────────────

    def _staged(
        self,
        event: stage_wire.StageResult
        | stage_wire.StageHello
        | stage_wire.StageProgress
        | stage_wire.StageEvent,
    ) -> str | None:
        """One answer from the page, folded through Stage; the line the model
        should see, if any. A progress gives its move its time again and says
        nothing."""
        if not isinstance(event, stage_wire.StageResult):
            self.stage.handle(event)
            return None
        result = self.stage.handle(event)
        if result is None or result.moved:
            return None
        return self._result_note(result)

    def _result_note(self, result: stage_wire.StageResult) -> str | None:
        """What the model hears about a move, as its class says: a look only
        when it failed, any other move one line naming the act, and a failure
        said plainly. A result that comes ``late``, after the move was said to
        be unknown, corrects that (:meth:`_late_note`)."""
        move = self.stage.move_of(result.call_ref)
        if move is None:
            return None
        if self._hold is not None and self._hold[0] == result.call_ref:
            self._hold = None
        if result.late:
            return self._late_note(result, move)
        landed_ = result.outcome in ("applied", "partial")
        detail = result.detail or result.outcome
        if result.outcome == "partial" and result.refused:
            missed = "; ".join(r.why for r in result.refused)
            detail = f"{detail}; not done: {missed}"
        if move.cls is MoveClass.LOOK:
            if landed_ or (result.outcome == "refused" and detail in ("interrupted", "stale")):
                return None  # Spoken past, or talked over: not a failure.
            if move.id == FOCUS_TAB.id:
                return f"[The tab did not come to the front ({detail}). Never say it did.]"
            return (
                f"[A screen cue of yours did not land ({detail}). If the visitor asks where "
                "it is, show it again; otherwise carry on.]"
            )
        act = _ACTS.get(move.id, move.id)
        if move.id == NAVIGATE.id and not landed_:
            self._page_failed = True
            self._page_arrived.set()
        if move.id == TWIN.id and not landed_:
            # The page in front has no twin: whatever waits for one stops.
            self._twin_refused = True
            self._page_arrived.set()
            return (
                f"[The page in front stays as it is ({detail}). Say so plainly if the visitor "
                "asked for it; never say it changed.]"
            )
        if landed_:
            if move.cls is MoveClass.CONFIRMED:
                return None  # The page says what happened: enquiry_sent.
            if result.outcome == "partial":
                return (
                    f"[Only part of it is done on their screen, {act}: {detail}. Say plainly "
                    "what is done and what is not.]"
                )
            return f"[Done on their screen, {act}: {detail}.]"
        if move.id in _BOOKING_MOVES:
            self._talk = None
            self._restore_idle()
        if result.outcome == "unknown":
            return (
                f"[The page did not answer {act} ({detail}). Never say it happened; go by "
                "what the screen lines show.]"
            )
        return (
            f"[That did not happen on the page ({act}: {detail}). Tell the visitor plainly "
            "and offer what you can do instead; never say it worked.]"
        )

    def _late_note(self, result: stage_wire.StageResult, move: Move) -> str | None:
        """A result after he was told the move was not confirmed: a short
        correction, and for a confirmed move the page did after all, his
        written line ("Done after all, …") in the next quiet spell."""
        landed_ = result.outcome in ("applied", "partial")
        detail = result.detail or result.outcome
        act = _ACTS.get(move.id, "a screen cue of yours")
        if not landed_:
            if move.cls is MoveClass.LOOK:
                return None  # Already said as not landed; nothing to correct.
            return (
                f"[The page has now answered {act}: {detail}. It did not happen; never say it did.]"
            )
        if move.cls is MoveClass.CONFIRMED and (lines := _DONE_AFTER_ALL.get(move.id)):
            self._late_done = lines[self.spoken]
            self._shorten_idle()
        return (
            f"[Correction: {act} did happen after all ({detail}). You were told the page did "
            "not answer: it did.]"
        )

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
            self.choose_room,
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
        known_date = date or (stay.date if stay and stay.hotel_code == hotel.code else "")
        rooms = request.show_rooms and bool(date or (self.stay and self.stay.date))
        if not rooms and known_date and (request.nights or self.stay_wanted):
            # Dev call 453f2e19: "show me the rates", the day and the nights
            # known, took a nights step; the rooms list the stay's prices.
            asked = self._heard[-1] if self._heard else ""
            if _RATES_ASK.search(asked):
                rooms = True
                date = date or known_date
                logger.info("explora: {!r} asks for the rates: on to the rooms", asked[:80])
        # The nights they said, when the model left them out: on dev call
        # 2f94965e "three nights" never reached the page, and the site's own
        # five were read out as chosen.
        nights = request.nights or self.stay_wanted
        if nights and not request.nights:
            logger.info("explora: nights {} filled in, as the visitor said", nights)
        if date and nights:
            self._nights_set_for = date
        args: dict[str, ArgValue] = {
            "hotel_code": hotel.code,
            "date": date,
            "month": request.month[:7] if request.month and not date else None,
            "nights": nights,
            "rooms": rooms,
            "language": self._site_language(),
        }
        line = (
            "rooms"
            if rooms
            else "stay_date"
            if date
            else "stay_nights"
            if request.nights
            else "stay"
        )
        # The same move again while it is still on its way would load the page
        # twice (prod call be1f5b9a sent the rooms twice, 3.7 s apart): Stage
        # does not send it twice.
        if self._send_move(CHECK_AVAILABILITY.id, args, line=line) == "running":
            return f"Already opening that for {hotel.label}: the page will report itself."
        self._booked = True
        what = ", ".join(
            x
            for x in (
                f"arriving {_spoken_date(date)}" if date else "",
                f"{nights} nights" if nights else "",
                "going on to the rooms" if rooms else "",
            )
            if x
        )
        return f"The booking site is opening {hotel.label}" + (f", {what}" if what else "") + "."

    async def choose_room(self, request: RoomRequest) -> str:
        """On the rooms and rates, select the room they picked, for their
        travellers and bed type: the page shows its summary with the check-out
        button, which they press themselves. Never books or pays."""
        stay = self.stay
        if stay is None or stay.step != "rooms":
            return (
                "Not chosen: the rooms are not on screen. check_availability with show_rooms first."
            )
        room = _match(request.room, [r.name for r in stay.rooms])
        if room is None:
            listed = ", ".join(r.name for r in stay.rooms) or "none"
            return f"Not chosen: no room '{request.room}'. The rooms: {listed}."
        count = max(1, min(request.count, 4))
        # A bed type only as the visitor said it: on prod call be1f5b9a "King"
        # was chosen for a visitor who never named one.
        bed = request.bed if request.bed and _BED_WORDS.search(" ".join(self._heard)) else None
        if request.bed and bed is None:
            logger.info("explora: bed {} dropped: the visitor never said one", request.bed)
        # The site adds a room each time its button is pressed, so the same
        # press twice in one turn is a repeat; in another turn it is another
        # room (prod call be1f5b9a: the second room for four was refused).
        chosen = (room, request.travellers, bed, count)
        already = f"{room} is already being added, as asked: the summary is on screen."
        if chosen == self._room and self._room_turn == self._turn:
            return already
        args: dict[str, ArgValue] = {
            "room": room,
            "travellers": request.travellers,
            "bed": bed,
            "count": count,
        }
        if self._send_move(CHOOSE_ROOM.id, args, line="room") == "running":
            return already
        self._room, self._room_turn = chosen, self._turn
        self._rooms_added += count
        self._booked = True
        what = f"Adding {count} {room} rooms" if count > 1 else f"Adding {room}"
        return (
            f"{what}; rooms added on these rates so far: {self._rooms_added}. The visitor "
            "presses check-out themselves."
            + (" No bed type was passed: they did not say one." if request.bed and not bed else "")
        )

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
        args: dict[str, ArgValue] = {
            "expedition_code": hotel.code,
            **{key: fields.get(key) for key in _ENQUIRY_KEYS},
            "language": self._site_language(),
        }
        self._booked = True
        self._send_move(FILL_ENQUIRY.id, args, line="enquiry")
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
        # The visitor's own details leave the page here: confirmed, and only
        # behind their tick and every field checked above.
        if self._send_move(SEND_ENQUIRY.id, {}, line="sent") == "running":
            return "Already sending it; the page will say when it has gone."
        self._booked = True
        return "Pressed Send Message; the page will say when it has gone."

    async def switch_tab(self, request: TabRequest) -> str:
        """Bring ANOTHER of the visitor's open Explora tabs to the front — only
        when the screen lines list more than one. Never to show a page: a page
        cue does that, in this tab."""
        if len(self.tabs) <= 1:
            return (
                "Not switched: they have only this one Explora tab. To show a page, cue it "
                "with {page: /path/} at the start of your reply. Never say it is on screen."
            )
        tab = next((t for t in self.tabs if t.tab_id == request.tab_id), None)
        if tab is None:
            listed = ", ".join(f"{t.tab_id} ({t.title})" for t in self.tabs) or "none"
            return f"Not switched: no tab '{request.tab_id}'. Open tabs: {listed}."
        self._send_move(FOCUS_TAB.id, {"tab_id": tab.tab_id}, line="tab")
        return f"Brought '{tab.title or tab.url}' to the front."

    async def set_language(self, request: LanguageRequest) -> str:
        """Conduct the rest of the call in English ('en') or Spanish ('es'),
        listening and speaking. Call it when they ask for the other language in
        words that are not already it — "Can you speak Spanish?" — and to go
        back. Say one short line in the language you are switching to, in the
        same response. A visitor already speaking Spanish has been switched: do
        not call it for them. Called with the language the call is already
        in, it loads the page in front in that language."""
        if request.language == self.spoken:
            name = LANGUAGE_NAMES[request.language]
            if self._page_language() not in (None, request.language):
                self._show_in(request.language)
                return f"The call is in {name}; the page in front is loading in {name}."
            return f"The call is already in {name}."
        self._chosen = True
        configure_soon(self.session, self._speaking(request.language))
        logger.info("explora: language -> {} (asked)", request.language)
        return "ok"


__all__ = [
    "MOVES",
    "EnquiryFields",
    "ExploraBrain",
    "LanguageChanged",
]
