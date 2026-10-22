"""SaintGeorgeBrain — Javier, a guide on saintgeorge.cl.

The site is Saint George's College's, not ours: a school in Santiago, Chile,
from Pre-Kínder to 12º. A browser extension injects the widget and a small
adapter into it; the adapter turns each :class:`~voqalize.sdk.Action` below
into a move on the tab in front — a page, a section scrolled to and ringed, an
accordion opened by its button's words — and the call itself opens the
documents and links he hands over in a new tab. Every tab reports what it
shows as a typed event (:mod:`.app_events`), whoever moved it.

This is a port of the Santander Arena guide (``demos/santanderarena``), with
the later lessons of the Clini guide (``demos/clini``): the floor held after
the nod, talk-throughs that wait for his speech and run with tools off, and
one page move at a time.

**A guide for a family choosing a school.** Every turn answers what was asked,
in words: the answer, why it matters for their child, and a short offer of
the next step — the child's unit and grade, academics and English, formation,
admissions, a message to the admissions office.

**Every fact has a source.** A grade, a programme, a value or a contact is
spoken from L1 (in this prompt), an L2 topic he read, a search of the site, or
what the page itself reported. Never from memory.

**What changes is read live, in the visitor's browser.** The fees and the
admission status are read off the admission page, and the coming events off
the school's public calendar, by the extension while the call is on, and
reach him as events (:class:`~.app_events.FeesRead`,
:class:`~.app_events.EventsRead`). This brain runs far from Chile and the site
does not answer it; it never fetches the site or the calendar. He quotes a fee
or a date only from a read made during this call, and when a read fails he
says he cannot see it right now and shows the page.

**Never block on the page.** A tool dispatches the move and returns; the page
answers later, and he says what it did once his own speech is over, in a
short quiet spell, with tools off.

**Nothing on the page is invented, and nothing is sent for them.** A path,
a heading, an accordion and a link are checked against the crawl and what
the tab last reported. The site has no contact form: he gathers the parent's
details by voice and puts up a card with a ready email to admissions, which
the parent opens and sends themselves. He never submits, never logs in,
never types a RUT; the families' portals open in a new tab only when asked.

**The screen follows his voice**, through cues written into his reply
(:mod:`.cues`), carried across the site's full page loads by the extension.

**Spanish or English, as the visitor chose or speaks**, in neutral Latin
American Spanish with "tú". The voice is one man, recorded in each.
"""

from __future__ import annotations

import dataclasses
import inspect
import math
import random
import re
import time
from collections.abc import AsyncGenerator
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import quote
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
from voqalize_demos.acknowledge import (
    Acknowledger,
    Floor,
    Kind,
    Vocabulary,
    classify,
    hold_the_floor,
)

from voqalize.sdk import (
    Action,
    Finalize,
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
    SAINT_GEORGE_EVENTS,
    CommandDone,
    CommandFailed,
    ContactUsed,
    EventsRead,
    FeesRead,
    LanguageRequested,
    PageChanged,
    SaintGeorgeEvent,
    TabInfo,
    TabsChanged,
)
from .cues import CueKind, CueParser, RawCue, words
from .knowledge import (
    TOPIC_IDS,
    Knowledge,
    Page,
    canonical_path,
    canonical_url,
    fold,
    is_link_url,
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

#: Santiago, for "this week" and "next month", and the calendar's dates.
TIMEZONE = ZoneInfo("America/Santiago")

# ─── Voice and timing ──────────────────────────────────────────────────────────

#: Javier's voice: the speech tier's male persona recorded once in English and
#: once in Spanish, so a switch keeps the same man.
VOICE = Voice.OMNIVOICE_JAVIER

#: A quiet visitor is someone reading a page; a guide beside them says
#: something after a while, and not twice more.
_IDLE_MS = 20_000
_IDLE_NUDGES = 2
#: The idle window while something is owed — the page's answer to a move, a
#: toggle's confirmation: a visitor who reacts speaks first, one who is
#: reading hears it from him.
_TALK_THROUGH_MS = 2_000
#: A little more patience than the demos' default: a parent working out a
#: child's age and grade pauses mid-sentence.
SAINT_GEORGE_PATIENCE = PATIENCE + 2
#: A message this soon after the last one is the rest of the same thought.
_FRAGMENT_S = 4.0

# ─── Language ──────────────────────────────────────────────────────────────────

#: What he answers in, as the tag both legs of the call take. The recognizer
#: leg only follows the voice, as a pair; the language is decided here from
#: words: the visitor's, then his own.
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
    su sus nosotros vale bueno claro dónde donde cuál cual cuándo cuando hijo hija hijos
    años colegio curso cursos matrícula colegiatura admisión postular muéstrame dime
    explícame quiénes quién próximo próximos
    """.split()  # noqa: SIM905
)
_ENGLISH_WORDS = frozenset(
    """the is are was what how can could you your i i'm it it's this that these those do
    does show me my we our for with about and of to have has there here please want
    would like tell sure yes okay right of course let's son daughter school
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
    found = set(_LETTERS.findall(text.lower()))
    es = len(found & _SPANISH_WORDS) + (1 if _SPANISH_MARKS.search(text) else 0)
    en = len(found & _ENGLISH_WORDS)
    if es >= (2 if sure else 1) and es > en:
        return "es"
    if en >= (3 if sure else 2) and es == 0:
        return "en"
    return None


#: Latin America says "vi-DE-o"; Spain says "VÍ-deo". On the Clini guide's dev
#: calls the Spanish voice read plain "video" the Spain way one sentence in
#: three; spelled "bidéo" it said "vi-DE-o" every time (Spanish b and v are one
#: sound). So in Spanish the voice is handed "bidéo", and only the voice: the
#: page's word anchors follow the same spelling (``_anchor_for_voice``), and
#: what comes back as heard is spelled "video" again before it reaches the
#: model (``on_finalize``). The school's site has videos on its home and its
#: history page, so the word comes up.
_VIDEO_TO_VOICE = re.compile(r"\b([Vv])[ií]deo(s?)\b")
_VIDEO_FROM_VOICE = re.compile(r"\b([Bb])idéo(s?)\b")
#: "vídeo" as the page's words reads it: the accented letter splits the word.
_VIDEO_AS_WORDS = re.compile(r"\bv deo(s?)\b")


def for_the_voice(text: str) -> str:
    """Spanish ``text`` as the voice must read it to say "vi-DE-o"."""
    return _VIDEO_TO_VOICE.sub(
        lambda m: ("B" if m.group(1) == "V" else "b") + "idéo" + m.group(2), text
    )


def from_the_voice(text: str) -> str:
    """What the voice said, spelled as Latin America writes it."""
    return _VIDEO_FROM_VOICE.sub(
        lambda m: ("V" if m.group(1) == "B" else "v") + "ideo" + m.group(2), text
    )


def _anchor_for_voice(at: str) -> str:
    """A cue's anchor, in the page's words, for speech spelled :func:`for_the_voice`."""
    return " ".join(words(for_the_voice(_VIDEO_AS_WORDS.sub(r"video\1", at))))


#: A reply that only promises more ("One moment.", "Déjame ver.") says nothing.
_PROMISE = re.compile(
    r"\b(?:just |one |un )?(?:moment|momento|momentito|second|segundo)\b"
    r"|\blet me (?:see|check|look)(?: (?:that|into it|at that))?\b|\bdéjame ver\b|\ba ver\b",
    re.IGNORECASE,
)


def _chosen_note(language: Lang, how: str) -> str:
    name = LANGUAGE_NAMES[language]
    return (
        f"[The visitor chose {name} {how}. Answer in {name} from now on, whatever "
        "language they speak to you, until they ask for the other one.]"
    )


# ─── Actions (brain → page) ────────────────────────────────────────────────────


class Navigate(Action):
    """Go to one of the site's pages and, with ``heading`` or ``text``, scroll
    to that section and ring it; with ``faq``, open that accordion on it. The
    page loads in full and reports ``page_changed``."""

    path: str
    heading: str | None = None
    text: str | None = None
    faq: str | None = None


class Cue(Action):
    """A move for the page to make when the voice reaches ``at`` — the first
    words of the sentence it belongs to (see :mod:`.cues`); empty ``at`` is
    when the voice stops. With ``path``, it is a :class:`Navigate`; else a
    section, words or accordion on the tab in front."""

    at: str
    word: int = 0
    """Words of the unit before it, for a page that times cues by the clock."""
    path: str | None = None
    heading: str | None = None
    text: str | None = None
    faq: str | None = None


class ShowSection(Action):
    """On the tab in front, scroll to the heading named ``heading`` and ring its
    section; with ``text``, ring the smallest element containing that text."""

    heading: str | None = None
    text: str | None = None


class OpenFaq(Action):
    """Open the accordion whose button starts with ``question`` on the page in
    front, and ring it. The site's accordions are found by their words: their
    ids repeat from page to page."""

    question: str


class OpenLink(Action):
    """Open a document or a link of the site's in a new tab: a PDF, the
    musical's tickets, a families' portal. The visitor goes on there; the
    extension does nothing on that tab."""

    url: str
    label: str = ""


class ShowFees(Action):
    """Take the visitor to the admission page (``path``), ring its reference
    fees (``about="fees"``) or its admission status (``"admission"``), and
    read both off the page as it stands. The page answers ``fees_read``, or
    ``command_failed`` when it cannot find them."""

    path: str
    about: Literal["fees", "admission"] = "fees"


class ShowEvents(Action):
    """Read the school's public calendar in the visitor's browser and take
    them to the calendar page (``path``), with the calendar ringed. The page
    answers ``events_read`` with the next ``count`` events, or
    ``command_failed``."""

    path: str
    count: int = 30


class ShowContactCard(Action):
    """Put up a card over the page with an email to admissions, written out
    and ready — ``to``, ``subject``, ``body``, in ``language`` — and the
    admissions phone. The parent presses its button to open the email in their
    own mail app and sends it themselves: nothing is sent from the card. The
    page answers ``command_done`` once it is up, and ``contact_used`` when a
    button is pressed."""

    to: str
    subject: str
    body: str
    phone: str
    language: Literal["en", "es"]


class FocusTab(Action):
    """Bring one of the visitor's Saint George's tabs to the front."""

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
        "'Cambridge', 'casino', 'lista de materiales', 'Programa Moreau', 'uniforme'."
    )


