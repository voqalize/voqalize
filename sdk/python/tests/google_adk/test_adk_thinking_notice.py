"""A Gemini agent left at its default thinking budget is told so, once.

Thinking happens *before* the first spoken token, and on a voice call that is
silence the caller sits through — then the SDK drops the thought parts, so the cost
has no audible half at all. It reads as "the brain is slow" and nothing in any log
or transcript names it. Measured on one production screening agent: 2115 ms to the
first spoken token at the default, 1119 ms with the budget at zero.

Not an error — a reasoning budget is right for some agents, and only the client
knows which. So: a line at build time, and never a default we override.
"""

from __future__ import annotations

import pytest

pytest.importorskip("google.adk")

from google.adk.agents import LlmAgent
from google.genai import types
from loguru import logger

from voqalize.google_adk import AdkBrain
from voqalize.google_adk.testing import ScriptedLlm, reply

INSTRUCTION = "You are a front desk agent."


class _Capture:
    """A loguru sink that keeps the rendered lines, and removes itself."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self._id = logger.add(lambda m: self.lines.append(str(m)), level="DEBUG")

    def close(self) -> None:
        logger.remove(self._id)

    def __enter__(self) -> _Capture:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def _build(agent: LlmAgent) -> None:
    _ = AdkBrain(lambda: agent).agent


def test_a_default_gemini_agent_is_told_what_the_silence_costs() -> None:
    with _Capture() as cap:
        _build(LlmAgent(name="desk", model="gemini-3-flash-preview", instruction=INSTRUCTION))

    assert "thinking" in cap.text, cap.text
    assert "desk" in cap.text and "gemini-3-flash-preview" in cap.text, cap.text
    assert "thinking_budget=0" in cap.text, "the line must say what to set"


def test_an_explicit_thinking_config_is_the_deliberate_choice_and_stays_quiet() -> None:
    """Any thinking_config at all — budget zero, or a budget the agent genuinely
    wants. The point is that somebody decided."""
    for thinking in (
        types.ThinkingConfig(thinking_budget=0),
        types.ThinkingConfig(thinking_level="low"),
    ):
        with _Capture() as cap:
            _build(
                LlmAgent(
                    name="desk",
                    model="gemini-3-flash-preview",
                    instruction=INSTRUCTION,
                    generate_content_config=types.GenerateContentConfig(thinking_config=thinking),
                )
            )
        assert "thinking" not in cap.text, cap.text


def test_a_non_gemini_model_is_not_lectured_about_a_setting_it_does_not_have() -> None:
    with _Capture() as cap:
        _build(LlmAgent(name="desk", model="claude-opus-5", instruction=INSTRUCTION))

    assert "thinking" not in cap.text, cap.text


def test_a_model_instance_is_read_as_a_deliberate_choice() -> None:
    """A ``BaseLlm`` (a fake, a custom model) carries no config we can read, and
    guessing from its class name would be a lecture aimed at the wrong thing."""
    with _Capture() as cap:
        _build(
            LlmAgent(
                name="desk",
                model=ScriptedLlm({"__unused__": [reply("ok")]}),
                instruction=INSTRUCTION,
            )
        )

    assert "thinking" not in cap.text, cap.text
