---
title: Voqalize
description: Voqalize adds voice to an existing web or mobile app. The user talks, the agent talks back and acts on the screen alongside them.
template: splash
head:
  - tag: title
    content: Voqalize — add voice to the app you already have
hero:
  tagline: Add voice to an existing web or mobile app. The user talks, the agent talks back and acts on the screen alongside them — and what they do in the app flows back as context.
  actions:
    - text: Evaluate Voqalize
      link: /overview/status/
      icon: open-book
      variant: primary
    - text: Quickstart
      link: /build/quickstart/
      icon: right-arrow
      variant: minimal
    - text: Build
      link: /build/
      icon: open-book
      variant: minimal
    - text: View on GitHub
      link: https://github.com/voqalize/voqalize
      icon: external
      variant: minimal
---

You integrate in two places. Stock pipecat client libraries on the frontend, and
one WebSocket endpoint on your backend. Voqalize dials that endpoint when a call
starts, and closes it when the call ends.

The sections below explain the responsibility on each side.

:::note[Developer preview]
The SDK and wire may change before 1.0, and the preview has no availability
guarantee. Calls run in India today. Read [current status and supported
environments](/overview/status/) before planning a production launch.
:::

## The integration boundary

Voqalize runs the media and voice path:
WebRTC, echo cancellation, voice activity detection, endpointing, speech-to-text,
text-to-speech, turn-taking, interruption, recording.

Your brain decides what to say, what to do, and what the caller is allowed to
commit — written in the language and framework you already use, running where
your backend already runs.

Your code never touches audio. There is no buffer to drain, no sample rate to
agree on, and no frame to time.

## The two halves of your app

An integration touches two places you already own. They never talk to each other
directly; everything between them crosses our wire.

| | You write | Voqalize runs |
|---|---|---|
| **Your server** | The brain: what to say, what to show, which tools to call, what to remember | The socket that dials it, one per call |
| **Your page** | One HTTP request for the connect params, then stock [pipecat](/build/pipecat/) | WebRTC to the browser, and the data channel that carries actions and transcripts |
| **Between them** | — | Recognition, synthesis, turn detection, interruption, recording |

The browser half ships no library of ours. Pipecat provides JavaScript, React,
React Native, native iOS and native Android clients for the same RTVI and
SmallWebRTC surfaces; Voqalize currently ships complete examples for web.
[Current status](/overview/status/) lists the supported clients, and
[connecting a page](/build/connect/) is the web implementation.

## Where you are

| Section | What is in it |
|---|---|
| **[Current status](/overview/status/)** | SDK stability, clients, regions, stored data, limits, pricing direction and support. |
| **[Build](/build/)** | Everything you write. From a ten-minute call to the whole SDK surface — the brain, the two hosting paths, the client, tools, actions, tests. |
| **[Improve the agent](/design/)** | How interruption, spoken output, tools and screen actions change the conversation design. |
| **[Operate](/operate/)** | Running it in production. Reading one call back, what persists per session, keys and limits. |
| **[API and protocols](/reference/)** | The wire, Brain API, voice catalog, errors and MCP tools. |

## Concepts

| Term | Definition |
|---|---|
| **Brain** | Your code. One WebSocket endpoint. Receives what the caller said, sends back what to say. |
| **Agent** | A record on our side, holding that endpoint's URL and the recording default. Configuration, not intelligence. |
| **Session** | One call. One connection, opened when it starts and closed when it ends. |
| **Action** | A typed message from the brain to the page. It renders; it is never spoken. |
| **Wire** | The protobuf frames on that connection. Versioned, and published in `proto/`. |
| **Cortex** | The relay, for a brain that cannot accept inbound connections. Your brain dials it; Voqalize dials it; it splices the two. |

**A note on the word *agent*.** You almost certainly call your own thing an
agent, and these pages sometimes will too. Ours is the record above — five
fields and a URL. When a sentence here says *create an agent* or *the agent's
`brain_url`*, it means the record. Your agent is the brain.

## A call, start to finish

1. Your server mints a session and gets a token.
2. Your page connects with that token. Media is direct UDP to a Voqalize media node.
3. The runtime dials `{brain_url}?session_id={session_id}` — one connection, this
   call only. Whatever your app passed at connect arrives as `session.init`,
   forwarded untouched.
4. Your brain greets. The caller is already connected and hearing nothing, so the
   greeting is a string — never a model call.
5. The caller speaks. The runtime endpoints the turn, transcribes it, and hands
   you the finalized text.
6. You yield speech. The first word plays while you are still producing the last.
7. If the caller interrupts, Voqalize stops mid-word and tells you where. Your
   history holds what was heard, not what you intended to say.
8. The connection closes. Events, logs and the recording are readable by
   `session_id`.

[A session, end to end](/build/session/) draws the same path with the frames on
it.

## What you keep

Your model, your prompts, your tools and your retrieval run in the process you
deploy today. The brain is code in your repository, under your version control,
and swapping the model behind it is a change we never see. Tool calls are local
function calls in your process, not webhooks we fire at you from rotating IPs.

Two Gemini adapters ship in the `gemini` extra: `GeminiBrain` and
`GeminiInteractionsBrain`. For Google ADK, LangChain, OpenAI Agents or another
framework, connect its text stream to `Brain` or implement the language-neutral
protobuf WebSocket contract. [Use another agent framework](/build/existing-agent/)
shows the integration and verification path.

## Where the brain runs

The default deployment is an inbound WebSocket route in your app. A laptop,
serverless function or egress-only network can use `serve(...)` to dial the
Cortex relay instead; this is also the default local-development path. The same
brain runs on either connection. See
[Where the brain runs](/build/hosting/).
