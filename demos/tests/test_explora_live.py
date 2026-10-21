"""Javier on Explora with the real model — opt-in, like SendPotion's live eval.

Each conversation runs the real ``ExploraBrain`` on the committed knowledge with
Gemini itself writing the replies; every page he opens loads and reports itself
the way the extension's next page does, with the headings the crawl has for it.
What is asserted is what the scripted tests cannot see: that the model writes
cues, that a page move comes at the start of a reply, that a Spanish reply is
Latin America's Spanish, and that bookings go through the tools.

Run: ``GEMINI_API_KEY=… uv run pytest tests/test_explora_live.py -s``
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest
from voqalize_demos.discovery import discover

from ._harness import check_voice_pair, demo
from .test_sendpotion_latam import spain_words

discover()

from voqalize_demos._loaded.explora import brain as explora  # noqa: E402
from voqalize_demos._loaded.explora import knowledge as kb  # noqa: E402

_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
live = pytest.mark.skipif(not _KEY, reason="no GEMINI_API_KEY — the live eval is opt-in")

#: How long one real turn may take, tools and a page load included.
_TURN = 60.0


def _client() -> Any:
    from google import genai

    return genai.Client(api_key=_KEY)


def _page_changed(path: str) -> dict[str, Any]:
    page = kb.KNOWLEDGE.page(path)
    return {
        "site": "site",
        "url": f"https://www.explora.com{kb.site_path(page.path) if page else path}",
        "path": kb.site_path(page.path) if page else path,
        "title": page.title if page else "",
        "headings": list(page.headings) if page else [],
        "faqs": [f.q for f in page.faqs] if page else [],
        "tabs": list(page.tabs) if page else [],
    }


async def _pages_load(rig: Any) -> None:
    """Every ``navigate`` he sends lands, a moment later, as the extension's
    next page reporting itself."""
    seen = 0
    while True:
        await asyncio.sleep(0.05)
        moves = [c["payload"] for c in rig.driver.ui_commands if c.get("command") == "navigate"]
        for move in moves[seen:]:
            await asyncio.sleep(0.3)
            await rig.driver.send_ui_event("page_changed", _page_changed(move["path"]))
        seen = len(moves)


async def _converse(asks: list[str], *, path: str, lang: str | None) -> tuple[Any, list[str]]:
    async with demo("explora", _client()) as rig:
        init: dict[str, Any] = {"site": "site", "path": path}
        if lang:
            init["lang"] = lang
        await rig.driver.start_session(init=init)
        await rig.driver.send_ui_event("page_changed", _page_changed(path))
        loader = asyncio.create_task(_pages_load(rig))
        said: list[str] = []
        try:
            for ask in asks:
                turn = await rig.driver.user_says(ask, timeout=_TURN, quiet_for=6.0)
                said.append(turn.text)
                moves = [
                    (c["command"], c["payload"])
                    for c in rig.driver.ui_commands
                    if c.get("command") not in ("language_changed",)
                ]
                print(f"\n> {ask}\n< {turn.text}\n  moves: {moves[-8:]}")
        finally:
            loader.cancel()
        if lang:
            check_voice_pair(rig, voice="omnivoice/javier", language=lang)
        return rig, said


@live
async def test_live_a_tour_moves_the_page_with_the_story() -> None:
    rig, said = await _converse(
        [
            "What is Explora?",
            "Patagonia sounds great. Which lodge is best for hiking?",
            "What's included in the stay?",
        ],
        path="/",
        lang=None,
    )
    assert all(s.strip() for s in said), said
    commands = [c["command"] for c in rig.driver.ui_commands]
    assert commands.count("cue") >= 3, commands
    assert "navigate" in commands, commands
    assert all("{" not in s for s in said), said


@live
async def test_live_he_checks_availability_with_the_tool() -> None:
    rig, _ = await _converse(
        ["Tell me about the Atacama lodge.", "Can I go in March for four nights?"],
        path="/lodge/atacama-lodge/",
        lang=None,
    )
    stays = [c["payload"] for c in rig.driver.ui_commands if c["command"] == "check_availability"]
    assert stays and stays[-1]["hotel_code"] == "EATA", stays


@live
@pytest.mark.parametrize(
    "asks",
    [
        ["¿Qué es Explora y qué incluye la estadía?", "Muéstrame el lodge de Atacama."],
        ["Quiero hacer la expedición Sacred Mountains.", "Me llamo Ana Díaz."],
    ],
    ids=["tour", "expedition"],
)
async def test_live_he_answers_in_latin_american_spanish(asks: list[str]) -> None:
    _, said = await _converse(asks, path="/", lang="es")
    spoken = " ".join(said)
    assert spoken.strip(), "he said nothing"
    assert explora.language_of(spoken, sure=False) == "es", spoken
    assert spain_words(spoken) == [], f"{spain_words(spoken)} in {spoken!r}"
