"""PaynoraSiteBrain: the sales agent on Paynora's marketing site.

An :class:`~voqalize.sdk.openai.OpenAIBrain`. One brain, three jobs, picked by
the page the call starts on (``init.page``) and followed as the visitor moves
(Stage's ``screen.viewed``):

- **Sales rep** on ``/`` and the product pages: qualifies the visitor
  (headcount, current tool, states, pains), fills the lead card on screen field
  by field and marks the module cards that fit.
- **Pricing explainer** on ``/pricing``: works out the plan by
  ``pricing_rules.plan_choice``, sets the calculator control by control and
  talks the per-employee maths through line by line.
- **Demo booker** on ``/book-demo``: shows the sales calendar, picks a free
  slot, fills the booking form, and confirms only after the visitor's spoken yes.

Every move on screen is a Stage move (``frontend/src/stage/scene.json``): tools
send them with :meth:`Stage.send`, and the ``{show:}``, ``{module:}`` and
``{line:}`` cues ring what the voice is talking about. The page reports what the
visitor does as Stage events, folded into the brain's own state.

Every number comes from ``data/product.json`` and ``content/site.json`` through
:mod:`.pricing` and :mod:`.calendar_rules`, whose twins on the page are pinned
to the same fixtures. The character comes from ``persona.json``.
"""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

from loguru import logger
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from voqalize_demos import PATIENCE, FallbackLine, configure_soon, landed, needs_result_now

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
from voqalize.sdk.openai import OpenAIBrain
from voqalize.sdk.stage import Mirror, Move, Stage, match_label
from voqalize.sdk.stage.wire import StageEvent, StageHello, StageProgress, StageResult
from voqalize.sdk.wire import Config, IdleConfig, RedialConfig, SttConfig, TtsConfig

from . import calendar_rules as cal
from .data import LEAD, MODULES, PAGES, PAINS, PLANS, STATES, TOPICS
from .lines import BOOKING, GREETING, LANDED, NO_WORDS, TOGGLE_CONFIRM, YES_WORDS
from .persona import PERSONA, Persona
from .pricing import choose_plan, quote, spoken
from .prompt import system_instruction
from .rejoin import Rejoin
from .spoken import SpokenAmounts, dropped_scale, numbers_note, speak_text
from .stage_gen import MOVES as STAGE_MOVES
from .stage_gen import SPEC, ReadRequest

MODEL = "gpt-6.1-terra"
REASONING = "medium"


class LanguageRequested(AppEvent):
    """The visitor pressed the other language on the EN / हिंदी toggle mid-call."""

    language: str


_EVENTS = AppEvents(StageResult, StageHello, StageProgress, StageEvent, LanguageRequested)

#: The quiet spell before the agent may speak up by itself, and how short it
#: gets while it has a line to say (a booking's outcome, a visitor's booking).
_IDLE_MS = 15000
_SAY_NOW_MS = 400
_REACT_IDLE_MS = 1500

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

Job = Literal["sdr", "pricing", "booker"]
JOB_NAMES: dict[Job, str] = {
    "sdr": "sales rep: qualify them, fill the lead card, show the modules that fit",
    "pricing": "pricing: work out their plan and price on the calculator",
    "booker": "demo booking: find a slot on the sales calendar and book it after their yes",
}

for _table in (*LANDED.values(), *GREETING.values(), *BOOKING.values(), TOGGLE_CONFIRM):
    assert set(PERSONA.languages) <= set(_table), "a persona language has no written line"


class LanguageChanged(Action):
    """The call's language moved: the page's EN / हिंदी toggle follows."""

    language: str


# ─── Tool parameters ──────────────────────────────────────────────────────────


