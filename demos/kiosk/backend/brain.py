"""KioskBrain — Tanvi, the Vantage Bank branch-kiosk assistant.

A :class:`voqalize_demos.GeminiBrain`. A walk-in customer stands at a totem in a
private cubicle, answers four questions out loud, sees three cards ranked for
them, says yes to one, and takes a QR code to the desk. Fourteen turns, about
three and a half minutes, and nothing in it is approved: the kiosk has no tool
that can submit anything, and says so.

Vantage Bank is invented, and so is every card on its shelf.

Four things carry this demo:

* **The rules are Python.** ``check_eligibility`` and ``show_shortlist`` run the
  pure functions in ``eligibility.py``. The model resolves what the customer
  *said* into one of the closed tokens in ``cards.py``; it never compares an
  income to a threshold, because the times it gets that wrong are a bank telling
  a customer the wrong thing in a branch.

* **Two strings per figure.** Every tool here returns a ``SAY:`` line already in
  words, and the prompt tells Tanvi to speak it as written. The display form —
  ``₹1,50,000``, ``5%``, ``2x`` — goes to the screen and never to the voice.

* **The screen is read, never remembered.** Tanvi keeps one mirror of the totem,
  patched by :meth:`_show` on her own commands and by :meth:`apply_event` on the
  customer's taps. It is never appended to the context: what goes in is one line
  naming what they *did*, and the screen itself is read back through
  ``get_screen_context``. ``ScreenState.version`` makes that enforceable — a tool
  aimed at a card the customer has moved past refuses and says to read first.

* **The hand drives the same journey as the voice.** A customer may ignore
  Tanvi completely and tap their way from the attract loop to the QR code. Every
  gesture arrives as a typed event and the brain answers it by dispatching the
  next row of :meth:`KioskBrain._advance` — in Python, with no model call and no
  speech, because an action holds no floor. Tanvi greets once and then says
  nothing until she is spoken to; every gesture still leaves its one-line note, so
  the turn she finally takes has the whole visit behind it.

* **Confirmation is spoken, and it is asked once.** ``confirm`` decides yes or
  not-yes in Python and re-asks at most one time; a second unclear answer is
  taken as heard and the call moves on. Repeated "sorry, I didn't catch that" is
  the defining sound of a bad voice bot, and the kiosk has no tap gate to fall
  back on.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from typing import Any, Literal, cast, get_args

from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel, Field
from voqalize_demos import DEFAULT_MODEL, GeminiBrain, ScreenState, screen_prose

from voqalize.sdk import (
    Action,
    AppEvent,
    AppEvents,
    RequestRejected,
    RTVIMessage,
    Session,
    Speech,
    UserIdle,
    UserMessage,
)
from voqalize.sdk.wire import Config, IdleConfig, Language, SttConfig, TtsConfig, Voice

from .cards import (
    PROFILE_CHOICES,
    PROFILE_PROMPTS,
    VALUE_PROMPTS,
    CapturedField,
    Card,
    Employment,
    ExistingCards,
    IncomeBand,
    ProfileField,
    SpendCategory,
    card_by_id,
)
from .eligibility import Assessment, Shortlist, assess, shortlist
from .prompts import GREETING, SYSTEM_INSTRUCTION
from .script_english import reads_as_english
from .values import (
    allowed_values,
    display_form,
    masked_form,
    normalise,
    reads_as_yes,
    spoken_form,
)

# How long the customer has to be quiet before Voqalize reports an idle tick.
# Tanvi never answers one — ``on_user_idle`` is silence, always — so this clock
# decides nothing about when she speaks; she speaks when she is spoken to. The
# first tick after the greeting is what puts the first question's answers up for
# a customer who did not give their name.
_IDLE_MS = 2500

#: Every language the recognizer serves. The kiosk starts in English and moves the
#: moment a customer asks for another or is already speaking one.
LanguageName = Literal[
    "English",
    "Hindi",
    "Bengali",
    "Gujarati",
    "Kannada",
    "Malayalam",
    "Marathi",
    "Punjabi",
    "Tamil",
    "Telugu",
    "Assamese",
    "Bodo",
    "Dogri",
    "Kashmiri",
    "Konkani",
    "Maithili",
    "Manipuri",
    "Nepali",
    "Odia",
    "Sanskrit",
    "Santali",
    "Sindhi",
    "Urdu",
]

#: Tanvi's voice, in every language. One person throughout — only the language
#: moves, never the voice, so her face and her voice cannot come apart mid-call.
_VOICE = Voice.OMNIVOICE_GAURI


@dataclass(frozen=True)
class _Speech:
    """How the kiosk listens and speaks in one language."""

    #: What the recognizer is set to — always the customer's own language.
    heard: Language
    #: The voice clip that answers. Where no clip exists for a language the
    #: recognizer understands, this is Hindi's, and the customer is told so.
    spoken: Language


def _clip(heard: Language) -> _Speech:
    """A language with a clip of its own: heard and spoken in it."""
    return _Speech(heard=heard, spoken=heard)


def _via_hindi(heard: Language) -> _Speech:
    """A language the recognizer understands and no clip speaks — answered in
    Hindi's. The substitution is stated here and said aloud, never made quietly:
    the speech tier refuses a voice/language pairing it cannot serve."""
    return _Speech(heard=heard, spoken=Language.HI)


_SPEECH: dict[LanguageName, _Speech] = {
    "English": _clip(Language.EN),
    "Hindi": _clip(Language.HI),
    "Bengali": _clip(Language.BN),
    "Gujarati": _clip(Language.GU),
    "Kannada": _clip(Language.KN),
    "Malayalam": _clip(Language.ML),
    "Marathi": _clip(Language.MR),
    "Punjabi": _clip(Language.PA),
    "Tamil": _clip(Language.TA),
    "Telugu": _clip(Language.TE),
    "Assamese": _via_hindi(Language.AS),
    "Bodo": _via_hindi(Language.BRX),
    "Dogri": _via_hindi(Language.DOI),
    "Kashmiri": _via_hindi(Language.KS),
    "Konkani": _via_hindi(Language.KOK),
    "Maithili": _via_hindi(Language.MAI),
    "Manipuri": _via_hindi(Language.MNI),
    "Nepali": _via_hindi(Language.NE),
    "Odia": _via_hindi(Language.OR),
    "Sanskrit": _via_hindi(Language.SA),
    "Santali": _via_hindi(Language.SAT),
    "Sindhi": _via_hindi(Language.SD),
    "Urdu": _via_hindi(Language.UR),
}

# A name in LanguageName with no row here is a tool call that raises mid-call, so
# the two are held to each other at import rather than discovered on a customer.
assert set(get_args(LanguageName)) == set(_SPEECH), "LanguageName and _SPEECH disagree"


#: How long the recognizer waits through a pause, on the 0-to-10 scale. Quick for
#: the four questions, which are answered in a word or two; patient while a
#: mobile number or PAN is being dictated, because people read those out in groups
#: and a partial one is rejected outright rather than read back.
_PATIENCE_QUICK = 3
_PATIENCE_DICTATION = 8


def _config(language_name: LanguageName, patience: int = _PATIENCE_QUICK) -> Config:
    """Both legs and the idle clock, in one request.

    The two legs always move together: naming a language on one and not the other
    is the half-applied-pair bug, and it is silent — the words stay right and only
    the speaker is wrong. ``Config`` refuses it at the call site, which is why
    this function exists and why nothing ever builds a one-legged one.
    """
    speech = _SPEECH[language_name]
    return Config(
        # The step's patience, carried by every switch so a language change never
        # drops it back to the deployment's 7 (see ``_PATIENCE_QUICK``).
        stt=SttConfig(language=speech.heard, patience=patience),
        tts=TtsConfig(voice=_VOICE, language=speech.spoken),
        idle=IdleConfig(timeout_ms=_IDLE_MS),
    )


# ─── Brain → screen: the typed action contract ────────────────────────────────
# Declared once, here. ``voqalize types backend/brain.py`` generates the
# TypeScript half, so the totem narrows on the same union this file defines.


class ProfileOption(BaseModel):
    """One answer the screen offers. The value is the closed token the rules run
    on; the two labels are what the customer reads."""

    value: str
    label: str
    label_hi: str


class CardView(BaseModel):
    """One card as the totem renders it — display forms only, every one of them
    a string the voice must never be handed.

    ``eligible`` is false for a card the customer does not clear yet. The
    shortlist always shows three, so a customer who clears only the secured card
    still sees where they can go next.
    """

    id: str
    name: str
    fee: str
    waiver: str
    reward: str
    perk: str
    line_estimate: str
    requirement: str
    eligible: bool


class StartedOver(Action):
    """Everything they answered is gone from the glass. The first question
    follows in the same breath; the call, and its language, stay as they are."""


class AskProfile(Action):
    """One discovery question, with the closed set of answers beside it."""

    field: str
    question: str
    options: list[ProfileOption]


class AskValue(Action):
    """One value for the customer to type in themselves.

    ``kind`` is the keypad the totem puts under their finger — ``tel`` for a
    mobile number, ``text`` for a PAN — and ``label`` is already in this
    session's language, because the screen is read and not spoken.
    """

    field: str
    label: str
    kind: str


class ConfirmValue(Action):
    """A value the customer spoke, as the screen holds it.

    ``state`` is one of ``heard`` (shown, nothing asked), ``confirming`` (read
    back, waiting on a yes) or ``confirmed`` (settled). ``masked`` is the safe
    form for a totem in a branch, and it is what the screen shows by default.
    """

    field: str
    display: str
    masked: str
    state: str


class ShowEligibility(Action):
    """The verdict, as a band and reasons. Never a score, and never a decision —
    ``band`` is one of ``wide``, ``standard`` or ``secured``."""

    band: str
    reasons: list[str]
    line_estimate: str


class ShowShortlist(Action):
    """Three cards, ranked, one of them recommended."""

    cards: list[CardView]
    recommended_id: str
    why: str


class OpenCardDetail(Action):
    """Open one card full screen. Also the parameter of the tool that sends it."""

    card_id: str


class OpenConsent(Action):
    """The consent panel for one card: what the customer is agreeing to, in the
    bank's own words. The bullets are written in Python, never by the model."""

    card_id: str
    bullets: list[str]


