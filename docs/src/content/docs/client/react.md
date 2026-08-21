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

Note what is *not* in that embed: the workspace, the voice, and the language.

There is no tenant prop — a `pk_` key belongs to exactly one workspace, so the
control plane reads it off the key; naming it again in the call would be a second
answer to a question the credential has already answered, and the only interesting
case is the two disagreeing. (MCP tools do still take a `tenant`, because stateless
RPC holds no credential that names one.)

Nor is the voice or the language. Those belong to the
brain — `voice` / `language` class attributes on your `Brain`, or
`session.configure_language(...)` when they depend on *this* caller — and the
agent record has no `stt`/`tts` fields either. One owner, because `language`
picks both the recognizer and the voice-cloning reference clip, and a page that
sets only half of that pair fails silently in the right words with the wrong
accent. See the [voice & language catalog](/docs/reference/catalog/).

## The hook: `useVoqalSession`

For full control over the UI, use the hook directly:

```ts
const session = useVoqalSession(opts: UseVoqalSessionOptions): VoqalSessionHandle
```

### Options

| Field | Type | Notes |
|---|---|---|
| `apiBase` | `string` (required) | Control-plane root incl. version, e.g. `"/api/v1"` or `"https://app.voqalize.com/api/v1"`. |
| `publishableKey` | `string` (required) | `pk_…` key (origin-allowlisted, browser-safe). |
| `agentId` | `string` (required) | The agent's id. |
| `pipeline?` | `{ stt?, tts? }` | **Usually omit.** Voice and language are declared on the brain, not here — see the [catalog](/docs/reference/catalog/). Kept for a page that is genuinely the pipeline's authority (a voice-auditioning console, an A/B harness); a brain that declares or configures a voice overrides it. |
| `payload?` | `Record<string,unknown>` | App payload handed to the brain; arrives as `start.init`. |
| `iceServers?` | `RTCIceServer[]` | Defaults to a public Google STUN server. |
| `autoConnect?` | `boolean` | Default `false` (`<VoqalAgent/>` sets it `true`). |
| `onServerMessage?` | `(msg) => void` | Every RTVI server message, unwrapped — the raw escape hatch. For UI commands prefer [`useUiCommand`](#typed-ui-commands-useuicommand). |

### Return value

| Field | Type | Meaning |
|---|---|---|
| `connectionState` | `"idle" \| "connecting" \| "awaiting-microphone" \| "connected" \| "disconnected" \| "error"` | Transport state. `awaiting-microphone` is [its own state on purpose](#the-microphone). |
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

1. **Mint** — one `POST {apiBase}/sessions.create` with the publishable key as a
   bearer token. The body is `{ agent_id, agent_input }`, where `agent_input`
   **wraps both** the `pipeline` override and your app `payload`:
   `{ agent_id, agent_input: { pipeline?, payload? } }` — so your app data nests
   one level in, under `agent_input.payload`. The response carries
   `connection_details.connect_params` — the runtime node's offer endpoint and
   the session token to present on it. (A missing `connect_params` means no
   worker is running for that agent — a `VoqalSessionError` is thrown with that
   hint.)

   `agent_input` goes two places at once: it is signed into the session token,
   which is how the runtime and then the brain receive it, and it is **stored on
   the session**, so you can still answer "what did the page send?" after the
   token has expired. Stored means readable by anyone who can read the session —
   send identifiers, not personal data.
2. **Connect** — it builds pipecat's own `SmallWebRTCTransport`, wraps it in a
   `PipecatClient` (mic on, camera off), and POSTs the SDP offer to that endpoint.
   Media is direct WebRTC; RTVI control messages ride a data channel. There is no
   transport of ours in the path — `toConnectParams` is the whole adaptation.

## The microphone

Every session needs one, and the browser will not hand one over quietly. The SDK
makes each way that can fail visible, rather than leaving you to find it in a
support ticket.

**The page must be a secure context** — `https://`, or `localhost` while you
develop. On plain `http://` the browser does not expose microphones at all, and
`connect()` fails immediately.

**A permission prompt can stay open forever**, and a caller who missed the
dialog has no reason to think the browser is waiting on them. While it is open
`connectionState` is `"awaiting-microphone"` — its own state rather than a
flavour of `connecting`, because the two ask the user for opposite things:
`connecting` means wait, this one means *go look for the dialog*. Render
something that says so. If nothing comes back within 30 s the connect fails.

**No microphone means no call.** Blocked, missing, or already held by another
app — `connect()` rejects rather than joining a call the user cannot speak into.
Before this was true, a denied prompt produced the worst outcome available: the
call connected with no audio track, the agent greeted, the caller talked, and
nothing left the page while the UI said "Listening…".

The rejection is a `MicrophoneError`. Its `message` is written for the person in
front of the browser and is what `session.error` already carries; `problem` is
what you branch on:

| `problem` | What happened |
|---|---|
| `"denied"` | The user (or a policy) blocked microphone access. |
| `"no-response"` | The prompt was never answered. |
| `"no-microphone"` | No input device exists. |
| `"in-use"` | Another application holds the device. |
| `"insecure-context"` | The page is not `https://` or `localhost`. |
| `"unknown"` | Anything else the browser reported. |

```tsx
import { MicrophoneError } from "@voqalize/client-react";

try {
  await session.connect();
} catch (err) {
  if (err instanceof MicrophoneError && err.problem === "denied") {
    showHowToUnblockMic();
  }
}
```

`requestMicrophone()` is exported on its own, for asking permission — and
rendering the outcome — before you mint a session at all.

## The two-way UI contract

For agents that drive the screen (see
[Handling a conversation](/docs/brain/conversation/)):

- **Brain → browser.** The brain's `interaction.action(name, { ...args })` arrives
  as a server message `{ type: "ui_command", action, action_id, ...args }` — the
  args are spread onto the top level. Dispatch it with `useUiCommand`, below.
- **Browser → brain.** `session.sendMessage(type, data)` reaches the brain's
  `on_client_message(session, ClientMessage(type=type, data=data))`. Reply to a UI
  command's outcome with `sendMessage("action_result", { action_id, status, result })`.

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
`uiCommandArgs`, `createSession`, `toConnectParams`, `VoqalSessionError`,
`MicrophoneError`, `requestMicrophone`, `AmbientPresence`, `PreCallGate`, plus the
TypeScript types (`UiCommand`, `UiCommandArgs`, `UiCommandHandlers`,
`UseVoqalSessionOptions`, `VoqalSessionHandle`, `VoqalConnectionState`,
`VoqalBotState`, `MicrophoneProblem`, `VoqalConnectParams`,
`VoqalPipelineConfig`, and more).

## Next

- **[Handling a conversation](/docs/brain/conversation/)** — the brain side of the
  UI contract.
- **[Voice & language catalog](/docs/reference/catalog/)** — the voices and languages,
  and why the brain is the one place that sets them.
