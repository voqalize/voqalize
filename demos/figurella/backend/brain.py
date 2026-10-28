"""FigurellaBrain — Javier, a guide on figurella.cl.

The site is Figurella Chile's, not ours: women's body-shaping centres in
Santiago, with an Italian method (a thermal capsule, oxygen therapy, pressure
therapy, nutrition advice), five plans, seven branches, and a free "Diagnóstico
Corporal" booked through a form in the footer of every page. A browser
extension injects the widget and a small adapter into it; the adapter turns
each :class:`~voqalize.sdk.Action` below into a move on the tab in front — a
page, a place on it scrolled to and ringed, an FAQ opened, a form filled field
by field — and the call itself opens a branch's map in a new tab. Every tab
reports what it shows as a typed event (:mod:`.app_events`), whoever moved it.

This is a port of the Saint George's guide (``demos/saintgeorge``), with the
Universidad Alberto Hurtado guide's form fill (``demos/uahurtado``): talk-throughs that wait for his
speech and run with tools off, one page move at a time, the screen following
his voice.

**A guide for a woman thinking about starting.** Every turn answers what was
asked, in words: the answer, why it matters for what she wants, and a short
offer of the next step — the method, the plan that fits her goal, a story like
hers, her nearest branch, and the free diagnosis, which he books with her by
filling the form as she dictates it.

**Every fact has a source.** A plan, a step, a branch's hours or an agreement
is spoken from L1 (in this prompt), an L2 topic he read, a search of the site,
or what the page itself reported. Never from memory. The site publishes no
price, no plan length, no session count and not the written guarantee's terms:
he says so, and that the free evaluation sets them.

**She presses the button.** He fills the booking form (name, phone, email,
comuna, branch, and a short message he writes from the conversation) and reads
the phone and email back; she reviews it and presses "Reservar mi
diagnóstico" herself. Nothing in this brain or the extension can press it:
there is no Action that submits, and the consent box is never touched. He never
asks for a RUT, a password or a card. When the site answers her press, the page
tells him and he says what happens next.

**The screen follows his voice**, through cues written into his reply
(:mod:`.cues`), carried across the site's full page loads by the extension.

**Spanish or English, as the visitor chose or speaks**, in neutral Latin
American Spanish with "tú". The voice is one man, recorded in each.
"""

from __future__ import annotations

import dataclasses
import math
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
from voqalize_demos.language_hold import HELD_NOTE, heard_language, holds_spanish, may_write_english

from voqalize.sdk import (
    Action,
    Finalize,
    RequestRejected,
    RTVIMessage,
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
    FIGURELLA_EVENTS,
    CommandDone,
    CommandFailed,
    FigurellaEvent,
    FormResult,
    FormState,
    LanguageRequested,
    PageChanged,
    TabInfo,
    TabsChanged,
)
from .comunas import nearest
from .cues import CueKind, CueParser, RawCue, words
from .knowledge import TOPIC_IDS, Anchor, Branch, Knowledge, Page, canonical_path, fold, norm

AGENT_NAME = "Javier"

#: GPT-6.1 Terra at low reasoning, for cost: OpenAI caches every prompt over
#: 1,024 tokens, where Gemini 3.8 Flash cached nothing under about 16k, so most
#: of each turn's input is read from the cache.
MODEL = "gpt-6.1-terra"
REASONING = "low"

#: Santiago, for "today" and a branch's hours.
TIMEZONE = ZoneInfo("America/Santiago")

# ─── Voice and timing ──────────────────────────────────────────────────────────

#: Javier's voice: the speech tier's male persona recorded once in English and
#: once in Spanish, so a switch keeps the same man.
VOICE = Voice.OMNIVOICE_JAVIER

#: A quiet visitor is someone reading a page; a guide beside her says
#: something after a while, and not twice more.
_IDLE_MS = 20_000
_IDLE_NUDGES = 2
#: The idle window while something is owed — the page's answer to a move, a
#: toggle's confirmation, the site's answer to her press: a visitor who reacts
#: speaks first, one who is reading hears it from him.
_TALK_THROUGH_MS = 2_000
#: A little more patience than the demos' default: a phone number or an email
#: is dictated with pauses.
FIGURELLA_PATIENCE = PATIENCE + 2

# ─── Language ──────────────────────────────────────────────────────────────────

#: What he answers in, as the tag both legs of the call take.
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
# Words both languages write ("a", "no", "me", "son", "plan") are in neither list.
_SPANISH_WORDS = frozenset(
    # A word list reads as words, so it stays a split string.
    """que qué de del el los las la una unas unos por para con como cómo cuánto cuanto
    cuánta cuesta cuestan puedes puede podrías quiero quisiera necesito tengo tienes
    tiene hay hola gracias sí está están estoy es eso esto esta este estos pero muy
    también hablar habla hablas hablemos español castellano usted ustedes mi mis tu tus
    su sus nosotros vale bueno claro dónde donde cuál cual cuándo cuando bajar peso
    planes sucursal sucursales hora reservar agendar evaluación muéstrame dime explícame
    quiénes quién vivo mujer
    """.split()  # noqa: SIM905
)
_ENGLISH_WORDS = frozenset(
    """the is are was what how can could you your i i'm it it's this that these those do
    does show me my we our for with about and of to have has there here please want
    would like tell sure yes okay right of course let's lose weight book branch near
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


def language_of(text: str, *, sure: bool = True) -> Lang | None:
    """The language ``text`` is plainly in, or ``None``.

    ``sure`` is for what the visitor said, where one stray word must not move
    the call: Spanish needs two of its words (or its marks and one), English
    three of its own and none of Spanish's. Unsure is for the first words of his
    own reply, which are few: one Spanish word, or two English ones, will do.
    Cues are taken out first: they are the site's words inside any reply."""
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
#: model (``on_finalize``). The method page has a video for each step.
#:
#: The site's own names — Figurella, Huérfanos, Chicureo, Tabancura,
#: presoterapia, oxigenoterapia — are left as written: nothing yet says the
#: Spanish voice says one wrong. If one is heard wrong on dev, respell it here
#: the way "video" is, for the voice only, tuned by ear.
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
    """Go to one of the site's pages and, with ``anchor`` (a key of the
    catalogue) or ``text``, scroll to that place and ring it; with ``faq``,
    open that question of the FAQ. The page loads in full and reports
    ``page_changed``."""

    path: str
    anchor: str | None = None
    text: str | None = None
    faq: str | None = None


class Cue(Action):
    """A move for the page to make when the voice reaches ``at`` — the first
    words of the sentence it belongs to (see :mod:`.cues`); empty ``at`` is
    when the voice stops. With ``path``, it is a :class:`Navigate`; else a
    place, words or FAQ question on the tab in front."""

    at: str
    word: int = 0
    """Words of the unit before it, for a page that times cues by the clock."""
    path: str | None = None
    anchor: str | None = None
    text: str | None = None
    faq: str | None = None


class ShowSection(Action):
    """On the tab in front, scroll to the catalogue's place ``anchor`` and ring
    it (a testimonial is brought into the carousel's view first); with
    ``text``, ring the smallest element containing that text."""

    anchor: str | None = None
    text: str | None = None


class OpenFaq(Action):
    """Open the FAQ question ``question`` (its key, ``faq_precio``, or its
    words) on the page in front, close the one open beside it, and ring it."""

    question: str


class OpenLink(Action):
    """Open a link of the site's in a new tab: a branch's "¿Cómo llegar?" map.
    The visitor goes on there; the extension does nothing on that tab."""

    url: str
    label: str = ""


class FillBookingForm(Action):
    """Type what the visitor dictated into the booking form
    ``#form_agendamiento_figurella`` ("Reserva tu Diagnóstico Corporal sin
    costo"), field by field (the value setter, then ``input``, ``change`` and
    ``blur``), and scroll it into view. A field left ``None`` is not touched;
    ``sucursal`` picks the branch's option by its name. On a page without the
    form (/franquicias/, /gracias/) the home page opens and the fill is made
    there. It never presses "Reservar mi diagnóstico", never submits, and never
    touches the privacy box: once every field is in, the button is rung for her
    to press. Answers ``form_state`` and ``command_done`` / ``command_failed``."""

    nombre: str | None = None
    telefono: str | None = None
    email: str | None = None
    comuna: str | None = None
    sucursal: str | None = None
    mensaje: str | None = None


class FillFranchiseForm(Action):
    """Type what the visitor dictated into the franchise form on /franquicias/
    ("Comunícate con nosotras"), opening that page first when it is not in
    front. Never presses "Contáctame ahora", never submits. Answers
    ``form_state`` and ``command_done`` / ``command_failed``."""

    nombre: str | None = None
    telefono: str | None = None
    email: str | None = None


class FocusTab(Action):
    """Bring one of the visitor's Figurella tabs to the front."""

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
        "'celulitis', 'suelo pélvico', 'cápsula térmica', 'Banmédica', 'efecto rebote'."
    )


