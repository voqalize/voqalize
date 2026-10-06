"""PetwellBrain — the "Appointment Desk" voice agent for a vet hospital chain.

A ``GeminiBrain`` (LLM + screen-driving tools + session state). Voqalize dials
this brain's WebSocket per session; the inherited ``respond`` runs Gemini's
function calls itself, and **a turn is one request**: each call runs as it
arrives, after the speech before it has gone out, and its result is filed in the
context for the model to read with the caller's next message.

The flow is the hospital's own booking form, spoken: clinic visit or vet at home,
then city, branch, reason for the visit, a time, and the owner's and pet's
details — and the caller taps **Send Request** themselves. Each step is a tool
that puts the answer on screen.

**Only ``show_slots`` is marked ``@needs_result_now``.** Which times are still
free at a branch on a day is something only the slot book knows, and the model
offers those times out loud, so it reads them before it speaks. Every branch,
service and helpline is compiled into the prompt, so every other tool shows what
the model already named and says its line with the call.

The browser also reaches the brain outside any turn, over
:meth:`~voqalize.sdk.Brain.on_rtvi`: a branch, service or time the caller
**tapped**, and the final Send Request. Each folds into the context and marks
that a word is owed; :meth:`~PetwellBrain.on_user_idle` pays it once the caller
is quiet, so a tap never puts the assistant's voice over someone still using the
screen.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncGenerator
from typing import Any, Literal
from zoneinfo import ZoneInfo

from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel, Field
from voqalize_demos import DEFAULT_MODEL, FallbackLine, GeminiBrain, landed, needs_result_now

from voqalize.sdk import Action, RTVIMessage, Session, Speech, UserIdle, UserMessage
from voqalize.sdk.wire import Config, IdleConfig, Language, SttConfig, TtsConfig, Voice

from .app_events import (
    PETWELL_EVENTS,
    AppointmentRequested,
    BranchPicked,
    CityPicked,
    PetwellEvent,
    ServicePicked,
    SlotPicked,
    VisitTypePicked,
)
from .catalog import (
    OPENING_SOON,
    VisitType,
    as_city,
    booking_dates,
    branches_in,
    catalog_for_prompt,
    get_branch,
    get_service,
    helpline_for,
    slots_for,
)

HOSPITAL = "Petwell Veterinary Hospitals"

PetType = Literal["dog", "cat", "bird", "rabbit", "other", ""]

_IST = ZoneInfo("Asia/Kolkata")


def _today() -> dt.date:
    return dt.datetime.now(_IST).date()


def _say_date(d: dt.date, today: dt.date) -> str:
    if d == today:
        return "today"
    if d == today + dt.timedelta(days=1):
        return "tomorrow"
    return d.strftime("%A %-d %B")


def _dates_for_prompt(today: dt.date) -> str:
    rows = []
    for d in booking_dates(today):
        tag = " (today)" if d == today else " (tomorrow)" if d == today + dt.timedelta(1) else ""
        rows.append(f"- {d.strftime('%A %-d %B')}{tag} = {d.isoformat()}")
    return "\n".join(rows)


def _system_instruction(today: dt.date) -> str:
    return f"""You are the Appointment Desk for {HOSPITAL}, a chain of veterinary hospitals across India, open 24x7. A pet owner is on the booking page and talking to you live. You book them a clinic visit or a vet at home — and you DRIVE THEIR SCREEN as you talk.

EVERY RESPONSE STARTS WITH WORDS. Whenever you call a tool, the same response opens with the one short spoken line that goes with it — the line first, then the calls, so the screen moves while the caller hears you. A response made only of tool calls is silence. For example:
- "I want to get my dog vaccinated in Powai": say "Happy to help — a vaccination at our Powai branch. Which day suits you?" and call start_booking, choose_city, choose_branch and choose_service in that one response.
- The caller picks a day: say "Let me check that day." and call show_slots. Its free times come straight back to you, and you then offer two or three of them.
- The caller picks a time: say "Eleven it is. What's your name, and your pet's name?" and call choose_slot.

