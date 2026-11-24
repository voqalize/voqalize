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
the activities that fit, the package and the summary. Choosing a flight, a hotel
or an activity, moving nights and going to checkout are actions: they say a
short line with the call, and their written line is the floor under a silent
turn.

**Language.** The visitor picks English or Hindi on the page before the call
(``init.lang``), and may switch mid-call by the toggle or by asking. Both legs
move together, with the voice ``persona.json`` names for that language.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from dataclasses import replace
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
    UserIdle,
    UserMessage,
)
from voqalize.sdk.openai import OpenAIBrain, needs_result_now
from voqalize.sdk.stage import Mirror, Stage, match_label
from voqalize.sdk.stage.wire import StageEvent, StageHello, StageProgress, StageResult
from voqalize.sdk.wire import Config, IdleConfig, RedialConfig, SttConfig, TtsConfig

from . import engine as eng
from .engine import Trip
from .persona import LANGUAGES, Speaking, speaking
from .prompt import system_instruction
from .rejoin import Rejoin
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

Lang = Literal["en", "hi"]

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
    "hi": {
        "brief": "मैंने यह आपकी ट्रिप में डाल दिया है।",
        "flights": "ये रहीं फ़्लाइट्स।",
        "flight": "हो गया, यह फ़्लाइट जुड़ गई। अब कुल {total} है।",
        "hotels": "ये रहे {city} के होटल।",
        "hotel": "हो गया, {hotel} जुड़ गया। अब कुल {total} है।",
        "nights": "हो गया, रातें बदल दीं। अब कुल {total} है।",
        "add": "जोड़ दिया। अब कुल {total} है।",
        "remove": "हटा दिया। अब कुल {total} है।",
        "build": "यह रहा आपका पूरा पैकेज, सब मिलाकर {total}।",
        "checkout": "यह रहा रिव्यू पेज। डिटेल्स देख लीजिए और तैयार हों तो Pay दबाइए।",
        "summary": "आपकी ट्रिप अभी ऐसी है।",
        "paid": "बधाई हो, आपकी बुकिंग हो गई! आपका रेफ़रेंस {reference} है।",
    },
}

