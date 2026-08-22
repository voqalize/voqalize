# @voqalize/client-react

Embed a [Voqalize](https://voqalize.com) voice agent in a React app. Ships a
one-call session bootstrap and a hook + component that manage the whole
voice-session lifecycle.

You bring the brain, we bring the voice.

**The media transport is pipecat's own `SmallWebRTCTransport`**, not one of ours.
A Voqalize session's connection details are an offer endpoint and a token, which
is exactly what it already speaks — so the WebRTC half of your app is stock
pipecat, upgradable and debuggable with everything written about it. What this
package adds is the half pipecat leaves to you: minting the session, the
microphone and its failure modes, and the UI around a live call.

## Install

```bash
pnpm add @voqalize/client-react
# peers you already have in a React app:
pnpm add @pipecat-ai/client-js @pipecat-ai/client-react react react-dom
# and the transport that carries the call:
pnpm add @pipecat-ai/small-webrtc-transport
```

> **Working from this repo?** The package lives at `sdk/react/` and is part of
> the repo's `pnpm` workspace — build it in place with
> `pnpm --filter @voqalize/client-react build` and reference it as a workspace
> dependency (`"@voqalize/client-react": "workspace:*"`).

## Quick start — `<VoqalAgent/>`

The smallest possible embed. Give it your API root, tenant slug, a **publishable**
(`pk_...`) key, and the agent id. It mints a session, connects, plays the agent's
audio, and shows a minimal status + mic/end bar.

```tsx
import { VoqalAgent } from "@voqalize/client-react";

export function Support() {
  return (
    <VoqalAgent
      apiBase="https://app.voqalize.com/api/v1"
      publishableKey={import.meta.env.VITE_VOQAL_PK}
      agentId="06a2…"
    />
  );
}
```

`pk_` keys are safe to ship in browser code.

### The three required props

- `apiBase` — control-plane root **including the API version**; the SDK appends
  `/sessions.create`. Production: `https://app.voqalize.com/api/v1`.
  Behind a Vite/Next dev proxy, a relative `"/api/v1"` works too.
- `publishableKey` — a `pk_…` key (origin-allowlisted; browser-safe).
- `agentId` — `agent.id` from the MCP `create_agent` / `list_agents`.

**There is no workspace prop.** A `pk_` key belongs to exactly one workspace, so
the server reads it off the key. An earlier version took a `tenantSlug` and
posted to `/{slug}/…`; that route and that prop were both removed on 2026-08-09.

**The voice and the language are not props.** They are declared on the brain, in
Python:

```python
class ConciergeBrain(Brain):
    voice = "omnivoice/gauri"
    language = "hi"          # sets the recognizer AND the TTS voice together
```

or, when the language depends on *this* caller, with one
`session.configure_language("ta", voice="omnivoice/gauri")` in `on_session_start`
(the same call switches language mid-call). The agent record carries no
`stt`/`tts` fields at all, so the brain is the single owner — which matters
because `language` picks both the recognizer *and* the voice-cloning reference
clip, and a half-applied pair errors nowhere: you get the right words in the
wrong speaker's accent, invisible to any transcript-based check.

A `pipeline` prop does still exist on `<VoqalAgent/>` and `useVoqalSession`, for a
page that is genuinely the pipeline's authority — a console auditioning voices, an
A/B harness. A brain that declares or configures a voice overrides it, because the
brain speaks last.

## Custom UI — render prop

Pass a function child to own all the markup. Audio playback is still wired for you.

```tsx
<VoqalAgent apiBase="/api/v1" publishableKey={pk} agentId={id}>
  {({ connectionState, botState, isUserSpeaking, error, disconnect, enableMic, sendMessage }) => (
    <MyPanel state={connectionState} bot={botState} onEnd={disconnect} />
  )}
</VoqalAgent>
```

## Hook — `useVoqalSession`

For full control over layout and providers:

```tsx
import { useVoqalSession } from "@voqalize/client-react";
import { PipecatClientProvider } from "@pipecat-ai/client-react";

function Widget() {
  const session = useVoqalSession({
    apiBase: "/api/v1",
    publishableKey: pk,
    agentId: id,
    // No `pipeline`: the brain declares the voice and the language.
    payload: { surface: "web", user: { name: "Ada" } },
    onServerMessage: (msg) => {
      // Already unwrapped past the `{ data }` quirk.
      if (msg.type === "ui_command") drive(msg);
    },
  });

  return (
    <div>
      <button onClick={session.connect} disabled={session.connectionState !== "idle"}>
        Talk
      </button>
      {session.client && (
        <PipecatClientProvider client={session.client}>
          {/* your voice-ui-kit components, etc. */}
        </PipecatClientProvider>
      )}
    </div>
  );
}
```

## Driving your UI from voice (the two-way message contract)

For agents that change the screen (a cart, a form, a map), brain and browser
exchange JSON with **fixed shapes**.

**Brain → browser.** The brain's `session.dispatch(Action(...))` arrives as a
`ui_command` server message — `{ type, action, action_id }` plus the `args`
**spread onto the top level**. `useUiCommand` subscribes, strips that envelope and
dispatches by name, so a handler sees the args alone:

```tsx
import { useUiCommand } from "@voqalize/client-react";

const { client } = useVoqalSession({ ...props });

useUiCommand(client, {
  add_to_cart: ({ sku, qty }) => addToCart(sku, qty),
});
```

Type it against the brain by declaring the command map — one entry per
`voqalize.sdk.Action` subclass, Python being the source of truth — and passing it
explicitly (an inline handler map gives TypeScript nothing to infer from):

```tsx
interface ShopCommands {
  add_to_cart: { sku: string; qty: number };
}

useUiCommand<ShopCommands>(client, {
  add_to_cart: ({ sku, qty }) => addToCart(sku, qty),     // sku: string, qty: number
});
```

Every handler is optional, and an unknown action is **not** an error — brain and
page ship separately, so it falls through to an optional `"*"` wildcard, else
`console.debug`. Handlers are read through a ref, so an inline object literal never
re-subscribes. `createUiCommandHandlers<T>(...)` pins a map defined away from the
call site; `uiCommandArgs(command)` is the envelope-stripping on its own.
`onServerMessage` remains the raw escape hatch for non-`ui_command` traffic.

**Browser → brain.** Call `sendMessage(type, data)` (from the render-prop /
`useVoqalSession`). The brain receives it as `on_browser_message(session, msg)`, with `msg.type` and
`msg.data`:

```tsx
<VoqalAgent {...props}>
  {(session) => (
    <button onClick={() => session.sendMessage("cart_edited", { removed: "oat-milk" })}>
      Remove
    </button>
  )}
</VoqalAgent>
```

If the brain passed a `callback=` to `.action(...)`, reply with
`sendMessage("action_result", { action_id, status: "ok", result })` and the SDK
routes it back to that callback.

## The microphone

Every session needs one, and the browser will not give you one quietly. Three
things follow from that, and the SDK makes all three visible rather than leaving
you to discover them in a support ticket:

- **The page must be a secure context.** `https://`, or `localhost` in
  development. On plain `http://` a browser does not expose microphones at all,
  and `connect()` fails with `MicrophoneError { problem: "insecure-context" }`.
- **A permission prompt can stay open forever.** `connectionState` becomes
  `"awaiting-microphone"` while it is — render something that tells the user to
  look for the dialog, because "Connecting…" tells them to wait, which is the
  opposite of what they should do. After 30 s the connect fails with
  `problem: "no-response"`.
- **No microphone means no call.** A blocked, missing or already-in-use
  microphone rejects `connect()` rather than joining a call the user cannot
  speak into. The rejection is a `MicrophoneError` whose `message` is written
  for the person in front of the browser; `problem` (`"denied"`,
  `"no-microphone"`, `"in-use"`, …) is what you branch on.

The handle carries the typed error, so a render-prop UI never has to catch
anything — and with `autoConnect` there is no promise to catch:

```tsx
const session = useVoqalSession({ ...props });

if (session.connectionState === "error") {
  // A blocked microphone is the user's to fix and is already worded for them;
  // anything else is ours, and telling them to check their connection is the
  // most useful thing we can say.
  return session.microphoneError ? (
    <MicHelp problem={session.microphoneError.problem}>
      {session.microphoneError.message}
    </MicHelp>
  ) : (
    <GenericFailure onRetry={session.connect} />
  );
}
```

`requestMicrophone()` is exported too, if you want to ask for permission (and
render the outcome) before minting a session at all.

## Minting on your own backend

`publishableKey` puts the decision to start a call in the page. That is right for
a public demo and wrong the moment starting a call depends on something the
browser must not be trusted with — who the caller is, whether they still have
credit, which agent they are entitled to. For that, swap the key for a route on
your own server:

```tsx
<VoqalAgent connectEndpoint="/api/voice/start" connectData={{ orderId }} />
```

The hook `POST`s there with `credentials: "include"`, so the session cookie you
already set is what authorizes it. Your route holds whatever credential it likes
— a secret (`sk_…`) key, an internal service token — mints the session against
the Voqalize API, and returns that response's `connect_params` verbatim:

```json
{
  "webrtc_request_params": {
    "endpoint": "https://signal.prod.voqalize.com/webrtc",
    "headers": { "Authorization": "Bearer <session token>" }
  },
  "session_id": "01J…"
}
```

Nothing else changes: same hook, same handle, same UI. The two paths differ only
in *who* is trusted to say a call may start.

## Low level

Connecting is pipecat's two-step — ask something that holds a credential where
the bot is, then negotiate WebRTC against the address you were given — and both
halves are exported so you can drive a raw `PipecatClient` yourself:

- `createSession({ apiBase, publishableKey, agentId, pipeline?, payload?, record? })` —
  step one against the Voqalize control plane. Returns parameters ready for
  `pc.connect(...)`. Throws `VoqalSessionError` on failure. (`pipeline` is the
  escape hatch above; normal embeds pass `payload` only. `record` is the
  per-call recording decision — `false` always wins, `true` is refused on a
  publishable key and says so on the console.)
- `toConnectParams(body)` — turn any minted session's `connect_params` into those
  same parameters. **Run every server response through this**, including your own
  backend's: pipecat builds each request with `headers.entries()`, so the plain
  object a JSON body gives you throws a `TypeError` at the offer POST rather than
  failing anywhere legible. This is what makes it a `Headers`.

```tsx
import { PipecatClient } from "@pipecat-ai/client-js";
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport";
import { toConnectParams } from "@voqalize/client-react";

const pc = new PipecatClient({ transport: new SmallWebRTCTransport(), enableMic: true });
await pc.connect(toConnectParams(await mintOnMyServer()));
```

## Exports

`VoqalAgent`, `useVoqalSession`, `useUiCommand`, `createUiCommandHandlers`,
`uiCommandArgs`, `createSession`, `toConnectParams`, `VoqalSessionError`,
`MicrophoneError`, `requestMicrophone`, plus their TypeScript types
(`VoqalConnectParams`, `UiCommand`, `UiCommandArgs`, `UiCommandHandlers`,
`MicrophoneProblem`, …).
