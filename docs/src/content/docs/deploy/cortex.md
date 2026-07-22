---
title: Cortex relay
description: The fallback path for brains that can't accept inbound connections — your brain dials out to a relay.
---

Cortex is the fallback for brains that **can't accept inbound connections**:
serverless functions, a process on a laptop behind NAT, or a network that only
allows egress. Instead of the runtime dialing you, your brain dials *out* to a
Cortex relay, which splices the two legs together.

:::note[Prefer inbound when you can]
The relay adds a hop and a moving part. If your brain can expose an authenticated
WebSocket route, use the [inbound path](/docs/deploy/inbound/) instead. Reach for
Cortex only when inbound genuinely isn't possible.
:::

## How it works

Cortex is a stateless, schema-free WebSocket relay. It has two sides:

- The voice runtime connects on one side at `/s/{session_id}`.
- Your brain connects on the other, dialing *out* to a Cortex URL that carries your
  agent's **pool key** in the path: `{cortex_url}/{pool}/s/{session_id}`.

Cortex matches the two legs by pool key and forwards frames between them. It holds
no state — kill it any time and both sides reconnect. Many sessions multiplex over
your one outbound socket, demuxed by a 16-byte session prefix.

Your `brain_url` for a Cortex agent is the Cortex URL with the pool key in the
path. Scaling out means handing the agent a different Cortex URL — routing lives in
the URL, not in a token.

## Serving over Cortex

The same `Brain` class runs over Cortex; only the entrypoint changes.

### Python

```python
from voqalize.sdk import CortexAgent, brain_factory
from mybrain import MyBrain

agent = CortexAgent(
    version="1.0.0",
    cortex_url="wss://cortex.voqalize.com/<pool>",
    factory=brain_factory(MyBrain),
    api_key="ak_…",     # OR authorization_provider=lambda: "Bearer <jwt>"
)
await agent.run()        # returns when the wire closes permanently
```

Pass **exactly one** credential: a static `api_key` (`ak_…`), or an
`authorization_provider` that mints a `"Bearer <jwt>"` per connect. `serve(MyBrain,
...)` is the sugar wrapper; `serve_auto(MyBrain, mode="cortex")` selects this
transport from `$VOQAL_AGENT_MODE`.

### Go

```go
agent, _ := cortex.New(cortex.Options{
    Version:   "1.0.0",
    CortexURL: "wss://cortex.voqalize.com/<pool>",
    APIKey:    "ak_…",            // OR AuthorizationProvider: func() string { ... }
    Logger:    logger,
}, brain.Factory(func() brain.Brain { return &MyBrain{} }, logger))
agent.Run(ctx)
```

## No tunnel needed

Because the brain dials out, Cortex needs no public inbound route and no tunnel —
which is exactly why it fits serverless and egress-only environments. Set the
outbound credentials (`VOQALIZE_AGENT_SECRET`, `VOQALIZE_CORTEX_URL`) and run.

## Crash-only

Cortex keeps no session state — that lives in the endpoints (the runtime's session
and your brain). There's no drain protocol and no graceful-shutdown contract: if
Cortex dies, both sides reconnect and carry on.

## Next

- **[Inbound server](/docs/deploy/inbound/)** — the primary path.
- **[Where the brain runs](/docs/deploy/brain-url/)** — choosing between them.
