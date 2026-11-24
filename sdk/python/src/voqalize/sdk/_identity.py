"""Who a session is for, as the connection's signed token said.

:func:`~voqalize.sdk.run_session` verifies the token before the brain exists, and
the :class:`~voqalize.sdk.Session` it hands the brain is built later, inside the
session's own tasks. A ``ContextVar`` carries the verified identity across that
gap: an ``asyncio.Task`` copies the ambient context when it is created, so every
task the session starts sees what ``run_session`` set, and nothing else does.

A session is identified by its agent: ``agent_id`` is globally unique, and an
agent belongs to exactly one account. The SDK no longer exposes the account.
Every ``tenant_id`` it still accepts or exposes is deprecated, kept for two
weeks after the organization switch and removed in 0.17.0.
"""

from __future__ import annotations

import warnings
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

# RENAME-CLEANUP: drop this constant with every tenant_id alias.
#: The release that removes every ``tenant_id`` alias, two weeks after the
#: organization switch. Named once so the warnings cannot disagree.
TENANT_ALIAS_REMOVAL = "0.17.0"


# RENAME-CLEANUP: drop warn_tenant_alias with every tenant_id alias.
def warn_tenant_alias(where: str, *, stacklevel: int = 3) -> None:
    """Emit the one ``DeprecationWarning`` every ``tenant_id`` alias raises."""
    warnings.warn(
        f"{where}: tenant_id is deprecated, use agent_id; the SDK no longer "
        f"exposes the account (removed in {TENANT_ALIAS_REMOVAL}).",
        DeprecationWarning,
        stacklevel=stacklevel,
    )


# RENAME-CLEANUP: drop the tenant_id= keyword alias.
def deprecated_tenant_kwarg(where: str, tenant_id: str | None) -> str | None:
    """Warn once if the deprecated ``tenant_id=`` keyword was passed; return it."""
    if tenant_id is not None:
        warn_tenant_alias(where, stacklevel=4)
    return tenant_id


# RENAME-CLEANUP: drop with Session.tenant_id and the tenant_id log field.
def account_claim(claims: dict[str, Any]) -> str:
    """The account a verified token names, for the deprecated ``tenant_id``
    surfaces only: the ``organization_id`` claim, falling back to ``tenant_id``
    (a platform from before the rename)."""
    value = claims.get("organization_id") or claims.get("tenant_id") or ""
    return str(value)


@dataclass(frozen=True)
class VerifiedIdentity:
    """The agent a connection's token was signed for."""

    agent_id: str
    # RENAME-CLEANUP: the account, kept only to serve the deprecated tenant_id.
    account: str = field(default="", repr=False)

    # RENAME-CLEANUP: drop the VerifiedIdentity.tenant_id alias
    @property
    def tenant_id(self) -> str:
        """Deprecated: use :attr:`agent_id`; the SDK no longer exposes the account."""
        warn_tenant_alias("VerifiedIdentity.tenant_id")
        return self.account


verified_identity: ContextVar[VerifiedIdentity | None] = ContextVar(
    "voqalize_verified_identity", default=None
)
