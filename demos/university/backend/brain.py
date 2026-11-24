"""UniversityBrain — Varenya University's course advisor and admissions counsellor.

One brain, two jobs, picked by the page the call is on (``prompt.job_for``):

- On ``/programs`` (and programme, school and home pages) the agent is the
  **course advisor**: it hears the learner's goal, level, interests, budget and
  hours, calls ``find_programs`` and narrates the result while the finder's
  filters tick on screen (``{filter: …}`` cues), marks two or three picks and
  opens the side-by-side comparison.
- On ``/admissions`` and ``/apply`` (and scholarships, campus life) it is the
  **admissions counsellor**: it answers fees, eligibility, deadlines,
  scholarships, hostel and loans from the authored reference in its prompt, and
  fills the five-step application with ``{fill: field | value}`` cues as the
  family talks.

Every screen move is a Stage move (``frontend/src/stage/scene.json``), cued in
the agent's words; the page answers each with a result, and reports the
finder and the form as Stage state events. A route change arrives as Stage's
``hello`` and switches the job.

**Voice and language.** The character, its voice per language and the
languages live in ``persona.json``. The page's EN / हिंदी toggle rides
``init.lang``; ``on_session_start`` moves both legs before the greeting. Hindi
heard, a reply written in Devanagari, the toggle pressed mid-call or
``set_language`` move both legs again, and the page's toggle follows
(``language_changed``).

**What is marked ``@needs_result_now``**: the reads the model must answer from
— the programme match, a programme's facts, the comparison, the eligibility and
scholarship check, the screen. ``set_language`` is an act and is not.
``program_details`` also opens the programme's page at the section asked about
(``site.open`` with a section), so "show me the curriculum" moves the screen in
the same turn (U1).

**Never a promise and then silence** (U1, the bank's B1, insurance I1): a read
the visitor asked to hear owes a written answer (``owe``), said by the brain
when the model's turn says nothing after the tool ran; a sentence promising the
screen with no cue is kept by Stage's backstop (``_auto_cues``) or, failing
that, at the end of the turn (``_keep``). While the visitor browses on their
own the agent stays quiet unless spoken to (U3).

**The application, a step at a time** (U2, the owner's call of 25 Nov):
``fill_application`` fills every detail said in one go, checks each against
the form first, fills what a value implies (a city's state, a programme's
intake), and returns what landed, what was refused and what the step still
needs, with the next question to ask (a group of related details, never one
field at a time). A finished step is offered as "shall we go to the next
step?", and a plain yes moves the form on (the brain does it, so it never
waits on the model). Mobile and email are typed by the applicant in boxes the
agent rings (X9). An admission question goes to the admission process, never
to a comparison (``backend/form.py``).
"""

from __future__ import annotations

import contextlib
import re
from collections.abc import AsyncGenerator, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import urlparse

from loguru import logger
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from voqalize_demos import PATIENCE, FallbackLine, configure_soon, landed, needs_result_now

from voqalize.sdk import (
    Action,
    AppEvent,
    AppEvents,
    Finalize,
    RTVIMessage,
    Session,
    Speech,
    SpeechChunk,
    SpeechStart,
    UserIdle,
    UserMessage,
)
from voqalize.sdk.openai import OpenAIBrain
from voqalize.sdk.stage import AutoCue, Dropped, Mirror, Move, RawCue, Stage, match_label
from voqalize.sdk.stage.wire import (
    StageEvent,
    StageHello,
    StageProgress,
    StageResult,
)
from voqalize.sdk.wire import Config, IdleConfig, RedialConfig, SttConfig, TtsConfig

from . import form
from .data import CampusId, Level, Mode, SchoolId, Stream, application, catalogue, persona
from .finder import (
    SECTIONS,
    Applicant,
    Profile,
    compare_text,
    eligibility_text,
    facets,
    find_text,
    matches,
    program_text,
    resolve_facet,
    resolve_program,
    section_named,
    section_of,
    section_text,
)
from .prompt import JOB_NOTE, Job, Lang, greeting, job_for, system_instruction
from .rejoin import Rejoin
from .spoken import SpokenAmounts, amounts_note, implausible, speak_text
from .stage_gen import MOVES, SPEC, ReadRequest

MODEL = "gpt-6.1-terra"
REASONING = "medium"

#: A quiet spell this long is not spoken into: a family reading the screen is not nudged.
_IDLE_MS = 15000
#: The quiet spell after the applicant submitted: the congratulation comes now.
_REACT_IDLE_MS = 1500

#: Where the demo is served, so a page's address reads as its route.
BASE = "/demos/university"

#: The confirmation, in the new language, when the call switches.
SWITCHED: dict[Lang, str] = {
    "en": "Sure, let's continue in English.",
    "hi": "ज़रूर, अब हिंदी में बात करते हैं।",
}

# ─── Brain → page: beside Stage ─────────────────────────────────────────────


class LanguageChanged(Action):
    """The call's language moved: the page's EN / हिंदी toggle follows."""

    language: Literal["en", "hi"]


# ─── Page → brain: beside Stage ─────────────────────────────────────────────


class LanguageRequested(AppEvent):
    """The visitor pressed the other language on the toggle, mid-call."""

    language: Literal["en", "hi"]


_EVENTS = AppEvents(LanguageRequested, StageResult, StageHello, StageProgress, StageEvent)

# ─── Tool requests ──────────────────────────────────────────────────────────


class FindRequest(BaseModel):
    """What the learner has said, as hard limits and interests."""

    level: Level | None = Field(
        None,
        description="ug for after Class 12, pg for graduates, diploma, certificate (short courses).",
    )
    school: SchoolId | None = Field(None, description="Only when they named an area.")
    interests: str = Field(
        "", description="Their goal and interests in their words: 'data, AI, business'."
    )
    mode: Mode | None = Field(
        None, description="full_time (on campus), online, weekend (executive) or hybrid."
    )
    campus: CampusId | None = None
    max_fee_per_year: int | None = Field(
        None,
        description="Their budget a year, in rupees: 1.5 lakh or dedh lakh is 150000.",
    )
    hours_per_week: int | None = Field(
        None,
        description="Hours a week they can give; under 16 rules out full-time programmes.",
    )


Section = Literal[
    "overview",
    "eligibility",
    "selection",
    "fees",
    "scholarships",
    "deadlines",
    "outcomes",
    "curriculum",
    "highlights",
]


class ProgramRequest(BaseModel):
    program: str = Field(description="A programme id from the catalogue, or its name.")
    section: Section = Field(
        "overview",
        description="The part they asked about: curriculum (modules, subjects, syllabus), fees, "
        "outcomes (placements, salary), eligibility, scholarships, deadlines, selection "
        "(entrance), highlights; overview for the programme in general. Its page opens there "
        "on their screen.",
    )


class CompareRequest(BaseModel):
    programs: list[str] = Field(description="Two or three programme ids.")


