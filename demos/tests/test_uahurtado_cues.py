"""The cue parser, as the UAH guide writes cues: out of the speech, each
anchored to its sentence, with pages on three hosts and prices in the text.

Run: ``cd demos && uv run pytest tests/test_uahurtado_cues.py``
"""

from __future__ import annotations

from voqalize_demos.discovery import discover

discover()

from voqalize_demos._loaded.uahurtado.cues import (  # noqa: E402
    MAX_CUE,
    CueKind,
    CueParser,
    RawCue,
    words,
)


def _run(*chunks: str, auto: object = None) -> tuple[str, list[RawCue]]:
    p = CueParser(auto)  # type: ignore[arg-type]
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
        "{page: /carreras/psicologia/} Psicología dura diez semestres. "
        "{show: Requisitos y Aranceles} Aquí ves lo que pide."
    )
    assert "{" not in spoken and "}" not in spoken
    assert spoken == " Psicología dura diez semestres. Aquí ves lo que pide."
    assert [(c.kind, c.value, c.at, c.word) for c in cues] == [
        ("page", "/carreras/psicologia/", "psicologia dura diez", 0),
        ("show", "Requisitos y Aranceles", "aqui ves lo", 4),
    ]


def test_a_page_on_another_host_keeps_its_host() -> None:
    _, cues = _run(
        "{page: www.uahurtado.cl/la-universidad/campus/campus-patrimonial/} "
        "La Casa Central está en el centro."
    )
    assert cues[0].value == "www.uahurtado.cl/la-universidad/campus/campus-patrimonial/"
    assert cues[0].at == "la casa central"


def test_a_price_with_points_does_not_end_a_sentence() -> None:
    spoken, cues = _run(
        "{show: Aranceles} El arancel es $7.167.421 al año. {faq: ¿Qué es la gratuidad?} Y hay gratuidad."
    )
    assert "$7.167.421" in spoken
    assert [(c.kind, c.at) for c in cues] == [
        ("show", "el arancel es"),
        ("faq", "y hay gratuidad"),
    ]


def test_a_cue_split_across_chunks_still_parses() -> None:
    spoken, cues = _run(
        "Hay becas. {sh", "ow: Excelencia acad", "émica} La beca cubre", " el arancel."
    )
    assert spoken == "Hay becas. La beca cubre el arancel."
    assert [(c.value, c.at) for c in cues] == [("Excelencia académica", "la beca cubre")]


def test_a_cue_at_the_end_fires_when_the_voice_stops() -> None:
    spoken, cues = _run("Aquí está la respuesta. {faq: ¿Quiénes pueden acceder?}")
    assert spoken.strip() == "Aquí está la respuesta."
    assert [(c.kind, c.at) for c in cues] == [("faq", "")]


def test_braces_that_are_not_cues_are_not_spoken_and_a_stray_one_is_dropped() -> None:
    spoken, cues = _run("Hola {mood: happy} cómo estás.")
    assert spoken == "Hola cómo estás." and cues == []
    long = "palabra " * (MAX_CUE // 4)
    spoken, cues = _run("Abre { " + long, "y sigue.")
    assert "{" not in spoken and spoken.startswith("Abre ") and cues == []


def test_auto_is_offered_each_sentence_with_the_kinds_it_already_has() -> None:
    seen: list[tuple[str, int, tuple[tuple[CueKind, str], ...]]] = []

    def auto(
        sentence: str, index: int, placed: tuple[tuple[CueKind, str], ...]
    ) -> list[tuple[CueKind, str]]:
        seen.append((sentence, index, placed))
        return [("show", "Descripción")] if index == 1 else []

    _, cues = _run(
        "{page: /carreras/derecho/} Derecho dura cinco años. Forma abogados con mirada social.",
        auto=auto,
    )
    assert [s[1] for s in seen] == [0, 1]
    assert seen[0][2] == (("page", "/carreras/derecho/"),)
    assert seen[1][2] == ()
    assert ("show", "Descripción", "forma abogados con") in [(c.kind, c.value, c.at) for c in cues]


def test_anchors_fold_like_the_page_folds() -> None:
    assert words("Está en Matrícula, ¿sí?") == ["esta", "en", "matricula", "si"]