class ShowQr(Action):
    """The last screen: a QR code to carry to the desk."""

    caption: str


class LanguageChanged(Action):
    """The conversation moved language. Not a screen: the language picker on the
    brand bar follows it, and the screen's own copy follows it only as far as
    copy exists. How a language is *written* on the picker is the page's to say —
    the brain names it and nothing more."""

    language: LanguageName
    #: Which of the screen's two copy sets to show. Every language but Hindi keeps
    #: the English copy: there is no Tamil screen, only a Tamil voice.
    screen_language: Literal["en", "hi"]


#: Everything Tanvi can put on the totem. Exhaustive, so a new action that
#: :meth:`KioskBrain._mirror` forgets is a type error rather than a mirror that
#: quietly falls a command behind.
ScreenMove = (
    StartedOver
    | AskProfile
    | AskValue
    | ConfirmValue
    | ShowEligibility
    | ShowShortlist
    | OpenCardDetail
    | OpenConsent
    | ShowQr
)


# ─── Screen → brain: what the customer did with their hand ────────────────────
# Twelve gestures, in the order a customer meets them. Every one of them is a
# step the journey can be driven by without a word being said; :meth:`_advance`
# is the table that turns one into the next screen.


class JourneyStarted(AppEvent):
    """They skipped the name and asked for the first question. The call is
    already live, because pressing Start is what opened it; this is the one tap
    that moves the welcome screen on for a customer who would rather not talk."""


class ProfileAnswered(AppEvent):
    """They tapped one of the answers on screen instead of saying it."""

    field: str
    value: str


class EligibilityAcknowledged(AppEvent):
    """They have read what they are likely eligible for and want the cards."""


class CardTapped(AppEvent):
    """They opened a card on the shortlist themselves."""

    card_id: str


class CardDetailClosed(AppEvent):
    """They closed a card and went back to the three."""


class CardCompared(AppEvent):
    """They put the shortlist side by side themselves."""


class CardChosen(AppEvent):
    """They settled on one card, with their hand."""

    card_id: str


class ConsentGiven(AppEvent):
    """They accepted the consent panel on screen."""

    card_id: str


class ValueEntered(AppEvent):
    """They typed a value in themselves rather than reading it out."""

    field: str
    value: str


class ValueConfirmed(AppEvent):
    """They confirmed a value on screen rather than out loud."""

    field: str


class ValueEdited(AppEvent):
    """They corrected a value by hand. Theirs wins; it is not read back again."""

    field: str
    value: str


class RestartPressed(AppEvent):
    """They pressed Start over. Their answers are cleared and the first question
    comes back; the call stays up. There is no idle timeout and nothing resets
    itself."""


class LanguagePicked(AppEvent):
    """They tapped the language chip. Not a step in the journey — it moves the
    conversation, so it is handled beside the journey rather than inside it."""

    language: LanguageName


