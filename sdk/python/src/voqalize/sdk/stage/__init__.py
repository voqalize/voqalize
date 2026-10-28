"""Stage: an agent that shows and does things on a screen while it talks.

The model writes moves into its reply — ``{show: Rooms}`` — and the page makes
each one when the voice reaches its words; moves that change what a person owns
are tools, behind a confirmation. Every move has a class that decides how it
behaves, every move is ringed on screen before it acts, and every move answers
with one :class:`StageResult`.

Not part of ``voqalize.sdk.__all__``: import it as ``voqalize.sdk.stage``.
"""

from __future__ import annotations

from .cues import MAX_CUE, AutoCues, CueParser, RawCue
from .director import (
    CUE_WAIT_S,
    RESULT_TIMEOUTS,
    ArgValue,
    Dropped,
    OnDrop,
    Refused,
    Resolve,
    Stage,
)
from .labels import fold, match_label
from .moves import MAX_ARGS, Move, MoveSet
from .policy import POLICY, Delivery, MoveClass, Policy, cueable
from .wire import (
    STAGE_CONTRACT,
    Outcome,
    Refusal,
    StageCue,
    StageEvents,
    StageHello,
    StageMove,
    StageResult,
)

__all__ = [
    "CUE_WAIT_S",
    "MAX_ARGS",
    "MAX_CUE",
    "POLICY",
    "RESULT_TIMEOUTS",
    "STAGE_CONTRACT",
    "ArgValue",
    "AutoCues",
    "CueParser",
    "Delivery",
    "Dropped",
    "Move",
    "MoveClass",
    "MoveSet",
    "OnDrop",
    "Outcome",
    "Policy",
    "RawCue",
    "Refusal",
    "Refused",
    "Resolve",
    "Stage",
    "StageCue",
    "StageEvents",
    "StageHello",
    "StageMove",
    "StageResult",
    "cueable",
    "fold",
    "match_label",
]
