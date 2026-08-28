---
title: Build an embedded voice agent
description: Connect your app, implement the brain, deploy it, and verify a complete call.
---

Build the integration in two places: a Pipecat client in your app and a brain
WebSocket in your backend. Voqalize connects them for each call and runs the
voice path between them.

## The three pieces

- **A brain.** Your code. Subclass `Brain`, implement `on_user_message`.
- **An agent.** A record on our side: a name and your brain's URL.
- **A client.** Stock pipecat on your page. You write no transport code.

## Recommended path

1. [How a session works](/build/session/) — follow one call from your app to the
   brain and back.
2. [Quickstart](/build/quickstart/) — run the smallest complete web example.
3. [Connect your app](/build/connect/) — choose browser or backend session
   creation and connect a Pipecat client.
4. [Build the brain](/build/brain/) — add speech, screen actions, tools, context
   and conversation history.
5. [Use another agent framework](/build/existing-agent/) — connect an existing
   framework through the text-and-actions wire.
6. [Deploy the brain](/build/hosting/) — use an inbound WebSocket in production
   or the outbound relay when the environment cannot accept ingress.
7. [Test the brain](/build/testing/) — run protocol scenarios without a
   microphone or live model.

Use [keys and authentication](/build/keys/) when choosing where a session may be
created. Add [the avatar](/build/avatar/) after the call path works.

## What Voqalize runs

Voqalize runs WebRTC, recognition, synthesis, endpointing, turn-taking,
interruption and optional recording. Your app uses Pipecat's client transport;
your brain receives finalized text and returns speech and actions.

Once the complete call works, continue with [improving the agent](/design/) and
[operating calls](/operate/).