class EligibilityRequest(BaseModel):
    """What the applicant has told you. Leave out what they have not said."""

    program: str = Field(description="A programme id.")
    class12_stream: Stream | None = None
    class12_percent: float | None = None
    graduation_percent: float | None = None
    experience_years: float | None = None
    vusat_rank: int | None = None
    family_income_lakh: float | None = Field(
        None, description="Annual family income in lakh: ₹6,00,000 or six lakh is 6."
    )
    gender: Literal["female", "male", "other"] | None = None
    sports: Literal["national", "state"] | None = Field(
        None, description="The level of a sports medal in the last three years."
    )
    defence_family: bool = False


class LanguageRequest(BaseModel):
    language: Literal["en", "hi"]


FieldName = Literal[
    "full_name",
    "date_of_birth",
    "gender",
    "mobile",
    "email",
    "city",
    "state",
    "parent_name",
    "class10_board",
    "class10_percent",
    "class12_board",
    "class12_stream",
    "class12_status",
    "class12_percent",
    "graduation_degree",
    "graduation_percent",
    "entrance_exam",
    "entrance_score",
    "program",
    "campus",
    "intake",
    "hostel",
    "room_type",
    "scholarship",
    "doc_class10",
    "doc_class12",
    "doc_graduation",
    "doc_score",
    "doc_photo_id",
    "doc_photo",
    "doc_income",
    "pay_method",
    "declaration",
]


class FieldValue(BaseModel):
    field: FieldName
    value: str = Field(
        description="As they said it, or the option id: 'Samkeet Jain', '22 Oct 1996', 'male', "
        "'state', '93.5', 'science_pcm', 'passed', 'btech-ai-ml', 'bengaluru', 'yes', 'later'."
    )


class FillRequest(BaseModel):
    """Every application detail they just gave, and whether to move on a step."""

    values: list[FieldValue] = Field(
        default_factory=list,
        description="One entry per field they gave in this turn (all of them, never one at a "
        "time), plus any they gave earlier in the call that the form does not hold yet.",
    )
    next_step: bool = Field(
        False,
        description="True when they said yes to going to the next step, or asked for next.",
    )


# ─── Hindi heard ────────────────────────────────────────────────────────────

# The small grammar words of Hindi, as the English recognizer spells them and as
# the Hindi one writes them: two different ones in a sentence is Hindi or Hinglish.
_HINDI_WORDS = frozenset(
    [
        "hai",
        "hain",
        "hoon",
        "kya",
        "mein",
        "mujhe",
        "chahiye",
        "karo",
        "kariye",
        "karna",
        "dikhao",
        "batao",
        "bataiye",
        "aap",
        "nahi",
        "nahin",
        "sakte",
        "sakta",
        "kitna",
        "kitne",
        "kitni",
        "liye",
        "bhi",
        "aur",
        "yeh",
        "woh",
        "accha",
        "haan",
        "ka",
        "ki",
        "ke",
        "ko",
        "se",
        "hum",
        "humko",
        "beta",
        "beti",
        "fees",
        "kaise",
        "kab",
        "है",
        "हैं",
        "हूँ",
        "क्या",
        "में",
        "मुझे",
        "चाहिए",
        "करो",
        "करिए",
        "दिखाओ",
        "बताइए",
        "आप",
        "नहीं",
        "सकते",
        "कितना",
        "कितनी",
        "लिए",
        "भी",
        "और",
        "यह",
        "वह",
        "अच्छा",
        "हाँ",
        "का",
        "की",
        "के",
        "को",
        "से",
        "हम",
        "कैसे",
        "कब",
    ]
)
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def sounds_hindi(text: str) -> bool:
    words = set(re.findall(r"[\wऀ-ॿ]+", text.lower()))
    return len(words & _HINDI_WORDS) >= 2 or len(_DEVANAGARI.findall(text)) >= 4


def route_of(url: str) -> str:
    """A page address as the demo's route: ``…/demos/university/apply`` → ``/apply``."""
    path = urlparse(url).path or url
    if BASE in path:
        path = path.split(BASE, 1)[1]
    return "/" + path.strip("/")


# ─── Cue resolution ─────────────────────────────────────────────────────────

_PAGES = ("home", "programs", "admissions", "scholarships", "campus-life", "apply", "schools")


def _choice(field: str, value: str) -> str:
    """A choice field's option id for a spoken value; the value itself when it
    names none, so the page refuses it with the options."""
    f = application().field(field)
    if f is None or not f.options:
        return value
    by_label = {label: oid for oid, label in f.options}
    ids = [oid for oid, _ in f.options]
    if value.strip().lower() in ids:
        return value.strip().lower()
    hit = match_label(value, ids) or match_label(value, list(by_label))
    return by_label.get(hit, hit) if hit is not None else value


def resolve_fill(field: str, value: str) -> list[str] | None:
    f = application().field(field.strip())
    if f is None:
        return None
    v = value.strip()
    match f.type:
        case "choice":
            return [f.name, _choice(f.name, v)]
        case "percent":
            m = re.search(r"\d+(?:\.\d+)?", v)
            return [f.name, m.group(0) if m else v]
        case "program":
            return [f.name, resolve_program(v) or v]
        case "document":
            hit = match_label(v, ["uploaded", "later"])
            return [f.name, hit or v]
        case "scholarship":
            if v.lower() in ("none", "no", "nil"):
                return [f.name, "none"]
            c = catalogue()
            ids = [s.id for s in c.scholarships]
            names = {s.name: s.id for s in c.scholarships}
            hit = match_label(v, ids) or names.get(match_label(v, list(names)) or "")
            return [f.name, hit or v]
        case _:
            return [f.name, v]


def resolve_cue(move: Move, args: list[str]) -> list[str] | None:
    """Each cue's arguments as the page names them; ``None`` drops the cue."""
    match move.id:
        case "catalogue.filter":
            if len(args) < 2:
                return None
            pair = resolve_facet(args[0], args[1])
            return list(pair) if pair else None
        case "catalogue.clear":
            if not args or not args[0].strip() or args[0].strip().lower() == "all":
                return []
            hit = match_label(args[0], list(facets()))
            return [hit] if hit else None
        case "catalogue.pick" | "catalogue.compare":
            ids = [p for p in (resolve_program(a) for a in args if a.strip()) if p]
            need = 2 if move.id == "catalogue.compare" else 1
            return ids[:3] if len(ids) >= need else None
        case "site.open":
            pid = resolve_program(args[0]) if args else None
            if pid is None:
                return None
            said = args[1].strip().lower() if len(args) > 1 else ""
            section = said if said in SECTIONS else section_of(said) if said else None
            return [pid, section] if section else [pid]
        case "site.go":
            if not args:
                return None
            page = args[0].strip().lower().strip("/")
            if page.startswith("schools/"):
                return [page]
            hit = match_label(page, list(_PAGES))
            return [hit] if hit else None
        case "apply.fill":
            return resolve_fill(args[0], args[1]) if len(args) >= 2 else None
        case _:
            return args


