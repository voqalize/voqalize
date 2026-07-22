# Voqalize Agent SDK (Python)

Part of the Voqalize voice AI platform: **you bring the brain, we bring the voice.**

**Pipecat-free.** Installing this SDK pulls **no** `pipecat` dependency — the
promise is "bring the brain, not the voice infra." The customer writes a
`Brain` of callbacks; the wire is plain protobuf and the Brain surface is
plain dataclasses. (Pipecat lives only inside the Voqalize voice runtime, on
the far side of the socket.) A native Go SDK speaks the same `Vql*` wire.

The **`Brain` is the sole customer surface** — there is no raw `FrameProcessor`
path. One Brain runs on either transport; a config flip picks which, with no
brain-code change (`serve_auto`). The SDK **does not own a WebSocket server** — its
production entrypoint is a *connected socket*:

- **`run_session()` (`src/voqalize/sdk/session.py`) — the primary inbound surface.**
  Your web framework (FastAPI/Starlette, Django Channels, Flask, aiohttp) accepts
  the upgrade and hands the connected socket (anything with `send(bytes)`/`recv()->bytes` —
  the `Channel` protocol) to the SDK, along with the URL `session_id` and the
  `Authorization` header. The voice runtime dials `{brain_url}/s/{session_id}` per
  session; one connection = one session. No Cortex relay, no server owned by the SDK.
- **`DirectAgent` / `serve_direct()` (`src/voqalize/sdk/inbound.py`) — a localhost/dev convenience.**
  Owns a `websockets` server and runs each connection through the *same* `run_session`
  loop. For quick scripts and local dev only.
- **`CortexAgent` / `serve()` (`src/voqalize/sdk/outbound.py`) — the optional fallback.**
  One outbound multiplexed WebSocket to a Cortex relay; many sessions demuxed by a
  16-byte prefix. For brains that can't accept inbound (serverless/FaaS, laptops,
  egress-only).

## Install

```bash
pip install voqalize-agent-sdk               # core, pipecat-free
pip install "voqalize-agent-sdk[examples]"   # + deps used only by examples/
```

## Layout

- `src/voqalize/sdk/brain.py` — the ergonomic surface: `Brain` (implement
  `on_interaction`; the rest are optional — `on_session_start`/`on_session_end`/
  `on_inference_finalized`/`on_app_event`/`on_error`) + `Session`/`Interaction`/
  `Inference`/`Conversation`/`Outcome`/`AppEvent`, the `_BrainAdapter` that maps
  `Vql*` frames ↔ callbacks, and the entry points (`serve`/`serve_direct`/
  `make_agent`/`make_direct_agent`/`brain_factory`).
- `src/voqalize/sdk/engine.py` — the pipecat-free per-session runtime:
  `SessionRunner` (two-lane in/out, system-first feeder, ack-after-dispatch,
  drop-newest + `ErrorFrame`, teardown), the `Emitter` / `SessionAdapter` /
  `SessionFactory` / `RunnerHost` seams. **One runner drives both transports.**
- `src/voqalize/sdk/session.py` — the connection-handoff surface: the `Channel`
  protocol (`send`/`recv` bytes), `run_session()` (verify token → run one session
  over a caller-supplied channel), `serve_channel()` (the transport-neutral loop,
  no auth — reused by `DirectAgent`), and `verify_token`. Owns no server.
- `src/voqalize/sdk/inbound.py` — `DirectAgent` (localhost WS server) +
  `_ServerChannel` (adapts a `websockets` `ServerConnection` to `Channel`);
  verifies and delegates to `serve_channel`.
- `src/voqalize/sdk/outbound.py` — `CortexAgent` (multiplexed demux + shared fair
  writer over one wire), implementing `RunnerHost`.
- `src/voqalize/sdk/_platform_keys.py` — the embedded Voqalize public key(s) the
  direct server verifies against by default.
- `src/voqalize/sdk/wire/` — plain-dataclass `Vql*` + lifecycle/RTVI frames,
  `FrameDirection`, `is_system()`, `CortexFrameSerializer` (protobuf transcoder,
  no base class), `Wire`/`MultiplexedWire` transport, protobuf stubs.

## Core invariants

