---
title: Voice protocol (Vql frames)
description: The Vql* frame set, the wire framing, ack semantics, and the greeting handshake — the contract both sides speak.
---

:::note
This is the reference for the `Vql*` wire **as shipped today** — exactly the
frames a brain receives now. (Voqalize maintains a separate, internal
forward-looking protocol design; this page always describes the currently
implemented contract.)
:::

The voice runtime and your brain exchange a small set of `Vql*` frames over one
WebSocket per session. The SDKs wrap these as objects, so most brains never touch
the wire directly — but the frame set *is* the contract, and this is the reference.

The canonical definition is [`proto/voqalize/frames/frames.proto`](https://github.com/voqalize/voqalize/tree/main/proto)
(package `voqalize.frames`); the SDK dataclasses mirror it exactly.

## Identity keys

Two numeric IDs thread through almost every frame:

- **`interaction_id`** (`uint64`) — runtime-minted, session-monotonic. One
  committed user stimulus plus the brain's whole response. `0` is the sentinel for
  agent-initiated speech (the greeting); real user interactions start at 1.
- **`inference_id`** (`uint64`) — brain-minted, per-interaction. One model call.
  One interaction contains N inferences.

`(interaction_id, inference_id)` uniquely names any piece of bot output. Both are
always numeric on the wire — never a dotted string.

## The application frames

"Direction" below is the logical sender. Fields marked *(JSON)* travel as a JSON
string on the wire and arrive as a dict in the SDK.

| Frame | Direction | Key fields | Meaning |
|---|---|---|---|
| `VqlStart` | runtime → brain | `session_id`, `agent_id`, `payload` *(JSON)*, `audio_in_sample_rate`, `audio_out_sample_rate` | First frame of a session. `payload` is your opaque init data. |
| `VqlUserText` | runtime → brain | `interaction_id`, `text` | A committed user utterance; opens an interaction. |
| `VqlInterruption` | both | *(none)* | Barge-in / drain barrier. Correlation lives on data frames, not here. |
| `VqlInferenceFinalized` | runtime → brain | `interaction_id`, `inference_id`, `heard_text`, `interrupted`, `reason` | The text the user **actually heard** for one inference (post-TTS, truncated on barge-in). |
| `VqlLLMFullResponseStart` | brain → runtime | `interaction_id`, `inference_id` | Start of one bot inference. |
| `VqlLLMText` | brain → runtime | `interaction_id`, `inference_id`, `text` | One chunk of bot text; many per inference. |
| `VqlLLMFullResponseEnd` | brain → runtime | `interaction_id`, `inference_id` | End of one bot inference. |
| `VqlFunctionCallsStarted` | brain → runtime | `…`, `tool_call_id`, `function_name`, `arguments` *(JSON)* | The model decided to call a tool. |
| `VqlFunctionCallInProgress` | brain → runtime | same | Mid-flight tool call (drives a UI spinner). |
| `VqlFunctionCallResult` | brain → runtime | `…`, `tool_call_id`, `function_name`, `result` *(JSON)* | Tool result. |
| `VqlInteractionCompleted` | brain → runtime | `interaction_id` | Brain is done with the whole interaction. **Barge-in skips this.** Idempotent per interaction. |

### `FinalizeReason`

`VqlInferenceFinalized.reason` is one of `COMPLETED` or `USER_BARGE_IN`.
`interrupted` is `true` exactly when `reason == USER_BARGE_IN`.

## Lifecycle and transport frames

| Frame | Meaning |
|---|---|
| `End` | Graceful end-of-session. Rides the **normal** lane, so teardown happens only after queued data drains. |
| `Cancel` | Abrupt cancel; carries a `reason`. |
| `Error` | `error` string + `fatal` bool. The SDK emits this on normal-lane overflow as a drop-newest congestion signal; it is never fatal to the session. |

## Pipecat-native wrappers

Four frames carry JSON-encoded payloads that reconstruct richer message types.
These are how UI commands and mid-call reconfiguration travel — and what the SDK
helpers emit under the hood:

| Frame | Direction | Emitted by | Purpose |
|---|---|---|---|
| `RTVIServerMessage` | brain → browser | `session.action` / `interaction.action` | A UI command: `{ type:"ui_command", action, action_id, ... }`. |
| `RTVIClientMessage` | browser → brain | client `sendMessage` | A browser app event; surfaces as `on_app_event`. |
| `TTSUpdateSettings` | brain → runtime | `session.configure_tts` | Mid-session TTS reconfigure (next inference). |
| `STTUpdateSettings` | brain → runtime | `session.configure_stt` | Mid-session STT reconfigure (live). |

There is no `configure_tts` / `configure_stt` *frame* — those are SDK methods that
emit the update-settings frames above.

## Wire framing

Messages are **binary** WebSocket frames only (a text frame is a protocol error).
Layout:

- **Single-session leg** (inbound / the `/s/{session_id}` route):
  `[1-byte direction][Envelope protobuf bytes]`.
- **Multiplexed leg** (the Cortex `/agent` connection):
  `[16-byte session_id][1-byte direction][Envelope protobuf bytes]` — Cortex adds
  the 16-byte prefix.

The **direction byte** is `DOWNSTREAM = 1` (toward the brain / bot output) or
`UPSTREAM = 2` (back toward the runtime), matching pipecat's values. The `Envelope`
holds the frame in a `body` oneof plus a top-level `request_id` (`uint64`).

## Ack / request_id gating

The runtime tags outbound **data** frames with a monotonically increasing
`request_id` (starting at 1). This enforces strict in-order dispatch across the
round-trip:

- `request_id == 0` (or absent) means **no ack expected**.
- The receiver never interprets the value — it only echoes it back.
- **Any frame received with `request_id > 0` must be acked.** After your
  `process_frame` returns, the SDK sends an `Ack` envelope with `ack_id ==
  request_id`. The sender resolves the pending frame and releases the next one.
- Lifecycle/system frames (`VqlStart`, `Interruption`, `End`, `Cancel`) carry no
  `request_id` and are not ack-gated. Acks themselves are wire-level and never
  surface as frames.

The SDKs handle acking for you. You only care about this if you implement the wire
yourself.

## The greeting handshake

On session start:

1. The runtime sends **`VqlStart`** (first frame) with `session_id`, `agent_id`,
   and `payload`.
2. The SDK calls your `on_session_start(session, start)`, where `start.init` is the
   payload.
3. To greet, you open an agent-initiated inference — `session.inference()` — which
   runs under the `interaction_id = 0` sentinel. Entering emits
   `VqlLLMFullResponseStart(interaction_id=0, inference_id=n)`; each `speak` emits
   `VqlLLMText`; exiting emits `VqlLLMFullResponseEnd`. (No `VqlInteractionCompleted`
   — that's for user-opened interactions.)

```python
class Greeter(Brain):
    async def on_session_start(self, session, start):
        async with session.inference() as inf:
            await inf.speak("Hi! How can I help?")
```

## Connection and auth

The runtime dials `{brain_url}/s/{session_id}`, one WebSocket per session. It
presents a short-lived RS256 JWT (as a bare token or `Authorization: Bearer
<jwt>`), verified against Voqalize's public key. Required claims: `iss="pygato"`,
`aud="brain"`, `sub == session_id`, and `exp`; `tenant_id` / `agent_id` are
informational. See [Core concepts → Authentication](/docs/start/concepts/#authentication).

Close-code contract: **4000** = no agent → permanent, never retry; **4001** = agent
gone → transient, reconnect with backoff; anything else → transient; **1000** from
the runtime → no reconnect.
