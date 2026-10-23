"""The cue parser: cues out of the speech, each anchored to its sentence.

Run: ``cd demos && uv run pytest tests/test_cannonhome_cues.py``
"""

from __future__ import annotations

from voqalize_demos.discovery import discover

discover()

from voqalize_demos._loaded.cannonhome.cues import MAX_CUE, CueParser, RawCue  # noqa: E402


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


def test_each_sentence_is_offered_for_the_moves_it_did_not_bring() -> None:
    seen: list[tuple[str, int, tuple[tuple[str, str], ...]]] = []

    def auto(
        sentence: str, index: int, placed: tuple[tuple[str, str], ...]
    ) -> list[tuple[str, str]]:
        seen.append((sentence, index, placed))
        return [("show", "Re-engage dormant leads")] if "dormant" in sentence else []

    p = CueParser(auto)  # type: ignore[arg-type]
    cues: list[RawCue] = []
    for chunk in ("{page: /sales} Hi. Reps wake up dor", "mant leads, too. Want pricing?"):
        cues += p.feed(chunk)[1]
    cues += p.flush()[1]
    assert seen == [
        ("Hi.", 0, (("page", "/sales"),)),
        ("Reps wake up dormant leads, too.", 1, ()),
        ("Want pricing?", 2, ()),
    ]
    # The model's page cue, on a sentence too short to wait out: anchored to
    # its own word, not the next sentence's. The added cue, to its sentence.
    assert [(c.kind, c.value, c.at, c.word) for c in cues] == [
        ("page", "/sales", "hi", 0),
        ("show", "Re-engage dormant leads", "reps wake up", 1),
    ]


def test_anchors_are_folded_like_the_page_folds_what_it_hears() -> None:
    """The site and half his replies are Spanish: "Está" and "está" are one
    word on both sides, or the page never finds the sentence and falls back to
    the clock."""
    from voqalize_demos._loaded.cannonhome.cues import words

    assert words("Está en la sección Música, ¿sí?") == [
        "esta",
        "en",
        "la",
        "seccion",
        "musica",
        "si",
    ]
    assert words("Ñuñoa y Maipú") == ["nunoa", "y", "maipu"]
    spoken, cues = _run("{show: Exámenes de Resonancia} Así se agenda tu exámen.")
    assert spoken == " Así se agenda tu exámen."
    assert [(c.kind, c.value, c.at) for c in cues] == [
        ("show", "Exámenes de Resonancia", "asi se agenda")
    ]
