---
title: Client libraries
description: The page side of a Voqalize session is your client on @voqalize/client-transport. What to install, the transport's options, the client calls a Voqalize page uses, mobile clients, and the versions to pin.
---

In the browser, a Voqalize session runs on your client and
`@voqalize/client-transport`, which handles the microphone, camera, screen share
and the agent's audio. Your server installs neither: the Python SDK depends on
none of it.

## Install

```bash
pnpm add @pipecat-ai/client-js @pipecat-ai/small-webrtc-transport @voqalize/client-transport@0.4.1
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

It connects your client to the session over WebRTC and handles the media
itself. It is MIT and [public](https://github.com/voqalize/voqalize-client-transport).

- **Loads nothing from a third party.** It uses `navigator.mediaDevices` only, and
  no script is fetched from another origin into your page.
- **Recovers a session that goes quiet:** a microphone lost on reconnect, a
  device unplugged mid-sentence, blocked autoplay, an Android element that stops
  playing. The package's
  [FINDINGS](https://github.com/voqalize/voqalize-client-transport/blob/main/docs/FINDINGS.md)
  records each measurement.
- **Keeps a session across a page load** with `keepAcrossPageLoads: true`.
  [Connect your app](/build/connect/#keeping-a-call-across-a-page-load) has the
  code.

`createVoqalizeTransport(options?)` takes the `SmallWebRTCTransport` options plus
these of its own:

| Option | Default | What it does |
|---|---|---|
| `mediaManager` | A new `VoqalizeMediaManager` | Pass your own instance when your app needs a reference to it, for example to bind an audio element before the transport exists. |
| `keepAcrossPageLoads` | `false` | Remember this tab's session so `connect()` with no arguments rejoins it after a reload. Adds the read-only `transport.hasLiveCall`. |

## The client

What a Voqalize page calls on the client:

- `client.connect(params)` starts the session with the body `sessions.connect`
  returned. It resolves when `RTVIEvent.BotReady` fires, and from then on the
  client can send.
- `client.disconnectBot()` ends the session at once, and `client.disconnect()`
  closes the connection.
- `sendUIEvent(name, payload)` sends the brain an
  [app event](/build/brain/context/). It throws before `RTVIEvent.BotReady`, so
  send from a handler that runs after `connect` resolves.
- `client.sendText(…)` sends a typed message. Voqalize commits it as a user turn,
  so your brain answers it in `on_user_message`.
- `client.on(RTVIEvent.UICommand, …)` receives the brain's
  [actions](/build/brain/actions/) as `{ command, payload }`.

In React, from `@pipecat-ai/client-react`:

- `useUICommandHandler` receives one action by name.
- `usePipecatConversation` gives the transcript.

`@pipecat-ai/client-react` and `@pipecat-ai/voice-ui-kit` are optional.
[RTVI messages](/reference/rtvi/) lists which message types cross to your brain.

[The avatar](/build/avatar/) is `@voqalize/avatar`, which takes the client you
already have and renders from the same session's messages.

## Mobile apps

Voqalize is pipecat-compatible. A native app (React Native, iOS or Android) uses
pipecat's own client SDKs, each with a SmallWebRTC transport. Our runnable
examples are web only; start from pipecat's
[client SDK documentation](https://docs.pipecat.ai/client/introduction).

- **Start sessions from your backend with an `sk_` key.** A native app sends no
  `Origin` header, so a `pk_` key is refused with `403 origin_not_allowed`. Your
  app asks your backend, your backend calls `sessions.connect`, and the app hands
  the response to its pipecat client, as
  [Connect your app](/build/connect/#from-your-server-with-an-sk_-key) shows.
- **`@voqalize/client-transport` and `keepAcrossPageLoads` are web only.**

## Versions

| Package | Version |
|---|---|
| `@voqalize/client-transport` | `0.4.1`, pinned exactly ([CHANGELOG](https://github.com/voqalize/voqalize-client-transport/blob/main/CHANGELOG.md)) |
| `@pipecat-ai/client-js` | `>=1.13.0 <2` (peer of our transport) |
| `@pipecat-ai/small-webrtc-transport` | `>=1.10.7 <2` (peer of our transport) |
| `voqalize-agent-sdk` (your server) | `==0.12.0`; installs websockets, protobuf, pydantic, a JWT library and loguru |

## Read next

- [Connect your app](/build/connect/): the request, both keys, and the one line you write.
- [RTVI messages](/reference/rtvi/): what crosses between page and brain.
