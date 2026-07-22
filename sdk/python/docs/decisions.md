# Decisions

The *why* behind the SDK's shape. Each entry: the decision, the reasoning, what was rejected.

---

## The SDK is intentionally thin — pipecat `FrameProcessor`, not a `Session` helper

**Decision:** Customers write a plain pipecat `FrameProcessor`. No subclassing of an SDK base class, no decorators, no `@on_event` registrations, no `Session` object that wraps state.

**Why:** Anything more opinionated is a guess at how customer agents want to be structured. The pipecat ecosystem already has context aggregators, LLM services, observers, RTVI — customers who want any of that can compose with the standard pipecat building blocks because our frames *are* pipecat frames. A "smart" SDK would lock customers out of pipecat. A thin SDK lets them use as much or as little of pipecat as they like.

**Rejected:** A `BaseAgent` class with hooks (`on_user_message`, `on_interruption`, `on_function_call`). Convenient at first; calcifies the agent's shape and forces every new pattern through a release of the SDK.

---

## Vql frames subclass their pipecat equivalents

**Decision:** `VqlStartFrame extends StartFrame`. `VqlLLMTextFrame extends LLMTextFrame`. Etc. See [`wire/frames.py`](../src/voqalize/sdk/wire/frames.py). Interruption is **not** a Vql subclass — it rides the wire as pipecat's native `InterruptionFrame` (field-less, both directions), so `broadcast_interruption`'s cancel+reset is identical on both sides; correlation lives on `inference_id`, not on the interrupt.

**Why:** Pipecat processors (context aggregators, LLM response handlers, RTVI observers) key off `isinstance(frame, LLMTextFrame)`. If our frames were a parallel hierarchy, customers would have to write an adapter to bridge them. By subclassing, every off-the-shelf pipecat processor recognizes Vql frames automatically. Pipecat's `SystemFrame` bypass semantics also apply transitively — `VqlStartFrame` gets queue-bypass behavior for free, as does the native `InterruptionFrame`.

**Rejected:** Parallel `Vql*` hierarchy. Requires an adapter for every pipecat integration; permanent maintenance tax.

---

## One multiplexed WebSocket per process, demuxed by 16-byte session prefix

**Decision:** The agent process opens one WebSocket to `/agent`. Per-message framing prepends the 16-byte raw `session_id` (matches [`cortex/internal/protocol/protocol.go`](../../cortex/internal/protocol/protocol.go) `SessionIDLen`). Inside the process, `_SessionRunner` per session_id owns its own pipeline.

**Why:** One TCP connection per session would be N× the file descriptors, N× the TLS handshakes, and N× the keepalive traffic. Multiplexing on a single connection is the standard answer. The 16-byte raw prefix is the minimum: it's the UUID bytes, no separator, no length field, fixed offset. Cortex routing decisions never touch the protobuf payload.

**Rejected:** TCP-per-session. Fine at 10 sessions, terrible at 10,000.

**Rejected:** Hex-string session IDs in the prefix. Doubles the prefix size for no benefit; raw UUID bytes are universally available.

---

## Caller supplies the Cortex URL; SDK does no routing

**Decision:** `CortexAgent(cortex_url=..., api_key=..., version=...)` takes the Cortex URL as an opaque string. Customer agents read it from `VOQALCLOUD_CORTEX_URL`; the platform's reference agents do the same. Cortex runs as a single process behind a single URL — there is no ring, hash, or per-agent routing decision anywhere.

**Why:** Where/how Cortex is deployed is an *infrastructure* detail, not an SDK contract. The SDK never knew the agent's pool key anyway — Cortex resolves the Bearer credential (customer `ak_…` via controlplane lookup, platform JWT via RSA verification) to a pool key internally, for its own agent-pool bookkeeping, unrelated to which URL the customer dials. Letting the operator pick the URL also makes single-Cortex local-dev trivial.

**Rejected:** SDK computes a shard/hash from an `agent_id` (an earlier fixed-32-DNS-ring design considered this). The SDK doesn't know the agent's pool key — Cortex does, after authenticating the credential. Asking the customer to also know their pool key for routing is the leak. Moot now that Cortex is single-process, but the reasoning still holds if multi-node HA is revisited later — routing must never be the SDK's job.

**Rejected:** A service-discovery layer (etcd, Consul, control-plane lookup). Reintroduces the operational tax we removed by killing Switchboard. The single env var is the discovery layer.

---

## Per-session backpressure: bounded normal lane, drop-newest, edge-triggered ErrorFrame

**Decision:** [`SessionBuffer`](../src/voqalize/sdk/_session_buffer.py) bounds each session's normal lane at 256 frames (default). On overflow, drop the *newest* frame and emit one non-fatal `ErrorFrame` per congestion episode. The episode clears when the lane drains below half-full.

