"""UnoSaludBrain — Javier, a guide on www.unosalud.cl and its online booking.

The site is Uno Salud Dental's, not ours. A browser extension injects the widget
and a small adapter into www.unosalud.cl; the adapter turns each
:class:`~voqalize.sdk.Action` below into a move on the visitor's tab — a page, a
place scrolled to and ringed (by its key in the catalogue,
``knowledge/L3/anchors.json``), an FAQ opened, a booking step taken, a form
filled. Every tab reports what it shows as a typed event (:mod:`.app_events`),
whichever of the visitor and Javier moved it. Every move to another page is a
full page load: the call is held by the extension across it, and the cues left
over are handed across in the tab's ``sessionStorage``.

**The booking starts with the visitor.** Uno Salud's booking
(``/agenda-tu-hora/``) asks first for the patient's RUT, the terms and a "No soy
un robot" box, and shows no clinic or hour until those are done. So he opens it
in its own tab, rings the RUT field, and explains kindly why those three are
theirs; then he picks the motivo, the clinic, the day and the hour with them, and
rings "Confirmar cita", which they press. Nothing in the brain reads the site:
it is not served where the brain runs, and its availability needs the visitor's
session. What the booking shows comes back as ``booking_state``.

**A guide, not a search box.** Every turn answers what was asked, in words, as
a conversation: the answer, then one gentle next step.

**Every fact has a source.** A price, a promotion, a clinic or a convenio is
spoken from L1 (in this prompt), an L2 topic he read, a search, the clinic
table, or what the page itself reported. Never from memory.

**A guide, not a dentist.** He says what the site says and never diagnoses; acute
pain is urgencias, or the call center, 600 707 1010.

**The screen follows his voice.** He writes his moves into the reply as cues
(``{show: ortodoncia_precios}``), at the start of the sentence they belong to;
the brain takes them out of the speech, checks them against the catalogue, and
the page fires each as the voice reaches its sentence (:mod:`.cues`).

**Spanish or English, as the visitor chose or speaks**, exactly as Clini: the
call opens in Spanish; a language chosen on the toggle or asked for holds; until
then the call follows the language they speak, both legs moved together.
"""

from __future__ import annotations

import contextlib
import dataclasses
import inspect
import math
import random
import re
import time
from collections.abc import AsyncGenerator
from contextvars import ContextVar
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
    UNOSALUD_EVENTS,
    BookingState,
    CallbackFormState,
    CommandDone,
    CommandFailed,
    CompanyFormState,
    LanguageRequested,
    PageChanged,
    TabInfo,
    TabsChanged,
    UnoSaludEvent,
)
from .cues import CueKind, CueParser, RawCue, words
from .knowledge import (
    BOOKING_PATH,
    CLINIC_PAGE,
    TOPIC_IDS,
    Anchor,
    Clinic,
    Knowledge,
    canonical_path,
    fold,
    is_clinic_page,
    norm,
)

AGENT_NAME = "Javier"

#: LOW, as Clini: at MINIMAL the model made the page call first and wrote
#: nothing, and gemini-3.8-flash refuses MINIMAL outright.
THINKING = types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)
#: Gemini 3.8 Flash, as Clini: its first words come out steadily in about two seconds.
MODEL = "gemini-3.8-flash"
#: Uno Salud is in Chile: "mañana" and "el lunes" are counted from Santiago's today.
TIMEZONE = ZoneInfo("America/Santiago")

# ─── Voice and timing ──────────────────────────────────────────────────────────

#: Javier's voice, recorded once in English and once in Spanish: a switch keeps the same man.
VOICE = Voice.OMNIVOICE_JAVIER

_IDLE_MS = 20_000
_IDLE_NUDGES = 2
#: The idle window while something the page did is waiting to be talked through.
_TALK_THROUGH_MS = 2_000
#: A visitor thinking aloud about their teeth pauses mid-sentence.
UNOSALUD_PATIENCE = PATIENCE + 2
#: While a form is open for them to dictate into: a name, a birth date or a
#: celular is said in pieces (Clini, prod 2026-10-22).
FORM_PATIENCE = 9
#: A message this soon after the last one is the rest of the same thought.
_FRAGMENT_S = 4.0

# ─── Language ──────────────────────────────────────────────────────────────────

Lang = Literal["en", "es"]
#: The site is Spanish (Chile), so the call opens in Spanish.
OPENING: Lang = "es"
LANGUAGE_NAMES: dict[Lang, str] = {"en": "English", "es": "Spanish"}

TOGGLE_CONFIRM: dict[Lang, str] = {
    "en": "Sure, let's continue in English.",
    "es": "Claro, seguimos en español.",
}

_SPANISH_WORDS = frozenset(
    # A word list reads as words, so it stays a split string.
    """que qué de del el los las una unas unos por para con como cómo cuánto cuanto
    cuánta cuesta cuestan puedes puede podrías quiero quisiera necesito tengo tienes
    tiene hay hola gracias sí está están estoy es eso esto esta este estos pero muy
    también hablar habla hablas hablemos español castellano usted ustedes mi mis tu tus
    su sus nosotros bueno claro dónde donde cuál cual cuándo cuando precio precios
    muéstrame dime explícame funciona hace hacer hora horas agendar necesitas atienden
    tienen muela muelas diente dientes dolor encías frenillos limpieza clínica
    """.split()  # noqa: SIM905
)
_ENGLISH_WORDS = frozenset(
    """the is are was what how can could you your i i'm it it's this that these those do
    does show me my we our for with about and of to have has there here please want
    would like tell sure yes okay right of course let's tooth teeth
    """.split()  # noqa: SIM905
)
_WRITTEN_ENOUGH = 60
_SENTENCE_END = re.compile(r"[.?!](?:\s|$)")
_SPANISH_MARKS = re.compile(r"[¿¡ñáéíóú]", re.IGNORECASE)
_LETTERS = re.compile(r"[\wáéíóúüñ']+")
#: A cue is the site's own words or a key, whatever he speaks.
_CUE_TEXT = re.compile(r"\{[^{}]*\}?")


def language_of(text: str, *, sure: bool = True) -> Lang | None:
    """The language ``text`` is plainly in, or ``None`` (as Clini)."""
    text = _CUE_TEXT.sub(" ", text)
    said = set(_LETTERS.findall(text.lower()))
    es = len(said & _SPANISH_WORDS) + (1 if _SPANISH_MARKS.search(text) else 0)
    en = len(said & _ENGLISH_WORDS)
    if es >= (2 if sure else 1) and es > en:
        return "es"
    if en >= (3 if sure else 2) and es == 0:
        return "en"
    return None


#: Latin America says "vi-DE-o"; the Spanish voice read plain "video" the Spain
#: way (Clini, dev 2026-10-21), and "bidéo" right every time. Only the voice gets it.
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


# ─── Actions (brain → page) ────────────────────────────────────────────────────


class Navigate(Action):
    """Go to one of www.unosalud.cl's pages (on the site tab, opened if there is
    none) and, after the load, scroll to the place ``anchor`` (a key of
    anchors.json) or the smallest element containing ``text`` and ring it; with
    ``faq``, open that FAQ key. The page reports ``page_changed``."""

    path: str
    anchor: str = ""
    text: str = ""
    faq: str = ""


class Cue(Action):
    """A move for the page to make when the voice reaches ``at`` — the first
    words of the sentence it belongs to (see :mod:`.cues`); empty ``at`` is
    when the voice stops. With ``path``, it is a :class:`Navigate`; else a
    place (``anchor``), words (``text``) or an FAQ key (``faq``) on the tab in front."""

    at: str
    word: int = 0
    """Words of the unit before it, for a page that times cues by the clock."""
    path: str = ""
    anchor: str = ""
    text: str = ""
    faq: str = ""
    lead: Literal["nod", "now"] | None = None
    """A page to open ahead of the words: ``nod``, once the nod in the air has
    played; ``now``, at once (see Clini)."""


class ShowSection(Action):
    """On the tab in front: scroll to the place ``anchor`` (or the smallest
    element containing ``text``) and ring it; in a carousel, pause it and select
    the cell."""

    anchor: str = ""
    text: str = ""


class OpenFaq(Action):
    """Open the FAQ ``faq`` (a key of anchors.json) on the tab in front, and ring it."""

    faq: str


class FocusTab(Action):
    """Bring one of the visitor's Uno Salud tabs to the front."""

    tab_id: str


class LanguageChanged(Action):
    """The call's language moved: the widget's toggle follows at once."""

    language: Literal["en", "es"]


class OpenLink(Action):
    """Open ``url`` in a new tab: a clinic's "¿Cómo llegar?" Google Maps link, or
    a www.unosalud.cl page. Resolved and checked by the brain."""

    url: str


class OpenBooking(Action):
    """Open /agenda-tu-hora/ (with ``?promo=`` when given) in its own tab, or move
    to the booking tab already open; once loaded, ring the RUT field (#rut). It
    never types the RUT, never ticks the terms or the captcha, and never presses
    Continuar there. Reports ``booking_state``."""

    promo: str = ""


class FillBookingPatient(Action):
    """On the new patient form (#setPAC): fill the fields given, then ring
    "Registrarse" once valid — the visitor presses it. On the known patient's
    step (#setEF): fill email and phone if given and, with ``confirm_existing``,
    press its Continuar. There is no RUT here: the visitor types it."""

    nombre: str = ""
    paterno: str = ""
    materno: str = ""
    birth_date: str = ""
    """YYYY-MM-DD."""
    email: str = ""
    phone: str = ""
    """Nine digits starting with 9: the form puts +56 in front."""
    confirm_existing: bool = False


class BookingPick(Action):
    """On the booking tab, the given steps in order, one at a time, waiting for
    each: the motivo (14 to 23) and its Continuar; the region, comuna and clinic
    (name or id from #jsonSucursales) and their Continuar; the day (YYYY-MM-DD);
    the hour (HH:MM), which moves to the review, where "Confirmar cita" is rung
    for the visitor. Reports ``booking_state`` after each step."""

    motivo: int = 0
    region: str = ""
    comuna: str = ""
    sucursal: str = ""
    date: str = ""
    time: str = ""


class BookingScan(Action):
    """On the day-and-hour step: read the hours of the next open days, from
    ``from_date``, for ``days`` days, and leave the first day with hours
    selected. Reports ``booking_state.days``."""

    from_date: str = ""
    days: int = 5


class FillCallbackForm(Action):
    """Fill the Te llamamos form (/landing/solicitar-diagnostico/) or the one on
    /urgencias/ (going there if needed), then ring the RUT field for the visitor
    and ENVIAR once complete. Never types the RUT, never presses ENVIAR. Reports
    ``callback_form_state``."""

    form: Literal["te_llamamos", "urgencias"] = "te_llamamos"
    nombre: str = ""
    apellidos: str = ""
    email: str = ""
    phone: str = ""
    """Nine digits, without +56."""
    region: str = ""
    comuna: str = ""


class FillCompanyForm(Action):
    """Fill the Convenio Empresas form on /landing/convenio-empresa/ (going there
    if needed) and ring ENVIAR, which the visitor presses. Reports ``company_form_state``."""

    nombre: str = ""
    phone: str = ""
    email: str = ""
    empresa: str = ""
    region: str = ""
    cargo: str = ""
    trabajadores: str = ""
    """The form's option text: "Menos de 50 Trabajadores", "Entre 200 a 500
    trabajadores", "Entre 500 a 1000 trabajadores" or "Más de 1000 trabajadores"."""
    comentarios: str = ""


# ─── Tool requests ─────────────────────────────────────────────────────────────

if TYPE_CHECKING:
    TopicId = str
else:
    TopicId = Literal[TOPIC_IDS]


class TopicRequest(BaseModel):
    topic: TopicId = Field(description="The topic to read, by its name.")


class SearchRequest(BaseModel):
    query: str = Field(
        description="A few words to look for on www.unosalud.cl, in Spanish, e.g. 'precio "
        "implante', 'muelas del juicio', 'excedentes isapre', 'urgencias sábado'."
    )


class ClinicRequest(BaseModel):
    query: str = Field(
        description="A comuna, city, region, clinic name, street, landmark or metro station, "
        "e.g. 'Providencia', 'Maipú', 'Temuco', 'metro Manuel Montt', 'Moneda'."
    )


class TabRequest(BaseModel):
    tab_id: str = Field(description="The tab_id from the open tabs list.")


class LanguageRequest(BaseModel):
    language: Lang = Field(description="'en' for English, 'es' for Spanish.")


class OpenBookingRequest(BaseModel):
    promo: str = Field(
        default="",
        description="A promotion's key from the promotions topic (e.g. 'ortodoncia_oct'), "
        "only when they book for that promotion. Empty otherwise.",
    )


class PatientRequest(BaseModel):
    """Only what the visitor said. There is no RUT here: they type it themselves."""

    nombre: str = Field(default="", description="First name(s), as they said them.")
    paterno: str = Field(default="", description="Apellido paterno.")
    materno: str = Field(default="", description="Apellido materno.")
    birth_date: str = Field(default="", description="YYYY-MM-DD.")
    email: str = Field(default="", description="As they said it, e.g. ana@correo.cl.")
    phone: str = Field(
        default="",
        description="Their celular, exactly the digits they said, never changed and never "
        "counted by you: a Chilean one is nine digits starting with 9. The tool checks it.",
    )
    confirm_existing: bool = Field(
        default=False,
        description="On the known patient's step: press its Continuar, once they agree "
        "their details are right.",
    )


