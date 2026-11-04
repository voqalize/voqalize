---
title: Build an agent
description: The order to build a Voqalize agent in, from the brain to the page, each step linked to the page that covers it.
---

You write two things: a brain behind one WebSocket in your backend, and a page
that starts a session with one request and pipecat's client. An agent record
joins them. [How Voqalize works](/build/session/) explains the parts; the
[Quickstart](/build/quickstart/) gets you to a first session in ten minutes.

## The order of work

1. **[Write the brain](/build/brain/).** Speech, screen actions, tools, context
   and history. Bringing logic from another framework instead:
   [Use another agent framework](/build/existing-agent/).
2. **[Test the brain](/build/testing/).** Drive it over the real wire with no
   microphone and no model, before any session is live.
3. **[Create the agent and say how it is reached](/build/hosting/).** An inbound
   `wss://` route in production, or the Cortex relay from a laptop or a
   serverless function.
4. **[Mint keys](/build/keys/).** An `sk_` for your server; a `pk_` only for a
   public page.
5. **[Connect your app](/build/connect/).** The `sessions.connect` request, the
   response, and the one line of pipecat glue.
6. **[Pick client libraries](/build/pipecat/).** Pipecat's client with
   `@voqalize/client-transport`, and the mobile path.

[Work with a coding agent](/build/coding-agent/) does these steps from your
editor through the Voqalize MCP server.

## Once it works

- Add [voice and language](/build/voice-and-language/), [Stage](/build/stage/),
  [the avatar](/build/avatar/) or [camera and screen](/build/video/).
- Improve the conversation with [Designing for voice](/design/).
- Read sessions back and prepare for launch in [Operate](/operate/).