class LeadUpdate(BaseModel):
    """What the visitor just told you. Only what is new; the rest stays on the card."""

    company: str | None = Field(default=None, description="Their company's name.")
    name: str | None = Field(default=None, description="Their name.")
    headcount: int | None = Field(default=None, description="How many employees they pay.")
    states: list[str] | None = Field(
        default=None, description="Every Indian state they have employees in, by name."
    )
    current_tool: Literal["spreadsheets", "ca_accountant", "other_software", "in_house"] | None = (
        Field(default=None, description="How they run payroll today.")
    )
    pains: list[str] | None = Field(
        default=None,
        description=(
            "Every pain they have mentioned so far, by id: payroll_errors, tax_proofs, "
            "statutory, leave, reimbursements, payslip_queries, multi_entity, integrations."
        ),
    )
    email: str | None = Field(default=None, description="Their work email, as they spelled it.")
    email_confirmed: bool = Field(
        default=False, description="True only after you read the email back and they said yes."
    )


class ModulesRequest(BaseModel):
    ids: list[str] = Field(description="Module ids to mark as a fit, in order.")


class PageRequest(BaseModel):
    page: str = Field(
        description="/, /modules, /modules/<module id>, /tax, /customers, /pricing or /book-demo."
    )


class PriceRequest(BaseModel):
    headcount: int = Field(description="Employees on payroll.")
    modules: list[str] = Field(
        default_factory=list[str],
        description="Extra modules they need: reimbursements, declarations, multi_entity, api.",
    )
    billing: Literal["monthly", "annual"] = "monthly"
    filing: bool = Field(default=False, description="The statutory filing service add-on.")


class SlotsRequest(BaseModel):
    day: str | None = Field(
        default=None,
        description="YYYY-MM-DD, a weekday name (thursday), or tomorrow. Empty: the whole calendar.",
    )
    part: Literal["morning", "afternoon", "evening", "any"] = "any"


class HoldRequest(BaseModel):
    slot_id: str = Field(description="A free slot id from demo_slots, 2026-11-19-1030-kavya.")
    name: str = Field(description="The visitor's name.")
    company: str = Field(description="Their company.")
    email: str | None = Field(default=None, description="Their work email.")
    email_confirmed: bool = Field(
        default=False, description="True only after you read the email back and they said yes."
    )
    headcount: int | None = None
    topic: Literal["walkthrough", "migration", "compliance", "pricing"] = "walkthrough"


class ConfirmRequest(BaseModel):
    visitor_said_yes: bool = Field(description="True only when they just said yes to the booking.")


class LanguageRequest(BaseModel):
    language: Literal["english", "hindi"]


# ─── State ────────────────────────────────────────────────────────────────────


@dataclass
class Held:
    slot: cal.Slot
    name: str
    company: str
    email: str
    turn: int


def _yes_no(text: str) -> Literal["yes", "no"] | None:
    t = " " + re.sub(r"[^\wऀ-ॿ ]", " ", text.lower()) + " "
    if any(f" {w} " in t for w in NO_WORDS):
        return "no"
    if any(f" {w} " in t for w in YES_WORDS):
        return "yes"
    return None


def canonical(path: str) -> str:
    """The route under the app's base, without query or trailing slash."""
    p = path.split("?", 1)[0].split("#", 1)[0]
    p = re.sub(r"^/demos/payroll_site", "", p) or "/"
    return p.rstrip("/") or "/"


def job_of(path: str) -> Job:
    if path.startswith("/pricing"):
        return "pricing"
    if path.startswith("/book-demo"):
        return "booker"
    return "sdr"


def page_title(path: str) -> str:
    if path.startswith("/modules/") and (m := MODULES.get(path.split("/")[2])):
        return f"the {m['name']} module page"
    return f"the {PAGES.get(path, path).lower()} page" if path != "/" else "the home page"


#: What a brain holds for one socket only: the session object and the speech
#: units waiting for the runtime to say what was heard. Everything else a call
#: built is carried to the brain a redial starts (rejoin.py).
_PER_SOCKET = frozenset({"_session", "_awaiting"})


