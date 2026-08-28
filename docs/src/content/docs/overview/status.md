---
title: Current status and supported environments
description: What is available during developer preview — SDK stability, clients, hosting, regions, stored data, limits, and the direction for pricing and support.
---

Voqalize is in developer preview. Build and test an embedded agent now; plan for
API changes, rate limiting and availability interruptions. The preview has no
service-level agreement.

This page separates what is available today from what is planned. The
[Python package on PyPI](https://pypi.org/project/voqalize-agent-sdk/) and
[Pipecat's client documentation](https://docs.pipecat.ai/client/introduction)
are the upstream records for the two SDK surfaces.

## Brain SDK

The published Python brain SDK is `voqalize-agent-sdk==0.2.0`. It requires
Python 3.12 or later and is classified as alpha. Pin the version: the callbacks
and wire may change before 1.0.

Two Gemini integrations ship with the `gemini` extra: `GeminiBrain` and
`GeminiInteractionsBrain`. Other agent frameworks and languages connect through
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

All five are supported client environments. The Voqalize repository currently
ships complete examples only for web. For a native client, use the official
Pipecat client and SmallWebRTC guide; the session-connect response supplies the
endpoint and session credential that its transport uses. The current
[connection guide](/build/connect/) shows the web implementation.

## Where the brain runs

Both connection paths are supported and run the same brain:

- An inbound WebSocket route in your application is the default deployment.
  Voqalize opens one connection per session.
- An outbound [Cortex relay](/build/outbound/) is supported for egress-only
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

Developer-preview workspaces may be rate-limited and have concurrent-call
ceilings. The ceilings are assigned per workspace and no public number is
committed. Ask before a pilot or launch that needs a specific concurrency
level.

## Stored session data

| Data | Stored by Voqalize during the preview |
|---|---|
| Session record and `init` | Yes |
| Lifecycle and wire events | Yes |
| Transcripts | Yes, as part of the wire-event record |
| Voqalize logs | Yes |
| Audio | Only when recording is enabled for that session |
| Brain model history and brain logs | No; these remain in your environment |

Retention is not configurable or guaranteed during developer preview. Do not
place personal data in `init`, and do not build a compliance requirement around
an assumed retention interval. Fine-grained retention and access controls are
planned for paid plans; their shape and availability date are not committed.

## Pricing and support direction

The developer preview is free. Prices for paid plans are not set.

Paid pricing is planned per session minute and will include speech recognition,
speech synthesis, endpointing, WebRTC, the avatar, monitoring, observability and
service operation. Your brain owns its model, so its LLM usage remains on your
model-provider account and outside the Voqalize minute.

Paid plans are planned to include ticket-based support. Enterprise plans will
support negotiated support contracts. No response-time commitment applies
during developer preview.

## Read next

- [A session, end to end](/build/session/) — the complete application path.
- [Quickstart](/build/quickstart/) — build the first web call.
- [Usage and limits](/operate/usage/) — the counters available during preview.
- [The wire](/reference/wire/) — implement and verify a brain in another language.
