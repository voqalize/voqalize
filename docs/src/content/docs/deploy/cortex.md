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

Cortex is a stateless, schema-free WebSocket relay with exactly two routes:

- The voice runtime lands on `/s/{session_id}`.
- Your brain dials *out* to `/agent`.

Both legs authenticate to the same tenant-and-agent **rendezvous scope**, and Cortex
matches them on that — derived from the credentials, not from the URL. There is
nothing to encode in a path and nothing to configure. Cortex holds no state; kill it
any time and both sides reconnect. Many sessions multiplex over your one outbound
socket, demuxed by a 16-byte session prefix.

## Get the credentials

Self-service, over the [MCP server](/docs/reference/mcp/):

```
create_agent_credentials(tenant, agent_id, label="")
```

It returns three things you use in three different places:

| Field | Where it goes |
|---|---|
| `agent_secret` | `ak_…` — the SDK's `api_key=`. **Shown once**, never recoverable. |
| `cortex_url` | The SDK's `cortex_url=`. It already ends in `/agent` — pass it verbatim; the SDK does not append. |
| `brain_url` | The Cortex origin. This is what the **agent's** `brain_url` must become. |

Wiring the `brain_url` is **not** automatic:

```
update_agent(tenant, agent_id, brain_url="<the brain_url it returned>")
```

Until you do, the agent still points wherever it pointed before. The `ak_` never
expires; minting revokes nothing, so rotation is mint → redeploy → `revoke_api_key`
on the old one, with no window where the agent can't connect.

## Serving over Cortex

The same `Brain` class runs over Cortex; only the entrypoint changes.

### Python

```python
from voqalize.sdk import CortexAgent, brain_factory
from mybrain import MyBrain

agent = CortexAgent(
    version="1.0.0",
    cortex_url="wss://cortex.dev.voqalize.com/agent",   # verbatim, from the tool
    factory=brain_factory(MyBrain),
    api_key="ak_…",     # OR authorization_provider=lambda: "Bearer <jwt>"
)
await agent.run()        # returns when the wire closes permanently
```

Pass **exactly one** credential: a static `api_key` (`ak_…`), or an
`authorization_provider` that mints a `"Bearer <jwt>"` per connect. `serve(MyBrain,
...)` is the sugar wrapper; `serve_auto(MyBrain, mode="cortex")` selects this
transport from `$VOQAL_AGENT_MODE`.

## No tunnel needed

Because the brain dials out, Cortex needs no public inbound route and no tunnel —
which is why it fits serverless and egress-only environments, and why it is the
fastest way to develop against the hosted platform from a laptop. Export the
credentials and run:

```bash
export VOQAL_AGENT_SECRET=ak_...                              # agent_secret
export VOQAL_CORTEX_URL=wss://cortex.dev.voqalize.com/agent   # cortex_url, verbatim
export VOQAL_AGENT_MODE=outbound
python run_cortex.py
```

`$VOQAL_AGENT_MODE` is the only one of the three the SDK reads itself — `serve_auto`
uses it to pick the transport (`outbound`/`cortex` vs `inbound`/`direct`). The other
two are conventions your code passes through as the kwargs above.

## Crash-only

Cortex keeps no session state — that lives in the endpoints (the runtime's session
and your brain). There's no drain protocol and no graceful-shutdown contract: if
Cortex dies, both sides reconnect and carry on.

## Next

- **[Inbound server](/docs/deploy/inbound/)** — the primary path.
- **[Where the brain runs](/docs/deploy/brain-url/)** — choosing between them.
