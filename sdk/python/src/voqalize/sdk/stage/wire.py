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

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from ..actions import Action
from ..app_events import AppEvent, AppEvents

__all__ = [
    "STAGE_CONTRACT",
    "By",
    "Fired",
    "Outcome",
    "Phase",
    "Refusal",
    "StageCue",
    "StageEvent",
    "StageEvents",
    "StageHello",
    "StageMove",
    "StagePageEvents",
    "StageProgress",
    "StageResult",
]

#: The version of these messages and of the page runtime's contract. A page and
#: a brain that disagree on it say so at hello, before any move is sent.
STAGE_CONTRACT = 1

Outcome = Literal["applied", "partial", "refused", "failed", "undone", "unknown"]

#: How a move was set off: a cue by its words (``anchor``; ``fuzzy``, two words
#: of three), by the clock (``clock``), or when the voice stopped (``end``); a
#: tool's move at once (``now``) or once the voice was quiet (``quiet``).
Fired = Literal["anchor", "fuzzy", "clock", "end", "now", "quiet"]

#: Where a move is, before its result: waiting its turn (``queued``), waiting
#: for a page to load (``loading``), waiting for the site's own scripts
#: (``waiting_site``), ringing its target (``ringing``), acting (``acting``), or
#: checking that what it did took (``confirming``).
Phase = Literal["queued", "loading", "waiting_site", "ringing", "acting", "confirming"]

#: Who did an act: the person at the screen, or the agent through a move.
By = Literal["visitor", "agent"]


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
    """How long the move itself took on the page that finished it."""
    fired: Fired | None = None
    """How the move was set off. Absent from a page that does not say."""
    received_ms: int | None = None
    """Milliseconds from the page receiving the move to this result."""
    queued_ms: int | None = None
    """Milliseconds from receipt to the move being set off (a cue: its words
    heard; a quiet move: the voice quiet) and queued to run."""
    fired_ms: int | None = None
    """Milliseconds from receipt to the move starting to act."""
    ringed_ms: int | None = None
    """Milliseconds from receipt to its first ring; absent when it rang nothing."""
    lag_ms: int | None = None
    """A cue's start minus when its words were heard: how far the screen ran
    behind the voice."""
    late: bool = False
    """Set by the brain's director, never the page: this result came after the
    move had already been reported ``unknown``, and corrects it."""


class StageProgress(AppEvent, name="stage_progress"):
    """Where a move is, before its result: never final, sent as its phase
    changes. Each one tells the brain the move is alive, so a move that is
    slow is not taken for one that failed."""

    call_ref: str
    move: str
    phase: Phase
    ms: int = 0
    """Milliseconds since the page received the move."""


class StageHello(AppEvent, name="stage_hello"):
    """A page running Stage, saying what it is — on connect and on every load."""

    runtime: str
    contract: int
    url: str = ""
    title: str = ""


class StageEvent(AppEvent, name="stage_event"):
    """A named act that changed one slice of the page's state
    (``cart.changed``, ``listing.filtered``), as the app's Stage Spec declares
    it. Only the fields the slice declares, and none it marks private, are
    sent; the brain folds them into its mirror and tells the model one short
    line, never the values."""

    name: str
    """The event's id in the spec."""
    by: By = "visitor"
    data: dict[str, Any] = {}  # noqa: RUF012 -- a pydantic field, copied per instance
    """The slice's new value (``set``), the fields that changed (``merge``), or
    nothing (``clear``)."""
    call_ref: str | None = None
    """The move that caused it, when the agent did."""


#: A page's results and hello: what a brain written before progress parses.
StageEvents = AppEvents(StageResult, StageHello)
#: Everything a page running Stage sends: results, hello, progress and state events.
StagePageEvents = AppEvents(StageResult, StageHello, StageProgress, StageEvent)