class BranchRequest(BaseModel):
    comuna: str = Field(
        description="The comuna or neighbourhood she said she lives or works in, as she "
        "said it, e.g. 'Ñuñoa', 'Las Condes', 'Puente Alto'."
    )


class BookingRequest(BaseModel):
    nombre: str | None = Field(default=None, description="Her name, exactly as she said it.")
    telefono: str | None = Field(
        default=None,
        description="Her phone, exactly the digits she said (with a leading + only if she "
        "said it), never changed, shortened or completed.",
    )
    email: str | None = Field(
        default=None, description="Her email, exactly as she spelled it, never changed."
    )
    comuna: str | None = Field(default=None, description="Her comuna, as she said it.")
    sucursal: str | None = Field(
        default=None,
        description="The branch she chose, by its name: Huérfanos, Costanera, Colón, "
        "Chicureo, Tabancura, Vitacura or Las Perdices.",
    )
    mensaje: str | None = Field(
        default=None,
        description="A short message you write in Spanish from the conversation, one or two "
        "sentences: her goal, the plan that interests her, and when she prefers to be "
        "contacted if she said it, e.g. 'Quiero bajar de peso antes de mi matrimonio en "
        "marzo. Me interesa el Plan Novias. Prefiero que me contacten en la tarde.'",
    )


class FranchiseRequest(BaseModel):
    nombre: str | None = Field(default=None, description="Their name, exactly as said.")
    telefono: str | None = Field(
        default=None, description="Their phone, exactly the digits said, never changed."
    )
    email: str | None = Field(default=None, description="Their email, exactly as spelled.")


class MapRequest(BaseModel):
    branch: str = Field(description="The branch, by its name, e.g. 'Vitacura', 'Colón'.")


class TabRequest(BaseModel):
    tab_id: str = Field(description="The tab_id from the open tabs list.")


class LanguageRequest(BaseModel):
    language: Lang = Field(description="'en' for English, 'es' for Spanish.")


# ─── Places ────────────────────────────────────────────────────────────────────

HOME = "/"
METHOD_PATH = "/metodo-figurella/"
PLANS_PATH = "/planes/"
STORIES_PATH = "/historias-de-exito/"
CONVENIOS_PATH = "/convenios/"
FRANCHISE_PATH = "/franquicias/"
FAQ_PATH = "/preguntas-frecuentes/"
BLOG_PATH = "/consejos/"

#: The pages every move here leans on, as the site serves them (checked
#: 2026-10-24): a cue to one of them is good even before a crawl is loaded.
CORE_PAGES: dict[str, str] = {
    HOME: "Inicio",
    METHOD_PATH: "Método Figurella",
    PLANS_PATH: "Planes",
    STORIES_PATH: "Historias de éxito",
    CONVENIOS_PATH: "Convenios",
    FRANCHISE_PATH: "Franquicias",
    FAQ_PATH: "Preguntas frecuentes",
    BLOG_PATH: "Consejos",
}
#: Where a place a cue names is looked for when it is not on the page in
#: front: a plan on the plans page before its summary on the home page.
_PLACE_ORDER = (PLANS_PATH, METHOD_PATH, STORIES_PATH, CONVENIOS_PATH, HOME, FAQ_PATH)
#: The booking form's place, in the footer of every page but /franquicias/.
CONTACT_ANCHOR = "contacto"

# ─── The prompt ────────────────────────────────────────────────────────────────

_TITLE_SUFFIX = re.compile(r"\s+[-|\u2013\u2014]\s+Figurella\s*$")


def _short_title(title: str) -> str:
    return _TITLE_SUFFIX.sub("", title).strip()


def _places(k: Knowledge) -> str:
    """Every page with the places a cue can show there, by key."""
    lines: list[str] = []
    for path in (*CORE_PAGES, "/politica-de-privacidad/"):
        page = k.page(path)
        title = _short_title(page.title) if page else CORE_PAGES.get(path, path)
        own = [a for a in k.anchors_on(path) if not a.hidden and a.key != CONTACT_ANCHOR]
        lines.append(f"- {path} — {title}")
        for a in own:
            lines.append(f"  - {a.key}: {a.label}")
        if path == FAQ_PATH:
            for f in k.faqs():
                lines.append(f"  - question {f.key}: {f.q}")
    if not lines:
        return "\n".join(f"- {path} — {title}" for path, title in CORE_PAGES.items())
    lines.append(
        f"- Every page but {FRANCHISE_PATH} has, in its footer: {CONTACT_ANCHOR}: the booking "
        "form «Reserva tu Diagnóstico Corporal sin costo»."
    )
    posts = [p for p in k.pages.values() if p.kind == "post"]
    if posts:
        lines.append(
            "- Blog posts, each its own page, with the places titulo, contenido, relacionados:"
        )
        lines += [f"  - {p.path} — {p.title}" for p in posts]
    return "\n".join(lines)


def _branches(k: Knowledge) -> str:
    out = []
    for b in k.branches:
        if not b.anchor:
            continue
        out.append(f"- {b.name}: place sucursal_{b.key} on {HOME}; {b.address}")
    return "\n".join(out) or "- (no branches loaded)"


def _topics(k: Knowledge) -> str:
    return "\n".join(f"- {t.id}: {t.title}" for t in k.topics.values()) or "(none loaded)"


