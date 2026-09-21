---
title: Current status and supported environments
description: What is available today — SDK versions, clients, hosting, regions, stored data and retention, and where plans, limits and support are set.
---

This page separates what is available today from what is planned. The
[Python package on PyPI](https://pypi.org/project/voqalize-agent-sdk/) and
[Pipecat's client documentation](https://docs.pipecat.ai/client/introduction)
are the upstream records for the SDK surfaces.

## Brain SDK

The published Python brain SDK is `voqalize-agent-sdk==0.5.0`. It requires
Python 3.12 or later. Pin the version you build against: releases before 1.0
may change the brain callbacks.

The `gemini` extra ships `GeminiBrain` and `GeminiInteractionsBrain`.

:::caution[`GeminiInteractionsBrain` is experimental]
Every demo brain runs on `GeminiBrain`, and the last one that did not moved across
on 2026-09-08. The interactions adapter's interruption path has open defects —
a step interrupted before its first delta stays in the context forever, and text
buffered during a step is discarded if a barge-in lands before the step
closes. Build on `GeminiBrain`; this one is kept, and tested, for the
properties it has that `generate_content` does not.
:::

Other agent frameworks and languages connect through
the published protobuf WebSocket [wire](/reference/wire/). The English
specification and the conformance harness are the compatibility path: implement
the wire around the framework's own text stream, then run the harness before
connecting a live call. See [bringing an agent you already have](/build/existing-agent/).

## App clients

Voqalize uses Pipecat's RTVI and SmallWebRTC client surfaces directly.

| Environment | Client | Voqalize example |
|---|---|---|
| Web | Pipecat JavaScript | Yes |
| React web app | Pipecat React | Yes |
| React Native | Pipecat React Native with SmallWebRTC | Not yet |
| Native iOS | Pipecat Swift with SmallWebRTC | Not yet |
| Native Android | Pipecat Kotlin with SmallWebRTC | Not yet |

All of these are supported client environments. The Voqalize repository currently
ships complete examples only for web. For a native client, use the official
Pipecat client and SmallWebRTC guide; the session-connect response supplies the
endpoint and session credential that its transport uses. The current
[connection guide](/build/connect/) shows the web implementation.

## Where the brain runs

Both connection paths are supported and run the same brain:

- An inbound WebSocket route in your application is the default deployment.
  Voqalize opens one connection per session.
- An outbound [Cortex relay](/build/hosting/#a-brain-that-dials-out) is supported for egress-only
  environments and is the default local-development path because the brain
  needs no public tunnel.

Build toward inbound for production unless the environment cannot accept a
WebSocket connection. See [where the brain runs](/build/hosting/).

## Configuration ownership

The agent record stores the brain URL and an optional recording default. It
stores no voice, language, recognizer or idle configuration.

`sessions.connect` accepts `tts`, `stt`, `idle` and `record` immediately before
the call starts. A browser holding a publishable `pk_` may call that route and
set the same values, with one recording rule: `record: false` is accepted and
`record: true` is refused. A backend holding an `sk_` may set either value.

During the call, the brain may update `tts`, `stt` and `idle` with
`await session.configure(...)`. Recording is fixed when the call starts and
cannot change mid-session. [Voice and language](/reference/catalog/) and
[recordings](/operate/recordings/) carry the full rules.

## Regions and availability

Calls are processed and stored in India today. A United States region is
planned and is not available for selection yet.

The MCP server is rate limited per tenant; a refused request is a `429`
with a `Retry-After` header. Concurrent sessions, included minutes and storage
are set by your plan; [pricing](https://voqalize.com/pricing) lists each plan's
allowance. Talk to us before a launch that needs more than a plan carries.

## Stored session data

| Data | Stored by Voqalize |
|---|---|
| Session record and `init` | Yes |
| Lifecycle and wire events | Yes |
| Transcripts | Yes, as part of the wire-event record |
| Voqalize logs | Yes |
| Audio | Only when recording is enabled for that session |
| Brain model history and brain logs | No; these remain in your environment |

Stored session data, recordings included, is retained for 30 days. Send
identifiers rather than personal data in `init`, and resolve them against your
own store.

## Pricing and support

Voqalize is priced per conversation minute. The minute includes speech
recognition, speech synthesis, endpointing, WebRTC, the avatar and
observability. Your brain owns its model, so its LLM usage remains on your
model-provider account and outside the Voqalize minute.

Plans, their included minutes, the free signup credit, support and uptime
commitments are on the [pricing page](https://voqalize.com/pricing).

## Read next

- [A session, end to end](/build/session/) — the complete application path.
- [Quickstart](/build/quickstart/) — build the first web call.
- [Usage and limits](/operate/usage/) — the counters for your tenant.
- [The wire](/reference/wire/) — implement and verify a brain in another language.
