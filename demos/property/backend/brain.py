"""PropertyBrain — the Kosha Homes property guide and site-visit booker.

An :class:`~voqalize.sdk.openai.OpenAIBrain`. One brain, two jobs, picked by the
page the call starts on and followed as the visitor moves: on the home page,
the listings and the project pages the agent is the **guide** (narrows the
listings from what the buyer says, compares two homes, works out an EMI); on a
listing's page it is the **visit booker** (finds a slot that suits the buyer and
the project's sales team, and books it once the buyer says yes).

Every move on screen is a Stage move (``frontend/src/stage/scene.json``): the
tools send them with :meth:`Stage.send`, and the ``{show: <id>}`` cue rings a
home as the voice reaches the sentence about it. The page reports what the
visitor does as Stage events, folded into the brain's own state (the search,
the shortlist, the page in front, the slots taken).

Every number comes from ``data/homes.json`` and the shared rules in
:mod:`.homes`. Everything the agent says, the model's words and its own lines,
reaches the voice through :mod:`.spoken`, which rewrites the amounts the voice
still reads wrong (a range with the scale said once, Hindi decimals); a
budget the buyer said is read back to the model in rupees, and one no buyer
would mean is confirmed before the search uses it (FEEDBACK X8).

**One model request a turn (K0 R4).** Searching, opening a home, comparing,
the EMI, the free slots and holding a visit are actions, not reads: the model
says a few words of lead-in and calls the tool, and the brain says the result in
its own written line (:data:`.lines.SAID`) straight after, in the same turn
(``say``). They used to wait for their result, a second model request of 2 to
10 seconds on nearly every turn; the model now reads the result with the
buyer's next message. Only ``home_facts`` (a specific question about a home)
and ``read_screen`` still wait. The budget on screen is always the one the
buyer said: an "around" answer up to 10% over it, or the nearest home when
nothing fits, is offered in words and never widens the filter. The character — name, voice per language, the languages offered
and the default — comes from ``persona.json`` (:mod:`.persona`).
"""

from __future__ import annotations

import contextlib
import re
from collections.abc import AsyncGenerator, Callable
from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import date
from typing import Any, Literal

from loguru import logger
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from voqalize_demos import PATIENCE, FallbackLine, configure_soon, landed, needs_result_now

