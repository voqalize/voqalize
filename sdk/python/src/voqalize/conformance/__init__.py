"""Conformance harness — a wire-compliant stand-in for Voqalize that drives a
brain and checks it against the MUSTs.

This package *is* the compatibility test bench: :class:`VoqalizeDriver` stands in
for Voqalize on the single-session ``/s/{session_id}`` direct leg, speaks the
shipped protobuf wire, models playout/heard-truth finalization the way
real Voqalize does, and records everything the brain sends back. On top of it sit a
named :data:`~voqalize.conformance.scenarios.CATALOG` of scenarios and the
:mod:`~voqalize.conformance.checks` library of wire assertions. Run the
whole thing with :func:`~voqalize.conformance.report.run_suite`, or point the
CLI (``python -m voqalize.conformance``) at a running brain.

Passing this suite is the bar a brain — the SDK plus the customer's code — must
clear to be called voice-wire compatible. It is deliberately transport-narrow:
the direct leg only, because from a brain's point of view the Cortex relay is the
*same* per-session leg (only who-dials-whom differs).
"""

from __future__ import annotations

from .checks import ConformanceError
from .driver import (
    CONFORMANCE_DUMP_EVENT,
    CONFORMANCE_STATE_ACTION,
    GREETING_EPOCH,
    EpochObs,
    SpeechObs,
    Turn,
    VoqalizeDriver,
)
from .host import BrainServer, brain_server
from .reference import ConformanceBrain, conformance_state
from .report import Report, ScenarioResult, run_suite
from .scenarios import CATALOG, Scenario, ScenarioContext
from .wire_voqalize import (
    DirectConnection,
    Keypair,
    generate_keypair,
    mint_voqalize_token,
)

__all__ = [
    "CATALOG",
    "CONFORMANCE_DUMP_EVENT",
    "CONFORMANCE_STATE_ACTION",
    "GREETING_EPOCH",
    "BrainServer",
    "ConformanceBrain",
    "ConformanceError",
    "DirectConnection",
    "EpochObs",
    "Keypair",
    "Report",
    "Scenario",
    "ScenarioContext",
    "ScenarioResult",
    "SpeechObs",
    "Turn",
    "VoqalizeDriver",
    "brain_server",
    "conformance_state",
    "generate_keypair",
    "mint_voqalize_token",
    "run_suite",
]
