"""Javier's Spanish is Latin America's, not Spain's, and he says "tú".

Enveedo's Spanish-speaking visitors are security and IT leaders across Latin
America. The accent is the speech tier's reference clip; the words are this
brain's. Every Spanish line the brain writes itself — the greetings, the
openers per page, nods, holding lines and the lines for a page move — carries
no word or form only Spain uses and addresses the visitor as "tú", never
"usted". In Spanish the voice is handed "bidéo" for "video", "sok dos" for "SOC
2", "siso" for "CISO" and the ISO standards in words; the model only ever sees
the site's spelling.

What the model writes is a property of the prompt and the model; the prompt's
rules are checked here, and the live check is SendPotion's opt-in eval
(``test_sendpotion_latam.py``), whose rules this prompt carries.

Run: ``cd demos && uv run pytest tests/test_enveedo_latam.py``
"""

from __future__ import annotations

import re

import pytest
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedOpenAI, input_texts, reply

from ._harness import check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.enveedo import brain as ev  # noqa: E402
from voqalize_demos._loaded.enveedo.cues import words  # noqa: E402

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
    assert re.search(_USTED, "¿En qué le ayudo? ¿Qué marco busca?")
    assert not re.search(_USTED, "¿En qué te ayudo? ¿Qué marco buscas?")


def _his_spanish_lines() -> list[str]:
    """Every Spanish line the brain writes itself, rather than the model."""
    lines = [
        ev.TOGGLE_CONFIRM["es"],
        ev._INTRO["es"],
        ev._GREETING["es"],
        *(opener["es"] for opener in ev._OPENERS.values()),
        *(landed["es"] for landed in ev._LANDED.values()),
        *(line for kind in ev._ACK_LINES["es"].values() for line in kind),
        *ev._ACK_HOLD["es"],
        ev._ACK_SORRY["es"],
    ]
    pages = ["/", "/es/", "/es/frameworks", "/book-a-demo", "/es/contact", "/es/trust-center"]
    return lines + [ev.greeting(path, "es") for path in pages]


@pytest.mark.parametrize("line", _his_spanish_lines())
def test_his_own_spanish_lines_are_latin_american_and_say_tu(line: str) -> None:
    assert spain_words(line) == [], line
    assert not re.search(_USTED, line, re.IGNORECASE), line


def test_the_greeting_says_tu() -> None:
    assert "tu guía" in ev._INTRO["es"]
    assert "tu rol" in ev._GREETING["es"]
    assert all(
        re.search(
            r"\bte\b|\btu\b|\btus\b|\bquieres\b|\bmanejas\b|\bofreces\b|\bestás\b",
            o["es"],
            re.IGNORECASE,
        )
        for o in ev._OPENERS.values()
    )


@pytest.mark.parametrize(
    ("written", "for_voice"),
    [
        ("Te muestro un video de la plataforma.", "Te muestro un bidéo de la plataforma."),
        ("El informe SOC 2 está aquí.", "El informe sok dos está aquí."),
        (
            "Cubre ISO 27001 e ISO 42001.",
            "Cubre ISO veintisiete mil uno e ISO cuarenta y dos mil uno.",
        ),
        ("Para el CISO y los MSSPs.", "Para el siso y los eme ese ese pes."),
        (
            "Una evaluación valorada en 2.500 USD.",
            "Una evaluación valorada en dos mil quinientos dólares.",
        ),
        ("Soporta 45+ marcos.", "Soporta más de cuarenta y cinco marcos."),
    ],
)
def test_spanish_is_respelled_for_the_voice(written: str, for_voice: str) -> None:
    assert ev.for_the_voice(written, "es") == for_voice


def test_what_comes_back_is_spelled_as_the_site_writes_it() -> None:
    assert ev.from_the_voice("El informe sok dos para el siso.") == "El informe SOC 2 para el CISO."
    assert (
        ev.from_the_voice("Un bidéo de la ISO veintisiete mil uno.") == "Un video de la ISO 27001."
    )


def test_a_cue_anchor_follows_the_voice() -> None:
    for sentence in ("Un video muestra la plataforma.", "El SOC 2 de Enveedo es anual."):
        at = " ".join(words(sentence)[:3])
        heard = " ".join(words(ev.for_the_voice(sentence, "es")))
        assert heard.startswith(ev._anchor_for_voice(at, "es")), (at, heard)


async def test_the_voice_says_sok_dos_and_the_model_reads_soc_2() -> None:
    llm = ScriptedOpenAI(
        {
            "¿Tienen SOC 2?": reply(
                "{page: /trust-center}{show: soc2} Sí, tienen un informe SOC 2 Tipo II."
            ),
            "¿Y quién lo audita?": reply("El sitio no nombra la firma."),
        }
    )
    async with demo("enveedo", llm) as rig:
        await rig.driver.start_session(init={"path": "/es/", "site_lang": "es"})
        turn = await rig.driver.user_says("¿Tienen SOC 2?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert "un informe sok dos Tipo II." in turn.text, turn.text
        await rig.driver.user_says("¿Y quién lo audita?")
        context = input_texts(llm.captured_inputs[-1])
        assert "un informe SOC 2 Tipo II." in context and "sok dos" not in context, context


def test_the_prompt_asks_for_latin_american_spanish_and_tu() -> None:
    prompt = ev._prompt(ev.kb.KNOWLEDGE)
    for rule in (
        "neutral Latin American Spanish",
        'Address one visitor as "tú", never "usted", unless they speak to you as usted',
        'never "vosotros"',
        'never "vídeo"',
        '"celular", never "móvil"',
        '"está bien" or "perfecto", never "vale"',
        '"¿Qué día te queda bien?", not "te viene bien"',
        "the simple past",
        "The site's forms, buttons and cookie banner stay in English on the Spanish pages.",
    ):
        assert rule in prompt, rule
