"""The rules. Deterministic Python, never model arithmetic.

Two pure functions and nothing else: :func:`assess` decides what the customer is
likely eligible for, :func:`shortlist` ranks what to show them. Both are total,
both are instant — plain dictionary lookups and comparisons, no I/O and no
sleeps — and neither of them speaks.

Three properties this file exists to hold:

**No number the model chose.** A model asked to compare an income against a
threshold will get it right most of the time, and the times it does not are a
bank telling a walk-in customer the wrong thing in a branch. So the model resolves
what was *said* into one of the closed tokens in ``cards.py`` and the arithmetic
happens here.

**No credit score ever leaves.** A score is simulated from the declared profile
because a kiosk demo has no bureau to call, and that simulated number gates the
cards and is then thrown away. What comes out is a band and a reason in plain
words. There is no field on :class:`Assessment` that could carry a score even by
accident.

**Nothing is approved.** :class:`Assessment` says *likely eligible*, and the band
names how wide the shelf is, not a decision. A banker confirms; the kiosk has no
tool that could submit anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .cards import (
    CARDS,
    SPEND_DISPLAY,
    SPEND_SPOKEN,
    Card,
    Employment,
    ExistingCards,
    IncomeBand,
    SpendCategory,
)

__all__ = ["Assessment", "Band", "Shortlist", "ShortlistRow", "assess", "shortlist"]

#: How wide the shelf is for this customer. Not a decision, and not a score.
Band = Literal["wide", "standard", "secured"]

#: The monthly income a band is worth for gating. A band is a range and the gate
#: needs one number, so this is the figure the bank is willing to work from until
#: a banker sees a payslip. It is deliberately mid-band rather than the floor: the
#: floor would put every customer one tier below the card they will actually be
#: offered, which is a worse demo *and* worse advice.
_INCOME_FOR_BAND: dict[IncomeBand, int] = {
    "under_25k": 18_000,
    "25k_60k": 40_000,
    "60k_150k": 100_000,
    "over_150k": 250_000,
}

#: The simulated bureau score, from what the customer declared. There is no
#: bureau behind a kiosk demo, so this stands in for one — and it never leaves
#: this module: it gates the cards in :func:`assess` and is discarded there.
_THICK_FILE = 760  # more than one card, managed for a while
_ESTABLISHED = 710  # one card, in good standing
_THIN_FILE = 680  # no card yet, but an income a lender can see
_NEW_TO_CREDIT = 660  # no card yet, little for a lender to go on
_NO_HISTORY = 0  # nothing at all: a student, or a first-ever account

#: Below this, the secured card is the honest answer whatever else clears.
_SECURED_ROUTE_BELOW = 700

#: The income floor that makes a card premium, and so makes the shelf "wide"
#: rather than "standard". It is the same figure as ``vantage_voyage``'s
#: ``min_income_inr`` and has to stay that way; named here so the bare literal is
#: not sitting in the middle of the band expression where nobody would find it.
_PREMIUM_INCOME_FLOOR = 75_000


def _simulated_bureau(employment: Employment, income_band: IncomeBand, cards: ExistingCards) -> int:
    """A stand-in score, from the profile the customer just declared."""
    if cards == "more_than_one":
        return _THICK_FILE
    if cards == "one":
        return _ESTABLISHED
    if employment == "student":
        return _NO_HISTORY
    return _THIN_FILE if income_band in ("60k_150k", "over_150k") else _NEW_TO_CREDIT


def _age_window(card: Card, employment: Employment) -> tuple[int, int]:
    """The card's own age window, tightened by the employment gate.

    The secured card is the exception the gate is written around: it is open from
    eighteen because it is backed by a deposit rather than by an income.
    """
    if card.secured:
        return card.min_age, card.max_age
    upper = 60 if employment == "salaried" else 65
    return max(card.min_age, 21), min(card.max_age, upper)


@dataclass(frozen=True)
class Assessment:
    """What the customer is likely eligible for, and why, in words.

    ``reasons`` are the screen's record, ``spoken`` is the single line the voice
    is allowed to say about it, and ``line_display`` / ``line_spoken`` are the
    indicative limit in the two forms every figure in this demo carries.
    """

    band: Band
    reasons: tuple[str, ...]
    spoken: str
    line_display: str
    line_spoken: str
    eligible_card_ids: tuple[str, ...]
    #: The file is thin enough that the secured card is the right first card,
    #: even where a fee card also clears.
    prefer_secured: bool


_BAND_SPOKEN: dict[Band, str] = {
    "wide": "you are likely eligible right across our range",
    "standard": "you are likely eligible for our main cards",
    "secured": "the surest start for you is our secured card",
}


def assess(
    *,
    employment: Employment,
    income_band: IncomeBand,
    existing_cards: ExistingCards,
    age: int | None = None,
) -> Assessment:
    """Which cards this profile likely clears, in a band and plain reasons.

    ``age`` is optional because the kiosk asks four questions and age is not one
    of them: the gate applies when the customer volunteered it and is left to the
    banker when they did not.
    """
    score = _simulated_bureau(employment, income_band, existing_cards)
    income = _INCOME_FOR_BAND[income_band]

    eligible = tuple(
        card
        for card in CARDS
        if score >= card.min_bureau
        and income >= card.min_income_inr
        and _within(_age_window(card, employment), age)
    )
    prefer_secured = score < _SECURED_ROUTE_BELOW
    band: Band = (
        "secured"
        if prefer_secured or all(card.secured for card in eligible)
        else "wide"
        if any(card.min_income_inr >= _PREMIUM_INCOME_FLOOR for card in eligible)
        else "standard"
    )
    best = _headline_card(eligible, prefer_secured)
    return Assessment(
        band=band,
        reasons=_reasons(employment, income_band, existing_cards, age, band),
        spoken=_BAND_SPOKEN[band],
        line_display=best.line_display,
        line_spoken=best.line_spoken,
        eligible_card_ids=tuple(card.id for card in eligible),
        prefer_secured=prefer_secured,
    )


def _headline_card(eligible: tuple[Card, ...], prefer_secured: bool) -> Card:
    """The card the indicative limit is quoted from.

    Normally the highest tier they clear. On a thin file it is the secured card,
    because that is the one :func:`shortlist` will recommend a moment later — and
    a limit quoted off a card nobody then recommends is the kiosk contradicting
    itself between two screens.
    """
    if not eligible:
        return CARDS[0]
    if prefer_secured:
        return next((card for card in eligible if card.secured), eligible[-1])
    return eligible[-1]


def _within(window: tuple[int, int], age: int | None) -> bool:
    """Age gate, open when the customer never said one."""
    if age is None:
        return True
    low, high = window
    return low <= age <= high


_EMPLOYMENT_REASON: dict[Employment, str] = {
    "salaried": "Salaried income",
    "self_employed": "Self employed income",
    "government": "Government salary",
    "student": "Student, no income declared",
}

_INCOME_REASON: dict[IncomeBand, str] = {
    "under_25k": "Declared income under ₹25,000 a month",
    "25k_60k": "Declared income ₹25,000 to ₹60,000 a month",
    "60k_150k": "Declared income ₹60,000 to ₹1,50,000 a month",
    "over_150k": "Declared income over ₹1,50,000 a month",
}

_HISTORY_REASON: dict[ExistingCards, str] = {
    "none": "New to credit cards",
    "one": "One card already, in good standing",
    "more_than_one": "An established card history",
}

_BAND_REASON: dict[Band, str] = {
    "wide": "Clears our premium range, subject to a banker's check",
    "standard": "Clears our main range, subject to a banker's check",
    "secured": "A secured card is the surest first card here",
}


def _reasons(
    employment: Employment,
    income_band: IncomeBand,
    existing_cards: ExistingCards,
    age: int | None,
    band: Band,
) -> tuple[str, ...]:
    """The screen's record of why. Every line is a band or a declaration the
    customer made themselves, and none of them is a score."""
    lines = [
        _EMPLOYMENT_REASON[employment],
        _INCOME_REASON[income_band],
        _HISTORY_REASON[existing_cards],
    ]
    if age is not None:
        lines.append(f"Age {age}, within range")
    lines.append(_BAND_REASON[band])
    return tuple(lines)


# ─── The shortlist ─────────────────────────────────────────────────────────────

#: What matching the customer's biggest spend is worth, against one tier step.
_AFFINITY_BONUS = 100
_TIER_STEP = 10
_SECURED_BONUS = 40
_SHORTLIST_SIZE = 3


@dataclass(frozen=True)
class ShortlistRow:
    """One card as it appears on the shortlist, and whether it is theirs today.

    A customer who clears only the secured card still sees three cards: the one
    they can take now, and the two the screen marks as not yet. That is the
    honest version of a shelf, and it is what makes ``eligible`` worth carrying.
    """

    card: Card
    eligible: bool


@dataclass(frozen=True)
class Shortlist:
    """Three cards, one of them recommended, and why in both forms."""

    rows: tuple[ShortlistRow, ...]
    recommended_id: str
    why_display: str
    why_spoken: str


def shortlist(assessment: Assessment, spend: SpendCategory) -> Shortlist:
    """Rank the shelf for this customer: affinity first, then tier.

    Affinity outweighs a full tier step because the card that pays the most on
    what they actually buy is the card that is right for them, and a thin file
    outweighs both — a secured card that is certain beats a fee card that a
    banker may still decline.
    """
    eligible = [card for card in CARDS if card.id in assessment.eligible_card_ids]
    ranked = sorted(eligible, key=lambda card: _score(card, assessment, spend), reverse=True)
    rows = [ShortlistRow(card=card, eligible=True) for card in ranked[:_SHORTLIST_SIZE]]
    rows += [
        ShortlistRow(card=card, eligible=False)
        for card in CARDS
        if card.id not in assessment.eligible_card_ids
    ][: _SHORTLIST_SIZE - len(rows)]

    recommended = rows[0].card
    return Shortlist(
        rows=tuple(rows),
        recommended_id=recommended.id,
        why_display=_why_display(recommended, assessment, spend),
        why_spoken=_why_spoken(recommended, assessment, spend),
    )


def _score(card: Card, assessment: Assessment, spend: SpendCategory) -> int:
    tier = CARDS.index(card) * _TIER_STEP
    affinity = _AFFINITY_BONUS if card.affinity == spend else 0
    secured = _SECURED_BONUS if assessment.prefer_secured and card.secured else 0
    return tier + affinity + secured


def _why_display(card: Card, assessment: Assessment, spend: SpendCategory) -> str:
    if card.affinity == spend:
        return f"{SPEND_DISPLAY[spend]} is your biggest spend, and this card pays the most on it"
    if assessment.prefer_secured and card.secured:
        return "Backed by your own deposit, so it is the surest first card"
    return "The strongest card your profile clears today"


def _why_spoken(card: Card, assessment: Assessment, spend: SpendCategory) -> str:
    if card.affinity == spend:
        return f"you spend most on {SPEND_SPOKEN[spend]}, and this one pays the most there"
    if assessment.prefer_secured and card.secured:
        return "it is backed by your own deposit, so it is the surest card to start with"
    return "it is the strongest card your profile clears today"
