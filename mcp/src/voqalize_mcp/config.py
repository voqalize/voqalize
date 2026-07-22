"""Environment-driven configuration for the Voqalize MCP server.

The server is a thin, non-interactive client over the Voqalize control-plane
management API. It authenticates with a **management key** (``mk_…``) minted
once in the console — see the control plane's ``api_keys.create`` with
``kind="management"``. That key resolves to a tenant role, so the MCP server
can create agents, set brain URLs, and mint publishable/secret keys exactly as
a console admin would, with no browser session.

Three environment variables drive it:

- ``VOQALIZE_MANAGEMENT_KEY`` — the ``mk_…`` key. **Required.**
- ``VOQALIZE_TENANT`` — the tenant slug the key belongs to. **Required.**
- ``VOQALIZE_API_BASE`` — control-plane base URL. Defaults to the local dev
  control plane (``http://localhost:8274``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_API_BASE = "http://localhost:8274"


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or malformed."""


@dataclass(frozen=True)
class Config:
    api_base: str
    tenant: str
    management_key: str

    @classmethod
    def from_env(cls) -> Config:
        management_key = os.environ.get("VOQALIZE_MANAGEMENT_KEY", "").strip()
        tenant = os.environ.get("VOQALIZE_TENANT", "").strip()
        api_base = os.environ.get("VOQALIZE_API_BASE", DEFAULT_API_BASE).strip() or DEFAULT_API_BASE

        if not management_key:
            raise ConfigError(
                "VOQALIZE_MANAGEMENT_KEY is not set. Mint a management key in the "
                "Voqalize console (API keys → kind 'management') and export it."
            )
        if not management_key.startswith("mk_"):
            raise ConfigError(
                "VOQALIZE_MANAGEMENT_KEY must be a management key (starts with 'mk_'). "
                "sk_/pk_ keys cannot drive the management API."
            )
        if not tenant:
            raise ConfigError("VOQALIZE_TENANT (your tenant slug) is not set.")

        return cls(
            api_base=api_base.rstrip("/"),
            tenant=tenant,
            management_key=management_key,
        )
