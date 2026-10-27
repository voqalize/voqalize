"""The cue parser and the catalogue it points into: cues out of the speech, each
anchored to its sentence, and every key a cue can name resolved by the brain to
a place the extension knows.

Run: ``cd demos && uv run pytest tests/test_unosalud_cues.py``
"""

from __future__ import annotations

from voqalize_demos.discovery import discover

discover()

from voqalize_demos._loaded.unosalud import brain as unosalud  # noqa: E402
from voqalize_demos._loaded.unosalud import knowledge as kb  # noqa: E402
from voqalize_demos._loaded.unosalud.cues import MAX_CUE, CueParser, RawCue, words  # noqa: E402


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
        "{page: /especialidades/ortodoncia/}{show: ortodoncia_precios} Hay tres tipos. "
        "{show: ortodoncia_tab_metalicos} Los metálicos son los más conocidos."
    )
    assert "{" not in spoken and "}" not in spoken
    assert spoken == " Hay tres tipos. Los metálicos son los más conocidos."
    assert [(c.kind, c.value, c.at, c.word) for c in cues] == [
        ("page", "/especialidades/ortodoncia/", "hay tres tipos", 0),
        ("show", "ortodoncia_precios", "hay tres tipos", 0),
        ("show", "ortodoncia_tab_metalicos", "los metalicos son", 3),
    ]


def test_a_cue_split_across_chunks_still_parses() -> None:
    spoken, cues = _run(
        "Los implantes parten bajo. {sh",
        "ow: implantes_pre",
        "cios} Trescientos sesenta y",
        " uno mil.",
    )
    assert spoken == "Los implantes parten bajo. Trescientos sesenta y uno mil."
    assert [(c.value, c.at) for c in cues] == [("implantes_precios", "trescientos sesenta y")]


def test_a_cue_at_the_end_fires_when_the_voice_stops() -> None:
    spoken, cues = _run("Aquí está la pregunta. {faq: faq_urgencias}")
    assert spoken.strip() == "Aquí está la pregunta."
    assert [(c.kind, c.at) for c in cues] == [("faq", "")]


def test_braces_that_are_not_cues_are_not_spoken_and_a_stray_one_is_dropped() -> None:
    spoken, cues = _run("Hola {mood: happy} otra vez.")
    assert spoken == "Hola otra vez." and cues == []
    long = "palabra " * (MAX_CUE // 4)
    spoken, cues = _run("Abre { " + long, "y sigue.")
    assert "{" not in spoken and spoken.startswith("Abre ") and cues == []


def test_anchors_are_folded_like_the_page_folds_what_it_hears() -> None:
    assert words("Está en la sección Ortodoncia, ¿sí?") == [
        "esta",
        "en",
        "la",
        "seccion",
        "ortodoncia",
        "si",
    ]
    assert words("Ñuñoa y Maipú") == ["nunoa", "y", "maipu"]


def test_every_place_the_prompt_lists_is_in_the_catalogue() -> None:
    """The prompt names places by key; each one is a place the extension can find."""
    prompt = unosalud._prompt(kb.KNOWLEDGE).split("# Pages and places")[1]
    listed = {
        line.strip()[2:].split(":")[0]
        for line in prompt.splitlines()
        if line.startswith("  - ") and ":" in line and "…" not in line
    }
    assert listed, "the prompt lists no places"
    missing = sorted(k for k in listed if k not in kb.KNOWLEDGE.anchors)
    assert missing == [], missing


def test_every_page_the_backstop_names_is_a_page_of_the_site() -> None:
    k = kb.KNOWLEDGE
    for _, path in unosalud._ASKED_PAGES:
        assert k.page(path) is not None, path


def test_what_the_visitor_asked_about_names_its_page() -> None:
    cases = {
        "¿Cuánto cuestan los frenillos?": "/especialidades/ortodoncia/",
        "Me quiero poner un implante": "/especialidades/implantes-dentales/",
        "Me sangran las encías": "/especialidades/periodoncia/",
        "Es para mi hijo de seis años": "/especialidades/odontopediatria/",
        "¿Tienen alguna promoción?": "/promociones/",
        "Tengo isapre Colmena": "/convenio/",
        "¿Dónde quedan las clínicas?": "/clinicas/",
        "Tengo una urgencia, me duele mucho": "/urgencias/",
        "How much is teeth whitening?": "/especialidades/blanqueamiento-dental/",
        "¿Puedes hablar en inglés?": None,
    }
    for said, path in cases.items():
        assert unosalud.asked_page(said) == path, said
