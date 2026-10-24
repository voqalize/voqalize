"""The cue parser: cues out of the speech, each anchored to its sentence.

Run: ``cd demos && uv run pytest tests/test_figurella_cues.py``
"""

from __future__ import annotations

from voqalize_demos.discovery import discover

discover()

from voqalize_demos._loaded.figurella.cues import MAX_CUE, CueParser, RawCue, words  # noqa: E402


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
        "{page: /metodo-figurella/}{show: paso_1} Cada sesión tiene tres pasos. "
        "{show: paso_2} Después viene un baño de oxígeno."
    )
    assert "{" not in spoken and "}" not in spoken
    assert spoken == " Cada sesión tiene tres pasos. Después viene un baño de oxígeno."
    assert [(c.kind, c.value, c.at, c.word) for c in cues] == [
        ("page", "/metodo-figurella/", "cada sesion tiene", 0),
        ("show", "paso_1", "cada sesion tiene", 0),
        ("show", "paso_2", "despues viene un", 5),
    ]


def test_a_cue_split_across_chunks_still_parses() -> None:
    spoken, cues = _run(
        "No hay un precio fijo. {fa", "q: faq_pre", "cio} Aquí está la respues", "ta."
    )
    assert spoken == "No hay un precio fijo. Aquí está la respuesta."
    assert [(c.kind, c.value, c.at) for c in cues] == [("faq", "faq_precio", "aqui esta la")]


def test_a_cue_at_the_end_fires_when_the_voice_stops() -> None:
    spoken, cues = _run("Here are the branches. {show: sucursales}")
    assert spoken.strip() == "Here are the branches."
    assert [(c.kind, c.at) for c in cues] == [("show", "")]


def test_a_number_with_a_decimal_comma_or_point_is_not_a_sentence_end() -> None:
    spoken, cues = _run("Treinta minutos son 1.5 horas de gimnasio. {show: feature_optimiza} Mira.")
    assert spoken == "Treinta minutos son 1.5 horas de gimnasio. Mira."
    assert [(c.value, c.at) for c in cues] == [("feature_optimiza", "mira")]


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
        return [("show", "paso_3")] if "presoterapia" in sentence else []

    p = CueParser(auto)  # type: ignore[arg-type]
    cues: list[RawCue] = []
    for chunk in ("{page: /metodo-figurella/} Hola. Cierras con preso", "terapia. ¿Te cuento más?"):
        cues += p.feed(chunk)[1]
    cues += p.flush()[1]
    assert seen == [
        ("Hola.", 0, (("page", "/metodo-figurella/"),)),
        ("Cierras con presoterapia.", 1, ()),
        ("¿Te cuento más?", 2, ()),
    ]
    assert [(c.kind, c.value, c.at, c.word) for c in cues] == [
        ("page", "/metodo-figurella/", "hola", 0),
        ("show", "paso_3", "cierras con presoterapia", 1),
    ]


def test_anchors_fold_accents_as_the_page_does() -> None:
    assert words("Está en Huérfanos, ¿sí?") == ["esta", "en", "huerfanos", "si"]
    spoken, cues = _run("{show: sucursal_colon} Colón está en Las Condes.")
    assert spoken == " Colón está en Las Condes."
    assert [(c.kind, c.value, c.at) for c in cues] == [("show", "sucursal_colon", "colon esta en")]
