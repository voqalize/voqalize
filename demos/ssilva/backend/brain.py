"""SsilvaBrain — Javier, a guide on ssilva.cl, a Chilean real-estate site.

The site is Ssilva's, not ours. A browser extension injects the widget and a
small adapter into ssilva.cl; the adapter turns each :class:`~voqalize.sdk.Action`
below into a move on the visitor's tab — a page opened, a section scrolled to and
ringed, a typology selected, the project list filtered, the gallery or the tour
opened, the quote form filled in — and every page reports what it shows as a
typed event (:mod:`.app_events`), whichever of the visitor and Javier moved it.
Every link on ssilva.cl is a full page load; the extension keeps the call and
replays a move that was meant for the page it is loading.

Five things shape every decision here.

**A guide, not a search box.** Every turn answers what was asked, in words, as
a conversation: the answer, why it matters for this buyer, and an offer of the
next step. He asks about the visitor only when the answer changes what he shows
— to live or to invest, which area, how many bedrooms, a budget in UF — and
offers the choices.

**Every fact has a source.** A price, a typology, a status, an address or a
phone number is spoken from L1 (the roster, in this prompt), a project or guide
he read, or what the page itself reported. Never from memory. The page in front
wins: a typology's price on screen can differ from the list's "desde".

**Nothing on the page is invented.** A path, a section, a typology, a project
to ring on the list is checked against the crawl and against what the tab last
reported; anything else is refused before it reaches the page.

**The quote form is the visitor's.** He fills in what they tell him, a few
fields a turn, reads the email back and spells the RUT back, maps what they say
to the form's own options, and never presses Enviar.

**The screen follows his voice.** He writes his moves into the reply as cues
(``{show: tipologías}``, ``{plan: 2D | 2B}``), at the start of the sentence they
belong to; the brain takes them out of the speech, checks them against the
site, and the page fires each as the voice reaches its sentence (:mod:`.cues`).

**Spanish first, English on request.** The site and its visitors are Chilean,
so the call opens in Spanish; a visitor who speaks English, presses the
widget's toggle or asks is answered in English from then on, with both legs of
the call moved together. A language the visitor chose holds whatever they speak.
His Spanish is neutral Latin American Spanish; in English he describes the
Spanish page and explains the local terms (UF, pie, RUT, "en blanco").

This is SendPotion's guide (``demos/sendpotion``) moved to a new site: the
nods, the written lines for a silent turn, the language handling, the cue
backstop and the talk-through after a page result are the same machinery.
"""

from __future__ import annotations

import dataclasses
import inspect
import math
import re
import time
from collections.abc import AsyncGenerator
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
    SSILVA_EVENTS,
    CommandFailed,
    LanguageRequested,
    LeadFormState,
    LeadSubmitted,
    PageChanged,
    PhotoShown,
    ProjectsListed,
    SsilvaEvent,
    TabInfo,
    TabsChanged,
    TypologyShown,
    ViewerClosed,
)
from .cues import CueKind, CueParser, RawCue, words
from .knowledge import (
    COMMUNE_IDS,
    REGION_LABELS,
    TOPIC_IDS,
    Knowledge,
    Project,
    canonical_path,
    fold,
    match_typology,
    property_of,
    region_of,
    site_path,
    typology_key,
)

AGENT_NAME = "Javier"

#: LOW, as SendPotion and Saatvik measured: at MINIMAL, Gemini mostly made the
#: page call first and wrote nothing; at LOW it writes the answer first.
THINKING = types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)
#: SendPotion's model: on its prompt it had first words out in about two seconds
#: and wrote the screen cues correctly.
MODEL = "gemini-3.8-flash"

# ─── Voice and timing ──────────────────────────────────────────────────────────

#: Javier's voice, recorded once in English and once in Spanish, so a switch
#: keeps the same man.
VOICE = Voice.OMNIVOICE_JAVIER

#: A quiet visitor is reading a project page; a guide beside them says
#: something after a while, and not twice more.
_IDLE_MS = 20_000
_IDLE_NUDGES = 2
#: The idle window while a result the page produced is waiting to be talked
#: through (the form's second step, a press of Enviar): a visitor who reacts
#: speaks first, one who is reading hears it from him.
_TALK_THROUGH_MS = 2_000
#: A little more patience than the demos' default: a buyer thinking aloud about
#: a budget or a family pauses mid-sentence, and a RUT is read out in pieces.
SSILVA_PATIENCE = PATIENCE + 2
#: A message this soon after the last one is the rest of the same thought.
_FRAGMENT_S = 4.0

# ─── Language ──────────────────────────────────────────────────────────────────

Lang = Literal["en", "es"]
#: The site and its visitors are Chilean: the call opens in Spanish.
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
# Words both languages write ("a", "no", "son") are in neither list.
_SPANISH_WORDS = frozenset(
    # A word list reads as words, so it stays a split string.
    """que qué de del el los las la una unas unos por para con como cómo cuánto cuanto
    cuánta cuesta cuestan puedes puede podrías quiero quisiera necesito tengo tienes
    tiene hay hola gracias sí está están estoy es eso esto esta este estos pero muy
    también hablar habla hablas hablemos español castellano usted ustedes mi mis tu tus
    su sus nosotros vale bueno claro dónde donde cuál cual cuándo cuando precio precios
    muéstrame dime explícame busco buscando quiero quieres algo más hace hacer
    """.split()  # noqa: SIM905
)
_ENGLISH_WORDS = frozenset(
    """the is are was what how can could you your i i'm it it's this that these those do
    does show me my we our for with about and of to have has there here please want
    would like tell sure yes okay right of course let's looking need in on at an some any
    which where when who see look find give hi hello thanks thank much many
    """.split()  # noqa: SIM905
)
#: Enough of his reply to tell its language: its first sentence, or this many
#: characters. On SendPotion's dev call 826ccd1f the first chunk was " P".
_WRITTEN_ENOUGH = 60
_SENTENCE_END = re.compile(r"[.?!](?:\s|$)")
#: Letters and marks only Spanish writes, of the two.
_SPANISH_MARKS = re.compile(r"[¿¡ñáéíóú]", re.IGNORECASE)
_LETTERS = re.compile(r"[\wáéíóúüñ']+")
#: A cue is the site's own words, in Spanish whatever he speaks.
_CUE_TEXT = re.compile(r"\{[^{}]*\}?")


def _places(k: Knowledge) -> re.Pattern[str]:
    """The site's place and project names: "Las Condes", "Viña del Mar" and
    "Mira al Mar" are Spanish words inside an English sentence."""
    names = {p.comuna for p in k.projects.values()} | {p.name for p in k.projects.values()}
    names |= set(kb.REGION_LABELS.values()) | {"La Dehesa", "Región de Valparaiso", "V Región"}
    alts = sorted((re.escape(n) for n in names if n), key=len, reverse=True)
    return re.compile(rf"\b(?:{'|'.join(alts)})\b", re.IGNORECASE) if alts else re.compile(r"$^")


_PLACES = _places(kb.KNOWLEDGE)


def language_of(text: str, *, sure: bool = True) -> Lang | None:
    """The language ``text`` is plainly in, or ``None``.

    ``sure`` is for what the visitor said, where one stray word must not move
    the call: Spanish needs two of its words (or its marks and one), English
    three of its own and none of Spanish's. Unsure is for the first words of his
    own reply, which are few: one Spanish word, or two English ones, will do.
    Cues and the site's place names are left out: they are Spanish inside an
    English sentence ("projects in Las Condes")."""
    text = _PLACES.sub(" ", _CUE_TEXT.sub(" ", text))
    found = set(_LETTERS.findall(text.lower()))
    es = len(found & _SPANISH_WORDS) + (1 if _SPANISH_MARKS.search(text) else 0)
    en = len(found & _ENGLISH_WORDS)
    if es >= (2 if sure else 1) and es > en:
        return "es"
    if en >= (3 if sure else 2) and es == 0:
        return "en"
    return None


#: Latin America says "vi-DE-o"; Spain says "VÍ-deo". On SendPotion's dev calls
#: the Spanish voice read plain "video" as "VÍ-deo" in one sentence of three;
#: spelled "bidéo" it said "vi-DE-o" every time. Project pages here have a
#: "video tour", so in Spanish the voice is handed "bidéo", and only the voice:
#: the cue anchors follow the same spelling, and what comes back as heard is
#: spelled "video" again before it reaches the model.
_VIDEO_TO_VOICE = re.compile(r"\b([Vv])[ií]deo(s?)\b")
_VIDEO_FROM_VOICE = re.compile(r"\b([Bb])idéo(s?)\b")
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


def _chosen_note(language: Lang, how: str) -> str:
    name = LANGUAGE_NAMES[language]
    return (
        f"[The visitor chose {name} {how}. Answer in {name} from now on, whatever "
        "language they speak to you, until they ask for the other one.]"
    )


# ─── Numbers as spoken words ───────────────────────────────────────────────────

_ES_UNITS = [
    "cero",
    "una",
    "dos",
    "tres",
    "cuatro",
    "cinco",
    "seis",
    "siete",
    "ocho",
    "nueve",
    "diez",
    "once",
    "doce",
    "trece",
    "catorce",
    "quince",
    "dieciséis",
    "diecisiete",
    "dieciocho",
    "diecinueve",
    "veinte",
    "veintiuna",
    "veintidós",
    "veintitrés",
    "veinticuatro",
    "veinticinco",
    "veintiséis",
    "veintisiete",
    "veintiocho",
    "veintinueve",
]
_ES_TENS = {
    3: "treinta",
    4: "cuarenta",
    5: "cincuenta",
    6: "sesenta",
    7: "setenta",
    8: "ochenta",
    9: "noventa",
}
_ES_HUNDREDS = [
    "",
    "ciento",
    "doscientas",
    "trescientas",
    "cuatrocientas",
    "quinientas",
    "seiscientas",
    "setecientas",
    "ochocientas",
    "novecientas",
]
_EN_UNITS = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
_EN_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()  # noqa: SIM905


def _es_below_1000(n: int) -> str:
    """0 < n < 1000, feminine: UF are "unidades"."""
    if n == 100:
        return "cien"
    hundreds, rest = divmod(n, 100)
    out = [_ES_HUNDREDS[hundreds]] if hundreds else []
    if rest:
        if rest < 30:
            out.append(_ES_UNITS[rest])
        else:
            tens, unit = divmod(rest, 10)
            out.append(_ES_TENS[tens] + (f" y {_ES_UNITS[unit]}" if unit else ""))
    return " ".join(out)


