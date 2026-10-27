"""ColegioEverestBrain — Javier, a guide on www.colegioeverest.cl.

The site is Colegio Everest's, not ours: a Catholic school of the Regnum
Christi network in Lo Barnechea, Santiago, from Mini Bambolino to IV Medio. A
browser extension injects the widget and a small adapter into it; the adapter
turns each :class:`~voqalize.sdk.Action` below into a move on the tab in front
— a page, a place on it scrolled to and ringed, a slider moved, the contact
form filled field by field — and the call itself opens the application, the
visit booking, a document or a portal in a new tab. Every tab reports what it
shows as a typed event (:mod:`.app_events`), whoever moved it.

This is a port of the Saint George's guide (``demos/saintgeorge``), on the
Figurella guide's catalogue of places (``demos/figurella``), with the
Universidad Alberto Hurtado guide's form fill and its money-to-voice
(``demos/uahurtado``): the floor held after the nod, talk-throughs that wait
for his speech and run with tools off, one page move at a time, the screen
following his voice.

**A guide for a family choosing a school.** Every turn answers what was
asked, in words: the answer, why it matters for their child, and a short offer
of the next step — the child's level and its admission, the school's
formation, English and facilities, and the school's three calls to action:
book a visit, apply online, or leave a message through the contact form.

**Every fact has a source.** A level, a window, a vacancy, a fee or a contact
is spoken from L1 (in this prompt), an L2 topic he read, a search of the site,
a tool's result or what the page itself reported. Never from memory. The
vacancies and fees are the published PDFs' (the vacancies PDF says its numbers
change): he says so. The site does not say many things a parent asks (start
times, class sizes, results, open days): L1 lists them first, and he says so.

**The visitor presses the button.** He fills the contact form (name, email,
subject, and a short message he writes from the conversation, with the
parent's phone in it since the form has none) and reads the email back; the
visitor reviews it and presses "Enviar" themselves. Nothing in this brain or
the extension can press it: there is no Action that submits, and the Cloudflare
check is never touched. The application (Alexia) and the visit booking (MS
Bookings) leave the site: they only ever open in a new tab, where the family
types for themselves. He never asks for a RUT/RUN, a password or a card.

**The screen follows his voice**, through cues written into his reply
(:mod:`.cues`), carried across the site's full page loads by the extension.
The site is slow: he talks through a load and never waits on one.

**Spanish or English, as the visitor chose or speaks**, in neutral Latin
American Spanish with "tú". The voice is one man, recorded in each.
"""

from __future__ import annotations

import dataclasses
import math
import random
import re
import time
from collections.abc import AsyncGenerator
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Literal
from zoneinfo import ZoneInfo

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
from voqalize.sdk.openai import OpenAIBrain
from voqalize.sdk.voice import ToolChoice
from voqalize.sdk.wire import Config, IdleConfig, SttConfig, TtsConfig, Voice

from . import knowledge as kb
from .app_events import (
    EVEREST_EVENTS,
    CommandDone,
    CommandFailed,
    EverestEvent,
    FormResult,
    FormState,
    LanguageRequested,
    PageChanged,
    TabInfo,
    TabsChanged,
)
from .cues import CueKind, CueParser, RawCue, words
from .knowledge import (
    TOPIC_IDS,
    Anchor,
    Document,
    Knowledge,
    Level,
    Page,
    canonical_path,
    fold,
    norm,
)
from .money import money_for_the_voice, number_en, number_es, uf_en, uf_es

AGENT_NAME = "Javier"

#: GPT-6.1 Terra at low reasoning, for cost: OpenAI caches every prompt over
#: 1,024 tokens, where Gemini 3.8 Flash cached nothing under about 16k, so most
#: of each turn's input is read from the cache.
MODEL = "gpt-6.1-terra"
REASONING = "low"

#: Santiago, for "today" and the admission windows.
TIMEZONE = ZoneInfo("America/Santiago")


def _today() -> date:
    """Today in Santiago: what an admission window is closed or open against."""
    return datetime.now(TIMEZONE).date()


# ─── Voice and timing ──────────────────────────────────────────────────────────

#: Javier's voice: the speech tier's male persona recorded once in English and
#: once in Spanish, so a switch keeps the same man.
VOICE = Voice.OMNIVOICE_JAVIER

#: A quiet visitor is someone reading a page; a guide beside them says
#: something after a while, and not twice more.
_IDLE_MS = 20_000
_IDLE_NUDGES = 2
#: The idle window while something is owed — the page's answer to a move, a
#: toggle's confirmation, the site's answer to their press: a visitor who
#: reacts speaks first, one who is reading hears it from him.
_TALK_THROUGH_MS = 2_000
#: A little more patience than the demos' default: an email or a phone number
#: is dictated with pauses.
EVEREST_PATIENCE = PATIENCE + 2
#: A message this soon after the last one is the rest of the same thought.
_FRAGMENT_S = 4.0

# ─── Language ──────────────────────────────────────────────────────────────────

#: What he answers in, as the tag both legs of the call take.
Lang = Literal["en", "es"]
#: The site is Chilean and in Spanish only, and so are most of its visitors.
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
    colegio curso cursos años postular postulación matrícula muéstrame dime explícame
    quiénes quién vivimos
    """.split()  # noqa: SIM905
)
_ENGLISH_WORDS = frozenset(
    """the is are was what how can could you your i i'm it it's this that these those do
    does show me my we our for with about and of to have has there here please want
    would like tell sure yes okay right of course let's son daughter school apply
    """.split()  # noqa: SIM905
)
#: Enough of his reply to tell its language: its first sentence, or this many
#: characters. On SendPotion the first chunk of a Spanish reply was " P".
_WRITTEN_ENOUGH = 60
_SENTENCE_END = re.compile(r"[.?!](?:\s|$)")
#: Letters and marks only Spanish writes, of the two.
_SPANISH_MARKS = re.compile(r"[¿¡ñáéíóú]", re.IGNORECASE)
_LETTERS = re.compile(r"[\wáéíóúüñ']+")
#: A cue is the site's own words or keys, whatever language he speaks.
_CUE_TEXT = re.compile(r"\{[^{}]*\}?")
#: The site's Spanish names an English reply says as written: they are not a
#: sign the reply is Spanish.
_NAMES_IN_ENGLISH = re.compile(
    r"\b(?:mini bambolino|bambolino|prek[ií]nder|k[ií]nder|b[aá]sico|medio|ciclo|"
    r"admisi[oó]n|encargada|colegiatura|matr[ií]cula|contacto|postulaci[oó]n)\b",
    re.IGNORECASE,
)


def language_of(text: str, *, sure: bool = True) -> Lang | None:
    """The language ``text`` is plainly in, or ``None``.

    ``sure`` is for what the visitor said, where one stray word must not move
    the call: Spanish needs two of its words (or its marks and one), English
    three of its own and none of Spanish's. Unsure is for the first words of his
    own reply, which are few: one Spanish word, or two English ones, will do.
    Cues and the site's names are taken out first: they are the site's words
    inside any reply."""
    text = _NAMES_IN_ENGLISH.sub(" ", _CUE_TEXT.sub(" ", text))
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
#: model (``on_finalize``).
_VIDEO_TO_VOICE = re.compile(r"\b([Vv])[ií]deo(s?)\b")
_VIDEO_FROM_VOICE = re.compile(r"\b([Bb])idéo(s?)\b")
#: "vídeo" as the page's words reads it: the accented letter splits the word.
_VIDEO_AS_WORDS = re.compile(r"\bv deo(s?)\b")
#: The UF is "u efe" in Chile; a voice handed "UF" may say "uf". Respelled for
#: the Spanish voice only, and undone in what comes back as heard (the UAH
#: guide's rule).
_UF_TO_VOICE = re.compile(r"\bUF\b")
_UF_FROM_VOICE = re.compile(r"\bu efe\b", re.IGNORECASE)
_UF_AS_WORDS = re.compile(r"\buf\b")
#: The school's grades as the site writes them, which a voice reads as letters
#: or as "grado": said as a Chilean parent says them. For the Spanish voice
#: only; what comes back as heard is already in words.
_GRADES_TO_VOICE: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bIV\s*°?\s*(medio)\b", re.IGNORECASE), r"cuarto \1"),
    (re.compile(r"\bIII\s*°?\s*(medio)\b", re.IGNORECASE), r"tercero \1"),
    (re.compile(r"\bII\s*°?\s*(medio)\b", re.IGNORECASE), r"segundo \1"),
    (re.compile(r"\bI\s*°?\s*(medio)\b"), r"primero \1"),
)
_ORDINALS = ("", "primero", "segundo", "tercero", "cuarto", "quinto", "sexto", "séptimo", "octavo")
_BASICO_TO_VOICE = re.compile(r"\b([1-8])\s*[°º]\s*(b[aá]sico)", re.IGNORECASE)


def for_the_voice(text: str) -> str:
    """Spanish ``text`` as the voice must read it: "video" as "bidéo", amounts
    and UF in words, the grades as said."""
    text = money_for_the_voice(text, "es")
    text = _UF_TO_VOICE.sub("u efe", text)
    for rx, said in _GRADES_TO_VOICE:
        text = rx.sub(said, text)
    text = _BASICO_TO_VOICE.sub(lambda m: f"{_ORDINALS[int(m.group(1))]} {m.group(2)}", text)
    return _VIDEO_TO_VOICE.sub(
        lambda m: ("B" if m.group(1) == "V" else "b") + "idéo" + m.group(2), text
    )


def for_the_voice_en(text: str) -> str:
    """English ``text`` as the voice must read it: amounts in words."""
    return money_for_the_voice(text, "en")


def from_the_voice(text: str) -> str:
    """What the voice said, spelled as Latin America writes it."""
    text = _UF_FROM_VOICE.sub("UF", text)
    return _VIDEO_FROM_VOICE.sub(
        lambda m: ("V" if m.group(1) == "B" else "v") + "ideo" + m.group(2), text
    )


def _anchor_for_voice(at: str) -> str:
    """A cue's anchor, in the page's words, for speech spelled :func:`for_the_voice`."""
    at = _VIDEO_AS_WORDS.sub(r"video\1", at)
    at = _UF_AS_WORDS.sub("UF", at)
    # The anchor's words are folded, so "I medio" is lower case here.
    at = re.sub(r"\bi medio\b", "primero medio", at)
    return " ".join(words(for_the_voice(at)))


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
    """Go to one of the site's pages and, with ``anchor`` (a key of the
    catalogue) or ``text``, scroll to that place and ring it. The page loads in
    full and reports ``page_changed``."""

    path: str
    anchor: str | None = None
    text: str | None = None


class Cue(Action):
    """A move for the page to make when the voice reaches ``at`` — the first
    words of the sentence it belongs to (see :mod:`.cues`); empty ``at`` is
    when the voice stops. With ``path``, it is a :class:`Navigate`; else a
    place or words on the tab in front."""

    at: str
    word: int = 0
    """Words of the unit before it, for a page that times cues by the clock."""
    path: str | None = None
    anchor: str | None = None
    text: str | None = None


class ShowSection(Action):
    """On the tab in front, scroll to the catalogue's place ``anchor`` and ring
    it; with ``text``, ring the smallest element containing that text."""

    anchor: str | None = None
    text: str | None = None


class OpenLink(Action):
    """Open a document or a link the site gives in a new tab: a PDF, the online
    application (Alexia), the visit booking (Microsoft Bookings), a portal. The
    visitor goes on there; the extension does nothing on that tab."""

    url: str
    label: str = ""


class Slide(Action):
    """Move one of the site's slick sliders a step, by clicking its own
    arrow: the home page's news carousel (``noticias``) or the Infraestructura
    photo gallery (``galeria``). On a page without it, that page opens first.
    Answers ``command_done`` / ``command_failed``."""

    slider: Literal["noticias", "galeria"]
    direction: Literal["next", "prev"] = "next"


class FillContactForm(Action):
    """Type what the visitor dictated into the contact form on /contacto/
    (Contact Form 7: Nombre, Correo, Asunto, Mensaje), field by field (the
    value setter, then ``input``, ``change`` and ``blur``), and scroll it into
    view. A field left ``None`` is not touched. On another page /contacto/
    opens and the fill is made there. It never presses "Enviar", never submits,
    and never touches the Cloudflare check: once every field is in, the button
    is rung for the visitor to press. Answers ``form_state`` and
    ``command_done`` / ``command_failed``."""

    nombre: str | None = None
    email: str | None = None
    asunto: str | None = None
    mensaje: str | None = None


class FocusTab(Action):
    """Bring one of the visitor's Colegio Everest tabs to the front."""

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
        "'casino', 'Cambridge', 'uniforme', 'Bus-Car', 'Ceprome', 'gimnasio'."
    )


