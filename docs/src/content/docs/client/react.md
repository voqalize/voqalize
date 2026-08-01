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
      apiBase="https://app.voqalize.com/api/v1"
      tenantSlug="acme"
      publishableKey={import.meta.env.VITE_VOQAL_PK}
      agentId="06a2…"
    />
  );
}
```

:::caution[`apiBase` includes `/api/v1`]
The React SDK's `apiBase` is the **versioned** root
(`https://app.voqalize.com/api/v1`). Point it at the bare host and the browser
session mint fails — this is the most common wiring mistake.
:::

## The hook: `useVoqalSession`

For full control over the UI, use the hook directly:

```ts
const session = useVoqalSession(opts: UseVoqalSessionOptions): VoqalSessionHandle
```

### Options

| Field | Type | Notes |
|---|---|---|
| `apiBase` | `string` (required) | Control-plane root incl. version, e.g. `"/api/v1"` or `"https://app.voqalize.com/api/v1"`. |
| `tenantSlug` | `string` (required) | Your tenant slug. |
| `publishableKey` | `string` (required) | `pk_…` key (origin-allowlisted, browser-safe). |
| `agentId` | `string` (required) | The agent's id. |
| `pipeline?` | `{ stt?, tts? }` | Per-session STT/TTS override; omit for agent defaults. See the [catalog](/docs/reference/catalog/). |
| `payload?` | `Record<string,unknown>` | App payload handed to the brain; arrives as `start.init`. |
| `iceServers?` | `RTCIceServer[]` | Defaults to a public Google STUN server. |
| `autoConnect?` | `boolean` | Default `false` (`<VoqalAgent/>` sets it `true`). |
| `onServerMessage?` | `(msg) => void` | Every RTVI server message, unwrapped — the raw escape hatch. For UI commands prefer [`useUiCommand`](#typed-ui-commands-useuicommand). |

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
   publishable key as a bearer token. The body is `{ agent_id, payload }`, where the
   outer `payload` **wraps both** the `pipeline` override and your app `payload`:
   `{ agent_id, payload: { pipeline?, payload? } }` — so your app data nests one level
   in, under `payload.payload`. The response carries the signaling URL and a session
   token. (A missing
   `connection_details.signaling_url` in the response means no worker is running
   for that agent — a `VoqalSessionError` is thrown with that hint.)
2. **Connect** — it builds a `VoqalWebRTCTransport`, wraps it in a `PipecatClient`
   (mic on, camera off), and connects to the runtime's signaling endpoint. Media is
   direct WebRTC; RTVI control messages ride a data channel.

## The two-way UI contract

For agents that drive the screen (see
[Handling a conversation](/docs/brain/conversation/)):

- **Brain → browser.** The brain's `interaction.action(name, { ...args })` arrives
  as a server message `{ type: "ui_command", action, action_id, ...args }` — the
  args are spread onto the top level. Dispatch it with `useUiCommand`, below.
- **Browser → brain.** `session.sendMessage(type, data)` reaches the brain's
  `on_client_message(session, ClientMessage(type=type, data=data))`. Reply to a UI
  command's outcome with `sendMessage("action_outcome", { action_id, status, result })`.

## Typed UI commands: `useUiCommand`

Handling commands by hand is the same three lines in every app — subscribe to
server messages, filter on `type`, `switch` on `action` — followed by re-coercing
every argument out of an untyped bag. The hook is those lines, once:

```tsx
import { useUiCommand } from "@voqalize/client-react";

const { client } = useVoqalSession({ /* … */ });

useUiCommand(client, {
  open_itinerary: ({ name }) => open(name),
  select_flight: ({ leg_id, option_id }) => choose(leg_id, option_id),
});
```

```ts
useUiCommand<T>(client: PipecatClient | null, handlers: UiCommandHandlers<T>): void
```

A handler receives **only the arguments** — `type`, `action` and `action_id` are
stripped, since they're the transport's — plus the whole command as a second
argument when you need the `action_id` to reply with an outcome. `client` may be
`null` before connect; the hook subscribes once one exists. Handlers are read
through a ref, so an inline object literal is fine: re-rendering never
re-subscribes.

An action with no handler is **not** an error — the brain and the page ship
separately, and a new command reaching an old build must not break it. It goes to
an optional `"*"` wildcard, else to `console.debug`.

### Typing it against the brain

Declare the command map — wire name → argument shape — and pass it as the type
argument. Each handler's parameter is then that action's args, so a field renamed
in Python is a compile error instead of an `undefined` that reaches the screen:

```ts
// Shapes mirror the brain's `voqalize.sdk.Action` subclasses — Python is the
// source of truth.
export interface TravelCommands {
  open_itinerary: { name: string };
  select_flight: { leg_id: string; option_id: string };
}

useUiCommand<TravelCommands>(client, {
  open_itinerary: ({ name }) => open(name),               // name: string
  select_flight: ({ leg_id, option_id }) => pick(leg_id, option_id),
});
```

Write the type argument explicitly — an inline handler map gives TypeScript
nothing to infer it from. The map is checked both ways: an action you didn't
declare is rejected, and every declared handler is optional (a page may handle a
subset). If the map lives away from the call site, `createUiCommandHandlers<T>(…)`
pins it there instead:

```ts
const handlers = createUiCommandHandlers<TravelCommands>({ /* … */ });
useUiCommand(client, handlers);
```

`uiCommandArgs(command)` is the same envelope-stripping used internally, exported
for the rare place you hold a whole `UiCommand` and want just its args.

The `travel` demo (`demos/travel`) runs this end to end: `Action` subclasses in
`backend/brain.py`, the mirrored `TravelCommands` in `frontend/src/uiCommands.ts`.

## Exports

`VoqalAgent`, `useVoqalSession`, `useUiCommand`, `createUiCommandHandlers`,
`uiCommandArgs`, `createSession`, `VoqalWebRTCTransport`, `VoqalSessionError`,
plus the TypeScript types (`UiCommand`, `UiCommandArgs`, `UiCommandHandlers`,
`UseVoqalSessionOptions`, `VoqalSessionHandle`, `VoqalConnectionState`,
`VoqalBotState`, `VoqalPipelineConfig`, and more).

## Next

- **[Handling a conversation](/docs/brain/conversation/)** — the brain side of the
  UI contract.
- **[Voice & language catalog](/docs/reference/catalog/)** — `pipeline` values.
