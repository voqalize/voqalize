"""The cue parser on ssilva: cues out of the speech, each anchored to its sentence.

Run: ``cd demos && uv run pytest tests/test_ssilva_cues.py``
"""

from __future__ import annotations

from voqalize_demos.discovery import discover

discover()

from voqalize_demos._loaded.ssilva.cues import MAX_CUE, CueParser, RawCue  # noqa: E402


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


def test_page_show_and_plan_leave_the_speech_and_anchor_to_their_sentence() -> None:
    spoken, cues = _run(
        "{page: /estocolmo/}{show: galería} Aquí ves las fotos. "
        "{plan: 2D | 3B} Este tiene dos dormitorios."
    )
    assert spoken == " Aquí ves las fotos. Este tiene dos dormitorios."
    assert [(c.kind, c.value, c.at, c.word) for c in cues] == [
        ("page", "/estocolmo/", "aqui ves las", 0),
        ("show", "galería", "aqui ves las", 0),
        ("plan", "2D | 3B", "este tiene dos", 4),
    ]


def test_a_plan_cue_split_across_chunks_still_parses() -> None:
    spoken, cues = _run("Mira este. {pl", "an: 3D | 2B + ES", "TAR} Tiene un estar ", "extra.")
    assert spoken == "Mira este. Tiene un estar extra."
    assert [(c.kind, c.value, c.at) for c in cues] == [
        ("plan", "3D | 2B + ESTAR", "tiene un estar")
    ]


def test_a_number_with_a_point_does_not_end_a_sentence() -> None:
    seen: list[str] = []

    def auto(
        sentence: str, index: int, placed: tuple[tuple[str, str], ...]
    ) -> list[tuple[str, str]]:
        seen.append(sentence)
        return []

    p = CueParser(auto)  # type: ignore[arg-type]
    p.feed("Parte en 13.976 UF. Es grande.")
    p.flush()
    assert seen == ["Parte en 13.976 UF.", "Es grande."]


def test_the_old_faq_cue_is_no_cue_here() -> None:
    spoken, cues = _run("Hola {faq: algo} aquí.")
    assert spoken == "Hola aquí." and cues == []


def test_a_cue_at_the_end_fires_when_the_voice_stops() -> None:
    spoken, cues = _run("Aquí está el formulario. {show: formulario}")
    assert spoken.strip() == "Aquí está el formulario."
    assert [(c.kind, c.at) for c in cues] == [("show", "")]


def test_a_stray_brace_is_dropped() -> None:
    long = "palabra " * (MAX_CUE // 4)
    spoken, cues = _run("Abro { " + long, "y sigo.")
    assert "{" not in spoken and spoken.startswith("Abro ") and cues == []


def test_each_sentence_is_offered_for_the_moves_it_did_not_bring() -> None:
    seen: list[tuple[str, int, tuple[tuple[str, str], ...]]] = []

    def auto(
        sentence: str, index: int, placed: tuple[tuple[str, str], ...]
    ) -> list[tuple[str, str]]:
        seen.append((sentence, index, placed))
        return [("show", "amenidades")] if "piscina" in sentence else []

    p = CueParser(auto)  # type: ignore[arg-type]
    cues: list[RawCue] = []
    for chunk in ("{plan: 2D | 2B} Hola. Tiene pisc", "ina y quincho. ¿Seguimos?"):
        cues += p.feed(chunk)[1]
    cues += p.flush()[1]
    assert seen == [
        ("Hola.", 0, (("plan", "2D | 2B"),)),
        ("Tiene piscina y quincho.", 1, ()),
        ("¿Seguimos?", 2, ()),
    ]
    assert [(c.kind, c.value, c.at, c.word) for c in cues] == [
        ("plan", "2D | 2B", "hola", 0),
        ("show", "amenidades", "tiene piscina y", 1),
    ]


def test_a_photo_cue_leaves_the_speech_and_anchors_to_its_sentence() -> None:
    spoken, cues = _run("{photo: 2} Este es el cowork. {photo: amenidades 1} Y la piscina.")
    assert spoken == " Este es el cowork. Y la piscina."
    assert [(c.kind, c.value, c.at) for c in cues] == [
        ("photo", "2", "este es el"),
        ("photo", "amenidades 1", "y la piscina"),
    ]