class FeesRequest(BaseModel):
    about: Literal["fees", "admission"] = Field(
        default="fees",
        description="'fees' for the reference fees (incorporation, enrolment, monthly "
        "tuition); 'admission' for which years are open and how to apply.",
    )


class EventsRequest(BaseModel):
    query: str = Field(
        default="",
        description="What they asked about, e.g. 'Kínder', 'musical', 'misa', 'reunión', "
        "'noviembre'. Empty for what is coming up in general.",
    )


class ContactRequest(BaseModel):
    parent_name: str = Field(description="The parent's name, as they said it.")
    child: Literal["son", "daughter", "child"] = Field(
        default="child", description="Whether the email is about their son, daughter, or not said."
    )
    child_age: str = Field(
        default="",
        description="The child's age as said, e.g. '5' or 'cinco años'. Empty if not said.",
    )
    grade: str = Field(
        default="",
        description="The level or grade they apply for, e.g. 'Kínder 2027' or '3º básico'. "
        "Empty if not said.",
    )
    question: str = Field(
        description="Their question or what they want from admissions, in their words, "
        "in the language of the call."
    )


LinkKind = Literal["document", "musical_tickets", "schoolnet", "tuition", "lirmi", "careers"]


class LinkRequest(BaseModel):
    kind: LinkKind = Field(
        description="document: a PDF or link on the page in front or in the site pages "
        "(name it in label); musical_tickets: The Lion King's tickets; schoolnet, tuition "
        "(Pago Colegiatura), lirmi: the families' logins; careers: Trabaja con nosotros."
    )
    label: str = Field(
        default="",
        description="For a document: its button's words as the screen or the site pages "
        "list them, e.g. 'HORARIOS DEPORTE 2026'.",
    )


class TabRequest(BaseModel):
    tab_id: str = Field(description="The tab_id from the open tabs list.")


class LanguageRequest(BaseModel):
    language: Lang = Field(description="'en' for English, 'es' for Spanish.")


# ─── Places, contacts and portals ──────────────────────────────────────────────

ADMISSION_PATH = "/admision/admision"
MOREAU_PATH = "/admision/admision-programa-moreau"
CALENDAR_PATH = "/familia/calendario"
MUSICAL_PATH = "/familia/musical-the-lion-king"

#: The admissions office, as the admission page gives it ("Consultas:
#: admisiones@saintgeorge.cl", "Fono: 223556181"). The card carries both; the
#: parent writes or calls.
ADMISSIONS_EMAIL = "admisiones@saintgeorge.cl"
ADMISSIONS_PHONE = "+56 2 2355 6181"

#: The site's own links to its portals and the musical's tickets, as its menu
#: and pages give them. The live page's link wins when it has one.
_PORTALS: dict[str, tuple[str, str]] = {
    "musical_tickets": (
        "Entradas The Lion King",
        "https://ticketplus.cl/events/musical-the-lion-king",
    ),
    "schoolnet": ("Schoolnet", "https://schoolnet.colegium.com/webapp/es_CL/login"),
    "tuition": (
        "Pago Colegiatura",
        "https://sistemas.saintgeorge.cl/colegiatura/pagar-mensualidad",
    ),
    "lirmi": ("LIRMI", "https://login.lirmi.com/"),
    "careers": (
        "Trabaja con nosotros",
        "https://saintgeorge.profejobs.cl/trabaja-con-nosotros",
    ),
}
#: Each portal's host, to prefer the page's own link to it.
_PORTAL_HOSTS = {
    "musical_tickets": "ticketplus.cl",
    "schoolnet": "schoolnet.colegium.com",
    "tuition": "sistemas.saintgeorge.cl",
    "lirmi": "lirmi.com",
    "careers": "profejobs.cl",
}

#: The pages every move here leans on, as the site serves them (checked
#: 2026-10-22): a cue to one of them is good even before a crawl is loaded.
CORE_PAGES: dict[str, str] = {
    "/": "Inicio",
    "/unidad/infant": "Infant",
    "/unidad/elementary": "Elementary",
    "/unidad/junior": "Junior",
    "/unidad/senior": "Senior",
    ADMISSION_PATH: "Admisión",
    MOREAU_PATH: "Admisión Programa Moreau",
    CALENDAR_PATH: "Calendario",
    MUSICAL_PATH: "The Lion King",
    "/formacion-integral/direccion_de_estudios": "Dirección de Estudios",
    "/formacion-integral/area-deportiva": "Área Deportiva",
}

#: The units and their grades, with each grade's accordion as the unit's page
#: writes it: the page opens a grade by its button's words.
UNITS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("Infant", "/unidad/infant", ("PRE KINDER", "KINDER")),
    ("Elementary", "/unidad/elementary", ("1º BÁSICO", "2º BÁSICO", "3º BÁSICO", "4º BÁSICO")),
    ("Junior", "/unidad/junior", ("5º BÁSICO", "6º BÁSICO", "7º BÁSICO", "8º BÁSICO")),
    ("Senior", "/unidad/senior", ("9°", "10°", "11°", "12°")),
)

# ─── The prompt ────────────────────────────────────────────────────────────────

_SITE_MAP_CHARS = 18000
_SECTIONS_PER_PAGE = 14
_FAQS_PER_PAGE = 10
_LINKS_PER_PAGE = 8
#: "Admisión - Saint George's College": the site's name after its own, with any
#: dash or bar, and either apostrophe.
_TITLE_SUFFIX = re.compile(r"\s+[-|\u2013\u2014]\s+Saint George.s College\s*$")


def _short_title(title: str) -> str:
    return _TITLE_SUFFIX.sub("", title).strip()


def _site_map(k: Knowledge) -> str:
    """Every page, with its headings, its accordions and its documents."""
    lines: list[str] = []
    size = 0
    for p in sorted(k.pages.values(), key=lambda p: (p.path.count("/"), p.path)):
        heads = "; ".join(p.headings[:_SECTIONS_PER_PAGE])
        faqs = "; ".join(f.q for f in p.faqs[:_FAQS_PER_PAGE])
        docs = "; ".join(dict.fromkeys(x.label for x in p.links[:_LINKS_PER_PAGE] if x.label))
        line = f"- {p.path} — {_short_title(p.title)}"
        line += f" (sections: {heads})" if heads else ""
        line += f" (accordions: {faqs})" if faqs else ""
        line += f" (links: {docs})" if docs else ""
        size += len(line) + 1
        if size > _SITE_MAP_CHARS:
            break
        lines.append(line)
    if lines:
        return "\n".join(lines)
    return "\n".join(f"- {path} — {title}" for path, title in CORE_PAGES.items())


def _levels(k: Knowledge) -> str:
    """The units, their pages and their grades' accordions, as the crawl has
    them where it has them."""
    lines: list[str] = []
    for name, path, grades in UNITS:
        page = k.page(path)
        crawled = [f.q for f in page.faqs] if page is not None else []
        listed = [g for g in crawled if not norm(g).startswith("direccion")] or list(grades)
        lines.append(f"- {name} — {path} — grade accordions: {'; '.join(listed)}")
    return "\n".join(lines)


def _topics(k: Knowledge) -> str:
    return "\n".join(f"- {t.id}: {t.title}" for t in k.topics.values()) or "(none loaded)"


