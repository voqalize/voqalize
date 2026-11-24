"""Dantika Dental: Indian amounts spoken and heard (FEEDBACK X8).

The bank's voice read "₹1.25 Cr" as "1 rupee 25 crore": Voqalize's TTS reads a
rupee amount with exactly two decimals as rupees and paise. These pin what the
front desk hands the voice for every amount the clinic's data has (fees, fee
ranges, the crown's "₹8,000-₹18,000" (en dash), the late and no-show fees, the EMI
threshold) and for the shapes a model may write, in English and Hindi; and the
reading of what a patient says about money.

Run: ``cd demos && uv run pytest tests/test_dental_amounts.py``
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from voqalize_demos.discovery import discover

discover()

from voqalize_demos._loaded.dental import clinic as cl  # noqa: E402
from voqalize_demos._loaded.dental.prompt import GREETINGS, LINES  # noqa: E402
from voqalize_demos._loaded.dental.spoken import (  # noqa: E402
    SpokenAmounts,
    amounts_note,
    parse_amounts,
    speak_text,
)

#: What the TTS mangles: a rupee mark, then a number with exactly two decimals.
_MAJOR_MINOR = re.compile(r"(?:₹|Rs\.?|INR)\s*\d[\d,]*\.\d\d(?!\d)")
#: A dash between two amounts, which the Hindi chain was never verified on.
_DASH_RANGE = re.compile(r"\d\s*[-\u2013\u2014]\s*₹?\d")


@pytest.mark.parametrize(
    ("written", "lang", "spoken"),
    [
        # The clinic's own figures: plain rupees and "to" ranges go as written.
        ("A root canal is ₹6,500 to ₹12,000 per tooth.", "en", None),
        ("A check-up is ₹700; X-rays are ₹300 each.", "en", None),
        ("Within 24 hours there is a ₹300 late-change fee; a missed visit is ₹500.", "en", None),
        ("Treatments of ₹10,000 or more can be paid in no-cost EMIs.", "en", None),
        ("Root canal ₹6,500 से ₹12,000 तक है।", "hi", None),
        # A dash between two amounts says "to" (से), with ₹ on both ends.
        (
            "The crown afterwards is extra (₹8,000\u2013₹18,000).",
            "en",
            "The crown afterwards is extra (₹8,000 to ₹18,000).",
        ),
        ("A filling is ₹1,800-3,500 per tooth.", "en", "A filling is ₹1,800 to ₹3,500 per tooth."),
        ("Crown ₹8,000\u2013₹18,000 का है।", "hi", "Crown ₹8,000 से ₹18,000 का है।"),
        ("OPG ₹3,500 - ₹5,500 में।", "hi", "OPG ₹3,500 से ₹5,500 में।"),
        # Thousands written short become whole rupees.
        (
            "Whitening is about ₹9k; the kit is ₹4.5k.",
            "en",
            "Whitening is about ₹9,000; the kit is ₹4,500.",
        ),
        ("Scaling is ₹1.5k to ₹2.5k.", "en", "Scaling is ₹1,500 to ₹2,500."),
        ("It costs ₹15 thousand rupees.", "en", "It costs ₹15,000."),
        ("Whitening ₹9 हज़ार का है।", "hi", "Whitening ₹9,000 का है।"),
        # Lakh and crore: words in English, the Hindi way in Hindi; never "paisa crore".
        (
            "A full-mouth plan can reach ₹1.25 lakh.",
            "en",
            "A full-mouth plan can reach one point two five lakh rupees.",
        ),
        ("That's ₹1.25 Cr.", "en", "That's one point two five crore rupees."),
        ("₹1.5L in all.", "en", "one point five lakh rupees in all."),
        ("कुल ₹1.25 लाख है।", "hi", "कुल सवा लाख रुपये है।"),
        ("कुल ₹1.5 lakh है।", "hi", "कुल डेढ़ लाख रुपये है।"),
        ("₹2.75 लाख", "hi", "पौने तीन लाख रुपये"),
        ("₹1.85 लाख", "hi", "₹1,85,000"),
        ("₹2 लाख", "hi", "₹2 लाख"),
        # Paise in words: no ₹ with two decimals reaches the voice.
        ("A tube is ₹12.50.", "en", "A tube is twelve rupees and fifty paise."),
        ("₹12.50 लगेंगे।", "hi", "₹12 और पचास पैसे लगेंगे।"),
        # Not money: phone numbers, codes, times, counts.
        ("I sent the code to 98450 31726; it's 4821. See you at 2:15 pm.", "en", None),
        ("A root canal is 3 sittings, 7 to 14 days apart.", "en", None),
        ("Walk 2 thousand steps; a 4k screen.", "en", None),
    ],
)
def test_amounts_are_written_the_way_the_voice_reads_them(
    written: str, lang: str, spoken: str | None
) -> None:
    assert speak_text(written, lang) == (written if spoken is None else spoken)


@pytest.mark.parametrize("lang", ["en", "hi"])
def test_every_amount_in_the_clinic_data_is_safe_to_speak(lang: str) -> None:
    """Every price line the tools hand the model, the policy and payment text, the
    greetings and the brain's own lines: after the rewrite, no ₹ amount with two
    decimals and no dash between amounts is left."""
    texts = [f"{s.name}: {cl.price_text(s)}" for s in cl.DATA_.services]
    texts += [v.text for v in cl.DATA_.policies.values()]
    texts += [v.text for k, v in cl.DATA_.instructions.items() if k not in ("eating", "aftercare")]
    texts += [*GREETINGS[lang].values(), *LINES[lang].values()]  # type: ignore[index]
    for text in texts:
        said = speak_text(text, lang)
        assert not _MAJOR_MINOR.search(said), said
        assert not _DASH_RANGE.search(said), said
    crown = speak_text(cl.price_text(cl.service("rct")), lang)  # type: ignore[arg-type]
    assert ("₹8,000 से ₹18,000" if lang == "hi" else "₹8,000 to ₹18,000") in crown


@pytest.mark.parametrize(
    ("heard", "values"),
    [
        # How a patient asks about the clinic's fees, as a recogniser may write it.
        ("fifteen hundred to twenty five hundred", [1500, 2500]),
        ("anything under dedh hazaar?", [1500]),
        ("is a filling more than 10k", [10000]),
        ("around 2 thousand", [2000]),
        ("can I pay 12,000 in EMIs", [12000]),
        ("one and a half thousand", [1500]),
        ("do hazaar se kam", [2000]),
        ("ek hazaar paanch sau", [1500]),
        ("sava do hazaar", [2250]),
        ("dhai hazaar", [2500]),
        ("डेढ़ हज़ार", [1500]),
        ("पंद्रह हज़ार", [15000]),
        ("साढ़े तीन हजार", [3500]),
        ("पौने दो लाख", [175000]),
        ("लगभग ₹\u0967\u0968,\u0966\u0966\u0966", [12000]),
        ("one point two five lakh", [125000]),
        ("1.25 Cr", [12500000]),
    ],
)
def test_spoken_amounts_parse_to_rupees(heard: str, values: list[float]) -> None:
    assert [h.value for h in parse_amounts(heard)] == values


def test_the_model_is_told_an_amount_said_in_words() -> None:
    assert amounts_note("anything under dedh hazaar?") == (
        "[Amounts they said, in rupees: 'dedh hazaar' = 1500 rupees.]"
    )
    assert amounts_note("around 2 thousand") == (
        "[Amounts they said, in rupees: '2 thousand' = about 2000 rupees.]"
    )
    # A phone number, a code or a time is not an amount said with a scale: no note.
    for heard in ("98450 31726", "It's 4821", "eleven thirty", "yes please"):
        assert amounts_note(heard) is None


async def test_an_amount_split_across_streamed_chunks_is_still_said_whole() -> None:
    """A model streams tokens: "₹8," then "000", a dash and "₹18", then ",000". The rewrite waits for the
    amount to finish, and the unit's start and end pass through as they came."""
    from voqalize.sdk import SpeechChunk, SpeechEnd, SpeechStart

    async def stream() -> Any:
        yield SpeechStart()
        for piece in ["The crown is ₹8,", "000\u2013₹18", ",000, and whitening ₹1.", "5k."]:
            yield SpeechChunk(piece)
        yield SpeechEnd()

    out = [e async for e in SpokenAmounts(lambda: "en").wrap(stream())]
    assert isinstance(out[0], SpeechStart) and isinstance(out[-1], SpeechEnd)
    text = "".join(e.text for e in out if isinstance(e, SpeechChunk))
    assert text == "The crown is ₹8,000 to ₹18,000, and whitening ₹1,500."
