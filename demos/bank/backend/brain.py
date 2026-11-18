"""BankBrain — the assistant of Anvaya Bank, a fictional Indian retail bank.

An :class:`~voqalize.sdk.openai.OpenAIBrain`. One brain, four jobs, one per
landing page (CONTRACT.md): the banking assistant in the signed-in app, the
account-opening guide, the credit-card advisor and the loan advisor, plus the
front desk on the home page. The landing comes in ``init``; every
``page_viewed`` moves the job with the visitor.

**Everything on screen is a Stage move** (``scene.json`` → ``stage_gen.py``):
tools compute from the bank's data (``bank.py``, ``bankmath.py``), send one or
more moves with ``stage.send(..., queue=False)`` and return at once. The page
runs them in order, rings each target before it changes it, and answers each with
a ``stage_result``.

**What is marked ``@needs_result_now``**: the reads whose facts the model must
speak (transactions, a transaction, spending, a card, a ranking, an EMI table, a
loan EMI, eligibility) and the two checks whose verdict it must say before it
asks anything (``request_change``, the form fills). Opening a screen, the
confirmation answer, a submit and the language switch are not.

**Anything that changes state is confirmed.** ``request_change`` puts a
confirmation sheet on screen; nothing changes until the customer says yes (the
brain hears a plain yes or no itself and presses the button, with no model
turn) or taps Confirm. The outcome is the page's: the brain says "done" only
when the page's result says so, with its reference.

**Persona and languages** come from ``persona.json``: both speech legs are set in
``on_session_start`` from the language the visitor picked, and move together on
the toggle or ``set_language``.
"""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator, Callable
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
from voqalize.sdk.stage import Stage
from voqalize.sdk.stage.wire import StageHello, StageProgress, StageResult
from voqalize.sdk.wire import Config, IdleConfig, SttConfig, TtsConfig

from . import bank as b
from . import bankmath as m
from .app_events import (
    BANK_EVENTS,
    ActionDone,
    CardControlChanged,
    CardsProfileChanged,
    FormChanged,
    FormSubmitted,
    LanguageRequested,
    LoanCalcChanged,
    PageViewed,
    SignedIn,
    SignedOut,
    TxnOpened,
)
from .forms import FIELDS, STEP_OF, check, missing
from .prompt import MODES, TIMES, greeting, line, system_instruction
from .stage_gen import MOVES

MODEL = "gpt-6.1-terra"
#: The repo's rule for a new demo: at "low" the model skipped screen actions it
#: had just promised (demos/README.md).
REASONING = "medium"
_IDLE_MS = 20_000
#: A line the brain already knows (a page's answer): said as soon as the voice is free.
_SAY_NOW_MS = 400

_EVENTS = AppEvents(*BANK_EVENTS, StageResult, StageHello, StageProgress)

Screen = Literal[
    "home", "login", "dashboard", "account", "transactions", "insights", "cards_hub", "debit_card",
    "credit_card", "payments", "bills", "deposits", "statements", "offers", "open_account", "cards",
    "card_detail", "cards_compare", "cards_apply", "cards_emi", "loans", "loan", "loan_apply",
]  # fmt: skip
_APP_SCREENS = {
    "dashboard", "account", "transactions", "insights", "cards_hub", "debit_card", "credit_card",
    "payments", "bills", "deposits", "statements", "offers",
}  # fmt: skip


def mode_of(screen: str) -> str:
    """The job a screen belongs to (CONTRACT.md's landing table)."""
    if screen in _APP_SCREENS:
        return "banking"
    if screen == "open_account":
        return "account"
    if screen.startswith("card"):
        return "cards"
    if screen.startswith("loan"):
        return "loans"
    return "home"


_MODE_NOTE = {
    "banking": "the banking assistant, answering from her own accounts and cards",
    "account": "the account-opening guide, filling the savings application as they talk",
    "cards": "the credit-card advisor",
    "loans": "the loan advisor",
    "home": "the front desk, taking them to the right part of the site",
}

# ─── Yes and no, heard by the brain itself ────────────────────────────────────

_YES = re.compile(
    r"^(yes|yeah|yep|yup|sure|ok|okay|go ahead|do it|please do|please|confirm|confirmed|correct|right|"
    r"haan|haa|han|haanji|haan ji|ji haan|ji|theek hai|thik hai|kar do|kardo|bilkul|"
    r"हाँ|हां|हा|जी|जी हाँ|हाँ जी|ठीक है|कर दो|कर दीजिए|बिल्कुल)(?=$|[\s,.!?।])",
    re.IGNORECASE,
)
_NO = re.compile(
    r"^(no|nope|nah|don'?t|do not|cancel|stop|wait|not now|leave it|"
    r"nahi|nahin|na|mat|ruko|rehne do|"
    r"नहीं|ना|मत|रुको|रहने दो|cancel करो)(?=$|[\s,.!?।])",
    re.IGNORECASE,
)


def classify(text: str) -> Literal["yes", "no"] | None:
    """A short, plain yes or no; anything longer or asking is the model's to read."""
    t = text.strip().lower().strip(" .!,।")
    if not t or "?" in t or len(t.split()) > 6:
        return None
    if _NO.match(t):
        return "no"
    if _YES.match(t):
        return "yes"
    return None


# ─── Actions: brain → page (beside the Stage moves) ───────────────────────────


class LanguageChanged(Action):
    """The call's language moved: the dock's toggle follows it."""

    language: str


# ─── Tool parameters (declared flat to the model) ─────────────────────────────

Period = Literal[
    "today", "last_7_days", "last_30_days", "this_month", "last_month", "last_3_months", "all"
]


class ScreenRequest(BaseModel):
    screen: Screen = Field(description="The screen to open.")
    id: str | None = Field(
        default=None,
        description="account: sb or ca; card_detail/cards_apply: a card id; loan/loan_apply: home, personal, gold or car.",
    )


class TxnQuery(BaseModel):
    account: Literal["all", "sb", "ca", "cc"] | None = Field(
        default=None, description="sb savings, ca current, cc credit card; all by default."
    )
    category: str | None = Field(default=None, description=f"One of: {', '.join(b.CATEGORY_IDS)}.")
    query: str | None = Field(default=None, description="Words in the merchant's name.")
    period: Period | None = Field(default=None, description="A period; or give month.")
    month: str | None = Field(default=None, description="A calendar month, YYYY-MM.")
    min_amount: float | None = None
    max_amount: float | None = None
    direction: Literal["any", "debit", "credit"] | None = None


class ExplainRequest(BaseModel):
    txn_id: str | None = Field(default=None, description="A transaction id from a result, T0197.")
    amount: float | None = Field(default=None, description="The amount the customer named.")
    merchant: str | None = Field(default=None, description="Words of the merchant, if named.")


class SpendingRequest(BaseModel):
    month: str | None = Field(
        default=None, description="this_month, last_month, or YYYY-MM. This month by default."
    )
    category: str | None = Field(default=None, description="A spend category id to point at.")


class CardRequest(BaseModel):
    card: Literal["debit", "credit"]


ChangeKind = Literal[
    "card_block", "card_unblock", "card_control", "card_limit", "bill_pay", "transfer", "fd_book",
    "emi_convert", "offer_accept",
]  # fmt: skip