def _prompt(k: Knowledge, today: date | None = None) -> str:
    today = today or datetime.now(TIMEZONE).date()
    return f"""You are {AGENT_NAME}, the guide on the website of Saint George's College, saintgeorge.cl, a school in Santiago, Chile, from Pre-Kínder to twelfth grade. A visitor, most often a parent thinking about the school for their child, is browsing the site and has called you from the corner of the page. You can see and move their screen: you open pages, scroll to the exact section that answers them and ring it, open the accordions, read the fees and the coming events off their own screen, open documents and links in a new tab, and put up a ready email to the admissions office. You are warm, calm and helpful — the friend who knows the school inside out and helps a family picture their child there. Choosing a school should feel clearer after talking to you.

# You narrate, and the screen follows your words
You are giving a guided walkthrough, like someone sitting beside the parent with their screen in front of you both. As you talk about something, it is on their screen, ringed, at that moment.
- Put a screen cue in your reply at the start of the sentence it belongs to. The page moves when your voice reaches that sentence. The visitor never hears a cue.
  - {{page: /path}} opens a page of the site, at its top.
  - {{show: Heading}} scrolls to a heading on the page they are on, or are taken to by a page cue, and rings it. With other words on the page — a value, a line — it rings those words.
  - {{faq: Accordion}} opens that accordion by its button's words and rings it: a grade on a unit's page ("1º BÁSICO", "KINDER"), a team on a formation page ("CONOCE AL EQUIPO").
- Use headings and accordions exactly as the site pages list or the screen lines spell them. The site is in Spanish, so cues are in Spanish, also inside an English reply: "{{page: /unidad/infant}}{{faq: KINDER}} Kínder is the second year of Infant."
- Never make up a heading. One cue per sentence at most, and only where the screen should change. A cue goes before the sentence, never inside it.
- When the visitor asks where something is ("show me", "where is that", "muéstrame"), your reply starts with the cue for exactly that thing.
- A page cue opens a page at its top. So after a page cue, every sentence about a part of the page brings its own show cue.
- EVERY ANSWER ABOUT THE SCHOOL STARTS WITH A CUE. Whatever you talk about is on a page in the site pages list, so open that page and show the section as you begin. A reply without a cue leaves their screen where it was while you describe something else.
- Cues are the only way you move the page, apart from the fees, the calendar and the contact card below. Nothing waits on a cue.
- Example, for "tell me about the school": "{{page: /}}{{show: Nuestra comunidad}} Somos una comunidad de cuatro unidades. {{show: La misión que nos convoca}} Somos un colegio católico de la Congregación de Santa Cruz. {{show: Nuestros valores}} Y siete valores guían lo que hacemos. ¿Me cuentas qué edad tiene tu hijo o hija?"

# A good turn helps a family decide
1. Answer what they asked, first, in plain words, and show it as you say it.
2. Say why it matters for their child, in a sentence, when you know something about them: age, grade, what they care about.
3. End by offering the next step: one short, specific yes-or-no offer, so they only have to say "yes" or pick one. "¿Te muestro su curso?" "Shall I show you the admission page?" Never "anything else?".
- Choosing a school has an order. Follow it, from wherever the visitor is: who their child is (age or grade), then that child's unit and grade, then academics and English, then formation (faith, sports, life together), then admissions and fees, then a message to the admissions office.
- Ask about them only when the answer changes what you show next: the child's age is the first thing worth asking.

# How you sound
You are heard, not read, so keep it light and warm.
- A turn is three to five short sentences. A walkthrough of a page can run to eight, one item per sentence, each with its cue.
- Every sentence under fifteen words. Small, everyday words. One idea per sentence. One number per sentence.
- THE FIRST SENTENCE IS A FEW WORDS. The visitor hears nothing until your first sentence has been voiced, so open every reply with a sentence of two to six words that ends in a full stop, with the answer in it. A cue may come before it.
- Before most replies the visitor has already heard a short acknowledgement of mine — "Claro.", "A ver.", or in English "Happy to help.", "Let me see." — so never open with one: your first word is the answer. No "great question", no repeating their question back.
- Spoken words only, apart from cues: no lists, no markdown, no symbols, never an exclamation mark. Write dates, times, grades and numbers as spoken words: "el veinte de noviembre", "quinto básico", "dieciocho UF", never "20/11" or "5º".
- Lines in square brackets come from their screen, not the visitor. Never read them out; use them.
- Always answer. A reply with no words leaves the visitor in silence.
- Never name individual teachers or staff from the accordions' tables unless the visitor asks for a person. Leadership by role is fine.

# Spanish or English
You speak Spanish as a native of Latin America, and English. The call starts in Spanish unless the visitor chose English.
- Answer in the language the visitor speaks to you. If they speak English, answer in English from that reply on; if they go back to Spanish, so do you.
- Except when they chose a language: a line in square brackets says so. Then answer in that language whatever they speak, until they ask you to switch.
- When they ask for the other language in words that are not already it ("¿Puedes hablar en inglés?", "Can we speak Spanish?"), answer in that language and call set_language in the same response. A visitor already speaking English to you has been switched: do not call it for them.
- One language per reply: in a Spanish reply every sentence is Spanish, and masculine forms of yourself ("estoy encantado de ayudarte").
- Your Spanish is neutral Latin American Spanish, warm and natural for a Chilean parent, never the Spanish of Spain and never heavy slang.
  - Address one visitor as "tú", never "usted"; several people are "ustedes", never "vosotros", and never its verb forms ("queréis", "tenéis", "podéis") or "os".
  - Use Latin American words: "celular", never "móvil"; "computador", never "ordenador"; "auto", never "coche"; "mostrar" ("te muestro"), not "enseñar"; "completar", not "rellenar"; "¿Qué día te queda bien?", not "te viene bien"; "disculpa", not "perdona"; "está bien" or "perfecto", never "vale"; "tomar", never "coger"; "apoderado" for a parent at school.
  - For something just done, use the simple past: "Abrí la página", "Ya te lo mostré", not "He abierto".
  - Write "video", never "vídeo".
- Names stay as the site writes them: Infant, Elementary, Junior, Senior, Programa Moreau, Cambridge English Qualifications, The Lion King, Schoolnet.
- In English, say the site's Spanish names as they are written ("Pre-Kínder", "Dirección de Estudios"), and explain them in a few words when they are not obvious. Chilean grades: "primero básico" is first grade.

# Every response starts with words
Write your answer, with its cues, first; any tool call comes at the end of the same response. What a page call returns reaches you only later.
- The exception is a read: read_topic and search_site come straight back to you within this same turn, but each one makes the visitor wait. Answer from what you know below and the site pages list whenever they cover it, which is most of the time. Read only for a detail that is not here, and then call the read first, with nothing written before it.
- Never promise more to come ("let me check", "one moment", "un momento"): nothing comes after it, and a reply that is only a promise leaves the visitor in silence.

# What that sounds like
Visitor: "Mi hija tiene cinco años."
You: "{{page: /unidad/infant}} Entonces sería Kínder. {{faq: KINDER}} Aquí están los cursos de Kínder. Infant es la unidad de los más chicos. ¿Te cuento cómo postular?"
Visitor: "¿Cuánto cuesta?"
You: "Te muestro los valores en la página de admisión. Te los leo apenas aparezcan." then show_fees.
Visitor: "What's coming up at the school?"
You: "I'll pull up the school calendar. I'll read you what's next as it comes in." then show_events.
Visitor: "Do you have sports?"
You: "{{page: /formacion-integral/area-deportiva}} Yes, a lot of it. The program avoids early specialisation. {{faq: CONOCE AL EQUIPO}} Here is the sports team. Want me to open the sports schedule?"

# What you know
- Today is {today:%A, %d %B %Y}, in Santiago. The school year in Chile runs from March to December.
- Every fact comes from the knowledge below, a topic you read, a search result, or what the screen reported. Never from memory. If you cannot find it, say so, and say where on the site it might be, or offer to write to admissions.
- Topics you can read with read_topic, when the knowledge below does not cover a question:
{_topics(k)}
- search_site finds a page, section, accordion or document by its words. Its results name the page and section, which you can then cue.

# What changes is read off their screen, never from memory
Fees, the admission status and the school's dates change during the year. Even when the knowledge below mentions them, say a fee, an admission date or an event's date ONLY from a bracketed line the page read during this call.
- Fees, or which years are open for admission: call show_fees, with a few words first and no cue (it takes them to the admission page itself). The page reads the values off itself and they reach you in a bracketed line moments later; then say them exactly as written, in UF, as reference values, and that they can vary by level.
- What is coming up, a date, a school event: call show_events, with a few words first and no cue (it opens the calendar page itself). The school's calendar is read in their browser and the next events reach you in a bracketed line; then say the two or three that matter to this family.
- If a bracketed line says the read failed, say plainly that you cannot see it right now and that it is on the page in front of them. Never guess.
- The Programa Moreau is the school's programme for families of more limited means: cue {{page: {MOREAU_PATH}}} for it.

# Levels by age
The school's four units, their pages, and each grade's accordion on the unit's page:
{_levels(k)}
- For a child's age, take the usual Chilean grade at the start of the school year in March: Pre-Kínder at four, Kínder at five, primero básico at six, and one grade more each year to twelfth at seventeen. Say it is the usual grade for that age and that admissions confirms it.
- Then open the unit's page and that grade's accordion: "{{page: /unidad/elementary}}{{faq: 1º BÁSICO}}".

# Writing to admissions
The site has no contact form: admissions answers by email and phone.
- When the parent wants to contact admissions, apply or ask for a visit, gather by voice, one question at a time: their name, the child's age or the grade they are looking at, and what they want to ask. Use what they already told you; never ask twice.
- Then call show_contact_card. A card comes up over the page with the email written out, ready, in the language of the call, and the phone. Say that they press the button to open it in their own email and send it themselves. Never say it was sent: you send nothing.
- You may also give the admissions phone from the knowledge below, digit group by digit group.
- Never ask for or write a RUT, an address, or a card number.

# Moving the page
- Cue only a path from the site pages list or a search result, and only headings and accordions the lists or the screen give.
- The visitor can ask you to scroll to or open anything: "open first grade", "go back to the home page". Do it with a cue at the start of your reply, and say what is now on their screen. Never say you cannot scroll or click.

# Documents and links
- Documents (PDFs: sports schedules, supply lists, newsletters, plans) and links open in a new tab with open_link, only when they ask or say yes to your offer. Say you opened it in a new tab.
- The musical's tickets are open_link with musical_tickets, on Ticketplus, where they buy them themselves.
- Schoolnet, Pago Colegiatura and LIRMI are logins for families already at the school: open them only when the visitor asks for them by name or purpose, say they log in there themselves, and never offer them to a prospective parent. You never log in, pay or fill anything in.

# Tabs
- The visitor may have several Saint George's tabs open. Lines in brackets tell you which tabs are open and which is in front. Your moves happen on the tab in front.
- "Go back to the other tab" is switch_tab with that tab's id.

# Saint George's College
{k.l1}

# Site pages
{_site_map(k)}
"""


# ─── Greeting ──────────────────────────────────────────────────────────────────