# ─── One turn's record: the floor under a read, the words said ───────────────


@dataclass
class _Turn:
    """What one turn said and owes: how many units of the model's speech went
    out, the written answer a read owes if nothing is said after it ran (and a
    move to make with it), and the words spoken, cues taken out."""

    starts: int = 0
    owed: str | None = None
    owed_at: int = 0
    then: tuple[str, dict[str, Any]] | None = None
    said: list[str] = field(default_factory=list)


#: Per turn, like ``landed``'s record: each turn runs in its own task.
_TURN: ContextVar[_Turn | None] = ContextVar("university_turn", default=None)


def owe(line: str, then: tuple[str, dict[str, Any]] | None = None) -> None:
    """Beside a read the visitor asked to hear: the written answer the brain
    says if the model's turn says nothing after the tool ran, and the move it
    makes with it. The floor under "I'll open the page" and then silence (U1),
    as the bank's B1 fix."""
    if (record := _TURN.get()) is not None:
        record.owed = line
        record.owed_at = record.starts
        record.then = then


async def _counted(
    turn: AsyncGenerator[Speech, None], record: _Turn
) -> AsyncGenerator[Speech, None]:
    """The model's turn, each unit counted and its words kept (not the brain's own lines)."""
    try:
        async for s in turn:
            if isinstance(s, SpeechStart):
                record.starts += 1
            elif isinstance(s, SpeechChunk):
                record.said.append(s.text)
            yield s
    finally:
        await turn.aclose()


#: A sentence that promises to put something on screen: "I'll open the page",
#: "let me show you", "here's the curriculum on your screen".
_PROMISE = re.compile(
    r"\b(?:i['\u2019]?ll|i will|i['\u2019]?m|i am|let me|let['\u2019]s|here['\u2019]?s|here is|"
    r"you can see|you['\u2019]?ll see|on (?:your |the )?screen)\b",
    re.IGNORECASE,
)
_PROMISE_VERB = re.compile(
    r"\b(?:open|opening|opened|show|showing|pull|pulling|bring|bringing|screen|page)\b",
    re.IGNORECASE,
)

#: The sections of the admissions page a sentence can name without a cue.
_ADMISSIONS_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("hostel", ("hostel", "room", "rooms", "mess")),
    ("loans", ("loan", "loans")),
    ("refund", ("refund",)),
    ("instalments", ("instalment", "instalments", "installment", "installments")),
    ("documents", ("documents",)),
    ("vusat", ("vusat", "entrance test")),
    ("scholarships", ("scholarship", "scholarships")),
    ("deadlines", ("deadline", "deadlines", "last date")),
    ("fees", ("fee", "fees")),
)


def _admissions_section(sentence: str) -> str | None:
    low = f" {sentence.lower()} "
    best: tuple[int, str] | None = None
    for name, words in _ADMISSIONS_SECTIONS:
        for w in words:
            at = low.find(f" {w}")
            if at >= 0 and (best is None or at < best[0]):
                best = (at, name)
    return best[1] if best else None


def _program_named(sentence: str) -> str | None:
    """A programme named in full in ``sentence`` (the longest name), or ``None``."""
    low = sentence.lower()
    hits = [p for p in catalogue().programs if p.name.lower() in low]
    return max(hits, key=lambda p: len(p.name)).id if hits else None


# ─── The application flow (U2) ──────────────────────────────────────────────

#: An admission question: "undergraduate admission into computer science",
#: "how do I apply", "the process for admission".
_ADMISSION = re.compile(
    r"\b(?:admissions?|admit|apply|applying|application|enrol+|enrol+ment|get(?:ting)? in(?:to)?)\b",
    re.IGNORECASE,
)

ADMISSION_NOTE = (
    "[They are asking about ADMISSION: lead to the admission process and the application, "
    "never to a comparison. With one programme in mind, call program_details for it with "
    "section selection (its admission process opens on screen), say the steps in one or two "
    "sentences, and offer to start the application now. If the programme is not clear yet, "
    "find it with find_programs and name the one that fits.]"
)

#: A plain yes to "shall we go to the next step?", and asking to move on outright.
_YES = re.compile(
    r"^(?:yes|yeah|yep|yup|ya|ok|okay|sure|correct|right|fine|perfect|done|go ahead|"
    r"haan|haan ji|ha|ji|theek hai|looks (?:right|good|fine)|that(?:'s| is) (?:right|correct|fine))"
    r"(?:[ ,]+(?:please|go ahead|let's go|sure|yes|ji|it is|it does|looks good))*[.!]*$"
)
_NEXT = re.compile(
    r"^(?:(?:yes|yeah|ok|okay)[ ,]+)?(?:let's |please )?(?:go to the |move to the |on to the )?"
    r"(?:next(?: step| page)?|continue|move on|proceed|aage (?:chalo|chaliye|badho))(?: please)?[.!]*$"
)

#: A sentence that says a value went into the form.
_CLAIM = re.compile(
    r"\b(?:noted|filled|entered|recorded|selected|marked|saved|updated|put (?:it|that|this) down|"
    r"added)\b",
    re.IGNORECASE,
)


def _said_list(names: Sequence[str]) -> str:
    said = [form.SAID.get(n, n) for n in names]
    return said[0] if len(said) == 1 else f"{', '.join(said[:-1])} and {said[-1]}"


# ─── The brain ──────────────────────────────────────────────────────────────

#: What a brain holds for one socket only: the session object and the speech
#: units waiting for the runtime to say what was heard. Everything else a call
#: built is carried to the brain a redial starts (rejoin.py).
_PER_SOCKET = frozenset({"_session", "_awaiting"})


