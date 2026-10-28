"""Stage: an agent that shows and does things on a screen while it talks.

The model writes moves into its reply — ``{show: Rooms}`` — and the page makes
each one when the voice reaches its words; moves that change what a person owns
are tools, behind a confirmation. Every move has a class that decides how it
behaves, every move is ringed on screen before it acts, and every move answers
with one :class:`StageResult`.

Not part of ``voqalize.sdk.__all__``: import it as ``voqalize.sdk.stage``.
"""

from __future__ import annotations

from .cues import MAX_CUE, AutoCue, AutoCues, CheckCue, CueParser, RawCue
from .director import (
    CUE_WAIT_S,
    FINISHED_KEEP_S,
    HOLDING_LINE_S,
    RESULT_TIMEOUTS,
    ArgValue,
    Dropped,
    OnDrop,
    OnProgress,
    Refused,
    Resolve,
    Running,
    Stage,
)
from .labels import fold, match_label
from .moves import MAX_ARGS, Move, MoveSet
from .policy import POLICY, Delivery, MoveClass, Policy, cueable
from .wire import (
    STAGE_CONTRACT,
    Fired,
    Outcome,
    Phase,
    Refusal,
    StageCue,
    StageEvents,
    StageHello,
    StageMove,
    StagePageEvents,
    StageProgress,
    StageResult,
)

__all__ = [
    "CUE_WAIT_S",
    "FINISHED_KEEP_S",
    "HOLDING_LINE_S",
    "MAX_ARGS",
    "MAX_CUE",
    "POLICY",
    "RESULT_TIMEOUTS",
    "STAGE_CONTRACT",
    "ArgValue",
    "AutoCue",
    "AutoCues",
    "CheckCue",
    "CueParser",
    "Delivery",
    "Dropped",
    "Fired",
    "Move",
    "MoveClass",
    "MoveSet",
    "OnDrop",
    "OnProgress",
    "Outcome",
    "Phase",
    "Policy",
    "RawCue",
    "Refusal",
    "Refused",
    "Resolve",
    "Running",
    "Stage",
    "StageCue",
    "StageEvents",
    "StageHello",
    "StageMove",
    "StagePageEvents",
    "StageProgress",
    "StageResult",
    "cueable",
    "fold",
    "match_label",
]
