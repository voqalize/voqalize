"""Javier's Spanish is Latin America's, not Spain's.

SendPotion's visitors are businesses across Latin America. A customer there
heard Javier speak the Spanish of Spain: the voice's accent, and words that
belong to Spain ("vale", "vídeo", "te viene bien"). The accent is the speech
tier's reference clip; the words are this brain's. Two halves, as in
``test_kiosk_language.py``:

* **The lines he owns — always run, no model.** His greetings, nods, holding
  lines and the lines for a page move are written here, and carry no word or
  form only Spain uses. "Vídeo" is respelled "video" in anything he says in
  Spanish, since the voice reads the accented spelling with Spain's stress.

* **What the model writes — opt-in, real model.** Whether Gemini answers in
  Latin American Spanish is a property of the prompt and the model, and only the
  model can show it. Each scenario starts a call in Spanish, asks what a visitor
  asks, and checks every word he said. Skipped without ``GEMINI_API_KEY``; run it
  after any change to the Spanish in the prompt::

      GEMINI_API_KEY=... uv run pytest tests/test_sendpotion_latam.py -q
"""

from __future__ import annotations

import os
import re
from typing import Any

import pytest
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, reply

from ._harness import check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.sendpotion import brain as sendpotion  # noqa: E402

#: Words and forms only Spain uses, as they would show in what he says. The
#: perfect for something just done ("he abierto") is Spain's habit rather than
#: its grammar, so it is checked in his own lines only.
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
}
_SPAIN_HABIT = {
    "enseñar (show)": r"\bte (?:lo |la )?enseñ\w*|\benseñárte\w*",
    "he + participle": r"\bhe (?:abierto|cerrado|rellenado|puesto)\b",
}


def spain_words(text: str, *, habits: bool = False) -> list[str]:
    """The Spain-only words and forms in ``text``, by name."""
    rules = _SPAIN | (_SPAIN_HABIT if habits else {})
    return [name for name, rx in rules.items() if re.search(rx, text, re.IGNORECASE)]


def test_the_spain_check_catches_spain() -> None:
    """The check itself: Spain's Spanish is caught, Latin America's is not."""
    assert spain_words("Vale, te lo enseño en el vídeo.", habits=True) == [
        "vídeo",
        "vale",
        "enseñar (show)",
    ]
    assert spain_words("¿Queréis verlo en el ordenador o en el móvil?") == [
        "vosotros verb (-áis/-éis)",
        "ordenador",
        "móvil",
    ]
    assert spain_words("Ya lo he rellenado. ¿Qué día te viene bien?", habits=True) == [
        "rellenar",
        "te viene bien",
        "he + participle",
    ]
    latam = (
        "Claro, te lo muestro en el video. ¿Qué día te queda bien? Ya lo completé, "
        "y abrí la página en una pestaña nueva. ¿Quieren verlo en la computadora?"
    )
    assert spain_words(latam, habits=True) == []


def _his_spanish_lines() -> list[str]:
    """Every Spanish line the brain writes itself, rather than the model."""
    lines = [
        sendpotion.TOGGLE_CONFIRM["es"],
        sendpotion._INTRO["es"],
        sendpotion._GREETING["es"],
        sendpotion._BLOG_GREETING["es"],
        *(opener["es"] for _, opener in sendpotion._OPENERS),
        *(landed["es"] for landed in sendpotion._LANDED.values()),
        *(line for kind in sendpotion._ACK_LINES["es"].values() for line in kind),
        *sendpotion._ACK_HOLD["es"],
        sendpotion._ACK_SORRY["es"],
    ]
    pages = ["/", "/pricing", "/demo", "/integrations", "/features", "/use-cases", "/faq"]
    lines += [sendpotion.greeting(path, "site", "es") for path in pages]
    lines.append(sendpotion.greeting("/x-1a2b", "blog", "es"))
    return lines


@pytest.mark.parametrize("line", _his_spanish_lines())
def test_his_own_spanish_lines_are_latin_american(line: str) -> None:
    assert spain_words(line, habits=True) == [], line


