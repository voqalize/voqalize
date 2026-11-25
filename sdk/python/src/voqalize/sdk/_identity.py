"""Who a session is for, as the connection's signed token said.

:func:`~voqalize.sdk.run_session` verifies the token before the brain exists, and
the :class:`~voqalize.sdk.Session` it hands the brain is built later, inside the
session's own tasks. A ``ContextVar`` carries the verified identity across that
gap: an ``asyncio.Task`` copies the ambient context when it is created, so every
task the session starts sees what ``run_session`` set, and nothing else does.

A session is identified by its agent: ``agent_id`` is globally unique, and an
agent belongs to exactly one organization, which the SDK does not expose. 0.16.0
removed ``tenant_id`` everywhere; the names below turn a leftover use of it into
an error that says what to use instead.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

#: What every error for a removed ``tenant_id`` tells the caller to do instead.
TENANT_ID_REMOVED = "was removed in 0.16.0: identify calls by session.agent_id"


def reject_removed_kwargs(where: str, removed: dict[str, Any]) -> None:
    """Raise ``TypeError`` for keywords a function no longer takes, naming
    ``tenant_id=`` specifically, since that one has a replacement to point at."""
    if "tenant_id" in removed:
        raise TypeError(f"{where}(tenant_id=) {TENANT_ID_REMOVED}")
    if removed:
        name = next(iter(removed))
        raise TypeError(f"{where}() got an unexpected keyword argument {name!r}")


@dataclass(frozen=True)
class VerifiedIdentity:
    """The agent a connection's token was signed for."""

    agent_id: str


verified_identity: ContextVar[VerifiedIdentity | None] = ContextVar(
    "voqalize_verified_identity", default=None
)
