"""What happened in the studio — the browser→brain half of the screen contract.

The other direction is the :class:`~voqalize.sdk.Action` classes in ``brain.py``:
a declared shape whose wire name comes off the class name, validated at the call
site, with a generated TypeScript twin. :class:`~voqalize.sdk.AppEvent` is that,
mirrored — so ``on_rtvi`` narrows on a *type* rather than being handed the whole
workspace and left to work out what moved in it.

Forge is the demo where the browser→brain direction is not only "the human did
something". Two kinds of thing arrive here, and they read differently on purpose:

  * **the admin's own hand** — they opened a workflow, switched panels, clicked a
    block. Ada is told *that* they did, never what the screen now says.
  * **the studio's own answer** — a test run finishing, the coverage linter
    replying, a persona run coming to rest, a publish minting a run id. Nobody
    decided these; the interpreter computed them, and it is the only thing that
    can. They carry their result, because there is nowhere else Ada could get it
    (see ``ScreenState.happened``, which is why that method exists).

There is no "studio opened" event. The workflow catalog is in ``session.init``
before the first word, so Ada builds her picture from what she was handed rather
than asking the browser to hand it back.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk import AppEvent, AppEvents

__all__ = [
    "FORGE_EVENTS",
    "BlockFocused",
    "CodeOpened",
    "CoverageScanned",
    "ForgeEvent",
    "GapSpec",
    "ListOpened",
    "PanelOpened",
    "ScenarioFinished",
    "TestOutcome",
    "TestsFinished",
    "WorkflowOpened",
    "WorkflowPublished",
]


class TestOutcome(BaseModel):
    """One test as the interpreter settled it."""

    name: str
    passed: bool
    rested_at: str = Field("", description="Where the run actually came to rest.")


class GapSpec(BaseModel):
    """One unhandled ``(state, event)`` pair the coverage linter found."""

    state: str
    event: str
    question: str = ""


# ─── The admin's own hand ──────────────────────────────────────────────────────


class ListOpened(AppEvent):
    """The admin went back to the workflow list. Nothing is open."""


class WorkflowOpened(AppEvent):
    """The admin opened a workflow themselves, off the list."""

    id: str


class PanelOpened(AppEvent):
    """The admin switched panels on the open workflow."""

    panel: Literal["flow", "code", "tests", "runtime"]


class BlockFocused(AppEvent):
    """The admin selected a block — which one they are pointing at, not a change."""

    id: str


class CodeOpened(AppEvent):
    """The admin opened one block's code."""

    id: str


# ─── The studio's own answer ───────────────────────────────────────────────────


class TestsFinished(AppEvent):
    """A ``run_tests`` came back. The outcomes are the interpreter's, on its own
    clock, and arrive only here — there is no other way for Ada to learn them."""

    tests: list[TestOutcome] = Field(default_factory=list)


class CoverageScanned(AppEvent):
    """A ``review_coverage`` came back. The gaps are read off the spec by the
    studio's interpreter, so a question Ada never thought to ask still shows up —
    which is the whole point of the linter, and why this is an event and not a
    tool result."""

    gaps: list[GapSpec] = Field(default_factory=list)


class ScenarioFinished(AppEvent):
    """A persona run finished walking the flow — where it came to rest."""

    persona: str = ""
    rested_at: str = ""


class WorkflowPublished(AppEvent):
    """The publish landed: the version that went live and the run id it minted."""

    id: str
    version: int = 0
    run_id: str = ""


type ForgeEvent = (
    ListOpened
    | WorkflowOpened
    | PanelOpened
    | BlockFocused
    | CodeOpened
    | TestsFinished
    | CoverageScanned
    | ScenarioFinished
    | WorkflowPublished
)

FORGE_EVENTS = AppEvents[ForgeEvent](
    ListOpened,
    WorkflowOpened,
    PanelOpened,
    BlockFocused,
    CodeOpened,
    TestsFinished,
    CoverageScanned,
    ScenarioFinished,
    WorkflowPublished,
)
