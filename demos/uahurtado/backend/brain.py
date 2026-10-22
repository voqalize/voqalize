"""UahurtadoBrain — Javier, a guide for prospective students of Universidad Alberto Hurtado.

The sites are the university's, not ours: admision.uahurtado.cl (undergraduate
admission, where a prospective student spends most of their time),
postgrados.uahurtado.cl and www.uahurtado.cl. A browser extension injects the
widget and a page adapter into all three; the adapter turns each
:class:`~voqalize.sdk.Action` in :mod:`.protocol` into a move on the tab in
front — a page, a tab or accordion opened, a section ringed, the career
mega-menu, the lead form filled — and every tab reports what it shows as a
typed event, whichever of the visitor and Javier moved it.

This is a port of the Santander Arena guide (``demos/santanderarena``), with
Clini's later machinery: nods measured to be his voice, a floor that is never
ten seconds of silence, moves the page confirms and he then talks through, one
move at a time. What differs is the site, and what is read live.

**A guide, not a brochure.** Every turn answers what was asked, in words, and
moves the visitor on along the way a student decides: an area, a career, what
it is like, what it asks for, what it costs and how to pay for it, the campus,
and how to get in touch.

**Every figure is read live, in the visitor's browser.** This brain runs far
from Chile and never fetches uahurtado.cl. A fee, a PAES weight, a minimum
score or a postgraduate deadline is read off the page in front by the
extension and comes back as an event; the knowledge carries none of them. He
says a figure only once the page has reported it, and if the read fails he says
he cannot see it right now and shows where it is.

**The arithmetic is done here, not by the model.** A weighted PAES score is
worked out from the career's own weights and the visitor's spoken scores
(:mod:`.admission`), and handed to the model with the words to say it.

**Forms are filled, never sent.** He types what the visitor dictates into the
site's own lead form, never a RUT, and never presses "Enviar": the visitor
reviews it and sends it themselves. Visit sign-ups are Google and HubSpot forms
he only points at. The PAES simulator is a lead form too: he opens it for them
and fills nothing.

**The screen follows his voice.** He writes his moves into the reply as cues
(``{show: Requisitos y Aranceles}``), at the start of the sentence they belong
to; the brain takes them out of the speech, checks them against the sites, and
the page fires each as the voice reaches its sentence (:mod:`.cues`). Every move
to another page is a full load, often to another host, so the extension carries
the cues still owed across the load and the call rejoins on the next page.

**Spanish or English, as the visitor chose or speaks.** The call opens in
neutral Latin American Spanish; it follows a visitor who speaks English, and a
language chosen on the widget's toggle (or asked for) holds whatever they speak.
The voice is one man, recorded in each.
"""

from __future__ import annotations

import asyncio
import dataclasses
import inspect
import math
import random
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
from .admission import (
    Fees,
    Scores,
    Weights,
    date_said,
    dates_in,
    describe_estimate,
    describe_fees,
    describe_weights,
    estimate,
    money_for_the_voice,
    money_items,
    number_es,
    parse_fees,
    parse_weights,
    pesos_en,
    pesos_es,
)
from .cues import CueKind, CueParser, RawCue, words
from .knowledge import (
    ADMISION,
    TOPIC_IDS,
    Career,
    Knowledge,
    Page,
    Program,
    fold,
    is_link_url,
    norm,
    page_key,
    page_url,
    short,
)
from .protocol import (
    UAH_EVENTS,
    AdmissionRead,
    AudiomallaEnded,
    CareerSheet,
    CommandDone,
    CommandFailed,
    Cue,
    FillLeadForm,
    FocusTab,
    LanguageChanged,
    LanguageRequested,
    LeadFormState,
    LeadSubmitted,
    OpenCareerMenu,
    OpenLink,
    PageChanged,
    PlayAudiomalla,
    ProgramRead,
    ProgramSheet,
    ShowAdmission,
    ShowProgram,
    ShowSignup,
    TabInfo,
    TabsChanged,
    UahEvent,
)

AGENT_NAME = "Javier"

#: LOW, as SendPotion measured: at MINIMAL, Gemini mostly made the page call
#: first and wrote nothing; at LOW it writes the answer first and calls at the
#: end, so the page moves while he is still talking.
THINKING = types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)
#: Every sibling's model: 3.8 had the first words out in about two seconds
#: where 3.5 spiked to seven (dev call 67d16b5d).
MODEL = "gemini-3.8-flash"

#: Santiago, for "today" and for dates read off the site.
TIMEZONE = ZoneInfo("America/Santiago")

# ─── Voice and timing ──────────────────────────────────────────────────────────

#: Javier's voice: the speech tier's male persona recorded once in English and
#: once in Spanish, so a switch keeps the same man.
VOICE = Voice.OMNIVOICE_JAVIER

#: A quiet visitor is someone reading a page; a guide beside them says
#: something after a while, and not twice more.
_IDLE_MS = 20_000
_IDLE_NUDGES = 2
#: The idle window while something the page answered is owed: a visitor who
#: reacts speaks first, one who is reading hears it from him.
_TALK_THROUGH_MS = 2_000
#: More patience than the demos' default: a student reading out their scores
#: pauses between them.
UAH_PATIENCE = PATIENCE + 2
#: A message this soon after the last one is the rest of the same thought.
_FRAGMENT_S = 4.0

# ─── Language ──────────────────────────────────────────────────────────────────

Lang = Literal["en", "es"]
#: The sites are Chilean and in Spanish, and so are most of their visitors.
OPENING: Lang = "es"
LANGUAGE_NAMES: dict[Lang, str] = {"en": "English", "es": "Spanish"}

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
    su sus nosotros bueno claro dónde donde cuál cual cuándo cuando carrera carreras
    estudiar estudio postular puntaje beca becas muéstrame dime explícame hace hacer
    saqué tengo quiénes quién próximo próximos universidad
    """.split()  # noqa: SIM905
)
_ENGLISH_WORDS = frozenset(
    """the is are was what how can could you your i i'm it it's this that these those do
    does show me my we our for with about and of to have has there here please want
    would like tell sure yes okay right of course let's study degree
    """.split()  # noqa: SIM905
)
_WRITTEN_ENOUGH = 60
_SENTENCE_END = re.compile(r"[.?!](?:\s|$)")
_SPANISH_MARKS = re.compile(r"[¿¡ñáéíóú]", re.IGNORECASE)
_LETTERS = re.compile(r"[\wáéíóúüñ']+")
#: A cue is the site's own words, in Spanish whatever he speaks.
_CUE_TEXT = re.compile(r"\{[^{}]*\}?")
#: Career and place names are the site's Spanish inside any reply: "Psicología
#: at the Casa Central" is an English sentence.
_NAMES_IN_ENGLISH = re.compile(
    r"\b(?:Universidad Alberto Hurtado|Casa Central|Admisión Directa|Becas y Beneficios|"
    r"Requisitos y Aranceles|Ven y Conócenos)\b",
    re.IGNORECASE,
)


def language_of(text: str, *, sure: bool = True) -> Lang | None:
    """The language ``text`` is plainly in, or ``None``.

    ``sure`` is for what the visitor said, where one stray word must not move
    the call: Spanish needs two of its words (or its marks and one), English
    three of its own and none of Spanish's. Unsure is for the first words of his
    own reply, which are few: one Spanish word, or two English ones, will do.
    Cues and the site's own names are taken out first."""
    text = _NAMES_IN_ENGLISH.sub(" ", _CUE_TEXT.sub(" ", text))
    found = set(_LETTERS.findall(text.lower()))
    es = len(found & _SPANISH_WORDS) + (1 if _SPANISH_MARKS.search(text) else 0)
    en = len(found & _ENGLISH_WORDS)
    if es >= (2 if sure else 1) and es > en:
        return "es"
    if en >= (3 if sure else 2) and es == 0:
        return "en"
    return None


#: Latin America says "vi-DE-o"; Spain says "VÍ-deo", and the Spanish voice read
#: plain "video" Spain's way in one sentence of three on Clini's dev calls.
#: Spelled "bidéo" it said "vi-DE-o" every take. So in Spanish the voice is
#: handed "bidéo" — the voice only: the page's word anchors follow the same
#: spelling (``_anchor_for_voice``), and what comes back as heard is spelled
#: "video" again before it reaches the model (``on_finalize``).
_VIDEO_TO_VOICE = re.compile(r"\b([Vv])[ií]deo(s?)\b")
_VIDEO_FROM_VOICE = re.compile(r"\b([Bb])idéo(s?)\b")
_VIDEO_AS_WORDS = re.compile(r"\bv deo(s?)\b")
#: The UF is "u efe" in Chile; a voice handed "UF" may say "uf". Respelled for
#: the Spanish voice only, and undone in what comes back as heard.
_UF_TO_VOICE = re.compile(r"\bUF\b")
_UF_FROM_VOICE = re.compile(r"\bu efe\b", re.IGNORECASE)
_UF_AS_WORDS = re.compile(r"\buf\b")
_UF_COUNT_AS_WORDS = re.compile(r"\b(\d+) uf\b")
#: Names the site writes in capitals, which a voice may spell letter by letter:
#: handed as words. Tuned on dev by ear, never in a test; "UAH" is spelled out
#: on purpose ("la U A H"), as Chileans say it, and so is left alone.
_CAPS_TO_VOICE = ((re.compile(r"\bPAES\b"), "Paes"), (re.compile(r"\bUBICACIÓN\b"), "Ubicación"))


def names_for_the_voice(text: str) -> str:
    for rx, word in _CAPS_TO_VOICE:
        text = rx.sub(word, text)
    return text


def for_the_voice(text: str) -> str:
    """Spanish ``text`` as the voice must read it: "video" as "bidéo", amounts
    and UF in words, the site's capitals as words."""
    text = money_for_the_voice(names_for_the_voice(text), "es")
    text = _UF_TO_VOICE.sub("u efe", text)
    return _VIDEO_TO_VOICE.sub(
        lambda m: ("B" if m.group(1) == "V" else "b") + "idéo" + m.group(2), text
    )


def for_the_voice_en(text: str) -> str:
    """English ``text`` as the voice must read it: amounts in words."""
    return money_for_the_voice(names_for_the_voice(text), "en")


def from_the_voice(text: str) -> str:
    """What the voice said, spelled as Latin America writes it."""
    text = _UF_FROM_VOICE.sub("UF", text)
    return _VIDEO_FROM_VOICE.sub(
        lambda m: ("V" if m.group(1) == "B" else "v") + "ideo" + m.group(2), text
    )


def _anchor_for_voice(at: str) -> str:
    """A cue's anchor, in the page's words, for speech spelled :func:`for_the_voice`."""
    at = _VIDEO_AS_WORDS.sub(r"video\1", at)
    # A UF count as the voice says it ("11 uf" is "once u efe"); the anchor's
    # words are already folded, so the amount's "UF" is lower case here.
    at = _UF_COUNT_AS_WORDS.sub(lambda m: f"{number_es(int(m.group(1)))} u efe", at)
    at = _UF_AS_WORDS.sub("u efe", at)
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
        description="A few words to look for on the university's sites, in Spanish or "
        "English, e.g. 'gratuidad', 'deportista destacado', 'intercambio', 'biblioteca'."
    )


class CareersRequest(BaseModel):
    query: str = Field(
        description="What the visitor wants to study, in their words: a career, an area, a "
        "faculty or a kind of work, e.g. 'ingeniería', 'psicología', 'trabajar con niños', "
        "'online', 'vespertino'."
    )


