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
"""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator
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
from voqalize.sdk.stage import Dropped, Mirror, Move, RawCue, Stage, match_label
from voqalize.sdk.stage.wire import StageEvent, StageHello, StageProgress, StageResult
from voqalize.sdk.wire import Config, IdleConfig, RedialConfig, SttConfig, TtsConfig

from .data import CampusId, Level, Mode, SchoolId, Stream, application, catalogue, persona
from .finder import (
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
)
from .prompt import JOB_NOTE, Job, Lang, greeting, job_for, system_instruction
from .rejoin import Rejoin
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
    max_fee_per_year: int | None = Field(None, description="Their budget a year, in rupees.")
    hours_per_week: int | None = Field(
        None,
        description="Hours a week they can give; under 16 rules out full-time programmes.",
    )


class ProgramRequest(BaseModel):
    program: str = Field(description="A programme id from the catalogue, or its name.")


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
    family_income_lakh: float | None = Field(None, description="Annual family income in lakh.")
    gender: Literal["female", "male", "other"] | None = None
    sports: Literal["national", "state"] | None = Field(
        None, description="The level of a sports medal in the last three years."
    )
    defence_family: bool = False


class LanguageRequest(BaseModel):
    language: Literal["en", "hi"]


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
            return [pid] if pid else None
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
            dispatch=lambda a: self.session.dispatch(a),
            moves=MOVES,
            resolve=resolve_cue,
            mirror=Mirror(SPEC),
            on_drop=self._dropped,
        )
        self._fallback = FallbackLine()
        #: What the page asked the agent to say in the next quiet spell.
        self._talk: str | None = None
        #: The confirmation of a language switch, said at the start of the next turn.
        self._confirm: str | None = None
        #: The greeting a redialled brain returns, which the caller never hears:
        #: kept out of the model's history if it comes back finalized.
        self._unheard_greeting: str | None = None

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
        return greeting(self.job, self.lang)

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
        async for event in super().on_user_message(session, msg):
            yield event

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The model's turn: cues taken out and sent to the page, a unit in
        Devanagari spoken by the Hindi legs, and a written line if it acted in
        silence."""
        if (line := self._confirm) is not None:
            self._confirm = None
            async for event in self.say_line(line):
                yield event
        turn = self._fallback.speak_if_silent(
            self, self._scripted(session, self.stage.cued(super().respond(session)))
        )
        async for event in turn:
            yield event
        self.stage.end_turn()

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
            if folded is None:
                return None
            if event.by == "visitor" and (ask := self.stage.take_reaction()):
                self._talk = ask
                configure_soon(self.session, Config(idle=IdleConfig(timeout_ms=_REACT_IDLE_MS)))
            return folded.note if event.by == "visitor" else None
        result = self.stage.handle(event)
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
            self.read_screen,
            self.set_language,
        ]

    @needs_result_now
    async def find_programs(self, request: FindRequest) -> str:
        """Match what the learner said to the catalogue: the programmes that fit,
        best first, with the finder filters to tick as you explain. Call it as
        soon as you know two or three of level, interests, budget, hours, mode."""
        profile = Profile(
            level=request.level,
            school=request.school,
            interests=request.interests,
            mode=request.mode,
            campus=request.campus,
            max_fee_per_year=request.max_fee_per_year,
            hours_per_week=request.hours_per_week,
        )
        logger.info("university: find {} -> {}", profile, len(matches(profile)))
        return find_text(profile)

    @needs_result_now
    async def program_details(self, request: ProgramRequest) -> str:
        """Every authored fact about one programme: fees, eligibility, selection,
        deadlines, scholarships, outcomes, modules."""
        pid = resolve_program(request.program)
        p = catalogue().program(pid) if pid else None
        if p is None:
            return f"No programme called {request.program!r}. Use an id from the catalogue."
        return program_text(p)

    @needs_result_now
    async def compare_programs(self, request: CompareRequest) -> str:
        """The facts of two or three programmes side by side, row by row, to talk
        through while the comparison is on screen ({compare: a | b})."""
        c = catalogue()
        found = [c.program(pid) for pid in (resolve_program(x) for x in request.programs) if pid]
        progs = [p for p in found if p is not None][:3]
        if len(progs) < 2:
            return "Name two or three programme ids from the catalogue to compare."
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
        return eligibility_text(
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
