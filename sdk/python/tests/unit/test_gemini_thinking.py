"""A brain picks its model's thinking level; unset, it is the voice floor."""

from __future__ import annotations

from google.genai import types

from tests.unit.test_gemini_turn import _ScriptedClient  # pyright: ignore[reportPrivateUsage]
from voqalize.sdk.gemini import VOICE_THINKING, GeminiBrain


def _config(brain: GeminiBrain) -> types.GenerateContentConfig:
    return brain._config  # pyright: ignore[reportPrivateUsage]


def test_thinking_defaults_to_the_voice_floor() -> None:
    brain = GeminiBrain(client=_ScriptedClient([]), system_instruction="x")  # pyright: ignore[reportArgumentType]
    assert _config(brain).thinking_config is VOICE_THINKING


def test_a_brain_can_choose_its_thinking_level() -> None:
    low = types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)
    brain = GeminiBrain(client=_ScriptedClient([]), system_instruction="x", thinking=low)  # pyright: ignore[reportArgumentType]
    assert _config(brain).thinking_config is low