class PickRequest(BaseModel):
    """Only what the visitor chose: leave out anything they did not."""

    motivo: int = Field(default=0, description="The motivo, 14 to 23, from the motivo list.")
    clinic: str = Field(
        default="",
        description="The clinic they chose: its key or name as find_clinic gave it, e.g. "
        "'manuel_montt' or 'Manuel Montt'.",
    )
    date: str = Field(default="", description="The day they chose, YYYY-MM-DD.")
    time: str = Field(default="", description="The hour they chose, HH:MM, from the booking.")


class ScanRequest(BaseModel):
    from_date: str = Field(default="", description="YYYY-MM-DD to start from; empty for today.")
    days: int = Field(default=5, description="How many open days to read, 1 to 10.")


class CallbackRequest(BaseModel):
    """Only what the visitor said. There is no RUT here: they type it themselves."""

    form: Literal["te_llamamos", "urgencias"] = Field(
        default="te_llamamos",
        description="'te_llamamos' for the callback form; 'urgencias' for the one on the "
        "urgencias page.",
    )
    nombre: str = Field(default="", description="First name(s).")
    apellidos: str = Field(default="", description="Surnames.")
    email: str = Field(default="", description="As they said it.")
    phone: str = Field(
        default="", description="Exactly the digits they said: nine, without +56. Never changed."
    )
    region: str = Field(
        default="", description="Their region, e.g. 'Región Metropolitana', 'Biobío'."
    )
    comuna: str = Field(default="", description="Their comuna, e.g. 'Ñuñoa'.")


class CompanyRequest(BaseModel):
    """Only what the visitor said."""

    nombre: str = Field(default="", description="The contact's name.")
    phone: str = Field(default="", description="Nine digits, exactly as said.")
    email: str = Field(default="", description="The contact email.")
    empresa: str = Field(default="", description="The company's name.")
    region: str = Field(default="", description="The company's region.")
    cargo: str = Field(default="", description="The contact's job title.")
    trabajadores: int = Field(default=0, description="How many employees, as a number.")
    comentarios: str = Field(default="", description="A short message, if they gave one.")


class LinkRequest(BaseModel):
    clinic: str = Field(
        default="", description="A clinic's key or name: opens its '¿Cómo llegar?' map."
    )
    path: str = Field(default="", description="Or a www.unosalud.cl page path, in a new tab.")


# ─── Small helpers ─────────────────────────────────────────────────────────────

#: Chile's sixteen regions as the forms write them, and what a visitor calls them.
REGIONS: dict[str, tuple[str, ...]] = {
    "Arica y Parinacota": ("arica", "parinacota"),
    "Tarapacá": ("tarapaca", "iquique"),
    "Antofagasta": ("antofagasta", "calama"),
    "Atacama": ("atacama", "copiapo"),
    "Coquimbo": ("coquimbo", "la serena", "serena"),
    "Valparaíso": ("valparaiso", "vina", "vina del mar", "quilpue"),
    "Región Metropolitana": ("metropolitana", "santiago", "rm", "region metropolitana"),
    "O'Higgins": ("o'higgins", "ohiggins", "libertador", "rancagua"),
    "Maule": ("maule", "talca", "curico"),
    "Ñuble": ("nuble", "chillan"),
    "Biobío": ("biobio", "bio bio", "concepcion"),
    "La Araucanía": ("araucania", "temuco"),
    "Los Ríos": ("los rios", "valdivia"),
    "Los Lagos": ("los lagos", "puerto montt", "osorno"),
    "Aysén": ("aysen", "aisen", "coyhaique"),
    "Magallanes": ("magallanes", "punta arenas"),
}


def region_name(said: str) -> str | None:
    """The region ``said`` names, as the forms write it."""
    f = " ".join(re.findall(r"[a-z']+", fold(said)))
    if not f:
        return None
    for name, aliases in REGIONS.items():
        if fold(name) == f or any(f == a or a in f.split() or a in f for a in aliases):
            return name
    return None


#: The Convenio Empresas form's size options. There is no 50 to 200: the site lists 200 to 500 twice.
def company_size(n: int) -> str | None:
    if n <= 0:
        return None
    if n < 50:
        return "Menos de 50 Trabajadores"
    if n <= 500:
        return "Entre 200 a 500 trabajadores"
    if n <= 1000:
        return "Entre 500 a 1000 trabajadores"
    return "Más de 1000 trabajadores"


def mobile(said: str) -> str | None:
    """A Chilean celular as the booking takes it: nine digits starting with 9."""
    digits = "".join(c for c in said if c.isdigit())
    if len(digits) == 11 and digits.startswith("56"):
        digits = digits[2:]
    return digits if len(digits) == 9 and digits.startswith("9") else None


def nine_digits(said: str) -> str | None:
    """A Chilean phone as the Brevo forms take it: nine digits, without +56."""
    digits = "".join(c for c in said if c.isdigit())
    if len(digits) == 11 and digits.startswith("56"):
        digits = digits[2:]
    return digits if len(digits) == 9 else None


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
_SAID_DIGITS_MIN = 8


def said_digits(text: str) -> str:
    """The digits in what the visitor said, written, spoken one by one, or
    spoken in Spanish pairs ("nueve, ochenta y dos, …")."""
    out: list[str] = []
    toks = re.findall(r"\d+|[a-z]+", fold(text))
    i = 0
    while i < len(toks):
        token = toks[i]
        if token.isdigit():
            out.append(token)
        elif token in _SPANISH_TENS:
            tens = _SPANISH_TENS[token]
            unit = toks[i + 2] if i + 2 < len(toks) and toks[i + 1] == "y" else ""
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
    return " ".join(digits)


def email_address(said: str) -> str | None:
    address = "".join(said.split()).lower()
    return address if re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", address) else None


def iso_day(said: str | None) -> str | None:
    if not said:
        return None
    try:
        return date.fromisoformat(said.strip()[:10]).isoformat()
    except ValueError:
        return None


def hhmm(said: str | None) -> str | None:
    m = re.fullmatch(r"\s*(\d{1,2})[:.h](\d{2})(?::\d{2})?\s*(?:hrs?)?\s*", said or "")
    if m is None or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        return None
    return f"{int(m.group(1)):02d}:{m.group(2)}"


_DAYS_ES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MONTHS_ES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def day_es(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{_DAYS_ES[d.weekday()]} {d.day} de {_MONTHS_ES[d.month - 1]}"


def _said_day(day: str) -> str:
    iso = iso_day(day)
    return f"{iso} ({day_es(iso)})" if iso else day


def _clip(items: list[str] | tuple[str, ...], most: int) -> str:
    more = f"; and {len(items) - most} more" if len(items) > most else ""
    return "; ".join(items[:most]) + more


def _and(lang: Lang, items: list[str]) -> str:
    if len(items) < 2:
        return "".join(items)
    return f"{', '.join(items[:-1])} {'y' if lang == 'es' else 'and'} {items[-1]}"


def _match(want: str, options: list[str] | tuple[str, ...]) -> str | None:
    """The option ``want`` names: the same words, else the one it begins, else
    the one it is inside. Case, accents and punctuation do not count."""

    def folded(s: str) -> str:
        return " ".join(re.sub(r"[^\w\s]", " ", norm(s)).replace("_", " ").split())

    w = folded(want)
    if not w:
        return None
    pairs = [(folded(o), o) for o in options]
    for test in (
        lambda o: o == w,
        lambda o: o.startswith(w) and len(w) > 3,
        lambda o: w.startswith(o) and len(o) > len(w) // 2,
        lambda o: w in o and len(w) > 4,
    ):
        if (hit := next((o for f, o in pairs if f and test(f)), None)) is not None:
            return hit
    return None


def _phrase(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", fold(text)))


_KEY = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)+$")


# ─── The section a sentence describes ──────────────────────────────────────────

_STOP = frozenset(
    """a an the and or but of to in on for with by at from as is are was were be been it its
    this that these those you your yours we our us they their them he she his her i me my
    can will just also so then than too very here there what which who how when where why all
    any each every more most some such no not only own same into out up down over under again
    once about after before both few other per via do does did have has had get gets got make
    makes made use uses used like let lets want would shall could should see show shows one two
    three section page el la los las un una unos unas de del y o u en por para con sin que se
    su sus es son al lo le les como mas muy tu te ti mi nos este esta estos estas ese esa eso
    hay ser estan tiene tienen puedes puede quieres aqui alli tambien pero cuando donde
    uno salud dental clinica clinicas hora horas agenda agendar precio precios valor desde
    puedo tratamiento tratamientos""".split()  # noqa: SIM905
)
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
    heading, text) on one page; ``None`` unless it is clearly one (as Clini)."""
    if sentence.rstrip().endswith("?"):
        return None
    said = " ".join(re.findall(r"[a-z0-9']+", fold(sentence)))
    quoted = [
        (k, h)
        for k, h, _ in sections
        if h
        and len(phrase := re.findall(r"[a-z0-9']+", fold(h))) >= 2
        and re.search(rf"\b{re.escape(' '.join(phrase))}\b", said)
    ]
    if quoted:
        return max(quoted, key=lambda kh: len(kh[1]))[0]
    if len(sentence.split()) < _SECTION_MIN_WORDS:
        return None
    docs = [(k, set(_terms(h)), set(_terms(t))) for k, h, t in sections if k]
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


# ─── What the visitor asked about ──────────────────────────────────────────────

#: The page for what the visitor asked about, when his reply forgets to show
#: it. Matched on their own words, folded, in Spanish and English; the first
#: named wins. A bare "agendar" is in none: the booking opens in its own tab.
_ASKED_PAGES: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(rf"\b(?:{w})", re.IGNORECASE), path)
    for w, path in (
        (r"ortodonci|frenillo|bracket|alineador|braces|aligner", "/especialidades/ortodoncia/"),
        (r"implante|implant|diente atornillado", "/especialidades/implantes-dentales/"),
        (
            r"conducto|endodonci|root canal|nervio",
            "/especialidades/tratamiento-de-conducto-endodoncia/",
        ),
        (r"periodonci|encias|gums?\b|mal aliento|bad breath", "/especialidades/periodoncia/"),
        (
            r"odontopediatr|ninos?\b|ninas?\b|hijos?\b|hijas?\b|children|kids?\b|my son|my daughter",
            "/especialidades/odontopediatria/",
        ),
        (
            r"blanqueamiento|whitening|dientes (?:mas )?blancos",
            "/especialidades/blanqueamiento-dental/",
        ),
        (r"radiografia|rayos x|x-?rays?\b", "/especialidades/radiologia/"),
        (
            r"muelas? del juicio|wisdom tooth|wisdom teeth|extraccion|extraer|cirugia oral",
            "/especialidades/cirugia-oral/",
        ),
        (r"protesis|placa dental|dentures?|rehabilitacion", "/especialidades/rehabilitacion-oral/"),
        (
            r"bruxismo|aprieto los dientes|rechino|grinding|clench|plano de relajacion",
            "/especialidades/planos-de-relajacion-bruxismo/",
        ),
        (r"limpieza|destartraje|sarro|cleaning|tartar", "/especialidades/limpieza-dental/"),
        (r"urgencia|emergencia|emergency|urgent", "/urgencias/"),
        (r"plan(?:es)? sonrisa|sonrisa protegida", "/landing/planes-sonrisa-protegida/"),
        (r"promocion|promo\b|ofertas?\b|descuentos? del mes|deals?\b|offers?\b", "/promociones/"),
        (r"\bpad\b", "/beneficios-y-reembolso/pad/"),
        (r"\bges\b", "/beneficios-y-reembolso/ges/"),
        (r"excedentes?", "/beneficios-y-reembolso/excedentes/"),
        (
            r"seguro complementario|supplementary insurance",
            "/beneficios-y-reembolso/seguro-complementario/",
        ),
        (
            r"convenios?\b|isapre|fonasa|caja de compensacion|caja los andes|la araucana"
            r"|aseguradora|coopeuch",
            "/convenio/",
        ),
        (
            r"medios de pago|formas? de pago|cuotas|cheques?|tarjeta de credito|payment"
            r"|garantia",
            "/por-que-elegirnos/",
        ),
        (r"empresa|colaboradores|trabajadores|my company|employees", "/landing/convenio-empresa/"),
        (r"preguntas frecuentes|faq", "/preguntas-frecuentes/"),
        (r"quienes son|quienes somos|about (?:you|uno salud)|historia", "/quienes-somos/"),
        (
            r"\bsucursal|\bclinicas? (?:mas )?cerca|donde (?:queda|quedan|estan)|nearest|locations?\b"
            r"|ubicaciones|\bclinicas\b",
            "/clinicas/",
        ),
        (r"contacto|contactar|reclamo|call center", "/contactanos/"),
    )
)
_ASKED_TAB = re.compile(r"\b(?:tabs?|pestanas?)\b", re.IGNORECASE)
_BOOKING_WORDS = re.compile(
    r"\b(?:agend\w*|reserv\w*|horas?|citas?|book\w*|appointments?|slots?)\b"
)

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
    """Whether ``text`` asks him to speak another language (as Clini)."""
    return bool(_CALL_LANGUAGE.search(text) and _TO_HIM.search(text))


_SITE_MOVE = re.compile(
    r"\b(?:home ?page|main (?:site|website|page)|website|web ?site|site|page|pagina|sitio"
    r"|inicio|go back|take me|llevame|vuelve|volver|abre|open|muestrame|show me)\b",
    re.IGNORECASE,
)


def asks_site_move(text: str) -> bool:
    return bool(_SITE_MOVE.search(fold(text)))


_ABOUT_THE_CALL = re.compile(
    r"\b(?:can you hear me|are you there|me escuchas|me oyes|who are you|quien eres"
    r"|are you (?:a )?(?:bot|robot|real|human|ai)|eres (?:un )?(?:bot|robot|humano))\b",
    re.IGNORECASE,
)


def about_the_call(text: str) -> bool:
    short = len(text.split()) <= 12
    return short and (asks_call_language(text) or bool(_ABOUT_THE_CALL.search(fold(text))))


def asked_pages(text: str) -> list[str]:
    """Every site page ``text`` names, the first named first."""
    if _ASKED_TAB.search(fold(text)) or asks_call_language(text):
        return []
    said = fold(text)
    named = [(m.start(), path) for rx, path in _ASKED_PAGES if (m := rx.search(said))]
    return [path for _, path in sorted(named)]


def asked_page(text: str) -> str | None:
    named = asked_pages(text)
    return named[0] if named else None


#: Words of acute trouble: the floor for advice he must never improvise.
_ACUTE = re.compile(
    r"\b(?:dolor (?:fuerte|agudo|insoportable)|me duele mucho|no (?:pude|puedo) dormir"
    r"|hinchad\w*|hinchazon|pus|sangra mucho|se me (?:rompio|quebro|partio)|fractur\w*"
    r"|severe pain|swollen|swelling|broke(?:n)? (?:a |my )?tooth|can'?t sleep)\b"
)


def sounds_acute(text: str) -> bool:
    return bool(_ACUTE.search(fold(text)))


# ─── The prompt ────────────────────────────────────────────────────────────────

_TITLE_SUFFIX = re.compile(r"\s*\|\s*Uno Salud Dental.*$")
#: The places listed in the prompt, per page: the rest are in the site-map topic.
_PLACES_PER_PAGE = 14


def _short_title(title: str) -> str:
    return _TITLE_SUFFIX.sub("", title).strip()


def _places(k: Knowledge) -> str:
    """Every page, with the places a cue can show there by key; clinic rows and
    convenio logos are named by find_clinic and the convenios topic instead."""
    lines: list[str] = []
    for path, page in k.pages.items():
        if path.startswith("/landing/terminos"):
            continue
        anchors = [
            a
            for a in k.anchors.values()
            if a.path == path and not a.key.startswith(("clinicas_", "convenio_", "faq_"))
        ]
        title = _short_title(page.title)
        shown = "/clinicas/<clinic>/ (any clinic's page)" if path == CLINIC_PAGE else path
        lines.append(f"- {shown} — {title}")
        lines += [f"  - {a.key}: {a.es}" for a in anchors[:_PLACES_PER_PAGE]]
        if len(anchors) > _PLACES_PER_PAGE:
            lines.append(f"  - … {len(anchors) - _PLACES_PER_PAGE} more (topic mapa_del_sitio)")
    faq = [a for a in k.anchors.values() if a.path == "/preguntas-frecuentes/" and a.faq]
    if faq:
        lines.append("- FAQs on /preguntas-frecuentes/, by key:")
        lines += [f"  - {a.key}: {a.es}" for a in faq]
    return "\n".join(lines) or "(The site map is not loaded: find pages with search_site.)"


def _topics(k: Knowledge) -> str:
    return "\n".join(f"- {t.id}: {t.title}" for t in k.topics.values()) or "(none loaded)"


def _motivos(k: Knowledge) -> str:
    return "\n".join(f"- {m.id}: {m.name}" for m in k.motivos) or "(not loaded)"


def _promotions(k: Knowledge) -> str:
    out = []
    for p in k.promotions:
        until = f", until {p.valid_until}" if p.valid_until else ""
        out.append(f"- {p.key} ({p.card}{until}; place promo_{p.key} on /promociones/)")
    return "\n".join(out) or "(not loaded)"


def _prompt(k: Knowledge, today: date | None = None) -> str:
    today = today or datetime.now(TIMEZONE).date()
    return f"""You are {AGENT_NAME}, the voice guide on Uno Salud Dental's website, www.unosalud.cl. Uno Salud Dental is a Chilean network of 103 dental clinics. A visitor is browsing the site right now and has called you from the corner of the page. You can see and move their screen: you open pages, scroll to the exact place that answers them and ring it, open FAQs, find their nearest clinic, open the online booking in its own tab and walk them through it, and fill in the "Te llamamos" callback form or the Convenio Empresas form with them. You are warm, calm and reassuring — the friendly person at the clinic's front desk who knows every treatment, price and clinic, and makes a visit to the dentist feel easy, even for someone who is nervous about it.

