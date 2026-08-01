"""Voice-protocol conformance harness — a protocol-compliant "voqalize" that
drives a brain over the wire and checks it against the MUSTs.

This package *is* the compatibility test bench: :class:`VoiceDriver` impersonates
PyGato/Voice on the single-session ``/s/{session_id}`` direct leg, speaks the
shipped ``Vql*`` protobuf wire, models playout/heard-truth finalization the way
real Voice does, and records everything the brain sends back. On top of it sit a
named :data:`~voqalize.conformance.scenarios.CATALOG` of scenarios and the
:mod:`~voqalize.conformance.checks` library of protocol assertions. Run the
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
    GREETING_INTERACTION_ID,
    InferenceObs,
    InteractionObs,
    Turn,
    VoiceDriver,
)
from .reference import ConformanceBrain, conformance_state
from .report import Report, ScenarioResult, run_suite
from .scenarios import CATALOG, Scenario, ScenarioContext, catalog
from .wire_pygato import (
    DirectConnection,
    Keypair,
    decode_upstream,
    generate_keypair,
    mint_pygato_token,
)

__all__ = [
    "CATALOG",
    "CONFORMANCE_DUMP_EVENT",
    "CONFORMANCE_STATE_ACTION",
    "GREETING_INTERACTION_ID",
    "ConformanceBrain",
    "ConformanceError",
    "DirectConnection",
    "InferenceObs",
    "InteractionObs",
    "Keypair",
    "Report",
    "Scenario",
    "ScenarioContext",
    "ScenarioResult",
    "Turn",
    "VoiceDriver",
    "catalog",
    "conformance_state",
    "decode_upstream",
    "generate_keypair",
    "mint_pygato_token",
    "run_suite",
]
