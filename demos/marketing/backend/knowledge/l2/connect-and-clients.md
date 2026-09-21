# L2 — connect, clients and the MCP server

Read when: the handshake, either credential path, the origin allowlist, pipecat
versions and packages, mobile, local development, or what the MCP server can do.

## The handshake

One HTTP call, then stock pipecat.

`POST /api/v1/sessions.connect` — body:

- `agent_id` — required. Selects the brain URL and the recording default.
- `init` — opaque blob, handed to the brain as `session.init` and stored with the
  session. Send identifiers, not PII; it is stored, and retained for 30 days.
- `config` — `tts`, `stt`, `idle`, `record`.
- `display_name` — shown in the console.
- `metadata` — your own tags for later filtering. Keys capped at ten, values at
  256 characters.

Strict body: an undeclared key is `422`, not ignored. That is deliberate — a
typo'd option is a silent wrong behaviour otherwise.

Response carries `webrtc_request_params` and `session_id`, nothing else. Forward
`webrtc_request_params` verbatim into pipecat's transport.

**The endpoint is a machine, not a load balancer.** The control plane picks the
PyGato node at mint time and the address is in the response, so it cannot be
hard-coded in the page. Media is direct UDP to that node — no SFU, no relay of
ours in the media path.

## The credential paths

- **`sk_` from your backend.** Your server holds the secret key, authenticates
  your user however it already does, and mints the session. The browser never
  sees a Voqalize credential. This is the path for anything real.
- **`pk_` from the page.** Publishable, origin-allowlisted, safe in page source.
  The allowlist must be non-empty; empty denies every request. A `pk_` may turn
  recording **off** for a call and may not turn it **on** — a page-embedded key
  cannot start recording a user.

Each names exactly one agent. There is no tenant-wide key; the one that existed
(`ak_`) was removed on 2026-08-12.

## The client is pipecat

There is no Voqalize client library, and that is the integration story rather
than a gap. The browser uses pipecat's `SmallWebRTCTransport` — the same
transport the console uses in production, with no transport or signalling code of
ours on top.

- Web: pipecat's JavaScript/React client packages.
- React Native, iOS, Android: pipecat's own client SDKs cover them; this is not a
  webview-only story. Whatever pipecat's client matrix supports, Voqalize
  supports, because the transport is stock.
- Version guidance and the exact package names live in the docs at
  `/build/pipecat` — check there rather than pinning from memory, because the
  supported range moves with pipecat.

The avatar (`@voqalize/avatar`) and the transport helper
(`@voqalize/client-transport`, MIT, an open implementation of pipecat's
`MediaManager` for `SmallWebRTCTransport`) are optional additions, each usable
against any pipecat agent.

`voqalize types` generates the TypeScript unions for your own UI actions and app
events; see `wire-and-brain.md`.

## Local development

Yes, a brain can be developed without exposing anything. **Cortex mode is the
local-development default**: the brain dials *out* to the relay, so a laptop
behind NAT needs no tunnel and no inbound port. Same brain code as production;
only who dials whom changes.

The cloud is still in the loop for WebRTC and speech — the voice tier is not
something that runs on a laptop. What local development means here is that your
code, your models and your data stay local while the call works end to end.

## The MCP server

`app.voqalize.com/mcp`, **OAuth**, not a bearer key. Paste the URL into a coding
agent and it becomes the management surface.

Setup *and* runtime reads:

- `create_agent`, `update_agent`, `get_agent`, `list_agents`, archive/unarchive
- `create_api_key`, `list_api_keys`, `revoke_api_key`, `update_api_key_origins`,
  `create_agent_credentials`
- `list_sessions`, `get_session`, `get_call_record`, `get_session_logs`,
  `get_session_events`, `get_recordings`, `get_usage`
- tenants and members

So a coding agent can create the agent record, mint the key, set `brain_url`,
then read back the logs of the call it just made and fix the brain. That loop is
the reason the MCP server exists.

Rate limit: 120 tool calls per minute per tenant. The management REST API is
separately rate limited per tenant and answers `429` with `Retry-After`.

Start by calling `whoami`, then `list_tenants`, and pass the chosen tenant's
slug as `tenant`.
