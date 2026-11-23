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
:mod:`.homes`. The character — name, voice per language, the languages offered
and the default — comes from ``persona.json`` (:mod:`.persona`).
"""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from loguru import logger
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from voqalize_demos import PATIENCE, FallbackLine, configure_soon, landed, needs_result_now

from voqalize.sdk import Action, AppEvents, RTVIMessage, Session, Speech, UserIdle, UserMessage
from voqalize.sdk.openai import OpenAIBrain
from voqalize.sdk.stage import Mirror, Move, Stage, match_label
from voqalize.sdk.stage.wire import StageEvent, StageHello, StageProgress, StageResult
from voqalize.sdk.wire import Config, IdleConfig, RedialConfig, SttConfig, TtsConfig

from . import homes as h
from .lines import BOOKING, BRING_SHORT, GREETING, LANDED, NO_WORDS, YES_WORDS
from .persona import PERSONA, Persona
from .prompt import system_instruction
from .rejoin import Rejoin
from .stage_gen import MOVES as STAGE_MOVES
from .stage_gen import SPEC, ReadRequest

MODEL = "gpt-6.1-terra"
REASONING = "medium"

_EVENTS = AppEvents(StageResult, StageHello, StageProgress, StageEvent)

#: The quiet spell before the agent may speak up by itself, and how short it gets
#: while it has a line to say (a booking's outcome, a visitor's booking).
_IDLE_MS = 15000
_SAY_NOW_MS = 400
_REACT_IDLE_MS = 1500

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")

Job = Literal["guide", "booker"]

for _table in (*LANDED.values(), *GREETING.values(), *BOOKING.values()):
    assert set(PERSONA.languages) <= set(_table), "a persona language has no written line"


class LanguageChanged(Action):
    """The call's language moved: the page's EN / हिंदी toggle follows."""

    language: str


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
    office: str | None = Field(default=None, description="Office id or name for the commute.")
    max_km: float | None = Field(default=None, description="Most km from the office.")
    school_km: float | None = Field(default=None, description="A school within this many km.")
    metro_km: float | None = Field(default=None, description="Metro within this many km.")
    amenities: list[str] | None = None
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
        description="YYYY-MM-DD, a weekday name (saturday), today or tomorrow. Empty: the week.",
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
    t = " " + re.sub(r"[^\wऀ-ॿ ]", " ", text.lower()) + " "
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
        self.results: list[str] = [x["id"] for x in h.search(self.search)]
        self.shortlisted: list[str] = []
        self.taken: set[str] = set()  # "<host key>|<slot id>": a host can be in one place at once
        self.booked: dict[str, Proposal] = {}  # reference → booking
        self.pending: Proposal | None = None
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
        return GREETING[self.job][self.lang].format(name=self.persona.name, title=title)

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

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[Speech, None]:
        self.turns += 1
        self.stage.visitor_spoke()
        self._talk = None
        self._settle_expired()
        if self.lang != "hi" and "hi" in self.persona.languages and _DEVANAGARI.search(msg.text):
            await session.configure(self._speaking("hi"))
        self.append_note(self.screen_now())
        self.append_note(msg.text)
        pending = self.pending
        if pending is not None and pending.turn < self.turns:
            answer = _yes_no(msg.text)
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
        """The model's turn with its cues sent to the page, and a written line
        under a turn that moved the screen in silence."""
        turn = self.stage.cued(super().respond(session))
        async for event in self._fallback.speak_if_silent(self, turn):
            yield event
        self.stage.end_turn()

    def on_user_idle(self, session: Session, idle: UserIdle) -> AsyncGenerator[Speech, None]:
        return self._idle(session)

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
            extra += f" Waiting for their yes to book {p.listing_id} at {p.slot}."
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
                self.results = [x["id"] for x in h.search(self.search)]
            case "shortlist.changed":
                self.shortlisted = [str(i) for i in data.get("ids") or []]
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

    def _booked_line(self, p: Proposal) -> str:
        x = h.LISTINGS[p.listing_id]
        d = date.fromisoformat(p.slot[:10])
        when = f"{h.spoken_day(d)}, {h.spoken_time(p.slot[11:16])}"
        return BOOKING["booked"][self.lang].format(
            when=when,
            reference=h.reference(p.listing_id, p.slot),
            contact=h.host(x).contact,
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

    @needs_result_now
    async def search_homes(self, request: SearchRequest) -> str:
        """Set the listings page's search from what the buyer said: the sidebar
        filters tick one by one and the map follows. Pass only what changed."""
        s = h.Search() if request.reset else h.Search(**vars(self.search))
        for name in request.clear or []:
            if hasattr(s, name):
                setattr(s, name, [] if isinstance(getattr(s, name), list) else None)
        given = request.model_dump(exclude={"clear", "reset"}, exclude_none=True)
        notes: list[str] = []
        if "localities" in given:
            names = h.localities(given.get("city") or s.city)
            picked = [m for m in (match_label(v, names) for v in given["localities"]) if m]
            if len(picked) < len(given["localities"]):
                notes.append(f"Known localities: {', '.join(names)}.")
            given["localities"] = picked
        if "office" in given:
            offices = h.places("office", given.get("city") or s.city)
            by_name = {o["name"]: o["id"] for o in offices}
            ids = {o["id"] for o in offices}
            raw = str(given["office"])
            office = raw if raw in ids else by_name.get(match_label(raw, list(by_name)) or "")
            if office is None:
                return (
                    f"No office called {raw!r}. Offices: "
                    + ", ".join(f"{o['name']} ({o['id']})" for o in offices)
                    + ". Nothing changed on screen."
                )
            given["office"] = office
            if not given.get("city"):
                given["city"] = next(o["city"] for o in offices if o["id"] == office)
        for key, value in given.items():
            setattr(s, key, value)
        self.search = s
        found = h.search(s)
        self.results = [x["id"] for x in found]
        self._send("listings.filter", s.args(), "filter")
        if not found:
            return (
                f"No homes match {s.summary()}. The list on screen is empty. Say so and suggest "
                "loosening one thing (budget, distance or locality)."
            )
        lines = [f"{len(found)} homes match {s.summary()}; on screen in this order:"]
        for x in found[:5]:
            extra = ""
            if s.office:
                extra = f", {h.office_km(x, s.office)} km to {h.place_name(s.office)}"
            lines.append(
                f"{x['id']} {x['title']}, {x['locality']}, {h.price_line(x)}, "
                f"{x['carpet_sqft']} sq ft, {x['possession_date']}{extra}, metro "
                f"{x['nearby']['metro'][0]['km']} km, school {x['nearby']['schools'][0]['km']} km."
            )
        return " ".join(lines + notes)

    @needs_result_now
    async def home_facts(self, request: ListingRef) -> str:
        """Everything the site says about one home, to answer a question about it.
        Changes nothing on screen."""
        x = self._listing(request.listing_id)
        if x is None:
            return f"No listing {request.listing_id}."
        project = h.PROJECTS.get(x["project_id"] or "")
        more = (
            f" Project {project['name']}: {project['pitch']} {project['towers']} towers, "
            f"{project['units']} homes on {project['acres']} acres."
            if project
            else ""
        )
        return h.facts(x) + more

    async def open_listing(self, request: ListingRef) -> str:
        """Open one home's page (where a site visit is booked)."""
        x = self._listing(request.listing_id)
        if x is None:
            return f"No listing {request.listing_id}."
        self._send("site.go", {"path": f"/listing/{x['id']}"}, "open")
        return f"opening {x['id']}, {x['title']}"

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

    @needs_result_now
    async def compare_homes(self, request: CompareRequest) -> str:
        """Put two or three homes side by side and read the comparison."""
        ids = [i.strip().upper() for i in request.listing_ids]
        missing = [i for i in ids if i not in h.LISTINGS]
        if missing or not 2 <= len(ids) <= 3:
            return f"Compare needs two or three listing ids; unknown: {', '.join(missing) or '-'}."
        self._send("compare.show", {"ids": ids}, "compare")
        rows = h.compare_rows(ids)
        out = [f"Comparing {' vs '.join(ids)}."]
        for label, values, best in rows:
            mark = f" (better: {ids[best]})" if best is not None else ""
            out.append(f"{label}: {' | '.join(values)}{mark}.")
        return " ".join(out)

    @needs_result_now
    async def estimate_emi(self, request: EmiRequest) -> str:
        """Work out a home loan's EMI for a home to buy, on screen, from the
        site's lender rates. Defaults: 20% down, 20 years."""
        x = self._listing(request.listing_id)
        if x is None or x["deal"] != "buy":
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
        self._send(
            "emi.show",
            {"listing_id": x["id"], "down_pct": down, "tenure_years": years, "lender": lender},
            "emi",
        )
        others = [
            f"{v['name']} {v['rate']}%: {h.inr(h.emi(x['price'], down, years, k).emi)}"
            for k, v in h.LENDERS.items()
            if k != lender and (k != "kosha-partner" or x["kind"] == "new")
        ]
        return (
            f"{x['id']} at {h.short(x['price'])}: {down:g}% down is {h.short(x['price'] - e.principal)}, "
            f"loan {h.short(e.principal)} over {years} years with {e.lender['name']} at "
            f"{e.lender['rate']}%: EMI {h.inr(e.emi)} a month, total interest {h.short(e.total_interest)}. "
            f"{e.lender['note']} Other lenders: {'; '.join(others)}."
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

    def _day(self, text: str | None) -> date | None | Literal["closed"]:
        days = h.visit_days()
        if not text:
            return None
        t = text.strip().lower()
        if t == "tomorrow":
            return days[0]
        for d in days:
            if t in (d.isoformat(), d.strftime("%A").lower(), d.strftime("%a").lower()):
                return d
        return "closed"

    @needs_result_now
    async def visit_slots(self, request: SlotsRequest) -> str:
        """The free site-visit slots for a home, in IST, where the buyer's
        preferred day and time meet the sales team's diary. Shows them on the
        listing's visit panel."""
        x = self._listing(request.listing_id)
        if x is None:
            return f"No listing {request.listing_id}."
        host = h.host(x)
        days = h.visit_days()
        day = self._day(request.day)
        if day == "closed":
            return (
                f"Visits can be booked on {', '.join(h.spoken_day(d) for d in days)} only "
                f"(the next seven days). Ask which of these."
            )
        if day is None:
            week: list[str] = []
            for d in days:
                free = h.free_slots(x, d, request.part, self._held(x))
                if h.day_slots(x, d) is None:
                    week.append(f"{h.spoken_day(d)} ({d.isoformat()}): closed")
                else:
                    week.append(f"{h.spoken_day(d)} ({d.isoformat()}): {len(free)} free")
            return f"{host.contact}'s team, {request.part}: " + "; ".join(week) + ". Ask which day."
        if not self.path.startswith(f"/listing/{x['id']}"):
            self._send("site.go", {"path": f"/listing/{x['id']}"}, "open")
        self._send(
            "visit.slots",
            {"listing_id": x["id"], "day": day.isoformat(), "part": request.part},
            "slots",
        )
        if h.day_slots(x, day) is None:
            nxt = [
                h.spoken_day(d) for d in days if h.free_slots(x, d, request.part, self._held(x))
            ][:3]
            return (
                f"The sales team does not take visits on {h.spoken_day(day)}. "
                f"Days with free {request.part} slots: {', '.join(nxt) or 'none this week'}."
            )
        free = h.free_slots(x, day, request.part, self._held(x))
        if not free:
            other = [s.time for s in h.free_slots(x, day, "any", self._held(x))][:4]
            return (
                f"No free {request.part} slots on {h.spoken_day(day)}. Other free times that day: "
                f"{', '.join(h.spoken_time(t) for t in other) or 'none'}."
            )
        slots = ", ".join(f"{h.spoken_time(s.time)} ({s.id})" for s in free[:6])
        return (
            f"Free on {h.spoken_day(day)} ({request.part}): {slots}. Visits are "
            f"{host.team['slot_minutes']} minutes with {host.contact}."
        )

    @needs_result_now
    async def propose_visit(self, request: ProposeRequest) -> str:
        """Hold one free slot for the buyer, before they confirm. Then ask them
        to confirm in plain words; their yes books it."""
        x = self._listing(request.listing_id)
        if x is None:
            return f"No listing {request.listing_id}."
        slot = request.slot.strip()
        try:
            day = date.fromisoformat(slot[:10])
        except ValueError:
            return "The slot must be an id like 2026-11-22T10:30 from visit_slots."
        free = {s.id for s in h.free_slots(x, day, "any", self._held(x))}
        if slot not in free:
            return f"{slot} is not a free slot. Call visit_slots for that day and offer a free one."
        name = request.name.strip()
        if not name:
            return "Ask for their name first."
        visitors = min(max(request.visitors, 1), 6)
        self.pending = Proposal(x["id"], slot, name, visitors, self.turns)
        when = f"{h.spoken_day(day)} at {h.spoken_time(slot[11:16])}"
        return (
            f"Held: {when} for {name}, {visitors} visitor{'s' if visitors > 1 else ''}, at "
            f"{x['title']}. Ask them to confirm; nothing is booked until they say yes."
        )

    async def book_visit(self, request: BookRequest) -> str:
        """Book the held visit. Only after the buyer just said yes to it."""
        if self.pending is None:
            return "Nothing is held. Find a free slot and propose it first."
        if not request.buyer_said_yes or self.pending.turn >= self.turns:
            return "Not booked: ask them to confirm first and wait for their yes."
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
