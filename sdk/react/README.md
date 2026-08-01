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
      tenantSlug="acme"
      publishableKey={import.meta.env.VITE_VOQAL_PK}
      agentId="06a2…"
    />
  );
}
```

`pk_` keys are safe to ship in browser code.

### The four required props

- `apiBase` — control-plane root **including the API version**; the SDK appends
  `/{tenantSlug}/sessions.create_and_start`. Production: `https://app.voqalize.com/api/v1`.
  Behind a Vite/Next dev proxy, a relative `"/api/v1"` works too.
- `tenantSlug` — your tenant slug (shown by the MCP `whoami` / `list_tenants` tools).
- `publishableKey` — a `pk_…` key (origin-allowlisted; browser-safe).
- `agentId` — `agent.id` from the MCP `create_agent` / `list_agents`.

**Choosing the voice / STT model (optional).** Both `<VoqalAgent/>` and
`useVoqalSession` accept an optional `pipeline` prop — `<VoqalAgent {...props}
pipeline={{ tts: { voice: "omnivoice/gauri" }, stt: { model: "vql-stt", language: "en" } }} />`.
It selects STT/TTS **for this session**; omit it and the agent's server-side
defaults apply. (There's no need to set anything on the agent for a first run —
a bare agent has working defaults.)

## Custom UI — render prop

Pass a function child to own all the markup. Audio playback is still wired for you.

```tsx
<VoqalAgent apiBase="/api/v1" tenantSlug="acme" publishableKey={pk} agentId={id}>
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
    tenantSlug: "acme",
    publishableKey: pk,
    agentId: id,
    pipeline: { stt: { model: "vql-stt", language: "en" }, tts: { voice: "omnivoice/gauri" } },
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

**Brain → browser.** The brain's `interaction.action(name, {...args})` arrives on
`onServerMessage` — the `args` are **spread onto the top level**:

```tsx
<VoqalAgent {...props}
  onServerMessage={(msg) => {
    if (msg.type !== "ui_command") return;         // always this envelope
    if (msg.action === "add_to_cart") {
      // { type:"ui_command", action:"add_to_cart", action_id:7, sku:"oat-milk", qty:2 }
      addToCart(String(msg.sku), Number(msg.qty));
    }
  }}
/>
```

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

- `createSession({ apiBase, tenantSlug, publishableKey, agentId, pipeline?, payload? })`
  → `{ signalingUrl, token }`. Throws `VoqalSessionError` on failure.
- `VoqalWebRTCTransport` — the pipecat `Transport`. Use with a raw `PipecatClient`
  and `pc.connect({ connection_url, token })` for total control.

## Exports

`VoqalAgent`, `useVoqalSession`, `createSession`, `VoqalWebRTCTransport`,
`VoqalSessionError`, plus their TypeScript types.
