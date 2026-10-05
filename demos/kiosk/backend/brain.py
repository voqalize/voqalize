"""KioskBrain — Tanvi, the Vantage Bank branch-kiosk assistant.

A :class:`voqalize_demos.GeminiBrain`. A walk-in customer stands at a totem in a
private cubicle and fills in a short form on the screen: the profile questions,
then the cards ranked for them, then their mobile number, their PAN and a tap to
agree, and a QR code to carry to the desk. Nothing in it is approved: the kiosk
has no tool that can submit anything, and says so.

Vantage Bank is invented, and so is every card on its shelf.

**The screen runs the form. Tanvi helps.** Four things carry that:

* **The form is Python, moved by gestures.** Every step is a typed event from
  the customer's hand, and :meth:`KioskBrain._advance` is the table that turns
  one into the next screen — no model call, no speech. The rules that rank the
  cards are the pure functions in ``eligibility.py``.

* **Tanvi's tools are the same gestures.** Each one builds the event a tap would
  and sends it through :meth:`apply_event`, so if a hand cannot do it right now,
  neither can she. None of them calls ``_show`` or ``session.dispatch`` itself,
  none takes display text, and none reaches the mobile number, the PAN or the
  consent: those are the customer's hand alone.

* **Nothing on the glass is written by a model, and it is in English.** Every
  string in every action comes from ``cards.py`` and this file. The screen does
  not follow the conversation's language; only Tanvi's voice and ears do.

* **The screen reaches Tanvi read-only, every turn.** Each spoken turn carries a
  short note of what is on the glass right now, placed after the cached prefix
  and dropped when the turn ends, so the context never fills with old copies of
  it. What the customer *did* stays, one line per gesture.

She speaks at the opening, when she is asked something, and once when the cards
go up, to say why the top one. That line is written here, not generated
(``pitch.py``).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from typing import Any, Literal, cast, get_args

from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel, Field
from voqalize_demos import (
    DEFAULT_MODEL,
    PHRASES,
    FallbackLine,
    GeminiBrain,
    configure_soon,
    landed,
    phrase,
    screen_prose,
)
from voqalize_demos.silent_turn import Phrase

from voqalize.sdk import (
    Action,
    AppEvent,
    AppEvents,
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
from voqalize.sdk.wire import Config, IdleConfig, Language, SttConfig, TtsConfig, Voice

from .cards import (
    CARDS,
    EMPLOYMENT_SPOKEN,
    EXISTING_CARDS_SPOKEN,
    INCOME_BAND_SPOKEN,
    PROFILE_CHOICES,
    PROFILE_PROMPTS,
    SPEND_SPOKEN,
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
from .latin_hindi import reads_as_latin_hindi
from .pitch import pitch_line
from .prompts import GREETING, HINDI_VOICED, SYSTEM_INSTRUCTION, switch_line
from .script_english import reads_as_english
from .values import display_form, masked_form, normalise

# How long the customer has to be quiet before Voqalize reports an idle tick.
# Tanvi answers an idle tick for one thing only: the line about the top card,
# when the cards went up under a hand and there was no turn to say it in. Every
# other tick is silence, so this clock decides nothing else.
_IDLE_MS = 2500
# How soon that one line follows the cards. Short, because the customer is
# looking at them now; the idle clock goes back to ``_IDLE_MS`` once it is said.
_IDLE_PITCH_MS = 600

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
_VOICE = Voice.OMNIVOICE_GAYATRI


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
# The prompt names the languages answered with the Hindi voice, so Tanvi can say
# so in the line she switches with; it is held to this table the same way.
assert set(HINDI_VOICED) == {name for name, s in _SPEECH.items() if s.spoken != s.heard}, (
    "HINDI_VOICED and _SPEECH disagree"
)

#: How long the recognizer waits through a pause, on the 0-to-10 scale. Quick,
#: because nothing here is dictated any more: an answer is a word or two, and a
#: mobile number or a PAN is typed.
_PATIENCE = 3


def _config(language_name: LanguageName) -> Config:
    """Both legs and the idle clock, in one request.

    The two legs always move together: naming a language on one and not the other
    is the half-applied-pair bug, and it is silent — the words stay right and only
    the speaker is wrong. ``Config`` refuses it at the call site, which is why
    this function exists and why nothing ever builds a one-legged one.
    """
    speech = _SPEECH[language_name]
    return Config(
        # Carried by every switch, so a language change never drops it back to
        # the deployment's 7.
        stt=SttConfig(language=speech.heard, patience=_PATIENCE),
        tts=TtsConfig(voice=_VOICE, language=speech.spoken),
        idle=IdleConfig(timeout_ms=_IDLE_MS),
    )


# ─── Brain → screen: the typed action contract ────────────────────────────────
# Declared once, here. ``voqalize types backend/brain.py`` generates the
# TypeScript half, so the totem narrows on the same union this file defines.


class ProfileOption(BaseModel):
    """One answer the screen offers. The value is the closed token the rules run
    on; the label is what the customer reads."""

    value: str
    label: str


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
    """One profile question, with the closed set of answers beside it."""

    field: str
    question: str
    options: list[ProfileOption]


class AskValue(Action):
    """One value for the customer to type in themselves.

    ``kind`` is the keypad the totem puts under their finger — ``tel`` for a
    mobile number, ``text`` for a PAN.
    """

    field: str
    label: str
    kind: str


class ConfirmValue(Action):
    """A value the customer typed, as the screen holds it.

    ``state`` is ``confirmed``: a value they typed themselves is already settled,
    and nothing reads it back. ``masked`` is the safe form for a totem in a
    branch, and it is what the screen shows by default.
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
    """Open one card full screen."""

    card_id: str


