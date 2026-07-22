---
title: React client SDK
description: Embed a live voice agent in a browser app — mint a session, connect the WebRTC transport, drive and read your UI.
---

`@voqalize/client-react` puts a voice agent in a web app. It mints a session
against the control plane, opens the WebRTC transport to the voice runtime, plays
the agent's audio, and exposes the two-way UI channel for screen-driving agents.

:::note[Pre-release]
Not yet on npm. Install from a clone of
[`voqalize/voqalize`](https://github.com/voqalize/voqalize) via the pnpm workspace.
Peer deps: `@pipecat-ai/client-js`, `@pipecat-ai/client-react`, `react`,
`react-dom`.
:::

## The quick way: `<VoqalAgent/>`

The smallest real embed is one component. It auto-connects, plays bot audio, and
renders a status + mute/end bar:

```tsx
import { VoqalAgent } from "@voqalize/client-react";

export function Support() {
  return (
    <VoqalAgent
      apiBase="https://api.voqalize.com/api/v1"
      tenantSlug="acme"
      publishableKey={import.meta.env.VITE_VOQAL_PK}
      agentId="06a2…"
    />
  );
}
```

:::caution[`apiBase` includes `/api/v1`]
The React SDK's `apiBase` is the **versioned** root
(`https://api.voqalize.com/api/v1`), unlike the MCP server's `VOQALIZE_API_BASE`,
which is the bare host. Getting these confused is the most common wiring mistake.
:::

## The hook: `useVoqalSession`

For full control over the UI, use the hook directly:

```ts
const session = useVoqalSession(opts: UseVoqalSessionOptions): VoqalSessionHandle
```

### Options

| Field | Type | Notes |
|---|---|---|
| `apiBase` | `string` (required) | Control-plane root incl. version, e.g. `"/api/v1"` or `"https://api.voqalize.com/api/v1"`. |
| `tenantSlug` | `string` (required) | Your tenant slug. |
| `publishableKey` | `string` (required) | `pk_…` key (origin-allowlisted, browser-safe). |
| `agentId` | `string` (required) | The agent's id. |
| `pipeline?` | `{ stt?, tts? }` | Per-session STT/TTS override; omit for agent defaults. See the [catalog](/docs/reference/catalog/). |
| `payload?` | `Record<string,unknown>` | App payload handed to the brain; arrives as `start.init`. |
| `iceServers?` | `RTCIceServer[]` | Defaults to a public Google STUN server. |
| `autoConnect?` | `boolean` | Default `false` (`<VoqalAgent/>` sets it `true`). |
| `onServerMessage?` | `(msg) => void` | Each RTVI server message, unwrapped. |

### Return value

| Field | Type | Meaning |
|---|---|---|
| `connectionState` | `"idle" \| "connecting" \| "connected" \| "disconnected" \| "error"` | Transport state. |
| `botState` | `"idle" \| "listening" \| "thinking" \| "speaking"` | Derived from runtime events. |
| `isUserSpeaking` | `boolean` | Local voice activity. |
| `error` | `string \| null` | Last error. |
| `connect` | `() => Promise<void>` | Mint + connect (no-op if active). |
| `disconnect` | `() => Promise<void>` | Tear down (idempotent). |
| `enableMic` | `(enable: boolean) => void` | Mute / unmute the mic. |
| `sendMessage` | `(type, data?) => void` | Browser → brain app event. |
| `client` | `PipecatClient \| null` | The live client, or `null`. |

### Example

```tsx
function CallButton() {
  const s = useVoqalSession({
    apiBase: "/api/v1",
    tenantSlug: "acme",
    publishableKey: import.meta.env.VITE_VOQAL_PK,
    agentId: "06a2…",
    onServerMessage: (msg) => {
      if (msg.type === "ui_command") handleUiCommand(msg);
    },
  });

  return s.connectionState === "connected" ? (
    <button onClick={s.disconnect}>End · {s.botState}</button>
  ) : (
    <button onClick={s.connect}>Talk</button>
  );
}
```

## How connecting works

The hook runs a two-step flow:

1. **Mint** — one `POST {apiBase}/{tenantSlug}/sessions.create_and_start` with the
   publishable key as a bearer token and `{ agent_id, payload }` as the body. The
   response carries the signaling URL and a session token. (A missing
   `connection_details.signaling_url` in the response means no worker is running
   for that agent — a `VoqalSessionError` is thrown with that hint.)
2. **Connect** — it builds a `VoqalWebRTCTransport`, wraps it in a `PipecatClient`
   (mic on, camera off), and connects to the runtime's signaling endpoint. Media is
   direct WebRTC; RTVI control messages ride a data channel.

## The two-way UI contract

For agents that drive the screen (see
[Handling a conversation](/docs/brain/conversation/)):

- **Brain → browser.** The brain's `interaction.action(name, { ...args })` arrives
  on `onServerMessage` as `{ type: "ui_command", action, action_id, ...args }` —
  the args are spread onto the top level.
- **Browser → brain.** `session.sendMessage(type, data)` reaches the brain's
  `on_app_event(session, AppEvent(name=type, data=data))`. Reply to a UI command's
  outcome with `sendMessage("action_outcome", { action_id, status, result })`.

## Exports

`VoqalAgent`, `useVoqalSession`, `createSession`, `VoqalWebRTCTransport`,
`VoqalSessionError`, plus the TypeScript types (`UseVoqalSessionOptions`,
`VoqalSessionHandle`, `VoqalConnectionState`, `VoqalBotState`,
`VoqalPipelineConfig`, and more).

## Next

- **[Handling a conversation](/docs/brain/conversation/)** — the brain side of the
  UI contract.
- **[Voice & language catalog](/docs/reference/catalog/)** — `pipeline` values.