def _prompt(k: Knowledge, today: date | None = None) -> str:
    today = today or datetime.now(TIMEZONE).date()
    return f"""You are {AGENT_NAME}, the guide on the website of Figurella Chile, figurella.cl: centres where women shape their bodies with an Italian method, in Santiago. A visitor, almost always a woman thinking about starting, is browsing the site and has called you from the corner of the page. You can see and move her screen: you open pages, scroll to the exact place that answers her and ring it, open the frequently asked questions, show her nearest branch, open a branch's map, and fill in the booking form for her free body diagnosis as she tells you her details. You are warm, calm and encouraging — the friend who knows Figurella inside out and helps her picture herself there. She should leave clearer, and with her free evaluation booked if she wants it.

# You narrate, and the screen follows your words
You are giving a guided walkthrough, like someone sitting beside her with her screen in front of you both. As you talk about something, it is on her screen, ringed, at that moment.
- Put a screen cue in your reply at the start of the sentence it belongs to. The page moves when your voice reaches that sentence. She never hears a cue.
  - {{page: /path/}} opens a page of the site, at its top.
  - {{show: key}} scrolls to a place and rings it: a key from the places list below, on the page she is on or one a page cue opens. With other words on the page instead of a key, it rings those words.
  - {{faq: key}} opens one of the frequently asked questions and rings it ("faq_precio").
- Use only keys from the places list. A show cue for a place that is not on her page takes her to the page that has it: on the method page, "{{show: plan_novias}}" opens the plans page at the Novias plan.
- Never make up a key. One cue per sentence at most, and only where the screen should change. A cue goes before the sentence, never inside it.
- When she asks where something is ("muéstrame", "show me", "¿dónde está?"), your reply starts with the cue for exactly that thing.
- EVERY ANSWER ABOUT FIGURELLA STARTS WITH A CUE. Whatever you talk about is somewhere on the site, so show it as you begin. A reply without a cue leaves her screen where it was while you describe something else.
- Cues are the only way you move the page, apart from the forms and the map below. Nothing waits on a cue.
- Example, for "¿cómo funciona?": "{{page: {METHOD_PATH}}} Cada sesión tiene tres pasos. {{show: paso_1}} Primero, treinta minutos de ejercicios suaves en una cápsula térmica. {{show: paso_2}} Después, quince minutos de oxigenoterapia. {{show: paso_3}} Y cierras con quince de presoterapia, un drenaje muy relajante. ¿Te cuento qué plan te calzaría mejor?"

# A good turn helps her decide
1. Answer what she asked, first, in plain words, and show it as you say it.
2. Say why it matters for what she wants, in a sentence, when you know her goal.
3. End by offering the next step: one short, specific yes-or-no offer, so she only has to say "sí". "¿Te muestro el plan que te calza?" "Shall I find your nearest branch?" Never "anything else?".
- Deciding has an order. Follow it, from wherever she is: what she wants to achieve, then how the method works, then the plan that fits her goal, then a story like hers or an agreement she has, then her nearest branch, then booking the free diagnosis.
- Ask about her only when the answer changes what you show next: her goal is the first thing worth asking.
- Steer toward the free evaluation gently, once her real questions are answered: it is free and without commitment, and it is where her plan, its price and the written guarantee are set. Never push, never repeat the offer in every turn.

# How you sound
You are heard, not read, so keep it light and warm.
- A turn is two to four short sentences. A walkthrough of a page can run to six, one place per sentence, each with its cue.
- Every sentence under fifteen words. Small, everyday words. One idea per sentence. One number per sentence.
- THE FIRST SENTENCE IS A FEW WORDS. She hears nothing until your first sentence has been voiced, so open every reply with a sentence of two to six words that ends in a full stop, with the answer in it. A cue may come before it.
- Your first word is the answer: no filler, no "great question", no repeating her question back.
- Spoken words only, apart from cues: no lists, no markdown, no symbols, never an exclamation mark. Write numbers, times and percentages as spoken words: "treinta minutos", "de ocho a nueve y media", "treinta por ciento".
- Lines in square brackets come from her screen, not from her. Never read them out; use them.
- Always answer. A reply with no words leaves her in silence.
- One question at a time, and only one per reply.

# Speaking to her
- She is a woman: speak to her in the feminine where Spanish marks it ("¿estás lista?", "bienvenida"). You are a man: masculine for yourself ("estoy encantado").
- Bodies are talked about with respect. Never judge her weight or her body, never say she needs to change, never use words like "gorda" or "rollitos" about her. Talk about what she wants and how the method works toward it.
- No medical promises and no medical advice. Never promise a number of kilos or centimetres, a time to a result, or a health outcome. If she mentions an illness, a pregnancy now, surgery or medication, say kindly that the evaluation at the centre is where they look at her case, and that her doctor's word comes first.
- Success stories are their own experiences, never a promise of hers: "Cuca cuenta que bajó diez kilos", never "vas a bajar diez kilos".

# Never invented
The site publishes no price, no plan length, no number of sessions, no package, and not the terms of the written guarantee. Never say or guess one, whatever she asks.
- Price: there is no fixed price; it depends on her goals and is set at the free evaluation, without commitment. Show {{faq: faq_precio}}.
- The guarantee "por escrito": the site promises it but does not publish its terms; it is explained and signed at the centre.
- Discounts: only the agreements on the convenios page, as written (a percentage, never an amount). "Plan Ideal" appears only in two of them and is not described anywhere: say so if asked.
- A branch's hours, address and phone are as the knowledge below gives them. No branch lists Sunday hours: never say one opens on Sunday.

# Spanish or English
You speak Spanish as a native of Latin America, and English. The call starts in Spanish unless she chose English.
- Answer in Spanish. Move to English only when she says at least two full sentences in English in one turn, or asks for English; then answer in English from that reply on, and if she goes back to Spanish, so do you. Speech recognition often hears a short Spanish reply or a Chilean name as English ("See" for "sí", "And lower net here" for "Lo Barnechea"): she is still speaking Spanish, so answer in Spanish. Your voice follows the language you write.
- Except when she chose a language: a line in square brackets says so. Then answer in that language whatever she speaks, until she asks you to switch.
- When she asks for the other language in words that are not already it ("¿Puedes hablar en inglés?", "Can we speak Spanish?"), answer in that language and call set_language in the same response. A visitor already speaking English to you has been switched: do not call it for her.
- One language per reply.
- Your Spanish is neutral Latin American Spanish, warm and natural for a Chilean woman, never the Spanish of Spain and never heavy slang.
  - Address her as "tú", never "usted" (unless she speaks to you as usted: then you may too); several people are "ustedes", never "vosotros", and never its verb forms ("queréis", "tenéis", "podéis") or "os".
  - Use Latin American words: "celular", never "móvil"; "computador", never "ordenador"; "auto", never "coche"; "mostrar" ("te muestro"), not "enseñar"; "completar", not "rellenar"; "¿Qué día te queda bien?", not "te viene bien"; "disculpa", not "perdona"; "está bien" or "perfecto", never "vale"; "tomar", never "coger".
  - For something just done, use the simple past: "Anoté tu correo", "Ya te lo mostré", not "He anotado".
  - Write "video", never "vídeo".
- Names stay as the site writes them: Figurella, Curvas perfectas, Novias, Mamá reciente, Rejuvenece, Intensivo, Huérfanos, Chicureo, Tabancura, Las Perdices, presoterapia, oxigenoterapia, Diagnóstico Corporal.
- In English, say the site's Spanish names as written and explain them in a few words when they are not obvious ("presoterapia, a lymphatic drainage massage").

# Every response starts with words
Write your answer, with its cues, first; any tool call comes at the end of the same response. What a page call returns reaches you only later.
- The exception is a read: read_topic, search_site and find_branch come straight back to you within this same turn, but each one makes her wait. Answer from what you know below whenever it covers the question, which is most of the time. Read only for a detail that is not here, and then call the read first, with nothing written before it.
- Never promise more to come ("let me check", "one moment", "un momento"): nothing comes after it, and a reply that is only a promise leaves her in silence.

# What that sounds like
Visitor: "Me caso en marzo y quiero verme bien."
You: "{{show: plan_novias}} Tenemos un plan para novias. Te ayuda a modelar la silueta antes de la última prueba del vestido. ¿Te cuento cómo es una sesión?"
Visitor: "¿Cuánto cuesta?"
You: "{{faq: faq_precio}} No hay un precio fijo. Depende de tus objetivos, y se define en la evaluación gratis, sin compromiso. ¿Te ayudo a reservarla?"
Visitor: "Vivo en Ñuñoa."
You: (call find_branch first, then) "{{page: /}}{{show: sucursal_costanera}} La más cercana es Costanera, en Nueva Tajamar doscientos ochenta y nueve. Abre de lunes a viernes de ocho a nueve y media. ¿La dejo marcada en el formulario?"
Visitor: "Do you have an agreement with Banmédica?"
You: "{{show: convenio_banmedica}} Yes, thirty percent off all plans for Banmédica members. Want to book your free evaluation?"
Visitor: "Sí, quiero reservar. Me llamo Ana."
You: "Perfecto, Ana. Lo voy anotando en el formulario. ¿Cuál es tu celular?" then fill_booking_form with nombre.
Visitor: "Nueve ocho siete seis cinco cuatro tres dos uno."
You: "Anoté nueve, ocho, siete, seis, cinco, cuatro, tres, dos, uno. ¿Está bien?" then fill_booking_form with telefono.

# What you know
- Today is {today:%A, %d %B %Y}, in Santiago.
- Every fact comes from the knowledge below, a topic you read, a search result, or what the screen reported. Never from memory. If you cannot find it, say so, and offer what the evaluation or the branch can answer.
- Topics you can read with read_topic, when the knowledge below does not cover a question:
{_topics(k)}
- search_site finds a page, place, question or blog post by its words. Its results name the page and the place's key, which you can then cue.

# Plans
Suggest the plan that fits what she wants, and say the evaluation confirms it: getting married → plan_novias; a baby recently → plan_mama_reciente; over sixty → plan_rejuvenece; specific areas (belly, hips, thighs, glutes, cellulite) → plan_curvas_perfectas; losing a lot of weight overall → plan_intensivo. Show the plan on the plans page as you name it.

# Branches
Seven branches, all in Santiago, on the home page's branch section:
{_branches(k)}
- When she says where she lives or works, call find_branch with her comuna. It tells you the nearest branch or two; show that branch's card with its key as you name it, say its address and hours, and offer to mark it in the booking form. She chooses: never decide for her.
- Its map ("¿Cómo llegar?") opens in a new tab with open_map, only when she asks how to get there or says yes to your offer.
- Montemar, in Concón, is only in the site's WhatsApp button: for the Quinta Región, say so and that she can write to it there. It is not in the booking form.

# Booking her free Diagnóstico Corporal
The booking is a form in the footer of almost every page: name, phone, email, comuna, branch and a message, all required, and a privacy box that comes ticked. After she sends it, the branch contacts her to coordinate. There is no calendar and no time slot to pick.
- When she wants to book, gather her details by voice, one question at a time, using what she already told you, never asking twice: her name, her phone, her email, her comuna, and the branch (offer her nearest).
- Fill each detail in with fill_booking_form as soon as she says it: only the new fields each time. The form comes up on her screen and fills as she talks.
- EVERY BOOKING TURN SPEAKS FIRST. Say back what you noted, in a few words, then ask the one next thing, and put the fill_booking_form call at the end of that same reply. A fill with no words leaves her waiting for the next question.
- Read her phone back digit by digit, and her email letter by letter ("m, a, r, í, a, arroba, gmail, punto, com"), and ask if it is right. Write them exactly as she said them, never changed, shortened or completed; a phone is digits only, with a + only if she said it.
- Write the message yourself, in Spanish, from the conversation: her goal, the plan that interests her, and when she prefers to be called if she said it. Read it back in a sentence and fill it in.
- The privacy box ("Acepto la Política de Privacidad y el contacto por WhatsApp") is already ticked: tell her it is there for her to review. Never change it.
- When everything is in, the page tells you; then say it is ready, and that she presses «Reservar mi diagnóstico» herself when she has checked it. YOU NEVER PRESS IT, and never say it was sent until a bracketed line says the site confirmed it.
- If the site refuses a field, a bracketed line says which: help her fix it and fill the corrected value.
- Never ask for or write a RUT, a password, a card number or any payment detail. If she offers one, say it is not needed.

# Franchises
Someone interested in opening a Figurella (a franchise) is shown {{page: {FRANCHISE_PATH}}} and its benefits. To be contacted, fill the franchise form with fill_franchise_form (name, phone, email), read them back the same way, and they press «Contáctame ahora» themselves. The site gives no investment amount, requirements or territories: say they are explained when Figurella contacts them.

# Moving the page
- Cue only paths and keys from the places list or a search result.
- She can ask you to scroll to or open anything: "muéstrame los convenios", "vuelve al inicio". Do it with a cue at the start of your reply, and say what is now on her screen. Never say you cannot scroll or click.

# Tabs
- She may have several Figurella tabs open. Lines in brackets tell you which tabs are open and which is in front. Your moves happen on the tab in front.
- "Go back to the other tab" is switch_tab with that tab's id.

# Figurella
{k.l1}

# Places on the site, by page, with the keys a cue takes
{_places(k)}
"""


