"""DentalBrain: the front desk of Dantika Dental Studio.

An :class:`~voqalize.sdk.openai.OpenAIBrain`. One brain serves the three landing
pages; the page the call starts on (``init.landing``) and the page in front
(``page_viewed``) set the job: answering on the clinic site, booking on
``/book``, changing appointments on ``/my-appointments``.

**Every move on the screen is a Stage move** (``frontend/src/stage/scene.json``):
the tools compute, then send one move each with ``stage.send(..., queue=False)``
and return at once; the page rings what it touches before it acts and answers
with one result. Cues in the agent's words (``{go: book}``, ``{show: parking}``)
ride the same director.

**Facts come from the data** (:mod:`.clinic`): slots are computed from the
dentists' schedules, the chairs and imaging rooms, and every booking on the
calendar, laid over with what this browser changed (``schedule_changed``). The
rules (CBCT referral, OPG before wisdom-tooth surgery, root-canal sittings) and
the cancellation terms are checked here, in code, against the patient's record.

**What is marked ``@needs_result_now``**: the reads the model must answer from:
clinic_info, find_slots, hold_slot, send_code, verify_code, my_appointments,
propose_change. Everything else is an act whose line is said with the call.

**A booking or a change needs a spoken yes.** confirm_booking and
confirm_change are refused unless the patient's last words were a yes (or they
pressed Confirm themselves), whatever the model believes.

**Clinical questions go to a dentist.** A note in front of any message that
sounds clinical keeps the model on the callback path; nothing here advises.
"""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from typing import Any, Literal

from loguru import logger
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from voqalize_demos import PATIENCE, FallbackLine, configure_soon, landed

from voqalize.sdk import (
    RTVIMessage,
    Session,
    Speech,
    UserIdle,
    UserMessage,
)
from voqalize.sdk.openai import OpenAIBrain, needs_result_now
from voqalize.sdk.stage import Stage
from voqalize.sdk.stage.wire import StagePageEvents, StageResult
from voqalize.sdk.wire import Config, IdleConfig, SttConfig, TtsConfig

from . import clinic as cl
from .app_events import (
    DENTAL_EVENTS,
    AppointmentChanged,
    AppointmentIn,
    Booked,
    CallbackRequested,
    LanguageChanged,
    LanguageRequested,
    PageViewed,
    PatientSignedIn,
    PatientSignedOut,
    ScheduleChanged,
    SelectionChanged,
)
from .clinic import Appt, Calendar, Patient, Service, Slot
from .persona import PERSONA, Lang
from .prompt import LANDINGS, LINES, greeting, system_instruction
from .stage_gen import MOVES

#: GPT-6.1 Terra at medium reasoning: the repo's rule for a new demo (at low,
#: a model skipped screen moves it had just promised).
MODEL = "gpt-6.1-terra"
REASONING = "medium"

_IDLE_MS = 15000
#: A line the brain already knows (a refusal the page sent after the turn):
#: said as soon as the voice is free.
_SAY_NOW_MS = 400

#: The first booking and callback numbers this brain mints in a session.
_FIRST_BOOKING = 24117
_FIRST_CALLBACK = 3107

Page = Literal["home", "book", "my-appointments"]
Topic = Literal[
    "prices",
    "eating",
    "aftercare",
    "payment",
    "insurance",
    "parking",
    "address",
    "hours",
    "what_to_bring",
    "late_arrival",
    "children",
    "sunday",
    "cancellation",
    "dentists",
    "emergency",
]
PartOfDay = Literal["morning", "afternoon", "evening"]

#: Which part of the home page each topic rings.
_THING: dict[str, str] = {
    "prices": "services",
    "eating": "eating",
    "aftercare": "aftercare",
    "payment": "payment",
    "insurance": "insurance",
    "parking": "parking",
    "address": "branches",
    "hours": "hours",
    "what_to_bring": "visit-info",
    "late_arrival": "visit-info",
    "children": "visit-info",
    "sunday": "emergency",
    "cancellation": "policy",
    "dentists": "dentists",
    "emergency": "emergency",
}

_YES = re.compile(
    r"\b(yes|yeah|yep|yup|sure|ok|okay|confirm|go ahead|please do|book it|do it|correct|right|"
    r"perfect|fine|haan|haa|han|ji|theek hai|thik hai|kar do|kardo|kar dijiye|kijiye|bilkul|zaroor)\b"
    r"|हाँ|हां|जी|ठीक है|कर दो|कर दीजिए|कीजिए|बिल्कुल|ज़रूर|जरूर"
)
_NO = re.compile(
    r"\b(no|nope|not|don't|dont|wait|hold on|cancel that|nahi|nahin|mat|ruko)\b|नहीं|मत|रुको|रुकिए"
)
_CLINICAL = re.compile(
    r"\b(bleed\w*|blood|swell\w*|swollen|fever|pus|antibiotic\w*|painkiller\w*|medicine\w*|"
    r"medication\w*|tablet\w*|dose|dosage|paracetamol|ibuprofen|pregnan\w*|blood thinner\w*|"
    r"diabet\w*|infection|khoon|sujan|soojan|bukhar|dawai|dawa|goli)\b"
    r"|खून|सूजन|बुखार|दवा|दवाई|गोली"
)
_HINDI_SCRIPT = re.compile(r"[ऀ-ॿ]")


def affirmed(text: str) -> bool:
    """A clear yes, with no no in it."""
    t = text.casefold()
    return bool(_YES.search(t)) and not _NO.search(t)


def clinical(text: str) -> bool:
    return bool(_CLINICAL.search(text.casefold()))


