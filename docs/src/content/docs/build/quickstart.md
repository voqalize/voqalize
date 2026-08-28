---
title: Quickstart
description: A brain that answers, a call you can hear, in ten minutes. Install, write eight lines, create an agent, open a page.
---

Ten minutes from nothing to a call you can hear. You install the SDK, write a
brain that answers one way, create an agent that points at it, and open a page.
Everything you skip here has its own page in [Build](/build/).

## 1. Install

```bash
pip install voqalize-agent-sdk==0.2.0
```

No pipecat, no model SDK, no audio library. **Pin it.** 0.2.0 is where this
surface stands; the 0.0.x on PyPI is a different one that will import cleanly
and then fail on a name this page uses.

## 2. Write the brain

Eight lines. A class, one required callback, three speech frames.

```python
from voqalize.sdk import Brain, Chunk, SpeechEnd, SpeechStart

class Concierge(Brain):
    async def greet(self, session):
        return "Hi! What can I do for you?"

    async def on_user_message(self, session, msg):
        yield SpeechStart()
        yield Chunk("You said: " + msg.text)
        yield SpeechEnd()
```

`msg.text` is the finalized transcript of one turn. The three frames are one
**speech unit** — a thing with a start, a middle you can stream, and an end that
lets the caller interrupt cleanly. Replace the middle with your model's stream
and this is a real agent. See [Your first brain](/build/brain/).

## 3. Serve it

```python
from voqalize.sdk import run_session

@app.websocket("/voice")
async def voice(ws: WebSocket, session_id: str):    # session_id from ?session_id=
    await ws.accept()
    await run_session(
        _WsChannel(ws),
        brain=Concierge,                            # the class, not an instance
        session_id=session_id,
        token=ws.headers.get("authorization"),
    )
```

`run_session` takes a **channel** — anything with `async send(bytes)` and
`async recv() -> bytes` — so the route is your framework's, not ours.
`_WsChannel` is the four-line adapter for whichever framework you run;
[Inbound server](/build/inbound/) has it written out for FastAPI. The `brain=`
is a class, constructed fresh per session, so no state leaks between calls.

On a laptop or a serverless function that cannot accept inbound, `serve(...)`
dials out instead and the brain above does not change —
[Where the brain runs](/build/hosting/).

## 4. Point an agent at it

An **agent** is our record holding your brain's URL. Create one, keep the `sk_`
key it gives you, and set `brain_url` to the route from step 3 — through the
[MCP server](/reference/mcp/), which is where every account operation lives, or
the console.
Locally, put a tunnel in front of the route so the URL is reachable.

## 5. Open a page

One `fetch` for the connect parameters, then stock pipecat. The runnable example
is web; Pipecat also supplies React Native, native iOS and native Android clients
for the same connect contract. See [Connecting a page](/build/connect/) and
[Voqalize and pipecat](/build/pipecat/).

## Verify that your brain answered

An agent whose `brain_url` is empty uses the hosted welcome brain. A greeting
therefore verifies the call path, but not your WebSocket route. Return a
distinctive response from `on_user_message`, as above, and confirm that response
before continuing.

## Read next

- [Your first brain](/build/brain/) — the callbacks, and which one is required.
- [Where the brain runs](/build/hosting/) — the two hosting paths.
- [Connecting a page](/build/connect/) — the browser half.
