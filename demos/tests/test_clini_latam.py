"""Javier's Spanish is Latin America's, not Spain's, and he says "tú".

CLINI's visitors are in Chile. The accent is the speech tier's reference clip;
the words are this brain's. Every Spanish line the brain writes itself — the
greetings, nods, holding lines and the lines for a page move — carries no word
or form only Spain uses, and addresses the visitor as "tú", as the site does
("Agenda tu evaluación"), never "usted". In Spanish the voice is handed "bidéo"
for "video", and the model only ever sees "video".

What the model writes is a property of the prompt and the model; the prompt's
rules are checked here, and the live check is SendPotion's opt-in eval
(``test_sendpotion_latam.py``), whose rules this prompt carries.

Run: ``cd demos && uv run pytest tests/test_clini_latam.py``
"""

from __future__ import annotations

import re

import pytest
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedOpenAI, input_texts, reply

from ._harness import check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.clini import brain as clini  # noqa: E402
from voqalize_demos._loaded.clini.cues import words  # noqa: E402

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
}
#: The visitor addressed as "usted": the site, and Javier, say "tú".
_USTED = r"\busted(?:es)?\b|\b(?:le|lo) (?:ayudo|muestro|abro|cuento)\b|\b(?:necesita|quiere|tiene|busca)\b\?"


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
    assert re.search(_USTED, "¿En qué le ayudo? ¿Qué examen necesita?")
    assert not re.search(_USTED, "¿En qué te ayudo? ¿Qué examen necesitas?")


def _his_spanish_lines() -> list[str]:
    """Every Spanish line the brain writes itself, rather than the model."""
    lines = [
        clini.TOGGLE_CONFIRM["es"],
        clini._INTRO["es"],
        clini._GREETING["es"],
        clini._AGENDA_GREETING["es"],
        *(opener["es"] for _, opener in clini._OPENERS),
        *(landed["es"] for landed in clini._LANDED.values()),
        *(line for kind in clini._ACK_LINES["es"].values() for line in kind),
        *clini._ACK_HOLD["es"],
        clini._ACK_SORRY["es"],
    ]
    pages = ["/", "/cirugia-lasik", "/imagenes", "/laboratorio", "/ubicaciones", "/resultados"]
    lines += [clini.greeting(path, "site", "es") for path in pages]
    lines.append(clini.greeting("/", "agenda", "es"))
    return lines


@pytest.mark.parametrize("line", _his_spanish_lines())
def test_his_own_spanish_lines_are_latin_american_and_say_tu(line: str) -> None:
    assert spain_words(line) == [], line
    assert not re.search(_USTED, line, re.IGNORECASE), line


def test_the_greeting_says_tu() -> None:
    assert "tu guía" in clini._INTRO["es"]
    assert any(re.search(r"\bte\b|\btu\b|\bnecesitas\b", o["es"]) for _, o in clini._OPENERS)


@pytest.mark.parametrize(
    ("written", "for_voice"),
    [
        ("Te muestro un video del examen.", "Te muestro un bidéo del examen."),
        ("Mira los videos de CLINI.", "Mira los bidéos de Clini."),
        ("Un vídeo y una videollamada.", "Un bidéo y una videollamada."),
    ],
)
def test_video_is_respelled_for_the_voice_and_back(written: str, for_voice: str) -> None:
    assert clini.for_the_voice(written) == for_voice
    assert clini.from_the_voice(for_voice) == written.replace("vídeo", "video").replace(
        "CLINI", "Clini"
    )


def test_a_cue_anchor_follows_the_voice() -> None:
    sentence = "Un video muestra cómo es la cirugía."
    at = " ".join(words(sentence)[:3])
    heard = " ".join(words(clini.for_the_voice(sentence)))
    assert heard.startswith(clini._anchor_for_voice(at)), (at, heard)


async def test_the_voice_says_bideo_and_the_model_reads_video() -> None:
    llm = ScriptedOpenAI(
        {
            "¿Cómo es la cirugía LASIK?": reply(
                "{page: /cirugia-lasik} Hay un video que lo muestra."
            ),
            "¿Y cuánto cuesta?": reply("Desde trescientos ochenta y un mil pesos por ojo."),
        }
    )
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        turn = await rig.driver.user_says("¿Cómo es la cirugía LASIK?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert "Hay un bidéo que lo muestra." in turn.text, turn.text
        await rig.driver.user_says("¿Y cuánto cuesta?")
        context = input_texts(llm.captured_inputs[-1])
        assert "Hay un video que lo muestra." in context and "bidéo" not in context, context


def test_the_prompt_asks_for_latin_american_spanish_and_tu() -> None:
    prompt = clini._prompt(clini.kb.KNOWLEDGE)
    for rule in (
        "neutral Latin American Spanish",
        'Address the visitor as "tú"',
        'never "usted"',
        'never "vosotros"',
        'never "vídeo"',
        '"celular", never "móvil"',
        '"está bien" or "perfecto", never "vale"',
        '"¿Qué día te queda bien?", not "te viene bien"',
        "the simple past",
        '"previsión", "sede", "examen", "hora"',
    ):
        assert rule in prompt, rule
