"""Javier's Spanish is Latin America's, not Spain's, and he says "tú".

Figurella's visitors are women in Chile. The accent is the speech tier's
reference clip; the words are this brain's. Every Spanish line the brain
writes itself — the greetings and the lines for a page move — carries no word or form only Spain uses, addresses her as "tú", never
"usted", and never judges a body. In Spanish the voice is handed "bidéo" for
"video", and the model only ever sees "video".

What the model writes is a property of the prompt and the model; the prompt's
rules are checked here, and the live check is SendPotion's opt-in eval
(``test_sendpotion_latam.py``), whose rules this prompt carries.

Run: ``cd demos && uv run pytest tests/test_figurella_latam.py``
"""

from __future__ import annotations

import re

import pytest
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedOpenAI, input_texts, reply

from ._harness import check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.figurella import brain as fg  # noqa: E402
from voqalize_demos._loaded.figurella.cues import words  # noqa: E402

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
#: Words about a body that judge it.
_JUDGING = r"\b(?:gorda|gordita|rollitos?|fea|sobrepeso)\b"


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
    assert re.search(_USTED, "¿En qué le ayudo? ¿Qué plan busca?")
    assert not re.search(_USTED, "¿En qué te ayudo? ¿Qué plan buscas?")


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
        "/metodo-figurella/",
        "/planes/",
        "/convenios/",
        "/historias-de-exito/",
        "/preguntas-frecuentes/",
        "/franquicias/",
    ]
    return lines + [fg.greeting(path, "es") for path in pages]


@pytest.mark.parametrize("line", _his_spanish_lines())
def test_his_own_spanish_lines_are_latin_american_and_say_tu(line: str) -> None:
    assert spain_words(line) == [], line
    assert not re.search(_USTED, line, re.IGNORECASE), line
    assert not re.search(_JUDGING, line, re.IGNORECASE), line


def test_the_greeting_says_tu_and_offers_the_free_diagnosis() -> None:
    assert "tu guía" in fg._INTRO["es"]
    assert "diagnóstico corporal gratis" in fg._GREETING["es"]
    assert all(re.search(r"\bte\b|\btu\b|\btus\b", o["es"], re.IGNORECASE) for _, o in fg._OPENERS)


@pytest.mark.parametrize(
    ("written", "for_voice"),
    [
        ("Te muestro un video del método.", "Te muestro un bidéo del método."),
        ("Cada paso tiene su video.", "Cada paso tiene su bidéo."),
        ("Un vídeo y una videollamada.", "Un bidéo y una videollamada."),
    ],
)
def test_video_is_respelled_for_the_voice_and_back(written: str, for_voice: str) -> None:
    assert fg.for_the_voice(written) == for_voice
    assert fg.from_the_voice(for_voice) == written.replace("vídeo", "video")


def test_a_cue_anchor_follows_the_voice() -> None:
    sentence = "Un video muestra la cápsula térmica."
    at = " ".join(words(sentence)[:3])
    heard = " ".join(words(fg.for_the_voice(sentence)))
    assert heard.startswith(fg._anchor_for_voice(at)), (at, heard)


async def test_the_voice_says_bideo_and_the_model_reads_video() -> None:
    llm = ScriptedOpenAI(
        {
            "¿Tienen algo del método?": reply(
                "{page: /metodo-figurella/} Hay un video de cada paso."
            ),
            "¿Y cuánto dura?": reply("Una hora en total."),
        }
    )
    async with demo("figurella", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("¿Tienen algo del método?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert "Hay un bidéo de cada paso." in turn.text, turn.text
        await rig.driver.user_says("¿Y cuánto dura?")
        context = input_texts(llm.captured_inputs[-1])
        assert "Hay un video de cada paso." in context and "bidéo" not in context, context


def test_the_prompt_asks_for_latin_american_spanish_and_tu() -> None:
    prompt = fg._prompt(fg.kb.KNOWLEDGE)
    for rule in (
        "neutral Latin American Spanish",
        'Address her as "tú", never "usted"',
        'never "vosotros"',
        'never "vídeo"',
        '"celular", never "móvil"',
        '"está bien" or "perfecto", never "vale"',
        '"¿Qué día te queda bien?", not "te viene bien"',
        "the simple past",
        "speak to her in the feminine",
    ):
        assert rule in prompt, rule