def _en_below_1000(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    out = [f"{_EN_UNITS[hundreds]} hundred"] if hundreds else []
    if rest:
        if rest < 20:
            out.append(_EN_UNITS[rest])
        else:
            tens, unit = divmod(rest, 10)
            out.append(_EN_TENS[tens] + (f"-{_EN_UNITS[unit]}" if unit else ""))
    return " ".join(out)


def number_words(n: int, lang: Lang) -> str:
    """``3375`` → "tres mil trescientas setenta y cinco" / "three thousand
    three hundred seventy-five": a price in UF, as he says it. Up to 999,999."""
    if n <= 0:
        return "cero" if lang == "es" else "zero"
    thousands, rest = divmod(min(n, 999_999), 1000)
    out: list[str] = []
    if lang == "es":
        if thousands == 1:
            out.append("mil")
        elif thousands:
            lead = _es_below_1000(thousands)
            # "veintiún mil", "treinta y un mil": the word before "mil" is cut.
            lead = re.sub(r"veintiuna$", "veintiún", lead)
            lead = re.sub(r"\buna$", "un", lead)
            out.append(f"{lead} mil")
        if rest:
            out.append(_es_below_1000(rest))
    else:
        if thousands:
            out.append(f"{_en_below_1000(thousands)} thousand")
        if rest:
            out.append(_en_below_1000(rest))
    return " ".join(out)


def uf_words(n: int | None, lang: Lang) -> str:
    """A price in UF as he says it: "trece mil novecientas setenta y seis UF"."""
    return "" if n is None else f"{number_words(n, lang)} UF"


# ─── Actions (brain → page) ────────────────────────────────────────────────────


class Navigate(Action):
    """Go to one of ssilva.cl's pages (a full page load) and then, with
    ``heading`` or ``text``, scroll to that section and ring it; with
    ``typology``, select that typology on a project page. The page reports
    ``page_changed``."""

    path: str
    heading: str | None = None
    text: str | None = None
    typology: str | None = None


class Cue(Action):
    """A move for the page to make when the voice reaches ``at`` — the first
    words of the sentence it belongs to (see :mod:`.cues`); empty ``at`` is
    when the voice stops. With ``path``, it is a :class:`Navigate`; with
    ``card``, the card of the project whose page is at that path, rung on the
    project list (paged to) as he names it, ``text`` its name; with
    ``photo``, that photo of ``photos`` full screen; else a section, words or
    a typology on the page in front. ``heading`` may be a section's heading
    or its canonical name: ``galería``, ``tipologías``, ``amenidades``,
    ``tour``, ``estado``, ``brochure``, ``contacto``, ``formulario``."""

    at: str
    word: int = 0
    """Words of the unit before it, for a page that times cues by the clock."""
    path: str | None = None
    heading: str | None = None
    text: str | None = None
    typology: str | None = None
    card: str | None = None
    photo: int | None = None
    photos: Literal["gallery", "amenities"] | None = None


class ShowSection(Action):
    """On the page in front, scroll to the heading or canonical section named
    ``heading`` and ring it; with ``text``, ring the smallest element
    containing that text (a price, a card)."""

    heading: str | None = None
    text: str | None = None


class SelectTypology(Action):
    """On a project page, select the typology labelled ``label`` ("2D | 2B"),
    ring its price and floor plan. The page reports ``typology_shown``."""

    label: str


class ShowProjects(Action):
    """Open the project list (``/proyectos/``) filtered by ``region``
    ("metropolitana", "valparaiso", "otros") and ``property``
    ("departamento", "casa", "oficina", "local"), tick the first of ``communes``
    (names as the filter writes them; only the Región Metropolitana has them,
    and it takes one at a time), and ring
    the cards of the ``highlight`` projects (names as the cards write them),
    found by their project pages in ``paths``, which a translated page does
    not rewrite, paging if needed. The page reports ``projects_listed``."""

    region: str | None = None
    property: str | None = None
    communes: list[str] = Field(default_factory=list[str])
    highlight: list[str] = Field(default_factory=list[str])
    paths: list[str] = Field(default_factory=list[str])


class ShowPhotos(Action):
    """On a project page: ``gallery`` scrolls to the photo gallery and moves it
    to photo ``index`` (1 for the first), or with ``fullscreen`` opens it full
    screen at that photo; ``amenities`` opens the amenities' photos full
    screen at photo ``index``. The page reports ``photo_shown``."""

    which: Literal["gallery", "amenities"]
    index: int | None = None
    fullscreen: bool = False


class StepPhoto(Action):
    """The next photo (``back``: the previous one) in the full-screen viewer,
    or on the gallery's slider when it is not open."""

    back: bool = False


class Slideshow(Action):
    """``play``: the photos full screen, one every ``seconds``, from the one
    shown (the gallery's, unless ``which`` says the amenities'), until
    stopped. Not ``play``: stop on the photo shown. The visitor starting to
    speak stops it too."""

    play: bool = True
    which: Literal["gallery", "amenities"] | None = None
    seconds: int | None = None


class ShowFloorPlan(Action):
    """A typology's floor plan, full screen: on a project page, select
    ``typology`` (when given) and open its plan; on a cotizar page, the
    typology's unit plan and its place on the floor."""

    typology: str | None = None


class OpenTour(Action):
    """On a project page, open its virtual tour (a modal). Fails, with a
    reason, where the page has none."""


class CloseOverlay(Action):
    """Close what is open over the page: the full-screen photos or plan, a
    lightbox, the tour's modal."""


class FillLeadForm(Action):
    """On a project page, scroll to the quote form beside the typologies, ring
    it, and fill in the fields given (a dropdown by its exact option text). What
    is filled stays. With ``next_step``, once step one is complete, press
    "Siguiente". It never presses "Enviar". The form reports ``lead_form``."""

    firstname: str | None = None
    lastname: str | None = None
    rut: str | None = None
    email: str | None = None
    phone: str | None = None
    motivo: str | None = None
    tipologia: str | None = None
    ingreso: str | None = None
    pie: str | None = None
    next_step: bool = False


class OpenWhatsApp(Action, name="open_whatsapp"):
    """Open the project's WhatsApp chat with its sales executive in a new tab."""


class FocusTab(Action):
    """Bring one of the visitor's ssilva.cl tabs to the front."""

    tab_id: str


class LanguageChanged(Action):
    """The call's language moved, by the toggle, by voice or by
    ``set_language``: the widget's toggle follows at once."""

    language: Literal["en", "es"]


# ─── Tool requests ─────────────────────────────────────────────────────────────

if TYPE_CHECKING:
    TopicId = str
else:
    # The guides present at import, as the tool's enum; see knowledge.TOPIC_IDS.
    TopicId = Literal[TOPIC_IDS]


class FindRequest(BaseModel):
    """Only what the visitor said or clearly meant: leave the rest out."""

    comuna: str | None = Field(
        default=None,
        description="A comuna or place, as the visitor said it: 'Las Condes', 'Viña', "
        "'Santiago centro', 'Reñaca'. Several, comma-separated.",
    )
    region: str | None = Field(
        default=None,
        description="'metropolitana' (Santiago), 'valparaiso' (the coast, 'playa', "
        "'V Región') or 'otros' (Pucón).",
    )
    tipo: str | None = Field(
        default=None, description="'departamento', 'casa', 'oficina' or 'local'."
    )
    dormitorios: int | None = Field(
        default=None, description="Bedrooms they need; 0 for a studio (estudio)."
    )
    max_uf: float | None = Field(default=None, description="Their top budget, in UF.")
    min_uf: float | None = Field(default=None, description="A floor, in UF, rarely needed.")
    estado: str | None = Field(
        default=None,
        description="'entrega inmediata' (ready now), 'en blanco' (off-plan), 'en verde' or "
        "'en construcción'.",
    )
    perfil: str | None = Field(
        default=None, description="'vivir', 'invertir' or 'segunda vivienda'."
    )


class ProjectRequest(BaseModel):
    name: str = Field(
        description="The project's name, as said: 'Estocolmo', 'Uniq', 'Canal Beagle'."
    )


class TopicRequest(BaseModel):
    topic: TopicId = Field(description="The guide to read, by its name.")


class SearchRequest(BaseModel):
    query: str = Field(
        description="A few words to look for on ssilva.cl: 'arriendo garantizado', "
        "'piscina', 'tasa subsidiada'."
    )


class ShowProjectsRequest(BaseModel):
    region: str | None = Field(
        default=None, description="'metropolitana', 'valparaiso' or 'otros'."
    )
    property: str | None = Field(
        default=None, description="'departamento', 'casa', 'oficina' or 'local'."
    )
    communes: list[str] = Field(
        default_factory=list[str],
        description="One comuna to tick, e.g. ['Las Condes']: the list filters one at a "
        "time. A comuna on the coast has no checkbox: its projects are rung instead.",
    )
    highlight: list[str] = Field(
        default_factory=list[str],
        description="Project names to ring on the list, best first, from find_projects.",
    )


class PhotosRequest(BaseModel):
    which: Literal["gallery", "amenities"] = Field(
        description="'gallery' for the photo gallery, 'amenities' for the amenities photos."
    )
    index: int | None = Field(default=None, description="Which photo, 1 for the first.")
    fullscreen: bool = Field(
        default=False,
        description="True to open the photos full screen, one at a time ('en grande', "
        "'pantalla completa', 'full screen'). The amenities always open full screen.",
    )


class StepRequest(BaseModel):
    back: bool = Field(default=False, description="True for the previous photo.")


class SlideshowRequest(BaseModel):
    play: bool = Field(default=True, description="True to start the slideshow, false to stop it.")
    which: Literal["gallery", "amenities"] | None = Field(
        default=None, description="Whose photos: the gallery's unless they asked for amenities."
    )
    seconds: int | None = Field(
        default=None, description="Seconds per photo, 3 to 15; leave out for five."
    )


class PlanRequest(BaseModel):
    typology: str | None = Field(
        default=None,
        description="The typology whose plan to open, as the page labels it ('2D | 2B'); "
        "leave out for the one selected.",
    )


class LeadRequest(BaseModel):
    """Only what the visitor told you, in this turn or before; leave out the rest."""

    firstname: str | None = Field(default=None, description="Nombre.")
    lastname: str | None = Field(default=None, description="Apellidos.")
    rut: str | None = Field(default=None, description="RUT, e.g. '12.345.678-5'.")
    email: str | None = Field(default=None, description="Email, written out: 'ana@gmail.com'.")
    phone: str | None = Field(default=None, description="Celular, digits as said.")
    motivo: str | None = Field(default=None, description="'Invertir' or 'Habitar'.")
    tipologia: str | None = Field(
        default=None, description="Step two: the exact option the form lists, e.g. '2 dormitorios'."
    )
    ingreso: str | None = Field(
        default=None,
        description="Step two: ingreso líquido mensual, the exact option the form lists, or "
        "the amount in pesos they said ('1500000').",
    )
    pie: str | None = Field(
        default=None,
        description="Step two: ahorro para el pie, the exact option the form lists, or the "
        "amount in pesos they said.",
    )
    next_step: bool = Field(
        default=False,
        description="True once step one (name to motivo) is complete and confirmed: presses "
        "'Siguiente'.",
    )


class TabRequest(BaseModel):
    tab_id: str = Field(description="The tab_id from the open tabs list.")


class LanguageRequest(BaseModel):
    language: Lang = Field(description="'en' for English, 'es' for Spanish.")


# ─── The prompt ────────────────────────────────────────────────────────────────

_SITE_MAP_CHARS = 9000


def _site_map(k: Knowledge) -> str:
    lines: list[str] = []
    size = 0
    for p in k.pages.values():
        if p.kind == "quote":
            continue
        if p.kind == "project":
            keys = ", ".join(p.keys)
            line = f"- {site_path(p.path)} — {p.title} (sections: {keys})"
        else:
            heads = "; ".join(p.headings[:10])
            line = f"- {site_path(p.path)} — {p.title}" + (f" (headings: {heads})" if heads else "")
        size += len(line) + 1
        if size > _SITE_MAP_CHARS:
            break
        lines.append(line)
    return "\n".join(lines) or "(The site map is not loaded: find pages with search_site.)"


def _topics(k: Knowledge) -> str:
    return "\n".join(f"- {t.id}: {t.title}" for t in k.topics.values()) or "(none loaded)"


def _prompt(k: Knowledge) -> str:
    return f"""You are {AGENT_NAME}, the guide on ssilva.cl, the website of SSILVA Gestión Inmobiliaria ("Ssilva"), which sells new apartments, houses and offices in Chile. A visitor is browsing the site right now and has called you from the corner of the page. You can see and move their screen: you open project pages, scroll to the part that answers them and ring it, select a typology, filter the project list, open the gallery or the virtual tour, and fill in the quote form with them. You are warm, calm and sharp — the best sales advisor in the office, who knows every project, explains buying in Chile in plain words, and helps the visitor find the one that fits their life and budget.

# You narrate, and the screen follows your words
Like an advisor sitting beside the visitor with their screen between you: as you talk about something, it is on their screen, ringed, at that moment.
- Put a screen cue at the start of the sentence it belongs to. The page moves when your voice reaches that sentence. The visitor never hears a cue.
  - {{page: /path/}} opens a page of the site, at its top. Every page opens in full, so say what is coming while it loads.
  - {{show: name}} scrolls to a part of the page they are on, or are taken to by a page cue, and rings it. On a project page use the section names: galería, tipologías, amenidades, tour, estado, brochure, contacto (address, hours, phone and map), formulario (the quote form). On other pages use a heading exactly as the site pages list or the screen lines spell it. Words that are not a heading ring those words instead: "{{show: Desde 13.976 UF}}".
  - {{plan: 2D | 2B}} selects that typology on a project page, with its price, floor plan and areas, exactly as the page labels it.
  - On the project list, {{show: Distrito Barroso}} rings that project's card, going to the page of the list it is on. When you talk through several projects, put one before each sentence about one of them, so each card lights up as you say its name.
  - {{photo: 3}} opens the gallery's third photo full screen; {{photo: amenidades 2}} the second amenities photo. To show photos one at a time, put one before each sentence about a photo.
- One cue per sentence at most, before the sentence, and only where the screen should change.
- When the visitor asks where something is ("muéstrame", "show me", "where is"), your reply starts with the cue for exactly that thing.
- Cues are the only way you open a page or a section. Nothing waits on a cue.
- Cues are the site's own Spanish words, in an English reply too.

# The story of a purchase
Follow the buyer's story, one step per turn, from wherever they are:
1. What they are looking for: to live in, to invest, or a second home; which area; how many bedrooms; a budget in UF. Ask only what changes what you show, one question at a time, with choices: "¿Lo buscas para vivir o para invertir?" "¿Santiago o la costa?"
2. The projects that fit: find_projects, then say the two or three best in a sentence each, and show them: show_projects to ring them on the list, or a page cue to open the one they pick.
3. One project, top to bottom, with a cue per sentence: what and where it is and its "desde" price, the description, the galería, the tipologías one by one with {{plan: …}} and each one's price and size, the amenidades, the tour if there is one, the estado, and the contacto with the sales office's hours.
4. The quote: offer the form ("¿Quieres que te ayude a cotizar?"), then fill it in with them.
- End each turn with one short yes-or-no offer of the next step, or a choice of two: "¿Te muestro las tipologías?" "¿Seguimos con las amenidades o vamos a cotizar?" Never an open question, never "¿algo más?".
- When they say yes, go there in that reply, with cues. When they pick something else, follow them.

# How you sound
You are heard, not read, so keep it light and warm.
- A turn is three to five short sentences. Walking a page top to bottom can run to eight, one part per sentence, each with its cue.
- Every sentence under fifteen words. Small, everyday words. One idea per sentence. One number per sentence.
- THE FIRST SENTENCE IS A FEW WORDS. The visitor hears nothing until your first sentence is voiced, so open every reply with a sentence of two to six words that ends in a full stop, with the answer in it. A cue may come before it.
- Before most replies the visitor has already heard a short acknowledgement of mine ("Claro.", "A ver.", "Happy to help.", "Let me see."), so never open with one: your first word is the answer. No "buena pregunta", no repeating their question back.
- Spoken words only, apart from cues: no lists, no markdown, no symbols, never an exclamation mark.
- Talk about what is on their screen, never about how the page works: never "the filter", "the list cleared", "the page did not highlight", "the cue". If something did not show, show it again another way, or open the project.
- Write every number as spoken words. A price in UF: "tres mil trescientas setenta y cinco UF", "three thousand three hundred seventy-five UF", never "3.375 UF". Pesos: "un millón quinientos mil pesos". A typology: "dos dormitorios y dos baños", "two bedrooms and two bathrooms", never "2D | 2B". Areas: "noventa y nueve metros cuadrados". Phone numbers digit by digit, in pairs.
- Lines in square brackets come from their screen, not the visitor. Never read them out; use them.
- Always answer. A reply with no words leaves the visitor in silence.

# Spanish or English
You speak Spanish as a native of Latin America, and English. The call starts in Spanish.
- Answer in the language the visitor speaks to you. If they speak English, answer in English from that reply on; if they go back to Spanish, so do you. Your voice follows the language you write.
- Except when they chose a language: a line in square brackets says so. Then answer in that language whatever they speak, until they ask you to switch.
- When they ask for the other language in words that are not already it ("¿Puedes hablar en inglés?", "Can you speak Spanish?"), answer in that language and call set_language in the same response. A visitor already speaking English to you has been switched: do not call it for them.
- One language per reply. In Spanish, masculine forms of yourself ("estoy encantado de ayudarte").
- Your Spanish is neutral Latin American Spanish, understood from Mexico to Chile, never the Spanish of Spain, and without Chilean slang.
  - Address one visitor as "tú"; several people are "ustedes", never "vosotros", and never its verb forms ("queréis", "tenéis", "podéis") or "os".
  - Use Latin American words: "departamento", never "piso"; "celular", never "móvil"; "computadora", never "ordenador"; "agendar una visita", not "reservar una cita"; "mostrar" ("te muestro"), not "enseñar"; "completar el formulario", not "rellenar"; "¿Qué día te queda bien?", not "te viene bien"; "disculpa", not "perdona"; "está bien" or "perfecto", never "vale"; "tomar", never "coger"; "video", never "vídeo".
  - For something just done, use the simple past: "Abrí la página", "Ya lo completé", not "He abierto" or "Ya lo he rellenado".
  - Chilean real-estate words are right here, and you use them: UF, pie, cuotas, comuna, RUT, crédito hipotecario, sala de ventas, piloto, entrega inmediata.
- In English, the page is still in Spanish: describe it in English, and explain a local term the first time it comes up, briefly: "UF, the inflation-indexed unit Chilean prices use", "the pie, the down payment", "en blanco, sold before construction starts", "two bedrooms and two bathrooms, which the page writes 2D, 2B". The cues stay in Spanish.

# Every response starts with words
Write your answer, with its cues, first; any action call comes at the end of the same response. What an action returns reaches you only on your next turn.
- The exception is a read: find_projects, read_project, read_topic and search_site come back to you within this turn, but each one makes the visitor wait. Answer from the roster and the site pages below whenever they cover it. Read only for what is not here — a project's typologies, unit prices, amenities, address, hours or phone — and then call the read first, with nothing written before it.
- Never promise more to come ("déjame buscar", "let me check"): nothing comes after it.

# What you know
- Every fact — a price, a typology, a size, a status, an address, hours, a phone, a payment offer — comes from the knowledge below, a project or guide you read, or what the screen reported. Never from memory. If you cannot find it, say so, and offer the project's sales executive on WhatsApp or by phone.
- The roster's prices are the list's "desde". On a project page the screen line gives the hero's price and the selected typology's price: quote the page in front.
- You do not give financial advice or promise a mortgage, a rate or a subsidy. You explain what the site says and offer the executive.
- Guides you can read with read_topic:
{_topics(k)}
- read_project gives one project's every fact: address, typologies with their unit prices and sizes, amenities, status, sections, hours, phone, email.
- find_projects filters the whole list by comuna, region, tipo, dormitorios, budget, estado and perfil. The list on the site cannot filter by price, bedrooms or status: you do it.

# Moving the screen
- Open a project with its page cue from the roster: {{page: /estocolmo/}}. Cue only paths from the roster or the site pages list.
- show_projects opens /proyectos/ filtered and rings the projects you name: use it to show the visitor several projects at once. Pass region, property and one comuna as the visitor asked (the list filters one comuna at a time), and highlight the projects you are about to talk about. A comuna on the coast has no filter: its projects are rung instead. It opens the list itself: never write a page cue in a reply that calls it. Put {{show: name}} before each sentence about one of the projects, so its card is rung as you say it.
- Photos: show_photos moves the gallery, or with fullscreen opens it full screen ("en grande", "pantalla completa", "full screen"); the amenities always open full screen. step_photo shows the next photo, or the previous one. slideshow runs the photos by themselves, one every few seconds, when they ask for a presentation or a slideshow; it stops when they speak, or with play false. While it runs, do not describe the photos one by one: they change on their own; say it is running and that they can say stop. The screen lines say what each photo shows, from the site's own file names: say it in a few words ("el cowork", "la piscina"), never a file name, and never invent what is not named.
- Floor plans: show_floor_plan opens a typology's floor plan full screen, at once: say it is on their screen, never offer to open it again. When they ask to see a plan ("el plano", "la planta", "the floor plan", "más grande"), write {{plan: …}} before the sentence about it and call show_floor_plan with that typology. On a cotizar page it shows the unit's plan and where it sits on the floor.
- open_tour opens the virtual tour where the project has one; close_overlay closes the full-screen photos, the plan or the tour.
- The visitor can ask you to scroll to or press anything. Do it with a cue, and say what is now on their screen. Never say you cannot scroll or click.
- open_whatsapp opens a chat with the project's sales executive in a new tab: only when they ask for it, or say yes to your offer.
- Several ssilva.cl tabs may be open: lines in brackets list them. "Go back to the other tab" is switch_tab.
- Leave the owners' portal (Portal propietario) alone.

# The quote form
Every project page with typologies has a quote form beside them ({{show: formulario}}). It has two steps: step one asks Nombre, Apellidos, N° de Rut, email, celular and the motivo (Invertir or Habitar); step two asks the tipología, the ingreso líquido mensual and the ahorro para el pie, as ranges.
- When they want a quote, a price for a unit, or to be contacted about a project: open that project's page and {{show: formulario}}, say you will fill it in together, and ask for their name. On the cotizar page, or another page, open the project page first.
- Collect it as a conversation, two or three fields a turn: name and apellidos; then RUT and email; then celular and whether it is to live in or to invest. Call fill_lead_form with what they said each time; what is filled stays, and you only add.
- Read the email back in words ("ana punto pérez arroba gmail punto com"), and spell the RUT back digit by digit with its verification digit. Correct what they correct.
- When step one is complete and confirmed, call fill_lead_form with next_step true. The form then reports the options of step two: offer those exact options, and map what they say to the nearest one ("un millón y medio" is "Entre $1.500.000 a $1.800.000") and confirm it with them.
- The visitor presses "Enviar" themselves, always. When everything is filled, tell them to check their details and press "Enviar". Never say it is sent until the screen says they pressed it; if the screen says this preview held it back, say so plainly: nothing was sent to Ssilva.
- A visitor without a RUT (from abroad): offer the project's WhatsApp or phone instead.
- Never ask for data the form does not ask for.

# What that sounds like
Visitor: "Busco un departamento de dos dormitorios en Viña."
You (after find_projects): "Hay cuatro en Viña del Mar. {{show: Isla Picton}} Isla Picton parte en dos mil trescientas setenta y dos UF, y está en blanco. {{show: Vistamar}} Vistamar parte en dos mil seiscientas cincuenta y ocho UF. Mira al Mar y Canal Beagle tienen entrega inmediata. ¿Lo buscas para vivir o para invertir?" then show_projects with region valparaiso and those four in highlight.
Visitor: "Para vivir. Muéstrame Canal Beagle."
You: "{{page: /canalbeagle/}} Te abro Canal Beagle. Está en Isla Melinka doscientos veinte, en Viña del Mar. {{show: Desde 3.654 UF}} Parte en tres mil seiscientas cincuenta y cuatro UF. {{show: tipologías}} Tiene departamentos de dos y tres dormitorios. {{show: amenidades}} Arriba hay una terraza panorámica y un lounge bar. ¿Te muestro la tipología de dos dormitorios?"
Visitor: "Sí."
You: "{{plan: 2D | 2B}} Este es el de dos dormitorios y dos baños. A la izquierda ves la planta. Las unidades de esta tipología parten en cuatro mil quinientas veintitrés UF. ¿Quieres que te ayude a cotizarlo?"
Visitor: "Muéstrame el plano en grande."
You: "{{plan: 2D | 2B}} Aquí tienes la planta en pantalla completa. Los dos dormitorios quedan a cada lado del living. ¿Seguimos con las amenidades?" then show_floor_plan with typology 2D | 2B.
Visitor: "¿Y las fotos?"
You: "Te las muestro en grande. {{photo: 1}} Aquí ves el departamento piloto. {{photo: 2}} Y este es el cowork del edificio. ¿Te pongo una presentación con el resto?"
Visitor: "Sí, dale."
You: "Perfecto, van pasando solas. Dime cuando quieras parar." then slideshow with play true.
Visitor: "Quiero cotizar."
You: "{{show: formulario}} Perfecto, lo completamos juntos. ¿Me dices tu nombre y apellidos?"
Visitor: "Ana Pérez Soto."
You: "Gracias, Ana. ¿Me dices tu RUT y tu correo?" then fill_lead_form with firstname Ana, lastname Pérez Soto.
Visitor: "doce millones trescientos cuarenta y cinco mil seiscientos setenta y ocho guion cinco, ana.perez@gmail.com"
You: "Anoté el RUT uno, dos, tres, cuatro, cinco, seis, siete, ocho, guion cinco. Y el correo ana punto pérez arroba gmail punto com. ¿Está bien?" then fill_lead_form with rut 12.345.678-5 and email ana.perez@gmail.com.

Visitor: "Show me projects in Las Condes."
You (after find_projects): "There are three in Las Condes. Estocolmo has large two and three bedroom apartments, from thirteen thousand nine hundred seventy-six UF. That's the UF, the inflation-indexed unit Chilean prices use. Los Navegantes has three bedrooms, and Apoquindo Moro is offices. Is it to live in, or to invest?" then show_projects with region metropolitana, communes Las Condes and those three in highlight.
Visitor: "To live. Tell me about Estocolmo."
You: "{{page: /estocolmo/}} Opening Estocolmo now. It faces Parque Juan Pablo the Second, in Las Condes. {{show: galería}} Here are the photos. {{show: tipologías}} It has two layouts. {{plan: 2D | 3B}} This one is two bedrooms and three bathrooms. Shall I show you the amenities, or the three bedroom layout?"

Visitor: "¿Qué es la UF?"
You: "Es la unidad en que se cotiza en Chile. Su valor en pesos se ajusta cada día con la inflación. Por eso los precios no cambian en UF. En oportunidades hay una calculadora de UF. ¿Te la muestro?"

# Ssilva
{k.l1}

# Site pages
{_site_map(k)}
"""


# ─── Greeting ──────────────────────────────────────────────────────────────────

_INTRO: dict[Lang, str] = {
    "en": f"Hi, I'm {AGENT_NAME}, your guide on Ssilva.",
    "es": f"Hola, soy {AGENT_NAME}, tu guía en Ssilva.",
}
_GREETING: dict[Lang, str] = {
    "en": "I can show you the projects, or take you straight to what you need. "
    "What are you looking for?",
    "es": "Puedo mostrarte los proyectos, o llevarte directo a lo que necesitas. "
    "¿Qué estás buscando?",
}
#: The opener's second sentence for the kind of page the call starts on.
_OPENERS: dict[str, dict[Lang, str]] = {
    "home": {
        "en": "I'll help you find your new home. Is it to live in, to invest, or a second home?",
        "es": "Te ayudo a encontrar tu departamento. ¿Lo buscas para vivir, para invertir "
        "o como segunda vivienda?",
    },
    "projects": {
        "en": "Tell me the area and how many bedrooms you need, and I'll show you what fits.",
        "es": "Dime qué comuna y cuántos dormitorios buscas, y te muestro los proyectos "
        "que encajan.",
    },
    "quote": {
        "en": "I can help you get a quote. Shall we start with the layout you like?",
        "es": "Te ayudo a cotizar. ¿Partimos por la tipología que te interesa?",
    },
    "invest": {
        "en": "I can tell you how investing with Ssilva works. Shall I walk you through it?",
        "es": "Te cuento cómo es invertir con Ssilva. ¿Te lo muestro paso a paso?",
    },
}
_PROJECT_OPENER: dict[Lang, str] = {
    "en": "You're looking at {name}, from {price}. Shall I walk you through it, "
    "or go straight to the layouts?",
    "es": "Estás viendo {name}, desde {price}. ¿Te lo muestro de arriba abajo, "
    "o vamos directo a las tipologías?",
}
_PROJECT_OPENER_NO_PRICE: dict[Lang, str] = {
    "en": "You're looking at {name}. Shall I walk you through it?",
    "es": "Estás viendo {name}. ¿Te lo muestro de arriba abajo?",
}


def page_kind(path: str, k: Knowledge) -> str:
    """``home``, ``projects``, ``project``, ``quote``, ``invest`` or ``page``."""
    here = canonical_path(path)
    page = k.page(here)
    if here == "/":
        return "home"
    if here.startswith("/proyectos/cotizar"):
        return "quote"
    if here in ("/proyectos", "/oportunidades"):
        return "projects"
    if here == "/centro-de-negocios":
        return "invest"
    if page is not None and page.kind == "project":
        return "project"
    return "page"


def greeting(path: str | None, k: Knowledge, lang: Lang = OPENING) -> str:
    """The written opener, in ``lang``, tailored to the page the call starts on."""
    here = path or "/"
    kind = page_kind(here, k)
    if kind == "project" and (p := k.project_at(here)) is not None:
        if p.desde_uf:
            line = _PROJECT_OPENER[lang].format(name=p.name, price=uf_words(p.desde_uf, lang))
        else:
            line = _PROJECT_OPENER_NO_PRICE[lang].format(name=p.name)
        return f"{_INTRO[lang]} {line}"
    line = _OPENERS.get(kind, {}).get(lang) or _GREETING[lang]
    return f"{_INTRO[lang]} {line}"


# ─── Written lines for moves ───────────────────────────────────────────────────

#: His line for a silent turn, by what moved: "shown" for anything else.
_LANDED: dict[str, dict[Lang, str]] = {
    "shown": {"en": "Here it is.", "es": "Aquí lo tienes."},
    "list": {
        "en": "Here are the projects on the list.",
        "es": "Aquí tienes los proyectos en la lista.",
    },
    "photos": {"en": "Here are the photos.", "es": "Aquí tienes las fotos."},
    "photo": {"en": "Here's the next one.", "es": "Aquí va la siguiente."},
    "slideshow": {
        "en": "The photos will go by on their own.",
        "es": "Las fotos van pasando solas.",
    },
    "stopped": {"en": "I've stopped it here.", "es": "La dejé aquí."},
    "plan": {"en": "Here's the floor plan, full screen.", "es": "Aquí tienes el plano en grande."},
    "tour": {"en": "The tour is open.", "es": "Abrí el recorrido virtual."},
    "closed": {"en": "I've closed it.", "es": "Listo, lo cerré."},
    "form": {"en": "I've filled that in on the form.", "es": "Ya lo completé en el formulario."},
    "whatsapp": {
        "en": "I've opened WhatsApp in a new tab.",
        "es": "Abrí WhatsApp en una pestaña nueva.",
    },
    "tab": {"en": "There's that tab.", "es": "Ahí tienes esa pestaña."},
}

#: What a reply that only promises more says: nothing comes after it.
_PROMISE = re.compile(
    r"\b(?:just |one |un )?(?:moment|momento|momentito|second|segundo)\b"
    r"|\blet me (?:see|check|look)(?: (?:that|into it|at that))?\b|\bdéjame ver\b|\ba ver\b",
    re.IGNORECASE,
)

# ─── His nod ───────────────────────────────────────────────────────────────────

#: His nods, the holding line and the apology — chosen by measurement, not by
#: ear. Each line is voiced on its own, and always the same way, so a line
#: either sounds like him in every call or like somebody else in every call:
#: on dev, "Right." came out at 82 Hz and "One moment." / "Un momento." at
#: 166 Hz against his 110-132 Hz, and a speaker model put "Certainly.",
#: "Okay.", "Right." and "Un momentito." well outside his voice (the owner
#: heard it on Explora, 2026-10-22). Every line here measured within his own spread, with
#: its pitch within 2.5 semitones of his. Measure a line before adding it; the
#: measurements hold for his voice as it is today.
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
ACK_RATE = 0.75
ACK_HOLD_AFTER_S = 4.0
_ACK_HOLD: dict[Lang, tuple[str, ...]] = {
    "en": ("Just a moment.", "One moment while I check that for you."),
    "es": ("Dame un momento mientras lo busco.", "Un momento mientras lo reviso para ti."),
}
_ACK_SORRY: dict[Lang, str] = {
    "en": "Sorry, that's taking a little longer.",
    "es": "Lo siento, está tardando un poco más de lo normal.",
}
#: A visitor's ordinary words about buying a home here, so the reading trusts them.
_ACK_WORDS = Vocabulary(
    common=frozenset(
        # A word list reads as words, so it stays a split string.
        """ssilva proyecto proyectos departamento departamentos depto casa oficina dormitorios
        dormitorio baños uf pie cuotas comuna santiago viña las condes vitacura reñaca
        cotizar cotización tipología tipologías piscina precio apartment apartments project
        projects bedroom bedrooms bathroom budget quote invest rut
        """.split()  # noqa: SIM905
    ),
)


def _avatar_state(session: Session, state: Literal["WORKING"] | None) -> None:
    """The talking head's working latch: held until speech owed has played."""
    session.send_rtvi(RTVIType.SERVER_MESSAGE, {"type": "avatar", "cmd": "state", "state": state})


_HEADINGS_IN_NOTE = 30
_SEARCH_HITS = 6
_FOUND_SHOWN = 8


async def _silence() -> AsyncGenerator[Any, None]:
    for _ in ():
        yield


def _clip(items: list[str] | tuple[str, ...], most: int) -> str:
    more = f"; and {len(items) - most} more" if len(items) > most else ""
    return "; ".join(items[:most]) + more


def _match(want: str, options: list[str] | tuple[str, ...]) -> str | None:
    """The option ``want`` names: the same words, else the one it begins, else
    the one it is inside — how the page itself matches. Punctuation and accents
    do not count: "2 dormitorios" is "2 Dormitorios"."""

    def folded(s: str) -> str:
        return " ".join(re.sub(r"[^\w\s]", " ", fold(s)).split())

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


# ─── What the visitor asked about ──────────────────────────────────────────────

#: The page for what the visitor asked about, when his reply forgets to open it
#: (SendPotion's dev call 60e6c24b: told about a page twice, screen unmoved).
#: Matched on their own words.
_ASKED_PAGES: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(rf"\b(?:{w})", re.IGNORECASE), path)
    for w, path in (
        (r"centro de negocios|business cent", "/centro-de-negocios"),
        (r"oportunidades|opportunities|calculadora de uf|uf calculator", "/oportunidades"),
        (
            r"sobre ssilva|sobre nosotros|qui[eé]nes son|about ssilva|about (?:the )?company|"
            r"who (?:are|is) ssilva",
            "/sobre-nosotros",
        ),
        (r"vender (?:un |mi )?terreno|sell (?:my |a )?(?:land|plot)", "/vende-tu-terreno"),
        (r"centro de ayuda|help cent", "/ayuda-llamanos"),
    )
)
_ASKED_TAB = re.compile(r"\b(?:tabs?|pestañas?)\b", re.IGNORECASE)