class ProgramsRequest(BaseModel):
    query: str = Field(
        description="The postgraduate subject, in their words, e.g. 'psicología', 'derecho "
        "penal', 'educación', 'MBA'."
    )
    type: Literal["magister", "doctorado", "diplomado", "postitulo", "curso", "any"] = Field(
        default="any", description="The kind of programme, if they said one."
    )
    modalidad: Literal["online", "presencial", "hibrida", "any"] = Field(
        default="any", description="How it is taught, if they said."
    )


class FacultyRequest(BaseModel):
    faculty: str | None = Field(
        default=None,
        description="The faculty or area whose careers to ring in the menu, as the careers "
        "list names it, e.g. 'Facultad de Ingeniería'. Empty for the whole menu.",
    )


class CareerRequest(BaseModel):
    career: str | None = Field(
        default=None,
        description="The career, by its name as the careers list writes it. Empty for the "
        "career page in front.",
    )


class ScoreRequest(BaseModel):
    career: str | None = Field(
        default=None,
        description="The career, by its name as the careers list writes it. Empty for the "
        "career page in front.",
    )
    nem: int | None = Field(default=None, description="Puntaje NEM in points, 100 to 1000.")
    ranking: int | None = Field(default=None, description="Puntaje Ranking in points, 100 to 1000.")
    lectora: int | None = Field(default=None, description="Competencia Lectora, PAES points.")
    matematica: int | None = Field(
        default=None, description="Competencia Matemática 1 (M1), PAES points."
    )
    historia: int | None = Field(
        default=None, description="Historia y Ciencias Sociales, PAES points."
    )
    ciencias: int | None = Field(default=None, description="Ciencias, PAES points.")
    m2: int | None = Field(default=None, description="Competencia Matemática 2 (M2), PAES points.")


class ProgramRequest(BaseModel):
    program: str | None = Field(
        default=None,
        description="The programme, by its name as find_programs gave it. Empty for the "
        "programme page in front.",
    )


class LeadRequest(BaseModel):
    nombre: str | None = Field(
        default=None, description="Their first name, exactly as they said it."
    )
    apellido: str | None = Field(default=None, description="Their surname, as they said it.")
    email: str | None = Field(
        default=None, description="Their email, exactly as they spelled it, never changed."
    )
    fono: str | None = Field(
        default=None,
        description="Their phone number, exactly the digits they said, never changed or completed.",
    )
    consulta: str | None = Field(
        default=None,
        description="Their question for admissions, which you write in Spanish in one "
        "sentence from the conversation, e.g. 'Consulta por arancel 2027 y becas de "
        "Psicología'.",
    )
    carrera: str | None = Field(
        default=None,
        description="Only where the form has a career list: the career, as the list writes it.",
    )
    via: str | None = Field(
        default=None,
        description="Only on Admisión Directa: the vía de admisión, as its list writes it.",
    )
    focus_rut: bool = Field(
        default=False,
        description="True to ring the RUT field for them to type. You never fill a RUT.",
    )


class VisitRequest(BaseModel):
    visit: str = Field(description="The visit or workshop, by its title as the screen lists it.")


class LinkRequest(BaseModel):
    kind: Literal["simulador", "malla"] = Field(
        description="'simulador' for the PAES score simulator; 'malla' for the career's "
        "malla curricular PDF."
    )


class TabRequest(BaseModel):
    tab_id: str = Field(description="The tab_id from the open tabs list.")


class LanguageRequest(BaseModel):
    language: Lang = Field(description="'en' for English, 'es' for Spanish.")


# ─── The prompt ────────────────────────────────────────────────────────────────

_SITE_MAP_CHARS = 14000
_SECTIONS_PER_PAGE = 12
_CARDS_PER_PAGE = 10
_PROGRAMS_IN_PROMPT = 90
_TITLE_SUFFIXES = (
    " | Admisión UAH",
    " - Admisión UAH",
    " | Universidad Alberto Hurtado",
    " - Universidad Alberto Hurtado",
    " | Postgrados UAH",
    " - Postgrados UAH",
    " | UAH",
    " - UAH",
)
SIMULADOR = "https://simula.uahurtado.cl/"


def _short_title(title: str) -> str:
    for suffix in _TITLE_SUFFIXES:
        title = title.removesuffix(suffix)
    return title.strip()


def _site_map(k: Knowledge) -> str:
    """Every page but the careers' and programmes' own (listed apart), with its
    headings and cards."""
    lines: list[str] = []
    size = 0
    own = {c.key for c in k.careers.values()} | {p.key for p in k.programs.values()}
    skip = ("news", "post", "carrera", "programa", "career", "program", "template")
    pages = [p for p in k.pages.values() if p.key not in own and p.kind not in skip]
    for p in sorted(pages, key=lambda p: (kb.host_of(p.key) != ADMISION, p.key.count("/"), p.key)):
        heads = "; ".join(p.headings[:_SECTIONS_PER_PAGE])
        cards = "; ".join(dict.fromkeys(c.title for c in p.cards[:_CARDS_PER_PAGE]))
        line = f"- {short(p.key)} — {_short_title(p.title)}"
        line += f" (sections: {heads})" if heads else ""
        line += f" (tabs: {'; '.join(p.toggles[:_SECTIONS_PER_PAGE])})" if p.toggles else ""
        line += f" (cards: {cards})" if cards else ""
        size += len(line) + 1
        if size > _SITE_MAP_CHARS:
            break
        lines.append(line)
    return "\n".join(lines) or "(The site map is not loaded: find pages with search_site.)"


def _careers_list(k: Knowledge) -> str:
    out: list[str] = []
    for faculty, careers in k.faculties().items():
        names = "; ".join(f"{c.name} ({short(c.key)})" for c in careers)
        out.append(f"- {faculty}: {names}")
    return "\n".join(out) or "(No careers loaded: use find_careers.)"


def _programs_list(k: Knowledge) -> str:
    by_type: dict[str, list[str]] = {}
    for p in list(k.programs.values())[:_PROGRAMS_IN_PROMPT]:
        by_type.setdefault(p.type or "programa", []).append(p.name)
    lines = [f"- {t}: {'; '.join(names)}" for t, names in by_type.items()]
    return "\n".join(lines) or "(No programmes loaded: use find_programs.)"


def _topics(k: Knowledge) -> str:
    return "\n".join(f"- {t.id}: {t.title}" for t in k.topics.values()) or "(none loaded)"