# ─── Tool parameters (declared flat to the model) ─────────────────────────────


class GoTo(BaseModel):
    page: Page = Field(description="home, book or my-appointments")


class InfoRequest(BaseModel):
    topic: Topic = Field(description="What they asked about.")
    service: str | None = Field(
        default=None, description="A service id or name, for eating/aftercare/prices."
    )
    branch: str | None = Field(default=None, description="indiranagar or hsr, for parking/address.")


class SlotSearch(BaseModel):
    service: str = Field(
        description="Service id (consult, checkup, emergency, scaling, …) or name."
    )
    branch: str | None = Field(default=None, description="indiranagar or hsr, if they care.")
    dentist: str | None = Field(
        default=None, description="Dentist id or name, if they asked for one."
    )
    date: str | None = Field(
        default=None,
        description="YYYY-MM-DD, 'today', 'tomorrow' or a weekday; empty for the next days with room.",
    )
    part_of_day: PartOfDay | None = Field(default=None, description="If they said a time of day.")


class HoldRequest(BaseModel):
    service: str = Field(description="Service id.")
    date: str = Field(description="YYYY-MM-DD, as find_slots gave it.")
    time: str = Field(description="HH:MM, 24-hour, as find_slots gave it.")
    dentist: str | None = Field(default=None, description="Dentist id, as find_slots gave it.")
    branch: str | None = Field(default=None, description="Branch id, as find_slots gave it.")


class PhoneRequest(BaseModel):
    phone: str = Field(description="The mobile number as the patient said it, digits only.")


class CodeRequest(BaseModel):
    code: str = Field(description="The four digits the patient read out.")


class NameRequest(BaseModel):
    name: str = Field(description="The new patient's full name.")


class ChangeRequest(BaseModel):
    appointment_id: str = Field(description="DT-24051, from my_appointments.")
    action: Literal["reschedule", "cancel"]
    date: str | None = Field(default=None, description="New day for a reschedule: YYYY-MM-DD.")
    time: str | None = Field(default=None, description="New time for a reschedule: HH:MM.")


class CallbackRequest(BaseModel):
    reason: str = Field(description="One short line for the dentist, in English.")
    urgency: Literal["urgent", "today", "routine"]
    phone: str | None = Field(default=None, description="A number to call, if not verified yet.")


class LanguageRequest(BaseModel):
    language: Lang = Field(description="en or hi")


# ─── What the desk is holding ─────────────────────────────────────────────────


@dataclass
class Hold:
    svc: Service
    slot: Slot
    sittings: list[Slot] = field(default_factory=list[Slot])


@dataclass
class Pending:
    appt: Appt
    action: Literal["reschedule", "cancel"]
    fee: int
    slot: Slot | None = None


def _iso(d: date) -> str:
    return d.isoformat()


def _slot_line(s: Slot, today: date) -> str:
    who = cl.who(s.dentist)
    b = cl.branch(s.branch)
    return f"{cl.spoken_time(s.time)} ({s.time}, {who}, {b.short if b else s.branch})"


def _in_part(s: Slot, part: PartOfDay | None) -> bool:
    if part is None:
        return True
    if part == "morning":
        return s.start < 12 * 60
    if part == "afternoon":
        return 12 * 60 <= s.start < 16 * 60
    return s.start >= 16 * 60


def _sitting_arg(s: Slot) -> str:
    return f"{_iso(s.on)} {s.time} {s.branch} {s.chair or ''}".strip()