class OpenConsent(Action):
    """The consent panel for one card: what the customer is agreeing to, in the
    bank's own words. The bullets are written in Python, never by the model."""

    card_id: str
    bullets: list[str]


class ShowQr(Action):
    """The last screen: a QR code to carry to the desk."""

    caption: str


#: Everything that can go on the totem. Exhaustive, so a new action that
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

#: What Tanvi says for a screen that landed in her turn, when the model's turn
#: said nothing — see :mod:`voqalize_demos.silent_turn`. A phrase, not a line,
#: because the line is said in the language her voice is speaking. A move that
#: puts a question to the customer hands them the turn (``over_to_you``); the
#: rest put something up to look at (``shown``). The shortlist has none: its line
#: is the pitch, which is spoken whether the model said anything or not.
_PHRASE: dict[type[ScreenMove], Phrase | None] = {
    StartedOver: "over_to_you",
    AskProfile: "over_to_you",
    AskValue: "over_to_you",
    ConfirmValue: "done",
    ShowEligibility: "shown",
    ShowShortlist: None,
    OpenCardDetail: "shown",
    OpenConsent: "over_to_you",
    ShowQr: "shown",
}
# A screen with no phrase, or a voice language with no lines, would raise
# mid-call, so each is held to the table it indexes here.
assert set(_PHRASE) == set(get_args(ScreenMove)), "_PHRASE and ScreenMove disagree"
assert {s.spoken for s in _SPEECH.values()} <= set(PHRASES), (
    "a language Tanvi speaks has no PHRASES row"
)


# ─── Screen → brain: what the customer did with their hand ────────────────────
# The gestures, in the order a customer meets them. Every one of them is a step
# the form can be driven by without a word being said; :meth:`_advance` is the
# table that turns one into the next screen.


class ProfileAnswered(AppEvent):
    """They answered the question on screen — with a tap, or by saying it to
    Tanvi, who tapped it for them."""

    field: str
    value: str


class EligibilityAcknowledged(AppEvent):
    """They have read what they are likely eligible for and want the cards."""


class CardTapped(AppEvent):
    """They opened a card on the shortlist."""

    card_id: str


class CardDetailClosed(AppEvent):
    """They closed a card and went back to the three."""


class CardCompared(AppEvent):
    """They put the shortlist side by side."""


class CardChosen(AppEvent):
    """They settled on one card."""

    card_id: str


class ConsentGiven(AppEvent):
    """They accepted the consent panel on screen. A hand only."""

    card_id: str


class ValueEntered(AppEvent):
    """They typed a value in. A hand only."""

    field: str
    value: str


class ValueConfirmed(AppEvent):
    """They confirmed a value on screen. A hand only."""

    field: str


class ValueEdited(AppEvent):
    """They corrected a value by hand. Theirs wins; it is not read back."""

    field: str
    value: str


class RestartPressed(AppEvent):
    """They pressed Start over. Their answers are cleared and the first question
    comes back; the call stays up."""


KioskEvent = (
    ProfileAnswered
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
)

#: The gestures Tanvi can make for the customer, and the ones she cannot. The
#: second set is the privacy line: a mobile number, a PAN and a consent reach the
#: kiosk from the customer's own hand or not at all.
TANVI_GESTURES: frozenset[type[AppEvent]] = frozenset(
    {
        ProfileAnswered,
        EligibilityAcknowledged,
        CardTapped,
        CardDetailClosed,
        CardCompared,
        CardChosen,
        RestartPressed,
    }
)
HAND_ONLY: frozenset[type[AppEvent]] = frozenset(
    {ConsentGiven, ValueEntered, ValueConfirmed, ValueEdited}
)
assert set(get_args(KioskEvent)) == TANVI_GESTURES | HAND_ONLY, "a gesture is in neither set"
assert not TANVI_GESTURES & HAND_ONLY, "a gesture is in both sets"

#: The profile questions, in the order they are asked. ``PROFILE_CHOICES`` is
#: written in that order and is the one place it lives.
_PROFILE_ORDER: tuple[ProfileField, ...] = tuple(PROFILE_CHOICES)

#: Every field a value can land in, as something the runtime can test against.
#: ``CapturedField`` is a type and a hand on a keypad can send anything.
_CAPTURED_FIELDS: frozenset[str] = frozenset(get_args(CapturedField))

