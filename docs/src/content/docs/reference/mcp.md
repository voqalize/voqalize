---
title: MCP server
description: Create and manage agents, mint keys, set brain_urls, and read call logs from your editor's agent — over a hosted, OAuth-authenticated MCP endpoint.
---

The Voqalize MCP server exposes Voqalize's management surface as tools your
editor's agent (Claude Code, etc.) can call: create an agent, mint its keys, point
its `brain_url` at your route, and read back what a call did — without leaving the
editor.

The server hands your agent its own instructions on connect, and those link here.
There is no skill to install and nothing to keep in sync: every page on this site
is also served as raw markdown at the same URL plus `.md`, indexed at
[`/llms.txt`](/llms.txt).

It is a **hosted, remote MCP endpoint** — you don't install or run anything. Point
your MCP client at the URL, authenticate once with Google in the browser, and the
tools are available.

## Connect

Add the server to your MCP client. In Claude Code:

```bash
claude mcp add --transport http voqalize https://app.voqalize.com/mcp
```

Or, project-scoped, drop an `.mcp.json` at your repo root:

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
- **300 tool calls per minute, per workspace.** Metered at the membership check,
  so it is charged only after your membership is proven and it counts against
  this surface alone — an agent looping over sessions cannot spend the budget a
  page needs to start a call. `whoami` and `list_tenants` take no `tenant` and
  are not metered here.

## Tools

Eighteen tools. Every tool returns the control plane's raw JSON. Errors surface with
one of two codes — `not_authorized` (you're not a member of that tenant, or your role
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
| `create_agent` | `(tenant, name, description="", brain_url="", recording=None) -> dict` | Create an agent. Returns `{agent, session_key (sk_…, once)}`. |
| `create_agent_credentials` | `(tenant, agent_id, label="") -> dict` | Mint Cortex outbound credentials for a brain that **can't accept inbound** (localhost, serverless, egress-only). Returns `{agent_secret (sk_…, once), cortex_url, brain_url, key_id, usage}`. |
| `get_agent` | `(tenant, agent_id) -> dict` | One agent: `id`, name, description, status, `brain_url`, Playground `test_url`, timestamps. It does **not** return STT/TTS config. |
| `list_agents` | `(tenant, status="", limit=20, cursor="") -> dict` | List agents, archived included. `status` is an exact match on one of two values, `active` or `archived`; any other string returns an empty list rather than an error, so read an empty result twice. |
| `update_agent` | `(tenant, agent_id, name="", description="", brain_url="", recording=None) -> dict` | Rename, re-describe, point the brain at a WS URL, or set the agent's [recording](/operate/recordings/) default. |
| `archive_agent` | `(tenant, agent_id) -> dict` | Soft delete (stops serving new sessions). |

There is no separate `set_brain_url` tool — pass `brain_url` to `create_agent` up
front, or set it later with `update_agent`. It must be `wss://` (`ws://` only for
`localhost`/`127.0.0.1`); an empty `brain_url` falls back to the hosted `welcome`
demo brain so a bare agent still greets.

`create_agent_credentials` returns three fields that go to three different
places, and two of them are URLs that are **not interchangeable**.
[Cortex relay](/build/outbound/) has the table and the `update_agent` call that
finishes the job. What is worth knowing before you call the tool: the `sk_`
secret is shown once, never expires, and minting revokes nothing — so rotation
is mint, redeploy, then `revoke_api_key` on the old one, with no window where
the agent cannot connect.

### Keys

| Tool | Signature | Does |
|---|---|---|
| `create_api_key` | `(tenant, agent_id, label, kind="secret", allowed_origins=None) -> dict` | Mint another key for one agent. `kind="publishable"` (`pk_`, browser — pass origins) or `"secret"` (`sk_`, backend). Raw key shown once. |
| `list_api_keys` | `(tenant, include_revoked=False) -> dict` | List keys (prefixes only), each with the agent it names. |
| `revoke_api_key` | `(tenant, key_id) -> dict` | Revoke by id (irreversible). |

### Calls (observability)

| Tool | Signature | Does |
|---|---|---|
| `list_sessions` | `(tenant, agent_id="", state="", limit=20, cursor="") -> dict` | List calls, most recent first; filter by agent/state. Page with `next_cursor`. |
| `get_session` | `(tenant, session_id) -> dict` | One call in full: state, timing, the resolved `config`, `init`, `metadata`, recordings summary. |
| `get_session_events` | `(tenant, session_id, source="all", frame="", disposition="", limit=2000) -> dict` | What happened, merged: lifecycle milestones **and** the wire between runtime and brain — transcripts, replies, actions, interruptions. |
| `get_session_logs` | `(tenant, session_id, level="INFO", service="", limit=500) -> dict` | The voice runtime's own log lines for that call. |
| `get_recordings` | `(tenant, session_id, ttl_seconds=900) -> dict` | Audio, one track per side, each with a short-lived signed `download_url`. |
| `get_usage` | `(tenant, period="") -> dict` | Counters for one `YYYY-MM` billing period, broken down per agent. |

**A call is a session, and that is the only noun.** There is no Meeting above it:
`list_meetings` / `get_meeting` / `list_meeting_events` / `query_logs` were removed
on 2026-08-20 along with the entity, and the session id you already hold — the one
in `connect_params`, in `{brain_url}?session_id={session_id}`, in every log line — is the id
every one of these tools takes.

The order to read them in, what the filters are for, and why an empty list is
not the same fact as a silent call are all in
[Reading a call back](/operate/reading-a-call/). Two things belong here because
they are properties of the tools rather than of the workflow:

- **Events are contract, logs are evidence.** `get_session_events` is versioned
  and safe to assert on in a test. `get_session_logs` is written in our
  vocabulary and free to change — read them to understand a call, never to
  assert on one.
- **Both halves arrive when the call ends**, so a call still in progress has
  neither. Check the `wire` / `logs_availability` field before concluding
  anything from an empty list.

These are **Voqalize's** records. Your brain runs in your own environment and
logs there; the `session_id` is the same string on both sides, so it joins them.

## The flow, end to end

An agent with these tools connected takes a project from empty to a running voice
agent in this order:

1. **Confirm the connection** — `whoami`, then `list_tenants` for the `tenant` slug
   every other tool requires.
2. **Write the brain** — `on_session_start` / `on_user_message` /
   `on_rtvi` / `on_user_idle`. See [Your first brain](/build/brain/).
3. **Create the agent** — `create_agent(tenant, name)` → `{agent, session_key}`.
4. **Run it and point `brain_url` at it** — locally, `create_agent_credentials` and
   dial out over [Cortex](/build/outbound/) (no tunnel); in production, an
   [inbound](/build/inbound/) route. Either way finish with `update_agent`.
5. **Test it unattended** — the [conformance harness](/build/testing/) drives
   the brain in text mode, with no audio and no human. Then talk to it live at the
   agent's `test_url`.
6. **Embed in the browser** — `create_api_key(tenant, agent_id, label, kind="publishable", …)`
   → `pk_…`, then [the handshake](/build/connect/) — no package to install.
7. **Instrument it** — `on_finalize` / `on_error` brain-side, `list_sessions` /
   `get_session_events` / `get_session_logs` on ours.

## Read next

- **[Where the brain runs](/build/hosting/)** — inbound vs. Cortex.
- **[Testing a brain](/build/testing/)** — the unattended test loop.
- **[Reading a call back](/operate/reading-a-call/)** — events first, logs second, and
  what an empty list does not mean.
