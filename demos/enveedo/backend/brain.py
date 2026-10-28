"""EnveedoBrain — Javier, a guide on enveedo.com.

The site is Enveedo's, not ours: a security program management platform from
Miami (Crown Jewel Analysis, risk register, compliance across some forty
frameworks, vendor risk, incident response, a security roadmap; the enterprise
"Security Performance OS"; a partner program for MSPs and MSSPs). A browser
extension injects the widget and a small adapter into it; the adapter turns
each :class:`~voqalize.sdk.Action` below into a move on the tab in front — a
page, a place on it scrolled to and ringed (opening a tab, an accordion or the
Without/With toggle first), the demo scheduler driven, a HubSpot form filled
field by field — and the call itself opens a gated eBook, the blog or the
platform PDF in a new tab. Every tab reports what it shows as a typed event
(:mod:`.app_events`), whoever moved it.

A port of the Colegio Everest guide (``demos/colegioeverest``: the catalogue of
places, the cues, the form fill, the floor held after the nod, talk-throughs
that run with tools off, one page move at a time), with SendPotion's demo
booking (``demos/sendpotion``: the scheduler driven by voice, its late results
spoken in the next quiet spell) and Explora's bilingual site (``demos/explora``:
the site follows the call's language).

**A guide for a security buyer.** Every turn answers what was asked, in words,
shows it, and ends on one specific next step: who they are first (a CISO, an IT
lead, an MSP, a compliance owner), then the part of the site that fits, then
the demo — a free risk assessment with a CISO strategist — booked in the page's
own scheduler.

**Every fact has a source**: L1 (in this prompt), an L2 topic he read, a search
of the site, a tool's result or what the page reported. The site publishes no
pricing, no trial, no customer counts and no funding: L1 lists what it does not
say first, and he says so.

**The visitor presses the button.** He fills the scheduler's details and the
site's forms as they dictate; the visitor ticks consent and presses Submit or
the scheduler's confirm themselves. There is no Action that submits, ticks a
box or touches the reCAPTCHA, and in this preview the scheduler's confirm is
held back by the page.

**English or Spanish.** The call opens in English unless the visitor chose
Spanish or started on a Spanish page; the site follows the call's language
(the brain names English paths, the extension loads the /es/ twins). The voice
is one man, recorded in each.
"""

from __future__ import annotations

import dataclasses
import math
import random
import re
import time
from collections.abc import AsyncGenerator
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
    ENVEEDO_EVENTS,
    CommandDone,
    CommandFailed,
    DemoScheduled,
    DemoState,
    EnveedoEvent,
    FormResult,
    FormState,
    LanguageRequested,
    PageChanged,
    TabInfo,
    TabsChanged,
)
from .cues import CueKind, CueParser, RawCue, words
from .knowledge import (
    FRAMEWORKS,
    TOPIC_IDS,
    Anchor,
    Framework,
    Knowledge,
    Page,
    fold,
    norm,
)

AGENT_NAME = "Javier"

#: GPT-6.1 Terra at low reasoning, for cost: OpenAI caches every prompt over
#: 1,024 tokens, so most of each turn's input is read from the cache.
MODEL = "gpt-6.1-terra"
REASONING = "low"

#: Where "today" is when the page does not say: the site's audience is mostly
#: Latin American, and the scheduler shows times in the visitor's own zone.
DEFAULT_TIMEZONE = "America/Santiago"


def _zone(name: object) -> ZoneInfo:
    """The browser's time zone, as the page reports it, or the default."""
    if isinstance(name, str) and name.strip():
        try:
            return ZoneInfo(name.strip())
        except (ZoneInfoNotFoundError, ValueError):
            logger.info("enveedo: unknown time zone {!r}; using the default", name)
    return ZoneInfo(DEFAULT_TIMEZONE)


# ─── Voice and timing ──────────────────────────────────────────────────────────

#: Javier's voice: the speech tier's male persona recorded once in English and
#: once in Spanish, so a switch keeps the same man.
VOICE = Voice.OMNIVOICE_JAVIER

#: A quiet visitor is someone reading a page; a guide beside them says
#: something after a while, and not twice more.
_IDLE_MS = 20_000
_IDLE_NUDGES = 2
#: The idle window while something is owed — the page's answer to a move, the
#: scheduler's open days, the site's answer to their press: a visitor who
#: reacts speaks first, one who is reading hears it from him.
_TALK_THROUGH_MS = 2_000
#: A little more patience than the demos' default: an email or a phone number
#: is dictated with pauses.
ENVEEDO_PATIENCE = PATIENCE + 2
#: A message this soon after the last one is the rest of the same thought.
_FRAGMENT_S = 4.0

# ─── Language ──────────────────────────────────────────────────────────────────

#: What he answers in, as the tag both legs of the call take.
Lang = Literal["en", "es"]
#: The site's first language: a call opens in it unless the visitor chose
#: Spanish or is reading the Spanish site.
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
    su sus nosotros vale bueno claro dónde donde cuál cual cuándo cuando empresa somos
    seguridad plataforma cumplimiento muéstrame dime explícame quiénes quién trabajo
    """.split()  # noqa: SIM905
)
_ENGLISH_WORDS = frozenset(
    """the is are was what how can could you your i i'm it it's this that these those do
    does show me my we our for with about and of to have has there here please want
    would like tell sure yes okay right of course let's company team security platform
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
#: Names a reply says as the site writes them, in the other language: the
#: site's English product names in a Spanish reply, Latin American laws and
#: Spanish webinars in an English one. They are not a sign of either language.
_NAMES = re.compile(
    r"\b(?:security performance os|crown jewel analysis|risk register|security roadmap|"
    r"book a demo|request executive briefing|schedule a strategic briefing|submit|"
    r"ley marco de ciberseguridad|esquema nacional de seguridad|anexo 28|"
    r"ciberseguridad en acci[oó]n[^.?!]{0,30}|c[oó]mo crear ciber resiliencia|"
    r"enveedopedia|encyclociso|encyloCISO)\b",
    re.IGNORECASE,
)


def language_of(text: str, *, sure: bool = True) -> Lang | None:
    """The language ``text`` is plainly in, or ``None``.

    ``sure`` is for what the visitor said, where one stray word must not move
    the call: Spanish needs two of its words (or its marks and one), English
    three of its own and none of Spanish's. Unsure is for the first words of his
    own reply, which are few: one Spanish word, or two English ones, will do.
    Cues and the site's names are taken out first."""
    text = _NAMES.sub(" ", _CUE_TEXT.sub(" ", text))
    found = set(_LETTERS.findall(text.lower()))
    es = len(found & _SPANISH_WORDS) + (1 if _SPANISH_MARKS.search(text) else 0)
    en = len(found & _ENGLISH_WORDS)
    if es >= (2 if sure else 1) and es > en:
        return "es"
    if en >= (3 if sure else 2) and es == 0:
        return "en"
    return None


# ─── What the voice reads ──────────────────────────────────────────────────────
#
# The site is full of acronyms and standard numbers a voice reads wrong: "SOC
# 2" as "sock" and a pause, "CISO" letter by letter, "ISO 27001" as a phone
# number, "GRC" as one word. The screen keeps the site's spelling; only the
# voice is handed the way a security practitioner says each, in the language
# he speaks, and what comes back as heard is spelled as written again before it
# reaches the model (``from_the_voice``). "SOC" is "sock", "CISO" is "SEE-so"
# ("siso" in Spanish), the ISO standards are said as people in the field say
# them.

#: The ISO standards on the site, said in each language.
_ISO: dict[str, dict[Lang, str]] = {
    "27001": {"en": "twenty-seven oh oh one", "es": "veintisiete mil uno"},
    "27002": {"en": "twenty-seven oh oh two", "es": "veintisiete mil dos"},
    "27017": {"en": "twenty-seven oh one seven", "es": "veintisiete mil diecisiete"},
    "27701": {"en": "twenty-seven seven oh one", "es": "veintisiete mil setecientos uno"},
    "42001": {"en": "forty-two oh oh one", "es": "cuarenta y dos mil uno"},
    "9001": {"en": "nine thousand one", "es": "nueve mil uno"},
    "31000": {"en": "thirty-one thousand", "es": "treinta y un mil"},
    "22301": {"en": "twenty-two three oh one", "es": "veintidós mil trescientos uno"},
}
_ISO_WRITTEN = re.compile(r"\bISO(?:[/ ]IEC)?[ -]?(\d{4,5})(?:[: ]\d{4})?\b", re.IGNORECASE)

#: (as written, the site's spelling, said in English, said in Spanish). Case
#: is ignored on the way in.
_SAID: tuple[tuple[str, str, str, str], ...] = (
    (r"SOC ?(?:2|II)", "SOC 2", "sock two", "sok dos"),
    (r"vCISOs", "vCISOs", "vee see-sos", "ve sisos"),
    (r"vCISO", "vCISO", "vee see-so", "ve siso"),
    (r"CISOs", "CISOs", "see-sos", "sisos"),
    (r"CISO", "CISO", "see-so", "siso"),
    (r"MSSPs", "MSSPs", "M S S Ps", "eme ese ese pes"),
    (r"MSSP", "MSSP", "M S S P", "eme ese ese pe"),
    (r"MSPs", "MSPs", "M S Ps", "eme ese pes"),
    (r"MSP", "MSP", "M S P", "eme ese pe"),
    (r"GRC", "GRC", "G R C", "ge erre ce"),
    (r"CDPO", "CDPO", "C D P O", "ce de pe o"),
    (r"CJA", "CJA", "C J A", "ce jota a"),
    (r"NIS ?2", "NIS2", "NIS two", "NIS dos"),
    (
        r"\$ ?2[,.]500(?: USD)?|2[,.]500 (?:USD|dollars|dólares)",
        "$2,500",
        "two thousand five hundred dollars",
        "dos mil quinientos dólares",
    ),
    (r"45\+", "45+", "more than forty-five", "más de cuarenta y cinco"),
    (r"170\+", "170+", "more than a hundred and seventy", "más de ciento setenta"),
)
_SAID_RX = tuple(
    (re.compile(rf"(?<![\w/]){w}(?![\w])", re.IGNORECASE), en, es) for w, _, en, es in _SAID
)
#: Latin America says "vi-DE-o": the Spanish voice is handed "bidéo" (Spanish b
#: and v are one sound), as on the other Javier guides.
_VIDEO_TO_VOICE = re.compile(r"\b([Vv])[ií]deo(s?)\b")
_VIDEO_FROM_VOICE = re.compile(r"\b([Bb])idéo(s?)\b")
_VIDEO_AS_WORDS = re.compile(r"\bv deo(s?)\b")


def for_the_voice(text: str, lang: Lang) -> str:
    """``text`` as the voice must read it in ``lang``."""

    def iso(m: re.Match[str]) -> str:
        said = _ISO.get(m.group(1))
        return f"ISO {said[lang]}" if said else m.group(0)

    text = _ISO_WRITTEN.sub(iso, text)
    for rx, en, es in _SAID_RX:
        text = rx.sub(en if lang == "en" else es, text)
    if lang == "es":
        text = _VIDEO_TO_VOICE.sub(
            lambda m: ("B" if m.group(1) == "V" else "b") + "idéo" + m.group(2), text
        )
    return text


