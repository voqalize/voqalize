"""Javier's Spanish is Latin America's, not Spain's, and he says "tú".

Uno Salud's visitors are in Chile. Every Spanish line the brain writes itself —
the greetings, nods, holding lines, the lines for a move and the lines a fill
says back — carries no word or form only Spain uses, and addresses the visitor
as "tú", never "usted" (even though some of the site's older pages do). In
Spanish the voice is handed "bidéo" for "video", and the model only ever sees
"video". What the model writes is the prompt's business: its rules are checked
here.

Run: ``cd demos && uv run pytest tests/test_unosalud_latam.py``
"""

from __future__ import annotations

import re

import pytest
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedOpenAI, input_texts, reply

from ._harness import check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.unosalud import brain as unosalud  # noqa: E402
from voqalize_demos._loaded.unosalud.cues import words  # noqa: E402

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
    "he + participle": r"\bhe (?:abierto|cerrado|rellenado|puesto|completado|marcado)\b",
    "cita previa": r"\bcita previa\b",
}
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
    assert re.search(_USTED, "¿En qué le ayudo? ¿Qué tratamiento necesita?")
    assert not re.search(_USTED, "¿En qué te ayudo? ¿Qué tratamiento necesitas?")


def _his_spanish_lines() -> list[str]:
    """Every Spanish line the brain writes itself, rather than the model."""
    lines = [
        unosalud.TOGGLE_CONFIRM["es"],
        unosalud._INTRO["es"],
        unosalud._GREETING["es"],
        *(opener["es"] for _, opener in unosalud._OPENERS),
        *(landed["es"] for landed in unosalud._LANDED.values()),
        *(ask["es"] for ask in unosalud._ASK_AGAIN.values()),
        *(line for kind in unosalud._ACK_LINES["es"].values() for line in kind),
        *unosalud._ACK_HOLD["es"],
        unosalud._ACK_SORRY["es"],
    ]
    pages = ["/", "/especialidades/ortodoncia/", "/clinicas/", "/urgencias/", "/agenda-tu-hora/"]
    lines += [unosalud.greeting(path, "es") for path in pages]
    return lines


@pytest.mark.parametrize("line", _his_spanish_lines())
def test_his_own_spanish_lines_are_latin_american_and_say_tu(line: str) -> None:
    assert spain_words(line) == [], line
    assert not re.search(_USTED, line, re.IGNORECASE), line


def test_the_greeting_says_tu() -> None:
    assert "tu guía" in unosalud._INTRO["es"]
    assert any(re.search(r"\bte\b|\btu\b", o["es"]) for _, o in unosalud._OPENERS)


@pytest.mark.parametrize(
    ("written", "for_voice"),
    [
        ("Te muestro un video del tratamiento.", "Te muestro un bidéo del tratamiento."),
        ("Un vídeo y una videollamada.", "Un bidéo y una videollamada."),
    ],
)
def test_video_is_respelled_for_the_voice_and_back(written: str, for_voice: str) -> None:
    assert unosalud.for_the_voice(written) == for_voice
    assert unosalud.from_the_voice(for_voice) == written.replace("vídeo", "video")


def test_a_cue_anchor_follows_the_voice() -> None:
    sentence = "Un video muestra cómo es el implante."
    at = " ".join(words(sentence)[:3])
    heard = " ".join(words(unosalud.for_the_voice(sentence)))
    assert heard.startswith(unosalud._anchor_for_voice(at)), (at, heard)


async def test_the_voice_says_bideo_and_the_model_reads_video() -> None:
    llm = ScriptedOpenAI(
        {
            "¿Cómo es un implante?": reply(
                "{page: /especialidades/implantes-dentales/} Hay un video que lo muestra."
            ),
            "¿Y cuánto cuesta?": reply("Desde trescientos sesenta y un mil novecientos pesos."),
        }
    )
    async with demo("unosalud", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("¿Cómo es un implante?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert "Hay un bidéo que lo muestra." in turn.text, turn.text
        await rig.driver.user_says("¿Y cuánto cuesta?")
        context = input_texts(llm.captured_inputs[-1])
        assert "Hay un video que lo muestra." in context and "bidéo" not in context, context


def test_the_prompt_asks_for_latin_american_spanish_and_tu() -> None:
    prompt = unosalud._prompt(unosalud.kb.KNOWLEDGE)
    for rule in (
        "neutral Latin American Spanish",
        '"tú", never "usted"',
        'never "vosotros"',
        'never "vídeo"',
        '"celular", never "móvil"',
        '"está bien" or "perfecto", never "vale"',
        '"¿Qué día te acomoda?", not "te viene bien"',
        "the simple past",
        '"agendar una hora"',
        '"previsión", "isapre", "Fonasa", "comuna"',
        '"cancelar" means to pay',
    ):
        assert rule in prompt, rule


def test_the_prompt_reads_phone_numbers_digit_by_digit_and_never_diagnoses() -> None:
    prompt = unosalud._prompt(unosalud.kb.KNOWLEDGE)
    assert "read digit by digit, never reshaped" in prompt
    assert "seis cero cero, siete cero siete, uno cero uno cero" in prompt
    assert "You never diagnose" in prompt
    assert "600 707 1010" in prompt
