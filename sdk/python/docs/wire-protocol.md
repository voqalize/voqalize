# Wire Protocol

The frame vocabulary and envelope shapes carried over the Cortex WebSocket. The Python representation lives in [`wire/frames.py`](../src/voqalize/sdk/wire/frames.py); the protobuf encoding in [`wire/_frames_pb2.py`](../src/voqalize/sdk/wire/_frames_pb2.py); the serializer in [`wire/serializer.py`](../src/voqalize/sdk/wire/serializer.py). All three move together — when changing the vocabulary, update the protobuf, regenerate (or hand-mirror) the stubs, and add the class to `VQL_FRAME_CLASSES`.

## Envelope shapes

Two endpoints, two envelopes, one connection class ([`wire/transport.py`](../src/voqalize/sdk/wire/transport.py)):

| Endpoint | Used by | Per-message format |
|---|---|---|
| `/s/{session_id}` | pygato (one connection per session) | `[1-byte direction][protobuf payload]` |
| `/agent` | agent SDK (one connection multiplexes N sessions) | `[16-byte session_id][1-byte direction][protobuf payload]` |

The 16-byte session prefix is raw UUID bytes — no separator, no length, fixed offset. Matches [`cortex/internal/protocol/protocol.go`](../../cortex/internal/protocol/protocol.go) `SessionIDLen`. The 1-byte direction is `0 = DOWNSTREAM`, `1 = UPSTREAM` (matches pipecat `FrameDirection`).

## Frame vocabulary

All `Vql*` classes are pipecat-frame subclasses ([decisions §2](decisions.md)). Two keys identify everything (see [docs/voice-protocol.md](../../../docs/voice-protocol.md)): `interaction_id` (Voice-minted, session-monotonic `uint64`; one committed user stimulus + the brain's full response) and `inference_id` (brain-minted, per-interaction `uint64`; one LLM call). `(interaction_id, inference_id)` is the composite key — two typed fields, never a dotted string on the wire. One interaction → N inferences.

**Lifecycle:**

- `VqlStartFrame` — first frame on the wire for a session. Carries `session_id`, `agent_id`, and an opaque `payload` dict that customer agents read on session boot. Subclass of pipecat `StartFrame` (a `SystemFrame`).

**User stimulus (DOWNSTREAM into the customer):**

- `VqlUserTextFrame` — committed user utterance opening an interaction. Fields: `interaction_id`, `text`.
- native `InterruptionFrame` (pipecat, not a `Vql*` class) — user interrupted. Field-less; rides the system-priority lane, bypasses queued data frames, cancels the in-flight `process_frame`. The customer (or the pipeline's `broadcast_interruption`) echoes an `InterruptionFrame` back UPSTREAM — pygato's drain barrier. Correlation lives on `inference_id`, not on the interrupt.

**Bot response (UPSTREAM from the customer; the brain stamps both ids):**

- `VqlLLMFullResponseStartFrame` — start of one inference. Fields: `interaction_id`, `inference_id`. Subclass of pipecat `LLMFullResponseStartFrame`.
- `VqlLLMTextFrame` — one chunk of LLM text. Many per inference. Subclass of pipecat `LLMTextFrame`.
- `VqlLLMFullResponseEndFrame` — end of one inference. Subclass of pipecat `LLMFullResponseEndFrame`.

**Function/tool calls** (each carries `interaction_id` + `inference_id`):

- `VqlFunctionCallsStartedFrame` — model decided to call a tool. Arguments JSON-encoded on wire.
- `VqlFunctionCallInProgressFrame` — mid-flight announcement (UI spinner).
- `VqlFunctionCallResultFrame` — tool result. JSON-encoded on wire. Used in both directions: customer emits results for tools they own; pygato/browser emits results for browser-side tools.

**Inference boundary (UPSTREAM, per inference):**

- `VqlInferenceFinalizedFrame` — emitted by pygato per inference (on playout end or barge-in). Fields: `interaction_id`, `inference_id`, `heard_text` (what the user actually heard for *that one inference*, post-TTS truncation — never a cross-inference concatenation), `interrupted: bool`, `reason` (`FinalizeReason` ∈ {COMPLETED, USER_BARGE_IN}). Acked.

## Ack envelope

Every wire-vocab data frame carries `request_id > 0`. The receiver emits an `Ack(request_id)` envelope once the frame has been fully consumed (downstream pushes complete). The mechanics:

- The SDK runner queues an internal `_AckSentinel(ack_id=request_id)` behind every inbound data frame ([`_session_buffer.py`](../src/voqalize/sdk/_session_buffer.py)).
- Pipecat's `__process_queue` is FIFO single-worker — the sentinel reaches `_SessionOutbound` only after the customer's `process_frame` returns.
- `_SessionOutbound` hands the sentinel to the writer, which serializes it as an `Ack` envelope.

Acks are bidirectional: UPSTREAM `VqlInferenceFinalizedFrame` is acked by pygato's `CortexFrameProcessor`.

## Close codes

From [`wire/transport.py`](../src/voqalize/sdk/wire/transport.py):

| Code | Name | Semantics |
|---|---|---|
| `4000` | `NoAgent` | Permanent — no agent process for this `agent_id` is registered. SDK raises `PermanentClose`. |
| `4001` | `AgentGone` | Transient — peer disconnected. Reconnect with exponential backoff. |
| `1000` | normal close from consumer | No reconnect. |
| anything else | — | Transient. Reconnect with backoff. |

Backoff: starts at 100ms, exponential ×2, capped at 60s, ±10% jitter (see [`WireConfig`](../src/voqalize/sdk/wire/transport.py)).

## Reference

- `VQL_FRAME_CLASSES` in [`frames.py`](../src/voqalize/sdk/wire/frames.py) — exhaustive registry. The completeness test asserts every entry round-trips through `CortexFrameSerializer`.
- `cortex/internal/protocol/protocol.go` — Go-side counterpart (envelope constants).
