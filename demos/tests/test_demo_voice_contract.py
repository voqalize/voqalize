"""Every demo, one check: the voice and the language reach the wire as a pair.

The per-demo e2e files each drive their own demo's conversation. This one is the
sweep — it opens a session against **all eleven** demos and asserts only the thing
that has broken repeatedly and that nothing else can see:

* both halves of the language landed (TTS ``language`` *and* STT ``language_hint``),
  agreeing, before the greeting audio;
* every value is one vql-speech actually serves.

Why this needs its own file rather than a line in each demo's tests: the failures
it catches are **silent**. A demo speaking Devanagari through the English
reference clip transcribes perfectly — the words are right and only the speaker is
wrong — so WER, logs, and every automated score stay green while the caller hears
a foreign accent. And a value naming an engine that was deleted a release ago is
not a soft failure at all: it is an HTTP 403 at connect. Both have shipped to
production, from three different owners of one field. This file is the guard for
the rule that replaced them: the brain declares it, once, and it is checked here
for every demo at once, so a new demo cannot quietly opt out.

Run: ``cd demos && uv run pytest tests/test_demo_voice_contract.py``
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pytest
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini

from voqalize.conformance import ConformanceError
from voqalize.sdk import Brain

from ._harness import check_catalog, check_greeting, check_voice_pair, demo, demo_from

pytest.importorskip("google.adk")  # the two ADK demos are built directly, below

discover()

from voqalize_demos._loaded.orderdesk.brain import OrderDeskBrain  # noqa: E402
from voqalize_demos._loaded.travel.brain import TravelBrain  # noqa: E402

from voqalize.google_adk.testing import ScriptedLlm  # noqa: E402


@dataclass(frozen=True)
class Expected:
    """One demo's declared voice/language, and the payload that resolves it.

    ``payload`` matters for the demos that pick a language per caller — which is
    the whole reason the value lives in the brain and not on the agent record: one
    record holds one language, and Tamil Nadu wants Tamil while Gujarat wants
    Gujarati."""

    voice: str
    language: str
    payload: dict[str, Any] = field(default_factory=dict)
    build: Callable[[], Brain] | None = None


# The full demo set. Keep this table in step with ``demos/manifest.json`` — the
# test below fails if a demo is discovered and not listed here, so adding a demo
# without declaring its voice is a red suite, not a silent gap.
DEMOS: dict[str, Expected] = {
    "aura": Expected(voice="omnivoice/gauri", language="en"),
    "forge": Expected(voice="omnivoice/gauri", language="en"),
    "interview_bot": Expected(voice="omnivoice/gauri", language="en"),
    "legal": Expected(voice="omnivoice/gauri", language="en"),
    # Auric opens in the language of the enquiry form's state; nothing in the
    # payload ⇒ the Hindi default.
    "lead_qual": Expected(voice="omnivoice/gauri", language="hi"),
    "orderdesk": Expected(
        voice="omnivoice/gauri",
        language="hi",
        build=lambda: OrderDeskBrain(model=ScriptedLlm({})),
    ),
    "servicing": Expected(voice="omnivoice/gauri", language="en"),
    "shopping": Expected(voice="omnivoice/gaurav", language="en"),
    "sugar": Expected(voice="omnivoice/gauri", language="en"),
    "support": Expected(voice="omnivoice/gaurav", language="en"),
    "travel": Expected(
        voice="omnivoice/gauri",
        language="hi",
        build=lambda: TravelBrain(model=ScriptedLlm({})),
    ),
}


def _open(name: str, expected: Expected):
    """The rig for one demo — through the umbrella's own factory where the demo
    takes the injected provider, directly where it builds its own model."""
    if expected.build is not None:
        return demo_from(name, expected.build)
    return demo(name, ScriptedGemini())


def test_every_discovered_demo_declares_a_voice() -> None:
    """A demo dropped into ``demos/`` is registered by existing; this table is not.
    Fail loudly rather than skipping the new demo's voice silently."""
    discovered = {d.name for d in discover()}
    assert discovered == set(DEMOS), (
        f"undeclared: {sorted(discovered - set(DEMOS))}; stale: {sorted(set(DEMOS) - discovered)}"
    )


@pytest.mark.parametrize("name", sorted(DEMOS))
async def test_demo_puts_a_complete_voice_pair_on_the_wire(name: str) -> None:
    """Open a real session against the demo and read the settings frames.

    This is the whole contract: the caller heard *something*, and the recognizer
    and the reference clip were told the same language before they did."""
    expected = DEMOS[name]
    async with _open(name, expected) as rig:
        greeting = await rig.driver.start_session(init=expected.payload)
        check_greeting(rig, greeting)
        check_voice_pair(rig, voice=expected.voice, language=expected.language)


async def test_a_per_caller_language_moves_both_halves() -> None:
    """Sugar's patient picks the language, so it is resolved in the brain from the
    payload rather than declared — and it must move the recognizer *and* the
    reference clip together. Until one atomic ``configure`` existed, the choice only
    reached the prompt: the coach wrote Devanagari and an en-IN voice read it out,
    correct on paper and foreign in the ear."""
    async with demo("sugar", ScriptedGemini()) as rig:
        await rig.driver.start_session(init={"language": "Hindi", "scenario": {}})
        check_voice_pair(rig, voice="omnivoice/gauri", language="hi")


async def test_a_per_caller_language_follows_the_enquiry_state() -> None:
    """Auric resolves the caller's language from the enquiry form's state — one
    agent, nine languages, which no single agent-record field could hold."""
    async with demo("lead_qual", ScriptedGemini()) as rig:
        await rig.driver.start_session(init={"name": "Meera", "state": "Tamil Nadu"})
        check_voice_pair(rig, voice="omnivoice/gauri", language="ta")


async def test_the_check_fails_when_a_half_is_wrong() -> None:
    """The negative control: this suite's own probe must be able to fail.

    A green check against a session that never sent the frames — or sent a
    mismatched pair — would be worse than no check, because it reads as proof. So
    assert against a real, correctly-configured session that the *wrong*
    expectation is rejected, on each half independently."""
    async with demo("shopping", ScriptedGemini()) as rig:
        await rig.driver.start_session()
        # The session really is en/gaurav — so each of these must raise.
        with pytest.raises(ConformanceError, match="TTS language"):
            check_voice_pair(rig, voice="omnivoice/gaurav", language="hi")
        with pytest.raises(ConformanceError, match="TTS voice"):
            check_voice_pair(rig, voice="omnivoice/gauri", language="en")
        # And the catalog check passes only because the values are real ones.
        check_catalog(rig)
        rig.driver.tts_settings.append({"voice": "supertonic/F1"})
        with pytest.raises(ConformanceError, match="not in the catalog"):
            check_catalog(rig)
        rig.driver.tts_settings.pop()
        rig.driver.stt_settings.append({"model": "indic-conformer"})
        with pytest.raises(ConformanceError, match="403"):
            check_catalog(rig)
