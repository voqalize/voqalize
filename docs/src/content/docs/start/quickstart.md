---
title: Quickstart
description: Build a brain, point an agent at it, and talk to it in the browser.
---

This walks you from nothing to a voice agent you can talk to, in four moves:
write a brain, create an agent, point the agent at your brain, embed it in a page.

:::note[Pre-release]
The SDK and MCP server are not yet published to PyPI / npm. Install them from a
clone of the [`voqalize/voqalize`](https://github.com/voqalize/voqalize) repo, as
shown below. Published packages will follow at beta.
:::

## 0. Prerequisites

- **Python 3.12+** for the brain.
- A **tenant** and a **management key** (`mk_…`). The fastest way to drive the
  platform is the [Voqalize MCP server](/docs/reference/mcp/) from your editor's
  agent — it creates agents and mints keys for you. You can also use the console.
- For local testing, a tunnel (`ngrok http 8080` or `cloudflared`) — the hosted
  voice runtime must be able to reach your brain over the public internet.

## 1. Write a brain

A brain is a subclass of `Brain` with two callbacks: greet on start, respond on
each user turn.

```python
# brain.py
from voqalize.sdk import Brain, Interaction, Session, SessionStart

class QuickstartBrain(Brain):
    async def on_session_start(self, session: Session, start: SessionStart) -> None:
        async with session.inference() as inf:
            await inf.speak("Hi! I'm your Voqalize quickstart agent. What's on your mind?")

    async def on_interaction(self, interaction: Interaction) -> None:
        # interaction.transcript is what the user actually said.
        async with interaction.inference() as inf:
            await inf.speak(f"You said: {interaction.transcript}. Tell me more.")
```

Swap the body of `on_interaction` for a call to your LLM to make it real — see
[Handling a conversation](/docs/brain/conversation/).

## 2. Serve it (inbound)

The primary path is **inbound**: the voice runtime dials *into* a WebSocket route
you expose. Mount the SDK's session handler on a FastAPI app:

```python
# app.py
from fastapi import FastAPI, WebSocket
from voqalize.sdk import run_session, brain_factory
from brain import QuickstartBrain

app = FastAPI()

class _WsChannel:
    def __init__(self, ws: WebSocket): self._ws = ws
    async def send(self, data: bytes) -> None: await self._ws.send_bytes(data)
    async def recv(self) -> bytes: return await self._ws.receive_bytes()

@app.websocket("/s/{session_id}")
async def brain_socket(ws: WebSocket, session_id: str):
    await ws.accept()
    token = ws.headers.get("authorization")
    await run_session(
        _WsChannel(ws),
        brain_builder=brain_factory(QuickstartBrain),
        session_id=session_id,
        token=token,
    )
```

Run it, then expose it:

```bash
uvicorn app:app --port 8080
ngrok http 8080        # → https://<id>.ngrok.app  ⇒  wss://<id>.ngrok.app
```

:::tip[Local dev auth]
Prod-signed tokens can't be verified through a tunnel. For local testing only,
pass `allow_unverified=True` to `run_session` (or set `VOQAL_ALLOW_UNVERIFIED=true`
and use the SDK's dev entrypoint). Never do this in production.
:::

## 3. Create an agent and point it at your brain

Using the MCP server (from your editor's agent):

```text
create_agent(name="Quickstart")
set_brain_url(agent_id="<agent.id>", brain_url="wss://<id>.ngrok.app")
```

`brain_url` is the base — the runtime appends `/s/{session_id}` when it dials.
It must be `wss://` (plain `ws://` is allowed only for localhost).

Then mint a browser key:

```text
create_api_key(kind="publishable", label="web", allowed_origins=["http://localhost:5173"])
```

## 4. Talk to it in the browser

```tsx
import { VoqalAgent } from "@voqalize/client-react";

export function App() {
  return (
    <VoqalAgent
      apiBase="https://api.voqalize.com/api/v1"
      tenantSlug="<your-tenant-slug>"
      publishableKey={import.meta.env.VITE_VOQAL_PK}
      agentId="<agent.id>"
    />
  );
}
```

Open the page, allow the mic, and start talking. `<VoqalAgent/>` mints the
session, connects the WebRTC transport, plays the agent's audio, and renders a
mute/end bar. Full options in [React client SDK](/docs/client/react/).

:::caution[`apiBase` vs the MCP host]
The React SDK's `apiBase` **includes** the `/api/v1` suffix
(`https://api.voqalize.com/api/v1`). The MCP server's `VOQALIZE_API_BASE` is the
**bare host** (`https://api.voqalize.com`) — it adds `/api/v1/{tenant}` itself.
Same host, different suffix. This is the most common wiring mistake.
:::

## Next steps

- **[Core concepts](/docs/start/concepts/)** — sessions, interactions, inferences.
- **[Handling a conversation](/docs/brain/conversation/)** — LLM streaming, tools,
  and driving the browser UI.
- **[Where the brain runs](/docs/deploy/brain-url/)** — inbound vs. Cortex.
