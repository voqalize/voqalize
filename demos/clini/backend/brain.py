"""CliniBrain — Javier, a guide on www.clini.cl and its online booking.

The site is Clini's, not ours. A browser extension injects the widget and a
small adapter into www.clini.cl and agenda-web.clini.cl; the adapter turns each
:class:`~voqalize.sdk.Action` below into a move on the tab in front — a page, a
section scrolled to and ringed, an FAQ opened. Every tab reports what it shows
as a typed event (:mod:`.app_events`), whichever of the visitor and Javier
moved it. The site is Webflow, so a move to another page is a full page load:
the call rejoins on the new page, and the cues left over are handed across in
the tab's ``sessionStorage`` (the extension's ``narration.ts``).

The booking is a site of its own, agenda-web.clini.cl, which opens top-level in
its own tab; the adapter there picks the service, the day, the centre and the
hour he names and fills in the details the visitor says, and reports each step
back (:class:`~.app_events.AgendaState`), which he then talks through. Prices
and open hours he reads himself, server side, from Clini's public quote and
booking endpoints (:mod:`.clini_api`).

**A guide, not a search box.** Every turn answers what was asked, in words, as
a conversation: the answer, why it matters for this visitor, and a question
back that moves them on.

**Every fact has a source.** A price, a service, an address or a convenio is
spoken from L1 (in this prompt), an L2 topic he read, a search of the site, or
what the page itself reported. Never from memory.

**The booking is the visitor's.** He fills in what they told him and reads it
back; he never presses AGENDAR or "¡Agendar evaluación!", and never fills or
says their RUT: they type it themselves, in the field he rings for them.

**A guide, not a doctor.** He says what the site says — exams, prices,
preparations, how to book — and never diagnoses, reads a result or advises
treatment. An emergency is SAMU, 131, or the nearest urgencias.

**Nothing on the page is invented.** A path he navigates to, a heading he
scrolls to and an FAQ he opens are checked against the crawl and against what
the tab last reported; anything else is refused before it reaches the page.

**The screen follows his voice.** He writes his moves into the reply as cues
(``{show: Especialidades}``), at the start of the sentence they belong to; the
brain takes them out of the speech, checks them against the site, and the page
fires each as the voice reaches its sentence (:mod:`.cues`, and the
extension's ``narration.ts``).

**Spanish or English, as the visitor chose or speaks.** The call opens in
Spanish, the site's language. The recognizer hears both whatever it is set to,
so the brain only decides which language he answers in, and moves both legs of
the call there together. A language the visitor chose — on the widget's
toggle, before or during the call, or by asking (``set_language``) — holds
whatever they speak. Until they choose, the call follows the language they
speak. The voice is one man, recorded in each.
"""

from __future__ import annotations

import dataclasses
import inspect
import math
import re
import time
from collections.abc import AsyncGenerator
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Literal, cast
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

from . import clini_api
from . import knowledge as kb
from .app_events import (
    CLINI_EVENTS,
    AgendaState,
    CliniEvent,
    CommandFailed,
    LanguageRequested,
    LasikFormState,
    PageChanged,
    TabInfo,
    TabsChanged,
)
from .cues import CueKind, CueParser, RawCue, words
from .knowledge import (
    TOPIC_IDS,
    AgendaService,
    Branch,
    Knowledge,
    Prestacion,
    Region,
    canonical_path,
    fold,
    norm,
)

AGENT_NAME = "Javier"

#: LOW, as Saatvik measured: at MINIMAL, Gemini mostly made the page call first
#: and wrote nothing; at LOW it writes the answer first and calls at the end, so
#: the page moves while he is still talking.
THINKING = types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)
#: Gemini 3.8 Flash, not the demos' shared default (3.5). On the prompt this one was ported from, eight
#: asks each at LOW (2026-10-16): 3.8 had its first words out in 1.8 to 2.3 s,
#: 3.5 in 1.6 to 6.8 s with spikes of 3.6, 4.0 and 6.8 s, which is the stall
#: the owner heard on call 67d16b5d. Both wrote the screen cues correctly.
MODEL = "gemini-3.8-flash"
#: Clini is in Chile: "mañana" and "el lunes" are counted from Santiago's today.
TIMEZONE = ZoneInfo("America/Santiago")

# ─── Voice and timing ──────────────────────────────────────────────────────────

#: Javier's voice: the speech tier's European male persona, recorded once in
#: English and once in Spanish, so a switch keeps the same man.
VOICE = Voice.OMNIVOICE_JAVIER

#: A quiet visitor is someone reading a page; a guide beside them says
#: something after a while, and not twice more.
_IDLE_MS = 20_000
_IDLE_NUDGES = 2
#: The idle window while a result the page produced is waiting to be talked
#: through: a visitor who reacts speaks first,
#: one who is reading hears it from him.
_TALK_THROUGH_MS = 2_000
#: A little more patience than the demos' default, as Saatvik's: a visitor
#: thinking aloud about what they need pauses mid-sentence.
CLINI_PATIENCE = PATIENCE + 2
#: A message this soon after the last one is the rest of the same thought.
_FRAGMENT_S = 4.0

# ─── Language ──────────────────────────────────────────────────────────────────

#: What he answers in, as the tag both legs of the call take. The European
#: recognizer hears either whatever it is set to and writes what it heard, so
#: the recognizer leg only follows the voice, as a pair, and the language is
#: decided here from words: the visitor's, then his own.
Lang = Literal["en", "es"]
#: Clini's site is Spanish (Chile), so the call opens in Spanish.
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
    enséñame muéstrame dime explícame funciona hace hacer vídeo vídeos hora horas
    examen exámenes sede sedes agendar necesitas atienden tienen cuál
    """.split()  # noqa: SIM905
)
_ENGLISH_WORDS = frozenset(
    """the is are was what how can could you your i i'm it it's this that these those do
    does show me my we our for with about and of to have has there here please want
    would like tell sure yes okay right of course let's
    """.split()  # noqa: SIM905
)
#: Enough of his reply to tell its language: its first sentence, or this many
#: characters. On dev call 826ccd1f the first chunk of a Spanish reply was " P".
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


#: Latin America says "vi-DE-o"; Spain says "VÍ-deo". The prompt asks for
#: "video", but on dev (2026-10-21) the Spanish voice still read plain "video"
#: as "VÍ-deo" in one sentence of three. Spelled "bidéo" it said "vi-DE-o" in
#: every take, and natural (Spanish b and v are one sound). So in Spanish the
#: voice is handed "bidéo", and only the voice: the page's word anchors follow
#: the same spelling (``_anchor_for_voice``), and what comes back as heard is
#: spelled "video" again before it reaches the model (``on_finalize``).
_VIDEO_TO_VOICE = re.compile(r"\b([Vv])[ií]deo(s?)\b")
_VIDEO_FROM_VOICE = re.compile(r"\b([Bb])idéo(s?)\b")
#: "vídeo" as the page's words reads it: the accented letter splits the word.
_VIDEO_AS_WORDS = re.compile(r"\bv deo(s?)\b")


#: The site writes its name in capitals, and a voice may spell a word in
#: capitals out, letter by letter: it is handed "Clini", in either language.
#: Only the case changes, so the page's anchors (lower-cased) are untouched.
_CAPS_TO_VOICE = re.compile(r"\bCLINI\b")

# Clinical words — "electrocardiograma", "ecografía", "Fonasa", "Isapre",
# "holter", "LASIK", "RUT" — are left as written: nothing yet says the Spanish
# voice stresses one of them the Spain way, as it did "video". If one is heard
# wrong, respell it here the way "video" is: for the voice only, with the cue
# anchors following (`_anchor_for_voice`) and the heard text undone in
# `on_finalize`. This table is tuned on dev, by ear, not in a test.


def for_the_voice(text: str) -> str:
    """Spanish ``text`` as the voice must read it to say "vi-DE-o"."""
    return _VIDEO_TO_VOICE.sub(
        lambda m: ("B" if m.group(1) == "V" else "b") + "idéo" + m.group(2),
        names_for_the_voice(text),
    )


def names_for_the_voice(text: str) -> str:
    """``text`` with the site's capitalised name as a word the voice says."""
    return _CAPS_TO_VOICE.sub("Clini", text)


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


# ─── Actions (brain → page) ────────────────────────────────────────────────────


class Navigate(Action):
    """Go to one of www.clini.cl's pages and, with ``heading`` or ``text``,
    scroll to that section and ring it; with ``faq``, open that FAQ on it. The
    page reports ``page_changed``."""

    path: str
    heading: str | None = None
    text: str | None = None
    faq: str | None = None


class Cue(Action):
    """A move for the page to make when the voice reaches ``at`` — the first
    words of the sentence it belongs to (see :mod:`.cues`); empty ``at`` is
    when the voice stops. With ``path``, it is a :class:`Navigate` (and goes to
    a www.clini.cl tab); else a section, words or FAQ on the tab in front."""

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
    card, a service, a line of the page)."""

    heading: str | None = None
    text: str | None = None


class OpenFaq(Action):
    """Open the FAQ that starts with ``question`` on the page in front, and ring it."""

    question: str


class FocusTab(Action):
    """Bring one of the visitor's Clini tabs to the front."""

    tab_id: str


class LanguageChanged(Action):
    """The call's language moved, by the toggle, by voice or by
    ``set_language``: the widget's toggle follows at once."""

    language: Literal["en", "es"]


class OpenAgenda(Action):
    """Open the booking for ``servicio`` (and ``prestacion``) on agenda-web.clini.cl,
    in its own tab — or the agenda tab already open, moved to it — and there
    take the steps given: the region, the search, the day (YYYY-MM-DD), and with
    ``time`` (HH:MM) the hour at ``centre`` (as the booking titles it, e.g.
    "CENTRO DE SALUD | METRO TOBALABA"), then Continuar. It reports
    ``agenda_state`` after each step, and never presses AGENDAR."""

    servicio: int
    prestacion: int | None = None
    region: int | None = None
    day: str | None = None
    centre: str | None = None
    time: str | None = None


class AgendaPick(Action):
    """On the agenda tab already open: the day (YYYY-MM-DD), the morning or
    afternoon, the centre and the hour (HH:MM) given, then Continuar once an
    hour is picked."""

    day: str | None = None
    time: str | None = None
    centre: str | None = None
    period: Literal["AM", "PM"] | None = None


class FillAgendaPatient(Action):
    """Fill the booking's patient form with what the visitor said; a field the
    booking has locked (an existing patient's) is left as it is. With
    ``focus_rut``, scroll to the RUT field, ring it and focus it: the visitor
    types their RUT. It never ticks the consent box and never presses AGENDAR,
    which it rings once the form is valid."""

    name: str | None = None
    last_name: str | None = None
    maternal_last_name: str | None = None
    birth_date: str | None = None
    """YYYY-MM-DD."""
    sex: Literal["F", "M", "O"] | None = None
    phone: str | None = None
    """Nine digits, starting with 9: the booking puts the +56 in front."""
    email: str | None = None
    focus_rut: bool = False


