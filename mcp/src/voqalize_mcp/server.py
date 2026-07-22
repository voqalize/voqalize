"""The Voqalize MCP server — management tools for a developer's Claude Code.

A stdio MCP server the customer's Claude Code connects to. It holds one
management key (``mk_…``) and exposes the control-plane management API as MCP
tools, mapped ~1:1 onto routes: create/inspect agents, point an agent's brain at
a WebSocket URL, and mint/revoke the runtime keys (``pk_`` for the browser,
``ak_`` returned at agent creation for a Cortex brain).

The developer flow this serves: describe a use case to Claude Code → it scaffolds
a brain (Python SDK), decides cortex-vs-direct, **creates the agent here**, wires
``brain_url``, and hands back a ``pk_`` for the React embed. Observability
(``tail_logs`` / ``get_metrics``) is deliberately absent — that layer is owned by
a separate track and will register its own tools.

Every tool returns plain dicts (the control plane's JSON), so Claude Code sees
the raw resource. Errors surface as ``ControlPlaneError`` with the platform code
(``not_authorized`` → the key's role is too low, ``validation_error`` → bad
input), which the MCP runtime relays to the model as the tool result.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from voqalize_mcp.client import ControlPlaneClient
from voqalize_mcp.config import Config

_INSTRUCTIONS = """\
Voqalize management tools. You are helping a developer build a voice agent on
Voqalize: they bring the brain (a WebSocket URL), Voqalize brings the voice.

Typical flow:
  1. `whoami` to confirm the tenant this key drives.
  2. `create_agent` (optionally with a brain_url). The response includes an
     `agent_secret` (ak_…) — only needed if the brain connects OUT via Cortex.
  3. Build the brain with the Voqalize Python SDK. For an inbound WebSocket the
     brain accepts (the primary path), set `brain_url` to that wss:// URL via
     `set_brain_url`. For a Cortex relay brain, use the returned `cortex_url`.
  4. `create_api_key` with kind="publishable" for the browser (React SDK); pass
     the site origin(s) in allowed_origins.

brain_url must be wss:// (ws:// only for localhost). An empty brain_url falls
back to the hosted `welcome` demo brain, so a fresh agent still greets."""


def build_server(
    config: Config | None = None, *, client: ControlPlaneClient | None = None
) -> FastMCP:
    config = config or Config.from_env()
    client = client or ControlPlaneClient(config)
    mcp = FastMCP("voqalize", instructions=_INSTRUCTIONS)

    @mcp.tool()
    async def whoami() -> dict[str, Any]:
        """Confirm the management key is valid and report the tenant it drives."""
        return await client.whoami()

    @mcp.tool()
    async def list_agents(status: str | None = None, limit: int = 20) -> dict[str, Any]:
        """List the tenant's agents. Optional status filter: draft|active|archived."""
        return await client.list_agents(status=status, limit=limit)

    @mcp.tool()
    async def get_agent(agent_id: str) -> dict[str, Any]:
        """Fetch one agent, including its configuration (STT/TTS + brain_url)."""
        return await client.get_agent(agent_id)

    @mcp.tool()
    async def create_agent(
        name: str,
        description: str | None = None,
        brain_url: str | None = None,
    ) -> dict[str, Any]:
        """Create an agent. Returns {agent, agent_secret (ak_…, shown once), cortex_url}.

        Pass brain_url (wss://, or ws:// for localhost) to pin the brain now, or
        leave it and call set_brain_url later. agent_secret is only needed for a
        Cortex (outbound) brain; an inbound brain never uses it.
        """
        return await client.create_agent(name=name, description=description, brain_url=brain_url)

    @mcp.tool()
    async def set_brain_url(agent_id: str, brain_url: str) -> dict[str, Any]:
        """Point an agent's brain at a WebSocket URL, preserving its STT/TTS config.

        brain_url must be wss:// (ws:// permitted only for localhost dev). PyGato
        dials it as `{brain_url}/s/{session_id}`, one connection per session.
        """
        return await client.set_brain_url(agent_id, brain_url)

    @mcp.tool()
    async def update_agent(
        agent_id: str,
        name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Rename or re-describe an agent. To change the brain, use set_brain_url."""
        return await client.update_agent(agent_id, name=name, description=description)

    @mcp.tool()
    async def archive_agent(agent_id: str) -> dict[str, Any]:
        """Archive an agent (soft delete — it stops serving new sessions)."""
        return await client.archive_agent(agent_id)

    @mcp.tool()
    async def create_api_key(
        kind: str,
        label: str,
        allowed_origins: list[str] | None = None,
    ) -> dict[str, Any]:
        """Mint a runtime key. kind="publishable" (pk_, browser/React — pass
        allowed_origins) or "secret" (sk_, backend). The raw key is in `raw`,
        shown only once. (Management keys can't be minted here — that needs owner.)
        """
        return await client.create_api_key(kind=kind, label=label, allowed_origins=allowed_origins)

    @mcp.tool()
    async def list_api_keys(include_revoked: bool = False) -> dict[str, Any]:
        """List the tenant's API keys (prefixes only — raw values are never stored)."""
        return await client.list_api_keys(include_revoked=include_revoked)

    @mcp.tool()
    async def revoke_api_key(key_id: str) -> dict[str, Any]:
        """Revoke an API key by id. Irreversible; the key stops working immediately."""
        return await client.revoke_api_key(key_id)

    return mcp
