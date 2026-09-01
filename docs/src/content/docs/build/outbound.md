---
title: Cortex relay
description: The fallback path for brains that can't accept inbound connections — your brain dials out to a relay.
---

Cortex is the fallback for brains that **can't accept inbound connections**:
serverless functions, a process on a laptop behind NAT, or a network that only
allows egress. Instead of Voqalize dialing you, your brain dials *out* to a
Cortex relay, which splices the two legs together.

:::note[Prefer inbound when you can]
The relay adds a hop and a moving part. If your brain can expose an authenticated
WebSocket route, use the [inbound path](/build/inbound/) instead. Reach for
Cortex only when inbound genuinely isn't possible.
:::

## How it works

Cortex is a stateless, schema-free WebSocket relay with exactly two routes:

- The voice runtime lands on `/?session_id={session_id}`.
- Your brain dials *out* to `/agent`.

Both legs authenticate to the same tenant-and-agent **rendezvous scope**, and Cortex
matches them on that — derived from the credentials, not from the URL. There is
nothing to encode in a path and nothing to configure. Cortex holds no state. Many
sessions multiplex over your one outbound socket, demuxed by a 16-byte session
prefix.

## Get the credentials

Self-service, over the [MCP server](/reference/mcp/):

```
create_agent_credentials(tenant, agent_id, label="")
```

It returns two things:

| Field | Where it goes |
|---|---|
| `agent_secret` | `sk_…` — the SDK's `api_key=`. The same kind `create_agent` gave you; **shown once**, never recoverable. |
| `cortex_url` | The SDK's `cortex_url=`. It already ends in `/agent` — pass it verbatim; the SDK does not append. |

**Calling this switches the agent to `cortex` mode.** There is no URL to copy
back: the address Voqalize dials to reach the relay is ours, and we hold it.

It used to return that address as a third field, `brain_url`, for you to paste
into a second call:

```
update_agent(tenant, agent_id, brain_url="<the brain_url it returned>")
```

Nothing in that step was a decision — we computed the value from our own settings
and asked you to type it back — and until you did, the agent still pointed
wherever it pointed before. A call still connected, so the relay looked broken
when it had never been wired in. The step is gone.

Keys never expire, and minting revokes nothing, so rotation is mint → redeploy →
`revoke_api_key` on the old one, with no window where the agent can't connect.

## Serving over Cortex

The same `Brain` class runs over Cortex; only the entrypoint changes.

### Python

```python
from voqalize.sdk import serve
from mybrain import MyBrain

await serve(
    MyBrain,            # or a () -> Brain callable, if the brain takes dependencies
    version="1.0.0",
    cortex_url="wss://cortex.dev.voqalize.com/agent",   # verbatim, from the tool
    api_key="sk_…",     # OR authorization_provider=lambda: "Bearer <jwt>"
)                       # returns when the wire closes permanently
```

**`version` and `cortex_url` are required**, and the signature will not tell you
so — `serve` takes `**cortex_kwargs` and forwards them, so omitting one is a
`TypeError` from a constructor you did not call rather than from the line you
wrote. `version` is a string of yours; it travels as `X-Agent-Version` on the
connect and is how you tell which build answered a call.

Pass **exactly one** credential: a static `api_key` (`sk_…`), or an
`authorization_provider` that mints a `"Bearer <jwt>"` per connect. Passing both,
or neither, raises at construction.

`serve` **blocks** for the life of the relay connection. Where that call lives —
`asyncio.run` in a `__main__`, a task in your app's lifespan, a worker entrypoint —
is yours to decide; the SDK owns no process management.

## No tunnel needed

Because the brain dials out, Cortex needs no public inbound route and no tunnel —
which is why it fits serverless and egress-only environments, and why it is the
fastest way to develop against hosted Voqalize from a laptop. Export the
credentials and run:

```bash
export VOQALIZE_AGENT_SECRET=sk_...                              # agent_secret
export VOQALIZE_CORTEX_URL=wss://cortex.dev.voqalize.com/agent   # cortex_url, verbatim
python run_cortex.py
```

Both names are **yours**, not ours: your code reads them and passes them through
as the kwargs above. The SDK reads exactly one environment variable of its own,
and it is the Gemini adapter's model default — see
[The Brain API](/reference/brain/).

## Crash-only

Cortex keeps no session state — that lives in the endpoints (Voqalize's session
and your brain). There's no drain protocol and no graceful-shutdown contract.
Your agent leg reconnects and carries on; the calls that were in flight when it
died do not survive, because a voice session is its socket.

## Read next

- **[Inbound server](/build/inbound/)** — the primary path.
- **[Where the brain runs](/build/hosting/)** — choosing between them.
