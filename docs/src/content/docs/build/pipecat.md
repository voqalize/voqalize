---
title: Voqalize and pipecat
description: Pipecat is the browser half of a Voqalize call and the message layer between them. What is ours, what is theirs, and which versions we hold to.
---

Pipecat sits at both ends of a Voqalize call, and at neither end is it wrapped.

In the browser it **is** your integration: one HTTP request of ours returns what a
pipecat transport connects with, and every line after that is pipecat. Inside the
voice tier it is what we build the pipeline out of — transport, voice activity
detection, the speech services, the avatar processor. Between the two, its RTVI
message format is what our wire carries.

The one place it is absent is your server. Installing the Python SDK pulls no
pipecat at all.

## The browser half

Two packages do the work:

```bash
pnpm add @pipecat-ai/client-js @pipecat-ai/small-webrtc-transport
```

`sessions.connect` returns the connect params; `client.connect(params)` takes
them. [The handshake](/build/connect/) is that request and the one line
of glue around it, and it is the entire Voqalize-specific surface in your page.

The demos add two more, and neither is required: `@pipecat-ai/client-react` for
the hooks, and `@pipecat-ai/voice-ui-kit` for components. What every demo uses is
declared in [`demos/shared/package.json`](https://github.com/voqalize/voqalize/blob/main/demos/shared/package.json).

Everything you learn here transfers. `usePipecatConversation` for the transcript,
`useUICommandHandler` for inbound actions, `sendClientMessage` for outbound
context — those are pipecat's APIs, documented by pipecat, and they behave the
same against any pipecat server.

## The message layer is RTVI

An action from your brain and a click from your page are both RTVI messages —
`{id, label, type, data}` — riding the peer connection's data channel. Our wire
carries them verbatim in both directions and interprets nothing about them.

The whitelist, in both directions:

| Brain → page | Page → brain |
|---|---|
| `server-message` | `client-message` |
| `server-response` | `send-text` |
| `error-response` | `ui-event` |
| `ui-command` | `ui-snapshot` |
| `ui-job-group` | `ui-cancel-job-group` |

A type absent from that list does not cross in either direction. `bot-*` and
`llm-*` are the voice tier's own assertions about the media and the model — that
speech started, that the model is thinking — and a brain must not be able to
forge them. Your page can trust a `bot-started-speaking` because only Voqalize
that moved the audio can emit one.

The list is enumerated in
[`proto/voqalize/frames/frames.proto`](https://github.com/voqalize/voqalize/blob/main/proto/voqalize/frames/frames.proto),
which is the contract of record.

## Your server has no pipecat in it

`pip install voqalize-agent-sdk==0.2.0` installs websockets, protobuf, pydantic and the
JWT library, and nothing else. A brain is callbacks over a socket. Pipecat runs
on our side of that socket, where the audio is.

That matters when your brain is a route inside a service you already deploy: a
voice integration adds no media dependency to a process that has never needed
one, and nothing in your dependency tree has an opinion about audio.

## The avatar is a pipecat processor

[The avatar](https://github.com/voqalize/avatar) is a talking head driven by RTVI
rather than by a video track. `AvatarProcessor` sits in the pipeline between
text-to-speech and the output transport and emits lipsync metadata as one custom
RTVI message; the browser package renders it. It works against any pipecat
pipeline, not only ours, and it is MIT-licensed.

## We ship no client library

There was one — `@voqalize/client-react` — and it was deprecated on 2026-08-24
with no successor. It wrapped the connect call and re-exported hooks that were
already pipecat's, which made it a second surface to learn and a release behind
every pipecat version.

The class of problem it existed to hide is now handled where it belongs: the two
credential paths are [the same route with a different signer](/build/connect/),
and a recording asked for on a key that may not record is refused when the
session is minted rather than warned about in a console.

## Versions

`@pipecat-ai/client-js` at `>=1.5.0 <2` is the floor, declared as a peer
dependency in `demos/shared/package.json` and exercised by every demo in the
repository. We track pipecat's 1.x line and pin no upper bound below the major.

The Python side pins `pipecat-ai` only inside the voice tier, which you do not
install.

## Read next

- [Connections and the handshake](/build/connect/) — the request, both credential paths, and the one line you write.
- [The wire](/reference/wire/) — how an RTVI message crosses to your brain.
