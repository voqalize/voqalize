"""Javier's Spanish is Latin America's, not Spain's, and he says "tú".

Saint George's families are in Chile. The accent is the speech tier's
reference clip; the words are this brain's. Every Spanish line the brain
writes itself — the greetings, the lines for a page move,
and the email to admissions it readies — carries no word or form only Spain
uses, and addresses the parent as "tú", never "usted". In Spanish the voice is
handed "bidéo" for "video", and the model only ever sees "video".

What the model writes is a property of the prompt and the model; the prompt's
rules are checked here, and the live check is SendPotion's opt-in eval
(``test_sendpotion_latam.py``), whose rules this prompt carries.

Run: ``cd demos && uv run pytest tests/test_saintgeorge_latam.py``
"""

from __future__ import annotations

import re

import pytest
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedOpenAI, input_texts, reply

from ._harness import check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.saintgeorge import brain as sg  # noqa: E402
from voqalize_demos._loaded.saintgeorge.cues import words  # noqa: E402

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
    "he + participle": r"\bhe (?:abierto|cerrado|rellenado|puesto|completado|enviado)\b",
}
#: The parent addressed as "usted": Javier says "tú".
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
    assert re.search(_USTED, "¿En qué le ayudo? ¿Qué curso busca?")
    assert not re.search(_USTED, "¿En qué te ayudo? ¿Qué curso buscas?")


def _email() -> list[str]:
    request = sg.ContactRequest(
        parent_name="Ana Pérez",
        child="daughter",
        child_age="5",
        grade="Kínder 2027",
        question="¿Hay vacantes y cuándo puedo visitar el colegio?",
    )
    subject, body = sg.contact_email(request, "es")
    return [subject, body]


def _his_spanish_lines() -> list[str]:
    """Every Spanish line the brain writes itself, rather than the model."""
    lines = [
        sg.TOGGLE_CONFIRM["es"],
        sg._INTRO["es"],
        sg._GREETING["es"],
        *(opener["es"] for _, opener in sg._OPENERS),
        *(landed["es"] for landed in sg._LANDED.values()),
        *_email(),
    ]
    pages = [
        "/",
        "/admision/admision",
        "/admision/admision-programa-moreau",
        "/unidad/infant",
        "/familia/calendario",
        "/familia/musical-the-lion-king",
        "/formacion-integral/area-deportiva",
    ]
    return lines + [sg.greeting(path, "es") for path in pages]


@pytest.mark.parametrize("line", _his_spanish_lines())
def test_his_own_spanish_lines_are_latin_american_and_say_tu(line: str) -> None:
    assert spain_words(line) == [], line
    assert not re.search(_USTED, line, re.IGNORECASE), line


def test_the_greeting_says_tu() -> None:
    assert "tu guía" in sg._INTRO["es"]
    assert all(re.search(r"\bte\b|\btu\b", o["es"], re.IGNORECASE) for _, o in sg._OPENERS)


@pytest.mark.parametrize(
    ("written", "for_voice"),
    [
        ("Te muestro un video del colegio.", "Te muestro un bidéo del colegio."),
        ("Mira los videos de la historia.", "Mira los bidéos de la historia."),
        ("Un vídeo y una videollamada.", "Un bidéo y una videollamada."),
    ],
)
def test_video_is_respelled_for_the_voice_and_back(written: str, for_voice: str) -> None:
    assert sg.for_the_voice(written) == for_voice
    assert sg.from_the_voice(for_voice) == written.replace("vídeo", "video")


def test_a_cue_anchor_follows_the_voice() -> None:
    sentence = "Un video cuenta la historia del colegio."
    at = " ".join(words(sentence)[:3])
    heard = " ".join(words(sg.for_the_voice(sentence)))
    assert heard.startswith(sg._anchor_for_voice(at)), (at, heard)


async def test_the_voice_says_bideo_and_the_model_reads_video() -> None:
    llm = ScriptedOpenAI(
        {
            "¿Tienen algo de la historia?": reply(
                "{page: /colegio/historia} Hay un video que la cuenta."
            ),
            "¿Y desde cuándo existe?": reply("Desde hace noventa años."),
        }
    )
    async with demo("saintgeorge", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("¿Tienen algo de la historia?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert "Hay un bidéo que la cuenta." in turn.text, turn.text
        await rig.driver.user_says("¿Y desde cuándo existe?")
        context = input_texts(llm.captured_inputs[-1])
        assert "Hay un video que la cuenta." in context and "bidéo" not in context, context


def test_the_prompt_asks_for_latin_american_spanish_and_tu() -> None:
    prompt = sg._prompt(sg.kb.KNOWLEDGE)
    for rule in (
        "neutral Latin American Spanish",
        'Address one visitor as "tú", never "usted"',
        'never "vosotros"',
        'never "vídeo"',
        '"celular", never "móvil"',
        '"está bien" or "perfecto", never "vale"',
        '"¿Qué día te queda bien?", not "te viene bien"',
        "the simple past",
        '"apoderado"',
    ):
        assert rule in prompt, rule
