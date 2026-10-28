"""Javier's Spanish is Latin America's, not Spain's, and he says "tú".

Colegio Everest's visitors are families in Chile. The accent is the speech
tier's reference clip; the words are this brain's. Every Spanish line the brain
writes itself — the greetings and the lines for a page move — carries no word or form only Spain uses and addresses the visitor as
"tú", never "usted". In Spanish the voice is handed "bidéo" for "video", "u
efe" for "UF", amounts and the grades in words; the model only ever sees
"video" and "UF".

What the model writes is a property of the prompt and the model; the prompt's
rules are checked here, and the live check is SendPotion's opt-in eval
(``test_sendpotion_latam.py``), whose rules this prompt carries.

Run: ``cd demos && uv run pytest tests/test_colegioeverest_latam.py``
"""

from __future__ import annotations

import re

import pytest
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedOpenAI, input_texts, reply

from ._harness import check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.colegioeverest import brain as fg  # noqa: E402
from voqalize_demos._loaded.colegioeverest.cues import words  # noqa: E402

#: Words and forms only Spain uses, as they would show in what he says.
_SPAIN = {
    "vídeo": r"\bvídeos?\b",
    "vale": r"\bvale\b",
    "vosotros": r"\bvosotr[oa]s\b",
    "os": r"\bos\b",
    "vosotros verb (-áis/-éis)": r"\b\w{2,}(?:áis|éis)\b",
    "ordenador": r"\bordenador(?:es)?\b",
    "móvil": r"\bmóvil(?:es)?\b",
    "coger": r"\bco(?:ger|ge|jo|gemos)\b",
    "rellenar": r"\brellen\w*\b",
    "te viene bien": r"\bte viene bien\b",
    "perdona": r"\bperdona\b",
    "enseñar (show)": r"\bte (?:lo |la )?enseñ\w*|\benseñárte\w*",
    "he + participle": r"\bhe (?:abierto|cerrado|rellenado|puesto|completado|enviado|anotado)\b",
}
#: The visitor addressed as "usted": Javier says "tú".
_USTED = (
    r"\busted(?:es)?\b|\b(?:le|lo) (?:ayudo|muestro|abro|cuento)\b"
    r"|\b(?:necesita|quiere|tiene|busca)\b\?"
)


def spain_words(text: str) -> list[str]:
    return [name for name, rx in _SPAIN.items() if re.search(rx, text, re.IGNORECASE)]


def test_the_checks_catch_spain_and_usted() -> None:
    assert spain_words("Vale, te lo enseño en el vídeo. Ya lo he rellenado.") == [
        "vídeo",
        "vale",
        "rellenar",
        "enseñar (show)",
        "he + participle",
    ]
    assert re.search(_USTED, "¿En qué le ayudo? ¿Qué nivel busca?")
    assert not re.search(_USTED, "¿En qué te ayudo? ¿Qué nivel buscas?")


def _his_spanish_lines() -> list[str]:
    """Every Spanish line the brain writes itself, rather than the model."""
    lines = [
        fg.TOGGLE_CONFIRM["es"],
        fg._INTRO["es"],
        fg._GREETING["es"],
        *(opener["es"] for _, opener in fg._OPENERS),
        *(landed["es"] for landed in fg._LANDED.values()),
    ]
    pages = [
        "/",
        "/bienvenidos-al-proceso-de-admision-del-colegio-everest/",
        "/contacto/",
        "/nuestro-colegio/infraestructura/",
        "/tour-virtual/",
        "/nuestro-modelo-educativo/ingles-intensivo/",
        "/nuestro-modelo-educativo/ciclos/",
    ]
    return lines + [fg.greeting(path, "es") for path in pages]


@pytest.mark.parametrize("line", _his_spanish_lines())
def test_his_own_spanish_lines_are_latin_american_and_say_tu(line: str) -> None:
    assert spain_words(line) == [], line
    assert not re.search(_USTED, line, re.IGNORECASE), line


def test_the_greeting_says_tu_and_asks_for_the_child() -> None:
    assert "tu guía" in fg._INTRO["es"]
    assert "tu hijo o hija" in fg._GREETING["es"]
    assert all(re.search(r"\bte\b|\btu\b|\btus\b", o["es"], re.IGNORECASE) for _, o in fg._OPENERS)


@pytest.mark.parametrize(
    ("written", "for_voice"),
    [
        ("Te muestro un video del colegio.", "Te muestro un bidéo del colegio."),
        ("Cada nivel tiene su video.", "Cada nivel tiene su bidéo."),
        ("Un vídeo y una videollamada.", "Un bidéo y una videollamada."),
    ],
)
def test_video_is_respelled_for_the_voice_and_back(written: str, for_voice: str) -> None:
    assert fg.for_the_voice(written) == for_voice
    assert fg.from_the_voice(for_voice) == written.replace("vídeo", "video")


def test_a_cue_anchor_follows_the_voice() -> None:
    sentence = "Un video muestra el gimnasio nuevo."
    at = " ".join(words(sentence)[:3])
    heard = " ".join(words(fg.for_the_voice(sentence)))
    assert heard.startswith(fg._anchor_for_voice(at)), (at, heard)


async def test_the_voice_says_bideo_and_the_model_reads_video() -> None:
    llm = ScriptedOpenAI(
        {
            "¿Tienen algo de la historia?": reply(
                "{page: /nuestro-colegio/historia/} Hay un video de los treinta años."
            ),
            "¿Y cuándo se fundó?": reply("En mil novecientos noventa y cinco."),
        }
    )
    async with demo("colegioeverest", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("¿Tienen algo de la historia?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert "Hay un bidéo de los treinta años." in turn.text, turn.text
        await rig.driver.user_says("¿Y cuándo se fundó?")
        context = input_texts(llm.captured_inputs[-1])
        assert "Hay un video de los treinta años." in context and "bidéo" not in context, context


def test_the_prompt_asks_for_latin_american_spanish_and_tu() -> None:
    prompt = fg._prompt(fg.kb.KNOWLEDGE)
    for rule in (
        "neutral Latin American Spanish",
        'Address one visitor as "tú", never "usted"',
        'never "vosotros"',
        'never "vídeo"',
        '"celular", never "móvil"',
        '"está bien" or "perfecto", never "vale"',
        '"¿Qué día te queda bien?", not "te viene bien"',
        "the simple past",
        '"apoderado" for a parent at school',
    ):
        assert rule in prompt, rule


@pytest.mark.parametrize(
    ("written", "for_voice"),
    [
        ("Son 193,34 UF al año.", "Son ciento noventa y tres coma treinta y cuatro u efe al año."),
        (
            "La matrícula es 15,996 UF.",
            "La matrícula es quince coma novecientos noventa y seis u efe.",
        ),
        ("El proceso cuesta $45.000.", "El proceso cuesta cuarenta y cinco mil pesos."),
        (
            "Hay vacantes en I medio y en IV medio.",
            "Hay vacantes en primero medio y en cuarto medio.",
        ),
        ("En 3° básico queda una.", "En tercero básico queda una."),
    ],
)
def test_amounts_uf_and_grades_are_said_in_words(written: str, for_voice: str) -> None:
    assert fg.for_the_voice(written) == for_voice


def test_uf_comes_back_as_written() -> None:
    assert fg.from_the_voice("Son diez u efe.") == "Son diez UF."


def test_english_amounts_are_said_in_words() -> None:
    assert fg.for_the_voice_en("It is 102,58 UF.") == "It is one hundred two point five eight UF."
