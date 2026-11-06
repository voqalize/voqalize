---
title: MCP server
description: The hosted, OAuth-authenticated MCP endpoint and every tool on it, with signatures and defaults. Create agents, mint keys, set brain URLs, read sessions, call records, logs, recordings and usage, manage members, and manage Site Agent sites.
---

The Voqalize MCP server is the management surface: tools your coding agent
(Claude Code, or any MCP client) calls to create an agent, mint its keys, point
its `brain_url` at your route, and read back what a session did. It is hosted;
there is nothing to install or run.

## Connect

The endpoint is `https://app.voqalize.com/mcp/`, over HTTP, signed in with
Google (OAuth). There is no API key, client ID or secret to configure, and your
first sign-in creates your Voqalize user.
[Work with a coding agent](/build/coding-agent/#connect-the-mcp-server) has the
setup for Claude Code and `.mcp.json`.

## Auth, tenancy and limits

- **The token is the credential; `tenant` is a selector.** Every scoped tool
  takes a required `tenant` slug and checks your membership before it runs.
- **Call `whoami`, then `list_tenants`.** Choose a tenant by its `name` and pass
  that row's `slug` as `tenant` to every other tool. An empty list means you
  have no tenant yet: call `create_tenant`.
- **120 tool calls per minute, per tenant.** Counted after the membership check,
  and separately from `sessions.connect`, so an agent looping over sessions
  cannot spend the allowance a page needs to start a session. `whoami`,
  `list_tenants` and `create_tenant` are not counted. Past the limit a call
  fails with the tool error `Too many requests. Slow down and retry.`; back off
  for a few seconds and call again.

A refused call comes back as a tool error with a message that says why: not a
member of that tenant, role too low, no such agent or session, or bad input.
There is no separate code to switch on. Every tool otherwise returns JSON.

In the signatures below, `tenant` is always the slug string from
`list_tenants`. An empty string for an optional argument means *leave it
unchanged* on an update and *no filter* on a list.

## Identity and tenant

| Tool | Signature | Does |
|---|---|---|
| `whoami` | `() -> {id, email, name}` | Identify the signed-in developer. **Call first.** |
| `list_tenants` | `() -> {tenants: [{slug, tenant_id, name, role, created_at}]}` | Every tenant you belong to. `role` is `owner`, `admin` or `member`. |
| `create_tenant` | `(about="", display_name="") -> {slug, tenant_id, display_name, name, role}` | Create your tenant and its first agent, "My first agent", which cannot take a session until you configure it. Idempotent: returns your existing tenant if you have one. Call `list_agents` for the agent's id. |

## Agents

Every agent-returning tool returns one record: `id`, `name`, `description`,
`status` (`active` or `archived`), `stage`, `mode`, `brain_url`, `recording`, the
Playground `test_url`, `last_session_at`, `brain_verified_at`, `created_at`,
`updated_at`.

- `mode` is `inbound`, `cortex` or `null`.
- `stage` is what you still have to do, not a health signal: `unconfigured` (no
  `brain_url`), `configured` (a `brain_url` is saved and no session has reached
  it), `verified` (a session reached *this* `brain_url` and ended without
  failing) or `embedded` (sessions arrive through an API key, not the console).
- The record carries no voice or language: those are set per session, at
  connect or by the brain.

| Tool | Signature | Does |
|---|---|---|
| `create_agent` | `(tenant, name, description="", brain_url="", recording=None) -> {agent, session_key: {value, note}}` | Create an agent. Owner or admin only. `session_key` is an `sk_` secret shown **once**, for your server to start sessions with. A `brain_url` sets `mode="inbound"`. |
| `create_agent_credentials` | `(tenant, agent_id, label="") -> {agent_id, agent_secret, cortex_url, key_id, expires, instructions, usage}` | Mint credentials for a brain that dials out over Cortex (local development, serverless, egress-only networks), and switch the agent to `cortex` mode. `agent_secret` is an `sk_` shown once that never expires; `usage` carries the environment variables and the `serve` call to paste. Minting revokes nothing: rotate by minting, redeploying, then `revoke_api_key` on the old one. See [Deploy the brain](/build/hosting/#a-brain-that-dials-out). |
| `get_agent` | `(tenant, agent_id) -> agent` | One agent. |
| `list_agents` | `(tenant, status=None, limit=20, cursor="") -> {agents, next_cursor}` | Agents, archived included. `status` is `active` or `archived`; anything else is refused. `limit` is capped at 100; a null `next_cursor` is the last page. |
| `update_agent` | `(tenant, agent_id, name="", description="", brain_url="", mode="", recording=None) -> agent` | Owner or admin only. Rename, re-describe, set the `brain_url`, or set the [recording](/operate/recordings/) default (`recording=None` leaves it). A `brain_url` sets `mode="inbound"`; `mode="cortex"` drops the `brain_url`. You rarely pass `mode`. |
| `archive_agent` | `(tenant, agent_id) -> agent` | Refuse new sessions with `agent_archived`, keeping the agent and its history. Sessions in progress continue. New credentials are refused while archived. |
| `unarchive_agent` | `(tenant, agent_id) -> agent` | Admit new sessions again, with the existing credentials. |

A `brain_url` must be `wss://` (`ws://` only for `localhost` and `127.0.0.1`).
An agent with neither a `brain_url` nor Cortex credentials refuses every session
with `409 agent_not_configured`. A `brain_url` nothing listens on is accepted,
the user hears the unreachable line, and `stage` stays `configured`.

## Keys

A key row is `id`, `kind`, `label`, `prefix`, `agent_id`, `agent_name`,
`allowed_origins`, `status`, `created_at`, `revoked_at`, `last_used_at`. The raw
value appears only on the response that minted it.

| Tool | Signature | Does |
|---|---|---|
| `create_api_key` | `(tenant, agent_id, label, kind="secret", allowed_origins=None) -> key + {value, note}` | Mint another key for one agent: `kind="secret"` (`sk_`, for your server) or `"publishable"` (`pk_`, for a browser page; pass its origins). `value` is shown once. |
| `list_api_keys` | `(tenant, include_revoked=False, agent_id="") -> {keys}` | Keys, newest first, prefixes only. Not paged. `agent_id` narrows to one agent. |
| `revoke_api_key` | `(tenant, key_id) -> {ok, revoked, key}` | Revoke a key. Irreversible. |
| `update_api_key_origins` | `(tenant, key_id, allowed_origins) -> key` | Replace a publishable key's origins. Send the **complete** list. |

Which key goes where is [Keys and authentication](/build/keys/).

## Sessions

A session row is `id`, `state`, `agent_id`, `agent_name`, `display_name`,
`created_at`, `started_at`, `ended_at`, `duration_secs`, `end_reason`, `error`.

| `state` | Means |
|---|---|
| `starting` | The session is minted and nobody has connected yet. |
| `active` | The user is connected. |
| `ended` | The session ended cleanly; `end_reason` says why. |
| `failed` | The session ended on a failure; `end_reason` says which. |
| `expired` | Nobody connected before the session token lapsed. |
| `lost` | The session connected and its end was never reported: it was still `active` five minutes past the one-hour cap. |

`end_reason` is set on `ended` and `failed` only. It is one of `user_hung_up`,
`user_dropped` (the user's audio stopped without a hangup), `agent_hung_up`,
`idle_timeout`, `max_duration` (the one-hour cap), `brain_disconnected`,
`brain_unreachable`, `never_connected` or `runtime_error`. A report that arrives
after a session read `expired` or `lost` replaces that state.

| Tool | Signature | Does |
|---|---|---|
| `list_sessions` | `(tenant, agent_id="", state=None, since=None, until=None, include_archived=False, limit=20, cursor="") -> {sessions, next_cursor}` | Sessions, newest first. Filter by agent, by one `state`, and by `created_at`: `since` inclusive, `until` exclusive, ISO-8601 with an offset; a `since` in the future is refused. Archived sessions are left out unless `include_archived=True`. `limit` is capped at 100. A page can be short while `next_cursor` is set; only a null `next_cursor` is the last page. |
| `get_session` | `(tenant, session_id) -> session` | One session in full: the row above plus `started_by`, `source` and `invite_id` (set on a Site Agent preview), `metadata`, the resolved `config`, `init`, a `recordings` summary (`id`, `role`, `state`, `duration_secs`, `failure_reason`), `video_stats`, and `files`. `files` says what became of the `call_record`, the `logs` and the `recording`; see [Reading a call back](/operate/reading-a-call/#whether-each-file-arrived). It is null until the session ends. |
| `get_call_record` | `(tenant, session_id, limit=2000, include_events=False) -> {session_id, record, turns, pace, meta, …}` | **The contract**: what your brain and the user exchanged, turn by turn. `record` is `found`, `missing` or `unavailable`; read it before concluding a session was silent. `include_events=True` adds the raw messages under the turns; `limit` bounds those, never the turns. |
| `get_session_events` | `(tenant, session_id) -> {session_id, events: [{occurred_at, event_type, id, actor_id, actor, payload}]}` | Voqalize's milestones (created, connected, ended), written while the session runs, so they answer for a session in progress. `actor` is `{id, email, name}` when a person acted, `null` when Voqalize did. |
| `get_session_logs` | `(tenant, session_id, level="INFO", service="", limit=500) -> {session_id, logs, logs_availability, truncated}` | Voqalize's log lines for the session. `level` is a floor (`DEBUG` to `CRITICAL`); `service` matches one process's lines exactly; `limit` is capped at 5000. |
| `get_recordings` | `(tenant, session_id, ttl_seconds=1200) -> {session_id, recordings}` | One entry per recorded `role`, each with `state`, `content_type`, `size_bytes`, `started_at`, `ended_at`, `duration_secs`, `failure_reason`, `capture_object`, `timeline` (video lanes only) and, on entries with a file, a signed `download_url` and its `download_url_expires_at`. `ttl_seconds` is 60 to 1200. See [Recordings](/operate/recordings/). |
| `get_usage` | `(tenant, period="") -> {tenant_id, period, sessions_created, sessions_started, sessions_completed, sessions_failed, duration_secs, agents}` | Counters for one `YYYY-MM` period in UTC (empty is the current month), with `agents` the same numbers per agent, busiest first. See [Usage and limits](/operate/usage/). |
| `update_session` | `(tenant, session_id, display_name="", metadata=None) -> session` | Label a session and set your own `metadata`. `metadata` **replaces** the whole map. |
| `archive_session` | `(tenant, session_id) -> session` | Take an ended session out of the default list. Its record, events and recordings are kept. A session in progress is refused, and no tool ends one. |

Every read is keyed on a `session_id`, the same id in your connect response, in
`{brain_url}?session_id={session_id}` and in your brain's logs. There is no
free-text log search. The order to read them in is
[Reading a call back](/operate/reading-a-call/).

## Members

A member row is `id`, `user_id`, `email`, `full_name`, `role`, `status`,
`added_by`, `added_by_user`, `added_at`, `updated_at`.

| Role | May |
|---|---|
| `owner`, `admin` | Everything below, plus: create, update, archive and restore agents; mint and revoke keys and Cortex credentials; add, re-role and remove members; read the audit log. |
| `member` | Read agents, sessions, call records, logs, recordings and usage; start sessions from the Playground. |

A member who tries an owner's or admin's action gets the tool error for a role
that is too low, and the console shows the control disabled with the reason.

| Tool | Signature | Does |
|---|---|---|
| `add_member` | `(tenant, email, full_name="", role="member") -> member` | A **grant, not an invitation**: nothing is emailed, and whoever signs in with that address reaches every agent, session, recording and key in the tenant at once. Tell the person yourself, and grant the narrowest role that works. |
| `list_members` | `(tenant, limit=50, cursor="") -> {members, next_cursor}` | The roster, paged. |
| `update_member_role` | `(tenant, member_id, role) -> member` | Change one member's role. |
| `remove_member` | `(tenant, member_id) -> member` | Take someone off the tenant. |

## Audit log

| Tool | Signature | Does |
|---|---|---|
| `list_audit_events` | `(tenant, action="", actor_id="", resource_id="", since=None, until=None, limit=20, cursor="") -> {events, next_cursor}` | The workspace's audit log, newest first. Owner or admin only. One record per change a member or key made (an agent created or updated, a key minted or revoked, a member added) and per console sign-in (`auth.sign_in`, with the provider and browser in `after`). Each carries `actor_email` and `actor_role` as they were at the time (`actor_label`, the key's label, when a key made the change), `source_ip` (null for a background task), and `before` and `after`. `action`, `actor_id` and `resource_id` match exactly, and `resource_id` gives one thing's history; `actor_id` and `resource_id` cannot be combined; `since` is inclusive and `until` exclusive. `limit` is capped at 100. Records are kept for 400 days. The console shows the same log under **Settings → Audit log**. |

## Site Agent tools

These tools serve the Site Agent, Voqalize's hosted agent that answers visitors
on a website you name; a voice agent you build does not need them. They manage
its sites: what a site knows is edited through a draft, checked, reviewed, then
published as a version. Each tool's own description, which your coding agent
reads, has the arguments in full.

Every tool takes `tenant` first and answers with an object. The pages under
[The Site Agent](/build/site-agent/) explain each step, and who may take it.

| Tool | Signature | Does |
|---|---|---|
| `create_site` | `(tenant, website, robots_acknowledgement_version="", languages=None, default_language="", name="")` | Create a site for a website and start its first study. Answers with the site, its live key's snippet (shown once) and the first study. `languages` defaults to `["english"]`. See [robots.txt](/build/site-agent/security/#robotstxt) and [If your site blocks automated visitors](/build/site-agent/security/#if-your-site-blocks-automated-visitors). |
| `list_sites` | `(tenant, limit=20, cursor="", include_archived=False)` | A tenant's sites, with the published and latest versions and any study in progress. `limit` is capped at 100. |
| `get_site` | `(tenant, site_id, versions_cursor="")` | One site with its settings, its versions 10 to a page, and any study in progress. |
| `get_site_version` | `(tenant, site_id, version)` | One stored version: its review state, checks, conflicts and review flags. |
| `update_site_settings` | `(tenant, site_id, settings, expected_updated_at="")` | Change a site's settings with a JSON merge patch. See [Settings](/build/site-agent/settings/). |
| `read_site_knowledge` | `(tenant, site_id, part, version=None, cursor="", limit=None)` | Read one part of a version, a page at a time: 12,000 characters by default, 1,000 to 40,000. `version` defaults to the published one. |
| `start_knowledge_edit` | `(tenant, site_id, base_version=None)` | Open a draft from a stored version, the published one by default. See [Edit the knowledge](/build/site-agent/knowledge/). |
| `edit_knowledge` | `(tenant, site_id, ops, expected_revision)` | Apply up to 50 operations to the open draft, all or none, and return its checks. |
| `check_knowledge_edit` | `(tenant, site_id)` | Run the open draft's checks again. |
| `get_draft_bundle` | `(tenant, site_id)` | A link to the open draft as a `tar.gz`, valid for ten minutes. |
| `submit_knowledge_edit` | `(tenant, site_id, owner_tested=False)` | Turn the open draft into a new version, waiting for review. |
| `discard_knowledge_edit` | `(tenant, site_id)` | Throw the open draft away. |
| `review_site_version` | `(tenant, site_id, version, decision, resolutions=None, notes="", publish_anyway=None)` | Approve or reject a version. See [Review in full](/build/site-agent/refresh/#review-in-full). |
| `publish_site_version` | `(tenant, site_id, version, confirm=False, publish_anyway=None)` | Without `confirm`, show what publishing would change; with it, serve the version to every visitor. Publishing a `superseded` version rolls back. |
| `start_self_study` | `(tenant, site_id)` | Start a study that your own coding agent runs. See [Self studies](/build/site-agent/self-study/). |
| `get_self_study` | `(tenant, site_id, run_id)` | A self study as it stands, with its upload link. |
| `submit_self_study` | `(tenant, site_id, run_id, bundle_sha256, kit_version, grader=None, owner_tested=False)` | Check the uploaded bundle and store it as a version. |
| `cancel_self_study` | `(tenant, site_id, run_id)` | Cancel a self study, freeing the site for another. |
| `create_site_invite` | `(tenant, site_id, label, days=14, minutes=60)` | Invite someone outside your tenant to try the site's preview: 1 to 90 days, 1 to 1000 voice minutes. See [Previews and invites](/build/site-agent/preview/). |
| `list_site_invites` | `(tenant, site_id)` | A site's preview invites, newest first, with their use. |
| `revoke_site_invite` | `(tenant, site_id, invite_id)` | Revoke a preview invite and every preview key made from it. |

## Read next

- [Work with a coding agent](/build/coding-agent/): the end-to-end flow with these tools.
- [Reading a call back](/operate/reading-a-call/): the record first, then the logs.
- [Deploy the brain](/build/hosting/): inbound or Cortex.