KioskEvent = (
    JourneyStarted
    | ProfileAnswered
    | EligibilityAcknowledged
    | CardTapped
    | CardDetailClosed
    | CardCompared
    | CardChosen
    | ConsentGiven
    | ValueEntered
    | ValueConfirmed
    | ValueEdited
    | RestartPressed
)

KIOSK_EVENTS = AppEvents(
    JourneyStarted,
    ProfileAnswered,
    EligibilityAcknowledged,
    CardTapped,
    CardDetailClosed,
    CardCompared,
    CardChosen,
    ConsentGiven,
    ValueEntered,
    ValueConfirmed,
    ValueEdited,
    RestartPressed,
    LanguagePicked,
)

#: The four discovery questions, in the order they are asked. ``PROFILE_CHOICES``
#: is written in that order and is the one place it lives, so this reads it off
#: rather than writing it down a second time.
_PROFILE_ORDER: tuple[ProfileField, ...] = tuple(PROFILE_CHOICES)

#: Every field a value can land in, as something the runtime can test against.
#: ``CapturedField`` is a type and a hand on a keypad can send anything.
_CAPTURED_FIELDS: frozenset[str] = frozenset(get_args(CapturedField))


# ─── Tool parameters ───────────────────────────────────────────────────────────
# A bare ``Literal`` crashes google-genai's function calling — it checks each
# argument with ``isinstance``, which refuses a subscripted generic — so every
# closed vocabulary travels inside a model, where it is validated instead.


class ProfileQuestion(BaseModel):
    """The one parameter of ``ask_profile``. The options are not here: they are
    the closed vocabulary in ``cards.py`` and the model must not author them."""

    field: ProfileField = Field(description="Which of the four questions to put on screen.")
    question: str = Field(
        description="The question as you will say it aloud, in the customer's language."
    )


class HeardValue(BaseModel):
    """The one parameter of ``capture_value``: what the customer said, resolved."""

    field: CapturedField = Field(description="Which value this is.")
    value: str = Field(
        description=(
            "For the four questions, one of the allowed tokens. "
            "For mobile, the ten digits. For pan, the ten characters."
        )
    )


class ConfirmCheck(BaseModel):
    """The one parameter of ``confirm``: the value you read back, and what they
    said next, verbatim."""

    field: CapturedField = Field(description="The value you read back to them.")
    value: str = Field(description="The value as you read it back.")
    heard: str = Field(description="Their reply, word for word, not paraphrased.")


class EligibilityRequest(BaseModel):
    """The one parameter of ``check_eligibility``."""

    age: int | None = Field(
        default=None,
        description="Their age, only if they volunteered it. Never ask for it.",
    )


class CardChoice(BaseModel):
    """The one parameter of the two tools that act on a chosen card."""

    card_id: str = Field(description="The id of the card, from the shortlist.")


class SwitchLanguage(BaseModel):
    """The one parameter of ``switch_language``."""

    language: LanguageName = Field(description="The language to continue in.")


# ─── Tanvi's mirror of the totem ───────────────────────────────────────────────
# The one copy of what is on screen. The keys reach the model verbatim through
# ``screen_prose``, so they are written the way a person would say them.


def _blank_screen() -> dict[str, Any]:
    """Where every session starts: the attract loop, nothing answered."""
    return {
        "screen": "attract",
        "the question on screen": None,
        "the value we are asking for": None,
        "what they have told us": {},
        "the value being confirmed": None,
        "their eligibility": None,
        "the shortlist": None,
        "the card we recommended": None,
        "the card they have open": None,
        "the consent panel": None,
        "the qr code": None,
    }


def _trim(view: dict[str, Any]) -> dict[str, Any]:
    """Drop what is not on screen, so an attract loop does not read as a list of
    nine empty panels."""
    return {key: value for key, value in view.items() if value or key == "screen"}


async def _silence() -> AsyncGenerator[Any, None]:
    """Yields nothing: an idle tick Tanvi has no reason to answer."""
    for _ in ():
        yield


