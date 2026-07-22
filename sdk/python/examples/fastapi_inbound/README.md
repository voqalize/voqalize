# FastAPI inbound brain — the primary production path

A standalone FastAPI app that hosts a `Brain` on an inbound WebSocket route.
**This is how you deploy a brain in production**: your framework owns the listener
and the upgrade; the SDK just runs the session over the connected socket. PyGato
dials `{brain_url}/s/{session_id}` — one connection per session, opened
just-in-time, no relay.

```
app.py             # FastAPI app: _WsChannel adapter + @app.websocket("/s/{session_id}") → run_session
requirements.txt   # voqalize-agent-sdk + fastapi + uvicorn
Dockerfile         # container for Cloud Run / Fly / ECS
```

The brain is the same `EchoBrain` as [`../echo/`](../echo/) (greet, then echo), so
the example needs no LLM keys. Swap in your own `Brain` subclass — the transport
plumbing is unchanged.

## The seam

The whole integration is one adapter and one route:

```python
class _WsChannel:                       # FastAPI WebSocket → SDK Channel
    def __init__(self, ws): self._ws = ws
    async def send(self, data): await self._ws.send_bytes(data)
    async def recv(self): return await self._ws.receive_bytes()

@app.websocket("/s/{session_id}")
async def voice(websocket, session_id):
    await websocket.accept()
    await run_session(
        _WsChannel(websocket),
        brain=EchoBrain,
        session_id=session_id,                          # from the URL path
        token=websocket.headers.get("Authorization"),   # SDK verifies it
    )
```

`run_session` verifies PyGato's token, runs one session, and returns when the call
ends or the socket closes. It never closes the socket — the route owns that, using
the close codes PyGato understands: **4000** on a rejected token (permanent,
PyGato gives up), **1011** on an unexpected error (retriable, PyGato reconnects).

> Modeled on the control plane's own `app/entrypoints/http/routes/brains.py`,
> which hosts Voqalize's demo brains over the identical `_WsChannel` seam — we
> dog-food this exact path.

## Run it locally

```bash
cd sdk/python
VOQAL_ALLOW_UNVERIFIED=true \
  uv run uvicorn examples.fastapi_inbound.app:app --host 0.0.0.0 --port 8080
```

Then point a **local** demo agent's `brain_url` at `ws://127.0.0.1:8080` (PyGato
appends `/s/{session_id}`), open the console, and start a call.

### Local-dev auth: `VOQAL_ALLOW_UNVERIFIED`

By default the SDK verifies PyGato's RS256 token against the **production**
Voqalize public keys embedded in the package. Your **local** PyGato signs with a
dev key, so a real check rejects every local session with a close code **4000**
and you hear silence. `VOQAL_ALLOW_UNVERIFIED=true` skips verification for local
dev; the app reads it into `allow_unverified=`. **Leave it unset in production** —
a deployed brain gets zero-config prod verification for free.

## Deploy to Cloud Run

Containerize the brain and expose it at a public `wss://` URL PyGato can dial.

```bash
# From this directory. Cloud Run terminates TLS and upgrades WebSockets for you.
gcloud run deploy echo-brain \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8080
```

Cloud Run returns an HTTPS URL like `https://echo-brain-xxxx.run.app`. Set the
agent's `brain_url` to its **WebSocket** form —
`wss://echo-brain-xxxx.run.app` — and PyGato will dial
`wss://echo-brain-xxxx.run.app/s/{session_id}` per session. No `allow_unverified`
in the deployed image: production PyGato signs with the prod key the SDK already
trusts.

### Building the image

`requirements.txt` lists `voqalize-agent-sdk` as if it were on a package index.
Until it's published there, vendor the SDK into the build context (copy
`sdk/python/` alongside this dir and `pip install ./python` in the
Dockerfile), or build a wheel with `uv build` and `COPY` it in. The
`--allow-unauthenticated` flag is about *Cloud Run's* IAM front door (PyGato is an
anonymous external caller); the brain still authenticates PyGato itself via the
RS256 token inside `run_session`.
