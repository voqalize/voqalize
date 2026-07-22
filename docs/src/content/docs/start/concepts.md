---
title: Core concepts
description: Sessions, interactions, inferences, the brain_url, and the Vql frames that connect the voice runtime to your brain.
---

A handful of ideas explain the whole platform. Read this once and the SDK reads
itself.

## The brain and the voice runtime

Two processes make one voice agent:

- **The voice runtime** (ours, managed) answers the call, transcribes speech,
  speaks replies, and handles interruptions.
- **The brain** (yours) receives text and streams text back.

They connect over **one WebSocket per session**, opened when a call starts and
torn down when it ends. The connection *is* the liveness signal — there is no
pool to manage.

## The `brain_url`

An agent's brain is a single WebSocket URL: `deployment.brain_url`. When a call
starts, the runtime dials:

```
{brain_url}/s/{session_id}
```

Where that URL points is the only thing that varies, and neither the runtime nor
the control plane interprets it:

- **Your own inbound server** — you expose one authenticated WebSocket route. This
  is the primary path. See [Inbound server](/docs/deploy/inbound/).
- **A Cortex relay** — for brains that can't accept inbound connections
  (serverless, laptops behind NAT, egress-only networks): your brain dials *out*
  to Cortex. See [Cortex relay](/docs/deploy/cortex/).

Same brain code either way. You only choose who dials whom. (An empty `brain_url`
falls back to a hosted `welcome` brain, so a bare agent still greets.)

## Session → interaction → inference

Three nested units of conversation, each with a stable identity:

- **Session** — one call. Identified by `session_id`. Starts with a `VqlStart`
  frame carrying an opaque `payload` (your per-call init data) and ends when the
  call does.
- **Interaction** — one committed user turn and the brain's whole response to it.
  Identified by `interaction_id` (a runtime-minted, session-monotonic number).
  The sentinel `interaction_id = 0` is reserved for **agent-initiated** speech —
  the greeting.
- **Inference** — one call to your model. Identified by `inference_id`
  (brain-minted, per-interaction). One interaction can contain **many** inferences
  (e.g. speak a line → call a tool → speak the result).

The composite `(interaction_id, inference_id)` uniquely names any piece of the
bot's output. In the SDK these map to the `Session`, `Interaction`, and
`Inference` objects your callbacks receive.

## Speaking: the inference bracket

Your brain never sends raw text frames. It opens an **inference bracket** and
calls `speak`:

```python
async with interaction.inference() as inf:   # one bracket == one LLM call
    await inf.speak("Let me check that for you.")
```

Entering the bracket tells the runtime a bot response is starting; each `speak`
streams a chunk of text (the runtime does TTS and word timing); exiting closes the
response. Open a fresh bracket per model call — never wrap a multi-call run in one.

Agent-initiated speech (the greeting) uses `session.inference()` instead, which
runs under the `interaction_id = 0` sentinel.

## The `Vql*` frames

The two sides speak a small set of framed messages. As a brain author you mostly
work through SDK objects, but it helps to know the shape:

| You receive | You send |
|---|---|
| `VqlStart` (session begins, with payload) | `VqlLLMFullResponseStart` / `VqlLLMText` / `VqlLLMFullResponseEnd` (a spoken response) |
| `VqlUserText` (a committed user turn) | `VqlFunctionCallsStarted` / `…Result` (tool calls, for UI + transcript) |
| `VqlInferenceFinalized` (what the user *actually heard*) | `RTVIServerMessage` (a UI command to the browser) |
| `RTVIClientMessage` (a browser app event) | `STTUpdateSettings` / `TTSUpdateSettings` (mid-call reconfigure) |

Full field-level detail is in the [Voice protocol reference](/docs/reference/voice-protocol/).

### Heard text vs. spoken text

An important subtlety: what your brain *says* and what the user *hears* can differ,
because the user can interrupt (barge-in) mid-sentence. The runtime tells you the
truth after the fact via `VqlInferenceFinalized` — the `heard` text, truncated at
the interruption point. The SDK commits **heard** text to the conversation
transcript, so your model context always reflects reality, not intent.

## Authentication

Every brain connection carries a short-lived RS256 JWT the runtime signs. Your
brain verifies it against Voqalize's public key (the SDK does this for you). The
claims:

- `iss = "pygato"` — the runtime.
- `aud = "brain"` — a protocol constant shared by all brain connections.
- `sub = session_id` — scopes the token to exactly one session.
- `tenant_id` / `agent_id` — informational; your brain can use them to decide
  whether it serves that agent.

## Next

- **[Build a brain: Python](/docs/brain/python/)** — the full callback surface.
- **[Handling a conversation](/docs/brain/conversation/)** — streaming, tools, UI.
- **[Voice protocol reference](/docs/reference/voice-protocol/)** — every frame.
