---
title: Status and support
description: What is available today, what Voqalize fits, SDK and client versions, where the brain runs, region, stored session data and its 30-day retention, limits, pricing and support.
---

This page says what is available today and what is planned. PyPI's
[`voqalize-agent-sdk`](https://pypi.org/project/voqalize-agent-sdk/) page and the
`@voqalize/client-transport`
[CHANGELOG](https://github.com/voqalize/voqalize-client-transport/blob/main/CHANGELOG.md)
are the upstream records for the SDK surfaces.

## What Voqalize fits

Voqalize fits an app that already has a screen and users, and wants them to talk
to an agent that acts on that screen: a store, a bank's support flow, a booking
form, an internal console. You keep the agent's logic, model and data in your own
backend; Voqalize runs the voice. [Examples](/overview/examples/) shows the
patterns.

Today it does not place or answer phone (PSTN) calls, it does not host your
agent's model, and it runs in India only.

## Brain SDK

The published Python SDK is `voqalize-agent-sdk==0.12.0`, for Python 3.12 or
later. Pin the version you build against: releases before 1.0 may change the
brain API.

| Extra | Brain it ships |
|---|---|
| `gemini` | `GeminiBrain` (recommended), and `GeminiInteractionsBrain` (experimental; see [the shipped adapters](/reference/brain/#the-shipped-adapters)) |
| `openai` | `OpenAIBrain` |
| `litellm` | `LiteLLMBrain` |

Another framework or language connects through the published protobuf
[wire](/reference/wire/), checked by the conformance harness.
[Use another agent framework](/build/existing-agent/) shows how.

## App clients

The page side is your client on `@voqalize/client-transport@0.4.1`, which
handles the media. See [Client libraries](/build/client/).

| Environment | Client | Voqalize example |
|---|---|---|
| Web | `@pipecat-ai/client-js` with `@voqalize/client-transport` | Yes |
| React web app | `@pipecat-ai/client-react` with `@voqalize/client-transport` | Yes |

### Mobile apps

Voqalize is pipecat-compatible, and a native app uses pipecat's own client SDKs.

| Environment | Client | Voqalize example |
|---|---|---|
| React Native | Pipecat React Native with SmallWebRTC | Not yet |
| Native iOS | Pipecat Swift with SmallWebRTC | Not yet |
| Native Android | Pipecat Kotlin with SmallWebRTC | Not yet |

Every environment on this page is supported. A native app starts sessions from
your backend with an `sk_` key, because a `pk_` key works only from a browser
page ([Client libraries](/build/client/#mobile-apps)).

## Where the brain runs

Both connections are supported and run the same brain code. An inbound
WebSocket route in your app is the production default. The outbound
[Cortex](/build/session/#glossary) relay is the local-development default, and
suits serverless and egress-only networks. See
[Deploy the brain](/build/hosting/).

## Region and limits

There is one Voqalize environment, `app.voqalize.com`, and you use it for local
development and testing as well as for production. Sessions are processed and stored in India today. A United States region is
planned and cannot be selected yet.

A session lasts at most one hour. Every other limit, and what happens at it, is
in [Usage and limits](/operate/usage/#limits); included minutes and storage are
set by your plan ([pricing](https://voqalize.com/pricing)).

## Stored session data

| Data | Stored by Voqalize |
|---|---|
| Session record and `init` | Yes |
| Lifecycle and wire events | Yes |
| Transcripts | Yes, as part of the wire-event record |
| Voqalize logs | Yes |
| Audio, and camera and screen video | Only when the session records; video only for a lane the page turned on |
| Your brain's model history and logs | No; they stay in your environment |

**Stored session data, recordings included, is retained for 30 days.** Send
identifiers rather than personal data in `init`, and resolve them against your
own store.

## Pricing and support

Voqalize is priced per conversation minute. The minute includes speech
recognition, speech synthesis, turn-taking, WebRTC, the avatar and
observability. Your brain's model usage stays on your own model-provider
account.

Plans, included minutes, the free signup credit, support and uptime commitments
are on the [pricing page](https://voqalize.com/pricing).

## Read next

- [Build an agent](/build/): every step, in order.
- [Quickstart](/build/quickstart/): hear your first agent.
- [Going to production](/operate/production/): the checklist before launch.
