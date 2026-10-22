"""The cue parser: cues out of the speech, each anchored to its sentence.

Run: ``cd demos && uv run pytest tests/test_saintgeorge_cues.py``
"""

from __future__ import annotations

from voqalize_demos.discovery import discover

discover()

from voqalize_demos._loaded.saintgeorge.cues import MAX_CUE, CueParser, RawCue, words  # noqa: E402


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
        "{page: /}{show: Nuestra comunidad} Somos cuatro unidades. "
        "{show: Nuestros valores} Siete valores guían lo que hacemos."
    )
    assert "{" not in spoken and "}" not in spoken
    assert spoken == " Somos cuatro unidades. Siete valores guían lo que hacemos."
    assert [(c.kind, c.value, c.at, c.word) for c in cues] == [
        ("page", "/", "somos cuatro unidades", 0),
        ("show", "Nuestra comunidad", "somos cuatro unidades", 0),
        ("show", "Nuestros valores", "siete valores guian", 3),
    ]


def test_a_cue_split_across_chunks_still_parses() -> None:
    spoken, cues = _run(
        "Kínder es el segundo año. {fa", "q: KIN", "DER} Aquí están sus cur", "sos."
    )
    assert spoken == "Kínder es el segundo año. Aquí están sus cursos."
    assert [(c.kind, c.value, c.at) for c in cues] == [("faq", "KINDER", "aqui estan sus")]


def test_a_cue_at_the_end_fires_when_the_voice_stops() -> None:
    spoken, cues = _run("Here is the sports team. {faq: CONOCE AL EQUIPO}")
    assert spoken.strip() == "Here is the sports team."
    assert [(c.kind, c.at) for c in cues] == [("faq", "")]


def test_a_value_with_a_decimal_comma_or_point_is_not_a_sentence_end() -> None:
    spoken, cues = _run("La matrícula es UF 13.5 al año. {show: Valores referenciales} Mira.")
    assert spoken == "La matrícula es UF 13.5 al año. Mira."
    assert [(c.value, c.at) for c in cues] == [("Valores referenciales", "mira")]


def test_braces_that_are_not_cues_are_not_spoken_and_a_stray_one_is_dropped() -> None:
    spoken, cues = _run("Hola {mood: happy} a todos.")
    assert spoken == "Hola a todos." and cues == []
    long = "palabra " * (MAX_CUE // 4)
    spoken, cues = _run("Abre { " + long, "y sigue.")
    assert "{" not in spoken and spoken.startswith("Abre ") and cues == []


def test_each_sentence_is_offered_for_the_moves_it_did_not_bring() -> None:
    seen: list[tuple[str, int, tuple[tuple[str, str], ...]]] = []

    def auto(
        sentence: str, index: int, placed: tuple[tuple[str, str], ...]
    ) -> list[tuple[str, str]]:
        seen.append((sentence, index, placed))
        return [("show", "Nuestros valores")] if "valores" in sentence else []

    p = CueParser(auto)  # type: ignore[arg-type]
    cues: list[RawCue] = []
    for chunk in ("{page: /} Hola. Tenemos siete va", "lores. ¿Te cuento más?"):
        cues += p.feed(chunk)[1]
    cues += p.flush()[1]
    assert seen == [
        ("Hola.", 0, (("page", "/"),)),
        ("Tenemos siete valores.", 1, ()),
        ("¿Te cuento más?", 2, ()),
    ]
    assert [(c.kind, c.value, c.at, c.word) for c in cues] == [
        ("page", "/", "hola", 0),
        ("show", "Nuestros valores", "tenemos siete valores", 1),
    ]


def test_anchors_fold_accents_and_ordinal_marks_as_the_page_does() -> None:
    """The page folds what it hears with NFD and drops the ordinal marks; the
    brain's NFKD would make "º" an "o", and the anchor would never be heard."""
    assert words("Está en 1º BÁSICO, ¿sí?") == ["esta", "en", "1", "basico", "si"]
    assert words("Él cursa 9° y su hermana 4ª") == ["el", "cursa", "9", "y", "su", "hermana", "4"]
    spoken, cues = _run("{faq: 1º BÁSICO} Así es primero básico.")
    assert spoken == " Así es primero básico."
    assert [(c.kind, c.value, c.at) for c in cues] == [("faq", "1º BÁSICO", "asi es primero")]