# ─── Greeting ──────────────────────────────────────────────────────────────────

_INTRO: dict[Lang, str] = {
    "en": f"Hi, I'm {AGENT_NAME}, your guide to Figurella.",
    "es": f"Hola, soy {AGENT_NAME}, tu guía de Figurella.",
}
_GREETING: dict[Lang, str] = {
    "en": "I can show you how it works and book your free body diagnosis. What would you like to achieve?",
    "es": "Te muestro cómo funciona y te ayudo a reservar tu diagnóstico corporal gratis. ¿Qué te gustaría lograr?",
}
#: The opener's second sentence for the page the call starts on, by a word in
#: its path; the first match wins, and anything else gets the plain greeting.
_OPENERS: tuple[tuple[str, dict[Lang, str]], ...] = (
    (
        "planes",
        {
            "en": "I can help you find the plan that fits you. What would you like to achieve?",
            "es": "Te ayudo a encontrar el plan que te calza. ¿Qué te gustaría lograr?",
        },
    ),
    (
        "metodo",
        {
            "en": "I can walk you through a session, step by step. Shall I start?",
            "es": "Te explico una sesión, paso a paso. ¿Partimos?",
        },
    ),
    (
        "convenios",
        {
            "en": "I can check if your bank, health plan or school has an agreement. Which one is yours?",
            "es": "Te ayudo a ver si tu banco, isapre o colegio tiene convenio. ¿Cuál es el tuyo?",
        },
    ),
    (
        "historias",
        {
            "en": "I can tell you the stories of women who did it. Shall I start with one?",
            "es": "Te cuento las historias de mujeres que lo lograron. ¿Te cuento una?",
        },
    ),
    (
        "preguntas",
        {
            "en": "I can answer your questions about the method. What would you like to know?",
            "es": "Te respondo tus dudas sobre el método. ¿Qué te gustaría saber?",
        },
    ),
    (
        "franquicias",
        {
            "en": "I can tell you about opening a Figurella. Is that what you're looking for?",
            "es": "Te cuento cómo abrir un Figurella. ¿Es lo que buscas?",
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
    "map": {
        "en": "I've opened the map in a new tab.",
        "es": "Te abrí el mapa en una pestaña nueva.",
    },
    "form": {
        "en": "I'm putting it in the form.",
        "es": "Lo voy anotando en el formulario.",
    },
    "to_form": {
        "en": "I'm taking you to the form.",
        "es": "Te llevo al formulario.",
    },
    "franchise": {
        "en": "I'm putting it in the franchise form.",
        "es": "Lo anoto en el formulario de franquicias.",
    },
    "queued": {
        "en": "I'll do that as soon as the page is ready.",
        "es": "Lo hago apenas la página esté lista.",
    },
    "tab": {"en": "There's that tab.", "es": "Ahí tienes esa pestaña."},
}

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
    underscores and punctuation do not count: "plan novias" is "plan_novias"."""

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


# ─── What she asked about ──────────────────────────────────────────────────────

#: Where to show what the visitor asked about, when his reply forgets to show
#: it: on SendPotion he described a page twice with the screen left where it
#: was, until the visitor said they could not see it. Matched on her own words,
#: English or Spanish, folded; a specific place beats a general one, and among
#: specific ones the first named wins. Each target is (path, place, question).
Target = tuple[str, str | None, str | None]

_ASKED: tuple[tuple[re.Pattern[str], Target], ...] = tuple(
    (re.compile(rf"\b(?:{w})", re.IGNORECASE), target)
    for w, target in (
        (
            r"cuanto cuesta|cuanto vale|precios?\b|cost\w*|price\w*|how much",
            (FAQ_PATH, None, "faq_precio"),
        ),
        (
            r"cuantas veces|frecuencia|how often|times a week|si falto|me salto|miss a session",
            (FAQ_PATH, None, "faq_frecuencia"),
        ),
        (
            r"abdomen|guata|barriga|vientre plano|belly|tummy|flat stomach",
            (FAQ_PATH, None, "faq_abdomen"),
        ),
        (r"caderas?|hips?\b", (FAQ_PATH, None, "faq_caderas")),
        (r"muslos?|gluteos?|piernas|thighs?|glutes|butt", (FAQ_PATH, None, "faq_muslos_gluteos")),
        (r"mucho peso|lose a lot", (FAQ_PATH, None, "faq_perder_mucho_peso")),
        (
            r"novias?\b|boda|matrimonio|me caso|wedding|bride|getting married",
            (PLANS_PATH, "plan_novias", None),
        ),
        (
            r"mama reciente|embaraz|post ?parto|guagua|bebe|baby|pregnan",
            (PLANS_PATH, "plan_mama_reciente", None),
        ),
        (
            r"rejuvenece|sesenta|60 anos|over sixty|older|tercera edad",
            (PLANS_PATH, "plan_rejuvenece", None),
        ),
        (r"intensivo|intensive", (PLANS_PATH, "plan_intensivo", None)),
        (
            r"curvas perfectas|zonas? especific|localizad|celulitis|cellulite",
            (PLANS_PATH, "plan_curvas_perfectas", None),
        ),
        (r"planes|plans?\b|programas?\b", (PLANS_PATH, None, None)),
        (r"capsula|cabina termica|thermal|capsule", (METHOD_PATH, "paso_1", None)),
        (r"oxigeno|oxigenoterapia|oxygen", (METHOD_PATH, "paso_2", None)),
        (r"presoterapia|drenaje|pressotherapy|drainage", (METHOD_PATH, "paso_3", None)),
        (
            r"nutricion|nutricionista|dieta|alimentacion|nutrition|diet\b",
            (METHOD_PATH, "paso_4", None),
        ),
        (
            r"metodo|como funciona|en que consiste|una sesion|sesiones|method|how does it work|session",
            (METHOD_PATH, None, None),
        ),
        (r"garantia|garantiza|guarantee", (HOME, "garantia", None)),
        (
            r"historias|testimonios?|experiencias|resultados de otras|reviews?|stories|testimonials",
            (STORIES_PATH, None, None),
        ),
        (
            r"convenios?|descuentos?|isapre|banco|tarjeta|colegio|discounts?|agreements?|health plan",
            (CONVENIOS_PATH, None, None),
        ),
        (r"franquicia|socio|abrir un figurella|franchise", (FRANCHISE_PATH, None, None)),
        (
            r"suelo pelvico|pelvic floor",
            ("/beneficios-de-ejercitar-el-suelo-pelvico-para-la-mujer/", None, None),
        ),
        (r"blog|consejos|articulos?|tips\b", (BLOG_PATH, None, None)),
        (
            r"sucursal\w*|donde estan|donde quedan|direccion|horarios?|branch\w*|locations?|where are you|"
            r"opening hours|near me|cerca",
            (HOME, "sucursales", None),
        ),
        (
            r"quienes son|figurella es|italian|italiano|anos en chile|who are you",
            (HOME, "intro", None),
        ),
    )
)
#: What a tool moves rather than a cue: the forms take her to themselves, a map
#: opens in a new tab, a tab is switched.
_BY_TOOL = re.compile(
    r"\b(?:reserv\w*|agend\w*|inscrib\w*|formulario|form\b|book\w*|appointment|sign me up|"
    r"llamen|contacten|call me|contact me|mi nombre|me llamo|my name|mi telefono|mi numero|"
    r"mi correo|my email|my phone|arroba|"
    r"como llego|como llegar|mapa|map\b|directions|how do i get|"
    r"tabs?|pestanas?)\b",
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
    this call, not a question about Figurella."""
    return bool(_CALL_LANGUAGE.search(text) and _TO_HIM.search(text))


def asked_target(text: str) -> Target | None:
    """Where on the site what ``text`` asks about is shown, or ``None``. The
    forms, a map and a tab are moved by their tools, and "can you speak
    English?" is about this call: none of them is a place."""
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
    # A place or a question beats a whole page; then the first named.
    specific = [n for n in named if n[3][1] is not None or n[3][2] is not None]
    return min(specific or named)[3]


def asked_page(text: str) -> str | None:
    """The page :func:`asked_target` shows."""
    target = asked_target(text)
    return target[0] if target else None


# ─── Her details ───────────────────────────────────────────────────────────────

_DIGIT_WORDS = {
    w: i
    for i, ws in enumerate(
        [
            ("zero", "cero", "oh"),
            ("one", "uno", "un"),
            ("two", "dos"),
            ("three", "tres"),
            ("four", "cuatro"),
            ("five", "cinco"),
            ("six", "seis"),
            ("seven", "siete"),
            ("eight", "ocho"),
            ("nine", "nueve"),
        ]
    )
    for w in ws
}
_PHONE_MIN = 8


def said_digits(text: str) -> str:
    """Every digit in what the visitor said, in order, written or spoken."""
    out: list[str] = []
    for token in re.findall(r"\d+|[a-z]+", fold(text)):
        if token.isdigit():
            out.append(token)
        elif token in _DIGIT_WORDS:
            out.append(str(_DIGIT_WORDS[token]))
    return "".join(out)


def phone_value(said: str) -> str:
    """A phone as the site's server takes it: digits, with a leading + only if
    it was given. Spaces, dashes, dots and brackets are dropped; nothing else
    is changed."""
    digits = re.sub(r"\D", "", said)
    return ("+" if said.strip().startswith("+") else "") + digits


_EMAIL = re.compile(r"^[\w.+-]+@[\w-]+(?:\.[\w-]+)+$")
#: A Chilean RUT, in any of its spellings: never typed by him.
_RUT = re.compile(r"\b\d{1,2}\.\d{3}\.\d{3}-?[\dkK]\b|\b\d{7,8}-[\dkK]\b")
#: A card number: never typed by him.
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")

#: The moves the page answers (``command_done`` or ``command_failed``), and how
#: long each may take, a full page load included (the home page loads in about
#: thirteen seconds cold).
_MOVE_TAKES_S = {"fill_booking_form": 35.0, "fill_franchise_form": 35.0}
#: Words of his still playing hold the floor no longer than this.
_PLAYOUT_MAX_S = 30.0
#: The longest message he writes into the form.
_MESSAGE_MAX = 400

_FIELD_WORDS: dict[str, dict[Lang, str]] = {
    "nombre": {"en": "name", "es": "nombre"},
    "telefono": {"en": "phone", "es": "teléfono"},
    "email": {"en": "email", "es": "correo"},
    "comuna": {"en": "comuna", "es": "comuna"},
    "sucursal": {"en": "branch", "es": "sucursal"},
    "mensaje": {"en": "message", "es": "mensaje"},
}

#: His own words telling her to press the form's button, which the page's
#: "complete" then need not repeat, if said this recently.
_PRESS_HINT = re.compile(r"\b(?:reservar mi diagnostico|contactame ahora)\b")
_PRESS_HINT_S = 20.0

_SAY_READY = (
    "The form is complete. Say in a sentence or two that everything is in, that the privacy "
    "box is ticked for her to review, and that she presses «Reservar mi diagnóstico» herself "
    "once she has checked it. Never say it was sent."
)
_SAY_FRANCHISE_READY = (
    "The franchise form is complete. Say that everything is in and that they press «Contáctame "
    "ahora» themselves once they have checked it. Never say it was sent."
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
    figurella""".split()  # noqa: SIM905
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
    docs = [(key, set(_terms(label)), set(_terms(text))) for key, label, text in sections if key]
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


#: Places a sentence names outright, in either language: an agreement by its
#: partner, a plan by its name, a story by its woman, a branch by its name (one
#: that is also a comuna only when it is said as a branch). The words of a card are
#: Spanish and few, so an English sentence about Banmédica scored too low to
#: ring its card on a live run (2026-10-24); a name is enough. Each is
#: (pattern over the folded sentence, page, place).
_NAMED: tuple[tuple[re.Pattern[str], str, str], ...] = tuple(
    (re.compile(rf"\b(?:{w})\b"), page, key)
    for w, page, key in (
        (r"banmedica", CONVENIOS_PATH, "convenio_banmedica"),
        (r"colmena", CONVENIOS_PATH, "convenio_colmena"),
        (r"vida tres", CONVENIOS_PATH, "convenio_vida_tres"),
        (r"santander", CONVENIOS_PATH, "convenio_santander"),
        (r"security", CONVENIOS_PATH, "convenio_security"),
        (r"bice", CONVENIOS_PATH, "convenio_bice"),
        (r"itau", CONVENIOS_PATH, "convenio_itau"),
        (r"cencosud|scotiabank", CONVENIOS_PATH, "convenio_cencosud_scotiabank"),
        (r"santiago college", CONVENIOS_PATH, "convenio_santiago_college"),
        (r"wenlock", CONVENIOS_PATH, "convenio_wenlock"),
        (r"colegio aleman|german school", CONVENIOS_PATH, "convenio_colegio_aleman"),
        (r"club mama ripley|mama ripley", CONVENIOS_PATH, "convenio_club_mama_ripley"),
        (r"club novios ripley|novios ripley", CONVENIOS_PATH, "convenio_club_novios_ripley"),
        (r"banco ripley|ripley bank|ripley card", CONVENIOS_PATH, "convenio_banco_ripley"),
        (r"plan novias|bridal plan|brides? plan", PLANS_PATH, "plan_novias"),
        (r"mama reciente|new moms? plan|new mothers?", PLANS_PATH, "plan_mama_reciente"),
        (r"rejuvenece", PLANS_PATH, "plan_rejuvenece"),
        (r"plan intensivo|intensive plan", PLANS_PATH, "plan_intensivo"),
        (r"curvas perfectas|perfect curves", PLANS_PATH, "plan_curvas_perfectas"),
        (r"pamela", STORIES_PATH, "testimonio_pamela"),
        (r"cuca|maria elia", STORIES_PATH, "testimonio_cuca"),
        (r"maria jesus", STORIES_PATH, "testimonio_maria_jesus"),
        (
            r"(?:sucursal|branch) (?:de |of |in )?huerfanos|huerfanos (?:branch|ochocientos)",
            HOME,
            "sucursal_huerfanos",
        ),
        (r"costanera", HOME, "sucursal_costanera"),
        (
            r"(?:sucursal|branch) (?:de |of |in )?colon|colon (?:branch|cuatro mil)",
            HOME,
            "sucursal_colon",
        ),
        (r"(?:sucursal|branch) (?:de |of |in )?chicureo|chamisero", HOME, "sucursal_chicureo"),
        (r"tabancura", HOME, "sucursal_tabancura"),
        (
            r"(?:sucursal|branch) (?:de |of |in )?vitacura|juan xxiii|juan veintitres",
            HOME,
            "sucursal_vitacura",
        ),
        (r"las perdices", HOME, "sucursal_las_perdices"),
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
    parts += [f"{f.q} {f.a}" for f in page.faqs]
    return any(want in norm(p) for p in parts)


# ─── The brain ─────────────────────────────────────────────────────────────────


class FigurellaBrain(OpenAIBrain):
    """One per session. Javier: Figurella's knowledge, its pages and places,
    the forms she fills with him, and a mirror of her tabs, in Spanish or
    English."""

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
        #: The language he speaks now, and the toggle's written confirmation
        #: of a switch, said at the start of his next turn.
        self.spoken: Lang = OPENING
        #: Whether the visitor chose the language, which then holds whatever
        #: she speaks; until she does, it follows what she speaks.
        self._chosen = False
        self._last_heard = ""
        self._confirm: str | None = None
        self._fallback = FallbackLine()
        #: The tab in front as it last reported itself, and whether the model
        #: has seen it since it changed.
        self.page: PageChanged | None = None
        self._path = HOME
        self._page_unseen = False
        #: Every open Figurella tab, and which is in front.
        self.tabs: list[TabInfo] = []
        self._active = ""
        self._tabs_unseen = False
        #: The forms as the page last reported them.
        self.forms: dict[str, FormState] = {}
        #: What she said lately, for checking a phone against her own digits.
        self._heard: list[str] = []
        #: The page this turn's cues are on: the one in front, then wherever a
        #: ``{page: …}`` cue took it.
        self._cue_path = HOME
        self._idle_short = False
        self._nudges = 0
        #: Where to show what she last asked about, at the start of his reply
        #: if it has no cue of its own; see :func:`asked_target`.
        self._backstop: Target | None = None
        #: Whether her last words asked for something a tool moves.
        self._by_tool = False
        #: This reply's moves so far: whether one opened a page, and what was
        #: last rung, so a sentence on the same place does not ring it again.
        self._paged = False
        self._shown: str | None = None
        #: A talk-through owed that is not a move's answer (the site's answer
        #: to her press).
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
        #: When he last told her to press the form's button himself.
        self._press_hint_at = float("-inf")
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
                stt=SttConfig(language=self.spoken, patience=FIGURELLA_PATIENCE),
                tts=TtsConfig(voice=VOICE, language=self.spoken),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
            )
        )
        logger.info(
            "figurella: session start on {} in {}{}",
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
        first word, unless she chose the language she is in; the tab she moved
        to is read in with what she said. The runtime acknowledges her while the
        model thinks (``Config.ack``, on by default)."""
        self._last_heard = msg.text
        heard = None if self._chosen else heard_language(msg.text, self.spoken, language_of)
        if heard is not None and heard != self.spoken:
            await session.configure(self._speaking(heard))
            logger.info("figurella: language -> {} (heard)", heard)
        if holds_spanish(msg.text, self.spoken, language_of):
            logger.info("figurella: held in Spanish: {!r}", msg.text)
            self._note(HELD_NOTE)
        self._heard = [*self._heard[-3:], msg.text]
        # She spoke first: the page's answers are in the context as notes, and
        # he answers them with what she said.
        self._talk = None
        self._outcomes.clear()
        self._idle_deferred = False
        # What he said before has played out, or she spoke over it.
        self._playing = 0
        self._nudges = 0
        # A reply cut off before it said a word keeps its place for the next one.
        # A request to switch language shows nothing.
        self._backstop = (
            None if asks_call_language(msg.text) else asked_target(msg.text) or self._backstop
        )
        # Asked for what a tool moves (a form, a map, a tab): the tool takes
        # her there, so his words open no page.
        self._by_tool = bool(_BY_TOOL.search(fold(msg.text)))
        self._restore_idle()
        self._read_in_screen()
        async for event in super().on_user_message(session, msg):
            yield event

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

        What the page answered after his turn (a form complete, a field the
        site refused, her press confirmed) is in the context already, and the
        idle window was shortened for it, so she hears it from him here.
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
                "Speak into the quiet, briefly, as the guide beside her would: one useful thing "
                "about what is on her screen, or one question that helps you help her. Never ask "
                "whether she is still there, and never repeat your last line."
            )
        else:
            ask = (
                "Still quiet. One last, light offer, different from your last: something you "
                "could show her next. Then let her browse."
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
            logger.warning("figurella: the model returned nothing; asking once more")
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
            if written == "en" and not may_write_english(
                self._last_heard, self.spoken, language_of
            ):
                written = None
            if written is not None and written != self.spoken:
                await session.configure(self._speaking(written))
                logger.info("figurella: language -> {} (written)", written)
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
        """The reply's first words, with what she asked about cued in front of
        them when the reply brings no cue of its own."""
        if self._backstop is None or not chunk.strip():
            return chunk
        (path, place, question), self._backstop = self._backstop, None
        if "{" in chunk or self._page_for(path) is None:
            return chunk
        if question is not None:
            if self.page is not None and question in self.page.faqs and path == self._path:
                return chunk if self._shown == question else f"{{faq: {question}}}{chunk}"
            cue = f"{{faq: {question}}}"
        elif place is not None:
            cue = (
                f"{{show: {place}}}" if path == self._path else f"{{page: {path}}}{{show: {place}}}"
            )
        elif path != self._path:
            cue = f"{{page: {path}}}"
        else:
            return chunk
        logger.info("figurella: the reply has no cue; showing {} first", cue)
        return f"{cue}{chunk}"

    def _send_cue(self, raw: RawCue) -> None:
        """Check a cue against the site, as the tools do, and send it; one that
        names nothing real is dropped and logged rather than reaching the page."""
        if self.spoken == "es" and raw.at:
            raw = dataclasses.replace(raw, at=_anchor_for_voice(raw.at))
        cue = self._resolve_cue(raw)
        logger.info("figurella: cue {} {!r} at {!r} -> {}", raw.kind, raw.value, raw.at, cue)
        if cue is not None:
            self._paged = self._paged or cue.path is not None
            if raw.kind in ("show", "faq"):
                self._shown = cue.anchor or cue.faq or cue.text
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
            if target is not None and target[0] != self._path and self._page_for(target[0]):
                logger.info("figurella: he talks about {} with no cue; opening it", target[0])
                out.append(("page", target[0]))
                path = target[0]
        self._cue_path = path
        # She is dictating her details: the form is on her screen, and stays.
        if kinds & {"show", "faq"} or self._by_tool:
            return out
        # A partner, a plan, a woman or a branch named outright: its card, on
        # this page, or, on the reply's first sentence, on the page that has it.
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
        known = [a for a in self.kb.anchors_on(path) if not a.hidden or a.key == CONTACT_ANCHOR]
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

    def _resolve_cue(self, raw: RawCue) -> Cue | None:
        if raw.kind == "page":
            page = self._page_for(raw.value)
            if page is None:
                return None
            self._cue_path = page.path
            return Cue(at=raw.at, word=raw.word, path=page.path)
        moved = self._cue_path != self._path
        if raw.kind == "faq":
            faqs = self.kb.faqs()
            keys = [f.key for f in faqs]
            hit = _match(raw.value, keys)
            if hit is None and (q := _match(raw.value, [f.q for f in faqs])) is not None:
                hit = keys[[f.q for f in faqs].index(q)]
            if hit is None:
                return None
            here = (self._cue_path if moved else self._path) == FAQ_PATH
            self._cue_path = FAQ_PATH
            return Cue(at=raw.at, word=raw.word, path=None if here else FAQ_PATH, faq=hit)
        # show: a place on the page she will be on, else the same place on
        # another page (a plan on the plans page), else words the page has.
        if (key := self._place(raw.value, self._cue_path, live=not moved)) is not None:
            return Cue(at=raw.at, word=raw.word, path=self._cue_path if moved else None, anchor=key)
        for path in _PLACE_ORDER + tuple(p for p in self.kb.anchors if p not in _PLACE_ORDER):
            if path == self._cue_path:
                continue
            if (key := self._place(raw.value, path, live=False)) is not None and norm(key) == norm(
                raw.value
            ).replace(" ", "_"):
                self._cue_path = path
                return Cue(at=raw.at, word=raw.word, path=path, anchor=key)
        target = self._page_for(self._cue_path)
        live = self.page is not None and not moved and canonical_path(self.page.path) == self._path
        if target is not None and target.sections and not live and not _on_page(raw.value, target):
            logger.info("figurella: {!r} is not on {}; dropped", raw.value, target.path)
            return None
        if re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)+", raw.value.strip()):
            # A key that is nowhere: never sent as words to look for.
            logger.info("figurella: no place {!r}; dropped", raw.value)
            return None
        return Cue(
            at=raw.at, word=raw.word, path=self._cue_path if moved else None, text=raw.value[:120]
        )

    def _talk_now(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The one extra request a turn with nothing in it gets: tools off."""
        return self.respond_with(session, tools=ToolChoice.NONE)

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Page→brain events, folded in silently: no floor taken, no turn."""
        event = FIGURELLA_EVENTS.parse(msg)
        if event is None:
            return
        logger.info("figurella: {} — {}", type(event).__voqal_event__, event)
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
            logger.warning("figurella: switch to {} refused: {}", event.language, rejected)
            self.spoken = was
            session.dispatch(LanguageChanged(language=was))
            return
        logger.info("figurella: language -> {} (toggle)", event.language)
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
            stt=SttConfig(language=language, patience=FIGURELLA_PATIENCE),
            tts=TtsConfig(voice=VOICE, language=language),
        )

    # ─── Page → brain ───────────────────────────────────────────────────

    def apply_event(self, event: FigurellaEvent) -> str | None:
        """Patch the mirror; return the line the model should see."""
        match event:
            case PageChanged():
                self.page = event
                self._path = canonical_path(event.path)
                self._page_unseen = True
                # Read in with her next message or quiet spell: she may click
                # on before she speaks, and only the last page matters.
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
        was = self.forms.get(event.form)
        self.forms[event.form] = event
        name = "booking form" if event.form == "booking" else "franchise form"
        values = "; ".join(f"{k}: {v}" for k, v in event.values.items() if v)
        who = "she typed in it herself" if event.by == "visitor" else "after your fill"
        note = (
            f"[The {name}, {who}: filled {', '.join(event.filled) or 'nothing'}; still empty "
            f"{', '.join(event.missing) or 'nothing'}"
        )
        if event.invalid:
            note += f"; the site would refuse {', '.join(event.invalid)}"
        if values:
            note += f". It holds: {values}"
        if event.form == "booking" and not event.consent:
            note += (
                ". She unticked the privacy box: it is hers to decide; the site needs it to send"
            )
        note += "."
        if event.ready:
            note += " It is complete: she reviews it and presses the button herself.]"
            # Said already, in the reply that made the last fill: not twice.
            told = time.monotonic() - self._press_hint_at < _PRESS_HINT_S
            if (was is None or not was.ready) and not told:
                self._talk_through(_SAY_READY if event.form == "booking" else _SAY_FRANCHISE_READY)
        else:
            note += "]"
        return note

    def _form_result(self, event: FormResult) -> str:
        if event.outcome == "sent":
            if event.form == "booking":
                state = self.forms.get("booking")
                branch = state.values.get("sucursal", "") if state is not None else ""
                where = f"the {branch} branch" if branch else "the branch she chose"
                self._talk_through(
                    "She pressed «Reservar mi diagnóstico» and the site confirmed it was sent. "
                    f"Congratulate her warmly in one sentence, say that {where} will contact her "
                    "by phone or WhatsApp to coordinate her free evaluation, and offer one last "
                    "thing: the map to the branch, or a question before she goes."
                )
            else:
                self._talk_through(
                    "They pressed «Contáctame ahora» and the site confirmed it was sent. Thank "
                    "them in one sentence and say Figurella will contact them."
                )
            said = f" ({event.message})" if event.message else ""
            return f"[The site confirmed the {event.form} form was sent{said}.]"
        fields = ", ".join(event.fields)
        self._talk_through(
            "The site refused the form when she pressed the button"
            + (f": {event.message}" if event.message else "")
            + (f" (fields: {fields})" if fields else "")
            + ". Say plainly what is wrong in a sentence, ask for the corrected detail, and fill "
            "it in again once she says it. Never say it was sent."
        )
        return (
            f"[The site refused the {event.form} form: {event.message or 'an error'}"
            + (f"; fields: {fields}" if fields else "")
            + ".]"
        )

    def _read_in_screen(self) -> None:
        """The tabs and the page in front, once per change, ahead of what she says."""
        if self._tabs_unseen and len(self.tabs) > 1:
            listed = "; ".join(
                f"{t.tab_id}: {t.title or t.url}"
                + (" (in front)" if t.tab_id == self._active else "")
                for t in self.tabs
            )
            self._note(f"[The visitor's open Figurella tabs — {listed}.]")
        self._tabs_unseen = False
        if not self._page_unseen or self.page is None:
            return
        self._page_unseen = False
        p = self.page
        where = {
            "home": "the home page",
            "method": "the method page",
            "plans": "the plans page",
            "stories": "the success stories",
            "convenios": "the agreements page",
            "franchise": "the franchise page",
            "faq": "the FAQ page",
            "blog": "the blog",
            "post": "a blog post",
            "thanks": "the thank-you page",
        }.get(p.kind, "a page")
        note = f"[The tab in front shows {where}: “{p.title or p.path}” ({p.path})."
        if p.anchors:
            note += f" Its places: {_clip(p.anchors, _ANCHORS_IN_NOTE)}."
        form = {"booking": "the booking form in its footer", "franchise": "the franchise form"}
        note += f" It has {form.get(p.form, 'no form')}."
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
        talked through in the next short quiet spell, unless she speaks first;
        a fill that went in is not (he said it as he filled), unless what was
        queued behind it could not be sent."""
        if command not in self._sent:
            return
        del self._sent[command]
        if (queued := self._queued) is not None and not self._busy():
            self._queued = None
            name = queued.__voqal_action__
            if " done" in outcome:
                logger.info("figurella: {} answered; sending the {} queued", command, name)
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
        A fill queued behind a fill of the same form keeps both fills' fields."""
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
        logger.info("figurella: {} queued behind {}", action.__voqal_action__, running)
        return (
            f"Queued, not sent yet: the page is still working on {running}. It goes to the page "
            "as soon as the page answers that. Say in a few words that you are noting it; never "
            "that it is done, and do not call it again."
        )

    def _take_ask(self) -> str | None:
        """What he has to talk through now — the page's answers to his moves,
        the site's answer to her press — and nothing left after."""
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

    # ─── Her details, checked ───────────────────────────────────────────

    def _checked(self, given: dict[str, str]) -> tuple[dict[str, str], list[str]]:
        """``given`` with a phone and an email made what the site takes, and
        what was refused, in words the model can act on."""
        refused: list[str] = []
        if (email := given.get("email")) is not None:
            email = "".join(email.split()).lower()
            if not _EMAIL.match(email):
                refused.append(f"email {email!r} is not an address: ask her to spell it again")
                given.pop("email")
            else:
                given["email"] = email
        if (telefono := given.get("telefono")) is not None:
            value = phone_value(telefono)
            digits = value.lstrip("+")
            heard = said_digits(" ".join(self._heard[-2:]))
            bare = digits[2:] if digits.startswith("56") and not heard.startswith("56") else digits
            if len(digits) < _PHONE_MIN or (len(heard) >= _PHONE_MIN and bare not in heard):
                said = f" (she said {' '.join(heard)})" if len(heard) >= _PHONE_MIN else ""
                refused.append(
                    f"telefono {' '.join(digits) or repr(telefono)} is not what she said{said}: never "
                    "change, shorten or complete her digits; ask again"
                )
                given.pop("telefono")
            else:
                given["telefono"] = value
        return given, refused

    @staticmethod
    def _given(request: BaseModel) -> dict[str, str]:
        return {
            k: " ".join(v.split()) if k != "mensaje" else v.strip()
            for k, v in request.model_dump().items()
            if isinstance(v, str) and v.strip()
        }

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        """Read and search Figurella's knowledge; find her nearest branch;
        fill the booking and franchise forms as she dictates; open a branch's
        map; move between her tabs; switch language."""
        return [
            self.read_topic,
            self.search_site,
            self.find_branch,
            self.fill_booking_form,
            self.fill_franchise_form,
            self.open_map,
            self.switch_tab,
            self.set_language,
        ]

    @needs_result_now
    async def read_topic(self, request: TopicRequest) -> str:
        """Read one of Figurella's knowledge topics before answering from it."""
        topic = self.kb.topics.get(request.topic)
        if topic is None:
            return f"No topic '{request.topic}' is written yet: use search_site."
        return topic.text

    @needs_result_now
    async def search_site(self, request: SearchRequest) -> str:
        """Search figurella.cl's pages, places, FAQ answers and blog posts. Each
        result names the page path and the place's key to show."""
        hits = self.kb.search(request.query, _SEARCH_HITS)
        if not hits:
            return (
                f"Nothing on figurella.cl matches '{request.query}'. Try other words in Spanish, "
                "or say it is something the free evaluation answers."
            )
        out: list[str] = []
        for h in hits:
            if h.kind == "faq":
                out.append(f"[FAQ question {h.section} on {h.path}] {h.title}\n  {h.snippet}")
            elif h.kind == "post":
                where = f", place: {h.section}" if h.section else ""
                out.append(f"[blog post] {h.title} — path: {h.path}{where}\n  {h.snippet}")
            else:
                where = f", place: {h.section}" if h.section else ""
                out.append(f"[page] {h.title} — path: {h.path}{where}\n  {h.snippet}")
        return "\n".join(out)

    @needs_result_now
    async def find_branch(self, request: BranchRequest) -> str:
        """The branch nearest the comuna she lives or works in, with its
        address, hours and phone, and the key of its card to show."""
        keys = nearest(request.comuna)
        if keys == ("montemar",):
            branch = self.kb.branch("montemar")
            number = branch.whatsapp if branch is not None else ""
            return (
                f"{request.comuna} is in the Quinta Región: all seven branches on the site are in "
                "Santiago. The site's WhatsApp button lists one more, Montemar, at Las Pelargonias "
                f"842, local 101, Concón{f' (WhatsApp {number})' if number else ''}; it is not in "
                "the booking form. Say so, and that she can write to it from the WhatsApp button "
                "at the bottom right of the page, or book at a Santiago branch."
            )
        if keys is None:
            listed = "; ".join(f"{b.name}: {b.address}" for b in self.kb.branches if b.anchor)
            return (
                f"'{request.comuna}' is not a comuna I place. The branches are: {listed}. Ask her "
                f"which is easiest for her, and show them with {{page: {HOME}}}{{show: sucursales}}."
            )
        found = [b for k in keys if (b := self.kb.branch(k)) is not None and b.anchor]
        if not found:
            return "The branches are not loaded: show {show: sucursales} and let her choose."
        lines = [self._branch_line(b) for b in found]
        first = found[0]
        return (
            f"Nearest to {request.comuna}, by address: "
            + " Then: ".join(lines)
            + f" Show the first one's card ({{page: {HOME}}}{{show: {first.anchor}}} if she is "
            "not on the home page), say its address and weekday hours in spoken words, and offer "
            "to mark it in the booking form. It is a suggestion: she chooses."
        )

    @staticmethod
    def _branch_line(b: Branch) -> str:
        hours = " ".join(b.hours) or "hours not given"
        wa = (
            f" WhatsApp {b.whatsapp}."
            if b.whatsapp and b.whatsapp.replace(" ", "") != b.phone.replace(" ", "")
            else ""
        )
        return f"{b.name} (place {b.anchor}): {b.address} Phone {b.phone}. {hours}{wa}"

    async def fill_booking_form(self, request: BookingRequest) -> str:
        """Fill the booking form for her free Diagnóstico Corporal with what
        she said: only the new fields each time. On a page without it, the
        home page opens and it is filled there. Never sent: she presses
        «Reservar mi diagnóstico» herself."""
        given = self._given(request)
        if any(_RUT.search(v) or _CARD.search(v) for k, v in given.items() if k != "telefono"):
            return (
                "Not filled: that looks like a RUT or a card number, which the form never asks "
                "for. Leave it out and tell her it is not needed."
            )
        if (t := given.get("telefono")) is not None and _RUT.search(t):
            return "Not filled: that is a RUT, not a phone. Ask for her phone number."
        given, refused = self._checked(given)
        if (said := given.get("sucursal")) is not None:
            branch = self.kb.branch(said)
            names = [b.name for b in self.kb.branches if b.anchor]
            if branch is None and (hit := _match(said, names)) is not None:
                branch = self.kb.branch(hit)
            if branch is None or not branch.anchor:
                given.pop("sucursal")
                refused.append(
                    f"sucursal {said!r} is not in the form's list ({', '.join(names)})"
                    + (
                        ": Montemar is only in the WhatsApp button"
                        if "montemar" in fold(said)
                        else ""
                    )
                )
            else:
                given["sucursal"] = branch.name
        if (msg := given.get("mensaje")) is not None:
            given["mensaje"] = msg[:_MESSAGE_MAX]
        if not given:
            return "Not filled: " + ("; ".join(refused) or "nothing to fill yet.")
        here = self.page.form if self.page is not None else "booking"
        queued = self._page_move(
            FillBookingForm(**given),  # type: ignore[arg-type]
            "form" if here == "booking" else "to_form",
        )
        if queued:
            return queued
        out = (
            f"Filling {', '.join(given)} on the booking form; the page confirms in a moment."
            if here == "booking"
            else (
                f"The page in front has no booking form, so the home page is opening with it; "
                f"{', '.join(given)} go in once it is up, and the page confirms. Say in a short "
                "sentence that you are taking her to the form."
            )
        )
        if refused:
            out += " Not filled: " + "; ".join(refused) + "."
        if "telefono" in given or "email" in given:
            out += " Read the phone back digit by digit and the email letter by letter."
        return out + " Never say it is sent: she reviews it and presses the button herself."

    async def fill_franchise_form(self, request: FranchiseRequest) -> str:
        """Fill the franchise form on /franquicias/ ("Comunícate con nosotras")
        with what they said, opening that page first if need be. Never sent:
        they press «Contáctame ahora» themselves."""
        given = self._given(request)
        if any(_RUT.search(v) for v in given.values()):
            return "Not filled: that is a RUT, which the form never asks for. Leave it out."
        given, refused = self._checked(given)
        if not given:
            return "Not filled: " + ("; ".join(refused) or "nothing to fill yet.")
        queued = self._page_move(FillFranchiseForm(**given), "franchise")  # type: ignore[arg-type]
        if queued:
            return queued
        here = self._path == FRANCHISE_PATH
        out = (
            f"Filling {', '.join(given)} on the franchise form; the page confirms in a moment."
            if here
            else f"The franchise page is opening; {', '.join(given)} go in once it is up."
        )
        if refused:
            out += " Not filled: " + "; ".join(refused) + "."
        return out + " Never say it is sent: they press «Contáctame ahora» themselves."

    async def open_map(self, request: MapRequest) -> str:
        """Open a branch's map ("¿Cómo llegar?") in a new tab."""
        branch = self.kb.branch(request.branch)
        names = [b.name for b in self.kb.branches if b.maps]
        if branch is None and (hit := _match(request.branch, names)) is not None:
            branch = self.kb.branch(hit)
        if branch is None or not branch.maps:
            return f"Not opened: no map for '{request.branch}'. The branches with one: {', '.join(names)}."
        self._move(OpenLink(url=branch.maps, label=f"Cómo llegar a {branch.name}"), "map")
        return f"Opened the map to {branch.name} ({branch.address}) in a new tab."

    async def switch_tab(self, request: TabRequest) -> str:
        """Bring another of the visitor's Figurella tabs to the front."""
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
        listening and speaking. Call it when she asks for the other language in
        words that are not already it — "Can we speak Spanish?" — and to go
        back. Say one short line in the language you are switching to, in the
        same response. A visitor already speaking English has been switched: do
        not call it for her."""
        self._chosen = True
        configure_soon(self.session, self._speaking(request.language))
        logger.info("figurella: language -> {} (asked)", request.language)
        return "ok"


__all__ = [
    "Cue",
    "FigurellaBrain",
    "FillBookingForm",
    "FillFranchiseForm",
    "FocusTab",
    "LanguageChanged",
    "Navigate",
    "OpenFaq",
    "OpenLink",
    "ShowSection",
]