#: Each respelling, back to how the site writes it.
_FROM_VOICE: tuple[tuple[re.Pattern[str], str], ...] = (
    *(
        (re.compile(rf"\bISO {re.escape(said[lang])}\b", re.IGNORECASE), f"ISO {number}")
        for number, said in _ISO.items()
        for lang in ("en", "es")
    ),
    *(
        (re.compile(rf"(?<![\w-]){re.escape(said)}(?![\w-])", re.IGNORECASE), written)
        for _, written, en, es in _SAID
        for said in (en, es)
    ),
)


def from_the_voice(text: str) -> str:
    """What the voice said, spelled as the site writes it."""
    for rx, written in _FROM_VOICE:
        text = rx.sub(lambda _m, w=written: w, text)
    return _VIDEO_FROM_VOICE.sub(
        lambda m: ("V" if m.group(1) == "B" else "v") + "ideo" + m.group(2), text
    )


#: A word the voice says otherwise, alone at the end of a cue's anchor (the
#: anchor is the sentence's first words, so "SOC 2" may be cut to "soc").
_WORD_SAID: dict[Lang, dict[str, str]] = {
    "en": {"soc": "sock", "ciso": "see so", "cisos": "see sos", "vciso": "vee see so"},
    "es": {"soc": "sok", "ciso": "siso", "cisos": "sisos", "vciso": "ve siso"},
}


def _anchor_for_voice(at: str, lang: Lang) -> str:
    """A cue's anchor, in the page's words, for speech spelled
    :func:`for_the_voice`: as many of its words as the voice says first."""
    at = _VIDEO_AS_WORDS.sub(r"video\1", at)
    said: list[str] = []
    for w in words(for_the_voice(at, lang)):
        if w == "iec" and said[-1:] == ["iso"]:
            continue  # "ISO/IEC 27001" is said "ISO twenty-seven…"
        said += _WORD_SAID[lang].get(w, w).split()
    n = len(at.split())
    return " ".join(said[: max(n, 1)])


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
    catalogue) or ``text``, scroll to that place and ring it. ``path`` is the
    English site's path; while the call is in Spanish the extension loads its
    /es/ twin. The page loads in full and reports ``page_changed``."""

    path: str
    anchor: str | None = None
    text: str | None = None


class Cue(Action):
    """A move for the page to make when the voice reaches ``at`` — the first
    words of the sentence it belongs to (see :mod:`.cues`); empty ``at`` is
    when the voice stops. With ``path``, it is a :class:`Navigate`; else a
    place or words on the tab in front. A place the catalogue marks
    ``reveal`` (a tab, an accordion, the Without/With toggle) is opened by
    its own control first, then ringed."""

    at: str
    word: int = 0
    """Words of the unit before it, for a page that times cues by the clock."""
    path: str | None = None
    anchor: str | None = None
    text: str | None = None


class ShowSection(Action):
    """On the tab in front, scroll to the catalogue's place ``anchor`` (opening
    it first when the catalogue marks it ``reveal``) and ring it; with
    ``text``, ring the smallest element containing that text."""

    anchor: str | None = None
    text: str | None = None


class OpenLink(Action):
    """Open a link the site gives in a new tab: a gated eBook or webinar on
    info.enveedo.com, a YouTube webinar, a blog post, the platform PDF, the
    customers' sign-in. The visitor goes on there; the extension does nothing
    on that tab."""

    url: str
    label: str = ""


class BookDemo(Action):
    """Open /book-a-demo (its /es/ twin in a Spanish call) and, in its HubSpot
    Meetings scheduler (a meetings.hubspot.com frame), choose ``duration``,
    ``day`` and ``time`` and fill in the details given, as far as they go. A
    field left ``None`` is not touched. The frame reports ``demo_state``; it
    never presses the scheduler's final confirm button."""

    duration: str | None = None
    """"15 mins", "30 mins" or "1 hour", as the scheduler labels them."""
    day: str | None = None
    """An open day as ``demo_state.days`` lists it, ISO "2026-11-04"."""
    time: str | None = None
    """A time as ``demo_state.times`` lists it, e.g. "10:30am"."""
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None


FormName = Literal["contact", "soc2"]


class FillForm(Action):
    """Type what the visitor dictated into one of the site's HubSpot forms,
    field by field (the native value setter, then ``input``, ``change`` and
    ``blur``), and scroll it into view: ``contact`` on /contact (also at the
    foot of /frameworks), ``soc2`` (the SOC 2 report request) on
    /trust-center. On another page the form's page opens first (its /es/ twin
    in a Spanish call) and the fill is made there. A field left ``None`` is
    not touched; a field the form does not have is ignored. It never ticks the
    consent box, never presses Submit and never touches the reCAPTCHA: once
    every field is in, the consent box and Submit are rung for the visitor.
    Answers ``form_state`` and ``command_done`` / ``command_failed``."""

    form: FormName
    firstname: str | None = None
    lastname: str | None = None
    email: str | None = None
    phone: str | None = None
    country: str | None = None
    """Exactly one of the contact form's country options ("Chile", "United
    States", "Others")."""
    company: str | None = None
    job_title: str | None = None
    message: str | None = None
    """``message`` on the contact form, ``notes`` (Description) on soc2."""


class FocusTab(Action):
    """Bring one of the visitor's Enveedo tabs to the front."""

    tab_id: str


class LanguageChanged(Action):
    """The call's language moved, by the toggle, by voice or by
    ``set_language``: the widget's toggle follows at once, and the tab keeps
    it for the rest of the call, on every page."""

    language: Literal["en", "es"]
    site: Literal["follow", "twin", "stay"] = "follow"
    """What the page in front does: ``follow`` loads it in that language (its
    twin, else that language's home page); ``twin`` loads its own twin only,
    and reports it when it has none; ``stay`` leaves it as it is (the call's
    start, on the page the visitor opened it on)."""


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
        description="A few words to look for on the site, in English or Spanish, e.g. "
        "'vendor risk', 'penetration test', 'multitenancy', 'heatmap', 'glossary vCISO'."
    )


class FrameworkRequest(BaseModel):
    query: str = Field(
        description="The framework, standard or law as the visitor named it, e.g. 'NIS 2', "
        "'ISO 42001', 'Chile's new data law', 'Ley Marco de Ciberseguridad', 'HIPAA', "
        "'GDPR', 'Mexico privacy law'."
    )


class DemoRequest(BaseModel):
    """Only what the visitor said: leave out anything they did not."""

    duration: Literal["15 mins", "30 mins", "1 hour"] | None = Field(
        default=None, description="The meeting length they chose, only if they said."
    )
    day: str | None = Field(
        default=None,
        description="An open day as the scheduler lists it, ISO 'YYYY-MM-DD', resolved from "
        "what they said ('next Tuesday') against today's date.",
    )
    time: str | None = Field(
        default=None, description="A time exactly as the scheduler lists it, e.g. '10:30am'."
    )
    first_name: str | None = Field(default=None, description="Only if the visitor said it.")
    last_name: str | None = Field(default=None, description="Only if the visitor said it.")
    email: str | None = Field(
        default=None,
        description="Their email exactly as they spelled it, never changed or completed.",
    )


class FormRequest(BaseModel):
    """Only the fields the visitor gave since the last fill."""

    form: FormName = Field(
        description="contact: the contact form (/contact, also at the foot of /frameworks); "
        "soc2: the SOC 2 Type II report request on /trust-center."
    )
    firstname: str | None = Field(default=None, description="First name, exactly as said.")
    lastname: str | None = Field(default=None, description="Last name, exactly as said.")
    email: str | None = Field(
        default=None,
        description="Their business or corporate email, exactly as they spelled it.",
    )
    phone: str | None = Field(
        default=None,
        description="contact only: their phone exactly as said, with its country code if given.",
    )
    country: str | None = Field(
        default=None,
        description="contact only: exactly one of the form's countries, in English as the form "
        "writes it ('Chile', 'Mexico', 'United States', 'Colombia', 'Peru', 'Argentina', "
        "'Brazil', 'Canada', …); 'Others' for a country not on it (Spain, the United Kingdom).",
    )
    company: str | None = Field(default=None, description="Their company or organization.")
    job_title: str | None = Field(default=None, description="soc2 only: their job title.")
    message: str | None = Field(
        default=None,
        description="A short message you write from the conversation, in the visitor's "
        "language, two or three sentences: who they are (role, company, size or industry if "
        "said), what they need (the framework, the pain, the partner program), and what they "
        "want from Enveedo (a call, information). On soc2 it goes in Description.",
    )


LinkKind = Literal["library", "blog", "pdf", "sign_in", "scheduler"]


class LinkRequest(BaseModel):
    kind: LinkKind = Field(
        description="library: a gated eBook or webinar (name it); blog: the Cyber Pulse blog; "
        "pdf: the platform overview PDF; sign_in: the customers' sign-in (only when asked); "
        "scheduler: the demo scheduler's own page, as a fallback when the page's one fails."
    )
    name: str = Field(
        default="",
        description="For library, a few words of its title: 'Hail & Cotton', 'beyond GRC', "
        "'scaling vCISO', 'gold standard', 'diario de un CISO'.",
    )


class TabRequest(BaseModel):
    tab_id: str = Field(description="The tab_id from the open tabs list.")


class LanguageRequest(BaseModel):
    language: Lang = Field(description="'en' for English, 'es' for Spanish.")


# ─── Places ────────────────────────────────────────────────────────────────────

HOME = "/"
PLATFORM_PATH = "/enveedo_platform"
SPOS_PATH = "/security-performance-os"
FRAMEWORKS_PATH = "/frameworks"
PARTNERS_PATH = "/partners"
DEMO_PATH = "/book-a-demo"
CONTACT_PATH = "/contact"
ABOUT_PATH = "/about-us"
RESOURCES_PATH = "/resources"
INSURANCE_PATH = "/cyber-insurance"
FAQ_PATH = "/faq"
TRUST_PATH = "/trust-center"
LIBRARY_PATH = "/webinars-and-ebooks"

#: The pages every move here leans on, as the site serves them (checked
#: 2026-10-28): a cue to one of them is good even before a crawl is loaded.
CORE_PAGES: dict[str, str] = {
    HOME: "Home",
    PLATFORM_PATH: "Platform",
    SPOS_PATH: "Security Performance OS",
    FRAMEWORKS_PATH: "Frameworks",
    PARTNERS_PATH: "Partners",
    DEMO_PATH: "Book a Demo",
    CONTACT_PATH: "Contact",
    ABOUT_PATH: "About Us",
    RESOURCES_PATH: "Resources",
    INSURANCE_PATH: "Cyber Insurance",
    FAQ_PATH: "FAQ",
    TRUST_PATH: "Trust Center",
    LIBRARY_PATH: "Webinars and eBooks",
}
#: Where each form lives, and the page that holds it first.
FORM_PAGES: dict[FormName, str] = {"contact": CONTACT_PATH, "soc2": TRUST_PATH}
FORM_NAMES: dict[FormName, str] = {"contact": "contact form", "soc2": "SOC 2 report request"}
#: The pages whose places are listed in full in the prompt; every other page
#: lists its keys only.
_LISTED_IN_FULL = (
    HOME,
    PLATFORM_PATH,
    SPOS_PATH,
    FRAMEWORKS_PATH,
    PARTNERS_PATH,
    DEMO_PATH,
    CONTACT_PATH,
    TRUST_PATH,
    FAQ_PATH,
    INSURANCE_PATH,
    ABOUT_PATH,
)
#: The header's and footer's places, on every page: listed once, not per page.
_CHROME = ("menu", "language_switcher", "footer")

