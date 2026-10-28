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

import asyncio
import contextlib
import dataclasses
import json
import math
import random
import re
import time
from collections.abc import AsyncGenerator
from contextvars import ContextVar
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Literal, cast
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
from voqalize_demos.language_hold import HELD_NOTE, heard_language, holds_spanish, may_write_english

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

from . import clini_api
from . import knowledge as kb
from .app_events import (
    CLINI_EVENTS,
    AgendaState,
    CliniEvent,
    CommandDone,
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

#: GPT-6.1 Terra at low reasoning, for cost: OpenAI caches every prompt over
#: 1,024 tokens, where Gemini 3.8 Flash cached nothing under about 16k, so most
#: of each turn's input is read from the cache.
MODEL = "gpt-6.1-terra"
REASONING = "low"
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
#: While a form is open for them to dictate into (the booking's patient form,
#: the LASIK form): a name, a birth date or a celular is said in pieces, with
#: pauses, and at the call's patience each piece was a turn of its own that
#: cancelled the last (prod, 2026-10-22: nine of one call's turns had no
#: reply, and a celular came in four fragments).
FORM_PATIENCE = 9
#: A message this soon after the last one is the rest of the same thought.
_FRAGMENT_S = 4.0

#: How long a booking with neither days nor hours must stay that way before he
#: says it has none. A page Chrome is translating, or still loading after the
#: search, reports nothing for a moment and then its hours (dev call 5ff8b052,
#: "no free hours" twice, with hours on screen).
NO_HOURS_HOLD_S = 1.5

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
    lead: Literal["nod", "now"] | None = None
    """A page to open ahead of the words, not at them: a page load drops the
    call for seconds while it rejoins, so it is better spent before the answer
    than in it. ``nod``: once the nod in the air has played (or at once, if no
    voice starts); ``now``: at once."""


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
    booking has locked (an existing patient's) is left as it is. ``document``
    switches the form's RUT / Pasaporte toggle first (``passport`` for a
    visitor without a Chilean RUT). With ``focus_rut``, scroll to the document
    field, ring it and focus it: the visitor types their RUT or passport
    number. It never ticks the consent box and never presses AGENDAR, which it
    rings once the form is valid. The page answers ``command_done`` or
    ``command_failed``."""

    name: str | None = None
    last_name: str | None = None
    maternal_last_name: str | None = None
    birth_date: str | None = None
    """YYYY-MM-DD."""
    sex: Literal["F", "M", "O"] | None = None
    phone: str | None = None
    """Nine digits, starting with 9: the booking puts the +56 in front."""
    email: str | None = None
    document: Literal["rut", "passport"] | None = None
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
    """Only what the visitor said. There is no RUT or passport number here: they
    type it themselves."""

    name: str | None = Field(default=None, description="First name(s), as they said them.")
    last_name: str | None = Field(default=None, description="Apellido paterno.")
    maternal_last_name: str | None = Field(default=None, description="Apellido materno.")
    birth_date: str | None = Field(default=None, description="YYYY-MM-DD.")
    sex: Literal["F", "M", "O"] | None = Field(
        default=None,
        description="'F' femenino, 'M' masculino, 'O' otro o no informado. Only if they said "
        "it; never infer it from a name or a voice.",
    )
    phone: str | None = Field(
        default=None,
        description="Their celular, exactly the digits they said, never changed and never "
        "counted by you: a Chilean one is nine digits starting with 9, e.g. 912345678. The "
        "tool checks it.",
    )
    email: str | None = Field(default=None, description="As they said it, e.g. ana@correo.cl.")
    document: Literal["rut", "passport"] | None = Field(
        default=None,
        description="'passport' when they have no Chilean RUT (a foreigner): the form's "
        "Pasaporte button. 'rut' to switch back.",
    )
    focus_rut: bool = Field(
        default=False,
        description="Ring the RUT (or passport) field and put the cursor there, for them to type.",
    )


class LasikRequest(BaseModel):
    """Only what the visitor said. There is no RUT here: they type it themselves."""

    name: str | None = Field(default=None, description="Nombre y apellido.")
    email: str | None = Field(default=None, description="As they said it.")
    phone: str | None = Field(
        default=None,
        description="Their celular, exactly the digits they said, never changed: a Chilean "
        "one is nine digits starting with 9, e.g. 912345678.",
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
#: Laboratorio, whose search is the slowest the booking has (6 s and more), and
#: the ask that nearly always follows a lab price.
_LAB = 62


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


#: Digits as a visitor says them, in either language: one by one, or as
#: Chileans read a celular, in pairs ("nueve, ochenta y dos, cuarenta y seis").
_DIGIT_WORDS = {
    "zero": 0,
    "oh": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "cero": 0,
    "uno": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
}
_SPANISH_TEENS = {
    "diez": 10,
    "once": 11,
    "doce": 12,
    "trece": 13,
    "catorce": 14,
    "quince": 15,
    "dieciseis": 16,
    "diecisiete": 17,
    "dieciocho": 18,
    "diecinueve": 19,
    "veinte": 20,
    "veintiuno": 21,
    "veintidos": 22,
    "veintitres": 23,
    "veinticuatro": 24,
    "veinticinco": 25,
    "veintiseis": 26,
    "veintisiete": 27,
    "veintiocho": 28,
    "veintinueve": 29,
}
_SPANISH_TENS = {
    "treinta": 30,
    "cuarenta": 40,
    "cincuenta": 50,
    "sesenta": 60,
    "setenta": 70,
    "ochenta": 80,
    "noventa": 90,
}
#: Fewer digits than this read out of what they said is no number to check against.
_SAID_DIGITS_MIN = 8


def said_digits(text: str) -> str:
    """The digits in what the visitor said, written, spoken one by one, or
    spoken in Spanish pairs."""
    out: list[str] = []
    tokens = re.findall(r"\d+|[a-z]+", fold(text))
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.isdigit():
            out.append(token)
        elif token in _SPANISH_TENS:
            tens = _SPANISH_TENS[token]
            unit = tokens[i + 2] if i + 2 < len(tokens) and tokens[i + 1] == "y" else ""
            if unit in _DIGIT_WORDS and _DIGIT_WORDS[unit] > 0:
                out.append(str(tens + _DIGIT_WORDS[unit]))
                i += 2
            else:
                out.append(str(tens))
        elif token in _SPANISH_TEENS:
            out.append(str(_SPANISH_TEENS[token]))
        elif token in _DIGIT_WORDS:
            out.append(str(_DIGIT_WORDS[token]))
        i += 1
    return "".join(out)


def spaced(digits: str) -> str:
    """Digits one by one, as he reads them back."""
    return " ".join(digits)


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
- Before most replies the visitor has already heard a short acknowledgement of mine — "Claro.", "A ver.", or in English "Happy to help.", "Let me see." — so never open with one: your first word is the answer. No "great question", no repeating their question back.
- Spoken words only, apart from cues: no lists, no markdown, no symbols, never an exclamation mark.
- Write every number, price, date and hour as spoken words. Prices are Chilean pesos: "$88.280" is "ochenta y ocho mil doscientos ochenta pesos", in English "eighty-eight thousand two hundred and eighty pesos". "2026-10-23" is "el viernes veintitrés de octubre"; "07:40" is "a las siete y cuarenta de la mañana"; "15:00" is "a las tres de la tarde". Never say a code, a servicio number or a date in digits.
- Lines in square brackets come from their screen, not the visitor: the page in front, the booking's step, what a form still needs. Never read them out; use them.
- Always answer. A reply with no words leaves the visitor in silence.

# Spanish or English
You speak Spanish as a native of Latin America, and English. The call starts in Spanish unless the visitor chose English.
- Answer in Spanish. Move to English only when the visitor says at least two full sentences in English in one turn, or asks for English; then answer in English from that reply on, and if the visitor go back to Spanish, so do you. Speech recognition often hears a short Spanish reply or a Chilean name as English ("See" for "sí", "And lower net here" for "Lo Barnechea"): the visitor is still speaking Spanish, so answer in Spanish. Your voice follows the language you write.
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
- The booking moves — open_agenda, agenda_pick, fill_agenda_patient, fill_lasik_form — are not done when you call them: the page does them a moment later and tells you in square brackets. In the reply that calls one, say only what you are doing ("Te abro la agenda.", "Te selecciono las diez."), never that it is done. When the page's answer comes, say what it says happened: what is done, and plainly what is not.
- Never promise more to come ("let me check"): nothing comes after it.
- A question about the call itself — "can I speak English?", "can you hear me?", "who are you?" — gets an answer and nothing else: no booking tool, no form, no page.

# Prices
- For any exam price, call quote_price first, with the exam's name in Spanish. It returns the Fonasa Nivel 1 copago (for tramos B, C and D) and the particular price, whether it needs contrast, and the preparation. Say the Fonasa price first, then the particular one, as words. When it says the prices came from the saved list, say they may have changed and the cotizador confirms them.
- Consultations, LASIK and the convenios are priced on their pages: answer from the knowledge and the page.
- For a whole medical order, offer the cotizador (open_link cotizador): it reads the order and adds it up.
- CLINI has no home sampling online (a "domicilio" page the site once had is gone): never offer it.

# Booking an exam
Labs, imaging and cardiology are booked online on CLINI's booking, which opens in its own tab. Consultations are booked on Reservo, and the LASIK evaluation through its form.
- The booking list below gives each servicio and its prestaciones by code. Map what they need to a servicio and prestación; if a servicio has several and it is not clear which, ask, offering two or three.
- "Is there an hour tomorrow?", "when is the first one?": check_availability. Say two or three days, or for one day two or three hours with the sede, and ask which suits them. Never an hour it did not list.
- OFFER AN ONLINE HOUR ONLY AT A CENTRE check_availability OR THE BOOKING LISTED for that exam. find_branch lists every sede, but the booking takes only some of them for each exam: never offer to book a sede it did not list. A laboratorio or Toma de Muestras sede it did not list takes walk-ins by order of arrival during its hours, with no booking: say that, and offer the nearest centre the booking listed.
- When the booking tab already shows the days and hours (the latest booking line in square brackets lists them), answer from that line, as their screen shows it, without check_availability. The days and hours on their screen are the truth.
- WITH THE BOOKING OPEN ON THAT EXAM, A DAY OR AN HOUR IS agenda_pick. "Can you do it for the twenty-eighth?", "anything on Friday?", "ten in the morning": agenda_pick with it, which shows that day's hours on their screen, and its answer comes back to you. check_availability is for an exam the booking is not showing. Never open_agenda again for the exam it shows.
- One booking move at a time: when a tool says the booking is still opening or working on the last step, what you asked for follows by itself. Say so in a few words, and never call it again.
- Say the booking has no free hours only when the booking line says it lists no open days and no hours. A line whose days could not be read but that lists hours has hours.
- When they want to book, open_agenda with what they chose: the servicio and prestación, and the day, sede and hour once they picked them. A sede they named goes in centre, as the booking titles it. It opens the booking in its own tab and takes those steps on it. That reply moves nothing on the site: no page or show cue in it. On the booking tab, a later choice is agenda_pick. While the booking is in front, cue the site only when they ask for a page of it. The booking's steps come back to you in square brackets: talk them through.
- At the patient form, ask them first to type their RUT: fill_agenda_patient with focus_rut rings the field. The form also takes a passport: a visitor with no Chilean RUT (a foreigner, a first visit) chooses Pasaporte, and fill_agenda_patient with document passport presses it for them. Say both options exist when they hesitate. The booking unlocks the other fields once it has a valid RUT or passport number (for a patient it knows, it fills them itself). Then fill_agenda_patient with what they tell you: name, surnames, birth date, sex, celular, email. What is filled stays; you only add.
- THE RUT OR PASSPORT IS THEIRS TO TYPE. Never ask them to say it, never repeat one, never write one anywhere. When it is time, fill_agenda_patient with focus_rut and say: "Escribe tu RUT, o tu pasaporte, en el campo que marqué." The consent box is theirs to tick, too. Online booking does not need a Chilean RUT: never send a visitor to WhatsApp for lack of one.
- A celular is the digits they said, never changed. NEVER COUNT OR JUDGE THE DIGITS YOURSELF: pass exactly what they said to fill_agenda_patient (or fill_lasik_form), even when it looks too long or too short; it checks them, and tells you what is wrong and how many digits it got. Only then, if it refused them, say the form needs a Chilean mobile, nine digits starting with 9, and ask again. Never drop, add or reorder a digit to make it fit. Fill a celular or an email the moment they say it, then read it back in the same reply, the celular digit by digit; if they correct it, fill it again with what they say.
- Sex goes in the form only when they said it ("femenino", "masculino", "otro"). Never guess it from a name or a voice: ask.
- AGENDAR STAYS THEIRS TO PRESS, always. When the form is complete, say what is filled and that they press AGENDAR themselves. Never say the hour is booked, reserved or ready ("quedó lista tu hora", "está reservada", "ya tienes tu hora", "you're booked") until the booking shows it is done: before that, say "Dejé seleccionada la hora…" and that AGENDAR is theirs.
- Read out the indications the booking shows (fasting, what to bring) in a sentence or two, in your own words.

# Consultations, results and other links
- Medical consultations (traumatología, medicina general, medicina interna, psicología, urología, nutricionista, neurocirugía, cirugía general, matrona, kinesiología, medicina deportiva) are booked on Reservo: open_link reservo with the specialty. Telemedicine is open_link telemedicine.
- Results: laboratory results are open_link results_lab; imaging results are open_link results_imaging. They sign in with their RUT there, themselves. You never see or read a result.
- A booking to cancel is open_link cancel_booking. WhatsApp agendamiento is open_link whatsapp.
- Open a link only when they ask for it, or say yes to your offer. Say you opened it in a new tab.

# LASIK
- The evaluation is free, for people from eighteen to sixty, and booked with the form on /cirugia-lasik: a coordinator calls them back to choose the day. It is not on the online booking.
- When they want it, fill_lasik_form with what they say: name and surname, email, celular, previsión, and where (Tobalaba, Los Leones, Santa Lucía, Antofagasta or Temuco). It takes them to the form. Fill the email and celular as soon as they say them, then read them back, as for the booking. For the RUT, fill_lasik_form with focus_rut, and they type it. "¡Agendar evaluación!" stays theirs to press.

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
#: Not "which day?": a call can start there at any step, the patient form too
#: (dev call 03a45037 opened on the form with "¿Qué día te queda bien?").
_AGENDA_GREETING: dict[Lang, str] = {
    "es": "Te ayudo a elegir tu hora y completar la reserva aquí mismo. ¿En qué te ayudo?",
    "en": "I can help you pick your time and finish the booking right here. What can I help with?",
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
    # A booking move is not done when the turn ends: the page answers later,
    # so its line says what he is doing, never that it is done.
    "agenda": {
        "en": "I'm opening the booking in its own tab.",
        "es": "Te abro la agenda en su propia pestaña.",
    },
    "agenda_pick": {"en": "I'm picking that on the booking.", "es": "Te lo marco en la agenda."},
    "already": {
        "en": "That's already selected on your screen.",
        "es": "Eso ya está seleccionado en tu pantalla.",
    },
    "queued": {
        "en": "I'll do that as soon as the booking is ready.",
        "es": "Lo hago apenas la agenda esté lista.",
    },
    "patient": {
        "en": "I'm filling that in on the booking form.",
        "es": "Te lo completo en el formulario de la agenda.",
    },
    "rut": {
        "en": "Please type your RUT or passport number in the field I've marked.",
        "es": "Escribe tu RUT o pasaporte en el campo que marqué.",
    },
    "lasik": {
        "en": "I'm filling that in on the evaluation form.",
        "es": "Te lo completo en el formulario de la evaluación.",
    },
    "link": {"en": "I've opened it in a new tab.", "es": "Lo abrí en una pestaña nueva."},
}

#: The patient form's fields as he names them, for his line on a fill.
_FIELD_NAMES: dict[Lang, dict[str, str]] = {
    "es": {
        "name": "tu nombre",
        "last_name": "tu apellido paterno",
        "maternal_last_name": "tu apellido materno",
        "birth_date": "tu fecha de nacimiento",
        "sex": "tu sexo",
        "phone": "tu celular",
        "email": "tu correo",
    },
    "en": {
        "name": "your name",
        "last_name": "your first surname",
        "maternal_last_name": "your second surname",
        "birth_date": "your birth date",
        "sex": "your sex",
        "phone": "your celular",
        "email": "your email",
    },
}
_DIGIT_NAMES: dict[Lang, tuple[str, ...]] = {
    "es": ("cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve"),
    "en": ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"),
}
#: What he asks when a fill turned a field down; "" when it took nothing at all.
_ASK_AGAIN: dict[str, dict[Lang, str]] = {
    "phone": {
        "es": "Ese celular no calza: el formulario pide uno chileno, de nueve dígitos, que "
        "empiece con nueve. ¿Me lo repites?",
        "en": "That celular doesn't fit: the form needs a Chilean one, nine digits starting "
        "with nine. Could you say it again?",
    },
    "email": {
        "es": "No me quedó claro tu correo. ¿Me lo deletreas?",
        "en": "I didn't quite get your email. Could you spell it for me?",
    },
    "birth_date": {
        "es": "¿Me repites tu fecha de nacimiento?",
        "en": "Could you tell me your birth date again?",
    },
    "sex": {
        "es": "Para el formulario, ¿tu sexo es femenino, masculino u otro?",
        "en": "For the form, is your sex female, male or other?",
    },
    "": {
        "es": "Todavía no tengo ese dato para el formulario. ¿Me lo repites?",
        "en": "I didn't get that for the form yet. Could you say it again?",
    },
}
#: The words that say each of the form's sexes, folded.
_SAID_SEX: dict[str, re.Pattern[str]] = {
    "M": re.compile(r"\b(?:masculino|hombre|varon|male|man)\b"),
    "F": re.compile(r"\b(?:femenino|mujer|female|woman)\b"),
    "O": re.compile(r"\b(?:otro|otra|other|no binari\w*|prefiero no)\b"),
}


def _and(lang: Lang, items: list[str]) -> str:
    """``items`` as a spoken list: "a, b y c", "a, b and c"."""
    if len(items) < 2:
        return "".join(items)
    return f"{', '.join(items[:-1])} {'y' if lang == 'es' else 'and'} {items[-1]}"


#: What a reply that only promises more says: nothing comes after it.
_PROMISE = re.compile(
    r"\b(?:just |one |un )?(?:moment|momento|momentito|second|segundo)\b"
    r"|\blet me (?:see|check|look)(?: (?:that|into it|at that))?\b|\bdéjame ver\b|\ba ver\b",
    re.IGNORECASE,
)

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
        # Not "gracias por avisarme": a plain request read as a statement
        # ("Me gustaría cotizar mi examen.") was thanked for the news (prod,
        # 2026-10-22).
        "statement": ("Entendido, eso me ayuda.", "Claro."),
    },
}
ACK_RATE = 0.75
#: After a nod, how long the model may stay quiet before he holds the floor. A
#: booking move or a lookup turn takes five or six seconds from India; at 4 s
#: nearly every such turn said "Just a moment." (dev call 2fd742d5).
ACK_HOLD_AFTER_S = 5.75
#: With no nod, the dead air a turn may leave before his first line: a late nod
#: for what they said, or a hold line. Without it, a turn the nod skipped sat in
#: ten seconds of silence (dev call 2fd742d5, T23 to T25). 3.2 s, not 2.5: the
#: model's first words come at 2.3 to 2.8 s, so at 2.5 the hold line won that
#: race by a few hundred milliseconds and the visitor sat through two seconds of
#: filler before an answer that was ready (11 of 33 hold lines on prod,
#: 2026-10-22, were followed by the answer within a second).
HOLD_WITHOUT_NOD_S = 3.2
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


#: A visitor saying what they want, which the shared reading takes for a
#: statement ("Me gustaría cotizar mi examen.") or, after a leading "No", for a
#: correction ("No, yo quiero agendar una resonancia."): a request, here.
_WANTS = re.compile(
    r"\b(?:me gustaria|quiero|quisiera|necesito|i'?d like|i want|i need|i would like)\b"
)
#: Thanks and goodbyes, which no hold line fits: "Dame un momento mientras lo
#: busco." answered "Voy a completar el resto. Muchas gracias." (prod, 2026-10-22).
_CLOSING = re.compile(r"\b(?:gracias|adios|chao|chau|thanks|thank you|bye|goodbye)\b")


def nod_kind(text: str) -> Kind | None:
    """What the visitor's words ask of him, for his nod: the shared reading,
    with what they want read as a request."""
    kind = classify(text, _ACK_WORDS)
    if kind in ("statement", "correction") and _WANTS.search(fold(text)):
        return "request"
    return kind


def is_closing(text: str) -> bool:
    """Whether ``text`` thanks him or says goodbye, and asks nothing more."""
    return "?" not in text and bool(_CLOSING.search(fold(text)))


class _Nods(Acknowledger[Lang]):
    """The shared acknowledger, reading the visitor with :func:`nod_kind`."""

    def line(self, text: str, spoken: Lang) -> str | None:
        kind = nod_kind(text)
        lines = self.lines.get(spoken, {}).get(kind) if kind else None
        if not lines or self.rng.random() >= self.rate:
            return None
        return self._pick(lines)


def _late_nod(text: str, spoken: Lang) -> str | None:
    """The nod :class:`Acknowledger` would have chosen, had the dice said yes."""
    kind = nod_kind(text)
    lines = _ACK_LINES[spoken].get(kind) if kind else None
    return random.choice(lines) if lines else None


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


#: Set while a turn runs with tools off (``ToolChoice.NONE``): a call the model
#: makes anyway is not run. Per turn, not per brain: turns overlap. A model does
#: not always honour the mode, and the SDK runs what comes back: on prod
#: (2026-10-22) an idle turn with tools off sent an ``agenda_pick`` that took
#: the patient form down and put it back.
_TOOLS_OFF: ContextVar[bool] = ContextVar("clini_tools_off", default=False)


async def _tools_off(turn: AsyncGenerator[Speech, None]) -> AsyncGenerator[Speech, None]:
    """``turn``, a request made with tools off, with :data:`_TOOLS_OFF` set."""
    token = _TOOLS_OFF.set(True)
    try:
        async for event in turn:
            yield event
    finally:
        await turn.aclose()
        # Closed from another context, the token cannot be reset, and that
        # context's value went with the task that set it.
        with contextlib.suppress(ValueError):
            _TOOLS_OFF.reset(token)


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


#: The words of a centre's or a sede's name that name no one place.
_PLACE_STOP = frozenset(
    # A word list reads as words, so it stays a split string.
    """centro centros salud sede sedes toma tomas muestra muestras clini metro mall plaza
    diagnostico laboratorio express astra imagenes resonancia cardiologia agenda
    """.split()  # noqa: SIM905
)


def _places(name: str) -> set[str]:
    """The words of a centre's name that tell it from the others, folded:
    "TM | MALL FLORIDA" is {"florida"}, "Toma de Muestras Tobalaba" {"tobalaba"}."""
    return {w for w in re.findall(r"[a-z]+", fold(name)) if len(w) > 3 and w not in _PLACE_STOP}


def _places_in(text: str, vocabulary: set[str]) -> set[str]:
    """The place words of ``vocabulary`` that ``text`` says."""
    return set(re.findall(r"[a-z]+", fold(text))) & vocabulary


def _same_centre(want: str, shown: str) -> bool:
    """Whether the centre ``want`` is the one ``shown`` names."""
    return bool(_places(want) & _places(shown)) or norm(want) in norm(shown)


def _phrase(text: str) -> str:
    """``text`` as folded words and numbers, one space apart: "$54.990" is "54 990"."""
    return " ".join(re.findall(r"[a-z0-9]+", fold(text)))


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
#: Words of booking, folded: a reply to them opens the booking in its own tab,
#: so no page of the site is opened ahead of it (:meth:`CliniBrain._lead`).
_BOOKING_WORDS = re.compile(
    r"\b(?:agend\w*|reserv\w*|horas?|citas?|book\w*|appointments?|slots?)\b"
)

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


#: Words that ask him to move the site itself, whichever tab is in front.
_SITE_MOVE = re.compile(
    r"\b(?:home ?page|main (?:site|website|page)|website|web ?site|site|page|pagina|sitio"
    r"|inicio|go back|take me|llevame|vuelve|volver|abre|open)\b",
    re.IGNORECASE,
)


def asks_site_move(text: str) -> bool:
    """Whether ``text`` asks for a page of the site: "go back to the homepage".
    A question about an exam is not one: asked on the booking, it is answered
    there (dev call 5ff8b052, pulled off the booking by a page cue)."""
    return bool(_SITE_MOVE.search(fold(text)))


#: A question about the call itself, which no booking tool answers: "can I speak
#: in English?" made a ``fill_agenda_patient`` on dev call 03a45037.
_ABOUT_THE_CALL = re.compile(
    r"\b(?:can you hear me|are you there|me escuchas|me oyes|who are you|quien eres"
    r"|are you (?:a )?(?:bot|robot|real|human|ai)|eres (?:un )?(?:bot|robot|humano))\b",
    re.IGNORECASE,
)


def about_the_call(text: str) -> bool:
    """Whether ``text`` is only about the call: its language, or him."""
    short = len(text.split()) <= 12
    return short and (asks_call_language(text) or bool(_ABOUT_THE_CALL.search(fold(text))))


def asked_page(text: str) -> str | None:
    """The site page for what ``text`` asks about, or ``None``. "The pricing
    tab" is a tab to switch to, not a page to open over the one in front, and
    "can you speak Spanish?" is a request about this call, not a page."""
    named = asked_pages(text)
    return named[0] if named else None


def asked_pages(text: str) -> list[str]:
    """Every site page ``text`` names, the first named first."""
    if _ASKED_TAB.search(fold(text)) or asks_call_language(text):
        return []
    said = fold(text)
    named = [(m.start(), path) for rx, path in _ASKED_PAGES if (m := rx.search(said))]
    return [path for _, path in sorted(named)]


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
#: The commands whose tool waits for the page's ``command_done`` / ``command_failed``.
_CONFIRMED_COMMANDS = frozenset(
    {"open_agenda", "agenda_pick", "fill_agenda_patient", "fill_lasik_form"}
)
#: What a lookup adds when the booking is already open on that exam: a day or
#: an hour asked for there is picked on it (dev call 2fd742d5, "can you do it
#: for the twenty-eighth?" looked up again, with the booking open on it).
_PICK_HINT = (
    "\nThe booking tab is open on this exam: to show or select a day or an hour there, call "
    "agenda_pick with it, which shows that day's hours on their screen. Never open_agenda again "
    "for this exam."
)
#: The moves on the booking's tab, one at a time: a pick raced an open still
#: under way, and the open then failed on the pick's day (dev call 2fd742d5).
_AGENDA_MOVES = frozenset({"open_agenda", "agenda_pick", "fill_agenda_patient"})
#: How long a move may take on the page before the next one stops waiting for
#: it: an open searches up to 20 s and waits for the hours (10 to 28 s on dev
#: call 2fd742d5); a pick or a fill takes a second or a few.
_MOVE_TAKES_S = {"open_agenda": 30.0, "": 8.0}
#: A unit of his not reported played this long after it began is taken as done.
_PLAYOUT_MAX_S = 30.0
_DAYS_IN_NOTE = 31
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
    if event.month and event.step == "results":
        note += f" Month on screen: {event.month}."
    if event.days:
        note += f" Open days: {_clip([_said_day(d) for d in event.days], _DAYS_IN_NOTE)}."
    elif event.step == "results" and event.times:
        note += " The calendar's open days could not be read; the hours below are on screen."
    elif event.step == "results":
        note += " No open days or hours are listed right now."
    if event.centres:
        note += f" Sedes listed: {_clip(event.centres, 12)}."
    if event.times:
        on = f" on {_said_day(event.day)}" if event.day else ""
        at = f" at {event.centre}" if event.centre else " at the open sede"
        note += f" Hours{at}{on}: {_clip(event.times, _TIMES_IN_NOTE)}."
    elif event.day and event.step == "results":
        note += f" Day in view: {_said_day(event.day)}."
    if event.selected:
        note += f" Selected: {event.selected}."
    if event.indications:
        note += f" Indications: {event.indications[:600]}"
        note += "" if note.endswith(".") else "."
    if event.step == "booking":
        document = "passport (Pasaporte)" if event.document == "passport" else "RUT"
        note += f" The form is set to the {document}."
        missing = ", ".join(event.invalid) or "nothing"
        note += f" Still missing or invalid: {missing}."
        note += (
            " AGENDAR is enabled: the visitor presses it themselves."
            if event.ready
            else " The RUT or passport number, and the consent box, are the visitor's to fill in."
        )
    return note + "]"


#: What the page says when the patient form is still locked behind the RUT.
_LOCK_WORDS = ("rut", "passport", "pasaporte", "document", "locked")
_LOCKED_NOTE = (
    "Nothing was filled yet: the booking form opens its other fields only once the visitor "
    "has typed their RUT, or chosen Pasaporte and typed their passport number. Say so "
    "plainly, ask them to type it in the field you marked, and fill in the rest once it "
    "opens: what they told you is kept"
)


def _locked(reason: str) -> bool:
    return any(w in reason.lower() for w in _LOCK_WORDS)


# ─── The brain ─────────────────────────────────────────────────────────────────


class CliniBrain(OpenAIBrain):
    """One per session. Javier: Clini's knowledge, its pages, and a mirror of
    the visitor's tabs, in Spanish or English."""

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
        self._heard_at = float("-inf")
        #: The language he speaks now, and the toggle's written confirmation
        #: of a switch, said at the start of his next turn.
        self.spoken: Lang = OPENING
        #: Whether the visitor chose the language, which then holds whatever
        #: they speak; until they do, it follows what they speak.
        self._chosen = False
        self._last_heard = ""
        self._confirm: str | None = None
        self._fallback = FallbackLine()
        self._ack: Acknowledger[Lang] = _Nods(
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
        #: Whether this reply opened the booking: the site's page cues after it
        #: would pull the visitor off the tab it just brought to the front (dev
        #: call 5ff8b052, "you went back to the main website, why?").
        self._opened_agenda = False
        #: Whether the visitor's last words asked for a page of the site, the
        #: one thing that moves the site while the booking is in front.
        self._asked_site = False
        #: What the visitor said lately, for the digits of a celular: the model
        #: may not reshape them to fit (dev call 03a45037, 8147514179 sent as
        #: 914751417).
        self._heard: list[str] = []
        #: The booking moves sent and not yet answered by the page, and the
        #: answers that came in since his last turn: talked through together,
        #: once, in the next short quiet spell.
        self._sent: dict[str, float] = {}
        self._outcomes: list[str] = []
        #: The booking move asked for while another was still under way on the
        #: page, sent once that one answers: one at a time, never two at once
        #: (dev call 2fd742d5, a pick that raced the booking still opening).
        self._queued: Action | None = None
        #: His turns under way, and his units of speech not yet played out: the
        #: idle window is shortened for a talk-through only when both are none,
        #: or the short quiet spell cuts his own reply (dev call 2fd742d5, T27).
        self._turns = 0
        self._playing = 0
        self._played_at = 0.0
        self._idle_deferred = False
        #: Lookups that missed the tool's deadline and are still running.
        self._late: set[asyncio.Task[None]] = set()
        self._no_hours: asyncio.TimerHandle | None = None
        #: The identity document the visitor said they use: ``passport`` for one
        #: with no Chilean RUT.
        self._document: Literal["rut", "passport"] | None = None
        #: The page opened ahead of this turn's answer, while his nod played
        #: (:meth:`_lead`), as the crawl names it; the reply's own cue for it is not
        #: sent again.
        self._led: str | None = None
        #: The day, hour and centre the last open_agenda or agenda_pick asked
        #: the booking for: a pick for the same, while it is on its way, is not
        #: sent again.
        self._sent_pick: tuple[str | None, str | None, str | None] | None = None
        #: The centres the booking listed for each (servicio, prestación): the
        #: only ones an hour can be booked at online.
        self._centres: dict[tuple[int, int], list[str]] = {}
        #: What he said in his last reply, for the sede he offered.
        self._last_said = ""
        #: The recognizer's patience now: raised while a form is being dictated.
        self._patience = CLINI_PATIENCE

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
                stt=SttConfig(language=self.spoken, patience=self._patience),
                tts=TtsConfig(voice=VOICE, language=self.spoken),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
            )
        )
        # The connections to Clini's hosts, opened while he greets.
        clini_api.warm()
        logger.info(
            "clini: session start on {} {} in {}{}",
            self._site,
            self._path,
            self.spoken,
            " (chosen)" if self._chosen else "",
        )
        if self._chosen:
            self._note(_chosen_note(self.spoken, "before the call"))

    async def on_session_end(self, session: Session) -> None:
        """A lookup still running for this call has no one left to tell."""
        for task in self._late:
            task.cancel()
        await super().on_session_end(session)

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
        self._last_heard = msg.text
        heard = None if self._chosen else heard_language(msg.text, self.spoken, language_of)
        if heard is not None and heard != self.spoken:
            await session.configure(self._speaking(heard))
            logger.info("clini: language -> {} (heard)", heard)
        if holds_spanish(msg.text, self.spoken, language_of):
            logger.info("clini: held in Spanish: {!r}", msg.text)
            self._note(HELD_NOTE)
        self._talk = None
        self._led = None
        # They spoke first: the page's answers are in the context as notes,
        # and he answers them with what they said.
        self._outcomes.clear()
        self._idle_deferred = False
        # What he said before has played out, or they spoke over it.
        self._playing = 0
        self._nudges = 0
        self._heard = [*self._heard[-3:], msg.text]
        self._asked_site = asks_site_move(msg.text)
        # A reply cut off before it said a word keeps its page for the next one:
        # "use cases in sales", then "mm-hmm" while he was still thinking.
        # A request to switch language shows nothing, not even the page a
        # reply cut off before had kept.
        self._backstop = (
            None if asks_call_language(msg.text) else asked_page(msg.text) or self._backstop
        )
        self._restore_idle()
        self._read_in_screen()
        # Kept open between questions: a lookup never pays for the connection.
        clini_api.warm()
        now = time.monotonic()
        fragment, self._heard_at = now - self._heard_at < _FRAGMENT_S, now
        nod = None if fragment else self._ack.line(msg.text, self.spoken)
        floor: Floor[Lang] = self._ack
        lead = self._lead(msg.text)
        if nod is not None:
            logger.info("clini: ack {!r}", nod)
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
        if lead is not None:
            self._send_lead(lead, "nod" if nod is not None else "now")
        working = nod is not None
        # Thanks or a goodbye: no hold line fits it, and the model's own short
        # reply follows in a couple of seconds.
        closing = nod is None and is_closing(msg.text)

        def answered() -> None:
            nonlocal working
            if working:
                working = False
                _avatar_state(session, None)

        try:
            turn = super().on_user_message(session, msg)
            if not closing:
                turn = hold_the_floor(self, floor, lambda: self.spoken, turn, answered)
            async for event in turn:
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

        A result the page produced after his turn is put in the context at once
        and the idle window shortened, so a reading visitor hears it from him
        here. Otherwise an ordinary quiet spell: a nudge, twice, then silence.

        He only talks here: the turn runs with tools off, so a quiet spell can
        never send a booking move of its own (dev call 2fd742d5, T27 filled the
        form again from a talk-through, on a form that had just been reset)."""
        self._restore_idle()
        self._backstop = None
        self._led = None
        self._asked_site = False
        if (ask := self._take_ask()) is not None:
            self._agenda_asked = self._lasik_asked = False
            self._note(ask)
            return self._reply(session, ToolChoice.NONE)
        if self._confirm is not None:
            line, self._confirm = self._confirm, None
            return say_line(self, line)
        if self._nudges >= _IDLE_NUDGES:
            return _silence()
        if (running := self._busy()) is not None:
            # The booking is still taking the step he sent: a nudge now said it
            # was open, and asked for the day it was on its way to (prod,
            # 2026-10-22). Its answer is talked through when it comes.
            logger.info("clini: quiet while {} is under way; no nudge", running)
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
        return self._reply(session, ToolChoice.NONE)

    def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        return self._reply(session, None)

    async def _reply(
        self, session: Session, tools: ToolChoice | None
    ) -> AsyncGenerator[Speech, None]:
        """The model's turn, with its screen cues taken out of the speech and
        sent to the page (:mod:`.cues`); ``tools`` limits it (``None``: any).

        If it moved the page and said nothing, he says the move's written line
        at once (:func:`landed`), in the language he speaks: the model never
        writes words before a booking move (ten times in ten on dev call
        2fd742d5), and asking it again cost a second round trip of silence, 2.3
        to 5.2 s, every time. A turn that came back with nothing at all — no
        words, no move — is asked once more, with tools off: on dev call
        67d16b5d three such turns left the visitor with a nod and then silence
        until they spoke again.

        A language switched on the toggle is confirmed first, in the new
        language. A unit is opened only once its first words are known, so the
        voice follows the language the model chose to write in."""
        if (line := self._confirm) is not None:
            self._confirm = None
            async for event in say_line(self, line):
                yield event
        self._cue_path = self._path if self._site == "site" else None
        if self._led is not None:
            # The page opened ahead of the answer: the reply's cues are for it.
            self._cue_path = self._led
        self._paged = False
        self._shown = None
        self._opened_agenda = False
        said = ""
        model = (
            super().respond(session) if tools is None else self.respond_with(session, tools=tools)
        )
        if tools is not None and tools.mode == "none":
            model = _tools_off(model)
        turn = self._fallback.speak_if_silent(self, model)
        async for event in self._spelled(self._written(session, self._cued(turn))):
            if isinstance(event, SpeechChunk):
                said += event.text
            yield event
        # Words, and not only a promise: on Explora's dev call ed9846d5 the whole
        # reply was "One moment.", and the visitor sat in silence.
        if not _PROMISE.sub("", _CUE_TEXT.sub(" ", said)).strip(" .,!?¡¿…"):
            logger.warning("clini: the model returned nothing; asking once more")
            again = self._written(session, self._cued(self._talk_now(session)))
            async for event in self._spelled(again):
                if isinstance(event, SpeechChunk):
                    said += event.text
                yield event
        self._last_said = said

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
        units = 0
        try:
            async for event in turn:
                if isinstance(event, SpeechStart):
                    parser = CueParser(self._auto_cues)
                    units += 1
                elif isinstance(event, SpeechChunk):
                    text, raw = parser.feed(self._with_backstop(event.text))
                    for cue in raw:
                        self._send_cue(cue, first_unit=units <= 1)
                    if text:
                        yield SpeechChunk(text)
                    continue
                else:  # SpeechEnd
                    rest, raw = parser.flush()
                    for cue in raw:
                        self._send_cue(cue, first_unit=units <= 1)
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
        if "{" in chunk or self._site != "site" or self._opened_agenda or path == self._path:
            return chunk
        logger.info("clini: the reply has no cue; showing {} first", path)
        return f"{{page: {path}}}{chunk}"

    def _lead(self, text: str) -> str | None:
        """The page to open while his nod plays, ahead of the answer: the one
        the visitor asked about (:func:`asked_page`), which his reply shows
        first in any case (:meth:`_with_backstop`).

        A page of the site is a full page load, and the call drops for 3 to 6 s
        while it rejoins (prod, 2026-10-22, from Chile). Opened at the answer's
        first word, that silence fell on the answer, with the mic dead; opened
        here it falls on the nod and the model's thinking. Not for a booking
        ask, whose reply opens the booking's own tab and moves no page, nor for
        a question about the call."""
        path = self._backstop
        if (
            path is None
            or self._site != "site"
            or path == self._path
            or self.kb.page(path) is None
            or _BOOKING_WORDS.search(fold(text))
            or about_the_call(text)
            # What they ask may be answered on the page they are on: "¿Cuánto
            # sale con Fonasa la resonancia?" on the resonance page names it.
            or self._path in asked_pages(text)
            or self._section_for(text.rstrip(" ?!."), self._path) is not None
        ):
            return None
        return path

    def _send_lead(self, path: str, when: Literal["nod", "now"]) -> None:
        self._led = path
        logger.info("clini: opening {} ahead of the answer ({})", path, when)
        self.session.dispatch(Cue(at="", path=_site_path(path), lead=when))

    def _send_cue(self, raw: RawCue, *, first_unit: bool = False) -> None:
        """Check a cue against the site, as the tools do, and send it; one that
        names nothing real is dropped and logged rather than reaching the page.

        The page a reply opens first, at its very start, is opened at once
        (``lead="now"``) rather than at its first words: the page load drops
        the call while it rejoins, and the opening words were cut by it."""
        if self.spoken == "es" and raw.at:
            raw = dataclasses.replace(raw, at=_anchor_for_voice(raw.at))
        if self._opened_agenda:
            # The booking is coming to the front in its own tab: a move on the
            # site now would take the visitor off it.
            logger.info(
                "clini: cue {} {!r} dropped: the booking opened this reply", raw.kind, raw.value
            )
            return
        cue = self._resolve_cue(raw)
        if (
            cue is not None
            and cue.path is not None
            and self._site == "agenda"
            and not self._asked_site
        ):
            logger.info("clini: cue {} {!r} dropped: the booking is in front", raw.kind, raw.value)
            return
        if cue is not None and raw.kind == "page" and self._led is not None:
            led, self._led = self._led, None
            if cue.path == _site_path(led):
                logger.info("clini: {} was opened ahead of the answer", led)
                self._paged = True
                return
        if cue is not None and not self._fits(raw, cue):
            logger.info(
                "clini: cue {} {!r} dropped: it shares no word with {!r}",
                raw.kind,
                raw.value,
                raw.sentence,
            )
            return
        first = raw.kind == "page" and raw.word == 0 and first_unit and not self._paged
        if cue is not None and first:
            cue = cue.model_copy(update={"lead": "now"})
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
        if (
            index == 0
            and not self._paged
            and not self._opened_agenda
            and "page" not in kinds
            and not kinds & {"show", "faq"}
            and self._shown is None
            and self._site == "site"
        ):
            # Not when the sentence already shows something on the page they are
            # on, or is about a section of it: on dev call 03a45037 "General
            # medicine … with Fonasa", on /consultas-medicas, opened the Fonasa page.
            asked = asked_page(sentence)
            if (
                asked is not None
                and asked != self._path
                and self.kb.page(asked) is not None
                and self._section_for(sentence, self._path) is None
            ):
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
        if text is not None and not self._on_page(text, self._cue_path):
            # Words the page does not show would fail there, after he has
            # spoken past them (prod, 2026-10-22: "Resonancias magnéticas
            # $54.990", a home page card, cued on the resonance page).
            logger.info("clini: {!r} is not on {}; not cued", text, self._cue_path)
            return None
        path = _site_path(self._cue_path) if moved and self._cue_path else None
        return Cue(at=raw.at, word=raw.word, path=path, heading=heading, text=text)

    def _on_page(self, text: str, path: str | None) -> bool:
        """Whether the words ``text`` are on the site page ``path``, as the
        crawl saw it; true when there is no page of the crawl to check against
        (the booking, a page it never saw)."""
        page = self.kb.page(path) if path is not None else None
        if page is None:
            return True
        want = _phrase(text)
        if any(_phrase(b.name) == want for b in self.kb.branches):
            return True  # A sede's card, wherever the site lists its sedes.
        parts = [page.title, page.text, *page.tabs]
        parts += [f"{s.heading} {s.text} {' '.join(s.items)}" for s in page.sections]
        parts += [f"{f.q} {f.a}" for f in page.faqs]
        return bool(want) and f" {want} " in f" {_phrase(' '.join(parts))} "

    def _fits(self, raw: RawCue, cue: Cue) -> bool:
        """Whether a question heading or an FAQ cued on a sentence of his is
        about that sentence: it shares a word with it. "¿Qué examen necesitas
        hacerte?" rang "¿Qué es mejor estar en fonasa o isapre?", and "Tenemos
        horas disponibles" rang "Preguntas Frecuentes para toma de muestras:"
        (prod, 2026-10-22). Spanish only: an English reply's cues are in Spanish
        and share none of its words. A heading that is not a question is not
        held to it."""
        named = cue.faq or cue.heading
        if named is None or self.spoken != "es":
            return True
        question = (
            cue.faq is not None or named.strip().startswith("¿") or named.rstrip().endswith("?")
        )
        if not question and "preguntas frecuentes" not in fold(named):
            return True
        if len(raw.sentence.split()) < _SECTION_MIN_WORDS:
            return True
        return bool(set(_terms(named)) & set(_terms(raw.sentence)))

    def _talk_now(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The one extra request a turn that said and moved nothing gets: tools
        declared, none callable."""
        return _tools_off(self.respond_with(session, tools=ToolChoice.NONE))

    async def _run(self, tool: Any, call: dict[str, Any]) -> dict[str, Any]:
        """Tools off means not run: a call the model makes on a turn that could
        only speak is answered, and never reaches the page."""
        if _TOOLS_OFF.get():
            logger.warning("clini: {} called on a turn with tools off; not run", call.get("name"))
            result = (
                "Not run: this turn could only speak, so nothing was sent to "
                "the page. Never say it was done."
            )
            return {
                "type": "function_call_output",
                "call_id": call.get("call_id", ""),
                "output": json.dumps({"result": result}),
            }
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
        self._shorten_idle()
        self._note(_chosen_note(event.language, "on the toggle"))

    def _speaking(self, language: Lang) -> Config:
        """Both legs of ``language``, recorded as the one he speaks now, and the
        widget's toggle moved to it."""
        if language != self.spoken:
            self.session.dispatch(LanguageChanged(language=language))
        self.spoken = language
        return Config(
            stt=SttConfig(language=language, patience=self._patience),
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
            case CommandFailed() if event.command == "fill_agenda_patient" and _locked(
                event.reason
            ):
                # The booking keeps its fields locked until the visitor has
                # typed a valid RUT (or chosen Pasaporte and typed one).
                self._talk = None
                self._answered(event.command, f"{event.command} not done: {_LOCKED_NOTE}")
                return f"[Not done on the page. {_LOCKED_NOTE} ({event.reason}).]"
            case CommandFailed():
                if event.command in _BOOKING_COMMANDS:
                    # The step's own talk-through is off; its failure is said instead.
                    self._talk = None
                    self._agenda_asked = self._lasik_asked = False
                    self._restore_idle()
                self._answered(event.command, f"{event.command} not done: {event.reason}")
                return (
                    f"[Not done on the page ({event.command}): {event.reason}. Tell the visitor "
                    "plainly and offer what you can do instead; never say it worked.]"
                )

    def _agenda_changed(self, event: AgendaState) -> str:
        """The booking's report, as a note; and, after a step he took there or
        once it is booked, the ask that has him talk it through."""
        before = self.agenda
        self.agenda = event
        search = (event.servicio, event.prestacion, event.region)
        if (
            event.servicio is not None
            and event.prestacion is not None
            and (before is None or (before.servicio, before.prestacion, before.region) != search)
            and (service := _services(self.kb).get(event.servicio)) is not None
        ):
            # The hours of the exam the booking now shows, looked up while the
            # visitor reads it: the question about a day finds them waiting.
            region = (event.region or _RM) if service.regions else None
            clini_api.prefetch(event.servicio, event.prestacion, region)
        if self._no_hours is not None:
            self._no_hours.cancel()
            self._no_hours = None
        if event.servicio is not None and event.prestacion is not None and event.centres:
            self._listed(event.servicio, event.prestacion, event.centres)
        self._dictation()
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
            if self._busy() is not None and self._sent_pick and self._sent_pick[0]:
                # On its way to the day they gave: the calendar it passes
                # through is not theirs to choose from again (prod, 2026-10-22:
                # "¿Qué día te acomoda?" with Friday asked for). The move's own
                # answer is talked through.
                logger.info("clini: the booking is still on its way to {}", self._sent_pick[0])
            elif new_times:
                ask = (
                    "The booking shows the hours for the day they chose. Name two or three of "
                    "them, with the sede, as words, and ask which suits them."
                )
            elif new_days:
                ask = (
                    "The booking shows its open days and they have not spoken. Name two or "
                    "three of them as words, and ask which day suits them."
                )
            elif not event.days and not event.times:
                # Only once it has stayed empty: a page being translated or
                # still searching reports nothing for a moment.
                hold = NO_HOURS_HOLD_S * (
                    2 if before is not None and before.step == "search" else 1
                )
                self._no_hours = asyncio.get_running_loop().call_later(
                    hold, self._still_no_hours, event
                )
        elif event.step == "booking":
            if before is None or before.step != "booking":
                ask = (
                    "The booking's patient form is open for the hour they chose. Say the day, "
                    "hour and sede back in one sentence, give the indications in a sentence if "
                    "there are any, and ask them to type their RUT first, in the field you mark "
                    "for them (fill_agenda_patient with focus_rut), or, with no Chilean RUT, "
                    "their passport (fill_agenda_patient with document passport): the booking "
                    "unlocks the other fields once it has one."
                )
            elif event.ready and not before.ready:
                ask = (
                    "Everything on the booking form is complete. Say so in one sentence, and that "
                    "AGENDAR is theirs to press."
                )
            elif event.invalid != before.invalid and event.invalid:
                ask = (
                    "Some of the booking form is still missing. Say in one sentence what is left. "
                    "The RUT or passport number and the consent box are theirs to fill in."
                )
        if ask is not None:
            self._talk_through(ask)
        return note

    def _still_no_hours(self, event: AgendaState) -> None:
        """The booking has shown neither days nor hours for the whole hold."""
        self._no_hours = None
        if self.agenda is not event or not self._agenda_asked:
            return
        logger.info("clini: the booking has no days and no hours for this search")
        self._talk_through(
            "The booking shows no open days and no hours for this search. Say so in one "
            "sentence, and offer another region, or WhatsApp agendamiento."
        )

    def _lasik_changed(self, event: LasikFormState) -> str:
        before = self.lasik
        self.lasik = event
        self._dictation()
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

    def _dictation(self) -> None:
        """More patience while a form is open for them to dictate into, and the
        call's own again once it is complete or gone (:data:`FORM_PATIENCE`)."""
        agenda = self.agenda
        lasik = self.lasik
        dictating = (agenda is not None and agenda.step == "booking" and not agenda.ready) or (
            lasik is not None and bool(self._lasik_fields) and not lasik.valid
        )
        want = FORM_PATIENCE if dictating else CLINI_PATIENCE
        if want == self._patience:
            return
        self._patience = want
        logger.info("clini: patience -> {}", want)
        # No language named: the pairing rule binds only a stated language.
        configure_soon(self.session, Config(stt=SttConfig(patience=want)))

    def _listed(self, servicio: int, prestacion: int, centres: list[str]) -> None:
        """Centres the booking listed for an exam, kept with those it listed before."""
        known = self._centres.setdefault((servicio, prestacion), [])
        known.extend(c for c in centres if c and c not in known)

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
        self.append_note(text)

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
        """The page answered a booking move he sent: he says what it did in the
        next short quiet spell, unless the visitor speaks first. Answers that
        come close together are said together, once. A move queued behind this
        one goes to the page now, or, if this one failed, is dropped and said."""
        if command not in self._sent:
            return
        del self._sent[command]
        if (queued := self._queued) is not None and not self._busy():
            self._queued = None
            name = queued.__voqal_action__
            if outcome.startswith(f"{command} done"):
                logger.info("clini: {} answered; sending the {} queued behind it", command, name)
                self._send(queued)
            else:
                outcome += f" (so {name}, asked for while it ran, was not sent)"
        self._outcomes.append(outcome)
        self._shorten_idle()

    def _busy(self) -> str | None:
        """The booking move on the page that has not answered yet, if it is
        still within the time it takes: one at a time."""
        now = time.monotonic()
        for command, until in self._sent.items():
            if command in _AGENDA_MOVES and until > now:
                return command
        return None

    def _send(self, action: Action) -> None:
        command = action.__voqal_action__
        if isinstance(action, OpenAgenda | AgendaPick):
            self._sent_pick = (action.day, action.time, action.centre)
        if command in _CONFIRMED_COMMANDS:
            self._sent[command] = time.monotonic() + _MOVE_TAKES_S.get(command, _MOVE_TAKES_S[""])
        self.session.dispatch(action)

    def _agenda_move(self, action: Action, line: str, said: str | None = None) -> str | None:
        """Send a booking move, or, while the last one is still under way on
        the page, queue it to follow: ``None`` when sent, else what the tool
        says. Only the latest queued move is kept. ``said`` is his line for it,
        when it is not one of :data:`_LANDED`."""
        if (running := self._busy()) is None:
            self._queued = None
            self._move(action, line, said)
            return None
        self._queued = action
        landed(_LANDED["queued"][self.spoken])
        doing = "still opening" if running == "open_agenda" else "still working on the last step"
        logger.info("clini: {} queued behind {}", action.__voqal_action__, running)
        return (
            f"Queued, not sent yet: the booking is {doing} ({running}). It goes to the page as "
            "soon as the page answers that, and what it did comes back to you after. Say in a "
            "few words that you will do it as soon as the booking is ready; never that it is "
            "done, and do not call it again."
        )

    def _take_ask(self) -> str | None:
        """What he has to talk through now — a step the page reported, the
        page's answers to his moves, or both — and nothing left after."""
        asks: list[str] = []
        if self._outcomes:
            asks.append(
                "The page answered what you sent it: "
                + "; ".join(self._outcomes)
                + ". Say in a sentence what actually happened, as the page says it, in the "
                "language you speak: what is done, and plainly what is not, with what you can "
                "do instead. Never say something is done that the page did not confirm."
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

    def _move(self, action: Action, line: str = "shown", said: str | None = None) -> None:
        """Dispatch ``action``, with the written line for it (``said``, else one
        of :data:`_LANDED`, in the language he speaks) should the turn say
        nothing. A booking move is awaited by nothing: the page answers later,
        as an event."""
        self._send(action)
        landed(said or _LANDED[line][self.spoken])

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
        if any(p.servicio == "LAB" for p in found):
            self._prefetch_lab()
        lines = "\n".join(f"- {clini_api.price_line(p)}" for p in found)
        return (
            f"From {source}; prices in Chilean pesos, Fonasa is the Nivel 1 copago for tramos B, "
            f"C and D:\n{lines}"
        )

    def _prefetch_lab(self) -> None:
        """The laboratorio's hours, looked up while he says a lab price: the lab
        search is the slowest the booking has (6 s, its deadline, on prod), and
        the question after a lab price is nearly always when."""
        lab = _services(self.kb).get(_LAB)
        if lab is None or len(lab.prestaciones) != 1:
            return
        clini_api.prefetch(lab.servicio, lab.prestaciones[0].code, _RM if lab.regions else None)

    @needs_result_now
    async def check_availability(self, request: AvailabilityRequest) -> str:
        """The first days with free hours for an exam on Clini's booking, and for
        one day (the first, or the one asked) each sede's first hours. Call it
        first, before you answer. Codes from the booking list. With the booking
        tab open on that exam, a day or an hour to show or select is agenda_pick."""
        service, error = self._service(request.servicio, request.prestacion, request.region)
        if service is None:
            return error
        prestacion = self._prestacion_for(service, request.prestacion)
        if prestacion is None:
            options = "; ".join(f"{p.code} {p.name}" for p in service.prestaciones)
            return f"Ask which one first: {service.name} has {options}."
        region = (request.region or _RM) if service.regions else None
        day = iso_day(request.day)
        here = _PICK_HINT if self._booking_shows(service.servicio, prestacion.code, region) else ""
        if (screen := self._on_screen(service.servicio, prestacion.code, region, day)) is not None:
            return screen + here
        try:
            found = await clini_api.availability(service.servicio, prestacion.code, region, day)
        except clini_api.LookupSlow as e:
            logger.warning("clini: availability for {} is slow: {}", service.servicio, e)
            self._finish_late(service, prestacion, region, day)
            return (
                "The booking is slow to answer just now. The lookup goes on, and its days and "
                "hours come to you in square brackets as soon as it answers. Say in one sentence "
                "that the booking is slow today and you will tell them in a moment"
                + (
                    ", or offer to open the booking (open_agenda), where they see the hours."
                    if not here
                    else "."
                )
            )
        except clini_api.LookupFailed as e:
            logger.warning("clini: availability for {} failed: {}", service.servicio, e)
            return (
                "The booking did not answer just now. Say so plainly, and offer to open the "
                "booking (open_agenda), where they can see the hours themselves."
            )
        if found.day and (later := [d for d in found.days if d > found.day]):
            # The next open day's hours, which is what they ask for next.
            clini_api.prefetch_day(service.servicio, prestacion.code, region, later[0])
        return self._availability_text(service, prestacion, region, day, found) + here

    def _availability_text(
        self,
        service: AgendaService,
        prestacion: Prestacion,
        region: int | None,
        day: str | None,
        found: clini_api.Availability,
    ) -> str:
        what = f"{service.name} — {prestacion.name}"
        named = _region(service, region)
        where = f", {named.name if named else f'region {region}'}" if region else ""
        if not found.days:
            return (
                f"No free hours for {what}{where} in the next month. Say so, "
                "and offer another region or WhatsApp agendamiento."
            )
        days = "; ".join(_said_day(d) for d in found.days[:_AVAILABLE_DAYS])
        out = [f"{what}{where}.", f"First days with free hours: {days}."]
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
            self._listed(service.servicio, prestacion.code, [c.nombre for c in found.centres])
            listed = "; ".join(self._centres.get((service.servicio, prestacion.code), []))
            out.append(
                f"Centres bookable online for this exam: {listed}. Offer an hour only at one of "
                "these, never at another sede."
                + (
                    " A Toma de Muestras sede not listed takes walk-ins by order of arrival "
                    "during its hours, with no booking."
                    if service.servicio == _LAB
                    else ""
                )
            )
        elif found.day:
            out.append(f"The hours of {_said_day(found.day)} did not load; the booking shows them.")
        out.append("Say two or three of these as words. Times are Santiago's.")
        return "\n".join(out)

    def _finish_late(
        self, service: AgendaService, prestacion: Prestacion, region: int | None, day: str | None
    ) -> None:
        """A lookup that missed the tool's deadline runs on; when it answers,
        its days and hours go into the context, talked through in the next
        short quiet spell unless the visitor speaks first."""

        async def finish() -> None:
            try:
                found = await clini_api.availability(
                    service.servicio,
                    prestacion.code,
                    region,
                    day,
                    deadline=clini_api.REQUEST_TIMEOUT_S,
                )
            except clini_api.LookupFailed as e:
                logger.warning(
                    "clini: the late availability for {} failed: {}", service.servicio, e
                )
                self._note(
                    f"[The open hours you were looking up for {service.name} did not come: the "
                    "booking did not answer.]"
                )
                self._talk_through(
                    "The booking did not answer the open hours you were looking up. Say so "
                    "plainly in one sentence, and offer to open the booking, where they see them."
                )
                return
            text = self._availability_text(service, prestacion, region, day, found)
            self._note(f"[The open hours you were looking up came in: {text}]")
            self._talk_through(
                "The open hours you were looking up came in, in the line above. Say two or three "
                "of them as words, and ask which suits them."
            )

        task = asyncio.get_running_loop().create_task(finish())
        self._late.add(task)
        task.add_done_callback(self._late.discard)

    def _booking_shows(self, servicio: int, prestacion: int, region: int | None) -> bool:
        """Whether the booking tab is open on this search, past its first step."""
        shown = self.agenda
        return (
            shown is not None
            and shown.step in ("results", "booking")
            and shown.servicio == servicio
            and shown.prestacion == prestacion
            and (region is None or (shown.region or _RM) == region)
        )

    def _on_screen(
        self, servicio: int, prestacion: int, region: int | None, day: str | None
    ) -> str | None:
        """The answer from the booking in front, when it already shows this
        search's days and the hours asked for: no lookup, no wait."""
        shown = self.agenda
        if (
            shown is None
            or shown.step != "results"
            or shown.servicio != servicio
            or shown.prestacion != prestacion
            or (region is not None and (shown.region or _RM) != region)
            or not shown.days
            or not shown.times
            or (day is not None and day != shown.day)
        ):
            return None
        logger.info("clini: availability for {} answered from the booking on screen", servicio)
        days = "; ".join(_said_day(d) for d in shown.days[:_AVAILABLE_DAYS])
        at = shown.centre or "the open sede"
        on = _said_day(shown.day) if shown.day else "the day in view"
        return (
            f"From the booking on their screen. Open days: {days}.\n"
            f"Hours at {at} on {on}: {_clip(shown.times, _AVAILABLE_TIMES * 2)}.\n"
            "Say two or three of these as words, as on their screen. Times are Santiago's."
        )

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

    def _meta_turn(self) -> str | None:
        """The refusal for a booking tool called on a question about the call."""
        if self._heard and about_the_call(self._heard[-1]):
            return (
                "Not done: they asked about the call itself, not the booking. Answer that "
                "only (set_language for a language), and touch nothing on the booking."
            )
        return None

    @staticmethod
    def _sent_note(doing: str) -> str:
        """What a booking tool tells the model: sent, not done."""
        return (
            f"Sent to the page; it has not happened yet. Say only what you are doing "
            f"({doing}), never that it is done; the page's answer will follow."
        )

    async def open_agenda(self, request: OpenAgendaRequest) -> str:
        """Open Clini's online booking for an exam in its own tab, and take the
        steps the visitor chose: the prestación, the day, the sede and the hour.
        It returns at once; what the booking did comes back to you after. It
        never presses AGENDAR."""
        if (meta := self._meta_turn()) is not None:
            return meta
        service, error = self._service(request.servicio, request.prestacion, request.region)
        if service is None:
            return error
        prestacion = self._prestacion_for(service, request.prestacion)
        day = iso_day(request.day)
        when = hhmm(request.time)
        region = request.region if request.region not in (None, _RM) else None
        centre = (request.centre or "").strip() or None
        if centre is None and prestacion is not None:
            named, refused = self._named_centre(service, prestacion)
            if refused is not None:
                return refused
            centre = named
        self._agenda_asked = True
        # The booking comes to the front now: nothing more of this reply moves
        # the site, and the next reply's cues are for the booking.
        self._opened_agenda = True
        self._site = "agenda"
        self._cue_path = None
        queued = self._agenda_move(
            OpenAgenda(
                servicio=service.servicio,
                prestacion=prestacion.code if prestacion else None,
                region=region,
                day=day,
                centre=centre,
                time=when,
            ),
            "agenda",
        )
        if prestacion is not None:
            # Its hours, looked up while the booking opens: asked about next,
            # they are answered from the cache.
            clini_api.prefetch(
                service.servicio,
                prestacion.code,
                (request.region or _RM) if service.regions else None,
            )
        if queued is not None:
            return queued
        steps = [x for x in (day and _said_day(day), when, centre) if x]
        return (
            f"Opening the booking for {service.name}"
            + (f" — {prestacion.name}" if prestacion else "; they pick the prestación there")
            + (f", for {', '.join(steps)}" if steps else "")
            + ". "
            + self._sent_note("'Te abro la agenda.'")
            + " AGENDAR is theirs to press."
        )

    async def agenda_pick(self, request: AgendaPickRequest) -> str:
        """On the booking tab already open: pick the day, morning or afternoon,
        sede and hour the visitor chose, then Continuar. It returns at once;
        what the booking selected comes back to you after."""
        if (meta := self._meta_turn()) is not None:
            return meta
        if not self._has_agenda():
            return "Not done: no booking tab is open. Use open_agenda first."
        day = iso_day(request.day)
        when = hhmm(request.time)
        shown = self.agenda
        if (
            shown is not None
            and day
            and shown.days
            and day not in shown.days
            # The calendar lists the open days of the month on screen; another
            # month's day is the page's to find.
            and (not shown.month or day.startswith(shown.month))
        ):
            return (
                f"Not picked: {_said_day(day)} is not an open day on the booking. Open days: "
                f"{_clip([_said_day(d) for d in shown.days], _DAYS_IN_NOTE)}."
            )
        if not (day or when or request.centre or request.period):
            return "Not picked: say which day, sede or hour."
        centre = (request.centre or "").strip() or None
        if (same := self._same_pick(day, when, centre)) is not None:
            landed(_LANDED["already"][self.spoken])
            return same
        self._agenda_asked = True
        queued = self._agenda_move(
            AgendaPick(day=day, time=when, centre=centre, period=request.period),
            "agenda_pick",
        )
        return queued or self._sent_note("'Te selecciono las diez.'")

    def _same_pick(self, day: str | None, when: str | None, centre: str | None) -> str | None:
        """Why a pick is not sent, when it asks for what the booking already
        shows or is already on its way to: a pick of the hour the open had
        chosen took the patient form down and put it back, twice (prod,
        2026-10-22)."""
        if not (day or when or centre):
            return None
        # What the booking will show once the moves under way are done: the
        # one queued, else the one on the page.
        queued = self._queued
        sent = (
            (queued.day, queued.time, queued.centre)
            if isinstance(queued, OpenAgenda | AgendaPick)
            else self._sent_pick
            if self._busy() is not None
            else None
        )
        if (
            sent is not None
            and (day is None or day == sent[0])
            and (when is None or when == sent[1])
            and (centre is None or (sent[2] is not None and _same_centre(centre, sent[2])))
        ):
            logger.info("clini: agenda_pick {} {} {} is on its way already", day, when, centre)
            return (
                "Not sent: the booking is already on its way to exactly that, from your last "
                "booking move, and its answer comes back to you. Say in a few words that it is "
                "being selected; do not call it again."
            )
        shown = self.agenda
        if (
            shown is not None
            and shown.step == "booking"
            and shown.selected
            and (day is None or day == shown.day)
            and (when is None or when in shown.selected)
            and (centre is None or _same_centre(centre, f"{shown.centre} {shown.selected}"))
        ):
            logger.info("clini: agenda_pick {} {} {} is on screen already", day, when, centre)
            return (
                f"Not sent: that is already selected on their screen ({shown.selected}), with "
                "the patient form open, which stays as it is. Say so in a few words and go on "
                "with the form."
            )
        return None

    def _named_centre(
        self, service: AgendaService, prestacion: Prestacion
    ) -> tuple[str | None, str | None]:
        """The centre the visitor chose, when open_agenda left it out: ``(the
        booking's centre, None)``; or ``(None, why not)`` when the sede they
        named is not one the booking lists for this exam (prod, 2026-10-22:
        Tobalaba, offered and accepted, dropped as ``centre: null``, and the
        booking then showed other sedes); ``(None, None)`` when nothing says.
        Only from the centres the booking listed for it."""
        listed = self._centres.get((service.servicio, prestacion.code))
        if not listed:
            return None, None
        vocabulary = {w for c in listed for w in _places(c)} | {
            w for b in self.kb.branches for w in _places(b.name)
        }
        theirs = " ".join(self._heard[-2:])
        named = _places_in(theirs, vocabulary) or _places_in(self._last_said, vocabulary)
        if not named:
            return None, None
        matches = [c for c in listed if _places(c) & named]
        if len(matches) == 1:
            logger.info("clini: open_agenda had no centre; they named {}", matches[0])
            return matches[0], None
        if matches:
            return None, None
        where = ", ".join(sorted(named))
        walk_in = (
            " A Toma de Muestras sede the booking does not list takes walk-ins by order of "
            "arrival during its hours, with no booking: say that."
            if service.servicio == _LAB
            else ""
        )
        return None, (
            f"Not opened: the sede they chose ({where}) is not one the booking takes for "
            f"{prestacion.name}; it lists only {'; '.join(listed)}.{walk_in} Offer the nearest of "
            "the listed centres, and call open_agenda again with the one they choose."
        )

    def _phone(self, said: str, refused: list[str]) -> str | None:
        """The celular the model passed, if it is a Chilean one and the digits
        the visitor said; else why not, in ``refused``. Never reshaped."""
        # What they said just now, or with the fragment before it.
        heard = said_digits(self._heard[-1]) if self._heard else ""
        if len(heard) < _SAID_DIGITS_MIN:
            heard = said_digits(" ".join(self._heard[-2:]))
        given = "".join(c for c in said if c.isdigit())
        phone = mobile(said)
        if phone is None:
            from_them = f" (they said {spaced(heard)})" if len(heard) >= _SAID_DIGITS_MIN else ""
            refused.append(
                f"celular: {spaced(given) or said!r}{from_them} is not a Chilean celular, nine "
                f"digits starting with 9 ({len(given)} digits given). Tell them the form needs a "
                "Chilean mobile and ask for one; never change or invent digits"
            )
            return None
        if len(heard) >= _SAID_DIGITS_MIN and phone not in heard:
            refused.append(
                f"celular: {spaced(phone)} is not what the visitor said ({spaced(heard)}). "
                "Never change their digits: if theirs is not a Chilean mobile, nine digits "
                "starting with 9, tell them the form needs one and ask"
            )
            return None
        return phone

    async def fill_agenda_patient(self, request: PatientRequest) -> str:
        """Fill the booking's patient form with what the visitor said: name,
        surnames, birth date, sex, celular, email; ``document`` passport for a
        visitor with no Chilean RUT. What is filled stays. With focus_rut, ring
        the RUT (or passport) field for them to type it. It returns at once;
        what the form took comes back to you after. Never a RUT or passport
        number; never AGENDAR."""
        if (meta := self._meta_turn()) is not None:
            return meta
        if not self._has_agenda():
            return "Not filled: no booking tab is open. Use open_agenda first."
        if self.agenda is not None and self.agenda.step != "booking":
            return (
                "Not filled yet: the patient form opens once they pick an hour (it shows "
                f"{_STEP_NAMES[self.agenda.step]} now)."
            )
        refused: list[str] = []
        #: What this call adds to the form, and what it turned down, by field:
        #: his line says exactly that (prod, 2026-10-22: "Te lo completo en el
        #: formulario" after a fill that took nothing).
        took: list[str] = []
        turned: list[str] = []
        given = {
            "name": request.name,
            "last_name": request.last_name,
            "maternal_last_name": request.maternal_last_name,
        }
        for key, value in given.items():
            if value and value.strip():
                self._patient[key] = " ".join(value.split())
                took.append(key)
        if request.birth_date:
            born = iso_day(request.birth_date)
            if born and born < clini_api.today().isoformat():
                self._patient["birth_date"] = born
                took.append("birth_date")
            else:
                refused.append("birth date (as YYYY-MM-DD, in the past)")
                turned.append("birth_date")
        if request.sex:
            if self._said_sex(request.sex):
                self._patient["sex"] = request.sex
                took.append("sex")
            else:
                # Inferred from a first name on prod (2026-10-22): a medical
                # form takes what they said, not a guess.
                refused.append(
                    "sex: they did not say it. Ask them (femenino, masculino u otro); never "
                    "guess it from a name or a voice"
                )
                turned.append("sex")
        if request.phone:
            if (phone := self._phone(request.phone, refused)) is not None:
                self._patient["phone"] = phone
                took.append("phone")
            else:
                turned.append("phone")
        if request.email:
            if (address := email_address(request.email)) is not None:
                self._patient["email"] = address
                took.append("email")
            else:
                refused.append("email")
                turned.append("email")
        if request.document is not None:
            self._document = request.document
        p = self._patient
        self._agenda_asked = True
        only_rut = request.focus_rut and not took and not turned
        line = None if only_rut else self._patient_line(took, turned, request.focus_rut)
        queued = self._agenda_move(
            FillAgendaPatient(
                name=p.get("name"),
                last_name=p.get("last_name"),
                maternal_last_name=p.get("maternal_last_name"),
                birth_date=p.get("birth_date"),
                sex=cast(Literal["F", "M", "O"] | None, p.get("sex")),
                phone=p.get("phone"),
                email=p.get("email"),
                document=self._document,
                focus_rut=request.focus_rut,
            ),
            "rut" if only_rut else "patient",
            line,
        )
        out = f"For the booking form: {', '.join(p) or 'nothing yet'}. " + (
            queued or self._sent_note("'Te lo completo.'")
        )
        if "email" in p:
            out += f" The email sent: {p['email']}."
        if "phone" in p:
            out += f" The celular sent: {spaced(p['phone'])}."
        if refused:
            out += f" Not filled: {'; '.join(refused)}."
        if request.focus_rut:
            which = "passport number" if self._document == "passport" else "RUT"
            out += f" The {which} field is ringed: they type it themselves."
        return out + " AGENDAR is theirs to press."

    def _said_sex(self, sex: str) -> bool:
        """Whether the visitor's last words say ``sex`` (F, M or O)."""
        said = _SAID_SEX.get(sex)
        return said is not None and bool(said.search(fold(" ".join(self._heard))))

    def _patient_line(self, took: list[str], turned: list[str], focus_rut: bool) -> str:
        """His line for a fill of the patient form, from what it did: the
        fields it sends, the celular read back, the first thing it turned down
        asked again, the RUT field to type in."""
        lang = self.spoken
        out: list[str] = []
        if took:
            fields = _and(lang, [_FIELD_NAMES[lang][k] for k in took])
            out.append(
                f"Te anoto {fields} en el formulario."
                if lang == "es"
                else f"I'm putting {fields} in the form."
            )
            if "phone" in took:
                digits = ", ".join(_DIGIT_NAMES[lang][int(d)] for d in self._patient["phone"])
                out.append(f"Tu celular: {digits}." if lang == "es" else f"Your celular: {digits}.")
        if turned:
            out.append(_ASK_AGAIN[turned[0]][lang])
        if focus_rut:
            out.append(_LANDED["rut"][lang])
        return " ".join(out) or _ASK_AGAIN[""][lang]

    async def fill_lasik_form(self, request: LasikRequest) -> str:
        """Fill the free LASIK evaluation form on /cirugia-lasik with what the
        visitor said: name, email, celular, previsión, where. It takes them to
        the form; it returns at once, and what the form took comes back to you
        after. What is filled stays.
        With focus_rut, ring the RUT field for them to type it. Never a RUT;
        never "¡Agendar evaluación!"."""
        if (meta := self._meta_turn()) is not None:
            return meta
        refused: list[str] = []
        if request.name and request.name.strip():
            self._lasik_fields["name"] = " ".join(request.name.split())
        if request.email:
            if (address := email_address(request.email)) is not None:
                self._lasik_fields["email"] = address
            else:
                refused.append("email")
        if request.phone and (phone := self._phone(request.phone, refused)) is not None:
            self._lasik_fields["phone"] = phone
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
        out = f"Sending to the LASIK evaluation form: {', '.join(f) or 'nothing yet'}. "
        out += self._sent_note("'Te lo completo.'")
        if "email" in f:
            out += f" The email sent: {f['email']}."
        if "phone" in f:
            out += f" The celular sent: {spaced(f['phone'])}."
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
