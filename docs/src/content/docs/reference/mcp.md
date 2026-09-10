---
title: MCP server
description: Create and manage agents, mint keys, set brain_urls, and read call records from your editor's agent — over a hosted, OAuth-authenticated MCP endpoint.
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

Two endpoints, one per environment:

| Environment | Endpoint |
|---|---|
| Production | `https://app.voqalize.com/mcp/` |
| Development | `https://app.dev.voqalize.com/mcp/` |

Add the server to your MCP client. In Claude Code:

```bash
claude mcp add --transport http voqalize https://app.voqalize.com/mcp/
```

Or, project-scoped, drop an `.mcp.json` at your repo root:

```json
{
  "mcpServers": {
    "voqalize": {
      "type": "http",
      "url": "https://app.voqalize.com/mcp/"
    }
  }
}
```

Swap in the development URL to work against dev. Every other MCP client takes
the same two things — a name and that URL over HTTP — so the block above
translates directly.

On first use your client runs a browser **Google sign-in** and the tools light up.
There is **no API key, client ID, or secret to configure** — the client registers
itself dynamically and carries the resulting token.

:::note[Either spelling reaches it]
The endpoint is `/mcp/` and that is the URL to configure — it answers directly,
with no redirect. `/mcp` reaches it too: it answers `307` to `/mcp/`, preserving
the method and the body, which every MCP client follows. Both spellings also
satisfy the OAuth resource check, which compares paths without regard to a
trailing slash.
:::

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
  `list_tenants` returns every tenant you can act on, each with its `name`, its
  `slug` and your `role` in it. Choose a tenant by its `name` — the `slug` is a
  random string that means nothing to a person — and pass that row's `slug` as
  the `tenant` argument to everything else. An empty list means there is no tenant
  yet: call `create_tenant`.
- **120 tool calls per minute, per tenant.** Metered at the membership check,
  so it is charged only after your membership is proven and it counts against
  this surface alone — an agent looping over sessions cannot spend the budget a
  page needs to start a call. `whoami`, `list_tenants` and `create_tenant` take
  no `tenant` and are not metered here.

## Tools

Twenty-eight tools. Every tool returns the control plane's raw JSON. A refused
call comes back as a tool error carrying the control plane's own message —
not a member of that tenant, role too low, no such agent or session, or bad
input (a non-`wss://` `brain_url` on a non-loopback host, say) — so read the
message; there is no separate code to switch on.

Signatures below omit the type of `tenant`: it is always the slug string from
`list_tenants`. An empty string for an optional argument means *leave it
unchanged* on an update and *no filter* on a list.

### Identity & tenant

| Tool | Signature | Does |
|---|---|---|
| `whoami` | `() -> {id, email, name}` | Identify the authenticated developer. **Call first.** |
| `list_tenants` | `() -> {tenants: [{slug, tenant_id, name, role, created_at}]}` | Every tenant you belong to. `role` is `owner`, `admin` or `member`. The `slug` is the `tenant` argument. |
| `create_tenant` | `(about="", display_name="") -> {slug, tenant_id, display_name, name, role}` | Create your tenant and its first agent, "My first agent", which has no `mode` and no `brain_url` and cannot take a call until you configure it. Idempotent — returns your existing tenant unchanged if you have one; a second tenant is not available here. The response does not carry the agent's id: call `list_agents` for it. |

### Agents

Every agent-returning tool hands back the same record: `id`, `name`,
`description`, `status` (`active` / `archived`), `stage`, `mode`, `brain_url`,
`recording`, the Playground `test_url`, `last_session_at`, `brain_verified_at`,
`created_at`, `updated_at`. `mode` is `inbound`, `cortex` or `null`; `stage` is
`unconfigured` (no `brain_url`), `configured` (a `brain_url` is saved; no call has
reached it), `verified` (a real call reached *this* `brain_url` and ended without
failing) or `embedded` (calls arrive through an API key, not the console). It is a
ladder of what you still have to do, not a health signal. It does **not** carry STT/TTS config —
that is the session's, set at connect and by the brain.

