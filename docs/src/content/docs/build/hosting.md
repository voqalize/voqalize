---
title: Deploy the brain
description: The brain_url is one WebSocket URL. Expose a route and let Voqalize dial it, or dial out to a Cortex relay — the same brain code either way.
---

An agent's brain is one setting: `deployment.brain_url`, a single WebSocket URL.
When a call starts, Voqalize dials `{brain_url}?session_id={session_id}` — one
connection per session, opened just-in-time and torn down when the call ends.

Nothing on our side interprets where that URL points, and your brain code is
identical wherever it runs. What you choose is **who dials whom**: expose a route
and Voqalize dials into it, or dial out to a Cortex relay and let it splice the
legs. Both run the same per-session engine and the same `Vql*` wire.

Expose a route when your backend can accept an authenticated WebSocket. Dial out
through Cortex when it cannot — a serverless function, a laptop behind NAT, an
egress-only or air-gapped network — and when you are developing against hosted
Voqalize from your own machine, which is what Cortex is the default for locally.
The relay adds a hop and a moving part, so reach for it when inbound is not
available rather than by preference.

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

## A route Voqalize dials

Mount **one ordinary WebSocket route** wherever you like, read `session_id` off
the query string, then hand the socket to the SDK's `run_session`, which drives
the whole session and returns when the call ends.

```python
from fastapi import FastAPI, WebSocket
from voqalize.sdk import run_session
from mybrain import MyBrain

app = FastAPI()

class _WsChannel:
    def __init__(self, ws: WebSocket): self._ws = ws
    async def send(self, data: bytes) -> None: await self._ws.send_bytes(data)
    async def recv(self) -> bytes: return await self._ws.receive_bytes()

@app.websocket("/voice")
async def brain_socket(ws: WebSocket, session_id: str):   # session_id from ?session_id=
    await ws.accept()
    try:
        await run_session(
            _WsChannel(ws),
            brain=MyBrain,            # or brain=lambda: MyBrain(llm=...)
            session_id=session_id,
            token=ws.headers.get("authorization"),
        )
    except Exception:
        await ws.close(code=1011)     # retriable
```

`run_session` accepts any object with `async send(bytes)` / `async recv() ->
bytes`, so it mounts on Starlette, aiohttp or Django Channels the same way. The
SDK ships no server of its own — your app already runs one, and that is the one
the route belongs on. To drive a brain over a socket in a *test*, use
[`brain_server`](/build/testing/).

`brain=` is a class, constructed fresh per session, so no state leaks between
calls.

**The socket is the session, and it is not reconnected.** Voqalize retries the
*first* connect for a few seconds — a **4000** close during that window stops it
early — and once you have answered, any close ends the call. There is nothing to
resume: a second connection would reach a fresh session with none of the first
one's history.

Run the route like any other service: behind your own load balancer, one socket
per session per user. Connection state *is* liveness — there is nothing to pool
or drain, and dropping a socket drops that call. Voqalize dials whatever the
`brain_url` resolves to.

## A brain that dials out

Cortex is a stateless, schema-free WebSocket relay. Voqalize lands on
`/?session_id={session_id}`; your brain dials out to `/agent`. Both legs
authenticate to the same tenant-and-agent **rendezvous scope**, derived from the
credentials rather than from the URL, and Cortex matches them on it. There is
nothing to encode in a path and nothing to configure. Cortex holds no state, and
many sessions multiplex over your one outbound socket, demuxed by a 16-byte
session prefix.

Get the credentials over the [MCP server](/reference/mcp/):

```text
create_agent_credentials(tenant, agent_id, label="")
```

| Field | Where it goes |
|---|---|
| `agent_secret` | `sk_…` — the SDK's `api_key=`. The same kind `create_agent` gave you; **shown once**, never recoverable. |
| `cortex_url` | The SDK's `cortex_url=`. It already ends in `/agent` — pass it verbatim; the SDK does not append. |

**Calling this switches the agent to `cortex` mode.** There is no URL to copy
back: the address Voqalize dials to reach the relay is ours, and we hold it.

It used to return that address as a third field, `brain_url`, for you to paste
into a second call. Nothing in that step was a decision — we computed the value
from our own settings and asked you to type it back — and until you did, the
agent still pointed wherever it pointed before. A call still connected, so the
relay looked broken when it had never been wired in. The step is gone.

Keys never expire, and minting revokes nothing, so rotation is mint → redeploy →
`revoke_api_key` on the old one, with no window where the agent cannot connect.

The same `Brain` class runs over Cortex; only the entrypoint changes.

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

Pass one credential and not both: a static `api_key` (`sk_…`), or an
`authorization_provider` that mints a `"Bearer <jwt>"` per connect. Passing both,
or neither, raises at construction.

`serve` **blocks** for the life of the relay connection. Where that call lives —
`asyncio.run` in a `__main__`, a task in your app's lifespan, a worker entrypoint
— is yours to decide; the SDK owns no process management.

Cortex keeps no session state; that lives in the endpoints, which are Voqalize's
session and your brain. There is no drain protocol and no graceful-shutdown
contract. Your agent leg reconnects and carries on; the calls that were in flight
when it died do not survive, because a voice session is its socket.

## The brain-connection token

However the connection is made, Voqalize presents the same credential: **the
brain-connection token**, a short-lived RS256 JWT whose `sub` is the
`session_id`. It is the same token on both paths, verified the same way, and the
SDK verifies it for you against Voqalize's embedded public keys — so you pass the
`Authorization` header value through and check nothing yourself.

A verification failure raises `SessionRejected`; close the socket with code
**4000**, which Voqalize treats as permanent.

That name is the one to remember. It is what `mint_voqalize_token` mints in
[Testing a brain](/build/testing/), what your route passes through above, and the
claims are written out once in [The wire](/reference/wire/).

## Local development

Cortex needs no public inbound route and no tunnel, which is why it is the
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

To develop against a route instead, Voqalize has to reach your brain over the
public internet, so put a tunnel in front of it and point the agent at the
tunnel:

```bash
uvicorn app:app --port 8080
ngrok http 8080          # → wss://<id>.ngrok.app
```

```text
update_agent(tenant="acme", agent_id="06a2…", brain_url="wss://<id>.ngrok.app/voice")
```

The SDK ships the production signer's public key and no other, so a token signed
by dev has nothing to verify against — the tunnel is not what breaks it, and
adding one will not fix it. For **local dev only**, pass `allow_unverified=True`
to `run_session`. Never ship that.

## Read next

- [Testing a brain](/build/testing/) — over the real wire, without a microphone.
- [Keys and authentication](/build/keys/) — which key goes where, and rotation.
- [The wire](/reference/wire/) — the token's claims, and every frame.
