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
    - text: Quickstart
      link: /build/quickstart/
      icon: right-arrow
      variant: primary
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

That is the whole integration. What follows is what is on each side of it.

## The boundary is text

Below the line is ours, and it is the same for every agent anyone will write:
WebRTC, echo cancellation, voice activity detection, endpointing, speech-to-text,
text-to-speech, turn-taking, interruption, recording.

Above the line is yours: what to say, what to do, what the caller is allowed to
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

The browser half ships no library of ours, which is also why mobile is not a
separate integration: pipecat's iOS and Android clients speak the same transport
the web one does. [Connecting a page](/build/connect/) is the whole of it.

## Where you are

| Section | What is in it |
|---|---|
| **[Build](/build/)** | Everything you write. From a ten-minute call to the whole SDK surface — the brain, the two hosting paths, the client, tools, actions, tests. |
| **[Designing for voice](/design/)** | What changes when the output is spoken and the caller can interrupt. The durable half, and the one nobody hands you. |
| **[Operate](/operate/)** | Running it in production. Reading one call back, what persists per session, keys and limits. |
| **[Reference](/reference/)** | The contracts. The wire, the Brain API, the catalog, error codes, the management API, the MCP server. |

## Concepts

| Term | Definition |
|---|---|
| **Brain** | Your code. One WebSocket endpoint. Receives what the caller said, sends back what to say. |
| **Agent** | A record on our side, holding that endpoint's URL and the voice to use. Configuration, not intelligence. |
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

Two adapters ship, both Gemini, both in the `gemini` extra: `GeminiBrain` and
`GeminiInteractionsBrain`. Everything else — Google ADK, LangChain, OpenAI
Agents, a hand-rolled state machine — is a subclass of `Brain` and a loop over
your own stream, which is about the same amount of code an adapter saves you.
**There is no adapter to wait for**, and that is the point rather than a gap: an
adapter per framework is a lag behind every framework's next release, and the
boundary is text precisely so that nothing has to sit between your stream and
ours. [Bringing an agent you already have](/build/existing-agent/) is the whole
of it.

## Where the brain runs

Two paths, and no third. **Your app owns the route** — accept the WebSocket
upgrade and hand the socket to `run_session`; this is the primary path. Or **your
app cannot accept inbound** — a laptop, a serverless function, an egress-only
network — and `serve(...)` dials a relay instead. The same brain runs on either
and nothing in your code changes. See
[Where the brain runs](/build/hosting/).
