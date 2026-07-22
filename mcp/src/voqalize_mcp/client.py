"""Async client over the Voqalize control-plane management API.

Thin wrapper around ``httpx.AsyncClient`` that speaks the control plane's
RPC-over-HTTP convention (``POST/GET /api/v1/{tenant}/operation.name``) with a
management key (``mk_…``) as ``Authorization: Bearer``. Every method maps to one
control-plane route; nothing here interprets the platform's domain model beyond
the read-modify-write helper for ``set_brain_url``.

Two control-plane conventions this client encodes:

- **Mutations need an ``Idempotency-Key``.** The ``agents.*`` write routes run on
  ``MutationCommandRoute`` and reject a missing key with 400. We mint a fresh
  uuid4 per call — the MCP tools are one-shot, so we never need replay semantics.
  (The ``api_keys.*`` routes are *not* mutations in that pipeline and take no key.)
- **Errors use a standard envelope** — ``{"error": {"code", "message"}, ...}`` for
  ``AppError``, or FastAPI's ``{"detail": ...}`` for request-validation failures.
  ``_raise_for_status`` unwraps whichever is present into a ``ControlPlaneError``.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx

from voqalize_mcp.config import Config


class ControlPlaneError(RuntimeError):
    """A non-2xx response from the control plane.

    ``status`` is the HTTP code; ``code`` is the platform error code when the
    body carried one (e.g. ``not_authorized``, ``validation_error``).
    """

    def __init__(self, status: int, message: str, *, code: str | None = None):
        self.status = status
        self.code = code
        super().__init__(f"[{status}{f' {code}' if code else ''}] {message}")


class ControlPlaneClient:
    """One instance per MCP-server process; wraps a shared ``AsyncClient``."""

    def __init__(self, config: Config, *, http: httpx.AsyncClient | None = None):
        self._config = config
        self._base = f"{config.api_base}/api/v1/{config.tenant}"
        self._http = http or httpx.AsyncClient(
            headers={"Authorization": f"Bearer {config.management_key}"},
            timeout=30.0,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    # ── low-level verbs ──────────────────────────────────────────────────────

    async def _get(self, operation: str, *, params: dict[str, Any] | None = None) -> Any:
        resp = await self._http.get(f"{self._base}/{operation}", params=_clean(params))
        return _unwrap(resp)

    async def _post(self, operation: str, *, json: dict[str, Any], idempotent: bool = False) -> Any:
        headers = {"Idempotency-Key": str(uuid.uuid4())} if idempotent else None
        resp = await self._http.post(f"{self._base}/{operation}", json=json, headers=headers)
        return _unwrap(resp)

    # ── whoami ───────────────────────────────────────────────────────────────

    async def whoami(self) -> dict[str, Any]:
        """Validate the management key and report the tenant it drives.

        There's no dedicated identity route for a machine credential, so we prove
        the key by listing agents (limit 1) — a successful read means the key is
        valid, unrevoked, and scoped to this tenant.
        """
        page = await self._get("agents.list", params={"limit": 1})
        return {
            "tenant": self._config.tenant,
            "api_base": self._config.api_base,
            "authenticated": True,
            "agent_count_hint": len(page.get("items", [])),
        }

    # ── agents ───────────────────────────────────────────────────────────────

    async def list_agents(
        self, *, status: str | None = None, cursor: str | None = None, limit: int = 20
    ) -> dict[str, Any]:
        return await self._get(
            "agents.list", params={"status": status, "cursor": cursor, "limit": limit}
        )

    async def get_agent(self, agent_id: str) -> dict[str, Any]:
        return await self._get("agents.get", params={"agent_id": agent_id})

    async def create_agent(
        self,
        *,
        name: str,
        description: str | None = None,
        brain_url: str | None = None,
        key: str | None = None,
    ) -> dict[str, Any]:
        """Create an agent, optionally pinning its ``brain_url`` at creation.

        Returns the full ``CreateAgentResponse`` — ``{agent, agent_secret,
        cortex_url}``. ``agent_secret`` (the raw ``ak_…``) is shown only here.
        """
        body: dict[str, Any] = {"name": name}
        if description is not None:
            body["description"] = description
        if key is not None:
            body["key"] = key
        if brain_url is not None:
            body["configuration"] = {"deployment": {"brain_url": brain_url}}
        return await self._post("agents.create", json=body, idempotent=True)

    async def update_agent(self, agent_id: str, **fields: Any) -> dict[str, Any]:
        body = {"agent_id": agent_id, **_clean(fields)}
        return await self._post("agents.update", json=body, idempotent=True)

    async def set_brain_url(self, agent_id: str, brain_url: str) -> dict[str, Any]:
        """Point an agent's brain at ``brain_url`` (read-modify-write).

        Preserves the agent's existing STT/TTS configuration and only swaps
        ``configuration.deployment.brain_url``.
        """
        agent = await self.get_agent(agent_id)
        configuration = dict(agent.get("configuration") or {})
        deployment = dict(configuration.get("deployment") or {})
        deployment["brain_url"] = brain_url
        configuration["deployment"] = deployment
        return await self.update_agent(agent_id, configuration=configuration)

    async def archive_agent(self, agent_id: str) -> dict[str, Any]:
        return await self._post("agents.archive", json={"agent_id": agent_id}, idempotent=True)

    # ── api keys ─────────────────────────────────────────────────────────────

    async def create_api_key(
        self,
        *,
        kind: str,
        label: str,
        allowed_origins: list[str] | None = None,
        role: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"kind": kind, "label": label}
        if allowed_origins is not None:
            body["allowed_origins"] = allowed_origins
        if role is not None:
            body["role"] = role
        return await self._post("api_keys.create", json=body)

    async def list_api_keys(self, *, include_revoked: bool = False) -> dict[str, Any]:
        return await self._get("api_keys.list", params={"include_revoked": include_revoked})

    async def revoke_api_key(self, key_id: str) -> dict[str, Any]:
        return await self._post("api_keys.revoke", json={"key_id": key_id})


def _clean(params: dict[str, Any] | None) -> dict[str, Any]:
    """Drop ``None`` values so we don't send empty query args / patch fields."""
    if not params:
        return {}
    return {k: v for k, v in params.items() if v is not None}


def _unwrap(resp: httpx.Response) -> Any:
    _raise_for_status(resp)
    if not resp.content:
        return {}
    return resp.json()


def _raise_for_status(resp: httpx.Response) -> None:
    if resp.is_success:
        return
    code: str | None = None
    message = resp.text
    try:
        body = resp.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):  # platform AppError envelope
            code = err.get("code")
            message = err.get("message", message)
        elif "detail" in body:  # FastAPI request-validation shape
            message = _format_detail(body["detail"])
    raise ControlPlaneError(resp.status_code, message, code=code)


def _format_detail(detail: Any) -> str:
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):  # pydantic validation errors
        return "; ".join(
            f"{'.'.join(str(p) for p in e.get('loc', []))}: {e.get('msg', '')}".strip(": ")
            for e in detail
            if isinstance(e, dict)
        )
    return str(detail)