# A request about the call's own language: a verb of speaking, addressed to him,
# and the language. "¿Hablan inglés en la sala de ventas?" is about the project.
_CALL_LANGUAGE = re.compile(
    r"\b(?:speak|talk|switch|change|continue|carry on|answer|reply|respond|go back|"
    r"habl\w*|cambi\w*|sig\w*|continu\w*|respond\w*|contest\w*|pas\w*|volv\w*)\b"
    r"[^.?!]{0,25}?\b(?:spanish|english|español|espanol|castellano|inglés|ingles)\b",
    re.IGNORECASE,
)
_TO_HIM = re.compile(
    r"^\W*(?:(?:hey|ok|okay|please|so|now|oye|bueno|por favor)\W+)*"
    r"(?:speak|talk|switch|change|continue|carry|answer|reply|respond|go|habla|háblame|"
    r"hábleme|cambia|sigue|continúa|responde|contesta|pasa|vuelve)\b"
    r"|\b(?:you|we|us|let'?s|let us|i|i'?ll|puedes|podemos|podrías|podríamos|hablemos|"
    r"sigamos|cambiemos|continuemos|pasemos|volvamos|me|nos|hablamos|seguimos|cambiamos|"
    r"continuamos|pasamos|volvemos|puedo)\b",
    re.IGNORECASE,
)


