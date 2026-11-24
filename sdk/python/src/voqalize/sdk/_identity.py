"""Who a session is for, as the connection's signed token said.

:func:`~voqalize.sdk.run_session` verifies the token before the brain exists, and
the :class:`~voqalize.sdk.Session` it hands the brain is built later, inside the
session's own tasks. A ``ContextVar`` carries the verified identity across that
gap: an ``asyncio.Task`` copies the ambient context when it is created, so every
task the session starts sees what ``run_session`` set, and nothing else does.

The organization was called a *tenant* until 0.16.0; 0.17.0 removed every
``tenant_id`` alias, and a token's ``organization_id`` claim is the only one read.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any


def organization_claim(claims: dict[str, Any]) -> str:
    """The organization a verified token names: its ``organization_id`` claim."""
    return str(claims.get("organization_id") or "")


@dataclass(frozen=True)
class VerifiedIdentity:
    """The organization and agent a connection's token was signed for."""

    organization_id: str
    agent_id: str


verified_identity: ContextVar[VerifiedIdentity | None] = ContextVar(
    "voqalize_verified_identity", default=None
)
