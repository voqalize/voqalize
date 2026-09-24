"""The Vantage Bank card shelf, and the two strings every fact on it carries.

Vantage Bank is invented. Nothing here names, quotes or paraphrases a real bank
or a real card.

**Two strings per fact, and the split is load bearing.** Every number on this
shelf exists twice: a ``_display`` form for the screen, which may carry numerals
and symbols, and a ``_spoken`` form for the voice, which is words only. They are
not interchangeable and the display form must never reach the TTS — a voice
handed ``5%`` says "five percent sign", handed ``2-3x`` says "two minus three
ex", and handed ``fuel_and_transport`` says "fuel underscore and underscore
transport". So the enums are mapped to phrases here too, before anything
interpolates one into a sentence.

Indian currency is the sharper half of the same rule. ``1,50,000`` is "one and a
half lakh rupees", not "one lakh fifty thousand" and never "one hundred fifty
thousand"; ``30,00,000`` is "thirty lakh rupees" and never "three million". That
is what :func:`spoken_rupees` is for, and why no amount is ever formatted for
speech at the call site.

This module is pure data and pure functions: no SDK import, no session, no model.
The brain projects it onto the wire; the rules read it; it never speaks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__ = [
    "CARDS",
    "CARD_BY_ID",
    "EMPLOYMENT_SPOKEN",
    "EXISTING_CARDS_SPOKEN",
    "INCOME_BAND_SPOKEN",
    "PROFILE_CHOICES",
    "PROFILE_PROMPTS",
    "SPEND_DISPLAY",
    "SPEND_SPOKEN",
    "VALUE_PROMPTS",
    "CapturedField",
    "Card",
    "Employment",
    "ExistingCards",
    "IncomeBand",
    "ProfileField",
    "SpendCategory",
    "card_by_id",
    "format_inr",
    "spoken_amount",
    "spoken_characters",
    "spoken_digits",
    "spoken_rupees",
    "spoken_score",
]

# ─── The four discovery vocabularies ───────────────────────────────────────────
# Closed on purpose. The customer speaks freely and the model resolves what they
# said to one of these tokens; nothing downstream ever sees the free text, so no
# rule here has to cope with "about forty odd thousand".

Employment = Literal["salaried", "self_employed", "government", "student"]
IncomeBand = Literal["under_25k", "25k_60k", "60k_150k", "over_150k"]
ExistingCards = Literal["none", "one", "more_than_one"]
SpendCategory = Literal["fuel", "groceries", "online", "travel", "dining", "bills"]

#: The four questions, in the order they are asked.
ProfileField = Literal["employment", "income_band", "existing_cards", "spend_category"]

#: Everything the customer can say that lands on screen as a value: the four
#: closed answers plus the two free-form ones they read out in the cubicle.
CapturedField = Literal[
    "employment", "income_band", "existing_cards", "spend_category", "mobile", "pan"
]


# ─── Numbers as words ──────────────────────────────────────────────────────────

_ONES = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen",
)  # fmt: skip
_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")

#: Indian units, largest first, and whether "and a half" reads naturally on one.
#: It does on a lakh ("one and a half lakh"); it does not on a thousand, where
#: "twelve thousand five hundred" is what a teller says.
_UNITS: tuple[tuple[int, str, bool], ...] = (
    (10_000_000, "crore", True),
    (100_000, "lakh", True),
    (1_000, "thousand", False),
)


def _words_under_thousand(value: int) -> str:
    """0 to 999 in words."""
    if value < 20:
        return _ONES[value]
    if value < 100:
        tens, ones = divmod(value, 10)
        return _TENS[tens] + (f" {_ONES[ones]}" if ones else "")
    hundreds, rest = divmod(value, 100)
    return f"{_ONES[hundreds]} hundred" + (f" {_words_under_thousand(rest)}" if rest else "")


def spoken_amount(value: int) -> str:
    """An amount in Indian words, with no unit: ``150000`` → "one and a half lakh".

    The half shortcut is how the number is actually said — a customer hears "one
    and a half lakh" and reads ``1,50,000`` off the screen beside it, and both
    say the same thing.
    """
    for unit, name, halves in _UNITS:
        if value < unit:
            continue
        whole, rest = divmod(value, unit)
        if halves and rest == unit // 2:
            return f"{_words_under_thousand(whole)} and a half {name}"
        head = f"{_words_under_thousand(whole)} {name}"
        return head if not rest else f"{head} {spoken_amount(rest)}"
    return _words_under_thousand(value)


def spoken_rupees(value: int) -> str:
    """An amount as the voice says it: ``12500`` → "twelve thousand five hundred
    rupees". Never a rupee sign, and never a western grouping."""
    return f"{spoken_amount(value)} rupees"


