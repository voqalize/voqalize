"""HolidaysBrain — the trip planner at Wanderloom Holidays, a fictional Indian
online holiday company.

An :class:`~voqalize.sdk.openai.OpenAIBrain`. The visitor says what they want in
a sentence or two (from where, where to, when, how long, who, budget, style)
and the planner builds the holiday on their screen: the brief, round-trip flight
options, hotels per city, activities day by day, and a priced package they can
edit item by item, ending at a review page where they pay (a mock payment they
press themselves).

**The screen is Stage.** Every change the planner makes is a Stage move from
``frontend/src/stage/scene.json`` (generated into :mod:`.stage_gen`): tools send
the moves that change the trip, and the model's own words carry the cues that
point (``{show: day 3}``), open a step (``{step: hotels}``) or a page
(``{go: plan}``). The page reports what the visitor does by hand as Stage events
on the ``trip`` slice, by id, and the brain folds each into its own copy of the
trip — so "swap the hotel in Ubud" means the hotel on screen now.

**No invented facts.** Fares, hotels, rooms, activities and every price come
from ``data/inventory.json`` through :mod:`.engine`, which the page implements
the same way (``data/engine_cases.json`` holds the two to one answer).

**What is marked ``@needs_result_now``.** The reads the model must speak from:
the destinations' prices, the brief as it stands, the flight and hotel options,
the activities that fit, the package and the summary. Each read ``owe``s the
brain's own line for it, said when the model says nothing after the tool ran.

**A pick does not wait (H3).** Choosing a flight, a hotel, an activity, moving
nights or taking an activity out are actions: each opens the next step on
screen and returns at once, with no second model request. Since H1 they had
waited for their result so the model could present what opened next, which
cost about two seconds on every pick. Instead the model is told *before* the
pick what opens after it (:meth:`HolidaysBrain.ahead`, in the reads' results
and the trip note), and says the pick and the next choice in the response that
calls the tool. The floor under it (``owe`` with ``then`` and ``cover``): when
the model's words named none of the next options, the brain says the next
choice itself (the whole step line if the model said nothing), straight away
(:mod:`.lead`). So a step still never ends on a bare confirmation (H1: the
owner's call stalled on "I'll add Banyan Air to your trip." twice). Going to
checkout and switching language stay actions too.

**Language.** The planner speaks the languages ``persona.json`` lists (English
only since H2, 25 Nov). With more than one, the visitor picks on the page
before the call (``init.lang``) and may switch mid-call by the toggle or by
asking; both legs move together, with the voice ``persona.json`` names for that
language. With one, there is no toggle and no ``set_language`` tool.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator, Callable
from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import date
from typing import Any, Literal

from loguru import logger
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from voqalize_demos import PATIENCE, FallbackLine, configure_soon, landed

from voqalize.sdk import (
    Action,
    AppEvent,
    AppEvents,
    RTVIMessage,
    Session,
    Speech,
    SpeechChunk,
    SpeechStart,
    UserIdle,
    UserMessage,
)
from voqalize.sdk.openai import OpenAIBrain, needs_result_now
from voqalize.sdk.stage import Mirror, Stage, match_label
from voqalize.sdk.stage.wire import StageEvent, StageHello, StageProgress, StageResult
from voqalize.sdk.wire import Config, IdleConfig, RedialConfig, SttConfig, TtsConfig

from . import engine as eng
from . import lead
from .engine import Trip
from .persona import LANGUAGES, Speaking, speaking
from .prompt import system_instruction
from .rejoin import Rejoin
from .spoken import SpokenAmounts, amounts_note, implausible, speak_text
from .stage_gen import SPEC

#: GPT-6.1 Terra, as the other OpenAI demos run it, at medium reasoning: at low,
#: the model skipped screen moves it had just promised (demos/README.md).
MODEL = "gpt-6.1-terra"
REASONING = "medium"

#: A quiet visitor is reading a package; the planner does not nudge.
_IDLE_MS = 30_000
#: A line the brain already knows (a booking reference, a language switch):
#: said as soon as the voice is free.
_SAY_NOW_MS = 400

#: A language tag persona.json offers ("en").
Lang = str

#: What a brain holds for one socket only: the session object and the speech
#: units waiting for the runtime to say what was heard. Everything else a call
#: built is carried to the brain a redial starts (rejoin.py).
_PER_SOCKET = frozenset({"_session", "_awaiting"})


class LanguageChosen(AppEvent):
    """The visitor pressed the other language on the toggle during the call."""

    language: str


class LanguageChanged(Action):
    """The call's language moved (the toggle, or the visitor asking by voice):
    the page's EN / हिंदी toggle follows and remembers it for the next call."""

    language: Lang


@dataclass
class _Owed:
    """One turn's record: how many units of the model's speech went out and what
    they said, and the written line a step owes if nothing is said after its
    tool ran.

    A pick (H3) owes differently, since its tool runs after the model's words:
    ``cover`` names the next step's options, and when the turn's words name none
    of them the brain says ``then`` (the next choice) after the model's own, or
    the whole ``line`` when the model said nothing at all. ``always`` is a line
    said whatever the model said: a pick that did not happen."""

    starts: int = 0
    text: str = ""
    line: str | None = None
    at: int = 0
    then: str | None = None
    cover: tuple[str, ...] = ()
    always: bool = False

    def floor(self) -> str | None:
        """What the brain says after the model's turn, if anything."""
        if self.line is None:
            return None
        if self.always:
            return self.line
        if self.then is None:
            return self.line if self.starts == self.at else None
        if not self.text.strip():
            return self.line
        said = _fold(self.text)
        if any(_named(name) in said for name in self.cover):
            return None
        return self.then


def _named(name: str) -> str:
    """How a name is said in passing: its first two words ("Sayan Ridge" for
    Sayan Ridge Villas, "Azure Atoll" for Azure Atoll Resort & Spa)."""
    words = [w for w in _fold(name).split() if w not in ("the", "&")]
    return " ".join(words[:2])


async def _counted(
    turn: AsyncGenerator[Speech, None], record: _Owed
) -> AsyncGenerator[Speech, None]:
    """The model's turn, each unit of its speech counted and its words kept (not
    the brain's own lines)."""
    try:
        async for s in turn:
            if isinstance(s, SpeechStart):
                record.starts += 1
            elif isinstance(s, SpeechChunk):
                record.text += s.text
            yield s
    finally:
        await turn.aclose()


#: Per turn: each turn runs in its own task.
_OWED: ContextVar[_Owed | None] = ContextVar("holidays_owed", default=None)


def owe(
    line: str, *, then: str | None = None, cover: tuple[str, ...] = (), always: bool = False
) -> None:
    """Beside a step that landed: the brain's own line for it and the next
    choice. For a read, said if the model's turn says nothing after the tool
    ran (its preamble alone does not count). For a pick, which runs after the
    model's words (H3): ``then``, said when those words named none of ``cover``
    (the whole ``line`` when there were none). The floor under "I'll add Banyan
    Air to your trip." followed by nothing, which is where the owner's call
    stalled (H1)."""
    if (record := _OWED.get()) is not None:
        record.line = line
        record.at = record.starts
        record.then = then
        record.cover = cover
        record.always = always


#: Words any offer of the package step says.
_PACKAGE_WORDS = ("package", "book", "checkout", "total")

_EVENTS = AppEvents(LanguageChosen, StageResult, StageHello, StageProgress, StageEvent)

# Written lines, per language: what the floor says when a turn acted in silence.
_LINES: dict[str, dict[str, str]] = {
    "en": {
        "brief": "I've put that in your trip.",
        "flights": "Here are the flights.",
        "flight": "Done, that flight is in. The total is now {total}.",
        "hotels": "Here are the hotels in {city}.",
        "hotel": "Done, {hotel} is in. The total is now {total}.",
        "nights": "Done, the nights are moved. The total is now {total}.",
        "add": "Added. The total is now {total}.",
        "remove": "Taken out. The total is now {total}.",
        "build": "Here's your whole package, {total} all in.",
        "checkout": "Here's the review page. Check the details and press Pay when you're ready.",
        "summary": "Here's where your trip stands.",
        "paid": "Congratulations, you're booked! Your reference is {reference}.",
    },
}

_ALIASES = {
    "bombay": "BOM",
    "bangalore": "BLR",
    # As the recognizer writes Bengaluru: "Bengalou" in the owner's call (H1).
    "bengalu": "BLR",
    "bengalo": "BLR",
    "banglore": "BLR",
    "madras": "MAA",
    "calcutta": "CCU",
    "new delhi": "DEL",
    "ncr": "DEL",
    "gurgaon": "DEL",
    "gurugram": "DEL",
    "noida": "DEL",
}