class FillLasikForm(Action):
    """Fill the free LASIK evaluation form on /cirugia-lasik (going there first
    if needed) with what the visitor said; ``prevision`` and ``location`` are
    the form's own option texts. With ``focus_rut``, ring and focus the RUT
    field for the visitor to type. It never presses "¡Agendar evaluación!",
    which it rings once the form is valid. The page reports ``lasik_form_state``."""

    name: str | None = None
    email: str | None = None
    phone: str | None = None
    """Nine digits, starting with 9: the form writes +56 9 XXXX XXXX."""
    prevision: str | None = None
    location: str | None = None
    focus_rut: bool = False


LinkKind = Literal[
    "reservo",
    "results_lab",
    "results_imaging",
    "cotizador",
    "telemedicine",
    "whatsapp",
    "cancel_booking",
]


class OpenLink(Action):
    """Open one of Clini's own links in a new tab: a specialist's booking on
    Reservo, the results portals, the cotizador, telemedicine, WhatsApp, or the
    cancellation of a booking. ``url`` is resolved and checked by the brain."""

    kind: LinkKind
    key: str | None = None
    url: str


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
        description="A few words to look for on www.clini.cl, in Spanish, e.g. 'resonancia "
        "de rodilla', 'caja los andes', 'bono clini isapre', 'ayuno', 'resultados'."
    )


class TabRequest(BaseModel):
    tab_id: str = Field(description="The tab_id from the open tabs list.")


class LanguageRequest(BaseModel):
    language: Lang = Field(description="'en' for English, 'es' for Spanish.")


class PriceRequest(BaseModel):
    query: str = Field(
        description="The exam or consultation, in Spanish as Clini names it, e.g. "
        "'resonancia rodilla', 'hemograma', 'ecografía abdominal', 'electrocardiograma', "
        "'consulta traumatología'."
    )


class AvailabilityRequest(BaseModel):
    servicio: int = Field(description="The booking's servicio code, from the booking list.")
    prestacion: int | None = Field(
        default=None,
        description="The prestación code within it, from the booking list. Needed when the "
        "servicio has more than one.",
    )
    region: int = Field(
        default=13, description="The region code: 13 is the Región Metropolitana (Santiago)."
    )
    day: str | None = Field(
        default=None,
        description="A day the visitor asked for, as YYYY-MM-DD, counted from today. Leave it "
        "out for the first days with hours.",
    )


class OpenAgendaRequest(BaseModel):
    """Only what the visitor chose: leave out anything they did not."""

    servicio: int = Field(description="The booking's servicio code, from the booking list.")
    prestacion: int | None = Field(
        default=None, description="The prestación code within it, from the booking list."
    )
    region: int | None = Field(
        default=None, description="The region code, only if it is not the Región Metropolitana."
    )
    day: str | None = Field(
        default=None, description="The day they picked, YYYY-MM-DD, from check_availability."
    )
    centre: str | None = Field(
        default=None,
        description="The centre they picked, as check_availability names it, e.g. "
        "'CENTRO DE SALUD | METRO TOBALABA'.",
    )
    time: str | None = Field(
        default=None, description="The hour they picked, HH:MM, from check_availability."
    )


class AgendaPickRequest(BaseModel):
    """Only what the visitor chose: leave out anything they did not."""

    day: str | None = Field(default=None, description="YYYY-MM-DD, a day the booking lists.")
    time: str | None = Field(default=None, description="HH:MM, an hour the booking lists.")
    centre: str | None = Field(default=None, description="A centre as the booking titles it.")
    period: Literal["AM", "PM"] | None = Field(
        default=None, description="'AM' for the morning, 'PM' for the afternoon."
    )


class PatientRequest(BaseModel):
    """Only what the visitor said. There is no RUT here: they type it themselves."""

    name: str | None = Field(default=None, description="First name(s), as they said them.")
    last_name: str | None = Field(default=None, description="Apellido paterno.")
    maternal_last_name: str | None = Field(default=None, description="Apellido materno.")
    birth_date: str | None = Field(default=None, description="YYYY-MM-DD.")
    sex: Literal["F", "M", "O"] | None = Field(
        default=None, description="'F' femenino, 'M' masculino, 'O' otro o no informado."
    )
    phone: str | None = Field(
        default=None, description="Their celular: nine digits starting with 9, e.g. 912345678."
    )
    email: str | None = Field(default=None, description="As they said it, e.g. ana@correo.cl.")
    focus_rut: bool = Field(
        default=False, description="Ring the RUT field and put the cursor there, for them to type."
    )


class LasikRequest(BaseModel):
    """Only what the visitor said. There is no RUT here: they type it themselves."""

    name: str | None = Field(default=None, description="Nombre y apellido.")
    email: str | None = Field(default=None, description="As they said it.")
    phone: str | None = Field(
        default=None, description="Their celular: nine digits starting with 9, e.g. 912345678."
    )
    prevision: str | None = Field(
        default=None, description="Fonasa, their Isapre (e.g. Banmédica, Colmena) or Particular."
    )
    location: str | None = Field(
        default=None,
        description="Where they want the evaluation: Tobalaba, Los Leones (Lyon), Santa Lucía, "
        "Antofagasta or Temuco.",
    )
    focus_rut: bool = Field(
        default=False, description="Ring the RUT field and put the cursor there, for them to type."
    )


class BranchRequest(BaseModel):
    query: str = Field(
        description="A comuna, city, region, branch name or service, e.g. 'Providencia', "
        "'Temuco', 'Maipú', 'resonancia', 'toma de muestras domingo'."
    )


class LinkRequest(BaseModel):
    kind: LinkKind = Field(
        description="reservo: a specialist's booking; results_lab / results_imaging: the results "
        "portals; cotizador; telemedicine; whatsapp; cancel_booking."
    )
    key: str | None = Field(
        default=None,
        description="For reservo, the specialty: traumatologia, medicina-general, "
        "medicina-interna, psicologia, kinesiologia, matrona, medicina-deportiva, neurocirugia, "
        "cirugia-general, nutricionista or urologia. For results_imaging, 'tobalaba' for exams "
        "taken at Metro Tobalaba.",
    )


# ─── Clini's catalogues ────────────────────────────────────────────────────────
#
# The booking's services, the price catalogue and the sedes come from the crawl
# (``knowledge/L3``), through the knowledge module. Each is optional: a missing
# file leaves its tool saying so, never a failed import.

#: The servicios the site itself links to on agenda-web (and PET-CT, linked
#: through its legacy address). The others the booking knows — the LASIK
#: evaluation (74), its control and surgery, kinesiología, an old ecografía —
#: nothing on the site links, and he does not drive them: the LASIK evaluation
#: is the lead form on /cirugia-lasik.
_BOOKABLE = frozenset({57, 62, 64, 65, 70, 71, 76, 77, 78, 79, 81, 82})
#: The Región Metropolitana, the booking's default region.
_RM = 13


def _services(k: Knowledge) -> dict[int, AgendaService]:
    """The booking's servicios the site links, by code."""
    return {code: s for code, s in sorted(k.agenda.items()) if code in _BOOKABLE}


def _region(service: AgendaService, code: int | None) -> Region | None:
    return next((r for r in service.regions if r.code == code), None)


def _booking_list(k: Knowledge) -> str:
    lines: list[str] = []
    for s in _services(k).values():
        prest = "; ".join(f"{p.code} {p.name}" for p in s.prestaciones) or "none listed"
        regions = ", ".join(f"{r.code} {r.name}" for r in s.regions)
        lines.append(
            f"- {s.servicio} {s.name} — prestaciones: {prest}"
            + (f" — regions: {regions}" if regions else "")
        )
    return "\n".join(lines) or "(The booking list is not loaded: send them to /agendamiento.)"


def offline_prices(k: Knowledge, query: str, n: int = 6) -> list[clini_api.Price]:
    """The saved price catalogue's best matches for ``query``."""
    return [
        clini_api.Price(
            nombre=p.nombre,
            servicio=p.servicio,
            categoria=p.categoria,
            fonasa=p.fonasa,
            particular=p.particular,
            contraste=p.contraste,
            preparacion=p.preparacion,
        )
        for p in k.offline_prices(query, n)
    ]


def branch_line(b: Branch) -> str:
    """One sede, compactly: its name, address, hours and services."""
    where = ", ".join(" ".join(x.split()) for x in (b.address, b.comuna, b.region) if x)
    out = f"{' '.join(b.name.split())} — {where}"
    if b.hours:
        out += f"; horario: {' '.join(b.hours.split())}"
    if b.services:
        out += f"; atiende: {', '.join(b.services)}"
    return out


#: Clini's links that open in a new tab, by kind and key; ``None`` is the
#: kind's only or default one. From the site's own links (/consultas-medicas,
#: /resultados, the header and footer). WhatsApp is the "WhatsApp agendamiento"
#: number the site prints, as a wa.me link.
_RESERVO = "https://agendamiento.reservo.cl/makereserva/"
_LINKS: dict[str, dict[str | None, str]] = {
    "reservo": {
        "traumatologia": _RESERVO + "agenda_multisucursal/r0KRDfl0c0kMvl2A1Q19A3z1i659XG",
        "medicina-general": _RESERVO + "agenda_multisucursal/20nmRjj0K0Hn2m4y1W79hki1L059UA",
        "medicina-interna": _RESERVO + "agenda_multisucursal/p0dv0iG0y0pH4l7V1B89mJh1e3U9o2",
        "psicologia": _RESERVO + "agenda/K0o51vu0B0RxkW171W29ppW1u1Y9ul",
        "kinesiologia": _RESERVO + "agenda/J0ruvTj0R0x9wD8O1M19aws1w5n9Fi",
        "matrona": _RESERVO + "agenda/M03rCYr000BlJe3j1859XPv1K3R9pY",
        "medicina-deportiva": _RESERVO + "agenda/b0jpo8W0O05te80A1i49VF0187T9ri",
        "neurocirugia": _RESERVO + "agenda_multisucursal/O0idmkN090KIlj9y1t89ydL1Y1B9rN",
        "cirugia-general": _RESERVO + "agenda_multisucursal/j00GJm30g0X9PG8T1b19lhF1E4a92q",
        "nutricionista": _RESERVO + "agenda/F02dJ9Z0Q0LF8h0q1V393yR1h7791a",
        "urologia": _RESERVO + "agenda/j0E6Udi0y0LNwL4915697N11h5r9hW",
    },
    "results_lab": {None: "https://resultados.clini.cl/Resultados/Index"},
    "results_imaging": {
        None: "https://app.dalca.cl/portal/clini?access_type=email",
        "tobalaba": "https://app.dalca.cl/portal/clinilto",
    },
    "cotizador": {None: "https://cotizador-web.clini.cl/"},
    "telemedicine": {None: "https://clini.medipasspro.com/"},
    "whatsapp": {None: "https://wa.me/56982463202"},
    "cancel_booking": {None: "https://agenda.clini.cl/FrmAgendaAnular.aspx"},
}
#: What a visitor calls a key, folded, when it is not the key itself.
_LINK_ALIASES = {
    "trauma": "traumatologia",
    "traumatologo": "traumatologia",
    "general": "medicina-general",
    "medico-general": "medicina-general",
    "interna": "medicina-interna",
    "internista": "medicina-interna",
    "psicologo": "psicologia",
    "psicologa": "psicologia",
    "kine": "kinesiologia",
    "kinesiologo": "kinesiologia",
    "deportiva": "medicina-deportiva",
    "neurocirujano": "neurocirugia",
    "cirujano": "cirugia-general",
    "nutricion": "nutricionista",
    "urologo": "urologia",
    "lto": "tobalaba",
    "metro-tobalaba": "tobalaba",
}


