"""Javier's cues on Stage: out of the speech, each sent as a ``stage_cue``
anchored to the raw words that follow it, and answered by one ``stage_result``.

Explora's cue verbs are Stage's ``show`` and ``faq``; a ``{page: …}`` cue is
not a cue on Explora (the brain splits the reply there, ``test_explora_e2e``).

Run: ``cd demos && uv run pytest tests/test_explora_cues.py``
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from voqalize_demos.discovery import discover

from voqalize.sdk import Speech, SpeechChunk, SpeechEnd, SpeechStart
from voqalize.sdk.stage import MAX_CUE, Stage, StageCue, StageResult

discover()

from voqalize_demos._loaded.explora.brain import MOVES  # noqa: E402


async def _speech(*chunks: str) -> AsyncGenerator[Speech, None]:
    yield SpeechStart()
    for c in chunks:
        yield SpeechChunk(c)
    yield SpeechEnd()


async def _run(*chunks: str, backstop: Any = None) -> tuple[str, list[StageCue], Stage]:
    sent: list[Any] = []
    stage = Stage(dispatch=sent.append, moves=MOVES, backstop=backstop)
    spoken = ""
    async for event in stage.cued(_speech(*chunks)):
        if isinstance(event, SpeechChunk):
            spoken += event.text
    return spoken, [c for c in sent if isinstance(c, StageCue)], stage


async def test_cues_leave_the_speech_and_anchor_to_the_words_after_them() -> None:
    spoken, cues, _ = await _run(
        "{show: How it works} It takes three steps. {show: Train} First, you train it on you."
    )
    assert "{" not in spoken and "}" not in spoken
    assert spoken == " It takes three steps. First, you train it on you."
    assert [(c.move, c.verb, c.args, c.at, c.before) for c in cues] == [
        ("core.show", "show", ["How it works"], "It takes three steps. First, you train it on", 0),
        ("core.show", "show", ["Train"], "First, you train it on", 23),
    ]
    assert [c.call_ref for c in cues] == ["c1", "c2"]


async def test_a_cue_split_across_chunks_still_parses() -> None:
    spoken, cues, _ = await _run(
        "Plans start low. {sh", "ow: Pricing pl", "ans} Thirty-nine dol", "lars a month."
    )
    assert spoken == "Plans start low. Thirty-nine dollars a month."
    # Released once three words have followed it; a word still growing is left out.
    assert [(c.args, c.at) for c in cues] == [(["Pricing plans"], "Thirty-nine dollars a")]


async def test_a_cue_at_the_end_fires_when_the_voice_stops() -> None:
    spoken, cues, _ = await _run("Here is the FAQ. {faq: Can I cancel anytime?}")
    assert spoken.strip() == "Here is the FAQ."
    assert [(c.move, c.at) for c in cues] == [("core.faq", "")]


async def test_anchors_are_raw_words_in_any_language() -> None:
    _, cues, _ = await _run(
        "{show: Incluido en su estadía} Todo está incluido, también las excursiones."
    )
    assert cues[0].at == "Todo está incluido, también las"


async def test_braces_that_are_not_cues_are_not_spoken_and_a_stray_one_is_dropped() -> None:
    spoken, cues, _ = await _run("Hello {mood: happy} there. {page: /lodge/}Fine.")
    assert spoken == "Hello there. Fine." and cues == []
    long = "word " * (MAX_CUE // 4)
    spoken, cues, _ = await _run("Open { " + long, "and on.")
    assert "{" not in spoken and spoken.startswith("Open ") and cues == []


async def test_each_sentence_is_offered_for_the_moves_it_did_not_bring() -> None:
    seen: list[tuple[str, int, tuple[tuple[str, tuple[str, ...]], ...]]] = []

    def auto(
        sentence: str, index: int, placed: tuple[tuple[str, tuple[str, ...]], ...]
    ) -> list[tuple[str, list[str]]]:
        seen.append((sentence, index, placed))
        return [("show", ["Dormant leads"])] if "dormant" in sentence else []

    _, cues, _ = await _run(
        "{show: Sales} Hi. Reps wake up dor", "mant leads, too. Want pricing?", backstop=auto
    )
    assert seen == [
        ("Hi.", 0, (("show", ("Sales",)),)),
        ("Reps wake up dormant leads, too.", 1, ()),
        ("Want pricing?", 2, ()),
    ]
    assert [(c.args, c.at, c.before) for c in cues] == [
        (["Sales"], "Hi. Reps wake up", 0),
        (["Dormant leads"], "Reps wake up dormant leads, too. Want", 5),
    ]


async def test_each_cue_gets_one_result() -> None:
    _, cues, stage = await _run("{show: Rooms} Here are the rooms.")
    ref = cues[0].call_ref
    done = StageResult(call_ref=ref, move="core.show", outcome="applied", detail="ringed Rooms")
    assert stage.handle(done) == done
    # A second answer for the same move is a duplicate.
    assert stage.handle(done) is None
