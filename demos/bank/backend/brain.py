"""BankBrain — the assistant of Global Bank, a fictional Indian retail bank.

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
speak (her accounts and balances, transactions, a transaction, spending, a card,
a ranking, an EMI table, a loan EMI, eligibility), opening a screen, which reads
back what that screen shows from her data (B1: "I'll open your accounts" and a
page answering "dashboard is already open" left the call silent), and the two
checks whose verdict it must say before it asks anything (``request_change``,
the form fills). The confirmation answer, a submit and the language switch are
not: the page's answer, or the switch, is said by the brain's own line.

**Never a promise and then silence.** A read the customer asked to hear
(``owe``) is said by the brain from her data when the model's turn says nothing
after the tool ran; a move the page refuses is told to her with a written line
even after the turn has ended; the language switch is said in the new language.

**Anything that changes state is confirmed.** ``request_change`` puts a
confirmation sheet on screen; nothing changes until the customer says yes (the
brain hears a plain yes or no itself and presses the button, with no model
turn) or taps Confirm. The outcome is the page's: the brain says "done" only
when the page's result says so, with its reference.

**Persona and languages** come from ``persona.json``: both speech legs are set in
``on_session_start`` from the language the visitor picked, and move together on
the toggle or ``set_language``.

**A call outlives a dropped socket** (CONTRACT.md, Redial; SDK 0.15.0): redial is
on wherever Voqalize offers it, and the brain a redial starts on a session this
process still holds adopts that call whole (``rejoin.py``) and does not greet it
again.
"""

from __future__ import annotations

import contextlib
import re
from collections.abc import AsyncGenerator, Callable
from contextvars import ContextVar
from dataclasses import dataclass
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
    SpeechStart,
    UserIdle,
    UserMessage,
)
from voqalize.sdk.openai import OpenAIBrain, needs_result_now
from voqalize.sdk.stage import Stage
from voqalize.sdk.stage.wire import StageHello, StageProgress, StageResult
from voqalize.sdk.wire import Config, IdleConfig, RedialConfig, SttConfig, TtsConfig

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
from .rejoin import Rejoin
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
    "cards": "the card salesperson: a few right questions (income, how they spend), then "
    "recommend_card with the money it is worth to them, then a nudge to apply",
    "loans": "the loan salesperson: a few right questions (which loan, income and EMIs, how much), "
    "then recommend_loan with the EMI and what they save, then a nudge to apply",
    "home": "the adviser at the front door: find what they came for, take them there, and sell",
}


def product_on(path: str) -> str | None:
    """The product a public page is about, from its path (``/loans/home``,
    ``/cards/voyage``, ``/loans/apply?type=car``), in words; None elsewhere."""
    p, _, query = path.partition("?")
    p = p.rstrip("/")
    q = dict(kv.split("=", 1) for kv in query.split("&") if "=" in kv)
    loan_id = (
        q.get("type")
        if p == "/loans/apply"
        else p.removeprefix("/loans/")
        if p.startswith("/loans/")
        else None
    )
    if loan_id and (loan := b.loan_product(loan_id)):
        return f"the {loan['short']} page"
    card_id = (
        q.get("card")
        if p == "/cards/apply"
        else p.removeprefix("/cards/")
        if p.startswith("/cards/")
        else None
    )
    if card_id and (card := b.card_product(card_id)):
        return f"the {card['name']} page"
    return None


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


class AccountsRequest(BaseModel):
    account: Literal["sb", "ca"] | None = Field(
        default=None, description="One account (sb savings, ca current); both by default."
    )


