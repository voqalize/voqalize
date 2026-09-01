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
| **Status** | Default deployment | Supported; default for local development |

Both paths run the **same per-session engine** and the **same `Vql*` wire**. A
brain written for one runs on the other unchanged.

## Choosing

Use **inbound** for the standard deployment when your backend can expose an
authenticated WebSocket route. Voqalize then dials your application directly.
See [Inbound server](/build/inbound/).

Use **Cortex** for local development or when the brain cannot accept inbound
connections, such as a serverless function, a laptop behind NAT or an
egress-only network. Your brain dials out to Cortex, which matches both legs
from their credentials. See [Cortex relay](/build/outbound/).

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
  appends only `?session_id=`. Setting it puts the agent in `inbound` mode.
- On Cortex you set no URL at all: `create_agent_credentials` switches the agent
  to `cortex` mode and holds the relay address itself.
- Changing `brain_url` never changes a session's STT/TTS configuration; that is
  supplied at connect or by the brain while the call runs.

**An agent with no brain cannot take a call.** `sessions.connect` refuses it with
`409 agent_not_configured` before anything is minted, and `get_agent` reports its
`stage` as `unconfigured`.

That is a deliberate reversal. An empty `brain_url` used to fall back to a hosted
`welcome` brain, so a freshly created agent still greeted while you built the real
one — and a call that connected, sounded right and answered was no evidence at all
that your code had run. A configuration step you can skip without seeing anything
break is a step that gets skipped.

## The brain-connection token

However the connection is made, Voqalize presents the same credential: **the
brain-connection token**, a short-lived RS256 JWT whose `sub` is the
`session_id`. It is the same token on both paths, verified the same way, and the
SDK verifies it for you against Voqalize's embedded public keys.

That name is the one to remember. It is what `mint_voqalize_token` mints in
[Testing a brain](/build/testing/), what your route passes through in
[Inbound server](/build/inbound/), and the claims are written out once in
[The wire](/reference/wire/).