_INTRO: dict[Lang, str] = {
    "en": f"Hi, I'm {AGENT_NAME}, your guide to Saint George's College.",
    "es": f"Hola, soy {AGENT_NAME}, tu guía del Saint George's College.",
}
_GREETING: dict[Lang, str] = {
    "en": "I can show you the school, its levels and how admissions work. How old is your child?",
    "es": "Te muestro el colegio, sus niveles y cómo es la admisión. ¿Qué edad tiene tu hijo o hija?",
}
#: The opener's second sentence for the page the call starts on, by a word in
#: its path; the first match wins, and anything else gets the plain greeting.
_OPENERS: tuple[tuple[str, dict[Lang, str]], ...] = (
    (
        "moreau",
        {
            "en": "I can tell you about the Programa Moreau. Is it for your family?",
            "es": "Te cuento sobre el Programa Moreau. ¿Es para tu familia?",
        },
    ),
    (
        "admision",
        {
            "en": "I can walk you through admissions and the fees. Which grade are you looking at?",
            "es": "Te explico la admisión y los valores. ¿A qué curso postularía tu hijo o hija?",
        },
    ),
    (
        "unidad",
        {
            "en": "I can show you this unit and its grades. How old is your child?",
            "es": "Te muestro esta unidad y sus cursos. ¿Qué edad tiene tu hijo o hija?",
        },
    ),
    (
        "calendario",
        {
            "en": "I can tell you what's coming up at the school. Shall I read you the next events?",
            "es": "Te cuento lo que viene en el colegio. ¿Te leo los próximos eventos?",
        },
    ),
    (
        "lion-king",
        {
            "en": "I can tell you about The Lion King musical. Shall I open the tickets?",
            "es": "Te cuento sobre el musical The Lion King. ¿Te abro las entradas?",
        },
    ),
    (
        "deportiva",
        {
            "en": "I can show you the sports program. How old is your child?",
            "es": "Te muestro el área deportiva. ¿Qué edad tiene tu hijo o hija?",
        },
    ),
)


def greeting(path: str | None, lang: Lang = OPENING) -> str:
    """The written opener, in ``lang``, tailored to the page the call starts on."""
    here = canonical_path(path or "/")
    line = next((lines[lang] for word, lines in _OPENERS if word in here), _GREETING[lang])
    return f"{_INTRO[lang]} {line}"


# ─── Written lines for moves ───────────────────────────────────────────────────

#: His line for a silent turn, by what moved: "shown" for anything else.
_LANDED: dict[str, dict[Lang, str]] = {
    "shown": {"en": "Here it is.", "es": "Aquí lo tienes."},
    "link": {"en": "I've opened it in a new tab.", "es": "Te lo abrí en una pestaña nueva."},
    "fees": {
        "en": "I'm bringing up the fees on the admission page.",
        "es": "Te muestro los valores en la página de admisión.",
    },
    "events": {
        "en": "I'm bringing up the school calendar.",
        "es": "Te muestro el calendario del colegio.",
    },
    "card": {
        "en": "Your email to admissions is on the screen, ready for you to send.",
        "es": "Tu correo a admisiones está en pantalla, listo para que lo envíes.",
    },
    "queued": {
        "en": "I'll do that as soon as the page is ready.",
        "es": "Lo hago apenas la página esté lista.",
    },
    "tab": {"en": "There's that tab.", "es": "Ahí tienes esa pestaña."},
}

# ─── His nod ───────────────────────────────────────────────────────────────────

#: Only lines measured to come out in Javier's own voice: each line is voiced
#: on its own and always the same way, and "Right.", "One moment." or "Un
#: momento." came out as somebody else (82 Hz and 166 Hz against his 110-132).
#: This is Explora's measured set (speaker embedding and pitch against his own
#: replies). It holds for this bake of omnivoice/javier: measure a new line first.
_ACK_LINES: dict[Lang, dict[Kind, tuple[str, ...]]] = {
    "en": {
        "request": ("Happy to help.", "Absolutely, let me do that.", "Sure thing."),
        "question": ("Let me see.", "Good question, let me see."),
        "correction": ("Got it, thanks for letting me know.", "Ah, I see what you mean."),
        "statement": ("Okay, that makes sense.", "Got it, thanks for letting me know."),
    },
    "es": {
        "request": (
            "Claro.",
            "Con gusto, ya lo hago.",
            "Por supuesto, déjame revisarlo.",
            "Claro, ahora mismo.",
        ),
        "question": ("A ver.", "Déjame revisarlo un momento."),
        "correction": ("Entendido, gracias por avisarme.", "Entendido, eso me ayuda."),
        "statement": ("Entendido, eso me ayuda.", "Claro.", "Entendido, gracias por avisarme."),
    },
}
#: Santander Arena's rate: every page here is a full load, and the nod is what
#: the visitor hears while the next page comes in.
ACK_RATE = 0.9
#: After a nod, how long the model may stay quiet before he holds the floor.
#: The brain answers from India; on the Clini guide's calls a turn with a move
#: took five or six seconds, and at 4 s nearly every one said "Just a moment."
ACK_HOLD_AFTER_S = 5.75
#: With no nod, the dead air a turn may leave before his first line: a late nod
#: for what they said, or a hold line. Without it, a turn the nod skipped sat in
#: ten seconds of silence on the Clini guide.
HOLD_WITHOUT_NOD_S = 2.5
#: "Sorry, that's taking a little longer." only when it really is.
ACK_SORRY_AFTER_S = 15.0
_ACK_HOLD: dict[Lang, tuple[str, ...]] = {
    "en": ("Just a moment.", "One moment while I check that for you."),
    "es": ("Dame un momento mientras lo busco.", "Un momento mientras lo reviso para ti."),
}
_ACK_SORRY: dict[Lang, str] = {
    "en": "Sorry, that's taking a little longer.",
    "es": "Lo siento, está tardando un poco más de lo normal.",
}
#: A parent's ordinary words about the school, so the reading trusts them.
_ACK_WORDS = Vocabulary(
    common=frozenset(
        # A word list reads as words, so it stays a split string.
        """colegio saint george george's college hijo hija hijos hijas niño niña niños años
        edad curso cursos kinder kínder prekinder pre básico basico medio infant elementary
        junior senior admisión admision postular postulación postulacion vacantes matrícula
        matricula colegiatura cuota valores uf moreau beca inglés ingles cambridge deporte
        deportes academia academias pastoral calendario eventos musical lion king entradas
        apoderado apoderados uniforme casino materiales correo teléfono telefono school son
        daughter child kids grade grades kindergarten admissions apply fees tuition english
        sports calendar events tickets uniform
        """.split()  # noqa: SIM905
    ),
)


@dataclasses.dataclass
class _LateFloor:
    """The floor for a turn that had no nod: a nod for what they said, late,
    else a hold line; then the apology. What :func:`hold_the_floor` reads."""

    ack: Acknowledger[Lang]
    nod: str | None
    hold_after_s: float
    sorry_after_s: float

    @property
    def sorry(self) -> dict[Lang, str]:
        return _ACK_SORRY

    def hold(self, spoken: Lang) -> str:
        return self.nod or self.ack.hold(spoken)


def _late_nod(text: str, spoken: Lang) -> str | None:
    """The nod :class:`Acknowledger` would have chosen, had the dice said yes."""
    kind = classify(text, _ACK_WORDS)
    lines = _ACK_LINES[spoken].get(kind) if kind else None
    return random.choice(lines) if lines else None


def _avatar_state(session: Session, state: Literal["WORKING"] | None) -> None:
    """The talking head's working latch: held until speech owed has played."""
    session.send_rtvi(RTVIType.SERVER_MESSAGE, {"type": "avatar", "cmd": "state", "state": state})


_HEADINGS_IN_NOTE = 40
_FAQS_IN_NOTE = 40
_LINKS_IN_NOTE = 16
_SEARCH_HITS = 6
_EVENTS_IN_NOTE = 8


async def _silence() -> AsyncGenerator[Any, None]:
    for _ in ():
        yield


def _clip(items: list[str] | tuple[str, ...], most: int) -> str:
    more = f"; and {len(items) - most} more" if len(items) > most else ""
    return "; ".join(items[:most]) + more


def _match(want: str, options: list[str] | tuple[str, ...]) -> str | None:
    """The option ``want`` names: the same words, else the one it begins, else
    the one it is inside — how the page itself matches. Case, accents, ordinal
    marks and punctuation do not count: "1° basico" is "1º BÁSICO"."""

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
    (re.compile(rf"\b(?:{w})", re.IGNORECASE), path)
    for w, path in (
        (r"moreau|beca|scholarship|financial aid", MOREAU_PATH),
        (
            r"pre ?-?kinder|prekinder|kinder|kindergarten|infant\b|preschool|jardin",
            "/unidad/infant",
        ),
        (
            r"elementary|primero basico|segundo basico|tercero basico|cuarto basico",
            "/unidad/elementary",
        ),
        (r"junior\b|quinto basico|sexto basico|septimo basico|octavo basico", "/unidad/junior"),
        (r"senior\b|ensenanza media|high school|\bmedio\b", "/unidad/senior"),
        (
            r"cambridge|direccion de estudios|academic|academico|curricul",
            "/formacion-integral/direccion_de_estudios",
        ),
        (
            r"deport|sports?\b|futbol|football|soccer|rugby|hockey|atletismo|athletics|"
            r"extracurricular|academias?\b",
            "/formacion-integral/area-deportiva",
        ),
        (r"musical|lion king|rey leon|90 anos|90 years|aniversario|anniversary", MUSICAL_PATH),
        (
            r"pastoral|catequesis|primera comunion|first communion",
            "/formacion-integral/direccion_de_pastoral",
        ),
        (r"psicorientacion|counsel", "/formacion-integral/psicorientacion"),
        (r"convivencia", "/formacion-integral/area-de-convivencia-escolar"),
        (r"historia|history|fundad|founded", "/colegio/historia"),
        (r"congregacion|holy cross|santa cruz", "/congregacion/congregacion-santa-cruz-chile"),
        (r"proyecto educativo", "/colegio/proyecto-educativo"),
        (r"equipo directivo|rector|principal\b|headmaster|leadership", "/equipo-directivo"),
        (r"casino|cafeteria|almuerzo|lunch", "/familia/casino"),
        (r"ropero|uniform", "/familia/ropero"),
        (
            r"lista de (?:utiles|materiales)|materiales|school supplies|supply list",
            "/familia/materiales",
        ),
        (r"the dragon|boletin|newsletter", "/familia/boletin-the-dragon"),
        (r"admision|admission|postul|apply|applying|vacantes?|enrol", ADMISSION_PATH),
        (r"valores|values|mision|mission|comunidad|community", "/"),
    )
)
#: The home page, which "school" and "values" name in passing.
_GENERAL_PAGE = "/"
#: What a tool moves rather than a cue: the fees and the calendar are read live
#: and their tools take the visitor there; a document, the tickets and the
#: portals open in a new tab; a message to admissions is a card.
_BY_TOOL = re.compile(
    r"\b(?:cuanto cuesta|cuestan?|costo|precios?|valor(?:es)? (?:de|referencial)|cuotas?|"
    r"colegiatura|matricula|mensualidad|arancel|fees?|tuition|costs?|price|how much|"
    r"calendario|calendar|eventos?|events?|actividades|activities|coming up|proxim\w*|"
    r"upcoming|fecha|dates?|when is|cuando es|"
    r"entradas?|tickets?|boletos?|comprar|buy|pdf|document\w*|horario|schedule|"
    r"schoolnet|lirmi|pago|login|"
    r"correo|email|e-mail|escribir|write to|contact\w*|llamar|call them|phone|telefono|"
    r"tabs?|pestanas?)\b",
    re.IGNORECASE,
)

