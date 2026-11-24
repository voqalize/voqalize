"""Wanderloom Holidays: amounts in speech, both ways (FEEDBACK X8).

What the planner writes is rewritten into a form Voqalize's TTS reads right (its
text stage reads a rupee amount with two decimals as rupees and paise, so "₹1.25
lakh" would be "one rupee and twenty five paisa lakh"); what the visitor says
(a budget) is read into rupees, and an implausible budget is confirmed back.

Run: ``cd demos && uv run pytest tests/test_holidays_amounts.py``
"""

from __future__ import annotations

from typing import Any

import pytest
from voqalize_demos.discovery import discover

from voqalize.sdk import SpeechChunk, SpeechEnd, SpeechStart

discover()

from voqalize_demos._loaded.holidays import engine as eng  # noqa: E402
from voqalize_demos._loaded.holidays.spoken import (  # noqa: E402
    SpokenAmounts,
    amounts_note,
    implausible,
    parse_amounts,
    speak_text,
)


@pytest.mark.parametrize(
    ("written", "lang", "spoken"),
    [
        # Package totals and per-person prices as the tools give them (₹, Indian
        # grouping): left to the TTS, which reads them in lakh and thousand.
        ("Here's your whole package, ₹2,28,975 all in.", "en", None),
        ("Total ₹2,28,975, ₹1,14,488 per person.", "en", None),
        ("Goa from ₹15,840 per person, Switzerland from ₹1,30,765.", "en", None),
        ("यह रहा आपका पूरा पैकेज, सब मिलाकर ₹2,28,975।", "hi", None),
        # Lakh written by the model: spelled out in English, two decimals never reach the TTS.
        (
            "That's ₹1.25 lakh over your ₹2 lakh budget.",
            "en",
            "That's one point two five lakh rupees over your two lakh rupees budget.",
        ),
        (
            "Bali comes to about ₹2.29 lakh.",
            "en",
            "Bali comes to about two point two nine lakh rupees.",
        ),
        ("Packages run ₹1.5\u20132 lakh.", "en", "Packages run one point five to two lakh rupees."),
        ("₹1.5 lakh\u2013₹2 lakh.", "en", "one point five lakh rupees to two lakh rupees."),
        (
            "Nine of you in Switzerland: ₹14.2 L.",
            "en",
            "Nine of you in Switzerland: fourteen point two lakh rupees.",
        ),
        ("Under ₹1.14 Cr.", "en", "Under one point one four crore rupees."),
        ("A 5 L water bottle is included.", "en", None),
        ("Peak-season surcharge is 8\u201318%.", "en", "Peak-season surcharge is 8% to 18%."),
        # Hindi: lakh in Devanagari with the ₹ mark (the TTS says डेढ़ / सवा / ढाई); any
        # other decimal is whole rupees, ending at the danda.
        ("आपका बजट ₹1.5 lakh है।", "hi", "आपका बजट ₹1.5 लाख है।"),
        ("कुल ₹2.3 लाख।", "hi", "कुल ₹2,30,000।"),
        ("बजट ₹2.29 लाख है।", "hi", "बजट ₹2,29,000 है।"),
        ("पैकेज ₹1.5\u20132 लाख में।", "hi", "पैकेज ₹1.5 लाख से ₹2 लाख में।"),
        ("आप 2.5 लाख रुपये तक खर्च कर सकते हैं।", "hi", "आप ₹2.5 लाख तक खर्च कर सकते हैं।"),
    ],
)
def test_amounts_are_written_the_way_the_voice_reads_them(
    written: str, lang: str, spoken: str | None
) -> None:
    assert speak_text(written, lang) == (written if spoken is None else spoken)


def test_every_written_line_with_a_total_passes_untouched() -> None:
    """The brain's own lines carry engine totals (₹ and Indian grouping), which the TTS
    already reads right, so the rewrite leaves them alone."""
    total = eng.money(228975)
    assert total == "₹2,28,975"
    for lang in ("en", "hi"):
        line = f"Done, that flight is in. The total is now {total}."
        assert speak_text(line, lang) == line


@pytest.mark.parametrize(
    ("heard", "values"),
    [
        ("our budget is around 2 lakhs", [200000]),
        ("around 1 and half lakhs for the two of us", [150000, 2]),
        ("one and a half lakh", [150000]),
        ("a lakh and a half", [150000]),
        ("one point five lakh", [150000]),
        ("1.5 lakhs", [150000]),
        ("150000 rupees", [150000]),
        ("1,50,000", [150000]),
        ("two lakh fifty thousand", [250000]),
        ("80k per person", [80000]),
        ("80 hazaar each", [80000]),
        ("dedh lakh", [150000]),
        ("dhai lakh", [250000]),
        ("sava do lakh", [225000]),
        ("saade teen lakh", [350000]),
        ("paune do lakh", [175000]),
        ("डेढ़ लाख", [150000]),
        ("लगभग ढाई लाख रुपये", [250000]),
        ("दो लाख पचास हजार", [250000]),
        ("अस्सी हज़ार", [80000]),
        ("₹\u0967,\u096b\u0966,\u0966\u0966\u0966", [150000]),
        # Ranges say the scale once: both ends in rupees.
        ("one and a half to two lakh", [150000, 200000]),
        ("1.5-2 lakh", [150000, 200000]),
        ("between 1 and 2 lakh", [100000, 200000]),
        ("डेढ़ से दो लाख", [150000, 200000]),
        # A count next to an amount is not added to it.
        ("I have 80 thousand and 2 kids", [80000, 2]),
        ("Around two thousand and eighty", [2080]),
    ],
)
def test_spoken_amounts_parse_to_rupees(heard: str, values: list[float]) -> None:
    assert [h.value for h in parse_amounts(heard)] == values


