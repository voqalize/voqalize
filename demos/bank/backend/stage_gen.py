# Generated from bank/frontend/src/stage/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
#   voqalize stage gen bank/frontend/src/stage/scene.json --py bank/backend/stage_gen.py --ts bank/frontend/src/stage/scene.gen.ts
"""The moves of global_bank, from its Stage Spec."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from voqalize.sdk.stage import Move, MoveClass, MoveSet, StageSpec, load_spec

#: The spec itself, carried here so the brain never reads the JSON at run
#: time (and a deploy that ships this file ships the spec with it).
SPEC: StageSpec = load_spec(
    '{"id":"global_bank","languages":["en","hi"],"moves":[{"args":[{"doc":"The spoken label of something on the screen in front, as data-stage-label names it: Reward points, Due date, Available balance.","name":"thing"}],"class":"look","doc":"Ring one thing on the screen in front (data-stage-thing / data-stage-label). Refused, with the labels on screen, when it is not there.","id":"ui.show","say":"{show: Reward points} right before the sentence that talks about that part of the screen; it scrolls into view and is ringed.","verb":"show"},{"args":[{"doc":"The screen to open.","enum":["home","login","dashboard","account","transactions","insights","cards_hub","debit_card","credit_card","payments","bills","deposits","statements","offers","open_account","cards","card_detail","cards_compare","cards_apply","cards_emi","loans","loan","loan_apply"],"name":"screen"},{"doc":"For account: sb or ca. For card_detail and cards_apply: a card id. For loan and loan_apply: home, personal, gold or car.","name":"id","optional":true}],"claims":["opening your","taking you to"],"class":"navigate","doc":"Open a screen of the bank\'s site or app. Signed out, a signed-in screen (or login) shows the sign-in form instead and rings it: only the customer signs in, by typing a mobile number and PIN.","id":"nav.open","objects":["screen","page","statement","dashboard"]},{"args":[{"doc":"One account\'s own screen; both accounts on the dashboard by default.","enum":["sb","ca"],"name":"account","optional":true}],"claims":["opening your accounts","showing your accounts","pulling up your accounts"],"class":"look","doc":"Her bank accounts and balances: both on the dashboard, the accounts ringed and scrolled fully into view, or one account\'s screen with its balance ringed. Returns each balance as the page shows it.","id":"accounts.show","objects":["accounts","balances","balance"]},{"args":[{"doc":"Which account: sb savings, ca current, cc credit card, bank for savings and current together (no credit card); all by default.","enum":["all","bank","sb","ca","cc"],"name":"account","optional":true},{"doc":"A spend category id: food, groceries, shopping, travel, fuel, bills, entertainment, health, rent, emi, investments, transfers, cash, fees, income, refunds.","name":"category","optional":true},{"doc":"Words in the merchant or description.","name":"query","optional":true},{"doc":"Oldest day to include, as days before today.","name":"from_days_ago","optional":true,"type":"integer"},{"doc":"Newest day to include, as days before today (0 is today).","name":"to_days_ago","optional":true,"type":"integer"},{"name":"min_amount","optional":true,"type":"number"},{"name":"max_amount","optional":true,"type":"number"},{"enum":["any","debit","credit"],"name":"direction","optional":true},{"doc":"What the filter shows, in words: Food in October.","name":"label","optional":true}],"claims":["filtering your transactions","pulling up your transactions"],"class":"reversible","doc":"Open the transactions screen with these filters set, each ringed as it is applied.","id":"txn.find","objects":["transactions","charges","payments","spends"]},{"args":[{"doc":"A transaction id, T0197.","name":"txn_id"}],"claims":["opening that transaction"],"class":"look","doc":"Open one transaction\'s detail panel (on the transactions screen) and ring it.","id":"txn.open","objects":["transaction","charge"]},{"args":[{"doc":"YYYY-MM.","name":"month"},{"doc":"A spend category id to ring.","name":"category","optional":true}],"claims":["opening your spending"],"class":"look","doc":"Open the spending insights for one month and ring a category\'s row.","id":"insights.show","objects":["spending","insights","breakdown"]},{"args":[{"doc":"A fresh id the brain mints, A1, A2…","name":"action_id"},{"doc":"What would change.","enum":["card_block","card_unblock","card_control","card_limit","bill_pay","transfer","fd_book","emi_convert","offer_accept"],"name":"kind"},{"enum":["debit","credit"],"name":"card","optional":true},{"enum":["international","online","contactless","atm","atm_daily","pos_daily","online_daily"],"name":"control","optional":true},{"doc":"on / off for a control; the new limit in rupees for a limit.","name":"value","optional":true},{"name":"amount","optional":true,"type":"number"},{"doc":"A biller id (bill_pay), a beneficiary id (transfer), a transaction id (emi_convert) or an offer id (offer_accept).","name":"target","optional":true},{"enum":["sb","ca"],"name":"from_account","optional":true},{"name":"tenure_months","optional":true,"type":"integer"},{"enum":["cumulative","monthly","quarterly"],"name":"payout","optional":true}],"claims":["asking you to confirm"],"class":"reversible","doc":"Put a confirmation sheet on screen for a change, with its summary and Confirm / Cancel. Nothing changes until it is confirmed, by tap or by confirm.answer.","id":"confirm.ask","objects":["confirmation"]},{"args":[{"name":"action_id"},{"doc":"true presses Confirm, false presses Cancel.","name":"yes","type":"boolean"}],"claims":["confirming it","cancelling it"],"class":"confirmed","doc":"Press Confirm or Cancel on the confirmation sheet, after the customer\'s spoken answer. Answers with the reference of what was done.","id":"confirm.answer","objects":["confirmation"]},{"args":[{"enum":["open_account","card_apply","loan_apply"],"name":"form"},{"doc":"A field of that form by its name (CONTRACT.md).","name":"field"},{"doc":"The value, as the form takes it: a choice id, a date YYYY-MM-DD, a number, or text.","name":"value"}],"claims":["filling in","putting down"],"class":"reversible","doc":"Set one field of a form, ringing it first. Refused with the field\'s choices when the value is not one of them.","id":"form.fill","objects":["form","field","application"]},{"args":[{"enum":["open_account","card_apply","loan_apply"],"name":"form"},{"name":"step","type":"integer"}],"class":"navigate","doc":"Open a step of a form (account opening has six; the others are one page, step 1).","id":"form.step","objects":["step"]},{"args":[{"enum":["open_account","card_apply","loan_apply"],"name":"form"}],"claims":["submitting your application","submitting it"],"class":"confirmed","doc":"Press the form\'s Submit after the customer\'s spoken yes. Refused, naming the missing fields. Answers with the reference.","id":"form.submit","objects":["application"]},{"args":[{"doc":"Two to five card ids, best first.","name":"card_ids","type":"array"},{"doc":"Monthly spend in rupees, for the ranking.","name":"dining","optional":true,"type":"integer"},{"name":"online","optional":true,"type":"integer"},{"name":"groceries","optional":true,"type":"integer"},{"name":"travel","optional":true,"type":"integer"},{"name":"fuel","optional":true,"type":"integer"},{"name":"utilities","optional":true,"type":"integer"},{"name":"other","optional":true,"type":"integer"}],"claims":["comparing the cards","putting the cards side by side"],"class":"look","doc":"Open the side-by-side compare of these cards in this order, with the monthly spend profile set, each card\'s yearly value worked out from it.","id":"cards.compare","objects":["cards","comparison"]},{"args":[{"doc":"A card transaction to convert; or an amount.","name":"txn_id","optional":true},{"name":"amount","optional":true,"type":"number"},{"doc":"3, 6, 9, 12, 18 or 24.","name":"tenure_months","type":"integer"}],"claims":["working out the emi"],"class":"reversible","doc":"Open the EMI planner for a card spend with every tenure\'s EMI worked out and this tenure selected and ringed.","id":"emi.plan","objects":["emi","instalments","plan"]},{"args":[{"enum":["home","personal","gold","car"],"name":"loan_type"},{"name":"amount","type":"number"},{"name":"tenure_months","type":"integer"},{"doc":"Yearly rate; the product\'s typical rate when absent.","name":"rate","optional":true,"type":"number"}],"claims":["working out the emi","putting that in the calculator"],"class":"reversible","doc":"Set the loan EMI calculator and show its working.","id":"loan.calc","objects":["calculator","emi"]},{"args":[{"enum":["home","personal","gold","car"],"name":"loan_type"},{"name":"monthly_income","optional":true,"type":"number"},{"name":"existing_emis","optional":true,"type":"number"},{"name":"tenure_months","optional":true,"type":"integer"},{"name":"gold_grams","optional":true,"type":"number"}],"claims":["checking your eligibility","working out how much"],"class":"reversible","doc":"Fill the eligibility check and show how much can be borrowed, with the working.","id":"loan.eligibility","objects":["eligibility"]}],"stage":1}'
)
#: The spec's hash: a page reading another spec reports a different one.
SPEC_SHA256 = "3dd166b5fa4d1e22defc8c213925e104f4482123ca1dbe8286f687ce23261962"


class UiShowArgs(BaseModel):
    """The arguments of ``ui.show``."""

    thing: str
    """The spoken label of something on the screen in front, as data-stage-label names it: Reward points, Due date, Available balance."""


class NavOpenArgs(BaseModel):
    """The arguments of ``nav.open``."""

    screen: Literal[
        "home",
        "login",
        "dashboard",
        "account",
        "transactions",
        "insights",
        "cards_hub",
        "debit_card",
        "credit_card",
        "payments",
        "bills",
        "deposits",
        "statements",
        "offers",
        "open_account",
        "cards",
        "card_detail",
        "cards_compare",
        "cards_apply",
        "cards_emi",
        "loans",
        "loan",
        "loan_apply",
    ]
    """The screen to open."""
    id: str | None = None
    """For account: sb or ca. For card_detail and cards_apply: a card id. For loan and loan_apply: home, personal, gold or car."""


class AccountsShowArgs(BaseModel):
    """The arguments of ``accounts.show``."""

    account: Literal["sb", "ca"] | None = None
    """One account's own screen; both accounts on the dashboard by default."""