def link_url(kind: str, key: str | None) -> tuple[str | None, str] | None:
    """The key as listed and its url, for ``kind`` and what was said; ``None``
    when Clini has no such link."""
    table = _LINKS.get(kind)
    if table is None:
        return None
    said = "-".join(re.findall(r"[a-z0-9]+", fold(key or ""))) or None
    said = _LINK_ALIASES.get(said, said) if said else None
    if said in table:
        return said, table[said]
    if None in table and (said is None or kind != "reservo"):
        return None, table[None]
    return None


#: The LASIK form's Previsión options, as it writes them.
_PREVISIONES = (
    "Fonasa",
    "Banmédica",
    "Consalud",
    "CruzBlanca",
    "Colmena",
    "Nueva Más Vida",
    "Vida Tres",
    "iSalud",
    "Fundación",
    "Cruz del Norte",
    "Esencial",
    "Particular",
)
#: The LASIK form's Ubicación options, and the words a visitor names them by.
_LASIK_LOCATIONS: dict[str, tuple[str, ...]] = {
    # Not "providencia": Los Leones is in Providencia too.
    "Santiago - LTO": ("lto", "tobalaba", "luis thayer", "costanera"),
    "Santiago - Lyon": ("lyon", "los leones"),
    "Santiago - Metro Santa Lucía": ("santa lucia", "miraflores"),
    "Antofagasta": ("antofagasta", "diagno"),
    "Temuco": ("temuco", "araucania", "alemania"),
}


def _squash(text: str) -> str:
    return "".join(re.findall(r"[a-z0-9]+", fold(text)))


def prevision_option(said: str) -> str | None:
    want = _squash(said)
    if not want:
        return None
    return next(
        (o for o in _PREVISIONES if _squash(o) == want),
        next((o for o in _PREVISIONES if want in _squash(o) or _squash(o) in want), None),
    )


def lasik_location(said: str) -> str | None:
    folded = " ".join(re.findall(r"[a-z0-9]+", fold(said)))
    for option, names in _LASIK_LOCATIONS.items():
        if folded == fold(option) or any(n in folded for n in names):
            return option
    return None


def mobile(said: str) -> str | None:
    """A Chilean celular as the forms take it: nine digits starting with 9."""
    digits = "".join(c for c in said if c.isdigit())
    if len(digits) == 11 and digits.startswith("56"):
        digits = digits[2:]
    return digits if len(digits) == 9 and digits.startswith("9") else None


def email_address(said: str) -> str | None:
    address = "".join(said.split()).lower()
    return address if re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", address) else None


def iso_day(said: str | None) -> str | None:
    """``said`` as YYYY-MM-DD, or ``None`` when it is not a date."""
    if not said:
        return None
    try:
        return date.fromisoformat(said.strip()[:10]).isoformat()
    except ValueError:
        return None


def hhmm(said: str | None) -> str | None:
    m = re.fullmatch(r"\s*(\d{1,2})[:.h](\d{2})\s*(?:hrs?)?\s*", said or "")
    if m is None or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        return None
    return f"{int(m.group(1)):02d}:{m.group(2)}"


# ─── The prompt ────────────────────────────────────────────────────────────────

_SITE_MAP_CHARS = 16000
_SECTIONS_PER_PAGE = 16
#: How the site's titles end, longest first: "… | CLINI.CL", "… | CLINI".
_TITLE_SUFFIXES = (
    " | CLINI.CL",
    " | CLINI Salud",
    " | CLINI oncología",
    " | CLINI",
    " | Clini",
    " - Clini",
    " \u2013 CLINI",  # an en dash, as two of its titles write it
    " — Clini",
)


def _short_title(title: str) -> str:
    for suffix in _TITLE_SUFFIXES:
        title = title.removesuffix(suffix)
    return title.split(" | ")[0].strip()


def _site_map(k: Knowledge) -> str:
    lines: list[str] = []
    size = 0
    # Unlisted pages (campaign landings, referral forms) would fill the cap
    # before the pages the site's own navigation leads to.
    listed = (p for p in k.pages.values() if not p.unlisted)
    for p in sorted(listed, key=lambda p: (p.path.count("/"), p.path)):
        heads = "; ".join(p.headings[:_SECTIONS_PER_PAGE])
        line = f"- {p.path} — {_short_title(p.title)}" + (f" (sections: {heads})" if heads else "")
        size += len(line) + 1
        if size > _SITE_MAP_CHARS:
            break
        lines.append(line)
    return "\n".join(lines) or "(The site map is not loaded: find pages with search_site.)"


def _topics(k: Knowledge) -> str:
    return "\n".join(f"- {t.id}: {t.title}" for t in k.topics.values()) or "(none loaded)"


