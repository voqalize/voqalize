"""Who a session is for, as the connection's signed token said.

:func:`~voqalize.sdk.run_session` verifies the token before the brain exists, and
the :class:`~voqalize.sdk.Session` it hands the brain is built later, inside the
session's own tasks. A ``ContextVar`` carries the verified identity across that
gap: an ``asyncio.Task`` copies the ambient context when it is created, so every
task the session starts sees what ``run_session`` set, and nothing else does.

The workspace was called a *tenant* until 0.15.0. Every ``tenant_id`` the SDK
still accepts or exposes is a deprecated alias for ``workspace_id``, kept for
about 90 days and removed in the first minor release on or after 2027-02-15.
"""

from __future__ import annotations

import warnings
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

#: The date on or after which the first minor release drops every ``tenant_id``
#: alias. Named once so the warnings cannot disagree.
TENANT_ALIAS_REMOVAL = "2027-02-15"


def warn_tenant_alias(where: str, *, stacklevel: int = 3) -> None:
    """Emit the one ``DeprecationWarning`` every ``tenant_id`` alias raises."""
    warnings.warn(
        f"{where}: tenant_id is deprecated, use workspace_id (the tenant is now "
        f"called a workspace). The alias is removed in the first minor release "
        f"on or after {TENANT_ALIAS_REMOVAL}.",
        DeprecationWarning,
        stacklevel=stacklevel,
    )


def resolve_workspace_kwarg(
    where: str, workspace_id: str | None, tenant_id: str | None, default: str
) -> str:
    """Pick ``workspace_id``, falling back to the deprecated ``tenant_id=`` keyword.

    Passing both is an error unless they agree: two different workspaces is a
    bug in the caller, and silently picking one hides it."""
    if tenant_id is not None:
        warn_tenant_alias(where, stacklevel=4)
        if workspace_id is not None and workspace_id != tenant_id:
            raise TypeError(f"{where}: pass workspace_id or tenant_id, not two different values")
        return tenant_id if workspace_id is None else workspace_id
    return default if workspace_id is None else workspace_id


def workspace_claim(claims: dict[str, Any]) -> str:
    """The workspace a verified token names.

    Reads ``workspace_id``, falling back to ``tenant_id``: Voqalize's tokens
    carried only ``tenant_id`` before the rename, and the brain token carries
    both for about 90 days after it."""
    value = claims.get("workspace_id")
    if not value:
        value = claims.get("tenant_id", "")
    return str(value or "")


@dataclass(frozen=True)
class VerifiedIdentity:
    """The workspace and agent a connection's token was signed for."""

    workspace_id: str
    agent_id: str

    @property
    def tenant_id(self) -> str:
        """Deprecated alias for :attr:`workspace_id`."""
        warn_tenant_alias("VerifiedIdentity.tenant_id")
        return self.workspace_id


verified_identity: ContextVar[VerifiedIdentity | None] = ContextVar(
    "voqalize_verified_identity", default=None
)