class KioskBrain(GeminiBrain):
    """One per session. Tanvi: the prompt, eleven tools, and this session's
    language, answers and screen."""

    def __init__(self, *, client: genai.Client, model: str = DEFAULT_MODEL) -> None:
        super().__init__(client=client, system_instruction=SYSTEM_INSTRUCTION, model=model)

        self.language: LanguageName = "English"
        #: The recognizer's patience right now; see ``_pace_for_the_screen``.
        self._patience = _PATIENCE_QUICK
        #: Patience changes in flight, held so none is collected before it lands.
        self._pending: set[asyncio.Task[None]] = set()

        # What the customer has told us, field → stored value. Filled from both
        # directions: ``capture_value`` when they speak, ``apply_event`` when
        # they tap. It is the input to the rules and nothing else reads it.
        self.answers: dict[str, str] = {}
        #: Values settled, either by a spoken yes or by the customer's own hand.
        self.confirmed: set[str] = set()
        #: Values already re-asked once. A field in here is never asked again.
        self.reasked: set[str] = set()

        self.assessment: Assessment | None = None
        self.shortlist_ids: tuple[str, ...] = ()
        self.consented_card_id: str | None = None

        # The totem, and the staleness clock over it. ``view`` is never appended
        # to the model's context; it is read through ``get_screen_context``.
        self.screen = ScreenState(read_tool="get_screen_context")
        self.view: dict[str, Any] = _blank_screen()

    @property
    def tools(self) -> list[Callable[..., Any]]:
        """The eleven Tanvi may call, in the order the call uses them."""
        return [
            self.start_over,
            self.ask_profile,
            self.capture_value,
            self.confirm,
            self.check_eligibility,
            self.show_shortlist,
            self.open_card_detail,
            self.open_consent,
            self.finish_with_qr,
            self.get_screen_context,
            self.switch_language,
        ]

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        """Settle the language and put both legs on it before a word is spoken.

        The page carries the customer's choice from the totem's own language
        toggle; English is what a walk-in gets otherwise. The prompt covers both
        languages and is never rewritten after this, so ``switch_language`` moves
        the wire alone.
        """
        payload = dict(session.init or {})
        chosen = str(payload.get("language", "")).strip().title()
        # Guarded on the greeting table, not the language table: a session may only
        # open in a language there is a written opener for.
        self.language = chosen if chosen in GREETING else "English"
        await session.configure(_config(self.language, self._patience))
        logger.info("kiosk: session start (language={})", self.language)

    async def greet(self, session: Session) -> str:
        """The opener, written not generated. It is the line that discloses Tanvi
        is an AI, and a customer standing at a totem should not wait on a first
        token to hear it."""
        return GREETING[self.language]

    def on_user_idle(self, session: Session, idle: UserIdle) -> AsyncGenerator[Speech, None]:
        """Silence, always — but the first quiet moment starts the journey.

        Tanvi greets once and then speaks when she is spoken to, and at no other
        time. A customer filling the kiosk in with their hands is not a customer
        to be prompted, commented at or nagged — the screen is answering them,
        and it is faster than she is. Every gesture still leaves its note, so the
        turn she eventually takes has the whole visit behind it.

        The one thing the quiet does is move the welcome screen on. The greeting
        asks for a name, and a customer who does not give one is not left
        looking at a screen with nothing to press: the first question's answers
        come up by themselves, with no speech and no model call. A customer who
        does answer never sees this — Tanvi has put the question up herself.
        """
        if self.view["screen"] == "attract":
            self._show(self._question(_PROFILE_ORDER[0]))
            self._append_note(
                self.screen.moved(
                    "stayed quiet after the greeting, so the first question's answers are up"
                )
            )
        return _silence()

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[Speech, None]:
        """One spoken turn — with English caught before the model sees it.

        In any other language the recognizer spells English in that language's
        script, and the model, reading it, would answer in English about one time
        in three without calling ``switch_language``: new words, old voice, old
        recognizer. :func:`reads_as_english` decides it in Python instead, and
        both legs move to English before the model runs, so its reply is spoken in
        English and the customer's next sentence is heard in English.
        """
        self.append_to_context(types.Content(role="user", parts=[types.Part(text=msg.text)]))
        if self.language != "English" and reads_as_english(msg.text):
            self._append_note(await self._switch_to("English", by="the kiosk, which heard English"))
        async for speech in self.respond(session):
            yield speech

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """One thing the customer just did on the totem.

        Two things happen for it, and neither of them speaks: the gesture folds
        into the mirror and leaves one line in front of the model, and the
        journey moves on. ``on_rtvi`` is not a generator, so a hand can drive the
        screen and cannot take the floor from the mouth beside it.
        """
        event = KIOSK_EVENTS.parse(msg)
        if event is None:
            return
        logger.info("kiosk: {} — {}", type(event).__voqal_event__, event)
        if isinstance(event, LanguagePicked):
            # A configure has to be awaited and the journey table is deliberately
            # synchronous, so the chip takes its own path. Still no speech.
            self._append_note(await self._switch_to(event.language, by="the customer"))
            return
        self._append_note(self.apply_event(event))

    # ─── Screen → brain ─────────────────────────────────────────────────

    def apply_event(self, event: KioskEvent) -> str:
        """Fold one gesture in, move the screen on, and return the line that
        tells Tanvi.

        Both halves run for every gesture and they are not the same thing.
        :meth:`_fold` records what the customer did and writes the note;
        :meth:`_advance` decides what goes on the glass next and this dispatches
        it. The fold runs first, because the next screen is a function of what
        they just told us.

        The note *names* what they did and never carries what the screen now
        says — that is read back through ``get_screen_context``, which is the only
        copy that cannot go stale.
        """
        note = self._fold(event)
        for move in self._advance(event):
            self._show(move)
        return note

    def _fold(self, event: KioskEvent) -> str:
        """Record one gesture in the mirror; return the line that names it.

        No fallback arm: an event added to :data:`KioskEvent` and not handled
        here is a type error, which is also what makes :meth:`_advance` safe to
        write as a lookup.
        """
        match event:
            case JourneyStarted():
                return self.screen.moved("touched the screen to begin")
            case ProfileAnswered():
                self._record(event.field, event.value)
                return self.screen.moved(f"tapped their answer to the {_spaced(event.field)}")
            case EligibilityAcknowledged():
                return self.screen.moved("read what they are likely eligible for and moved on")
            case CardTapped():
                card = card_by_id(event.card_id)
                self.view["the card they have open"] = card.name if card else event.card_id
                return self.screen.moved("opened one of the cards themselves")
            case CardDetailClosed():
                self.view["the card they have open"] = None
                return self.screen.moved("closed the card and went back to the three")
            case CardCompared():
                return self.screen.moved("put the shortlisted cards side by side themselves")
            case CardChosen():
                return self.screen.moved("chose their card themselves")
            case ConsentGiven():
                self.consented_card_id = event.card_id
                self.view["the consent panel"] = "accepted"
                return self.screen.moved("accepted the consent panel on screen")
            case ValueEntered():
                self._enter(event.field, event.value)
                return self.screen.moved(f"typed their {_spaced(event.field)} in themselves")
            case ValueConfirmed():
                self.confirmed.add(event.field)
                self._set_state(event.field, "confirmed")
                return self.screen.moved(f"confirmed their {_spaced(event.field)} on screen")
            case ValueEdited():
                self._enter(event.field, event.value)
                return self.screen.moved(f"corrected their {_spaced(event.field)} by hand")
            case RestartPressed():
                self._reset()
                return self.screen.moved(
                    "pressed Start over, so their answers are cleared and the first question is back"
                )

    # ─── The journey, as one table ──────────────────────────────────────

    def _advance(self, event: KioskEvent) -> tuple[ScreenMove, ...]:
        """What the screen does next, for one gesture.

        Read the table as a table: the gesture on the left, what goes on the
        glass on the right. Every row is free — an action calls no model and
        holds no floor — which is the whole reason a customer who never says a
        word can still walk from the attract loop to the QR code, in Python, at
        the speed of their own hand.

        Two rows move nothing and say so. Comparing cards is the customer using
        the screen for the thing the screen is for, and a value confirmed out
        loud has already been painted by ``confirm``. The only row that is two
        moves is a value typed in: it settles, and then the next thing is asked
        for in the same breath.

        A hand and a voice reach the same transitions. The tools below still
        dispatch every one of these actions when Tanvi is the one driving;
        neither path is a special case of the other.
        """
        table: dict[type[KioskEvent], Callable[[Any], tuple[ScreenMove, ...]]] = {
            JourneyStarted: self._next_question,
            ProfileAnswered: self._next_question,
            EligibilityAcknowledged: self._the_shortlist,
            CardTapped: self._one_card,
            CardDetailClosed: self._the_shortlist,
            CardCompared: self._nothing,
            CardChosen: self._the_consent_panel,
            ConsentGiven: self._ask_for_mobile,
            ValueEntered: self._value_and_what_follows,
            ValueConfirmed: self._nothing,
            ValueEdited: self._value_alone,
            RestartPressed: self._started_over,
        }
        return table.get(type(event), self._nothing)(event)

    def _nothing(self, _: KioskEvent) -> tuple[ScreenMove, ...]:
        """A gesture the journey deliberately does not advance on."""
        return ()

    def _started_over(self, _: KioskEvent) -> tuple[ScreenMove, ...]:
        """:meth:`_fold` has already cleared the session; this clears the glass
        and puts the first question back on it."""
        return (StartedOver(), self._question(_PROFILE_ORDER[0]))

    def _next_question(self, _: KioskEvent) -> tuple[ScreenMove, ...]:
        """The first of the four they have not answered — or, once all four are
        in, what they are likely eligible for."""
        for field in _PROFILE_ORDER:
            if field not in self.answers:
                return (self._question(field),)
        return (_eligibility_view(self._assess()),)

    def _the_shortlist(self, _: KioskEvent) -> tuple[ScreenMove, ...]:
        """The three cards, ranked.

        The same payload every time it is asked, because the ranking is a pure
        function of an assessment that has not changed — so closing a card and
        coming back re-renders the row it left, rather than moving it.
        """
        ranked = self._rank()
        return () if ranked is None else (_shortlist_view(ranked),)

    def _one_card(self, event: CardTapped) -> tuple[ScreenMove, ...]:
        card = self._on_the_glass(event.card_id)
        return () if card is None else (OpenCardDetail(card_id=card.id),)

    def _the_consent_panel(self, event: CardChosen) -> tuple[ScreenMove, ...]:
        card = self._on_the_glass(event.card_id)
        if card is None:
            return ()
        return (OpenConsent(card_id=card.id, bullets=_consent_bullets(card)),)

    def _ask_for_mobile(self, _: KioskEvent) -> tuple[ScreenMove, ...]:
        return (self._ask_value("mobile"),)

    def _value_and_what_follows(self, event: ValueEntered) -> tuple[ScreenMove, ...]:
        """The value they typed, settled, and then whatever comes after it.

        A value the keypad sent that ``normalise`` will not take is not on the
        screen and is not in the mirror, so the same question goes back up. That
        is the one row that can repeat itself, and it repeats because the
        customer has not answered it yet.
        """
        settled = self._settled(event.field)
        if settled is None:
            return (self._ask_value(event.field),)
        if event.field == "mobile":
            return (settled, self._ask_value("pan"))
        if event.field == "pan":
            return (settled, self._handoff())
        return (settled,)

    def _value_alone(self, event: ValueEdited) -> tuple[ScreenMove, ...]:
        """A correction settles and goes no further: they are mid-journey, not
        answering the question the journey last asked."""
        settled = self._settled(event.field)
        return () if settled is None else (settled,)

    # ─── What the table needs ───────────────────────────────────────────

    def _question(self, field: ProfileField) -> AskProfile:
        """One discovery question as the totem asks it by itself, in this
        session's language. The options are the closed vocabulary, never authored
        here and never authored by a model."""
        english, hindi = PROFILE_PROMPTS[field]
        return AskProfile(
            field=field,
            question=hindi if self.language == "Hindi" else english,
            options=_profile_options(field),
        )

    def _ask_value(self, field: str) -> AskValue:
        """The keypad for one value, labelled in this session's language."""
        english, hindi, kind = VALUE_PROMPTS[field]
        return AskValue(
            field=field, label=hindi if self.language == "Hindi" else english, kind=kind
        )

    def _settled(self, field: str) -> ConfirmValue | None:
        """One stored value, painted as settled — or ``None`` when there is no
        value of that name to paint, which is the keypad's way of saying the
        customer has not given one yet."""
        value = self.answers.get(field)
        if value is None:
            return None
        return _confirm_view(cast(CapturedField, field), value, "confirmed")

    def _handoff(self) -> ShowQr:
        """The code they carry to the desk, for the card they consented to."""
        card = card_by_id(self.consented_card_id) if self.consented_card_id else None
        return ShowQr(caption=_qr_caption(card))

    def _assess(self, age: int | None = None) -> Assessment:
        """Run the rules over what the customer has told us, and remember the
        verdict. The one place :func:`assess` is called from."""
        assessment = assess(
            employment=cast(Employment, self.answers["employment"]),
            income_band=cast(IncomeBand, self.answers["income_band"]),
            existing_cards=cast(ExistingCards, self.answers["existing_cards"]),
            age=age,
        )
        self.assessment = assessment
        logger.info(
            "kiosk: assessed band={} cards={}", assessment.band, assessment.eligible_card_ids
        )
        return assessment

    def _rank(self) -> Shortlist | None:
        """Rank the shelf for this customer and remember what is on the glass,
        or ``None`` while there is nothing to rank. The one place
        :func:`shortlist` is called from."""
        if self.assessment is None or "spend_category" not in self.answers:
            return None
        spend = cast(SpendCategory, self.answers["spend_category"])
        ranked = shortlist(self.assessment, spend)
        self.shortlist_ids = tuple(row.card.id for row in ranked.rows)
        logger.info("kiosk: shortlist {} pick={}", self.shortlist_ids, ranked.recommended_id)
        return ranked

    def _on_the_glass(self, card_id: str) -> Card | None:
        """The card a hand just pointed at, or ``None`` if it is not one.

        No staleness clock here: a hand cannot be out of date with the screen it
        is touching. That guard is :meth:`_shortlisted`, and it is for the model,
        which can be.
        """
        card = card_by_id(card_id)
        if card is None or (self.shortlist_ids and card.id not in self.shortlist_ids):
            logger.warning("kiosk: {!r} is not a card on this screen", card_id)
            return None
        return card

    def _enter(self, field: str, value: str) -> None:
        """Store a value the customer typed, in the one shape this demo stores.

        A keypad sends what was pressed; ``normalise`` is what decides whether
        that is yet a mobile number. What it will not take is not stored and not
        mirrored — a half-typed PAN rendered as a settled one is the kiosk
        telling a customer it has something it does not have.
        """
        if field not in _CAPTURED_FIELDS:
            logger.warning("kiosk: nothing on this kiosk holds a {!r}", field)
            return
        stored = normalise(cast(CapturedField, field), value)
        if stored is None:
            logger.info("kiosk: the {} they typed is not one we can use", _spaced(field))
            self.answers.pop(field, None)
            self.confirmed.discard(field)
            self.view["what they have told us"].pop(field, None)
            return
        self._record(field, stored)

    def _record(self, field: str, value: str) -> None:
        """Store an answer the customer gave with their hand.

        A value they typed or tapped themselves needs no reading back — it is
        already theirs, and asking them to confirm their own keystrokes is the
        kiosk redoing work the human has done.
        """
        self.answers[field] = value
        self.confirmed.add(field)
        self.view["what they have told us"][field] = value
        self._set_state(field, "confirmed")

    def _set_state(self, field: str, state: str) -> None:
        """Move the value panel's state, if that is the value it is showing."""
        panel = self.view["the value being confirmed"]
        if isinstance(panel, dict) and panel.get("field") == field:
            panel["state"] = state

    def _reset(self) -> None:
        """Back to the attract loop, with nothing remembered but the language."""
        self.answers.clear()
        self.confirmed.clear()
        self.reasked.clear()
        self.assessment = None
        self.shortlist_ids = ()
        self.consented_card_id = None
        self.view = _blank_screen()

    def _append_note(self, text: str) -> None:
        """Put one line in front of the model without taking the floor. It is
        appended as the customer's own content, because that is what it is."""
        self.append_to_context(types.Content(role="user", parts=[types.Part(text=text)]))

    # ─── Brain → screen ─────────────────────────────────────────────────

    def _show(self, action: ScreenMove) -> None:
        """Put something on the totem: patch the mirror, then dispatch.

        Both, in that order, and only here — a dispatch that skipped the mirror
        would leave Tanvi reading a screen one command behind her own last word.
        The browser never echoes this back: her own dispatch is not an event.
        """
        self._mirror(action)
        self.session.dispatch(action)
        self._pace_for_the_screen()

    def _pace_for_the_screen(self) -> None:
        """Wait longer through pauses while a mobile or PAN is being dictated.

        ``_show`` is synchronous — the journey table is — so the change is sent
        as its own request rather than awaited here. It touches patience alone,
        never a language, so it cannot half-move the pair.
        """
        wanted = (
            _PATIENCE_DICTATION if self.view["screen"] in ("value", "confirm") else _PATIENCE_QUICK
        )
        if wanted == self._patience:
            return
        self._patience = wanted
        task = asyncio.get_running_loop().create_task(
            self.session.configure(Config(stt=SttConfig(patience=wanted)))
        )
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    def _mirror(self, action: ScreenMove) -> None:
        """Apply one of Tanvi's own commands to her picture of the totem.

        The totem shows one thing at a time, so each arm also clears what that
        move takes off the glass. A key left behind is a panel Tanvi believes is
        still in front of the customer, and she will talk about it.
        """
        view = self.view
        match action:
            case StartedOver():
                self.view = _blank_screen()
            case AskProfile():
                view["screen"] = "question"
                view["the question on screen"] = _spaced(action.field)
                view["the value we are asking for"] = None
                view["the value being confirmed"] = None
            case AskValue():
                view["screen"] = "value"
                view["the question on screen"] = None
                view["the value we are asking for"] = _spaced(action.field)
                view["the value being confirmed"] = None
            case ConfirmValue() if action.state == "confirming":
                view["screen"] = "confirm"
                view["the question on screen"] = None
                view["the value we are asking for"] = None
                view["the value being confirmed"] = {
                    "field": action.field,
                    "shown as": action.masked,
                    "state": action.state,
                }
            case ConfirmValue() if view["screen"] == "confirm":
                # A mobile or PAN read-back, now settled: the panel stays up and
                # says so, until the next move takes it off the glass.
                view["the value being confirmed"] = {
                    "field": action.field,
                    "shown as": action.masked,
                    "state": action.state,
                }
            case ConfirmValue():
                # A chip answer, settled as it was heard: the screen does not stop
                # to ask. It used to paint a confirm screen here, and Tanvi,
                # reading it, waited for a yes nobody was going to say.
                view["the value being confirmed"] = None
            case ShowEligibility():
                view["screen"] = "eligibility"
                view["the question on screen"] = None
                view["the value being confirmed"] = None
                view["their eligibility"] = {
                    "band": action.band,
                    "indicative limit": action.line_estimate,
                }
            case ShowShortlist():
                view["screen"] = "shortlist"
                view["the shortlist"] = {
                    card.id: ("eligible" if card.eligible else "not yet") for card in action.cards
                }
                view["the card we recommended"] = action.recommended_id
                view["the card they have open"] = None
                view["the consent panel"] = None
            case OpenCardDetail():
                view["screen"] = "card"
                card = card_by_id(action.card_id)
                view["the card they have open"] = card.name if card else action.card_id
            case OpenConsent():
                view["screen"] = "consent"
                view["the consent panel"] = f"waiting on {action.card_id}"
            case ShowQr():
                view["screen"] = "qr"
                view["the value we are asking for"] = None
                view["the qr code"] = action.caption

    # ─── Tools ──────────────────────────────────────────────────────────

    async def start_over(self) -> str:
        """Clear everything and put the first question back on screen. Use it when the
        customer says they want to start again, or when a new person has walked
        up. Nothing is kept."""
        logger.info("kiosk: start_over")
        self._reset()
        for move in self._started_over(RestartPressed()):
            self._show(move)
        return (
            "Cleared, and the first question is back in front of them. "
            "Say you are starting over and ask it once, in one short line."
        )

    async def ask_profile(self, ask: ProfileQuestion) -> str:
        """Put one of the four discovery questions on screen, with its answers.

        Ask the four in order: employment, income_band, existing_cards,
        spend_category. Call this FIRST, then ask the question aloud — once. The
        screen only holds the choices; it asks nothing. Do not read the options
        out; they are on the glass in front of the customer.
        """
        logger.info("kiosk: ask_profile {}", ask.field)
        self._show(
            # The glass carries the bank's own wording, in the screen's language —
            # never the model's, which may be in a language the screen has no copy for.
            self._question(ask.field)
        )
        return (
            "Shown. Now ask the question aloud once, in one short line — unless you already "
            "asked it this turn, in which case say nothing more. Never read the options."
        )

    async def capture_value(self, heard: HeardValue) -> str:
        """Record what the customer just said and show it to them.

        For the four questions, resolve what they said to one of the allowed
        tokens first — "about forty thousand a month" is ``25k_60k``. For mobile
        and PAN, pass the characters; the kiosk masks them on screen for you.

        A closed answer settles here and needs no reading back. Mobile and PAN
        come back with a SAY line: read it, then pass their reply to confirm.
        """
        value = normalise(heard.field, heard.value)
        if value is None:
            logger.warning("kiosk: capture_value rejected {}={!r}", heard.field, heard.value)
            # Not "that is not a income band I can use": the field name is
            # interpolated, so the sentence has to read for every one of the six.
            return (
                f"{heard.value!r} is not a value I can use for {_spaced(heard.field)}. "
                f"Allowed: {allowed_values(heard.field)}. Ask them again in different words."
            )

        spoken_needed = heard.field in ("mobile", "pan")
        state = "confirming" if spoken_needed else "heard"
        self.answers[heard.field] = value
        self.view["what they have told us"][heard.field] = value
        if not spoken_needed:
            self.confirmed.add(heard.field)
        on_screen = self.view["the question on screen"] == _spaced(heard.field)
        logger.info("kiosk: capture_value {}={}", heard.field, masked_form(heard.field, value))
        self._show(_confirm_view(heard.field, value, state))
        if not spoken_needed:
            return self._after_an_answer(on_screen)
        return (
            f"On screen, masked. SAY: {spoken_form(heard.field, value)}. "
            "Read that back in one line, ask if it is right, then call confirm with their reply."
        )

    def _after_an_answer(self, on_screen: bool) -> str:
        """Move the journey on from a spoken answer, in Python.

        While the customer is still in the questions — on the welcome screen or
        on one of the four — an answer puts the next unanswered question up at
        once, the way a tap does. The model used to be told to acknowledge and
        wait for ``ask_profile``, and in a live Kannada session it acknowledged
        and then sat silent until the customer spoke again. That includes an
        answer given before any question was up ("I'm Ravi, I'm salaried"), which
        would otherwise leave the welcome screen standing and have the first quiet
        moment ask them what they had just said.

        The one answer that moves nothing is a correction: an earlier question
        answered again while a different, unanswered one is on screen, or any
        answer once the questions are behind them.
        """
        remaining: list[ProfileField] = [f for f in _PROFILE_ORDER if f not in self.answers]
        shown = self.view["the question on screen"]
        in_the_questions = self.view["screen"] in ("attract", "question")
        another_is_up = not on_screen and shown in {_spaced(f) for f in remaining}
        if not in_the_questions or another_is_up:
            return "Recorded. Acknowledge in two or three words and carry on where they were."
        if remaining:
            self._show(self._question(remaining[0]))
            return (
                f"Recorded, and the {_spaced(remaining[0])} question is already up for them. "
                "In this same turn: acknowledge in two or three words, then ask it once, in "
                "one short line. Do not call ask_profile for it."
            )
        return (
            "Recorded; that was the last of the four. In this same turn, call "
            "check_eligibility and say the line it returns."
        )

    async def confirm(self, check: ConfirmCheck) -> str:
        """Decide whether the customer actually confirmed a value.

        Pass their reply word for word, not your reading of it. A clear yes
        settles the value. Anything else — a hedge, a correction, a reply too
        short to carry signal — comes back as unclear, and you ask once more in
        different words. There is no third time: a second unclear reply is taken
        as heard and the call moves on.
        """
        value = self.answers.get(check.field)
        if value is None:
            return f"Nothing to confirm — call capture_value for the {_spaced(check.field)} first."
        if reads_as_yes(check.heard):
            return self._settle(check.field, value, "Confirmed.")
        if check.field in self.reasked:
            logger.info("kiosk: confirm {} unclear twice, taking it as heard", check.field)
            return self._settle(
                check.field,
                value,
                "Still unclear, and it has been asked once already. Taking it as heard.",
            )
        self.reasked.add(check.field)
        logger.info("kiosk: confirm {} unclear, asking once more", check.field)
        self._show(_confirm_view(check.field, value, "confirming"))
        return (
            "Not a clear yes. SAY: ask once more, in different words, in one short line. "
            "Do not say you did not catch it, and do not ask a third time."
        )

    def _settle(self, field: CapturedField, value: str, verdict: str) -> str:
        """Mark a value settled, paint it, and hand the model its next move."""
        self.confirmed.add(field)
        self._show(_confirm_view(field, value, "confirmed"))
        return (
            f"{verdict} Acknowledge in a few words. Whatever comes next arrives with its own "
            "tool call; do not say it twice."
        )

    async def check_eligibility(self, request: EligibilityRequest) -> str:
        """Work out what the customer is likely eligible for and show it.

        Call it once all four questions are answered. The rules are Python — you
        do not compare incomes or scores yourself, and there is no credit score
        to speak: the screen shows a band and the reasons behind it.
        """
        missing = [field for field in _PROFILE_ORDER if field not in self.answers]
        if missing:
            return f"Not yet — still missing {', '.join(_spaced(field) for field in missing)}."

        assessment = self._assess(request.age)
        self._show(_eligibility_view(assessment))
        return (
            f"On screen. SAY: {assessment.spoken}, and the line is about "
            f"{assessment.line_spoken}. One line only, then call show_shortlist. "
            "Add that a banker at the desk will confirm."
        )

    async def show_shortlist(self) -> str:
        """Rank the cards for this customer and put the top three on screen.

        The ranking is Python: their biggest spend first, then the tier they
        clear. Say which one you would pick and why, in one line, and let the
        screen hold the fees and the rates.
        """
        ranked = self._rank()
        if ranked is None:
            return "Call check_eligibility first — there is nothing to rank yet."
        self._show(_shortlist_view(ranked))
        return _pick_line(ranked)

    async def open_card_detail(self, card: OpenCardDetail) -> str:
        """Open one card full screen, when the customer asks about it by name.

        Say the one thing that makes it theirs. The fee, the rate and the cap are
        on screen; do not read them out.
        """
        chosen = self._shortlisted(card.card_id)
        if isinstance(chosen, str):
            return chosen
        logger.info("kiosk: open_card_detail {}", chosen.id)
        self._show(OpenCardDetail(card_id=chosen.id))
        return (
            f"On screen. SAY: {chosen.perk_spoken}. One line, and do not read the fee "
            "or the rate aloud."
        )

    async def open_consent(self, card: CardChoice) -> str:
        """Open the consent panel for the card the customer has chosen.

        The bullets are written by the bank, not by you. Say the one line this
        returns and ask them to say yes out loud. There is nothing to tap: the
        kiosk takes a spoken yes.
        """
        chosen = self._shortlisted(card.card_id)
        if isinstance(chosen, str):
            return chosen
        logger.info("kiosk: open_consent {}", chosen.id)
        self._show(OpenConsent(card_id=chosen.id, bullets=_consent_bullets(chosen)))
        return (
            f"On screen. SAY: the {chosen.name}, and everything you are agreeing to is on "
            "screen. Ask them to say yes out loud. Say a banker will confirm, and that "
            "nothing here is decided."
        )

    async def finish_with_qr(self, card: CardChoice) -> str:
        """Show the QR code that ends the visit, after a spoken yes.

        Only after the customer has agreed out loud, or accepted the panel on
        screen. Tell them to show it at the desk, then stop talking.
        """
        chosen = self._shortlisted(card.card_id)
        if isinstance(chosen, str):
            return chosen
        self.consented_card_id = chosen.id
        logger.info("kiosk: finish_with_qr {}", chosen.id)
        self._show(ShowQr(caption=_qr_caption(chosen)))
        return (
            "On screen. SAY: one line telling them to show that code at the desk, where a "
            "banker will take it from here. Then stop."
        )

    async def get_screen_context(self) -> str:
        """What the customer is looking at right now: the screen, what they have
        told us, and anything they have chosen.

        Call it before you act on something they pointed at, and whenever you are
        told they moved the screen themselves. It is free — it reads this
        session's own mirror, says nothing and moves nothing.
        """
        self.screen.read()
        logger.info(
            "kiosk: get_screen_context -> {} (v{})", self.view["screen"], self.screen.version
        )
        return screen_prose(_trim(self.view))

    async def switch_language(self, to: SwitchLanguage) -> str:
        """Continue the conversation in another language — the listening and the
        speaking both.

        Call it when the customer asks for a language, AND when you can tell they
        are already speaking one: do not wait to be asked. Do not switch on a
        single borrowed English word; Indian speech is full of them.
        """
        return await self._switch_to(to.language, by="you")

    async def _switch_to(self, name: LanguageName, *, by: str) -> str:
        """Move both legs to one language and tell the page. Shared by the tool
        and the chip, so the two cannot disagree about what a switch does."""
        if name == self.language:
            return f"Already in {name}. Carry on."
        speech = _SPEECH[name]
        try:
            # One request moves both legs, so the kiosk is never listening in one
            # language and speaking in another. All-or-nothing on refusal.
            await self.session.configure(_config(name, self._patience))
        except RequestRejected as rejected:
            logger.warning("kiosk: language {} rejected — {}", name, rejected)
            return (
                f"Refused — the kiosk is still in {self.language}. "
                f"Tell the customer, in {self.language}, that you cannot speak {name} here."
            )
        logger.info("kiosk: language {} -> {} (by {})", self.language, name, by)
        self.language = name
        self.session.dispatch(
            LanguageChanged(
                language=name,
                screen_language="hi" if name == "Hindi" else "en",
            )
        )
        if speech.spoken != speech.heard:
            return (
                f"Now listening in {name}, answering in Hindi — no voice speaks {name}. "
                f"SAY: once, in Hindi, that you understand them and will reply in Hindi. "
                "Do not repeat a question you already asked this turn."
            )
        return (
            f"Now in {name}, switched by {by}. Say one short line in {name}. If you already asked "
            "a question this turn, do not ask it again; if you did not, ask it once."
        )

    # ─── Tool guards ────────────────────────────────────────────────────

    def _shortlisted(self, card_id: str) -> Card | str:
        """The card this tool may act on, or the sentence explaining the refusal.

        Three refusals, all retriable and all naming the way out: a screen the
        model has not re-read since the customer moved it, a shortlist that does
        not exist yet, and a card id that is not on the one that does — which is
        either invented or left over from a shortlist since replaced.
        """
        if (stale := self.screen.stale()) is not None:
            return f"Not yet: {stale}."
        if not self.shortlist_ids:
            return "There is no shortlist on screen yet — call show_shortlist first."
        chosen = card_by_id(card_id)
        if chosen is None or chosen.id not in self.shortlist_ids:
            return (
                f"{card_id!r} is not on the shortlist. "
                f"The cards on screen are: {', '.join(self.shortlist_ids)}."
            )
        return chosen