def test_the_model_is_told_what_the_visitor_said_in_rupees() -> None:
    assert amounts_note("around 1 and half lakhs") == (
        "[Amounts they said, in rupees: '1 and half lakhs' = about 150000 rupees.]"
    )
    assert amounts_note("somewhere between one and a half to two lakh") == (
        "[Amounts they said, in rupees: 'one and a half to two lakh' = 150000 to 200000 "
        "rupees (a range).]"
    )
    assert amounts_note("two adults, six nights") is None


def test_an_implausible_budget_is_confirmed_back_never_used() -> None:
    why = implausible({"budget": 15}, ["around 1 and half lakhs"])
    assert why is not None and why.startswith("Not done")
    assert "₹1,50,000" in why and "₹1.5 lakh, right?" in why
    asked = implausible({"budget": 30}, ["fifteen"])
    assert asked is not None and "Sorry, what budget was that?" in asked
    assert implausible({"budget": 150000}, ["1.5 lakh"]) is None
    assert implausible({"budget": 0}, ["no budget"]) is None


async def test_an_amount_split_across_streamed_chunks_is_still_said_whole() -> None:
    async def stream() -> Any:
        yield SpeechStart()
        for piece in ["That's ₹1.", "25 la", "kh over budget; ₹1.5", "\u20132 lakh is typical."]:
            yield SpeechChunk(piece)
        yield SpeechEnd()

    out = [e async for e in SpokenAmounts(lambda: "en").wrap(stream())]
    assert isinstance(out[0], SpeechStart) and isinstance(out[-1], SpeechEnd)
    text = "".join(e.text for e in out if isinstance(e, SpeechChunk))
    assert text == (
        "That's one point two five lakh rupees over budget; one point five to two lakh rupees "
        "is typical."
    )


# ─── Whitespace around a rewritten amount ─────────────────────────────────────

#: Amounts as a piece of streamed speech may start or end with them, with and without ₹.
_WS_AMOUNTS = [
    ("en", "7.2 lakh"),
    ("en", "₹7.2 lakh"),
    ("en", "1.14 crore"),
    ("en", "₹1.14 crore"),
    ("en", "₹8 to 12 lakh"),
    ("en", "Rs 5 lakh"),
    ("hi", "7.2 लाख"),
    ("hi", "₹7.2 लाख"),
    ("hi", "₹1.25 करोड़"),
    ("hi", "₹8 से 12 लाख"),
]


@pytest.mark.parametrize(("lang", "amount"), _WS_AMOUNTS)
@pytest.mark.parametrize(("before", "after"), [(" ", ""), ("", " "), (" ", " "), ("Fees: ", ", ")])
def test_a_rewritten_amount_keeps_the_whitespace_around_it(
    lang: str, amount: str, before: str, after: str
) -> None:
    """The stream is rewritten in pieces, and a piece may start or end with a space: a
    leading space eaten with the amount ran "It costs" into "seven point two lakh"."""
    assert speak_text(f"{before}{amount}{after}", lang) == (
        f"{before}{speak_text(amount, lang)}{after}"
    )


async def _ws_streamed(units: list[list[str]], lang: str) -> str:
    from voqalize.sdk import SpeechChunk, SpeechEnd, SpeechStart

    async def stream() -> Any:
        for unit in units:
            yield SpeechStart()
            for piece in unit:
                yield SpeechChunk(piece)
            yield SpeechEnd()

    out = [e async for e in SpokenAmounts(lambda: lang).wrap(stream())]
    return "".join(e.text for e in out if isinstance(e, SpeechChunk))


@pytest.mark.parametrize(
    ("lang", "sentence"),
    [
        ("en", "It costs 7.2 lakh a year."),
        ("en", "The flat is ₹1.14 crore now."),
        ("hi", "यह ₹7.2 लाख का है।"),
        ("en", "Fees: 7.2 lakh a year."),
        ("hi", "शुल्क: 7.2 लाख है।"),
    ],
)
async def test_every_two_chunk_split_speaks_like_the_whole_sentence(
    lang: str, sentence: str
) -> None:
    """However the model's tokens fall, the voice hears what the whole sentence rewrites to;
    so it does when the amount opens a second unit (" 7.2 lakh a year." after "It costs")."""
    whole = speak_text(sentence, lang)
    for i in range(1, len(sentence)):
        head, tail = sentence[:i], sentence[i:]
        assert await _ws_streamed([[head, tail]], lang) == whole, (head, tail)
        if tail[0] == " " and tail[1] in "₹0123456789":  # an amount starts the second unit
            assert await _ws_streamed([[head], [tail]], lang) == whole, (head, tail)