**Why:** A slow `process_frame` on session A must not be able to stall the wire reader for B, C, D — otherwise one bad customer agent (or one slow LLM) freezes every other session. The buffer is the isolation boundary.

Drop-newest (not drop-oldest) keeps already-in-flight conversations making forward progress; the dropped frame is the one that hadn't started being acted on yet. Edge-triggered `ErrorFrame` (one per episode, not one per drop) avoids spamming the customer pipeline with hundreds of errors during a sustained back-pressure event — they get one alert, then silence until recovery.

System lane (priority, ~unbounded modulo a tripwire) ensures the native `InterruptionFrame` always cuts through.

**Rejected:** Blocking the wire reader on customer back-pressure. Couples sessions and turns the slowest into the system bottleneck.

**Rejected:** Killing the session on overflow. Surgical drops degrade gracefully; killing is hostile.

---

## Ack-gated frame ordering via `_AckSentinel`

**Decision:** Every wire-vocab data frame carries `request_id > 0`. The runner enqueues an `_AckSentinel(ack_id=request_id)` immediately behind every inbound data frame. When the sentinel reaches `_SessionOutbound` it gets serialized as an `Ack` envelope to Cortex. Pipecat's `__process_queue` is FIFO single-worker, so the sentinel is guaranteed to flow *after* whatever the customer pushed during the original frame's `process_frame`.

**Why:** Pygato's `CortexFrameProcessor` (the bridge) needs to know when a frame has been *fully* consumed — not just received, but processed including downstream pushes. Without that signal, pygato would either pipeline blindly (causing reorder under variable processing time) or assume frame-at-a-time pessimistically (wasting throughput).

The sentinel-in-the-pipeline trick uses pipecat's own FIFO guarantee as the synchronization mechanism. No locks, no waits, no separate ack channel — the ack is just another frame.

**Rejected:** Application-level RPCs (request/response IDs in custom protocol). Reinvents what pipecat's queue already gives us.

**Rejected:** No ordering guarantee. Works for single LLM responses; falls apart for any conversational logic that depends on prior frames being applied.

---

## Reconnect tears down all sessions; SDK does not re-send `VqlStartFrame`

**Decision:** On WebSocket reconnect, `CortexAgent._on_reconnect` cancels every open `_SessionRunner` and clears `self._sessions`. New sessions only start when a fresh `session_id` arrives on the reconnected wire.

**Why:** A session's state lives inside the customer's `FrameProcessor` instance. Once the wire drops, that state is no longer reachable by the other side — the agent has no way to know what point in the conversation pygato thinks it's at. Replaying `VqlStartFrame` would trample whatever lives in the processor's `self` and create a phantom-clone session.

The right policy is: declare bankruptcy on every in-flight session, let pygato decide whether to re-establish (it usually won't, because pygato is also crash-only on this dimension). New sessions arrive normally.

**Rejected:** SDK auto-replays `VqlStartFrame`. Wrong layer to own session lifecycle decisions.

---

## Customers forward unconsumed frames; no automatic passthrough

**Decision:** Customer processors must explicitly `await self.push_frame(frame, direction)` for anything they don't consume — including `StartFrame`, `EndFrame`, `CancelFrame`, `SystemFrame`s, and any data frame they don't recognize.

**Why:** Pipecat's pipeline machinery depends on control frames reaching the Sink. If a processor swallows `StartFrame`, the pipeline never finishes starting. If it swallows `EndFrame`, teardown stalls. Auto-forwarding "everything I didn't match" would also auto-forward things the customer *did* mean to consume but forgot to return from — turning a bug into silent misbehavior.

Explicit forwarding is one extra line. The default branch is always `await self.push_frame(frame, direction)`.

**Rejected:** Auto-forward unhandled frames. Saves a line; masks bugs.

---

## Protobuf wire, hand-mirrored stubs (for now)

**Decision:** [`wire/_frames_pb2.py`](../src/voqalize/sdk/wire/_frames_pb2.py) is a hand-mirrored copy of the protobuf definitions. There's no generated-from-source pipeline today; the schema is small and stable.

**Why:** A single small Python package with no second consumer doesn't need a build step. The frame vocabulary changes rarely; when it does, both sides update in lockstep within a single PR. Adding a code-generation pipeline now would slow every change for no current benefit.

**When to revisit:** As soon as a second consumer needs the protobuf (a non-Python SDK, an external integration). At that point publish `proto/frames.proto` at the repo root and regenerate stubs from there. See the open follow-up in [../AGENTS.md](../AGENTS.md).
