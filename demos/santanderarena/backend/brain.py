"""SantanderBrain — Javier, a guide on www.santanderarena.cl.

The site is Santander Arena's, not ours. A browser extension injects the widget
and a small adapter into it; the adapter turns each :class:`~voqalize.sdk.Action`
below into a move on the tab in front — a page, a section scrolled to and
ringed, a card brought out of its carousel, an FAQ opened — and the call itself
opens the ticket, parking and VIP links he hands over, on Puntoticket, in a new
tab. Every tab reports what it shows as a typed event (:mod:`.app_events`),
whichever of the visitor and Javier moved it.

This is a port of the SendPotion guide (``demos/sendpotion``), whose seams were
earned on real calls; what differs is the site.

**A guide, not a search box.** Every turn answers what was asked, in words, as
a conversation: the answer, why it matters for this visitor's night, and a
short offer of what comes next. A move on the page goes beside the answer and is
talked about, never just pointed at.

**Every fact has a source.** A date, a time, an experience, a bar, a gate or a
rule is spoken from L1 (in this prompt), an L2 topic he read, a search of the
site or of its events, or what the page itself reported. Never from memory.

**Nothing on the page is invented.** A path he navigates to, a heading he
scrolls to, an FAQ he opens and a ticket link he opens are checked against the
crawl and against what the tab last reported; anything else is refused before
it reaches the page.

**The purchase is the visitor's.** Tickets, parking and VIP experiences are sold
on Puntoticket, a site of its own. He opens the right link in a new tab and the
visitor buys there; the extension does not run on it.

**The screen follows his voice.** He writes his moves into the reply as cues
(``{show: Completa tu noche en Santander Arena}``), at the start of the sentence
they belong to; the brain takes them out of the speech, checks them against the
site, and the page fires each as the voice reaches its sentence (:mod:`.cues`,
and the extension's ``narration.ts``). The site loads a whole new document for
every page, so the extension carries the cues still owed across the load, and
the call rejoins on the next page with the speech held.

**Spanish or English, as the visitor chose or speaks.** The site and most of its
visitors are Chilean, so the call opens in Spanish; it follows a visitor who
speaks English, and a language chosen on the widget's toggle (or asked for)
holds whatever they speak. Either way the voice follows the language his reply
is written in. The voice is one man, recorded in each.
"""

from __future__ import annotations

import inspect
import math
import re
import time
from collections.abc import AsyncGenerator
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Literal
from zoneinfo import ZoneInfo

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
    SpeechStart,
    UserIdle,
    UserMessage,
)
from voqalize.sdk.voice import ToolChoice
from voqalize.sdk.wire import Config, IdleConfig, SttConfig, TtsConfig, Voice

from . import knowledge as kb
from .app_events import (
    SANTANDER_EVENTS,
    CommandFailed,
    LanguageRequested,
    PageChanged,
    SantanderEvent,
    TabInfo,
    TabsChanged,
)
from .cues import CueKind, CueParser, RawCue
from .knowledge import (
    TOPIC_IDS,
    Event,
    Knowledge,
    Page,
    canonical_path,
    canonical_url,
    fold,
    is_ticket_url,
    norm,
)

AGENT_NAME = "Javier"

#: LOW, as SendPotion measured: at MINIMAL, Gemini mostly made the page call
#: first and wrote nothing; at LOW it writes the answer first and calls at the
#: end, so the page moves while he is still talking.
THINKING = types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)
#: SendPotion's model, for SendPotion's reason: on its prompt 3.8 had the first
#: words out in about two seconds where 3.5 spiked to seven.
MODEL = "gemini-3.8-flash"

#: Santiago, for "tonight" and "this weekend".
TIMEZONE = ZoneInfo("America/Santiago")

# ─── Voice and timing ──────────────────────────────────────────────────────────

#: Javier's voice: the speech tier's male persona recorded once in English and
#: once in Spanish, so a switch keeps the same man. SendPotion's Javier.
VOICE = Voice.OMNIVOICE_JAVIER

#: A quiet visitor is someone looking at a page; a guide beside them says
#: something after a while, and not twice more.
_IDLE_MS = 20_000
_IDLE_NUDGES = 2
#: The idle window while a confirmation is owed: a visitor who reacts speaks
#: first, one who is reading hears it from him.
_TALK_THROUGH_MS = 2_000
#: A little more patience than the demos' default: a visitor working out which
#: night they are free pauses mid-sentence.
SANTANDER_PATIENCE = PATIENCE + 2
#: A message this soon after the last one is the rest of the same thought.
_FRAGMENT_S = 4.0

# ─── Language ──────────────────────────────────────────────────────────────────

#: What he answers in, as the tag both legs of the call take. The recognizer
#: hears either whatever it is set to and writes what it heard, so the
#: recognizer leg only follows the voice, as a pair, and the language is
#: decided here from words: the visitor's, then his own.
Lang = Literal["en", "es"]
#: The site is Chilean and in Spanish, and so are most of its visitors.
OPENING: Lang = "es"
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
    muéstrame dime explícame funciona hace hacer entradas concierto conciertos llegar
    estacionamiento comer quiénes quién próximo próximos
    """.split()  # noqa: SIM905
)
_ENGLISH_WORDS = frozenset(
    """the is are was what how can could you your i i'm it it's this that these those do
    does show me my we our for with about and of to have has there here please want
    would like tell sure yes okay right of course let's
    """.split()  # noqa: SIM905
)
#: Enough of his reply to tell its language: its first sentence, or this many
#: characters. On SendPotion the first chunk of a Spanish reply was " P".
_WRITTEN_ENOUGH = 60
_SENTENCE_END = re.compile(r"[.?!](?:\s|$)")
#: Letters and marks only Spanish writes, of the two.
_SPANISH_MARKS = re.compile(r"[¿¡ñáéíóú]", re.IGNORECASE)
_LETTERS = re.compile(r"[\wáéíóúüñ']+")
#: A cue is the site's own words, in Spanish whatever he speaks.
_CUE_TEXT = re.compile(r"\{[^{}]*\}?")


def language_of(text: str, *, sure: bool = True) -> Lang | None:
    """The language ``text`` is plainly in, or ``None``.

    ``sure`` is for what the visitor said, where one stray word must not move
    the call: Spanish needs two of its words (or its marks and one), English
    three of its own and none of Spanish's. Unsure is for the first words of his
    own reply, which are few: one Spanish word, or two English ones, will do.
    Cues are taken out first: they are the site's Spanish inside any reply."""
    text = _CUE_TEXT.sub(" ", text)
    words = set(_LETTERS.findall(text.lower()))
    es = len(words & _SPANISH_WORDS) + (1 if _SPANISH_MARKS.search(text) else 0)
    en = len(words & _ENGLISH_WORDS)
    if es >= (2 if sure else 1) and es > en:
        return "es"
    if en >= (3 if sure else 2) and es == 0:
        return "en"
    return None


#: "Vídeo" is Spain's spelling, and the voice reads it with Spain's stress;
#: Latin America writes and says "video". The prompt asks for it, and this
#: makes sure of it in everything he says in Spanish.
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
    """Go to one of the site's pages and, with ``heading`` or ``text``, scroll
    to that section or card and ring it; with ``faq``, open that FAQ on it. The
    page loads in full and reports ``page_changed``."""

    path: str
    heading: str | None = None
    text: str | None = None
    faq: str | None = None


class Cue(Action):
    """A move for the page to make when the voice reaches ``at`` — the first
    words of the sentence it belongs to (see :mod:`.cues`); empty ``at`` is
    when the voice stops. With ``path``, it is a :class:`Navigate`; else a
    section, card, words or FAQ on the tab in front."""

    at: str
    word: int = 0
    """Words of the unit before it, for a page that times cues by the clock."""
    path: str | None = None
    heading: str | None = None
    text: str | None = None
    faq: str | None = None


