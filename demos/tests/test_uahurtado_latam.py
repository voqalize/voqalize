"""Javier's Spanish is Latin America's, not Spain's, and he says "tú".

The university's visitors are Chilean school leavers and their families. The
accent is the speech tier's reference clip; the words are this brain's. Every
Spanish line the brain writes itself — the greetings, openers, nods, holding
lines, the lines for a page move and the toggle's confirmation — carries no
word or form only Spain uses, and addresses the visitor as "tú", never "usted".
In Spanish the voice is handed "bidéo" for "video", amounts in words and "u
efe" for the UF, and the model only ever sees what it wrote.

What the model writes is a property of the prompt and the model: the prompt's
rules are checked here, and an opt-in live half (``OPENAI_API_KEY=…``) runs
real Spanish conversations on the committed knowledge.

Run: ``cd demos && uv run pytest tests/test_uahurtado_latam.py``
"""

from __future__ import annotations

import os
import re
from typing import Any

import pytest
from voqalize_demos.discovery import discover

from ._harness import check_voice_pair, demo
from .test_sendpotion_latam import spain_words

discover()

from voqalize_demos._loaded.uahurtado import brain as uah  # noqa: E402
from voqalize_demos._loaded.uahurtado import knowledge as kb  # noqa: E402
from voqalize_demos._loaded.uahurtado.cues import words  # noqa: E402

#: The visitor addressed as "usted": the site, and Javier, say "tú".
_USTED = (
    r"\busted(?:es)?\b|\b(?:le|lo) (?:ayudo|muestro|abro|cuento|explico)\b"
    r"|\b(?:necesita|quiere|tiene|busca|desea)\b\?"
)
#: Chilean slang he never uses in his own lines: neutral Spanish, Chilean
#: context only.
_CHILENISMOS = r"\b(?:po|cachai|cachái|bacán|al tiro|fome|pololo|polola|weón|harto|altiro)\b"


def test_the_checks_catch_spain_usted_and_slang() -> None:
    assert spain_words("Vale, te lo enseño en el vídeo.", habits=True)
    assert re.search(_USTED, "¿En qué le ayudo? ¿Qué carrera busca?")
    assert not re.search(_USTED, "¿En qué te ayudo? ¿Qué carrera buscas?")
    assert re.search(_CHILENISMOS, "Te lo abro al tiro, po.")


def _his_spanish_lines() -> list[str]:
    """Every Spanish line the brain writes itself, rather than the model."""
    lines = [
        uah.TOGGLE_CONFIRM["es"],
        uah._INTRO["es"],
        uah._GREETING["es"],
        uah._CAREER_GREETING["es"],
        *(opener["es"] for _, opener in uah._OPENERS),
        *(landed["es"] for landed in uah._LANDED.values()),
        *(line for kind in uah._ACK_LINES["es"].values() for line in kind),
        *uah._ACK_HOLD["es"],
        uah._ACK_SORRY["es"],
    ]
    urls = [
        "https://admision.uahurtado.cl/",
        "https://admision.uahurtado.cl/becas-y-beneficios/",
        "https://admision.uahurtado.cl/gratuidad-universitaria/",
        "https://admision.uahurtado.cl/ven-y-conocenos/",
        "https://admision.uahurtado.cl/admision-directa/",
        "https://www.uahurtado.cl/la-universidad/campus/campus-patrimonial/",
        "https://postgrados.uahurtado.cl/",
    ]
    lines += [uah.greeting(url, "es") for url in urls]
    return lines


@pytest.mark.parametrize("line", _his_spanish_lines())
def test_his_own_spanish_lines_are_latin_american_and_say_tu(line: str) -> None:
    assert spain_words(line, habits=True) == [], line
    assert not re.search(_USTED, line, re.IGNORECASE), line
    assert not re.search(_CHILENISMOS, line, re.IGNORECASE), line


def test_the_greeting_says_tu() -> None:
    assert "tu guía" in uah._INTRO["es"]
    assert re.search(r"\bte\b|\btu\b", uah._GREETING["es"])


