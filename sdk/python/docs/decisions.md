# Decisions

The *why* behind the SDK's shape. Each entry: the decision, the reasoning, what was rejected.

---

## The customer surface is a `Brain` of callbacks — and the SDK is pipecat-free

**Decision:** the sole customer surface is `voqalize.sdk.Brain` — subclass it,
implement `on_interaction(interaction)` (the rest are optional hooks), and drive
turns through `interaction.say()` / `speak(...)`. Installing the SDK pulls
**no** `pipecat` dependency; the `Vql*` wire is plain protobuf and the Brain
surface is plain dataclasses.

**Why:** the brain only ever does text-in / text-out plus tool calls. An earlier
SDK made the customer write a pipecat `FrameProcessor`, which dragged the entire
pipecat framework into their process — a heavy dependency, a parallel mental model
(frame direction, ack sentinels, aggregators, `push_frame` forwarding) that a brain
author never needed, and a hard coupling to pipecat's release cadence. `Brain`
exposes exactly the text/tool surface and nothing else. pipecat now lives **only**
inside PyGato (the runtime), on the far side of the socket, so the customer installs
a small pure-Python package and the same `Brain` runs identically inbound or over
Cortex. This mirrored the pipecat-free Go SDK, which spoke the same wire; the Go
SDK was removed (2026-08) while the platform surface moves fast on the
Python/ADK track — the language-neutral wire (`proto/`) is what a future Go SDK
would build back against.

**Rejected:** the pipecat `FrameProcessor` surface (the prior model). Forced every
brain author to learn pipecat and pinned the SDK to pipecat's versioning for no
benefit on the text-only brain side.

**Rejected:** a heavier `BaseAgent` with a large hook taxonomy
(`on_user_message`/`on_interruption`/`on_function_call`/…). The `Interaction` /
`Inference` objects already model the turn structure; a flat hook zoo calcifies the
agent's shape and forces every new pattern through an SDK release.

---

## `Vql*` frames are plain dataclasses in the SDK (they subclass pipecat only inside PyGato)

