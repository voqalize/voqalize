"""What the bank's page tells the brain (CONTRACT.md, "Page → brain events").

Typed and fine-grained: each event is one thing the customer (``by: "visitor"``)
or the agent's own move (``by: "agent"``) did on screen. The other direction is
the Stage moves in ``stage_gen.py`` and the one plain :class:`LanguageChanged`
action in ``brain.py``."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from voqalize.sdk import AppEvent, AppEvents

By = Literal["visitor", "agent"]
FormName = Literal["open_account", "card_apply", "loan_apply"]


class PageViewed(AppEvent):
    """A route change: the screen the customer is on now."""

    path: str
    screen: str = "home"
    signed_in: bool = False
    by: By = "visitor"


class SignedIn(AppEvent):
    """The mock sign-in was pressed."""

    customer_id: str = ""
    by: By = "visitor"


class SignedOut(AppEvent):
    by: By = "visitor"


class TxnOpened(AppEvent):
    """A transaction's detail panel was opened: "this charge" means it."""

    txn_id: str
    by: By = "visitor"


class CardControlChanged(AppEvent):
    """A card control or limit changed (after its confirmation)."""

    card: Literal["debit", "credit"]
    control: str
    value: str
    by: By = "visitor"


class ActionDone(AppEvent):
    """A confirmation sheet was answered, by tap or by ``confirm.answer``."""

    action_id: str
    kind: str
    outcome: Literal["done", "cancelled"]
    reference: str | None = None
    summary: str = ""
    by: By = "visitor"


class FormChanged(AppEvent):
    """A form changed: its field names only, never values."""

    form: FormName
    step: int = 1
    filled: list[str] = Field(default_factory=list[str])
    missing: list[str] = Field(default_factory=list[str])
    by: By = "visitor"


class FormSubmitted(AppEvent):
    form: FormName
    reference: str
    summary: str = ""
    by: By = "visitor"


class CardsProfileChanged(AppEvent):
    """The spend sliders on the cards page moved; ``top`` is the page's ranking."""

    dining: float = 0
    online: float = 0
    groceries: float = 0
    travel: float = 0
    fuel: float = 0
    utilities: float = 0
    other: float = 0
    top: list[str] = Field(default_factory=list[str])
    by: By = "visitor"


class LoanCalcChanged(AppEvent):
    loan_type: str
    amount: float
    tenure_months: int
    rate: float
    emi: float
    by: By = "visitor"


class LanguageRequested(AppEvent):
    """The customer pressed the other language on the dock's toggle."""

    language: str
    by: By = "visitor"


BankEvent = (
    PageViewed
    | SignedIn
    | SignedOut
    | TxnOpened
    | CardControlChanged
    | ActionDone
    | FormChanged
    | FormSubmitted
    | CardsProfileChanged
    | LoanCalcChanged
    | LanguageRequested
)

BANK_EVENTS: tuple[type[AppEvent], ...] = (
    PageViewed,
    SignedIn,
    SignedOut,
    TxnOpened,
    CardControlChanged,
    ActionDone,
    FormChanged,
    FormSubmitted,
    CardsProfileChanged,
    LoanCalcChanged,
    LanguageRequested,
)

__all__ = [
    "BANK_EVENTS",
    "ActionDone",
    "AppEvents",
    "BankEvent",
    "CardControlChanged",
    "CardsProfileChanged",
    "FormChanged",
    "FormSubmitted",
    "LanguageRequested",
    "LoanCalcChanged",
    "PageViewed",
    "SignedIn",
    "SignedOut",
    "TxnOpened",
]