class FindArgs(BaseModel):
    """The arguments of ``txn.find``."""

    account: Literal["all", "bank", "sb", "ca", "cc"] | None = None
    """Which account: sb savings, ca current, cc credit card, bank for savings and current together (no credit card); all by default."""
    category: str | None = None
    """A spend category id: food, groceries, shopping, travel, fuel, bills, entertainment, health, rent, emi, investments, transfers, cash, fees, income, refunds."""
    query: str | None = None
    """Words in the merchant or description."""
    from_days_ago: int | None = None
    """Oldest day to include, as days before today."""
    to_days_ago: int | None = None
    """Newest day to include, as days before today (0 is today)."""
    min_amount: float | None = None
    max_amount: float | None = None
    direction: Literal["any", "debit", "credit"] | None = None
    label: str | None = None
    """What the filter shows, in words: Food in October."""


class TxnOpenArgs(BaseModel):
    """The arguments of ``txn.open``."""

    txn_id: str
    """A transaction id, T0197."""


class InsightsShowArgs(BaseModel):
    """The arguments of ``insights.show``."""

    month: str
    """YYYY-MM."""
    category: str | None = None
    """A spend category id to ring."""


class AskArgs(BaseModel):
    """The arguments of ``confirm.ask``."""

    action_id: str
    """A fresh id the brain mints, A1, A2…"""
    kind: Literal[
        "card_block",
        "card_unblock",
        "card_control",
        "card_limit",
        "bill_pay",
        "transfer",
        "fd_book",
        "emi_convert",
        "offer_accept",
    ]
    """What would change."""
    card: Literal["debit", "credit"] | None = None
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
    ) = None
    value: str | None = None
    """on / off for a control; the new limit in rupees for a limit."""
    amount: float | None = None
    target: str | None = None
    """A biller id (bill_pay), a beneficiary id (transfer), a transaction id (emi_convert) or an offer id (offer_accept)."""
    from_account: Literal["sb", "ca"] | None = None
    tenure_months: int | None = None
    payout: Literal["cumulative", "monthly", "quarterly"] | None = None