_MONTHS = [
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
]

FlightSort = Literal["recommended", "price", "duration", "departure"]


# ─── Tool arguments ───────────────────────────────────────────────────────────


class TripBrief(BaseModel):
    """Any part of the brief the visitor gave. Leave out what they did not say."""

    from_city: str | None = Field(None, description="City or airport they fly from, as said.")
    destination: str | None = Field(
        None, description="Destination, or a city in it (Ubud means Bali), as said."
    )
    start_date: str | None = Field(None, description="Departure from home, YYYY-MM-DD.")
    month: str | None = Field(
        None, description="A month when they gave no date: 'February' or '2027-02'."
    )
    nights: int | None = None
    adults: int | None = None
    kids_ages: list[int] | None = Field(
        None, description="Every child's age. An empty list removes the children."
    )
    budget: int | None = Field(None, description="Budget in rupees; 0 removes it.")
    budget_per_person: bool = Field(False, description="True when the budget was per person.")
    style: Literal["relaxed", "adventure", "honeymoon", "family"] | None = None


class DestinationQuery(BaseModel):
    style: Literal["relaxed", "adventure", "honeymoon", "family"] | None = None
    month: str | None = Field(None, description="A month they mentioned, to say what is in season.")
    domestic: bool | None = Field(None, description="True for India only, False for abroad.")


class FlightsRequest(BaseModel):
    sort: FlightSort = "recommended"


class FlightChoice(BaseModel):
    choice: str = Field(
        description="The option as the visitor named it: its number on screen ('2'), "
        "the airline, or 'the nonstop' / 'the cheapest'."
    )


class HotelsRequest(BaseModel):
    city: str = Field(description="A city of the trip, as said: Ubud, Seminyak, Munnar…")
    want: str | None = Field(
        None,
        description="What they want: beach, pool, luxury, budget, family, honeymoon, "
        "relaxed, adventure, culture.",
    )


class HotelChoice(BaseModel):
    hotel: str = Field(description="The hotel's name as said.")
    room: str | None = Field(None, description="A room type, if they named one.")


class NightsRequest(BaseModel):
    city: str
    nights: int = Field(description="How many nights they want in that city.")


class ActivitiesRequest(BaseModel):
    day: int | None = Field(None, description="A day of the holiday, 1 = arrival day.")
    city: str | None = None


class ActivityChoice(BaseModel):
    activity: str = Field(description="The activity's name as said.")
    day: int | None = Field(None, description="The day, if they said one.")


class LanguageRequest(BaseModel):
    language: str = Field(
        description="The language tag: "
        + ", ".join(f"{t} ({s.name})" for t, s in LANGUAGES.items())
    )


# ─── Words ────────────────────────────────────────────────────────────────────


def _fold(s: str) -> str:
    return " ".join(s.lower().replace("-", " ").split())


def resolve_origin(said: str) -> str | None:
    s = _fold(said)
    if said.upper() in eng.ORIGINS:
        return said.upper()
    for alias, code in _ALIASES.items():
        if alias in s:
            return code
    hit = match_label(said, list(eng.ORIGINS.values()))
    return next((c for c, city in eng.ORIGINS.items() if city == hit), None)


def resolve_destination(said: str) -> str | None:
    s = _fold(said)
    if s in eng.DESTINATIONS:
        return s
    names = {d["name"]: d["id"] for d in eng.DESTINATIONS.values()}
    names |= {c["name"]: c["destination"] for c in eng.CITIES.values()}
    names |= {
        "Thai": "thailand",
        "Phi Phi": "thailand",
        "Krabi": "thailand",
        "Swiss": "switzerland",
        "UAE": "dubai",
        "Indonesia": "bali",
        "Male": "maldives",
    }
    for name, did in names.items():
        if _fold(name) in s.split() or _fold(name) == s:
            return did
    hit = match_label(said, list(names))
    return names.get(hit) if hit else None


def resolve_month(said: str, today: date) -> date | None:
    s = _fold(said)
    year: int | None = None
    month: int | None = None
    if len(s) == 7 and s[4] == " " and s[:4].isdigit():  # "2027 02" after folding
        year, month = int(s[:4]), int(s[5:])
    elif s.isdigit() and 1 <= int(s) <= 12:
        month = int(s)
    else:
        for i, name in enumerate(_MONTHS):
            if name.startswith(s[:3]) and s[:3] in name:
                month = i + 1
        for word in s.split():
            if word.isdigit() and len(word) == 4:
                year = int(word)
    if month is None:
        return None
    try:
        return eng.month_start(month, today, year)
    except ValueError:
        return None


def _included(activity: str, inclusions: list[str]) -> bool:
    """The hotel already gives it ("Sunset dolphin cruise once" at Azure Atoll):
    the real call offered the dolphin cruise for ₹7,600 and then said the resort
    includes one."""
    words = set(_fold(activity).split())
    return any(words <= set(_fold(i).split()) for i in inclusions)


def _or(names: list[str], word: str = "or") -> str:
    """ "A", "A or B", "A, B or C"."""
    if len(names) <= 1:
        return "".join(names)
    return f"{', '.join(names[:-1])} {word} {names[-1]}"


# ─── The brain ────────────────────────────────────────────────────────────────


