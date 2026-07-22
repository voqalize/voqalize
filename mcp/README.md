# Voqalize MCP server

Manage Voqalize voice agents **from inside your Claude Code** (or any MCP client).
The server holds one Voqalize **management key** and exposes the control-plane
management API as tools, so your Claude Code can create an agent, point its brain
at a WebSocket URL, and mint the browser/backend keys — without you leaving the
editor.

You bring the brain (a WebSocket URL), Voqalize brings the voice.

## Prerequisites

1. You're a member of a Voqalize tenant.
2. A tenant **owner** minted you a management key (`mk_…`) in the console
   (API keys → kind *management*). It's shown once — copy it.

## Configure

The server reads three environment variables:

| Variable | Required | Notes |
|---|---|---|
| `VOQALIZE_MANAGEMENT_KEY` | ✓ | Your `mk_…` key. |
| `VOQALIZE_TENANT` | ✓ | Your tenant slug. |
| `VOQALIZE_API_BASE` | | Control-plane base URL. Defaults to `http://localhost:8274` (local dev). |

## Run it in Claude Code

> **Pre-release:** `voqalize-mcp` isn't on PyPI yet, so the `uvx voqalize-mcp`
> form below won't resolve from the index today. Until it's published, point
> `uvx` at a clone of this repo — `"command": "uvx", "args": ["--from",
> "path/to/voqalize/mcp", "voqalize-mcp"]` — or run it from the clone
> (`cd path/to/voqalize/mcp && uv run voqalize-mcp`). The published form below is
> what you'll switch to once it ships.

Add to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "voqalize": {
      "command": "uvx",
      "args": ["voqalize-mcp"],
      "env": {
        "VOQALIZE_MANAGEMENT_KEY": "mk_live_…",
        "VOQALIZE_TENANT": "your-tenant",
        "VOQALIZE_API_BASE": "https://api.voqalize.com"
      }
    }
  }
}
```

Then in Claude Code: *"Create a Voqalize agent called Support Bot and point its
brain at wss://my-brain.example.com."*

## Tools

| Tool | What it does |
|---|---|
| `whoami` | Confirm the key is valid and report the tenant. |
| `list_agents` / `get_agent` | Inspect agents (status filter, full config). |
| `create_agent` | Create an agent; returns `agent_secret` (`ak_…`, for a Cortex brain) + `cortex_url`. |
| `set_brain_url` | Point an agent's brain at a `wss://` URL (preserves STT/TTS config). |
| `update_agent` / `archive_agent` | Rename/re-describe, or soft-delete. |
| `create_api_key` | Mint `pk_` (browser/React) or `sk_` (backend). Raw key shown once. |
| `list_api_keys` / `revoke_api_key` | List (prefixes only) / revoke. |

Observability tools (`tail_logs`, `get_metrics`) are **not** here — that layer is
owned by a separate track and registers its own tools.

## The Claude Code skill

This package ships a Claude Code **skill** under [`skill/`](skill/) that drives
the full "build a voice agent on Voqalize" flow on top of these tools: scaffold a
brain, pick the inbound (direct) or Cortex (outbound) transport, create the agent,
wire its `brain_url`, mint a browser key, and embed the React widget. Copy
[`skill/.mcp.json`](skill/.mcp.json) into your project (filling in your key and
tenant) to connect the server, and point Claude Code at [`skill/SKILL.md`](skill/SKILL.md).
The `skill/templates/` files (`brain.py`, `inbound_app.py`, `run_cortex.py`,
`react_embed.tsx`) are standalone starters the developer drops into their own repo.

## Develop

```bash
cd mcp
uv run pytest
```