class AnswerArgs(BaseModel):
    """The arguments of ``confirm.answer``."""

    action_id: str
    yes: bool
    """true presses Confirm, false presses Cancel."""


class FillArgs(BaseModel):
    """The arguments of ``form.fill``."""

    form: Literal["open_account", "card_apply", "loan_apply"]
    field: str
    """A field of that form by its name (CONTRACT.md)."""
    value: str
    """The value, as the form takes it: a choice id, a date YYYY-MM-DD, a number, or text."""


class StepArgs(BaseModel):
    """The arguments of ``form.step``."""

    form: Literal["open_account", "card_apply", "loan_apply"]
    step: int


class SubmitArgs(BaseModel):
    """The arguments of ``form.submit``."""

    form: Literal["open_account", "card_apply", "loan_apply"]


class CompareArgs(BaseModel):
    """The arguments of ``cards.compare``."""

    card_ids: list[str]
    """Two to five card ids, best first."""
    dining: int | None = None
    """Monthly spend in rupees, for the ranking."""
    online: int | None = None
    groceries: int | None = None
    travel: int | None = None
    fuel: int | None = None
    utilities: int | None = None
    other: int | None = None


class PlanArgs(BaseModel):
    """The arguments of ``emi.plan``."""

    txn_id: str | None = None
    """A card transaction to convert; or an amount."""
    amount: float | None = None
    tenure_months: int
    """3, 6, 9, 12, 18 or 24."""