**Decision:** in the SDK, each `Vql*` frame is a plain dataclass in
[`wire/frames.py`](../src/voqalize/sdk/wire/frames.py) mirroring the protobuf.
There is no pipecat import. (On the *runtime* side, inside PyGato,
`VqlStartFrame extends StartFrame`, `VqlLLMTextFrame extends LLMTextFrame`, etc., so
stock pipecat processors recognize them — but that inheritance is PyGato's, not the
SDK's.) Interruption rides the wire as a field-less native `InterruptionFrame` in
both directions; correlation lives on `inference_id`, not on the interrupt.

**Why:** the wire is a language-neutral protobuf contract, so any language's SDK
can mirror the same frames as its own native structs. Binding the *SDK's*
representation to pipecat's class hierarchy would have forced pipecat on every
consumer and blocked non-Python ports (the now-removed Go SDK proved this out).
Keeping the pipecat-subclassing on the runtime side gives PyGato the aggregator
compatibility it wants without leaking the dependency outward.

**Rejected:** SDK frames that subclass pipecat. Reintroduces the pipecat dependency
the SDK deliberately dropped, and has no analog in a non-Python SDK.

---

## One multiplexed WebSocket per process (Cortex fallback), demuxed by 16-byte session prefix

**Decision:** on the Cortex fallback, the agent process opens one WebSocket to
`/agent`. Per-message framing prepends the 16-byte raw `session_id`. Inside the
process, one `SessionRunner` per `session_id` owns its own engine. (The primary
inbound path — `run_session` — is instead one socket per session, session
implicit in the URL; no prefix.)

**Why:** one TCP connection per session on the outbound path would be N× the file
descriptors, N× the TLS handshakes, and N× the keepalive traffic. Multiplexing on a
single connection is the standard answer. The 16-byte raw prefix is the minimum: the
UUID bytes, no separator, no length field, fixed offset. Cortex routing decisions
never touch the protobuf payload.

**Rejected:** TCP-per-session on the outbound path. Fine at 10 sessions, terrible at
10,000.

**Rejected:** hex-string session IDs in the prefix. Doubles the prefix size for no
benefit; raw UUID bytes are universally available.

---

## Caller supplies the Cortex URL; SDK does no routing

**Decision:** `CortexAgent(cortex_url=..., api_key=..., version=...)` takes the
Cortex URL as an opaque string. Customer agents read it from config; the platform's
reference agents do the same. Cortex runs as a single process behind a single URL —
there is no ring, hash, or per-agent routing decision anywhere.

**Why:** where/how Cortex is deployed is an *infrastructure* detail, not an SDK
contract. The SDK never knew the agent's pool key anyway — Cortex resolves the Bearer
credential (customer `sk_…` via controlplane lookup) to a pool key internally, for
its own agent-pool bookkeeping, unrelated to which URL the customer dials. Letting the
operator pick the URL also makes single-Cortex local-dev trivial.

**Rejected:** SDK computes a shard/hash from an `agent_id` (an earlier
fixed-32-DNS-ring design considered this). The SDK doesn't know the agent's pool key —
Cortex does, after authenticating the credential. Moot now that Cortex is
single-process, but the reasoning still holds if multi-node HA is revisited: routing
must never be the SDK's job.

**Rejected:** a service-discovery layer (etcd, Consul, control-plane lookup).
Reintroduces the operational tax we removed by killing Switchboard. The single URL is
the discovery layer.

---

## Per-session backpressure: bounded normal lane, drop-newest, edge-triggered ErrorFrame

**Decision:** the `SessionRunner` ([`engine.py`](../src/voqalize/sdk/engine.py))
bounds each session's normal lane at 256 frames (default). On overflow, drop the
*newest* frame and deliver one non-fatal `ErrorFrame` to the adapter per congestion
episode (surfaced to the Brain via optional `on_error`). The episode clears when the
lane drains below half-full.

**Why:** a slow `on_interaction` on session A must not be able to stall the wire
reader for B, C, D — otherwise one bad brain (or one slow LLM) freezes every other
session on a shared outbound connection. The bounded lane is the isolation boundary.

Drop-newest (not drop-oldest) keeps already-in-flight conversations making forward
progress; the dropped frame is the one that hadn't started being acted on yet.
Edge-triggered `ErrorFrame` (one per episode, not one per drop) avoids spamming the
Brain with hundreds of errors during a sustained back-pressure event — one alert, then
silence until recovery. The system lane (priority, ~unbounded modulo a tripwire)
ensures the native `InterruptionFrame` always cuts through.

**Rejected:** blocking the wire reader on brain back-pressure. Couples sessions and
turns the slowest into the system bottleneck.

**Rejected:** killing the session on overflow. Surgical drops degrade gracefully;
killing is hostile — and a session is never killed for backpressure.

---

## Ack-gated frame ordering via an outbound-lane `_Ack`

**Decision:** every wire-vocab data frame carries `request_id > 0`. After
`adapter.handle_frame(frame)` returns, the runner enqueues an `_Ack(request_id)` onto
the **outbound normal lane** — so the ack FIFOs *behind* any response frames the
handler emitted synchronously. Acks bypass the lane bound (`append_ack`): a dropped
ack would hang PyGato's per-frame flow control. Crucially, `_BrainAdapter` **spawns**
`on_interaction` as a task rather than awaiting it, so the `VqlUserText` ack fires
promptly and PyGato keeps sending; the reply streams out of the spawned task.

**Why:** PyGato's `CortexLLMService` (the brain bridge) needs to know when a frame has
been dispatched, in order, so it can enforce strict in-order round-trips without
either pipelining blindly (reorder under variable processing time) or going
frame-at-a-time pessimistically (wasted throughput). Using the outbound lane's FIFO as
the ordering mechanism means no locks, no separate ack channel — the ack is just
another queued item.

**Rejected:** application-level RPCs (request/response IDs in a custom protocol).
Reinvents what the lane ordering already gives us.

**Rejected:** no ordering guarantee. Works for a single LLM response; falls apart for
any conversational logic that depends on prior frames being applied.

---

## Reconnect tears down all sessions; SDK does not re-send `VqlStartFrame`

**Decision:** on a transient WebSocket close (Cortex path), every open `SessionRunner`
is cancelled and cleared. New sessions only start when a fresh `session_id` arrives on
the reconnected wire. A `4000` close propagates out as `PermanentClose`.

**Why:** a session's state lives inside the Brain instance the adapter holds. Once the
wire drops, that state is no longer reachable by the other side — the brain has no way
to know what point in the conversation PyGato thinks it's at. Replaying `VqlStartFrame`
would trample the live Brain state and create a phantom-clone session. The right policy
is to declare bankruptcy on every in-flight session and let PyGato decide whether to
re-establish (it usually won't — PyGato is also crash-only on this dimension).

**Rejected:** SDK auto-replays `VqlStartFrame`. Wrong layer to own session-lifecycle
decisions.

---

## The SDK owns frame forwarding and the heard-text transcript — the Brain never touches the wire

**Decision:** the Brain does not forward, push, or ack frames. The `_BrainAdapter`
consumes each inbound `Vql*` frame, invokes the matching callback, and the
`SessionRunner` owns acking and teardown. Lifecycle/control frames
(`VqlStart`/`Interruption`/`End`/`Cancel`) are handled by the engine, not the Brain.
The SDK also owns the `Conversation`: it commits the user utterance at interaction
start and one assistant message per inference from its **heard** text at finalize;
the Brain reads `interaction.conversation.messages` and cannot commit generated text.

**Why:** the prior pipecat model made the customer responsible for
`await self.push_frame(frame, direction)` on everything they didn't consume —
swallow a `StartFrame` and the pipeline never starts; swallow an `EndFrame` and
teardown stalls. That turned a forgotten line into silent misbehavior and leaked
pipeline mechanics into brain code. Making the engine own forwarding removes the
entire class of bug. Owning the transcript in the SDK enforces the heard-text
contract (the generated-but-barged-in tail never lands in the record) in one place
instead of trusting every brain to get it right.

**Rejected:** brain-driven `push_frame` forwarding. Leaks pipeline internals and
masks bugs as silent frame loss.

---

## Protobuf wire, hand-mirrored stubs

**Decision:** [`wire/_frames_pb2.py`](../src/voqalize/sdk/wire/_frames_pb2.py) is
kept in lockstep with the canonical `proto/frames.proto`. `make proto` regenerates and
copies the stubs to every consumer (pygato, this SDK); CI fails on diff.

**Why:** the schema is small and stable and changes rarely; when it does, all
consumers update in a single lockstep change. There is more than one consumer
across the platform (pygato, this SDK, and any future non-Python SDK), which is
exactly why the canonical schema lives at `proto/frames.proto` and is generated
from there rather than edited per-copy.