def _spaced(field: str) -> str:
    """A field name as a person says it: ``income_band`` → "income band". Nothing
    with an underscore in it ever reaches the voice."""
    return field.replace("_", " ")


def _profile_options(field: ProfileField) -> list[ProfileOption]:
    """The closed set of answers to one question, as the screen offers them."""
    return [
        ProfileOption(value=value, label=label, label_hi=label_hi)
        for value, label, label_hi in PROFILE_CHOICES[field]
    ]


def _confirm_view(field: CapturedField, value: str, state: str) -> ConfirmValue:
    """One captured value as the totem holds it. Both renderings come from
    ``values.py``, which is the one home for the difference between them."""
    return ConfirmValue(
        field=field,
        display=display_form(field, value),
        masked=masked_form(field, value),
        state=state,
    )


def _eligibility_view(assessment: Assessment) -> ShowEligibility:
    """The verdict on the wire: a band and the reasons, never a score."""
    return ShowEligibility(
        band=assessment.band,
        reasons=list(assessment.reasons),
        line_estimate=assessment.line_display,
    )


def _shortlist_view(ranked: Shortlist) -> ShowShortlist:
    """A ranking on the wire. The whole row every time, so re-rendering it after
    a card closes puts back exactly what was there."""
    return ShowShortlist(
        cards=[_card_view(row.card, row.eligible) for row in ranked.rows],
        recommended_id=ranked.recommended_id,
        why=ranked.why_display,
    )