class ShowSection(Action):
    """On the tab in front, scroll to the heading named ``heading`` and ring its
    section; with ``text``, ring the smallest element containing that text (a
    show's card, a bar, a date), brought out of its carousel first."""

    heading: str | None = None
    text: str | None = None


class OpenFaq(Action):
    """Open the FAQ that starts with ``question`` on the page in front, and ring it."""

    question: str


class OpenTickets(Action):
    """Open a ticket, parking or VIP link on Puntoticket in a new tab. The
    visitor buys there; the extension does not run on that site."""

    url: str
    label: str = ""


class FocusTab(Action):
    """Bring one of the visitor's Santander Arena tabs to the front."""

    tab_id: str


class LanguageChanged(Action):
    """The call's language moved, by the toggle, by voice or by
    ``set_language``: the widget's toggle follows at once."""

    language: Literal["en", "es"]


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
        description="A few words to look for on the site, in Spanish or English, e.g. "
        "'estacionamiento', 'objetos perdidos', 'menores de edad', 'Santander Suites'."
    )


class EventsRequest(BaseModel):
    query: str = Field(
        default="",
        description="An artist, a genre, a month or a date, e.g. 'Nicky Jam', 'rock', "
        "'noviembre', 'December 4'. Empty for everything coming up, soonest first.",
    )


TicketKind = Literal["tickets", "parking", "vip"]


class TicketsRequest(BaseModel):
    event: str | None = Field(
        default=None,
        description="The show, by its name or its page path, from find_events or the "
        "screen. Empty for a link on the page in front that is not one show's.",
    )
    kind: TicketKind = Field(
        default="tickets",
        description="'tickets' to buy tickets, 'parking' for a parking space, 'vip' for a "
        "VIP experience.",
    )
    label: str | None = Field(
        default=None,
        description="Only for a link with no show: the button's words as the screen lists "
        "them under its ticket links, e.g. 'Ir a la reservación'.",
    )


class TabRequest(BaseModel):
    tab_id: str = Field(description="The tab_id from the open tabs list.")


class LanguageRequest(BaseModel):
    language: Lang = Field(description="'en' for English, 'es' for Spanish.")


# ─── The prompt ────────────────────────────────────────────────────────────────

_SITE_MAP_CHARS = 18000
_SECTIONS_PER_PAGE = 14
_CARDS_PER_PAGE = 12
_TITLE_SUFFIXES = (" | Santander Arena", " - Santander Arena", " — Santander Arena")


def _short_title(title: str) -> str:
    for suffix in _TITLE_SUFFIXES:
        title = title.removesuffix(suffix)
    return title.strip()


def _site_map(k: Knowledge) -> str:
    """Every page but the shows' and the news stories' own (the events list and
    find_events have those), with its headings and cards."""
    lines: list[str] = []
    size = 0
    pages = [p for p in k.pages.values() if p.kind not in ("event", "news")]
    for p in sorted(pages, key=lambda p: (p.path.count("/"), p.path)):
        heads = "; ".join(p.headings[:_SECTIONS_PER_PAGE])
        cards = "; ".join(dict.fromkeys(c.title for c in p.cards[:_CARDS_PER_PAGE]))
        line = f"- {p.path} — {_short_title(p.title)}"
        line += f" (sections: {heads})" if heads else ""
        line += f" (cards: {cards})" if cards else ""
        size += len(line) + 1
        if size > _SITE_MAP_CHARS:
            break
        lines.append(line)
    return "\n".join(lines) or "(The site map is not loaded: find pages with search_site.)"


def _events_list(k: Knowledge, today: date) -> str:
    """The shows coming up, soonest first: the billboard as the crawl saw it."""
    coming = [e for e in k.events.values() if not e.date or e.date >= today.isoformat()]
    coming.sort(key=lambda e: e.date or "9999")
    lines = [f"- {e.name} — {e.when or 'date not given'} — {e.path}" for e in coming[:40]]
    return "\n".join(lines) or "(No events loaded: use find_events.)"


def _topics(k: Knowledge) -> str:
    return "\n".join(f"- {t.id}: {t.title}" for t in k.topics.values()) or "(none loaded)"


