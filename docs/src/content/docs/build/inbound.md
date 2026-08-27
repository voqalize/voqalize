---
title: Inbound server
description: Expose one authenticated WebSocket route; Voqalize dials into it. The primary way to run a brain.
---

The inbound path is the primary way to run a brain: you expose **one authenticated
WebSocket route**, Voqalize dials into it, and there's no relay in the
path. If you already run a REST API or webhooks, this is the same shape.

## The route

The runtime dials `{brain_url}?session_id={session_id}` — your path, verbatim,
with the session as a query parameter. Mount **one ordinary WebSocket route**
wherever you like, read `session_id` off the query string, then hand the socket to
the SDK's `run_session`, which drives the whole session and returns when the call
ends.

### Python (FastAPI)

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
bytes`, so it mounts on Starlette, aiohttp, or Django Channels the same way. The SDK
ships no server of its own — your app already runs one, and that is the one the
route belongs on. To drive a brain over a socket in a *test*, use
[`brain_server`](/build/testing/).

## Authentication

Voqalize presents **the brain-connection token** — a short-lived RS256 JWT,
`sub == session_id`. The SDK verifies it against Voqalize's embedded public keys
by default, so you pass the `Authorization` header value through and check
nothing yourself. A verification failure raises `SessionRejected`; close the
socket with code **4000**, which Voqalize treats as permanent. The claims are in
[The wire](/reference/wire/).

**The socket is the session, and it is not reconnected.** The runtime retries
the *first* connect for a few seconds — a **4000** during that window stops it
early — and once you have answered, any close ends the call. There is nothing to
resume: a second connection would reach a fresh session with none of the first
one's history.

## Local testing

The hosted runtime must reach your brain over the public internet, so during
development put a tunnel in front of it:

```bash
uvicorn app:app --port 8080
ngrok http 8080          # → wss://<id>.ngrok.app
```

The SDK ships **one** public key, the production signer's, so a token signed by
dev has nothing to verify against — the tunnel is not what breaks it, and adding
one will not fix it. For **local dev only**, pass `allow_unverified=True` to
`run_session`. Never ship that.

Then point the agent at the tunnel:

```text
update_agent(tenant="acme", agent_id="06a2…", brain_url="wss://<id>.ngrok.app/voice")
```

## Production

Run the route like any other service: behind your own load balancer, one socket
per session per user. Connection state *is* liveness — there's nothing to pool or
drain, and dropping a socket drops that call. Scale horizontally with your LB;
Voqalize just dials whatever the `brain_url` resolves to.

## Read next

- **[Cortex relay](/build/outbound/)** — the fallback when you can't accept
  inbound.
- **The SDK README** (`sdk/python/README.md`) — the serving API in full.