| Tool | Signature | Does |
|---|---|---|
| `create_agent` | `(tenant, name, description="", brain_url="", recording=None) -> {agent, session_key: {value, note}}` | Create an agent. The `session_key` is an `sk_` secret shown **once**, for a backend to start sessions with. A `brain_url` implies `mode="inbound"`; without one the agent has no mode. |
| `create_agent_credentials` | `(tenant, agent_id, label="") -> {agent_id, agent_secret, cortex_url, key_id, expires, instructions, usage}` | Mint Cortex outbound credentials for a brain that **can't accept inbound** (localhost, serverless, egress-only). Switches the agent to `cortex` mode. `agent_secret` is an `sk_` shown once and never expires; `usage` carries the env, `serve` and note to paste. There is no `brain_url` to copy back — the relay address is ours. |
| `get_agent` | `(tenant, agent_id) -> agent` | One agent, as above. |
| `list_agents` | `(tenant, status=None, limit=20, cursor="") -> {agents, next_cursor}` | List agents, archived included. `status` is an exact match on `active` or `archived`; anything else is **refused** — it used to return an empty list, which reads exactly like a tenant whose agents have gone. `limit` is capped at 100; a null `next_cursor` is the last page. |
| `update_agent` | `(tenant, agent_id, name="", description="", brain_url="", mode="", recording=None) -> agent` | Rename, re-describe, point the brain at a WS URL, or set the agent's [recording](/operate/recordings/) default. Empty means unchanged; `recording=None` means unchanged too. A `brain_url` implies `mode="inbound"`; `mode="cortex"` drops the `brain_url`. You rarely pass `mode` yourself. |
| `archive_agent` | `(tenant, agent_id) -> agent` | Retire the record while keeping it. It does **not** take the agent out of service: a live `sk_` or `pk_` still starts sessions against it and they still reach its `brain_url`. What archiving refuses is new credentials. To stop an agent serving, `list_api_keys` and `revoke_api_key` every key whose `agent_id` is this one. |
| `unarchive_agent` | `(tenant, agent_id) -> agent` | Put an archived agent back. |

There is no separate `set_brain_url` tool — pass `brain_url` to `create_agent` up
front, or set it later with `update_agent`. It must be `wss://` (`ws://` only for
`localhost`/`127.0.0.1`).

**An agent with no `mode` cannot take a call**: `sessions.connect` refuses it with
`409 agent_not_configured`, and `stage` reads `unconfigured`. An empty `brain_url`
used to fall back to a hosted `welcome` demo brain so a bare agent still greeted,
which meant a call that worked was no evidence your brain was wired. The remaining
silent failure is a `brain_url` nothing listens on: the session connects, the user
hears nothing, and `stage` stays at `configured` — it reads `verified` only once a
real session has reached your brain.

`create_agent_credentials` puts the agent on the relay and hands you the one URL
your brain dials out to. [Cortex relay](/build/outbound/) has the detail — including
the `update_agent` round trip it used to require and no longer does. What is worth
knowing before you call the tool: the `sk_`
secret is shown once, never expires, and minting revokes nothing — so rotation
is mint, redeploy, then `revoke_api_key` on the old one, with no window where
the agent cannot connect.

### Keys

A key row is `id`, `kind`, `label`, `prefix`, `agent_id`, `agent_name`,
`allowed_origins`, `status`, `created_at`, `revoked_at`, `last_used_at`. The
raw value appears only on the response that minted it.