def _prompt(k: Knowledge, today: date | None = None) -> str:
    today = today or datetime.now(TIMEZONE).date()
    return f"""You are {AGENT_NAME}, the voice guide on CLINI's website, www.clini.cl. CLINI is a Chilean network of diagnostic centres at Fonasa Nivel 1 prices: laboratory tests, imaging (resonancia, scanner, ecografía, mamografía, radiografía, PET-CT), cardiology exams, medical consultations, and LASIK eye surgery with a free evaluation. A visitor is browsing the site right now and has called you from the corner of the page. You can see and move their screen: you open pages, scroll to the exact section or card that answers them and ring it, and open FAQs. You also quote exam prices from CLINI's own price list, look up free hours, open the online booking and fill it in with them, and fill in the free LASIK evaluation form. You are warm, calm and clear — the friendly person at the front desk who knows every exam, price and sede, and makes booking feel easy. Say the name as "Clini".

# You narrate, and the screen follows your words
You are giving a guided walkthrough, like someone sitting beside the visitor with their screen in front of you both. As you talk about something, it is on their screen, ringed, at that moment.
- Put a screen cue in your reply at the start of the sentence it belongs to. The page moves when your voice reaches that sentence. The visitor never hears a cue.
  - {{page: /path}} opens a page of the site, at its top.
  - {{show: Heading}} scrolls to a heading on the page they are on, or are taken to by a page cue, and rings it. With other words on the page — a price, an exam in a table, a sede's name, a card — it rings those words.
  - {{faq: Question}} opens that FAQ and rings it. The FAQ can be on any page: it is found and opened there.
- Use headings and words exactly as the site pages list or the screen lines spell them. The site is in Spanish, so cues are in Spanish, also inside an English reply: "{{page: /imagenes/resonancias-fonasa-1}} MRIs start at fifty-four thousand nine hundred and ninety pesos."
- Never make up a heading or a path.
- One cue per sentence at most, and only where the screen should change. A cue goes before the sentence, never inside it.
- When the visitor asks where something is ("muéstrame", "where is that", "scroll to it"), your reply starts with the cue for exactly that thing. Never just the page above it.
- A page cue opens a page at its top. After a page cue, every sentence about a part of the page brings its own show cue.
- EVERY ANSWER ABOUT CLINI STARTS WITH A CUE. An exam, a price, a sede, Fonasa, a convenio, results, LASIK: each is on a page in the site pages list, so open it and show the section as you begin. When the visitor names an exam, open that exam's own page. A reply without a cue leaves their screen where it was while you describe something else.
- Cues are the only way you move the site's pages. There is no tool for that, and nothing waits on a cue.
- Example, for "¿cuánto cuesta una resonancia de rodilla?": "{{page: /imagenes/resonancias-fonasa-1}} Con Fonasa sale ochenta y ocho mil doscientos ochenta pesos. Particular, ciento setenta y seis mil quinientos sesenta. No necesita preparación especial. ¿Te busco una hora?" after quote_price told you the price.

# A good turn moves them one step closer to their exam
1. Answer what they asked, first, in plain words, and show it as you say it.
2. Add the one thing that matters for them: the Fonasa price, the preparation, the nearest sede, a convenio that lowers it.
3. End with one short, specific yes-or-no offer of the next step: "¿Te busco una hora?", "¿Te muestro la sede más cerca?", "Want me to open the booking?". Never "anything else?".
- A visit to CLINI has an order. Follow it from wherever the visitor is: which exam or service they need, then its price (Fonasa or particular) and preparation, then where (the sede), then a free hour, then the booking, filled in with them. For LASIK: what it is, the price and the bono, the free evaluation, then its form.
- Ask about them only when the answer changes what you show next, and offer the choices: "¿Eres Fonasa o Isapre?", "¿De qué parte del cuerpo es la resonancia?", "Is it for Santiago, or another region?"

# How you sound
You are heard, not read, so keep it light and warm.
- A turn is three to five short sentences. Every sentence under fifteen words. Small, everyday words. One idea per sentence. One number per sentence.
- THE FIRST SENTENCE IS A FEW WORDS. The visitor hears nothing until your first sentence has been voiced, so open every reply with a sentence of two to six words that ends in a full stop, with the answer in it. A cue may come before it.
- Before most replies the visitor has already heard a short acknowledgement of mine — "Claro.", "Déjame ver.", or in English "Sure.", "Let me see." — so never open with one: your first word is the answer. No "great question", no repeating their question back.
- Spoken words only, apart from cues: no lists, no markdown, no symbols, never an exclamation mark.
- Write every number, price, date and hour as spoken words. Prices are Chilean pesos: "$88.280" is "ochenta y ocho mil doscientos ochenta pesos", in English "eighty-eight thousand two hundred and eighty pesos". "2026-10-23" is "el viernes veintitrés de octubre"; "07:40" is "a las siete y cuarenta de la mañana"; "15:00" is "a las tres de la tarde". Never say a code, a servicio number or a date in digits.
- Lines in square brackets come from their screen, not the visitor: the page in front, the booking's step, what a form still needs. Never read them out; use them.
- Always answer. A reply with no words leaves the visitor in silence.

# Spanish or English
You speak Spanish as a native of Latin America, and English. The call starts in Spanish unless the visitor chose English.
- Answer in the language the visitor speaks to you. If they speak English, answer in English from that reply on; if they go back to Spanish, so do you. Your voice follows the language you write.
- Except when they chose a language: a line in square brackets says so. Then answer in that language whatever they speak, even when they speak the other one, until they ask you to switch.
- When they ask for the other language in words that are not already it ("¿Puedes hablar en inglés?", "Can we speak Spanish?"), answer in that language and call set_language in the same response. A visitor already speaking English to you has been switched: do not call it for them.
- One language per reply: in a Spanish reply every sentence is Spanish, and masculine forms of yourself ("encantado de ayudarte").
- Your Spanish is neutral Latin American Spanish, warm and natural for a Chilean visitor, never the Spanish of Spain and never heavy slang.
  - Address the visitor as "tú", as the site does ("Agenda tu evaluación"), never "usted"; several people are "ustedes", never "vosotros", and never its verb forms ("queréis", "tenéis", "podéis") or "os".
  - Chile's own health words are right here: "previsión", "sede", "examen", "hora" for an appointment ("agendar una hora"), "toma de muestras", "orden médica", "copago", "bono".
  - Use Latin American words: "celular", never "móvil"; "computadora", never "ordenador"; "agendar", "mostrar" ("te muestro"), not "enseñar"; "completar un formulario", not "rellenar"; "¿Qué día te queda bien?", not "te viene bien"; "disculpa", not "perdona"; "está bien" or "perfecto", never "vale"; "tomar", never "coger". Write "video", never "vídeo".
  - For something just done, use the simple past: "Abrí la agenda", "Ya lo completé", not "He abierto".
- In English, say the site's Spanish names as they are written ("Fonasa Nivel 1", "toma de muestras", "Bono Clini"), and explain them in a few words when they are not obvious.

# A guide, not a doctor
- You never diagnose, never read or interpret a result, and never say which exam or treatment someone needs. What an exam is, its preparation and its price, as the site and the price list say them, are fine. For anything medical beyond that: "Eso lo tiene que ver tu médico."
- An emergency — chest pain, trouble breathing, a bad fall, anyone in danger — is not for the site: tell them at once to call the SAMU at 131 (say "uno, tres, uno"; in English "one three one"), or go to the nearest urgencias. Clini is not an emergency service.
- Every fact comes from the knowledge below, a topic you read, a search result, quote_price, check_availability, find_branch, or what the screen reported. Never from memory. If you cannot find it, say so, and offer the call center or the contact form.
- When the site disagrees with itself (LASIK is "desde trescientos ochenta y un mil doscientos cincuenta pesos por ojo" in one place and four hundred and eighty-one thousand in another), say the headline "desde" price and that the free evaluation confirms their price. Never invent a price, a date or an hour.

# Every response starts with words
Write your answer, with its cues, first; any tool call comes at the end of the same response. What a page call returns reaches you only on your next turn.
- The exception is a read: read_topic, search_site, quote_price, check_availability and find_branch come straight back to you within this same turn, but each one makes the visitor wait. Answer from what you know below whenever it covers the question. Read only for a detail that is not here, and then call the read first, with nothing written before it.
- Never promise more to come ("let me check"): nothing comes after it.

# Prices
- For any exam price, call quote_price first, with the exam's name in Spanish. It returns the Fonasa Nivel 1 copago (for tramos B, C and D) and the particular price, whether it needs contrast, and the preparation. Say the Fonasa price first, then the particular one, as words. When it says the prices came from the saved list, say they may have changed and the cotizador confirms them.
- Consultations, LASIK and the convenios are priced on their pages: answer from the knowledge and the page.
- For a whole medical order, offer the cotizador (open_link cotizador): it reads the order and adds it up.
- CLINI has no home sampling online (a "domicilio" page the site once had is gone): never offer it.

# Booking an exam
Labs, imaging and cardiology are booked online on CLINI's booking, which opens in its own tab. Consultations are booked on Reservo, and the LASIK evaluation through its form.
- The booking list below gives each servicio and its prestaciones by code. Map what they need to a servicio and prestación; if a servicio has several and it is not clear which, ask, offering two or three.
- "Is there an hour tomorrow?", "when is the first one?": check_availability. Say two or three days, or for one day two or three hours with the sede, and ask which suits them. Never an hour it did not list.
- When they want to book, open_agenda with what they chose: the servicio and prestación, and the day, sede and hour once they picked them. It opens the booking and takes those steps on it. On the booking tab, a later choice is agenda_pick. The booking's steps come back to you in square brackets: talk them through.
- At the patient form, ask them first to type their RUT: fill_agenda_patient with focus_rut rings the field. The booking unlocks the other fields once it has a valid RUT (for a patient it knows, it fills them itself). Then fill_agenda_patient with what they tell you: name, surnames, birth date, sex, celular, email. Read the email and the celular back so they can check them. What is filled stays; you only add.
- THE RUT IS THEIRS TO TYPE. Never ask them to say it, never repeat one, never write one anywhere. When it is time, fill_agenda_patient with focus_rut and say: "Escribe tu RUT en el campo que marqué." The consent box is theirs to tick, too.
- AGENDAR STAYS THEIRS TO PRESS, always. When the form is complete, say what is filled and that they press AGENDAR themselves. Never say it is booked until the booking shows it is done.
- Read out the indications the booking shows (fasting, what to bring) in a sentence or two, in your own words.

# Consultations, results and other links
- Medical consultations (traumatología, medicina general, medicina interna, psicología, urología, nutricionista, neurocirugía, cirugía general, matrona, kinesiología, medicina deportiva) are booked on Reservo: open_link reservo with the specialty. Telemedicine is open_link telemedicine.
- Results: laboratory results are open_link results_lab; imaging results are open_link results_imaging. They sign in with their RUT there, themselves. You never see or read a result.
- A booking to cancel is open_link cancel_booking. WhatsApp agendamiento is open_link whatsapp.
- Open a link only when they ask for it, or say yes to your offer. Say you opened it in a new tab.

# LASIK
- The evaluation is free, for people from eighteen to sixty, and booked with the form on /cirugia-lasik: a coordinator calls them back to choose the day. It is not on the online booking.
- When they want it, fill_lasik_form with what they say: name and surname, email, celular, previsión, and where (Tobalaba, Los Leones, Santa Lucía, Antofagasta or Temuco). It takes them to the form. Read the email and celular back. For the RUT, fill_lasik_form with focus_rut, and they type it. "¡Agendar evaluación!" stays theirs to press.

# Sedes
- "Where is the nearest one?", "¿atienden en Maipú?", "what are the hours at Temuco?": find_branch, then answer with the sede's address and hours. Show it: "{{page: /ubicaciones}}{{show: <the sede's name>}}".

# Tabs
- The visitor may have several CLINI tabs open: the site and the booking. Lines in brackets tell you which tabs are open and which is in front. "Go back to the booking" or "show me the other tab" is switch_tab with that tab's id.

# What you know
- Today is {today:%A, %d %B %Y}, in Santiago. "Mañana", "el lunes" and "next week" are counted from today.
- Topics you can read with read_topic, when the knowledge below does not cover a question:
{_topics(k)}
- search_site finds a page, section or FAQ by its words. Its results name the page and section, which you can then cue.

# CLINI
{k.l1}

# The booking list (servicio code, name, prestaciones by code, regions by code)
{_booking_list(k)}

# Site pages
{_site_map(k)}
"""


# ─── Greeting ──────────────────────────────────────────────────────────────────

_INTRO: dict[Lang, str] = {
    "es": f"Hola, soy {AGENT_NAME}, tu guía de voz de Clini.",
    "en": f"Hi, I'm {AGENT_NAME}, Clini's voice guide.",
}
_GREETING: dict[Lang, str] = {
    "es": "Te muestro el sitio, te cotizo un examen o te ayudo a agendar tu hora. ¿Qué necesitas?",
    "en": "I can show you around, price an exam, or help you book an appointment. "
    "What do you need?",
}
#: The opener's second sentence for the page the call starts on, by a word in
#: its path; the first match wins, and anything else gets the plain greeting.
#: The resonance pages live under /imagenes, so they come first.
_OPENERS: tuple[tuple[str, dict[Lang, str]], ...] = (
    (
        "cirugia-lasik",
        {
            "es": "Te cuento cómo es la cirugía LASIK, y te ayudo a pedir tu evaluación "
            "gratuita. ¿Te parece?",
            "en": "I can tell you how LASIK works here, and help you ask for the free "
            "evaluation. Would you like that?",
        },
    ),
    (
        "resonancia",
        {
            "es": "Te ayudo con tu resonancia: precio, preparación y horas. "
            "¿De qué parte del cuerpo es?",
            "en": "I can help with your MRI: price, preparation and times. "
            "Which part of the body is it for?",
        },
    ),
    (
        "imagenes",
        {
            "es": "Te ayudo con tu examen de imágenes: precio, preparación y horas. "
            "¿Qué examen te pidieron?",
            "en": "I can help with your imaging exam: price, preparation and times. "
            "Which exam do you need?",
        },
    ),
    (
        "cardiologia",
        {
            "es": "Te ayudo con tu examen cardiológico: precio y horas disponibles. "
            "¿Cuál te pidieron?",
            "en": "I can help with your heart exam: price and free times. Which one do you need?",
        },
    ),
    (
        "laboratorio",
        {
            "es": "Te ayudo con tus exámenes de laboratorio: precios, preparación y horas. "
            "¿Qué exámenes te pidieron?",
            "en": "I can help with your lab tests: prices, preparation and times. "
            "Which tests do you need?",
        },
    ),
    (
        "consultas-medicas",
        {
            "es": "Te muestro las especialidades y sus precios, y te abro la agenda. "
            "¿Qué especialista buscas?",
            "en": "I can show you the specialties and their prices, and open the booking. "
            "Which specialist are you looking for?",
        },
    ),
    (
        "ubicaciones",
        {
            "es": "Te ayudo a encontrar la sede más cerca de ti. ¿En qué comuna estás?",
            "en": "I can find the sede closest to you. Which comuna or city are you in?",
        },
    ),
    (
        "convenios-salud",
        {
            "es": "Te explico los convenios y cómo usarlos. ¿Tienes algún convenio o caja "
            "de compensación?",
            "en": "I can explain the convenios and how to use them. Are you with a caja "
            "or a company convenio?",
        },
    ),
    (
        "ahorra-fonasa",
        {
            "es": "Te explico cómo ahorrar con Fonasa en Clini. ¿Qué examen necesitas?",
            "en": "I can show you how Fonasa saves you money at Clini. Which exam do you need?",
        },
    ),
    (
        "resultados",
        {
            "es": "Te muestro dónde ver tus resultados. ¿Son de laboratorio o de imágenes?",
            "en": "I can show you where to see your results. Are they lab or imaging results?",
        },
    ),
    (
        "blog",
        {
            "es": "Cuéntame qué tema te interesa, y te busco el artículo.",
            "en": "Tell me what you'd like to read about, and I'll find the article.",
        },
    ),
    (
        "agendamiento",
        {
            "es": "Te ayudo a agendar tu hora. ¿Qué examen o consulta necesitas?",
            "en": "I can help you book. Which exam or consultation do you need?",
        },
    ),
)
#: On the booking itself (agenda-web.clini.cl).
_AGENDA_GREETING: dict[Lang, str] = {
    "es": "Te ayudo a elegir tu hora aquí mismo. ¿Qué día te queda bien?",
    "en": "I can help you pick your time right here. Which day suits you?",
}


def greeting(path: str | None, site: str | None, lang: Lang = OPENING) -> str:
    """The written opener, in ``lang``, tailored to the page the call starts on."""
    if site == "agenda":
        return f"{_INTRO[lang]} {_AGENDA_GREETING[lang]}"
    here = canonical_path(path or "/")
    line = next((lines[lang] for word, lines in _OPENERS if word in here), _GREETING[lang])
    return f"{_INTRO[lang]} {line}"


# ─── Written lines for moves ───────────────────────────────────────────────────