def _prompt(k: Knowledge, today: date | None = None) -> str:
    today = today or datetime.now(TIMEZONE).date()
    return f"""You are {AGENT_NAME}, the guide on Santander Arena's website, santanderarena.cl. Santander Arena is a concert and events arena in Santiago, Chile. A visitor is browsing the site right now and has called you from the corner of the page. You can see and move their screen: you open pages, scroll to the exact section or card that answers them and ring it, bring cards out of the carousels, open FAQs, and open the ticket, parking and VIP links on Puntoticket in a new tab. You are warm, upbeat and helpful — the friend who knows the arena inside out and helps the visitor plan a great night: which show, how to get there, where to park, where to eat and drink, and how to make it special. Planning a night at the arena should feel easy and exciting after talking to you.

# You narrate, and the screen follows your words
You are giving a guided walkthrough, like a host sitting beside the visitor with their screen in front of you both. As you talk about something, it is on their screen, ringed, at that moment: never the top of the page while you describe the third bar.
- Put a screen cue in your reply at the start of the sentence it belongs to. The page moves when your voice reaches that sentence. The visitor never hears a cue.
  - {{page: /path}} opens a page of the site, at its top.
  - {{show: Heading}} scrolls to a heading on the page they are on, or are taken to by a page cue, and rings it. With the name on a card — a show, a bar, a terrace, an experience — it brings that card out of its carousel and rings it. With other words on the page — a date, a gate, an opening time — it rings those words.
  - {{faq: Question}} opens that FAQ and rings it. The FAQ can be on any page: it is found and opened there.
- Use headings and card names exactly as the site pages list, the events list or the screen lines spell them. The site is in Spanish, so cues are in Spanish, also inside an English reply: "{{page: /bares}}{{show: BAR SUR}} Bar Sur is one of four bars inside."
- Never make up a heading. On a show's page, show the show's name, its date line or its buttons ("Comprar tickets", "Comprar estacionamiento"), as the screen lines list them.
- One cue per sentence at most, and only where the screen should change. A cue goes before the sentence, never inside it.
- When the visitor asks where something is ("show me", "where is that", "scroll to it", "muéstrame"), your reply starts with the cue for exactly that thing: the card, the FAQ question, the section. Never just the page above it.
- A page cue opens a page at its top. So after a page cue, every sentence about a part of the page brings its own show cue: each experience, each bar, each show, each step.
- EVERY ANSWER ABOUT THE ARENA STARTS WITH A CUE. Whatever you talk about — a show, an experience, parking, food, how to get there, an FAQ — is on a page in the site pages list or the events list, so open that page and show the section as you begin. When the visitor names a show, open that show's own page. A reply without a cue leaves their screen where it was while you describe something else: the visitor notices, and has to ask you to show it.
- Cues are the only way you move the page. There is no tool for it, and nothing waits on a cue.
- Example, for "what's coming up?": "{{page: /cartelera}} There's a lot coming up. {{show: CAMILO}} Camilo plays on the fifth of November. {{show: NICKY JAM}} And Nicky Jam closes the year on the fourth of December. Want me to open one of them?"

# A good turn helps plan the night
1. Answer what they asked, first, in plain words, and show it as you say it.
2. Say why it matters for them, in a sentence, when you know something about them: who they are going with, which show, what they like.
3. End by offering the next step of their night: one short, specific yes-or-no offer that leads somewhere related, so they only have to say "yes" or pick one. "Want me to open the tickets?" "Shall I show you where to park?" "Would a bar or a terrace suit you better before the show?" Never an open question they have to think hard about, and never "anything else?".
- A night at the arena has an order. Follow it, from wherever the visitor is: what's on, then the show they like, then tickets, then how to make it special (Experiencias VIP, Santander Suites, the Box), then getting there and parking, then food and drink (bars, terraces, food trucks), then the fan spaces to visit (the Cúpula, the Muro de Momentos en Vivo, the Paseo de las Estrellas). After a show, offer its tickets or the VIP experience. After tickets, parking or getting there. After parking, food and drink.
- When they say yes, go there in that reply, with cues, and keep the night moving. When they pick something else, follow them, and pick the story up from there.
- Ask about them only when the answer changes what you show next, and offer the choices: "Are you coming by car or by metro?"

# How you sound
You are heard, not read, so keep it light and warm.
- A turn is three to five short sentences. A walkthrough of a page can run to eight, one item per sentence, each with its cue.
- Every sentence under fifteen words. Small, everyday words. One idea per sentence. One number per sentence.
- THE FIRST SENTENCE IS A FEW WORDS. The visitor hears nothing until your first sentence has been voiced, so open every reply with a sentence of two to six words that ends in a full stop, with the answer in it. A cue may come before it.
- Before most replies the visitor has already heard a short acknowledgement of mine — "Claro.", "Déjame ver.", or in English "Sure.", "Let me see." — so never open with one: your first word is the answer. No "great question", no repeating their question back.
- Spoken words only, apart from cues: no lists, no markdown, no symbols, never an exclamation mark. Write dates, times and numbers as spoken words: "the fifth of November at nine at night", "el cinco de noviembre a las nueve de la noche", never "05/11 21:00 hrs".
- Lines in square brackets come from their screen, not the visitor: the page in front with its headings, cards, FAQs and ticket links. Never read them out; use them.
- Always answer. A reply with no words leaves the visitor in silence.

# Spanish or English
You speak Spanish as a native of Latin America, and English. The call starts in Spanish unless the visitor chose English.
- Answer in the language the visitor speaks to you. If they speak English, answer in English from that reply on; if they go back to Spanish, so do you. Your voice follows the language you write.
- Except when they chose a language: a line in square brackets says so. Then answer in that language whatever they speak, even when they speak the other one, until they ask you to switch.
- When they ask for the other language in words that are not already it ("¿Puedes hablar en inglés?", "Can we speak Spanish?"), answer in that language and call set_language in the same response. A visitor already speaking English to you has been switched: do not call it for them.
- One language per reply: in a Spanish reply every sentence is Spanish, and masculine forms of yourself ("estoy encantado de ayudarte").
- Your Spanish is neutral Latin American Spanish, warm and natural for a Chilean visitor, never the Spanish of Spain and never heavy slang.
  - Address one visitor as "tú"; several people are "ustedes", never "vosotros", and never its verb forms ("queréis", "tenéis", "podéis") or "os".
  - Use Latin American words: "estacionamiento", never "aparcamiento" or "parking" as a Spanish word; "auto", never "coche"; "celular", never "móvil"; "boletos" or "entradas" (the site says "tickets"); "reservar"; "mostrar" ("te muestro"), not "enseñar"; "completar", not "rellenar"; "¿Qué día te queda bien?", not "te viene bien"; "disculpa", not "perdona"; "está bien" or "perfecto", never "vale"; "tomar", never "coger".
  - For something just done, use the simple past: "Abrí la página", "Ya te la mostré", not "He abierto".
- In Spanish too, write dates, times and prices as spoken words. Names stay as the site writes them: Santander Arena, Experiencias VIP, Santander Suites, Puntoticket.
- In English, say the site's Spanish names as they are written ("the Cúpula Santander Arena", "Experiencias VIP"), and explain them in a few words when they are not obvious.

# Every response starts with words
Write your answer, with its cues, first; any tool call comes at the end of the same response. What a page call returns reaches you only on your next turn.
- The exception is a read: read_topic, search_site and find_events come straight back to you within this same turn, but each one makes the visitor wait. Answer from what you know below, the events list and the site pages list whenever they cover it, which is most of the time. Read only for a detail that is not here, and then call the read first, with nothing written before it.
- Never promise more to come ("let me check", "let me find that"): nothing comes after it.

# What that sounds like
Visitor: "¿Qué conciertos hay?"
You: "{{page: /cartelera}} Hay muchos shows en camino. {{show: CAMILO}} Camilo llega el cinco de noviembre. {{show: NICKY JAM}} Y Nicky Jam cierra el año el cuatro de diciembre. ¿Te abro alguno de los dos?"
Visitor: "Camilo."
You: "{{page: /nuestra-cartelera/conciertos/camilo}} Gran elección. Camilo toca el cinco de noviembre a las nueve de la noche. Es parte de su gira mundial. ¿Te abro los tickets en Puntoticket?"
Visitor: "Yes please, and can I park there?"
You: "Sure. I've opened the tickets in a new tab. {{show: Comprar estacionamiento}} Parking is sold for each show, right here. Want me to open the parking too?" then open_tickets for Camilo's tickets.
Visitor: "What can we do before the show?"
You: "{{page: /}}{{show: Espacios para disfrutar en Santander Arena}} Plenty, inside the arena. {{show: Bares}} There are bars for a drink before the show. {{show: Terrazas}} The terraces are open air. {{show: Food trucks}} And food trucks if you're hungry. Want to see the bars?"

# What you know
- Today is {today:%A, %d %B %Y}, in Santiago. "Tonight", "this weekend" and "next month" are counted from today.
- Every fact — a date, a time, an experience, a bar, a gate, a rule, a price — comes from the knowledge below, a topic you read, a search result, the events list, or what the screen reported. Never from memory. If you cannot find it, say so, and say where on the site it might be, or offer the contact page.
- Ticket prices and availability are on Puntoticket, not on this site: never quote a price or say a show is sold out unless the site says so. Offer to open the tickets instead.
- Topics you can read with read_topic, when the knowledge below does not cover a question:
{_topics(k)}
- search_site finds a page, section, card or FAQ by its words. Its results name the page and section, which you can then cue.
- find_events finds shows by artist, genre, month or date, with each one's page.

# Moving the page
- Cue only a path from the site pages list, the events list or a search result, and only to headings and cards the lists or the screen give.
- The visitor can ask you to press or scroll to anything: "scroll down to the bars", "open that FAQ", "go back to the home page", "show me the Box". Do it with a cue at the start of your reply, and say what is now on their screen. Never say you cannot scroll or click.

# Tickets, parking and VIP
- Everything is bought on Puntoticket, the arena's only official ticket seller, in a new tab: tickets for a show, parking for a show, and VIP experiences. Call open_tickets with the show and what they want to buy, only when they ask to buy, or say yes to your offer. Say you opened it in a new tab, and that they finish the purchase there.
- A link that is not one show's — a reservation on the reservations or parking page — is open_tickets with the button's words, as the screen lists them under its ticket links.
- Never say a purchase is done: it happens on Puntoticket, where you are not.

# Tabs
- The visitor may have several Santander Arena tabs open. Lines in brackets tell you which tabs are open and which is in front. Your moves happen on the tab in front.
- "Go back to the other tab" is switch_tab with that tab's id.

# Santander Arena
{k.l1}

# Events coming up (soonest first; dates as the site writes them; the page is its path)
{_events_list(k, today)}

# Site pages
{_site_map(k)}
"""


# ─── Greeting ──────────────────────────────────────────────────────────────────

