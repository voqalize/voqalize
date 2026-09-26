"""The harness, checked against itself: the rules every demo test runs under
fail when they should, and the scripted model behaves as the loop expects.

The brain here is not a demo. It is the smallest ``GeminiBrain`` with a tool
that dispatches to the screen and one that is slow, so each property is the only
thing its test can fail on.

Run: ``cd demos && uv run pytest tests/test_harness.py``
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from voqalize_demos import GeminiBrain
from voqalize_demos.testing import ScriptedGemini, reply, reply_and_call

from voqalize.sdk import Session
from voqalize.sdk.gemini import TOOL_BUDGET_MS

from ._harness import check_turn, demo_from, tools_within_budget


class _Probe(GeminiBrain):
    def __init__(self, client: Any) -> None:
        super().__init__(client=client, system_instruction="Be brief.")

    async def greet(self, session: Session) -> str | None:
        return "Hi."

    @property
    def tools(self) -> list[Any]:
        return [self.open_panel, self.crawl]

    async def open_panel(self) -> str:
        """Open the panel."""
        return "opened"

    async def crawl(self) -> str:
        """Take far longer than a tool may."""
        await asyncio.sleep(TOOL_BUDGET_MS * 3 / 1000)
        return "done"


async def test_a_slow_tool_fails_the_test() -> None:
    llm = ScriptedGemini({"Go slowly.": reply_and_call("On it.", "crawl")})
    with pytest.raises(AssertionError, match=r"_Probe\.crawl took \d+ms"):
        with tools_within_budget():
            async with demo_from("probe", lambda: _Probe(llm)) as rig:
                await rig.driver.start_session()
                await rig.driver.user_says("Go slowly.")


async def test_a_fast_tool_passes() -> None:
    llm = ScriptedGemini({"Open it.": reply_and_call("Opening it.", "open_panel")})
    with tools_within_budget() as slow:
        async with demo_from("probe", lambda: _Probe(llm)) as rig:
            await rig.driver.start_session()
            await rig.driver.user_says("Open it.")
    assert slow == []


async def test_a_turn_that_only_acknowledges_ends_after_one_request() -> None:
    """The reply scripted after the call is not played in that turn: an
    unmarked tool's result waits for the user's next message."""
    llm = ScriptedGemini(
        {"Open it.": [reply_and_call("Opening it.", "open_panel"), reply("Never said.")]}
    )
    async with demo_from("probe", lambda: _Probe(llm)) as rig:
        await rig.driver.start_session()
        turn = await rig.driver.user_says("Open it.")
        check_turn(rig, turn, units=1)
        assert turn.text == "Opening it."
    assert len(llm.calls) == 1
