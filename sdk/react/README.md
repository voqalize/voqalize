# @voqalize/client-react

Mint a [Voqalize](https://voqalize.com) voice session for a pipecat client.

You bring the brain, we bring the voice.

**A Voqalize call is a pipecat call.** The media transport is pipecat's own
`SmallWebRTCTransport`, the events are RTVI's, the transcript arrives on
`onBotTranscript`, and the brain's UI commands arrive at pipecat's
`useUICommandHandler`. None of that needs a wrapper from us, so this package
ships none: it is one function, the connection step, and nothing else.

Everything else you need is `@pipecat-ai/client-js` and
`@pipecat-ai/client-react`, documented by pipecat, upgradable on pipecat's
release notes, and debuggable with everything already written about them.

## Install

```bash
pnpm add @voqalize/client-react @pipecat-ai/client-js @pipecat-ai/client-react @pipecat-ai/small-webrtc-transport
```

This package itself has no dependencies and no peers — it is fetch and JSON.

> **Working from this repo?** It lives at `sdk/react/` and is part of the repo's
> `pnpm` workspace: build it in place with
> `pnpm --filter @voqalize/client-react build`.

## Connect

Connecting is pipecat's two-step — ask something that holds a credential where
the bot is, then negotiate WebRTC against the address you were given.
`createSession` is step one:

```tsx
import { PipecatClient } from "@pipecat-ai/client-js";
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport";
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

`publishableKey` is safe in page source — that is what publishable means. It is
scoped to one agent and to the origins you allowlist when you mint it.

`payload` is handed to the brain at connect and **persisted on the session**, so
it is readable later by anyone who can read the session. Send identifiers, not
personal data.

`createSession` throws `VoqalSessionError` (carrying the HTTP `status`) when the
control plane refuses.

## In React

Wrap the app in pipecat's provider and use pipecat's hooks. There is no Voqalize
layer here at all:

```tsx
import { PipecatClientProvider, useUICommandHandler } from "@pipecat-ai/client-react";

function Screen() {
  useUICommandHandler<{ items: Item[] }>("log_meal", ({ items }) => setItems(items));
  return …;
}

<PipecatClientProvider client={client}>
  <Screen />
</PipecatClientProvider>;
```

`useUICommandHandler(command, handler)` is the browser half of the brain's
`session.dispatch(...)` — a Python `Action` subclass arrives as an RTVI
`ui-command` whose `command` is the action's wire name and whose `payload` is its
fields. Answering goes back the other way on `sendClientMessage(type, data)`,
which reaches the brain's `on_rtvi`.

## Minting on your own backend

`publishableKey` puts the decision to start a call in the page. That is right for
a public demo and wrong the moment starting a call depends on something the
browser must not be trusted with — who the caller is, whether they still have
credit, which agent they are entitled to. For that, mint on a route of your own
that holds a secret (`sk_…`) key, and run the response through
`toConnectParams`:

```tsx
import { toConnectParams } from "@voqalize/client-react";

const body = await fetch("/api/voice/start", {
  method: "POST",
  credentials: "include",
}).then((r) => r.json());

await client.connect(toConnectParams(body.connect_params));
```

Where `connect_params` is what the Voqalize API returned verbatim:

```json
{
  "webrtc_request_params": {
    "endpoint": "https://signal.voqalize.com/webrtc",
    "headers": { "Authorization": "Bearer <session token>" }
  },
  "session_id": "01J…"
}
```

**Run every server response through `toConnectParams`, including your own
backend's.** It is not a formality: pipecat builds the offer request with
`headers.entries()`, so the plain object a JSON body gives you throws a
`TypeError` at the offer POST rather than failing anywhere legible. Turning it
into a real `Headers` is what this function is for.

## Voice and language belong to the brain

`createSession` accepts a `pipeline` override, and **most pages should not set
it**. How an agent sounds is declared in Python:

```python
class ConciergeBrain(GeminiBrain):
    voice = "omnivoice/gauri"
    language = "hi"          # the recognizer AND the TTS voice, together
```

and, when it depends on *this* caller, `session.configure_language(...)` inside
`on_session_start`. The two legs move together or the call is silently wrong: the
words stay correct while an English reference voice reads Devanagari, which no
transcript, log or WER score can see. Set it in one place, and let that place be
the one that sees the caller.

## Recording is a per-call decision

`record: false` is always honoured, so a caller who declines is never recorded
even on an agent that records by default. `record: true` is **refused** on a
publishable key — it ships in page source, so anyone holding it could otherwise
write voice into your storage on your bill. Turn recording on where its owner
controls it: the agent's own default, over MCP or in the console.

## Exports

`createSession`, `toConnectParams`, `VoqalSessionError`, and the types
`CreateSessionOptions`, `VoqalConnectParams`, `VoqalPipelineConfig`.