#: How each answer is said, for the note Tanvi reads — never a wire token.
_ANSWER_SPOKEN: dict[str, dict[str, str]] = {
    field: {str(token): said for token, said in spoken.items()}
    for field, spoken in (
        ("employment", EMPLOYMENT_SPOKEN),
        ("income_band", INCOME_BAND_SPOKEN),
        ("existing_cards", EXISTING_CARDS_SPOKEN),
        ("spend_category", SPEND_SPOKEN),
    )
}


# ─── Tool parameters ───────────────────────────────────────────────────────────
# A bare ``Literal`` crashes google-genai's function calling — it checks each
# argument with ``isinstance``, which refuses a subscripted generic — so every
# closed vocabulary travels inside a model, where it is validated instead. The
# schema is the refusal: a value outside a field's options cannot be sent.


def _options(field: ProfileField) -> str:
    """One field's options, as the tool declaration spells them out."""
    return ", ".join(f"{value} ({label})" for value, label in PROFILE_CHOICES[field])


class OnScreenAnswer(BaseModel):
    """The one parameter of ``answer_on_screen``. Set the field for the question
    on the screen; the rest stay empty."""

    employment: Employment | None = Field(
        default=None, description=f"What they do: {_options('employment')}."
    )
    income_band: IncomeBand | None = Field(
        default=None, description=f"Monthly income: {_options('income_band')}."
    )
    existing_cards: ExistingCards | None = Field(
        default=None, description=f"Credit cards they hold: {_options('existing_cards')}."
    )
    spend_category: SpendCategory | None = Field(
        default=None, description=f"Where most of their money goes: {_options('spend_category')}."
    )


#: Every card on the shelf, as the tool declarations may name one.
CardId = Literal[
    "vantage_rise", "vantage_fuel", "vantage_everyday", "vantage_voyage", "vantage_crest"
]
assert set(get_args(CardId)) == {card.id for card in CARDS}, "CardId and the shelf disagree"


class CardPick(BaseModel):
    """The one parameter of the tools that point at a card."""

    card_id: CardId = Field(description="The card, by id, from the cards on the screen.")


class SwitchLanguage(BaseModel):
    """The one parameter of ``switch_language``."""

    language: LanguageName = Field(description="The language to continue in.")


# ─── The mirror of the totem ───────────────────────────────────────────────────
# The one copy of what is on screen. The keys reach the model verbatim through
# ``screen_prose``, so they are written the way a person would say them. A mobile
# number and a PAN are in it as "typed in" and never as themselves.


def _blank_screen() -> dict[str, Any]:
    """Where every session starts: the welcome screen, nothing answered."""
    return {
        "screen": "welcome",
        "the question on screen": None,
        "its answers": None,
        "the value we are asking them to type": None,
        "what they have told us": {},
        "their eligibility": None,
        "the cards on screen": None,
        "the card we recommend": None,
        "why we recommend it": None,
        "the card they have open": None,
        "the consent panel": None,
        "the qr code": None,
    }


def _trim(view: dict[str, Any]) -> dict[str, Any]:
    """Drop what is not on screen, so a welcome screen does not read as a list of
    empty panels."""
    return {key: value for key, value in view.items() if value or key == "screen"}


async def _silence() -> AsyncGenerator[Any, None]:
    """Yields nothing: an idle tick Tanvi has no reason to answer."""
    for _ in ():
        yield