YOU CONTROL THE SCREEN. Every answer the caller gives goes on screen through its tool — never just say it. Several answers in one sentence → several calls in one response, in flow order.

THE CALLER CAN ALSO TAP. If you are told the caller tapped something, treat it as their answer and carry on with the next step — do not ask it again.

{catalog_for_prompt()}

DATES YOU CAN BOOK (say the day, use the ISO date only in tool arguments):
{_dates_for_prompt(today)}

THE BOOKING FLOW — one step at a time, skipping any step the caller already answered:
1. VISIT TYPE: clinic visit, or a vet at home (vaccination, minor illness or injury, blood sample, physiotherapy only). Call start_booking.
2. CITY: call choose_city. Kolkata is opening soon — say so warmly and offer to book in another city instead; never book there.
3. BRANCH: if the city has one branch, choose it straight away. Otherwise name the branches by area and ask which is closest. Call choose_branch. A home visit is sent from the branch nearest them.
4. REASON: map what they describe to one service and call choose_service. Clinic visits use Everyday or Specialty care; home visits use At home services only. If it's unclear, ask one short question.
5. DAY AND TIME: call show_slots for the day they want (today if they say "as soon as possible"), offer two or three of the free times it returns, then call choose_slot with the one they pick. Never offer a time show_slots did not return.
6. DETAILS: ask for the owner's name, the pet's name and what kind of pet, and a phone number — one or two at a time. Email is optional; for a home visit also ask for the address or locality. Call fill_details each time you learn something, with only the fields you learned. Read phone numbers back in groups to confirm.
7. REVIEW: once name, pet name and phone are in, call show_review and ask them to check the summary and tap "Send Request". Then stop. When they send it you'll be told the reference — read it out, say the branch will call to confirm, and wish the pet well.

EMERGENCIES COME FIRST. If the pet is bleeding heavily, not breathing, collapsed, having a seizure, hit by a vehicle, or has eaten poison, do NOT book. Call show_emergency with their city (if known) in the same response as a short, calm line: give the helpline number for their region and tell them to come straight to the nearest 24x7 emergency branch now.

