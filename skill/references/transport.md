# Transport — where the brain runs, and who dials whom

An agent's brain is **one WebSocket URL** (`brain_url`). The Voqalize runtime
(PyGato) dials `{brain_url}/s/{session_id}` — one connection per session, opened
just-in-time, torn down when the call ends. The control plane never interprets where
that URL points. There are exactly two ways to get a reachable URL.

| | **Inbound / direct** | **Cortex / outbound** |
|---|---|---|
| Who dials whom | PyGato dials **into** your brain | Your brain dials **out** to Cortex |
| You run | one authenticated `wss://` route (like any webhook) | a process holding an outbound socket |
| `brain_url` | your route's base: `wss://your-host/…` | the Cortex origin (from `create_agent_credentials`) |
| Needs a public inbound endpoint | yes | **no** |
| Use for | production, when you already run a web backend | **localhost dev**, serverless/FaaS, egress-only / air-gapped |
| Template | `templates/inbound_app.py` | `templates/run_cortex.py` |

**The same `Brain` class runs on both.** Only the entrypoint changes. Typical
lifecycle: build over Cortex on the laptop, ship over inbound in production.

---

## Local development — Cortex, no tunnel

This is the fast path and it is fully self-service. **Do not set up ngrok /
cloudflared** — the brain dials out, so nothing needs to reach your laptop.

**1. Mint the credentials.**

```
create_agent_credentials(tenant, agent_id, label="")
```

Returns:

| Field | What to do with it |
|---|---|
| `agent_secret` | `ak_…` — the brain's credential. **Shown once**, never recoverable. |
| `cortex_url` | Pass **verbatim** to the SDK's `cortex_url=`. Already ends in `/agent`; the SDK does not append. |
| `brain_url` | The Cortex **origin** — what this agent's `brain_url` must become. |
| `key_id` | For `revoke_api_key` later. |
| `usage` / `instructions` | A ready-to-paste env block and the wiring steps. |

Today the deployed relays are `wss://cortex.dev.voqalize.com` and
`wss://cortex.prod.voqalize.com`, but **always use the values the tool returns** —
they are the contract, not these strings.

**2. Wire the agent to Cortex.** Not automatic:

```
update_agent(tenant, agent_id, brain_url="<the brain_url the tool returned>")
```

Until you do this, the agent still points wherever it pointed before.

**3. Run the brain.** Export exactly the env block the tool handed back:

```bash
export VOQAL_AGENT_SECRET=ak_...            # agent_secret
export VOQAL_CORTEX_URL=wss://cortex.dev.voqalize.com/agent   # cortex_url, verbatim
export VOQAL_AGENT_MODE=outbound
python run_cortex.py
```

`templates/run_cortex.py` is a nine-line wrapper around:

```python
from voqalize.sdk import serve
await serve(MyBrain, api_key=..., cortex_url=..., version="1.0.0")
```

`serve_auto(MyBrain, api_key=..., cortex_url=..., version="1.0.0")` does the same
but picks the transport from `$VOQAL_AGENT_MODE` (`outbound`/`cortex` vs
`inbound`/`direct`) — the SDK reads *only* that variable itself; the other two are
conventions your code passes through as kwargs.

**4. Talk to it.** Open the agent's `test_url` (from `create_agent` / `get_agent`).

Rotation is safe by construction: minting revokes nothing. Mint → redeploy the brain
with the new key → `revoke_api_key(tenant, old_key_id)`. `ak_` keys never expire.

**How Cortex splices the legs.** It exposes two routes: PyGato lands on
`/s/{session_id}`, your brain on `/agent`. Both legs authenticate to the same
tenant+agent rendezvous scope — Cortex matches them on that, derived from the
credentials. **The scope is not in the URL path**, and there is nothing to configure.
Many sessions multiplex over your one outbound socket, demuxed by a 16-byte session
prefix. Cortex is crash-only and holds no state: kill it and both sides reconnect.

---

## Production — inbound

Your web framework owns the listener and the upgrade; the SDK just runs the session
over the socket you hand it. `voqalize.sdk.run_session` is the framework-agnostic
primitive:

```python
from voqalize.sdk import SessionRejected, run_session

@app.websocket("/s/{session_id}")
async def voice(ws: WebSocket, session_id: str) -> None:
    await ws.accept()
    try:
        await run_session(
            _WsChannel(ws),                          # anything with send/recv bytes
            brain=MyBrain,                           # or brain_builder=lambda: MyBrain(llm)
            session_id=session_id,                   # from your route param
            token=ws.headers.get("Authorization"),   # the SDK verifies it
        )
    except SessionRejected:
        await ws.close(code=4000)                    # bad token — PyGato won't retry
```

`templates/inbound_app.py` is the complete FastAPI version, including the
Starlette→`Channel` shim and the close-code discipline (**4000 = permanent, don't
retry; 1011 = retriable**).

- **Auth is zero-config.** The SDK verifies PyGato's RS256 token (`iss=pygato`,
  `aud=brain`, `sub == session_id`) against public keys embedded in the package.
  Pass `public_keys=` only for a self-hosted deployment.
- **`allow_unverified=True` is local-only** and logs loudly. A deployed brain never
  sets it.
- **`brain_url` is the route's base** — PyGato appends `/s/{session_id}`. Must be
  `wss://`; `ws://` is accepted only for `localhost`/`127.0.0.1`.
- Use `brain_builder=` (not `brain=`) when the brain needs injected dependencies;
  a fresh instance is still built per session either way.

`serve_direct(MyBrain, host=..., port=...)` / `DirectAgent` own a `websockets`
server for you — handy for scripts and tests, but in production mount `run_session`
in the framework you already run.

## Gotchas

- An **empty `brain_url`** falls back to the hosted `welcome` brain, so a bare agent
  still greets. If your agent greets with something you didn't write, it's unwired.
- `create_agent` returns an `sk_` **session key**, not the Cortex `ak_`. They are
  different credentials for different jobs: `sk_` starts sessions from your backend;
  `ak_` authenticates the brain's outbound leg to Cortex.
- Never expose an `sk_` or `ak_` to a browser. The browser gets a `pk_` only.

## Read next

- **`references/testing.md`** — drive the brain with no runtime at all, then inspect
  a real call.
- **`references/ui-actions.md`** — if the agent drives the screen.
- **`references/frontend.md`** — once it answers, embed it.
