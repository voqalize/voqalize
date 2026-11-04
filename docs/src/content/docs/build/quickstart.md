---
title: Quickstart
description: Hear an agent you wrote in about ten minutes. Write a brain in one Python file, create an agent, run the brain on your laptop with no tunnel, and talk to it in the console Playground. Then put it in your page.
---

You write a brain in one file, create an agent for it, run the brain on your
laptop and talk to it in the browser. There is no page to build and no tunnel to
set up: the brain dials out to Voqalize through the Cortex relay.

You need Python 3.12 or later and a Google account to sign in to Voqalize.

## With a coding agent

Connect the Voqalize MCP server to your coding agent. In Claude Code:

```bash
claude mcp add --transport http voqalize https://app.voqalize.com/mcp/
```

Then ask:

```text
Follow https://docs.voqalize.com/build/quickstart.md: write the brain, create
the agent and its Cortex credentials, run the brain, and give me the test_url.
```

[Work with a coding agent](/build/coding-agent/) covers the setup and what your
agent can do from there. The steps below are what it will do.

## By hand

### 1. Install the SDK

```bash
pip install voqalize-agent-sdk==0.12.0
```

Pin the version: releases before 1.0 may change the brain API, and the 0.0.x
releases on PyPI are an earlier, incompatible surface.

### 2. Write the brain

Save this as `brain.py`:

```python
import asyncio
import os

from voqalize.sdk import Brain, SpeechChunk, SpeechEnd, SpeechStart, serve


class Concierge(Brain):
    async def greet(self, session):
        return "Hi, I'm your first Voqalize agent. Say something and I'll repeat it."

    async def on_user_message(self, session, msg):
        yield SpeechStart()
        yield SpeechChunk("You said: " + msg.text)
        yield SpeechEnd()


async def main():
    await serve(
        Concierge,
        version="0.1.0",
        cortex_url=os.environ["VOQALIZE_CORTEX_URL"],
        api_key=os.environ["VOQALIZE_AGENT_SECRET"],
    )


if __name__ == "__main__":
    asyncio.run(main())
```

- `greet` returns the first line of every session.
- `on_user_message` receives each finished user turn as `msg.text` and yields one
  **speech unit**: `SpeechStart`, the text, `SpeechEnd`. Replace the middle with
  your model's stream and this is a real agent.
- `serve` dials the Cortex relay and runs every session on that one connection.
  `version` is a label of yours that tells you which build answered.

### 3. Create the agent and its credentials

Sign in at [app.voqalize.com](https://app.voqalize.com) with Google. Then use
either the MCP tools or the console.

**With the MCP tools:**

```text
whoami()
list_tenants()                       # pick your tenant; create_tenant() if the list is empty
create_agent(tenant, name="Concierge")
create_agent_credentials(tenant, agent_id)
```

`create_agent_credentials` puts the agent in Cortex mode and returns
`agent_secret` (an `sk_` key, shown once) and `cortex_url`.

**In the console:** create an agent, set it to dial out through Cortex on its
Overview, then create its secret key on the Connect tab. The console shows both
values.

### 4. Run the brain

```bash
export VOQALIZE_AGENT_SECRET=sk_...   # agent_secret
export VOQALIZE_CORTEX_URL=...        # cortex_url, exactly as returned
python brain.py
```

The two variable names are yours; `brain.py` reads them. Leave the process
running: it is your brain, connected and waiting for sessions.

### 5. Talk to it

Open the agent's **Playground** in the console. With MCP, its link is the
`test_url` that `create_agent` and `get_agent(tenant, agent_id)` return. Start a
session, allow the microphone and say something.

You hear the greeting, then your own words after "You said". That echo is the
proof that your `on_user_message` ran: an agent whose brain is not connected
cannot start a session at all.

If the session does not start, check that `brain.py` is still running and that
`VOQALIZE_CORTEX_URL` is the exact `cortex_url` the tool returned.
[Troubleshooting](/operate/troubleshooting/) has the rest.

## Put it in your page

The Playground is a page Voqalize hosts. Yours needs two pieces: a route on your
server that calls `sessions.connect` with an `sk_` key, and your client on
`@voqalize/client-transport` in the page. [Connect your app](/build/connect/) has
both, complete.

## Read next

- [Build the brain](/build/brain/): the callbacks, speech, actions and tools.
- [Deploy the brain](/build/hosting/): an inbound route for production.
- [Connect your app](/build/connect/): start sessions from your own page.