# ─── The prompt ────────────────────────────────────────────────────────────────


def _own_anchors(k: Knowledge, path: str) -> list[Anchor]:
    """The places of ``path`` itself: not hidden, not the header's or footer's."""
    return [a for a in k.anchors_on(path) if not a.hidden and a.key not in _CHROME]


def _places(k: Knowledge) -> str:
    """Every English page with the places a cue can show there, by key."""
    lines: list[str] = []
    english = [p for p in k.anchors if not p.startswith("/es/")]
    for path in dict.fromkeys([*_LISTED_IN_FULL, *english]):
        page = k.page(path)
        if page is None and path not in CORE_PAGES:
            continue
        title = CORE_PAGES.get(path) or (page.title if page else path)
        own = _own_anchors(k, path)
        if path == FRAMEWORKS_PATH:
            cards = [a for a in own if a.key.startswith("fw_")]
            own = [a for a in own if not a.key.startswith("fw_")]
            lines.append(f"- {path} — {title}")
            lines += [f"  - {a.key}: {a.label}" for a in own]
            if cards:
                lines.append(
                    f"  - and one card per framework ({len(cards)}: fw_iso_27001, fw_soc2, fw_nis2, "
                    "fw_chile_21719, …): find_framework gives the key."
                )
        elif path in _LISTED_IN_FULL:
            lines.append(f"- {path} — {title}")
            lines += [
                f"  - {a.key}: {a.label}" + (" (opens it first)" if a.reveal else "") for a in own
            ]
        else:
            keys = ", ".join(a.key for a in own)
            lines.append(f"- {path} — {title}" + (f" (places: {keys})" if keys else ""))
    if not lines:
        return "\n".join(f"- {path} — {title}" for path, title in CORE_PAGES.items())
    lines.append(
        "- Every page has menu (the top menu), language_switcher (the site's English/Español "
        "switcher) and footer."
    )
    return "\n".join(lines)


def _topics(k: Knowledge) -> str:
    return "\n".join(f"- {t.id}: {t.title}" for t in k.topics.values()) or "(none loaded)"


def _library(k: Knowledge) -> str:
    return "\n".join(f"- {x.label}" for x in k.library) or "- (none loaded)"


def _prompt(k: Knowledge) -> str:
    return f"""You are {AGENT_NAME}, the guide on Enveedo's website, enveedo.com. Enveedo is a security program management platform: it turns fragmented security tools into one program that reduces risk, streamlines compliance and proves security value to the business. A visitor — most often a security or IT leader, a compliance owner, or a managed security provider — is browsing the site and has called you from the corner of the page. You can see and move their screen: you open pages, scroll to the exact place that answers them and ring it, open tabs, FAQ answers and the Without/With toggle, drive the demo scheduler, open eBooks and the blog in a new tab, and fill in the site's forms as they tell you their details. You are calm, sharp and useful: a B2B guide who knows security programs, never a pushy salesperson. Their time is valuable.

# You narrate, and the screen follows your words
You are giving a guided walkthrough, like someone sitting beside the visitor with their screen in front of you both. As you talk about something, it is on their screen, ringed, at that moment.
- Put a screen cue in your reply at the start of the sentence it belongs to. The page moves when your voice reaches that sentence. The visitor never hears a cue.
  - {{page: /path}} opens a page of the site, at its top. Always the English path from the places list: in a Spanish call the Spanish version opens by itself.
  - {{show: key}} scrolls to a place and rings it: a key from the places list below, on the page they are on or one a page cue opens. With other words on the page instead of a key, it rings those words. A place marked "opens it first" (a tab, an FAQ answer, the Without/With toggle) is opened, then ringed.
- Use only keys from the places list, a search result or find_framework. A show cue for a place on one other page only takes them to that page: on the home page, "{{show: faq_start}}" opens the FAQ at that answer.
- Never make up a key. One cue per sentence at most, and only where the screen should change. A cue goes before the sentence, never inside it.
- When they ask where something is ("show me", "muéstrame", "where is"), your reply starts with the cue for exactly that thing.
- EVERY ANSWER ABOUT ENVEEDO STARTS WITH A CUE. Whatever you talk about is somewhere on the site, so show it as you begin.
- Every page of this site loads in full, which takes a few seconds. Never wait for a page and never stop talking because one is loading; keep explaining, and the screen catches up.
- Example, for "how does it work?": "{{page: /}}{{show: how_it_works}} It starts from your business. {{show: how_business_first}} First it finds your crown jewels, the functions that matter most. {{show: how_integration}} Then it connects the tools you already have. {{show: how_reporting}} And it reports to the board in business terms. Would you like to see the six modules?"

# Who you are talking to
Ask early, lightly, one question at a time, and use the answers: their role, their company (size, industry), their country, and the framework or pain that brought them. Never ask twice for what they said. Then route them:
- An enterprise CISO or security leader: the Security Performance OS page ({{page: {SPOS_PATH}}}): control, risk and audit performance, the multi-workspace console for subsidiaries, AI risk suggestions. Then an executive briefing: the demo.
- A mid-market IT or security lead: the home page's story — the Without/With toggle, the Impact Timeline, How Enveedo Works — then the platform's six modules ({{page: {PLATFORM_PATH}}}{{show: modules}}).
- An MSP, MSSP or vCISO provider: the partners page ({{page: {PARTNERS_PATH}}}): why partner, multitenancy and the marketplace, then Become a Partner, which is the contact form with a partner message.
- Someone driven by a framework or a law: find_framework, show its card on the frameworks page, say what the card says, then the demo.
- Someone under cyber-insurance pressure: the cyber insurance page ({{page: {INSURANCE_PATH}}}).
- Questions about Enveedo's own security: the trust center ({{page: {TRUST_PATH}}}{{show: soc2}}), and the SOC 2 report request form there.

# A good turn moves them forward
1. Answer what they asked, first, in plain words, and show it as you say it.
2. Tie it to them in a sentence when you know something about them: their role, their framework, their pain.
3. End by offering one next step: a short, specific yes-or-no offer, so they only have to say "yes". "Shall I show you how it maps one control to several frameworks?" "Want me to book you a demo?" Never "anything else?".
- The calls to action, offered where the story reaches them, never pushed, never in every turn: the demo, a free risk assessment with a CISO strategist (book_demo, the main one); a message through the contact form (fill_form contact), for someone with a question the site does not answer or who wants to be contacted; the SOC 2 report (fill_form soc2), for someone checking Enveedo's own security; Become a Partner, for an MSP.

# How you sound
You are heard, not read.
- A turn is three to five short sentences. A walkthrough of a page can run to seven, one place per sentence, each with its cue.
- Every sentence under fifteen words. Plain words. One idea per sentence. One number per sentence.
- THE FIRST SENTENCE IS A FEW WORDS. The visitor hears nothing until your first sentence has been voiced, so open every reply with a sentence of two to six words that ends in a full stop, with the answer in it. A cue may come before it.
- Before most replies the visitor has already heard a short acknowledgement of mine — "Happy to help.", "Let me see.", or in Spanish "Claro.", "A ver." — so never open with one: your first word is the answer. No "great question", no repeating their question back.
- Spoken words only, apart from cues: no lists, no markdown, no symbols, never an exclamation mark. Write numbers and dates as spoken words: "five times faster", "the fourth of November", "two thousand five hundred dollars".
- Product names stay as the site writes them, in both languages: Crown Jewel Analysis, Risk Register, Security Performance OS, CISO Concierge, Enveedopedia, EncyloCISO, vCISO, GRC, CDPO. Write acronyms and standards short, as the site does: SOC 2, ISO 27001 (never "ISO/IEC 27001:2022"), NIS2, CISO, MSSP. The voice is taught to say them.
- Lines in square brackets come from their screen, not the visitor. Never read them out; use them.
- Always answer. One question at a time, and only one per reply.

# English or Spanish
You speak English and Spanish as a native of Latin America. The call starts in English unless the visitor chose Spanish or is on the Spanish site.
- Answer in the language the visitor speaks to you. If they speak Spanish, answer in Spanish from that reply on; if they go back to English, so do you.
- Except when they chose a language: a line in square brackets says so. Then answer in that language whatever they speak, until they ask to switch.
- When they ask for the other language in words that are not already it ("¿Puedes hablar en español?", "Can we speak English?"), answer in that language and call set_language in the same response. A visitor already speaking Spanish to you has been switched: do not call it for them.
- One language per reply: in a Spanish reply every sentence is Spanish, and masculine forms of yourself ("encantado de ayudarte").
- Your Spanish is neutral Latin American Spanish, understood from Mexico to Chile, professional and warm, never the Spanish of Spain.
  - Address one visitor as "tú", never "usted", unless they speak to you as usted: then you may too. Several people are "ustedes", never "vosotros", and never its verb forms ("queréis", "tenéis", "podéis") or "os".
  - Latin American words: "computadora", never "ordenador"; "celular", never "móvil"; "mostrar" ("te muestro"), not "enseñar"; "completar", not "rellenar"; "¿Qué día te queda bien?", not "te viene bien"; "disculpa", not "perdona"; "está bien" or "perfecto", never "vale"; "agendar" a demo.
  - For something just done, use the simple past: "Abrí la página", "Anoté tu correo", not "He abierto".
  - Write "video", never "vídeo".
- The site follows the call's language: in a Spanish call it shows Enveedo's Spanish pages (their paths start with /es/), with the same place keys. If a screen line shows an English page in a Spanish call, it is loading in Spanish or has no Spanish version (the webinars page has none, and the blog opens in its own tab): never say you changed it.
- When they say the page is in the wrong language, or ask to see it in Spanish or English, it reloads in the call's language by itself: say so in a few words and nothing more until the screen lines show it.
- The site's forms, buttons and cookie banner stay in English on the Spanish pages. In a Spanish call, say the field you are filling in Spanish ("tu nombre", "el país") and translate a button's English words when you point at it ("Submit, que es enviar").

# Every response starts with words
Write your answer, with its cues, first; any tool call comes at the end of the same response. What a page move returns reaches you only later.
- The exception is a read: read_topic, search_site and find_framework come straight back to you within this same turn, but each one makes the visitor wait. Answer from what you know below whenever it covers the question. Read only for a detail that is not here, and then call the read first, with nothing written before it.
- Never promise more to come ("let me check", "one moment", "un momento"): nothing comes after it.

# What that sounds like
Visitor: "We're a bank in Chile. Do you cover the new data protection law?"
You: (call find_framework first, then) "{{page: {FRAMEWORKS_PATH}}}{{show: fw_chile_21719}} Yes, it's on the list. Chile's new law, twenty-one seven nineteen, is one of the frameworks you can assess. It covers consent and data subject rights. Would you like to see how one control maps to several frameworks?"
Visitor: "How much does it cost?"
You: "Pricing isn't published. The site doesn't list plans or prices. The team sets that in a short call, together with a free risk assessment. Shall I book it for you?"
Visitor: "Sí, agendemos."
You: "Perfecto. Te abro la agenda de demos de Elis Martinez." then book_demo.

# What you know
- Every fact comes from the knowledge below, a topic you read, a search result, a tool's result, or what the screen reported. Never from memory. The knowledge opens with what the site does NOT say: when they ask one of those things (pricing, a trial, customer numbers, funding), say plainly the site does not publish it, and offer the demo or the contact form.
- Never invent a customer, a number, an integration, a certification or a framework. Testimonials are anonymous: never name them. "More than forty-five frameworks" is the home page's claim; the frameworks page lists thirty-nine.
- Topics you can read with read_topic, when the knowledge below does not cover a question:
{_topics(k)}
- search_site finds a page or place by its words. Its results name the page and the place's key, which you can then cue.
- find_framework finds a framework, standard or law among the thirty-nine cards, by any name the visitor uses. It returns the card's key and what the card says. When it finds none, say it is not among the listed frameworks, and that the team can say in the demo whether it is supported. Never say it is supported.

# Booking a demo
The main call to action: a demo, which is a free risk assessment with a CISO strategist, in the HubSpot scheduler on {DEMO_PATH}, on Elis Martinez's calendar (co-founder and Chief Revenue Officer). It is a Microsoft Teams meeting of fifteen minutes, thirty minutes or one hour. Times show in the visitor's own time zone.
- Offer it where the story reaches it: after they have seen what fits them, when they ask about pricing, a trial, a specific integration or framework the site does not settle, or ask to talk to someone. Not in the first turns.
- When they want one, book_demo with whatever they have already said. It opens {DEMO_PATH} and its scheduler itself, which takes several seconds: write no page cue for it, and in that reply say only that you are opening it, and name no day.
- The scheduler's open days come back to you in a line in square brackets. Only then say two or three of them, and ask which day and length suit them. Until that line lists the days, never name a day, never say a day is open or full, and never say the calendar is empty: "today" and "tomorrow" too. If the line says it is still loading, it is.
- When they name a day, book_demo with it (and the length if they said) before you say anything about that day's times. The times for that day come back to you after, and you read two or three of them then. Never a time the scheduler has not listed. Then book_demo again with their time.
- Once the time is chosen, ask for their first name, last name and work email, one at a time. Fill each in with book_demo as soon as they say it, then spell the email back letter by letter: "I've put j, a, n, e, at acme dot com. Is that right?" What is filled stays; you only add.
- Never say the scheduler is open, or that a day, a time or a detail is selected or filled, until a line in square brackets says so. When one says it did not happen, it did not: say so, and offer the scheduler's own page in a new tab (open_link scheduler).
- The final confirm button is theirs to press, always. When the details are in, tell them what is left and that they press confirm themselves. Never say it is booked until the page tells you. In this preview the page holds the booking back: when a line says so, say plainly that in this preview the booking is not sent to Enveedo.

# The site's forms
Two forms you fill as they dictate: the contact form (fill_form contact: first name, last name, phone, country, business email, organization, message) and the SOC 2 report request (fill_form soc2: first name, last name, company, job title, a description, corporate email). The page with the form opens if it is not in front.
- Gather by voice, one question at a time, using what they already told you, never asking twice.
- Fill each detail with fill_form as soon as they say it, only the new fields each time.
- EVERY FORM TURN SPEAKS FIRST. Say back what you noted in a few words, ask the one next thing, and put the fill_form call at the end of that same reply.
- Read the email back letter by letter and ask if it is right; a phone number digit by digit. Write them exactly as said, never changed or completed.
- The country is one of the form's options, in English: say it back in the visitor's language. A country not on the list (Spain, the United Kingdom) is "Others": say so.
- Write the message yourself, in the visitor's language, from the conversation: who they are, what they need, what they want from Enveedo. A partner's message says they want to join the partner program. Read it back in a sentence and fill it in.
- When everything is in, the page tells you. Then say it is ready: they tick the consent box and press Submit themselves. YOU NEVER TICK THE BOX OR PRESS SUBMIT, and never say it was sent until a bracketed line says the site confirmed it.
- If the site refuses something, a bracketed line says what: help them fix it.
- Never type a password, a card number, or anything into the cookie banner, the newsletter box or the sign-in. Never accept or decline the cookie banner: that is theirs.

# Links that open in a new tab
open_link, only when they ask or say yes to your offer; say you opened it in a new tab.
- The gated eBooks and webinars (they register there themselves):
{_library(k)}
- The Cyber Pulse blog (blog), the platform overview PDF (pdf), the scheduler's own page (scheduler).
- The sign-in (sign_in) is for existing customers: only when they ask for it. There is no trial or self-serve signup.
- Never send anyone to the footer's social icons: they are placeholders.

# Tabs
- The visitor may have several Enveedo tabs open. Lines in brackets tell you which tabs are open and which is in front. Your moves happen on the tab in front.
- "Go back to the other tab" is switch_tab with that tab's id.

# Enveedo
{k.l1}

# Places on the site, by page, with the keys a cue takes
{_places(k)}
"""