# A request about the call's own language: a verb of speaking, addressed to him
# ("can you", "let's") or said by him ("I can", "volvemos"), and the language.
# On SendPotion "Hey, can you speak in Spanish?" opened the languages page
# while he talked about something else. "Do you teach in English?" is about
# the school, not the call: it has no verb of speaking to him.
_CALL_LANGUAGE = re.compile(
    r"\b(?:speak|talk|switch|change|continue|carry on|answer|reply|respond|go back|"
    r"habl\w*|cambi\w*|sig\w*|continu\w*|respond\w*|contest\w*|pas\w*|volv\w*)\b"
    r"[^.?!]{0,25}?\b(?:spanish|english|español|espanol|castellano|inglés|ingles)\b",
    re.IGNORECASE,
)
_TO_HIM = re.compile(
    r"^\W*(?:(?:hey|ok|okay|please|so|now|oye|bueno|por favor)\W+)*"
    r"(?:speak|talk|switch|change|continue|carry|answer|reply|respond|go|habla|háblame|"
    r"cambia|sigue|continúa|responde|contesta|pasa|vuelve)\b"
    r"|\b(?:you|we|us|let'?s|let us|i|i'?ll|puedes|podemos|podrías|podríamos|hablemos|"
    r"sigamos|cambiemos|continuemos|pasemos|volvamos|me|nos|hablamos|seguimos|cambiamos|"
    r"continuamos|pasamos|volvemos|puedo)\b",
    re.IGNORECASE,
)


def asks_call_language(text: str) -> bool:
    """Whether ``text`` asks him to speak another language — a request about
    this call, not a question about the school."""
    return bool(_CALL_LANGUAGE.search(text) and _TO_HIM.search(text))


def asked_page(text: str) -> str | None:
    """The site page for what ``text`` asks about, or ``None``. The fees, the
    calendar, a document, a portal, a message to admissions and a tab are
    moved by their tools, and "can you speak English?" is about this call:
    none of them is a page."""
    said = fold(text)
    if _BY_TOOL.search(said) or asks_call_language(text):
        return None
    named = [
        (m.start(), m.start() - m.end(), path)
        for rx, path in _ASKED_PAGES
        if (m := rx.search(said))
    ]
    specific = [n for n in named if n[2] != _GENERAL_PAGE]
    return min(specific or named)[2] if named else None


#: A RUT, as written in Chile ("12.345.678-9", "12345678-K"): never put in an
#: email or anywhere on the page.
_RUT = re.compile(r"\b\d{1,2}\.?\d{3}\.?\d{3}\s*-\s*[\dkK]\b")


def contact_email(request: ContactRequest, lang: Lang) -> tuple[str, str]:
    """The subject and body of the parent's email to admissions, in ``lang``."""
    name = " ".join(request.parent_name.split())
    age = " ".join(request.child_age.split())
    grade = " ".join(request.grade.split())
    question = " ".join(request.question.split())
    if lang == "es":
        child = {"son": "mi hijo", "daughter": "mi hija", "child": "mi hijo o hija"}[request.child]
        about = child + (f", de {age}" if age else "")
        if age and not re.search(r"\baño", age):
            about += " años"
        subject = f"Consulta de admisión{f': {grade}' if grade else ''}"
        lines = [
            "Hola,",
            "",
            f"Mi nombre es {name}. Les escribo por la admisión de {about}"
            + (f", para {grade}." if grade else "."),
            "",
            question,
            "",
            "Muchas gracias.",
            name,
        ]
    else:
        child = {"son": "my son", "daughter": "my daughter", "child": "my child"}[request.child]
        about = child + (f", age {age}" if age else "")
        subject = f"Admissions enquiry{f': {grade}' if grade else ''}"
        lines = [
            "Hello,",
            "",
            f"My name is {name}. I am writing about admission for {about}"
            + (f", for {grade}." if grade else "."),
            "",
            question,
            "",
            "Thank you,",
            name,
        ]
    return subject, "\n".join(lines)


def mailto(to: str, subject: str, body: str) -> str:
    """The ``mailto:`` link the card's button carries."""
    return f"mailto:{to}?subject={quote(subject)}&body={quote(body)}"