_INTRO: dict[Lang, str] = {
    "en": f"Hi, I'm {AGENT_NAME}, your guide to Santander Arena.",
    "es": f"Hola, soy {AGENT_NAME}, tu guía de Santander Arena.",
}
_GREETING: dict[Lang, str] = {
    "en": "I can tell you what's on, show you the experiences, or help you plan your night. "
    "What are you looking for?",
    "es": "Te cuento qué shows vienen, te muestro las experiencias, o te ayudo a planear "
    "tu noche. ¿Qué estás buscando?",
}
#: The opener's second sentence for the page the call starts on, by a word in
#: its path; the first match wins, and anything else gets the plain greeting.
_OPENERS: tuple[tuple[str, dict[Lang, str]], ...] = (
    (
        "cartelera",
        {
            "en": "Tell me what music you like, and I'll find you a show.",
            "es": "Cuéntame qué música te gusta, y te busco un show.",
        },
    ),
    (
        "experiencias",
        {
            "en": "I can walk you through the VIP experiences. Is it for a special occasion?",
            "es": "Te muestro las experiencias VIP. ¿Es para una ocasión especial?",
        },
    ),
    (
        "suites",
        {
            "en": "I can tell you all about the suites. How many people would come?",
            "es": "Te cuento todo sobre las suites. ¿Cuántas personas vendrían?",
        },
    ),
    (
        "estacionamiento",
        {
            "en": "I can help you park for your show. Which show are you coming to?",
            "es": "Te ayudo a estacionar para tu show. ¿A qué show vienes?",
        },
    ),
    (
        "como-llegar",
        {
            "en": "I can help you get here. Are you coming by car or by public transport?",
            "es": "Te ayudo a llegar. ¿Vienes en auto o en transporte público?",
        },
    ),
    (
        "preguntas-frecuentes",
        {
            "en": "Ask me anything, and I'll open the answer for you.",
            "es": "Pregúntame lo que quieras, y te abro la respuesta.",
        },
    ),
)
_EVENT_GREETING: dict[Lang, str] = {
    "en": "Shall I tell you about {name}, or help you plan your night?",
    "es": "¿Te cuento sobre {name}, o te ayudo a planear tu noche?",
}


def greeting(path: str | None, lang: Lang = OPENING, k: Knowledge | None = None) -> str:
    """The written opener, in ``lang``, tailored to the page the call starts on."""
    here = canonical_path(path or "/")
    event = (k or kb.KNOWLEDGE).events.get(here)
    if event is not None:
        return f"{_INTRO[lang]} {_EVENT_GREETING[lang].format(name=_spoken_name(event.name))}"
    line = next((lines[lang] for word, lines in _OPENERS if word in here), _GREETING[lang])
    return f"{_INTRO[lang]} {line}"


def _spoken_name(name: str) -> str:
    """A show's name as a sentence carries it: the site writes them in capitals."""
    return name.title() if name.isupper() else name


# ─── Written lines for moves ───────────────────────────────────────────────────

#: His line for a silent turn, by what moved: "shown" for anything else.
_LANDED: dict[str, dict[Lang, str]] = {
    "shown": {"en": "Here it is.", "es": "Aquí lo tienes."},
    "tickets": {
        "en": "I've opened it on Puntoticket in a new tab.",
        "es": "Te lo abrí en Puntoticket en una pestaña nueva.",
    },
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
#: Higher than SendPotion's 0.75: every page here is a full load, and the nod
#: is what the visitor hears while the next page comes in.
ACK_RATE = 0.9
ACK_HOLD_AFTER_S = 4.0
_ACK_HOLD: dict[Lang, tuple[str, ...]] = {
    "en": ("One moment.", "Just a moment."),
    "es": ("Un momento.", "Un momentito."),
}
_ACK_SORRY: dict[Lang, str] = {
    "en": "Sorry, that's taking a little longer.",
    "es": "Disculpa, está tardando un poco más.",
}
#: A visitor's ordinary words about the arena, so the reading trusts them.
_ACK_WORDS = Vocabulary(
    common=frozenset(
        # A word list reads as words, so it stays a split string.
        """santander arena concert concerts concierto conciertos show shows ticket tickets
        entradas boletos puntoticket vip suite suites box parking estacionamiento
        estacionamientos bar bares terraza terrazas food trucks cupula cúpula cartelera
        experiencia experiencias metro reserva reservas fans
        """.split()  # noqa: SIM905
    ),
)


def _avatar_state(session: Session, state: Literal["WORKING"] | None) -> None:
    """The talking head's working latch: held until speech owed has played."""
    session.send_rtvi(RTVIType.SERVER_MESSAGE, {"type": "avatar", "cmd": "state", "state": state})


_HEADINGS_IN_NOTE = 40
_CARDS_IN_NOTE = 40
_FAQS_IN_NOTE = 60
_TICKETS_IN_NOTE = 12
_SEARCH_HITS = 6
_EVENT_HITS = 8


async def _silence() -> AsyncGenerator[Any, None]:
    for _ in ():
        yield


def _clip(items: list[str] | tuple[str, ...], most: int) -> str:
    more = f"; and {len(items) - most} more" if len(items) > most else ""
    return "; ".join(items[:most]) + more


def _match(want: str, options: list[str] | tuple[str, ...]) -> str | None:
    """The option ``want`` names: the same words, else the one it begins, else
    the one it is inside — how the page itself matches. Case, accents and
    punctuation do not count: "cupula" is "Cúpula"."""

    def folded(s: str) -> str:
        return " ".join(re.sub(r"[^\w\s]", " ", norm(s)).split())

    w = folded(want)
    if not w:
        return None
    pairs = [(folded(o), o) for o in options]
    for test in (
        lambda o: o == w,
        lambda o: o.startswith(w),
        lambda o: w.startswith(o) and len(o) > len(w) // 2,
        lambda o: w in o,
    ):
        if (hit := next((o for f, o in pairs if f and test(f)), None)) is not None:
            return hit
    return None


#: The page for what the visitor asked about, when his reply forgets to show
#: it: on SendPotion he described a page twice with the screen left where it
#: was, until the visitor said they could not see it. Matched on their own
#: words, English or Spanish, folded; a specific page beats a general one, and
#: among specific ones the first named wins. A path the crawl does not have is
#: skipped where it is used.
_ASKED_PAGES: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(rf"\b(?:{words})", re.IGNORECASE), path)
    for words, path in (
        (r"suites?\b", "/santander-suites"),
        (r"\bbox\b|palco", "/box"),
        (r"vip\b|experienc|premium|pre[- ]?show", "/experiencias"),
        (r"cupula|dome\b", "/cupula-santander-arena"),
        (r"muro|wall of moments|momentos en vivo", "/muro-de-momentos-en-vivo"),
        (r"paseo de las estrellas|walk of fame|estrellas\b", "/paseo-de-las-estrellas"),
        (r"arena fans|fan zone|fans\b", "/arena-fans"),
        (r"bar(?:es|s)?\b|drink|trago|beber", "/bares"),
        (r"terraza|terrace", "/terrazas"),
        (r"food ?trucks?|comer\b|comida|food\b|eat\b|hungry|hambre", "/food-trucks"),
        (r"estacionamiento|estacionar|parking|park\b|car park|aparcar", "/estacionamientos"),
        (
            r"como llegar|get there|getting there|directions|metro\b|transport|"
            r"address|direccion|ubicacion|where is the arena|donde queda",
            "/como-llegar-a-santander-arena",
        ),
        # Not ticket outlets: the site's "Puntos de venta" is the Vive Snack food stands.
        (r"puntos? de venta|vive snack|snacks?\b", "/puntos-de-venta"),
        (
            r"objetos perdidos|lost and found|lost (?:my|a|an|something)|perdi\b",
            "/objetos-perdidos",
        ),
        (r"reserva|reservation|booking", "/reservas-santander-arena"),
        (r"sustentab|sustainab", "/sustentabilidad"),
        (r"trabaj|\bjobs?\b|careers?|unete|join the team|work (?:at|for)", "/unete-a-nosotros"),
        (r"contact|contacto", "/formulario-de-contacto"),
        (r"news|noticias", "/arena-news"),
        (r"about (?:the|santander) arena|sobre nosotros|history|historia", "/sobre-nosotros"),
        (r"faqs?\b|preguntas frecuentes|frequent questions", "/preguntas-frecuentes"),
        (
            r"cartelera|what'?s on|coming up|upcoming|concerts?\b|conciertos?|shows?\b|"
            r"eventos?\b|events?\b|que hay\b|proximos",
            "/cartelera",
        ),
    )
)
#: The billboard, which "show" and "events" name in passing.
_GENERAL_PAGE = "/cartelera"
#: A request to buy opens a Puntoticket tab, not a page of the site: on dev
#: "Open the tickets for Camilo" also loaded Camilo's page behind the new tab.
_BUYING = re.compile(
    r"\b(?:tickets?|entradas?|boletos?|comprar?|compro|buy|purchase|book)\b", re.IGNORECASE
)
_ASKED_TAB = re.compile(r"\b(?:tabs?|pestanas?)\b", re.IGNORECASE)