def _qr_caption(card: Card | None) -> str:
    """The line under the code they carry to the desk."""
    return f"{card.name}. Show this at the desk." if card else "Show this at the desk."


def _card_view(card: Card, eligible: bool) -> CardView:
    """One card projected onto the wire — display forms only."""
    return CardView(
        id=card.id,
        name=card.name,
        fee=card.fee_display,
        waiver=card.waiver_display,
        reward=card.reward_display,
        perk=card.perk_display,
        line_estimate=card.line_display,
        requirement=card.requirement_display,
        eligible=eligible,
    )


def _consent_bullets(card: Card) -> list[str]:
    """What the customer is agreeing to, in the bank's words. Written here so a
    model cannot soften a fee or invent a waiver, and the last line is the one
    this kiosk exists to keep saying."""
    return [
        f"Annual fee: {card.fee_display}",
        f"Fee waiver: {card.waiver_display}",
        f"Rewards: {card.reward_display}",
        f"Indicative limit: {card.line_display}",
        f"Eligibility: {card.requirement_display}",
        "Vantage Bank runs its own checks. Nothing is approved at this kiosk.",
    ]


def _pick_line(ranked: Shortlist) -> str:
    """The one line Tanvi may say about a shortlist of three."""
    pick = card_by_id(ranked.recommended_id)
    name = pick.name if pick else "the first one"
    return (
        f"On screen. SAY: the {name} is your best fit, because {ranked.why_spoken}. "
        # No em-dash: everything after SAY: is text Tanvi may read as written, and
        # an em-dash read aloud is a stumble at best. Two sentences instead.
        "One line. Do not read the fees or the rates aloud. They are on screen."
    )