def asks_call_language(text: str) -> bool:
    """Whether ``text`` asks him to speak another language — a request about
    this call, not a question about the projects."""
    return bool(_CALL_LANGUAGE.search(text) and _TO_HIM.search(text))


def named_projects(text: str, k: Knowledge) -> list[Project]:
    """The projects ``text`` names outright, by a distinctive part of their name."""
    said = f" {' '.join(re.findall(r'[a-z0-9]+', fold(text)))} "
    found: list[Project] = []
    for p in k.projects.values():
        if not p.path:
            continue
        if any(f" {alias} " in said for alias in _aliases(p)):
            found.append(p)
    # "Distrito Barroso" is not also "Locales comerciales Distrito Barroso".
    return [p for p in found if not any(q is not p and _aliases(p) < _aliases(q) for q in found)]


#: Words of a name too common to stand for the project alone.
_WEAK = frozenset(
    [
        "edificio",
        "parque",
        "el",
        "la",
        "los",
        "las",
        "de",
        "del",
        "oficinas",
        "mira",
        "vista",
        "mar",
        "al",
        "playa",
        "limit",
        "carrera",
        "rodeo",
        "poza",
        "golf",
        "lagunamar",
        "isla",
        "canal",
        "aires",
        "distrito",
        "santa",
        "locales",
        "comerciales",
        "condominio",
        "mirador",
    ]
)


def _aliases(p: Project) -> frozenset[str]:
    name = " ".join(re.findall(r"[a-z0-9]+", fold(p.name)))
    out = {name}
    parts = name.split()
    # Without "edificio", "parque el", "oficinas": "Uniq", "Millalongo 72".
    core = [w for w in parts if w not in ("edificio", "oficinas", "parque", "el", "condominio")]
    if core:
        out.add(" ".join(core))
    strong = [w for w in core if w not in _WEAK and len(w) > 3 and not w.isdigit()]
    if len(strong) == 1:
        out.add(strong[0])
    return frozenset(out)


def asked_page(text: str, k: Knowledge) -> str | None:
    """The page for what ``text`` asks about, or ``None``: one project named
    outright, or one of the site's own pages. "The other tab" is a tab, and
    "¿puedes hablar en inglés?" is about the call, not a page."""
    if _ASKED_TAB.search(text) or asks_call_language(text):
        return None
    projects = named_projects(text, k)
    if len(projects) == 1:
        return canonical_path(projects[0].path)
    if projects:
        return None  # A comparison: not one page.
    named = [(m.start(), path) for rx, path in _ASKED_PAGES if (m := rx.search(text))]
    return min(named)[1] if named else None


# ─── The part of the page a sentence describes ─────────────────────────────────