class DentalBrain(OpenAIBrain):
    """One per call: the calendar, the patient, the slot held and the change pending."""

    def __init__(self, *, client: AsyncOpenAI, model: str = MODEL) -> None:
        super().__init__(
            client=client,
            system_instruction=system_instruction(),
            model=model,
            reasoning=REASONING,
        )
        self.lang: Lang = PERSONA.default_language
        self.page: Page = "home"
        self.cal = Calendar.build(cl.now_ist())
        self.patient: Patient | None = None
        self.phone: str | None = None  # the number a code was sent to
        self.code_ok = False  # the code matched; a new number still needs a name
        self.hold: Hold | None = None
        self.pending: Pending | None = None
        self.heard = ""  # what the patient said last
        self.confirm_pressed = False  # the visitor pressed Confirm by hand
        self._next_booking = _FIRST_BOOKING
        self._next_callback = _FIRST_CALLBACK
        # Brain-made changes waiting for the page's answer: call_ref → undo.
        self._undo: dict[str, list[Appt | str]] = {}
        self._say_next: str | None = None
        self._new_name: str | None = None
        self._fallback = FallbackLine()
        self.stage = Stage(dispatch=lambda a: self.session.dispatch(a), moves=MOVES)

    # ─── Session ────────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        """Both legs in the page's chosen language, before the greeting."""
        init: dict[str, Any] = dict(session.init or {})
        self.lang = PERSONA.pick(init.get("lang"))
        landing = str(init.get("landing") or "home")
        self.page = landing if landing in LANDINGS else "home"  # type: ignore[assignment]
        self.cal = Calendar.build(cl.now_ist())
        await session.configure(self._speaking(self.lang, idle=True))
        logger.info("dental: session start on {} in {}", self.page, self.lang)
        now = self.cal.now
        self.append_note(
            f"[Now: {now:%A} {now.day} {now:%B} {now.year}, {cl.spoken_time(f'{now:%H:%M}')} in Bengaluru. "
            f"The call is in {self._lang_name(self.lang)}. {self._page_note()}]"
        )

    def _speaking(self, lang: Lang, *, idle: bool = False) -> Config:
        return Config(
            stt=SttConfig(language=lang, patience=PATIENCE),
            tts=TtsConfig(voice=PERSONA.voice(lang), language=lang),
            idle=IdleConfig(timeout_ms=_IDLE_MS) if idle else None,
        )

    @staticmethod
    def _lang_name(lang: Lang) -> str:
        return {"en": "English", "hi": "Hindi"}[lang]

    async def greet(self, session: Session) -> str:
        """Written, per language and landing page: no model call."""
        return greeting(self.lang, self.page)

    def _line(self, key: str, **kw: str) -> str:
        return LINES[self.lang][key].format(**kw)

    def _page_note(self) -> str:
        jobs = {
            "home": "The visitor is on the clinic's home page: answer questions, and book if they want.",
            "book": "The visitor is on the booking page: help them book.",
            "my-appointments": "The visitor is on My appointments: verify them, then reschedule or cancel.",
        }
        return jobs[self.page]

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[Speech, None]:
        self.heard = msg.text
        self.confirm_pressed = False
        self.stage.visitor_spoke()
        self._settle_expired()
        self.cal.now = cl.now_ist()
        self.append_note(self._state_note())
        if clinical(msg.text):
            self.append_note(
                "[This sounds clinical. Do not advise or name any medicine. Say a dentist should "
                "answer it and offer a callback (request_callback); for the red-flag signs, say "
                "the red-flag line first.]"
            )
        if self.lang == "en" and _HINDI_SCRIPT.search(msg.text):
            self.append_note(
                "[They spoke Hindi: offer to continue in Hindi, or call set_language.]"
            )
        async for speech in super().on_user_message(session, msg):
            yield speech

    def _state_note(self) -> str:
        bits = [f"page: {self.page}"]
        if self.patient is not None:
            bits.append(f"verified patient: {self.patient.name} ({self.patient.id})")
        elif self.code_ok:
            bits.append("number verified, new patient: name still needed")
        elif self.phone:
            bits.append(f"code sent to {self.phone}, not verified yet")
        else:
            bits.append("patient not verified")
        if self.hold is not None:
            h = self.hold
            bits.append(
                f"slot held: {h.svc.name} on {_iso(h.slot.on)} at {h.slot.time}"
                + (f" with {h.slot.dentist}" if h.slot.dentist else "")
            )
        if self.pending is not None:
            p = self.pending
            bits.append(f"change on screen: {p.action} {p.appt.id}")
        return "[Screen: " + "; ".join(bits) + "]"

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The model's turn with its cues made on the page, and a written line
        if it acted and said nothing."""
        turn = self.stage.cued(super().respond(session))
        async for event in self._fallback.speak_if_silent(self, turn):
            yield event
        self.stage.end_turn()

    def on_user_idle(self, session: Session, idle: UserIdle) -> AsyncGenerator[Speech, None]:
        return self._idle(session)

    async def _idle(self, session: Session) -> AsyncGenerator[Speech, None]:
        self._settle_expired()
        say, self._say_next = self._say_next, None
        if say is None:
            return
        configure_soon(session, Config(idle=IdleConfig(timeout_ms=_IDLE_MS)))
        async for event in self.say_line(say, remember=True):
            yield event

    def _say_soon(self, line: str) -> None:
        self._say_next = line
        configure_soon(self.session, Config(idle=IdleConfig(timeout_ms=_SAY_NOW_MS)))

    # ─── Page → brain ───────────────────────────────────────────────────

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        staged = StagePageEvents.parse(msg)
        if staged is not None:
            if isinstance(staged, StageResult):
                result = self.stage.handle(staged)
                if result is not None and (note := self._settle(result)) is not None:
                    self.append_note(note)
            else:
                self.stage.handle(staged)  # type: ignore[arg-type]
            return
        event = DENTAL_EVENTS.parse(msg)
        if event is None:
            return
        if isinstance(event, LanguageRequested):
            await self._switch(session, event.language, how="toggle")
            return
        note = self.apply_event(event)
        if note is not None:
            logger.info("dental: {}", note)
            self.append_note(note)

    def apply_event(self, event: object) -> str | None:
        """Fold one page event into the brain's picture; the line the model reads."""
        match event:
            case PageViewed():
                page = event.page if event.page in LANDINGS else "home"
                if page == self.page:
                    return None
                self.page = page  # type: ignore[assignment]
                return f"[{'They' if event.by == 'visitor' else 'You'} opened {page}. {self._page_note()}]"
            case ScheduleChanged():
                for a in event.appointments:
                    self.cal.put(self._appt_in(a))
                return None
            case PatientSignedIn():
                known = next((p for p in cl.DATA_.patients if p.id == event.patient_id), None)
                self.patient = known or Patient(
                    id=event.patient_id,
                    name=event.name,
                    phone=cl.normal_phone(event.phone),
                    age=0,
                    since=self.cal.today.year,
                )
                self.code_ok = True
                if event.by == "agent":
                    return None
                return f"[The patient signed in on screen themselves: {self.patient.name} ({self.patient.id}).]"
            case PatientSignedOut():
                self.patient = None
                self.code_ok = False
                self.phone = None
                return "[The patient signed out on screen.]"
            case SelectionChanged() if event.by == "visitor":
                picked = ", ".join(
                    f"{k} {v}"
                    for k, v in (
                        ("service", event.service_id),
                        ("branch", event.branch_id),
                        ("dentist", event.dentist_id),
                        ("date", event.date),
                        ("time", event.time),
                    )
                    if v
                )
                if event.time and event.date and event.service_id:
                    self._adopt_hold(event)
                return f"[They picked on screen: {picked}.]" if picked else None
            case Booked() if event.by == "visitor":
                self.hold = None
                return (
                    f"[They pressed Confirm themselves: {event.booking_id}, {event.service_id} on "
                    f"{event.date} at {event.time}. It is booked; do not book it again.]"
                )
            case AppointmentChanged() if event.by == "visitor":
                self.pending = None
                what = (
                    f"moved to {event.date} at {event.time}"
                    if event.action == "reschedule"
                    else "cancelled"
                )
                return f"[They {what} {event.appointment_id} themselves (fee ₹{event.fee}). It is done.]"
            case CallbackRequested() if event.by == "visitor":
                return f"[They asked for a callback themselves ({event.callback_id}, {event.urgency}).]"
            case _:
                return None

    def _appt_in(self, a: AppointmentIn) -> Appt:
        return Appt(
            id=a.id,
            service=a.service,
            branch=a.branch,
            on=date.fromisoformat(a.date),
            start=cl.minutes(a.time),
            duration_min=a.duration_min,
            dentist=a.dentist,
            chair=a.chair,
            resource=a.resource,
            patient_id=a.patient_id,
            sitting=a.sitting,
            changes=a.changes,
            status=a.status,
        )

    def _adopt_hold(self, event: SelectionChanged) -> None:
        """The visitor clicked a slot: it is the held one now."""
        svc = cl.service(event.service_id or "")
        if svc is None or not event.date or not event.time:
            return
        slot = self.cal.slot_at(
            svc,
            date.fromisoformat(event.date),
            event.time,
            branch_id=event.branch_id,
            dentist_id=event.dentist_id,
        )
        if slot is not None:
            self.hold = Hold(svc, slot, self.cal.plan_sittings(svc, slot))

    def _settle_expired(self) -> None:
        for result in self.stage.expire():
            if (note := self._settle(result)) is not None:
                self.append_note(note)

    def _settle(self, result: StageResult) -> str | None:
        """A move's answer: a refusal undoes what the brain assumed and is said."""
        undo = self._undo.pop(result.call_ref, None)
        if result.moved or result.outcome in ("applied", "partial", "undone"):
            if result.move == "patient.name" and result.detail:
                self._adopt_registration(result.detail)
            return None
        for item in undo or []:
            if isinstance(item, str):
                self.cal.appts.pop(item, None)
            else:
                self.cal.put(item)
        why = "; ".join(
            f"{r.arg}: {r.why}" + (f" (options: {', '.join(r.options)})" if r.options else "")
            for r in result.refused
        )
        detail = result.detail or why or result.outcome
        if undo is not None:
            self._say_soon(self._line("refused", why=detail))
        return (
            f"[Your {result.move} did not happen on screen ({result.outcome}: {detail}). "
            "Never say it did; tell them, and offer what fixes it.]"
        )

    def _adopt_registration(self, detail: str) -> None:
        m = re.search(r"P-\d+", detail)
        if m and self.patient is None and self.phone:
            self.patient = Patient(
                id=m.group(0),
                name=self._new_name or "",
                phone=self.phone,
                age=0,
                since=self.cal.today.year,
            )

    async def _switch(self, session: Session, lang: Lang, *, how: str) -> None:
        if lang == self.lang or lang not in PERSONA.codes:
            return
        await session.configure(self._speaking(lang))
        self.lang = lang
        session.dispatch(LanguageChanged(language=lang))
        self.append_note(
            f"[The visitor switched the call to {self._lang_name(lang)} on the {how}. "
            f"From now on speak {self._lang_name(lang)}.]"
        )

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        return [
            self.go_to,
            self.clinic_info,
            self.find_slots,
            self.hold_slot,
            self.send_code,
            self.verify_code,
            self.register_patient,
            self.confirm_booking,
            self.my_appointments,
            self.propose_change,
            self.confirm_change,
            self.request_callback,
            self.set_language,
        ]

    def _send(self, move: str, args: dict[str, Any]) -> str:
        clean = {k: v for k, v in args.items() if v is not None}
        return self.stage.send(move, clean, queue=False)

    async def go_to(self, request: GoTo) -> str:
        """Open one of the clinic's pages: home, book or my-appointments."""
        self._send("site.go", {"page": request.page})
        self.page = request.page
        landed(self._line("page"))
        return f"Opening {request.page}. {self._page_note()}"

    @needs_result_now
    async def clinic_info(self, request: InfoRequest) -> str:
        """The clinic's own answer on prices, eating before a visit, aftercare,
        payment, insurance, parking, address, hours, what to bring, running
        late, children, Sundays, the cancellation policy, dentists or
        emergencies. Rings the matching part of the home page."""
        ins = cl.DATA_.instructions
        svc = cl.find_service(request.service) if request.service else None
        b = cl.find_branch(request.branch) if request.branch else None
        topic = request.topic
        if topic == "eating":
            text = ins["eating"].by_service.get(svc.id, "") if svc else ins["eating"].general
            text = text or ins["eating"].general
        elif topic == "aftercare":
            if svc is None:
                text = "Aftercare depends on the treatment: ask which one."
            else:
                text = ins["aftercare"].by_service.get(svc.id) or (
                    f"No special aftercare is written down for {svc.name}."
                )
        elif topic == "prices":
            items = [svc] if svc else cl.DATA_.services
            text = "; ".join(f"{s.name}: {cl.price_text(s)}, {s.duration_min} min" for s in items)
        elif topic in ("parking", "address", "hours"):
            items = [b] if b else cl.DATA_.branches
            if topic == "parking":
                text = " ".join(f"{x.short}: {x.parking}" for x in items)
            elif topic == "address":
                text = " ".join(f"{x.name}: {x.address} ({x.landmark})." for x in items)
            else:
                text = " ".join(
                    f"{x.short}: Monday to Saturday, {cl.spoken_time(x.open)} to "
                    f"{cl.spoken_time(x.close)}; closed on Sunday."
                    for x in items
                )
        elif topic == "cancellation":
            pol = cl.DATA_.policies["cancellation"]
            text = f"{pol.text} {pol.rct_text}"
        elif topic == "dentists":
            text = " ".join(f"{d.name}, {d.role}." for d in cl.DATA_.dentists)
        elif topic == "emergency":
            text = (
                f"{cl.DATA_.rules['same_day_emergency'].text} {ins['sunday'].text} "
                f"Red flags: {cl.DATA_.clinical.red_flags}"
            )
        else:
            text = ins[topic].text
        if self.page == "home":
            self._send("site.show", {"thing": _THING[topic]})
        return f"{text} (Say it in your own words, briefly.)"

    @needs_result_now
    async def find_slots(self, request: SlotSearch) -> str:
        """Free times for a service, from the dentists' real calendars, and put
        them on the booking page's calendar. Call before offering any time."""
        self.cal.now = cl.now_ist()
        svc = cl.find_service(request.service)
        if svc is None:
            names = ", ".join(f"{s.id} ({s.name})" for s in cl.DATA_.services)
            return f"No service matches '{request.service}'. The services are: {names}."
        d = cl.find_dentist(request.dentist) if request.dentist else None
        if request.dentist and d is None:
            return f"No dentist matches '{request.dentist}'."
        if d is not None and svc.dentists and d.id not in svc.dentists:
            who = ", ".join(x.short for x in cl.DATA_.dentists if x.id in svc.dentists)
            return f"{d.short} does not do {svc.name}. It is done by {who}. Ask which they prefer."
        b = cl.find_branch(request.branch) if request.branch else None
        if b is None and request.branch:
            return f"No branch matches '{request.branch}': Indiranagar or HSR Layout."
        notes: list[str] = []
        when = cl.parse_date(request.date, self.cal.today) if request.date else None
        if request.date and when is None:
            notes.append(f"Could not read the date '{request.date}'; showing the next free days.")
        rule = cl.check_rule(svc, self.patient, when or self.cal.today, self.cal)
        if rule.ok is False and rule.rule is not None:
            alt = cl.service(rule.rule.alternative or "")
            return (
                f"Not bookable for {self.patient.name if self.patient else 'them'}: {rule.rule.text} "
                f"({rule.why}). Offer to book the {alt.name if alt else 'alternative'} first "
                f"(find_slots with service {rule.rule.alternative})."
            )
        if rule.ok is None and rule.rule is not None:
            notes.append(
                f"Rule: {rule.rule.text} The patient is not verified, so this is not checked yet: "
                "ask about it, and it is checked again when you hold a slot."
            )
        did = d.id if d else None
        bid = b.id if b else None
        if when is not None:
            day = [
                s
                for s in self.cal.slots(svc, when, branch_id=bid, dentist_id=did)
                if _in_part(s, request.part_of_day)
            ]
            days = [(when, day)] if day else []
            if not day:
                why = (
                    "the clinic is closed"
                    if cl.DAYS[when.weekday()] == "sun"
                    else "it is outside the booking window"
                    if not self.cal.bookable_day(when)
                    else "nothing is free then"
                )
                notes.append(
                    f"No slot on {cl.spoken_date(when, self.cal.today)}: {why}. The next free days:"
                )
                days = self.cal.next_days(
                    svc, branch_id=bid, dentist_id=did, start=when + timedelta(days=1)
                )
        else:
            days = self.cal.next_days(svc, branch_id=bid, dentist_id=did)
        if request.part_of_day:
            days = [(on, [s for s in got if _in_part(s, request.part_of_day)]) for on, got in days]
            days = [(on, got) for on, got in days if got]
        if not days:
            return " ".join(
                [
                    *notes,
                    f"No free {svc.name} slots in the next {cl.DATA_.booking.horizon_days} days with those choices. Offer another dentist or branch, or a callback.",
                ]
            )
        first_day, first = days[0]
        show_dentist = did or first[0].dentist
        self._send(
            "book.slots",
            {
                "service_id": svc.id,
                "date": _iso(first_day),
                "branch_id": bid or first[0].branch,
                "dentist_id": show_dentist,
                "view": "day",
            },
        )
        self.page = "book"
        landed(self._line("slots"))
        lines = [
            f"{svc.name}: {svc.duration_min} min, {cl.price_text(svc)}."
            + (
                f" {svc.sittings} sittings, {cl.DATA_.rules['rct_sittings'].text}"
                if svc.sittings > 1
                else ""
            )
        ]
        for on, got in days[:3]:
            times = ", ".join(_slot_line(s, self.cal.today) for s in got[:6])
            more = f" and {len(got) - 6} more" if len(got) > 6 else ""
            lines.append(f"{cl.spoken_date(on, self.cal.today)} ({_iso(on)}): {times}{more}.")
        lines.append(
            "On screen: the calendar for the first day. Offer two or three of these, then hold_slot."
        )
        return " ".join([*notes, *lines])

    @needs_result_now
    async def hold_slot(self, request: HoldRequest) -> str:
        """Select one free slot and show the booking summary with its price and
        preparation. Nothing is booked until confirm_booking."""
        self.cal.now = cl.now_ist()
        svc = cl.find_service(request.service)
        if svc is None:
            return f"No service '{request.service}'."
        on = cl.parse_date(request.date, self.cal.today)
        time = cl.parse_time(request.time)
        if on is None or time is None:
            return f"Could not read {request.date} {request.time}: use YYYY-MM-DD and HH:MM from find_slots."
        d = cl.find_dentist(request.dentist) if request.dentist else None
        b = cl.find_branch(request.branch) if request.branch else None
        slot = self.cal.slot_at(
            svc, on, time, branch_id=b.id if b else None, dentist_id=d.id if d else None
        )
        if slot is None:
            near = self.cal.slots(
                svc, on, branch_id=b.id if b else None, dentist_id=d.id if d else None
            )
            near.sort(key=lambda s: abs(s.start - cl.minutes(time)))
            alt = ", ".join(_slot_line(s, self.cal.today) for s in near[:3])
            return (
                f"{cl.spoken_time(time)} on {cl.spoken_date(on, self.cal.today)} is not free for {svc.name}."
                + (
                    f" Nearest free: {alt}."
                    if alt
                    else " Nothing else that day; call find_slots for other days."
                )
            )
        rule = cl.check_rule(svc, self.patient, on, self.cal)
        if rule.ok is False and rule.rule is not None:
            return (
                f"Cannot hold it: {rule.rule.text} ({rule.why}). Offer the "
                f"{rule.rule.alternative} first."
            )
        sittings = self.cal.plan_sittings(svc, slot)
        self.hold = Hold(svc, slot, sittings)
        self._send(
            "book.hold",
            {
                "service_id": svc.id,
                "branch_id": slot.branch,
                "date": _iso(on),
                "time": slot.time,
                "dentist_id": slot.dentist,
                "chair_id": slot.chair,
                "resource_id": slot.resource,
                "sittings": [_sitting_arg(s) for s in sittings] or None,
            },
        )
        self.page = "book"
        landed(self._line("hold"))
        who = cl.who(slot.dentist, full=True, none="the imaging room")
        br = cl.branch(slot.branch)
        prep = cl.DATA_.instructions["eating"].by_service.get(svc.id, "")
        out = [
            f"Held on screen: {svc.name} with {who} at {br.name if br else slot.branch}, "
            f"{cl.spoken_date(on, self.cal.today)} at {cl.spoken_time(slot.time)}, {svc.duration_min} min, "
            f"{cl.price_text(svc)}. Preparation: {prep}"
        ]
        if sittings:
            out.append(
                "Later sittings pencilled in: "
                + "; ".join(f"{cl.spoken_date(s.on)} at {cl.spoken_time(s.time)}" for s in sittings)
                + "."
            )
        if rule.ok is None and rule.rule is not None:
            out.append(f"Rule to check before confirming: {rule.rule.text}")
        if self.patient is None:
            out.append(
                "The patient is not verified: ask for their mobile number (send_code) before confirming."
            )
        else:
            out.append(f"For {self.patient.name}. Read it back in one sentence and ask for a yes.")
        return " ".join(out)

    @needs_result_now
    async def send_code(self, request: PhoneRequest) -> str:
        """Fill the patient's mobile number on screen and send the one-time code."""
        digits = cl.normal_phone(request.phone)
        if len(digits) != 10 or digits[0] not in "6789":
            return f"'{request.phone}' is not a ten-digit Indian mobile number. Ask them to say it again."
        self.phone = digits
        self.code_ok = False
        self._send("patient.phone", {"phone": digits})
        landed(self._line("code"))
        spaced = f"{digits[:5]} {digits[5:]}"
        return f"Code sent to {spaced} (shown on screen as a demo SMS). Ask them to read out the four-digit code."

    @needs_result_now
    async def verify_code(self, request: CodeRequest) -> str:
        """Check the code the patient read out and sign them in."""
        if self.phone is None:
            return "No code was sent yet: ask for their mobile number and call send_code first."
        code = "".join(ch for ch in request.code if ch.isdigit())
        if code != cl.DATA_.otp.demo_code:
            return "That code does not match. Ask them to read the four digits on screen again."
        self.code_ok = True
        self._send("patient.otp", {"code": code})
        known = cl.patient_by_phone(self.phone)
        if known is None:
            return "Verified. This number has no record: it is a new patient. Ask their full name, then register_patient."
        self.patient = known
        landed(self._line("verified", name=known.name))
        up = self.cal.upcoming(known.id)
        listed = "; ".join(self._appt_line(a) for a in up) or "none"
        return f"Verified: {known.name} ({known.id}). Upcoming appointments: {listed}."

    async def register_patient(self, request: NameRequest) -> str:
        """Register a new patient's name after their number was verified."""
        if not self.code_ok or self.phone is None:
            return "Verify their number first (send_code, verify_code)."
        if self.patient is not None:
            return f"Already registered as {self.patient.name}."
        self._new_name = request.name.strip()
        self._send("patient.name", {"name": self._new_name})
        landed(self._line("registered"))
        return f"Registering {self._new_name}."

    def _mint(self) -> str:
        self._next_booking += 1
        return f"{cl.DATA_.booking.id_prefix}{self._next_booking - 1}"

    def _yes(self) -> bool:
        return self.confirm_pressed or affirmed(self.heard)

    async def confirm_booking(self) -> str:
        """Book the held slot, only after the patient's yes to the summary."""
        h = self.hold
        if h is None:
            return "Nothing is held: find_slots, then hold_slot first."
        if self.patient is None:
            return "The patient is not verified: ask for their mobile number (send_code) first."
        if not self._yes():
            return "They have not said yes to the summary yet. Ask: shall I confirm it?"
        rule = cl.check_rule(h.svc, self.patient, h.slot.on, self.cal)
        if rule.ok is False and rule.rule is not None:
            return f"Cannot book: {rule.rule.text} ({rule.why})."
        if (
            self.cal.slot_at(
                h.svc, h.slot.on, h.slot.time, branch_id=h.slot.branch, dentist_id=h.slot.dentist
            )
            is None
        ):
            self.hold = None
            return "That slot was just taken. Say so and call find_slots again."
        booking_id = self._mint()
        sitting_ids = [self._mint() for _ in h.sittings]
        made: list[Appt] = []
        for n, (sid, s) in enumerate(
            zip([booking_id, *sitting_ids], [h.slot, *h.sittings], strict=True), 1
        ):
            made.append(
                Appt(
                    id=sid,
                    service=h.svc.id,
                    branch=s.branch,
                    on=s.on,
                    start=s.start,
                    duration_min=h.svc.duration_min,
                    dentist=s.dentist,
                    chair=s.chair,
                    resource=s.resource,
                    patient_id=self.patient.id,
                    sitting=n if h.svc.sittings > 1 else None,
                )
            )
        ref = self._send(
            "book.confirm",
            {
                "booking_id": booking_id,
                "patient_id": self.patient.id,
                "service_id": h.svc.id,
                "branch_id": h.slot.branch,
                "date": _iso(h.slot.on),
                "time": h.slot.time,
                "dentist_id": h.slot.dentist,
                "chair_id": h.slot.chair,
                "resource_id": h.slot.resource,
                "sittings": [_sitting_arg(s) for s in h.sittings] or None,
                "sitting_ids": sitting_ids or None,
            },
        )
        for a in made:
            self.cal.put(a)
        self._undo[ref] = [a.id for a in made]
        self.hold = None
        landed(self._line("booked"))
        extra = f" Later sittings: {', '.join(sitting_ids)}." if sitting_ids else ""
        prep = cl.DATA_.instructions["eating"].by_service.get(h.svc.id, "")
        return (
            f"Booked {booking_id}: {h.svc.name}, {cl.spoken_date(h.slot.on, self.cal.today)} at "
            f"{cl.spoken_time(h.slot.time)}.{extra} Tell them it's booked, the confirmation is on screen, "
            f"and the one preparation line: {prep}"
        )

    def _appt_line(self, a: Appt) -> str:
        svc = cl.service(a.service)
        who = cl.who(a.dentist)
        b = cl.branch(a.branch)
        sit = (
            f" (sitting {a.sitting} of {svc.sittings})"
            if a.sitting and svc and svc.sittings > 1
            else ""
        )
        return (
            f"{a.id} {svc.name if svc else a.service}{sit} with {who} at {b.short if b else a.branch}, "
            f"{cl.spoken_date(a.on, self.cal.today)} {_iso(a.on)} at {cl.spoken_time(cl.hhmm(a.start))}"
        )

    @needs_result_now
    async def my_appointments(self) -> str:
        """The verified patient's upcoming appointments and what each change would cost."""
        if self.patient is None:
            return "Not verified yet: ask for their mobile number (send_code)."
        self.cal.now = cl.now_ist()
        up = self.cal.upcoming(self.patient.id)
        if not up:
            return f"{self.patient.name} has no upcoming appointments."
        out: list[str] = []
        for a in up:
            terms = cl.change_terms(a, self.cal, action="reschedule")
            change = (
                f"change: {'free' if terms.fee == 0 else cl.rupees(terms.fee) + ' fee'} ({terms.why})"
                if terms.allowed
                else f"cannot change online: {terms.why}"
            )
            out.append(f"{self._appt_line(a)}; {change}")
        return f"{self.patient.name}: " + " | ".join(out)

    @needs_result_now
    async def propose_change(self, request: ChangeRequest) -> str:
        """Put a reschedule or a cancellation on screen with its fee, for the
        patient to say yes to. Without a new date and time, returns the free ones."""
        if self.patient is None:
            return "Not verified yet: ask for their mobile number (send_code)."
        self.cal.now = cl.now_ist()
        a = self.cal.appts.get(request.appointment_id.strip().upper())
        if a is None or a.patient_id != self.patient.id:
            mine = ", ".join(x.id for x in self.cal.upcoming(self.patient.id)) or "none"
            return f"{request.appointment_id} is not one of {self.patient.name}'s appointments ({mine})."
        terms = cl.change_terms(a, self.cal, action=request.action)
        if not terms.allowed:
            return f"Cannot {request.action} {a.id} online: {terms.why}. Offer a callback from the desk."
        svc = cl.service(a.service)
        assert svc is not None
        if request.action == "cancel":
            self.pending = Pending(a, "cancel", terms.fee)
            self._send(
                "appt.propose", {"appointment_id": a.id, "action": "cancel", "fee": terms.fee}
            )
            self.page = "my-appointments"
            landed(self._line("proposed"))
            return (
                f"On screen: cancel {self._appt_line(a)}. {terms.why.capitalize()}. "
                "Tell them the fee in one sentence and ask for a yes."
            )
        window = cl.sitting_window(a, self.cal, self.patient)
        if not request.date or not request.time:
            start = max(self.cal.today, window[0]) if window else self.cal.today
            days = self.cal.next_days(
                svc, branch_id=None, dentist_id=a.dentist, start=start, ignore=a.id, days=3
            )
            if window:
                days = [(on, got) for on, got in days if on <= window[1]]
            if not days:
                return "No free times to move it to. Offer a callback from the desk."
            self._send(
                "cal.view",
                {
                    "date": _iso(days[0][0]),
                    "dentist_id": a.dentist,
                    "resource_id": a.resource,
                    "mode": "week",
                },
            )
            lines = [
                f"{cl.spoken_date(on, self.cal.today)} ({_iso(on)}): "
                + ", ".join(_slot_line(s, self.cal.today) for s in got[:5])
                for on, got in days
            ]
            limit = (
                f" A root canal sitting must stay between {_iso(window[0])} and {_iso(window[1])}."
                if window
                else ""
            )
            return (
                f"Free times for {a.id}:{limit} "
                + " | ".join(lines)
                + ". Ask which they want, then call again with date and time."
            )
        on = cl.parse_date(request.date, self.cal.today)
        time = cl.parse_time(request.time)
        if on is None or time is None:
            return "Could not read the new date or time: use YYYY-MM-DD and HH:MM."
        if window and not (window[0] <= on <= window[1]):
            return (
                f"A root canal sitting can only move to between {cl.spoken_date(window[0])} and "
                f"{cl.spoken_date(window[1])}. {cl.DATA_.policies['cancellation'].rct_text}"
            )
        slot = self.cal.slot_at(svc, on, time, dentist_id=a.dentist, ignore=a.id) or (
            self.cal.slot_at(svc, on, time, ignore=a.id) if svc.resource else None
        )
        if slot is None:
            near = self.cal.slots(svc, on, dentist_id=a.dentist, ignore=a.id)
            near.sort(key=lambda s: abs(s.start - cl.minutes(time)))
            alt = ", ".join(_slot_line(s, self.cal.today) for s in near[:3])
            return (
                f"{cl.spoken_time(time)} on {cl.spoken_date(on, self.cal.today)} is not free."
                + (f" Nearest: {alt}." if alt else "")
            )
        self.pending = Pending(a, "reschedule", terms.fee, slot)
        self._send(
            "appt.propose",
            {
                "appointment_id": a.id,
                "action": "reschedule",
                "fee": terms.fee,
                "date": _iso(on),
                "time": slot.time,
                "branch_id": slot.branch,
                "dentist_id": slot.dentist,
                "chair_id": slot.chair,
                "resource_id": slot.resource,
            },
        )
        self.page = "my-appointments"
        landed(self._line("proposed"))
        return (
            f"On screen: move {a.id} from {cl.spoken_date(a.on, self.cal.today)} "
            f"{cl.spoken_time(cl.hhmm(a.start))} to {cl.spoken_date(on, self.cal.today)} "
            f"{cl.spoken_time(slot.time)}. {terms.why.capitalize()}. Ask for a yes."
        )

    async def confirm_change(self) -> str:
        """Make the change on screen, only after the patient's yes."""
        p = self.pending
        if p is None:
            return "No change is on screen: call propose_change first."
        if not self._yes():
            return "They have not said yes yet. Ask: shall I go ahead?"
        args: dict[str, Any] = {"appointment_id": p.appt.id, "action": p.action, "fee": p.fee}
        new = replace(p.appt, status="cancelled", changes=p.appt.changes + 1)
        if p.slot is not None:
            s = p.slot
            args |= {
                "date": _iso(s.on),
                "time": s.time,
                "branch_id": s.branch,
                "dentist_id": s.dentist,
                "chair_id": s.chair,
                "resource_id": s.resource,
            }
            new = cl.moved(p.appt, s)
        ref = self._send("appt.apply", args)
        self._undo[ref] = [p.appt]
        self.cal.put(new)
        self.pending = None
        landed(self._line("changed"))
        fee = f" A {cl.rupees(p.fee)} late-change fee applies." if p.fee else ""
        if p.action == "cancel":
            return f"{p.appt.id} is cancelled.{fee} Tell them in one sentence."
        assert p.slot is not None
        return (
            f"{p.appt.id} is moved to {cl.spoken_date(p.slot.on, self.cal.today)} at "
            f"{cl.spoken_time(p.slot.time)}.{fee} Tell them in one sentence."
        )

    async def request_callback(self, request: CallbackRequest) -> str:
        """Ask a dentist to call the patient back, for anything clinical."""
        phone = (
            self.patient.phone
            if self.patient
            else self.phone or (cl.normal_phone(request.phone) if request.phone else None)
        )
        if not phone or len(phone) != 10:
            return "No number to call yet: ask for their mobile number, then call request_callback with phone."
        self._next_callback += 1
        cid = f"CB-{self._next_callback - 1}"
        window = cl.DATA_.clinical.callback_windows[request.urgency]
        self._send(
            "callback.request",
            {
                "callback_id": cid,
                "reason": request.reason,
                "urgency": request.urgency,
                "window": window,
                "phone": phone,
            },
        )
        landed(self._line("callback"))
        return f"Callback {cid} requested: a dentist calls {phone[:5]} {phone[5:]} {window}. Tell them that."

    async def set_language(self, request: LanguageRequest) -> str:
        """Switch the call's language (both what you hear and how you speak)."""
        lang = request.language
        if lang not in PERSONA.codes:
            return f"This desk speaks {', '.join(o.label for o in PERSONA.languages)} only."
        if lang == self.lang:
            return f"Already in {self._lang_name(lang)}."
        configure_soon(self.session, self._speaking(lang))
        self.lang = lang
        self.session.dispatch(LanguageChanged(language=lang))
        landed(self._line("switch"))
        return f"Switched to {self._lang_name(lang)}: speak {self._lang_name(lang)} from now on."