# A request about the call's own language: a verb of speaking, addressed to him
# ("can you", "let's") or said by him ("I can", "volvemos"), and the language.
# On SendPotion "Hey, can you speak in Spanish?" opened the languages page
# while he talked about something else.
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
    """Whether ``text`` asks him to speak another language — a request about
    this call, not a question about the arena."""
    return bool(_CALL_LANGUAGE.search(text) and _TO_HIM.search(text))


def named_event(text: str, k: Knowledge) -> Event | None:
    """The show ``text`` names, by the whole of its name (folded), or ``None``.
    The longest name wins, so "La Oreja de Van Gogh" is not "La"."""
    said = f" {' '.join(re.findall(r'[a-z0-9]+', fold(text)))} "
    best: Event | None = None
    for e in k.events.values():
        name = " ".join(re.findall(r"[a-z0-9]+", fold(e.name)))
        if len(name) >= 4 and f" {name} " in said and (best is None or len(name) > len(best.name)):
            best = e
    return best


def asked_page(text: str, k: Knowledge | None = None) -> str | None:
    """The site page for what ``text`` asks about, or ``None``: a show it
    names, else the page its words are about. "The other tab" is a tab to
    switch to, and "can you speak English?" is about this call: neither is a
    page."""
    if _ASKED_TAB.search(fold(text)) or asks_call_language(text) or _BUYING.search(fold(text)):
        return None
    if (event := named_event(text, k or kb.KNOWLEDGE)) is not None:
        return event.path
    said = fold(text)
    # Where it is named, the longer name first at one place ("box office" is
    # not the Box); the billboard only when nothing more specific is named, as
    # "show me the bars" names it too.
    named = [
        (m.start(), m.start() - m.end(), path)
        for rx, path in _ASKED_PAGES
        if (m := rx.search(said))
    ]
    specific = [n for n in named if n[2] != _GENERAL_PAGE]
    return min(specific or named)[2] if named else None


# ─── The section a sentence describes ──────────────────────────────────────────
#
# What he says, sentence by sentence, matched against the sections of the one
# page in front — never the whole site. A heading word counts for more than a
# word of the section's text, a word every section shares for little, and a
# sentence that is not clearly about one section moves nothing. The site is in
# Spanish: an English sentence mostly matches nothing here, which is the safe
# way to fail, and his own cues carry those replies.

_STOP = frozenset(
    # English and Spanish words that name no section.
    """a an the and or but of to in on for with by at from as is are was were be been it its
    this that these those you your yours we our us they their them he she his her i me my
    can will just also so then than too very here there what which who how when where why all
    any each every more most some such no not only own same into out up down over under again
    once about after before both few other per via do does did have has had get gets got make
    makes made use uses used like let lets want would shall could should see show shows one two
    three section page el la los las un una unos unas de del y o u en por para con sin que se
    su sus es son al lo le les como mas muy tu te ti mi nos este esta estos estas ese esa eso
    hay ser esta estan tiene tienen puedes puede quieres aqui alli tambien pero cuando donde
    santander arena""".split()  # noqa: SIM905
)
#: How sure a match must be: its score, and its lead over the runner-up — the
#: SendPotion guide's, tuned on its calls.
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
        _stem(w) for w in re.findall(r"[a-z0-9']+", fold(text)) if len(w) > 2 and w not in _STOP
    ]


def best_section(sentence: str, sections: list[tuple[str, str]]) -> str | None:
    """The heading of the one section ``sentence`` is about, of ``sections``
    (heading, text) on one page; ``None`` unless it is clearly one."""
    if sentence.rstrip().endswith("?"):
        return None  # The closing offer: about what comes next, not this page.
    # A heading he says outright is the one, however short the sentence; the
    # longest, when he says two.
    said = " ".join(re.findall(r"[a-z0-9']+", fold(sentence)))
    quoted = [
        h
        for h, _ in sections
        if h
        and len(phrase := re.findall(r"[a-z0-9']+", fold(h))) >= 2
        and re.search(rf"\b{re.escape(' '.join(phrase))}\b", said)
    ]
    if quoted:
        return max(quoted, key=len)
    if len(sentence.split()) < _SECTION_MIN_WORDS:
        return None  # A few words: about no one section.
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


def _on_page(words: str, page: Page) -> bool:
    """Whether ``words`` are on ``page`` as the crawl read it: its text, its
    sections, its cards, its buttons."""
    want = norm(words)
    if not want:
        return False
    parts = [page.title, page.text, *(f"{s.heading} {s.text}" for s in page.sections)]
    parts += [c.title for c in page.cards] + [t.label for t in page.tickets]
    return any(want in norm(p) for p in parts)


def named_card(sentence: str, cards: list[str] | tuple[str, ...]) -> str | None:
    """A card the sentence names by its whole title — a show, a bar, an
    experience — to ring; the longest, when it names two; ``None`` for none.
    Titles of a single short word ("Box") count only when written as a name."""
    said = f" {' '.join(re.findall(r'[a-z0-9]+', fold(sentence)))} "
    best: str | None = None
    for card in cards:
        words = re.findall(r"[a-z0-9]+", fold(card))
        name = " ".join(words)
        if len(name) < 3 or f" {name} " not in said:
            continue
        # The site writes a show in capitals, and he says "Camilo".
        as_name = {card.strip(), _spoken_name(card.strip())}
        if len(words) == 1 and not any(
            re.search(rf"\b{re.escape(n)}\b", sentence) for n in as_name
        ):
            continue
        if best is None or len(name) > len(best):
            best = card
    return best


# ─── The brain ─────────────────────────────────────────────────────────────────


