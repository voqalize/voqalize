# @voqalize/client-react

Embed a [Voqalize](https://voqalize.com) voice agent in a React app. Ships the
browser WebRTC transport, a one-call session bootstrap, and a hook + component
that manage the whole voice-session lifecycle.

You bring the brain, we bring the voice.

## Install

```bash
pnpm add @voqalize/client-react
# peers you already have in a React app:
pnpm add @pipecat-ai/client-js @pipecat-ai/client-react react react-dom
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
  `/sessions.create_and_start`. Production: `https://app.voqalize.com/api/v1`.
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

**Brain → browser.** The brain's `interaction.action(name, {...args})` arrives as a
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
`useVoqalSession`). The brain receives it as `on_client_message(message.type, message.data)`:

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
`sendMessage("action_outcome", { action_id, status: "done", result })` and the SDK
routes it back to that callback.

## Low level

- `createSession({ apiBase, publishableKey, agentId, pipeline?, payload? })`
  → `{ signalingUrl, token }`. Throws `VoqalSessionError` on failure. (`pipeline` is
  the escape hatch above; normal embeds pass `payload` only.)
- `VoqalWebRTCTransport` — the pipecat `Transport`. Use with a raw `PipecatClient`
  and `pc.connect({ connection_url, token })` for total control.

## Exports

`VoqalAgent`, `useVoqalSession`, `useUiCommand`, `createUiCommandHandlers`,
`uiCommandArgs`, `createSession`, `VoqalWebRTCTransport`, `VoqalSessionError`,
plus their TypeScript types (`UiCommand`, `UiCommandArgs`, `UiCommandHandlers`, …).