def test_the_prompt_asks_for_latin_american_spanish_and_tu() -> None:
    prompt = uah._prompt(kb.KNOWLEDGE)
    for rule in (
        "neutral Latin American Spanish",
        'Address the visitor as "tú", never "usted"',
        'never "vosotros"',
        'never "vídeo"',
        '"celular", never "móvil"',
        '"está bien" or "perfecto", never "vale"',
        '"completar un formulario", not "rellenar"',
        '"¿Qué día te queda bien?", not "te viene bien"',
        '"mostrar" ("te muestro"), not "enseñar"',
        "the simple past",
        "never heavy slang or chilenismos",
        '"carrera", "malla curricular", "postular", "PAES"',
    ):
        assert rule in prompt, rule


def test_the_prompt_keeps_figures_live_and_the_form_unsent() -> None:
    prompt = uah._prompt(kb.KNOWLEDGE)
    for rule in (
        "Never say a figure that a note or a read did not just give you",
        "Never add up a weighted score yourself",
        "The /aranceles/ page shows last year's table: never quote it.",
        "Never ask for, say, repeat or type their RUT",
        'press "Enviar" themselves',
        "Never open or fill a sign-up form.",
        "they fill it in themselves, never you",
    ):
        assert rule in prompt, rule


@pytest.mark.parametrize(
    ("written", "for_voice"),
    [
        ("Te muestro un video de la carrera.", "Te muestro un bidéo de la carrera."),
        ("Un vídeo y una videollamada.", "Un bidéo y una videollamada."),
        ("La titulación es de 11 UF.", "La titulación es de once u efe."),
        (
            "La matrícula es $277.456.",
            "La matrícula es doscientos setenta y siete mil cuatrocientos cincuenta y seis pesos.",
        ),
    ],
)
def test_the_voice_gets_its_spelling_and_the_model_gets_its_words_back(
    written: str, for_voice: str
) -> None:
    assert uah.for_the_voice(written) == for_voice
    back = uah.from_the_voice(for_voice)
    assert "bidéo" not in back and "u efe" not in back


def test_english_amounts_are_said_in_english_words() -> None:
    assert uah.for_the_voice_en("Tuition is $7,167,421.") == (
        "Tuition is seven million one hundred sixty-seven thousand four hundred twenty-one pesos."
    )


def test_a_cue_anchor_follows_the_voice() -> None:
    for sentence in ("Un video muestra el campus.", "Son 11 UF de titulación."):
        at = " ".join(words(sentence)[:3])
        heard = " ".join(words(uah.for_the_voice(sentence)))
        assert heard.startswith(uah._anchor_for_voice(at)), (at, heard)


# ─── What the model writes: the real model ────────────────────────────────────

_KEY = os.environ.get("OPENAI_API_KEY")
live = pytest.mark.skipif(not _KEY, reason="no OPENAI_API_KEY — the live Spanish eval is opt-in")
_TURN = 45.0
_ASKS = [
    ["¿Qué carreras de ingeniería tienen?", "Háblame de Ingeniería Comercial."],
    ["¿Qué becas hay para buenos puntajes?", "¿Y la gratuidad cómo funciona?"],
    ["¿Dónde queda la universidad?", "¿Puedo ir a conocerla?"],
]


def _client() -> Any:
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=_KEY)


@live
@pytest.mark.parametrize("asks", _ASKS, ids=["careers", "becas", "campus"])
async def test_live_he_answers_in_latin_american_spanish(asks: list[str]) -> None:
    async with demo("uahurtado", _client()) as rig:
        await rig.driver.start_session(init={"url": "https://admision.uahurtado.cl/"})
        said: list[str] = []
        for ask in asks:
            turn = await rig.driver.user_says(ask, timeout=_TURN)
            said.append(turn.text)
        spoken = " ".join(said)
        print(f"\n[{asks[0]}] {spoken}")
        assert spoken.strip(), "he said nothing"
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert spain_words(spoken) == [], f"{spain_words(spoken)} in {spoken!r}"
        assert not re.search(_USTED, spoken, re.IGNORECASE), spoken
        assert not re.search(r"\d", spoken), spoken
