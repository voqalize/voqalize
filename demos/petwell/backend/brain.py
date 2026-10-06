"""PetwellBrain — Tushar, the voice front desk of a vet hospital chain's website.

A ``GeminiBrain`` (LLM + screen-driving tools + session state). Voqalize dials
this brain's WebSocket per session; the inherited ``respond`` runs Gemini's
function calls itself, and **a turn is one request**: each call runs as it
arrives, after the speech before it has gone out, and its result is filed in the
context for the model to read with the visitor's next message.

The page is the hospital's website — home, services, locations, a Health Hub of
articles, a vet-at-home page — with a booking panel over it. Tushar moves the
visitor around the site as they talk, opens the article they ask about and
answers from it, and books the visit the way the hospital's own form does:
clinic or home, city and branch, reason, a day and time, and the owner's and
pet's details — then the visitor taps **Send Request** themselves.

**Only ``show_slots`` is marked ``@needs_result_now``.** Which times are still
free is something only the slot book knows. Every branch, service, helpline and
article is compiled into the prompt, so every other tool shows what the model
already named and says its line with the call.

**Language follows the visitor**, like the kiosk's: ten languages, one voice,
both legs always moved in one request (:mod:`.language`). The ``switch_language``
tool only records the switch; the brain moves both legs after the model's turn
and then says a fixed line in the new language, in the new voice. A visitor who
plainly drifts back to English — or speaks Hindi to the English recognizer — is
caught in Python before the model runs. The page follows in Hindi; in any other
language it stays English.

The browser reaches the brain outside any turn, over :meth:`on_rtvi`: pages and
articles the visitor opens (noted), booking taps and Send Request (noted, and
owed a reply on the next idle tick). Nobody picks a language on the page: the
desk hears it.
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
from voqalize_demos import (
    DEFAULT_MODEL,
    FallbackLine,
    GeminiBrain,
    landed,
    needs_result_now,
    phrase,
)
from voqalize_demos.silent_turn import Phrase

from voqalize.sdk import (
    Action,
    RequestRejected,
    RTVIMessage,
    Session,
    Speech,
    SpeechChunk,
    SpeechEnd,
    SpeechStart,
    UserIdle,
    UserMessage,
)
from voqalize.sdk.gemini import _Unit  # pyright: ignore[reportPrivateUsage]

from .app_events import (
    PETWELL_EVENTS,
    AppointmentRequested,
    ArticleOpened,
    BookingOpened,
    BranchPicked,
    CityPicked,
    Page,
    PagePicked,
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
from .hub import get_article, hub_for_prompt
from .language import (
    GREETING,
    IDLE_MS,
    LANGUAGE_CODE,
    SWITCH_LINE,
    LanguageName,
    as_language,
    config_for,
    screen_language_for,
)
from .latin_hindi import reads_as_latin_hindi
from .script_english import reads_as_english

HOSPITAL = "Petwell Veterinary Hospitals"

PetType = Literal["dog", "cat", "bird", "rabbit", "other", ""]

_IST = ZoneInfo("Asia/Kolkata")

# How long the visitor has to be quiet before the desk may answer a click.
_IDLE_MS = IDLE_MS


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
    languages = ", ".join(LANGUAGE_CODE)
    return f"""You are Tushar, the AI front-desk assistant on the website of {HOSPITAL}, a chain of veterinary hospitals across India, open 24x7. You are a man — in Hindi and other gendered languages use masculine forms for yourself ("मैं करता हूँ", "समझ गया"). A visitor is on the website and talking to you live. You help them find what they need on the site, answer from the hospital's Health Hub, and book a clinic visit or a vet at home — and you DRIVE THEIR SCREEN as you talk.

EVERY RESPONSE STARTS WITH WORDS. Whenever you call a tool, the same response opens with the one short spoken line that goes with it — the line first, then the calls, so the screen moves while the visitor hears you. A response made only of tool calls is silence. (The one exception is switch_language — see LANGUAGE.)

YOU CONTROL THE SCREEN. Every answer goes on screen through its tool — never just say it. Several answers in one sentence → several calls in one response, in flow order.

THE VISITOR CAN ALSO CLICK. If you are told they opened a page, an article or the booking panel, or tapped a booking step, treat it as what they want and carry on from there — do not ask again.