def spoken_score(minimum: int) -> str:
    """A bureau threshold as a phrase. The band is spoken, the number never is —
    ``700`` → "a credit score of seven hundred or more"."""
    return f"a credit score of {_words_under_thousand(minimum)} or more"


def spoken_digits(digits: str) -> str:
    """A number read out digit by digit, grouped in fives the way a mobile number
    is said: ``"9876543210"`` → "nine eight seven six five, four three two one
    zero"."""
    groups = [digits[index : index + 5] for index in range(0, len(digits), 5)]
    return ", ".join(" ".join(_ONES[int(digit)] for digit in group) for group in groups)


def spoken_characters(value: str) -> str:
    """A PAN read back as it is dictated: letters spelled, digits said —
    ``"ABCDE1234F"`` → "A B C D E, one two three four, F"."""
    groups: list[str] = []
    run: list[str] = []
    numeric = False
    for char in value:
        if char.isdigit() != numeric and run:
            groups.append(" ".join(run))
            run = []
        numeric = char.isdigit()
        run.append(_ONES[int(char)] if numeric else char.upper())
    if run:
        groups.append(" ".join(run))
    return ", ".join(groups)


def format_inr(value: int) -> str:
    """Indian digit grouping, for the screen only: ``150000`` → ``"1,50,000"``."""
    text = str(value)
    if len(text) <= 3:
        return text
    head, tail = text[:-3], text[-3:]
    pairs = [head[max(index - 2, 0) : index] for index in range(len(head), 0, -2)]
    return ",".join(reversed(pairs)) + "," + tail


# ─── Enums as phrases ──────────────────────────────────────────────────────────
# Every token above, mapped once, so nothing interpolates a wire value into a
# sentence. A missing entry is a KeyError here rather than a noise the customer
# hears.

EMPLOYMENT_SPOKEN: dict[Employment, str] = {
    "salaried": "salaried",
    "self_employed": "self employed",
    "government": "in government service",
    "student": "a student",
}

INCOME_BAND_SPOKEN: dict[IncomeBand, str] = {
    "under_25k": "under twenty five thousand rupees a month",
    "25k_60k": "between twenty five and sixty thousand rupees a month",
    "60k_150k": "between sixty thousand and one and a half lakh rupees a month",
    "over_150k": "over one and a half lakh rupees a month",
}

EXISTING_CARDS_SPOKEN: dict[ExistingCards, str] = {
    "none": "no credit card yet",
    "one": "one credit card",
    "more_than_one": "more than one credit card",
}

SPEND_SPOKEN: dict[SpendCategory, str] = {
    "fuel": "fuel",
    "groceries": "groceries",
    "online": "online shopping",
    "travel": "travel",
    "dining": "eating out",
    "bills": "bills",
}

SPEND_DISPLAY: dict[SpendCategory, str] = {
    "fuel": "Fuel",
    "groceries": "Groceries",
    "online": "Online",
    "travel": "Travel",
    "dining": "Dining",
    "bills": "Bills",
}