# You narrate, and the screen follows your words
You are giving a guided walkthrough, like someone sitting beside the visitor with their screen in front of you both.
- Put a screen cue in your reply at the start of the sentence it belongs to. The page moves when your voice reaches that sentence. The visitor never hears a cue.
  - {{page: /path/}} opens a page of the site, at its top.
  - {{show: key}} scrolls to a place and rings it: a key from the places list below, on the page they are on or one a page cue opens. A key on another page opens that page too. With words the page shows instead of a key, it rings those words.
  - {{faq: key}} opens that FAQ and rings it, on whatever page it lives.
- Cues use keys and paths exactly as listed. Never make up a key or a path. They are the same in an English reply.
- One cue per sentence at most, and only where the screen should change. A cue goes before the sentence, never inside it.
- EVERY ANSWER ABOUT UNO SALUD STARTS WITH A CUE: a treatment's page, a price block, a promotion card, a clinic, a convenio, the FAQ. When they name a treatment, open its page and show the part that answers.
- Example, for "¿cuánto cuestan los brackets?": "{{show: ortodoncia_precios}} Los brackets metálicos parten en trescientos ochenta y tres mil quinientos pesos la instalación. {{show: ortodoncia_tab_metalicos}} Luego pagas cuarenta y seis mil novecientos pesos al mes por los controles. ¿Te agendo una evaluación?"

# A good turn
1. Answer what they asked, first, in plain words, and show it as you say it.
2. Add the one thing that matters for them: the price, a promotion that applies now, a convenio that lowers it, the nearest clinic.
3. End with one short, gentle offer of the next step: "¿Te agendo una hora de diagnóstico?", "¿Te busco la clínica más cerca?", "Want me to open the booking?". Never "anything else?".
- The next steps you offer, in this order of preference: (1) book a diagnosis online; (2) "Te llamamos", where an executive calls them back; (3) for pain or an accident, urgencias or the call center, 600 707 1010; (4) for a company, the Convenio Empresas form.
- Ask about them only when the answer changes what you show next, and offer the choices: "¿En qué comuna estás?", "¿Es para ti o para un niño?", "¿Tienes Fonasa o isapre?"

# How you sound
You are heard, not read.
- A turn is two to four short sentences. Every sentence under fifteen words. One idea and one number per sentence.
- THE FIRST SENTENCE IS A FEW WORDS, two to six, ending in a full stop, with the answer in it. A cue may come before it.
- Before most replies the visitor already heard a short acknowledgement of mine ("Claro.", "A ver.", "Happy to help."), so never open with one, and never repeat their question.
- Spoken words only, apart from cues: no lists, no markdown, no symbols, no exclamation marks.
- Every number, price, date and hour as spoken words. "$383.500" is "trescientos ochenta y tres mil quinientos pesos". "2026-10-31" is "el sábado treinta y uno de octubre". "16:30" is "a las cuatro y media de la tarde".
- A phone number is read digit by digit, never reshaped: 600 707 1010 is "seis cero cero, siete cero siete, uno cero uno cero" (in English "six oh oh, seven oh seven, one oh one oh"). A celular the visitor gave is read back digit by digit, exactly as they said it.
- Lines in square brackets come from their screen, not the visitor. Never read them out; use them.
- Always answer. A reply with no words leaves the visitor in silence.

# Spanish or English
You speak Spanish as a native of Latin America, and English. The call starts in Spanish unless the visitor chose English.
- Answer in the language the visitor speaks to you; your voice follows the language you write. Except when they chose a language (a bracket line says so): then keep it until they ask to switch.
- When they ask for the other language in words that are not already it, answer in that language and call set_language in the same response.
- One language per reply, and masculine forms for yourself ("encantado de ayudarte").
- Your Spanish is neutral Latin American Spanish, natural for a Chilean visitor, never the Spanish of Spain and never heavy slang:
  - "tú", never "usted" (even where the site says "usted"); "ustedes", never "vosotros", "os" or "queréis/tenéis/podéis".
  - Chile's words are right here: "agendar una hora" (an appointment is a "hora"), "previsión", "isapre", "Fonasa", "comuna", "sucursal" or "clínica", "frenillos" or "brackets", "muela del juicio", "tapadura", "presupuesto", "cuotas", "celular".
  - "celular", never "móvil"; "computadora", never "ordenador"; "mostrar" ("te muestro"), not "enseñar"; "completar", not "rellenar"; "¿Qué día te acomoda?", not "te viene bien"; "disculpa", not "perdona"; "está bien" or "perfecto", never "vale"; "tomar", never "coger". Write "video", never "vídeo".
  - On this site "cancelar" means to pay ("se cancelan las radiografías"): say "pagar" yourself.
  - For something just done, the simple past: "Abrí la reserva", not "He abierto".
- In English, say the site's Spanish names as written ("Planes Sonrisa Protegida", "Te llamamos", "isapre", "Fonasa", "RUT") and explain them in a few words when needed.

# A guide, not a dentist
- You never diagnose, never say which treatment someone needs, and never interpret symptoms beyond what the site says. "Eso lo ve el dentista en tu diagnóstico."
- Acute pain, swelling, a broken tooth, bleeding that will not stop: be calm and kind, say that is an urgency, show {{page: /urgencias/}}, give the hours, and offer to book with motivo 15 or to call 600 707 1010 (read digit by digit). Never home remedies or medicines. A general medical emergency (trouble breathing, a serious accident) is for the emergency services, not a dental clinic.
- Every fact comes from the knowledge below, a topic you read, search_site, find_clinic, or what the screen reported. Never from memory. A price, a promotion term or a date that is not there is not said: show the page or offer Te llamamos.
- Prices are "desde" and referential: say so once when you give one ("los valores pueden cambiar según tus beneficios"). A promotion is said with its end date; one past its date is not offered.

# Every response starts with words
Write your answer, with its cues, first; any tool call comes at the end of the same response.
- The reads — read_topic, search_site and find_clinic — come straight back to you in this same turn, but each makes the visitor wait. Answer from what you know below whenever it covers the question; read only for a detail that is not here, and then call the read first, with nothing written before it.
- The moves — open_booking, booking_pick, booking_scan, fill_booking_patient, fill_callback_form, fill_company_form, open_link — are not done when you call them: the page does them a moment later and tells you in square brackets. In the reply that calls one, say only what you are doing ("Te abro la reserva.", "Te marco la clínica."), never that it is done. When the page answers, say what it says happened.
- Never promise more to come ("déjame ver"): nothing comes after it.
- A question about the call itself — "can you speak English?", "who are you?" — gets an answer and nothing else.

