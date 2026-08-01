---
name: voqalize
description: >-
  Build a voice agent on Voqalize end-to-end. Use when the developer wants to add
  voice/phone/talk-to-my-app capability, build a voice agent or voice bot, or
  mentions Voqalize. Guides you to scaffold a "brain" (a WebSocket the SDK runs),
  choose the inbound (direct) or Cortex (outbound) transport, create the agent
  over the Voqalize MCP server, wire its brain_url, mint a browser key, and embed
  the React widget. Requires the hosted `voqalize` MCP server (Google-OAuth HTTP).
---

# Build a voice agent on Voqalize

Voqalize is a **voice operator that lives inside the app** — it drives the UI,
reads live state, and does the work. The developer writes the **brain** — a `Brain`
subclass that receives transcribed user turns and speaks replies (and can drive the
screen). Voqalize's runtime (PyGato) handles WebRTC, VAD, speech-to-text,
text-to-speech, interruption, and recording. Brain and runtime talk over **one
WebSocket per session**, carrying text frames — the brain never touches audio.

Your job across a session with the developer: **scaffold the brain → pick the
transport → create the agent (MCP) → wire `brain_url` → run + test → mint a
browser key → embed the React widget → iterate.**

## Prerequisites (check first)

1. The **`voqalize` MCP server** is connected. It's a hosted HTTP endpoint
   (`https://app.voqalize.com/mcp`) added with
   `claude mcp add --transport http voqalize https://app.voqalize.com/mcp` (or the
   `.mcp.json` in this skill folder) — **no key to configure**; first use runs a
   browser Google sign-in. Run `whoami` (identity), then `list_tenants` to get the
   `tenant` slug — **every scoped tool takes a required `tenant` argument.** If the
   developer has no tenant yet, `create_tenant` makes one (and seeds demo agents).
   Do not proceed until `whoami` succeeds.
2. Python ≥ 3.12 for the brain. Node + a React app if they want the browser embed.

## Step 1 — Understand the use case, draft the brain

Ask what the agent should do (support bot, lead qualifier, booking assistant, …),
what data/tools it needs, and what it should say first. Then scaffold from
`templates/brain.py` — a `Brain` with:

- `on_session_start(session, start)` — the greeting (agent speaks first).
  `start.init` is the app payload the browser sent at connect (see Step 6's
  `payload=`) — the logged-in user, their current cart, etc.
- `on_interaction(interaction)` — one user turn. `interaction.transcript` is the
  heard text; open `interaction.say()` and `speak(...)` or stream an LLM.
- `on_client_message(session, message)` — a message the browser sent up (a tap, a
  state sync). Needed for any UI the user also touches by hand. `message.type` is
  the name, `message.data` the payload. Read them and return to ingest silently;
  touch `message.interaction` to take the floor and answer.
- `on_user_idle(interaction)` — the user went silent past the idle timeout and you
  hold the floor to re-engage (`interaction.idle.level` escalates while the silence
  persists). Set it with `session.configure_idle(timeout_ms=…)`; `0` disables it.