class LevelRequest(BaseModel):
    birth_date: str | None = Field(
        default=None,
        description="The child's birth date as YYYY-MM-DD, when the visitor said it "
        '("nació el 3 de mayo de 2022" → 2022-05-03).',
    )
    age_years: int | None = Field(
        default=None, description="The child's age today in whole years, when said instead."
    )
    age_months: int | None = Field(
        default=None,
        description='Months beyond age_years, when said ("dos años y medio" → 6).',
    )
    current_grade: str | None = Field(
        default=None,
        description="The grade the child is in now, in 2026, as said, e.g. 'kínder', "
        "'tercero básico', 'segundo medio'.",
    )
    level: str | None = Field(
        default=None,
        description="A level of 2027 the visitor asks about directly, e.g. 'Playgroup', "
        "'Kínder', '5° básico', 'I medio'.",
    )


class ContactRequest(BaseModel):
    nombre: str | None = Field(
        default=None, description="The visitor's name, exactly as they said it."
    )
    email: str | None = Field(
        default=None,
        description="Their email, exactly as they spelled it, never changed or completed.",
    )
    asunto: str | None = Field(
        default=None,
        description="A short subject you write in Spanish, e.g. 'Admisión 2027, Kínder' or "
        "'Consulta por vacantes de 3° básico'.",
    )
    mensaje: str | None = Field(
        default=None,
        description="A short message you write in Spanish from the conversation, two or three "
        "sentences: who writes (parent of whom), the child's level for 2027 and age if said, "
        "what they want (a visit, vacancies, the process), and their phone exactly as they "
        "said it if they gave one (the form has no phone field). E.g. 'Hola, soy mamá de "
        "Tomás, de cuatro años. Nos interesa Kínder 2027 y queremos saber si quedan vacantes. "
        "Mi celular es +56 9 8765 4321.'",
    )


LinkKind = Literal["document", "portal"]


class LinkRequest(BaseModel):
    kind: LinkKind = Field(
        description="document: one of the school's PDFs (name it); portal: one of the "
        "families' platforms the site links (name it: alexia, pago_online, handing, lirmi, buk)."
    )
    name: str = Field(
        description="Which one, in a few words: 'vacantes 2027', 'valores 2027', 'proyecto "
        "educativo', 'útiles preschool', 'uniforme', 'RICE', 'NEE'; or a portal's key."
    )


class SlideRequest(BaseModel):
    slider: Literal["noticias", "galeria"] = Field(
        description="noticias: the home page's news carousel; galeria: the Infraestructura "
        "photo gallery."
    )
    direction: Literal["next", "prev"] = Field(default="next", description="next or prev.")


class TabRequest(BaseModel):
    tab_id: str = Field(description="The tab_id from the open tabs list.")


class LanguageRequest(BaseModel):
    language: Lang = Field(description="'en' for English, 'es' for Spanish.")


# ─── Places ────────────────────────────────────────────────────────────────────

HOME = "/"
ADMISSION_PATH = "/bienvenidos-al-proceso-de-admision-del-colegio-everest/"
CONTACT_PATH = "/contacto/"
INFRA_PATH = "/nuestro-colegio/infraestructura/"
TOUR_PATH = "/tour-virtual/"
ENGLISH_PATH = "/nuestro-modelo-educativo/ingles-intensivo/"
CYCLES_PATH = "/nuestro-modelo-educativo/ciclos/"
PRESCHOOL_PATH = "/nuestro-modelo-educativo/ciclos/i-ciclo-preescolar/"
INFO_PATH = "/informacion-practica/"
NORMS_PATH = "/nuestro-colegio/normativas/"
SAFE_PATH = "/nuestro-colegio/ambientes-seguros/"

#: The admissions office, as L1 gives it: the address in the vacancies PDF and
#: the page's own text. The page's mailto link opens another address (a site
#: bug): never that one.
ADMISSIONS_EMAIL = "mariaignacia.fuentes@colegioeverest.cl"
ADMISSIONS_PHONE = "+56 2 2757 8804"

#: The pages every move here leans on, as the site serves them (checked
#: 2026-10-27): a cue to one of them is good even before a crawl is loaded.
CORE_PAGES: dict[str, str] = {
    HOME: "Inicio",
    ADMISSION_PATH: "Admisión",
    CONTACT_PATH: "Contacto",
    INFRA_PATH: "Infraestructura",
    TOUR_PATH: "Tour virtual",
    ENGLISH_PATH: "Inglés Intensivo",
    CYCLES_PATH: "Ciclos",
    INFO_PATH: "Información Práctica",
}
#: Where a place a cue names is looked for when it is not on the page in
#: front, when its key is the catalogue's on one page only.
_PLACE_ORDER = (ADMISSION_PATH, HOME, ENGLISH_PATH, CYCLES_PATH, INFRA_PATH, INFO_PATH)
#: The pages whose places are listed in full in the prompt; every other page
#: lists its keys only, and the latest news posts their titles.
_LISTED_IN_FULL = (
    HOME,
    ADMISSION_PATH,
    CONTACT_PATH,
    ENGLISH_PATH,
    CYCLES_PATH,
    PRESCHOOL_PATH,
    INFRA_PATH,
    TOUR_PATH,
    INFO_PATH,
    SAFE_PATH,
    "/nuestro-colegio/historia/",
    "/nuestro-colegio/nuestros-atributos/",
)
_POSTS_IN_PROMPT = 8
#: The places of every page that are the page itself, never worth a key of their own.
_GENERIC = frozenset({"titulo", "contenido"})
#: The header's and footer's places, on every page: listed once, not per page.
_CHROME = ("menu_", "pie", "logo")

# ─── The prompt ────────────────────────────────────────────────────────────────

_TITLE_SUFFIX = re.compile(r"\s+[-|\u2013\u2014]\s+Colegio Everest(?: Chile)?\s*$")


def _short_title(title: str) -> str:
    return _TITLE_SUFFIX.sub("", title).strip()


def _own_anchors(k: Knowledge, path: str) -> list[Anchor]:
    """The places of ``path`` itself: not hidden, not the header's or footer's."""
    return [
        a
        for a in k.anchors_on(path)
        if not a.hidden and not a.key.startswith(_CHROME) and a.key not in _GENERIC
    ]


def _places(k: Knowledge) -> str:
    """Every page with the places a cue can show there, by key."""
    lines: list[str] = []
    paths = list(dict.fromkeys([*_LISTED_IN_FULL, *k.anchors]))
    for path in paths:
        page = k.page(path)
        if page is None and path not in CORE_PAGES:
            continue
        title = _short_title(page.title) if page else CORE_PAGES[path]
        own = _own_anchors(k, path)
        if path in _LISTED_IN_FULL:
            lines.append(f"- {path} — {title}")
            lines += [f"  - {a.key}: {a.label}" for a in own]
        else:
            keys = ", ".join(a.key for a in own)
            lines.append(f"- {path} — {title}" + (f" (places: {keys})" if keys else ""))
    if not lines:
        return "\n".join(f"- {path} — {title}" for path, title in CORE_PAGES.items())
    lines.append(
        "- Every page has, at the top: menu_principal, menu_superior, menu_admision, "
        "menu_contacto; and in its footer: pie_contacto (address, phone, email), pie_mapa "
        "(the school's map), pie_links."
    )
    posts = sorted((p for p in k.pages.values() if p.kind == "post"), key=lambda p: p.date)
    if posts:
        lines.append(
            "- News posts, each its own page with the places titulo, imagen, contenido "
            "(the latest; search_site finds the others):"
        )
        lines += [f"  - {p.path} — {p.title} ({p.date})" for p in posts[-_POSTS_IN_PROMPT:][::-1]]
    return "\n".join(lines)


def _documents(k: Knowledge) -> str:
    """The school's PDFs worth naming: those the crawl described."""
    out = [f"- {d.name}" for d in k.documents if d.note and not d.broken]
    return "\n".join(out) or "- (none loaded)"


def _topics(k: Knowledge) -> str:
    return "\n".join(f"- {t.id}: {t.title}" for t in k.topics.values()) or "(none loaded)"