#: A project page's sections, by the words a sentence about each one uses.
_SECTION_WORDS: dict[str, tuple[str, ...]] = {
    "galería": ("galeria", "fotos", "foto", "imagenes", "gallery", "photos", "pictures"),
    "tipologías": (
        "tipologia",
        "tipologias",
        "planta",
        "plantas",
        "plano",
        "planos",
        "floor plan",
        "floor plans",
        "layouts",
        "layout",
    ),
    "amenidades": (
        "amenidades",
        "amenities",
        "piscina",
        "piscinas",
        "pool",
        "gimnasio",
        "gym",
        "quincho",
        "quinchos",
        "cowork",
        "equipamiento",
        "lounge",
        "sala gourmet",
        "zona gourmet",
        "club house",
        "senderos",
    ),
    "tour": ("tour", "recorrido virtual", "virtual tour", "recorrer los espacios"),
    "estado": (
        "estado del proyecto",
        "estado de la obra",
        "obra gruesa",
        "termino de obra",
        "under construction",
        "construction stage",
        "en construccion",
        "barra de estado",
    ),
    "contacto": (
        "direccion",
        "address",
        "horario",
        "horarios",
        "opening hours",
        "sala de ventas",
        "sales office",
        "telefono",
        "phone number",
        "mapa",
        "map",
        "ubicacion",
        "location",
    ),
    "formulario": ("formulario", "the form", "quote form", "cotizacion"),
    "brochure": ("brochure", "folleto"),
}
_NUMBER_WORDS = {
    "uno": 1,
    "un": 1,
    "una": 1,
    "one": 1,
    "dos": 2,
    "two": 2,
    "tres": 3,
    "three": 3,
    "cuatro": 4,
    "four": 4,
}
_COUNT = r"(\d|uno|un|una|one|dos|two|tres|three|cuatro|four)"
_BEDS = re.compile(rf"\b{_COUNT}\s+(?:dormitorios?|dorms?|bedrooms?|bed)\b")
_BATHS = re.compile(rf"\b{_COUNT}\s+(?:banos?|bathrooms?|baths?)\b")
_LABEL = re.compile(r"\b(\d)\s*d\s*\|?\s*(\d)\s*b\b")
#: "dos y tres dormitorios", "one, two and three bedrooms": several, so none.
_SEVERAL_BEDS = re.compile(
    rf"\b{_COUNT}\s*(?:,|y|o|and|or)\s*(?:de\s+|the\s+)?{_COUNT}\s+(?:dormitorios?|dorms?|bedrooms?)\b"
)


def _count(word: str) -> int:
    return int(word) if word.isdigit() else _NUMBER_WORDS.get(word, -1)


#: The words a label adds to its bedrooms and bathrooms ("2D | 2B MARIPOSA"),
#: as a sentence says them, in either language.
_LABEL_EXTRAS: dict[str, tuple[str, ...]] = {
    "mariposa": ("mariposa", "butterfly"),
    "penthouse": ("penthouse",),
    "loft": ("loft",),
    "suite": ("suite",),
    "estar": ("estar", "living"),
}


def _plain(label: str) -> bool:
    """A label that is only bedrooms and bathrooms: "2D | 2B"."""
    return re.fullmatch(r"\d+d\d+b", typology_key(label)) is not None


def typology_in(sentence: str, typologies: tuple[str, ...] | list[str]) -> str | None:
    """The one typology of ``typologies`` that ``sentence`` is about: by its
    label ("2D | 2B"), by bedrooms and bathrooms said in words ("two-bedroom"
    too), by a word only its label has ("butterfly", "mariposa"), or by its
    bedrooms alone when only one typology has that many. ``None`` unless one."""
    if not typologies or sentence.rstrip().endswith("?"):
        return None
    # "two-bedroom, one-bathroom" is two bedrooms and one bathroom.
    f = fold(sentence).replace("-", " ")
    extras = [
        k for k, said in _LABEL_EXTRAS.items() if any(re.search(rf"\b{w}\b", f) for w in said)
    ]

    def one(fitting: list[str]) -> str | None:
        if extras:
            fitting = [t for t in fitting if any(k in typology_key(t) for k in extras)]
        elif len(fitting) > 1 and [t for t in fitting if _plain(t)]:
            # "Two bedrooms and two bathrooms" is the plain one, not its mariposa.
            fitting = [t for t in fitting if _plain(t)]
        return fitting[0] if len(fitting) == 1 else None

    if (m := _LABEL.search(f)) is not None:
        keyed = typology_key(f"{m.group(1)}D | {m.group(2)}B")
        return one([t for t in typologies if typology_key(t).startswith(keyed)])
    if re.search(r"\b(?:estudio|studio)\b", f):
        studios = [t for t in typologies if "estudio" in typology_key(t)]
        return studios[0] if len(studios) == 1 else None
    if _SEVERAL_BEDS.search(f):
        return None
    beds = {_count(m.group(1)) for m in _BEDS.finditer(f)}
    baths = {_count(m.group(1)) for m in _BATHS.finditer(f)}
    if not beds and not baths and extras:
        return one(list(typologies))
    if len(beds) != 1 or len(baths) > 1:
        return None
    n = next(iter(beds))
    fitting = [t for t in typologies if re.match(rf"^\s*{n}\s*d\b", fold(t))]
    if baths:
        b = next(iter(baths))
        fitting = [t for t in fitting if re.search(rf"\b{b}\s*b\b", fold(t))]
    return one(fitting)


def section_in(sentence: str, keys: tuple[str, ...] | list[str]) -> str | None:
    """The one project-page section of ``keys`` that ``sentence`` is about, by
    its words; ``None`` unless it is clearly one."""
    if sentence.rstrip().endswith("?"):
        return None  # The closing offer: about what comes next.
    said = f" {' '.join(re.findall(r'[a-z0-9]+', fold(sentence)))} "
    scored: list[tuple[int, str]] = []
    for key in keys:
        hits = sum(1 for w in _SECTION_WORDS.get(key, ()) if f" {w} " in said)
        if hits:
            scored.append((hits, key))
    scored.sort(reverse=True)
    if not scored or (len(scored) > 1 and scored[0][0] == scored[1][0]):
        return None
    return scored[0][1]


_STOP = frozenset(
    """a an the and or but of to in on for with by at from as is are was were be it its this
    that these those you your we our they their he she his her i me my can will just also so
    then here there what which who how when where why all any each more most some no not only
    de del la las el los un una unos unas y o en con por para que es son se su sus al lo le
    tu te mi muy mas ya como este esta estos estas ese esa aqui hay tiene tienen ssilva
    proyecto proyectos""".split()  # noqa: SIM905
)
#: How sure a match must be: its score, and its lead over the runner-up.
_SECTION_MIN = 6.0
_SECTION_LEAD = 1.5
_SECTION_MIN_WORDS = 4


