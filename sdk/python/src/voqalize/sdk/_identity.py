"""Who a session is for, as the connection's signed token said.

:func:`~voqalize.sdk.run_session` verifies the token before the brain exists, and
the :class:`~voqalize.sdk.Session` it hands the brain is built later, inside the
session's own tasks. A ``ContextVar`` carries the verified identity across that
gap: an ``asyncio.Task`` copies the ambient context when it is created, so every
task the session starts sees what ``run_session`` set, and nothing else does.

The organization was called a *tenant* until 0.16.0. Every ``tenant_id`` the SDK
still accepts or exposes is a deprecated alias for ``organization_id``, kept for
two weeks after the organization switch and removed in 0.17.0.
"""

from __future__ import annotations

import warnings
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

#: When every ``tenant_id`` alias goes. Named once so the warnings and docs
#: cannot disagree.
# RENAME-CLEANUP: drop this constant with every tenant_id alias in 0.17.0.
TENANT_ALIAS_REMOVAL = "removed in 0.17.0, two weeks after the organization switch"


# RENAME-CLEANUP: drop warn_tenant_alias with every tenant_id alias.
def warn_tenant_alias(where: str, *, stacklevel: int = 3) -> None:
    """Emit the one ``DeprecationWarning`` every ``tenant_id`` alias raises."""
    warnings.warn(
        f"{where}: tenant_id is deprecated, use organization_id (the tenant is now "
        f"called an organization). The alias is {TENANT_ALIAS_REMOVAL}.",
        DeprecationWarning,
        stacklevel=stacklevel,
    )


def resolve_organization_kwarg(
    where: str, organization_id: str | None, tenant_id: str | None, default: str
) -> str:
    """Pick ``organization_id``, falling back to the deprecated ``tenant_id=`` keyword.

    Passing both is an error unless they agree: two different organizations is a
    bug in the caller, and silently picking one hides it."""
    if tenant_id is not None:  # RENAME-CLEANUP: drop the tenant_id= keyword alias
        warn_tenant_alias(where, stacklevel=4)
        if organization_id is not None and organization_id != tenant_id:
            raise TypeError(f"{where}: pass organization_id or tenant_id, not two different values")
        return tenant_id if organization_id is None else organization_id
    return default if organization_id is None else organization_id


def organization_claim(claims: dict[str, Any]) -> str:
    """The organization a verified token names.

    Reads ``organization_id``, falling back to ``tenant_id``: Voqalize's tokens
    carried only ``tenant_id`` before the rename, and the brain token carries
    both for two weeks after it."""
    value = claims.get("organization_id")
    if not value:  # RENAME-CLEANUP: drop the tenant_id claim fallback
        value = claims.get("tenant_id", "")
    return str(value or "")


@dataclass(frozen=True)
class VerifiedIdentity:
    """The organization and agent a connection's token was signed for."""

    organization_id: str
    agent_id: str

    # RENAME-CLEANUP: drop the VerifiedIdentity.tenant_id alias
    @property
    def tenant_id(self) -> str:
        """Deprecated alias for :attr:`organization_id`."""
        warn_tenant_alias("VerifiedIdentity.tenant_id")
        return self.organization_id


verified_identity: ContextVar[VerifiedIdentity | None] = ContextVar(
    "voqalize_verified_identity", default=None
)