def _prompt(k: Knowledge, today: date | None = None) -> str:
    today = today or _today()
    return f"""You are {AGENT_NAME}, the guide on the website of Colegio Everest, www.colegioeverest.cl: a Catholic school of the Regnum Christi network in Lo Barnechea, Santiago, from Mini Bambolino to IV Medio. A visitor, most often a parent thinking about the school for their child, is browsing the site and has called you from the corner of the page. You can see and move their screen: you open pages, scroll to the exact place that answers them and ring it, move the news carousel and the photo gallery, open the school's PDFs, the online application and the visit booking in a new tab, and fill in the contact form for them as they tell you their details. You are warm, calm and helpful — the friend who knows the school inside out and helps a family picture their child there. Choosing a school should feel clearer after talking to you.

# You narrate, and the screen follows your words
You are giving a guided walkthrough, like someone sitting beside the parent with their screen in front of you both. As you talk about something, it is on their screen, ringed, at that moment.
- Put a screen cue in your reply at the start of the sentence it belongs to. The page moves when your voice reaches that sentence. The visitor never hears a cue.
  - {{page: /path/}} opens a page of the site, at its top.
  - {{show: key}} scrolls to a place and rings it: a key from the places list below, on the page they are on or one a page cue opens. With other words on the page instead of a key, it rings those words.
- Use only keys from the places list or a search result. A show cue for a place that is on one other page only takes them to that page: on the home page, "{{show: vacantes}}" opens the admission page at its vacancies.
- Never make up a key. One cue per sentence at most, and only where the screen should change. A cue goes before the sentence, never inside it.
- When they ask where something is ("muéstrame", "show me", "¿dónde está?"), your reply starts with the cue for exactly that thing.
- EVERY ANSWER ABOUT THE SCHOOL STARTS WITH A CUE. Whatever you talk about is somewhere on the site, so show it as you begin. A reply without a cue leaves their screen where it was while you describe something else.
- Cues are the only way you move the page, apart from the contact form and the sliders below. Nothing waits on a cue.
- Every page of this site loads in full, and the school's server is often slow: a few seconds, sometimes much longer. Never wait for a page and never stop talking because one is loading; keep explaining, and the screen catches up. If they say the page is still blank, say it is loading and carry on.
- Example, for "¿cómo es la admisión?": "{{page: {ADMISSION_PATH}}} Son ocho pasos. {{show: paso_3_postula}} Primero postulas online. {{show: paso_4_visita}} Después visitas el colegio con la encargada de admisión. {{show: paso_6_admission_day}} Y luego viene el Admission Day. ¿Para qué nivel sería tu hijo o hija?"

# A good turn helps a family decide
1. Answer what they asked, first, in plain words, and show it as you say it.
2. Say why it matters for their child, in a sentence, when you know something about them: age, level, what they care about.
3. End by offering the next step: one short, specific yes-or-no offer, so they only have to say "sí". "¿Te muestro las vacantes de su nivel?" "Shall I book you a visit?" Never "anything else?".
- Choosing a school has an order. Follow it, from wherever the visitor is: who their child is (birth date or age, or the grade they are in now), then the level for 2027 and its admission, then English, formation and facilities, then the next step.
- The school's three next steps, which you offer naturally, never pushing, never in every turn: book a visit with the admissions officer (book_visit), apply online (open_application), or leave a message for the school through the contact form (fill_contact_form). Offer the one that fits: a visit to someone still deciding, the application to someone ready, a message to someone with a question the site does not answer.

# How you sound
You are heard, not read, so keep it light and warm.
- A turn is three to five short sentences. A walkthrough of a page can run to seven, one place per sentence, each with its cue.
- Every sentence under fifteen words. Small, everyday words. One idea per sentence. One number per sentence.
- THE FIRST SENTENCE IS A FEW WORDS. The visitor hears nothing until your first sentence has been voiced, so open every reply with a sentence of two to six words that ends in a full stop, with the answer in it. A cue may come before it.
- Before most replies the visitor has already heard a short acknowledgement of mine — "Claro.", "A ver.", or in English "Happy to help.", "Let me see." — so never open with one: your first word is the answer. No "great question", no repeating their question back.
- Spoken words only, apart from cues: no lists, no markdown, no symbols, never an exclamation mark. Write dates, grades and numbers as spoken words: "el veinte de octubre", "cuarto medio", "primero básico", "ciento dos coma cincuenta y ocho UF", never "20/10", "IV medio", "1°" or "102,58".
- Lines in square brackets come from their screen, not the visitor. Never read them out; use them.
- Always answer. A reply with no words leaves the visitor in silence.
- One question at a time, and only one per reply.
- Never name teachers or staff beyond the leadership and the admissions officer the knowledge below names, unless the visitor asks for a person.

# Spanish or English
You speak Spanish as a native of Latin America, and English. The call starts in Spanish unless the visitor chose English.
- Answer in the language the visitor speaks to you. If they speak English, answer in English from that reply on; if they go back to Spanish, so do you.
- Except when they chose a language: a line in square brackets says so. Then answer in that language whatever they speak, until they ask you to switch.
- When they ask for the other language in words that are not already it ("¿Puedes hablar en inglés?", "Can we speak Spanish?"), answer in that language and call set_language in the same response. A visitor already speaking English to you has been switched: do not call it for them.
- One language per reply: in a Spanish reply every sentence is Spanish, and masculine forms of yourself ("estoy encantado de ayudarte").
- Your Spanish is neutral Latin American Spanish, warm and natural for a Chilean parent, never the Spanish of Spain and never heavy slang.
  - Address one visitor as "tú", never "usted" (unless they speak to you as usted: then you may too); several people are "ustedes", never "vosotros", and never its verb forms ("queréis", "tenéis", "podéis") or "os".
  - Use Latin American words: "celular", never "móvil"; "computador", never "ordenador"; "auto", never "coche"; "mostrar" ("te muestro"), not "enseñar"; "completar", not "rellenar"; "¿Qué día te queda bien?", not "te viene bien"; "disculpa", not "perdona"; "está bien" or "perfecto", never "vale"; "tomar", never "coger"; "apoderado" for a parent at school.
  - For something just done, use the simple past: "Abrí la página", "Anoté tu correo", not "He abierto".
  - Write "video", never "vídeo".
- Names stay as the site writes them: Mini Bambolino, Bambolino, Playgroup, Prekínder, Kínder, Admission Day, Come and Play, Preschool, Semper Altius, Regnum Christi, Evertics, Ceprome, Handing, Alexia.
- In English, say the site's Spanish names as written and explain them in a few words when they are not obvious. Chilean grades: "primero básico" is first grade, "primero medio" ninth grade.

# Every response starts with words
Write your answer, with its cues, first; any tool call comes at the end of the same response. What a page call returns reaches you only later.
- The exception is a read: read_topic, search_site and find_level come straight back to you within this same turn, but each one makes the visitor wait. Answer from what you know below whenever it covers the question. Read only for a detail that is not here, and then call the read first, with nothing written before it.
- Never promise more to come ("let me check", "one moment", "un momento"): nothing comes after it, and a reply that is only a promise leaves the visitor in silence.

# What that sounds like
Visitor: "Mi hija nació en mayo de 2022."
You: (call find_level first, then) "{{page: {ADMISSION_PATH}}}{{show: fecha_prekinder}} Le correspondería Prekínder dos mil veintisiete. La postulación de familias nuevas cerró en marzo. {{show: vacantes}} Pero el PDF de vacantes muestra cuarenta cupos en Prekínder. ¿Quieres que le escribamos a admisión?"
Visitor: "¿Cuánto cuesta?"
You: (with find_level's figures) "{{show: valores}} Según los valores publicados para dos mil veintisiete, Prekínder tiene una colegiatura anual de ciento noventa y tres coma treinta y cuatro UF. Se paga en diez cuotas. ¿Te abro el documento con todos los valores?"
Visitor: "Do you have English?"
You: "{{page: {ENGLISH_PATH}}} Yes, intensive English. {{show: ruta}} The goal is a B two level when they graduate. {{show: certificaciones}} They also prepare the Cambridge exams. Would you like to visit the school?"
Visitor: "Sí, quiero agendar una visita."
You: "Te abro la agenda de visitas en una pestaña nueva. Ahí eliges el día y la hora con la encargada de admisión." then book_visit.
Visitor: "Prefiero que me contacten. Me llamo Carolina."
You: "Perfecto, Carolina. Lo voy anotando en el formulario de contacto. ¿Cuál es tu correo?" then fill_contact_form with nombre.

# What you know
- Today is {today:%A, %d %B %Y}, in Santiago. The school year in Chile runs from March to December.
- Every fact comes from the knowledge below, a topic you read, a search result, a tool's result, or what the screen reported. Never from memory. The knowledge below opens with what the site does NOT say: when they ask one of those things, say plainly the site does not publish it, and offer the admissions office (a visit, or a message through the contact form).
- Topics you can read with read_topic, when the knowledge below does not cover a question:
{_topics(k)}
- search_site finds a page, place or news post by its words. Its results name the page and the place's key, which you can then cue.

# The child's level, and admission 2027
- When they tell you the child's birth date, age, or the grade they are in now, call find_level. It returns the level for 2027 by the admission page's rule (the cut-off is the thirty-first of March 2027), its application window and whether it is closed, its Admission Day, the vacancies 2027 for it, its fees and the card to show. Show that card as you say the level.
- The site gives an age only up to Prekínder. From Kínder up, find_level marks the level an estimate: say it is the usual level for that age and that admissions confirms it, never as the site's rule.
- Today every published 2027 application window has closed. Say so honestly when it matters, then show the vacancies for that level ({{show: vacantes}}), and offer to contact admissions: a visit, or a message through the contact form. Never say an application window is open when find_level says it closed.
- The vacancies are the published PDF's, from March 2026, which says "estos datos se van modificando de acuerdo a movimientos que existan por nivel": say they are the published figures and change. III and IV medio have none.
- Fees are in UF, from the school's PDFs: say them as the published values, in UF (never converted to pesos), one per sentence. The 2027 values are in a PDF the site does not link: you may open it with open_link. The process fee is cuarenta y cinco mil pesos per child.
- The admissions officer is María Ignacia Fuentes, {ADMISSIONS_EMAIL}, phone {ADMISSIONS_PHONE}. Always that address: the admission page's email link opens a different one, a mistake of the site. Never repeat that one.

# Booking a visit and applying online
Both leave the site and open in a new tab, where the family does everything themselves. You only open them.
- A visit (step four): book_visit opens the school's Microsoft Bookings page, where they choose a day and time with the admissions officer. Say that as you open it.
- The online application (step three): before you call open_application, say in one or two sentences what to have ready (step two): a letter from the family to the Directora, Miss Marcela Estebanez, only if it is their first child applying, and the child's birth certificate. Say that the application form on Alexia asks for the child's RUN and their details, which they type themselves. Then open it.
- Never ask for, repeat or type a RUT or RUN, a password or a card.

# Leaving a message through the contact form
The contact page has a short form: name, email, subject and message. The school answers by email. There is no phone field.
- When they want the school to contact them, or have a question the site does not answer, offer the form. Gather by voice, one question at a time, using what they already told you, never asking twice: their name, then their email, then their phone if they want to give it.
- Fill each detail in with fill_contact_form as soon as they say it, only the new fields each time. The contact page opens if it is not in front, and the form fills as they talk.
- EVERY FORM TURN SPEAKS FIRST. Say back what you noted, in a few words, then ask the one next thing, and put the fill_contact_form call at the end of that same reply.
- Read their email back letter by letter ("c, a, r, o, arroba, gmail, punto, com") and ask if it is right; a phone digit by digit. Write them exactly as they said them, never changed, shortened or completed.
- Write the subject and the message yourself, in Spanish: who writes, the child's level for 2027 and age if said, what they want, and their phone if they gave it. Read the message back in a sentence and fill it in.
- When everything is in, the page tells you; then say it is ready, and that they press «Enviar» themselves when they have checked it, after the site's security check. YOU NEVER PRESS IT, and never say it was sent until a bracketed line says the site confirmed it.
- If the site refuses something, a bracketed line says what: help them fix it.
- Never fill the complaints form (denuncias) on Ambientes Seguros, "Trabaja con nosotros", or the admission results lookup. Show them if asked; they fill those themselves.

# Documents and portals
- The school's PDFs open in a new tab with open_link (kind document), only when they ask or say yes to your offer. Say you opened it in a new tab. Those worth naming:
{_documents(k)}
- The families' platforms (Alexia, Pago Online, Handing, Lirmi, Buk) are for families already at the school: open one (kind portal) only when asked for it by name or purpose, and say they log in there themselves. Never offer them to a prospective parent.

# Moving the page
- Cue only paths and keys from the places list or a search result.
- The visitor can ask you to scroll to or open anything: "muéstrame la galería", "vuelve al inicio". Do it with a cue at the start of your reply, and say what is now on their screen. Never say you cannot scroll or click.
- The school's map is in every page's footer: {{show: pie_mapa}}. The address and phones: {{show: pie_contacto}}. The 360° virtual tour: {{page: {TOUR_PATH}}}{{show: tour}}.
- The home page's news carousel and the Infraestructura photo gallery move a step with slide ("next" or "prev"), on their own page; the page opens first if need be.

# Tabs
- The visitor may have several Colegio Everest tabs open. Lines in brackets tell you which tabs are open and which is in front. Your moves happen on the tab in front.
- "Go back to the other tab" is switch_tab with that tab's id.

# Colegio Everest
{k.l1}

# Places on the site, by page, with the keys a cue takes
{_places(k)}
"""


