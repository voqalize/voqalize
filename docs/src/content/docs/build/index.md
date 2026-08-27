---
title: Build
description: From nothing to an application people use twice — the brain you write, where it runs, the page that connects, and the SDK surface in full.
---

Everything you write lives here. A brain is one WebSocket endpoint: it receives
what the caller said and sends back what to say and what to show. Voqalize dials
it once per call. This section takes you from an empty file to a brain that
speaks, acts on the screen, calls tools, remembers a conversation and has tests —
and it is the section to come back to when you add the next capability.

## The three pieces

- **A brain.** Your code. Subclass `Brain`, implement `on_user_message`.
- **An agent.** A record on our side: a name and your brain's URL.
- **A client.** Stock pipecat on your page. You write no transport code.

## The path

Ten minutes first, then depth in the order you will want it.

1. [Quickstart](/build/quickstart/) — a call you can hear, no explanations.
2. [A session, end to end](/build/session/) — the whole path with the frames on it.
3. [Your first brain](/build/brain/) — the callbacks, and the five chapters under it.
4. [Bringing an agent you already have](/build/existing-agent/) — if you arrived
   with an ADK, LangChain or hand-rolled agent, start here instead of at 3.
5. [Where the brain runs](/build/hosting/) — inbound or outbound, and how to choose.
6. [Connecting a page](/build/connect/) — the browser half, end to end.
7. [Keys and authentication](/build/keys/) — `sk_` and `pk_`, and which goes where.
8. [Testing a brain](/build/testing/) — the real wire, no microphone, no model.

Along the way: [Voqalize and pipecat](/build/pipecat/) for what is ours and what
is theirs, and [the avatar](/build/avatar/) when a face helps.

## What you are not building

No audio handling. No turn detector. No reconnection logic. No transport code in
the browser. If you find yourself writing any of it, you are on the wrong side of
the line — read [the boundary](/) again.

## When you are done here

You have an application that works. Whether it is one people use twice is a
different question, and it is
[Designing for voice](/design/).