#: His line for a silent turn, by what moved: "shown" for anything else.
_LANDED: dict[str, dict[Lang, str]] = {
    "shown": {"en": "Here it is.", "es": "Aquí lo tienes."},
    "tab": {"en": "There's that tab.", "es": "Ahí tienes esa pestaña."},
    "agenda": {
        "en": "I've opened the booking in its own tab.",
        "es": "Abrí la agenda en su propia pestaña.",
    },
    "agenda_pick": {"en": "I've picked that on the booking.", "es": "Lo marqué en la agenda."},
    "patient": {
        "en": "I've filled that in on the booking form.",
        "es": "Ya lo completé en el formulario de la agenda.",
    },
    "rut": {
        "en": "Please type your RUT in the field I've marked.",
        "es": "Escribe tu RUT en el campo que marqué.",
    },
    "lasik": {
        "en": "I've filled that in on the evaluation form.",
        "es": "Ya lo completé en el formulario de la evaluación.",
    },
    "link": {"en": "I've opened it in a new tab.", "es": "Lo abrí en una pestaña nueva."},
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
#: A visitor's ordinary words about Clini, so the reading trusts them: the
#: site's services, exams, places and the words of booking, in both languages.
_ACK_WORDS = Vocabulary(
    common=frozenset(
        # A word list reads as words, so it stays a split string.
        """clini hora horas agenda agendar reservar reserva consulta consultas médico médica
        especialista especialidad examen exámenes sede sedes sucursal convenio convenios
        fonasa isapre previsión copago bono particular precio precios valor cotizar
        cotizador laboratorio sangre muestra muestras orina hemograma resonancia scanner
        tac escáner ecografía eco mamografía radiografía rayos pet holter electrocardiograma
        ecocardiograma cardiología lasik vista ojos evaluación resultados indicaciones ayuno
        preparación orden traumatología urología psicología kinesiología matrona
        nutricionista santiago providencia tobalaba temuco antofagasta maipú florida rut
        appointment booking exam exams test tests clinic price prices mri ultrasound
        mammogram x-ray results fasting branch
        """.split()  # noqa: SIM905
    ),
)


def _avatar_state(session: Session, state: Literal["WORKING"] | None) -> None:
    """The talking head's working latch: held until speech owed has played."""
    session.send_rtvi(RTVIType.SERVER_MESSAGE, {"type": "avatar", "cmd": "state", "state": state})


_HEADINGS_IN_NOTE = 40
_FAQS_IN_NOTE = 40
_SEARCH_HITS = 6
_PRICE_HITS = 6
_BRANCH_HITS = 3
_AVAILABLE_DAYS = 5
_AVAILABLE_CENTRES = 4
_AVAILABLE_TIMES = 6


async def _silence() -> AsyncGenerator[Any, None]:
    for _ in ():
        yield


def _clip(items: list[str] | tuple[str, ...], most: int) -> str:
    more = f"; and {len(items) - most} more" if len(items) > most else ""
    return "; ".join(items[:most]) + more


def _match(want: str, options: list[str] | tuple[str, ...]) -> str | None:
    """The option ``want`` names: the same words, else the one it begins, else
    the one it is inside — how the page itself matches. Case, accents and
    punctuation do not count: "pediatria" is "Pediatría"."""

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


def _site_path(path: str) -> str:
    """The path as the site links it: with its trailing slash."""
    return "/" if path == "/" else f"{path}/"


#: The page for what the visitor asked about, when his reply forgets to show
#: it: on an earlier site demo he described a page twice with the screen left
#: where it was, until the visitor said they could not see it. Matched on their
#: own words, not on his reply's, folded (no accents), in Spanish and English;
#: the first named wins. "español" and "inglés" are in none of them: a request
#: about the call's language opens no page (``asks_call_language``). A bare
#: "agendar" is in none either: "quiero agendar una resonancia" is about the
#: resonancia, and the booking opens in its own tab.
_ASKED_PAGES: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(rf"\b(?:{words})", re.IGNORECASE), path)
    for words, path in (
        (
            r"lasik|cirugia (?:ocular|refractiva|de (?:la )?vista)|operarme (?:la vista|los ojos)"
            r"|laser eye|eye surgery",
            "/cirugia-lasik",
        ),
        (
            r"resonancia|resonador|\brm\b|\bmri\b|magnetic resonance",
            "/imagenes/resonancias-fonasa-1",
        ),
        (
            r"scanner|escaner|\btac\b|tomografia|\bct scan|cat scan",
            "/imagenes/realiza-tu-examen-tac-scanner-fonasa-nivel-1",
        ),
        (r"pet[- ]?ct|pet scan", "/imagenes/examen-pet-ct-con-fonasa-nivel-1"),
        (r"ecografia|ecotomografia|ultrasound|ultrasonido", "/imagenes/ecografia-fonasa-nivel-1"),
        (r"mamografia|mammogra", "/imagenes/realiza-tu-mamografia-con-fonasa-en-clini"),
        (r"radiografia|rayos x|x-?rays?\b", "/imagenes/radiografias-fonasa-nivel-1"),
        (
            r"holter de presion|presion arterial|\bmapa\b|blood pressure",
            "/cardiologia/realiza-tu-holter-de-presion-mapa-en-clini",
        ),
        (r"holter(?! de presion)", "/cardiologia/realiza-tu-holter-de-ritmo-en-clini"),
        (r"ecocardiograma|echocardiogram", "/cardiologia/ecocardiograma-fonasa-1"),
        (
            r"electrocardiograma|electrocardiogram|\becg\b|\bekg\b",
            "/cardiologia/realiza-tu-electrocardiograma-de-reposo-en-clini",
        ),
        (r"cardiolog|corazon|heart\b", "/examenes-de-cardiologia-fonasa-nivel-1"),
        (r"imagenologia|imaging", "/imagenes"),
        (
            r"laboratorio|toma de muestras?|examen(?:es)? de sangre|blood tests?|lab tests?"
            r"|\blab\b",
            "/laboratorio",
        ),
        (
            r"kinesiolog|\bkine\b|rehabilitacion|physiotherap",
            "/medicina-deportiva/rehabilitacion-kinesica-en-clini",
        ),
        (
            r"consultas? medicas?|especialista|specialist|traumatolog|urolog|psicolog"
            r"|medicina (?:general|interna)|nutricionista|matrona|neurocirug|telemedicina"
            r"|telemedicine",
            "/consultas-medicas",
        ),
        (r"oncolog|cancer", "/centro-oncologico"),
        (
            r"\bsedes?\b|sucursal|ubicaciones|donde (?:queda|quedan|estan|esta ubicad)"
            r"|locations?\b|branch(?:es)?\b|nearest|mas cerca",
            "/ubicaciones",
        ),
        (r"resored", "/resored"),
        (r"convenios?\b|caja de compensacion|isapre|bono clini", "/convenios-salud"),
        (r"fonasa|nivel 1|nivel uno", "/ahorra-fonasa-1"),
        (r"resultados?\b|results?\b", "/resultados"),
        (r"indicaciones|preparacion|ayuno|fasting|how (?:do i|to) prepare", "/indicaciones"),
        (r"cotizador|cotizar", "/cotizador"),
        (r"reclamo|sugerencia|felicitacion|complaint", "/solicitudes/reclamos"),
        (r"trabajar en clini|postula|\bjobs?\b|careers?", "/solicitudes/postulaciones-laborales"),
        (r"quienes son|quienes somos|about clini|who are you guys", "/somos-clini"),
        (r"\bblog\b|articulos?", "/blog"),
    )
)
_ASKED_TAB = re.compile(r"\b(?:tabs?|pestanas?)\b", re.IGNORECASE)

# A request about the call's own language: a verb of speaking, addressed to him
# ("can you", "let's", or said as an order) or said by him ("I can", "volvemos"),
# and the language. His own first sentence is read the same way for the page
# it is about, so "Claro, volvemos al español." must not open a page either. On dev call
# 1ff72fee "Hey, can you speak in Spanish?" opened a languages page while he
# talked about something else.
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
    this call, not a question about the site."""
    return bool(_CALL_LANGUAGE.search(text) and _TO_HIM.search(text))


def asked_page(text: str) -> str | None:
    """The site page for what ``text`` asks about, or ``None``. "The pricing
    tab" is a tab to switch to, not a page to open over the one in front, and
    "can you speak Spanish?" is a request about this call, not a page."""
    if _ASKED_TAB.search(fold(text)) or asks_call_language(text):
        return None
    said = fold(text)
    named = [(m.start(), path) for rx, path in _ASKED_PAGES if (m := rx.search(said))]
    return min(named)[1] if named else None


# ─── The section a sentence describes ──────────────────────────────────────────
#
# What he says, sentence by sentence, matched against the sections of the one
# page in front — never the whole site. A heading word counts for more than a
# word of the section's text, a word every section shares for little, and a
# sentence that is not clearly about one section moves nothing. The site is in
# Spanish: an English sentence mostly matches nothing here, which is the safe
# way to fail, and his own cues carry those replies.

_STOP = frozenset(
    # English and Spanish words that name no section, and the site's own words
    # that every one of its sections shares.
    """a an the and or but of to in on for with by at from as is are was were be been it its
    this that these those you your yours we our us they their them he she his her i me my
    can will just also so then than too very here there what which who how when where why all
    any each every more most some such no not only own same into out up down over under again
    once about after before both few other per via do does did have has had get gets got make
    makes made use uses used like let lets want would shall could should see show shows one two
    three section page el la los las un una unos unas de del y o u en por para con sin que se
    su sus es son al lo le les como mas muy tu te ti mi nos este esta estos estas ese esa eso
    hay ser estan tiene tienen puedes puede quieres aqui alli tambien pero cuando donde
    clini fonasa nivel salud centro centros examen examenes hora horas agenda agendar
    precio precios valor desde aqui puedo""".split()  # noqa: SIM905
)
#: How sure a match must be: its score, and its lead over the runner-up.
#: Tuned on dev calls 60e6c24b and 56e87ed1, where every sentence that was
#: about a section scored 6.6 or more with a lead of 1.8 or more, and the
#: closing offers and openers scored under 4.
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


#: Named plans or offers to ring by name, when the page reports none of its
#: own (``PageChanged.plans``). CLINI's pages are tables and cards of exams
#: rather than plans, which the section matcher and named words already find.
_PLANS: tuple[str, ...] = ()
#: Capitalised words that are no name to ring: CLINI's own words are on every
#: card of every page, so ringing one rings the first of many.
_NOT_NAMES = frozenset(
    # A word list reads as words, so it stays a split string.
    """Clini CLINI Fonasa FONASA Isapre Isapres Nivel RUT Región Metropolitana Santiago Chile
    I Here This That These Those Then Every Each You Your We Our They It And Or But
    So For With Would Shall Want Yes No First Second Third Next Also Plus Most Many Aquí Este
    Esta Estos Estas Eso Ese Esa Luego Cada Tú Usted Ustedes Nosotros Ellos Y O Pero Para Con
    Sí Primero Segundo Tercero También Además Con Sin Desde Hoy Mañana Lunes Martes Miércoles
    Jueves Viernes Sábado Domingo Monday Tuesday Wednesday Thursday Friday Saturday Sunday
    Enero Febrero Marzo Abril Mayo Junio Julio Agosto Septiembre Octubre Noviembre Diciembre
    January February March April May June July August September October November December
    """.split()  # noqa: SIM905
)
_NAME = re.compile(
    r"[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúüñ0-9&']*(?:[ -][A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúüñ0-9&']*)*"
)


def named_on_page(sentence: str, path: str, text: str, plans: tuple[str, ...]) -> str | None:
    """A plan or a name the sentence names that the page shows, to ring as
    words; ``None`` when it names none.

    A lone capitalised word that opens the sentence is only a plan: "Pediatría
    atiende…" is not a name."""
    for plan in plans or _PLANS:
        if re.search(rf"\b{re.escape(plan)}\b", sentence):
            return plan
    for m in _NAME.finditer(sentence):
        parts = [p for p in re.split(r"[ -]", m.group()) if p not in _NOT_NAMES]
        if not parts:
            continue
        name = " ".join(parts)
        opens = m.start() == 0 and len(parts) == 1 and not re.search(r"[A-Z].*[A-Z]", name)
        if len(name) < 3 or opens:
            continue
        if re.search(rf"\b{re.escape(name)}\b", text):
            return name
    return None