# ─── Greeting ──────────────────────────────────────────────────────────────────

_INTRO: dict[Lang, str] = {
    "en": f"Hi, I'm {AGENT_NAME}, your guide to Enveedo.",
    "es": f"Hola, soy {AGENT_NAME}, tu guía de Enveedo.",
}
_GREETING: dict[Lang, str] = {
    "en": "I can show you how it runs a security program, or take you straight to what you need. "
    "What's your role?",
    "es": "Te muestro cómo gestiona un programa de seguridad, o te llevo directo a lo que "
    "necesitas. ¿Cuál es tu rol?",
}
#: The opener's second sentence for the page the call starts on, by its
#: English path; anything else gets the plain greeting.
_OPENERS: dict[str, dict[Lang, str]] = {
    PLATFORM_PATH: {
        "en": "This is the platform's six modules. Shall I walk you through them?",
        "es": "Aquí están los seis módulos de la plataforma. ¿Te los muestro?",
    },
    SPOS_PATH: {
        "en": "This is Enveedo for larger security programs. Are you running one across several units?",
        "es": "Esta es la propuesta para programas de seguridad grandes. ¿Lo manejas en varias unidades?",
    },
    FRAMEWORKS_PATH: {
        "en": "I can find any framework on this list for you. Which one matters to you?",
        "es": "Te encuentro cualquier marco de esta lista. ¿Cuál te importa?",
    },
    PARTNERS_PATH: {
        "en": "This is the partner program for MSPs and MSSPs. Do you deliver security services?",
        "es": "Este es el programa de partners para MSP y MSSP. ¿Ofreces servicios de seguridad?",
    },
    DEMO_PATH: {
        "en": "I can book your demo with you right here. Shall we pick a day?",
        "es": "Te ayudo a agendar tu demo aquí mismo. ¿Elegimos un día?",
    },
    "/book-a-demo-grl": {
        "en": "I can book you a demo, or help with this eBook. Which would you like?",
        "es": "Te ayudo a agendar una demo, o con este eBook. ¿Qué prefieres?",
    },
    CONTACT_PATH: {
        "en": "I can help you write to the team. What would you like to ask?",
        "es": "Te ayudo a escribirle al equipo. ¿Qué te gustaría preguntar?",
    },
    TRUST_PATH: {
        "en": "This is how Enveedo secures its own platform. Would you like the SOC 2 report?",
        "es": "Así protege Enveedo su propia plataforma. ¿Quieres pedir el informe SOC 2?",
    },
    INSURANCE_PATH: {
        "en": "This is how Enveedo helps with cyber insurance. Are you renewing a policy?",
        "es": "Así ayuda Enveedo con el seguro cibernético. ¿Estás renovando una póliza?",
    },
    FAQ_PATH: {
        "en": "I can open any of these answers for you. What would you like to know?",
        "es": "Te abro cualquiera de estas respuestas. ¿Qué te gustaría saber?",
    },
    ABOUT_PATH: {
        "en": "I can tell you about the team behind Enveedo. What's your role?",
        "es": "Te cuento del equipo detrás de Enveedo. ¿Cuál es tu rol?",
    },
}


def greeting(path: str | None, lang: Lang = OPENING, k: Knowledge | None = None) -> str:
    """The written opener, in ``lang``, tailored to the page the call starts on."""
    k = k if k is not None else kb.KNOWLEDGE
    here = k.english_path(path or "/")
    line = _OPENERS.get(here, _GREETING)[lang]
    return f"{_INTRO[lang]} {line}"


# ─── Written lines for moves ───────────────────────────────────────────────────