class CalcArgs(BaseModel):
    """The arguments of ``loan.calc``."""

    loan_type: Literal["home", "personal", "gold", "car"]
    amount: float
    tenure_months: int
    rate: float | None = None
    """Yearly rate; the product's typical rate when absent."""


class EligibilityArgs(BaseModel):
    """The arguments of ``loan.eligibility``."""

    loan_type: Literal["home", "personal", "gold", "car"]
    monthly_income: float | None = None
    existing_emis: float | None = None
    tenure_months: int | None = None
    gold_grams: float | None = None


UI_SHOW = Move(
    id="ui.show",
    verb="show",
    cls=MoveClass.LOOK,
    args=("thing",),
    say="{show: Reward points} right before the sentence that talks about that part of the screen; it scrolls into view and is ringed.",
)
"""Ring one thing on the screen in front (data-stage-thing / data-stage-label). Refused, with the labels on screen, when it is not there."""

NAV_OPEN = Move(
    id="nav.open",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=(
        "screen",
        "id",
    ),
    claims=(
        "opening your",
        "taking you to",
    ),
    objects=(
        "screen",
        "page",
        "statement",
        "dashboard",
    ),
)
"""Open a screen of the bank's site or app. Signed out, a signed-in screen (or login) shows the sign-in form instead and rings it: only the customer signs in, by typing a mobile number and PIN."""

ACCOUNTS_SHOW = Move(
    id="accounts.show",
    verb=None,
    cls=MoveClass.LOOK,
    args=("account",),
    claims=(
        "opening your accounts",
        "showing your accounts",
        "pulling up your accounts",
    ),
    objects=(
        "accounts",
        "balances",
        "balance",
    ),
)
"""Her bank accounts and balances: both on the dashboard, the accounts ringed and scrolled fully into view, or one account's screen with its balance ringed. Returns each balance as the page shows it."""

FIND = Move(
    id="txn.find",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "account",
        "category",
        "query",
        "from_days_ago",
        "to_days_ago",
        "min_amount",
        "max_amount",
        "direction",
        "label",
    ),
    claims=(
        "filtering your transactions",
        "pulling up your transactions",
    ),
    objects=(
        "transactions",
        "charges",
        "payments",
        "spends",
    ),
)
"""Open the transactions screen with these filters set, each ringed as it is applied."""

TXN_OPEN = Move(
    id="txn.open",
    verb=None,
    cls=MoveClass.LOOK,
    args=("txn_id",),
    claims=("opening that transaction",),
    objects=(
        "transaction",
        "charge",
    ),
)
"""Open one transaction's detail panel (on the transactions screen) and ring it."""

