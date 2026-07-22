---
title: MCP server & Claude Code skill
description: Create and manage agents, mint keys, and set brain_urls from your editor's agent — plus a skill that walks the whole build.
---

The Voqalize MCP server exposes the platform's management API as tools your
editor's agent (Claude Code, etc.) can call. Paired with the **`voqalize` skill**,
it takes a developer from an empty project to a running voice agent without leaving
the editor.

:::note[Pre-release]
Not yet on PyPI. Run it from a clone of
[`voqalize/voqalize`](https://github.com/voqalize/voqalize) (`uvx --from ./mcp
voqalize-mcp`).
:::

## Configuration

The server is a stdio MCP server holding one **management key** (`mk_…`). Three
environment variables:

| Var | Required | Notes |
|---|---|---|
| `VOQALIZE_MANAGEMENT_KEY` | yes | `mk_…` — drives the tenant. |
| `VOQALIZE_TENANT` | yes | Tenant slug. |
| `VOQALIZE_API_BASE` | no | **Bare host**, e.g. `https://api.voqalize.com` (the client adds `/api/v1/{tenant}`). Defaults to `http://localhost:8274`. |

:::caution[`VOQALIZE_API_BASE` is a bare host]
Unlike the React SDK's `apiBase` (which **includes** `/api/v1`), the MCP server's
`VOQALIZE_API_BASE` is just the host — the client appends `/api/v1/{tenant}`
itself. Same host, different suffix.
:::

## Tools

Every tool returns the control plane's raw JSON. Errors surface as a
`ControlPlaneError` with a platform code (`not_authorized` = key role too low,
`validation_error` = bad input).

| Tool | Signature | Does |
|---|---|---|
| `whoami` | `() -> dict` | Validate the key; report the tenant it drives. |
| `list_agents` | `(status=None, limit=20) -> dict` | List agents; optional `draft\|active\|archived` filter. |
| `get_agent` | `(agent_id) -> dict` | One agent, incl. STT/TTS config + `brain_url`. |
| `create_agent` | `(name, description=None, brain_url=None) -> dict` | Create an agent. Returns `{agent, agent_secret (ak_…, once), cortex_url}`. |
| `set_brain_url` | `(agent_id, brain_url) -> dict` | Point the brain at a WS URL (`wss://`; `ws://` only for localhost). Preserves STT/TTS. |
| `update_agent` | `(agent_id, name=None, description=None) -> dict` | Rename / re-describe. |
| `archive_agent` | `(agent_id) -> dict` | Soft delete (stops serving new sessions). |
| `create_api_key` | `(kind, label, allowed_origins=None) -> dict` | Mint a runtime key. `kind="publishable"` (`pk_`, browser — pass origins) or `"secret"` (`sk_`, backend). Raw key shown once. |
| `list_api_keys` | `(include_revoked=False) -> dict` | List keys (prefixes only). |
| `revoke_api_key` | `(key_id) -> dict` | Revoke by id (irreversible). |

The management key can mint runtime keys but **not** other management keys.

:::note
Observability tools (log tailing, metrics) are not part of the MCP server yet —
they belong to a separate track.
:::

## The `voqalize` skill

The skill (`mcp/skill/SKILL.md`) drives the end-to-end build on top of those tools.
It walks seven steps:

1. **Prereqs** — confirm the MCP server is connected (`whoami`); Python 3.12+; a
   React app for the embed.
2. **Draft the brain** — scaffold from `templates/brain.py`; implement
   `on_session_start` / `on_interaction` / `on_app_event`.
3. **Pick the transport** — inbound (primary) vs. Cortex (fallback). Default to
   [inbound](/docs/deploy/inbound/).
4. **Create the agent** — `create_agent` → `{agent, agent_secret, cortex_url}`.
5. **Run + test** — run the brain locally behind a tunnel (inbound) or dial out
   (Cortex).
6. **Wire the `brain_url`** — `set_brain_url(agent_id, brain_url)`.
7. **Embed in the browser** — `create_api_key(kind="publishable", …)` → `pk_…`,
   then `@voqalize/client-react`.

Templates ship alongside it: `brain.py`, `inbound_app.py`, `run_cortex.py`, and
`react_embed.tsx`.

## Next

- **[Quickstart](/docs/start/quickstart/)** — the same flow, by hand.
- **[Where the brain runs](/docs/deploy/brain-url/)** — inbound vs. Cortex.
