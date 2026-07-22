---
title: Inbound server
description: Expose one authenticated WebSocket route; the voice runtime dials into it. The primary way to run a brain.
---

The inbound path is the primary way to run a brain: you expose **one authenticated
WebSocket route**, the voice runtime dials into it, and there's no relay in the
path. If you already run a REST API or webhooks, this is the same shape.

## The route

The runtime dials `{brain_url}/s/{session_id}`, so your route matches `/s/{id}`.
Accept the socket, then hand it to the SDK's `run_session`, which drives the whole
session and returns when the call ends.

### Python (FastAPI)

```python
from fastapi import FastAPI, WebSocket
from voqalize.sdk import run_session, brain_factory
from mybrain import MyBrain

app = FastAPI()

class _WsChannel:
    def __init__(self, ws: WebSocket): self._ws = ws
    async def send(self, data: bytes) -> None: await self._ws.send_bytes(data)
    async def recv(self) -> bytes: return await self._ws.receive_bytes()

@app.websocket("/s/{session_id}")
async def brain_socket(ws: WebSocket, session_id: str):
    await ws.accept()
    try:
        await run_session(
            _WsChannel(ws),
            brain_builder=brain_factory(MyBrain),
            session_id=session_id,
            token=ws.headers.get("authorization"),
        )
    except Exception:
        await ws.close(code=1011)     # retriable
```

`run_session` accepts any object with `async send(bytes)` / `async recv() ->
bytes`, so it mounts on Starlette, aiohttp, or Django Channels the same way. For a
standalone local server that owns the socket for you, use
`serve_direct(MyBrain, host=..., port=...)`.

### Go

```go
srv, _ := cortex.NewDirectServer(
    brain.Factory(func() brain.Brain { return &MyBrain{} }, logger),
    cortex.DirectOptions{Audience: "brain"},
)
http.Handle("/s/", srv)                       // srv.ServeHTTP does the WS upgrade
log.Fatal(http.ListenAndServe(":8080", nil))
// or: srv.ListenAndServe(ctx, ":8080")
```

## Authentication

The runtime presents an RS256 JWT (`iss=pygato`, `aud="brain"`,
`sub=session_id`). The SDK verifies it against Voqalize's embedded public keys by
default — you just pass the `Authorization` header value through. A verification
failure raises `SessionRejected`; close the socket with code **4000**
(permanent — the runtime won't retry).

Close-code discipline:

- **4000** — reject permanently (bad token, unknown agent). No retry.
- **1011** / other — transient. The runtime reconnects with backoff.
- **1000** from you — normal close, no reconnect.

## Local testing

The hosted runtime must reach your brain over the public internet, so during
development put a tunnel in front of it:

```bash
uvicorn app:app --port 8080
ngrok http 8080          # → wss://<id>.ngrok.app
```

Prod-signed tokens can't be verified through a tunnel, so for **local dev only**
pass `allow_unverified=True` to `run_session` (or set
`VOQAL_ALLOW_UNVERIFIED=true`). Never ship that.

Then point the agent at the tunnel:

```text
set_brain_url(agent_id="06a2…", brain_url="wss://<id>.ngrok.app")
```

## Production

Run the route like any other service: behind your own load balancer, one socket
per session per user. Connection state *is* liveness — there's nothing to pool or
drain. Scale horizontally with your LB; the runtime just dials whatever the
`brain_url` resolves to.

## Next

- **[Cortex relay](/docs/deploy/cortex/)** — the fallback when you can't accept
  inbound.
- **[Build a brain (Python)](/docs/brain/python/)** / **[Go](/docs/brain/go/)** —
  the serving APIs in full.
