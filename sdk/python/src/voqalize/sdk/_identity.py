"""Who a session is for, as the connection's signed token said.

:func:`~voqalize.sdk.run_session` verifies the token before the brain exists, and
the :class:`~voqalize.sdk.Session` it hands the brain is built later, inside the
session's own tasks. A ``ContextVar`` carries the verified identity across that
gap: an ``asyncio.Task`` copies the ambient context when it is created, so every
task the session starts sees what ``run_session`` set, and nothing else does.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class VerifiedIdentity:
    """The workspace and agent a connection's token was signed for."""

    tenant_id: str
    agent_id: str


verified_identity: ContextVar[VerifiedIdentity | None] = ContextVar(
    "voqalize_verified_identity", default=None
)
