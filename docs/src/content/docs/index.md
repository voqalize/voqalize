---
title: Voqalize
description: Voqalize is voice mode for your app. The user talks, your agent answers and acts on the screen beside them, and Voqalize runs everything between the microphone and the text.
template: splash
head:
  - tag: title
    content: Voqalize — voice mode for your app
hero:
  tagline: Voice mode for your app. The user talks, your agent answers and acts on the screen beside them, and what they do in the app flows back as context.
  actions:
    - text: Quickstart
      link: /build/quickstart/
      icon: right-arrow
      variant: primary
    - text: How Voqalize works
      link: /build/session/
      icon: open-book
      variant: minimal
    - text: Examples
      link: /overview/examples/
      icon: open-book
      variant: minimal
    - text: View on GitHub
      link: https://github.com/voqalize/voqalize
      icon: external
      variant: minimal
---

Voqalize adds voice to a web or mobile app you already have. You write the
**brain**: one WebSocket endpoint that receives each finished user turn as text
and returns what to say and what to show. Voqalize dials it when a session
starts and runs the audio around it.

## Who does what

| | You write | Voqalize runs |
|---|---|---|
| **Your server** | The brain: prompts, model, tools, data, and what the user may commit | The connection that dials the brain, one per session |
| **Your page** | One request for the connect params, then pipecat's client on [`@voqalize/client-transport`](/build/pipecat/) | WebRTC to the browser, and the data channel that carries actions and transcripts |
| **Between them** | Nothing | Recognition, synthesis, turn-taking, interruption, the avatar and recording |

Your code never touches audio. Your model, prompts, tools and retrieval stay in
the process you deploy today, and Voqalize never sees your model credentials.

## Where to start

**New here.** Read [How Voqalize works](/build/session/) for the whole path and
the glossary, then hear your first agent in the [Quickstart](/build/quickstart/).
If you work with a coding agent, [connect it first](/build/coding-agent/).

**Building an agent.** [Build an agent](/build/) walks the order: write the
brain, test it, deploy it, create the agent, connect your page.

**Adding to an agent that works.** Set
[voice and language](/build/voice-and-language/), drive the page with
[Stage](/build/stage/), add [the avatar](/build/avatar/), or record
[camera and screen](/build/video/).

**Running it.** [Operate](/operate/) reads a session back, finds the cause of a
bad call and gets you ready for production.

**Looking something up.** [Reference](/reference/) has the Brain API, the wire,
RTVI messages, the voice catalog, error codes, the HTTP API and the MCP tools.

## See it working

[Examples](/overview/examples/) lists every demo by the pattern it shows, with a
live link and its source. [Status and support](/overview/status/) has versions,
supported clients, region, retention and pricing.