#: His line for a silent turn, by what moved: "shown" for anything else.
_LANDED: dict[str, dict[Lang, str]] = {
    "shown": {"en": "Here it is.", "es": "Aquí lo tienes."},
    "link": {
        "en": "I've opened it in a new tab.",
        "es": "Te lo abrí en una pestaña nueva.",
    },
    "demo": {
        "en": "I'm opening the demo scheduler.",
        "es": "Te abro la agenda de demos.",
    },
    "demo_filled": {
        "en": "I'm putting that in the scheduler.",
        "es": "Lo voy poniendo en la agenda.",
    },
    "form": {
        "en": "I'm putting it in the form.",
        "es": "Lo voy anotando en el formulario.",
    },
    "to_form": {
        "en": "I'm taking you to the form.",
        "es": "Te llevo al formulario.",
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
ACK_HOLD_AFTER_S = 5.75
#: With no nod, the dead air a turn may leave before his first line.
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
#: A visitor's ordinary words about Enveedo, so the reading trusts them.
_ACK_WORDS = Vocabulary(
    common=frozenset(
        # A word list reads as words, so it stays a split string.
        """enveedo security seguridad platform plataforma risk riesgo riesgos compliance
        cumplimiento framework frameworks marco marcos iso soc nist gdpr nis2 dora hipaa
        ciso vciso msp mssp partner partners socio socios audit auditoria auditoría vendor
        proveedores incident incidente roadmap crown jewel joyas corona integration
        integrations integración integraciones crowdstrike okta aws azure demo demos
        agendar book meeting reunión pricing price precio cost costo insurance seguro
        cibernético trust report informe form formulario email correo phone teléfono
        company empresa enterprise multi workspace subsidiaries filiales ai ia dashboard
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
_DAYS_IN_NOTE = 10
_TIMES_IN_NOTE = 16


async def _silence() -> AsyncGenerator[Any, None]:
    for _ in ():
        yield


def _clip(items: list[str] | tuple[str, ...], most: int) -> str:
    more = f"; and {len(items) - most} more" if len(items) > most else ""
    return "; ".join(items[:most]) + more


def _match(want: str, options: list[str] | tuple[str, ...]) -> str | None:
    """The option ``want`` names: the same words, else the one it begins, else
    the one it is inside — how the page itself matches. Case, accents,
    underscores and punctuation do not count: "faq start" is "faq_start"."""

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
#: it. Matched on their own words, English or Spanish, folded; a specific place
#: beats a general one, and among specific ones the first named wins. Each
#: target is (path, place); a path of "" is the page in front.
Target = tuple[str, str | None]

_ASKED: tuple[tuple[re.Pattern[str], Target], ...] = tuple(
    (re.compile(rf"\b(?:{w})", re.IGNORECASE), target)
    for w, target in (
        (r"soc ?2 report|informe soc|reporte soc", (TRUST_PATH, "soc2")),
        (
            r"trust center|your own security|pen ?test\w*|penetration test\w*|"
            r"how do you (?:protect|secure)|seguridad de (?:la plataforma|ustedes|sus datos)",
            (TRUST_PATH, "controls"),
        ),
        (r"sub-?processors?|subprocesadores|subencargados", ("/sub-processors", None)),
        (
            r"responsible disclosure|bug bounty|divulgacion responsable",
            ("/responsible-disclosure-policy", None),
        ),
        (
            r"partners? program|become a partner|ser partner|programa de (?:partners|socios)",
            (PARTNERS_PATH, "benefits"),
        ),
        (
            r"\bmssps?\b|\bmsps?\b|managed service|reseller|\bvars?\b|channel|canal",
            (PARTNERS_PATH, "why_partner"),
        ),
        (r"multi-?tenan\w*|multitenencia|marketplace", (PARTNERS_PATH, "benefits")),
        (
            r"insurance|insurer|premium|seguro\w* (?:cibernetico|de ciber)|aseguradora|poliza",
            (INSURANCE_PATH, "benefits"),
        ),
        (r"crown jewel|joyas de la corona|\bcja\b", (PLATFORM_PATH, "modules")),
        (
            r"risk register|registro de riesgos|vendor risk|third[- ]party|proveedores|terceros|"
            r"incident response|respuesta a incidentes|roadmap|hoja de ruta|modules?\b|modulos?",
            (PLATFORM_PATH, "modules"),
        ),
        (r"dashboards?|tableros?|paneles", (PLATFORM_PATH, "dashboards")),
        (r"automat\w*|automatiz\w*|evidence collection|evidencia", (PLATFORM_PATH, "automation")),
        (
            r"compar\w* (?:with|to|con)|versus|\bvs\b|competitor|competencia|alternativ\w*",
            (PLATFORM_PATH, "comparison"),
        ),
        (
            r"subsidiar\w*|filiales|business units|unidades de negocio|multi-?workspace|"
            r"several countries|varios paises",
            (SPOS_PATH, "multi_workspace"),
        ),
        (r"audit\w*|auditor\w*", (SPOS_PATH, "audit_performance")),
        (
            r"quantif\w*|cuantific\w*|cuantitativ\w*|quantitative|financial risk",
            (SPOS_PATH, "risk_performance"),
        ),
        (
            r"polic(?:y|ies) management|document management|gestion documental|politicas",
            (SPOS_PATH, "document_management"),
        ),
        (
            r"ai suggestions|ai-powered|sugerencias de ia|inteligencia artificial para riesgos",
            (SPOS_PATH, "ai_suggestions"),
        ),
        (
            r"enterprise|large compan\w*|gran empresa|corporativ\w*|security performance",
            (SPOS_PATH, "hero"),
        ),
        (
            r"integrat\w*|integra\w*|connect\w* (?:to|with)|conecta\w*|crowdstrike|okta|"
            r"sentinelone|tenable|qualys|rapid7|snyk|intune|entra|jira|\baws\b|azure|google cloud",
            (HOME, "integrations"),
        ),
        (r"how does (?:it|enveedo) work|como funciona", (HOME, "how_it_works")),
        (
            r"impact timeline|linea de tiempo|time to value|how long (?:until|to)",
            (HOME, "timeline"),
        ),
        (r"\broi\b|results|resultados|impact|impacto|5x|faster risk", (HOME, "impact_stats")),
        (r"testimonial\w*|reviews?|opiniones|what (?:do )?customers say", (HOME, "testimonials")),
        (
            r"customers|clients|clientes|who uses|quien (?:lo )?usa|case stud\w*|caso de exito",
            (HOME, "customers"),
        ),
        (
            r"frameworks?|marcos?|normativas?|regulations?|regulaciones|standards?|estandares|compliance|cumplimiento",
            (FRAMEWORKS_PATH, "intro"),
        ),
        (
            r"founders?|fundador\w*|\bceo\b|who (?:is|are) behind|equipo|the team|leadership",
            (ABOUT_PATH, "team"),
        ),
        (r"investors?|inversionistas|inversores|funding|financiamiento", (ABOUT_PATH, "investors")),
        (r"mission|mision|vision|philosophy|filosofia", (ABOUT_PATH, "tab_mission")),
        (r"principles|principios|values|valores", (ABOUT_PATH, "principles")),
        (r"glossary|glosario|encyloCISO|what is a vciso|que es un vciso", (FAQ_PATH, "glossary")),
        (r"training|capacitacion|onboarding", (FAQ_PATH, "faq_training")),
        (
            r"how do i (?:start|get started)|como empiezo|como empezar|free (?:risk )?assessment|evaluacion gratuita",
            (FAQ_PATH, "faq_start"),
        ),
        (r"\bfaqs?\b|preguntas frecuentes|enveedopedia", (FAQ_PATH, "faq_general")),
        (r"webinars?|e-?books?|case study|customer story|hail", (LIBRARY_PATH, "library")),
        (
            r"where are you|headquarter\w*|offices?|oficinas?|miami|direccion|address|phone number|telefono de",
            (CONTACT_PATH, "contact_info"),
        ),
    )
)
#: What a tool moves rather than a cue: the demo scheduler, a form, a link in
#: a new tab, a tab switch.
_BY_TOOL = re.compile(
    r"\b(?:demo\w*|book\w*|agend\w*|schedul\w*|reserv\w*|meeting|reunion|calendar\w*|"
    r"calendario|briefing|formulario|form\b|fill|llena\w*|complet\w*|escrib\w*|message|"
    r"mensaje|contacten|contactarme|contact me|call me|my name|me llamo|mi nombre|"
    r"my email|mi correo|my phone|mi telefono|mi celular|arroba|submit|enviar|pdf|"
    r"download|descarg\w*|blog|sign ?in|log ?in|iniciar sesion|tabs?|pestanas?|"
    r"request the (?:soc|report)|pedir el informe)\b",
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


# A remark about the page's own language (Explora's prod call be1f5b9a: "Me
# está mostrando la página en inglés. ¿Se la puedes mostrar en español?",
# answered "Ya la cambié" with nothing sent to the page).
_PAGE_WORDS = re.compile(
    r"\b(?:p[aá]gina|sitio|web|pantalla|page|site|website|screen)\b", re.IGNORECASE
)
_LANGUAGE_WORDS: dict[Lang, re.Pattern[str]] = {
    "es": re.compile(r"\b(?:espa[nñ]ol|castellano|spanish)\b", re.IGNORECASE),
    "en": re.compile(r"\b(?:ingl[eé]s|english)\b", re.IGNORECASE),
}


def asked_page_language(text: str, spoken: Lang, page: Lang | None) -> Lang | None:
    """The language ``text`` asks the page to be shown in, when that is the
    call's language and the page in front is not in it: "show me the page in
    Spanish", "the page is in English". Asking for the page in the *other*
    language is a request about the call, and is the model's."""
    if page is None or page == spoken or not _PAGE_WORDS.search(text):
        return None
    named = {lang for lang, rx in _LANGUAGE_WORDS.items() if rx.search(text)}
    return spoken if spoken in named or named == {page} else None


#: Aliases that are only a country's name: "we're in Mexico" names no law.
_COUNTRY_ALIASES = frozenset(
    "mexico colombia argentina peru panama brazil brasil spain espana chile".split()  # noqa: SIM905
) | {"costa rica"}


def framework_named(text: str) -> Framework | None:
    """The framework card ``text`` names by one of its aliases, the longest
    alias first; ``None`` for none. A country alone names none."""
    said = f" {re.sub(r'[^a-z0-9./ -]', ' ', norm(text))} "
    best: tuple[int, Framework] | None = None
    for f in FRAMEWORKS:
        for alias in (norm(f.name), *f.aliases):
            if len(alias) < 3 or alias in _COUNTRY_ALIASES:
                continue
            if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", said) and (
                best is None or len(alias) > best[0]
            ):
                best = (len(alias), f)
    return best[1] if best else None


def asked_target(text: str) -> Target | None:
    """Where on the site what ``text`` asks about is shown, or ``None``. The
    demo, a form, a link and a tab are moved by their tools, and "can you speak
    Spanish?" is about this call: none of them is a place."""
    said = fold(text)
    if _BY_TOOL.search(said) or asks_call_language(text):
        return None
    named = [
        (m.start(), m.start() - m.end(), i, target)
        for i, (rx, target) in enumerate(_ASKED)
        if (m := rx.search(said))
    ]
    # Enveedo's own SOC 2 report beats the SOC 2 framework card.
    if any(target[0] == TRUST_PATH for *_, target in named):
        return min(n for n in named if n[3][0] == TRUST_PATH)[3]
    if (f := framework_named(text)) is not None:
        return (FRAMEWORKS_PATH, f.key)
    if not named:
        return None
    return min(named)[3]


def asked_page(text: str) -> str | None:
    """The page :func:`asked_target` shows ("" is the page in front)."""
    target = asked_target(text)
    return target[0] if target else None


# ─── Their details ─────────────────────────────────────────────────────────────

_EMAIL = re.compile(r"^[\w.+-]+@[\w-]+(?:\.[\w-]+)+$")
#: A card number: never typed by him.
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_PASSWORD = re.compile(r"\b(?:password|contraseña|contrasena|clave)\b", re.IGNORECASE)

#: The contact form's countries, as its select writes them (checked
#: 2026-10-28). "Others" stands for any country not on it.
COUNTRIES: tuple[str, ...] = (
    "Antigua and Barbuda", "Argentina", "Australia", "Bahamas", "Barbados", "Belize",
    "Bolivia", "Botswana", "Brazil", "British Virgin Islands", "Canada", "Chile",
    "Colombia", "Costa Rica", "Cuba", "Dominica", "Dominican Republic", "Ecuador",
    "El Salvador", "Guatemala", "Guyana", "Honduras", "India", "Israel", "Jamaica",
    "Marshall Islands", "Mexico", "Nicaragua", "Others", "Panama", "Paraguay", "Peru",
    "Saint Kitts and Nevis", "Singapore", "Somalia", "South Korea", "Suriname",
    "Thailand", "Trinidad and Tobago", "United States", "Uruguay",
)  # fmt: skip
#: The Spanish (and common English) names a visitor says for a listed country.
_COUNTRY_SAID: dict[str, str] = {
    "brasil": "Brazil", "canada": "Canada", "mexico": "Mexico", "peru": "Peru",
    "panama": "Panama",
    "republica dominicana": "Dominican Republic", "estados unidos": "United States",
    "usa": "United States", "us": "United States", "united states of america": "United States",
    "eeuu": "United States", "ee uu": "United States", "america": "United States",
    "corea del sur": "South Korea", "korea": "South Korea", "tailandia": "Thailand",
    "singapur": "Singapore", "jamaica": "Jamaica", "trinidad y tobago": "Trinidad and Tobago",
    "islas virgenes britanicas": "British Virgin Islands", "san cristobal y nieves":
    "Saint Kitts and Nevis", "botsuana": "Botswana", "belice": "Belize",
}  # fmt: skip


def country_option(said: str) -> str:
    """The contact form's option for a country as said: the option itself, its
    Spanish name, else "Others"."""
    want = norm(said).strip(" .")
    for c in COUNTRIES:
        if norm(c) == want:
            return c
    return _COUNTRY_SAID.get(want, "Others")


#: The moves the page answers (``command_done`` or ``command_failed``), and how
#: long each may take, a full page load included.
_MOVE_TAKES_S = {"fill_form": 45.0}
#: Words of his still playing hold the floor no longer than this.
_PLAYOUT_MAX_S = 30.0
#: The longest message he writes into a form.
_MESSAGE_MAX = 900

#: His own words telling them to press Submit or confirm, which the page's
#: "ready" then need not repeat, if said this recently.
_PRESS_HINT = re.compile(r"\b(?:submit|enviar|confirm\w*)\b")
_PRESS_HINT_S = 20.0


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
    enveedo security seguridad""".split()  # noqa: SIM905
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


#: Places a sentence names outright, in either language. Each is (pattern over
#: the folded sentence, page, place).
_NAMED: tuple[tuple[re.Pattern[str], str, str], ...] = tuple(
    (re.compile(rf"\b(?:{w})\b"), page, key)
    for w, page, key in (
        (r"control performance|desempeno de controles", SPOS_PATH, "control_performance"),
        (r"risk performance|desempeno de riesgos?", SPOS_PATH, "risk_performance"),
        (r"audit performance|desempeno de auditoria", SPOS_PATH, "audit_performance"),
        (r"document management|gestion de documentos", SPOS_PATH, "document_management"),
        (r"multi ?workspace", SPOS_PATH, "multi_workspace"),
        (r"impact timeline", HOME, "timeline"),
        (r"soc 2 type (?:ii|2|two)|soc 2 tipo|informe soc 2|soc 2 report", TRUST_PATH, "soc2"),
        (r"multitenan\w*|multitenencia", PARTNERS_PATH, "benefits"),
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


def describe_framework(f: Framework, lang: Lang) -> str:
    """What find_framework hands the model for one card."""
    group = {"infosec": "Information Security", "ai": "AI", "privacy": "Privacy"}[f.group]
    blurb = f" The card says: «{f.blurb}»" if f.blurb else ""
    return f"{f.name} (key {f.key}, {group} Frameworks).{blurb}"


def _resolve_day(text: str, today: date) -> str | None:
    """An ISO day from a relative one the model passed through: "today",
    "tomorrow", "mañana"; else ``None``."""
    t = norm(text)
    if t in ("today", "hoy"):
        return today.isoformat()
    if t in ("tomorrow", "manana", "mañana"):
        return (today + timedelta(days=1)).isoformat()
    return None


# ─── The brain ─────────────────────────────────────────────────────────────────


class EnveedoBrain(OpenAIBrain):
    """One per session. Javier: Enveedo's knowledge, its pages and places in
    both languages, the demo scheduler and the forms the visitor fills with
    him, and a mirror of their tabs, in English or Spanish."""

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
            system_instruction=_prompt(self.kb),
            model=model,
            reasoning=REASONING,
        )
        self._heard_at = float("-inf")
        #: The visitor's time zone, as the page reports it.
        self.tz = ZoneInfo(DEFAULT_TIMEZONE)
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
        #: The tab in front as it last reported itself, its English path, its
        #: language, and whether the model has seen it since it changed.
        self.page: PageChanged | None = None
        self._path = HOME
        self._page_lang: Lang = "en"
        self._page_unseen = False
        #: Every open Enveedo tab, and which is in front.
        self.tabs: list[TabInfo] = []
        self._active = ""
        self._tabs_unseen = False
        #: The forms as the page last reported them, and the scheduler.
        self.forms: dict[FormName, FormState] = {}
        self.demo: DemoState | None = None
        #: The scheduler's details given so far: what is filled stays.
        self._demo_fields: dict[str, str] = {}
        self._demo_duration: str | None = None
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
        #: A talk-through owed that is not a move's answer (the scheduler's
        #: days, the site's answer to their press).
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
        #: When he last told them to press Submit or confirm himself.
        self._press_hint_at = float("-inf")
        self._playing = 0
        self._played_at = 0.0
        self._idle_deferred = False

    @property
    def today(self) -> date:
        """Today where the visitor is."""
        return self._today or datetime.now(self.tz).date()

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        init = session.init or {}
        reported = str(init.get("path") or init.get("url") or "/")
        self._path = self.kb.english_path(reported)
        self._cue_path = self._path
        self.tz = _zone(init.get("tz"))
        # The page sends `lang` only once the visitor has pressed the toggle.
        chosen = init.get("lang")
        self._chosen = chosen in LANGUAGE_NAMES
        site_es = init.get("site_lang") == "es" or kb.is_spanish(reported)
        self._page_lang = "es" if site_es else "en"
        # English unless they chose Spanish, or are reading the Spanish site
        # (not held to it: what they speak still moves the call).
        self.spoken = "es" if chosen == "es" or (chosen is None and site_es) else OPENING
        await session.configure(
            Config(
                stt=SttConfig(language=self.spoken, patience=ENVEEDO_PATIENCE),
                tts=TtsConfig(voice=VOICE, language=self.spoken),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
            )
        )
        # The tab keeps the call's language for the whole call, on every page;
        # the page they opened the call on stays as it is.
        session.dispatch(LanguageChanged(language=self.spoken, site="stay"))
        logger.info(
            "enveedo: session start on {} in {}{} ({})",
            reported,
            self.spoken,
            " (chosen)" if self._chosen else "",
            self.tz.key,
        )
        today = self.today
        self._note(
            f"[Today is {today:%A}, {today:%B} {today.day}, {today.year}, in the visitor's time "
            f"zone ({self.tz.key}).]"
        )
        if self._chosen:
            self._note(_chosen_note(self.spoken, "before the call"))

    async def greet(self, session: Session) -> str:
        """The opener, written not generated."""
        return for_the_voice(greeting(self._path, self.spoken, self.kb), self.spoken)

    async def on_finalize(self, session: Session, fin: Finalize) -> None:
        """What was heard goes into the model's context, spelled as the site
        writes it, so the model never sees "sock two" in its own words."""
        heard = from_the_voice(fin.heard)
        if heard != fin.heard:
            fin = dataclasses.replace(fin, heard=heard)
        await super().on_finalize(session, fin)
        self._playing = max(0, self._playing - 1)
        self._floor_free()

    def on_user_message(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]:
        return self._own_turn(self._answer(session, msg))

    async def _answer(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]:
        """A visitor who speaks the other language is answered in it from the
        first word, unless they chose the language they are in; the tab they
        moved to is read in with what they said; his nod covers the model's
        thinking, and his own line any dead air after it."""
        heard = None if self._chosen else language_of(msg.text)
        if heard is not None and heard != self.spoken:
            await session.configure(self._speaking(heard))
            logger.info("enveedo: language -> {} (heard)", heard)
        self._talk = None
        self._outcomes.clear()
        self._idle_deferred = False
        self._playing = 0
        self._nudges = 0
        # "Show me the page in Spanish" is done in code, not left to a model
        # that may say it was done and do nothing.
        page_language = asked_page_language(msg.text, self.spoken, self._page_lang)
        self._backstop = (
            None
            if asks_call_language(msg.text) or page_language is not None
            else asked_target(msg.text) or self._backstop
        )
        self._by_tool = bool(_BY_TOOL.search(fold(msg.text)))
        self._restore_idle()
        self._read_in_screen()
        if page_language is not None:
            self._show_in(page_language)
        now = time.monotonic()
        fragment, self._heard_at = now - self._heard_at < _FRAGMENT_S, now
        nod = None if fragment else self._ack.line(msg.text, self.spoken)
        floor: Floor[Lang] = self._ack
        if nod is not None:
            logger.info("enveedo: ack {!r}", nod)
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

        What the page answered after his turn (the scheduler's open days, the
        form complete, a field the site refused, their press confirmed) is in
        the context already, and the idle window was shortened for it, so they
        hear it from him here. Otherwise an ordinary quiet spell: a nudge,
        twice, then silence.

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
                "could show them next, or the demo. Then let them browse."
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
        back with nothing at all is asked once more, with tools off.

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
            logger.warning("enveedo: the model returned nothing; asking once more")
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
                logger.info("enveedo: language -> {} (written)", written)
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
                    text = for_the_voice(event.text, self.spoken)
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
        logger.info("enveedo: the reply has no cue; showing {} first", cue)
        return f"{cue}{chunk}"

    def _send_cue(self, raw: RawCue) -> None:
        """Check a cue against the site, as the tools do, and send it; one that
        names nothing real is dropped and logged rather than reaching the page."""
        if raw.at:
            raw = dataclasses.replace(raw, at=_anchor_for_voice(raw.at, self.spoken))
        cue = self._resolve_cue(raw)
        logger.info("enveedo: cue {} {!r} at {!r} -> {}", raw.kind, raw.value, raw.at, cue)
        if cue is not None:
            self._paged = self._paged or cue.path is not None
            if raw.kind != "page":
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
                logger.info("enveedo: he talks about {} with no cue; opening it", target[0])
                out.append(("page", target[0]))
                path = target[0]
        self._cue_path = path
        # They are dictating their details: the form is on their screen, and stays.
        if kinds & {"show", "faq"} or self._by_tool:
            return out
        named = named_place(sentence)
        # A framework he names on the frameworks page: its card.
        if named is None and path == FRAMEWORKS_PATH and not sentence.rstrip().endswith("?"):
            f = framework_named(sentence)
            named = (FRAMEWORKS_PATH, f.key) if f is not None else None
        if named is not None and named[1] != self._shown:
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
        """The crawl's English page, or one of the core pages the site serves
        when the crawl does not have it."""
        path = self.kb.english_path(path_or_url)
        if (page := self.kb.page(path)) is not None:
            return page
        title = CORE_PAGES.get(path)
        return Page(path=path, title=title) if title is not None else None

    def _places_on(self, path: str, *, live: bool) -> list[Anchor]:
        """The places a cue may name on ``path``: the catalogue's, and, on the
        page in front, any other place it reported."""
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
        """The one English page whose catalogue has ``key``, if exactly one does."""
        have = [
            p
            for p, anchors in self.kb.anchors.items()
            if not p.startswith("/es/") and any(a.key == key and not a.hidden for a in anchors)
        ]
        return have[0] if len(have) == 1 else None

    def _resolve_cue(self, raw: RawCue) -> Cue | None:
        if raw.kind == "page":
            page = self._page_for(raw.value)
            if page is None:
                return None
            self._cue_path = page.path
            return Cue(at=raw.at, word=raw.word, path=page.path)
        if raw.kind == "faq":
            # An FAQ question is a place: its accordion opens.
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
        live = self.page is not None and not moved
        if target is not None and target.sections and not live and not _on_page(raw.value, target):
            logger.info("enveedo: {!r} is not on {}; dropped", raw.value, target.path)
            return None
        if re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)+", raw.value.strip()):
            # A key that is nowhere: never sent as words to look for.
            logger.info("enveedo: no place {!r}; dropped", raw.value)
            return None
        return Cue(
            at=raw.at, word=raw.word, path=self._cue_path if moved else None, text=raw.value[:120]
        )

    def _talk_now(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The one extra request a turn with nothing in it gets: tools off."""
        return self.respond_with(session, tools=ToolChoice.NONE)

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Page→brain events, folded in silently: no floor taken, no turn."""
        event = ENVEEDO_EVENTS.parse(msg)
        if event is None:
            return
        logger.info("enveedo: {} — {}", type(event).__voqal_event__, event)
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
            logger.warning("enveedo: switch to {} refused: {}", event.language, rejected)
            self.spoken = was
            session.dispatch(LanguageChanged(language=was))
            return
        logger.info("enveedo: language -> {} (toggle)", event.language)
        self._chosen = True
        self._confirm = TOGGLE_CONFIRM[event.language]
        self._shorten_idle()
        self._note(_chosen_note(event.language, "on the toggle"))

    def _speaking(self, language: Lang) -> Config:
        """Both legs of ``language``, recorded as the one he speaks now, and the
        widget's toggle moved to it; the page in front follows (its twin)."""
        if language != self.spoken:
            self.session.dispatch(LanguageChanged(language=language))
        self.spoken = language
        return Config(
            stt=SttConfig(language=language, patience=ENVEEDO_PATIENCE),
            tts=TtsConfig(voice=VOICE, language=language),
        )

    def _show_in(self, language: Lang) -> None:
        """Load the page in front's own twin in ``language``, now."""
        logger.info("enveedo: the page in front is asked for in {}", language)
        self.session.dispatch(LanguageChanged(language=language, site="twin"))
        name = LANGUAGE_NAMES[language]
        self._note(
            f"[The page in front is loading in {name} now. Say so in a few words, and never "
            f"say it has changed until the screen lines show the {name} page.]"
        )

    # ─── Page → brain ───────────────────────────────────────────────────

    def apply_event(self, event: EnveedoEvent) -> str | None:
        """Patch the mirror; return the line the model should see."""
        match event:
            case PageChanged():
                self.page = event
                self._path = self.kb.english_path(event.path)
                self._page_lang = event.lang
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
            case DemoState():
                return self._demo_changed(event)
            case DemoScheduled():
                return self._demo_scheduled(event)
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
                    f"[A screen cue of yours did not land ({event.reason}). It is not on their "
                    "screen, so never say it is. If the visitor asks where it is, show it again; "
                    "otherwise carry on.]"
                )
            case CommandFailed() if event.command == "language_changed":
                return (
                    f"[The page in front stays as it is ({event.reason}): it has no version in "
                    "that language. Say so plainly if the visitor asked; never say it changed.]"
                )
            case CommandFailed() if event.command == "book_demo":
                self._talk_through(
                    "The demo scheduler did not do what you sent it. Say so plainly in a "
                    "sentence, and offer to open the scheduler's own page in a new tab."
                )
                return (
                    f"[The demo scheduler did not take that ({event.reason}). It did not happen: "
                    "never say it did.]"
                )
            case CommandFailed():
                self._answered(event.command, f"{event.command} not done: {event.reason}")
                return (
                    f"[Not done on the page ({event.command}): {event.reason}. Tell the visitor "
                    "plainly and offer what you can do instead; never say it worked.]"
                )

    def _demo_changed(self, event: DemoState) -> str | None:
        before = self.demo
        if event.step == "loading" or (event.step == "calendar" and not event.days):
            self.demo = event if before is None else before
            # The scheduler loads several seconds after the page.
            return "[The demo scheduler is still loading: it has listed no days yet.]"
        self.demo = event
        if event.duration:
            self._demo_duration = event.duration
        zone = f" Times are in {event.timezone}." if event.timezone else ""
        if event.step == "details":
            filled = [k for k, v in event.filled.model_dump().items() if v]
            note = (
                f"[The demo scheduler is at its details step for {event.date} at {event.time}"
                f"{f', {event.duration}' if event.duration else ''}.{zone} Filled: "
                f"{', '.join(filled) or 'nothing'}. Still empty: "
                f"{', '.join(event.missing) or 'nothing required'}. The visitor presses its "
                "confirm button themselves.]"
            )
            if before is None or before.step != "details":
                self._talk_through(
                    "The scheduler's details step is on their screen. Say the day and time back "
                    "to them in one sentence, and ask for the next detail still empty (first "
                    "name, last name, then work email)."
                )
            elif not event.missing and before.missing:
                self._talk_through(
                    "Every detail is in the scheduler now. Say so in a sentence: they check it "
                    "and press its confirm button themselves."
                )
            return note
        if event.step == "scheduled":
            return "[The demo scheduler shows the meeting as scheduled.]"
        days = _clip(event.days, _DAYS_IN_NOTE) or "none this month"
        lengths = f" Lengths: {', '.join(event.durations)}." if event.durations else ""
        chosen = f" Length chosen: {event.duration}." if event.duration else ""
        note = (
            f"[The demo scheduler shows {event.month or 'this month'}. Open days: {days}."
            f"{lengths}{chosen}"
        )
        if event.date and event.times:
            note += f" Times on {event.date}: {_clip(event.times, _TIMES_IN_NOTE)}."
        elif event.date:
            note += f" {event.date} is chosen; its times are not listed yet."
        note += f"{zone}]"
        if (
            before is None
            or before.step == "loading"
            or (before.days != event.days and not before.date)
        ):
            self._talk_through(
                "The demo scheduler is on their screen with its open days. Name two or three of "
                "them in one sentence, and ask which day suits them."
            )
        elif event.date and event.times and before.times != event.times:
            self._talk_through(
                f"The scheduler now lists the times for {event.date}. Read two or three of them "
                "in one sentence, and ask which suits them."
            )
        return note

    def _demo_scheduled(self, event: DemoScheduled) -> str:
        when = " ".join(x for x in (event.date, event.time) if x) or "the chosen slot"
        if event.blocked:
            self._talk_through(
                "They have just pressed the scheduler's confirm button. This is a preview, so the "
                "page held it back: say plainly in one sentence that in this preview the booking "
                "is not sent to Enveedo, thank them, and offer to keep answering questions."
            )
            return (
                f"[The visitor pressed confirm for {when}. This preview held it back: nothing "
                "reached Enveedo's calendar.]"
            )
        self._talk_through(
            "They have just booked the demo. Thank them in one sentence, say Elis Martinez's "
            "team will meet them on Microsoft Teams then, and offer to keep answering questions."
        )
        return f"[The visitor confirmed the demo for {when}.]"

    def _form_state(self, event: FormState) -> str:
        was = self.forms.get(event.form)
        self.forms[event.form] = event
        name = FORM_NAMES[event.form]
        values = "; ".join(f"{k}: {v}" for k, v in event.values.items() if v)
        who = "they typed in it themselves" if event.by == "visitor" else "after your fill"
        note = (
            f"[The {name}, {who}: filled {', '.join(event.filled) or 'nothing'}; still empty "
            f"{', '.join(event.missing) or 'nothing'}"
        )
        if event.invalid:
            note += f"; the site would refuse {', '.join(event.invalid)}"
        if values:
            note += f". It holds: {values}"
        note += "."
        if event.ready:
            note += " It is complete: they press Submit themselves.]"
        else:
            note += "]"
        # Everything of his is in, and only their part is left: the consent box.
        theirs = {"consent"}
        only_theirs = bool(event.missing) and set(event.missing) <= theirs and not event.invalid
        was_theirs = was is not None and bool(was.missing) and set(was.missing) <= theirs
        told = time.monotonic() - self._press_hint_at < _PRESS_HINT_S
        if only_theirs and not was_theirs and not told:
            self._talk_through(
                f"The {name} has everything you can fill. Say in a sentence or two that it is "
                "ready, that they tick the consent box and press Submit themselves when they have "
                "checked it. Never say it was sent."
            )
        elif event.ready and (was is None or not was.ready) and not told:
            self._talk_through(
                f"The {name} is complete. Say in a sentence that they press Submit themselves "
                "when they have checked it. Never say it was sent."
            )
        return note

    def _form_result(self, event: FormResult) -> str:
        name = FORM_NAMES[event.form]
        said = f" ({event.message})" if event.message else ""
        if event.outcome == "sent":
            follow = (
                "the team will send the report"
                if event.form == "soc2"
                else "Enveedo's team will get back to them"
            )
            self._talk_through(
                f"They pressed Submit and the site confirmed the {name} was sent. Thank them in "
                f"one sentence, say {follow}, and offer one last thing: the demo, or a question."
            )
            return f"[The site confirmed the {name} was sent{said}.]"
        if event.outcome == "failed":
            phone = self.kb.contact.get("phone", "+1 786 648 6418")
            email = self.kb.contact.get("email", "info@enveedo.com")
            self._talk_through(
                f"The site could not send the {name} (its security check did not pass, or the "
                f"request failed). Say so plainly: they can press Submit again, or write to "
                f"{email} or call {phone}. Never say it was sent."
            )
            return f"[The site failed to send the {name}{said}.]"
        fields = ", ".join(event.fields)
        self._talk_through(
            f"The site refused the {name} when they pressed Submit"
            + (f": {event.message}" if event.message else "")
            + (f" (fields: {fields})" if fields else "")
            + ". Say plainly what is wrong in a sentence, ask for the corrected detail, and fill "
            "it in again once they say it. Never say it was sent."
        )
        return (
            f"[The site refused the {name}: {event.message or 'an error'}"
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
            self._note(f"[The visitor's open Enveedo tabs — {listed}.]")
        self._tabs_unseen = False
        if not self._page_unseen or self.page is None:
            return
        self._page_unseen = False
        p = self.page
        spanish = " (the Spanish version)" if p.lang == "es" else ""
        note = f"[The tab in front shows “{p.title or p.path}” ({p.path}){spanish}, {p.kind}."
        if self.spoken == "es" and p.lang == "en":
            note += (
                " It is in English: it is loading in Spanish, or has no Spanish version."
                if self.kb.spanish_path(self._path)
                else " It has no Spanish version."
            )
        own = [a for a in p.anchors if a not in _CHROME]
        if own:
            note += f" Its places: {_clip(own, _ANCHORS_IN_NOTE)}."
        if p.form == "demo":
            note += " It has the demo scheduler."
        elif p.form in FORM_NAMES:
            note += f" It has the {FORM_NAMES[p.form]}."
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
        the page now, or, if this one failed, is dropped and said."""
        if command not in self._sent:
            return
        del self._sent[command]
        if (queued := self._queued) is not None and not self._busy():
            self._queued = None
            name = queued.__voqal_action__
            if " done" in outcome:
                logger.info("enveedo: {} answered; sending the {} queued", command, name)
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
        if (
            isinstance(queued, FillForm)
            and isinstance(action, FillForm)
            and queued.form == action.form
        ):
            merged = {k: v for k, v in queued.model_dump().items() if v is not None}
            merged |= {k: v for k, v in action.model_dump().items() if v is not None}
            action = FillForm(**merged)
        self._queued = action
        landed(_LANDED["queued"][self.spoken])
        logger.info("enveedo: {} queued behind {}", action.__voqal_action__, running)
        return (
            f"Queued, not sent yet: the page is still working on {running}. It goes to the page "
            "as soon as the page answers that. Say in a few words that you are noting it; never "
            "that it is done, and do not call it again."
        )

    def _take_ask(self) -> str | None:
        """What he has to talk through now — the page's answers to his moves,
        the scheduler's days, the site's answer to their press — and nothing
        left after."""
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

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        """Read and search Enveedo's knowledge and its frameworks; book the
        demo; fill the contact form or the SOC 2 request as they dictate; open
        a link in a new tab; move between their tabs; switch language."""
        return [
            self.read_topic,
            self.search_site,
            self.find_framework,
            self.book_demo,
            self.fill_form,
            self.open_link,
            self.switch_tab,
            self.set_language,
        ]

    @needs_result_now
    async def read_topic(self, request: TopicRequest) -> str:
        """Read one of Enveedo's knowledge topics before answering from it."""
        topic = self.kb.topics.get(request.topic)
        if topic is None:
            return f"No topic '{request.topic}' is written yet: use search_site."
        return topic.text

    @needs_result_now
    async def search_site(self, request: SearchRequest) -> str:
        """Search enveedo.com's pages and places, English and Spanish. Each
        result names the page path (English) and the place's key to show."""
        hits = self.kb.search(request.query, _SEARCH_HITS)
        if not hits:
            return (
                f"Nothing on the site matches '{request.query}'. Try other words, or say the "
                "site does not say, and offer the demo or the contact form."
            )
        out: list[str] = []
        for h in hits:
            where = f", place: {h.section}" if h.section else ""
            out.append(f"{h.title} — path: {h.path}{where}\n  {h.snippet}")
        return "\n".join(out)

    @needs_result_now
    async def find_framework(self, request: FrameworkRequest) -> str:
        """Find a framework, standard or law among the 39 cards on /frameworks,
        by any name the visitor uses. Returns each card's key to show, with
        what the card says."""
        found = self.kb.find_framework(request.query)
        if not found:
            return (
                f"No card matches '{request.query}': it is not among the 39 frameworks the page "
                "lists (the home page claims more than 45). Say so honestly, never that it is "
                "supported, and offer the demo, where the team can say whether it is. You may "
                f"show the page's groups: {{page: {FRAMEWORKS_PATH}}}{{show: intro}}."
            )
        first, rest = found[0], found[1:4]
        out = [
            f"Found: {describe_framework(first, self.spoken)}",
            f"Show it with {{page: {FRAMEWORKS_PATH}}}{{show: {first.key}}} (just "
            f"{{show: {first.key}}} if they are on the frameworks page). It is listed on the "
            "page; the Assessment module assesses and monitors compliance against it. Never say "
            "Enveedo certifies anyone.",
        ]
        if rest:
            out.append("Also close: " + "; ".join(f"{f.name} ({f.key})" for f in rest) + ".")
        return "\n".join(out)

    async def book_demo(self, request: DemoRequest) -> str:
        """Open the demo scheduler on /book-a-demo, or add to it: the length,
        day and time they chose, and their first name, last name and email as
        they give them. What is filled stays. It never presses the scheduler's
        confirm button. The scheduler's open days, times and details step come
        back to you from the page."""
        for key in ("first_name", "last_name", "email"):
            value = getattr(request, key)
            if isinstance(value, str) and value.strip():
                value = " ".join(value.split())
                if key == "email":
                    value = "".join(value.split()).lower()
                    if not _EMAIL.match(value):
                        return (
                            f"Not filled: {value!r} is not an email address. Ask them to spell "
                            "it again."
                        )
                self._demo_fields[key] = value
        if request.duration:
            self._demo_duration = request.duration
        day = request.day
        if day:
            day = _resolve_day(day, self.today) or day
            if self.demo is not None and self.demo.days:
                day = _match(day, self.demo.days) or day
        time_ = request.time
        if time_ and self.demo is not None and self.demo.times:
            time_ = _match(time_, self.demo.times) or time_
        fields = self._demo_fields
        self._move(
            BookDemo(
                duration=self._demo_duration,
                day=day,
                time=time_,
                first_name=fields.get("first_name"),
                last_name=fields.get("last_name"),
                email=fields.get("email"),
            ),
            "demo_filled" if day or time_ or fields else "demo",
        )
        parts = [x for x in (self._demo_duration, day, time_) if x]
        filled = ", ".join(fields) or "nothing"
        out = (
            f"Sent to the page: open the demo scheduler on {DEMO_PATH}"
            f"{(', choose ' + ', '.join(parts)) if parts else ''}; details sent: {filled}. "
            "Nothing is confirmed yet: the page reports the scheduler's days, times and details "
            "in a line in square brackets, or that it failed. Until then, say only that you are "
            "opening it or putting it in, and name no day or time it has not listed. The "
            "visitor presses its confirm button themselves."
        )
        if "email" in fields and request.email:
            out += " Spell the email back letter by letter."
        return out

    async def fill_form(self, request: FormRequest) -> str:
        """Fill the contact form (/contact) or the SOC 2 report request
        (/trust-center) with what the visitor said: only the new fields each
        time. On another page, the form's page opens and it is filled there.
        Never sent: they tick consent and press Submit themselves."""
        form = request.form
        given = {
            k: (" ".join(v.split()) if k != "message" else v.strip())
            for k, v in request.model_dump(exclude={"form"}).items()
            if isinstance(v, str) and v.strip()
        }
        if any(_CARD.search(v) and k != "phone" for k, v in given.items()) or any(
            _PASSWORD.search(v) for k, v in given.items() if k != "message"
        ):
            return (
                "Not filled: that looks like a card number or a password, which these forms never "
                "ask for. Leave it out and tell them it is not needed."
            )
        refused: list[str] = []
        if form == "soc2":
            for k in ("phone", "country"):
                if given.pop(k, None) is not None:
                    refused.append(f"{k} is not on the SOC 2 request")
        elif given.pop("job_title", None) is not None:
            refused.append("job title is not on the contact form (put it in the message)")
        if (email := given.get("email")) is not None:
            email = "".join(email.split()).lower()
            if not _EMAIL.match(email):
                refused.append(f"email {email!r} is not an address: ask them to spell it again")
                given.pop("email")
            else:
                given["email"] = email
        if (country := given.get("country")) is not None:
            given["country"] = country_option(country)
        if (msg := given.get("message")) is not None:
            given["message"] = msg[:_MESSAGE_MAX]
        if not given:
            return "Not filled: " + ("; ".join(refused) or "nothing to fill yet.")
        here = self._path == FORM_PAGES[form] or (
            form == "contact" and self._path == FRAMEWORKS_PATH
        )
        queued = self._page_move(FillForm(form=form, **given), "form" if here else "to_form")
        if queued:
            return queued
        name = FORM_NAMES[form]
        out = (
            f"Filling {', '.join(given)} on the {name}; the page confirms in a moment."
            if here
            else (
                f"The {name}'s page is opening; {', '.join(given)} go in once it is up (a few "
                "seconds), and the page confirms. Say in a short sentence that you are taking "
                "them to the form, and keep talking."
            )
        )
        if "country" in given:
            out += f" Country set to the form's option «{given['country']}»"
            out += (
                ": say it is not on the list, so it is Others."
                if given["country"] == "Others"
                else "."
            )
        if refused:
            out += " Not filled: " + "; ".join(refused) + "."
        if "email" in given:
            out += " Read the email back letter by letter."
        if "phone" in given:
            out += " Read the phone back digit by digit."
        return out + " Never say it is sent: they tick consent and press Submit themselves."

    async def open_link(self, request: LinkRequest) -> str:
        """Open, in a new tab, a gated eBook or webinar, the blog, the platform
        PDF, the customers' sign-in, or the scheduler's own page."""
        if request.kind == "library":
            names = [x.label for x in self.kb.library]
            hit = _match(request.name, names) if request.name else None
            if hit is None and request.name:
                want = set(re.findall(r"[a-z0-9]+", fold(request.name))) - {
                    "the",
                    "a",
                    "of",
                    "el",
                    "la",
                    "de",
                }
                scored = [
                    (len(want & set(re.findall(r"[a-z0-9]+", fold(x.label)))), x.label)
                    for x in self.kb.library
                ]
                best = max(scored, default=(0, ""))
                hit = best[1] if best[0] else None
            item = next((x for x in self.kb.library if x.label == hit), None)
            if item is None:
                return (
                    f"Not opened: no eBook or webinar matches '{request.name}'. They are: "
                    + "; ".join(names)
                    + "."
                )
            self._move(OpenLink(url=item.url, label=item.label), "link")
            gated = "info.enveedo.com" in item.url
            return f"Opened «{item.label}» in a new tab." + (
                " It is gated: they register there themselves." if gated else ""
            )
        key = {
            "blog": "blog_es" if self.spoken == "es" else "blog",
            "pdf": "platform_pdf",
            "sign_in": "sign_in",
            "scheduler": "scheduler",
        }[request.kind]
        exit_ = self.kb.exits.get(key) or self.kb.exits.get(request.kind)
        if exit_ is None:
            return f"Not opened: the {request.kind} link is not loaded."
        self._move(OpenLink(url=exit_.url, label=exit_.label), "link")
        extra = {
            "sign_in": " It is for existing customers: there is no self-serve signup.",
            "scheduler": " It is the same scheduler, on its own page: they pick the slot there.",
        }.get(request.kind, "")
        return f"Opened {exit_.label} in a new tab.{extra}"

    async def switch_tab(self, request: TabRequest) -> str:
        """Bring another of the visitor's Enveedo tabs to the front."""
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
        listening and speaking; the site follows. Call it when they ask for the
        other language in words that are not already it — "Can we speak
        Spanish?" — and to go back. Say one short line in the language you are
        switching to, in the same response. A visitor already speaking Spanish
        has been switched: do not call it for them."""
        self._chosen = True
        configure_soon(self.session, self._speaking(request.language))
        logger.info("enveedo: language -> {} (asked)", request.language)
        return "ok"


__all__ = [
    "BookDemo",
    "Cue",
    "EnveedoBrain",
    "FillForm",
    "FocusTab",
    "LanguageChanged",
    "Navigate",
    "OpenLink",
    "ShowSection",
]