class SantanderBrain(GeminiBrain):
    """One per session. Javier: Santander Arena's knowledge, its pages and
    events, and a mirror of the visitor's tabs, in Spanish or English."""

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
        #: The language he speaks now, and the toggle's written confirmation
        #: of a switch, said at the start of his next turn.
        self.spoken: Lang = OPENING
        #: Whether the visitor chose the language, which then holds whatever
        #: they speak; until they do, it follows what they speak.
        self._chosen = False
        self._confirm: str | None = None
        self._fallback = FallbackLine()
        self._ack = Acknowledger(
            _ACK_LINES, _ACK_HOLD, _ACK_SORRY, _ACK_WORDS, ACK_RATE, ACK_HOLD_AFTER_S
        )
        #: The tab in front as it last reported itself, and whether the model
        #: has seen it since it changed.
        self.page: PageChanged | None = None
        self._path = "/"
        self._page_unseen = False
        #: Every open Santander Arena tab, and which is in front.
        self.tabs: list[TabInfo] = []
        self._active = ""
        self._tabs_unseen = False
        #: The page this turn's cues are on: the one in front, then wherever a
        #: ``{page: …}`` cue took it.
        self._cue_path = "/"
        self._idle_short = False
        self._nudges = 0
        #: The page for what the visitor last asked about, shown at the start
        #: of his reply if it has no cue of its own; see :func:`asked_page`.
        self._backstop: str | None = None
        #: This reply's moves so far: whether one opened a page, and what was
        #: last rung, so a sentence on the same section does not ring it again.
        self._paged = False
        self._shown: str | None = None

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        init = session.init or {}
        self._path = canonical_path(str(init.get("path") or "/"))
        # The page sends `lang` only once the visitor has pressed the toggle.
        chosen = init.get("lang")
        self._chosen = chosen in LANGUAGE_NAMES
        self.spoken = "en" if chosen == "en" else OPENING
        # His own voice, settled here and not by the page. Both language legs
        # move together; what he hears, the toggle and `set_language` move them
        # again.
        await session.configure(
            Config(
                stt=SttConfig(language=self.spoken, patience=SANTANDER_PATIENCE),
                tts=TtsConfig(voice=VOICE, language=self.spoken),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
            )
        )
        logger.info(
            "santanderarena: session start on {} in {}{}",
            self._path,
            self.spoken,
            " (chosen)" if self._chosen else "",
        )
        if self._chosen:
            self._note(_chosen_note(self.spoken, "before the call"))

    async def greet(self, session: Session) -> str:
        """The opener, written not generated."""
        return greeting(self._path, self.spoken, self.kb)

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
            logger.info("santanderarena: language -> {} (heard)", heard)
        self._nudges = 0
        # A reply cut off before it said a word keeps its page for the next one.
        # A request to switch language shows nothing, not even that page.
        self._backstop = (
            None
            if asks_call_language(msg.text)
            else asked_page(msg.text, self.kb) or self._backstop
        )
        self._restore_idle()
        self._read_in_screen()
        now = time.monotonic()
        fragment, self._heard_at = now - self._heard_at < _FRAGMENT_S, now
        if not fragment and (nod := self._ack.line(msg.text, self.spoken)) is not None:
            logger.info("santanderarena: ack {!r}", nod)
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
        """A quiet spell — the only floor he gets without the visitor speaking:
        the toggle's confirmation when one is owed, else a nudge, twice, then
        silence."""
        self._restore_idle()
        self._backstop = None
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
                "Speak into the quiet, briefly, as the host beside them would: one useful thing "
                "about what is on their screen, or one question that helps you plan their night. "
                "Never ask whether they are still there, and never repeat your last line."
            )
        else:
            ask = (
                "Still quiet. One last, light offer, different from your last: a show coming up, "
                "or something you could show them for their night. Then let them browse."
            )
        self._note(f"{quiet} {ask}")
        return self.respond(session)

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The model's turn, with its screen cues taken out of the speech and
        sent to the page (:mod:`.cues`).

        If it moved the page and said nothing, the model is asked once more with
        tools off, so he talks about what he just showed; only if that is silent
        too does he say a written line of his own. A turn that came back with
        nothing at all is asked once more the same way.

        A language switched on the toggle is confirmed first, in the new
        language. A unit is opened only once its first words are known, so the
        voice follows the language the model chose to write in."""
        if (line := self._confirm) is not None:
            self._confirm = None
            async for event in say_line(self, line):
                yield event
        self._cue_path = self._path
        self._paged = False
        self._shown = None
        spoke = False
        turn = self._fallback.speak_if_silent(
            self, super().respond(session), again=lambda: self._talk_now(session)
        )
        async for event in self._spelled(self._written(session, self._cued(turn))):
            spoke = spoke or isinstance(event, SpeechStart)
            yield event
        if not spoke:
            logger.warning("santanderarena: the model returned nothing; asking once more")
            again = self._written(session, self._cued(self._talk_now(session)))
            async for event in self._spelled(again):
                yield event

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
                logger.info("santanderarena: language -> {} (written)", written)
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
        """``turn`` with every ``{page|show|faq: …}`` taken out of its text and
        sent to the page as a :class:`Cue`, anchored to the words before it."""
        parser = CueParser(self._auto_cues)
        try:
            async for event in turn:
                if isinstance(event, SpeechStart):
                    parser = CueParser(self._auto_cues)
                elif isinstance(event, SpeechChunk):
                    text, raw = parser.feed(self._with_backstop(event.text))
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
        if "{" in chunk or path == self._path or self.kb.page(path) is None:
            return chunk
        logger.info("santanderarena: the reply has no cue; showing {} first", path)
        return f"{{page: {path}}}{chunk}"

    def _send_cue(self, raw: RawCue) -> None:
        """Check a cue against the site, as the tools do, and send it; one that
        names nothing real is dropped and logged rather than reaching the page."""
        cue = self._resolve_cue(raw)
        logger.info("santanderarena: cue {} {!r} at {!r} -> {}", raw.kind, raw.value, raw.at, cue)
        if cue is not None:
            self._paged = self._paged or raw.kind == "page"
            if raw.kind == "show":
                self._shown = cue.heading or cue.text
            self.session.dispatch(cue)

    def _auto_cues(
        self, sentence: str, index: int, placed: tuple[tuple[CueKind, str], ...]
    ) -> list[tuple[CueKind, str]]:
        """The moves a sentence of his needs and did not bring (see
        :mod:`.cues`): the page its first sentence is about, when nothing has
        opened one, and the section or card on the page it describes."""
        out: list[tuple[CueKind, str]] = []
        kinds = {k for k, _ in placed}
        # A page the model opens on this very sentence is not sent yet.
        pages = [p.path for k, v in placed if k == "page" and (p := self.kb.page(v)) is not None]
        path = pages[-1] if pages else self._cue_path
        if index == 0 and not self._paged and "page" not in kinds:
            asked = asked_page(sentence, self.kb)
            if asked is not None and asked != self._path and self.kb.page(asked) is not None:
                logger.info("santanderarena: he talks about {} with no cue; opening it", asked)
                out.append(("page", asked))
                path = asked
        # The rest of the reply is on this page, though the cue that opens it
        # may not be sent until several sentences have come in one chunk.
        self._cue_path = path
        if kinds & {"show", "faq"}:
            return out
        page = self.kb.page(path)
        faqs = [(f.q, f.a) for f in page.faqs] if page is not None else []
        if faqs and (question := best_section(sentence, faqs)) is not None:
            # An answer read off the FAQ page: on dev, "kids pay from two"
            # opened the page and rang nothing.
            if question != self._shown:
                self._shown = question
                out.append(("faq", question))
            return out
        shown = self._section_for(sentence, path)
        if shown is not None and shown != self._shown:
            out.append(("show", shown))
        return out

    def _section_for(self, sentence: str, path: str) -> str | None:
        """The heading or card on ``path`` that ``sentence`` is about."""
        page = self.kb.page(path)
        live = self.page is not None and canonical_path(self.page.path) == path
        cards = list(self.page.cards) if live and self.page is not None else []
        if page is not None:
            cards += [c.title for c in page.cards]
            heading = best_section(sentence, [(s.heading, s.text) for s in page.sections])
            if heading is not None:
                return heading
        return named_card(sentence, list(dict.fromkeys(cards)))

    def _resolve_cue(self, raw: RawCue) -> Cue | None:
        if raw.kind == "page":
            page = self.kb.page(raw.value)
            if page is None:
                return None
            self._cue_path = page.path
            return Cue(at=raw.at, word=raw.word, path=page.path)
        target = self.kb.page(self._cue_path)
        moved = self._cue_path != self._path
        if raw.kind == "faq":
            faqs = [f.q for f in target.faqs] if target else list(self._faqs())
            if not moved:
                faqs = list(dict.fromkeys([*self._faqs(), *faqs]))
            question = _match(raw.value, faqs)
            if question is None:
                found = self._faq_elsewhere(raw.value)
                if found is None:
                    return None
                self._cue_path, question = found
                return Cue(at=raw.at, word=raw.word, path=found[0], faq=question)
            path = self._cue_path if moved else None
            return Cue(at=raw.at, word=raw.word, path=path, faq=question)
        # show: a heading of the page the visitor will be on, else a card's
        # title or those words, which the page finds itself.
        headings = (
            target.headings
            if moved and target
            else self._headings() or (target.headings if target else ())
        )
        heading = _match(raw.value, headings)
        text = None
        if heading is None:
            cards = [c.title for c in target.cards] if target else []
            if not moved and self.page is not None:
                cards = [*self.page.cards, *cards]
            text = _match(raw.value, cards)
            if text is None and target is not None and not _on_page(raw.value, target):
                # Words the page does not have: on dev he cued "DESCRIPCIÓN" on
                # a show's page, which has none, and the page reported a miss.
                logger.info("santanderarena: {!r} is not on {}; dropped", raw.value, target.path)
                return None
            text = text or raw.value[:120]
        path = self._cue_path if moved else None
        return Cue(at=raw.at, word=raw.word, path=path, heading=heading, text=text)

    def _talk_now(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The one extra request a silent page move gets: tools declared, none callable."""
        return self.respond_with(session, tools=ToolChoice.NONE)

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
            logger.info("santanderarena: {} called with flat arguments; wrapping them", call.name)
            call = call.model_copy(update={"args": {"request": args}})
        return await super()._run(tool, call)

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Page→brain events, folded in silently: no floor taken, no turn."""
        event = SANTANDER_EVENTS.parse(msg)
        if event is None:
            return
        logger.info("santanderarena: {} — {}", type(event).__voqal_event__, event)
        if isinstance(event, LanguageRequested):
            await self._requested(session, event)
            return
        if (note := self.apply_event(event)) is not None:
            self._note(note)

    async def _requested(self, session: Session, event: LanguageRequested) -> None:
        """The visitor pressed the other language on the toggle. Switched in
        code, not through the model: both legs move in one awaited request, and
        the written confirmation is said in his next turn — which, if they stay
        quiet, is the short quiet spell :meth:`on_user_idle` turns into it."""
        if event.language == self.spoken:
            return
        was = self.spoken
        try:
            await session.configure(self._speaking(event.language))
        except RequestRejected as rejected:
            logger.warning("santanderarena: switch to {} refused: {}", event.language, rejected)
            self.spoken = was
            session.dispatch(LanguageChanged(language=was))
            return
        logger.info("santanderarena: language -> {} (toggle)", event.language)
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
            stt=SttConfig(language=language, patience=SANTANDER_PATIENCE),
            tts=TtsConfig(voice=VOICE, language=language),
        )

    # ─── Page → brain ───────────────────────────────────────────────────

    def apply_event(self, event: SantanderEvent) -> str | None:
        """Patch the mirror; return the line the model should see."""
        match event:
            case PageChanged():
                self.page = event
                self._path = canonical_path(event.path)
                self._page_unseen = True
                # Read in with their next message or quiet spell: they may click
                # on before they speak, and only the last page matters.
                return None
            case TabsChanged():
                self.tabs = event.tabs
                self._active = event.active
                self._tabs_unseen = True
                return None
            case LanguageRequested():
                # Switched by on_rtvi before it gets here: a toggle is not a note.
                return None
            case CommandFailed() if event.command == "cue":
                # He has already spoken past it: the next turn should not claim
                # it is on screen, nor stop to apologise for a scroll.
                return (
                    f"[A screen cue of yours did not land ({event.reason}). If the visitor "
                    "asks where it is, show it again; otherwise carry on.]"
                )
            case CommandFailed():
                return (
                    f"[That did not happen on the page ({event.command}: {event.reason}). "
                    "Tell the visitor plainly and offer what you can do instead; never say it "
                    "worked.]"
                )

    def _read_in_screen(self) -> None:
        """The tabs and the page in front, once per change, ahead of what they say."""
        if self._tabs_unseen and len(self.tabs) > 1:
            listed = "; ".join(
                f"{t.tab_id}: {t.title or t.url}"
                + (" (in front)" if t.tab_id == self._active else "")
                for t in self.tabs
            )
            self._note(f"[The visitor's open Santander Arena tabs — {listed}.]")
        self._tabs_unseen = False
        if not self._page_unseen or self.page is None:
            return
        self._page_unseen = False
        p = self.page
        where = {"event": "a show's page", "news": "a news story", "home": "the home page"}.get(
            p.kind, "a page"
        )
        note = f"[The tab in front shows {where}: “{p.title or p.path}” ({p.path})."
        if p.headings:
            note += f" Its headings: {_clip(p.headings, _HEADINGS_IN_NOTE)}."
        if p.cards:
            note += f" Its cards: {_clip(p.cards, _CARDS_IN_NOTE)}."
        if p.faqs:
            note += f" Its FAQs: {_clip(p.faqs, _FAQS_IN_NOTE)}."
        if p.tickets:
            links = [f"{t.label or 'link'}" + (f" ({t.near})" if t.near else "") for t in p.tickets]
            note += f" Its ticket links: {_clip(links, _TICKETS_IN_NOTE)}."
        self._note(note + "]")

    def _note(self, text: str) -> None:
        self.append_to_context(types.Content(role="user", parts=[types.Part(text=text)]))

    def _restore_idle(self) -> None:
        if self._idle_short:
            self._idle_short = False
            configure_soon(self.session, Config(idle=IdleConfig(timeout_ms=_IDLE_MS)))

    def _move(self, action: Action, line: str = "shown") -> None:
        """Dispatch ``action``, with the written line for it (one of
        :data:`_LANDED`, in the language he speaks) should the turn say nothing."""
        self.session.dispatch(action)
        landed(_LANDED[line][self.spoken])

    def _headings(self) -> tuple[str, ...]:
        if self.page is not None:
            return tuple(self.page.headings)
        page = self.kb.page(self._path)
        return page.headings if page else ()

    def _faqs(self) -> tuple[str, ...]:
        if self.page is not None:
            return tuple(self.page.faqs)
        page = self.kb.page(self._path)
        return tuple(f.q for f in page.faqs) if page else ()

    def _faq_elsewhere(self, asked: str) -> tuple[str, str] | None:
        """The page and FAQ ``asked`` names: by its words on any page, else the
        best FAQ search hit."""
        for page in self.kb.pages.values():
            if (q := _match(asked, [f.q for f in page.faqs])) is not None:
                return page.path, q
        for hit in self.kb.search(asked, 4):
            if hit.kind == "faq" and hit.path is not None:
                return hit.path, hit.title
        return None

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        """Read and search the arena's knowledge and billboard, open what the
        visitor buys on Puntoticket, move between their tabs, switch language."""
        return [
            self.read_topic,
            self.search_site,
            self.find_events,
            self.open_tickets,
            self.switch_tab,
            self.set_language,
        ]

    @needs_result_now
    async def read_topic(self, request: TopicRequest) -> str:
        """Read one of Santander Arena's knowledge topics before answering from it."""
        topic = self.kb.topics.get(request.topic)
        if topic is None:
            return f"No topic '{request.topic}' is written yet: use search_site."
        return topic.text

    @needs_result_now
    async def search_site(self, request: SearchRequest) -> str:
        """Search santanderarena.cl's pages, sections, cards and FAQs. Each
        result names the page path and the heading or card to take them to."""
        hits = self.kb.search(request.query, _SEARCH_HITS)
        if not hits:
            return (
                f"Nothing on santanderarena.cl matches '{request.query}'. Try find_events, "
                "or other words in Spanish."
            )
        out: list[str] = []
        for h in hits:
            if h.kind == "faq":
                out.append(f"[FAQ on {h.path}] {h.title}\n  {h.snippet}")
            elif h.kind == "card":
                out.append(f"[card on {h.path}] {h.title}\n  {h.snippet}")
            else:
                where = f", heading: {h.section}" if h.section else ""
                out.append(f"[page] {h.title} — path: {h.path}{where}\n  {h.snippet}")
        return "\n".join(out)

    @needs_result_now
    async def find_events(self, request: EventsRequest) -> str:
        """Find shows on Santander Arena's billboard by artist, genre, month or
        date, soonest first when nothing narrower is asked. Each names its date,
        its page path and what can be bought for it."""
        today = datetime.now(TIMEZONE).date().isoformat()
        events = list(self.kb.events.values())
        if not events:
            return "No events are loaded. Open /cartelera and read its cards from the screen."
        month = _month_of(request.query)
        if month is not None:
            found = [e for e in events if e.date[5:7] == f"{month:02d}"]
        else:
            hits = self.kb.find_events(request.query, _EVENT_HITS) if request.query else []
            found = [e for h in hits if h.path and (e := self.kb.events.get(h.path))]
        if not found:
            found = events
            # An empty query asked for everything, and matched nothing by it.
            lead = (
                f"No show matches '{request.query}'. Everything coming up:\n"
                if request.query.strip()
                else ""
            )
        else:
            lead = ""
        coming = sorted(
            (e for e in found if not e.date or e.date >= today), key=lambda e: e.date or "9999"
        )
        lines: list[str] = []
        for e in coming[:_EVENT_HITS]:
            buy = [
                k
                for k, u in (
                    ("tickets", e.tickets_url),
                    ("parking", e.parking_url),
                    ("vip", e.vip_url),
                )
                if u
            ]
            line = f"- {e.name} — {e.when or 'date not given'} — path: {e.path}"
            line += f" — can open: {', '.join(buy)}" if buy else ""
            if e.summary:
                line += f"\n  {e.summary}"
            lines.append(line)
        if not lines:
            return f"{lead}Nothing coming up from today on matches. Offer /cartelera."
        return lead + "\n".join(lines)

    async def open_tickets(self, request: TicketsRequest) -> str:
        """Open, in a new tab on Puntoticket, the tickets, parking or VIP
        experience for a show, or a reservation link on the page in front. Only
        when the visitor asks to buy or says yes. In the same response, say you
        opened it and that they finish the purchase there."""
        url, label = self._ticket_link(request)
        if url is None:
            return label
        self._move(OpenTickets(url=url, label=label), "tickets")
        return f"Opened '{label}' on Puntoticket in a new tab. The visitor buys there."

    def _ticket_link(self, request: TicketsRequest) -> tuple[str | None, str]:
        """The link to open and its label, or ``None`` and why not."""
        kind_label = {
            "tickets": "Comprar tickets",
            "parking": "Comprar estacionamiento",
            "vip": "Compra Experiencias VIP",
        }[request.kind]
        live = list(self.page.tickets) if self.page is not None else []
        if request.event:
            event = self.kb.event(request.event)
            here = self._event_here()
            if event is None and here is not None and _same_show(request.event, here.name):
                event = here
            if event is not None:
                url = {
                    "tickets": event.tickets_url,
                    "parking": event.parking_url,
                    "vip": event.vip_url,
                }[request.kind]
                on_page = self.page is not None and canonical_path(self.page.path) == event.path
                if on_page:
                    # The page in front is that show's: its own button is the truth.
                    url = self._live_ticket(live, kind_label) or url
                if url:
                    return url, f"{kind_label} — {_spoken_name(event.name)}"
                return None, (
                    f"Not opened: {event.name}'s page has no '{kind_label}' link. Say so, and "
                    f"offer to open its page ({event.path})."
                )
            if (url := self._live_ticket(live, request.event)) is not None:
                return url, request.event
            known = ", ".join(e.name for e in self.kb.events.values()) or "none loaded"
            return None, f"Not opened: no show '{request.event}'. Shows: {known}. Use find_events."
        if request.label and (url := self._live_ticket(live, request.label)) is not None:
            return url, request.label
        if (here := self._event_here()) is not None:
            return self._ticket_link(request.model_copy(update={"event": here.path}))
        if (url := self._live_ticket(live, kind_label)) is not None:
            return url, kind_label
        listed = "; ".join(t.label for t in live if t.label) or "none"
        return None, (
            f"Not opened: say which show. The page in front has these ticket links: {listed}."
        )

    def _event_here(self) -> Event | None:
        return self.kb.events.get(canonical_path(self.page.path)) if self.page else None

    def _live_ticket(self, live: list[Any], words: str) -> str | None:
        """A ticket link the page in front reported, by its label or the card it
        is on, and only one to a buying site the site itself links."""
        labels = [f"{t.label} {t.near}".strip() for t in live]
        hit = _match(words, labels)
        if hit is None:
            return None
        link = live[labels.index(hit)]
        url = str(link.url)
        known = self.kb.ticket_urls()
        if not is_ticket_url(url) and canonical_url(url) not in known:
            return None
        return url

    async def switch_tab(self, request: TabRequest) -> str:
        """Bring another of the visitor's Santander Arena tabs to the front."""
        tab = next((t for t in self.tabs if t.tab_id == request.tab_id), None)
        if tab is None:
            listed = ", ".join(f"{t.tab_id} ({t.title})" for t in self.tabs) or "none"
            return f"Not switched: no tab '{request.tab_id}'. Open tabs: {listed}."
        self._move(FocusTab(tab_id=tab.tab_id), "tab")
        return f"Brought '{tab.title or tab.url}' to the front."

    async def set_language(self, request: LanguageRequest) -> str:
        """Conduct the rest of the call in Spanish ('es') or English ('en'),
        listening and speaking. Call it when they ask for the other language in
        words that are not already it — "Can we speak Spanish?" — and to go
        back. Say one short line in the language you are switching to, in the
        same response. A visitor already speaking English has been switched: do
        not call it for them."""
        self._chosen = True
        configure_soon(self.session, self._speaking(request.language))
        logger.info("santanderarena: language -> {} (asked)", request.language)
        return "ok"


