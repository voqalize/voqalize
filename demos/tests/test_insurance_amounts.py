"""Chhatri Insurance: Indian amounts heard and spoken (I2, X8).

The owner said "around 1 and half lakhs" and the claim form got ₹15; the bank's
voice read "₹1.25 Cr" as "1 rupee 25 crore". These pin the reading of every
shape the recognizer writes an amount in, and the words the voice is given.

Run: ``cd demos && uv run pytest tests/test_insurance_amounts.py``
"""

from __future__ import annotations

from datetime import date

import pytest
from voqalize_demos.discovery import discover

discover()

from voqalize_demos._loaded.insurance import amounts, claims  # noqa: E402


@pytest.mark.parametrize(
    ("said", "rupees"),
    [
        # The owner's words, and what the recognizer may have written for them.
        ("around 1 and half lakhs", 150_000),
        ("one and a half lakh", 150_000),
        ("1.5 lakhs", 150_000),
        ("1.5L", 150_000),
        ("one lakh fifty thousand", 150_000),
        ("1 lakh 50 thousand", 150_000),
        ("1,50,000", 150_000),
        ("₹1,50,000", 150_000),
        ("150000 rupees", 150_000),
        ("a lakh and a half", 150_000),
        ("one point five lakh", 150_000),
        # Thousands, crores, k.
        ("15k", 15_000),
        ("15 thousand", 15_000),
        ("fifteen thousand", 15_000),
        ("twenty five thousand five hundred", 25_500),
        ("2 lakh 34,567 rupees", 234_567),
        ("2.5 crore", 25_000_000),
        ("1.25 Cr", 12_500_000),
        ("Rs. 45,000", 45_000),
        ("half a lakh", 50_000),
        # Hindi, typed in Latin and in Devanagari.
        ("dedh lakh", 150_000),
        ("dhai lakh", 250_000),
        ("sava do lakh", 225_000),
        ("saade teen lakh", 350_000),
        ("paune do lakh", 175_000),
        ("15 hazaar", 15_000),
        ("ek lakh pachaas hazaar", 150_000),
        ("डेढ़ लाख", 150_000),
        ("ढाई लाख रुपये", 250_000),
        ("एक लाख पचास हज़ार", 150_000),
        ("एक लाख पचास हजार रुपए", 150_000),
        ("सवा करोड़", 12_500_000),
        ("\u0967,\u096b\u0966,\u0966\u0966\u0966", 150_000),  # Devanagari digits
        ("लगभग दो लाख", 200_000),
    ],
)
def test_every_shape_of_a_spoken_amount_is_read_whole(said: str, rupees: int) -> None:
    heard = amounts.parse(said)
    assert heard is not None and heard.rupees == rupees, (said, heard)


def test_around_is_an_estimate_and_a_range_keeps_both_ends() -> None:
    assert amounts.parse("around 1 and half lakhs") == amounts.Amount(150_000, approx=True)
    assert amounts.parse("1 to 1.5 lakh") == amounts.Amount(150_000, approx=True, low=100_000)
    assert amounts.parse("between one and one and a half lakh") == amounts.Amount(
        150_000, approx=True, low=100_000
    )
    assert amounts.parse("no idea") is None


def test_the_claim_form_never_stores_an_amount_that_lost_its_unit() -> None:
    state = claims.ClaimState()
    state.start("health", "health-2026")
    today = date(2026, 11, 24)
    assert claims.normalise("claim_amount", "around 1 and half lakhs", state, today) == (
        "150000",
        "an estimate: fine for the form",
    )
    value, why = claims.normalise("claim_amount", "15", state, today)
    assert value is None and "too small" in why
    value, why = claims.normalise("claim_amount", "1.5", state, today)
    assert value is None and "too small" in why
    value, why = claims.normalise("claim_amount", "1 to 1.5 lakh", state, today)
    assert value == "150000" and "range" in why


@pytest.mark.parametrize(
    ("amount", "en", "hi"),
    [
        (150_000, "one lakh fifty thousand rupees", "डेढ़ लाख रुपये"),
        (250_000, "two lakh fifty thousand rupees", "ढाई लाख रुपये"),
        (125_000, "one lakh twenty-five thousand rupees", "सवा लाख रुपये"),
        (175_000, "one lakh seventy-five thousand rupees", "पौने दो लाख रुपये"),
        (350_000, "three lakh fifty thousand rupees", "साढ़े तीन लाख रुपये"),
        (12_500_000, "one crore twenty-five lakh rupees", "सवा करोड़ रुपये"),
        (
            44_775,
            "forty-four thousand seven hundred and seventy-five rupees",
            "चौवालीस हज़ार सात सौ पचहत्तर रुपये",
        ),
        (1_000_000, "ten lakh rupees", "दस लाख रुपये"),
        (105, "one hundred and five rupees", "एक सौ पाँच रुपये"),
    ],
)
def test_amounts_are_said_the_indian_way(amount: int, en: str, hi: str) -> None:
    assert amounts.words(amount, "en") == en
    assert amounts.words(amount, "hi") == hi


def test_written_amounts_reach_the_voice_as_words() -> None:
    # The TTS reads a two-decimal ₹ amount as rupees and paise ("₹1.25 Cr" →
    # "one rupee and twenty five paisa crore"): never hand it one.
    assert amounts.speakable("Cover of ₹1.25 Cr.") == "Cover of one crore twenty-five lakh rupees."
    assert amounts.speakable("₹1.25 करोड़ का कवर", "hi") == "सवा करोड़ रुपये का कवर"
    assert (
        amounts.speakable("Your premium is ₹31,395 a year.")
        == "Your premium is thirty-one thousand three hundred and ninety-five rupees a year."
    )
    assert amounts.speakable("about 1.5 lakh rupees") == "about one lakh fifty thousand rupees"
    assert amounts.speakable("10 lakh of cover") == "ten lakh of cover"
    assert amounts.speakable("₹5,000 to ₹10,000") == "five thousand rupees to ten thousand rupees"
    # What is not an amount stays as written.
    for text in (
        "Policy CHI/HL/26/0072415, clause 4.4.",
        "Admitted on 05 Nov 2026.",
        "Account 50100417234821, IFSC MRDN0000417.",
        "A waiting period of 24 months, 8.5% a year.",
    ):
        assert amounts.speakable(text) == text


def test_a_streamed_amount_split_across_pieces_is_said_whole() -> None:
    stream = amounts.SpokenAmounts("en")
    pieces = ["Got it, ", "₹1,", "50,", "000. Shall I use ", "your account ending 4821?"]
    out = "".join(stream.feed(p) for p in pieces) + stream.flush()
    assert out == "Got it, one lakh fifty thousand rupees. Shall I use your account ending 4821?"
    stream = amounts.SpokenAmounts("hi")
    out = "".join(stream.feed(p) for p in ["ठीक है, ₹1", ".5 ला", "ख का क्लेम।"]) + stream.flush()
    assert out == "ठीक है, डेढ़ लाख रुपये का क्लेम।"