from voqalize.sdk import (
    Action,
    AppEvent,
    AppEvents,
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
from voqalize.sdk.stage import Mirror, Move, Refused, Stage, match_label
from voqalize.sdk.stage.wire import StageEvent, StageHello, StageProgress, StageResult
from voqalize.sdk.wire import Config, IdleConfig, RedialConfig, SttConfig, TtsConfig

from . import homes as h
from .lines import (
    ASK,
    BOOKING,
    BRING_SHORT,
    EDGE,
    GREETING,
    HI_DAYS,
    HI_MONTHS,
    HI_PARTS,
    LANDED,
    MISSES,
    NO_WORDS,
    NUDGE,
    OWED,
    SAID,
    WHO,
    WHY,
    YES_WORDS,
)
from .persona import PERSONA, Persona
from .prompt import system_instruction
from .rejoin import Rejoin
from .spoken import (
    SpokenAmounts,
    amounts_note,
    confirm_back,
    implausible,
    parse_amounts,
    speak_text,
)
from .stage_gen import MOVES as STAGE_MOVES
from .stage_gen import SPEC, ReadRequest

MODEL = "gpt-6.1-terra"
REASONING = "medium"

#: The quiet spell before the agent may speak up by itself, and how short it gets
#: while it has a line to say (a booking's outcome, a visitor's booking).
_IDLE_MS = 15000
_SAY_NOW_MS = 400
_REACT_IDLE_MS = 1500

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")

Job = Literal["guide", "booker"]

for _table in (
    *LANDED.values(),
    *GREETING.values(),
    *BOOKING.values(),
    *OWED.values(),
    *WHO.values(),
):
    assert set(PERSONA.languages) <= set(_table), "a persona language has no written line"

#: A phone number said aloud: never used, never repeated (X9).
_SPOKEN_PHONE = re.compile(r"(?:\d[\s-]?){7,}")

#: The questions that narrow the homes, in the order a good adviser asks them:
#: (topic, the search field that answers it, how the tool names it to the model).
_TOPICS: tuple[tuple[str, str, str], ...] = (
    ("deal", "deal", "whether they want to buy or rent"),
    ("city", "city", "which city"),
    ("budget", "budget_max", "their budget"),
    ("bhk", "bhk", "how many bedrooms"),
    ("office", "office", "where they work, so the commute is short"),
    ("possession", "possession", "ready to move, or is under construction fine"),
    ("school", "school_km", "whether a good school nearby matters"),
)


@dataclass
class _Owed:
    """One turn's record: how many units of the model's speech went out and what
    they said, and the brain's own line the turn ends on.

    A read (``owe``) owes its written answer only if nothing is said after it
    ran. A step the brain answers itself (``say``, K0 R4) always ends on its
    line: the model said only its few words of lead-in before the call, and the
    turn needs no second model request. ``bare`` is that line without the
    buyer's name, said instead when the model's words already used ``name``."""

    starts: int = 0
    text: str = ""
    line: str | None = None
    at: int = 0
    always: bool = False
    bare: str | None = None
    name: str | None = None

    def floor(self) -> str | None:
        """What the brain says after the model's turn, if anything."""
        if self.line is None:
            return None
        if self.always:
            if self.bare is not None and self.name and self.name in self.text:
                return self.bare
            return self.line
        return self.line if self.starts == self.at else None


async def _counted(
    turn: AsyncGenerator[Speech, None], record: _Owed
) -> AsyncGenerator[Speech, None]:
    """The model's turn, each unit of its speech counted."""
    try:
        async for s in turn:
            if isinstance(s, SpeechStart):
                record.starts += 1
            elif isinstance(s, SpeechChunk):
                record.text += s.text
            yield s
    finally:
        await turn.aclose()


#: Per turn, like ``landed``'s record: each turn runs in its own task.
_OWED: ContextVar[_Owed | None] = ContextVar("property_owed", default=None)


def owe(line: str) -> None:
    """Beside a read whose answer the buyer is waiting for (the homes that fit,
    an EMI, a comparison): the written answer, said by the brain when the model's
    turn says nothing after the tool ran. "Let me narrow that down" followed by
    silence is the gap this closes (the turn's opening line alone does not count)."""
    if (record := _OWED.get()) is not None:
        record.line = line
        record.at = record.starts
        record.always = False
        record.bare = record.name = None


def say(line: str, *, bare: str | None = None, name: str | None = None) -> None:
    """Beside a step the brain answers itself: the line the turn ends on, said
    straight after the model's few words, whatever they were (K0 R4: no second
    model request). The last step of a turn wins. ``bare``: the same line
    without ``name``, for when the model already said the name (never twice)."""
    if (record := _OWED.get()) is not None:
        record.line = line
        record.at = record.starts
        record.always = True
        record.bare = bare
        record.name = name


class LanguageChanged(Action):
    """The call's language moved: the page's EN / हिंदी toggle follows."""

    language: str


class LanguageRequested(AppEvent):
    """The visitor pressed the other language on the call tile's EN / हिंदी
    toggle mid-call."""

    language: str = "en"
    by: str = "visitor"


_EVENTS = AppEvents(LanguageRequested, StageResult, StageHello, StageProgress, StageEvent)


# ─── Tool parameters ──────────────────────────────────────────────────────────


class SearchRequest(BaseModel):
    """What the buyer asked for. Only what changed; the rest of the search is kept."""

    city: Literal["bengaluru", "pune", "hyderabad"] | None = None
    deal: Literal["buy", "rent"] | None = None
    bhk: list[int] | None = Field(default=None, description="Bedroom counts, e.g. [2, 3].")
    budget_min: int | None = Field(default=None, description="Rupees; monthly rent when renting.")
    budget_max: int | None = Field(default=None, description="Rupees; monthly rent when renting.")
    possession: Literal["ready", "under_construction"] | None = None
    localities: list[str] | None = Field(default=None, description="Locality names.")
    office: str | None = Field(
        default=None,
        description="Where they work: an office id, its name, or the area they named (Whitefield).",
    )
    max_km: float | None = Field(default=None, description="Most km from the office.")
    school_km: float | None = Field(default=None, description="A school within this many km.")
    metro_km: float | None = Field(default=None, description="Metro within this many km.")
    amenities: list[str] | None = None
    around: bool = Field(
        default=False,
        description="They said about/around/roughly/lagbhag the budget: a home up to 10% over it may be offered.",
    )
    clear: list[str] | None = Field(
        default=None, description="Fields to unset, e.g. ['localities', 'budget_max']."
    )
    reset: bool = Field(default=False, description="Start the search over first.")


class ListingRef(BaseModel):
    listing_id: str = Field(description="A listing id, BLR-104.")


class CompareRequest(BaseModel):
    listing_ids: list[str] = Field(description="Two or three listing ids.")


class EmiRequest(BaseModel):
    listing_id: str
    also: list[str] | None = Field(
        default=None, description="Other listing ids to compare EMIs with, on the same terms."
    )
    down_pct: float | None = Field(default=None, description="Down payment, percent of price.")
    tenure_years: int | None = None
    lender: str | None = Field(default=None, description="Lender id.")


class ShortlistRequest(BaseModel):
    listing_id: str
    on: bool = True


class PageRequest(BaseModel):
    page: str = Field(
        description="/ , /listings, /shortlist, /visits, /compare, or /project/<project id>."
    )


class SlotsRequest(BaseModel):
    listing_id: str
    day: str | None = Field(
        default=None,
        description="YYYY-MM-DD, a weekday name (saturday), tomorrow or weekend. Empty: the week.",
    )
    part: Literal["morning", "afternoon", "evening", "any"] = "any"


class ProposeRequest(BaseModel):
    listing_id: str
    slot: str = Field(description="A free slot id, YYYY-MM-DDTHH:MM, from visit_slots.")
    name: str = Field(description="The buyer's name as they said it.")
    visitors: int = Field(default=1, description="How many people are coming.")


class BookRequest(BaseModel):
    buyer_said_yes: bool = Field(description="True only when they just said yes to the booking.")


class LanguageRequest(BaseModel):
    language: Literal["english", "hindi"]


@dataclass
class Proposal:
    listing_id: str
    slot: str
    name: str
    visitors: int
    turn: int


def _yes_no(text: str) -> Literal["yes", "no"] | None:
    # The danda (।, ॥) sits inside the Devanagari block: a Hindi "हाँ।" is a yes too.
    t = " " + re.sub(r"[^\wऀ-ॿ ]|[।॥]", " ", text.lower()) + " "
    if any(f" {w} " in t for w in NO_WORDS):
        return "no"
    if any(f" {w} " in t for w in YES_WORDS):
        return "yes"
    return None


def _job_of(path: str) -> tuple[Job, str | None]:
    m = re.match(r"^/listing/([A-Za-z]{3}-\d+)", path)
    if m:
        return "booker", m.group(1).upper()
    return "guide", None


def _canonical(path: str) -> str:
    """The route under the app's base, without query or trailing slash."""
    p = path.split("?", 1)[0].split("#", 1)[0]
    p = re.sub(r"^/demos/property", "", p) or "/"
    return p.rstrip("/") or "/"


#: What a brain holds for one socket only: the session object and the speech
#: units waiting for the runtime to say what was heard. Everything else a call
#: built is carried to the brain a redial starts (rejoin.py).
_PER_SOCKET = frozenset({"_session", "_awaiting"})


class PropertyBrain(OpenAIBrain):
    """One per session: the job, the search, the shortlist and the visit being booked."""

    def __init__(
        self, *, client: AsyncOpenAI, model: str = MODEL, persona: Persona = PERSONA
    ) -> None:
        super().__init__(
            client=client,
            system_instruction=system_instruction(persona),
            model=model,
            reasoning=REASONING,
        )
        self.persona = persona
        self.lang = persona.default_language
        self.path = "/"
        self.job: Job = "guide"
        self.listing_id: str | None = None
        self.search = h.Search()
        #: The search as the buyer asked for it, which is also exactly what the
        #: screen shows: an answer that offers a home over the budget or past a
        #: limit never widens the filter, and the next search starts from this.
        self.wanted = h.Search()
        #: They said their budget with "around": the answer may offer a home up to
        #: 10% over it when nothing is at it (the screen still shows the budget).
        self.around = False
        self._nudges = 0
        self.results: list[str] = [x["id"] for x in h.search(self.search)]
        self.shortlisted: list[str] = []
        self.taken: set[str] = set()  # "<host key>|<slot id>": a host can be in one place at once
        self.booked: dict[str, Proposal] = {}  # reference → booking
        self.pending: Proposal | None = None
        #: The visitor typed a mobile number on the visit form (the page says so;
        #: the number itself never reaches the brain, X9).
        self.phone_typed = False
        #: The questions the guide was already pointed at: never asked twice.
        self.asked: set[str] = set()
        self.turns = 0
        self._flights: dict[str, Proposal] = {}  # visit.book call_ref → booking
        self._say_next: Callable[[], str] | None = None
        self._talk: str | None = None
        self.stage = Stage(
            dispatch=lambda a: self.session.dispatch(a),
            moves=STAGE_MOVES,
            resolve=self._resolve,
            mirror=Mirror(SPEC),
        )
        self._fallback = FallbackLine()
        #: Every amount spoken in the form the voice reads right (spoken.py, X8).
        self._spoken = SpokenAmounts(lambda: self.lang)
        #: The buyer's last few turns, as heard: what a budget is checked against.
        self._heard_recent: list[str] = []
        # This socket's brain took over a call a dropped socket left (rejoin.py).
        self._rejoined = False

    # ─── Session ────────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        """The persona's voice for the call's language on both legs, and the job
        from the page the call started on.

        A call outlives a dropped socket (CONTRACT.md, "Redial"; SDK 0.15.0):
        redial is on wherever Voqalize offers it, and a brain started by a
        redial on a session this process still holds adopts that call as it
        was — the language and the page it had moved to included — instead of
        starting over. Its greeting is not spoken."""
        prior = REJOIN.take(session.id)
        self._rejoined = False
        if prior is not None and prior is not self:
            self._adopt(prior)
            self._rejoined = True
            logger.info("property: rejoined call {} after its socket dropped", session.id)
        else:
            init = session.init or {}
            self.lang = self.persona.tag(str(init.get("lang") or init.get("language") or ""))
            self._at(_canonical(str(init.get("page") or "/")))
        REJOIN.hold(session.id, self)
        await session.configure(
            Config(
                stt=SttConfig(language=self.persona.language(self.lang), patience=PATIENCE),
                tts=TtsConfig(
                    voice=self.persona.voice(self.lang), language=self.persona.language(self.lang)
                ),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
                redial=RedialConfig(enabled=True) if session.can_redial else None,
            )
        )
        logger.info("property: session on {} as {} in {}", self.path, self.job, self.lang)

    async def on_session_end(self, session: Session) -> None:
        """The socket closed: a hang-up, or a drop Voqalize may redial. Kept a
        short while for the redial; runs at least once, and a second run (or
        one on a brain a redial already replaced) changes nothing."""
        REJOIN.dropped(session.id, self)

    def _adopt(self, prior: PropertyBrain) -> None:
        """Take over ``prior``'s call: every piece of state but its socket's.
        ``prior`` then shares this brain's state, so whatever still points at
        it — the Stage director's dispatch and resolver, a booking in flight, a
        line queued for the next quiet spell — acts on this call and this socket."""
        self.__dict__.update({k: v for k, v in prior.__dict__.items() if k not in _PER_SOCKET})
        prior.__dict__ = self.__dict__

    async def greet(self, session: Session) -> str | None:
        """Written, not generated: the job's opener in the call's language. A
        rejoined call opens silently: the buyer already heard hello, and the
        model's history should not gain a second one."""
        if self._rejoined:
            return None
        title = h.LISTINGS[self.listing_id]["title"] if self.listing_id else ""
        line = GREETING[self.job][self.lang].format(name=self.persona.name, title=title)
        return speak_text(line, self.lang)

    def _at(self, path: str) -> bool:
        """The visitor is on ``path``; True when the job changed."""
        self.path = path
        job, listing = _job_of(path)
        if listing is not None and listing not in h.LISTINGS:
            job, listing = "guide", None
        changed = job != self.job or listing != self.listing_id
        self.job, self.listing_id = job, listing
        return changed

    # ─── The turn ───────────────────────────────────────────────────────

    def on_user_message(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]:
        return self._spoken.wrap(self._answer(session, msg))

    async def _answer(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]:
        self.turns += 1
        self._heard_recent = [*self._heard_recent[-2:], msg.text]
        self.stage.visitor_spoke()
        self._talk = None
        self._settle_expired()
        if self.lang != "hi" and "hi" in self.persona.languages and _DEVANAGARI.search(msg.text):
            await session.configure(self._speaking("hi"))
        self.append_note(self.screen_now())
        self.append_note(msg.text)
        if _SPOKEN_PHONE.search(msg.text):
            self.append_note(
                "[They said a phone number aloud. Never repeat it or use it: their mobile number is "
                "typed by them in the Mobile box on the visit form.]"
            )
        elif (said := amounts_note(msg.text)) is not None:
            self.append_note(said)
        pending = self.pending
        if pending is not None and pending.turn < self.turns:
            answer = _yes_no(msg.text)
            if answer == "yes" and not self.phone_typed:
                self._send_fill(pending)
                async for speech in self.say_line(BOOKING["need_phone"][self.lang], remember=True):
                    yield speech
                return
            if answer == "yes":
                line = self._book(pending)
                async for speech in self.say_line(line, remember=True):
                    yield speech
                return
            if answer == "no":
                self.pending = None
                self.append_note("[They did not confirm the visit; nothing was booked.]")
        async for speech in self.respond(session):
            yield speech

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The model's turn with its cues sent to the page; a written line under a
        turn that moved the screen in silence; and the written answer of a read
        the buyer is waiting for when the model said nothing after it ran."""
        record = _Owed()
        token = _OWED.set(record)
        try:
            turn = _counted(self.stage.cued(super().respond(session)), record)
            async for event in self._fallback.speak_if_silent(self, turn):
                yield event
            if (floor := record.floor()) is not None:
                if not record.always:
                    logger.warning("property: a read went unanswered; the brain says {!r}", floor)
                async for event in self.stage.cued(self.say_line(floor, remember=True)):
                    yield event
        finally:
            with contextlib.suppress(ValueError):
                _OWED.reset(token)
        self.stage.end_turn()

    def on_user_idle(self, session: Session, idle: UserIdle) -> AsyncGenerator[Speech, None]:
        return self._spoken.wrap(self._idle(session))

    async def _idle(self, session: Session) -> AsyncGenerator[Speech, None]:
        """A quiet spell: a line the brain owes (a booking's outcome) or the
        page asked for (the visitor booked by hand); otherwise stay quiet."""
        self._settle_expired()
        configure_soon(session, Config(idle=IdleConfig(timeout_ms=_IDLE_MS)))
        say, self._say_next = self._say_next, None
        if say is not None:
            async for event in self.say_line(say(), remember=True):
                yield event
            return
        ask, self._talk = self._talk, None
        if ask is None:
            return
        self.append_note(f"[{ask}]")
        async for event in self.respond(session):
            yield event

    def _say_soon(self, line: Callable[[], str]) -> None:
        self._say_next = line
        configure_soon(self.session, Config(idle=IdleConfig(timeout_ms=_SAY_NOW_MS)))

    def screen_now(self) -> str:
        """The page and the job, in front of what the visitor says."""
        language = self.persona.language_names[self.lang]
        if self.job == "booker" and self.listing_id:
            x = h.LISTINGS[self.listing_id]
            where = (
                f"the page of {x['id']}, {x['title']} ({x['locality']}, {h.price_line(x)}). "
                "Your job: book a site visit for this home."
            )
        else:
            first = ", ".join(self.results[:4])
            where = (
                f"{self.path}. Your job: guide. Search: {self.search.summary()}; "
                f"{len(self.results)} homes match" + (f", first {first}" if first else "") + "."
            )
        extra = ""
        if self.shortlisted:
            extra += f" Shortlist: {', '.join(self.shortlisted)}."
        if self.pending is not None:
            p = self.pending
            extra += f" Waiting for their yes to book {p.listing_id} at {p.slot} for {p.name}."
        if self.job == "booker":
            extra += (
                " Mobile number: typed."
                if self.phone_typed
                else " Mobile number: not typed yet (they type it, never say it)."
            )
        return f"[Screen: {where}{extra}] [Language: {language}]"

    # ─── Stage ──────────────────────────────────────────────────────────

    def _resolve(self, move: Move, args: list[str]) -> list[str] | None:
        """A ``{show: …}`` cue names a listing id that exists, or is dropped."""
        if move.id == "listings.show" and args:
            ref = args[0].strip().upper()
            return [ref] if ref in h.LISTINGS else None
        return args

    def _send(self, move: str, args: dict[str, Any], landed_key: str) -> None:
        self.stage.send(move, args)
        landed(*LANDED[landed_key][self.lang])

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        event = _EVENTS.parse(msg)
        if event is None:
            return
        if isinstance(event, LanguageRequested):
            await self._requested(session, event.language)
            return
        if isinstance(event, StageEvent):
            note = self._event(event)
        elif isinstance(event, StageResult):
            result = self.stage.handle(event)
            note = None if result is None else self._settle(result)
        else:
            self.stage.handle(event)
            note = None
        if note is not None:
            logger.info("property: {}", note)
            self.append_note(note)

    def _event(self, event: StageEvent) -> str | None:
        """Fold what the page reports into the brain's state; the line the model reads."""
        folded = self.stage.handle(event)
        data = event.data
        visitor = event.by == "visitor"
        match event.name:
            case "screen.viewed":
                if self._at(_canonical(str(data.get("path") or "/"))):
                    if self.job == "booker" and self.listing_id:
                        x = h.LISTINGS[self.listing_id]
                        return (
                            f"[They are now on the page of {x['id']}, {x['title']}: "
                            "your job here is booking a site visit.]"
                        )
                    return f"[They are now on {self.path}: your job here is guiding.]"
                return None
            case "search.changed":
                self.search = h.Search.of(data)
                if visitor:
                    self.wanted = replace(self.search)
                self.results = [x["id"] for x in h.search(self.search)]
            case "shortlist.changed":
                self.shortlisted = [str(i) for i in data.get("ids") or []]
            case "visit.phone_typed":
                self.phone_typed = bool(data.get("typed"))
                ask = self.stage.take_reaction()
                if self.phone_typed and visitor:
                    if self.pending is not None:
                        p = self.pending
                        self._say_soon(lambda: self._confirm_line(p))
                    elif ask:
                        self._talk = ask
                        configure_soon(
                            self.session, Config(idle=IdleConfig(timeout_ms=_REACT_IDLE_MS))
                        )
            case "visit.booked":
                slot, listing = str(data.get("slot") or ""), str(data.get("listing_id") or "")
                if slot and listing in h.LISTINGS:
                    self.taken.add(f"{h.host_key(h.LISTINGS[listing])}|{slot}")
                if visitor and listing in h.LISTINGS:
                    self.pending = None
                    if ask := self.stage.take_reaction():
                        self._talk = ask
                        configure_soon(
                            self.session, Config(idle=IdleConfig(timeout_ms=_REACT_IDLE_MS))
                        )
            case _:
                pass
        if folded is None or not visitor:
            return None
        return folded.note

    def _settle_expired(self) -> None:
        for result in self.stage.expire():
            if (note := self._settle(result)) is not None:
                self.append_note(note)

    def _settle(self, result: StageResult) -> str | None:
        """A move's answer: a booking is told in a written line; a move that did
        not land is told to the model with what the page offers instead."""
        booking = self._flights.pop(result.call_ref, None)
        why = "; ".join(
            r.why + (f" (options: {', '.join(r.options)})" if r.options else "")
            for r in result.refused
        )
        if booking is not None:
            if result.outcome in ("applied", "partial"):
                ref = h.reference(booking.listing_id, booking.slot)
                self.taken.add(f"{h.host_key(h.LISTINGS[booking.listing_id])}|{booking.slot}")
                self.booked[ref] = booking
                self._say_soon(lambda: self._booked_line(booking))
                return f"[The visit is booked: {booking.listing_id} at {booking.slot}, reference {ref}.]"
            reason = result.detail or why or result.outcome
            self._say_soon(lambda: BOOKING["failed"][self.lang].format(why=reason))
            return f"[The booking did not go through: {reason}. Offer another free slot.]"
        if result.moved or result.outcome in ("applied", "partial", "undone"):
            return None
        return (
            f"[Your {result.move} move did not land ({result.detail or result.outcome}"
            + (f"; {why}" if why else "")
            + "). Never say it did.]"
        )

    def _when(self, slot: str) -> str:
        """A slot as the brain's own lines say it, in the call's language."""
        d = date.fromisoformat(slot[:10])
        hhmm = slot[11:16]
        if self.lang == "hi":
            hour, minute = (int(v) for v in hhmm.split(":"))
            part = "सुबह" if hour < 12 else "दोपहर" if hour < 16 else "शाम"
            clock = f"{hour % 12 or 12}:{minute:02d}" if minute else f"{hour % 12 or 12}"
            return f"{HI_DAYS[d.weekday()]} {d.day} {HI_MONTHS[d.month - 1]}, {part} {clock} बजे"
        return f"{h.spoken_day(d)} at {h.spoken_time(hhmm)}"

    def _who(self, kind: str, visitors: int) -> str:
        one, two, more = WHO[kind][self.lang]
        return one if visitors <= 1 else two if visitors == 2 else more.format(n=visitors)

    def _confirm_line(self, p: Proposal, *, named: bool = True) -> str:
        line = BOOKING["confirm" if named else "confirm_bare"][self.lang]
        return line.format(
            first=p.name.split()[0], when=self._when(p.slot), who=self._who("confirm", p.visitors)
        )

    def _booked_line(self, p: Proposal) -> str:
        x = h.LISTINGS[p.listing_id]
        return BOOKING["booked"][self.lang].format(
            first=p.name.split()[0],
            when=self._when(p.slot),
            contact=h.host(x).contact,
            who=self._who("booked", p.visitors),
            bring=BRING_SHORT[self.lang],
        )

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        return [
            self.search_homes,
            self.home_facts,
            self.open_listing,
            self.open_page,
            self.compare_homes,
            self.estimate_emi,
            self.shortlist_home,
            self.visit_slots,
            self.propose_visit,
            self.book_visit,
            self.set_language,
            self.read_screen,
        ]

    def _held(self, x: dict[str, Any]) -> set[str]:
        """The slots this call booked or heard booked with ``x``'s host."""
        key = h.host_key(x) + "|"
        return {t[len(key) :] for t in self.taken if t.startswith(key)}

    def _listing(self, ref: str) -> dict[str, Any] | None:
        return h.LISTINGS.get(ref.strip().upper())

    def _approx_budget(self, value: int) -> bool:
        """The buyer said this budget with "around", "about", lagbhag (their last turn)."""
        for heard in parse_amounts(self._heard_recent[-1] if self._heard_recent else ""):
            if heard.approx and heard.low is None and abs(heard.value - value) <= value * 0.02:
                return True
        return False

    # ─── The brain's own answers (K0 R4) ─────────────────────────────────

    def _said(self, key: str, **kw: Any) -> str:
        return SAID[key][self.lang].format(**kw)

    def _and(self, items: list[str]) -> str:
        word = " और " if self.lang == "hi" else " and "
        return items[0] if len(items) == 1 else ", ".join(items[:-1]) + word + items[-1]

    def _price(self, x: dict[str, Any]) -> str:
        """A home's price said once: "₹94 lakh", or "₹29,000 a month" to rent."""
        if x["deal"] == "rent":
            return f"{h.inr(x['rent'])} " + ("महीना" if self.lang == "hi" else "a month")
        return h.short(x["price"])

    def _home(self, x: dict[str, Any], office: str | None = None) -> dict[str, str]:
        """The words a line says about one home."""
        km = h.office_km(x, office) if office else None
        return {
            "name": x["society"],
            "locality": x["locality"],
            "bhk": str(x["bhk"]),
            "price": self._price(x),
            "km": ""
            if km is None or office is None
            else self._said("km", km=f"{km:g}", office=h.place_name(office)),
        }

    def _nudge(self, x: dict[str, Any], *, skip: str = "") -> str:
        """The nudge toward a visit, never the same words two turns running."""
        options = [o for o in NUDGE[x["deal"]][self.lang] if not skip or skip not in o]
        self._nudges += 1
        return options[self._nudges % len(options)]

    def _day_said(self, d: date) -> str:
        if self.lang == "hi":
            return f"{HI_DAYS[d.weekday()]} {d.day} {HI_MONTHS[d.month - 1]}"
        return h.spoken_day(d)

    def _time_said(self, slot_id: str) -> str:
        if self.lang == "hi":
            return self._when(slot_id).split(", ")[-1]
        return h.spoken_time(slot_id[11:16])

    def _next_step(self, found: list[dict[str, Any]], s: h.Search) -> str:
        """What the guide says after the pitch: the next question worth asking (never
        one already asked or answered), or, once the homes are few, the nudge."""
        known = {
            topic for topic, fieldname, _ in _TOPICS if getattr(s, fieldname) not in (None, [])
        }
        open_topics = [t for t, _, _ in _TOPICS if t not in known and t not in self.asked]
        best = found[0]
        if len(found) <= 2 or (len(found) <= 4 and len(known) >= 4) or not open_topics:
            return self._nudge(best)
        topic = open_topics[0]
        self.asked.add(topic)
        return ASK[topic][self.lang]

    def _nearest(self, s: h.Search) -> tuple[str, dict[str, Any]] | None:
        """When nothing fits: the one home closest to it, and what it misses. Over
        the budget by at most 30% (said with how far over), else one limit dropped.
        Never the city, buy or rent, or the bedrooms they asked for. The screen
        keeps what they asked for; this is only what the answer offers."""
        if s.budget_max is not None:
            over = [
                x
                for x in h.search(replace(s, budget_max=None))
                if h.amount(x) <= s.budget_max * 1.3
            ]
            if over:
                return "budget", min(over, key=h.amount)
        tries: list[tuple[str, dict[str, Any]]] = []
        if s.school_km is not None:
            tries.append(("school", {"school_km": None}))
        if s.metro_km is not None:
            tries.append(("metro", {"metro_km": None}))
        if s.max_km is not None:
            tries.append(("commute", {"max_km": None}))
        if s.possession:
            tries.append(("possession", {"possession": None}))
        if s.localities:
            tries.append(("localities", {"localities": []}))
        if s.budget_min is not None:
            tries.append(("budget_min", {"budget_min": None}))
        for what, change in tries:
            if found := h.search(replace(s, **change)):
                return what, found[0]
        return None

    def _detail(self, xs: list[dict[str, Any]], office: str | None) -> list[str]:
        out: list[str] = []
        for x in xs[:5]:
            extra = f", {h.office_km(x, office)} km to {h.place_name(office)}" if office else ""
            out.append(
                f"{x['id']} {x['society']}, {x['bhk']} BHK, {x['locality']}, {h.price_line(x)}, "
                f"{x['carpet_sqft']} sq ft, {x['possession_date']}{extra}, metro "
                f"{x['nearby']['metro'][0]['km']} km, school {x['nearby']['schools'][0]['km']} km."
            )
        return out

    # ─── Tools ──────────────────────────────────────────────────────────

    async def search_homes(self, request: SearchRequest) -> str:
        """Set the listings page's search from what the buyer said: the sidebar
        filters tick one by one and the map follows. Pass only what changed.
        Say only a few words before calling it: the homes that fit are said for
        you straight after."""
        deal = request.deal or (None if request.reset else self.search.deal)
        if deal is None:
            # A price in crores is a home to buy; a few thousand a month is rent.
            top = request.budget_max or request.budget_min
            if top is not None and top >= 10_00_000:
                deal = "buy"
            elif top is not None and top <= 3_00_000:
                deal = "rent"
        budgets: dict[str, float | None] = {
            "budget_min": request.budget_min,
            "budget_max": request.budget_max,
        }
        why = implausible(budgets, deal, self._heard_recent[::-1])
        if why is not None:
            amount = confirm_back(budgets, deal, self._heard_recent[::-1])
            say(
                self._said("budget_check", amount=h.short(amount))
                if amount is not None
                else self._said("budget_again")
            )
            return why
        s = h.Search() if request.reset else replace(self.wanted)
        if request.reset:
            self.around = False
        for name in request.clear or []:
            if hasattr(s, name):
                setattr(s, name, [] if isinstance(getattr(s, name), list) else None)
            if name == "budget_max":
                self.around = False
        given = request.model_dump(exclude={"clear", "reset", "around"}, exclude_none=True)
        notes: list[str] = []
        if deal and "deal" not in given:
            given["deal"] = deal
            if not self.search.deal:
                notes.append(
                    f"They are {'buying' if deal == 'buy' else 'renting'} (from the budget): "
                    "never ask buy or rent."
                )
        if "budget_max" in given:
            # "Around 1 crore": the screen shows ₹1 crore, exactly as said; the
            # answer may offer a home up to 10% over it when nothing is at it.
            self.around = "budget_min" not in given and (
                request.around or self._approx_budget(given["budget_max"])
            )
        if "localities" in given:
            names = h.localities(given.get("city") or s.city)
            picked = [m for m in (match_label(v, names) for v in given["localities"]) if m]
            if len(picked) < len(given["localities"]):
                notes.append(f"Known localities: {', '.join(names)}.")
            given["localities"] = picked
        if "office" in given:
            city = given.get("city") or s.city
            raw = str(given["office"])
            office = h.resolve_office(raw, city) or h.resolve_office(raw)
            if office is None:
                offices = h.places("office", city)
                say(
                    self._said(
                        "office_unknown",
                        offices=self._and(
                            [f"{o['name']} in {h.office_area(o['id'])}" for o in offices]
                        ),
                    )
                )
                return (
                    f"No office matches {raw!r}. Offices: "
                    + ", ".join(
                        f"{o['name']} ({o['id']}, in {h.office_area(o['id'])})" for o in offices
                    )
                    + ". Nothing changed on screen; you asked which of these is nearest their work."
                )
            given["office"] = office
            if raw.strip().lower() not in (office, h.place_name(office).lower()):
                notes.append(
                    f"'{raw}' is {h.place_name(office)}, in {h.office_area(office)}: take it as "
                    "where they work; never ask which office."
                )
            if not given.get("city"):
                given["city"] = next(o["city"] for o in h.places("office") if o["id"] == office)
        for key, value in given.items():
            setattr(s, key, value)
        # The screen shows exactly what they asked for, and the next search starts
        # from it: a stretch or a nearest home is the answer's, never the filter's.
        self.wanted = s
        self.search = replace(s)
        found = h.search(s)
        self.results = [x["id"] for x in found]
        self.stage.send("listings.filter", s.args())
        screen = f"The screen shows {len(found)} homes: {s.summary()}."
        if found:
            best = found[0]
            words = self._home(best, s.office)
            key = "fit_one" if len(found) == 1 else "fit_many"
            line = self._said(key, n=len(found), show=f"{{show: {best['id']}}} ", **words)
            say(f"{line} {self._next_step(found, s)}")
            return " ".join(
                [screen, *notes, "DETAIL, in the screen's order:", *self._detail(found, s.office)]
            )
        top = s.budget_max
        if self.around and top is not None:
            close = h.search(replace(s, budget_max=int(top * 1.1)))
            if close:
                best = close[0]
                pct = max(1, round((h.amount(best) - top) * 100 / top))
                line = self._said(
                    "around", budget=h.short(top), pct=pct, **self._home(best, s.office)
                )
                say(f"{line} {self._next_step(close, s)}")
                return " ".join(
                    [
                        screen,
                        f"They said around {h.short(top)}: you offered homes up to 10% over it "
                        "(not on screen; the filter stays at their budget).",
                        *notes,
                        "DETAIL:",
                        *self._detail(close, s.office),
                    ]
                )
        near = self._nearest(s)
        if near is None:
            say(OWED["none"][self.lang])
            return " ".join([screen, *notes, "Nothing is close; you offered to loosen one thing."])
        what, x = near
        words = self._home(x)
        if what == "budget" and top is not None:
            pct = round((h.amount(x) - top) * 100 / top)
            say(self._said("over", budget=h.short(top), pct=pct, **words))
            offer = f"the nearest home, {pct}% over their budget, and asked whether to raise it"
        else:
            say(self._said("except", what=MISSES[what][self.lang], **words))
            offer = f"the nearest home, which misses only {MISSES[what]['en']}, and asked whether to include such homes"
        return " ".join(
            [
                screen,
                f"Nothing fits; you offered {offer} (it is not on screen; the filter stays as "
                "they said until they agree).",
                *notes,
                "DETAIL:",
                *self._detail([x], s.office),
            ]
        )

    @needs_result_now
    async def home_facts(self, request: ListingRef) -> str:
        """Everything the site says about one home, to answer a question about it.
        Opens the home's page if they are still on the list."""
        x = self._listing(request.listing_id)
        if x is None:
            return f"No listing {request.listing_id}."
        if self.job == "guide":
            self._send("site.go", {"path": f"/listing/{x['id']}"}, "open")
        project = h.PROJECTS.get(x["project_id"] or "")
        more = (
            f" Project {project['name']}: {project['pitch']} {project['towers']} towers, "
            f"{project['units']} homes on {project['acres']} acres."
            if project
            else ""
        )
        owe(
            OWED["facts"][self.lang].format(
                title=x["title"], bhk=x["bhk"], carpet=x["carpet_sqft"], price=self._price(x)
            )
        )
        return (
            "SAY: answer just what they asked, in two short sentences, then nudge toward a "
            "site visit. FACTS: " + h.facts(x) + more
        )

    def _fit(self, x: dict[str, Any]) -> str:
        """The one thing about a home that fits what they asked for."""
        office = self.search.office
        km = h.office_km(x, office) if office else None
        if office and km is not None and km <= 8:
            return self._said("fit_office", km=f"{km:g}", office=h.place_name(office))
        school = x["nearby"]["schools"][0]
        if self.search.school_km is not None or school["km"] <= 2:
            return self._said("fit_school", school=school["name"], km=f"{school['km']:g}")
        metro = x["nearby"]["metro"][0]
        return self._said("fit_metro", metro=metro["name"], km=f"{metro['km']:g}")

    async def open_listing(self, request: ListingRef) -> str:
        """Open one home's page (where a site visit is booked), for "can I see it?"
        and for "tell me more about it". Say only a few words before calling it:
        the home is described for you straight after."""
        x = self._listing(request.listing_id)
        if x is None:
            say(self._said("which_home"))
            return f"No listing {request.listing_id}."
        if not self.path.startswith(f"/listing/{x['id']}"):
            self.stage.send("site.go", {"path": f"/listing/{x['id']}"})
        possession = (
            self._said("ready")
            if x["possession"] == "ready"
            else self._said("building", date=x["possession_date"])
        )
        say(
            self._said(
                "open",
                carpet=x["carpet_sqft"],
                possession=possession,
                fit=self._fit(x),
                **self._home(x),
            )
        )
        return (
            f"Opened {x['title']} ({x['id']}); you described it and asked which day suits them "
            f"for a visit. You are now its visit booker. FACTS: {h.facts(x)}"
        )

    async def open_page(self, request: PageRequest) -> str:
        """Open another page of the site: the listings, the shortlist, booked
        visits, the compare page or a project's page."""
        page = _canonical(request.page)
        ok = page in ("/", "/listings", "/shortlist", "/visits", "/compare") or (
            page.startswith("/project/") and page.split("/")[2] in h.PROJECTS
        )
        if not ok:
            return "Not a page here. Pages: /, /listings, /shortlist, /visits, /project/<id>."
        self._send("site.go", {"path": page}, "open")
        return f"opening {page}"

    def _pick(self, ids: list[str]) -> tuple[str, str, str]:
        """Which of two or three homes suits this buyer better, why in their
        language, and the comparison row that says it: the commute when they gave
        work, a school when they asked for one, else the most space for the money."""
        xs = [h.LISTINGS[i] for i in ids]
        office = self.search.office
        if office and all(h.office_km(x, office) is not None for x in xs):
            best = min(xs, key=lambda x: h.office_km(x, office) or 99.0)
            km = f"{h.office_km(best, office):g}"
            return (
                best["id"],
                WHY["office"][self.lang].format(km=km, office=h.place_name(office)),
                "",
            )
        if self.search.school_km is not None:
            best = min(xs, key=lambda x: x["nearby"]["schools"][0]["km"])
            school = best["nearby"]["schools"][0]
            why = WHY["school"][self.lang].format(school=school["name"], km=f"{school['km']:g}")
            return best["id"], why, "Nearest school"
        if all(x["deal"] == "buy" for x in xs):
            best = min(xs, key=lambda x: x["price_per_sqft"])
            why = WHY["value"][self.lang].format(per=h.inr(best["price_per_sqft"]))
            return best["id"], why, "Price per sq ft"
        best = min(xs, key=lambda x: h.amount(x))
        return best["id"], WHY["price"][self.lang].format(price=self._price(best)), "Price"

    async def compare_homes(self, request: CompareRequest) -> str:
        """Put two or three homes side by side. Say only a few words before
        calling it: which suits them better is said for you straight after."""
        ids = [i.strip().upper() for i in request.listing_ids]
        missing = [i for i in ids if i not in h.LISTINGS]
        if missing or not 2 <= len(ids) <= 3:
            say(self._said("which_two"))
            return f"Compare needs two or three listing ids; unknown: {', '.join(missing) or '-'}."
        self.stage.send("compare.show", {"ids": ids})
        pick, why, row = self._pick(ids)
        x = h.LISTINGS[pick]
        rows = h.compare_rows(ids)
        though = ""
        for label, values, best in rows:
            if label == row or label not in EDGE or best is None or ids[best] == pick:
                continue
            other = h.LISTINGS[ids[best]]
            what = EDGE[label][self.lang].format(name=other["society"], value=values[best])
            though = self._said("though", what=what)
            break
        say(self._said("compare", name=x["society"], why=why, though=though))
        out = [
            f"Side by side: {' vs '.join(ids)}; you said {x['society']} ({pick}) suits them "
            "better and offered a site visit there. DETAIL:"
        ]
        for label, values, best in rows:
            mark = f" (better: {ids[best]})" if best is not None else ""
            out.append(f"{label}: {' | '.join(values)}{mark}.")
        return " ".join(out)

    async def estimate_emi(self, request: EmiRequest) -> str:
        """Work out a home loan's EMI for a home to buy, on screen, from the
        site's lender rates. Defaults: 20% down, 20 years. ``also``: other homes
        to compare the EMI with on the same terms. Say only a few words before
        calling it: the EMI is said for you straight after."""
        x = self._listing(request.listing_id)
        if x is None or x["deal"] != "buy":
            say(self._said("emi_rent" if x is not None else "which_home"))
            return "EMI is only for a home to buy; give a listing id of one."
        down = request.down_pct if request.down_pct is not None else h.EMI_DEFAULTS["down_pct"]
        years = request.tenure_years or h.EMI_DEFAULTS["tenure_years"]
        lender = request.lender or h.EMI_DEFAULTS["lender"]
        if lender not in h.LENDERS:
            lender = match_label(lender, list(h.LENDERS)) or h.EMI_DEFAULTS["lender"]
        if lender == "kosha-partner" and x["kind"] != "new":
            lender = h.EMI_DEFAULTS["lender"]
        down = min(max(down, h.EMI_DEFAULTS["min_down_pct"]), 90)
        years = min(max(years, 1), h.EMI_DEFAULTS["max_tenure_years"])
        e = h.emi(x["price"], down, years, lender)
        self.stage.send(
            "emi.show",
            {"listing_id": x["id"], "down_pct": down, "tenure_years": years, "lender": lender},
        )
        rivals: list[str] = []
        rival = ""
        for ref in request.also or []:
            y = self._listing(ref)
            if y is None or y["deal"] != "buy" or y["id"] == x["id"]:
                continue
            ey = h.emi(y["price"], down, years, lender)
            rivals.append(
                f"{y['title']} ({y['id']}, {h.short(y['price'])}): EMI {h.inr(ey.emi)} a month"
            )
            if not rival:
                lower = x if e.emi <= ey.emi else y
                rival = self._said(
                    "emi_rival", other=y["society"], emi=h.inr(ey.emi), lower=lower["society"]
                )
        say(
            self._said(
                "emi",
                name=x["society"],
                down=f"{down:g}",
                years=years,
                emi=h.inr(e.emi),
                rival=rival,
                nudge=self._nudge(x, skip="EMI"),
            )
        )
        others = [
            f"{v['name']} {v['rate']}%: {h.inr(h.emi(x['price'], down, years, k).emi)}"
            for k, v in h.LENDERS.items()
            if k != lender and (k != "kosha-partner" or x["kind"] == "new")
        ]
        return (
            f"You said the EMI and offered a site visit. DETAIL: {x['id']} at "
            f"{h.short(x['price'])}: {down:g}% down is {h.short(x['price'] - e.principal)}, loan "
            f"{h.short(e.principal)} over {years} years with {e.lender['name']} at "
            f"{e.lender['rate']}%: EMI {h.inr(e.emi)} a month, total interest "
            f"{h.short(e.total_interest)}. {e.lender['note']}"
            + (f" Same terms: {'; '.join(rivals)}." if rivals else "")
            + f" Other lenders: {'; '.join(others)}."
        )

    async def shortlist_home(self, request: ShortlistRequest) -> str:
        """Add a home to the buyer's shortlist, or take it off."""
        x = self._listing(request.listing_id)
        if x is None:
            return f"No listing {request.listing_id}."
        if request.on and x["id"] not in self.shortlisted:
            self.shortlisted.append(x["id"])
        if not request.on and x["id"] in self.shortlisted:
            self.shortlisted.remove(x["id"])
        self._send("shortlist.set", {"listing_id": x["id"], "on": request.on}, "shortlist")
        return f"{x['id']} {'on' if request.on else 'off'} the shortlist"

    def _day(self, text: str | None) -> date | None | Literal["closed", "weekend"]:
        days = h.visit_days()
        if not text:
            return None
        t = text.strip().lower()
        if t == "tomorrow":
            return days[0]
        if "weekend" in t or t in ("वीकेंड", "सप्ताहांत", "शनिवार-रविवार"):
            return "weekend"
        for d in days:
            if t in (d.isoformat(), d.strftime("%A").lower(), d.strftime("%a").lower()):
                return d
        return "closed"

    def _open_days(self, x: dict[str, Any], part: h.Part = "any") -> str:
        """The next days with a free visit slot at ``x``, as a line says them."""
        held = self._held(x)
        free = [d for d in h.visit_days() if h.free_slots(x, d, part, held)]
        return self._and([self._day_said(d).split(" ")[0] for d in free[:3]] or ["-"])

    def _times(self, slots: list[h.Slot]) -> str:
        return self._and([self._time_said(s.id) for s in slots[:2]])

    def _are(self, slots: list[h.Slot]) -> str:
        """The verb after one or two times: "is"/"are", "है"/"हैं"."""
        one = len(slots[:2]) == 1
        if self.lang == "hi":
            return "है" if one else "हैं"
        return "is" if one else "are"

    async def visit_slots(self, request: SlotsRequest) -> str:
        """The free site-visit slots for a home, in IST, where the buyer's
        preferred day and time meet the sales team's diary. Shows them on the
        listing's visit panel. Say only a few words before calling it: the free
        times are said for you straight after."""
        x = self._listing(request.listing_id)
        if x is None:
            say(self._said("which_home"))
            return f"No listing {request.listing_id}."
        host = h.host(x)
        days = h.visit_days()
        held = self._held(x)
        open_days = [d for d in days if h.free_slots(x, d, request.part, held)]
        days_said = self._open_days(x, request.part)
        day = self._day(request.day)
        if day == "closed":
            say(self._said("which_day", days=days_said))
            return (
                f"Visits can be booked on {', '.join(h.spoken_day(d) for d in days)} only "
                "(the next seven days); you asked which."
            )
        if day is None:
            say(self._said("which_day", days=days_said))
            return f"{host.contact}'s team has free {request.part} slots on " + ", ".join(
                f"{h.spoken_day(d)} ({d.isoformat()})" for d in open_days
            )
        weekend: list[tuple[date, list[h.Slot]]] = []
        if day == "weekend":
            ends = [d for d in days if d.weekday() >= 5]
            weekend = [(d, h.free_slots(x, d, request.part, held)) for d in ends]
            day = next((d for d, free in weekend if free), ends[0] if ends else days[0])
        if not self.path.startswith(f"/listing/{x['id']}"):
            self.stage.send("site.go", {"path": f"/listing/{x['id']}"})
        self.stage.send(
            "visit.slots", {"listing_id": x["id"], "day": day.isoformat(), "part": request.part}
        )
        if h.day_slots(x, day) is None:
            say(self._said("closed", day=self._day_said(day), days=days_said))
            return f"The sales team does not take visits on {h.spoken_day(day)}; you offered other days."
        free = h.free_slots(x, day, request.part, held)
        both = [(d, f) for d, f in weekend if f]
        if len(both) == 2:
            (d1, f1), (d2, f2) = both
            say(
                self._said(
                    "weekend",
                    day=self._day_said(d1),
                    times=self._times(f1),
                    day2=self._day_said(d2),
                    times2=self._times(f2),
                    are=self._are(f1),
                )
            )
        elif free:
            say(
                self._said(
                    "slots", day=self._day_said(day), times=self._times(free), are=self._are(free)
                )
            )
        else:
            other = h.free_slots(x, day, "any", held)
            if other:
                part = HI_PARTS[request.part] if self.lang == "hi" else request.part
                say(
                    self._said(
                        "part_full",
                        day=self._day_said(day),
                        part=part,
                        times=self._times(other),
                        is_=self._are(other),
                    )
                )
                free = other
            else:
                say(self._said("day_full", day=self._day_said(day), days=days_said))
        listed = ", ".join(f"{h.spoken_time(s.time)} ({s.id})" for s in free[:6]) or "none"
        return (
            f"Free on {h.spoken_day(day)}: {listed}. Visits are {host.team['slot_minutes']} "
            f"minutes with {host.contact}. You offered the first one or two."
            + (
                " This weekend: "
                + "; ".join(
                    f"{h.spoken_day(d)}: {', '.join(f'{s.time} ({s.id})' for s in f[:4]) or 'nothing free'}"
                    for d, f in weekend
                )
                if weekend
                else ""
            )
        )

    def _send_fill(self, p: Proposal) -> None:
        """Fill the visit form as said: the slot, the name, how many are coming;
        the page rings the Mobile box while it is empty (the visitor types it)."""
        with contextlib.suppress(Refused):  # the same fill still on its way: it stands
            self.stage.send(
                "visit.fill",
                {
                    "listing_id": p.listing_id,
                    "slot": p.slot,
                    "name": p.name,
                    "visitors": p.visitors,
                },
            )

    async def propose_visit(self, request: ProposeRequest) -> str:
        """Hold one free slot for the buyer and fill the visit form on screen,
        before they confirm; their yes books it. Say only a few words before
        calling it (never their name): what comes next is said for you."""
        x = self._listing(request.listing_id)
        if x is None:
            say(self._said("which_home"))
            return f"No listing {request.listing_id}."
        slot = request.slot.strip()
        try:
            day = date.fromisoformat(slot[:10])
        except ValueError:
            say(self._said("which_day", days=self._open_days(x)))
            return "The slot must be an id like 2026-11-22T10:30 from visit_slots."
        free = h.free_slots(x, day, "any", self._held(x))
        if slot not in {s.id for s in free}:
            if free:
                say(
                    self._said(
                        "taken",
                        day=self._day_said(day),
                        times=self._times(free),
                        are=self._are(free),
                    )
                )
            else:
                say(self._said("day_full", day=self._day_said(day), days=self._open_days(x)))
            return f"{slot} is not a free slot; you offered the free ones that day."
        name = request.name.strip()
        if not name:
            say(self._said("no_name"))
            return "Ask for their name first."
        visitors = min(max(request.visitors, 1), 6)
        self.pending = Proposal(x["id"], slot, name, visitors, self.turns)
        self._send_fill(self.pending)
        when = f"{h.spoken_day(day)} at {h.spoken_time(slot[11:16])}"
        held = (
            f"Held and filled in on screen: {when} for {name}, {visitors} "
            f"visitor{'s' if visitors > 1 else ''}, at {x['title']}."
        )
        if not self.phone_typed:
            say(self._said("filled", when=self._when(slot), who=self._who("confirm", visitors)))
            return (
                f"{held} You asked them to type their mobile number in the highlighted Mobile "
                "box (never say it). The page tells you when it is in; the one confirmation follows."
            )
        first = name.split()[0]
        say(
            self._confirm_line(self.pending),
            bare=self._confirm_line(self.pending, named=False),
            name=first,
        )
        return f"{held} Their mobile number is typed; you asked the one confirmation. Nothing is booked until they say yes."

    async def book_visit(self, request: BookRequest) -> str:
        """Book the held visit. Only after the buyer just said yes to it."""
        if self.pending is None:
            return "Nothing is held. Find a free slot and propose it first."
        if not request.buyer_said_yes or self.pending.turn >= self.turns:
            return "Not booked: ask them to confirm first and wait for their yes."
        if not self.phone_typed:
            self._send_fill(self.pending)
            return (
                "Not booked yet: their mobile number is not typed. Ask them to type it in the "
                "highlighted Mobile box; never ask them to say it."
            )
        line = self._book(self.pending)
        landed(line)
        return "booking sent; the page answers with the visit card"

    def _book(self, p: Proposal) -> str:
        """Send the booking to the page; the line said while it goes."""
        self.pending = None
        ref = self.stage.send(
            "visit.book",
            {"listing_id": p.listing_id, "slot": p.slot, "name": p.name, "visitors": p.visitors},
            queue=False,
        )
        self._flights[ref] = p
        self.append_note(
            f"[They said yes: booking {p.listing_id} at {p.slot} for {p.name}. "
            "The page answers; do not book again.]"
        )
        return BOOKING["booking"][self.lang]

    async def set_language(self, request: LanguageRequest) -> str:
        """Speak and listen in another language for the rest of the call."""
        tag = self.persona.tag(request.language)
        configure_soon(self.session, self._speaking(tag))
        return f"the call is now in {self.persona.language_names[tag]}"

    async def _requested(self, session: Session, tag: str) -> None:
        """The toggle: both legs in one awaited request, then a written line in
        the new language at the next quiet spell."""
        if tag == self.lang or tag not in self.persona.languages:
            return
        was = self.lang
        try:
            await session.configure(self._speaking(tag))
        except RequestRejected as rejected:
            logger.warning("property: switch to {} refused: {}", tag, rejected)
            self.lang = was
            self.session.dispatch(LanguageChanged(language=was))
            return
        name = self.persona.language_names[tag]
        self.append_note(f"[They switched the call to {name} on the toggle; speak {name} now.]")
        self._say_soon(lambda: BOOKING["switched"][tag])

    def _speaking(self, tag: str) -> Config:
        """Both legs in ``tag``, and the page's toggle moved to it."""
        if tag != self.lang:
            self.session.dispatch(LanguageChanged(language=tag))
        self.lang = tag
        logger.info("property: language -> {}", tag)
        return Config(
            stt=SttConfig(language=self.persona.language(tag), patience=PATIENCE),
            tts=TtsConfig(voice=self.persona.voice(tag), language=self.persona.language(tag)),
        )

    @needs_result_now
    async def read_screen(self, request: ReadRequest) -> str:
        """Read part of their screen as the page last reported it."""
        mirror = self.stage.mirror
        return mirror.read(request.slice) if mirror is not None else "nothing reported"


#: Live calls by session id, for a redial to rejoin (rejoin.py).
REJOIN: Rejoin[PropertyBrain] = Rejoin()

__all__ = ["REJOIN", "LanguageChanged", "PropertyBrain"]
