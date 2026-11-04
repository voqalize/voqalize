---
title: Deploy the brain
description: The brain_url is one WebSocket URL. In production, expose an inbound route Voqalize dials; for local development and egress-only hosts, dial out to the Cortex relay. The brain code is the same either way.
---

An agent reaches its brain through one setting, `deployment.brain_url`, a single
WebSocket URL. When a session starts, Voqalize dials
`{brain_url}?session_id={session_id}`: one connection per session, opened when the
session starts and closed when it ends.

What you choose is **who dials whom**. Your `Brain` class is the same either way;
only the entrypoint changes.

| Where the brain runs | Use | Entrypoint |
|---|---|---|
| Your production backend, which can accept an authenticated WebSocket | [An inbound route](#a-route-voqalize-dials) (the default) | `run_session` |
| Your laptop, during development | [Cortex](#a-brain-that-dials-out): no tunnel, no public route | `serve` |
| A serverless function, or a network that allows only outbound connections | [Cortex](#a-brain-that-dials-out) | `serve` |

Cortex is Voqalize's WebSocket relay: your brain dials out to it, and Voqalize
reaches your brain through it. It adds a hop, so in production prefer an inbound
route wherever your backend can take one.

## Setting the `brain_url`

Point an agent at your inbound route with the [MCP server](/reference/mcp/):

```text
update_agent(tenant="acme", agent_id="06a2…", brain_url="wss://brain.example.com/voice")
```

`create_agent` takes the same `brain_url` argument up front.

| Rule | Detail |
|---|---|
| Scheme | `wss://`. Plain `ws://` is accepted only for `localhost` and `127.0.0.1`. |
| Path | Give the full URL of your route. Voqalize dials it as given and appends only `?session_id=`. |
| Mode | Setting `brain_url` puts the agent in `inbound` mode. |
| Cortex | You set no URL. `create_agent_credentials` puts the agent in `cortex` mode and stores the relay address for you. |

An agent with neither a `brain_url` nor Cortex credentials cannot take a session:
`sessions.connect` refuses it with
[`409 agent_not_configured`](/reference/errors/), and `get_agent` reports its
`stage` as `unconfigured`.

The agent record carries no voice or language. Those are set per session; see
[Voice and language](/build/voice-and-language/).

## A route Voqalize dials

Mount one WebSocket route in the web app you already run, read `session_id` from
the query string, and hand the socket to the SDK's `run_session`. It verifies the
connection, runs the session, and returns when the session ends.

```bash
pip install "voqalize-agent-sdk==0.12.0" fastapi "uvicorn[standard]"
```

```python
import contextlib

from fastapi import FastAPI, WebSocket
from starlette.websockets import WebSocketDisconnect
from voqalize.sdk import SessionRejected, run_session

from mybrain import MyBrain  # your Brain subclass

app = FastAPI()


class _WsChannel:
    """Adapts a FastAPI WebSocket to the SDK's send/recv channel."""

    def __init__(self, ws: WebSocket) -> None:
        self._ws = ws

    async def send(self, data: bytes) -> None:
        await self._ws.send_bytes(data)

    async def recv(self) -> bytes:
        return await self._ws.receive_bytes()


@app.websocket("/voice")
async def voice(ws: WebSocket, session_id: str) -> None:  # session_id from ?session_id=
    await ws.accept()
    try:
        await run_session(
            _WsChannel(ws),
            brain=MyBrain,  # or brain=lambda: MyBrain(llm=...)
            session_id=session_id,
            token=ws.headers.get("authorization"),
        )
    except SessionRejected:
        await ws.close(code=4000)  # the token did not verify
    except WebSocketDisconnect:
        pass  # Voqalize closed the socket: the session is over
    except Exception:
        with contextlib.suppress(Exception):
            await ws.close(code=1011)  # your brain failed
```

Run it with `uvicorn app:app --host 0.0.0.0 --port 8080` behind your own TLS
and load balancer, and set the agent's `brain_url` to the route's public `wss://`
URL.

- `run_session` accepts any object with `async send(bytes)` and
  `async recv() -> bytes`, so the same route mounts on Starlette, aiohttp or
  Django Channels.
- `brain=` is a class, or a zero-argument callable that returns a brain. It is
  constructed fresh for each session, so no state leaks between sessions.
- To drive the route without a real session, see [Test the brain](/build/testing/).

**The socket is the session, and it is not reconnected.** Voqalize retries
opening the socket for up to 10 seconds, so a brain that is still starting up is
reached. Once your route accepts it, any close ends the session, whatever the
code. A second connection would reach a fresh brain with none of the first one's
history, so nothing reconnects.

Each session is one socket, so there is nothing to pool or drain: dropping a
socket drops that session.

## A brain that dials out

With Cortex, your brain opens one outbound WebSocket to the relay and keeps it
open. Voqalize connects to the same relay for each session, and Cortex pairs the
two by the agent their credentials name, never by anything in a URL. Many
sessions share your one outbound socket.

Get the credentials over the [MCP server](/reference/mcp/):

```text
create_agent_credentials(tenant="acme", agent_id="06a2…")
```

| Field | Where it goes |
|---|---|
| `agent_secret` | An `sk_` key for this agent, passed as `api_key=`. **Shown once**; it cannot be read back, only revoked and re-minted. |
| `cortex_url` | Passed as `cortex_url=`, as returned. It already ends in `/agent`, for example `wss://cortex.prod.voqalize.com/agent`. |

Calling it switches the agent to `cortex` mode. There is no URL to copy back
into the agent.

```python
import asyncio
import os

from voqalize.sdk import serve

from mybrain import MyBrain  # your Brain subclass

asyncio.run(
    serve(
        MyBrain,  # or a () -> Brain callable
        version="1.0.0",
        cortex_url=os.environ["VOQALIZE_CORTEX_URL"],
        api_key=os.environ["VOQALIZE_AGENT_SECRET"],
    )
)
```

- **`version` and `cortex_url` are required.** `serve` forwards them to its relay
  client, so leaving one out raises a `TypeError` from inside `serve`. `version`
  is your own string; it travels as the `X-Agent-Version` header and tells you
  which build answered a session.
- **Pass exactly one credential:** `api_key=` (an `sk_` key), or
  `authorization_provider=`, a callable that returns `"Bearer <jwt>"` for each
  connect. Both or neither raises at once.
- **`serve` blocks** for the life of the relay connection and returns when the
  relay closes it permanently. Run it from `asyncio.run`, a task in your app's
  lifespan, or a worker entrypoint.

Cortex keeps no session state. If it restarts, your brain's connection
reconnects, and the sessions that were in flight end.

To rotate the key, see [Keys and authentication](/build/keys/#rotating-a-key).

## The brain-connection token

On both paths, Voqalize presents the same credential: the **brain-connection
token**, a short-lived RS256 JWT whose `sub` is the `session_id`, in the
`Authorization` header. `run_session` verifies it against Voqalize's public keys,
which ship inside the SDK, so you pass the header value through and check nothing
yourself.

A token that fails verification raises `SessionRejected`; close the socket with
code `4000`, as the route above does.

The claims are listed in [the wire reference](/reference/wire/#connection-and-auth),
and the harness in [Test the brain](/build/testing/) mints the same token for tests.

## Local development

Develop with Cortex. It needs no public route and no tunnel. Create the agent,
call `create_agent_credentials`, export what it returned, and run the `serve`
script above:

```bash
export VOQALIZE_AGENT_SECRET=sk_live_…                          # agent_secret
export VOQALIZE_CORTEX_URL=wss://cortex.prod.voqalize.com/agent  # cortex_url, as returned
python run_cortex.py
```

Both variable names are your own: your code reads them and passes them to
`serve`. Then open the agent's `test_url` from `get_agent` and talk to it.

To exercise the inbound route itself before you deploy, run it locally, put a
tunnel in front of it, and set `brain_url` to the tunnel's `wss://` URL with the
route's path. The token verifies exactly as in production. `run_session` also
takes `allow_unverified=True`, which skips verification; never set it on a route
Voqalize can reach.

## Read next

- [Keys and authentication](/build/keys/): which key goes where, and how to rotate one.
- [Connect your app](/build/connect/): start a session from your page.
- [Test the brain](/build/testing/): drive the brain over the real wire, with no microphone.