# Booking a diagnosis (/agenda-tu-hora/)
The online booking books a "hora de diagnóstico" at a clinic. The diagnosis has no cost; X-rays are paid. Its first step belongs to the visitor, and you explain it kindly.
- When they want an hour, open_booking (with the promotion's key if they book for one). It opens in its own tab and rings the RUT field. That reply moves nothing on the site.
- Then, in your own warm words: they type the patient's RUT, tick "Acepto los Términos y Condiciones" and "No soy un robot", and press Continuar. Why, when they ask or hesitate: the RUT identifies the patient in their clinical record, the terms are their own consent, and the box proves a person is booking; the booking shows clinics and hours only after that, so you cannot look them up before. You never ask them to say their RUT, never repeat one, never write one.
- While they do it, you can already agree the motivo and the clinic: booking_pick with them is kept and taken as soon as the booking reaches those steps.
- A new patient sees "Registro de Nuevo Paciente": ask for name, apellido paterno, apellido materno, birth date, email and celular, and fill_booking_patient as they say them. Fill an email or a celular the moment they say it and read it back, the celular digit by digit. NEVER COUNT OR JUDGE THE DIGITS YOURSELF: pass exactly what they said; the tool checks it and tells you what is wrong. "Registrarse" is theirs to press.
- A known patient sees "Hola …, confirma o actualiza tus datos": greet them by the first name the booking shows, and with their yes, fill_booking_patient with confirm_existing.
- A patient who already has an hour booked is told so by the booking: say it kindly, and offer the call center (600 707 1010) or Te llamamos.
- The motivo: map what they tell you to one of the motivos below; when unsure, ask with two choices, or use 22 ("Chequeo y diagnóstico general") or 23 ("No estoy seguro"). Pain, a broken tooth or orthodontic trouble is 15. booking_pick with motivo.
- The clinic: find_clinic with their comuna, landmark or metro station; offer one or two by name and address; booking_pick with the clinic they choose.
- The day and hour: booking_pick with the day; the booking then lists that day's hours and you read two or three as words. "¿Qué días hay?" is booking_scan. Never an hour the booking did not list. booking_pick with the hour they choose takes them to the review.
- The review shows patient, date, hour, dentist, address and reference: read the date, hour and address back in one or two sentences. "Confirmar cita" STAYS THEIRS TO PRESS. Never say the hour is booked until the booking shows it is.
- One booking move at a time: when a tool says the booking is still working, the next step follows by itself.

# Te llamamos, urgencias and companies
- A visitor who prefers a call, cannot use the booking, or will not give a RUT online: offer Te llamamos. fill_callback_form with what they tell you (name, surnames, email, phone, region, comuna). It takes them to the form. The RUT they type themselves in the field you ring; ENVIAR is theirs to press.
- On /urgencias/ the same form is fill_callback_form with form urgencias.
- A company (HR, a manager) asking for a dental benefit: show {{page: /landing/convenio-empresa/}}, say plans start at nine hundred sixty-five pesos a month per employee, and offer to fill the form: fill_company_form with name, phone, email, company, region, job title, number of employees, comment. ENVIAR is theirs.

# Clinics
- "¿Dónde hay una clínica?", "la más cerca de Manuel Montt": find_clinic, then name one or two with their address. Show it: on /clinicas/ the row is {{show: clinicas_<key>}}; its own page is {{page: /clinicas/<slug>/}}. Each clinic's hours are on its own page: open it, and use the hours the page reports (a bracket line). The map is open_link with the clinic.

# Tabs
- The visitor may have several Uno Salud tabs: the site and the booking. Bracket lines say which are open and which is in front. "Volvamos a la reserva" is switch_tab.

# What you know
- Today is {today:%A, %d %B %Y}, in Santiago. "Mañana", "el lunes" and "next week" are counted from today.
- Topics for read_topic, when the knowledge below does not cover a question:
{_topics(k)}

# Uno Salud Dental
{k.l1}

# Motivos of the booking
{_motivos(k)}

# Promotions (read the topic promociones for their conditions before you offer one)
{_promotions(k)}

# Pages and places (keys for {{show: key}}; every page path ends in a slash)
{_places(k)}
"""


# ─── Greeting ──────────────────────────────────────────────────────────────────

_INTRO: dict[Lang, str] = {
    "es": f"Hola, soy {AGENT_NAME}, tu guía de voz de Uno Salud Dental.",
    "en": f"Hi, I'm {AGENT_NAME}, Uno Salud Dental's voice guide.",
}
_GREETING: dict[Lang, str] = {
    "es": "Te muestro el sitio, te busco tu clínica o te ayudo a agendar tu hora. "
    "¿En qué te ayudo?",
    "en": "I can show you around, find your nearest clinic, or help you book. "
    "What can I help with?",
}
#: The opener's second sentence for the page the call starts on, by a word in its path.
_OPENERS: tuple[tuple[str, dict[Lang, str]], ...] = (
    (
        "agenda-tu-hora",
        {
            "es": "Te acompaño con tu reserva paso a paso. ¿En qué te ayudo?",
            "en": "I can walk you through your booking step by step. What can I help with?",
        },
    ),
    (
        "ortodoncia",
        {
            "es": "Te cuento los tipos de brackets y sus precios. ¿Te muestro?",
            "en": "I can walk you through the types of braces and their prices. Shall I?",
        },
    ),
    (
        "implantes",
        {
            "es": "Te explico cómo es un implante y cuánto cuesta. ¿Te muestro?",
            "en": "I can explain how an implant works and what it costs. Shall I show you?",
        },
    ),
    (
        "especialidades",
        {
            "es": "Te explico nuestros tratamientos y te ayudo a agendar. ¿Qué buscas?",
            "en": "I can explain our treatments and help you book. What are you looking for?",
        },
    ),
    (
        "clinicas",
        {
            "es": "Te ayudo a encontrar tu clínica más cerca. ¿En qué comuna estás?",
            "en": "I can find the clinic closest to you. Which comuna are you in?",
        },
    ),
    (
        "urgencias",
        {
            "es": "Te ayudo a que te atiendan pronto. ¿Qué te está pasando?",
            "en": "I can help you get seen soon. What's going on?",
        },
    ),
    (
        "promociones",
        {
            "es": "Te cuento las promociones vigentes. ¿Qué tratamiento te interesa?",
            "en": "I can walk you through the current promotions. Which treatment interests you?",
        },
    ),
    (
        "planes-sonrisa-protegida",
        {
            "es": "Te explico los Planes Sonrisa Protegida. ¿Te muestro las diferencias?",
            "en": "I can explain the Sonrisa Protegida plans. Shall I show you the differences?",
        },
    ),
    (
        "convenio-empresa",
        {
            "es": "Te explico el convenio dental para empresas. ¿Te cuento cómo funciona?",
            "en": "I can explain the dental plan for companies. Shall I tell you how it works?",
        },
    ),
    (
        "convenio",
        {
            "es": "Te ayudo a ver tu descuento por convenio. ¿Tienes Fonasa, isapre o caja?",
            "en": "I can find your agreement discount. Are you with Fonasa, an isapre or a caja?",
        },
    ),
    (
        "solicitar-diagnostico",
        {
            "es": "Te ayudo a pedir que te llamemos. ¿Completamos el formulario juntos?",
            "en": "I can help you ask for a call back. Shall we fill in the form together?",
        },
    ),
)


def greeting(path: str | None, lang: Lang = OPENING) -> str:
    """The written opener, in ``lang``, tailored to the page the call starts on."""
    here = canonical_path(path or "/")
    line = next((lines[lang] for word, lines in _OPENERS if word in here), _GREETING[lang])
    return f"{_INTRO[lang]} {line}"


# ─── Written lines for moves ───────────────────────────────────────────────────

_LANDED: dict[str, dict[Lang, str]] = {
    "shown": {"en": "Here it is.", "es": "Aquí lo tienes."},
    "tab": {"en": "There's that tab.", "es": "Ahí tienes esa pestaña."},
    "booking": {
        "en": "I'm opening the booking in its own tab.",
        "es": "Te abro la reserva en su propia pestaña.",
    },
    "pick": {"en": "I'm selecting that on the booking.", "es": "Te lo marco en la reserva."},
    "scan": {
        "en": "I'm checking the next days on the booking.",
        "es": "Reviso los próximos días en la reserva.",
    },
    "kept": {
        "en": "I'll select that as soon as the booking gets there.",
        "es": "Lo marco apenas la reserva llegue a ese paso.",
    },
    "queued": {
        "en": "I'll do that as soon as the booking is ready.",
        "es": "Lo hago apenas la reserva esté lista.",
    },
    "patient": {
        "en": "I'm filling that in on the booking form.",
        "es": "Te lo completo en el formulario de la reserva.",
    },
    "callback": {
        "en": "I'm filling that in on the call-back form.",
        "es": "Te lo completo en el formulario para que te llamen.",
    },
    "company": {
        "en": "I'm filling that in on the company form.",
        "es": "Te lo completo en el formulario de empresas.",
    },
    "link": {"en": "I've opened it in a new tab.", "es": "Lo abrí en una pestaña nueva."},
}
_FIELD_NAMES: dict[Lang, dict[str, str]] = {
    "es": {
        "nombre": "tu nombre",
        "paterno": "tu apellido paterno",
        "materno": "tu apellido materno",
        "apellidos": "tus apellidos",
        "birth_date": "tu fecha de nacimiento",
        "phone": "tu celular",
        "email": "tu correo",
        "region": "tu región",
        "comuna": "tu comuna",
    },
    "en": {
        "nombre": "your name",
        "paterno": "your first surname",
        "materno": "your second surname",
        "apellidos": "your surnames",
        "birth_date": "your birth date",
        "phone": "your phone",
        "email": "your email",
        "region": "your region",
        "comuna": "your comuna",
    },
}
_DIGIT_NAMES: dict[Lang, tuple[str, ...]] = {
    "es": ("cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve"),
    "en": ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"),
}
_ASK_AGAIN: dict[str, dict[Lang, str]] = {
    "phone": {
        "es": "Ese número no calza: el formulario pide nueve dígitos. ¿Me lo repites?",
        "en": "That number doesn't fit: the form needs nine digits. Could you say it again?",
    },
    "email": {
        "es": "No me quedó claro tu correo. ¿Me lo deletreas?",
        "en": "I didn't quite get your email. Could you spell it for me?",
    },
    "birth_date": {
        "es": "¿Me repites tu fecha de nacimiento?",
        "en": "Could you tell me your birth date again?",
    },
    "region": {
        "es": "¿En qué región estás?",
        "en": "Which region are you in?",
    },
    "": {
        "es": "Todavía no tengo ese dato para el formulario. ¿Me lo repites?",
        "en": "I didn't get that for the form yet. Could you say it again?",
    },
}

_PROMISE = re.compile(
    r"\b(?:just |one |un )?(?:moment|momento|momentito|second|segundo)\b"
    r"|\blet me (?:see|check|look)(?: (?:that|into it|at that))?\b|\bdéjame ver\b|\ba ver\b",
    re.IGNORECASE,
)

# ─── His nod ───────────────────────────────────────────────────────────────────

#: Only lines measured to come out in Javier's own voice (Clini's measured set
#: for this bake of omnivoice/javier): measure a new line before adding it.
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
        "statement": ("Entendido, eso me ayuda.", "Claro."),
    },
}
ACK_RATE = 0.75
ACK_HOLD_AFTER_S = 5.75
HOLD_WITHOUT_NOD_S = 3.2
ACK_SORRY_AFTER_S = 15.0
_ACK_HOLD: dict[Lang, tuple[str, ...]] = {
    "en": ("Just a moment.", "One moment while I check that for you."),
    "es": ("Dame un momento mientras lo busco.", "Un momento mientras lo reviso para ti."),
}
_ACK_SORRY: dict[Lang, str] = {
    "en": "Sorry, that's taking a little longer.",
    "es": "Lo siento, está tardando un poco más de lo normal.",
}
_ACK_WORDS = Vocabulary(
    common=frozenset(
        """uno salud dental dentista odontologo clinica clinicas sucursal hora horas agenda
        agendar reservar reserva cita diagnostico evaluacion limpieza ortodoncia frenillos
        brackets alineadores implante implantes muela muelas diente dientes encias conducto
        endodoncia blanqueamiento radiografia radiografias protesis bruxismo urgencia
        urgencias dolor convenio convenios fonasa isapre caja previsión precio precios valor
        cuotas promocion promociones plan planes rut comuna region santiago providencia
        maipu florida concepcion temuco antofagasta appointment booking clinic dentist
        teeth tooth braces implant cleaning whitening price prices emergency
        """.split()  # noqa: SIM905
    ),
)


@dataclasses.dataclass
class _LateFloor:
    ack: Acknowledger[Lang]
    nod: str | None
    hold_after_s: float
    sorry_after_s: float

    @property
    def sorry(self) -> dict[Lang, str]:
        return _ACK_SORRY

    def hold(self, spoken: Lang) -> str:
        return self.nod or self.ack.hold(spoken)


_WANTS = re.compile(
    r"\b(?:me gustaria|quiero|quisiera|necesito|i'?d like|i want|i need|i would like)\b"
)
_CLOSING = re.compile(r"\b(?:gracias|adios|chao|chau|thanks|thank you|bye|goodbye)\b")


def nod_kind(text: str) -> Kind | None:
    kind = classify(text, _ACK_WORDS)
    if kind in ("statement", "correction") and _WANTS.search(fold(text)):
        return "request"
    return kind


def is_closing(text: str) -> bool:
    return "?" not in text and bool(_CLOSING.search(fold(text)))


class _Nods(Acknowledger[Lang]):
    def line(self, text: str, spoken: Lang) -> str | None:
        kind = nod_kind(text)
        lines = self.lines.get(spoken, {}).get(kind) if kind else None
        if not lines or self.rng.random() >= self.rate:
            return None
        return self._pick(lines)


def _late_nod(text: str, spoken: Lang) -> str | None:
    kind = nod_kind(text)
    lines = _ACK_LINES[spoken].get(kind) if kind else None
    return random.choice(lines) if lines else None


def _avatar_state(session: Session, state: Literal["WORKING"] | None) -> None:
    session.send_rtvi(RTVIType.SERVER_MESSAGE, {"type": "avatar", "cmd": "state", "state": state})


async def _silence() -> AsyncGenerator[Any, None]:
    for _ in ():
        yield


#: Set while a turn runs with tools off: a call the model makes anyway is not
#: run (Clini, prod 2026-10-22: an idle turn's call took a form down).
_TOOLS_OFF: ContextVar[bool] = ContextVar("unosalud_tools_off", default=False)


async def _tools_off(turn: AsyncGenerator[Speech, None]) -> AsyncGenerator[Speech, None]:
    token = _TOOLS_OFF.set(True)
    try:
        async for event in turn:
            yield event
    finally:
        await turn.aclose()
        with contextlib.suppress(ValueError):
            _TOOLS_OFF.reset(token)


# ─── The booking ───────────────────────────────────────────────────────────────

#: The moves on the booking's tab, one at a time.
_BOOKING_MOVES = frozenset({"open_booking", "booking_pick", "booking_scan", "fill_booking_patient"})
#: The commands whose failure cancels the talk-through they would have had.
_FORM_COMMANDS = _BOOKING_MOVES | {"fill_callback_form", "fill_company_form", "open_link"}
#: How long a move may take on the page before the next one stops waiting for it:
#: each booking step is a server round trip, a scan is several.
_MOVE_TAKES_S = {"open_booking": 20.0, "booking_pick": 30.0, "booking_scan": 45.0, "": 8.0}
_PLAYOUT_MAX_S = 30.0
_TIMES_IN_NOTE = 24
_HEADINGS_IN_NOTE = 30
_SEARCH_HITS = 6
_CLINIC_HITS = 4

_STEP_NAMES: dict[str, str] = {
    "getPAC": "its first step: the patient's RUT, the terms and the 'No soy un robot' box, for "
    "the visitor to complete",
    "setPAC": "the new patient form (Registro de Nuevo Paciente)",
    "setEF": "the known patient's step (confirm or update email and phone)",
    "notsetRH": "a message that this patient already has an hour booked (call 600 707 1010)",
    "getMRes": "the motivo step (¿Cuál es el motivo de la cita?)",
    "getSuc": "the clinic step (region, comuna, clinic)",
    "getHor": "the day-and-hour step",
    "getDC": "the review, with 'Confirmar cita' for the visitor to press",
    "setRH": "the confirmation: the hour is booked",
    "unknown": "a step it could not read",
}
#: The steps in order, for what is still ahead.
_STEP_ORDER = ("getPAC", "setPAC", "setEF", "getMRes", "getSuc", "getHor", "getDC", "setRH")


def _booking_note(event: BookingState, k: Knowledge) -> str:
    note = f"[The booking shows {_STEP_NAMES.get(event.step, event.step)}."
    if event.step == "getPAC":
        note += " The RUT is typed." if event.rut_entered else " No RUT typed yet."
    if event.patient_first_name:
        note += (
            f" The patient's first name, as the booking greets them: {event.patient_first_name}."
        )
    if event.motivo and (m := k.motivo(event.motivo)) is not None:
        note += f" Motivo: {m.id} {m.name}."
    if event.sucursal:
        note += f" Clinic: {event.sucursal}" + (f", {event.comuna}" if event.comuna else "") + "."
    if event.days:
        days = [f"{_said_day(d.date)}: {', '.join(d.times[:8]) or 'none'}" for d in event.days]
        note += f" Open days read: {_clip(days, 7)}."
    if event.date:
        note += f" Day selected: {_said_day(event.date)}."
        if event.slots:
            note += f" Its hours: {_clip(event.slots, _TIMES_IN_NOTE)}."
        elif event.no_slots:
            note += " That day has no free hours."
    if event.summary is not None:
        s = event.summary
        note += (
            f" Review: fecha {s.fecha}, hora {s.hora}, odontólogo {s.odontologo}, "
            f"dirección {s.direccion}, referencia {s.referencia}. 'Confirmar cita' is the "
            "visitor's to press."
        )
    if event.error:
        note += f" The booking shows an error: {event.error}."
    if event.booked:
        note += " It is booked."
    return note + "]"


# ─── The brain ─────────────────────────────────────────────────────────────────


@dataclasses.dataclass
class _Wanted:
    """What the visitor chose for the booking before it reached that step: taken
    as soon as it does."""

    motivo: int = 0
    clinic: Clinic | None = None
    date: str = ""
    time: str = ""

    def any(self) -> bool:
        return bool(self.motivo or self.clinic or self.date or self.time)


class UnoSaludBrain(GeminiBrain):
    """One per session. Javier: Uno Salud's knowledge, its pages, and a mirror of
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
        self.spoken: Lang = OPENING
        self._chosen = False
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
        #: The tab in front as it last reported itself.
        self.page: PageChanged | None = None
        self._path = "/"
        self._page_unseen = False
        self.tabs: list[TabInfo] = []
        self._active = ""
        self._tabs_unseen = False
        self._talk: str | None = None
        #: The booking as its tab last reported it; what the visitor gave for it
        #: (never a RUT); and whether a step he took is waiting to be talked through.
        self.booking: BookingState | None = None
        self._patient: dict[str, str] = {}
        self._booking_asked = False
        self._wanted = _Wanted()
        self.callback: CallbackFormState | None = None
        self._callback_fields: dict[str, str] = {}
        self._callback_asked = False
        self.company: CompanyFormState | None = None
        self._company_fields: dict[str, str] = {}
        self._company_asked = False
        #: The page this turn's cues are on; ``None`` on the booking.
        self._cue_path: str | None = None
        self._idle_short = False
        self._nudges = 0
        self._backstop: str | None = None
        self._paged = False
        self._shown: str | None = None
        self._opened_booking = False
        self._asked_site = False
        self._heard: list[str] = []
        self._sent: dict[str, float] = {}
        self._outcomes: list[str] = []
        self._queued: Action | None = None
        self._turns = 0
        self._playing = 0
        self._played_at = 0.0
        self._idle_deferred = False
        self._led: str | None = None
        self._patience = UNOSALUD_PATIENCE

    # ─── Callbacks ──────────────────────────────────────────────────────

    @property
    def _on_booking(self) -> bool:
        return canonical_path(self._path) == BOOKING_PATH

    async def on_session_start(self, session: Session) -> None:
        init = session.init or {}
        self._path = canonical_path(str(init.get("path") or "/"))
        chosen = init.get("lang")
        self._chosen = chosen in LANGUAGE_NAMES
        self.spoken = "en" if chosen == "en" else OPENING
        await session.configure(
            Config(
                stt=SttConfig(language=self.spoken, patience=self._patience),
                tts=TtsConfig(voice=VOICE, language=self.spoken),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
            )
        )
        logger.info(
            "unosalud: session start on {} in {}{}",
            self._path,
            self.spoken,
            " (chosen)" if self._chosen else "",
        )
        if self._chosen:
            self._note(_chosen_note(self.spoken, "before the call"))

    async def greet(self, session: Session) -> str:
        line = greeting(self._path, self.spoken)
        return for_the_voice(line) if self.spoken == "es" else line

    async def on_finalize(self, session: Session, fin: Finalize) -> None:
        if "idéo" in fin.heard:
            fin = dataclasses.replace(fin, heard=from_the_voice(fin.heard))
        await super().on_finalize(session, fin)
        self._playing = max(0, self._playing - 1)
        self._floor_free()

    def on_user_message(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]:
        return self._own_turn(self._answer(session, msg))

    async def _answer(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]:
        """As Clini: the language they speak, the screen read in, his nod, and
        the floor held through the model's thinking."""
        heard = None if self._chosen else language_of(msg.text)
        if heard is not None and heard != self.spoken:
            await session.configure(self._speaking(heard))
            logger.info("unosalud: language -> {} (heard)", heard)
        self._talk = None
        self._led = None
        self._outcomes.clear()
        self._idle_deferred = False
        self._playing = 0
        self._nudges = 0
        self._heard = [*self._heard[-3:], msg.text]
        self._asked_site = asks_site_move(msg.text)
        # A booking ask is answered in the booking's own tab: a site page opened
        # first would pull the visitor off it.
        self._backstop = (
            None
            if asks_call_language(msg.text) or _BOOKING_WORDS.search(fold(msg.text))
            else asked_page(msg.text) or self._backstop
        )
        if sounds_acute(msg.text):
            self._note(
                "[What they said sounds like a dental urgency. Be calm and kind; never diagnose "
                "or suggest medicines. Show /urgencias/, give the clinics' hours, and offer a "
                "booking with motivo 15 or the call center, 600 707 1010, read digit by digit.]"
            )
        self._restore_idle()
        self._read_in_screen()
        now = time.monotonic()
        fragment, self._heard_at = now - self._heard_at < _FRAGMENT_S, now
        nod = None if fragment else self._ack.line(msg.text, self.spoken)
        floor: Floor[Lang] = self._ack
        lead = self._lead(msg.text)
        if nod is not None:
            logger.info("unosalud: ack {!r}", nod)
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
        """A quiet spell: what the page did, talked through (tools off), else a
        nudge, twice, then silence (as Clini)."""
        self._restore_idle()
        self._backstop = None
        self._led = None
        self._asked_site = False
        if (ask := self._take_ask()) is not None:
            self._booking_asked = self._callback_asked = self._company_asked = False
            self._note(ask)
            return self._reply(session, ToolChoice.NONE)
        if self._confirm is not None:
            line, self._confirm = self._confirm, None
            return say_line(self, line)
        if self._nudges >= _IDLE_NUDGES:
            return _silence()
        if (running := self._busy()) is not None:
            logger.info("unosalud: quiet while {} is under way; no nudge", running)
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
            if self.booking is not None and self.booking.step == "getPAC" and self._on_booking:
                ask = (
                    "They are on the booking's first step. Gently remind them, in one or two "
                    "sentences, that the RUT, the terms and 'No soy un robot' are theirs, then "
                    "Continuar; and that you take it from there."
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
        """The model's turn, with its cues taken out and sent; the toggle's
        confirmation first; the floor under a silent move; one more ask when
        the turn said nothing at all (as Clini)."""
        if (line := self._confirm) is not None:
            self._confirm = None
            async for event in say_line(self, line):
                yield event
        self._cue_path = None if self._on_booking else self._path
        if self._led is not None:
            self._cue_path = self._led
        self._paged = False
        self._shown = None
        self._opened_booking = False
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
        if not _PROMISE.sub("", _CUE_TEXT.sub(" ", said)).strip(" .,!?¡¿…"):
            logger.warning("unosalud: the model returned nothing; asking once more")
            again = self._written(session, self._cued(self._talk_now(session)))
            async for event in self._spelled(again):
                yield event

    async def _written(
        self, session: Session, turn: AsyncGenerator[Speech, None]
    ) -> AsyncGenerator[Speech, None]:
        """Each unit held back until its first sentence is in, and both legs
        moved to the language it is in (as Clini)."""
        held: list[Speech] = []
        text = ""

        async def release() -> AsyncGenerator[Speech, None]:
            nonlocal held, text
            written = language_of(text, sure=False)
            if written is not None and written != self.spoken:
                await session.configure(self._speaking(written))
                logger.info("unosalud: language -> {} (written)", written)
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
        async def spelled() -> AsyncGenerator[Speech, None]:
            async for event in turn:
                if isinstance(event, SpeechChunk) and self.spoken == "es":
                    event = SpeechChunk(for_the_voice(event.text))
                yield event

        return spelled()

    async def _cued(self, turn: AsyncGenerator[Speech, None]) -> AsyncGenerator[Speech, None]:
        """``turn`` with every ``{page|show|faq: …}`` taken out of its text and
        sent to the page as a :class:`Cue`."""
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
                else:
                    rest, raw = parser.flush()
                    for cue in raw:
                        self._send_cue(cue, first_unit=units <= 1)
                    if rest:
                        yield SpeechChunk(rest)
                yield event
        finally:
            await turn.aclose()

    def _with_backstop(self, chunk: str) -> str:
        """The page the visitor asked about, cued in front of a reply that brings no cue."""
        if self._backstop is None or not chunk.strip():
            return chunk
        path, self._backstop = self._backstop, None
        if "{" in chunk or self._on_booking or self._opened_booking or path == self._path:
            return chunk
        logger.info("unosalud: the reply has no cue; showing {} first", path)
        return f"{{page: {path}}}{chunk}"

    def _lead(self, text: str) -> str | None:
        """The page to open while his nod plays (as Clini): not for a booking
        ask, a question about the call, or one the page in front answers."""
        path = self._backstop
        if (
            path is None
            or self._on_booking
            or path == self._path
            or self.kb.page(path) is None
            or _BOOKING_WORDS.search(fold(text))
            or about_the_call(text)
            or self._path in asked_pages(text)
            or self._section_for(text.rstrip(" ?!."), self._path) is not None
        ):
            return None
        return path

    def _send_lead(self, path: str, when: Literal["nod", "now"]) -> None:
        self._led = path
        logger.info("unosalud: opening {} ahead of the answer ({})", path, when)
        self.session.dispatch(Cue(at="", path=path, lead=when))

    def _send_cue(self, raw: RawCue, *, first_unit: bool = False) -> None:
        """Check a cue against the catalogue and send it; one that names nothing
        real is dropped and logged."""
        if self.spoken == "es" and raw.at:
            raw = dataclasses.replace(raw, at=_anchor_for_voice(raw.at))
        if self._opened_booking:
            logger.info("unosalud: cue {} {!r} dropped: the booking opened", raw.kind, raw.value)
            return
        cue = self._resolve_cue(raw)
        if cue is not None and cue.path and self._on_booking and not self._asked_site:
            logger.info(
                "unosalud: cue {} {!r} dropped: the booking is in front", raw.kind, raw.value
            )
            return
        if cue is not None and raw.kind == "page" and self._led is not None:
            led, self._led = self._led, None
            if cue.path == led:
                logger.info("unosalud: {} was opened ahead of the answer", led)
                self._paged = True
                return
        first = raw.kind == "page" and raw.word == 0 and first_unit and not self._paged
        if cue is not None and first:
            cue = cue.model_copy(update={"lead": "now"})
        logger.info("unosalud: cue {} {!r} at {!r} -> {}", raw.kind, raw.value, raw.at, cue)
        if cue is not None:
            self._paged = self._paged or bool(cue.path)
            if raw.kind in ("show", "faq"):
                self._shown = cue.anchor or cue.faq or cue.text
            self.session.dispatch(cue)

    def _auto_cues(
        self, sentence: str, index: int, placed: tuple[tuple[CueKind, str], ...]
    ) -> list[tuple[CueKind, str]]:
        """The moves a sentence of his needs and did not bring: the page its
        first sentence is about, and the place on the page it describes."""
        out: list[tuple[CueKind, str]] = []
        kinds = {k for k, _ in placed}
        pages = [canonical_path(v) for k, v in placed if k == "page" and self._known_page(v)]
        path = pages[-1] if pages else self._cue_path
        if (
            index == 0
            and not self._paged
            and not self._opened_booking
            and not kinds
            and self._shown is None
            and not self._on_booking
        ):
            asked = asked_page(sentence)
            if (
                asked is not None
                and asked != self._path
                and self.kb.page(asked) is not None
                and self._section_for(sentence, self._path) is None
            ):
                logger.info("unosalud: he talks about {} with no cue; opening it", asked)
                out.append(("page", asked))
                path = asked
        self._cue_path = path
        if kinds & {"show", "faq"}:
            return out
        shown = self._section_for(sentence, path)
        if shown is not None and shown != self._shown:
            out.append(("show", shown))
        return out

    def _section_for(self, sentence: str, path: str | None) -> str | None:
        """The anchor key on ``path`` that ``sentence`` is about: a place it
        names (a clinic, a card), else the block it describes."""
        if path is None:
            return None
        anchors = self.kb.anchors_on(path)
        if not anchors:
            return None
        said = f" {_phrase(sentence)} "
        for a in anchors:
            name = re.sub(r"^(?:Tarjeta|Clínica|Logo) ", "", a.es)
            if a.key.startswith(("clinicas_", "especialidades_card_", "home_card_", "promo_")) and (
                len(_phrase(name)) > 4 and f" {_phrase(name)} " in said
            ):
                return a.key
        page = self.kb.page(path)
        texts = {s.anchor: s.text for s in page.sections} if page is not None else {}
        sections = [
            (a.key, a.es, texts.get(a.key, ""))
            for a in anchors
            if not a.faq and not a.key.startswith(("clinicas_", "convenio_"))
        ]
        return best_section(sentence, sections)

    def _known_page(self, path_or_url: str) -> bool:
        path = canonical_path(path_or_url)
        if path == BOOKING_PATH:
            return False
        if is_clinic_page(path):
            return self.kb.clinic_by_path(path) is not None
        return path in self.kb.pages

    def _resolve_cue(self, raw: RawCue) -> Cue | None:
        if raw.kind == "page":
            if not self._known_page(raw.value):
                return None
            path = canonical_path(raw.value)
            self._cue_path = path
            return Cue(at=raw.at, word=raw.word, path=path)
        here = self._cue_path or self._path
        moved = here != self._path
        if raw.kind == "faq":
            a = self._faq_anchor(raw.value, here)
            if a is None:
                return None
            if self.kb.anchor_on(a.key, here):
                return Cue(at=raw.at, word=raw.word, path=here if moved else "", faq=a.key)
            self._cue_path = a.path
            return Cue(at=raw.at, word=raw.word, path=a.path, faq=a.key)
        # show: a key; a place on this page by its label; else words this page shows.
        value = raw.value.strip()
        a = self.kb.anchor(value) if _KEY.match(value) else None
        if a is None:
            on_here = self.kb.anchors_on(here)
            hit = _match(value, [x.es for x in on_here]) or _match(value, [x.key for x in on_here])
            a = next((x for x in on_here if hit in (x.es, x.key)), None)
        if a is not None:
            if self.kb.anchor_on(a.key, here):
                return Cue(at=raw.at, word=raw.word, path=here if moved else "", anchor=a.key)
            if a.path == CLINIC_PAGE:
                logger.info("unosalud: {} is on a clinic's page, not on {}", a.key, here)
                return None
            self._cue_path = a.path
            return Cue(at=raw.at, word=raw.word, path=a.path, anchor=a.key)
        if _KEY.match(value):
            logger.info("unosalud: no place {!r}; dropped", value)
            return None
        if not self._on_page(value, here):
            logger.info("unosalud: {!r} is not on {}; not cued", value, here)
            return None
        return Cue(at=raw.at, word=raw.word, path=here if moved else "", text=value[:120])

    def _faq_anchor(self, value: str, here: str) -> Anchor | None:
        v = value.strip()
        if (a := self.kb.anchor(v)) is not None and a.faq:
            return a
        faqs = [a for a in self.kb.anchors.values() if a.faq]
        local = [a for a in faqs if self.kb.anchor_on(a.key, here)]
        for pool in (local, faqs):
            if (q := _match(v, [a.es for a in pool])) is not None:
                return next(a for a in pool if a.es == q)
        return None

    def _on_page(self, text: str, path: str) -> bool:
        """Whether the words ``text`` are on ``path`` as the research read it;
        true when there is nothing to check against."""
        page = self.kb.page(path)
        if page is None or not page.sections:
            return True
        want = _phrase(text)
        parts = [page.title, *(f"{s.heading} {s.text}" for s in page.sections)]
        parts += [f"{f.q} {f.a}" for f in page.faqs]
        parts += [a.es for a in self.kb.anchors_on(path)]
        return bool(want) and f" {want} " in f" {_phrase(' '.join(parts))} "

    def _talk_now(self, session: Session) -> AsyncGenerator[Speech, None]:
        return _tools_off(self.respond_with(session, tools=ToolChoice.NONE))

    async def _run(self, tool: Any, call: types.FunctionCall) -> types.Part:
        """Tools off means not run; flat arguments are wrapped in ``request`` (as Clini)."""
        if _TOOLS_OFF.get():
            logger.warning("unosalud: {} called on a turn with tools off; not run", call.name)
            return types.Part(
                function_response=types.FunctionResponse(
                    id=call.id,
                    name=call.name,
                    response={
                        "result": "Not run: this turn could only speak, so nothing was sent to "
                        "the page. Never say it was done."
                    },
                )
            )
        args = dict(call.args or {})
        if (
            tool is not None
            and args
            and "request" not in args
            and "request" in inspect.signature(tool).parameters
        ):
            logger.info("unosalud: {} called with flat arguments; wrapping them", call.name)
            call = call.model_copy(update={"args": {"request": args}})
        return await super()._run(tool, call)

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Page→brain events, folded in silently: no floor taken, no turn."""
        event = UNOSALUD_EVENTS.parse(msg)
        if event is None:
            return
        logger.info("unosalud: {} — {}", type(event).__voqal_event__, event)
        if isinstance(event, LanguageRequested):
            await self._requested(session, event)
            return
        if (note := self.apply_event(event)) is not None:
            self._note(note)

    async def _requested(self, session: Session, event: LanguageRequested) -> None:
        """The toggle: switched in code, confirmed in his next turn (as Clini)."""
        if event.language == self.spoken:
            return
        was = self.spoken
        try:
            await session.configure(self._speaking(event.language))
        except RequestRejected as rejected:
            logger.warning("unosalud: switch to {} refused: {}", event.language, rejected)
            self.spoken = was
            session.dispatch(LanguageChanged(language=was))
            return
        logger.info("unosalud: language -> {} (toggle)", event.language)
        self._chosen = True
        self._confirm = TOGGLE_CONFIRM[event.language]
        self._shorten_idle()
        self._note(_chosen_note(event.language, "on the toggle"))

    def _speaking(self, language: Lang) -> Config:
        if language != self.spoken:
            self.session.dispatch(LanguageChanged(language=language))
        self.spoken = language
        return Config(
            stt=SttConfig(language=language, patience=self._patience),
            tts=TtsConfig(voice=VOICE, language=language),
        )

    # ─── Page → brain ───────────────────────────────────────────────────

    def apply_event(self, event: UnoSaludEvent) -> str | None:
        """Patch the mirror; return the line the model should see."""
        match event:
            case PageChanged():
                self.page = event
                self._path = canonical_path(event.path)
                self._page_unseen = True
                return None
            case TabsChanged():
                self.tabs = event.tabs
                self._active = event.active
                self._tabs_unseen = True
                return None
            case BookingState():
                return self._booking_changed(event)
            case CallbackFormState():
                return self._callback_changed(event)
            case CompanyFormState():
                return self._company_changed(event)
            case LanguageRequested():
                return None
            case CommandDone():
                detail = event.detail or "done"
                self._answered(event.command, f"{event.command} done: {detail}")
                return f"[The page confirms {event.command}: {detail}.]"
            case CommandFailed() if event.command == "cue":
                return (
                    f"[A screen cue of yours did not land ({event.reason}). If the visitor "
                    "asks where it is, show it again; otherwise carry on.]"
                )
            case CommandFailed():
                if event.command in _FORM_COMMANDS:
                    self._talk = None
                    self._booking_asked = self._callback_asked = self._company_asked = False
                    self._restore_idle()
                self._answered(event.command, f"{event.command} not done: {event.reason}")
                return (
                    f"[Not done on the page ({event.command}): {event.reason}. Tell the visitor "
                    "plainly and offer what you can do instead; never say it worked.]"
                )

    def _booking_changed(self, event: BookingState) -> str:
        """The booking's report, as a note; the step's talk-through; and any
        choice the visitor made earlier, taken now that its step is on screen."""
        before = self.booking
        self.booking = event
        self._dictation()
        note = _booking_note(event, self.kb)
        new_step = before is None or before.step != event.step
        if new_step:
            self._take_wanted(event)
        ask: str | None = None
        if event.booked or event.step == "setRH":
            ask = (
                "The booking shows the hour as booked. Congratulate them warmly in one "
                "sentence and say the day, hour and clinic back as words. If a payment link "
                "appears, it is theirs: never follow it."
            )
        elif event.error and (before is None or before.error != event.error):
            ask = (
                f"The booking shows an error ({event.error}). Say in a sentence what it says, "
                "kindly, and what they can do; offer Te llamamos or 600 707 1010 if it blocks them."
            )
        elif event.step == "notsetRH" and new_step:
            ask = (
                "The booking says this patient already has an hour booked, and to call. Say so "
                "kindly, read the call center 600 707 1010 digit by digit, and offer Te llamamos."
            )
        elif not self._booking_asked and not new_step:
            ask = None
        elif event.step == "getPAC" and new_step:
            ask = (
                "The booking is open at its first step, and its RUT field is ringed. In two "
                "warm sentences: they type the patient's RUT, tick the terms and 'No soy un "
                "robot', and press Continuar; you take it from there. If they hesitate, say "
                "why: the RUT identifies the patient's clinical record, the terms are their "
                "consent, and the box proves a person is booking."
            )
        elif event.step == "setPAC" and new_step:
            ask = (
                "The booking asks for a new patient's details. Say so in one sentence and ask "
                "for their name and both surnames first; you fill them in as they say them "
                "(fill_booking_patient). 'Registrarse' is theirs to press."
            )
        elif event.step == "setEF" and new_step:
            ask = (
                "The booking knows this patient"
                + (f" ({event.patient_first_name})" if event.patient_first_name else "")
                + ". Greet them by their first name and ask whether their email and phone are "
                "still right; with their yes, fill_booking_patient with confirm_existing."
            )
        elif event.step == "getMRes" and new_step and not self._wanted.motivo:
            ask = (
                "The booking asks the motivo of the visit. Ask in one sentence what they want "
                "to see the dentist for, offering two likely motivos."
            )
        elif event.step == "getSuc" and new_step and self._wanted.clinic is None:
            ask = (
                "The booking asks for the clinic. Ask which comuna suits them, or offer the "
                "clinic you agreed on before."
            )
        elif event.step == "getHor":
            fresh = new_step or (before is not None and before.slots != event.slots)
            scanned = bool(event.days) and (before is None or before.days != event.days)
            if scanned:
                ask = (
                    "The booking read the next open days and their hours (in the line above). "
                    "Name two or three days with an hour or two each, as words, and ask which "
                    "suits them."
                )
            elif event.slots and fresh:
                ask = (
                    "The booking shows the hours for the selected day. Name two or three of "
                    "them as words, and ask which suits them."
                )
            elif event.no_slots and (before is None or not before.no_slots):
                ask = (
                    "The selected day has no free hours. Say so in a sentence and offer another "
                    "day, or to check the next days (booking_scan)."
                )
            elif new_step and not self._wanted.date:
                ask = "The booking asks for a day. Ask which day suits them, or offer to check the next days (booking_scan)."
        elif event.step == "getDC" and new_step:
            ask = (
                "The booking shows the review. Read back the date, hour and address in one or "
                "two sentences, as words, and say 'Confirmar cita' is theirs to press; never "
                "say it is booked yet."
            )
        if ask is not None:
            self._talk_through(ask)
        return note

    def _take_wanted(self, event: BookingState) -> None:
        """What the visitor chose before the booking got there, sent now that it
        has: the motivo on the motivo step, the clinic (and day, hour) after."""
        w = self._wanted
        if not w.any() or self._busy() is not None:
            return
        pick: BookingPick | None = None
        if event.step == "getMRes" and w.motivo:
            pick = self._pick_action(w.motivo, w.clinic, w.date, w.time)
        elif event.step == "getSuc" and w.clinic is not None:
            pick = self._pick_action(0, w.clinic, w.date, w.time)
        elif event.step == "getHor" and (w.date or w.time):
            pick = self._pick_action(0, None, w.date, w.time)
        if pick is None:
            return
        logger.info(
            "unosalud: the booking reached {}; taking what they chose: {}", event.step, pick
        )
        self._wanted = _Wanted()
        self._booking_asked = True
        self._send(pick)

    def _callback_changed(self, event: CallbackFormState) -> str:
        before = self.callback
        self.callback = event
        self._dictation()
        name = "Te llamamos" if event.form == "te_llamamos" else "urgencias callback"
        note = (
            f"[The {name} form: filled {', '.join(event.filled) or 'nothing'}; still missing "
            f"{', '.join(event.missing) or 'nothing'}; RUT "
            f"{'typed' if event.rut_typed else 'not typed yet (theirs to type)'}."
        )
        if event.result == "success":
            note += f" Sent: {event.message or 'the form says it was received'}."
        elif event.result == "error":
            note += f" The form shows an error: {event.message}."
        note += "]"
        if event.result != "none" and (before is None or before.result != event.result):
            self._talk_through(
                "The callback form was sent. Thank them in one sentence: an executive will call."
                if event.result == "success"
                else "The callback form shows an error. Say what it says, kindly, and offer 600 707 1010."
            )
        elif self._callback_asked and (before is None or before != event):
            self._talk_through(
                "Say in one sentence what is filled and what is left; the RUT they type in the "
                "field you ringed, and ENVIAR is theirs to press."
            )
        return note

    def _company_changed(self, event: CompanyFormState) -> str:
        before = self.company
        self.company = event
        note = (
            f"[The Convenio Empresas form: filled {', '.join(event.filled) or 'nothing'}; still "
            f"missing {', '.join(event.missing) or 'nothing'}."
            + (f" Result: {event.result} {event.message}." if event.result != "none" else "")
            + "]"
        )
        if event.result != "none" and (before is None or before.result != event.result):
            self._talk_through(
                "The company form was sent. Thank them in one sentence: an adviser will contact them."
                if event.result == "success"
                else "The company form shows an error. Say what it says, kindly."
            )
        elif self._company_asked and (before is None or before != event):
            self._talk_through(
                "Say in one sentence what is filled and what is left; ENVIAR is theirs to press."
            )
        return note

    def _dictation(self) -> None:
        """More patience while a form is open for them to dictate into."""
        b = self.booking
        dictating = (b is not None and b.step == "setPAC") or (
            self.callback is not None
            and bool(self._callback_fields)
            and self.callback.result == "none"
            and bool(self.callback.missing)
        )
        want = FORM_PATIENCE if dictating else UNOSALUD_PATIENCE
        if want == self._patience:
            return
        self._patience = want
        logger.info("unosalud: patience -> {}", want)
        configure_soon(self.session, Config(stt=SttConfig(patience=want)))

    def _read_in_screen(self) -> None:
        """The tabs and the page in front, once per change, ahead of what they say."""
        if self._tabs_unseen and len(self.tabs) > 1:
            listed = "; ".join(
                f"{t.tab_id}: {t.title or t.url}"
                + (" (the booking)" if BOOKING_PATH in t.url else "")
                + (" (in front)" if t.tab_id == self._active else "")
                for t in self.tabs
            )
            self._note(f"[The visitor's open Uno Salud tabs — {listed}.]")
        self._tabs_unseen = False
        if not self._page_unseen or self.page is None:
            return
        self._page_unseen = False
        p = self.page
        note = f"[The tab in front shows “{p.title or p.path}” ({p.path}), a {p.kind} page."
        if p.anchors:
            note += f" Its places: {_clip(p.anchors, _HEADINGS_IN_NOTE)}."
        if p.faqs:
            note += f" Its FAQs: {_clip(p.faqs, _HEADINGS_IN_NOTE)}."
        if p.form != "none":
            note += f" It has the {p.form} form."
        if p.clinic is not None:
            c = p.clinic
            note += f" Clinic {c.name}: {c.address}."
            if c.hours:
                note += f" Hours, as its page shows them: {c.hours}."
            if c.references:
                note += f" References: {c.references}."
        elif is_clinic_page(p.path) and (c := self.kb.clinic_by_path(p.path)) is not None:
            note += f" Clinic {c.name}: {c.address}, {c.comuna}."
            if c.hours:
                note += f" Hours: {c.hours}."
        self._note(note + "]")

    def _note(self, text: str) -> None:
        self.append_to_context(types.Content(role="user", parts=[types.Part(text=text)]))

    def _talk_through(self, ask: str) -> None:
        self._talk = ask
        self._shorten_idle()

    def _holding_floor(self) -> bool:
        playing = self._playing > 0 and time.monotonic() - self._played_at < _PLAYOUT_MAX_S
        return self._turns > 0 or playing

    def _shorten_idle(self) -> None:
        if self._holding_floor():
            self._idle_deferred = True
            return
        self._idle_deferred = False
        if not self._idle_short:
            self._idle_short = True
            configure_soon(self.session, Config(idle=IdleConfig(timeout_ms=_TALK_THROUGH_MS)))

    def _floor_free(self) -> None:
        if self._idle_deferred and not self._holding_floor():
            self._shorten_idle()

    def _answered(self, command: str, outcome: str) -> None:
        """The page answered a move he sent: said in the next short quiet spell;
        a move queued behind it goes now, or is dropped and said (as Clini)."""
        if command not in self._sent:
            return
        del self._sent[command]
        if (queued := self._queued) is not None and not self._busy():
            self._queued = None
            name = queued.__voqal_action__
            if outcome.startswith(f"{command} done"):
                logger.info("unosalud: {} answered; sending the {} queued behind it", command, name)
                self._send(queued)
            else:
                outcome += f" (so {name}, asked for while it ran, was not sent)"
        self._outcomes.append(outcome)
        self._shorten_idle()

    def _busy(self) -> str | None:
        now = time.monotonic()
        for command, until in self._sent.items():
            if command in _BOOKING_MOVES and until > now:
                return command
        return None

    def _send(self, action: Action) -> None:
        command = action.__voqal_action__
        if command in _FORM_COMMANDS and command != "open_link":
            self._sent[command] = time.monotonic() + _MOVE_TAKES_S.get(command, _MOVE_TAKES_S[""])
        self.session.dispatch(action)

    def _booking_move(self, action: Action, line: str, said: str | None = None) -> str | None:
        """Send a booking move, or queue it behind the one still under way."""
        if (running := self._busy()) is None:
            self._queued = None
            self._move(action, line, said)
            return None
        self._queued = action
        landed(_LANDED["queued"][self.spoken])
        logger.info("unosalud: {} queued behind {}", action.__voqal_action__, running)
        return (
            f"Queued, not sent yet: the booking is still working on the last step ({running}). "
            "It goes as soon as the page answers that. Say in a few words that you will do it "
            "as soon as the booking is ready; never that it is done, and do not call it again."
        )

    def _take_ask(self) -> str | None:
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
        self._send(action)
        landed(said or _LANDED[line][self.spoken])

    def _meta_turn(self) -> str | None:
        if self._heard and about_the_call(self._heard[-1]):
            return (
                "Not done: they asked about the call itself, not the booking. Answer that "
                "only (set_language for a language), and touch nothing."
            )
        return None

    @staticmethod
    def _sent_note(doing: str) -> str:
        return (
            f"Sent to the page; it has not happened yet. Say only what you are doing "
            f"({doing}), never that it is done; the page's answer will follow."
        )

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        """Read the knowledge, find a clinic; open and drive the booking, fill
        the callback and company forms (never submitting any); open a map; move
        the visitor's tabs; switch language."""
        return [
            self.read_topic,
            self.search_site,
            self.find_clinic,
            self.open_booking,
            self.booking_pick,
            self.booking_scan,
            self.fill_booking_patient,
            self.fill_callback_form,
            self.fill_company_form,
            self.open_link,
            self.switch_tab,
            self.set_language,
        ]

    @needs_result_now
    async def read_topic(self, request: TopicRequest) -> str:
        """Read one of Uno Salud's knowledge topics before answering from it."""
        topic = self.kb.topics.get(request.topic)
        if topic is None:
            return f"No topic '{request.topic}' is written yet: use search_site."
        return topic.text

    @needs_result_now
    async def search_site(self, request: SearchRequest) -> str:
        """Search www.unosalud.cl's pages, FAQs, clinics and promotions. Each
        result names the page path and the place key to show."""
        hits = self.kb.search(request.query, _SEARCH_HITS)
        if not hits:
            return f"Nothing on www.unosalud.cl matches '{request.query}'. Say so plainly."
        out: list[str] = []
        for h in hits:
            where = f" — path {h.path}" if h.path else ""
            key = f", faq key {h.faq}" if h.faq else f", place {h.anchor}" if h.anchor else ""
            out.append(f"[{h.kind}] {h.title}{where}{key}\n  {h.snippet}")
        return "\n".join(out)

    @needs_result_now
    async def find_clinic(self, request: ClinicRequest) -> str:
        """Uno Salud's clinics that match a comuna, city, region, name, street,
        landmark or metro station: address, page and the name the booking uses.
        Call it first, before you answer."""
        found = self.kb.find_clinics(request.query, _CLINIC_HITS)
        if not found:
            return (
                f"No clinic matches '{request.query}'. Say so, and show /clinicas/, where they "
                "can choose their region and comuna."
            )
        lines: list[str] = []
        for c in found:
            line = f"- {c.name} (key {c.key}): {c.address}, {c.comuna}, {c.region}."
            if c.references:
                line += f" Referencias: {c.references}."
            if c.hours:
                line += f" Horario: {c.hours}."
            line += f" Page {c.path}; row on /clinicas/: place clinicas_{c.key}."
            if c.booking_name:
                line += f" In the booking: {c.booking_name}."
            lines.append(line)
        return (
            "\n".join(lines)
            + "\nEach clinic's hours are on its own page: open it to read them. The map is "
            "open_link with the clinic. For the booking, booking_pick with the clinic's key."
        )

    async def switch_tab(self, request: TabRequest) -> str:
        """Bring another of the visitor's Uno Salud tabs to the front."""
        tab = next((t for t in self.tabs if t.tab_id == request.tab_id), None)
        if tab is None:
            listed = ", ".join(f"{t.tab_id} ({t.title})" for t in self.tabs) or "none"
            return f"Not switched: no tab '{request.tab_id}'. Open tabs: {listed}."
        self._move(FocusTab(tab_id=tab.tab_id), "tab")
        return f"Brought '{tab.title or tab.url}' to the front."

    async def set_language(self, request: LanguageRequest) -> str:
        """Conduct the rest of the call in English ('en') or Spanish ('es').
        Call it when they ask for the other language in words that are not
        already it; say one short line in the new language in the same response."""
        self._chosen = True
        configure_soon(self.session, self._speaking(request.language))
        logger.info("unosalud: language -> {} (asked)", request.language)
        return "ok"

    async def open_booking(self, request: OpenBookingRequest) -> str:
        """Open the online booking (/agenda-tu-hora/) in its own tab and ring the
        RUT field for the visitor. With a promotion's key, the booking carries
        its code. It returns at once; what the booking shows comes back after."""
        if (meta := self._meta_turn()) is not None:
            return meta
        code = ""
        note = ""
        if request.promo.strip():
            promo = self.kb.promotion(request.promo)
            if promo is None:
                note = f" No promotion '{request.promo}' is known: the booking opens without one."
            elif (
                promo.valid_until and promo.valid_until < datetime.now(TIMEZONE).date().isoformat()
            ):
                note = f" The promotion {promo.card} ended on {promo.valid_until}: never offer it."
            elif promo.promo:
                code = promo.promo
            else:
                note = (
                    f" {promo.card} is booked from its own page ({promo.landing}); its code was "
                    "not published, so the booking opens without it: say they mention the "
                    "promotion at the clinic, or open its page."
                )
        self._booking_asked = True
        self._opened_booking = True
        self._cue_path = None
        queued = self._booking_move(OpenBooking(promo=code), "booking")
        if queued is not None:
            return queued
        return (
            "Opening the booking in its own tab"
            + (f" with the promotion code {code}" if code else "")
            + ", with the RUT field ringed. "
            + self._sent_note("'Te abro la reserva.'")
            + " Tell them kindly: they type the patient's RUT, tick the terms and 'No soy un "
            "robot', and press Continuar; then you pick the motivo, clinic, day and hour with "
            "them." + note
        )

    def _clinic(self, said: str) -> Clinic | None:
        if not said.strip():
            return None
        if (c := self.kb.clinic(said)) is not None:
            return c
        found = self.kb.find_clinics(said, 2)
        return found[0] if len(found) == 1 else None

    def _pick_action(self, motivo: int, clinic: Clinic | None, day: str, when: str) -> BookingPick:
        return BookingPick(
            motivo=motivo,
            region=clinic.booking_region if clinic else "",
            comuna=(clinic.booking_comuna or clinic.comuna) if clinic else "",
            sucursal=(clinic.booking_id or clinic.booking_name or clinic.name) if clinic else "",
            date=day,
            time=when,
        )

    async def booking_pick(self, request: PickRequest) -> str:
        """On the booking: the motivo, the clinic, the day and the hour they
        chose, in that order, each as its step comes. A choice made before the
        booking reaches its step is kept and taken then. It returns at once."""
        if (meta := self._meta_turn()) is not None:
            return meta
        motivo = request.motivo
        if motivo and self.kb.motivo(motivo) is None:
            listed = "; ".join(f"{m.id} {m.name}" for m in self.kb.motivos)
            return f"Not picked: {motivo} is not a motivo. The motivos: {listed}."
        clinic = self._clinic(request.clinic)
        if request.clinic.strip() and clinic is None:
            found = self.kb.find_clinics(request.clinic, 4)
            names = "; ".join(f"{c.name} (key {c.key})" for c in found) or "none"
            return f"Not picked: which clinic is '{request.clinic}'? Candidates: {names}. Ask them."
        day = iso_day(request.date) or ""
        if request.date and not day:
            return "Not picked: the day must be YYYY-MM-DD."
        when = hhmm(request.time) or ""
        if request.time and not when:
            return "Not picked: the hour must be HH:MM, one the booking listed."
        if not (motivo or clinic or day or when):
            return "Not picked: say which motivo, clinic, day or hour."
        b = self.booking
        if b is not None and b.step == "getHor" and when and b.slots and when not in b.slots:
            return (
                f"Not picked: {when} is not an hour the booking lists for {b.date}. It lists: "
                f"{_clip(b.slots, _TIMES_IN_NOTE)}."
            )
        step = b.step if b is not None else "getPAC"
        if step == "notsetRH":
            return "Not picked: this patient already has an hour booked; offer 600 707 1010."
        if step in ("getDC", "setRH"):
            return "Not picked: the booking is past those steps (the review is on screen)."
        dropped: list[str] = []
        if step in _STEP_ORDER and _STEP_ORDER.index(step) > _STEP_ORDER.index("getMRes"):
            # A choice for a step already behind stays as the booking took it.
            if motivo:
                dropped.append("the motivo")
            motivo = 0
        if step in _STEP_ORDER and _STEP_ORDER.index(step) > _STEP_ORDER.index("getSuc"):
            if clinic is not None:
                dropped.append("the clinic")
            clinic = None
        behind = (
            f" Not sent: {' and '.join(dropped)}, which the booking already has (it shows "
            f"{_STEP_NAMES.get(step, step)}); to change it, they press Volver themselves."
            if dropped
            else ""
        )
        if not (motivo or clinic or day or when):
            return "Not picked:" + behind
        # What the booking cannot take yet waits for its step.
        first = "getMRes" if motivo else "getSuc" if clinic else "getHor"
        if (
            b is None
            or step not in _STEP_ORDER
            or step in ("getPAC", "setPAC", "setEF")
            or _STEP_ORDER.index(first) > _STEP_ORDER.index(step)
        ):
            self._wanted = _Wanted(
                motivo or self._wanted.motivo,
                clinic or self._wanted.clinic,
                day or self._wanted.date,
                when or self._wanted.time,
            )
            landed(_LANDED["kept"][self.spoken])
            if b is None:
                where = "the booking is not open yet (open_booking first)"
            elif step == "getPAC":
                where = (
                    "the booking is still at its first step, which is the visitor's: the RUT, "
                    "the terms and 'No soy un robot', then Continuar"
                )
            else:
                where = f"the booking shows {_STEP_NAMES.get(step, step)}"
            return (
                f"Kept, not sent yet: {where}. It is selected by itself as soon as the booking "
                "reaches that step. Say in a few words that you will select it then." + behind
            )
        self._booking_asked = True
        self._wanted = _Wanted()
        queued = self._booking_move(self._pick_action(motivo, clinic, day, when), "pick")
        named = self.kb.motivo(motivo)
        chosen = [
            x
            for x in (
                named and f"motivo {named.name}",
                clinic and f"clinic {clinic.name}",
                day and _said_day(day),
                when,
            )
            if x
        ]
        return queued or (
            f"Selecting {', '.join(str(c) for c in chosen)} on the booking. "
            + self._sent_note("'Te lo marco.'")
            + (" Choosing the hour takes them to the review." if when else "")
            + behind
        )

    async def booking_scan(self, request: ScanRequest) -> str:
        """On the day-and-hour step: read the hours of the next open days. It
        returns at once; the days come back after."""
        b = self.booking
        if b is None or b.step != "getHor":
            where = _STEP_NAMES.get(b.step, b.step) if b is not None else "no booking open"
            return f"Not scanned: the booking is not on the day-and-hour step ({where})."
        days = max(1, min(10, request.days))
        start = iso_day(request.from_date) or ""
        self._booking_asked = True
        queued = self._booking_move(BookingScan(from_date=start, days=days), "scan")
        return queued or (
            f"Reading the next {days} open days on the booking. "
            + self._sent_note("'Reviso los próximos días.'")
        )

    def _phone(self, said: str, refused: list[str], *, booking: bool) -> str | None:
        """The digits the model passed, if they are the visitor's and fit the
        form; else why not, in ``refused``. Never reshaped."""
        heard = said_digits(self._heard[-1]) if self._heard else ""
        if len(heard) < _SAID_DIGITS_MIN:
            heard = said_digits(" ".join(self._heard[-2:]))
        given = "".join(c for c in said if c.isdigit())
        phone = mobile(said) if booking else nine_digits(said)
        if phone is None:
            from_them = f" (they said {spaced(heard)})" if len(heard) >= _SAID_DIGITS_MIN else ""
            need = "a celular, nine digits starting with 9" if booking else "nine digits"
            refused.append(
                f"phone: {spaced(given) or said!r}{from_them} is not {need} ({len(given)} digits "
                "given). Tell them what the form needs and ask again; never change or invent digits"
            )
            return None
        if len(heard) >= _SAID_DIGITS_MIN and phone not in heard:
            refused.append(
                f"phone: {spaced(phone)} is not what the visitor said ({spaced(heard)}). Never "
                "change their digits"
            )
            return None
        return phone

    def _fill_line(self, took: list[str], turned: list[str], fields: dict[str, str]) -> str:
        lang = self.spoken
        out: list[str] = []
        if took:
            names = _and(lang, [_FIELD_NAMES[lang].get(k, k) for k in took])
            out.append(f"Te anoto {names}." if lang == "es" else f"I'm putting in {names}.")
            if "phone" in took:
                digits = ", ".join(_DIGIT_NAMES[lang][int(d)] for d in fields["phone"])
                out.append(f"Tu número: {digits}." if lang == "es" else f"Your number: {digits}.")
        if turned:
            out.append(_ASK_AGAIN.get(turned[0], _ASK_AGAIN[""])[lang])
        return " ".join(out) or _ASK_AGAIN[""][lang]

    async def fill_booking_patient(self, request: PatientRequest) -> str:
        """Fill the booking's patient details with what the visitor said: name,
        surnames, birth date, email, celular; or, for a known patient, confirm
        with confirm_existing. What is filled stays. Never a RUT; never
        'Registrarse' or 'Confirmar cita'. It returns at once."""
        if (meta := self._meta_turn()) is not None:
            return meta
        b = self.booking
        if b is None:
            return "Not filled: no booking is open. Use open_booking first."
        if b.step not in ("setPAC", "setEF"):
            return (
                "Not filled: the patient details are asked only after the RUT step (the booking "
                f"shows {_STEP_NAMES.get(b.step, b.step)} now)."
            )
        refused: list[str] = []
        took: list[str] = []
        turned: list[str] = []
        for key, value in (
            ("nombre", request.nombre),
            ("paterno", request.paterno),
            ("materno", request.materno),
        ):
            if value.strip():
                self._patient[key] = " ".join(value.split())
                took.append(key)
        if request.birth_date:
            born = iso_day(request.birth_date)
            if born and born < datetime.now(TIMEZONE).date().isoformat():
                self._patient["birth_date"] = born
                took.append("birth_date")
            else:
                refused.append("birth date (as YYYY-MM-DD, in the past)")
                turned.append("birth_date")
        if request.phone:
            if (phone := self._phone(request.phone, refused, booking=True)) is not None:
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
        p = self._patient
        self._booking_asked = True
        line = self._fill_line(took, turned, p) if (took or turned) else None
        queued = self._booking_move(
            FillBookingPatient(
                nombre=p.get("nombre", "") if b.step == "setPAC" else "",
                paterno=p.get("paterno", "") if b.step == "setPAC" else "",
                materno=p.get("materno", "") if b.step == "setPAC" else "",
                birth_date=p.get("birth_date", "") if b.step == "setPAC" else "",
                email=p.get("email", ""),
                phone=p.get("phone", ""),
                confirm_existing=request.confirm_existing and b.step == "setEF",
            ),
            "patient",
            line,
        )
        out = f"For the booking: {', '.join(p) or 'nothing yet'}. " + (
            queued or self._sent_note("'Te lo completo.'")
        )
        if "email" in p:
            out += f" The email sent: {p['email']}."
        if "phone" in p:
            out += f" The celular sent: {spaced(p['phone'])}; read it back digit by digit."
        if refused:
            out += f" Not filled: {'; '.join(refused)}."
        if b.step == "setPAC":
            out += " 'Registrarse' is theirs to press once it is complete."
        return out

    async def fill_callback_form(self, request: CallbackRequest) -> str:
        """Fill the Te llamamos form (or the urgencias one) with what the visitor
        said, going there if needed: name, surnames, email, phone, region,
        comuna. What is filled stays. The RUT and ENVIAR are theirs."""
        if (meta := self._meta_turn()) is not None:
            return meta
        refused: list[str] = []
        took: list[str] = []
        turned: list[str] = []
        f = self._callback_fields
        for key, value in (("nombre", request.nombre), ("apellidos", request.apellidos)):
            if value.strip():
                f[key] = " ".join(value.split())
                took.append(key)
        if request.email:
            if (address := email_address(request.email)) is not None:
                f["email"] = address
                took.append("email")
            else:
                refused.append("email")
                turned.append("email")
        if request.phone:
            if (phone := self._phone(request.phone, refused, booking=False)) is not None:
                f["phone"] = phone
                took.append("phone")
            else:
                turned.append("phone")
        if request.region:
            if (region := region_name(request.region)) is not None:
                f["region"] = region
                took.append("region")
            else:
                refused.append(f"region (one of: {', '.join(REGIONS)})")
                turned.append("region")
        if request.comuna.strip():
            f["comuna"] = " ".join(request.comuna.split())
            took.append("comuna")
        self._callback_asked = True
        self._move(
            FillCallbackForm(
                form=request.form,
                nombre=f.get("nombre", ""),
                apellidos=f.get("apellidos", ""),
                email=f.get("email", ""),
                phone=f.get("phone", ""),
                region=f.get("region", ""),
                comuna=f.get("comuna", ""),
            ),
            "callback",
            self._fill_line(took, turned, f) if (took or turned) else None,
        )
        out = f"Sending to the {request.form} form: {', '.join(f) or 'nothing yet'}. "
        out += self._sent_note("'Te lo completo.'")
        if "phone" in f:
            out += f" The phone sent: {spaced(f['phone'])}; read it back digit by digit."
        if refused:
            out += f" Not filled, ask again: {'; '.join(refused)}."
        return out + " The RUT field is ringed for them to type; ENVIAR is theirs to press."

    async def fill_company_form(self, request: CompanyRequest) -> str:
        """Fill the Convenio Empresas form with what the visitor said, going
        there if needed. ENVIAR is theirs to press."""
        if (meta := self._meta_turn()) is not None:
            return meta
        refused: list[str] = []
        f = self._company_fields
        for key, value in (
            ("nombre", request.nombre),
            ("empresa", request.empresa),
            ("cargo", request.cargo),
            ("comentarios", request.comentarios[:200]),
        ):
            if value.strip():
                f[key] = " ".join(value.split())
        if request.email:
            if (address := email_address(request.email)) is not None:
                f["email"] = address
            else:
                refused.append("email")
        if request.phone and (phone := self._phone(request.phone, refused, booking=False)):
            f["phone"] = phone
        if request.region:
            if (region := region_name(request.region)) is not None:
                f["region"] = region
            else:
                refused.append(f"region (one of: {', '.join(REGIONS)})")
        size_note = ""
        if request.trabajadores and (size := company_size(request.trabajadores)) is not None:
            f["trabajadores"] = size
            if 50 <= request.trabajadores < 200:
                size_note = (
                    " The form has no option between 50 and 200 employees; 'Entre 200 a 500' "
                    "was chosen as the nearest: say so."
                )
        self._company_asked = True
        self._move(
            FillCompanyForm(
                nombre=f.get("nombre", ""),
                phone=f.get("phone", ""),
                email=f.get("email", ""),
                empresa=f.get("empresa", ""),
                region=f.get("region", ""),
                cargo=f.get("cargo", ""),
                trabajadores=f.get("trabajadores", ""),
                comentarios=f.get("comentarios", ""),
            ),
            "company",
        )
        out = f"Sending to the Convenio Empresas form: {', '.join(f) or 'nothing yet'}. "
        out += self._sent_note("'Te lo completo.'") + size_note
        if refused:
            out += f" Not filled, ask again: {'; '.join(refused)}."
        return out + " ENVIAR is theirs to press."

    async def open_link(self, request: LinkRequest) -> str:
        """Open a clinic's map ("¿Cómo llegar?") or a www.unosalud.cl page in a
        new tab. Only when they ask for it, or say yes to your offer."""
        if request.clinic.strip():
            c = self._clinic(request.clinic)
            if c is None:
                return f"Not opened: which clinic is '{request.clinic}'? Use find_clinic."
            if not c.maps_url.startswith("https://www.google.com/maps/"):
                return f"Not opened: no map link is known for {c.name}; open its page instead."
            self._move(OpenLink(url=c.maps_url), "link")
            return f"Opened the map to {c.name} in a new tab."
        if request.path.strip():
            if not self._known_page(request.path):
                return f"Not opened: '{request.path}' is not a known page of the site."
            url = kb.SITE + canonical_path(request.path)
            self._move(OpenLink(url=url), "link")
            return f"Opened {url} in a new tab."
        return "Not opened: say which clinic or page."


__all__ = [
    "BookingPick",
    "BookingScan",
    "Cue",
    "FillBookingPatient",
    "FillCallbackForm",
    "FillCompanyForm",
    "FocusTab",
    "LanguageChanged",
    "Navigate",
    "OpenBooking",
    "OpenFaq",
    "OpenLink",
    "ShowSection",
    "UnoSaludBrain",
]