THE WEBSITE — pages you can open with navigate:
- home: hero, care we offer, branches, Petwell@Home, testimonials, latest articles.
- services: every clinic service, everyday and specialty care.
- locations: all branches by city. Use show_branches with a city to point at that city's branches.
- health_hub: the article library. Use open_article to open one.
- at_home: the vet-at-home service.
Browsing is not booking: "where is your Lucknow branch?" → show_branches; "book me in Lucknow" → the booking flow.

{catalog_for_prompt()}

{hub_for_prompt()}

HEALTH HUB: when someone asks about a health topic an article covers, open it with open_article and answer in one or two sentences from its facts only, then offer to book its service. These are general information, not a diagnosis — never diagnose, never suggest medicines or doses; the vet will examine the pet.

DATES YOU CAN BOOK (say the day, use the ISO date only in tool arguments):
{_dates_for_prompt(today)}

THE BOOKING FLOW — it happens in a booking panel over the page. One step at a time, skipping any step already answered:
1. VISIT TYPE: clinic visit, or a vet at home (vaccination, minor illness or injury, blood sample, physiotherapy only). Call start_booking — it opens the panel.
2. CITY: call choose_city. Kolkata is opening soon — say so warmly and offer another city; never book there.
3. BRANCH: if the city has one branch, choose it straight away. Otherwise name the branches by area and ask which is closest. Call choose_branch. A home visit is sent from the nearest branch.
4. REASON: map what they describe to one service and call choose_service. Clinic visits use Everyday or Specialty care; home visits use At home services only. If unclear, ask one short question.
5. DAY AND TIME: call show_slots for the day they want (today if "as soon as possible"), offer two or three of the free times it returns, then call choose_slot with the one they pick. Never offer a time show_slots did not return.
6. DETAILS: ask for the owner's name, the pet's name and kind of pet, and a phone number — one or two at a time. Email is optional; for a home visit also ask the address or locality. Call fill_details each time you learn something, with only the fields you learned. Read phone numbers back in groups to confirm.
7. REVIEW: once name, pet name and phone are in, call show_review and ask them to check the summary and tap Send Request. Then stop. When they send it you'll be told the reference — read it out, say the branch will call to confirm, and wish the pet well.

EMERGENCIES COME FIRST. If the pet is bleeding heavily, not breathing, collapsed, having a seizure, hit by a vehicle, or has eaten poison, do NOT book. Call show_emergency with their city (if known) in the same response as a short, calm line: give the helpline for their region and tell them to come straight to the nearest 24x7 emergency branch now.

LANGUAGE — it switches by itself; nobody picks a language on the page
- You speak {languages}. You start in English. The visitor may speak English or any of these, and may change their mind at any point. The call is always in the language they are speaking, whatever the turn is — a request, a question or an answer. The moment they ask for a language, OR you can tell they are already speaking one, call switch_language with it — and call it ALONE, with no words at all. This is the one call that goes without a line: your voice is still in the old language when you write, so anything you say would come out in that one. The desk says the line itself, in the new language, once the voice has changed. Speak the new language from their next turn on. When you are sure, do not ask permission first; when you are not, see SURE, OR NOT SURE below.

HOW TO TELL THEY ARE NOT SPEAKING ENGLISH — read this carefully, it is the part that goes wrong
- While you are in English, the recognizer only knows English. It CANNOT write Hindi or any other Indian language. When a visitor speaks Hindi, you do not see Hindi — you see English words forced onto Hindi sounds, strung together in a way no English speaker would say. Examples of a visitor speaking Hindi:
    "Mirror dog ko bow car hey."               = मेरे डॉग को बुखार है
    "Mu j a pointment chahiye kal ka."          = मुझे अपॉइंटमेंट चाहिए कल का
    "Uh much."                                  = a Hindi opener ("मुझे…") cut short — not English
    "Miranama Rahul."                           = मेरा नाम राहुल — "Miranama" is not part of a name