# ─── The section a sentence describes ──────────────────────────────────────────
#
# What he says, sentence by sentence, matched against the sections of the one
# page in front — never the whole site. A heading word counts for more than a
# word of the section's text, a word every section shares for little, and a
# sentence that is not clearly about one section moves nothing.

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
    saint george georges college colegio""".split()  # noqa: SIM905
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


def _on_page(text: str, page: Page) -> bool:
    """Whether ``text`` is on ``page`` as the crawl read it."""
    want = norm(text)
    if not want:
        return False
    parts = [page.title, page.text, *(f"{s.heading} {s.text}" for s in page.sections)]
    parts += [c.title for c in page.cards] + [f.q for f in page.faqs]
    parts += [link.label for link in page.links]
    return any(want in norm(p) for p in parts)


# ─── One move at a time ────────────────────────────────────────────────────────

#: The moves the page answers (``fees_read``, ``events_read``, ``command_done``
#: or ``command_failed``), and how long each may take, a page load included.
_MOVE_TAKES_S = {"show_fees": 20.0, "show_events": 25.0, "show_contact_card": 8.0}
#: Words of his still playing hold the floor no longer than this.
_PLAYOUT_MAX_S = 30.0

#: The talk-through each answer asks for.
_SAY_FEES = (
    "Say these values now, exactly as the page writes them, in UF, one per sentence, as the "
    "school's reference values, and that the monthly tuition can vary by level. Then offer to "
    "put up an email to admissions."
)
_SAY_STATUS = (
    "Say what the page says about admission now, in a sentence or two, as written. Then offer "
    "the fees, or an email to admissions."
)
_SAY_EVENTS = (
    "Say the two or three of these that matter to this family, with their dates as spoken "
    "words, then offer one next step. Do not read out the whole list."
)
_SAY_NO_EVENTS = (
    "None of the coming events matches what they asked. Say so plainly, name one or two that "
    "are coming up, and say the calendar is on their screen."
)


# ─── The brain ─────────────────────────────────────────────────────────────────


class SaintGeorgeBrain(GeminiBrain):
    """One per session. Javier: Saint George's knowledge, its pages, what the
    visitor's browser read live, and a mirror of their tabs, in Spanish or
    English."""

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
            _ACK_LINES,
            _ACK_HOLD,
            _ACK_SORRY,
            _ACK_WORDS,
            ACK_RATE,
            ACK_HOLD_AFTER_S,
            ACK_SORRY_AFTER_S,
        )
        #: The tab in front as it last reported itself, and whether the model
        #: has seen it since it changed.
        self.page: PageChanged | None = None
        self._path = "/"
        self._page_unseen = False
        #: Every open Saint George's tab, and which is in front.
        self.tabs: list[TabInfo] = []
        self._active = ""
        self._tabs_unseen = False
        #: What the visitor's browser read live this call, newest last.
        self.fees: FeesRead | None = None
        self.events: EventsRead | None = None
        self._events_query = ""
        self._fees_about: Literal["fees", "admission"] = "fees"
        #: The page this turn's cues are on: the one in front, then wherever a
        #: ``{page: …}`` cue took it.
        self._cue_path = "/"
        self._idle_short = False
        self._nudges = 0
        #: The page for what the visitor last asked about, shown at the start
        #: of his reply if it has no cue of its own; see :func:`asked_page`.
        self._backstop: str | None = None
        #: Whether the visitor's last words asked for something a tool moves.
        self._by_tool = False
        #: This reply's moves so far: whether one opened a page, and what was
        #: last rung, so a sentence on the same section does not ring it again.
        self._paged = False
        self._shown: str | None = None
        #: A talk-through owed that is not a move's answer (a card's button).
        self._talk: str | None = None
        #: The moves sent and not yet answered by the page, and the answers
        #: that came in since his last turn: talked through together, once, in
        #: the next short quiet spell.
        self._sent: dict[str, float] = {}
        self._outcomes: list[str] = []
        #: A move asked for while another was still under way on the page,
        #: sent once that one answers: one at a time, never two at once.
        self._queued: Action | None = None
        #: His turns under way, and his units of speech not yet played out: the
        #: idle window is shortened for a talk-through only when both are none,
        #: or the short quiet spell cuts his own reply.
        self._turns = 0
        self._playing = 0
        self._played_at = 0.0
        self._idle_deferred = False

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
                stt=SttConfig(language=self.spoken, patience=SAINT_GEORGE_PATIENCE),
                tts=TtsConfig(voice=VOICE, language=self.spoken),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
            )
        )
        logger.info(
            "saintgeorge: session start on {} in {}{}",
            self._path,
            self.spoken,
            " (chosen)" if self._chosen else "",
        )
        if self._chosen:
            self._note(_chosen_note(self.spoken, "before the call"))

    async def greet(self, session: Session) -> str:
        """The opener, written not generated."""
        line = greeting(self._path, self.spoken)
        return for_the_voice(line) if self.spoken == "es" else line

    async def on_finalize(self, session: Session, fin: Finalize) -> None:
        """What was heard goes into the model's context; a word respelled for
        the voice is spelled as written again first, so the model never sees
        "bidéo" in its own words."""
        if "idéo" in fin.heard:
            fin = dataclasses.replace(fin, heard=from_the_voice(fin.heard))
        await super().on_finalize(session, fin)
        self._playing = max(0, self._playing - 1)
        self._floor_free()

    def on_user_message(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]:
        return self._own_turn(self._answer(session, msg))

    async def _answer(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]:
        """A visitor who speaks the other language is answered in it from the
        first word, unless they chose the language they are in; the tab they
        moved to is read in with what they said; his nod covers the model's
        thinking, and his own line any dead air after it (:func:`hold_the_floor`):
        after a nod, past :data:`ACK_HOLD_AFTER_S`; with none, a late nod or a
        hold line past :data:`HOLD_WITHOUT_NOD_S`."""
        heard = None if self._chosen else language_of(msg.text)
        if heard is not None and heard != self.spoken:
            await session.configure(self._speaking(heard))
            logger.info("saintgeorge: language -> {} (heard)", heard)
        # They spoke first: the page's answers are in the context as notes,
        # and he answers them with what they said.
        self._talk = None
        self._outcomes.clear()
        self._idle_deferred = False
        # What he said before has played out, or they spoke over it.
        self._playing = 0
        self._nudges = 0
        # A reply cut off before it said a word keeps its page for the next one.
        # A request to switch language shows nothing, not even that page.
        self._backstop = (
            None if asks_call_language(msg.text) else asked_page(msg.text) or self._backstop
        )
        # Asked for what a tool moves (the fees, the calendar, a document, a
        # message): the tool takes them there, so his words open no page.
        self._by_tool = bool(_BY_TOOL.search(fold(msg.text)))
        self._restore_idle()
        self._read_in_screen()
        now = time.monotonic()
        fragment, self._heard_at = now - self._heard_at < _FRAGMENT_S, now
        nod = None if fragment else self._ack.line(msg.text, self.spoken)
        floor: Floor[Lang] = self._ack
        if nod is not None:
            logger.info("saintgeorge: ack {!r}", nod)
            async for event in say_line(self, nod):
                yield event
            _avatar_state(session, "WORKING")
        else:
            floor = _LateFloor(
                self._ack,
                None if fragment else _late_nod(msg.text, self.spoken),
                HOLD_WITHOUT_NOD_S,
                ACK_SORRY_AFTER_S,
            )
        working = nod is not None

        def answered() -> None:
            nonlocal working
            if working:
                working = False
                _avatar_state(session, None)

        try:
            turn = super().on_user_message(session, msg)
            async for event in hold_the_floor(self, floor, lambda: self.spoken, turn, answered):
                yield event
        finally:
            answered()

    async def _own_turn(self, turn: AsyncGenerator[Speech, None]) -> AsyncGenerator[Speech, None]:
        """``turn``, counted while it runs and for each unit until it has
        played: the floor is his, and no short idle window is set under it."""
        self._turns += 1
        try:
            async for event in turn:
                if isinstance(event, SpeechStart):
                    self._playing += 1
                    self._played_at = time.monotonic()
                yield event
        finally:
            await turn.aclose()
            self._turns -= 1
            self._floor_free()

    def on_user_idle(self, session: Session, idle: UserIdle) -> AsyncGenerator[Speech, None]:
        return self._own_turn(self._quiet(session, idle))

    def _quiet(self, session: Session, idle: UserIdle) -> AsyncGenerator[Speech, None]:
        """A quiet spell — the only floor he gets without the visitor speaking.

        What the page answered after his turn (the fees it read, the calendar,
        the card) is in the context already, and the idle window was shortened
        for it, so a reading visitor hears it from him here. Otherwise an
        ordinary quiet spell: a nudge, twice, then silence.

        He only talks here: the turn runs with tools off, so a quiet spell can
        never send a move of its own."""
        self._restore_idle()
        self._backstop = None
        self._by_tool = False
        if (ask := self._take_ask()) is not None:
            self._note(ask)
            return self._reply(session, ToolChoice.NONE)
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
                "Speak into the quiet, briefly, as the guide beside them would: one useful thing "
                "about what is on their screen, or one question that helps you help their child. "
                "Never ask whether they are still there, and never repeat your last line."
            )
        else:
            ask = (
                "Still quiet. One last, light offer, different from your last: something you "
                "could show them next. Then let them browse."
            )
        self._note(f"{quiet} {ask}")
        return self._reply(session, ToolChoice.NONE)

    def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        return self._reply(session, None)

    async def _reply(
        self, session: Session, tools: ToolChoice | None
    ) -> AsyncGenerator[Speech, None]:
        """The model's turn, with its screen cues taken out of the speech and
        sent to the page (:mod:`.cues`); ``tools`` limits it (``None``: any).

        If it moved the page and said nothing, he says the move's written line
        at once (:func:`landed`), in the language he speaks: asking the model
        again cost the Clini guide a second round trip of silence every time. A
        turn that came back with nothing at all — no words, no move — is asked
        once more, with tools off.

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
        said = ""
        model = (
            super().respond(session) if tools is None else self.respond_with(session, tools=tools)
        )
        turn = self._fallback.speak_if_silent(self, model)
        async for event in self._spelled(self._written(session, self._cued(turn))):
            if isinstance(event, SpeechChunk):
                said += event.text
            yield event
        # Words, and not only a promise: on Explora's dev call ed9846d5 the whole
        # reply was "One moment.", and the visitor sat in silence.
        if not _PROMISE.sub("", _CUE_TEXT.sub(" ", said)).strip(" .,!?¡¿…"):
            logger.warning("saintgeorge: the model returned nothing; asking once more")
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
                logger.info("saintgeorge: language -> {} (written)", written)
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
        """``turn``, with Spanish speech spelled as the voice must read it."""

        async def spelled() -> AsyncGenerator[Speech, None]:
            async for event in turn:
                if isinstance(event, SpeechChunk) and self.spoken == "es":
                    event = SpeechChunk(for_the_voice(event.text))
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
        if "{" in chunk or path == self._path or self._page_for(path) is None:
            return chunk
        logger.info("saintgeorge: the reply has no cue; showing {} first", path)
        return f"{{page: {path}}}{chunk}"

    def _send_cue(self, raw: RawCue) -> None:
        """Check a cue against the site, as the tools do, and send it; one that
        names nothing real is dropped and logged rather than reaching the page."""
        if self.spoken == "es" and raw.at:
            raw = dataclasses.replace(raw, at=_anchor_for_voice(raw.at))
        cue = self._resolve_cue(raw)
        logger.info("saintgeorge: cue {} {!r} at {!r} -> {}", raw.kind, raw.value, raw.at, cue)
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
        opened one, and the section on the page it describes."""
        out: list[tuple[CueKind, str]] = []
        kinds = {k for k, _ in placed}
        # A page the model opens on this very sentence is not sent yet.
        pages = [p.path for k, v in placed if k == "page" and (p := self._page_for(v)) is not None]
        path = pages[-1] if pages else self._cue_path
        # An accordion cue finds its own page (a grade on its unit's), so it
        # needs none in front of it: two loads in a row lose the second.
        if index == 0 and not self._paged and not self._by_tool and not kinds & {"page", "faq"}:
            asked = asked_page(sentence)
            if asked is not None and asked != self._path and self._page_for(asked) is not None:
                logger.info("saintgeorge: he talks about {} with no cue; opening it", asked)
                out.append(("page", asked))
                path = asked
        self._cue_path = path
        if kinds & {"show", "faq"}:
            return out
        page = self.kb.page(path)
        if page is None:
            return out
        shown = best_section(sentence, [(s.heading, s.text) for s in page.sections])
        if shown is not None and shown != self._shown:
            out.append(("show", shown))
        return out

    def _page_for(self, path_or_url: str) -> Page | None:
        """The crawl's page, or one of the core pages the site serves when the
        crawl does not have it."""
        if (page := self.kb.page(path_or_url)) is not None:
            return page
        path = canonical_path(path_or_url)
        title = CORE_PAGES.get(path)
        return Page(path=path, title=title) if title is not None else None

    def _resolve_cue(self, raw: RawCue) -> Cue | None:
        if raw.kind == "page":
            page = self._page_for(raw.value)
            if page is None:
                return None
            self._cue_path = page.path
            return Cue(at=raw.at, word=raw.word, path=page.path)
        target = self._page_for(self._cue_path)
        moved = self._cue_path != self._path
        if raw.kind == "faq":
            faqs = [f.q for f in target.faqs] if target else []
            if not moved:
                faqs = list(dict.fromkeys([*self._faqs(), *faqs]))
            faqs += [g for unit in UNITS if unit[1] == self._cue_path for g in unit[2]]
            question = _match(raw.value, faqs)
            if question is None:
                found = self._faq_elsewhere(raw.value)
                if found is None:
                    return None
                self._cue_path, question = found
                return Cue(at=raw.at, word=raw.word, path=found[0], faq=question)
            path = self._cue_path if moved else None
            return Cue(at=raw.at, word=raw.word, path=path, faq=question)
        # show: a heading of the page the visitor will be on, else those words,
        # which the page finds itself.
        headings = (
            target.headings
            if moved and target
            else self._headings() or (target.headings if target else ())
        )
        heading = _match(raw.value, headings)
        text = None
        if heading is None:
            live = (
                self.page is not None and not moved and canonical_path(self.page.path) == self._path
            )
            if (
                target is not None
                and target.sections
                and not live
                and not _on_page(raw.value, target)
            ):
                # Words the page does not have: on Santander Arena he cued a
                # "DESCRIPCIÓN" heading a show's page did not have.
                logger.info("saintgeorge: {!r} is not on {}; dropped", raw.value, target.path)
                return None
            text = raw.value[:120]
        path = self._cue_path if moved else None
        return Cue(at=raw.at, word=raw.word, path=path, heading=heading, text=text)

    def _talk_now(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The one extra request a turn with nothing in it gets: tools off."""
        return self.respond_with(session, tools=ToolChoice.NONE)

    async def _run(self, tool: Any, call: types.FunctionCall) -> types.Part:
        """Every tool takes one model, ``request``; Gemini sometimes sends its
        fields flat, which the SDK refuses. Wrap them before the call runs."""
        args = dict(call.args or {})
        # A request with nothing to say (show_fees with its default) arrives
        # as no arguments at all, and is wrapped the same way.
        if (
            tool is not None
            and "request" not in args
            and "request" in inspect.signature(tool).parameters
        ):
            logger.info("saintgeorge: {} called with flat arguments; wrapping them", call.name)
            call = call.model_copy(update={"args": {"request": args}})
        return await super()._run(tool, call)

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Page→brain events, folded in silently: no floor taken, no turn."""
        event = SAINT_GEORGE_EVENTS.parse(msg)
        if event is None:
            return
        logger.info("saintgeorge: {} — {}", type(event).__voqal_event__, event)
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
            logger.warning("saintgeorge: switch to {} refused: {}", event.language, rejected)
            self.spoken = was
            session.dispatch(LanguageChanged(language=was))
            return
        logger.info("saintgeorge: language -> {} (toggle)", event.language)
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
            stt=SttConfig(language=language, patience=SAINT_GEORGE_PATIENCE),
            tts=TtsConfig(voice=VOICE, language=language),
        )

    # ─── Page → brain ───────────────────────────────────────────────────

    def apply_event(self, event: SaintGeorgeEvent) -> str | None:
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
            case FeesRead():
                return self._fees_read(event)
            case EventsRead():
                return self._events_read(event)
            case ContactUsed():
                return self._contact_used(event)
            case CommandDone():
                detail = event.detail or "done"
                self._answered(event.command, f"{event.command} done: {detail}")
                return f"[The page confirms {event.command}: {detail}.]"
            case CommandFailed() if event.command == "cue":
                # He has already spoken past it: the next turn should not claim
                # it is on screen, nor stop to apologise for a scroll.
                return (
                    f"[A screen cue of yours did not land ({event.reason}). If the visitor "
                    "asks where it is, show it again; otherwise carry on.]"
                )
            case CommandFailed() if event.command in ("show_fees", "show_events"):
                what = "the fees" if event.command == "show_fees" else "the school's calendar"
                self._answered(
                    event.command,
                    f"{event.command} not done: the page could not read {what} ({event.reason}). "
                    f"Say plainly that you cannot see {what} right now, that it is on the page "
                    "in front of them, and never guess a value or a date.",
                )
                return (
                    f"[Not read on the page ({event.command}): {event.reason}. You cannot see "
                    f"{what} right now: never guess them.]"
                )
            case CommandFailed():
                self._answered(event.command, f"{event.command} not done: {event.reason}")
                return (
                    f"[Not done on the page ({event.command}): {event.reason}. Tell the visitor "
                    "plainly and offer what you can do instead; never say it worked.]"
                )

    def _fees_read(self, event: FeesRead) -> str:
        self.fees = event
        about = self._fees_about
        fees = "; ".join(
            f"{f.label}: {f.value}" + (f" {f.note}" if f.note else "") for f in event.fees
        )
        status = "; ".join(event.status)
        if not fees and not status:
            self._answered(
                "show_fees",
                "show_fees not done: the admission page showed no fees or admission lines. "
                "Say plainly that you cannot see them right now and that the page is in front "
                "of them; never guess.",
            )
            return "[The admission page showed no fees and no admission lines just now.]"
        heading = f"{event.heading}: " if event.heading else ""
        note = "[The admission page, read just now in the visitor's browser."
        note += f" {heading}{fees}." if fees else " No fees are on it."
        note += f" Admission: {status}." if status else ""
        note += " These are the only values and dates to quote.]"
        ask = _SAY_STATUS if about == "admission" or not fees else _SAY_FEES
        self._answered("show_fees", f"show_fees done. {ask}")
        return note

    def _events_read(self, event: EventsRead) -> str:
        self.events = event
        query = self._events_query
        chosen = event.events
        if query:
            want = [w for w in re.findall(r"[a-z0-9]+", fold(query)) if len(w) > 2]
            month = _month_of(query)
            hits = [
                e
                for e in event.events
                if (month is not None and int(e.date[5:7] or 0) == month)
                or (want and all(w in fold(e.title) for w in want))
            ]
            chosen = hits
        listed = chosen[:_EVENTS_IN_NOTE] or event.events[:_EVENTS_IN_NOTE]
        lines = "; ".join(
            f"{_date_words(e.date)}{f' {e.time}' if e.time else ''}: {e.title}" for e in listed
        )
        if not event.events:
            self._answered(
                "show_events",
                "show_events done, but the calendar has nothing coming up. Say so, and that the "
                "calendar is on their screen.",
            )
            return "[The school's calendar, read just now: nothing coming up.]"
        ask = _SAY_EVENTS if chosen else _SAY_NO_EVENTS
        self._answered("show_events", f"show_events done. {ask}")
        lead = f" matching '{query}'" if query and chosen else ""
        return (
            f"[The school's public calendar, read just now in the visitor's browser; the next "
            f"events{lead}: {lines}. Only these dates are to be quoted.]"
        )

    def _contact_used(self, event: ContactUsed) -> str:
        if event.via == "email":
            self._talk_through(
                "The visitor pressed the email button: the email to admissions is open in their "
                "own mail app. Say in a sentence that it is ready there for them to review and "
                "send; never that it was sent."
            )
            return "[The visitor opened the email to admissions in their own mail app.]"
        if event.via == "phone":
            return "[The visitor pressed the admissions phone number on the card.]"
        return "[The visitor closed the contact card.]"

    def _read_in_screen(self) -> None:
        """The tabs and the page in front, once per change, ahead of what they say."""
        if self._tabs_unseen and len(self.tabs) > 1:
            listed = "; ".join(
                f"{t.tab_id}: {t.title or t.url}"
                + (" (in front)" if t.tab_id == self._active else "")
                for t in self.tabs
            )
            self._note(f"[The visitor's open Saint George's tabs — {listed}.]")
        self._tabs_unseen = False
        if not self._page_unseen or self.page is None:
            return
        self._page_unseen = False
        p = self.page
        where = {
            "home": "the home page",
            "unit": "a unit's page",
            "admission": "an admission page",
        }.get(p.kind, "a page")
        note = f"[The tab in front shows {where}: “{p.title or p.path}” ({p.path})."
        if p.headings:
            note += f" Its headings: {_clip(p.headings, _HEADINGS_IN_NOTE)}."
        if p.faqs:
            note += f" Its accordions: {_clip(p.faqs, _FAQS_IN_NOTE)}."
        if p.links:
            labels = [x.label or x.url for x in p.links]
            note += f" Its documents and links: {_clip(labels, _LINKS_IN_NOTE)}."
        self._note(note + "]")

    def _note(self, text: str) -> None:
        self.append_to_context(types.Content(role="user", parts=[types.Part(text=text)]))

    # ─── Talk-throughs and one move at a time ───────────────────────────

    def _talk_through(self, ask: str) -> None:
        self._talk = ask
        self._shorten_idle()

    def _holding_floor(self) -> bool:
        """Whether a turn of his is under way, or his words are still playing."""
        playing = self._playing > 0 and time.monotonic() - self._played_at < _PLAYOUT_MAX_S
        return self._turns > 0 or playing

    def _shorten_idle(self) -> None:
        """The short quiet spell, for something to talk through: set now, or,
        while he holds the floor, once he has finished. Requests made meanwhile
        are one, and what they were for is said together."""
        if self._holding_floor():
            self._idle_deferred = True
            return
        self._idle_deferred = False
        if not self._idle_short:
            self._idle_short = True
            configure_soon(self.session, Config(idle=IdleConfig(timeout_ms=_TALK_THROUGH_MS)))

    def _floor_free(self) -> None:
        """A turn ended or a unit played out: a short spell put off is set now."""
        if self._idle_deferred and not self._holding_floor():
            self._shorten_idle()

    def _answered(self, command: str, outcome: str) -> None:
        """The page answered a move he sent: he says what it did in the next
        short quiet spell, unless the visitor speaks first. A move queued
        behind this one goes to the page now, or, if this one failed, is
        dropped and said."""
        if command not in self._sent:
            return
        del self._sent[command]
        if (queued := self._queued) is not None and not self._busy():
            self._queued = None
            name = queued.__voqal_action__
            if outcome.startswith(f"{command} done"):
                logger.info("saintgeorge: {} answered; sending the {} queued", command, name)
                self._send(queued)
            else:
                outcome += f" (so {name}, asked for while it ran, was not sent)"
        self._outcomes.append(outcome)
        self._shorten_idle()

    def _busy(self) -> str | None:
        """The move on the page that has not answered yet, if it is still
        within the time it takes: one at a time."""
        now = time.monotonic()
        for command, until in self._sent.items():
            if until > now:
                return command
        return None

    def _send(self, action: Action) -> None:
        command = action.__voqal_action__
        if command in _MOVE_TAKES_S:
            self._sent[command] = time.monotonic() + _MOVE_TAKES_S[command]
        self.session.dispatch(action)

    def _page_move(self, action: Action, line: str) -> str | None:
        """Send a move the page answers, or, while the last one is still under
        way, queue it to follow: ``None`` when sent, else what the tool says.
        Only the latest queued move is kept."""
        if (running := self._busy()) is None:
            self._queued = None
            self._send(action)
            landed(_LANDED[line][self.spoken])
            return None
        self._queued = action
        landed(_LANDED["queued"][self.spoken])
        logger.info("saintgeorge: {} queued behind {}", action.__voqal_action__, running)
        return (
            f"Queued, not sent yet: the page is still working on {running}. It goes to the page "
            "as soon as the page answers that. Say in a few words that you will do it as soon as "
            "the page is ready; never that it is done, and do not call it again."
        )

    def _take_ask(self) -> str | None:
        """What he has to talk through now — the page's answers to his moves,
        a button the visitor pressed — and nothing left after."""
        asks: list[str] = []
        if self._outcomes:
            asks.append(
                "The page answered what you sent it: "
                + " ".join(self._outcomes)
                + " Speak in the language you speak now. Never say something is done that the "
                "page did not confirm."
            )
            self._outcomes = []
        if self._talk is not None:
            asks.append(self._talk)
            self._talk = None
        return " ".join(asks) or None

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
        """The page and accordion ``asked`` names: a grade by its unit, else by
        its words on any page, else the best accordion search hit."""
        for _, path, grades in UNITS:
            if (g := _match(asked, grades)) is not None and norm(g) == norm(asked):
                return path, g
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
        """Read and search the school's knowledge; read the fees and the
        calendar off the visitor's screen; put up an email to admissions; open
        documents and links; move between their tabs; switch language."""
        return [
            self.read_topic,
            self.search_site,
            self.show_fees,
            self.show_events,
            self.show_contact_card,
            self.open_link,
            self.switch_tab,
            self.set_language,
        ]

    @needs_result_now
    async def read_topic(self, request: TopicRequest) -> str:
        """Read one of the school's knowledge topics before answering from it."""
        topic = self.kb.topics.get(request.topic)
        if topic is None:
            return f"No topic '{request.topic}' is written yet: use search_site."
        return topic.text

    @needs_result_now
    async def search_site(self, request: SearchRequest) -> str:
        """Search saintgeorge.cl's pages, sections, accordions and documents.
        Each result names the page path and the heading or accordion to take
        them to."""
        hits = self.kb.search(request.query, _SEARCH_HITS)
        if not hits:
            return (
                f"Nothing on saintgeorge.cl matches '{request.query}'. Try other words in "
                "Spanish, or offer to write to admissions."
            )
        out: list[str] = []
        for h in hits:
            if h.kind == "faq":
                out.append(f"[accordion on {h.path}] {h.title}\n  {h.snippet}")
            elif h.kind == "link":
                out.append(f"[document or link on {h.path}] {h.title}")
            elif h.kind == "card":
                out.append(f"[card on {h.path}] {h.title}\n  {h.snippet}")
            else:
                where = f", heading: {h.section}" if h.section else ""
                out.append(f"[page] {h.title} — path: {h.path}{where}\n  {h.snippet}")
        return "\n".join(out)

    async def show_fees(self, request: FeesRequest) -> str:
        """Take the visitor to the admission page and read its reference fees
        and admission status off their own screen. The values reach you in a
        bracketed line moments later: say a few words now ("I'm bringing up the
        fees"), never a number."""
        self._fees_about = request.about
        action = ShowFees(path=ADMISSION_PATH, about=request.about)
        if (queued := self._page_move(action, "fees")) is not None:
            return queued
        return (
            "Sent: the page is opening the admission page and reading it. The values reach you "
            "in a bracketed line once it has; until then, say no fee or date."
        )

    async def show_events(self, request: EventsRequest) -> str:
        """Read the school's public calendar in the visitor's browser and open
        the calendar page. The next events reach you in a bracketed line
        moments later: say a few words now, never a date."""
        self._events_query = request.query.strip()
        action = ShowEvents(path=CALENDAR_PATH)
        if (queued := self._page_move(action, "events")) is not None:
            return queued
        return (
            "Sent: the calendar is being read in the visitor's browser. The events reach you in "
            "a bracketed line once it is; until then, say no date."
        )

    async def show_contact_card(self, request: ContactRequest) -> str:
        """Put up a card with a ready email to the admissions office, in the
        language of the call, and its phone. Only once you have the parent's
        name, the child's age or grade, and their question. The parent opens
        the email and sends it themselves: say so, never that it was sent."""
        missing = [
            what
            for what, value in (
                ("their name", request.parent_name),
                ("the child's age or the grade", request.child_age or request.grade),
                ("their question", request.question),
            )
            if not value.strip()
        ]
        if missing:
            return f"Not shown: ask for {' and '.join(missing)} first, one question at a time."
        fields = (request.parent_name, request.child_age, request.grade, request.question)
        if any(_RUT.search(f) for f in fields):
            return (
                "Not shown: a RUT is never written in the email. Leave it out, and tell the "
                "visitor admissions will ask for what it needs."
            )
        subject, body = contact_email(request, self.spoken)
        card = ShowContactCard(
            to=ADMISSIONS_EMAIL,
            subject=subject,
            body=body,
            phone=ADMISSIONS_PHONE,
            language=self.spoken,
        )
        if (queued := self._page_move(card, "card")) is not None:
            return queued
        return (
            f"Card sent to the page: an email to {ADMISSIONS_EMAIL}, subject '{subject}', and the "
            "phone. Say that they press its button to open the email in their own mail app and "
            "send it themselves. Nothing is sent by you."
        )

    async def open_link(self, request: LinkRequest) -> str:
        """Open a document or link in a new tab: a PDF or link by its words, the
        musical's tickets, or — only when the visitor asks for it — a families'
        login (Schoolnet, Pago Colegiatura, LIRMI) or the careers portal."""
        url, label = self._link(request)
        if url is None:
            return label
        self._move(OpenLink(url=url, label=label), "link")
        if request.kind in ("schoolnet", "tuition", "lirmi"):
            return f"Opened {label} in a new tab. The visitor logs in there themselves."
        return f"Opened '{label}' in a new tab."

    def _link(self, request: LinkRequest) -> tuple[str | None, str]:
        """The link to open and its label, or ``None`` and why not."""
        live = list(self.page.links) if self.page is not None else []
        if request.kind != "document":
            host = _PORTAL_HOSTS[request.kind]
            for link in live:
                if host in link.url.lower() and is_link_url(link.url):
                    return link.url, link.label or _PORTALS[request.kind][0]
            label, url = _PORTALS[request.kind]
            return url, label
        want = request.label.strip()
        if not want:
            labels = "; ".join(x.label for x in live if x.label) or "none on this page"
            return None, f"Not opened: say which document, by its words. On the page: {labels}."
        labels = [f"{x.label} {x.near}".strip() for x in live]
        if (hit := _match(want, labels)) is not None:
            link = live[labels.index(hit)]
            if is_link_url(link.url):
                return link.url, link.label or want
        known = self.kb.links()
        here = [x for path, x in known if path == self._path]
        for pool in (here, [x for _, x in known]):
            pool_labels = [f"{x.label} {x.near}".strip() for x in pool]
            if (hit := _match(want, pool_labels)) is not None:
                link = pool[pool_labels.index(hit)]
                if is_link_url(link.url) and canonical_url(link.url) in self.kb.link_urls():
                    return link.url, link.label or want
        listed = "; ".join(x.label for x in live if x.label) or "none on this page"
        return None, (
            f"Not opened: no document '{want}' on the page or in the site pages. On the page: "
            f"{listed}. Use search_site."
        )

    async def switch_tab(self, request: TabRequest) -> str:
        """Bring another of the visitor's Saint George's tabs to the front."""
        tab = next((t for t in self.tabs if t.tab_id == request.tab_id), None)
        if tab is None:
            listed = ", ".join(f"{t.tab_id} ({t.title})" for t in self.tabs) or "none"
            return f"Not switched: no tab '{request.tab_id}'. Open tabs: {listed}."
        if len(self.tabs) < 2:
            return "Not switched: this is the only tab open. Say so."
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
        logger.info("saintgeorge: language -> {} (asked)", request.language)
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
_WEEKDAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def _month_of(query: str) -> int | None:
    """The month a query names ("noviembre", "in December"), or ``None``."""
    found = [_MONTHS[w] for w in re.findall(r"[a-z]+", fold(query)) if w in _MONTHS]
    return found[0] if len(found) == 1 else None


def _date_words(iso: str) -> str:
    """``2026-10-27`` as the note gives it: with its weekday, so he can say it."""
    try:
        day = date.fromisoformat(iso)
    except ValueError:
        return iso
    return f"{iso} ({_WEEKDAYS[day.weekday()]})"


__all__ = [
    "Cue",
    "FocusTab",
    "LanguageChanged",
    "Navigate",
    "OpenFaq",
    "OpenLink",
    "SaintGeorgeBrain",
    "ShowContactCard",
    "ShowEvents",
    "ShowFees",
    "ShowSection",
]
