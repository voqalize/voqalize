---
title: Client libraries
description: The browser half of a Voqalize call is pipecat's client with @voqalize/client-transport handling the media. What is ours, what is pipecat's, the stock path that still works, and which versions we hold to.
---

In the browser, a Voqalize call runs on pipecat's client and transport, with
`@voqalize/client-transport` handling the microphone, camera and the agent's
audio. Inside the voice tier, pipecat is what we build the pipeline out of. Its
RTVI message format is what our wire carries between the two.

Your server has no pipecat. Installing the Python SDK pulls in none of it.

## The browser half

Install pipecat's client and transport, and our media manager:

```bash
pnpm add @pipecat-ai/client-js @pipecat-ai/small-webrtc-transport @voqalize/client-transport@0.3.0
```

```ts
import { PipecatClient } from "@pipecat-ai/client-js";
import { createVoqalizeTransport } from "@voqalize/client-transport";

const client = new PipecatClient({
  transport: createVoqalizeTransport(),
  enableMic: true,
});
```

`sessions.connect` returns the connect params, and `client.connect(params)`
takes them. [The handshake](/build/connect/) covers that request and the one
line of glue around it.

`@voqalize/client-transport` is MIT and
[public](https://github.com/voqalize/voqalize-client-transport). It is pipecat's
own `SmallWebRTCTransport` with its `MediaManager` replaced. What that adds:

- **Keeps the page free of daily.** Pipecat's default media manager downloads
  daily's call machine from `c.daily.co` into your page on every call. Ours uses
  `navigator.mediaDevices` and nothing else.
- **Recovers a call that goes quiet.** It covers a microphone lost on reconnect,
  a device unplugged mid-sentence, a blocked autoplay, and an Android element
  that stops playing. Each case is measured in the package's `FINDINGS.md`.
- **Keeps a call across a page load.** `keepAcrossPageLoads: true` lets a reload,
  or a link to another page of your site, carry on with the same call.
  [Connecting a page](/build/connect/#keeping-a-call-across-a-page-load) has the
  code.

Signalling, the client API, the hooks and RTVI stay pipecat's. `usePipecatConversation`
for the transcript, `useUICommandHandler` for inbound actions and `sendUIEvent`
for outbound context are documented by pipecat and behave the same against any
pipecat server. The demos also use `@pipecat-ai/client-react` for hooks and
`@pipecat-ai/voice-ui-kit` for components. Neither is required.

## Without our library

Pipecat's stock `SmallWebRTCTransport` still connects to Voqalize, and we
document it for a couple more releases. Pass it where the example above passes
`createVoqalizeTransport()`:

```bash
pnpm add @pipecat-ai/client-js @pipecat-ai/small-webrtc-transport
```

```ts
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport";

const client = new PipecatClient({ transport: new SmallWebRTCTransport(), enableMic: true });
```

On this path your page loads daily's call machine from `c.daily.co`, and none of
the recoveries above apply. To keep a call across a page load, follow
[the stock recipe](/build/connect/#on-pipecats-stock-transport). A later release
drops this section, and from then on the docs cover only
`@voqalize/client-transport`.

## Web, React Native and native mobile

`@voqalize/client-transport` is a browser package. Pipecat also publishes
clients for React Native, native iOS and native Android, with SmallWebRTC
transports for each. Voqalize uses those interfaces directly, so each of them is
a supported client environment, on pipecat's own transport.

Our runnable examples currently cover web only. For React Native, Swift or
Kotlin, start with Pipecat's official
[client SDK documentation](https://docs.pipecat.ai/client/introduction) and use
the same `sessions.connect` response described in [connecting a
page](/build/connect/).

## The message layer is RTVI

An action from your brain and a click from your page are both RTVI messages —
`{id, label, type, data}` — riding the peer connection's data channel. Our wire
carries the whitelisted types verbatim in both directions and interprets nothing
about them.

`client.sendText(…)` is the one exception to "verbatim": a typed sentence takes
the floor the way a spoken one does, so Voqalize commits it as a user turn and
your brain answers it in `on_user_message` rather than receiving a message.

Which types cross, which do not, and why the exclusions are what let your page
trust `bot-started-speaking`, are [the RTVI plane](/reference/rtvi/). The
enumeration of record is `RTVIType` in
[`proto/voqalize/frames/frames.proto`](https://github.com/voqalize/voqalize/blob/main/proto/voqalize/frames/frames.proto).

## Your server has no pipecat in it

`pip install voqalize-agent-sdk==0.6.0` installs websockets, protobuf, pydantic and the
JWT library, and nothing else. A brain is callbacks over a socket. Pipecat runs
on our side of that socket, where the audio is.

That matters when your brain is a route inside a service you already deploy: a
voice integration adds no media dependency to a process that has never needed
one, and nothing in your dependency tree has an opinion about audio.

## The avatar rides RTVI

[The avatar](/build/avatar/) is a talking head driven by RTVI messages rather
than by a video track. Voqalize sends the state and the mouth shapes from inside
the call's pipeline; in the browser, `@voqalize/avatar` takes the
`PipecatClient` you already have and renders them.

## Versions

`@voqalize/client-transport` 0.3.0 needs `@pipecat-ai/client-js` at
`>=1.13.0 <2` and `@pipecat-ai/small-webrtc-transport` at `>=1.10.0 <2`, as peer
dependencies. Pin our package at an exact version. Its
[CHANGELOG](https://github.com/voqalize/voqalize-client-transport/blob/main/CHANGELOG.md)
says what each release changes.

Without our library, the floor is `@pipecat-ai/client-js` at `>=1.5.0 <2`,
declared as a peer dependency in `demos/shared/package.json`. We track
pipecat's 1.x line and pin no upper bound below the major.

The Python side pins `pipecat-ai` only inside the voice tier, which you do not
install.

## Read next

- [Connections and the handshake](/build/connect/) — the request, both credential paths, and the one line you write.
- [The wire](/reference/wire/) — how an RTVI message crosses to your brain.