#: What each question offers, as ``(value, English label, Hindi label)``. The
#: labels are the screen's; the voice never reads a list of options aloud, it
#: asks the question and lets the screen hold the choices.
PROFILE_CHOICES: dict[ProfileField, tuple[tuple[str, str, str], ...]] = {
    "employment": (
        ("salaried", "Salaried", "नौकरी"),
        ("self_employed", "Self employed", "अपना काम"),
        ("government", "Government", "सरकारी नौकरी"),
        ("student", "Student", "विद्यार्थी"),
    ),
    "income_band": (
        ("under_25k", "Under 25,000", "25,000 से कम"),
        ("25k_60k", "25,000 to 60,000", "25,000 से 60,000"),
        ("60k_150k", "60,000 to 1,50,000", "60,000 से 1,50,000"),
        ("over_150k", "Over 1,50,000", "1,50,000 से ज़्यादा"),
    ),
    "existing_cards": (
        ("none", "None yet", "अभी कोई नहीं"),
        ("one", "One", "एक"),
        ("more_than_one", "More than one", "एक से ज़्यादा"),
    ),
    "spend_category": (
        ("fuel", "Fuel", "पेट्रोल"),
        ("groceries", "Groceries", "राशन"),
        ("online", "Online", "ऑनलाइन"),
        ("travel", "Travel", "यात्रा"),
        ("dining", "Dining", "बाहर खाना"),
        ("bills", "Bills", "बिल"),
    ),
}


#: The question the *totem* puts on the glass, per language, when the customer
#: is driving with their hand and there is no spoken line to carry it. When Tess
#: asks a question she writes her own; this is the screen's, and it is written
#: here rather than generated so nothing a model authored lands on a bank's glass.
PROFILE_PROMPTS: dict[ProfileField, tuple[str, str]] = {
    "employment": ("What do you do?", "आप क्या करते हैं?"),
    "income_band": ("What comes in every month?", "हर महीने कितना आता है?"),
    "existing_cards": ("How many credit cards do you have?", "आपके पास कितने क्रेडिट कार्ड हैं?"),
    "spend_category": ("Where does most of your money go?", "सबसे ज़्यादा खर्च किस पर होता है?"),
}

#: The two values a customer types in themselves, as ``(English label, Hindi
#: label, keypad)``. The keypad is what goes under their finger: digits for a
#: mobile number, letters and digits for a PAN.
VALUE_PROMPTS: dict[str, tuple[str, str, str]] = {
    "mobile": ("Mobile number", "मोबाइल नंबर", "tel"),
    "pan": ("PAN", "पैन नंबर", "text"),
}


# ─── The shelf ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Card:
    """One Vantage Bank card: its copy, its gates, and both forms of every figure.

    The hand-written pairs are the ones no formatter can derive — a reward rate
    reads differently in a table and in a sentence. Everything numeric derives
    from the one number beside it, so the screen and the voice cannot drift.
    """

    id: str
    name: str
    #: Annual fee in rupees; ``0`` is lifetime free.
    fee_inr: int
    #: Annual spend that waives the fee; ``None`` where there is no fee to waive.
    waiver_inr: int | None
    reward_display: str
    reward_spoken: str
    perk_display: str
    perk_spoken: str
    #: The indicative limit, in the bank's own words. Never computed.
    line_display: str
    line_spoken: str
    #: The spend this card is built for; the shortlist ranks on it.
    affinity: SpendCategory
    #: Monthly income floor, in rupees. ``0`` for the secured card.
    min_income_inr: int
    #: Bureau floor. Used to gate; never spoken, never rendered.
    min_bureau: int
    min_age: int
    max_age: int
    #: Secured against a fixed deposit, so it needs neither income proof nor a score.
    secured: bool = False

    @property
    def fee_display(self) -> str:
        return "No fee, ever" if not self.fee_inr else f"₹{format_inr(self.fee_inr)} a year"

    @property
    def fee_spoken(self) -> str:
        if not self.fee_inr:
            return "no joining fee and no annual fee"
        return f"{spoken_rupees(self.fee_inr)} a year"

    @property
    def waiver_display(self) -> str:
        if self.waiver_inr is None:
            return "Nothing to waive"
        return f"Waived on ₹{format_inr(self.waiver_inr)} spend a year"

    @property
    def waiver_spoken(self) -> str:
        if self.waiver_inr is None:
            return "there is no fee to waive"
        return f"the fee is waived once you spend {spoken_rupees(self.waiver_inr)} in a year"

    @property
    def requirement_display(self) -> str:
        if self.secured:
            return "No income proof, no score needed"
        return f"₹{format_inr(self.min_income_inr)} a month, score {self.min_bureau}+"

    @property
    def requirement_spoken(self) -> str:
        if self.secured:
            return "no income proof and no credit score needed"
        return f"{spoken_rupees(self.min_income_inr)} a month, and {spoken_score(self.min_bureau)}"