class PaynoraSiteBrain(OpenAIBrain):
    """One per session: the job, the lead card, the calculator and the booking."""

    def __init__(
        self,
        *,
        client: AsyncOpenAI,
        model: str = MODEL,
        persona: Persona = PERSONA,
        today: date | None = None,
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
        self.job: Job = "sdr"
        self._today = today
        self.lead: dict[str, Any] = {
            "company": "",
            "name": "",
            "headcount": None,
            "states": [],
            "current_tool": "",
            "pains": [],
            "recommended_plan": "",
            "has_email": False,
        }
        self.matched: list[str] = []
        self.pricing: dict[str, Any] = {}
        self.booking: dict[str, Any] = {"status": "choosing"}
        self.booked: set[str] = set()
        self.held: Held | None = None
        self.turns = 0
        self._flights: dict[str, Held] = {}
        self._say_next: Callable[[], str] | None = None
        self._talk: str | None = None
        self.stage = Stage(
            dispatch=lambda a: self.session.dispatch(a),
            moves=STAGE_MOVES,
            resolve=self._resolve,
            mirror=Mirror(SPEC),
        )
        self._fallback = FallbackLine()
        #: This brain took over a call whose socket dropped (rejoin.py).
        self.rejoined = False
        #: The visitor's last few turns, as heard: what a headcount is checked against.
        self._heard_recent: list[str] = []
        #: Every amount spoken in the form the voice reads right (spoken.py, X8).
        self._spoken = SpokenAmounts(lambda: self.lang)

    @property
    def today(self) -> date:
        return self._today or cal.today_ist(datetime.now().astimezone())

    # ─── Session ────────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        """The job from the page the call started on and both legs in the
        toggle's language, before the greeting.

        A call outlives a dropped socket (CONTRACT.md, redial; SDK 0.15.0):
        redial is on wherever Voqalize offers it, and a brain started by a
        redial on a session this process still holds adopts that call as it
        was — the page, job and language it had moved to included — instead of
        starting over. Its greeting is not spoken."""
        prior = REJOIN.take(session.id)
        if prior is not None and prior is not self:
            self._adopt(prior)
            self.rejoined = True
        else:
            init = session.init or {}
            self.lang = self.persona.tag(str(init.get("lang") or init.get("language") or ""))
            self._at(canonical(str(init.get("page") or "/")))
        REJOIN.hold(session.id, self)
        await session.configure(
            Config(
                stt=SttConfig(language=self.lang, patience=PATIENCE),
                tts=TtsConfig(voice=self.persona.voices[self.lang], language=self.lang),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
                redial=RedialConfig(enabled=True) if session.can_redial else None,
            )
        )
        logger.info(
            "payroll_site: session {} on {} as {} in {}",
            "rejoined" if self.rejoined else "started",
            self.path,
            self.job,
            self.lang,
        )

    async def on_session_end(self, session: Session) -> None:
        """The socket closed: a hang-up, or a drop Voqalize may redial. Kept a
        short while for the redial; runs at least once, and a second run (or
        one on a brain a redial already replaced) changes nothing."""
        REJOIN.dropped(session.id, self)

    def _adopt(self, prior: PaynoraSiteBrain) -> None:
        """Take over ``prior``'s call: every piece of state but its socket's.
        ``prior`` then shares this brain's state, so whatever still points at
        it — the Stage director's dispatch, a line queued for the next quiet
        spell — acts on this call and this socket."""
        self.__dict__.update({k: v for k, v in prior.__dict__.items() if k not in _PER_SOCKET})
        prior.__dict__ = self.__dict__

    async def greet(self, session: Session) -> str | None:
        """Written, not generated: the job's opener in the call's language.
        None on a rejoined call: the visitor was greeted when it began."""
        if self.rejoined:
            return None
        return speak_text(GREETING[self.job][self.lang].format(name=self.persona.name), self.lang)

    def _at(self, path: str) -> bool:
        """The visitor is on ``path``; True when the job changed."""
        self.path = path
        job = job_of(path)
        changed = job != self.job
        self.job = job
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
        if (said := numbers_note(msg.text)) is not None:
            self.append_note(said)
        held = self.held
        if held is not None and held.turn < self.turns:
            answer = _yes_no(msg.text)
            if answer == "yes":
                line = self._confirm(held)
                async for speech in self.say_line(line, remember=True):
                    yield speech
                return
            if answer == "no":
                self.held = None
                self.append_note("[They did not confirm the demo; nothing was booked.]")
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
        return self._spoken.wrap(self._idle(session))

    async def _idle(self, session: Session) -> AsyncGenerator[Speech, None]:
        """A quiet spell: a line the brain owes (a booking's outcome, a language
        switch) or the page asked for (the visitor booked by hand); else quiet."""
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
        """The page, the job and what is on screen, in front of what the visitor says."""
        parts = [
            f"[Screen: {page_title(self.path)} ({self.path}). Your job: {JOB_NAMES[self.job]}.]"
        ]
        filled = self._lead_line()
        if filled:
            parts.append(f"[Lead card: {filled}.]")
        if self.job == "pricing" and self.pricing:
            p = self.pricing
            parts.append(
                f"[Calculator: {p.get('headcount')} employees, modules "
                f"{', '.join(p.get('modules') or []) or 'core only'}, {p.get('billing')} billing, "
                f"filing {'on' if p.get('filing') else 'off'}: {p.get('plan')}, "
                f"₹{p.get('monthly')} a month before GST.]"
            )
        if self.job == "booker":
            b = self.booking
            line = f"[Calendar: today is {cal.day_label(self.today)} IST"
            if b.get("day"):
                line += f"; showing {b['day']}"
            if b.get("slot_id"):
                line += f"; slot picked {b['slot_id']}"
            if b.get("reference"):
                line += f"; booked, reference {b['reference']}"
            parts.append(line + ".]")
        if self.held is not None:
            parts.append(f"[Waiting for their yes to confirm {self.held.slot.id}.]")
        parts.append(f"[Language: {self.persona.language_names[self.lang]}]")
        return " ".join(parts)

    def _lead_line(self) -> str:
        lead = self.lead
        bits: list[str] = []
        for key in ("company", "name", "headcount", "current_tool", "recommended_plan"):
            if lead.get(key):
                bits.append(f"{key} {lead[key]}")
        for key in ("states", "pains"):
            if lead.get(key):
                bits.append(f"{key} {', '.join(lead[key])}")
        if lead.get("has_email"):
            bits.append("email given")
        return "; ".join(bits)

    # ─── Stage ──────────────────────────────────────────────────────────

    def _resolve(self, move: Move, args: list[str]) -> list[str] | None:
        """A ``{module: …}`` cue names a module that exists, or is dropped."""
        if move.id == "modules.show" and args:
            want = args[0].strip().lower().replace(" ", "_")
            if want in MODULES:
                return [want]
            by_name = {m["name"]: k for k, m in MODULES.items()}
            hit = match_label(args[0], list(by_name))
            return [by_name[hit]] if hit else None
        return args

    def _send(self, move: str, args: dict[str, Any], landed_key: str | None = None) -> None:
        """Send a move now. The page makes its moves one at a time, in the order
        sent, so several fills from one tool land field by field; the director's
        own queue would keep only the newest of a kind."""
        self.stage.send(move, args, queue=False)
        if landed_key is not None:
            landed(*LANDED[landed_key][self.lang])

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        event = _EVENTS.parse(msg)
        if event is None:
            return
        if isinstance(event, LanguageRequested):
            await self.switch_from_toggle(session, event.language)
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
            logger.info("payroll_site: {}", note)
            self.append_note(note)

    def _event(self, event: StageEvent) -> str | None:
        """Fold what the page reports into the brain's state; the line the model reads."""
        folded = self.stage.handle(event)
        data = event.data
        visitor = event.by == "visitor"
        match event.name:
            case "screen.viewed":
                if self._at(canonical(str(data.get("path") or "/"))):
                    return f"[They are now on {page_title(self.path)}: your job here is {JOB_NAMES[self.job]}.]"
                return None
            case "lead.changed":
                for key in ("company", "name", "headcount", "current_tool", "recommended_plan"):
                    if key in data:
                        self.lead[key] = data[key]
                for key in ("states", "pains"):
                    if key in data:
                        self.lead[key] = list(data[key] or [])
                if "has_email" in data:
                    self.lead["has_email"] = bool(data["has_email"])
                if "modules" in data:
                    self.matched = [str(m) for m in data["modules"] or []]
            case "pricing.changed":
                self.pricing = dict(data)
            case "booking.changed" | "booking.confirmed":
                self.booking.update(data)
                if ref := data.get("reference"):
                    if self.booking.get("slot_id"):
                        self.booked.add(str(self.booking["slot_id"]))
                    if visitor:
                        self.held = None
                        if ask := self.stage.take_reaction():
                            self._talk = ask
                            configure_soon(
                                self.session, Config(idle=IdleConfig(timeout_ms=_REACT_IDLE_MS))
                            )
                    logger.info("payroll_site: booked {}", ref)
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
        held = self._flights.pop(result.call_ref, None)
        why = "; ".join(
            r.why + (f" (options: {', '.join(r.options)})" if r.options else "")
            for r in result.refused
        )
        if held is not None:
            if result.outcome in ("applied", "partial"):
                ref = cal.reference(held.slot)
                self.booked.add(held.slot.id)
                self.booking.update(status="confirmed", reference=ref, slot_id=held.slot.id)
                self._say_soon(lambda: self._booked_line(held))
                return f"[The demo is booked: {held.slot.id}, reference {ref}. Do not book again.]"
            reason = result.detail or why or result.outcome
            self._say_soon(lambda: BOOKING["failed"][self.lang].format(why=reason))
            return (
                f"[The booking did not go through: {reason}. Offer to fix it or pick another slot.]"
            )
        if result.moved or result.outcome in ("applied", "partial", "undone"):
            return None
        return (
            f"[Your {result.move} move did not land ({result.detail or result.outcome}"
            + (f"; {why}" if why else "")
            + "). Never say it did.]"
        )

    def _when(self, slot: cal.Slot) -> str:
        """The slot as said in the call's language (round 2, R8: a Hindi call
        heard "Wednesday 25 November at 9:30 am" inside its booking line)."""
        if self.lang == "hi":
            return f"{cal.spoken_day_hi(slot.day)}, {cal.spoken_time_hi(slot.time)}"
        return f"{cal.spoken_day(slot.day)} at {cal.spoken_time(slot.time)}"

    def _booked_line(self, held: Held) -> str:
        return BOOKING["booked"][self.lang].format(
            when=self._when(held.slot),
            rep=held.slot.rep_name.split()[0],
            reference=cal.reference(held.slot),
        )

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        return [
            self.update_lead,
            self.mark_modules,
            self.open_page,
            self.price_plan,
            self.demo_slots,
            self.hold_slot,
            self.confirm_booking,
            self.set_language,
            self.read_screen,
        ]

    @needs_result_now
    async def update_lead(self, request: LeadUpdate) -> str:
        """Put what the visitor told you on the lead card: each field fills on
        screen in turn, the modules that fit their pains are marked, and the
        suggested plan follows. Pass only what is new."""
        notes: list[str] = []
        changes: list[tuple[str, dict[str, Any]]] = []
        lead = self.lead
        if request.company and request.company.strip() != lead["company"]:
            lead["company"] = request.company.strip()
            changes.append(("company", {"value": lead["company"]}))
        if request.name and request.name.strip() != lead["name"]:
            lead["name"] = request.name.strip()
            changes.append(("name", {"value": lead["name"]}))
        if request.headcount is not None:
            if (wrong := dropped_scale(request.headcount, self._heard_recent[::-1])) is not None:
                notes.append(wrong.replace("Not done:", "Headcount not added:", 1))
            elif request.headcount <= 0:
                notes.append("A headcount must be a positive number.")
            elif request.headcount != lead["headcount"]:
                lead["headcount"] = request.headcount
                changes.append(("headcount", {"value": str(request.headcount)}))
        if request.states:
            picked = [m for m in (match_label(s, STATES) for s in request.states) if m]
            if len(picked) < len(request.states):
                notes.append(f"States the card knows: {', '.join(STATES)}.")
            merged = list(dict.fromkeys([*lead["states"], *picked]))
            if merged != lead["states"]:
                lead["states"] = merged
                changes.append(("states", {"items": merged}))
        if request.current_tool and request.current_tool != lead["current_tool"]:
            lead["current_tool"] = request.current_tool
            changes.append(("current_tool", {"value": request.current_tool}))
        pains_changed = False
        if request.pains:
            labels = {p["label"]: k for k, p in PAINS.items()}
            ids: list[str] = []
            for p in request.pains:
                key = p.strip().lower()
                hit = key if key in PAINS else labels.get(match_label(p, list(labels)) or "")
                if hit:
                    ids.append(hit)
                else:
                    notes.append(f"Unknown pain {p!r}; pains are {', '.join(PAINS)}.")
            merged = list(dict.fromkeys([*lead["pains"], *ids]))
            if merged != lead["pains"]:
                lead["pains"] = merged
                pains_changed = True
                changes.append(("pains", {"items": merged}))
        if request.email:
            email = request.email.strip().lower().replace(" at ", "@").replace(" dot ", ".")
            if not _EMAIL.match(email):
                notes.append(f"{request.email!r} is not an email address; ask them to spell it.")
            elif not request.email_confirmed:
                notes.append(
                    f"Email not added: read {email} back to them and add it once they say yes."
                )
            else:
                lead["has_email"] = True
                changes.append(("email", {"value": email}))
        modules = self._pain_modules()
        plan_id, why = (None, [])
        if lead["headcount"]:
            plan_id, why = choose_plan(lead["headcount"], modules, False)
            if plan_id and plan_id != lead["recommended_plan"]:
                lead["recommended_plan"] = plan_id
                changes.append(("recommended_plan", {"value": plan_id}))
        for field, args in changes:
            self._send("lead.fill", {"field": field, **args})
        if pains_changed and modules:
            self.matched = modules
            self._send("modules.highlight", {"ids": modules})
        if changes:
            landed(*LANDED["lead"][self.lang])
        empty = [
            LEAD["labels"][f].lower()
            for f in ("company", "name", "headcount", "states", "current_tool", "pains")
            if not lead[f]
        ]
        out = [f"Lead card: {self._lead_line() or 'empty'}."]
        if modules:
            out.append(
                "Modules that fit, marked on screen: "
                + ", ".join(f"{MODULES[m]['name']} ({m})" for m in modules)
                + "."
            )
        if plan_id:
            reasons = f" because {'; '.join(why)}" if why else ""
            out.append(f"Suggested plan: {PLANS[plan_id]['name']}{reasons}.")
        elif lead["headcount"] and lead["headcount"] > 1000:
            out.append("Above 1,000 employees: a custom price; offer a demo.")
        if empty:
            out.append(f"Still empty: {', '.join(empty)}.")
        return " ".join(out + notes)

    def _pain_modules(self) -> list[str]:
        return list(dict.fromkeys(m for p in self.lead["pains"] for m in PAINS[p]["modules"]))

    async def mark_modules(self, request: ModulesRequest) -> str:
        """Mark module cards as a fit for them (replaces the marked set)."""
        ids = [i for i in (x.strip().lower() for x in request.ids) if i in MODULES]
        if not ids:
            return f"No such modules. Modules: {', '.join(MODULES)}."
        self.matched = ids
        self._send("modules.highlight", {"ids": ids}, "modules")
        return f"marked {', '.join(ids)}"

    async def open_page(self, request: PageRequest) -> str:
        """Open another page of the site."""
        page = canonical(request.page if request.page.startswith("/") else f"/{request.page}")
        ok = page in PAGES or (page.startswith("/modules/") and page.split("/")[2] in MODULES)
        if not ok:
            return f"Not a page here. Pages: {', '.join(PAGES)}, /modules/<module id>."
        self._send("site.go", {"path": page}, "open")
        return f"opening {page}"

    @needs_result_now
    async def price_plan(self, request: PriceRequest) -> str:
        """Work out their plan and price: sets the pricing calculator on screen
        control by control (opening the pricing page if needed) and gives you
        every line of the maths."""
        if request.headcount <= 0:
            return "Ask for their headcount first."
        if (wrong := dropped_scale(request.headcount, self._heard_recent[::-1])) is not None:
            return wrong
        unknown = [m for m in request.modules if m not in MODULES]
        q = quote(request.headcount, request.modules, request.billing, request.filing)
        extra = [m for m in q.modules if MODULES[m]["min_plan"] != "starter"]
        self._send(
            "pricing.set",
            {
                "headcount": request.headcount,
                "modules": extra,
                "billing": request.billing,
                "filing": request.filing,
            },
            "pricing",
        )
        self.pricing = {
            "headcount": request.headcount,
            "modules": extra,
            "billing": request.billing,
            "filing": request.filing,
            "plan": q.plan,
            "monthly": q.monthly,
        }
        out = spoken(q)
        if unknown:
            out += f" Unknown modules ignored: {', '.join(unknown)}."
        return out

    def _day(self, text: str | None) -> date | None | Literal["closed"]:
        if not text:
            return None
        days = cal.business_days(self.today)
        t = text.strip().lower()
        if t == "tomorrow":
            t = date.fromordinal(self.today.toordinal() + 1).isoformat()
        for d in days:
            if t in (d.isoformat(), d.strftime("%A").lower(), d.strftime("%a").lower()):
                return d
            if t in (f"{d.day} {d.strftime('%B').lower()}", f"{d.strftime('%B').lower()} {d.day}"):
                return d
        return "closed"

    def _free(self, day: date, part: str = "any") -> list[cal.Slot]:
        return [
            s
            for s in cal.slots_on(day)
            if not s.taken
            and s.id not in self.booked
            and (part == "any" or cal.part_of(s.time) == part)
        ]

    @needs_result_now
    async def demo_slots(self, request: SlotsRequest) -> str:
        """The free 30-minute demo slots, in IST. With a day, shows that day on
        the calendar (opening the booking page if needed) and lists its slots."""
        days = cal.business_days(self.today)
        day = self._day(request.day)
        if day == "closed":
            return (
                "Demos are on business days only. The calendar has: "
                + ", ".join(cal.spoken_day(d) for d in days)
                + ". Ask which of these."
            )
        if day is None:
            week = [
                f"{cal.spoken_day(d)} ({d.isoformat()}): {len(self._free(d, request.part))} free"
                for d in days
            ]
            return "Free demo slots, " + request.part + ": " + "; ".join(week) + ". Ask which day."
        self._send("calendar.show", {"day": day.isoformat()}, "calendar")
        free = self._free(day, request.part)
        if not free:
            other = [cal.spoken_time(s.time) for s in self._free(day)][:4]
            return (
                f"No free {request.part} slots on {cal.spoken_day(day)}. Other free times that "
                f"day: {', '.join(other) or 'none'}."
            )
        slots = "; ".join(f"{cal.spoken_time(s.time)} with {s.rep_name} ({s.id})" for s in free[:6])
        return f"Free on {cal.spoken_day(day)} ({request.part}), IST: {slots}. Each demo is 30 minutes."

    @needs_result_now
    async def hold_slot(self, request: HoldRequest) -> str:
        """Pick one free slot on the calendar and fill the booking form, before
        they confirm. Then ask them to confirm in plain words; their yes books it."""
        slot = cal.parse_slot(request.slot_id)
        if slot is None or slot.day not in cal.business_days(self.today):
            return f"{request.slot_id} is not a slot on the calendar. Call demo_slots for the day."
        if slot.taken or slot.id in self.booked:
            return f"{slot.id} is taken. Offer a free one from demo_slots."
        name, company = request.name.strip(), request.company.strip()
        if not name or not company:
            return "Ask for their name and company first."
        email = ""
        note = ""
        if request.email:
            e = request.email.strip().lower()
            if not _EMAIL.match(e):
                note = f" {request.email!r} is not an email address; ask them to spell it."
            elif not request.email_confirmed:
                note = f" Email not filled: read {e} back and hold again once they say yes."
            else:
                email = e
        if not email and not note:
            note = (
                " The form still needs their work email: ask for it, read it back, then hold again."
            )
        self._send("booking.pick", {"slot_id": slot.id}, "pick")
        fields: list[tuple[str, str]] = [("name", name), ("company", company)]
        if request.headcount:
            fields.append(("headcount", str(request.headcount)))
        fields.append(("topic", request.topic))
        if email:
            fields.append(("email", email))
        for field, value in fields:
            self._send("booking.fill", {"field": field, "value": value})
        self.held = Held(slot, name, company, email, self.turns) if email else None
        when = self._when(slot)
        rep = slot.rep_name.split()[0]
        if not email:
            return f"Picked {when} with {slot.rep_name}, form filled for {name} at {company}.{note}"
        return (
            f"Held: {when} IST with {slot.rep_name}, for {name} at {company}, {email}, topic "
            f"{TOPICS[request.topic]}. Ask them to confirm, e.g. "
            f'"{BOOKING["ask"][self.lang].format(when=when, rep=rep)}" Nothing is booked until '
            "they say yes."
        )

    async def confirm_booking(self, request: ConfirmRequest) -> str:
        """Confirm the held demo. Only after the visitor just said yes to it."""
        if self.held is None:
            return "Nothing is held. Pick a free slot with hold_slot first."
        if not request.visitor_said_yes or self.held.turn >= self.turns:
            return "Not booked: ask them to confirm first and wait for their yes."
        line = self._confirm(self.held)
        landed(line)
        return "confirming; the page answers with the confirmation"

    def _confirm(self, held: Held) -> str:
        """Press Confirm booking on the page; the line said while it goes."""
        self.held = None
        ref = self.stage.send("booking.confirm", {}, queue=False)
        self._flights[ref] = held
        self.append_note(
            f"[They said yes: confirming {held.slot.id} for {held.name}. The page answers; "
            "do not confirm again.]"
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
        logger.info("payroll_site: language -> {}", tag)
        return Config(
            stt=SttConfig(language=tag, patience=PATIENCE),
            tts=TtsConfig(voice=self.persona.voices[tag], language=tag),
        )

    async def switch_from_toggle(self, session: Session, tag: str) -> None:
        """The visitor pressed the other language on the toggle mid-call."""
        tag = self.persona.tag(tag)
        if tag == self.lang:
            return
        await session.configure(self._speaking(tag))
        self._say_soon(lambda: TOGGLE_CONFIRM[self.lang])
        self.append_note(
            f"[The call is now in {self.persona.language_names[tag]}, switched on the toggle.]"
        )

    @needs_result_now
    async def read_screen(self, request: ReadRequest) -> str:
        """Read part of their screen as the page last reported it."""
        mirror = self.stage.mirror
        return mirror.read(request.slice) if mirror is not None else "nothing reported"


#: Live calls by session id, for a redial to rejoin (rejoin.py).
REJOIN: Rejoin[PaynoraSiteBrain] = Rejoin()


__all__ = [
    "REJOIN",
    "LanguageChanged",
    "LanguageRequested",
    "PaynoraSiteBrain",
    "canonical",
    "job_of",
]
