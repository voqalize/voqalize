"""BelmonteBrain — the concierge in Hotel Belmonte's guest app, a fictional
coastal resort in Halcyon Bay, California.

An :class:`~voqalize.sdk.openai.OpenAIBrain`. The guest asks for what they would
phone the front desk for, and the concierge does it on their screen while she
talks: check-in (reservation, ID, arrival and room preferences, early check-in),
check-out (the folio, a charge questioned, late check-out, express check-out),
in-room dining and drinks orders, spa and activity bookings, meeting rooms,
visitors at the front desk, housekeeping and the other front desk requests, and
the hotel's policies.

**The screen is Stage.** Every change she makes is a Stage move from
``frontend/src/stage/scene.json`` (generated into :mod:`.stage_gen`): tools send
the moves, and the model's own words carry the cues that open a screen
(``{go: spa}``) or point at something on it (``{show: total}``). The app reports
what the guest does by hand as Stage events on the ``stay`` slice, by id, and the
brain folds each into its own picture of the stay.

**The guest decides.** A move fills, opens and selects; it never presses the
final button of anything that costs money or approves someone (Place order,
Book, Request booking, Approve, Decline, Add visitor, Complete check-in,
Request late check-out, Check out now). The guest presses it; the app says so
with an event, and the brain says a short written line of its own at once.

**No invented facts.** Menus, prices, slots, fees and policies come from
``data/hotel.json`` through :mod:`.hotel`, which the app implements the same way
(``data/rules_cases.json`` holds the two to one answer).

**What is marked ``@needs_result_now``.** The reads the model must speak from:
the menus and an order's totals, the folio, late check-out options, the spa's
treatments and free times, activities, meeting rooms and a quote, visitors,
the hotel's information, and the room the guest's preferences get. Actions
(adding, choosing, filling, opening) return at once; one that cannot be done
is said straight away in the brain's own words (``_missed``), since its result
reaches the model only on the next turn.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from typing import Any

from loguru import logger
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from voqalize_demos import PATIENCE, FallbackLine, configure_soon, landed

from voqalize.sdk import (
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

from . import hotel as h
from .hotel import Line, Stay
from .persona import LANGUAGES, NAME, Speaking, speaking
from .prompt import system_instruction
from .rejoin import Rejoin
from .spoken import Spoken, parse_date, parse_time, speak_text
from .stage_gen import SPEC

#: GPT-6.1 Terra, as the other OpenAI demos run it, at medium reasoning: at low,
#: the model skipped screen moves it had just promised (demos/README.md).
MODEL = "gpt-6.1-terra"
REASONING = "medium"

#: A quiet guest is reading a menu or a bill; the concierge does not nudge.
_IDLE_MS = 30_000
#: A line the brain already knows (an order placed, a visitor approved): said as
#: soon as the voice is free.
_SAY_NOW_MS = 400

#: What a brain holds for one socket only. Everything else a call built is
#: carried to the brain a redial starts (rejoin.py).
_PER_SOCKET = frozenset({"_session", "_awaiting"})

_EVENTS = AppEvents(StageResult, StageHello, StageProgress, StageEvent)

Outlet = str  # "dining" | "bar"
OUTLETS = ("dining", "bar")


@dataclass
class _Turn:
    """One turn's record: a line the brain owes whatever the model said (an
    action that could not be done; its result reaches the model a turn late)."""

    must: str | None = None


_TURN: ContextVar[_Turn | None] = ContextVar("belmonte_turn", default=None)


@dataclass
class Checkin:
    """How far check-in has got (the app's ``Checkin``)."""

    confirmed: bool = False
    id_verified: bool = False
    arrival: str | None = None
    floor: str | None = None
    bed: str | None = None
    quiet: bool | None = None
    early: bool | None = None

    def reachable(self, now: str) -> list[str]:
        out = ["reservation"]
        if not self.confirmed:
            return out
        out.append("id")
        if not self.id_verified:
            return out
        out.append("room")
        if not self.arrival:
            return out
        if h.early_offered(self.arrival, now):
            out.append("early")
            if self.early is None:
                return out
        out.append("review")
        return out


@dataclass
class Guest:
    """The stay as the concierge knows it: the scenario's seed, then every change
    made by her moves or reported by the app."""

    scenario: str = "arrival"
    page: str = "home"
    checkin: Checkin = field(default_factory=Checkin)
    checked_in: bool = False
    room: str | None = None
    checked_out: bool = False
    carts: dict[str, list[Line]] = field(default_factory=lambda: {"dining": [], "bar": []})
    charges: list[dict[str, Any]] = field(default_factory=list)
    disputes: set[str] = field(default_factory=set)
    late_requested: str | None = None
    visitors: dict[str, str] = field(default_factory=dict)
    bookings: list[str] = field(default_factory=list)
    requests: list[str] = field(default_factory=list)

    @classmethod
    def seed(cls, scenario: str) -> Guest:
        sc = scenario if scenario in h.SCENARIOS else "arrival"
        s = h.SCENARIOS[sc]
        return cls(
            scenario=sc,
            checked_in=bool(s["checked_in"]),
            room=s["room"],
            visitors={v["id"]: v["status"] for v in h.VISITORS["pending"]},
        )

    @classmethod
    def from_init(cls, raw: dict[str, Any]) -> Guest:
        """The stay the app sends in ``init.stay`` (ids and flags only)."""
        g = cls.seed(str(raw.get("scenario") or "arrival"))
        g.checked_in = bool(raw.get("checked_in", g.checked_in))
        g.checked_out = bool(raw.get("checked_out", False))
        g.room = raw.get("room") or g.room
        ci = raw.get("checkin")
        if isinstance(ci, dict):
            c: dict[str, Any] = ci  # pyright: ignore[reportUnknownVariableType]
            g.checkin = Checkin(
                confirmed=bool(c.get("confirmed")),
                id_verified=bool(c.get("idVerified")),
                arrival=c.get("arrival"),
                floor=c.get("floor"),
                bed=c.get("bed"),
                quiet=c.get("quiet"),
                early=c.get("early"),
            )
        carts = raw.get("carts")
        if isinstance(carts, dict):
            for o in OUTLETS:
                lines: list[Any] = carts.get(o) or []  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                g.carts[o] = [
                    Line(
                        str(x.get("item_id")),
                        int(x.get("qty") or 1),
                        list(x.get("choices") or []),
                        str(x.get("note") or ""),
                    )
                    for x in lines
                    if isinstance(x, dict) and str(x.get("item_id")) in h.ITEMS[o]  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
                ]
        charges = raw.get("charges")
        if isinstance(charges, list):
            g.charges = [dict(x) for x in charges if isinstance(x, dict)]  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
        disputes = raw.get("disputes")
        if isinstance(disputes, list):
            g.disputes = {str(x) for x in disputes}  # pyright: ignore[reportUnknownVariableType]
        g.late_requested = raw.get("late") or None
        vis = raw.get("visitors")
        if isinstance(vis, dict):
            g.visitors.update({str(k): str(v) for k, v in vis.items()})  # pyright: ignore[reportUnknownVariableType]
        for key in ("bookings", "requests"):
            v = raw.get(key)
            if isinstance(v, list):
                setattr(g, key, [str(x) for x in v])  # pyright: ignore[reportUnknownVariableType]
        return g

    def folio(self) -> list[dict[str, Any]]:
        return [*h.SCENARIOS[self.scenario]["folio"], *self.charges]


# ─── Tool arguments ───────────────────────────────────────────────────────────


class InfoQuery(BaseModel):
    topic: str = Field(
        description="What they asked about, in a word or two: pets, smoking, pools, wifi, parking, quiet hours, check-in, check-out, house rules, accessibility, restaurants, fitness, contact."
    )


class RoomPrefs(BaseModel):
    arrival: str | None = Field(
        None, description="When they arrive: 'now', or a time as said ('5 pm')."
    )
    floor: str | None = Field(None, description="high, low or any.")
    bed: str | None = Field(None, description="king or queens (two queen beds).")
    quiet: bool | None = Field(None, description="True when they want a quiet room.")


class EarlyChoice(BaseModel):
    want: bool = Field(description="True to take the room on arrival for the early check-in fee.")


class ChargeQuestion(BaseModel):
    charge: str = Field(
        description="The charge as the guest names it ('the minibar', 'the spa on Monday') or its id."
    )
    reason: str = Field(description="What they say is wrong, in their words.")
    send: bool = Field(
        False, description="True only once the guest agreed to send it to the front desk."
    )


class LateRequest(BaseModel):
    time: str | None = Field(
        None,
        description="The late check-out time they chose ('1 pm'), or empty to read the options.",
    )


class MenuQuery(BaseModel):
    outlet: str = Field(
        description="dining (in-room dining food) or bar (drinks, wine, beer, bar bites)."
    )
    section: str | None = Field(
        None,
        description="dining: breakfast, all day, late night. bar: cocktails, beer, wine, zero proof, bites.",
    )
    search: str | None = Field(
        None,
        description="Optional: what they want ('gluten-free', 'vegetarian', 'no nuts', 'burger', 'red wine').",
    )


class AddItem(BaseModel):
    outlet: str = Field(description="dining or bar.")
    item: str = Field(description="The item as named on the menu.")
    quantity: int = Field(1, ge=1, le=20)
    choices: list[str] = Field(
        default_factory=list,
        description="Every option the guest chose, as the menu names it ('medium', 'sweet potato fries', 'no onions', 'bottle', 'oat milk').",
    )
    note: str | None = Field(None, description="A special request in their words, if any.")


class RemoveItem(BaseModel):
    outlet: str = Field(description="dining or bar.")
    item: str


class ReviewOrder(BaseModel):
    outlet: str = Field(description="dining or bar.")
    tip_percent: int | None = Field(
        None, description="Only the tip the guest said: 0, 10, 15 or 20."
    )
    deliver_to: str | None = Field(
        None, description="Drinks only, as the guest said: room or cabana."
    )
    cabana: str | None = Field(None, description="Cabana number 1 to 8, if they said.")


class SpaQuery(BaseModel):
    category: str | None = Field(None, description="massage, facial, ritual or nails.")


class SpaTimes(BaseModel):
    treatment: str = Field(
        description="The treatment as named, with its length if they said ('80 minute deep tissue')."
    )
    date: str | None = Field(None, description="The day as said: today, tomorrow, Friday, Nov 27.")
    therapist: str | None = Field(None, description="any, female, male, or a therapist's name.")


class SpaPick(BaseModel):
    treatment: str
    date: str = Field(description="The day as said.")
    time: str = Field(description="The start time they chose.")
    therapist: str | None = Field(None, description="The therapist's name, if they chose one.")


class ActivityQuery(BaseModel):
    kind: str | None = Field(
        None, description="pools, kids, golf, sport (tennis), fitness, tours, music (tonight)."
    )


class PlaceQuery(BaseModel):
    place: str = Field(
        description="An activity or a place on the resort ('kayak tour', 'the cliff pool', 'the spa')."
    )


class ActivityBooking(BaseModel):
    activity: str
    date: str = Field(description="The day as said.")
    time: str = Field(description="The start time they chose.")
    guests: int = Field(1, ge=1, le=20)


class MeetingQuery(BaseModel):
    headcount: int | None = None
    layout: str | None = Field(
        None, description="boardroom, u-shape, classroom, theatre or banquet."
    )
    date: str | None = Field(None, description="The day as said.")


class MeetingBooking(BaseModel):
    room: str
    date: str = Field(description="The day as said.")
    block: str = Field(description="morning, afternoon, full day, or hours.")
    start: str | None = Field(None, description="Start time, for a booking by the hour.")
    hours: int | None = Field(None, description="Hours, for a booking by the hour.")
    headcount: int
    layout: str = Field(description="boardroom, u-shape, classroom, theatre or banquet.")
    catering: list[str] = Field(
        default_factory=list,
        description="Any of: coffee break, continental breakfast, working lunch, afternoon snack.",
    )
    av: list[str] = Field(
        default_factory=list, description="Any of: extra mics, recording, AV technician."
    )


class VisitorOpen(BaseModel):
    visitor: str = Field(description="The visitor's name as said.")
    meet: str | None = Field(
        None,
        description="room (send them up) or lobby (wait in the lobby), only if the guest said.",
    )


class VisitorExpect(BaseModel):
    name: str
    from_time: str = Field(description="Start of the arrival window, as said.")
    to_time: str = Field(description="End of the arrival window, as said.")
    meet: str | None = Field(None, description="room or lobby, only if the guest said.")
    note: str | None = None


class DeskRequest(BaseModel):
    kind: str = Field(
        description="housekeeping, maintenance, wakeup, valet, transport or lost_found."
    )
    items: list[str] = Field(
        default_factory=list,
        description="Housekeeping: towels, pillows, toiletries, robes, crib, turndown, clean, dnd.",
    )
    issue: str | None = Field(
        None, description="Maintenance: ac, tv, plumbing, lights, door, other."
    )
    option: str | None = Field(None, description="Transport: house car, airport sedan, taxi.")
    date: str | None = Field(None, description="Wake-up call: the day as said.")
    time: str | None = Field(None, description="The time as said.")
    details: str | None = Field(
        None, description="What is wrong, where to, or what was lost and where."
    )
    send: bool = Field(False, description="True only after the guest said yes to sending it.")


# ─── Resolving what the guest said ────────────────────────────────────────────


def _fold(s: str) -> str:
    return " ".join(s.lower().replace("-", " ").replace("_", " ").split())


_TOPICS = {
    "pets": ("pet", "dog", "cat", "animal"),
    "smoking": ("smok", "vap", "cigar", "cannabis"),
    "pools": ("pool", "swim", "cabana", "lifeguard"),
    "wifi": ("wifi", "wi fi", "internet", "password", "network"),
    "parking": ("park", "valet", "car", "ev ", "charger"),
    "quiet": ("quiet", "noise", "loud", "music"),
    "checkin": ("check in", "checkin", "check out", "checkout", "late check", "early check"),
    "house_rules": ("rule", "visitor", "party", "parties", "guests allowed", "balcony"),
    "accessibility": ("access", "wheelchair", "roll in", "hearing", "disab", "mobility"),
    "dining_hours": (
        "restaurant",
        "bar",
        "breakfast",
        "dinner",
        "tidewater",
        "compass",
        "dining",
        "room service",
    ),
    "fitness": ("gym", "fitness", "workout", "spa hours", "steam"),
    "contact": ("contact", "phone", "call", "address", "front desk", "number"),
}


def resolve_topic(said: str) -> str | None:
    s = f" {_fold(said)} "
    if said in h.INFO:
        return said
    for tid, keys in _TOPICS.items():
        if any(k in s for k in keys):
            return tid
    hit = match_label(said, [x["title"] for x in h.INFO.values()])
    return next((k for k, v in h.INFO.items() if v["title"] == hit), None)


def resolve_outlet(said: str) -> str:
    s = _fold(said)
    return "bar" if any(w in s for w in ("bar", "drink", "wine", "beer", "cocktail")) else "dining"


_FLOORS = {
    "high": ("high", "top", "upper"),
    "low": ("low", "ground", "bottom"),
    "any": ("any", "no pref", "doesn"),
}


def _choice(said: str | None, table: dict[str, tuple[str, ...]]) -> str | None:
    if said is None:
        return None
    s = _fold(said)
    return next((k for k, keys in table.items() if s == k or any(x in s for x in keys)), None)


def _or(names: list[str], word: str = "or") -> str:
    if len(names) <= 1:
        return "".join(names)
    return f"{', '.join(names[:-1])} {word} {names[-1]}"


# ─── The brain ────────────────────────────────────────────────────────────────


class BelmonteBrain(OpenAIBrain):
    """One per call: the stay as the concierge and the app both see it."""

    def __init__(self, *, client: AsyncOpenAI, model: str = MODEL) -> None:
        self.lang = "en"
        self.guest = Guest.seed("arrival")
        super().__init__(
            client=client,
            system_instruction=system_instruction(self.guest.scenario, self.lang),
            model=model,
            reasoning=REASONING,
        )
        self.stage = Stage(
            dispatch=lambda a: self.session.dispatch(a),
            moves=SPEC.move_set(),
            mirror=Mirror(SPEC),
        )
        self._fallback = FallbackLine()
        self._say_next: Callable[[], str] | None = None
        self._said_state = ""
        self._rejoined = False
        self._spoken = Spoken()

    @property
    def stay(self) -> Stay:
        return Stay.of(self.guest.scenario)

    # ─── Session ────────────────────────────────────────────────────────

    def _speaking(self, s: Speaking) -> Config:
        return Config(
            tts=TtsConfig(voice=s.voice, language=s.tag),
            stt=SttConfig(language=s.tag, patience=PATIENCE),
        )

    async def on_session_start(self, session: Session) -> None:
        """The screen, language and stay the call started on; then both legs of
        the language, before the greeting. A brain started by a redial on a
        session this process still holds adopts that call (CONTRACT.md, Redial)."""
        prior = REJOIN.take(session.id)
        rejoined = prior is not None and prior is not self
        if prior is not None and rejoined:
            self._adopt(prior)
            logger.info("belmonte: rejoined call {} after its socket dropped", session.id)
            s = LANGUAGES[self.lang]
        else:
            init: dict[str, Any] = dict(session.init or {})
            s = speaking(str(init.get("lang") or ""))
            self.lang = s.tag
            raw = init.get("stay")
            self.guest = Guest.from_init(raw) if isinstance(raw, dict) else Guest.seed("arrival")  # pyright: ignore[reportUnknownArgumentType]
            self.guest.page = str(init.get("page") or "home")
            self.system_instruction = system_instruction(self.guest.scenario, self.lang)
        self._rejoined = rejoined
        REJOIN.hold(session.id, self)
        await session.configure(
            replace(
                self._speaking(s),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
                redial=RedialConfig(enabled=True) if session.can_redial else None,
            )
        )

    async def on_session_end(self, session: Session) -> None:
        REJOIN.dropped(session.id, self)

    def _adopt(self, prior: BelmonteBrain) -> None:
        """Take over ``prior``'s call: every piece of state but its socket's."""
        self.__dict__.update({k: v for k, v in prior.__dict__.items() if k not in _PER_SOCKET})
        prior.__dict__ = self.__dict__

    async def greet(self, session: Session) -> str | None:
        if self._rejoined:
            return None
        s = LANGUAGES[self.lang]
        line = s.greeting_checked_in if self.guest.checked_in else s.greeting
        return speak_text(line.format(name=NAME, guest=h.GUEST["first_name"]))

    def on_user_message(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]:
        return self._spoken.wrap(self._answer(session, msg))

    async def _answer(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]:
        self.stage.visitor_spoke()
        self._say_next = None
        self._settle_expired()
        state = self.state_line()
        if state != self._said_state:
            self.append_note(f"[{state}]")
            self._said_state = state
        self.append_note(msg.text)
        async for speech in self.respond(session):
            yield speech

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The model's turn, its cues sent to the app; ``FallbackLine`` speaks a
        landed action's line when the turn said nothing; then any line the turn
        owes whatever was said (an action that could not be done)."""
        record = _Turn()
        token = _TURN.set(record)
        try:
            turn = self.stage.cued(super().respond(session))
            async for event in self._fallback.speak_if_silent(self, turn):
                yield event
            if record.must:
                logger.info("belmonte: the brain says {!r}", record.must)
                async for event in self.say_line(record.must, remember=True):
                    yield event
        finally:
            with contextlib.suppress(ValueError):
                _TURN.reset(token)
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

    # ─── The stay in a line, for the model ──────────────────────────────

    def state_line(self) -> str:
        g, st = self.guest, self.stay
        parts = [
            f"Stay now: {h.SCENARIOS[g.scenario]['label'].lower()}, {h.day(st.today)} {h.clock(st.now)}."
        ]
        if g.checked_out:
            parts.append("Checked out.")
        elif g.checked_in:
            parts.append(f"Checked in, room {g.room}.")
        else:
            c = g.checkin
            step = c.reachable(st.now)[-1]
            done = [
                *(["reservation confirmed"] if c.confirmed else []),
                *(["ID verified"] if c.id_verified else []),
                *([f"arrival {c.arrival}"] if c.arrival else []),
                *([f"floor {c.floor}"] if c.floor else []),
                *([f"bed {c.bed}"] if c.bed else []),
                *(["quiet room"] if c.quiet else []),
                *([f"early check-in {'yes' if c.early else 'no'}"] if c.early is not None else []),
            ]
            parts.append(
                f"Not checked in yet; check-in: {', '.join(done) or 'not started'}; next step {step}."
            )
        parts.append(f"Screen: {g.page}.")
        for o in OUTLETS:
            if g.carts[o]:
                lines = "; ".join(self._line_words(o, ln) for ln in g.carts[o])
                parts.append(
                    f"{'Food' if o == 'dining' else 'Drinks'} order not placed yet: {lines}."
                )
        waiting = [v["name"] for v in h.VISITORS["pending"] if g.visitors.get(v["id"]) == "pending"]
        if waiting:
            parts.append(f"Visitors waiting at the front desk: {_or(waiting, 'and')}.")
        if g.late_requested:
            parts.append(f"Late check-out requested until {h.clock(g.late_requested)}.")
        if g.disputes:
            parts.append(f"Charges under review: {len(g.disputes)}.")
        return " ".join(parts)

    def _line_words(self, outlet: str, ln: Line) -> str:
        item = h.ITEMS[outlet][ln.item_id]
        extras = h.choice_labels(outlet, ln)
        return f"{ln.qty} {item['name']}" + (f" ({', '.join(extras)})" if extras else "")

    # ─── What the app says ──────────────────────────────────────────────

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        event = _EVENTS.parse(msg)
        if event is None:
            return
        if isinstance(event, StageEvent):
            note = self._app_did(event)
            if note:
                logger.info("belmonte: app {}", note)
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
        """A move that did not land is told plainly, with what the app offers."""
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

    def _app_did(self, event: StageEvent) -> str | None:
        """Fold a change the app reports into the stay. The concierge's own moves
        come back ``by: "agent"`` and are already in it; what only the guest can
        do (their final presses) is said at once in the brain's own words."""
        self.stage.handle(event)
        g = self.guest
        d: dict[str, Any] = dict(event.data)
        name, by = event.name, event.by
        label = str(d.get("label") or "")
        first = h.GUEST["first_name"]
        if name == "stay.page":
            g.page = str(d.get("page") or g.page)
            return None
        if name == "stay.scenario":
            scenario = str(d.get("scenario") or "arrival")
            self.guest = Guest.seed(scenario)
            self.guest.page = g.page
            self.system_instruction = system_instruction(self.guest.scenario, self.lang)
            return f"The demo was switched to '{h.SCENARIOS[self.guest.scenario]['label']}': the stay starts over from that scenario. {self.state_line()}"
        if name == "checkin.id_verified":
            g.checkin.id_verified = True
            if not g.checkin.arrival:
                self._say_soon(
                    "Thank you, your ID is verified. What time will you get here, and any room preferences, like a higher floor, a quiet room, or one king versus two queens?"
                )
            return "The guest scanned their ID and it is verified. Next: arrival time and room preferences."
        if name == "checkin.done":
            g.checked_in, g.room = True, str(d.get("room") or "") or g.room
            room = next((r for r in h.CHECKIN["rooms"] if r["room"] == g.room), None)
            if g.checkin.early:
                g.charges.append(
                    {
                        "id": "early",
                        "category": "fee",
                        "label": "Early check-in",
                        "amount": h.CHECKIN["early"]["fee"],
                    }
                )
            floor = f", on floor {room['floor']}" if room else ""
            self._say_soon(
                f"You're all checked in, {first}. Room {g.room}{floor}, and your digital key is on screen. Can I arrange anything before you head up, maybe lunch or a spa time?"
            )
            return f"The guest pressed Complete check-in: checked in, room {g.room}. Their digital key is on screen."
        if name == "order.placed":
            outlet = str(d.get("outlet") or "dining")
            g.carts[outlet] = []
            total = float(d.get("total") or 0)
            g.charges.append(
                {
                    "id": str(d.get("id") or outlet),
                    "category": outlet,
                    "label": "In-room dining" if outlet == "dining" else "Drinks delivery",
                    "amount": total,
                }
            )
            eta = str(d.get("time") or "")
            self._say_soon(
                f"Thank you, your order is in: {h.money(total)} on your room bill, arriving in about {eta}. Anything else I can get you?"
            )
            return f"The guest pressed Place order: {label}. It is ordered."
        if name in ("spa.booked", "activity.booked"):
            g.bookings.append(label)
            total = float(d.get("total") or 0)
            if total:
                g.charges.append(
                    {
                        "id": str(d.get("id") or name),
                        "category": name.split(".")[0],
                        "label": label,
                        "amount": total,
                    }
                )
            self._say_soon(f"Lovely, you're booked: {label}. Anything else I can set up for you?")
            return f"The guest pressed Book: {label}. It is booked."
        if name == "meeting.booked":
            g.bookings.append(label)
            self._say_soon(
                "Your booking request is with our events team; they'll confirm within two hours. Anything else for the meeting?"
            )
            return f"The guest pressed Request booking: {label}. The events team confirms within two hours."
        if name == "visitor.decided":
            vid, value = str(d.get("id") or ""), str(d.get("value") or "")
            g.visitors[vid] = value
            who = next((v["name"] for v in h.VISITORS["pending"] if v["id"] == vid), "your visitor")
            if value == "approved":
                where = (
                    "is on the way up to your room"
                    if "room" in label
                    else "will wait for you in the lobby"
                )
                self._say_soon(f"Done, {who} {where}.")
            else:
                self._say_soon(f"Done, the front desk will let {who} know.")
            return (
                f"The guest pressed {'Approve' if value == 'approved' else 'Decline'} for {label}."
            )
        if name == "visitor.added":
            self._say_soon("They're on the list; the front desk will be expecting them.")
            return f"The guest pressed Add visitor: {label}."
        if name == "late.requested":
            g.late_requested = str(d.get("value") or "") or None
            fee = float(d.get("total") or 0)
            g.charges.append(
                {
                    "id": "late",
                    "category": "fee",
                    "label": f"Late check-out, {label}",
                    "amount": fee,
                }
            ) if fee else None
            self._say_soon(
                f"Requested: late check-out until {label}. The front desk confirms in about 15 minutes."
            )
            return f"The guest pressed Request late check-out: {label}."
        if name == "checkout.done":
            g.checked_out = True
            self._say_soon(
                f"You're all checked out, {first}. Your receipt is on its way to your email. Safe travels, and we'd love to welcome you back."
            )
            return f"The guest pressed Check out now: {label}. They are checked out."
        if name == "folio.disputed":
            g.disputes.add(str(d.get("id") or ""))
            if by == "visitor":
                self._say_soon(
                    "Thank you, I've passed that to the front desk; it's held off your balance while they review it, within 24 hours."
                )
            return (
                f"The guest sent a question about the charge {label} to the front desk."
                if by == "visitor"
                else None
            )
        if name == "request.sent":
            g.requests.append(label)
            if by == "visitor":
                self._say_soon(f"Sent: {label}. Anything else?")
                return f"The guest sent a request: {label}."
            return None
        if by != "visitor":
            return None
        # The guest's own taps on a step a move could also take.
        c = g.checkin
        if name == "checkin.confirmed":
            c.confirmed = True
        elif name == "checkin.prefs":
            fld, value = str(d.get("field") or ""), d.get("value")
            if fld == "quiet":
                c.quiet = str(value).lower() == "true"
            elif fld in ("arrival", "floor", "bed"):
                setattr(c, fld, str(value) if value not in (None, "null") else None)
                if fld == "arrival" and not h.early_offered(c.arrival, self.stay.now):
                    c.early = None
        elif name == "checkin.early":
            c.early = str(d.get("value")) == "yes"
        elif name == "cart.changed":
            self._cart_by_hand(d, label)
        elif name == "late.picked":
            pass
        note_names = {
            "checkin.confirmed",
            "checkin.prefs",
            "checkin.early",
            "cart.changed",
            "late.picked",
            "spa.picked",
            "activity.picked",
            "meeting.picked",
        }
        if name in note_names:
            folded = (
                f"The guest {name.split('.')[1].replace('_', ' ')} on screen themselves: {label}"
                if label
                else f"The guest did {name} on screen themselves"
            )
            return folded
        return None

    def _cart_by_hand(self, d: dict[str, Any], label: str) -> None:
        outlet = str(d.get("outlet") or "dining")
        item_id = str(d.get("id") or "")
        qty = int(d.get("qty") or 0)
        lines = self.guest.carts.setdefault(outlet, [])
        if item_id not in h.ITEMS.get(outlet, {}):
            return
        if label.startswith("added"):
            choices: list[Any] = list(d.get("choices") or [])
            lines.append(Line(item_id, max(qty, 1), [str(x) for x in choices]))
        elif qty == 0:
            idx = next((i for i, ln in enumerate(lines) if ln.item_id == item_id), None)
            if idx is not None:
                lines.pop(idx)
        else:
            for ln in lines:
                if ln.item_id == item_id:
                    ln.qty = qty
                    break

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        return [
            self.hotel_info,
            self.start_check_in,
            self.confirm_reservation,
            self.set_room_preferences,
            self.set_early_check_in,
            self.open_bill,
            self.question_charge,
            self.late_checkout,
            self.express_checkout,
            self.show_menu,
            self.add_to_order,
            self.remove_from_order,
            self.review_order,
            self.spa_treatments,
            self.spa_times,
            self.choose_spa_time,
            self.find_activities,
            self.show_on_map,
            self.book_activity,
            self.meeting_rooms,
            self.quote_meeting,
            self.visitors,
            self.open_visitor,
            self.expect_visitor,
            self.front_desk_request,
        ]

    def _send(self, move: str, args: dict[str, Any]) -> None:
        self.stage.send(move, args)

    def _missed(self, why: str, said: str) -> str:
        """An action that could not be done: the guest hears ``said`` at once (the
        model hears ``why`` only with its next turn)."""
        if (record := _TURN.get()) is not None:
            record.must = said
        return f"Not done: {why} The guest has already been told: {said!r}"

    # ── Hotel information ──

    @needs_result_now
    async def hotel_info(self, query: InfoQuery) -> str:
        """Read the hotel's information on a topic (pets, smoking, pools, Wi-Fi,
        parking, quiet hours, check-in and check-out, house rules,
        accessibility, restaurants and bars, fitness, contact) and open that
        section on screen. Answer only from what it returns."""
        tid = resolve_topic(query.topic)
        if tid is None:
            return f"No section on '{query.topic}'. Sections: {', '.join(v['title'] for v in h.INFO.values())}."
        sec = h.INFO[tid]
        self._send("info.open", {"topic": tid})
        return f"{sec['title']} (open on screen): " + " ".join(sec["facts"])

    # ── Check-in ──

    def _not_arriving(self) -> str | None:
        g = self.guest
        if g.checked_out:
            return "the guest has checked out"
        if g.checked_in:
            return f"the guest is already checked in, room {g.room}"
        return None

    async def start_check_in(self) -> str:
        """Open check-in where it has got to. Then confirm the reservation details
        with the guest before confirm_reservation."""
        if why := self._not_arriving():
            return self._missed(
                why + ".",
                f"You're already checked in, room {self.guest.room}."
                if self.guest.checked_in
                else "You've already checked out.",
            )
        step = self.guest.checkin.reachable(self.stay.now)[-1]
        self._send("checkin.open", {"step": step})
        landed("Here's your check-in.", "Let's get you checked in.")
        g, st = h.GUEST, self.stay
        return (
            f"Check-in is open at the {step} step. Reservation {g['reservation']}: {g['room_type']}, "
            f"{h.day(st.arrive)} to {h.day(st.depart)}, {st.nights} nights, {g['adults']} adults, "
            f"{h.money(g['rate'])} a night. Steps: confirm the reservation, the guest scans their ID, "
            "arrival time and room preferences, early check-in if they arrive before 4:00 PM, then they press Complete check-in."
        )

    async def confirm_reservation(self) -> str:
        """The guest said the reservation is theirs: confirm it on screen. Next they
        tap Scan ID themselves."""
        if why := self._not_arriving():
            return self._missed(
                why + ".",
                "You're already checked in."
                if self.guest.checked_in
                else "You've already checked out.",
            )
        self.guest.checkin.confirmed = True
        self._send("checkin.confirm", {})
        landed(
            "Confirmed. Next, tap Scan ID on screen and hold up your driver's license or passport."
        )
        return "Confirmed. Next the guest taps Scan ID on screen themselves; you never see the ID."

    @needs_result_now
    async def set_room_preferences(self, prefs: RoomPrefs) -> str:
        """Set the arrival time and room preferences the guest said (only those).
        Answers with the room they get and whether early check-in applies."""
        if why := self._not_arriving():
            return f"Not done: {why}."
        c = self.guest.checkin
        if not c.id_verified:
            return "Not done: the guest has not scanned their ID yet. Ask them to tap Scan ID on screen first."
        args: dict[str, Any] = {}
        now = self.stay.now
        if prefs.arrival:
            arrival = self._arrival_option(prefs.arrival)
            if arrival is None:
                return f"Not done: '{prefs.arrival}' is not a time. Arrival options: now, 3:00 PM, 4:00 PM, 5:00 to 7:00 PM, after 7:00 PM."
            c.arrival = args["arrival"] = arrival
            if not h.early_offered(arrival, now):
                c.early = None
        if (floor := _choice(prefs.floor, _FLOORS)) is not None:
            c.floor = args["floor"] = floor
        if prefs.bed:
            bed = "queens" if "queen" in prefs.bed.lower() or "two" in prefs.bed.lower() else "king"
            c.bed = args["bed"] = bed
        if prefs.quiet is not None:
            c.quiet = prefs.quiet
            args["quiet"] = "yes" if prefs.quiet else "no"
        if not args:
            return "Nothing to set: ask for their arrival time and preferences."
        self._send("checkin.prefs", args)
        room = h.assign_room(c.floor, c.bed, c.quiet)
        out = f"Set. That gets room {room['room']}, floor {room['floor']} ({room['note']})."
        if not c.arrival:
            return out + " Still needed: their arrival time."
        if h.early_offered(c.arrival, now):
            ready = h.early_available(room, c.arrival, now)
            when = "now" if room["ready"] == "now" else f"by {h.clock(room['ready'])}"
            out += (
                f" They arrive before {h.clock(h.CHECKIN['early']['before'])}, so early check-in applies: the room is ready {when}"
                + (
                    f", and early check-in is {h.money(h.CHECKIN['early']['fee'])}. Ask if they want it."
                    if ready
                    else ", which is not in time; early check-in is not possible, standard check-in is 4:00 PM."
                )
            )
        else:
            out += " No early check-in needed. Next they review and press Complete check-in."
        return out

    def _arrival_option(self, said: str) -> str | None:
        s = said.strip().lower()
        if any(w in s for w in ("now", "here", "arrived", "lobby", "right away")):
            return "now"
        t = parse_time(said, self.stay.now)
        if t is None:
            return None
        n = h.minutes(t)
        if n <= h.minutes(self.stay.now) + 10:
            return "now"
        for opt, upto in (("15:00", "15:00"), ("16:00", "16:00"), ("17:00", "19:00")):
            if n <= h.minutes(upto):
                return opt
        return "19:00"

    async def set_early_check_in(self, choice: EarlyChoice) -> str:
        """Take, or not, early check-in, as the guest said. Then they review and
        press Complete check-in."""
        c = self.guest.checkin
        now = self.stay.now
        if not h.early_offered(c.arrival, now):
            return self._missed(
                "early check-in only applies when arriving before 4:00 PM.",
                "Early check-in doesn't apply to your arrival time, so there's no fee. You can review and press Complete check-in.",
            )
        room = h.assign_room(c.floor, c.bed, c.quiet)
        if choice.want and c.arrival and not h.early_available(room, c.arrival, now):
            return self._missed(
                "the room is not ready by their arrival.",
                f"I'm sorry, your room won't be ready until {h.clock(room['ready'])}, so early check-in isn't possible.",
            )
        c.early = choice.want
        self._send("checkin.early", {"want": "yes" if choice.want else "no"})
        landed("Done. Have a look at the summary and press Complete check-in when you're ready.")
        return f"Early check-in {'added, ' + h.money(h.CHECKIN['early']['fee']) if choice.want else 'declined'}. The review is on screen; the guest presses Complete check-in."

    # ── Check-out ──

    def _line(self, said: str) -> dict[str, Any] | None:
        lines = [ln for ln in self.guest.folio() if ln["amount"] > 0]
        for ln in lines:
            if said == ln["id"]:
                return ln
        s = _fold(said)
        by_cat = [ln for ln in lines if ln.get("category") and ln["category"] in s]
        if len(by_cat) == 1:
            return by_cat[0]
        hit = match_label(said, [ln["label"] for ln in lines])
        return next((ln for ln in lines if ln["label"] == hit), by_cat[0] if by_cat else None)

    @needs_result_now
    async def open_bill(self) -> str:
        """Open the folio and read every charge and the balance."""
        g = self.guest
        self._send("checkout.open", {"part": "folio"})
        lines = g.folio()
        rows = "; ".join(
            f"{h.day(ln['date']) if 'date' in ln else 'today'}: {ln['label']} {h.money(ln['amount'])}"
            + (" (under review)" if ln["id"] in g.disputes else "")
            + (f" [{ln['detail']}]" if ln.get("detail") else "")
            for ln in lines
        )
        bal = h.balance(lines, g.disputes)
        return f"The bill is open. {rows}. Balance due {h.money(bal)}, on the {h.GUEST['card']}."

    async def question_charge(self, q: ChargeQuestion) -> str:
        """Open a question about one charge with the guest's reason; with send,
        send it to the front desk (only once they agreed)."""
        ln = self._line(q.charge)
        if ln is None:
            names = [x["label"] for x in self.guest.folio() if x["amount"] > 0]
            return self._missed(
                f"no charge matches '{q.charge}'.",
                f"I couldn't find that charge. Which one do you mean: {_or(names[-4:])}?",
            )
        self._send("folio.dispute", {"line_id": ln["id"], "reason": q.reason, "send": q.send})
        if q.send:
            self.guest.disputes.add(ln["id"])
            landed(
                "Sent. It's held off your balance while the front desk reviews it, within 24 hours."
            )
            return f"Sent to the front desk: {ln['label']}. {h.DATA['dispute_rule']}"
        landed("I've written it up for the front desk. Shall I send it?")
        return f"The question about {ln['label']} ({h.money(ln['amount'])}) is filled in. Ask if they want it sent. {h.DATA['dispute_rule']}"

    @needs_result_now
    async def late_checkout(self, req: LateRequest) -> str:
        """Read the late check-out options, or pick the one the guest chose (they
        press Request)."""
        d = self.stay.depart
        opts = "; ".join(
            f"{o['label']}: {('complimentary' if not o['fee'] else h.money(o['fee']))}"
            + ("" if o["available"] else f" ({o['note']})")
            + (f" ({o['note']})" if o["available"] and o["note"] else "")
            for o in h.LATE["options"]
        )
        if not req.time:
            self._send("checkout.open", {"part": "late"})
            return f"Late check-out options for {h.day(d)} (standard check-out {h.HOTEL['check_out_time']}): {opts}. {h.LATE['rule']}"
        t = parse_time(req.time)
        o = next((x for x in h.LATE["options"] if x["id"] == t), None)
        if o is None:
            return f"No late check-out at '{req.time}'. Options: {opts}."
        if not o["available"]:
            return f"{o['label']} is {o['note']}. Options: {opts}."
        self._send("late.pick", {"time": o["id"]})
        return f"{o['label']} is selected ({'complimentary' if not o['fee'] else h.money(o['fee'])}); the guest presses Request. {h.LATE['rule']}"

    async def express_checkout(self) -> str:
        """Open the express check-out review (balance, card, receipt email). The
        guest presses Check out now."""
        g = self.guest
        if not g.checked_in:
            return self._missed(
                "not checked in.", "You'll need to check in before you can check out."
            )
        if g.checked_out:
            return self._missed("already checked out.", "You're already checked out.")
        self._send("checkout.open", {"part": "express"})
        bal = h.balance(g.folio(), g.disputes)
        landed(
            f"Here's your express check-out: {h.money(bal)} on your {h.GUEST['card']}. Press Check out now when you're ready."
        )
        return f"Express check-out is open: balance {h.money(bal)} on the {h.GUEST['card']}, receipt to {h.GUEST['email']}. The guest presses Check out now."

    # ── Dining and drinks ──

    def _item(self, outlet: str, said: str) -> dict[str, Any] | None:
        items = h.ITEMS[outlet]
        if said in items:
            return items[said]
        now = self.stay.now
        pool = list(items.values())
        if outlet == "dining":
            open_now = [i for i in pool if h.period_open(h.SECTIONS["dining"][i["section"]], now)]
            pool = open_now + [i for i in pool if i not in open_now]
        hit = match_label(said, list(dict.fromkeys(i["name"] for i in pool)))
        return next((i for i in pool if i["name"] == hit), None)

    def _section(self, outlet: str, said: str | None) -> str | None:
        if not said:
            return None
        s = _fold(said).replace(" ", "_")
        secs = h.SECTIONS[outlet]
        if s in secs:
            return s
        hit = match_label(said, [v["label"] for v in secs.values()])
        return next((k for k, v in secs.items() if v["label"] == hit), None)

    def _item_words(self, outlet: str, i: dict[str, Any]) -> str:
        price = (
            f"{h.money(i['price'])} a glass, {h.money(i['bottle'])} a bottle"
            if "bottle" in i
            else h.money(i["price"])
        )
        bits = [f"{i['name']} {price}: {i['desc']}"]
        if i.get("diet"):
            bits.append(", ".join(i["diet"]))
        if i.get("allergens"):
            bits.append("contains " + ", ".join(i["allergens"]))
        for gid, g in h.groups_of(i):
            if gid == "size":
                continue
            ch = ", ".join(
                lbl + (f" (+{h.money(add)})" if add else "") for _, lbl, add in g["choices"]
            )
            bits.append(f"{g['label']} ({'choose one' if g['pick'] else 'optional'}): {ch}")
        return "; ".join(bits)

    @needs_result_now
    async def show_menu(self, query: MenuQuery) -> str:
        """Open a menu (in-room dining or drinks) at a section, and read its items
        with prices, options, diet and allergens; with search, only what fits."""
        outlet = resolve_outlet(query.outlet)
        now = self.stay.now
        section = self._section(outlet, query.section)
        items = list(h.ITEMS[outlet].values())
        if section is None and outlet == "dining":
            section = h.open_period(now) if not query.search else None
        if section:
            items = [i for i in items if i["section"] == section]
        if query.search:
            want = _fold(query.search)

            def fits(i: dict[str, Any]) -> bool:
                text = _fold(f"{i['name']} {i['desc']} {' '.join(i.get('diet', []))}")
                if "gluten free" in want or "celiac" in want:
                    return "gluten" not in i.get("allergens", []) or "gluten-free" in i.get(
                        "diet", []
                    )
                if "vegan" in want:
                    return "vegan" in i.get("diet", [])
                if "vegetarian" in want or "veggie" in want:
                    return bool({"vegetarian", "vegan"} & set(i.get("diet", [])))
                if "nut" in want:
                    return not any("nut" in a for a in i.get("allergens", []))
                if "dairy" in want:
                    return "dairy" not in i.get("allergens", [])
                if "non alcoholic" in want or "zero" in want or "mocktail" in want:
                    return not i.get("alcohol")
                return any(w in text for w in want.split() if len(w) > 2)

            items = [i for i in items if fits(i)]
            if outlet == "dining":
                items = [
                    i for i in items if h.period_open(h.SECTIONS["dining"][i["section"]], now)
                ] or items
        args: dict[str, Any] = {"outlet": outlet}
        if section:
            args["section"] = section
        elif items:
            args["section"] = items[0]["section"]
        self._send("menu.open", args)
        head = []
        if outlet == "dining":
            p = h.SECTIONS["dining"][args.get("section") or h.open_period(now)]
            head.append(
                f"In-room dining, {p['label']} ({p['hours']}{', served now' if h.period_open(p, now) else ', NOT served now'}), delivery {p['eta']}."
            )
            head.append(h.DINING["policy"])
        else:
            head.append(
                f"Drinks, delivered in {h.BAR['eta']} to the room, or to a pool cabana while the pool bar is open (11:00 AM to 6:00 PM). {h.BAR['policy']} {h.BAR['age_rule']}"
            )
            if not h.alcohol_served(now):
                head.append("No alcohol can be served right now (2:00 to 6:00 AM).")
        if not items:
            return " ".join(head) + f" Nothing on this menu fits '{query.search}'."
        body = " | ".join(self._item_words(outlet, i) for i in items[:12])
        more = f" (and {len(items) - 12} more on screen)" if len(items) > 12 else ""
        return " ".join(head) + f" Items: {body}{more}"

    async def add_to_order(self, add: AddItem) -> str:
        """Add an item the guest chose, with every choice they made, to the in-room
        dining or drinks order (it is opened, set and added on screen). Ask first
        for any required choice they have not made."""
        outlet = resolve_outlet(add.outlet)
        if self.guest.checked_out:
            return self._missed(
                "checked out.", "You've checked out, so I can't send anything to the room."
            )
        item = self._item(outlet, add.item)
        if item is None:
            return self._missed(
                f"no {outlet} item '{add.item}'.",
                f"I couldn't find {add.item} on the {'menu' if outlet == 'dining' else 'drinks menu'}. Shall I read you what's there?",
            )
        now = self.stay.now
        if outlet == "dining":
            p = h.SECTIONS["dining"][item["section"]]
            if not h.period_open(p, now):
                return self._missed(
                    f"{p['label']} is served {p['hours']}.",
                    f"The {item['name']} is on the {p['label'].lower()} menu, served {p['hours']}, so I can't order it right now.",
                )
        elif item.get("alcohol") and not h.alcohol_served(now):
            return self._missed(
                "no alcohol from 2:00 to 6:00 AM.",
                "I'm sorry, we can't serve alcohol between 2 and 6 in the morning.",
            )
        choices = list(add.choices)
        if "bottle" in item and not any(
            "glass" in c.lower() or "bottle" in c.lower() for c in choices
        ):
            choices.append("glass") if "glass" in _fold(add.item) else None
        got, problems = h.check_choices(outlet, item["id"], choices)
        if problems:
            need = "; ".join(problems)
            return self._missed(f"{item['name']}: {need}.", f"For the {item['name']}, {need}?")
        args: dict[str, Any] = {
            "outlet": outlet,
            "item_id": item["id"],
            "qty": add.quantity,
            "choices": got,
            "add": True,
        }
        if add.note:
            args["note"] = add.note
        self._send("menu.item", args)
        line = Line(item["id"], add.quantity, got, add.note or "")
        self.guest.carts[outlet].append(line)
        t = h.order_totals(outlet, self.guest.carts[outlet], 0)
        landed(f"Added. Your order is {h.money(t.subtotal)} so far. Anything else?")
        return f"Added {self._line_words(outlet, line)} at {h.money(h.unit_price(outlet, line))} each. Order so far {h.money(t.subtotal)} before charges."

    async def remove_from_order(self, rm: RemoveItem) -> str:
        """Take an item off the order."""
        outlet = resolve_outlet(rm.outlet)
        lines = self.guest.carts[outlet]
        item = self._item(outlet, rm.item)
        idx = next((i for i, ln in enumerate(lines) if item and ln.item_id == item["id"]), None)
        if idx is None:
            names = [h.ITEMS[outlet][ln.item_id]["name"] for ln in lines]
            return self._missed(
                f"'{rm.item}' is not in the order.",
                f"That isn't in your order. You have {_or(names, 'and') or 'nothing yet'}.",
            )
        gone = lines.pop(idx)
        self._send("cart.remove", {"outlet": outlet, "item_id": gone.item_id})
        landed("Taken off.")
        return f"Removed {self._line_words(outlet, gone)}."

    @needs_result_now
    async def review_order(self, rv: ReviewOrder) -> str:
        """Open the order with its totals; set the tip and, for drinks, where it
        goes, only as the guest said. The guest presses Place order."""
        outlet = resolve_outlet(rv.outlet)
        g = self.guest
        lines = g.carts[outlet]
        if not lines:
            return "The order is empty: nothing to review."
        args: dict[str, Any] = {"outlet": outlet}
        tip = rv.tip_percent
        if tip is not None:
            if tip not in (0, 10, 15, 20):
                return "Tips are 0, 10, 15 or 20 percent: ask which."
            args["tip"] = tip
        if outlet == "bar" and rv.deliver_to:
            to = (
                "cabana"
                if "cabana" in rv.deliver_to.lower() or "pool" in rv.deliver_to.lower()
                else "room"
            )
            if to == "cabana" and not h.cabana_open(self.stay.now):
                return "Cabana delivery is only while the pool bar is open, 11:00 AM to 6:00 PM; it can go to the room."
            args["deliver_to"] = to
            if rv.cabana:
                if rv.cabana.strip() not in h.BAR["cabanas"]:
                    return "Cabanas are numbered 1 to 8: ask which."
                args["cabana"] = rv.cabana.strip()
        self._send("cart.open", args)
        t = h.order_totals(outlet, lines, tip or 0)
        policy = h.DINING if outlet == "dining" else h.BAR
        eta = (
            h.SECTIONS["dining"][h.ITEMS["dining"][lines[0].item_id]["section"]]["eta"]
            if outlet == "dining"
            else h.BAR["eta"]
        )
        items = "; ".join(
            f"{self._line_words(outlet, ln)} {h.money(h.unit_price(outlet, ln) * ln.qty)}"
            for ln in lines
        )
        out = (
            f"The order is open: {items}. Subtotal {h.money(t.subtotal)}, service charge {policy['service_charge_pct']:.0f}% {h.money(t.service)}"
            + (f", delivery {h.money(t.delivery)}" if t.delivery else "")
            + f", tax {h.money(t.tax)}"
            + (f", tip {tip}% {h.money(t.tip)}" if tip is not None else "")
            + f", total {h.money(t.total)}{'' if tip is not None else ' before any tip'}. Delivery in about {eta}, charged to room {g.room or '(assigned at check-in)'}."
        )
        missing = []
        if tip is None:
            missing.append("the tip (0, 10, 15 or 20 percent)")
        if outlet == "bar" and "deliver_to" not in args:
            missing.append("room or a pool cabana")
        if not g.checked_in:
            missing.append("check-in first: orders go to the room, which is assigned at check-in")
        if any(h.ITEMS[outlet][ln.item_id].get("alcohol") for ln in lines):
            out += f" {h.BAR['age_rule']}"
        return out + (
            f" Still to choose: {'; '.join(missing)}."
            if missing
            else " The guest presses Place order."
        )

    # ── Spa ──

    def _treatment(self, said: str) -> dict[str, Any] | None:
        if said in h.TREATMENTS:
            return h.TREATMENTS[said]
        s = _fold(said)
        mins = next((int(w) for w in s.split() if w.isdigit()), None)
        names = list(dict.fromkeys(t["name"] for t in h.TREATMENTS.values()))
        hit = match_label(said, names) or next((n for n in names if _fold(n).split()[0] in s), None)
        cands = [t for t in h.TREATMENTS.values() if t["name"] == hit]
        if not cands:
            return None
        if mins is not None:
            exact = [t for t in cands if t["minutes"] == mins]
            return exact[0] if exact else None
        return cands[0] if len(cands) == 1 else None

    def _treatment_options(self, said: str) -> str:
        s = _fold(said)
        cands = [t for t in h.TREATMENTS.values() if _fold(t["name"]).split()[0] in s] or list(
            h.TREATMENTS.values()
        )
        return _or([f"{h.treatment_label(t)} ({h.money(t['price'])})" for t in cands])

    @needs_result_now
    async def spa_treatments(self, q: SpaQuery) -> str:
        """Open the spa menu (at a category) and read the treatments with lengths
        and prices, the service charge and the cancellation policy."""
        cat = (q.category or "").lower().rstrip("s") or None
        cats = {"massage", "facial", "ritual", "nail"}
        args: dict[str, Any] = {}
        if cat in cats:
            args["category"] = "nails" if cat == "nail" else cat
        self._send("spa.open", args)
        ts = [
            t
            for t in h.TREATMENTS.values()
            if "category" not in args or t["category"] == args["category"]
        ]
        rows = "; ".join(
            f"{h.treatment_label(t)} {h.money(t['price'])}{' for two' if t.get('for_two') else ''}: {t['desc']}"
            for t in ts
        )
        return f"{h.SPA['name']}, {h.SPA['hours']}. {rows}. A {h.SPA['service_charge_pct']:.0f}% service charge is added. {h.SPA['cancellation']} {h.SPA['arrive']}"

    @needs_result_now
    async def spa_times(self, q: SpaTimes) -> str:
        """Open a treatment's booking sheet and read its free times for a day and a
        therapist preference."""
        t = self._treatment(q.treatment)
        if t is None:
            return f"Which treatment exactly? {self._treatment_options(q.treatment)}."
        d = parse_date(q.date, self.stay.today) if q.date else self.stay.today
        dates = self.stay.bookable_dates()
        if d not in dates:
            return (
                f"The spa can be booked {h.day(dates[0])} to {h.day(dates[-1])} during this stay."
            )
        pref = self._therapist_pref(q.therapist, t)
        args: dict[str, Any] = {"treatment_id": t["id"], "date": d}
        if pref != "any":
            args["therapist"] = pref
        self._send("spa.treatment", args)
        slots = h.spa_slots(self.stay, t["id"], d, pref)
        price, service, total = h.spa_total(t["id"])
        head = f"{h.treatment_label(t)}, {h.money(price)} plus {h.money(service)} service charge, {h.money(total)} in all."
        if not slots:
            other = next(
                (x for x in dates if x > d and h.spa_slots(self.stay, t["id"], x, pref)), None
            )
            return (
                head
                + f" No free times on {h.day(d)}"
                + (f"; the next day with times is {h.day(other)}." if other else ".")
            )
        times = "; ".join(f"{h.clock(x)} with {h.THERAPISTS[th]['name']}" for x, th in slots[:10])
        return head + f" Free on {h.day(d)}: {times}. {h.SPA['cancellation']}"

    def _therapist_pref(self, said: str | None, t: dict[str, Any]) -> str:
        if not said:
            return "any"
        s = _fold(said)
        if any(w in s for w in ("female", "woman", "women", "lady")):
            return "female"
        if any(w in s for w in (" male", "man", "men", "guy")) or s == "male":
            return "male"
        for tid in t["therapists"]:
            if h.THERAPISTS[tid]["name"].lower() in s:
                return tid
        return "any"

    async def choose_spa_time(self, pick: SpaPick) -> str:
        """Pick the free time (and therapist) the guest chose; they press Book."""
        t = self._treatment(pick.treatment)
        if t is None:
            return self._missed(
                f"no treatment '{pick.treatment}'.",
                f"Which treatment would you like: {self._treatment_options(pick.treatment)}?",
            )
        d = parse_date(pick.date, self.stay.today)
        tm = parse_time(pick.time)
        if d is None or tm is None:
            return self._missed("no day or time.", "Which day and time would you like?")
        pref = self._therapist_pref(pick.therapist, t)
        slots = h.spa_slots(self.stay, t["id"], d, pref)
        at = [th for x, th in slots if x == tm]
        if not at:
            near = ", ".join(h.clock(x) for x in dict.fromkeys(x for x, _ in slots[:6]))
            return self._missed(
                f"{h.clock(tm)} on {h.day(d)} is not free.",
                f"I'm sorry, {h.clock(tm)} isn't free on {h.day(d)}."
                + (f" There's {near}." if near else " There are no times left that day."),
            )
        th = at[0]
        self._send("spa.slot", {"treatment_id": t["id"], "date": d, "time": tm, "therapist_id": th})
        _, _, total = h.spa_total(t["id"])
        landed(
            f"I've picked {h.clock(tm)} with {h.THERAPISTS[th]['name']}, {h.money(total)} in all. Press Book when you're ready."
        )
        return f"Picked {h.treatment_label(t)} {h.day(d)} at {h.clock(tm)} with {h.THERAPISTS[th]['name']}, {h.money(total)} including service. The guest presses Book. {h.SPA['cancellation']}"

    # ── Activities ──

    def _activity(self, said: str) -> dict[str, Any] | None:
        if said in h.ACTIVITIES:
            return h.ACTIVITIES[said]
        s = _fold(said)
        for a in h.ACTIVITIES.values():
            if _fold(a["name"]) in s or s in _fold(a["name"]):
                return a
        keys = {
            "kayak": "kayak-tour",
            "tide": "tide-pools",
            "wine": "wine-shuttle",
            "golf": "golf",
            "tennis": "tennis",
            "yoga": "sunrise-yoga",
            "hiit": "hiit",
            "pilates": "pilates",
            "kids": "kids-club",
            "jazz": "jazz-trio",
            "music": "jazz-trio",
            "s'more": "smores",
            "smore": "smores",
        }
        aid = next((v for k, v in keys.items() if k in s), None)
        if aid:
            return h.ACTIVITIES[aid]
        hit = match_label(said, [a["name"] for a in h.ACTIVITIES.values()])
        return next((a for a in h.ACTIVITIES.values() if a["name"] == hit), None)

    @needs_result_now
    async def find_activities(self, q: ActivityQuery) -> str:
        """Open activities (things to do, with the resort map) and read them with
        times, places and prices."""
        kinds = {
            "pool": "pools",
            "kid": "kids",
            "golf": "golf",
            "tennis": "sport",
            "sport": "sport",
            "fitness": "fitness",
            "yoga": "fitness",
            "class": "fitness",
            "tour": "tours",
            "music": "music",
            "tonight": "music",
            "live": "music",
        }
        kind = next((v for k, v in kinds.items() if q.kind and k in q.kind.lower()), None)
        self._send("app.go", {"page": "activities"})
        acts = [a for a in h.ACTIVITIES.values() if kind is None or a["kind"] == kind]
        rows = "; ".join(
            f"{a['name']} ({h.PLACES[a['place']]['name']}, {a['hours']}, "
            + (f"{h.money(a['price'])} per {a.get('per', 'guest')}" if a["price"] else "free")
            + (", book ahead" if a["bookable"] else ", no booking needed")
            + (f", {a['min_age']}+" if a.get("min_age") else "")
            + f"): {a['desc']}"
            for a in acts
        )
        return f"Activities on screen: {rows}."

    async def show_on_map(self, q: PlaceQuery) -> str:
        """Pin an activity or a place on the resort map."""
        a = self._activity(q.place)
        if a is None:
            hit = match_label(q.place, [p["name"] for p in h.PLACES.values()])
            place = next((p for p in h.PLACES.values() if p["name"] == hit), None)
            a = next(
                (x for x in h.ACTIVITIES.values() if place and x["place"] == place["id"]), None
            )
        if a is None:
            return self._missed(f"no place '{q.place}'.", "I couldn't find that on the resort map.")
        self._send("activity.show", {"activity_id": a["id"], "map": True})
        landed(f"Here it is on the map: the {h.PLACES[a['place']]['name']}.")
        return f"{a['name']} pinned at the {h.PLACES[a['place']]['name']}."

    async def book_activity(self, b: ActivityBooking) -> str:
        """Set up an activity booking the guest chose (day, time, guests); they
        press Book."""
        a = self._activity(b.activity)
        if a is None:
            return self._missed(
                f"no activity '{b.activity}'.", "Which activity would you like to book?"
            )
        if not a["bookable"]:
            return self._missed(
                f"{a['name']} needs no booking.",
                f"No booking needed for the {a['name']}: just come along, {a['hours']}.",
            )
        d = parse_date(b.date, self.stay.today)
        tm = parse_time(b.time)
        if d not in self.stay.bookable_dates():
            return self._missed(
                "not a day of the stay.",
                f"I can book days of your stay, through {h.day(self.stay.depart)}.",
            )
        times = h.activity_times(self.stay, a["id"], d) if d else []
        if tm not in times:
            said = _or([h.clock(x) for x in times])
            return self._missed(
                f"{a['name']} on {h.day(d or self.stay.today)} runs at {said or 'no more times'}.",
                f"The {a['name']} on {h.day(d or self.stay.today)} "
                + (
                    f"is at {said}. Which would you like?"
                    if said
                    else "has no more times that day."
                ),
            )
        if a.get("capacity") and b.guests > a["capacity"]:
            return self._missed(
                f"at most {a['capacity']}.", f"The {a['name']} takes up to {a['capacity']} people."
            )
        self._send(
            "activity.pick", {"activity_id": a["id"], "date": d, "time": tm, "guests": b.guests}
        )
        total = h.activity_total(a["id"], b.guests)
        landed(
            f"It's all set up{f', {h.money(total)} on your room' if total else ''}. Press Book to confirm."
        )
        return (
            f"{a['name']} {h.day(d)} at {h.clock(tm)} for {b.guests}: {h.money(total) if total else 'free'}. The guest presses Book."
            + (f" Guests must be {a['min_age']} or over." if a.get("min_age") else "")
        )

    # ── Meetings ──

    def _layout(self, said: str | None) -> str | None:
        if not said:
            return None
        s = _fold(said)
        for k in ("boardroom", "classroom", "theatre", "banquet"):
            if k in s or (k == "theatre" and "theater" in s):
                return k
        return "u_shape" if "u" in s.split() or "u shape" in s else None

    def _meeting_room(self, said: str) -> dict[str, Any] | None:
        if said in h.ROOMS:
            return h.ROOMS[said]
        s = _fold(said)
        for r in h.ROOMS.values():
            if _fold(r["name"]).split()[0] in s:
                return r
        hit = match_label(said, [r["name"] for r in h.ROOMS.values()])
        return next((r for r in h.ROOMS.values() if r["name"] == hit), None)

    @needs_result_now
    async def meeting_rooms(self, q: MeetingQuery) -> str:
        """Open meeting rooms filtered by headcount and layout, and read which fit,
        their rates and which blocks are free on a day."""
        layout = self._layout(q.layout)
        d = parse_date(q.date, self.stay.today) if q.date else None
        if d and d not in h.MEETINGS["dates"]:
            return f"Meeting rooms can be booked on {', '.join(h.day(x) for x in h.MEETINGS['dates'])}."
        args: dict[str, Any] = {}
        if q.headcount:
            args["headcount"] = q.headcount
        if layout:
            args["layout"] = layout
        if d:
            args["date"] = d
        self._send("meeting.filter", args)
        rooms = h.rooms_for(q.headcount, layout)
        if not rooms:
            return "No room fits that headcount and layout. Largest: the Grand Halcyon Ballroom, 300 theatre, 180 classroom, 220 banquet."
        rows: list[str] = []
        for r in rooms:
            caps = ", ".join(
                f"{h.MEETINGS['layout_labels'][k]} {v}" for k, v in r["layouts"].items()
            )
            rates = r["rates"]
            line = f"{r['name']} ({caps}; {h.money(rates['hour'])} an hour, {h.money(rates['half'])} half day, {h.money(rates['full'])} full day; {r['av']})"
            if d:
                free = [
                    b["label"].lower()
                    for b in h.MEETINGS["blocks"]
                    if b["id"] != "hours" and h.room_free(r["id"], d, (b["from"], b["to"]))
                ]
                line += f": on {h.day(d)} free for " + (
                    _or(free) if free else "no half or full day blocks"
                )
            rows.append(line)
        return "Rooms that fit: " + "; ".join(rows) + f". {h.MEETINGS['policy']}"

    @needs_result_now
    async def quote_meeting(self, b: MeetingBooking) -> str:
        """Fill a meeting room booking with everything the guest said and read the
        estimate. They press Request booking."""
        r = self._meeting_room(b.room)
        if r is None:
            return f"No room '{b.room}'. Rooms: {', '.join(x['name'] for x in h.ROOMS.values())}."
        layout = self._layout(b.layout)
        if layout not in r["layouts"]:
            return f"{r['name']} sets up as {_or([h.MEETINGS['layout_labels'][k] for k in r['layouts']])}."
        if b.headcount > r["layouts"][layout]:
            return f"{r['name']} seats {r['layouts'][layout]} {h.MEETINGS['layout_labels'][layout].lower()}; that is too small for {b.headcount}."
        d = parse_date(b.date, self.stay.today)
        if d is None or d not in h.MEETINGS["dates"]:
            return f"Bookable dates: {', '.join(h.day(x) for x in h.MEETINGS['dates'])}."
        bs = _fold(b.block)
        block = (
            "full"
            if "full" in bs
            else "morning"
            if "morn" in bs
            else "afternoon"
            if "after" in bs
            else "hours"
        )
        start = parse_time(b.start) if b.start else None
        span = h.block_span(block, start, b.hours)
        if span is None:
            return "By the hour needs a start time and how many hours."
        if not h.room_free(r["id"], d, span):
            return f"{r['name']} is taken then on {h.day(d)}; ask for another time or room."
        cat_ids = [
            c["id"]
            for c in h.MEETINGS["catering"]
            if any(
                _fold(c["name"]).split()[0] in _fold(x) or c["id"] in _fold(x) for x in b.catering
            )
        ]
        av_ids = [
            a["id"]
            for a in h.MEETINGS["av_addons"]
            if any(
                k in _fold(x)
                for x in b.av
                for k in ({"mics": ("mic",), "recording": ("record",), "tech": ("tech",)}[a["id"]])
            )
        ]
        args: dict[str, Any] = {
            "room_id": r["id"],
            "date": d,
            "block": block,
            "headcount": b.headcount,
            "layout": layout,
            "catering": cat_ids,
            "av": av_ids,
        }
        if block == "hours":
            args["start"], args["hours"] = start, b.hours
        self._send("meeting.pick", args)
        q = h.meeting_quote(r["id"], block, b.hours, b.headcount, cat_ids, av_ids)
        parts = [f"room {h.money(q.room)}"]
        if q.catering:
            parts.append(
                f"catering {h.money(q.catering)} plus {h.money(q.fb_service)} service and {h.money(q.tax)} tax"
            )
        if q.av:
            parts.append(f"AV {h.money(q.av)}")
        return (
            f"The booking is filled in: {r['name']}, {h.day(d)}, {h.clock(span[0])} to {h.clock(span[1])}, {b.headcount} people, "
            f"{h.MEETINGS['layout_labels'][layout].lower()}. Estimate {h.money(q.total)} ({'; '.join(parts)}). The guest presses Request booking. {h.MEETINGS['policy']}"
        )

    # ── Visitors ──

    def _visitor(self, said: str) -> dict[str, Any] | None:
        pend = h.VISITORS["pending"]
        s = _fold(said)
        for v in pend:
            if v["id"] == said or any(w in s for w in _fold(v["name"]).split() if len(w) > 3):
                return v
        hit = match_label(said, [v["name"] for v in pend])
        return next((v for v in pend if v["name"] == hit), None)

    @needs_result_now
    async def visitors(self) -> str:
        """Open visitors and read who is waiting at the front desk."""
        self._send("app.go", {"page": "visitors"})
        g = self.guest
        rows = [
            f"{v['name']}: {v['purpose']}, waiting {v['waiting_min']} minutes at the {v['where'].lower()}"
            + (
                ""
                if g.visitors.get(v["id"]) == "pending"
                else f" (already {g.visitors.get(v['id'])})"
            )
            for v in h.VISITORS["pending"]
        ]
        return "Visitors: " + "; ".join(rows) + f". {h.VISITORS['rule']}"

    async def open_visitor(self, q: VisitorOpen) -> str:
        """Open a waiting visitor's request (with where to meet, if the guest said);
        the guest presses Approve or Decline."""
        v = self._visitor(q.visitor)
        if v is None:
            names = [
                x["name"]
                for x in h.VISITORS["pending"]
                if self.guest.visitors.get(x["id"]) == "pending"
            ]
            return self._missed(
                f"no visitor '{q.visitor}'.",
                f"I don't see that name at the desk. Waiting now: {_or(names, 'and') or 'nobody'}.",
            )
        status = self.guest.visitors.get(v["id"])
        if status != "pending":
            return self._missed(
                f"{v['name']} was already {status}.", f"{v['name']} was already {status}."
            )
        args: dict[str, Any] = {"visitor_id": v["id"]}
        meet = None
        if q.meet:
            meet = "lobby" if "lobby" in q.meet.lower() or "wait" in q.meet.lower() else "room"
            args["meet"] = meet
        self._send("visitor.open", args)
        landed(f"Here's {v['name']}'s request. Press Approve or Decline.")
        return (
            f"{v['name']}'s request is open"
            + (
                f", meeting {'in the lobby' if meet == 'lobby' else 'in the room'}"
                if meet
                else ", where to meet not chosen yet"
            )
            + ". The guest presses Approve or Decline."
        )

    async def expect_visitor(self, q: VisitorExpect) -> str:
        """Fill the form for a visitor the guest is expecting; they press Add visitor."""
        a, b = parse_time(q.from_time), parse_time(q.to_time)
        if not q.name.strip() or a is None or b is None:
            return self._missed(
                "needs a name and an arrival window.",
                "Who are you expecting, and between what times?",
            )
        if a >= b:
            return self._missed("the window ends before it starts.", "When does the window end?")
        if b > h.VISITORS["until"]:
            return self._missed(
                "visitors only until 10:00 PM.",
                "Visitors are welcome until 10 PM. Shall I make the window end by then?",
            )
        args: dict[str, Any] = {"name": q.name.strip(), "arrive_from": a, "arrive_to": b}
        if q.meet:
            args["meet"] = "lobby" if "lobby" in q.meet.lower() else "room"
        if q.note:
            args["note"] = q.note
        self._send("visitor.expect", args)
        landed("It's filled in. Press Add visitor to put them on the list.")
        return (
            f"{q.name}, {h.clock(a)} to {h.clock(b)}, is filled in. The guest presses Add visitor."
        )

    # ── Front desk ──

    @staticmethod
    def _kind(said: str) -> str | None:
        s = _fold(said)
        table = {
            "housekeeping": (
                "house",
                "towel",
                "pillow",
                "clean",
                "turndown",
                "toiletr",
                "robe",
                "crib",
                "disturb",
            ),
            "maintenance": ("mainten", "repair", "broken", "fix", "engineer", "ac", "heat", "leak"),
            "wakeup": ("wake",),
            "valet": ("valet", "my car", "car from"),
            "transport": (
                "transport",
                "taxi",
                "cab",
                "ride",
                "airport",
                "shuttle",
                "house car",
                "sedan",
            ),
            "lost_found": ("lost", "found", "missing", "left"),
        }
        if s.replace(" ", "_") in table:
            return s.replace(" ", "_")
        return next(
            (k for k, keys in table.items() if any(x in s.split() or x in s for x in keys)), None
        )

    async def front_desk_request(self, r: DeskRequest) -> str:
        """Fill a front desk request (housekeeping, maintenance, wake-up call, car
        from valet, a ride, lost and found); with send, send it (free requests
        only, after the guest said yes)."""
        kind = self._kind(r.kind)
        if kind is None:
            return self._missed(
                f"no request kind '{r.kind}'.",
                "I can arrange housekeeping, maintenance, a wake-up call, your car, a ride or lost and found. Which would you like?",
            )
        rq = h.REQUESTS
        args: dict[str, Any] = {"kind": kind}
        missing: str | None = None
        if kind == "housekeeping":
            items = [
                i["id"]
                for i in rq["housekeeping"]["items"]
                if any(
                    i["id"] in _fold(x)
                    or _fold(i["label"]).split()[-1] in _fold(x)
                    or (i["id"] == "dnd" and "disturb" in _fold(x))
                    for x in r.items
                )
            ]
            if not items:
                missing = "what they need"
            args["items"] = items
        elif kind == "maintenance":
            issue = r.issue and next(
                (
                    i["id"]
                    for i in rq["maintenance"]["issues"]
                    if i["id"] == _fold(r.issue)
                    or i["id"] in _fold(r.issue)
                    or _fold(i["label"]).split()[0] in _fold(r.issue)
                ),
                None,
            )
            if not issue:
                missing = "what is wrong"
            else:
                args["issue"] = issue
        elif kind == "wakeup":
            d = parse_date(r.date, self.stay.today) if r.date else None
            t = parse_time(r.time) if r.time else None
            if t and not d:
                d = (
                    self.stay.today
                    if h.minutes(t) > h.minutes(self.stay.now)
                    else parse_date("tomorrow", self.stay.today)
                )
            if not (d and t):
                missing = "the day and time"
            else:
                args["date"], args["time"] = d, t
        elif kind == "valet":
            t = parse_time(r.time, self.stay.now) if r.time else None
            if not t:
                missing = "when they need the car"
            else:
                args["time"] = t
        elif kind == "transport":
            s = _fold(r.option or r.details or "")
            opt = (
                "airport"
                if "airport" in s
                else "taxi"
                if ("taxi" in s or "cab" in s)
                else "house-car"
                if ("house" in s or "shuttle" in s or "car" in s)
                else None
            )
            t = parse_time(r.time, self.stay.now) if r.time else None
            if opt:
                args["option"] = opt
            if t:
                args["time"] = t
            if not (opt and t):
                missing = "which ride and when"
        elif kind == "lost_found" and not (r.details or "").strip():
            missing = "what they lost and where"
        if r.details:
            args["details"] = r.details
        fee = 0.0
        if kind == "transport" and args.get("option"):
            fee = next(
                o["price"] or 0.0 for o in rq["transport"]["options"] if o["id"] == args["option"]
            )
        send = r.send and not missing and not fee
        args["send"] = send
        self._send("request.fill", args)
        if send:
            label = kind.replace("_", " ")
            self.guest.requests.append(label)
            landed("Sent. Anything else I can do?")
            eta = {
                "housekeeping": rq["housekeeping"]["eta"],
                "maintenance": rq["maintenance"]["eta"],
                "valet": rq["valet"]["eta"],
            }.get(kind)
            extra = (
                rq["wakeup"]["note"]
                if kind == "wakeup"
                else rq["valet"]["rate"]
                if kind == "valet"
                else f"Expect {eta}."
                if eta
                else ""
            )
            return f"Sent to the front desk. {extra}".strip()
        if missing:
            landed("It's open on screen. Tell me the rest and I'll fill it in.")
            return f"The request is open; still needed: {missing}."
        if fee:
            landed(f"It's filled in: {h.money(fee)}, fixed fare. Press Send to book it.")
            return f"Filled in. It costs {h.money(fee)}, so the guest presses Send."
        landed("It's filled in. Shall I send it?")
        return "Filled in and ready. Ask if they want it sent, then call again with send=true."


#: Live calls by session id, for a redial to rejoin (rejoin.py).
REJOIN: Rejoin[BelmonteBrain] = Rejoin()

__all__ = ["REJOIN", "BelmonteBrain", "Guest"]
