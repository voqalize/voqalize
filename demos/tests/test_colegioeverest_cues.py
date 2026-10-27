"""The cue parser: cues out of the speech, each anchored to its sentence.

Run: ``cd demos && uv run pytest tests/test_colegioeverest_cues.py``
"""

from __future__ import annotations

from voqalize_demos.discovery import discover

discover()

from voqalize_demos._loaded.colegioeverest.cues import (  # noqa: E402
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
        "{page: /bienvenidos-al-proceso-de-admision-del-colegio-everest/}{show: pasos} La admisión tiene ocho pasos. "
        "{show: paso_4_visita} Después visitas el colegio."
    )
    assert "{" not in spoken and "}" not in spoken
    assert spoken == " La admisión tiene ocho pasos. Después visitas el colegio."
    assert [(c.kind, c.value, c.at, c.word) for c in cues] == [
        (
            "page",
            "/bienvenidos-al-proceso-de-admision-del-colegio-everest/",
            "la admision tiene",
            0,
        ),
        ("show", "pasos", "la admision tiene", 0),
        ("show", "paso_4_visita", "despues visitas el", 5),
    ]


def test_a_cue_split_across_chunks_still_parses() -> None:
    spoken, cues = _run(
        "Quedan cupos en Prekínder. {sh", "ow: vacan", "tes} Aquí están las vacant", "es."
    )
    assert spoken == "Quedan cupos en Prekínder. Aquí están las vacantes."
    assert [(c.kind, c.value, c.at) for c in cues] == [("show", "vacantes", "aqui estan las")]


def test_a_cue_at_the_end_fires_when_the_voice_stops() -> None:
    spoken, cues = _run("Here is the school's map. {show: pie_mapa}")
    assert spoken.strip() == "Here is the school's map."
    assert [(c.kind, c.at) for c in cues] == [("show", "")]


def test_a_number_with_a_decimal_comma_or_point_is_not_a_sentence_end() -> None:
    spoken, cues = _run("La colegiatura es de 193,34 UF en 10 cuotas. {show: valores} Mira.")
    assert spoken == "La colegiatura es de 193,34 UF en 10 cuotas. Mira."
    assert [(c.value, c.at) for c in cues] == [("valores", "mira")]


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
        return [("show", "paso_6_admission_day")] if "Admission Day" in sentence else []

    p = CueParser(auto)  # type: ignore[arg-type]
    cues: list[RawCue] = []
    for chunk in (
        "{page: /bienvenidos-al-proceso-de-admision-del-colegio-everest/} Hola. Luego viene el Admission",
        " Day. ¿Te cuento más?",
    ):
        cues += p.feed(chunk)[1]
    cues += p.flush()[1]
    assert seen == [
        ("Hola.", 0, (("page", "/bienvenidos-al-proceso-de-admision-del-colegio-everest/"),)),
        ("Luego viene el Admission Day.", 1, ()),
        ("¿Te cuento más?", 2, ()),
    ]
    assert [(c.kind, c.value, c.at, c.word) for c in cues] == [
        ("page", "/bienvenidos-al-proceso-de-admision-del-colegio-everest/", "hola", 0),
        ("show", "paso_6_admission_day", "luego viene el", 1),
    ]


def test_anchors_fold_accents_as_the_page_does() -> None:
    assert words("Está en Lo Barnechea, ¿sí?") == ["esta", "en", "lo", "barnechea", "si"]
    spoken, cues = _run("{show: fecha_prekinder} Prekínder pide cuatro años.")
    assert spoken == " Prekínder pide cuatro años."
    assert [(c.kind, c.value, c.at) for c in cues] == [
        ("show", "fecha_prekinder", "prekinder pide cuatro")
    ]
