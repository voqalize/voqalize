"""The messages between a brain and a page running Stage.

They ride the same two channels every typed action and app event already do —
``ui-command`` down, ``ui-event`` up — so a page keeps an unmodified pipecat
client. Generate the page's TypeScript from this module with
``voqalize types``; the two halves then cannot drift.

The wire carries no acknowledgement of its own, so every move has a
``call_ref`` the brain mints, and every move gets exactly one
:class:`StageResult` back with it — or, when none comes in time, the brain
records the outcome as ``unknown`` itself.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..actions import Action
from ..app_events import AppEvent, AppEvents

__all__ = [
    "STAGE_CONTRACT",
    "Outcome",
    "Refusal",
    "StageCue",
    "StageEvents",
    "StageHello",
    "StageMove",
    "StageResult",
]

#: The version of these messages and of the page runtime's contract. A page and
#: a brain that disagree on it say so at hello, before any move is sent.
STAGE_CONTRACT = 1

Outcome = Literal["applied", "partial", "refused", "failed", "undone", "unknown"]


class StageCue(Action, name="stage_cue"):
    """A move written inside the agent's reply, to make when the voice reaches it.

    ``at`` is the spoken text that follows the cue, as written, up to a few
    dozen characters: the page compares it with the words it hears, after
    segmenting both the same way, in whatever language the call is in. ``at``
    is empty for a cue at the very end of a reply, which fires when the voice
    stops. ``before`` counts the characters of the reply said before the cue,
    for a page that has to time cues by the clock."""

    call_ref: str
    move: str
    """The move's id, e.g. ``core.show``."""
    verb: str
    """The word the model wrote, e.g. ``show``."""
    args: list[str]
    """The cue's arguments, resolved to what the page offers."""
    at: str
    before: int
    unit: int = 0
    """Which stretch of speech of this turn the cue belongs to."""


class StageMove(Action, name="stage_move"):
    """A move made because a tool was called: the page makes it now, or, with
    ``when="quiet"``, once the voice has finished what it is saying."""

    call_ref: str
    move: str
    args: dict[str, str | int | float | bool | list[str] | None]
    when: Literal["now", "quiet"] = "now"


class Refusal(BaseModel):
    """One argument the page could not use, and what it offers instead."""

    model_config = ConfigDict(extra="forbid")

    arg: str
    why: str
    options: list[str] = []


class StageResult(AppEvent, name="stage_result"):
    """What happened to one move: sent exactly once per ``call_ref``."""

    call_ref: str
    move: str
    outcome: Outcome
    detail: str | None = None
    """What the page did, in words the model can repeat: "King applied; 8 products"."""
    refused: list[Refusal] = []  # noqa: RUF012 -- a pydantic field, copied per instance
    moved: bool = False
    """The move went on to another page, which finishes it and reports again."""
    ms: int = 0


class StageHello(AppEvent, name="stage_hello"):
    """A page running Stage, saying what it is — on connect and on every load."""

    runtime: str
    contract: int
    url: str = ""
    title: str = ""


StageEvents = AppEvents(StageResult, StageHello)
