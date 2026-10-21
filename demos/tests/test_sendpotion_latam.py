"""Javier's Spanish is Latin America's, not Spain's.

SendPotion's visitors are businesses across Latin America. A customer there
heard Javier speak the Spanish of Spain: the voice's accent, and words that
belong to Spain ("vale", "vídeo", "te viene bien"). The accent is the speech
tier's reference clip; the words are this brain's. Two halves, as in
``test_kiosk_language.py``:

* **The lines he owns — always run, no model.** His greetings, nods, holding
  lines and the lines for a page move are written here, and carry no word or
  form only Spain uses. In Spanish the voice is handed "bidéo" for "video":
  on dev it read plain "video" with Spain's stress in one sentence of three.
  The page's cue anchors follow that spelling, and the model only ever sees
  "video".

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
    ("written", "for_voice"),
    [
        ("Cada cliente recibe un video.", "Cada cliente recibe un bidéo."),
        ("Los videos llegan por correo.", "Los bidéos llegan por correo."),
        ("Video personalizado", "Bidéo personalizado"),
        ("Un vídeo y dos vídeos.", "Un bidéo y dos bidéos."),
        ("Una videollamada no cambia.", "Una videollamada no cambia."),
    ],
)
def test_video_is_respelled_for_the_voice_and_back(written: str, for_voice: str) -> None:
    """The voice reads "bidéo" as Latin America says "video"; what it said is
    spelled "video" again for the model."""
    assert sendpotion.for_the_voice(written) == for_voice
    assert sendpotion.from_the_voice(for_voice) == written.replace("vídeo", "video")


@pytest.mark.parametrize(
    "sentence",
    [
        "Un video para cada cliente.",
        "Los videos llegan solos.",
        "Un vídeo para ti.",
        "Potion crea un video.",
    ],
)
def test_a_cue_anchor_follows_the_voice(sentence: str) -> None:
    """The page finds a cue by the first words of its sentence in what the voice
    says, reduced to [a-z0-9']; the anchor is spelled the way the voice says it."""
    from voqalize_demos._loaded.sendpotion.cues import words

    at = " ".join(words(sentence)[:3])
    heard = " ".join(words(sendpotion.for_the_voice(sentence)))
    assert heard.startswith(sendpotion._anchor_for_voice(at)), (at, heard)


async def test_the_voice_says_bideo_and_the_model_reads_video() -> None:
    """The voice is handed "bidéo"; the page's cue is anchored to it; the model's
    next request holds what was said, spelled "video"."""
    llm = ScriptedGemini(
        {
            "¿Qué hace Potion?": reply(
                chunks=[
                    "{page: /pricing} Un video para cada cliente.",
                    " Los vídeos llevan tu voz.",
                ]
            ),
            "¿Y cuánto cuesta?": reply("Los planes empiezan en treinta y nueve dólares."),
        }
    )
    async with demo("sendpotion", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/", "lang": "es"})
        turn = await rig.driver.user_says("¿Qué hace Potion?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert "Un bidéo para cada cliente." in turn.text, turn.text
        assert "Los bidéos llevan tu voz." in turn.text, turn.text
        assert "video" not in turn.text.lower().replace("bidéo", ""), turn.text
        cues = [c["payload"] for c in rig.driver.ui_commands if c.get("command") == "cue"]
        assert any(c["at"] == "un bid o para" for c in cues), cues
        await rig.driver.user_says("¿Y cuánto cuesta?")
        context = " ".join(
            part.text or "" for content in llm.captured_contents[-1] for part in content.parts or []
        )
        assert "Un video para cada cliente." in context, context
        assert "bidéo" not in context, context


async def test_the_spanish_greeting_is_respelled_too() -> None:
    llm = ScriptedGemini({"Hola.": reply("Claro.")})
    async with demo("sendpotion", llm) as rig:
        opener = await rig.driver.start_session(
            init={"site": "site", "path": "/pricing/", "lang": "es"}
        )
        assert opener is not None and "harían bidéos?" in opener.text, opener
        await rig.driver.user_says("Hola.")
        context = " ".join(
            part.text or "" for content in llm.captured_contents[-1] for part in content.parts or []
        )
        assert "harían videos?" in context and "bidéo" not in context, context


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