def _terms(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", fold(text)) if len(w) > 2 and w not in _STOP]


def best_section(sentence: str, sections: list[tuple[str, str]]) -> str | None:
    """The heading of the one section ``sentence`` is about, of ``sections``
    (heading, text) on a page other than a project's; ``None`` unless it is
    clearly one."""
    if sentence.rstrip().endswith("?"):
        return None
    said = " ".join(re.findall(r"[a-z0-9]+", fold(sentence)))
    quoted = [
        h
        for h, _ in sections
        if h
        and len(phrase := re.findall(r"[a-z0-9]+", fold(h))) >= 2
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


#: What the visitor or the model may call a project page's section.
_SECTION_NAMES: dict[str, str] = {
    "galeria": "galería",
    "gallery": "galería",
    "fotos": "galería",
    "photos": "galería",
    "tipologias": "tipologías",
    "tipologia": "tipologías",
    "typologies": "tipologías",
    "layouts": "tipologías",
    "floor plans": "tipologías",
    "plantas": "tipologías",
    "amenidades": "amenidades",
    "amenities": "amenidades",
    "equipamiento": "amenidades",
    "tour": "tour",
    "virtual tour": "tour",
    "recorrido virtual": "tour",
    "estado": "estado",
    "status": "estado",
    "estado del proyecto": "estado",
    "brochure": "brochure",
    "folleto": "brochure",
    "contacto": "contacto",
    "contact": "contacto",
    "ubicacion": "contacto",
    "location": "contacto",
    "mapa": "contacto",
    "map": "contacto",
    "direccion": "contacto",
    "horario": "contacto",
    "formulario": "formulario",
    "form": "formulario",
    "quote form": "formulario",
    "cotizar": "formulario",
    "cotizacion": "formulario",
}


def section_key(value: str) -> str | None:
    """The canonical section ``value`` names, or ``None``."""
    return _SECTION_NAMES.get(fold(value).strip(" ."))


# ─── The quote form ────────────────────────────────────────────────────────────

LEAD_FIELDS = ("firstname", "lastname", "rut", "email", "phone", "motivo")
LEAD_STEP_TWO = ("tipologia", "ingreso", "pie")
_LEAD_NAMES = {
    "firstname": "nombre",
    "lastname": "apellidos",
    "rut": "RUT",
    "email": "email",
    "phone": "celular",
    "motivo": "motivo",
    "tipologia": "tipología",
    "ingreso": "ingreso líquido",
    "pie": "ahorro para el pie",
}
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.IGNORECASE)


def rut_is_valid(rut: str) -> bool:
    """A Chilean RUT's verification digit (módulo 11) checks out."""
    clean = re.sub(r"[^0-9kK]", "", rut).upper()
    if len(clean) < 2 or not clean[:-1].isdigit():
        return False
    body, dv = clean[:-1], clean[-1]
    total, factor = 0, 2
    for digit in reversed(body):
        total += int(digit) * factor
        factor = 2 if factor == 7 else factor + 1
    expected = 11 - total % 11
    want = "0" if expected == 11 else "K" if expected == 10 else str(expected)
    return dv == want


def format_rut(rut: str) -> str:
    """``123456785`` → ``12.345.678-5``."""
    clean = re.sub(r"[^0-9kK]", "", rut).upper()
    body, dv = clean[:-1], clean[-1:]
    return f"{int(body):,}".replace(",", ".") + f"-{dv}" if body.isdigit() else rut


def motivo_of(value: str) -> str | None:
    f = fold(value)
    if re.search(r"invert|invest|inversion|arrendar|rent", f):
        return "Invertir"
    if re.search(r"habit|vivir|live|home|hogar|familia|family|primera vivienda", f):
        return "Habitar"
    return None


def amount_of(text: str) -> float | None:
    """Pesos in ``text``: "1500000", "$1.500.000", "1,5 millones", "800 mil",
    "one and a half million". ``None`` when it names no amount."""
    f = fold(text).replace("$", " ")
    if re.search(r"\b(?:no tengo|nada|none|nothing|cero|zero)\b", f):
        return 0.0
    m = re.search(r"(\d+(?:[.,]\d+)*)\s*(millon(?:es)?|million|mill|mm|mil|thousand|k)?\b", f)
    if m is None:
        half = re.search(r"\b(?:un millon y medio|one and a half million|millon y medio)\b", f)
        if half:
            return 1_500_000.0
        word = re.search(
            r"\b(un|uno|one|dos|two|tres|three|cuatro|four|cinco|five)\s+(millon(?:es)?|million)", f
        )
        if word:
            n = {"un": 1, "uno": 1, "one": 1, "dos": 2, "two": 2, "tres": 3, "three": 3}
            n |= {"cuatro": 4, "four": 4, "cinco": 5, "five": 5}
            return n[word.group(1)] * 1_000_000.0 + (500_000.0 if "y medio" in f else 0.0)
        return None
    raw, unit = m.group(1), m.group(2) or ""
    if unit:
        number = (
            float(raw.replace(".", "").replace(",", "."))
            if raw.count(".") > 1
            else float(raw.replace(",", "."))
        )
        scale = 1_000_000 if unit.startswith(("mill", "mm")) else 1_000
        return number * scale
    return float(re.sub(r"[.,]", "", raw))


def _range_of(option: str) -> tuple[float, float] | None:
    """The pesos an option of the form covers: "Entre $1.000.000 a $1.200.000"."""
    f = fold(option)
    nums = [float(re.sub(r"\D", "", n)) for n in re.findall(r"\d[\d.]*", f)]
    if "no tengo" in f:
        return (0.0, 0.0)
    if not nums:
        return None
    if f.startswith("menos"):
        return (0.0, nums[0])
    if f.startswith("mas"):
        return (nums[0], math.inf)
    if len(nums) >= 2:
        return (nums[0], nums[1])
    return None


def option_for(value: str, options: list[str]) -> str | None:
    """The form's option for what the visitor said: the option itself, else the
    range their amount falls in."""
    if (hit := _match(value, options)) is not None:
        return hit
    amount = amount_of(value)
    if amount is None:
        return None
    for option in options:
        span = _range_of(option)
        if span is not None and (span[0] <= amount < span[1] or span[0] == span[1] == amount):
            return option
    # On a boundary the option ending there counts too: "1.200.000" is "Entre 1.000.000 a 1.200.000".
    for option in options:
        span = _range_of(option)
        if span is not None and span[1] == amount:
            return option
    return None


# ─── The brain ─────────────────────────────────────────────────────────────────


class SsilvaBrain(GeminiBrain):
    """One per session. Javier: Ssilva's projects, its pages, and a mirror of
    the visitor's tabs and quote form, in Spanish or English."""

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
        #: toggle's written confirmation of a switch, said at his next turn.
        self.spoken: Lang = OPENING
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
        #: Every open ssilva.cl tab, and which is in front.
        self.tabs: list[TabInfo] = []
        self._active = ""
        self._tabs_unseen = False
        #: The typology the page last showed, the list it last showed, the quote
        #: form as it last reported itself.
        self.typology: TypologyShown | None = None
        self.listed: ProjectsListed | None = None
        self.lead: LeadFormState | None = None
        #: What he has put on the form this call, and what he holds back until
        #: the form can take it (a project page; step two's options).
        self._lead_sent: dict[str, str] = {}
        self._lead_held: dict[str, str] = {}
        self._talk: str | None = None
        #: The page this turn's cues are on: the one in front, then wherever a
        #: ``{page: …}`` cue took it.
        self._cue_path = "/"
        self._idle_short = False
        self._nudges = 0
        #: The page for what the visitor last asked about, opened at the start
        #: of his reply if it has no cue of its own; see :func:`asked_page`.
        self._backstop: str | None = None
        #: This reply's moves so far, so a sentence on the same part does not
        #: ring it again.
        self._shown: str | None = None
        self._planned: str | None = None
        #: The card this reply last rang on the project list; the project
        #: cards he names before this reply's show_projects has opened the
        #: list, kept for it; and whether it has.
        self._carded: str | None = None
        self._cards: list[Cue] = []
        self._listing_turn = False
        #: The photo or plan on screen, as the page last reported it, and
        #: whether this reply put one full screen.
        self.photo: PhotoShown | None = None
        self._viewing = False

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        init = session.init or {}
        self._path = canonical_path(str(init.get("path") or init.get("url") or "/"))
        # The page sends `lang` only once the visitor has pressed the toggle.
        chosen = init.get("lang")
        self._chosen = chosen in LANGUAGE_NAMES
        self.spoken = "en" if chosen == "en" else OPENING
        await session.configure(
            Config(
                stt=SttConfig(language=self.spoken, patience=SSILVA_PATIENCE),
                tts=TtsConfig(voice=VOICE, language=self.spoken),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
            )
        )
        logger.info(
            "ssilva: session start on {} in {}{}",
            self._path,
            self.spoken,
            " (chosen)" if self._chosen else "",
        )
        if self._chosen:
            self._note(_chosen_note(self.spoken, "before the call"))

    async def greet(self, session: Session) -> str:
        """The opener, written not generated."""
        line = greeting(self._path, self.kb, self.spoken)
        return for_the_voice(line) if self.spoken == "es" else line

    async def on_finalize(self, session: Session, fin: Finalize) -> None:
        """What was heard goes into the model's context, "bidéo" spelled
        "video" again first."""
        if "idéo" in fin.heard:
            fin = dataclasses.replace(fin, heard=from_the_voice(fin.heard))
        await super().on_finalize(session, fin)

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[Speech, None]:
        """A visitor who speaks the other language is answered in it from the
        first word, unless they chose the language they are in; the page they
        moved to is read in with what they said; his nod covers the thinking."""
        heard = None if self._chosen else language_of(msg.text)
        if heard is not None and heard != self.spoken:
            await session.configure(self._speaking(heard))
            logger.info("ssilva: language -> {} (heard)", heard)
        self._talk = None
        self._nudges = 0
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
            logger.info("ssilva: ack {!r}", nod)
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

        A result the page produced after his turn (the form's second step, a
        press of Enviar) is in the context already and the idle window was
        shortened, so a reading visitor hears it from him here. Otherwise an
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
                "Speak into the quiet, briefly, as the advisor beside them would: one useful "
                "thing about what is on their screen, or one question that helps you find their "
                "project. Never ask whether they are still there, and never repeat your last line."
            )
        else:
            ask = (
                "Still quiet. One last, light offer, different from your last: a part of this "
                "project you could show, or the quote. Then let them browse."
            )
        self._note(f"{quiet} {ask}")
        return self.respond(session)

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The model's turn, with its screen cues taken out of the speech and
        sent to the page (:mod:`.cues`).

        A move with no words is asked once more with tools off; a turn with
        nothing at all, the same. A language switched on the toggle is
        confirmed first, in the new language. A unit is opened only once its
        first words are known, so the voice follows the language it is in."""
        if (line := self._confirm) is not None:
            self._confirm = None
            async for event in say_line(self, line):
                yield event
        self._cue_path = self._path
        self._shown = None
        self._planned = None
        self._carded = None
        self._cards = []
        self._listing_turn = False
        self._viewing = False
        said = ""
        turn = self._fallback.speak_if_silent(
            self, super().respond(session), again=lambda: self._talk_now(session)
        )
        async for event in self._spelled(self._written(session, self._cued(turn))):
            if isinstance(event, SpeechChunk):
                said += event.text
            yield event
        # Words, and not only a promise: on Explora's dev call ed9846d5 his
        # whole reply was "One moment.", and the visitor sat in silence.
        if not _PROMISE.sub("", _CUE_TEXT.sub(" ", said)).strip(" .,!?¡¿…"):
            logger.warning("ssilva: the model returned nothing; asking once more")
            again = self._written(session, self._cued(self._talk_now(session)))
            async for event in self._spelled(again):
                yield event
        if self._cards:
            # Cards named on a page with no list, and no list opened after.
            logger.info("ssilva: {} card cue(s) with no list to ring them on", len(self._cards))
            self._cards = []

    async def _written(
        self, session: Session, turn: AsyncGenerator[Speech, None]
    ) -> AsyncGenerator[Speech, None]:
        """``turn``, with each unit held back until its first sentence is in,
        and both legs moved to the language it is in when it is not the call's."""
        held: list[Speech] = []
        text = ""

        async def release() -> AsyncGenerator[Speech, None]:
            nonlocal held, text
            written = None if self._chosen else language_of(text, sure=False)
            if written is not None and written != self.spoken:
                await session.configure(self._speaking(written))
                logger.info("ssilva: language -> {} (written)", written)
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
        """``turn`` with every ``{page|show|plan: …}`` taken out of its text and
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
        if "{" in chunk or path == self._path:
            return chunk
        logger.info("ssilva: the reply has no cue; showing {} first", path)
        return f"{{page: {site_path(path)}}}{chunk}"

    def _send_cue(self, raw: RawCue) -> None:
        """Check a cue against the site, as the tools do, and send it; one that
        names nothing real is dropped and logged rather than reaching the page."""
        if self.spoken == "es" and raw.at:
            raw = dataclasses.replace(raw, at=_anchor_for_voice(raw.at))
        cue = self._resolve_cue(raw)
        logger.info("ssilva: cue {} {!r} at {!r} -> {}", raw.kind, raw.value, raw.at, cue)
        if cue is None:
            return
        if cue.card is not None:
            self._carded = canonical_path(cue.card)
            if not self._on_a_list():
                # The list this reply is about opens with its show_projects,
                # which the model calls after its words: kept until then.
                self._cards.append(cue)
                return
        elif raw.kind == "show":
            self._shown = cue.heading or cue.text
        elif raw.kind == "plan":
            self._planned = cue.typology
            self._shown = "tipologías"
        self.session.dispatch(cue)

    def _auto_cues(
        self, sentence: str, index: int, placed: tuple[tuple[CueKind, str], ...]
    ) -> list[tuple[CueKind, str]]:
        """The move a sentence of his needs and did not bring (see :mod:`.cues`):
        on a project page, the typology or the section it describes; on another
        page, the section. Never a page: that is the visitor's backstop's."""
        kinds = {k for k, _ in placed}
        # A page the model opens on this very sentence is not sent yet.
        pages = [p for k, v in placed if k == "page" and (p := self._page_for(v)) is not None]
        path = pages[-1] if pages else self._cue_path
        self._cue_path = path
        if "photo" in kinds:
            self._viewing = True
        if kinds & {"show", "plan", "photo"}:
            # Its own cues are sent after this returns: count them as shown now,
            # so the next sentence on the same part does not ring it again.
            for kind, value in placed:
                if kind == "show":
                    self._shown = section_key(value) or value
                elif kind == "plan":
                    self._shown = "tipologías"
                    self._planned = match_typology(value, self._typologies(path)) or value
            return []
        page = self.kb.page(path)
        # Photos or a plan full screen: a sentence about what is in them
        # ("the barbecue area") is not a move to that part of the page.
        viewing = self._viewing or (self.photo is not None and self.photo.fullscreen)
        if not self._is_project_page(path):
            # The project list, or a reply that opens it: the card of the one
            # project a sentence is about, as he says it.
            card = self._card_in(sentence)
            if card is not None:
                return [("show", card.site_name)]
        if page is not None and page.kind == "project":
            typologies = self._typologies(path)
            plan = typology_in(sentence, typologies)
            if plan is not None and plan != self._planned:
                self._planned = plan
                return [("plan", plan)]
            key = section_in(sentence, self._keys(path))
            if key is not None and key != self._shown and not viewing:
                return [("show", key)]
            return []
        if page is None:
            return []
        heading = best_section(sentence, [(s.heading, s.text) for s in page.sections])
        if heading is not None and heading != self._shown:
            return [("show", heading)]
        return []

    def _card_in(self, sentence: str) -> Project | None:
        """The one listed project ``sentence`` is about, unless its card is
        rung already or the sentence is a question (the closing offer)."""
        if sentence.rstrip().endswith("?"):
            return None
        named = named_projects(sentence, self.kb)
        if len(named) != 1 or not named[0].listed or not named[0].path:
            return None
        if canonical_path(named[0].path) == self._carded:
            return None
        return named[0]

    def _is_project_page(self, path: str) -> bool:
        page = self.kb.page(path)
        live = self._live(path)
        return (page is not None and page.kind == "project") or (
            live is not None and live.kind == "project"
        )

    def _on_a_list(self) -> bool:
        """Whether this reply's cues land on the project list: it is in front,
        a page cue opened it, or this reply's show_projects did."""
        if self._listing_turn:
            return True
        target = canonical_path(self._cue_path)
        page = self.kb.page(target)
        live = self._live(target)
        return (
            target in ("/proyectos", "/oportunidades")
            or (page is not None and page.kind == "projects")
            or (live is not None and live.kind == "projects")
        )

    def _listed_project(self, value: str) -> Project | None:
        project = self.kb.project(value)
        if project is None or not project.listed or not project.path:
            return None
        return project

    def _page_for(self, value: str) -> str | None:
        """The canonical path a page cue's value names: a path of the site, or a
        project by its name."""
        page = self.kb.page(value)
        if page is not None:
            return page.path
        project = self.kb.project(value)
        if project is not None and project.path:
            return canonical_path(project.path)
        return None

    def _live(self, path: str) -> PageChanged | None:
        """What the tab reported, if it is showing ``path`` now."""
        if self.page is not None and canonical_path(self.page.path) == canonical_path(path):
            return self.page
        return None

    def _keys(self, path: str) -> tuple[str, ...]:
        """The canonical sections of the project page at ``path``: as the page
        reported them, else as the crawl found them, with the form beside the
        typologies."""
        live = self._live(path)
        if live is not None and live.sections:
            keys = tuple(live.sections)
        else:
            page = self.kb.page(path)
            keys = page.keys if page is not None else ()
        if "tipologías" in keys and "formulario" not in keys:
            keys = (*keys, "formulario")
        return keys

    def _typologies(self, path: str) -> tuple[str, ...]:
        live = self._live(path)
        if live is not None and live.typologies:
            return tuple(live.typologies)
        project = self.kb.project_at(path)
        return project.typologies if project is not None else ()

    def _resolve_cue(self, raw: RawCue) -> Cue | None:
        if raw.kind == "page":
            path = self._page_for(raw.value)
            if path is None:
                return None
            self._cue_path = path
            return Cue(at=raw.at, word=raw.word, path=site_path(path))
        target = self._cue_path
        moved = canonical_path(target) != canonical_path(self._path)
        path = site_path(target) if moved else None
        page = self.kb.page(target)
        if raw.kind == "plan":
            if page is None or page.kind != "project":
                return None
            label = match_typology(raw.value, self._typologies(target))
            if label is None:
                return None
            return Cue(at=raw.at, word=raw.word, path=path, typology=label)
        live = None if moved else self._live(target)
        on_project = (page is not None and page.kind == "project") or bool(
            live and live.kind == "project"
        )
        if raw.kind == "photo":
            return self._photo_cue(raw, path, target) if on_project else None
        # show: a section by its canonical name, a heading, else those words.
        if on_project:
            key = section_key(raw.value)
            if key is not None:
                if key not in self._keys(target):
                    return None
                return Cue(at=raw.at, word=raw.word, path=path, heading=key)
        headings = list(live.headings) if live and live.headings else []
        if page is not None:
            headings += [h for h in page.headings if h not in headings]
        heading = _match(raw.value, headings)
        if heading is None and not on_project:
            # A project named off its own page: its card, on the list.
            project = self._listed_project(raw.value)
            if project is not None:
                return Cue(
                    at=raw.at,
                    word=raw.word,
                    card=site_path(project.path),
                    text=project.site_name,
                )
        text = None if heading else raw.value[:120]
        return Cue(at=raw.at, word=raw.word, path=path, heading=heading, text=text)

    def _photo_cue(self, raw: RawCue, path: str | None, target: str) -> Cue | None:
        """``{photo: 3}``, ``{photo: amenidades 2}``: that photo, full screen."""
        value = fold(raw.value)
        which: Literal["gallery", "amenities"] = (
            "amenities" if re.search(r"amenid|amenit|equipam", value) else "gallery"
        )
        if ("amenidades" if which == "amenities" else "galería") not in self._keys(target):
            return None
        digits = re.search(r"\d+", value)
        number = int(digits.group()) if digits else None
        if number is None:
            number = next((n for w, n in _NUMBER_WORDS.items() if re.search(rf"\b{w}\b", value)), 1)
        total = 0
        if self.page is not None and path is None:
            total = len(self.page.photos if which == "gallery" else self.page.amenity_photos)
        if number < 1 or (total and number > total):
            return None
        return Cue(at=raw.at, word=raw.word, path=path, photo=number, photos=which)

    def _talk_now(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The one extra request a silent page move gets: tools declared, none
        callable. Gemini refuses a request that ends on its own turn (a reply
        of thoughts and no words did, live, on 2026-10-22), so the ask is put
        in words first."""
        history = self._history
        if history and history[-1].role == "model":
            self._note("[Your last reply had no words. Answer the visitor now, briefly, in words.]")
        return self.respond_with(session, tools=ToolChoice.NONE)

    async def _run(self, tool: Any, call: types.FunctionCall) -> types.Part:
        """Every tool takes one model, ``request``; Gemini sometimes sends its
        fields flat, which the SDK refuses. Wrap them before the call runs."""
        args = dict(call.args or {})
        if (
            tool is not None
            and "request" not in args
            and "request" in inspect.signature(tool).parameters
        ):
            # Flat, or none at all ("the next photo"): every field has a default.
            logger.info("ssilva: {} called with flat arguments; wrapping them", call.name)
            call = call.model_copy(update={"args": {"request": args}})
        return await super()._run(tool, call)

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Page→brain events, folded in silently: no floor taken, no turn."""
        event = SSILVA_EVENTS.parse(msg)
        if event is None:
            return
        logger.info("ssilva: {} — {}", type(event).__voqal_event__, event)
        if isinstance(event, LanguageRequested):
            await self._requested(session, event)
            return
        if (note := self.apply_event(event)) is not None:
            self._note(note)

    async def _requested(self, session: Session, event: LanguageRequested) -> None:
        """The visitor pressed the other language on the toggle: both legs move
        in one awaited request, and the written confirmation is said in his next
        turn — which, if they stay quiet, is a short quiet spell."""
        if event.language == self.spoken:
            return
        was = self.spoken
        try:
            await session.configure(self._speaking(event.language))
        except RequestRejected as rejected:
            logger.warning("ssilva: switch to {} refused: {}", event.language, rejected)
            self.spoken = was
            session.dispatch(LanguageChanged(language=was))
            return
        logger.info("ssilva: language -> {} (toggle)", event.language)
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
            stt=SttConfig(language=language, patience=SSILVA_PATIENCE),
            tts=TtsConfig(voice=VOICE, language=language),
        )

    # ─── Page → brain ───────────────────────────────────────────────────

    def apply_event(self, event: SsilvaEvent) -> str | None:
        """Patch the mirror; return the line the model should see."""
        match event:
            case PageChanged():
                if canonical_path(event.path) != self._path:
                    self.typology = None
                    self.photo = None
                    if self.lead is not None and self.lead.step != "sent":
                        self.lead = None
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
            case TypologyShown():
                self.typology = event
                return f"[On screen: {_typology_line(event)}.]"
            case ProjectsListed():
                self.listed = event
                if event.count == 0:
                    self._talk_through(
                        "The project list on their screen shows no project for that filter. "
                        "Say so in one sentence and offer a nearby area or a wider search."
                    )
                return f"[{_listed_line(event)}]"
            case LeadFormState():
                return self._lead_changed(event)
            case LeadSubmitted():
                if event.blocked:
                    self._talk_through(
                        "They have just pressed Enviar on the quote form. This is a preview, so "
                        "the page held it back and nothing reached Ssilva: say so plainly in "
                        "one sentence, thank them, and offer the project's WhatsApp or more "
                        "about the project."
                    )
                    return (
                        "[The visitor pressed Enviar on the quote form. This preview held it "
                        "back: nothing was sent to Ssilva.]"
                    )
                self._talk_through(
                    "They have just pressed Enviar on the quote form. Thank them in one "
                    "sentence, say a Ssilva executive will contact them, and offer to keep "
                    "answering questions."
                )
                return "[The visitor pressed Enviar: the quote form was sent to Ssilva.]"
            case LanguageRequested():
                # Switched by on_rtvi before it gets here: a toggle is not a note.
                return None
            case PhotoShown():
                was, self.photo = self.photo, event
                return _photo_line(event, was)
            case ViewerClosed():
                self.photo = None
                if event.by == "javier":
                    return None  # He moved on; he knows.
                return "[The visitor closed the full-screen view.]"
            case CommandFailed() if event.command == "show_projects" and "is not among" in (
                event.reason
            ):
                # The list is up, filtered; only the ring missed.
                return (
                    f"[The project list is on their screen, but these cards were not rung "
                    f"({event.reason}). Do not mention it; if they pick one, open its page "
                    "with a page cue.]"
                )
            case CommandFailed() if event.command == "cue":
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

    def _lead_changed(self, event: LeadFormState) -> str:
        before = self.lead
        self.lead = event
        filled = "; ".join(f"{_LEAD_NAMES.get(k, k)}: {v}" for k, v in event.filled.items() if v)
        missing = ", ".join(_LEAD_NAMES.get(k, k) for k in event.missing)
        note = f"[The quote form, step {'one' if event.step == 'contact' else 'two' if event.step == 'details' else event.step}. Filled: {filled or 'nothing'}."
        if missing:
            note += f" Still empty: {missing}."
        for key, options in event.options.items():
            if options and key in LEAD_STEP_TWO:
                note += f" Options for {_LEAD_NAMES.get(key, key)}: {' | '.join(options)}."
        if event.errors:
            note += f" The form says: {' '.join(event.errors)}"
        if event.step == "details" and not event.missing:
            note += " Everything is filled: the visitor checks it and presses Enviar themselves."
        note += "]"
        new_errors = [e for e in event.errors if before is None or e not in before.errors]
        if new_errors:
            self._talk_through(
                "The quote form on their screen rejected something they gave. Tell them which, "
                "in one sentence, and ask for it again."
            )
        elif event.step == "details" and (before is None or before.step != "details"):
            held = {k: v for k, v in self._lead_held.items() if k in LEAD_STEP_TWO}
            self._talk_through(
                "Step two of the quote form is on their screen. Ask its questions one at a "
                "time, with its options"
                + (f"; they already told you: {held}, so fill those in now" if held else "")
                + "."
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
            self._note(f"[The visitor's open ssilva.cl tabs — {listed}.]")
        self._tabs_unseen = False
        if not self._page_unseen or self.page is None:
            return
        self._page_unseen = False
        self._note(_page_line(self.page, self.kb))

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

    def _on_project(self) -> Project | None:
        """The project whose page is in front, if it is a project page."""
        if self.page is not None and self.page.kind != "project":
            return None
        return self.kb.project_at(self._path) if self.kb.page(self._path) else None

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        """Read and search Ssilva's projects and pages, filter the list, move
        the gallery and the tour, fill the quote form, open WhatsApp."""
        return [
            self.find_projects,
            self.read_project,
            self.read_topic,
            self.search_site,
            self.show_projects,
            self.show_photos,
            self.step_photo,
            self.slideshow,
            self.show_floor_plan,
            self.open_tour,
            self.close_overlay,
            self.fill_lead_form,
            self.open_whatsapp,
            self.switch_tab,
            self.set_language,
        ]

    @needs_result_now
    async def find_projects(self, request: FindRequest) -> str:
        """Filter Ssilva's projects by what the visitor wants: comuna or region,
        type, bedrooms, budget in UF, status, profile. Cheapest first."""
        found = self.kb.find_projects(**request.model_dump())
        lang = self.spoken
        out: list[str] = []
        if found.unknown:
            comunas = sorted({p.comuna for p in self.kb.projects.values() if p.listed})
            out.append(
                f"Not a comuna, region or value the site has: {', '.join(found.unknown)}. "
                f"Comunas with projects: {', '.join(comunas)}."
            )
            asked = {k: v for k, v in request.model_dump().items() if v is not None}
            if set(asked) <= {"comuna", "region"}:
                return "\n".join(out)
        if found.dropped:
            out.append(
                f"No project fits all of that. Without {' and '.join(found.dropped)}, these do; "
                "say what is different."
            )
        if not found.projects:
            return "\n".join([*out, "No project matches."])
        out.append(f"{len(found.projects)} projects:")
        for p in found.projects[:_FOUND_SHOWN]:
            said = f" (say: {uf_words(p.desde_uf, lang)})" if p.desde_uf else ""
            out.append(f"- {p.line()}{said}")
        if len(found.projects) > _FOUND_SHOWN:
            out.append(f"And {len(found.projects) - _FOUND_SHOWN} more.")
        return "\n".join(out)

    @needs_result_now
    async def read_project(self, request: ProjectRequest) -> str:
        """Every fact of one project: address, typologies with unit prices and
        sizes, amenities, status, sections, hours, phone, email."""
        project = self.kb.project(request.name)
        if project is None:
            hits = [h for h in self.kb.search(request.name, 4) if h.kind == "project"]
            names = ", ".join(h.title for h in hits) or "none"
            return f"No project '{request.name}' on ssilva.cl. Closest: {names}."
        text = self.kb.project_text(project)
        if project.desde_uf:
            text += f"\nSay the desde price as: {uf_words(project.desde_uf, self.spoken)}."
        if project.path:
            text += f"\nOpen it with {{page: {project.path}}}."
        return text

    @needs_result_now
    async def read_topic(self, request: TopicRequest) -> str:
        """Read one of the guides before answering from it."""
        topic = self.kb.topics.get(request.topic)
        if topic is None:
            return f"No guide '{request.topic}' is written yet: use search_site."
        return topic.text

    @needs_result_now
    async def search_site(self, request: SearchRequest) -> str:
        """Search ssilva.cl's pages, the guides and the projects. Each result
        names where it is."""
        hits = self.kb.search(request.query, _SEARCH_HITS)
        if not hits:
            return f"Nothing on ssilva.cl matches '{request.query}'."
        out: list[str] = []
        for h in hits:
            if h.kind == "project":
                where = f"project {h.title}" + (f", page {h.path}" if h.path else "")
            elif h.kind == "topic":
                where = f"guide {h.ref}"
            else:
                where = f"page {site_path(h.path or '/')}" + (
                    f", heading: {h.section}" if h.section else ""
                )
            out.append(f"[{where}] {h.snippet}")
        return "\n".join(out)

    async def show_projects(self, request: ShowProjectsRequest) -> str:
        """Open the project list filtered by region, type and comunas, and ring
        the projects you name. The page reports what it lists."""
        region = region_of(request.region)
        prop = property_of(request.property)
        communes: list[str] = []
        rung: list[str] = []
        unknown: list[str] = []
        for asked in request.communes:
            found = self.kb.find_projects(comuna=asked)
            places = {p.comuna for p in found.projects} if not found.unknown else set()
            if not places:
                unknown.append(asked)
                continue
            for place in sorted(places):
                if place in COMMUNE_IDS:
                    communes.append(place)
                    region = region or "metropolitana"
                else:
                    # No checkbox outside the Región Metropolitana: ring its projects.
                    here = [p for p in found.projects if p.comuna == place]
                    rung += [p.site_name for p in here]
                    region = region or here[0].region
        names: list[str] = []
        for name in request.highlight:
            project = self.kb.project(name)
            if project is None or not project.listed:
                unknown.append(name)
            elif project.site_name not in names:
                names.append(project.site_name)
        names += [n for n in rung if n not in names]
        by_name = {p.site_name: p for p in self.kb.projects.values()}
        paths = [site_path(by_name[n].path) for n in names if n in by_name and by_name[n].path]
        # The site's commune filter takes one comuna at a time.
        others, communes = communes[1:], communes[:1]
        if region is None and names:
            regions = {p.region for p in self.kb.projects.values() if p.site_name in names}
            if len(regions) == 1:
                region = next(iter(regions))
        self._move(
            ShowProjects(
                region=region, property=prop, communes=communes, highlight=names, paths=paths
            ),
            "list",
        )
        # The cards he named before this call, rung on the list as he says them.
        self._listing_turn = True
        self._cue_path = "/proyectos"
        cards, self._cards = self._cards, []
        for cue in cards:
            self.session.dispatch(cue)
        parts = [
            REGION_LABELS[region] if region else "every region",
            prop or "",
            ", ".join(communes),
        ]
        result = f"Opening /proyectos/ filtered to {', '.join(p for p in parts if p)}"
        result += f"; ringing {', '.join(names)}." if names else "."
        if unknown:
            result += f" Not on the list, so left out: {', '.join(unknown)}."
        if others:
            result += (
                f" The list filters one comuna at a time: {', '.join(others)} left out; show it "
                "in another show_projects call if they ask."
            )
        return result + " The page reports what it lists."

    async def show_photos(self, request: PhotosRequest) -> str:
        """On a project page: move the photo gallery, or open the amenities
        photos. In the same response, say what the photos show."""
        project = self._on_project()
        if project is None:
            return "Not shown: photos are on a project page. Open the project first."
        key = "galería" if request.which == "gallery" else "amenidades"
        if key not in self._keys(self._path):
            return f"Not shown: {project.name}'s page has no {key}."
        full = request.fullscreen or request.which == "amenities"
        self._move(ShowPhotos(which=request.which, index=request.index, fullscreen=full), "photos")
        return (
            f"Showing {project.name}'s {key}"
            + (" full screen" if full else "")
            + (f" at photo {request.index}." if request.index else ".")
            + " Say what it shows from the screen line, in a few words."
        )

    async def step_photo(self, request: StepRequest) -> str:
        """The next photo, or with back the previous one: in the full-screen
        view, or on the gallery."""
        if self._on_project() is None:
            return "Not moved: photos are on a project page. Open the project first."
        self._move(StepPhoto(back=request.back), "photo")
        return "Moved. Say what it shows from the screen line, in a few words."

    async def slideshow(self, request: SlideshowRequest) -> str:
        """Run the photos full screen by themselves, one every few seconds, or
        stop them. They also stop when the visitor speaks."""
        project = self._on_project()
        if project is None:
            return "Not started: photos are on a project page. Open the project first."
        if not request.play:
            self._move(Slideshow(play=False), "stopped")
            return "Stopped on the photo on screen."
        which = request.which
        key = "amenidades" if which == "amenities" else "galería"
        if key not in self._keys(self._path):
            return f"Not started: {project.name}'s page has no {key}."
        seconds = max(3, min(15, request.seconds)) if request.seconds else None
        self._move(Slideshow(play=True, which=which, seconds=seconds), "slideshow")
        return (
            "The slideshow is running. Say in one sentence that the photos go by on their own "
            "and they can say stop, or ask for any one."
        )

    async def show_floor_plan(self, request: PlanRequest) -> str:
        """Open a typology's floor plan full screen, on a project page or its
        cotizar page."""
        on_quote = self.page is not None and self.page.kind == "quote"
        project = self._on_project()
        if project is None and not on_quote:
            return "Not shown: floor plans are on a project page. Open the project first."
        label = request.typology
        if label and not on_quote:
            typologies = self._typologies(self._path)
            matched = match_typology(label, typologies)
            if matched is None:
                return f"Not shown: no typology '{label}' here. It has: {'; '.join(typologies)}."
            label = matched
        self._move(ShowFloorPlan(typology=label), "plan")
        return f"Opening the floor plan{f' of {label}' if label else ''} full screen."

    async def open_tour(self) -> str:
        """Open the virtual tour on this project's page, where it has one."""
        project = self._on_project()
        if project is None:
            return "Not opened: the tour is on a project page. Open the project first."
        if "tour" not in self._keys(self._path):
            return f"Not opened: {project.name}'s page has no virtual tour. Offer the gallery."
        self._move(OpenTour(), "tour")
        return f"Opening {project.name}'s virtual tour."

    async def close_overlay(self) -> str:
        """Close the photo viewer or the tour that is open."""
        self._move(CloseOverlay(), "closed")
        return "Closed."

    async def fill_lead_form(self, request: LeadRequest) -> str:
        """Fill in the quote form on this project's page with what the visitor
        told you; what is filled stays. With next_step, once step one is
        complete, go to step two. It never presses Enviar."""
        given = {
            k: v.strip()
            for k, v in request.model_dump(exclude={"next_step"}).items()
            if isinstance(v, str) and v.strip()
        }
        given = {**self._lead_held, **given}
        refused: list[str] = []
        fields: dict[str, str] = {}
        options = self.lead.options if self.lead is not None else {}
        for key, value in given.items():
            if key == "rut":
                if not rut_is_valid(value):
                    refused.append(
                        f"RUT '{value}' does not check out (its last digit is wrong): spell it "
                        "back and ask again"
                    )
                    continue
                value = format_rut(value)
            elif key == "email" and not _EMAIL.match(value.replace(" ", "")):
                refused.append(f"'{value}' is not an email: ask again")
                continue
            elif key == "email":
                value = value.replace(" ", "").lower()
            elif key == "motivo":
                value = _match(value, options.get("motivo", [])) or motivo_of(value) or value
                if value not in ("Invertir", "Habitar") and not options.get("motivo"):
                    refused.append(f"motivo is Invertir or Habitar, not '{value}'")
                    continue
            elif key in LEAD_STEP_TWO:
                choices = options.get(key, [])
                if not choices:
                    self._lead_held[key] = value
                    continue
                picked = option_for(value, choices)
                if picked is None:
                    refused.append(
                        f"{_LEAD_NAMES[key]} '{value}' is none of the form's options: "
                        f"{' | '.join(choices)}"
                    )
                    continue
                value = picked
            fields[key] = value
        project = self._on_project()
        if project is None or "formulario" not in self._keys(self._path):
            self._lead_held.update(fields)
            where = f"{{page: {project.path}}}" if project and project.path else "the project page"
            return (
                "Not filled yet: the quote form is on a project page with typologies. Open it "
                f"({where}{{show: formulario}}) and call fill_lead_form again; what they told "
                "you is kept."
            )
        for key in fields:
            self._lead_held.pop(key, None)
        if not fields and not request.next_step:
            return "Nothing filled. " + "; ".join(refused) if refused else "Nothing to fill."
        self._lead_sent.update(fields)
        self._move(FillLeadForm(**fields, next_step=request.next_step), "form")
        result = "Filled: " + (
            ", ".join(f"{_LEAD_NAMES[k]} {v}" for k, v in fields.items()) or "nothing new"
        )
        if "email" in fields:
            result += ". Read the email back in words"
        if "rut" in fields:
            result += ". Spell the RUT back"
        if request.next_step:
            result += ". Going to step two once step one is complete; its options come back"
        held = [k for k in self._lead_held if k in LEAD_STEP_TWO]
        if held:
            result += f". Kept for step two: {', '.join(_LEAD_NAMES[k] for k in held)}"
        missing = [
            _LEAD_NAMES[k] for k in (*LEAD_FIELDS, *LEAD_STEP_TWO) if k not in self._lead_sent
        ]
        if missing:
            result += f". Still to ask: {', '.join(missing)}"
        if refused:
            result += ". Not filled: " + "; ".join(refused)
        return result + ". The visitor presses Enviar themselves."

    async def open_whatsapp(self) -> str:
        """Open a WhatsApp chat with this project's sales executive, in a new
        tab. Only when they ask, or say yes to your offer."""
        project = self._on_project()
        if project is None:
            return (
                "Not opened: the WhatsApp button is on a project page. Open the project "
                "first, or give Ssilva's phone, (56 2) 2496 1300."
            )
        self._move(OpenWhatsApp(), "whatsapp")
        return f"Opened WhatsApp with {project.name}'s executive in a new tab."

    async def switch_tab(self, request: TabRequest) -> str:
        """Bring another of the visitor's ssilva.cl tabs to the front."""
        tab = next((t for t in self.tabs if t.tab_id == request.tab_id), None)
        if tab is None:
            listed = ", ".join(f"{t.tab_id} ({t.title})" for t in self.tabs) or "none"
            return f"Not switched: no tab '{request.tab_id}'. Open tabs: {listed}."
        self._move(FocusTab(tab_id=tab.tab_id), "tab")
        return f"Brought '{tab.title or tab.url}' to the front."

    async def set_language(self, request: LanguageRequest) -> str:
        """Conduct the rest of the call in Spanish ('es') or English ('en'),
        listening and speaking. Call it when they ask for the other language in
        words that are not already it — "¿Puedes hablar en inglés?" — and to go
        back. Say one short line in the language you are switching to, in the
        same response. A visitor already speaking English has been switched: do
        not call it for them."""
        self._chosen = True
        configure_soon(self.session, self._speaking(request.language))
        logger.info("ssilva: language -> {} (asked)", request.language)
        return "ok"


# ─── Screen lines ──────────────────────────────────────────────────────────────


def _typology_line(t: TypologyShown) -> str:
    facts = [
        f"typology {t.label}",
        t.price,
        f"área total {t.total_area}" if t.total_area else "",
        f"área útil {t.useful_area}" if t.useful_area else "",
        f"{t.bedrooms} dormitorios" if t.bedrooms else "",
        f"{t.bathrooms} baños" if t.bathrooms else "",
        f"orientación {t.orientation}" if t.orientation else "",
    ]
    return ", ".join(f for f in facts if f)


_PHOTOS_IN_NOTE = 12


def _numbered(items: list[str]) -> str:
    return _clip([f"{i} {c or 'sin nombre'}" for i, c in enumerate(items, 1)], _PHOTOS_IN_NOTE)


def _photo_line(e: PhotoShown, was: PhotoShown | None) -> str | None:
    """A photo on screen, as the model reads it: each one he or the visitor
    moved to, and a slideshow once, when it starts and when it stops."""
    what = {"gallery": "gallery photo", "amenities": "amenities photo", "plan": "floor plan"}
    shown = (
        f"the floor plan {e.caption}"
        if e.which == "plan"
        else f"{what[e.which]} {e.index} of {e.total}" + (f" ({e.caption})" if e.caption else "")
    )
    if e.playing:
        if was is not None and was.playing:
            return None  # The slideshow's next photo: no news.
        return f"[On screen: a slideshow of the {e.which} photos, from {shown}.]"
    if was is not None and was.playing:
        return f"[The slideshow stopped on {shown}.]"
    by = " (the visitor moved to it)" if e.by == "visitor" else ""
    return f"[On screen: {shown}{by}.]"


def _listed_line(e: ProjectsListed) -> str:
    where = ", ".join(x for x in (e.region or "", e.property or "", ", ".join(e.communes)) if x)
    names = "; ".join(e.projects) or "none"
    return (
        f"The project list shows {e.count} project{'s' if e.count != 1 else ''}"
        + (f" for {where}" if where else "")
        + f". On this page: {names}."
    )


def _page_line(p: PageChanged, k: Knowledge) -> str:
    """The page in front, as the model reads it."""
    path = site_path(p.path)
    if p.kind == "project":
        project = k.project_at(p.path)
        # The site's own name: a translated page's title is "BARROSO DISTRICT".
        name = project.name if project else (p.project or p.title)
        note = f"[The tab in front: the project page of {name} ({path})."
        if p.price:
            note += f" Hero: {p.price}."
        if p.status:
            note += f" Estado: {p.status}."
        if p.typologies:
            note += f" Typologies: {'; '.join(p.typologies)}"
            note += f" (selected: {p.typology})." if p.typology else "."
        if p.sections:
            note += f" Sections: {', '.join(p.sections)}."
        if p.photos:
            note += f" Gallery photos: {_numbered(p.photos)}."
        if p.amenity_photos:
            note += f" Amenities photos: {_numbered(p.amenity_photos)}."
    elif p.kind == "projects":
        note = f"[The tab in front: the project list ({path})."
    elif p.kind == "quote":
        note = f"[The tab in front: the cotizar page {p.title or path} ({path}). Its form is on the project's page."
    elif p.kind == "home":
        note = "[The tab in front: the home page (/)."
    else:
        note = f"[The tab in front: “{p.title or path}” ({path})."
    if p.headings:
        note += f" Headings: {_clip(p.headings, _HEADINGS_IN_NOTE)}."
    return note + "]"


__all__ = [
    "CloseOverlay",
    "Cue",
    "FillLeadForm",
    "FocusTab",
    "LanguageChanged",
    "Navigate",
    "OpenTour",
    "OpenWhatsApp",
    "SelectTypology",
    "ShowPhotos",
    "ShowProjects",
    "ShowSection",
    "SsilvaBrain",
]
