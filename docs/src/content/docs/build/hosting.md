---
title: Where the brain runs
description: The brain_url is a single WebSocket URL. Choose between an inbound server and a Cortex relay — same brain code either way.
---

An agent's brain is one setting: `deployment.brain_url`, a single WebSocket URL.
When a call starts, Voqalize dials `{brain_url}?session_id={session_id}`
— one connection per session, opened just-in-time and torn down when the call
ends.

Nothing on our side interprets where that URL points. Your
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
more authenticated WebSocket route is trivial, and it keeps Voqalize dialing you
directly with no relay in the path. See [Inbound server](/build/inbound/).

Reach for **Cortex** only when your brain genuinely can't accept inbound
connections — a serverless function, a process on a laptop behind NAT, or a
network that only allows egress. Your brain dials out to Cortex, which splices the
two legs on a scope it derives from the **credential each leg presents** — never
from the URL, so nothing an attacker can type decides who gets your sessions. See
[Cortex relay](/build/outbound/).

## Setting the `brain_url`

Point an agent at your brain with the MCP server:

```text
update_agent(tenant="acme", agent_id="06a2…", brain_url="wss://brain.example.com")
```

There is no `set_brain_url` tool — `brain_url` is a field on the agent, set with
`create_agent` up front or `update_agent` later.

Rules:

- It must be `wss://` (plain `ws://` is allowed only for `localhost`).
- Give the URL of your route, path and all — Voqalize uses it verbatim and
  appends only `?session_id=`. For Cortex, it's the Cortex origin exactly as
  `create_agent_credentials` returned it.
- Changing `brain_url` never touches the agent's STT/TTS config.

An **empty** `brain_url` falls back to a hosted `welcome` brain, so a freshly
created agent still greets while you build the real one.

## The brain-connection token

However the connection is made, Voqalize presents the same credential: **the
brain-connection token**, a short-lived RS256 JWT whose `sub` is the
`session_id`. It is the same token on both paths, verified the same way, and the
SDK verifies it for you against Voqalize's embedded public keys.

That name is the one to remember. It is what `mint_voqalize_token` mints in
[Testing a brain](/build/testing/), what your route passes through in
[Inbound server](/build/inbound/), and the claims are written out once in
[The wire](/reference/wire/).
