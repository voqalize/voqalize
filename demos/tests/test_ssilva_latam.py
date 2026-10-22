"""Javier's Spanish on ssilva.cl is Latin America's, not Spain's.

The site is Chilean and the call opens in Spanish. The rules are SendPotion's
(``test_sendpotion_latam.py``), with the words a home buyer hears: a
"departamento", never a "piso"; a "celular", never a "móvil". Two halves:

* **The lines he owns — always run, no model.** His greetings, nods, holding
  lines and the lines for a page move are written here, and carry no word or
  form only Spain uses.

* **What the model writes — opt-in, real model.** Skipped without
  ``GEMINI_API_KEY``; run it after any change to the Spanish in the prompt::

      GEMINI_API_KEY=... uv run pytest tests/test_ssilva_latam.py -q
"""

from __future__ import annotations

import os
import re
from typing import Any

import pytest
from voqalize_demos.discovery import discover

from ._harness import check_voice_pair, demo

discover()

from voqalize_demos._loaded.ssilva import brain as ssilva  # noqa: E402
from voqalize_demos._loaded.ssilva import knowledge as kb  # noqa: E402

#: Words and forms only Spain uses, as they would show in what he says.
_SPAIN = {
    "vídeo": r"\bvídeos?\b",
    "vale": r"\bvale\b",
    "vosotros": r"\bvosotr[oa]s\b",
    "os": r"\bos\b",
    "vosotros verb (-áis/-éis)": r"\b\w{2,}(?:áis|éis)\b",
    "piso": r"\bpisos?\b(?! \d)",
    "ordenador": r"\bordenador(?:es)?\b",
    "móvil": r"\bmóvil(?:es)?\b",
    "coger": r"\bco(?:ger|ge|jo|gemos)\b",
    "rellenar": r"\brellen\w*\b",
    "te viene bien": r"\bte viene bien\b",
    "perdona": r"\bperdona\b",
}
_SPAIN_HABIT = {
    "enseñar (show)": r"\bte (?:lo |la )?enseñ\w*|\benseñárte\w*",
    "he + participle": r"\bhe (?:abierto|cerrado|rellenado|puesto|completado)\b",
}


def spain_words(text: str, *, habits: bool = False) -> list[str]:
    """The Spain-only words and forms in ``text``, by name."""
    rules = _SPAIN | (_SPAIN_HABIT if habits else {})
    return [name for name, rx in rules.items() if re.search(rx, text, re.IGNORECASE)]


def test_the_spain_check_catches_spain() -> None:
    assert spain_words("Vale, te enseño el piso en el vídeo.", habits=True) == [
        "vídeo",
        "vale",
        "piso",
        "enseñar (show)",
    ]
    assert spain_words("¿Queréis dejar el móvil?") == ["vosotros verb (-áis/-éis)", "móvil"]
    latam = (
        "Claro, te muestro el departamento. ¿Qué día te queda bien? Ya lo completé, y abrí "
        "el formulario. Está en el piso 8. ¿Quieren dejar su celular?"
    )
    assert spain_words(latam, habits=True) == []


def _his_spanish_lines() -> list[str]:
    """Every Spanish line the brain writes itself, rather than the model."""
    lines = [
        ssilva.TOGGLE_CONFIRM["es"],
        ssilva._INTRO["es"],
        ssilva._GREETING["es"],
        ssilva._PROJECT_OPENER["es"],
        ssilva._PROJECT_OPENER_NO_PRICE["es"],
        *(opener["es"] for opener in ssilva._OPENERS.values()),
        *(landed["es"] for landed in ssilva._LANDED.values()),
        *(line for kind in ssilva._ACK_LINES["es"].values() for line in kind),
        *ssilva._ACK_HOLD["es"],
        ssilva._ACK_SORRY["es"],
    ]
    k = kb.KNOWLEDGE
    pages = ["/", "/proyectos/", "/estocolmo/", "/proyectos/cotizar/estocolmo/"]
    lines += [ssilva.greeting(path, k, "es") for path in [*pages, "/centro-de-negocios/"]]
    return lines


@pytest.mark.parametrize("line", _his_spanish_lines())
def test_his_own_spanish_lines_are_latin_american(line: str) -> None:
    assert spain_words(line, habits=True) == [], line


def test_the_prompt_asks_for_latin_american_spanish() -> None:
    prompt = ssilva._prompt(kb.KNOWLEDGE)
    for rule in (
        "neutral Latin American Spanish",
        'never "vosotros"',
        '"departamento", never "piso"',
        '"celular", never "móvil"',
        '"está bien" or "perfecto", never "vale"',
        '"completar el formulario", not "rellenar"',
        "the simple past",
        "without Chilean slang",
    ):
        assert rule in prompt, rule


@pytest.mark.parametrize(
    ("n", "es", "en"),
    [
        (3375, "tres mil trescientas setenta y cinco", "three thousand three hundred seventy-five"),
        (1753, "mil setecientas cincuenta y tres", "one thousand seven hundred fifty-three"),
        (
            13976,
            "trece mil novecientas setenta y seis",
            "thirteen thousand nine hundred seventy-six",
        ),
        (21000, "veintiún mil", "twenty-one thousand"),
        (2372, "dos mil trescientas setenta y dos", "two thousand three hundred seventy-two"),
        (100, "cien", "one hundred"),
        (101, "ciento una", "one hundred one"),
        (9950, "nueve mil novecientas cincuenta", "nine thousand nine hundred fifty"),
    ],
)
def test_prices_in_uf_are_said_in_words(n: int, es: str, en: str) -> None:
    assert ssilva.number_words(n, "es") == es
    assert ssilva.number_words(n, "en") == en


# ─── What the model writes: the real model ────────────────────────────────────

_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
live = pytest.mark.skipif(not _KEY, reason="no GEMINI_API_KEY — the live Spanish eval is opt-in")
_TURN = 45.0
_ASKS = [
    ["Busco un departamento de dos dormitorios en Viña.", "Muéstrame Canal Beagle."],
    ["¿Qué es la UF y cómo funciona el pie?", "¿Tienen algo para invertir en Santiago?"],
    ["Quiero cotizar Estocolmo.", "Me llamo Ana Pérez."],
]


def _client() -> Any:
    from google import genai

    return genai.Client(api_key=_KEY)


@live
@pytest.mark.parametrize("asks", _ASKS, ids=["find", "explain", "quote"])
async def test_live_he_answers_in_latin_american_spanish(asks: list[str]) -> None:
    async with demo("ssilva", _client()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        said: list[str] = []
        for ask in asks:
            turn = await rig.driver.user_says(ask, timeout=_TURN)
            said.append(turn.text)
        spoken = " ".join(said)
        print(f"\n[{asks[0]}] {spoken}")
        assert spoken.strip(), "he said nothing"
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert spain_words(spoken) == [], f"{spain_words(spoken)} in {spoken!r}"
        assert not re.search(r"\d", spoken.replace("2D", "").replace("2B", "")), spoken