class UniversityBrain(OpenAIBrain):
    """One per session: the job, the language, and the Stage director."""

    def __init__(self, *, client: AsyncOpenAI, model: str = MODEL) -> None:
        super().__init__(
            client=client,
            system_instruction=system_instruction(),
            model=model,
            reasoning=REASONING,
        )
        p = persona()
        self.lang: Lang = "hi" if p.default_language == "hi" else "en"
        self.path = "/"
        self.job: Job = "advisor"
        self.stage = Stage(
            dispatch=self._dispatch,
            moves=MOVES,
            resolve=self._resolve,
            mirror=Mirror(SPEC),
            on_drop=self._dropped,
            backstop=self._auto_cues,
        )
        #: The programme the conversation is about: what "show me that" opens.
        self.focus: str | None = None
        #: Programme pages opened (or asked to open) this turn, as (id, section):
        #: a second open of the same one, from a cue or the backstop, is not sent.
        self._opened: set[tuple[str, str | None]] = set()
        #: The application as this brain knows it (U2): the values it filled (and
        #: the non-personal ones the page reports), the step in front, the fill
        #: each pending ``apply.fill`` carries, the step it offered to move on
        #: from, and whether the boxes they type into were rung.
        self._form: dict[str, str] = {}
        self._step = 1
        self._fill_refs: dict[str, str] = {}
        #: Details given for a later step, filled when the form reaches it: a
        #: fill opens its own step, and the form must not jump ahead (U2).
        self._later: dict[str, str] = {}
        self._ready: int | None = None
        self._rung_typed = False
        #: This user turn: the form moved on already; something was filled.
        self._advanced = False
        self._filled = False
        #: They asked about admission: lead to the process and the application,
        #: never to a comparison (U2).
        self._admission = False
        #: The application as last told to the model, so a note goes only on a change.
        self._form_told: str | None = None
        self._fallback = FallbackLine()
        #: What the page asked the agent to say in the next quiet spell.
        self._talk: str | None = None
        #: The confirmation of a language switch, said at the start of the next turn.
        self._confirm: str | None = None
        #: The greeting a redialled brain returns, which the caller never hears:
        #: kept out of the model's history if it comes back finalized.
        self._unheard_greeting: str | None = None
        #: The visitor's last few turns, as heard: what an amount is checked against.
        self._heard_recent: list[str] = []
        #: Every amount spoken in the form the voice reads right (spoken.py, X8).
        self._spoken = SpokenAmounts(lambda: self.lang)

    # ─── Session ────────────────────────────────────────────────────────

    def _config(self, lang: Lang) -> Config:
        """Both legs in one language, in one request — never one without the other."""
        return Config(
            stt=SttConfig(language=lang, patience=PATIENCE),
            tts=TtsConfig(voice=persona().voices[lang], language=lang),
        )

    async def on_session_start(self, session: Session) -> None:
        """Both legs in the page's language, and the job from the landing page.

        A call outlives a dropped socket (CONTRACT.md, redial; SDK 0.15.0):
        redial is on wherever Voqalize offers it, and a brain started by a
        redial on a session this process still holds adopts that call as it
        was — the language, page and job it had moved to, the model's history,
        the Stage director and its screen mirror, a pending switch line —
        instead of starting over. The greeting a redialled brain returns is
        not spoken, and the call-start note is not added twice."""
        prior = REJOIN.take(session.id)
        rejoined = prior is not None and prior is not self
        if rejoined:
            assert prior is not None
            self._adopt(prior)
            logger.info("university: rejoined call {} after its socket dropped", session.id)
        else:
            init: dict[str, Any] = dict(session.init or {})
            lang = str(init.get("lang") or "")
            if lang in persona().languages and lang in ("en", "hi"):
                self.lang = "hi" if lang == "hi" else "en"
            self.path = route_of(str(init.get("landing") or "/"))
            self.job = job_for(self.path)
            if self.path.startswith("/programs/") and catalogue().program(self.path[10:]):
                self.focus = self.path[10:]
        REJOIN.hold(session.id, self)
        self._unheard_greeting = greeting(self.job, self.lang) if rejoined else None
        config = self._config(self.lang)
        await session.configure(
            Config(
                stt=config.stt,
                tts=config.tts,
                idle=IdleConfig(timeout_ms=_IDLE_MS),
                redial=RedialConfig(enabled=True) if session.can_redial else None,
            )
        )
        if not rejoined:
            self.append_note(f"[The call starts on {self.path}. {JOB_NOTE[self.job]}]")
            logger.info("university: start on {} as {} in {}", self.path, self.job, self.lang)

    async def on_session_end(self, session: Session) -> None:
        """The socket closed: a hang-up, or a drop Voqalize may redial. Kept a
        short while for the redial; runs at least once, and a second run (or
        one on a brain a redial already replaced) changes nothing."""
        REJOIN.dropped(session.id, self)

    def _adopt(self, prior: UniversityBrain) -> None:
        """Take over ``prior``'s call: every piece of state but its socket's.
        ``prior`` then shares this brain's state, so whatever still points at
        it — the Stage director's dispatch and drop hook, a pending
        ``configure_soon`` — acts on this call and this socket."""
        self.__dict__.update({k: v for k, v in prior.__dict__.items() if k not in _PER_SOCKET})
        prior.__dict__ = self.__dict__

    async def greet(self, session: Session) -> str:
        return speak_text(greeting(self.job, self.lang), self.lang)

    async def on_finalize(self, session: Session, fin: Finalize) -> None:
        """A redialled brain's greeting is not spoken (SDK 0.15.0): should a
        finalize for it come back anyway, the model does not read it as said —
        the call greeted once, on its first socket."""
        if self._unheard_greeting is not None and not self._awaiting:
            self._unheard_greeting = None
            return
        self._unheard_greeting = None
        await super().on_finalize(session, fin)

    async def switch_language(self, lang: Lang, why: str) -> None:
        """Both legs, awaited, and the page's toggle moved."""
        if lang == self.lang:
            return
        await self.session.configure(self._config(lang))
        self.lang = lang
        self.session.dispatch(LanguageChanged(language=lang))
        logger.info("university: language -> {} ({})", lang, why)

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[Speech, None]:
        self.stage.visitor_spoke()
        self._talk = None
        self._settle_expired()
        configure_soon(session, Config(idle=IdleConfig(timeout_ms=_IDLE_MS)))
        if self.lang != "hi" and sounds_hindi(msg.text):
            await self.switch_language("hi", "heard")
            self.append_note(
                "[They are speaking Hindi: the call is now in Hindi. Answer in Hindi.]"
            )
        self._heard_recent = [*self._heard_recent[-2:], msg.text]
        self._advanced = False
        self._filled = False
        moved = self._yes_moves_on(msg.text) if self.path == "/apply" else None
        if self.path == "/apply" and (note := self._form_note()) is not None and moved is None:
            self.append_note(note)
        # The turn is in the history once this returns; the model reads it lazily,
        # so a note added now comes right after the visitor's words.
        turn = super().on_user_message(session, msg)
        if (said := amounts_note(msg.text)) is not None:
            self.append_note(said)
        if moved is not None:
            self.append_note(moved)
        if self.path != "/apply" and _ADMISSION.search(msg.text):
            self._admission = True
            self.append_note(ADMISSION_NOTE)
        async for event in turn:
            yield event

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The model's turn: amounts written the way the voice reads them, cues
        taken out and sent to the page, a unit in Devanagari spoken by the Hindi
        legs, and a written line if it acted in silence."""
        if (line := self._confirm) is not None:
            self._confirm = None
            async for event in self.say_line(speak_text(line, self.lang)):
                yield event
        self._opened = set()
        record = _Turn()
        token = _TURN.set(record)
        try:
            # Amounts are rewritten for the voice before the cues come out, so a cue's
            # anchor words are the words the voice says (spoken.py).
            model = self._spoken.wrap(super().respond(session))
            cued = _counted(self.stage.cued(model), record)
            turn = self._fallback.speak_if_silent(self, self._scripted(session, cued))
            async for event in turn:
                yield event
            if record.owed is not None and record.starts == record.owed_at:
                # A read ran and nothing was said after it: the brain answers from
                # the data itself, never a promise and then silence (U1, as B1).
                logger.warning("university: a read went unanswered; saying {!r}", record.owed)
                if record.then is not None:
                    self._send(*record.then)
                async for event in self.say_line(speak_text(record.owed, self.lang), remember=True):
                    yield event
        finally:
            with contextlib.suppress(ValueError):
                _TURN.reset(token)
        for unkept in self.stage.end_turn():
            self._keep(unkept.move.id, unkept.sentence)
        self._claimed_unfilled(record.said)

    async def _scripted(
        self, session: Session, turn: AsyncGenerator[Speech, None]
    ) -> AsyncGenerator[Speech, None]:
        """``turn``, each unit opened once its first words are known, with both
        legs moved to Hindi first when they are Devanagari."""
        opening: SpeechStart | None = None
        try:
            async for event in turn:
                if isinstance(event, SpeechStart):
                    opening = event
                    continue
                if opening is not None:
                    if (
                        isinstance(event, SpeechChunk)
                        and self.lang != "hi"
                        and _DEVANAGARI.search(event.text)
                    ):
                        await self.switch_language("hi", "written")
                    yield opening
                    opening = None
                yield event
            if opening is not None:
                yield opening
        finally:
            await turn.aclose()

    # ─── Keeping what the voice promised on screen ──────────────────────

    def _dispatch(self, action: Action) -> None:
        """Every Stage move goes out here."""
        self.session.dispatch(action)

    def _send(self, move: str, args: dict[str, Any]) -> str | None:
        """A move a tool or the brain makes itself (not a cue in the speech)."""
        try:
            return self.stage.send(move, args, queue=False)
        except KeyError:
            logger.warning("university: no move {}", move)
            return None

    def _resolve(self, move: Move, args: list[str]) -> list[str] | None:
        """``resolve_cue``, and the programme in focus followed: a programme page
        the voice opens is what "show me that" means next."""
        out = resolve_cue(move, args)
        if out is not None and move.id == "apply.fill":
            self._filled = True
        if out is not None and move.id == "site.open":
            self.focus = out[0]
            self._opened.add((out[0], out[1] if len(out) > 1 else None))
        return out

    def _open(self, pid: str, section: str | None) -> bool:
        """Open a programme page at ``section`` unless this turn already did."""
        if (pid, section) in self._opened or (
            section is None and any(p == pid for p, _ in self._opened)
        ):
            return False
        self._opened.add((pid, section))
        self.focus = pid
        self._send("site.open", {"program": pid, "section": section})
        return True

    def _auto_cues(
        self, sentence: str, index: int, placed: tuple[tuple[str, tuple[str, ...]], ...]
    ) -> Sequence[AutoCue]:
        """The backstop under the model's cues, one finished sentence at a time.

        - A sentence that promises the screen ("I'll open the B.Tech CSE (AI & ML)
          page so you can see it", U1 turn 9) with no cue of its own opens the
          programme it names, or the one in focus, at the section it names.
        - On a programme page, a sentence about one of its sections ("The
          curriculum includes deep learning...") rings that section.
        - On the admissions page, a sentence about one of its sections rings it.
        A question is an offer, never a promise."""
        if placed or sentence.rstrip().endswith(("?", "\uff1f")):
            return ()
        here = self.path.removeprefix("/programs/") if self.path.startswith("/programs/") else None
        section = section_of(sentence)
        promised = bool(_PROMISE.search(sentence) and _PROMISE_VERB.search(sentence))
        target = _program_named(sentence) if promised else None
        target = target or (self.focus if promised else None)
        if target is not None and catalogue().program(target) is not None:
            if (target, section) in self._opened:
                return ()
            self._opened.add((target, section))
            self.focus = target
            logger.info("university: backstop opens {} at {} for {!r}", target, section, sentence)
            return [("open", [target, section] if section else [target])]
        # Pointing unasked: once a turn, at a section the sentence names outright,
        # and never after a tool or cue already put this page's section in view.
        named = section_named(sentence)
        if here is not None and named is not None and catalogue().program(here) is not None:
            if any(p == here for p, _ in self._opened):
                return ()
            self._opened.add((here, named))
            return [("open", [here, named])]
        if self.path == "/admissions" and (shown := _admissions_section(sentence)) is not None:
            if any(p == "/admissions" for p, _ in self._opened):
                return ()
            self._opened.add(("/admissions", shown))
            return [("show", [shown])]
        return ()

    def _keep(self, move_id: str, sentence: str) -> None:
        """A promise the turn made and nothing kept (the backstop missed it):
        a programme page is opened now; anything else is told to the model, so
        the next turn neither repeats the claim nor leaves it standing."""
        if move_id == "site.open" and self.focus is not None:
            logger.info("university: keeping {!r} by opening {}", sentence, self.focus)
            self._open(self.focus, section_of(sentence))
            return
        self.append_note(
            f'[You said "{sentence.strip()}" but nothing moved on their screen. Do it now '
            "with the cue or tool, or say plainly that you cannot.]"
        )

    # ─── The application, a step at a time (U2) ─────────────────────────

    def _known(self) -> set[str]:
        """The fields that hold something: as the page last reported them, and
        what this brain filled since (its fills are on their way)."""
        shown = self.stage.mirror.value("application") if self.stage.mirror else None
        return {str(f) for f in (shown or {}).get("filled") or []} | set(self._form)

    def _page_form(self, data: dict[str, Any]) -> None:
        """An ``application.*`` event folded into what this brain knows: the step
        in front, the non-personal values, and a field emptied on the page."""
        step = data.get("step")
        if isinstance(step, int):
            self._step = step
        for k, v in data.items():
            if application().field(k) is not None and v not in (None, ""):
                self._form[k] = str(v)
        filled = data.get("filled")
        if isinstance(filled, list):
            pending = set(self._fill_refs.values())
            for k in [k for k in self._form if k not in filled and k not in pending]:
                del self._form[k]

    def _fill(
        self, said: dict[str, str], *, defer: bool = True
    ) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
        """Fill every value said, in the form's order, each checked first (so a
        refusal is known now) and with what it implies (a city's state, a
        programme's intake). A value for a later step is kept for it (``defer``),
        never sent now: a fill opens its own step. Returns what was sent and
        what was refused, why."""
        filled: list[tuple[str, str]] = []
        refused: list[tuple[str, str]] = []
        known = self._known()
        queue = sorted(said.items(), key=lambda kv: form.order(kv[0]))
        i = 0
        while i < len(queue):
            raw_name, raw = queue[i]
            i += 1
            resolved = resolve_fill(raw_name, raw)
            if resolved is None:
                refused.append((raw_name, f"the application has no field {raw_name!r}"))
                continue
            name, value = resolved
            if name == "mobile":
                value = re.sub(r"[^\d+]", "", value)
            if defer and (application().step_of(name) or 0) > self._step:
                self._later[name] = value
                continue
            self._later.pop(name, None)
            focus = self._later.get("program") or self.focus
            if (why := form.check(name, value, self._form, focus)) is not None:
                refused.append((name, why))
                continue
            if name in known and self._form.get(name) == value:
                continue
            ref = self._send("apply.fill", {"field": name, "value": value})
            if ref is not None:
                self._fill_refs[ref] = name
            self._form[name] = value
            known.add(name)
            filled.append((name, value))
            self._step = application().step_of(name) or self._step
            extra = [(k, v) for k, v in form.implied(name, value, known).items() if k not in said]
            if extra:
                queue[i:] = sorted([*queue[i:], *extra], key=lambda kv: form.order(kv[0]))
        if filled:
            self._filled = True
            logger.info("university: filled {}", [n for n, _ in filled])
        if refused:
            logger.info("university: refused {}", refused)
        return filled, refused

    def _advance(self) -> tuple[bool, list[str], list[tuple[str, str]]]:
        """Move the form on from the step in front, when nothing it needs is
        empty: whether it moved, what is still empty, and what was filled on
        arriving (the programme in focus, on the programme step)."""
        if self._advanced:
            return True, [], []
        missing = form.needs(self._step, self._known(), self._form)
        if missing or self._step >= form.last_step():
            return False, missing, []
        self._send("apply.next", {})
        self._step += 1
        self._ready = None
        self._advanced = True
        logger.info("university: application on to step {}", self._step)
        due = {k: v for k, v in self._later.items() if application().step_of(k) == self._step}
        if self._step == 3 and "program" not in self._known() and self.focus is not None:
            due.setdefault("program", self.focus)
        auto, refused = self._fill(due) if due else ([], [])
        if refused:
            self.append_note(
                "[Kept from earlier and NOT filled: "
                + "; ".join(f"{form.SAID.get(n, n)}: {why}" for n, why in refused)
                + ". Ask for it again.]"
            )
        return True, [], auto

    def _ring_typed(self) -> None:
        """Ring the mobile and email boxes, once a call, for the applicant to type
        into themselves (X9)."""
        if self._rung_typed or self._step != 1:
            return
        todo = [f for f in form.TYPED if f not in self._known()]
        if not todo:
            return
        self._rung_typed = True
        for name in todo:
            self._send("site.show", {"target": name})

    def _yes_moves_on(self, text: str) -> str | None:
        """On /apply, "yes" to "shall we go to the next step?" (or "next") moves
        the form on now, in the brain, so it never waits on the model; the
        note for the model says where the form is and what to ask."""
        words = text.strip().lower()
        nxt = _NEXT.search(words) is not None
        yes = self._ready == self._step and _YES.match(words) is not None
        if not (yes or nxt):
            return None
        moved, missing, auto = self._advance()
        if not moved:
            if not missing:
                return None
            return (
                f"[They want to move on, but step {self._step} still needs: "
                f"{_said_list(missing)}. Ask for those (they type mobile and email "
                "themselves).]"
            )
        return f"[They said yes: {self._where(moved=True, auto=auto)}]"

    def _where(self, *, moved: bool, auto: list[tuple[str, str]]) -> str:
        """Where the form is now and the one question to ask next."""
        known = self._known()
        step = self._step
        parts = [
            f"{'the form moved on to' if moved else 'The form is on'} step {step} of "
            f"{form.last_step()}, {form.title(step)}, on their screen"
            + (" (write no next or step cue)." if moved else ".")
        ]
        if auto:
            parts.append(
                "Filled with it: "
                + "; ".join(f"{form.SAID[n]}: {form.said_value(n, v)}" for n, v in auto)
                + "."
            )
        parts.append(self._ask_line(step, known))
        return " ".join(parts)

    def _ask_line(self, step: int, known: set[str]) -> str:
        missing = form.needs(step, known, self._form)
        ask = form.ask_next(step, known | set(self._later), self._form, self.focus)
        typed = [f for f in form.TYPED if f in missing]
        if step == form.last_step() and not missing:
            return "Everything is filled: tell them to press the Pay button themselves."
        if not missing and not ask:
            self._ready = step
            return (
                f'Step {step} is complete. Ask: "If that looks right, shall we go to the next '
                'step?" On yes or "next", call fill_application with next_step true.'
            )
        out: list[str] = []
        if ask:
            out.append(f"Ask next, together in ONE natural question: {_said_list(ask)}.")
        if step == 4:
            out.append(
                "Documents: ask whether they will upload them now or later; for later, fill "
                "each document field with later in one call."
            )
        if typed:
            out.append(
                f"Their {_said_list(typed)}: ask them to type it themselves in the box ringed "
                "on screen; never ask them to say it or confirm it."
            )
        if not ask and not typed and missing:
            out.append(f"Still empty on this step: {_said_list(missing)}.")
        return " ".join(out)

    def _form_note(self) -> str | None:
        """On /apply, what the form holds and still needs, when it changed since
        the model was last told: the next group of details to ask together,
        and never again what is filled (insurance I1, U2)."""
        known = self._known()
        filled = sorted(known, key=form.order)
        text = (
            f"[The application is on step {self._step} of {form.last_step()}, "
            f"{form.title(self._step)}. Filled: {', '.join(filled) or 'nothing yet'}. "
            "Never ask again for anything filled; fill what they say with fill_application. "
            + self._ask_line(self._step, known)
            + "]"
        )
        if text == self._form_told:
            return None
        self._form_told = text
        return text

    def _claimed_unfilled(self, said: list[str]) -> None:
        """On /apply, a turn that said it filled something and filled nothing
        (the owner's call: "Passed, noted." with an empty form) is told so."""
        if self.path != "/apply" or self._filled:
            return
        for sentence in re.split(r"(?<=[.!])\s+", "".join(said)):
            if _CLAIM.search(sentence) and not sentence.rstrip().endswith("?"):
                logger.warning("university: claimed a fill and filled nothing: {!r}", sentence)
                self.append_note(
                    f'[You said "{sentence.strip()}" but nothing was filled this turn: it is NOT '
                    "on their form. Fill it now with fill_application, never say it is filled "
                    "otherwise.]"
                )
                return

    def on_user_idle(self, session: Session, idle: UserIdle) -> AsyncGenerator[Speech, None]:
        return self._idle(session)

    async def _idle(self, session: Session) -> AsyncGenerator[Speech, None]:
        """A quiet spell: spoken into only when the page left something to say
        (the applicant submitted). A family reading the screen is not nudged."""
        self._settle_expired()
        configure_soon(session, Config(idle=IdleConfig(timeout_ms=_IDLE_MS)))
        ask, self._talk = self._talk, None
        if ask is None and self._confirm is None:
            return
        if ask is not None:
            self.append_note(f"[{ask}]")
        async for event in self.respond(session):
            yield event

    # ─── The page ───────────────────────────────────────────────────────

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        event = _EVENTS.parse(msg)
        if event is None:
            return
        if isinstance(event, LanguageRequested):
            lang: Lang = event.language
            if lang != self.lang:
                await self.switch_language(lang, "toggle")
                self._confirm = SWITCHED[lang]
                self.append_note(
                    f"[The visitor switched the call to {persona().language_names[lang]} "
                    "on the page. Answer in it from now on.]"
                )
                configure_soon(session, Config(idle=IdleConfig(timeout_ms=_REACT_IDLE_MS)))
            return
        note = self._staged(event)
        if note is not None:
            logger.info("university: page {}", note)
            self.append_note(note)

    def _staged(self, event: StageResult | StageHello | StageProgress | StageEvent) -> str | None:
        """One answer from the page, folded in; the line the model reads, if any."""
        if isinstance(event, StageHello):
            self.stage.handle(event)
            path = route_of(event.url) if event.url else self.path
            if path == self.path:
                return None
            self.path = path
            if path.startswith("/programs/") and catalogue().program(path[10:]) is not None:
                self.focus = path[10:]
            if path == "/apply":
                self._admission = False
                self._ring_typed()
            job = job_for(path)
            if job == self.job:
                return f"[They are now on {path}.]"
            self.job = job
            return f"[They are now on {path}. {JOB_NOTE[job]}]"
        if isinstance(event, StageProgress):
            self.stage.handle(event)
            return None
        if isinstance(event, StageEvent):
            folded = self.stage.handle(event)
            if event.name.startswith("application."):
                self._page_form(event.data)
            if folded is None:
                return None
            if event.by == "visitor" and (ask := self.stage.take_reaction()):
                self._talk = ask
                configure_soon(self.session, Config(idle=IdleConfig(timeout_ms=_REACT_IDLE_MS)))
            return folded.note if event.by == "visitor" else None
        result = self.stage.handle(event)
        field = self._fill_refs.pop(event.call_ref, None)
        if field is not None and event.outcome not in ("applied", "partial"):
            # The page refused a fill: it is not on the form, whatever was sent.
            self._form.pop(field, None)
        return None if result is None else self._settle(result)

    def _settle(self, result: StageResult) -> str | None:
        """A move that landed needs no line: the voice already said it. One
        that did not is told plainly, with what the page offers instead."""
        if result.moved or result.outcome in ("applied", "partial", "undone"):
            return None
        offers = "; ".join(
            f"{r.arg}: {r.why}" + (f" (options: {', '.join(r.options)})" if r.options else "")
            for r in result.refused
        )
        return (
            f"[Your {result.move} cue did not land ({result.detail or result.outcome}"
            + (f"; {offers}" if offers else "")
            + "). Never say it did; use one of the options, or ask.]"
        )

    def _settle_expired(self) -> None:
        for result in self.stage.expire():
            if (note := self._settle(result)) is not None:
                self.append_note(note)

    def _dropped(self, cue: RawCue, why: Dropped) -> None:
        logger.info("university: dropped {{{}: {}}} ({})", cue.verb, " | ".join(cue.args), why)
        if why == "unresolved":
            self.append_note(
                f"[Your {{{cue.verb}: {' | '.join(cue.args)}}} cue named nothing the page has, "
                "so nothing moved. Use the labels and ids from your instructions.]"
            )

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        return [
            self.find_programs,
            self.program_details,
            self.compare_programs,
            self.check_eligibility,
            self.fill_application,
            self.read_screen,
            self.set_language,
        ]

    def _check_amounts(self, **values: float | None) -> str | None:
        """A tool's guard on the amounts it was given: one no family would mean (a ₹15
        budget, a mis-heard "one and a half lakh") is confirmed back, never used (X8)."""
        return implausible(values, self._heard_recent[::-1])

    @needs_result_now
    async def find_programs(self, request: FindRequest) -> str:
        """Match what the learner said to the catalogue: the programmes that fit,
        best first, with the finder filters to tick as you explain. Call it as
        soon as you know two or three of level, interests, budget, hours, mode."""
        if (why := self._check_amounts(max_fee_per_year=request.max_fee_per_year)) is not None:
            return why
        profile = Profile(
            level=request.level,
            school=request.school,
            interests=request.interests,
            mode=request.mode,
            campus=request.campus,
            max_fee_per_year=request.max_fee_per_year,
            hours_per_week=request.hours_per_week,
        )
        found = matches(profile)
        logger.info("university: find {} -> {}", profile, len(found))
        shown = self.stage.mirror.value("catalogue") if self.stage.mirror else None
        ticked = [str(f) for f in (shown or {}).get("filters") or []]
        picks = [str(p) for p in (shown or {}).get("picks") or []]
        if found:
            owe(self._found_line(profile, found))
        text = find_text(profile, ticked, picks)
        if self._admission and found:
            text += (
                "\nBut they asked about ADMISSION, not a choice between programmes: name the ONE "
                "that fits what they said with {pick: id}, then {open: id | selection} as you say "
                "how admission works for it (one or two sentences from its facts), and offer to "
                "start the application now. Do not offer a comparison."
            )
        return text

    def _found_line(self, profile: Profile, found: list[Any]) -> str:
        """What the brain says if the model says nothing after find_programs."""
        c = catalogue()
        if self.lang == "hi":
            return f"आपकी screen पर {len(found)} programmes हैं। इनमें से आपको किसमें सबसे ज़्यादा रुचि है?"
        if profile.school is None and not profile.interests.strip():
            areas = ", ".join(dict.fromkeys(c.school(p.school).short for p in found))
            return f"We have programmes in {areas}. Which area interests you most?"
        names = ", ".join(p.name for p in found[:3])
        if self._admission:
            return (
                f"{found[0].name} is the closest fit. Shall I show you how admission works for "
                "it and start your application?"
            )
        return f"The closest fits are {names}. Shall I compare them, or open one of them?"

    @needs_result_now
    async def program_details(self, request: ProgramRequest) -> str:
        """One programme's facts, with its page opened on their screen at the part
        they asked about: "show me the curriculum of …", "what are the fees for
        this?", "tell me about B.Tech CSE". Every authored fact comes back:
        fees, eligibility, selection, deadlines, scholarships, outcomes, modules."""
        pid = resolve_program(request.program)
        p = catalogue().program(pid) if pid else None
        if p is None:
            return f"No programme called {request.program!r}. Use an id from the catalogue."
        section = None if request.section == "overview" else request.section
        self._open(p.id, section)
        where = f"at its {request.section}" if section else "at the top"
        owe(self._details_line(p, request.section))
        return (
            f"Their screen now shows {p.name}'s page {where} (write no open cue for it).\n"
            f"What they asked about: {section_text(p, request.section)}\n"
            f"Everything else about it:\n{program_text(p)}\n"
            "Answer what they asked in one to three sentences from this, in your own words, then "
            "offer the one next step that helps them decide (fees and scholarships, eligibility "
            "with their marks, outcomes, comparing, applying), as a question."
        )

    def _details_line(self, p: Any, section: str) -> str:
        """What the brain says if the model says nothing after program_details."""
        if self.lang == "hi":
            return f"{p.name} आपकी screen पर है। आगे fees देखें या scholarship?"
        fact = section_text(p, section).rstrip(".")
        nxt = (
            "Shall I check which scholarship you could get?"
            if section in ("fees", "scholarships")
            else "Shall I show you the fees and scholarships next?"
        )
        return f"Here is {p.name} on your screen. {fact}. {nxt}"

    @needs_result_now
    async def compare_programs(self, request: CompareRequest) -> str:
        """The facts of two or three programmes side by side, row by row, to talk
        through while the comparison is on screen ({compare: a | b})."""
        c = catalogue()
        found = [c.program(pid) for pid in (resolve_program(x) for x in request.programs) if pid]
        progs = [p for p in found if p is not None][:3]
        if len(progs) < 2:
            return "Name two or three programme ids from the catalogue to compare."
        ids = [p.id for p in progs]
        owe(
            "Here they are side by side on your screen. Which one would you like to look at "
            "more closely?"
            if self.lang == "en"
            else "ये आपकी screen पर साथ-साथ हैं। किसे और करीब से देखना चाहेंगे?",
            then=(
                "catalogue.compare",
                {"first": ids[0], "second": ids[1], "third": ids[2] if len(ids) > 2 else None},
            ),
        )
        return compare_text(progs)

    @needs_result_now
    async def check_eligibility(self, request: EligibilityRequest) -> str:
        """Whether an applicant meets a programme's published eligibility, and the
        scholarship they would get from what they have told you, with the yearly
        fee after it."""
        pid = resolve_program(request.program)
        p = catalogue().program(pid) if pid else None
        if p is None:
            return f"No programme called {request.program!r}. Use an id from the catalogue."
        if (why := self._check_amounts(family_income_lakh=request.family_income_lakh)) is not None:
            return why
        text = eligibility_text(
            p,
            Applicant(
                class12_stream=request.class12_stream,
                class12_percent=request.class12_percent,
                graduation_percent=request.graduation_percent,
                experience_years=request.experience_years,
                vusat_rank=request.vusat_rank,
                family_income_lakh=request.family_income_lakh,
                gender=request.gender,
                sports=request.sports,
                defence_family=request.defence_family,
            ),
        )
        verdict, _, scholarship = text.partition("\n")
        owe(
            f"For {p.name}: {verdict.split(': ', 1)[-1]} {scholarship}"
            if self.lang == "en"
            else f"{p.name} के लिए मैंने आपकी eligibility check कर ली है। क्या मैं पूरा हिसाब बताऊँ?"
        )
        return text

    @needs_result_now
    async def fill_application(self, request: FillRequest) -> str:
        """Fill the application on their screen with every detail they just gave,
        all at once, and move it to the next step when they say yes or "next".
        Returns what was filled, what the form refused and why, and what to ask
        next. Call it the moment they give details, before you say anything."""
        said: dict[str, str] = {}
        for v in request.values:
            said[v.field] = v.value
        held = set(self._later)
        filled, refused = self._fill(said) if said else ([], [])
        kept = [n for n in self._later if n not in held]
        moved, missing, auto = (False, [], [])
        ahead = kept and min(application().step_of(n) or 0 for n in kept) == self._step + 1
        if request.next_step or (
            # Answering the next step's question is a yes to moving on, when this
            # step has everything it needs (the real-model check: "Bengaluru, and a
            # hostel" said to "shall we go to the next step?").
            ahead and not form.needs(self._step, self._known(), self._form)
        ):
            moved, missing, auto = self._advance()
            kept = [n for n in kept if n in self._later]
        self._ring_typed()
        lines: list[str] = []
        if filled or auto:
            lines.append(
                "Filled on their screen now: "
                + "; ".join(f"{form.SAID[n]}: {form.said_value(n, v)}" for n, v in [*filled, *auto])
                + "."
            )
        if refused:
            lines.append(
                "NOT filled (say so plainly and ask again; for mobile or email, ask them to type "
                "it in the box): "
                + "; ".join(f"{form.SAID.get(n, n)}: {why}" for n, why in refused)
                + "."
            )
        if kept:
            lines.append(
                f"Kept for a later step (it goes in when the form gets there; do not ask for it "
                f"again): {_said_list(sorted(kept, key=form.order))}."
            )
        if request.next_step and not moved and missing:
            lines.append(
                f"It cannot move on yet: step {self._step} still needs {_said_list(missing)}."
            )
        lines.append(self._where(moved=moved, auto=[]))
        lines.append(
            "Say in one short sentence what you filled (never read back a mobile number or "
            "email, never ask them to confirm one), then the question above. Write no fill or "
            "next cue: the tool did it."
        )
        owe(self._filled_line(filled + auto, refused, moved))
        return "\n".join(lines)

    def _filled_line(
        self, filled: list[tuple[str, str]], refused: list[tuple[str, str]], moved: bool
    ) -> str:
        """What the brain says if the model says nothing after fill_application."""
        known = self._known()
        if self.lang == "hi":
            if refused:
                return f"{_said_list([n for n, _ in refused])} नहीं भर पाया, क्या आप दोबारा बताएँगे?"
            return "मैंने form में भर दिया है। अगर सब सही है, तो क्या अगले step पर चलें?"
        head = (
            f"I've filled in your {_said_list([n for n, _ in filled])}."
            if filled
            else f"We're on step {self._step}, {form.title(self._step)}."
        )
        if refused:
            return f"{head} I couldn't fill your {_said_list([n for n, _ in refused])}: could you give it again?"
        if not form.needs(self._step, known, self._form) and self._step < form.last_step():
            self._ready = self._step
            return f"{head} If that looks right, shall we go to the next step?"
        ask = form.ask_next(self._step, known | set(self._later), self._form, self.focus)
        return f"{head} Could you tell me your {_said_list(ask)}?" if ask else head

    @needs_result_now
    async def read_screen(self, request: ReadRequest) -> str:
        """What their screen shows now: the programme finder or the application."""
        assert self.stage.mirror is not None
        return self.stage.mirror.read(request.slice)

    async def set_language(self, request: LanguageRequest) -> str:
        """Conduct the rest of the call in English or Hindi, listening and
        speaking. Call it when they ask for the other language; say one short
        line in the language they asked for, in the same response."""
        lang: Lang = request.language
        if lang == self.lang:
            return f"The call is already in {persona().language_names[lang]}."
        # Sent, not awaited: a tool returns within its budget.
        configure_soon(self.session, self._config(lang))
        self.lang = lang
        self.session.dispatch(LanguageChanged(language=lang))
        logger.info("university: language -> {} (asked)", lang)
        landed(SWITCHED[lang])
        return f"The call is now in {persona().language_names[lang]}."


#: Live calls by session id, for a redial to rejoin (rejoin.py).
REJOIN: Rejoin[UniversityBrain] = Rejoin()


__all__ = [
    "REJOIN",
    "LanguageChanged",
    "LanguageRequested",
    "UniversityBrain",
    "resolve_cue",
    "route_of",
    "sounds_hindi",
]