class ChangeRequest(BaseModel):
    kind: ChangeKind = Field(description="What would change.")
    card: Literal["debit", "credit"] | None = Field(default=None, description="For card kinds.")
    control: (
        Literal[
            "international",
            "online",
            "contactless",
            "atm",
            "atm_daily",
            "pos_daily",
            "online_daily",
        ]
        | None
    ) = Field(
        default=None,
        description="card_control: international|online|contactless|atm; card_limit: atm_daily|pos_daily|online_daily.",
    )
    value: str | None = Field(
        default=None, description="card_control: on or off; card_limit: the new limit in rupees."
    )
    amount: float | None = Field(
        default=None, description="Rupees, for bill_pay, transfer, fd_book, offer_accept."
    )
    target: str | None = Field(
        default=None,
        description="bill_pay: biller id; transfer: beneficiary id; emi_convert: transaction id; offer_accept: offer id.",
    )
    from_account: Literal["sb", "ca"] | None = None
    tenure_months: int | None = Field(
        default=None, description="emi_convert, fd_book, offer_accept."
    )
    payout: Literal["cumulative", "monthly", "quarterly"] | None = None


class ConfirmRequest(BaseModel):
    action_id: str = Field(description="The id request_change returned.")
    yes: bool = Field(description="True only after the customer clearly said yes.")


class AccountForm(BaseModel):
    """Every field optional: pass only what the customer has just told you."""

    full_name: str | None = None
    date_of_birth: str | None = Field(default=None, description="YYYY-MM-DD.")
    gender: Literal["female", "male", "other"] | None = None
    mobile: str | None = Field(default=None, description="10 digits.")
    email: str | None = None
    address_line: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = Field(default=None, description="6 digits.")
    residence_type: Literal["owned", "rented", "family", "company"] | None = None
    pan: str | None = Field(default=None, description="ABCDE1234F.")
    aadhaar: str | None = Field(default=None, description="12 digits.")
    occupation: (
        Literal["salaried", "self_employed", "business", "student", "homemaker", "retired"] | None
    ) = None
    annual_income: Literal["below_5l", "5l_10l", "10l_25l", "25l_50l", "above_50l"] | None = None
    nominee_name: str | None = None
    nominee_relation: (
        Literal["spouse", "father", "mother", "son", "daughter", "brother", "sister", "other"]
        | None
    ) = None
    nominee_dob: str | None = Field(default=None, description="YYYY-MM-DD.")
    variant: Literal["basic", "classic", "privilege", "shakti"] | None = None
    debit_card: Literal["yes", "no"] | None = None
    cheque_book: Literal["yes", "no"] | None = None


class CardForm(BaseModel):
    card_id: str | None = Field(default=None, description=f"One of {', '.join(b.CARD_IDS)}.")
    full_name: str | None = None
    mobile: str | None = None
    pan: str | None = None
    employment: Literal["salaried", "self_employed", "business"] | None = None
    monthly_income: float | None = None
    city: str | None = None


class LoanForm(BaseModel):
    loan_type: Literal["home", "personal", "gold", "car"] | None = None
    full_name: str | None = None
    mobile: str | None = None
    city: str | None = None
    employment: Literal["salaried", "self_employed", "business"] | None = None
    employer: str | None = None
    monthly_income: float | None = None
    existing_emis: float | None = None
    amount: float | None = None
    tenure_months: int | None = None
    property_value: float | None = Field(default=None, description="Home loans.")
    gold_grams: float | None = Field(default=None, description="Gold loans.")
    car_price: float | None = Field(default=None, description="Car loans, on-road price.")
    preferred_time: Literal["morning", "afternoon", "evening"] | None = None


class SubmitRequest(BaseModel):
    form: Literal["open_account", "card_apply", "loan_apply"]


class RankRequest(BaseModel):
    """Monthly spend in rupees by category; or use_my_spend for a signed-in customer."""

    dining: int | None = None
    online: int | None = None
    groceries: int | None = None
    travel: int | None = None
    fuel: int | None = None
    utilities: int | None = None
    other: int | None = None
    use_my_spend: bool = Field(default=False, description="Use her real last-3-months spend.")


class EmiRequest(BaseModel):
    txn_id: str | None = Field(default=None, description="A credit-card transaction id.")
    amount: float | None = None
    tenure_months: int = Field(default=6, description="3, 6, 9, 12, 18 or 24.")


class LoanEmiRequest(BaseModel):
    loan_type: Literal["home", "personal", "gold", "car"]
    amount: float
    tenure_months: int
    rate: float | None = Field(default=None, description="Yearly %; the typical rate if absent.")


class EligibilityRequest(BaseModel):
    loan_type: Literal["home", "personal", "gold", "car"]
    monthly_income: float | None = None
    existing_emis: float | None = None
    tenure_months: int | None = None
    gold_grams: float | None = None
    use_my_data: bool = Field(
        default=False, description="Use the signed-in customer's salary and EMIs."
    )


class LanguageRequest(BaseModel):
    language: Literal["en", "hi"]


# ─── Helpers ──────────────────────────────────────────────────────────────────

#: What counts as spending (CONTRACT.md): sb and cc debits, not money moved.
_NOT_SPEND = {"transfers", "investments", "income", "refunds"}


def spend_txns(month: str) -> list[dict[str, Any]]:
    lo, hi = b.month_bounds(month)
    return [
        t
        for t in b.filter_txns(b.TxnFilter(from_days_ago=lo, to_days_ago=hi, direction="debit"))
        if t["account"] in ("sb", "cc") and t["category"] not in _NOT_SPEND
    ]


def _txn_line(t: dict[str, Any]) -> str:
    sign = "+" if t["direction"] == "credit" else ""
    return (
        f"{t['id']} {b.fmt_date(b.days_ago(t['days_ago']))} {t['merchant']} "
        f"{sign}{b.inr(t['amount'])} ({b.ACCOUNT_NAMES[t['account']]}, {t['category']})"
    )


def _not_done(why: str) -> str:
    return f"Not done: {why}"