**If the agent drives the screen** (a shopping cart, a form, a map) it also calls
`interaction.action(name, {...})` to push commands to the browser — see
[UI actions](#ui-actions-the-two-way-contract) for the exact wire shape both ways.

Keep the first version tiny (greet + echo, or greet + one canned reply) so you can
prove the pipe before adding an LLM or tools. The SDK is **pipecat-free** (pulls no
audio deps). **Pre-release: it isn't on PyPI yet** — install it editable from the
Voqalize agent-sdk source (`pip install -e path/to/agent-sdk`, or
`uv add --editable path/to/agent-sdk`). Once published the name will be
`voqalize-agent-sdk`.

## Step 2 — Pick the transport: inbound (direct) vs Cortex (outbound)

This is the one real decision. **Default to inbound.**

| | **Inbound / direct (PRIMARY)** | **Cortex / outbound (fallback)** |
|---|---|---|
| Who dials whom | PyGato dials **into** your brain | Your brain dials **out** to Cortex |
| You run | one authenticated `wss://` route (like any webhook) | a process holding an outbound socket |
| `brain_url` | your route: `wss://your-host/…` | the platform's single Cortex URL — same for every agent, no per-agent path |
| Use when | you can expose an inbound HTTPS/WSS endpoint (you already run a web backend) | serverless/FaaS, a laptop, or strict egress-only / air-gapped networks that **can't** accept inbound |
| Template | `templates/inbound_app.py` (FastAPI) | `templates/run_cortex.py` |

Rule of thumb: **if they already run a web/mobile backend, use inbound** — one WS
route is trivial and there's no relay in the path. Only reach for Cortex when an
inbound endpoint is genuinely impossible.

⚠️ **Cortex isn't self-serviceable through this MCP tool surface yet.** A Cortex
brain authenticates with an `ak_…` agent credential (not the `sk_…` this skill's
`create_agent` mints — see Step 3), and today the only code path that mints an
`ak_` + hands back the Cortex URL is the control-plane REST call
`POST /api/v1/{tenant}/agents.create`, which is gated on an interactive console
browser session — no MCP tool exposes it. If a developer genuinely needs Cortex,
say so plainly (get the `ak_`/Cortex URL from whoever provisions them for the
tenant) rather than improvising a working-looking flow — default to inbound.

## Step 3 — Create the agent (MCP)

Call the MCP tool `create_agent` with your `tenant` slug, a `name` (and optional
`description`, and `brain_url` if you already have it). The response is
`{agent, session_key}`:

- `agent.id` — you'll need it to set the brain URL.
- `session_key.value` (`sk_…`) — a tenant-scoped secret, shown once, that your
  own backend can use as a Bearer token to start test sessions
  (`POST /api/v1/{tenant}/sessions.create_and_start`). Store it now — never
  commit it. This is **not** the Cortex `ak_` credential (see the callout in
  Step 2) — it works for both inbound and Cortex agents, but only for starting
  sessions, not for the Cortex outbound leg itself.

You can pass `brain_url` to `create_agent` up front, or leave it and set it in
step 5.

## Step 4 — Run the brain locally, test in the console

You talk to the agent in the hosted Voqalize **console Playground** (or your own
embed from Step 6). The runtime that dials your brain (PyGato) is hosted by
Voqalize, so it must reach your brain over the public internet — a plain
`ws://127.0.0.1` `brain_url` only works if you are *also* running the whole
Voqalize stack locally. For the normal case (hosted Voqalize, brain on your
laptop), expose the local brain with a tunnel:

- **Inbound:** run `templates/inbound_app.py` (uvicorn on `:8080`). Because the
  brain can't verify PyGato's prod-signed token against a tunnel in dev, set
  `VOQAL_ALLOW_UNVERIFIED=true` **locally only** (a deployed brain drops this and
  verifies with zero config). Start a tunnel — e.g. `ngrok http 8080` or
  `cloudflared tunnel --url http://localhost:8080` — and use the `wss://…` URL it
  prints as your `brain_url` (Step 5). PyGato dials `{that}/s/{session_id}`.
- **Cortex:** no tunnel needed — the brain dials *out*. Run
  `templates/run_cortex.py` with `VOQALIZE_AGENT_SECRET` (an `ak_…` agent
  credential) and `VOQALIZE_CORTEX_URL` (the platform's Cortex URL) exported.
  Neither is mintable through this MCP tool surface today (see Step 2's
  callout) — get both from whoever provisions Cortex credentials for the
  tenant. This is why Cortex exists: brains that can't accept inbound (a
  laptop with no public URL) still work.

Then set the brain URL (Step 5) and open the agent in the Voqalize console
Playground to talk to it. (Deploying for real? Skip the tunnel — give the brain a
real public `wss://` host and point `brain_url` at that.)

## Step 5 — Wire `brain_url` (MCP)

Set it on `create_agent` up front, or later with
`update_agent(tenant, agent_id, brain_url=…)` — there is no separate `set_brain_url`
tool:

- Inbound: your route's base — PyGato appends `/s/{session_id}`. `wss://` in
  production; `ws://` allowed only for `localhost`/`127.0.0.1`.
- Cortex: the platform's Cortex URL (not returned by `create_agent` — see
  Step 2's callout).

An empty `brain_url` falls back to the hosted `welcome` demo brain, so a bare
agent still greets — but to serve *your* brain you must set this.

## Step 6 — Embed in the browser (React)

1. `create_api_key(tenant, label="web", kind="publishable", allowed_origins=["https://your-site.com"])`
   → the `raw` `pk_…` (shown once). Publishable keys are origin-allowlisted and
   safe to ship to the browser; **never** put an `sk_` key in frontend code.
   For **local** testing, include your dev origin in `allowed_origins` too (e.g.
   `["http://localhost:5173"]`) or the browser session mint is rejected. (The
   `sk_` "secret" kind is a server-to-server backend key — you don't need it just
   to embed the widget; `pk_` is the only key the browser uses.)
2. Install `@voqalize/client-react` and drop in `templates/react_embed.tsx`,
   passing the `pk_…` and the `agent.id`. Its four config values:
   - `publishableKey` — the `pk_…` from step 1.
   - `agentId` — `agent.id`.
   - `tenantSlug` — your tenant slug (the one from `list_tenants` that you pass to
     every MCP tool).
   - `apiBase` — the control-plane root **including the API version**; the React
     SDK appends `/{tenantSlug}/…`. Production: `https://app.voqalize.com/api/v1`.
     ⚠️ Point it at the bare host (no `/api/v1`) and the browser session mint fails.

<a id="ui-actions-the-two-way-contract"></a>
## UI actions — the two-way contract

For agents that drive the screen (cart, form, map), brain and browser exchange
JSON messages with **fixed shapes**:

**Brain → browser.** The brain calls `interaction.action(name, {...args})` (or
`session.action(...)` outside a turn). The React SDK's `onServerMessage` receives:

```json
{ "type": "ui_command", "action": "add_to_cart", "action_id": 7, "sku": "oat-milk", "qty": 2 }
```

The `args` dict is **spread onto the top level** (not nested under `data`/`args`).
Switch on `msg.action` and read the args as top-level fields. `action(...)` is
**fire-and-forget** — not a coroutine (don't `await` it); the SDK mints the
`action_id` and returns it. It only *messages* the browser; it does **not** persist
anything (writing to your own backend is your brain code's job).

**Browser → brain.** The browser calls the SDK's `session.sendMessage(type, data)`
(exposed by `useVoqalSession` / the `VoqalAgent` render-prop). The brain receives
it as `on_client_message(session, message)` with `message.type == type`,
`message.data == data`. Every client message also carries an `interaction_id` the
platform minted for it — the brain decides whether it warrants a reply: read the
data and return (silent), or touch `message.interaction` to take the floor and
answer on it.

**Action results (optional).** Pass `callback=` to `interaction.action(...)` and
the browser can reply with `sendMessage("action_outcome", {action_id, status,
result})`; the SDK routes it to your callback (matched by `action_id`) instead of
`on_client_message`.

`templates/brain.py` and `templates/react_embed.tsx` show both directions wired to
a cart end-to-end.

## Step 7 — Iterate & observe

Test, gather feedback, refine the brain, redeploy, re-test. To see what happened on
a call, use the observability tools: `list_meetings(tenant)` for recent calls,
`get_meeting` / `list_meeting_events` for one call's detail and timeline, and
`query_logs(tenant, meeting_id)` for the runtime log lines.

## MCP tools you'll use

Identity/workspace: `whoami` · `list_tenants` · `create_tenant`. Agents:
`create_agent` · `get_agent` · `list_agents` · `update_agent` · `archive_agent`.
Keys: `create_api_key` · `list_api_keys` · `revoke_api_key`. Calls/logs:
`list_meetings` · `get_meeting` · `list_meeting_events` · `query_logs`. Every tool
returns the control plane's raw JSON, and every scoped tool takes a required
`tenant`. A `not_authorized` error means you're not a member of that tenant (or your
role is too low); `validation_error` means bad input (e.g. a non-`wss://` `brain_url`
on a non-loopback host).

## Files in this skill

| Path | Use |
|---|---|
| `.mcp.json` | MCP server config the developer copies into their repo. |
| `templates/brain.py` | Starter `Brain` — greet + reply. Transport-agnostic. |
| `templates/inbound_app.py` | FastAPI inbound host (primary path). |
| `templates/run_cortex.py` | Cortex outbound runner (fallback path). |
| `templates/react_embed.tsx` | Browser embed via `@voqalize/client-react`. |