class HolidaysBrain(OpenAIBrain):
    """One per call: the trip as the planner and the page both see it."""

    def __init__(
        self, *, client: AsyncOpenAI, model: str = MODEL, today: date | None = None
    ) -> None:
        self.today = today or date.today()
        self.page = "plan"
        self.lang: Lang = "en"
        super().__init__(
            client=client,
            system_instruction=system_instruction(self.page, self.lang, self.today),
            model=model,
            reasoning=REASONING,
        )
        self.trip = Trip()
        self.flight_sort: FlightSort = "recommended"
        self.booked: str | None = None
        self.stage = Stage(
            dispatch=lambda a: self.session.dispatch(a),
            moves=SPEC.move_set(),
            mirror=Mirror(SPEC),
        )
        self._fallback = FallbackLine()
        self._say_next: Callable[[], str] | None = None
        self._said_state = ""
        self._rejoined = False  # this socket picked up a call a dropped one served
        #: The visitor's last few turns, as heard: what a budget is checked against.
        self._heard_recent: list[str] = []
        #: Every amount spoken in the form the voice reads right (spoken.py, X8).
        self._spoken = SpokenAmounts(lambda: self.lang)

    # ─── Session ────────────────────────────────────────────────────────

    def _speaking(self, s: Speaking) -> Config:
        return Config(
            tts=TtsConfig(voice=s.voice, language=s.tag),
            stt=SttConfig(language=s.tag, patience=PATIENCE),
        )

    async def on_session_start(self, session: Session) -> None:
        """The page and language the call started on, and any trip the visitor
        already built by hand; then both legs of the language, before the greeting.

        A call outlives a dropped socket (CONTRACT.md, Redial; SDK 0.15.0):
        redial is on wherever Voqalize offers it, and a brain started by a
        redial on a session this process still holds adopts that call as it
        was — the trip, the page and language it had moved to, the model's
        history — instead of starting over from the (now stale) ``init``."""
        prior = REJOIN.take(session.id)
        rejoined = prior is not None and prior is not self
        if prior is not None and rejoined:
            self._adopt(prior)
            logger.info("holidays: rejoined call {} after its socket dropped", session.id)
            s = LANGUAGES[self.lang]
        else:
            init: dict[str, Any] = dict(session.init or {})
            self.page = "home" if init.get("page") == "home" else "plan"
            s = speaking(str(init.get("lang") or ""))
            self.lang = s.tag
            raw = init.get("trip")
            if isinstance(raw, dict):
                self.trip = Trip.from_json(raw)  # pyright: ignore[reportUnknownArgumentType]
            self.system_instruction = system_instruction(self.page, self.lang, self.today)
        self._rejoined = rejoined
        REJOIN.hold(session.id, self)
        config = self._speaking(s)
        await session.configure(
            replace(
                config,
                idle=IdleConfig(timeout_ms=_IDLE_MS),
                redial=RedialConfig(enabled=True) if session.can_redial else None,
            )
        )
        if not rejoined and self.trip.destination:
            self.append_note(f"[The visitor already started a trip on screen. {self.state_line()}]")

    async def on_session_end(self, session: Session) -> None:
        """The socket closed: a hang-up, or a drop Voqalize may redial. Kept a
        short while for the redial; runs at least once, and a second run (or
        one on a brain a redial already replaced) changes nothing."""
        REJOIN.dropped(session.id, self)

    def _adopt(self, prior: HolidaysBrain) -> None:
        """Take over ``prior``'s call: every piece of state but its socket's.
        ``prior`` then shares this brain's state, so whatever still points at
        it — the Stage director's dispatch, a line queued for the next quiet
        spell — acts on this call and this socket."""
        self.__dict__.update({k: v for k, v in prior.__dict__.items() if k not in _PER_SOCKET})
        prior.__dict__ = self.__dict__

    async def greet(self, session: Session) -> str | None:
        """The page's greeting in the call's language; none for a rejoined call,
        which the visitor already heard greeted (Voqalize does not speak a
        redialled brain's greeting either, and none means none in the history)."""
        if self._rejoined:
            return None
        s = LANGUAGES[self.lang]
        return speak_text(s.greeting_home if self.page == "home" else s.greeting_plan, self.lang)

    def _line(self, key: str, **kw: str) -> str:
        return _LINES.get(self.lang, _LINES["en"])[key].format(**kw)

    def on_user_message(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]:
        return self._spoken.wrap(self._answer(session, msg))

    async def _answer(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]:
        self.stage.visitor_spoke()
        self._heard_recent = [*self._heard_recent[-2:], msg.text]
        self._say_next = None
        self._settle_expired()
        state = self.state_line()
        if state != self._said_state:
            ahead = self.ahead()
            self.append_note(
                f"[Trip now: {state} {self.next_note()}]" + (f"\n{ahead}" if ahead else "")
            )
            self._said_state = state
        self.append_note(msg.text)
        if (said := amounts_note(msg.text)) is not None:
            self.append_note(said)
        async for speech in self.respond(session):
            yield speech

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The model's turn, its cues sent to the page; then, when a step landed
        and nothing was said after its tool ran, the step's own line with the
        next choice (``owe``): every turn that moves the plan ends on where it
        goes next (H1). ``FallbackLine`` stays the floor for a landed action."""
        record = _Owed()
        token = _OWED.set(record)
        try:
            turn = _counted(self.stage.cued(super().respond(session)), record)
            async for event in self._fallback.speak_if_silent(self, turn):
                yield event
            if (floor := record.floor()) is not None:
                logger.info("holidays: the step's next choice, in the brain's words: {!r}", floor)
                async for event in self.say_line(floor, remember=True):
                    yield event
        finally:
            with contextlib.suppress(ValueError):
                _OWED.reset(token)
        self.stage.end_turn()

    def on_user_idle(self, session: Session, idle: UserIdle) -> AsyncGenerator[Speech, None]:
        return self._spoken.wrap(self._idle(session))

    async def _idle(self, session: Session) -> AsyncGenerator[Speech, None]:
        self._settle_expired()
        say, self._say_next = self._say_next, None
        configure_soon(session, Config(idle=IdleConfig(timeout_ms=_IDLE_MS)))
        if say is not None:
            async for event in self.say_line(say(), remember=True):
                yield event

    def _say_soon(self, line: str) -> None:
        self._say_next = lambda: line
        configure_soon(self.session, Config(idle=IdleConfig(timeout_ms=_SAY_NOW_MS)))

    # ─── What the page says ─────────────────────────────────────────────

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        event = _EVENTS.parse(msg)
        if event is None:
            return
        if isinstance(event, LanguageChosen):
            self._switch(event.language, by="toggle")
            return
        if isinstance(event, StageEvent):
            note = self._visitor_did(event)
            if note:
                logger.info("holidays: visitor {}", note)
                self.append_note(f"[{note}]")
            return
        if isinstance(event, StageResult):
            result = self.stage.handle(event)
            if result is not None and (note := self._settle(result)):
                self.append_note(note)
            return
        self.stage.handle(event)

    def _settle_expired(self) -> None:
        for result in self.stage.expire():
            if note := self._settle(result):
                self.append_note(note)

    def _settle(self, result: StageResult) -> str | None:
        """A move that did not land is told plainly, with what the page offers."""
        if result.moved or result.outcome in ("applied", "partial", "undone"):
            return None
        if any(r.why == "interrupted" for r in result.refused):
            return None
        offers = "; ".join(
            f"{r.arg}: {r.why}" + (f" (options: {', '.join(r.options[:8])})" if r.options else "")
            for r in result.refused
        )
        return (
            f"[Your {result.move} move did not happen on screen ({result.detail or result.outcome}"
            + (f"; {offers}" if offers else "")
            + "). Never say it did.]"
        )

    def _visitor_did(self, event: StageEvent) -> str | None:
        """Fold a change the page reports into the trip. The agent's own moves
        come back ``by: "agent"`` and are already in it."""
        folded = self.stage.handle(event)
        data: dict[str, Any] = dict(event.data)
        if event.name == "trip.page_changed":
            self.page = str(data.get("page") or self.page)
        if event.name == "trip.paid" and (ref := str(data.get("reference") or "")):
            self.booked = ref
            self._say_soon(self._line("paid", reference=" ".join(ref)))
            return f"The visitor paid. Booking reference {ref}. It is booked."
        if event.by != "visitor":
            return None
        t = self.trip
        name = event.name
        if name == "trip.brief_changed":
            field, value = str(data.get("field") or ""), str(data.get("value") or "")
            self._apply_brief_field(field, value)
        elif name == "trip.flight_picked":
            if (fid := str(data.get("flight_id") or "")) in eng.FLIGHTS:
                t.flight_id = fid
                self._lead_after_click(
                    lead.line(self.lang, "flight_in", airline=eng.FLIGHTS[fid]["airline_name"])
                )
        elif name == "trip.hotel_picked":
            city, hid, rid = (str(data.get(k) or "") for k in ("city", "hotel_id", "room_id"))
            if hid in eng.HOTELS and eng.HOTELS[hid]["city"] == city:
                t.hotels[city] = (hid, rid)
                self._lead_after_click(
                    lead.line(self.lang, "hotel_in", hotel=eng.HOTELS[hid]["name"])
                )
        elif name == "trip.nights_changed":
            split = data.get("split")
            if isinstance(split, list):
                self._set_split([int(str(x)) for x in split if str(x).isdigit()])  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
        elif name == "trip.activity_added":
            aid, day = str(data.get("activity_id") or ""), data.get("day")
            if aid in eng.ACTIVITIES and isinstance(day, int) and (day, aid) not in t.activities:
                t.activities.append((day, aid))
        elif name == "trip.activity_removed":
            aid, day = str(data.get("activity_id") or ""), data.get("day")
            t.activities = [x for x in t.activities if x != (day, aid)]
        elif name == "trip.step_changed":
            return None
        note = folded.note if folded is not None else None
        if note and name not in ("trip.page_changed",):
            return f"{note}. {self.total_line()}" if t.destination else note
        return None

    def _lead_after_click(self, ack: str) -> None:
        """The visitor picked by hand: in the next quiet moment, a happy word and
        the next step as a question. Nothing on screen moves for them; their
        click was the choice, and the next one is theirs too (H1)."""
        self._say_soon(f"{ack} {lead.offer(self.trip, self.lang)}")

    def _apply_brief_field(self, field: str, value: str) -> None:
        t = self.trip
        if field == "from_city" and value in eng.ORIGINS and value != t.from_city:
            t.from_city, t.flight_id = value, None
        elif field == "destination" and value in eng.DESTINATIONS and value != t.destination:
            self._set_destination(value)
        elif field == "start_date" and eng._parse_date(value):  # pyright: ignore[reportPrivateUsage]
            t.start_date = value
            self._revalidate()
        elif field == "nights" and value.isdigit():
            self._set_nights_total(int(value))
        elif field == "adults" and value.isdigit():
            t.adults = int(value)
            self._revalidate()
        elif field == "kids":
            t.kids = [int(x) for x in value.replace(" ", "").split(",") if x.isdigit()]
            self._revalidate()
        elif field == "budget" and value.isdigit():
            t.budget = int(value)
        elif field == "style" and value in eng.STYLES:
            t.style = value  # pyright: ignore[reportAttributeAccessIssue]

    # ─── The trip's own rules (CONTRACT.md, "The trip") ─────────────────

    def _set_destination(self, did: str) -> None:
        t = self.trip
        t.destination, t.flight_id, t.hotels, t.activities = did, None, {}, []
        d = eng.DESTINATIONS[did]
        if t.nights and not eng._nights_ok(d, t.nights):  # pyright: ignore[reportPrivateUsage]
            t.nights = None
        t.split = eng.default_split(d, t.nights) if t.nights else []

    def _set_nights_total(self, nights: int) -> None:
        t = self.trip
        if t.nights == nights:
            return
        t.nights = nights
        t.split = eng.default_split(t.dest, nights) if t.dest else []
        self._drop_empty_cities()
        self._revalidate()

    def _set_split(self, split: list[int]) -> None:
        if eng.valid_split(self.trip, split):
            self.trip.split = split
            self._drop_empty_cities()
            self._revalidate()

    def _drop_empty_cities(self) -> None:
        keep = dict(eng.stops(self.trip))
        self.trip.hotels = {c: h for c, h in self.trip.hotels.items() if c in keep}

    def _revalidate(self) -> list[str]:
        """Re-check every activity in order; drop the ones that no longer fit."""
        t = self.trip
        kept: list[tuple[int, str]] = []
        dropped: list[str] = []
        for day, aid in t.activities:
            trial = replace(t, activities=kept)
            if eng.can_add(trial, aid, day) is None:
                kept.append((day, aid))
            else:
                dropped.append(eng.ACTIVITIES[aid]["name"])
        t.activities = kept
        return dropped

    # ─── What the model reads ───────────────────────────────────────────

    def total_line(self) -> str:
        p = eng.price(self.trip)
        line = f"Total now {eng.money(p.total)} ({eng.money(p.per_person)} per person)"
        if self.trip.budget:
            gap = self.trip.budget - p.total
            line += (
                f", {eng.money(gap)} under the {eng.money(self.trip.budget)} budget"
                if gap >= 0
                else f", {eng.money(-gap)} over the {eng.money(self.trip.budget)} budget"
            )
        return line + "."

    def state_line(self) -> str:
        t = self.trip
        parts = []
        if t.from_city:
            parts.append(f"from {eng.ORIGINS[t.from_city]}")
        if t.dest:
            parts.append(f"to {t.dest['name']}")
        if t.start_date:
            parts.append(f"leaving {eng.day_label(date.fromisoformat(t.start_date))}")
        if t.nights:
            parts.append(f"{t.nights} nights")
        who = f"{t.adults} adult{'s' if t.adults != 1 else ''}"
        if t.kids:
            who += f" and children aged {', '.join(map(str, t.kids))}"
        parts.append(who)
        if t.budget:
            parts.append(f"budget {eng.money(t.budget)}")
        if t.style:
            parts.append(f"{t.style} style")
        line = ", ".join(parts) + "."
        if t.split and t.dest:
            line += (
                " Nights: "
                + ", ".join(f"{eng.CITIES[c]['name']} {n}" for c, n in eng.stops(t))
                + "."
            )
        if f := eng.FLIGHTS.get(t.flight_id or ""):
            line += f" Flight: {f['airline_name']}, {'nonstop' if not f['stops'] else str(f['stops']) + ' stop'}."
        for city, (hid, rid) in t.hotels.items():
            h = eng.HOTELS[hid]
            room = next(r["name"] for r in h["rooms"] if r["id"] == rid)
            line += f" {eng.CITIES[city]['name']}: {h['name']}, {room}."
        if t.activities:
            line += (
                " Activities: "
                + "; ".join(f"day {d} {eng.ACTIVITIES[a]['name']}" for d, a in sorted(t.activities))
                + "."
            )
        if t.dest and (t.flight_id or t.hotels):
            line += " " + self.total_line()
        if missing := t.missing():
            line += f" Brief still needs: {', '.join(missing)}."
        return line

    def describe(self, t: Trip) -> str:
        """The package as the model may say it: every fact with its price."""
        p = eng.price(t)
        out: list[str] = []
        if f := eng.FLIGHTS.get(t.flight_id or ""):
            adult, total = eng.flight_price(t, f)
            out.append(
                f"Flight: {self._flight_words(f)}; {eng.money(adult)} per adult, {eng.money(total)} for the group."
            )
        for city, n in eng.stops(t):
            if pick := t.hotels.get(city):
                h = eng.HOTELS[pick[0]]
                room = next(r for r in h["rooms"] if r["id"] == pick[1])
                out.append(
                    f"{eng.CITIES[city]['name']}, {n} night{'s' if n != 1 else ''}: {h['name']} ({h['stars']} star, {h['area']}), "
                    f"{room['name']}, {eng.money(room['price'])} a night x {eng.rooms(t)} room(s) = "
                    f"{eng.money(eng.hotel_price(t, city, *pick))}; includes {', '.join(h['inclusions'])}."
                )
        for d in eng.days(t):
            acts = [eng.ACTIVITIES[a] for n, a in t.activities if n == d.n]
            when = eng.day_label(d.date) if d.date else ""
            what = {
                "arrival": "arrive",
                "transfer": "move to " + eng.CITIES[d.city]["name"],
                "departure": "fly home",
                "full": "free",
            }[d.kind]
            line = f"Day {d.n} {when} in {eng.CITIES[d.city]['name']}: {what}"
            if acts:
                line += "; " + "; ".join(
                    f"{a['name']} ({a['duration']}, {a['slot'].replace('_', ' ')}, {eng.money(eng.activity_price(t, a['id']))})"
                    for a in acts
                )
            out.append(line + ".")
        legs = eng.transfer_legs(t)
        if legs:
            out.append(
                "Transfers: "
                + "; ".join(f"{leg.label} by {leg.mode} {eng.money(leg.price)}" for leg in legs)
                + "."
            )
        out.append(
            f"Price: flights {eng.money(p.flights)}, hotels {eng.money(p.hotels)}, transfers {eng.money(p.transfers)}, "
            f"activities {eng.money(p.activities)}, GST 5% on the land part {eng.money(p.gst)}. "
            f"Total {eng.money(p.total)}, {eng.money(p.per_person)} per person."
        )
        if t.budget:
            gap = t.budget - p.total
            out.append(
                f"That is {eng.money(gap)} under their {eng.money(t.budget)} budget."
                if gap >= 0
                else f"That is {eng.money(-gap)} OVER their {eng.money(t.budget)} budget: offer cheaper hotels or fewer activities."
            )
        return "\n".join(out)

    def _flight_words(self, f: dict[str, Any]) -> str:
        def journey(j: dict[str, Any]) -> str:
            legs = j["legs"]
            first, last = legs[0], legs[-1]
            via = (
                "nonstop"
                if len(legs) == 1
                else "via "
                + ", ".join(eng.INVENTORY["airports"][leg["to"]]["city"] for leg in legs[:-1])
            )
            h, m = divmod(int(j["minutes"]), 60)
            nd = " next day" if last["arrive_day"] > first["depart_day"] else ""
            return f"{first['depart']} {first['from']} to {last['arrive']}{nd} {last['to']}, {via}, {h}h {m:02d}m"

        return (
            f"{f['airline_name']} ({f['kind']}), out {journey(f['out'])}; back {journey(f['back'])}; "
            f"{f['baggage']}; {f['meal']}"
        )

    def sorted_flights(self, sort: FlightSort) -> list[dict[str, Any]]:
        """The options in the order the page lists them (CONTRACT.md)."""
        options = eng.flights_for(self.trip)
        if sort == "price":
            return sorted(options, key=lambda f: f["fare_adult"])
        if sort == "duration":
            return sorted(options, key=lambda f: f["out"]["minutes"])
        if sort == "departure":
            return sorted(options, key=lambda f: f["out"]["legs"][0]["depart"])
        best = eng.recommended_flight(self.trip)
        rest = sorted((f for f in options if f is not best), key=lambda f: f["fare_adult"])
        return [best, *rest] if best else rest

    # ─── Leading: the next step (H1) ────────────────────────────────────

    def next_note(self) -> str:
        """The next step, for the model: where you lead them now."""
        kind, city = lead.next_step(self.trip)
        return {
            "brief": "Next: finish the brief.",
            "flights": "Next: flights (or the whole package in one go).",
            "hotels": f"Next: a hotel in {eng.CITIES[city]['name'] if city else ''}.",
            "days": "Next: activities for their days.",
            "package": "Next: the package and checkout.",
        }[kind]

    def _hotel_options(self, city: str) -> tuple[list[dict[str, Any]], str | None]:
        """A city's hotels for this trip, those that fit its style first; and the
        filter the page should show, when one fits."""
        style = self.trip.style or ("family" if self.trip.kids else None)
        every = list(eng.CITIES[city]["hotels"])
        if style:
            fit = [h for h in every if style in h["tags"]]
            if fit and len(fit) < len(every):
                return fit, style
            if fit:
                return fit, None
        return every, None

    def _opens(self, t: Trip) -> tuple[str, tuple[str, ...], str, str]:
        """What the trip's next unfilled step puts in front of the visitor: the
        brain's line for it (the next choice), the names any presentation of it
        would say, the step for the model with its options, and the Stage move
        that opens it ("" for none). Read off ``t``, so it previews a pick not
        yet made as well as it describes one just made (H3)."""
        kind, city = lead.next_step(t)
        total = eng.money(eng.price(t).total)
        if kind == "hotels" and city:
            found, _ = self._hotel_options(city)
            nights = dict(eng.stops(t)).get(city, 0)
            return (
                lead.hotels_line(city, found, self.lang),
                tuple(h["name"] for h in found),
                f"the hotels step opens on {eng.CITIES[city]['name']} ({nights} nights). Present the "
                "two that suit them best, each with one vivid detail and its price for their nights, "
                "and ask which:\n" + "\n".join(self._hotel_line(city, h) for h in found),
                "hotels",
            )
        if kind == "days":
            fits = self._fits(None, None, t)
            if not fits:
                return (
                    lead.line(self.lang, "package", total=total),
                    _PACKAGE_WORDS,
                    "nothing more fits their days: say the total and offer the package or checkout.",
                    "days",
                )
            day, first = fits[0]
            return (
                f"{lead.line(self.lang, 'days')} "
                f"{lead.activity_line(t, day, eng.ACTIVITIES[first['id']], self.lang)}",
                tuple(a["name"] for _, a in fits[:6]),
                "the days step opens. Suggest one or two of these that suit them, with one vivid "
                "detail and the price, and ask whether to add one:\n"
                + self._activity_lines(fits, 5, t),
                "days",
            )
        if kind == "package":
            return (
                lead.line(self.lang, "package", total=total),
                _PACKAGE_WORDS,
                "every step has something in it: say the total and offer another activity, a look "
                "at the whole package, or review and book.",
                "",
            )
        return lead.offer(t, self.lang), (), f"{self.next_note()}", ""

    def ahead(self, hotel_city: str | None = None) -> str:
        """What opens after the visitor's next pick, for the model to say in the
        same response as the pick's call (H3): the pick tools do not wait for a
        result, so this is the only time the model can know it. Empty when the
        step in front is not a pick."""
        t = self.trip
        kind, city = lead.next_step(t)
        if hotel_city is not None and t.flight_id:
            kind, city = "hotels", hotel_city
        if kind == "flights":
            best = eng.recommended_flight(t)
            if best is None:
                return ""
            trial, thing, tool = replace(t, flight_id=best["id"]), "a flight", "choose_flight"
        elif kind == "hotels" and city:
            trial = replace(t, hotels={**t.hotels, city: eng.recommended_hotel(t, city)})
            thing, tool = f"a hotel in {eng.CITIES[city]['name']}", "choose_hotel"
        elif kind in ("days", "package") and self._fits(None, None, t):
            return (
                "AFTER THEIR PICK: when they choose an activity, call add_activity and, in the same "
                "response, say it is in with a happy word and offer one more that fits (or the whole "
                "package and booking). The tool gives you nothing more to say."
            )
        else:
            return ""
        _, _, step, _ = self._opens(trial)
        return (
            f"AFTER THEIR PICK: when they choose {thing}, call {tool} and, in the same response as "
            f"the call, say it is in with a happy word, then {step}\nThe tool gives you nothing "
            "more to say: everything for that reply is here."
        )

    def _advance(self, lead_in: str) -> str:
        """After a pick landed: open the next unfilled step on screen (a city's
        hotels, the days with activities that fit), owe the brain's own line —
        ``lead_in`` and the next choice, or the next choice alone when the
        model's words named none of it (H3) — and return what is on screen now,
        for the model's next request.

        Nothing is chosen for the visitor here: the next step's options are put
        in front of them, and they pick by voice or by click."""
        t = self.trip
        _, city = lead.next_step(t)
        then, cover, step, move = self._opens(t)
        if move == "hotels" and city:
            _, want = self._hotel_options(city)
            args: dict[str, Any] = {"city": city}
            if want:
                args["want"] = want
            self._send("trip.hotels", args)
        elif move == "days":
            self._send("trip.step", {"step": "days"})
        owe(f"{lead_in} {then}", then=then, cover=cover)
        return (
            f"{self.total_line()}\nOn screen now: {step}\n"
            "They have been offered it (by you, or in the brain's words just after); do not "
            "offer it again, take their answer."
        )

    def _activity_lines(
        self, fits: list[tuple[int, dict[str, Any]]], limit: int, t: Trip | None = None
    ) -> str:
        t = t or self.trip
        by_act: dict[str, tuple[dict[str, Any], list[int]]] = {}
        for n, a in fits:
            by_act.setdefault(a["id"], (a, []))[1].append(n)
        lines = []
        for a, ds in list(by_act.values())[:limit]:
            city = eng.ACTIVITIES[a["id"]]["city"]
            lines.append(
                f"{a['name']} ({eng.CITIES[city]['name']}, {a['duration']}, {a['slot'].replace('_', ' ')}): {a['blurb']} "
                f"{eng.money(eng.activity_price(t, a['id']))} for the group; fits day {', '.join(map(str, ds))}."
            )
        return "\n".join(lines)

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        return [
            self.list_destinations,
            self.set_trip,
            self.show_flights,
            self.choose_flight,
            self.show_hotels,
            self.choose_hotel,
            self.set_nights,
            self.suggest_activities,
            self.add_activity,
            self.remove_activity,
            self.build_package,
            self.trip_summary,
            self.go_to_checkout,
            # Only when persona.json offers more than one language (H2).
            *([self.set_language] if len(LANGUAGES) > 1 else []),
        ]

    def _send(self, move: str, args: dict[str, Any]) -> None:
        self.stage.send(move, args)

    @needs_result_now
    async def list_destinations(self, query: DestinationQuery) -> str:
        """The destinations Wanderloom sells, with their 'from' price per person
        (two adults, cheapest hotels, no activities) and best months. Use it to
        help someone choose."""
        origin = self.trip.from_city or "DEL"
        start = resolve_month(query.month, self.today) if query.month else None
        month = start.month if start else None
        lines = []
        for d in eng.DESTINATIONS.values():
            if query.domestic is not None and d["domestic"] != query.domestic:
                continue
            if query.style and not any(
                query.style in a["tags"] for c in d["cities"] for a in c["activities"]
            ):
                continue
            season = ""
            if month:
                season = (
                    " In season then."
                    if month in d["best_months"]
                    else " Not its best season then."
                )
            lines.append(
                f"{d['name']} ({'India' if d['domestic'] else d['country']}): {d['tagline']}. "
                f"From {eng.money(eng.from_price(d['id'], origin))} per person from {eng.ORIGINS[origin]}, "
                f"{d['default_nights']} nights.{season}"
            )
        return "\n".join(lines)

    @needs_result_now
    async def set_trip(self, brief: TripBrief) -> str:
        """Put what the visitor said into the trip brief on screen (from-city,
        destination, dates or month, nights, travellers, budget, style). Call it as
        soon as they give any of it, with all of it. Returns the brief as it now
        stands and what is still missing."""
        t = self.trip
        notes: list[str] = []
        sent: dict[str, Any] = {}
        if brief.from_city:
            code = resolve_origin(brief.from_city)
            if code is None:
                notes.append(
                    f"Wanderloom does not fly from {brief.from_city}. It flies from {', '.join(eng.ORIGINS.values())}."
                )
            elif code != t.from_city:
                t.from_city, t.flight_id = code, None
                sent["from_city"] = code
        if brief.destination:
            did = resolve_destination(brief.destination)
            if did is None:
                notes.append(
                    f"Wanderloom does not sell {brief.destination}. It sells "
                    + ", ".join(d["name"] for d in eng.DESTINATIONS.values())
                    + "."
                )
            elif did != t.destination:
                self._set_destination(did)
                sent["destination"] = did
        start: date | None = None
        if brief.start_date:
            start = eng._parse_date(brief.start_date)  # pyright: ignore[reportPrivateUsage]
            if start is None:
                notes.append(f"{brief.start_date} is not a date.")
        elif brief.month:
            start = resolve_month(brief.month, self.today)
            if start is None:
                notes.append(f"{brief.month} is not a month I can use.")
            else:
                notes.append(
                    f"For {brief.month} I picked {eng.day_label(start)}; they can change the date."
                )
        if start is not None:
            if start < eng.earliest(self.today):
                notes.append(
                    f"Trips must leave on or after {eng.day_label(eng.earliest(self.today))}; the date was not set."
                )
            elif start.isoformat() != t.start_date:
                t.start_date = start.isoformat()
                sent["start_date"] = t.start_date
        if brief.adults is not None or brief.kids_ages is not None:
            kids = list(t.kids if brief.kids_ages is None else brief.kids_ages)
            adults = t.adults if brief.adults is None else brief.adults
            older = [k for k in kids if k > eng.RULES["child_max_age"]]
            if older:
                adults += len(older)
                kids = [k for k in kids if k <= eng.RULES["child_max_age"]]
                notes.append(f"Children aged {', '.join(map(str, older))} count as adults.")
            if not 1 <= adults + len(kids) <= eng.RULES["max_travellers"] or adults < 1:
                notes.append(
                    f"A booking here is 1 to {eng.RULES['max_travellers']} travellers with at least one adult; not changed."
                )
            else:
                if adults != t.adults:
                    t.adults = adults
                    sent["adults"] = adults
                if kids != t.kids:
                    t.kids = kids
                    sent["kids"] = [str(k) for k in kids]
        if brief.nights is not None:
            d = t.dest
            if d and not eng._nights_ok(d, brief.nights):  # pyright: ignore[reportPrivateUsage]
                notes.append(
                    f"{d['name']} is sold for {d['nights'][0]} to {d['nights'][1]} nights; nights not set."
                )
            elif brief.nights != t.nights:
                self._set_nights_total(brief.nights)
                sent["nights"] = brief.nights
        if brief.budget is not None:
            budget = brief.budget * (t.pax if brief.budget_per_person else 1)
            if (why := implausible({"budget": budget}, self._heard_recent[::-1])) is not None:
                notes.insert(0, why)  # first, so the model confirms before anything else
            elif budget != t.budget:
                t.budget = budget
                sent["budget"] = budget
        if brief.style and brief.style != t.style:
            t.style = brief.style
            sent["style"] = brief.style
        if dropped := self._revalidate():
            notes.append(f"Dropped because they no longer fit: {', '.join(dropped)}.")
        if sent:
            self._send("trip.brief", sent)
        owe(lead.brief_line(t, self.lang))
        missing = t.missing()
        head = "Brief now: " + self.state_line()
        if missing:
            ask = {
                "from_city": "where they fly from",
                "destination": "where to",
                "start_date": "when (a date or a month)",
                "nights": "how many nights",
            }
            tail = (
                "Still need: "
                + ", ".join(ask[m] for m in missing)
                + ". React warmly to what they gave, then ask only for that."
            )
            if t.dest and "nights" in missing:
                tail += f" {t.dest['name']} is sold for {t.dest['nights'][0]} to {t.dest['nights'][1]} nights, usually {t.dest['default_nights']}."
        else:
            d = t.dest
            assert d is not None
            tail = (
                f"The brief is complete. NEXT, in this same reply: be excited for them, with one vivid "
                f"detail of {d['name']} ({d['tagline']}), then offer the two ways: the flights first, "
                "or the whole package built in one go."
            )
        return "\n".join([*notes, head, tail])

    def _missed(self, why: str, said: str) -> str:
        """A pick that did not happen (H3). The tool does not wait, so the model
        may already have said it did: the brain says ``said`` after it, whatever
        the model said, and the model reads ``why`` with its next request."""
        owe(said, always=True)
        return (why + " " if why else "") + f"Not done; the visitor was told: {said!r}"

    def _need_brief(self) -> str | None:
        if missing := self.trip.missing():
            return f"Not yet: the brief still needs {', '.join(missing)}. Ask for it, then call set_trip."
        return None

    @needs_result_now
    async def show_flights(self, request: FlightsRequest) -> str:
        """Put the round-trip flight options on screen and read them, numbered as
        the screen numbers them."""
        if why := self._need_brief():
            return why
        self.flight_sort = request.sort
        self._send("trip.flights", {"sort": request.sort})
        owe(
            lead.line(
                self.lang,
                "flights",
                origin=eng.ORIGINS[self.trip.from_city or "DEL"],
                pick=lead.flight_line(self.trip, self.lang),
            )
        )
        options = self.sorted_flights(request.sort)
        best = eng.recommended_flight(self.trip)
        out = [
            f"{len(options)} options from {eng.ORIGINS[self.trip.from_city or 'DEL']}, sorted {request.sort}:"
        ]
        for i, f in enumerate(options, 1):
            adult, total = eng.flight_price(self.trip, f)
            tag = " (suggested: best-value nonstop)" if f is best else ""
            chosen = " (in the trip now)" if f["id"] == self.trip.flight_id else ""
            out.append(
                f"{i}. {self._flight_words(f)}; {eng.money(adult)} per adult, {eng.money(total)} for the group{tag}{chosen}."
            )
        if eng.season_pct(self.trip) != 100:
            out.append("These fares include the season's peak pricing for that month.")
        out.append(
            "Say the two or three that matter (time, stops, price for the group), which you suggest "
            "and why, and ask which one to add."
        )
        if ahead := self.ahead():
            out.append(ahead)
        return "\n".join(out)

    async def choose_flight(self, choice: FlightChoice) -> str:
        """Put the flight option the visitor picked into the trip. Opens the next
        step (a city's hotels) at once: in the same response as this call, say
        the flight is in and present that step, as AFTER THEIR PICK said."""
        if why := self._need_brief():
            return self._missed(why, lead.ask_missing(self.trip, self.lang))
        options = self.sorted_flights(self.flight_sort)
        said = _fold(choice.choice)
        pick: dict[str, Any] | None = None
        digits = "".join(ch for ch in said if ch.isdigit())
        words = {"first": 1, "one": 1, "second": 2, "two": 2, "third": 3, "three": 3}
        n = int(digits) if digits else next((v for k, v in words.items() if k in said.split()), 0)
        if choice.choice in eng.FLIGHTS:
            pick = eng.FLIGHTS[choice.choice]
        elif 1 <= n <= len(options):
            pick = options[n - 1]
        elif "cheap" in said:
            pick = min(options, key=lambda f: f["fare_adult"])
        elif "nonstop" in said or "direct" in said:
            pick = next((f for f in options if f["stops"] == 0), None)
        else:
            hit = match_label(choice.choice, [f["airline_name"] for f in options])
            pick = next((f for f in options if f["airline_name"] == hit), None)
        if pick is None:
            names = [f["airline_name"] for f in options]
            return self._missed(
                f"No option matches '{choice.choice}'. Options: "
                + "; ".join(f"{i}. {n}" for i, n in enumerate(names, 1)),
                f"Sorry, I couldn't match that to a flight. On screen there's {_or(names)}. "
                "Which one shall I add?",
            )
        self.trip.flight_id = pick["id"]
        self._revalidate()
        self._send("trip.flight", {"flight_id": pick["id"]})
        nxt = self._advance(lead.line(self.lang, "flight_in", airline=pick["airline_name"]))
        return f"{pick['airline_name']} is in the trip. {nxt}"

    def _city(self, said: str) -> str | None:
        d = self.trip.dest
        if not d:
            return None
        names = {c["name"]: c["id"] for c in d["cities"]}
        if said in names.values():
            return said
        hit = match_label(said, list(names))
        return names.get(hit) if hit else None

    def _hotel_matches(self, city: str, want: str | None) -> list[dict[str, Any]]:
        hotels = eng.CITIES[city]["hotels"]
        if not want:
            return list(hotels)
        w = _fold(want)
        if "luxur" in w or "5 star" in w or "five star" in w:
            return [h for h in hotels if h["stars"] == 5]
        if "budget" in w or "cheap" in w:
            return [h for h in hotels if "budget" in h["tags"] or h["stars"] == 3]
        if "pool" in w:
            return [h for h in hotels if any("pool" in r["name"].lower() for r in h["rooms"])]
        tag = next(
            (
                t
                for t in ("beach", "family", "honeymoon", "relaxed", "adventure", "culture")
                if t[:4] in w
            ),
            None,
        )
        return [h for h in hotels if tag in h["tags"]] if tag else list(hotels)

    def _hotel_line(self, city: str, h: dict[str, Any]) -> str:
        nights = dict(eng.stops(self.trip)).get(city, 0)
        rooms = "; ".join(
            f"{r['name']} {eng.money(r['price'])} a night ({eng.money(r['price'] * nights * eng.rooms(self.trip))} for {nights} nights, {eng.rooms(self.trip)} room(s))"
            for r in h["rooms"]
        )
        mine = " (in the trip now)" if self.trip.hotels.get(city, ("",))[0] == h["id"] else ""
        return f"{h['name']}, {h['stars']} star, {h['area']}: {h['blurb']} Includes {', '.join(h['inclusions'])}. Rooms: {rooms}.{mine}"

    @needs_result_now
    async def show_hotels(self, request: HotelsRequest) -> str:
        """Put one city's hotels on screen, optionally only those that fit what the
        visitor wants, and read them."""
        if why := self._need_brief():
            return why
        city = self._city(request.city)
        if city is None:
            cities = self.trip.dest["cities"] if self.trip.dest else []
            return f"{request.city} is not on this trip. Cities: " + ", ".join(
                c["name"] for c in cities
            )
        nights = dict(eng.stops(self.trip)).get(city, 0)
        found = self._hotel_matches(city, request.want)
        out: list[str] = []
        if not nights:
            out.append(
                f"{eng.CITIES[city]['name']} has no nights in this trip now; use set_nights to add some."
            )
        if request.want and not found:
            others = [
                (c["id"], h)
                for c, _ in [(eng.CITIES[cid], n) for cid, n in eng.stops(self.trip)]
                if c["id"] != city
                for h in self._hotel_matches(c["id"], request.want)
            ]
            inland = (
                " It is inland."
                if eng.CITIES[city].get("inland") and "beach" in request.want.lower()
                else ""
            )
            out.append(f"No hotel in {eng.CITIES[city]['name']} fits '{request.want}'.{inland}")
            if others:
                out.append(
                    "Elsewhere on this trip: "
                    + " | ".join(
                        f"{eng.CITIES[c]['name']}: {self._hotel_line(c, h)}" for c, h in others
                    )
                    + " Offer to move nights there with set_nights, or keep this city's hotel."
                )
            self._send("trip.hotels", {"city": city})
            owe(self._line("hotels", city=eng.CITIES[city]["name"]))
            return "\n".join(out)
        args: dict[str, Any] = {"city": city}
        if request.want:
            args["want"] = request.want
        self._send("trip.hotels", args)
        owe(lead.hotels_line(city, found, self.lang))
        out.append(f"Hotels in {eng.CITIES[city]['name']} ({nights} nights):")
        out += [self._hotel_line(city, h) for h in found]
        out.append(
            "Present the two that suit them best, each with one vivid detail and its price for "
            "their nights, and ask which one to add."
        )
        if nights and (ahead := self.ahead(hotel_city=city)):
            out.append(ahead)
        return "\n".join(out)

    async def choose_hotel(self, choice: HotelChoice) -> str:
        """Put a hotel (and room) into the trip for its city, replacing the one
        there. Opens the next step (the next city's hotels, or the days with
        activities) at once: in the same response as this call, say the hotel is
        in and present that step, as AFTER THEIR PICK said."""
        if why := self._need_brief():
            return self._missed(why, lead.ask_missing(self.trip, self.lang))
        d = self.trip.dest
        assert d is not None
        hotels = {h["name"]: h for c in d["cities"] for h in c["hotels"]}
        hit = match_label(choice.hotel, list(hotels))
        if hit is None:
            return self._missed(
                f"No hotel on this trip is called '{choice.hotel}'. Hotels: {', '.join(hotels)}.",
                "Sorry, I couldn't match that to a hotel on this trip. Which one did you mean?",
            )
        h = hotels[hit]
        city = h["city"] if "city" in h else eng.HOTELS[h["id"]]["city"]
        if not dict(eng.stops(self.trip)).get(city):
            cname = eng.CITIES[city]["name"]
            return self._missed(
                f"{h['name']} is in {cname}, which has no nights in this trip. Offer set_nights first.",
                f"{h['name']} is in {cname}, and the trip has no nights there yet. "
                f"Shall I move a night or two to {cname}?",
            )
        room = h["rooms"][0]
        if choice.room:
            rhit = match_label(choice.room, [r["name"] for r in h["rooms"]])
            if rhit is None:
                rooms = [r["name"] for r in h["rooms"]]
                return self._missed(
                    f"{h['name']} has: {', '.join(rooms)}.",
                    f"{h['name']} has {_or(rooms)}. Which room would you like?",
                )
            room = next(r for r in h["rooms"] if r["name"] == rhit)
        before = eng.price(self.trip).total
        self.trip.hotels[city] = (h["id"], room["id"])
        self._send("trip.hotel", {"city": city, "hotel_id": h["id"], "room_id": room["id"]})
        after = eng.price(self.trip).total
        diff = after - before
        stay = eng.hotel_price(self.trip, city, h["id"], room["id"])
        change = f"{eng.money(stay)} for the stay; the total moved by {eng.money(abs(diff))} " + (
            "(hotel changes carry 5% GST)" if diff else "(the same price)"
        )
        nxt = self._advance(lead.line(self.lang, "hotel_in", hotel=h["name"]))
        return f"{h['name']}, {room['name']}, is in for {eng.CITIES[city]['name']}: {change}. {nxt}"

    async def set_nights(self, request: NightsRequest) -> str:
        """Change how many nights are spent in one city; the other cities give or
        take the difference, so the trip's length stays the same. Returns at
        once: say the change in the same response as this call."""
        if why := self._need_brief():
            return self._missed(why, lead.ask_missing(self.trip, self.lang))
        t = self.trip
        d = t.dest
        assert d is not None
        city = self._city(request.city)
        if city is None:
            names = [c["name"] for c in d["cities"]]
            return self._missed(
                f"{request.city} is not on this trip. Cities: " + ", ".join(names),
                f"{request.city} isn't on this trip; it goes to {_or(names, 'and')}.",
            )
        ids = [c["id"] for c in d["cities"]]
        split = list(t.split)
        i = ids.index(city)
        want = max(0, min(request.nights, t.nights or 0))
        diff = want - split[i]
        for j in reversed([j for j in range(len(ids)) if j != i]):
            if diff > 0:
                take = min(diff, split[j])
                split[j] -= take
                diff -= take
            elif diff < 0:
                split[j] += -diff
                diff = 0
        split[i] = want
        if diff != 0 or not eng.valid_split(t, split):
            now = ", ".join(f"{eng.CITIES[c]['name']} {n}" for c, n in eng.stops(t))
            order = ", ".join(eng.CITIES[c]["name"] for c in ids)
            return self._missed(
                f"That split cannot be served: {d['name']}'s cities in order are {order}, "
                f"and the trip is {t.nights} nights. Current: {now}.",
                f"I can't split the nights that way; right now it's {now}.",
            )
        before = {a for _, a in t.activities}
        self._set_split(split)
        dropped = [eng.ACTIVITIES[a]["name"] for a in before - {a for _, a in t.activities}]
        self._send("trip.nights", {"split": [str(n) for n in split]})
        for c, _ in eng.stops(t):
            if c not in t.hotels and t.flight_id:
                t.hotels[c] = eng.recommended_hotel(t, c)
                hid, rid = t.hotels[c]
                self._send("trip.hotel", {"city": c, "hotel_id": hid, "room_id": rid})
        nxt = self._advance(lead.line(self.lang, "nights_in", split=lead.split_words(t)))
        out = (
            "Nights now: "
            + ", ".join(f"{eng.CITIES[c]['name']} {n}" for c, n in eng.stops(t))
            + "."
        )
        if dropped:
            out += f" Dropped because their day moved: {', '.join(dropped)}."
        return out + " " + self.state_line() + "\n" + nxt

    def _fits(
        self, city: str | None, day: int | None, t: Trip | None = None
    ) -> list[tuple[int, dict[str, Any]]]:
        t = t or self.trip
        style = t.style or ("family" if t.kids else "relaxed")
        out: list[tuple[int, dict[str, Any]]] = []
        for d in eng.days(t):
            if (day and d.n != day) or (city and d.city != city):
                continue
            stay = eng.HOTELS[t.hotels[d.city][0]]["inclusions"] if d.city in t.hotels else []
            for a in eng.CITIES[d.city]["activities"]:
                if (
                    eng.can_add(t, a["id"], d.n) is None
                    and all(a["id"] != x for _, x in t.activities)
                    and not _included(a["name"], stay)
                ):
                    out.append((d.n, a))
        out.sort(key=lambda x: (style not in x[1]["tags"], x[0]))
        return out

    @needs_result_now
    async def suggest_activities(self, request: ActivitiesRequest) -> str:
        """The activities that fit a day or a city of the trip, best for their
        style first, with price for the group, and the days they fit."""
        if why := self._need_brief():
            return why
        city = self._city(request.city) if request.city else None
        fits = self._fits(city, request.day)
        self._send("trip.step", {"step": "days"})
        if not fits:
            day = next((d for d in eng.days(self.trip) if d.n == request.day), None)
            if day and day.kind in ("arrival", "transfer"):
                return f"Day {day.n} is a travel day with only the evening free, and nothing else fits it."
            return "Nothing more fits there: the slots are taken, it is a travel day, or the ages or weekday rule it out."
        day, first = fits[0]
        owe(lead.activity_line(self.trip, day, eng.ACTIVITIES[first["id"]], self.lang))
        return (
            self._activity_lines(fits, 8)
            + "\nSuggest one or two that suit them, each with one vivid detail and the price, and ask "
            "whether to add one.\n" + self.ahead()
        )

    def _activity(self, said: str) -> dict[str, Any] | None:
        d = self.trip.dest
        if not d:
            return None
        acts = {a["name"]: a for c in d["cities"] for a in c["activities"]}
        hit = match_label(said, list(acts))
        return acts.get(hit) if hit else None

    async def add_activity(self, choice: ActivityChoice) -> str:
        """Add an activity to a day of the trip (the first day it fits, if no day
        was said). Returns at once: in the same response as this call, say it is
        in and offer one more that fits, or the package."""
        if why := self._need_brief():
            return self._missed(why, lead.ask_missing(self.trip, self.lang))
        a = self._activity(choice.activity)
        if a is None:
            return self._missed(
                f"No activity on this trip is called '{choice.activity}'. Use suggest_activities.",
                "Sorry, I couldn't find that activity on this trip. Shall I suggest a few?",
            )
        a = eng.ACTIVITIES[a["id"]]
        day = choice.day
        if day is None:
            day = next(
                (d.n for d in eng.days(self.trip) if eng.can_add(self.trip, a["id"], d.n) is None),
                None,
            )
            if day is None:
                why = eng.can_add(self.trip, a["id"], 1) or "no day is free for it"
                return self._missed(
                    f"{a['name']} does not fit any day: {why}.",
                    f"Sorry, the {a['name']} doesn't fit any day of this trip.",
                )
        if (why := eng.can_add(self.trip, a["id"], day)) is not None:
            fits = [
                d.n for d in eng.days(self.trip) if eng.can_add(self.trip, a["id"], d.n) is None
            ]
            where = f" It fits day {', '.join(map(str, fits))}." if fits else ""
            return self._missed(
                f"Not added: {why}.{where}",
                f"I couldn't put it on day {day}: {why}."
                + (f" Shall I put it on day {fits[0]} instead?" if fits else ""),
            )
        self.trip.activities.append((day, a["id"]))
        self._send("trip.add", {"activity_id": a["id"], "day": day})
        done = f"{a['name']} is on day {day}, {eng.money(eng.activity_price(self.trip, a['id']))}. {self.total_line()}"
        lead_in = lead.line(self.lang, "activity_in", activity=a["name"], day=str(day))
        kind, _ = lead.next_step(self.trip)
        if kind != "package":
            return f"{done}\n{self._advance(lead_in)}"
        fits = self._fits(None, None)
        package = lead.line(self.lang, "offer_package")
        if not fits:
            owe(f"{lead_in} {package}", then=package, cover=_PACKAGE_WORDS)
            return f"{done}\nNothing more fits their days; the package or review and book is next."
        nd, na = fits[0]
        more = lead.activity_line(self.trip, nd, eng.ACTIVITIES[na["id"]], self.lang)
        owe(
            f"{lead_in} {more}",
            then=more,
            cover=(*(x["name"] for _, x in fits[:6]), *_PACKAGE_WORDS),
        )
        return (
            f"{done}\nThey have been offered one more (by you, or in the brain's words just "
            "after) or the package; take their answer. What else fits:\n"
            + self._activity_lines(fits, 4)
        )

    async def remove_activity(self, choice: ActivityChoice) -> str:
        """Take an activity off the trip. Returns at once: say it in the same
        response as this call."""
        t = self.trip
        names = {
            eng.ACTIVITIES[a]["name"]: (d, a) for d, a in t.activities if choice.day in (None, d)
        }
        hit = match_label(choice.activity, list(names))
        if hit is None:
            return self._missed(
                "That is not in the trip. In it: " + (", ".join(names) or "no activities") + ".",
                "That one isn't in your trip"
                + (f"; it has {_or(list(names), 'and')}." if names else "."),
            )
        day, aid = names[hit]
        t.activities.remove((day, aid))
        self._send("trip.remove", {"activity_id": aid, "day": day})
        offer = lead.offer(t, self.lang)
        owe(f"{lead.line(self.lang, 'removed', activity=hit)} {offer}", then="")
        return f"{hit} is off day {day}. {self.total_line()} NEXT: {self.next_note()}"

    @needs_result_now
    async def build_package(self) -> str:
        """Build the whole package for the brief at once — the suggested flight,
        a hotel per city and activities for their style — and put it on screen.
        Replaces any flight, hotels and activities already chosen. Returns the
        package day by day with every price."""
        if why := self._need_brief():
            return why
        built = eng.build_package(self.trip)
        self.trip = built
        self._send(
            "trip.build",
            {
                "flight_id": built.flight_id or "",
                "hotels": [f"{c}:{h}:{r}" for c, (h, r) in built.hotels.items()],
                "activities": [f"{d}:{a}" for d, a in built.activities],
            },
        )
        owe(
            lead.line(
                self.lang,
                "built",
                total=eng.money(eng.price(built).total),
                highlight=self._highlight(built),
            )
        )
        return (
            "Package on screen:\n"
            + self.describe(built)
            + "\nNEXT, in this same reply: the total, one or two highlights that will thrill them "
            "(a hotel, an activity), and ask: happy to book, or change anything?"
        )

    def _highlight(self, t: Trip) -> str:
        """One thing in the package to look forward to: its first hotel."""
        for city, _ in eng.stops(t):
            if pick := t.hotels.get(city):
                h = eng.HOTELS[pick[0]]
                return f"{h['name']} in {eng.CITIES[city]['name']}"
        return eng.CITIES[eng.stops(t)[0][0]]["name"] if eng.stops(t) else ""

    @needs_result_now
    async def trip_summary(self) -> str:
        """The trip as it is on screen now: every item with its price, the total,
        and how it compares with the budget."""
        if not self.trip.destination:
            return "No trip yet. " + self.state_line()
        if not self.trip.flight_id and not self.trip.hotels:
            owe(lead.offer(self.trip, self.lang))
            return (
                "Nothing is priced yet: no flight or hotel is chosen, so there is no total to say. "
                f"Say so and lead on. {self.state_line()} {self.next_note()}"
            )
        owe(self._line("summary") + " " + lead.offer(self.trip, self.lang))
        return (
            self.state_line()
            + "\n"
            + self.describe(self.trip)
            + f"\nAnswer what they asked, then lead on. {self.next_note()}"
        )

    async def go_to_checkout(self) -> str:
        """Open the review and payment page, once the trip has a flight and a
        hotel in every city (the trip note says what is still missing; offer
        that first). The visitor types their details and presses Pay; never
        take payment details."""
        t = self.trip
        if why := self._need_brief():
            return why
        if not t.flight_id:
            return self._missed(
                "Not yet: the trip needs a flight and a hotel in every city first.",
                "Before we book, let's pick your flight. " + lead.line(self.lang, "offer_flights"),
            )
        if empty := [c for c, _ in eng.stops(t) if c not in t.hotels]:
            name = eng.CITIES[empty[0]]["name"]
            return self._missed(
                f"Not yet: no hotel in {name}. The trip needs a hotel in every city first.",
                f"Almost there, but you don't have a hotel in {name} yet, so I can't open the "
                f"booking page. {lead.line(self.lang, 'offer_hotels', city=name)}",
            )
        self._send("trip.go", {"page": "checkout"})
        landed(self._line("checkout"))
        return f"The review page is open. {self.total_line()} They fill in the lead traveller and press Pay themselves."

    async def set_language(self, request: LanguageRequest) -> str:
        """Speak and listen in another language persona.json offers, from now on."""
        self._switch(request.language, by="voice")
        return f"Now speaking {LANGUAGES[self.lang].name}."

    def _switch(self, tag: str, *, by: str) -> None:
        s = speaking(tag)
        if s.tag == self.lang:
            return
        self.lang = s.tag
        configure_soon(self.session, self._speaking(s))
        self.session.dispatch(LanguageChanged(language=self.lang))
        self.system_instruction = system_instruction(self.page, self.lang, self.today)
        logger.info("holidays: language -> {} ({})", s.tag, by)
        if by == "toggle":
            self.append_note(
                f"[The visitor chose {s.name} on the toggle. Reply in {s.name} from now on.]"
            )
            self._say_soon(s.switched)


#: Live calls by session id, for a redial to rejoin (rejoin.py).
REJOIN: Rejoin[HolidaysBrain] = Rejoin()
