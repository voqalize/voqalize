---
title: What Voqalize is
description: The brain, the session, and the two halves of a Voqalize app — what your code owns and what the voice tier runs.
---

Voqalize runs the voice tier — WebRTC transport, echo cancellation, voice
activity detection, speech-to-text, text-to-speech, turn-taking, barge-in and
recording — and opens one WebSocket per session to a route you own. Your code
receives the caller's finalized text and sends back two things: the words to
speak, and typed **actions** that update the screen the caller is looking at.

Your code never touches audio. There is no buffer to drain, no sample rate to
agree on, and no frame to time.

## A brain is a WebSocket route

A **brain** is one URL. Voqalize dials it once per **session**:

```
{brain_url}?session_id={session_id}
```

One connection, opened when the call starts and closed when it ends. It is the
shape you already use for webhooks, held open. The frames are protobuf and the
contract is published — see [the wire](/docs/reference/wire/).

Where that URL points is yours to choose: a route in the service you already
deploy, or a [Cortex relay](/docs/deploy/cortex/) when your network cannot accept
inbound connections. The same brain code runs on either.

## The two halves of your app

A Voqalize integration touches two places you already own, and they never talk to
each other directly — everything between them crosses our wire.

| | You write | Voqalize runs |
|---|---|---|
| **Your server** | The brain: what to say, what to show, which tools to call, what to remember | The socket that dials it, one per session |
| **Your page** | One HTTP request for the connect params, then stock [pipecat](/docs/start/pipecat/) | WebRTC to the browser, and the RTVI data channel that carries actions and transcripts |
| **Between them** | — | Speech recognition, speech synthesis, turn detection, interruption, recording |

The browser half ships no library of ours. One `fetch` returns what a pipecat
transport connects with, and the rest of the page is pipecat you can read the
docs for elsewhere — [the handshake](/docs/client/handshake/) is the whole of it.

## What a session does, in order

1. Your page asks the control plane for connect params and hands them to pipecat.
   The browser negotiates WebRTC **straight to the machine that will run the
   call**; nothing of ours proxies the audio.
2. Voqalize builds the pipeline, then dials your brain and sends `SessionStart`.
3. Your brain returns a greeting. The caller is already connected and hearing
   nothing at this point, so the greeting is a string — a fixed line or a
   template over what the page sent — and never a model call.
4. The caller speaks. Voqalize decides when they have finished and hands your
   brain the finalized text.
5. Your brain yields speech in units, and dispatches actions as the answer takes
   shape. Speaking starts on the first unit rather than on the last, so the reply
   begins before it has finished being generated.
6. The caller interrupts. Voqalize stops the audio and tells your brain which
   turn was condemned; the in-flight turn is cancelled.
7. At the end of each unit your brain is told what the caller actually **heard**,
   which is what a transcript records. A reply that generated three sentences and
   was cut after one is remembered as one.

Steps 4 through 7 repeat until one side ends the call.

## Two channels back

Voice and screen carry different things, and the split is the product.

**Speech** is a stream of text, in units. Each unit is one thing the caller can
be interrupted out of.

**Actions** are typed messages from the brain to the page — a form to open, a row
to highlight, a total to update. They ride the same RTVI data channel the
transcript does, so an action lands while the sentence about it is still being
spoken. A number the caller has to hold in their head is a number that belongs on
the screen.

The screen answers back as **state sync**: what the caller has clicked or typed,
sent from the page and delivered to the brain while the floor stays where it
was. That callback cannot speak, so an agent cannot talk over the person who
just clicked.

## What you keep

Your model, your prompts, your tools and your retrieval run in the process you
deploy today. Your transcripts, session events and outcomes land in your systems,
on your schema. The brain is code in your repository, under your version control,
and swapping the model behind it is a change we never see.

Voqalize holds the session while the call is up: the audio, the recognition, the
floor, and the recording if you asked for one. All of it is readable back through
[the MCP server](/docs/reference/mcp/) or the API, inside your own tooling.

## Read next

- [Voqalize and pipecat](/docs/start/pipecat/) — what is ours, what is theirs, and what that buys you.
- [Connections and the handshake](/docs/client/handshake/) — the browser half, end to end.
- [Testing a brain](/docs/brain/testing/) — drive a real brain over the real wire, without a microphone.
- [The wire](/docs/reference/wire/) — the contract both ends are held to.