- **Pipecat-free customer surface.** `import voqalize.sdk` loads zero pipecat
  modules. `pyjwt` is a runtime dependency (the direct server verifies the
  runtime's token).
- **Connection-handoff, not a server.** The production inbound surface is
  `run_session(channel, *, brain, session_id, token=...)`: the customer's
  framework owns the listener + upgrade and hands the SDK a connected `Channel`.
  The SDK **verifies by default** against the embedded Voqalize public keys
  (`_platform_keys.py`) — the token shape is uniform for every brain
  (`iss=pygato, aud=brain, sub=session_id`), and `sub` must equal the passed
  `session_id`. The audience is a protocol constant (`BRAIN_AUDIENCE = "brain"`),
  verified unconditionally alongside `iss="pygato"` and `exp` — there is no
  per-agent audience and no `audience=` parameter; override `public_keys=`, or
  `allow_unverified=True` (local dev). A bad token raises `SessionRejected`
  (caller closes 4000). `serve_direct()` is the localhost wrapper that owns a
  `websockets` server and calls the same loop. One socket = one session; framing
  is bare `[1-byte direction][protobuf]`, session implicit in the URL.
- **Config picks the transport, brain code doesn't change.**
  `serve_auto(MyBrain, mode=…)` (default `$VOQAL_AGENT_MODE`) dispatches to `serve`
  (outbound Cortex) or `serve_direct` (localhost inbound); production inbound
  mounts `run_session` in the customer's framework. Same `Brain` either way.
- **Cortex (fallback):** one `CortexAgent` process → one outbound WebSocket to a
  `wss://.../agent` URL. Auth is `Authorization: Bearer <api_key>` (or a
  per-connect JWT via `authorization_provider`) + `X-Agent-Version`. Many sessions
  multiplex over the connection, demuxed by a 16-byte raw `session_id` prefix.
- **One `SessionRunner` per `session_id`.** `factory(emitter)` (a `SessionFactory`)
  runs once per session, building a fresh `_BrainAdapter(Brain(), emitter)`.
  Cross-session writes are structurally unreachable. Holds identically for both
  transports — `direct` just has one session per connection.
- **Two lanes each way.** System frames (`VqlStart` / `Interruption` / `Cancel`,
  per `is_system()`) ride a priority lane that bypasses queued data; everything
  else rides a bounded normal lane (default 256) with **drop-newest**. `End` is
  *not* system — it rides the normal lane so a session tears down only after its
  queued data drains.
- **Ack-gated ordering.** Every wire-vocab data frame carries `request_id > 0`.
  The runner emits an `Ack(request_id)` envelope **after** `adapter.handle_frame`
  returns — so the ack FIFOs behind any frames the handler emitted synchronously.
  The adapter **spawns** `on_interaction` (rather than awaiting it), so the
  `VqlUserText` ack is prompt and the runtime's per-frame flow control keeps moving.
- **Interruption is a drain barrier.** Barge-in rides the wire as a field-less
  `InterruptionFrame` (system lane); the adapter cancels the in-flight interaction
  task(s) and echoes an `InterruptionFrame` back on the outbound system lane — the
  runtime's drain barrier. Correlation lives on `inference_id`, not on the interrupt.
- **Backpressure never kills a session.** On normal-lane overflow the runner drops
  the newest frame and delivers a non-fatal `ErrorFrame` to the adapter
  (edge-triggered: one per congestion episode per direction), surfaced to the Brain
  via optional `on_error`.
- **Framework-owned `Conversation` (heard-text contract).** The SDK commits the
  user utterance at interaction start and one assistant message per inference from
  its HEARD text at finalize; the Brain keeps no parallel history and cannot commit
  generated text.

## Read next

- [docs/architecture.md](docs/architecture.md) — connection model, per-session engine, ack-gated ordering, backpressure, reconnect.
- [docs/decisions.md](docs/decisions.md) — why the SDK is pipecat-free, why the Brain is the sole surface, why routing stays out of the SDK, drop-newest, etc.
- [docs/wire-protocol.md](docs/wire-protocol.md) — envelope shapes, frame vocabulary, close codes.
- `examples/` — runnable brains: `echo`, `travel`, `grocery_brain`, `fastapi_inbound`.

## Development

```bash
uv run pytest
```

Integration tests run a `FakeCortex` over real TCP; the runtime leg is simulated
by the SDK's own `Wire` client. No `MagicMock` / `AsyncMock` anywhere.
