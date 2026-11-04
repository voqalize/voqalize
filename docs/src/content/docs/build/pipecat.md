---
title: Client libraries
description: The page side of a Voqalize session is pipecat's client with @voqalize/client-transport handling the media. What to install, the transport's options, what is pipecat's, the stock transport that still works, mobile clients, and the versions to pin.
---

In the browser, a Voqalize session runs on pipecat's client and its
`SmallWebRTCTransport`, with `@voqalize/client-transport` handling the
microphone, camera, screen share and the agent's audio. Your server installs
no pipecat: the Python SDK depends on none of it.

## Install

```bash
pnpm add @pipecat-ai/client-js @pipecat-ai/small-webrtc-transport @voqalize/client-transport@0.4.0
```

```ts
import { PipecatClient } from "@pipecat-ai/client-js";
import { createVoqalizeTransport } from "@voqalize/client-transport";

const client = new PipecatClient({
  transport: createVoqalizeTransport(),
  enableMic: true,
});
```

`client.connect(params)` takes the body `sessions.connect` returns.
[Connect your app](/build/connect/) has that request and the one line of glue
around it.

## What `@voqalize/client-transport` does

It is pipecat's own `SmallWebRTCTransport` with its media manager replaced. It is
MIT and [public](https://github.com/voqalize/voqalize-client-transport).

- **Loads nothing from a third party.** Pipecat's default media manager downloads
  daily's call machine from `c.daily.co` into your page. Ours uses
  `navigator.mediaDevices` only.
- **Recovers a session that goes quiet:** a microphone lost on reconnect, a
  device unplugged mid-sentence, blocked autoplay, an Android element that stops
  playing. The package's
  [FINDINGS](https://github.com/voqalize/voqalize-client-transport/blob/main/docs/FINDINGS.md)
  records each measurement.
- **Keeps a session across a page load** with `keepAcrossPageLoads: true`.
  [Connect your app](/build/connect/#keeping-a-call-across-a-page-load) has the
  code.

`createVoqalizeTransport(options?)` takes pipecat's `SmallWebRTCTransport`
options plus two of its own:

| Option | Default | What it does |
|---|---|---|
| `mediaManager` | A new `VoqalizeMediaManager` | Pass your own instance when your app needs a reference to it, for example to bind an audio element before the transport exists. |
| `keepAcrossPageLoads` | `false` | Remember this tab's session so `connect()` with no arguments rejoins it after a reload. Adds the read-only `transport.hasLiveCall`. |

## What stays pipecat's

The client API, signalling, hooks and RTVI are pipecat's, and behave as
[pipecat's documentation](https://docs.pipecat.ai/client/introduction) describes.
The ones a Voqalize page uses most:

- `usePipecatConversation` (React) for the transcript.
- `useUICommandHandler` (React) to receive the brain's
  [actions](/build/brain/actions/).
- `sendUIEvent` to send the brain an [app event](/build/brain/context/).
- `client.sendText(…)` to send a typed message. Voqalize commits it as a user
  turn, so your brain answers it in `on_user_message`.

The demos also use `@pipecat-ai/client-react` for hooks and
`@pipecat-ai/voice-ui-kit` for components; neither is required.
[RTVI messages](/reference/rtvi/) lists which message types cross to your brain.

[The avatar](/build/avatar/) is `@voqalize/avatar`, which takes the
`PipecatClient` you already have and renders from the same session's messages.

## Mobile apps

Pipecat publishes clients for React Native, native iOS and native Android, each
with a SmallWebRTC transport, and they connect to Voqalize with pipecat's own
transport. Our runnable examples are web only; start from pipecat's
[client SDK documentation](https://docs.pipecat.ai/client/introduction).

- **Start sessions from your backend with an `sk_` key.** A native app sends no
  `Origin` header, so a `pk_` key is refused with `403 origin_not_allowed`. Your
  app asks your backend, your backend calls `sessions.connect`, and the app hands
  the response to its pipecat client, as
  [Connect your app](/build/connect/#from-your-server-with-an-sk_-key) shows.
- **`@voqalize/client-transport` and `keepAcrossPageLoads` are web only.**

## Without our library

Pipecat's stock `SmallWebRTCTransport` still connects, and is documented for a
few more releases. Pass it where the example above passes
`createVoqalizeTransport()`:

```bash
pnpm add @pipecat-ai/client-js @pipecat-ai/small-webrtc-transport
```

```ts
import { PipecatClient } from "@pipecat-ai/client-js";
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport";

const client = new PipecatClient({ transport: new SmallWebRTCTransport(), enableMic: true });
```

On this path your page loads daily's call machine from `c.daily.co`, and none of
the recoveries above apply. To keep a session across a page load, follow
[the stock recipe](/build/connect/#on-pipecats-stock-transport).

## Versions

| Package | Version |
|---|---|
| `@voqalize/client-transport` | `0.4.0`, pinned exactly ([CHANGELOG](https://github.com/voqalize/voqalize-client-transport/blob/main/CHANGELOG.md)) |
| `@pipecat-ai/client-js` | `>=1.13.0 <2` (peer of our transport); `>=1.5.0 <2` on the stock transport |
| `@pipecat-ai/small-webrtc-transport` | `>=1.10.0 <2` (peer of our transport) |
| `voqalize-agent-sdk` (your server) | `==0.12.0`; installs websockets, protobuf, pydantic, a JWT library and loguru, and no pipecat |

## Read next

- [Connect your app](/build/connect/): the request, both keys, and the one line you write.
- [RTVI messages](/reference/rtvi/): what crosses between page and brain.
