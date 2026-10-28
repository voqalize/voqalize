"""The cue parser: cues out of the speech, each anchored to its sentence.

Run: ``cd demos && uv run pytest tests/test_enveedo_cues.py``
"""

from __future__ import annotations

from voqalize_demos.discovery import discover

discover()

from voqalize_demos._loaded.enveedo.cues import (  # noqa: E402
    MAX_CUE,
    CueParser,
    RawCue,
    words,
)


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
        "{page: /}{show: how_it_works} La plataforma parte por tu negocio. "
        "{show: how_integration} Después conecta tus herramientas."
    )
    assert "{" not in spoken and "}" not in spoken
    assert spoken == " La plataforma parte por tu negocio. Después conecta tus herramientas."
    assert [(c.kind, c.value, c.at, c.word) for c in cues] == [
        ("page", "/", "la plataforma parte", 0),
        ("show", "how_it_works", "la plataforma parte", 0),
        ("show", "how_integration", "despues conecta tus", 6),
    ]


def test_a_cue_split_across_chunks_still_parses() -> None:
    spoken, cues = _run("NIS2 está en la lista. {sh", "ow: fw_ni", "s2} Aquí está su tarj", "eta.")
    assert spoken == "NIS2 está en la lista. Aquí está su tarjeta."
    assert [(c.kind, c.value, c.at) for c in cues] == [("show", "fw_nis2", "aqui esta su")]


def test_a_cue_at_the_end_fires_when_the_voice_stops() -> None:
    spoken, cues = _run("Here is the footer. {show: footer}")
    assert spoken.strip() == "Here is the footer."
    assert [(c.kind, c.at) for c in cues] == [("show", "")]


def test_a_version_number_or_a_law_number_is_not_a_sentence_end() -> None:
    spoken, cues = _run("NIST CSF v2.0 and law 21.719 are listed. {show: fw_nist_csf} Look.")
    assert spoken == "NIST CSF v2.0 and law 21.719 are listed. Look."
    assert [(c.value, c.at) for c in cues] == [("fw_nist_csf", "look")]


def test_braces_that_are_not_cues_are_not_spoken_and_a_stray_one_is_dropped() -> None:
    spoken, cues = _run("Hola {mood: happy} a todas.")
    assert spoken == "Hola a todas." and cues == []
    long = "palabra " * (MAX_CUE // 4)
    spoken, cues = _run("Abre { " + long, "y sigue.")
    assert "{" not in spoken and spoken.startswith("Abre ") and cues == []


def test_each_sentence_is_offered_for_the_moves_it_did_not_bring() -> None:
    seen: list[tuple[str, int, tuple[tuple[str, str], ...]]] = []

    def auto(
        sentence: str, index: int, placed: tuple[tuple[str, str], ...]
    ) -> list[tuple[str, str]]:
        seen.append((sentence, index, placed))
        return [("show", "control_performance")] if "Control Performance" in sentence else []

    p = CueParser(auto)  # type: ignore[arg-type]
    cues: list[RawCue] = []
    for chunk in (
        "{page: /security-performance-os} Hello. Then comes Control",
        " Performance. Shall I go on?",
    ):
        cues += p.feed(chunk)[1]
    cues += p.flush()[1]
    assert seen == [
        ("Hello.", 0, (("page", "/security-performance-os"),)),
        ("Then comes Control Performance.", 1, ()),
        ("Shall I go on?", 2, ()),
    ]
    assert [(c.kind, c.value, c.at, c.word) for c in cues] == [
        ("page", "/security-performance-os", "hello", 0),
        ("show", "control_performance", "then comes control", 1),
    ]


def test_anchors_fold_accents_as_the_page_does() -> None:
    assert words("Está en Miami, ¿sí?") == ["esta", "en", "miami", "si"]
    spoken, cues = _run("{show: faq_start} Cómo empezar está aquí.")
    assert spoken == " Cómo empezar está aquí."
    assert [(c.kind, c.value, c.at) for c in cues] == [("show", "faq_start", "como empezar esta")]