STYLE:
- This is voice. One or two short sentences, never more than three. One question at a time.
- Warm and reassuring — people calling a vet are often worried about their pet.
- Never read ids aloud. Say times naturally ("half past ten", "four PM").
- Do not give medical diagnoses or medicine doses; the vet will see the pet.
- Never invent branches, services, prices or doctors. If it is not above, say the branch will help on the call."""


_GREETING = (
    f"Hi, welcome to {HOSPITAL}. I can book a clinic visit or a vet at home — "
    "how can I help your pet today?"
)

# How long the caller has to be quiet before the assistant may answer a tap.
_IDLE_MS = 3000


# ─── Actions (screen-driving payloads) ─────────────────────────────────────────


class StartBooking(Action):
    visit_type: VisitType


class ChooseCity(Action):
    city: str


class ChooseBranch(Action):
    branch_id: str


class ChooseService(Action):
    service_id: str


class ShowSlots(Action):
    branch_id: str
    date: str = Field(description="ISO date, e.g. 2026-10-07.")
    visit_type: VisitType = "clinic"
    times: list[str] = Field(default_factory=list[str])


class ChooseSlot(Action):
    date: str = Field(description="ISO date, e.g. 2026-10-07.")
    time: str = Field(description="24-hour HH:MM, exactly as show_slots returned it.")


class FillDetails(Action):
    owner_name: str = Field(default="", description="Leave empty if not learned this turn.")
    pet_name: str = Field(default="", description="Leave empty if not learned this turn.")
    pet_type: PetType = Field(default="", description="Leave empty if not learned this turn.")
    phone: str = Field(default="", description="Digits only. Empty if not learned this turn.")
    email: str = Field(default="", description="Empty if not given.")
    address: str = Field(default="", description="Home visits only. Empty if not given.")
    notes: str = Field(default="", description="A short note for the vet. Empty if none.")


class ShowReview(Action):
    pass


class ShowEmergency(Action):
    city: str = ""
    helpline: str = ""
    branch_ids: list[str] = Field(default_factory=list[str])


class GoHome(Action):
    pass


class SlotQuery(BaseModel):
    """What ``show_slots`` asks the model for."""

    date: str = Field(description="ISO date from the DATES list, e.g. 2026-10-07.")


class EmergencyQuery(BaseModel):
    """What ``show_emergency`` asks the model for."""

    city: str = Field(default="", description="The caller's city if known, else empty.")


async def _silence() -> AsyncGenerator[Any, None]:
    """Yields nothing: an idle tick the assistant has no reason to answer."""
    for _ in ():
        yield


class PetwellBrain(GeminiBrain):
    """One per session. Owns this caller's booking so far; the inherited tool
    loop runs each turn, each tool below drives the screen, and ``on_rtvi`` folds
    the caller's own taps in — see the module docstring."""

    def __init__(
        self,
        *,
        client: genai.Client,
        model: str = DEFAULT_MODEL,
        today: dt.date | None = None,
    ) -> None:
        self._today = today or _today()
        super().__init__(
            client=client, system_instruction=_system_instruction(self._today), model=model
        )
        self.visit_type: VisitType = "clinic"
        self.city: str | None = None
        self.branch_id: str | None = None
        self.service_id: str | None = None
        self.date: str | None = None
        self.time: str | None = None
        self._owed_a_reply = False
        self._fallback = FallbackLine()

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        """The tools the assistant may call. Only ``show_slots`` is marked
        ``@needs_result_now``: see the module docstring."""
        return [
            self.start_booking,
            self.choose_city,
            self.choose_branch,
            self.choose_service,
            self.show_slots,
            self.choose_slot,
            self.fill_details,
            self.show_review,
            self.show_emergency,
            self.go_home,
        ]

    async def start_booking(self, action: StartBooking) -> str:
        """Start a booking: 'clinic' for a visit to a branch, 'home' for a vet at
        home. Opens the location step on the caller's screen."""
        logger.info("petwell: start_booking {}", action.visit_type)
        self.visit_type = action.visit_type
        self.service_id = None
        self.session.dispatch(action)
        if action.visit_type == "home":
            landed("A vet at home — which city are you in?", "Sure, a home visit. Which city?")
        else:
            landed("A clinic visit — which city are you in?", "Sure. Which city are you in?")
        return str({"status": "started", "visit_type": action.visit_type})

    async def choose_city(self, action: ChooseCity) -> str:
        """Select the caller's city and show its branches on screen."""
        city = as_city(action.city)
        if city is None:
            return f"error: we have no branch in {action.city!r}"
        logger.info("petwell: choose_city {}", city)
        self.city = city
        self.branch_id = None
        self.session.dispatch(ChooseCity(city=city))
        if city in OPENING_SOON:
            landed(f"Our {city} hospital is opening soon — could another city work?")
            return str({"status": "opening_soon", "city": city})
        branches = branches_in(city)
        landed(f"Here are our branches in {city}.", f"{city} — which branch is closest?")
        return str({"status": "shown", "city": city, "branches": [b["name"] for b in branches]})

    async def choose_branch(self, action: ChooseBranch) -> str:
        """Select the branch for the visit and move on to the reason for the
        visit."""
        branch = get_branch(action.branch_id)
        if branch is None:
            return f"error: unknown branch {action.branch_id!r}"
        if branch["city"] in OPENING_SOON:
            return f"error: {branch['name']} is opening soon and not taking appointments"
        logger.info("petwell: choose_branch {}", action.branch_id)
        self.city = branch["city"]
        self.branch_id = branch["id"]
        self.session.dispatch(action)
        landed(f"{branch['name']} it is. What's the visit for?")
        return str({"status": "selected", "branch": branch["name"]})

    async def choose_service(self, action: ChooseService) -> str:
        """Select the reason for the visit and move on to picking a day and
        time."""
        service = get_service(action.service_id)
        if service is None:
            return f"error: unknown service {action.service_id!r}"
        if service["visit"] != self.visit_type:
            return (
                f"error: {service['name']} is a {service['visit']} service but this booking "
                f"is a {self.visit_type} visit — pick a matching service, or start_booking again"
            )
        logger.info("petwell: choose_service {}", action.service_id)
        self.service_id = service["id"]
        self.session.dispatch(action)
        landed(f"{service['name']}. Which day works for you?")
        return str({"status": "selected", "service": service["name"]})

    @needs_result_now
    async def show_slots(self, query: SlotQuery) -> str:
        """Show one day's free times at the chosen branch on the caller's screen
        and return them. You get them straight away, so say a short line with
        the call and offer two or three of the returned times after it."""
        if self.branch_id is None:
            return "error: choose a branch first"
        try:
            day = dt.date.fromisoformat(query.date)
        except ValueError:
            return f"error: {query.date!r} is not an ISO date"
        if day not in booking_dates(self._today):
            return "error: we can only book from today up to six days ahead"
        times = slots_for(self.branch_id, day.isoformat(), self.visit_type)
        if day == self._today:
            now = dt.datetime.now(_IST).strftime("%H:%M")
            times = [t for t in times if t > now]
        logger.info("petwell: show_slots {} {} → {}", self.branch_id, day, len(times))
        self.session.dispatch(
            ShowSlots(
                branch_id=self.branch_id,
                date=day.isoformat(),
                visit_type=self.visit_type,
                times=times,
            )
        )
        return str(
            {
                "date": day.isoformat(),
                "day": _say_date(day, self._today),
                "free_times": times or "fully booked — offer the next day",
            }
        )

    async def choose_slot(self, action: ChooseSlot) -> str:
        """Pick the day and time the caller chose and move on to their details."""
        if self.branch_id is None:
            return "error: choose a branch first"
        if action.time not in slots_for(self.branch_id, action.date, self.visit_type):
            return f"error: {action.time} on {action.date} is not free — offer a time show_slots returned"
        logger.info("petwell: choose_slot {} {}", action.date, action.time)
        self.date, self.time = action.date, action.time
        self.session.dispatch(action)
        landed("Got it. May I have your name and your pet's name?")
        return str({"status": "selected", "date": action.date, "time": action.time})

    async def fill_details(self, action: FillDetails) -> str:
        """Fill the owner's and pet's details into the form on screen. Pass only
        the fields you learned; empty fields are left as they are."""
        filled = {k: v for k, v in action.model_dump().items() if v}
        logger.info("petwell: fill_details {}", sorted(filled))
        self.session.dispatch(action)
        landed("Noted.", "Got that down.")
        return str({"status": "filled", "fields": sorted(filled)})

    async def show_review(self) -> str:
        """Show the booking summary with the Send Request button. Call once the
        owner's name, pet's name and phone are in, in the same response that asks
        the caller to check it and tap Send Request."""
        logger.info("petwell: show_review")
        self.session.dispatch(ShowReview())
        landed(
            "Here's your booking. Please check it and tap Send Request.",
            "All set — have a look and tap Send Request.",
        )
        return str({"status": "review_shown"})

    async def show_emergency(self, query: EmergencyQuery) -> str:
        """Open the emergency panel: the helpline for the caller's region and the
        24x7 emergency branches in their city. Use instead of booking when the
        pet is in danger right now."""
        city = as_city(query.city) or ""
        line = helpline_for(city) if city else None
        er = [b["id"] for b in branches_in(city) if b["emergency"]] if city else []
        logger.info("petwell: show_emergency city={!r}", city)
        self.session.dispatch(
            ShowEmergency(city=city, helpline=line["phone"] if line else "", branch_ids=er)
        )
        landed("Please come to our nearest emergency branch now — the number is on your screen.")
        return str(
            {
                "status": "emergency_shown",
                "helpline": line["phone"] if line else "see screen for all regions",
                "emergency_branches": [b["name"] for b in branches_in(city) if b["emergency"]],
            }
        )

    async def go_home(self) -> str:
        """Clear the booking and go back to the start screen."""
        logger.info("petwell: go_home")
        self.city = self.branch_id = self.service_id = self.date = self.time = None
        self.session.dispatch(GoHome())
        landed("Back to the start.")
        return str({"status": "home"})

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        await session.configure(
            Config(
                tts=TtsConfig(voice=Voice.OMNIVOICE_GAURAV, language=Language.EN),
                stt=SttConfig(language=Language.EN),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
            )
        )

    async def greet(self, session: Session) -> str:
        """The opener is fixed — no model call — so the caller hears the desk the
        instant the session connects."""
        return _GREETING

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The inherited turn, and — when it acted on screen and said nothing —
        the line of the last call that landed. No second model request."""
        async for event in self._fallback.speak_if_silent(self, super().respond(session)):
            yield event

    def on_user_message(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]:
        """The caller spoke; whatever they tapped is answered by this reply."""
        self._owed_a_reply = False
        return super().on_user_message(session, msg)

    def on_user_idle(self, session: Session, idle: UserIdle) -> AsyncGenerator[Speech, None]:
        """The caller has gone quiet. If the last thing they did was tap the
        screen, this is the turn that carries on from it; otherwise silence — a
        caller reading the screen is not one to be prompted."""
        if not self._owed_a_reply:
            return _silence()
        self._owed_a_reply = False
        logger.info("petwell: idle -> answering what the caller tapped")
        return self.respond(session)

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """A tap on the booking screen. Folded into the context without taking
        the floor; :meth:`on_user_idle` answers it once the caller is quiet."""
        event = PETWELL_EVENTS.parse(msg)
        if event is None:
            return
        note = self.apply_event(event)
        if note:
            self.append_to_context(types.Content(role="user", parts=[types.Part(text=note)]))
            self._owed_a_reply = True

    # ─── Browser → brain ────────────────────────────────────────────────

    def apply_event(self, event: PetwellEvent) -> str | None:
        """Bring the booking up to date with a tap and say what happened, as the
        note the model reads next. ``None`` for a tap that names nothing real."""
        match event:
            case VisitTypePicked():
                self.visit_type = event.visit_type
                self.service_id = None
                kind = "a vet at home" if event.visit_type == "home" else "a clinic visit"
                return f"[The caller tapped {kind} on screen.] Carry on with the next step."
            case CityPicked():
                city = as_city(event.city)
                if city is None:
                    return None
                self.city, self.branch_id = city, None
                return f"[The caller tapped {city} on screen.] Carry on with the next step."
            case BranchPicked():
                branch = get_branch(event.branch_id)
                if branch is None:
                    return None
                self.city, self.branch_id = branch["city"], branch["id"]
                return (
                    f"[The caller tapped the {branch['name']} branch.] Carry on with the next step."
                )
            case ServicePicked():
                service = get_service(event.service_id)
                if service is None:
                    return None
                self.service_id = service["id"]
                return f"[The caller tapped {service['name']}.] Carry on with the next step."
            case SlotPicked():
                self.date, self.time = event.date, event.time
                return (
                    f"[The caller tapped {event.time} on {event.date}.] "
                    "Carry on with the next step."
                )
            case AppointmentRequested():
                logger.info("petwell: appointment_requested ref={}", event.ref)
                branch = get_branch(self.branch_id or "")
                where = branch["name"] if branch else "the branch"
                return (
                    f"[The caller tapped Send Request. Reference {event.ref}.] Next time you "
                    f"speak, read the reference out clearly, say {where} will call "
                    f"{event.owner_name or 'them'} shortly to confirm, and wish "
                    f"{event.pet_name or 'their pet'} well. Two sentences."
                )