| Tool | Signature | Does |
|---|---|---|
| `create_api_key` | `(tenant, agent_id, label, kind="secret", allowed_origins=None) -> key + {value, note}` | Mint another key for one agent. `kind="publishable"` (`pk_`, browser — pass origins) or `"secret"` (`sk_`, backend). Raw `value` shown once. |
| `list_api_keys` | `(tenant, include_revoked=False, agent_id="") -> {keys}` | List keys (prefixes only), newest first, each with the agent it names. Not paged. `agent_id` narrows to one agent. |
| `revoke_api_key` | `(tenant, key_id) -> {ok, revoked, key}` | Revoke by id (irreversible). |
| `update_api_key_origins` | `(tenant, key_id, allowed_origins) -> key` | Replace a publishable key's origin list. It is the **complete** list — send every origin, not the one you are adding. |

### Calls (observability)

A session row is `id`, `state`, `agent_id`, `agent_name`, `display_name`,
`created_at`, `started_at`, `ended_at`, `duration_secs`, `end_reason`,
`end_detail`, `error`. `state` is one of `starting`, `active`, `ending`,
`ended`, `expired`, `failed`. `end_reason` is `null` while `state` is
`starting`, `active` or `ending` — a live call has no reason yet, and it is
never `unknown` just because the call has not ended. Once the call is over it
is `token_expired` when the session never connected and only expired, or one
of `user_hung_up`, `agent_hung_up`, `idle_timeout`, `brain_disconnected`,
`brain_unreachable`, `never_connected`, `terminated`, `runtime_error`, or
`unknown` when none of those apply. `end_detail` is one line of evidence for
that reason — the raw signal, not a sentence for a person. `disconnect_reason`
is deprecated: it still appears on the row but `end_reason` is the field to
read.

| Tool | Signature | Does |
|---|---|---|
| `list_sessions` | `(tenant, agent_id="", state=None, limit=20, cursor="") -> {sessions, next_cursor}` | List calls, most recent first; filter by agent and by one `state`. `limit` is capped at 100; page with `next_cursor`. |
| `get_session` | `(tenant, session_id) -> session` | One call in full: the row above plus `brain_url_defaulted`, `started_by`, `metadata`, the resolved `config`, `init`, and a `recordings` summary (`id`, `role`, `state`, `duration_secs`, `failure_reason`). |
| `get_session_events` | `(tenant, session_id) -> {session_id, events: [{occurred_at, event_type, id, actor_id, actor, payload}]}` | Voqalize's own milestones — created, connected, ended; about five, written **while the session runs**, so they answer for a call still in progress and for one nothing connected to. `actor` is the person as `{id, email, name}` when a person did it, `null` when Voqalize did. This says how far the call got, not what was said. |
| `get_call_record` | `(tenant, session_id, limit=2000, include_events=False) -> {session_id, record, turns, pace, meta, …}` | **The contract.** What the two halves exchanged, as turns: each `asked` question with its `asked_at`, the `units` your brain spoke with what it `generated`, what the user `heard` and an `outcome` (`spoken`, `cut_short`, `never_spoken`, `unknown`), the `gaps` where the wire was quiet, and the `marks`. `record` is `found`, `missing` or `unavailable` — read it before concluding a call was silent. `include_events` adds the raw records under the turns; `limit` bounds those and never the turns. |
| `get_session_logs` | `(tenant, session_id, level="INFO", service="", limit=500) -> {session_id, logs, logs_availability, truncated}` | Voqalize's own log lines for that call. `level` is a floor (`DEBUG` … `CRITICAL`); `service` matches one process's lines exactly; `limit` is capped at 5000. |
| `get_recordings` | `(tenant, session_id, ttl_seconds=900) -> {session_id, recordings}` | Audio, one entry per `role` (`mixed`, `user`, `agent`), with a short-lived signed `download_url` on the entries that have a file in storage. `ttl_seconds` is 60–900. |
| `get_usage` | `(tenant, period="") -> {duration_secs, sessions_created, sessions_started, agents, …}` | Counters for one `YYYY-MM` billing period (UTC; empty is the current month), with the same numbers per agent in `agents`, busiest first. |