@pytest.mark.parametrize(
    ("said", "spelled"),
    [
        ("Cada cliente recibe un vídeo.", "Cada cliente recibe un video."),
        ("Los vídeos llegan por correo.", "Los videos llegan por correo."),
        ("Vídeo personalizado", "Video personalizado"),
        ("Un video ya bien escrito.", "Un video ya bien escrito."),
        ("Potion makes videos.", "Potion makes videos."),
    ],
)
def test_video_is_spelled_as_latin_america_says_it(said: str, spelled: str) -> None:
    assert sendpotion.latin_american(said) == spelled


async def test_a_spanish_reply_reaches_the_voice_as_latin_america_spells_it() -> None:
    """The model wrote Spain's "vídeos"; the voice is handed "videos"."""
    llm = ScriptedGemini(
        {
            "¿Qué hace Potion?": reply(
                chunks=[" Potion hace vídeos de ti.", " Cada vídeo lleva tu cara y tu voz."]
            )
        }
    )
    async with demo("sendpotion", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/", "lang": "es"})
        turn = await rig.driver.user_says("¿Qué hace Potion?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert "vídeo" not in turn.text, turn.text
        assert "Potion hace videos de ti." in turn.text, turn.text
        assert "Cada video lleva tu cara y tu voz." in turn.text, turn.text


async def test_english_speech_is_left_as_written() -> None:
    llm = ScriptedGemini({"What does Potion do?": reply("Potion makes videos of you.")})
    async with demo("sendpotion", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        turn = await rig.driver.user_says("What does Potion do?")
        assert turn.text.strip().endswith("Potion makes videos of you."), turn.text


def test_the_prompt_asks_for_latin_american_spanish() -> None:
    prompt = sendpotion._prompt(sendpotion.kb.KNOWLEDGE)
    assert "Madrid" not in prompt
    for rule in (
        "neutral Latin American Spanish",
        'never "vosotros"',
        'never "vídeo"',
        '"computadora", never "ordenador"',
        '"celular", never "móvil"',
        '"está bien" or "perfecto", never "vale"',
        '"¿Qué día te queda bien?", not "te viene bien"',
        "the simple past",
    ):
        assert rule in prompt, rule


# ─── What the model writes: the real model ────────────────────────────────────

_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
live = pytest.mark.skipif(not _KEY, reason="no GEMINI_API_KEY — the live Spanish eval is opt-in")

#: How long one real turn may take, tools included.
_TURN = 45.0

#: What a visitor from Latin America asks, in their Spanish: the questions the
#: site's own story is made of, and the ones that pull the Spain-only words out
#: (a demo's day, a video, a form filled in, a team of several people).
_ASKS = [
    ["¿Qué es Potion y cómo funciona?", "¿Cómo se ven los videos que recibe el cliente?"],
    ["¿Cuánto cuesta Potion?", "Somos un equipo de cinco personas, ¿qué plan nos recomiendas?"],
    ["¿Cómo usan Potion los equipos de marketing?", "Muéstrame otro caso de uso, por favor."],
    ["Quiero agendar una demo.", "El martes por la tarde, si se puede."],
]


def _client() -> Any:
    from google import genai

    return genai.Client(api_key=_KEY)


@live
@pytest.mark.parametrize("asks", _ASKS, ids=["how-it-works", "pricing", "use-cases", "demo"])
async def test_live_he_answers_in_latin_american_spanish(asks: list[str]) -> None:
    async with demo("sendpotion", _client()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/", "lang": "es"})
        said: list[str] = []
        for ask in asks:
            turn = await rig.driver.user_says(ask, timeout=_TURN)
            said.append(turn.text)
        spoken = " ".join(said)
        print(f"\n[{asks[0]}] {spoken}")
        assert spoken.strip(), "he said nothing"
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert sendpotion.language_of(spoken, sure=False) == "es", spoken
        assert spain_words(spoken) == [], f"{spain_words(spoken)} in {spoken!r}"