class TxnQuery(BaseModel):
    account: Literal["all", "bank", "sb", "ca", "cc"] | None = Field(
        default=None,
        description="sb savings, ca current, cc credit card, bank = savings and current together "
        "(no credit card); all by default.",
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


class CardPitchRequest(BaseModel):
    """What the visitor told you: their monthly income and how they spend. Spend by
    category in rupees a month; or only a total and where most of it goes."""

    monthly_income: float | None = Field(
        default=None,
        description="Take-home a month, rupees, as THEY said it. Never a guess: leave it out "
        "until they tell you.",
    )
    dining: int | None = None
    online: int | None = None
    groceries: int | None = None
    travel: int | None = None
    fuel: int | None = None
    utilities: int | None = None
    other: int | None = None
    total_monthly: int | None = Field(
        default=None,
        description="Only when they gave a total, not a split: all card spend a month.",
    )
    mostly_on: Literal["dining", "online", "groceries", "travel", "fuel", "utilities"] | None = (
        Field(default=None, description="With total_monthly: where most of it goes.")
    )
    use_my_data: bool = Field(
        default=False, description="Signed in: her real salary and last-3-months spend."
    )


class LoanPitchRequest(BaseModel):
    """What the visitor told you, for the loan they want."""

    loan_type: Literal["home", "personal", "gold", "car"]
    monthly_income: float | None = Field(default=None, description="Take-home a month, rupees.")
    existing_emis: float | None = Field(default=None, description="EMIs they already pay a month.")
    amount: float | None = Field(default=None, description="How much they want to borrow.")
    tenure_months: int | None = Field(default=None, description="Only if they said one.")
    property_value: float | None = Field(
        default=None, description="Home loans: the property's price."
    )
    car_price: float | None = Field(default=None, description="Car loans: on-road price.")
    gold_grams: float | None = Field(default=None, description="Gold loans: grams of 22 carat.")
    use_my_data: bool = Field(default=False, description="Signed in: her real salary and EMIs.")


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


#: How the transactions screen's label names an account filter.
_SCOPE_NAMES = {
    "bank": "Savings and current",
    "sb": "Savings",
    "ca": "Current account",
    "cc": "Credit card",
}


def _txn_line(t: dict[str, Any]) -> str:
    sign = "+" if t["direction"] == "credit" else ""
    return (
        f"{t['id']} {b.fmt_date(b.days_ago(t['days_ago']))} {t['merchant']} "
        f"{sign}{b.inr(t['amount'])} ({b.ACCOUNT_NAMES[t['account']]}, {t['category']})"
    )


def _not_done(why: str) -> str:
    return f"Not done: {why}"


@dataclass
class _Owed:
    """One turn's record: how many units of speech went out, and the written
    answer a read put on screen owes if nothing is said after it ran."""

    starts: int = 0
    line: str | None = None
    at: int = 0


async def _counted(
    turn: AsyncGenerator[Speech, None], record: _Owed
) -> AsyncGenerator[Speech, None]:
    """The model's turn, each unit of its speech counted (not the brain's own lines)."""
    try:
        async for s in turn:
            if isinstance(s, SpeechStart):
                record.starts += 1
            yield s
    finally:
        await turn.aclose()


#: Per turn, like ``landed``'s record: each turn runs in its own task.
_OWED: ContextVar[_Owed | None] = ContextVar("bank_owed", default=None)


def owe(line: str) -> None:
    """Beside a read the customer asked to hear (her balances, a screen's
    contents): the written answer, said by the brain if the model's turn says
    nothing after the tool ran (the turn's preamble alone does not count). It
    is the floor under "I'll open your accounts" followed by silence."""
    if (record := _OWED.get()) is not None:
        record.line = line
        record.at = record.starts


#: What a brain holds for one socket only: the session object and the speech
#: units waiting for the runtime to say what was heard. Everything else a call
#: built is carried to the brain a redial starts (rejoin.py).
_PER_SOCKET = frozenset({"_session", "_awaiting"})


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
        self.path = "/"
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
        #: The customer's turns so far: a rejoined call past its first is not greeted.
        self.turns = 0
        self.rejoined = False

    # ─── Session ────────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        """Both speech legs in the language the visitor picked, and the job from
        the landing page, before the greeting.

        A call outlives a dropped socket (CONTRACT.md, Redial): redial is on
        wherever Voqalize offers it, and a brain started by a redial on a
        session this process still holds adopts that call as it was (the job,
        screen and language it had moved to, the model's history, a sheet
        awaiting a yes, the call's cards and balances) instead of starting over."""
        prior = REJOIN.take(session.id)
        if prior is not None and prior is not self:
            self._adopt(prior)
            self.rejoined = True
            REJOIN.hold(session.id, self)
            await session.configure(
                Config(
                    stt=SttConfig(language=self.lang, patience=PATIENCE),
                    tts=TtsConfig(voice=b.voice_for(self.lang), language=self.lang),
                    idle=IdleConfig(timeout_ms=_IDLE_MS),
                    redial=RedialConfig(enabled=True) if session.can_redial else None,
                )
            )
            logger.info(
                "bank: rejoined call {} after its socket dropped (mode={} lang={} turns={})",
                session.id,
                self.mode,
                self.lang,
                self.turns,
            )
            return
        init = session.init or {}
        lang = str(init.get("lang") or "")
        self.lang = lang if lang in b.LANGUAGES else b.DEFAULT_LANGUAGE
        landing = str(init.get("landing") or "")
        self.mode = landing if landing in MODES else "home"
        self.signed_in = bool(init.get("signed_in")) or self.mode == "banking"
        self.path = str(init.get("path") or "/")
        self.screen = {
            "banking": "dashboard",
            "account": "open_account",
            "cards": "cards",
            "loans": "loans",
        }.get(self.mode, "home")
        REJOIN.hold(session.id, self)
        await session.configure(
            Config(
                stt=SttConfig(language=self.lang, patience=PATIENCE),
                tts=TtsConfig(voice=b.voice_for(self.lang), language=self.lang),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
                redial=RedialConfig(enabled=True) if session.can_redial else None,
            )
        )
        logger.info(
            "bank: session start mode={} lang={} signed_in={}", self.mode, self.lang, self.signed_in
        )
        self.append_note(self._language_note())
        self.append_note(self._screen_note())

    async def on_session_end(self, session: Session) -> None:
        """The socket closed: a hang-up, or a drop Voqalize may redial. Kept a
        short while for the redial; runs at least once, and a second run (or
        one on a brain a redial already replaced) changes nothing."""
        REJOIN.dropped(session.id, self)

    def _adopt(self, prior: BankBrain) -> None:
        """Take over ``prior``'s call: every piece of state but its socket's.
        ``prior`` then shares this brain's state, so whatever still points at
        it (the Stage director's dispatch, a line queued for the next quiet
        spell) acts on this call and this socket."""
        self.__dict__.update({k: v for k, v in prior.__dict__.items() if k not in _PER_SOCKET})
        prior.__dict__ = self.__dict__

    async def greet(self, session: Session) -> str:
        """Written, not generated: the voice starts the moment the call connects.
        A rejoined call the customer already spoke on is not greeted again (a
        call that dropped before her first word still is)."""
        if self.rejoined and self.turns:
            return ""
        return greeting(self.mode, self.lang, self.signed_in)

    def _language_note(self) -> str:
        name = b.PERSONA["language_names"].get(self.lang, self.lang)
        extra = (
            " Hindi in Devanagari, banking words in English as people say them."
            if self.lang == "hi"
            else ""
        )
        return f"[Speak {name} from now on.{extra}]"

    def _screen_told_key(self) -> str:
        product = product_on(self.path) if self.mode in ("cards", "loans") else None
        return f"{self.screen}|{self.signed_in}|{self.mode}|{product or ''}"

    def _screen_note(self) -> str:
        self._screen_told = self._screen_told_key()
        product = product_on(self.path) if self.mode in ("cards", "loans") else None
        about = f" ({product}: they are looking at it, do not ask which one)" if product else ""
        return (
            f"[On screen: {self.screen}{about}. Signed in: {'yes' if self.signed_in else 'no'}. "
            f"You are {_MODE_NOTE[self.mode]}.]"
        )

    # ─── Turns ──────────────────────────────────────────────────────────

    def on_user_message(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]:
        return self._answer(session, msg)

    async def _answer(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]:
        self.turns += 1
        self._last_heard = msg.text
        self._say_next = None
        self._settle_expired()
        if self._screen_told != self._screen_told_key():
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
        line when it acted on screen and said nothing.

        A read that owes an answer (``owe``: her balances, what a screen holds)
        is said by the brain when nothing was spoken after it ran: "I'll open
        your accounts" and then silence is the bug this closes (B1)."""
        record = _Owed()
        token = _OWED.set(record)
        try:
            turn = _counted(self.stage.cued(super().respond(session)), record)
            async for s in self._fallback.speak_if_silent(self, turn):
                yield s
            if record.line is not None and record.starts == record.at:
                logger.warning("bank: a read went unanswered; the brain says {!r}", record.line)
                async for s in self.say_line(record.line, remember=True):
                    yield s
        finally:
            with contextlib.suppress(ValueError):
                _OWED.reset(token)
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
                self.path = event.path
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
        if what == "confirm.ask" and self.awaiting is not None:
            # No sheet is on screen, so a yes now has nothing to press.
            self.awaiting = None
        if what != "ui.show":
            # A move the customer asked for did not happen: she hears so, even
            # when the model's turn has already ended (never silence, B1). A cue
            # that missed only failed to point; the words still stand.
            self._say_soon(line(self.lang, "not_shown"))
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
            self.my_accounts,
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
            self.recommend_card,
            self.rank_cards,
            self.recommend_loan,
            self.plan_emi,
            self.loan_emi,
            self.loan_eligibility,
            self.set_language,
        ]

    def _need_sign_in(self) -> str | None:
        if self.signed_in:
            return None
        return "she is not signed in. Offer to open her banking (open_screen dashboard), which signs her in."

    @needs_result_now
    async def open_screen(self, req: ScreenRequest) -> str:
        """Open a screen of the bank's site or app (an app screen signs a demo visitor in).
        Returns what is on it, from her data: answer from that. Her balances: my_accounts."""
        self._send("nav.open", {"screen": req.screen, "id": req.id})
        if req.screen in _APP_SCREENS:
            self.signed_in = True
        self.screen = req.screen
        self.mode = mode_of(req.screen)
        self.path = (
            {
                "card_detail": f"/cards/{req.id}",
                "cards_apply": f"/cards/apply?card={req.id}",
                "loan": f"/loans/{req.id}",
                "loan_apply": f"/loans/apply?type={req.id}",
            }.get(req.screen, self.path)
            if req.id
            else self.path
        )
        facts = self._screen_facts(req.screen, req.id)
        owe(self._screen_line(req.screen, req.id))
        return (
            f"{req.screen.replace('_', ' ')} is on screen (if it was open already, it stays). "
            f"You are now {_MODE_NOTE[self.mode]}.\n"
            + (f"What it shows:\n{facts}\n" if facts else "")
            + "Answer what she asked from this in one or two sentences; if she only asked to see "
            "it, say what is there that matters and offer the next step."
        )

    @needs_result_now
    async def my_accounts(self, req: AccountsRequest) -> str:
        """Her bank accounts and balances ("my accounts", "my balance", "how much money do I
        have"): both accounts on the dashboard, ringed; or one account's screen."""
        if (why := self._need_sign_in()) is not None:
            return _not_done(why)
        self._send("accounts.show", {"account": req.account})
        if req.account is None:
            self.screen = "dashboard"
        else:
            self.screen = "account"
        self.mode = "banking"
        ids = [req.account] if req.account else [a["id"] for a in b.CUSTOMER["accounts"]]
        owe(self._balances_line(ids))
        lines = [self._account_line(i) for i in ids]
        if req.account is None:
            total = sum(self.balances[i] for i in ids)
            lines.append(f"Together {b.inr(total)} across her two bank accounts.")
            cc = next(c for c in b.CUSTOMER["cards"] if c["id"] == "credit")
            lines.append(
                f"Not a bank account: the credit card ending {cc['last4']} has {b.inr(cc['outstanding'])} "
                "outstanding (card_details if she asks)."
            )
        lines.append("Read her each account's balance now, in one or two sentences.")
        return "\n".join(lines)

    # ─── What a screen holds (spoken from her data, never invented) ─────

    def _account_line(self, acc_id: str) -> str:
        a = next(x for x in b.CUSTOMER["accounts"] if x["id"] == acc_id)
        rate = f", interest {a['rate']}% a year" if a.get("rate") else ""
        return (
            f"{b.ACCOUNT_NAMES[acc_id].capitalize()}: {a['name']} ending {a['last4']}, available "
            f"balance {b.inr(self.balances[acc_id])}{rate}."
        )

    def _balances_line(self, ids: list[str]) -> str:
        """Her balances as a sentence in the call's language: the line the brain
        says itself when the model does not."""
        parts = [
            line(
                self.lang,
                f"balance_{i}",
                last4=next(a["last4"] for a in b.CUSTOMER["accounts"] if a["id"] == i),
                amount=b.inr(self.balances[i]),
            )
            for i in ids
        ]
        return line(self.lang, "balances", accounts=line(self.lang, "and").join(parts))

    def _screen_line(self, screen: str, acc_id: str | None) -> str:
        if screen == "dashboard" and self.signed_in:
            return self._balances_line([a["id"] for a in b.CUSTOMER["accounts"]])
        if screen == "account":
            return self._balances_line([acc_id if acc_id in self.balances else "sb"])
        return line(self.lang, "screen_open")

    def _card_facts(self, card_id: str) -> list[str]:
        data = next(c for c in b.CUSTOMER["cards"] if c["id"] == card_id)
        state = self.cards[card_id]
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
        if card_id == "credit":
            st = data["statement"]
            due = b.fmt_date(b.days_ago(-int(st["due_days_from_now"])))
            pe = data["points_expiring"]
            lines.append(
                f"Credit limit {b.inr(data['credit_limit'])}, outstanding {b.inr(data['outstanding'])}, "
                f"available {b.inr(data['available'])}. Statement due {b.inr(st['total_due'])}, minimum "
                f"{b.inr(st['min_due'])}, by {due}. Unbilled {b.inr(data['unbilled'])}. "
                f"Reward points {data['reward_points']:,} ({pe['points']:,} expire in {pe['days_from_now']} days)."
            )
        return lines

    def _screen_facts(self, screen: str, item: str | None) -> str:
        """A short summary of what ``screen`` shows, from the same data the page reads."""
        c = b.CUSTOMER
        out: list[str] = []
        match screen:
            case "dashboard":
                out += [self._account_line(a["id"]) for a in c["accounts"]]
                cc = next(x for x in c["cards"] if x["id"] == "credit")
                st = cc["statement"]
                out.append(
                    f"Credit card ending {cc['last4']}: outstanding {b.inr(cc['outstanding'])}, "
                    f"bill {b.inr(st['total_due'])} due in {st['due_days_from_now']} days."
                )
                out.append(
                    "Upcoming dues: "
                    + "; ".join(
                        f"{(b.biller(r['biller_id']) or {}).get('name', r['biller_id'])} "
                        f"{b.inr(r['due'])} in {r['due_days_from_now']} days"
                        for r in c["registered_billers"]
                    )
                    + "."
                )
            case "account":
                acc = item if item in self.balances else "sb"
                out.append(self._account_line(acc))
                recent = b.filter_txns(b.TxnFilter(account=acc))[:5]
                out += ["Latest:"] + [_txn_line(t) for t in recent]
            case "transactions":
                recent = b.filter_txns(b.TxnFilter())[:5]
                out.append(
                    f"All {len(c['transactions'])} transactions, newest first "
                    "(savings, current and credit card; find_transactions filters them). Latest:"
                )
                out += [_txn_line(t) for t in recent]
            case "insights":
                key = b.month_key(b.today())
                txns = spend_txns(key)
                out.append(
                    f"{b.month_name(key)} so far: spent {b.inr(sum(t['amount'] for t in txns))} "
                    f"in {len(txns)} payments (spending has the breakdown)."
                )
            case "cards_hub":
                out += self._card_facts("debit")[:1] + self._card_facts("credit")[::2]
            case "debit_card" | "credit_card":
                out += self._card_facts(screen.removesuffix("_card"))
            case "payments":
                out.append(self._account_line("sb"))
                out.append(
                    "Beneficiaries: "
                    + "; ".join(
                        f"{x['name']} ({x['nickname']}, {x['bank']}, limit {b.inr(x['limit'])})"
                        for x in c["beneficiaries"]
                    )
                    + "."
                )
            case "bills":
                out.append(
                    "Billers: "
                    + "; ".join(
                        f"{(b.biller(r['biller_id']) or {}).get('name', r['biller_id'])} due "
                        f"{b.inr(r['due'])} in {r['due_days_from_now']} days"
                        + (" (autopay)" if r.get("autopay") else "")
                        for r in c["registered_billers"]
                    )
                    + "."
                )
            case "deposits":
                out += [
                    f"FD {b.inr(d['amount'])} at {d['rate']}% for {d['tenure_months']} months, "
                    f"{d['payout']}, matures in {d['matures_days_from_now']} days"
                    + (f" at {b.inr(d['maturity_amount'])}" if d["payout"] == "cumulative" else "")
                    + "."
                    for d in c["deposits"]
                ]
            case "statements":
                out.append(
                    f"Monthly account statements and {len(c['statements'])} card statements; "
                    "the latest card bill is on the credit card screen."
                )
            case "offers":
                out += [f"{o['title']}: {o['line']}" for o in c["offers"]]
            case "cards":
                out.append(
                    "Cards: "
                    + "; ".join(
                        f"{x['name']} (annual fee {b.inr(x['annual_fee'])})"
                        for x in b.PRODUCTS["credit_cards"]
                    )
                    + ". rank_cards compares them for a spend."
                )
            case "card_detail":
                card = b.card_product(item or "spark")
                if card:
                    out.append(f"{card['name']}: {'; '.join(card['highlights'])}.")
            case "loans" | "loan":
                loans = b.PRODUCTS["loans"]
                if screen == "loan":
                    loans = [x for x in loans if x["id"] == (item or "home")]
                out += [
                    f"{x['name']}: {x['rate_min']}% to {x['rate_max']}%, {b.inr(x['amount_min'])} to "
                    f"{b.inr(x['amount_max'])}."
                    for x in loans
                ]
            case _:
                pass
        return "\n".join(out)

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
                    _SCOPE_NAMES.get(q.account or "", ""),
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
        self._send("nav.open", {"screen": f"{req.card}_card"})
        self.screen, self.mode = f"{req.card}_card", "banking"
        landed(line(self.lang, "card"))
        return "\n".join(self._card_facts(req.card))

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
        # Signed in, her salary is known: the page ranks the cards she qualifies for first
        # and marks the rest "Income below requirement" (same rule, bankmath.rank_cards).
        income = float(b.CUSTOMER["profile"]["monthly_income"]) if self.signed_in else None
        ranked = m.rank_cards(profile, monthly_income=income)
        top = [v.card_id for v in ranked[:3]]
        self._send("cards.compare", {"card_ids": top, **{k: int(v) for k, v in profile.items()}})
        self.screen, self.mode = "cards_compare", "cards"
        landed(line(self.lang, "compare"))
        lines = [
            "Monthly spend: " + ", ".join(f"{k} {b.inr(v)}" for k, v in profile.items() if v) + "."
        ]
        if income is not None:
            lines.append(
                f"Her income is {b.inr(income)} a month: cards she qualifies for are ranked first; "
                "the page marks the others 'Income below requirement'."
            )
        for i, v in enumerate(ranked, 1):
            card = b.card_product(v.card_id) or {}
            lines.append(
                f"{i}. {card.get('name')}: about {b.inr(v.net_yearly)} a year net "
                f"(rewards {b.inr(v.yearly_rewards)}, fuel saving {b.inr(v.fuel_saving_yearly)}, "
                f"lounge value {b.inr(v.lounge_value)}, fee "
                + ("waived" if v.fee_waived else b.inr(v.fee))
                + ")."
                + (
                    f" Income below requirement: needs {b.inr(card.get('min_income_monthly', 0))}"
                    " a month, above hers; do not recommend it, say so if you mention it."
                    if v.below_income
                    else ""
                )
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

    # ─── The pitch (public pages, B2): the best option for this person ──

    @needs_result_now
    async def recommend_card(self, req: CardPitchRequest) -> str:
        """The ONE card to recommend to this person, once you know their income and how
        they spend: puts it side by side with the runner-up on screen, best first, and
        returns what it is worth to them a year, what it costs, and that they qualify."""
        if req.use_my_data:
            if (why := self._need_sign_in()) is not None:
                return _not_done(why)
            profile = m.customer_profile()
            income: float | None = float(b.CUSTOMER["profile"]["monthly_income"])
        else:
            profile = {c: float(getattr(req, c) or 0) for c in b.CARD_CATEGORIES}
            income = req.monthly_income
        assumed = ""
        if not any(profile.values()) and req.total_monthly:
            total = float(req.total_monthly)
            if req.mostly_on:
                profile[req.mostly_on] = round(total / 2 / 100) * 100
                profile["other"] = total - profile[req.mostly_on]
                assumed = (
                    f"Split assumed from what they said: half on {req.mostly_on}, half elsewhere. "
                )
            else:
                profile["other"] = total
                assumed = "No split given: all counted as everyday spend; ask where most goes if it matters. "
        if not any(profile.values()):
            return _not_done(
                "ask roughly how much they put on a card a month, and where most of it goes"
            )
        if not income:
            return _not_done(
                "ask their monthly take-home income (each card has an income minimum), in one short question"
            )
        ranked = m.rank_cards(profile, monthly_income=income)
        ok = [v for v in ranked if not v.below_income]
        if not ok:
            lowest = min(b.PRODUCTS["credit_cards"], key=lambda c: c["min_income_monthly"])
            return _not_done(
                f"no card fits an income of {b.inr(income)} a month; the lowest minimum is "
                f"{b.inr(lowest['min_income_monthly'])} ({lowest['name']}). Say so kindly and offer "
                "a savings account instead"
            )
        best = ok[0]
        shown = [v.card_id for v in ok[:3]]
        if len(shown) < 2:
            shown.append(next(v.card_id for v in ranked if v.card_id not in shown))
        self._send("cards.compare", {"card_ids": shown, **{k: int(v) for k, v in profile.items()}})
        self.screen, self.mode = "cards_compare", "cards"
        landed(line(self.lang, "compare"))
        card = b.card_product(best.card_id) or {}
        short = card["name"].split(" ", 1)[-1]  # "Daily Cashback", without the bank's name
        fee = (
            f"annual fee {b.inr(best.fee)} waived at their spend"
            if best.fee_waived
            else f"annual fee {b.inr(best.fee)} (waived on {b.inr(card['fee_waiver_spend'])} a year)"
        )
        # B5: the pitch is two or three short sentences, so the result leads with
        # exactly what to say (the pick, the one number, the nudge) and keeps the
        # rest of the working below it, for a follow-up question only.
        out = [
            "SAY THIS and nothing more (two sentences, in the call's language), e.g.: "
            f'"{short} is the one for you: about {b.inr(best.net_yearly)} a year back after fees, '
            'and you qualify. Shall I start your application?"',
            "Do not read out the detail below (rewards, fees, runner-up, the split); it is only for a "
            "follow-up question.",
            "DETAIL: "
            + assumed
            + "Monthly spend: "
            + ", ".join(f"{k} {b.inr(v)}" for k, v in profile.items() if v)
            + f"; income {b.inr(income)} a month. "
            f"RECOMMEND: {card['name']} ({card['tier']}), about {b.inr(best.net_yearly)} a year: "
            f"{b.inr(best.yearly_rewards)} in rewards"
            + (
                f", {b.inr(best.fuel_saving_yearly)} fuel surcharge saved"
                if best.fuel_saving_yearly
                else ""
            )
            + (f", lounge visits worth {b.inr(best.lounge_value)}" if best.lounge_value else "")
            + f"; {fee}; joining fee {b.inr(card['joining_fee'])}. "
            f"Eligible: needs {b.inr(card['min_income_monthly'])} a month, they earn {b.inr(income)}. "
            f"Why: {card['highlights'][0]}.",
        ]
        if len(ok) > 1:
            nxt = ok[1]
            out.append(
                f"Runner-up: {(b.card_product(nxt.card_id) or {}).get('name')}, about "
                f"{b.inr(nxt.net_yearly)} a year: the pick gives them {b.inr(best.net_yearly - nxt.net_yearly)} more."
            )
        above = [v for v in ranked if v.below_income and v.net_yearly > best.net_yearly]
        if above:
            c2 = b.card_product(above[0].card_id) or {}
            out.append(
                f"Not offered: {c2.get('name')} needs {b.inr(c2.get('min_income_monthly', 0))} a month; "
                "do not pitch it."
            )
        out.append(
            f"On yes: open_screen cards_apply id {best.card_id}, then fill_card_application with "
            "what you already know."
        )
        return "\n".join(out)

    @needs_result_now
    async def recommend_loan(self, req: LoanPitchRequest) -> str:
        """The best plan for this person, once you know the loan, their income (gold: the
        grams) and the amount or the price: the amount and tenure that fit, the EMI, the
        interest, eligibility, and a cheaper option when one fits. Puts the eligibility
        check and the EMI calculator on screen with their numbers."""
        loan = b.loan_product(req.loan_type)
        assert loan is not None
        income, existing = req.monthly_income, req.existing_emis
        if req.use_my_data:
            if (why := self._need_sign_in()) is not None:
                return _not_done(why)
            income = float(b.CUSTOMER["profile"]["monthly_income"])
            existing = float(sum(x["emi"] for x in b.CUSTOMER["loans"]))
        asset = req.property_value if req.loan_type == "home" else req.car_price
        if req.loan_type == "gold":
            if not req.gold_grams:
                return _not_done("ask how many grams of gold (22 carat) they would pledge")
        else:
            if not income:
                return _not_done("ask their monthly take-home income and any EMIs they already pay")
            if not req.amount and not asset:
                what = {"home": "the property's price", "car": "the car's on-road price"}.get(
                    req.loan_type, "the amount they need"
                )
                return _not_done(f"ask how much they need to borrow (or {what})")
        p = m.loan_plan(
            loan,
            amount=req.amount,
            tenure_months=req.tenure_months,
            monthly_income=income,
            existing_emis=existing,
            asset_value=asset,
            gold_grams=req.gold_grams,
        )
        if req.loan_type == "gold":
            self._send("loan.eligibility", {"loan_type": "gold", "gold_grams": req.gold_grams})
        else:
            self._send(
                "loan.eligibility",
                {
                    "loan_type": req.loan_type,
                    "monthly_income": income,
                    "existing_emis": existing or 0,
                    "tenure_months": p.tenure_months,
                },
            )
        self._send(
            "loan.calc",
            {
                "loan_type": req.loan_type,
                "amount": p.amount,
                "tenure_months": p.tenure_months,
                "rate": p.rate,
            },
        )
        self.screen, self.mode = "loan", "loans"
        landed(line(self.lang, "loan_emi"))
        years = p.tenure_months / 12
        span = f"{years:g} years" if p.tenure_months % 12 == 0 else f"{p.tenure_months} months"
        # B5: two or three short sentences. The result leads with what to say: the
        # plan in one breath (amount, tenure, the EMI: the one number), that it fits
        # them, one nudge. Interest, the saving, eligibility working and documents
        # stay below for a follow-up question.
        out: list[str] = []
        blocked = p.below_min_income or not p.fits
        if p.below_min_income:
            out.append(
                f"NOT ELIGIBLE: the {loan['short']} needs {b.inr(loan['min_income_monthly'])} a month, "
                f"they earn {b.inr(income or 0)}. Say so kindly in one or two short sentences; offer a "
                "gold loan (no income proof) if it fits."
            )
        elif not p.fits:
            out.append(
                f"Cannot fit: at {b.inr(income or 0)} a month with {b.inr(existing or 0)} in EMIs the most "
                f"is {b.inr(p.max_amount)}, below this loan's minimum. Say so kindly, in one or two short "
                "sentences."
            )
        else:
            why = ""
            fit = "your gold covers" if req.loan_type == "gold" else "fits your income"
            if p.capped_by == "income" and req.amount:
                why = f"They asked for {b.inr(req.amount)}: this is the most their income supports; say so in a few words, inside those two sentences."
            elif p.capped_by == "gold" and req.amount:
                why = f"They asked for {b.inr(req.amount)}: this is the most the gold covers; say so in a few words, inside those two sentences."
            elif p.stretched_from:
                why = f"Tenure stretched from {p.stretched_from} months so the EMI fits; say so in a few words, inside those two sentences."
            out += [
                "SAY THIS and nothing more (two sentences, in the call's language), e.g.: "
                f'"You can get {b.inr(p.amount)} over {span} at an EMI of {b.inr(p.emi)} a month, '
                f'which {fit}. Shall I start your application?"',
                *([why] if why else []),
                "Do not read out the detail below (rate, interest, a shorter tenure, their own share, "
                "the eligibility working); it is only for a follow-up question, one figure at a time.",
            ]
        out.append(
            f"DETAIL: PLAN: {loan['short']} of {b.inr(p.amount)} over {span} at {p.rate}% (typical rate; "
            f"{loan['rate_min']}% for the best profiles): EMI {b.inr(p.emi)} a month, total interest "
            f"{b.inr(p.total_interest)}. Processing fee: {loan['processing_fee']}."
        )
        if p.max_emi is not None:
            out.append(
                f"Eligibility: affordable EMI up to {b.inr(p.max_emi)} "
                f"({int(float(loan['foir']) * 100)}% of income less existing EMIs); "
                f"at {span} they can borrow up to {b.inr(p.max_amount)}."
            )
        else:
            out.append(
                f"Against {req.gold_grams} g of gold they can borrow up to {b.inr(p.max_amount)}."
            )
        if p.capped_by == "ltv" and asset:
            out.append(
                f"The loan covers at most {b.inr(p.amount)} of the {b.inr(asset)} price "
                f"({loan['ltv']}); own share {b.inr(asset - p.amount)}."
            )
        elif asset and req.amount is None:
            out.append(
                f"No amount given: this is the most the loan lends on {b.inr(asset)} ({loan['ltv']}); "
                f"own share {b.inr(asset - p.amount)}. If they need less, recommend again with the amount."
            )
        if p.shorter:
            n2, e2, saved = p.shorter
            out.append(
                f"If they ask about paying less interest: over {n2 // 12 if n2 % 12 == 0 else n2} "
                f"{'years' if n2 % 12 == 0 else 'months'} the EMI is {b.inr(e2)} (still within budget) "
                f"and they save {b.inr(saved)} in interest."
            )
        if not blocked:
            out.append(
                f"On yes, offer to start the application: fill_loan_application with loan_type "
                f"{req.loan_type} and what you already know, then ask only for what is missing."
            )
        return "\n".join(out)

    async def set_language(self, req: LanguageRequest) -> str:
        """Switch the call's language (both what you hear and how you speak)."""
        if req.language == self.lang:
            return f"Already speaking {req.language}."
        configure_soon(self.session, self._speaking(req.language))
        self.append_note(self._language_note())
        # The model's line before the call was in the old language; the switch
        # is said in the new one, so the turn never ends on a promise alone.
        self._say_soon(line(self.lang, "switched"))
        return (
            f"Switched; she was told so in {b.PERSONA['language_names'][req.language]}, do not repeat it. "
            f"From your next sentence, speak {b.PERSONA['language_names'][req.language]}."
        )


def _reference(detail: str) -> str | None:
    hit = re.search(r"\b(GLB[-A-Z0-9]*\d{4,})\b", detail)
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


#: Live calls by session id, for a redial to rejoin (rejoin.py).
REJOIN: Rejoin[BankBrain] = Rejoin()

__all__ = ["REJOIN", "BankBrain", "classify", "mode_of"]
