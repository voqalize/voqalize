---
title: React client SDK
description: Embed a live voice agent in a browser app — mint a session with Voqalize, then run the call on stock pipecat.
---

`@voqalize/client-react` is one function. It mints a session against the control
plane and hands back the offer endpoint and token a pipecat transport dials.
Everything after that — the WebRTC connection, the audio, the transcript, the
agent's UI commands — is [pipecat](https://docs.pipecat.ai)'s own client, used
directly, with nothing of ours in between.

That is the whole design. A Voqalize call **is** a pipecat call: the transport is
`SmallWebRTCTransport`, the control messages are RTVI, and a brain's
`session.dispatch(...)` arrives at pipecat's `useUICommandHandler`. A wrapper
around any of it would be a second surface to learn, a lag behind every pipecat
release, and one more place a frame can be dropped in translation. So there
isn't one.

:::note[Pre-release]
Not yet on npm. Install from a clone of
[`voqalize/voqalize`](https://github.com/voqalize/voqalize) via the pnpm
workspace. The package itself has no dependencies; you install pipecat.
:::

## Install

```bash
pnpm add @voqalize/client-react @pipecat-ai/client-js @pipecat-ai/client-react @pipecat-ai/small-webrtc-transport
```

## Connect

Connecting is pipecat's two-step: ask something that holds a credential where the
bot is, then negotiate WebRTC against the address you were given.
`createSession` is step one.

```tsx
import { PipecatClient } from "@pipecat-ai/client-js";
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport";
import { PipecatClientProvider, PipecatClientAudio } from "@pipecat-ai/client-react";
import { createSession } from "@voqalize/client-react";

const client = new PipecatClient({
  transport: new SmallWebRTCTransport(),
  enableMic: true,
});

await client.connect(
  await createSession({
    apiBase: "https://api.voqalize.com/api/v1",
    publishableKey: "pk_live_…",
    agentId: "…",
    payload: { orderId },
  }),
);
```

```tsx
<PipecatClientProvider client={client}>
  <YourApp />
  <PipecatClientAudio />
</PipecatClientProvider>
```

`PipecatClientAudio` is what plays the agent. Everything your UI needs to read
the call comes off pipecat's hooks — `usePipecatClientTransportState`,
`usePipecatClientMicControl`, `usePipecatConversation`, `useRTVIClientEvent`.

### What the mint call does

One `POST {apiBase}/sessions.create`, with the publishable key as a bearer token
and a body of `{ agent_id, agent_input: { pipeline?, payload? }, record? }`.

Your app data nests one level in, under `agent_input.payload`. `record` rides
*beside* `agent_input`, not inside it — `agent_input` is what the page hands the
brain, and recording is not the brain's business.

`agent_input` goes two places at once: it is signed into the session token, which
is how the runtime and then the brain receive it, and it is **stored on the
session**, so you can still answer "what did the page send?" after the token has
expired. Stored means readable by anyone who can read the session — send
identifiers, not personal data.

The response carries `connection_details.connect_params`: the runtime node's
offer endpoint and the session token to present on it. A missing `connect_params`
means no worker is running for that agent, and `createSession` throws a
`VoqalSessionError` saying so. Every failure is a `VoqalSessionError` carrying
the HTTP `status`.

## Driving the screen

An agent that only talks needs nothing on this page. An agent that moves the UI
uses two channels, and both are RTVI's.

**Brain → browser.** The brain's `session.dispatch(ShowResults(...))` arrives as
an RTVI `ui-command`:

```json
{ "command": "show_results", "payload": { "rows": [] } }
```

`command` is the action class's wire name; `payload` is its fields, nested rather
than spread — so no field of yours can ever collide with the envelope. Pipecat
routes it for you:

```tsx
import { useUICommandHandler } from "@pipecat-ai/client-react";

useUICommandHandler<{ rows: Row[] }>("show_results", ({ rows }) => setRows(rows));
```

A command with no handler is not an error. The brain and the page ship
separately, and a new command reaching an old build must not break it.

**Browser → brain.** `client.sendClientMessage(type, data)` reaches the brain's
`on_rtvi(session, msg)` as `msg.data == { t: type, d: data }`.

Dispatch is **one-way**: nothing comes back from it and it never blocks. If the
brain needs an answer — which flight did they pick, did the form validate — the
page sends an ordinary client message and correlates it with whatever the two
halves agree on. There is no reply channel to learn, because there is no reply
channel: it is the same message lane in the other direction.

## The microphone

Every session needs one, and the browser will not hand one over quietly. Pipecat
owns this — it asks for the device and reports what happened on `onDeviceError`
with a `DeviceError` whose `type` you branch on (`"permissions"`, `"not-found"`,
`"in-use"`, `"undefined-mediadevices"`, `"constraints"`, `"unknown"`).

Three things about it are worth knowing before you ship, none of them
Voqalize-specific and all of them found the hard way:

**The page must be a secure context** — `https://`, or `localhost` while you
develop. On plain `http://` the browser does not expose microphones at all, and
the connect fails immediately (`undefined-mediadevices`).

**The grant is per origin.** Allowing the microphone on the deployed site grants
nothing to `localhost`, and the other way round. The first call on each origin
asks again — including the first call after you ship.

**A permission prompt can stay open forever**, and a caller who missed the dialog
has no reason to think the browser is waiting on them. Render something that
says *go look for the dialog*, not a spinner: "connecting" tells the user to
wait, which is the opposite of what they need to do.

## Minting on your own backend

`publishableKey` puts the decision to start a call in the page. That is right for
a public demo and wrong the moment starting a call depends on something the
browser must not be trusted with — who the caller is, whether they still have
credit, which agent they are entitled to.

For that, mint on a route of your own holding a secret (`sk_…`) key, return the
API's `connect_params` verbatim, and run them through `toConnectParams`:

```tsx
import { toConnectParams } from "@voqalize/client-react";

const body = await fetch("/api/voice/start", {
  method: "POST",
  credentials: "include",
}).then((r) => r.json());

await client.connect(toConnectParams(body.connect_params));
```

**Run every server response through `toConnectParams`, including your own
backend's.** Pipecat builds the offer request with `headers.entries()`, so the
plain object a JSON body gives you throws a `TypeError` at the offer POST rather
than failing anywhere legible. Turning it into a real `Headers` is what this
function is for.

## Voice and language belong to the brain

`createSession` accepts a `pipeline` override, and **most pages should not set
it**. How an agent sounds is declared in Python, on the brain:

```python
class ConciergeBrain(GeminiBrain):
    voice = "omnivoice/gauri"
    language = "hi"          # the recognizer AND the TTS voice, together
```

and, when it depends on *this* caller, `session.configure_language(...)` inside
`on_session_start`.

The two legs move together or the call is silently wrong. `tts.language` picks
the voice-cloning reference clip and `stt.language_hint` picks the recognizer;
move one without the other and the words stay correct while an English voice
reads Devanagari. No transcript, log, metric or WER score can see that. It is
found by ear, weeks later, and it was found by ear here. Set it in one place, and
let that place be the one that sees the caller — see the
[Voice & language catalog](/docs/reference/catalog/).

## Recording is a per-call decision

`record: false` is always honoured, so a caller who declines is never recorded
even on an agent that records by default.

`record: true` is **refused** on a publishable key. A `pk_` key ships in page
source, so anyone holding it could otherwise write voice into your storage, on
your bill, for an agent whose owner chose not to record. The call still runs and
nothing about it sounds wrong, so `createSession` warns on the console when it
happens. Turn recording on where its owner controls it: the agent's own default,
over MCP or in the console.

## Exports

`createSession`, `toConnectParams`, `VoqalSessionError`, and the types
`CreateSessionOptions`, `VoqalConnectParams`, `VoqalPipelineConfig`.

That is the entire package. Everything else you reach for is pipecat's.

## Next

- **[The wire](/docs/reference/wire/)** — the frames underneath all of this,
  and the contract they keep.
- **[Testing a brain](/docs/brain/testing/)** — the other end of the UI
  contract, asserted on the frames.
- **[Voice & language catalog](/docs/reference/catalog/)** — the voices and
  languages, and why the brain is the one place that sets them.