class KioskBrain(GeminiBrain):
    """One per session. Tanvi: the prompt, the gestures, and this session's
    language, answers and screen."""

    def __init__(self, *, client: genai.Client, model: str = DEFAULT_MODEL) -> None:
        super().__init__(client=client, system_instruction=SYSTEM_INSTRUCTION, model=model)

        self.language: LanguageName = "English"
        self._fallback = FallbackLine()

        # What the customer has told us, field → stored value. Filled only by
        # gestures, whoever made them. It is the input to the rules.
        self.answers: dict[str, str] = {}
        self.assessment: Assessment | None = None
        self.ranked: Shortlist | None = None
        self.shortlist_ids: tuple[str, ...] = ()
        self.consented_card_id: str | None = None

        #: The shortlist the line about the top card is owed for, until it is said.
        self._pitch_due: Shortlist | None = None
        #: The shortlist that line was last said for, so it is said once per
        #: shortlist and not again when a card closes and the three come back.
        self._pitched: tuple[str, ...] = ()
        #: Whether the idle clock is shortened for that line right now.
        self._idle_short = False
        #: The language the model asked to move to this turn, until the voice has
        #: moved and the kiosk has said so in it (``_switch_now``).
        self._switch_due: LanguageName | None = None

        # The totem. Never appended to the context; each spoken turn reads it as
        # a note that leaves again when the turn is over (``_with_the_screen``).
        self.view: dict[str, Any] = _blank_screen()

    @property
    def tools(self) -> list[Callable[..., Any]]:
        """The gestures Tanvi may make, in the order the form meets them. None is
        marked ``@needs_result_now``: each is an action, not a read — the screen
        reaches her with every turn instead."""
        return [
            self.answer_on_screen,
            self.continue_to_cards,
            self.open_card,
            self.close_card,
            self.compare_cards,
            self.choose_card,
            self.start_over,
            self.switch_language,
        ]

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        """Settle the language and put both legs on it before a word is spoken.

        The page may carry a language; English is what a walk-in gets otherwise.
        The prompt covers every language and is never rewritten after this, so
        ``switch_language`` moves the wire alone.
        """
        payload = dict(session.init or {})
        chosen = str(payload.get("language", "")).strip().title()
        # Guarded on the greeting table, not the language table: a session may only
        # open in a language there is a written opener for.
        self.language = chosen if chosen in GREETING else "English"
        await session.configure(_config(self.language))
        logger.info("kiosk: session start (language={})", self.language)

    async def greet(self, session: Session) -> str:
        """The opener, written not generated — and the first question on the glass
        as it is said, because the greeting asks them to fill the form in.

        It is the line that discloses Tanvi is an AI, and a customer standing at a
        totem should not wait on a first token to hear it.
        """
        self._show(self._question(_PROFILE_ORDER[0]))
        return GREETING[self.language]

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The model's turn; a line of Tanvi's own if it acted and said nothing;
        the switch line, in the new language, if it moved the language; and the
        line about the top card, if the cards just went up.

        The prompt has the model speak and call in the same response, and on a
        dialled call it sometimes called alone, leaving the customer in silence
        with the screen changed. See :mod:`voqalize_demos.silent_turn`."""
        async for event in self._fallback.speak_if_silent(self, self._model_turn(session)):
            yield event
        async for event in self._pitch_now():
            yield event

    async def _model_turn(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The model's own turn, and the switch line if it moved the language.

        The switch line is inside the turn the fallback watches, so a turn that
        tapped an answer and switched in silence — as the prompt asks — is not
        also given "Go ahead." in the language being left."""
        async for event in super().respond(session):
            yield event
        async for event in self._switch_now():
            yield event

    async def _switch_now(self) -> AsyncGenerator[Speech, None]:
        """Move both legs, wait for them to land, then say so in the new language.

        The model writes before the voice changes, so a switch line of its own
        would be heard in the language being left — a customer who spoke Hindi
        heard "Let's continue in Hindi" in English. So the tool only asks, and
        the line is written, and spoken here once the new voice is on."""
        name = self._switch_due
        if name is None:
            return
        self._switch_due = None
        note = await self._switch_to(name, by="you")
        if self.language != name:
            # Refused: the call stays where it was, and the model is told why.
            self._append_note(note)
            return
        async for speech in self._say(switch_line(name)):
            yield speech

    def on_user_idle(self, session: Session, idle: UserIdle) -> AsyncGenerator[Speech, None]:
        """Silence — except for the line about the top card.

        A customer filling the form in with their hand is not a customer to be
        prompted, commented at or nagged: the screen is answering them, and it is
        faster than she is. The one thing a quiet moment may carry is the line a
        tap owed and could not say — ``on_rtvi`` takes no floor, so when a tap
        puts the cards up, the idle clock is shortened and the line is said here.
        """
        if self._pitch_due is None:
            return _silence()
        return self._pitch_on_idle()

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[Speech, None]:
        """One spoken turn — with a plain change of language caught before the
        model sees it, and the screen in front of it.

        A recognizer writes every language in its own script: English spoken to
        the Kannada one comes out as English in Kannada letters, and Hindi spoken
        to the English one as Hindi in English letters. The model reads both, and
        answers in the new language without calling ``switch_language`` often
        enough to matter: new words, old voice, old recognizer. So the plain
        cases are decided in Python — :func:`reads_as_english`,
        :func:`reads_as_latin_hindi` — and both legs move before the model runs,
        so its reply is spoken by the right voice.
        """
        # The kiosk's own notes go in front of the customer's words, never after
        # them: a request that does not end on what they said is one the model
        # has been seen to continue, note and all, out loud.
        if self.language != "English" and reads_as_english(msg.text):
            note = await self._switch_to("English", by="the kiosk, which heard English")
            self._append_note(note)
        elif self.language == "English" and reads_as_latin_hindi(msg.text):
            note = await self._switch_to("Hindi", by="the kiosk, which heard Hindi")
            self._append_note(note)
        self.append_to_context(types.Content(role="user", parts=[types.Part(text=msg.text)]))
        async for speech in self._with_the_screen(self.respond(session)):
            yield speech

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """One thing the customer just did on the totem.

        The gesture folds into the mirror, leaves one line in front of the model,
        and moves the form on. ``on_rtvi`` is not a generator, so a hand can drive
        the screen and cannot take the floor from the mouth beside it — which is
        why the cards going up under a hand arms the idle clock for their line.
        """
        event = KIOSK_EVENTS.parse(msg)
        if event is None:
            return
        logger.info("kiosk: {} — {}", type(event).__voqal_event__, event)
        self._append_note(self.apply_event(event))
        if self._pitch_due is not None:
            self._idle_clock(short=True)

    # ─── Screen → brain ─────────────────────────────────────────────────

    def apply_event(self, event: KioskEvent) -> str:
        """Fold one gesture in, move the screen on, and return the line that
        tells Tanvi.

        The one way anything reaches the glass, for a hand and for Tanvi alike.
        :meth:`_fold` records what was done and writes the note; :meth:`_advance`
        decides what goes on the glass next and this dispatches it. The fold runs
        first, because the next screen is a function of what they just told us.
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
            case ProfileAnswered():
                self._record(event.field, event.value)
                said = _ANSWER_SPOKEN.get(event.field, {}).get(event.value, event.value)
                return f"The customer answered the {_spaced(event.field)}: {said}."
            case EligibilityAcknowledged():
                return (
                    "The customer read what they are likely eligible for and asked for the cards."
                )
            case CardTapped():
                card = card_by_id(event.card_id)
                self.view["the card they have open"] = card.name if card else event.card_id
                return f"The customer opened the {card.name if card else event.card_id}."
            case CardDetailClosed():
                self.view["the card they have open"] = None
                return "The customer closed the card and went back to the three."
            case CardCompared():
                return "The customer put the cards side by side."
            case CardChosen():
                card = card_by_id(event.card_id)
                return f"The customer chose the {card.name if card else event.card_id}."
            case ConsentGiven():
                self.consented_card_id = event.card_id
                self.view["the consent panel"] = "accepted"
                return "The customer tapped I agree on the consent panel."
            case ValueEntered():
                self._enter(event.field, event.value)
                return f"The customer typed in their {_spaced(event.field)}."
            case ValueConfirmed():
                return f"The customer confirmed their {_spaced(event.field)} on screen."
            case ValueEdited():
                self._enter(event.field, event.value)
                return f"The customer corrected their {_spaced(event.field)}."
            case RestartPressed():
                self._reset()
                return "The customer pressed Start over, so their answers are cleared."

    # ─── The form, as one table ─────────────────────────────────────────

    def _advance(self, event: KioskEvent) -> tuple[ScreenMove, ...]:
        """What the screen does next, for one gesture.

        Read the table as a table: the gesture on the left, what goes on the
        glass on the right. Every row is free — an action calls no model and
        holds no floor — which is why a customer who never says a word walks from
        the first question to the QR code, in Python, at the speed of their hand.

        Two rows move nothing and say so: comparing is the customer using the
        screen for what it is for, and a value confirmed is already settled. The
        only row that is two moves is a value typed in: it settles, and the next
        thing is asked for in the same breath.
        """
        table: dict[type[KioskEvent], Callable[[Any], tuple[ScreenMove, ...]]] = {
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
        """A gesture the form deliberately does not advance on."""
        return ()

    def _started_over(self, _: KioskEvent) -> tuple[ScreenMove, ...]:
        """:meth:`_fold` has already cleared the session; this clears the glass
        and puts the first question back on it."""
        return (StartedOver(), self._question(_PROFILE_ORDER[0]))

    def _next_question(self, _: KioskEvent) -> tuple[ScreenMove, ...]:
        """The first question they have not answered — or, once they are all in,
        what they are likely eligible for."""
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

        A value ``normalise`` will not take is not on the screen and not in the
        mirror, so the same question goes back up — the one row that repeats,
        because the customer has not answered it yet.
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
        """A correction settles and goes no further."""
        settled = self._settled(event.field)
        return () if settled is None else (settled,)

    # ─── What the table needs ───────────────────────────────────────────

    def _question(self, field: ProfileField) -> AskProfile:
        """One profile question as the bank wrote it. The options are the closed
        vocabulary, never authored here and never authored by a model."""
        return AskProfile(
            field=field,
            question=PROFILE_PROMPTS[field],
            options=[
                ProfileOption(value=value, label=label) for value, label in PROFILE_CHOICES[field]
            ],
        )

    def _ask_value(self, field: str) -> AskValue:
        """The keypad for one value."""
        label, kind = VALUE_PROMPTS[field]
        return AskValue(field=field, label=label, kind=kind)

    def _settled(self, field: str) -> ConfirmValue | None:
        """One stored value, painted as settled — or ``None`` when there is no
        value of that name to paint, which is the keypad's way of saying the
        customer has not given one yet."""
        value = self.answers.get(field)
        if value is None or field not in _CAPTURED_FIELDS:
            return None
        return _confirm_view(cast(CapturedField, field), value)

    def _handoff(self) -> ShowQr:
        """The code they carry to the desk, for the card they consented to."""
        card = card_by_id(self.consented_card_id) if self.consented_card_id else None
        return ShowQr(caption=_qr_caption(card))

    def _assess(self) -> Assessment:
        """Run the rules over what the customer has told us, and remember the
        verdict. The one place :func:`assess` is called from."""
        assessment = assess(
            employment=cast(Employment, self.answers["employment"]),
            income_band=cast(IncomeBand, self.answers["income_band"]),
            existing_cards=cast(ExistingCards, self.answers["existing_cards"]),
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
        ranked = shortlist(self.assessment, cast(SpendCategory, self.answers["spend_category"]))
        self.ranked = ranked
        self.shortlist_ids = tuple(row.card.id for row in ranked.rows)
        logger.info("kiosk: shortlist {} pick={}", self.shortlist_ids, ranked.recommended_id)
        return ranked

    def _on_the_glass(self, card_id: str) -> Card | None:
        """The card a gesture pointed at, or ``None`` if it is not one on screen."""
        card = card_by_id(card_id)
        if card is None or (self.shortlist_ids and card.id not in self.shortlist_ids):
            logger.warning("kiosk: {!r} is not a card on this screen", card_id)
            return None
        return card

    def _enter(self, field: str, value: str) -> None:
        """Store a value the customer typed, in the one shape this demo stores.

        What ``normalise`` will not take is not stored and not mirrored — a
        half-typed PAN rendered as a settled one is the kiosk telling a customer
        it has something it does not have.
        """
        if field not in _CAPTURED_FIELDS:
            logger.warning("kiosk: nothing on this kiosk holds a {!r}", field)
            return
        stored = normalise(cast(CapturedField, field), value)
        if stored is None:
            logger.info("kiosk: the {} they typed is not one we can use", _spaced(field))
            self.answers.pop(field, None)
            self.view["what they have told us"].pop(_spaced(field), None)
            return
        self._record(field, stored)

    def _record(self, field: str, value: str) -> None:
        """Store an answer. The mirror carries how it is said — and, for a mobile
        number or a PAN, only that it was typed in."""
        self.answers[field] = value
        said = (
            "typed in"
            if field in ("mobile", "pan")
            else _ANSWER_SPOKEN.get(field, {}).get(value, value)
        )
        self.view["what they have told us"][_spaced(field)] = said

    def _reset(self) -> None:
        """Back to the start, with nothing remembered but the language."""
        self.answers.clear()
        self.assessment = None
        self.ranked = None
        self.shortlist_ids = ()
        self.consented_card_id = None
        self._pitch_due = None
        self._pitched = ()
        self._idle_clock(short=False)
        self.view = _blank_screen()

    def _append_note(self, text: str) -> None:
        """Put one line in front of the model without taking the floor. It is
        appended as the customer's own content, because that is what it is."""
        self.append_to_context(types.Content(role="user", parts=[types.Part(text=text)]))

    # ─── Brain → screen ─────────────────────────────────────────────────

    def _show(self, action: ScreenMove) -> None:
        """Put something on the totem: patch the mirror, then dispatch.

        Both, in that order, and only here — and only ever from a gesture's row
        or the greeting, never from a tool. A dispatch that skipped the mirror
        would leave Tanvi reading a screen one command behind.
        """
        self._mirror(action)
        self.session.dispatch(action)
        said = _PHRASE[type(action)]
        if said is not None:
            landed(*phrase(_SPEECH[self.language].spoken, said))
        # The cards going up owe their line, once per shortlist.
        if (
            isinstance(action, ShowShortlist)
            and self.ranked is not None
            and self.shortlist_ids != self._pitched
        ):
            self._pitch_due = self.ranked

    def _mirror(self, action: ScreenMove) -> None:
        """Apply one command to the picture of the totem.

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
                view["the question on screen"] = f"{_spaced(action.field)}: {action.question}"
                view["its answers"] = ", ".join(o.label for o in action.options)
                view["the value we are asking them to type"] = None
            case AskValue():
                view["screen"] = "typing"
                view["the question on screen"] = None
                view["its answers"] = None
                view["the value we are asking them to type"] = action.label
            case ConfirmValue():
                pass
            case ShowEligibility():
                view["screen"] = "eligibility"
                view["the question on screen"] = None
                view["its answers"] = None
                assessment = self.assessment
                view["their eligibility"] = assessment.spoken if assessment else action.band
            case ShowShortlist():
                view["screen"] = "cards"
                view["the cards on screen"] = ", ".join(
                    f"{card.name} ({'likely eligible' if card.eligible else 'not yet'})"
                    for card in action.cards
                )
                pick = card_by_id(action.recommended_id)
                view["the card we recommend"] = pick.name if pick else action.recommended_id
                view["why we recommend it"] = self.ranked.why_spoken if self.ranked else None
                view["the card they have open"] = None
                view["the consent panel"] = None
            case OpenCardDetail():
                view["screen"] = "one card"
                card = card_by_id(action.card_id)
                view["the card they have open"] = card.name if card else action.card_id
            case OpenConsent():
                view["screen"] = "consent"
                card = card_by_id(action.card_id)
                view["the consent panel"] = (
                    f"for the {card.name if card else action.card_id}, waiting on their tap"
                )
            case ShowQr():
                view["screen"] = "qr code"
                view["the value we are asking them to type"] = None
                view["the qr code"] = "on screen, for the desk"

    # ─── The screen, read-only, every turn ──────────────────────────────

    def _snapshot(self) -> str:
        """What is on the glass right now, as the note a turn starts from."""
        return "What the kiosk screen shows right now:\n" + screen_prose(_trim(self.view))

    async def _with_the_screen(
        self, turn: AsyncGenerator[Speech, None]
    ) -> AsyncGenerator[Speech, None]:
        """Run ``turn`` with the screen in front of the model, then take it away.

        The note goes in just before the customer's words, after everything the
        cache has already seen, and comes out when the turn is over — so every
        request sees the screen as it is now, and none carries a stale copy of
        it forward. The SDK has no seam for a per-request note yet, so this
        reaches into the context it keeps.
        """
        note = types.Content(role="user", parts=[types.Part(text=self._snapshot())])
        history: list[types.Content] = self._history  # pyright: ignore[reportPrivateUsage]
        history.insert(max(len(history) - 1, 0), note)
        try:
            async for speech in turn:
                yield speech
        finally:
            self._history = [c for c in self._history if c is not note]  # pyright: ignore[reportPrivateUsage]

    # ─── The line about the top card ────────────────────────────────────

    async def _pitch_now(self) -> AsyncGenerator[Speech, None]:
        """The line, straight after a turn that put the cards up — when it is
        written for the language the voice is speaking. Otherwise it waits for
        the idle clock, where the model says it (:meth:`_pitch_on_idle`)."""
        ranked = self._pitch_due
        if ranked is None:
            return
        line = self._written_pitch(ranked)
        if line is None:
            self._idle_clock(short=True)
            return
        async for speech in self._pitch(line, ranked):
            yield speech

    async def _pitch_on_idle(self) -> AsyncGenerator[Speech, None]:
        """The line, on the quiet moment after the cards went up.

        Written where a line is written; in a language with no written line, the
        model says the English one in the customer's language — the one model
        call this line ever costs, and only in those languages.
        """
        ranked = self._pitch_due
        if ranked is None:
            return
        self._idle_clock(short=False)
        line = self._written_pitch(ranked)
        if line is not None:
            async for speech in self._pitch(line, ranked):
                yield speech
            return
        english = pitch_line(ranked, self._spend(), Language.EN)
        self._pitched, self._pitch_due = self.shortlist_ids, None
        self._append_note(
            f"The cards are up. In one short line, in {self.language}, tell them: {english}"
        )
        async for speech in self._with_the_screen(self.respond(self.session)):
            yield speech

    def _written_pitch(self, ranked: Shortlist) -> str | None:
        return pitch_line(ranked, self._spend(), _SPEECH[self.language].spoken)

    def _spend(self) -> SpendCategory:
        return cast(SpendCategory, self.answers.get("spend_category", "bills"))

    async def _pitch(self, line: str, ranked: Shortlist) -> AsyncGenerator[Speech, None]:
        """Say the line about the top card, once, and put the idle clock back."""
        self._pitched, self._pitch_due = self.shortlist_ids, None
        logger.info("kiosk: the line about the top card ({})", ranked.recommended_id)
        async for speech in self._say(line):
            yield speech
        self._idle_clock(short=False)

    async def _say(self, line: str) -> AsyncGenerator[Speech, None]:
        """Speak a written line, and keep it in the context as Tanvi's own, so the
        model knows what she has already said.

        It is a speech unit like any the model writes: it joins the finalize
        queue and is rewritten to what the customer actually heard.
        """
        unit = _Unit(types.Content(role="model", parts=[types.Part(text=line)]))
        self._history.append(unit.content)  # pyright: ignore[reportPrivateUsage]
        self._awaiting.append(unit)  # pyright: ignore[reportPrivateUsage]
        yield SpeechStart()
        yield SpeechChunk(line)
        yield SpeechEnd()

    def _idle_clock(self, *, short: bool) -> None:
        """Shorten the idle clock for the line about the top card, or put it back.

        Idle alone, never a language, so it cannot half-move the pair. Sent, not
        awaited, and only when it changes."""
        if short == self._idle_short:
            return
        self._idle_short = short
        timeout = _IDLE_PITCH_MS if short else _IDLE_MS
        configure_soon(self.session, Config(idle=IdleConfig(timeout_ms=timeout)))

    # ─── Tools: the gestures Tanvi makes for the customer ───────────────
    # Each builds the event a hand would send and hands it to ``_perform``,
    # which refuses what a hand could not do right now and otherwise runs it
    # through ``apply_event`` — the one road to the glass. The result reaches the
    # model with the customer's next message, so it records what happened and
    # never says what to say: she said her line before she called.

    async def answer_on_screen(self, answer: OnScreenAnswer) -> str:
        """Tap the customer's answer to the question on the screen, when they say
        it instead of tapping it. Set only the field for the question that is up.
        Say a word or two in the same response, like "Got it." — the next question
        comes up by itself.
        """
        given = answer.model_dump(exclude_none=True)
        if not given:
            return "Nothing tapped: no answer was given."
        done: list[str] = []
        for field in _PROFILE_ORDER:
            if field in given:
                done.append(self._perform(ProfileAnswered(field=field, value=str(given[field]))))
        return " ".join(done)

    async def continue_to_cards(self) -> str:
        """Tap "Show me the cards" on the eligibility screen, when they ask to see
        the cards. Say only a word or two; the kiosk says why the top card itself.
        """
        return self._perform(EligibilityAcknowledged())

    async def open_card(self, card: CardPick) -> str:
        """Open one of the cards on the screen, when they ask about it by name."""
        return self._perform(CardTapped(card_id=card.card_id))

    async def close_card(self) -> str:
        """Close the open card and go back to the three."""
        return self._perform(CardDetailClosed())

    async def compare_cards(self) -> str:
        """Put the cards on the screen side by side, when they ask to compare."""
        return self._perform(CardCompared())

    async def choose_card(self, card: CardPick) -> str:
        """Choose one of the cards on the screen for them, when they say which.
        The consent panel comes up; they read it and tap I agree themselves.
        """
        return self._perform(CardChosen(card_id=card.card_id))

    async def start_over(self) -> str:
        """Press Start over, when they want to start again or a new person has
        walked up. Their answers are cleared and the first question comes back.
        """
        return self._perform(RestartPressed())

    def _perform(self, event: KioskEvent) -> str:
        """One gesture on the customer's behalf — or the reason a hand could not
        make it right now."""
        if type(event) not in TANVI_GESTURES:
            # Never reached from a tool; this is the line the privacy rule holds.
            raise TypeError(f"{type(event).__name__} is the customer's hand only")
        refused = self._refusal(event)
        if refused is not None:
            logger.info("kiosk: refused {} — {}", type(event).__voqal_event__, refused)
            return f"Not done: {refused}"
        logger.info("kiosk: Tanvi {} — {}", type(event).__voqal_event__, event)
        self._append_note(self.apply_event(event))
        return "Done."

    def _refusal(self, event: KioskEvent) -> str | None:
        """Why a hand could not make this gesture on the screen as it is, or
        ``None`` when it could."""
        screen = self.view["screen"]
        on_cards = screen in ("cards", "one card")
        match event:
            case ProfileAnswered():
                if screen != "question" or not str(self.view["the question on screen"]).startswith(
                    _spaced(event.field) + ":"
                ):
                    return f"the {_spaced(event.field)} question is not the one on the screen."
                return None
            case EligibilityAcknowledged():
                return None if screen == "eligibility" else "the eligibility screen is not up."
            case CardTapped() | CardChosen():
                if not on_cards:
                    return "the cards are not on the screen."
                if event.card_id not in self.shortlist_ids:
                    return f"that card is not one of the three on the screen: {', '.join(self.shortlist_ids)}."
                return None
            case CardDetailClosed():
                return None if screen == "one card" else "no card is open."
            case CardCompared():
                return None if on_cards else "the cards are not on the screen."
            case RestartPressed():
                return None
            case _:
                return "that is the customer's to do on the screen."

    async def switch_language(self, to: SwitchLanguage) -> str:
        """Continue the conversation in another language — the listening and the
        speaking both. The screen stays in English.

        Call it when the customer asks for a language, AND when you can tell they
        are already speaking one: do not wait to be asked. Do not switch on a
        single borrowed English word; Indian speech is full of them. Call it
        alone, with no words: the kiosk says the switch line itself, in the new
        language, once the voice has changed. Speak the new language from their
        next turn.
        """
        if to.language == self.language:
            return f"Already in {to.language}."
        # Not sent here: a tool returns inside its budget, and the line has to wait
        # for the new voice. ``_switch_now`` awaits both legs after the turn.
        self._switch_due = to.language
        return (
            f"Switching to {to.language}; the kiosk tells them so in {to.language}. "
            f"Speak {to.language} from here on."
        )

    async def _switch_to(self, name: LanguageName, *, by: str) -> str:
        """Move both legs to one language, from a callback rather than a tool.

        The English check is not a tool, so it has no budget to keep, and it
        awaits the request: it has to land before the model's reply is spoken.
        """
        if name == self.language:
            return f"Already in {name}. Carry on."
        try:
            # One request moves both legs, so the kiosk is never listening in one
            # language and speaking in another. All-or-nothing on refusal.
            await self.session.configure(_config(name))
        except RequestRejected as rejected:
            logger.warning("kiosk: language {} rejected — {}", name, rejected)
            return (
                f"Refused — the kiosk is still in {self.language}. "
                f"Tell the customer, in {self.language}, that you cannot speak {name} here."
            )
        return self._switched(name, by=by)

    def _switched(self, name: LanguageName, *, by: str) -> str:
        """Record a switch that has been sent, and write the line the model reads
        about it. Nothing on the screen changes: it stays in English."""
        logger.info("kiosk: language {} -> {} (by {})", self.language, name, by)
        self.language = name
        speech = _SPEECH[name]
        if speech.spoken != speech.heard:
            return (
                f"Now listening in {name}, switched by {by}, and answering in Hindi — no voice "
                f"speaks {name}. Reply in Hindi from here on."
            )
        return f"Now in {name}, switched by {by}. Speak {name} from here on."


def _spaced(field: str) -> str:
    """A field name as a person says it: ``income_band`` → "income band". Nothing
    with an underscore in it ever reaches the voice."""
    return field.replace("_", " ")


def _confirm_view(field: CapturedField, value: str) -> ConfirmValue:
    """One typed value as the totem holds it. Both renderings come from
    ``values.py``, which is the one home for the difference between them."""
    return ConfirmValue(
        field=field,
        display=display_form(field, value),
        masked=masked_form(field, value),
        state="confirmed",
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