_MONTHS = {
    name: i + 1
    for i, names in enumerate(
        [
            ("january", "enero"),
            ("february", "febrero"),
            ("march", "marzo"),
            ("april", "abril"),
            ("may", "mayo"),
            ("june", "junio"),
            ("july", "julio"),
            ("august", "agosto"),
            ("september", "septiembre", "setiembre"),
            ("october", "octubre"),
            ("november", "noviembre"),
            ("december", "diciembre"),
        ]
    )
    for name in names
}


def _same_show(asked: str, name: str) -> bool:
    """Whether ``asked`` is ``name``, or part of it, or it of ``asked``."""
    a, n = norm(asked), norm(name)
    return bool(a and n) and (a in n or n in a)


def _month_of(query: str) -> int | None:
    """The month a query asks for when it is only a month ("noviembre", "in
    December"); ``None`` when it names anything more, which search handles."""
    words = re.findall(r"[a-z]+", fold(query))
    months = [_MONTHS[w] for w in words if w in _MONTHS]
    rest = [w for w in words if w not in _MONTHS and w not in ("in", "en", "de", "for", "the")]
    return months[0] if len(months) == 1 and not rest else None


__all__ = [
    "Cue",
    "FocusTab",
    "LanguageChanged",
    "Navigate",
    "OpenFaq",
    "OpenTickets",
    "SantanderBrain",
    "ShowSection",
]