INSIGHTS_SHOW = Move(
    id="insights.show",
    verb=None,
    cls=MoveClass.LOOK,
    args=(
        "month",
        "category",
    ),
    claims=("opening your spending",),
    objects=(
        "spending",
        "insights",
        "breakdown",
    ),
)
"""Open the spending insights for one month and ring a category's row."""

ASK = Move(
    id="confirm.ask",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "action_id",
        "kind",
        "card",
        "control",
        "value",
        "amount",
        "target",
        "from_account",
        "tenure_months",
        "payout",
    ),
    claims=("asking you to confirm",),
    objects=("confirmation",),
)
"""Put a confirmation sheet on screen for a change, with its summary and Confirm / Cancel. Nothing changes until it is confirmed, by tap or by confirm.answer."""

ANSWER = Move(
    id="confirm.answer",
    verb=None,
    cls=MoveClass.CONFIRMED,
    args=(
        "action_id",
        "yes",
    ),
    claims=(
        "confirming it",
        "cancelling it",
    ),
    objects=("confirmation",),
)
"""Press Confirm or Cancel on the confirmation sheet, after the customer's spoken answer. Answers with the reference of what was done."""

FILL = Move(
    id="form.fill",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "form",
        "field",
        "value",
    ),
    claims=(
        "filling in",
        "putting down",
    ),
    objects=(
        "form",
        "field",
        "application",
    ),
)
"""Set one field of a form, ringing it first. Refused with the field's choices when the value is not one of them."""

STEP = Move(
    id="form.step",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=(
        "form",
        "step",
    ),
    objects=("step",),
)
"""Open a step of a form (account opening has six; the others are one page, step 1)."""

SUBMIT = Move(
    id="form.submit",
    verb=None,
    cls=MoveClass.CONFIRMED,
    args=("form",),
    claims=(
        "submitting your application",
        "submitting it",
    ),
    objects=("application",),
)
"""Press the form's Submit after the customer's spoken yes. Refused, naming the missing fields. Answers with the reference."""

COMPARE = Move(
    id="cards.compare",
    verb=None,
    cls=MoveClass.LOOK,
    args=(
        "card_ids",
        "dining",
        "online",
        "groceries",
        "travel",
        "fuel",
        "utilities",
        "other",
    ),
    claims=(
        "comparing the cards",
        "putting the cards side by side",
    ),
    objects=(
        "cards",
        "comparison",
    ),
)
"""Open the side-by-side compare of these cards in this order, with the monthly spend profile set, each card's yearly value worked out from it."""

PLAN = Move(
    id="emi.plan",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "txn_id",
        "amount",
        "tenure_months",
    ),
    claims=("working out the emi",),
    objects=(
        "emi",
        "instalments",
        "plan",
    ),
)
"""Open the EMI planner for a card spend with every tenure's EMI worked out and this tenure selected and ringed."""

CALC = Move(
    id="loan.calc",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "loan_type",
        "amount",
        "tenure_months",
        "rate",
    ),
    claims=(
        "working out the emi",
        "putting that in the calculator",
    ),
    objects=(
        "calculator",
        "emi",
    ),
)
"""Set the loan EMI calculator and show its working."""

ELIGIBILITY = Move(
    id="loan.eligibility",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "loan_type",
        "monthly_income",
        "existing_emis",
        "tenure_months",
        "gold_grams",
    ),
    claims=(
        "checking your eligibility",
        "working out how much",
    ),
    objects=("eligibility",),
)
"""Fill the eligibility check and show how much can be borrowed, with the working."""

MOVES = MoveSet(
    (
        UI_SHOW,
        NAV_OPEN,
        ACCOUNTS_SHOW,
        FIND,
        TXN_OPEN,
        INSIGHTS_SHOW,
        ASK,
        ANSWER,
        FILL,
        STEP,
        SUBMIT,
        COMPARE,
        PLAN,
        CALC,
        ELIGIBILITY,
    )
)

#: The line each cue is taught with, in the spec's order.
PROMPT_LINES: tuple[str, ...] = (
    "{show: Reward points} right before the sentence that talks about that part of the screen; it scrolls into view and is ringed.",
)
