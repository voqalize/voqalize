"""What the customer did — the browser→brain half of Aura's screen contract.

The other direction is the :class:`~voqalize.sdk.Action` classes in ``brain.py``:
a declared shape whose wire name comes off the class name, validated at the call
site, with a generated TypeScript twin. :class:`~voqalize.sdk.AppEvent` is that,
mirrored — so ``on_rtvi`` narrows on a *type* rather than being handed the whole
page and left to work out what moved in it.

Aura has three kinds of inbound traffic, and they read differently on purpose:

  * **the customer's own hand** — they clicked into a category, paused the clip,
    closed the helpline panel. Aria is told *that* they did it, never what the
    screen now says; the screen is read back through ``get_screen_context``.
  * **what only the browser holds** — the calculator they edited, the field they
    typed into, the forex reference the page minted. The act is what goes into
    the context; the values go into Aria's mirror, where they cannot go stale.
  * **an answer to a dialog Aria opened** — the sign-in, the account picker, the
    card picker. Each carries the ``nonce`` the brain minted, which is what makes
    it trustworthy: it went out with one dialog, closes that one dialog once, and
    a replayed or mismatched answer matches nothing. This is not the reconciliation
    nonce that died with ``state_sync`` — it is a handshake token for a question
    the customer has been asked.

There is no "page opened" event. The home page is where every call starts, so
Aria's picture begins there rather than waiting to be told.

:class:`VideoProgressed` is the one event that produces no line of context at all.
A clip crossing into its next chapter is nobody's decision and no news, but it is
the only place the current step exists — and a note per chapter would refuse every
video tool for the rest of the clip. It folds into the mirror and says nothing.
"""

from __future__ import annotations

from pydantic import Field

from voqalize.sdk import AppEvent, AppEvents

__all__ = [
    "AURA_EVENTS",
    "AccountCancelled",
    "AccountSelected",
    "ApplicationStarted",
    "ApplicationSubmitted",
    "ArticleOpened",
    "AuraEvent",
    "AuthCancelled",
    "AuthCompleted",
    "CalculatorChanged",
    "CalculatorOpened",
    "CardCancelled",
    "CardControlsSaved",
    "CardSelected",
    "CategoryOpened",
    "ContactClosed",
    "FieldFilled",
    "ForexLeadSubmitted",
    "HelpCenterOpened",
    "HomeOpened",
    "VideoPaused",
    "VideoProgressed",
    "VideoResumed",
    "VideoSeeked",
]


# ─── The customer's own hand: moving around ───────────────────────────────────


class HomeOpened(AppEvent):
    """The customer went back to the Aura Bank home page."""


class HelpCenterOpened(AppEvent):
    """The customer opened the help centre's category index."""


class CategoryOpened(AppEvent):
    """The customer opened one help-centre category themselves."""

    category: str


class ArticleOpened(AppEvent):
    """The customer opened one help article themselves."""

    article_id: str


class ContactClosed(AppEvent):
    """The customer closed the helpline panel."""


# ─── The customer's own hand: the clip ────────────────────────────────────────


class VideoPaused(AppEvent):
    """The customer paused the clip."""


class VideoResumed(AppEvent):
    """The customer started the clip playing again."""


class VideoSeeked(AppEvent):
    """The customer tapped a step in the list, which jumps the clip to it."""

    start_sec: float = 0
    step_index: int = 0


class VideoProgressed(AppEvent):
    """The clip crossed into its next chapter — the page's own clock, not a
    gesture. Folded into the mirror in silence; see the module docstring."""

    step_index: int = 0


# ─── What only the browser holds ──────────────────────────────────────────────


class CalculatorOpened(AppEvent):
    """The customer opened a calculator off the help page's quick links, which
    arrives already filled in with that link's figures and solved."""

    kind: str = Field("emi", description="One of emi, fd, eligibility.")
    inputs: dict[str, float] = Field(default_factory=dict)
    result: dict[str, float] = Field(default_factory=dict)


class CalculatorChanged(AppEvent):
    """The customer edited a calculator input, and the page re-solved it."""

    inputs: dict[str, float] = Field(default_factory=dict)
    result: dict[str, float] = Field(default_factory=dict)


class ApplicationStarted(AppEvent):
    """The customer started an application themselves, off a quick link."""

    product: str = Field("savings", description="One of savings, credit_card, loan.")


class FieldFilled(AppEvent):
    """The customer typed into one field of the open application."""

    field: str
    value: str = ""


class ApplicationSubmitted(AppEvent):
    """The customer submitted the open application themselves."""


class CardControlsSaved(AppEvent):
    """The customer saved the usage & limits form. The values are theirs — they
    edited the toggles and sliders on screen, and this is the only copy."""

    domestic_enabled: bool = False
    international_enabled: bool = False
    contactless_enabled: bool = False
    online_enabled: bool = False
    domestic_limit: float = 0
    international_limit: float = 0
    atm_cash_limit: float = 0


class ForexLeadSubmitted(AppEvent):
    """The customer requested the forex card. The page mints the reference, so it
    rides along — there is nowhere else Aria could read it."""

    reference: str = ""


# ─── An answer to a dialog Aria opened ────────────────────────────────────────


class AuthCompleted(AppEvent):
    """The customer authorised the secure sign-in. THIS is what mints the handle,
    server-side, which is why the model can never produce one itself."""

    nonce: str


class AuthCancelled(AppEvent):
    """The customer closed the sign-in without signing in — an answer too."""

    nonce: str


class AccountSelected(AppEvent):
    """The customer tapped an account in the picker."""

    nonce: str
    account_id: str


class AccountCancelled(AppEvent):
    """The customer dismissed the account picker."""

    nonce: str


class CardSelected(AppEvent):
    """The customer tapped a card in the picker."""

    nonce: str
    card_id: str


class CardCancelled(AppEvent):
    """The customer dismissed the card picker."""

    nonce: str


type AuraEvent = (
    HomeOpened
    | HelpCenterOpened
    | CategoryOpened
    | ArticleOpened
    | ContactClosed
    | VideoPaused
    | VideoResumed
    | VideoSeeked
    | VideoProgressed
    | CalculatorOpened
    | CalculatorChanged
    | ApplicationStarted
    | FieldFilled
    | ApplicationSubmitted
    | CardControlsSaved
    | ForexLeadSubmitted
    | AuthCompleted
    | AuthCancelled
    | AccountSelected
    | AccountCancelled
    | CardSelected
    | CardCancelled
)

AURA_EVENTS = AppEvents[AuraEvent](
    HomeOpened,
    HelpCenterOpened,
    CategoryOpened,
    ArticleOpened,
    ContactClosed,
    VideoPaused,
    VideoResumed,
    VideoSeeked,
    VideoProgressed,
    CalculatorOpened,
    CalculatorChanged,
    ApplicationStarted,
    FieldFilled,
    ApplicationSubmitted,
    CardControlsSaved,
    ForexLeadSubmitted,
    AuthCompleted,
    AuthCancelled,
    AccountSelected,
    AccountCancelled,
    CardSelected,
    CardCancelled,
)