class BankBrain(OpenAIBrain):
    """One per session."""

    def __init__(self, *, client: AsyncOpenAI, model: str = MODEL) -> None:
        super().__init__(
            client=client,
            system_instruction=system_instruction(),
            model=model,
            reasoning=REASONING,
        )
        self.lang: str = b.DEFAULT_LANGUAGE
        self.mode = "home"
        self.screen = "home"
        self.signed_in = False
        self._screen_told = ""
        self.stage = Stage(dispatch=lambda a: self.session.dispatch(a), moves=MOVES)
        self._fallback = FallbackLine()
        #: The customer's card state as the brain knows it (moved by confirmed changes).
        self.cards: dict[str, dict[str, Any]] = {
            c["id"]: {"controls": dict(c["controls"]), "limits": dict(c["limits"])}
            for c in b.CUSTOMER["cards"]
        }
        self.balances: dict[str, float] = {
            a["id"]: float(a["balance"]) for a in b.CUSTOMER["accounts"]
        }
        self.converted: set[str] = set()
        #: Confirmation sheets put on screen: action_id → (args, summary); the one awaiting an answer.
        self.asked: dict[str, tuple[dict[str, Any], str]] = {}
        self.awaiting: str | None = None
        self._next_action = 0
        #: Answers the brain sent and is waiting for the page to settle: call_ref → action_id.
        self.answering: dict[str, str] = {}
        #: Forms as the brain filled them, and what the page last said is filled.
        self.forms: dict[str, dict[str, str]] = {f: {} for f in FIELDS}
        self.form_filled: dict[str, set[str]] = {f: set() for f in FIELDS}
        self.submitting: dict[str, str] = {}  # call_ref → form
        self.opened_txn: str | None = None
        self._last_heard = ""
        #: A line of the brain's own for the next quiet spell (a page's answer).
        self._say_next: str | None = None

    # ─── Session ────────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        init = session.init or {}
        lang = str(init.get("lang") or "")
        self.lang = lang if lang in b.LANGUAGES else b.DEFAULT_LANGUAGE
        landing = str(init.get("landing") or "")
        self.mode = landing if landing in MODES else "home"
        self.signed_in = bool(init.get("signed_in")) or self.mode == "banking"
        self.screen = {
            "banking": "dashboard",
            "account": "open_account",
            "cards": "cards",
            "loans": "loans",
        }.get(self.mode, "home")
        await session.configure(
            Config(
                stt=SttConfig(language=self.lang, patience=PATIENCE),
                tts=TtsConfig(voice=b.voice_for(self.lang), language=self.lang),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
            )
        )
        logger.info(
            "bank: session start mode={} lang={} signed_in={}", self.mode, self.lang, self.signed_in
        )
        self.append_note(self._language_note())
        self.append_note(self._screen_note())

    async def greet(self, session: Session) -> str:
        """Written, not generated: the voice starts the moment the call connects."""
        return greeting(self.mode, self.lang, self.signed_in)

    def _language_note(self) -> str:
        name = b.PERSONA["language_names"].get(self.lang, self.lang)
        extra = (
            " Hindi in Devanagari, banking words in English as people say them."
            if self.lang == "hi"
            else ""
        )
        return f"[Speak {name} from now on.{extra}]"

    def _screen_note(self) -> str:
        self._screen_told = f"{self.screen}|{self.signed_in}|{self.mode}"
        return (
            f"[On screen: {self.screen}. Signed in: {'yes' if self.signed_in else 'no'}. "
            f"You are {_MODE_NOTE[self.mode]}.]"
        )

    # ─── Turns ──────────────────────────────────────────────────────────

    def on_user_message(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]:
        return self._answer(session, msg)

    async def _answer(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]:
        self._last_heard = msg.text
        self._say_next = None
        self._settle_expired()
        if self._screen_told != f"{self.screen}|{self.signed_in}|{self.mode}":
            self.append_note(self._screen_note())
        self.append_note(msg.text)
        if self.awaiting is not None and (said := classify(msg.text)) is not None:
            # A plain yes or no to the sheet on screen: pressed here, with no
            # model turn, and the brain's own line says so.
            action_id = self.awaiting
            self._answer_sheet(action_id, said == "yes")
            self.append_note(
                f"[The customer said {said} to {action_id}; you pressed "
                f"{'Confirm' if said == 'yes' else 'Cancel'}. The page's answer follows.]"
            )
            async for s in self.say_line(
                line(self.lang, "doing" if said == "yes" else "cancelled"), remember=True
            ):
                yield s
            return
        async for s in self.respond(session):
            yield s

    def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        return self._reply(session)

    async def _reply(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The model's turn, its ``{show: …}`` cues sent to the page, and a written
        line when it acted on screen and said nothing."""
        turn = self.stage.cued(super().respond(session))
        async for s in self._fallback.speak_if_silent(self, turn):
            yield s
        for unkept in self.stage.end_turn():
            logger.info("bank: unkept promise {} in {!r}", unkept.move.id, unkept.sentence)

    def on_user_idle(self, session: Session, idle: UserIdle) -> AsyncGenerator[Speech, None]:
        return self._idle(session)

    async def _idle(self, session: Session) -> AsyncGenerator[Speech, None]:
        """A quiet spell: say the page's answer if one is owed; never nag."""
        self._settle_expired()
        say, self._say_next = self._say_next, None
        configure_soon(session, Config(idle=IdleConfig(timeout_ms=_IDLE_MS)))
        if say is None:
            return
        async for s in self.say_line(say, remember=True):
            yield s

    def _say_soon(self, text: str) -> None:
        self._say_next = text
        configure_soon(self.session, Config(idle=IdleConfig(timeout_ms=_SAY_NOW_MS)))

    # ─── Page → brain ───────────────────────────────────────────────────

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        event = _EVENTS.parse(msg)
        if event is None:
            return
        if isinstance(event, StageResult):
            result = self.stage.handle(event)
            if result is not None and (note := self._settle(result)) is not None:
                self.append_note(note)
            return
        if isinstance(event, StageHello | StageProgress):
            self.stage.handle(event)
            return
        if isinstance(event, LanguageRequested):
            await self._toggle(session, event.language)
            return
        note = self.apply_event(event)
        if note is not None:
            logger.info("bank: page {}", note)
            self.append_note(note)

    def apply_event(self, event: AppEvent) -> str | None:
        """Fold one page event into the brain's picture; the line the model reads."""
        match event:
            case PageViewed():
                self.screen = event.screen
                self.signed_in = event.signed_in
                mode = mode_of(event.screen)
                if mode != self.mode:
                    self.mode = mode
                    return self._screen_note()
                return None
            case SignedIn():
                self.signed_in = True
                return "[The customer signed in.]"
            case SignedOut():
                self.signed_in = False
                return "[The customer signed out: do not discuss her accounts any more.]"
            case TxnOpened():
                self.opened_txn = event.txn_id
                if event.by == "visitor":
                    t = b.txn(event.txn_id)
                    return f"[The customer opened a transaction: {_txn_line(t) if t else event.txn_id}.]"
                return None
            case CardControlChanged():
                card = self.cards.get(event.card)
                if card is not None:
                    if event.control in card["limits"]:
                        card["limits"][event.control] = int(float(event.value))
                    else:
                        card["controls"][event.control] = event.value in ("on", "true", "yes")
                return (
                    None
                    if event.by == "agent"
                    else f"[The customer changed {event.card} card {event.control} to {event.value}.]"
                )
            case ActionDone():
                return self._action_done(event)
            case FormChanged():
                self.form_filled[event.form] = set(event.filled)
                if event.by == "agent":
                    return None
                return (
                    f"[The customer is filling the {event.form} form by hand, step {event.step}; "
                    f"still missing: {', '.join(event.missing) or 'nothing'}.]"
                )
            case FormSubmitted():
                if event.by == "visitor":
                    self._say_soon(line(self.lang, "submitted", reference=event.reference))
                return f"[The {event.form} form was submitted: reference {event.reference}. {event.summary}]"
            case CardsProfileChanged():
                if event.by == "agent":
                    return None
                return f"[The customer moved the spend sliders; the page now ranks: {', '.join(event.top[:3])}.]"
            case LoanCalcChanged():
                if event.by == "agent":
                    return None
                return (
                    f"[The customer set the {event.loan_type} calculator: {b.inr(event.amount)} for "
                    f"{event.tenure_months} months at {event.rate}%: EMI {b.inr(round(event.emi))}.]"
                )
            case _:
                return None

    def _action_done(self, event: ActionDone) -> str | None:
        asked = self.asked.get(event.action_id)
        if event.outcome == "done" and asked is not None:
            self._apply_change(asked[0])
        if self.awaiting == event.action_id:
            self.awaiting = None
        if event.by == "agent":
            return None  # the move's own result says it
        if event.outcome == "done":
            self._say_soon(
                line(self.lang, "done", summary=event.summary, reference=event.reference or "—")
            )
        else:
            self._say_soon(line(self.lang, "cancelled"))
        return (
            f"[The customer tapped {'Confirm' if event.outcome == 'done' else 'Cancel'} on the sheet: "
            f"{event.summary or event.kind}"
            + (f", reference {event.reference}" if event.reference else "")
            + ".]"
        )

    def _settle_expired(self) -> None:
        for result in self.stage.expire():
            if (note := self._settle(result)) is not None:
                self.append_note(note)

    def _settle(self, result: StageResult) -> str | None:
        """One answer from the page: a confirmation or a submit is said once,
        with its reference; a move the page refused is told, with its options."""
        if result.moved:
            return None
        why = "; ".join(
            f"{r.arg}: {r.why}" + (f" (options: {', '.join(r.options)})" if r.options else "")
            for r in result.refused
        )
        detail = result.detail or why or result.outcome
        if (action_id := self.answering.pop(result.call_ref, None)) is not None:
            if self.awaiting == action_id:
                self.awaiting = None
            if result.outcome in ("applied", "partial"):
                if detail.lower().startswith("cancel"):
                    return f"[The page cancelled {action_id}; nothing changed.]"
                asked = self.asked.get(action_id)
                if asked is not None:
                    self._apply_change(asked[0])
                ref = _reference(detail)
                summary = asked[1] if asked else ""
                self._say_soon(
                    line(self.lang, "done", summary=_sentence(summary), reference=ref or "—")
                )
                return f"[Done on the page: {detail}. You told her; do not say it again.]"
            self._say_soon(line(self.lang, "failed", why=detail))
            return f"[The page did not do {action_id}: {detail}.]"
        if (form := self.submitting.pop(result.call_ref, None)) is not None:
            if result.outcome in ("applied", "partial"):
                ref = _reference(detail) or "—"
                if form == "loan_apply":
                    values = self.forms["loan_apply"]
                    product = b.loan_product(values.get("loan_type", "")) or {}
                    when = TIMES.get(self.lang, TIMES["en"]).get(
                        values.get("preferred_time", ""), ""
                    )
                    self._say_soon(
                        line(
                            self.lang,
                            "lead",
                            product=str(product.get("short", "loans")).lower(),
                            reference=ref,
                            time=when,
                        )
                    )
                else:
                    self._say_soon(line(self.lang, "submitted", reference=ref))
                return f"[The {form} form is submitted: {detail}. The lead card is on screen. You told her the reference.]"
            self._say_soon(line(self.lang, "failed", why=detail))
            return f"[The {form} form was not submitted: {detail}.]"
        if result.outcome in ("applied", "partial", "undone"):
            return None
        move = self.stage.move_of(result.call_ref)
        what = move.id if move else result.move
        if result.outcome == "unknown":
            return f"[The page has not answered {what} yet; do not say it happened.]"
        return f"[On screen, {what} did not happen: {detail}. Never say it did; use the options or ask.]"

    async def _toggle(self, session: Session, language: str) -> None:
        """The customer pressed the other language on the dock."""
        if language not in b.LANGUAGES or language == self.lang:
            return
        await session.configure(self._speaking(language))
        self.append_note(self._language_note())
        self._say_soon(line(self.lang, "switched"))

    def _speaking(self, language: str) -> Config:
        """Both legs of ``language``, and the dock's toggle moved to it."""
        self.lang = language
        self.session.dispatch(LanguageChanged(language=language))
        return Config(
            stt=SttConfig(language=language, patience=PATIENCE),
            tts=TtsConfig(voice=b.voice_for(language), language=language),
        )

    # ─── Moves ──────────────────────────────────────────────────────────

    def _send(self, move: str, args: dict[str, Any]) -> str:
        clean = {k: v for k, v in args.items() if v is not None}
        ref = self.stage.send(move, clean, queue=False)
        logger.info("bank: move {} {}", move, clean)
        return ref

    def _answer_sheet(self, action_id: str, yes: bool) -> None:
        ref = self._send("confirm.answer", {"action_id": action_id, "yes": yes})
        self.answering[ref] = action_id
        self.awaiting = None

    def _apply_change(self, args: dict[str, Any]) -> None:
        """A confirmed change, in the brain's picture of her bank."""
        kind = args.get("kind")
        card = self.cards.get(str(args.get("card")))
        if kind == "card_block" and card:
            card["controls"]["blocked"] = True
        elif kind == "card_unblock" and card:
            card["controls"]["blocked"] = False
        elif kind == "card_control" and card:
            card["controls"][str(args["control"])] = args.get("value") == "on"
        elif kind == "card_limit" and card:
            card["limits"][str(args["control"])] = int(float(args["value"]))
        elif kind == "emi_convert":
            self.converted.add(str(args["target"]))
        elif kind in ("bill_pay", "transfer", "fd_book"):
            acc = str(args.get("from_account") or "sb")
            self.balances[acc] = self.balances.get(acc, 0.0) - float(args.get("amount") or 0)
        elif kind == "offer_accept":
            o = b.offer(str(args.get("target")))
            if o and o["kind"] == "loan":
                self.balances["sb"] += float(args.get("amount") or o["amount"])

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Callable[..., Any]]:
        return [
            self.open_screen,
            self.find_transactions,
            self.explain_transaction,
            self.spending,
            self.card_details,
            self.request_change,
            self.confirm_change,
            self.fill_account_form,
            self.fill_card_application,
            self.fill_loan_application,
            self.submit_application,
            self.rank_cards,
            self.plan_emi,
            self.loan_emi,
            self.loan_eligibility,
            self.set_language,
        ]

    def _need_sign_in(self) -> str | None:
        if self.signed_in:
            return None
        return "she is not signed in. Offer to open her banking (open_screen dashboard), which signs her in."

    async def open_screen(self, req: ScreenRequest) -> str:
        """Open a screen of the bank's site or app (an app screen signs a demo visitor in)."""
        self._send("nav.open", {"screen": req.screen, "id": req.id})
        if req.screen in _APP_SCREENS:
            self.signed_in = True
        self.screen = req.screen
        self.mode = mode_of(req.screen)
        landed(line(self.lang, "open"))
        return f"Opening {req.screen}. You are now {_MODE_NOTE[self.mode]}."

    @needs_result_now
    async def find_transactions(self, q: TxnQuery) -> str:
        """Find her transactions and show them on the transactions screen: totals, by category, the top ones."""
        if (why := self._need_sign_in()) is not None:
            return _not_done(why)
        if q.category and q.category not in b.CATEGORY_IDS:
            return _not_done(f"no category {q.category}; use one of {', '.join(b.CATEGORY_IDS)}")
        lo, hi, label = self._period(q.period, q.month)
        f = b.TxnFilter(
            account=q.account,
            category=q.category,
            query=q.query,
            from_days_ago=lo,
            to_days_ago=hi,
            min_amount=q.min_amount,
            max_amount=q.max_amount,
            direction=q.direction,
        )
        found = b.filter_txns(f)
        what = (
            " ".join(
                x
                for x in (
                    b.CATEGORY_NAMES.get(q.category or "", ""),
                    f'"{q.query}"' if q.query else "",
                    label,
                )
                if x
            )
            or "All transactions"
        )
        self._send(
            "txn.find",
            {
                "account": q.account,
                "category": q.category,
                "query": q.query,
                "from_days_ago": lo,
                "to_days_ago": hi,
                "min_amount": q.min_amount,
                "max_amount": q.max_amount,
                "direction": q.direction,
                "label": what,
            },
        )
        self.screen, self.mode = "transactions", "banking"
        landed(line(self.lang, "show_txns"))
        out = sum(t["amount"] for t in found if t["direction"] == "debit")
        inn = sum(t["amount"] for t in found if t["direction"] == "credit")
        lines = [f"{len(found)} transactions ({what}): debits {b.inr(out)}, credits {b.inr(inn)}."]
        if not q.category and found:
            by: dict[str, float] = {}
            for t in found:
                if t["direction"] == "debit":
                    by[t["category"]] = by.get(t["category"], 0.0) + t["amount"]
            top = sorted(by.items(), key=lambda kv: -kv[1])[:5]
            lines.append(
                "Debits by category: "
                + "; ".join(f"{b.CATEGORY_NAMES[k]} {b.inr(v)}" for k, v in top)
                + "."
            )
        lines += [_txn_line(t) for t in found[:8]]
        if len(found) > 8:
            lines.append(f"…and {len(found) - 8} more on screen.")
        return "\n".join(lines)

    def _period(self, period: str | None, month: str | None) -> tuple[int | None, int | None, str]:
        now = b.today()
        this = b.month_key(now)
        if month:
            key = month if re.fullmatch(r"\d{4}-\d{2}", month) else this
            lo, hi = b.month_bounds(key)
            return lo, hi, f"in {b.month_name(key)}"
        match period:
            case "today":
                return 0, 0, "today"
            case "last_7_days":
                return 6, 0, "in the last 7 days"
            case "last_30_days":
                return 29, 0, "in the last 30 days"
            case "this_month":
                lo, hi = b.month_bounds(this)
                return lo, hi, f"in {b.month_name(this)}"
            case "last_month":
                key = b.shift_month(this, -1)
                lo, hi = b.month_bounds(key)
                return lo, hi, f"in {b.month_name(key)}"
            case "last_3_months":
                return 89, 0, "in the last 3 months"
            case _:
                return None, None, ""

    @needs_result_now
    async def explain_transaction(self, req: ExplainRequest) -> str:
        """Explain one transaction (a charge she asks about) and open it on screen. With no
        arguments: the one she has open."""
        if (why := self._need_sign_in()) is not None:
            return _not_done(why)
        t: dict[str, Any] | None = None
        if req.txn_id:
            t = b.txn(req.txn_id)
        elif req.amount is not None or req.merchant:
            hits = b.filter_txns(
                b.TxnFilter(
                    query=req.merchant,
                    min_amount=None if req.amount is None else req.amount - 0.5,
                    max_amount=None if req.amount is None else req.amount + 0.5,
                )
            )
            if len(hits) > 1:
                self._send(
                    "txn.find",
                    {
                        "query": req.merchant,
                        "min_amount": None if req.amount is None else req.amount - 0.5,
                        "max_amount": None if req.amount is None else req.amount + 0.5,
                        "label": f"{b.inr(req.amount)} transactions"
                        if req.amount is not None
                        else req.merchant,
                    },
                )
                landed(line(self.lang, "show_txns"))
                return "Several match; ask which one:\n" + "\n".join(_txn_line(h) for h in hits[:6])
            t = hits[0] if hits else None
        elif self.opened_txn:
            t = b.txn(self.opened_txn)
        if t is None:
            return _not_done("no transaction matches; ask for the amount or the merchant")
        self._send("txn.open", {"txn_id": t["id"]})
        self.opened_txn = t["id"]
        self.screen, self.mode = "transactions", "banking"
        landed(line(self.lang, "show_txn"))
        facts = [
            _txn_line(t),
            f"On the statement as: {t['description']}. Mode: {t['mode']}. Reference {t['ref']}.",
        ]
        if t.get("note"):
            facts.append(f"Note: {t['note']}")
        if t["account"] == "cc" and t["direction"] == "debit":
            if t["id"] in self.converted:
                facts.append("Already converted to EMI.")
            elif t.get("emi_eligible"):
                facts.append("Eligible to convert to EMI (plan_emi).")
        return "\n".join(facts)

    @needs_result_now
    async def spending(self, req: SpendingRequest) -> str:
        """Her spending for a month by category (sb and card debits, not transfers or
        investments), compared with the month before; opens Insights."""
        if (why := self._need_sign_in()) is not None:
            return _not_done(why)
        this = b.month_key(b.today())
        key = {"this_month": this, "last_month": b.shift_month(this, -1), None: this}.get(
            req.month, req.month or this
        )
        if not re.fullmatch(r"\d{4}-\d{2}", key):
            key = this
        if req.category and req.category not in b.CATEGORY_IDS:
            return _not_done(f"no category {req.category}; use one of {', '.join(b.CATEGORY_IDS)}")
        txns = spend_txns(key)
        prev = spend_txns(b.shift_month(key, -1))
        by: dict[str, float] = {}
        for t in txns:
            by[t["category"]] = by.get(t["category"], 0.0) + t["amount"]
        total = sum(by.values())
        before = sum(t["amount"] for t in prev)
        self._send("insights.show", {"month": key, "category": req.category})
        self.screen, self.mode = "insights", "banking"
        landed(line(self.lang, "spending"))
        lines = [
            f"{b.month_name(key)}: spent {b.inr(total)} in {len(txns)} payments "
            f"({b.month_name(b.shift_month(key, -1))}: {b.inr(before)})."
        ]
        lines.append(
            "By category: "
            + "; ".join(
                f"{b.CATEGORY_NAMES[k]} {b.inr(v)}"
                for k, v in sorted(by.items(), key=lambda kv: -kv[1])
            )
            + "."
        )
        if req.category:
            mine = [t for t in txns if t["category"] == req.category]
            was = sum(t["amount"] for t in prev if t["category"] == req.category)
            merchants: dict[str, float] = {}
            for t in mine:
                merchants[t["merchant"]] = merchants.get(t["merchant"], 0.0) + t["amount"]
            top = sorted(merchants.items(), key=lambda kv: -kv[1])[:3]
            lines.append(
                f"{b.CATEGORY_NAMES[req.category]}: {b.inr(sum(t['amount'] for t in mine))} in {len(mine)} payments "
                f"(month before: {b.inr(was)}). Top: "
                + "; ".join(f"{k} {b.inr(v)}" for k, v in top)
                + "."
            )
        if key == this:
            lines.append(f"This month runs to today, {b.fmt_date(b.today())}.")
        return "\n".join(lines)

    @needs_result_now
    async def card_details(self, req: CardRequest) -> str:
        """Her debit or credit card: status, controls, limits, and for the credit card its
        limit, dues and reward points. Opens the card's screen."""
        if (why := self._need_sign_in()) is not None:
            return _not_done(why)
        data = next(c for c in b.CUSTOMER["cards"] if c["id"] == req.card)
        state = self.cards[req.card]
        self._send("nav.open", {"screen": f"{req.card}_card"})
        self.screen, self.mode = f"{req.card}_card", "banking"
        landed(line(self.lang, "card"))
        ctl = state["controls"]
        lines = [
            f"{data['name']} ending {data['last4']}, expires {data['expiry']}. "
            + ("BLOCKED. " if ctl["blocked"] else "Active. ")
            + "Controls: "
            + ", ".join(f"{k} {'on' if v else 'off'}" for k, v in ctl.items() if k != "blocked")
            + ".",
            "Daily limits: "
            + "; ".join(
                f"{k} {b.inr(v)} (max {b.inr(data['limits_max'][k])})"
                for k, v in state["limits"].items()
            )
            + ".",
        ]
        if req.card == "credit":
            st = data["statement"]
            due = b.fmt_date(b.days_ago(-int(st["due_days_from_now"])))
            pe = data["points_expiring"]
            lines.append(
                f"Credit limit {b.inr(data['credit_limit'])}, outstanding {b.inr(data['outstanding'])}, "
                f"available {b.inr(data['available'])}. Statement due {b.inr(st['total_due'])}, minimum "
                f"{b.inr(st['min_due'])}, by {due}. Unbilled {b.inr(data['unbilled'])}. "
                f"Reward points {data['reward_points']:,} ({pe['points']:,} expire in {pe['days_from_now']} days)."
            )
        return "\n".join(lines)

    @needs_result_now
    async def request_change(self, req: ChangeRequest) -> str:
        """Put a change on screen for her to confirm (block/unblock a card, a card control or
        limit, pay a bill, a transfer, book an FD, convert a spend to EMI, accept an offer).
        Nothing changes until she says yes. Returns the summary to read and the action_id."""
        if (why := self._need_sign_in()) is not None:
            return _not_done(why)
        summary, problem = self._describe(req)
        if problem is not None:
            return _not_done(problem)
        self._next_action += 1
        action_id = f"A{self._next_action}"
        args = {"action_id": action_id, **req.model_dump()}
        if req.kind == "bill_pay" and req.amount is None:
            args["amount"] = _bill_due(str(req.target))
        if req.kind == "offer_accept" and req.amount is None:
            o = b.offer(str(req.target)) or {}
            if o.get("amount") is not None:
                args["amount"] = float(o["amount"])
        self._send("confirm.ask", args)
        self.asked[action_id] = (args, summary)
        self.awaiting = action_id
        landed(line(self.lang, "confirm"))
        return (
            f"{action_id} is on screen to confirm: {summary}. Say what it will do in one line and ask "
            "if she wants to go ahead; then wait for her answer."
        )

    def _describe(self, req: ChangeRequest) -> tuple[str, str | None]:
        """The change in words, or why it cannot be asked."""
        kind = req.kind
        if kind in ("card_block", "card_unblock", "card_control", "card_limit"):
            if req.card is None:
                return "", "say which card: debit or credit"
            data = next(c for c in b.CUSTOMER["cards"] if c["id"] == req.card)
            state = self.cards[req.card]
            name = f"{req.card} card ending {data['last4']}"
            if kind == "card_block":
                if state["controls"]["blocked"]:
                    return "", f"the {name} is already blocked"
                return f"block the {name}", None
            if kind == "card_unblock":
                if not state["controls"]["blocked"]:
                    return "", f"the {name} is not blocked"
                return f"unblock the {name}", None
            if kind == "card_control":
                if req.control not in ("international", "online", "contactless", "atm"):
                    return "", "control is one of international, online, contactless, atm"
                if req.value not in ("on", "off"):
                    return "", "value is on or off"
                if state["controls"][req.control] == (req.value == "on"):
                    return "", f"{req.control} use is already {req.value} on the {name}"
                return f"turn {req.control} use {req.value} on the {name}", None
            if req.control not in data["limits_max"]:
                return "", f"limit is one of {', '.join(data['limits_max'])}"
            try:
                value = int(float(str(req.value).replace(",", "")))
            except ValueError:
                return "", "say the new limit in rupees"
            top = int(data["limits_max"][req.control])
            if value < 0 or value > top:
                return "", f"the {req.control} limit can be at most {b.inr(top)}"
            return (
                f"set the {name}'s {str(req.control).replace('_', ' ')} limit to {b.inr(value)}",
                None,
            )
        acc = req.from_account or "sb"
        balance = self.balances.get(acc, 0.0)
        if kind == "bill_pay":
            reg = next(
                (r for r in b.CUSTOMER["registered_billers"] if r["biller_id"] == req.target), None
            )
            if reg is None:
                ids = [r["biller_id"] for r in b.CUSTOMER["registered_billers"]]
                return "", f"target is a registered biller: {', '.join(ids)}"
            amount = req.amount if req.amount is not None else float(reg["due"])
            if amount > balance:
                return (
                    "",
                    f"{b.inr(amount)} is more than the {b.ACCOUNT_NAMES[acc]} balance {b.inr(balance)}",
                )
            bl = b.biller(str(req.target)) or {"name": req.target}
            return f"pay {bl['name']} {b.inr(amount)} from {b.ACCOUNT_NAMES[acc]}", None
        if kind == "transfer":
            ben = b.beneficiary(str(req.target))
            if ben is None:
                return (
                    "",
                    f"target is a beneficiary: {', '.join(x['id'] for x in b.CUSTOMER['beneficiaries'])}",
                )
            if req.amount is None or req.amount <= 0:
                return "", "say how much to send"
            if req.amount > balance:
                return (
                    "",
                    f"{b.inr(req.amount)} is more than the {b.ACCOUNT_NAMES[acc]} balance {b.inr(balance)}",
                )
            if req.amount > ben["limit"]:
                return "", f"{ben['name']}'s transfer limit is {b.inr(ben['limit'])}"
            return (
                f"send {b.inr(req.amount)} to {ben['name']} ({ben['bank']} {ben['account_masked']}) from {b.ACCOUNT_NAMES[acc]}",
                None,
            )
        if kind == "fd_book":
            fd = b.PRODUCTS["fd"]
            if req.amount is None or req.amount < fd["min_amount"]:
                return "", f"an FD starts at {b.inr(fd['min_amount'])}"
            months = req.tenure_months or 12
            if m.fd_rate(months) is None:
                return "", "tenure is 6 to 120 months"
            if req.amount > balance:
                return (
                    "",
                    f"{b.inr(req.amount)} is more than the {b.ACCOUNT_NAMES[acc]} balance {b.inr(balance)}",
                )
            payout = req.payout or "cumulative"
            q = m.fd_quote(req.amount, months, payout)
            tail = (
                f"maturity {b.inr(q['maturity'])}"
                if payout == "cumulative"
                else f"{b.inr(q['payout_each'])} paid out {payout}"
            )
            return f"book a {months}-month FD of {b.inr(req.amount)} at {q['rate']}%, {tail}", None
        if kind == "emi_convert":
            t = b.txn(str(req.target))
            if t is None or not t.get("emi_eligible"):
                ok = [x["id"] for x in b.CUSTOMER["transactions"] if x.get("emi_eligible")]
                return "", f"target is an EMI-eligible card spend: {', '.join(ok)}"
            if t["id"] in self.converted:
                return "", "that spend is already on EMI"
            months = req.tenure_months or 6
            if months not in m.EMI_TENURES:
                return "", f"tenure is one of {', '.join(map(str, m.EMI_TENURES))} months"
            row = m.card_emi(t["amount"], months)
            return (
                f"convert {t['merchant']} {b.inr(t['amount'])} into {months} EMIs of {b.inr(row.emi)} at "
                f"{row.rate}% (interest {b.inr(row.total_interest)}, fee {b.inr(row.processing_fee)} + GST "
                f"{b.inr(row.gst_on_fee)})",
                None,
            )
        o = b.offer(str(req.target))
        if o is None:
            return "", f"target is an offer: {', '.join(x['id'] for x in b.CUSTOMER['offers'])}"
        if o["kind"] == "card":
            return "", "the card upgrade is an application: open cards_apply for that card"
        amount = req.amount if req.amount is not None else float(o["amount"])
        months = req.tenure_months or int(o["tenure_max_months"])
        if amount > o["amount"]:
            return "", f"the offer is up to {b.inr(o['amount'])}"
        if months > o["tenure_max_months"] or months < 12:
            return "", f"tenure is 12 to {o['tenure_max_months']} months"
        e = m.rnd(m.emi(amount, float(o["rate"]), months))
        return (
            f"take the pre-approved personal loan of {b.inr(amount)} at {o['rate']}% for {months} months, EMI {b.inr(e)}, credited to savings",
            None,
        )

    async def confirm_change(self, req: ConfirmRequest) -> str:
        """Press Confirm (yes=true) or Cancel on the sheet, after her clear spoken answer."""
        if req.action_id not in self.asked:
            return _not_done(f"no confirmation {req.action_id} is on screen")
        if req.yes and classify(self._last_heard) != "yes" and not _sounds_yes(self._last_heard):
            return _not_done("she has not clearly said yes; ask her")
        self._answer_sheet(req.action_id, req.yes)
        landed(line(self.lang, "doing" if req.yes else "cancelled"))
        return "Pressed. The page's answer comes next; do not say it is done before it."

    # ─── Forms ──────────────────────────────────────────────────────────

    def _fill(self, form: str, values: dict[str, Any]) -> str:
        filled: list[str] = []
        refused: list[str] = []
        for field in FIELDS[form]:
            raw = values.get(field)
            if raw is None or raw == "":
                continue
            raw_s = str(int(raw)) if isinstance(raw, float) and raw.is_integer() else str(raw)
            value, why = check(form, field, raw_s)
            if value is None:
                refused.append(f"{field} ({why})")
                continue
            self.forms[form][field] = value
            self._send("form.fill", {"form": form, "field": field, "value": value})
            filled.append(field)
        have = {**dict.fromkeys(self.form_filled[form], "x"), **self.forms[form]}
        left = missing(form, have)
        if form == "open_account" and left:
            self._send("form.step", {"form": form, "step": STEP_OF[left[0]]})
        if filled:
            landed(line(self.lang, "filled"))
        parts = [f"Filled: {', '.join(filled) or 'nothing'}."]
        if refused:
            parts.append(f"Refused, ask again: {'; '.join(refused)}.")
        if left:
            where = f" (step {STEP_OF[left[0]]})" if form == "open_account" else ""
            parts.append(f"Still needed{where}: {', '.join(left)}.")
        else:
            parts.append("Everything is filled: show the review and ask for a yes to submit.")
            if form == "open_account":
                self._send("form.step", {"form": form, "step": 6})
        return " ".join(parts)

    @needs_result_now
    async def fill_account_form(self, f: AccountForm) -> str:
        """Put what the customer just said into the savings account application (only the
        fields they gave). Returns what was filled, refused, and what is still needed."""
        return self._fill("open_account", f.model_dump())

    @needs_result_now
    async def fill_card_application(self, f: CardForm) -> str:
        """Put what the customer said into the credit card application."""
        return self._fill("card_apply", f.model_dump())

    @needs_result_now
    async def fill_loan_application(self, f: LoanForm) -> str:
        """Put what the customer said into the loan application."""
        return self._fill("loan_apply", f.model_dump())

    async def submit_application(self, req: SubmitRequest) -> str:
        """Press Submit on a form, only right after she clearly said yes to submitting."""
        if classify(self._last_heard) != "yes" and not _sounds_yes(self._last_heard):
            return _not_done("she has not said yes to submitting; ask her first")
        have = {**dict.fromkeys(self.form_filled[req.form], "x"), **self.forms[req.form]}
        if left := missing(req.form, have):
            return _not_done(f"still needed: {', '.join(left)}")
        ref = self._send("form.submit", {"form": req.form})
        self.submitting[ref] = req.form
        landed(line(self.lang, "doing"))
        return "Submitting; the page's answer comes next."

    # ─── Cards and loans ────────────────────────────────────────────────

    @needs_result_now
    async def rank_cards(self, req: RankRequest) -> str:
        """Rank all the bank's cards by yearly value for a monthly spend profile and show the
        top three side by side."""
        if req.use_my_spend:
            if (why := self._need_sign_in()) is not None:
                return _not_done(why)
            profile = m.customer_profile()
        else:
            profile = {c: float(getattr(req, c) or 0) for c in b.CARD_CATEGORIES}
            if not any(profile.values()):
                return _not_done("ask how much they spend a month, by category")
        ranked = m.rank_cards(profile)
        top = [v.card_id for v in ranked[:3]]
        self._send("cards.compare", {"card_ids": top, **{k: int(v) for k, v in profile.items()}})
        self.screen, self.mode = "cards_compare", "cards"
        landed(line(self.lang, "compare"))
        lines = [
            "Monthly spend: " + ", ".join(f"{k} {b.inr(v)}" for k, v in profile.items() if v) + "."
        ]
        for i, v in enumerate(ranked, 1):
            card = b.card_product(v.card_id) or {}
            lines.append(
                f"{i}. {card.get('name')}: about {b.inr(v.net_yearly)} a year net "
                f"(rewards {b.inr(v.yearly_rewards)}, fuel saving {b.inr(v.fuel_saving_yearly)}, "
                f"lounge value {b.inr(v.lounge_value)}, fee "
                + ("waived" if v.fee_waived else b.inr(v.fee))
                + ")."
            )
        return "\n".join(lines)

    @needs_result_now
    async def plan_emi(self, req: EmiRequest) -> str:
        """Show the EMI for every tenure for a card spend (or an amount), this tenure selected."""
        amount = req.amount
        if req.txn_id:
            t = b.txn(req.txn_id)
            if t is None or not t.get("emi_eligible"):
                ok = [x["id"] for x in b.CUSTOMER["transactions"] if x.get("emi_eligible")]
                return _not_done(f"not an EMI-eligible card spend; eligible: {', '.join(ok)}")
            amount = float(t["amount"])
        if amount is None or amount < b.PRODUCTS["emi"]["min_amount"]:
            return _not_done(
                f"EMI needs a spend of at least {b.inr(b.PRODUCTS['emi']['min_amount'])}"
            )
        if req.tenure_months not in m.EMI_TENURES:
            return _not_done(f"tenure is one of {', '.join(map(str, m.EMI_TENURES))} months")
        self._send(
            "emi.plan",
            {
                "txn_id": req.txn_id,
                "amount": None if req.txn_id else amount,
                "tenure_months": req.tenure_months,
            },
        )
        self.screen, self.mode = "cards_emi", "cards"
        landed(line(self.lang, "emi"))
        rows = [
            f"{r.months} months at {r.rate}%: EMI {b.inr(r.emi)}, interest {b.inr(r.total_interest)}, "
            f"fee {b.inr(r.processing_fee)} + GST {b.inr(r.gst_on_fee)}"
            + (" (selected)" if r.months == req.tenure_months else "")
            for r in m.card_emi_table(amount)
        ]
        return f"EMI plans for {b.inr(amount)}:\n" + "\n".join(rows)

    @needs_result_now
    async def loan_emi(self, req: LoanEmiRequest) -> str:
        """Work out a loan's EMI and put it in the calculator with the maths on screen."""
        loan = b.loan_product(req.loan_type)
        assert loan is not None
        if not loan["amount_min"] <= req.amount <= loan["amount_max"]:
            return _not_done(
                f"the {loan['short']} is {b.inr(loan['amount_min'])} to {b.inr(loan['amount_max'])}"
            )
        if not loan["tenure_min_months"] <= req.tenure_months <= loan["tenure_max_months"]:
            return _not_done(
                f"tenure is {loan['tenure_min_months']} to {loan['tenure_max_months']} months"
            )
        rate = req.rate if req.rate is not None else float(loan["rate_typical"])
        if not loan["rate_min"] <= rate <= loan["rate_max"]:
            return _not_done(f"the rate is {loan['rate_min']}% to {loan['rate_max']}%")
        e = m.rnd(m.emi(req.amount, rate, req.tenure_months))
        total = e * req.tenure_months
        self._send(
            "loan.calc",
            {
                "loan_type": req.loan_type,
                "amount": req.amount,
                "tenure_months": req.tenure_months,
                "rate": rate,
            },
        )
        self.screen, self.mode = "loan", "loans"
        landed(line(self.lang, "loan_emi"))
        return (
            f"{loan['short']} of {b.inr(req.amount)} for {req.tenure_months} months at {rate}%: EMI {b.inr(e)}. "
            f"Total interest {b.inr(total - req.amount)}, total payable {b.inr(total)}. "
            f"Working: r = {rate}/12/100 = {rate / 1200:.5f} a month; EMI = P·r·(1+r)^n / ((1+r)^n - 1). "
            f"Processing fee: {loan['processing_fee']}."
        )

    @needs_result_now
    async def loan_eligibility(self, req: EligibilityRequest) -> str:
        """Work out how much they can borrow (income and existing EMIs; gold: grams) and show it."""
        loan = b.loan_product(req.loan_type)
        assert loan is not None
        income, existing = req.monthly_income, req.existing_emis
        if req.use_my_data:
            if (why := self._need_sign_in()) is not None:
                return _not_done(why)
            income = float(b.CUSTOMER["profile"]["monthly_income"])
            existing = float(sum(x["emi"] for x in b.CUSTOMER["loans"]))
        if req.loan_type == "gold":
            if not req.gold_grams:
                return _not_done("ask how many grams of gold (22 carat)")
        elif not income:
            return _not_done("ask their monthly income and existing EMIs")
        el = m.loan_eligibility(
            loan,
            monthly_income=income,
            existing_emis=existing,
            tenure_months=req.tenure_months,
            gold_grams=req.gold_grams,
        )
        self._send(
            "loan.eligibility",
            {
                "loan_type": req.loan_type,
                "monthly_income": income,
                "existing_emis": existing,
                "tenure_months": el.tenure_months,
                "gold_grams": req.gold_grams,
            },
        )
        self.screen, self.mode = "loan", "loans"
        landed(line(self.lang, "eligibility"))
        if req.loan_type == "gold":
            per = loan["gold_rate_per_gram_22k"]
            return (
                f"{req.gold_grams} g at {b.inr(per)} a gram (sample rate) at {loan['ltv_pct']}%: up to {b.inr(el.max_amount)}, "
                f"at {el.rate}% a year."
            )
        foir = int(float(loan["foir"]) * 100)
        if income and income < loan["min_income_monthly"]:
            note = f" Below the minimum income of {b.inr(loan['min_income_monthly'])} a month for this loan."
        else:
            note = ""
        return (
            f"Affordable EMI {b.inr(el.max_emi or 0)} ({foir}% of {b.inr(income or 0)} minus {b.inr(existing or 0)} existing EMIs). "
            f"At {el.rate}% for {el.tenure_months} months: up to {b.inr(el.max_amount)}.{note}"
        )

    async def set_language(self, req: LanguageRequest) -> str:
        """Switch the call's language (both what you hear and how you speak)."""
        if req.language == self.lang:
            return f"Already speaking {req.language}."
        configure_soon(self.session, self._speaking(req.language))
        self.append_note(self._language_note())
        return (
            f"Switched. From your next sentence, speak {b.PERSONA['language_names'][req.language]}."
        )


def _reference(detail: str) -> str | None:
    hit = re.search(r"\b(ANV[-A-Z0-9]*\d{4,})\b", detail)
    return hit.group(1) if hit else None


def _sentence(summary: str) -> str:
    """'block the debit card ending 7712' → 'Block the debit card ending 7712.'"""
    s = summary.strip()
    return (s[:1].upper() + s[1:] + ("" if s.endswith(".") else ".")) if s else ""


def _bill_due(biller_id: str) -> float | None:
    reg = next((r for r in b.CUSTOMER["registered_billers"] if r["biller_id"] == biller_id), None)
    return float(reg["due"]) if reg else None


_YES_ANYWHERE = re.compile(
    r"\b(yes|go ahead|do it|please do|confirm|submit it|haan|haanji|kar do|kardo|bilkul|हाँ|हां|कर दो|कर दीजिए|बिल्कुल)(?=$|[\s,.!?।])",
    re.IGNORECASE,
)


def _sounds_yes(text: str) -> bool:
    """A yes inside a longer sentence ("yes, go ahead and block it")."""
    return bool(_YES_ANYWHERE.search(text)) and not _NO.match(text.strip().lower())


__all__ = ["BankBrain", "classify", "mode_of"]