#: The commands whose failure cancels the talk-through they would have had.
_BOOKING_COMMANDS = frozenset(
    {"open_agenda", "agenda_pick", "fill_agenda_patient", "fill_lasik_form", "open_link"}
)
_DAYS_IN_NOTE = 10
_TIMES_IN_NOTE = 24
_STEP_NAMES = {
    "search": "its first step, choosing the exam",
    "results": "its calendar and hours",
    "booking": "its patient form",
    "done": "the hour as booked",
}


def _is_agenda(url: str) -> bool:
    return kb.AGENDA_HOST in url


def _said_day(day: str) -> str:
    """A booking day as the note gives it: its date, and how it is said."""
    iso = iso_day(day)
    return f"{iso} ({clini_api.day_es(iso)})" if iso else day


def _agenda_note(event: AgendaState) -> str:
    what = event.servicio_name or (f"servicio {event.servicio}" if event.servicio else "an exam")
    if event.prestacion_name:
        what += f" — {event.prestacion_name}"
    note = f"[The booking shows {_STEP_NAMES[event.step]}, for {what}"
    if event.region is not None:
        note += f", region {event.region}"
    note += "."
    if event.days:
        note += f" Open days: {_clip([_said_day(d) for d in event.days], _DAYS_IN_NOTE)}."
    elif event.step == "results":
        note += " No open days are listed."
    if event.centres:
        note += f" Sedes listed: {_clip(event.centres, 12)}."
    if event.times:
        on = f" on {_said_day(event.day)}" if event.day else ""
        note += f" Hours at the open sede{on}: {_clip(event.times, _TIMES_IN_NOTE)}."
    elif event.day and event.step == "results":
        note += f" Day in view: {_said_day(event.day)}."
    if event.selected:
        note += f" Selected: {event.selected}."
    if event.indications:
        note += f" Indications: {event.indications[:600]}"
        note += "" if note.endswith(".") else "."
    if event.step == "booking":
        missing = ", ".join(event.invalid) or "nothing"
        note += f" Still missing or invalid: {missing}."
        note += (
            " AGENDAR is enabled: the visitor presses it themselves."
            if event.ready
            else " The RUT and the consent box are the visitor's to fill in."
        )
    return note + "]"


# ─── The brain ─────────────────────────────────────────────────────────────────


