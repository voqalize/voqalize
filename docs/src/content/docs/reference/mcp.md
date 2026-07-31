---
title: MCP server & Claude Code skill
description: Create and manage agents, mint keys, set brain_urls, and read call logs from your editor's agent — over a hosted, OAuth-authenticated MCP endpoint.
---

The Voqalize MCP server exposes the platform's management surface as tools your
editor's agent (Claude Code, etc.) can call. Paired with the **`voqalize` skill**,
it takes a developer from an empty project to a running voice agent without leaving
the editor.

It is a **hosted, remote MCP endpoint** — you don't install or run anything. Point
your MCP client at the URL, authenticate once with Google in the browser, and the
tools are available.

## Connect

Add the server to your MCP client. In Claude Code:

```bash
claude mcp add --transport http voqalize https://app.voqalize.com/mcp
```

Or, project-scoped, drop an `.mcp.json` at your repo root (this is the file the
`voqalize` skill ships):

```json
{
  "mcpServers": {
    "voqalize": {
      "type": "http",
      "url": "https://app.voqalize.com/mcp"
    }
  }
}
```

On first use your client runs a browser **Google sign-in** and the tools light up.
There is **no API key, client ID, or secret to configure** — the client registers
itself dynamically and carries the resulting token.

:::note[One endpoint, no install]
The old pre-pivot server was a local stdio process holding a management key
(`mk_…`). That is gone: management keys are removed, and the server now runs inside
the Voqalize control plane behind Google OAuth. Nothing to `pip`/`uvx`-install.
:::

## Auth & tenancy

- **Google OAuth (the same login as the console).** Your MCP client authenticates
  with Google via Dynamic Client Registration — it self-registers, you complete the
  browser sign-in, and identity comes from your Google account. First sign-in
  provisions your Voqalize user automatically.
- **The token is the credential; `tenant` is a selector.** Every scoped tool takes
  a required `tenant` slug and is checked against your membership before it runs —
  passing a slug you don't belong to fails. You can't act on a tenant just by naming
  it.
- **`whoami` first, then `list_tenants`.** `whoami` returns your identity;
  `list_tenants` returns every workspace you can act on. Call them at the start of a
  session to learn which `tenant` slug to pass to everything else.

## Tools

Fifteen tools. Every tool returns the control plane's raw JSON. Errors surface with
a platform code — `not_authorized` (you're not a member of that tenant, or your role
is too low) or `validation_error` (bad input, e.g. a non-`wss://` `brain_url` on a
non-loopback host).

### Identity & workspace

| Tool | Signature | Does |
|---|---|---|
| `whoami` | `() -> dict` | Identify the authenticated developer. **Call first.** |
| `list_tenants` | `() -> dict` | Every tenant (workspace) you can act on. |
| `create_tenant` | `(about="", display_name="") -> dict` | Create your workspace + seed demo agents. Idempotent — returns your existing tenant if you have one. |

### Agents

| Tool | Signature | Does |
|---|---|---|
| `create_agent` | `(tenant, name, description="", brain_url="") -> dict` | Create an agent. Returns `{agent, session_key (sk_…, once)}`. |
| `get_agent` | `(tenant, agent_id) -> dict` | One agent, incl. STT/TTS config + `brain_url`. |
| `list_agents` | `(tenant, status="", limit=20) -> dict` | List agents; optional `draft\|active\|archived` filter. |
| `update_agent` | `(tenant, agent_id, name="", description="", brain_url="") -> dict` | Rename, re-describe, and/or point the brain at a WS URL. |
| `archive_agent` | `(tenant, agent_id) -> dict` | Soft delete (stops serving new sessions). |

There is no separate `set_brain_url` tool — pass `brain_url` to `create_agent` up
front, or set it later with `update_agent`. It must be `wss://` (`ws://` only for
`localhost`/`127.0.0.1`); an empty `brain_url` falls back to the hosted `welcome`
demo brain so a bare agent still greets.

### Keys

| Tool | Signature | Does |
|---|---|---|
| `create_api_key` | `(tenant, label, kind="secret", allowed_origins=None) -> dict` | Mint a runtime key. `kind="publishable"` (`pk_`, browser — pass origins) or `"secret"` (`sk_`, backend). Raw key shown once. |
| `list_api_keys` | `(tenant, include_revoked=False) -> dict` | List keys (prefixes only). |
| `revoke_api_key` | `(tenant, key_id) -> dict` | Revoke by id (irreversible). |

### Calls & logs (observability)

| Tool | Signature | Does |
|---|---|---|
| `list_meetings` | `(tenant, agent_id="", state="", limit=20) -> dict` | List calls, most recent first; filter by agent/state. |
| `get_meeting` | `(tenant, meeting_id) -> dict` | One call's detail. |
| `list_meeting_events` | `(tenant, meeting_id) -> dict` | The event timeline for a call. |
| `query_logs` | `(tenant, meeting_id, severity_min="INFO", component="", limit=100) -> dict` | Runtime log lines for one call. |

## The `voqalize` skill

The skill (`skill/SKILL.md`) drives the end-to-end build on top of those tools. It
walks the flow:

1. **Prereqs** — confirm the MCP server is connected (`whoami` → `list_tenants`);
   Python 3.12+; a React app for the embed.
2. **Draft the brain** — scaffold from `templates/brain.py`; implement
   `on_session_start` / `on_interaction` / `on_app_event`.
3. **Pick the transport** — inbound (primary) vs. Cortex (fallback). Default to
   [inbound](/docs/deploy/brain-url/).
4. **Create the agent** — `create_agent(tenant, name, brain_url=…)` →
   `{agent, session_key}`.
5. **Run + test** — run the brain locally behind a tunnel (inbound) or dial out
   (Cortex), then talk to it in the console Playground.
6. **Wire the `brain_url`** — via `create_agent` up front or `update_agent` later.
7. **Embed in the browser** — `create_api_key(tenant, label, kind="publishable", …)`
   → `pk_…`, then `@voqalize/client-react`.

Templates ship alongside it: `brain.py`, `inbound_app.py`, `run_cortex.py`, and
`react_embed.tsx`.

## Next

- **[Quickstart](/docs/start/quickstart/)** — the same flow, by hand.
- **[Where the brain runs](/docs/deploy/brain-url/)** — inbound vs. Cortex.