_ALIASES = {
    "bombay": "BOM",
    "bangalore": "BLR",
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
    language: Literal["en", "hi"]


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
            self.lang = "hi" if s.tag == "hi" else "en"
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
        return s.greeting_home if self.page == "home" else s.greeting_plan

    def _line(self, key: str, **kw: str) -> str:
        return _LINES[self.lang][key].format(**kw)

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[Speech, None]:
        self.stage.visitor_spoke()
        self._say_next = None
        self._settle_expired()
        state = self.state_line()
        if state != self._said_state:
            self.append_note(f"[Trip now: {state}]")
            self._said_state = state
        self.append_note(msg.text)
        async for speech in self.respond(session):
            yield speech

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        turn = self.stage.cued(super().respond(session))
        async for event in self._fallback.speak_if_silent(self, turn):
            yield event
        self.stage.end_turn()

    def on_user_idle(self, session: Session, idle: UserIdle) -> AsyncGenerator[Speech, None]:
        return self._idle(session)

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
        elif name == "trip.hotel_picked":
            city, hid, rid = (str(data.get(k) or "") for k in ("city", "hotel_id", "room_id"))
            if hid in eng.HOTELS and eng.HOTELS[hid]["city"] == city:
                t.hotels[city] = (hid, rid)
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
            self.set_language,
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
            if budget != t.budget:
                t.budget = budget
                sent["budget"] = budget
        if brief.style and brief.style != t.style:
            t.style = brief.style
            sent["style"] = brief.style
        if dropped := self._revalidate():
            notes.append(f"Dropped because they no longer fit: {', '.join(dropped)}.")
        if sent:
            self._send("trip.brief", sent)
            landed(self._line("brief"))
        missing = t.missing()
        head = "Brief now: " + self.state_line()
        if missing:
            ask = {
                "from_city": "where they fly from",
                "destination": "where to",
                "start_date": "when (a date or a month)",
                "nights": "how many nights",
            }
            tail = "Still need: " + ", ".join(ask[m] for m in missing) + "."
            if t.dest and "nights" in missing:
                tail += f" {t.dest['name']} is sold for {t.dest['nights'][0]} to {t.dest['nights'][1]} nights, usually {t.dest['default_nights']}."
        else:
            tail = "The brief is complete. Offer to build the whole package or go step by step."
        return "\n".join([*notes, head, tail])

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
        landed(self._line("flights"))
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
        return "\n".join(out)

    async def choose_flight(self, choice: FlightChoice) -> str:
        """Put the flight option the visitor picked into the trip."""
        if why := self._need_brief():
            return why
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
            return f"No option matches '{choice.choice}'. Options: " + "; ".join(
                f"{i}. {f['airline_name']}" for i, f in enumerate(options, 1)
            )
        self.trip.flight_id = pick["id"]
        self._revalidate()
        self._send("trip.flight", {"flight_id": pick["id"]})
        total = eng.money(eng.price(self.trip).total)
        landed(self._line("flight", total=total))
        return f"{pick['airline_name']} is in the trip. {self.total_line()}"

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
            landed(self._line("hotels", city=eng.CITIES[city]["name"]))
            return "\n".join(out)
        args: dict[str, Any] = {"city": city}
        if request.want:
            args["want"] = request.want
        self._send("trip.hotels", args)
        landed(self._line("hotels", city=eng.CITIES[city]["name"]))
        out.append(f"Hotels in {eng.CITIES[city]['name']} ({nights} nights):")
        out += [self._hotel_line(city, h) for h in found]
        return "\n".join(out)

    async def choose_hotel(self, choice: HotelChoice) -> str:
        """Put a hotel (and room) into the trip for its city, replacing the one there."""
        if why := self._need_brief():
            return why
        d = self.trip.dest
        assert d is not None
        hotels = {h["name"]: h for c in d["cities"] for h in c["hotels"]}
        hit = match_label(choice.hotel, list(hotels))
        if hit is None:
            return f"No hotel on this trip is called '{choice.hotel}'. Hotels: {', '.join(hotels)}."
        h = hotels[hit]
        city = h["city"] if "city" in h else eng.HOTELS[h["id"]]["city"]
        if not dict(eng.stops(self.trip)).get(city):
            return f"{h['name']} is in {eng.CITIES[city]['name']}, which has no nights in this trip. Offer set_nights first."
        room = h["rooms"][0]
        if choice.room:
            rhit = match_label(choice.room, [r["name"] for r in h["rooms"]])
            if rhit is None:
                return f"{h['name']} has: {', '.join(r['name'] for r in h['rooms'])}."
            room = next(r for r in h["rooms"] if r["name"] == rhit)
        before = eng.price(self.trip).total
        self.trip.hotels[city] = (h["id"], room["id"])
        self._send("trip.hotel", {"city": city, "hotel_id": h["id"], "room_id": room["id"]})
        after = eng.price(self.trip).total
        landed(self._line("hotel", hotel=h["name"], total=eng.money(after)))
        diff = after - before
        change = (
            f"{eng.money(abs(diff))} {'more' if diff > 0 else 'less'}" if diff else "the same price"
        )
        return f"{h['name']}, {room['name']}, is in for {eng.CITIES[city]['name']}: {change}. {self.total_line()}"

    async def set_nights(self, request: NightsRequest) -> str:
        """Change how many nights are spent in one city; the other cities give or
        take the difference, so the trip's length stays the same."""
        if why := self._need_brief():
            return why
        t = self.trip
        d = t.dest
        assert d is not None
        city = self._city(request.city)
        if city is None:
            return f"{request.city} is not on this trip. Cities: " + ", ".join(
                c["name"] for c in d["cities"]
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
            return f"That split cannot be served: {d['name']}'s cities in order are {', '.join(eng.CITIES[c]['name'] for c in ids)}, and the trip is {t.nights} nights. Current: {', '.join(f'{eng.CITIES[c]["name"]} {n}' for c, n in eng.stops(t))}."
        before = {a for _, a in t.activities}
        self._set_split(split)
        dropped = [eng.ACTIVITIES[a]["name"] for a in before - {a for _, a in t.activities}]
        self._send("trip.nights", {"split": [str(n) for n in split]})
        for c, _ in eng.stops(t):
            if c not in t.hotels and t.flight_id:
                t.hotels[c] = eng.recommended_hotel(t, c)
                hid, rid = t.hotels[c]
                self._send("trip.hotel", {"city": c, "hotel_id": hid, "room_id": rid})
        landed(self._line("nights", total=eng.money(eng.price(t).total)))
        out = (
            "Nights now: "
            + ", ".join(f"{eng.CITIES[c]['name']} {n}" for c, n in eng.stops(t))
            + "."
        )
        if dropped:
            out += f" Dropped because their day moved: {', '.join(dropped)}."
        return out + " " + self.state_line()

    def _fits(self, city: str | None, day: int | None) -> list[tuple[int, dict[str, Any]]]:
        t = self.trip
        style = t.style or ("family" if t.kids else "relaxed")
        out: list[tuple[int, dict[str, Any]]] = []
        for d in eng.days(t):
            if (day and d.n != day) or (city and d.city != city):
                continue
            for a in eng.CITIES[d.city]["activities"]:
                if eng.can_add(t, a["id"], d.n) is None and all(
                    a["id"] != x for _, x in t.activities
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
        if request.day:
            self._send("trip.step", {"step": "days"})
        if not fits:
            day = next((d for d in eng.days(self.trip) if d.n == request.day), None)
            if day and day.kind in ("arrival", "transfer"):
                return f"Day {day.n} is a travel day with only the evening free, and nothing else fits it."
            return "Nothing more fits there: the slots are taken, it is a travel day, or the ages or weekday rule it out."
        by_act: dict[str, tuple[dict[str, Any], list[int]]] = {}
        for n, a in fits:
            by_act.setdefault(a["id"], (a, []))[1].append(n)
        lines = []
        for a, ds in list(by_act.values())[:8]:
            lines.append(
                f"{a['name']} ({eng.CITIES[a['city']]['name']}, {a['duration']}, {a['slot'].replace('_', ' ')}): {a['blurb']} "
                f"{eng.money(eng.activity_price(self.trip, a['id']))} for the group; fits day {', '.join(map(str, ds))}."
            )
        return "\n".join(lines)

    def _activity(self, said: str) -> dict[str, Any] | None:
        d = self.trip.dest
        if not d:
            return None
        acts = {a["name"]: a for c in d["cities"] for a in c["activities"]}
        hit = match_label(said, list(acts))
        return acts.get(hit) if hit else None

    async def add_activity(self, choice: ActivityChoice) -> str:
        """Add an activity to a day of the trip (the first day it fits, if no day was said)."""
        if why := self._need_brief():
            return why
        a = self._activity(choice.activity)
        if a is None:
            return (
                f"No activity on this trip is called '{choice.activity}'. Use suggest_activities."
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
                return f"{a['name']} does not fit any day: {why}."
        if (why := eng.can_add(self.trip, a["id"], day)) is not None:
            fits = [
                d.n for d in eng.days(self.trip) if eng.can_add(self.trip, a["id"], d.n) is None
            ]
            return f"Not added: {why}." + (
                f" It fits day {', '.join(map(str, fits))}." if fits else ""
            )
        self.trip.activities.append((day, a["id"]))
        self._send("trip.add", {"activity_id": a["id"], "day": day})
        landed(self._line("add", total=eng.money(eng.price(self.trip).total)))
        return f"{a['name']} is on day {day}, {eng.money(eng.activity_price(self.trip, a['id']))}. {self.total_line()}"

    async def remove_activity(self, choice: ActivityChoice) -> str:
        """Take an activity off the trip."""
        t = self.trip
        names = {
            eng.ACTIVITIES[a]["name"]: (d, a) for d, a in t.activities if choice.day in (None, d)
        }
        hit = match_label(choice.activity, list(names))
        if hit is None:
            return "That is not in the trip. In it: " + (", ".join(names) or "no activities") + "."
        day, aid = names[hit]
        t.activities.remove((day, aid))
        self._send("trip.remove", {"activity_id": aid, "day": day})
        landed(self._line("remove", total=eng.money(eng.price(t).total)))
        return f"{hit} is off day {day}. {self.total_line()}"

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
        landed(self._line("build", total=eng.money(eng.price(built).total)))
        return "Package on screen:\n" + self.describe(built)

    @needs_result_now
    async def trip_summary(self) -> str:
        """The trip as it is on screen now: every item with its price, the total,
        and how it compares with the budget."""
        if not self.trip.destination:
            return "No trip yet. " + self.state_line()
        landed(self._line("summary"))
        return self.state_line() + "\n" + self.describe(self.trip)

    async def go_to_checkout(self) -> str:
        """Open the review and payment page. The visitor types their details and
        presses Pay; never take payment details."""
        t = self.trip
        if why := self._need_brief():
            return why
        if not t.flight_id or any(c not in t.hotels for c, _ in eng.stops(t)):
            return "Not yet: the trip needs a flight and a hotel in every city first."
        self._send("trip.go", {"page": "checkout"})
        landed(self._line("checkout"))
        return f"The review page is open. {self.total_line()} They fill in the lead traveller and press Pay themselves."

    async def set_language(self, request: LanguageRequest) -> str:
        """Speak and listen in English (en) or Hindi (hi) from now on."""
        self._switch(request.language, by="voice")
        return f"Now speaking {LANGUAGES[self.lang].name}."

    def _switch(self, tag: str, *, by: str) -> None:
        s = speaking(tag)
        if s.tag == self.lang:
            return
        self.lang = "hi" if s.tag == "hi" else "en"
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
