---
title: Where the brain runs
description: The brain_url is a single WebSocket URL. Choose between an inbound server and a Cortex relay — same brain code either way.
---

An agent's brain is one setting: `deployment.brain_url`, a single WebSocket URL.
When a call starts, the voice runtime dials `{brain_url}/s/{session_id}` — one
connection per session, opened just-in-time and torn down when the call ends.

Neither the runtime nor the control plane interprets where that URL points. Your
brain code is identical regardless. The only choice is **who dials whom**.

## Two paths

| | Inbound server | Cortex relay |
|---|---|---|
| **Who dials** | The runtime dials *into* your route | Your brain dials *out* to Cortex |
| **You expose** | One authenticated `wss://` route | Nothing inbound |
| **Best for** | Any backend that can accept connections | Serverless, laptops, egress-only / air-gapped networks |
| **Scaling** | Your own load balancer | Hand out a different Cortex URL |
| **Status** | Primary — build toward this | Fallback |

Both paths run the **same per-session engine** and the **same `Vql*` wire**. A
brain written for one runs on the other unchanged.

## Choosing

Default to **inbound**. If you already run a web or mobile backend, exposing one
more authenticated WebSocket route is trivial, and it keeps the runtime dialing you
directly with no relay in the path. See [Inbound server](/docs/deploy/inbound/).

Reach for **Cortex** only when your brain genuinely can't accept inbound
connections — a serverless function, a process on a laptop behind NAT, or a
network that only allows egress. Your brain dials out to Cortex, which splices the
two legs by a pool key in the URL. See [Cortex relay](/docs/deploy/cortex/).

## Setting the `brain_url`

Point an agent at your brain with the MCP server:

```text
update_agent(tenant="acme", agent_id="06a2…", brain_url="wss://brain.example.com")
```

There is no `set_brain_url` tool — `brain_url` is a field on the agent, set with
`create_agent` up front or `update_agent` later.

Rules:

- It must be `wss://` (plain `ws://` is allowed only for `localhost`).
- Give the **base** URL — the runtime appends `/s/{session_id}` itself. For
  inbound, that's the base of your route; for Cortex, it's the Cortex URL with your
  pool key in the path.
- Changing `brain_url` never touches the agent's STT/TTS config.

An **empty** `brain_url` falls back to a hosted `welcome` brain, so a freshly
created agent still greets while you build the real one.

## The token every brain sees

However the connection is made, the runtime presents the same short-lived RS256
JWT: `iss=pygato`, `aud="brain"`, `sub=session_id`, plus `tenant_id` / `agent_id`.
Both SDKs verify it against Voqalize's public key for you. Details in
[Core concepts](/docs/start/concepts/#authentication).
