---
title: Build an embedded voice agent
description: Connect your app, implement the brain, deploy it, and verify a complete call.
---

You write a pipecat client in your page and a brain behind one WebSocket in
your backend. An agent record joins them — a name and your brain's
URL — and Voqalize runs what is between: WebRTC, recognition, synthesis,
endpointing, turn-taking, interruption and optional recording. Your brain
receives finalized text and returns speech and actions. Your page writes no
transport code.

Start with [how a session works](/build/session/), which follows one call the
whole way, from your page to your brain and back. Every page here is a step of
that path in detail.

- [Quickstart](/build/quickstart/) — the smallest complete web example, running.
- [Connect your app](/build/connect/) — the session-creation request, both
  credential paths, and the one line of pipecat glue around it.
- [Build the brain](/build/brain/) — speech, screen actions, tools, context and
  conversation history.
- [Use another agent framework](/build/existing-agent/) — when the conversation
  logic already exists somewhere else.
- [Deploy the brain](/build/hosting/) — a route Voqalize dials, or a relay your
  brain dials out to.
- [Test the brain](/build/testing/) — your brain over the real wire, with no
  microphone and no model.
- [Keys and authentication](/build/keys/) — which key goes where, and where a
  session may be created.
- [The avatar](/build/avatar/) — a talking head in the page, once the call path
  works.

Once a call works end to end, [improving the agent](/design/) is what changes
next, and [operating calls](/operate/) is how you read one back.
