"""The cue parser: cues out of the speech, each anchored to its sentence.

Run: ``cd demos && uv run pytest tests/test_sendpotion_cues.py``
"""

from __future__ import annotations

from voqalize_demos.discovery import discover

discover()

from voqalize_demos._loaded.sendpotion.cues import MAX_CUE, CueParser, RawCue  # noqa: E402


def _run(*chunks: str) -> tuple[str, list[RawCue]]:
    p = CueParser()
    spoken = ""
    cues: list[RawCue] = []
    for c in chunks:
        text, got = p.feed(c)
        spoken += text
        cues += got
    text, got = p.flush()
    return spoken + text, cues + got


def test_cues_leave_the_speech_and_anchor_to_their_sentence() -> None:
    spoken, cues = _run(
        "{page: /}{show: How Potion works} It takes three steps. "
        "{show: Train video AI} First, you train the AI on you."
    )
    assert "{" not in spoken and "}" not in spoken
    assert spoken == " It takes three steps. First, you train the AI on you."
    assert [(c.kind, c.value, c.at, c.word) for c in cues] == [
        ("page", "/", "it takes three", 0),
        ("show", "How Potion works", "it takes three", 0),
        ("show", "Train video AI", "first you train", 4),
    ]


def test_a_cue_split_across_chunks_still_parses() -> None:
    spoken, cues = _run(
        "Plans start low. {sh", "ow: Pricing pl", "ans} Thirty-nine dol", "lars a month."
    )
    assert spoken == "Plans start low. Thirty-nine dollars a month."
    assert [(c.value, c.at) for c in cues] == [("Pricing plans", "thirty nine dollars")]


def test_a_cue_at_the_end_fires_when_the_voice_stops() -> None:
    spoken, cues = _run("Here is the FAQ. {faq: Can I cancel anytime?}")
    assert spoken.strip() == "Here is the FAQ."
    assert [(c.kind, c.at) for c in cues] == [("faq", "")]


def test_braces_that_are_not_cues_are_not_spoken_and_a_stray_one_is_dropped() -> None:
    spoken, cues = _run("Hello {mood: happy} there.")
    assert spoken == "Hello there." and cues == []
    long = "word " * (MAX_CUE // 4)
    spoken, cues = _run("Open { " + long, "and on.")
    assert "{" not in spoken and spoken.startswith("Open ") and cues == []