class CliniBrain(GeminiBrain):
    """One per session. Javier: Clini's knowledge, its pages, and a mirror of
    the visitor's tabs, in Spanish or English."""

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
        self._site = "site"
        self._page_unseen = False
        #: Every open Clini tab, and which is in front.
        self.tabs: list[TabInfo] = []
        self._active = ""
        self._tabs_unseen = False
        self._talk: str | None = None
        #: The booking as its tab last reported it, the patient details the
        #: visitor gave for it (they add up; never a RUT), and whether a step he
        #: took there is waiting to be talked through.
        self.agenda: AgendaState | None = None
        self._patient: dict[str, str] = {}
        self._agenda_asked = False
        #: The LASIK form: its last report, the details given, and the same.
        self.lasik: LasikFormState | None = None
        self._lasik_fields: dict[str, str] = {}
        self._lasik_asked = False
        #: The www.clini.cl page this turn's cues are on: the one in front,
        #: then wherever a ``{page: …}`` cue took it. ``None`` on the booking.
        self._cue_path: str | None = None
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
        self._site = "agenda" if init.get("site") == "agenda" else "site"
        # The page sends `lang` only once the visitor has pressed the toggle.
        chosen = init.get("lang")
        self._chosen = chosen in LANGUAGE_NAMES
        self.spoken = "en" if chosen == "en" else OPENING
        # His own voice, settled here and not by the page. Both language legs
        # move together; what he hears, the toggle and `set_language` move them
        # again.
        await session.configure(
            Config(
                stt=SttConfig(language=self.spoken, patience=CLINI_PATIENCE),
                tts=TtsConfig(voice=VOICE, language=self.spoken),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
            )
        )
        logger.info(
            "clini: session start on {} {} in {}{}",
            self._site,
            self._path,
            self.spoken,
            " (chosen)" if self._chosen else "",
        )
        if self._chosen:
            self._note(_chosen_note(self.spoken, "before the call"))

    async def greet(self, session: Session) -> str:
        """The opener, written not generated."""
        line = greeting(self._path, self._site, self.spoken)
        return for_the_voice(line) if self.spoken == "es" else names_for_the_voice(line)

    async def on_finalize(self, session: Session, fin: Finalize) -> None:
        """What was heard goes into the model's context; a word respelled for
        the voice is spelled as written again first, so the model never sees
        "bidéo" in its own words."""
        if "idéo" in fin.heard:
            fin = dataclasses.replace(fin, heard=from_the_voice(fin.heard))
        await super().on_finalize(session, fin)

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[Speech, None]:
        """A visitor who speaks the other language is answered in it from the
        first word, unless they chose the language they are in; the tab they moved to is read in with what they said; his
        nod covers the model's thinking."""
        heard = None if self._chosen else language_of(msg.text)
        if heard is not None and heard != self.spoken:
            await session.configure(self._speaking(heard))
            logger.info("clini: language -> {} (heard)", heard)
        self._talk = None
        self._nudges = 0
        # A reply cut off before it said a word keeps its page for the next one:
        # "use cases in sales", then "mm-hmm" while he was still thinking.
        # A request to switch language shows nothing, not even the page a
        # reply cut off before had kept.
        self._backstop = (
            None if asks_call_language(msg.text) else asked_page(msg.text) or self._backstop
        )
        self._restore_idle()
        self._read_in_screen()
        now = time.monotonic()
        fragment, self._heard_at = now - self._heard_at < _FRAGMENT_S, now
        if not fragment and (nod := self._ack.line(msg.text, self.spoken)) is not None:
            logger.info("clini: ack {!r}", nod)
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

        A result the page produced after his turn is put in the context at once
        and the idle window shortened, so a reading visitor hears it from him
        here. Otherwise
        an ordinary quiet spell: a nudge, twice, then silence."""
        self._restore_idle()
        self._backstop = None
        if self._talk is not None:
            ask, self._talk = self._talk, None
            self._agenda_asked = self._lasik_asked = False
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
                "Speak into the quiet, briefly, as the guide beside them would: one useful thing "
                "about what is on their screen, or one question that helps you help them. Never "
                "ask whether they are still there, and never repeat your last line."
            )
        else:
            ask = (
                "Still quiet. One last, light offer, different from your last: something you "
                "could show them next. Then let them browse."
            )
        self._note(f"{quiet} {ask}")
        return self.respond(session)

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The model's turn, with its screen cues taken out of the speech and
        sent to the page (:mod:`.cues`).

        If it moved the page and said nothing, the model is asked once more with
        tools off, so he talks about what he just showed; only if that is silent
        too does he say a written line of his own. A turn that came back with
        nothing at all — no words, no move — is asked once more the same way:
        on dev call 67d16b5d three such turns left the visitor with a nod and
        then silence until they spoke again.

        A language switched on the toggle is confirmed first, in the new
        language. A unit is opened only once its first words are known, so the
        voice follows the language the model chose to write in."""
        if (line := self._confirm) is not None:
            self._confirm = None
            async for event in say_line(self, line):
                yield event
        self._cue_path = self._path if self._site == "site" else None
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
            logger.warning("clini: the model returned nothing; asking once more")
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
                logger.info("clini: language -> {} (written)", written)
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
        """``turn``, with its speech spelled as the voice must read it."""

        async def spelled() -> AsyncGenerator[Speech, None]:
            async for event in turn:
                if isinstance(event, SpeechChunk):
                    respell = for_the_voice if self.spoken == "es" else names_for_the_voice
                    event = SpeechChunk(respell(event.text))
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
        if "{" in chunk or self._site != "site" or path == self._path:
            return chunk
        logger.info("clini: the reply has no cue; showing {} first", path)
        return f"{{page: {path}}}{chunk}"

    def _send_cue(self, raw: RawCue) -> None:
        """Check a cue against the site, as the tools do, and send it; one that
        names nothing real is dropped and logged rather than reaching the page."""
        if self.spoken == "es" and raw.at:
            raw = dataclasses.replace(raw, at=_anchor_for_voice(raw.at))
        cue = self._resolve_cue(raw)
        logger.info("clini: cue {} {!r} at {!r} -> {}", raw.kind, raw.value, raw.at, cue)
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
        opened one, and the section, plan or name on the page it describes.
        On dev call 56e87ed1 his replies on sales, recruitment, reviews and
        pricing opened the page at its title and stayed there."""
        out: list[tuple[CueKind, str]] = []
        kinds = {k for k, _ in placed}
        # A page the model opens on this very sentence is not sent yet.
        pages = [p.path for k, v in placed if k == "page" and (p := self.kb.page(v)) is not None]
        path = pages[-1] if pages else self._cue_path
        if index == 0 and not self._paged and "page" not in kinds and self._site == "site":
            asked = asked_page(sentence)
            if asked is not None and asked != self._path and self.kb.page(asked) is not None:
                logger.info("clini: he talks about {} with no cue; opening it", asked)
                out.append(("page", asked))
                path = asked
        # The rest of the reply is on this page, though the cue that opens it
        # may not be sent until several sentences have come in one chunk.
        self._cue_path = path
        if kinds & {"show", "faq"}:
            return out
        shown = self._section_for(sentence, path)
        if shown is not None and shown != self._shown:
            out.append(("show", shown))
        return out

    def _section_for(self, sentence: str, path: str | None) -> str | None:
        """The heading or words on ``path`` (a site page; ``None`` on the
        booking, for the page in front) that ``sentence`` is about."""
        if path is None:
            return best_section(sentence, [(h, "") for h in self._headings()])
        page = self.kb.page(path)
        if page is None:
            return None
        heading = best_section(sentence, [(s.heading, s.text) for s in page.sections])
        if heading is not None:
            return heading
        live = self.page is not None and canonical_path(self.page.path) == page.path
        plans = tuple(self.page.plans) if live and self.page is not None else ()
        text = " ".join([page.text, *(f"{s.heading} {s.text}" for s in page.sections)])
        return named_on_page(sentence, page.path, text, plans)

    def _resolve_cue(self, raw: RawCue) -> Cue | None:
        if raw.kind == "page":
            page = self.kb.page(raw.value)
            if page is None:
                return None
            self._cue_path = page.path
            return Cue(at=raw.at, word=raw.word, path=_site_path(page.path))
        target = self.kb.page(self._cue_path) if self._cue_path is not None else None
        moved = self._cue_path is not None and self._cue_path != self._path
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
                return Cue(at=raw.at, word=raw.word, path=_site_path(found[0]), faq=question)
            path = _site_path(self._cue_path) if moved and self._cue_path else None
            return Cue(at=raw.at, word=raw.word, path=path, faq=question)
        # show: a heading of the page the visitor will be on, else those words.
        headings = (
            target.headings
            if moved and target
            else self._headings() or (target.headings if target else ())
        )
        heading = _match(raw.value, headings)
        text = None if heading else raw.value[:120]
        path = _site_path(self._cue_path) if moved and self._cue_path else None
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
            logger.info("clini: {} called with flat arguments; wrapping them", call.name)
            call = call.model_copy(update={"args": {"request": args}})
        return await super()._run(tool, call)

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Page→brain events, folded in silently: no floor taken, no turn."""
        event = CLINI_EVENTS.parse(msg)
        if event is None:
            return
        logger.info("clini: {} — {}", type(event).__voqal_event__, event)
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
            logger.warning("clini: switch to {} refused: {}", event.language, rejected)
            self.spoken = was
            session.dispatch(LanguageChanged(language=was))
            return
        logger.info("clini: language -> {} (toggle)", event.language)
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
            stt=SttConfig(language=language, patience=CLINI_PATIENCE),
            tts=TtsConfig(voice=VOICE, language=language),
        )

    # ─── Page → brain ───────────────────────────────────────────────────

    def apply_event(self, event: CliniEvent) -> str | None:
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
            case AgendaState():
                return self._agenda_changed(event)
            case LasikFormState():
                return self._lasik_changed(event)
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
            case CommandFailed() if event.command == "fill_agenda_patient" and "rut" in (
                event.reason.lower()
            ):
                # Not a failure: the booking keeps its fields locked until the
                # visitor has typed a valid RUT and it has looked them up.
                self._talk = None
                self._restore_idle()
                return (
                    "[The booking form keeps its other fields locked until the visitor types "
                    f"their RUT ({event.reason}). Ask them, in the language you speak, to type "
                    "their RUT in the field you marked, then fill in the rest. Do not say it "
                    "failed.]"
                )
            case CommandFailed():
                if event.command in _BOOKING_COMMANDS:
                    self._talk = None
                    self._agenda_asked = self._lasik_asked = False
                    self._restore_idle()
                return (
                    f"[That did not happen on the page ({event.command}: {event.reason}). "
                    "Tell the visitor plainly and offer what you can do instead; never say it "
                    "worked.]"
                )

    def _agenda_changed(self, event: AgendaState) -> str:
        """The booking's report, as a note; and, after a step he took there or
        once it is booked, the ask that has him talk it through."""
        before = self.agenda
        self.agenda = event
        note = _agenda_note(event)
        ask: str | None = None
        if event.step == "done":
            ask = (
                "The booking shows the hour as booked. Congratulate them in one sentence, say "
                "the day, the hour and the sede back as words, and offer help with the exam's "
                "preparation."
            )
        elif not self._agenda_asked:
            ask = None
        elif event.step == "search":
            ask = (
                "The booking is open at its first step and they have not spoken. Say in one "
                "sentence what it needs chosen, and ask them."
            )
        elif event.step == "results":
            new_times = bool(event.times) and (before is None or before.times != event.times)
            new_days = bool(event.days) and (
                before is None or before.step != "results" or before.days != event.days
            )
            if new_times:
                ask = (
                    "The booking shows the hours for the day they chose. Name two or three of "
                    "them, with the sede, as words, and ask which suits them."
                )
            elif new_days:
                ask = (
                    "The booking shows its open days and they have not spoken. Name two or "
                    "three of them as words, and ask which day suits them."
                )
            elif not event.days:
                ask = (
                    "The booking shows no free hours for this search. Say so in one sentence, "
                    "and offer another region, or WhatsApp agendamiento."
                )
        elif event.step == "booking":
            if before is None or before.step != "booking":
                ask = (
                    "The booking's patient form is open for the hour they chose. Say the day, "
                    "hour and sede back in one sentence, give the indications in a sentence if "
                    "there are any, and ask them to type their RUT first, in the field you mark "
                    "for them (fill_agenda_patient with focus_rut): the booking unlocks the "
                    "other fields once it has the RUT."
                )
            elif event.ready and not before.ready:
                ask = (
                    "Everything on the booking form is complete. Say so in one sentence, and that "
                    "AGENDAR is theirs to press."
                )
            elif event.invalid != before.invalid and event.invalid:
                ask = (
                    "Some of the booking form is still missing. Say in one sentence what is left. "
                    "The RUT and the consent box are theirs to fill in themselves."
                )
        if ask is not None:
            self._talk_through(ask)
        return note

    def _lasik_changed(self, event: LasikFormState) -> str:
        before = self.lasik
        self.lasik = event
        missing = ", ".join(event.missing) or "nothing"
        note = (
            f"[The free LASIK evaluation form: filled {', '.join(event.filled) or 'nothing'}; "
            f"still missing {missing}."
            + (
                " It is complete: the visitor presses “¡Agendar evaluación!” themselves.]"
                if event.valid
                else " The visitor types their RUT themselves.]"
            )
        )
        if self._lasik_asked and (before is None or before != event):
            self._talk_through(
                "The LASIK evaluation form is complete. Read the email back, and say "
                "“¡Agendar evaluación!” is theirs to press; a coordinator then calls them."
                if event.valid
                else "Part of the LASIK evaluation form is still missing. Say in one sentence "
                "what is left; the RUT they type themselves, in the field you marked."
            )
        return note

    def _read_in_screen(self) -> None:
        """The tabs and the page in front, once per change, ahead of what they say."""
        if self._tabs_unseen and len(self.tabs) > 1:
            listed = "; ".join(
                f"{t.tab_id}: {t.title or t.url}"
                + (" (the booking)" if _is_agenda(t.url) else "")
                + (" (in front)" if t.tab_id == self._active else "")
                for t in self.tabs
            )
            self._note(f"[The visitor's open Clini tabs — {listed}.]")
        self._tabs_unseen = False
        if not self._page_unseen or self.page is None:
            return
        self._page_unseen = False
        p = self.page
        where = (
            "the booking"
            if p.site == "agenda"
            else "a blog post on the site"
            if p.kind == "post"
            else "the site"
        )
        note = f"[The tab in front shows {where}: “{p.title or p.path}” ({p.url or p.path})."
        if p.headings:
            note += f" Its headings: {_clip(p.headings, _HEADINGS_IN_NOTE)}."
        if p.faqs:
            note += f" Its FAQs: {_clip(p.faqs, _FAQS_IN_NOTE)}."
        if p.plans:
            note += f" Its plans: {', '.join(p.plans)}."
        self._note(note + "]")

    def _has_agenda(self) -> bool:
        """Whether a booking tab is open: one reported itself, or the tab list has it."""
        return (
            self._site == "agenda"
            or self.agenda is not None
            or any(_is_agenda(t.url) for t in self.tabs)
        )

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

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        """Read and search Clini's knowledge, its prices, open hours and sedes;
        open and fill the booking and the LASIK form (never submitting either);
        open Clini's other links; move the visitor's tabs; switch language."""
        return [
            self.read_topic,
            self.search_site,
            self.quote_price,
            self.check_availability,
            self.find_branch,
            self.open_agenda,
            self.agenda_pick,
            self.fill_agenda_patient,
            self.fill_lasik_form,
            self.open_link,
            self.switch_tab,
            self.set_language,
        ]

    @needs_result_now
    async def read_topic(self, request: TopicRequest) -> str:
        """Read one of Clini's knowledge topics before answering from it."""
        topic = self.kb.topics.get(request.topic)
        if topic is None:
            return f"No topic '{request.topic}' is written yet: use search_site."
        return topic.text

    @needs_result_now
    async def search_site(self, request: SearchRequest) -> str:
        """Search www.clini.cl's pages, sections and FAQs. Each result names the
        page path and the section heading to take them to."""
        hits = self.kb.search(request.query, _SEARCH_HITS)
        if not hits:
            return f"Nothing on www.clini.cl matches '{request.query}'. Say so plainly."
        out: list[str] = []
        for h in hits:
            if h.kind == "faq":
                out.append(f"[FAQ on {h.path}] {h.title}\n  {h.snippet}")
            else:
                where = f", heading: {h.section}" if h.section else ""
                out.append(f"[page] {h.title} — path: {h.path}{where}\n  {h.snippet}")
        return "\n".join(out)

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

    async def switch_tab(self, request: TabRequest) -> str:
        """Bring another of the visitor's Clini tabs to the front."""
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
        logger.info("clini: language -> {} (asked)", request.language)
        return "ok"

    # ─── Prices, hours and sedes ────────────────────────────────────────

    @needs_result_now
    async def quote_price(self, request: PriceRequest) -> str:
        """The price of an exam or consultation from Clini's own price list: the
        Fonasa Nivel 1 copago and the particular price, whether it needs
        contrast, and its preparation. Call it first, before you answer."""
        query = request.query.strip()
        if not query:
            return "Not looked up: say which exam."
        source = "Clini's price list (cotizador), live"
        try:
            found = (await clini_api.search_prices(query))[:_PRICE_HITS]
        except clini_api.LookupFailed as e:
            logger.warning("clini: price search for {!r} failed: {}", query, e)
            found = []
            source = ""
        if not found:
            saved = offline_prices(self.kb, query, _PRICE_HITS)
            if saved:
                found = saved
                source = (
                    "the saved copy of Clini's price list (it may have changed; the cotizador "
                    "confirms it)"
                )
        if not found:
            return (
                f"No price found for '{query}'"
                + ("" if source else " (the price list did not answer)")
                + ". Say so, try other words for the exam, or offer the cotizador "
                "(open_link cotizador)."
            )
        lines = "\n".join(f"- {clini_api.price_line(p)}" for p in found)
        return (
            f"From {source}; prices in Chilean pesos, Fonasa is the Nivel 1 copago for tramos B, "
            f"C and D:\n{lines}"
        )

    @needs_result_now
    async def check_availability(self, request: AvailabilityRequest) -> str:
        """The first days with free hours for an exam on Clini's booking, and for
        one day (the first, or the one asked) each sede's first hours. Call it
        first, before you answer. Codes from the booking list."""
        service, error = self._service(request.servicio, request.prestacion, request.region)
        if service is None:
            return error
        prestacion = self._prestacion_for(service, request.prestacion)
        if prestacion is None:
            options = "; ".join(f"{p.code} {p.name}" for p in service.prestaciones)
            return f"Ask which one first: {service.name} has {options}."
        region = (request.region or _RM) if service.regions else None
        day = iso_day(request.day)
        try:
            found = await clini_api.availability(service.servicio, prestacion.code, region, day)
        except clini_api.LookupFailed as e:
            logger.warning("clini: availability for {} failed: {}", service.servicio, e)
            return (
                "The booking did not answer just now. Say so plainly, and offer to open the "
                "booking (open_agenda), where they can see the hours themselves."
            )
        what = f"{service.name} — {prestacion.name}"
        named = _region(service, region)
        where = f", {named.name if named else f'region {region}'}"
        if not found.days:
            return (
                f"No free hours for {what}{where if region else ''} in the next month. Say so, "
                "and offer another region or WhatsApp agendamiento."
            )
        days = "; ".join(_said_day(d) for d in found.days[:_AVAILABLE_DAYS])
        out = [f"{what}{where if region else ''}.", f"First days with free hours: {days}."]
        if day and found.day != day:
            out.append(
                f"{_said_day(day)} has no free hours; the next is {_said_day(found.day or '')}."
            )
        if found.day and found.centres:
            out.append(f"Hours on {_said_day(found.day)}, by sede:")
            for c in found.centres[:_AVAILABLE_CENTRES]:
                times = ", ".join(c.times[:_AVAILABLE_TIMES]) or "none left"
                addr = f" ({c.direccion})" if c.direccion else ""
                out.append(f"- {c.nombre}{addr}: {times}")
        elif found.day:
            out.append(f"The hours of {_said_day(found.day)} did not load; the booking shows them.")
        out.append("Say two or three of these as words. Times are Santiago's.")
        return "\n".join(out)

    @needs_result_now
    async def find_branch(self, request: BranchRequest) -> str:
        """Clini's sedes that match a comuna, city, region, name or service, with
        each one's address, hours and services. Call it first, before you answer."""
        found = self.kb.find_branches(request.query, _BRANCH_HITS)
        if not found:
            return (
                f"No sede matches '{request.query}'. Say so, and show /ubicaciones, where they "
                "can filter by region and comuna."
            )
        lines = "\n".join(f"- {branch_line(b)}" for b in found)
        return f"{lines}\nShow it with {{page: /ubicaciones}} and {{show: <the sede's name>}}."

    # ─── The booking and the LASIK form ─────────────────────────────────

    def _service(
        self, servicio: int, prestacion: int | None, region: int | None
    ) -> tuple[AgendaService | None, str]:
        """The servicio, checked against the booking list; else why not."""
        services = _services(self.kb)
        service = services.get(servicio)
        listed = "; ".join(f"{s.servicio} {s.name}" for s in services.values())
        if service is None:
            return None, (
                f"Not done: {servicio} is not a servicio of the booking. The booking list has: "
                f"{listed or 'nothing loaded; send them to /agendamiento'}."
            )
        if prestacion is not None and service.prestacion(prestacion) is None:
            options = "; ".join(f"{p.code} {p.name}" for p in service.prestaciones)
            return (
                None,
                f"Not done: {service.name} has no prestación {prestacion}. It has: {options}.",
            )
        if region is not None and service.regions and _region(service, region) is None:
            options = "; ".join(f"{r.code} {r.name}" for r in service.regions)
            return (
                None,
                f"Not done: {service.name} is not booked in region {region}. Regions: {options}.",
            )
        return service, ""

    @staticmethod
    def _prestacion_for(service: AgendaService, code: int | None) -> Prestacion | None:
        if code is not None:
            return service.prestacion(code)
        return service.prestaciones[0] if len(service.prestaciones) == 1 else None

    async def open_agenda(self, request: OpenAgendaRequest) -> str:
        """Open Clini's online booking for an exam in its own tab, and take the
        steps the visitor chose: the prestación, the day, the sede and the hour.
        Its steps come back to you from the page. It never presses AGENDAR."""
        service, error = self._service(request.servicio, request.prestacion, request.region)
        if service is None:
            return error
        prestacion = self._prestacion_for(service, request.prestacion)
        day = iso_day(request.day)
        when = hhmm(request.time)
        region = request.region if request.region not in (None, _RM) else None
        self._agenda_asked = True
        self._move(
            OpenAgenda(
                servicio=service.servicio,
                prestacion=prestacion.code if prestacion else None,
                region=region,
                day=day,
                centre=(request.centre or "").strip() or None,
                time=when,
            ),
            "agenda",
        )
        steps = [x for x in (day and _said_day(day), when, request.centre) if x]
        return (
            f"Opened the booking for {service.name}"
            + (f" — {prestacion.name}" if prestacion else "; they pick the prestación there")
            + (f", at {', '.join(steps)}" if steps else "")
            + ". Its steps come back to you. AGENDAR is theirs to press."
        )

    async def agenda_pick(self, request: AgendaPickRequest) -> str:
        """On the booking tab already open: pick the day, morning or afternoon,
        sede and hour the visitor chose, then Continuar. Its steps come back to you."""
        if not self._has_agenda():
            return "Not done: no booking tab is open. Use open_agenda first."
        day = iso_day(request.day)
        when = hhmm(request.time)
        if self.agenda is not None and day and self.agenda.days and day not in self.agenda.days:
            return (
                f"Not picked: {_said_day(day)} is not an open day on the booking. Open days: "
                f"{_clip([_said_day(d) for d in self.agenda.days], _DAYS_IN_NOTE)}."
            )
        if not (day or when or request.centre or request.period):
            return "Not picked: say which day, sede or hour."
        self._agenda_asked = True
        self._move(
            AgendaPick(
                day=day,
                time=when,
                centre=(request.centre or "").strip() or None,
                period=request.period,
            ),
            "agenda_pick",
        )
        return "Picked on the booking. Its next step comes back to you."

    async def fill_agenda_patient(self, request: PatientRequest) -> str:
        """Fill the booking's patient form with what the visitor said: name,
        surnames, birth date, sex, celular, email. What is filled stays. With
        focus_rut, ring the RUT field for them to type it. Never a RUT; never
        AGENDAR."""
        if not self._has_agenda():
            return "Not filled: no booking tab is open. Use open_agenda first."
        if self.agenda is not None and self.agenda.step != "booking":
            return (
                "Not filled yet: the patient form opens once they pick an hour (it shows "
                f"{_STEP_NAMES[self.agenda.step]} now)."
            )
        refused: list[str] = []
        given = {
            "name": request.name,
            "last_name": request.last_name,
            "maternal_last_name": request.maternal_last_name,
        }
        for key, value in given.items():
            if value and value.strip():
                self._patient[key] = " ".join(value.split())
        if request.birth_date:
            born = iso_day(request.birth_date)
            if born and born < clini_api.today().isoformat():
                self._patient["birth_date"] = born
            else:
                refused.append("birth date (as YYYY-MM-DD, in the past)")
        if request.sex:
            self._patient["sex"] = request.sex
        if request.phone:
            if (phone := mobile(request.phone)) is not None:
                self._patient["phone"] = phone
            else:
                refused.append("celular (nine digits starting with 9)")
        if request.email:
            if (address := email_address(request.email)) is not None:
                self._patient["email"] = address
            else:
                refused.append("email")
        p = self._patient
        self._agenda_asked = True
        self._move(
            FillAgendaPatient(
                name=p.get("name"),
                last_name=p.get("last_name"),
                maternal_last_name=p.get("maternal_last_name"),
                birth_date=p.get("birth_date"),
                sex=cast(Literal["F", "M", "O"] | None, p.get("sex")),
                phone=p.get("phone"),
                email=p.get("email"),
                focus_rut=request.focus_rut,
            ),
            "rut" if request.focus_rut and not any(given.values()) else "patient",
        )
        out = f"Filled on the booking form: {', '.join(p) or 'nothing yet'}."
        if "email" in p:
            out += f" Read the email back: {p['email']}."
        if "phone" in p:
            out += f" Read the celular back: {p['phone']}."
        if refused:
            out += f" Not filled, ask again: {', '.join(refused)}."
        if request.focus_rut:
            out += " The RUT field is ringed: they type it themselves."
        return out + " AGENDAR is theirs to press."

    async def fill_lasik_form(self, request: LasikRequest) -> str:
        """Fill the free LASIK evaluation form on /cirugia-lasik with what the
        visitor said: name, email, celular, previsión, where. It takes them to
        the form. What is filled stays. With focus_rut, ring the RUT field for
        them to type it. Never a RUT; never "¡Agendar evaluación!"."""
        refused: list[str] = []
        if request.name and request.name.strip():
            self._lasik_fields["name"] = " ".join(request.name.split())
        if request.email:
            if (address := email_address(request.email)) is not None:
                self._lasik_fields["email"] = address
            else:
                refused.append("email")
        if request.phone:
            if (phone := mobile(request.phone)) is not None:
                self._lasik_fields["phone"] = phone
            else:
                refused.append("celular (nine digits starting with 9)")
        if request.prevision:
            if (option := prevision_option(request.prevision)) is not None:
                self._lasik_fields["prevision"] = option
            else:
                refused.append(f"previsión (the form lists: {', '.join(_PREVISIONES)})")
        if request.location:
            if (place := lasik_location(request.location)) is not None:
                self._lasik_fields["location"] = place
            else:
                refused.append(
                    "where (the form lists: Tobalaba, Los Leones, Santa Lucía, Antofagasta, Temuco)"
                )
        f = self._lasik_fields
        self._lasik_asked = True
        self._move(
            FillLasikForm(
                name=f.get("name"),
                email=f.get("email"),
                phone=f.get("phone"),
                prevision=f.get("prevision"),
                location=f.get("location"),
                focus_rut=request.focus_rut,
            ),
            "lasik",
        )
        out = f"Filled on the LASIK evaluation form: {', '.join(f) or 'nothing yet'}."
        if "email" in f:
            out += f" Read the email back: {f['email']}."
        if refused:
            out += f" Not filled, ask again: {'; '.join(refused)}."
        if request.focus_rut:
            out += " The RUT field is ringed: they type it themselves."
        return out + " “¡Agendar evaluación!” is theirs to press."

    async def open_link(self, request: LinkRequest) -> str:
        """Open one of Clini's links in a new tab: a specialist's booking on
        Reservo (with the specialty), the lab or imaging results portal, the
        cotizador, telemedicine, WhatsApp agendamiento, or cancelling a booking.
        Only when they ask for it, or say yes to your offer."""
        found = link_url(request.kind, request.key)
        if found is None:
            keys = ", ".join(k for k in _LINKS.get(request.kind, {}) if k) or "none"
            return (
                f"Not opened: Clini has no {request.kind} link for '{request.key}'. Keys: {keys}."
            )
        key, url = found
        self._move(OpenLink(kind=request.kind, key=key, url=url), "link")
        return f"Opened {url} in a new tab."


__all__ = [
    "AgendaPick",
    "CliniBrain",
    "Cue",
    "FillAgendaPatient",
    "FillLasikForm",
    "FocusTab",
    "LanguageChanged",
    "Navigate",
    "OpenAgenda",
    "OpenFaq",
    "OpenLink",
    "ShowSection",
]