def _prompt(k: Knowledge, today: date | None = None) -> str:
    today = today or datetime.now(TIMEZONE).date()
    return f"""You are {AGENT_NAME}, a guide for prospective students of Universidad Alberto Hurtado (UAH), a Jesuit university in Santiago, Chile. A visitor is on the university's sites right now — admision.uahurtado.cl for undergraduate admission, postgrados.uahurtado.cl and www.uahurtado.cl — and has called you from the corner of the page. You can see and move their screen: you open pages, open the Carreras menu, switch a career page's tabs, open accordions and FAQs, ring the exact section that answers them, read the career's fees and PAES weights off the page, fill the contact form as they dictate it, and open the PAES simulator in a new tab. You are warm, calm and clear — an older student who knows the university well and wants this visitor to decide well, with no pressure. Choosing a career should feel clearer after talking to you.

# You narrate, and the screen follows your words
You are giving a guided walkthrough, like someone sitting beside the visitor with their screen in front of you both. As you talk about something, it is on their screen, ringed, at that moment.
- Put a screen cue in your reply at the start of the sentence it belongs to. The page moves when your voice reaches that sentence. The visitor never hears a cue.
  - {{page: /path/}} opens a page of admision.uahurtado.cl at its top; a page on the other two sites is written with its host, as the lists below write it: {{page: www.uahurtado.cl/la-universidad/campus/campus-patrimonial/}}, {{page: postgrados.uahurtado.cl/programa/magister-intervencion-psicosocial/}}.
  - {{show: Heading}} scrolls to a heading and rings it. With a tab, pill or accordion label ("Requisitos y Aranceles", "Descripción", "Excelencia académica", "Requisitos y Valores") it opens it first. With a card's title or other words on the page it rings those.
  - {{faq: Question}} opens that FAQ and rings it.
- Use headings, tabs and names exactly as the lists or the screen lines spell them. The site is in Spanish, so cues are in Spanish, also inside an English reply: "{{page: /carreras/psicologia/}} Psicología takes five years."
- Never make up a heading or a path. One cue per sentence at most, before the sentence, never inside it.
- When the visitor asks where something is ("muéstrame", "show me"), your reply starts with the cue for exactly that thing.
- After a page cue, every sentence about a part of that page brings its own show cue.
- EVERY ANSWER ABOUT THE UNIVERSITY STARTS WITH A CUE, when what you talk about is on a page in the lists below. When the visitor names a career, open that career's own page.
- Cues are the only way you move between pages and sections. The tools below do the rest: the menu, fees, the form, the audio.
- Example, for "¿Qué es Psicología?": "{{page: /carreras/psicologia/}} Te abro la carrera. Psicología dura diez semestres. {{show: Descripción}} Forma psicólogos con mirada social y ética. ¿Te muestro qué piden para entrar?"

# A good turn helps them decide
1. Answer what they asked, first, in plain words, and show it as you say it.
2. Say why it matters for them, in a sentence, when you know something about them: what they like, their scores, where they live.
3. End with one short, specific yes-or-no offer that leads to the next step: "¿Te muestro los requisitos?", "¿Quieres saber cuánto cuesta?", "Shall I check whether your scores are enough?". Never an open question, and never "anything else?".
- A student's decision has an order. Follow it from wherever they are: an area or faculty, then a career, then what it is like (its page, its description, the audiomalla), then what it asks for (the PAES weights and minimums, and whether their scores are enough), then what it costs, then becas and gratuidad, then the campus and a visit, then the contact form so admissions can follow up.
- Ask about them only when the answer changes what you show next, and offer the choices: "¿Te interesa más la ingeniería o las ciencias sociales?"

# How you sound
You are heard, not read, so keep it light and warm.
- A turn is three to five short sentences; a walkthrough of a page can run to eight, one item per sentence, each with its cue.
- Every sentence under fifteen words. Small, everyday words. One idea per sentence. One number per sentence.
- THE FIRST SENTENCE IS A FEW WORDS: two to six words that end in a full stop, with the answer in it. A cue may come before it.
- Before most replies the visitor has already heard a short acknowledgement of mine — "Claro.", "A ver.", or in English "Happy to help.", "Let me see." — so never open with one: your first word is the answer. No "great question", no repeating their question back.
- Spoken words only, apart from cues: no lists, no markdown, no symbols, never an exclamation mark. Write numbers, dates and money as spoken words: "diez semestres", "el catorce de noviembre", "doscientos setenta y siete mil cuatrocientos cincuenta y seis pesos". When a note gives you the words for a figure ("say …"), say exactly those words.
- Lines in square brackets come from their screen or from the page, not the visitor. Never read them out; use them.
- Always answer. A reply with no words leaves the visitor in silence.

# Spanish or English
You speak Spanish as a native of Latin America, and English. The call starts in Spanish unless the visitor chose English.
- Answer in the language the visitor speaks to you. If they speak English, answer in English from that reply on; if they go back to Spanish, so do you. Your voice follows the language you write.
- Except when they chose a language: a line in square brackets says so. Then answer in that language whatever they speak, until they ask you to switch.
- When they ask for the other language in words that are not already it ("¿Puedes hablar en inglés?", "Can we speak Spanish?"), answer in that language and call set_language in the same response. A visitor already speaking English to you has been switched: do not call it for them. "¿La carrera se dicta en inglés?" is a question about a career, not about this call.
- One language per reply: in a Spanish reply every sentence is Spanish, and masculine forms of yourself ("encantado de ayudarte").
- Your Spanish is neutral Latin American Spanish, warm and natural for a Chilean visitor, never the Spanish of Spain and never heavy slang or chilenismos.
  - Address the visitor as "tú", never "usted"; several people are "ustedes", never "vosotros", never its verb forms ("queréis", "tenéis", "podéis") or "os".
  - Use Latin American words: "celular", never "móvil"; "computadora", never "ordenador"; "mostrar" ("te muestro"), not "enseñar"; "completar un formulario", not "rellenar"; "¿Qué día te queda bien?", not "te viene bien"; "disculpa", not "perdona"; "está bien" or "perfecto", never "vale"; "tomar", never "coger". Write "video", never "vídeo".
  - The university's own words: "carrera", "malla curricular", "postular", "PAES", "puntaje ponderado", "matrícula", "arancel", "beca", "gratuidad", "sede", "jornada diurna" or "vespertina".
  - For something just done, use the simple past: "Abrí la página", not "He abierto".
- In English, say the site's Spanish names as they are written ("Psicología", "Becas y Beneficios", "Requisitos y Aranceles") and explain them in a few words.

# Every response starts with words
Write your answer, with its cues, first; any tool call comes at the end of the same response. What a page move returns reaches you as a note in brackets, and you talk it through then.
- The exception is a read: read_topic, search_site, find_careers, find_programs, read_fees, estimate_score and read_program come straight back to you within this same turn, but each one makes the visitor wait. Answer from what you know below whenever it covers the question. Read only for what is not here, and then call the read first, with nothing written before it.
- Never promise more to come ("let me check", "un momento"): nothing comes after it, and a reply that is only a promise leaves the visitor in silence.
- Questions about the call itself ("can you hear me?", "can we speak English?") get an answer and nothing else: no page, no tool but set_language.

# Careers
- Every career is in the careers list below, by faculty, with its page. For "what careers are there in engineering" open the Carreras menu at that faculty with show_careers and name a few of its careers as it opens, then ask which one interests them. For a career they name, open its page with a page cue.
- On a career page the screen line lists its tabs and its Datos Académicos (modalidad, título, sede, régimen, duración). Talk from those, and open a tab with a show cue as you talk about it.
- Many careers have an audiomalla: the career's director talking about it. Offer it ("¿Quieres escuchar a la directora contar la carrera?"); when they say yes, say one short sentence that the audio starts, then call play_audiomalla, and say nothing more until it ends.
- find_careers finds careers by what the visitor wants to study, in their words.

# Fees, PAES weights and whether their score is enough
- Fees, PAES weights, minimum scores and dates change every year, so they are not in what you know: they are read live off the career's page. Never say a figure that a note or a read did not just give you, and never one from memory.
- For what a career costs, call read_fees with the career. It opens the career's "Requisitos y Aranceles" tab on their screen and reads the fees there. Say the year the page gives ("para el año dos mil veintisiete"). If it could not read them, say you cannot see the fees right now and that they are in that tab.
- The /aranceles/ page shows last year's table: never quote it.
- For "¿me alcanza?", "is my score enough?": ask for their PAES scores (Competencia Lectora, Matemática, Historia or Ciencias, and M2 if the career weighs it) and their NEM and Ranking scores in points, as their DEMRE results write them. A grade average like "seis coma dos" is not a score: ask for the puntaje NEM. Then call estimate_score with every score they gave. Never add up a weighted score yourself: the tool does the arithmetic with the career's own weights, and you say its result with the words it gives you.
- Always call it an estimate. The official figure is DEMRE's, and the university's PAES simulator (simula.uahurtado.cl) gives one too: offer to open it with open_link. The simulator asks for their details; they fill it in themselves, never you.

# Becas and gratuidad
- /becas-y-beneficios/ groups the becas in tabs (Excelencia académica, Matrícula, Arancel, Descuentos, Mantención, Servicios de apoyo, Otros): open the right one with a show cue as you talk about it.
- /gratuidad-universitaria/ answers gratuidad in FAQs: open the one that answers them with a faq cue.
- Never promise a beca, gratuidad, a discount or admission: say what the page says it requires, and point to the official channel.

# Campus and visits
- The Casa Central and the campus addresses are on www.uahurtado.cl/la-universidad/campus/campus-patrimonial/, under UBICACIÓN, with a map. Show them there.
- Visits and workshops are on /ven-y-conocenos/. The screen line lists each card, with the ones already held marked as past: never offer a past one. To sign up, ring its "Inscribirse aquí" with show_signup and say they sign up there themselves. Never open or fill a sign-up form.

# The contact form
- Most admision pages have the form "Solicita información" (on a career page, at its top, already for that career). When the visitor wants admissions to contact them, fill it as they dictate with fill_lead_form: nombre, apellido, email, fono and a short consulta you write from the conversation. Fill what they said as soon as they say it, then read back the email letter by letter and the phone digit by digit.
- Never ask for, say, repeat or type their RUT: it is theirs to type, in the field you ring for them (focus_rut).
- Never send it. When it is complete, ask them to review it and press "Enviar" themselves.
- Never ask for data the form does not ask for.

# Postgrado
- Postgraduate programmes (magíster, doctorados, diplomados, postítulos) are on postgrados.uahurtado.cl. find_programs finds one by subject, type and modality; open its page with a page cue.
- For a programme's fees, early-enrolment discount, application window or start date, call read_program: it opens "Requisitos y Valores" on their screen and reads them. The same rule as fees: only figures it just gave you.

# Tabs
- The visitor may have several UAH tabs open. Lines in brackets tell you which tabs are open and which is in front. Your moves happen on the tab in front. "Go back to the other tab" is switch_tab with that tab's id.

# What you know
- Today is {today:%A, %d %B %Y}, in Santiago.
- Every fact comes from the knowledge below, a topic you read, a search result, or what the screen reported. Never from memory. If you cannot find it, say so and say where on the site it might be, or offer the contact form. Where pages of the site disagree, say which page says what.
- Topics you can read with read_topic, when the knowledge below does not cover a question:
{_topics(k)}
- search_site finds a page, section, card or FAQ by its words; its results name the page and section, which you can then cue.

# Universidad Alberto Hurtado
{k.l1}

# Careers (by faculty; each with its page)
{_careers_list(k)}

# Postgraduate programmes (by type; find_programs gives each one's page)
{_programs_list(k)}

# Site pages
{_site_map(k)}
"""


# ─── Greeting ──────────────────────────────────────────────────────────────────

_INTRO: dict[Lang, str] = {
    "en": f"Hi, I'm {AGENT_NAME}, your guide to the Universidad Alberto Hurtado.",
    "es": f"Hola, soy {AGENT_NAME}, tu guía de la Universidad Alberto Hurtado.",
}
_GREETING: dict[Lang, str] = {
    "en": "I can help you find a career, see what it asks for and what it costs, or plan a "
    "visit. What would you like to study?",
    "es": "Te ayudo a encontrar una carrera, ver qué pide y cuánto cuesta, o a planear una "
    "visita. ¿Qué te gustaría estudiar?",
}
#: The opener's second sentence for the page the call starts on, by a word in
#: its key; the first match wins, and anything else gets the plain greeting.
#: Neutral: a greeting never assumes a step the visitor has not taken (Clini's
#: dev call 03a45037 opened a form with "¿Qué día te queda bien?").
_OPENERS: tuple[tuple[str, dict[Lang, str]], ...] = (
    (
        "postgrados.",
        {
            "en": "I can help you find a postgraduate programme. What area are you interested in?",
            "es": "Te ayudo a encontrar un postgrado. ¿Qué área te interesa?",
        },
    ),
    (
        "/becas",
        {
            "en": "I can walk you through the becas and benefits. What would you like to know?",
            "es": "Te explico las becas y beneficios. ¿Qué te gustaría saber?",
        },
    ),
    (
        "/gratuidad",
        {
            "en": "I can tell you how gratuidad works here. What's your question?",
            "es": "Te cuento cómo funciona la gratuidad aquí. ¿Cuál es tu duda?",
        },
    ),
    (
        "/ven-y-conocenos",
        {
            "en": "I can tell you about the visits and workshops coming up. Want to hear them?",
            "es": "Te cuento las visitas y talleres que vienen. ¿Quieres conocerlos?",
        },
    ),
    (
        "/campus",
        {
            "en": "I can show you where the campus is and how to get there. Shall I?",
            "es": "Te muestro dónde está el campus y cómo llegar. ¿Te parece?",
        },
    ),
    (
        "/admision-directa",
        {
            "en": "I can explain Admisión Directa and who it is for. Shall I?",
            "es": "Te explico la Admisión Directa y para quién es. ¿Te parece?",
        },
    ),
)
_CAREER_GREETING: dict[Lang, str] = {
    "en": "Shall I tell you about {name}, or help you with something else?",
    "es": "¿Te cuento sobre {name}, o te ayudo con otra cosa?",
}


def greeting(url: str | None, lang: Lang = OPENING, k: Knowledge | None = None) -> str:
    """The written opener, in ``lang``, tailored to the page the call starts on."""
    key = page_key(url or "/") or f"{ADMISION}/"
    career = (k or kb.KNOWLEDGE).career_at(page_url(key))
    if career is not None:
        return f"{_INTRO[lang]} {_CAREER_GREETING[lang].format(name=career.name)}"
    line = next((lines[lang] for word, lines in _OPENERS if word in key), _GREETING[lang])
    return f"{_INTRO[lang]} {line}"


# ─── Written lines for moves ───────────────────────────────────────────────────

#: His line for a turn that moved the page and said nothing. A move the page
#: answers later says what he is doing, never that it is done (Clini b349add).
_LANDED: dict[str, dict[Lang, str]] = {
    "shown": {"en": "Here it is.", "es": "Aquí lo tienes."},
    "tab": {"en": "There's that tab.", "es": "Ahí tienes esa pestaña."},
    "menu": {
        "en": "I'm opening the careers menu for you.",
        "es": "Te abro el menú de carreras.",
    },
    "fees": {
        "en": "I'm opening the fees on the career's page.",
        "es": "Te abro los aranceles en la página de la carrera.",
    },
    "requirements": {
        "en": "I'm opening what the career asks for.",
        "es": "Te abro los requisitos de la carrera.",
    },
    "program": {
        "en": "I'm opening the programme's requirements and fees.",
        "es": "Te abro los requisitos y valores del programa.",
    },
    "form": {
        "en": "I'm filling in the form with what you told me.",
        "es": "Te completo el formulario con lo que me dijiste.",
    },
    "signup": {
        "en": "Here is where you sign up.",
        "es": "Aquí te puedes inscribir.",
    },
    "audio": {
        "en": "Here's the audio, listen.",
        "es": "Te pongo el audio, escucha.",
    },
    "link": {
        "en": "I've opened it in a new tab.",
        "es": "Te lo abrí en una pestaña nueva.",
    },
    "queued": {
        "en": "I'll do that as soon as the page is ready.",
        "es": "Lo hago apenas la página esté lista.",
    },
}

# ─── His nod ───────────────────────────────────────────────────────────────────

