"""Sync tools are rejected loudly, before a call can fail on one.

ADK dispatches a *sync* tool on a thread pool, in a fresh context where the SDK's
``voice()`` ``ContextVar`` is unset — so ``voice().action(...)`` raises ``NoActiveVoice``
deep inside a live call, after the model already spoke, and the developer sees a
mid-conversation stack trace with no obvious cause. The adapter refuses instead, at the
moment the agent is built, with an error that names the offending tool and says what to
do. ``allow_sync_tools=True`` is the escape hatch for tools that never touch ``voice()``.
"""

from __future__ import annotations

import pytest

pytest.importorskip("google.adk")

from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.tools.function_tool import FunctionTool

from voqalize.google_adk import AdkBrain
from voqalize.google_adk.testing import ScriptedLlm, reply

INSTRUCTION = "You are a front desk agent."


async def open_dashboard() -> dict:
    """Open the dashboard."""
    return {"ok": True}


def show_receipt() -> dict:
    """Show the receipt (sync — would lose voice())."""
    return {"ok": True}


def _agent(model: str | BaseLlm, tools: list) -> LlmAgent:
    return LlmAgent(name="desk", model=model, instruction=INSTRUCTION, tools=tools)


def _llm() -> ScriptedLlm:
    return ScriptedLlm({"__unused__": [reply("ok")]})


def test_a_sync_tool_is_rejected_and_named() -> None:
    """The error names the tool and explains the async requirement — not a generic
    ValueError the developer has to decode."""
    brain = AdkBrain(lambda: _agent(_llm(), [open_dashboard, show_receipt]))
    with pytest.raises(ValueError) as excinfo:
        _ = brain.agent
    message = str(excinfo.value)
    assert "show_receipt" in message, message
    assert "open_dashboard" not in message, "an async tool must not be blamed"
    assert "voice()" in message and "async" in message, message


def test_a_sync_tool_wrapped_in_functiontool_is_rejected_too() -> None:
    """Wrapping the function in ADK's ``FunctionTool`` yourself doesn't hide it — the
    check reads the wrapped ``func``."""
    brain = AdkBrain(lambda: _agent(_llm(), [FunctionTool(show_receipt)]))
    with pytest.raises(ValueError, match="show_receipt"):
        _ = brain.agent


def test_async_tools_build_cleanly() -> None:
    """The common case stays silent."""
    brain = AdkBrain(lambda: _agent(_llm(), [open_dashboard]))
    assert brain.agent.name == "desk"


def test_allow_sync_tools_is_the_escape_hatch() -> None:
    """A tool that never calls ``voice()`` can opt out explicitly."""
    brain = AdkBrain(lambda: _agent(_llm(), [show_receipt]), allow_sync_tools=True)
    assert brain.agent.name == "desk"