#: The five cards, richest last. Order is the tier order the shortlist ranks on.
CARDS: tuple[Card, ...] = (
    Card(
        id="vantage_rise",
        name="Vantage Rise",
        fee_inr=0,
        waiver_inr=None,
        reward_display="1% on everything, up to ₹500 a month",
        reward_spoken="one percent on everything, up to five hundred rupees a month",
        perk_display="Secured against your fixed deposit, limit is 80% of the deposit",
        perk_spoken=(
            "it is secured against a fixed deposit, and the limit is eighty percent of that deposit"
        ),
        line_display="80% of your fixed deposit",
        line_spoken="eighty percent of your fixed deposit",
        affinity="bills",
        min_income_inr=0,
        min_bureau=0,
        min_age=18,
        max_age=70,
        secured=True,
    ),
    Card(
        id="vantage_fuel",
        name="Vantage Fuel",
        fee_inr=500,
        waiver_inr=100_000,
        reward_display="4% at any pump, up to ₹400 a month",
        reward_spoken="four percent at any pump, up to four hundred rupees a month",
        perk_display="1% fuel surcharge waived on fills of ₹500 to ₹4,000",
        perk_spoken=(
            "the one percent fuel surcharge is waived on fills between "
            "five hundred and four thousand rupees"
        ),
        line_display="2x your monthly income",
        line_spoken="two times your monthly income",
        affinity="fuel",
        min_income_inr=20_000,
        min_bureau=650,
        min_age=21,
        max_age=65,
    ),
    Card(
        id="vantage_everyday",
        name="Vantage Everyday",
        fee_inr=500,
        waiver_inr=150_000,
        reward_display="5% online, 1% everywhere else, up to ₹1,000 a month",
        reward_spoken=(
            "five percent online, one percent everywhere else, up to one thousand rupees a month"
        ),
        perk_display="Rewards come back as statement credit, nothing to redeem",
        perk_spoken="the rewards come back as statement credit, so there is nothing to redeem",
        line_display="2x to 3x your monthly income",
        line_spoken="two to three times your monthly income",
        affinity="online",
        min_income_inr=25_000,
        min_bureau=700,
        min_age=21,
        max_age=60,
    ),
    Card(
        id="vantage_voyage",
        name="Vantage Voyage",
        fee_inr=5_000,
        waiver_inr=800_000,
        reward_display="5 miles per ₹100 on travel, 2 miles elsewhere",
        reward_spoken="five miles per hundred rupees on travel, and two miles everywhere else",
        perk_display="18 domestic and 12 international lounge visits a year",
        perk_spoken="eighteen domestic and twelve international lounge visits a year",
        line_display="3x to 4x your monthly income",
        line_spoken="three to four times your monthly income",
        affinity="travel",
        min_income_inr=75_000,
        min_bureau=750,
        min_age=21,
        max_age=65,
    ),
    Card(
        id="vantage_crest",
        name="Vantage Crest",
        fee_inr=12_500,
        waiver_inr=2_500_000,
        reward_display="3% on everything, no cap",
        reward_spoken="three percent on everything, with no cap",
        perk_display="Unlimited lounge access worldwide, plus a guest",
        perk_spoken="unlimited lounge access worldwide, and a guest with you",
        line_display="Set individually, from ₹5,00,000",
        line_spoken="set individually, starting at five lakh rupees",
        affinity="dining",
        min_income_inr=250_000,
        min_bureau=750,
        min_age=23,
        max_age=65,
    ),
)

CARD_BY_ID: dict[str, Card] = {card.id: card for card in CARDS}


def card_by_id(card_id: str) -> Card | None:
    """The card with this id, or ``None`` — a model that invented an id is told
    so rather than crashing the turn."""
    return CARD_BY_ID.get(card_id.strip())
