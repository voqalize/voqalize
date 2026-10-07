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
    UserMessage,
)
from voqalize.sdk.gemini import _Unit  # pyright: ignore[reportPrivateUsage]

from .app_events import (
    PETWELL_EVENTS,
    AppointmentRequested,
    ArticleOpened,
    BookingClosed,
    BookingOpened,
    BookingRestarted,
    BranchesBrowsed,
    BranchPicked,
    CityPicked,
    DatePicked,
    DetailEdited,
    EmergencyClosed,
    EmergencyOpened,
    Page,
    PagePicked,
    PetwellEvent,
    ReviewOpened,
    ServicePicked,
    SlotPicked,
    StepOpened,
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
    LANGUAGE_CODE,
    NEXT_QUESTION,
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

# After the language moves, how many of the visitor's turns pass before the
# desk's own checks may move it again. Indian speech mixes English into every
# language; one mixed sentence is not a request to switch back.
_SETTLE_TURNS = 2

#: The form's fields as a person says them.
_FIELD_NAME = {
    "owner_name": "owner name",
    "pet_name": "pet name",
    "pet_type": "pet type",
    "phone": "phone",
    "email": "email",
    "address": "address",
    "notes": "message",
}

_STEP_NAME = {
    "city": "LOCATION — choose the city",
    "branch": "LOCATION — choose the branch",
    "service": "REASON — choose the reason for the visit",
    "slot": "DAY AND TIME — choose a free time",
    "details": "DETAILS — owner name, pet name, phone",
    "review": "REVIEW — waiting for the visitor to tap Send Request",
}


def _not_done(why: str, ask: str) -> str:
    """A refused tool call, worded so it cannot be glossed over in speech."""
    return f"NOT DONE — {why}. Nothing changed on screen; do not say it was done. {ask}"


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

SAY WHAT YOU HAVE DONE. Whenever you tell the visitor something is selected, chosen, opened or booked, its tool call is in that same response. To move the booking on, call the tool and say the line with it; to find out what you still need, ask the question. Before every turn you are shown a [SCREEN NOW …] line: it is the truth about the page, and you continue from exactly there — a field marked NOT CHOSEN is the next thing to ask about or select. When a tool answers NOT DONE, tell the visitor what is still needed and ask for it. When the visitor says the screen has not changed, go by the SCREEN NOW line.

THE VISITOR CAN ALSO USE THE PAGE THEMSELVES. Their clicks and typing reach you as [The visitor …] lines and in SCREEN NOW. Someone driving the page is getting on with it on their own: you reply only when they speak to you, and then you continue from exactly where they are — using what they have already typed or picked, and asking only for what is still missing.

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

THE BOOKING FLOW — it happens in a booking panel over the page. Ask one question at a time, and put each answer on screen the moment you hear it:
1. BOOKING ANSWERS — visit type, city, branch and reason. Each time the visitor gives any of them, call update_booking with ALL the answers you know so far, in the same response as your line. It opens the panel and moves the screen through each step; a city with one branch gets its branch selected too. Its reply says what is on screen and what is next — continue from there.
   - Visit type: a clinic visit, or a vet at home (vaccination, minor illness or injury, blood sample, physiotherapy).
   - City and branch: Kolkata is opening soon, so offer one of the other cities. In a city with several branches, name them by area and ask which is closest. A home visit is sent from the nearest branch.
   - Reason: map what they describe to one service — clinic visits use Everyday or Specialty care, home visits the At home services. If it is unclear, ask one short question.
2. DAY AND TIME: call show_slots for the day they want (today if "as soon as possible"), offer two or three of the free times it returns, then call choose_slot with the one they pick. Never offer a time show_slots did not return.
3. DETAILS: the form needs the owner's name, the pet's name and kind of pet, a phone number, and a message for the vet (a sentence about why they are coming) — for a home visit, the address or locality too; email is optional. Ask for one or two at a time, starting with whatever SCREEN NOW lists as still needed. Call fill_details each time you learn something, with only the fields you learned. Read phone numbers back in groups to confirm.
4. REVIEW: once SCREEN NOW lists no details still needed, call show_review and ask them to check the summary and tap Send Request. Then wait for them. When the request is sent you will see its reference in SCREEN NOW — if they ask, read it out and say the branch will call to confirm.

EMERGENCIES COME FIRST. If the pet is bleeding heavily, not breathing, collapsed, having a seizure, hit by a vehicle, or has eaten poison, do NOT book. Call show_emergency with their city (if known) in the same response as a short, calm line: give the helpline for their region and tell them to come straight to the nearest 24x7 emergency branch now.

LANGUAGE — it switches by itself; nobody picks a language on the page
- You speak {languages}. You start in English. The visitor may speak English or any of these, and may change their mind at any point. The call is always in the language they are speaking, whatever the turn is — a request, a question or an answer. The moment they ask for a language, OR you can tell they are already speaking one, call switch_language with it — and call it ALONE, with no words at all. This is the one call that goes without a line: your voice is still in the old language when you write, so anything you say would come out in that one. The desk says the line itself, in the new language, once the voice has changed. Speak the new language from their next turn on. When you are sure, do not ask permission first; when you are not, see SURE, OR NOT SURE below.
- switch_language is the one silent call. Every other response, in every language, opens with your spoken line in the visitor's language and then makes its calls — for example, in Tamil: "சரி, ஹைதராபாத் ஜூபிலி ஹில்ஸ் கிளையைத் தேர்வு செய்கிறேன். எதற்காக வருகிறீர்கள்?" with update_booking; in Hindi: "ठीक है, पवई ब्रांच चुन रहा हूँ। किस लिए आना है?" with update_booking.

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
- Indian speech mixes English into every language ("mera dog ka appointment", "naan doctor-a paakanum"). Mixing is NOT a switch: stay in the current language. Once you have switched away from English, stay in that language unless the visitor asks for another one or speaks whole sentences in it for two turns in a row.
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


class BookingUpdate(BaseModel):
    """What ``update_booking`` asks the model for: every booking answer known so
    far. Leave a field empty only when the visitor has not said it yet."""

    visit_type: Literal["clinic", "home", ""] = Field(
        default="", description="'clinic' or 'home' once known, else empty."
    )
    city: str = Field(
        default="", description="A city from the BRANCHES list once known, else empty."
    )
    branch_id: str = Field(
        default="", description="A branch id from the BRANCHES list once chosen, else empty."
    )
    service_id: str = Field(
        default="", description="A service id from SERVICES once the reason is clear, else empty."
    )


class SlotQuery(BaseModel):
    """What ``show_slots`` asks the model for."""

    date: str = Field(description="ISO date from the DATES list, e.g. 2026-10-07.")


class EmergencyQuery(BaseModel):
    """What ``show_emergency`` asks the model for."""

    city: str = Field(default="", description="The visitor's city if known, else empty.")


class SwitchLanguage(BaseModel):
    """What ``switch_language`` asks the model for."""

    language: LanguageName = Field(description="The language to continue in.")


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
        # The rest of what is on screen, kept from the brain's own dispatches and
        # the page's events. It is the ground truth the model is shown in front of
        # every turn (``screen_now``): a model that said "I've selected Powai"
        # without calling the tool is told, next turn, that no branch is chosen.
        self.page: str = "home"
        self.panel_open = False
        # The form, field by field, as the screen holds it — typed by the visitor
        # (``DetailEdited``) or filled by the desk (``fill_details``).
        self.details: dict[str, str] = {}
        # The step the visitor went back to look at, until the booking moves on.
        self.viewing: str | None = None
        self.emergency_open = False
        self.review_shown = False
        self.sent_ref: str | None = None
        # A switch the model asked for, made after its turn (see ``_switch_now``).
        self._switch_due: LanguageName | None = None
        # The visitor's turns since the language last moved; the automatic checks
        # wait two turns after a switch, so code-mixed speech cannot flap it.
        self._turns_in_language = _SETTLE_TURNS
        # The switch line, when the desk's own check moved the language before the
        # model ran: said if the model's turn then says nothing.
        self._switch_line_due: str | None = None
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
            self.update_booking,
            self.show_slots,
            self.choose_slot,
            self.fill_details,
            self.show_review,
            self.show_emergency,
            self.go_home,
            self.switch_language,
        ]

    def _reset_booking(self) -> None:
        """The booking panel starts over — as the page's own reset does, which
        puts the visit type back to a clinic visit too."""
        self.visit_type = "clinic"
        self.city = self.branch_id = self.service_id = None
        self._clear_slot()
        self.details = {}
        self.viewing = None
        self.sent_ref = None

    def _clear_slot(self) -> None:
        """The day and time no longer hold — the branch, visit or reason moved, or
        another day's times are on screen. The page clears its own the same way."""
        self.date = self.time = None
        self.review_shown = False

    def _free_times(self, branch_id: str, day: dt.date) -> list[str]:
        """The times still free at ``branch_id`` on ``day`` — none already past,
        when ``day`` is today. Both what show_slots offers and what choose_slot
        accepts."""
        times = slots_for(branch_id, day.isoformat(), self.visit_type)
        if day == self._today:
            now = dt.datetime.now(_IST).strftime("%H:%M")
            times = [t for t in times if t > now]
        return times

    def booking_step(self) -> str | None:
        """The step the booking panel is on, or ``None`` when it is closed."""
        if not self.panel_open:
            return None
        if self.sent_ref:
            return "sent"
        if self.city is None:
            return "city"
        if self.branch_id is None:
            return "branch"
        if self.service_id is None:
            return "service"
        if self.time is None:
            return "slot"
        return "review" if self.review_shown else "details"

    def missing_details(self) -> list[str]:
        """The form fields the review still needs — the page's required ones."""
        needed = ["owner_name", "pet_name", "phone", "notes"]
        if self.visit_type == "home":
            needed.append("address")
        return [_FIELD_NAME[f] for f in needed if not self.details.get(f, "").strip()]

    def screen_now(self) -> str:
        """One line of ground truth, put in front of the model every turn: what
        the website actually shows, kept from what landed — not from what was
        said. Anything missing from it has not happened."""
        page = self.page
        if page.startswith("article:"):
            article = get_article(page.removeprefix("article:"))
            page = f"Health Hub article '{article['title'] if article else page}'"
        parts = [f"page: {page.replace('_', ' ')}"]
        step = self.booking_step()
        if step is None:
            parts.append("booking panel: CLOSED")
        elif step == "sent":
            parts.append(f"booking: request SENT, reference {self.sent_ref}")
        else:
            branch = get_branch(self.branch_id or "")
            service = get_service(self.service_id or "")
            parts += [
                f"booking panel OPEN at step {_STEP_NAME[step]}",
                f"visit: {'vet at home' if self.visit_type == 'home' else 'clinic visit'}",
                f"city: {self.city or 'NOT CHOSEN'}",
                f"branch: {branch['name'] if branch else 'NOT CHOSEN'}",
                f"reason: {service['name'] if service else 'NOT CHOSEN'}",
                f"day and time: {f'{self.date} {self.time}' if self.time else 'NOT CHOSEN'}",
            ]
            filled = [f"{_FIELD_NAME[k]} '{v}'" for k, v in self.details.items() if v.strip()]
            parts.append(f"details on the form: {', '.join(filled) or 'none yet'}")
            if step in ("details", "review"):
                missing = self.missing_details()
                parts.append(f"details still needed: {', '.join(missing) or 'none'}")
            # The page names its steps visit/location/service/slot/details/review;
            # the desk splits location into city and branch.
            page_step = {"city": "location", "branch": "location"}.get(step, step)
            if self.viewing and self.viewing != page_step:
                parts.append(f"the visitor has gone back to look at the {self.viewing} step")
        if self.emergency_open:
            parts.append("the emergency sheet is OPEN")
        return (
            "[SCREEN NOW — what the website actually shows. Anything not listed here has "
            "NOT happened; make it happen with its tool before you say it is done. "
            + " · ".join(parts)
            + "]"
        )

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
        self.page, self.panel_open = action.page, False
        self.session.dispatch(action)
        self._landed("shown", "Here you go.", "This is that page.")
        return str({"status": "shown", "page": action.page})

    async def show_branches(self, action: ShowBranches) -> str:
        """Open the locations page with one city's branches picked out. For
        browsing — to book, use the booking flow."""
        city = as_city(action.city)
        if city is None:
            return _not_done(
                f"Petwell has no branch in {action.city!r}",
                "Say so, and name only cities from the BRANCHES list.",
            )
        logger.info("petwell: show_branches {}", city)
        self.page, self.panel_open = "locations", False
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
            return _not_done(
                f"there is no article {action.article_id!r}", "Use an id from the list."
            )
        logger.info("petwell: open_article {}", action.article_id)
        self.page, self.panel_open = f"article:{article['id']}", False
        self.session.dispatch(action)
        self._landed("shown", "Here's our article on that.", "I've opened the article.")
        return str({"status": "opened", "title": article["title"], "books": article["service_id"]})

    async def update_booking(self, update: BookingUpdate) -> str:
        """Put the visitor's booking answers on screen — visit type, city, branch
        and reason — in this one call, with every answer you know so far. It opens
        the booking panel and moves the screen through each step; a city with one
        branch has that branch selected too. Call it whenever the visitor tells
        you any of these, in the same response as your line. It answers with what
        is on screen now and what is still needed."""
        before = (self.visit_type, self.city, self.branch_id, self.service_id)
        refused: list[str] = []

        if update.visit_type and update.visit_type != self.visit_type:
            self.visit_type = update.visit_type
            current = get_service(self.service_id or "")
            if current is not None and current["visit"] != self.visit_type:
                self.service_id = None

        if update.branch_id:
            branch = get_branch(update.branch_id)
            if branch is None:
                refused.append(f"no branch {update.branch_id!r} — use a branch id from the list")
            elif branch["city"] in OPENING_SOON:
                refused.append(f"{branch['name']} is opening soon — offer another city")
            else:
                self.city, self.branch_id = branch["city"], branch["id"]
        elif update.city:
            city = as_city(update.city)
            if city is None:
                refused.append(
                    f"Petwell has no branch in {update.city!r} — offer the nearest Petwell city"
                )
            elif city != self.city:
                self.city, self.branch_id = city, None
                if city in OPENING_SOON:
                    refused.append(
                        f"{city} is shown on screen with its opening-soon note, but it cannot "
                        "be booked yet — offer another city"
                    )

        # A city with one branch has nothing to ask: select it now.
        if self.city and self.branch_id is None and self.city not in OPENING_SOON:
            only = branches_in(self.city)
            if len(only) == 1:
                self.branch_id = only[0]["id"]

        if update.service_id:
            service = get_service(update.service_id)
            if service is None:
                refused.append(f"no service {update.service_id!r} — use a service id from the list")
            elif service["visit"] != self.visit_type:
                refused.append(
                    f"{service['name']} is a {service['visit']} service and this booking is a "
                    f"{self.visit_type} visit — pass visit_type '{service['visit']}' with it, "
                    "or pick a reason that fits"
                )
            else:
                self.service_id = service["id"]

        after = (self.visit_type, self.city, self.branch_id, self.service_id)
        if after != before:
            # A changed booking needs a new time; the page drops its own the same way.
            self._clear_slot()
        if after != before or (not self.panel_open and after[1:] != (None, None, None)):
            self._show_booking(visit_changed=after[0] != before[0])
        elif not self.panel_open and update.visit_type:
            self._show_booking(visit_changed=True)

        logger.info(
            "petwell: update_booking {} → {} (refused {})",
            update.model_dump(exclude_defaults=True),
            after,
            len(refused),
        )
        return self._booking_result(refused)

    def _show_booking(self, *, visit_changed: bool) -> None:
        """Bring the page's booking panel to what the desk holds, step by step.

        The page's own setters each move it one step (a city shows its branches,
        a branch moves to the reason, a reason with a branch moves to the times),
        so the whole state is replayed in that order and the panel lands where the
        desk is. Starting the booking closes the emergency sheet, as on the page."""
        opening = not self.panel_open
        self.panel_open, self.review_shown = True, False
        if opening or visit_changed:
            self.emergency_open = False
            self.session.dispatch(StartBooking(visit_type=self.visit_type))
        if self.city:
            self.session.dispatch(ChooseCity(city=self.city))
        if self.branch_id:
            self.session.dispatch(ChooseBranch(branch_id=self.branch_id))
        if self.service_id:
            self.session.dispatch(ChooseService(service_id=self.service_id))
        branch = get_branch(self.branch_id or "")
        service = get_service(self.service_id or "")
        step = self.booking_step() or ""
        if self.language != "English":
            # The visitor hears the next question in their own language.
            question = NEXT_QUESTION[self.language].get(step)
            if question:
                landed(question)
            else:
                self._landed("over_to_you")
            return
        match step:
            case "city":
                self._landed("over_to_you", "Which city are you in?")
            case "branch":
                self._landed("over_to_you", f"{self.city} — which branch is closest?")
            case "service" if branch:
                self._landed("over_to_you", f"{branch['name']} it is. What's the visit for?")
            case "slot" if service:
                self._landed("over_to_you", f"{service['name']}. Which day works for you?")
            case _:
                self._landed("over_to_you", "Done.")

    def _booking_result(self, refused: list[str]) -> str:
        """What ``update_booking`` answers: the booking as the screen shows it, the
        next thing to ask, and anything it could not do."""
        branch = get_branch(self.branch_id or "")
        service = get_service(self.service_id or "")
        step = self.booking_step()
        result: dict[str, object] = {
            "on screen now": {
                "visit": "vet at home" if self.visit_type == "home" else "clinic visit",
                "city": self.city or "NOT CHOSEN",
                "branch": branch["name"] if branch else "NOT CHOSEN",
                "reason": service["name"] if service else "NOT CHOSEN",
            },
            "next": _STEP_NAME.get(step or "", "open the booking with update_booking"),
        }
        if step == "branch" and self.city:
            result["branches to offer"] = {b["id"]: b["name"] for b in branches_in(self.city)}
        if refused:
            result["NOT DONE"] = refused
            result["note"] = (
                "The items under NOT DONE are not part of the booking. "
                "Tell the visitor what is still needed and ask for it."
            )
        return str(result)

    @needs_result_now
    async def show_slots(self, query: SlotQuery) -> str:
        """Show one day's free times at the chosen branch and return them. You
        get them straight away, so say a short line with the call and offer two
        or three of the returned times after it."""
        if self.branch_id is None:
            return _not_done("no branch is chosen yet", "Ask which branch first.")
        try:
            day = dt.date.fromisoformat(query.date)
        except ValueError:
            return _not_done(f"{query.date!r} is not an ISO date", "Use a date from the list.")
        if day not in booking_dates(self._today):
            return _not_done(
                "that day is outside the booking window",
                "Offer a day from today up to six days ahead.",
            )
        times = self._free_times(self.branch_id, day)
        logger.info("petwell: show_slots {} {} → {}", self.branch_id, day, len(times))
        # The page's slot step drops any chosen time when it shows a day's times.
        self._clear_slot()
        self.date = day.isoformat()
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
            return _not_done("no branch is chosen yet", "Ask which branch first.")
        try:
            day = dt.date.fromisoformat(action.date)
        except ValueError:
            return _not_done(f"{action.date!r} is not an ISO date", "Use a date from the list.")
        if day not in booking_dates(self._today) or action.time not in self._free_times(
            self.branch_id, day
        ):
            return _not_done(
                f"{action.time} on {action.date} is not free",
                "Call show_slots for that day and offer only the times it returns.",
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
        self.details.update(filled)
        self.session.dispatch(action)
        self._landed("done", "Noted.", "Got that down.")
        return str({"status": "filled", "fields": sorted(filled)})

    async def show_review(self) -> str:
        """Show the booking summary with the Send Request button. Call once the
        owner's name, pet's name, phone and message are in (and the address, for a
        home visit), in the same response that asks the visitor to check it and
        tap Send Request."""
        missing = self.missing_details()
        if missing:
            return _not_done(
                f"the form still needs: {', '.join(missing)}",
                "Ask for these, put them in with fill_details, then show the review.",
            )
        logger.info("petwell: show_review")
        self.review_shown = True
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
        er = [b for b in branches_in(city) if b["emergency"]]
        logger.info("petwell: show_emergency city={!r}", city)
        self.emergency_open = True
        self.session.dispatch(
            ShowEmergency(
                city=city,
                helpline=line["phone"] if line else "",
                branch_ids=[b["id"] for b in er],
            )
        )
        self._landed(
            "shown",
            "Please come to our nearest emergency branch now — the number is on your screen.",
        )
        return str(
            {
                "status": "emergency_shown",
                "helpline": line["phone"] if line else "see screen for all regions",
                "emergency_branches": [b["name"] for b in er],
            }
        )

    async def go_home(self) -> str:
        """Clear the booking and go back to the home page."""
        logger.info("petwell: go_home")
        self._reset_booking()
        self.page, self.panel_open = "home", False
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
        self._turns_in_language = 0
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
        """Move both legs to the opening language before the greeting is spoken:
        English, unless the connect request names Hindi — the page sends none. Gaurav,
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
        if self._switch_line_due is not None:
            # Recorded as this turn's floor: spoken only if the model says nothing.
            landed(self._switch_line_due)
            self._switch_line_due = None
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
        self._turns_in_language += 1
        settled = self._turns_in_language > _SETTLE_TURNS
        was = self.language
        if settled and self.language != "English" and reads_as_english(msg.text):
            self._append_note(await self._switch_to("English", by="the desk, which heard English"))
        elif settled and self.language == "English" and reads_as_latin_hindi(msg.text):
            self._append_note(await self._switch_to("Hindi", by="the desk, which heard Hindi"))
        if self.language != was:
            self._switch_line_due = SWITCH_LINE[self.language]
        # Ground truth goes in front of the visitor's words, never after them.
        self._append_note(self.screen_now())
        self.append_to_context(types.Content(role="user", parts=[types.Part(text=msg.text)]))
        async for speech in self.respond(session):
            yield speech

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Something the visitor did on the page. The desk updates its picture
        of the screen and leaves one line for the model, and says nothing: a
        visitor driving the page is getting on with it. They hear from the desk
        when they next speak to it."""
        event = PETWELL_EVENTS.parse(msg)
        if event is None:
            return
        note = self.apply_event(event)
        if note is not None:
            logger.info("petwell: visitor {}", note)
            self._append_note(note)

    # ─── Browser → brain ────────────────────────────────────────────────

    def apply_event(self, event: PetwellEvent) -> str | None:
        """Bring the desk up to date with something the visitor did, and return
        the line the model reads next. ``None`` for an event naming nothing real.
        Nothing here asks for a reply: the visitor is driving."""
        match event:
            case PagePicked():
                self.page, self.panel_open = event.page, False
                return f"[The visitor opened the {event.page.replace('_', ' ')} page.]"
            case ArticleOpened():
                article = get_article(event.article_id)
                if article is None:
                    return None
                self.page, self.panel_open = f"article:{article['id']}", False
                return f"[The visitor opened the article: {article['title']}.]"
            case BranchesBrowsed():
                city = as_city(event.city)
                self.page, self.panel_open = "locations", False
                return f"[The visitor is looking at our branches in {city or 'every city'}.]"
            case BookingOpened():
                # The page starts the panel over; so does the desk.
                self._reset_booking()
                self.panel_open, self.emergency_open = True, False
                service = get_service(event.service_id)
                if service is not None:
                    self.service_id = service["id"]
                    self.visit_type = service["visit"]
                    return f"[The visitor opened the booking panel to book {service['name']}.]"
                return "[The visitor opened the booking panel.]"
            case BookingClosed():
                self.panel_open = False
                return "[The visitor closed the booking panel; what they chose is kept.]"
            case BookingRestarted():
                self._reset_booking()
                self.panel_open = True
                return "[The visitor started a new booking.]"
            case VisitTypePicked():
                if event.visit_type != self.visit_type:
                    self._clear_slot()
                    # The page drops a reason that does not fit the new visit type.
                    service = get_service(self.service_id or "")
                    if service is not None and service["visit"] != event.visit_type:
                        self.service_id = None
                self.visit_type = event.visit_type
                self.panel_open, self.emergency_open = True, False
                self.viewing = None
                kind = "a vet at home" if event.visit_type == "home" else "a clinic visit"
                return f"[The visitor chose {kind}.]"
            case CityPicked():
                city = as_city(event.city)
                if city is None:
                    return None
                if city != self.city:
                    self.branch_id = None
                    self._clear_slot()
                self.city, self.viewing = city, None
                return f"[The visitor chose the city {city}.]"
            case BranchPicked():
                branch = get_branch(event.branch_id)
                if branch is None:
                    return None
                if branch["id"] != self.branch_id:
                    self._clear_slot()
                self.city, self.branch_id, self.viewing = branch["city"], branch["id"], None
                return f"[The visitor chose the {branch['name']} branch.]"
            case ServicePicked():
                service = get_service(event.service_id)
                if service is None:
                    return None
                if service["id"] != self.service_id:
                    self._clear_slot()
                self.service_id, self.viewing = service["id"], None
                return f"[The visitor chose {service['name']} as the reason.]"
            case DatePicked():
                self.date, self.time = event.date, None
                return f"[The visitor is looking at the times on {event.date}.]"
            case SlotPicked():
                self.date, self.time, self.viewing = event.date, event.time, None
                return f"[The visitor chose {event.time} on {event.date}.]"
            case StepOpened():
                self.viewing = event.step
                self.review_shown = self.review_shown and event.step == "review"
                return f"[The visitor went back to the {event.step} step.]"
            case DetailEdited():
                self.details[event.field] = event.value
                label = _FIELD_NAME[event.field]
                if event.value.strip():
                    return f"[The visitor typed their {label}: '{event.value}'.]"
                return f"[The visitor cleared the {label} field.]"
            case ReviewOpened():
                self.review_shown, self.viewing = True, None
                return "[The visitor is checking the summary before Send Request.]"
            case AppointmentRequested():
                self.sent_ref = event.ref or "sent"
                branch = get_branch(self.branch_id or "")
                where = branch["name"] if branch else "the branch"
                return (
                    f"[The visitor tapped Send Request. Reference {self.sent_ref}. {where} will call "
                    f"{event.owner_name or 'them'} to confirm.]"
                )
            case EmergencyOpened():
                self.emergency_open = True
                return "[The visitor opened the 24x7 emergency sheet.]"
            case EmergencyClosed():
                self.emergency_open = False
                return "[The visitor closed the emergency sheet.]"
