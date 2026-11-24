"""Paynora's amounts in speech, both ways (FEEDBACK X8): the formatter that turns what
both brains write into text the voice reads right, and the parser that turns what the
recogniser heard into rupees and counts. Each demo has its own copy
(``payroll_site/backend/spoken.py``, ``payroll_app/backend/spoken.py``); the shared
cases run against both, so the copies cannot drift apart.

Run: ``cd demos && uv run pytest tests/test_payroll_spoken.py``
"""

from __future__ import annotations

from types import ModuleType
from typing import Any

import pytest
from voqalize_demos.discovery import discover

discover()

from voqalize_demos._loaded.payroll_app import spoken as app_spoken  # noqa: E402
from voqalize_demos._loaded.payroll_site import spoken as site_spoken  # noqa: E402

BOTH = pytest.mark.parametrize("spoken", [site_spoken, app_spoken], ids=["site", "app"])


@BOTH
@pytest.mark.parametrize(
    ("written", "lang", "said"),
    [
        # The tax page's worked example, as a model writes it from the title.
        (
            "For a ₹16.8 lakh CTC in Mumbai, the new regime costs less.",
            "en",
            "For a sixteen point eight lakh rupees CTC in Mumbai, the new regime costs less.",
        ),
        ("A CTC of ₹7.25 lakh.", "en", "A CTC of seven point two five lakh rupees."),
        ("Surcharge applies above ₹50 lakh.", "en", "Surcharge applies above fifty lakh rupees."),
        (
            "Salaries of ₹6\u201312 lakh a year.",
            "en",
            "Salaries of six to twelve lakh rupees a year.",
        ),
        # Plain amounts, as the tools write them, are left to the TTS (it reads them right).
        ("Net pay ₹1,26,374, TDS ₹6,664, minimum ₹3,000 a month.", "en", None),
        ("Reimbursements ₹4,580 against a bill of ₹4,850.", "en", None),
        ("Basic 40% of CTC, HRA 50% of basic.", "en", None),
        ("FY 2025-26, employee BB-1042.", "en", None),
        # Hindi: Devanagari scale with ₹ (सवा / डेढ़ / ढाई), else whole rupees.
        ("CTC ₹16.8 lakh है।", "hi", "CTC ₹16,80,000 है।"),
        ("CTC ₹7.5 lakh है।", "hi", "CTC ₹7.5 लाख है।"),
        ("साल का tax ₹1.25 लाख बनता है।", "hi", None),
        ("सालाना 12.5 लाख रुपये।", "hi", "सालाना ₹12.5 लाख।"),
        ("नेट पे ₹1,26,374 है।", "hi", None),
    ],
)
def test_what_both_brains_write_is_what_the_voice_reads_right(
    spoken: ModuleType, written: str, lang: str, said: str | None
) -> None:
    assert spoken.speak_text(written, lang) == (written if said is None else said)


@BOTH
@pytest.mark.parametrize(
    ("heard", "values"),
    [
        ("Her CTC is 7.2 lakh.", [720000]),
        ("seven point two lakh", [720000]),
        ("around twelve and a half lakhs per annum", [1250000]),
        ("16.8 lakh", [1680000]),
        ("dedh lakh", [150000]),
        ("साढ़े सात लाख", [750000]),
        ("सात लाख बीस हज़ार", [720000]),
        ("LTA teen hazaar for G5 and 5k for G6", [3000, 5000]),
        ("₹3,000 a month", [3000]),
        ("we have dedh hazaar people", [1500]),
        ("about two hundred and fifty employees", [250]),
        ("one and a half thousand", [1500]),
        ("लगभग ढाई सौ लोग", [250]),
        ("१२० कर्मचारी", [120]),
    ],
)
def test_spoken_numbers_parse(spoken: ModuleType, heard: str, values: list[float]) -> None:
    assert [h.value for h in spoken.parse_amounts(heard)] == values


@BOTH
async def test_an_amount_split_across_streamed_chunks_is_said_whole(spoken: ModuleType) -> None:
    from voqalize.sdk import SpeechChunk, SpeechEnd, SpeechStart

    async def stream() -> Any:
        yield SpeechStart()
        for piece in ["A ₹16.", "8 la", "kh CTC, net pay ", "₹1,26,374 a month."]:
            yield SpeechChunk(piece)
        yield SpeechEnd()

    out = [e async for e in spoken.SpokenAmounts(lambda: "en").wrap(stream())]
    assert isinstance(out[0], SpeechStart) and isinstance(out[-1], SpeechEnd)
    text = "".join(e.text for e in out if isinstance(e, SpeechChunk))
    assert text == "A sixteen point eight lakh rupees CTC, net pay ₹1,26,374 a month."


def test_a_headcount_that_lost_its_scale_is_confirmed_back() -> None:
    dropped = site_spoken.dropped_scale
    why = dropped(15, ["We have about one and a half thousand people."])
    assert why is not None and why.startswith("Not done") and "1,500 employees, right?" in why
    assert dropped(2, ["do hazaar log hain"]) is not None
    assert dropped(1500, ["one and a half thousand"]) is None
    assert dropped(56, ["We have 56 people."]) is None
    # Rupees said beside the count are not a headcount.
    assert dropped(40, ["40 people, about 1.5 lakh a month in salaries"]) is None
    assert (
        site_spoken.numbers_note("dedh hazaar log") == "[Numbers they said: 'dedh hazaar' = 1500.]"
    )
    assert site_spoken.numbers_note("56 people") is None


def test_an_implausible_ctc_or_lta_is_confirmed_back_never_used() -> None:
    why = app_spoken.implausible({"annual_ctc": 72}, ["Her CTC is 7.2 lakh."])
    assert why is not None and why.startswith("Not done")
    assert "₹7,20,000" in why and "₹7.2 lakh, right?" in why
    assert app_spoken.implausible({"annual_ctc": 720000}, ["7.2 lakh"]) is None
    assert app_spoken.implausible({"lta_g5": 3}, ["three thousand"]) is not None
    assert app_spoken.implausible({"lta_g5": 3000}, ["three thousand"]) is None
    note = app_spoken.amounts_note("around 7.2 lakh")
    assert note == "[Amounts she said, in rupees: '7.2 lakh' = about 720000.]"


@pytest.mark.parametrize(
    ("field", "value", "digits"),
    [
        ("lta_g5", "three thousand", "3000"),
        ("lta_g5", "3k", "3000"),
        ("lta_g6_up", "₹5,000", "5000"),
        ("basic_pct", "forty five percent", "45"),
        ("el_per_year", "eighteen", "18"),
        ("lta_g5", "3000", "3000"),
        ("pf_rule", "12% of basic up to ₹15,000", "12% of basic up to ₹15,000"),
    ],
)
def test_setup_numbers_said_in_words_go_in_as_digits(field: str, value: str, digits: str) -> None:
    assert app_spoken.setup_number(field, value) == digits