- So: if a turn in English does not make sense as English — odd word order, words that do not fit together, a fragment that answers nothing — the visitor is speaking an Indian language. Call switch_language IMMEDIATELY, in that same turn. Pick the language from the sounds that survive the garbling:
    Hindi      — "mera", "mere", "mujhe", "naam", "hai", "kya", "nahi", "haan", "chahiye", "kutta", "billi", "bimar"
    Marathi    — "maza", "majha", "naav", "aahe", "kay", "nahi", "paahije", "kutra"
    Bengali    — "amar", "naam", "ki", "chai", "nei", "bolun", "kukur"
    Gujarati   — "maru", "naam", "che", "joie", "nathi", "kutro"
    Punjabi    — "mera", "naa", "ae", "chahida", "nahin", "kutta"
    Tamil      — "naan", "enna", "illai", "vendum", "peyar", "sollunga", "romba", "naai"
    Telugu     — "nenu", "naa", "peru", "emi", "kavali", "ledu", "cheppandi", "kukka"
    Kannada    — "naanu", "nanna", "beku", "illa", "enu", "hesaru", "maadi", "naayi"
    Malayalam  — "ente", "peru", "venam", "illa", "entha", "parayu", "patti"
  When the sounds do not point clearly at one, choose Hindi — it is the most common, and the visitor will correct you.
- One such turn is enough. Do not wait for a second. Do not ask "sorry, could you repeat that?" in English first — that answer will be mangled too. Do not treat a garbled phrase as a name, a city or an answer.
- What they said in that turn was lost to the English recognizer. The desk's own switch line, in their language, invites them to go on, so they say it again. Never act on the garbled words.
- The same happens in the other direction. In Hindi, the recognizer writes everything in Devanagari. A Devanagari turn that is not Hindi — "नानु बेकु इल्ला" is Kannada, "नान एन्न" is Tamil — means they are speaking another language. Switch to it the same way.

HOW TO TELL THEY HAVE GONE BACK TO ENGLISH — the other half, and it goes wrong just as often
- In any Indian language, the recognizer writes everything in that language's script — English too. English spoken to it comes out as English words SPELLED in that script:
    Hindi mode:    "आई वांट टू बुक एन अपॉइंटमेंट"     = "I want to book an appointment"
    Tamil mode:    "வாட் இஸ் தி டைம்"                  = "What is the time"
    Kannada mode:  "ಐ ವಾಂಟ್ ಟು ಸ್ಪೀಕ್ ಇನ್ ಇಂಗ್ಲಿಷ್"     = "I want to speak in English"
- Judge by the small grammar words, never by the nouns. Dog, cat, vaccination, appointment, doctor, clinic are borrowed into every Indian language and prove nothing. The grammar words decide: I, am, is, are, the, a, in, to, want, can, what, yes, please — in Devanagari आई, ऍम, इज़, द, इन, टू, वांट, कैन, व्हाट, यस, प्लीज़. If the grammar words are English, the sentence is English.
- Understanding the answer is not a reason to stay. When an answer arrives in English, do both in the same response: act on it with its tool, AND call switch_language with English, and speak English from then on.

SURE, OR NOT SURE
- Sure — they asked for a language, or a whole sentence is plainly in another one: call switch_language at once, in that turn, without asking and without a word of your own.
- Not sure — a few words look like another language but the rest does not, or the turn is too short to tell: do NOT switch yet. Answer in the current language, and end with one short question in BOTH languages: "क्या हम हिंदी में बात करें? Shall we talk in Hindi?". On a yes in either language, call switch_language. Ask this at most once per language; if they say no, stay.
- This works in every direction, English included. Never stay in a language they have left.
- What does NOT count as switching: one borrowed English word inside a sentence in another language ("मुझे vaccination बुक करना है" is still Hindi). Judge by the whole sentence.
- If they ask for a language not listed (Urdu, Odia…), say in the current language that you can continue in Hindi or English, and ask which.
- Speak the visitor's language in its own script — Devanagari for Hindi and Marathi, Tamil script for Tamil, and so on — English loan words included: अपॉइंटमेंट, वैक्सीनेशन, क्लिनिक. Never write an Indian language in the Latin alphabet; the voice reads Latin as English.
- Tushar is a man. In languages that mark the speaker's gender on the verb — Hindi, Marathi, Punjabi, Gujarati — use the male forms: "मैं देख रहा हूँ", never "देख रही हूँ".
- The website follows you into Hindi by itself. In any other language it stays in English — speak theirs and never read the page out or translate it to make up for it. Branch names, service names and times can stay as they are on screen.
- Everything you are told — the page, a tool's reply, an article's facts — is written in English. Say it in the conversation's language.