### Sessions (lifecycle)

| Tool | Signature | Does |
|---|---|---|
| `update_session` | `(tenant, session_id, display_name="", metadata=None) -> session` | Label a session for a person, and set your own `metadata` — a customer reference, a build number. `metadata` is a **replace**: send the whole map back, or the keys you left out are gone. |
| `terminate_session` | `(tenant, session_id, reason="") -> session` | Hang up on a live session, without warning and with no goodbye. Recorded as `failed`, not `ended`, with `reason` beside it — so it is absent from a list filtered on `ended`. A session already over is refused. |
| `archive_session` | `(tenant, session_id) -> session` | Take a finished session out of the working list. Record, events and recordings are all kept. A session still in progress is refused — `terminate_session` is the way to end one. |

### Members

A member row is `id`, `user_id`, `email`, `full_name`, `role`, `status`,
`added_by`, `added_by_user`, `added_at`, `updated_at`. Roles are `owner`,
`admin` (may mint and revoke keys, and change this roster) and `member`.

| Tool | Signature | Does |
|---|---|---|
| `add_member` | `(tenant, email, full_name="", role="member") -> member` | A **grant, not an invitation**: nothing is emailed, and whoever signs in with that address reaches every agent, session, recording and key in the tenant the moment this returns. Tell the person yourself. Grant the narrowest role that works. |
| `list_members` | `(tenant, limit=50, cursor="") -> {members, next_cursor}` | The roster, paged. |
| `update_member_role` | `(tenant, member_id, role) -> member` | Change one member's role. |
| `remove_member` | `(tenant, member_id) -> member` | Take someone off the tenant. |

**A call is a session, and that is the only noun.** There is no Meeting above it:
`list_meetings` / `get_meeting` / `list_meeting_events` / `query_logs` were removed
on 2026-08-20 along with the entity, and the session id you already hold — the one
in `connect_params`, in `{brain_url}?session_id={session_id}`, in every log line — is the id
every one of these tools takes.

The order to read them in, what the filters are for, and why an empty list is
not the same fact as a silent call are all in
[Reading a call back](/operate/reading-a-call/). Three things belong here because
they are properties of the tools rather than of the workflow:

- **The record is contract, logs are evidence.** `get_call_record` is versioned,
  additive-only and safe to assert on in a test. `get_session_logs` is written in
  our vocabulary and free to change — read them to understand a call, never to
  assert on one.
- **Milestones arrive during the call; the record and the logs arrive when it
  ends.** `get_session_events` answers for a session still in progress.
  `get_call_record` and `get_session_logs` are uploaded at teardown, so a call
  still running has neither: check `record` and `logs_availability` before
  concluding anything from an empty list.
- **Every read is keyed on a session you are authorized to see.** There is no
  free-text log search and no arbitrary time range, on purpose.

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
4. **Run it and say how it is reached** — locally, `create_agent_credentials` to
   dial out over [Cortex](/build/outbound/) (no tunnel), which sets the mode for
   you; in production, `update_agent(brain_url=…)` for an
   [inbound](/build/inbound/) route. Until you do one of the two, the agent
   cannot take a call.
5. **Test it unattended** — the [conformance harness](/build/testing/) drives
   the brain in text mode, with no audio and no human. Then talk to it live at the
   agent's `test_url`.
6. **Embed in the browser** — `create_api_key(tenant, agent_id, label, kind="publishable", …)`
   → `pk_…`, then [the handshake](/build/connect/) — no package to install.
7. **Instrument it** — `on_finalize` / `on_error` brain-side, `list_sessions` /
   `get_call_record` / `get_session_logs` on ours.

## Read next

- **[Where the brain runs](/build/hosting/)** — inbound vs. Cortex.
- **[Testing a brain](/build/testing/)** — the unattended test loop.
- **[Reading a call back](/operate/reading-a-call/)** — the record first, logs second, and
  what an empty list does not mean.