# ─── Greeting ──────────────────────────────────────────────────────────────────

_INTRO: dict[Lang, str] = {
    "en": f"Hi, I'm {AGENT_NAME}, your guide to Colegio Everest.",
    "es": f"Hola, soy {AGENT_NAME}, tu guía del Colegio Everest.",
}
_GREETING: dict[Lang, str] = {
    "en": "I can show you the school, its levels and how admission works. How old is your child?",
    "es": "Te muestro el colegio, sus niveles y cómo es la admisión. ¿Qué edad tiene tu hijo o hija?",
}
#: The opener's second sentence for the page the call starts on, by a word in
#: its path; the first match wins, and anything else gets the plain greeting.
_OPENERS: tuple[tuple[str, dict[Lang, str]], ...] = (
    (
        "admision",
        {
            "en": "I can walk you through admission and find your child's level. When was your child born?",
            "es": "Te explico la admisión y vemos el nivel de tu hijo o hija. ¿Cuándo nació?",
        },
    ),
    (
        "contacto",
        {
            "en": "I can help you write to the school. What would you like to ask?",
            "es": "Te ayudo a escribirle al colegio. ¿Qué te gustaría preguntar?",
        },
    ),
    (
        "infraestructura",
        {
            "en": "I can show you the school's facilities. Shall I start with the photos?",
            "es": "Te muestro las instalaciones del colegio. ¿Partimos por las fotos?",
        },
    ),
    (
        "tour-virtual",
        {
            "en": "This is the 360 tour of the school. Would you like me to tell you what you're seeing?",
            "es": "Este es el tour virtual del colegio. ¿Te cuento lo que vas viendo?",
        },
    ),
    (
        "ingles",
        {
            "en": "I can tell you how English works at the school. How old is your child?",
            "es": "Te cuento cómo es el inglés en el colegio. ¿Qué edad tiene tu hijo o hija?",
        },
    ),
    (
        "ciclos",
        {
            "en": "I can show you the school's cycles and levels. How old is your child?",
            "es": "Te muestro los ciclos y niveles del colegio. ¿Qué edad tiene tu hijo o hija?",
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
    "link": {
        "en": "I've opened it in a new tab.",
        "es": "Te lo abrí en una pestaña nueva.",
    },
    "visit": {
        "en": "I've opened the visit booking in a new tab.",
        "es": "Te abrí la agenda de visitas en una pestaña nueva.",
    },
    "apply": {
        "en": "I've opened the online application in a new tab.",
        "es": "Te abrí la postulación online en una pestaña nueva.",
    },
    "form": {
        "en": "I'm putting it in the form.",
        "es": "Lo voy anotando en el formulario.",
    },
    "to_form": {
        "en": "I'm taking you to the contact form.",
        "es": "Te llevo al formulario de contacto.",
    },
    "slide": {"en": "Here's the next one.", "es": "Aquí va la siguiente."},
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
#: A visitor's ordinary words about the school, so the reading trusts them.
_ACK_WORDS = Vocabulary(
    common=frozenset(
        # A word list reads as words, so it stays a split string.
        """colegio everest admisión admision postular postulación postulacion vacantes vacante
        cupos matrícula matricula colegiatura valores arancel aranceles uf kínder kinder
        prekínder prekinder playgroup bambolino mini básico basico medio ciclo curso cursos
        nivel niveles hijo hija hijos edad años nació nacio inglés ingles cambridge católico
        catolico religión religion misa formación formacion deporte canchas gimnasio
        infraestructura instalaciones tour visita agendar entrevista evaluación evaluacion
        resultados uniforme útiles utiles casino bus enfermería enfermeria contacto correo
        formulario mensaje teléfono telefono directora encargada school apply admission
        vacancies fees tuition level grade english visit tour form
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


_ANCHORS_IN_NOTE = 40
_SEARCH_HITS = 6


async def _silence() -> AsyncGenerator[Any, None]:
    for _ in ():
        yield


def _clip(items: list[str] | tuple[str, ...], most: int) -> str:
    more = f"; and {len(items) - most} more" if len(items) > most else ""
    return "; ".join(items[:most]) + more


def _match(want: str, options: list[str] | tuple[str, ...]) -> str | None:
    """The option ``want`` names: the same words, else the one it begins, else
    the one it is inside — how the page itself matches. Case, accents,
    underscores and punctuation do not count: "paso 4 visita" is "paso_4_visita"."""

    def folded(s: str) -> str:
        return " ".join(re.sub(r"[^\w\s]|_", " ", norm(s)).split())

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


# ─── What they asked about ─────────────────────────────────────────────────────

#: Where to show what the visitor asked about, when his reply forgets to show
#: it: on SendPotion he described a page twice with the screen left where it
#: was, until the visitor said they could not see it. Matched on their own
#: words, English or Spanish, folded; a specific place beats a general one, and
#: among specific ones the first named wins. Each target is (path, place); a
#: path of "" is the page in front (the header and footer are on every page).
Target = tuple[str, str | None]

_ASKED: tuple[tuple[re.Pattern[str], Target], ...] = tuple(
    (re.compile(rf"\b(?:{w})", re.IGNORECASE), target)
    for w, target in (
        (r"vacantes?|cupos?|vacanc\w*|spots? (?:left|available)", (ADMISSION_PATH, "vacantes")),
        (
            r"cuanto cuesta|cuanto vale|valor(?:es)? del colegio|colegiatura|aranceles?|mensualidad|"
            r"bono de incorporacion|cuota de incorporacion|fees?\b|tuition|how much",
            (ADMISSION_PATH, "valores"),
        ),
        (
            r"fechas? de postulacion|plazos?|cuando (?:se )?postula|deadlines?|when (?:can|do) we apply",
            (ADMISSION_PATH, "fechas"),
        ),
        (
            r"admission day|come and play|evaluacion de ingreso|examen de admision",
            (ADMISSION_PATH, "paso_6_admission_day"),
        ),
        (r"entrevista|interview", (ADMISSION_PATH, "paso_5_entrevista")),
        (
            r"resultados de (?:la )?admision|admission results",
            (ADMISSION_PATH, "paso_7_resultados"),
        ),
        (
            r"que documentos|carta de presentacion|certificado de nacimiento|documents? (?:do we|to) ",
            (ADMISSION_PATH, "paso_2_prepara"),
        ),
        (r"encargada de admision|admissions officer", (ADMISSION_PATH, "encargada_admision")),
        (
            r"admision|postul\w*|proceso de ingreso|admission|apply|application|enrol\w*",
            (ADMISSION_PATH, "pasos"),
        ),
        (
            r"cambridge|certificaci\w*|first certificate|\bfce\b|\bcae\b",
            (ENGLISH_PATH, "certificaciones"),
        ),
        (r"ingles|english|bilingue|bilingual", (ENGLISH_PATH, "intro")),
        (
            r"preescolar|preschool|jardin|bambolino|playgroup|prekinder|kinder",
            (PRESCHOOL_PATH, None),
        ),
        (r"ciclos?\b|niveles|cycles?\b", (CYCLES_PATH, None)),
        (r"tour virtual|recorrido virtual|360|virtual tour", (TOUR_PATH, "tour")),
        (
            r"infraestructura|instalaciones|canchas?|gimnasio|biblioteca|laboratorio|capillas?|"
            r"facilities|campus|sports? fields?|gym\b",
            (INFRA_PATH, "galeria"),
        ),
        (r"historia|fundad\w*|history|founded", ("/nuestro-colegio/historia/", None)),
        (
            r"directora|equipo directivo|quien dirige|principal|leadership",
            ("/nuestro-colegio/equipo-directivo/", "equipo"),
        ),
        (
            r"catolic\w*|religion|pastoral|misas?\b|sacramentos|fe\b|catholic|faith|legionarios|regnum",
            ("/nuestro-colegio/nuestros-atributos/colegio-catolico/", None),
        ),
        (
            r"atributos|valores del colegio|attributes",
            ("/nuestro-colegio/nuestros-atributos/", None),
        ),
        (r"mision|mission", ("/nuestro-colegio/nuestra-mision/", None)),
        (r"proyecto educativo|\bpei\b", ("/nuestro-modelo-educativo/proyecto-educativo/", None)),
        (r"evertics|tecnologia|ipads?|technology", ("/nuestro-modelo-educativo/evertics/", None)),
        (
            r"ambientes seguros|abuso|proteccion|safeguarding|child protection",
            (SAFE_PATH, None),
        ),
        (r"reglamentos?|normativas?|protocolos?|rules\b|regulations", (NORMS_PATH, None)),
        (r"casino|almuerzo|lunch|cafeteria", ("/informacion-practica/casino/", None)),
        (r"uniformes?|uniform", ("/informacion-practica/uniforme-del-colegio/", None)),
        (
            r"utiles|lista de materiales|textos escolares|school supplies",
            ("/textos-y-utiles-escolares/", None),
        ),
        (r"enfermeria|nurse", ("/informacion-practica/enfermeria/", None)),
        (r"bus ?car|transporte|furgon\w*|school bus", ("/informacion-practica/bus-car/", None)),
        (r"centro de padres|parents'? association", ("/comunidad-everest/centro-de-padres/", None)),
        (r"ex ?alumnos|alumni", ("/comunidad-everest/ex-alumnos/", None)),
        (r"noticias|news", (HOME, "noticias")),
        (
            r"mapa|como llego|donde queda|ubicacion|direccion|map\b|address|where is the school",
            ("", "pie_mapa"),
        ),
        (r"telefono|phone number|call the school", ("", "pie_contacto")),
    )
)
#: What a tool moves rather than a cue: the contact form takes them to itself,
#: a document, the application or the visit opens in a new tab, a tab is switched.
_BY_TOOL = re.compile(
    r"\b(?:formulario|form\b|escrib\w*|mensaje|message|contacten|contactarme|call me|"
    r"contact me|mi nombre|me llamo|my name|mi telefono|mi numero|mi celular|mi correo|"
    r"my email|my phone|arroba|pdf|descarg\w*|download|abre el|open the|agend\w*|"
    r"book\w*|tabs?|pestanas?)\b",
    re.IGNORECASE,
)

# A request about the call's own language: a verb of speaking, addressed to him
# ("can you", "let's") or said by him ("I can", "volvemos"), and the language.
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
    this call, not a question about the school's English."""
    return bool(_CALL_LANGUAGE.search(text) and _TO_HIM.search(text))


def asked_target(text: str) -> Target | None:
    """Where on the site what ``text`` asks about is shown, or ``None``. The
    contact form, a document, the application, the visit and a tab are moved by
    their tools, and "can you speak English?" is about this call: none of them
    is a place."""
    said = fold(text)
    if _BY_TOOL.search(said) or asks_call_language(text):
        return None
    named = [
        (m.start(), m.start() - m.end(), i, target)
        for i, (rx, target) in enumerate(_ASKED)
        if (m := rx.search(said))
    ]
    if not named:
        return None
    # A place beats a whole page; then the first named.
    specific = [n for n in named if n[3][1] is not None]
    return min(specific or named)[3]


def asked_page(text: str) -> str | None:
    """The page :func:`asked_target` shows ("" is the page in front)."""
    target = asked_target(text)
    return target[0] if target else None


# ─── Their details ─────────────────────────────────────────────────────────────

_EMAIL = re.compile(r"^[\w.+-]+@[\w-]+(?:\.[\w-]+)+$")
#: A Chilean RUT or RUN, in any of its spellings: never typed by him.
_RUT = re.compile(r"\b\d{1,2}\.\d{3}\.\d{3}-?[\dkK]\b|\b\d{7,8}-[\dkK]\b")
#: A card number: never typed by him.
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")

#: The moves the page answers (``command_done`` or ``command_failed``), and how
#: long each may take, a full page load included: the school's server can take
#: well over half a minute for a page.
_MOVE_TAKES_S = {"fill_contact_form": 60.0, "slide": 45.0}
#: Words of his still playing hold the floor no longer than this.
_PLAYOUT_MAX_S = 30.0
#: The longest message and subject he writes into the form.
_MESSAGE_MAX = 600
_SUBJECT_MAX = 120

#: His own words telling them to press "Enviar", which the page's "complete"
#: then need not repeat, if said this recently.
_PRESS_HINT = re.compile(r"\b(?:enviar|send button|press send)\b")
_PRESS_HINT_S = 20.0

_SAY_READY = (
    "The contact form is complete. Say in a sentence or two that everything is in, that they "
    "check it, pass the site's security check if it asks, and press «Enviar» themselves. "
    "Never say it was sent."
)


# ─── The place a sentence describes ────────────────────────────────────────────
#
# What he says, sentence by sentence, matched against the places of the one
# page in front — never the whole site. A word of the place's label counts for
# more than a word of its text, a word every place shares for little, and a
# sentence that is not clearly about one place moves nothing.

_STOP = frozenset(
    # English and Spanish words that name no place.
    """a an the and or but of to in on for with by at from as is are was were be been it its
    this that these those you your yours we our us they their them he she his her i me my
    can will just also so then than too very here there what which who how when where why all
    any each every more most some such no not only own same into out up down over under again
    once about after before both few other per via do does did have has had get gets got make
    makes made use uses used like let lets want would shall could should see show shows one two
    three section page el la los las un una unos unas de del y o u en por para con sin que se
    su sus es son al lo le les como mas muy tu te ti mi nos este esta estos estas ese esa eso
    hay ser esta estan tiene tienen puedes puede quieres aqui alli tambien pero cuando donde
    colegio everest""".split()  # noqa: SIM905
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


def best_section(sentence: str, sections: list[tuple[str, str, str]]) -> str | None:
    """The key of the one place ``sentence`` is about, of ``sections`` (key,
    label, text) on one page; ``None`` unless it is clearly one."""
    if sentence.rstrip().endswith("?"):
        return None  # The closing offer: about what comes next, not this page.
    if len(sentence.split()) < _SECTION_MIN_WORDS:
        return None  # A few words: about no one place.
    docs = [
        (key, set(_terms(label)), set(_terms(text)))
        for key, label, text in sections
        if key and key not in _GENERIC
    ]
    if not docs:
        return None
    df: dict[str, int] = {}
    for _, head, text in docs:
        for w in head | text:
            df[w] = df.get(w, 0) + 1
    want = set(_terms(sentence))
    scored: list[tuple[float, str]] = []
    for key, head, text in docs:
        score = 0.0
        for w in want:
            idf = math.log(1 + len(docs) / (1 + df.get(w, 0)))
            score += 2 * idf if w in head else 0.6 * idf if w in text else 0.0
        scored.append((score, key))
    scored.sort(key=lambda s: -s[0])
    top, key = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    return key if top >= _SECTION_MIN and top - second >= _SECTION_LEAD else None


#: Places a sentence names outright, in either language: a level's admission
#: card by the level, a step by its name, the admissions officer by hers. The
#: words of a card are Spanish and few, so an English sentence about Playgroup
#: scores too low to ring its card; a name is enough. Each is (pattern over the
#: folded sentence, page, place).
_NAMED: tuple[tuple[re.Pattern[str], str, str], ...] = tuple(
    (re.compile(rf"\b(?:{w})\b"), page, key)
    for w, page, key in (
        (r"mini bambolino", ADMISSION_PATH, "fecha_bambolino"),
        (r"(?<!mini )bambolino", ADMISSION_PATH, "fecha_bambolino"),
        (r"playgroup", ADMISSION_PATH, "fecha_playgroup"),
        (r"pre ?kinder", ADMISSION_PATH, "fecha_prekinder"),
        (
            r"(?<!pre)kinder a (?:iv|cuarto) medio|kinder to (?:iv|twelfth|fourth)",
            ADMISSION_PATH,
            "fecha_kinder_iv_medio",
        ),
        (r"admission day|come and play", ADMISSION_PATH, "paso_6_admission_day"),
        (
            r"maria ignacia|encargada de admision|admissions officer",
            ADMISSION_PATH,
            "encargada_admision",
        ),
        (r"cambridge", ENGLISH_PATH, "certificaciones"),
        (r"ceprome", SAFE_PATH, "ceprome"),
    )
)


def named_place(sentence: str) -> tuple[str, str] | None:
    """The (page, place) a sentence names outright, the first named; ``None``
    for none, or for a question (the closing offer is about what comes next)."""
    if sentence.rstrip().endswith("?"):
        return None
    said = " ".join(re.findall(r"[a-z0-9]+", fold(sentence)))
    hits = [(m.start(), page, key) for rx, page, key in _NAMED if (m := rx.search(said))]
    return (min(hits)[1], min(hits)[2]) if hits else None


def _on_page(text: str, page: Page) -> bool:
    """Whether ``text`` is on ``page`` as the crawl read it."""
    want = norm(text)
    if not want:
        return False
    parts = [page.title, page.text, *(f"{s.heading} {s.text}" for s in page.sections)]
    return any(want in norm(p) for p in parts)


# ─── The child's level ─────────────────────────────────────────────────────────

#: The grades of the 2026 school year, in order, as a parent says them; the
#: level for 2027 is the next one. Each is (words it is said with, level key).
_GRADE_WORDS: tuple[tuple[str, str], ...] = (
    (r"mini bambolino", "mini_bambolino"),
    (r"bambolino", "bambolino"),
    (r"playgroup|play group", "playgroup"),
    (r"pre ?kinder|pre ?kindergarten", "prekinder"),
    (r"kinder|kindergarten", "kinder"),
    (r"(?:1|primero|primer|first)(?: ?°|º)? ?(?:basico|grade)", "1_basico"),
    (r"(?:2|segundo|second)(?: ?°|º)? ?(?:basico|grade)", "2_basico"),
    (r"(?:3|tercero|tercer|third)(?: ?°|º)? ?(?:basico|grade)", "3_basico"),
    (r"(?:4|cuarto|fourth)(?: ?°|º)? ?(?:basico|grade)", "4_basico"),
    (r"(?:5|quinto|fifth)(?: ?°|º)? ?(?:basico|grade)", "5_basico"),
    (r"(?:6|sexto|sixth)(?: ?°|º)? ?(?:basico|grade)", "6_basico"),
    (r"(?:7|septimo|seventh)(?: ?°|º)? ?(?:basico|grade)", "7_basico"),
    (r"(?:8|octavo|eighth)(?: ?°|º)? ?(?:basico|grade)", "8_basico"),
    (r"(?:iv|4|cuarto)(?: ?°|º)? ?medio|twelfth grade", "iv_medio"),
    (r"(?:iii|3|tercero|tercer)(?: ?°|º)? ?medio|eleventh grade", "iii_medio"),
    (r"(?:ii|2|segundo)(?: ?°|º)? ?medio|tenth grade", "ii_medio"),
    (r"(?:i|1|primero|primer)(?: ?°|º)? ?medio|ninth grade", "i_medio"),
)


def grade_key(said: str) -> str | None:
    """The level key a grade as said names: "tercero básico" → "3_basico"."""
    text = fold(said)
    for words_, key in _GRADE_WORDS:
        if re.search(rf"\b(?:{words_})\b", text):
            return key
    return None


def _months_between(born: date, on: date) -> int:
    months = (on.year - born.year) * 12 + on.month - born.month
    return months - (1 if on.day < born.day else 0)


@dataclasses.dataclass(frozen=True)
class Placement:
    """Where a child goes in 2027, and how sure that is."""

    level: Level
    estimated: bool
    """From Kínder up the site gives no age: the level is the usual sequence's."""
    how: str
    """What it was worked out from, in words."""


def place_child(
    k: Knowledge,
    *,
    birth_date: date | None = None,
    age_months_today: int | None = None,
    today: date,
    current_grade: str | None = None,
    level: str | None = None,
) -> Placement | str:
    """The 2027 level for a child, by the admission page's rule; a string says
    why there is none."""
    levels = list(k.levels)
    if not levels:
        return "The levels are not loaded: show the admission page's dates and offer admissions."
    if level:
        key = grade_key(level) or norm(level).replace(" ", "_")
        found = k.level(key) or next(
            (lv for lv in levels if _match(level, [lv.name]) is not None), None
        )
        if found is None:
            names = ", ".join(lv.name for lv in levels)
            return f"No level '{level}' for 2027. The levels are: {names}."
        return Placement(found, False, "the level asked about")
    if current_grade:
        key = grade_key(current_grade)
        keys = [lv.key for lv in levels]
        if key is None or key not in keys:
            return (
                f"'{current_grade}' is not a grade I can place. Ask for the child's birth date "
                "instead."
            )
        i = keys.index(key)
        if i + 1 >= len(levels):
            return (
                "The child is in IV medio now: they finish school this year, so there is no level "
                "for 2027 at Colegio Everest."
            )
        nxt = levels[i + 1]
        return Placement(nxt, False, f"the grade after {levels[i].name}, the one they are in now")
    cutoff = k.cutoff or date(2027, 3, 31)
    if birth_date is not None:
        months = _months_between(birth_date, cutoff)
        how = f"born {birth_date.isoformat()}: {months // 12} years and {months % 12} months at the cut-off"
    elif age_months_today is not None:
        months = age_months_today + _months_between(today, cutoff)
        how = (
            f"aged {age_months_today // 12} years and {age_months_today % 12} months today, "
            "so about that plus five months at the cut-off (from the age, not a birth date: ask "
            "for the birth date if it is close to a boundary)"
        )
    else:
        return "Say the child's birth date, age, or the grade they are in now."
    ruled = [lv for lv in levels if lv.min_age_months is not None]
    if ruled and months < min(lv.min_age_months or 0 for lv in ruled):
        youngest = min(ruled, key=lambda lv: lv.min_age_months or 0)
        return (
            f"Too young for 2027: {how}. The youngest level, {youngest.name}, asks for "
            f"{youngest.age_text}. Say so kindly, and that admissions can say when to apply."
        )
    fit = [lv for lv in ruled if (lv.min_age_months or 0) <= months]
    oldest_ruled = max(ruled, key=lambda lv: lv.min_age_months or 0) if ruled else None
    if fit and (oldest_ruled is None or months < (oldest_ruled.min_age_months or 0) + 12):
        best = max(fit, key=lambda lv: lv.min_age_months or 0)
        return Placement(best, False, how)
    years = months // 12
    seq = [lv for lv in levels if lv.age_if_sequence is not None]
    found = next((lv for lv in seq if lv.age_if_sequence == years), None)
    if found is None:
        if seq and years > max(lv.age_if_sequence or 0 for lv in seq):
            return f"{how}: older than IV medio's usual age. Ask which grade they are in now."
        return f"{how}: no level fits. Ask which grade they are in now."
    return Placement(found, True, how)


def _window_status(lv: Level, today: date) -> str:
    if lv.closes is not None and today > lv.closes:
        return f"CLOSED on {lv.closes.isoformat()} (today is {today.isoformat()})"
    if lv.opens is not None and today < lv.opens:
        return f"not open yet: it opens on {lv.opens.isoformat()}"
    if lv.opens is not None and lv.closes is not None:
        return f"OPEN now, until {lv.closes.isoformat()}"
    return "dates as written"


def _uf(value: str, lang: Lang) -> str:
    said = uf_es(value) if lang == "es" else uf_en(value)
    return f"{value} UF (say: {said})"


def describe_placement(k: Knowledge, p: Placement, today: date, lang: Lang) -> str:
    """What find_level hands the model: every figure with its words."""
    lv = p.level
    count = (
        (number_es(lv.vacancies) if lang == "es" else number_en(lv.vacancies))
        if lv.vacancies is not None
        else ""
    )
    lines = [f"Level for 2027: {lv.name} (cycle {lv.cycle}), from {p.how}."]
    if p.estimated:
        lines.append(
            "ESTIMATE: the site gives no age rule from Kínder up. Say it is the usual level for "
            "that age, and that admissions confirms it; never say it is the site's rule."
        )
    elif lv.age_text:
        lines.append(f"The admission page's age rule: «{lv.age_text}».")
    else:
        lines.append("The site gives no age rule for this level; admissions confirms it.")
    lines.append(
        f"Application window (admission page): «{lv.window_text}» — {_window_status(lv, today)}."
    )
    if lv.admission_day:
        lines.append(f"Admission Day: {lv.admission_day}. Results: {lv.results.rstrip('.')}.")
    if lv.vacancies is not None:
        lines.append(
            f"Vacancies 2027 (PDF of March 2026, which says the numbers change with movements per "
            f"level): {lv.vacancies} (say: {count})"
            + (
                f", plus {lv.priority_neep} priority place for a child with special educational needs or a disability"
                if lv.priority_neep
                else ""
            )
            + "."
            + (
                " None: say so, and offer admissions for the waiting list."
                if lv.vacancies == 0
                else ""
            )
        )
    fees27 = k.fees.get("2027")
    band = fees27.bands.get(lv.fee_band_2027) if fees27 is not None else None
    if fees27 is not None and band is not None:
        lines.append(
            f"Published fees 2027 ({band.label}; PDF «Valores 2027», on the school's server but not "
            f"linked on the site): enrolment (matrícula) {_uf(band.matricula, lang)}; annual tuition "
            f"(colegiatura) {_uf(band.anual, lang)}, in {fees27.cuotas} instalments of "
            f"{_uf(band.cuota, lang)}."
        )
    fees26 = k.fees.get("2026")
    band26 = fees26.bands.get(lv.fee_band_2026) if fees26 is not None else None
    if fees26 is not None and band26 is not None:
        lines.append(
            f"For comparison, 2026 ({band26.label}, PDF «Valores 2026», linked): annual tuition "
            f"{_uf(band26.anual, lang)}. Only if asked."
        )
    lines.append(
        "The admission process fee is $45.000 per child (say: cuarenta y cinco mil pesos)."
    )
    on_adm = None
    if lv.place:
        on_adm = f"{{page: {ADMISSION_PATH}}}{{show: {lv.place}}}"
        lines.append(
            f"Show its card as you name the level: {{show: {lv.place}}} (with {on_adm} if they are "
            "not on the admission page), and {show: vacantes} or {show: valores} as you give those."
        )
    if lv.closes is not None and today > lv.closes:
        lines.append(
            "The window has closed: say so honestly, give the vacancies, and offer to contact "
            "admissions (book_visit, or a message with fill_contact_form)."
        )
    return " ".join(lines)


def _parse_date(text: str) -> date | None:
    try:
        return date.fromisoformat(text.strip()[:10])
    except ValueError:
        return None


# ─── The brain ─────────────────────────────────────────────────────────────────


class ColegioEverestBrain(OpenAIBrain):
    """One per session. Javier: Colegio Everest's knowledge, its pages and
    places, the levels and admission 2027, the contact form the visitor fills
    with him, and a mirror of their tabs, in Spanish or English."""

    def __init__(
        self,
        *,
        client: AsyncOpenAI,
        model: str = MODEL,
        knowledge: Knowledge | None = None,
        today: date | None = None,
    ) -> None:
        self.kb = knowledge if knowledge is not None else kb.KNOWLEDGE
        self._today = today
        super().__init__(
            client=client,
            system_instruction=_prompt(self.kb, today),
            model=model,
            reasoning=REASONING,
        )
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
        self._path = HOME
        self._page_unseen = False
        #: Every open Colegio Everest tab, and which is in front.
        self.tabs: list[TabInfo] = []
        self._active = ""
        self._tabs_unseen = False
        #: The contact form as the page last reported it.
        self.form: FormState | None = None
        #: The page this turn's cues are on: the one in front, then wherever a
        #: ``{page: …}`` cue took it.
        self._cue_path = HOME
        self._idle_short = False
        self._nudges = 0
        #: Where to show what they last asked about, at the start of his reply
        #: if it has no cue of its own; see :func:`asked_target`.
        self._backstop: Target | None = None
        #: Whether their last words asked for something a tool moves.
        self._by_tool = False
        #: This reply's moves so far: whether one opened a page, and what was
        #: last rung, so a sentence on the same place does not ring it again.
        self._paged = False
        self._shown: str | None = None
        #: A talk-through owed that is not a move's answer (the site's answer
        #: to their press).
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
        #: When he last told them to press "Enviar" himself.
        self._press_hint_at = float("-inf")
        self._playing = 0
        self._played_at = 0.0
        self._idle_deferred = False

    @property
    def today(self) -> date:
        return self._today or _today()

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
                stt=SttConfig(language=self.spoken, patience=EVEREST_PATIENCE),
                tts=TtsConfig(voice=VOICE, language=self.spoken),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
            )
        )
        logger.info(
            "colegioeverest: session start on {} in {}{}",
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
        "bidéo" or "u efe" in its own words."""
        if "idéo" in fin.heard or "u efe" in fin.heard:
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
        thinking, and his own line any dead air after it (:func:`hold_the_floor`)."""
        heard = None if self._chosen else language_of(msg.text)
        if heard is not None and heard != self.spoken:
            await session.configure(self._speaking(heard))
            logger.info("colegioeverest: language -> {} (heard)", heard)
        # They spoke first: the page's answers are in the context as notes, and
        # he answers them with what they said.
        self._talk = None
        self._outcomes.clear()
        self._idle_deferred = False
        # What he said before has played out, or they spoke over it.
        self._playing = 0
        self._nudges = 0
        # A reply cut off before it said a word keeps its place for the next one.
        # A request to switch language shows nothing.
        self._backstop = (
            None if asks_call_language(msg.text) else asked_target(msg.text) or self._backstop
        )
        # Asked for what a tool moves (the form, a document, a tab): the tool
        # takes them there, so his words open no page.
        self._by_tool = bool(_BY_TOOL.search(fold(msg.text)))
        self._restore_idle()
        self._read_in_screen()
        now = time.monotonic()
        fragment, self._heard_at = now - self._heard_at < _FRAGMENT_S, now
        nod = None if fragment else self._ack.line(msg.text, self.spoken)
        floor: Floor[Lang] = self._ack
        if nod is not None:
            logger.info("colegioeverest: ack {!r}", nod)
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

        What the page answered after his turn (the form complete, a field the
        site refused, their press confirmed) is in the context already, and the
        idle window was shortened for it, so they hear it from him here.
        Otherwise an ordinary quiet spell: a nudge, twice, then silence.

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
                "about what is on their screen, or one question that helps you help them. Never "
                "ask whether they are still there, and never repeat your last line."
            )
        else:
            ask = (
                "Still quiet. One last, light offer, different from your last: something you "
                "could show them next, or a visit. Then let them browse."
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
        at once (:func:`landed`), in the language he speaks. A turn that came
        back with nothing at all — no words, no move — is asked once more,
        with tools off.

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
                if _PRESS_HINT.search(fold(said)):
                    self._press_hint_at = time.monotonic()
            yield event
        # Words, and not only a promise: on Explora's dev call ed9846d5 the whole
        # reply was "One moment.", and the visitor sat in silence.
        if not _PROMISE.sub("", _CUE_TEXT.sub(" ", said)).strip(" .,!?¡¿…"):
            logger.warning("colegioeverest: the model returned nothing; asking once more")
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
                logger.info("colegioeverest: language -> {} (written)", written)
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
        """``turn``, with speech spelled as the voice must read it."""

        async def spelled() -> AsyncGenerator[Speech, None]:
            async for event in turn:
                if isinstance(event, SpeechChunk):
                    text = (
                        for_the_voice(event.text)
                        if self.spoken == "es"
                        else for_the_voice_en(event.text)
                    )
                    if text != event.text:
                        event = SpeechChunk(text)
                yield event

        return spelled()

    async def _cued(self, turn: AsyncGenerator[Speech, None]) -> AsyncGenerator[Speech, None]:
        """``turn`` with every ``{page|show: …}`` taken out of its text and
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
        """The reply's first words, with what they asked about cued in front of
        them when the reply brings no cue of its own."""
        if self._backstop is None or not chunk.strip():
            return chunk
        (path, place), self._backstop = self._backstop, None
        path = path or self._path
        if "{" in chunk or self._page_for(path) is None:
            return chunk
        if place is not None:
            cue = (
                f"{{show: {place}}}" if path == self._path else f"{{page: {path}}}{{show: {place}}}"
            )
        elif path != self._path:
            cue = f"{{page: {path}}}"
        else:
            return chunk
        logger.info("colegioeverest: the reply has no cue; showing {} first", cue)
        return f"{cue}{chunk}"

    def _send_cue(self, raw: RawCue) -> None:
        """Check a cue against the site, as the tools do, and send it; one that
        names nothing real is dropped and logged rather than reaching the page."""
        if self.spoken == "es" and raw.at:
            raw = dataclasses.replace(raw, at=_anchor_for_voice(raw.at))
        elif raw.at:
            raw = dataclasses.replace(raw, at=" ".join(words(for_the_voice_en(raw.at))))
        cue = self._resolve_cue(raw)
        logger.info("colegioeverest: cue {} {!r} at {!r} -> {}", raw.kind, raw.value, raw.at, cue)
        if cue is not None:
            self._paged = self._paged or cue.path is not None
            if raw.kind == "show":
                self._shown = cue.anchor or cue.text
            self.session.dispatch(cue)

    def _auto_cues(
        self, sentence: str, index: int, placed: tuple[tuple[CueKind, str], ...]
    ) -> list[tuple[CueKind, str]]:
        """The moves a sentence of his needs and did not bring (see
        :mod:`.cues`): the page its first sentence is about, when nothing has
        opened one, and the place on the page it describes."""
        out: list[tuple[CueKind, str]] = []
        kinds = {k for k, _ in placed}
        # A page the model opens on this very sentence is not sent yet.
        pages = [p.path for k, v in placed if k == "page" and (p := self._page_for(v)) is not None]
        path = pages[-1] if pages else self._cue_path
        if index == 0 and not self._paged and not self._by_tool and not kinds:
            target = asked_target(sentence)
            if (
                target is not None
                and target[0]
                and target[0] != self._path
                and self._page_for(target[0])
            ):
                logger.info("colegioeverest: he talks about {} with no cue; opening it", target[0])
                out.append(("page", target[0]))
                path = target[0]
        self._cue_path = path
        # They are dictating their details: the form is on their screen, and stays.
        if kinds & {"show", "faq"} or self._by_tool:
            return out
        # A level, a step or a person named outright: its card, on this page,
        # or, on the reply's first sentence, on the page that has it.
        if (named := named_place(sentence)) is not None and named[1] != self._shown:
            on_page = any(a.key == named[1] for a in self.kb.anchors_on(path))
            if on_page or (index == 0 and not self._paged and not self._by_tool):
                return [*out, ("show", named[1])]
        page = self.kb.page(path)
        if page is None:
            return out
        shown = best_section(sentence, [(s.key, s.heading, s.text) for s in page.sections])
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

    def _places_on(self, path: str, *, live: bool) -> list[Anchor]:
        """The places a cue may name on ``path``: the catalogue's, and, on the
        page in front, any other place it reported. A place the page has not
        laid out yet is still sent: the page says plainly if it cannot ring it."""
        known = [a for a in self.kb.anchors_on(path) if not a.hidden]
        if live and self.page is not None:
            have = {a.key for a in known}
            known += [Anchor(k, k) for k in self.page.anchors if k not in have]
        return known

    def _place(self, value: str, path: str, *, live: bool) -> str | None:
        """The key ``value`` names among the places on ``path``."""
        places = self._places_on(path, live=live)
        keys = [a.key for a in places]
        if (hit := _match(value, keys)) is not None:
            return hit
        labels = [a.label for a in places]
        if (hit := _match(value, labels)) is not None:
            return keys[labels.index(hit)]
        return None

    def _only_page_of(self, key: str) -> str | None:
        """The one page whose catalogue has ``key``, if exactly one does; a key
        several pages share (``valores``: the fees on the admission page, the
        casino's prices, the III cycle's values) is the admission page's, the
        page a family asks about, unless it names no place of its own there."""
        have = [p for p, anchors in self.kb.anchors.items() if any(a.key == key for a in anchors)]
        if len(have) == 1:
            return have[0]
        if ADMISSION_PATH in have and key not in {*_GENERIC, "intro"}:
            return ADMISSION_PATH
        return None

    def _resolve_cue(self, raw: RawCue) -> Cue | None:
        if raw.kind == "page":
            page = self._page_for(raw.value)
            if page is None:
                return None
            self._cue_path = page.path
            return Cue(at=raw.at, word=raw.word, path=page.path)
        if raw.kind == "faq":
            # This site has no FAQ: a stray {faq: …} is taken as a place.
            raw = dataclasses.replace(raw, kind="show")
        moved = self._cue_path != self._path
        # show: a place on the page they will be on, else the same place on the
        # one other page that has it, else words the page has.
        if (key := self._place(raw.value, self._cue_path, live=not moved)) is not None:
            return Cue(at=raw.at, word=raw.word, path=self._cue_path if moved else None, anchor=key)
        want = norm(raw.value).replace(" ", "_")
        if (other := self._only_page_of(want)) is not None and other != self._cue_path:
            self._cue_path = other
            return Cue(at=raw.at, word=raw.word, path=other, anchor=want)
        target = self._page_for(self._cue_path)
        live = self.page is not None and not moved and canonical_path(self.page.path) == self._path
        if target is not None and target.sections and not live and not _on_page(raw.value, target):
            logger.info("colegioeverest: {!r} is not on {}; dropped", raw.value, target.path)
            return None
        if re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)+", raw.value.strip()):
            # A key that is nowhere: never sent as words to look for.
            logger.info("colegioeverest: no place {!r}; dropped", raw.value)
            return None
        return Cue(
            at=raw.at, word=raw.word, path=self._cue_path if moved else None, text=raw.value[:120]
        )

    def _talk_now(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The one extra request a turn with nothing in it gets: tools off."""
        return self.respond_with(session, tools=ToolChoice.NONE)

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Page→brain events, folded in silently: no floor taken, no turn."""
        event = EVEREST_EVENTS.parse(msg)
        if event is None:
            return
        logger.info("colegioeverest: {} — {}", type(event).__voqal_event__, event)
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
            logger.warning("colegioeverest: switch to {} refused: {}", event.language, rejected)
            self.spoken = was
            session.dispatch(LanguageChanged(language=was))
            return
        logger.info("colegioeverest: language -> {} (toggle)", event.language)
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
            stt=SttConfig(language=language, patience=EVEREST_PATIENCE),
            tts=TtsConfig(voice=VOICE, language=language),
        )

    # ─── Page → brain ───────────────────────────────────────────────────

    def apply_event(self, event: EverestEvent) -> str | None:
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
            case FormState():
                return self._form_state(event)
            case FormResult():
                return self._form_result(event)
            case CommandDone():
                detail = event.detail or "done"
                self._answered(event.command, f"{event.command} done: {detail}", talk=False)
                return f"[The page confirms {event.command}: {detail}.]"
            case CommandFailed() if event.command == "cue":
                # He has already spoken past it: the next turn should not claim
                # it is on screen, nor stop to apologise for a scroll.
                return (
                    f"[A screen cue of yours did not land ({event.reason}). If the visitor "
                    "asks where it is, show it again; otherwise carry on.]"
                )
            case CommandFailed():
                self._answered(event.command, f"{event.command} not done: {event.reason}")
                return (
                    f"[Not done on the page ({event.command}): {event.reason}. Tell the visitor "
                    "plainly and offer what you can do instead; never say it worked.]"
                )

    def _form_state(self, event: FormState) -> str:
        was = self.form
        self.form = event
        values = "; ".join(f"{k}: {v}" for k, v in event.values.items() if v)
        who = "they typed in it themselves" if event.by == "visitor" else "after your fill"
        note = (
            f"[The contact form, {who}: filled {', '.join(event.filled) or 'nothing'}; still "
            f"empty {', '.join(event.missing) or 'nothing'}"
        )
        if event.invalid:
            note += f"; the site would refuse {', '.join(event.invalid)}"
        if values:
            note += f". It holds: {values}"
        note += "."
        if event.ready:
            note += " It is complete: they review it and press «Enviar» themselves.]"
            # Said already, in the reply that made the last fill: not twice.
            told = time.monotonic() - self._press_hint_at < _PRESS_HINT_S
            if (was is None or not was.ready) and not told:
                self._talk_through(_SAY_READY)
        else:
            note += "]"
        return note

    def _form_result(self, event: FormResult) -> str:
        said = f" ({event.message})" if event.message else ""
        if event.outcome == "sent":
            self._talk_through(
                "They pressed «Enviar» and the site confirmed the message was sent. Thank them "
                "warmly in one sentence, say the school answers by email, and offer one last "
                "thing: booking a visit, or a question before they go."
            )
            return f"[The site confirmed the contact form was sent{said}.]"
        if event.outcome == "spam":
            self._talk_through(
                "The site did not take the message: its security check (the Cloudflare box above "
                "«Enviar») did not pass. Say so plainly in a sentence: they complete the check "
                "and press «Enviar» again. Never say it was sent."
            )
            return f"[The site refused the contact form as spam{said}: its security check did not pass.]"
        if event.outcome == "failed":
            self._talk_through(
                "The site could not send the message (its own error). Say so plainly, and give "
                f"the admissions email, {ADMISSIONS_EMAIL}, and phone instead. Never say it was "
                "sent."
            )
            return f"[The site failed to send the contact form{said}.]"
        fields = ", ".join(event.fields)
        self._talk_through(
            "The site refused the form when they pressed «Enviar»"
            + (f": {event.message}" if event.message else "")
            + (f" (fields: {fields})" if fields else "")
            + ". Say plainly what is wrong in a sentence, ask for the corrected detail, and fill "
            "it in again once they say it. Never say it was sent."
        )
        return (
            f"[The site refused the contact form: {event.message or 'an error'}"
            + (f"; fields: {fields}" if fields else "")
            + ".]"
        )

    def _read_in_screen(self) -> None:
        """The tabs and the page in front, once per change, ahead of what they say."""
        if self._tabs_unseen and len(self.tabs) > 1:
            listed = "; ".join(
                f"{t.tab_id}: {t.title or t.url}"
                + (" (in front)" if t.tab_id == self._active else "")
                for t in self.tabs
            )
            self._note(f"[The visitor's open Colegio Everest tabs — {listed}.]")
        self._tabs_unseen = False
        if not self._page_unseen or self.page is None:
            return
        self._page_unseen = False
        p = self.page
        where = {
            "home": "the home page",
            "admission": "the admission page",
            "contact": "the contact page",
            "post": "a news post",
            "news": "the news page",
            "tour": "the virtual tour",
        }.get(p.kind, "a page")
        note = f"[The tab in front shows {where}: “{p.title or p.path}” ({p.path})."
        own = [a for a in p.anchors if not a.startswith(_CHROME)]
        if own:
            note += f" Its places: {_clip(own, _ANCHORS_IN_NOTE)}."
        if p.form == "contact":
            note += " It has the contact form."
        self._note(note + "]")

    def _note(self, text: str) -> None:
        self.append_note(text)

    # ─── Talk-throughs and one move at a time ───────────────────────────

    def _talk_through(self, ask: str) -> None:
        self._talk = ask if self._talk is None else f"{self._talk} {ask}"
        self._shorten_idle()

    def _holding_floor(self) -> bool:
        """Whether a turn of his is under way, or his words are still playing."""
        playing = self._playing > 0 and time.monotonic() - self._played_at < _PLAYOUT_MAX_S
        return self._turns > 0 or playing

    def _shorten_idle(self) -> None:
        """The short quiet spell, for something to talk through: set now, or,
        while he holds the floor, once he has finished."""
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

    def _answered(self, command: str, outcome: str, *, talk: bool = True) -> None:
        """The page answered a move he sent. A move queued behind it goes to
        the page now, or, if this one failed, is dropped and said. A failure is
        talked through in the next short quiet spell, unless they speak first;
        a fill that went in is not (he said it as he filled), unless what was
        queued behind it could not be sent."""
        if command not in self._sent:
            return
        del self._sent[command]
        if (queued := self._queued) is not None and not self._busy():
            self._queued = None
            name = queued.__voqal_action__
            if " done" in outcome:
                logger.info("colegioeverest: {} answered; sending the {} queued", command, name)
                self._send(queued)
            else:
                outcome += f" (so {name}, asked for while it ran, was not sent)"
                talk = True
        if talk:
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
        A fill queued behind a fill keeps both fills' fields."""
        if (running := self._busy()) is None:
            self._queued = None
            self._send(action)
            landed(_LANDED[line][self.spoken])
            return None
        queued = self._queued
        if queued is not None and type(queued) is type(action):
            merged = {k: v for k, v in queued.model_dump().items() if v is not None}
            merged |= {k: v for k, v in action.model_dump().items() if v is not None}
            action = type(action)(**merged)
        self._queued = action
        landed(_LANDED["queued"][self.spoken])
        logger.info("colegioeverest: {} queued behind {}", action.__voqal_action__, running)
        return (
            f"Queued, not sent yet: the page is still working on {running}. It goes to the page "
            "as soon as the page answers that. Say in a few words that you are noting it; never "
            "that it is done, and do not call it again."
        )

    def _take_ask(self) -> str | None:
        """What he has to talk through now — the page's answers to his moves,
        the site's answer to their press — and nothing left after."""
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

    # ─── Documents ──────────────────────────────────────────────────────

    def document(self, name: str) -> Document | None:
        """The school's PDF ``name`` describes: the one whose description,
        labels and file name share most of its words, served (not a 404), the
        newest first on a tie."""
        want = {w for w in re.findall(r"[a-z0-9]+", fold(name)) if len(w) > 1}
        want -= {"de", "del", "la", "el", "los", "las", "pdf", "documento", "the", "of"}
        if not want:
            return None
        best: tuple[float, str, Document] | None = None
        for d in self.kb.documents:
            if d.broken:
                continue
            hay = set(re.findall(r"[a-z0-9]+", fold(f"{d.note} {' '.join(d.labels)} {d.file}")))
            score = len(want & hay) / len(want) + (0.2 if d.note else 0.0)
            if score < 0.6:
                continue
            if best is None or (score, d.url) > (best[0], best[1]):
                best = (score, d.url, d)
        return best[2] if best else None

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        """Read and search the school's knowledge; place a child in a level;
        fill the contact form as they dictate; open the application, the visit
        booking, a document or a portal; move a slider; move between their
        tabs; switch language."""
        return [
            self.read_topic,
            self.search_site,
            self.find_level,
            self.fill_contact_form,
            self.book_visit,
            self.open_application,
            self.open_link,
            self.slide,
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
        """Search www.colegioeverest.cl's pages, places and news posts. Each
        result names the page path and the place's key to show."""
        hits = self.kb.search(request.query, _SEARCH_HITS)
        if not hits:
            return (
                f"Nothing on the site matches '{request.query}'. Try other words in Spanish, or "
                "say the site does not say, and offer the admissions office."
            )
        out: list[str] = []
        for h in hits:
            where = f", place: {h.section}" if h.section else ""
            label = "[news post]" if h.kind == "post" else "[page]"
            out.append(f"{label} {h.title} — path: {h.path}{where}\n  {h.snippet}")
        return "\n".join(out)

    @needs_result_now
    async def find_level(self, request: LevelRequest) -> str:
        """The level a child enters in 2027, by the admission page's rule
        (cut-off 31 March 2027), from their birth date, age or current grade,
        or a level asked about: its window and whether it has closed, its
        Admission Day, the 2027 vacancies, the published fees, and the card to
        show."""
        born = _parse_date(request.birth_date) if request.birth_date else None
        if request.birth_date and born is None:
            return (
                f"'{request.birth_date}' is not a date: pass it as YYYY-MM-DD, or ask for it again."
            )
        months = (
            request.age_years * 12 + (request.age_months or 0)
            if request.age_years is not None
            else None
        )
        placed = place_child(
            self.kb,
            birth_date=born,
            age_months_today=months,
            today=self.today,
            current_grade=request.current_grade,
            level=request.level,
        )
        if isinstance(placed, str):
            return placed
        return describe_placement(self.kb, placed, self.today, self.spoken)

    async def fill_contact_form(self, request: ContactRequest) -> str:
        """Fill the contact form on /contacto/ with what the visitor said: only
        the new fields each time. On another page, /contacto/ opens and it is
        filled there. Never sent: they press «Enviar» themselves."""
        given = {
            k: " ".join(v.split()) if k != "mensaje" else v.strip()
            for k, v in request.model_dump().items()
            if isinstance(v, str) and v.strip()
        }
        if any(_RUT.search(v) or _CARD.search(v) for v in given.values()):
            return (
                "Not filled: that looks like a RUT or a card number, which the school never asks "
                "for here. Leave it out and tell them it is not needed."
            )
        refused: list[str] = []
        if (email := given.get("email")) is not None:
            email = "".join(email.split()).lower()
            if not _EMAIL.match(email):
                refused.append(f"email {email!r} is not an address: ask them to spell it again")
                given.pop("email")
            else:
                given["email"] = email
        if (msg := given.get("mensaje")) is not None:
            given["mensaje"] = msg[:_MESSAGE_MAX]
        if (subject := given.get("asunto")) is not None:
            given["asunto"] = subject[:_SUBJECT_MAX]
        if not given:
            return "Not filled: " + ("; ".join(refused) or "nothing to fill yet.")
        here = self._path == CONTACT_PATH
        queued = self._page_move(FillContactForm(**given), "form" if here else "to_form")
        if queued:
            return queued
        out = (
            f"Filling {', '.join(given)} on the contact form; the page confirms in a moment."
            if here
            else (
                f"The contact page is opening; {', '.join(given)} go in once it is up (it may "
                "take a few seconds), and the page confirms. Say in a short sentence that you "
                "are taking them to the contact form, and keep talking."
            )
        )
        if refused:
            out += " Not filled: " + "; ".join(refused) + "."
        if "email" in given:
            out += " Read the email back letter by letter."
        return out + " Never say it is sent: they review it and press «Enviar» themselves."

    def _open_exit(self, key: str, line: str) -> str | None:
        exit_ = self.kb.exits.get(key)
        if exit_ is None:
            return None
        self._move(OpenLink(url=exit_.url, label=exit_.label), line)
        return exit_.label

    async def book_visit(self) -> str:
        """Open the school's visit booking (Microsoft Bookings, step four of
        admission: a visit with the admissions officer) in a new tab."""
        label = self._open_exit("visita", "visit")
        if label is None:
            return (
                f"The booking link is not loaded. Show {{page: {ADMISSION_PATH}}}"
                "{show: paso_4_visita}, where its «Agenda AQUÍ» button is."
            )
        return (
            f"Opened {label} in a new tab: they choose a day and time there themselves. Say so in "
            "a sentence."
        )

    async def open_application(self) -> str:
        """Open the online application (Postulación ONLINE, on Alexia; step
        three of admission) in a new tab. Before calling it, say what to have
        ready: step two's documents."""
        label = self._open_exit("postulacion", "apply")
        if label is None:
            return (
                f"The application link is not loaded. Show {{page: {ADMISSION_PATH}}}"
                "{show: paso_3_postula}, where its button is."
            )
        return (
            f"Opened {label} in a new tab. The family fills it in there themselves: it asks for "
            "the child's RUN and details, which you never ask for or type. If you have not yet, "
            "say what to have ready (the family letter to the Directora for a first child, the "
            "birth certificate). If the window for their level has closed, say admissions can "
            "say whether it still takes applications."
        )

    async def open_link(self, request: LinkRequest) -> str:
        """Open one of the school's PDFs, or a families' portal, in a new tab."""
        if request.kind == "portal":
            key = _match(
                request.name, [k for k in self.kb.exits if k not in ("visita", "postulacion")]
            )
            if key is None:
                listed = ", ".join(
                    f"{k} ({e.label})"
                    for k, e in self.kb.exits.items()
                    if k not in ("visita", "postulacion")
                )
                return f"Not opened: no portal '{request.name}'. The portals: {listed}."
            label = self._open_exit(key, "link")
            return f"Opened {label} in a new tab: they log in there themselves."
        doc = self.document(request.name)
        if doc is None:
            named = "; ".join(d.name for d in self.kb.documents if d.note and not d.broken)
            return (
                f"Not opened: no document matches '{request.name}'. The ones worth naming: {named}. "
                "Or show the page that lists them."
            )
        self._move(OpenLink(url=doc.url, label=doc.name), "link")
        unlinked = (
            " The site itself does not link this one: it is on the school's server."
            if not doc.linked
            else ""
        )
        return f"Opened «{doc.name}» in a new tab.{unlinked}"

    async def slide(self, request: SlideRequest) -> str:
        """Move the home page's news carousel or the Infraestructura photo
        gallery one step, by its own arrow; its page opens first if need be."""
        where = HOME if request.slider == "noticias" else INFRA_PATH
        queued = self._page_move(Slide(slider=request.slider, direction=request.direction), "slide")
        if queued:
            return queued
        if self._path != where:
            return (
                f"Its page ({where}) is opening first, then it moves; the page confirms. Say what "
                "they will see while it loads."
            )
        return "Moving it; the page confirms what is showing."

    async def switch_tab(self, request: TabRequest) -> str:
        """Bring another of the visitor's Colegio Everest tabs to the front."""
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
        logger.info("colegioeverest: language -> {} (asked)", request.language)
        return "ok"


__all__ = [
    "ColegioEverestBrain",
    "Cue",
    "FillContactForm",
    "FocusTab",
    "LanguageChanged",
    "Navigate",
    "OpenLink",
    "ShowSection",
    "Slide",
]