STYLE:
- This is voice. One or two short sentences, never more than three. One question at a time.
- Warm and reassuring — people calling a vet are often worried about their pet.
- Never read ids aloud. Say times naturally ("half past ten", "four PM").
- Never invent branches, services, prices, doctors or articles. If it is not above, say the branch will help on the call."""


# ─── Actions (screen-driving payloads) ─────────────────────────────────────────


class Navigate(Action):
    page: Page


class ShowBranches(Action):
    city: str


class OpenArticle(Action):
    article_id: str


class LanguageChanged(Action):
    language: LanguageName
    screen_language: Literal["en", "hi"]


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

    city: str = Field(default="", description="The visitor's city if known, else empty.")


class SwitchLanguage(BaseModel):
    """What ``switch_language`` asks the model for."""

    language: LanguageName = Field(description="The language to continue in.")


async def _silence() -> AsyncGenerator[Any, None]:
    """Yields nothing: an idle tick the desk has no reason to answer."""
    for _ in ():
        yield


class PetwellBrain(GeminiBrain):
    """One per session. Owns this visitor's booking so far and the call's
    language; the inherited tool loop runs each turn, each tool below drives the
    page, and ``on_rtvi`` folds the visitor's own clicks in — see the module
    docstring."""

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
        self.language: LanguageName = "English"
        self.visit_type: VisitType = "clinic"
        self.city: str | None = None
        self.branch_id: str | None = None
        self.service_id: str | None = None
        self.date: str | None = None
        self.time: str | None = None
        # A switch the model asked for, made after its turn (see ``_switch_now``).
        self._switch_due: LanguageName | None = None
        # Set when a click wants answering; paid on the next idle tick.
        self._owed_a_reply = False
        self._fallback = FallbackLine()

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        """The tools the desk may call. Only ``show_slots`` is marked
        ``@needs_result_now``: see the module docstring."""
        return [
            self.navigate,
            self.show_branches,
            self.open_article,
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
            self.switch_language,
        ]

    def _landed(self, kind: Phrase, *english: str) -> None:
        """The lines that say a dispatch landed, in the call's language: the
        tool's own English lines in English, the shared written phrases in any
        other — a silent turn is never covered in a language being left."""
        if self.language == "English":
            landed(*english)
        else:
            landed(*phrase(LANGUAGE_CODE[self.language], kind))

    async def navigate(self, action: Navigate) -> str:
        """Open a page of the website: home, services, locations, health_hub or
        at_home. Closes the booking panel if it is open."""
        logger.info("petwell: navigate {}", action.page)
        self.session.dispatch(action)
        self._landed("shown", "Here you go.", "This is that page.")
        return str({"status": "shown", "page": action.page})

    async def show_branches(self, action: ShowBranches) -> str:
        """Open the locations page with one city's branches picked out. For
        browsing — to book, use the booking flow."""
        city = as_city(action.city)
        if city is None:
            return f"error: we have no branch in {action.city!r}"
        logger.info("petwell: show_branches {}", city)
        self.session.dispatch(ShowBranches(city=city))
        self._landed("shown", f"Here are our branches in {city}.")
        if city in OPENING_SOON:
            return str({"status": "shown", "city": city, "note": "opening soon"})
        names = [b["name"] for b in branches_in(city)]
        return str({"status": "shown", "city": city, "branches": names})

    async def open_article(self, action: OpenArticle) -> str:
        """Open a Health Hub article on the visitor's screen. Answer from its
        facts in the same response."""
        article = get_article(action.article_id)
        if article is None:
            return f"error: no article {action.article_id!r}"
        logger.info("petwell: open_article {}", action.article_id)
        self.session.dispatch(action)
        self._landed("shown", "Here's our article on that.", "I've opened the article.")
        return str({"status": "opened", "title": article["title"], "books": article["service_id"]})

    async def start_booking(self, action: StartBooking) -> str:
        """Open the booking panel: 'clinic' for a visit to a branch, 'home' for a
        vet at home. Shows the location step."""
        logger.info("petwell: start_booking {}", action.visit_type)
        self.visit_type = action.visit_type
        current = get_service(self.service_id or "")
        if current is not None and current["visit"] != action.visit_type:
            self.service_id = None
        self.session.dispatch(action)
        if action.visit_type == "home":
            self._landed("over_to_you", "A vet at home — which city are you in?")
        else:
            self._landed("over_to_you", "A clinic visit — which city are you in?")
        return str({"status": "started", "visit_type": action.visit_type})

    async def choose_city(self, action: ChooseCity) -> str:
        """Select the visitor's city in the booking panel and show its branches."""
        city = as_city(action.city)
        if city is None:
            return f"error: we have no branch in {action.city!r}"
        logger.info("petwell: choose_city {}", city)
        self.city = city
        self.branch_id = None
        self.session.dispatch(ChooseCity(city=city))
        if city in OPENING_SOON:
            self._landed(
                "over_to_you", f"Our {city} hospital is opening soon — could another city work?"
            )
            return str({"status": "opening_soon", "city": city})
        branches = branches_in(city)
        self._landed("over_to_you", f"{city} — which branch is closest?")
        return str({"status": "shown", "city": city, "branches": [b["name"] for b in branches]})

    async def choose_branch(self, action: ChooseBranch) -> str:
        """Select the branch for the visit and move on to the reason."""
        branch = get_branch(action.branch_id)
        if branch is None:
            return f"error: unknown branch {action.branch_id!r}"
        if branch["city"] in OPENING_SOON:
            return f"error: {branch['name']} is opening soon and not taking appointments"
        logger.info("petwell: choose_branch {}", action.branch_id)
        self.city = branch["city"]
        self.branch_id = branch["id"]
        self.session.dispatch(action)
        self._landed("over_to_you", f"{branch['name']} it is. What's the visit for?")
        return str({"status": "selected", "branch": branch["name"]})

    async def choose_service(self, action: ChooseService) -> str:
        """Select the reason for the visit and move on to picking a day and time."""
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
        self._landed("over_to_you", f"{service['name']}. Which day works for you?")
        return str({"status": "selected", "service": service["name"]})

    @needs_result_now
    async def show_slots(self, query: SlotQuery) -> str:
        """Show one day's free times at the chosen branch and return them. You
        get them straight away, so say a short line with the call and offer two
        or three of the returned times after it."""
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
        """Pick the day and time the visitor chose and move on to their details."""
        if self.branch_id is None:
            return "error: choose a branch first"
        if action.time not in slots_for(self.branch_id, action.date, self.visit_type):
            return (
                f"error: {action.time} on {action.date} is not free — "
                "offer a time show_slots returned"
            )
        logger.info("petwell: choose_slot {} {}", action.date, action.time)
        self.date, self.time = action.date, action.time
        self.session.dispatch(action)
        self._landed("over_to_you", "Got it. May I have your name and your pet's name?")
        return str({"status": "selected", "date": action.date, "time": action.time})

    async def fill_details(self, action: FillDetails) -> str:
        """Fill the owner's and pet's details into the booking form. Pass only
        the fields you learned; empty fields are left as they are."""
        filled = {k: v for k, v in action.model_dump().items() if v}
        logger.info("petwell: fill_details {}", sorted(filled))
        self.session.dispatch(action)
        self._landed("done", "Noted.", "Got that down.")
        return str({"status": "filled", "fields": sorted(filled)})

    async def show_review(self) -> str:
        """Show the booking summary with the Send Request button. Call once the
        owner's name, pet's name and phone are in, in the same response that asks
        the visitor to check it and tap Send Request."""
        logger.info("petwell: show_review")
        self.session.dispatch(ShowReview())
        self._landed(
            "over_to_you",
            "Here's your booking. Please check it and tap Send Request.",
            "All set — have a look and tap Send Request.",
        )
        return str({"status": "review_shown"})

    async def show_emergency(self, query: EmergencyQuery) -> str:
        """Open the emergency panel: the helpline for the visitor's region and
        the 24x7 emergency branches in their city. Use instead of booking when
        the pet is in danger right now."""
        city = as_city(query.city) or ""
        line = helpline_for(city) if city else None
        er = [b["id"] for b in branches_in(city) if b["emergency"]] if city else []
        logger.info("petwell: show_emergency city={!r}", city)
        self.session.dispatch(
            ShowEmergency(city=city, helpline=line["phone"] if line else "", branch_ids=er)
        )
        self._landed(
            "shown",
            "Please come to our nearest emergency branch now — the number is on your screen.",
        )
        return str(
            {
                "status": "emergency_shown",
                "helpline": line["phone"] if line else "see screen for all regions",
                "emergency_branches": [b["name"] for b in branches_in(city) if b["emergency"]],
            }
        )

    async def go_home(self) -> str:
        """Clear the booking and go back to the home page."""
        logger.info("petwell: go_home")
        self.city = self.branch_id = self.service_id = self.date = self.time = None
        self.session.dispatch(GoHome())
        self._landed("shown", "Back to the start.")
        return str({"status": "home"})

    async def switch_language(self, to: SwitchLanguage) -> str:
        """Continue the conversation in another language — the listening and the
        speaking both, and the website too if it is Hindi.

        Call it when the visitor asks for a language, AND when you can tell they
        are already speaking one. Call it alone, with no words: the desk says the
        switch line itself, in the new language, once the voice has changed.
        Speak the new language from their next turn."""
        if to.language == self.language:
            return f"Already in {to.language}."
        # Not sent here: a tool returns inside its budget, and the line has to
        # wait for the new voice. ``_switch_now`` moves both legs after the turn.
        self._switch_due = to.language
        return (
            f"Switching to {to.language}; the desk tells them so in {to.language}. "
            f"Speak {to.language} from here on."
        )

    # ─── Language ───────────────────────────────────────────────────────

    async def _switch_to(self, name: LanguageName, *, by: str) -> str:
        """Move both legs to one language, from a callback rather than a tool —
        awaited, so it lands before the next word is spoken."""
        if name == self.language:
            return f"Already in {name}. Carry on."
        try:
            await self.session.configure(config_for(name))
        except RequestRejected as rejected:
            logger.warning("petwell: language {} rejected — {}", name, rejected)
            return (
                f"Refused — the desk is still in {self.language}. "
                f"Tell the visitor, in {self.language}, that you cannot speak {name} here."
            )
        logger.info("petwell: language {} -> {} (by {})", self.language, name, by)
        self.language = name
        self.session.dispatch(
            LanguageChanged(language=name, screen_language=screen_language_for(name))
        )
        return f"Now in {name}, switched by {by}. Speak {name} from here on."

    async def _switch_now(self) -> AsyncGenerator[Speech, None]:
        """After the model's turn: move both legs, then say so in the new language.

        The model writes before the voice changes, so a switch line of its own
        would be heard in the language being left. So the tool only asks, and
        the line is written, and spoken here once the new voice is on."""
        name = self._switch_due
        if name is None:
            return
        self._switch_due = None
        note = await self._switch_to(name, by="you")
        if self.language != name:
            self._append_note(note)
            return
        async for speech in self._say(SWITCH_LINE[name]):
            yield speech

    async def _say(self, line: str) -> AsyncGenerator[Speech, None]:
        """Speak a written line and keep it in the context as Tushar's own, so the
        model knows what he has already said."""
        unit = _Unit(types.Content(role="model", parts=[types.Part(text=line)]))
        self._history.append(unit.content)  # pyright: ignore[reportPrivateUsage]
        self._awaiting.append(unit)  # pyright: ignore[reportPrivateUsage]
        yield SpeechStart()
        yield SpeechChunk(line)
        yield SpeechEnd()

    def _append_note(self, text: str) -> None:
        """One line in front of the model, without taking the floor."""
        self.append_to_context(types.Content(role="user", parts=[types.Part(text=text)]))

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        """Open in the language the visitor picked on the page — English or
        Hindi — and move both legs there before the greeting is spoken. Gaurav,
        the voice, is the first the avatar runtime suggests for `tushar`, the face
        the page mounts — one person, heard and seen."""
        chosen = as_language(dict(session.init or {}).get("language"))
        self.language = chosen if chosen in GREETING else "English"
        await session.configure(config_for(self.language))

    async def greet(self, session: Session) -> str:
        """The opener is fixed — no model call — so the visitor hears the desk the
        instant the session connects, in the page's language."""
        return GREETING[self.language]

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The model's turn and any switch it asked for — and, when the turn moved
        the screen and said nothing, the line of the last call that landed. No
        second model request."""
        async for event in self._fallback.speak_if_silent(self, self._model_turn(session)):
            yield event

    async def _model_turn(self, session: Session) -> AsyncGenerator[Speech, None]:
        """Inside the fallback's watch, so a turn that switched in silence — as the
        prompt asks — is not also given a fallback line in the language being left."""
        async for event in super().respond(session):
            yield event
        async for event in self._switch_now():
            yield event

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[Speech, None]:
        """One spoken turn — with a plain change of language caught before the
        model sees it, so its reply is spoken by the right voice.

        A recognizer writes every language in its own script: English spoken to
        the Hindi one comes out as English in Devanagari, Hindi spoken to the
        English one as Hindi in English letters. The plain cases are decided here
        (:func:`reads_as_english`, :func:`reads_as_latin_hindi`)."""
        self._owed_a_reply = False
        if self.language != "English" and reads_as_english(msg.text):
            self._append_note(await self._switch_to("English", by="the desk, which heard English"))
        elif self.language == "English" and reads_as_latin_hindi(msg.text):
            self._append_note(await self._switch_to("Hindi", by="the desk, which heard Hindi"))
        self.append_to_context(types.Content(role="user", parts=[types.Part(text=msg.text)]))
        async for speech in self.respond(session):
            yield speech

    def on_user_idle(self, session: Session, idle: UserIdle) -> AsyncGenerator[Speech, None]:
        """The visitor has gone quiet. A booking click or Send Request is
        answered with the next step; anything else — a visitor reading — with
        silence."""
        if not self._owed_a_reply:
            return _silence()
        self._owed_a_reply = False
        logger.info("petwell: idle -> answering what the visitor clicked")
        return self.respond(session)

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """A click on the website. Folded into the context without taking the
        floor; :meth:`on_user_idle` answers the ones that want answering."""
        event = PETWELL_EVENTS.parse(msg)
        if event is None:
            return
        applied = self.apply_event(event)
        if applied is None:
            return
        note, owed = applied
        self._append_note(note)
        self._owed_a_reply = self._owed_a_reply or owed

    # ─── Browser → brain ────────────────────────────────────────────────

    def apply_event(self, event: PetwellEvent) -> tuple[str, bool] | None:
        """Bring the desk up to date with a click: the note the model reads next,
        and whether it is owed a reply. ``None`` for a click naming nothing real."""
        carry_on = "Carry on with the next step."
        match event:
            case PagePicked():
                return (f"[The visitor opened the {event.page.replace('_', ' ')} page.]", False)
            case ArticleOpened():
                article = get_article(event.article_id)
                if article is None:
                    return None
                return (f"[The visitor is reading the article: {article['title']}.]", False)
            case BookingOpened():
                service = get_service(event.service_id)
                if service is not None:
                    self.service_id = service["id"]
                    self.visit_type = service["visit"]
                    return (
                        f"[The visitor opened the booking panel to book {service['name']}.] "
                        "Ask what you still need, starting with their city.",
                        True,
                    )
                return (
                    "[The visitor opened the booking panel.] Ask clinic visit or home visit.",
                    True,
                )
            case VisitTypePicked():
                self.visit_type = event.visit_type
                kind = "a vet at home" if event.visit_type == "home" else "a clinic visit"
                return (f"[The visitor tapped {kind}.] {carry_on}", True)
            case CityPicked():
                city = as_city(event.city)
                if city is None:
                    return None
                self.city, self.branch_id = city, None
                return (f"[The visitor tapped {city}.] {carry_on}", True)
            case BranchPicked():
                branch = get_branch(event.branch_id)
                if branch is None:
                    return None
                self.city, self.branch_id = branch["city"], branch["id"]
                return (f"[The visitor tapped the {branch['name']} branch.] {carry_on}", True)
            case ServicePicked():
                service = get_service(event.service_id)
                if service is None:
                    return None
                self.service_id = service["id"]
                return (f"[The visitor tapped {service['name']}.] {carry_on}", True)
            case SlotPicked():
                self.date, self.time = event.date, event.time
                return (f"[The visitor tapped {event.time} on {event.date}.] {carry_on}", True)
            case AppointmentRequested():
                logger.info("petwell: appointment_requested ref={}", event.ref)
                branch = get_branch(self.branch_id or "")
                where = branch["name"] if branch else "the branch"
                return (
                    f"[The visitor tapped Send Request. Reference {event.ref}.] Next time you "
                    f"speak, read the reference out clearly, say {where} will call "
                    f"{event.owner_name or 'them'} shortly to confirm, and wish "
                    f"{event.pet_name or 'their pet'} well. Two sentences.",
                    True,
                )