#: Only lines measured to come out in Javier's own voice: each line is voiced
#: on its own and always the same way, and "Right.", "One moment." or "Un
#: momento." came out as somebody else (82 Hz and 166 Hz against his 110-132).
#: Explora's measured set (speaker embedding and pitch, fd30c1c), as every
#: sibling uses it. It holds for this bake of omnivoice/javier: measure a new
#: line before adding it.
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
#: Santander Arena's: every page here is a full load, often to another host,
#: and the nod is what the visitor hears while the next page comes in.
ACK_RATE = 0.9
#: After a nod, how long the model may stay quiet before he holds the floor
#: (Clini, dev call 2fd742d5: at 4 s nearly every lookup turn said "Just a moment.").
ACK_HOLD_AFTER_S = 5.75
#: With no nod, the dead air a turn may leave before his first line.
HOLD_WITHOUT_NOD_S = 2.5
ACK_SORRY_AFTER_S = 15.0
_ACK_HOLD: dict[Lang, tuple[str, ...]] = {
    "en": ("Just a moment.", "One moment while I check that for you."),
    "es": ("Dame un momento mientras lo busco.", "Un momento mientras lo reviso para ti."),
}
_ACK_SORRY: dict[Lang, str] = {
    "en": "Sorry, that's taking a little longer.",
    "es": "Lo siento, está tardando un poco más de lo normal.",
}
#: A visitor's ordinary words about the university, so the reading trusts them.
_ACK_WORDS = Vocabulary(
    common=frozenset(
        # A word list reads as words, so it stays a split string.
        """uah universidad hurtado carrera carreras estudiar postular postulación admisión
        directa paes puntaje puntajes ponderado ponderación nem ranking lectora matemática
        historia ciencias m1 m2 demre simulador malla audiomalla semestres arancel aranceles
        matrícula titulación uf beca becas beneficio beneficios gratuidad fuas cae crédito
        descuento campus sede casa central metro héroes visita visitas taller talleres
        facultad ingeniería psicología derecho periodismo pedagogía educación sociología
        antropología historia filosofía comercial informática trabajo social postgrado
        postgrados magíster doctorado diplomado online vespertino diurno formulario
        career careers degree tuition fee fees scholarship scholarships score scores
        campus visit master phd
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
_TOGGLES_IN_NOTE = 30
_CARDS_IN_NOTE = 30
_FAQS_IN_NOTE = 40
_SEARCH_HITS = 6
_CAREER_HITS = 6
_PROGRAM_HITS = 6
_TEXT_IN_NOTE = 1400


async def _silence() -> AsyncGenerator[Any, None]:
    for _ in ():
        yield


def _clip(items: list[str] | tuple[str, ...], most: int) -> str:
    more = f"; and {len(items) - most} more" if len(items) > most else ""
    return "; ".join(items[:most]) + more


def _match(want: str, options: list[str] | tuple[str, ...]) -> str | None:
    """The option ``want`` names: the same words, else the one it begins, else
    the one it is inside — how the page itself matches. Case, accents and
    punctuation do not count: "requisitos y aranceles" is "Requisitos y Aranceles"."""

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
#: it. Matched on their own words, English or Spanish, folded; a career or
#: programme they name beats these, and among these the first named wins. A
#: page the crawl does not have is skipped where it is used.
_ASKED_PAGES: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(rf"\b(?:{w})", re.IGNORECASE), path)
    for w, path in (
        (r"gratuidad|free tuition|tuition[- ]free", "/gratuidad-universitaria/"),
        (r"becas?\b|beneficios|scholarships?|financial aid", "/becas-y-beneficios/"),
        (r"admision directa|direct admission", "/admision-directa/"),
        (r"vias? de admision|admission routes|ways to (?:apply|get in)", "/vias-de-admision/"),
        (r"ranking 1000", "/ranking-1000/"),
        (r"deportista", "/deportista-destacado/"),
        (r"red internacional|intercambio|exchange", "/red-internacional/"),
        (r"continuidad de estudios|continuidad\b", "/continuidad-de-estudios/"),
        (r"audiomallas", "/audiomallas/"),
        (
            r"visitas?\b|visitar|conocer la (?:u|universidad)|ven y conocenos|open day|"
            r"talleres?\b|workshops?|tours?\b",
            "/ven-y-conocenos/",
        ),
        (
            r"campus|donde (?:queda|esta) la (?:u|universidad)|ubicacion|direccion|address|"
            r"where is (?:it|the university|the campus)|como llego|how do i get there",
            "www.uahurtado.cl/la-universidad/campus/campus-patrimonial/",
        ),
        (
            r"postgrados?|posgrados?|magister|masters?\b|doctorad|phd|diplomados?|postitulos?",
            "postgrados.uahurtado.cl/",
        ),
    )
)
_ASKED_TAB = re.compile(r"\b(?:tabs?|pestanas?)\b", re.IGNORECASE)
_POSTGRADO = re.compile(
    r"\b(?:postgrados?|posgrados?|magister|masters?|mba|doctorados?|phd|diplomados?|"
    r"postitulos?)\b",
    re.IGNORECASE,
)
#: A question for a figure is answered by a read that opens its own page and
#: tab: a page cue in the same breath would load the page under it.
_ASKS_FIGURES = re.compile(
    r"\b(?:cuanto cuesta|cuanto vale|cuanto sale|precio|costo|arancel|aranceles|matricula|"
    r"cost|costs|fees?|tuition|price|me alcanza|alcanza|puntaje|ponderad|minimo|weights?|"
    r"scores?|enough|requisitos y valores|plazo|postulacion hasta|deadline)\b",
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
#: "¿La carrera se dicta en inglés?" is a question about a career.
_ABOUT_A_COURSE = re.compile(
    r"\b(?:carrera|clases?|programa|magister|se dicta|dictan|imparte|taught|courses?|"
    r"classes|degree)\b",
    re.IGNORECASE,
)
_ABOUT_THE_CALL = re.compile(
    r"\b(?:can you hear me|are you there|me escuchas|me oyes|who are you|quien eres"
    r"|are you (?:a )?(?:bot|robot|real|human|ai)|eres (?:un )?(?:bot|robot|humano))\b",
    re.IGNORECASE,
)


def asks_call_language(text: str) -> bool:
    """Whether ``text`` asks him to speak another language — a request about
    this call, not a question about a career taught in English."""
    if _ABOUT_A_COURSE.search(fold(text)):
        return False
    return bool(_CALL_LANGUAGE.search(text) and _TO_HIM.search(text))


def about_the_call(text: str) -> bool:
    """Whether ``text`` is only about the call: its language, or him."""
    short_words = len(text.split()) <= 12
    return short_words and (asks_call_language(text) or bool(_ABOUT_THE_CALL.search(fold(text))))


def asks_figures(text: str) -> bool:
    return bool(_ASKS_FIGURES.search(fold(text)))


def asked_page(text: str, k: Knowledge | None = None) -> str | None:
    """The page key for what ``text`` asks about, or ``None``: a career or
    programme it names, else the page its words are about. "The other tab" is
    a tab, "can you speak English?" is about this call, and a question for a
    figure is answered by its own read: none of them is a page."""
    said = fold(text)
    if _ASKED_TAB.search(said) or asks_call_language(text) or asks_figures(text):
        return None
    k = k or kb.KNOWLEDGE
    if _POSTGRADO.search(said):
        # "Un magíster en psicología" is a postgraduate programme, never the
        # undergraduate career it names.
        program = k.named_program(text)
        return program.key if program is not None else page_key("postgrados.uahurtado.cl/")
    if (career := k.named_career(text)) is not None:
        return career.key
    if (program := k.named_program(text)) is not None:
        return program.key
    named = [(m.start(), path) for rx, path in _ASKED_PAGES if (m := rx.search(said))]
    return page_key(min(named)[1]) if named else None


# ─── The section a sentence describes ──────────────────────────────────────────

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
    hay ser esta estan tiene tienen puedes puede quieres aqui alli tambien pero cuando donde
    universidad alberto hurtado uah carrera""".split()  # noqa: SIM905
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


def _on_page(phrase: str, page: Page) -> bool:
    want = norm(phrase)
    if not want:
        return False
    parts = [page.title, page.text, *(f"{s.heading} {s.text}" for s in page.sections)]
    parts += [c.title for c in page.cards]
    return any(want in norm(p) for p in parts)


def named_card(sentence: str, cards: list[str] | tuple[str, ...]) -> str | None:
    """A card or label the sentence names by its whole title; the longest when
    it names two. Titles of a single short word count only when capitalised."""
    said = f" {' '.join(re.findall(r'[a-z0-9]+', fold(sentence)))} "
    best: str | None = None
    for card in cards:
        parts = re.findall(r"[a-z0-9]+", fold(card))
        name = " ".join(parts)
        if len(name) < 4 or f" {name} " not in said:
            continue
        if len(parts) == 1 and not re.search(rf"\b{re.escape(card.strip())}\b", sentence):
            continue
        if best is None or len(name) > len(fold(best)):
            best = card
    return best


#: Digits read out of what the visitor said: written, or spoken one by one.
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


_EMAIL = re.compile(r"^[\w.+-]+@[\w-]+(?:\.[\w-]+)+$")
#: A Chilean RUT, in any of its spellings: never typed by him.
_RUT = re.compile(r"\b\d{1,2}\.\d{3}\.\d{3}-?[\dkK]\b|\b\d{7,8}-[\dkK]\b")

#: The moves the page answers, with ``command_done``/``command_failed`` or with
#: their own event; one at a time, each within the time it takes.
_CONFIRMED_COMMANDS = frozenset(
    {
        "open_career_menu",
        "play_audiomalla",
        "fill_lead_form",
        "show_signup",
        "show_admission",
        "show_program",
    }
)
#: A page load across hosts on a heavy page, then a tab and a read.
_MOVE_TAKES_S = {"show_admission": 15.0, "show_program": 15.0, "open_career_menu": 12.0, "": 8.0}
#: A move after a page cue in the same reply waits for that page to report
#: itself, at most this long: sent on the old page, it would be lost in the load.
_PAGE_WAIT_S = 15.0
_PLAYOUT_MAX_S = 30.0


# ─── The brain ─────────────────────────────────────────────────────────────────


@dataclasses.dataclass
class _Sheet:
    """What the page has read of one career this call."""

    fees: Fees | None = None
    weights: Weights | None = None
    requirements_text: str = ""
    told: bool = False
    """The fees went to the model from an earlier read: a later one only
    corrects them."""


class UahurtadoBrain(GeminiBrain):
    """One per session. Javier: the university's knowledge, its careers and
    programmes, what the page in front reads live, and a mirror of the
    visitor's tabs, in Spanish or English."""

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
        self._key = f"{ADMISION}/"
        self._page_unseen = False
        self.tabs: list[TabInfo] = []
        self._active = ""
        self._tabs_unseen = False
        #: The page this reply's cues are on: the one in front, then wherever a
        #: page cue took it.
        self._cue_key = self._key
        self._idle_short = False
        self._nudges = 0
        self._backstop: str | None = None
        self._paged = False
        self._shown: str | None = None
        #: What the page read live, by career slug and programme slug.
        self._sheets: dict[str, _Sheet] = {}
        self._programs_read: dict[str, ProgramRead] = {}
        #: Scores the visitor gave for a career whose weights are still on
        #: their way from the page: worked out when they arrive.
        self._scores: dict[str, Scores] = {}
        self.form: LeadFormState | None = None
        self._heard: list[str] = []
        self._asked_figures = False
        #: The page a page cue of this reply is loading, and since when: a move
        #: for it waits for it to report itself.
        self._loading: tuple[str, float] | None = None
        self._parked: list[Action] = []
        #: Moves sent and not yet answered, the answers that came since his
        #: last turn, and the ask a read's answer brought: talked through once,
        #: in the next short quiet spell.
        self._sent: dict[str, float] = {}
        self._quiet_ok: set[str] = set()
        self._outcomes: list[str] = []
        self._talk: list[str] = []
        self._queued: Action | None = None
        self._turns = 0
        self._playing = 0
        self._played_at = 0.0
        self._idle_deferred = False
        self._audio_playing = False

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        init = session.init or {}
        where = str(init.get("url") or init.get("path") or "/")
        self._key = page_key(where) or f"{ADMISION}/"
        chosen = init.get("lang")
        self._chosen = chosen in LANGUAGE_NAMES
        self.spoken = "en" if chosen == "en" else OPENING
        # His own voice, settled here and not by the page. Both language legs
        # move together; what he hears, the toggle and `set_language` move them
        # again.
        await session.configure(
            Config(
                stt=SttConfig(language=self.spoken, patience=UAH_PATIENCE),
                tts=TtsConfig(voice=VOICE, language=self.spoken),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
            )
        )
        logger.info(
            "uahurtado: session start on {} in {}{}",
            self._key,
            self.spoken,
            " (chosen)" if self._chosen else "",
        )
        if self._chosen:
            self._note(_chosen_note(self.spoken, "before the call"))

    async def greet(self, session: Session) -> str:
        """The opener, written not generated."""
        line = greeting(page_url(self._key), self.spoken, self.kb)
        return for_the_voice(line) if self.spoken == "es" else for_the_voice_en(line)

    async def on_finalize(self, session: Session, fin: Finalize) -> None:
        """What was heard goes into the model's context; a word respelled for
        the voice is spelled as written again first."""
        if "idéo" in fin.heard or "u efe" in fin.heard:
            fin = dataclasses.replace(fin, heard=from_the_voice(fin.heard))
        await super().on_finalize(session, fin)
        self._playing = max(0, self._playing - 1)
        self._floor_free()

    def on_user_message(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]:
        return self._own_turn(self._answer(session, msg))

    async def _answer(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]:
        """A visitor who speaks the other language is answered in it from the
        first word, unless they chose; the tab they moved to is read in with
        what they said; his nod covers the model's thinking, and his own line
        any dead air after it."""
        heard = None if self._chosen else language_of(msg.text)
        if heard is not None and heard != self.spoken:
            await session.configure(self._speaking(heard))
            logger.info("uahurtado: language -> {} (heard)", heard)
        # They spoke first: the page's answers are in the context as notes,
        # and he answers them with what they said.
        self._outcomes.clear()
        self._talk.clear()
        self._idle_deferred = False
        self._playing = 0
        self._nudges = 0
        self._heard = [*self._heard[-3:], msg.text]
        self._asked_figures = asks_figures(msg.text)
        self._backstop = (
            None if about_the_call(msg.text) else asked_page(msg.text, self.kb) or self._backstop
        )
        self._restore_idle()
        self._read_in_screen()
        now = time.monotonic()
        fragment, self._heard_at = now - self._heard_at < _FRAGMENT_S, now
        nod = None if fragment else self._ack.line(msg.text, self.spoken)
        floor: Floor[Lang] = self._ack
        if nod is not None:
            logger.info("uahurtado: ack {!r}", nod)
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
        """A quiet spell. What the page answered since his turn is talked
        through first, with tools off, so a quiet spell never sends a move; else
        the toggle's confirmation; else a nudge, twice, then silence. While the
        audiomalla plays, nothing: the director has the floor."""
        self._restore_idle()
        self._backstop = None
        if (ask := self._take_ask()) is not None:
            self._note(ask)
            return self._reply(session, ToolChoice.NONE)
        if self._confirm is not None:
            line, self._confirm = self._confirm, None
            return say_line(self, line)
        if self._audio_playing or self._nudges >= _IDLE_NUDGES:
            return _silence()
        self._nudges += 1
        self._read_in_screen()
        quiet = f"The visitor has said nothing for about {round(idle.idle_ms / 1000)} seconds."
        if self._nudges == 1:
            ask = (
                "Speak into the quiet, briefly, as the guide beside them would: one useful thing "
                "about what is on their screen, or one question that helps them decide. Never "
                "ask whether they are still there, and never repeat your last line."
            )
        else:
            ask = (
                "Still quiet. One last, light offer, different from your last: something you "
                "could show them next. Then let them read."
            )
        self._note(f"{quiet} {ask}")
        return self._reply(session, ToolChoice.NONE)

    def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        return self._reply(session, None)

    async def _reply(
        self, session: Session, tools: ToolChoice | None
    ) -> AsyncGenerator[Speech, None]:
        """The model's turn, with its screen cues taken out of the speech and
        sent to the page; ``tools`` limits it (``None``: any).

        A turn that moved the page and said nothing says the move's written line
        (:func:`landed`) at once; one that came back with nothing at all — no
        words, no move, or only a promise — is asked once more with tools off."""
        if (line := self._confirm) is not None:
            self._confirm = None
            async for event in say_line(self, line):
                yield event
        self._cue_key = self._key
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
        if not _PROMISE.sub("", _CUE_TEXT.sub(" ", said)).strip(" .,!?¡¿…"):
            logger.warning("uahurtado: the model returned nothing; asking once more")
            again = self._written(session, self._cued(self._talk_now(session)))
            async for event in self._spelled(again):
                yield event

    async def _written(
        self, session: Session, turn: AsyncGenerator[Speech, None]
    ) -> AsyncGenerator[Speech, None]:
        """``turn``, with each unit held back until its first sentence is in,
        and both legs moved to the language it is in when it is not the call's."""
        held: list[Speech] = []
        text = ""

        async def release() -> AsyncGenerator[Speech, None]:
            nonlocal held, text
            written = language_of(text, sure=False)
            if written is not None and written != self.spoken:
                await session.configure(self._speaking(written))
                logger.info("uahurtado: language -> {} (written)", written)
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
                    respell = for_the_voice if self.spoken == "es" else for_the_voice_en
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
        key, self._backstop = self._backstop, None
        if "{" in chunk or key == self._key or self.kb.page(page_url(key)) is None:
            return chunk
        logger.info("uahurtado: the reply has no cue; showing {} first", key)
        return f"{{page: {short(key)}}}{chunk}"

    def _send_cue(self, raw: RawCue) -> None:
        """Check a cue against the sites and send it; one that names nothing
        real is dropped and logged rather than reaching the page."""
        if self.spoken == "es" and raw.at:
            raw = dataclasses.replace(raw, at=_anchor_for_voice(raw.at))
        if raw.kind == "page" and self._asked_figures:
            # The read opens that page and its tab itself; a load sent now
            # would be under way when it arrives.
            logger.info("uahurtado: page cue {!r} dropped: a read moves the page", raw.value)
            return
        cue = self._resolve_cue(raw)
        logger.info("uahurtado: cue {} {!r} at {!r} -> {}", raw.kind, raw.value, raw.at, cue)
        if cue is None:
            if raw.kind == "page":
                self._note(
                    f"[Your page cue {{page: {raw.value}}} named no page of the sites, so the "
                    "screen did not move. Never say it is on their screen; use a path from the "
                    "lists.]"
                )
            return
        self._paged = self._paged or raw.kind == "page"
        if raw.kind == "page" and cue.url and (key := page_key(cue.url)) != self._key:
            self._loading = (key or "", time.monotonic())
        if raw.kind == "show":
            self._shown = cue.heading or cue.text
        self.session.dispatch(cue)

    def _auto_cues(
        self, sentence: str, index: int, placed: tuple[tuple[CueKind, str], ...]
    ) -> list[tuple[CueKind, str]]:
        """The moves a sentence of his needs and did not bring: the page its
        first sentence is about, when nothing opened one, and the section, tab
        or card on the page it describes."""
        out: list[tuple[CueKind, str]] = []
        kinds = {k for k, _ in placed}
        pages = [p.key for k, v in placed if k == "page" and (p := self.kb.page(v)) is not None]
        key = pages[-1] if pages else self._cue_key
        if index == 0 and not self._paged and "page" not in kinds and not self._asked_figures:
            asked = asked_page(sentence, self.kb)
            if asked is not None and asked != self._key and self.kb.page(page_url(asked)):
                logger.info("uahurtado: he talks about {} with no cue; opening it", asked)
                out.append(("page", short(asked)))
                key = asked
        self._cue_key = key
        if kinds & {"show", "faq"}:
            return out
        page = self.kb.page(page_url(key))
        live = self.page is not None and page_key(self.page.url) == key
        faqs = [(f.q, f.a) for f in page.faqs] if page is not None else []
        if faqs and (question := best_section(sentence, faqs)) is not None:
            if question != self._shown:
                self._shown = question
                out.append(("faq", question))
            return out
        names = list(self.page.toggles) + list(self.page.cards) if live and self.page else []
        if page is not None:
            names += [c.title for c in page.cards]
            heading = best_section(sentence, [(s.heading, s.text) for s in page.sections])
            if heading is not None and heading != self._shown:
                out.append(("show", heading))
                return out
        named = named_card(sentence, list(dict.fromkeys(names)))
        if named is not None and named != self._shown:
            out.append(("show", named))
        return out

    def _resolve_cue(self, raw: RawCue) -> Cue | None:
        if raw.kind == "page":
            page = self.kb.page(raw.value)
            if page is None:
                return None
            self._cue_key = page.key
            return Cue(at=raw.at, word=raw.word, url=page.url)
        target = self.kb.page(page_url(self._cue_key))
        moved = self._cue_key != self._key
        url = page_url(self._cue_key) if moved else None
        if raw.kind == "faq":
            faqs = [f.q for f in target.faqs] if target else []
            if not moved:
                faqs = list(dict.fromkeys([*self._live("faqs"), *faqs]))
            question = _match(raw.value, faqs)
            if question is None:
                found = self._faq_elsewhere(raw.value)
                if found is None:
                    return None
                self._cue_key, question = found
                return Cue(at=raw.at, word=raw.word, url=page_url(found[0]), faq=question)
            return Cue(at=raw.at, word=raw.word, url=url, faq=question)
        # show: a heading or a tab of the page the visitor will be on, else a
        # card's title or words the page has.
        headings = [*target.headings, *target.toggles] if target else []
        if not moved:
            headings = [*self._live("headings"), *self._live("toggles"), *headings]
        else:
            headings += list(self._career_tabs(self._cue_key))
        heading = _match(raw.value, headings)
        text = None
        if heading is None:
            cards = [c.title for c in target.cards] if target else []
            if not moved:
                cards = [*self._live("cards"), *cards]
            text = _match(raw.value, cards)
            if text is None and not moved and self.page is not None:
                return Cue(at=raw.at, word=raw.word, text=raw.value[:120])
            if text is None and target is not None and not _on_page(raw.value, target):
                logger.info("uahurtado: {!r} is not on {}; dropped", raw.value, target.key)
                return None
            text = text or raw.value[:120]
        return Cue(at=raw.at, word=raw.word, url=url, heading=heading, text=text)

    def _career_tabs(self, key: str) -> tuple[str, ...]:
        career = self.kb.career_at(page_url(key))
        return career.tab_labels if career else ()

    def _live(self, what: Literal["headings", "toggles", "faqs", "cards"]) -> list[str]:
        if self.page is None:
            return []
        return list(getattr(self.page, what))

    def _faq_elsewhere(self, asked: str) -> tuple[str, str] | None:
        for page in self.kb.pages.values():
            if (q := _match(asked, [f.q for f in page.faqs])) is not None:
                return page.key, q
        for hit in self.kb.search(asked, 4):
            if hit.kind == "faq" and hit.key is not None:
                return hit.key, hit.title
        return None

    def _talk_now(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The one extra request an empty turn gets: tools declared, none callable."""
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
            logger.info("uahurtado: {} called with flat arguments; wrapping them", call.name)
            call = call.model_copy(update={"args": {"request": args}})
        return await super()._run(tool, call)

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Page→brain events, folded in silently: no floor taken, no turn."""
        event = UAH_EVENTS.parse(msg)
        if event is None:
            return
        logger.info("uahurtado: {} — {}", type(event).__voqal_event__, event)
        if isinstance(event, LanguageRequested):
            await self._requested(session, event)
            return
        if (note := self.apply_event(event)) is not None:
            self._note(note)

    async def _requested(self, session: Session, event: LanguageRequested) -> None:
        """The visitor pressed the other language on the toggle: both legs move
        in one awaited request, and the written confirmation is said next."""
        if event.language == self.spoken:
            return
        was = self.spoken
        try:
            await session.configure(self._speaking(event.language))
        except RequestRejected as rejected:
            logger.warning("uahurtado: switch to {} refused: {}", event.language, rejected)
            self.spoken = was
            session.dispatch(LanguageChanged(language=was))
            return
        logger.info("uahurtado: language -> {} (toggle)", event.language)
        self._chosen = True
        self._confirm = TOGGLE_CONFIRM[event.language]
        if not self._idle_short:
            self._idle_short = True
            configure_soon(session, Config(idle=IdleConfig(timeout_ms=_TALK_THROUGH_MS)))
        self._note(_chosen_note(event.language, "on the toggle"))

    def _speaking(self, language: Lang) -> Config:
        if language != self.spoken:
            self.session.dispatch(LanguageChanged(language=language))
        self.spoken = language
        return Config(
            stt=SttConfig(language=language, patience=UAH_PATIENCE),
            tts=TtsConfig(voice=VOICE, language=language),
        )

    # ─── Page → brain ───────────────────────────────────────────────────

    def apply_event(self, event: UahEvent) -> str | None:
        """Patch the mirror; return the line the model should see."""
        match event:
            case PageChanged():
                return self._page_changed(event)
            case TabsChanged():
                self.tabs = event.tabs
                self._active = event.active
                self._tabs_unseen = True
                return None
            case LanguageRequested():
                return None
            case AdmissionRead():
                return self._admission_read(event)
            case ProgramRead():
                return self._program_read(event)
            case LeadFormState():
                self.form = event
                return _form_note(event)
            case LeadSubmitted():
                self._say_soon(
                    "The visitor pressed Enviar on the form, but this is a preview: the page "
                    "stopped it, and nothing reached the university. Say so in one sentence, "
                    "and that on the real site the form would go to admissions."
                    if event.blocked
                    else "The visitor sent the form to admissions. Thank them in one sentence, "
                    "and say admissions will contact them."
                )
                return None
            case AudiomallaEnded():
                self._audio_playing = False
                if event.finished:
                    self._say_soon(
                        "The audiomalla finished. Ask in one sentence what they thought of it, "
                        "and offer one next step: what the career asks for, or what it costs."
                    )
                return None
            case CommandDone():
                detail = event.detail or "done"
                if event.command == "play_audiomalla":
                    self._audio_playing = True
                self._answered(event.command, f"{event.command} done: {detail}", ok=True)
                return f"[The page confirms {event.command}: {detail}.]"
            case CommandFailed() if event.command == "cue":
                return (
                    f"[A screen cue of yours did not land ({event.reason}). If the visitor "
                    "asks where it is, show it again; otherwise carry on.]"
                )
            case CommandFailed():
                outcome = f"{event.command} not done: {event.reason}"
                if event.command == "show_admission":
                    outcome += (
                        ". So you cannot see the fees or the weights right now: say so, and "
                        "that they are in the career's Requisitos y Aranceles tab"
                    )
                self._answered(event.command, outcome, ok=False)
                return (
                    f"[Not done on the page ({event.command}): {event.reason}. Tell the visitor "
                    "plainly and offer what you can do instead; never say it worked.]"
                )

    def _page_changed(self, event: PageChanged) -> str | None:
        self.page = event
        self._key = page_key(event.url) or self._key
        self._page_unseen = True
        if event.career is not None:
            self._sheet_from_page(event.career)
        if self._loading is not None:
            # The page the cue loaded, or another the visitor went to: either
            # way the load is over, and what waited for it goes now.
            self._loading = None
            self._send_parked()
        # Read in with their next message or quiet spell: they may click on
        # before they speak, and only the last page matters.
        return None

    def _sheet_from_page(self, sheet: CareerSheet) -> None:
        """A career page read itself at load, every tab pane included: its fees
        and weights are a live read, kept for read_fees and estimate_score."""
        s = self._sheets.setdefault(sheet.slug, _Sheet())
        fees = parse_fees(sheet.fees_text) if sheet.fees_text else None
        if fees is not None and fees.found:
            s.fees = fees
        weights = parse_weights([(r.label, r.value) for r in sheet.weights])
        if weights.found:
            s.weights = weights
        s.requirements_text = sheet.requirements_text or s.requirements_text

    def _admission_read(self, event: AdmissionRead) -> str:
        """The career's Requisitos y Aranceles, just read on screen: kept, and
        talked through — the fees, the weights, and any estimate waiting on them."""
        s = self._sheets.setdefault(event.slug, _Sheet())
        page_fees = parse_fees(event.fees_text or " ".join([event.matricula, event.arancel]))
        api_fees = parse_fees(event.api_fees_text) if event.api_fees_text else None
        fees = page_fees if page_fees.found else api_fees if api_fees and api_fees.found else None
        weights = parse_weights([(r.label, r.value) for r in event.weights])
        before = s.fees
        if fees is not None:
            s.fees = fees
        if weights.found:
            s.weights = weights
        s.requirements_text = event.requirements_text or s.requirements_text
        career = self.kb.career(event.slug)
        name = career.name if career else event.slug
        parts: list[str] = []
        if fees is not None:
            source = "the page" if page_fees.found else "the site's own record for this career"
            parts.append(f"Fees for {name}, read just now from {source}: {self._fees_said(fees)}.")
            if api_fees and api_fees.found and page_fees.found and api_fees != page_fees:
                mismatch = (api_fees.matricula, api_fees.arancel) != (
                    page_fees.matricula,
                    page_fees.arancel,
                )
                if mismatch:
                    parts.append(
                        "The site's own record gives other figures "
                        f"({self._fees_said(api_fees)}): quote the page, the one on their screen."
                    )
        else:
            parts.append(
                f"The fees for {name} could not be read right now ({event.error or 'not found'}): "
                "say you cannot see them right now, and that they are in its Requisitos y "
                "Aranceles tab, on their screen."
            )
        if weights.found:
            parts.append(f"PAES weights for {name}: {describe_weights(weights)}.")
        elif s.requirements_text:
            parts.append(
                f"{name} lists requirements instead of PAES weights: "
                f"{s.requirements_text[:_TEXT_IN_NOTE]}"
            )
        note = "[" + " ".join(parts) + "]"
        quiet = "show_admission" in self._quiet_ok and before == fees and s.told
        if (scores := self._scores.pop(event.slug, None)) is not None:
            worked = estimate(weights, scores) if weights.found else None
            ask = (
                f"Their estimate for {name}: {describe_estimate(worked, self.spoken)} Say it as an "
                "estimate, in two or three sentences, with the words given; then offer to open the "
                "PAES simulator for the official figure."
                if worked is not None
                else f"The page gave no PAES weights for {name}, so no estimate: say so, and "
                "offer the PAES simulator."
            )
            self._answered("show_admission", ask, ok=True, talk=True)
        elif quiet:
            self._answered("show_admission", "show_admission done", ok=True)
        else:
            s.told = fees is not None
            self._answered(
                "show_admission",
                f"{note[1:-1]} Say what the page shows, in two or three sentences, each figure "
                "as the words given.",
                ok=True,
                talk=True,
            )
        return note

    def _fees_said(self, fees: Fees) -> str:
        return describe_fees(fees, self.spoken)

    def _program_read(self, event: ProgramRead) -> str:
        self._programs_read[event.slug] = event
        program = self.kb.program(event.slug)
        name = program.name if program else event.slug
        note = f"[{name}, read just now: {_program_text(event, self.spoken)}]"
        if "show_program" in self._quiet_ok:
            self._answered("show_program", "show_program done", ok=True)
        else:
            self._answered(
                "show_program",
                f"{note[1:-1]} Say the fees, the early-enrolment discount and the application "
                "window from it, in three or four sentences, figures as the words given.",
                ok=True,
                talk=True,
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
            self._note(f"[The visitor's open UAH tabs — {listed}.]")
        self._tabs_unseen = False
        if not self._page_unseen or self.page is None:
            return
        self._page_unseen = False
        self._note(_screen_note(self.page))

    def _note(self, text: str) -> None:
        self.append_to_context(types.Content(role="user", parts=[types.Part(text=text)]))

    def _say_soon(self, ask: str) -> None:
        """Something the page reported that he talks through in the next quiet spell."""
        self._talk.append(ask)
        self._shorten_idle()

    def _holding_floor(self) -> bool:
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
        if self._idle_deferred and not self._holding_floor():
            self._shorten_idle()

    def _answered(self, command: str, outcome: str, *, ok: bool, talk: bool = False) -> None:
        """The page answered a move he sent. A move whose success was already
        told needs no word now (``_quiet_ok``); a failure always does; a read's
        answer (``talk``) is said in full. A move queued behind this one goes to
        the page now, or, if this one failed, is dropped and said."""
        if command not in self._sent:
            return
        del self._sent[command]
        quiet = ok and not talk and command in self._quiet_ok
        self._quiet_ok.discard(command)
        if (queued := self._queued) is not None and not self._busy():
            self._queued = None
            name = queued.__voqal_action__
            if ok:
                logger.info(
                    "uahurtado: {} answered; sending the {} queued behind it", command, name
                )
                self._send(queued)
            else:
                outcome += f" (so {name}, asked for while it ran, was not sent)"
                quiet = False
        if quiet:
            return
        if talk:
            self._talk.append(outcome)
        else:
            self._outcomes.append(outcome)
        self._shorten_idle()

    def _busy(self) -> str | None:
        now = time.monotonic()
        for command, until in self._sent.items():
            if until > now:
                return command
        return None

    def _send(self, action: Action) -> None:
        """Send a page move now, or, if a page cue of this reply is still
        loading another page, once that page has reported itself."""
        if self._loading is not None:
            key, since = self._loading
            if time.monotonic() - since < _PAGE_WAIT_S and key != self._key:
                logger.info("uahurtado: {} waits for {} to load", action.__voqal_action__, key)
                if not self._parked:
                    asyncio.get_running_loop().call_later(_PAGE_WAIT_S, self._load_over)
                self._parked.append(action)
                self._track(action)
                return
            self._loading = None
        self._track(action)
        self.session.dispatch(action)

    def _track(self, action: Action) -> None:
        command = action.__voqal_action__
        if command in _CONFIRMED_COMMANDS:
            took = _MOVE_TAKES_S.get(command, _MOVE_TAKES_S[""])
            self._sent[command] = time.monotonic() + took + (_PAGE_WAIT_S if self._parked else 0)

    def _load_over(self) -> None:
        """No page reported itself in time: what waited goes to the page in front."""
        if self._parked:
            logger.info("uahurtado: no page came in; sending what waited")
            self._loading = None
            self._send_parked()

    def _send_parked(self) -> None:
        parked, self._parked = self._parked, []
        for action in parked:
            logger.info("uahurtado: the page is in; sending {}", action.__voqal_action__)
            self.session.dispatch(action)

    def _move(self, action: Action, line: str = "shown", *, quiet_ok: bool = False) -> str | None:
        """Send a page move, or, while the last one is still under way on the
        page, queue it to follow: ``None`` when sent, else what the tool says.
        Only the latest queued move is kept. ``quiet_ok``: its success needs no
        talk-through, because his reply already said what it does."""
        command = action.__voqal_action__
        running = self._busy() if command in _CONFIRMED_COMMANDS else None
        if quiet_ok:
            self._quiet_ok.add(command)
        if running is None:
            if command in _CONFIRMED_COMMANDS:
                self._queued = None
            self._send(action)
            landed(_LANDED[line][self.spoken])
            return None
        self._queued = action
        landed(_LANDED["queued"][self.spoken])
        logger.info("uahurtado: {} queued behind {}", command, running)
        return (
            f"Queued, not sent yet: the page is still working on the last move ({running}). It "
            "goes to the page as soon as that one answers, and what it did comes back to you "
            "after. Say in a few words that you will do it as soon as the page is ready; never "
            "that it is done, and do not call it again."
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
        if self._talk:
            asks.extend(self._talk)
            self._talk = []
        return " ".join(asks) or None

    def _restore_idle(self) -> None:
        if self._idle_short:
            self._idle_short = False
            configure_soon(self.session, Config(idle=IdleConfig(timeout_ms=_IDLE_MS)))

    def _career_here(self) -> Career | None:
        return self.kb.career_at(self.page.url) if self.page is not None else None

    def _program_here(self) -> Program | None:
        return self.kb.program_at(self.page.url) if self.page is not None else None

    def _which_career(self, said: str | None) -> Career | str:
        """The career asked for, the one in front if none was named; else why not."""
        if said:
            career = self.kb.career(said)
            if career is not None:
                return career
            hits = ", ".join(c.name for c in self.kb.find_careers(said, 4)) or "none"
            return (
                f"No career '{said}'. Closest: {hits}. Use the name as the careers list writes it."
            )
        career = self._career_here()
        if career is not None:
            return career
        if self.page is not None and self.page.career is not None:
            slug = self.page.career.slug
            return self.kb.career(slug) or Career(
                slug, self.page.career.name or slug, self.page.url
            )
        return "Say which career: the page in front is not a career's."

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        """Read and search the university's knowledge, careers and programmes;
        open the careers menu; read a career's fees and weights off its page and
        work out the visitor's score; read a programme's fees and dates; play the
        audiomalla; fill the contact form (never sending it); ring a visit's
        sign-up; open the simulator; move between tabs; switch language."""
        return [
            self.read_topic,
            self.search_site,
            self.find_careers,
            self.find_programs,
            self.show_careers,
            self.read_fees,
            self.estimate_score,
            self.read_program,
            self.play_audiomalla,
            self.fill_lead_form,
            self.show_signup,
            self.open_link,
            self.switch_tab,
            self.set_language,
        ]

    @needs_result_now
    async def read_topic(self, request: TopicRequest) -> str:
        """Read one of the university's knowledge topics before answering from it."""
        topic = self.kb.topics.get(request.topic)
        if topic is None:
            return f"No topic '{request.topic}' is written yet: use search_site."
        return topic.text

    @needs_result_now
    async def search_site(self, request: SearchRequest) -> str:
        """Search the university's pages, sections, cards and FAQs. Each result
        names the page and the heading to take them to."""
        hits = self.kb.search(request.query, _SEARCH_HITS)
        if not hits:
            return (
                f"Nothing on the sites matches '{request.query}'. Try find_careers or "
                "find_programs, or other words in Spanish."
            )
        out: list[str] = []
        for h in hits:
            where = short(h.key) if h.key else "?"
            if h.kind == "faq":
                out.append(f"[FAQ on {where}] {h.title}\n  {h.snippet}")
            elif h.kind == "card":
                out.append(f"[card on {where}] {h.title}\n  {h.snippet}")
            else:
                heading = f", heading: {h.section}" if h.section else ""
                out.append(f"[page] {h.title} — {where}{heading}\n  {h.snippet}")
        return "\n".join(out)

    @needs_result_now
    async def find_careers(self, request: CareersRequest) -> str:
        """Find undergraduate careers by what the visitor wants to study: a
        name, an area, a faculty, a kind of work, a modality or schedule."""
        found = self.kb.find_careers(request.query, _CAREER_HITS)
        if not found:
            return f"No career matches '{request.query}'. The careers list in your prompt has all."
        return "\n".join(_career_line(c) for c in found)

    @needs_result_now
    async def find_programs(self, request: ProgramsRequest) -> str:
        """Find postgraduate programmes by subject, type and modality."""
        found = self.kb.find_programs(request.query, _PROGRAM_HITS * 3)
        if request.type != "any":
            kind = "otro" if request.type == "curso" else request.type
            found = [p for p in found if fold(kind) in fold(p.type)]
        if request.modalidad == "presencial":
            found = [p for p in found if fold(p.modalidad).startswith("presencial")]
        elif request.modalidad != "any":
            found = [p for p in found if fold(request.modalidad) in fold(p.modalidad)]
        if not found:
            return (
                f"No {request.type if request.type != 'any' else ''} programme matches "
                f"'{request.query}'{' ' + request.modalidad if request.modalidad != 'any' else ''}."
                " Offer postgrados.uahurtado.cl's listings, or other words."
            )
        return "\n".join(_program_line(p) for p in found[:_PROGRAM_HITS])

    async def show_careers(self, request: FacultyRequest) -> str:
        """Open the Carreras menu on their screen and ring one faculty's careers
        in it. Say a few of those careers as it opens, then ask which one."""
        faculties = list(self.kb.faculties())
        faculty = None
        if request.faculty:
            faculty = _match(request.faculty, faculties) or request.faculty
        careers = self.kb.faculties().get(faculty or "", [])
        queued = self._move(OpenCareerMenu(faculty=faculty), "menu", quiet_ok=True)
        if queued:
            return queued
        listed = "; ".join(c.name for c in careers) if careers else "the whole menu"
        return f"Opening the Carreras menu at {faculty or 'all faculties'}: {listed}."

    @needs_result_now
    async def read_fees(self, request: CareerRequest) -> str:
        """Read a career's fees off its page: opens its "Requisitos y
        Aranceles" tab on their screen. Call it for any question about what a
        career costs, with nothing written before it."""
        career = self._which_career(request.career)
        if isinstance(career, str):
            return career
        s = self._sheets.get(career.slug)
        here = self._career_here() == career
        if s is not None and s.fees is not None and s.fees.found and here:
            # Read off the page in front at its load: live, and on their screen
            # as the tab opens while he says it.
            s.told = True
            queued = self._move(
                ShowAdmission(url=career.url, slug=career.slug, focus="fees"), "fees", quiet_ok=True
            )
            lead = f"{queued}\n" if queued else ""
            return (
                f"{lead}Read just now from {career.name}'s page, which is opening its Requisitos y "
                f"Aranceles tab on their screen: {self._fees_said(s.fees)}. Say them now, each "
                "figure as the words given, and the year."
            )
        queued = self._move(ShowAdmission(url=career.url, slug=career.slug, focus="fees"), "fees")
        if queued:
            return queued
        return (
            f"Opening {career.name}'s Requisitos y Aranceles tab on their screen; the page reads "
            "the fees there and they reach you in a moment. In this response say only that you "
            "are opening its fees, in one short sentence: never a figure yet."
        )

    @needs_result_now
    async def estimate_score(self, request: ScoreRequest) -> str:
        """Work out the visitor's weighted PAES score for a career, with the
        career's own weights read off its page, and compare it with its
        minimums. Pass every score they gave, in points."""
        career = self._which_career(request.career)
        if isinstance(career, str):
            return career
        scores = Scores(
            nem=request.nem,
            ranking=request.ranking,
            lectora=request.lectora,
            matematica=request.matematica,
            historia=request.historia,
            ciencias=request.ciencias,
            m2=request.m2,
        )
        if all(v is None for v in vars(scores).values()):
            return (
                "No scores given: ask for their PAES scores, and their NEM and Ranking in points."
            )
        s = self._sheets.get(career.slug)
        here = self._career_here() == career
        if s is not None and s.weights is not None and s.weights.found:
            worked = estimate(s.weights, scores)
            if here:
                self._move(
                    ShowAdmission(url=career.url, slug=career.slug, focus="requirements"),
                    "requirements",
                    quiet_ok=True,
                )
            return (
                f"With {career.name}'s weights, read off its page ({describe_weights(s.weights)}): "
                f"{describe_estimate(worked, self.spoken)} Say it as an estimate, with the words "
                "given; the official figure is DEMRE's. Offer the PAES simulator."
            )
        self._scores[career.slug] = scores
        queued = self._move(
            ShowAdmission(url=career.url, slug=career.slug, focus="requirements"), "requirements"
        )
        if queued:
            return queued
        return (
            f"Opening {career.name}'s Requisitos y Aranceles tab, where its PAES weights are; the "
            "page reads them and the estimate reaches you in a moment. In this response say "
            "only that you are checking its weights, in one short sentence: never a score yet."
        )

    @needs_result_now
    async def read_program(self, request: ProgramRequest) -> str:
        """Read a postgraduate programme's fees, discounts, application window
        and start date off its page: opens "Requisitos y Valores" on screen."""
        program = self.kb.program(request.program) if request.program else self._program_here()
        if program is None and self.page is not None and self.page.program is not None:
            sheet = self.page.program
            program = self.kb.program(sheet.slug) or Program(sheet.slug, sheet.name, self.page.url)
        if program is None:
            return (
                f"No programme '{request.program}'. Use find_programs."
                if request.program
                else "Say which programme: the page in front is not a programme's."
            )
        here = self._program_here() == program
        sheet = self.page.program if (here and self.page is not None) else None
        if sheet is not None and sheet.requisitos_text:
            queued = self._move(
                ShowProgram(url=program.url, slug=program.slug), "program", quiet_ok=True
            )
            lead = f"{queued}\n" if queued else ""
            return (
                f"{lead}Read just now from {program.name}'s page, which is opening Requisitos y "
                f"Valores on their screen: {_sheet_text(sheet, self.spoken)} Say the fees and "
                "the dates from it, figures as the words given."
            )
        queued = self._move(ShowProgram(url=program.url, slug=program.slug), "program")
        if queued:
            return queued
        return (
            f"Opening {program.name}'s Requisitos y Valores on their screen; the page reads them "
            "and they reach you in a moment. In this response say only that you are opening "
            "them, in one short sentence: never a figure yet."
        )

    async def play_audiomalla(self) -> str:
        """Play the career's audiomalla, its director talking about it, on the
        career page in front. Say one short sentence before it; then stay quiet
        until it ends."""
        career = self._career_here()
        sheet = self.page.career if self.page is not None else None
        if career is None and sheet is None:
            return "Not played: the page in front is not a career's. Open the career first."
        has = (sheet.has_audiomalla if sheet else False) or (
            career.has_audiomalla if career else False
        )
        if not has:
            name = career.name if career else "This career"
            return f"Not played: {name}'s page has no audiomalla. Offer its description instead."
        url = career.url if career else (self.page.url if self.page else "")
        return self._move(PlayAudiomalla(url=url), "audio", quiet_ok=True) or (
            "Pressing play on the audiomalla. Say nothing more until it ends: the page tells you."
        )

    async def fill_lead_form(self, request: LeadRequest) -> str:
        """Fill the page's contact form ("Solicita información") with what the
        visitor said. Never their RUT, and never sent: they press Enviar."""
        form = self.page.form if self.page is not None else None
        if form is None:
            return (
                "Not filled: the page in front has no contact form. Every career page has one at "
                "its top: open the career's page with a page cue first, then fill it."
            )
        given = {
            k: v.strip()
            for k, v in request.model_dump(exclude={"focus_rut"}).items()
            if isinstance(v, str) and v.strip()
        }
        refused: list[str] = []
        if any(_RUT.search(v) for v in given.values()):
            return (
                "Not filled: that is a RUT. You never type a RUT: ring its field with focus_rut "
                "and ask them to type it themselves."
            )
        if (email := given.get("email")) is not None:
            email = "".join(email.split()).lower()
            if not _EMAIL.match(email):
                refused.append(f"email {email!r} is not an address: ask them to spell it again")
                given.pop("email")
            else:
                given["email"] = email
        if (fono := given.get("fono")) is not None:
            digits = re.sub(r"\D", "", fono)
            heard = said_digits(" ".join(self._heard[-2:]))
            if len(digits) < _PHONE_MIN or (len(heard) >= _PHONE_MIN and digits not in heard):
                said = f" (they said {' '.join(heard)})" if len(heard) >= _PHONE_MIN else ""
                refused.append(
                    f"fono {' '.join(digits) or fono!r} is not what the visitor said{said}: never "
                    "change, shorten or complete their digits; ask again"
                )
                given.pop("fono")
            else:
                given["fono"] = ("+" if fono.strip().startswith("+") else "") + digits
        for field_name, options in (("carrera", form.career_options), ("via", form.via_options)):
            if (said := given.get(field_name)) is None:
                continue
            if field_name not in form.fields or not options:
                given.pop(field_name)
                continue
            if (hit := _match(said, options)) is None:
                refused.append(f"{field_name} {said!r} is not on its list: {_clip(options, 12)}")
                given.pop(field_name)
            else:
                given[field_name] = hit
        missing_fields = [k for k in given if k not in form.fields]
        for k in missing_fields:
            given.pop(k)
        if not given and not request.focus_rut:
            return "Not filled: " + ("; ".join(refused) or "nothing to fill.")
        queued = self._move(
            FillLeadForm(**given, focus_rut=request.focus_rut),
            "form",  # type: ignore[arg-type]
        )
        if queued:
            return queued
        out = f"Filling {', '.join(given) or 'nothing'} on the form; the page confirms in a moment."
        if request.focus_rut:
            out += " The RUT field is rung for them to type."
        if refused:
            out += " Not filled: " + "; ".join(refused) + "."
        return out + " Never say it is sent: they review it and press Enviar."

    async def show_signup(self, request: VisitRequest) -> str:
        """Ring the "Inscribirse aquí" of a visit or workshop on /ven-y-conocenos/.
        Never opens it: the visitor signs up there themselves."""
        visits = self.page.visits if self.page is not None else []
        if not visits:
            return (
                "Not shown: the page in front lists no visits. Open /ven-y-conocenos/ with a page "
                "cue first."
            )
        title = _match(request.visit, [v.title for v in visits])
        visit = next((v for v in visits if v.title == title), None)
        if visit is None:
            listed = "; ".join(v.title for v in visits if not v.done) or "none open"
            return f"Not shown: no visit '{request.visit}'. Open ones: {listed}."
        if visit.done:
            return f"Not shown: {visit.title} already happened (REALIZADO). Never offer it."
        if not visit.open:
            return f"Not shown: sign-ups for {visit.title} are closed. Say so."
        return self._move(ShowSignup(title=visit.title), "signup", quiet_ok=True) or (
            f"Ringing the sign-up of {visit.title}. They open it and sign up themselves."
        )

    async def open_link(self, request: LinkRequest) -> str:
        """Open, in a new tab, the PAES simulator or the career's malla PDF.
        The simulator asks for their details: they fill it in, never you."""
        if request.kind == "simulador":
            self._move(OpenLink(url=SIMULADOR, label="Simula tu puntaje"), "link")
            return (
                "Opening the PAES simulator in a new tab. It asks for their details and scores, "
                "which they fill in themselves; you fill in nothing there."
            )
        sheet = self.page.career if self.page is not None else None
        here = self._career_here()
        url = (sheet.malla_pdf if sheet else "") or (here.malla_pdf if here else "")
        if not url or not is_link_url(url):
            return "Not opened: the page in front has no malla PDF. Open the career's page first."
        self._move(OpenLink(url=url, label="Malla curricular"), "link")
        return "Opening the malla curricular in a new tab."

    async def switch_tab(self, request: TabRequest) -> str:
        """Bring another of the visitor's UAH tabs to the front."""
        if len(self.tabs) < 2:
            return (
                "Not switched: they have only this one tab. To show a page, cue it with "
                "{page: …}; never say it is on screen otherwise."
            )
        tab = next((t for t in self.tabs if t.tab_id == request.tab_id), None)
        if tab is None:
            listed = ", ".join(f"{t.tab_id} ({t.title})" for t in self.tabs) or "none"
            return f"Not switched: no tab '{request.tab_id}'. Open tabs: {listed}."
        self._move(FocusTab(tab_id=tab.tab_id), "tab")
        return f"Bringing '{tab.title or tab.url}' to the front."

    async def set_language(self, request: LanguageRequest) -> str:
        """Conduct the rest of the call in Spanish ('es') or English ('en'),
        listening and speaking. Call it when they ask for the other language in
        words that are not already it, and to go back. Say one short line in the
        language you are switching to, in the same response."""
        self._chosen = True
        configure_soon(self.session, self._speaking(request.language))
        logger.info("uahurtado: language -> {} (asked)", request.language)
        return "ok"


# ─── Notes ─────────────────────────────────────────────────────────────────────


def _career_line(c: Career) -> str:
    facts = ", ".join(
        x for x in (c.faculty, c.duration, c.jornada, c.modalidad, c.campus, c.title_awarded) if x
    )
    line = f"- {c.name} — {short(c.key)}" + (f" — {facts}" if facts else "")
    if c.has_audiomalla:
        line += " — has an audiomalla"
    return line + (f"\n  {c.summary[:240]}" if c.summary else "")


def _program_line(p: Program) -> str:
    facts = ", ".join(x for x in (p.type, p.area, p.modalidad, p.duration) if x)
    line = f"- {p.name} — {short(p.key)}" + (f" — {facts}" if facts else "")
    return line + (f"\n  {p.summary[:240]}" if p.summary else "")


def _money_said(text: str, lang: str) -> str:
    items = money_items(text)
    say = pesos_es if lang == "es" else pesos_en
    out = [f"{label} ${n:,}".replace(",", ".") + f" — say “{say(n)}”" for label, n in items]
    deadlines = [f"{d} ({date_said(d, lang)})" for d in dates_in(text)]
    if deadlines:
        out.append("dates on it: " + ", ".join(deadlines))
    return "; ".join(out)


def _sheet_text(sheet: ProgramSheet, lang: str) -> str:
    text = sheet.requisitos_text[:_TEXT_IN_NOTE]
    side = "; ".join(f"{r.label}: {r.value}" for r in sheet.sidebar)
    out = f"Requisitos y Valores: “{text}”."
    if money := _money_said(sheet.requisitos_text, lang):
        out += f" Amounts: {money}."
    if side:
        out += f" Sidebar: {side}."
    return out


def _program_text(event: ProgramRead, lang: str) -> str:
    out: list[str] = []
    text = event.requisitos_text or event.api_requisitos_text
    if text:
        out.append(f"Requisitos y Valores: “{text[:_TEXT_IN_NOTE]}”.")
        if money := _money_said(text, lang):
            out.append(f"Amounts: {money}.")
    for label, value in (
        ("applications open", event.postulacion_desde),
        ("applications close", event.postulacion_hasta),
        ("the programme starts", event.inicio_programa),
    ):
        if value:
            out.append(f"{label} {value} ({date_said(value, lang)}).")
    if event.sidebar:
        out.append("Sidebar: " + "; ".join(f"{r.label}: {r.value}" for r in event.sidebar) + ".")
    if not out:
        out.append(
            f"nothing could be read ({event.error or 'empty'}): say you cannot see it right now, "
            "and that it is under Requisitos y Valores on their screen."
        )
    return " ".join(out)


def _form_note(event: LeadFormState) -> str:
    note = (
        f"[The contact form: filled {', '.join(event.filled) or 'nothing'}; still missing "
        f"{', '.join(event.missing) or 'nothing'}"
    )
    if event.invalid:
        note += f"; not valid: {', '.join(event.invalid)}"
    note += "."
    note += (
        " It is complete: the visitor reviews it and presses Enviar themselves.]"
        if event.ready
        else " The RUT is the visitor's to type.]"
    )
    return note


def _screen_note(p: PageChanged) -> str:
    where = {
        "home": "the home page",
        "career": "a career's page",
        "program": "a postgraduate programme's page",
        "listing": "a listing of programmes",
    }.get(p.kind, "a page")
    key = page_key(p.url)
    note = f"[The tab in front shows {where}: “{_short_title(p.title) or p.url}” ({short(key) if key else p.url})."
    if p.translated:
        note += (
            " Chrome is translating it, so its words may not be the site's: cue the site's "
            "Spanish headings anyway."
        )
    if p.career is not None:
        c = p.career
        facts = "; ".join(f"{r.label}: {r.value}" for r in c.facts)
        note += f" Career: {c.name or c.slug}."
        if facts:
            note += f" Datos Académicos: {facts}."
        if c.tabs:
            note += f" Its tabs: {'; '.join(c.tabs)}."
        if c.has_audiomalla:
            note += f" It has an audiomalla{(' (' + c.audiomalla_label + ')') if c.audiomalla_label else ''}."
        note += (
            " Its fees and PAES weights are in the Requisitos y Aranceles tab: read them with "
            "read_fees or estimate_score, never from memory."
        )
    if p.program is not None:
        g = p.program
        note += f" Programme: {g.name or g.slug}."
        if g.accordion:
            note += f" Its sections: {'; '.join(g.accordion)}."
        note += " Its fees and dates are under Requisitos y Valores: read them with read_program."
    if p.headings:
        note += f" Its headings: {_clip(p.headings, _HEADINGS_IN_NOTE)}."
    if p.toggles and p.career is None:
        note += f" Its tabs and accordions: {_clip(p.toggles, _TOGGLES_IN_NOTE)}."
    if p.cards:
        note += f" Its cards: {_clip(p.cards, _CARDS_IN_NOTE)}."
    if p.faqs:
        note += f" Its FAQs: {_clip(p.faqs, _FAQS_IN_NOTE)}."
    if p.visits:
        coming = [
            f"{v.title} ({v.text[:120]})" + ("" if v.open else ", sign-ups closed")
            for v in p.visits
            if not v.done
        ]
        past = [v.title for v in p.visits if v.done]
        if coming:
            note += f" Visits and workshops coming up: {'; '.join(coming)}."
        if past:
            note += f" Already held (REALIZADO, never offer them): {'; '.join(past)}."
    if p.form is not None:
        f = p.form
        note += f" It has the contact form, with {', '.join(f.fields)}"
        note += f", already for {f.career}." if f.career else "."
        if f.career_options:
            note += " Its career list is a select."
    return note + "]"


__all__ = [
    "UahurtadoBrain",
    "asked_page",
    "asks_call_language",
    "best_section",
    "for_the_voice",
    "from_the_voice",
    "greeting",
    "language_of",
    "named_card",
]
